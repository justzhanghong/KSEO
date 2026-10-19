"""可追踪的 argv 执行器；SSH、Docker 和 AIHub 通过 adapter 接入。"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from .util import KSEOError, now, write_json


class StepFailure(KSEOError):
    def __init__(self, message: str, *, timeout: bool = False):
        super().__init__(message)
        self.timeout = timeout


def expand(text: str, variables: dict[str, str]) -> str:
    for key, value in variables.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def execute(step: dict, directory: Path, variables: dict[str, str], environment: dict[str, str], *, remaining: float) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    timeout = min(float(step.get("timeout_seconds", 300)), remaining)
    if timeout <= 0:
        raise StepFailure("预算已耗尽", timeout=True)
    command = [expand(part, variables) for part in step["command"]]
    env = os.environ.copy()
    env.update(environment)
    env.update({key: expand(value, variables) for key, value in step.get("env", {}).items()})
    for key in environment:
        if key.startswith("KSEO_"):
            env[key] = environment[key]
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    temp = directory / "tmp"
    temp.mkdir(exist_ok=True)
    env["TMPDIR"] = str(temp)
    env["TMP"] = str(temp)
    env["TEMP"] = str(temp)
    cwd = Path(expand(step.get("cwd", "{source_dir}"), variables)).resolve()
    if not cwd.is_dir():
        raise StepFailure(f"工作目录不存在: {cwd}")
    started = time.monotonic()
    record = {"started_at": now(), "timeout_seconds": timeout, "cwd": str(cwd), "pid": None}
    # 不保存 env 或 argv，避免把 adapter 的 credentials 参数带入报告。
    process = None
    try:
        with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            record["pid"] = process.pid
            record["start_ticks"] = process_start_ticks(process.pid)
            write_json(directory / "process.json", record)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                stop_group(process)
                raise StepFailure(f"阶段超时（{timeout:.1f}s）", timeout=True)
            except KeyboardInterrupt:
                stop_group(process)
                raise
    except OSError as exc:
        raise StepFailure(f"无法启动 adapter: {exc}") from exc
    finally:
        record["finished_at"] = now()
        record["elapsed_seconds"] = time.monotonic() - started
        record["returncode"] = process.returncode if process else None
        write_json(directory / "process.json", record)
    if returncode != 0:
        raise StepFailure(f"adapter 退出码 {returncode}，日志位于 {directory}")
    return record


def stop_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # 父进程已退出时，仍可能有忽略 SIGTERM 的子进程留在同一进程组。
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def process_start_ticks(pid: int) -> str | None:
    try:
        # comm 字段可能含空格，先跳过最后一个右括号。
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def recover_processes(directory: Path) -> None:
    from .util import read_json

    paths = [*directory.glob("steps/*/process.json"), *directory.glob("*/process.json"),
             *directory.glob("proposal/process/process.json")]
    for path in paths:
        record = read_json(path)
        pid = record.get("pid")
        if not pid or record.get("returncode") is not None or not record.get("start_ticks"):
            continue
        try:
            if process_start_ticks(pid) == record["start_ticks"] and os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGTERM)
                time.sleep(0.1)
                if process_start_ticks(pid) == record["start_ticks"]:
                    os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
