#!/usr/bin/env python3
"""Package the local dependencies recorded by successful pdfLaTeX builds.

The ZIP contains sources and graphics, not compiled manuscript PDFs or build
products. System TeX packages remain supplied by the TeX installation. BibTeX
inputs are added from the source because pdfLaTeX does not record them in .fls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


BUILD_SUFFIXES = {
    '.aux', '.bbl', '.bcf', '.blg', '.fdb_latexmk', '.fls', '.idx', '.ilg',
    '.ind', '.lof', '.log', '.lot', '.nav', '.out', '.run.xml', '.snm',
    '.synctex', '.synctex.gz', '.toc', '.vrb', '.xdv', '.dvi', '.thm',
}
BIB_COMMAND = re.compile(
    r'\\(bibliography|bibliographystyle|addbibresource)'
    r'(?:\s*\[[^\]]*\])?\s*\{([^{}]+)\}'
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def is_build_file(path):
    return any(path.name.endswith(suffix) for suffix in BUILD_SUFFIXES)


def tex_without_comments(text):
    lines = []
    for line in text.splitlines():
        for pos, char in enumerate(line):
            if char != '%':
                continue
            backslashes = 0
            at = pos - 1
            while at >= 0 and line[at] == '\\':
                backslashes += 1
                at -= 1
            if backslashes % 2 == 0:
                line = line[:pos]
                break
        lines.append(line)
    return '\n'.join(lines)


def collect_entry(source, entry):
    fls = source / (entry + '.fls')
    log = source / (entry + '.log')
    pdf = source / (entry + '.pdf')
    if not all(path.is_file() for path in (fls, log, pdf)):
        raise ValueError(f'{entry}: build .fls, .log and .pdf are required')
    log_text = log.read_text(errors='replace')
    if ('Output written on ' not in log_text or
            re.search(r'^!', log_text, flags=re.MULTILINE) or
            'Fatal error occurred' in log_text or 'Emergency stop' in log_text):
        raise ValueError(f'{entry}: the log does not record a successful build')
    lines = fls.read_text(errors='strict').splitlines()
    pwd = next((Path(line[4:]).resolve() for line in lines if line.startswith('PWD ')), None)
    if pwd != source:
        raise ValueError(f'{entry}: stale or external recorder directory; rebuild in --source')
    files = set()
    for line in lines:
        if not line.startswith('INPUT '):
            continue
        recorded = Path(line[6:])
        path = (recorded if recorded.is_absolute() else source / recorded).resolve()
        if not path.is_relative_to(source):
            if not recorded.is_absolute():
                raise ValueError(f'{entry}: local input escapes the source directory: {recorded}')
            continue
        relative = path.relative_to(source)
        if is_build_file(path) or relative.as_posix() in {entry+'.pdf', 'main.pdf', 'supplement.pdf'}:
            continue
        if not path.is_file():
            raise ValueError(f'{entry}: recorded input is missing: {relative}')
        files.add(relative.as_posix())
    if entry + '.tex' not in files:
        raise ValueError(f'{entry}: the entry TeX source is absent from its recorder')

    bib_files = set()
    for relative in sorted(files):
        path = source / relative
        if path.suffix not in ('.tex', '.sty', '.cls'):
            continue
        text = tex_without_comments(path.read_text(errors='strict'))
        for command, argument in BIB_COMMAND.findall(text):
            names = argument.split(',') if command == 'bibliography' else [argument]
            for name in names:
                name = name.strip()
                if not name or '\\' in name or '#' in name:
                    raise ValueError(f'Cannot resolve dynamic bibliography input in {relative}: {name}')
                suffix = '.bst' if command == 'bibliographystyle' else '.bib'
                candidate = Path(name if name.endswith(suffix) else name + suffix)
                full = (source / candidate).resolve()
                if not full.is_relative_to(source):
                    raise ValueError(f'Bibliography input is outside source: {name}')
                if full.is_file():
                    bib_files.add(full.relative_to(source).as_posix())
                elif suffix == '.bib':
                    raise ValueError(f'Required bibliography is missing: {candidate}')
                # A nonlocal .bst such as plain.bst is supplied by TeX.
    files.update(bib_files)
    return files, {
        'entry': entry,
        'recorder_sha256': digest(fls.read_bytes()),
        'log_sha256': digest(log.read_bytes()),
        'bibliography_files_added': sorted(bib_files),
        'files': sorted(files),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--entry', required=True, help='Comma-separated entry stems, e.g. main,supplement')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-readme', action='store_true',
                        help='Include README.md and an existing Makefile used by its build instructions')
    parser.add_argument('--include-provenance', action='store_true')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    entries = list(dict.fromkeys(item.strip().removesuffix('.tex') for item in args.entry.split(',')))
    if not entries or any(not re.fullmatch(r'[A-Za-z0-9_-]+', entry) for entry in entries):
        parser.error('--entry requires simple entry stems such as main,supplement')
    if output.suffix.lower() != '.zip':
        parser.error('--output must end in .zip')
    files, build_records = set(), []
    for entry in entries:
        selected, record = collect_entry(source, entry)
        files.update(selected)
        build_records.append(record)
    optional = []
    if args.include_readme:
        optional.append('README.md')
        if (source / 'Makefile').is_file():
            optional.append('Makefile')
    if args.include_provenance:
        optional.append('FIGURE_PROVENANCE.json')
    for name in optional:
        if not (source / name).is_file():
            raise ValueError('Requested optional file is missing: ' + name)
        files.add(name)
    if output.is_relative_to(source) and output.relative_to(source).as_posix() in files:
        raise ValueError('Output would overwrite an input')
    payloads = {name: (source / name).read_bytes() for name in sorted(files)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in payloads.items():
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    manifest = {
        'schema': 'latex-recorder-source-package-v1',
        'archive': output.name,
        'archive_sha256': digest(output.read_bytes()),
        'entries': entries,
        'file_count': len(payloads),
        'optional_files': optional,
        'files': [{'path': name, 'sha256': digest(data), 'bytes': len(data)}
                  for name, data in payloads.items()],
        'build_records': build_records,
        'excluded': 'Build products, compiled manuscript PDFs, and system TeX dependencies',
    }
    manifest_path = output.with_suffix('.manifest.json')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'archive': str(output), 'manifest': str(manifest_path),
                      'entries': entries, 'file_count': len(payloads)}, indent=2))


if __name__ == '__main__':
    main()
