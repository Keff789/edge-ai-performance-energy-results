"""One-time bounded metadata capture; normal replay uses operators.py only.

Read only the supplied archive's run_manifest/artifact_index, their exact seven
model entries and one manifest-indexed full graph per hash. No weights are
exported. ONNX shape inference is static graph analysis, not model inference.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import typing
from pathlib import Path

import operators

HISTORICAL = "d164aad6d7c7ef68c1b371c49a1fdea0a3b27dd7"
PUBLISHED = "db729b9fcde00e4bcadf9200d43282977d7bf1cc"
MODULE = "onnx_splitpoint_tool/metrics.py"
UTILS = "onnx_splitpoint_tool/onnx_utils.py"
EXPECTED_METRICS = "1de2623871bfcd2d7c3d5472141ead4cbddddb4b903481a9adbc07bd578cd735"


def digest(b):
    return hashlib.sha256(b).hexdigest()


def git_bytes(root, rev, path):
    return subprocess.check_output(["git", "-C", str(root), "show", f"{rev}:{path}"])


def selected_functions(text, names):
    tree = ast.parse(text)
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]


def capture(repo_root, archive_root, tool_root, identity_manifest=None):
    import onnx
    out = repo_root / operators.INPUT
    out.mkdir(parents=True, exist_ok=True)
    run_path, index_path = archive_root / "run_manifest.json", archive_root / "artifact_index.json"
    run_bytes, index_bytes = run_path.read_bytes(), index_path.read_bytes()
    run, index = json.loads(run_bytes), json.loads(index_bytes)["artifacts"]
    metric_bytes = git_bytes(tool_root, HISTORICAL, MODULE)
    current_bytes = git_bytes(tool_root, PUBLISHED, MODULE)
    assert digest(metric_bytes) == digest(current_bytes) == EXPECTED_METRICS
    utils_bytes = git_bytes(tool_root, HISTORICAL, UTILS)
    text = metric_bytes.decode()
    names = {n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and
             (n.name.startswith("flops_") or n.name in {"_prod", "_matmul_dims", "_get_weight_dims", "_shape_from_any", "per_node_flops"})}
    funcs = selected_functions(text, names)
    ufuncs = selected_functions(utils_bytes.decode(), {"_get_attr", "shape_from_vi", "numel_from_shape"})
    namespace = dict(vars(typing), onnx=onnx)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + ufuncs + funcs, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "<bound metrics functions>", "exec"), namespace)
    example_node = onnx.helper.make_node("ConvTranspose", ["x", "w"], ["y"], strides=[2, 2])
    example_input = onnx.helper.make_tensor_value_info("x", onnx.TensorProto.FLOAT, [1, 1, 2, 2])
    example_output = onnx.helper.make_tensor_value_info("y", onnx.TensorProto.FLOAT, [1, 1, 4, 4])
    example_weight = onnx.TensorProto(name="w", data_type=onnx.TensorProto.FLOAT, dims=[1, 1, 2, 2])
    example_model = onnx.helper.make_model(onnx.helper.make_graph(
        [example_node], "counterexample_metadata_only", [example_input], [example_output], [example_weight]))
    original_counterexample = namespace["per_node_flops"](example_model, {"x": example_input, "y": example_output})[0][3]
    assert original_counterexample == 64
    snippet = "\n\n".join(ast.get_source_segment(text, f) for f in funcs) + "\n"
    (out / "historical_metrics_counting.py.txt").write_text(snippet)
    (out / "historical_onnx_shape_helpers.py.txt").write_text(
        "\n\n".join(ast.get_source_segment(utils_bytes.decode(), f) for f in ufuncs) + "\n")
    (out / "LICENSE.tool").write_bytes(git_bytes(tool_root, HISTORICAL, "LICENSE"))
    originals = [
        {"source": "canonical_archive:run_manifest.json", "sha256": digest(run_bytes), "role": "original_campaign_model_identity_and_execution_metadata"},
        {"source": "canonical_archive:artifact_index.json", "sha256": digest(index_bytes), "role": "original_manifest_paths_and_artifact_hashes"},
    ]
    graphs, selected_index, model_bindings = [], [], []

    def verified(rel, expected=None):
        p = archive_root / rel
        if not p.resolve().is_relative_to(archive_root.resolve()):
            raise ValueError("Manifest path escapes canonical archive")
        records = [e for e in index if e.get("path") == rel]
        if not records:
            raise ValueError(f"Path has no original artifact-index binding: {rel}")
        data = p.read_bytes()
        actual = digest(data)
        hashes = {e.get("sha256", "").removeprefix("sha256:") for e in records}
        if actual not in hashes or (expected and expected != actual):
            raise ValueError(f"Original artifact hash mismatch: {rel}")
        selected_index.extend({k: e.get(k) for k in ("path", "sha256", "size_bytes", "producer_stage", "created_at")} for e in records if e.get("sha256", "").removeprefix("sha256:") == actual)
        originals.append({"source": "canonical_archive:" + rel, "sha256": actual, "role": "graph_or_graph_analysis_source"})
        return data, actual

    for model, identity in sorted(run["models"].items()):
        expected = identity["model_sha256"].removeprefix("sha256:")
        graph_records = [e for e in index if e.get("sha256", "").removeprefix("sha256:") == expected and e.get("path", "").endswith(".onnx")]
        preferred = f"models/{model}/benchmark_set/legacy_suite/models/{model}.onnx"
        chosen = next((e for e in graph_records if e["path"] == preferred), None)
        if chosen is None:
            raise ValueError(f"Expected exact full-graph archive entry absent: {model}")
        raw_bytes, graph_sha = verified(chosen["path"], expected)
        analysis_rel = f"models/{model}/analysis/analysis.json"
        ranking_rel = f"models/{model}/analysis/candidate_ranking.json"
        analysis_bytes, analysis_sha = verified(analysis_rel)
        rank_bytes, rank_sha = verified(ranking_rel)
        analysis, ranking = json.loads(analysis_bytes), json.loads(rank_bytes)
        raw = onnx.load_model_from_string(raw_bytes)
        raw_vimap = {vi.name: vi for vi in list(raw.graph.input) + list(raw.graph.value_info) + list(raw.graph.output)}
        # Every supplied original graph has concrete image inputs. The additional
        # historical dynamic-input/default/custom-op branches are not invoked.
        for vi in raw.graph.input:
            shape = namespace["shape_from_vi"](vi)
            if shape is None or any(d is None or d <= 0 for d in shape):
                raise ValueError(f"Dynamic input needs separately bound inference policy: {model}/{vi.name}")
        inferred = onnx.shape_inference.infer_shapes(raw, strict_mode=False)
        vimap = {vi.name: vi for vi in list(inferred.graph.input) + list(inferred.graph.value_info) + list(inferred.graph.output)}
        init = {x.name: list(x.dims) for x in inferred.graph.initializer}
        records = namespace["per_node_flops"](inferred, vimap)
        nodes = []
        for i, n in enumerate(inferred.graph.node):
            attrs = {}
            for a in n.attribute:
                value = namespace["_get_attr"](n, a.name)
                if value is not None:
                    attrs[a.name] = value
                elif a.type in (onnx.AttributeProto.GRAPH, onnx.AttributeProto.GRAPHS):
                    raise ValueError("Nested subgraphs require explicit recursive inventory")
            nodes.append({
                "index": i, "name": n.name, "op_type": n.op_type, "domain": n.domain,
                "input_names": list(n.input),
                "input_shapes": [namespace["shape_from_vi"](vimap.get(v)) for v in n.input],
                "initializer_shapes": [init.get(v) for v in n.input],
                "output_shapes": [namespace["shape_from_vi"](vimap.get(v)) for v in n.output],
                "raw_output_shapes": [namespace["shape_from_vi"](raw_vimap.get(v)) for v in n.output],
                "attributes": attrs,
            })
        costs = [r[3] for r in records]
        for node, original_cost in zip(nodes, costs):
            if operators.historical_proxy(node) != original_cost:
                raise AssertionError(f"Projection differs from bound original function: {model}/{node['index']}")
        assert len(nodes) == analysis["node_count"]
        keys = ("case_id", "boundary", "flops_left_abs", "flops_right_abs", "total_flops", "cut_bytes")
        candidates = [{k: c[k] for k in keys} for c in ranking["candidates"]]
        graphs.append({
            "model_id": model, "graph_sha256": graph_sha,
            "source_binding": {"graph": "canonical_archive:" + chosen["path"],
                               "model_identity_pointer": "/models/" + model,
                               "analysis_sha256": analysis_sha, "ranking_sha256": rank_sha},
            "opsets": [{"domain": o.domain, "version": o.version} for o in raw.opset_import],
            "nodes": nodes, "original_function_proxy_by_node": costs,
            "historical_candidates": candidates,
        })
        model_bindings.append({"model_id": model, "model_sha256": expected, "model_size_bytes": identity["model_size_bytes"],
                               "archive_graph_path": chosen["path"], "analysis_path": analysis_rel,
                               "ranking_path": ranking_rel})
        print(model, "nodes", len(nodes), "ConvTranspose", sum(n["op_type"] == "ConvTranspose" for n in nodes),
              "proxy", sum(costs), "stored", sorted({c["total_flops"] for c in candidates}), flush=True)

    precision_path = Path("results/supplementary-studies/thesis-v49-confirmation-20261019/inputs/metrology/version_and_precision_bindings.json")
    precision = json.loads((repo_root / precision_path).read_text())
    refs = []
    for e in precision["entries"]:
        recipe = e["stage_precision"].get("compiler_recipe") or {}
        if recipe.get("source_onnx_sha256"):
            refs.append({
                "uid": e["uid"], "graph_sha256": recipe["source_onnx_sha256"],
                "graph_role": "tensorrt_compile_source_onnx_for_selected_deployment",
                "source": str(precision_path),
                "source_pointer": "/entries/" + str(precision["entries"].index(e)) + "/stage_precision/compiler_recipe",
                "inspection_status": "referenced_not_inspected",
                "convtranspose_count": None,
                "reason": "Only the selected source-ONNX hash is public; no claim about transformed/split graph operators follows from the full graph inventory.",
            })
    confirmation_bindings = []
    if identity_manifest is not None:
        identity_bytes = identity_manifest.read_bytes()
        identity_hash = digest(identity_bytes)
        expected_identity = "0a41bcb7c606fd398996061f7fb0651c8b81c735541db97197b31a6d5efc58f3"
        if identity_hash != expected_identity:
            raise ValueError("Confirmation identity manifest differs from the bound archive member")
        identity_source = "archive:thesis_v49_hardware_confirmation_energy_supplement_20261019.tar.gz/thesis_v49_hardware_confirmation_20261018/evidence/identity_runtime_manifest.json"
        originals.append({"source": identity_source, "sha256": identity_hash,
                          "role": "selected_deployment_full_and_part_graph_identity",
                          "archive_sha256": "edbd618ad91ef658a866c73c61defd00389e3ca9218c33ea22d87a6ec3721915"})
        full_hashes = {g["graph_sha256"] for g in graphs}
        refs = []
        for i, entry in enumerate(json.loads(identity_bytes)["entries"]):
            local = entry.get("current_local_source_model", {})
            confirmation_bindings.append({
                "uid": entry["uid"], "model_id": entry["model"],
                "recorded_local_source_sha256": local.get("sha256"),
                "original_quality_model_sha256": local.get("original_quality_model_sha256"),
                "matches_original_quality_model_sha256": local.get("matches_original_quality_model_sha256"),
                "full_graph_hash_inspected_in_this_audit": local.get("sha256") in full_hashes,
                "source": identity_source, "source_sha256": identity_hash,
                "source_pointer": f"/entries/{i}/current_local_source_model",
            })
            for role, artifact in entry.get("artifacts", {}).items():
                if not isinstance(artifact, dict) or not artifact.get("sha256"):
                    continue
                if not (artifact.get("path", "").endswith(".onnx") or "onnx" in role):
                    continue
                same_full = artifact["sha256"] in full_hashes
                refs.append({
                    "uid": entry["uid"], "graph_sha256": artifact["sha256"],
                    "graph_role": role, "source": identity_source,
                    "source_sha256": identity_hash, "source_pointer": f"/entries/{i}/artifacts/{role}",
                    "inspection_status": "same_hash_as_inspected_full_graph" if same_full else "referenced_not_inspected",
                    "convtranspose_count": 0 if same_full else None,
                    "reason": "Exact SHA equals inspected full graph." if same_full else "Distinct source/build part-graph hash. Its operators are not inferred from the original full graph; only this manifest reference was inspected.",
                })
    graph_projection = {
        "schema": "thesis-v53/operator-shape-projection-v1", "graphs": graphs, "subgraph_references": refs,
        "confirmation_model_bindings": confirmation_bindings,
        "shape_inference": {
            "onnx_version": onnx.__version__, "call": "onnx.shape_inference.infer_shapes(model, strict_mode=False)",
            "all_original_inputs_static": True, "weights_exported": False, "original_graphs_modified": False,
            "interpretation": "New offline metadata projection. It is not a historical shape-inference execution receipt. Raw and inferred output shape gaps are reported separately.",
        },
    }
    (out / "graphs.json").write_text(json.dumps(graph_projection, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    # Keep only the necessary run-manifest fields, never the full environment.
    runtime = []
    for role in ("environment", "current_environment"):
        env = run[role]
        tb = env["tool_build"]
        runtime.append({"role": role, "tool_version": env["tool_version"],
                        "critical_module_names": sorted(tb["critical_module_sha256"]),
                        "metrics_module_individually_bound": "metrics.py" in tb["critical_module_sha256"],
                        "package_content_sha256": tb["package_content_sha256"],
                        "distribution_record_status": tb["distribution_record_status"]})
    operators.dump(out / "archive_bindings.json", {"models": model_bindings, "selected_artifact_index_entries": selected_index, "runtime_build_projection": runtime})
    function = next(f for f in funcs if f.name == "flops_convtranspose")
    node_function = next(f for f in funcs if f.name == "per_node_flops")
    repo_inputs = [operators.METHOD_INPUT, operators.CASES_INPUT, precision_path,
                   Path("results/supplementary-studies/thesis20-ranking-20261005/inputs/method_code_provenance.json")]
    operators.dump(out / "source_bindings.json", {
        "schema": "thesis-v53/operator-source-bindings-v1",
        "original_sources": originals,
        "repository_inputs": [{"path": str(p), "sha256": operators.sha(repo_root / p), "role": "existing_frozen_population_or_method_input"} for p in repo_inputs],
        "counting_source": {
            "repository": "https://github.com/Keff789/ONNX-Splitpoint-Tool",
            "historical_definition_commit": HISTORICAL, "current_published_commit": PUBLISHED,
            "module": MODULE, "historical_module_sha256": digest(metric_bytes),
            "current_published_module_sha256": digest(current_bytes),
            "module_bytes_equal": metric_bytes == current_bytes,
            "historical_definition_binding": "The preserved method_code_provenance.json binds d164aad as the methods-definition release. metrics.py is read from that exact Git object; this is not proof of process import.",
            "historical_execution_binding": "not_individually_recorded_in_inspected_campaign_critical_module_lists",
            "convtranspose_function_sha256": digest(ast.get_source_segment(text, function).encode()),
            "convtranspose_source_lines": [function.lineno, function.end_lineno],
            "per_node_function_sha256": digest(ast.get_source_segment(text, node_function).encode()),
            "per_node_source_lines": [node_function.lineno, node_function.end_lineno],
            "original_source_counterexample_proxy": original_counterexample,
            "shape_helpers_module_sha256": digest(utils_bytes),
            "current_published_shape_helpers_sha256": digest(git_bytes(tool_root, PUBLISHED, UTILS)),
            "dirty_checkout_used_for_execution": False,
            "local_checkout_head_observed": subprocess.check_output(["git", "-C", str(tool_root), "rev-parse", "HEAD"], text=True).strip(),
            "local_metrics_worktree_sha256_observed": operators.sha(tool_root / MODULE),
            "local_checkout_observation_scope": "Only source observation; foreign dirty files were neither edited nor imported.",
        },
        "compact_files": [{"path": p.name, "sha256": operators.sha(p)} for p in sorted(out.iterdir()) if p.name != "source_bindings.json" and p.is_file()],
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--tool-repo", type=Path, required=True)
    parser.add_argument("--identity-manifest", type=Path, help="Previously verified exact v49 archive member; no archive search/download is performed.")
    args = parser.parse_args()
    capture(args.repo_root.resolve(), args.archive_root.resolve(), args.tool_repo.resolve(), args.identity_manifest)
