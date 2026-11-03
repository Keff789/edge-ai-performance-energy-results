"""Verify a diagram-level YOLOv7 map against frozen published operation metadata."""
from pathlib import Path
import csv
import hashlib
import json
import yaml

import argparse
ROOT = Path(__file__).resolve().parents[2]
_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument('--output',type=Path,default=ROOT/'results/supplementary-studies/dissertation-author-style-20261103/topology')
OUT = _parser.parse_args().output.resolve()
OUT.mkdir(parents=True,exist_ok=True)
FEATURES = ROOT / 'results/supplementary-studies/rq2-weighted-20261020/features'
source_yaml = ROOT / 'results/supplementary-studies/dissertation-author-style-20261103/sources/upstream_yolov7_training.yaml'
official = yaml.safe_load(source_yaml.read_text())
audit_file = FEATURES / 'node_operation_audit.json'
audit = next(g for g in json.loads(audit_file.read_text())['graphs'] if g['model'] == 'yolov7_paper')
nodes = audit['node_costs']
norm_file = FEATURES / 'normalization_universes.json'
norm = next(g for g in json.loads(norm_file.read_text())['graphs'] if g['model'] == 'yolov7_paper')
features_file = FEATURES / 'graph_boundary_features.csv'
features = list(csv.DictReader(features_file.open()))
patterns = {
    'Conv': ['Conv', 'Sigmoid', 'Mul'],
    'MP': ['MaxPool'],
    'Concat': ['Concat'],
    'nn.Upsample': ['Resize'],
    'RepConv': ['Conv', 'Conv', 'Add', 'Sigmoid', 'Mul'],
    'IDetect': ['Conv', 'Reshape', 'Transpose'] * 3,
    'SPPCSPC': (['Conv', 'Sigmoid', 'Mul'] * 3 + ['MaxPool'] * 3 + ['Concat']
                 + ['Conv', 'Sigmoid', 'Mul'] * 3 + ['Concat', 'Conv', 'Sigmoid', 'Mul']),
}
layers = []
shapes = {}
cursor = 0
for layer_index, (sources, repeats, module, arguments) in enumerate(official['backbone'] + official['head']):
    assert repeats == 1
    sources = sources if isinstance(sources, list) else [sources]
    source_layers = [s + layer_index if s < 0 else s for s in sources]
    source_shapes = [shapes[s] if s >= 0 else [1, 3, 640, 640] for s in source_layers]
    pattern = patterns[module]
    slice_nodes = nodes[cursor:cursor + len(pattern)]
    assert [n['operator'] for n in slice_nodes] == pattern, (layer_index, module)
    shape = None
    if module in ('Conv', 'RepConv'):
        expected = source_shapes[0].copy()
        expected[1] = arguments[0]
        expected[2] //= arguments[2]
        expected[3] //= arguments[2]
        shape = slice_nodes[-1]['detail']['output_shape']
        assert shape == expected, (layer_index, shape, expected)
        assert slice_nodes[0]['detail']['input_channels'] == source_shapes[0][1]
    elif module == 'MP':
        shape = slice_nodes[-1]['detail']['output_shape']
        expected = source_shapes[0].copy()
        expected[2] //= 2
        expected[3] //= 2
        assert shape == expected
    elif module == 'Concat':
        assert all(s[2:] == source_shapes[0][2:] for s in source_shapes)
        shape = source_shapes[0].copy()
        shape[1] = sum(s[1] for s in source_shapes)
    elif module == 'SPPCSPC':
        shape = slice_nodes[-1]['detail']['output_shape']
        assert shape == [1, arguments[0], *source_shapes[0][2:]]
    elif module == 'nn.Upsample':
        shape = slice_nodes[-1]['detail']['output_shape']
        assert shape == [*source_shapes[0][:2], source_shapes[0][2] * 2, source_shapes[0][3] * 2]
    elif module == 'IDetect':
        assert [n['detail']['output_shape'] for n in slice_nodes if n['operator'] == 'Conv'] == [
            [1, 255, 80, 80], [1, 255, 40, 40], [1, 255, 20, 20]]
    shapes[layer_index] = shape
    layers.append(dict(yaml_layer=layer_index, module=module, source_yaml_layers=source_layers,
                       onnx_nodes=[cursor, cursor+len(pattern)-1], output_shape_nchw=shape))
    cursor += len(pattern)
assert cursor == len(nodes) == 309

cut_specs = [
    ('b009', 9, 3, [1, 128, 160, 160], 'After Conv, before SiLU in the early stride-two convolution'),
    ('b044', 44, 16, [1, 256, 80, 80], 'After concatenation of the two downsampling branches, before the second ELAN block'),
    ('b066', 66, 24, [1, 512, 80, 80], 'After the second ELAN block including its final 1x1 Conv and SiLU; backbone P3/8 output'),
]
cuts = []
for case, index, layer, shape, location in cut_specs:
    row = next(r for r in features if r['model'] == 'yolov7_paper' and r['case'] == case)
    assert int(row['left_last_node_index']) == index
    assert set(norm['order'][:index + 1]) == set(range(index + 1))
    assert int(row['part2_input_count']) == int(row['crossing_tensor_count']) == 1
    assert int(row['Comm']) == 4 * shape[0] * shape[1] * shape[2] * shape[3]
    cuts.append(dict(case=case, boundary_position=index, onnx_node_index=index,
                     onnx_node_name=nodes[index]['node_name'], onnx_operator=nodes[index]['operator'],
                     yaml_layer=layer, crossing_tensor=json.loads(row['crossing_tensor_names'])[0],
                     shape_nchw=shape, logical_fp32_bytes=int(row['Comm']),
                     suffix_input_count=1, location=location,
                     topology_position_distinct_from_onnx_index_in_general=True))

groups = [
    ('stem', 'Conv stem', 0, 2),
    ('conv_p2', 'Stride-two Conv, including b009 before SiLU', 3, 3),
    ('elan_p2', 'ELAN P2', 4, 11),
    ('down_p3', 'Two-branch downsampling, ending at b044', 12, 16),
    ('elan_p3', 'ELAN P3, ending at b066', 17, 24),
    ('down_p4', 'Two-branch downsampling', 25, 29),
    ('elan_p4', 'ELAN P4', 30, 37),
    ('down_p5', 'Two-branch downsampling', 38, 42),
    ('elan_p5', 'ELAN P5', 43, 50),
    ('spp', 'SPPCSPC', 51, 51),
    ('topdown_p4', 'Top-down fusion P4', 52, 63),
    ('topdown_p3', 'Top-down fusion P3', 64, 75),
    ('bottomup_p4', 'Bottom-up fusion P4', 76, 88),
    ('bottomup_p5', 'Bottom-up fusion P5', 89, 101),
    ('rep_p3', 'RepConv P3', 102, 102),
    ('rep_p4', 'RepConv P4', 103, 103),
    ('rep_p5', 'RepConv P5', 104, 104),
    ('detect', 'Three detection heads', 105, 105),
]
group_rows = [dict(id=i, label=l, yaml_layers=[a,b],
                   onnx_nodes=[layers[a]['onnx_nodes'][0], layers[b]['onnx_nodes'][1]],
                   output_shape_nchw=shapes[b]) for i,l,a,b in groups]
layer_to_group = {n:i for i,l,a,b in groups for n in range(a,b+1)}
group_edges = sorted({(layer_to_group[s], layer_to_group[l['yaml_layer']])
                      for l in layers for s in l['source_yaml_layers']
                      if s >= 0 and layer_to_group[s] != layer_to_group[l['yaml_layer']]})

source_files = [source_yaml, audit_file, norm_file, features_file]
evidence = dict(
    schema='yolov7-diagram-topology-v1',
    model='yolov7_paper', model_sha256=audit['model_sha256'],
    upstream_architecture_url='https://github.com/WongKinYiu/yolov7/blob/main/cfg/training/yolov7.yaml',
    upstream_paper_url='https://openaccess.thecvf.com/content/CVPR2023/html/Wang_YOLOv7_Trainable_Bag-of-Freebies_Sets_New_State-of-the-Art_for_Real-Time_Object_Detectors_CVPR_2023_paper.html',
    sources=[dict(path=str(p.relative_to(ROOT)), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in source_files],
    validation=dict(onnx_operator_sequence_matches_all_106_yaml_modules=True,
                    matched_onnx_nodes=309, convolution_input_channels_match_yaml_edges=True,
                    convolution_pool_resize_output_shapes_match=True,
                    cut_prefixes_and_tensor_counts_verified=True,
                    actual_onnx_binary_present=False,
                    status='High-confidence diagram-level mapping from frozen metadata and matching official architecture; not a re-export or graph-binary round-trip'),
    conventions=dict(shape='NCHW', input_shape=[1,3,640,640],
                     boundary_number='Position in saved topological boundary order; for the three selected cuts it also equals the last ONNX node index, not the YAML layer number',
                     bytes='Logical FP32 tensor bytes, not a claim about all runtime transfer representations'),
    cuts=cuts, layers=layers, diagram_groups=group_rows,
    diagram_edges=[dict(source=s,target=t) for s,t in group_edges],
    detector_outputs=dict(pre_reshape_conv_shapes=[[1,255,80,80],[1,255,40,40],[1,255,20,20]],
                          classes=80, anchors_per_scale=3, values_per_anchor=85,
                          final_transpose_shapes='Not explicitly present in frozen operation audit; label pre-reshape convolution shapes or spatial scales in the diagram'),
    interpretation=[
        'b066 produces a single P3 tensor that fans out within the suffix to deeper backbone and the lateral neck route.',
        'A single cut tensor can have more than one downstream consumer.',
        'The three cut IDs are not indices of the YAML modules.',
        'b044 has fewer logical boundary bytes than b066, so the higher measured b066 throughput cannot be attributed to minimum boundary size alone.',
        'Architectural placement and compute allocation explain differences descriptively; they do not isolate the causal contributions of runtime overlap, copies, and accelerator/GPU execution.'
    ])
(OUT/'yolov7_diagram_topology.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(dict(validation=evidence['validation'], cuts=cuts, yaml_sha256=evidence['sources'][0]['sha256']), indent=2))
