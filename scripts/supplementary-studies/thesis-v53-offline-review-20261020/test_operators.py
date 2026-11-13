"""Targeted algebra, grouping/cropping and frozen-source projection checks."""
import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("operators", HERE / "operators.py")
operators = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operators)
REPO = HERE.parents[2]


class OperatorAuditTests(unittest.TestCase):
    def test_counterexample_independent_coordinates(self):
        example = operators.counterexample()
        self.assertEqual(example["direct_products"], 16)
        self.assertEqual(example["historical_dense_proxy"], 64)
        self.assertEqual(Counter(tuple(p["input"]) for p in example["enumerated_products"]),
                         {(0, 0, 0, 0): 4, (0, 0, 0, 1): 4, (0, 0, 1, 0): 4, (0, 0, 1, 1): 4})
        self.assertEqual({tuple(p["output"][2:]) for p in example["enumerated_products"]},
                         {(y, x) for y in range(4) for x in range(4)})
        self.assertIsNone(example["device_operations"])

    def test_groups_keep_channels_separate(self):
        output, products = operators.enumerate_products([1, 4, 1, 1], [4, 3, 2, 2], groups=2)
        self.assertEqual(output, [1, 6, 2, 2])
        self.assertEqual(len(products), 48)
        self.assertTrue(all(p["input"][1] // 2 == p["output"][1] // 3 for p in products))
        with self.assertRaises(ValueError):
            operators.enumerate_products([1, 3, 1, 1], [3, 1, 2, 2], groups=2)

    def test_crop_excludes_outside_output(self):
        output, products = operators.enumerate_products([1, 1, 2, 2], [1, 1, 2, 2],
                                                       strides=(2, 2), pads=(1, 1, 1, 1))
        self.assertEqual(output, [1, 1, 2, 2])
        self.assertEqual(len(products), 4)
        self.assertEqual({tuple(p["weight"][2:]) for p in products}, {(0, 0), (0, 1), (1, 0), (1, 1)})

    def test_dilation_counts_sparse_direct_products(self):
        output, products = operators.enumerate_products([1, 1, 1, 1], [1, 1, 2, 2], dilations=(2, 2))
        self.assertEqual(output, [1, 1, 3, 3])
        self.assertEqual(len(products), 4)
        self.assertEqual({tuple(p["output"][2:]) for p in products}, {(0, 0), (0, 2), (2, 0), (2, 2)})

    def test_bound_projection_matches_original_function_and_stored_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = operators.build(REPO, Path(tmp))
            audit = json.loads((Path(tmp) / "convtranspose_audit.json").read_text())
        self.assertEqual(result["graph_count"], 7)
        self.assertEqual(audit["historical_candidates_bound"], 2111)
        self.assertEqual(audit["inspected_convtranspose_count"], 0)
        self.assertEqual(audit["later_deployment_full_graph_bound_rows"], 437)
        self.assertEqual(audit["later_deployment_full_graph_unbound_rows"], 13)
        self.assertTrue(all(g["recomputed_total_matches_all_stored_totals"] for g in audit["graphs"]))
        self.assertEqual(audit["counting_source"]["historical_module_sha256"],
                         audit["counting_source"]["current_published_module_sha256"])
        self.assertNotIn("onnx", sys.modules)

    def test_tampered_projection_rejected_before_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / operators.INPUT
            base.mkdir(parents=True)
            (base / "graphs.json").write_text("{}\n")
            operators.dump(base / "source_bindings.json", {
                "compact_files": [{"path": "graphs.json", "sha256": "0" * 64}],
                "repository_inputs": [],
            })
            with self.assertRaisesRegex(ValueError, "Operator input hash mismatch"):
                operators.build(root, root / "output")


if __name__ == "__main__":
    unittest.main()
