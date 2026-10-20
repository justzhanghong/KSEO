"""独立验收器：核对身份，从逐请求记录重算性能，再执行硬门禁。"""

from __future__ import annotations

import math
import operator
from pathlib import Path

from .util import KSEOError, confined, file_digest, finite, get_path, positive_int, read_json

COMPARE = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne}


def jsonl(path: Path) -> list[dict]:
    import json

    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise KSEOError(f"逐条记录无法读取: {path}: {exc}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise KSEOError("逐条记录不能为空，且每条记录必须是 JSON 对象")
    return rows


def artifact(payload: dict, key: str, directory: Path) -> Path:
    if not isinstance(payload.get(key), str):
        raise KSEOError(f"缺少原始产物: {key}")
    path = confined(directory, payload[key])
    expected = payload.get(key + "_sha256")
    if not path.is_file() or expected != file_digest(path):
        raise KSEOError(f"原始产物缺失或 SHA256 不匹配: {key}")
    return path


def stats(values: list[float]) -> dict:
    if not values:
        raise KSEOError("无法从空样本计算性能")
    ordered = sorted(values)
    return {"mean": sum(values) / len(values), "min": ordered[0], "max": ordered[-1],
            "p95": ordered[max(0, math.ceil(len(values) * 0.95) - 1)]}


def benchmark(payload: dict, directory: Path, policy: dict) -> dict:
    rows = jsonl(artifact(payload, "requests_file", directory))
    expected = {case["id"]: case for case in policy["cases"]}
    groups: dict[str, list[dict]] = {name: [] for name in expected}
    ids = set()
    for row in rows:
        request_id = row.get("request_id")
        if not isinstance(request_id, str) or not request_id or request_id in ids:
            raise KSEOError("request_id 缺失或重复")
        ids.add(request_id)
        case_id = row.get("case_id")
        if case_id not in groups:
            raise KSEOError(f"出现合同外 case: {case_id}")
        if row.get("status") not in ("completed", "failed"):
            raise KSEOError("请求 status 必须是 completed 或 failed")
        positive_int(row.get("input_tokens"), "input_tokens")
        if row["input_tokens"] != expected[case_id]["input_tokens"]:
            raise KSEOError(f"{case_id} 输入长度与合同不符")
        if row["status"] == "completed":
            positive_int(row.get("output_tokens"), "output_tokens")
            if row["output_tokens"] != expected[case_id]["output_tokens"]:
                raise KSEOError(f"{case_id} 输出长度与合同不符")
            ttft = finite(row.get("ttft_ms"), "ttft_ms")
            total = finite(row.get("total_ms"), "total_ms")
            if ttft < 0 or total < ttft:
                raise KSEOError("请求计时不合法：要求 total_ms >= ttft_ms >= 0")
            if row["output_tokens"] < 2:
                raise KSEOError("TPOT 测量至少需要两个输出 token")
            positive_int(row.get("cache_read_tokens"), "cache_read_tokens", zero=True)
            case = expected[case_id]
            for key in ("output_token_basis", "ttft_basis"):
                if key in case and row.get(key) != case[key]:
                    raise KSEOError(f"{case_id} 的 {key} 与计时/token 合同不符")
            zero_read = case.get("cache_policy") == "zero_read" if "cache_policy" in case else policy.get("zero_cache_reads", True)
            if zero_read and row["cache_read_tokens"] != 0:
                raise KSEOError("正式速度合同要求 cache read 为零")
        groups[case_id].append(row)
    cases = {}
    for name, records in groups.items():
        if len(records) != expected[name]["requests"]:
            raise KSEOError(f"{name} 请求数量不符：实际 {len(records)}，要求 {expected[name]['requests']}")
        good = [row for row in records if row["status"] == "completed"]
        failed = len(records) - len(good)
        if not good:
            cases[name] = {"requests": len(records), "failed_requests": failed}
            continue
        cases[name] = {"requests": len(records), "failed_requests": failed,
                       "ttft_ms": stats([row["ttft_ms"] for row in good]),
                       "tpot_ms": stats([(row["total_ms"] - row["ttft_ms"]) / (row["output_tokens"] - 1) for row in good])}
    failed = sum(case["failed_requests"] for case in cases.values())
    result = {"cases": cases, "failed_requests": failed, "requests": len(rows), "raw_sha256": file_digest(directory / payload["requests_file"])}
    if policy.get("selection_metrics"):
        values = []
        for metric in policy["selection_metrics"]:
            target = finite(metric["target"], "selection.target")
            if target <= 0 or not metric["field"].startswith("benchmark."):
                raise KSEOError("搜索评分仅使用正值性能目标")
            values.append(finite(get_path({"benchmark": result}, metric["field"]), metric["field"]) / target)
        result["mean_goal_ratio"] = math.fsum(values) / len(values)
    return result


def quality(payload: dict, directory: Path, policy: dict) -> dict:
    rows = jsonl(artifact(payload, "samples_file", directory))
    ids = [row.get("sample_id") for row in rows]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise KSEOError("quality sample_id 缺失或重复")
    if policy.get("quality_samples") is not None and len(rows) != policy["quality_samples"]:
        raise KSEOError("quality 样本数与合同不符")
    generation = policy.get('quality_generation')
    if generation:
        from .generation import output_budget
        from .util import digest
        manifest = policy['quality_manifest']
        if ids != [r['sample_id'] for r in manifest]:raise KSEOError('GSM8K 样本集合及顺序必须与冻结 manifest 一致')
        for row, expected in zip(rows,manifest):
            for key in ('prompt_sha256','prompt_tokens'):
                if row.get(key) != expected[key]:raise KSEOError('GSM8K native prompt 与冻结身份不符')
            if row.get('max_output_tokens') != output_budget(generation,expected['prompt_tokens']):
                raise KSEOError('GSM8K 不得另加输出 cap 或采用服务的默认短上限')
            if row.get('thinking') != generation['thinking'] or row.get('generation_policy_sha256') != digest(generation):
                raise KSEOError('GSM8K 生成策略与合同不符')
    for row in rows:
        if any(type(row.get(key)) is not bool for key in ("correct", "failed", "unparseable")):
            raise KSEOError("quality 记录要求 correct/failed/unparseable 为 boolean")
        if row["correct"] and (row["failed"] or row["unparseable"]):
            raise KSEOError("失败或不可解析样本不能记为正确")
    return {"samples": len(rows), "accuracy": sum(row["correct"] for row in rows) / len(rows),
            "failed_requests": sum(row["failed"] for row in rows),
            "unparseable": sum(row["unparseable"] for row in rows)}


def ingest_stage(path: Path, identity: dict, mode: str, stage: str, policy: dict) -> dict:
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise KSEOError("adapter 输出要求 schema_version=1")
    if payload.get("identity") != identity:
        raise KSEOError("adapter 输出身份与本次实验不符")
    if payload.get("kind") != mode:
        raise KSEOError("synthetic、replay 与 measured 结果不能混用")
    result = {"checks": payload.get("checks", {}), "runtime": payload.get("runtime", {})}
    if not isinstance(result["checks"], dict) or not isinstance(result["runtime"], dict):
        raise KSEOError("checks 和 runtime 必须是对象")
    if stage == "benchmark":
        result.update(benchmark(payload, path.parent, policy))
    if stage == "profile" and "profile" in payload:
        from .profiling import normalize
        result["profile"] = normalize(payload["profile"])
    if stage == "quality" and ("samples_file" in payload or policy.get("quality_samples") is not None):
        result.update(quality(payload, path.parent, policy))
    if stage == "multi_turn":
        from .multi_turn import evaluate
        result.update(evaluate(payload, path.parent, policy["multi_turn"], identity))
    if stage == "final_accuracy":
        from .final_accuracy import evaluate
        result.update(evaluate(payload, path.parent, policy["final_accuracy"]))
    return result


def gates(results: dict, policy: dict, stage: str | None = None, *, phase: str | None = None) -> list[dict]:
    decisions = []
    for gate in policy["gates"]:
        if phase in ("baseline", "candidate") and gate["stage"] in ("final_accuracy", "multi_turn"):
            continue
        if phase in ("baseline", "candidate") and policy.get("milestones") and gate["stage"] == "benchmark" and not gate.get("always_required", False):
            continue
        if stage is not None and gate["stage"] != stage:
            continue
        try:
            actual = get_path(results, gate["field"])
            if gate["op"] in ("<", "<=", ">", ">="):
                actual = finite(actual, gate["field"])
            elif isinstance(gate["value"], bool) and type(actual) is not bool:
                raise KSEOError("boolean 门禁要求 boolean 结果")
            passed = COMPARE[gate["op"]](actual, gate["value"])
            decision = {"name": gate["name"], "field": gate["field"], "actual": actual,
                        "op": gate["op"], "expected": gate["value"], "pass": bool(passed)}
        except (KSEOError, TypeError, ValueError) as exc:
            decision = {"name": gate["name"], "field": gate["field"], "pass": False, "error": str(exc)}
        decisions.append(decision)
    return decisions


def score(results: dict, policy: dict) -> float:
    return finite(get_path(results, policy["objective"]["field"]), "objective")
