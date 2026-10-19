"""产物、身份和有限数值处理。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class KSEOError(Exception):
    """可以向用户直接展示的错误。"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=_bad_constant)
    except (OSError, ValueError) as exc:
        raise KSEOError(f"无法读取 JSON {path}: {exc}") from exc


def _bad_constant(value: str) -> None:
    raise ValueError(f"JSON 不允许 {value}")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise KSEOError(f"{label} 必须是有限数值")
    return float(value)


def positive_int(value: Any, label: str, *, zero: bool = False) -> int:
    if type(value) is not int or value < (0 if zero else 1):
        raise KSEOError(f"{label} 必须是{'非负' if zero else '正'}整数")
    return value


def confined(root: Path, relative: str) -> Path:
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise KSEOError(f"产物路径越出工作目录: {relative}")
    return result


def get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KSEOError(f"缺少结果字段: {path}")
        current = current[part]
    return current


def redact(text: str) -> str:
    """对导入文本做基础脱敏；导入结果仍需在发布前审查。"""
    lines = []
    for line in text.splitlines():
        if re.search(r"password|passwd|密码|口令|api[_-]?key|access[_-]?token|secret|credential", line, re.I):
            lines.append("[已移除 credentials 行]")
        else:
            line = re.sub(r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b", "<private-host>", line)
            line = re.sub(r"/(?:nfs|home|mnt|data)/[^\s`\"'<>]+", "<local-path>", line)
            lines.append(line)
    return "\n".join(lines)
