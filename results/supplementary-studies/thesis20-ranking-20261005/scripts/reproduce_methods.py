#!/usr/bin/env python3
"""Reproduce methods evaluation and two vector figures from compact frozen inputs."""
import argparse
from pathlib import Path
from evaluate_methods import analyze
from reproduce_method_scores import analyze as reproduce_scores
from render_methods import render

def main():
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,default=root/'source');p.add_argument('--deep-root',type=Path);p.add_argument('--method-root',type=Path,default=root);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args()
    reproduce_scores(a.method_root.resolve(),a.source_root.resolve(),a.output_root.resolve())
    analyze(a.source_root.resolve(),a.output_root.resolve(),a.output_root.resolve(),a.deep_root)
    render(a.source_root.resolve(),a.output_root.resolve(),a.output_root.resolve(),a.deep_root)
if __name__=='__main__':main()
