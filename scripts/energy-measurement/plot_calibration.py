#!/usr/bin/env python3
"""Plot the supplied calibration verification rows; no fitting or measurement."""
import argparse,csv,os
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
repo=Path(__file__).resolve().parents[2];out=a.output.resolve()
if out==repo or repo in out.parents:p.error('Use an output directory outside the repository.')
out.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR',str(out/'matplotlib-cache'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
with (repo/'results/energy-measurement/data/tim/validation/calibration/jetson_calibration_verification_rows.csv').open(newline='') as f:rows=list(csv.DictReader(f))
fig,ax=plt.subplots(figsize=(6,3.5))
for sheet,label in [('INA225','PicoScope / INA225'),('firmware','u.RECS firmware')]:
 rr=[r for r in rows if r['sheet']==sheet and r['zero_target']=='False']
 assert len(rr)==35
 ax.plot([float(r['actual_A']) for r in rr],[float(r['signed_relative_error_pct']) for r in rr],'.-',label=label)
ax.axhline(0,color='0.5',linewidth=.7);ax.set(xlabel='Reference current (A)',ylabel='Signed current difference (%)')
ax.grid(alpha=.2);ax.legend();fig.tight_layout()
for ext in ['pdf','png']:fig.savefig(out/('current_verification.'+ext),dpi=160)
plt.close(fig)
print('PASS: 35 nonzero verification settings per path; zero-target rows remain in the supplied CSV.')
