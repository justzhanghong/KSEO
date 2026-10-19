import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from kseo import validation
from kseo.config import validate
from kseo.demo import task
from kseo.util import KSEOError, file_digest, write_json


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = {"run_id": "run", "trial_id": "trial"}
        self.policy = {"cases": [{"id": "c1", "requests": 2, "input_tokens": 10, "output_tokens": 4}], "zero_cache_reads": True}
        self.rows = [{"request_id": str(i), "case_id": "c1", "status": "completed", "input_tokens": 10,
                      "output_tokens": 4, "cache_read_tokens": 0, "ttft_ms": 10 + i * 10, "total_ms": 40 + i * 10} for i in range(2)]

    def payload(self):
        raw = self.root / "requests.jsonl"
        raw.write_text("".join(json.dumps(row) + "\n" for row in self.rows))
        value = {"schema_version": 1, "kind": "synthetic", "identity": self.identity,
                 "requests_file": raw.name, "requests_file_sha256": file_digest(raw)}
        path = self.root / "result.json"
        write_json(path, value)
        return path, value

    def ingest(self):
        path, _ = self.payload()
        return validation.ingest_stage(path, self.identity, "synthetic", "benchmark", self.policy)

    def test_recomputes_per_token_latency(self):
        result = self.ingest()
        self.assertEqual(result["cases"]["c1"]["ttft_ms"]["mean"], 15)
        self.assertEqual(result["cases"]["c1"]["tpot_ms"]["mean"], 10)

    def test_duplicate_request_invalid(self):
        self.rows[1]["request_id"] = "0"
        with self.assertRaises(KSEOError): self.ingest()

    def test_wrong_count_invalid(self):
        self.rows.pop()
        with self.assertRaises(KSEOError): self.ingest()

    def test_wrong_case_invalid(self):
        self.rows[0]["case_id"] = "unknown"
        with self.assertRaises(KSEOError): self.ingest()

    def test_wrong_output_length_invalid(self):
        self.rows[0]["output_tokens"] = 3
        with self.assertRaises(KSEOError): self.ingest()

    def test_wrong_input_length_invalid(self):
        self.rows[0]["input_tokens"] = 11
        with self.assertRaises(KSEOError): self.ingest()

    def test_cache_hit_invalid(self):
        self.rows[0]["cache_read_tokens"] = 1
        with self.assertRaises(KSEOError): self.ingest()

    def test_missing_cache_evidence_invalid(self):
        del self.rows[0]["cache_read_tokens"]
        with self.assertRaises(KSEOError): self.ingest()

    def test_negative_decode_time_invalid(self):
        self.rows[0]["total_ms"] = 1
        with self.assertRaises(KSEOError): self.ingest()

    def test_nan_invalid(self):
        self.rows[0]["ttft_ms"] = float("nan")
        with self.assertRaises(KSEOError): self.ingest()

    def test_boolean_not_a_latency(self):
        self.rows[0]["ttft_ms"] = True
        with self.assertRaises(KSEOError): self.ingest()

    def test_failed_requests_counted(self):
        self.rows[0]["status"] = "failed"
        self.assertEqual(self.ingest()["failed_requests"], 1)

    def test_identity_mismatch_invalid(self):
        path, _ = self.payload()
        with self.assertRaises(KSEOError):
            validation.ingest_stage(path, {"run_id": "other"}, "synthetic", "benchmark", self.policy)

    def test_synthetic_cannot_be_measured(self):
        path, _ = self.payload()
        with self.assertRaises(KSEOError):
            validation.ingest_stage(path, self.identity, "measured", "benchmark", self.policy)

    def test_raw_hash_tampering_invalid(self):
        path, _ = self.payload()
        (self.root / "requests.jsonl").write_text("{}\n")
        with self.assertRaises(KSEOError):
            validation.ingest_stage(path, self.identity, "synthetic", "benchmark", self.policy)

    def test_artifact_path_escape_invalid(self):
        path, value = self.payload()
        value["requests_file"] = "../outside.jsonl"
        write_json(path, value)
        with self.assertRaises(KSEOError):
            validation.ingest_stage(path, self.identity, "synthetic", "benchmark", self.policy)

    def test_missing_gate_field_fails_closed(self):
        policy = {"gates": [{"name": "test", "field": "quality.accuracy", "op": ">=", "value": 0.95, "stage": "quality"}]}
        self.assertFalse(validation.gates({}, policy)[0]["pass"])

    def test_boolean_gate_rejects_numeric_proxy(self):
        policy = {"gates": [{"name": "test", "field": "api.pass", "op": "==", "value": True, "stage": "api"}]}
        self.assertFalse(validation.gates({"api": {"pass": 1}}, policy)[0]["pass"])

    def test_nearest_rank_p95(self):
        self.assertEqual(validation.stats(list(range(1, 101)))["p95"], 95)

    def test_quality_uses_total_denominator(self):
        rows = [{"sample_id": "a", "correct": True, "failed": False, "unparseable": False},
                {"sample_id": "b", "correct": False, "failed": True, "unparseable": False}]
        raw = self.root / "samples.jsonl"
        raw.write_text("".join(json.dumps(row) + "\n" for row in rows))
        payload = {"samples_file": raw.name, "samples_file_sha256": file_digest(raw)}
        self.assertEqual(validation.quality(payload, self.root, {"quality_samples": 2})["accuracy"], 0.5)
        with self.assertRaises(KSEOError): validation.quality(payload, self.root, {"quality_samples": 3})


class ConfigTests(unittest.TestCase):
    def test_demo_contract_valid(self): validate(task())

    def test_draft_rejected(self):
        value = task(); value["draft"] = True
        with self.assertRaises(KSEOError): validate(value)

    def test_measured_requires_digest(self):
        value = task(); value["mode"] = "measured"
        with self.assertRaises(KSEOError): validate(value)

    def test_unknown_stage_rejected(self):
        value = task(); value["steps"][0]["name"] = "unknown"
        with self.assertRaises(KSEOError): validate(value)

    def test_shell_string_rejected(self):
        value = task(); value["steps"][0]["command"] = "echo unsafe"
        with self.assertRaises(KSEOError): validate(value)

    def test_out_of_space_baseline_rejected(self):
        value = task(); value["parameters"]["chunk_tokens"] = 42
        with self.assertRaises(KSEOError): validate(value)

    def test_future_gate_dependency_rejected(self):
        value = task(); value["validation"]["gates"][0]["field"] = "quality.accuracy"
        with self.assertRaises(KSEOError): validate(value)

    def test_missing_resource_keys_rejected(self):
        value = task(); value["resources"]["keys"] = []
        with self.assertRaises(KSEOError): validate(value)
