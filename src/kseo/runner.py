"""可恢复的实验控制器。候选源码和任务合同分别冻结。"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

from . import __version__, optimizer, source, validation
from .config import load, validate
from .executor import StepFailure, execute, expand, recover_processes
from .locking import file_lock, resource_locks
from .util import KSEOError, canonical, digest, file_digest, now, read_json, write_json


class Runner:
    def __init__(self, directory: Path):
        self.root = directory.resolve()
        self.state: dict = {}
        self.config: dict = {}
        self.lease = None

    def event(self, event: str, **fields) -> None:
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": now(), "event": event, **fields}, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def save(self) -> None:
        timestamp = time.time()
        if self.state.get("charged_at") is not None:
            self.state["elapsed_seconds"] += max(0, timestamp - self.state["charged_at"])
            self.state["charged_at"] = timestamp
        self.state["updated_at"] = now()
        write_json(self.root / "state.json", self.state)

    def remaining(self) -> float:
        self.save()
        spent = self.state["elapsed_seconds"]
        budget = self.config["budget"]
        remaining = budget["max_wall_seconds"] - spent
        gpus = self.config["resources"].get("gpu_count", 0)
        if gpus:
            remaining = min(remaining, budget["max_gpu_hours"] * 3600 / gpus - spent)
        return remaining

    def variables(self, trial: dict, stage: str) -> tuple[dict, dict]:
        trial_dir = self.root / trial["directory"]
        directory = trial_dir / "steps" / stage
        directory.mkdir(parents=True, exist_ok=True)
        variables = {"run_dir": str(self.root), "trial_dir": str(trial_dir), "stage_dir": str(directory),
                     "source_dir": str(trial_dir / "source"), "config_dir": self.state["config_dir"],
                     "package_dir": str(Path(__file__).parent), "python": sys.executable}
        env = {"KSEO_RUN_DIR": str(self.root), "KSEO_TRIAL_DIR": str(trial_dir),
               "KSEO_SOURCE_DIR": variables["source_dir"], "KSEO_STAGE": stage,
               "KSEO_TRIAL_ID": trial["id"], "KSEO_IDENTITY_PATH": str(trial_dir / "identity.json"),
               "KSEO_PARAMETERS_PATH": str(trial_dir / "parameters.json"),
               "KSEO_RESULT_PATH": str(directory / "result.json"), "KSEO_STAGE_DIR": str(directory),
               "KSEO_MODE": self.config["mode"]}
        if self.state.get("active_workflow"):
            env["KSEO_WORKFLOW_DIR"] = str(self.root / self.state["active_workflow"])
        return variables, env

    def cleanup(self, trial: dict, *, recovery: bool = False) -> bool:
        if "identity" not in trial:
            trial["cleanup"] = "NOT_STARTED"
            self.lease["clean"] = True
            return True
        command = self.config.get("cleanup")
        if not command:
            trial["cleanup"] = "NOT_CONFIGURED"
            self.lease["clean"] = True
            return True
        variables, env = self.variables(trial, "cleanup")
        try:
            # 清理不受优化预算阻断，避免预算耗尽后遗留 GPU 服务。
            execute(command, Path(variables["stage_dir"]), variables, env,
                    remaining=float(command.get("timeout_seconds", 120)))
            trial["cleanup"] = "PASS"
            self.lease["clean"] = True
            self.event("cleanup_pass", trial=trial["id"], recovery=recovery)
            self.save()
            return True
        except (KSEOError, KeyboardInterrupt) as exc:
            trial["cleanup"] = "FAILED"
            trial["cleanup_error"] = str(exc)
            self.lease["clean"] = False
            self.state["status"] = "CLEANUP_FAILED"
            self.event("cleanup_failed", trial=trial["id"])
            self.save()
            return False

    def trial(self, parameters: dict, phase: str, base: Path, patch: Path | None, hypothesis: str,
              *, kernel_evidence: dict | None = None, workflow: dict | None = None) -> dict:
        number = len(self.state["trials"])
        identifier = f"t{number:04d}"
        relative = f"trials/{identifier}"
        directory = self.root / relative
        while directory.exists():
            number += 1
            identifier = f"t{number:04d}"
            relative = f"trials/{identifier}"
            directory = self.root / relative
        directory.mkdir(parents=True)
        record = {"id": identifier, "directory": relative, "phase": phase, "status": "PREPARING",
                  "parameters": parameters, "hypothesis": hypothesis, "results": {}, "gates": [],
                  "started_at": now(), "cleanup": "PENDING"}
        if kernel_evidence:
            record["kernel_evidence"] = kernel_evidence
        if workflow:
            record["workflow_attempt"] = workflow["workflow_attempt"]
            record["workflow_lane"] = workflow["workflow_lane"]
        self.state["trials"].append(record)
        self.state["active_trial"] = identifier
        self.lease["clean"] = False
        self.save()
        self.event("trial_start", trial=identifier, phase=phase)
        try:
            revision = source.fork(base, directory / "source", patch)
            if kernel_evidence:
                if patch is None or file_digest(patch) != kernel_evidence["patch_sha256"]:
                    raise KSEOError("System 集成的 Kernel patch 与局部证据不一致")
                if source.git(directory / "source", "rev-parse", "HEAD^{tree}") != kernel_evidence["candidate_tree"]:
                    raise KSEOError("System 集成的源码 tree 与 Kernel 局部验证不一致")
            if patch:
                (directory / "proposal.diff").write_bytes(patch.read_bytes())
            write_json(directory / "parameters.json", parameters)
            identity = {"run_id": self.state["run_id"], "trial_id": identifier,
                        "phase": phase,
                        "contract_sha256": self.state["contract_sha256"], "parameters_sha256": digest(parameters),
                        "source_revision": revision, "image": self.config["inputs"]["image"],
                        "model": self.config["inputs"]["model"],
                        "model_revision": self.config["inputs"].get("model_revision", "synthetic"),
                        "workload_sha256": self.config["inputs"].get("workload_sha256", digest(self.config["inputs"]["workload"]))}
            record["identity"] = identity
            write_json(directory / "identity.json", identity)
            record["status"] = "RUNNING"
            self.save()
            for step in self.config["steps"]:
                stage = step["name"]
                if stage == "final_accuracy" and phase != "final":
                    continue
                record["stage"] = stage
                self.save()
                self.event("stage_start", trial=identifier, stage=stage)
                variables, env = self.variables(record, stage)
                self.check_tools()
                execute(step, Path(variables["stage_dir"]), variables, env, remaining=self.remaining())
                source.assert_unchanged(directory / "source", revision)
                result_path = Path(variables["stage_dir"]) / "result.json"
                result = validation.ingest_stage(result_path, identity, self.config["mode"], stage, self.config["validation"])
                record["results"][stage] = result
                decisions = validation.gates(record["results"], self.config["validation"], stage, phase=phase)
                record["gates"].extend(decisions)
                write_json(directory / "normalized.json", record["results"])
                self.event("stage_finish", trial=identifier, stage=stage, result_sha256=file_digest(result_path))
                self.save()
                failed = [gate for gate in decisions if not gate["pass"]]
                # 基线必须完整验证质量；性能目标不通过时仍可作为待优化起点。
                if failed and phase != "baseline":
                    record["status"] = "REJECTED_PERFORMANCE" if stage == "benchmark" else "REJECTED_VALIDATION"
                    break
            else:
                decisions = validation.gates(record["results"], self.config["validation"], phase=phase)
                record["gates"] = decisions
                if all(gate["pass"] for gate in decisions):
                    record["score"] = validation.score(record["results"], self.config["validation"])
                    record["status"] = "VALID"
                elif phase == "baseline":
                    failed_stages = {gate["stage"] for gate in self.config["validation"]["gates"]
                                     if any(item["name"] == gate["name"] and not item["pass"] for item in decisions)}
                    record["status"] = "BASELINE_TARGET_NOT_MET" if failed_stages <= {"benchmark"} else "BASELINE_INVALID"
                else:
                    record["status"] = "REJECTED_VALIDATION"
        except StepFailure as exc:
            record["status"] = "DEPLOYMENT_FAILED" if record.get("stage") in ("preflight", "build", "deploy", "smoke") else "EXECUTION_FAILED"
            record["error"] = str(exc)
        except KSEOError as exc:
            record["status"] = "INVALID_MEASUREMENT"
            record["error"] = str(exc)
        except KeyboardInterrupt:
            record["status"] = "INTERRUPTED"
            raise
        finally:
            record["finished_at"] = now()
            self.cleanup(record)
            if record["cleanup"] != "FAILED":
                self.state["active_trial"] = None
            self.save()
            write_json(directory / "trial.json", record)
            self.event("trial_finish", trial=identifier, status=record["status"])
        return record

    def consider(self, trial: dict) -> None:
        if trial["status"] != "VALID":
            return
        best = self.state.get("best")
        direction = self.config["validation"]["objective"]["direction"]
        improvement = self.config["optimizer"].get("min_relative_improvement", 0)
        better = best is None
        if best:
            delta = best["score"] - trial["score"] if direction == "min" else trial["score"] - best["score"]
            better = delta > abs(best["score"]) * improvement
        if better:
            self.state["best"] = {"id": trial["id"], "directory": trial["directory"], "score": trial["score"],
                                  "parameters": trial["parameters"], "identity": trial["identity"]}
            trial["status"] = "ACCEPTED"
            self.event("best_updated", trial=trial["id"], score=trial["score"])
        else:
            trial["status"] = "VALID_NO_GAIN"
        self.save()
        write_json(self.root / trial["directory"] / "trial.json", trial)

    def recover(self) -> bool:
        active_workflow = self.state.get("active_workflow")
        if active_workflow:
            self.lease["clean"] = False
            recover_processes(self.root / active_workflow)
            attempt = next(item for item in self.state["pipeline"]["attempts"] if item["directory"] == active_workflow)
            parent = next(item for item in self.state["trials"] if item["id"] == attempt["parent_trial"])
            if not self.cleanup(parent, recovery=True):
                return False
            attempt["status"] = "INTERRUPTED"
            phases_path = self.root / active_workflow / "kernel_phases.json"
            if phases_path.exists():
                phases = read_json(phases_path)
                write_json(phases_path, {name: "INTERRUPTED" if outcome == "RUNNING" else outcome for name, outcome in phases.items()})
            write_json(self.root / active_workflow / "workflow.json", attempt)
            self.state["active_workflow"] = None
            self.event("interrupted_workflow_recovered", workflow=attempt["id"])
            self.save()
        active = self.state.get("active_trial")
        if not active:
            return True
        trial = next(item for item in self.state["trials"] if item["id"] == active)
        self.lease["clean"] = False
        recover_processes(self.root / trial["directory"])
        if not self.cleanup(trial, recovery=True):
            return False
        trial["status"] = "INTERRUPTED"
        trial["finished_at"] = now()
        self.state["active_trial"] = None
        self.event("interrupted_trial_recovered", trial=active)
        self.save()
        return True

    def loop(self) -> None:
        from .workflows.system import SystemWorkflow
        SystemWorkflow(self).run()

    def check_tools(self) -> None:
        variables = {"config_dir": self.state["config_dir"], "package_dir": str(Path(__file__).parent), "python": sys.executable}
        paths = set(Path(__file__).parent.rglob("*.py"))
        paths.update(Path(__file__).parent.joinpath("data").glob("*.json"))
        commands = []
        def collect(value):
            if isinstance(value, dict):
                if isinstance(value.get("command"), list):
                    commands.append(value)
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
        collect(self.config)
        for command in commands:
            for arg in command["command"]:
                expanded = expand(arg, variables)
                if "{" not in expanded and Path(expanded).is_file():
                    paths.add(Path(expanded).resolve())
        workload = Path(self.config["inputs"]["workload"])
        if not workload.is_absolute():
            workload = Path(self.state["config_dir"]) / workload
        if self.config["mode"] == "measured" and workload.is_file():
            if file_digest(workload) != self.config["inputs"]["workload_sha256"]:
                raise KSEOError("冻结负载清单 SHA256 不匹配")
            paths.add(workload.resolve())
        manifest = {str(path): file_digest(path) for path in sorted(paths)}
        path = self.root / "tools_manifest.json"
        if path.exists() and manifest != read_json(path):
            raise KSEOError("执行工具、KSEO 代码或负载文件已变化，拒绝沿用旧合同恢复")
        if not path.exists():
            write_json(path, manifest)

    def report(self) -> None:
        best = self.state.get("best")
        lines = [f"# {self.config['name']} 优化报告", "", f"- 状态：`{self.state['status']}`",
                 f"- 结果类型：`{self.config['mode']}`", f"- 停止原因：`{self.state.get('stop_reason', '')}`",
                 f"- 累计计费时间：{self.state['elapsed_seconds']:.3f}s",
                 f"- 保守 GPU 小时估算：{self.state['elapsed_seconds'] * self.config['resources'].get('gpu_count', 0) / 3600:.6f}", ""]
        if self.config["mode"] != "measured":
            lines += ["本次为 synthetic 示例或历史 replay，不代表真实模型的新实测收益。", ""]
        lines += ["| 实验 | 阶段 | 结果 | objective |", "| --- | --- | --- | --- |"]
        for trial in self.state["trials"]:
            lines.append(f"| {trial['id']} | {trial['phase']} | {trial['status']} | {trial.get('score', '')} |")
        lines += [""]
        if self.state.get("pipeline"):
            pipeline = self.state["pipeline"]
            tree = {"system_status": self.state["status"], "profile_source": pipeline.get("profile_source"), "workflows": []}
            lines += ["## 分层流水线", "", "| 子流程 | 热点 | 局部与集成结果 | E2E trial |", "| --- | --- | --- | --- |"]
            for attempt in pipeline["attempts"]:
                phases_path = self.root / attempt["directory"] / "kernel_phases.json"
                phases = read_json(phases_path) if phases_path.exists() else {}
                tree["workflows"].append({**attempt, "kernel_phases": phases})
                hotspot = (attempt.get("hotspot") or {}).get("id", "")
                lines.append(f"| {attempt['lane']} | {hotspot} | {attempt['status']} | {attempt.get('trial', '')} |")
            write_json(self.root / "workflow-tree.json", tree)
            lines += ["", "`workflow-tree.json` 保存 System 大流程与 Kernel 内部阶段的对应关系。", ""]
        if best:
            bundle = self.root / "bundle"
            bundle.mkdir(exist_ok=True)
            write_json(bundle / "parameters.json", best["parameters"])
            patch_sha = source.export_patch(self.root / "source-base", self.root / best["directory"] / "source", bundle / "source.patch")
            write_json(bundle / "manifest.json", {"schema_version": 1, "mode": self.config["mode"], "status": self.state["status"],
                       "best": best, "final_trial": self.state.get("final_trial"), "contract_sha256": self.state["contract_sha256"],
                       "source_patch_sha256": patch_sha, "note": "本地源码与配置交付包；真实镜像由 build adapter 产物提供。"})
            lines += [f"最佳已通过候选：`{best['id']}`，objective 为 `{best['score']}`。", "",
                      "`bundle/` 保存配置和相对基线的累积源码补丁。请保留完整运行目录以追溯证据。", ""]
        if self.config["validation"].get("final_accuracy"):
            final = next((t for t in self.state["trials"] if t["id"] == self.state.get("final_trial")), None)
            results = (final or {}).get("results", {}).get("final_accuracy", {}).get("benchmarks", {})
            lines += ["## 最终精度", "", "| 数据集 | 完整样本 | 得分 | 有效性审阅 | 结论 |", "| --- | --- | --- | --- | --- |"]
            for suite in self.config["validation"]["final_accuracy"]["suites"]:
                value = results.get(suite["id"], {})
                lines.append(f"| {suite['id']} | {value.get('samples', 'NOT_RUN')} | {value.get('score', '')} | {value.get('validity_review_passed', False)} | {'PASS' if value.get('passed') else 'NOT_PASSED'} |")
            lines += ["", "分数与证据有效性同时验收；未运行、缺失 raw 或未解决争议均不自动通过。", ""]
        (self.root / "report.md").write_text("\n".join(lines), encoding="utf-8")

    def run(self, task_path: Path | None = None) -> dict:
        self.root.mkdir(parents=True, exist_ok=True)
        with file_lock(self.root / "controller.lock"):
            exists = (self.root / "state.json").exists()
            if task_path is not None:
                if exists:
                    raise KSEOError("运行目录已存在，请使用 kseo resume")
                self.config = load(task_path)
                self.state = {"schema_version": 1, "kseo_version": __version__, "run_id": uuid.uuid4().hex,
                              "status": "RUNNING", "created_at": now(), "config_dir": str(task_path.resolve().parent),
                              "contract_sha256": digest(self.config), "trials": [], "best": None,
                              "elapsed_seconds": 0.0, "charged_at": None, "active_trial": None}
                write_json(self.root / "task.json", self.config)
                self.save()
            else:
                if not exists:
                    raise KSEOError("运行目录中没有 state.json")
                self.config = validate(read_json(self.root / "task.json"))
                self.state = read_json(self.root / "state.json")
                if digest(self.config) != self.state["contract_sha256"]:
                    raise KSEOError("冻结任务合同已被修改，拒绝恢复")
                if self.state["status"] in ("COMPLETED", "CANDIDATE_ONLY"):
                    return self.state
            lock_dir = Path(self.config["resources"].get("lock_dir", str(self.root.parent / ".kseo-locks"))).resolve()
            with resource_locks(lock_dir, self.config["resources"]["keys"], str(self.root)) as lease:
                self.lease = lease
                self.save()  # 崩溃后的未结束时间保守计入预算。
                self.state["charged_at"] = time.time()
                self.state["status"] = "RUNNING"
                self.save()
                self.event("controller_start", resume=exists)
                try:
                    self.loop()
                except KeyboardInterrupt:
                    if self.state.get("active_workflow"):
                        self.recover()
                    self.state["status"] = "INTERRUPTED" if lease["clean"] else "CLEANUP_FAILED"
                except (KSEOError, OSError) as exc:
                    self.state["status"] = "CONTROLLER_FAILED"
                    self.state["error"] = str(exc)
                    self.event("controller_failed", error=str(exc))
                finally:
                    self.save()
                    self.state["charged_at"] = None
                    self.save()
                    self.report()
            return self.state
