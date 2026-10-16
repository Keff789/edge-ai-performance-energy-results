"""Check expanded-render estimators against independently checked final TIM tables."""
import csv, math, statistics

def verify(data, result_root):
    with (result_root/'tables/tim/direct_rates.csv').open(newline='') as f: rates=list(csv.DictReader(f))
    with (result_root/'tables/tim/paired_300s.csv').open(newline='') as f: pairs=list(csv.DictReader(f))
    maximum=0.0
    for row in rates:
        sid=row['series'];view=row['window']
        means=[statistics.mean(r['energy_J'] for r in data.get(sid,view,'pico',x)) for x in data.grid(sid) if data.get(sid,view,'pico',x)]
        residual=abs(statistics.mean(means)-float(row['reference_J']))
        if residual>1e-9:raise ValueError('Final rate-group reference mismatch: '+sid)
        maximum=max(maximum,residual)
    for row in pairs:
        group=data.pair_group(row['series'],row['window'],row['sensor'],300.)
        for quantity,prefix in [('energy','E'),('power','P'),('duration','T')]:
            residual=abs(group[quantity+'_paired_median_pct']-float(row[prefix+'_median_pct']))
            if residual>1e-9:raise ValueError('Final paired median mismatch: '+row['series'])
            maximum=max(maximum,residual)
    print(f'PASS: {len(rates)} final rate-group references and {len(pairs)*3} paired medians; maximum residual {maximum:.3g}.')
