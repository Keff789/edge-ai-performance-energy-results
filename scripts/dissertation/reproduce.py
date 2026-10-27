#!/usr/bin/env python3
"""Generate German dissertation figures and tables from recorded split results.

The English exports remain the scientific data source. Existing renderers are
called with translated labels before layout. Tables use a reviewed static
catalog. No model compilation, hardware measurement, or online translation.
"""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REPOSITORY_URL = 'https://github.com/Keff789/edge-ai-performance-energy-results'
sys.path.insert(0, str(HERE))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_reference(path, repo, source):
    """Use stable repository paths even for a freshly reproduced English export."""
    path, repo, source = (Path(value).resolve() for value in (path, repo, source))
    if path.is_relative_to(source):
        reference = source.relative_to(repo) if source.is_relative_to(repo) else Path('results/split-inference')
        return str(reference / path.relative_to(source))
    return str(path.relative_to(repo))


def source_metadata(path, repo, source):
    reference = source_reference(path, repo, source)
    canonical = repo / reference
    result = {'source': reference, 'source_sha256': sha(canonical) if canonical.is_file() else None}
    if path != canonical and path.is_file():
        # PDF metadata and generated SVG identifiers need not be byte-stable.
        # Distinguish the fresh English rendering from the committed reference.
        result['reproduced_source_sha256'] = sha(path)
    return result


def repair_markdown_links(path, original, repo):
    """Link uncopied machine records to their unchanged canonical repository files."""
    def replace(match):
        link = match.group(1)
        if '://' in link or link.startswith(('#', 'mailto:')):
            return match.group()
        destination, separator, anchor = link.partition('#')
        if (path.parent / destination).exists():
            return match.group()
        canonical = (original.parent / destination).resolve()
        if canonical.is_relative_to(repo) and canonical.exists():
            kind = 'tree' if canonical.is_dir() else 'blob'
            url = f'{REPOSITORY_URL}/{kind}/main/{canonical.relative_to(repo)}'
            return '](' + url + (separator + anchor if separator else '') + ')'
        return match.group()
    path.write_text(re.sub(r'\]\(([^\s)]+)\)', replace, path.read_text(encoding='utf-8')), encoding='utf-8')


def json_write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def refresh_figure_metadata(repo, source, output, figure):
    """Refresh an existing translated figure's hashes after its normal redraw."""
    repo, source, output = (Path(value).resolve() for value in (repo, source, output))
    manifest = json.loads((output / 'ASSET_MANIFEST.json').read_text())
    for asset in manifest['figures']:
        if str(Path(asset['output']).with_suffix('')) != figure:
            continue
        original = source / 'publications' / asset['output']
        asset.update(source_metadata(original, repo, source))
        asset['sha256'] = sha(output / asset['output'])
    r30 = json.loads((source / 'publications/mlsys-r30/ASSET_MANIFEST.json').read_text())
    manifest['current_rq2_graph_display'] = r30['existing_rq2_assets']['graph_display']
    json_write(output / 'ASSET_MANIFEST.json', manifest)


def scientific_payload(value):
    """Text offsets may change with German label widths, data coordinates may not."""
    if isinstance(value, dict):
        return {key: scientific_payload(item) for key, item in value.items() if key != 'text_offset_points'}
    if isinstance(value, list):
        return [scientific_payload(item) for item in value]
    return value


def build(repo, source, output, *, numeric_only=False, supplementary=True, strict=True, rq2_study=None):
    repo, source, output = map(lambda p: Path(p).resolve(), (repo, source, output))
    if rq2_study is not None and not (source / 'publications/mlsys-r30').is_dir():
        raise ValueError('--rq2-study requires an English source with the mlsys-r30 profile.')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use an empty output directory: ' + str(output))
    if output == repo or output == source or output in source.parents:
        raise ValueError('Output must not replace the repository or English sources.')
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'dissertation-matplotlib-cache'))
    from german_labels import GermanLabels
    from german_tables import translate_tables
    labels = GermanLabels()
    bundles = []
    table_reports = []
    figure_assets, table_assets = [], []
    numeric_checks = []
    split_scripts = repo / 'scripts/split-inference'
    sys.path.insert(0, str(split_scripts))
    work_parent = None if output.is_relative_to(repo) else output.parent
    with tempfile.TemporaryDirectory(prefix='dissertation-de-', dir=work_parent) as temporary:
        work = Path(temporary)
        broad = work / 'split'
        broad.mkdir()
        for folder in ['data', 'tables']:
            shutil.copytree(source / folder, broad / folder)
        # The frozen profile supplies the original numerical inputs to R30.
        shutil.copytree(source / 'publications/mlsys-r22', broad / 'publications/mlsys-r22')
        schematic_report = None
        studies = {}
        with (labels.active() if not numeric_only else nullcontext()):
            print('Render German split and publication figures', flush=True)
            if not numeric_only:
                from render_figures import render
                render(broad)
            from publication_mlsys import build_profile as build_r22
            from publication_mlsys_r30 import build_profile as build_r30, verify_profile
            if (broad / 'data/current_observation_binding.json').is_file():
                # R22 retains its original cohort while the current R30 below
                # replays the source-admitted deployment replacements.
                from build_paper_dataset import build as build_dataset
                archived = work / 'archived-split'
                configuration = json.loads((broad / 'data/analysis_config.json').read_text())
                build_dataset(repo / 'results/split-inference/data/inputs', archived,
                              configuration, current_observations=False)
                build_r22(repo, archived, numeric_only=numeric_only)
                shutil.copytree(archived / 'publications/mlsys-r22',
                                broad / 'publications/mlsys-r22', dirs_exist_ok=True)
            else:
                build_r22(repo, broad, numeric_only=numeric_only)
            if (source / 'publications/mlsys-r30').is_dir():
                build_r30(repo, broad, numeric_only=numeric_only, rq2_study=rq2_study)
                numeric_checks.append(verify_profile(repo, broad, rq2_study=rq2_study))
                if not numeric_only:
                    from schematic import render_schematic
                    schematic_report = render_schematic(repo, broad / 'publications/mlsys-r30/figures')
            else:
                schematic_report = None
            bundles.append(('split-inference', broad, source, 'scripts/split-inference/render_figures.py'))
            for name in ['mlsys-r22', 'mlsys-r30']:
                if (source / 'publications' / name).is_dir():
                    bundles.append((name, broad / 'publications' / name, source / 'publications' / name,
                                    'scripts/split-inference/publication_mlsys' + ('_r30' if name.endswith('r30') else '') + '.py'))
            if supplementary:
                from supplementary import render_supplementary
                print('Render German supplementary-study figures', flush=True)
                studies = render_supplementary(repo, work / 'supplementary', numeric_only=numeric_only)
                for name, study in studies.items():
                    bundles.append(('supplementary-studies/' + name, Path(study['output']), repo / study['source'], study['generator']))

        early_audit = labels.report()
        early_audit['figures'] = {str(Path(k).relative_to(work)): value for k, value in early_audit['figures'].items() if Path(k).is_relative_to(work)}
        json_write(output / 'FIGURE_TRANSLATION_AUDIT.json', early_audit)
        for name, rendered, english, generator in bundles:
            print('Translate tables: ' + name, flush=True)
            target = output / name
            target.mkdir(parents=True, exist_ok=True)
            report = (translate_tables(rendered / 'tables', target / 'tables', strict=strict)
                      if name in ['split-inference', 'mlsys-r22', 'mlsys-r30']
                      else translate_tables(rendered, target, strict=strict))
            table_reports.append({'bundle': name, 'report': report})
            # Tables are presentation exports. JSON/CSV retain their original identities
            # and numbers; the manifest points to the English records instead of copies.
            for path in sorted(target.rglob('*')):
                if path.suffix in ['.tex', '.md'] and path.name != 'README.md':
                    relative = path.relative_to(target)
                    original = english / relative
                    canonical = source_reference(original, repo, source)
                    if path.suffix == '.md':
                        repair_markdown_links(path, repo / canonical, repo)
                    table_assets.append({'bundle': name, 'output': str(path.relative_to(output)),
                                         **source_metadata(original, repo, source),
                                         'sha256': sha(path), 'generator': generator})
            if name.startswith('supplementary-studies/'):
                for path in sorted(rendered.rglob('*')):
                    if path.suffix not in ['.csv', '.json']:
                        continue
                    relative = path.relative_to(rendered)
                    original = english / relative
                    if original.is_file():
                        if path.read_bytes() != original.read_bytes():
                            raise ValueError('Supplementary numeric export changed: ' + name + '/' + str(relative))
                        numeric_checks.append({'bundle': name, 'payload': str(relative), 'sha256': sha(original), 'unchanged': True})
            if not numeric_only:
                # Only this bundle's figures, never the nested publication bundles.
                figures = rendered / 'figures'
                for image_folder in [figures, rendered / 'previews']:
                    for path in sorted(image_folder.rglob('*')):
                        if path.suffix.lower() not in ['.pdf', '.svg', '.png']:
                            continue
                        relative = path.relative_to(rendered)
                        # Some older studies store their PNG alongside the vector
                        # figure in a separate previews directory. Publish all three
                        # formats together without changing the source reference.
                        destination_relative = (Path('figures') / path.relative_to(image_folder)
                                                if image_folder.name == 'previews' else relative)
                        dest = target / destination_relative
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(path, dest)
                        original = english / relative
                        figure_assets.append({'bundle': name, 'output': str(dest.relative_to(output)),
                                              **source_metadata(original, repo, source),
                                              'sha256': sha(dest), 'generator': generator})
                # Machine-readable plot data must remain identical.
                for path in sorted(figures.glob('*.json')) if figures.is_dir() else []:
                    original = english / 'figures' / path.name
                    if original.is_file() and path.name != 'system_overview.json':
                        left, right = json.loads(path.read_text()), json.loads(original.read_text())
                        if scientific_payload(left) != scientific_payload(right):
                            json_write(output / 'DATA_DIFFERENCE.json', {'bundle': name, 'payload': path.name, 'actual': left, 'expected': right})
                            raise ValueError('Numerical figure payload changed: ' + name + '/' + path.name)
                        numeric_checks.append({'bundle': name, 'payload': path.name, 'sha256': sha(original), 'unchanged': True, 'excluded_presentation_fields': ['text_offset_points']})

        audit = labels.report()
        # Private temporary absolute paths are unnecessary in the published audit.
        audit['figures'] = {str(Path(k).relative_to(work)): value for k, value in audit['figures'].items()
                            if Path(k).is_relative_to(work)}
        json_write(output / 'TRANSLATION_AUDIT.json', {'figures': audit, 'tables': table_reports})
        if strict and any(x['report']['untranslated'] for x in table_reports):
            raise ValueError('Missing German table labels; see TRANSLATION_AUDIT.json')
        if strict and audit['untranslated']:
            raise ValueError('Missing German figure labels; see TRANSLATION_AUDIT.json: ' + repr(audit['untranslated']))
        manifest = {'schema': 'dissertation-german-assets-v1', 'language': 'de',
                    'scope': 'Split inference, current and frozen publication profiles, and supplementary split studies. Energy measurement is a separate analysis tool.',
                    'numeric_only': numeric_only, 'supplementary_studies': supplementary,
                    'source_reference_base': REPOSITORY_URL + '/blob/main/',
                    'english_source_kind': 'repository' if source == repo / 'results/split-inference' else 'fresh_reproduction',
                    'english_source': str(source.relative_to(repo)) if source.is_relative_to(repo) else 'results/split-inference',
                    'current_rq2_study': (str(Path(rq2_study).resolve().relative_to(repo)) if rq2_study is not None and Path(rq2_study).resolve().is_relative_to(repo) else None),
                    'schematic': schematic_report,
                    'study_provenance': {name: {
                        **{key: value for key, value in study.items() if key not in ['output', 'presentation_status']},
                        'presentation_status': ('machine_tables_only' if study['presentation_status'] == 'machine_tables_only'
                                                else 'german_presentation_exported')}
                                         for name, study in studies.items()},
                    'number_format': 'Original scientific number formatting retained. Numerical records are unchanged.',
                    'catalogs': {str(p.relative_to(HERE)): sha(p) for p in sorted((HERE / 'locales').glob('*.json'))},
                    'figures': figure_assets, 'tables': table_assets, 'numeric_checks': numeric_checks}
        if rq2_study is not None:
            current = json.loads((broad / 'publications/mlsys-r30/ASSET_MANIFEST.json').read_text())
            manifest['current_rq2_graph_display'] = current['existing_rq2_assets']['graph_display']
        # Link repair affects only Markdown destinations. Record the final bytes
        # in both manifests; numerical-token checks above precede link repair.
        for item in table_reports:
            base = output / item['bundle']
            if item['bundle'] in ['split-inference', 'mlsys-r22', 'mlsys-r30']:
                base /= 'tables'
            for entry in item['report']['files']:
                entry['target_sha256'] = sha(base / entry['target'])
        json_write(output / 'TRANSLATION_AUDIT.json', {'figures': audit, 'tables': table_reports})
        json_write(output / 'ASSET_MANIFEST.json', manifest)
        write_catalog(output, manifest)
    return {'figure_families': len({str(Path(x['output']).with_suffix('')) for x in figure_assets}),
            'table_files': len(table_assets), 'untranslated_figure_labels': len(audit['untranslated']),
            'output': str(output)}


def write_catalog(output, manifest):
    bundles = sorted({x['bundle'] for x in manifest['figures'] + manifest['tables']} |
                     {'supplementary-studies/' + name for name in manifest['study_provenance']})
    graph_link = '../rq3-generic420/de/' if (output.parent / 'publications/mlsys-r30').exists() else 'rq3-generic420/de/'
    lines = ['# Deutsche Grafiken und Tabellen für die Dissertation', '',
             'Die aktuelle Studie untersucht den Nutzen der Split-Inferenz, die Auswahl mit Generic und die Vorauswahl anhand des Modellgraphen. Die deutschen Darstellungen verwenden dieselben Messwerte wie die englischen Ausgaben.', '',
             '- [Split-Vergleiche und Generic–Native-Auswahl](mlsys-r30/README.md)',
             f'- [Graph-basierte Vorauswahl]({graph_link})', '',
             '## Reproduktion', '', '```sh',
             'python3 scripts/reproduce_current.py --output local-output/current --languages en de',
             '```', '',
             'Ein leeres Ausgabeverzeichnis verwenden. Die Prüfung der Zahlen und Übersetzungen ist Bestandteil des Aufrufs. PDF/SVG und LaTeX sind für die Dissertation vorgesehen, PNG und Markdown für die Vorschau.', '',
             'Der [vollständige Dateikatalog](ASSET_CATALOG.md) enthält zusätzliche Darstellungen. `ASSET_MANIFEST.json` verknüpft jede Ausgabe mit ihren Quelldaten.', '']
    catalog = ['# Vollständiger Dateikatalog', '',
               'Die aktuelle Auswahl steht in [README.md](README.md). Weitere Darstellungen und frühere Analysen sind hier nach Generator gruppiert.', '',
               '| Bereich | Grafiken | Tabellen-Dateien |', '|---|---:|---:|']
    for bundle in bundles:
        figs = [x for x in manifest['figures'] if x['bundle'] == bundle]
        tabs = [x for x in manifest['tables'] if x['bundle'] == bundle]
        catalog.append(f'| [{bundle}]({bundle}/README.md) | {len({str(Path(x["output"]).with_suffix("")) for x in figs})} | {len(tabs)} |')
        index = ['# ' + bundle, '', 'Deutsche Darstellung der unveränderten Ausgangsdaten.', '', '## Grafiken', '']
        if not figs and not tabs:
            study = manifest['study_provenance'][bundle.split('/', 1)[1]]
            index = ['# ' + bundle, '',
                     'Diese Studie enthält ausschließlich maschinenlesbare Tabellen. CSV-/JSON-Spalten und Messwerte behalten ihre ursprünglichen Bezeichnungen.', '',
                     '[Originaltabellen](' + REPOSITORY_URL + '/tree/main/' + study['source'] + ')', '']
        stems = sorted({str(Path(x['output']).relative_to(bundle).with_suffix('')) for x in figs})
        for stem in stems:
            available = [Path(x['output']).suffix[1:] for x in figs if str(Path(x['output']).relative_to(bundle).with_suffix('')) == stem]
            index.append('- **' + Path(stem).name + '**: ' + ' · '.join(f'[{ext.upper()}]({stem}.{ext})' for ext in available))
        if tabs:
            index += ['', '## Tabellen', '', 'LaTeX-Dateien benötigen je nach Ausgangstabelle `booktabs`, `siunitx` und `longtable`. Breite Tabellen sind für eine ganze Seite oder das Querformat vorgesehen.', '']
        for item in tabs:
            rel = str(Path(item['output']).relative_to(bundle))
            index.append('- [' + rel + '](' + rel + ')')
        (output / bundle / 'README.md').write_text('\n'.join(index) + '\n', encoding='utf-8')
    (output / 'ASSET_CATALOG.md').write_text('\n'.join(catalog) + '\n', encoding='utf-8')
    (output / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=REPO / 'results/split-inference')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--numeric-only', action='store_true', help='German tables only, without rendering figures.')
    parser.add_argument('--no-supplementary', action='store_true')
    parser.add_argument('--verify', action='store_true', help='Require complete label coverage and unchanged numerical payloads (default).')
    parser.add_argument('--collect-labels', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--generic420-study',type=Path,help='Optional curated Generic420 study; add German RQ3 figures and tables')
    parser.add_argument('--rq2-study', type=Path, help='Verified current Generic/Native paired study; use the same study as the English publication')
    args = parser.parse_args()
    summary=build(REPO, args.source, args.output, numeric_only=args.numeric_only,
                  supplementary=not args.no_supplementary, strict=not args.collect_labels, rq2_study=args.rq2_study)
    if args.generic420_study:
        import subprocess
        renderer=REPO/'scripts/supplementary-studies/rq3-generic420/render_artifacts.py'
        command=[sys.executable,str(renderer),'--study',str(args.generic420_study),
                 '--out',str(args.output/'rq3-generic420'),'--languages','de']
        if args.numeric_only: command.append('--numeric-only')
        subprocess.run(command,check=True)
        summary['generic420_artifacts']='rq3-generic420'
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
