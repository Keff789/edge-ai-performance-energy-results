"""Offline operator audit from small, hash-bound graph projections.

This module uses the standard library only. Capture of original ONNX metadata is
separate; no model, runtime, hardware, network, or inference is needed to replay.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path

INPUT = Path("results/supplementary-studies/thesis-v53-offline-review-20261020/inputs/operators")
METHOD_INPUT = Path("results/supplementary-studies/thesis20-ranking-20261005/inputs/method_graph_features.csv")
CASES_INPUT = Path("results/split-inference/data/inputs/cases.json")
SUPPORTED = {
    "Conv", "ConvInteger", "QLinearConv", "ConvTranspose", "MatMul",
    "MatMulInteger", "QLinearMatMul", "Gemm", "BatchNormalization",
    "Relu", "LeakyRelu", "Sigmoid", "Tanh", "Softsign", "Softplus", "Gelu",
    "Clip", "Resize", "Upsample", "Interpolate", "Add", "Sub", "Mul", "Div",
}
ACTIVATIONS = {"Relu", "LeakyRelu", "Sigmoid", "Tanh", "Softsign", "Softplus", "Gelu", "Clip"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def numel(shape):
    """The historical helper substitutes one for missing/nonpositive dimensions."""
    return math.prod(d if d is not None and d > 0 else 1 for d in shape) if shape else 0


def missing_input_shape(node):
    return any(
        shape is None or any(d is None or d <= 0 for d in shape)
        for name, shape in zip(node["input_names"], [
            s if s is not None else w
            for s, w in zip(node["input_shapes"], node["initializer_shapes"])
        ]) if name
    )


def historical_proxy(node):
    """Faithful scalar projection of the frozen metrics.py default-count path.

    Capture verifies every result against the original functions, including their
    historical Gemm/transB and MatMul fallback behavior. These are proxy units.
    """
    op = node["op_type"]
    inputs = node["input_shapes"]
    initializers = node["initializer_shapes"]
    output = node["output_shapes"][0] if node["output_shapes"] else None
    out = numel(output)
    names = node["input_names"]

    def shape(i):
        return inputs[i] or initializers[i]

    if op in {"Conv", "ConvInteger", "QLinearConv", "ConvTranspose"}:
        wi = 3 if op == "QLinearConv" else 1
        w = initializers[wi] if len(initializers) > wi else None
        cost = 0
        if w and len(w) == 4 and output and len(output) == 4:
            n, _, h, width = [int(d or 1) for d in output]
            cost = n * h * width * math.prod(w)
        bi = 8 if op == "QLinearConv" else 2
        if op != "ConvInteger" and len(names) > bi and names[bi]:
            cost += out
        return cost
    if op in {"MatMul", "MatMulInteger", "QLinearMatMul", "Gemm"}:
        wi = 3 if op == "QLinearMatMul" else 1
        if len(inputs) <= wi:
            return 0
        a, b = shape(0), shape(wi)
        cost = 0
        if a and b and len(a) >= 2 and len(b) >= 2:
            aa, bb = ([int(d or 1) for d in s] for s in (a, b))
            cost = max(math.prod(aa[:-2]), math.prod(bb[:-2])) * aa[-2] * bb[-1] * min(aa[-1], bb[-2])
        elif op in {"MatMul", "MatMulInteger"} and output and b and len(b) >= 2:
            oo = [int(d or 1) for d in output]
            cost = (math.prod(oo[:-2]) if len(oo) >= 2 else 1) * (oo[-2] if len(oo) >= 2 else 1) * oo[-1] * int(b[-2] if b[-2] is not None else 1)
        if op == "Gemm" and len(names) > 2 and names[2]:
            cost += out
        return cost
    if op == "BatchNormalization":
        return 4 * out
    if op in ACTIVATIONS or op in {"Add", "Sub", "Mul", "Div"}:
        return out
    if op in {"Resize", "Upsample", "Interpolate"}:
        mode = str(node["attributes"].get("mode", "")).lower()
        return (8 if mode in {"linear", "bilinear", "trilinear"} else 16 if mode in {"cubic", "bicubic"} else 1) * out
    return 0


def enumerate_products(input_shape, weight_shape, *, groups=1, strides=(1, 1),
                       pads=(0, 0, 0, 0), dilations=(1, 1), output_padding=(0, 0)):
    """Enumerate direct input/weight products for small static 2D cases.

    Coordinates outside the declared output are cropped. This is an independent
    mathematical counterexample, not a replacement runtime or graph cost model.
    """
    n, cin, hi, wi = input_shape
    wcin, cout_per_group, kh, kw = weight_shape
    if cin != wcin or groups < 1 or cin % groups:
        raise ValueError("Inconsistent channels/groups")
    if min(*input_shape, *weight_shape, *strides, *dilations) < 1 or min(*pads, *output_padding) < 0:
        raise ValueError("Expected positive dimensions/strides and nonnegative pads")
    ho = (hi - 1) * strides[0] - pads[0] - pads[2] + dilations[0] * (kh - 1) + output_padding[0] + 1
    wo = (wi - 1) * strides[1] - pads[1] - pads[3] + dilations[1] * (kw - 1) + output_padding[1] + 1
    if min(ho, wo) < 1:
        raise ValueError("Empty output")
    products = []
    for batch, ci, iy, ix, co_local, ky, kx in itertools.product(
        range(n), range(cin), range(hi), range(wi), range(cout_per_group), range(kh), range(kw)
    ):
        oy = iy * strides[0] - pads[0] + ky * dilations[0]
        ox = ix * strides[1] - pads[1] + kx * dilations[1]
        if 0 <= oy < ho and 0 <= ox < wo:
            group = ci // (cin // groups)
            products.append({
                "input": [batch, ci, iy, ix],
                "weight": [ci, co_local, ky, kx],
                "output": [batch, group * cout_per_group + co_local, oy, ox],
            })
    return [n, groups * cout_per_group, ho, wo], products


def counterexample():
    inp, weight = [1, 1, 2, 2], [1, 1, 2, 2]
    out, products = enumerate_products(inp, weight, strides=(2, 2))
    proxy = out[0] * out[2] * out[3] * math.prod(weight)
    return {
        "input_shape": inp, "weight_shape": weight, "output_shape": out,
        "groups": 1, "strides": [2, 2], "pads": [0, 0, 0, 0], "dilations": [1, 1],
        "bias": False, "direct_products": len(products), "historical_dense_proxy": proxy,
        "proxy_to_direct_ratio": proxy / len(products), "enumerated_products": products,
        "device_operations": None,
        "device_operations_reason": "No inference or backend kernel execution was performed.",
    }


def build(repo_root: Path, output: Path):
    repo_root, output = Path(repo_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    base = repo_root / INPUT
    bindings = json.loads((base / "source_bindings.json").read_text())
    for entry in bindings["compact_files"]:
        actual = sha(base / entry["path"])
        if actual != entry["sha256"]:
            raise ValueError(f"Operator input hash mismatch: {entry['path']}")
    for entry in bindings["repository_inputs"]:
        if sha(repo_root / entry["path"]) != entry["sha256"]:
            raise ValueError(f"Repository input hash mismatch: {entry['path']}")
    projection = json.loads((base / "graphs.json").read_text())
    with (repo_root / METHOD_INPUT).open(newline="") as f:
        methods = list(csv.DictReader(f))
    cases = json.loads((repo_root / CASES_INPUT).read_text())
    inventory, reports = [], []
    for graph in projection["graphs"]:
        nodes = graph["nodes"]
        counts = Counter(n["op_type"] for n in nodes)
        costs = [historical_proxy(n) for n in nodes]
        assert costs == graph["original_function_proxy_by_node"]
        total = sum(costs)
        unknown_raw = sum(any(s is None or any(d is None or d <= 0 for d in s) for s in n["raw_output_shapes"]) for n in nodes)
        unknown_after = sum(any(s is None or any(d is None or d <= 0 for d in s) for s in n["output_shapes"]) for n in nodes)
        supported_count = sum(n["op_type"] in SUPPORTED for n in nodes)
        fallback_count = len(nodes) - supported_count
        selected = [x for x in cases if x["model_id"] == graph["model_id"]]
        bound = [x for x in selected if x.get("model_sha256") == graph["graph_sha256"]]
        unknown = [x["uid"] for x in selected if not x.get("model_sha256")]
        other = [x["uid"] for x in selected if x.get("model_sha256") not in (None, graph["graph_sha256"])]
        historical = [x for x in methods if x["model_id"] == graph["model_id"]]
        original = {x["case_id"]: x for x in graph["historical_candidates"]}
        if len(original) != len(historical):
            raise ValueError("Historical candidate universe changed")
        mismatches = []
        for row in historical:
            source = original[row["case_id"]]
            for key in ("boundary", "flops_left_abs", "flops_right_abs", "total_flops", "cut_bytes"):
                if float(row[key]) != float(source[key]):
                    mismatches.append({"case_id": row["case_id"], "field": key})
        if mismatches:
            raise ValueError(f"Historical graph feature binding failed: {graph['model_id']}")
        transpose = [n for n in nodes if n["op_type"] == "ConvTranspose"]
        for op, count in sorted(counts.items()):
            subset = [(n, costs[i]) for i, n in enumerate(nodes) if n["op_type"] == op]
            inventory.append({
                "model_id": graph["model_id"], "graph_role": "canonical_full_onnx",
                "graph_sha256": graph["graph_sha256"], "graph_verified": True,
                "op_type": op, "node_count": count, "all_graph_nodes_denominator": len(nodes),
                "node_fraction": count / len(nodes),
                "cost_rule": "implemented_proxy" if op in SUPPORTED else "zero_unimplemented_fallback",
                "zero_cost_node_count": sum(c == 0 for _, c in subset),
                "historical_proxy_units": sum(c for _, c in subset),
                "missing_or_symbolic_output_before_shape_inference": sum(any(s is None or any(d is None or d <= 0 for d in s) for s in n["raw_output_shapes"]) for n, _ in subset),
                "missing_or_symbolic_output_after_shape_inference": sum(any(s is None or any(d is None or d <= 0 for d in s) for s in n["output_shapes"]) for n, _ in subset),
                "missing_or_symbolic_input_after_shape_inference": sum(missing_input_shape(n) for n, _ in subset),
            })
        reports.append({
            "model_id": graph["model_id"], "graph_sha256": graph["graph_sha256"],
            "graph_role": "canonical_full_onnx", "source_binding": graph["source_binding"],
            "node_count": len(nodes), "operator_counts": dict(sorted(counts.items())),
            "convtranspose_nodes": transpose, "convtranspose_count": len(transpose),
            "implemented_rule_nodes": supported_count,
            "zero_unimplemented_fallback_nodes": fallback_count,
            "zero_cost_nodes": sum(c == 0 for c in costs),
            "node_coverage_denominator": len(nodes),
            "implemented_rule_node_fraction": supported_count / len(nodes),
            "missing_or_symbolic_output_nodes_before_inference": unknown_raw,
            "missing_or_symbolic_output_nodes_after_inference": unknown_after,
            "missing_or_symbolic_input_nodes_after_inference": sum(missing_input_shape(n) for n in nodes),
            "recomputed_proxy_total": total,
            "stored_historical_proxy_totals": sorted({float(x["total_flops"]) for x in historical}),
            "recomputed_total_matches_all_stored_totals": all(total == float(x["total_flops"]) for x in historical),
            "historical_candidate_count": len(historical),
            "historical_candidate_fields_match_archive": not mismatches,
            "later_deployment_full_graph_sha_bound_uid_count": len(bound),
            "later_deployment_unbound_uids": unknown,
            "later_deployment_other_graph_uids": other,
            "convtranspose_change_effect": {
                "status": "unchanged_by_absence" if not transpose else "requires_separate_rank_replay",
                "total_proxy_delta": 0 if not transpose else None,
                "prefix_suffix_fraction_delta": 0 if not transpose else None,
                "score_rank_changes": 0 if not transpose else None,
                "basis": "No node is dispatched to ConvTranspose; changing only that branch changes no node cost, prefix, normalization input, candidate score or tie key." if not transpose else "Do not infer ranking changes without the full same-candidate replay.",
                "scope": "Only the exact verified full-graph hash and a change confined to ConvTranspose.",
            },
        })
    with (output / "operator_inventory.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(inventory[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory)
    example = counterexample()
    if (example["direct_products"], example["historical_dense_proxy"]) != (16, 64):
        raise AssertionError("Counterexample failed")
    if bindings["counting_source"]["original_source_counterexample_proxy"] != example["historical_dense_proxy"]:
        raise AssertionError("Counterexample differs from captured original code evaluation")
    audit = {
        "schema": "thesis-v53/operator-audit-v1",
        "counterexample": example, "counting_source": bindings["counting_source"],
        "formula": {
            "historical_dense_proxy": "N * H_out * W_out * C_in * (C_out / group) * kH * kW",
            "weight_layout": "[C_in, C_out/group, kH, kW]",
            "shape_requirement": "4D initializer weights and first output shape; otherwise the multiplication term is zero. Missing dimensions in a present output shape are replaced by one.",
            "groups": "Grouping is implicit in weight dimensions; group attribute is not independently inspected.",
            "stride_padding_dilation": "Not read by the product-count function; they can influence the inferred output shape, but sparse/cropped contribution counts are not enumerated.",
            "bias": "per_node_flops adds first-output numel when input[2] is nonempty; no bias term in flops_convtranspose itself.",
            "units": "Historical mixed proxy units: one dense product accumulation unit, plus separate scalar bias/elementwise units. Not exact arithmetic instructions or measured device FLOPs.",
        },
        "graphs": reports,
        "coverage_interpretation": "All fractions count graph nodes, never device runtime or energy. Implemented means a rule exists, not exact operator arithmetic.",
        "shape_interpretation": projection["shape_inference"],
        "subgraph_references": projection["subgraph_references"],
        "confirmation_model_bindings": projection.get("confirmation_model_bindings", []),
        "subgraph_scope": "Referenced deployment part graphs and compiler-adjusted graphs are not inferred from the original full graph. Their uninspected status is explicit.",
        "limitations": [
            "Historical release/definition provenance is distinct from proof of the source bytes imported by a particular historical process.",
            "The selected historical runtime critical-module lists omit onnx_splitpoint_tool/metrics.py; no exact process-to-metrics binding was found in these inspected manifests.",
            f"{sum(len(r['later_deployment_unbound_uids']) for r in reports)} current population rows lack model_sha256; model names do not close this identity gap.",
            "No execution-cost or backend-fusion claim follows from this graph inventory.",
            "The count replay uses the captured ONNX 1.21.0 static shape projection, not a historical shape-inference execution receipt.",
        ],
        "measured_values_modified": False,
        "graph_count": len(reports), "inspected_full_graph_nodes": sum(r["node_count"] for r in reports),
        "inspected_convtranspose_count": sum(r["convtranspose_count"] for r in reports),
        "historical_candidates_bound": sum(r["historical_candidate_count"] for r in reports),
        "later_deployment_full_graph_bound_rows": sum(r["later_deployment_full_graph_sha_bound_uid_count"] for r in reports),
        "later_deployment_full_graph_unbound_rows": sum(len(r["later_deployment_unbound_uids"]) for r in reports),
    }
    dump(output / "convtranspose_audit.json", audit)
    return {
        "status": "completed_with_limits",
        "graph_count": audit["graph_count"],
        "inspected_convtranspose_count": audit["inspected_convtranspose_count"],
        "counterexample": {"direct_products": 16, "historical_dense_proxy": 64},
        "outputs": ["operator_inventory.csv", "convtranspose_audit.json"],
        "evidence": ["operator_inventory.csv", "convtranspose_audit.json"],
        "limitations": audit["limitations"],
    }
