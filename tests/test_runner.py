import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from kseo.cli import audit
from kseo.demo import task
from kseo.locking import file_lock, resource_locks
from kseo.runner import Runner
from kseo.util import KSEOError, digest, read_json, write_json


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_task(self, config=None, name="run"):
        config = config or task()
        path = self.root / (name + ".json")
        write_json(path, config)
        directory = self.root / name
        return Runner(directory).run(path), directory, path

    def test_grid_rejects_tradeoff_and_revalidates(self):
        state, directory, path = self.run_task()
        self.assertEqual(state["status"], "COMPLETED")
        self.assertEqual(state["best"]["parameters"], {"chunk_tokens": 1024})
        self.assertTrue(any(t["status"] == "REJECTED_PERFORMANCE" for t in state["trials"]))
        self.assertEqual(state["trials"][-1]["phase"], "final")
        self.assertTrue(audit(path, directory / state["best"]["directory"])["pass"])
        manifest = read_json(directory / "bundle/manifest.json")
        self.assertEqual(manifest["mode"], "synthetic")

    def test_agent_applies_patch_without_modifying_original(self):
        original = Path(__file__).resolve().parents[1] / "src/kseo/data/demo_kernel.py"
        content = original.read_bytes()
        state, directory, _ = self.run_task(task(agent=True))
        self.assertEqual(state["status"], "COMPLETED")
        self.assertAlmostEqual(state["best"]["score"], 84.3)
        self.assertEqual(original.read_bytes(), content)
        self.assertIn("+KERNEL_SCALE = 0.8", (directory / "bundle/source.patch").read_text())

    def test_completed_resume_is_idempotent(self):
        state, directory, _ = self.run_task()
        resumed = Runner(directory).run()
        self.assertEqual(resumed, state)

    def test_changed_contract_cannot_resume(self):
        _, directory, _ = self.run_task()
        frozen = read_json(directory / "task.json")
        frozen["parameters"]["chunk_tokens"] = 1024
        write_json(directory / "task.json", frozen)
        with self.assertRaises(KSEOError): Runner(directory).run()

    def test_deploy_failure_not_scored(self):
        config = task()
        config["steps"][0]["command"] = ["{python}", "-c", "raise SystemExit(7)"]
        state, _, _ = self.run_task(config)
        self.assertEqual(state["status"], "BASELINE_INVALID")
        self.assertEqual(state["trials"][0]["status"], "DEPLOYMENT_FAILED")
        self.assertIsNone(state["best"])

    def test_adapter_failure_still_cleans_up(self):
        script = self.root / "cleanup.py"
        marker = self.root / "cleaned"
        script.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ok')\n")
        config = task(); config["steps"][0]["command"] = ["{python}", "-c", "raise SystemExit(7)"]
        config["cleanup"]["command"] = ["{python}", str(script)]
        state, _, _ = self.run_task(config)
        self.assertTrue(marker.exists())
        self.assertEqual(state["trials"][0]["cleanup"], "PASS")

    def test_cleanup_failure_blocks_other_owner(self):
        config = task(); config["cleanup"]["command"] = ["{python}", "-c", "raise SystemExit(8)"]
        state, _, _ = self.run_task(config)
        self.assertEqual(state["status"], "CLEANUP_FAILED")
        with self.assertRaises(KSEOError): self.run_task(task(), name="other")

    def test_budget_expiry_does_not_report_success(self):
        config = task(); config["budget"]["max_wall_seconds"] = 0.00001
        state, _, _ = self.run_task(config)
        self.assertNotEqual(state["status"], "COMPLETED")
        self.assertIsNone(state["best"])

    def test_unmet_baseline_speed_still_allows_search(self):
        config = task()
        gate = next(g for g in config["validation"]["gates"] if g["name"] == "长上下文 TTFT")
        gate["value"] = 150
        state, _, _ = self.run_task(config)
        self.assertEqual(state["trials"][0]["status"], "BASELINE_TARGET_NOT_MET")
        self.assertIn("quality", state["trials"][0]["results"])
        self.assertEqual(state["status"], "COMPLETED")

    def test_pending_best_selection_recovered(self):
        state, directory, _ = self.run_task()
        best_id = state["best"]["id"]
        state["best"] = None
        state["status"] = "INTERRUPTED"
        for trial in state["trials"]:
            if trial["id"] == best_id: trial["status"] = "VALID"
        write_json(directory / "state.json", state)
        resumed = Runner(directory).run()
        self.assertEqual(resumed["status"], "COMPLETED")
        self.assertEqual(resumed["best"]["id"], best_id)

    def test_interrupted_trial_is_marked_and_retried(self):
        state, directory, _ = self.run_task()
        candidate = next(t for t in state["trials"] if t["status"] == "REJECTED_PERFORMANCE")
        state["status"] = "INTERRUPTED"
        state["active_trial"] = candidate["id"]
        candidate["status"] = "RUNNING"
        state["trials"] = [t for t in state["trials"] if t["phase"] != "final"]
        write_json(directory / "state.json", state)
        resumed = Runner(directory).run()
        self.assertEqual(resumed["status"], "COMPLETED")
        repeated = [t for t in resumed["trials"] if t["parameters"]["chunk_tokens"] == 2048]
        self.assertEqual(len(repeated), 2)
        self.assertEqual(repeated[0]["status"], "INTERRUPTED")

    def test_controller_lock_excludes_second_controller(self):
        path = self.root / "controller.lock"
        with file_lock(path):
            with self.assertRaises(KSEOError):
                with file_lock(path): pass

    def test_resource_lock_excludes_shared_gpu(self):
        with resource_locks(self.root, ["gpu-uuid"], "one"):
            with self.assertRaises(KSEOError):
                with resource_locks(self.root, ["gpu-uuid"], "two"): pass


if __name__ == "__main__": unittest.main()
