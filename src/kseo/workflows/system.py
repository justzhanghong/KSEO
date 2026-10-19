"""System 大流程：基线、策略选择、子流程集成、E2E 门禁与最终交付。"""

import sys
from pathlib import Path

from .. import optimizer, source
from ..util import canonical, file_digest, write_json
from .pipeline import Pipeline


class SystemWorkflow:
    def __init__(self, runner):
        self.runner = runner

    def run(self) -> None:
        runner = self.runner
        pipeline = Pipeline(runner) if runner.config["optimizer"]["kind"] == "pipeline" else None
        if not runner.recover():
            return
        runner.check_tools()
        for recorded in runner.state["trials"]:
            if recorded["status"] == "VALID" and recorded["phase"] != "final":
                runner.consider(recorded)
            if pipeline and recorded.get("workflow_attempt"):
                attempt = next(a for a in pipeline.state["attempts"] if a["id"] == recorded["workflow_attempt"])
                if not attempt.get("trial"):
                    pipeline.integrated(recorded, recorded)
        base = runner.root / "source-base"
        revision = source.freeze(runner.config, base, Path(runner.state["config_dir"]))
        runner.state["baseline_source_revision"] = revision
        runner.save()
        retryable = {"INTERRUPTED", "DEPLOYMENT_FAILED", "EXECUTION_FAILED"}
        max_attempts = runner.config["budget"].get("max_attempts_per_candidate", 2)
        baselines = [trial for trial in runner.state["trials"] if trial["phase"] == "baseline"]
        if baselines and baselines[-1]["status"] in retryable and len(baselines) < max_attempts:
            baselines = []
        if not baselines:
            baseline = runner.trial(runner.config["parameters"], "baseline", base, None, "冻结基线与完整验证")
            runner.consider(baseline)
        else:
            baseline = baselines[-1]
        if runner.state["status"] == "CLEANUP_FAILED":
            return
        if baseline["status"] not in ("ACCEPTED", "VALID", "VALID_NO_GAIN", "BASELINE_TARGET_NOT_MET"):
            runner.state["status"] = "BASELINE_INVALID"
            return
        reason = "SEARCH_EXHAUSTED"
        while len([trial for trial in runner.state["trials"] if trial["phase"] != "final"]) < runner.config["budget"]["max_trials"]:
            reserve = runner.config["optimizer"].get("final_reserve_seconds", 0) if pipeline else 0
            if runner.remaining() <= reserve:
                reason = "FINAL_RESERVE_REACHED" if reserve else "BUDGET_EXHAUSTED"
                break
            best = runner.state.get("best")
            selected_base = runner.root / best["directory"] / "source" if best else base
            if pipeline:
                selected = next(row for row in runner.state["trials"] if row["id"] == best["id"]) if best else baseline
                proposal = pipeline.next(selected, selected_base)
            elif runner.config["optimizer"]["kind"] == "grid":
                groups = {}
                for previous in runner.state["trials"]:
                    if previous["phase"] != "final":
                        groups.setdefault(canonical(previous["parameters"]), []).append(previous)
                tried = {key for key, attempts in groups.items()
                         if len(attempts) >= max_attempts or any(item["status"] not in retryable for item in attempts)}
                proposal = optimizer.grid(runner.config, tried)
            else:
                number = len(runner.state["trials"])
                proposal_dir = runner.root / "proposals" / f"p{number:04d}"
                variables = {"run_dir": str(runner.root), "source_dir": str(selected_base),
                             "package_dir": str(Path(__file__).resolve().parents[1]), "config_dir": runner.state["config_dir"],
                             "python": sys.executable}
                before = source.git(selected_base, "rev-parse", "HEAD")
                proposal = optimizer.agent(runner.config, runner.state, proposal_dir, variables, {}, runner.remaining())
                source.assert_unchanged(selected_base, before)
            if proposal is None:
                if pipeline:
                    reason = pipeline.state.get("stop_reason", "SEARCH_EXHAUSTED")
                break
            patch_hash = file_digest(proposal["patch"]) if proposal["patch"] else ""
            fingerprint = optimizer.signature(proposal["parameters"], source.git(selected_base, "rev-parse", "HEAD"), patch_hash)
            if any(trial.get("proposal_sha256") == fingerprint and trial["status"] not in retryable for trial in runner.state["trials"]):
                reason = "DUPLICATE_PROPOSAL"
                break
            trial = runner.trial(proposal["parameters"], "candidate", selected_base, proposal["patch"], proposal["hypothesis"],
                                 kernel_evidence=proposal.get("kernel_evidence"), workflow=proposal if pipeline else None)
            trial["proposal_sha256"] = fingerprint
            if pipeline:
                trial["workflow_lane"] = proposal["workflow_lane"]
                trial["kernel_evidence"] = proposal.get("kernel_evidence")
            runner.consider(trial)
            if pipeline:
                pipeline.integrated(trial, proposal)
                write_json(runner.root / trial["directory"] / "trial.json", trial)
            runner.save()
            if runner.state["status"] == "CLEANUP_FAILED":
                return
        else:
            reason = "TRIAL_LIMIT_REACHED"
        runner.state["stop_reason"] = reason
        best = runner.state.get("best")
        if not best:
            runner.state["status"] = "NO_VALID_CANDIDATE"
        elif runner.remaining() <= 0:
            runner.state["status"] = "BUDGET_EXHAUSTED_UNVALIDATED"
        elif runner.config.get("final_validation", True):
            final = runner.trial(best["parameters"], "final", runner.root / best["directory"] / "source", None, "独立重新运行最佳候选的完整合同")
            if runner.state["status"] == "CLEANUP_FAILED":
                return
            runner.state["final_trial"] = final["id"]
            runner.state["status"] = "COMPLETED" if final["status"] == "VALID" else "FINAL_VALIDATION_FAILED"
        else:
            runner.state["status"] = "CANDIDATE_ONLY"
