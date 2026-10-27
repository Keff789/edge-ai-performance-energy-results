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


def render_gallery(out, summary, fastest):
    """Build navigation from the same current figure index and table selection."""
    index = read(out/'figures/INDEX.json')
    by_name = {item['name']: item for item in index}
    names = {'mobilenet_v3_large': 'MobileNetV3 Large', 'regnet_x_1_6gf': 'RegNet X 1.6GF',
             'resnet50': 'ResNet-50', 'yolo11l': 'YOLO11l', 'yolo26m': 'YOLO26m',
             'yolo26s': 'YOLO26s', 'yolov7_paper': 'YOLOv7'}
    models = [row['model'] for row in fastest]
    gallery = ['# Split-inference gallery', '',
               '[Result overview](../README.md) · [Tables](../tables/README.md) · [Full captions](../CAPTIONS.md)', '',
               f'All {len(index)} current figure families are included. Each has a vector PDF/SVG and a PNG preview. Throughput is images/s and calibrated energy includes the host. The figures compare observed deployments with their recorded quality and timed-work differences.', '',
               '## Complete model views and empirical Pareto fronts', '']
    model_dir = out/'figures/models'
    model_dir.mkdir(exist_ok=True)
    for model in models:
        name = names.get(model, model)
        gallery += [f'- [{name}: performance, energy and dataset quality](models/{model}.md)']
        page = [f'# {name}', '',
                '[All figures](../README.md) · [Methods](../../METHODS.md) · [Complete data](../../data/PAPER_DATASET.csv)', '']
        for basename, title, alt in [
                ('04_tradeoff_'+model, 'Throughput, energy, empirical Pareto front and quality', 'Throughput, energy and quality'),
                ('06_quality_'+model, 'All split and Full quality observations', 'All split and Full quality observations')]:
            item = by_name[basename]
            page += ['## '+title, '', f'![{alt}](../{basename}.png)', '',
                     ' · '.join(f'[{fmt.upper()}](../{basename}.{fmt})' for fmt in item['formats']), '',
                     item['caption'], '']
        (model_dir/(model+'.md')).write_text('\n'.join(page)+'\n')
    pareto = read(out/'tables/PARETO_POINTS.json')
    front_count = sum(row['pareto_all'] is True for row in pareto)
    gallery += ['',
                f'The {len(models)} model views retain all observations, both Full alternatives and dataset quality. Outlines mark the joint performance–energy front within each model/setup; lines connect discrete front coordinates only. [All {summary["cases"]} points and front flags](../tables/PARETO_POINTS.csv) distinguish the {front_count} joint front points from runner-specific split fronts. See [methods](../METHODS.md) for dominance and interpretation limits.', '']
    titles = {
        'fastest_split_baseline_comparison': 'Baseline effect: the same selected split, two Full references',
        'fastest_deployment_tradeoff': 'Fastest deployments: throughput and energy relative to global Full',
        '01_full_throughput': 'All Full deployments: throughput',
        '02_full_energy': 'All Full deployments: energy per image',
        '03a_native_generic_pooled': 'Native and Generic: pooled operating points',
        '03b_native_generic_equal_model': 'Native and Generic: equal model weighting',
        '03c_native_generic_model_setup': 'Native and Generic: every model and setup',
        '05_fastest_vs_min_energy': 'Fastest and lowest-energy splits',
        '06_quality_reference_comparison': 'Dataset quality relative to model references',
    }
    gallery += ['[Recommended Table 3: global fastest Full and split](../tables/table3_fastest_deployments.md) · [Same split, two Full baselines](../tables/fastest_split_baselines.md) · [Supplementary relative same-host Top-2](../tables/table3_top2_native.md)', '']
    for basename, title in titles.items():
        item = by_name[basename]
        gallery += ['## '+title, '', f'![{title}]({basename}.png)', '',
                    ' · '.join(f'[{fmt.upper()}]({basename}.{fmt})' for fmt in item['formats']), '',
                    item['caption'], '']
    (out/'figures/README.md').write_text('\n'.join(gallery)+'\n')


def render(output):
    out = Path(output)
    s = read(out/'data/summary.json')
    data = read(out/'data/PAPER_DATASET.json')
    current = read(out/'data/current_observation_binding.json') if (out/'data/current_observation_binding.json').is_file() else None
    ng = s['native_generic']
    fc = s['fastest_full_comparison']
    ec = s['lowest_full_energy_comparison']
    opt = s['optima']
    top = read(out/'tables/table3_top2_native.json')
    fastest = read(out/'tables/table3_fastest_deployments.json')
    global_compared = [r for r in fastest if r['R_global'] is not None]
    joint_compared = [r for r in global_compared if r['energy_ratio_global'] is not None]
    global_faster = sum(r['R_global'] > 1 for r in global_compared)
    global_both = sum(r['R_global'] > 1 and r['energy_ratio_global'] < 1 for r in joint_compared)
    denominator_changed = sum(r['host_full_uid'] is not None and r['global_full_uid'] is not None
                              and r['host_full_uid'] != r['global_full_uid'] for r in fastest)
    slower = [r for r in global_compared if r['R_global'] < 1]
    slower_description = ('Selected splits below their global Full reference: '+
                          '; '.join(f"{r['model']} {r['split_setup']}/{r['split_case']} (R_global={r['R_global']:.2f}, R_host={r['R_host']:.2f})"
                                    if r['R_host'] is not None else
                                    f"{r['model']} {r['split_setup']}/{r['split_case']} (R_global={r['R_global']:.2f}; same-host Full missing)"
                                    for r in slower)+'.') if slower else 'No selected split is below its observed global Full reference.'
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

All ratios are computed from unrounded inputs. Native/Generic pairs match model, host and cut. All split rows are compared to both measured Full alternatives on the same host, with winners and nonwinners retained. Table 2 reports TRT ranges across the three host aggregates; these ranges are not repeat confidence intervals. Host values and arithmetic means are separately available.

Recommended Table 3, `table3_fastest_deployments`, selects one split per model by the highest unrounded observed FPS cohort median across every measured setup and both Native and Generic runners. Its global Full reference is the fastest concrete Full configuration for that model across all measured hosts. Each selected Full remains one measured UID; host-specific TensorRT Fulls are not averaged before selection. The table reports throughput and energy from these exact two configurations. Global fastest asks for the strongest observed deployment alternative when setup choice is open.

The companion table `fastest_split_baselines` retains exactly the same selected split UID and adds the fastest Full on that split's normalized physical host. Same-host asks how that selected split compares with the available Full alternatives on its own host. It does not choose a new split by relative gain. For b in {{global, host}}, R_b=FPS(split)/FPS(Full_b), G_b=E(Full_b)/E(split), and delta_E_b_pct=100*(E(split)/E(Full_b)-1). Energy is taken from the exact Full selected by FPS, never from a separately energy-minimizing Full. R_b>1 indicates higher split throughput; G_b>1 and negative delta_E_b_pct indicate lower split energy. Where both denominators exist, R_global<=R_host because the same-host Full is among the global candidates. Equal denominator UIDs produce equal ratios.

Only finite, strictly positive FPS observations are selection candidates. Exact ties use ascending UID without a rounding tolerance; model order follows the configuration. Missing energy leaves the FPS winner selected and its energy fields missing. Missing split or Full candidates and unavailable ratios are explicit in the exports. Selection does not use an accuracy, claim or energy veto. CSV/JSON retain all selected UIDs, source records, quality values, classes, runtime/endpoints and restriction flags. Display alone rounds FPS to integers, factors and mJ/image to two decimals, and percentage energy changes to one decimal.

The separate supplementary `table3_top2_native` retains the historical selection method and its numerical results: two Native splits per model with the largest relative FPS gain over the fastest Full on the same host. That method can select a different split from the absolute fastest selection. Its G_n=E(Full)/E(split) still uses the exact Full chosen for its own speedup. Energy never changes either FPS ranking. The independently lowest-energy Full remains a separate export.

Point-pooled summaries are separate from equal-model summaries. The latter first take the point median within each model/setup, then average setups within each model, then average those model values. Classifiers with many cuts therefore receive no extra model weight. Fastest and lowest-energy splits are also selected within each model/setup/runner in the separate group-optimum analysis. Shared optima are one configuration; groups with a single candidate are distinguished from multiple-candidate groups. All optimum and Top-2 selections are retrospective over the finite measured candidate space. They do not establish a general hardware limit, matched quality, a prediction or a causal splitting effect. Small differences are not significance tests, and no confidence interval for a selected maximum is invented.

## Fastest-deployment overview figures

`fastest_split_baseline_comparison` plots R_global and R_host for the same split UID selected in both tables. A thin connection joins only the two denominator choices in one model row; it is neither a time series nor a measured optimization step. The linear ratio axis and reference at one retain observations below one. Absolute FPS remain in the tables.

`fastest_deployment_tradeoff` plots one selected split per model at x=R_global and y=E(split)/E(global Full). Both coordinates use the same concrete global Full UID from Table 3. Right of one means faster and below one means less host-inclusive energy per image. Missing coordinates are recorded rather than replaced or selected around. Labels may move for readability; data coordinates do not. These are throughput-selected configurations, not a complete Pareto front or a minimum-energy selection. Neither quadrant position nor marker color asserts quality PASS, equal endpoint work, equal parallelism or causal efficiency. The full observed-space Pareto views remain separate.

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
    if current:
        captures = s['current_external_captures']
        intro = (f"# Methods: current deployment observations\n\n"
                 f"The established selection contains {s['cases']} deployments ({s['native']} Native and {s['generic']} Generic), "
                 f"including {s['full_coverage']['configurations']} host-specific Full configurations. "
                 f"The source-bound current input admits {len(current['accepted_packages'])}/{len(current['expected_packages'])} declared measurement packages. "
                 f"These comprise {captures['performance']} new performance cohorts, {captures['quality']} new quality evaluations and "
                 f"{captures['energy']} new energy cohorts; reused observations remain explicitly identified. "
                 "Original input rows and replaced observations remain archived in data/current_observation_history.json. "
                 "Only declared, normally admitted metrics change; Full measurements and the literal b066 records are retained. "
                 "This offline generator performs no hardware measurement, model build or dataset evaluation.\n\n"
                 "Unchanged DeepX Native A4 observations retain their recorded batch-one, single-engine regime, at most four outstanding jobs, "
                 "FIFO depth three and serial TensorRT completion. Current replacements and the added Generic deployment retain their own "
                 "runtime, quality and source epochs. The broad RQ1 dataset retains unchanged Generic FPS/energy generations separately "
                 "from the current Generic FPS used by RQ2. These observed deployment comparisons do not isolate a causal effect "
                 "of splitting at equal executed work or parallelism. Own metric admission and Full-baseline comparison "
                 "authority are reported separately in the retained normal source records.\n\n")
        methods = intro + '## Selection and coverage\n\n' + methods.split('## Selection and coverage\n\n', 1)[1]
        methods = methods.replace('No such fallback is needed for the current complete FPS/energy matrix.',
            'Replacing FPS clears prior energy unless the normal source binds energy to that exact performance observation. Missing current energy remains unavailable.')
        start = methods.index('All 36 Native detector split configurations')
        end = methods.index('\n\nOther recorded completion modes', start)
        methods = methods[:start] + ('Completion mode, oracle placement, prepared inputs and endpoint contracts remain explicit per observation. '
            'The declared current Native quality replacements evaluate actual timed completion records; earlier quality evaluations '
            'with additional NMS remain archived and do not establish the current timed endpoint quality. Unchanged A4 and Full '
            'observations retain their recorded oracle, host-tail or integrated normalization scope. No blanket equality of executed '
            'work or cross-backend endpoint equivalence is inferred from an administrative hash or numerical quality value.') + methods[end:]
    (out/'METHODS.md').write_text(methods)
    findings = f'''# Findings from the broad Native A4 selection

This report is generated from the same selected rows as Tables 2/3 and all figures. {s['cases']} identities provide {s['performance_coverage']} FPS and {s['energy_coverage']} energy observations, including all {s['full_coverage']['configurations']} Full deployments. Numeric dataset quality covers {s['quality_numeric_coverage']} identities. No measurement or quality evaluation was started by this analysis.

Native exceeds Generic throughput in {ng['faster']}/{ng['n_performance']} paired points and uses less raw energy in {ng['energy_lower']}/{ng['n_energy']}; {ng['both_better']}/{ng['n_joint']} improve both. The point-pooled median Native/Generic ratios are {ng['fps_ratio_median']:.4f} for throughput and {ng['energy_ratio_median']:.4f} for energy. Separate equal-model results in `tables/equal_model_summary.json` avoid weighting models by their number of cuts.

Recommended Table 3 compares each model's global fastest observed Full with its global fastest observed split, selected across both runners and all setups. {global_faster}/{len(global_compared)} selected splits exceed the global Full's throughput; {global_both}/{len(joint_compared)} are both faster and lower in energy per image. The companion baseline table uses those exact same split UIDs with the same-host Full as a second denominator; {denominator_changed}/{len(fastest)} rows use different Full UIDs for the two baselines. {slower_description} Counts use only the available ratios; missing candidates or metrics remain explicit in the tables. Both new figures use these same unrounded selections and denominators.

Across the separate full set of Native splits, {fc['faster']}/{fc['splits']} are faster than the fastest Full on the same host. Against the separately selected minimum-energy Full, {ec['lower']}/{ec['splits']} use less energy. The largest relative same-host speedup is {best['speedup']:.3f}x for {best['model']} {best['setup']}/{best['case']}; its energy gain against that exact same Full is {best['energy_gain_same_full']:.3f}. The supplementary `table3_top2_native` retains two Native splits per model selected by this relative same-host gain. It is the historical selection method, distinct from the absolute fastest selection in the new Table 3. These are retrospective results over the measured candidate space.

The fastest and minimum-energy Native split differ in {opt['multi_candidate_conflicts']}/{opt['multi_candidate_groups']} groups with more than one candidate. Shared optima and the candidate counts are shown explicitly. A small ratio above one is described as a small observed advantage; the analysis does not infer statistical significance from it.

Quality is a separate result axis. The original {s['quality_loss'].get('native',0)} Native and {s['quality_loss'].get('generic',0)} Generic accuracy-loss flags remain visible. Vendor Full quality, model reference quality and every available split score appear in the quality figures. {len(mismatches)} cached Current losses differ from the numerical selected quality reports; both are retained. The Full and split figures display actual deployments with their quality and timed-work differences, including the YOLO26s fast-oracle versus host-tail distinction described in `METHODS.md`.

See [Table 2](tables/table2_full.md), [recommended Table 3: global fastest deployments](tables/table3_fastest_deployments.md), [same split with two Full baselines](tables/fastest_split_baselines.md), [supplementary relative same-host Top-2](tables/table3_top2_native.md), [methods](METHODS.md), [figure captions](CAPTIONS.md), and [all machine-readable findings](data/summary.json). Missing values, if any, are enumerated by UID in `data/summary.json`. Historical source-version and clock-profile limitations remain; these do not trigger a new measurement campaign.
'''
    if current:
        findings = findings.replace('# Findings from the broad Native A4 selection', '# Findings from the current deployment selection')
        findings = findings.replace('The original ', 'The recorded ')
    (out/'FINDINGS.md').write_text(findings)
    # Source paragraphs are supplied separately from any private manuscript.
    paragraph = ('We report the broad measured deployment selection, retaining quality-loss, single-repeat and screening observations with their original flags. '
                 'Throughput is the recorded cohort median in images/s. Energy is calibrated host-inclusive energy per completed image, averaged as the mean of per-repeat E/N and displayed in mJ/image. '
                 'Dataset Top-1 accuracy or COCO mAP is reused from the selected existing evidence and shown separately. '
                 'Table 3 selects the highest unrounded FPS split across all setups and both runners and compares it with the highest FPS concrete Full configuration across all hosts. Each configuration retains its own measured energy. '
                 'A companion table retains the identical selected split and adds the fastest Full on its physical host; the separate historical Top-2 method ranks Native splits by relative same-host speedup. Exact ties use ascending UID; energy and quality do not veto throughput selection. '
                 'For either Full baseline, R=FPS(split)/FPS(Full), G=E(Full)/E(split), and the percentage energy change is 100*(E(split)/E(Full)-1). Missing energy leaves the FPS selection intact. '
                 'The baseline figure shows the same split under these two denominators. The deployment overview uses R and E(split)/E(global Full) for the exact global Full UID; it is not the full Pareto front or a minimum-energy selection. All selections are retrospective over the finite observed candidates, not general hardware limits or significance tests. '
                 'Source generations and numerical quality/cache discrepancies are recorded per metric. '
                 'Empirical performance--energy fronts maximize throughput and minimize host-inclusive energy within each model/setup, including both Full alternatives; quality is shown by color and is not a dominance objective. '
                 'The 75 updated Native DeepX observations use batch-one, single-engine A4 with at most four outstanding jobs; splits use FIFO depth three and a serial TensorRT consumer through task completion. The other 375 direct observations and all 450 selected dataset-quality observations are retained. '
                 'Native detector splits record a correctness oracle outside timing, whereas Generic detector splits record decoded NMS; Full paths retain their recorded host-tail or integrated normalization work. These ratios compare observed deployments with their recorded parallelism and do not isolate a causal effect of splitting at identical work.')
    if current:
        paragraph = paragraph.replace('Dataset Top-1 accuracy or COCO mAP is reused from the selected existing evidence and shown separately.',
            'Dataset Top-1 accuracy or COCO AP50-95 comes from the selected own quality evidence, including explicitly declared new evaluations; prior values and bootstrap statistics remain archived.')
        begin = paragraph.index('The 75 updated Native DeepX observations')
        paragraph = paragraph[:begin] + ('Unchanged A4 observations retain their recorded runtime regime. Only declared current metrics are '
            'replaced by normally admitted sources; prior observations remain archived. Fulls and literal b066 are unchanged. '
            'Current Generic FPS does not inherit energy from a different performance observation. Completion and oracle placement '
            'remain explicit per identity, and current Native quality replacements evaluate their actual timed outputs. '
            'The comparisons retain their recorded work and parallelism and do not establish a causal splitting effect at identical work.')
    (out/'METHODS_PARAGRAPH.tex').write_text(tex(paragraph)+'\n')
    render_gallery(out, s, fastest)
    if current:
        native_splits = sum(row['runner']=='native' and row['kind']=='split' for row in data)
        generic_splits = sum(row['runner']=='generic' and row['kind']=='split' for row in data)
        (out/'README.md').write_text(
            '# Split inference: performance, energy and quality\n\n'
            f"{s['cases']} observed deployments cover {len(fastest)} models, with {native_splits} Native splits, "
            f"{generic_splits} Generic splits and {s['full_coverage']['configurations']} host-specific Full configurations. "
            f"The current inputs admit {len(current['accepted_packages'])}/{len(current['expected_packages'])} declared measurement packages. "
            f"Measured coverage is {s['performance_coverage']}/{s['cases']} FPS, {s['energy_coverage']}/{s['cases']} energy and "
            f"{s['quality_numeric_coverage']}/{s['cases']} numerical quality observations. Missing metrics remain unavailable.\n\n"
            '[Figures](figures/README.md) · [Tables](tables/README.md) · [Complete dataset](data/PAPER_DATASET.csv) · '
            '[Findings](FINDINGS.md) · [Methods](METHODS.md)\n\n'
            'The fastest-deployment tables select one split across Native and Generic runners and all measured setups, '
            'with the runner and exact source UID retained. Global and same-host Full references use the same selected split. '
            'Energy belongs to its exact performance observation; replacing FPS clears incompatible prior energy. '
            'The [source table](data/METRIC_SOURCES.csv), [measurement generations](data/MEASUREMENT_GENERATIONS.csv) and '
            '[replacement history](data/current_observation_history.json) retain the old and current observations. '
            'Full measurements and the literal b066 records are unchanged.\n\n'
            'Unchanged Generic FPS/energy generations in this broad dataset remain separate from the current Generic FPS '
            'used by [RQ2](../supplementary-studies/rq2-native-scope-20261027/README.md). '
            'Quality uses Top-1 accuracy for classifiers and COCO AP@[.50:.05:.95] for detectors; current Native quality '
            'replacements evaluate their actual timed completion records. Source-specific runtime, quality and comparison '
            'authority remain visible in the data.\n\n'
            'Reproduce with the [offline instructions](../../scripts/split-inference/README.md). '
            'The generator performs no hardware measurement, compilation or dataset evaluation.\n')

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    render(p.parse_args().output)
