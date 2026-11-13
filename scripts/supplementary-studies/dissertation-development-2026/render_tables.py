#!/usr/bin/env python3
"""Render supplied historical manuscript cells; no metric or interval estimation.

Adapted from style_v44/scripts/render_tables.py and its TeX wrappers. Decimal
ROUND_HALF_UP and quality/runtime identity checks retain the source convention.
"""
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import csv
import re


def read(source, name):
    with (source/f'{name}_full_precision.csv').open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def fmt(s, n):
    return str(Decimal(s).quantize(Decimal('1').scaleb(-n), rounding=ROUND_HALF_UP))


def markdown(headers, rows, caption):
    return (caption+'\n\n| '+' | '.join(headers)+' |\n| '+
            ' | '.join(['---']*len(headers))+' |\n'+
            ''.join('| '+' | '.join(map(str,row))+' |\n' for row in rows))


def tex_escape(value):
    return (str(value).replace('&',r'\&').replace('_',r'\_')
            .replace('%',r'\%').replace('→',r'$\rightarrow$'))


def expected_rows(source):
    dec=read(source,'yolov7_decoder'); q=read(source,'yolov7_quality')
    n=read(source,'yolov7_native'); h=read(source,'hailo_optimisation')
    if (len(dec),len(q),len(n),len(h))!=(3,9,9,4):
        raise ValueError('Unexpected source table size')
    labs=['Tiny anchors; production policy','Standard anchors; production policy','Standard anchors; sanity policy']
    decoder=[[labs[i]]+[fmt(row[k],3) for k in ['AP','AP50','AP75']] for i,row in enumerate(dec)]
    tex={'decoder_table':[' & '.join(row)+r' \\' for row in decoder],
         'quality_table':[], 'native_table':[], 'hailo_optimisation_table':[]}
    quality=[]; native=[]; compiler=[]
    for i,(a,b) in enumerate(zip(q,n)):
        if a['source_label']!=b['source_label'] or a['decision']!=b['decision']:
            raise ValueError('Quality and runtime identities differ')
        setup=['DEEPX','Hailo-10H','Hailo-8'][i//3]
        path=['Split b044','Accelerator Full','TensorRT Full'][i%3]
        expected_label=(setup+r'$\rightarrow$TensorRT, \texttt{b044}' if i%3==0 else
                        setup+' Full' if i%3==1 else 'TensorRT Full on '+setup+' setup')
        if a['source_label']!=expected_label:
            raise ValueError('Unexpected deployment identity or row order')
        if a['decision'] not in ('pass','fail'):
            raise ValueError('Unexpected quality decision')
        if not Decimal(b['ci_low'])<=Decimal(b['fps'])<=Decimal(b['ci_high']):
            raise ValueError('Reported median outside reported interval')
        qrow=[setup,path]+[fmt(a[k],3) for k in ['Q','Q50','Q75']]+[a['decision']]
        quality.append(qrow)
        ci=fmt(b['ci_low'],2)+'–'+fmt(b['ci_high'],2)
        native.append([setup,path,fmt(b['fps'],2),ci,b['decision']])
        if i and i%3==0:
            tex['quality_table'].append(r'\addlinespace[.3em]')
            tex['native_table'].append(r'\addlinespace[.3em]')
        tex['quality_table'].append(' & '.join([setup if i%3==0 else '']+qrow[1:])+r' \\')
        ci=r'\num{'+fmt(b['ci_low'],2)+r'}--\num{'+fmt(b['ci_high'],2)+'}'
        tex['native_table'].append(' & '.join([setup if i%3==0 else '',path,fmt(b['fps'],2),ci,b['decision']])+r' \\')
    if len({(r['source_label'],r['level']) for r in h})!=4:
        raise ValueError('Duplicate compiler-sensitivity identity')
    for row in h:
        values=[row[k] for k in ['Q','Q50','Q75']]
        if row['decision']=='not evaluated':
            if any(values) or row['source_label']!='Hailo-10H Full' or row['level']!='2':
                raise ValueError('Unexpected missing compiler outcome')
        elif not all(values) or row['decision']!='fail':
            raise ValueError('Invalid compiler quality outcome')
        display=[fmt(v,3) if v else 'NA' for v in values]
        compiler.append([row['source_label'],row['level']]+display+[row['decision']])
        tex['hailo_optimisation_table'].append(' & '.join(
            [row['source_label'].removesuffix(' Full'),row['level']]+
            ['{--}' if v=='NA' else v for v in display]+[row['decision']])+r' \\')
    tables={
      'decoder_table':(['Decoder','AP','AP50','AP75'],decoder,
         'Official COCO decoder comparison on the same 500 inference outputs. Fractions; the sanity policy uses different thresholds.'),
      'quality_table':(['Setup','Path','Q','Q50','Q75','Quality'],quality,
         'Internal paired B500 quality. Q metrics are distinct from official COCO AP; recorded decisions use unrounded source cells.'),
      'native_table':(['Setup','Path','FPS','95% interval (FPS)','Quality'],native,
         'Completed-detection throughput including host decoding/NMS. Reported bootstrap intervals for medians of three fresh-process repeats; quality is separately bound. Two decimal places retain the narrow low-FPS contrasts.'),
      'hailo_optimisation_table':(['Backend','Level','Q','Q50','Q75','Decision'],compiler,
         'Bounded compiler sensitivity under the internal B500 evaluator. Hailo-10H level 2 has no evaluable outcome because the request used hailo10 instead of hailo10h; NA is not quality loss.')}
    return tex,tables


def matrix(source):
    with (source/'resnet_matrix_reported.csv').open(encoding='utf-8',newline='') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=7 or len({r['execution_path'] for r in rows})!=7:
        raise ValueError('Expected seven unique reported matrix paths')
    def interval(row,low,high):
        a,b=row[low],row[high]
        if bool(a)!=bool(b):
            raise ValueError('Incomplete reported range')
        if a and Decimal(a)>Decimal(b):
            raise ValueError('Reversed reported range')
        return a if a==b else a+'–'+b
    displayed=[]; body=[]
    for i,row in enumerate(rows):
        values=[]
        for stem in ['top1','top5']:
            value=interval(row,stem+'_min',stem+'_max')
            if row[stem+'_status'] not in ('reported','split-dependent'):
                raise ValueError('Unknown quality reporting status')
            if (row[stem+'_status']=='reported')!=bool(value):
                raise ValueError('Value/status disagreement')
            values.append(value or row[stem+'_status'])
        values += [interval(row,'latency_ms_min','latency_ms_max') or 'NA',
                   interval(row,'throughput_fps_min','throughput_fps_max') or 'NA']
        displayed.append([row['execution_path']]+values+[row['status']])
        if i: body.append(r'\addlinespace[0.35em]')
        body.append(' & '.join([tex_escape(row['execution_path'])]+[
            ('--' if v=='NA' else 'split-dep.' if v=='split-dependent' else
             '--'.join(r'\num{'+x+'}' for x in v.split('–'))) for v in values])+r' \\')
        body.append(r'\multicolumn{5}{@{}L{\dimexpr\linewidth-2\tabcolsep\relax}@{}}{\emph{Status:} '+tex_escape(row['status'])+r'}\\')
    return body,(['Execution path','Top-1','Top-5','Latency (ms)','Throughput (FPS)','Status'],displayed,
      'Reported ResNet50/Imagenette development matrix. Ranges retain mixed original timing contracts; unavailable throughput is NA and is never inferred from latency. Quality is a fraction. This is neither ImageNet nor B500.')


def render(source, templates, output):
    tex,tables=expected_rows(source)
    tex['resnet_matrix'],tables['resnet_matrix']=matrix(source)
    for name,body in tex.items():
        template=(templates/(name+'.tex')).read_text(encoding='utf-8')
        match=re.search(r'(\\midrule\n)(.*?)(\n\\bottomrule)',template,re.S)
        if not match: raise ValueError('No table body in '+name)
        (output/(name+'.tex')).write_text(template[:match.start(2)]+'\n'.join(body)+template[match.end(2):],encoding='utf-8')
        headers,rows,caption=tables[name]
        (output/(name+'.md')).write_text(markdown(headers,rows,caption),encoding='utf-8')
    return {'decoder':3,'quality':9,'native':9,'compiler_sensitivity':4,'resnet_matrix':7}


def render_rankings(source, output):
    specs=[('phase2_ranking_diagnostic_spearman_six_eligible_strata.csv','ranking_methods','method_id','diagnostic_paired_candidate_count','diagnostic_spearman_rho'),
           ('static_proxy_spearman_confirmatory.csv','ranking_proxies','feature','paired_candidate_count','spearman_rho')]
    # Same presentation names as the existing ranking chart; no correlations recomputed.
    from plot_rankings import METHODS, FEATURES, MODEL, DIRECTION, model_key
    labels=dict((x[0],x[1]) for x in METHODS+FEATURES)
    for filename,name,identity,count,value in specs:
        with (source/filename).open(encoding='utf-8',newline='') as f:
            rows=list(csv.DictReader(f))
        display=[]
        for row in rows:
            model,direction=model_key(row)
            display.append([MODEL[model],DIRECTION[direction],labels[row[identity]],row[count],fmt(row[value],3)])
        headers=['Model','Accelerator prefix','Method / proxy','Paired n','Spearman rho']
        caption='Historical six-stratum Generic development audit: supplied aggregate correlations, unchanged paired counts. No candidate-level Spearman re-estimation.'
        (output/(name+'.md')).write_text(markdown(headers,display,caption),encoding='utf-8')
        tex=r'\begin{longtable}{@{}llp{5.3cm}rr@{}}'+'\n'+r'\caption{'+caption+r'}\\'+'\n'+r'\toprule'+'\n'
        tex+=' & '.join(tex_escape(x) for x in headers)+r' \\'+'\n'+r'\midrule\endhead'+'\n'
        tex+='\n'.join(' & '.join(tex_escape(x) for x in row)+r' \\' for row in display)
        tex+='\n'+r'\bottomrule\end{longtable}'+'\n'
        (output/(name+'.tex')).write_text(tex,encoding='utf-8')
