from pathlib import Path
import xml.etree.ElementTree as E,re,json,argparse
R=Path(__file__).resolve().parent;P=argparse.ArgumentParser();P.add_argument('--working',type=Path,default=R/'drawio7_normalized');a=P.parse_args();ROOT=a.working;NS='http://www.w3.org/2000/svg';E.register_namespace('',NS)
changes=[]
for p in sorted((ROOT/'Export_SVG').rglob('*.svg')):
 n=p.name[:2];st=E.parse(p);sr=st.getroot();W=float(sr.get('width'));frac=.6 if n in ['01','02','03','04'] else 1;draw=next((ROOT/'DrawIO').rglob(n+'_*.drawio'));dt=E.parse(draw)
 edits=[]
 def norm(s):return re.sub(r'\s+',' ',s).strip()
 def drawval(old,new):
  for c in dt.getroot().iter('mxCell'):
   if norm(c.get('value',''))==norm(old):c.set('value',new)
 def font(e,pt):
  txt=''.join(e.itertext());v=pt*W/(355.725*frac);e.set('font-size',f'{v:.3f}px');e.set('style',re.sub(r'font-size\s*:[^;]+;?','',e.get('style',''))+f';font-size:{v:.3f}px')
  for c in dt.getroot().iter('mxCell'):
   if norm(c.get('value',''))==norm(txt):c.set('style',re.sub(r'fontSize=[\d.]+',f'fontSize={v:.3f}',c.get('style','')))
  edits.append({'text':txt,'font_final_pt':pt})
 def lines(e,new):
  old='\n'.join(e.itertext());x=e.get('x');ys=[float(t.get('y',e.get('y','0'))) for t in e if t.tag.endswith('tspan')]
  mid=sum(ys)/len(ys) if ys else float(e.get('y','0'));fs=float(e.get('font-size').replace('px',''));leading=fs*1.15;ls=new.split('\n');start=mid-leading*(len(ls)-1)/2
  for c in list(e):e.remove(c)
  e.text=None
  for i,l in enumerate(ls):E.SubElement(e,'{'+NS+'}tspan',{'x':x,'y':f'{start+i*leading:.3f}'}).text=l
  drawval(old,new);edits.append({'old':old,'new':new})
 for e in sr.iter():
  if not e.tag.endswith('text'):continue
  txt=' '.join(e.itertext());tt=norm(txt)
  if n=='01' and '1024-core' in tt:font(e,7.7)
  if n=='03' and 'Resource layout' in tt:font(e,6.6)
  if n=='11' and tt=='Measurement boundaries; channel wiring to be defined for each measurement series':
   new='System input and downstream power paths'
   e.text=new;drawval(tt,new);edits.append({'old':tt,'new':new})
  if n=='11' and tt=='Voltage regulator':lines(e,'Voltage\nregulator')
  if n=='11' and 'auxiliary components' in tt:font(e,7.8)
  if n=='12' and tt.startswith('Edge node'):lines(e,'Edge\nnode '+tt[-1])
  if n=='12' and ('Network variability' in tt or tt=='Stage balance'):font(e,7.2)
  if n=='12' and tt=='Stage balance':
   e.set('y','472')
   for c in dt.getroot().iter('mxCell'):
    if norm(c.get('value',''))==tt:
     g=c.find('mxGeometry')
     if g is not None:g.set('y',str(float(g.get('y','0'))-10))
  if n=='14' and 'Workload +' in tt:lines(e,'Compiled\nsubgraph')
  if n=='15' and tt in ['Preprocessing','Postprocessing']:font(e,7.8)
  if n=='15' and tt=='Application':font(e,7.2)
  if n=='17' and 'requirements' in tt and len(list(e)):font(e,8.)
  if n=='17' and tt=='Boundary tensor size':font(e,7.0)
  if n=='16' and tt=='Requires multiple contexts':lines(e,'Requires\nmultiple contexts')
  if n=='27' and tt=='Auxiliary supply':font(e,7.2)
  # Increase manual tspan leading to match the enlarged type, about its old centre.
  ts=[t for t in e if t.tag.endswith('tspan')]
  if len(ts)>1:
   fs=float(e.get('font-size').replace('px',''));ys=[float(t.get('y',e.get('y','0'))) for t in ts];mid=sum(ys)/len(ys);leading=fs*1.15
   for i,t in enumerate(ts):t.set('y',f'{mid+leading*(i-(len(ts)-1)/2):.3f}')
   txtn='\n'.join(t.text or '' for t in ts)
   for c in dt.getroot().iter('mxCell'):
    if norm(c.get('value',''))==norm(txtn):
     style=c.get('style','');style=re.sub(r'lineHeight=[^;]+;?','',style);c.set('style',style+';lineHeight=1.15;')
 st.write(p,encoding='utf-8',xml_declaration=True);dt.write(draw,encoding='utf-8',xml_declaration=True)
 changes.append({'id':n,'changes':edits})
(ROOT.parent/'DRAWIO7_LABEL_REFINEMENTS.json').write_text(json.dumps(changes,indent=2,ensure_ascii=False))
