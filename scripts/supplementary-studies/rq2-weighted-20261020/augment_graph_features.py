#!/usr/bin/env python3
"""Extend the bound analytic operation proxy without modifying its source export.

This declares a new analysis convention. It does not recover missing historical
counter rules and does not estimate actual backend instructions or execution time.
"""
from __future__ import annotations

import argparse
import copy
import csv
from fractions import Fraction
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import shutil

VERSION = 'analytic-operation-proxy-r29-extended-v1'
SEMANTICS = {
    'Softmax': 'https://onnx.ai/onnx/operators/onnx__Softmax.html#softmax-13',
    'ReduceMax': 'https://onnx.ai/onnx/operators/onnx__ReduceMax.html#reducemax-18',
    'TopK': 'https://onnx.ai/onnx/operators/onnx__TopK.html#topk-11',
    'Mod': 'https://onnx.ai/onnx/operators/onnx__Mod.html#mod-13',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def shape(tensors, name):
    value = tensors[name].get('shape')
    if value is None or any(not isinstance(x, int) or isinstance(x, bool) or x <= 0 for x in value):
        raise ValueError('Missing, dynamic, or empty shape: ' + name)
    return value


def axis_index(axis, rank):
    if not isinstance(axis, int) or not -rank <= axis < rank:
        raise ValueError('Invalid axis')
    return axis % rank


def infer_reduction_axes(source, output, keepdims, count=None):
    """Infer only when captured shapes permit precisely one axes subset."""
    possibilities = []
    for length in range(len(source) + 1):
        if count is not None and length != count:
            continue
        for axes in itertools.combinations(range(len(source)), length):
            expected = ([1 if i in axes else d for i, d in enumerate(source)] if keepdims
                        else [d for i, d in enumerate(source) if i not in axes])
            if expected == output:
                possibilities.append(list(axes))
    if len(possibilities) != 1:
        raise ValueError('Reduction axes not uniquely implied by shapes: ' + repr(possibilities))
    return possibilities[0]


def extension_count(node, tensors, opset):
    op, attrs = node['op_type'], node['attributes']
    if node.get('domain', '') not in ('', 'ai.onnx') or opset != 18:
        raise ValueError('Only captured standard-domain opset-18 graphs are supported')
    inputs, outputs = node['input_names'], node['output_names']
    source, output = shape(tensors, inputs[0]), shape(tensors, outputs[0])
    elements = math.prod(output)
    detail = {'input_shape': source, 'output_shape': output, 'output_elements': elements,
              'proxy_version': VERSION, 'semantic_reference': SEMANTICS[op],
              'count_is_hardware_independent_analysis_convention': True}
    if op == 'Softmax':
        if source != output:
            raise ValueError('Softmax changed shape')
        axis = axis_index(attrs.get('axis', -1), len(source))
        length = source[axis]
        vectors = math.prod(source) // length
        maximum_comparisons = maximum_selections = vectors * (length - 1)
        additions = vectors * (length - 1)
        value = maximum_comparisons + maximum_selections + 3 * elements + additions
        detail.update(axis=axis, vector_length=length, vector_count=vectors,
                      maximum_comparisons=maximum_comparisons, maximum_selections=maximum_selections,
                      subtractions=elements, exponentials=elements, sum_additions=additions,
                      divisions=elements, formula='vectors * (6 * vector_length - 3)',
                      algorithm='Numerically stabilized softmax: maximum, subtract, exp, sum, divide')
    elif op == 'ReduceMax':
        keepdims = attrs.get('keepdims', 1)
        if keepdims not in (0, 1):
            raise ValueError('Invalid keepdims')
        axes = attrs.get('axes')
        origin = 'attribute'
        if len(inputs) > 1 and inputs[1]:
            axes = tensors[inputs[1]].get('constant_int_values')
            origin = 'constant_input'
            if axes is None:
                axes_shape = shape(tensors, inputs[1])
                if len(axes_shape) != 1:
                    raise ValueError('Reduction axes tensor has unexpected rank')
                axes = infer_reduction_axes(source, output, keepdims, axes_shape[0])
                origin = 'uniquely_inferred_from_captured_input_output_shapes_and_axes_tensor_length'
        if axes is None:
            raise ValueError('No recoverable reduction axes')
        axes = [axis_index(a, len(source)) for a in axes]
        if len(set(axes)) != len(axes):
            raise ValueError('Repeated reduction axis')
        expected = ([1 if i in axes else d for i, d in enumerate(source)] if keepdims
                    else [d for i, d in enumerate(source) if i not in axes])
        if output != expected:
            raise ValueError('Reduction shape mismatch')
        length = math.prod(source[i] for i in axes)
        comparisons = elements * (length - 1)
        value = 2 * comparisons
        detail.update(axes=axes, axes_source=origin, keepdims=keepdims,
                      comparisons=comparisons, selections=comparisons,
                      formula='output_elements * 2 * (reduced_elements - 1)')
    elif op == 'TopK':
        if len(outputs) != 2 or output != shape(tensors, outputs[1]):
            raise ValueError('TopK value/index output shape mismatch')
        if attrs.get('largest', 1) != 1 or attrs.get('sorted', 1) != 1:
            raise ValueError('Only sorted largest TopK is defined in this extension')
        axis = axis_index(attrs.get('axis', -1), len(source))
        if len(output) != len(source) or any(source[i] != output[i] for i in range(len(source)) if i != axis):
            raise ValueError('TopK dimensions outside axis changed')
        n, k = source[axis], output[axis]
        if not 0 < k <= n:
            raise ValueError('Invalid TopK output count')
        captured_k = tensors[inputs[1]].get('constant_int_values')
        if captured_k is not None and captured_k != [k]:
            raise ValueError('TopK captured K disagrees with output shape')
        vectors = math.prod(source) // n
        comparisons = vectors * (k * (n - 1) - k * (k - 1) // 2)
        value = 3 * comparisons
        detail.update(axis=axis, N=n, K=k, vector_count=vectors,
                      K_source='constant_input' if captured_k is not None else 'captured_value_and_index_output_shapes',
                      comparisons=comparisons, value_selections=comparisons, index_selections=comparisons,
                      formula='vectors * 3 * sum(N-j-1 for j in range(K))',
                      algorithm='Repeated maximum selection without replacement, scanning remaining original indices in ascending order; strict > preserves lower-index ties',
                      algorithm_is_not_an_observed_runtime_implementation=True,
                      structural_moves_and_loop_control_excluded=True)
    elif op == 'Mod':
        if attrs.get('fmod', 0) != 0 or any(tensors[n].get('dtype_enum') != 7 for n in inputs + outputs):
            raise ValueError('Only captured INT64 integer remainder is defined')
        right = shape(tensors, inputs[1])
        length = max(len(source), len(right))
        a, b = [1] * (length-len(source)) + source, [1] * (length-len(right)) + right
        if any(x != y and x != 1 and y != 1 for x, y in zip(a, b)) or output != [max(x,y) for x,y in zip(a,b)]:
            raise ValueError('Mod broadcasting mismatch')
        value = elements
        detail.update(fmod=0, integer_remainder_primitives=elements,
                      formula='output_elements; one scalar remainder primitive each')
    else:
        raise ValueError('Unsupported extension operator: ' + op)
    return {'node_index': node['index'], 'node_name': node['name'], 'operator': op,
            'complete': True, 'operations': value, 'known_operations': value,
            'classification': 'modeled_r29_extension', 'reason': '', 'detail': detail}


def self_checks():
    assert infer_reduction_axes([1, 8400, 80], [1, 8400], 0, 1) == [2]
    try:
        infer_reduction_axes([2, 2], [2], 0, 1)
    except ValueError:
        pass
    else:
        raise AssertionError('Ambiguous axes were accepted')
    # Independent loop verifies the closed count and deterministic TopK tie policy.
    for values in ([3, 1, 3, 2], [-5, 4, 0], [1, 1, 1]):
        for k in range(1, len(values)+1):
            remaining = list(enumerate(values)); winners=[]; operations=0
            for _ in range(k):
                best=remaining[0]
                for candidate in remaining[1:]:
                    take=candidate[1] > best[1]
                    best=(candidate[0] if take else best[0], candidate[1] if take else best[1])
                    operations += 3
                winners.append(best); remaining.remove(best)
            assert winners == sorted(enumerate(values), key=lambda x:(-x[1], x[0]))[:k]
            assert operations == 3*(k*(len(values)-1)-k*(k-1)//2)


def main(source, output):
    source, output = source.resolve(), output.resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('Use a separate derived output directory')
    self_checks()
    original_paths = [source/'inputs/graphs.json', source/'scripts/operation_counter.py',
                      source/'scripts/graph_features.py', source/'current_pair_feature_bindings.csv',
                      source/'graph_boundary_features.csv', source/'normalization_universes.json', source/'validation.json']
    original_hashes = {str(p.relative_to(source)):digest(p) for p in original_paths}
    graphs = json.loads((source/'inputs/graphs.json').read_text())['graphs']
    base = module(source/'scripts/operation_counter.py', 'r29_base_counter')
    features = module(source/'scripts/graph_features.py', 'r29_features')
    old_norm = json.loads((source/'normalization_universes.json').read_text())
    original_rows = list(csv.DictReader((source/'graph_boundary_features.csv').open()))
    original_by_id = {r['boundary_id']:r for r in original_rows}
    baseline_complete_models = {g['model'] for g in graphs if all(base.count_node(n,g['tensors'])['complete'] for n in g['nodes'])}
    assert len(baseline_complete_models) == 4
    base_costs, additions = {}, []
    for graph in graphs:
        opset = next(x['version'] for x in graph['opsets'] if x['domain'] in ('', 'ai.onnx'))
        costs=[]
        for node in graph['nodes']:
            cost=base.count_node(node, graph['tensors'])
            if not cost['complete']:
                cost=extension_count(node, graph['tensors'], opset)
                additions.append({'model':graph['model'], 'model_sha256':graph['model_sha256'], **cost})
            costs.append(cost)
        base_costs[graph['model']]=costs
    assert len(additions) == 15
    output.mkdir(parents=True, exist_ok=True)
    for rel in ['inputs/graphs.json', 'scripts/operation_counter.py', 'scripts/graph_features.py']:
        target=output/rel; target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/rel,target)
    shutil.copy2(source/'validation.json',output/'original_export_validation.json')
    scenarios=[('base',Fraction(1),output), ('new_ops_x0_1',Fraction(1,10),output/'sensitivity/new_ops_x0_1'),
               ('new_ops_x10',Fraction(10),output/'sensitivity/new_ops_x10')]
    reports=[]
    operations_fields={'F_left','F_right','F_total','F_left_known','F_right_known','F_total_known',
        'left_operations_complete','right_operations_complete','operations_complete','left_missing_operation_nodes',
        'right_missing_operation_nodes','total_missing_operation_nodes','Imb_raw','Imb_status',
        'candidate_available','candidate_unavailable_reasons','feature_complete'}
    for scenario,factor,folder in scenarios:
        folder.mkdir(parents=True,exist_ok=True)
        all_rows=[];all_norm=[];audits=[]
        for graph in graphs:
            costs=copy.deepcopy(base_costs[graph['model']])
            for cost in costs:
                if cost['classification']=='modeled_r29_extension':
                    scaled=Fraction(cost['operations'])*factor
                    assert scaled.denominator==1
                    cost['operations']=cost['known_operations']=int(scaled)
                    cost['detail']['sensitivity_scale']=str(factor)
            rows,_,norm,audit=features.features_for_graph(graph,costs)
            all_rows.extend(rows);all_norm.append(norm);audits.append(audit)
        features.write_csv(folder/'graph_boundary_features.csv',all_rows)
        actual_rows=list(csv.DictReader((folder/'graph_boundary_features.csv').open()))
        for row in actual_rows:
            original=original_by_id[row['boundary_id']]
            for field in row:
                if row['model'] in baseline_complete_models or field not in operations_fields:
                    assert row[field]==original[field], (row['model'],row['boundary'],field,row[field],original[field])
        # Retain the original normalization document schema and all membership semantics.
        norm_doc=copy.deepcopy(old_norm);norm_doc['graphs']=all_norm
        norm_doc['operation_proxy_version']=VERSION
        norm_doc['new_operation_sensitivity_scale']=str(factor)
        features.write_json(folder/'normalization_universes.json',norm_doc)
        shutil.copy2(source/'current_pair_feature_bindings.csv',folder/'current_pair_feature_bindings.csv')
        assert digest(folder/'current_pair_feature_bindings.csv')==original_hashes['current_pair_feature_bindings.csv']
        validation={'schema':'r29-derived-operation-features-validation-v1','status':'passed',
            'operation_proxy_version':VERSION,'new_operation_sensitivity_scale':str(factor),
            'scope':'New analytic operation proxy extension. Original measurements, pair bindings, graph identities, topology, bytes and tensor counts are unchanged.',
            'checks':{'graphs':7,'graph_boundary_rows':len(all_rows),'all_operation_features_complete':all(r['operations_complete'] for r in all_rows),
                'previously_complete_models_unchanged':sorted(baseline_complete_models),'original_nonoperation_fields_unchanged':True,
                'pair_binding_file_byte_identical':True,'added_operation_nodes':15,'reduction_axes_uniquely_inferred':True,
                'topk_k_validated_from_both_output_shapes':True,'topk_reference_algorithm_ties_and_counts_checked':True},
            'source_inputs_sha256':original_hashes,
            'model_operation_totals':[{'model':a['model'],'F_total':a['F_total'],
                'added_operations':sum(c['operations'] for c in a['node_costs'] if c['classification']=='modeled_r29_extension')} for a in audits]}
        features.write_json(folder/'validation.json',validation)
        if scenario=='base':
            features.write_json(folder/'node_operation_audit.json',{'proxy_version':VERSION,'graphs':audits})
            features.write_json(folder/'added_operation_nodes.json',{'proxy_version':VERSION,'nodes':additions})
        reports.append({'scenario':scenario,'output':folder.relative_to(output).as_posix(),'totals':validation['model_operation_totals']})
    assert original_hashes=={str(p.relative_to(source)):digest(p) for p in original_paths}
    features.write_json(output/'provenance.json',{'version':VERSION,'source_inputs_sha256':original_hashes,
        'source_inputs_unchanged':True,'semantic_sources':SEMANTICS,'scenarios':reports})
    print(json.dumps({'status':'passed','derived_export':str(output),'scenarios':reports},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.source,args.output)
