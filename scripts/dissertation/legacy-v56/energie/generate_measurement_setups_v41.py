#!/usr/bin/env python3
"""Regenerate the historical English v41 measurement-boundary schematic."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.lines import Line2D

matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["font.size"] = 9.5

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output-dir", type=Path,
                    default=ROOT / "local-output" / "dissertation-v56-legacy" / "energie_v41" / "figures",
                    help="Destination for the historical PDF and PNG")
args = parser.parse_args()
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)

fig, ax = plt.subplots(figsize=(12.4, 5.5), constrained_layout=True)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")


def box(x, y, w, h, text, fontsize=9.3, lw=1.15):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.012,rounding_size=0.015",
        facecolor="white", edgecolor="black", linewidth=lw,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize)
    return patch


def arrow(start, end, linestyle="-", lw=1.2, ms=10):
    patch = FancyArrowPatch(
        start, end,
        arrowstyle="-|>", mutation_scale=ms,
        linewidth=lw, linestyle=linestyle, color="black",
        shrinkA=0, shrinkB=0,
    )
    ax.add_patch(patch)
    return patch

# Main physical boundary chain.
box(0.025, 0.70, 0.18, 0.16, "AC wall meter\nwhole-system boundary")
box(0.275, 0.70, 0.18, 0.16, "Aim-TTi CPX200DP\n19-V DC input")
box(0.535, 0.70, 0.20, 0.16, "Jetson Orin NX\nmodule-input boundary")
box(0.815, 0.70, 0.16, 0.16, "INA3221\non-board rails")
arrow((0.205, 0.78), (0.275, 0.78))
arrow((0.455, 0.78), (0.535, 0.78))
arrow((0.735, 0.78), (0.815, 0.78), linestyle="--")

# Three setups observe the selected DC module-input boundary.
box(0.055, 0.30, 0.25, 0.20,
    "Embedded 2-kS/s setup\n"
    "u.RECS implementation\n"
    r"20 m$\Omega$ / INA225 / ADS7953" "\n"
    "current-path bandwidth approx. 77 kHz",
    fontsize=8.8)
box(0.375, 0.30, 0.25, 0.20,
    "PicoScope 4224A setup\n"
    r"20 m$\Omega$ / INA225 + verified $U(I)$" "\n"
    "50 S/s to 5 MS/s\n"
    "current-path bandwidth approx. 77 kHz",
    fontsize=8.8)
box(0.695, 0.30, 0.25, 0.20,
    "Tektronix setup\n"
    "MSO64B + TCP0030A\n"
    "5-A range; no BW limit\n"
    "2.5 kS/s to 250 MS/s",
    fontsize=8.8)

# A clean measurement tap and distribution bus avoid crossing any labels.
tap_x = 0.495
ax.plot([tap_x, tap_x], [0.78, 0.59], linestyle="--", linewidth=1.0, color="black")
ax.plot([0.18, 0.82], [0.59, 0.59], linestyle="--", linewidth=1.0, color="black")
for x in (0.18, 0.50, 0.82):
    arrow((x, 0.59), (x, 0.50), linestyle="--", lw=1.05)

# Shared GPIO trigger applies only to the paired external records.
ax.text(0.66, 0.13,
        "Shared Jetson GPIO trigger via TPP0051\n"
        "for paired PicoScope/Tektronix records",
        ha="center", va="center", fontsize=9.2)
ax.plot([0.50, 0.50], [0.24, 0.20], linestyle=":", linewidth=1.0, color="black")
ax.plot([0.50, 0.82], [0.20, 0.20], linestyle=":", linewidth=1.0, color="black")
arrow((0.50, 0.20), (0.50, 0.30), linestyle=":", lw=1.0)
arrow((0.82, 0.20), (0.82, 0.30), linestyle=":", lw=1.0)

legend_lines = [
    Line2D([0], [0], color="black", lw=1.2, linestyle="-"),
    Line2D([0], [0], color="black", lw=1.2, linestyle="--"),
    Line2D([0], [0], color="black", lw=1.2, linestyle=":"),
]
ax.legend(
    legend_lines,
    ["power flow", "declared measurement relation", "shared trigger"],
    loc="lower left", bbox_to_anchor=(0.02, 0.02),
    ncol=3, frameon=False, fontsize=8.4, handlelength=2.6,
)

for ext in ("pdf", "png"):
    fig.savefig(OUT / f"measurement_setups_v41.{ext}", dpi=240, bbox_inches="tight")
print(OUT / "measurement_setups_v41.pdf")
