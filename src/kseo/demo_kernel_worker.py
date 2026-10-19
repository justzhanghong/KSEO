"""Kernel 子流程的 CPU oracle 提取和独立验证示例。"""

import json
import os
import runpy
from pathlib import Path

identity = json.loads(Path(os.environ["KSEO_IDENTITY_PATH"]).read_text())
reference = Path(os.environ["KSEO_KERNEL_REFERENCE_DIR"])
output = Path(os.environ["KSEO_KERNEL_RESULT"])
if os.environ["KSEO_KERNEL_PHASE"] == "extract":
    request = json.loads(Path(os.environ["KSEO_KERNEL_REQUEST"]).read_text())
    model = runpy.run_path(str(Path(request["source_dir"]) / "demo_kernel.py"))
    cases = [{"id": "negative", "input": -2}, {"id": "zero", "input": 0}, {"id": "positive", "input": 3}]
    for case in cases:
        case["expected"] = model["kernel_value"](case["input"])
    (reference / "oracle.json").write_text(json.dumps({"scale": model["KERNEL_SCALE"], "cases": cases}))
    result = {"identity": identity, "kind": "synthetic", "cases": [case["id"] for case in cases],
              "editable_files": ["demo_kernel.py"]}
else:
    oracle = json.loads((reference / "oracle.json").read_text())
    model = runpy.run_path(str(Path(os.environ["KSEO_KERNEL_CANDIDATE_DIR"]) / "demo_kernel.py"))
    passed = [case["id"] for case in oracle["cases"] if model["kernel_value"](case["input"]) == case["expected"]]
    result = {"identity": identity, "kind": "synthetic", "oracle_sha256": identity["oracle_sha256"],
              "passed_cases": passed, "checks": {"path_exercised": True, "numerics": len(passed) == len(oracle["cases"])},
              "speedup": oracle["scale"] / model["KERNEL_SCALE"]}
result["schema_version"] = 1
output.write_text(json.dumps(result))
