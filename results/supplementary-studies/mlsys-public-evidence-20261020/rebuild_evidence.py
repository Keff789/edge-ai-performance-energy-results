#!/usr/bin/env python3
"""Extract unchanged publication evidence from two hash-pinned original archives."""
from pathlib import Path
import argparse
import collections
import csv
import hashlib
import io
import json
import re
import tarfile
import zipfile

BASE = Path.cwd() / 'evidence-rebuild'
INPUT = None
SOURCES = {
    'regnet': ('MLSYS_R14_SM2_ABKLAERUNG_20261017_RESULTS.zip', '703c1824b64659bea6e06feb403301fc9d86fe0175d9d7725a5a37c988429b68'),
    'resnet': ('MLSYS_R14_RESNET_FULL_REPLIKATION_20261017_RESULTS.zip', '7e0bd1c86f57184cd6c53cc5122a20d664ca1f8a05b57eeb8d8d3a3807ae5056'),
}
AUDITS = {
    'EVIDENCE_AUDIT.csv': (5004159, 'dbb415827fd453d908d82b00b4d12952bdd9cc21a46568c0fb40d46a6f68175d'),
    'FLAG_RESOLUTION.csv': (529954, 'b7d866acf1dfa6df7ea300cb6fafe1df461987bcb1b05aeb0ba0cffed3bfca2f'),
}
sha = lambda data: hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def secret_scan(name, data):
    """Report only category, filename and line; never matched credential values."""
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return [], False
    patterns = {
        'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----',
        'github_token': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
        'aws_access_key': r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
        'api_secret_token': r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{35,}\b',
        'credential_url': r'\b(?:https?|ssh|postgres(?:ql)?|mysql)://[^\s/:@]+:[^\s/@]+@',
        'quoted_credential_literal': r'''(?i)["']?(?:password|passwd|api_key|access_token|auth_token|client_secret|secret_key)["']?\s*[:=]\s*["']([^"'\r\n]{8,})["']''',
    }
    hits = []
    for kind, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            hits.append({'file': name, 'line': text.count('\n', 0, match.start()) + 1, 'category': kind})
    return hits, True


def select_members(z, kind):
    names = set(n for n in z.namelist() if not n.endswith('/'))
    protocol = json.loads(z.read('PROTOCOL.json'))
    protocol_hash = sha(z.read('PROTOCOL.json'))
    prefixes = [f'results/mechanism/{protocol_hash}/', 'results/mechanism_source_cases/']
    common = {'PROTOCOL.json', 'README.md', 'REPORT.md', 'receipts/REPRODUCTION_ENVIRONMENT.json',
              'analysis/mechanism_adapter.py', 'analysis/run_mechanism.py'}
    # Copy the entire Python source closure, while excluding unneeded bundled images/docs.
    selected = {n for n in names if n.startswith('results/mechanism_source_bundle/') and n.endswith('.py')}
    if kind == 'regnet':
        prefixes += ['results/mechanism_snapshots/', 'results/mechanism_confirmation',
                     'results/mechanism_canary_comparisons/', 'evidence/mechanism_historical_references/']
        common |= {
            'CLAIM_STATUS.csv', 'PROTOCOL_pilot_canary_v1.json',
            'analysis/capture_mechanism_snapshot.py', 'analysis/freeze_mechanism_protocol.py',
            'analysis/mechanism_prepare_cases.py', 'analysis/mechanism_prepare_sources.py',
            'analysis/mechanism_source_analysis.py', 'analysis/review_mechanism_execution.py',
            'analysis/review_mechanism_results.py', 'analysis/summarize_mechanism.py',
            'analysis/summarize_mechanism_stages.py', 'analysis/test_mechanism_controller.py',
            'analysis/test_summarize_mechanism.py', 'analysis/test_review_mechanism_results.py',
            'receipts/ANALYSIS_CODE_PIN.json', 'receipts/CONFIRMATION_PROTOCOL_COMMIT.txt',
            'receipts/h10_artifact_preflight.json', 'receipts/h10_power_mode.json',
            'results/mechanism_extension_trigger.json', 'results/mechanism_extension_trigger_final.json',
            'results/mechanism_source_case_manifest.json', 'results/mechanism_source_code_index.json',
            'results/mechanism_source_deploy_manifest.json', 'results/mechanism_source_r14_raw.json',
            'results/mechanism_source_contrasts.csv', 'results/mechanism_source_repetitions.csv',
            'results/mechanism_source_summary.csv', 'results/mechanism_source_validation.json',
        }
        # These 16 frozen functional tests are prerequisites reused by the confirmed
        # study. Include their inputs/reference outputs, not pilot timing observations.
        canary_hash = sha(z.read('PROTOCOL_pilot_canary_v1.json'))
        canary_prefix = f'results/mechanism/{canary_hash}/reports/'
        for n in names:
            if n.startswith(canary_prefix):
                if n.endswith('.json'):
                    report = json.loads(z.read(n))
                    assert report['mode'] == 'canary' and report['canary_pass']
                selected.add(n)
    else:
        prefixes += ['input/reuse/', 'receipts/reuse/', 'results/replication_analysis']
        common |= {
            'PROTOCOL.md', 'CLAIM_STATUS_DELTA.md', 'analysis/analyze_replication.py',
            'analysis/audit_reuse.py', 'analysis/review_execution.py', 'analysis/review_results.py',
            'analysis/test_analyze_replication.py', 'analysis/test_audit_reuse.py',
            'analysis/test_review_execution.py', 'analysis/test_review_results.py',
            'analysis/test_run_mechanism.py', 'receipts/runtime_copy_manifest.json',
            'receipts/FROZEN_CODE_COMMIT.txt', 'receipts/device_preflight.json',
            'receipts/final_progress_snapshot.json', 'results/final_progress.json',
            'results/execution_review.json', 'results/independent_results.json',
            'results/independent_verifier_checks.json',
        }
    assert not common - names, sorted(common - names)
    selected |= common
    selected |= {n for n in names if any(n.startswith(p) for p in prefixes)}
    for row in protocol['deploy_files']:
        member = row.get('local_path', row.get('local', ''))
        if member not in names:
            matches = [n for n in names if member.endswith('/' + n)]
            assert len(matches) == 1, member
            member = matches[0]
        assert sha(z.read(member)) == row['sha256'], member
        selected.add(member)
    assert not any(n.startswith(('input/paper_context/', 'input/R14/')) or n.startswith('CODEX_') for n in selected)
    assert not any(n.endswith(('.onnx', '.hef', '.engine', '.pt', '.pth', '.safetensors')) for n in selected)
    return sorted(selected), protocol, protocol_hash


def build_bundle(kind):
    filename, expected = SOURCES[kind]
    archive = INPUT / filename
    assert sha(archive.read_bytes()) == expected
    z = zipfile.ZipFile(archive)
    members, protocol, protocol_hash = select_members(z, kind)
    original_sums = {}
    for line in z.read('SHA256SUMS').decode().splitlines():
        h, name = line.split(None, 1)
        original_sums[name.lstrip('*')] = h
    entries, data_by_name, hits = [], {}, []
    text_count = 0
    for member in members:
        data = z.read(member)
        digest = sha(data)
        assert original_sums.get(member) == digest, f'Original checksum mismatch: {member}'
        data_by_name[member] = data
        entries.append({'member': member, 'bytes': len(data), 'sha256': digest})
        found, is_text = secret_scan(member, data)
        hits += found
        text_count += int(is_text)
    digest_map = collections.defaultdict(list)
    for row in entries:
        digest_map[row['sha256']].append(row['member'])
    local_code_checks = []
    for row in protocol['local_code']:
        matches = digest_map[row['sha256']]
        assert matches, row['path']
        local_code_checks.append({'original_path': row['path'], 'sha256': row['sha256'], 'included_members': matches})
    reports = []
    report_prefix = f'results/mechanism/{protocol_hash}/reports/'
    for member in members:
        if member.startswith(report_prefix) and member.endswith('.json'):
            r = json.loads(data_by_name[member])
            assert r['status'] == 'complete' and r['protocol_sha256'] == protocol_hash
            assert r['accepted_work_drained'] and r['completed_work_units'] > 0
            for path, digest in r['loaded_source_hashes'].items():
                assert digest in digest_map, (member, path)
            model = r['identity']['model_id']
            series = 'regnet_confirmed_factorial' if kind == 'regnet' and model.startswith('regnet') else 'earlier_resnet_native_only' if kind == 'regnet' else 'resnet_fresh_factorial'
            reports.append({'member': member, 'series': series, 'run_id': r['run_id'],
                            'model': model, 'cut': r['identity']['case_id'], 'chain': r['chain'],
                            'schedule': r['schedule'], 'block': r['block'], 'pid': r['pid']})
    counts = dict(collections.Counter(r['series'] for r in reports))
    assert counts == ({'regnet_confirmed_factorial': 40, 'earlier_resnet_native_only': 20} if kind == 'regnet' else {'resnet_fresh_factorial': 40}), counts
    assert len({r['run_id'] for r in reports}) == len(reports)
    assert all(r['chain'] == 'native' for r in reports if r['series'] == 'earlier_resnet_native_only')
    snapshot_counts = collections.Counter()
    for n in members:
        if n.startswith(f'results/mechanism/{protocol_hash}/snapshots/'):
            for phase in ('before', 'after', 'stability'):
                if f'_{phase}_' in n:
                    snapshot_counts[phase] += 1
    assert dict(snapshot_counts) == {k: len(reports) for k in ['before', 'after', 'stability']}
    manifest = {
        'schema': 'unchanged-original-evidence-extract-v1',
        'source_archive': {'filename': filename, 'bytes': archive.stat().st_size, 'sha256': expected},
        'selection': 'Original protocol-bound runtime source closure, case configurations, confirmed process reports and states, analysis, and frozen reused functional evidence. No model binaries, manuscript inputs, task prompts, or pilot timing reports.',
        'protocol_sha256': protocol_hash,
        'files': entries,
        'validation': {'original_SHA256SUMS_all_members_match': True,
                       'protocol_deploy_files_matched': len(protocol['deploy_files']),
                       'pinned_local_code_matches': local_code_checks,
                       'loaded_source_hashes_all_confirmed_reports_covered': True,
                       'confirmed_process_counts': counts, 'snapshot_counts': dict(snapshot_counts)},
        'series': reports,
        'external_requirements': [
            'New hardware collection requires the specified H10/Orin setup, SDKs, TensorRT, Python dependencies and hardware profile.',
            'Original HEFs, TensorRT engines, ONNX models, full benchmark artifacts and original quality datasets are external. Their paths and hashes are preserved in PROTOCOL.json.',
            'Historical absolute paths are provenance identifiers; reproducing collection requires explicit path mapping and access to the external artifacts.',
            'These extracts establish inspectable recorded evidence and source copies; they do not by themselves recreate the historical environment or establish complete raw-dependency archival.'
        ],
        'functional_support_note': 'Frozen functional prerequisites retain original canary/pilot path names and historical reference records. They are not additional timing measurements and are not pooled into the reported process groups.',
        'generated_files_inside_zip': ['EXTRACT_MANIFEST.json', 'EXTRACT_README.md'],
    }
    stem = f'{kind}_scheduling_evidence'
    readme = f'''# Original scheduling evidence extract\n\nSource: `{filename}`\nSHA256: `{expected}`\n\nAll selected original members are byte-identical and retain their original paths. `EXTRACT_MANIFEST.json` binds each member to its original archive and SHA256. The two EXTRACT files are new packaging metadata. Original README commands and statements describe the full source archive; they are not a claim that every original dependency is bundled here.\n\nThe process groups are {json.dumps(counts, sort_keys=True)}. The earlier twenty-process Native-only ResNet series is separate from both forty-process factorial studies. Use the manifest's series index; do not pool these observations.\n\nAll protocol-deployed source files and separately pinned local controller files are included with matching hashes. Each confirmed process has before, stability and after state records. Reused functional checks retain their original canary/pilot provenance; pilot timing reports, model binaries, manuscript inputs and personal task prompts are excluded. Small prepared-input and output-reference tensors are functional evidence, not model binaries.\n\nOffline arithmetic can use these recorded reports and the accompanying analysis source. New hardware measurements additionally require the original model artifacts, datasets/benchmark artifacts, compatible vendor SDKs and recorded device configuration. Source copies and recorded states do not recreate every historical environment.\n'''
    out = BASE / f'{stem}.zip'
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for member in members:
            info = zipfile.ZipInfo(member, (2026, 10, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            target.writestr(info, data_by_name[member])
        for name, data in [('EXTRACT_MANIFEST.json', json.dumps(manifest, indent=2, sort_keys=True) + '\n'), ('EXTRACT_README.md', readme)]:
            info = zipfile.ZipInfo(name, (2026, 10, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, data)
    with zipfile.ZipFile(out) as target:
        assert target.testzip() is None
        for row in entries:
            assert sha(target.read(row['member'])) == row['sha256']
    # Keep the ZIP only as an intermediate; publish the smaller deterministic tar.xz.
    zip_out = out
    out = BASE / f'{stem}.tar.xz'
    with zipfile.ZipFile(zip_out) as original, tarfile.open(out, 'w:xz', preset=6, format=tarfile.PAX_FORMAT) as target:
        for member in sorted(original.namelist()):
            data = original.read(member)
            info = tarfile.TarInfo(member)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            target.addfile(info, io.BytesIO(data))
    with zipfile.ZipFile(zip_out) as original, tarfile.open(out, 'r:xz') as target:
        assert sorted(original.namelist()) == sorted(target.getnames())
        for member in target.getmembers():
            assert target.extractfile(member).read() == original.read(member.name)
    write_json(BASE / f'{stem}.manifest.json', manifest)
    return {'filename': out.name, 'bytes': out.stat().st_size, 'sha256': sha(out.read_bytes()),
            'source_archive': filename, 'original_member_count': len(members),
            'original_uncompressed_bytes': sum(r['bytes'] for r in entries),
            'process_counts': counts, 'snapshot_counts': dict(snapshot_counts),
            'source_deploy_files_verified': len(protocol['deploy_files']),
            'scan': {'text_files_checked': text_count, 'nontext_files': len(members)-text_count, 'candidates': hits}}


def main():
    global BASE, INPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True, help='Directory containing the two hash-pinned original ZIP archives.')
    parser.add_argument('--output-dir', type=Path, default=BASE, help='Separate output directory for rebuilt extracts and local validation reports.')
    args = parser.parse_args()
    INPUT = args.input_dir.resolve()
    BASE = args.output_dir.resolve()
    BASE.mkdir(parents=True, exist_ok=True)
    audit_source = INPUT / SOURCES['regnet'][0]
    assert sha(audit_source.read_bytes()) == SOURCES['regnet'][1]
    validation = {'source_archive': SOURCES['regnet'][0], 'source_archive_sha256': SOURCES['regnet'][1], 'files': {}}
    with zipfile.ZipFile(audit_source) as z:
        ids = None
        for name, (size, expected) in AUDITS.items():
            data = z.read(name)
            assert len(data) == size and sha(data) == expected
            (BASE / name).write_bytes(data)
            rows = list(csv.DictReader(io.StringIO(data.decode('utf-8'))))
            current_ids = {r['config_id'] for r in rows}
            assert len(current_ids) == 450 and '' not in current_ids
            if ids is None:
                ids = current_ids
                assert len(rows) == 450
            else:
                assert current_ids == ids
            hits, _ = secret_scan(name, data)
            validation['files'][name] = {'bytes': size, 'sha256': expected, 'rows': len(rows), 'distinct_config_ids': len(current_ids), 'credential_candidates': hits}
            if name == 'EVIDENCE_AUDIT.csv':
                quality = dict(collections.Counter(r['passes_5pct'] for r in rows))
                assert quality == {'True': 407, 'False': 43}
                validation['numeric_quality_rule'] = quality
        validation['same_450_config_ids_in_both_files'] = True
    write_json(BASE / 'AUDIT_VALIDATION.json', validation)
    bundles = [build_bundle(k) for k in SOURCES]
    scan = {'method': 'UTF-8 text scan for private keys, recognized provider tokens, credential-bearing URLs and quoted credential literals; values are never reported.',
            'scope': 'Both publication CSVs and every original member selected into the two evidence extracts.',
            'limits': 'Pattern scanning cannot prove absence of arbitrary or encrypted credentials. Binary members are small functional tensors/reference outputs, not credential stores.',
            'audit_candidates': {k:v['credential_candidates'] for k,v in validation['files'].items()},
            'bundles': {b['filename']:b.pop('scan') for b in bundles}}
    write_json(BASE / 'CREDENTIAL_SCAN.json', scan)
    write_json(BASE / 'PACKAGE_SUMMARY.json', {'bundles': bundles, 'audit': validation})
    public = [BASE / n for n in AUDITS] + [BASE / b['filename'] for b in bundles]
    (BASE / 'SHA256SUMS').write_text(''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in public))
    print(json.dumps({'bundles': bundles, 'audit_rows': {k:v['rows'] for k,v in validation['files'].items()}, 'credential_candidate_count': sum(len(x) for x in scan['audit_candidates'].values())+sum(len(x['candidates']) for x in scan['bundles'].values())}, indent=2))


if __name__ == '__main__':
    main()
