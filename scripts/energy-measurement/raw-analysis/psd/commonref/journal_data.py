"""Read-only adapters. All new numeric caches live below journal_artifacts/cache."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import gc
import csv
import hashlib
import math
import os
import re
import zipfile
import numpy as np
from .utils import LOGGER, load_yaml, read_json, write_json, stable_hash, normalise_for_json
from .journal_signal import check_spectrum, metrics, welch_chunks, npy_chunks

JOURNAL_SCHEMA = 1
BANDS = [('0–100 Hz', 0., 100.), ('100 Hz–1 kHz', 100., 1000.),
         ('1–10 kHz', 1000., 10000.), ('10–77 kHz', 10000., 77000.),
         ('77–500 kHz', 77000., 500000.), ('500 kHz–2.5 MHz', 500000., 2500000.)]
FINE_WINDOWS = [('0–1 kHz', 0., 1000.), ('1–8 kHz', 1000., 8000.),
                ('8–16 kHz', 8000., 16000.), ('25–35 kHz', 25000., 35000.),
                ('300–700 kHz', 300000., 700000.)]


def safe_name(s: str) -> str:
    return re.sub('[^a-zA-Z0-9_-]+', '_', str(s)).strip('_') or 'unknown'


def identity(path: Path, digest: bool = False) -> dict[str, Any]:
    st = path.stat()
    r = {'path': str(path.resolve()), 'size': st.st_size, 'mtime_ns': st.st_mtime_ns,
         'ctime_ns': st.st_ctime_ns, 'inode': st.st_ino, 'device': st.st_dev}
    if digest:
        h = hashlib.sha256()
        with path.open('rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
        r['sha256'] = h.hexdigest()
    return r


def atomic_npz(path: Path, arrays: dict[str, np.ndarray]):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    try:
        with temp.open('wb') as f: np.savez_compressed(f, **arrays)
        os.replace(temp, path)
    finally:
        if temp.exists(): temp.unlink()


def arrays_from_npz(path: Path):
    with np.load(path, allow_pickle=False) as data: return {key: data[key] for key in data.files}


@dataclass
class JournalConfig:
    path: Path
    output: Path
    multi_root: Path
    multi_config: Path
    data: dict[str, Any]
    rate: int
    nperseg: int
    minimum_segments: int
    bandwidth: float
    max_points: int
    matched_duration: float
    idle_guard: float
    energy_tolerance: float


def load_journal_config(path: Path, output_override: Path | None = None) -> JournalConfig:
    path = path.expanduser().resolve()
    data = load_yaml(path)
    def resolve(value):
        p = Path(value).expanduser()
        return (p if p.is_absolute() else path.parent / p).resolve()
    mr = resolve(data['multi_workload_output_root'])
    out = resolve(output_override or data.get('output_root', mr / 'journal_artifacts'))
    mc = resolve(data['multi_workload_config'])
    protected = [mr / p for p in ['paper_artifacts', 'psd', 'common_reference', 'direct_rate_validation']]
    if not isinstance(data.get('npy_sources', []), list): raise ValueError('npy_sources must be a list')
    for source in data.get('npy_sources', []):
        if not isinstance(source, dict): raise ValueError('npy_sources entries must be mappings')
        source['root'] = str(resolve(source['root']))
        protected.append(Path(source['root']))
        if source.get('unit') != 'W' or source.get('signal') != 'power':
            raise ValueError('Legacy NPY adapter requires explicitly configured signal: power, unit: W')
        if source.get('contract') != 'legacy_results_energy_checked':
            raise ValueError('Unsupported NPY contract')
    if out == mr or out in mr.parents:
        raise ValueError('Journal output cannot overwrite the existing multi-workload root')
    for source in protected:
        if out == source or out in source.parents or source in out.parents:
            raise ValueError(f'Journal output overlaps a protected source/result tree: {source}')
    psd = data.get('psd', {})
    rate, n = int(psd.get('native_rate_sps', 5000000)), int(psd.get('nperseg', 1048576))
    minseg, bw = int(psd.get('minimum_welch_segments', 2)), float(psd.get('nominal_bandwidth_hz', 77000.))
    duration, guard, tolerance = [float(data.get(k, d)) for k, d in
        [('matched_duration_s', 10.), ('idle_guard_s', .1), ('energy_check_tolerance_pct', .5)]]
    if rate <= 0 or n < 64 or n % 2 or minseg < 1 or not 0 < bw < rate / 2:
        raise ValueError('Invalid journal PSD settings')
    if not all(math.isfinite(v) for v in [duration, guard, tolerance]) or min(duration, tolerance) <= 0 or guard < 0:
        raise ValueError('Invalid duration, guard or energy consistency tolerance')
    return JournalConfig(path, out, mr, mc, data, rate, n, minseg, bw,
                         max(500, int(data.get('plot_max_points', 6000))), duration, guard, tolerance)


@dataclass
class Curve:
    workload_id: str
    label: str
    platform: str
    setup: str
    signal: str
    basis: str
    window: str
    f: np.ndarray
    p: np.ndarray
    meta: dict[str, Any] = field(default_factory=dict)
    per_run: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self):
        return safe_name('__'.join([self.platform, self.workload_id, self.setup, self.signal, self.basis, self.window]))


def _specs(cfg: JournalConfig) -> list[dict[str, Any]]:
    if cfg.multi_config.is_file():
        payload = load_yaml(cfg.multi_config)
        specs = payload.get('workloads', [])
    elif (cfg.multi_root / 'multi_workload_manifest.json').is_file():
        specs = read_json(cfg.multi_root / 'multi_workload_manifest.json').get('config', {}).get('workloads', [])
    else:
        specs = []
        for p in sorted((cfg.multi_root / 'psd' / 'per_workload').glob('*/psd_metrics.json')):
            m = read_json(p)
            specs.append({'id': p.parent.name, 'label': m.get('workload_label', p.parent.name)})
    return [dict(s, id=s.get('id', s.get('workload_id'))) for s in specs
            if s.get('id', s.get('workload_id')) and str(s.get('enabled', 'auto')).lower() != 'false']


def load_jetson(cfg: JournalConfig):
    """Use both-source NATIVE spectra already computed by v0.8.x, never a 1-MS/s CR cache."""
    curves, audit = [], []
    for spec in _specs(cfg):
        wid = str(spec['id']); label = str(spec.get('label', wid))
        root = cfg.multi_root / 'psd' / 'per_workload' / wid
        npz, jp = root / 'cross_workload_psd_summary.npz', root / 'psd_metrics.json'
        row = {'platform': 'Jetson Orin NX', 'workload_id': wid, 'label': label, 'source_path': str(npz)}
        try:
            before = [identity(npz), identity(jp, True)]
            m, arrays = read_json(jp), arrays_from_npz(npz)
            if not isinstance(m, dict): raise ValueError('PSD metrics JSON is not an object')
            if float(m.get('comparison_rate_sps', 0)) != cfg.rate:
                raise ValueError('Cached PSD is not at the configured native comparison rate')
            pending = []
            for setup in ['tek', 'pico']:
                for signal, unit in [('current', 'a2'), ('power', 'w2')]:
                    fkey = f'{setup}_{signal}_frequencies_hz'
                    f = np.asarray(arrays[fkey], dtype=np.float64)
                    if abs(f[0]) > 1e-9 or abs(f[-1] - cfg.rate / 2) > 1e-6:
                        raise ValueError('Native frequency support does not span DC to Nyquist')
                    active = arrays[f'{setup}_{signal}_active_psd_{unit}_per_hz']
                    idle = arrays.get(f'{setup}_{signal}_idle_psd_{unit}_per_hz')
                    excess = arrays.get(f'{setup}_{signal}_excess_psd_{unit}_per_hz')
                    if idle is not None and excess is not None and not np.allclose(
                            np.maximum(active - idle, 0.), excess, rtol=1e-10, atol=1e-24):
                        raise ValueError('Stored excess disagrees with active-minus-idle')
                    for basis, p in [('active', active), ('idle', idle), ('excess', excess if idle is not None else None)]:
                        if p is None: continue
                        f, p = check_spectrum(f, p)
                        per = []
                        if basis == 'excess':
                            for r in m.get('per_run_metrics', []):
                                rr = {'run': r.get('run')}
                                for q in [50, 90, 95, 99]: rr[f'f{q}_hz'] = r.get(f'{setup}_{signal}_f{q}_hz')
                                rr['variance_integral'] = r.get(f'{setup}_{signal}_integral')
                                per.append(rr)
                        meta = {'origin': 'existing_native_multi_workload_aggregate', 'inputs': before,
                            'upstream_signature': m.get('signature'), 'source_rate_sps': cfg.rate,
                            'physical_runs': m.get('valid_pairs'), 'external_idle_runs': m.get('external_idle_pairs'),
                            'external_idle_total_duration_s': m.get('external_idle_total_duration_s'),
                            'active_duration_s': m.get('active_duration_s'),
                            'duration_note': 'Existing full records; typically 10 s. Duration not inferred from rate.',
                            'measurement_boundary': 'jetson_dc_module_input',
                            'precision': spec.get('precision', 'unspecified'),
                            'family': spec.get('family', 'unspecified'),
                            'setup_id': 'pico_ina225' if setup == 'pico' else 'tek_tcp0030a',
                            'power_origin': 'current_dependent_voltage_model' if signal == 'power' else 'calibrated_current',
                            'aggregation': 'pointwise_median_PSD; excess=difference_of_medians_clipped_at_zero',
                            'zero_offset_policy': 'unchanged_upstream_audit; no new fit or correction',
                            'independent_accuracy_validation': False}
                        # Duration is available in the scope cross-rate summary on some runs.
                        scopepath = spec.get('scope_config')
                        if scopepath and Path(scopepath).is_file():
                            sc = load_yaml(Path(scopepath))
                            meta['scope_config_snapshot'] = sc
                            pair_csv = Path(sc['output_root']) / f'{cfg.rate}Sps' / 'scope_comparison' / 'pair_metrics.csv'
                            if pair_csv.is_file():
                                with pair_csv.open(newline='', encoding='utf-8') as h:
                                    pr = list(csv.DictReader(h))
                                wanted = {str(r.get('run')) for r in m.get('per_run_metrics', [])}
                                vals = []
                                for r in pr:
                                    if wanted and str(r.get('run')) not in wanted: continue
                                    try: val = float(r[f'{setup}_nominal_duration_s'])
                                    except (ValueError, KeyError, TypeError): continue
                                    if math.isfinite(val) and val > 0: vals.append(val)
                                if vals and (not wanted or len(vals) == len(wanted)):
                                    meta['active_duration_s'] = float(np.median(vals))
                                    meta['duration_min_s'], meta['duration_max_s'] = min(vals), max(vals)
                                    meta['duration_note'] = 'Full-record durations from upstream paired-run metrics'
                                    meta['duration_source'] = identity(pair_csv, True)
                        pending.append(Curve(wid, label, 'Jetson Orin NX', setup, signal, basis,
                                             'existing_full_record', f, p, meta, per))
            if before != [identity(npz), identity(jp, True)]:
                raise RuntimeError('Source files changed during read; retry after upstream run finishes')
            curves.extend(pending)
            row.update(status='reused_native_spectra', physical_runs=m.get('valid_pairs'), reason='no_raw_read')
            LOGGER.info('Journal: %s — reused native Tek AND Pico PSDs; no scope/CR recalculation', label)
        except (OSError, ValueError, KeyError, RuntimeError, EOFError, zipfile.BadZipFile) as e:
            row.update(status='unavailable', reason=f'{type(e).__name__}: {e}')
            LOGGER.warning('Journal skipped %s: %s', wid, e)
        audit.append(row)
    return curves, audit


def _rate(name: str) -> int | None:
    m = re.fullmatch(r'(\d+)(?:Sps)?', name)
    return int(m[1]) if m else None


def _run_metadata(run: Path, rate: int):
    npy, yml = run / 'oscilloscope.npy', run / 'results.yaml'
    data = load_yaml(yml)
    osc = data['oscilloscope_results']; res = osc['results']
    fs = float(osc['sample_rate'])
    if fs != rate: raise ValueError(f'Wrong sample rate: YAML {fs}, requested {rate}')
    raw_idx = res['start_stop_idx']
    if len(raw_idx) != 2 or any(isinstance(v, bool) or int(v) != v for v in raw_idx):
        raise ValueError('Invalid integer start_stop_idx')
    start, last = map(int, raw_idx)
    duration, energy = float(res['duration']), float(res['energy'])
    if not all(math.isfinite(x) for x in [duration, energy]) or duration <= 0 or energy <= 0:
        raise ValueError('Nonpositive/nonfinite duration or energy')
    a = np.load(npy, mmap_mode='r', allow_pickle=False)
    if a.ndim != 1 or a.dtype.kind not in 'fiu' or not 0 <= start <= last < a.size:
        raise ValueError('Invalid NPY signal shape, type or sample window')
    rows = int(a.size); del a
    if abs((last - start + 1) / fs - duration) > max(1.01 / fs, 1e-8):
        raise ValueError('YAML duration does not match inclusive start/stop indices')
    # This establishes only the declared acquisition-suite format, not physical calibration.
    explicit_unit = data.get('signal_unit', osc.get('unit', osc.get('signal_unit')))
    if explicit_unit and str(explicit_unit).lower() not in ['w', 'watt', 'watts', 'power_w']:
        raise ValueError(f'NPY unit conflicts with declared power contract: {explicit_unit}')
    return npy, yml, start, last + 1, duration, energy, rows, data


def _cached_npy_run(cfg: JournalConfig, source: dict, run: Path, *, force=False, cached_only=False):
    npy, yml, start, stop, duration, energy, rows, source_meta = _run_metadata(run, cfg.rate)
    facts = [identity(npy), identity(yml, True)]
    numeric_settings = {'rate':cfg.rate, 'nperseg':cfg.nperseg, 'min_segments':cfg.minimum_segments,
        'matched_s':cfg.matched_duration, 'idle_guard_s':cfg.idle_guard, 'energy_tol_pct':cfg.energy_tolerance}
    signature = stable_hash({'schema':JOURNAL_SCHEMA, 'settings':numeric_settings, 'inputs':facts})
    target = cfg.output / 'cache' / 'npy' / safe_name(source['id']) / signature
    mp, ap = target / 'metrics.json', target / 'spectra.npz'
    if not force and mp.is_file() and ap.is_file():
        try:
            m, arrays = read_json(mp), arrays_from_npz(ap)
            if m.get('signature') == signature:
                for key in [k for k in arrays if k.endswith('_psd')]:
                    check_spectrum(arrays['frequency_hz'], arrays[key])
                return arrays, m, 'cached'
        except (ValueError, KeyError, OSError, EOFError, zipfile.BadZipFile): pass
    if cached_only: raise ValueError('Journal cache missing/stale; run without --artifacts-only once')
    LOGGER.info('Journal Hailo/native NPY: %s (%g s) — power only, no Jetson calibration', run, duration)
    f, active, active_meta = welch_chunks(npy_chunks(npy, start, stop), cfg.rate, cfg.nperseg, cfg.minimum_segments)
    relative_errors = {kind: 100. * (active_meta[f'{kind}_integral'] / energy - 1.) for kind in ['rectangle', 'trapezoid']}
    if min(abs(v) for v in relative_errors.values()) > cfg.energy_tolerance:
        raise ValueError(f'NPY power integral conflicts with YAML energy: {relative_errors}')
    if active_meta['mean'] <= 0: raise ValueError('Nonpositive active mean power')
    arrays = {'frequency_hz': f, 'full_active_psd': active}
    m = {'signature':signature, 'inputs':facts, 'source_metadata': source_meta,
        'source_rate_sps': cfg.rate, 'declared_input_unit':'W', 'input_contract':'legacy_results_energy_checked',
        'current_inferred':False, 'jetson_voltage_model_applied':False, 'double_calibration_applied':False,
        'run':run.name, 'yaml_energy_j':energy, 'energy_check_errors_pct':relative_errors,
        'energy_check_role':'internal_consistency_only_not_independent_accuracy_validation',
        'start_idx':start, 'stop_exclusive':stop, 'total_samples':rows,
        'full':active_meta, 'idle_status':'absent_or_too_short',
        'windows':{'full_record': {'active_psd':'full_active_psd', 'duration_s':duration}},
        'algorithm_settings':numeric_settings}
    idle_stop = max(0, start - int(round(cfg.idle_guard * cfg.rate)))
    try:
        if idle_stop <= 0: raise ValueError('No pre-window samples')
        fi, idle, idle_meta = welch_chunks(npy_chunks(npy, 0, idle_stop), cfg.rate, cfg.nperseg, cfg.minimum_segments)
        if not np.array_equal(f, fi): raise ValueError('Idle/active frequency grids differ')
        arrays['idle_psd'] = idle
        m.update(idle_status='same_record_prebenchmark', idle=idle_meta)
    except ValueError as e:
        # A malformed existing prefix (NaN etc.) must not silently become zero idle.
        m['idle_reason'] = str(e)
    matched_samples = int(round(cfg.matched_duration * cfg.rate))
    if stop - start >= matched_samples:
        if stop - start == matched_samples:
            arrays['matched_active_psd'] = active
            matched_meta = dict(active_meta)
        else:
            _, matched, matched_meta = welch_chunks(npy_chunks(npy, start, start + matched_samples),
                                                    cfg.rate, cfg.nperseg, cfg.minimum_segments)
            arrays['matched_active_psd'] = matched
        m['matched'] = matched_meta
        m['windows']['matched_prefix'] = {'active_psd':'matched_active_psd', 'duration_s':cfg.matched_duration}
    if facts != [identity(npy), identity(yml, True)]:
        raise RuntimeError('NPY/YAML changed during processing; result not published')
    atomic_npz(ap, arrays); write_json(mp, m)
    return arrays, m, 'computed'


def load_npy_platforms(cfg: JournalConfig, *, force=False, cached_only=False):
    curves, audit = [], []
    for source in cfg.data.get('npy_sources', []):
        if not source.get('enabled', True): continue
        root = Path(source['root'])
        if not root.is_dir():
            audit.append({'platform':source['platform_label'], 'source_path':str(root),
                          'status':'source_missing', 'reason':'Optional platform not yet available'})
            continue
        # Discover only declared native-rate directories. Do not traverse or analyse
        # archived invalid runs and .part/.tmp files as valid measurements.
        rate_dirs = [p for p in root.rglob('*') if p.is_dir() and _rate(p.name) == cfg.rate
            and not any(s.startswith(('.', 'invalid', '_')) for s in p.relative_to(root).parts)]
        groups: dict[str, list[tuple[dict, dict]]] = {}
        if not rate_dirs:
            audit.append({'platform':source['platform_label'], 'source_path':str(root),
                          'status':'no_native_rate_runs', 'reason':f'No native {cfg.rate}-S/s directories found'})
        ambiguous_parents = {rd.parent for rd in rate_dirs if sum(p.parent == rd.parent for p in rate_dirs) > 1}
        for parent in sorted(ambiguous_parents):
            audit.append({'platform':source['platform_label'], 'source_path':str(parent),
                          'status':'skipped_invalid', 'reason':'Ambiguous duplicate native-rate directories; no double counting'})
        for rd in sorted(rate_dirs):
            if rd.parent in ambiguous_parents: continue
            wid = str(rd.parent.relative_to(root))
            if wid == '.': wid = 'workload'
            if wid.lower() in ('idle', 'zero', 'calibration'): continue
            for run in sorted((x for x in rd.iterdir() if x.is_dir() and x.name.isdigit()), key=lambda x: int(x.name)):
                row = {'platform':source['platform_label'], 'workload_id':wid, 'run':run.name,
                       'source_path':str(run), 'rate_sps':cfg.rate}
                try:
                    arrays, m, status = _cached_npy_run(cfg, source, run, force=force, cached_only=cached_only)
                    groups.setdefault(wid, []).append((arrays, m))
                    row.update(status=status, duration_s=m['full']['duration_s'], idle_status=m['idle_status'],
                               idle_reason=m.get('idle_reason',''),
                               energy_check_max_abs_pct=max(abs(v) for v in m['energy_check_errors_pct'].values()))
                except (OSError, ValueError, KeyError, TypeError, RuntimeError, EOFError, zipfile.BadZipFile) as e:
                    row.update(status='skipped_invalid', reason=f'{type(e).__name__}: {e}')
                    LOGGER.warning('Journal NPY skipped %s: %s', run, e)
                audit.append(row)
        for wid, runs in groups.items():
            override = source.get('workload_metadata', {}).get(wid, {})
            label = override.get('label', f'{source["platform_label"]} / {wid}')
            for window, akey in [('full_record', 'full_active_psd'), ('matched_prefix', 'matched_active_psd')]:
                subset = [(a, m) for a, m in runs if akey in a]
                if not subset: continue
                f = subset[0][0]['frequency_hz']
                if any(not np.array_equal(f, a['frequency_hz']) for a, m in subset):
                    raise ValueError('Fixed native Welch grids unexpectedly differ')
                for basis in ['active', 'idle', 'excess']:
                    cohort = subset if basis == 'active' else [(a,m) for a,m in subset if 'idle_psd' in a]
                    if not cohort: continue
                    active_median = np.median(np.stack([a[akey] for a,m in cohort]), axis=0)
                    if basis == 'active': p = active_median
                    else:
                        idle_median = np.median(np.stack([a['idle_psd'] for a,m in cohort]), axis=0)
                        p = idle_median if basis == 'idle' else np.maximum(active_median - idle_median, 0.)
                    per = []
                    for a, m in cohort:
                        pp = a[akey] if basis == 'active' else (a['idle_psd'] if basis == 'idle' else np.maximum(a[akey] - a['idle_psd'], 0.))
                        per.append(dict(metrics(f, pp, cfg.bandwidth), run=m['run']))
                    durations = [m['windows'][window]['duration_s'] for a,m in cohort]
                    boundary = override.get('measurement_boundary', source.get('measurement_boundary', 'unspecified'))
                    precision = override.get('precision', source.get('precision', 'unspecified'))
                    meta = {'origin':'legacy_power_npy_native_welch', 'physical_runs':len(cohort),
                        'source_rate_sps':cfg.rate, 'nperseg':cfg.nperseg, 'frequency_resolution_hz':cfg.rate / cfg.nperseg,
                        'active_duration_s':float(np.median(durations)), 'duration_min_s':min(durations), 'duration_max_s':max(durations),
                        'measurement_boundary':boundary, 'precision':precision, 'family':override.get('family', wid),
                        'setup_id':source.get('setup_id', 'unspecified'), 'setup_evidence':source.get('setup_evidence', 'unspecified'),
                        'comparison_status':'exploratory_not_model_or_boundary_matched',
                        'power_origin':'stored_power_not_recalibrated', 'idle_source':'same_run_prebenchmark' if basis != 'active' else 'not_subtracted',
                        'aggregation':'equal_physical_run_pointwise_median; no concatenation',
                        'window_definition':'YAML active window' if window == 'full_record' else 'first configured seconds of YAML active window',
                        'independent_accuracy_validation':False,
                        'source_cache_signatures':[m['signature'] for a,m in cohort],
                        'inputs':[x for a,m in cohort for x in m['inputs']],
                        'idle_available_runs':sum('idle_psd' in a for a,m in subset)}
                    curves.append(Curve(safe_name(wid), label, source['platform_label'], 'pico', 'power',
                                        basis, window, f, p, meta, per))
                    gc.collect()
    return curves, audit
