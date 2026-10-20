import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from kseo import optimizer
from kseo.cli import main
from kseo.demo import task
from kseo.knowledge import load_cards, retrieve
from kseo.recipes import catalog, for_context, load_recipe
from kseo.util import KSEOError, read_json


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.recipe = load_recipe("deepseek-v4.1-flash")

    def test_only_v41_has_dedicated_recipe(self):
        self.assertEqual([entry["id"] for entry in catalog()], ["deepseek-v4.1-flash"])
        for family in (None, "deepseek_v4", "deepseek-v4-flash", "glm5_2", "glm5_1"):
            self.assertIsNone(for_context({"model_family": family}))

    def test_explicit_aliases_load_same_recipe(self):
        for alias in self.recipe["aliases"]:
            self.assertEqual(for_context({"model_family": alias})["id"], self.recipe["id"])

    def test_unknown_recipe_cannot_fall_back_to_other_model(self):
        with self.assertRaises(KSEOError):
            load_recipe("DeepSeek-V4-Flash")

    def test_current_policy_precedes_more_specific_old_card(self):
        context = {"model_family": "deepseek_v4_1", "gpu_arch": "sm80",
                   "capabilities": ["mhc", "target_verified_speculation", "kv_offloading"]}
        selected = retrieve(context, load_cards(), 1)
        self.assertEqual(selected[0]["id"], "V41-P01")

    def test_all_rules_are_available_independently_of_top_k(self):
        recipe = for_context({"model_family": "deepseek_v4_1"})
        self.assertEqual(set(recipe["rules"]), {f"V41-P{index:02d}" for index in range(1, 12)})
        self.assertNotIn("cards", recipe)

    def test_hardware_case_not_migrated_without_hardware_identity(self):
        cards = load_cards()
        context = {"model_family": "deepseek_v4_1", "capabilities": ["mhc"]}
        self.assertNotIn("V41-H02", {card["id"] for card in retrieve(context, cards, 100)})
        context["gpu_arch"] = "sm80"
        self.assertIn("V41-H02", {card["id"] for card in retrieve(context, cards, 100)})

    def test_current_rules_do_not_claim_unimplemented_audit(self):
        state = self.recipe["implementation_status"]
        self.assertEqual(state["real_single_node_deployment"], "not_included")
        self.assertEqual(state["pd_deployment"], "not_included")
        rules = self.recipe["rules"]
        self.assertFalse(rules["V41-P03"]["enforcement"]["automatic_gate_enabled"])
        self.assertIsNone(rules["V41-P04"]["max_adjacent_growth_ratio"])
        self.assertFalse(rules["V41-P06"]["output_text_similarity_gate_enabled"])
        self.assertIn("仅在", rules["V41-P05"]["activation"])

    def test_source_references_complete_and_current_text_hash_matches(self):
        sources = {source["id"]: source for source in self.recipe["sources"]}
        self.assertEqual(len(sources), len(self.recipe["sources"]))
        for row in [*self.recipe["cards"], *self.recipe["rules"].values()]:
            for source_id in row["source_ids"]:
                self.assertIn(source_id, sources)
        for source in sources.values():
            self.assertRegex(source["sha256"], r"^[a-f0-9]{64}$")
        for source_id in ("U01", "U02", "U03"):
            current = sources[source_id]
            self.assertEqual(hashlib.sha256("\n".join(current["statements"]).encode()).hexdigest(), current["sha256"])

    def test_model_pack_retains_stage_result_boundaries(self):
        cards = {card["id"]: card for card in self.recipe["cards"]}
        self.assertEqual(len(cards), 28)
        self.assertEqual(cards["V41-H05"]["status"], "INDETERMINATE_UNDER_AMENDED_RULE")
        self.assertEqual(cards["V41-H07"]["status"], "STAGE_PASS_FULL_TASK_REJECTED")
        self.assertIn("PENDING_FINAL", cards["V41-H10"]["status"])
        self.assertIn("SEPARATE_RUN_REJECTED", cards["V41-H11"]["status"])

    def test_metrics_aliases_require_real_observability(self):
        metrics = self.recipe["rules"]["V41-P07"]
        self.assertEqual(metrics["public_paths"], ["/metrics", "/v1/metrics"])
        self.assertIn("Waiting", metrics["required_metrics"])
        self.assertFalse(metrics["enforcement"]["implemented_by_recipe"])
        self.assertIn("ITL", " ".join(metrics["procedure"]))

    def test_v41_usage_preserves_backend_specific_four_field_accounting(self):
        usage = self.recipe["rules"]["V41-P08"]
        self.assertEqual(set(usage["usage_fields"]), {"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"})
        self.assertEqual(usage["server_prompt_formula"], "input_tokens + cache_read_input_tokens")
        self.assertIn("不能", usage["usage_fields"]["cache_creation_input_tokens"])
        self.assertIn("cache_read_input_tokens /", usage["cache_hit_rate_formula"])

    def test_router_clips_output_before_global_reservation(self):
        router = self.recipe["rules"]["V41-P09"]
        self.assertEqual(router["effective_output_formula"], "min(requested_max_output_tokens, max_model_len - prompt_tokens)")
        self.assertIn("裁剪后预算", router["procedure"][0])
        self.assertIn("没有至少一个生成 token", router["input_equal_limit"])

    def test_new_image_policy_supersedes_old_bounds_without_inventing_quotas(self):
        limits = self.recipe["rules"]["V41-P10"]
        for key in ("gateway_image_width_limit", "gateway_image_height_limit", "gateway_image_pixel_limit", "gateway_image_format_allowlist", "max_outstanding_requests", "max_reserved_tokens"):
            self.assertIsNone(limits[key])
        self.assertIn("running_requests", limits["outstanding_requests_formula"])
        self.assertIn("admitted_waiting_requests", limits["outstanding_requests_formula"])
        self.assertTrue(any("旧 API 图像" in item["scope"] for item in self.recipe["history_policy"]))

    def test_stability_requires_text_and_conditional_vision_1200(self):
        replay = self.recipe["rules"]["V41-P11"]
        self.assertEqual(replay["text_replay_requests"], 1200)
        self.assertEqual(replay["vision_replay_requests_if_capable"], 1200)
        self.assertTrue(replay["image_count_sampling"]["frozen_before_measuring"])
        self.assertFalse(replay["image_count_sampling"]["counts_are_api_limits"])
        self.assertIsNone(replay["success_rate_threshold"])

    def test_cli_export_and_existing_file_protection(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            output = Path(temp) / "recipe.json"
            self.assertEqual(main(["recipe", "deepseek-v4.1-flash", "--out", str(output)]), 0)
            self.assertEqual(read_json(output)["id"], self.recipe["id"])
            original = output.read_bytes()
            self.assertEqual(main(["recipe", "deepseek-v4.1-flash", "--out", str(output)]), 2)
            self.assertEqual(output.read_bytes(), original)

    def test_cli_knowledge_can_retrieve_more_than_eight(self):
        with tempfile.TemporaryDirectory() as temp:
            context = Path(temp) / "context.json"
            context.write_text(json.dumps({"model_family": "deepseek_v4_1"}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["knowledge", "--context", str(context), "--limit", "40"])
            cards = json.loads(out.getvalue())
            self.assertEqual(code, 0)
            self.assertGreater(len(cards), 8)
            self.assertEqual([card["id"] for card in cards[:11]], [f"V41-P{i:02d}" for i in range(1, 12)])

    def test_agent_receives_complete_recipe_and_stops_without_gpu(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source").mkdir()
            wrapper = root / "agent.py"
            wrapper.write_text(
                "import json,os\nfrom pathlib import Path\n"
                "request=json.loads(Path(os.environ['KSEO_AGENT_REQUEST']).read_text())\n"
                "assert len(request['model_recipe']['rules'])==11\n"
                "assert request['model_recipe']['rules']['V41-P06']['output_text_similarity_gate_enabled'] is False\n"
                "assert 'cards' not in request['model_recipe']\n"
                "assert any(card['id'].startswith('V41-H') for card in request['experience'])\n"
                "assert not any(card.get('status')=='CURRENT_USER_POLICY' for card in request['experience'])\n"
                "assert '不得据此写 PASS' in request['instructions']\n"
                "Path(os.environ['KSEO_AGENT_PROPOSAL']).write_text('{\"stop\":true}')\n"
            )
            config = task(agent=True)
            config["context"]["model_family"] = "deepseek_v4_1"
            config["optimizer"]["command"] = ["{python}", str(wrapper)]
            import sys
            result = optimizer.agent(config, {"trials": [], "best": None}, root / "proposal",
                                     {"run_dir": str(root), "source_dir": str(root / "source"), "python": sys.executable}, {}, 20)
            self.assertIsNone(result)
            request = read_json(root / "proposal/request.json")
            self.assertEqual(request["model_recipe"]["id"], self.recipe["id"])


if __name__ == "__main__":
    unittest.main()
