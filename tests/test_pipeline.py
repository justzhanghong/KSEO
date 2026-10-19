import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from kseo.cli import audit
from kseo.adapter import emit
from kseo.config import validate
from kseo.demo import task
from kseo.executor import recover_processes
from kseo.profiling import normalize, route
from kseo.runner import Runner
from kseo.util import KSEOError, read_json, write_json
from kseo.validation import ingest_stage


class ProfilingTests(unittest.TestCase):
    def test_adapter_profile_reaches_system_router_with_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            identity = {"run_id": "run", "trial_id": "trial"}
            write_json(directory / "identity.json", identity)
            profile = {"scope": "critical_path", "hotspots": [
                {"id": "wait", "kind": "host", "share": 0.5, "achievable_speedup": 2}]}
            with patch.dict(os.environ, {"KSEO_STAGE_DIR": str(directory),
                                         "KSEO_IDENTITY_PATH": str(directory / "identity.json"),
                                         "KSEO_MODE": "synthetic", "KSEO_RESULT_PATH": str(directory / "result.json")}):
                result = emit(profile=profile)
            observed = ingest_stage(result, identity, "synthetic", "profile", {})
            self.assertEqual(route(observed["profile"], {"scheduling"}, set(), "r")["lane"], "scheduling")
            with self.assertRaises(KSEOError):
                ingest_stage(result, {"run_id": "other"}, "synthetic", "profile", {})

    def profile(self):
        return normalize({"scope": "critical_path", "hotspots": [
            {"id": "large_no_headroom", "kind": "scheduling", "share": 0.7, "achievable_speedup": 1},
            {"id": "useful", "kind": "kernel", "share": 0.3, "achievable_speedup": 4, "editable": True}]})

    def test_routes_by_headroom_not_only_time(self):
        decision = route(self.profile(), {"kernel", "scheduling"}, set(), "revision")
        self.assertEqual(decision["hotspot"]["id"], "useful")
        self.assertAlmostEqual(decision["hotspot"]["expected_saved_fraction"], 0.225)

    def test_noneditable_kernel_skipped(self):
        profile = self.profile(); profile["hotspots"][0]["editable"] = False
        self.assertIsNone(route(profile, {"kernel"}, set(), "revision"))

    def test_seen_hotspot_skipped(self):
        self.assertIsNone(route(self.profile(), {"kernel"}, {"revision:kernel:useful"}, "revision"))

    def test_unconfigured_lane_not_invoked(self):
        self.assertIsNone(route(self.profile(), {"scheduling"}, set(), "revision"))

    def test_host_work_routes_to_scheduling(self):
        profile = normalize({"scope": "critical_path", "hotspots": [
            {"id": "wait", "kind": "host", "share": 0.5, "achievable_speedup": 2}]})
        self.assertEqual(route(profile, {"scheduling"}, set(), "r")["lane"], "scheduling")

    def test_unknown_scope_rejected(self):
        with self.assertRaises(KSEOError): normalize({"scope": "unknown", "hotspots": []})

    def test_duplicate_hotspots_rejected(self):
        row = {"id": "x", "kind": "kernel", "share": 0.1}
        with self.assertRaises(KSEOError): normalize({"scope": "critical_path", "hotspots": [row, row]})

    def test_invalid_share_and_nan_rejected(self):
        for share in (-0.1, 1.1, float("nan"), True):
            with self.subTest(share=share), self.assertRaises(KSEOError):
                normalize({"scope": "gpu_time", "hotspots": [{"id": "x", "kind": "kernel", "share": share}]})

    def test_critical_path_cannot_double_count(self):
        with self.assertRaises(KSEOError):
            normalize({"scope": "critical_path", "hotspots": [
                {"id": "x", "kind": "kernel", "share": 0.8}, {"id": "y", "kind": "host", "share": 0.8}]})


class PipelineConfigTests(unittest.TestCase):
    def test_pipeline_configuration_valid(self): validate(task(pipeline=True))

    def test_profile_required(self):
        config = task(pipeline=True)
        config["steps"] = [s for s in config["steps"] if s["name"] != "profile"]
        with self.assertRaises(KSEOError): validate(config)

    def test_kernel_has_independent_validator(self):
        config = task(pipeline=True); del config["optimizer"]["kernel"]["validator"]
        with self.assertRaises(KSEOError): validate(config)

    def test_kernel_requires_patch_permission(self):
        config = task(pipeline=True)
        config["optimizer"]["kernel"]["proposer"]["allow_source_changes"] = False
        with self.assertRaises(KSEOError): validate(config)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_task(self, config=None):
        config = config or task(pipeline=True)
        path = self.root / "task.json"; write_json(path, config)
        directory = self.root / "run"
        return Runner(directory).run(path), directory, path

    def test_layered_flow_reprofiles_and_audits_kernel(self):
        state, directory, path = self.run_task()
        self.assertEqual(state["status"], "COMPLETED")
        attempts = state["pipeline"]["attempts"]
        self.assertEqual([a["lane"] for a in attempts], ["configuration", "configuration", "scheduling", "kernel"])
        self.assertAlmostEqual(state["best"]["score"], 75.9)
        best_dir = directory / state["best"]["directory"]
        self.assertTrue(audit(path, best_dir)["pass"])
        trial = read_json(best_dir / "trial.json")
        evidence = trial["kernel_evidence"]
        oracle = directory / evidence["directory"] / "oracle/oracle.json"
        original = oracle.read_bytes(); oracle.write_text("{}")
        with self.assertRaises(KSEOError): audit(path, best_dir)
        oracle.write_bytes(original)
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        self.assertGreaterEqual(sum(e["event"] == "profile_refreshed" for e in events), 3)
        self.assertEqual(state["pipeline"]["profile_source"]["trial"], state["best"]["id"])
        self.assertEqual(read_json(directory / "workflow-tree.json")["workflows"][-1]["kernel_phases"]["local_validation"], "COMPLETED")

    def test_oracle_tampering_cannot_reach_e2e(self):
        script = self.root / "tamper.py"
        script.write_text("import os,json\nfrom pathlib import Path\n"
                          "r=json.loads(Path(os.environ['KSEO_AGENT_REQUEST']).read_text())\n"
                          "(Path(r['workflow']['oracle_dir'])/'oracle.json').write_text('{}')\n"
                          "Path(os.environ['KSEO_AGENT_PROPOSAL']).write_text('{\"stop\":true}')\n")
        config = task(pipeline=True)
        config["optimizer"]["kernel"]["proposer"]["command"] = ["{python}", str(script)]
        state, _, _ = self.run_task(config)
        self.assertEqual(state["status"], "COMPLETED")
        kernels = [a for a in state["pipeline"]["attempts"] if a["lane"] == "kernel"]
        self.assertEqual(kernels[0]["status"], "KERNEL_REJECTED")
        self.assertFalse(any(t.get("workflow_lane") == "kernel" for t in state["trials"]))

    def test_local_speedup_does_not_override_e2e_regression(self):
        script = self.root / "tradeoff.py"
        script.write_text("import os,json,difflib\nfrom pathlib import Path\n"
                          "r=json.loads(Path(os.environ['KSEO_AGENT_REQUEST']).read_text())\n"
                          "out=Path(os.environ['KSEO_AGENT_PROPOSAL'])\n"
                          "old=(Path(r['source_dir'])/'demo_kernel.py').read_text()\n"
                          "new=old.replace('KERNEL_SCALE = 1.0','KERNEL_SCALE = 0.8').replace('SCHEDULER_SCALE = 0.9','SCHEDULER_SCALE = 4.0')\n"
                          "patch=''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='a/demo_kernel.py',tofile='b/demo_kernel.py'))\n"
                          "(out.parent/'patch.diff').write_text(patch)\n"
                          "out.write_text(json.dumps({'parameters':r['best']['parameters'],'patch':'patch.diff','hypothesis':'局部加速但 E2E 回退的 synthetic 候选'}))\n")
        config = task(pipeline=True)
        config["optimizer"]["kernel"]["proposer"]["command"] = ["{python}", str(script)]
        state, directory, _ = self.run_task(config)
        self.assertEqual(state["status"], "COMPLETED")
        kernel = next(a for a in state["pipeline"]["attempts"] if a["lane"] == "kernel")
        self.assertEqual(kernel["status"], "LOCAL_PASS_E2E_REJECTED")
        self.assertGreater(kernel["kernel_evidence"]["speedup"], 1)
        self.assertEqual(next(t for t in state["trials"] if t["id"] == state["best"]["id"])["workflow_lane"], "scheduling")
        self.assertNotIn("+KERNEL_SCALE = 0.8", (directory / "bundle/source.patch").read_text())

    def test_crashed_kernel_workflow_is_cleaned_and_retried(self):
        worker = Path(__file__).resolve().parents[1] / "src/kseo/demo_kernel_worker.py"
        script = self.root / "extract.py"
        script.write_text("import os,time,runpy\nfrom pathlib import Path\n"
                          "marker=Path(os.environ['KSEO_RUN_DIR'])/'first-extract'\n"
                          "if not marker.exists():\n marker.write_text('ready')\n time.sleep(60)\n"
                          f"runpy.run_path({str(worker)!r},run_name='__main__')\n")
        config = task(pipeline=True)
        config["optimizer"]["kernel"]["extractor"] = {"command": ["{python}", str(script)], "timeout_seconds": 90}
        path = self.root / "task.json"; write_json(path, config)
        directory = self.root / "run"
        env = os.environ.copy(); env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        process = subprocess.Popen([sys.executable, "-m", "kseo", "run", str(path), "--run-dir", str(directory)],
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 60
            while not (directory / "first-extract").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    self.fail("子流程未进入预期的提取阶段")
                time.sleep(0.05)
            process.kill(); process.wait(timeout=5)
            resumed = Runner(directory).run()
            self.assertEqual(resumed["status"], "COMPLETED")
            kernels = [a for a in resumed["pipeline"]["attempts"] if a["lane"] == "kernel"]
            self.assertEqual([a["status"] for a in kernels], ["INTERRUPTED", "ACCEPTED"])
            self.assertIsNone(resumed.get("active_workflow"))
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
            if (directory / "state.json").exists():
                state = read_json(directory / "state.json")
                if state.get("active_workflow"):
                    recover_processes(directory / state["active_workflow"])

    def test_proposal_is_recovered_before_integration(self):
        config = task(pipeline=True)
        path = self.root / "task.json"; write_json(path, config)
        directory = self.root / "run"
        original = Runner.trial
        def interrupt(controller, *args, **kwargs):
            if args[1] == "candidate":
                raise KeyboardInterrupt()
            return original(controller, *args, **kwargs)
        with patch.object(Runner, "trial", new=interrupt):
            initial = Runner(directory).run(path)
        self.assertEqual(initial["status"], "INTERRUPTED")
        self.assertEqual(initial["pipeline"]["attempts"][0]["status"], "PROPOSED")
        resumed = Runner(directory).run()
        self.assertEqual(resumed["status"], "COMPLETED")
        self.assertEqual(len(resumed["pipeline"]["attempts"]), 4)
