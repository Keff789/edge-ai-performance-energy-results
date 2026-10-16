"""One-command journal artifacts, isolated from the completed workshop pipeline."""
from __future__ import annotations
import argparse
import csv
import fcntl
import hashlib
import json
import logging
import os
import re
from pathlib import Path
import shutil
import tempfile
import zipfile
import numpy as np
from . import __version__
from .utils import LOGGER, setup_logging, stable_hash, write_json, read_json, utc_now_iso, package_versions
from .journal_data import load_journal_config, load_jetson, load_npy_platforms, JOURNAL_SCHEMA, identity
from .journal_artifacts import render_paired, render_platforms, render_extra_setup_comparisons, export_csv, latex_escape


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): h.update(block)
    return h.hexdigest()


def _inventory(root: Path):
    rows=[]
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name!='journal_inventory.csv':
            rows.append({'path':path.relative_to(root).as_posix(),'size_bytes':path.stat().st_size,'sha256':sha256(path)})
    return rows


def verify_inventory(root: Path, inventory_path: Path) -> bool:
    if not inventory_path.is_file():return False
    try:
        with inventory_path.open(encoding='utf-8',newline='') as f:
            for row in csv.DictReader(f):
                rel=Path(row['path'])
                if rel.is_absolute() or '..' in rel.parts:return False
                p=root/rel
                if not p.is_file() or p.stat().st_size!=int(row['size_bytes']) or sha256(p)!=row['sha256']:return False
        return True
    except (OSError,ValueError,KeyError):return False


def _snippets(stage: Path, figures):
    files=[]
    latex=stage/'latex';latex.mkdir(exist_ok=True)
    lines=['% Paths are relative to the journal artifact root. Requires graphicx.', '']
    for entry in figures:
        path=Path(entry['figure']).relative_to(stage).with_suffix('.pdf').as_posix()
        lines += [r'\begin{figure}[tbp]',r'\centering',r'\includegraphics[width=\linewidth]{'+path+'}',
                  r'\caption{'+latex_escape(entry['caption'])+'}',
                  r'\label{fig:journal-'+re.sub(r'[^A-Za-z0-9:-]+','-',path.removesuffix('.pdf'))+'}',r'\end{figure}', '']
    (latex/'journal_figure_snippets.tex').write_text('\n'.join(lines),encoding='utf-8')
    tablelines=['% From the journal artifact root. Requires booktabs and graphicx.']
    for p in sorted(stage.glob('*/tables/*.tex')):
        tablelines.append(r'\input{'+p.relative_to(stage).as_posix()+'}')
    (latex/'journal_table_snippets.tex').write_text('\n'.join(tablelines)+'\n',encoding='utf-8')


def run_journal(config, *, force=False, artifacts_only=False, verbose=False):
    cfg=config
    cfg.output.mkdir(parents=True,exist_ok=True)
    # Each command holds a dedicated lock; no lock/file in legacy trees is changed.
    with (cfg.output/'.journal.lock').open('a+') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as e:raise RuntimeError('Another journal run is active; do not start it twice') from e
        setup_logging(cfg.output,verbose)
        LOGGER.info('Journal tool %s; output %s',__version__,cfg.output)
        LOGGER.info('Frozen upstream: read-only %s; no scope/Common-Reference command is called',cfg.multi_root)
        jetson,ja=load_jetson(cfg)
        hailo,ha=load_npy_platforms(cfg,force=force,cached_only=artifacts_only)
        audit=ja+ha
        curves=jetson+hailo
        if len({c.key for c in curves})!=len(curves):raise ValueError('Colliding journal series identifiers')
        signatures=[{'key':c.key,'meta':c.meta} for c in curves]
        # A changed input/header invalidates the new journal results only.
        sig=stable_hash({'schema':JOURNAL_SCHEMA,'renderer_version':__version__,
                         'config':cfg.data,'curves':signatures,
                         'audit':[{k:v for k,v in r.items() if k!='status'} for r in audit]})
        state_path=cfg.output/'journal_state.json'
        review_path=cfg.output/'journal_documentation_artifacts_review.zip'
        if not force and state_path.is_file():
            try:
                state=read_json(state_path)
                if state.get('signature')==sig and verify_inventory(cfg.output,cfg.output/'manifest'/'journal_inventory.csv') and review_path.is_file() and sha256(review_path)==state.get('review_sha256'):
                    LOGGER.info('Journal outputs fresh; all existing figures/tables/bundle reused')
                    return cfg.output/'JOURNAL_ANALYSIS_SUMMARY.md'
            except (OSError,ValueError):pass
        stage=Path(tempfile.mkdtemp(prefix='.journal-build-',dir=cfg.output))
        try:
            fig1,met1=render_paired(jetson,cfg,stage/'pico_vs_tek_psd')
            fig2,met2=render_platforms(jetson,hailo,cfg,stage/'cross_platform_psd')
            fig3=render_extra_setup_comparisons(jetson,cfg,stage/'pico_vs_tek_psd')
            figures=fig1+fig2+fig3
            _snippets(stage,figures)
            export_csv(stage/'manifest'/'input_audit.csv',audit)
            write_json(stage/'manifest'/'input_audit.json',audit)
            metadata=[dict(key=c.key,workload_id=c.workload_id,label=c.label,platform=c.platform,
                setup=c.setup,signal=c.signal,basis=c.basis,window=c.window,metadata=c.meta,per_run=c.per_run) for c in curves]
            write_json(stage/'manifest'/'spectral_sources.json',metadata)
            failed=[r for r in audit if r.get('status') in ['unavailable','skipped_invalid','source_missing','no_native_rate_runs']]
            status='completed' if curves and not failed else ('completed_with_skips' if curves else 'no_usable_spectra')
            manifest={'tool_version':__version__,'created_utc':utc_now_iso(),'signature':sig,
                      'analysis_schema':JOURNAL_SCHEMA,'status':status,'config_path':str(cfg.path),
                      'config':cfg.data,'package_versions':package_versions(),
                      'jetson_workloads':sorted({c.workload_id for c in jetson}),
                      'additional_platforms':sorted({c.platform for c in hailo}),
                      'figure_count':len(figures),'series_count':len(curves),
                      'legacy_result_trees_written':False,'legacy_numerical_commands_called':False,
                      'review_contains_raw_data':False,'review_contains_full_resolution_npz':False,
                      'metric_basis':'Full native bins for metrics; sampled curves only for display/review',
                      'claim_scope':'descriptive spectral comparison, not independently calibrated bandwidth or absolute accuracy',
                      'skipped_inputs':failed}
            write_json(stage/'manifest'/'journal_manifest.json',manifest)
            methods=Path(__file__).resolve().parents[1]/'JOURNAL_METHODS.md'
            if methods.is_file():shutil.copy2(methods,stage/'JOURNAL_METHODS.md')
            lines=['# Journal PSD analysis','',f'- Tool: `{__version__}`',f'- Status: **{status}**',
                f'- Jetson workloads with native Tek/Pico spectra: {len(manifest["jetson_workloads"])}',
                f'- Additional platform series: {len(hailo)}',f'- Figures: {len(figures)}',
                f'- Input records unavailable/skipped: {len(failed)}','',
                '## Start with these figures','',
                '`pico_vs_tek_psd/figures/pico_cross_workload_current_cumulative.pdf`',
                '`pico_vs_tek_psd/figures/tek_vs_pico_current_cumulative_overlay.pdf`',
                '`pico_vs_tek_psd/figures/tek_vs_pico_current_conditional_cumulative_0_77khz.pdf`',
                '`pico_vs_tek_psd/figures/tek_vs_pico_current_cumulative_difference.pdf`','',
                'Individual workload overlays and absolute PSDs are under `pico_vs_tek_psd/figures/per_workload/`.',
                'Platform results and their comparison limits are under `cross_platform_psd/`.','',
                '## Data and interpretation','',
                'Existing native Jetson spectra were read, not remeasured or regenerated. No PARMA result or Common-Reference cache was modified.',
                'Additional legacy power NPYs use their declared rate and exact inclusive YAML sample window, an energy consistency check, and memory-bounded native Welch.',
                'Full windows and duration-matched prefixes remain separate. Independent physical runs are not concatenated. Missing idle is not replaced with zero or Jetson idle.',
                'All frequency percentiles are explicitly labelled as per-run medians or derived from the pointwise-median curve. They need not be equal.',
                'The 77-kHz marker is not a hard cutoff. Conditional low-band CDFs distinguish shape changes from full-band denominator changes.',
                'Cross-platform plots are exploratory unless measurement boundary, setup, precision, model and operating state are independently matched.','',
                '## Review bundle','',
                'The compact ZIP includes PDF/PNG, exact numeric tables, LaTeX snippets, source metadata and thinned review curves. No raw waveform or NPZ cache is copied.',
                'Native aggregate files remain local and are identified by their source metadata. This is a review bundle, not a raw-data archive.']
            if failed:
                lines+=['','## Inputs requiring attention','']
                for r in failed:lines.append(f"- `{r.get('source_path','')}`: {r.get('reason',r['status'])}")
            (stage/'JOURNAL_ANALYSIS_SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
            (stage/'REVIEW_BUNDLE_NOTICE.md').write_text('This compact review bundle omits raw waveforms and full-resolution NPZ arrays.\n'
                'It contains exact numerical summary tables and display-sampled curves. See manifest/spectral_sources.json for source identities.\n'
                'Its inventory describes only the files actually included and excludes the inventory itself.\n',encoding='utf-8')
            inv=_inventory(stage)
            export_csv(stage/'manifest'/'journal_inventory.csv',inv,('path','size_bytes','sha256'))
            if not verify_inventory(stage,stage/'manifest'/'journal_inventory.csv'):
                raise RuntimeError('Internal journal inventory verification failed')
            tmpzip=cfg.output/'.journal_review_pending.zip'
            with zipfile.ZipFile(tmpzip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                for p in sorted(stage.rglob('*')):
                    if p.is_file():z.write(p,p.relative_to(stage).as_posix())
            with zipfile.ZipFile(tmpzip) as z:
                if z.testzip():raise RuntimeError('Journal ZIP integrity test failed')
            # Publish only owned journal artifact branches, after successful generation.
            # A failure before here leaves the prior artifact directories/bundle intact.
            for child in list(stage.iterdir()):
                dest=cfg.output/child.name
                if dest.is_dir():shutil.rmtree(dest)
                elif dest.exists():dest.unlink()
                os.replace(child,dest)
            os.replace(tmpzip,review_path)
            digest=sha256(review_path)
            review_path.with_suffix('.zip.sha256').write_text(digest+'  '+review_path.name+'\n',encoding='ascii')
            write_json(state_path,{'signature':sig,'tool_version':__version__,'status':status,'review_sha256':digest})
            LOGGER.info('Journal analysis %s. Summary: %s',status,cfg.output/'JOURNAL_ANALYSIS_SUMMARY.md')
            LOGGER.info('Compact journal review: %s (%.2f MiB)',review_path,review_path.stat().st_size/1048576)
            if not curves:raise RuntimeError('No usable spectra; diagnostic report written, no synthetic results generated')
            return cfg.output/'JOURNAL_ANALYSIS_SUMMARY.md'
        finally:
            shutil.rmtree(stage,ignore_errors=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Isolated Pico/Tek and cross-platform journal PSD artifacts')
    parser.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[1]/'config_journal.yaml')
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--force',action='store_true',help='Rebuild journal-only caches, never old scope/CR results')
    parser.add_argument('--artifacts-only',action='store_true',help='Use journal caches; no NPY waveform reanalysis')
    parser.add_argument('--verbose',action='store_true')
    args=parser.parse_args(argv)
    try:
        cfg=load_journal_config(args.config,args.output_root)
        run_journal(cfg,force=args.force,artifacts_only=args.artifacts_only,verbose=args.verbose)
        return 0
    except Exception as e:
        LOGGER.exception('Journal analysis failed: %s',e)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
