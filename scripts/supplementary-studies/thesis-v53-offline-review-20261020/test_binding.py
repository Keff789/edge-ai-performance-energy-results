"""Focused provenance regressions; no evaluator or numerical package is imported."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("mobile_binding", HERE / "binding.py")
binding = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(binding)
REPO = HERE.parents[2]


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((REPO / binding.INPUT).read_text())

    def test_existing_provenance_chain_preserves_limit(self):
        checks = binding.validate(self.data)
        self.assertEqual(checks["uid"], binding.TARGET_UID)
        self.assertEqual(checks["cross_source_checks"], "passed")
        self.assertFalse(checks["quality_recalculated"])
        self.assertFalse(checks["bootstrap_recalculated"])

    def test_archived_inventory_counts_all_selected_uids(self):
        inventory = binding.archived_binding_inventory(self.data)
        self.assertEqual(inventory["selected_configuration_count"], 14)
        self.assertEqual(inventory["recorded_evaluator_source_bound_count"], 13)
        self.assertEqual(inventory["unbound_uids"], [binding.TARGET_UID])
        changed = copy.deepcopy(self.data)
        del changed["sources"]["historical_evaluator_audit"]["projection"]["/rows/13/uid"]
        with self.assertRaisesRegex(ValueError, "inventory is incomplete"):
            binding.validate(changed)

    def test_model_and_cut_alone_cannot_replace_full_uid(self):
        changed = copy.deepcopy(self.data)
        changed["sources"]["prediction_inventory"]["projection"]["/rows/0/uid"] = (
            "native|mobilenet_v3_large|H10|deepx_to_trt|b135")
        with self.assertRaisesRegex(ValueError, "same full UID"):
            binding.validate(changed)

    def test_original_runtime_request_cannot_be_used_as_replay(self):
        changed = copy.deepcopy(self.data)
        changed["sources"]["central_receipt"]["projection"][""]["source_request_sha256"] = (
            changed["sources"]["original_runtime_request"]["source_sha256"])
        with self.assertRaisesRegex(ValueError, "Central replay request"):
            binding.validate(changed)

    def test_equal_quality_values_do_not_replace_result_hash_binding(self):
        changed = copy.deepcopy(self.data)
        changed["sources"]["central_receipt"]["projection"][""]["result_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Central result hash"):
            binding.validate(changed)

    def test_corroborating_code_cannot_silently_become_execution_proof(self):
        changed = copy.deepcopy(self.data)
        changed["sources"]["historical_evaluator_audit"]["projection"]["/rows/0"][
            "historical_evaluator_source_sha256"
        ] = changed["sources"]["evaluator_source"]["source_sha256"]
        with self.assertRaisesRegex(ValueError, "review and update"):
            binding.validate(changed)

    def test_original_source_verification_rejects_changed_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = b'{"evaluation":{"request":"bound-request","n":5000}}\n'
            (root / "source.json").write_bytes(raw)
            data = {
                "path_normalization": {},
                "sources": {"receipt": {
                    "kind": "json_projection",
                    "source_sha256": binding.sha256(raw),
                    "source_bytes": len(raw),
                    "location": {"root": "original", "path": "source.json"},
                    "projection": {"/evaluation/request": "bound-request"},
                }},
            }
            self.assertEqual(
                binding.verify_originals(data, {"original": root})[0]["status"],
                "hash_and_projection_verified")
            data["sources"]["receipt"]["projection"]["/evaluation/request"] = "other-request"
            with self.assertRaisesRegex(ValueError, "original JSON pointer"):
                binding.verify_originals(data, {"original": root})

    def test_longest_historical_path_substitution_takes_precedence(self):
        substitutions = {"/home/example/": "home:/",
                         "/home/example/archive/": "archive:/"}
        self.assertEqual(binding.normalize("/home/example/archive/item", substitutions),
                         "archive:/item")

    def test_build_is_deterministic_and_does_not_claim_original_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            first = binding.build(REPO, output)
            raw = (output / first["outputs"][0]).read_bytes()
            second = binding.build(REPO, output)
            self.assertEqual(first, second)
            self.assertEqual(raw, (output / first["outputs"][0]).read_bytes())
            report = json.loads(raw)
            self.assertEqual(report["status"], "completed_with_limits")
            self.assertFalse(report["historical_evaluator_binding_closed"])
            self.assertIsNone(report["open_fields"]["evaluation_bound_evaluator_sha256"])
            self.assertNotIn("original_source_verification", report["verification"])


if __name__ == "__main__":
    unittest.main()
