from pathlib import Path
import xml.etree.ElementTree as E,re,copy,json,argparse
R=Path(__file__).resolve().parent
P=argparse.ArgumentParser();P.add_argument('--source',type=Path,default=R/'graphics/Grafiken_DE_EN/English');P.add_argument('--output',type=Path,default=R/'drawio7_normalized');a=P.parse_args();SRC=a.source;OUT=a.output
IDS=['01','02','03','04','10','11','12','13','14','15','16','17','18','24','25','26','27']
LINEWIDTH=355.725
E.register_namespace('','http://www.w3.org/2000/svg')
records=[]
def fsize(e,parent):
 while e is not None:
  s=e.get('font-size') or re.search(r'(?:^|;)\s*font-size\s*:\s*([\d.]+)(?:px|pt)?',e.get('style',''))
  if s:return float(s.group(1) if not isinstance(s,str) else s.replace('px','').replace('pt',''))
  e=parent.get(e)
 return 10.
for n in IDS:
 svg=next((SRC/'Export_SVG').rglob(n+'_*.svg'));draw=next((SRC/'DrawIO').rglob(n+'_*.drawio'))
 st=E.parse(svg);root=st.getroot();dt=E.parse(draw);parents={c:p for p in root.iter() for c in p}
 W=float(root.get('width').replace('px',''));frac=.60 if n in ['01','02','03','04'] else 1.
 if n=='02':
  cells=list(dt.getroot().iter('mxCell'));removed={c.get('parent') for c in cells if c.get('value') in ['ISP','H.264']}
  while True:
   count=len(removed);removed.update(c.get('id') for c in cells if c.get('parent') in removed or c.get('source') in removed or c.get('target') in removed)
   if count==len(removed):break
  for p in dt.getroot().iter():
   for c in list(p):
    if c.tag=='mxCell' and c.get('id') in removed:p.remove(c)
  for e in list(root.iter()):
   if e.get('data-cell-id') in removed and e in list(parents.get(e,[])):parents[e].remove(e)
 else:removed=set()
 # DrawIO labels remain literal, with their font and existing geometry updated.
 def target(old,txt):
  if frac<1:return 8.7 if old>=28 else 7.2
  if old>=25:return 9.5
  return 8.6 if old>=20 else 7.2
 textupdates=[]
 for e in root.iter():
  if e.tag.endswith('text'):
   old=fsize(e,parents);txt=''.join(e.itertext()).strip()
   if not txt:continue
   pt=target(old,txt);new=pt*W/(LINEWIDTH*frac)
   e.set('font-size',f'{new:.3f}px')
   style=re.sub(r'font-size\s*:[^;]+;?', '',e.get('style',''))
   e.set('style',style+f';font-size:{new:.3f}px')
   textupdates.append({'text':txt,'old_css_px':old,'new_css_px':round(new,3),'target_final_pt':pt})
 for cell in dt.getroot().iter('mxCell'):
  value=cell.get('value','').strip();style=cell.get('style','');m=re.search(r'fontSize=([\d.]+)',style)
  if not value or not m:continue
  old=float(m.group(1));new=target(old,value)*W/(LINEWIDTH*frac)
  cell.set('style',re.sub(r'fontSize=[\d.]+',f'fontSize={new:.3f}',style))
 os=OUT/'Export_SVG'/svg.relative_to(SRC/'Export_SVG');od=OUT/'DrawIO'/draw.relative_to(SRC/'DrawIO');os.parent.mkdir(parents=True,exist_ok=True);od.parent.mkdir(parents=True,exist_ok=True)
 st.write(os,encoding='utf-8',xml_declaration=True);dt.write(od,encoding='utf-8',xml_declaration=True)
 records.append({'id':n,'width_fraction':frac,'body_text_width_bp':LINEWIDTH,'removed_cell_ids':sorted(removed),'typography_changes':textupdates})
(OUT.parent/'DRAWIO7_TYPOGRAPHY_PLAN.json').write_text(json.dumps(records,indent=2,ensure_ascii=False))
