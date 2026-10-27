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


def current_rq1_binding(repo, broad_output, current_observations=None, deployment_inputs=None):
    """Rebuild the source-admitted rows before accepting current RQ1 changes."""
    repo, broad = Path(repo), Path(broad_output)
    path = broad / 'data/current_observation_binding.json'
    if not path.is_file():
        return None
    inputs = Path(deployment_inputs) if deployment_inputs else repo / 'results/split-inference/data/inputs'
    source = Path(current_observations) if current_observations else inputs / 'current_observations.json'
    assert source.is_file(), 'Current RQ1 needs its original observation input and source directory'
    read = lambda p: json.loads(Path(p).read_text())
    binding, document = read(path), read(source)
    assert binding['schema'] == 'current-deployment-input-binding-v1'
    assert binding['observations_sha256'] == digest(source), 'Current observation input changed'
    assert binding['sources'] == document['sources']
    assert binding['prior_rows_preserved'] is True
    assert binding['hardware_measurements_performed_by_generator'] is False
    assert read(broad / 'data/current_observation_inputs.json') == document
    from build_paper_dataset import build
    with tempfile.TemporaryDirectory(prefix='r30-current-source-check-') as temporary:
        expected = Path(temporary)
        config = read(broad / 'data/analysis_config.json')
        build(inputs, expected, config, current_observations=source)
        for name in ['data/PAPER_DATASET.json', 'data/current_observation_history.json',
                     'tables/energy_repeats.json', 'tables/pipeline_repeats.json',
                     'tables/table3_top2_native.json']:
            assert read(broad / name) == read(expected / name), 'Source-bound current data differs: ' + name
        archived_output = expected / 'archived'
        build(repo / 'results/split-inference/data/inputs', archived_output, config, current_observations=False)
        archived = read(archived_output / 'data/PAPER_DATASET.json')
        archived_sha256 = digest(archived_output / 'data/PAPER_DATASET.json')
    rows = read(broad / 'data/PAPER_DATASET.json')
    current = {row['uid']: row for row in rows}
    assert len(current) == len(rows), 'Duplicate current RQ1 UID'
    affected = {row['uid'] for row in document['observations']}
    archived_uids = {row['uid'] for row in archived}
    assert archived_uids <= set(current), 'Archived deployment UID removed'
    assert set(current) - archived_uids <= affected, 'New deployment lacks observation authority'
    literal_b066 = 'native|yolov7_paper|H8|hailo8_to_trt|b066'
    for row in archived:
        if row['kind'] == 'full' or row['uid'] == literal_b066:
            assert current.get(row['uid']) == row, 'Archived Full or literal b066 changed: ' + row['uid']
        elif row['uid'] not in affected:
            assert current[row['uid']] == row, 'Unaffected archived deployment changed: ' + row['uid']
    observations = sorted(document['observations'], key=lambda row: row['uid'])
    history = read(broad / 'data/current_observation_history.json')
    assert {row['uid'] for row in history} == {row['uid'] for row in observations}
    return {'schema': 'mlsys-r30-source-bound-current-rq1-v1',
        'paper_dataset_sha256': digest(broad / 'data/PAPER_DATASET.json'),
        'archived_paper_dataset_sha256': archived_sha256,
        'observation_inputs_sha256': digest(source), 'sources': binding['sources'],
        'observation_history_sha256': digest(broad / 'data/current_observation_history.json'),
        'affected_observations': [dict(uid=row['uid'], generation=row['generation'],
            metrics=sorted(row['metrics'])) for row in observations],
        'expected_packages': binding.get('expected_packages', []),
        'accepted_packages': binding.get('accepted_packages', []),
        'pending_packages': binding.get('pending_packages', []),
        'new_native_measurements': any(row['uid'].startswith('native|') and any(
            metric.get('acquisition_origin') == 'new_capture' for metric in row['metrics'].values())
            for row in observations),
        'full_baselines_unchanged': True, 'literal_b066_unchanged': True,
        'archived_r22_unchanged': True, 'hardware_measurements_performed_by_generator': False}


def current_core_reference(repo, broad_output):
    """Fresh numerical core exports; historical weighted studies are not fitted."""
    from publication_mlsys_data import build
    from publication_mlsys import build_methods
    from publication_mlsys_figures import write_figure_data
    with tempfile.TemporaryDirectory(prefix='r30-current-core-check-') as temporary:
        output = Path(temporary)
        context = build(repo, broad_output, output)
        build_methods(Path(repo), Path(broad_output), output)
        _, payload = write_figure_data(output, context)
        payload['system_overview'] = current_schematic(Path(repo), output, True)
        (output / 'figures/FIGURE_DATA.json').write_text(json.dumps(payload, sort_keys=True, indent=2) + '\n')
        return {str(path.relative_to(output)): path.read_bytes() for path in output.rglob('*')
                if path.is_file() and path.suffix in {'.json', '.csv', '.tex'}}


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
        'weight_policy':summary['weight_policy'],'weights_refitted':False,
        'new_native_measurements':any(summary.get('current_native_external_captures', {}).values()),
        'refreshed_fps_joined_to_old_energy':False,
        'publication_status':summary.get('publication_status','historical_snapshot'),
        'validation_scope':'Offline reproduction and identity accounting; unresolved scientific evidence remains unresolved.',
        **({'hardware_measurements_performed_by_generator':False,
            'current_native_external_captures':summary['current_native_external_captures']}
            if 'current_native_external_captures' in summary else {})}


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


def verify_profile(repo, broad_output, rq2_study=None, current_observations=None, deployment_inputs=None):
    repo, broad_output = Path(repo), Path(broad_output)
    rq1_current = current_rq1_binding(repo, broad_output, current_observations, deployment_inputs)
    core_reference = current_core_reference(repo, broad_output) if rq1_current else {}
    output = broad_output / 'publications' / PROFILE
    if rq1_current:
        assert json.loads((output / 'data/current_rq1_binding.json').read_text()) == rq1_current
        for name in core_reference:
            assert (output / name).is_file(), 'Missing current source-derived RQ1 export: ' + name
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
            if str(name) == 'data/current_rq1_binding.json':
                assert rq1_current is not None and json.loads(actual.read_text()) == rq1_current
                checked.append(str(name));continue
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
                actual_data=json.loads(actual.read_text());expected_data=json.loads(
                    core_reference[str(name)] if str(name) in core_reference else (target/name).read_bytes())
                if str(name) == 'data/profile_summary.json' and rq1_current:
                    assert actual_data.pop('current_rq1_observations') == rq1_current
                    assert actual_data.pop('measurement_changes') is True
                    expected_data.pop('current_rq1_observations', None)
                    expected_data.pop('measurement_changes', None)
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
            if str(name) == 'data/profile_summary.json' and rq1_current:
                actual_data=json.loads(actual.read_text());expected_data=json.loads((target/name).read_text())
                assert actual_data.pop('current_rq1_observations') == rq1_current
                assert actual_data.pop('measurement_changes') is True
                expected_data.pop('current_rq1_observations', None);expected_data.pop('measurement_changes', None)
                assert actual_data == expected_data, 'Unrelated profile summary changed'
                checked.append(str(name));continue
            if str(name) in core_reference:
                assert actual.read_bytes() == core_reference[str(name)], f'Current source-derived RQ1 differs: {name}'
                checked.append(str(name));continue
            assert (target / name).is_file(), f'Missing R30 reference: {name}'
            assert actual.read_bytes() == (target / name).read_bytes(), f'R30 differs: {name}'
            checked.append(str(name))
    return {'result': 'PASS', 'files_checked': len(checked), 'frozen_r22_files_checked': r22_checked,
            'frozen_r22_numerical_payload_unchanged': True, 'yolo_payload_unchanged': True,
            **({'current_rq1_observations': rq1_current} if rq1_current else {})}


def build_profile(repo_root, broad_output, numeric_only=False, rq2_study=None,
                  current_observations=None, deployment_inputs=None):
    repo, broad_output = Path(repo_root), Path(broad_output)
    current = current_rq1_binding(repo, broad_output, current_observations, deployment_inputs)
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
    if current:
        from publication_mlsys import build_methods
        context['assets'].update(build_methods(repo, broad_output, output))
        (output / 'data/current_rq1_binding.json').write_text(json.dumps(current, sort_keys=True, indent=2) + '\n')
    if numeric_only:
        _, payload = write_figure_data(output, context)
    else:
        _, payload = render(output, context, uniform_typography=True, uniform_palette=True)
    if not current:
        assert (output / 'figures/FIGURE_DATA.json').read_bytes() == (frozen / 'figures/FIGURE_DATA.json').read_bytes()
    assert payload['yolov7_h8_case'] == json.loads((frozen / 'figures/FIGURE_DATA.json').read_text())['yolov7_h8_case']
    shutil.copyfile(frozen / 'figures/FIGURE_DATA.json', output / 'data/frozen_r22_figure_data.json')
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
        if current:
            metadata = context['assets'].get(asset['asset_id'], {})
            figure = next((Path(name).stem for name in asset['outputs']
                           if name.startswith('figures/') and Path(name).stem in payload), None)
            if figure:
                metadata = payload[figure]
            for key in ['input_uids', 'input_files', 'data_generation', 'generator']:
                if key in metadata:
                    asset[key] = metadata[key]
            asset['input_files'] = list(dict.fromkeys(asset['input_files'] + [
                str(profile_output_reference(repo, output) / 'data/current_rq1_binding.json')]))
            asset['verification'] = 'Source-admitted current dataset reproduction; archived R22, Full baselines and literal b066 remain unchanged.'
        if asset['asset_id'] == 'fig:runners':
            asset['generator'] = 'scripts/split-inference/publication_mlsys_r30.py:current_schematic'
            asset['caption'] = payload['system_overview']['scope']
            asset['data_generation'] = 'Maintained author vector source, replacing the frozen R22 schematic.'
        if final_rq2 and any('generic_selection_loss' in p for p in asset['outputs']):
            current_rq2_asset_metadata(asset, repo, rq2_study)
            asset['generator']=str(rq2_engine_source(repo,rq2_study).relative_to(repo))+':render'
            asset['data_generation']=('Current source-bound Generic and Native observations; original records remain archived and study metadata records observation authority.'
                if current else 'Current compatible Generic observations with original artifact-bound Native measurements; study metadata records the observation policy and audit status.')
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
            'scope':final_rq2,'frozen_rq1_and_yolov7':not bool(current),
            'asset_files':sorted(final_rq2_files(Path(rq2_study)))}
        manifest['scope']='Frozen RQ1 and YOLOv7 evidence; current RQ2 recomputed using the verified study population and observation policy.'
        manifest['existing_rq2_assets']['historical_graph_generator']=str(old_source.relative_to(repo))
        manifest['existing_rq2_assets']['generator']=str(rq2_engine_source(repo,rq2_study).relative_to(repo))
        manifest['existing_rq2_assets']['graph_display']=graph_display_policy()
        manifest['existing_rq2_assets']['scope']='Current Generic scatter, Native success and search budgets use the verified original Native population study; historical graph campaign remains unchanged.'
        for name in ['rq2_weighted_all_models','r30_weighted_budget_table','r30_weighted_macros']:
            if name in assets:
                assets[name]['caption']=('Current source-bound Generic / Native verified pairs with original records archived, frozen prior graph weights. '
                    if current else 'Current Generic / original Native verified pairs, frozen prior graph weights. ') + 'See data/rq2_final_summary.json for counts, singleton groups, pending evidence and quality contract limitations.'
                assets[name]['generator']=str(rq2_engine_source(repo,rq2_study).relative_to(repo))+':render'
                assets[name]['source_sha256']={'rq2_final_input_manifest':digest(Path(rq2_study)/'INPUT_MANIFEST.json'),
                    'rq2_final_summary':digest(Path(rq2_study)/'summary.json')}
                if 'optimized_status' in assets[name]:assets[name]['optimized_status']='Frozen prior shared weights; no fit on the current paired subset.'
                if 'held_out_status' in assets[name]:assets[name]['held_out_status']='Frozen prior model-held-out vectors; prior training scope retained separately.'
    if current:
        manifest['current_rq1_observations'] = current
        manifest['scope'] = 'Source-admitted current deployment observations; archived R22, Full baselines and the literal b066 case remain unchanged.'
        manifest['core_presentation'] = 'Current PAPER_DATASET drives RQ1; data/frozen_r22_figure_data.json preserves the archived R22 payload.'
        if final_rq2:
            manifest['current_rq2_override']['archived_r22_and_literal_b066_unchanged'] = True
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
    if current:
        profile_summary['current_rq1_observations'] = current
        profile_summary['measurement_changes'] = True
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
    if current:
        provenance['measurement_changes'] = True
        provenance['hardware_measurements_performed_by_generator'] = False
        provenance['current_rq1_observations'] = current
        for name in ['PAPER_DATASET.json', 'current_observation_binding.json', 'current_observation_inputs.json', 'current_observation_history.json']:
            provenance['input_sha256']['results/split-inference/data/' + name] = digest(broad_output / 'data' / name)
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
        (output/'README.md').write_text(f"""# Split benefits and runner selection

The runner comparison contains {final_rq2['quality_pair_count']} quality-admissible paired cuts
in {final_rq2['quality_group_count']} equally weighted model–device groups.
The split/Full comparisons and the YOLOv7 case use their recorded throughput, energy and quality.

[Figures](figures/) · [Tables](tables/) · [Unrounded data](data/)

Reproduce the current study from the repository root:

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

The build includes the graph-selection analysis and English/German artifacts.
`ASSET_MANIFEST.json` maps the outputs to their sources.
""")
    if current:
        readme = output / 'README.md'
        text = readme.read_text().replace(
            'The core measurement figures use the common paper style and their frozen R22 numerical data.',
            'The core measurement figures use the source-admitted current PAPER_DATASET and the common paper style.')
        readme.write_text(text + '\nCurrent observation identities, source hashes, affected metrics and pending packages are in '
            '`data/current_rq1_binding.json`. Archived R22, all Full baselines, and the literal b066 case remain unchanged.\n')
    return manifest
