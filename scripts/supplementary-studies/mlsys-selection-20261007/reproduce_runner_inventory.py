"""Recompute the historical single-input inventory from saved descriptors."""
from pathlib import Path
import argparse
import pandas as pd


def build(analysis_root, output_root):
    output_root.mkdir(parents=True, exist_ok=True)
    stored = pd.read_csv(analysis_root / 'runner_sources/method_graph_features.csv')
    positions = pd.read_csv(analysis_root / 'runner_sources/graph_positions.csv')
    assert len(stored) == len(positions) == 2111
    assert not positions.duplicated(['model_id', 'case_id']).any()
    aliases = {
        'flops_left_ratio': 'stored_flops_left_ratio',
        'total_flops': 'stored_total_flops',
        'predicted_stream_fps': 'stored_predicted_stream_fps',
        'predicted_bottleneck_ms': 'stored_predicted_bottleneck_ms',
        'throughput_calibration_profile': 'prediction_calibration_profile',
    }
    graph = stored.rename(columns=aliases).merge(
        positions, on=['model_id', 'case_id'], validate='one_to_one', how='inner', sort=False)
    # Every source descriptor has this historical role; no new ranking is run.
    graph['source_role'] = 'base_saved_candidate_ranking'
    columns = ['model_id', 'case_id', 'boundary', 'node_count', 'topological_position',
               'cut_bytes', 'n_cut_tensors', 'part2_input_count', 'stored_flops_left_ratio',
               'stored_total_flops', 'stored_predicted_stream_fps',
               'stored_predicted_bottleneck_ms', 'prediction_calibration_profile', 'source_role']
    graph = graph[columns]
    native = pd.read_csv(analysis_root / 'runner_sources/native_cases.csv')
    assert len(graph) == 2111
    assert not graph.duplicated(['model_id', 'case_id']).any()
    # Native capability is bound to the actual suffix input count. A single
    # crossing activation is insufficient when the suffix needs another input.
    assert (graph.part2_input_count >= graph.n_cut_tensors).all()
    rows, details = [], []
    for model, frame in graph.groupby('model_id'):
        single = frame[frame.part2_input_count == 1].sort_values('boundary')
        selected = native[(native.model_id == model) & (native.case_id != 'full')]
        base = sorted(selected[selected.cohort == 'base'].case_id.unique())
        added = sorted(selected[selected.cohort == 'augmentation'].case_id.unique())
        rows.append(dict(model=model, nodes=int(frame.node_count.max()),
                         enumerated_cuts=len(frame), single_input=len(single),
                         one_cut_tensor=int((frame.n_cut_tensors == 1).sum()),
                         multi_input=len(frame)-len(single),
                         single_ratio=len(single)/len(frame),
                         single_cut_indices=','.join(single.case_id),
                         base_selected_native=','.join(base),
                         added_native=','.join(added),
                         single_position_min=single.topological_position.min(),
                         single_position_max=single.topological_position.max()))
        details.append(single.assign(selected_base=single.case_id.isin(base),
                                     selected_added=single.case_id.isin(added)))
    inventory = pd.DataFrame(rows)
    boundaries = pd.concat(details)
    assert len(inventory) == 7 and len(boundaries) == 183
    inventory.to_csv(output_root/'single_tensor_inventory.csv', index=False)
    boundaries.to_csv(output_root/'single_tensor_boundaries.csv', index=False)
    print(inventory[['model','enumerated_cuts','single_input','base_selected_native','added_native']].to_string(index=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    build(args.analysis_root.resolve(), args.output_root.resolve())
