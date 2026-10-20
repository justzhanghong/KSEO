"""System 层策略路由：配置优先，再按当前 Profile 选择子流程。"""

from __future__ import annotations

from pathlib import Path
import sys

from .. import profiling, source, roles
from ..executor import StepFailure, execute
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
            priority = None
            if 'analyst' in self.settings:
                request = roles.diagnosis_request(profile, selected['identity'], selected['parameters'], runner.config['validation'], seen,
                    evidence={'context': runner.config['context'], 'resources': runner.config['resources'],
                              'budget': runner.config['budget'], 'remaining_seconds': runner.remaining(),
                              'source_dir': str(base), 'trial_dir': str(runner.root/selected['directory']), 'run_dir': str(runner.root),
                              'runtime': {name: result.get('runtime',{}) for name,result in selected.get('results',{}).items()},
                              'history': [{'id': t['id'], 'status': t['status'], 'directory': t['directory'], 'error': t.get('error'), 'gates': t.get('gates',[])}
                                          for t in runner.state['trials']]})
                cached = self.state.get('diagnosis', {})
                if cached.get('request_sha256') == digest(request):
                    diagnosis_path = confined(runner.root, cached['output'])
                    if file_digest(diagnosis_path) != cached['output_sha256']:
                        raise KSEOError('瓶颈诊断产物已变化')
                    rows = roles.validate_diagnosis(read_json(diagnosis_path), request)
                else:
                    analysis, analysis_dir = self.begin('analysis', parent=selected['id'])
                    request_path, diagnosis_path = analysis_dir/'request.json', analysis_dir/'diagnosis.json'
                    write_json(request_path, request)
                    request_sha = file_digest(request_path)
                    variables = {'run_dir': str(runner.root), 'source_dir': str(base), 'analysis_dir': str(analysis_dir),
                                 'config_dir': runner.state['config_dir'], 'package_dir': str(Path(__file__).resolve().parents[1]), 'python': sys.executable}
                    try:
                        runner.check_tools()
                        execute(self.settings['analyst'], analysis_dir/'process', variables,
                                {'KSEO_ANALYST_REQUEST': str(request_path), 'KSEO_ANALYST_OUTPUT': str(diagnosis_path), 'KSEO_MODE': runner.config['mode']}, remaining=runner.remaining())
                        source.assert_unchanged(base, revision)
                        runner.check_tools()
                        if file_digest(request_path) != request_sha:
                            raise KSEOError('瓶颈分析员改写了输入请求')
                        rows = roles.validate_diagnosis(read_json(diagnosis_path), request)
                    except (KSEOError, StepFailure) as exc:
                        self.finish_local(analysis, 'ANALYSIS_FAILED', str(exc))
                        self.state['stop_reason'] = 'ANALYSIS_FAILED'
                        return None
                    self.state['diagnosis'] = {'request_sha256': digest(request), 'output': str(diagnosis_path.relative_to(runner.root)),
                                               'output_sha256': file_digest(diagnosis_path)}
                    self.finish_local(analysis, 'DIAGNOSED')
                priority = [row['hotspot_id'] for row in rows]
            decision = profiling.route(profile, {lane for lane in ("scheduling", "kernel") if lane in self.settings},
                                       seen, context_id, min_gain=self.settings.get("min_expected_gain", 0), priority=priority)
            if decision is None:
                self.state["stop_reason"] = "NO_ACTIONABLE_HOTSPOT"
                runner.save()
                return None
            lane, hotspot = decision["lane"], decision["hotspot"]
            if priority is not None:
                hotspot = {**hotspot, 'analyst_diagnosis': next(row for row in rows if row['hotspot_id'] == hotspot['id'])}
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
                                                 "objective": trial.get("score"), "gates": trial["gates"], "acceptance_scope": trial.get("acceptance_scope"),
                                                 "milestones": trial.get("milestones", [])},
                                "provenance": {"trial": trial["directory"], "contract_sha256": runner.state["contract_sha256"]}}
        memory["cards"] = [row for row in memory["cards"] if row["id"] != trial["id"]] + [card]
        write_json(memory_path, memory)
        if status == "ACCEPTED":
            runner.event("profile_refreshed", trial=trial["id"], source_revision=trial["identity"]["source_revision"])
        runner.save()
