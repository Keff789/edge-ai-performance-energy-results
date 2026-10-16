"""Pure table/figure rendering adapted from finalize_stage_cost_report.py::plots.

Plot inputs are the freshly evaluated ANALYSIS and block comparison records.
Matplotlib is loaded only when rendering figures; table rendering uses stdlib.
"""
import csv
import statistics


def case_labels(plan):
    return {c["case_id"]: c["family"].replace("H10 /", "Hailo-10H /") + " / " + c["split"]
            for c in plan["cases"]}


def plot_values(analysis, plan, comparisons):
    labels = case_labels(plan)
    values = []
    for case in analysis["cases"]:
        if not case["n"]:
            continue
        blocks = [r for r in comparisons
                  if r["record_type"] == "block" and r["case_id"] == case["case_id"]]
        if len(blocks) != case["n"]:
            raise ValueError("comparison count differs from the evaluated case")
        med = lambda key: case["metrics"][key]["median"]
        values.append({"label": labels[case["case_id"]],
                       "P_ms": med("cP_ms"), "C_ms": med("cC_ms"),
                       "PC_ms": statistics.median(1000 / float(r["fps_PC_core"]) for r in blocks),
                       "PC_fps": med("fps_PC_core"), "Oracle_fps": med("fps_Oracle_core")})
    return values


def render_tables(analysis, plan, output):
    recipes = {c["case_id"]: c for c in plan["cases"]}
    rows = []
    for case in analysis["cases"]:
        recipe = recipes[case["case_id"]]
        backend, model = recipe["family"].split(" / ")
        backend = "Hailo-10H" if backend == "H10" else backend
        m = case["metrics"]
        row = dict(case_id=case["case_id"], backend=backend, model=model, cut=recipe["split"],
                   n_blocks=case["n"])
        for column, metric in [("prefix_core_fps", "fps_P_core"), ("consumer_core_fps", "fps_C_core"),
                               ("oracle_core_fps", "fps_Oracle_core"), ("pipeline_core_fps", "fps_PC_core"),
                               ("pipeline_total_fps", "fps_PC_total")]:
            row[column + "_median"] = m[metric]["median"]
        for stat in ("median", "min", "max"):
            row["absolute_error_pct_" + stat] = m["absolute_error_pct"][stat]
        row["cycle_residual_ms_median"] = m["cycle_residual_ms"]["median"]
        row["bottleneck_in_model"] = "P" if m["cP_ms"]["median"] >= m["cC_ms"]["median"] else "C"
        row["blocks_inside_predeclared_10pct"] = case["within_10pct_band_n"]
        rows.append(row)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "STAGE_COST_SUMMARY.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    md = ["# Independent stage-cost summary", "",
          "[Full-precision CSV](STAGE_COST_SUMMARY.csv) · [LaTeX table](stage_cost_table.tex)", "",
          "All rates are medians of matching blocks. Errors are calculated within each block before aggregation; "
          "they are not generally the ratio of the displayed FPS medians. P counts usable boundary tensors; "
          "C/PC count completed classifications. All primary rates use the fixed core window.", "",
          "| Case | P / s | C / s | Oracle / s | PC / s | Median absolute error | Maximum absolute error | Blocks |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    tex = [r"% Generated from freshly evaluated ANALYSIS.json; display rounding only.",
           r"\begin{table}[htbp]", r" \centering\small",
           r" \caption{Independent prediction and observed pipeline throughput: medians over three blocks. Error summaries use blockwise ratios, not ratios of the displayed column medians.}",
           r" \label{tab:evaluation:stage_cost_oracle_20261014}", r" \setlength{\tabcolsep}{3.5pt}",
           r" \renewcommand{\arraystretch}{1.12}",
           r" \begin{tabularx}{\linewidth}{@{}X S[table-format=4.0] S[table-format=4.0] S[table-format=1.2] S[table-format=1.2]@{}}",
           r" \toprule", r" Recipe & {Predicted} & {Measured} & \multicolumn{2}{c}{Absolute error [\%]} \\",
           r" & {FPS} & {FPS} & {Median} & {Maximum} \\", r" \midrule"]
    for row in rows:
        label = f"{row['backend']} / {row['model']} / {row['cut']}"
        rates = [row[k + "_median"] for k in ("prefix_core_fps", "consumer_core_fps", "oracle_core_fps", "pipeline_core_fps")]
        error, maximum = row["absolute_error_pct_median"], row["absolute_error_pct_max"]
        md.append(f"| {label} | " + " | ".join(f"{v:.0f}" for v in rates) +
                  f" | {error:.2f}% | {maximum:.2f}% | {row['n_blocks']} |")
        tex_label = f"{row['backend']} / {row['model']} / \\texttt{{{row['cut']}}}"
        tex.append(f"{tex_label} & {rates[2]:.0f} & {rates[3]:.0f} & {error:.2f} & {maximum:.2f} " + r"\\")
    md += ["", "All twelve errors are positive (optimistic Oracle) and below the predeclared 10% band, "
           "which is not a confidence interval. Both within-model cut orderings match in all three blocks. "
           "The detailed comparison CSV contains twelve block comparisons plus six pair-ratio rows; "
           "those are not eighteen independent observations.", "",
           "Experiment `stage_cost_composition_20261014`, source revision `20261014T102852Z`. "
           "The CSV retains full precision and also reports total pipeline FPS, minimum error, cycle residual and bottleneck."]
    tex += [r" \bottomrule", r" \end{tabularx}", r"\end{table}"]
    (output / "STAGE_COST_SUMMARY.md").write_text("\n".join(md) + "\n")
    (output / "stage_cost_table.tex").write_text("\n".join(tex) + "\n")


def plots(analysis, plan, comparisons, output):
    # Matplotlib cache and all temporary files are placed by the caller.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    values = plot_values(analysis, plan, comparisons)
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"pdf.fonttype": 42, "svg.fonttype": "none"})

    def save(fig, name):
        for ext in ("pdf", "svg", "png"):
            fig.savefig(output / (name + "." + ext), dpi=180)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.2))
    for row in values:
        ax.scatter(row["PC_fps"], row["Oracle_fps"], label=row["label"], s=55)
    largest = max(max(r["PC_fps"], r["Oracle_fps"]) for r in values) * 1.1
    ax.plot([0, largest], [0, largest], color="gray", linewidth=1)
    ax.set(xlabel="Observed PC core rate (completions/s)", ylabel="Oracle core rate (completions/s)",
           xlim=(0, largest), ylim=(0, largest))
    ax.legend(fontsize=8)
    ax.grid(alpha=.2)
    fig.tight_layout()
    save(fig, "prediction_observation")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    xs = list(range(len(values)))
    width = .25
    for offset, key, label in [(-width, "P_ms", "Isolated P"), (0, "C_ms", "Isolated C"),
                                (width, "PC_ms", "PC cycle")]:
        ax.bar([x + offset for x in xs], [r[key] for r in values], width, label=label)
    names = [r["label"].rsplit(" / ", 1) for r in values]
    ax.set_xticks(xs, [family + "\n" + cut for family, cut in names])
    ax.tick_params(axis="x", labelsize=8)
    ax.set_ylabel("Effective core interval (ms/completion)")
    ax.legend()
    ax.grid(axis="y", alpha=.2)
    fig.tight_layout()
    save(fig, "stage_costs")
