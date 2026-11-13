from __future__ import annotations

import copy
import csv
import fcntl
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from . import __version__
from .utils import (
    LOGGER,
    load_yaml,
    normalise_for_json,
    read_json,
    stable_hash,
    utc_now_iso,
    write_csv,
    write_json,
)


_AUTO_PIPELINE_SCHEMA_VERSION = 1
_RATE_DIRECTORY_RE = re.compile(r"^(?P<rate>\d+)(?:Sps)?$")
_RUN_FILE_RE = re.compile(r"^(?P<prefix>tek_hsi|usb_osc_data)_(?P<run>\d+)\.parquet$")
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class AutoPipelineConfig:
    config_path: Path
    tool_root: Path
    dataset_root: Path
    analysis_root: Path
    state_root: Path
    idle_directory_name: str
    base_multi_workload_config: Path
    generic_scope_template: Path
    known_scope_configs: dict[str, Path]
    workload_metadata: dict[str, dict[str, Any]]
    exclude_directories: tuple[str, ...]
    common_rate_sps: int
    minimum_paired_runs_any_rate: int
    minimum_paired_runs_common_rate: int
    continue_on_error: bool
    skip_fresh_scope: bool
    skip_fresh_multi: bool
    generate_artifacts: bool


@dataclass(frozen=True)
class DiscoveredWorkload:
    workload_id: str
    label: str
    family: str
    precision: str
    dataset_root: Path
    scope_output_root: Path
    scope_template: Path
    scope_config: Path
    include_in_paper: bool
    notes: str
    rate_count: int
    paired_runs_total: int
    common_rate_paired_runs: int
    rate_inventory: tuple[dict[str, Any], ...]
    metadata_source: str
    scope_overrides: dict[str, Any]
    sort_order: int


@dataclass(frozen=True)
class PipelineStageResult:
    workload_id: str
    label: str
    stage: str
    status: str
    reason: str
    output_root: str
    source_fingerprint: str
    command: tuple[str, ...]


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _safe_id(value: str) -> str:
    text = _SAFE_ID_RE.sub("_", str(value)).strip("_.-")
    return text or "workload"


def _parse_rate_directory(name: str) -> int | None:
    match = _RATE_DIRECTORY_RE.fullmatch(name)
    return int(match.group("rate")) if match else None


def _run_ids(directory: Path, prefix: str) -> set[int]:
    result: set[int] = set()
    for path in directory.glob(f"{prefix}_*.parquet"):
        match = _RUN_FILE_RE.fullmatch(path.name)
        if match and match.group("prefix") == prefix:
            result.add(int(match.group("run")))
    return result


def _rate_inventory(dataset_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for directory in sorted(dataset_root.iterdir(), key=lambda item: item.name):
        if not directory.is_dir():
            continue
        rate = _parse_rate_directory(directory.name)
        if rate is None:
            continue
        tek = _run_ids(directory, "tek_hsi")
        pico = _run_ids(directory, "usb_osc_data")
        paired = sorted(tek & pico)
        rows.append(
            {
                "rate_sps": int(rate),
                "directory": str(directory),
                "directory_name": directory.name,
                "tek_runs": len(tek),
                "pico_runs": len(pico),
                "paired_runs": len(paired),
                "paired_run_ids": paired,
                "missing_tek_run_ids": sorted(pico - tek),
                "missing_pico_run_ids": sorted(tek - pico),
            }
        )
    return sorted(rows, key=lambda row: int(row["rate_sps"]))


def _humanise_unknown(directory_name: str) -> tuple[str, str, str]:
    lower = directory_name.lower()
    precision_match = re.search(r"(tf32|fp64|fp32|fp16|bf16|int16|int8)", lower)
    precision = precision_match.group(1).upper() if precision_match else "unspecified"

    if lower.startswith("gemm"):
        family = "GEMM"
    elif lower.startswith("yolo"):
        family = "YOLO"
    elif lower.startswith("resnet"):
        number = re.search(r"resnet[-_ ]?(\d+)", lower)
        family = f"ResNet-{number.group(1)}" if number else "ResNet"
    elif lower.startswith("gemma"):
        family = re.sub(r"^gemma", "Gemma", directory_name, flags=re.IGNORECASE)
        family = family.replace("_", "-")
    else:
        family = re.sub(r"[_-]+", " ", directory_name).strip().title()

    if precision != "unspecified" and precision.lower() not in family.lower():
        label = f"{family}-{precision}" if family in {"GEMM", "YOLO"} else f"{family} {precision}"
    else:
        label = family
    return label, family, precision


def _default_metadata(directory_name: str) -> dict[str, Any]:
    known: dict[str, dict[str, Any]] = {
        "gemmfp32": {
            "label": "GEMM-FP32",
            "family": "GEMM",
            "precision": "FP32",
            "sort_order": 10,
        },
        "gemmint8": {
            "label": "GEMM-INT8",
            "family": "GEMM",
            "precision": "INT8",
            "sort_order": 11,
        },
        "yolofp32": {
            "label": "YOLO-FP32",
            "family": "YOLO",
            "precision": "FP32",
            "sort_order": 20,
        },
        "yoloint8": {
            "label": "YOLO-INT8",
            "family": "YOLO",
            "precision": "INT8",
            "sort_order": 21,
        },
        "gemma3-4b": {
            "label": "Gemma3-4B",
            "family": "Gemma3-4B",
            "precision": "unspecified",
            "sort_order": 30,
        },
        "resnet50": {
            "label": "ResNet-50 FP32",
            "family": "ResNet-50",
            "precision": "FP32",
            "sort_order": 40,
        },
    }
    if directory_name in known:
        return dict(known[directory_name])
    label, family, precision = _humanise_unknown(directory_name)
    return {
        "label": label,
        "family": family,
        "precision": precision,
        "sort_order": 1000,
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_auto_pipeline_config(path: Path) -> AutoPipelineConfig:
    data = load_yaml(path)
    base = path.resolve().parent
    tool_root = base

    known_raw = data.get("known_scope_configs", {})
    if not isinstance(known_raw, dict):
        raise ValueError("known_scope_configs must be a mapping")
    known = {
        str(key): _resolve(base, value)
        for key, value in known_raw.items()
    }
    metadata = data.get("workload_metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("workload_metadata must be a mapping")

    discovery = data.get("discovery", {})
    execution = data.get("execution", {})
    if not isinstance(discovery, dict) or not isinstance(execution, dict):
        raise ValueError("discovery and execution must be mappings")

    state_root = _resolve(
        base,
        data.get(
            "state_root",
            "external-analysis/edge_ai_auto_pipeline_v1",
        ),
    )
    return AutoPipelineConfig(
        config_path=path.resolve(),
        tool_root=tool_root,
        dataset_root=_resolve(
            base,
            data.get(
                "dataset_root",
                "external-measurements/tek_scope_comparison",
            ),
        ),
        analysis_root=_resolve(
            base,
            data.get("analysis_root", "external-analysis"),
        ),
        state_root=state_root,
        idle_directory_name=str(data.get("idle_directory_name", "idle")),
        base_multi_workload_config=_resolve(
            base, data.get("base_multi_workload_config", "config_multi_workload.yaml")
        ),
        generic_scope_template=_resolve(
            base, data.get("generic_scope_template", "config_scope_resnet50.yaml")
        ),
        known_scope_configs=known,
        workload_metadata={str(key): dict(value) for key, value in metadata.items()},
        exclude_directories=tuple(
            str(item)
            for item in discovery.get("exclude_directories", ["idle"])
        ),
        common_rate_sps=int(discovery.get("common_rate_sps", 5_000_000)),
        minimum_paired_runs_any_rate=int(
            discovery.get("minimum_paired_runs_any_rate", 1)
        ),
        minimum_paired_runs_common_rate=int(
            discovery.get("minimum_paired_runs_common_rate", 5)
        ),
        continue_on_error=bool(execution.get("continue_on_error", True)),
        skip_fresh_scope=bool(execution.get("skip_fresh_scope", True)),
        skip_fresh_multi=bool(execution.get("skip_fresh_multi", True)),
        generate_artifacts=bool(execution.get("generate_artifacts", True)),
    )


def _metadata_for(cfg: AutoPipelineConfig, dataset_root: Path) -> tuple[dict[str, Any], str]:
    metadata = _default_metadata(dataset_root.name)
    source = "built_in_name_inference"
    override = cfg.workload_metadata.get(dataset_root.name)
    if override:
        metadata = _deep_merge(metadata, override)
        source = "config_override"
    sidecar = dataset_root / "workload_metadata.yaml"
    if sidecar.is_file():
        sidecar_data = load_yaml(sidecar)
        metadata = _deep_merge(metadata, sidecar_data)
        source = "dataset_sidecar"
    return metadata, source


def _template_for(
    cfg: AutoPipelineConfig,
    workload_id: str,
    metadata: dict[str, Any],
) -> Path:
    explicit = metadata.get("scope_template")
    if explicit:
        return _resolve(cfg.config_path.parent, explicit)
    return cfg.known_scope_configs.get(workload_id, cfg.generic_scope_template)


def _scope_output_root(cfg: AutoPipelineConfig, workload_id: str, metadata: dict[str, Any]) -> Path:
    explicit = metadata.get("scope_output_root")
    if explicit:
        return _resolve(cfg.config_path.parent, explicit)
    return cfg.analysis_root / f"tek_scope_comparison_{_safe_id(workload_id).replace('-', '_')}_v1"


def _scope_config_path(cfg: AutoPipelineConfig, workload_id: str) -> Path:
    return cfg.state_root / "generated_configs" / f"config_scope_{_safe_id(workload_id)}.yaml"


def discover_workloads(cfg: AutoPipelineConfig) -> list[DiscoveredWorkload]:
    if not cfg.dataset_root.is_dir():
        raise FileNotFoundError(cfg.dataset_root)
    cfg.state_root.mkdir(parents=True, exist_ok=True)
    discovered: list[DiscoveredWorkload] = []
    excludes = set(cfg.exclude_directories) | {cfg.idle_directory_name}
    for child in sorted(cfg.dataset_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name.startswith(".") or child.name in excludes:
            continue
        rate_rows = _rate_inventory(child)
        paired_total = sum(int(row["paired_runs"]) for row in rate_rows)
        if paired_total < cfg.minimum_paired_runs_any_rate:
            continue
        metadata, metadata_source = _metadata_for(cfg, child)
        workload_id = str(metadata.get("id", child.name)).strip() or child.name
        label = str(metadata.get("label", workload_id))
        family = str(metadata.get("family", label))
        precision = str(metadata.get("precision", "unspecified"))
        common_pairs = next(
            (
                int(row["paired_runs"])
                for row in rate_rows
                if int(row["rate_sps"]) == cfg.common_rate_sps
            ),
            0,
        )
        discovered.append(
            DiscoveredWorkload(
                workload_id=workload_id,
                label=label,
                family=family,
                precision=precision,
                dataset_root=child.resolve(),
                scope_output_root=_scope_output_root(cfg, workload_id, metadata).resolve(),
                scope_template=_template_for(cfg, workload_id, metadata).resolve(),
                scope_config=_scope_config_path(cfg, workload_id).resolve(),
                include_in_paper=bool(metadata.get("include_in_paper", True)),
                notes=str(
                    metadata.get(
                        "notes",
                        "Automatically discovered paired Tektronix/PicoScope campaign.",
                    )
                ),
                rate_count=len(rate_rows),
                paired_runs_total=paired_total,
                common_rate_paired_runs=common_pairs,
                rate_inventory=tuple(rate_rows),
                metadata_source=metadata_source,
                scope_overrides=dict(metadata.get("scope_overrides", {})),
                sort_order=int(metadata.get("sort_order", 1000)),
            )
        )
    return sorted(
        discovered,
        key=lambda item: (item.sort_order, item.family.lower(), item.precision, item.workload_id),
    )


def _generic_scope_overrides(cfg: AutoPipelineConfig, workload: DiscoveredWorkload) -> dict[str, Any]:
    idle_root = cfg.dataset_root / cfg.idle_directory_name
    return {
        "dataset_root": str(workload.dataset_root),
        "output_root": str(workload.scope_output_root),
        "rate_directories": "auto",
        "dataset": {
            "id": workload.workload_id,
            "workload_label": workload.label,
            "analysis_role": "paired_scope_validation",
            "signal_label": "estimated power derived from calibrated current",
        },
        "external_idle": {
            "enabled": idle_root.is_dir(),
            "dataset_root": str(idle_root.resolve()),
            "matching_policy": "exact_directory_rate",
            "minimum_pairs": 5,
            "use_for_psd_when_same_run_unavailable": True,
            "use_for_baseline_diagnostics": True,
            "use_for_incremental_energy": True,
            "maximum_idle_current_difference_ma": 50.0,
        },
        "zero_offset_correction": {
            "enabled": idle_root.is_dir(),
            "target_source": "tek",
            "detection_source": "workload_minus_external_idle_rate_medians",
            "application_scope": "workload_only",
            "apply_when_detected": True,
            "minimum_reference_rates": 2,
            "minimum_reference_pairs_total": 10,
            "minimum_abs_offset_ma": 50.0,
            "maximum_abs_correction_ma": 500.0,
            "maximum_rate_median_deviation_ma": 10.0,
            "maximum_rate_q95_span_ma": 15.0,
            "minimum_sign_consistency_fraction": 1.0,
            "preserve_raw_metrics": True,
        },
        "analysis_windows": {
            "shared_anchor_mode": "fixed_time",
            "trigger_time_s": 0.0,
            "trigger_fraction": "auto",
            "trigger_time_by_rate_s": {},
            "mode": "full",
            "detection_smoothing_ms": 20.0,
            "threshold_fraction": 0.30,
            "guard_after_trigger_s": 0.0,
            "idle_gap_s": 0.0,
            "idle_duration_s": 0.0,
            "stop_margin_s": 0.0,
            "minimum_active_duration_s": 0.05,
            "step_detector_diagnostics": False,
        },
    }


def generate_scope_config(cfg: AutoPipelineConfig, workload: DiscoveredWorkload) -> Path:
    if not workload.scope_template.is_file():
        raise FileNotFoundError(workload.scope_template)
    template = load_yaml(workload.scope_template)
    is_known = workload.workload_id in cfg.known_scope_configs
    if is_known:
        # Preserve all established, dataset-specific scientific decisions and
        # only bind the discovered paths and current label.
        overrides: dict[str, Any] = {
            "dataset_root": str(workload.dataset_root),
            "output_root": str(workload.scope_output_root),
            "dataset": {
                "id": workload.workload_id,
                "workload_label": workload.label,
            },
        }
        idle_root = cfg.dataset_root / cfg.idle_directory_name
        if isinstance(template.get("external_idle"), dict):
            overrides["external_idle"] = {"dataset_root": str(idle_root.resolve())}
    else:
        # New campaigns use the current acquisition contract: GPIO at the left
        # record edge, complete record as load, exact-rate external idle, and
        # adaptive additive Tek zero correction with raw values preserved.
        overrides = _generic_scope_overrides(cfg, workload)

    scope_overrides = workload.scope_overrides
    if scope_overrides and not isinstance(scope_overrides, dict):
        raise ValueError(
            f"Scope overrides for {workload.workload_id} must be a mapping"
        )
    effective = _deep_merge(template, overrides)
    if scope_overrides:
        effective = _deep_merge(effective, scope_overrides)
    workload.scope_config.parent.mkdir(parents=True, exist_ok=True)
    with workload.scope_config.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(effective, handle, sort_keys=False, allow_unicode=True)
    return workload.scope_config


def generate_multi_workload_config(
    cfg: AutoPipelineConfig,
    workloads: Sequence[DiscoveredWorkload],
    stage_results: Sequence[PipelineStageResult] | None = None,
) -> Path:
    if not cfg.base_multi_workload_config.is_file():
        raise FileNotFoundError(cfg.base_multi_workload_config)
    data = load_yaml(cfg.base_multi_workload_config)
    if "analysis_template_config" in data:
        data["analysis_template_config"] = str(
            _resolve(
                cfg.base_multi_workload_config.parent,
                data["analysis_template_config"],
            )
        )
    successful: set[str] | None = None
    if stage_results is not None:
        successful = {
            row.workload_id
            for row in stage_results
            if row.stage == "scope" and row.status in {"completed", "fresh_reused"}
        }
    rows: list[dict[str, Any]] = []
    for workload in workloads:
        enabled: str | bool = "auto"
        if successful is not None and workload.workload_id not in successful:
            enabled = False
        rows.append(
            {
                "id": workload.workload_id,
                "label": workload.label,
                "family": workload.family,
                "precision": workload.precision,
                "scope_config": str(workload.scope_config),
                "enabled": enabled,
                "include_in_paper": workload.include_in_paper,
                "notes": workload.notes,
            }
        )
    data["workloads"] = rows
    target = cfg.state_root / "generated_configs" / "config_multi_workload_auto.yaml"
    if target.is_file() and "analysis_template_config" in data:
        try:
            old = load_yaml(target).get("analysis_template_config")
            if old and Path(old).is_file() and Path(old).read_bytes() == Path(data["analysis_template_config"]).read_bytes():
                data["analysis_template_config"] = old
        except (OSError, ValueError, TypeError):
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
    return target


def _file_stat_rows(root: Path, patterns: Sequence[str]) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for pattern in patterns:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            stat = path.stat()
            rows.append(
                {
                    "path": str(path.relative_to(root)),
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                    "ctime_ns": int(stat.st_ctime_ns),
                    "inode": int(stat.st_ino),
                    "device": int(stat.st_dev),
                }
            )
    unique = {row["path"]: row for row in rows}
    return [unique[key] for key in sorted(unique)]



def _numeric_cache_version(state_path: Path) -> str:
    """Retain the version token of a compatible completed numerical cache.

    v0.9.0 adds journal-only analysis; it does not change the legacy numerical
    implementations. Compare CURRENT input/config fingerprints with the old
    token, rather than invalidating them merely due to the display version.
    """
    try:
        state = read_json(state_path)
        version = str(state.get("numeric_cache_version", state.get("tool_version", "")))
        if version in {"0.8.1", "0.8.2", "0.9.0"}:
            return version
    except (OSError, ValueError, TypeError):
        pass
    return __version__

def _scope_fingerprint(cfg: AutoPipelineConfig, workload: DiscoveredWorkload) -> str:
    scope_yaml = load_yaml(workload.scope_config)
    idle_root = cfg.dataset_root / cfg.idle_directory_name
    return stable_hash(
        {
            "schema": _AUTO_PIPELINE_SCHEMA_VERSION,
            "tool_version": _numeric_cache_version(_scope_state_path(cfg, workload.workload_id)),
            "scope_config": scope_yaml,
            "dataset_files": _file_stat_rows(
                workload.dataset_root,
                ["tek_hsi_*.parquet", "usb_osc_data_*.parquet", "workload_metadata.yaml"],
            ),
            "idle_files": _file_stat_rows(
                idle_root,
                ["tek_hsi_*.parquet", "usb_osc_data_*.parquet"],
            ),
        }
    )


def _scope_state_path(cfg: AutoPipelineConfig, workload_id: str) -> Path:
    return cfg.state_root / "state" / "workloads" / f"{_safe_id(workload_id)}.json"


def _scope_outputs_complete(workload: DiscoveredWorkload) -> bool:
    return (
        (workload.scope_output_root / "SCOPE_COMPARISON_SUMMARY.md").is_file()
        and (workload.scope_output_root / "scope_comparison_manifest.json").is_file()
        and (
            workload.scope_output_root
            / "paper_artifacts"
            / "SCOPE_PAPER_ARTIFACTS_SUMMARY.md"
        ).is_file()
    )


def _scope_fresh(cfg: AutoPipelineConfig, workload: DiscoveredWorkload, fingerprint: str) -> bool:
    state_path = _scope_state_path(cfg, workload.workload_id)
    if not state_path.is_file() or not _scope_outputs_complete(workload):
        return False
    try:
        state = read_json(state_path)
    except Exception:
        return False
    return state.get("source_fingerprint") == fingerprint and state.get("status") == "completed"


def _run_subprocess(command: Sequence[str], cwd: Path) -> tuple[int, str]:
    LOGGER.info("Executing: %s", " ".join(command))
    completed = subprocess.run(list(command), cwd=str(cwd), check=False)
    return int(completed.returncode), "completed" if completed.returncode == 0 else f"exit_{completed.returncode}"


def _write_scope_state(
    cfg: AutoPipelineConfig,
    workload: DiscoveredWorkload,
    fingerprint: str,
    command: Sequence[str],
) -> None:
    path = _scope_state_path(cfg, workload.workload_id)
    write_json(
        path,
        {
            "schema_version": _AUTO_PIPELINE_SCHEMA_VERSION,
            "created_utc": utc_now_iso(),
            "tool_version": __version__,
            "numeric_cache_version": _numeric_cache_version(_scope_state_path(cfg, workload.workload_id)),
            "workload_id": workload.workload_id,
            "workload_label": workload.label,
            "dataset_root": str(workload.dataset_root),
            "scope_config": str(workload.scope_config),
            "scope_output_root": str(workload.scope_output_root),
            "source_fingerprint": fingerprint,
            "command": list(command),
            "status": "completed",
        },
    )


def _run_scope_stage(
    cfg: AutoPipelineConfig,
    workload: DiscoveredWorkload,
    *,
    force: bool,
    verbose: bool,
) -> PipelineStageResult:
    fingerprint = _scope_fingerprint(cfg, workload)
    if cfg.skip_fresh_scope and not force and _scope_fresh(cfg, workload, fingerprint):
        LOGGER.info("Scope analysis fresh; reusing %s", workload.label)
        return PipelineStageResult(
            workload_id=workload.workload_id,
            label=workload.label,
            stage="scope",
            status="fresh_reused",
            reason="source_and_config_fingerprint_match",
            output_root=str(workload.scope_output_root),
            source_fingerprint=fingerprint,
            command=(),
        )

    command = [
        sys.executable,
        "-m",
        "commonref.cli",
        "scope-compare",
        "--config",
        str(workload.scope_config),
    ]
    if force:
        command.append("--force")
    if verbose:
        command.append("--verbose")
    returncode, reason = _run_subprocess(command, cfg.tool_root)
    if returncode == 0:
        _write_scope_state(cfg, workload, fingerprint, command)
        status = "completed"
    else:
        status = "failed"
    return PipelineStageResult(
        workload_id=workload.workload_id,
        label=workload.label,
        stage="scope",
        status=status,
        reason=reason,
        output_root=str(workload.scope_output_root),
        source_fingerprint=fingerprint,
        command=tuple(command),
    )


def _multi_state_path(cfg: AutoPipelineConfig) -> Path:
    return cfg.state_root / "state" / "multi_workload.json"


def _multi_output_root(multi_config: Path) -> Path:
    data = load_yaml(multi_config)
    return _resolve(multi_config.parent, data["output_root"])


def _multi_fingerprint(
    cfg: AutoPipelineConfig,
    multi_config: Path,
    scope_results: Sequence[PipelineStageResult],
) -> str:
    return stable_hash(
        {
            "schema": _AUTO_PIPELINE_SCHEMA_VERSION,
            "tool_version": _numeric_cache_version(_multi_state_path(cfg)),
            "multi_config": load_yaml(multi_config),
            "scope_results": [
                {
                    "workload_id": row.workload_id,
                    "source_fingerprint": row.source_fingerprint,
                    "usable": row.status in {"completed", "fresh_reused"},
                }
                for row in scope_results
                if row.stage == "scope"
            ],
        }
    )


def _multi_outputs_complete(output_root: Path) -> bool:
    return (
        (output_root / "MULTI_WORKLOAD_SUMMARY.md").is_file()
        and (output_root / "multi_workload_manifest.json").is_file()
        and (
            output_root
            / "paper_artifacts"
            / "multi_workload_documentation_artifacts_review.zip"
        ).is_file()
    )


def _multi_fresh(cfg: AutoPipelineConfig, fingerprint: str, output_root: Path) -> bool:
    state_path = _multi_state_path(cfg)
    if not state_path.is_file() or not _multi_outputs_complete(output_root):
        return False
    try:
        state = read_json(state_path)
    except Exception:
        return False
    return state.get("source_fingerprint") == fingerprint and state.get("status") == "completed"


def _write_multi_state(
    cfg: AutoPipelineConfig,
    multi_config: Path,
    output_root: Path,
    fingerprint: str,
    command: Sequence[str],
) -> None:
    write_json(
        _multi_state_path(cfg),
        {
            "schema_version": _AUTO_PIPELINE_SCHEMA_VERSION,
            "created_utc": utc_now_iso(),
            "tool_version": __version__,
            "numeric_cache_version": _numeric_cache_version(_multi_state_path(cfg)),
            "multi_config": str(multi_config),
            "multi_output_root": str(output_root),
            "source_fingerprint": fingerprint,
            "command": list(command),
            "status": "completed",
            "review_bundle": str(
                output_root
                / "paper_artifacts"
                / "multi_workload_documentation_artifacts_review.zip"
            ),
        },
    )


def _run_multi_stage(
    cfg: AutoPipelineConfig,
    multi_config: Path,
    scope_results: Sequence[PipelineStageResult],
    *,
    force: bool,
    artifacts_only: bool,
    verbose: bool,
) -> PipelineStageResult:
    output_root = _multi_output_root(multi_config)
    fingerprint = _multi_fingerprint(cfg, multi_config, scope_results)
    if (
        cfg.skip_fresh_multi
        and not force
        and not artifacts_only
        and _multi_fresh(cfg, fingerprint, output_root)
    ):
        LOGGER.info("Multi-workload analysis and paper artifacts are fresh; reusing outputs")
        return PipelineStageResult(
            workload_id="__multi__",
            label="Multi-workload",
            stage="multi_workload",
            status="fresh_reused",
            reason="scope_and_config_fingerprint_match",
            output_root=str(output_root),
            source_fingerprint=fingerprint,
            command=(),
        )

    command = [
        sys.executable,
        "-m",
        "commonref.cli",
        "workload-compare",
        "--config",
        str(multi_config),
    ]
    if force:
        command.append("--force")
    if artifacts_only:
        command.append("--artifacts-only")
    if verbose:
        command.append("--verbose")
    returncode, reason = _run_subprocess(command, cfg.tool_root)
    status = "completed" if returncode == 0 else "failed"
    if returncode == 0:
        _write_multi_state(cfg, multi_config, output_root, fingerprint, command)
    return PipelineStageResult(
        workload_id="__multi__",
        label="Multi-workload",
        stage="multi_workload",
        status=status,
        reason=reason,
        output_root=str(output_root),
        source_fingerprint=fingerprint,
        command=tuple(command),
    )



def _dataset_directory_inventory(cfg: AutoPipelineConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not cfg.dataset_root.is_dir():
        return rows
    excludes = set(cfg.exclude_directories) | {cfg.idle_directory_name}
    for child in sorted(cfg.dataset_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        rate_rows = _rate_inventory(child)
        paired_total = sum(int(row["paired_runs"]) for row in rate_rows)
        if child.name == cfg.idle_directory_name:
            status = "reserved_external_idle"
        elif child.name in excludes:
            status = "excluded"
        elif not rate_rows:
            status = "no_rate_directories"
        elif paired_total < cfg.minimum_paired_runs_any_rate:
            status = "no_complete_pairs"
        else:
            status = "workload_candidate"
        rows.append(
            {
                "directory_name": child.name,
                "path": str(child.resolve()),
                "status": status,
                "rate_directories": len(rate_rows),
                "paired_runs_total": paired_total,
                "common_rate_paired_runs": next(
                    (
                        int(row["paired_runs"])
                        for row in rate_rows
                        if int(row["rate_sps"]) == cfg.common_rate_sps
                    ),
                    0,
                ),
            }
        )
    return rows

def _write_discovery_outputs(
    cfg: AutoPipelineConfig,
    workloads: Sequence[DiscoveredWorkload],
) -> None:
    root = cfg.state_root / "discovery"
    directory_rows = _dataset_directory_inventory(cfg)
    write_csv(
        root / "dataset_directories.csv",
        directory_rows,
        fieldnames=[
            "directory_name",
            "path",
            "status",
            "rate_directories",
            "paired_runs_total",
            "common_rate_paired_runs",
        ],
    )
    write_json(
        root / "dataset_directories.json",
        {
            "schema_version": _AUTO_PIPELINE_SCHEMA_VERSION,
            "created_utc": utc_now_iso(),
            "directories": directory_rows,
        },
    )
    rows: list[dict[str, Any]] = []
    for workload in workloads:
        rows.append(
            {
                "workload_id": workload.workload_id,
                "label": workload.label,
                "family": workload.family,
                "precision": workload.precision,
                "dataset_root": str(workload.dataset_root),
                "scope_template": str(workload.scope_template),
                "scope_config": str(workload.scope_config),
                "scope_output_root": str(workload.scope_output_root),
                "rate_count": workload.rate_count,
                "paired_runs_total": workload.paired_runs_total,
                "common_rate_sps": cfg.common_rate_sps,
                "common_rate_paired_runs": workload.common_rate_paired_runs,
                "paper_ready_common_rate": workload.common_rate_paired_runs
                >= cfg.minimum_paired_runs_common_rate,
                "include_in_paper": workload.include_in_paper,
                "metadata_source": workload.metadata_source,
            }
        )
    write_csv(root / "discovered_workloads.csv", rows)
    write_json(
        root / "discovered_workloads.json",
        {
            "schema_version": _AUTO_PIPELINE_SCHEMA_VERSION,
            "created_utc": utc_now_iso(),
            "dataset_root": str(cfg.dataset_root),
            "idle_root": str(cfg.dataset_root / cfg.idle_directory_name),
            "workloads": [
                {
                    **normalise_for_json(asdict(workload)),
                    "rate_inventory": list(workload.rate_inventory),
                }
                for workload in workloads
            ],
        },
    )
    for workload in workloads:
        write_csv(
            root / "rates" / f"{_safe_id(workload.workload_id)}.csv",
            list(workload.rate_inventory),
        )


def _write_pipeline_summary(
    cfg: AutoPipelineConfig,
    workloads: Sequence[DiscoveredWorkload],
    results: Sequence[PipelineStageResult],
    multi_config: Path,
) -> Path:
    result_rows = [normalise_for_json(asdict(row)) for row in results]
    write_csv(
        cfg.state_root / "auto_pipeline_results.csv",
        result_rows,
        fieldnames=[
            "workload_id",
            "label",
            "stage",
            "status",
            "reason",
            "output_root",
            "source_fingerprint",
            "command",
        ],
    )
    write_json(
        cfg.state_root / "auto_pipeline_manifest.json",
        {
            "schema_version": _AUTO_PIPELINE_SCHEMA_VERSION,
            "created_utc": utc_now_iso(),
            "tool_version": __version__,
            "config": str(cfg.config_path),
            "dataset_root": str(cfg.dataset_root),
            "generated_multi_workload_config": str(multi_config),
            "workloads": [normalise_for_json(asdict(item)) for item in workloads],
            "results": result_rows,
        },
    )
    by_id = {row.workload_id: row for row in results if row.stage == "scope"}
    multi = next((row for row in results if row.stage == "multi_workload"), None)
    lines = [
        "# Automatic Edge-AI workload pipeline",
        "",
        f"- Tool version: `{__version__}`",
        f"- Dataset root: `{cfg.dataset_root}`",
        f"- Discovered workload campaigns: **{len(workloads)}**",
        f"- Generated multi-workload config: `{multi_config}`",
        "",
        "| Workload | Family | Precision | Rates | Paired records | 5-MS/s pairs | Scope stage |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for workload in workloads:
        result = by_id.get(workload.workload_id)
        lines.append(
            "| {label} | {family} | {precision} | {rates} | {pairs} | {common} | {status} |".format(
                label=workload.label,
                family=workload.family,
                precision=workload.precision,
                rates=workload.rate_count,
                pairs=workload.paired_runs_total,
                common=workload.common_rate_paired_runs,
                status=(result.status if result else "not_run"),
            )
        )
    lines.extend(["", "## Multi-workload analysis and paper artifacts", ""])
    if multi is None:
        lines.append("Not run.")
    else:
        lines.extend(
            [
                f"- Status: **{multi.status}**",
                f"- Output root: `{multi.output_root}`",
                f"- Summary: `{Path(multi.output_root) / 'MULTI_WORKLOAD_SUMMARY.md'}`",
                "- Compact review bundle: "
                f"`{Path(multi.output_root) / 'paper_artifacts' / 'multi_workload_documentation_artifacts_review.zip'}`",
            ]
        )
    journal = next((row for row in results if row.stage == "journal"), None)
    if journal is not None:
        lines.extend(["", "## Separate journal PSD artifacts", "",
            f"- Status: **{journal.status}**", f"- Output: `{journal.output_root}`",
            f"- Review: `{Path(journal.output_root) / 'journal_documentation_artifacts_review.zip'}`"])
    failures = [row for row in results if row.status == "failed"]
    lines.extend(["", "## Result", ""])
    if not results:
        lines.append("Discovery completed; no analysis stages were requested.")
    elif failures:
        lines.append(f"Completed with **{len(failures)} failed stage(s)**; see the table and logs.")
    else:
        lines.append("All requested stages completed or were safely reused from matching fingerprints.")
    lines.extend(
        [
            "",
            "The measurement trees were treated read-only. Empty directories, unpaired files, "
            "and partial high-rate campaigns remain visible in the generated inventories.",
            "",
        ]
    )
    path = cfg.state_root / "AUTO_PIPELINE_SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _selected_workloads(
    workloads: Sequence[DiscoveredWorkload], selected: Sequence[str] | None
) -> list[DiscoveredWorkload]:
    if not selected:
        return list(workloads)
    wanted = {str(item).strip() for item in selected if str(item).strip()}
    known = {item.workload_id for item in workloads}
    missing = sorted(wanted - known)
    if missing:
        raise ValueError(f"Requested workloads were not discovered: {missing}")
    return [item for item in workloads if item.workload_id in wanted]


def _journal_upstream_ready(results: Sequence[PipelineStageResult]) -> bool:
    return any(row.stage == "multi_workload" and row.status in {"completed", "fresh_reused"}
               for row in results)


def run_auto_pipeline(
    cfg: AutoPipelineConfig,
    *,
    selected_workloads: Sequence[str] | None = None,
    force_scope: bool = False,
    force_multi: bool = False,
    discover_only: bool = False,
    artifacts_only: bool = False,
    verbose: bool = False,
) -> Path:
    cfg.state_root.mkdir(parents=True, exist_ok=True)
    lock_path = cfg.state_root / "auto_pipeline.lock"
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                f"Another automatic pipeline run holds {lock_path}"
            ) from error

        workloads = discover_workloads(cfg)
        if not workloads:
            raise RuntimeError(f"No paired workload campaigns discovered below {cfg.dataset_root}")
        selected = _selected_workloads(workloads, selected_workloads)
        selected_ids = {item.workload_id for item in selected}
        for workload in workloads:
            generate_scope_config(cfg, workload)
        _write_discovery_outputs(cfg, workloads)

        initial_multi = generate_multi_workload_config(cfg, workloads)
        if discover_only:
            return _write_pipeline_summary(cfg, workloads, [], initial_multi)

        results: list[PipelineStageResult] = []
        if not artifacts_only:
            for workload in workloads:
                if selected_workloads and workload.workload_id not in selected_ids:
                    complete = _scope_outputs_complete(workload)
                    results.append(
                        PipelineStageResult(
                            workload_id=workload.workload_id,
                            label=workload.label,
                            stage="scope",
                            status="fresh_reused" if complete else "skipped_not_selected",
                            reason="existing_scope_output_not_selected" if complete else "not_selected_and_scope_output_missing",
                            output_root=str(workload.scope_output_root),
                            source_fingerprint=(
                                _scope_fingerprint(cfg, workload) if complete else ""
                            ),
                            command=(),
                        )
                    )
                    continue
                try:
                    result = _run_scope_stage(
                        cfg,
                        workload,
                        force=force_scope,
                        verbose=verbose,
                    )
                except Exception as error:
                    LOGGER.exception("Scope stage failed for %s: %s", workload.label, error)
                    result = PipelineStageResult(
                        workload_id=workload.workload_id,
                        label=workload.label,
                        stage="scope",
                        status="failed",
                        reason=f"{type(error).__name__}:{error}",
                        output_root=str(workload.scope_output_root),
                        source_fingerprint="",
                        command=(),
                    )
                results.append(result)
                if result.status == "failed" and not cfg.continue_on_error:
                    break
        else:
            # Artifact-only mode uses all completed scope trees without touching
            # raw data. Missing trees are disabled in the effective config.
            for workload in workloads:
                status = "fresh_reused" if _scope_outputs_complete(workload) else "failed"
                results.append(
                    PipelineStageResult(
                        workload_id=workload.workload_id,
                        label=workload.label,
                        stage="scope",
                        status=status,
                        reason="artifacts_only_existing_scope" if status == "fresh_reused" else "scope_outputs_missing",
                        output_root=str(workload.scope_output_root),
                        source_fingerprint=(
                            _scope_fingerprint(cfg, workload) if status == "fresh_reused" else ""
                        ),
                        command=(),
                    )
                )

        effective_multi = generate_multi_workload_config(cfg, workloads, results)
        successful_scope = [
            row for row in results if row.stage == "scope" and row.status in {"completed", "fresh_reused"}
        ]
        if successful_scope:
            try:
                multi_result = _run_multi_stage(
                    cfg,
                    effective_multi,
                    results,
                    force=force_multi,
                    artifacts_only=artifacts_only,
                    verbose=verbose,
                )
            except Exception as error:
                LOGGER.exception("Multi-workload stage failed: %s", error)
                multi_result = PipelineStageResult(
                    workload_id="__multi__",
                    label="Multi-workload",
                    stage="multi_workload",
                    status="failed",
                    reason=f"{type(error).__name__}:{error}",
                    output_root=str(_multi_output_root(effective_multi)),
                    source_fingerprint="",
                    command=(),
                )
            results.append(multi_result)
        else:
            LOGGER.error("No successful scope analyses are available for the multi-workload stage")

        journal_options = load_yaml(cfg.config_path)
        journal_requested = journal_options.get("journal_enabled", False) and os.environ.get("COMMONREF_SKIP_JOURNAL", "0") != "1"
        if journal_requested and not _journal_upstream_ready(results):
            LOGGER.warning("Journal stage skipped because the current upstream multi-workload stage failed; old journal outputs are retained")
            results.append(PipelineStageResult(workload_id="__journal__", label="Journal PSD",
                stage="journal", status="skipped_upstream_failure", reason="no_current_successful_multi_stage",
                output_root="", source_fingerprint="", command=()))
        if journal_requested and _journal_upstream_ready(results):
            journal_cfg = _resolve(cfg.config_path.parent, journal_options.get("journal_config", "config_journal.yaml"))
            command = [sys.executable, "-m", "commonref.journal", "--config", str(journal_cfg)]
            if artifacts_only:
                command.append("--artifacts-only")
            if verbose:
                command.append("--verbose")
            try:
                code, reason = _run_subprocess(command, cfg.tool_root)
                from .journal_data import load_journal_config
                jr = load_journal_config(journal_cfg)
                status = "completed" if code == 0 else "failed"
                out = str(jr.output)
            except Exception as error:
                status, reason, out = "failed", str(error), ""
            results.append(PipelineStageResult(workload_id="__journal__", label="Journal PSD",
                stage="journal", status=status, reason=reason, output_root=out,
                source_fingerprint="", command=tuple(command)))
        return _write_pipeline_summary(cfg, workloads, results, effective_multi)
