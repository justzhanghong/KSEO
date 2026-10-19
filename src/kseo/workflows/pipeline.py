"""System 层策略路由：配置优先，再按当前 Profile 选择子流程。"""

from __future__ import annotations

from pathlib import Path

from .. import profiling, source
from ..executor import StepFailure
from ..util import KSEOError, confined, digest, file_digest, read_json, write_json
from .configuration import next_configuration
from .kernel import KernelRejected, KernelWorkflow
from .scheduling import propose as scheduling_proposal


class Pipeline:
    def __init__(self, runner):
        self.runner = runner
        self.settings = runner.config["optimizer"]
        self.state = runner.state.setdefault("pipeline", {"attempts": [], "config_done": False})

    def begin(self, lane: str, *, parent: str, key: str | None = None, hotspot: dict | None = None) -> tuple[dict, Path]:
        runner = self.runner
        number = len(self.state["attempts"])
        directory = runner.root / "workflows" / f"w{number:04d}"
        while directory.exists():
            number += 1
            directory = runner.root / "workflows" / f"w{number:04d}"
        directory.mkdir(parents=True)
        attempt = {"id": directory.name, "directory": str(directory.relative_to(runner.root)),
                   "lane": lane, "key": key, "hotspot": hotspot, "parent_trial": parent, "status": "RUNNING"}
        self.state["attempts"].append(attempt)
        runner.state["active_workflow"] = attempt["directory"]
        runner.lease["clean"] = False
        runner.event("workflow_start", workflow=attempt["id"], lane=lane)
        runner.save()
        return attempt, directory

    def finish_local(self, attempt: dict, status: str, error: str | None = None) -> None:
        runner = self.runner
        attempt["status"] = status
        if error:
            attempt["error"] = error
            phases_path = runner.root / attempt["directory"] / "kernel_phases.json"
            if phases_path.exists():
                phases = read_json(phases_path)
                write_json(phases_path, {name: "FAILED" if outcome == "RUNNING" else outcome for name, outcome in phases.items()})
        runner.state["active_workflow"] = None
        runner.lease["clean"] = True
        write_json(runner.root / attempt["directory"] / "workflow.json", attempt)
        runner.save()

    def next(self, selected: dict, base: Path) -> dict | None:
        runner = self.runner
        for attempt in self.state["attempts"]:
            if attempt["status"] == "PROPOSED" and not attempt.get("trial") and attempt.get("proposal"):
                proposal = dict(attempt["proposal"])
                patch = proposal.get("patch")
                if patch:
                    proposal["patch"] = confined(runner.root, patch)
                    if file_digest(proposal["patch"]) != proposal["patch_sha256"]:
                        raise KSEOError("待集成提案的 patch 已发生变化")
                return proposal
        limit = self.settings.get("max_cycles", runner.config["budget"]["max_trials"] * 2)
        while len(self.state["attempts"]) < limit:
            if runner.remaining() <= self.settings.get("final_reserve_seconds", 0):
                self.state["stop_reason"] = "FINAL_RESERVE_REACHED"
                return None
            if not self.state["config_done"]:
                config_count = sum(item["lane"] == "configuration" for item in self.state["attempts"])
                config_limit = self.settings.get("max_config_trials", max(1, min(4, runner.config["budget"]["max_trials"] // 2)))
                proposal = next_configuration(runner.config, runner.state) if config_count < config_limit else None
                if proposal is not None:
                    attempt, _ = self.begin("configuration", parent=selected["id"])
                    proposal.update({"workflow_attempt": attempt["id"], "workflow_lane": "configuration"})
                    self.pending(attempt, proposal)
                    return proposal
                self.state["config_done"] = True
                runner.event("configuration_sweep_complete")
                runner.save()
            profile = selected.get("results", {}).get("profile", {}).get("profile")
            if profile is None:
                raise KSEOError("pipeline 需要标准化 Profile；不能从检查标记猜测热点")
            revision = source.git(base, "rev-parse", "HEAD")
            context_id = revision + ":" + digest(selected["parameters"])
            self.state["profile_source"] = {"trial": selected["id"], "source_revision": revision,
                                            "parameters_sha256": digest(selected["parameters"]), "profile_sha256": digest(profile)}
            seen = {item["key"] for item in self.state["attempts"]
                    if item["key"] and item["status"] != "INTERRUPTED"}
            decision = profiling.route(profile, {lane for lane in ("scheduling", "kernel") if lane in self.settings},
                                       seen, context_id, min_gain=self.settings.get("min_expected_gain", 0))
            if decision is None:
                self.state["stop_reason"] = "NO_ACTIONABLE_HOTSPOT"
                runner.save()
                return None
            lane, hotspot = decision["lane"], decision["hotspot"]
            attempt, directory = self.begin(lane, parent=selected["id"], key=decision["key"], hotspot=hotspot)
            runner.event("strategy_route", workflow=attempt["id"], lane=lane, hotspot=hotspot["id"],
                         expected_saved_fraction=hotspot["expected_saved_fraction"])
            try:
                if lane == "kernel":
                    proposal = KernelWorkflow(runner).propose(base, hotspot, directory)
                else:
                    proposal = scheduling_proposal(runner, base, hotspot, directory)
            except (KernelRejected, StepFailure, KSEOError) as exc:
                source.assert_unchanged(base, revision)
                status = "KERNEL_REJECTED" if isinstance(exc, KernelRejected) else "WORKFLOW_FAILED"
                self.finish_local(attempt, status, str(exc))
                runner.event("workflow_rejected", workflow=attempt["id"], lane=lane, reason=str(exc))
                continue
            if proposal is None:
                self.finish_local(attempt, "NO_PROPOSAL")
                continue
            proposal.update({"workflow_attempt": attempt["id"], "workflow_lane": lane, "hotspot": hotspot})
            self.pending(attempt, proposal)
            return proposal
        self.state["stop_reason"] = "WORKFLOW_CYCLE_LIMIT"
        return None

    def pending(self, attempt: dict, proposal: dict) -> None:
        stored = dict(proposal)
        if stored.get("patch"):
            stored["patch_sha256"] = file_digest(stored["patch"])
            stored["patch"] = str(stored["patch"].relative_to(self.runner.root))
        attempt["proposal"] = stored
        self.finish_local(attempt, "PROPOSED")

    def integrated(self, trial: dict, proposal: dict) -> None:
        runner = self.runner
        attempt = next(item for item in self.state["attempts"] if item["id"] == proposal["workflow_attempt"])
        status = trial["status"]
        if proposal.get("kernel_evidence") and status not in ("ACCEPTED", "VALID_NO_GAIN"):
            status = "LOCAL_PASS_E2E_REJECTED"
        attempt.update({"status": status, "trial": trial["id"], "kernel_evidence": proposal.get("kernel_evidence")})
        write_json(runner.root / attempt["directory"] / "workflow.json", attempt)
        memory_path = runner.root / "learned-experience.json"
        memory = read_json(memory_path) if memory_path.exists() else {"schema_version": 1, "cards": []}
        card = {"id": trial["id"], "title": trial["hypothesis"], "status": status,
                                "applies_to": {key: value for key, value in runner.config["context"].items() if key != "capabilities"},
                                "observations": {"mode": runner.config["mode"], "lane": attempt["lane"],
                                                 "objective": trial.get("score"), "gates": trial["gates"]},
                                "provenance": {"trial": trial["directory"], "contract_sha256": runner.state["contract_sha256"]}}
        memory["cards"] = [row for row in memory["cards"] if row["id"] != trial["id"]] + [card]
        write_json(memory_path, memory)
        if status == "ACCEPTED":
            runner.event("profile_refreshed", trial=trial["id"], source_revision=trial["identity"]["source_revision"])
        runner.save()
