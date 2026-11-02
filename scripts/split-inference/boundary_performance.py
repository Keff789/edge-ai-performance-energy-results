#!/usr/bin/env python3
"""Compare measured split throughput with the complete graph boundary profile.

Offline only: this module joins published numeric inputs. It neither acquires
measurements nor changes candidate selection. Both languages render one payload.
"""
import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

from publication_mlsys_figures import DISSERTATION_STYLE, MODEL_LABELS, PAPER_PALETTE

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / 'results/supplementary-studies/rq3-generic420-detector-corrected-20261027'
DEFAULTS = {
    'graph_universe': STUDY / 'inputs/graph_universe.csv',
    'graph_features': ROOT / 'results/supplementary-studies/rq2-weighted-20261020/features/graph_boundary_features.csv',
    'feature_metadata': STUDY / 'inputs/feature_metadata.json',
    'candidates': STUDY / 'inputs/candidates.csv',
    'dataset': ROOT / 'results/split-inference/data/PAPER_DATASET.json',
}
BOUNDARY_ID = re.compile(r'^sha256:([0-9a-f]{64}):topo:([0-9a-f]{64}):b([0-9]+)$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def boolean(value):
    if value in (True, 'True', 'true', '1', 1):
        return True
    if value in (False, 'False', 'false', '0', 0, '', None):
        return False
    raise ValueError(f'Invalid boolean: {value!r}')


def number(value, label, positive=False):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Missing or invalid {label}: {value!r}') from exc
    require(math.isfinite(result), f'Nonfinite {label}')
    require(result > 0 if positive else result >= 0, f'Invalid {label}: {result}')
    return result


def same_number(left, right):
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def graph_catalogue(rows, model, full_features=False):
    """Read explicit graph identities, never infer a position from a case label."""
    catalogue, positions, identities, model_hashes, topo_hashes = {}, set(), set(), set(), set()
    for row in rows:
        if row['model'] != model:
            continue
        case = row['case'] if full_features else row['case_id']
        raw_boundary = number(row['boundary'], 'boundary')
        require(raw_boundary.is_integer(), f'Noninteger boundary: {case}')
        boundary = int(raw_boundary)
        identity = row.get('boundary_id', '')
        match = BOUNDARY_ID.fullmatch(identity)
        require(match is not None, f'Missing or invalid boundary_id: {case}')
        model_hash, topo_hash, identity_index = match.groups()
        require(model_hash == row.get('model_sha256'), f'Model hash mismatch: {case}')
        require(int(identity_index) == boundary, f'Boundary ID/index mismatch: {case}')
        if full_features:
            require(topo_hash == row.get('topological_order_sha256'), f'Topology mismatch: {case}')
            require(boolean(row.get('comm_complete')), f'Incomplete boundary bytes: {case}')
        require(case not in catalogue and boundary not in positions and identity not in identities,
                f'Duplicate graph boundary: {case}')
        catalogue[case] = {
            'case_id': case, 'boundary': boundary, 'boundary_id': identity,
            'model_sha256': model_hash, 'topological_order_sha256': topo_hash,
            'cut_bytes': number(row['Comm'] if full_features else row['cut_bytes'], 'cut_bytes'),
            'workflow_candidate': boolean(row.get('tool_workflow_candidate', True)),
        }
        positions.add(boundary)
        identities.add(identity)
        model_hashes.add(model_hash)
        topo_hashes.add(topo_hash)
    require(catalogue, f'No graph boundaries for {model}')
    require(len(model_hashes) == len(topo_hashes) == 1, 'Mixed graph model/topology identities')
    return catalogue


def quality_pass(row):
    reference = number(row.get('quality_reference_value'), 'quality reference', positive=True)
    quality = number(row.get('quality_value'), 'quality value')
    loss = (reference - quality) / reference
    return loss <= .05, loss


def bind(row, catalogue, model, csv_candidate=False):
    case = row.get('case_id')
    require(case in catalogue, f'Measurement has no graph boundary: {case}')
    graph = catalogue[case]
    require(row.get('model', row.get('model_id')) == model, f'Measurement model mismatch: {case}')
    require(row.get('model_sha256') == graph['model_sha256'], f'Measurement model hash mismatch: {case}')
    if csv_candidate:
        require(row.get('boundary_id') == graph['boundary_id'], f'Measurement boundary_id mismatch: {case}')
        require(same_number(row.get('boundary'), graph['boundary']), f'Measurement boundary mismatch: {case}')
        require(same_number(row.get('cut_bytes'), graph['cut_bytes']), f'Measurement byte mismatch: {case}')
    elif row.get('boundary_id'):
        require(row['boundary_id'] == graph['boundary_id'], f'Measurement boundary_id mismatch: {case}')
    return graph


def build_payload(graph_rows, feature_rows, candidate_rows, dataset_rows,
                  model='yolov7_paper', setup='H8', highlight_case=None):
    workflow = graph_catalogue(graph_rows, model)
    catalogue = graph_catalogue(feature_rows, model, full_features=True)
    for case, row in workflow.items():
        require(case in catalogue, f'Workflow boundary absent from complete graph: {case}')
        for key in ('boundary', 'boundary_id', 'model_sha256', 'cut_bytes'):
            require(row[key] == catalogue[case][key], f'Workflow/full graph mismatch: {case}/{key}')
    selected = [r for r in candidate_rows if r['model'] == model and r['accelerator'] == setup]
    deployment = [r for r in dataset_rows if r['model_id'] == model and r['setup_id'] == setup]
    require(selected, f'No Generic candidates for {model}/{setup}')
    hosts = {r.get('setup_id') for r in selected} | {r.get('physical_host') for r in deployment}
    require(len(hosts) == 1 and None not in hosts and '' not in hosts, 'Physical host mismatch')
    host = next(iter(hosts))
    graph_hash = next(iter(catalogue.values()))['model_sha256']
    generic, native, omitted, duplicate_sources = {}, {}, [], []
    seen_candidates, seen_cases, seen_dataset = set(), set(), set()

    def measurement(row, graph, runner, eligible, source, uid, fps_key='fps'):
        return {
            'uid': uid, 'model': model, 'setup': setup, 'physical_host': host,
            'runner': runner, **graph, 'fps': number(row.get(fps_key), 'FPS', positive=True),
            'quality_eligible': eligible, 'sources': [source],
        }

    for row in selected:
        graph = bind(row, catalogue, model, csv_candidate=True)
        uid = row.get('generic_uid')
        require(uid and uid not in seen_candidates, f'Duplicate/missing Generic UID: {uid}')
        require(row['case_id'] not in seen_cases, f'Duplicate Generic case: {row["case_id"]}')
        seen_candidates.add(uid)
        seen_cases.add(row['case_id'])
        if not boolean(row.get('fps_measured')):
            require(not row.get('fps'), f'Unmeasured candidate carries FPS: {uid}')
            omitted.append({'uid': uid, 'case_id': row['case_id'],
                            'reason': row.get('technical_reason') or row.get('fps_status') or 'No measured FPS'})
            continue
        require(not boolean(row.get('technical_exclusion')), f'Measured candidate marked technical exclusion: {uid}')
        eligible = boolean(row.get('analysis_eligible'))
        require(eligible == boolean(row.get('quality_eligible')), f'Unresolved measurement eligibility: {uid}')
        generic[row['case_id']] = measurement(row, graph, 'generic', eligible, 'candidates', uid)

    fulls = []
    for row in deployment:
        uid = row.get('uid')
        require(uid and uid not in seen_dataset, f'Duplicate/missing deployment UID: {uid}')
        seen_dataset.add(uid)
        require(row.get('model_sha256') == graph_hash, f'Deployment model hash mismatch: {uid}')
        if not boolean(row.get('included_performance')):
            omitted.append({'uid': uid, 'case_id': row.get('case_id'), 'reason': 'Not included in deployment performance'})
            continue
        eligible, loss = quality_pass(row)
        if row['kind'] == 'full':
            reference = {'uid': uid, 'backend': row['backend'], 'physical_host': host,
                         'fps': number(row['fps'], 'Full FPS', positive=True),
                         'quality_eligible': eligible, 'relative_quality_loss': loss}
            fulls.append(reference)
            continue
        require(row['kind'] == 'split', f'Unknown deployment kind: {uid}')
        graph = bind(row, catalogue, model)
        runner = row['runner']
        require(runner in ('generic', 'native'), f'Unknown split runner: {uid}')
        point = measurement(row, graph, runner, eligible, 'dataset', uid)
        point['relative_quality_loss'] = loss
        target = generic if runner == 'generic' else native
        previous = target.get(row['case_id'])
        if previous is not None:
            for key in ('uid', 'boundary_id', 'model_sha256', 'physical_host', 'quality_eligible'):
                require(previous[key] == point[key], f'Conflicting duplicate {uid}: {key}')
            require(same_number(previous['fps'], point['fps']), f'Conflicting duplicate {uid}: FPS')
            previous['sources'].append('dataset')
            previous['relative_quality_loss'] = loss
            duplicate_sources.append(uid)
        else:
            target[row['case_id']] = point
    admissible_fulls = [r for r in fulls if r['quality_eligible']]
    require(admissible_fulls, 'No quality-admissible Full on the same physical host')
    baseline = sorted(admissible_fulls, key=lambda r: (-r['fps'], r['uid']))[0]
    graph_points = sorted(catalogue.values(), key=lambda r: r['boundary'])
    measurements = sorted([*generic.values(), *native.values()], key=lambda r: (r['runner'], r['boundary']))
    if highlight_case is not None:
        require(highlight_case in native and native[highlight_case]['quality_eligible'],
                f'Highlight must be a quality-admissible measured Native cut: {highlight_case}')
    return {
        'schema': 'boundary-performance-v1', 'model': model, 'setup': setup, 'physical_host': host,
        'model_sha256': graph_hash, 'quality_loss_limit': .05,
        'graph_boundaries': graph_points, 'measurements': measurements,
        'full_reference': baseline, 'full_alternatives': fulls, 'highlight_case': highlight_case,
        'counts': {'graph_boundaries': len(catalogue), 'workflow_boundaries': len(workflow),
                   'fixed_candidates': len(selected), 'generic_measured': len(generic),
                   'generic_admissible': sum(r['quality_eligible'] for r in generic.values()),
                   'native_measured': len(native), 'native_admissible': sum(r['quality_eligible'] for r in native.values())},
        'merged_duplicate_uids': sorted(duplicate_sources), 'omitted': omitted,
        'conventions': {
            'boundary_binding': 'Exact boundary_id for candidates; case_id plus matching model SHA256 for deployment rows without boundary_id. Positions always come from the graph catalogue.',
            'graph_scope': 'All graph boundaries, including workflow-ineligible positions; bars do not imply compiler or runner support.',
            'bytes_unit': 'MB = cut_bytes / 1000000, matching the graph-analysis GUI.',
            'generic_line': 'Thin line through admitted measured points is only a visual guide; no unmeasured FPS are estimated.',
            'native_points': 'Measured points only; no connection or interpolation.',
            'quality': 'Candidate analysis_eligible; deployment numeric relative loss against CPU-ONNX, at most 5%.',
        },
    }


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_name(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(Path(path).resolve())


def load_payload(paths, model, setup, highlight_case):
    hashes = {key: sha256(path) for key, path in paths.items()}
    metadata = json.loads(Path(paths['feature_metadata']).read_text())
    require(hashes['graph_features'] == metadata['published_graph_features']['sha256'],
            'Complete graph-feature file does not match the current study metadata hash')
    tables = {}
    for key in ('graph_universe', 'graph_features', 'candidates'):
        with Path(paths[key]).open(newline='') as handle:
            tables[key] = list(csv.DictReader(handle))
    payload = build_payload(tables['graph_universe'], tables['graph_features'], tables['candidates'],
                            json.loads(Path(paths['dataset']).read_text()), model, setup, highlight_case)
    payload['sources'] = {key: {'path': source_name(path), 'sha256': hashes[key]} for key, path in paths.items()}
    return payload


def stem_for(payload):
    model = payload['model'].removesuffix('_paper')
    return f'{model}_{payload["setup"].lower()}_boundary_performance'


def caption(payload, language):
    model = MODEL_LABELS.get(payload['model'], payload['model'])
    if language == 'de':
        return (f'Gemessener Durchsatz und Grenztensorgröße für {model} auf {payload["setup"]}. '
                'Oben: Generic- und Native-Messwerte an den untersuchten Schnittpositionen. '
                'Die dünne Verbindung der zugelassenen Generic-Messpunkte dient nur der Orientierung. '
                'Das orange Kreuz kennzeichnet einen gemessenen Schnitt, der die Qualitätsgrenze nicht erfüllt. '
                'Die gestrichelte horizontale Linie zeigt die schnellste qualitätszugelassene Full-Ausführung auf demselben System. '
                'Unten: logische Grenztensorgröße an allen Graphgrenzen, unabhängig von ihrer technischen Umsetzbarkeit. '
                'Beide Teilgrafiken verwenden dieselben Schnittpositionen. MB bezeichnet $10^6$ Byte.')
    return (f'Measured throughput and boundary size for {model} on {payload["setup"]}. '
            'Top: Generic and Native measurements at the tested boundary positions. '
            'The thin line connecting admissible Generic measurements is only a visual guide. '
            'The orange cross marks a measured cut that fails the quality threshold. '
            'The dashed horizontal line is the fastest quality-admissible Full deployment on the same system. '
            'Bottom: logical tensor size at every graph boundary, irrespective of technical support. '
            'Both panels use the same boundary positions. MB denotes $10^6$ bytes.')


def export_numeric(payload, output):
    output = Path(output)
    data = output / 'data'
    data.mkdir(parents=True, exist_ok=True)
    stem = stem_for(payload)
    path = data / f'{stem}.json'
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    for name, rows in (('measurements', payload['measurements']), ('graph_boundaries', payload['graph_boundaries'])):
        fields = sorted({key for row in rows for key in row})
        with (data / f'{stem}_{name}.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows({k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()} for row in rows)
    return path


def render(payload, output, language):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    require(language in ('en', 'de'), f'Unsupported language: {language}')
    labels = {
        'en': {'fps': 'Throughput (FPS)', 'bytes': 'Boundary size (MB)', 'x': 'Boundary index',
               'fail': 'Quality threshold failed', 'full': 'Full (TensorRT)'},
        'de': {'fps': 'Durchsatz (FPS)', 'bytes': 'Grenztensorgröße (MB)', 'x': 'Schnittposition',
               'fail': 'Qualitätsgrenze verfehlt', 'full': 'Full (TensorRT)'},
    }[language]
    backend = payload['full_reference']['backend']
    if 'tensorrt' not in backend.lower():
        labels['full'] = f'Full ({payload["setup"]})'
    destination = Path(output) / 'artifacts' / language / 'figures'
    destination.mkdir(parents=True, exist_ok=True)
    stem = stem_for(payload)
    with plt.rc_context(DISSERTATION_STYLE):
        fig, (top, bottom) = plt.subplots(2, 1, sharex=True, figsize=(4.9, 3.9),
                                         gridspec_kw={'height_ratios': [1.35, 1], 'hspace': .13})
        fig.subplots_adjust(left=.135, right=.985, top=.85, bottom=.12)
        for runner, color, marker in [('generic', 'blue', 'o'), ('native', 'green', '^')]:
            rows = [r for r in payload['measurements'] if r['runner'] == runner and r['quality_eligible']]
            if rows:
                top.plot([r['boundary'] for r in rows], [r['fps'] for r in rows],
                         color=PAPER_PALETTE[color], marker=marker, markersize=3.7 if runner == 'generic' else 5,
                         linewidth=.75, linestyle='-' if runner == 'generic' else 'None',
                         label=runner.capitalize(), zorder=4 if runner == 'native' else 3)
        top.axhline(payload['full_reference']['fps'], color=PAPER_PALETTE['dark_gray'],
                    linestyle='--', linewidth=.9, label=labels['full'], zorder=2)
        failed = [r for r in payload['measurements'] if not r['quality_eligible']]
        if failed:
            top.scatter([r['boundary'] for r in failed], [r['fps'] for r in failed],
                        color=PAPER_PALETTE['orange'], marker='x', s=28, linewidths=1.1,
                        label=labels['fail'], zorder=5)
        graph = payload['graph_boundaries']
        bottom.bar([r['boundary'] for r in graph], [r['cut_bytes'] / 1e6 for r in graph],
                   width=.85, color=PAPER_PALETTE['blue'], linewidth=0)
        if payload['highlight_case']:
            point = next(r for r in payload['measurements']
                         if r['runner'] == 'native' and r['case_id'] == payload['highlight_case'])
            for axis in (top, bottom):
                axis.axvline(point['boundary'], linestyle=':', color=PAPER_PALETTE['dark_gray'], linewidth=.85, zorder=1)
            value = f'{point["fps"]:.2f}'
            if language == 'de':
                value = value.replace('.', ',')
            top.annotate(f'{point["case_id"]}: {value} FPS', (point['boundary'], point['fps']),
                         xytext=(8, -3), textcoords='offset points', va='center', fontsize=9)
        if payload['model'] == 'yolov7_paper' and payload['setup'] == 'H8':
            comparison = next((r for r in payload['measurements']
                               if r['runner'] == 'native' and r['case_id'] == 'b044'), None)
            if comparison:
                top.annotate('b044', (comparison['boundary'], comparison['fps']),
                             xytext=(-19, 25), textcoords='offset points', fontsize=9,
                             ha='center', va='bottom',
                             arrowprops={'arrowstyle': '-', 'color': PAPER_PALETTE['dark_gray'],
                                         'lw': .6, 'shrinkA': 2, 'shrinkB': 5})
        top.set_ylim(0, max(r['fps'] for r in payload['measurements'] + [payload['full_reference']]) * 1.18)
        top.set_ylabel(labels['fps'])
        bottom.set_ylabel(labels['bytes'])
        bottom.set_xlabel(labels['x'])
        bottom.set_xlim(min(r['boundary'] for r in graph) - 3, max(r['boundary'] for r in graph) + 3)
        bottom.set_ylim(bottom=0)
        bottom.xaxis.set_major_locator(MaxNLocator(nbins=7, integer=True))
        for axis in (top, bottom):
            axis.grid(axis='y', color='#DDDDDD', linewidth=.45)
        handles, legend_labels = top.get_legend_handles_labels()
        fig.legend(handles, legend_labels, loc='upper center', bbox_to_anchor=(.55, .99), ncol=2,
                   frameon=False, columnspacing=1.5, handletextpad=.5, handlelength=2.2)
        for extension in ('pdf', 'svg', 'png'):
            kwargs = {'dpi': 200} if extension == 'png' else {}
            if extension == 'pdf':
                kwargs['metadata'] = {'CreationDate': None, 'ModDate': None}
            elif extension == 'svg':
                kwargs['metadata'] = {'Date': None}
            fig.savefig(destination / f'{stem}.{extension}', **kwargs)
        plt.close(fig)
    (destination / f'{stem}_caption.tex').write_text(caption(payload, language) + '\n')


def export_readme_manifest(payload, output, languages, rendered):
    output = Path(output)
    stem = stem_for(payload)
    counts = payload['counts']
    links = []
    if rendered:
        links = [f'- {lang.upper()}: [PDF](artifacts/{lang}/figures/{stem}.pdf), '
                 f'[SVG](artifacts/{lang}/figures/{stem}.svg), '
                 f'[PNG](artifacts/{lang}/figures/{stem}.png), '
                 f'[LaTeX caption](artifacts/{lang}/figures/{stem}_caption.tex)'
                 for lang in dict.fromkeys(languages)]
    content = [
        '# Measured performance along graph boundaries', '',
        f'{MODEL_LABELS.get(payload["model"], payload["model"])} / {payload["setup"]}; '
        f'physical host `{payload["physical_host"]}`.', '', *links, '',
        f'Both languages use the same [numeric payload](data/{stem}.json), '
        f'[measurement CSV](data/{stem}_measurements.csv), and '
        f'[graph boundary CSV](data/{stem}_graph_boundaries.csv).', '',
        '## Interpretation', '',
        f'- The lower panel contains all {counts["graph_boundaries"]} graph positions. '
        f'{counts["workflow_boundaries"]} occur in the current workflow candidate universe. '
        'Bars give logical boundary tensor size in decimal MB, not measured PCIe traffic or technical eligibility.',
        f'- The upper panel contains {counts["generic_measured"]} unique Generic observations '
        f'({counts["generic_admissible"]} quality-admissible) and {counts["native_measured"]} Native observations. '
        'Generic observations from the broader study and the paired set are merged only when identities and FPS agree.',
        '- The thin Generic line is only a visual guide between measured, admitted points. '
        'Native observations are points only. Orange crosses show measured quality failures.',
        f'- The dashed Full reference is the fastest quality-admissible Full deployment on this physical host: '
        f'{payload["full_reference"]["fps"]:.8f} FPS (`{payload["full_reference"]["backend"]}`).',
        '- Published source files are read only. Conflicting duplicate observations, graph IDs, '
        'model hashes, and boundary byte counts cause generation to stop.', '',
        '## Reproduce', '', 'From the Results repository root:', '', '```bash',
        f'python scripts/split-inference/boundary_performance.py --model {payload["model"]} '
        f'--setup {payload["setup"]} --output /tmp/boundary-performance '
        '--languages en de --verify', '```', '',
        'The JSON payload records exact input paths and SHA256 hashes. `MANIFEST.json` '
        'records generated output hashes. No new hardware measurements are taken.', '',
    ]
    (output / 'README.md').write_text('\n'.join(content))
    files = sorted(p for p in output.rglob('*') if p.is_file() and p.name != 'MANIFEST.json')
    manifest = {
        'schema': 'boundary-performance-artifacts-v1',
        'generator': {'path': source_name(__file__), 'sha256': sha256(__file__)},
        'sources': payload['sources'],
        'outputs': [{'path': str(path.relative_to(output)), 'sha256': sha256(path)} for path in files],
    }
    (output / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key, default in DEFAULTS.items():
        parser.add_argument('--' + key.replace('_', '-'), type=Path, default=default)
    parser.add_argument('--model', default='yolov7_paper')
    parser.add_argument('--setup', default='H8')
    parser.add_argument('--highlight-case', default=None)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--languages', nargs='+', choices=('en', 'de'), default=['en', 'de'])
    parser.add_argument('--verify', action='store_true', help='Reload numeric export and check input preservation')
    parser.add_argument('--no-render', action='store_true', help='Export only numeric data (no matplotlib required)')
    args = parser.parse_args(argv)
    paths = {key: getattr(args, key) for key in DEFAULTS}
    highlight = args.highlight_case
    if highlight is None and args.model == 'yolov7_paper' and args.setup == 'H8':
        highlight = 'b066'
    payload = load_payload(paths, args.model, args.setup, highlight)
    numeric = export_numeric(payload, args.output)
    if not args.no_render:
        for language in dict.fromkeys(args.languages):
            render(payload, args.output, language)
    export_readme_manifest(payload, args.output, args.languages, not args.no_render)
    # Input preservation is always checked; --verify additionally checks the serialized export.
    for key, path in paths.items():
        require(sha256(path) == payload['sources'][key]['sha256'], f'Input changed during generation: {path}')
    if args.verify:
        require(json.loads(numeric.read_text()) == payload, 'Numeric export differs from generated payload')
    print(json.dumps({'numeric_payload': str(numeric), 'counts': payload['counts'],
                      'full_reference': payload['full_reference'], 'verified': args.verify}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
