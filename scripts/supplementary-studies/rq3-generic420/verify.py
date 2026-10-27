#!/usr/bin/env python3
"""Check input provenance, every fitted scope, reported rankings and localization."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from fit_weights import BASELINES, SCOPES, DEFAULT, make_groups, ranked_metrics, summarize, weight_grid


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_inputs(study):
    d = pd.read_csv(study/'inputs/candidates.csv')
    cov = pd.read_csv(study/'inputs/coverage.csv')
    universe = pd.read_csv(study/'inputs/graph_universe.csv')
    meta = json.loads((study/'inputs/feature_metadata.json').read_text())
    assert len(d) == 420 and d.generic_uid.is_unique
    assert len(cov) == 21 and not cov.duplicated(['model', 'accelerator']).any()
    assert not universe.duplicated(['model', 'case_id']).any()
    measured = d.fps_measured
    assert np.array_equal(measured, np.isfinite(d.fps) & (d.fps > 0))
    assert np.array_equal(d.analysis_eligible, measured & d.quality_eligible)
    repetitions = d.loc[measured, ['repeat1', 'repeat2', 'repeat3']].to_numpy(float)
    assert np.isfinite(repetitions).all() and (repetitions > 0).all()
    np.testing.assert_allclose(d.loc[measured, 'fps'], np.median(repetitions, axis=1), rtol=1e-12, atol=1e-10)
    assert not (measured & d.technical_exclusion.notna()).any()
    for (model, accelerator), rows in d.groupby(['model', 'accelerator'], sort=False):
        assert len(rows) == 20 and rows.case_id.nunique() == 20
        selected = cov[(cov.model == model) & (cov.accelerator == accelerator)]
        assert len(selected) == 1
        c = selected.iloc[0]
        eligible = int(rows.analysis_eligible.sum())
        fps_measured = int(rows.fps_measured.sum())
        qfail = int((rows.fps_measured & rows.quality_status.eq('accuracy_loss')).sum())
        qpending = fps_measured-eligible-qfail
        technical = int(rows.technical_exclusion.notna().sum())
        fps_pending = 20-fps_measured-technical
        values = dict(selected=20, fps_measured=fps_measured, analysis_eligible=eligible,
                      quality_fail_measured=qfail, quality_pending_measured=qpending,
                      technical_excluded=technical, fps_pending=fps_pending)
        assert qpending >= 0 and fps_pending >= 0
        for key, value in values.items():
            assert c[key] == value, (model, accelerator, key)
        complete = fps_pending == 0 and qpending == 0
        assert c.analysis_group_complete == complete
        assert rows.analysis_group_complete.eq(complete).all()
        assert rows.group_eligible_n.eq(eligible).all()
        assert rows.group_fps_pending.eq(fps_pending).all()
        assert rows.group_quality_pending.eq(qpending).all()
    counts = dict(selected=len(d), fps_measured=int(measured.sum()), eligible=int(d.analysis_eligible.sum()),
                  quality_fail_measured=int(cov.quality_fail_measured.sum()),
                  quality_pending_measured=int(cov.quality_pending_measured.sum()),
                  technical_excluded=int(cov.technical_excluded.sum()), fps_pending=int(cov.fps_pending.sum()),
                  nonempty_eligible_groups=int((cov.analysis_eligible > 0).sum()),
                  analysis_complete_groups=int(cov.analysis_group_complete.sum()))
    assert counts == meta['counts']
    assert counts['fps_measured']+counts['technical_excluded']+counts['fps_pending'] == 420
    assert counts['eligible']+counts['quality_fail_measured']+counts['quality_pending_measured'] == counts['fps_measured']
    assert meta['status'] == ('preliminary' if counts['fps_pending'] or counts['quality_pending_measured'] else 'resolved_conditional_candidate_pool')
    for model, rows in universe.groupby('model'):
        provenance = meta['prediction_sources'][model]
        assert len(rows) == provenance['candidate_count']
        c = np.log10(1+rows.cut_bytes.to_numpy(float))
        t = np.maximum(rows.n_cut_tensors.to_numpy(int)-1, 0)
        np.testing.assert_allclose(rows.C, (c-c.min())/(c.max()-c.min()) if c.max() > c.min() else np.zeros(len(c)), rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(rows['T'], (t-t.min())/(t.max()-t.min()) if t.max() > t.min() else np.zeros(len(t)), rtol=1e-12, atol=1e-12)
        total = rows.flops_left_abs+rows.flops_right_abs
        assert (total > 0).all()
        np.testing.assert_allclose(rows.I, abs(rows.flops_left_abs-rows.flops_right_abs)/total, rtol=1e-12, atol=1e-12)
        assert provenance['normalization_matches_published']
    joined = d.merge(universe, on=['model', 'case_id'], suffixes=('', '_universe'), validate='many_to_one')
    assert len(joined) == len(d)
    for column in ['C', 'I', 'T', 'cut_bytes', 'n_cut_tensors', 'flops_left_abs', 'flops_right_abs']:
        np.testing.assert_allclose(joined[column], joined[column+'_universe'], rtol=1e-12, atol=1e-12)
    for column in ['boundary_id', 'model_sha256']:
        assert joined[column].equals(joined[column+'_universe'])
    pending = d[measured & ~d.analysis_eligible & ~d.quality_status.eq('accuracy_loss')]
    if 'quality_completion' in meta:
        quality = meta['quality_completion']
        assert quality['complete'] == pending.empty
        assert {r['generic_uid'] for r in quality['pending_measured']} == set(pending.generic_uid)
        assert not quality['historical_quality_is_current_admission']
    return d, counts


def check_weights(weights, grid):
    weights = np.asarray(weights, dtype=float)
    assert np.isfinite(weights).all() and (weights >= 0).all()
    np.testing.assert_allclose(weights.sum(), 1, rtol=0, atol=1e-12)
    assert np.any(np.all(np.isclose(grid, weights, rtol=0, atol=1e-12), axis=1))


def verify_fit(d, directory):
    config = json.loads((directory/'fit_config.json').read_text())
    groups = make_groups(d, 'bytes' if directory.name == 'tie_secondary_bytes' else 'uid')
    folds = pd.read_csv(directory/'fold_weights.csv')
    metrics = pd.read_csv(directory/'heldout_metrics.csv')
    grid = weight_grid(config['denominator'])
    assert np.any(np.all(grid == [1, 0, 0], axis=1))
    assert np.any(np.all(grid == DEFAULT, axis=1))
    assert config['grid_points'] == len(grid)
    assert config['groups'] == len(groups) and config['candidates'] == sum(g['n'] for g in groups)
    assert config['models'] == len({g['model'] for g in groups})
    assert config['objective_budgets'] == ([5] if directory.name == 'budget5_fit' else [1, 3, 5])
    assert set(folds.method) == set(SCOPES) and folds.fold_id.is_unique
    assert set(metrics.method) == set(SCOPES) | set(BASELINES)
    assert not metrics.duplicated(['method', 'model', 'accelerator', 'k']).any()
    assert len(metrics) == len(groups)*20*(len(SCOPES)+len(BASELINES))
    fold_lookup = {row.fold_id: row for row in folds.itertuples()}

    def training_loss(weight, selected):
        return np.mean([ranked_metrics(weight, g, config['objective_budgets'])[0].mean() for g in selected])

    for row in folds.itertuples():
        excluded = row.held_out_models.split(';')
        training = row.train_models.split(';')
        assert not set(excluded) & set(training)
        if directory.name == 'family_holdout' and row.test_model == 'yolo26_family':
            assert set(excluded) == {'yolo26m', 'yolo26s'}
        else:
            assert excluded == [row.test_model]
        selected = [g for g in groups if g['model'] not in excluded
                    and (row.train_task == 'all' or g['task'] == row.train_task)
                    and (row.train_accelerator == 'all' or g['accelerator'] == row.train_accelerator)]
        assert set(training) == {g['model'] for g in selected}
        assert row.train_groups == len(selected) and row.train_candidates == sum(g['n'] for g in selected)
        assert row.train_model_count == len(training)
        w = np.array([row.w_comm, row.w_imb, row.w_ten])
        check_weights(w, grid)
        loss = training_loss(w, selected)
        assert abs(loss*100-row.train_loss_pct) < 1e-8
        assert loss <= training_loss([1, 0, 0], selected)+1e-12
    group_lookup = {(g['model'], g['accelerator']): g for g in groups}
    rank_cache = {}
    for r in metrics.itertuples():
        g = group_lookup[r.model, r.accelerator]
        assert r.task == g['task'] and r.group_complete == g['complete'] and r.eligible_n == g['n']
        assert 1 <= r.k <= 20 and r.tested_n == min(r.k, g['n'])
        w = np.array([r.w_comm, r.w_imb, r.w_ten])
        if r.method in BASELINES:
            np.testing.assert_allclose(w, BASELINES[r.method], rtol=0, atol=1e-12)
            assert r.fold_id == 'fixed_baseline'
        else:
            fold = fold_lookup[r.fold_id]
            assert fold.method == r.method and r.model in fold.held_out_models.split(';')
            assert fold.train_task == (r.task if r.method in ('task', 'task_device') else 'all')
            assert fold.train_accelerator == (r.accelerator if r.method in ('device', 'task_device') else 'all')
            np.testing.assert_allclose(w, [fold.w_comm, fold.w_imb, fold.w_ten], rtol=0, atol=1e-12)
            assert abs(r.train_loss_pct-fold.train_loss_pct) < 1e-8
        key = (r.model, r.accelerator, *w)
        if key not in rank_cache:
            rank_cache[key] = ranked_metrics(w, g)
        losses, order = rank_cache[key]
        selected = order[0, :min(r.k, g['n'])]
        chosen = selected[np.argmax(g['fps'][selected])]
        loss = float(losses[0, r.k-1])
        assert r.selected_cases == ','.join(g['rows'].case_id.iloc[selected])
        assert r.shortlist_best_case == g['rows'].case_id.iloc[chosen]
        assert abs(r.best_fps-g['best']) < 1e-8
        assert abs(r.shortlist_best_fps-g['fps'][chosen]) < 1e-8
        assert abs(r.loss_pct-100*loss) < 1e-8
        assert r.exact_hit == (loss <= 1e-12)
        assert r.within_1pct == (loss <= .01+1e-12)
        assert r.within_5pct == (loss <= .05+1e-12)
    regenerated = summarize(metrics.to_dict(orient='records'))
    actual = pd.read_csv(directory/'summary.csv')
    pd.testing.assert_frame_equal(regenerated, actual, check_exact=False, rtol=1e-10, atol=1e-10)
    full = pd.read_csv(directory/'full_data_weights.csv')
    assert set(full.method) == set(SCOPES)
    expected_full = {(scope, task, device) for scope in SCOPES
                     for task in (sorted({g['task'] for g in groups}) if scope in ('task', 'task_device') else ['all'])
                     for device in (sorted({g['accelerator'] for g in groups}) if scope in ('device', 'task_device') else ['all'])}
    assert len(full) == len(expected_full)
    assert set(zip(full.method, full.task, full.accelerator)) == expected_full
    for row in full.itertuples():
        selected = [g for g in groups if (row.task == 'all' or g['task'] == row.task)
                    and (row.accelerator == 'all' or g['accelerator'] == row.accelerator)]
        w = np.array([row.w_comm, row.w_imb, row.w_ten])
        check_weights(w, grid)
        assert row.evaluation_role == 'fit_on_all_available_data_not_holdout'
        assert row.train_groups == len(selected)
        assert set(row.train_models.split(';')) == {g['model'] for g in selected}
        loss = training_loss(w, selected)
        assert abs(loss*100-row.train_loss_pct) < 1e-8
        assert loss <= training_loss([1, 0, 0], selected)+1e-12
    return dict(folds=len(folds), metrics=len(metrics), descriptive_fits=len(full), summary_reproduced=True)


def check_file_manifest(root, name):
    path = root/name
    if not path.exists():
        return
    manifest = json.loads(path.read_text())
    for member, digest in manifest['files'].items():
        file = (root/member).resolve()
        assert file.is_relative_to(root.resolve())
        assert sha(file) == digest, member


def verify(study):
    study = Path(study)
    d, counts = verify_inputs(study)
    fit_results = {}
    for directory in sorted((study/'fit_results').iterdir()):
        if directory.is_dir() and (directory/'fit_config.json').exists():
            fit_results[directory.name] = verify_fit(d, directory)
    assert 'primary' in fit_results
    provenance = json.loads((study/'fit_results/provenance.json').read_text())
    assert provenance['input_sha256'] == sha(study/'inputs/candidates.csv')
    artifact = study/'artifacts'
    pairs = 0
    if (artifact/'en').exists() and (artifact/'de').exists():
        english = {p.name for p in (artifact/'en/tables').glob('*.csv')}
        german = {p.name for p in (artifact/'de/tables').glob('*.csv')}
        assert english == german and english
        for name in sorted(english):
            with (artifact/'en/tables'/name).open() as f:
                en = list(csv.reader(f))[1:]
            with (artifact/'de/tables'/name).open() as f:
                de = list(csv.reader(f))[1:]
            assert len(en) == len(de)
            for a, b in zip(en, de):
                assert len(a) == len(b)
                for x, y in zip(a, b):
                    if re.fullmatch(r'-?\d+(\.\d+)?', x):
                        assert x == y
            pairs += 1
    payload = json.loads((artifact/'FIGURE_DATA.json').read_text())
    assert payload['counts'] == counts
    assert payload['budgets'] == payload['training_budgets'] == [1, 3, 5]
    summary = pd.read_csv(study/'fit_results/primary/summary.csv')
    expected_curves = summary[(summary.accelerator == 'all') & (summary.group_scope == 'all_available')
                              & summary.method.isin(['boundary_size', 'weighted_default', 'global'])
                              & summary.k.isin([1, 3, 5])].to_dict(orient='records')
    assert payload['curves'] == expected_curves
    for member, digest in payload['source_sha256'].items():
        assert sha(study/member) == digest
    check_file_manifest(artifact, 'MANIFEST.json')
    check_file_manifest(study, 'MANIFEST.json')
    result = dict(schema='generic420-verification-v2', candidate_count=len(d), eligible_count=int(d.analysis_eligible.sum()),
                  groups=counts['nonempty_eligible_groups'], counts=counts, fits=fit_results,
                  model_holdout_and_training_bytes_dominance_checked=sum(v['folds'] for v in fit_results.values()),
                  metrics_checked=sum(v['metrics'] for v in fit_results.values()), summary_reproduced=True,
                  localized_numeric_table_pairs_checked=pairs)
    (study/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--study', type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(verify(args.study)))
