#!/usr/bin/env python3
"""Reproduce all-cut RQ2 rankings, budgets and finite-set success curves offline.

The numerical engines retain the audited calculations. This entry point binds
their inputs to existing repository sources, uses temporary working inputs, and
publishes only derived results. It never measures hardware or refits a proxy.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUDY = Path('results/supplementary-studies/rq2-all-cuts-20261020')
AUDIT = Path('results/split-inference/publication-inputs/mlsys-r22/evidence/r15/audit_regnet/results')
PUB = Path('results/split-inference/publications/mlsys-r22')
GRAPH = Path('results/supplementary-studies/thesis20-ranking-20261005')
OLD = Path('results/supplementary-studies/mlsys-selection-20261007/inputs/analysis')
SOURCE_COMMIT = 'b10d15992d0ce45d0f81329a5e961cb6207a1d09'


def module(name):
    spec = importlib.util.spec_from_file_location('rq2_'+name, HERE/(name+'.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def stage(folder, mapping):
    folder.mkdir(parents=True, exist_ok=True)
    for name, source in mapping.items():
        shutil.copyfile(source, folder/name)


def derived_files(path):
    return sorted(p for p in path.rglob('*') if p.is_file()
                  and 'inputs' not in p.relative_to(path).parts)


def read_csv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def check_success_matches_loss(output):
    """Different engines must agree on every exact-optimum hit probability."""
    current = read_csv(output/'current/all_k_group_curves.csv')
    success = read_csv(output/'success/current/group_success_curves.csv')
    key = lambda r: (r['view'],r['model'],r['setup'],r['method'],r['k'])
    target = {key(r):float(r['success_fraction']) for r in success
              if float(r['loss_tolerance_pct']) == 0}
    assert len(target) == len(current) == 1386
    for row in current:
        assert float(row['winner_coverage']) == target[key(row)]

    graph = read_csv(output/'historical/historical_shortlist_group_curves.csv')
    success = read_csv(output/'success/graph_rules/success_by_group_and_budget.csv')
    key = lambda r: (r['model'],r['setup'],r['method'],r['k'])
    target = {key(r):float(r['success_probability']) for r in success
              if r['criterion'] == 'exact_optimum'}
    assert len(target) == len(graph) == 1428
    for row in graph:
        assert abs(float(row['native_winner_coverage'])-target[key(row)]) < 1e-15
    return {'current_exact_optimum_rows':len(current),
            'graph_exact_optimum_rows':len(graph),
            'result':'PASS'}


def verify_published(output):
    """Compare regenerated scientific data to the committed reference files."""
    reference = REPO/STUDY
    if not reference.exists():
        raise RuntimeError('Published results do not exist yet; omit --verify for the first build.')
    checked = []
    for name in ['current','historical','success','tables','figures']:
        for path in sorted((output/name).rglob('*')):
            if not path.is_file() or path.suffix not in ('.csv','.json','.tex'):
                continue
            relative = path.relative_to(output)
            expected = reference/relative
            if not expected.is_file():
                raise AssertionError(f'Missing published reference: {relative}')
            if path.read_bytes() != expected.read_bytes():
                raise AssertionError(f'Reproduction differs: {relative}')
            checked.append(str(relative))
    return {'result':'PASS','mode':'byte comparison of scientific CSV/JSON/TeX, including figure coordinates',
            'files_checked':len(checked),'files':checked}


def asset_manifest(output, numeric_only):
    figures = [
        ('rq2_shortlist_curves', 'fig:rq2-shortlists',
         ['historical/historical_shortlist_summary.csv','current/fixed_group_budget_curves.csv'],
         'Separate nine-group classifier curves: 168 graph-score cuts and 151 quality-eligible current cuts.'),
        ('rq2_graph_analysis','fig:supp-graph-analysis',
         ['historical/historical_rank_correlations.csv','historical/historical_shortlist_summary.csv',
          'success/graph_rules/success_summary.csv'],
         'Nine fixed graph-score classifier groups with all 168 measured cuts.'),
        ('rq2_native_success','fig:supp-native-search-success',
         ['success/current/fixed_group_success_curves.csv'],
         'Nine current quality-eligible classifier groups with 151 cuts.'),
    ]
    assets=[]
    for name,label,inputs,scope in figures:
        assets.append({'name':name,'tex_label':label,'kind':'figure',
            'generator':'scripts/supplementary-studies/rq2-all-cuts-20261020/paper_assets.py:run',
            'inputs':inputs,'scope':scope,'outputs':[] if numeric_only else
            ['figures/'+name+'.'+extension for extension in ['pdf','svg','png']],
            'coordinates':None if numeric_only else 'figures/RQ2_FIGURE_DATA.json',
            'rendered':not numeric_only})
    assets.append({'name':'rq2_search_budget_table','tex_label':'tab:rq2-search-budgets',
        'kind':'table','generator':'scripts/supplementary-studies/rq2-all-cuts-20261020/paper_assets.py:write_table',
        'inputs':['success/graph_rules/required_budgets.csv','success/current/minimum_budgets_for_target_success.csv'],
        'scope':'Both classifier measurement sets reported separately.',
        'outputs':['tables/rq2_search_budget_table.'+extension for extension in ['csv','json','tex']]})
    manifest={'analysis':'rq2-all-cuts-20261020','assets':assets,
        'verification':'Regenerated scientific values are checked against committed files with --verify. Figure coordinates are included in full mode.',
        'scope':'Exact and near-optimal success use each measurement set\'s own Native optimum. Neither dataset is a complete graph survey.'}
    (output/'ASSET_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')


def run(output, numeric_only=False, verify=False):
    if output.exists() and any(output.iterdir()):
        raise RuntimeError('Choose an empty or nonexistent output directory.')
    output.mkdir(parents=True,exist_ok=True)
    inputs = {
        'calibration_candidate_audit.csv': REPO/AUDIT/'calibration_candidate_audit.csv',
        'calibration_predictions.csv': REPO/AUDIT/'calibration_predictions.csv',
        'published_calibration_groups.csv': REPO/PUB/'data/r15_calibration_groups.csv',
    }
    graph_inputs = {
        'method_availability.csv': REPO/GRAPH/'inputs/method_availability.csv',
        'method_parameters.json': REPO/GRAPH/'inputs/method_parameters.json',
        'stage_cost_source_README.md': REPO/'results/supplementary-studies/stage-cost-composition/README.md',
    }
    source_paths = set(inputs.values()) | set(graph_inputs.values()) | {
        REPO/OLD/'evidence/tables/rank_cases.csv',
        REPO/OLD/'reported_update/reported_results.csv',
        REPO/GRAPH/'inputs/method_candidate_scores.csv',
        REPO/PUB/'data/historical_selector_groups.csv',
        REPO/PUB/'tables/ranking_tables.csv',
    }
    manifest = {
        'source_commit':SOURCE_COMMIT,
        'source_binding':'Existing public compact inputs; no external model or measurement files.',
        'sources':[{'path':str(p.relative_to(REPO)),
                    'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                   for p in sorted(source_paths)],
        'derived_input_bindings':[
            {'consumer':'success/graph_rules','input':'graph_rule_cuts.csv',
             'generated_from':'historical/historical_cuts.csv'},
            {'consumer':'success/graph_rules','input':'source_provenance.json',
             'generated_from':'historical/historical_provenance.json'}],
        'cohorts':'Graph-score and current Native/A4 results use separate runtime references.',
    }
    (output/'INPUT_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    log = io.StringIO()
    with tempfile.TemporaryDirectory(prefix='rq2-all-cuts-') as temporary:
        work = Path(temporary)
        with contextlib.redirect_stdout(log):
            current = module('analyze_current')
            current.ROOT = work/'current'
            stage(current.ROOT/'inputs',inputs)
            current.main()

            graph = module('analyze_graph_rules')
            graph.run(REPO,work/'historical')

            current_success = module('success_current')
            current_success.ROOT = work/'success/current'
            stage(current_success.ROOT/'inputs',{
                key:value for key,value in inputs.items() if key!='published_calibration_groups.csv'})
            current_success.main()

            graph_success = module('success_graph_rules')
            graph_work = work/'success/graph_rules'
            stage(graph_work/'inputs',dict(graph_inputs,
                graph_rule_cuts=work/'historical/historical_cuts.csv'))
            # The frozen success engine expects the original two input names.
            (graph_work/'inputs/graph_rule_cuts').rename(graph_work/'inputs/graph_rule_cuts.csv')
            shutil.copyfile(work/'historical/historical_provenance.json',
                            graph_work/'inputs/source_provenance.json')
            graph_success.run(graph_work/'inputs',graph_work)
        for path in derived_files(work):
            target = output/path.relative_to(work)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)

    checks = check_success_matches_loss(output)
    module('documentation').run(output)
    renderer = module('paper_assets')
    renderer.run(output,output,numeric_only)
    asset_manifest(output,numeric_only)
    if verify:
        checks['published_reference'] = verify_published(output)
    import numpy, pandas, scipy
    environment = {'python':platform.python_version(),'numpy':numpy.__version__,
                   'pandas':pandas.__version__,'scipy':scipy.__version__,
                   'numeric_only':numeric_only}
    if not numeric_only:
        import matplotlib
        environment['matplotlib'] = matplotlib.__version__
    (output/'REPRODUCTION_ENVIRONMENT.json').write_text(json.dumps(environment,indent=2)+'\n')
    (output/'VALIDATION.json').write_text(json.dumps(checks,indent=2)+'\n')
    (output/'REPRODUCTION_LOG.txt').write_text(log.getvalue())
    print(json.dumps({'output':str(output),'checks':checks,
                      'mode':'numeric-only' if numeric_only else 'numerical results and figures'},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--numeric-only',action='store_true')
    parser.add_argument('--verify',action='store_true')
    args = parser.parse_args()
    run(args.output.resolve(),args.numeric_only,args.verify)
