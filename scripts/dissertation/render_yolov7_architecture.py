from pathlib import Path
import xml.etree.ElementTree as E
import html, subprocess, json, shutil
import argparse
_parser=argparse.ArgumentParser(description='Render the measured YOLOv7 architecture and exact ONNX cuts in DE/EN.')
_parser.add_argument('--output',type=Path,default=Path.cwd()/'yolov7-architecture')
BASE=_parser.parse_args().output.resolve()
W,H=1060,1090
P={'text':'#18354A','muted':'#64798A','edge':'#58758B','blue':'#2E73B6','bluefill':'#EAF2FB','green':'#25896F','greenfill':'#EAF6F1','orange':'#D18432','orangefill':'#FFF3E5','container':'#F6F8FA','border':'#D9E3EA'}
class Scene:
 def __init__(self,lang):self.lang=lang;self.nodes=[];self.edges=[];self.texts=[];self.boxes=[];self.lines=[]
 def box(self,id,x,y,w,h,fill,stroke,rx=15,sw=1.5,dash=False):self.boxes.append(dict(id=id,x=x,y=y,w=w,h=h,fill=fill,stroke=stroke,rx=rx,sw=sw,dash=dash))
 def node(self,id,x,y,w,h,label,kind='compute',fs=27):
  fill,stroke={'compute':(P['bluefill'],P['blue']),'merge':(P['greenfill'],P['green']),'io':(P['orangefill'],P['orange'])}[kind]
  self.nodes.append(dict(id=id,x=x,y=y,w=w,h=h,label=label,fill=fill,stroke=stroke,fs=fs))
 def text(self,id,x,y,w,h,label,fs=25,bold=False,color=None,align='center'):
  self.texts.append(dict(id=id,x=x,y=y,w=w,h=h,label=label,fs=fs,bold=bold,color=color or P['text'],align=align))
 def edge(self,id,points,src=None,dst=None,arrow=True,color=None,sw=2.2):self.edges.append(dict(id=id,points=points,src=src,dst=dst,arrow=arrow,color=color or P['edge'],sw=sw))
 def line(self,id,points,color,sw=2.5,dash=False):self.lines.append(dict(id=id,points=points,color=color,sw=sw,dash=dash))
 def lookup(self,id):return next(n for n in self.nodes if n['id']==id)

def build(lang):
 de=lang=='de';s=Scene(lang)
 s.box('backbone_container',8,40,314,1008,P['container'],P['border'],22)
 s.box('neck_container',350,344,430,704,P['container'],P['border'],22)
 s.box('heads_container',808,344,244,704,P['container'],P['border'],22)
 s.text('backbone_label',20,2,290,34,'Backbone',28,True)
 s.text('neck_label',350,305,430,34,'Neck',28,True)
 s.text('heads_label',808,305,244,34,'Detektionsköpfe' if de else 'Detection heads',27,True)
 # The accelerator executes the highlighted prefix only when b066 is chosen.
 s.box('b066_prefix',21,109,288,507,'#F4F9FF',P['blue'],15,2.1)
 s.text('prefix_label',27,112,276,30,'Präfix bei b066' if de else 'Prefix at b066',24,True,P['blue'])
 s.node('input',65,50,200,44,'Bild 640 × 640' if de else 'Image 640 × 640','io',25)
 s.node('stem',55,155,220,70,'Conv × 3\n32 → 64 → 64',fs=26)
 s.node('conv128',55,252,220,44,'Conv 128, s = 2',fs=26)
 s.node('silu128',55,331,220,38,'SiLU',fs=25)
 s.node('elan160',55,395,220,48,'ELAN · 256',fs=27)
 s.node('down80',55,469,220,63,'MP + Conv\nConcat','merge',25)
 s.node('elan80',55,565,220,48,'ELAN · 512',fs=27)
 s.node('back40',55,682,220,80,'MP + Conv, Concat\nELAN · 1024',fs=24)
 s.node('back20',55,875,220,80,'MP + Conv, Concat\nELAN · 1024',fs=24)
 # A compact but topologically faithful feature pyramid and bottom-up path.
 s.node('spp',375,949,160,66,'SPPCSPC\n512',fs=25)
 s.node('up40',375,842,160,68,'Conv 256\nUpsample ×2','merge',24)
 s.node('cat40_top',375,779,160,40,'Concat','merge',26)
 s.node('elan40_top',375,714,160,44,'ELAN · 256',fs=25)
 s.node('up80',375,609,160,68,'Conv 128\nUpsample ×2','merge',24)
 s.node('cat80',375,531,160,40,'Concat','merge',26)
 s.node('elan80_neck',595,531,160,44,'ELAN · 128',fs=25)
 s.node('down40_neck',595,629,160,52,'MP + Conv','merge',24)
 s.node('cat40_bottom',595,779,160,40,'Concat','merge',26)
 s.node('elan40_bottom',595,843,160,44,'ELAN · 256',fs=25)
 s.node('down20_neck',595,925,160,44,'MP + Conv','merge',24)
 s.node('cat20_bottom',595,1007,160,36,'Concat','merge',25)
 # Lower ELAN shares a compact compound block so no giant canvas is needed.
 # Revise previous positions to keep three detection scales evenly separated.
 for n in s.nodes:
  if n['id']=='cat20_bottom': n.update(y=990,h=53,label='Concat\nELAN · 512',fs=24)
 s.node('head80',830,508,200,72,'RepConv 256\nConv 1×1 · 255',fs=24)
 s.node('head40',830,802,200,72,'RepConv 512\nConv 1×1 · 255',fs=24)
 s.node('head20',830,935,200,72,'RepConv 1024\nConv 1×1 · 255',fs=24)
 s.text('out80',830,586,200,55,'80 × 80\n3 × 85',24)
 s.text('out40',830,880,200,44,'40 × 40 · 3 × 85',23)
 s.text('out20',830,1013,200,30,'20 × 20 · 3 × 85',23)
 # Main backbone chain, exact cuts appear on links, not at arbitrary ELAN positions.
 e=s.edge
 e('input_stem',[(165,94),(165,155)],'input','stem')
 e('stem_conv',[(165,225),(165,252)],'stem','conv128')
 e('conv_silu',[(165,296),(165,331)],'conv128','silu128')
 e('silu_elan',[(165,369),(165,395)],'silu128','elan160')
 e('elan_down',[(165,443),(165,469)],'elan160','down80')
 e('down_elan',[(165,532),(165,565)],'down80','elan80')
 e('elan_back40',[(165,613),(165,682)],'elan80','back40')
 e('back40_back20',[(165,762),(165,875)],'back40','back20')
 e('back20_spp',[(275,915),(332,915),(332,982),(375,982)],'back20','spp')
 # Lateral backbone routes include their 1x1 projection explicitly via edge labels.
 e('p3_to_neck',[(165,654),(332,654),(332,551),(375,551)],None,'cat80')
 e('p4_to_neck',[(165,799),(375,799)],None,'cat40_top')
 e('spp_up',[(455,949),(455,910)],'spp','up40')
 e('up40_cat',[(455,842),(455,819)],'up40','cat40_top')
 e('cat_elan40',[(455,779),(455,758)],'cat40_top','elan40_top')
 e('elan40_up80',[(455,714),(455,677)],'elan40_top','up80')
 e('up80_cat',[(455,609),(455,571)],'up80','cat80')
 e('cat80_elan',[(535,551),(595,551)],'cat80','elan80_neck')
 e('p3_head',[(755,553),(830,553)],'elan80_neck','head80')
 e('p3_down',[(675,575),(675,629)],'elan80_neck','down40_neck')
 e('down40_cat_mp',[(650,681),(650,779)],'down40_neck','cat40_bottom')
 e('down40_cat_conv',[(700,681),(700,779)],'down40_neck','cat40_bottom')
 e('top40_bottom40',[(535,736),(565,736),(565,799),(595,799)],'elan40_top','cat40_bottom')
 e('cat40_elan',[(675,819),(675,843)],'cat40_bottom','elan40_bottom')
 e('p4_head',[(755,865),(795,865),(795,838),(830,838)],'elan40_bottom','head40')
 e('p4_down',[(675,887),(675,925)],'elan40_bottom','down20_neck')
 e('down20_cat_mp',[(650,969),(650,990)],'down20_neck','cat20_bottom')
 e('down20_cat_conv',[(700,969),(700,990)],'down20_neck','cat20_bottom')
 e('spp_bottom',[(535,982),(565,982),(565,1016),(595,1016)],'spp','cat20_bottom')
 e('p5_head',[(755,1016),(795,1016),(795,971),(830,971)],'cat20_bottom','head20')
 # Cut annotations are placed in the inter-module space.
 s.line('b009_cut',[(41,314),(289,314)],P['orange'],2.8,True)
 s.text('b009_label',42,298,92,30,'b009',24,True,P['orange'])
 s.line('b044_cut',[(41,549),(289,549)],P['orange'],2.8,True)
 s.text('b044_label',42,533,92,30,'b044',24,True,P['orange'])
 s.line('b066_cut',[(39,634),(293,634)],P['blue'],3.5,True)
 s.text('b066_label',40,618,92,32,'b066',26,True,P['blue'])
 s.text('p3_label',182,651,115,27,'P3 · 80²',23,color=P['muted'])
 s.text('p4_label',178,817,115,31,'P4 · 40²',23,color=P['muted'])
 s.text('p5_label',202,959,115,31,'P5 · 20²',23,color=P['muted'])
 # Show explicit lateral projections without filling the main diagram with more boxes.
 s.text('lateral128',300,491,94,45,'Conv\n128',23,color=P['muted'])
 s.text('lateral256',285,747,94,45,'Conv\n256',23,color=P['muted'])
 # The spare upper-right area explains the selected split and defines all tensor numbers.
 s.box('split_key',350,40,702,233,'#FFFFFF',P['border'],15)
 s.text('key_title',374,55,654,34,'Split b066: ein Grenztensor' if de else 'Split b066: one boundary tensor',28,True,P['blue'],align='left')
 s.text('key_shape',374,100,654,36,'[1, 512, 80, 80]  ·  13,11 MB (FP32)' if de else '[1, 512, 80, 80]  ·  13.11 MB (FP32)',27,False,align='left')
 s.text('key_runtime',374,149,654,61,'Blauer Rahmen: Beschleunigerpräfix\nAlle nachfolgenden Module: GPU-Suffix' if de else 'Blue frame: accelerator prefix\nAll subsequent modules: GPU suffix',24,False,align='left')
 s.text('key_cuts',374,218,654,33,'b009 und b044: alternative Schnitte' if de else 'b009 and b044: alternative cuts',24,False,P['muted'],align='left')
 s.text('bottom_note',10,1052,1040,34,'COCO: 3 Anker × (4 Boxwerte + 1 Objektscore + 80 Klassen)' if de else 'COCO: 3 anchors × (4 box values + 1 objectness + 80 classes)',24,color=P['muted'])
 return s

def render(s,out):
 svg=E.Element('svg',{'xmlns':'http://www.w3.org/2000/svg','width':str(W),'height':str(H),'viewBox':f'0 0 {W} {H}'})
 defs=E.SubElement(svg,'defs')
 mark=E.SubElement(defs,'marker',{'id':'arrow','viewBox':'0 0 10 10','refX':'8','refY':'5','markerWidth':'7','markerHeight':'7','orient':'auto-start-reverse'})
 E.SubElement(mark,'path',{'d':'M 0 0 L 10 5 L 0 10 z','fill':P['edge']})
 E.SubElement(svg,'rect',{'width':str(W),'height':str(H),'fill':'white'})
 mx=E.Element('mxfile',{'host':'app.diagrams.net','version':'24.7.17','type':'device'})
 diag=E.SubElement(mx,'diagram',{'name':'YOLOv7 — Splits','id':f'yolov7-splits-{s.lang}'})
 model=E.SubElement(diag,'mxGraphModel',{'dx':str(W),'dy':str(H),'grid':'1','gridSize':'10','guides':'1','tooltips':'1','connect':'1','arrows':'1','fold':'1','page':'1','pageScale':'1','pageWidth':str(W),'pageHeight':str(H),'math':'0','shadow':'0'})
 root=E.SubElement(model,'root');E.SubElement(root,'mxCell',{'id':'0'});E.SubElement(root,'mxCell',{'id':'1','parent':'0'})
 def cell(id,value,style,x,y,w,h):
  c=E.SubElement(root,'mxCell',{'id':id,'value':value,'style':style,'vertex':'1','parent':'1'})
  E.SubElement(c,'mxGeometry',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'as':'geometry'})
 def svtext(o):
  lines=o['label'].split('\n');lineh=o['fs']*1.17; yy=o['y']+(o['h']-(len(lines)-1)*lineh)/2+0.34*o['fs']
  left=o.get('align')=='left';xx=o['x'] if left else o['x']+o['w']/2
  t=E.SubElement(svg,'text',{'x':str(xx),'y':str(yy),'font-family':'Arial, Nimbus Sans, sans-serif','font-size':str(o['fs']),'font-weight':'bold' if o.get('bold') else 'normal','fill':o.get('color',P['text']),'text-anchor':'start' if left else 'middle'})
  for i,l in enumerate(lines):E.SubElement(t,'tspan',{'x':str(xx),'dy':'0' if i==0 else str(lineh)}).text=l
 for b in s.boxes:
  a={'x':str(b['x']),'y':str(b['y']),'width':str(b['w']),'height':str(b['h']),'rx':str(b['rx']),'fill':b['fill'],'stroke':b['stroke'],'stroke-width':str(b['sw'])}
  if b['dash']:a['stroke-dasharray']='7 5'
  E.SubElement(svg,'rect',a)
  cell(b['id'],'',f"rounded=1;absoluteArcSize=1;arcSize={b['rx']*2};fillColor={b['fill']};strokeColor={b['stroke']};strokeWidth={b['sw']};",b['x'],b['y'],b['w'],b['h'])
 for e in s.edges:
  E.SubElement(svg,'polyline',{'points':' '.join(f'{x},{y}' for x,y in e['points']),'fill':'none','stroke':e['color'],'stroke-width':str(e['sw']),'stroke-linejoin':'round',**({'marker-end':'url(#arrow)'} if e['arrow'] else {})})
  style=f"edgeStyle=none;rounded=0;html=0;strokeColor={e['color']};strokeWidth={e['sw']};endArrow={'block' if e['arrow'] else 'none'};endFill=1;endSize=7;"
  attrs={'id':e['id'],'edge':'1','parent':'1','value':''}
  for key,ix in [('src',0),('dst',-1)]:
   if e[key]:
    n=s.lookup(e[key]);pt=e['points'][ix];attrs['source' if key=='src' else 'target']=e[key]
    pre='exit' if key=='src' else 'entry';style+=f"{pre}X={(pt[0]-n['x'])/n['w']};{pre}Y={(pt[1]-n['y'])/n['h']};{pre}Dx=0;{pre}Dy=0;{pre}Perimeter=0;"
  attrs['style']=style;c=E.SubElement(root,'mxCell',attrs);g=E.SubElement(c,'mxGeometry',{'relative':'1','as':'geometry'})
  E.SubElement(g,'mxPoint',{'x':str(e['points'][0][0]),'y':str(e['points'][0][1]),'as':'sourcePoint'});E.SubElement(g,'mxPoint',{'x':str(e['points'][-1][0]),'y':str(e['points'][-1][1]),'as':'targetPoint'})
  a=E.SubElement(g,'Array',{'as':'points'})
  for x,y in e['points'][1:-1]:E.SubElement(a,'mxPoint',{'x':str(x),'y':str(y)})
 for n in s.nodes:
  E.SubElement(svg,'rect',{'x':str(n['x']),'y':str(n['y']),'width':str(n['w']),'height':str(n['h']),'rx':'9','fill':n['fill'],'stroke':n['stroke'],'stroke-width':'1.6'})
  svtext(n)
  cell(n['id'],n['label'],f"rounded=1;absoluteArcSize=1;arcSize=18;whiteSpace=wrap;html=0;fillColor={n['fill']};strokeColor={n['stroke']};strokeWidth=1.6;fontColor={P['text']};fontFamily=Arial;fontSize={n['fs']};align=center;verticalAlign=middle;spacing=0;",n['x'],n['y'],n['w'],n['h'])
 for l in s.lines:
  E.SubElement(svg,'polyline',{'points':' '.join(f'{x},{y}' for x,y in l['points']),'fill':'none','stroke':l['color'],'stroke-width':str(l['sw']),**({'stroke-dasharray':'8 6'} if l['dash'] else {})})
  c=E.SubElement(root,'mxCell',{'id':l['id'],'edge':'1','parent':'1','style':f"edgeStyle=none;endArrow=none;strokeColor={l['color']};strokeWidth={l['sw']};dashed={1 if l['dash'] else 0};dashPattern=3 2;"})
  g=E.SubElement(c,'mxGeometry',{'relative':'1','as':'geometry'})
  E.SubElement(g,'mxPoint',{'x':str(l['points'][0][0]),'y':str(l['points'][0][1]),'as':'sourcePoint'});E.SubElement(g,'mxPoint',{'x':str(l['points'][-1][0]),'y':str(l['points'][-1][1]),'as':'targetPoint'})
 for t in s.texts:
  if t['id'] in ('b009_label','b044_label','b066_label'):
   E.SubElement(svg,'rect',{'x':str(t['x']),'y':str(t['y']),'width':str(t['w']),'height':str(t['h']),'fill':'#F4F9FF' if t['id']!='b066_label' else P['container']})
  svtext(t)
  cell(t['id'],t['label'],f"text;html=0;whiteSpace=wrap;fillColor={'#F4F9FF' if t['id'] in ('b009_label','b044_label','b066_label') else 'none'};strokeColor=none;fontColor={t['color']};fontFamily=Arial;fontSize={t['fs']};fontStyle={1 if t['bold'] else 0};align={t['align']};verticalAlign=middle;spacing=0;",t['x'],t['y'],t['w'],t['h'])
 E.indent(svg);E.indent(mx)
 out.parent.mkdir(parents=True,exist_ok=True)
 E.ElementTree(svg).write(str(out)+'.svg',encoding='utf-8',xml_declaration=True)
 E.ElementTree(mx).write(str(out)+'.drawio',encoding='utf-8',xml_declaration=True)
 subprocess.run(['inkscape',str(out)+'.svg','--export-type=pdf',f'--export-filename={out}.pdf'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 subprocess.run(['inkscape',str(out)+'.svg','--export-type=png','--export-width=1272',f'--export-filename={out}.png'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
for lang in ('de','en'):
 render(build(lang),BASE/f'yolov7_architecture_splits_{lang}')
print(BASE)
