#!/usr/bin/env python3
"""Export the supplied English DrawIO7 SVGs as PDF, preserving their content."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,shutil,subprocess
import fitz
P=argparse.ArgumentParser();P.add_argument('--source',required=True,type=Path);P.add_argument('--output',required=True,type=Path);P.add_argument('--project',type=Path);a=P.parse_args();a.output.mkdir(parents=True,exist_ok=True)
MAP={'01':'9_resources/illustrations/architecture_orin_nx.pdf','02':'9_resources/illustrations/architecture_hailo8.pdf','03':'9_resources/illustrations/architecture_hailo10h.pdf','04':'9_resources/illustrations/architecture_deepx_dxm1.pdf','10':'9_resources/layout_v48/energy/figures/measurement_boundaries.pdf','11':'9_resources/review_v49/power_boundaries.pdf','12':'9_resources/layout_v48/foundations/figures/related_work_settings.pdf','13':'9_resources/illustrations/runner_tensor_boundaries.pdf','14':'9_resources/integration_v47/methods/cost_decomposition.pdf','15':'9_resources/layout_v48/methods/edge_pipeline.pdf','16':'9_resources/layout_v48/methods/multicontext.pdf','17':'9_resources/layout_v48/methods/split_workflow.pdf','18':'9_resources/integration_v47/methods/throughput_taxonomy.pdf','24':'9_resources/layout_v48/foundations/figures/management_overview.pdf','25':'9_resources/layout_v48/foundations/figures/toolchain_bridge.pdf','26':'9_resources/layout_v48/foundations/figures/urecs_architecture.pdf','27':'9_resources/layout_v48/foundations/figures/urecs_power.pdf'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def one(v):
 n,target=v;svg=next((a.source/'Export_SVG').rglob(n+'_*.svg'));draw=next((a.source/'DrawIO').rglob(n+'_*.drawio'));out=a.output/(svg.stem+'.pdf')
 subprocess.run(['inkscape',str(svg),'--export-area-page','--export-type=pdf','--export-filename='+str(out)],check=True,capture_output=True)
 d=fitz.open(out);assert len(d)==1;page=d[0];assert not page.get_images();spans=[s for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
 r={'id':n,'project_file':target,'source_archive':'Grafiken_DrawIO-7.zip','source_library_file_id':'libfile_f8b451836af881918c72662a48305526','drawio_path':str(draw.relative_to(a.source)),'drawio_sha256':sha(draw),'svg_path':str(svg.relative_to(a.source)),'svg_sha256':sha(svg),'pdf_path':str(out),'pdf_sha256':sha(out),'page_size_points':[page.rect.width,page.rect.height],'spans':[{'text':s['text'],'font_size_points':s['size']} for s in spans],'raster_images':0,'semantic_changes':[]}
 if a.project:
  dest=a.project/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(out,dest)
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:r=list(e.map(one,MAP.items()))
(a.output.parent/'DRAWIO7_EXPORTS.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'exported':len(r),'output':str(a.output)}))
