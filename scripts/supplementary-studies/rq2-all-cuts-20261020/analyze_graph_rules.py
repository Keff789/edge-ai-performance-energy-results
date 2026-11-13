#!/usr/bin/env python3
"""All-cut analysis of the paper's HISTORICAL selector experiment.

This uses the frozen graph scores and the historical paired campaign, with the
same nine-row YOLOv7 Native report overlay as the paper. It does not project
historical graph identities onto current Native/A4 measurements. All 204
technical pairs enter; the current 5% quality filter is intentionally not used.

Invoked by reproduce.py through run(repository_root, output_directory).
Requires scipy. No hardware, network, fitted parameters, or Monte Carlo draws.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from scipy.stats import rankdata, spearmanr

HIST = Path('results/supplementary-studies/thesis20-ranking-20261005')
OLD = Path('results/supplementary-studies/mlsys-selection-20261007/inputs/analysis')
PUB = Path('results/split-inference/publications/mlsys-r22')
METHODS = ['cut_bytes_only', 'weighted_score', 'onnx_real_boundary_hardware_aware',
           'cycle_time_no_handover', 'stored_predicted_stream_fps',
           'measured_generic_completion']
MODELS = ['mobilenet_v3_large', 'regnet_x_1_6gf', 'resnet50', 'yolo11l',
          'yolo26m', 'yolo26s', 'yolov7_paper']
SETUPS = ['H8', 'H10', 'DeepX']

def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))

def write(path, rows):
    rows = list(rows)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows({k: json.dumps(v, separators=(',', ':')) if isinstance(v, (list, dict)) else v
                    for k, v in row.items()} for row in rows)

def mean(values):
    return statistics.fmean(values)

def exact_random(values, k):
    values = sorted(values)
    n = len(values)
    denominator = math.comb(n, k)
    expected_best = math.fsum(v * math.comb(i, k - 1)
                              for i, v in enumerate(values) if i >= k - 1) / denominator
    best = values[-1]
    winners = sum(v == best for v in values)
    miss = math.comb(n - winners, k) if n - winners >= k else 0
    return expected_best, 1 - miss / denominator, denominator

def run(repo, output):
    output.mkdir(parents=True, exist_ok=True)
    source_paths = [OLD/'evidence/tables/rank_cases.csv',
                    OLD/'reported_update/reported_results.csv',
                    HIST/'inputs/method_candidate_scores.csv',
                    HIST/'inputs/method_parameters.json',
                    PUB/'data/historical_selector_groups.csv',
                    PUB/'tables/ranking_tables.csv']
    raw = read(repo/source_paths[0])
    overlays = {(r['model'], r['setup'], r['case']): r
                for r in read(repo/source_paths[1]) if r['configuration_type'] == 'split'}
    assert len(raw) == 204 and len(overlays) == 9
    score_map = {}
    for r in read(repo/source_paths[2]):
        if r['method'] not in METHODS[:5]:
            continue
        key = r['model_id'], r['case_id'], r['setup_id'], r['method']
        assert key not in score_map and r['status'] == 'available'
        score_map[key] = r
    groups = defaultdict(list)
    cuts = []
    seen = set()
    for pair_order, original in enumerate(raw):
        assert original['eligible_for_technical_transfer'] == 'True'
        model, setup, case = (original[k] for k in ['model_id', 'setup_id', 'case_id'])
        identity = model, setup, case
        assert identity not in seen
        seen.add(identity)
        native = float(original['native_completed_task_fps'])
        native_source = 'archived_completed_campaign'
        overlay_hash = ''
        if identity in overlays:
            overlay = overlays[identity]
            native = float(overlay['fps_median'])
            assert math.isclose(native, statistics.median(float(overlay[f'fps_{i}'])
                                for i in [1, 2, 3]), abs_tol=5e-7)
            native_source = 'supplied_report_overlay_20261006'
            overlay_hash = overlay['source_sha256']
        row = dict(dataset='historical_204_technical_pairs', model=model, setup=setup,
                   case=case, family='classification' if model in MODELS[:3] else 'detection',
                   direction=original['direction'], precision=original['precision'],
                   comparison_backend=original['comparison_backend'],
                   endpoint=original['output_endpoint_id'],
                   generic_fps=float(original['generic_completed_task_fps']), native_fps=native,
                   native_source=native_source, native_overlay_source_sha256=overlay_hash,
                   original_pair_order=pair_order)
        row['_scores'] = {}
        for method in METHODS[:5]:
            exact = score_map.get((model, case, setup, method))
            shared = score_map.get((model, case, 'all', method))
            assert not (exact and shared)
            source = exact or shared
            assert source is not None
            score = float(source['score'])
            direction = source['score_direction']
            assert direction == ('descending' if method == 'stored_predicted_stream_fps' else 'ascending')
            utility = score if direction == 'descending' else -score
            order = int(float(source['original_order']))
            row['_scores'][method] = (utility, order)
            row[f'score_{method}'] = score
            row[f'utility_{method}'] = utility
            row[f'tie_order_{method}'] = order
        row['_scores']['measured_generic_completion'] = (row['generic_fps'], pair_order)
        groups[(model, setup)].append(row)
        cuts.append(row)
    assert len(groups) == 21
    correlations, curves = [], []
    for (model, setup), pool in groups.items():
        n = len(pool)
        metadata = dict(dataset='historical_204_technical_pairs', model=model, setup=setup,
                        family=pool[0]['family'], n=n)
        native_values = [r['native_fps'] for r in pool]
        generic_values = [r['generic_fps'] for r in pool]
        best_native, best_generic = max(native_values), max(generic_values)
        for i, row in enumerate(pool):
            row['native_rank_average'] = float(rankdata([-v for v in native_values], method='average')[i])
            row['generic_rank_average'] = float(rankdata([-v for v in generic_values], method='average')[i])
            row['native_loss_pct'] = 100*(1-row['native_fps']/best_native)
            row['generic_loss_pct'] = 100*(1-row['generic_fps']/best_generic)
        for method in METHODS:
            utilities = [r['_scores'][method][0] for r in pool]
            assert len(set(utilities)) > 1
            correlations.append(dict(metadata, method=method,
                spearman_native=float(spearmanr(utilities, native_values).statistic),
                spearman_generic=float(spearmanr(utilities, generic_values).statistic),
                distinct_scores=len(set(utilities)),
                ranks='average ranks for exact ties; higher utility and FPS are better'))
            ordered = sorted(pool, key=lambda r:(-r['_scores'][method][0], r['_scores'][method][1], r['original_pair_order']))
            score_ranks = rankdata([-u for u in utilities], method='average')
            for i, row in enumerate(pool):
                row[f'rank_average_{method}'] = float(score_ranks[i])
            for k in range(1, n+1):
                chosen = ordered[:k]
                nr, gr = max(r['native_fps'] for r in chosen), max(r['generic_fps'] for r in chosen)
                curves.append(dict(metadata, method=method, k=k,
                    selected_cases=[r['case'] for r in chosen],
                    native_retained_fps=nr, native_loss_pct=100*(1-nr/best_native),
                    native_winner_coverage=float(nr == best_native),
                    generic_retained_fps=gr, generic_loss_pct=100*(1-gr/best_generic),
                    generic_winner_coverage=float(gr == best_generic), random_subset_count=''))
        for k in range(1,n+1):
            nr, nh, count = exact_random(native_values, k)
            gr, gh, _ = exact_random(generic_values, k)
            curves.append(dict(metadata, method='uniform_random', k=k, selected_cases=[],
                native_retained_fps=nr, native_loss_pct=max(0,100*(1-nr/best_native)),
                native_winner_coverage=nh, generic_retained_fps=gr,
                generic_loss_pct=max(0,100*(1-gr/best_generic)),
                generic_winner_coverage=gh, random_subset_count=count))
    # Verify against every published historical Top1 row and the headline table.
    published = read(repo/source_paths[4])
    curve_index = {(r['model'],r['setup'],r['method'],r['k']):r for r in curves}
    assert len(published) == 126
    for p in published:
        r = curve_index[(p['model_id'],p['setup_id'],p['method'],1)]
        assert r['selected_cases'] == [p['selected_case']]
        assert math.isclose(r['native_retained_fps'],float(p['selected_native_fps']),rel_tol=1e-12)
        assert math.isclose(r['native_loss_pct'],100*float(p['L_R']),abs_tol=1e-10)
    summaries = []
    correlation_summaries = []
    for family in ['classification','detection','all']:
        group_keys = [key for key,pool in groups.items() if family=='all' or pool[0]['family']==family]
        for method in METHODS:
            selected = [r for r in correlations if r['method']==method and (family=='all' or r['family']==family)]
            correlation_summaries.append(dict(family=family,method=method,groups=len(selected),
                mean_spearman_native=mean(r['spearman_native'] for r in selected),
                median_spearman_native=statistics.median(r['spearman_native'] for r in selected),
                mean_spearman_generic=mean(r['spearman_generic'] for r in selected),
                median_spearman_generic=statistics.median(r['spearman_generic'] for r in selected)))
        for k in range(1,21):
            for method in METHODS+['uniform_random']:
                selected=[curve_index[(model,setup,method,min(k,len(groups[(model,setup)])))] for model,setup in group_keys]
                summaries.append(dict(family=family,method=method,requested_k=k,groups=len(group_keys),
                    candidate_count=sum(len(groups[key]) for key in group_keys),
                    actual_k_min=min(r['k'] for r in selected),actual_k_max=max(r['k'] for r in selected),
                    mean_native_loss_pct=mean(r['native_loss_pct'] for r in selected),
                    median_native_loss_pct=statistics.median(r['native_loss_pct'] for r in selected),
                    native_winner_groups_or_expectation=sum(r['native_winner_coverage'] for r in selected),
                    mean_generic_loss_pct=mean(r['generic_loss_pct'] for r in selected),
                    median_generic_loss_pct=statistics.median(r['generic_loss_pct'] for r in selected),
                    generic_winner_groups_or_expectation=sum(r['generic_winner_coverage'] for r in selected),
                    aggregation='equal group weight; actual_k=min(requested_k,n); fixed group population'))
    headline = read(repo/source_paths[5])
    for p in headline:
        r=next(r for r in summaries if r['family']=='all' and r['method']==p['method'] and r['requested_k']==1)
        assert math.isclose(r['mean_native_loss_pct'],float(p['mean_loss_pct']),abs_tol=1e-10)
        assert math.isclose(r['median_native_loss_pct'],float(p['median_loss_pct']),abs_tol=1e-10)
        assert r['native_winner_groups_or_expectation']==int(p['all_hits'])
    cuts.sort(key=lambda r:(MODELS.index(r['model']),SETUPS.index(r['setup']),r['case']))
    for row in cuts:
        del row['_scores']
    write(output/'historical_cuts.csv',cuts)
    write(output/'historical_rank_correlations.csv',correlations)
    write(output/'historical_correlation_summary.csv',correlation_summaries)
    write(output/'historical_shortlist_group_curves.csv',curves)
    write(output/'historical_shortlist_summary.csv',summaries)
    provenance=dict(dataset='historical_204_technical_pairs',pairs=len(cuts),groups=len(groups),
        source_commit='b10d15992d0ce45d0f81329a5e961cb6207a1d09',
        classifier_pairs=168,detector_pairs=36,
        relation_to_current='Separate historical measurements; not current Native/A4 deployment comparison.',
        quality_filter='Historical technical-transfer admission only; all 204 pairs; no new 5% gate.',
        rank_ties='Spearman uses average ranks for exact score or FPS ties.',
        selection_ties='Static: frozen original_order (boundary order), then original pair order. Generic: original pair order.',
        random='Exact expected maximum of uniform k-subsets without replacement, combinatorial weights.',
        summary_population='Fixed nine classifier and twelve detector groups. k capped to group size. Every group equal weight.',
        verified_published_top1_groups=126,verified_published_summary_methods=6,
        score_formulas={
          'cut_bytes_only':'graph-estimated boundary bytes; lower better',
          'weighted_score':'minmax(log10(1+bytes)) + 3*minmax(imbalance) + 0.2*minmax(max(tensors-1,0)); full saved model universe normalization',
          'onnx_real_boundary_hardware_aware':'frozen Hailo10-to-TensorRT accelerator fit shared across setups; lower better',
          'cycle_time_no_handover':'stored heuristic total latency times max(left,right) compute share; lower better',
          'stored_predicted_stream_fps':'1000/(stored bottleneck + stored handover term); higher better',
          'measured_generic_completion':'paired measured Generic completion FPS; higher better'},
        sources=[dict(path=str(p),sha256=hashlib.sha256((repo/p).read_bytes()).hexdigest()) for p in source_paths])
    (output/'historical_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({'pairs':len(cuts),'correlations':len(correlations),'group_curve_rows':len(curves),
                      'summary_rows':len(summaries),'published_top1_check':'PASS'},indent=2))
    for row in correlation_summaries:
        if row['method']=='cut_bytes_only':print(row)
    for row in summaries:
        if row['family']=='classification' and row['requested_k'] in [1,3,5,10] and row['method'] in ['cut_bytes_only','measured_generic_completion','uniform_random']:
            print(row)

if __name__=='__main__':
    raise SystemExit('Use reproduce.py --output PATH [--numeric-only] [--verify].')
