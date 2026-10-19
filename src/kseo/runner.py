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

    def trial(self, parameters: dict, phase: str, base: Path, patch: Path | None, hypothesis: str) -> dict:
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
        self.state["trials"].append(record)
        self.state["active_trial"] = identifier
        self.lease["clean"] = False
        self.save()
        self.event("trial_start", trial=identifier, phase=phase)
        try:
            revision = source.fork(base, directory / "source", patch)
            if patch:
                (directory / "proposal.diff").write_bytes(patch.read_bytes())
            write_json(directory / "parameters.json", parameters)
            identity = {"run_id": self.state["run_id"], "trial_id": identifier,
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
                decisions = validation.gates(record["results"], self.config["validation"], stage)
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
                decisions = validation.gates(record["results"], self.config["validation"])
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
        if not self.recover():
            return
        self.check_tools()
        for recorded in self.state["trials"]:
            if recorded["status"] == "VALID" and recorded["phase"] != "final":
                self.consider(recorded)
        base = self.root / "source-base"
        revision = source.freeze(self.config, base, Path(self.state["config_dir"]))
        self.state["baseline_source_revision"] = revision
        self.save()
        retryable = {"INTERRUPTED", "DEPLOYMENT_FAILED", "EXECUTION_FAILED"}
        max_attempts = self.config["budget"].get("max_attempts_per_candidate", 2)
        baselines = [trial for trial in self.state["trials"] if trial["phase"] == "baseline"]
        if baselines and baselines[-1]["status"] in retryable and len(baselines) < max_attempts:
            baselines = []
        if not baselines:
            baseline = self.trial(self.config["parameters"], "baseline", base, None, "冻结基线与完整验证")
            self.consider(baseline)
        else:
            baseline = baselines[-1]
        if self.state["status"] == "CLEANUP_FAILED":
            return
        if baseline["status"] not in ("ACCEPTED", "VALID", "VALID_NO_GAIN", "BASELINE_TARGET_NOT_MET"):
            self.state["status"] = "BASELINE_INVALID"
            return
        reason = "SEARCH_EXHAUSTED"
        while len([trial for trial in self.state["trials"] if trial["phase"] != "final"]) < self.config["budget"]["max_trials"]:
            if self.remaining() <= 0:
                reason = "BUDGET_EXHAUSTED"
                break
            best = self.state.get("best")
            selected_base = self.root / best["directory"] / "source" if best else base
            if self.config["optimizer"]["kind"] == "grid":
                groups = {}
                for previous in self.state["trials"]:
                    if previous["phase"] != "final":
                        groups.setdefault(canonical(previous["parameters"]), []).append(previous)
                tried = {key for key, attempts in groups.items()
                         if len(attempts) >= max_attempts or any(item["status"] not in retryable for item in attempts)}
                proposal = optimizer.grid(self.config, tried)
            else:
                number = len(self.state["trials"])
                proposal_dir = self.root / "proposals" / f"p{number:04d}"
                variables = {"run_dir": str(self.root), "source_dir": str(selected_base),
                             "package_dir": str(Path(__file__).parent), "config_dir": self.state["config_dir"],
                             "python": sys.executable}
                before = source.git(selected_base, "rev-parse", "HEAD")
                proposal = optimizer.agent(self.config, self.state, proposal_dir, variables, {}, self.remaining())
                source.assert_unchanged(selected_base, before)
            if proposal is None:
                break
            patch_hash = file_digest(proposal["patch"]) if proposal["patch"] else ""
            fingerprint = optimizer.signature(proposal["parameters"], source.git(selected_base, "rev-parse", "HEAD"), patch_hash)
            if any(trial.get("proposal_sha256") == fingerprint and trial["status"] not in retryable for trial in self.state["trials"]):
                reason = "DUPLICATE_PROPOSAL"
                break
            trial = self.trial(proposal["parameters"], "candidate", selected_base, proposal["patch"], proposal["hypothesis"])
            trial["proposal_sha256"] = fingerprint
            self.consider(trial)
            self.save()
            if self.state["status"] == "CLEANUP_FAILED":
                return
        else:
            reason = "TRIAL_LIMIT_REACHED"
        self.state["stop_reason"] = reason
        best = self.state.get("best")
        if not best:
            self.state["status"] = "NO_VALID_CANDIDATE"
        elif self.remaining() <= 0:
            self.state["status"] = "BUDGET_EXHAUSTED_UNVALIDATED"
        elif self.config.get("final_validation", True):
            final = self.trial(best["parameters"], "final", self.root / best["directory"] / "source", None, "独立重新运行最佳候选的完整合同")
            if self.state["status"] == "CLEANUP_FAILED":
                return
            self.state["final_trial"] = final["id"]
            self.state["status"] = "COMPLETED" if final["status"] == "VALID" else "FINAL_VALIDATION_FAILED"
        else:
            self.state["status"] = "CANDIDATE_ONLY"

    def check_tools(self) -> None:
        variables = {"config_dir": self.state["config_dir"], "package_dir": str(Path(__file__).parent), "python": sys.executable}
        paths = set(Path(__file__).parent.glob("*.py"))
        commands = list(self.config["steps"]) + [item for item in (self.config.get("cleanup"),) if item]
        if self.config["optimizer"]["kind"] == "agent":
            commands.append(self.config["optimizer"])
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
