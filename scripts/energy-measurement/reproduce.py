#!/usr/bin/env python3
"""Regenerate TIM numerical exports and charts in a separate output directory."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--verify-only', action='store_true', help='Audit shipped numeric tables using only the standard library.')
    p.add_argument('--historical-fp16-only', action='store_true', help='Regenerate only the separately labelled historical 13-run FP16 curves.')
    a = p.parse_args()
    if a.verify_only and a.historical_fp16_only:
        p.error('Choose either verification or the historical FP16 study.')
    out = a.output.resolve()
    if out == REPO or REPO in out.parents:
        p.error('Output must be outside the repository.')
    if out.exists() and not out.is_dir():
        p.error('Output must be a directory.')
    if out.exists() and any(out.iterdir()):
        p.error('Choose an empty output directory.')
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ENERGY_OUTPUT_ROOT=str(out), PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(out/'matplotlib-cache'))
    if a.historical_fp16_only:
        commands = []
    elif a.verify_only:
        env['ENERGY_VERIFY_SHIPPED'] = '1'
        commands = [HERE/'tim/verify_results.py']
    else:
        commands = [HERE/'tim'/f for f in ['generate_results.py','make_figures.py','make_foundation_figures.py','verify_results.py']]
        commands.append(HERE/'make_device_comparison.py')
    for script in commands:
        subprocess.run([sys.executable,str(script)],env=env,check=True)
    if not a.verify_only:
        os.environ['MPLCONFIGDIR'] = env['MPLCONFIGDIR']
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(HERE))
        import historical_fp16
        historical_fp16.reproduce(out)
    print('PASS: existing exported outcomes checked; no acquisition or raw-waveform reconstruction.')


if __name__ == '__main__':
    main()
