#!/usr/bin/env python3
"""Recreate paper figure sources and figures from bundled compact records.

Called by reproduce.py with explicit input and output paths. Matplotlib, NumPy
and pandas are required; Ghostscript is optional. The current report-overlay package always refreshes its four
plot sources from bundled historical inputs and freshly updated ranking tables.
All outputs have fixed physical sizes (no bbox-dependent rescaling).
"""
from pathlib import Path
import argparse
import json
import subprocess
import shutil


OUT = None  # Set only by render(); imports never select an output directory.
MODELS = ["mobilenet_v3_large", "regnet_x_1_6gf", "resnet50", "yolo11l", "yolo26m", "yolo26s", "yolov7_paper"]
MODEL_LABELS = ["MobileNetV3-L", "RegNetX-1.6GF", "ResNet-50", "YOLO11l", "YOLO26m", "YOLO26s", "YOLOv7"]
LABEL = dict(zip(MODELS, MODEL_LABELS))
SETUPS = ["H8", "H10", "DeepX"]
COLORS = dict(zip(SETUPS, ["#1f77b4", "#d97900", "#2c8c51"]))
MARKERS = dict(zip(SETUPS, ["o", "s", "^"]))
METHODS = ["cut_bytes_only", "weighted_score", "onnx_real_boundary_hardware_aware", "cycle_time_no_handover", "stored_predicted_stream_fps", "measured_generic_completion"]
METHOD_LABELS = ["Cut\npayload", "Weighted\nscore", "HW fit\n(H10)", "Cycle\n(no handover)", "Stored\nstream rate", "Generic\ncompletion"]
ORDER = [(m, s) for m in MODELS for s in SETUPS]
FIGURES = []


def refresh_bundled_sources(inputs, generated):
    """Recreate current plot projections; never require a cached plot CSV.

    Energy ratios retain the six-model archived energy campaign. The current
    pair output determines the available identities and must agree with that
    projection. In particular, revised YOLOv7 FPS cannot acquire old energy.
    Ranking tables are generated first by update_ranking_reported --tables-only.
    """
    fields = ["model_id", "case_id", "setup_id", "cohort", "baseline_kind",
              "split_uid", "baseline_uid", "split_accuracy_class",
              "baseline_accuracy_class", "both_reference_close",
              "semantic_comparable", "energy_ratio", "energy_window_rate_ratio",
              "attestor_source_gap"]
    archived = pd.read_csv(inputs / "evidence/tables/energy_split_full.csv")
    frame = archived[archived.model_id.ne("yolov7_paper")][fields].copy()
    current = pd.read_csv(generated / "best_cases_output/best_cases_pairs.csv")
    assert current[current.model_id.eq("yolov7_paper")].energy_available.eq(False).all()
    available = current[current.energy_available.eq(True)].copy()
    assert len(frame) == len(available) == 390
    keys = ["split_uid", "baseline_uid"]
    comparison = frame.merge(available.rename(columns={
        "split_energy_uid": "split_uid", "baseline_energy_uid": "baseline_uid"}),
        on=keys, suffixes=("_plot", "_current"), validate="one_to_one")
    assert len(comparison) == 390
    for field in ["model_id", "case_id", "setup_id", "cohort", "baseline_kind",
                  "split_accuracy_class", "baseline_accuracy_class",
                  "both_reference_close", "semantic_comparable"]:
        assert comparison[field + "_plot"].equals(comparison[field + "_current"]), field
    assert np.allclose(comparison.energy_ratio,
                       comparison.split_j_per_task / comparison.baseline_j_per_task,
                       rtol=1e-12, atol=1e-14)
    assert frame.split_uid.nunique() == 195 and frame.baseline_uid.nunique() == 36
    # Regenerate the plotted ratios from per-repeat completed counts, energy,
    # and active duration. Archived pair fields only establish identity/admission.
    repeats = pd.read_csv(inputs / "best_cases_inputs/energy_repeats.csv")
    repeats["energy_fps"] = repeats.completed_count / repeats.active_duration_s
    repeats["j_per_task"] = repeats.energy_j / repeats.completed_count
    aggregates = repeats.groupby("case_uid").agg(
        energy_fps_mean=("energy_fps", "mean"), energy_fps_min=("energy_fps", "min"),
        energy_fps_max=("energy_fps", "max"), j_per_task_mean=("j_per_task", "mean"),
        j_per_task_min=("j_per_task", "min"), j_per_task_max=("j_per_task", "max"))
    for field, metric in [("energy_ratio", "j_per_task_mean"),
                          ("energy_window_rate_ratio", "energy_fps_mean")]:
        values = frame.split_uid.map(aggregates[metric]) / frame.baseline_uid.map(aggregates[metric])
        assert np.allclose(values, frame[field], rtol=1e-12, atol=1e-14), field
        frame[field] = values
    frame.to_csv(OUT / "split_full_source.csv", index=False)

    ranking = generated / "reported_update/ranking_tables"
    for filename in ("selector_loss_source.csv", "generic_stability_source.csv"):
        # The producer and consumer use identical current source bytes.
        (OUT / filename).write_bytes((ranking / filename).read_bytes())
    energy = pd.read_csv(inputs / "evidence/tables/energy_cases.csv")
    energy = energy[energy.model_id.eq("resnet50") & energy.setup_id.eq("H8")].copy()
    fields = ["model_id", "setup_id", "case_id", "backend", "execution_mode",
              "accuracy_class", "case_uid", "energy_fps_mean", "energy_fps_min",
              "energy_fps_max", "j_per_task_mean", "j_per_task_min", "j_per_task_max",
              "valid_repeats", "physical_scope", "window", "calibration_sha256",
              "attestor_source_gap"]
    energy = energy[fields]
    for field in aggregates.columns:
        values = energy.case_uid.map(aggregates[field])
        assert np.allclose(values, energy[field], rtol=1e-12, atol=1e-14), field
        energy[field] = values
    assignment = pd.read_csv(ranking / "method_groups.csv")
    assignment = assignment[assignment.model_id.eq("resnet50") &
        assignment.setup_id.eq("H8") & assignment.cohort.eq("augmented") &
        assignment.tier.eq("technical") & assignment.method.isin(METHODS)]
    assert len(assignment) == 6
    energy["selected_by"] = energy.case_id.map(lambda c: ";".join(
        method for method in METHODS
        if method in set(assignment.loc[assignment.selected_case.eq(c), "method"])))
    assert len(energy) == 21
    energy.to_csv(OUT / "resnet_energy_source.csv", index=False)


def style():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Nimbus Sans", "Arial", "Liberation Sans", "DejaVu Sans"], "font.size": 8,
        "axes.titlesize": 8.5, "axes.labelsize": 8,
        "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "legend.fontsize": 7.5, "axes.linewidth": .65,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.axisbelow": True,
        "grid.color": "#dddddd", "grid.linewidth": .45,
        "grid.alpha": .75, "xtick.major.width": .6,
        "ytick.major.width": .6, "pdf.use14corefonts": bool(shutil.which("gs")), "pdf.fonttype": 42,
        "ps.useafm": True, "svg.fonttype": "none",
        "svg.hashsalt": "mlsys-splitpoint-paper-20261005",
        "savefig.facecolor": "white", "figure.facecolor": "white",
    })


def save(fig, name, source, caption):
    metadata = {"Creator": "Historical MLSys compact-data renderer", "CreationDate": None, "ModDate": None}
    if shutil.which("gs"):
        core_pdf = OUT / f".{name}.corefonts.pdf"
        fig.savefig(core_pdf, metadata=metadata)
        try:
            subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
                "-dEmbedAllFonts=true", "-dSubsetFonts=true", "-dPDFSETTINGS=/prepress",
                "-dOmitInfoDate=true", "-dOmitID=true", f"-sOutputFile={OUT / (name+'.pdf')}",
                str(core_pdf)], check=True, capture_output=True)
        finally:
            core_pdf.unlink(missing_ok=True)
    else:
        fig.savefig(OUT / f"{name}.pdf", metadata=metadata)
    fig.savefig(OUT / f"{name}.svg", metadata={"Date": None})
    fig.savefig(OUT / f"{name}.png", dpi=200)
    FIGURES.append({"name": name, "width_inches": fig.get_figwidth(), "height_inches": fig.get_figheight(), "source": source, "caption": caption})
    plt.close(fig)


def split_full():
    data = pd.read_csv(OUT / "split_full_source.csv")
    assert len(data) == 390 and data.split_uid.nunique() == 195 and data.baseline_uid.nunique() == 36
    assert not data.model_id.eq("yolov7_paper").any(), "No current YOLOv7 energy; do not combine historical energy with revised FPS"
    fig, axes = plt.subplots(1, 2, figsize=(6.75, 3.10), sharex=True, sharey=True)
    fig.subplots_adjust(left=.092, right=.985, bottom=.255, top=.855, wspace=.125)
    for ax, kind, title in zip(axes, ["vendor_full", "tensorrt_full"], ["(a) Vendor Full", "(b) TensorRT Full"]):
        rows = data[data.baseline_kind == kind]
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlim(.14, 14); ax.set_ylim(.14, 5.1)
        ax.add_patch(Rectangle((1, .14), 13, .86, facecolor="#eef3ee", edgecolor="none", zorder=0))
        ax.axhline(1, color="#555555", ls="--", lw=.8)
        ax.axvline(1, color="#555555", ls="--", lw=.8)
        for setup in SETUPS:
            group = rows[rows.setup_id == setup]
            for quality_ok in [False, True]:
                r = group[group.semantic_comparable & (group.both_reference_close == quality_ok)]
                ax.scatter(r.energy_window_rate_ratio, r.energy_ratio, s=19, marker=MARKERS[setup], facecolors=COLORS[setup] if quality_ok else "white", edgecolors=COLORS[setup], lw=.7, alpha=.82 if quality_ok else .95, zorder=3 if quality_ok else 2)
            r = group[~group.semantic_comparable]
            ax.scatter(r.energy_window_rate_ratio, r.energy_ratio, s=24, marker="x", color=COLORS[setup], lw=.85, zorder=4)
        ticks = [.2, .5, 1, 2, 5, 10]
        ax.xaxis.set_major_locator(FixedLocator(ticks)); ax.xaxis.set_major_formatter(FixedFormatter(["0.2", "0.5", "1", "2", "5", "10"]))
        ax.yaxis.set_major_locator(FixedLocator(ticks[:-1])); ax.yaxis.set_major_formatter(FixedFormatter(["0.2", "0.5", "1", "2", "5"]))
        ax.xaxis.set_minor_formatter(NullFormatter()); ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_title(title, loc="left", pad=7)
        ax.set_xlabel("Energy-window task-rate ratio (Split / Full)", labelpad=5)
    axes[0].set_ylabel("Full-system J/task ratio (Split / Full)")
    handles = [Line2D([], [], marker=MARKERS[s], ls="", color=COLORS[s], markersize=4.8, label=s) for s in SETUPS]
    handles += [Line2D([], [], marker="o", ls="", color="#333333", markersize=4.8, label="Reference-close + semantic"), Line2D([], [], marker="o", ls="", color="#555555", markerfacecolor="white", markersize=4.8, label="Quality-limited"), Line2D([], [], marker="x", ls="", color="#555555", markersize=4.8, label="Semantic-limited")]
    fig.legend(handles=handles[:3], loc="lower center", bbox_to_anchor=(.52, .06), ncol=3, frameon=False, columnspacing=2.0, handletextpad=.4)
    fig.legend(handles=handles[3:], loc="lower center", bbox_to_anchor=(.52, .003), ncol=3, frameon=False, columnspacing=1.3, handletextpad=.4)
    save(fig, "split_full_tradeoffs", "split_full_source.csv", "Split/Full energy and task-rate ratios for the 195 split cases with current energy measurements, against each of two baseline families (390 dependent pairs; 36 unique Full baselines). YOLOv7 energy is unavailable and is excluded. Each ratio uses means of three per-repeat E/N and N/T values in the corresponding active energy windows. Filled markers have reference-close quality at both endpoints and local semantic evidence; open markers are quality-limited; crosses denote 15 semantic-limited Vendor Full pairs. The green region improves both metrics. Of the strict pairs, 78/138 improve both metrics against Vendor Full and 81/178 against TensorRT Full. Logarithmic axes; no uncertainty intervals are shown. Primary energy is calibrated full-system energy without idle subtraction. Shared baselines create dependence, and TensorRT Full retains the declared historical attestor-source gap. These are descriptive configuration comparisons, not isolated split effects.")


def selector_loss():
    rows = pd.read_csv(OUT / "selector_loss_source.csv")
    assert len(rows) == 126 and rows.cohort.eq("augmented").all() and rows.tier.eq("technical").all()
    index = rows.set_index(["model_id", "setup_id", "method"])
    matrix = np.array([[100 * index.loc[(m, s, method), "L_R"] for method in METHODS] for m, s in ORDER])
    fig, ax = plt.subplots(figsize=(6.75, 4.40))
    fig.subplots_adjust(left=.275, right=.895, bottom=.025, top=.85)
    # Individual vector cells keep PDF/SVG editable; imshow embeds a raster.
    im = ax.pcolormesh(np.arange(matrix.shape[1] + 1) - .5,
                       np.arange(matrix.shape[0] + 1) - .5, matrix,
                       cmap="YlOrRd", vmin=0, vmax=90, shading="flat")
    ax.set_xlim(-.5, matrix.shape[1] - .5)
    ax.set_ylim(matrix.shape[0] - .5, -.5)
    ax.grid(False)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=7.5, color="white" if v >= 49 else "#202020")
    hits = [int(rows.loc[rows.method == m, "top1_hit_tie_aware"].sum()) for m in METHODS]
    labels = [f"{s}\n{h}/21 hits" for s, h in zip(METHOD_LABELS, hits)]
    ax.set_xticks(range(len(METHODS)), labels)
    ax.xaxis.tick_top(); ax.tick_params(axis="x", length=0, pad=6, labelsize=7.5)
    labels = []
    for m, s in ORDER:
        n = int(index.loc[(m, s, METHODS[0]), "n"])
        labels.append(f"{s}  ({n})")
    ax.set_yticks(range(len(ORDER)), labels)
    ax.tick_params(axis="y", length=0, pad=5, labelsize=7.5)
    for tick, (_, s) in zip(ax.get_yticklabels(), ORDER):
        tick.set_color(COLORS[s])
    for i, m in enumerate(MODELS):
        ax.text(-.175, 1 - (3*i+1.5)/21, LABEL[m], transform=ax.transAxes, ha="right", va="center", fontsize=7.5, color="#222222")
    for p in np.arange(2.5, 21, 3):
        ax.axhline(p, color="white", lw=1.8)
    for p in np.arange(.5, 6, 1):
        ax.axvline(p, color="white", lw=.55)
    for spine in ax.spines.values(): spine.set_visible(False)
    cax = fig.add_axes([.92, .16, .017, .53])
    cb = fig.colorbar(im, cax=cax, ticks=[0, 20, 40, 60, 80])
    cb.solids.set_rasterized(False)
    cb.ax.tick_params(labelsize=7.5, width=.5, length=2)
    cb.set_label("Native throughput loss (%)", fontsize=8, labelpad=6)
    save(fig, "selector_loss", "selector_loss_source.csv", "Native throughput loss L_R = 1 - R_selected/R_best (percent) for six selectors in all 21 exact model/setup/precision/endpoint groups. Parentheses give the measured candidate count: 204 technical candidates overall, including 12 post-planned detection additions and retained accuracy losses. Every selector uses the same candidates within a row. The oracle is the best measured Native candidate in that row, not a global graph optimum. Native and measured Generic completion rates use medians of three 1000-task repeats. Column headings count stable Top1 selections matching the tie-aware Native best. Static selectors use archived scores and tie order; HW fit retains the historical H10 profile on all setups. Repeat and tie sensitivity are separate from these point estimates.")


def resnet_energy():
    rows = pd.read_csv(OUT / "resnet_energy_source.csv")
    assert len(rows) == 21 and rows.execution_mode.eq("native_split").sum() == 19
    assert rows.accuracy_class.eq("reference_close").all()
    fig, ax = plt.subplots(figsize=(3.25, 2.75))
    fig.subplots_adjust(left=.19, right=.97, bottom=.19, top=.86)
    split = rows[rows.execution_mode == "native_split"]
    for _, row in rows.iterrows():
        full = row.execution_mode != "native_split"
        marker = "D" if row.backend == "native_full_hailo8" else "X" if full else "o"
        color = "#555555" if full else COLORS["H8"]
        x, y = row.energy_fps_mean, 1000 * row.j_per_task_mean
        highlight = row.case_id in ["b031", "b060"]
        ax.errorbar(x, y, xerr=[[x-row.energy_fps_min], [row.energy_fps_max-x]], yerr=[[y-1000*row.j_per_task_min], [1000*row.j_per_task_max-y]], fmt=marker, ms=5.2 if full or highlight else 3.5, mew=.55, mfc=color, mec="#222222" if highlight else color, ecolor=color, lw=.55, capsize=1.1, zorder=4 if highlight else 3)
    ax.set_xlim(70, 705); ax.set_ylim(32, 146)
    ax.set_xticks([100, 250, 400, 550, 700]); ax.set_yticks([40, 60, 80, 100, 120, 140])
    ax.set_xlabel("Completed tasks/s in own energy window")
    ax.set_ylabel("Full-system energy (mJ/task)")
    # Context is in the LaTeX caption; no plot title per MLSys template.
    lookup = {r.case_id:r for _, r in split.iterrows()}
    annotations = {
        "b060": ((500, 36.5), "b060: min energy", "right"),
        "b031": ((697, 69), "b031: max rate", "right"),
        "b002": ((448, 89), "b002: Generic choice", "center"),
        "b119": ((187, 116.5), "b119: cut payload", "left"),
    }
    for case, (pos, label, align) in annotations.items():
        r = lookup[case]
        ax.annotate(label, (r.energy_fps_mean, 1000*r.j_per_task_mean), xytext=pos, textcoords="data", fontsize=7.5, ha=align, va="center", arrowprops={"arrowstyle":"-", "lw":.55, "color":"#555555", "shrinkA":1, "shrinkB":3})
    vendor = rows[rows.backend == "native_full_hailo8"].iloc[0]
    ax.text(vendor.energy_fps_mean+24, vendor.j_per_task_mean*1000, "Vendor Full", ha="left", va="center", fontsize=7.5, color="#444444")
    trt = rows[rows.backend == "native_full_tensorrt"].iloc[0]
    ax.annotate("TensorRT Full", (trt.energy_fps_mean,trt.j_per_task_mean*1000), xytext=(330,102), fontsize=7.5, ha="center", arrowprops={"arrowstyle":"-", "lw":.55, "color":"#555555", "shrinkB":3})
    save(fig, "resnet_energy", "resnet_energy_source.csv", "Within-group energy/rate tradeoff for all 19 ResNet-50/H8 split candidates, with the two Full references shown once as contextual markers (diamond: Vendor Full; X: TensorRT Full). Points are means of three own-window N/T and E/N values; bars are observed min/max ranges, not confidence intervals. All plotted endpoints are reference-close. Energy minimum b060 uses 42.286 mJ/task at 615.65 tasks/s; energy-window rate maximum b031 uses 47.715 mJ/task at 626.89 tasks/s. Selecting b060 instead reduces energy by 11.38% and rate by 1.79%, with different denominators for the two changes. Generic completion selects b002; cut-payload selection chooses b119. Primary energy is calibrated full-system energy without idle subtraction. Fulls do not enter the split oracle; TensorRT Full retains the historical attestor-source gap. The paired artifact snapshot supplies local semantic evidence for both Full comparisons.")


def generic_stability():
    rows = pd.read_csv(OUT / "generic_stability_source.csv").set_index(["model_id", "setup_id"])
    assert len(rows) == 21 and not rows.index.duplicated().any()
    assert rows.repeat_top1_hits.between(0, 9).all()
    fig, ax = plt.subplots(figsize=(6.75, 2.40))
    fig.subplots_adjust(left=.075, right=.985, bottom=.27, top=.875)
    for i, (m, s) in enumerate(ORDER):
        r = rows.loc[(m, s)]
        x = i + .25*(i//3)
        ax.vlines(x, 100*r.repeat_L_R_min, 100*r.repeat_L_R_max, color=COLORS[s], lw=1.2, zorder=2)
        ax.plot([x-.06, x+.06], [100*r.repeat_L_R_min]*2, color=COLORS[s], lw=.7)
        ax.plot([x-.06, x+.06], [100*r.repeat_L_R_max]*2, color=COLORS[s], lw=.7)
        ax.plot(x, 100*r.L_R, marker=MARKERS[s], color=COLORS[s], ms=4.2, ls="", zorder=3)
    positions = [i+.25*(i//3) for i in range(21)]
    ax.set_xticks(positions, [s if s != "DeepX" else "DX" for _,s in ORDER])
    ax.tick_params(axis="x", length=0, pad=7, labelsize=7.5)
    for i, m in enumerate(MODELS):
        ax.text(3*i+1+.25*i, -28, LABEL[m], ha="center", va="center", fontsize=7.5, clip_on=False)
        if i: ax.axvline(3*i-.5+.25*i-.125, color="#cccccc", lw=.6, zorder=0)
    ax.set_xlim(-.6,22.1); ax.set_ylim(-5, 82)
    ax.set_yticks([0,20,40,60,80]); ax.grid(axis="x", visible=False)
    ax.set_ylabel("Native rate loss (%)")
    # Context is in the LaTeX caption; no plot title per MLSys template.
    save(fig, "generic_stability", "generic_stability_source.csv", "Measured Generic-completion selection across all 21 exact groups (204 technical candidates). Symbols use the three-repeat median rates. Vertical ranges span all nine Generic/Native repetition combinations and are neither confidence intervals nor nine independent experiments. The selection baseline in each combination is the best observed Native candidate in that group. H8, H10, and DX denote Hailo-8, Hailo-10H, and DeepX. Quality losses and the 12 post-planned additions remain in this technical cohort. Large observed failures, including RegNetX/H10 and ResNet-50/H10, persist across the existing repetition combinations.")


def notes():
    d = pd.read_csv(OUT / "split_full_source.csv")
    r = pd.read_csv(OUT / "resnet_energy_source.csv").set_index("case_id")
    text = ["# Figure captions and numerical checks", "", "All figures use fixed physical sizes; embed at their recorded width. Fonts are 7.5 pt or larger. PDF and SVG are native vector plots. When available, Ghostscript embeds standard Type-1 fonts; otherwise Matplotlib embeds TrueType outlines. SVG retains editable text. Raster previews use the matching sans-serif fallback. Mathematical loss notation is defined in the captions rather than rendered with a non-Type-1 math font in the axes. Figure CSVs are regenerated projections of the preserved compact inputs. No new hardware runs, confidence intervals, or causal measurements are implied.", ""]
    for f in FIGURES:
        text += [f"## {f['name']} ({f['width_inches']} × {f['height_inches']} in)", "", f["caption"], "", f"Source: `{f['source']}`.", ""]
    text += ["## Numerical checks", "", f"- Split/Full: {len(d)} rows, {d.split_uid.nunique()} split identities, {d.baseline_uid.nunique()} Full identities.", f"- Semantic-limited: {(~d.semantic_comparable).sum()} pairs, all Vendor Full.", f"- ResNet/H8: b060 vs b031 energy decrease = {(1-r.loc['b060','j_per_task_mean']/r.loc['b031','j_per_task_mean'])*100:.9f}%; energy-window rate decrease = {(1-r.loc['b060','energy_fps_mean']/r.loc['b031','energy_fps_mean'])*100:.9f}%.", "- Ratio figures aggregate mean E/N and mean N/T separately; the power/rate identity need not hold exactly for a ratio of arithmetic means.", "- Filled Split/Full symbols indicate the stated quality and semantic filters only, not claim eligibility or a passed historical provenance attestation.", "- Heatmap L_R is recomputed in the archived analysis from measured Native rates; it is not latency and uses a measured-set oracle.", "- Generic stability displays dependent repetition combinations; ranges do not imply inferential coverage.", ""]
    (OUT / "FIGURE_CAPTIONS.md").write_text("\n".join(text))


def update_current_metadata():
    """Apply the report-overlay caption and hash updates after figure rendering."""
    captions={
        'selector_loss': (
            'Native throughput loss L_R = 1 - R_selected/R_best (percent) for six selectors '
            'in 21 fixed candidate groups (204 technical candidates). Parentheses give the '
            'measured candidate count. YOLOv7 uses final native rates from the supplied '
            'campaign report and historical Generic rates; the other six models retain '
            'archived measurements. This is descriptive selector transfer across recorded '
            'campaigns, not a same-state controlled comparison. Column headings count '
            'Top1 selections matching the native winner. Static selections and tie order '
            'are frozen; the stored hardware fit retains its H10 profile on all setups. '
            'The oracle is the best candidate in the measured row, not a global graph '
            'optimum. Throughput uses three-repeat medians; repetition and tie sensitivity '
            'are separate from these point estimates.'),
        'generic_stability': (
            'Generic-completion selection loss across 21 groups (204 technical candidates). '
            'Symbols use three-repeat median rates. YOLOv7 pairs historical Generic '
            'repetitions with final native repetitions from the supplied report; all other '
            'groups retain archived repetitions. Vertical ranges span nine dependent '
            'Generic/Native repetition combinations, not confidence intervals or nine '
            'independent experiments. H8, H10, and DX denote Hailo-8, Hailo-10H, and DeepX. '
            'Accuracy-loss cases and the 12 post-planned additions remain in the technical '
            'cohort. Near-tied Generic candidates can give a correct median recommendation '
            'yet a large observed loss range, as for YOLOv7/DeepX.')}
    caption_path=OUT/'FIGURE_CAPTIONS.md'
    text=caption_path.read_text()
    for name,caption in captions.items():
        start=text.index('## '+name)
        body_start=text.index('\n\n',start)+2
        body_end=text.index('\n\nSource:',body_start)
        text=text[:body_start]+caption+text[body_end:]
    text=text.replace(
        '- Heatmap L_R is recomputed in the archived analysis from measured Native rates; it is not latency and uses a measured-set oracle.',
        '- Heatmap L_R is recomputed from the final reported YOLOv7 native rates and archived rates for the other models; it uses a measured-set oracle. Reported values were not independently verified against a raw ZIP.')
    caption_path.write_text(text)


def render(inputs, generated, output):
    """Regenerate plot projections from fresh numerical stages, then all formats."""
    global OUT, plt, Line2D, Rectangle, FixedLocator, FixedFormatter, NullFormatter, np, pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FixedLocator, FixedFormatter, NullFormatter
    import numpy as np
    import pandas as pd
    OUT = output
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURES.clear()
    refresh_bundled_sources(inputs, generated)
    style()
    split_full(); selector_loss(); resnet_energy(); generic_stability(); notes()
    update_current_metadata()
    return len(FIGURES)
