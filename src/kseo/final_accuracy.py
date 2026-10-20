"""最终三项精度：固定合同、原始响应映射、全量重算；不执行生成代码。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .util import KSEOError, digest, file_digest, finite, positive_int, read_json
from .generation import validate_generation, output_budget

SUITES = ("rtlbench", "longbench_v2", "livecodebench_v1")


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha(value, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise KSEOError(f"{label} 需要完整 SHA256")


def validate_policy(policy: dict, mode: str) -> None:
    suites = policy.get("suites", [])
    if [suite.get("id") for suite in suites] != list(SUITES):
        raise KSEOError("最终精度必须依次配置 RTLBench、LongBenchv2、LiveCodeBench，不能只配置部分")
    for suite in suites:
        for key in ("dataset_sha256", "evaluator_sha256", "extractor_sha256"):
            _sha(suite.get(key), key)
        minimum = finite(suite.get("min_score"), "min_score")
        if not 0 <= minimum <= 1:
            raise KSEOError("min_score 必须在 [0,1]；旧任务门槛不能自动继承")
        positive_int(suite.get("max_failed_requests"), "max_failed_requests", zero=True)
        manifest = suite.get("manifest", [])
        positive_int(suite.get("expected_samples"), "expected_samples")
        if len(manifest) != suite["expected_samples"]:
            raise KSEOError("最终精度 manifest 必须覆盖完整声明的样本集合")
        ids = [row.get("sample_id") for row in manifest]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise KSEOError("最终精度 manifest 的 ID 缺失或重复")
        for row in manifest:
            _sha(row.get("prompt_sha256"), "manifest.prompt_sha256")
            if suite["id"] == "longbench_v2":
                if row.get("gold") not in ("A", "B", "C", "D"):
                    raise KSEOError("LongBenchv2 必须冻结 A-D gold")
            else:
                _sha(row.get("test_payload_sha256"), "manifest.test_payload_sha256")
        generation = suite.get("generation", {})
        validate_generation(generation)
        if generation.get("output_limit") == "context_remaining":
            for row in manifest:
                output_budget(generation, row.get("prompt_tokens"))
        if mode == "measured":
            from .datasets import load_dataset
            entry = load_dataset(suite.get("dataset_id", ""))
            if (not entry.get("final_accuracy_eligible") or entry.get("benchmark") != suite["id"]
                    or entry.get("selection_authority") != "local_frozen"
                    or entry.get("expected_samples") != suite["expected_samples"]
                    or entry.get("ordered_sample_ids") != ids
                    or digest(entry) != suite["dataset_sha256"]):
                raise KSEOError("最终精度与本地冻结数据版本/数量/顺序不符，不能换官方版本或自行去重")
            if suite["id"] == "longbench_v2" and any(row["gold"] != entry["gold_answers"][row["sample_id"]] for row in manifest):
                raise KSEOError("LongBenchv2 gold 与本地冻结数据不符")
        if suite["id"] == "longbench_v2":
            try:
                pattern = re.compile(suite.get("choice_regex", ""))
            except re.error as exc:
                raise KSEOError("LongBenchv2 choice_regex 无效") from exc
            if pattern.groups != 1 or not suite.get("choice_regex"):
                raise KSEOError("LongBenchv2 必须冻结一个捕获组选项的 choice_regex，只用于 final_content")


def evaluate(payload: dict, directory: Path, policy: dict) -> dict:
    from .validation import artifact, jsonl

    outputs = payload.get("benchmarks", [])
    if [output.get("id") for output in outputs] != list(SUITES):
        raise KSEOError("最终精度结果缺失、重复或顺序不符")
    summaries = {}
    for contract, output in zip(policy["suites"], outputs):
        for key in ("dataset_sha256", "evaluator_sha256", "extractor_sha256"):
            if output.get(key) != contract[key]:
                raise KSEOError(f"{contract['id']} 的 {key} 与冻结合同不符")
        generation = contract["generation"]
        if output.get("generation_policy_sha256") != digest(generation):
            raise KSEOError("最终精度生成策略身份不符")
        rows = jsonl(artifact(output, "samples_file", directory))
        expected = contract["manifest"]
        if [row.get("sample_id") for row in rows] != [row["sample_id"] for row in expected]:
            raise KSEOError("最终精度样本数、ID、顺序不符，不能用分片/重复 ID 冒充全量")
        attempts = jsonl(artifact(output, "attempts_file", directory))
        by_sample = {row["sample_id"]: [] for row in expected}
        seen = set()
        for attempt in attempts:
            sid, aid = attempt.get("sample_id"), attempt.get("attempt_id")
            if sid not in by_sample or not isinstance(aid, str) or not aid or aid in seen:
                raise KSEOError("原始 attempt 的 ID 缺失、重复或不在完整 manifest 内")
            if not isinstance(attempt.get("final_content"), str):
                raise KSEOError("原始 attempt 必须保存 final_content，不能仅保存提取后的答案")
            seen.add(aid)
            by_sample[sid].append(attempt)
        correct = failed = 0
        for row, reference in zip(rows, expected):
            trace = by_sample[row["sample_id"]]
            max_attempts = 1 if generation["retry_policy"] == "none" else 2
            if not 1 <= len(trace) <= max_attempts:
                raise KSEOError("原始 attempt 缺失或超过预先冻结的重试次数")
            for index, attempt in enumerate(trace):
                if attempt.get("thinking") != generation["thinking"] or attempt.get("prompt_sha256") != reference["prompt_sha256"]:
                    raise KSEOError("原始请求 thinking 或 prompt 与冻结合同不符")
                if generation.get("output_limit") == "context_remaining":
                    if attempt.get("prompt_tokens") != reference.get("prompt_tokens"):
                        raise KSEOError("实际 prompt token 数与预先冻结的 native tokenize 结果不符")
                    budget = output_budget(generation, reference["prompt_tokens"])
                else:
                    budget = generation["first_max_output_tokens"]
                if index:
                    previous = trace[index - 1]
                    if previous["final_content"].strip() or previous.get("finish_reason") != "length":
                        raise KSEOError("不得因答错、低分或非空回答重采样")
                    positive_int(previous.get("prompt_tokens"), "raw.prompt_tokens")
                    budget = generation["context_limit"] - previous["prompt_tokens"]
                    positive_int(budget, "第二次输出预算")
                if attempt.get("max_output_tokens") != budget:
                    raise KSEOError("原始请求输出预算与冻结策略不符")
            last = trace[-1]
            if row.get("attempt_id") != last["attempt_id"] or row.get("final_content_sha256") != hash_text(last["final_content"]):
                raise KSEOError("计分正文没有精确绑定所选原始 attempt")
            status = row.get("status")
            if status not in ("completed", "failed", "unparseable"):
                raise KSEOError("最终精度样本终态缺失")
            nonempty = bool(last["final_content"].strip())
            failed += status != "completed" or not nonempty
            passed = False
            if contract["id"] == "longbench_v2":
                choice = row.get("predicted_choice")
                if choice not in (None, "A", "B", "C", "D"):
                    raise KSEOError("LongBenchv2 无有效选项时应记录 null，并留在分母")
                matches = list(re.finditer(contract["choice_regex"], last["final_content"]))
                actual_choice = matches[-1].group(1) if matches else None
                if actual_choice != choice:
                    raise KSEOError("LongBenchv2 选项必须按冻结正则从 final_content 独立重算")
                passed = nonempty and status == "completed" and choice == reference["gold"]
            else:
                if row.get("test_payload_sha256") != reference["test_payload_sha256"]:
                    raise KSEOError("原测试/expected output 身份改变，不能合并为原基准得分")
                tests = row.get("test_results", [])
                if not isinstance(tests, list) or any(type(v) is not bool and not (type(v) is int and v in (-1, -2)) for v in tests):
                    raise KSEOError("测试结果必须为 bool 或 -1/-2 错误哨兵；不得按 Python 真值计分")
                passed = nonempty and status == "completed" and bool(tests) and all(value is True for value in tests)
                if contract["id"] == "rtlbench":
                    for key in ("compile_exit_code", "simulation_exit_code"):
                        if type(row.get(key)) is not int:
                            raise KSEOError("RTLBench 必须保存编译和仿真退出码")
                    for key in ("success_marker", "failure_marker"):
                        if type(row.get(key)) is not bool:
                            raise KSEOError("RTLBench 必须显式报告成功/失败标记，不能 fail-open")
                    passed = passed and row["compile_exit_code"] == row["simulation_exit_code"] == 0 and row["success_marker"] and not row["failure_marker"]
            correct += bool(passed)
        review = read_json(artifact(output, "validity_review_file", directory))
        review_valid = (review.get("status") == "PASS" and review.get("manifest_sha256") == digest(expected)
                        and review.get("unresolved_sample_ids") == [])
        score = correct / len(rows)
        summaries[contract["id"]] = {"samples": len(rows), "correct": correct, "score": score,
                                      "failed_requests": failed, "validity_review_passed": review_valid,
                                      "passed": score >= contract["min_score"] and failed <= contract["max_failed_requests"] and review_valid,
                                      "samples_sha256": file_digest(artifact(output, "samples_file", directory))}
    return {"benchmarks": summaries, "passed": all(suite["passed"] for suite in summaries.values()),
            "note": "从原记录重算得分和证据绑定；测试执行与语义审阅仍由独立可信 evaluator/adapter 提供。"}
