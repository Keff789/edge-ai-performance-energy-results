#!/usr/bin/env python3
"""R22 budget/calibration and scheduling assets from compact bound evidence.

The R15 arithmetic/source checker is adapted from the supplied review_r15.py;
R20's unchanged projection checker is reused with repository-local input paths.
No plotting, LaTeX execution, archive access or hardware is needed for build().
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath

from mlsys_evidence_checks import r15

INPUT_ROOT = Path('results/split-inference/publication-inputs/mlsys-r22')
GENERATOR = 'scripts/split-inference/publication_mlsys_evidence.py'
METHODS = [('generic', 'Generic'), ('calibrated_generic', 'Calibrated Generic'),
           ('uniform_random', 'Uniform random'), ('boundary_bytes_only_recomputed', 'Boundary bytes')]
CONTRASTS = ['G_product', 'N_product', 'G_single', 'N_single',
             'generic_schedule_effect', 'native_schedule_effect', 'interaction']
CONTRAST_LABELS = ['Generic productive', 'Native productive', 'Generic single-task',
                   'Native single-task', 'Generic scheduling', 'Native scheduling', 'Interaction']


def encoded(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'


class Evidence:
    """Resolve an original logical member to an existing canonical input or import."""
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        self.root = self.repo / INPUT_ROOT
        self.manifest = json.loads((self.root/'evidence_sources.json').read_text())
        entries = self.manifest['files']
        self.entries = {entry['logical_path']: entry for entry in entries}
        r15.require(len(entries) == len(self.entries), 'duplicate evidence mapping')

    def actual(self, logical):
        entry = self.entries[logical]
        path = (self.repo/entry['repo_path']).resolve()
        r15.require(path.is_relative_to(self.repo), 'evidence outside repository')
        return path

    def verify(self):
        for logical, entry in self.entries.items():
            payload = self.actual(logical).read_bytes()
            r15.require(len(payload) == entry['size_bytes'], 'evidence size: '+logical)
            r15.require(hashlib.sha256(payload).hexdigest() == entry['sha256'],
                        'evidence source SHA256: '+logical)
        return {'mapped_files': len(self.entries),
                'canonical_files_reused': sum(e['relationship'] == 'existing_byte_identical'
                                              for e in self.entries.values())}

    def path(self, logical):
        return EvidencePath(self, logical)


class EvidencePath:
    """Small path adapter for the original read-only source checkers.

    Logical containment preserves their original archive-member checks; every
    actual read independently enforces containment within the repository.
    """
    def __init__(self, evidence, logical):
        self.evidence, self.logical = evidence, PurePosixPath(logical)
        r15.require(not self.logical.is_absolute() and '..' not in self.logical.parts,
                    'unsafe logical evidence path')

    def __truediv__(self, child):
        return EvidencePath(self.evidence, self.logical/child)

    def resolve(self):
        return self.evidence.root/'evidence'/str(self.logical)

    def actual(self):
        return self.evidence.actual(str(self.logical))

    def is_file(self):
        return self.actual().is_file()

    def stat(self):
        return self.actual().stat()

    def open(self, *args, **kwargs):
        return self.actual().open(*args, **kwargs)

    def read_text(self, *args, **kwargs):
        return self.actual().read_text(*args, **kwargs)

    def read_bytes(self):
        return self.actual().read_bytes()


def check_r20(evidence):
    path = evidence.actual('r20/extract.py')
    spec = importlib.util.spec_from_file_location('mlsys_r20_projection_checker', path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    checker.ROOT = evidence.path('r20')
    provenance = json.loads((checker.ROOT/'SOURCE_PROVENANCE.json').read_text())
    for entry in provenance['bundled_files']:
        payload = (checker.ROOT/entry['file']).read_bytes()
        checker.require(len(payload) == entry['size_bytes'] and
                        checker.digest(payload) == entry['sha256'],
                        'R20 bundled projection differs: '+entry['file'])
    generator = provenance['generator']
    checker.require(generator['file'] == 'extract.py' and
                    checker.digest(path.read_bytes()) == generator['sha256'],
                    'original R20 generator hash differs')
    return {'status': 'PASS', 'mode': 'read_only_compact_projection_verification',
            'hashed_files': len(provenance['bundled_files']),
            'generator_verified': True, 'value_checks': checker.verify_values(),
            'archive_reconstructed_files': 0, 'new_hardware_or_quality_runs': False}


def recompute(repo_root, broad_output):
    evidence = Evidence(repo_root)
    integrity = evidence.verify()
    source = evidence.path('r15')
    original_manifest = r15.check_manifest(source)
    quality_summary, quality = r15.check_quality(source/'audit_regnet')
    candidates = r15.rows(source/'audit_regnet/results/calibration_candidate_audit.csv')
    broad = {r['uid']: r for r in json.loads((Path(broad_output)/'data/PAPER_DATASET.json').read_text())}
    r15.require(set(quality) == set(broad), 'R15/current dataset UID inventory differs')
    for uid, row in quality.items():
        r15.close(row['primary_candidate'], broad[uid]['quality_value'], 'current quality join')
        r15.close(row['primary_reference'], broad[uid]['quality_reference_value'], 'current CPU quality reference')
    for row in candidates:
        for role, key in [('native', 'config_id'), ('generic', 'generic_config_id')]:
            observed = broad[row[key]]
            r15.close(row[role+'_fps'], observed['fps'], 'current candidate FPS join')
            r15.require(row[role+'_performance_source_sha256'] == observed['performance_source_sha256'],
                        'current candidate performance source differs')
    protocol = r15.read_json(source/'audit_regnet/results/calibration_protocol.json')
    r15.require(protocol['lambda'] == 1 and protocol['intercept_penalized'] is False
                and protocol['hyperparameter_search'] is False,
                'frozen calibration protocol differs')
    calibration = r15.check_calibration(source/'audit_regnet', quality)
    scheduling = {
        'regnet': r15.check_mechanism(source/'audit_regnet'),
        'resnet': r15.check_mechanism(source/'resnet_replication', resnet=True),
        'resnet_prior_native_only': r15.check_mechanism(source/'audit_regnet', prior_native=True),
    }
    return {'integrity': integrity, 'original_manifest': original_manifest,
            'quality': quality_summary, 'calibration': calibration,
            'calibration_protocol': protocol, 'scheduling': scheduling,
            'r20': check_r20(evidence)}, evidence


def tex(text):
    replacements = {'&': r'\&', '%': r'\%', '_': r'\_', '#': r'\#'}
    return ''.join(replacements.get(c, c) for c in str(text))


def fmt(value, digits=2):
    return '---' if value is None else f'{value:.{digits}f}'


def tex_cell(value):
    parts = str(value).split('\n')
    return tex(value) if len(parts) == 1 else r'\shortstack{'+r'\\'.join('{'+tex(p)+'}' for p in parts)+'}'


def csv_text(rows):
    columns = list(dict.fromkeys(k for row in rows for k in row))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, columns, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()})
    return stream.getvalue()


def table_payload(stem, label, caption, records, panels, wide=False):
    environment = 'table*' if wide else 'table'
    lines = [r'\begin{'+environment+r'}[t]', r'\centering',
             r'\caption{'+tex(caption)+'}', r'\label{'+label+'}',
             r'\begingroup\small\setlength{\tabcolsep}{3pt}']
    markdown = ['# '+caption.split('.')[0], '', caption, '']
    for title, headers, cells in panels:
        if title:
            lines += [r'\par\smallskip\textbf{'+tex(title)+r'}\par\smallskip']
            markdown += ['## '+title, '']
        spec = 'l' * len(headers)
        lines += [r'\begin{tabular}{'+spec+'}', r'\toprule',
                  ' & '.join(tex(h) for h in headers)+r' \\', r'\midrule']
        markdown += ['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |']
        for row in cells:
            lines += [' & '.join(tex_cell(v) for v in row)+r' \\']
            markdown += ['| '+' | '.join(str(v).replace('\n', '<br>') for v in row)+' |']
        lines += [r'\bottomrule', r'\end{tabular}']
        markdown += ['']
    lines += [r'\endgroup', r'\end{'+environment+'}']
    return {'stem': stem, 'label': label, 'records': records,
            'tex': '\n'.join(lines)+'\n', 'md': '\n'.join(markdown)+'\n'}


def tables(audit):
    calibration = audit['calibration']
    summary = calibration['budget_results']
    population = {task: {
        'pairs': len({uid for r in calibration['groups'] if r['task'] == task for uid in r['candidate_uids']}),
        'groups': len({(r['model'], r['setup']) for r in calibration['groups'] if r['task'] == task})}
        for task in ['classification', 'detection']}
    training_count = len({r['uid'] for r in calibration['memberships'] if r['role'] == 'train'})
    outputs = []
    budget_records, panels = [], []
    for task, allowed in [('classification', METHODS), ('detection', [METHODS[0], METHODS[2]])]:
        title = f'{task.title()}: {population[task]["pairs"]} pairs, {population[task]["groups"]} groups'
        cells = []
        for method, display in allowed:
            row = {'task': task, 'method': method}
            for k in (1, 3, 5):
                value = summary.get(f'{task}|{method}|{k}')
                row['regret_k'+str(k)] = value['regret_pct'] if value else None
                row['groups_k'+str(k)] = value['groups'] if value else 0
            budget_records.append(row)
            cells.append([display]+[fmt(row['regret_k'+str(k)]) for k in (1, 3, 5)])
        panels.append((title, ['Method', 'k=1', 'k=3', 'k=5'], cells))
    outputs.append(table_payload('r15_budget', 'tab:budget',
        'Mean lost Native throughput (%) after the numerical 5% CPU-relative quality filter. Each method selects k candidates and retains their fastest Native result. Groups receive equal weight. Random values are exact expectations without replacement. Detector k=5 is unavailable.', budget_records, panels))
    classifier_records, losses, coverage = [], [], []
    for method, display in METHODS:
        row = {'method': method, 'groups': population['classification']['groups']}
        for k in (1, 3, 5):
            result = summary[f'classification|{method}|{k}']
            row['regret_k'+str(k)] = result['regret_pct']
            row['winner_coverage_k'+str(k)] = result['winner_coverage']*result['groups']
        classifier_records.append(row)
        losses.append([display]+[fmt(row['regret_k'+str(k)], 3) for k in (1, 3, 5)])
        coverage.append([display]+[fmt(row['winner_coverage_k'+str(k)], 3 if method == 'uniform_random' else 0) for k in (1, 3, 5)])
    outputs.append(table_payload('r15_calibration_summary', 'tab:supp-calibration-summary',
        f'Classifier selection loss (%) and winner coverage after the numerical 5% quality filter. The {population["classification"]["groups"]} groups receive equal weight; coverage counts groups. Random values are exact expectations. Budgets count held-out Native trials only; {training_count} distinct training configurations across folds, Generic acquisition, compilation and quality evaluation are additional costs.',
        classifier_records, [('Selection loss (%)', ['Method', 'k=1', 'k=3', 'k=5'], losses),
                             ('Winner coverage', ['Method', 'k=1', 'k=3', 'k=5'], coverage)]))
    group_records = [r for r in calibration['groups'] if r['task'] == 'classification']
    grouped = {(r['model'], r['setup'], r['method'], r['k']): r for r in group_records}
    cells = []
    for model, display in [('mobilenet_v3_large', 'MobileNet'), ('regnet_x_1_6gf', 'RegNet'), ('resnet50', 'ResNet')]:
        for setup in ['DeepX', 'H10', 'H8']:
            cells.append([display, setup, str(grouped[(model, setup, 'generic', 1)]['n'])]+[
                '/'.join(fmt(grouped[(model, setup, method, k)]['regret_pct']) for k in (1, 3, 5))
                for method, _ in METHODS])
    outputs.append(table_payload('r15_calibration_groups', 'tab:supp-calibration-groups',
        'Complete classifier selection losses (%) by group and budget. All methods use the same eligible cuts. Triplets are k=1/3/5. The calibrated method holds out the entire named architecture while fitting on the indicated setup.',
        group_records, [('', ['Model', 'Setup', 'n', 'Generic', 'Calibrated', 'Random', 'Bytes'], cells)], wide=True))
    scheduling = audit['scheduling']
    mechanisms, summary_records, cells = [], [], []
    for index, contrast in enumerate(CONTRASTS):
        row = {'contrast': contrast}
        for series in ('regnet', 'resnet'):
            row.update({series+'_'+k: v for k, v in scheduling[series]['estimates'][contrast].items()})
        summary_records.append(row)
        if index < 4:
            mechanisms.append(row)
            cells.append([CONTRAST_LABELS[index]]+[
                fmt(row[s+'_geometric_mean'], 3)+'\n['+fmt(row[s+'_ci95_low'], 3)+', '+fmt(row[s+'_ci95_high'], 3)+']'
                for s in ('regnet', 'resnet')])
    outputs.append(table_payload('r15_mechanism', 'tab:scheduling',
        'Cut-throughput ratios on H10: RegNet b123/b052 and ResNet b095/b002. Each column is a separate forty-process experiment with five randomized complete blocks. Geometric means and nominal 95% t intervals use block log ratios.',
        mechanisms, [('', ['Runtime/schedule', 'RegNet', 'ResNet'], cells)]))
    cells = [[CONTRAST_LABELS[i]]+[
        value for series in ('regnet', 'resnet') for value in [
            fmt(row[series+'_geometric_mean'], 4)+' ['+fmt(row[series+'_ci95_low'], 4)+', '+fmt(row[series+'_ci95_high'], 4)+']',
            fmt(row[series+'_sd_log'], 5)]] for i, row in enumerate(summary_records)]
    outputs.append(table_payload('r15_scheduling_summary', 'tab:supp-scheduling-summary',
        'Complete contrasts from the separate forty-process RegNet and forty-process full ResNet experiments. Geometric means have nominal 95% intervals over five complete blocks. SD is sample standard deviation of block log contrasts; interval degrees of freedom are four.',
        summary_records, [('', ['Contrast', 'RegNet mean [interval]', 'Log SD', 'ResNet mean [interval]', 'Log SD'], cells)], wide=True))
    blocks, cells = [], []
    for series, display in [('regnet', 'RegNet'), ('resnet', 'ResNet full')]:
        lookup = {(r['block'], r['contrast']): r for r in scheduling[series]['blocks']}
        for block in range(1, 6):
            row = {'series': series, 'block': block, **{contrast: lookup[(block, contrast)]['ratio'] for contrast in CONTRASTS}}
            blocks.append(row)
            cells.append([display, str(block)]+[fmt(row[c], 5) for c in CONTRASTS])
    outputs.append(table_payload('r15_scheduling_blocks', 'tab:supp-scheduling-blocks',
        'Blockwise contrasts in the two full experiments. Each block contains eight independent processes measured in randomized order. GP/NP are Generic/Native productive ratios; GS/NS are single-task ratios. Scheduling contrasts divide productive by single-task; interaction divides Native scheduling by Generic scheduling.',
        blocks, [('', ['Series', 'Block', 'GP', 'NP', 'GS', 'NS', 'G sched.', 'N sched.', 'Interaction'], cells)], wide=True))
    prior = scheduling['resnet_prior_native_only']
    records, cells = [], []
    for contrast, display in [('N_product', 'Productive'), ('N_single', 'Single-task'), ('native_schedule_effect', 'Scheduling')]:
        row = {'kind': 'summary', 'contrast': contrast, **prior['estimates'][contrast]}
        records.append(row)
        cells.append([display, fmt(row['geometric_mean'], 4)+' ['+fmt(row['ci95_low'], 4)+', '+fmt(row['ci95_high'], 4)+']'])
    block_cells = []
    lookup = {(r['block'], r['contrast']): r['ratio'] for r in prior['blocks']}
    for block in range(1, 6):
        row = {'kind': 'block', 'block': block, **{c: lookup[(block, c)] for c in ['N_product', 'N_single', 'native_schedule_effect']}}
        records.append(row)
        block_cells.append([str(block)]+[fmt(row[c], 5) for c in ['N_product', 'N_single', 'native_schedule_effect']])
    outputs.append(table_payload('r15_scheduling_native_only', 'tab:supp-scheduling-native-only',
        'Earlier Native-only ResNet series, retained separately. These twenty processes are excluded from the full replication. Five four-cell blocks use b095/b002; intervals are nominal 95% intervals on block log contrasts.',
        records, [('', ['Contrast', 'Mean [interval]'], cells), ('Blocks', ['Block', 'Productive', 'Single-task', 'Scheduling'], block_cells)]))
    return outputs


def artifacts(audit):
    outputs = {}
    for table in tables(audit):
        prefix = 'tables/'+table['stem']
        outputs[prefix+'.json'] = encoded(table['records'])
        outputs[prefix+'.csv'] = csv_text(table['records'])
        outputs[prefix+'.tex'] = table['tex']
        outputs[prefix+'.md'] = table['md']
    for name in ['folds', 'predictions', 'memberships', 'groups']:
        values = audit['calibration'][name]
        outputs['data/r15_calibration_'+name+'.json'] = encoded(values)
        outputs['data/r15_calibration_'+name+'.csv'] = csv_text(values)
    outputs['data/r15_evidence_validation.json'] = encoded(audit)
    outputs['data/r20_evidence_validation.json'] = encoded(audit['r20'])
    return outputs


def build(repo_root, broad_output, profile_output):
    audit, evidence = recompute(repo_root, broad_output)
    out = Path(profile_output)
    for relative, text in artifacts(audit).items():
        destination = out/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)
    source_files = sorted({e['repo_path'] for e in evidence.entries.values()})
    refs = {'r15_budget': 'r15_budget_table.tex', 'r15_mechanism': 'r15_mechanism_table.tex',
            'r15_calibration_summary': 'r15_supp_calibration_tables.tex',
            'r15_calibration_groups': 'r15_supp_calibration_tables.tex',
            'r15_scheduling_summary': 'r15_supp_mechanism_tables.tex',
            'r15_scheduling_blocks': 'r15_supp_mechanism_tables.tex',
            'r15_scheduling_native_only': 'r15_supp_mechanism_tables.tex'}
    assets = {}
    for table in tables(audit):
        stem = table['stem']
        if stem in ['r15_budget', 'r15_calibration_summary', 'r15_calibration_groups']:
            uids = sorted({uid for r in audit['calibration']['groups']
                           if stem == 'r15_budget' or r['task'] == 'classification' for uid in r['candidate_uids']})
            generation = 'mlsys_r14_evidence_mechanism_20261017_sm2; quality-filtered deepx_native_a4_20261015'
        else:
            series = ['resnet_prior_native_only'] if stem.endswith('native_only') else ['regnet', 'resnet']
            uids = [uid for s in series for uid in audit['scheduling'][s]['process_uids']]
            generation = 'separate scheduling process studies 20261017; earlier Native-only ResNet retained separately'
        assets[table['label']] = {'reference_file': 'sections/'+refs[stem],
            'outputs': ['tables/'+stem+'.'+extension for extension in ['csv', 'json', 'tex', 'md']],
            'input_uids': uids, 'input_files': source_files, 'data_generation': generation,
            'generator': GENERATOR,
            'verification': 'Original bound R15 quality/calibration/process checks; all folds, predictions, memberships, budget groups, block contrasts and nominal intervals recomputed; deterministic CSV/JSON/TeX/Markdown comparison.'}
    return {'assets': assets, 'validation': {'r15_source_files': audit['original_manifest']['files_verified'],
            'r15_processes': sum(v['raw_reports_recomputed'] for v in audit['scheduling'].values()),
            'ridge_folds': audit['calibration']['refitted_architecture_disjoint_folds'],
            'predictions': audit['calibration']['recomputed_predictions'], 'r20': audit['r20']}}


def validate(repo_root, broad_output, profile_output):
    audit, _ = recompute(repo_root, broad_output)
    outputs = artifacts(audit)
    for relative, expected in outputs.items():
        r15.require((Path(profile_output)/relative).read_text() == expected,
                    'R22 evidence output differs: '+relative)
    return {'status': 'PASS', 'evidence_exports_checked': len(outputs),
            'raw_processes_checked': sum(v['raw_reports_recomputed'] for v in audit['scheduling'].values()),
            'ridge_predictions_checked': len(audit['calibration']['predictions']),
            'main_scheduling_ratio_intervals_checked': sum(c in audit['scheduling'][s]['estimates']
                for s in ['regnet', 'resnet'] for c in CONTRASTS[:4]),
            'all_scheduling_summary_contrasts_checked': sum(len(s['estimates']) for s in audit['scheduling'].values()),
            'r20': audit['r20']}
