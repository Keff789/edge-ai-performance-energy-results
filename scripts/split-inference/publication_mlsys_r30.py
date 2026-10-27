"""Current MLSys paper profile, preserving the registered frozen R22 view."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

PROFILE = 'mlsys-r30'
STUDY = Path('results/supplementary-studies/rq2-weighted-20261020')
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile_output_reference(repo, output):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    return output.relative_to(repo) if output.is_relative_to(repo) else Path('results/split-inference/publications') / PROFILE


def bind_output_targets(assets, repo, output):
    reference = profile_output_reference(repo, output)
    for asset in assets:
        asset['repo_targets'] = [str(reference / name) for name in asset['outputs']]


def profile_output_hashes(output):
    return {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*'))
            if p.is_file() and p not in [output / 'PROVENANCE.json', output / 'README.md']}


def graph_display_policy():
    return {'figure': 'rq2_graph_analysis', 'excluded_methods': ['uniform_random'],
            'scope': 'Active R30 presentation only; the separate historical RQ2 graph-score numerical controls and archived studies remain unchanged.'}


def render_current_graph(repo, data_root, output):
    renderer = module(Path(repo) / 'scripts/supplementary-studies/rq2-all-cuts-20261020/paper_assets.py', 'rq2_current_graph_display')
    renderer.run(data_root, output, excluded_graph_methods=('uniform_random',))


def refresh_profile_metadata(repo, broad_output):
    """Rebind an existing profile's output authority without regenerating science."""
    repo = Path(repo).resolve()
    output = (Path(broad_output) / 'publications' / PROFILE).resolve()
    manifest = json.loads((output / 'ASSET_MANIFEST.json').read_text())
    bind_output_targets(manifest['existing_core_assets'], repo, output)
    if manifest.get('current_rq2_override'):
        manifest['existing_rq2_assets']['graph_display'] = graph_display_policy()
    (output / 'ASSET_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    provenance = json.loads((output / 'PROVENANCE.json').read_text())
    if manifest.get('current_rq2_override'):
        provenance['source_sha256']['scripts/supplementary-studies/rq2-all-cuts-20261020/paper_assets.py'] = ''
    provenance['source_sha256'] = {name: digest(repo / name) for name in provenance['source_sha256']}
    provenance['output_sha256'] = profile_output_hashes(output)
    (output / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return manifest


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def current_schematic(repo, output, numeric_only):
    """Render the maintained author vector; this is not the old R22 schematic."""
    source = repo / 'publications/mlsys/figure1/source.zip'
    with zipfile.ZipFile(source) as archive:
        vector = archive.read('analysis/system_overview.svg')
        provenance = json.loads(archive.read('analysis/system_overview_provenance.json'))
    payload = {'kind': 'conceptual_illustration',
               'source': 'publications/mlsys/figure1/source.zip',
               'archive_sha256': digest(source),
               'svg_sha256': hashlib.sha256(vector).hexdigest(),
               'scope': 'Supported boundary capabilities. Paired measurements use the same single-input cut.',
               'source_provenance': provenance}
    figures = output / 'figures'
    (figures / 'system_overview.json').write_text(json.dumps(payload, indent=2) + '\n')
    if not numeric_only:
        import fitz
        (figures / 'system_overview.svg').write_bytes(vector)
        with fitz.open(stream=vector, filetype='svg') as document:
            raw = document.convert_to_pdf()
        (figures / 'system_overview.pdf').write_bytes(raw)
        with fitz.open(stream=raw, filetype='pdf') as document:
            document[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).save(
                figures / 'system_overview.png')
    return payload


def final_rq2_files(study):
    """The only replaceable current RQ2 numerical assets in this profile."""
    result={}
    for folder in ['data','figures','tables']:
        for source in sorted((Path(study)/folder).glob('*')):
            if source.is_file():
                result[str(source.relative_to(study))]=source
    result['data/rq2_final_summary.json']=Path(study)/'summary.json'
    result['data/rq2_final_input_manifest.json']=Path(study)/'INPUT_MANIFEST.json'
    return result


def rq2_engine_source(repo, study):
    """Select the registered importer by the study schema, preserving old commands."""
    summary = json.loads((Path(study) / 'summary.json').read_text())
    engines = {'rq2-native-scope-pairs-v1':'rq2-native-scope-20261027',
               'rq2-final-pairs-v1':'rq2-generic-final-20261027'}
    if summary.get('schema') not in engines:
        raise ValueError('Unregistered RQ2 study schema: ' + str(summary.get('schema')))
    name = engines[summary['schema']]
    return Path(repo) / 'scripts/supplementary-studies' / name / 'reproduce.py'


def rq2_study_name(repo, study):
    try:
        return str(Path(study).resolve().relative_to(Path(repo).resolve()))
    except ValueError:
        return str(Path(study))


def current_rq2_asset_metadata(asset, repo, study):
    """Current figure provenance uses its current cohort; archive fields stay explicit."""
    study = Path(study)
    quality = any('quality_generic_selection_loss' in name for name in asset['outputs'])
    key = 'quality_pairs' if quality else 'current_pairs'
    figure_name = 'quality_generic_selection_loss' if quality else 'current_generic_selection_loss'
    pairs = json.loads((study / 'data' / (key + '.json')).read_text())
    figure = json.loads((study / 'figures' / (figure_name + '.json')).read_text())
    groups = {(row['model'], row['setup']) for row in pairs}
    asset['caption'] = figure['caption']
    asset['description'] = f"Current Generic-to-Native selection, {len(pairs)} verified pairs in {len(groups)} model/device groups"
    asset['input_uids'] = sorted({uid for pair in pairs for uid in [pair['native_uid'], pair['generic_uid']]})
    prefix = rq2_study_name(repo, study)
    asset['input_files'] = [prefix + '/INPUT_MANIFEST.json', prefix + '/data/' + key + '.json']
    asset['current_cohort'] = dict(verified_pairs=len(pairs), model_device_groups=len(groups),
        singleton_groups=sum(row.get('singleton', False) for row in figure['points']))
    asset['archived_reference_scope'] = 'Reference archive, original occurrences and reference captions retain their historical R22 scope; current cohort and input identities are given above.'
    asset['verification'] = 'Verified current study numerical reproduction and identity/accounting gates; archived R22 reference evidence is retained separately.'
    return asset


def current_weighted_scope(summary):
    return {'evaluated_quality_pairs':summary['quality_pair_count'],'model_device_groups':summary['quality_group_count'],
        'classifier_pairs':summary['classifier_quality_pairs'],'detector_pairs':summary['detector_quality_pairs'],
        'models':summary['models'],'groups_without_quality_pairs':summary['groups_without_quality_pairs'],
        'scope':summary['scope'],
        **{key:summary[key] for key in ['original_native_population','quality_singleton_groups','quality_groups_n_ge_2',
            'mean_final_generic_loss_n_ge_2_pct','publication_status'] if key in summary}}


def current_weighted_validation(study):
    study=Path(study);summary=json.loads((study/'summary.json').read_text())
    manifest=json.loads((study/'INPUT_MANIFEST.json').read_text())
    return {'result':'PASS','scope':current_weighted_scope(summary),'source_snapshot_sha256':manifest['source_snapshot_sha256'],
        'input_manifest_sha256':digest(study/'INPUT_MANIFEST.json'),'frozen_weights':summary['weights'],
        'weight_policy':summary['weight_policy'],'weights_refitted':False,'new_native_measurements':False,
        'refreshed_fps_joined_to_old_energy':False,
        'publication_status':summary.get('publication_status','historical_snapshot'),
        'validation_scope':'Offline reproduction and identity accounting; unresolved scientific evidence remains unresolved.'}


def apply_final_rq2(repo,output,study,numeric_only):
    study=Path(study).resolve()
    engine=module(rq2_engine_source(repo,study),'rq2_final_publication')
    with tempfile.TemporaryDirectory(prefix='rq2-final-profile-') as temporary:
        verified=Path(temporary)/'verified'
        summary=engine.run(verified,repo,numeric_only=numeric_only,verify_reference=study)
        for relative,source in final_rq2_files(verified).items():
            target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    payload=json.loads((output/'figures/FIGURE_DATA.json').read_text())
    for name in ['current_generic_selection_loss','quality_generic_selection_loss']:
        payload[name]=json.loads((output/'figures'/f'{name}.json').read_text())
    (output/'figures/FIGURE_DATA.json').write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n')
    legacy=json.loads((output/'figures/RQ2_FIGURE_DATA.json').read_text())
    for name in ['rq2_generic_selection_loss','rq2_native_success']:
        legacy[name]=json.loads((output/'figures'/f'{name}.json').read_text())
    (output/'figures/RQ2_FIGURE_DATA.json').write_text(json.dumps(legacy,sort_keys=True,indent=2)+'\n')
    broad_summary=json.loads((output/'data/summary.json').read_text())
    broad_summary.update(paired_candidates=summary['pair_count'],quality_paired_candidates=summary['quality_pair_count'],
        quality_groups=summary['quality_group_count'],quality_mean_loss_pct=summary['mean_final_generic_loss_pct'],
        quality_exact_hits=sum(r['exact_hit'] for r in json.loads((output/'data/quality_selection_groups.json').read_text())))
    (output/'data/summary.json').write_text(json.dumps(broad_summary,sort_keys=True,indent=2)+'\n')
    shutil.copyfile(output/'data/weighted_validation.json',output/'data/historical_weighted_validation.json')
    (output/'data/weighted_validation.json').write_text(json.dumps(current_weighted_validation(study),sort_keys=True,indent=2)+'\n')
    return summary


def verify_profile(repo, broad_output, rq2_study=None):
    output = broad_output / 'publications' / PROFILE
    old = repo / 'results/split-inference/publications/mlsys-r22/figures/FIGURE_DATA.json'
    assert (output / 'data/frozen_r22_figure_data.json').read_bytes() == old.read_bytes()
    frozen = json.loads(old.read_text())
    yolo = json.loads((output / 'figures/yolov7_h8_case_single_column.json').read_text())
    assert yolo == frozen['yolov7_h8_case']
    r22_checked = 0
    for actual in sorted((broad_output / 'publications/mlsys-r22').rglob('*')):
        if actual.suffix not in ['.csv', '.json', '.tex']:
            continue
        expected = repo / 'results/split-inference' / actual.relative_to(broad_output)
        assert actual.read_bytes() == expected.read_bytes(), f'Frozen R22 data changed: {actual.name}'
        r22_checked += 1
    target = repo / 'results/split-inference/publications' / PROFILE
    checked = []
    changed=final_rq2_files(Path(rq2_study)) if rq2_study else {}
    combined={'figures/FIGURE_DATA.json':['current_generic_selection_loss','quality_generic_selection_loss'],
              'figures/RQ2_FIGURE_DATA.json':['rq2_generic_selection_loss','rq2_native_success'],
              'data/summary.json':['paired_candidates','quality_paired_candidates','quality_groups','quality_mean_loss_pct','quality_exact_hits'],
              'data/profile_summary.json':['final_rq2_scope','weighted_scope','historical_weighted_scope','weighted_weight_policy']}
    if rq2_study:
        engine=module(rq2_engine_source(repo,rq2_study),'rq2_final_verify')
        with tempfile.TemporaryDirectory(prefix='rq2-final-verify-') as temporary:
            engine.run(Path(temporary)/'checked',repo,numeric_only=True,verify_reference=Path(rq2_study))
    for folder in ['figures', 'tables', 'data']:
        for actual in sorted((output / folder).glob('*')):
            if actual.suffix not in ['.csv', '.json', '.tex']:
                continue
            name = actual.relative_to(output)
            if rq2_study and str(name)=='data/weighted_validation.json':
                assert json.loads(actual.read_text())==current_weighted_validation(rq2_study),'Current weighted validation differs'
                checked.append(str(name));continue
            if rq2_study and str(name)=='data/historical_weighted_validation.json':
                historical=target/'data/historical_weighted_validation.json'
                if not historical.is_file():historical=target/'data/weighted_validation.json'
                assert actual.read_bytes()==historical.read_bytes(),'Historical weighted validation changed'
                checked.append(str(name));continue
            if str(name) in changed:
                assert actual.read_bytes()==changed[str(name)].read_bytes(),f'Final RQ2 asset differs: {name}'
                checked.append(str(name));continue
            if rq2_study and str(name) in combined:
                actual_data=json.loads(actual.read_text());expected_data=json.loads((target/name).read_text())
                for key in combined[str(name)]:
                    actual_data.pop(key,None);expected_data.pop(key,None)
                assert actual_data==expected_data,f'Unrelated frozen R30 values changed: {name}'
                if str(name)=='figures/FIGURE_DATA.json':
                    current=json.loads(actual.read_text())
                    for key in combined[str(name)]:
                        assert current[key]==json.loads((Path(rq2_study)/'figures'/f'{key}.json').read_text())
                elif str(name)=='figures/RQ2_FIGURE_DATA.json':
                    current=json.loads(actual.read_text())
                    for key in combined[str(name)]:
                        assert current[key]==json.loads((Path(rq2_study)/'figures'/f'{key}.json').read_text())
                elif str(name)=='data/profile_summary.json':
                    current=json.loads(actual.read_text());study_summary=json.loads((Path(rq2_study)/'summary.json').read_text())
                    previous=json.loads((target/name).read_text())
                    assert current['final_rq2_scope']==study_summary
                    assert current['weighted_scope']==current_weighted_scope(study_summary)
                    assert current['weighted_weight_policy']==study_summary['weight_policy']
                    assert current['historical_weighted_scope']==previous.get('historical_weighted_scope',previous['weighted_scope'])
                elif str(name)=='data/summary.json':
                    current=json.loads(actual.read_text());scope=json.loads((Path(rq2_study)/'summary.json').read_text())
                    expected_updates={'paired_candidates':scope['pair_count'],'quality_paired_candidates':scope['quality_pair_count'],
                        'quality_groups':scope['quality_group_count'],'quality_mean_loss_pct':scope['mean_final_generic_loss_pct'],
                        'quality_exact_hits':sum(r['exact_hit'] for r in json.loads((Path(rq2_study)/'data/quality_selection_groups.json').read_text()))}
                    assert all(current[k]==v for k,v in expected_updates.items()),'Refreshed RQ2 summary differs'
                checked.append(str(name));continue
            assert (target / name).is_file(), f'Missing R30 reference: {name}'
            assert actual.read_bytes() == (target / name).read_bytes(), f'R30 differs: {name}'
            checked.append(str(name))
    return {'result': 'PASS', 'files_checked': len(checked), 'frozen_r22_files_checked': r22_checked,
            'frozen_r22_numerical_payload_unchanged': True, 'yolo_payload_unchanged': True}


def build_profile(repo_root, broad_output, numeric_only=False, rq2_study=None):
    repo, broad_output = Path(repo_root), Path(broad_output)
    output = broad_output / 'publications' / PROFILE
    output.mkdir(parents=True, exist_ok=True)
    frozen = broad_output / 'publications/mlsys-r22'
    for folder in ['data', 'tables']:
        shutil.copytree(frozen / folder, output / folder, dirs_exist_ok=True)
    # This archival evidence report is already retained by R22. Its original
    # source-machine paths are not repeated in the current publication export.
    (output / 'data/r15_evidence_validation.json').unlink()
    (output / 'data/profile_summary.json').unlink()
    from publication_mlsys_data import build
    from publication_mlsys_figures import render, write_figure_data, PAPER_STYLE, PAPER_PALETTE
    from publication_mlsys_r30_assets import render_weighted, render_yolo_single_column, write_weighted_tables
    context = build(repo, broad_output, output)
    if numeric_only:
        _, payload = write_figure_data(output, context)
    else:
        _, payload = render(output, context, uniform_typography=True, uniform_palette=True)
    assert (output / 'figures/FIGURE_DATA.json').read_bytes() == (frozen / 'figures/FIGURE_DATA.json').read_bytes()
    shutil.copyfile(output / 'figures/FIGURE_DATA.json', output / 'data/frozen_r22_figure_data.json')
    assets = render_yolo_single_column(output, payload['yolov7_h8_case'], numeric_only)
    payload['system_overview'] = current_schematic(repo, output, numeric_only)
    (output / 'figures/FIGURE_DATA.json').write_text(json.dumps(payload, sort_keys=True, indent=2) + '\n')

    weighted_source = repo / 'scripts/supplementary-studies/rq2-weighted-20261020/reproduce.py'
    old_source = repo / 'scripts/supplementary-studies/rq2-all-cuts-20261020/reproduce.py'
    with tempfile.TemporaryDirectory(prefix='mlsys-r30-') as temporary:
        work = Path(temporary)
        weighted = module(weighted_source, 'rq2_weighted_reproduce')
        result = weighted.run(work / 'weighted', repo)
        result['published_comparison'] = weighted.verify_published(work / 'weighted', repo)
        (output / 'data/weighted_validation.json').write_text(json.dumps(result, indent=2) + '\n')
        assets.update(render_weighted(output, work / 'weighted/analysis', numeric_only))
        assets.update(write_weighted_tables(output, work / 'weighted/analysis'))
        # The active historical supplementary views keep their original scope.
        # Their temporary engine logs and duplicate datasets are not published.
        legacy = module(old_source, 'rq2_all_cuts_reproduce')
        with contextlib.redirect_stdout(io.StringIO()):
            legacy.run(work / 'all_cuts', numeric_only=numeric_only, verify=True)
        if rq2_study and not numeric_only:
            render_current_graph(repo, work / 'all_cuts', work / 'all_cuts')
        for stem in ['rq2_generic_selection_loss', 'rq2_native_success', 'rq2_graph_analysis']:
            for ext in ([] if numeric_only else ['pdf', 'svg', 'png']):
                shutil.copyfile(work / 'all_cuts/figures' / f'{stem}.{ext}', output / 'figures' / f'{stem}.{ext}')
        shutil.copyfile(work / 'all_cuts/figures/RQ2_FIGURE_DATA.json', output / 'figures/RQ2_FIGURE_DATA.json')
        for path in (work / 'all_cuts/tables').glob('rq2_search_budget_table.*'):
            shutil.copyfile(path, output / 'tables' / path.name)

    final_rq2=apply_final_rq2(repo,output,rq2_study,numeric_only) if rq2_study else None
    core_assets = json.loads((frozen / 'ASSET_MANIFEST.json').read_text())['assets']
    bind_output_targets(core_assets, repo, output)
    for asset in core_assets:
        if asset['asset_id'] == 'fig:runners':
            asset['generator'] = 'scripts/split-inference/publication_mlsys_r30.py:current_schematic'
            asset['caption'] = payload['system_overview']['scope']
            asset['data_generation'] = 'Maintained author vector source, replacing the frozen R22 schematic.'
        if final_rq2 and any('generic_selection_loss' in p for p in asset['outputs']):
            current_rq2_asset_metadata(asset, repo, rq2_study)
            asset['generator']=str(rq2_engine_source(repo,rq2_study).relative_to(repo))+':render'
            asset['data_generation']='Current compatible Generic observations with original artifact-bound Native measurements; study metadata records the observation policy and audit status.'
    manifest = {'profile': PROFILE, 'frozen_profile': 'mlsys-r22',
        'scope': 'Current paper presentation plus the seven-model weighted analysis; original measurements unchanged.',
        'existing_core_assets': core_assets,
        'core_presentation': 'Shared PAPER_STYLE/PAPER_PALETTE; frozen numerical payload stored in data/frozen_r22_figure_data.json.',
        'schematic_override': payload['system_overview'],
        'existing_rq2_assets': {'generator': str(old_source.relative_to(repo)),
                              'figures': ['rq2_generic_selection_loss', 'rq2_native_success', 'rq2_graph_analysis'],
                              'tables': ['rq2_search_budget_table'], 'scope': 'Unchanged separate current/historical cohorts.'},
        'new_assets': assets, 'study': str(STUDY),
        'numeric_only': numeric_only}
    if final_rq2:
        manifest['current_rq2_override']={'study':rq2_study_name(repo,rq2_study),
            'scope':final_rq2,'frozen_rq1_and_yolov7':True,
            'asset_files':sorted(final_rq2_files(Path(rq2_study)))}
        manifest['scope']='Frozen RQ1 and YOLOv7 evidence; current RQ2 recomputed using the verified study population and observation policy.'
        manifest['existing_rq2_assets']['historical_graph_generator']=str(old_source.relative_to(repo))
        manifest['existing_rq2_assets']['generator']=str(rq2_engine_source(repo,rq2_study).relative_to(repo))
        manifest['existing_rq2_assets']['graph_display']=graph_display_policy()
        manifest['existing_rq2_assets']['scope']='Current Generic scatter, Native success and search budgets use the verified original Native population study; historical graph campaign remains unchanged.'
        for name in ['rq2_weighted_all_models','r30_weighted_budget_table','r30_weighted_macros']:
            if name in assets:
                assets[name]['caption']='Current Generic / original Native verified pairs, frozen prior graph weights. See data/rq2_final_summary.json for counts, singleton groups, pending evidence and quality contract limitations.'
                assets[name]['generator']=str(rq2_engine_source(repo,rq2_study).relative_to(repo))+':render'
                assets[name]['source_sha256']={'rq2_final_input_manifest':digest(Path(rq2_study)/'INPUT_MANIFEST.json'),
                    'rq2_final_summary':digest(Path(rq2_study)/'summary.json')}
                if 'optimized_status' in assets[name]:assets[name]['optimized_status']='Frozen prior shared weights; no fit on the current paired subset.'
                if 'held_out_status' in assets[name]:assets[name]['held_out_status']='Frozen prior model-held-out vectors; prior training scope retained separately.'
    (output / 'ASSET_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    profile_summary={
        'profile': PROFILE, 'frozen_numerical_profile': 'mlsys-r22',
        'weighted_scope': result['scope'], 'weighted_weights': result['weights'],
        'new_asset_ids': sorted(assets), 'measurement_changes': False,
        'old_evidence_reference': 'results/split-inference/publications/mlsys-r22/data/r15_evidence_validation.json'
    }
    if final_rq2:
        profile_summary['final_rq2_scope']=final_rq2
        profile_summary['historical_weighted_scope']=profile_summary['weighted_scope']
        profile_summary['weighted_scope']=current_weighted_scope(final_rq2)
        profile_summary['weighted_weight_policy']=final_rq2['weight_policy']
    (output / 'data/profile_summary.json').write_text(json.dumps(profile_summary, indent=2) + '\n')
    sources = [HERE / 'publication_mlsys_r30.py', HERE / 'publication_mlsys_r30_assets.py',
               HERE / 'publication_mlsys_figures.py', weighted_source, old_source]
    if final_rq2:
        sources.append(rq2_engine_source(repo,rq2_study))
        sources.append(old_source.parent / 'paper_assets.py')
    provenance = {'schema': 'mlsys-r30-publication-v1', 'paper_style': PAPER_STYLE,
        'paper_palette': PAPER_PALETTE, 'measurement_changes': False,
        'source_sha256': {str(p.relative_to(repo)): digest(p) for p in sources},
        'input_sha256': {str(STUDY / 'inputs/MANIFEST.json'): digest(repo / STUDY / 'inputs/MANIFEST.json'),
                         'publications/mlsys/figure1/source.zip': digest(repo / 'publications/mlsys/figure1/source.zip')},
        'output_sha256': profile_output_hashes(output)}
    if final_rq2:
        provenance['input_sha256'][rq2_study_name(repo,rq2_study)+'/INPUT_MANIFEST.json']=digest(Path(rq2_study)/'INPUT_MANIFEST.json')
    (output / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (output / 'README.md').write_text(f'''# MLSys R30 paper assets

Generated with `python -I -B scripts/split-inference/reproduce.py --publication mlsys-r30 --output <empty-directory> --verify`.
Add `--numeric-only` to omit image rendering. The default registered R22 profile remains unchanged.

The core measurement figures use the common paper style and their frozen R22 numerical data.
The author boundary illustration is regenerated from its maintained vector source.
Both wide and single-column YOLOv7 case figures are included, with identical numbers.
The historical weighted figure and tables use {result['scope']['evaluated_quality_pairs']} quality-eligible measured pairs in {result['scope']['model_device_groups']} groups.
The historical optimized weights are fitted across {len(result['scope']['models'])} models; held-out results exclude one entire model at a time.
The new main weighted figure has no Random curve. Existing historical supplementary evidence keeps its original scope.

Inputs, operation rules, fold memberships, exact results and sensitivity checks are in
`results/supplementary-studies/rq2-weighted-20261020`.
`ASSET_MANIFEST.json` maps assets to generators. `PROVENANCE.json` records hashes.
''')
    if final_rq2:
        (output/'README.md').write_text(f"""# MLSys R30 with current Generic RQ2 evidence

Reproduce with the normal split-inference CLI plus
`--rq2-study {rq2_study_name(repo,rq2_study)}`.
RQ1, Full energy and the YOLOv7 case retain their frozen original bindings.
The current RQ2 figures and tables use {final_rq2['pair_count']} verified artifact pairs, of which
{final_rq2['quality_pair_count']} pass Native numerical quality and bound Generic quality across {final_rq2['quality_group_count']} groups.
{final_rq2['groups_without_quality_pairs']} groups have no admitted paired candidate and are listed as unavailable.
Publication status: {final_rq2.get('publication_status', 'historical_snapshot')}.
{final_rq2['scope']}
{final_rq2.get('overall_statistic', 'Every evaluated model/device group receives equal weight.')}
Groups with one admitted cut: {final_rq2.get('quality_singleton_groups', 'see per-group candidate_count')}.
Mean restricted to groups with at least two cuts: {final_rq2.get('mean_final_generic_loss_n_ge_2_pct', 'not separately evaluated in this historical snapshot')}.
All prior graph weights and normalization universes are frozen; no new fit.
The original weighted folds and operation rules remain separately documented.
Current Generic rates never inherit historical energy as joint measurements.
`data/rq2_final_summary.json`, `data/pair_group_coverage.json` and
`data/pair_identity_audit.json` give exact counts, exclusions and source hashes.
""")
    return manifest
