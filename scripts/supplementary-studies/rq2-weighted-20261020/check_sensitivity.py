#!/usr/bin/env python3
"""Check fixed learned/default rankings under changed new-operation costs."""
import argparse
import json
from pathlib import Path
import pandas as pd
from analyze_weighted import DEFAULT_ALPHA, SHARED_RATIO, groups, load_bound_features, weighted_order


def run(repo,export,results):
    summary=json.loads((results/'summary.json').read_text())
    data,_=load_bound_features(repo,export)
    main=data[data.quality_pass]
    folds={r['held_out_model']:r['alpha'] for r in summary['folds']}
    methods={'weighted_default':lambda model:DEFAULT_ALPHA,
             'weighted_shared':lambda model:SHARED_RATIO/(1+SHARED_RATIO),
             'weighted_pooled':lambda model:summary['pooled_fit']['selected']['alpha'],
             'weighted_cv':lambda model:folds[model]}
    base={}
    for (model,setup),g in groups(main):
        for method,alpha in methods.items():
            base[(model,setup,method)]=g.config_id.iloc[weighted_order(g,alpha(model))].tolist()
    reports=[]
    for variant in ['new_ops_x0_1','new_ops_x10']:
        path=export/'sensitivity'/variant
        data,_=load_bound_features(repo,path)
        alternative=data[data.quality_pass]
        assert set(main.config_id)==set(alternative.config_id)
        changed=[]
        for (model,setup),g in groups(alternative):
            for method,alpha in methods.items():
                ranking=g.config_id.iloc[weighted_order(g,alpha(model))].tolist()
                if ranking!=base[(model,setup,method)]:
                    changed.append({'model':model,'setup':setup,'method':method,'baseline_order':base[(model,setup,method)],'alternative_order':ranking})
        reports.append({'variant':variant,'checked_groups':len(groups(alternative)),'checked_methods':list(methods),
                        'complete_ranking_comparisons':len(base),'changed_rankings':changed,
                        'result':'unchanged_at_fixed_weights' if not changed else 'rank_changes_require_followup'})
    report={'scope':'Only costs added by analytic-operation-proxy-r29-extended-v1 are scaled. Graph identities, measurements, communication sizes and previous operation counts remain fixed.',
            'weights':'Use exact main-run default, frozen shared, pooled and each held-out fold weights without refitting.',
            'reports':reports}
    (results/'sensitivity_fixed_weights.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if any(r['changed_rankings'] for r in reports):
        raise SystemExit('Fixed-weight rank changes detected; refit before final claims.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--export',type=Path,required=True)
    p.add_argument('--results',type=Path,required=True)
    a=p.parse_args();run(a.repo.resolve(),a.export.resolve(),a.results.resolve())
