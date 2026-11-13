"""Focused offline score-unit regression and counterfactual checks (stdlib)."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("scores.py")
SPEC = importlib.util.spec_from_file_location("thesis_v53_score_audit", SCRIPT)
scores = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scores)
ROOT = Path(__file__).resolve().parents[3]


class ScoreUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = scores.load_historical_modules(ROOT)
        cls.objective = cls.modules["objective_scoring"]
        cls.parameters = json.loads(
            (ROOT / scores.HISTORICAL / "inputs/method_parameters.json").read_text()
        )

    def test_decimal_MB_binary_MiB_fit_threshold_independently(self):
        row = {
            "cut_bytes": 10 * 2**20, "cut_mb_val": 10 * 2**20 / 1e6,
            "flops_left_abs": 42, "flops_right_abs": 58,
            "n_cut_tensors": 1, "strict_ok": True,
        }
        untouched = copy.deepcopy(row)
        historical = self.objective.accelerator_fit_metrics(row, stage1="hailo10", stage2="tensorrt")
        variant = self.objective.accelerator_fit_metrics(
            scores.binary_mib_input(row), stage1="hailo10", stage2="tensorrt"
        )
        # Exactly 10 MiB lies above 10 decimal MB but on the binary threshold.
        expected_old_cut_penalty = (10.48576 - 10) * 0.06
        self.assertAlmostEqual(historical["accelerator_fit_cut_penalty"], expected_old_cut_penalty)
        self.assertEqual(variant["accelerator_fit_cut_penalty"], 0)
        self.assertAlmostEqual(historical["accelerator_fit_score"] - variant["accelerator_fit_score"],
                               expected_old_cut_penalty)
        self.assertEqual(row, untouched)
        self.assertEqual(scores.binary_mib_input(row)["cut_bytes"], row["cut_bytes"])

    def test_stream_conversion_changes_hinge_without_changing_bottleneck(self):
        row = {
            "cut_bytes": 6 * 2**20, "cut_mb_val": 6 * 2**20 / 1e6,
            "flops_left_abs": 42, "flops_right_abs": 58, "n_cut_tensors": 1,
            "strict_ok": True, "pred_latency_total_ms": 8.0,
            "imbalance_val": 0.16,
        }
        old = self.objective.candidate_objective_metrics(
            row, stage1="hailo10", stage2="tensorrt", use_calibration=True
        )
        new = self.objective.candidate_objective_metrics(
            scores.binary_mib_input(row), stage1="hailo10", stage2="tensorrt", use_calibration=True
        )
        self.assertEqual(old["predicted_bottleneck_ms"], 8 * 0.58)
        self.assertEqual(new["predicted_bottleneck_ms"], old["predicted_bottleneck_ms"])
        self.assertEqual(old["accelerator_fit_score"], new["accelerator_fit_score"])
        # Independent affine difference at the 6-MiB hinge, with coefficients
        # held fixed. No measured or newly fitted coefficient enters this test.
        raw_difference = 0.12 * (6.291456 - 6.0)
        expected_old_minus_new = (
            -0.6536494472975787 * raw_difference + 0.2434774810758271 * (6.291456 - 6)
        )
        self.assertAlmostEqual(old["predicted_handover_ms_raw"] - new["predicted_handover_ms_raw"],
                               raw_difference)
        self.assertAlmostEqual(old["predicted_handover_ms"] - new["predicted_handover_ms"],
                               expected_old_minus_new)
        self.assertEqual(new["predicted_stream_fps"], 1000 / new["predicted_stream_cycle_ms"])
        self.assertNotEqual(old["predicted_stream_fps"], new["predicted_stream_fps"])

    def test_exact_ties_use_boundary_and_case_without_rounding(self):
        rows = [
            {"case_id": "b002", "boundary": 2},
            {"case_id": "b001z", "boundary": 1},
            {"case_id": "b001a", "boundary": 1},
        ]
        tied = {row["case_id"]: 1.0 for row in rows}
        self.assertEqual(scores.ranks(rows, tied), {"b001a": 1, "b001z": 2, "b002": 3})
        tied["b002"] = 1.0 - 1e-15
        self.assertEqual(scores.ranks(rows, tied)["b002"], 1)
        self.assertEqual(scores.ranks(rows, tied, descending=True)["b002"], 3)

    def test_full_universe_normalization_is_not_subset_normalization(self):
        rows = [
            {"case_id": "a", "boundary": 1, "cut_bytes": 1, "imbalance_val": .02, "n_cut_tensors": 1},
            {"case_id": "b", "boundary": 2, "cut_bytes": 10, "imbalance_val": 0, "n_cut_tensors": 1},
            {"case_id": "c", "boundary": 3, "cut_bytes": 1000000, "imbalance_val": 1, "n_cut_tensors": 1},
        ]
        function = self.modules["ranking_methods"].compute_ranking_predictions
        policy = dict(self.parameters["ranking_validation"], methods=["weighted_score"])
        full = {r["case_id"]: r["predicted_value"] for r in function(rows, [], policy)}
        subset = {r["case_id"]: r["predicted_value"] for r in function(rows[:2], [], policy)}
        self.assertLess(full["a"], full["b"])
        self.assertLess(subset["b"], subset["a"])
        converted = {r["case_id"]: r["predicted_value"]
                     for r in function([scores.binary_mib_input(r) for r in rows], [], policy)}
        self.assertEqual(full, converted)

    def test_changed_frozen_candidate_gate_is_rejected(self):
        rows = scores._read_csv(ROOT / scores.HISTORICAL / "inputs/method_graph_features.csv")
        model_rows = [row for row in rows if row["model_id"] == rows[0]["model_id"]]
        model_rows[0]["strict_ok"] = False
        with self.assertRaisesRegex(ValueError, "strict_ok"):
            scores.compare_model(model_rows, self.parameters, self.modules)

    def test_complete_frozen_regression_and_versioned_effects(self):
        protected = [
            ROOT / scores.HISTORICAL / "inputs/method_graph_features.csv",
            ROOT / scores.HISTORICAL / "inputs/method_candidate_scores.csv",
            ROOT / scores.HISTORICAL / "tables/method_groups.csv",
        ]
        before = {str(path): scores._sha(path.read_bytes()) for path in protected}
        with tempfile.TemporaryDirectory(prefix="thesis-v53-score-test-") as directory:
            output = Path(directory)
            result = scores.build(ROOT, output)
            audit = json.loads((output / "score_audit.json").read_text())
            self.assertEqual(result["counts"]["graph_candidates"], 2111)
            self.assertEqual(result["counts"]["frozen_method_scores_verified"], 14777)
            self.assertEqual(result["counts"]["published_subset_method_comparisons"], 252)
            self.assertEqual(result["counts"]["published_subset_selection_comparisons"], 186)
            self.assertEqual(result["counts"]["published_subset_insufficient_candidate_groups"], 66)
            for method in scores.CONTROLS:
                self.assertEqual(result["changes"][method]["score_changed_candidates"], 0)
                self.assertEqual(result["changes"][method]["rank_changed_candidates"], 0)
            self.assertEqual(result["changes"]["onnx_real_boundary_hardware_aware"],
                             {"score_changed_candidates": 912, "rank_changed_candidates": 1254,
                              "full_universe_top1_changes": 0, "published_subset_top1_changes": 0})
            self.assertEqual(result["changes"]["stored_predicted_stream_fps"],
                             {"score_changed_candidates": 2111, "rank_changed_candidates": 663,
                              "full_universe_top1_changes": 0, "published_subset_top1_changes": 7})
            changed = [r for r in audit["published_subset_selections"] if r["selected_case_changed"]]
            self.assertEqual({r["model_id"] for r in changed}, {"yolov7_paper"})
            self.assertEqual({r["cohort"] for r in changed}, {"augmented"})
            self.assertEqual({(r["historical_selected_case"], r["variant_selected_case"]) for r in changed},
                             {("b044", "b066")})
            for row in audit["published_subset_selections"]:
                if not row["selection_evaluated"]:
                    self.assertIsNone(row["historical_selected_case"])
                    self.assertIsNone(row["variant_selected_case"])
            # All numerical output files are independent of output location.
            first = {path.name: path.read_bytes() for path in output.iterdir()}
            second = output / "second"
            scores.build(ROOT, second)
            self.assertEqual(first, {path.name: path.read_bytes() for path in second.iterdir()})
        after = {str(path): scores._sha(path.read_bytes()) for path in protected}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
