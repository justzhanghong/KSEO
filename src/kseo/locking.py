"""控制器锁和共享资源锁。进程退出时由 OS 释放 flock。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path

from .util import KSEOError, now, read_json, write_json


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise KSEOError(f"资源正在被其他控制器占用: {path}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "time": now()}))
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def resource_locks(directory: Path, keys: list[str], owner: str):
    lease = {"clean": True}
    records = []
    with ExitStack() as stack:
        for key in sorted(set(keys)):
            name = hashlib.sha256(key.encode()).hexdigest() + ".lock"
            stack.enter_context(file_lock(directory / name))
            record = directory / (name + ".lease.json")
            if record.exists():
                previous = read_json(record)
                if not previous.get("released", False) and previous.get("owner") != owner:
                    raise KSEOError(f"资源 {key} 上次未完成清理；请先恢复任务 {previous.get('owner')}")
            records.append((record, key))
        for record, key in records:
            write_json(record, {"owner": owner, "key": key, "released": False, "time": now()})
        try:
            yield lease
        finally:
            for record, key in records:
                write_json(record, {"owner": owner, "key": key, "released": lease["clean"], "time": now()})
