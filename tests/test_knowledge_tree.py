import contextlib
import copy
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from kseo import optimizer
from kseo.cli import main
from kseo.demo import task
from kseo.knowledge import load_cards
from kseo.knowledge_tree import inspect_node, load_hierarchy, overview, retrieve_hierarchy, validate
from kseo.recipes import load_recipe
from kseo.util import KSEOError, read_json


class KnowledgeTreeTests(unittest.TestCase):
    def setUp(self):
        self.data = load_hierarchy()
        self.nodes = {node["id"]: node for node in self.data["nodes"]}

    def test_all_reviewed_candidates_and_existing_cards_are_reachable(self):
        ids = set(self.nodes)
        self.assertTrue({f"R{i:02d}" for i in range(1, 21)} <= ids)
        self.assertTrue({f"case:R{i:02d}" for i in range(1, 21)} <= ids)
        self.assertTrue({card["id"] for card in load_cards()} <= ids)
        self.assertEqual(overview(self.data)["counts"], {"1": 6, "2": 12, "3": 51, "4": 59})

    def test_every_case_has_continuous_ancestry_and_explicit_boundary(self):
        for node in self.data["nodes"]:
            self.assertFalse(node["evidence_boundary"]["revalidated_in_kseo"])
            if node["level"] == 4:
                result = inspect_node(node["id"], self.data)
                self.assertEqual([a["level"] for a in result["ancestors"]], [1, 2, 3])

    def test_unknown_capabilities_do_not_select_specialized_rules(self):
        ids = {n["id"] for n in retrieve_hierarchy({}, 100, self.data)["nodes"]}
        self.assertFalse({"R03", "R07", "R09", "R10", "R11", "R13", "R15", "R17", "R18", "R20"} & ids)
        self.assertNotIn("V41-P01", ids)
        for i in ids:
            if self.nodes[i]["level"] == 4:
                self.assertEqual(self.nodes[i].get("applies_to", {}), {})
                self.assertEqual(self.nodes[i].get("requires_capabilities", []), [])

    def test_new_model_defaults_are_unconditional_but_contain_no_example_targets(self):
        for model in ('unseen_model','glm5_2','deepseek_v4_1'):
            result=retrieve_hierarchy({'model_family':model},1,self.data)
            node=next(n for n in result['nodes'] if n['id']=='G-P03')
            defaults=node['policy']['defaults']
            self.assertEqual(defaults['speed']['output_token_basis'],'reasoning_plus_final')
            self.assertNotIn('input_tokens',defaults['speed'])
            self.assertNotIn('min_scores',defaults['accuracy'])
            self.assertFalse(node['evidence_boundary']['revalidated_in_kseo'])

    def test_conditional_rule_transfers_but_old_model_case_does_not(self):
        context = {"model_family": "new-model", "capabilities": ["pd_disaggregation"]}
        ids = {n["id"] for n in retrieve_hierarchy(context, 100, self.data)["nodes"]}
        self.assertIn("R09", ids)
        self.assertNotIn("case:R09", ids)
        context["model_family"] = "glm5_1"
        ids = {n["id"] for n in retrieve_hierarchy(context, 100, self.data)["nodes"]}
        self.assertIn("case:R09", ids)

    def test_top_k_retains_full_ancestor_chain_and_all_principles(self):
        result = retrieve_hierarchy({"capabilities": ["pd_disaggregation", "mtp", "pp"]}, 1, self.data)
        rules = [n for n in result["nodes"] if n["level"] == 3 and n["kind"] != "current_policy"]
        self.assertEqual([n["id"] for n in rules], ["R11"])
        self.assertEqual(rules[0]["ancestor_ids"], ["K04", "M07"])
        self.assertEqual(sum(n["level"] == 1 for n in result["nodes"]), 6)
        self.assertIn("M07", {n["id"] for n in result["nodes"]})

    def test_current_policy_is_complete_and_unresolved_parameters_stay_unresolved(self):
        result = retrieve_hierarchy({"model_family": "deepseek_v4_1"}, 1, self.data)
        self.assertEqual(set(result["current_rule_ids"]), {"G-P01", "G-P02", "G-P03", *[f"V41-P{i:02d}" for i in range(1, 12)]})
        policies = {n["id"]: n["policy"] for n in result["nodes"] if n["id"].startswith("V41-P")}
        self.assertEqual(policies, load_recipe("deepseek-v4.1-flash")["rules"])
        self.assertFalse(policies["V41-P03"]["enforcement"]["automatic_gate_enabled"])
        self.assertIsNone(policies["V41-P04"]["max_adjacent_growth_ratio"])
        self.assertFalse(policies["V41-P06"]["output_text_similarity_gate_enabled"])

    def test_case_context_and_hardware_still_required(self):
        context = {"model_family": "deepseek_v4_1", "capabilities": ["mhc"]}
        ids = {n["id"] for n in retrieve_hierarchy(context, 100, self.data)["nodes"]}
        self.assertNotIn("V41-H02", ids)
        context["gpu_arch"] = "sm80"
        ids = {n["id"] for n in retrieve_hierarchy(context, 100, self.data)["nodes"]}
        self.assertIn("V41-H02", ids)
        self.assertNotIn("case:R13", ids)

    def test_open_output_causality_is_not_upgraded(self):
        for i in ("R15", "R20"):
            for key in (i, "case:" + i):
                self.assertEqual(self.nodes[key]["evidence_boundary"]["causal_status"], "OUTPUT_CAUSALITY_OPEN")
        self.assertIn("NOT_CONFIRMED", self.nodes["C09"]["status"])
        self.assertEqual(self.nodes["case:R19"]["evidence_boundary"]["causal_status"], "LOCAL_TEST_REPORT_ONLY")

    def test_existing_case_status_and_observations_remain_exact(self):
        for card in load_cards():
            node = self.nodes[card["id"]]
            self.assertEqual(node["status"], card["status"])
            self.assertEqual(node.get("observations"), card.get("observations"))
        self.assertEqual(self.nodes["V41-H07"]["status"], "STAGE_PASS_FULL_TASK_REJECTED")

    def test_sources_are_namespaced_hash_addressed_and_not_private_absolute_paths(self):
        source_ids = {s["id"] for s in self.data["sources"]}
        self.assertEqual(len(source_ids), 74)
        for source in self.data["sources"]:
            self.assertRegex(source["sha256"], r"^[a-f0-9]{64}$")
            if "relative_path" in source:
                self.assertFalse(Path(source["relative_path"]).is_absolute())
                self.assertGreater(source["line"], 0)
                self.assertIs(type(source["raw_in_repository"]), bool)
        for node in self.nodes.values():
            self.assertTrue(set(node.get("source_ids", [])) <= source_ids)
        text = json.dumps(self.data)
        self.assertNotIn("/nfs/", text)
        self.assertFalse(re.search(r"\b(?:10|192\.168)\.\d+\.\d+", text))

    def test_summary_cards_without_direct_hash_do_not_get_fabricated_sources(self):
        self.assertEqual(self.nodes["C05"]["source_ids"], [])
        self.assertIn("无逐卡原文件 SHA256", " ".join(self.nodes["C05"]["evidence_boundary"]["not_established"]))

    def test_math_equivalence_is_unconditional_normative_policy_with_no_invented_tolerance(self):
        for context in ({}, {"model_family": "new-model"}, {"model_family": "deepseek_v4_1"},
                        {"model_family": "glm5_2", "capabilities": ["mtp"]}):
            result = retrieve_hierarchy(context, 1, self.data)
            self.assertIn("G-P01", result["current_rule_ids"])
            node = next(n for n in result["nodes"] if n["id"] == "G-P01")
            self.assertEqual(node["ancestor_ids"], ["K01", "M02"])
            policy = node["policy"]
            self.assertTrue(policy["mathematical_equivalence_required"])
            self.assertFalse(policy["bitwise_equality_required"])
            self.assertTrue(policy["floating_point_tolerance"]["defined_before_search"])
            self.assertIsNone(policy["floating_point_tolerance"]["universal_atol"])
            self.assertIsNone(policy["floating_point_tolerance"]["universal_rtol"])
            self.assertFalse(policy["enforcement"]["automatic_global_pass_enabled"])
            self.assertEqual(node["evidence_boundary"]["causal_status"], "NORMATIVE_NOT_EMPIRICAL")
            self.assertIn("不重新启用模型输出文本相似度门禁", " ".join(policy["procedure"]))
        source = next(s for s in self.data["sources"] if s["id"] == "policy:U01")
        self.assertEqual(source["sha256"], hashlib.sha256("\n".join(source["statements"]).encode()).hexdigest())

    def test_node_drilldown_carries_sources_and_parent_boundaries(self):
        result = inspect_node("case:R15", self.data)
        self.assertEqual([a["id"] for a in result["ancestors"]], ["K04", "M08", "R15"])
        self.assertEqual([s["id"] for s in result["sources"]], ["cross:S15"])
        self.assertGreater(result["sources"][0]["line"], 0)
        self.assertIn("not_established", result["ancestors"][0]["evidence_boundary"])
        self.assertIn("case:R15", inspect_node("K04", self.data)["case_ids"])
        with self.assertRaises(KSEOError):
            inspect_node("unreviewed-import", self.data)

    def test_invalid_hierarchy_cannot_silently_load(self):
        for mutation in ("duplicate", "parent", "source", "boundary"):
            data = copy.deepcopy(self.data)
            node = data["nodes"][0]
            if mutation == "duplicate":
                data["nodes"].append(node)
            elif mutation == "parent":
                node["parent_id"] = "R01"
            elif mutation == "source":
                node["source_ids"] = ["not-a-source"]
            else:
                del node["evidence_boundary"]
            with self.assertRaises(KSEOError):
                validate(data)

    def test_cli_modes_and_protection_against_ambiguous_filtering(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "context.json"
            path.write_text('{"model_family":"glm5_2","capabilities":["index_share"]}')
            for argv, field in ((["--tree"], "tree"), (["--node", "R15"], "node"),
                                (["--hierarchy", "--context", str(path)], "nodes")):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["knowledge", *argv]), 0)
                self.assertIn(field, json.loads(output.getvalue()))
            for argv in ([], ["--node", "unknown"], ["--tree", "--context", str(path)],
                         ["--hierarchy", "--extra", str(path), "--context", str(path)], ["--tree", "--limit", "0"]):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["knowledge", *argv]), 2)

    def test_agent_receives_hierarchy_and_output_causal_limits_without_gpu(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source").mkdir()
            wrapper = root / "agent.py"
            wrapper.write_text(
                "import json,os\nfrom pathlib import Path\n"
                "r=json.loads(Path(os.environ['KSEO_AGENT_REQUEST']).read_text())\n"
                "nodes={n['id']:n for n in r['knowledge_hierarchy']['nodes']}\n"
                "assert nodes['R15']['ancestor_ids']==['K04','M08']\n"
                "assert nodes['case:R15']['evidence_boundary']['causal_status']=='OUTPUT_CAUSALITY_OPEN'\n"
                "assert nodes['K04']['evidence_boundary']['revalidated_in_kseo'] is False\n"
                "assert nodes['G-P01']['policy']['mathematical_equivalence_required'] is True\n"
                "assert any(s['id']=='cross:S15' for s in r['knowledge_hierarchy']['sources'])\n"
                "Path(os.environ['KSEO_AGENT_PROPOSAL']).write_text('{\"stop\":true}')\n"
            )
            config = task(agent=True)
            config["context"] = {"model_family": "glm5_2", "capabilities": ["multi_prefill_producer", "pd_disaggregation", "prefix_cache"]}
            config["optimizer"]["command"] = ["{python}", str(wrapper)]
            self.assertIsNone(optimizer.agent(config, {"trials": [], "best": None}, root / "proposal",
                                             {"run_dir": str(root), "source_dir": str(root / "source"), "python": sys.executable}, {}, 20))
            request = read_json(root / "proposal/request.json")
            self.assertNotIn("model_recipe", request)
            self.assertIn("导航关系不等于因果证明", request["instructions"])


if __name__ == "__main__":
    unittest.main()
