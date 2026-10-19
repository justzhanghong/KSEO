"""可运行示例的合同构造。"""

from pathlib import Path
from copy import deepcopy


def task(*, agent: bool = False, pipeline: bool = False) -> dict:
    command = ["{python}", "{package_dir}/demo_worker.py"]
    config = {"schema_version": 1, "name": "kseo_cpu_demo", "mode": "synthetic",
              "inputs": {"model": "synthetic-demo", "image": "synthetic-image", "workload": "synthetic-v1"},
              "context": {"model_family": "synthetic", "gpu_arch": "cpu-demo", "backend": "synthetic", "workload": "long_context", "capabilities": []},
              "source": {"kind": "files", "path": str(Path(__file__).parent / "data"), "include": ["demo_kernel.py"]},
              "parameters": {"chunk_tokens": 512},
              "steps": [{"name": name, "command": command, "timeout_seconds": 15}
                        for name in ("preflight", "profile", "benchmark", "quality", "api")],
              "cleanup": {"command": command, "timeout_seconds": 15},
              "validation": {"zero_cache_reads": True, "quality_samples": 6,
                             "cases": [{"id": "short_c1", "requests": 3, "input_tokens": 1024, "output_tokens": 16},
                                       {"id": "long_c2", "requests": 4, "input_tokens": 8192, "output_tokens": 16}],
                             "gates": [
                                 {"name": "请求全部完成", "stage": "benchmark", "field": "benchmark.failed_requests", "op": "==", "value": 0},
                                 {"name": "长上下文 TTFT", "stage": "benchmark", "field": "benchmark.cases.long_c2.ttft_ms.mean", "op": "<=", "value": 200},
                                 {"name": "TPOT 硬门禁", "stage": "benchmark", "field": "benchmark.cases.long_c2.tpot_ms.mean", "op": "<=", "value": 30},
                                 {"name": "完整样本精度", "stage": "quality", "field": "quality.accuracy", "op": ">=", "value": 0.95},
                                 {"name": "数值一致性", "stage": "quality", "field": "quality.checks.numerics", "op": "==", "value": True},
                                 {"name": "请求隔离", "stage": "api", "field": "api.checks.request_isolation", "op": "==", "value": True}],
                             "objective": {"field": "benchmark.cases.long_c2.ttft_ms.mean", "direction": "min"}},
              "optimizer": {"kind": "grid", "space": {"chunk_tokens": [512, 1024, 2048]}},
              "budget": {"max_trials": 4, "max_wall_seconds": 120, "max_gpu_hours": 1},
              "resources": {"gpu_count": 0, "keys": ["kseo:cpu-demo"]}, "final_validation": True}
    if agent:
        config["optimizer"].update({"kind": "agent", "command": ["{python}", "{package_dir}/demo_proposer.py"],
                                    "timeout_seconds": 15, "allow_source_changes": True})
    if pipeline:
        proposer = {"command": ["{python}", "{package_dir}/demo_pipeline_proposer.py"],
                    "timeout_seconds": 15, "allow_source_changes": True}
        worker = {"command": ["{python}", "{package_dir}/demo_kernel_worker.py"], "timeout_seconds": 15}
        config["optimizer"].update({"kind": "pipeline", "allow_source_changes": True,
                                    "max_cycles": 12, "final_reserve_seconds": 10,
                                    "scheduling": deepcopy(proposer),
                                    "kernel": {"extractor": deepcopy(worker), "proposer": deepcopy(proposer), "validator": deepcopy(worker),
                                               "min_speedup": 1.01}})
        config["budget"].update({"max_trials": 8, "max_wall_seconds": 240})
    return config
