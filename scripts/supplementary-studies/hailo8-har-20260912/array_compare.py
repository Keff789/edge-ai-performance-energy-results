#!/usr/bin/env python3
"""Prepare exact recorded feeds, execute local ORT references, compare saved stages."""
from __future__ import annotations
import argparse, csv, json, sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import bound, identity, plain, read_json, write_json

def scores(value, labels):
    import numpy as np
    value = np.asarray(value)
    if value.shape != (16, 1000) or value.dtype.kind != 'f' or not np.isfinite(value).all():
        raise ValueError('Explizite finite Float-Logits [16,1000] erforderlich')
    order = np.argsort(-value, axis=1, kind='stable')[:, :5]
    return {'shape': list(value.shape), 'dtype': str(value.dtype), 'finite': True,
        'top1': order[:,0].tolist(), 'top5': order.tolist(),
        'top1_correct': int((order[:,0] == labels).sum()),
        'top5_correct': int((order == labels[:,None]).any(axis=1).sum()), 'count':16}

def differences(a,b):
    import numpy as np
    a=np.asarray(a,dtype=np.float64);b=np.asarray(b,dtype=np.float64); delta=b-a
    an=np.linalg.norm(a,axis=1);bn=np.linalg.norm(b,axis=1);den=an*bn
    cos=np.divide(np.sum(a*b,axis=1),den,out=np.full(16,np.nan),where=den!=0)
    cos[np.logical_and(an==0,bn==0)]=1.0
    rows=[None if not np.isfinite(v) else float(v) for v in cos]
    finite=[v for v in rows if v is not None]
    return {'max_abs_difference':float(np.max(np.abs(delta))),
      'rms_difference':float(np.sqrt(np.mean(delta**2))),
      'mean_logit_cosine':sum(finite)/len(finite) if finite else None,
      'min_logit_cosine':min(finite) if finite else None,
      'per_image_cosine':rows,
      'top1_changed_count':int((a.argmax(1)!=b.argmax(1)).sum()),
      'numerically_equal':bool(np.array_equal(a,b))}

def save_array(out,name,value):
    import numpy as np
    p=out/(name+'.npy');np.save(p,value,allow_pickle=False);return identity(p)

def prepare(build, runtime, out):
    import numpy as np
    import onnxruntime as ort
    ort.disable_telemetry_events()
    build=plain(build);runtime=plain(runtime);out=plain(out);out.mkdir(parents=True,exist_ok=True)
    br=read_json(build/'request.json');bs=read_json(build/'summary.json');result=read_json(build/'build_result.json')
    rr=read_json(runtime/'runtime_request.json');rs=read_json(runtime/'results/runtime_result.json')
    previous=read_json(runtime/'comparison.json')
    if (br['model']!='mobilenet_v3_large' or br['family']!='hailo8' or result['hw_arch']!='hailo8'
          or bs.get('model_build_status')!='pass' or bs.get('gpu_execution_status')!='pass'
          or previous.get('g3_status')!='pass' or rs.get('runtime_status')!='pass'
          or rr.get('setup_id')!='orin_nx_hailo8_01'):
        raise ValueError('Die gebundene Hailo8-Build-/Runtimekette ist nicht vollstaendig')
    bound(rr['model_build_summary'])
    if Path(rr['model_build_summary']['path']).resolve()!= (build/'summary.json').resolve():
        raise ValueError('Runtime stammt nicht vom ausgewaehlten GPU-Build')
    for field,role in [('source_onnx','source'),('compiler_onnx','compiler')]:
        if rr['expected_'+role+'_onnx_sha256' if role=='source' else 'expected_compiler_sha256'] != br[field]['sha256']:
            raise ValueError('ONNX-Identitaet passt nicht zum Runtimeauftrag')
    ids=[x['id'] for x in rr['images']];labels=np.array([x['label'] for x in rr['images']],dtype=np.int64)
    if len(ids)!=16 or len(set(ids))!=16 or ((labels<0)|(labels>=1000)).any():raise ValueError('Fixed16 falsch')
    if [(x['id'],x['label'],x['sha256']) for x in br['images']] != [(x['id'],x['label'],x['sha256']) for x in rr['images']]:
        raise ValueError('Build- und Runtimebildbindung abweichend')
    gpu=bs['private_hef'];cpu=br['cpu_hef']
    if rr['gpu_hef']['sha256']!=gpu['sha256'] or rr['cpu_hef']['sha256']!=cpu['sha256']:
        raise ValueError('Falsches HEF-Paar')
    # Existing HEFs are verified, never loaded into HailoRT or copied to Git.
    frozen=[identity(bound(x)) for x in (cpu,gpu,br['source_onnx'],br['compiler_onnx'])]
    arrays_record={**rs['arrays'],'path':str(runtime/'results/runtime_arrays.npz')}
    path=bound(arrays_record);frozen.append(identity(path))
    if path.stat().st_size>128*1024*1024:raise ValueError('Runtimearray ueber 128 MiB')
    with np.load(path,allow_pickle=False) as z:
        required={r+s for r in ('cpu_hef','gpu_hef') for s in ('_logits','_logical_feed','_actual_feed')}
        if set(z.files)!=required:raise ValueError('Unerwartete Runtimearrays')
        data={k:z[k] for k in z.files}
    feed=data['gpu_hef_logical_feed']
    if feed.shape!=(16,224,224,3) or feed.dtype!=np.float32 or not np.isfinite(feed).all():
        raise ValueError('Nur bereits normalisierte NHWC-FLOAT32-Feeds [16,224,224,3]')
    if rs.get('actual_vstream_feed_equal') is not True:raise ValueError('VStream-Gleichheit nicht bestaetigt')
    baselines={};reports={}
    for role in ('cpu_hef','gpu_hef'):
        s=rs['stages'][role]
        if s['ids']!=ids or s['artifact_sha256']!=rr[role]['sha256'] or s.get('actual_vstream_call_count')!=16:
            raise ValueError('Ungebundene Runtimeausgabe '+role)
        if (data[role+'_actual_feed'].shape!=(16,1,224,224,3) or
            data[role+'_actual_feed'].dtype!=np.float32 or
            not np.array_equal(data[role+'_actual_feed'][:,0],feed) or
            not np.array_equal(data[role+'_logical_feed'],feed)):
            raise ValueError('Die tatsaechlichen Eingangsbuffer unterscheiden sich')
        baselines[role]=data[role+'_logits'];reports[role]=scores(baselines[role],labels)
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    for role,field in [('source_float','source_onnx'),('build_float','compiler_onnx')]:
        p=bound(br[field]);session=ort.InferenceSession(str(p),sess_options=opts,providers=['CPUExecutionProvider'])
        ins=session.get_inputs();outs=session.get_outputs()
        if len(ins)!=1 or len(outs)!=1 or ins[0].name!=rr['input_name'] or outs[0].name!=rr['output_name']:
            raise ValueError('ONNX-I/O-Vertrag abweichend')
        values=[]
        for image in feed:
            arr=session.run([outs[0].name],{ins[0].name:np.ascontiguousarray(image.transpose(2,0,1)[None])})[0]
            if arr.shape!=(1,1000):raise ValueError('ONNX-Ausgabe nicht [1,1000]')
            values.append(arr[0])
        baselines[role]=np.stack(values);reports[role]=scores(baselines[role],labels)
    for role,s in reports.items():
        old=previous['stages'][role]
        if s['top1']!=old['top1'] or any(set(a)!=set(b) for a,b in zip(s['top5'],old['top5'])):
            raise ValueError('Vorhandene Fixed16-Vorhersagen nicht reproduziert: '+role)
    hars={}
    for role,key in [('parsed_native','parsed_har_path'),('quantized','quant_har_path')]:
        p=plain(Path(result[key]))
        if not p.is_relative_to(build) or p.suffix!='.har':raise ValueError('HAR ausserhalb des originalen privaten Builds')
        hars[role]=identity(p);frozen.append(hars[role])
    receipt=read_json(build/'private_hef_receipt.json')
    cpu_receipt=br['cpu_build_receipt']
    if (receipt['hef_sha256']!=gpu['sha256'] or receipt['compiler_onnx_sha256']!=br['compiler_onnx']['sha256']
        or receipt['cache_payload']!=cpu_receipt['cache_payload']):raise ValueError('Buildreceipt nicht gebunden')
    req={'schema':'hailo8-har-comparison-r1','model':br['model'],'family':'hailo8',
        'net_name':result['net_name'],'sdk_version':receipt['hailo_sdk_version'].split(':')[-1],
        'venv_python':br['venv_python'],'image_ids':ids,'labels':labels.tolist(),'count':16,
        'feed_semantics':'recorded_actual_FLOAT32_VStreams_NHWC_already_imagenet_normalized_NO_new_normalization',
        'feed':save_array(out,'feed',feed),'baseline_arrays':{k:save_array(out,k,v) for k,v in baselines.items()},
        'baseline_metrics':reports,'hars':hars,'input_files':frozen,
        'artifact_identity':{'cpu_hef':cpu,'gpu_hef':gpu,'source_onnx':br['source_onnx'],'compiler_onnx':br['compiler_onnx']},
        'har_binding':'original_build_report_paths; HAR fingerprints recorded NOW, not retrospectively attested at build time',
        'runtime_array_identity':arrays_record,'images_usage':'opened_development_diagnostic_not_holdout',
        'hef_build_invoked':False,'hardware_inference_invoked':False,'model_acceptance':'NOT_EVALUATED'}
    for item in frozen:bound(item)
    write_json(out/'comparison_request.json',req);write_json(out/'prepare_result.json',{'status':'pass','reference_topk_reproduced':True,'ort_version':ort.__version__})
    return req

def aggregate(request_path,out):
    import numpy as np
    out=Path(out);req=read_json(request_path);labels=np.array(req['labels']);values={}
    for k,item in req['baseline_arrays'].items():values[k]=np.load(bound(item),allow_pickle=False)
    stages={k:{'status':'evaluated',**scores(v,labels)} for k,v in values.items()}
    for stage in ('parsed_native','quantized'):
        result_path=out/stage/'result.json';s=read_json(result_path) if result_path.exists() else {'status':'not_available'}
        process_path=out/stage/'process.json';p=read_json(process_path) if process_path.exists() else {}
        if (s.get('status')=='evaluated' and p.get('returncode')==0 and p.get('process_cleanup_complete') is True
            and not p.get('timed_out') and not p.get('cancelled')):
            if s.get('image_ids')!=req['image_ids'] or s.get('feed_sha256')!=req['feed']['sha256']:
                raise ValueError('HAR-Stufe nicht an denselben Auftrag gebunden')
            values[stage]=np.load(bound(s['output']),allow_pickle=False)
            stages[stage]={'status':'evaluated',**scores(values[stage],labels),'sdk_context':s['context'],'har':s['har']}
        else:stages[stage]={'status':'not_evaluated','worker':s,'process':p}
    pairs=[('source_float','build_float'),('build_float','parsed_native'),('parsed_native','quantized'),
           ('quantized','gpu_hef'),('quantized','cpu_hef'),('cpu_hef','gpu_hef')]
    comparison={a+'_vs_'+b: differences(values[a],values[b]) for a,b in pairs if a in values and b in values}
    original_inputs_unchanged=True;preservation_errors=[]
    for item in req['input_files']:
        try:bound(item)
        except Exception as exc:original_inputs_unchanged=False;preservation_errors.append(str(exc))
    complete=all(stages[s]['status']=='evaluated' for s in ('parsed_native','quantized')) and original_inputs_unchanged
    report={'schema':'hailo8-har-comparison-result-r1','status':'diagnostic_evaluated' if complete else 'incomplete',
        'model':req['model'],'image_ids':req['image_ids'],'labels':req['labels'],'stages':stages,'comparisons':comparison,
        'original_inputs_unchanged':original_inputs_unchanged,'preservation_errors':preservation_errors,
        'har_binding':req['har_binding'],'new_hef_build':False,'new_optimization':False,'new_hardware_inference':False,
        'energy':'NOT_RUN','claim_eligible':False,'quality_gate':'NOT_EVALUATED; fixed16 diagnostic only',
        'interpretation':'Compare first material numerical deviation; no universal emulation/hardware bit-exactness claim. '
                         'Only quantized.har of GPU build available; quantized_vs_cpu_hef is cross-build comparison.'}
    write_json(out/'comparison.json',report)
    with (out/'per_image.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['image_id','label']+[k+'_top1' for k in values])
        for i,key in enumerate(req['image_ids']):w.writerow([key,int(labels[i])]+[stages[k]['top1'][i] for k in values])
    lines=['# Hailo8 MobileNet: HAR-Zwischenstufen','',f"Status: **{report['status']}**",'',
      '| Stufe | Top-1 richtig | Top-5 richtig |','|---|---:|---:|']
    for k,s in stages.items():lines.append(f"| {k} | {s.get('top1_correct','nicht ausgewertet')}/16 | {s.get('top5_correct','nicht ausgewertet')}/16 |")
    lines+=['','## Grenzen','',report['interpretation'],'',req['har_binding'],'',
      'Keine Neuoptimierung, kein HEF-Neubau, keine erneute Hailo-Hardwareausfuehrung. '
      'FLOAT32-NHWC-Eingaben wurden aus dem gebundenen Runtime-Dump uebernommen, nicht neu normalisiert.',
      '', '## Numerische Vergleiche','', '| Vergleich | Maximaler Absolutfehler | RMS | Mittlere Logit-Cosine | Top-1-Wechsel |','|---|---:|---:|---:|---:|']
    for k,v in comparison.items():lines.append(f"| {k} | {v['max_abs_difference']:.8g} | {v['rms_difference']:.8g} | {v['mean_logit_cosine']} | {v['top1_changed_count']} |")
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return complete

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','compare']);p.add_argument('--build',type=Path);p.add_argument('--runtime',type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--request',type=Path);a=p.parse_args()
    try:
        if a.mode=='prepare':prepare(a.build,a.runtime,a.out);return 0
        return 0 if aggregate(a.request,a.out) else 2
    except Exception as exc:
        a.out.mkdir(parents=True,exist_ok=True)
        write_json(a.out/(a.mode+'_error.json'),{'status':'failed','error':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc()})
        traceback.print_exc();return 2
if __name__=='__main__':raise SystemExit(main())
