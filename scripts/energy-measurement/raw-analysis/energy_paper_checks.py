#!/usr/bin/env python3
"""Gezielte Offlinepruefungen zum Energy-Paper; Eingabedaten bleiben unveraendert.

Default: alle sechs dokumentierten Scope-Workloads bei 5 MS/s, Zielraten
2/9.4/16 kS/s; dazu FP16-IDs 0..14. Ein unabhaengiger Sensitivitaetscheck,
keine behauptete bitgenaue Wiederholung der urspruenglichen Paper-Pipeline.
Python >= 3.10. Abhaengigkeiten: numpy scipy soxr pyarrow pyyaml.
"""
from __future__ import annotations

import argparse
import csv
import gc
import importlib.metadata
import itertools
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import traceback
import zipfile

VERSION = "1.0.1"
FS_NATIVE = 5_000_000
FS_REDUCED = 1_000_000
CHUNK = 1_000_000
WORKLOADS = ("gemmfp32", "gemmint8", "yolofp32", "yoloint8", "gemma3-4b", "resnet50")
EXPECTED_PAIRS = {w: (9 if w == "resnet50" else 10) for w in WORKLOADS}
PAPER_FP16_IDS = tuple(range(2, 15))
ALL_FP16_IDS = tuple(range(15))
FULL_RATES = (50, 85, 150, 240, 400, 680, 1200, 2000, 2500, 3300,
              5500, 9400, 16000, 25000, 45000, 80000, 100000, 125000, 160000)
FULL_DURATIONS = (.02, .05, .1, .2, .5, 1., 2., 5., 10.)
PICO_GAIN = 1.99000512058047
PICO_OFFSET_RAW = .0004272598504
V_INTERCEPT = 19.062607082705
V_SLOPE = -.07444582
YOLO_TEK_OFFSET_A = .111917
SOURCE_BASE = ("https://github.com/Keff789/onnx-splitpoint-results/blob/"
               "c9c867d0a90bb62b764579322a135b60157bd8db/energy-measurement/")
SOURCE_URLS = [
    SOURCE_BASE + "PSD_Analysis_multi_workload_documentation_artifacts/multi_workload_manifest.json",
    SOURCE_BASE + "PSD_Analysis_journal_documentation_artifacts/manifest/spectral_sources.json",
    SOURCE_BASE + "Energy_Paper_TIM_KnowledgeBase_2026-09-30.md",
    "https://github.com/PercyJW-2/masterarbeit-helper-scripts/blob/4a9fe2daca4012f0c578ebf9e37d37f54163285f/power_calculations/src/main.rs",
    "https://github.com/PercyJW-2/masterarbeit-helper-scripts/blob/27a927fc089d49d2f1ea8104bf863a9bec1a0011/power_calculations/src/output_types.rs",
    "https://github.com/PercyJW-2/urecs-data-collector/blob/9079d79574fa683f98a10ee0e0537931d8c3bd5b/src/tekhsi_osc_communication.rs",
    "https://github.com/PercyJW-2/urecs-data-collector/blob/9079d79574fa683f98a10ee0e0537931d8c3bd5b/src/pico_osc_communication.rs",
    "https://github.com/PercyJW-2/masterarbeit-helper-scripts/blob/27a927fc089d49d2f1ea8104bf863a9bec1a0011/measurement_suite.py",
]


def log(message):
    print(time.strftime("[%H:%M:%S] ") + str(message), flush=True)


def dependencies():
    global np, soxr, pq, yaml, signal
    missing = []
    for name in ("numpy", "scipy", "soxr", "pyarrow", "yaml"):
        try:
            __import__(name)
        except ImportError:
            missing.append("pyyaml" if name == "yaml" else name)
    if missing:
        raise RuntimeError("Fehlende Python-Pakete: " + ", ".join(missing) +
                           "\nIm verwendeten Python installieren: " + sys.executable +
                           " -m pip install " + " ".join(missing))
    import numpy as np
    from scipy import signal
    import soxr
    import pyarrow.parquet as pq
    import yaml


def json_clean(value):
    if isinstance(value, dict):
        return {str(k): json_clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_clean(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return json_clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(json_clean(value), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        f.write("\n")
    tmp.replace(path)


def read_small_json(path, limit=4_000_000):
    if not path.is_file() or path.stat().st_size > limit:
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def file_stamp(path):
    st = path.stat()
    return {"path": str(path.resolve()), "bytes": st.st_size, "mtime_ns": st.st_mtime_ns}


def write_csv(path, rows):
    rows = list(rows)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        if not keys:
            f.write("status\nno_rows\n")
            return
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in json_clean(row).items()})


def directory_overview(path, limit=40):
    """Kleine Pfaddiagnose; liest ausschliesslich Verzeichniseintraege."""
    result = {"path": str(path), "entries": [], "listing_truncated": False}
    try:
        with os.scandir(path) as entries:
            for index, entry in enumerate(entries):
                if index >= limit:
                    result["listing_truncated"] = True
                    break
                kind = "symlink" if entry.is_symlink() else ("directory" if entry.is_dir() else "file")
                result["entries"].append({"name": entry.name, "type": kind})
        result["entries"].sort(key=lambda x: x["name"])
        result["status"] = "readable"
    except FileNotFoundError:
        result["status"] = "missing"
    except NotADirectoryError:
        result["status"] = "not_a_directory"
    except OSError as exc:
        result.update(status="access_error", error=f"{type(exc).__name__}: {exc}")
    return result


def scope_rate_from_directory(name):
    """Nur vollstaendige Ratenbezeichnungen; kleine reine Zahlen bleiben Run-IDs."""
    token = name.replace("_", "").replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)([kKmMgG]?)([sS][pP][sS])?", token)
    if not match:
        return None
    value = float(match.group(1)) * {"": 1, "k": 1e3, "m": 1e6, "g": 1e9}[match.group(2).lower()]
    if not math.isfinite(value) or value <= 0:
        return None
    if not match.group(2) and not match.group(3):
        # Keine Jahres-/Sessionordner (z.B.2026) als fremde Rate abschneiden.
        # Die hohen Raten sind in den publizierten Scope-Metadaten belegt.
        if value not in {FS_NATIVE, 1_000_000, 25_000_000, 125_000_000, 250_000_000}:
            return None
    return value


def scope_file_identity(path):
    """Analyseexport *_ID oder Collector-Datei unmittelbar im numerischen Run-Ordner."""
    for source, stem in (("tek", "tek_hsi"), ("pico", "usb_osc_data")):
        match = re.fullmatch(re.escape(stem) + r"_(\d+)\.parquet", path.name)
        if match:
            return source, int(match.group(1)), "numbered_filename"
        if path.name == stem + ".parquet" and re.fullmatch(r"\d+", path.parent.name):
            if scope_rate_from_directory(path.parent.name) is None:
                return source, int(path.parent.name), "immediate_run_directory"
    return None


def scan_scope_workload(root):
    """Begrenzte Namenssuche, keine Parquet-Inhalte; fremde Rateebenen werden nicht betreten."""
    candidates = {"tek": {}, "pico": {}}
    diag = {"root": directory_overview(root), "max_depth": 4, "max_directories": 128,
            "max_entries": 10000, "directories_visited": 0, "entries_seen": 0,
            "rate_directories": [], "access_errors": [], "skipped_symlinks": [],
            "unclassified_file_examples": [], "unlabelled_numeric_directories": [],
            "ambiguous_candidates": [], "scan_complete": True}
    queue = [(root, 0, None)]
    while queue:
        current, depth, rate_dir = queue.pop(0)
        if diag["directories_visited"] >= diag["max_directories"]:
            diag["scan_complete"] = False
            break
        diag["directories_visited"] += 1
        try:
            entries = []
            with os.scandir(current) as iterator:
                for entry in iterator:
                    diag["entries_seen"] += 1
                    if diag["entries_seen"] > diag["max_entries"]:
                        diag["scan_complete"] = False
                        break
                    entries.append(entry)
            if not diag["scan_complete"]:
                break
            for entry in sorted(entries, key=lambda e: e.name):
                path = Path(entry.path)
                if entry.is_symlink():
                    if len(diag["skipped_symlinks"]) < 40:
                        diag["skipped_symlinks"].append(str(path))
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.startswith(".") or entry.name in {"cache", "caches", "venv", "__pycache__"}:
                        continue
                    rate = scope_rate_from_directory(entry.name)
                    if rate is not None:
                        diag["rate_directories"].append({"path": str(path), "rate_sps": rate,
                                                         "selected": rate == FS_NATIVE})
                        if rate != FS_NATIVE:
                            continue
                    if depth >= diag["max_depth"]:
                        diag["scan_complete"] = False
                        continue
                    next_rate_dir = path if rate == FS_NATIVE else rate_dir
                    if rate is None and re.fullmatch(r"\d{4,}", entry.name):
                        # Ohne Einheit ist unklar, ob dies eine Session oder eine andere Rate ist.
                        # Nach darunterliegenden eindeutigen Rateordnern suchen, aber keine Rate erben.
                        diag["unlabelled_numeric_directories"].append(str(path))
                        next_rate_dir = None
                    queue.append((path, depth + 1, next_rate_dir))
                    continue
                identity = scope_file_identity(path)
                if identity is None or rate_dir is None:
                    if path.suffix.lower() == ".parquet" and len(diag["unclassified_file_examples"]) < 30:
                        diag["unclassified_file_examples"].append(str(path))
                    continue
                source, run_id, layout = identity
                item = {"path": path, "rate_directory": rate_dir, "run_id_origin": layout}
                candidates[source].setdefault(run_id, []).append(item)
        except FileNotFoundError:
            if depth != 0:
                diag["access_errors"].append({"path": str(current), "error": "directory_disappeared"})
        except OSError as exc:
            diag["access_errors"].append({"path": str(current), "error": f"{type(exc).__name__}: {exc}"})
    if diag["access_errors"] or diag["skipped_symlinks"]:
        # Ungepruefte Zweige koennten gleichnamige zweite Aufnahmen enthalten.
        diag["scan_complete"] = False
    sources = {"tek": {}, "pico": {}}
    for source, runs in candidates.items():
        for run_id, items in runs.items():
            if len(items) == 1:
                sources[source][run_id] = items[0]
            else:
                diag["ambiguous_candidates"].append({"source": source, "run_id": run_id,
                                                      "paths": [str(i["path"]) for i in items]})
    diag["candidate_counts"] = {s: sum(len(v) for v in runs.values()) for s, runs in candidates.items()}
    if not diag["scan_complete"]:
        sources = {"tek": {}, "pico": {}}
    return sources, diag


def discover_scopes(data_root, workloads, requested_ids=None, scope_root=None):
    records, problems, inventory = [], [], []
    scope_root = Path(scope_root) if scope_root is not None else data_root / "tek_scope_comparison"
    parent_diagnostic = directory_overview(scope_root)
    for workload in workloads:
        root = scope_root / workload
        sources, diagnostic = scan_scope_workload(root)
        diagnostic["scope_root"] = parent_diagnostic
        paired, cross_directory = [], []
        for run_id in sorted(set(sources["tek"]) & set(sources["pico"])):
            tek, pico = sources["tek"][run_id], sources["pico"][run_id]
            if tek["path"].parent != pico["path"].parent or tek["rate_directory"] != pico["rate_directory"]:
                cross_directory.append(run_id)
            else:
                paired.append(run_id)
        canonical = set(range(EXPECTED_PAIRS[workload]))
        wanted = canonical if requested_ids is None else set(requested_ids) & canonical
        outside_requested = [] if requested_ids is None else sorted(set(requested_ids) - canonical)
        actual = [i for i in paired if i in wanted]
        expected = len(wanted)
        if not wanted:
            problems.append(f"{workload}: keine angeforderte ID gehoert zur dokumentierten Paper-Kohorte.")
        if outside_requested:
            problems.append(f"{workload}: angeforderte IDs {outside_requested} liegen ausserhalb der Paper-Kohorte und werden nicht verwendet.")
        extras = sorted((set(sources["tek"]) | set(sources["pico"])) - set(paired))
        inventory.append({"workload": workload, "directory": str(root), "discovery": diagnostic,
                          "cross_directory_pair_ids": cross_directory, "paired_ids": paired,
                          "requested_ids": sorted(wanted), "evaluated_ids": actual,
                          "requested_ids_outside_paper_cohort": outside_requested,
                          "unpaired_ids": extras, "additional_paired_ids": sorted(set(paired) - canonical),
                          "expected_count": expected,
                          "cohort_count_matches": len(actual) == expected})
        if len(actual) != expected:
            problems.append(f"{workload}: {len(actual)} statt {expected} angeforderter Run-Paare gefunden.")
        if diagnostic["root"]["status"] != "readable":
            problems.append(f"{workload}: Datenverzeichnis {root}: {diagnostic['root']['status']}.")
        if not diagnostic["scan_complete"]:
            problems.append(f"{workload}: begrenzte Suche unvollstaendig (Limit/Zugriff/Symlink); keine Aufnahme automatisch ausgewaehlt. Details: input_inventory.json.")
        if diagnostic["ambiguous_candidates"] or cross_directory:
            problems.append(f"{workload}: mehrdeutige Dateien oder getrennte Aufnahmeverzeichnisse; betroffene IDs werden nicht verwendet. Details: input_inventory.json.")
        if extras:
            problems.append(f"{workload}: ungepaarte IDs {extras}; keine automatische Paarbildung.")
        for run_id in actual:
            for source in ("tek", "pico"):
                item = sources[source][run_id]
                records.append({"kind": "scope", "workload": workload, "source": source,
                                "run_id": run_id, "path": item["path"],
                                "discovery_layout": item["run_id_origin"],
                                "rate_directory": item["rate_directory"]})
    return records, problems, inventory


def discover_fp16(data_root, requested_ids=None):
    base = data_root / "sweep_without_filter" / "gemm" / "fp16" / "5000000Sps"
    records, problems = [], []
    wanted = ALL_FP16_IDS if requested_ids is None else tuple(i for i in requested_ids if i in ALL_FP16_IDS)
    for run_id in wanted:
        path = base / str(run_id) / "oscilloscope.npy"
        meta = base / str(run_id) / "results.yaml"
        if not path.is_file() or not meta.is_file():
            problems.append(f"FP16 Run {run_id}: oscilloscope.npy oder results.yaml fehlt in {path.parent}.")
            continue
        records.append({"kind": "fp16", "workload": "gemmfp16", "source": "pico_stored_power",
                        "run_id": run_id, "path": path, "yaml_path": meta})
    return records, problems


def metadata_evidence(analysis_root, out):
    """Nur kleine, gezielt bekannte Analysebaeume. Kein Scan des Rohdatenarchivs."""
    home = Path.home()
    roots = [analysis_root / "gemm_fp16_common_reference_psd_v3",
             analysis_root / "edge_ai_auto_pipeline_v1" / "generated_configs"]
    homes = list(dict.fromkeys((home, Path("external-analysis"))))
    explicit = []
    for base in homes:
        if base.is_dir():
            explicit.extend(sorted(base.glob("common_reference_psd_tool_v*/config_gemm_fp16.yaml")))
    for w in WORKLOADS:
        name = w.replace("-", "_")
        explicit.append(analysis_root / ("tek_scope_comparison_" + name + "_v1") / "scope_comparison_manifest.json")
    explicit.append(analysis_root / "edge_ai_multi_workload_v1" / "multi_workload_manifest.json")
    candidates = list(explicit)
    skipped = []
    for root in roots:
        if not root.is_dir():
            continue
        for current, dirs, names in os.walk(root):
            rel = Path(current).relative_to(root)
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in
                             {"cache", "caches", "_cache", "figures", "plots", "venv", "__pycache__"})
            if len(rel.parts) >= 3:
                dirs[:] = []
            for name in sorted(names):
                p = Path(current) / name
                if p.suffix.lower() in {".yaml", ".yml", ".json", ".csv", ".md"}:
                    candidates.append(p)
    candidates = list(dict.fromkeys(candidates))[:120]
    found = []
    budget = 12_000_000
    pattern = re.compile(r"select|exclu|inclu|run_ids|record_ids|keep_runs|104|window|offset|start_stop|warm.?up", re.I)
    excerpts = []
    dest = out / "metadata"
    dest.mkdir(exist_ok=True)
    for old in dest.iterdir():
        if old.is_file() and re.fullmatch(r"\d{3}_.+", old.name):
            old.unlink()  # Nur von diesem Skript erzeugte Metadatenkopien.
    for path in candidates:
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > 2_000_000 or size > budget:
            skipped.append(str(path))
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        budget -= size
        target = dest / (f"{len(found):03d}_" + path.name)
        target.write_text(text, encoding="utf-8")
        found.append({"source": str(path), "copy": str(target.relative_to(out)), "bytes": size})
        hits = [(i + 1, line[:600]) for i, line in enumerate(text.splitlines()) if pattern.search(line)][:50]
        if hits:
            excerpts.append({"source": str(path), "matching_lines": hits})
    source_pattern = re.compile(r"run_ids|selected_runs|include_runs|exclude_runs|keep_runs|range\(2|104|offset_raw|gain_a_per_raw|voltage_model")
    source_excerpts = []
    inspected = 0
    for base in homes:
        for tool_root in sorted(base.glob("common_reference_psd_tool_v*")) if base.is_dir() else []:
            if not tool_root.is_dir():
                continue
            for current, dirs, names in os.walk(tool_root):
                depth = len(Path(current).relative_to(tool_root).parts)
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in
                                 {"venv", "env", "__pycache__", "site-packages", "tests", "cache"})
                if depth >= 2:
                    dirs[:] = []
                for name in sorted(names):
                    p = Path(current) / name
                    if p.suffix != ".py" or p.stat().st_size > 250_000 or inspected >= 200:
                        continue
                    inspected += 1
                    source_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                    indices = set()
                    for i, line in enumerate(source_lines):
                        if source_pattern.search(line):
                            indices.update(range(max(0, i - 2), min(len(source_lines), i + 3)))
                    if indices:
                        source_excerpts.append({"source": str(p), "lines": [(i + 1, source_lines[i][:600])
                                                for i in sorted(indices)[:160]]})
    result = {"found": found, "omitted_large": skipped, "selection_and_window_excerpts": excerpts,
              "search_roots": [directory_overview(p) for p in dict.fromkeys([analysis_root] + roots)],
              "local_analysis_code_excerpts": source_excerpts,
              "selection_reason": "Nicht automatisch bewiesen; Originalmetadaten und Textbelege manuell pruefen.",
              "note": "Es wird keine Config automatisch ausgefuehrt oder anhand guter Resultate ausgewaehlt."}
    write_json(out / "metadata_evidence.json", result)
    return result


def calibrated_power(raw, source, workload):
    x = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(x).all():
        raise ValueError("Nichtendlicher Stromwert; keine Imputation oder Sampleentfernung.")
    if source == "pico":
        current = (x + PICO_OFFSET_RAW) * PICO_GAIN
    elif source == "tek":
        current = x + (YOLO_TEK_OFFSET_A if workload == "yolofp32" else 0.0)
    else:
        raise ValueError("Unbekannte Stromquelle")
    outside = int(np.count_nonzero((current < 0) | (current > 3.5)))
    power = current * (V_INTERCEPT + V_SLOPE * current)
    return power, outside, float(current.min()), float(current.max())


def resample_power(blocks, n, workspace, native_dest=None):
    """VHQ auf der gesamten Aufnahme; konstante 0.5-s-Randfortsetzung nur zum Filtern.

    Fortsetzung wird nach dem Filtern verworfen. Native Zeitachse wird nicht
    verlaengert. Erzeugte Arbeitsdateien liegen ausschliesslich im eigenen Tempordner.
    """
    native_fs, reduced_fs = FS_NATIVE, FS_REDUCED
    guard = int(.5 * native_fs)
    discard = int(.5 * reduced_fs)
    expected = int(round(n * reduced_fs / native_fs))
    reduced = np.memmap(workspace / "reduced.dat", mode="w+", dtype=np.float32, shape=(expected,))
    stream = soxr.ResampleStream(native_fs, reduced_fs, 1, dtype="float64", quality="VHQ")
    emitted = written = seen = 0
    iterator = iter(blocks)
    try:
        first_block = np.asarray(next(iterator), dtype=np.float64)
    except StopIteration:
        raise ValueError("Leerer Datenstrom")
    if len(first_block) == 0:
        raise ValueError("Leerer erster Datenblock")
    first_power = float(first_block[0])
    last_power = first_power

    def consume(samples, last=False):
        nonlocal emitted, written
        y = stream.resample_chunk(np.ascontiguousarray(samples, dtype=np.float64), last=last)
        lo = max(0, discard - emitted)
        hi = min(len(y), discard + expected - emitted)
        if hi > lo:
            count = hi - lo
            reduced[written:written + count] = y[lo:hi]
            written += count
        emitted += len(y)

    for start in range(0, guard, CHUNK):
        consume(np.full(min(CHUNK, guard - start), first_power, dtype=np.float64))
    for block in itertools.chain((first_block,), iterator):
        block = np.asarray(block, dtype=np.float64)
        if not np.isfinite(block).all():
            raise ValueError("Nichtendliche gespeicherte Leistung; keine Imputation oder Sampleentfernung.")
        if seen + len(block) > n:
            raise ValueError("Mehr Samples als der Dateikopf angibt.")
        if native_dest is not None:
            native_dest[seen:seen + len(block)] = block
        consume(block)
        seen += len(block)
        if len(block):
            last_power = float(block[-1])
    if seen != n:
        raise ValueError(f"Datei unvollstaendig gelesen: {seen} statt {n} Samples.")
    for start in range(0, guard, CHUNK):
        count = min(CHUNK, guard - start)
        consume(np.full(count, last_power, dtype=np.float64), last=start + count == guard)
    if written != expected:
        raise ValueError(f"Resampler lieferte {written} statt {expected} Nutzsamples.")
    reduced.flush()
    if native_dest is not None:
        native_dest.flush()
    return reduced


def check_disk(workspace, required_bytes):
    free = shutil.disk_usage(workspace).free
    if free < required_bytes + 256_000_000:
        raise RuntimeError(f"Temporaer etwa {required_bytes / 1e9:.2f} GB benoetigt, "
                           f"nur {free / 1e9:.2f} GB frei in {workspace}; --scratch-dir verwenden.")


def load_scope(record, workspace):
    path, source, workload = record["path"], record["source"], record["workload"]
    pf = pq.ParquetFile(path)
    schema = pf.schema_arrow
    if "current" not in schema.names:
        raise ValueError(f"Dokumentierte Spalte current fehlt: {schema}")
    import pyarrow as pa
    dtype = schema.field("current").type
    if not pa.types.is_floating(dtype):
        raise ValueError(f"current hat {dtype}; erwartete skalierte Gleitkommawerte, keine ADC-Codes.")
    n = pf.metadata.num_rows
    if n < 10:
        raise ValueError("Zu wenige Rohsamples")
    check_disk(workspace, n * 8 + math.ceil(n / 5) * 4)
    native = np.memmap(workspace / "native.dat", mode="w+", dtype=np.float64, shape=(n,))
    audit = {"n_samples": n, "schema": str(schema), "current_min_A": math.inf,
             "current_max_A": -math.inf, "outside_voltage_model_range_samples": 0,
             "input_units": "A" if source == "tek" else "V_at_INA225_output",
             "current_formula": "raw + session_offset_A" if source == "tek" else "(raw + offset_raw) * gain",
             "session_offset_A": YOLO_TEK_OFFSET_A if source == "tek" and workload == "yolofp32" else 0.,
             "session_offset_precision": "KB-rounded; no new fit" if source == "tek" and workload == "yolofp32" else "not_applicable",
             "voltage_model": {"intercept_V": V_INTERCEPT, "slope_V_per_A": V_SLOPE},
             "time_basis": "sample_index / 5000000; keine Hardware-Zeitkontinuitaet daraus bewiesen"}

    def blocks():
        for batch in pf.iter_batches(batch_size=CHUNK, columns=["current"], use_threads=False):
            column = batch.column(0)
            if column.null_count:
                raise ValueError("Nullwerte in current; keine stille Auslassung.")
            power, count, low, high = calibrated_power(column.to_numpy(zero_copy_only=False), source, workload)
            audit["outside_voltage_model_range_samples"] += count
            audit["current_min_A"] = min(audit["current_min_A"], low)
            audit["current_max_A"] = max(audit["current_max_A"], high)
            yield power

    reduced = resample_power(blocks(), n, workspace, native_dest=native)
    return native, reduced, audit


def load_fp16(record, workspace):
    native = np.load(record["path"], mmap_mode="r", allow_pickle=False)
    if native.ndim != 1 or native.dtype.kind != "f" or len(native) < 10:
        raise ValueError(f"Erwartet gespeicherte 1-D-Leistung, erhalten {native.shape}/{native.dtype}.")
    meta = parse_fp16_yaml(record["yaml_path"], len(native))
    if meta["status"] != "ok":
        if str(meta.get("reason", "")).startswith("no_original_window") and "sample_rate_sps" in meta:
            meta["start_s"] = 0.
            meta["stop_s"] = (len(native) - 1) / float(meta["sample_rate_sps"])
            meta["has_original_indices"] = False
            meta["window_basis"] = "complete_saved_array_no_original_window_indices"
        else:
            raise ValueError(meta.get("reason", "Ungueltige FP16-Metadaten"))
    else:
        meta["start_s"], meta["stop_s"] = meta["t0_s"], meta["t1_s"]
        meta["has_original_indices"] = True
    if float(meta["sample_rate_sps"]) != FS_NATIVE:
        raise ValueError(f"FP16-Rate {meta['sample_rate_sps']} statt {FS_NATIVE} S/s.")
    check_disk(workspace, math.ceil(len(native) / 5) * 4)
    blocks = (native[i:i + CHUNK] for i in range(0, len(native), CHUNK))
    reduced = resample_power(blocks, len(native), workspace)
    meta["n_samples"] = len(native)
    meta["input_dtype"] = str(native.dtype)
    meta["power_origin"] = "stored_power_W_no_recalibration"
    return native, reduced, meta


def compact_comparison(comparison):
    rows = comparison["rows"]
    good = [r for r in rows if r["eligible"]]
    return {"rate_sps": comparison["rate_sps"], "phase_fraction": [r["phase_fraction"] for r in good],
            "native_error_pct": [r["native_error_pct"] for r in good],
            "reduced_error_pct": [r["reduced_error_pct"] for r in good],
            "path_difference_pct": [r["path_difference_pct"] for r in good],
            "ineligible": [{"phase_fraction": r["phase_fraction"], "reason": r["reason"]}
                           for r in rows if not r["eligible"]]}


def compare_windows(native, reduced, windows, rates, offsets, endpoint_mode="source"):
    answer = []
    for window in windows:
        start, stop = window["start_s"], window["stop_s"]
        ref_native = linear_window_integral(native, FS_NATIVE, start, stop)
        ref_reduced = linear_window_integral(reduced, FS_REDUCED, start, stop)
        if ref_native <= 0 or not math.isfinite(ref_native):
            raise ValueError("Nichtpositives oder nichtendliches natives Referenzintegral.")
        result = dict(window, native_reference_J=ref_native, reduced_reference_J=ref_reduced,
                      reference_reduction_delta_pct=100 * (ref_reduced / ref_native - 1), comparisons=[])
        for rate in rates:
            if window["actual_duration_s"] * rate + 1e-9 < 3:
                continue
            comparison = compare_energy_paths(native, FS_NATIVE, reduced, FS_REDUCED,
                                              (start, stop), rate, phases=offsets,
                                              endpoint_mode=endpoint_mode,
                                              native_reference_j=ref_native,
                                              reduced_reference_j=ref_reduced)
            result["comparisons"].append(compact_comparison(comparison))
        answer.append(result)
    return answer


def run_record(record, workspace, settings):
    begin = time.monotonic()
    if record["kind"] == "scope":
        native, reduced, meta = load_scope(record, workspace)
    else:
        native, reduced, meta = load_fp16(record, workspace)
    support_stop = min((len(native) - 1) / FS_NATIVE, (len(reduced) - 1) / FS_REDUCED)
    result = {"kind": record["kind"], "workload": record["workload"], "source": record["source"],
              "run_id": record["run_id"], "input": file_stamp(record["path"]), "audit": meta,
              "common_support_stop_s": support_stop,
              "analysis_basis": "independent_sensitivity_not_exact_paper_reproduction",
              "windows": [], "unavailable_durations_s": []}
    if record["kind"] == "scope":
        windows = []
        for duration in settings["durations"]:
            found = make_windows(0., support_stop, duration, count=settings["windows"], max_shortfall_s=2e-6)
            if not found:
                result["unavailable_durations_s"].append(duration)
            windows.extend(found)
        result["windows"] = compare_windows(native, reduced, windows, settings["rates"], settings["offsets"])
        if not windows:
            raise ValueError("Keine angeforderte Fensterdauer im gemeinsamen Samplesupport verfuegbar.")
    else:
        start = meta["start_s"]
        stop = min(meta["stop_s"], support_stop)
        result["metadata_input"] = file_stamp(record["yaml_path"])
        legacy_ref = linear_window_integral(native, FS_NATIVE, meta["start_s"], meta["stop_s"])
        result["legacy_integral_J"] = legacy_ref
        if meta.get("reported_energy_J") is not None:
            result["legacy_integral_minus_reported_J"] = legacy_ref - meta["reported_energy_J"]
        available = stop - start
        if available <= 0:
            raise ValueError("FP16-Fenster liegt ausserhalb des gemeinsamen Samplesupports.")
        if available >= 104. - 2e-6:
            center = .5 * (start + stop)
            duration = min(104., available)
            energy_start, energy_stop = center - .5 * duration, center + .5 * duration
            basis = "centered_104s_within_yaml_indices_independent_sensitivity"
        else:
            energy_start, energy_stop = start, stop
            duration = energy_stop - energy_start
            basis = "yaml_window_shorter_than_104s_not_paper_104s_cohort"
        result["energy_window_basis"] = basis
        window = {"start_s": energy_start, "stop_s": energy_stop, "nominal_duration_s": 104.,
                  "actual_duration_s": duration, "shortfall_s": max(0., 104. - duration),
                  "window_index": 0}
        result["windows"] = compare_windows(native, reduced, [window], [50, 85, 2000], 64)
        if meta.get("has_original_indices", False):
            result["psd"] = compute_fp16_psd(reduced, FS_REDUCED, meta["start_s"], stop,
                                             window_basis="yaml_start_stop_indices_not_original_psd_config")
            result["psd"]["benchmark_stop_support_clip_s"] = max(0., meta["stop_s"] - stop)
        else:
            result["psd"] = {"status": "unavailable", "reason": "Keine start_stop_idx; kein belegter Vorlauf/Idlebereich."}
    result["elapsed_s"] = time.monotonic() - begin
    result["status"] = "completed"
    del native, reduced
    gc.collect()
    return result




import math
from collections.abc import Mapping, Sequence



_BLOCK = 262_144


class IneligibleWindow(ValueError):
    """A declared window/grid lacks enough samples or measured support."""


def _array(power):
    y = np.asanyarray(power)
    if y.ndim != 1 or len(y) < 2 or not np.issubdtype(y.dtype, np.number):
        raise ValueError("Power must be a one-dimensional numeric array with >=2 samples.")
    if np.iscomplexobj(y):
        raise ValueError("Power must be real-valued.")
    return y


def _positive_rate(fs):
    fs = float(fs)
    if not math.isfinite(fs) or fs <= 0:
        raise ValueError("Sampling rate must be finite and positive.")
    return fs


def _snap_integer(x):
    nearest = round(x)
    if abs(x - nearest) <= 8 * np.finfo(float).eps * max(1.0, abs(x)):
        return float(nearest)
    return x


def _positions(times_s, fs, n):
    x = np.asarray(times_s, dtype=np.float64) * fs
    tolerance = 8 * np.finfo(float).eps * max(1, n - 1)
    if not np.all(np.isfinite(x)) or np.any(x < -tolerance) or np.any(x > n - 1 + tolerance):
        raise IneligibleWindow("Window/grid extends beyond measured source support; no extrapolation.")
    # Only floating-point roundoff at a support boundary is clipped.
    return np.clip(x, 0, n - 1)


def _sample_at(power, fs, times_s):
    x = _positions(times_s, fs, len(power))
    indices = np.floor(x).astype(np.int64)
    indices = np.minimum(indices, len(power) - 2)
    fraction = x - indices
    left = np.asarray(power[indices], dtype=np.float64)
    right = np.asarray(power[indices + 1], dtype=np.float64)
    values = left + fraction * (right - left)
    if not np.all(np.isfinite(values)):
        raise ValueError("Non-finite power value encountered; samples are not silently removed.")
    return values


def linear_window_integral(power, fs, start_s, stop_s):
    """Exact integral of the native piecewise-linear interpolant, in joules.

    Uses block sums, no trace-sized time vector or cumulative sum. 'Exact' refers
    to the declared interpolant, subject to ordinary floating-point roundoff.
    """
    y, fs = _array(power), _positive_rate(fs)
    start_s, stop_s = float(start_s), float(stop_s)
    if not start_s < stop_s:
        raise ValueError("A positive-duration window is required.")
    x0, x1 = _positions([start_s, stop_s], fs, len(y))
    p0, p1 = _sample_at(y, fs, [start_s, stop_s])
    left, right = math.ceil(_snap_integer(float(x0))), math.floor(_snap_integer(float(x1)))
    if left > right:
        return float((p0 + p1) * 0.5 * (stop_s - start_s))
    pl, pr = float(y[left]), float(y[right])
    area = 0.5 * (p0 + pl) * (left / fs - start_s)
    area += 0.5 * (pr + p1) * (stop_s - right / fs)
    if right > left:
        total = 0.5 * (pl + pr)
        for first in range(left + 1, right, _BLOCK):
            total += float(np.sum(y[first:min(first + _BLOCK, right)], dtype=np.float64))
        area += total / fs
    if not math.isfinite(area):
        raise ValueError("Non-finite integral; input data require inspection.")
    return float(area)


def make_windows(span_start, span_stop, duration_s, count=16, max_shortfall_s=2e-6):
    """Evenly place distinct windows in common measured support.

    A nominal duration longer than support by <=max_shortfall_s uses the actual
    support and records its shortfall. Larger deficits return no windows. A
    full-support window occurs only once, rather than sixteen duplicates.
    """
    span_start, span_stop, duration_s = map(float, (span_start, span_stop, duration_s))
    if not all(map(math.isfinite, (span_start, span_stop, duration_s))):
        raise ValueError("Window parameters must be finite.")
    if span_stop <= span_start or duration_s <= 0 or int(count) != count or count < 1:
        raise ValueError("Invalid support, duration or window count.")
    if not math.isfinite(max_shortfall_s) or max_shortfall_s < 0:
        raise ValueError("max_shortfall_s must be finite and non-negative.")
    support = span_stop - span_start
    roundoff = 8 * np.finfo(float).eps * max(1.0, support, duration_s)
    if duration_s > support + max_shortfall_s + roundoff:
        return []
    actual = min(duration_s, support)
    last_start = span_stop - actual
    if last_start - span_start <= roundoff:
        starts = [span_start]
    else:
        starts = np.unique(np.linspace(span_start, last_start, int(count))).tolist()
    return [dict(start_s=float(s), stop_s=float(min(s + actual, span_stop)),
                 nominal_duration_s=duration_s,
                 actual_duration_s=float(min(s + actual, span_stop) - s),
                 shortfall_s=float(max(0.0, duration_s - (min(s + actual, span_stop) - s))))
            for s in starts]


def _grid_value(power, fs, index, rate_sps, phase_fraction):
    return float(_sample_at(power, fs, [(index + phase_fraction) / rate_sps])[0])


def _grid_boundary_value(power, fs, coordinate, rate_sps, phase_fraction):
    coordinate = _snap_integer(float(coordinate))
    first = math.floor(coordinate)
    fraction = coordinate - first
    if fraction == 0:
        return _grid_value(power, fs, first, rate_sps, phase_fraction)
    pair = _sample_at(power, fs, (np.array([first, first + 1], dtype=float) + phase_fraction) / rate_sps)
    return float(pair[0] + fraction * (pair[1] - pair[0]))


def sampled_window_energy(power, fs, start_s, stop_s, rate_sps, phase_fraction=0.0,
                          endpoint_mode="source", min_samples=4):
    """Sample stored power on t=(k+phase_fraction)/rate and integrate a fixed window.

    source: endpoints use this source's interpolated values; both branches insert
    endpoints by the same rule. They are not counted as extra target-grid samples.
    grid: endpoints are interpolated from bracketing target samples, requiring up
    to one target period of recorded support outside the integration window.

    No target-rate anti-alias filter is added. Returns (energy_J, target_count).
    """
    y, fs, rate = _array(power), _positive_rate(fs), _positive_rate(rate_sps)
    phase = float(phase_fraction)
    if not math.isfinite(phase) or not 0 <= phase < 1:
        raise ValueError("phase_fraction must lie in [0,1).")
    if rate > fs * (1 + 8 * np.finfo(float).eps):
        raise ValueError("Target rate may not exceed the source representation rate.")
    if endpoint_mode not in ("source", "grid"):
        raise ValueError("endpoint_mode must be 'source' or 'grid'.")
    if not isinstance(min_samples, (int, np.integer)) or min_samples < 0:
        raise ValueError("min_samples must be a non-negative integer.")
    start_s, stop_s = float(start_s), float(stop_s)
    if not start_s < stop_s:
        raise ValueError("A positive-duration window is required.")
    _positions([start_s, stop_s], fs, len(y))
    u0 = _snap_integer(start_s * rate - phase)
    u1 = _snap_integer(stop_s * rate - phase)
    left, right = math.ceil(u0), math.floor(u1)
    n_target = max(0, right - left + 1)
    if n_target < min_samples:
        raise IneligibleWindow(f"Only {n_target} in-window target samples; minimum is {min_samples}.")
    if endpoint_mode == "source":
        p0, p1 = _sample_at(y, fs, [start_s, stop_s])
    else:
        p0 = _grid_boundary_value(y, fs, u0, rate, phase)
        p1 = _grid_boundary_value(y, fs, u1, rate, phase)
    if left > right:
        return float((p0 + p1) * 0.5 * (stop_s - start_s)), n_target
    tl, tr = (left + phase) / rate, (right + phase) / rate
    pl, pr = _sample_at(y, fs, [tl, tr])
    area = 0.5 * (p0 + pl) * (tl - start_s) + 0.5 * (pr + p1) * (stop_s - tr)
    if right > left:
        total = 0.5 * (pl + pr)
        for first in range(left + 1, right, _BLOCK):
            indices = np.arange(first, min(first + _BLOCK, right), dtype=np.float64)
            total += float(np.sum(_sample_at(y, fs, (indices + phase) / rate), dtype=np.float64))
        area += total / rate
    if not math.isfinite(area):
        raise ValueError("Non-finite sampled integral.")
    return float(area), n_target


def bandlimit_power(power, native_fs, analysis_fs=1_000_000.0):
    """VHQ rate conversion of already derived power; no U/I recombination."""
    import soxr
    y, native_fs, analysis_fs = _array(power), _positive_rate(native_fs), _positive_rate(analysis_fs)
    if analysis_fs >= native_fs:
        raise ValueError("The sensitivity branch must reduce the native rate.")
    if y.dtype not in (np.dtype("float32"), np.dtype("float64")):
        y = np.asarray(y, dtype=np.float64)
    return soxr.resample(y, native_fs, analysis_fs, quality="VHQ")


def compare_energy_paths(native, native_fs, reduced, reduced_fs, window, rate_sps,
                         phases=64, endpoint_mode="source", min_samples=4,
                         native_reference_j=None, reduced_reference_j=None):
    """Compare native->target with native->reduced->target on identical grids.

    References can be supplied to reuse one integration across multiple rates.
    Both path errors use the native reference; reduced_self_error_pct is also
    provided to isolate changes caused by choosing a different denominator.
    """
    start_s, stop_s = map(float, window)
    if isinstance(phases, (int, np.integer)):
        if phases < 1:
            raise ValueError("At least one grid offset is required.")
        phase_values = np.arange(phases, dtype=float) / phases
    else:
        phase_values = np.asarray(phases, dtype=float)
        if phase_values.ndim != 1 or len(phase_values) == 0:
            raise ValueError("phases must be a positive count or nonempty one-dimensional sequence.")
    en = linear_window_integral(native, native_fs, start_s, stop_s) if native_reference_j is None else float(native_reference_j)
    er = linear_window_integral(reduced, reduced_fs, start_s, stop_s) if reduced_reference_j is None else float(reduced_reference_j)
    if not (math.isfinite(en) and math.isfinite(er) and en > 0 and er > 0):
        raise ValueError("Relative energy errors require finite positive reference energies.")
    rows = []
    for phase in phase_values:
        row = dict(phase_fraction=float(phase), eligible=False)
        try:
            a, na = sampled_window_energy(native, native_fs, start_s, stop_s, rate_sps,
                                          float(phase), endpoint_mode, min_samples)
            b, nb = sampled_window_energy(reduced, reduced_fs, start_s, stop_s, rate_sps,
                                          float(phase), endpoint_mode, min_samples)
            if na != nb:
                raise RuntimeError("The two branches unexpectedly used different grids.")
            row.update(eligible=True, target_samples=na, native_sampled_J=a, reduced_sampled_J=b,
                       native_error_pct=100 * (a - en) / en,
                       reduced_error_pct=100 * (b - en) / en,
                       reduced_self_error_pct=100 * (b - er) / er,
                       path_difference_pct=100 * (b - a) / en)
        except IneligibleWindow as exc:
            row["reason"] = str(exc)
        rows.append(row)
    return dict(start_s=start_s, stop_s=stop_s, actual_duration_s=stop_s-start_s,
                rate_sps=float(rate_sps), endpoint_mode=endpoint_mode,
                native_reference_J=en, reduced_reference_J=er,
                reference_reduction_delta_pct=100 * (er-en) / en,
                rows=rows)


def summarize_errors(errors, quantile_method="linear"):
    """Descriptive signed/absolute error summary, explicitly counting invalid cases."""
    a = np.asarray(errors, dtype=float).ravel()
    finite = a[np.isfinite(a)]
    result = dict(n_total=int(a.size), n_valid=int(finite.size), n_invalid=int(a.size-finite.size),
                  quantile_method=quantile_method)
    if finite.size == 0:
        result.update(signed_mean_pct=None, abs_median_pct=None, abs_q95_pct=None, abs_max_pct=None)
    else:
        result.update(signed_mean_pct=float(np.mean(finite)),
                      abs_median_pct=float(np.quantile(np.abs(finite), .5, method=quantile_method)),
                      abs_q95_pct=float(np.quantile(np.abs(finite), .95, method=quantile_method)),
                      abs_max_pct=float(np.max(np.abs(finite))))
    return result


def hierarchical_error_summary(errors_by_record, quantile_method="linear"):
    """Q95 within each physical recording, then Q95 across recordings; no CI claim."""
    groups = errors_by_record.values() if isinstance(errors_by_record, Mapping) else errors_by_record
    summaries = [summarize_errors(e, quantile_method) for e in groups]
    per_record = [s["abs_q95_pct"] for s in summaries if s["n_valid"]]
    return dict(n_records_total=len(summaries), n_records_valid=len(per_record),
                n_records_invalid=len(summaries)-len(per_record), quantile_method=quantile_method,
                hierarchical_q95_pct=(float(np.quantile(per_record, .95, method=quantile_method)) if per_record else None),
                max_record_q95_pct=(max(per_record) if per_record else None),
                per_record_q95_pct=per_record)


def welch_psd(power, fs, segment_seconds=1.0, overlap=0.5):
    """Mean-removed power PSD; periodic Hann, arithmetic segment average, W²/Hz."""
    y, fs = _array(power), _positive_rate(fs)
    if not math.isfinite(segment_seconds) or segment_seconds <= 0 or not 0 <= overlap < 1:
        raise ValueError("Invalid Welch segment duration or overlap.")
    nperseg = int(round(segment_seconds * fs))
    if nperseg < 2 or len(y) < nperseg:
        raise IneligibleWindow("Not enough samples for the declared Welch segment size.")
    noverlap = int(round(overlap * nperseg))
    if noverlap >= nperseg:
        raise ValueError("Rounded Welch overlap is not smaller than its segment.")
    z = np.asarray(y, dtype=np.float64)
    if not np.all(np.isfinite(z)):
        raise ValueError("PSD input contains non-finite power samples.")
    z = z - float(np.mean(z))
    frequencies, psd = signal.welch(z, fs=fs, window=signal.windows.hann(nperseg, sym=False),
                                   nperseg=nperseg, noverlap=noverlap, nfft=nperseg,
                                   detrend=False, return_onesided=True, scaling="density", average="mean")
    metadata = dict(samples=len(y), fs_sps=fs, actual_span_s=(len(y)-1)/fs,
                    nperseg=nperseg, noverlap=noverlap,
                    n_segments=1+(len(y)-nperseg)//(nperseg-noverlap),
                    window="periodic Hann", centering="whole supplied interval mean",
                    detrend=False, scaling="density", segment_average="mean")
    return frequencies, psd, metadata


def _validate_psd(frequencies, psd):
    f, p = np.asarray(frequencies, dtype=float), np.asarray(psd, dtype=float)
    if f.ndim != 1 or p.shape != f.shape or len(f) < 2:
        raise ValueError("PSD and frequency arrays must have equal one-dimensional shape.")
    if not (np.all(np.isfinite(f)) and np.all(np.isfinite(p))) or np.any(np.diff(f) <= 0) or f[0] < 0:
        raise ValueError("Invalid PSD frequency support or non-finite PSD.")
    return f, p


def psd_area(frequencies, psd, cutoff_hz=None):
    """Trapezoidal area of a linearly interpolated PSD, including an exact cutoff."""
    f, p = _validate_psd(frequencies, psd)
    cutoff = float(f[-1] if cutoff_hz is None else cutoff_hz)
    if not math.isfinite(cutoff) or cutoff < 0:
        raise ValueError("PSD cutoff must be finite and non-negative.")
    if cutoff <= f[0]:
        return 0.0
    if cutoff >= f[-1]:
        return float(np.sum((p[:-1]+p[1:]) * 0.5 * np.diff(f)))
    upper = int(np.searchsorted(f, cutoff, side="right"))
    lower = upper - 1
    area = float(np.sum((p[:lower]+p[1:lower+1]) * 0.5 * np.diff(f[:lower+1])))
    pc = p[lower] + (p[upper]-p[lower]) * (cutoff-f[lower]) / (f[upper]-f[lower])
    return area + float((p[lower]+pc) * 0.5 * (cutoff-f[lower]))


def _spectral_quantile(f, p, fraction):
    areas = (p[:-1]+p[1:]) * 0.5 * np.diff(f)
    cumulative = np.concatenate(([0.0], np.cumsum(areas)))
    total = float(cumulative[-1])
    if total <= 0:
        return None
    target = fraction * total
    # The lowest frequency enclosing the requested area is the left edge of
    # a CDF plateau, not its right edge.
    i = max(0, min(int(np.searchsorted(cumulative, target, side="left"))-1, len(f)-2))
    remainder = target-cumulative[i]
    width = f[i+1]-f[i]
    slope = (p[i+1]-p[i])/width
    if remainder <= 0:
        dx = 0.0
    else:
        discriminant = max(0.0, p[i]*p[i]+2*slope*remainder)
        denominator = p[i] + math.sqrt(discriminant)
        dx = 2*remainder/denominator if denominator > 0 else width
    return float(f[i]+min(max(dx, 0.0), width))


def positive_excess_metrics(frequencies, active_psd, idle_psd, rates_sps=()):
    """Explicit max(active-idle,0), alongside its signed and negative components.

    This is measured positive excess, not an unbiased estimate of workload-only
    variance. Under a same-distribution null it can remain positive from PSD noise.
    """
    f, active = _validate_psd(frequencies, active_psd)
    _, idle = _validate_psd(f, idle_psd)
    if np.any(active < 0) or np.any(idle < 0):
        raise ValueError("Input PSDs must be non-negative.")
    difference = active-idle
    positive, negative = np.maximum(difference, 0), np.maximum(-difference, 0)
    av, iv = psd_area(f, active), psd_area(f, idle)
    pv, nv = psd_area(f, positive), psd_area(f, negative)
    coverage = {str(float(rate)): (psd_area(f, positive, _positive_rate(rate)/2)/pv if pv > 0 else None)
                for rate in rates_sps}
    return dict(active_variance_W2=av, idle_variance_W2=iv,
                signed_excess_variance_W2=psd_area(f, difference),
                positive_excess_variance_W2=pv, negative_excess_variance_W2=nv,
                positive_excess_over_active=(pv/av if av > 0 else None),
                f95_hz=_spectral_quantile(f, positive, .95),
                f99_hz=_spectral_quantile(f, positive, .99), coverage_by_rate=coverage,
                area_rule="trapezoidal piecewise-linear PSD; exact cutoff interpolation",
                claim="descriptive measured positive excess; clipping/noise bias retained")


def idle_split_sanity(idle_power, fs, segment_seconds=1.0, overlap=0.5,
                      rates_sps=(), active_power=None):
    """Disjoint first/last idle blocks with exactly matched Welch segment counts.

    An optional central active block uses the same sample count for a descriptive
    matched-segment comparison. Splits are numerical blocks from a recording, not
    independent physical acquisitions; this is neither a formal null test nor a
    bias correction, and no significance/equivalence threshold is inferred.
    """
    idle, fs = _array(idle_power), _positive_rate(fs)
    if not math.isfinite(segment_seconds) or segment_seconds <= 0 or not 0 <= overlap < 1:
        raise ValueError("Invalid Welch settings.")
    segment = int(round(segment_seconds*fs))
    hop = segment-int(round(segment*overlap))
    half = len(idle)//2
    if segment < 2 or hop < 1 or half < segment:
        raise IneligibleWindow("Idle is too short for two disjoint blocks of the declared Welch size.")
    n = segment+((half-segment)//hop)*hop
    f, p0, m0 = welch_psd(idle[:n], fs, segment_seconds, overlap)
    f1, p1, m1 = welch_psd(idle[-n:], fs, segment_seconds, overlap)
    if not np.array_equal(f, f1) or m0["n_segments"] != m1["n_segments"]:
        raise RuntimeError("Idle blocks unexpectedly have unmatched PSD settings.")
    result = dict(samples_per_block=n, n_segments_per_block=m0["n_segments"],
                  first_block_span_s=(n-1)/fs, second_block_start_s=(len(idle)-n)/fs,
                  shared_idle_record=True, claim="descriptive disjoint-block idle sanity, not independent repetitions",
                  first_minus_last=positive_excess_metrics(f, p0, p1, rates_sps),
                  last_minus_first=positive_excess_metrics(f, p1, p0, rates_sps))
    if active_power is not None:
        active = _array(active_power)
        if len(active) < n:
            raise IneligibleWindow("Active interval is shorter than the matched idle blocks.")
        start = (len(active)-n)//2
        fa, pa, ma = welch_psd(active[start:start+n], fs, segment_seconds, overlap)
        if not np.array_equal(f, fa) or ma["n_segments"] != m0["n_segments"]:
            raise RuntimeError("Active block unexpectedly has unmatched PSD settings.")
        result["active_block_start_s"] = start/fs
        result["active_minus_first_idle"] = positive_excess_metrics(f, pa, p0, rates_sps)
        result["active_minus_last_idle"] = positive_excess_metrics(f, pa, p1, rates_sps)
    return result




import math
from collections.abc import Mapping
from pathlib import Path




FP16_RATES = (2_000.0, 125_000.0, 160_000.0)


def _number(value, name, positive=False):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be numeric, not boolean.")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive." if positive else "."))
    return result


def _integer(value, name, minimum=0):
    result = _number(value, name)
    if not result.is_integer() or result < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}.")
    return int(result)


def parse_fp16_yaml(path, n_samples):
    """Read the verified legacy schema; YAML start and stop are inclusive.

    A null start_stop_idx is returned as blocked, because a previously cut array
    does not establish the original benchmark boundaries or preceding idle data.
    The reported legacy N/fs duration and actual (N-1)/fs span remain separate.
    No waveform is read, changed, calibrated or implicitly trimmed here.
    """
    answer = dict(status="blocked", path=str(path), reason=None,
                  window_basis="legacy YAML inclusive start_stop_idx")
    try:
        n_samples = _integer(n_samples, "n_samples", 2)
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise ValueError("YAML root is not a mapping.")
        scope = document["oscilloscope_results"]
        if not isinstance(scope, Mapping):
            raise ValueError("oscilloscope_results is missing or null.")
        values = scope["results"]
        if not isinstance(values, Mapping):
            raise ValueError("oscilloscope_results.results is missing or null.")
        fs = _number(scope["sample_rate"], "sample_rate", positive=True)
        energy = _number(values["energy"], "reported energy")
        duration = _number(values["duration"], "reported duration", positive=True)
        voltage_flag = scope.get("use_voltage")
        if voltage_flag is not None and not isinstance(voltage_flag, bool):
            raise ValueError("use_voltage must be boolean when present.")
        answer.update(n_samples=n_samples, sample_rate_sps=fs,
                      reported_energy_J=energy, reported_duration_s=duration,
                      use_voltage=voltage_flag, measurement_type=scope.get("msmt_type"),
                      measurement_environment=document.get("measurement_environment"))
        pair = values["start_stop_idx"]
        if pair is None:
            answer.update(reason="no_original_window: start_stop_idx is null; array may already be cut",
                          start_idx=None, stop_idx=None, t0_s=None, t1_s=None)
            return answer
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("start_stop_idx must contain exactly two inclusive indices.")
        start = _integer(pair[0], "start index")
        stop = _integer(pair[1], "stop index")
        if not 0 <= start < stop < n_samples:
            raise ValueError("Inclusive indices are outside the array or have no positive span.")
        count = stop - start + 1
        expected_duration = count / fs
        delta = duration - expected_duration
        tolerance = max(2.0 / fs, 1e-9 * max(1.0, duration))
        answer.update(status="ok", reason=None, start_idx=start, stop_idx=stop,
                      python_stop_exclusive=stop + 1, window_samples=count,
                      t0_s=start / fs, t1_s=stop / fs,
                      integration_span_s=(stop - start) / fs,
                      expected_legacy_duration_s=expected_duration,
                      reported_duration_delta_s=delta,
                      duration_consistency=("matches_legacy_N_over_fs" if abs(delta) <= tolerance
                                            else "mismatch_requires_inspection"))
    except (OSError, UnicodeError, yaml.YAMLError, KeyError, TypeError, ValueError, OverflowError) as exc:
        answer["reason"] = f"invalid_fp16_metadata: {exc}"
    return answer


def _power_array(power):
    array = np.asanyarray(power)
    if (array.ndim != 1 or len(array) < 2
            or not np.issubdtype(array.dtype, np.number) or np.iscomplexobj(array)):
        raise ValueError("Expected a one-dimensional real numeric power array.")
    return array


def _block(power, fs, start_s, duration_s, label):
    """Choose the nearest existing sample grid, with an exact declared sample count.

    Period counts and first-to-last sample spans are both exported. No waveform
    interpolation or padding is used for PSD blocks. The rounding shift is <= a
    half sample and is recorded, rather than silently claiming exact endpoints.
    """
    count_float = duration_s * fs
    count = int(round(count_float))
    if count < 2 or abs(count_float - count) > 1e-6:
        raise ValueError("The requested PSD duration is not an integer sample count at this rate.")
    first = int(round(start_s * fs))
    stop = first + count
    tolerance = 8 * np.finfo(float).eps * max(1.0, len(power) / fs)
    if (start_s < -tolerance or start_s + duration_s > len(power) / fs + tolerance
            or first < 0 or stop > len(power)):
        raise IneligibleWindow(f"{label} is outside recorded support; no padding or replacement idle.")
    metadata = dict(label=label, requested_start_s=float(start_s),
                    requested_duration_s=float(duration_s), start_index=first,
                    stop_index_exclusive=stop, samples=count,
                    first_sample_s=first / fs, last_sample_s=(stop - 1) / fs,
                    sample_count_duration_s=count / fs, actual_span_s=(count - 1) / fs,
                    grid_rounding_shift_s=first / fs - start_s)
    return power[first:stop], metadata


def _spectra_pair(active, idle, fs):
    f, ap, am = welch_psd(active, fs, segment_seconds=1.0, overlap=0.5)
    fi, ip, im = welch_psd(idle, fs, segment_seconds=1.0, overlap=0.5)
    if not np.array_equal(f, fi):
        raise RuntimeError("Active and idle frequency grids differ.")
    metrics = positive_excess_metrics(f, ap, ip, FP16_RATES)
    # A target above this stored representation's rate is not an observed
    # spectral coverage result, even though an integral could clamp to Nyquist.
    for rate in FP16_RATES:
        if rate > fs:
            metrics["coverage_by_rate"][str(float(rate))] = None
    return metrics, am, im


def _ratio(numerator, denominator):
    return float(numerator / denominator) if denominator is not None and denominator > 0 else None


def compute_fp16_psd(reduced_power, fs=1_000_000.0, t0=None, t1=None,
                     window_basis="not supplied"):
    """Return descriptive FP16 PSD checks on a complete already reduced record.

    t0/t1 are benchmark endpoints measured from sample zero of reduced_power.
    Baseline: central active 10 s vs idle 4 s ending 0.5 s before t0 (19/7
    Welch segments). Matched-length sensitivity: central active 4 s vs the same
    idle 4 s (7/7). Idle sanity: two disjoint 2-s halves (3/3), both subtraction
    directions, plus equal-length active comparisons. None is a formal null test,
    uncertainty interval, selection justification, or automatic bias correction.
    """
    result = dict(status="blocked", reason=None, window_basis=window_basis,
                  rates_sps=list(FP16_RATES),
                  claim="descriptive measured positive excess and block sensitivities; no confidence intervals")
    try:
        power = _power_array(reduced_power)
        fs = _number(fs, "fs", positive=True)
        t0, t1 = _number(t0, "t0"), _number(t1, "t1")
        if t0 < 0 or t1 <= t0:
            raise ValueError("Benchmark endpoints must define a positive recorded interval.")
        if t1 - t0 < 10.0 - 1e-9:
            raise IneligibleWindow("Benchmark interval is shorter than the declared 10-s active PSD block.")
        if t1 > len(power) / fs + 1e-9:
            raise IneligibleWindow("Benchmark endpoint lies outside the supplied complete record.")
        center = (t0 + t1) / 2.0
        active10, a10w = _block(power, fs, center - 5.0, 10.0, "central active 10 s")
        idle4, i4w = _block(power, fs, t0 - 4.5, 4.0, "pre-benchmark idle 4 s")
        active4, a4w = _block(power, fs, center - 2.0, 4.0, "central active 4 s")
        baseline, a10m, i4m = _spectra_pair(active10, idle4, fs)
        matched4, a4m, i4m_matched = _spectra_pair(active4, idle4, fs)
        if (a10m["n_segments"], i4m["n_segments"],
                a4m["n_segments"], i4m_matched["n_segments"]) != (19, 7, 7, 7):
            raise ValueError("Sampling rate/rounded Welch hop does not support exact 19/7 and 7/7 counts.")
        sanity = idle_split_sanity(idle4, fs, segment_seconds=1.0, overlap=0.5,
                                   rates_sps=FP16_RATES, active_power=active4)
        if sanity["n_segments_per_block"] != 3:
            raise RuntimeError("The idle halves unexpectedly do not have three Welch segments each.")
        for key in ("first_minus_last", "last_minus_first",
                    "active_minus_first_idle", "active_minus_last_idle"):
            for rate in FP16_RATES:
                if rate > fs:
                    sanity[key]["coverage_by_rate"][str(float(rate))] = None
        null_ratios = {}
        for direction in ("first_minus_last", "last_minus_first"):
            value = sanity[direction]["positive_excess_variance_W2"]
            null_ratios[direction] = dict(
                to_baseline_active_excess=_ratio(value, baseline["positive_excess_variance_W2"]),
                to_matched_4s_active_excess=_ratio(value, matched4["positive_excess_variance_W2"]),
                to_active_minus_first_idle_2s=_ratio(value, sanity["active_minus_first_idle"]["positive_excess_variance_W2"]),
                to_active_minus_last_idle_2s=_ratio(value, sanity["active_minus_last_idle"]["positive_excess_variance_W2"]))
        result.update(status="ok", reason=None, fs_sps=fs,
                      benchmark_window=dict(start_s=t0, stop_s=t1, span_s=t1 - t0),
                      baseline_10s_4s=dict(metrics=baseline, active_window=a10w, idle_window=i4w,
                                          active_welch=a10m, idle_welch=i4m),
                      matched_4s_4s=dict(metrics=matched4, active_window=a4w, idle_window=i4w,
                                         active_welch=a4m, idle_welch=i4m_matched),
                      idle_split_2s_2s=sanity,
                      null_to_active_excess_ratios=null_ratios,
                      null_ratio_scope="baseline denominator uses 19/7 segments, matched 4-s denominator 7/7; 2-s comparisons use 3/3 throughout",
                      grid_rule="nearest existing sample for each PSD block start; fixed sample count; no padding")
    except (TypeError, ValueError, OverflowError) as exc:
        result["reason"] = f"fp16_psd_not_computable: {exc}"
    return result


def _empirical(values, expected_count):
    usable = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    q = np.quantile(usable, [.05, .5, .95], method="linear") if usable else [None] * 3
    return dict(n_defined=len(usable), n_undefined=expected_count - len(usable),
                q05=(float(q[0]) if usable else None), median=(float(q[1]) if usable else None),
                q95=(float(q[2]) if usable else None))


def summarize_fp16_psd_cohorts(results_by_run):
    """Empirical 13-vs-15 summaries from {run_id: compute_fp16_psd(...)}, no CI."""
    normalized = {}
    for run, value in results_by_run.items():
        number = _integer(run, "run ID")
        if number in normalized:
            raise ValueError("Duplicate run IDs after numeric normalization.")
        normalized[number] = value
    output = dict(selection_reason="not inferred; metadata evidence is required",
                  quantile_method="linear", statistic_scope="per-recording empirical percentiles, not confidence intervals",
                  extra_run_ids=sorted(set(normalized) - set(range(15))), cohorts={})
    for name, expected in (("paper_ids_2_to_14", list(range(2, 15))),
                           ("all_ids_0_to_14", list(range(15)))):
        valid = [i for i in expected if normalized.get(i, {}).get("status") == "ok"]
        invalid = [i for i in expected if i in normalized and i not in valid]
        missing = [i for i in expected if i not in normalized]
        cohort = dict(expected_run_ids=expected, valid_run_ids=valid, missing_run_ids=missing,
                      blocked_run_ids=invalid, complete=(not missing and not invalid), branches={})
        for branch in ("baseline_10s_4s", "matched_4s_4s"):
            metrics = [normalized[i][branch]["metrics"] for i in valid]
            summary = {key: _empirical([m[key] for m in metrics], len(expected))
                       for key in ("positive_excess_variance_W2", "f95_hz", "f99_hz")}
            summary["coverage_by_rate"] = {
                str(rate): _empirical([m["coverage_by_rate"][str(rate)] for m in metrics], len(expected))
                for rate in FP16_RATES}
            cohort["branches"][branch] = summary
        output["cohorts"][name] = cohort
    return output


def self_test():
    """Analytische Integrale und reale NPY/Parquet/Soxr-IO, nur synthetische Daten."""
    import pyarrow as pa
    passed = []
    with tempfile.TemporaryDirectory(prefix="energy-paper-selftest-") as directory:
        base = Path(directory)
        constant = np.full(10001, 30., dtype=np.float64)
        energy = linear_window_integral(constant, 10000., .12345, .87654)
        assert abs(energy - 30 * (.87654 - .12345)) < 1e-10
        e, count = sampled_window_energy(constant, 10000., .12345, .87654, 2000., .37)
        assert abs(e - energy) < 1e-10 and count >= 4
        passed.append("Konstante Leistung und fraktionale Endpunkte")
        time_axis = np.arange(10001) / 10000.
        ramp = 2. + 3. * time_axis
        expected = 2 * (.89 - .12) + 1.5 * (.89 ** 2 - .12 ** 2)
        e, _ = sampled_window_energy(ramp, 10000., .12, .89, 71., .29)
        assert abs(e - expected) < 1e-10
        passed.append("Lineare Rampe mit ungleich liegendem Zielraster")
        windows = make_windows(0., 9.999999, 10., 16)
        assert len(windows) == 1 and abs(windows[0]["shortfall_s"] - 1e-6) < 1e-12
        assert make_windows(0., 9.9, 10., 16) == []
        passed.append("10-s-Support, ausgewiesenes Dauerdefizit und Deduplizierung")
        n = 300_003
        t = np.arange(n) / FS_NATIVE
        current = 1.5 + .15 * np.cos(2 * np.pi * 600_000 * t)
        raw = current / PICO_GAIN - PICO_OFFSET_RAW
        directory = base / "scope"
        directory.mkdir()
        source = base / "pico.parquet"
        pq.write_table(pa.table({"current": raw, "voltage": np.full(n, 19.)}), source, row_group_size=70_000)
        record = {"path": source, "source": "pico", "workload": "gemmfp32"}
        native, reduced, audit = load_scope(record, directory)
        expected_power = current * (V_INTERCEPT + V_SLOPE * current)
        assert np.max(np.abs(native - expected_power)) < 1e-12
        assert audit["outside_voltage_model_range_samples"] == 0
        cmp = compare_energy_paths(native, FS_NATIVE, reduced, FS_REDUCED, (.01, .05),
                                   2000., phases=[0., 1. / 600.])
        assert all(row["eligible"] for row in cmp["rows"])
        assert min(abs(row["native_error_pct"]) for row in cmp["rows"]) > 5.
        assert max(abs(row["reduced_error_pct"]) for row in cmp["rows"]) < .01
        passed.append("Parquet-Kalibrierung und HF-Aliasing bei erhaltener Referenzenergie")
        padded = np.pad(expected_power, int(.5 * FS_NATIVE), mode="edge")
        full = soxr.resample(padded, FS_NATIVE, FS_REDUCED, quality="VHQ")
        start = int(.5 * FS_REDUCED)
        expected_reduced = full[start:start + round(n / 5)].astype(np.float32)
        assert np.array_equal(reduced, expected_reduced)
        passed.append("Streaming-VHQ gleich Ganzsignal-VHQ einschliesslich Randbehandlung")
        del native, reduced, padded, full
        gc.collect()
        y = base / "results.yaml"
        y.write_text(yaml.safe_dump({"oscilloscope_results": {"sample_rate": FS_NATIVE,
                     "use_voltage": True, "results": {"energy": 30., "duration": 101 / FS_NATIVE,
                     "start_stop_idx": [10, 110]}}}), encoding="utf-8")
        meta = parse_fp16_yaml(y, 200)
        assert meta["status"] == "ok" and meta["python_stop_exclusive"] == 111
        assert meta["integration_span_s"] == 100 / FS_NATIVE
        passed.append("YAML-Indizes inklusive; N/fs getrennt von Integrationsspanne")
        fs = 4000.
        t = np.arange(int(fs * 30)) / fs
        power = np.full(len(t), 10.)
        active = (t >= 5.) & (t <= 25.)
        power[active] = 30. + 2. * np.sin(2 * np.pi * 100. * t[active])
        psd = compute_fp16_psd(power, fs, 5., 25., window_basis="synthetic")
        assert psd["status"] == "ok", psd
        assert psd["baseline_10s_4s"]["active_welch"]["n_segments"] == 19
        assert psd["baseline_10s_4s"]["idle_welch"]["n_segments"] == 7
        assert abs(psd["baseline_10s_4s"]["metrics"]["positive_excess_variance_W2"] - 2.) < 1e-9
        assert psd["idle_split_2s_2s"]["n_segments_per_block"] == 3
        assert compute_fp16_psd(power, fs, 1., 21.)["status"] == "blocked"
        passed.append("Bekannte PSD-Varianz,19/7,7/7,3/3 und fehlender Idlebereich")
        cohort = summarize_fp16_psd_cohorts({i: psd for i in range(2, 15)})
        assert cohort["cohorts"]["paper_ids_2_to_14"]["complete"]
        assert not cohort["cohorts"]["all_ids_0_to_14"]["complete"]
        assert cohort["cohorts"]["all_ids_0_to_14"]["missing_run_ids"] == [0, 1]
        json.dumps(cohort, allow_nan=False)
        passed.append("Unvollstaendige15er-Kohorte wird nicht als vollstaendig ausgegeben")
        rate_dir = base / "data" / "tek_scope_comparison" / "gemmfp32" / "5000000Sps"
        rate_dir.mkdir(parents=True)
        for run_id in (0, 99):
            for prefix in ("tek_hsi_", "usb_osc_data_"):
                (rate_dir / (prefix + str(run_id) + ".parquet")).touch()
        found, issues, inventory = discover_scopes(base / "data", ["gemmfp32"])
        assert {r["run_id"] for r in found} == {0} and issues
        assert inventory[0]["additional_paired_ids"] == [99]
        passed.append("Exakte Paper-IDs; zusaetzlicher Run ersetzt keinen fehlenden")
        collector = rate_dir / "1"
        collector.mkdir()
        for name in ("tek_hsi.parquet", "usb_osc_data.parquet"):
            (collector / name).touch()
        other_rate = rate_dir.parent / "250000000Sps"
        other_rate.mkdir()
        for name in ("tek_hsi_1.parquet", "usb_osc_data_1.parquet"):
            (other_rate / name).touch()
        found, _, inventory = discover_scopes(base / "data", ["gemmfp32"], requested_ids=[0, 1])
        assert {r["run_id"] for r in found} == {0, 1} and len(found) == 4
        assert inventory[0]["cohort_count_matches"]
        assert all("250000000Sps" not in str(r["path"]) for r in found)
        passed.append("Collector-Unterordner erkannt; 250-MS/s-Tek-Kohorte ausgeschlossen")
    for name in passed:
        log("PASS " + name)
    log(f"{len(passed)} Selbsttests bestanden. Keine Nutzer-Rohdaten verwendet.")
    return 0


def energy_groups(records, kind="scope"):
    groups = {}
    for record in records:
        if record.get("status") != "completed" or record["kind"] != kind:
            continue
        for window in record["windows"]:
            duration = window["nominal_duration_s"]
            for comparison in window["comparisons"]:
                key = (record["workload"], record["source"], duration, comparison["rate_sps"])
                run = groups.setdefault(key, {}).setdefault(record["run_id"],
                         {"native": [], "reduced": [], "difference": [], "n_windows": 0,
                          "ineligible_offsets": 0, "actual_durations_s": [], "reference_deltas_pct": []})
                run["native"].extend(comparison["native_error_pct"])
                run["reduced"].extend(comparison["reduced_error_pct"])
                run["difference"].extend(comparison["path_difference_pct"])
                run["n_windows"] += 1
                run["ineligible_offsets"] += len(comparison["ineligible"])
                run["actual_durations_s"].append(window["actual_duration_s"])
                run["reference_deltas_pct"].append(window["reference_reduction_delta_pct"])
    return groups


def scope_summaries(records, inventory, settings):
    groups = energy_groups(records)
    run_rows, group_rows, envelope_rows = [], [], []
    wanted = {row["workload"]: set(row["requested_ids"]) for row in inventory}
    for (workload, source, duration, rate), runs in sorted(groups.items()):
        valid = {i: r for i, r in runs.items() if r["native"] and r["reduced"]}
        if not valid:
            continue
        en = hierarchical_error_summary({i: r["native"] for i, r in valid.items()})
        er = hierarchical_error_summary({i: r["reduced"] for i, r in valid.items()})
        expected = wanted.get(workload, set())
        qn, qr = en["hierarchical_q95_pct"], er["hierarchical_q95_pct"]
        row = {"workload": workload, "source": source, "nominal_duration_s": duration,
               "rate_sps": rate, "expected_ids": sorted(expected), "used_ids": sorted(valid),
               "complete_requested_cohort": set(valid) == expected,
               "n_physical_records": len(valid), "native_hierarchical_Q95_pct": qn,
               "via_1M_hierarchical_Q95_pct": qr, "native_minus_via_Q95_pp": qn - qr,
               "native_max_record_Q95_pct": en["max_record_q95_pct"],
               "via_1M_max_record_Q95_pct": er["max_record_q95_pct"],
               "max_abs_path_difference_pct": max(max(map(abs, r["difference"])) for r in valid.values()),
               "max_abs_reference_reduction_delta_pct": max(max(map(abs, r["reference_deltas_pct"])) for r in valid.values()),
               "min_actual_duration_s": min(min(r["actual_durations_s"]) for r in valid.values()),
               "max_actual_duration_s": max(max(r["actual_durations_s"]) for r in valid.values()),
               "decision_changed_at_1pct": (qn <= 1.) != (qr <= 1.),
               "decision_changed_at_0p5pct": (qn <= .5) != (qr <= .5)}
        group_rows.append(row)
        for run_id, values in valid.items():
            native = summarize_errors(values["native"])
            reduced = summarize_errors(values["reduced"])
            run_rows.append({"workload": workload, "source": source, "run_id": run_id,
                             "nominal_duration_s": duration, "rate_sps": rate,
                             "n_windows": values["n_windows"], "n_offsets_cases": native["n_valid"],
                             "ineligible_offset_cases": values["ineligible_offsets"],
                             "native_Q95_pct": native["abs_q95_pct"], "via_1M_Q95_pct": reduced["abs_q95_pct"],
                             "native_max_pct": native["abs_max_pct"], "via_1M_max_pct": reduced["abs_max_pct"],
                             "max_abs_path_difference_pct": max(map(abs, values["difference"]))})
    for duration in settings["durations"]:
        for rate in settings["rates"]:
            selected = [r for r in group_rows if r["nominal_duration_s"] == duration and r["rate_sps"] == rate]
            if not selected:
                continue
            qn = max(r["native_hierarchical_Q95_pct"] for r in selected)
            qr = max(r["via_1M_hierarchical_Q95_pct"] for r in selected)
            complete = len(selected) == 2 * len(settings["workloads"]) and all(r["complete_requested_cohort"] for r in selected)
            envelope_rows.append({"nominal_duration_s": duration, "rate_sps": rate,
                                  "n_workload_source_groups": len(selected),
                                  "complete_requested_cohort": complete,
                                  "all_six_paper_workloads_and_ids": complete and settings["workloads"] == list(WORKLOADS)
                                      and settings["run_ids"] is None,
                                  "native_envelope_Q95_pct": qn, "via_1M_envelope_Q95_pct": qr,
                                  "native_minus_via_Q95_pp": qn - qr,
                                  "decision_changed_at_1pct": (qn <= 1.) != (qr <= 1.),
                                  "decision_changed_at_0p5pct": (qn <= .5) != (qr <= .5),
                                  "claim": "only this declared sensitivity grid; no new persistent minimum rate"})
    return run_rows, group_rows, envelope_rows


def fp16_energy_summary(records):
    good = {r["run_id"]: r for r in records if r.get("status") == "completed" and r["kind"] == "fp16"}
    rows = []
    for label, expected in (("paper_ids_2_to_14", PAPER_FP16_IDS), ("all_ids_0_to_14", ALL_FP16_IDS),
                            ("additional_ids_0_and_1", (0, 1))):
        for rate in (50, 85, 2000):
            ns, rs, actual, ids, bases = [], [], [], [], []
            for run_id in expected:
                if run_id not in good:
                    continue
                record = good[run_id]
                run_native, run_reduced = [], []
                for w in record["windows"]:
                    for c in w["comparisons"]:
                        if c["rate_sps"] == rate and c["native_error_pct"]:
                            run_native.extend(c["native_error_pct"])
                            run_reduced.extend(c["reduced_error_pct"])
                            actual.append(w["actual_duration_s"])
                if run_native:
                    ns.extend(run_native)
                    rs.extend(run_reduced)
                    ids.append(run_id)
                    bases.append(record["energy_window_basis"])
            n, r = summarize_errors(ns), summarize_errors(rs)
            complete = set(ids) == set(expected)
            matched_duration = bool(actual) and min(actual) >= 104. - 2e-6 and max(actual) <= 104. + 2e-6
            rows.append({"cohort": label, "rate_sps": rate, "expected_ids": list(expected), "used_ids": ids,
                         "complete_cohort": complete, "all_intervals_104s_within_2us": matched_duration,
                         "window_bases": sorted(set(bases)), "min_duration_s": min(actual) if actual else None,
                         "max_duration_s": max(actual) if actual else None, "n_offset_cases": n["n_valid"],
                         "native_pooled_Q95_pct": n["abs_q95_pct"], "via_1M_pooled_Q95_pct": r["abs_q95_pct"],
                         "native_max_pct": n["abs_max_pct"], "via_1M_max_pct": r["abs_max_pct"],
                         "original_window_and_selection_provenance_confirmed": False})
    return rows


def fp16_psd_rows(records):
    rows = []
    for r in records:
        if r.get("status") != "completed" or r["kind"] != "fp16":
            continue
        p = r.get("psd", {})
        if p.get("status") != "ok":
            rows.append({"run_id": r["run_id"], "status": p.get("status", "missing"), "reason": p.get("reason")})
            continue
        branches = {key: p[key]["metrics"] for key in ("baseline_10s_4s", "matched_4s_4s")}
        branches.update({"idle_split_" + key: p["idle_split_2s_2s"][key]
                         for key in ("first_minus_last", "last_minus_first", "active_minus_first_idle", "active_minus_last_idle")})
        for branch, m in branches.items():
            row = {"run_id": r["run_id"], "status": "ok", "branch": branch,
                   "positive_excess_variance_W2": m["positive_excess_variance_W2"],
                   "signed_excess_variance_W2": m["signed_excess_variance_W2"],
                   "negative_excess_variance_W2": m["negative_excess_variance_W2"],
                   "f95_hz": m["f95_hz"], "f99_hz": m["f99_hz"]}
            for rate, fraction in m["coverage_by_rate"].items():
                row["coverage_pct_at_" + str(int(float(rate))) + "Sps"] = None if fraction is None else 100 * fraction
            rows.append(row)
    return rows


def report_outputs(out, records, problems, inventory, settings, metadata, interrupted=False):
    run_rows, groups, envelope = scope_summaries(records, inventory, settings)
    fp_energy = fp16_energy_summary(records) if settings["part"] != "scopes" else []
    fp_psd = fp16_psd_rows(records)
    psd_cohorts = summarize_fp16_psd_cohorts({r["run_id"]: r.get("psd", {}) for r in records
                                           if r.get("status") == "completed" and r["kind"] == "fp16"})
    write_csv(out / "scope_per_run.csv", run_rows)
    write_csv(out / "scope_groups.csv", groups)
    write_csv(out / "scope_envelope.csv", envelope)
    write_csv(out / "fp16_energy_selection.csv", fp_energy)
    write_csv(out / "fp16_psd_per_run.csv", fp_psd)
    write_json(out / "fp16_psd_selection.json", psd_cohorts)
    successful = [r for r in records if r.get("status") == "completed"]
    errors = [r for r in records if r.get("status") != "completed"]
    limitations = list(problems)
    observations = []
    if settings["part"] != "fp16" and not envelope:
        limitations.append("Keine gueltigen Scope-Vergleiche auf dem angeforderten Raster (Minimum4 Samples/Fenster).")
    if settings["part"] != "scopes" and not any(r["kind"] == "fp16" for r in successful):
        limitations.append("Keine angeforderte FP16-Aufzeichnung erfolgreich ausgewertet.")
    for r in successful:
        if r.get("unavailable_durations_s"):
            limitations.append(f"{r['workload']}/{r['source']}/{r['run_id']}: Fenster fehlen: {r['unavailable_durations_s']}")
        if r["audit"].get("outside_voltage_model_range_samples", 0):
            observations.append(f"{r['workload']}/{r['source']}/{r['run_id']}: Strom ausserhalb 0..3.5 A; Modell extrapoliert, nicht geclippt.")
        if r["kind"] == "fp16":
            if r["audit"].get("duration_consistency") == "mismatch_requires_inspection":
                observations.append(f"FP16 Run {r['run_id']}: YAML-Dauer und gespeicherte Fensterindizes sind inkonsistent; keine Anpassung erfolgt.")
            if r.get("psd", {}).get("status") != "ok":
                limitations.append(f"FP16 Run {r['run_id']}: PSD nicht berechenbar: {r.get('psd', {}).get('reason')}")
            if r["windows"][0]["actual_duration_s"] < 104. - 2e-6:
                limitations.append(f"FP16 Run {r['run_id']}: kein 104-s-Fenster innerhalb belegter YAML-Grenzen.")
            if not r["audit"].get("has_original_indices", False):
                limitations.append(f"FP16 Run {r['run_id']}: gespeichertes Gesamtarray statt belegter Originalfenster; Auswahlvergleich eingeschraenkt.")
    for r in errors:
        limitations.append(f"FEHLER {r['workload']}/{r['source']}/{r['run_id']}: {r.get('error')}")
    completed = bool(successful) and not limitations and not interrupted
    summary = {"script_version": VERSION, "status": "interrupted" if interrupted else ("completed_requested_probe" if completed else "partial_or_needs_inspection"),
               "successful_records": len(successful), "failed_records": len(errors), "limitations": limitations,
               "observed_data_notes": observations,
               "scope_inventory": inventory, "scope_envelope": envelope,
               "fp16_energy_selection": fp_energy, "fp16_psd_selection": psd_cohorts,
               "original_selection_reason": "not automatically established; see metadata evidence",
               "paper_reproduction": False,
               "active_record_files": [f"{r['kind']}_{r['workload']}_{r['source']}_{r['run_id']}.json" for r in records],
               "next_action": "Ergebnis-ZIP pruefen; keine automatische Aenderung von Paper, Kalibrierung oder Auswahl."}
    write_json(out / "summary.json", summary)
    lines = ["ENERGY-PAPER: GEZIELTE OFFLINEPRUEFUNG", "", f"Status: {summary['status']}",
             f"Fertig berechnete Quellen: {len(successful)}; Fehler: {len(errors)}", "",
             "1. Rekonstruktionsvergleich", ""]
    if envelope:
        lines.append("Dauer[s]  Rate[S/s]  Q95 nativ[%]  Q95 via1M[%]  Differenz[pp]  Kohorte vollstaendig")
        for row in envelope:
            lines.append(f"{row['nominal_duration_s']:8g} {row['rate_sps']:10g} {row['native_envelope_Q95_pct']:13.6f} "
                         f"{row['via_1M_envelope_Q95_pct']:13.6f} {row['native_minus_via_Q95_pp']:14.6f} "
                         f"{row['complete_requested_cohort']}")
        changed = [r for r in envelope if r["complete_requested_cohort"] and
                   (r["decision_changed_at_1pct"] or r["decision_changed_at_0p5pct"])]
        lines.extend(["", f"Raten-/Dauerkombinationen mit Wechsel an 0.5% oder 1%: {len(changed)}.",
                      "Kein Wechsel auf diesem Raster ist keine allgemeine Gleichheit aller Signale oder Offsets."])
    else:
        lines.append("Keine Scope-Huelle berechenbar/angefordert.")
    lines.extend(["", "2. FP16: IDs 2..14 und alle IDs 0..14", ""])
    for row in fp_energy:
        if row["cohort"] == "additional_ids_0_and_1":
            continue
        nq, rq = row["native_pooled_Q95_pct"], row["via_1M_pooled_Q95_pct"]
        lines.append(f"{row['cohort']}, {row['rate_sps']} S/s: n={len(row['used_ids'])}, "
                     f"Q95 nativ={nq}, via1M={rq}; 104-s-Fenster={row['all_intervals_104s_within_2us']}")
    lines.extend(["", "Die Auswahlbegruendung wird aus Messwerten nicht erfunden. Gefundene Originalconfigs",
                  "und Auswahl-/Fensterhinweise stehen in metadata/ und metadata_evidence.json.",
                  "IDs 0/1 werden nicht getrimmt. Fehlende Runs werden als fehlend ausgewiesen.", "",
                  "3. FP16-Spektren", "",
                  "fp16_psd_per_run.csv: aktive10s/idle4s (19/7 Welchsegmente),",
                  "aktive4s/idle4s (7/7), disjunkte idle2s/idle2s (3/3) in beiden Richtungen.",
                  "Die 2-s-Blockpruefung ist deskriptiv und keine unabhaengige Messkampagne,",
                  "kein Signifikanztest und keine automatische Korrektur der positiven PSD-Differenz.", "",
                  "4. Festgelegte Methode dieses Zusatzchecks", "",
                  "* Beide Zielrasterintegrale gegen dieselbe native Referenzenergie.",
                  "* Leistung zuerst bilden; erst danach VHQ von 5 MS/s auf 1 MS/s.",
                  "* Ganze Aufzeichnung filtern; 0.5 s konstante Randfortsetzung entfernen.",
                  "* Native Leistung Float64, reduzierte Darstellung Float32. Keine Zielratenfilterung.",
                  "* Gleichmaessig verteilte, unterschiedliche Fenster; alle Zeitgrenzen gespeichert.",
                  "* Quell-Endpunkte interpoliert; gleiche Endpunktregel in beiden Zweigen.",
                  "* Endpunkte zaehlen nicht als zusaetzliche Zielraster-Samples (Minimum4).",
                  "* Gemeinsamer gemessener Support; maximal2us Defizit einer Nenndauer explizit ausgewiesen.",
                  "* Scope: Q95 ueber Fenster/Offsets je Run, dann Q95 ueber physische Runs.",
                  "* FP16: gepooltes Q95 der Run-/Offsetfaelle; verwendete Lauf-IDs immer ausgewiesen.",
                  "* Quantile: NumPy method='linear'; Perzentile sind keine Konfidenzintervalle.",
                  "* Scope-Pico: (raw_current + 0.0004272598504) * 1.99000512058047.",
                  "* Scope-Tek YOLO-FP32: +0.111917 A, gerundeter KB-Wert; kein neuer Fit.",
                  "* Scope-Leistung: I * (19.062607082705 - 0.07444582 * I).",
                  "* FP16 oscilloscope.npy: gespeicherte Wattwerte, keine Rekalibrierung.",
                  "* FP16-Fensterbasis: inklusive YAML-Indizes;104s zentral wenn verfuegbar,",
                  "  sonst kuerzeres belegtes Fenster klar markiert. Urspruengliche104s-Lage unbestaetigt.",
                  "* Dies ist eine neue Sensitivitaetsauswertung. Keine exakte Table2-Reproduktion.", "",
                  "5. Noch zu pruefen / fehlende Eingaben", ""])
    lines.extend(limitations or ["Keine zusaetzlichen Dateifehler oder Laufblockaden im angeforderten Check."])
    if observations:
        lines.extend(["", "Beobachtete Datenhinweise (Rechenlauf ausgefuehrt):"] + observations)
    lines.extend(["", "Die historische FP16-Auswahlbegruendung und Gleichheit zum urspruenglichen",
                  "Fenster-/Offsetgitter brauchen weiterhin einen Blick in die mitgesicherten Metadaten.",
                  "", "Quellen:"] + SOURCE_URLS)
    (out / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def make_zip(out, include_results=True):
    target = out.parent / (out.name + ".zip")
    temporary = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        allowed = {"REPORT.txt", "run_settings.json", "environment.json", "input_inventory.json", "metadata_evidence.json"}
        if include_results:
            allowed.update({"summary.json", "scope_per_run.csv", "scope_groups.csv", "scope_envelope.csv",
                            "fp16_energy_selection.csv", "fp16_psd_per_run.csv", "fp16_psd_selection.json"})
        candidates = [out / name for name in allowed]
        candidates.extend((out / "metadata").glob("[0-9][0-9][0-9]_*"))
        if include_results:
            state = read_small_json(out / "summary.json") or {}
            candidates.extend(out / "records" / name for name in state.get("active_record_files", [])
                              if Path(name).name == name and name.endswith(".json"))
        for path in sorted(candidates):
            if path.is_file() and not path.is_symlink():
                z.write(path, arcname=str(Path(out.name) / path.relative_to(out)))
    temporary.replace(target)
    return target


def positive_list(text, integral=False):
    vals = [float(x.strip()) for x in text.split(",") if x.strip()]
    if not vals or any(not math.isfinite(v) or v <= 0 for v in vals):
        raise argparse.ArgumentTypeError("Kommagetrennte positive endliche Zahlen erforderlich.")
    if integral and any(v != int(v) for v in vals):
        raise argparse.ArgumentTypeError("Ganzzahlige Raten erforderlich.")
    return sorted(set(int(v) if integral else v for v in vals))


def parser():
    p = argparse.ArgumentParser(description="Gezielter Energy-Paper-Check aus vorhandenen Rohdaten; schreibt nur neue Ergebnisse.")
    p.add_argument("--data-root", type=Path, default=Path("external-measurements"))
    p.add_argument("--scope-root", type=Path, default=None,
                   help="Optionaler Ordner mit den sechs Scope-Workloads; sonst DATA_ROOT/tek_scope_comparison.")
    p.add_argument("--analysis-root", type=Path, default=Path("external-analysis"))
    p.add_argument("--out", type=Path, default=Path("energy-raw-analysis"))
    p.add_argument("--scratch-dir", type=Path, default=Path(tempfile.gettempdir()), help="Temporaerer Platz fuer genau eine Aufnahme.")
    p.add_argument("--part", choices=("all", "scopes", "fp16"), default="all")
    p.add_argument("--inspect", action="store_true", help="Nur Pfade/Metadaten pruefen, keine grossen Zeitreihen lesen.")
    p.add_argument("--self-test", action="store_true", help="Kurze analytische und IO-Selbsttests, keine Nutzer-Rohdaten.")
    p.add_argument("--full-grid", action="store_true", help="Alle19 Originalraten,9 Dauern,64Offsets; laengerer Rechenlauf.")
    p.add_argument("--rates", type=lambda x: positive_list(x, True), default=[2000, 9400, 16000])
    p.add_argument("--durations", type=positive_list, default=[.02, .1, 1., 2., 5., 10.])
    p.add_argument("--windows", type=int, default=16)
    p.add_argument("--offsets", type=int, default=32)
    p.add_argument("--workloads", default=",".join(WORKLOADS))
    p.add_argument("--run-ids", default=None, help="Optionale explizite Teilmenge, z.B.0,1; als Teilmenge gekennzeichnet.")
    return p


def main():
    args = parser().parse_args()
    dependencies()
    if args.self_test:
        return self_test()
    args.data_root, args.analysis_root, args.out, args.scratch_dir = (
        p.expanduser().resolve() for p in (args.data_root, args.analysis_root, args.out, args.scratch_dir))
    args.scope_root = (args.scope_root.expanduser().resolve() if args.scope_root is not None
                       else args.data_root / "tek_scope_comparison")
    input_roots = (args.data_root, args.analysis_root, args.scope_root)
    if any(args.out.is_relative_to(root) for root in input_roots):
        raise ValueError("Ergebnisordner muss ausserhalb der Rohdaten und vorhandenen Analysebaeume liegen.")
    if any(args.scratch_dir.is_relative_to(root) for root in input_roots):
        raise ValueError("Temporaerer Arbeitsordner muss ausserhalb der Eingabebaeume liegen.")
    workloads = list(dict.fromkeys(x.strip() for x in args.workloads.split(",") if x.strip()))
    if not workloads or any(w not in WORKLOADS for w in workloads):
        raise ValueError("Unbekannter Workload; gueltig: " + ", ".join(WORKLOADS))
    run_ids = None
    if args.run_ids is not None:
        if not re.fullmatch(r"\d+(?:\s*,\s*\d+)*", args.run_ids):
            raise ValueError("Run-IDs als nichtnegative ganze Zahlen mit Komma angeben.")
        run_ids = sorted(set(int(i) for i in args.run_ids.split(",")))
    if not 1 <= args.windows <= 64 or not 1 <= args.offsets <= 256:
        raise ValueError("windows muss1..64 und offsets1..256 sein.")
    rates = list(FULL_RATES) if args.full_grid else args.rates
    durations = list(FULL_DURATIONS) if args.full_grid else args.durations
    offsets = 64 if args.full_grid else args.offsets
    if max(rates) > FS_REDUCED:
        raise ValueError("Zielraten muessen <=1 MS/s sein.")
    versions = {n: importlib.metadata.version(n) for n in ("numpy", "scipy", "soxr", "pyarrow", "pyyaml")}
    settings = {"script_version": VERSION, "package_versions": versions, "part": args.part, "data_root": str(args.data_root),
                "scope_root": str(args.scope_root),
                "analysis_root": str(args.analysis_root), "rates": rates, "durations": durations,
                "windows": args.windows, "offsets": offsets, "workloads": workloads, "run_ids": run_ids,
                "native_fs": FS_NATIVE, "reduced_fs": FS_REDUCED, "resample_quality": "VHQ",
                "filter_guard_s": .5, "filter_guard_mode": "constant endpoint extension then remove",
                "endpoint_mode": "source", "quantile_method": "linear",
                "native_dtype": "float64", "reduced_dtype": "float32",
                "fp16_rates": [50, 85, 2000], "fp16_offsets": 64}
    previous = read_small_json(args.out / "run_settings.json")
    if previous is not None and previous != settings:
        raise ValueError("Dieser Ergebnisordner gehoert zu anderen Einstellungen/Skriptversion. Anderen --out waehlen.")
    if args.out.exists() and previous is None and any(args.out.iterdir()):
        raise ValueError("Ergebnisordner ist belegt und gehoert nicht zu diesem Skript; anderen --out waehlen.")
    args.out.mkdir(parents=True, exist_ok=True)
    args.scratch_dir.mkdir(parents=True, exist_ok=True)
    (args.out / "records").mkdir(exist_ok=True)
    write_json(args.out / "run_settings.json", settings)
    write_json(args.out / "environment.json", {"python": sys.version, "packages": versions})
    log("Pruefe die dokumentierten Datenpfade und kleine Analysemetadaten.")
    try:
        metadata = metadata_evidence(args.analysis_root, args.out)
    except OSError as exc:
        metadata = {"found": [], "selection_and_window_excerpts": [], "local_analysis_code_excerpts": [],
                    "search_roots": [directory_overview(args.analysis_root)],
                    "collection_error": f"{type(exc).__name__}: {exc}",
                    "selection_reason": "Originalmetadaten nicht vollstaendig lesbar; Auswahlgrund bleibt offen."}
        write_json(args.out / "metadata_evidence.json", metadata)
        log("Analysemetadaten nicht vollstaendig lesbar; Details in metadata_evidence.json.")
    records, problems, inventory = [], [], []
    if args.part != "fp16":
        scope, issues, inventory = discover_scopes(args.data_root, workloads, run_ids, args.scope_root)
        records.extend(scope)
        problems.extend(issues)
    if args.part != "scopes":
        fp16, issues = discover_fp16(args.data_root, run_ids)
        records.extend(fp16)
        problems.extend(issues)
    write_json(args.out / "input_inventory.json", {"scope_cohorts": inventory, "records": records, "problems": problems})
    log(f"Gefunden: {len(records)} Quelldateien; {len(problems)} Hinweise zu fehlenden Eingaben.")
    if args.part != "fp16":
        log(f"Scope: {sum(len(x['evaluated_ids']) for x in inventory)} Run-Paare; Pfaddiagnose in input_inventory.json.")
    for issue in problems[:12]:
        log(issue)
    if args.inspect:
        (args.out / "REPORT.txt").write_text("Nur Eingangspruefung; keine Rohdatenanalyse ausgefuehrt.\n" +
                                               "\n".join(problems) + "\n", encoding="utf-8")
        archive = make_zip(args.out, include_results=False)
        log(f"Eingangspruefung: {archive}")
        return 2 if problems or not records else 0
    results = []
    interrupted = False
    try:
        for index, record in enumerate(records, 1):
            name = f"{record['kind']}_{record['workload']}_{record['source']}_{record['run_id']}"
            target = args.out / "records" / (name + ".json")
            saved = read_small_json(target, limit=200_000_000)
            unchanged = saved and saved.get("status") == "completed" and saved.get("input") == file_stamp(record["path"])
            if unchanged and record["kind"] == "fp16":
                unchanged = saved.get("metadata_input") == file_stamp(record["yaml_path"])
            if unchanged:
                results.append(saved)
                log(f"[{index}/{len(records)}] vorhanden: {name}")
                continue
            log(f"[{index}/{len(records)}] berechne {name}")
            try:
                before = file_stamp(record["path"])
                yaml_before = file_stamp(record["yaml_path"]) if record["kind"] == "fp16" else None
                with tempfile.TemporaryDirectory(prefix="energy-paper-work-", dir=args.scratch_dir) as work:
                    answer = run_record(record, Path(work), settings)
                if before != file_stamp(record["path"]) or (yaml_before is not None and yaml_before != file_stamp(record["yaml_path"])):
                    raise ValueError("Eingabedatei waehrend der Auswertung geaendert; Ergebnis nicht uebernommen.")
                write_json(target, answer)
                results.append(answer)
                log(f"Fertig in {answer['elapsed_s']:.1f} s")
            except (OSError, ValueError, RuntimeError, KeyError, MemoryError) as exc:
                answer = {k: record[k] for k in ("kind", "workload", "source", "run_id")}
                answer.update(status="failed", input=file_stamp(record["path"]), error=str(exc),
                              traceback=traceback.format_exc())
                write_json(target, answer)
                results.append(answer)
                log("Nicht berechnet: " + str(exc))
    except KeyboardInterrupt:
        interrupted = True
        log("Unterbrochen. Fertige Aufzeichnungen bleiben fuer den naechsten Aufruf gespeichert.")
    summary = report_outputs(args.out, results, problems, inventory, settings, metadata, interrupted)
    archive = make_zip(args.out)
    log(f"Bericht: {args.out / 'REPORT.txt'}")
    log(f"Ergebnis-ZIP: {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
    log("Status: " + summary["status"])
    return 130 if interrupted else (0 if summary["status"] == "completed_requested_probe" else 2)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print("Fehler: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
