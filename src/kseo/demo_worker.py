"""显式标记为 synthetic 的确定性 CPU adapter。"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
from pathlib import Path


def main() -> None:
    if os.environ["KSEO_STAGE"] == "cleanup":
        return
    identity = json.loads(Path(os.environ["KSEO_IDENTITY_PATH"]).read_text())
    parameters = json.loads(Path(os.environ["KSEO_PARAMETERS_PATH"]).read_text())
    stage = os.environ["KSEO_STAGE"]
    directory = Path(os.environ["KSEO_STAGE_DIR"])
    payload = {"schema_version": 1, "identity": identity, "kind": "synthetic", "checks": {}, "runtime": {}}
    if stage == "preflight":
        payload["runtime"] = {"gpu_arch": "cpu-demo", "image": identity["image"]}
        payload["checks"] = {"source_readable": True}
    elif stage == "profile":
        payload["checks"] = {"primary_bottleneck": "synthetic_scheduling", "note": "CPU 示例，仅演示反馈协议"}
        model = runpy.run_path(str(Path(os.environ["KSEO_SOURCE_DIR"]) / "demo_kernel.py"))
        scheduled = model["SCHEDULER_SCALE"] < 1
        optimized = model["KERNEL_SCALE"] < 1
        payload["profile"] = {"scope": "critical_path", "hotspots": [
            {"id": "launch_wait", "kind": "scheduling", "share": 0.1 if scheduled else 0.6,
             "achievable_speedup": 1 if scheduled else 1.5, "editable": True},
            {"id": "demo_kernel", "kind": "kernel", "share": 0.25 if optimized else (0.65 if scheduled else 0.35),
             "achievable_speedup": 1 if optimized else 1.5, "editable": True}]}
    elif stage == "benchmark":
        kernel = runpy.run_path(str(Path(os.environ["KSEO_SOURCE_DIR"]) / "demo_kernel.py"))
        scale = kernel["KERNEL_SCALE"] * kernel["SCHEDULER_SCALE"]
        chunk = parameters["chunk_tokens"]
        ttft, tpot = {512: (120, 24), 1024: (70, 18), 2048: (45, 60)}[chunk]
        rows = []
        for case_id, input_tokens, count, multiplier in [("short_c1", 1024, 3, 1.0), ("long_c2", 8192, 4, 1.5)]:
            for index in range(count):
                first = ttft * multiplier * scale + index * 0.2
                per_token = tpot * kernel["KERNEL_SCALE"]
                rows.append({"request_id": f"{case_id}-{index}", "case_id": case_id,
                             "status": "completed", "input_tokens": input_tokens, "output_tokens": 16,
                             "cache_read_tokens": 0, "ttft_ms": first, "total_ms": first + per_token * 15})
        raw = directory / "requests.jsonl"
        raw.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        payload.update({"requests_file": raw.name, "requests_file_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()})
    elif stage == "quality":
        rows = [{"sample_id": str(i), "correct": True, "failed": False, "unparseable": False} for i in range(6)]
        raw = directory / "samples.jsonl"
        raw.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        payload.update({"samples_file": raw.name, "samples_file_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()})
        payload["checks"] = {"numerics": True}
    elif stage == "api":
        payload["checks"] = {"request_isolation": True, "context_admission": True}
    Path(os.environ["KSEO_RESULT_PATH"]).write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
