from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import zipfile
from tempfile import TemporaryDirectory
import warnings
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
mpl.rcParams["pdf.fonttype"] = 42
mpl.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import numpy as np

from . import __version__
from .config import AnalysisConfig
from .utils import (
    LOGGER,
    human_rate,
    load_yaml,
    package_versions,
    read_csv,
    read_json,
    utc_now_iso,
    write_csv,
    write_json,
)


PAPER_ARTIFACT_SCHEMA_VERSION = 4




def _rate_duration_contract(output_root: Path) -> dict[str, Any]:
    """Load the canonical rate-duration artifact contract.

    The analysis stage still keeps the historical ``duration_sensitivity`` tree
    for backwards compatibility, but all paper/documentation consumers use only
    ``rate_duration``.  Rows are normalised to the internal field names used by
    the plotting/table code so the public file contract remains terminology-stable.
    """
    root = output_root / "rate_duration"
    summary_path = root / "same_trace_summary.csv"
    fmin_path = root / "f_min_by_duration.csv"
    decision_path = root / "highlighted_rate_duration_decision.json"
    campaign_root = root / "duration_campaign"

    summary_raw = read_csv(summary_path) if summary_path.is_file() else []
    fmin_raw = read_csv(fmin_path) if fmin_path.is_file() else []
    decision = read_json(decision_path) if decision_path.is_file() else {}

    summary: list[dict[str, Any]] = []
    for row in summary_raw:
        normalised = dict(row)
        normalised.update({
            "duration_s": row.get("window_duration_s"),
            "run_abs_error_q95_median": row.get("per_run_abs_error_q95_median_pct"),
            "run_abs_error_q95_q05": row.get("per_run_abs_error_q95_q05_pct"),
            "run_abs_error_q95_q95": row.get("per_run_abs_error_q95_q95_pct"),
            "run_abs_error_q95_max": row.get("per_run_abs_error_q95_max_pct"),
            "run_abs_error_max_max": row.get("abs_error_max_pct"),
            "abs_error_pct_median": row.get("abs_error_median_pct"),
            "abs_error_pct_q95": row.get("abs_error_q95_pct"),
        })
        summary.append(normalised)

    fmin: list[dict[str, Any]] = []
    for row in fmin_raw:
        normalised = dict(row)
        normalised.update({
            "duration_s": row.get("window_duration_s"),
            "threshold_pct": row.get("error_limit_pct"),
            "f_min_sps": row.get("selected_rate_sps"),
        })
        fmin.append(normalised)

    recommendations: list[dict[str, Any]] = []
    for row in decision.get("recommendations", []):
        normalised = dict(row)
        normalised.setdefault(
            "minimum_duration_s", row.get("minimum_passing_duration_s")
        )
        normalised.setdefault("threshold_pct", row.get("error_limit_pct"))
        recommendations.append(normalised)
    decision = dict(decision)
    decision["recommendations"] = recommendations

    return {
        "root": root,
        "summary_path": summary_path,
        "fmin_path": fmin_path,
        "decision_path": decision_path,
        "summary": summary,
        "fmin": fmin,
        "decision": decision,
        "campaign_thresholds_path": campaign_root / "reference_convergence_thresholds.csv",
        "campaign_reference_path": campaign_root / "reference_convergence.csv",
        "campaign_urecs_path": campaign_root / "urecs_vs_pico_summary.csv",
        "campaign_source_path": campaign_root / "source.json",
    }

def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_files(paths: Sequence[Path]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Paper-artifact generation requires completed analysis outputs. "
            "Missing files:\n- " + "\n- ".join(missing)
        )


def _save_figure(fig: plt.Figure, directory: Path, stem: str, dpi: int = 240, *, tight: bool = True) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pdf = directory / f"{stem}.pdf"
    png = directory / f"{stem}.png"
    save_kwargs = {"bbox_inches": "tight"} if tight else {}
    fig.savefig(pdf, **save_kwargs)
    fig.savefig(png, dpi=dpi, **save_kwargs)
    plt.close(fig)
    return pdf, png


def _optional_float(value: Any, default: float = float("nan")) -> float:
    """Convert optional numeric output to a finite/NaN float without raising.

    ``None`` is a valid scientific result for quantities such as a validated
    band edge when no predefined band satisfies the agreement criteria.
    Human-facing artifacts render this as ``n/a``; artifact generation must
    not fail merely because no band passed.
    """
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    return numeric


def _fmt_rate(rate: float) -> str:
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:g} MS/s"
    if rate >= 1_000:
        return f"{rate / 1_000:g} kS/s"
    return f"{rate:g} S/s"

def _fmt_frequency(value_hz: float) -> str:
    value = _optional_float(value_hz)
    if not np.isfinite(value):
        return "n/a"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.4g} MHz"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.4g} kHz"
    return f"{value:.4g} Hz"


def _fmt_duration(value_s: float) -> str:
    value = _optional_float(value_s)
    if not np.isfinite(value):
        return "n/a"
    if value < 1e-3:
        return f"{1000.0 * value:.3g} ms"
    if value < 1.0:
        return f"{1000.0 * value:g} ms"
    return f"{value:g} s"


def _bound_text(relation: str, value: float, formatter) -> str:
    if not np.isfinite(float(value)):
        return "n/a"
    prefix = {"<=": "$\\leq$", "=": "", ">": "$>$"}.get(str(relation), str(relation))
    formatted = formatter(float(value))
    return f"{prefix}{formatted}" if prefix else formatted


def _first_finite_dict(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        try:
            value = float(row.get(key, float("nan")))
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            return value
    return float("nan")


def _fmt_optional(value: Any, format_spec: str, suffix: str = "") -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(numeric):
        return "n/a"
    return f"{format(numeric, format_spec)}{suffix}"


def _psd_db_curves(
    *densities: np.ndarray,
    dynamic_range_db: float = 120.0,
) -> tuple[list[np.ndarray], tuple[float, float]]:
    """Convert PSD arrays to a bounded dB representation for publication.

    Active-minus-idle estimates can be exactly zero at isolated bins.  Mapping
    those values to floating-point ``tiny`` creates artificial vertical spikes
    near -3000 dB.  A relative display floor preserves the scientifically
    relevant dynamic range while making the plot readable.  Numeric analyses
    continue to use the unfloored linear PSD arrays.
    """

    positive_parts: list[np.ndarray] = []
    for values in densities:
        array = np.asarray(values, dtype=np.float64)
        part = array[np.isfinite(array) & (array > 0)]
        if part.size:
            positive_parts.append(part)
    if not positive_parts:
        floor = 1e-30
        peak = floor
    else:
        finite_positive = np.concatenate(positive_parts)
        peak = float(np.max(finite_positive))
        floor = peak * 10.0 ** (-dynamic_range_db / 10.0)
    converted: list[np.ndarray] = []
    for values in densities:
        array = np.asarray(values, dtype=np.float64)
        display = np.full(array.shape, np.nan, dtype=np.float64)
        # Mask bins at or below the publication floor instead of forcing them
        # onto one horizontal line.  Connecting a valid point to an isolated
        # zero bin creates the visually dominant vertical drops that made the
        # previous plot hard to read.  The numeric analyses still use the
        # original unfloored arrays.
        valid = np.isfinite(array) & (array > floor)
        display[valid] = 10.0 * np.log10(array[valid])
        converted.append(display)
    upper = 10.0 * math.log10(peak) + 3.0
    lower = upper - dynamic_range_db
    return converted, (lower, upper)


def _spectral_display_indices(
    size: int,
    maximum_points: int = 20_000,
) -> np.ndarray:
    """Return compact indices that retain low- and high-frequency detail.

    Publication plots do not need every Welch bin. Drawing millions of points
    makes vector PDFs unnecessarily large and turns dense coherence/noise-floor
    regions into solid blocks. Combining a linear and a geometric selection
    preserves narrow low-frequency structure and the full-band envelope without
    changing any reported numeric metric.
    """

    if size <= maximum_points:
        return np.arange(size, dtype=np.int64)
    half = max(2, maximum_points // 2)
    linear = np.linspace(0, size - 1, half, dtype=np.int64)
    geometric = np.geomspace(1, size, half, dtype=np.float64) - 1.0
    geometric = np.rint(geometric).astype(np.int64)
    return np.unique(
        np.concatenate(
            [np.asarray([0, size - 1], dtype=np.int64), linear, geometric]
        )
    )



def _latex_percent(value: float, *, decimals: int = 3) -> str:
    if value == 0:
        return "0\\%"
    if abs(value) >= 0.001:
        return f"{value:.{decimals}f}\\%"
    exponent = int(math.floor(math.log10(abs(value))))
    coefficient = value / (10 ** exponent)
    return rf"${coefficient:.2f}\times10^{{{exponent}}}$\%"


def _yes_no(value: Any) -> str:
    return "yes" if _as_bool(value) else "no"


def _nearest_row(rows: Sequence[dict[str, str]], field: str, target: float) -> dict[str, str]:
    if not rows:
        raise ValueError(f"No rows available while looking up {field}={target}")
    return min(rows, key=lambda row: abs(float(row[field]) - target))


def _metric(rows: Sequence[dict[str, str]], name: str, field: str = "median") -> float:
    for row in rows:
        if row.get("metric") == name:
            return float(row[field])
    raise KeyError(f"Metric {name!r} not found")


def _latex_plain(value: str) -> str:
    text = value
    replacements = {
        "\\urecs{}": "u.RECS",
        "\\%": "%",
        "\\pm": "+/-",
        "~": " ",
        "$": "",
        "\\min": "min",
        "\\,": " ",
        "--": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\\[A-Za-z]+\{([^{}]*)\}", r"\1", text)
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())


def _write_markdown_table(path: Path, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    plain_headers = [_latex_plain(str(value)) for value in headers]
    lines = [
        "| " + " | ".join(plain_headers) + " |",
        "|" + "|".join("---" for _ in plain_headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_latex_plain(str(value)) for value in row) + " |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv_table(path: Path, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([_latex_plain(str(value)) for value in headers])
        for row in rows:
            writer.writerow([_latex_plain(str(value)) for value in row])


def _table_tex(
    *,
    caption: str,
    label: str,
    environment: str,
    column_spec: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> str:
    if environment not in {"tabular", "tabularx", "tabular_resize"}:
        raise ValueError(f"Unsupported LaTeX table environment: {environment}")

    if environment == "tabularx":
        begin_line = f"\\begin{{tabularx}}{{\\textwidth}}{{{column_spec}}}"
        end_line = "\\end{tabularx}"
        resize_open = None
    else:
        begin_line = f"\\begin{{tabular}}{{{column_spec}}}"
        end_line = "\\end{tabular}"
        resize_open = (
            "\\resizebox{\\textwidth}{!}{%"
            if environment == "tabular_resize"
            else None
        )

    lines = [
        "% Auto-generated by common_reference_psd_tool. Do not edit by hand.",
        "\\begin{table}[t]",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        "\\centering",
        "\\small",
    ]
    if resize_open is not None:
        lines.append(resize_open)
    lines.extend(
        [
            begin_line,
            "\\toprule",
            " & ".join(str(value) for value in headers) + r" \\",
            "\\midrule",
        ]
    )
    lines.extend(" & ".join(str(value) for value in row) + r" \\" for row in rows)
    lines.extend(["\\bottomrule", end_line])
    if resize_open is not None:
        lines.append("}")
    lines.extend(["\\end{table}", ""])
    return "\n".join(lines)


def _write_table_triplet(
    directory: Path,
    stem: str,
    *,
    caption: str,
    label: str,
    environment: str,
    column_spec: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    tex = directory / f"{stem}.tex"
    csv_path = directory / f"{stem}.csv"
    md = directory / f"{stem}.md"
    tex.write_text(
        _table_tex(
            caption=caption,
            label=label,
            environment=environment,
            column_spec=column_spec,
            headers=headers,
            rows=rows,
        ),
        encoding="utf-8",
    )
    _write_csv_table(csv_path, headers, rows)
    _write_markdown_table(md, headers, rows)
    return tex, csv_path, md


# ---------------------------------------------------------------------------
# Paper-ready figures used by the current manuscript.
# ---------------------------------------------------------------------------

def _box(ax, x, y, w, h, text, fontsize=7.6, linewidth=0.9):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.03,rounding_size=0.06",
        facecolor="white",
        edgecolor="black",
        linewidth=linewidth,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize)
    return x, y, w, h


def _point(box_value, side):
    x, y, w, h = box_value
    return {
        "l": (x, y + h / 2),
        "r": (x + w, y + h / 2),
        "t": (x + w / 2, y + h),
        "b": (x + w / 2, y),
    }[side]


def _arrow(ax, a, b, linestyle="solid", rad=0.0, linewidth=0.85):
    ax.add_patch(
        FancyArrowPatch(
            a,
            b,
            arrowstyle="-|>",
            mutation_scale=8,
            connectionstyle=f"arc3,rad={rad}",
            linewidth=linewidth,
            linestyle=linestyle,
            color="black",
            shrinkA=2,
            shrinkB=2,
        )
    )


def _figure_sampling_method(directory: Path, n_runs: int, active_duration_s: float) -> tuple[Path, Path]:
    fig, ax = plt.subplots(figsize=(8.25, 3.55))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.0)
    ax.axis("off")
    ax.text(
        6.0,
        5.72,
        "Common-reference-trace and spectral analysis",
        ha="center",
        fontsize=10.0,
        fontweight="bold",
    )

    b1 = _box(ax, 0.25, 3.75, 2.0, 0.92, "Calibrated 5-MS/s\npower trace $P(t)$", 7.8)
    b2 = _box(
        ax,
        2.75,
        3.75,
        2.0,
        0.92,
        f"Freeze the same\n{active_duration_s:g}-s integration window",
        7.5,
    )
    b3 = _box(ax, 5.35, 4.55, 2.25, 0.92, "Target-rate low-pass\n+ band-limited resampling", 7.4)
    b4 = _box(
        ax,
        5.35,
        2.85,
        2.25,
        1.08,
        "No target-rate low-pass\nsample the same trace\nat shifted time grids",
        7.25,
    )
    b5 = _box(ax, 8.05, 3.75, 1.85, 0.92, "Up to 64 grid offsets\nwithin $T_s=1/f_s$", 7.2)
    b6 = _box(
        ax,
        10.18,
        3.75,
        1.55,
        0.92,
        "$Q_{0.95}$ energy error\nacross runs + offsets",
        6.75,
    )
    b7 = _box(ax, 5.35, 1.25, 2.25, 0.92, "Welch PSD at 1 MS/s\nactive minus idle", 7.5)
    b8 = _box(ax, 8.05, 1.25, 1.85, 0.92, "$f_{95}$, $f_{99}$ and\nvariance below Nyquist", 6.95)
    b9 = _box(ax, 10.18, 1.25, 1.55, 0.92, "125 / 160 kS/s\nfor 95 / 99%", 6.95)

    _arrow(ax, _point(b1, "r"), _point(b2, "l"))
    _arrow(ax, _point(b2, "r"), _point(b3, "l"), rad=0.12)
    _arrow(ax, _point(b2, "r"), _point(b4, "l"), rad=-0.12)
    _arrow(ax, _point(b3, "r"), _point(b5, "l"), rad=-0.08)
    _arrow(ax, _point(b4, "r"), _point(b5, "l"), rad=0.08)
    _arrow(ax, _point(b5, "r"), _point(b6, "l"))
    _arrow(ax, _point(b1, "b"), _point(b7, "l"), rad=-0.22)
    _arrow(ax, _point(b7, "r"), _point(b8, "l"))
    _arrow(ax, _point(b8, "r"), _point(b9, "l"))

    ax.text(
        6.0,
        0.54,
        "Grid offset = timing of the first low-rate sample within one sample period; it is not the electrical voltage-current phase.",
        ha="center",
        va="center",
        fontsize=7.55,
        fontweight="bold",
    )
    ax.text(
        6.0,
        0.20,
        "Independent rate sweeps are compared afterwards to separate pure sampling effects from run-to-run and acquisition effects.",
        ha="center",
        va="center",
        fontsize=7.35,
    )
    fig.tight_layout(pad=0.12)
    return _save_figure(fig, directory, "sampling_rate_method", dpi=220)


def _figure_measurement_setup(directory: Path, metadata: dict[str, Any]) -> tuple[Path, Path]:
    setup = metadata.get("measurement_setup", {})
    fig, ax = plt.subplots(figsize=(8.46, 4.66))
    ax.set_xlim(0, 14.2)
    ax.set_ylim(0, 8.0)
    ax.axis("off")
    ax.text(
        7.1,
        7.68,
        str(setup.get("title", "Heterogeneous u.RECS measurement setup")),
        ha="center",
        va="center",
        fontsize=11.0,
        fontweight="bold",
    )

    ac = _box(ax, 0.35, 5.55, 2.55, 0.95, str(setup.get("ac_meter", "AC wall meter\nwhole-system boundary")), 8.0)
    supply = _box(ax, 0.35, 3.90, 2.55, 0.95, str(setup.get("supply", "Laboratory supply\nDC input")), 8.0)
    urecs = _box(ax, 3.45, 3.90, 2.75, 0.95, str(setup.get("urecs", "u.RECS power subsystem\nslot shunts + ADC")), 8.0)
    jetson = _box(ax, 6.85, 5.20, 2.60, 0.95, str(setup.get("jetson", "Jetson host module\nSoC boundary")), 8.0)
    hailo = _box(ax, 6.85, 2.60, 2.60, 0.95, str(setup.get("hailo", "M.2 Hailo accelerator\ndedicated slot rail")), 8.0)
    reference = _box(ax, 3.45, 0.95, 2.75, 0.95, str(setup.get("reference", "External high-rate reference\nselected DC rail")), 8.0)
    host = _box(ax, 10.55, 3.90, 2.55, 0.95, str(setup.get("host", "Acquisition host\ncontrol and analysis")), 8.0)

    ax.text(8.15, 6.78, str(setup.get("jetson_group", "integrated SoC")), ha="center", fontsize=8.1)

    # Solid power paths.
    _arrow(ax, _point(ac, "b"), _point(supply, "t"), linewidth=0.95)
    _arrow(ax, _point(supply, "r"), _point(urecs, "l"), linewidth=0.95)
    _arrow(ax, _point(urecs, "r"), _point(jetson, "l"), rad=0.20, linewidth=0.95)
    _arrow(ax, _point(urecs, "r"), _point(hailo, "l"), rad=-0.20, linewidth=0.95)

    # Analogue reference tap.
    ax.plot(
        [_point(urecs, "b")[0], _point(urecs, "b")[0]],
        [_point(urecs, "b")[1], _point(reference, "t")[1]],
        linestyle="--",
        color="black",
        linewidth=0.9,
    )
    _arrow(ax, (_point(urecs, "b")[0], 2.08), _point(reference, "t"), linestyle="--", linewidth=0.9)

    # Digital measurement / control paths.
    x_bus = 10.10
    ax.plot([x_bus, x_bus], [2.45, 6.25], linestyle=":", color="black", linewidth=0.9)
    for source in (ac, urecs, jetson, hailo, reference):
        y = _point(source, "r")[1]
        start_x = _point(source, "r")[0]
        ax.plot([start_x, x_bus], [y, y], linestyle=":", color="black", linewidth=0.9)
    _arrow(ax, (x_bus, _point(host, "l")[1]), _point(host, "l"), linestyle=":", linewidth=0.9)

    # Legend.
    y_leg = 0.15
    ax.plot([0.6, 1.3], [y_leg, y_leg], color="black", linewidth=0.95)
    ax.text(1.4, y_leg, "power path", va="center", fontsize=7.7)
    ax.plot([3.0, 3.7], [y_leg, y_leg], color="black", linewidth=0.9, linestyle="--")
    ax.text(3.8, y_leg, "analogue reference tap", va="center", fontsize=7.7)
    ax.plot([6.2, 6.9], [y_leg, y_leg], color="black", linewidth=0.9, linestyle=":")
    ax.text(7.0, y_leg, "digital measurement / control", va="center", fontsize=7.7)

    fig.tight_layout(pad=0.15)
    return _save_figure(fig, directory, "measurement_setup_heterogeneous", dpi=220, tight=False)


def _figure_common_trace(directory: Path, output_root: Path) -> tuple[Path, Path]:
    real = read_csv(output_root / "real_measurements" / "real_measurements_summary.csv")
    anti = read_csv(output_root / "common_trace" / "anti_aliased_summary.csv")
    phase = read_csv(output_root / "common_trace" / "phase_only_summary.csv")
    n_runs = max(int(float(row["n_runs"])) for row in anti)

    real = sorted(real, key=lambda row: float(row["reported_rate_median_sps"]))
    anti = sorted(anti, key=lambda row: float(row["target_rate_sps"]))
    phase = sorted(phase, key=lambda row: float(row["target_rate_sps"]))

    fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.25))

    ax = axes[0]
    x = np.asarray([float(row["reported_rate_median_sps"]) for row in real])
    y = np.asarray([float(row["error_median_pct"]) for row in real])
    ylo = np.asarray([float(row["error_q05_pct"]) for row in real])
    yhi = np.asarray([float(row["error_q95_pct"]) for row in real])
    ax.fill_between(x, ylo, yhi, alpha=0.22, label="5th-95th percentile")
    ax.plot(x, y, marker="o", markersize=3.0, linewidth=1.0, label="Median")
    ax.axhline(0.0, linewidth=0.8)
    ax.axhline(1.0, linewidth=0.7, linestyle="--")
    ax.axhline(-1.0, linewidth=0.7, linestyle="--")
    ax.set_xscale("log")
    ax.set_xlabel("Independently acquired rate (S/s)")
    ax.set_ylabel("Energy difference from 5-MS/s median (%)")
    ax.set_title("(a) Separate executions: run + acquisition effects", fontsize=8.7)
    ax.grid(True, which="both", linewidth=0.35, alpha=0.45)
    ax.legend(fontsize=6.8, loc="best")
    idx_max = int(np.nanargmax(y))
    ax.annotate(f"{y[idx_max]:.2f}%", (x[idx_max], y[idx_max]), xytext=(4, 5), textcoords="offset points", fontsize=6.8)
    row_4m = _nearest_row(real, "reported_rate_median_sps", 4_000_000)
    rx = float(row_4m["reported_rate_median_sps"])
    ry = float(row_4m["error_median_pct"])
    ax.annotate(f"{ry:.2f}%", (rx, ry), xytext=(-27, -12), textcoords="offset points", fontsize=6.8)

    ax = axes[1]
    anti_plot = [
        row
        for row in anti
        if float(row["target_rate_sps"]) <= 1_000_000 and not _as_bool(row["is_high_rate_anchor"])
    ]
    phase_plot = [row for row in phase if float(row["target_rate_sps"]) <= 1_000_000]
    ax.plot(
        [float(row["target_rate_sps"]) for row in anti_plot],
        [float(row["abs_error_q95_pct"]) for row in anti_plot],
        marker="o",
        markersize=3.0,
        linewidth=1.0,
        label="Target-rate low-pass\n(controlled best case)",
    )
    ax.plot(
        [float(row["target_rate_sps"]) for row in phase_plot],
        [float(row["abs_error_q95_pct"]) for row in phase_plot],
        marker="s",
        markersize=3.0,
        linewidth=1.0,
        label="No target-rate low-pass\ngrid offset swept",
    )
    ax.axhline(1.0, linewidth=0.8, linestyle="--", label="1% tolerance")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Rate reconstructed from the same execution (S/s)")
    ax.set_ylabel(r"$Q_{0.95}$ absolute energy error (%)")
    ax.set_title(f"(b) Same-run grid-offset sensitivity ($n={n_runs}$)", fontsize=8.65)
    ax.grid(True, which="both", linewidth=0.35, alpha=0.45)
    ax.legend(fontsize=5.9, loc="lower left", framealpha=0.94)

    iax = inset_axes(ax, width="42%", height="29%", loc="upper right", borderpad=0.8)
    tt = np.linspace(0.0, 1.0, 500)
    wave = 0.56 + 0.28 * np.sin(2.0 * np.pi * 2.1 * tt) + 0.10 * np.sin(2.0 * np.pi * 5.0 * tt)
    iax.plot(tt, wave, linewidth=0.8, color="0.35")
    period = 0.20
    grid_a = np.arange(0.03, 1.0, period)
    grid_b = np.arange(0.10, 1.0, period)
    iax.scatter(grid_a, np.interp(grid_a, tt, wave), s=8, marker="o", label="grid A")
    iax.scatter(grid_b, np.interp(grid_b, tt, wave), s=9, marker="s", label="grid B")
    iax.set_xlim(0.0, 1.0)
    iax.set_ylim(0.05, 1.02)
    iax.set_xticks([])
    iax.set_yticks([])
    iax.set_title("same rate, shifted first sample", fontsize=5.4, pad=1.0)
    iax.legend(fontsize=4.7, loc="lower center", ncol=2, framealpha=0.9, handletextpad=0.25, columnspacing=0.6)
    for spine in iax.spines.values():
        spine.set_linewidth(0.55)

    for rate, offset in [(50, (5, 5)), (2000, (5, 5))]:
        row = _nearest_row(phase_plot, "target_rate_sps", rate)
        xx = float(row["target_rate_sps"])
        yy = float(row["abs_error_q95_pct"])
        ax.annotate(f"{yy:.3f}%", (xx, yy), xytext=offset, textcoords="offset points", fontsize=6.8)
    row = _nearest_row(anti_plot, "target_rate_sps", 50)
    anti_value = float(row["abs_error_q95_pct"])
    exponent = int(math.floor(math.log10(abs(anti_value)))) if anti_value else 0
    coefficient = anti_value / (10 ** exponent) if anti_value else 0.0
    anti_label = rf"${coefficient:.2f}\times10^{{{exponent}}}$%"
    ax.annotate(
        anti_label,
        (float(row["target_rate_sps"]), anti_value),
        xytext=(5, -12),
        textcoords="offset points",
        fontsize=6.8,
    )

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="This figure includes Axes that are not compatible with tight_layout",
            category=UserWarning,
        )
        fig.tight_layout(pad=0.6, w_pad=1.0)
    return _save_figure(fig, directory, "common_trace_results_paper", dpi=240)


def _figure_psd_variance(directory: Path, output_root: Path) -> tuple[Path, Path]:
    data = np.load(output_root / "psd" / "psd_summary.npz")
    freq = data["frequencies_hz"]
    active = data["active_median"]
    idle = data["idle_median"]
    variance = sorted(
        read_csv(output_root / "psd" / "variance_capture_summary.csv"),
        key=lambda row: float(row["target_rate_sps"]),
    )
    metrics = read_csv(output_root / "psd" / "psd_metrics_summary.csv")
    n_runs = int(float(metrics[0]["n_runs"])) if metrics else 0
    f95 = _metric(metrics, "f95_hz")
    f99 = _metric(metrics, "f99_hz")

    fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.15))
    ax = axes[0]
    mask = freq >= 1.0
    tiny = np.finfo(float).tiny
    ax.plot(
        freq[mask],
        10.0 * np.log10(np.maximum(active[mask], tiny)),
        linewidth=0.9,
        label=f"GEMM active: median PSD ({n_runs} runs)",
    )
    ax.plot(
        freq[mask],
        10.0 * np.log10(np.maximum(idle[mask], tiny)),
        linewidth=0.9,
        label=f"Idle before GEMM: median PSD ({n_runs} runs)",
    )
    ax.axvline(f95, linewidth=0.8, linestyle="--", label=f"$f_{{95}}$={f95/1000:.2f} kHz")
    ax.axvline(f99, linewidth=0.8, linestyle=":", label=f"$f_{{99}}$={f99/1000:.2f} kHz")
    ax.set_xscale("log")
    ax.set_xlim(1, 500_000)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel(r"Power-fluctuation PSD (dB W$^2$/Hz)")
    ax.set_title("(a) Power-fluctuation spectra: GEMM versus idle", fontsize=8.6)
    ax.grid(True, which="both", linewidth=0.35, alpha=0.45)
    ax.legend(fontsize=5.7, loc="lower left", framealpha=0.94)
    ax.text(
        0.98,
        0.97,
        "Each window is mean-centred separately\n(curves show fluctuations, not average power)",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=5.6,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="0.55", alpha=0.92, linewidth=0.5),
    )

    ax = axes[1]
    x = np.asarray([float(row["target_rate_sps"]) for row in variance])
    med = np.asarray([float(row["percent_median"]) for row in variance])
    q05 = np.asarray([float(row["percent_q05"]) for row in variance])
    q95 = np.asarray([float(row["percent_q95"]) for row in variance])
    ax.fill_between(x, q05, q95, alpha=0.22, label="5th-95th percentile")
    ax.plot(x, med, marker="o", markersize=3.0, linewidth=1.0, label="Median")
    ax.axhline(95.0, linewidth=0.75, linestyle="--", label="95% criterion")
    ax.axhline(99.0, linewidth=0.75, linestyle=":", label="99% criterion")
    for rate in (2_000, 125_000, 160_000):
        ax.axvline(rate, linewidth=0.65, linestyle="--")
        row = _nearest_row(variance, "target_rate_sps", rate)
        xx = float(row["target_rate_sps"])
        yy = float(row["percent_median"])
        ax.scatter([xx], [yy], s=18, zorder=4)
        if rate == 2_000:
            offset, ha, label = (5, 5), "left", f"{_fmt_rate(xx)}: {yy:.2f}%"
        elif rate == 125_000:
            offset, ha, label = (-8, -22), "right", f"125 kS/s\n{yy:.2f}%"
        else:
            offset, ha, label = (8, -34), "left", f"160 kS/s\n{yy:.2f}%"
        ax.annotate(label, (xx, yy), xytext=offset, textcoords="offset points", fontsize=6.4, ha=ha)
    ax.set_xscale("log")
    ax.set_ylim(0, 102)
    ax.set_xlabel("Sampling rate (S/s)")
    ax.set_ylabel("Variance below Nyquist (%)")
    ax.set_title("(b) GEMM-related fluctuation variance retained", fontsize=8.6)
    ax.grid(True, which="both", linewidth=0.35, alpha=0.45)
    ax.legend(fontsize=6.3, loc="lower right")

    fig.tight_layout(pad=0.6, w_pad=0.9)
    return _save_figure(fig, directory, "psd_variance_results_paper", dpi=240)


def _figure_duration_rate_sufficiency(
    directory: Path,
    output_root: Path,
) -> tuple[Path, Path]:
    """Plot rate-versus-window-length evidence from common-reference traces."""

    contract = _rate_duration_contract(output_root)
    summary = contract["summary"]
    fmin = contract["fmin"]
    decision = contract["decision"]
    highlighted = int(decision.get("highlighted_rate_sps", 2000))

    selected_rows = sorted(
        [
            row
            for row in summary
            if int(float(row["target_rate_sps"])) == highlighted
        ],
        key=lambda row: (
            str(row["reconstruction_mode"]),
            float(row["duration_s"]),
        ),
    )
    if not selected_rows:
        raise ValueError(
            f"Duration analysis contains no rows for {highlighted} S/s"
        )

    fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.25))
    labels = {
        "anti_alias": "Target-rate low-pass (controlled best case)",
        "phase_only": "No target-rate low-pass (grid offset swept)",
    }
    y_positive: list[float] = []
    for mode in ("anti_alias", "phase_only"):
        rows = [row for row in selected_rows if row["reconstruction_mode"] == mode]
        if not rows:
            continue
        duration = np.asarray([float(row["duration_s"]) for row in rows])
        median = np.asarray([float(row["run_abs_error_q95_median"]) for row in rows])
        q05 = np.asarray([float(row["run_abs_error_q95_q05"]) for row in rows])
        q95 = np.asarray([float(row["run_abs_error_q95_q95"]) for row in rows])
        y_positive.extend(q95[np.isfinite(q95) & (q95 > 0)].tolist())
        axes[0].fill_between(duration, q05, q95, alpha=0.16)
        axes[0].plot(
            duration,
            median,
            marker="o",
            markersize=3.0,
            linewidth=1.0,
            label=labels.get(mode, mode),
        )
    for threshold, linestyle in ((0.1, ":"), (0.5, "--"), (1.0, "-.")):
        axes[0].axhline(
            threshold,
            linestyle=linestyle,
            linewidth=0.75,
            label=f"{threshold:g}% tolerance",
        )
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    if y_positive:
        axes[0].set_ylim(bottom=max(min(y_positive) / 3.0, 1e-8))
    axes[0].set_xlabel("Exact integration-window duration (s)")
    axes[0].set_ylabel("Per-run q95 absolute energy error (%)")
    axes[0].set_title(
        f"(a) {_fmt_rate(highlighted)} energy accuracy versus window length",
        fontsize=8.0,
    )
    axes[0].grid(True, which="both", linewidth=0.35, alpha=0.45)
    axes[0].legend(fontsize=5.55, loc="best")

    phase_fmin = [
        row
        for row in fmin
        if row["reconstruction_mode"] == "phase_only"
        and float(row["threshold_pct"]) in {0.1, 0.5, 1.0}
    ]
    for threshold in sorted({float(row["threshold_pct"]) for row in phase_fmin}):
        rows = sorted(
            [
                row
                for row in phase_fmin
                if math.isclose(
                    float(row["threshold_pct"]),
                    threshold,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            ],
            key=lambda row: float(row["duration_s"]),
        )
        duration_values: list[float] = []
        rate_values: list[float] = []
        lower_bound_x: list[float] = []
        lower_bound_y: list[float] = []
        for row in rows:
            try:
                rate = float(row["f_min_sps"])
            except (TypeError, ValueError):
                continue
            if not np.isfinite(rate):
                continue
            duration = float(row["duration_s"])
            duration_values.append(duration)
            rate_values.append(rate)
            if row.get("f_min_relation") == "<=":
                lower_bound_x.append(duration)
                lower_bound_y.append(rate)
        if duration_values:
            axes[1].plot(
                duration_values,
                rate_values,
                marker="o",
                markersize=3.0,
                linewidth=1.0,
                label=f"{threshold:g}% tolerance",
            )
        if lower_bound_x:
            axes[1].scatter(
                lower_bound_x,
                lower_bound_y,
                marker="v",
                s=20,
                zorder=4,
            )
    axes[1].axhline(
        highlighted,
        linestyle="--",
        linewidth=0.8,
        label=f"u.RECS operating rate: {_fmt_rate(highlighted)}",
    )
    axes[1].set_xscale("log")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("Exact integration-window duration (s)")
    axes[1].set_ylabel("Minimum tested sampling-rate bound (S/s)")
    axes[1].set_title(
        "(b) Required rate without a target-rate low-pass",
        fontsize=8.1,
    )
    axes[1].grid(True, which="both", linewidth=0.35, alpha=0.45)
    axes[1].legend(fontsize=5.55, loc="best")
    fig.tight_layout(pad=0.6, w_pad=0.95)
    return _save_figure(
        fig,
        directory,
        "energy_rate_duration_sufficiency_paper",
        dpi=240,
    )


def _figure_duration_protocol_context(
    directory: Path,
    output_root: Path,
) -> tuple[Path, Path]:
    """Plot benchmark-duration convergence separately from sampling error."""

    path = _rate_duration_contract(output_root)["campaign_thresholds_path"]
    rows = read_csv(path)
    if not rows:
        raise ValueError("No duration-campaign convergence rows are available")
    rows = sorted(rows, key=lambda row: str(row["workload"]))
    labels = [str(row["workload"]) for row in rows]
    five_diff = np.asarray(
        [float(row["difference_5_to_reference_pct"]) for row in rows]
    )
    first_duration = np.asarray(
        [float(row["first_duration_within_tolerance_s"]) for row in rows]
    )
    tolerance = float(rows[0].get("tolerance_pct", 3.0))
    reference_duration = float(rows[0].get("reference_duration_s", 600.0))

    fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.15))
    positions = np.arange(len(rows))
    axes[0].bar(positions, five_diff)
    axes[0].set_xticks(positions, labels, rotation=35, ha="right")
    axes[0].set_ylabel(
        f"|5-s vs. {reference_duration:g}-s mean power| (%)"
    )
    axes[0].set_title("(a) Short commands include start/stop and fixed overhead", fontsize=8.0)
    axes[0].grid(True, axis="y", linewidth=0.35, alpha=0.45)

    axes[1].scatter(positions, first_duration, s=28)
    axes[1].set_xticks(positions, labels, rotation=35, ha="right")
    axes[1].set_yscale("log")
    axes[1].set_ylabel(f"First duration within {tolerance:g}% (s)")
    axes[1].set_title(
        f"(b) First duration within {tolerance:g}% of the {reference_duration:g}-s result",
        fontsize=8.0,
    )
    axes[1].grid(True, which="both", axis="y", linewidth=0.35, alpha=0.45)
    fig.tight_layout(pad=0.6, w_pad=1.0)
    return _save_figure(
        fig,
        directory,
        "duration_protocol_context_paper",
        dpi=240,
    )


# ---------------------------------------------------------------------------
# Tables, macros, snippets and provenance bundle.
# ---------------------------------------------------------------------------

def _generate_static_tables(metadata: dict[str, Any], tables_dir: Path) -> list[Path]:
    outputs: list[Path] = []
    for stem, spec in metadata.get("static_tables", {}).items():
        triplet = _write_table_triplet(
            tables_dir,
            f"table_{stem}",
            caption=str(spec["caption"]),
            label=str(spec["label"]),
            environment=str(spec.get("environment", "tabular")),
            column_spec=str(spec["column_spec"]),
            headers=[str(value) for value in spec["headers"]],
            rows=[[str(value) for value in row] for row in spec["rows"]],
        )
        outputs.extend(triplet)
    return outputs


def _dynamic_tables(
    output_root: Path,
    metadata: dict[str, Any],
    tables_dir: Path,
    cfg: AnalysisConfig,
) -> tuple[list[Path], dict[str, float | int | str]]:
    anti = read_csv(output_root / "common_trace" / "anti_aliased_summary.csv")
    phase = read_csv(output_root / "common_trace" / "phase_only_summary.csv")
    real = read_csv(output_root / "real_measurements" / "real_measurements_summary.csv")
    metrics = read_csv(output_root / "psd" / "psd_metrics_summary.csv")
    variance = read_csv(output_root / "psd" / "variance_capture_summary.csv")
    thresholds = read_csv(output_root / "psd" / "variance_capture_thresholds.csv")
    sensitivity_path = output_root / "psd" / "psd_bandwidth_sensitivity_summary.csv"
    sensitivity = read_csv(sensitivity_path) if sensitivity_path.is_file() else []
    duration_contract = _rate_duration_contract(output_root)
    duration_summary = duration_contract["summary"]
    duration_fmin = duration_contract["fmin"]
    duration_recommendation = duration_contract["decision"]
    duration_campaign_thresholds_path = duration_contract["campaign_thresholds_path"]
    duration_urecs_summary_path = duration_contract["campaign_urecs_path"]
    duration_campaign_thresholds = (
        read_csv(duration_campaign_thresholds_path)
        if duration_campaign_thresholds_path.is_file()
        else []
    )
    duration_urecs_summary = (
        read_csv(duration_urecs_summary_path)
        if duration_urecs_summary_path.is_file()
        else []
    )


    configured = metadata.get("dynamic_tables", {})
    ct_rates = [int(value) for value in configured.get("common_trace_rates_sps", [50, 150, 2000])]
    variance_rates = [int(value) for value in configured.get("variance_rates_sps", [2000, 125000, 160000])]
    n_runs = max(int(float(row["n_runs"])) for row in anti)

    common_rows: list[list[str]] = []
    for rate in ct_rates:
        aa = _nearest_row(anti, "target_rate_sps", rate)
        po = _nearest_row(phase, "target_rate_sps", rate)
        common_rows.append(
            [
                _fmt_rate(float(rate)),
                _latex_percent(float(aa["abs_error_q95_pct"]), decimals=3),
                _latex_percent(float(po["abs_error_q95_pct"]), decimals=3),
                _latex_percent(float(po["abs_error_max_pct"]), decimals=3),
            ]
        )
    outputs: list[Path] = list(
        _write_table_triplet(
            tables_dir,
            "table_common_trace_key_results",
            caption=(
                "Common-reference-trace energy error across the retained GEMM-FP16 "
                f"recordings ($n={n_runs}$). The unfiltered mode sweeps the sampling-grid offset."
            ),
            label="tab:common-trace-key-results",
            environment="tabular",
            column_spec="@{}lrrr@{}",
            headers=[
                "Rate",
                "Target-rate low-pass $Q_{0.95}$",
                "Unfiltered grid-offset $Q_{0.95}$",
                "Unfiltered maximum",
            ],
            rows=common_rows,
        )
    )

    f95 = _metric(metrics, "f95_hz")
    f99 = _metric(metrics, "f99_hz")
    f95_q05 = _metric(metrics, "f95_hz", "q05")
    f95_q95 = _metric(metrics, "f95_hz", "q95")
    f99_q05 = _metric(metrics, "f99_hz", "q05")
    f99_q95 = _metric(metrics, "f99_hz", "q95")
    spectral_rows = [
        ["$f_{95}$", f"{f95/1000:.2f}~kHz", f"{f95_q05/1000:.2f}--{f95_q95/1000:.2f}~kHz", f"{2*f95/1000:.2f}~kS/s theoretical Nyquist"],
        ["$f_{99}$", f"{f99/1000:.2f}~kHz", f"{f99_q05/1000:.2f}--{f99_q95/1000:.2f}~kHz", f"{2*f99/1000:.2f}~kS/s theoretical Nyquist"],
    ]
    outputs.extend(
        _write_table_triplet(
            tables_dir,
            "table_psd_frequency_metrics",
            caption="Spectral frequencies containing 95 and 99 percent of the positive active-minus-idle power-fluctuation variance.",
            label="tab:psd-frequency-metrics",
            environment="tabular",
            column_spec="@{}lrrl@{}",
            headers=["Metric", "Median", "5th--95th percentile", "Implication"],
            rows=spectral_rows,
        )
    )

    variance_rows: list[list[str]] = []
    for rate in variance_rates:
        row = _nearest_row(variance, "target_rate_sps", rate)
        variance_rows.append(
            [
                _fmt_rate(float(row["target_rate_sps"])),
                f"{float(row['nyquist_hz'])/1000:.3g}~kHz",
                f"{float(row['percent_median']):.2f}\\%",
                f"{float(row['percent_q05']):.2f}--{float(row['percent_q95']):.2f}\\%",
            ]
        )
    outputs.extend(
        _write_table_triplet(
            tables_dir,
            "table_temporal_variance_capture",
            caption="Workload-related temporal power variance below the Nyquist limit of selected sampling rates.",
            label="tab:temporal-variance-capture",
            environment="tabular",
            column_spec="@{}rrrr@{}",
            headers=["Sampling rate", "Nyquist", "Median retained", "5th--95th percentile"],
            rows=variance_rows,
        )
    )

    max_real = max(real, key=lambda row: float(row["error_median_pct"]))
    min_real = min(real, key=lambda row: float(row["error_median_pct"]))
    comparison_rows = [
        ["Largest positive median", _fmt_rate(float(max_real["reported_rate_median_sps"])), f"{float(max_real['error_median_pct']):+.3f}\\%"],
        ["Most negative median", _fmt_rate(float(min_real["reported_rate_median_sps"])), f"{float(min_real['error_median_pct']):+.3f}\\%"],
        ["2-kS/s independent sweep", "2 kS/s", f"{float(_nearest_row(real, 'reported_rate_median_sps', 2000)['error_median_pct']):+.3f}\\%"],
        ["2-kS/s same-run grid offset, $Q_{0.95}$", "2 kS/s", f"{float(_nearest_row(phase, 'target_rate_sps', 2000)['abs_error_q95_pct']):.3f}\\%"],
    ]
    outputs.extend(
        _write_table_triplet(
            tables_dir,
            "table_independent_vs_same_trace",
            caption="Independent rate-sweep differences compared with the isolated same-run sampling-grid effect.",
            label="tab:independent-vs-same-trace",
            environment="tabular",
            column_spec="@{}lrr@{}",
            headers=["Quantity", "Rate", "Energy difference/error"],
            rows=comparison_rows,
        )
    )

    if sensitivity:
        row = sensitivity[0]
        sensitivity_rows = [
            ["$f_{95}$", f"{100*float(row['abs_f95_hz_relative_delta_q95']):.3f}\\%", f"{100*float(row['frequency_relative_tolerance']):.1f}\\%", _yes_no(row["f95_hz_relative_delta_q95_pass"])],
            ["$f_{99}$", f"{100*float(row['abs_f99_hz_relative_delta_q95']):.3f}\\%", f"{100*float(row['frequency_relative_tolerance']):.1f}\\%", _yes_no(row["f99_hz_relative_delta_q95_pass"])],
            ["Variance at 125 kS/s", f"{100*float(row['abs_variance_at_125000_sps_delta_q95']):.3f} pp", f"{100*float(row['variance_fraction_tolerance']):.1f} pp", _yes_no(row["variance_at_125000_sps_delta_q95_pass"])],
            ["Variance at 160 kS/s", f"{100*float(row['abs_variance_at_160000_sps_delta_q95']):.3f} pp", f"{100*float(row['variance_fraction_tolerance']):.1f} pp", _yes_no(row["variance_at_160000_sps_delta_q95_pass"])],
        ]
        outputs.extend(
            _write_table_triplet(
                tables_dir,
                "table_psd_bandwidth_sensitivity",
                caption="Sensitivity of the primary 1-MS/s PSD metrics to a 250-kS/s representation of the same intervals.",
                label="tab:psd-bandwidth-sensitivity",
                environment="tabular",
                column_spec="@{}lrrl@{}",
                headers=["Metric", "95th-percentile change", "Criterion", "Pass"],
                rows=sensitivity_rows,
            )
        )

    duration_macros: dict[str, float | int | str] = {}
    if duration_summary and duration_fmin:
        highlighted = int(duration_recommendation.get("highlighted_rate_sps", 2000))
        configured_durations = [
            float(value)
            for value in configured.get(
                "duration_window_s",
                [0.1, 0.5, 1, 5, 10, 20, 50, 100, 104],
            )
        ]
        threshold_values = [0.1, 0.5, 1.0]

        def duration_row(mode: str, duration_s: float) -> dict[str, str]:
            candidates = [
                row
                for row in duration_summary
                if row["reconstruction_mode"] == mode
                and int(float(row["target_rate_sps"])) == highlighted
            ]
            return _nearest_row(candidates, "duration_s", duration_s)

        def fmin_row(duration_s: float, threshold_pct: float) -> dict[str, str]:
            candidates = [
                row
                for row in duration_fmin
                if row["reconstruction_mode"] == "phase_only"
                and math.isclose(
                    float(row["threshold_pct"]),
                    threshold_pct,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            ]
            return _nearest_row(candidates, "duration_s", duration_s)

        def latex_fmin(row: dict[str, str]) -> str:
            relation = str(row.get("f_min_relation", ""))
            try:
                rate = float(row.get("f_min_sps", "nan"))
            except (TypeError, ValueError):
                rate = float("nan")
            if not np.isfinite(rate):
                return "n/a"
            if relation == "<=":
                return f"$\\leq${_fmt_rate(rate)}"
            if relation == ">":
                return f"$>${_fmt_rate(rate)}"
            return _fmt_rate(rate)

        duration_rows: list[list[str]] = []
        for requested_duration in configured_durations:
            po = duration_row("phase_only", requested_duration)
            actual_duration = float(po["duration_s"])
            row_values = [
                _fmt_duration(actual_duration),
                f"{float(po['run_abs_error_q95_median']):.4g}\\%",
                f"{float(po['run_abs_error_q95_q95']):.4g}\\%",
                f"{float(po['run_abs_error_max_max']):.4g}\\%",
            ]
            for threshold in threshold_values:
                row_values.append(latex_fmin(fmin_row(actual_duration, threshold)))
            duration_rows.append(row_values)
        duration_headers = [
            "Window",
            f"{_fmt_rate(highlighted)} median run-q95",
            f"{_fmt_rate(highlighted)} hierarchical q95",
            "Worst observed",
        ] + [f"$f_{{\\min}}$ at {value:g}\\%" for value in threshold_values]
        outputs.extend(
            _write_table_triplet(
                tables_dir,
                "table_duration_rate_sufficiency",
                caption=(
                    "Sampling-only duration dependence for exact sub-windows of "
                    "the stationary GEMM-FP16 recordings. Each physical run first "
                    "yields a q95 over window positions and sampling-grid offsets; "
                    "the hierarchical q95 is the 95th percentile of those per-run "
                    "values. Minimum-rate bounds use the unfiltered grid-offset "
                    "reconstruction and require all higher tested rates to pass."
                ),
                label="tab:duration-rate-sufficiency",
                environment="tabular_resize",
                column_spec="@{}l" + "r" * (3 + len(threshold_values)) + "@{}",
                headers=duration_headers,
                rows=duration_rows,
            )
        )

        if duration_campaign_thresholds:
            protocol_rows = []
            for row in sorted(
                duration_campaign_thresholds,
                key=lambda item: str(item["workload"]),
            ):
                protocol_rows.append(
                    [
                        str(row["workload"]),
                        f"{float(row['difference_5_to_reference_pct']):.2f}\\%",
                        _fmt_duration(float(row["first_duration_within_tolerance_s"])),
                        f"{float(row['tolerance_pct']):g}\\% of "
                        f"{_fmt_duration(float(row['reference_duration_s']))}",
                    ]
                )
            outputs.extend(
                _write_table_triplet(
                    tables_dir,
                    "table_duration_protocol_context",
                    caption=(
                        "Benchmark-duration convergence from the independent "
                        "5--600-s campaign. These values include workload start/stop, "
                        "fixed overhead, timeout and automatic boundary effects; they "
                        "are not sampling-only errors."
                    ),
                    label="tab:duration-protocol-context",
                    environment="tabular",
                    column_spec="@{}lrrl@{}",
                    headers=[
                        "Workload",
                        "5-s vs. long-run mean",
                        "First passing duration",
                        "Criterion",
                    ],
                    rows=protocol_rows,
                )
            )

        longest_duration = max(float(row["duration_s"]) for row in duration_summary)
        long_po = duration_row("phase_only", longest_duration)
        long_aa = duration_row("anti_alias", longest_duration)
        if duration_campaign_thresholds:
            first_values = np.asarray(
                [
                    float(row["first_duration_within_tolerance_s"])
                    for row in duration_campaign_thresholds
                ],
                dtype=np.float64,
            )
            protocol_range = (
                f"{_fmt_duration(float(np.min(first_values)))}--"
                f"{_fmt_duration(float(np.max(first_values)))}"
            )
        else:
            protocol_range = "50--200 s (thesis summary)"

        values_already_corrected = (
            cfg.duration_sensitivity.campaign.
            urecs_values_already_include_correction_factor
        )
        urecs_statement = (
            "about $\\pm0.5$\\% versus the PicoScope setup; the stored "
            "processed values already include the setup-specific 0.97 factor"
            if values_already_corrected
            else "about $\\pm0.5$\\% versus the PicoScope setup after the "
            "setup-specific 0.97 factor"
        )
        if duration_urecs_summary:
            preferred_variants = (
                ("stored_processed", "raw")
                if values_already_corrected
                else ("factor_corrected", "raw")
            )
            all_row = None
            for variant in preferred_variants:
                all_row = next(
                    (
                        row for row in duration_urecs_summary
                        if row.get("scope") in {"all", "thesis_summary"}
                        and row.get("variant") == variant
                    ),
                    None,
                )
                if all_row is not None:
                    break
            if all_row is None:
                all_row = duration_urecs_summary[0]
            try:
                q95 = float(all_row.get("abs_error_q95_pct", "nan"))
            except (TypeError, ValueError):
                q95 = float("nan")
            if np.isfinite(q95):
                if values_already_corrected:
                    urecs_statement = (
                        f"q95 absolute difference {q95:.3f}\\% versus the "
                        "PicoScope setup; the stored processed values already "
                        "include the setup-specific 0.97 factor"
                    )
                else:
                    urecs_statement = (
                        f"q95 absolute difference {q95:.3f}\\% versus the "
                        "PicoScope setup after the setup-specific 0.97 factor"
                    )

        guidance_rows = [
            [
                "Run-level energy; exact boundaries",
                _fmt_rate(highlighted),
                _fmt_duration(longest_duration),
                f"hierarchical grid-offset q95 "
                f"{float(long_po['run_abs_error_q95_q95']):.4g}\\%; "
                f"target-rate low-pass "
                f"{float(long_aa['run_abs_error_q95_q95']):.4g}\\%",
            ],
            [
                "Automated u.RECS versus reference path",
                "2 kS/s",
                "5--600 s",
                urecs_statement,
            ],
            [
                "Steady-state mean / protocol convergence",
                "2 kS/s used",
                protocol_range,
                "workload-dependent first tested duration within 3\\% of the 600-s mean",
            ],
            [
                "Faithful filtered-path transient reconstruction",
                "125 / 160 kS/s",
                "10-s PSD windows",
                "first tested rates conservatively retaining at least 95 / 99\\% of the INA225-path fluctuation variance",
            ],
        ]
        outputs.extend(
            _write_table_triplet(
                tables_dir,
                "table_energy_measurement_guidance",
                caption=(
                    "Rate and duration guidance for the investigated Jetson/u.RECS "
                    "setup. Sampling-only accuracy, end-to-end benchmark duration, "
                    "and transient fidelity are separate requirements."
                ),
                label="tab:energy-measurement-guidance",
                environment="tabularx",
                column_spec="@{}L{3.1cm}L{1.8cm}L{1.8cm}Y@{}",
                headers=[
                    "Measurement objective",
                    "Rate",
                    "Duration",
                    "Supported conclusion",
                ],
                rows=guidance_rows,
            )
        )

        duration_macros.update(
            {
                "DurationHighlightedRateSps": highlighted,
                "DurationLongestWindowSeconds": longest_duration,
                "DurationTwoKLongRunQ95Pct": float(
                    long_po["run_abs_error_q95_q95"]
                ),
                "DurationTwoKLongRunWorstPct": float(
                    long_po["run_abs_error_max_max"]
                ),
            }
        )
        macro_durations = {
            "PointOneSecond": 0.1,
            "OneSecond": 1.0,
            "FiveSeconds": 5.0,
            "TenSeconds": 10.0,
            "FiftySeconds": 50.0,
            "OneHundredSeconds": 100.0,
        }
        for label, duration in macro_durations.items():
            row = duration_row("phase_only", duration)
            duration_macros[f"DurationTwoK{label}Q95Pct"] = float(
                row["run_abs_error_q95_q95"]
            )
        for recommendation in duration_recommendation.get("recommendations", []):
            if recommendation.get("reconstruction_mode") != "phase_only":
                continue
            threshold = float(recommendation["threshold_pct"])
            label = {
                0.1: "PointOne",
                0.5: "PointFive",
                1.0: "One",
                2.0: "Two",
                5.0: "Five",
            }.get(threshold, f"Threshold{int(round(1000 * threshold))}")
            raw_duration = recommendation.get("minimum_duration_s")
            if raw_duration not in (None, ""):
                duration_macros[
                    f"DurationTwoKMinWindowFor{label}PctSeconds"
                ] = float(raw_duration)
        if duration_campaign_thresholds:
            first_values = [
                float(row["first_duration_within_tolerance_s"])
                for row in duration_campaign_thresholds
            ]
            duration_macros["ProtocolFirstPassingDurationMinSeconds"] = min(first_values)
            duration_macros["ProtocolFirstPassingDurationMaxSeconds"] = max(first_values)
            five_values = [
                float(row["difference_5_to_reference_pct"])
                for row in duration_campaign_thresholds
            ]
            duration_macros["ProtocolFiveSecondDifferenceMinPct"] = min(five_values)
            duration_macros["ProtocolFiveSecondDifferenceMaxPct"] = max(five_values)

    threshold_by_fraction = {float(row["variance_fraction"]): row for row in thresholds}
    macros: dict[str, float | int | str] = {
        "CommonTraceRunCount": n_runs,
        "AntiAliasFiftyQ95Pct": float(_nearest_row(anti, "target_rate_sps", 50)["abs_error_q95_pct"]),
        "GridOffsetFiftyQ95Pct": float(_nearest_row(phase, "target_rate_sps", 50)["abs_error_q95_pct"]),
        "GridOffsetFiftyMaxPct": float(_nearest_row(phase, "target_rate_sps", 50)["abs_error_max_pct"]),
        "GridOffsetOneFiftyQ95Pct": float(_nearest_row(phase, "target_rate_sps", 150)["abs_error_q95_pct"]),
        "GridOffsetTwoKQ95Pct": float(_nearest_row(phase, "target_rate_sps", 2000)["abs_error_q95_pct"]),
        "IndependentMaxMedianPct": float(max_real["error_median_pct"]),
        "IndependentMaxMedianRateSps": int(round(float(max_real["reported_rate_median_sps"]))),
        "PSDFNinetyFiveHz": f95,
        "PSDFNinetyNineHz": f99,
        "VarianceTwoKPct": float(_nearest_row(variance, "target_rate_sps", 2000)["percent_median"]),
        "VarianceOneTwentyFiveKPct": float(_nearest_row(variance, "target_rate_sps", 125000)["percent_median"]),
        "VarianceOneSixtyKPct": float(_nearest_row(variance, "target_rate_sps", 160000)["percent_median"]),
        "RateForNinetyFiveVarianceSps": int(float(threshold_by_fraction[0.95]["sampling_rate_bound_sps"])),
        "RateForNinetyNineVarianceSps": int(float(threshold_by_fraction[0.99]["sampling_rate_bound_sps"])),
    }
    macros.update(duration_macros)
    return outputs, macros


def _format_macro_value(name: str, value: float | int | str) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not np.isfinite(value):
            return "n/a"
        if "Hz" in name:
            return f"{value:.6f}"
        if abs(value) < 0.001:
            return f"{value:.8g}"
        return f"{value:.6g}"
    return str(value)


_LATEX_DIGIT_WORDS = {
    "0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
    "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine",
}


def _latex_command_name(name: str) -> str:
    """Return a TeX-safe control-sequence name containing letters only."""
    converted: list[str] = []
    for character in str(name):
        if character.isalpha():
            converted.append(character)
        elif character.isdigit():
            converted.append(_LATEX_DIGIT_WORDS[character])
        else:
            converted.append("X")
    result = "".join(converted)
    if not result or re.fullmatch(r"[A-Za-z]+", result) is None:
        raise ValueError(f"Cannot convert macro name to a TeX-safe form: {name!r}")
    return result


def _write_macros(path: Path, macros: dict[str, float | int | str]) -> Path:
    lines = [
        "% Auto-generated by common_reference_psd_tool. Do not edit by hand.",
        "% TeX control-sequence names contain letters only; see the adjacent name-map CSV.",
        "% Numeric values are unitless unless the macro name states otherwise.",
    ]
    seen_commands: set[str] = set()
    mapping_rows: list[dict[str, Any]] = []
    for name in sorted(macros):
        command = _latex_command_name(name)
        if command in seen_commands:
            raise ValueError(
                f"Macro-name collision after TeX sanitisation: {name!r} -> {command!r}"
            )
        seen_commands.add(command)
        value = _format_macro_value(name, macros[name])
        if command != name:
            lines.append(f"% {name} -> {command}")
        lines.append(f"\\providecommand{{\\{command}}}{{{value}}}")
        mapping_rows.append(
            {
                "analysis_key": name,
                "tex_command": f"\\{command}",
                "rendered_value": value,
            }
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    write_csv(path.with_name(f"{path.stem}_name_map.csv"), mapping_rows)
    return path


def _write_figure_snippets(path: Path, metadata: dict[str, Any]) -> Path:
    captions = metadata.get("figure_captions", {})
    widths = {
        "sampling_rate_method": "\\textwidth",
        "measurement_setup_heterogeneous": "0.96\\textwidth",
        "common_trace_results_paper": "\\textwidth",
        "psd_variance_results_paper": "\\textwidth",
        "energy_rate_duration_sufficiency_paper": "\\textwidth",
        "duration_protocol_context_paper": "\\textwidth",
    }
    lines = ["% Auto-generated figure snippets. Copy or input as needed.", ""]
    for stem in widths:
        spec = captions.get(stem, {})
        caption = str(spec.get("caption", stem))
        label = str(spec.get("label", f"fig:{stem}"))
        # Use the manuscript macro for u.RECS where appropriate.
        caption = caption.replace("u.RECS", "\\urecs{}")
        caption = caption.replace("Q0.95", "$Q_{0.95}$")
        lines.extend(
            [
                "\\begin{figure}[t]",
                "\\centering",
                f"\\includegraphics[width={widths[stem]}]{{figures/{stem}.pdf}}",
                f"\\caption{{{caption}}}",
                f"\\label{{{label}}}",
                "\\end{figure}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_table_include(
    path: Path,
    table_tex_files: Sequence[Path],
    *,
    include_prefix: str = "tables",
) -> Path:
    """Write manuscript-relative table include snippets.

    ``include_prefix`` is explicit because scope tables live below
    ``scope_validation/tables`` in the combined artifact bundle, whereas the
    main tables live directly below ``tables``.
    """
    prefix = include_prefix.strip("/")
    lines = ["% Auto-generated table includes. Uncomment the tables required by the manuscript.", ""]
    for table in sorted(table_tex_files):
        lines.append(f"% \\input{{{prefix}/{table.name}}}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _copy_key_data(output_root: Path, data_dir: Path) -> list[Path]:
    relative = [
        Path("analysis_manifest.json"),
        Path("SUMMARY.md"),
        Path("common_trace/anti_aliased_summary.csv"),
        Path("common_trace/phase_only_summary.csv"),
        Path("common_trace/f_min.csv"),
        Path("real_measurements/real_measurements_summary.csv"),
        Path("psd/psd_metrics_summary.csv"),
        Path("psd/variance_capture_summary.csv"),
        Path("psd/variance_capture_thresholds.csv"),
        Path("psd/variance_bands_summary.csv"),
        Path("psd/psd_bandwidth_sensitivity_summary.csv"),
        Path("psd/psd_bandwidth_sensitivity_decision.json"),
        Path("psd/psd_summary.npz"),
        Path("rate_duration/same_trace_per_run.csv"),
        Path("rate_duration/same_trace_summary.csv"),
        Path("rate_duration/f_min_by_duration.csv"),
        Path("rate_duration/highlighted_rate_by_duration.csv"),
        Path("rate_duration/highlighted_rate_duration_thresholds.csv"),
        Path("rate_duration/highlighted_rate_duration_decision.json"),
        Path("rate_duration/RATE_DURATION_SUMMARY.md"),
        Path("rate_duration/same_trace_duration_analysis.json"),
        Path("rate_duration/duration_campaign/reference_convergence_thresholds.csv"),
        Path("rate_duration/duration_campaign/reference_convergence.csv"),
        Path("rate_duration/duration_campaign/urecs_vs_pico_summary.csv"),
        Path("rate_duration/duration_campaign/source.json"),
        Path("validation/reference_runs.json"),
        Path("validation/real_measurement_run_selection.csv"),
    ]
    outputs: list[Path] = []
    for rel in relative:
        source = output_root / rel
        if not source.is_file():
            continue
        destination = data_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        outputs.append(destination)
    return outputs


def _artifact_inventory(root: Path, exclude: set[Path] | None = None) -> list[dict[str, Any]]:
    excluded = {path.resolve() for path in (exclude or set())}
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.resolve() in excluded:
            continue
        rows.append(
            {
                "relative_path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "suffix": path.suffix.lower(),
            }
        )
    return rows


def _write_summary(
    path: Path,
    cfg: AnalysisConfig,
    metadata: dict[str, Any],
    macros: dict[str, float | int | str],
    tables: Sequence[Path],
    figures: Sequence[Path],
    scope_artifacts: Path | None,
) -> Path:
    lines = [
        "# Paper documentation artifacts",
        "",
        f"- Paper ID: `{metadata.get('paper_id', 'unknown')}`",
        f"- Manuscript metadata version: `{metadata.get('manuscript_version', 'unknown')}`",
        f"- Analysis root: `{cfg.output_root}`",
        f"- Generated UTC: `{utc_now_iso()}`",
        "",
        "## Paper-ready figures",
        "",
    ]
    for figure in sorted(path.parent.joinpath("figures").glob("*.pdf")):
        lines.append(f"- `figures/{figure.name}`")
    lines.extend(["", "## LaTeX-ready tables", ""])
    for table in sorted(path.parent.joinpath("tables").glob("*.tex")):
        lines.append(f"- `tables/{table.name}`")
    lines.extend(
        [
            "",
            "## Generated numerical macros",
            "",
            "The file `latex/paper_results_macros.tex` exposes the analysis values as `\\providecommand` macros, so manuscript text can reference the same numbers as the figures and tables.",
            "",
            "Key values:",
            "",
            f"- Common-trace runs: {int(macros['CommonTraceRunCount'])}",
            f"- Target-rate low-pass at 50 S/s, q95 absolute energy error: {float(macros['AntiAliasFiftyQ95Pct']):.7g}%",
            f"- Unfiltered grid-offset at 50 S/s, q95: {float(macros['GridOffsetFiftyQ95Pct']):.3f}%",
            f"- Unfiltered grid-offset at 2 kS/s, q95: {float(macros['GridOffsetTwoKQ95Pct']):.3f}%",
            f"- f95 / f99: {float(macros['PSDFNinetyFiveHz'])/1000:.2f} / {float(macros['PSDFNinetyNineHz'])/1000:.2f} kHz",
            f"- Variance below Nyquist at 2 / 125 / 160 kS/s: {float(macros['VarianceTwoKPct']):.2f}% / {float(macros['VarianceOneTwentyFiveKPct']):.2f}% / {float(macros['VarianceOneSixtyKPct']):.2f}%",
            "",
            "## Provenance",
            "",
            "- `manifest/paper_artifacts_manifest.json` records tool/package versions and SHA-256 hashes of analysis inputs.",
            "- `manifest/paper_artifacts_inventory.csv` lists every generated artifact and its SHA-256 hash; the ZIP itself is intentionally excluded from its own inventory.",
            "- `paper_documentation_artifacts.zip.sha256` records the SHA-256 of the complete transfer bundle.",
            "- `paper_documentation_artifacts_review.zip` is a compact review-only bundle without large NPZ arrays; it contains regenerated inventories that match the review ZIP exactly.",
            "- `paper_documentation_artifacts_review.zip.sha256` records the review-bundle SHA-256.",
            "- `data/` contains the compact analysis tables and PSD aggregate needed to reproduce the paper figures without the multi-gigabyte raw traces.",
            "- The static manuscript overview tables are stored in `paper_artifacts_metadata.yaml`; numerical common-trace/PSD tables are generated directly from analysis output.",
        ]
    )
    if "DurationTwoKLongRunQ95Pct" in macros:
        lines.extend(
            [
                "",
                "Duration-sensitive sampling result:",
                "",
                f"- 2 kS/s, longest exact sub-window: 95th percentile across physical runs of each run's q95 grid/window error = {float(macros['DurationTwoKLongRunQ95Pct']):.4g}%.",
                f"- Duration-sensitive figure: `figures/energy_rate_duration_sufficiency_paper.pdf`.",
                "- This isolates sampling. The separate 5-600-s campaign must still be used for start/stop, boundary and fixed-overhead effects.",
            ]
        )
    if scope_artifacts is not None:
        lines.extend(["", f"Scope-validation documentation was also generated at `{scope_artifacts}`."])
    lines.extend(
        [
            "",
            "## Direct manuscript integration",
            "",
            "1. Copy `figures/*.pdf` into the manuscript's `figures/` directory.",
            "2. Copy the required `tables/*.tex` files and replace hard-coded table blocks with `\\input{...}`.",
            "3. Input `latex/paper_artifacts_include.tex` in the preamble to load both main and optional scope-validation macros without manual number drift.",
            "4. Use `latex/paper_all_figure_snippets.tex` and `latex/paper_all_table_snippets.tex` as the canonical main-plus-scope snippet lists.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_bundle(root: Path) -> tuple[Path, Path]:
    """Create a deterministic-metadata bundle and an external SHA-256 sidecar."""
    bundle = root / "paper_documentation_artifacts.zip"
    sidecar = root / "paper_documentation_artifacts.zip.sha256"
    for path in (bundle, sidecar):
        if path.exists():
            path.unlink()

    excluded = {bundle.resolve(), sidecar.resolve()}
    with zipfile.ZipFile(
        bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.resolve() in excluded:
                continue
            relative = str(path.relative_to(root)).replace(os.sep, "/")
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)

    sidecar.write_text(
        f"{_sha256(bundle)}  {bundle.name}\n", encoding="utf-8"
    )
    return bundle, sidecar


def _write_review_bundle(root: Path) -> tuple[Path, Path]:
    """Create a compact review bundle with a matching internal inventory.

    Large aggregate ``.npz`` arrays are intentionally omitted.  The review
    bundle is therefore suitable for manuscript, table, figure, JSON, and
    provenance review, but it is not advertised as the fully self-contained
    figure-regeneration package.  Inventories are regenerated inside the
    staged tree after the omissions, so every listed file is actually present.
    """
    bundle = root / "paper_documentation_artifacts_review.zip"
    sidecar = root / "paper_documentation_artifacts_review.zip.sha256"
    for path in (bundle, sidecar):
        if path.exists():
            path.unlink()

    bundle_names = {
        "paper_documentation_artifacts.zip",
        "paper_documentation_artifacts.zip.sha256",
        "paper_documentation_artifacts_review.zip",
        "paper_documentation_artifacts_review.zip.sha256",
    }
    inventory_relpaths = {
        Path("manifest/paper_artifacts_inventory.csv"),
        Path("scope_validation/manifest/scope_paper_artifacts_inventory.csv"),
    }

    with TemporaryDirectory(prefix="commonref-review-bundle-") as temporary:
        staging = Path(temporary) / "paper_artifacts_review"
        staging.mkdir(parents=True)
        omitted: list[dict[str, Any]] = []

        for source in sorted(root.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(root)
            if source.name in bundle_names or relative in inventory_relpaths:
                continue
            if source.suffix.lower() == ".npz":
                omitted.append(
                    {
                        "relative_path": str(relative),
                        "bytes": source.stat().st_size,
                        "sha256": _sha256(source),
                        "reason": "large_aggregate_npz_omitted_from_review_bundle",
                    }
                )
                continue
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        notice = staging / "REVIEW_BUNDLE_NOTICE.md"
        notice.write_text(
            "# Compact paper-artifact review bundle\n\n"
            "This bundle contains all generated figures, LaTeX/CSV/Markdown "
            "tables, strict JSON metadata, macros, and compact provenance "
            "files required for manuscript review. Large aggregate NPZ arrays "
            "are intentionally omitted. Use `paper_documentation_artifacts.zip` "
            "for the complete self-contained artifact transfer. The inventories "
            "inside this review bundle were regenerated after the omissions and "
            "therefore describe this ZIP exactly.\n",
            encoding="utf-8",
        )
        write_json(
            staging / "manifest" / "review_bundle_manifest.json",
            {
                "schema_version": 1,
                "created_utc": utc_now_iso(),
                "tool_version": __version__,
                "bundle_role": "compact_review",
                "complete_regeneration_bundle": False,
                "omitted_files": omitted,
            },
        )

        scope_root = staging / "scope_validation"
        if scope_root.is_dir():
            scope_inventory = (
                scope_root / "manifest" / "scope_paper_artifacts_inventory.csv"
            )
            scope_inventory.parent.mkdir(parents=True, exist_ok=True)
            write_csv(
                scope_inventory,
                _artifact_inventory(scope_root, exclude={scope_inventory}),
            )

        root_inventory = staging / "manifest" / "paper_artifacts_inventory.csv"
        root_inventory.parent.mkdir(parents=True, exist_ok=True)
        write_csv(
            root_inventory,
            _artifact_inventory(staging, exclude={root_inventory}),
        )

        with zipfile.ZipFile(
            bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for source in sorted(staging.rglob("*")):
                if not source.is_file():
                    continue
                relative = str(source.relative_to(staging)).replace(os.sep, "/")
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (source.stat().st_mode & 0xFFFF) << 16
                with source.open("rb") as input_handle, archive.open(
                    info, "w", force_zip64=True
                ) as output_handle:
                    shutil.copyfileobj(
                        input_handle, output_handle, length=1024 * 1024
                    )

    sidecar.write_text(
        f"{_sha256(bundle)}  {bundle.name}\n", encoding="utf-8"
    )
    return bundle, sidecar


def generate_paper_artifacts(
    cfg: AnalysisConfig,
    runs: Sequence[int],
    metadata_path: Path,
    *,
    scope_output_root: Path | None = None,
    force: bool = False,
) -> Path:
    metadata = load_yaml(metadata_path)
    if int(metadata.get("schema_version", 0)) != PAPER_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported paper-artifact metadata schema: {metadata.get('schema_version')}"
        )

    required = [
        cfg.output_root / "common_trace" / "anti_aliased_summary.csv",
        cfg.output_root / "common_trace" / "phase_only_summary.csv",
        cfg.output_root / "common_trace" / "f_min.csv",
        cfg.output_root / "real_measurements" / "real_measurements_summary.csv",
        cfg.output_root / "psd" / "psd_metrics_summary.csv",
        cfg.output_root / "psd" / "variance_capture_summary.csv",
        cfg.output_root / "psd" / "variance_capture_thresholds.csv",
        cfg.output_root / "psd" / "psd_summary.npz",
    ]
    _require_files(required)

    artifact_root = cfg.output_root / str(metadata.get("artifact_output_subdir", "paper_artifacts"))
    if force and artifact_root.exists():
        shutil.rmtree(artifact_root)
    figures_dir = artifact_root / "figures"
    tables_dir = artifact_root / "tables"
    latex_dir = artifact_root / "latex"
    data_dir = artifact_root / "data"
    manifest_dir = artifact_root / "manifest"
    for directory in (figures_dir, tables_dir, latex_dir, data_dir, manifest_dir):
        directory.mkdir(parents=True, exist_ok=True)

    anti = read_csv(cfg.output_root / "common_trace" / "anti_aliased_summary.csv")
    n_runs = max(int(float(row["n_runs"])) for row in anti)
    reference_runs_path = cfg.output_root / "validation" / "reference_runs.json"
    if reference_runs_path.is_file():
        reference_payload = read_json(reference_runs_path)
        first_reference = reference_payload.get("runs", [{}])[0]
        active_duration = float(
            first_reference.get(
                "yaml_duration_s",
                first_reference.get("active_duration_from_indices_s", 104.0),
            )
        )
    else:
        active_duration = 104.0

    figure_outputs: list[Path] = []
    for pair in (
        _figure_sampling_method(figures_dir, n_runs=n_runs, active_duration_s=active_duration),
        _figure_measurement_setup(figures_dir, metadata),
        _figure_common_trace(figures_dir, cfg.output_root),
        _figure_psd_variance(figures_dir, cfg.output_root),
    ):
        figure_outputs.extend(pair)
    duration_contract = _rate_duration_contract(cfg.output_root)
    duration_required = [
        duration_contract["summary_path"],
        duration_contract["fmin_path"],
        duration_contract["decision_path"],
    ]
    if all(path.is_file() for path in duration_required):
        figure_outputs.extend(
            _figure_duration_rate_sufficiency(figures_dir, cfg.output_root)
        )
        protocol_path = duration_contract["campaign_thresholds_path"]
        if protocol_path.is_file() and read_csv(protocol_path):
            figure_outputs.extend(
                _figure_duration_protocol_context(figures_dir, cfg.output_root)
            )
    elif cfg.duration_sensitivity.enabled:
        LOGGER.warning(
            "Duration-sensitive paper figure was not generated because the duration stage has not completed. "
            "Run `python -m commonref.cli duration --config ...` first."
        )

    table_outputs = _generate_static_tables(metadata, tables_dir)
    dynamic_outputs, macros = _dynamic_tables(
        cfg.output_root, metadata, tables_dir, cfg
    )
    table_outputs.extend(dynamic_outputs)

    macros_path = _write_macros(latex_dir / "paper_results_macros.tex", macros)
    figure_snippets = _write_figure_snippets(latex_dir / "paper_figure_snippets.tex", metadata)
    table_tex = [path for path in table_outputs if path.suffix == ".tex"]
    table_snippets = _write_table_include(latex_dir / "paper_table_snippets.tex", table_tex)
    latex_master = latex_dir / "paper_artifacts_include.tex"
    latex_master.write_text(
        "% Auto-generated documentation include file.\n"
        "\\input{latex/paper_results_macros.tex}\n"
        "% Figure and table blocks are available in the adjacent snippet files.\n",
        encoding="utf-8",
    )

    copied_data = _copy_key_data(cfg.output_root, data_dir)
    shutil.copy2(metadata_path, artifact_root / "paper_artifacts_metadata.yaml")

    scope_artifact_path: Path | None = None
    if scope_output_root is not None and (scope_output_root / "cross_rate_summary.csv").is_file():
        scope_artifact_path = generate_scope_documentation_artifacts(
            scope_output_root,
            artifact_root / "scope_validation",
            force=force,
        )

    # Build the central LaTeX include only after optional scope artifacts exist.
    include_lines = [
        "% Auto-generated documentation include file.",
        "\\input{latex/paper_results_macros.tex}",
    ]
    if scope_artifact_path is not None:
        include_lines.append(
            "\\input{scope_validation/latex/scope_results_macros.tex}"
        )
        with table_snippets.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n% Scope-validation tables\n"
                "% \\input{scope_validation/latex/scope_table_snippets.tex}\n"
            )
        with figure_snippets.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n% Scope-validation figure blocks\n"
                "% \\input{scope_validation/latex/scope_figure_snippets.tex}\n"
            )
    include_lines.append(
        "% Figure and table blocks are available in the adjacent snippet files."
    )
    latex_master.write_text("\n".join(include_lines) + "\n", encoding="utf-8")

    all_figure_snippets = latex_dir / "paper_all_figure_snippets.tex"
    all_figure_lines = [
        "% Auto-generated canonical figure snippets.",
        "\\input{latex/paper_figure_snippets.tex}",
    ]
    if scope_artifact_path is not None:
        all_figure_lines.append(
            "\\input{scope_validation/latex/scope_figure_snippets.tex}"
        )
    all_figure_snippets.write_text(
        "\n".join(all_figure_lines) + "\n", encoding="utf-8"
    )

    all_table_snippets = latex_dir / "paper_all_table_snippets.tex"
    all_table_lines = [
        "% Auto-generated canonical table include list.",
        "\\input{latex/paper_table_snippets.tex}",
    ]
    if scope_artifact_path is not None:
        all_table_lines.append(
            "\\input{scope_validation/latex/scope_table_snippets.tex}"
        )
    all_table_snippets.write_text(
        "\n".join(all_table_lines) + "\n", encoding="utf-8"
    )

    duration_input_candidates = [
        cfg.output_root / "rate_duration" / "same_trace_summary.csv",
        cfg.output_root / "rate_duration" / "f_min_by_duration.csv",
        cfg.output_root / "rate_duration" / "highlighted_rate_duration_decision.json",
        cfg.output_root / "rate_duration" / "duration_campaign" / "reference_convergence.csv",
        cfg.output_root / "rate_duration" / "duration_campaign" / "reference_convergence_thresholds.csv",
        cfg.output_root / "rate_duration" / "duration_campaign" / "urecs_vs_pico_summary.csv",
        cfg.output_root / "rate_duration" / "duration_campaign" / "source.json",
    ]
    manifest_inputs = required + [metadata_path] + [
        path for path in duration_input_candidates if path.is_file()
    ]
    if scope_output_root is not None:
        manifest_inputs.extend(
            path
            for path in (
                scope_output_root / "cross_rate_summary.csv",
                scope_output_root / "scope_comparison_manifest.json",
                scope_output_root / "scope_analysis_overview.json",
                scope_output_root / "diagnostics" / "operating_point_per_pair.csv",
                scope_output_root / "diagnostics" / "segment_mean_regression.csv",
                scope_output_root / "tek_reference" / "selection.json",
                scope_output_root / "pico_usability" / "selection.json",
                scope_output_root / "pico_usability" / "pico_usability.json",
            )
            if path.is_file()
        )
    # Keep deterministic order and avoid duplicate hashes.
    manifest_inputs = list(dict.fromkeys(manifest_inputs))
    input_hashes = [
        {
            "path": str(path),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in manifest_inputs
    ]
    manifest = {
        "schema_version": PAPER_ARTIFACT_SCHEMA_VERSION,
        "created_utc": utc_now_iso(),
        "tool_version": __version__,
        "paper_id": metadata.get("paper_id"),
        "manuscript_version": metadata.get("manuscript_version"),
        "analysis_root": str(cfg.output_root),
        "artifact_root": str(artifact_root),
        "runs": list(runs),
        "package_versions": package_versions(),
        "input_files": input_hashes,
        "numerical_macros": macros,
        "scope_output_root": None if scope_output_root is None else str(scope_output_root),
        "copied_compact_data": [
            str(path.relative_to(artifact_root)) for path in copied_data
        ],
    }
    manifest_path = manifest_dir / "paper_artifacts_manifest.json"
    write_json(manifest_path, manifest)

    summary = _write_summary(
        artifact_root / "PAPER_ARTIFACTS_SUMMARY.md",
        cfg,
        metadata,
        macros,
        table_outputs,
        figure_outputs,
        scope_artifact_path,
    )

    inventory_path = manifest_dir / "paper_artifacts_inventory.csv"
    bundle = artifact_root / "paper_documentation_artifacts.zip"
    bundle_hash_path = artifact_root / "paper_documentation_artifacts.zip.sha256"
    review_bundle = artifact_root / "paper_documentation_artifacts_review.zip"
    review_bundle_hash_path = artifact_root / "paper_documentation_artifacts_review.zip.sha256"
    # Stale bundles from a previous artifact refresh must never appear inside
    # either the full inventory or the full transfer bundle.
    for stale in (
        bundle, bundle_hash_path, review_bundle, review_bundle_hash_path
    ):
        if stale.exists():
            stale.unlink()
    inventory = _artifact_inventory(
        artifact_root,
        exclude={
            inventory_path, bundle, bundle_hash_path,
            review_bundle, review_bundle_hash_path,
        },
    )
    write_csv(inventory_path, inventory)
    bundle, bundle_hash_path = _write_bundle(artifact_root)
    review_bundle, review_bundle_hash_path = _write_review_bundle(artifact_root)

    LOGGER.info("Paper figures: %s", figures_dir)
    LOGGER.info("Paper tables: %s", tables_dir)
    LOGGER.info("Paper documentation bundle: %s", bundle)
    LOGGER.info("Compact review bundle: %s", review_bundle)
    LOGGER.info("Compact review bundle SHA-256: %s", review_bundle_hash_path)
    return summary


# ---------------------------------------------------------------------------
# Paper-ready documentation for the paired Tektronix/PicoScope validation.
# This is generated automatically by scope-compare and becomes useful as soon
# as multiple rates/pairs are present.
# ---------------------------------------------------------------------------

def _scope_documentation_context(scope_output_root: Path) -> dict[str, str]:
    """Infer stable manuscript labels from the scope-analysis manifest."""
    manifest_path = scope_output_root / "scope_comparison_manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    config = manifest.get("config", {}) if isinstance(manifest, dict) else {}
    dataset_root = str(config.get("dataset_root", scope_output_root))
    dataset_descriptor = config.get("dataset", {}) if isinstance(config, dict) else {}
    compact = re.sub(r"[^a-z0-9]+", "", dataset_root.lower())
    explicit_workload = (
        str(dataset_descriptor.get("workload_label", "")).strip()
        if isinstance(dataset_descriptor, dict)
        else ""
    )
    if explicit_workload:
        workload = explicit_workload
    elif "gemmfp32" in compact:
        workload = "GEMM-FP32"
    elif "gemmfp16" in compact:
        workload = "GEMM-FP16"
    elif "yolofp32" in compact:
        workload = "YOLO-FP32"
    else:
        workload = Path(dataset_root).name.replace("_", "-") or "paired workload"
    voltage = config.get("voltage_model", {}) if isinstance(config, dict) else {}
    calibration_id = str(voltage.get("calibration_id", "shared voltage model"))
    zero_model_path = scope_output_root / "zero_correction" / "zero_offset_model.json"
    zero_model = read_json(zero_model_path) if zero_model_path.is_file() else {}
    if bool(zero_model.get("correction_applied", False)):
        zero_note = (
            "Selected currents, energies and PSDs include the separately marked "
            f"additive Tektronix zero correction of "
            f"{float(zero_model.get('offset_applied_ma', 0.0)):+.3f} mA; "
            "uncorrected values remain archived."
        )
    else:
        zero_note = (
            f"Adaptive zero-offset status: {zero_model.get('status', 'disabled')}; "
            "no correction was applied."
        )
    return {
        "workload": workload,
        "signal": (
            str(dataset_descriptor.get("signal_label"))
            if isinstance(dataset_descriptor, dict)
            and dataset_descriptor.get("signal_label")
            else "estimated power derived from the measured current"
        ),
        "tek_signal": "Tektronix-current-probe estimated power",
        "pico_signal": "PicoScope/INA225 estimated power",
        "voltage_model": calibration_id,
        "zero_correction_note": zero_note,
    }


def _copy_scope_key_data(scope_output_root: Path, data_root: Path) -> list[Path]:
    """Copy compact scope aggregates needed to regenerate paper artifacts."""
    relative_paths = [
        Path("cross_rate_summary.csv"),
        Path("scope_analysis_overview.json"),
        Path("scope_comparison_manifest.json"),
        Path("SCOPE_COMPARISON_SUMMARY.md"),
        Path("input_discovery/rate_inventory.csv"),
        Path("input_discovery/skipped_pairs.csv"),
        Path("diagnostics/operating_point_diagnostics.json"),
        Path("diagnostics/operating_point_per_pair.csv"),
        Path("diagnostics/operating_region_summary.csv"),
        Path("diagnostics/segment_mean_regression.csv"),
        Path("external_idle/external_idle_overview.csv"),
        Path("zero_correction/zero_offset_model.json"),
        Path("zero_correction/zero_offset_pair_evidence.csv"),
        Path("zero_correction/zero_offset_rate_evidence.csv"),
        Path("tek_reference/candidate_rates.csv"),
        Path("tek_reference/selection.json"),
        Path("tek_reference/tek_primary_metrics.csv"),
        Path("tek_reference/tek_primary_psd_summary.npz"),
        Path("pico_usability/selection.json"),
        Path("pico_usability/pico_usability.json"),
        Path("pico_usability/pico_usability.csv"),
        Path("pico_usability/paired_band_agreement.csv"),
        Path("pico_usability/paired_psd_summary.npz"),
    ]
    outputs: list[Path] = []
    for rel in relative_paths:
        source = scope_output_root / rel
        if not source.is_file():
            continue
        destination = data_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        outputs.append(destination)

    # Preserve compact external-idle provenance and per-rate summaries.  The
    # full Parquet recordings are never copied into a paper bundle.
    external_idle_root = scope_output_root / "external_idle"
    if external_idle_root.is_dir():
        for source in sorted(external_idle_root.glob("*Sps/*")):
            if not source.is_file():
                continue
            if source.suffix.lower() not in {".json", ".csv", ".npz"}:
                continue
            destination = data_root / source.relative_to(scope_output_root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            outputs.append(destination)

    # Preserve the fastest native Tek aggregate used for the high-frequency
    # diagnostic without copying per-pair raw/intermediate files.
    native_candidates: list[tuple[float, Path]] = []
    cross_path = scope_output_root / "cross_rate_summary.csv"
    if cross_path.is_file():
        for row in read_csv(cross_path):
            rate = int(float(row["rate_sps"]))
            path = scope_output_root / f"{rate}Sps" / "psd" / "tek_native_psd_summary.npz"
            if path.is_file():
                native_candidates.append((float(row.get("tek_rate_sps", rate)), path))
    if native_candidates:
        _, source = max(native_candidates, key=lambda item: item[0])
        destination = data_root / "high_rate_extension" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        outputs.append(destination)
    return outputs


def _write_scope_figure_snippets(
    path: Path,
    context: dict[str, str],
    figures_dir: Path | None = None,
) -> Path:
    specs = [
        (
            "scope_validation_time_domain_paper",
            "fig:scope-time-domain",
            f"Trigger-matched {context['workload']} validation in the time domain. Relative estimated-energy differences are shown against the Tektronix segment-mean current; the affine current fit is diagnostic only and is not applied as a gain calibration. {context['zero_correction_note']}",
        ),
        (
            "scope_validation_idle_baseline_paper",
            "fig:scope-idle-baseline",
            f"{context['workload']} idle/DC-baseline diagnostics. Raw full-record estimated-energy differences remain archived; active-window and idle-subtracted incremental results diagnose whether a stable baseline mismatch dominates a low-duty-cycle workload. Same-run idle is preferred and the independent exact-rate idle data are a documented cross-check or fallback.",
        ),
        (
            "scope_validation_zero_offset_correction_paper",
            "fig:scope-zero-offset",
            f"Adaptive additive zero-offset audit for {context['workload']}. The configured session model evaluates stable rate-wise evidence and preserves raw and selected offset-corrected energy differences side by side. Because the PicoScope setup participates in the estimate, the corrected comparison is a post-hoc salvage analysis rather than an independent absolute PicoScope validation.",
        ),
        (
            "scope_validation_tek_reference_psd_paper",
            "fig:scope-tek-reference-psd",
            f"Native Tektronix reference PSD for {context['workload']} {context['signal']}. Active and pre-benchmark idle windows are mean-centred separately; reported frequency percentiles use physical runs as the uncertainty unit.",
        ),
        (
            "scope_validation_pico_usability_paper",
            "fig:scope-pico-usability",
            f"Paired {context['workload']} comparison within the common Tektronix/PicoScope band. The PicoScope/INA225 setup is evaluated against the Tektronix-primary reference using the same current-dependent voltage model.",
        ),
        (
            "scope_validation_tek_high_frequency_extension_paper",
            "fig:scope-tek-high-frequency",
            f"High-rate Tektronix-only extension for {context['workload']}. Records without a valid idle interval are explicitly active-only diagnostics and are not interpreted as workload-related excess PSD.",
        ),
        (
            "scope_validation_bandwidth_coverage_paper",
            "fig:scope-bandwidth-coverage",
            f"Tektronix-native spectral coverage for {context['workload']}, separated into idle-subtracted workload-related measurements and active-only high-rate diagnostics.",
        ),
    ]
    lines = ["% Auto-generated scope-validation figure snippets.", ""]
    for stem, label, caption in specs:
        if figures_dir is not None and not (figures_dir / f"{stem}.pdf").is_file():
            continue
        lines.extend(
            [
                "\\begin{figure}[t]",
                "\\centering",
                f"\\includegraphics[width=\\textwidth]{{scope_validation/figures/{stem}.pdf}}",
                f"\\caption{{{caption}}}",
                f"\\label{{{label}}}",
                "\\end{figure}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_scope_documentation_artifacts(
    scope_output_root: Path,
    artifact_root: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """Generate paper artifacts with Tektronix as the primary PSD reference.

    The paired PicoScope results are used to quantify how much of the Tektronix
    reference spectrum is retained by the PicoScope/INA225 setup.  High-rate Tek
    records without a valid idle window remain clearly labelled active-only.
    """

    cross_path = scope_output_root / "cross_rate_summary.csv"
    _require_files([cross_path])
    root = artifact_root or scope_output_root / "paper_artifacts"
    if force and root.exists():
        shutil.rmtree(root)
    figures = root / "figures"
    tables = root / "tables"
    latex = root / "latex"
    data_root = root / "data"
    manifest_dir = root / "manifest"
    for directory in (figures, tables, latex, data_root, manifest_dir):
        directory.mkdir(parents=True, exist_ok=True)
    context = _scope_documentation_context(scope_output_root)
    zero_model_path = scope_output_root / "zero_correction" / "zero_offset_model.json"
    zero_rate_path = scope_output_root / "zero_correction" / "zero_offset_rate_evidence.csv"
    zero_pair_path = scope_output_root / "zero_correction" / "zero_offset_pair_evidence.csv"
    zero_model = read_json(zero_model_path) if zero_model_path.is_file() else {}
    zero_rate_rows = read_csv(zero_rate_path) if zero_rate_path.is_file() else []
    zero_pair_rows = read_csv(zero_pair_path) if zero_pair_path.is_file() else []
    zero_artifact_available = bool(zero_model.get("enabled", False)) or bool(
        zero_rate_rows
    )

    rows = sorted(read_csv(cross_path), key=lambda row: float(row["rate_sps"]))
    x = np.asarray([float(row.get("tek_rate_sps", row["rate_sps"])) for row in rows])
    pico_x = np.asarray([float(row.get("pico_rate_sps", row["rate_sps"])) for row in rows])

    # ------------------------------------------------------------------
    # Time-domain figure: show the operating-point dependence directly.
    # This replaces the misleading impression that high q95 values were a
    # monotonic sampling-rate effect.
    # ------------------------------------------------------------------
    pair_path = scope_output_root / "diagnostics" / "operating_point_per_pair.csv"
    regression_path = scope_output_root / "diagnostics" / "segment_mean_regression.csv"
    pair_rows = read_csv(pair_path) if pair_path.is_file() else []
    regression_rows = read_csv(regression_path) if regression_path.is_file() else []
    if pair_rows:
        tek_current = np.asarray([float(row["tek_mean_current_a"]) for row in pair_rows])
        pico_current = np.asarray([float(row["pico_mean_current_a"]) for row in pair_rows])
        energy_error = np.asarray([float(row["pico_vs_tek_energy_error_pct"]) for row in pair_rows])
        current_delta_ma = np.asarray([float(row["mean_current_difference_ma"]) for row in pair_rows])
        rates = np.asarray([float(row["tek_rate_sps"]) for row in pair_rows])
        threshold = float(
            next(
                (
                    row.get("low_current_threshold_a", "0.75")
                    for row in rows
                    if row.get("low_current_threshold_a") not in (None, "")
                ),
                0.75,
            )
        )
        fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.25))
        norm = mpl.colors.LogNorm(vmin=max(1.0, float(np.min(rates))), vmax=float(np.max(rates)))
        scatter = axes[0].scatter(
            tek_current,
            energy_error,
            c=rates,
            norm=norm,
            cmap="viridis",
            s=22,
            alpha=0.82,
            edgecolors="none",
        )
        axes[0].axvspan(0.0, threshold, alpha=0.08, label="Low-current region")
        axes[0].axhline(0.0, linewidth=0.8)
        axes[0].axhline(1.0, linestyle="--", linewidth=0.8, label="±1%")
        axes[0].axhline(-1.0, linestyle="--", linewidth=0.8)
        axes[0].set_xlabel("Tektronix segment-mean current (A)")
        axes[0].set_ylabel("Estimated-energy difference, Pico - Tek (%)")
        axes[0].set_title("(a) Relative error depends on operating current", fontsize=8.2)
        axes[0].grid(True, linewidth=0.35, alpha=0.45)
        axes[0].legend(fontsize=6.2, loc="best")
        cbar = fig.colorbar(scatter, ax=axes[0], pad=0.02)
        cbar.set_label("Tektronix sampling rate (S/s)", fontsize=6.5)
        cbar.ax.tick_params(labelsize=6)

        axes[1].scatter(
            tek_current,
            pico_current,
            c=rates,
            norm=norm,
            cmap="viridis",
            s=22,
            alpha=0.82,
            edgecolors="none",
        )
        lower = min(float(np.min(tek_current)), float(np.min(pico_current)))
        upper = max(float(np.max(tek_current)), float(np.max(pico_current)))
        margin = 0.04 * max(upper - lower, 0.1)
        domain = np.linspace(lower - margin, upper + margin, 200)
        axes[1].plot(domain, domain, linestyle="--", linewidth=0.8, label="Identity")
        all_fit = next((row for row in regression_rows if row.get("region") == "all"), None)
        if all_fit is not None:
            gain = float(all_fit["gain"])
            offset = float(all_fit["offset_a"])
            axes[1].plot(
                domain,
                gain * domain + offset,
                linewidth=1.0,
                label=f"Diagnostic fit: {gain:.4f}·I + {1000*offset:.1f} mA",
            )
        axes[1].axvspan(0.0, threshold, alpha=0.08)
        axes[1].set_xlim(domain[0], domain[-1])
        axes[1].set_ylim(domain[0], domain[-1])
        axes[1].set_xlabel("Tektronix segment-mean current (A)")
        axes[1].set_ylabel("PicoScope segment-mean current (A)")
        axes[1].set_title("(b) Residual gain/offset diagnostic", fontsize=8.3)
        axes[1].grid(True, linewidth=0.35, alpha=0.45)
        axes[1].legend(fontsize=6.0, loc="best")
        fig.suptitle(
            f"{context['workload']} paired current-path validation",
            fontsize=8.8,
        )
        fig.text(
            0.5,
            0.006,
            "All short segments are retained. The affine fit is diagnostic only and is not applied as a calibration.",
            ha="center",
            va="bottom",
            fontsize=6.2,
        )
        fig.tight_layout(pad=0.6, w_pad=1.0, rect=(0.0, 0.05, 1.0, 0.94))
        _save_figure(fig, figures, "scope_validation_time_domain_paper", dpi=240)

        # Additional absolute-error figure for low-power accelerators.
        fig, ax = plt.subplots(figsize=(8.25, 3.0))
        current_scatter = ax.scatter(
            tek_current,
            current_delta_ma,
            c=rates,
            norm=norm,
            cmap="viridis",
            s=22,
            alpha=0.82,
            edgecolors="none",
        )
        ax.axvspan(0.0, threshold, alpha=0.08, label="Low-current region")
        ax.axhline(0.0, linewidth=0.8)
        ax.set_xlabel("Tektronix segment-mean current (A)")
        ax.set_ylabel("Current difference, Pico - Tek (mA)")
        ax.set_title(
            f"{context['workload']}: absolute current-path difference across operating points",
            fontsize=8.5,
        )
        ax.grid(True, linewidth=0.35, alpha=0.45)
        ax.legend(fontsize=6.3)
        current_cbar = fig.colorbar(current_scatter, ax=ax, pad=0.02)
        current_cbar.set_label("Tektronix sampling rate (S/s)", fontsize=6.5)
        current_cbar.ax.tick_params(labelsize=6)
        fig.tight_layout(pad=0.6)
        _save_figure(fig, figures, "scope_validation_absolute_current_error_paper", dpi=240)

    # ------------------------------------------------------------------
    # Tables for time-domain validation and operating-point effects.
    # ------------------------------------------------------------------
    table_rows: list[list[str]] = []
    for row in rows:
        duration = float(row.get("common_nominal_duration_s_median", float("nan")))
        selected_corr = float(row.get("selected_correlation_median", float("nan")))
        selected_window = float(row.get("selected_correlation_window_ms_median", float("nan")))
        table_rows.append(
            [
                _fmt_rate(float(row.get("tek_rate_sps", row["rate_sps"]))),
                _fmt_rate(float(row.get("pico_rate_sps", row["rate_sps"]))),
                f"{duration:.6g}~s",
                str(int(float(row["n_pairs"]))),
                str(int(float(row.get("low_current_n_pairs", 0)))),
                _fmt_optional(
                    row.get("raw_pico_vs_tek_energy_error_pct_median"),
                    "+.3f",
                    "\\%",
                ),
                _fmt_optional(
                    row.get("raw_abs_energy_error_q95_pct"),
                    ".3f",
                    "\\%",
                ),
                _fmt_optional(
                    row.get("pico_vs_tek_energy_error_pct_median"),
                    "+.3f",
                    "\\%",
                ),
                _fmt_optional(
                    row.get("nominal_current_abs_energy_error_q95_pct"),
                    ".3f",
                    "\\%",
                ),
                _fmt_optional(
                    row.get("zero_offset_applied_ma_median"),
                    "+.2f",
                    "~mA",
                ),
                _fmt_optional(
                    row.get("mean_current_difference_ma_median"),
                    "+.2f",
                    "~mA",
                ),
                (
                    f"{selected_corr:.5f} ({selected_window:g}~ms)"
                    if np.isfinite(selected_corr)
                    else "n/a"
                ),
            ]
        )
    _write_table_triplet(
        tables,
        "table_scope_validation_by_rate",
        caption=(
            f"Trigger-matched {context['workload']} Tektronix/PicoScope validation. "
            "Raw calibrated results are retained beside the selected comparison. "
            "When the adaptive zero-offset audit passes, the selected columns use "
            "the additive-corrected Tektronix trace and are a documented post-hoc "
            "salvage result, not an independent absolute PicoScope validation. "
            "No gain correction is applied."
        ),
        label="tab:scope-validation",
        environment="tabular_resize",
        column_spec="@{}rrrrrrrrrrrr@{}",
        headers=[
            "Tek rate",
            "Pico rate",
            "Duration",
            "Pairs",
            "Low-I",
            "Raw median $\\Delta E$",
            "Raw q95",
            "Selected median $\\Delta E$",
            "Selected nominal q95",
            "Tek zero corr.",
            "Selected median $\\Delta I$",
            "Selected corr.",
        ],
        rows=table_rows,
    )

    # ------------------------------------------------------------------
    # Idle/DC-baseline diagnostics.  Raw full-record results remain canonical;
    # idle-subtracted active-window metrics are shown only to diagnose whether
    # a stable baseline mismatch dominates a low-duty-cycle workload.
    # ------------------------------------------------------------------
    external_overview_path = (
        scope_output_root / "external_idle" / "external_idle_overview.csv"
    )
    external_overview_rows = (
        read_csv(external_overview_path)
        if external_overview_path.is_file()
        else []
    )
    external_by_rate = {
        int(float(row["rate_sps"])): row
        for row in external_overview_rows
        if row.get("rate_sps") not in (None, "")
    }
    baseline_table_rows: list[list[str]] = []
    raw_q95_values: list[float] = []
    selected_q95_values: list[float] = []
    active_q95_values: list[float] = []
    incremental_q95_values: list[float] = []
    selected_idle_delta_values: list[float] = []
    same_run_idle_delta_values: list[float] = []
    external_idle_delta_values: list[float] = []
    baseline_rates: list[float] = []
    for row in rows:
        rate = int(float(row["rate_sps"]))
        external_row = external_by_rate.get(rate, {})
        raw_q95 = _first_finite_dict(row, "raw_abs_energy_error_q95_pct")
        selected_q95 = _first_finite_dict(row, "abs_energy_error_q95_pct")
        active_q95 = _first_finite_dict(
            row, "active_window_abs_energy_error_q95_pct"
        )
        incremental_q95 = _first_finite_dict(
            row, "incremental_abs_energy_error_q95_pct"
        )
        selected_idle_delta = _first_finite_dict(
            row, "idle_baseline_current_difference_ma_median"
        )
        same_run_idle_delta = _first_finite_dict(
            row, "same_run_idle_current_difference_ma_median"
        )
        external_idle_delta = _first_finite_dict(
            external_row,
            "idle_current_difference_ma_median",
        )
        external_pairs = int(float(external_row.get("valid_pairs", 0) or 0))
        external_status = str(external_row.get("status", "unavailable"))
        baseline_sources = str(row.get("idle_baseline_source_counts", "none"))
        mismatch_fraction = _first_finite_dict(
            row, "idle_baseline_mismatch_fraction"
        )
        baseline_table_rows.append(
            [
                _fmt_rate(float(row.get("tek_rate_sps", rate))),
                _fmt_rate(float(row.get("pico_rate_sps", rate))),
                baseline_sources.replace("_", " "),
                (
                    f"{external_pairs} ({external_status.replace('_', ' ')})"
                    if external_pairs or external_status != "unavailable"
                    else "n/a"
                ),
                _fmt_optional(selected_idle_delta, "+.2f", "~mA"),
                _fmt_optional(external_idle_delta, "+.2f", "~mA"),
                _fmt_optional(raw_q95, ".3f", "\\%"),
                _fmt_optional(selected_q95, ".3f", "\\%"),
                _fmt_optional(active_q95, ".3f", "\\%"),
                _fmt_optional(incremental_q95, ".3f", "\\%"),
                (
                    f"{100.0*mismatch_fraction:.1f}\\%"
                    if np.isfinite(mismatch_fraction)
                    else "n/a"
                ),
            ]
        )
        baseline_rates.append(float(row.get("tek_rate_sps", rate)))
        raw_q95_values.append(raw_q95)
        selected_q95_values.append(selected_q95)
        active_q95_values.append(active_q95)
        incremental_q95_values.append(incremental_q95)
        selected_idle_delta_values.append(selected_idle_delta)
        same_run_idle_delta_values.append(same_run_idle_delta)
        external_idle_delta_values.append(external_idle_delta)

    if baseline_table_rows:
        _write_table_triplet(
            tables,
            "table_scope_idle_baseline_by_rate",
            caption=(
                f"{context['workload']} idle/DC-baseline diagnostics. Raw full-record "
                "energy differences remain archived beside any separately marked "
                "adaptive additive zero-offset correction. "
                "Active-window and idle-subtracted incremental results are additional "
                "diagnostics only. Same-run pre-benchmark idle is preferred; an "
                "independent exact-rate idle median is used only when same-run idle is "
                "unavailable and is otherwise reported as a cross-check."
            ),
            label="tab:scope-idle-baseline",
            environment="tabular_resize",
            column_spec="@{}rrllrrrrrrr@{}",
            headers=[
                "Tek rate",
                "Pico rate",
                "Selected idle source",
                "External idle pairs",
                "Selected $\\Delta I_{idle}$",
                "External $\\Delta I_{idle}$",
                "Raw q95 $|\\Delta E|$",
                "Selected q95",
                "Active q95",
                "Incremental q95",
                "Mismatch pairs",
            ],
            rows=baseline_table_rows,
        )

        fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.15))
        rate_array = np.asarray(baseline_rates, dtype=np.float64)

        def _plot_q95(values, *, marker, label):
            array = np.asarray(values, dtype=np.float64)
            valid = np.isfinite(rate_array) & np.isfinite(array)
            if not np.any(valid):
                return False
            order = np.argsort(rate_array[valid])
            axes[0].plot(
                rate_array[valid][order],
                array[valid][order],
                marker=marker,
                linewidth=0.95,
                label=label,
            )
            return True

        _plot_q95(raw_q95_values, marker="o", label="Raw full record")
        _plot_q95(selected_q95_values, marker="D", label="Selected after zero audit")
        _plot_q95(active_q95_values, marker="s", label="Detected active window")
        _plot_q95(
            incremental_q95_values,
            marker="^",
            label="Idle-subtracted incremental",
        )
        axes[0].axhline(1.0, linestyle="--", linewidth=0.75, label="1% criterion")
        axes[0].set_xscale("log")
        axes[0].set_yscale("log")
        axes[0].set_xlabel("Tektronix sampling rate (S/s)")
        axes[0].set_ylabel("q95 absolute estimated-energy difference (%)")
        axes[0].set_title("(a) Raw versus baseline-aware diagnostics", fontsize=8.0)
        axes[0].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[0].legend(fontsize=5.8, loc="best")

        def _plot_idle(values, *, marker, label, linestyle="-"):
            array = np.asarray(values, dtype=np.float64)
            valid = np.isfinite(rate_array) & np.isfinite(array)
            if not np.any(valid):
                return False
            order = np.argsort(rate_array[valid])
            axes[1].plot(
                rate_array[valid][order],
                array[valid][order],
                marker=marker,
                linestyle=linestyle,
                linewidth=0.95,
                label=label,
            )
            return True

        idle_plotted = _plot_idle(
            selected_idle_delta_values,
            marker="o",
            label="Selected baseline",
        )
        idle_plotted = _plot_idle(
            same_run_idle_delta_values,
            marker="s",
            label="Same-run pre-benchmark",
        ) or idle_plotted
        idle_plotted = _plot_idle(
            external_idle_delta_values,
            marker="^",
            label="Independent exact-rate idle",
            linestyle="--",
        ) or idle_plotted
        axes[1].axhline(0.0, linewidth=0.75)
        axes[1].set_xscale("log")
        axes[1].set_xlabel("Tektronix sampling rate (S/s)")
        axes[1].set_ylabel("Idle-current difference, Pico - Tek (mA)")
        axes[1].set_title("(b) DC-baseline agreement", fontsize=8.0)
        axes[1].grid(True, which="both", linewidth=0.35, alpha=0.45)
        if idle_plotted:
            axes[1].legend(fontsize=5.8, loc="best")
        else:
            axes[1].text(
                0.5,
                0.5,
                "No finite idle-baseline comparison available",
                transform=axes[1].transAxes,
                ha="center",
                va="center",
                fontsize=6.8,
            )
        fig.suptitle(
            f"{context['workload']} baseline and adaptive zero-offset diagnostics",
            fontsize=8.7,
        )
        fig.tight_layout(pad=0.62, w_pad=1.0, rect=(0.0, 0.0, 1.0, 0.94))
        _save_figure(
            fig,
            figures,
            "scope_validation_idle_baseline_paper",
            dpi=240,
        )

    # ------------------------------------------------------------------
    # Adaptive additive zero-offset audit.  The estimate follows the configured
    # rate-wise evidence model.  A correction is applied to the Tek
    # trace only after all materiality, safety, within-rate and cross-rate
    # stability checks pass.  Raw metrics remain visible beside the selected
    # corrected salvage result.
    # ------------------------------------------------------------------
    zero_status = str(zero_model.get("status", "unavailable"))
    zero_detected = bool(zero_model.get("offset_detected", False))
    zero_applied = bool(zero_model.get("correction_applied", False))
    zero_estimate_ma = _optional_float(zero_model.get("offset_estimate_ma"))
    zero_applied_ma = _optional_float(zero_model.get("offset_applied_ma"))
    zero_uncertainty_ma = _optional_float(zero_model.get("offset_uncertainty_ma"))
    zero_rates = zero_model.get("reference_rates_sps", [])
    zero_rate_label = ", ".join(_fmt_rate(float(value)) for value in zero_rates) or "n/a"
    zero_summary_rows = [[
        zero_status.replace("_", " "),
        "yes" if zero_detected else "no",
        "yes" if zero_applied else "no",
        str(zero_model.get("target_source", "n/a")),
        _fmt_optional(zero_estimate_ma, "+.3f", "~mA"),
        _fmt_optional(zero_applied_ma, "+.3f", "~mA"),
        _fmt_optional(zero_uncertainty_ma, ".3f", "~mA"),
        str(zero_model.get("confidence", "none")),
        zero_rate_label,
        str(int(zero_model.get("reference_pair_count", 0) or 0)),
        "yes" if bool(zero_model.get("independent_reference", False)) else "no",
    ]]
    _write_table_triplet(
        tables,
        "table_scope_zero_offset_correction",
        caption=(
            f"Adaptive additive zero-offset audit for {context['workload']}. "
            "The session estimate is the median of eligible rate-wise evidence "
            "from the configured adaptive model. A correction is applied only "
            "after all configured materiality, magnitude, within-rate, cross-rate "
            "and sign-consistency checks pass. Raw results remain archived. "
            "Because the PicoScope setup participates in the estimate, an applied "
            "correction is a post-hoc salvage result and not an independent "
            "absolute PicoScope validation. No gain correction is fitted or applied."
        ),
        label="tab:scope-zero-offset",
        environment="tabular_resize",
        column_spec="@{}lrrlrrrllrr@{}",
        headers=[
            "Status",
            "Detected",
            "Applied",
            "Target",
            "Estimate",
            "Applied offset",
            "Uncertainty",
            "Confidence",
            "Reference rates",
            "Pairs",
            "Independent",
        ],
        rows=zero_summary_rows,
    )

    fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.15))
    evidence_rates: list[float] = []
    evidence_medians: list[float] = []
    evidence_low: list[float] = []
    evidence_high: list[float] = []
    evidence_eligible: list[bool] = []
    for evidence_row in zero_rate_rows:
        rate_value = _optional_float(evidence_row.get("rate_sps"))
        median_value = _optional_float(evidence_row.get("offset_median_ma"))
        q05_value = _optional_float(evidence_row.get("offset_q05_ma"))
        q95_value = _optional_float(evidence_row.get("offset_q95_ma"))
        if not (np.isfinite(rate_value) and np.isfinite(median_value)):
            continue
        evidence_rates.append(rate_value)
        evidence_medians.append(median_value)
        evidence_low.append(q05_value)
        evidence_high.append(q95_value)
        evidence_eligible.append(
            str(evidence_row.get("eligible_for_session_model", "")).lower()
            in {"true", "1", "yes"}
        )
    if evidence_rates:
        rate_array = np.asarray(evidence_rates, dtype=np.float64)
        median_array = np.asarray(evidence_medians, dtype=np.float64)
        low_array = np.asarray(evidence_low, dtype=np.float64)
        high_array = np.asarray(evidence_high, dtype=np.float64)
        lower_error = np.where(
            np.isfinite(low_array), np.maximum(0.0, median_array - low_array), 0.0
        )
        upper_error = np.where(
            np.isfinite(high_array), np.maximum(0.0, high_array - median_array), 0.0
        )
        eligible_array = np.asarray(evidence_eligible, dtype=bool)
        for eligible_value, marker_value, label_value in (
            (True, "o", "Eligible rate evidence"),
            (False, "x", "Rejected rate"),
        ):
            mask = eligible_array == eligible_value
            if not np.any(mask):
                continue
            axes[0].errorbar(
                rate_array[mask],
                median_array[mask],
                yerr=np.vstack([lower_error[mask], upper_error[mask]]),
                fmt=marker_value,
                capsize=2.5,
                linewidth=0.8,
                label=label_value,
            )
        if np.isfinite(zero_estimate_ma):
            axes[0].axhline(
                zero_estimate_ma,
                linewidth=1.0,
                label=f"Session estimate {zero_estimate_ma:+.2f} mA",
            )
        axes[0].set_xscale("log")
        axes[0].set_xlabel("Sampling rate (S/s)")
        axes[0].set_ylabel("Estimated Tek session shift (mA)")
        axes[0].set_title("(a) Rate-wise adaptive offset evidence", fontsize=7.8)
        axes[0].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[0].legend(fontsize=5.8, loc="best")
    else:
        axes[0].text(
            0.5,
            0.5,
            f"No eligible adaptive offset evidence\nstatus: {zero_status}",
            transform=axes[0].transAxes,
            ha="center",
            va="center",
            fontsize=7.0,
        )
        axes[0].set_axis_off()

    workload_rates = np.asarray(
        [float(row.get("tek_rate_sps", row["rate_sps"])) for row in rows],
        dtype=np.float64,
    )
    raw_energy_median = np.asarray(
        [
            _optional_float(row.get("raw_pico_vs_tek_energy_error_pct_median"))
            for row in rows
        ],
        dtype=np.float64,
    )
    selected_energy_median = np.asarray(
        [
            _optional_float(row.get("pico_vs_tek_energy_error_pct_median"))
            for row in rows
        ],
        dtype=np.float64,
    )
    valid_raw = np.isfinite(workload_rates) & np.isfinite(raw_energy_median)
    valid_selected = np.isfinite(workload_rates) & np.isfinite(selected_energy_median)
    if np.any(valid_raw):
        order = np.argsort(workload_rates[valid_raw])
        axes[1].plot(
            workload_rates[valid_raw][order],
            raw_energy_median[valid_raw][order],
            marker="o",
            linewidth=0.95,
            label="Raw calibrated",
        )
    if np.any(valid_selected):
        order = np.argsort(workload_rates[valid_selected])
        axes[1].plot(
            workload_rates[valid_selected][order],
            selected_energy_median[valid_selected][order],
            marker="s",
            linewidth=0.95,
            label="Selected after zero audit",
        )
    axes[1].axhline(0.0, linewidth=0.75)
    axes[1].axhline(1.0, linestyle="--", linewidth=0.7, label="±1%")
    axes[1].axhline(-1.0, linestyle="--", linewidth=0.7)
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Tektronix sampling rate (S/s)")
    axes[1].set_ylabel("Median $\\Delta E$, Pico - Tek (\\%)")
    axes[1].set_title("(b) Raw values remain visible beside corrected salvage", fontsize=7.8)
    axes[1].grid(True, which="both", linewidth=0.35, alpha=0.45)
    axes[1].legend(fontsize=5.8, loc="best")
    fig.suptitle(
        f"{context['workload']} adaptive Tektronix zero-offset audit: {zero_status.replace('_', ' ')}",
        fontsize=8.5,
    )
    fig.text(
        0.5,
        0.006,
        "Only a constant additive offset may be applied; gain fitting remains diagnostic only.",
        ha="center",
        va="bottom",
        fontsize=6.1,
    )
    fig.tight_layout(pad=0.62, w_pad=0.9, rect=(0.0, 0.045, 1.0, 0.93))
    _save_figure(
        fig,
        figures,
        "scope_validation_zero_offset_correction_paper",
        dpi=240,
    )
    if not zero_artifact_available:
        for suffix in (".pdf", ".png"):
            (figures / f"scope_validation_zero_offset_correction_paper{suffix}").unlink(
                missing_ok=True
            )
        for suffix in (".tex", ".csv", ".md"):
            (tables / f"table_scope_zero_offset_correction{suffix}").unlink(
                missing_ok=True
            )

    if regression_rows:
        regression_table_rows: list[list[str]] = []
        region_labels = {
            "all": "all",
            "nominal_current": "nominal current",
            "low_current": "low current",
        }
        for row in regression_rows:
            regression_table_rows.append(
                [
                    region_labels.get(str(row.get("region", "")), str(row.get("region", "")).replace("_", " ")),
                    str(int(float(row.get("n_pairs", 0)))),
                    f"{float(row.get('gain', float('nan'))):.6f}",
                    f"{float(row.get('offset_ma', float('nan'))):+.3f}~mA",
                    f"{float(row.get('r2', float('nan'))):.6f}",
                    "diagnostic only",
                ]
            )
        _write_table_triplet(
            tables,
            "table_scope_operating_point_regression",
            caption=(
                f"Diagnostic affine fits for {context['workload']} between segment-mean PicoScope and "
                "Tektronix currents. The fits describe residual gain/offset "
                "behaviour and are not applied as a calibration correction."
            ),
            label="tab:scope-operating-point-regression",
            environment="tabular",
            column_spec="@{}lrrrrl@{}",
            headers=["Region", "Pairs", "Gain", "Offset", "$R^2$", "Use"],
            rows=regression_table_rows,
        )

    # ------------------------------------------------------------------
    # Tektronix-primary PSD reference.
    # ------------------------------------------------------------------
    tek_selection_path = scope_output_root / "tek_reference" / "selection.json"
    tek_selection = read_json(tek_selection_path) if tek_selection_path.is_file() else {}
    if tek_selection.get("status") == "selected":
        tek_npz = scope_output_root / "tek_reference" / "tek_primary_psd_summary.npz"
        _require_files([tek_npz])
        data = np.load(tek_npz)
        f = np.asarray(data["tek_native_frequencies_hz"], dtype=np.float64)
        active = np.asarray(data["tek_native_active_psd_w2_per_hz_median"], dtype=np.float64)
        idle = np.asarray(data["tek_native_idle_psd_w2_per_hz_median"], dtype=np.float64)
        analysis = np.asarray(data["tek_native_analysis_psd_w2_per_hz_median"], dtype=np.float64)
        cumulative = np.asarray(data["tek_native_analysis_cumulative_median"], dtype=np.float64)
        display_idx = _spectral_display_indices(f.size)
        display_mask = f[display_idx] >= 1.0
        plot_idx = display_idx[display_mask]
        (active_db, idle_db), psd_ylim = _psd_db_curves(active, idle)
        fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.15))
        axes[0].plot(
            f[plot_idx],
            active_db[plot_idx],
            linewidth=0.85,
            label=f"{context['workload']} active",
        )
        axes[0].plot(
            f[plot_idx],
            idle_db[plot_idx],
            linewidth=0.85,
            label=f"Idle before {context['workload']}",
        )
        axes[0].set_xscale("log")
        axes[0].set_ylim(*psd_ylim)
        axes[0].set_xlabel("Frequency (Hz)")
        axes[0].set_ylabel(r"PSD (dB W$^2$/Hz)")
        axes[0].set_title(
            f"(a) Native Tektronix PSD at "
            f"{_fmt_rate(float(tek_selection['selected_tek_rate_sps']))}",
            fontsize=8.3,
        )
        axes[0].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[0].legend(fontsize=6.3, loc="upper right")

        axes[1].plot(
            f[plot_idx],
            100.0 * cumulative[plot_idx],
            linewidth=0.95,
            label="Tek active - idle",
        )
        f95 = float(tek_selection.get("f95_hz", float("nan")))
        f99 = float(tek_selection.get("f99_hz", float("nan")))
        f95_q05 = float(tek_selection.get("f95_hz_q05", float("nan")))
        f95_q95 = float(tek_selection.get("f95_hz_q95", float("nan")))
        f99_q05 = float(tek_selection.get("f99_hz_q05", float("nan")))
        f99_q95 = float(tek_selection.get("f99_hz_q95", float("nan")))
        axes[1].axvline(77_000.0, linestyle="--", linewidth=0.8, label="INA225 path: 77 kHz")
        if np.isfinite(f95_q05) and np.isfinite(f95_q95):
            axes[1].axvspan(f95_q05, f95_q95, alpha=0.10)
        if np.isfinite(f99_q05) and np.isfinite(f99_q95):
            axes[1].axvspan(f99_q05, f99_q95, alpha=0.10)
        axes[1].axvline(f95, linestyle=":", linewidth=0.9, label=f"per-run median f95={_fmt_frequency(f95)}")
        axes[1].axvline(f99, linestyle="-.", linewidth=0.9, label=f"per-run median f99={_fmt_frequency(f99)}")
        axes[1].axhline(95.0, linestyle=":", linewidth=0.6)
        axes[1].axhline(99.0, linestyle="-.", linewidth=0.6)
        axes[1].set_xscale("log")
        axes[1].set_ylim(0.0, 101.0)
        axes[1].set_xlabel("Frequency (Hz)")
        axes[1].set_ylabel("Cumulative variance (%)")
        axes[1].set_title(
            "(b) Workload-related active-minus-idle variance",
            fontsize=8.0,
        )
        axes[1].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[1].legend(fontsize=5.9, loc="lower right")
        fig.suptitle(
            f"{context['workload']} estimated power from the Tektronix current probe",
            fontsize=8.8,
        )
        fig.tight_layout(pad=0.62, w_pad=1.0, rect=(0.0, 0.0, 1.0, 0.94))
        _save_figure(fig, figures, "scope_validation_tek_reference_psd_paper", dpi=240)

        tek_table_rows = [[
            _fmt_rate(float(tek_selection["selected_tek_rate_sps"])),
            str(int(tek_selection["selected_n_pairs"])),
            _fmt_frequency(float(tek_selection["nyquist_hz"])),
            f"{_fmt_frequency(f95)} [{_fmt_frequency(f95_q05)}--{_fmt_frequency(f95_q95)}]",
            f"{_fmt_frequency(f99)} [{_fmt_frequency(f99_q05)}--{_fmt_frequency(f99_q95)}]",
            f"{100*float(tek_selection['variance_above_77khz']):.3f}\\% "
            f"[{100*float(tek_selection.get('variance_above_77khz_q05', float('nan'))):.3f}--"
            f"{100*float(tek_selection.get('variance_above_77khz_q95', float('nan'))):.3f}\\%]",
            f"{100*float(tek_selection['variance_above_pico_nyquist']):.4f}\\%",
        ]]
        _write_table_triplet(
            tables,
            "table_scope_tek_reference_psd",
            caption=(
                f"Primary Tektronix-native {context['workload']} estimated-power PSD reference selected as the highest "
                "rate with a valid pre-benchmark idle window, at least two seconds "
                "of active data, and sufficient Welch averaging. Frequency and "
                "77-kHz variance values are medians with 5th--95th percentiles "
                "across physical runs; the figure uses the pointwise median PSD."
            ),
            label="tab:scope-tek-reference",
            environment="tabular_resize",
            column_spec="@{}rrrrrrr@{}",
            headers=["Tek rate", "Pairs", "$f_N$", "$f_{95}$", "$f_{99}$", "Var. $>$77 kHz", "Var. $>$Pico $f_N$"],
            rows=tek_table_rows,
        )

    # ------------------------------------------------------------------
    # PicoScope usability relative to the Tek reference in the common band.
    # ------------------------------------------------------------------
    pico_selection_path = scope_output_root / "pico_usability" / "selection.json"
    pico_selection = read_json(pico_selection_path) if pico_selection_path.is_file() else {}
    pico_metrics_path = scope_output_root / "pico_usability" / "pico_usability.json"
    pico_metrics = read_json(pico_metrics_path) if pico_metrics_path.is_file() else {}
    selected_pico_cross_row: dict[str, str] | None = None
    if pico_selection.get("status") == "selected":
        selected_common_rate = float(pico_selection.get("selected_common_rate_sps", pico_selection.get("selected_rate_sps", float("nan"))))
        if np.isfinite(selected_common_rate):
            selected_pico_cross_row = min(
                rows,
                key=lambda row: abs(float(row.get("common_comparison_rate_sps", row.get("rate_sps", "nan"))) - selected_common_rate),
            )
        selected_rate = int(pico_selection["selected_rate_sps"])
        path = scope_output_root / f"{selected_rate}Sps" / "psd" / "psd_summary.npz"
        _require_files([path])
        data = np.load(path)
        f = np.asarray(data["frequencies_hz"], dtype=np.float64)
        tek_psd = np.asarray(data["tek_analysis_psd_w2_per_hz_median"], dtype=np.float64)
        pico_psd = np.asarray(data["pico_analysis_psd_w2_per_hz_median"], dtype=np.float64)
        coherence = np.asarray(data["coherence_median"], dtype=np.float64)
        ratio = np.asarray(data["analysis_psd_ratio_db_median"], dtype=np.float64)
        display_idx = _spectral_display_indices(f.size)
        display_mask = f[display_idx] >= 1.0
        plot_idx = display_idx[display_mask]
        mask = f >= 1.0
        (tek_db, pico_db), psd_ylim = _psd_db_curves(tek_psd, pico_psd)
        fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.15))
        axes[0].plot(
            f[plot_idx],
            tek_db[plot_idx],
            linewidth=0.85,
            label="Tektronix current-probe estimate",
        )
        axes[0].plot(
            f[plot_idx],
            pico_db[plot_idx],
            linewidth=0.85,
            label="PicoScope/INA225 estimate",
        )
        axes[0].axvline(77_000.0, linestyle="--", linewidth=0.8, label="INA225: 77 kHz")
        axes[0].set_xscale("log")
        axes[0].set_ylim(*psd_ylim)
        axes[0].set_xlabel("Frequency (Hz)")
        axes[0].set_ylabel(r"PSD (dB W$^2$/Hz)")
        axes[0].set_title(
            "(a) Common-band active-minus-idle PSD",
            fontsize=8.1,
        )
        axes[0].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[0].legend(fontsize=6.0)

        # Coherence and PSD ratios are meaningful only where both instruments
        # carry displayed signal content.  Mask low-signal/zero excess bins so
        # the full-band plot cannot be dominated by numerical ratios of noise
        # floors after the common signal has vanished.
        common_signal = mask & np.isfinite(tek_db) & np.isfinite(pico_db)
        selected_for_display = np.zeros(f.shape, dtype=bool)
        selected_for_display[display_idx] = True
        finite_coh = common_signal & selected_for_display & np.isfinite(coherence)
        finite_ratio = common_signal & selected_for_display & np.isfinite(ratio)
        validated_edge = _optional_float(
            pico_metrics.get("validated_contiguous_band_edge_hz")
        )
        if not np.isfinite(validated_edge):
            validated_edge = _optional_float(
                pico_metrics.get("highest_fixed_band_edge_meeting_agreement_hz")
            )
        if np.isfinite(validated_edge):
            axes[1].axvspan(
                max(1.0, float(np.min(f[mask]))),
                validated_edge,
                alpha=0.08,
                label="Predefined bands meeting criteria",
            )
        if np.any(finite_coh):
            axes[1].plot(f[finite_coh], coherence[finite_coh], linewidth=0.85, label="Coherence")
        coherence_threshold = _optional_float(
            pico_metrics.get("coherence_threshold")
        )
        if np.isfinite(coherence_threshold):
            axes[1].axhline(
                coherence_threshold,
                linestyle=":",
                linewidth=0.7,
                label="Coherence criterion",
            )
        axes[1].set_xscale("log")
        axes[1].set_ylim(-0.02, 1.02)
        axes[1].set_xlabel("Frequency (Hz)")
        axes[1].set_ylabel("Magnitude-squared coherence")
        axr = axes[1].twinx()
        if np.any(finite_ratio):
            axr.plot(f[finite_ratio], ratio[finite_ratio], linestyle="--", linewidth=0.75, label="Pico/Tek PSD ratio")
        ratio_tolerance = _optional_float(
            pico_metrics.get("psd_ratio_tolerance_db"), 3.0
        )
        axr.axhline(ratio_tolerance, linestyle=":", linewidth=0.6)
        axr.axhline(-ratio_tolerance, linestyle=":", linewidth=0.6)
        axr.set_ylabel("PSD ratio (dB)")
        if np.any(finite_ratio):
            ratio_values = ratio[finite_ratio]
            low, high = np.quantile(ratio_values, [0.01, 0.99])
            margin = max(1.0, 0.1 * (high - low))
            axr.set_ylim(max(-30.0, low - margin), min(30.0, high + margin))
        axes[1].set_title("(b) Agreement in the common frequency band", fontsize=8.0)
        axes[1].grid(True, which="both", linewidth=0.35, alpha=0.45)
        h1, l1 = axes[1].get_legend_handles_labels()
        h2, l2 = axr.get_legend_handles_labels()
        axes[1].legend(h1+h2, l1+l2, fontsize=5.75, loc="lower left")
        validated_coherence = _optional_float(
            pico_metrics.get("validated_contiguous_band_coherence_min")
        )
        validated_ratio = _optional_float(
            pico_metrics.get("validated_contiguous_band_abs_psd_ratio_db_max")
        )
        low_band_coherence = _optional_float(
            pico_metrics.get("paired_bandwise_coherence_0_10khz_median"),
            validated_coherence,
        )
        low_band_ratio = _optional_float(
            pico_metrics.get("paired_bandwise_abs_psd_ratio_db_0_10khz_median"),
            validated_ratio,
        )
        fig.suptitle(
            f"{context['workload']} estimated-power path comparison at "
            f"{_fmt_rate(float(pico_selection['selected_common_rate_sps']))}",
            fontsize=8.8,
        )
        fig.tight_layout(pad=0.62, w_pad=1.0, rect=(0.0, 0.0, 1.0, 0.94))
        _save_figure(fig, figures, "scope_validation_pico_usability_paper", dpi=240)

        if pico_metrics.get("status") == "selected":
            usability_rows = [[
                _fmt_rate(float(pico_metrics["paired_tek_rate_sps"])),
                _fmt_rate(float(pico_metrics["paired_pico_rate_sps"])),
                _fmt_frequency(float(pico_metrics["paired_common_nyquist_hz"])),
                _fmt_frequency(_first_finite_dict(
                    selected_pico_cross_row or {},
                    "spectral_tek_analysis_f95_hz_median",
                    "spectral_tek_f95_hz_median",
                )),
                _fmt_frequency(_first_finite_dict(
                    selected_pico_cross_row or {},
                    "spectral_pico_analysis_f95_hz_median",
                    "spectral_pico_f95_hz_median",
                )),
                _fmt_optional(pico_metrics.get("paired_pico_to_tek_integrated_psd_ratio_db"), "+.3f", "~dB"),
                _fmt_optional(
                    pico_metrics.get(
                        "paired_bandwise_coherence_0_10khz_median",
                        pico_metrics.get("validated_contiguous_band_coherence_min"),
                    ),
                    ".4f",
                ),
                _fmt_optional(
                    pico_metrics.get(
                        "paired_bandwise_abs_psd_ratio_db_0_10khz_median",
                        pico_metrics.get("validated_contiguous_band_abs_psd_ratio_db_max"),
                    ),
                    ".3f",
                    "~dB",
                ),
                _fmt_frequency(validated_edge),
            ]]
            _write_table_triplet(
                tables,
                "table_scope_pico_usability",
                caption=(
                    f"{context['workload']} PicoScope/INA225 usability relative to the Tektronix-primary "
                    "reference in the paired common band. The final band edge is "
                    "the highest contiguous predefined band from DC satisfying "
                    "the configured coherence and PSD-ratio criteria; it is not an analogue "
                    "-3 dB bandwidth estimate. Bandwise agreement is reported for 0--10 kHz "
                    "instead of a misleading full-band median. The reported f95 "
                    "values are medians of the per-run frequency metrics, matching "
                    "the Tek-reference convention."
                ),
                label="tab:scope-pico-usability",
                environment="tabular_resize",
                column_spec="@{}rrrrrrrrr@{}",
                headers=[
                    "Tek rate", "Pico rate", "Common $f_N$",
                    "Tek per-run median $f_{95}$", "Pico per-run median $f_{95}$", "PSD ratio",
                    "Median coh. 0--10 kHz", "Median $|$PSD ratio$|$ 0--10 kHz",
                    "Validated band edge",
                ],
                rows=usability_rows,
            )

    # ------------------------------------------------------------------
    # High-frequency Tek-only endpoint: explicitly active-only when no idle is
    # present.  This is not used as the primary workload-related PSD.
    # ------------------------------------------------------------------
    native_candidates: list[tuple[float, int, Path, dict[str, str]]] = []
    for row in rows:
        rate = int(float(row["rate_sps"]))
        path = scope_output_root / f"{rate}Sps" / "psd" / "tek_native_psd_summary.npz"
        if path.is_file():
            native_candidates.append((float(row.get("tek_rate_sps", rate)), rate, path, row))
    if native_candidates:
        tek_rate, rate, path, row = max(native_candidates, key=lambda item: item[0])
        data = np.load(path)
        f = np.asarray(data["tek_native_frequencies_hz"], dtype=np.float64)
        density = np.asarray(data["tek_native_analysis_psd_w2_per_hz_median"], dtype=np.float64)
        cumulative = np.asarray(data["tek_native_analysis_cumulative_median"], dtype=np.float64)
        basis_mode = str(row.get("native_tek_native_psd_basis_mode", ""))
        workload_fraction = float(
            row.get("native_tek_native_workload_related_pair_fraction", "nan")
        )
        if basis_mode:
            workload_related = "active_minus" in basis_mode or "active-idle" in basis_mode
        else:
            workload_related = (
                np.isfinite(workload_fraction) and workload_fraction >= 0.8
            )
        mask = f >= 1.0
        (density_db,), native_ylim = _psd_db_curves(density)
        fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.05))
        axes[0].plot(f[mask], density_db[mask], linewidth=0.8)
        axes[0].axvline(77_000.0, linestyle="--", linewidth=0.8, label="77 kHz")
        axes[0].axvline(float(row.get("pico_rate_sps", 5e6))/2.0, linestyle=":", linewidth=0.8, label="Pico Nyquist")
        axes[0].set_xscale("log")
        axes[0].set_ylim(*native_ylim)
        axes[0].set_xlabel("Frequency (Hz)")
        axes[0].set_ylabel(r"PSD (dB W$^2$/Hz)")
        axes[0].set_title(
            f"(a) {context['workload']}, {_fmt_rate(tek_rate)} Tek-only endpoint\n"
            + ("active - idle" if workload_related else "active-only diagnostic"),
            fontsize=8.1,
        )
        axes[0].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[0].legend(fontsize=6.0)
        axes[1].plot(f[mask], 100*cumulative[mask], linewidth=0.85)
        axes[1].axvline(77_000.0, linestyle="--", linewidth=0.8, label="77 kHz")
        axes[1].axvline(float(row.get("pico_rate_sps", 5e6))/2.0, linestyle=":", linewidth=0.8, label="Pico Nyquist")
        axes[1].set_xscale("log")
        axes[1].set_ylim(0, 101)
        axes[1].set_xlabel("Frequency (Hz)")
        axes[1].set_ylabel("Cumulative variance (%)")
        axes[1].set_title("(b) Native Tek bandwidth extension", fontsize=8.3)
        axes[1].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[1].legend(fontsize=6.0)
        fig.tight_layout(pad=0.6, w_pad=1.0)
        _save_figure(fig, figures, "scope_validation_tek_high_frequency_extension_paper", dpi=240)

    # ------------------------------------------------------------------
    # Spectral coverage table: distinguish workload-related and active-only.
    # ------------------------------------------------------------------
    coverage_rows: list[list[str]] = []
    workload_x: list[float] = []
    workload_above_pico: list[float] = []
    workload_above_77: list[float] = []
    active_x: list[float] = []
    active_above_pico: list[float] = []
    active_above_77: list[float] = []
    for row in rows:
        tek_rate = float(row.get("tek_rate_sps", row["rate_sps"]))
        pico_rate = float(row.get("pico_rate_sps", row["rate_sps"]))
        common_nyquist = float(row.get("common_comparison_nyquist_hz", min(tek_rate, pico_rate)/2.0))
        tek_native_nyquist = float(row.get("native_tek_native_nyquist_hz_median", tek_rate/2.0))
        basis_mode = str(row.get("native_tek_native_psd_basis_mode", "")).strip().lower()
        workload_fraction = float(row.get("native_tek_native_workload_related_pair_fraction", "nan"))
        if basis_mode:
            workload_related = (
                "active_minus" in basis_mode
                or "active-idle" in basis_mode
                or "prebenchmark_idle" in basis_mode
            ) and "active_only" not in basis_mode
        else:
            workload_related = np.isfinite(workload_fraction) and workload_fraction >= 0.8
        if workload_related:
            above_pico = float(
                row.get(
                    "native_workload_tek_native_analysis_variance_above_pico_nyquist_median",
                    row.get("native_tek_native_analysis_variance_above_pico_nyquist_median", "nan"),
                )
            )
            above_77 = float(
                row.get(
                    "native_workload_tek_native_analysis_variance_above_77khz_median",
                    row.get("native_tek_native_analysis_variance_above_77khz_median", "nan"),
                )
            )
            f95 = float(
                row.get(
                    "native_workload_tek_native_analysis_f95_hz_median",
                    row.get("native_tek_native_analysis_f95_hz_median", "nan"),
                )
            )
            f99 = float(
                row.get(
                    "native_workload_tek_native_analysis_f99_hz_median",
                    row.get("native_tek_native_analysis_f99_hz_median", "nan"),
                )
            )
            basis = "active-minus-idle"
            workload_f95 = _fmt_frequency(f95)
            workload_f99 = _fmt_frequency(f99)
            active_f95 = "n/a"
            active_f99 = "n/a"
            workload_x.append(tek_rate); workload_above_pico.append(above_pico); workload_above_77.append(above_77)
        else:
            above_pico = _first_finite_dict(
                row,
                "native_tek_native_active_variance_above_pico_nyquist_median",
                "native_tek_native_analysis_variance_above_pico_nyquist_median",
                "spectral_tek_native_active_variance_above_pico_nyquist_median",
            )
            above_77 = _first_finite_dict(
                row,
                "native_tek_native_active_variance_above_77khz_median",
                "native_tek_native_analysis_variance_above_77khz_median",
                "spectral_tek_native_active_variance_above_77khz_median",
            )
            f95 = _first_finite_dict(
                row,
                "native_tek_native_active_f95_hz_median",
                "native_tek_native_analysis_f95_hz_median",
                "spectral_tek_native_active_f95_hz_median",
            )
            f99 = _first_finite_dict(
                row,
                "native_tek_native_active_f99_hz_median",
                "native_tek_native_analysis_f99_hz_median",
                "spectral_tek_native_active_f99_hz_median",
            )
            basis = "active-only diagnostic"
            workload_f95 = "n/a"
            workload_f99 = "n/a"
            active_f95 = _fmt_frequency(f95)
            active_f99 = _fmt_frequency(f99)
            active_x.append(tek_rate); active_above_pico.append(above_pico); active_above_77.append(above_77)
        coverage_rows.append([
            _fmt_rate(tek_rate), _fmt_rate(pico_rate), _fmt_frequency(common_nyquist),
            _fmt_frequency(tek_native_nyquist), basis,
            f"{100*above_pico:.4f}\\%" if np.isfinite(above_pico) else "n/a",
            f"{100*above_77:.3f}\\%" if np.isfinite(above_77) else "n/a",
            workload_f95, workload_f99, active_f95, active_f99,
        ])
    _write_table_triplet(
        tables,
        "table_scope_spectral_coverage",
        caption=(
            "Tektronix-native spectral coverage. Workload-related frequency "
            "metrics require a measured pre-benchmark idle PSD and are reported "
            "only in the workload columns. Short high-rate records without idle "
            "are reported separately as active-only diagnostics; their f95/f99 "
            "values must not be interpreted as workload-related excess-PSD metrics."
        ),
        label="tab:scope-spectral-coverage",
        environment="tabular_resize",
        column_spec="@{}rrrrlrrrrrr@{}",
        headers=[
            "Tek rate", "Pico rate", "Common $f_N$", "Tek $f_N$", "Basis",
            "Var. $>$Pico $f_N$", "Var. $>$77 kHz",
            "Workload $f_{95}$", "Workload $f_{99}$",
            "Active-only $f_{95}$", "Active-only $f_{99}$",
        ],
        rows=coverage_rows,
    )

    if workload_x or active_x:
        fig, axes = plt.subplots(1, 2, figsize=(8.25, 3.05), sharey=False)

        def _plot_finite_line(axis, x_values, y_values, *, marker, label):
            x_array = np.asarray(x_values, dtype=np.float64)
            y_array = 100.0 * np.asarray(y_values, dtype=np.float64)
            valid = np.isfinite(x_array) & np.isfinite(y_array)
            if not np.any(valid):
                return False
            order = np.argsort(x_array[valid])
            axis.plot(
                x_array[valid][order],
                y_array[valid][order],
                marker=marker,
                linewidth=1.0,
                label=label,
            )
            return True

        workload_plotted = False
        if workload_x:
            workload_plotted |= _plot_finite_line(
                axes[0],
                workload_x,
                workload_above_pico,
                marker="o",
                label="Above Pico Nyquist",
            )
            workload_plotted |= _plot_finite_line(
                axes[0],
                workload_x,
                workload_above_77,
                marker="s",
                label="Above 77 kHz",
            )
        axes[0].axvline(
            5_000_000.0,
            linestyle="--",
            linewidth=0.8,
            label="Pico rate ceiling",
        )
        axes[0].set_xscale("log")
        axes[0].set_xlabel("Tektronix sampling rate (S/s)")
        axes[0].set_ylabel("Tek-native variance fraction (%)")
        axes[0].set_title("(a) Workload-related active-minus-idle", fontsize=8.0)
        axes[0].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[0].legend(fontsize=5.9, loc="best")
        if not workload_plotted:
            axes[0].text(
                0.5,
                0.5,
                "No finite active-minus-idle coverage metrics",
                transform=axes[0].transAxes,
                ha="center",
                va="center",
                fontsize=6.4,
            )

        active_plotted = False
        if active_x:
            active_array = np.asarray(active_x, dtype=np.float64)
            pico_array = 100.0 * np.asarray(active_above_pico, dtype=np.float64)
            band_array = 100.0 * np.asarray(active_above_77, dtype=np.float64)
            valid_pico = np.isfinite(active_array) & np.isfinite(pico_array)
            valid_band = np.isfinite(active_array) & np.isfinite(band_array)
            if np.any(valid_pico):
                axes[1].scatter(
                    active_array[valid_pico],
                    pico_array[valid_pico],
                    marker="o",
                    facecolors="none",
                    edgecolors="C0",
                    linewidths=1.0,
                    label="Above Pico Nyquist",
                )
                active_plotted = True
            if np.any(valid_band):
                axes[1].scatter(
                    active_array[valid_band],
                    band_array[valid_band],
                    marker="s",
                    facecolors="none",
                    edgecolors="C1",
                    linewidths=1.0,
                    label="Above 77 kHz",
                )
                active_plotted = True
            for rate_value, pico_value, band_value in zip(
                active_array, pico_array, band_array
            ):
                if np.isfinite(band_value):
                    axes[1].annotate(
                        f"{band_value:.1f}%",
                        (rate_value, band_value),
                        xytext=(3, 4),
                        textcoords="offset points",
                        fontsize=5.5,
                    )
        axes[1].axvline(
            5_000_000.0,
            linestyle="--",
            linewidth=0.8,
            label="Pico rate ceiling",
        )
        axes[1].set_xscale("log")
        axes[1].set_xlabel("Tektronix sampling rate (S/s)")
        axes[1].set_ylabel("Active-only Tek variance fraction (%)")
        finite_active_values = np.concatenate([
            np.asarray(active_above_pico, dtype=np.float64),
            np.asarray(active_above_77, dtype=np.float64),
        ]) if active_x else np.asarray([], dtype=np.float64)
        finite_active_values = 100.0 * finite_active_values[np.isfinite(finite_active_values)]
        if finite_active_values.size:
            axes[1].set_ylim(
                bottom=min(-0.5, float(np.min(finite_active_values)) - 1.0),
                top=max(5.0, 1.15 * float(np.max(finite_active_values))),
            )
        axes[1].set_title(
            "(b) High-rate Tek-only diagnostics (no idle subtraction)",
            fontsize=7.65,
        )
        axes[1].grid(True, which="both", linewidth=0.35, alpha=0.45)
        axes[1].legend(fontsize=5.9, loc="best")
        if not active_plotted:
            axes[1].text(
                0.5,
                0.5,
                "No finite active-only coverage metrics",
                transform=axes[1].transAxes,
                ha="center",
                va="center",
                fontsize=6.4,
            )
        fig.suptitle(f"{context['workload']} Tek reference bandwidth and PicoScope coverage", fontsize=8.7)
        fig.tight_layout(pad=0.62, w_pad=0.9, rect=(0.0, 0.0, 1.0, 0.94))
        _save_figure(
            fig,
            figures,
            "scope_validation_bandwidth_coverage_paper",
            dpi=240,
        )

    # ------------------------------------------------------------------
    # Macros, provenance and summary.
    # ------------------------------------------------------------------
    energy_q95 = np.asarray([float(row["abs_energy_error_q95_pct"]) for row in rows])
    nominal_q95 = np.asarray([float(row.get("nominal_current_abs_energy_error_q95_pct", "nan")) for row in rows])
    incremental_q95 = np.asarray(
        [float(row.get("incremental_abs_energy_error_q95_pct", "nan")) for row in rows]
    )
    baseline_mismatch = np.asarray(
        [float(row.get("idle_baseline_mismatch_fraction", "nan")) for row in rows]
    )
    external_idle_rate_count = sum(
        str(row.get("status", "")) == "available"
        for row in external_overview_rows
    )
    finite_incremental = incremental_q95[np.isfinite(incremental_q95)]
    finite_baseline_mismatch = baseline_mismatch[np.isfinite(baseline_mismatch)]
    macros: dict[str, float | int | str] = {
        "ScopeRateCount": len(rows),
        "ScopePairCount": len(pair_rows),
        "ScopeHighestTekRateSps": int(max(x)),
        "ScopeHighestPicoRateSps": int(max(pico_x)),
        "ScopeWorstQ95EnergyErrorPct": float(np.nanmax(energy_q95)),
        "ScopeWorstNominalQ95EnergyErrorPct": float(np.nanmax(nominal_q95)),
        "ScopeExternalIdleRateCount": int(external_idle_rate_count),
        "ScopeWorstIncrementalQ95EnergyErrorPct": (
            float(np.max(finite_incremental))
            if finite_incremental.size
            else float("nan")
        ),
        "ScopeIdleBaselineMismatchRateCount": int(
            np.sum(finite_baseline_mismatch > 0.0)
            if finite_baseline_mismatch.size
            else 0
        ),
    }
    all_regression = next(
        (row for row in regression_rows if row.get("region") == "all"),
        None,
    )
    if all_regression is not None:
        macros.update(
            {
                "ScopeDiagnosticGain": float(all_regression.get("gain", float("nan"))),
                "ScopeDiagnosticOffsetMilliampere": float(all_regression.get("offset_ma", float("nan"))),
                "ScopeDiagnosticRegressionRSquared": float(all_regression.get("r2", float("nan"))),
            }
        )
    if tek_selection.get("status") == "selected":
        macros.update({
            "ScopeTekReferenceRateSps": int(float(tek_selection["selected_tek_rate_sps"])),
            "ScopeTekReferenceF95Hz": float(tek_selection.get("f95_hz", float("nan"))),
            "ScopeTekReferenceF99Hz": float(tek_selection.get("f99_hz", float("nan"))),
            "ScopeTekReferenceF95Q05Hz": float(tek_selection.get("f95_hz_q05", float("nan"))),
            "ScopeTekReferenceF95Q95Hz": float(tek_selection.get("f95_hz_q95", float("nan"))),
            "ScopeTekReferenceF99Q05Hz": float(tek_selection.get("f99_hz_q05", float("nan"))),
            "ScopeTekReferenceF99Q95Hz": float(tek_selection.get("f99_hz_q95", float("nan"))),
            "ScopeTekVarianceAbove77kPct": 100*float(tek_selection.get("variance_above_77khz", float("nan"))),
            "ScopeTekVarianceAbove77kQ05Pct": 100*float(tek_selection.get("variance_above_77khz_q05", float("nan"))),
            "ScopeTekVarianceAbove77kQ95Pct": 100*float(tek_selection.get("variance_above_77khz_q95", float("nan"))),
            "ScopeTekVarianceAbovePicoNyquistPct": 100*float(tek_selection.get("variance_above_pico_nyquist", float("nan"))),
        })
    if pico_selection.get("status") == "selected":
        macros.update({
            "ScopePicoUsabilityRateSps": int(float(pico_selection["selected_common_rate_sps"])),
        })
    if pico_metrics.get("status") == "selected":
        validated_edge = _optional_float(
            pico_metrics.get("validated_contiguous_band_edge_hz")
        )
        if not np.isfinite(validated_edge):
            validated_edge = _optional_float(
                pico_metrics.get("highest_fixed_band_edge_meeting_agreement_hz")
            )
        macros.update({
            "ScopePicoPairedTekF95Hz": _first_finite_dict(
                selected_pico_cross_row or {},
                "spectral_tek_analysis_f95_hz_median",
                "spectral_tek_f95_hz_median",
            ),
            "ScopePicoPairedF95Hz": _first_finite_dict(
                selected_pico_cross_row or {},
                "spectral_pico_analysis_f95_hz_median",
                "spectral_pico_f95_hz_median",
            ),
            "ScopePicoIntegratedPsdRatioDb": _optional_float(pico_metrics.get("paired_pico_to_tek_integrated_psd_ratio_db")),
            "ScopePicoBandwiseCoherenceZeroToTenK": _optional_float(pico_metrics.get("paired_bandwise_coherence_0_10khz_median")),
            "ScopePicoBandwiseAbsPsdRatioZeroToTenKDb": _optional_float(pico_metrics.get("paired_bandwise_abs_psd_ratio_db_0_10khz_median")),
            "ScopePicoValidatedBandEdgeHz": validated_edge,
            "ScopePicoValidatedBandEdgeLabel": _fmt_frequency(validated_edge),
            "ScopePicoValidatedBandMinCoherence": _optional_float(pico_metrics.get("validated_contiguous_band_coherence_min")),
            "ScopePicoValidatedBandMaxAbsPsdRatioDb": _optional_float(pico_metrics.get("validated_contiguous_band_abs_psd_ratio_db_max")),
            "ScopeTekVarianceCapturedByPicoSamplingPct": 100.0 * _optional_float(pico_metrics.get("tek_reference_variance_captured_by_pico_sampling_ceiling")),
        })
    if zero_model:
        macros.update({
            "ScopeTekZeroOffsetEstimateMa": _optional_float(
                zero_model.get("offset_estimate_ma")
            ),
            "ScopeTekZeroOffsetAppliedMa": _optional_float(
                zero_model.get("offset_applied_ma")
            ),
            "ScopeTekZeroOffsetUncertaintyMa": _optional_float(
                zero_model.get("offset_uncertainty_ma")
            ),
            "ScopeTekZeroOffsetReferenceRateCount": int(
                zero_model.get("reference_rate_count", 0)
            ),
            "ScopeTekZeroOffsetReferencePairCount": int(
                zero_model.get("reference_pair_count", 0)
            ),
            "ScopeTekZeroOffsetStatusLabel": str(
                zero_model.get("status", "disabled")
            ).replace("_", " "),
            "ScopeTekZeroOffsetConfidenceLabel": str(
                zero_model.get("confidence", "none")
            ),
        })
    _write_macros(latex / "scope_results_macros.tex", macros)
    copied_scope_data = _copy_scope_key_data(scope_output_root, data_root)
    _write_scope_figure_snippets(
        latex / "scope_figure_snippets.tex", context, figures
    )
    scope_table_tex = sorted(tables.glob("*.tex"))
    _write_table_include(
        latex / "scope_table_snippets.tex",
        scope_table_tex,
        include_prefix="scope_validation/tables",
    )
    (latex / "scope_artifacts_include.tex").write_text(
        "% Auto-generated scope-validation include file.\n"
        "\\input{scope_validation/latex/scope_results_macros.tex}\n"
        "% Figure and table snippets are provided next to this file.\n",
        encoding="utf-8",
    )
    scope_input_paths = [
        path
        for path in (
            scope_output_root / "cross_rate_summary.csv",
            scope_output_root / "scope_comparison_manifest.json",
            scope_output_root / "scope_analysis_overview.json",
            scope_output_root / "diagnostics" / "operating_point_per_pair.csv",
            scope_output_root / "diagnostics" / "segment_mean_regression.csv",
            scope_output_root / "external_idle" / "external_idle_overview.csv",
            scope_output_root / "zero_correction" / "zero_offset_model.json",
            scope_output_root / "zero_correction" / "zero_offset_pair_evidence.csv",
            scope_output_root / "zero_correction" / "zero_offset_rate_evidence.csv",
            scope_output_root / "tek_reference" / "selection.json",
            scope_output_root / "tek_reference" / "tek_primary_psd_summary.npz",
            scope_output_root / "pico_usability" / "selection.json",
            scope_output_root / "pico_usability" / "pico_usability.json",
            scope_output_root / "pico_usability" / "paired_psd_summary.npz",
        )
        if path.is_file()
    ]

    manifest = {
        "schema_version": 5,
        "created_utc": utc_now_iso(),
        "tool_version": __version__,
        "scope_output_root": str(scope_output_root),
        "input_cross_rate_summary": {"path": str(cross_path), "sha256": _sha256(cross_path)},
        "tek_reference_selection": tek_selection,
        "pico_usability_selection": pico_selection,
        "pico_usability_metrics": pico_metrics,
        "package_versions": package_versions(),
        "numerical_macros": macros,
        "documentation_context": context,
        "input_files": [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in scope_input_paths
        ],
        "copied_compact_data": [
            str(path.relative_to(root)) for path in copied_scope_data
        ],
    }
    write_json(manifest_dir / "scope_paper_artifacts_manifest.json", manifest)

    summary = root / "SCOPE_PAPER_ARTIFACTS_SUMMARY.md"
    lines = [
        "# Tek-primary scope-validation paper artifacts",
        "",
        f"- Source: `{scope_output_root}`",
        f"- Tektronix rates represented: {', '.join(_fmt_rate(value) for value in x)}",
        f"- PicoScope rates represented: {', '.join(_fmt_rate(value) for value in sorted(set(pico_x)))}",
        "- Tektronix-native, idle-subtracted data are the primary PSD reference.",
        "- PicoScope results quantify current-integral, estimated-energy and common-band spectral usability relative to that reference.",
        "- Short high-rate records without idle are active-only diagnostics and do not contribute workload-related f95/f99.",
        "- Low-current segments are retained and reported separately rather than removed as outliers.",
        "- Raw full-record current/energy remain archived. A selected additive-corrected result is emitted only when the configured adaptive zero-offset safety gates pass; it is explicitly marked as a non-independent post-hoc salvage result and no gain correction is applied.",
        "- The idle-source policy follows the configured trigger geometry; record-start workloads use exact-rate external idle because no same-run pre-trigger interval exists.",
        "",
        "## Outputs",
        "",
        "- `figures/scope_validation_time_domain_paper.pdf`",
        "- `figures/scope_validation_absolute_current_error_paper.pdf`",
        "- `figures/scope_validation_idle_baseline_paper.pdf`",
        "- `figures/scope_validation_zero_offset_correction_paper.pdf` (when adaptive evidence is available)",
        "- `figures/scope_validation_tek_reference_psd_paper.pdf`",
        "- `figures/scope_validation_pico_usability_paper.pdf`",
        "- `figures/scope_validation_tek_high_frequency_extension_paper.pdf`",
        "- `figures/scope_validation_bandwidth_coverage_paper.pdf`",
        "- `tables/table_scope_validation_by_rate.tex`",
        "- `tables/table_scope_operating_point_regression.tex`",
        "- `tables/table_scope_idle_baseline_by_rate.tex`",
        "- `tables/table_scope_zero_offset_correction.tex` (when enabled)",
        "- `tables/table_scope_tek_reference_psd.tex`",
        "- `tables/table_scope_pico_usability.tex`",
        "- `tables/table_scope_spectral_coverage.tex`",
        "- `latex/scope_results_macros.tex`",
        "- `latex/scope_figure_snippets.tex`",
        "- `latex/scope_table_snippets.tex`",
        "- `data/` compact scope aggregates used to regenerate the figures",
        "",
    ]
    summary.write_text("\n".join(lines), encoding="utf-8")
    inventory_path = manifest_dir / "scope_paper_artifacts_inventory.csv"
    write_csv(inventory_path, _artifact_inventory(root, exclude={inventory_path}))
    return summary

