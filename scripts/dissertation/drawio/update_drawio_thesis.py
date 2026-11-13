#!/usr/bin/env python3
"""Export supplied English DrawIO diagrams with dissertation-scale typography."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True,help='Grafiken_DE_EN/English from supplied DrawIO7 bundle');p.add_argument('--output',type=Path,required=True);p.add_argument('--project',type=Path);a=p.parse_args();here=Path(__file__).resolve().parent
work=a.output.parent/'drawio_typography_working';a.output.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,str(here/'normalize_drawio7.py'),'--source',str(a.source),'--output',str(work)],check=True)
subprocess.run([sys.executable,str(here/'refine_drawio7_labels.py'),'--working',str(work)],check=True)
cmd=[sys.executable,str(here/'export_drawio7.py'),'--source',str(work),'--output',str(a.output)]
if a.project:cmd+=['--project',str(a.project)]
subprocess.run(cmd,check=True)
manifest=a.output.parent/'DRAWIO7_EXPORTS.json';rows=json.loads(manifest.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for r in rows:
 n=r['id'];draw=next((a.source/'DrawIO').rglob(n+'_*.drawio'));svg=next((a.source/'Export_SVG').rglob(n+'_*.svg'));frac='.60' if n in ['01','02','03','04'] else '1.0'
 r['original_drawio_sha256']=sha(draw);r['original_svg_sha256']=sha(svg);r['width_fraction']=float(frac)
 r['semantic_changes']=({'removed':['ISP','H.264'],'reason':'Hailo-8 has no video encoder; the supplied general-purpose ISP block is unsupported.'} if n=='02' else {'old':'Workload + calibration','new':'Compiled subgraph','reason':'Calibration is not part of timed stage execution.'} if n=='14' else {'old':'Measurement boundaries; channel wiring to be defined for each measurement series','new':'System input and downstream power paths','reason':'Describe the schematic directly without implying an unfinished measurement step.'} if n=='11' else [])
 r['typography']={'primary_pt':8.7 if float(frac)<1 else 8.6,'secondary_pt':7.2,'exceptions':'Long narrow labels are adjusted locally; see label refinement script.'}
 if a.project:
  for tex in a.project.rglob('*.tex'):
   s=tex.read_text();pattern=r'\\includegraphics\[[^\]]*\]\{'+re.escape(r['project_file'])+r'\}'
   if re.search(pattern,s):tex.write_text(re.sub(pattern,lambda m:r'\includegraphics[width='+frac+r'\linewidth]{'+r['project_file']+'}',s))
manifest.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'exported':len(rows),'manifest':str(manifest),'working_sources':str(work)}))
