#!/usr/bin/env python3
"""Regenerate historical English redesign drafts; external original images are required."""
import argparse
from pathlib import Path
import math, textwrap, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle, FancyArrowPatch, Polygon
from matplotlib.lines import Line2D
from matplotlib.ticker import LogLocator, LogFormatterMathtext
import pandas as pd
from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[4]
SOURCE = None  # Set only from the explicitly supplied external --source-dir.
OUT = ROOT/'local-output'/'dissertation-v56-legacy'/'redesigned'/'figures'
PHOTO = ROOT/'local-output'/'dissertation-v56-legacy'/'redesigned'/'photos'

C = {
    'ink':'#27313D','muted':'#697386','line':'#364152','white':'#FFFFFF',
    'panel':'#F5F7FA','panel2':'#E9EEF4','grid':'#D8DEE6',
    'blue':'#2F5D8C','blue2':'#5B8DB8','blue_light':'#D9EAF7',
    'teal':'#2E7D6E','teal_light':'#DFF2EE',
    'green':'#3C7D40','green_light':'#E3F2E2',
    'orange':'#C7791D','orange_light':'#F8E5C7',
    'red':'#9B3A37','red_light':'#F2DBDA',
    'purple':'#6B5CA5','purple_light':'#E6E2F3',
    'yellow':'#C99A2E','yellow_light':'#F7EBC8',
    'gray':'#E7EBEF','gray2':'#D1D8E0'
}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.labelsize':8,'axes.titlesize':10,'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'pdf.fonttype':42,'ps.fonttype':42})

def canvas(w=7.0,h=3.3):
    fig,ax=plt.subplots(figsize=(w,h)); fig.patch.set_facecolor('white'); ax.set_xlim(0,w); ax.set_ylim(0,h); ax.axis('off'); return fig,ax

def save(fig,name):
    fig.savefig(OUT/name,bbox_inches='tight',pad_inches=0.035); plt.close(fig)

def wrap(s,w=18):
    return '\n'.join(textwrap.wrap(s,width=w,break_long_words=False,break_on_hyphens=False))

def label(ax,x,y,t,fs=8,weight='normal',color='ink',ha='center',va='center',w=None,rot=0):
    if w: t=wrap(t,w)
    ax.text(x,y,t,ha=ha,va=va,fontsize=fs,fontweight=weight,color=C[color],linespacing=1.12,rotation=rot)

def box(ax,x,y,w,h,t,fc='panel',ec='line',fs=7,weight='normal',lw=.9,r=.08,color='ink'):
    p=FancyBboxPatch((x,y),w,h,boxstyle=f'round,pad=0.025,rounding_size={r}',fc=C[fc],ec=C[ec],lw=lw)
    ax.add_patch(p); label(ax,x+w/2,y+h/2,t,fs=fs,weight=weight,color=color); return p

def arrow(ax,x1,y1,x2,y2,color='line',lw=.95,ms=8,dashed=False,rad=0):
    a=FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=ms,lw=lw,color=C[color],linestyle='--' if dashed else '-',connectionstyle=f'arc3,rad={rad}')
    ax.add_patch(a); return a

def line(ax,x1,y1,x2,y2,color='line',lw=.95,dashed=False):
    ax.plot([x1,x2],[y1,y2],color=C[color],lw=lw,ls='--' if dashed else '-')

def pill(ax,x,y,w,h,t,fc='panel2',ec='white',fs=6.3):
    return box(ax,x,y,w,h,t,fc=fc,ec=ec,fs=fs,lw=.5,r=h/2)

def axes_style(ax,grid=True):
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(C['line']); ax.spines['bottom'].set_color(C['line'])
    ax.tick_params(colors=C['ink'],width=.7)
    if grid:
        ax.grid(True,which='major',color=C['grid'],lw=.55,alpha=.95)
        ax.grid(True,which='minor',color='#EEF1F4',lw=.4,alpha=.8)
        ax.set_axisbelow(True)

def generic_flow(name,title,items,links=None,notes=None,w=7,h=3.0):
    fig,ax=canvas(w,h); label(ax,.05,h-.20,title,fs=10,weight='bold',ha='left')
    for it in items:
        x,y,ww,hh,t,fc,ec=it[:7]; wt=it[7] if len(it)>7 else 'normal'; fs=it[8] if len(it)>8 else 6.8
        box(ax,x,y,ww,hh,t,fc=fc,ec=ec,fs=fs,weight=wt)
    if links:
        for l in links:
            arrow(ax,*l[:4],color=l[4] if len(l)>4 else 'line',dashed=(len(l)>5 and l[5]),rad=(l[6] if len(l)>6 else 0))
    if notes:
        for n in notes:
            label(ax,*n[:3],fs=n[3] if len(n)>3 else 6.5,color=n[4] if len(n)>4 else 'muted',ha=n[5] if len(n)>5 else 'center')
    save(fig,name)

# --- conceptual figures ---
def related_work_settings():
    fig,ax=canvas(7,3.0); label(ax,.05,2.83,'Deployment settings normalised for split inference',fs=10,weight='bold',ha='left')
    panels=[(.15,.35,2.1,2.15,'CE','Device to edge/cloud','network variability\ncommunication energy','blue'),(2.45,.35,2.1,2.15,'EC','Edge cluster','stage balance\nqueueing/scheduling','teal'),(4.75,.35,2.1,2.15,'IN','Intra-node','toolchain mismatch\nDMA/copies/layout','purple')]
    for x,y,w,h,tag,title,note,col in panels:
        box(ax,x,y,w,h,'',fc='white',ec='gray2',r=.11)
        label(ax,x+.13,y+h-.23,tag,fs=8.5,weight='bold',color=col,ha='left'); label(ax,x+.58,y+h-.23,title,fs=7.2,weight='bold',ha='left')
        pill(ax,x+.18,y+.12,w-.36,.34,note,fc=col+'_light' if col!='blue' else 'blue_light',fs=6.4)
    box(ax,.38,1.38,.58,.42,'Device',fc='blue_light',ec='blue',fs=6.5); box(ax,1.45,1.38,.58,.42,'Cloud',fc='orange_light',ec='orange',fs=6.5); arrow(ax,.98,1.59,1.43,1.59,'blue'); label(ax,1.20,1.84,'WAN / LTE',fs=6.1,color='muted')
    for i,x in enumerate([2.75,3.45,4.15]): box(ax,x,1.30,.50,.52,f'Edge\n{i+1}',fc='teal_light',ec='teal',fs=6.0)
    line(ax,3.25,1.56,3.45,1.56,'teal'); line(ax,3.95,1.56,4.15,1.56,'teal')
    box(ax,5.02,1.02,1.55,.95,'',fc='panel',ec='gray2',fs=6,color='muted')
    label(ax,5.10,1.87,'microserver',fs=6,weight='bold',color='muted',ha='left')
    box(ax,5.10,1.30,.58,.42,'GPU\nSoC',fc='green_light',ec='green',fs=6); box(ax,5.94,1.30,.58,.42,'ASIC\nNPU',fc='purple_light',ec='purple',fs=6); arrow(ax,5.70,1.51,5.92,1.51,'purple'); label(ax,5.81,1.15,'PCIe/DMA',fs=6.1,color='muted')
    save(fig,'related_work_settings_taxonomy.pdf')

def genai_stack():
    generic_flow('genai_stack_comparison.pdf','Static ONNX split versus decoder-runtime deployment',
        [(0.2,2.05,.75,.43,'ONNX\nmodel','blue_light','blue'),(1.15,2.05,.80,.43,'split\nanalysis','blue_light','blue'),(2.12,2.05,.85,.43,'subgraph\nartefacts','blue_light','blue'),(.55,1.18,.95,.45,'compiler A\nTensorRT','panel','gray2'),(2.00,1.18,.95,.45,'compiler B\nNPU','panel','gray2'),(1.18,.38,1.15,.45,'host scheduler\ntransfer tensor','yellow_light','yellow','bold'),
         (3.75,2.05,.75,.43,'tokens +\nweights','orange_light','orange'),(4.68,2.05,.75,.43,'prefill','orange_light','orange'),(5.55,2.05,.75,.43,'decode\nloop','orange_light','orange'),(6.05,1.18,.75,.43,'backend\nkernels','panel','gray2'),(4.45,1.18,.82,.43,'KV cache\nstate','purple_light','purple'),(5.25,.38,1.20,.43,'runtime support\nbecomes central','red_light','red','bold')],
        [(0.95,2.26,1.15,2.26,'blue'),(1.95,2.26,2.12,2.26,'blue'),(1.50,2.05,1.05,1.63,'blue'),(2.55,2.05,2.48,1.63,'purple'),(1.02,1.18,1.55,.83,'yellow'),(2.48,1.18,1.95,.83,'yellow'),(4.50,2.26,4.68,2.26,'orange'),(5.43,2.26,5.55,2.26,'orange'),(5.93,2.05,6.22,1.61,'orange'),(5.93,2.05,4.87,1.61,'purple'),(4.87,1.18,5.85,2.05,'purple',True)],
        [(0.2,.12,'explicit tensor handover once per inference',6.2,'muted','left'),(3.75,.12,'stateful loop, KV cache and sampling shape deployability',6.2,'muted','left')])

def recs_family():
    fig,ax=canvas(7,3.6); label(ax,.05,3.42,'RECS family overview: edge-to-cloud form factors',fs=10,weight='bold',ha='left')
    stages=[(.12,2.05,1.55,'Far edge','u.RECS / t.RECS','custom board, <30 W','Jetson + M.2 NPU','green'),(1.85,2.05,1.55,'Near edge','compact RECS','1 RU, <500 W','few microservers','blue'),(3.58,2.05,1.55,'Edge cluster','RECS|Box Durin','2 RU, 500 W-2 kW','up to 48 nodes','orange'),(5.31,2.05,1.55,'Cloud','RECS|Box Deneb','3 RU, >2 kW','up to 144 nodes','purple')]
    for x,y,w,t,name,powr,nodes,col in stages:
        box(ax,x,y,w,1.05,'',fc=col+'_light' if col!='blue' else 'blue_light',ec=col,r=.12)
        label(ax,x+.12,y+.82,t,fs=7.3,weight='bold',color=col,ha='left'); label(ax,x+w/2,y+.55,name,fs=7.2,weight='bold'); label(ax,x+w/2,y+.30,powr,fs=6.1,color='muted'); label(ax,x+w/2,y+.13,nodes,fs=6.1,color='muted')
    for x in [1.67,3.40,5.13]: arrow(ax,x,2.57,x+.16,2.57,'muted')
    label(ax,.12,1.52,'Representative module ecosystem',fs=8,weight='bold',ha='left')
    mods=['GPU\nSoC','ML\nASIC','SMARC\nCPU','FPGA\nSoC','COM-HPC\nXeon','M.2\nNPU','ARM\nserver','x86\nserver','RISC\nAI']
    for i,m in enumerate(mods): box(ax,.25+i*.73,1.02,.57,.42,m,fc='panel2' if i%2 else 'panel',ec='gray2',fs=5.8)
    box(ax,.15,.25,6.65,.48,'site count decreases while power, footprint and integration scale increase',fc='white',ec='gray2',fs=6.4)
    save(fig,'recs_family_redesigned.pdf')

def urecs_architecture():
    generic_flow('urecs_architecture_redesigned.pdf','u.RECS architecture: compute slots, interconnect, management and I/O',
        [(.45,2.15,1.25,.62,'Jetson Orin NX\nGPU SoC','green_light','green','bold'),(2.65,2.15,1.25,.62,'SMARC 2.1\nSoM slot','blue_light','blue','bold'),(1.55,1.08,1.25,.62,'M.2 M-Key\nAI accelerator','purple_light','purple','bold'),(1.72,1.82,1.00,.42,'COM-Brick\nPCIe routing','orange_light','orange','bold'),(5.05,2.25,1.15,.58,'ESP32 BMC\npower + monitor','yellow_light','yellow','bold'),(5.05,1.42,1.15,.50,'Ethernet\nswitch','teal_light','teal'),(4.55,.65,.85,.42,'RJ-45 /\nPoE','panel','gray2'),(5.60,.65,.85,.42,'SpE /\nLoRa','panel','gray2'),(4.15,2.88,2.10,.30,'USB-C / barrel -> rails + ADC sensing','red_light','red','normal',5.5)],
        [(1.70,2.45,1.75,2.24,'orange'),(2.65,2.45,2.62,2.24,'orange'),(2.22,1.82,2.17,1.70,'orange'),(5.63,2.25,5.63,1.92,'yellow'),(5.63,1.42,5.05,1.07,'teal'),(5.63,1.42,6.03,1.07,'teal'),(1.05,2.15,.88,.98,'muted',True),(3.28,2.15,3.75,.98,'muted',True),(5.20,2.88,5.45,2.83,'red')], w=7,h=3.55)

def urecs_power():
    fig,ax=canvas(7,3.45); label(ax,.05,3.25,'u.RECS power tree and measurement points',fs=10,weight='bold',ha='left')
    box(ax,.15,2.42,.85,.50,'USB-C\nPD',fc='green_light',ec='green',fs=7); box(ax,.15,1.72,.85,.50,'barrel\njack',fc='green_light',ec='green',fs=7); box(ax,1.30,2.07,.90,.50,'20 V\ninput',fc='orange_light',ec='orange',fs=7,weight='bold')
    arrow(ax,1.00,2.67,1.30,2.36,'green'); arrow(ax,1.00,1.97,1.30,2.18,'green')
    rails=[('54 V','PoE output','30 W',2.80,'red'),('5 V','Jetson + SMARC','45 W',2.25,'blue'),('3.3 V','M.2 + BMC','20 W',1.70,'purple'),('aux','switch / PHY / fan','logic rails',1.15,'teal')]
    for r,cons,p,y,col in rails:
        box(ax,3.00,y,.78,.35,r,fc=col+'_light' if col!='blue' else 'blue_light',ec=col,fs=6.9,weight='bold')
        box(ax,4.10,y,1.25,.35,cons,fc='white',ec=col,fs=6.2); pill(ax,5.65,y+.03,.78,.27,p,fs=5.8)
        arrow(ax,2.20,2.32,3.00,y+.17,'orange')
    box(ax,2.25,.45,2.35,.42,'load switches + ADC current sense',fc='yellow_light',ec='yellow',fs=6.8,weight='bold')
    arrow(ax,3.42,.87,3.42,1.15,'yellow'); label(ax,4.75,.58,'BMC switches rails and exports\ncalibrated telemetry',fs=6.1,color='muted',ha='left')
    save(fig,'urecs_power_redesigned.pdf')

def com_brick():
    fig,ax=canvas(6.2,2.8); label(ax,.05,2.60,'COM-Brick: replaceable passive PCIe routing',fs=10,weight='bold',ha='left')
    box(ax,.35,1.45,1.1,.50,'Jetson\nOrin NX',fc='green_light',ec='green',fs=6.8,weight='bold'); box(ax,4.75,1.45,1.1,.50,'SMARC\nmodule',fc='blue_light',ec='blue',fs=6.8,weight='bold'); box(ax,2.55,.45,1.1,.50,'M.2\naccelerator',fc='purple_light',ec='purple',fs=6.8,weight='bold')
    line(ax,1.45,1.70,4.75,1.70,'gray2'); line(ax,1.15,1.45,2.90,.95,'gray2'); line(ax,5.15,1.45,3.25,.95,'gray2')
    box(ax,2.35,1.48,1.35,.40,'COM1 Jetson-SMARC',fc='orange_light',ec='orange',fs=6.2); box(ax,1.50,.95,1.22,.38,'COM2 Jetson-M.2',fc='yellow_light',ec='yellow',fs=6.0); box(ax,3.42,.95,1.22,.38,'COM3 SMARC-M.2',fc='red_light',ec='red',fs=6.0)
    box(ax,.55,.08,5.15,.27,'No active PCIe switch: topology is selected mechanically by the mezzanine card.',fc='panel',ec='gray2',fs=6.1)
    save(fig,'com_brick_redesigned.pdf')

def toolchain_bridge():
    generic_flow('toolchain_bridge_redesigned.pdf','Toolchain bridge for GPU+ASIC partitioned inference',
      [(.30,2.35,1.15,.48,'Logical\nONNX DAG','blue_light','blue','bold'),(1.82,2.35,1.15,.48,'partition +\ngraph surgery','orange_light','orange','bold'),(.50,1.30,1.25,.50,'TensorRT / CUDA\nGPU toolchain','green_light','green'),(.50,.55,1.25,.45,'engine\nartefact','panel','gray2'),(4.95,1.30,1.35,.50,'NPU compiler\n+ calibration','purple_light','purple'),(4.95,.55,1.35,.45,'HEF / contexts\nartefact','panel','gray2'),(2.55,.95,1.75,.62,'runtime orchestrator\nqueues, sync, logging','yellow_light','yellow','bold'),(2.05,.16,2.95,.30,'boundary tensor: PCIe/DMA + layout/(de-)quantisation','red_light','red','bold',6.0)],
      [(1.45,2.60,1.82,2.60,'blue'),(2.38,2.35,1.10,1.80,'green'),(2.97,2.35,5.60,1.80,'purple'),(1.12,1.30,1.12,1.00,'green'),(5.62,1.30,5.62,1.00,'purple'),(1.75,.78,2.55,1.20,'yellow'),(4.95,.78,4.30,1.20,'yellow')],w=7,h=3.2)

def management():
    generic_flow('management_overview_redesigned.pdf','u.RECS management and monitoring fabric',
      [(2.65,1.45,1.10,.60,'ESP32\nBMC','yellow_light','yellow','bold'),(.45,2.20,1.08,.42,'IO expanders\nrail enables','panel','gray2'),(.45,1.45,1.08,.42,'ADC\ncurrent sense','panel','gray2'),(.45,.70,1.08,.42,'fan + temp\ncontrollers','panel','gray2'),(5.00,2.20,1.05,.42,'Ethernet\nswitch','teal_light','teal'),(5.00,1.45,1.05,.42,'Wi-Fi / LoRa\nremote mgmt','panel','gray2'),(5.00,.70,1.05,.42,'UART / USB\ndebug','panel','gray2'),(2.05,.20,2.35,.35,'manage and measure even when compute modules are off','panel2','gray2')],
      [(1.53,2.41,2.65,1.82,'blue'),(1.53,1.66,2.65,1.75,'purple'),(1.53,.91,2.65,1.60,'yellow'),(3.75,1.82,5.00,2.41,'teal'),(3.75,1.75,5.00,1.66,'muted'),(3.75,1.60,5.00,.91,'muted')],w=6.4,h=3.1)

def photo_cleaning():
    # clean u.RECS photo
    src=SOURCE/'urecs_real_front.png'; im=Image.open(src).convert('RGB'); gray=im.convert('L'); mask=gray.point(lambda p:255 if p>8 else 0); bbox=mask.getbbox(); im=im.crop(bbox) if bbox else im
    im=ImageEnhance.Contrast(im).enhance(1.08); im=ImageEnhance.Sharpness(im).enhance(1.08); im=ImageOps.expand(im,border=25,fill='white'); im.save(PHOTO/'urecs_real_front_clean.png',quality=95)
    # PCB photos with cleaner blue badges over existing red labels
    positions={'recs_pcb_front.png':{1:(295,2780),2:(2600,2760),3:(1460,2550),5:(220,1600),7:(1165,360),8:(2775,1580),9:(2500,1215),10:(1425,1000),11:(1840,980),12:(420,900)},'recs_pcb_back.png':{4:(2300,2050),9:(520,1280)}}
    try: font=ImageFont.truetype('DejaVuSans-Bold.ttf',42)
    except Exception: font=ImageFont.load_default()
    for fn,pos in positions.items():
        im=Image.open(SOURCE/fn).convert('RGB'); gray=im.convert('L'); mask=gray.point(lambda p:255 if p>8 else 0); bbox=mask.getbbox(); im=im.crop(bbox) if bbox else im; bx,by=(bbox[0],bbox[1]) if bbox else (0,0)
        maxw=1700; scale=maxw/im.width; im=im.resize((maxw,int(im.height*scale)),Image.LANCZOS); draw=ImageDraw.Draw(im,'RGBA')
        for n,(x,y) in pos.items():
            xx=int((x-bx)*scale); yy=int((y-by)*scale); r=36
            draw.rounded_rectangle((xx-r-7,yy-r-7,xx+r+7,yy+r+7),radius=12,fill=(255,255,255,205))
            draw.ellipse((xx-r,yy-r,xx+r,yy+r),fill=(47,93,140,248),outline=(255,255,255,255),width=4)
            txt=str(n); tw=draw.textlength(txt,font=font); draw.text((xx-tw/2,yy-30),txt,font=font,fill=(255,255,255,255))
        im=ImageOps.expand(im,border=20,fill='white'); im.save(PHOTO/fn.replace('.png','_clean.png'),quality=95)

def energy_scopes():
    fig,ax=canvas(6.5,2.5); box(ax,.25,.25,6.0,1.90,'',fc='panel',ec='blue',r=.12,lw=1.1); label(ax,.55,1.95,'Full system (FS)',fs=8.2,weight='bold',color='blue',ha='left')
    box(ax,1.15,.58,4.15,1.20,'',fc='blue_light',ec='teal',r=.10); label(ax,1.40,1.58,'Module / board-level (MB)',fs=7.8,weight='bold',color='teal',ha='left')
    box(ax,2.05,.88,2.35,.55,'Accelerator-only (AO)',fc='purple_light',ec='purple',fs=7.8,weight='bold')
    label(ax,.55,.43,'host CPU + DRAM + storage + interconnect + accelerators',fs=6.2,color='muted',ha='left'); label(ax,4.55,1.95,'primary scope for\nfinal thesis claims',fs=6.6,weight='bold',color='blue',ha='left')
    save(fig,'energy_scopes_redesigned.pdf')

def ground_truth():
    generic_flow('ground_truth_setup_redesigned.pdf','Reference energy measurement chain',
      [(.20,1.55,.95,.45,'measured rail\nFS/MB','blue_light','blue','bold'),(1.50,1.55,.95,.45,'shunt /\nsense','panel','gray2'),(2.80,1.55,.95,.45,'diff. probe\n/ amp.','panel','gray2'),(4.10,1.55,.95,.45,'high-rate\nlogger','panel','gray2'),(5.40,1.55,1.00,.45,'trace analysis\nP(t), E','blue_light','blue','bold'),(1.80,.55,1.25,.42,'runtime\ntimestamps','green_light','green'),(3.55,.55,1.25,.42,'GPIO/log\nmarker','orange_light','orange'),(5.10,.36,1.25,.30,'explicit windows only','panel2','gray2')],
      [(1.15,1.77,1.50,1.77,'blue'),(2.45,1.77,2.80,1.77,'blue'),(3.75,1.77,4.10,1.77,'blue'),(5.05,1.77,5.40,1.77,'blue'),(3.05,.76,3.55,.76,'green'),(4.18,.97,4.55,1.55,'orange',True),(2.45,.97,5.85,1.55,'green',True,.18)],w=7,h=2.7)

def time_alignment():
    fig,ax=canvas(7,2.6); label(ax,.05,2.42,'Time alignment and phase segmentation',fs=10,weight='bold',ha='left')
    arrow(ax,.55,.42,6.55,.42,'line'); label(ax,6.70,.42,'time',fs=6.5,color='muted',ha='left')
    phases=[(.85,1.75,'warm-up\nexcluded','red_light'),(1.75,5.35,'steady-state\nreported','green_light'),(5.35,6.20,'flush\nexcluded','panel2')]
    for x0,x1,t,fc in phases:
        ax.add_patch(Rectangle((x0,.20),x1-x0,.30,fc=C[fc],ec='none')); label(ax,(x0+x1)/2,.09,t,fs=5.8,color='muted'); line(ax,x0,.33,x0,2.15,'gray2',dashed=True)
    line(ax,6.20,.33,6.20,2.15,'gray2',dashed=True)
    xs=[.55,.8,1.05,1.32,1.65,2.0,2.35,2.72,3.12,3.56,4.0,4.40,4.85,5.20,5.55,5.9,6.25]
    ys=[1.35,2.0,1.38,1.65,1.30,2.05,1.55,2.0,1.47,2.1,1.58,2.0,1.65,1.92,1.70,1.35,1.20]
    ax.plot(xs,ys,color=C['blue'],lw=1.5); label(ax,.62,2.18,'reference P(t)',fs=6.3,color='blue',ha='left')
    tx=[.9,1.5,2.1,2.7,3.3,3.9,4.5,5.1,5.7,6.1]; ty=[.94+0.04*math.sin(i) for i in range(len(tx))]; ax.plot(tx,ty,'o:',ms=3,color=C['orange'],lw=.8); label(ax,.62,.98,'telemetry samples',fs=6.3,color='orange',ha='left')
    arrow(ax,3.15,2.16,3.15,1.72,'orange'); label(ax,3.22,2.02,'marker',fs=6.0,color='muted',ha='left')
    save(fig,'time_alignment_redesigned.pdf')

def urecs_window():
    items=[]; steps=['deploy\nsuite','warm\nengines','duration\nprobe','u.RECS collector\nfast-firmware','power\ncalculations','row energy\nmerge']; x=.20
    for i,t in enumerate(steps): items.append((x,1.45,.95,.45,t,'blue_light' if i==3 else 'green_light' if i==5 else 'panel','blue' if i==3 else 'green' if i==5 else 'gray2','bold' if i in [3,5] else 'normal',6.2)); x+=1.10
    items += [(2.88,.55,1.15,.42,'remote command\ncase+variant+phase','orange_light','orange'),(.55,.15,5.90,.28,'engine build, deployment and report packaging remain outside the measured window','panel2','gray2','normal',6.0)]
    links=[(items[i][0]+.95,1.68,items[i+1][0],1.68,'blue' if i==2 else 'muted') for i in range(5)] + [(3.45,.97,3.70,1.45,'orange'),(3.45,.55,5.70,1.45,'orange',True,-.18)]
    generic_flow('urecs_command_window_redesigned.pdf','u.RECS command-window integration for benchmark rows',items,links,w=7,h=2.65)

def edge_pipeline():
    stages=[('sensor\nI/O','panel','gray2'),('pre-process\ndecode/resize','blue_light','blue'),('DNN\ninference','purple_light','purple'),('post-process\nNMS/tracking','orange_light','orange'),('application\noutput','panel','gray2')]
    items=[]; links=[]; x=.25
    for i,(t,fc,ec) in enumerate(stages):
        items.append((x,1.30,1.05,.52,t,fc,ec,'bold' if i==2 else 'normal',6.6));
        if i: links.append((x-.22,1.56,x,1.56,'muted'))
        x+=1.32
    notes=[(1.35,.72,'CPU/GPU flexible kernels',6.1,'blue'),(3.90,.72,'NPU/GPU/FPGA regular compute',6.1,'purple'),(5.15,.72,'CPU/GPU irregular ops',6.1,'orange')]
    generic_flow('edge_pipeline_redesigned.pdf','Edge inference is embedded in a larger system pipeline',items,links,notes,w=7,h=2.55)

def accelerator_tradeoff():
    fig,ax=plt.subplots(figsize=(6.2,3.0)); fig.patch.set_facecolor('white'); ax.set_xlim(0,10); ax.set_ylim(0,10); ax.set_xticks([]); ax.set_yticks([]); ax.spines[['top','right']].set_visible(False); ax.spines[['left','bottom']].set_color(C['line']); ax.set_xlabel('programmability / flexibility'); ax.set_ylabel('energy efficiency / specialisation')
    ax.plot([1.6,8.7],[1.9,8.4],ls='--',lw=1.0,color=C['muted'])
    pts=[('CPU',2,2,'panel2','gray2'),('GPU',4.2,4.1,'blue_light','blue'),('FPGA',6.2,6.3,'orange_light','orange'),('ASIC / NPU',8.3,8.1,'purple_light','purple')]
    for t,x,y,fc,ec in pts:
        p=FancyBboxPatch((x-.72,y-.35),1.44,.70,boxstyle='round,pad=.03,rounding_size=.12',fc=C[fc],ec=C[ec],lw=1); ax.add_patch(p); ax.text(x,y,t,ha='center',va='center',fontsize=8,fontweight='bold',color=C['ink'])
    ax.text(6.5,1.35,'heterogeneous edge nodes combine\nmultiple points on the curve',ha='center',fontsize=7,color=C['muted'])
    save(fig,'accelerator_tradeoff_redesigned.pdf')

def accelerator_paradigms():
    fig,ax=canvas(7,3.15); label(ax,.05,2.95,'Simplified edge-accelerator paradigms',fs=10,weight='bold',ha='left')
    panels=[(.20,.55,2.0,'GPU SoC\nshared memory','CPU','GPU / tensor cores','shared DRAM','green'),(2.50,.55,2.0,'Dataflow NPU\ncoprocessor','host CPU','NPU fabric','on-chip SRAM','purple'),(4.80,.55,2.0,'Systolic TPU\ncoprocessor','host CPU','systolic array','on-chip SRAM','orange')]
    for x,y,w,t,a,b,c,col in panels:
        box(ax,x,y,w,2.05,'',fc='white',ec='gray2',r=.12); label(ax,x+.12,y+1.84,t,fs=7.3,weight='bold',color=col,ha='left')
        box(ax,x+.15,y+1.15,.70,.42,a,fc='panel',ec='gray2',fs=6.0); box(ax,x+1.08,y+1.15,.75,.42,b,fc=col+'_light' if col!='blue' else 'blue_light',ec=col,fs=6.0); box(ax,x+.42,y+.42,1.16,.38,c,fc='panel2',ec='gray2',fs=6.0); arrow(ax,x+.85,y+1.36,x+1.08,y+1.36,col); arrow(ax,x+1.45,y+1.15,x+1.08,y+.80,col)
    save(fig,'accelerator_paradigms_redesigned.pdf')

def jetson_hailo():
    generic_flow('jetson_hailo_schematic_redesigned.pdf','Integrated GPU SoC versus PCIe-attached dataflow NPU',
      [(.35,.55,2.45,2.15,'','green_light','green'),(.55,2.45,1.20,.30,'Jetson-class SoC','green_light','green','bold'),(.65,1.80,.75,.42,'Arm\nCPU','white','gray2'),(1.65,1.80,.85,.42,'GPU /\nDLA','white','gray2'),(.85,.95,1.35,.42,'shared DRAM','panel','gray2'),(4.15,.55,2.45,2.15,'','purple_light','purple'),(4.35,2.45,1.40,.30,'Hailo-8 coprocessor','purple_light','purple','bold'),(4.40,1.80,.80,.42,'host\nCPU','white','gray2'),(5.55,1.80,.80,.42,'NPU\nfabric','white','gray2'),(5.45,.95,1.05,.42,'on-chip\nbuffers','panel','gray2'),(2.98,1.28,.90,.48,'separate\nmemory +\ntoolchain','red_light','red','bold',5.8)],
      [(1.40,2.01,1.65,2.01,'green'),(1.78,1.80,1.55,1.37,'green'),(5.20,2.01,5.55,2.01,'purple'),(5.95,1.80,5.95,1.37,'purple')],w=7,h=3.25)

def toolchain_flows():
    generic_flow('toolchain_flows_redesigned.pdf','GPU-centric and INT8-centric deployment flows',
      [(.25,1.80,.75,.40,'ONNX','panel','gray2'),(1.25,1.80,.75,.40,'TensorRT\nbuild','green_light','green'),(2.25,1.80,.75,.40,'TRT\nengine','panel','gray2'),(3.25,1.80,.75,.40,'runtime\nGPU/DLA','green_light','green'),(.25,.85,.75,.40,'ONNX','panel','gray2'),(1.25,.85,.75,.40,'quantise\nINT8','purple_light','purple'),(2.25,.85,.75,.40,'Hailo\ncompiler','purple_light','purple'),(3.25,.85,.75,.40,'HEF\nbinary','panel','gray2'),(4.25,.85,.95,.40,'host +\naccelerator','purple_light','purple'),(4.35,1.85,1.25,.30,'fallbacks/plugins possible','panel2','gray2'),(5.62,.72,.92,.38,'unsupported\n-> redesign','red_light','red','bold',5.7)],
      [(.99,2.00,1.25,2.00,'green'),(2.00,2.00,2.25,2.00,'green'),(3.00,2.00,3.25,2.00,'green'),(.99,1.05,1.25,1.05,'purple'),(2.00,1.05,2.25,1.05,'purple'),(3.00,1.05,3.25,1.05,'purple'),(4.00,1.05,4.25,1.05,'purple')],[(.05,2.00,'Jetson',7,'green','right'),(.05,1.05,'Hailo',7,'purple','right')],w=7,h=2.95)

def orin_hailo_arch():
    # Redrawn architecture contrast, detail level similar to original paper figure.
    fig,ax=canvas(7,3.8); label(ax,.05,3.60,'Architectural contrast used in the heterogeneous split study',fs=10,weight='bold',ha='left')
    box(ax,.25,.45,3.05,2.75,'',fc='green_light',ec='green',r=.12); label(ax,.42,3.00,'Orin NX SoC',fs=8.5,weight='bold',color='green',ha='left')
    box(ax,.55,2.25,.90,.40,'CPU complex',fc='white',ec='gray2',fs=6.4); box(ax,1.75,2.25,1.05,.40,'Ampere GPU\nTensor Cores',fc='white',ec='gray2',fs=6.2); box(ax,.55,1.58,.85,.36,'NVDLA',fc='white',ec='gray2',fs=6.2); box(ax,1.65,1.58,.85,.36,'media / PVA',fc='white',ec='gray2',fs=6.2); box(ax,1.02,.82,1.42,.40,'shared LPDDR memory',fc='panel',ec='gray2',fs=6.3)
    box(ax,3.85,.45,2.90,2.75,'',fc='purple_light',ec='purple',r=.12); label(ax,4.02,3.00,'Hailo-8',fs=8.5,weight='bold',color='purple',ha='left')
    box(ax,4.08,2.30,.58,.34,'ISP',fc='white',ec='gray2',fs=6); box(ax,4.08,1.82,.58,.34,'M4',fc='white',ec='gray2',fs=6); box(ax,4.08,1.34,.58,.34,'H.264',fc='white',ec='gray2',fs=6)
    ax.add_patch(Rectangle((4.95,1.02),1.50,1.85,fc=C['white'],ec=C['gray2'],lw=.8)); label(ax,5.70,2.70,'NN core',fs=6.8,weight='bold',color='purple')
    for i in range(5):
        for j in range(4): ax.add_patch(Rectangle((5.06+i*.25,1.15+j*.32),.18,.22,fc=[C['blue_light'],C['green_light'],C['orange_light'],C['purple_light']][(i+j)%4],ec='white',lw=.5))
    box(ax,3.25,1.85,.45,.34,'PCIe\nx4',fc='red_light',ec='red',fs=5.8); arrow(ax,3.30,2.02,3.85,2.02,'red'); label(ax,3.50,.65,'host-visible memory/toolchain boundary',fs=6.1,color='red')
    save(fig,'orin_hailo_arch_redesigned.pdf')

def evidence_stack():
    fig,ax=canvas(7,3.2); label(ax,.05,3.02,'Evidence stack for interpreting accelerator numbers',fs=10,weight='bold',ha='left')
    layers=[('vendor / public peak claims','TOPS, TOPS/W, precision, form factor','gray'),('Reuther / LAICS public-data map','segments, architecture classes, provenance','blue_light'),('workload-oriented survey evidence','achieved/peak bridge for selected benchmarks','teal_light'),('VEDLIoT controlled benchmarks','achieved GOPS/GOPS/W, latency, power scope','orange_light'),('this thesis','compile success, split validity, full-system energy','green_light')]
    y=2.42
    for i,(a,b,fc) in enumerate(layers):
        w=5.15+i*.27; x=(7-w)/2; ec='gray2' if fc=='gray' else ('blue' if fc=='blue_light' else 'teal' if fc=='teal_light' else 'orange' if fc=='orange_light' else 'green')
        box(ax,x,y,w,.36,f'{a}: {b}',fc=fc,ec=ec,fs=6.3); y-=.46
    arrow(ax,.70,2.63,.70,.58,'blue'); label(ax,.14,1.55,'increasing\ndeployment\nevidence',fs=6.0,color='blue')
    save(fig,'evidence_stack_redesigned.pdf')

def throughput_taxonomy():
    fig,ax=canvas(7,2.8); label(ax,.05,2.60,'Throughput semantics for full and split deployments',fs=10,weight='bold',ha='left')
    label(ax,.25,2.05,'Full deployment',fs=7.6,weight='bold',color='blue',ha='left')
    for i in range(5):
        box(ax,1.45+i*.70,1.86,.50,.28,f'F{i+1}',fc='blue_light',ec='blue',fs=6)
        if i: arrow(ax,1.45+(i-1)*.70+.50,2.00,1.45+i*.70,2.00,'blue',ms=5)
    label(ax,5.45,2.00,'cycle = repeated full-backend window',fs=6.1,color='muted',ha='left')
    label(ax,.25,1.02,'Heterogeneous split',fs=7.6,weight='bold',color='purple',ha='left')
    for i in range(4):
        box(ax,1.30+i*.92,1.10,.58,.28,f'S1-{i+1}',fc='purple_light',ec='purple',fs=5.8); box(ax,1.64+i*.92,.63,.58,.28,f'S2-{i+1}',fc='green_light',ec='green',fs=5.8); arrow(ax,1.59+i*.92,1.10,1.92+i*.92,.91,'orange',ms=5)
    ax.add_patch(Rectangle((2.55,.48),2.10,1.05,fill=False,ec=C['orange'],lw=1,ls='--')); label(ax,3.60,.32,'steady-state pipeline window',fs=6.0,color='orange'); label(ax,5.45,.86,'cycle governed by slowest\nnon-overlapped stage',fs=6.1,color='muted',ha='left')
    save(fig,'throughput_taxonomy_redesigned.pdf')

def dag_cut():
    fig,ax=canvas(6.7,2.8); label(ax,.05,2.60,'DAG partition cut with branch and join semantics',fs=10,weight='bold',ha='left')
    coords={'A':(.75,1.35),'B':(1.75,1.35),'C1':(2.85,1.80),'C2':(2.85,.90),'J':(3.95,1.35),'D':(4.95,1.35)}
    for n,(x,y) in coords.items(): box(ax,x,y,.55,.36,n,fc='blue_light' if n in ['A','B'] else 'orange_light' if n in ['C1','C2'] else 'green_light' if n=='J' else 'panel',ec='blue' if n in ['A','B'] else 'orange' if n in ['C1','C2'] else 'green' if n=='J' else 'gray2',fs=7.5,weight='bold')
    for a,b in [('A','B'),('B','C1'),('B','C2'),('C1','J'),('C2','J'),('J','D')]: arrow(ax,coords[a][0]+.55,coords[a][1]+.18,coords[b][0],coords[b][1]+.18,'line',ms=6)
    line(ax,2.48,.48,2.48,2.22,'red',lw=1.2,dashed=True); label(ax,2.48,2.35,'boundary',fs=6.2,color='red'); label(ax,3.20,.42,'multiple crossing tensors require explicit staging and join handling',fs=6.0,color='muted')
    save(fig,'dag_cut_redesigned.pdf')

def cost_decomposition():
    items=[]; xvals=[.22,1.20,2.45,3.70,4.95,6.18]; texts=['input','Stage 1\ncompute','boundary\ntransfer','runtime\noverhead','Stage 2\ncompute','output']; fcs=['panel','blue_light','orange_light','red_light','purple_light','panel']; ecs=['gray2','blue','orange','red','purple','gray2']
    for x,t,fc,ec in zip(xvals,texts,fcs,ecs): items.append((x,1.35,.85 if t in ['input','output'] else 1.0,.45,t,fc,ec,'bold' if fc!='panel' else 'normal',6.4))
    links=[]
    for i in range(5): links.append((xvals[i]+(.85 if i in [0,5] else 1.0),1.58,xvals[i+1],1.58,'line'))
    notes=[(1.70,.84,'FLOPs + calibration',5.9,'blue'),(2.95,.84,'activation bytes',5.9,'orange'),(4.20,.84,'sync + queues',5.9,'red'),(5.45,.84,'FLOPs + calibration',5.9,'purple')]
    generic_flow('cost_decomposition_redesigned.pdf','Single-split end-to-end cost decomposition',items,links,notes,w=7,h=2.6)

def multicontext():
    generic_flow('multicontext_redesigned.pdf','Multi-context execution on SRAM-limited dataflow NPUs',
      [(.35,1.45,1.35,.50,'single context\nfits on chip','green_light','green','bold'),(2.05,1.45,1.25,.50,'NPU run\ncontext 1','panel','green'),(.35,.55,1.35,.50,'does not fit\nas one context','red_light','red','bold'),(2.00,.55,.72,.50,'ctx 1','purple_light','purple'),(3.00,.55,.72,.50,'ctx 2','purple_light','purple'),(4.00,.55,.72,.50,'ctx 3','purple_light','purple'),(5.20,.55,1.15,.50,'host-visible\noverhead','orange_light','orange','bold'),(4.10,1.70,2.15,.36,'discrete setup, sync and spills can dominate batch=1','panel2','gray2','normal',6.0)],
      [(1.70,1.70,2.05,1.70,'green'),(1.70,.80,2.00,.80,'purple'),(2.72,.80,3.00,.80,'purple'),(3.72,.80,4.00,.80,'purple'),(4.72,.80,5.20,.80,'orange')],w=7,h=2.75)

def llm_loop():
    items=[]; steps=[('prompt\ntokens','panel','gray2'),('prefill\nfull prompt','blue_light','blue'),('KV cache\nstate','purple_light','purple'),('decode\none token','orange_light','orange'),('logits +\nsampling','yellow_light','yellow'),('append\ntoken','panel','gray2')]
    for i,(t,fc,ec) in enumerate(steps): items.append((.25+i*1.08,1.45,.82,.43,t,fc,ec,'bold' if i in [1,2,3] else 'normal',6.2))
    links=[(.25+i*1.08+.82,1.66,.25+(i+1)*1.08,1.66,'line') for i in range(5)] + [(6.05,1.45,3.85,.70,'orange',False,-.32),(3.55,.70,3.70,1.45,'purple')]
    items.append((3.00,.45,1.20,.36,'update KV cache','purple_light','purple'))
    generic_flow('llm_prefill_decode_loop.pdf','Decoder-only LLM execution is a stateful runtime loop',items,links,[(.25,.20,'Persistent KV state and sampling logic make deployability a runtime-backend problem.',6.0,'muted','left')],w=7,h=2.55)

def genai_orch():
    generic_flow('jetson_hailo10h_genai_orchestration.pdf','Jetson-Hailo-10H GenAI orchestration as a multi-runtime system',
      [(.35,1.90,.95,.45,'camera /\nsensors','panel','gray2'),(1.75,1.90,1.25,.45,'Jetson Orin NX\nvision + host logic','green_light','green','bold'),(3.55,1.90,1.25,.45,'local API\n/ scheduler','orange_light','orange','bold'),(5.25,1.90,1.25,.45,'Hailo-10H\nGenAI runtime','purple_light','purple','bold'),(1.38,.90,1.45,.42,'parallel Jetson work\ntracking, I/O','panel','gray2'),(5.05,.90,1.30,.42,'dedicated GenAI\nresponse service','purple_light','purple'),(2.30,.22,3.20,.36,'near-term: serve a complete GenAI model, not layer-split one decoder stack','red_light','red','bold',6.2)],
      [(1.30,2.12,1.75,2.12,'line'),(3.00,2.12,3.55,2.12,'orange'),(4.80,2.12,5.25,2.12,'purple'),(2.38,1.90,2.10,1.32,'green'),(5.88,1.90,5.72,1.32,'purple')],w=7,h=2.95)

def split_workflow():
    items=[]; steps=[('Load ONNX\nmodel','panel','gray2'),('shape +\nmetadata pass','blue_light','blue'),('candidate\ncut generation','orange_light','orange'),('backend\nconstraints','purple_light','purple'),('rank +\nexport','green_light','green')]
    for i,(t,fc,ec) in enumerate(steps): items.append((.35+i*1.28,1.55,1.00,.45,t,fc,ec,'bold' if i in [2,4] else 'normal',6.2))
    links=[(.35+i*1.28+1.00,1.77,.35+(i+1)*1.28,1.77,'line') for i in range(4)]
    items += [(1.35,.65,1.30,.42,'activation bytes\n+ FLOPs','blue_light','blue'),(3.35,.65,1.30,.42,'deployability\nfilters','red_light','red'),(5.15,.65,1.05,.42,'CSV / PDF\nGUI export','panel','gray2')]
    links += [(1.85,1.55,2.00,1.07,'blue'),(4.00,1.55,4.00,1.07,'red'),(5.70,1.55,5.70,1.07,'green')]
    generic_flow('split_tool_workflow_redesigned.pdf','Workflow of the ONNX split-point analyser',items,links,w=7,h=2.65)

def split_analyser_overview():
    fig,ax=canvas(7,3.2); label(ax,.05,3.00,'Split-point analyser overview export',fs=10,weight='bold',ha='left')
    # three mini charts
    panels=[(.30,1.75,1.85,.85,'Activation bytes per cut','blue'),(2.58,1.75,1.85,.85,'Cumulative compute split','green'),(4.86,1.75,1.85,.85,'Candidate score / Pareto','orange')]
    for x,y,w,h,t,col in panels:
        box(ax,x,y,w,h,'',fc='white',ec='gray2',r=.05); label(ax,x+.10,y+.73,t,fs=6.3,weight='bold',color=col,ha='left')
    # draw chart lines
    ax.plot([.45,.75,1.05,1.40,1.75],[2.02,2.18,2.03,2.35,1.96],color=C['blue'],lw=1.3); ax.plot([2.75,3.05,3.40,3.75,4.15],[1.95,2.05,2.18,2.28,2.42],color=C['green'],lw=1.3)
    for x,y in [(5.08,1.98),(5.35,2.18),(5.75,2.05),(6.20,2.38),(6.45,2.12)]: ax.plot(x,y,'o',ms=3,color=C['orange'])
    box(ax,.35,.55,1.60,.55,'model facts\nnodes, tensors, ops','panel','gray2',fs=6.2); box(ax,2.30,.55,1.60,.55,'boundary table\nbytes, FLOPs, risk','panel','gray2',fs=6.2); box(ax,4.25,.55,1.60,.55,'selected cuts\nexported artefacts','green_light','green',fs=6.2,weight='bold')
    arrow(ax,1.95,.82,2.30,.82,'muted'); arrow(ax,3.90,.82,4.25,.82,'muted')
    save(fig,'split_analyser_overview.pdf')

def split_analyser_gui():
    fig,ax=canvas(7,3.6); label(ax,.05,3.42,'Split-point analyser GUI layout',fs=10,weight='bold',ha='left')
    box(ax,.25,.35,1.55,2.70,'settings panel\n\nmodel path\nbackend pair\nscore weights\nconstraints',fc='panel2',ec='gray2',fs=6.4)
    box(ax,2.05,2.15,2.10,.90,'candidate table\nrank | boundary | bytes | score | status',fc='white',ec='blue',fs=6.4,weight='bold')
    box(ax,4.45,2.15,2.10,.90,'graph summary\noperator coverage\nshape completeness',fc='white',ec='green',fs=6.4,weight='bold')
    box(ax,2.05,.50,2.10,1.25,'plot area A\nactivation bytes\ncompute balance',fc='blue_light',ec='blue',fs=6.4)
    box(ax,4.45,.50,2.10,1.25,'plot area B\nPareto / score\nlatency model',fc='orange_light',ec='orange',fs=6.4)
    arrow(ax,1.80,1.70,2.05,2.55,'muted'); arrow(ax,3.10,2.15,3.10,1.75,'blue'); arrow(ax,5.50,2.15,5.50,1.75,'orange')
    save(fig,'split_analyser_gui.pdf')

def eval_pipeline_model():
    fig,ax=canvas(7,2.9); label(ax,.05,2.70,'Two-stage single-boundary pipeline execution model',fs=10,weight='bold',ha='left')
    label(ax,.65,1.90,'Stage 1\nASIC',fs=6.5,color='purple',ha='right'); label(ax,.65,1.10,'Stage 2\nGPU',fs=6.5,color='green',ha='right')
    for i in range(6):
        x=1.0+i*.72
        box(ax,x,1.75,.55,.28,f'F{i+1}',fc='purple_light',ec='purple',fs=5.8)
        if i>0: box(ax,x-.35,.95,.55,.28,f'F{i}',fc='green_light',ec='green',fs=5.8)
    ax.add_patch(Rectangle((2.38,.78),2.60,1.30,fill=False,ec=C['orange'],lw=1,ls='--'))
    label(ax,3.68,.62,'steady state: throughput after fill and before flush',fs=6.2,color='orange')
    arrow(ax,1.0,.35,5.40,.35,'line'); label(ax,5.55,.35,'time',fs=6.2,color='muted',ha='left')
    save(fig,'evaluation_pipeline_model_redesigned.pdf')

def pareto():
    fig,ax=plt.subplots(figsize=(5.8,3.2)); fig.patch.set_facecolor('white'); ax.set_xlim(0,6); ax.set_ylim(0,4.2); ax.set_xlabel('latency $T_{e2e}$ ↓'); ax.set_ylabel('energy $E_{inf}$ ↓'); axes_style(ax,grid=True)
    pts=[(1.1,3.6),(1.7,2.6),(2.3,2.0),(3.0,1.6),(4.2,1.3),(2.5,3.2),(3.8,2.7),(5.0,2.4),(4.8,3.6)]
    front=[(1.1,3.6),(1.7,2.6),(2.3,2.0),(3.0,1.6),(4.2,1.3)]
    ax.scatter([p[0] for p in pts],[p[1] for p in pts],s=28,c=C['gray2'],edgecolors=C['line'],linewidths=.5,label='dominated / infeasible')
    ax.plot([p[0] for p in front],[p[1] for p in front],'-o',color=C['blue'],ms=4,label='Pareto front')
    ax.annotate('feasible candidates\n(pass accuracy + deployability)',xy=(3.9,2.7),xytext=(3.3,3.55),arrowprops=dict(arrowstyle='->',color=C['muted'],lw=.8),fontsize=7,color=C['muted'])
    ax.legend(frameon=False,loc='upper right')
    save(fig,'pareto_concept_redesigned.pdf')

# --- data-driven plots ---
def extract_yolov4_scatter():
    import fitz
    p=fitz.open(SOURCE/'vedliot_yolov4_power_vs_perf.pdf')[0]
    x10=170.673583984375; x100=333.90478515625; y1e3=182.58074951171875; y1e4=87.98123168945312
    def xy(cx,cy):
        return 10**(1+(cx-x10)/(x100-x10)), 10**(3+(y1e3-cy)/(y1e3-y1e4))
    points={'FP16':[],'FP32':[],'INT8':[]}
    for d in p.get_drawings():
        fill=d.get('fill');
        if not fill or fill==(1,1,1): continue
        r=d['rect']; cx=(r.x0+r.x1)/2; cy=(r.y0+r.y1)/2
        if not(50<=cx<=450 and 10<=cy<=264 and r.width<=12 and r.height<=12): continue
        if max(fill)<.05: continue
        color=tuple(round(c,3) for c in fill)
        name=None
        if abs(color[0]-0.122)<.01 and abs(color[1]-0.467)<.02: name='FP16'
        elif abs(color[0]-1.0)<.01 and abs(color[1]-.498)<.02: name='FP32'
        elif abs(color[0]-.173)<.02 and abs(color[1]-.627)<.02: name='INT8'
        if name:
            x,y=xy(cx,cy)
            if abs(x-287.5)<1 and y<400: continue # legend marker inside plot area
            points[name].append((x,y))
    return points

def yolov4_power_perf():
    pts=extract_yolov4_scatter(); fig,ax=plt.subplots(figsize=(6.4,4.0)); fig.patch.set_facecolor('white')
    colors={'FP16':C['blue'],'FP32':C['orange'],'INT8':C['green']}; markers={'FP16':'o','FP32':'s','INT8':'^'}
    for k,p in pts.items(): ax.scatter([x for x,y in p],[y for x,y in p],s=24,marker=markers[k],c=colors[k],edgecolors='white',linewidths=.45,label=f'{k} ({len(p)} pts)')
    ax.set_xscale('log'); ax.set_yscale('log'); ax.set_xlabel('Power [W]'); ax.set_ylabel('Throughput [GOPS]'); axes_style(ax,grid=True); ax.legend(frameon=False,loc='lower right')
    ax.axvline(25,color=C['red'],lw=.9,ls='--'); ax.text(25*1.05,130,'25 W',fontsize=6.5,color=C['red'])
    save(fig,'yolov4_power_perf_redesigned.pdf')

def barh_plot(name,title,labels,values,xlabel,log=False,width=6.7,height=4.6):
    fig,ax=plt.subplots(figsize=(width,height)); fig.patch.set_facecolor('white')
    y=range(len(labels)); ax.barh(y,values,color=C['blue2'],edgecolor=C['blue'],lw=.4); ax.set_yticks(y); ax.set_yticklabels(labels); ax.set_xlabel(xlabel); axes_style(ax,grid=True); ax.grid(axis='y',visible=False)
    if log: ax.set_xscale('log'); ax.xaxis.set_major_locator(LogLocator(base=10)); ax.xaxis.set_major_formatter(LogFormatterMathtext(base=10))
    ax.set_title(title,loc='left',fontweight='bold',fontsize=9,color=C['ink'])
    save(fig,name)

def vedliot_bars():
    labels=['ZU3 B2304','ZU15 2xB4096','Xavier AGX (LP)','Xavier AGX','Orin AGX','Orin NX','Orin AGX (B8)','Xavier AGX (HP_B8)','Orin NX (B8)','Xavier NX','VC1902 C32B6','Xavier NX (B8)','Hailo-8 + Host','Hailo-8 + Host (B8)','Hailo-8','Hailo-8 (B8)']
    vals=[34.4,47.1,154.7,177.0,184.6,191.0,196.1,209.8,216.7,242.5,269.5,285.8,340.8,545.2,1345.9,1585.2]
    barh_plot('yolov4_efficiency_int8_redesigned.pdf','YOLOv4 INT8 efficiency (log scale)',labels,vals,'Efficiency [GOPS/W]',log=True,width=6.8,height=5.0)
    labels2=['GAP8','i.MX8M Plus (B1)','Xavier AGX TVM (B1)','Xavier AGX (LP)','Hailo-8 (B1)','Coral (Dev.)','Coral (M.2)','ZU3 B2304 (v2)','Xavier NX (B1)','Xavier NX (B8)']
    vals2=[2.2,3.4,4.0,5.2,5.7,7.6,8.5,8.8,12.3,26.9]
    barh_plot('mobilenet_efficiency_lp_redesigned.pdf','MobileNetV3 INT8 efficiency on low-power devices',labels2,vals2,'Efficiency [GOPS/W]',width=6.4,height=3.8)

def partitioning_setup():
    generic_flow('partitioning_setup_redesigned.pdf','Heterogeneous YOLOv7 split setup on u.RECS',
      [(.30,1.80,1.00,.45,'input\nframes','panel','gray2'),(1.75,1.80,1.30,.45,'Hailo-8\nstage 1','purple_light','purple','bold'),(3.55,1.80,1.00,.45,'activation\nhandover','orange_light','orange','bold'),(5.00,1.80,1.30,.45,'Orin NX\nTensorRT stage 2','green_light','green','bold'),(1.75,.85,1.30,.38,'HEF / contexts','panel','gray2'),(5.00,.85,1.30,.38,'TRT engine','panel','gray2'),(3.15,.30,1.45,.38,'u.RECS power + timing window','yellow_light','yellow')],
      [(1.30,2.02,1.75,2.02,'line'),(3.05,2.02,3.55,2.02,'orange'),(4.55,2.02,5.00,2.02,'orange'),(2.40,1.80,2.40,1.23,'purple'),(5.65,1.80,5.65,1.23,'green'),(3.70,.68,3.88,1.80,'yellow',True)],w=7,h=2.8)

def partitioning_speedup_fps():
    # conceptual speedup / pipeline overlap diagram
    fig,ax=canvas(6.4,2.5); label(ax,.05,2.32,'Pipeline overlap hides part of the split overhead',fs=10,weight='bold',ha='left')
    # single row
    label(ax,.40,1.65,'single accelerator',fs=6.5,color='muted',ha='right')
    box(ax,.70,1.48,.65,.30,'pre',fc='orange_light',ec='orange',fs=5.8); box(ax,1.40,1.48,3.45,.30,'P1 + P2',fc='blue_light',ec='blue',fs=5.8); line(ax,.68,1.34,4.90,1.34,'blue'); label(ax,2.80,1.18,'cycle time',fs=5.8,color='blue')
    label(ax,.40,.85,'double accelerator',fs=6.5,color='muted',ha='right')
    box(ax,.70,.68,.65,.30,'pre',fc='orange_light',ec='orange',fs=5.8); box(ax,1.40,.98,1.30,.30,'P1',fc='purple_light',ec='purple',fs=5.8); box(ax,2.85,.68,.55,.30,'trans',fc='yellow_light',ec='yellow',fs=5.6); box(ax,3.55,.68,1.15,.30,'P2',fc='green_light',ec='green',fs=5.8); line(ax,1.40,.45,4.70,.45,'green'); label(ax,3.05,.30,'shorter steady-state cycle',fs=5.8,color='green')
    arrow(ax,4.95,1.34,4.95,.45,'red'); label(ax,5.12,.92,'speedup',fs=6.2,color='red',ha='left')
    save(fig,'partitioning_speedup_redesigned.pdf')
    # FPS chart using values extracted from original figure
    labels=['Hailo x1 & Hailo x4','NX & Hailo x1','NX & Hailo x4','Hailo 0001 & NX','Hailo 0004 & NX','Split locally on NX','Hailo x1','Hailo x4','NX']
    p1=[96,68,68,95,96,54,0,0,0]; p2=[56,25,46,115,115,107,0,0,0]; single=[0,0,0,0,0,0,22,37,57]
    fig,ax=plt.subplots(figsize=(6.5,4.0)); fig.patch.set_facecolor('white'); y=list(range(len(labels)))
    ax.barh(y,single,color=C['green'],label='Single'); ax.barh(y,p2,color=C['blue2'],label='P2'); ax.barh(y,p1,left=p2,color=C['orange'],label='P1')
    ax.set_yticks(y); ax.set_yticklabels(labels); ax.invert_yaxis(); ax.set_xlabel('FPS'); axes_style(ax,grid=True); ax.grid(axis='y',visible=False); ax.legend(frameon=False,loc='lower right')
    save(fig,'partitioning_fps_redesigned.pdf')

def yolov7_plots():
    df=pd.read_csv(ROOT/'results/supplementary-studies/dissertation-v56/inputs/yolov7/prediction_vs_benchmark_yolov7_cases.csv')
    best_split=df['h2t_fps'].max(); hailo_full=(1000/df['hailo_composed_ms']).max(); trt_full=(1000/df['trt_full_ms']).max(); cuda_full=(1000/df['cuda_full_ms']).max()
    fig,ax=plt.subplots(figsize=(5.6,3.0)); fig.patch.set_facecolor('white')
    labels=['CUDA full','TensorRT full','Hailo full','best Hailo→TRT split']; vals=[cuda_full,trt_full,hailo_full,best_split]
    ax.bar(labels,vals,color=[C['gray2'],C['green'],C['purple'],C['orange']],edgecolor=C['line'],linewidth=.4); ax.set_ylabel('Throughput [FPS]'); axes_style(ax,grid=True); ax.grid(axis='x',visible=False); ax.tick_params(axis='x',rotation=18); save(fig,'yolov7_best_full_vs_best_split.pdf')
    fig,ax=plt.subplots(figsize=(5.5,3.4)); fig.patch.set_facecolor('white'); ideal=1000/df['h2t_cycle_ms']; real=df['h2t_fps']; ax.scatter(ideal,real,c=C['blue'],edgecolors='white',s=35); m=max(ideal.max(),real.max())*1.05; ax.plot([0,m],[0,m],ls='--',color=C['muted']); ax.set_xlabel('Ideal bottleneck throughput [FPS]'); ax.set_ylabel('Measured streaming throughput [FPS]'); axes_style(ax,grid=True); save(fig,'yolov7_ideal_vs_real.pdf')
    fig,ax=plt.subplots(figsize=(5.4,3.2)); fig.patch.set_facecolor('white'); ax.scatter(df['pred_rank_score'],df['actual_rank_h2t'],c=C['orange'],edgecolors='white',s=35); ax.plot([1,10],[1,10],ls='--',color=C['muted']); ax.set_xlabel('Predicted rank'); ax.set_ylabel('Measured H2T rank'); ax.set_xlim(.5,10.5); ax.set_ylim(.5,10.5); ax.invert_yaxis(); axes_style(ax,grid=True); save(fig,'yolov7_predicted_rank_vs_actual.pdf')
    fig,ax=plt.subplots(figsize=(5.4,3.2)); fig.patch.set_facecolor('white'); ax.scatter(df['pred_score'],df['h2t_fps'],c=C['purple'],edgecolors='white',s=35); ax.set_xlabel('Predicted score (lower is better)'); ax.set_ylabel('Measured H2T throughput [FPS]'); axes_style(ax,grid=True); save(fig,'yolov7_score_vs_fps.pdf')

def resnet_energy():
    labels=['DeepX full','TensorRT full','DX→TRT b059','DX→TRT b054']; vals=[37.8,112.8,144.4,164.1]
    fig,ax=plt.subplots(figsize=(5.8,3.0)); fig.patch.set_facecolor('white'); ax.bar(labels,vals,color=[C['purple'],C['green'],C['orange'],C['orange']],edgecolor=C['line'],linewidth=.4); ax.set_ylabel('Energy per frame [mJ]'); axes_style(ax,grid=True); ax.grid(axis='x',visible=False); ax.tick_params(axis='x',rotation=18); save(fig,'resnet50_energy_frame.pdf')

# Execute all
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True,
                        help='Directory with the four external original graphics')
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT/'local-output'/'dissertation-v56-legacy'/'redesigned',
                        help='Destination containing figures/ and photos/ subdirectories')
    args = parser.parse_args()
    SOURCE = args.source_dir.resolve()
    required = [SOURCE/name for name in (
        'urecs_real_front.png', 'recs_pcb_front.png', 'recs_pcb_back.png',
        'vedliot_yolov4_power_vs_perf.pdf',
    )]
    required.append(ROOT/'results/supplementary-studies/dissertation-v56/inputs/yolov7/prediction_vs_benchmark_yolov7_cases.csv')
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        parser.error('Missing original inputs; supply --source-dir from the original archive. '
                     'No outputs were generated. Missing: ' + ', '.join(missing))
    OUT = args.output_dir.resolve()/'figures'
    PHOTO = args.output_dir.resolve()/'photos'
    OUT.mkdir(parents=True, exist_ok=True)
    PHOTO.mkdir(parents=True, exist_ok=True)
    related_work_settings(); genai_stack(); recs_family(); urecs_architecture(); urecs_power(); com_brick(); toolchain_bridge(); management(); photo_cleaning(); energy_scopes(); ground_truth(); time_alignment(); urecs_window(); edge_pipeline(); accelerator_tradeoff(); accelerator_paradigms(); jetson_hailo(); toolchain_flows(); orin_hailo_arch(); evidence_stack(); throughput_taxonomy(); dag_cut(); cost_decomposition(); multicontext(); llm_loop(); genai_orch(); split_workflow(); split_analyser_overview(); split_analyser_gui(); eval_pipeline_model(); pareto(); yolov4_power_perf(); vedliot_bars(); partitioning_setup(); partitioning_speedup_fps(); yolov7_plots(); resnet_energy()
    print(f'Generated redesigned figures in {OUT}')
