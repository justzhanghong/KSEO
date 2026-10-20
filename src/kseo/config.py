"""任务合同校验。配置使用 JSON，避免运行时依赖。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .util import KSEOError, canonical, finite, positive_int, read_json

STAGES = ("preflight", "build", "deploy", "smoke", "profile", "benchmark", "quality", "api", "stability", "multi_turn", "final_accuracy")
OPS = ("<", "<=", ">", ">=", "==", "!=")


def validate(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise KSEOError("任务合同要求 schema_version=1")
    if config.get("draft", False):
        raise KSEOError("当前是任务草稿，请补齐 adapter、GPU 身份、负载和门禁后设置 draft=false")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", config.get("name", "")):
        raise KSEOError("name 只能包含英文、数字、下划线和连字符")
    if config.get("mode") not in ("measured", "synthetic", "replay"):
        raise KSEOError("mode 必须明确设为 measured、synthetic 或 replay")
    for key in ("inputs", "context", "parameters", "validation", "optimizer", "budget", "resources"):
        if not isinstance(config.get(key), dict):
            raise KSEOError(f"缺少配置对象: {key}")
    inputs = config["inputs"]
    for key in ("model", "image", "workload"):
        if not isinstance(inputs.get(key), str) or not inputs[key]:
            raise KSEOError(f"inputs.{key} 不能为空")
    if config["mode"] == "measured":
        if "@sha256:" not in inputs["image"] or not re.search(r"@sha256:[0-9a-f]{64}$", inputs["image"]):
            raise KSEOError("measured 模式必须冻结完整 image digest")
        if not re.fullmatch(r"[0-9a-f]{64}", inputs.get("workload_sha256", "")):
            raise KSEOError("measured 模式必须提供 workload_sha256")
        if not inputs.get("model_revision"):
            raise KSEOError("measured 模式必须提供模型权重清单或 revision 身份")
        if not config.get("source"):
            raise KSEOError("measured 模式必须提供冻结源码")
    source = config.get("source")
    if source:
        if not isinstance(source, dict):
            raise KSEOError("source 必须是对象")
        if source.get("kind") not in ("git", "files") or not source.get("path"):
            raise KSEOError("source 需要 kind=git/files 和 path")
        if source["kind"] == "git" and not source.get("revision"):
            raise KSEOError("Git source 必须提供 revision")
        if source["kind"] == "files" and not source.get("include"):
            raise KSEOError("files source 必须明确提供 include 文件列表")
    steps = config.get("steps", [])
    if not isinstance(steps, list) or not steps:
        raise KSEOError("steps 不能为空")
    names = []
    for step in steps:
        name = step.get("name")
        if name not in STAGES or name in names:
            raise KSEOError(f"未知或重复阶段: {name}")
        names.append(name)
        validate_command(step)
    if names != sorted(names, key=STAGES.index) or "benchmark" not in names:
        raise KSEOError("steps 必须按预定义顺序排列，并包含 benchmark")
    for command in (config.get("cleanup"),):
        if command:
            validate_command(command)
    if config["mode"] == "measured" and ("preflight" not in names or not config.get("cleanup")):
        raise KSEOError("measured 模式要求 preflight 和幂等 cleanup adapter")
    validation = config["validation"]
    if validation.get('quality_generation'):
        from .generation import validate_generation, output_budget
        from .final_accuracy import _sha
        gen = validation['quality_generation']
        validate_generation(gen)
        manifest = validation.get('quality_manifest', [])
        if not manifest or len(manifest) != validation.get('quality_samples'):
            raise KSEOError('GSM8K 需要完整冻结 quality_manifest')
        ids = [r.get('sample_id') for r in manifest]
        if any(not isinstance(i,str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise KSEOError('GSM8K manifest sample_id 缺失或重复')
        for row in manifest:
            _sha(row.get('prompt_sha256'),'quality.prompt_sha256')
            output_budget(gen,row.get('prompt_tokens'))
    if config["mode"] == "measured" or "final_accuracy" in names or "final_accuracy" in validation:
        from .final_accuracy import validate_policy
        if "final_accuracy" not in names or "final_accuracy" not in validation or not config.get("final_validation", True):
            raise KSEOError("真实优化必须配置 final_accuracy 和最终复验，执行三个完整精度数据集")
        validate_policy(validation["final_accuracy"], config["mode"])
        if not any(g.get("stage") == "final_accuracy" and g.get("field") == "final_accuracy.passed"
                   and g.get("op") == "==" and g.get("value") is True for g in validation.get("gates", [])):
            raise KSEOError("最终精度必须配置 final_accuracy.passed == true 硬门禁")
    from . import milestones
    milestones.validate(validation)
    if milestones.enabled(config) and not any(g.get("stage") == "benchmark" and g.get("field") == "benchmark.failed_requests"
            and g.get("op") == "==" and g.get("value") == 0 and g.get("always_required") is True
            for g in validation["gates"]):
        raise KSEOError("阶段搜索必须始终要求 benchmark.failed_requests == 0，不能放宽失败率")
    if "multi_turn" in names or "multi_turn" in validation:
        from .multi_turn import validate_policy
        if "multi_turn" not in names or "multi_turn" not in validation or not config.get("final_validation", True):
            raise KSEOError("多轮验收必须声明最终阶段与完整策略")
        validate_policy(validation["multi_turn"])
        if not any(g.get("stage") == "multi_turn" and g.get("field") == "multi_turn.passed"
                and g.get("op") == "==" and g.get("value") is True for g in validation["gates"]):
            raise KSEOError("多轮验收必须包含 multi_turn.passed == true 硬门禁")
    cases = validation.get("cases", [])
    if not cases or len({c.get("id") for c in cases}) != len(cases):
        raise KSEOError("validation.cases 不能为空且 id 必须唯一")
    for case in cases:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", case.get("id", "")):
            raise KSEOError("case id 只能包含英文、数字、下划线和连字符")
        for key in ("requests", "input_tokens", "output_tokens"):
            positive_int(case.get(key), f"case.{key}")
        if case.get("cache_policy", "zero_read") not in ("zero_read", "reuse_allowed"):
            raise KSEOError("case.cache_policy 必须明确为 zero_read/reuse_allowed")
    gates = validation.get("gates", [])
    if not gates:
        raise KSEOError("至少需要一个明确验收门禁")
    gate_names = set()
    for gate in gates:
        if not gate.get("name") or gate["name"] in gate_names:
            raise KSEOError("门禁 name 不能为空或重复")
        gate_names.add(gate["name"])
        if gate.get("stage") not in names or gate.get("op") not in OPS or not isinstance(gate.get("field"), str):
            raise KSEOError(f"门禁配置错误: {gate}")
        if gate["field"].split(".")[0] not in names:
            raise KSEOError("门禁字段需要以阶段名开头")
        if names.index(gate["field"].split(".")[0]) > names.index(gate["stage"]):
            raise KSEOError("门禁不能依赖尚未执行的阶段")
        if "value" not in gate:
            raise KSEOError("门禁必须提供 value")
        if gate["op"] in ("<", "<=", ">", ">="):
            finite(gate["value"], "门禁阈值")
    objective = validation.get("objective", {})
    if not isinstance(objective.get("field"), str) or objective.get("direction") not in ("min", "max"):
        raise KSEOError("objective 必须包含 field 和 direction=min/max")
    optimizer = config["optimizer"]
    if optimizer.get("kind") not in ("grid", "agent", "pipeline"):
        raise KSEOError("optimizer.kind 必须为 grid、agent 或 pipeline")
    space = optimizer.get("space", {})
    if not isinstance(space, dict) or any(not isinstance(v, list) or not v for v in space.values()):
        raise KSEOError("optimizer.space 的每一项必须是非空候选列表")
    if any(key not in config["parameters"] for key in space):
        raise KSEOError("搜索空间中的参数必须有 baseline 默认值")
    for key, values in space.items():
        if config["parameters"][key] not in values:
            raise KSEOError(f"baseline 参数 {key} 不在搜索空间中")
    if optimizer["kind"] == "agent":
        validate_command(optimizer)
    if optimizer["kind"] == "pipeline":
        if "profile" not in names:
            raise KSEOError("pipeline 必须包含 profile 阶段")
        positive_int(optimizer.get("max_cycles", budget_limit(config)), "max_cycles")
        if "max_config_trials" in optimizer:
            positive_int(optimizer["max_config_trials"], "max_config_trials")
        if finite(optimizer.get("final_reserve_seconds", 0), "final_reserve_seconds") < 0:
            raise KSEOError("final_reserve_seconds 不能小于 0")
        if finite(optimizer.get("min_expected_gain", 0), "min_expected_gain") < 0:
            raise KSEOError("min_expected_gain 不能小于 0")
        if "scheduling" in optimizer:
            validate_command(optimizer["scheduling"])
        if 'analyst' in optimizer:
            validate_command(optimizer['analyst'])
        if "kernel" in optimizer:
            kernel = optimizer["kernel"]
            if not isinstance(kernel, dict):
                raise KSEOError("kernel 子流程配置必须是对象")
            for role in ("extractor", "proposer", "validator"):
                if role not in kernel:
                    raise KSEOError(f"Kernel 子流程缺少 {role}")
                validate_command(kernel[role])
            if kernel["proposer"].get("allow_source_changes", optimizer.get("allow_source_changes", False)) is not True:
                raise KSEOError("Kernel proposer 必须开启 allow_source_changes")
            if finite(kernel.get("min_speedup", 1), "min_speedup") < 1:
                raise KSEOError("Kernel min_speedup 必须 >= 1")
    if finite(optimizer.get("min_relative_improvement", 0), "min_relative_improvement") < 0:
        raise KSEOError("min_relative_improvement 不能小于 0")
    budget = config["budget"]
    positive_int(budget.get("max_trials"), "max_trials")
    positive_int(budget.get("max_attempts_per_candidate", 2), "max_attempts_per_candidate")
    for key in ("max_wall_seconds", "max_gpu_hours"):
        if finite(budget.get(key), key) <= 0:
            raise KSEOError(f"{key} 必须大于 0")
    resources = config["resources"]
    positive_int(resources.get("gpu_count", 0), "gpu_count", zero=True)
    keys = resources.get("keys", [])
    if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not k for k in keys):
        raise KSEOError("resources.keys 需要明确的资源锁标识；GPU 推荐使用 host:GPU-UUID")
    if config["mode"] == "measured" and (not config.get("final_validation", True)):
        raise KSEOError("measured 模式必须执行最终复验")
    canonical(config)
    return config


def validate_command(step: dict) -> None:
    if not isinstance(step, dict):
        raise KSEOError("命令配置必须是对象")
    command = step.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
        raise KSEOError("command 必须是非空 argv 数组；不隐式启动 shell")
    if finite(step.get("timeout_seconds", 300), "timeout_seconds") <= 0:
        raise KSEOError("timeout_seconds 必须大于 0")
    if not isinstance(step.get("env", {}), dict):
        raise KSEOError("env 必须是字符串键值对象")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in step.get("env", {}).items()):
        raise KSEOError("env 只接受字符串键值")


def budget_limit(config: dict) -> int:
    return positive_int(config["budget"].get("max_trials"), "max_trials") * 2


def load(path: Path) -> dict:
    return validate(read_json(path))
