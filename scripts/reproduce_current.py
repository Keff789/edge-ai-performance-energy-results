#!/usr/bin/env python3
"""Reproduce the current split-selection study and its publication artifacts.

All steps operate on published inputs. No hardware measurement is performed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import importlib.util
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
RQ2 = REPO / 'results/supplementary-studies/rq2-native-scope-20261027'
RQ3 = REPO / 'results/supplementary-studies/rq3-generic420-detector-corrected-20261027'


def run(script: str, *arguments: object) -> None:
    subprocess.run([sys.executable, '-B', str(REPO / script),
                    *(str(value) for value in arguments)], cwd=REPO, check=True)


def write_overview(output: Path, rq2: Path, rq3: Path, languages: list[str]) -> None:
    paired = json.loads((rq2 / 'summary.json').read_text())
    counts = json.loads((rq3 / 'MANIFEST.json').read_text())['counts']
    lines = [
        '# Split-selection results', '',
        'This study evaluates split deployment benefits, selection with a universal runner, '
        'and graph-based selection before measurement.', '',
        f"The paired comparison contains {paired['quality_pair_count']} quality-admissible cuts "
        f"in {paired['quality_group_count']} model–device groups. The graph comparison uses "
        f"{counts['eligible']} quality-admissible Generic cuts in {counts['nonempty_eligible_groups']} groups.", '',
        '| Result | Figures and tables |', '|---|---|',
        '| Split benefits and paired runner selection | [Paper assets](paper/publications/mlsys-r30/) |',
        '| Graph-selected shortlists | [English artifacts](paper/rq3-generic420/en/) |',
        '| Graph–Generic–Native selection | [Workflow, budget curves and tables](staged-selection/artifacts/en/) |',
    ]
    if 'de' in languages:
        lines.append('| German dissertation artifacts | [German collection](dissertation-de/README.md) |')
    lines += ['', 'Reproduce the entire study from the repository root:', '', '```sh',
              'python3 scripts/reproduce_current.py --output local-output/current --languages en de',
              '```', '', 'Use a fresh output directory. Verification is enabled for every build. '
              'CSV and JSON files contain the unrounded values. Input manifests retain the measurement sources.', '']
    (output / 'README.md').write_text('\n'.join(lines))
    paper_lines = [
        '# Paper figures and tables', '',
        '[Split benefits and paired runner selection](publications/mlsys-r30/) and '
        '[graph-selected shortlists](rq3-generic420/en/) form the current paper artifact set.', '',
        '[Staged selection](../staged-selection/artifacts/en/) reports Native throughput after graph preselection and Generic testing.', '',
        'The [workflow diagram](../staged-selection/artifacts/en/figures/staged_selection_flow.pdf) illustrates the candidate pool and the two measurement stages.', '',
        '[Build overview and reproduction](../README.md). '
        'The numbered publication-profile directories are internal generator identifiers.', '']
    (output / 'paper/README.md').write_text('\n'.join(paper_lines))
    profile_lines = [
        '# Split benefits and runner selection', '',
        f"The runner comparison uses {paired['quality_pair_count']} quality-admissible paired cuts "
        f"in {paired['quality_group_count']} equally weighted model–device groups.", '',
        '[Figures](figures/) · [Tables](tables/) · [Unrounded data](data/) · '
        '[Graph-selection results](../../rq3-generic420/en/)', '',
        'The split/Full and YOLOv7 case figures use their recorded throughput, energy and quality. '
        'The runner-selection figures use the same current paired inputs as the analysis tables.', '',
        '[Reproduce the current study](../../../README.md). '
        '`ASSET_MANIFEST.json` maps the outputs to their generators and input files.', '']
    (output / 'paper/publications/mlsys-r30/README.md').write_text('\n'.join(profile_lines))
    english = output / 'dissertation-en'
    english.mkdir(exist_ok=True)
    (english / 'README.md').write_text(
        '# English dissertation figures and tables\n\n'
        'Use the current [split and runner-selection figures](../paper/publications/mlsys-r30/) '
        'and [graph-selection figures](../paper/rq3-generic420/en/). '
        'Both wide and single-column YOLOv7 variants are included.\n\n'
        '[Graph–Generic–Native budgets](../staged-selection/artifacts/en/) use the same paired measurements.\n\n'
        '[Selection workflow](../staged-selection/artifacts/en/figures/staged_selection_flow.pdf).\n\n'
        '[Reproduce the complete study](../README.md).\n')
    if 'de' in languages:
        german = output / 'dissertation-de/README.md'
        lines = [line for line in german.read_text().splitlines()
                 if not line.startswith('[Auswahl mit Graph, Generic und Native]')]
        german.write_text('\n'.join(lines).rstrip() + '\n\n[Auswahl mit Graph, Generic und Native](../staged-selection/artifacts/de/): '
                          '[Ablaufgrafik](../staged-selection/artifacts/de/figures/staged_selection_flow.pdf), '
                          'Budgetgrafiken und Tabellen aus denselben Messpaaren.\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Fresh output directory.')
    parser.add_argument('--languages', nargs='+', choices=['en', 'de'], default=['en', 'de'])
    parser.add_argument('--verify', action='store_true', help='Verification is always enabled.')
    parser.add_argument('--reuse-studies', action='store_true',
                        help='Render the already reproduced published studies without fitting again.')
    parser.add_argument('--deployment-inputs', type=Path,
                        default=REPO/'results/split-inference/data/inputs',
                        help='Established curated deployment input directory.')
    parser.add_argument('--current-observations', type=Path,
                        help='Source-bound current metric replacements for RQ1 and Native RQ2.')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('Use a fresh output directory: ' + str(output))
    if output == REPO or output in RQ2.parents or output in RQ3.parents:
        parser.error('Output must not replace repository inputs.')
    output.mkdir(parents=True, exist_ok=True)
    # English data and assets are the common source of the German presentation.
    languages = list(dict.fromkeys(['en', *args.languages]))
    rq2, rq3 = RQ2, RQ3
    replacements = args.current_observations or args.deployment_inputs/'current_observations.json'
    native_arguments = []
    if replacements.is_file():
        # Materialize the same curated deployment rows before either analysis.
        # This performs no fit and leaves the archived input rows untouched.
        sys.path.insert(0, str(REPO/'scripts/split-inference'))
        from build_paper_dataset import build
        configuration = json.loads((REPO/'scripts/split-inference/config.json').read_text())
        build(args.deployment_inputs, output/'current-deployments', configuration,
              current_observations=replacements)
        native_arguments = ['--native-dataset', output/'current-deployments/data/PAPER_DATASET.json']
        if args.reuse_studies:
            import hashlib
            actual = hashlib.sha256(Path(native_arguments[1]).read_bytes()).hexdigest()
            published = json.loads((RQ2/'summary.json').read_text()).get('current_native_dataset_sha256')
            if actual != published:
                parser.error('Reused RQ2 study does not bind the selected current deployment observations')
    if not args.reuse_studies:
        rq2, rq3 = output / 'rq2', output / 'rq3'
        run('scripts/supplementary-studies/rq2-native-scope-20261027/reproduce.py',
            '--input', RQ2 / 'inputs/observations.json', '--output', rq2, '--verify', *native_arguments)
        run('scripts/supplementary-studies/rq3-generic420/reproduce.py',
            '--inputs', RQ3 / 'inputs', '--output', rq3, '--languages', *languages)
    run('scripts/supplementary-studies/rq3-generic420/verify.py', '--study', rq3)
    run('scripts/supplementary-studies/staged-selection/reproduce.py',
        '--paired-study', rq2, '--graph-metadata', rq3 / 'inputs/feature_metadata.json',
        '--output', output / 'staged-selection',
        '--languages', *languages, '--verify')
    run('scripts/split-inference/reproduce.py', '--publication', 'mlsys-r30',
        '--languages', 'en', '--rq2-study', rq2, '--generic420-study', rq3,
        '--inputs', args.deployment_inputs, '--output', output / 'paper', '--verify',
        *(['--current-observations', replacements] if replacements.is_file() else []))
    if 'de' in languages:
        run('scripts/dissertation/reproduce.py', '--source', output / 'paper',
            '--rq2-study', rq2, '--generic420-study', rq3,
            '--output', output / 'dissertation-de', '--verify')
        # Both destinations present the same German assets. Render once and
        # retain the existing paper/dissertation paths with identical data.
        shutil.copytree(output / 'dissertation-de', output / 'paper/de',
                        ignore=shutil.ignore_patterns('rq3-generic420'))
        spec = importlib.util.spec_from_file_location('current_german_export', REPO / 'scripts/dissertation/reproduce.py')
        exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exporter)
        manifest = json.loads((output / 'paper/de/ASSET_MANIFEST.json').read_text())
        exporter.write_catalog(output / 'paper/de', manifest)
        # The paper renderer already populated the English destination.
        # Render both languages in a fresh directory before replacing it.
        localized_graph = output / 'rq3-artifacts-localized'
        run('scripts/supplementary-studies/rq3-generic420/render_artifacts.py',
            '--study', rq3, '--out', localized_graph, '--languages', *languages)
        shutil.rmtree(output / 'paper/rq3-generic420')
        shutil.move(str(localized_graph), str(output / 'paper/rq3-generic420'))
    write_overview(output, rq2, rq3, languages)
    (output / 'BUILD.json').write_text(json.dumps({
        'schema': 'current-study-build-v1',
        'languages': languages,
        'rq2_source': os.path.relpath(rq2, output),
        'rq3_source': os.path.relpath(rq3, output),
        'staged_selection': 'staged-selection',
        'studies_recomputed': not args.reuse_studies,
        'verification_enabled': True,
        'hardware_measurements': False,
    }, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'languages': languages, 'status': 'complete'}))


if __name__ == '__main__':
    main()
