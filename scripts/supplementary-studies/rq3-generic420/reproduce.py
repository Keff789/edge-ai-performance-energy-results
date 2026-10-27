#!/usr/bin/env python3
"""Build an additive Generic420 study from a frozen SM2 export or curated inputs."""
import argparse
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import subprocess
import sys
import platform
from verify import verify_inputs

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
DEFAULT_STUDY=REPO/'results/supplementary-studies/rq3-generic420-detector-corrected-20261027'


def run(script,*args):
    subprocess.run([sys.executable,'-B',str(HERE/script),*map(str,args)],check=True)


def write_readme(output, meta):
    c=meta['counts']
    pending = c['fps_pending'] or c['quality_pending_measured']
    pool_note = (
        'Open decisions remain excluded; this is not a final full-quality universe. '
        if pending else
        'All selected cases have a resolved measured-quality or technical-exclusion status. '
    )
    try:
        input_path = (output.resolve()/'inputs').relative_to(REPO.resolve()).as_posix()
    except ValueError:
        input_path = '<STUDY>/inputs'
    with (output/'fit_results/primary/summary.csv').open() as stream:
        summary=list(csv.DictReader(stream))
    rows=[r for r in summary if r['task']=='all' and r['accelerator']=='all' and r['group_scope']=='all_available']
    names={'boundary_size':'Boundary size','weighted_default':'Standard (1, 3, 0.2)',
           'global':'Shared fitted weights','task':'Fit by task','device':'Fit by accelerator',
           'task_device':'Fit by task and accelerator'}
    lines=['# Generic420 RQ3: published conditional analysis','',
           f"Status: **{meta['status']}**. {c['selected']} selected configurations; {c['fps_measured']} accepted FPS medians; "
           f"{c['eligible']} quality-eligible cuts in {c['nonempty_eligible_groups']} model–accelerator groups. "
           f"{c['quality_fail_measured']} measured quality failures, {c['quality_pending_measured']} measured quality decisions pending, "
           f"{c['technical_excluded']} technical exclusions and {c['fps_pending']} FPS measurements pending.",'',
           'The candidate pool is conditional on available, quality-eligible measurements. '
           'Historical quality is not a current endpoint admission. ' + pool_note +
           'Pending identities and historical roles are in '
           '`inputs/feature_metadata.json`. Native measurements are unchanged.','',
           'Mean held-out Generic throughput loss (%); every model–accelerator group has equal weight:', '',
           '| Ranking | 1 cut | 3 cuts | 5 cuts | Mean at 1, 3, 5 |',
           '| --- | ---: | ---: | ---: | ---: |']
    for method,label in names.items():
        values=[float(next(r['mean_loss_pct'] for r in rows if r['method']==method and int(r['k'])==k)) for k in [1,3,5]]
        lines.append('| '+label+' | '+' | '.join(f'{v:.6f}' for v in [*values,sum(values)/3])+' |')
    lines+=['','Learned rankings hold out the complete model on every accelerator. One training fit '
            'minimizes mean loss at budgets 1, 3 and 5, and supplies the same ranking at all budgets. '
            'The primary simplex grid has step 0.0025 and includes the exact standard and pure boundary-size weights. '
            'Full-data weights are descriptive training fits, separate from held-out performance.','',
            'From the repository root, rebuild all five analyses and EN/DE figures from these published inputs:', '',
            '```bash','python -B scripts/supplementary-studies/rq3-generic420/reproduce.py \\',
            f'  --inputs "{input_path}" \\',
            '  --output /tmp/generic420-reproduced --languages en de','```','',
            'Verify a completed study with `scripts/supplementary-studies/rq3-generic420/verify.py --study STUDY`. '
            'Dependencies and the detailed scoring, holdout and sensitivity protocol are in '
            '`scripts/supplementary-studies/rq3-generic420/README.md`. No private snapshot is needed for this rebuild.','']
    (output/'README.md').write_text('\n'.join(lines))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    source=ap.add_mutually_exclusive_group()
    source.add_argument('--source',type=Path,help='Read-only extracted SM2 export; verify manifest, ledger, frozen selection and all feature identities')
    source.add_argument('--inputs',type=Path,default=DEFAULT_STUDY/'inputs',help='Previously prepared canonical inputs')
    ap.add_argument('--output',type=Path,required=True,help='New study directory; an existing nonempty directory is rejected')
    ap.add_argument('--languages',nargs='+',choices=['en','de'],default=['en','de'])
    ap.add_argument('--skip-sensitivity',action='store_true')
    ap.add_argument('--numeric-only',action='store_true')
    ap.add_argument('--published-features',type=Path)
    ap.add_argument('--published-normalization',type=Path)
    a=ap.parse_args()
    if a.output.exists() and any(a.output.iterdir()):raise ValueError('Use a fresh output directory')
    a.output.mkdir(parents=True,exist_ok=True)
    if a.source:
        extra=[]
        if a.published_features:extra+=['--published-features',a.published_features]
        if a.published_normalization:extra+=['--published-normalization',a.published_normalization]
        run('prepare_inputs.py','--source',a.source,'--out',a.output/'inputs',*extra)
    else:
        (a.output/'inputs').mkdir()
        for name in ['candidates.csv','graph_universe.csv','coverage.csv','feature_metadata.json','published_feature_provenance.json']:
            shutil.copyfile(a.inputs/name,a.output/'inputs'/name)
    verify_inputs(a.output)
    run('fit_weights.py','--input',a.output/'inputs/candidates.csv','--out',a.output/'fit_results',*(['--skip-sensitivity'] if a.skip_sensitivity else []))
    run('render_artifacts.py','--study',a.output,'--out',a.output/'artifacts','--languages',*a.languages,*(['--numeric-only'] if a.numeric_only else []))
    run('verify.py','--study',a.output)
    meta=json.loads((a.output/'inputs/feature_metadata.json').read_text())
    write_readme(a.output,meta)
    files={p.relative_to(a.output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(a.output.rglob('*')) if p.is_file()}
    manifest={'schema':'generic420-study-v1','status':meta.get('status','preliminary'),'counts':meta['counts'],
              'target':'Generic throughput only; Native observations are unchanged',
              'environment':{'python':platform.python_version(),**{name:version(name) for name in ['numpy','pandas','matplotlib']}},
              'analysis_scripts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.glob('*.py'))},
              'requirements_sha256':hashlib.sha256((HERE/'requirements.txt').read_bytes()).hexdigest(),'files':files}
    (a.output/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'output':str(a.output),'status':manifest['status'],'counts':manifest['counts']}))

if __name__=='__main__':main()
