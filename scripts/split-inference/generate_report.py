#!/usr/bin/env python3
"""Generate methods and findings from the compact observed data."""
import json
from pathlib import Path

def read(p):
    return json.loads(p.read_text())

def tex(value):
    replacements = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
                    '#': r'\#', '_': r'\_\allowbreak{}', '/': r'/\allowbreak{}', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}'}
    return ''.join(replacements.get(c, c) for c in str(value))

def render(output):
    out = Path(output)
    s = read(out/'data/summary.json')
    data = read(out/'data/PAPER_DATASET.json')
    ng = s['native_generic']
    fc = s['fastest_full_comparison']
    ec = s['lowest_full_energy_comparison']
    opt = s['optima']
    top = read(out/'tables/table3_top2_native.json')
    best = max(top, key=lambda r: r['speedup'])
    n_single = sum(r['performance_observations']==1 for r in data)
    mismatches = [r for r in data if r.get('quality_cached_loss_disagrees')]
    methods = f'''# Methods: Native A4 paper analysis

The analysis uses the canonical `{s['source_generation']}` selection, projected from the active `CURRENT.json` and its existing manifest. It contains {s['cases']} deployment identities ({s['native']} Native and {s['generic']} Generic), including {s['full_coverage']['configurations']} host-specific Full configurations. DeepX Native A4 replaces performance and energy for {s['native_a4_cases']} exact Native identities: 68 DeepX-to-TensorRT splits and seven DeepX Full deployments. Each has three accepted independent performance processes and three valid energy repeats, including the explicitly reused complete acceptance cohorts. The other {s['unchanged_cases']} direct observations and their repeats remain unchanged, including Generic on the DeepX host and that host's seven TensorRT Full references. All original dataset-quality values, sources, selections and flags are preserved. No measurement, model build or dataset evaluation is performed by this offline tool.

The updated Native DeepX deployments use A4 with batch one, one engine and at most four outstanding DeepX jobs. Splits use FIFO depth three and a serial TensorRT consumer through task completion. Generic deployments retain their original runtime and measurements. These are comparisons between measured deployments with their recorded parallelism; they do not isolate chip or splitting effects at equal parallelism. A4 runtime sources and the final reader/importer source evidence are identified separately in the software overview; the update does not claim that all 450 observations were newly acquired under one tool version.

## Selection and coverage

The primary view includes every available measured numeric observation. Accuracy-loss classes, a 5% loss threshold, a single historical repeat, screening/diagnostic status, recorded claim flags and missing administrative hashes do not veto a row. The 75 A4 observations retain the normal reader's nonclaim performance/energy status and its explicit exclusion reasons, including screening energy policy; accepted source completion is not a claim of cross-backend endpoint equivalence. Included means used in this descriptive deployment comparison; it does not establish equality of executed work. Performance-only questions use observed FPS independently of energy; energy questions require observed energy, and joint questions use the intersection. The measured coverage is {s['performance_coverage']}/{s['cases']} FPS, {s['energy_coverage']}/{s['cases']} energy and {s['quality_numeric_coverage']}/{s['cases']} numeric dataset-quality values.

Source selection follows completed canonical observations, never highest FPS or filesystem modification time. The explicit per-metric fallback accepts a latest completed older observation only when a newer matching metric is absent or invalid, retaining exact host, model, cut, runtime, input and endpoint identity. No such fallback is needed for the current complete FPS/energy matrix. Source generations and actual field locations are listed in `data/METRIC_SOURCES.csv` and `data/MEASUREMENT_GENERATIONS.csv`; re-assignment of existing quality is not counted as a new evaluation.

## Metrics and uncertainty

Throughput is images/s (FPS), preserving the median of the recorded independent repeats. Historical single observations remain labelled n=1 ({n_single} current identities), without an invented confidence interval. The primary energy is calibrated host-inclusive energy per completed image: for repeat r, e_r=E_r/N_r, then mean(e_r). The compact display is 1000*mean(e_r) mJ/image. N_r is completed images, never detected boxes. Total joules, actual command-window duration, average power, image count and each repeat remain in the accompanying tables. Existing host/idle-corrected comparison energy is a separately labelled sensitivity; no new correction is estimated.

The descriptive repeat range and sample coefficient of variation remain visible. Existing three-repeat t intervals describe the energy mean, not the FPS median, and do not establish between-implementation significance. Mean(N/E), 1/mean(E/N) and sum(N)/sum(E) are separately named and generally differ. Neither J/FPS nor a compound throughput/energy score is used. Small differences are observations, not significance claims.

## Comparisons and weighting

All ratios are computed from unrounded inputs. Native/Generic pairs match model, host and cut. All split rows are compared to both measured Full alternatives on the same host, with winners and nonwinners retained. Table 2 reports TRT ranges across the three host aggregates; these ranges are not repeat confidence intervals. Host values and arithmetic means are separately available. Table 3 selects the two Native configurations with the largest FPS ratio to the fastest observed Full on the same host for each model. Stable ascending UID breaks ties. Energy never changes this FPS ranking. Energy gain G_n=e_full/e_split uses exactly the same Full identity as that row's speedup; values greater than one indicate lower split energy. The independently lowest-energy Full is kept separately.

Point-pooled summaries are separate from equal-model summaries. The latter first take the point median within each model/setup, then average setups within each model, then average those model values. Classifiers with many cuts therefore receive no extra model weight. Fastest and lowest-energy splits are selected within each model/setup/runner. Shared optima are one configuration; groups with a single candidate are distinguished from multiple-candidate groups. All optimum and Top-2 selections are retrospective, with no prediction or causal interpretation.

## Empirical performance–energy fronts

The seven `04_tradeoff_<model>` figures show every observed finite FPS/energy point in separate H8, H10 and DeepX panels, including both host-specific Full alternatives. The empirical two-objective front maximizes unrounded FPS and minimizes calibrated host-inclusive mJ/image within exactly one model/setup. B dominates A only when B has at least as much FPS and at most as much energy, with at least one strict inequality. Equal coordinates do not dominate each other; all associated UIDs are retained. Dataset quality determines color, not admission or dominance. Missing quality is neutral gray; missing/nonfinite FPS or energy is recorded with an omission reason, never replaced by zero.

Front points have an extra outline. A thin line joins distinct front coordinates in FPS order only when there are at least two; a singleton has no line. Lines guide the eye between discrete observations and imply no attainable intermediate configuration. `tables/PARETO_POINTS.csv` and `.json` contain exact values, grouping, joint-front flags, separate Native/Generic split-only front flags and a deterministic dominating UID where one exists. `figures/FIGURE_DATA.json` records plotted identities, front coordinates and label selections. `tables/pareto.*` retains its separate recorded-work-cohort sensitivity scope and is recalculated from the current observations. Neither view establishes equal quality or equal timed work.

## Dataset quality and source inconsistencies

Top-1 accuracy and COCO mAP@[.50:.95] are distinct metrics. Numerical metrics, reference values, sample counts and existing bootstrap intervals are copied from the selected completed quality evidence. Output parity/PASS is not dataset accuracy. Relative loss (reference-candidate)/reference and percentage-point differences 100*(candidate-reference) are separately named. Vendor-Full and split quality are shown even when Hailo Full quality is substantially below the model reference.

For {len(mismatches)} Native DeepX classifier rows, the selected quality summary's numerical result differs from the cached relative loss in Current. The newer summary numbers are exposed as `quality_value` and `quality_numeric_relative_loss`; the original `quality_relative_loss`, quality class and gates remain unchanged. Both values and their exact sources are published, rather than substituting an older, more favorable result or silently repairing Current. This is a projection of existing reports, not a new quality evaluation. The prior 17 administrative receipt-version gaps and unresolved historical Full-producer source version remain provenance limits.

## Executed work and remaining interpretation limits

All 36 Native detector split configurations record an oracle outside timing, whereas the 36 corresponding Generic detector splits record `decoded_nms`. The 12 A4 DeepX detector splits explicitly record `native_three_stage_fast_oracle_outside_timing`: their correctness oracle runs outside the timed loop. The A4 DeepX detector Full paths retain their actual `frozen_host_tail` or `integrated_accelerator_plus_frozen_normalization` completion modes. The unchanged earlier YOLO26s H8/H10 Vendor Full paths record dense outputs with host decoding/NMS; the corresponding TensorRT Full paths include their recorded frozen normalization. Per-configuration completion modes and execution notes retain each observed boundary. These implementation differences remain visible even where a comparison-endpoint declaration matches. A missing or different administrative hash alone establishes neither equal nor different work and does not remove an observation. The deployment ratios therefore do not isolate the causal effect of graph splitting at equal executed work.

Other recorded completion modes, prepared-input identities and work boundaries are retained per identity. Missing contract hashes alone are not evidence of different executed work; unknown entries remain unknown. Missing historical clock profiles remain unknown for their original dated records; the new A4 cohorts retain their normal verified runtime and source evidence. Contextual comparisons are retained. Strict recorded claim/provenance and reference-close views are optional sensitivities, never the hidden main selection. Broad plots show raw throughput, host-inclusive energy and quality. The recorded-work Pareto sensitivity retains its cohorts; the broad empirical front uses the model/setup population defined above. Neither establishes equal quality or universal endpoint equivalence.
'''
    (out/'METHODS.md').write_text(methods)
    findings = f'''# Findings from the broad Native A4 selection

This report is generated from the same selected rows as Tables 2/3 and all figures. {s['cases']} identities provide {s['performance_coverage']} FPS and {s['energy_coverage']} energy observations, including all {s['full_coverage']['configurations']} Full deployments. Numeric dataset quality covers {s['quality_numeric_coverage']} identities. No measurement or quality evaluation was started by this analysis.

Native exceeds Generic throughput in {ng['faster']}/{ng['n_performance']} paired points and uses less raw energy in {ng['energy_lower']}/{ng['n_energy']}; {ng['both_better']}/{ng['n_joint']} improve both. The point-pooled median Native/Generic ratios are {ng['fps_ratio_median']:.4f} for throughput and {ng['energy_ratio_median']:.4f} for energy. Separate equal-model results in `tables/equal_model_summary.json` avoid weighting models by their number of cuts.

Against the fastest Full on the same host, {fc['faster']}/{fc['splits']} Native splits are faster. Against the separately selected minimum-energy Full, {ec['lower']}/{ec['splits']} use less energy. The largest observed speedup is {best['speedup']:.3f}x for {best['model']} {best['setup']}/{best['case']}; its energy gain against that exact same Full is {best['energy_gain_same_full']:.3f}. Table 3 reports the Top-2 for every model, selected from unrounded FPS ratios without energy filtering. These are retrospective results.

The fastest and minimum-energy Native split differ in {opt['multi_candidate_conflicts']}/{opt['multi_candidate_groups']} groups with more than one candidate. Shared optima and the candidate counts are shown explicitly. A small ratio above one is described as a small observed advantage; the analysis does not infer statistical significance from it.

Quality is a separate result axis. The original {s['quality_loss'].get('native',0)} Native and {s['quality_loss'].get('generic',0)} Generic accuracy-loss flags remain visible. Vendor Full quality, model reference quality and every available split score appear in the quality figures. {len(mismatches)} cached Current losses differ from the numerical selected quality reports; both are retained. The Full and split figures display actual deployments with their quality and timed-work differences, including the YOLO26s fast-oracle versus host-tail distinction described in `METHODS.md`.

See [Table 2](tables/table2_full.md), [Table 3](tables/table3_top2_native.md), [methods](METHODS.md), [figure captions](CAPTIONS.md), and [all machine-readable findings](data/summary.json). Missing values, if any, are enumerated by UID in `data/summary.json`. Historical source-version and clock-profile limitations remain; these do not trigger a new measurement campaign.
'''
    (out/'FINDINGS.md').write_text(findings)
    # Source paragraphs are supplied separately from any private manuscript.
    paragraph = ('We report the broad measured deployment selection, retaining quality-loss, single-repeat and screening observations with their original flags. '
                 'Throughput is the recorded cohort median in images/s. Energy is calibrated host-inclusive energy per completed image, averaged as the mean of per-repeat E/N and displayed in mJ/image. '
                 'Dataset Top-1 accuracy or COCO mAP is reused from the selected existing evidence and shown separately. '
                 'Table 3 ranks Native splits retrospectively against the fastest measured Full on the same host and uses that exact Full for both speedup and energy gain. '
                 'Source generations and numerical quality/cache discrepancies are recorded per metric. '
                 'Empirical performance--energy fronts maximize throughput and minimize host-inclusive energy within each model/setup, including both Full alternatives; quality is shown by color and is not a dominance objective. '
                 'The 75 updated Native DeepX observations use batch-one, single-engine A4 with at most four outstanding jobs; splits use FIFO depth three and a serial TensorRT consumer through task completion. The other 375 direct observations and all 450 selected dataset-quality observations are retained. '
                 'Native detector splits record a correctness oracle outside timing, whereas Generic detector splits record decoded NMS; Full paths retain their recorded host-tail or integrated normalization work. These ratios compare observed deployments with their recorded parallelism and do not isolate a causal effect of splitting at identical work.')
    (out/'METHODS_PARAGRAPH.tex').write_text(tex(paragraph)+'\n')

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    render(p.parse_args().output)
