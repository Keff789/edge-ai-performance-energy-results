"""Focused checks for evidence-backed A receipts and unexecuted B/C routes."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("thesis_v53_paths", Path(__file__).with_name("paths.py"))
paths = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(paths)
ROOT = Path(__file__).resolve().parents[3]


class ReproductionPathTests(unittest.TestCase):
    def test_bound_receipts_and_separate_execution_statuses(self):
        with tempfile.TemporaryDirectory(prefix="thesis-v53-paths-test-") as directory:
            output = Path(directory)
            result = paths.build(ROOT, output)
            report = json.loads((output / "reproduction_paths.json").read_text())
            self.assertEqual(result["summary"]["A_output_files"],
                             {"A_deployment_tables": 227, "A_confirmation_tables": 38})
            self.assertEqual(result["summary"]["byte_equal_A_files"], 265)
            self.assertEqual(result["summary"]["manifest_bound_campaign_source_files"], 6)
            self.assertEqual(result["summary"]["B_metric_or_waveform_runs"], 0)
            self.assertEqual(result["summary"]["C_runs_including_validate_only"], 0)
            self.assertEqual(result["summary"]["new_bootstrap_resamples"], 0)
            routes = {route["id"]: route for route in report["routes"]}
            for route in routes.values():
                self.assertEqual(route["executed_in_this_audit"], route["category"] == "A")
                if route["category"] == "A":
                    self.assertTrue(route["execution_receipt"])
                    self.assertEqual(route["status"], "executed_pass")
                elif route["category"] == "C":
                    self.assertEqual(route["status"], "documented")
            self.assertEqual(routes["B_prediction_input_inspection"]["status"], "inputs_verified")
            self.assertEqual(routes["B_prediction_input_inspection"]["observed_result"]["candidate_records"], 5000)
            self.assertIn("INSIDE --storage", routes["B_raw_interval_rederivation"]["write_behavior"])
            self.assertIn("1,000 new bootstrap", " ".join(routes["B_paired_quality_bootstrap"]["limits"]))
            first = (output / "reproduction_paths.json").read_bytes()
            paths.build(ROOT, output / "second")
            self.assertEqual(first, (output / "second/reproduction_paths.json").read_bytes())

    def test_documented_command_cannot_be_promoted_to_executed(self):
        route = {
            "id": "C_controller", "category": "C", "status": "documented",
            "executed_in_this_audit": False, "source_files": ["source"],
            "inputs": ["plan"], "expected_controls": ["UID"],
        }
        paths.validate_routes([route])
        altered = copy.deepcopy(route)
        altered["status"] = "executed_pass"
        with self.assertRaisesRegex(ValueError, "B/C execution"):
            paths.validate_routes([altered])
        altered = copy.deepcopy(route)
        altered["executed_in_this_audit"] = True
        with self.assertRaisesRegex(ValueError, "B/C execution"):
            paths.validate_routes([altered])

    def test_hash_drift_and_external_path_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="thesis-v53-path-binding-") as directory:
            root = Path(directory)
            file = root / "bound.json"
            file.write_text('{"value":1}\n')
            binding = {"path": "bound.json", "sha256": paths.sha(file), "bytes": file.stat().st_size}
            paths.verify_record(root, binding)
            file.write_text('{"value":2}\n')
            with self.assertRaisesRegex(ValueError, "Bound evidence changed"):
                paths.verify_record(root, binding)
            with self.assertRaisesRegex(ValueError, "escapes"):
                paths.repository_file(root, "../external.json")


if __name__ == "__main__":
    unittest.main()
