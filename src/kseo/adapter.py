"""现有部署、profile、精度脚本可调用的 adapter 输出辅助函数。"""

import hashlib
import json
import os
from pathlib import Path

from .util import write_json


def emit(*, checks: dict | None = None, runtime: dict | None = None,
         requests: list[dict] | None = None, samples: list[dict] | None = None,
         profile: dict | None = None) -> Path:
    directory = Path(os.environ["KSEO_STAGE_DIR"])
    result = {"schema_version": 1, "identity": json.loads(Path(os.environ["KSEO_IDENTITY_PATH"]).read_text()),
              "kind": os.environ["KSEO_MODE"], "checks": checks or {}, "runtime": runtime or {}}
    if profile is not None:
        result["profile"] = profile
    for key, rows in (("requests_file", requests), ("samples_file", samples)):
        if rows is not None:
            path = directory / ("requests.jsonl" if key == "requests_file" else "samples.jsonl")
            path.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows), encoding="utf-8")
            result[key] = path.name
            result[key + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    path = Path(os.environ["KSEO_RESULT_PATH"])
    write_json(path, result)
    return path
