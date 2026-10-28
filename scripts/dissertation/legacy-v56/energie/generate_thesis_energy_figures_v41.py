#!/usr/bin/env python3
"""Regenerate historical English v41 figures from the packaged energy CSVs."""
from __future__ import annotations

import argparse
from pathlib import Path
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.ticker import FixedLocator, FuncFormatter

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data-dir", type=Path, default=ROOT / "results" / "supplementary-studies" / "dissertation-v56" / "inputs" / "energie",
                    help="Directory containing the frozen energy CSV inputs")
parser.add_argument("--output-dir", type=Path,
                    default=ROOT / "local-output" / "dissertation-v56-legacy" / "energie_v41" / "figures",
                    help="Destination for the historical PDFs and PNGs")
args = parser.parse_args()
DATA = args.data_dir.resolve()
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "font.size": 9.0,
    "axes.titlesize": 10.0,
    "axes.labelsize": 9.0,
    "legend.fontsize": 7.5,
    "xtick.labelsize": 8.0,
    "ytick.labelsize": 8.0,
})


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def human_duration(value: float, _pos: float | None = None) -> str:
    if value < 1.0:
        return f"{value * 1000:g} ms"
    return f"{value:g} s"


def percent_tick(value: float, _pos: float | None = None) -> str:
    return f"{value:g}%"


# ---------------------------------------------------------------------------
# Figure 1: measurement boundaries and simultaneous references
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7.2, 6.1))
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.set_title("Measurement boundaries and simultaneous reference setups", pad=10)


def box(x: float, y: float, w: float, h: float, text: str, fs: float = 8.7) -> None:
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        facecolor="white", edgecolor="black", linewidth=1.1,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)


def arrow(start: tuple[float, float], end: tuple[float, float], ls: str = "-", lw: float = 1.1) -> None:
    patch = FancyArrowPatch(
        start, end,
        arrowstyle="-|>", mutation_scale=11,
        linewidth=lw, linestyle=ls, color="black",
        shrinkA=0, shrinkB=0,
    )
    ax.add_patch(patch)

# Top chain
box(0.03, 0.75, 0.20, 0.13, "AC wall meter\nwhole-system boundary")
box(0.29, 0.75, 0.19, 0.13, "Aim-TTi CPX200DP\n19-V DC input")
box(0.54, 0.75, 0.21, 0.13, "Jetson Orin NX\nmodule input")
box(0.81, 0.75, 0.16, 0.13, "INA3221\non-board rails")
arrow((0.23, 0.815), (0.29, 0.815))
arrow((0.48, 0.815), (0.54, 0.815))
arrow((0.75, 0.815), (0.81, 0.815), ls="--")

# Lower setups
box(0.05, 0.38, 0.27, 0.20,
    "Embedded 2-kS/s setup\nu.RECS implementation\n20 m$\\Omega$ / INA225\nADS7953", fs=8.3)
box(0.365, 0.38, 0.27, 0.20,
    "PicoScope 4224A setup\n20 m$\\Omega$ / INA225 + verified $U(I)$\n50 S/s to 5 MS/s\ncurrent-path BW $\\approx$ 77 kHz", fs=8.3)
box(0.68, 0.38, 0.27, 0.20,
    "Tektronix setup\nMSO64B + TCP0030A\n5-A range; no BW limit\n2.5 kS/s to 250 MS/s", fs=8.3)

# Fan-out from the selected DC input boundary
ax.plot([0.51, 0.51], [0.75, 0.66], color="black", linestyle="--", linewidth=1.0)
ax.plot([0.185, 0.815], [0.66, 0.66], color="black", linestyle="--", linewidth=1.0)
for x in (0.185, 0.50, 0.815):
    arrow((x, 0.66), (x, 0.58), ls="--", lw=1.0)

# Trigger routing
ax.text(
    0.50, 0.19,
    "Shared Jetson GPIO trigger via TPP0051\nfor paired PicoScope/Tektronix segments",
    ha="center", va="center", fontsize=8.7,
)
ax.plot([0.50, 0.50], [0.26, 0.31], color="black", linestyle=":", linewidth=1.0)
ax.plot([0.50, 0.815], [0.31, 0.31], color="black", linestyle=":", linewidth=1.0)
arrow((0.50, 0.31), (0.50, 0.38), ls=":", lw=1.0)
arrow((0.815, 0.31), (0.815, 0.38), ls=":", lw=1.0)

ax.text(
    0.50, 0.055,
    "The common-reference analysis reconstructs lower rates from the same physical 5-MS/s execution.",
    ha="center", va="center", fontsize=8.4,
)
save(fig, "measurement_reference_setups_thesis_v41")


# ---------------------------------------------------------------------------
# Figure 2: direct rate sweeps versus same-trace sampling at 2.5 kS/s
# ---------------------------------------------------------------------------
direct = pd.read_csv(DATA / "direct_rate_validation.csv")
direct = direct[direct["direct_rate_sps"] == 2500].copy()
direct["direct_abs"] = direct["direct_power_deviation_pct"].abs()
direct["same_trace"] = direct["common_reference_hierarchical_q95_pct"].abs()
direct["Workload"] = direct["workload_label"]
direct["Setup"] = direct["source"].map({"tek": "Tektronix setup", "pico": "PicoScope/INA225 setup"})
workload_order = [
    "GEMM-FP32", "GEMM-INT8", "YOLO-FP32",
    "YOLO-INT8", "Gemma3-4B", "ResNet-50 FP32",
]
setup_order = ["Tektronix setup", "PicoScope/INA225 setup"]

fig, axes = plt.subplots(2, 1, figsize=(7.2, 6.5), sharex=True, constrained_layout=False)
fig.subplots_adjust(left=0.16, right=0.98, bottom=0.10, top=0.89, hspace=0.30)
for ax, setup in zip(axes, setup_order):
    sub = direct[direct["Setup"] == setup].set_index("Workload").reindex(workload_order)
    y = np.arange(len(workload_order))
    for yi, d, s in zip(y, sub["direct_abs"], sub["same_trace"]):
        ax.plot([s, d], [yi, yi], linewidth=1.0, alpha=0.75)
    ax.scatter(sub["direct_abs"], y, marker="o", label="separate-run median deviation", zorder=3)
    ax.scatter(sub["same_trace"], y, marker="s", label="same-trace sampling q95", zorder=3)
    ax.set_yticks(y, workload_order)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.grid(True, which="both", axis="x", alpha=0.3)
    ax.set_title(setup)
    ax.legend(loc="lower right")
axes[-1].set_xlabel("Absolute energy difference at 2.5 kS/s")
axes[-1].xaxis.set_major_locator(FixedLocator([0.05, 0.1, 0.2, 0.5, 1, 2, 5]))
axes[-1].xaxis.set_major_formatter(FuncFormatter(percent_tick))
fig.suptitle("Direct rate sweeps do not isolate the numerical sampling effect", y=0.975, fontsize=11.0)
save(fig, "direct_vs_same_trace_2p5ksps_thesis_v41")


# ---------------------------------------------------------------------------
# Figure 3: evidence horizons and 2-kS/s duration dependence
# ---------------------------------------------------------------------------
summary = pd.read_csv(DATA / "common_reference_summary.csv")
summary = summary[
    (summary["mode"] == "phase_only")
    & (summary["target_rate_sps"] == 2000)
]
worst = (
    summary.groupby(["source", "duration_s"], as_index=False)["hierarchical_abs_error_q95_pct"]
    .max()
)
long_df = pd.read_csv(DATA / "long_record_duration_q95.csv")

fig, axes = plt.subplots(2, 1, figsize=(7.2, 7.3), constrained_layout=True)
ax = axes[0]
ax.set_xscale("log")
ax.set_xlim(0.015, 750)
ax.set_ylim(-0.55, 2.55)
ax.set_yticks([2, 1, 0], [
    "six-workload common reference\n6 campaigns, 59 pairs",
    "long same-trace anchor\nGEMM-FP16, 13 runs",
    "independent command duration\n15 repetitions",
])
ax.hlines(2, 0.02, 10, linewidth=5)
ax.scatter([0.02, 10], [2, 2], s=24, zorder=3)
ax.hlines(1, 0.02, 104, linewidth=5)
ax.scatter([0.02, 104], [1, 1], s=24, zorder=3)
ax.hlines(0, 5, 600, linewidth=5)
ax.scatter([5, 600], [0, 0], s=24, zorder=3)
ax.text(0.45, 2.18, "exact sampling-only windows", ha="center", va="bottom")
ax.text(0.65, 1.18, "exact sampling-only windows", ha="center", va="bottom")
ax.text(55, 0.18, "complete benchmark commands", ha="center", va="bottom")
ax.xaxis.set_major_locator(FixedLocator([0.02, 0.1, 1, 10, 100, 600]))
ax.xaxis.set_major_formatter(FuncFormatter(human_duration))
ax.set_xlabel("Physical duration supported by the evidence")
ax.grid(True, which="both", axis="x", alpha=0.25)
ax.set_title("(a) Complementary evidence horizons")

ax = axes[1]
for source, label in [("tek", "six-workload Tektronix worst case"), ("pico", "six-workload PicoScope worst case")]:
    sub = worst[worst["source"] == source].sort_values("duration_s")
    ax.plot(sub["duration_s"], sub["hierarchical_abs_error_q95_pct"], marker="o", label=label)
ax.plot(long_df["duration_s"], long_df["q95_pct"], marker="s", label="104-s GEMM-FP16 anchor")
for threshold, style in [(1.0, "--"), (0.5, ":"), (0.1, "-.")]:
    ax.axhline(threshold, linestyle=style, linewidth=1.0, label=f"{threshold:g}% criterion")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(0.017, 125)
ax.set_ylim(0.085, 14)
ax.xaxis.set_major_locator(FixedLocator([0.02, 0.1, 0.5, 1, 2, 5, 10, 50, 104]))
ax.xaxis.set_major_formatter(FuncFormatter(human_duration))
ax.yaxis.set_major_locator(FixedLocator([0.1, 0.2, 0.5, 1, 2, 5, 10]))
ax.yaxis.set_major_formatter(FuncFormatter(percent_tick))
ax.grid(True, which="both", alpha=0.28)
ax.set_xlabel("Exact integration-window duration")
ax.set_ylabel("Hierarchical q95 energy error at 2 kS/s")
ax.set_title("(b) Sampling-only error falls with exact integration duration")
ax.legend(ncol=2, loc="upper right", fontsize=6.8)

# Annotate canonical headline points.
annotations = [
    (1.0, 1.081, "six-workload 1 s: 1.081%"),
    (2.0, 0.792, "2 s: 0.792%"),
    (5.0, 0.529, "5 s: 0.529%"),
    (10.0, 0.384, "10 s: 0.384%"),
    (104.0, 0.112315, "long anchor 104 s: 0.112%"),
]
for x, yv, text in annotations:
    ax.annotate(text, xy=(x, yv), xytext=(5, 8), textcoords="offset points", fontsize=6.7,
                arrowprops={"arrowstyle": "-", "linewidth": 0.7})

save(fig, "sampling_duration_evidence_thesis_v41")


# ---------------------------------------------------------------------------
# Figure 4: portrait-friendly frequency-band composition
# ---------------------------------------------------------------------------
bands = []
for wid in ["gemmfp32", "gemmint8", "yolofp32", "yoloint8", "gemma3-4b", "resnet50"]:
    f = ROOT / ".."  # placeholder for static analysis clarity
# The combined input contains all setups; select Tektronix current and active shares.
raw_bands = pd.read_csv(DATA / "idle_load_frequency_bands.csv")
raw_bands = raw_bands[
    (raw_bands["source"] == "tek")
    & (raw_bands["signal"] == "current")
]
# active_share_of_total_percent is the workload's bandwise active PSD composition.
pivot = raw_bands.pivot_table(
    index="workload_label", columns="band", values="active_share_of_total_percent", aggfunc="first"
).reindex(workload_order)
band_order = [
    "0–100 Hz", "100 Hz–1 kHz", "1–10 kHz",
    "10–77 kHz", "77–500 kHz", "500 kHz–2.5 MHz",
]

fig, ax = plt.subplots(figsize=(7.2, 4.6))
left = np.zeros(len(pivot))
y = np.arange(len(pivot))
for band in band_order:
    vals = pivot[band].to_numpy(dtype=float)
    ax.barh(y, vals, left=left, label=band)
    left += vals
ax.set_yticks(y, workload_order)
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.xaxis.set_major_locator(FixedLocator([0, 20, 40, 60, 80, 100]))
ax.xaxis.set_major_formatter(FuncFormatter(percent_tick))
ax.set_xlabel("Share of workload-related Tektronix current variance")
ax.set_title("Frequency-band composition at the common 5-MS/s rate")
ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=True)
ax.grid(True, axis="x", alpha=0.25)
save(fig, "cross_workload_frequency_bands_thesis_v41")

print(f"Generated thesis figures in {OUT}")
