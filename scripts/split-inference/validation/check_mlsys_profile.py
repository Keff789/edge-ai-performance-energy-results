#!/usr/bin/env python3
"""Independent R22 identities/cohorts plus fresh recomputation of every export."""
import argparse
import collections
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from publication_mlsys import build_profile, INPUT_ROOT, OUTPUT_ROOT


def read(path):
    return json.loads(path.read_text())


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (actual, expected)


def check_inventory(repo, output):
    profile = output / OUTPUT_ROOT
    manifest = read(profile/'ASSET_MANIFEST.json')
    spec = read(repo/INPUT_ROOT/'asset_spec.json')
    assert (manifest['occurrence_count'], manifest['unique_asset_count'],
            manifest['figure_count'], manifest['table_count']) == (37, 36, 8, 28)
    assets = manifest['assets']
    assert len({a['asset_id'] for a in assets}) == 36
    assert collections.Counter((r['label'], r['document'], r['tex_path'])
                               for a in assets for r in a['occurrences']) == collections.Counter(
        (r['label'], r['document'], r['tex_path']) for r in spec['occurrences'])
    assert collections.Counter((r['document'], a['kind']) for a in assets for r in a['occurrences']) == {
        ('main.tex','figure'):5, ('main.tex','table'):7, ('supplement.tex','figure'):3, ('supplement.tex','table'):22}
    registered = []
    full = (output/'figures').is_dir()
    for asset in assets:
        assert asset['generator'] and asset['data_generation'] and asset['verification']
        assert asset['input_files'], asset['asset_id']
        for source in asset['input_files']:
            path = Path(source)
            assert not path.is_absolute() and '..' not in path.parts, source
            assert (repo/path).exists(), source
        paths = asset['outputs']
        assert asset['repo_targets'] == ['results/split-inference/'+str(OUTPUT_ROOT/p) for p in paths]
        suffixes = {Path(p).suffix for p in paths}
        if asset['kind'] == 'figure':
            assert {'.pdf','.svg','.png','.json'} <= suffixes, asset['asset_id']
            if asset['asset_id'] != 'fig:runners':
                assert '.csv' in suffixes and asset['input_uids'], asset['asset_id']
            else:
                assert '.csv' not in suffixes
        else:
            assert {'.tex','.md','.json'} <= suffixes, asset['asset_id']
            data = read(profile/next(p for p in paths if p.endswith('.json')))
            if not (isinstance(data,dict) and data.get('kind') == 'methods_description'):
                assert '.csv' in suffixes and asset['input_uids'], asset['asset_id']
        for relative in paths:
            assert not Path(relative).is_absolute() and '..' not in Path(relative).parts
            if full or Path(relative).suffix not in {'.pdf','.svg','.png'}:
                assert (profile/relative).is_file(), relative
        registered += paths
    assert len(registered) == len(set(registered)), 'Two assets share an output'
    index = read(profile/'figures/INDEX.json')
    assert len(index) == 8
    payload = read(profile/'figures/FIGURE_DATA.json')
    assert set(payload) == {f['name'] for f in index}
    for figure in index:
        assert payload[figure['name']] == read(profile/'figures'/(figure['name']+'.json'))
    return manifest


def check_science(output):
    """Derive selection and denominator checks directly, without selector imports."""
    profile = output/OUTPUT_ROOT
    rows = read(output/'data/PAPER_DATASET.json')
    by_uid = {r['uid']:r for r in rows}
    assert len(rows) == len(by_uid) == 450
    quality = lambda r: (r['quality_reference_value']-r['quality_value'])/r['quality_reference_value'] <= .05
    admitted = [r for r in rows if quality(r)]
    assert collections.Counter((r['kind'],r['runner']) for r in admitted) == {
        ('split','native'):187,('split','generic'):187,('full','native'):33}
    winners = read(profile/'tables/best_cases_table.json')
    assert len(winners) == 7
    fastest = lambda rr: min(rr,key=lambda r:(-r['fps'],r['uid']))
    for winner in winners:
        pool = [r for r in admitted if r['model_id'] == winner['model']]
        split = fastest([r for r in pool if r['kind'] == 'split'])
        full = fastest([r for r in pool if r['kind'] == 'full'])
        host = fastest([r for r in pool if r['kind'] == 'full' and r['physical_host'] == split['physical_host']])
        assert (winner['split_uid'],winner['full_uid'],winner['host_full_uid']) == (split['uid'],full['uid'],host['uid'])
        close(winner['R_global'],split['fps']/full['fps'])
        close(winner['R_host'],split['fps']/host['fps'])
        close(winner['split_mj'],1000*split['energy_j_per_image'])
        close(winner['energy_ratio'],split['energy_j_per_image']/full['energy_j_per_image'])
    assert sum(w['R_global']>1 for w in winners) == 6
    assert sum(w['R_global']>1 and w['energy_ratio']<1 for w in winners) == 3
    assert 'yolo26m' in {w['model'] for w in winners}
    identity = lambda r:(r['model_id'],r['setup_id'],r['backend'],r['case_id'])
    generic = {identity(r):r for r in admitted if r['kind']=='split' and r['runner']=='generic'}
    pairs = [(n,generic[identity(n)]) for n in admitted if n['kind']=='split' and n['runner']=='native']
    assert len(pairs) == 187
    losses=[]; hits=0
    for (model,setup), group in __import__('itertools').groupby(
            sorted(pairs,key=lambda p:(p[0]['model_id'],p[0]['setup_id'])),
            key=lambda p:(p[0]['model_id'],p[0]['setup_id'])):
        group=list(group)
        best=fastest([n for n,g in group])
        chosen=min(group,key=lambda p:(-p[1]['fps'],p[1]['uid']))[0]
        loss=100*(1-chosen['fps']/best['fps'])
        actual=next(r for r in read(profile/'data/quality_selection_groups.json') if (r['model'],r['setup'])==(model,setup))
        assert actual['selected_native_uid']==chosen['uid'] and actual['native_best_uid']==best['uid']
        assert actual['candidate_count']==len(group)
        close(actual['loss_pct'],loss)
        losses.append(loss);hits+=chosen['fps']==best['fps']
    assert len(losses)==21 and hits==9
    close(math.fsum(losses)/len(losses),15.077128973324962)
    for row in read(profile/'tables/full_performance_table.json'):
        pool=[r for r in rows if r['model_id']==row['model'] and r['backend']=='native_full_tensorrt']
        assert len(pool)==3
        close(row['trt_fps'],statistics.mean(r['fps'] for r in pool))
        close(row['trt_mj'],statistics.mean(r['energy_mj_per_image'] for r in pool))
    for row in read(profile/'tables/vendor_quality_recovery_table.json'):
        split,full=by_uid[row['split_uid']],by_uid[row['full_uid']]
        close(row['quality_difference_pp'],100*(split['quality_value']-full['quality_value']))
        close(row['split_quality'],100*split['quality_value'])
    ranges=read(profile/'tables/r21_winner_repeat_ranges.json')
    assert len(ranges)==16
    assert sum(len(r['fps_repeats']) for r in ranges)==sum(len(r['energy_repeats_mj_per_image']) for r in ranges)==48
    for row in ranges:
        close(statistics.median(row['fps_repeats']),by_uid[row['uid']]['fps'])
        close(statistics.mean(row['energy_repeats_mj_per_image']),by_uid[row['uid']]['energy_mj_per_image'])
        assert len(row['energy_repeat_source_bindings'])==3
    historical=read(profile/'data/historical_yolo11l_windows.json')
    old=historical['historical_same_window']
    # Full-precision R21 energy-window oracles; kept separate from current medians.
    close(old['split']['fps'],37.09576116064978)
    close(old['full']['fps'],35.52575537369155)
    close(old['split']['energy_mj'],641.5540217558388)
    close(old['full']['energy_mj'],707.3628164913566)
    assert historical['current_deployment_candidate_check']['full_still_faster_and_lower_energy']
    return {'configurations':450,'quality_admissible':407,'quality_pairs':187,'equal_weight_groups':21,
            'fps_repeats':48,'energy_repeats':48,'globally_faster':6,'globally_faster_and_lower_energy':3}


def validate(repo, output):
    repo, output = Path(repo),Path(output)
    manifest=check_inventory(repo,output)
    science=check_science(output)
    # Independent generators recompute from canonical source records; compare
    # every registered payload/table/figure coordinate, not only headline values.
    with tempfile.TemporaryDirectory(prefix='mlsys-profile-check-') as temp:
        fresh=Path(temp)
        # Only the broad shared data/tables are input; no profile outputs copied.
        import shutil
        for name in ['data','tables']:
            shutil.copytree(output/name,fresh/name)
        build_profile(repo,fresh,numeric_only=True)
        expected={str(p.relative_to(fresh/OUTPUT_ROOT)):p.read_bytes()
                  for p in (fresh/OUTPUT_ROOT).rglob('*') if p.is_file()}
        actual={str(p.relative_to(output/OUTPUT_ROOT)):p.read_bytes()
                for p in (output/OUTPUT_ROOT).rglob('*') if p.is_file() and p.suffix not in {'.pdf','.svg','.png'}}
        assert expected==actual, {'missing':sorted(expected.keys()-actual.keys()),
                                 'unexpected':sorted(actual.keys()-expected.keys()),
                                 'different':sorted(k for k in expected.keys()&actual.keys() if expected[k]!=actual[k])}
    return dict(status='PASS',unique_assets=manifest['unique_asset_count'],
                recomputed_profile_files=len(expected),**science)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(validate(args.repo,args.output),sort_keys=True))
