#!/usr/bin/env python3
"""Export the small portable RQ2 input projection from an immutable ledger.

This is a read-only import adapter. Local paths and large runtime payloads are
discarded. Source-byte and canonical-row hashes preserve the original binding.
"""
import argparse
import hashlib
import json
from pathlib import Path


def project(path):
    payload=path.read_bytes();ledger=json.loads(payload);rows=[]
    for row in ledger['rows']:
        a=row.get('actual_artifact_authority') or {};bound=a.get('bound_runtime_artifacts',{});obs=a.get('part2_engine_observation') or {}
        artifacts={'part1_sha256':a.get('part1',{}).get('sha256') or bound.get('part1_runtime',{}).get('sha256'),
            'part2_engine_sha256':obs.get('artifact',{}).get('sha256') or bound.get('engine',{}).get('sha256'),
            'source_part2_onnx_sha256':a.get('source_part2_onnx',{}).get('sha256') or bound.get('source_part2_onnx',{}).get('sha256'),
            'boundary_inputs':a.get('boundary_inputs'),'authority_kind':a.get('authority_kind','cached_artifacts_with_exact_hashes'),
            'original_boundary_mode':a.get('original_boundary_mode')}
        references={}
        for key,ref in row['source_authorities'].items():
            if isinstance(ref,dict) and ref.get('sha256'):
                references[key]={k:v for k,v in ref.items() if k in ['sha256','canonical_row_sha256','selector','archive_member','archive_member_sha256']}
        rows.append({k:row.get(k) for k in ['generic_uid','model','setup','setup_id','case_id','task','model_sha256','boundary_id','boundary_count',
            'part2_input_count','execution_precision','full_product_identity','effective_generic_fps','effective_repeats','quality_eligible',
            'quality_status','measurement_status','admission_mode','observation_mode']}|{'artifacts':artifacts,'source_sha256':references})
    return {'schema':'rq2-final-generic-projection-v1','source_snapshot_sha256':hashlib.sha256(payload).hexdigest(),
        'source_selection_sha256':ledger['selection_authority']['sha256'],'source_summary':ledger['summary'],'rows':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-sha256')
    args=parser.parse_args();result=project(args.ledger)
    if args.expected_sha256 and result['source_snapshot_sha256']!=args.expected_sha256:
        raise ValueError('Immutable source ledger hash differs')
    if args.output.exists():raise ValueError('Choose a new output file')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
