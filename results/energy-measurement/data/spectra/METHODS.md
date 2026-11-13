# Journal spectral comparison — numerical and evidence contract

Tool release: 0.9.0. This is a separate extension of the completed v0.8.2 pipeline.
The frozen PARMA results, scope algorithms and Common-Reference matrices are not
modified by a journal-only run.

## 1. Native source, not the Common-Reference cache

For Jetson, the reader uses `psd/per_workload/<id>/cross_workload_psd_summary.npz`
and `psd_metrics.json` from the actual generated multi-workload configuration.
Those arrays already contain **Tek AND Pico**, current AND estimated power, and
active, idle and positive excess densities. The default accepted rate is 5 MS/s
and the reader verifies coverage from DC through 2.5 MHz. It does not substitute
the 1-MS/s, anti-aliased Common-Reference cache.

Missing/corrupt/mismatched aggregate files are documented and skipped. The journal
command never silently starts a full legacy scope or Common-Reference rebuild.
Existing aggregate signatures and file identities are retained in the report;
the reader does not re-validate every original Parquet file. Run the normal
upstream pipeline first when acquisition data have changed.

## 2. What is plotted

Let S(f) denote a nonnegative PSD in A²/Hz or W²/Hz. Its integral is a variance,
not energy in joules. The plotted cumulative fraction is

    C(f) = integral(0..f, S) / integral(0..Nyquist, S).

Every setup has its own denominator. Therefore a filter that reduces high-band
variance also changes the apparent percentage in the low band. The extension
reports a second **conditional CDF normalised only over 0–77 kHz**, so this
normalisation effect is distinguishable from changes in low-band shape.

The 77-kHz line is a nominal installed analogue-bandwidth marker, not a hard
cutoff, a noise threshold or an independently validated passband. Spectra retain
all available bins up to the native Nyquist limit. No deconvolution is applied.

The PSD view uses 10 log10(S / integral(S)) in dB relative to 1/Hz. Absolute PSD
views are explicitly labelled dB relative to 1 A²/Hz or 1 W²/Hz. A display floor
120 dB below each peak is only a plotting convention. Integrals and percentile
metrics use unchanged linear densities. The linear fine-structure ordinate is
normalised variance density in percent per kHz.

Band integrals insert exact interpolated edge coordinates. Full-resolution
values are used for tables. Thinned CSVs preserve local peaks for review/plotting;
they are not a replacement for full-resolution arrays in a numerical reanalysis.

## 3. Setup comparison

The full-band and conditional CDF differences are reported in **percentage
points**. They are not energy errors. Absolute variance ratios are ratios of PSD
integrals. Log-bin ratio plots integrate both PSDs over the same logarithmic bins
before dividing. Bins contributing at most 1e-10 of either setup's total are
suppressed as a relative numerical relevance gate, not as a calibrated noise
criterion.

No transfer function, coherence, certified bandwidth or independent absolute
measurement accuracy can be inferred from these aggregate PSD ratios alone.
Existing offset handling is preserved; no new gain or offset fit is performed.
In particular, a constant current offset vanishes on centring a **current** signal,
but this is not an exact invariance for a nonlinear current-to-power model.

Tables distinguish:
- percentiles of the plotted pointwise-median PSD (`*_curve_hz`);
- medians and empirical 5th–95th percentiles of per-physical-run metrics.

These quantities need not be equal. Per-run intervals are not confidence
intervals. Workload rank correlations are descriptive and have a small sample
of workloads; no population-level inference or automatic pass/fail claim is made.

## 4. Hailo / legacy oscilloscope.npy adapter

The discovered tree is `hailo_sweep/<workload>[/<precision>]/<rate>/<run>/`.
Only native `5000000Sps` or `5000000` directories are analysed by default. Empty,
invalid, temporary and incomplete observations are not used. Every accepted run
needs `oscilloscope.npy` and `results.yaml` with the acquisition suite's
`oscilloscope_results.sample_rate` and `results.{start_stop_idx,duration,energy}`.
The end index is inclusive. The rate, window, numeric 1-D array, finite samples
and duration are checked. Both rectangle and trapezoid integration are compared
to the saved energy; at least one must agree within the configured tolerance.
This is an **internal consistency check**, not independent physical calibration.

The configuration declares the input as stored **power in watts**. We do not
multiply it by a Pico calibration a second time, infer current from it, or apply
the Jetson U(I) model to Hailo. Conflicting explicit units are rejected.

Each accepted run produces a full active-window spectrum and, when long enough,
a spectrum of the first 10 s of the YAML active window. They stay separate. Idle
is taken only from the same recording before the active start, with a configured
guard. A missing/too-short/nonfinite prefix is not replaced with Jetson idle or a
zero spectrum: the run remains active-only. Excess aggregates use only the cohort
with valid own-record idle. The cohort size is stated separately.

All complete Welch segments of the selected interval are used; unused trailing
samples are recorded and still included in finite-value and energy checks. A
memory-mapped NPY is read sequentially. Welch is evaluated in bounded blocks with
exactly the same complete segment boundaries and weighting as a single SciPy call.
No physical recordings are concatenated. One PSD per physical run has equal
weight in the cross-run median; a longer record merely supplies more within-run
Welch averages.

Default new NPY spectral parameters:

    native fs = 5,000,000 S/s
    nperseg = 1,048,576
    noverlap = 524,288
    window = Hann
    detrend = constant, per Welch segment
    scaling = density, one-sided
    average = mean within a physical run

These agree with the existing typical 10-s / 5-MS/s multi-workload estimator.
The implementation is numerically tested against a monolithic SciPy Welch call
for irregular chunk sizes, including finite checks of unused tails.

## 5. Cross-platform scope

Jetson/Pico estimated-power PSDs and Hailo stored-power PSDs can be plotted in the
same units. Full records with different durations are explicitly exploratory.
A duration-matched plot is produced only when the actual upstream Jetson pair
metadata confirms the requested duration and the Hailo prefix exists.

Duration matching does NOT establish matching model, numeric precision,
stationarity, batch size, host contribution, measurement boundary or analogue
setup response. Unknown fields remain `unspecified`. The Hailo setup match is a
user-reported premise, not a newly measured calibration. No energy-efficiency
ranking or hardware-causal spectral claim is generated automatically.

## 6. Reuse, isolation and packaging

New per-run NPY spectra are cached only under `journal_artifacts/cache/`, keyed by
input stat identity, YAML content and journal numerical settings. They are
reused on an unchanged second run. Changes to labels or plotting settings do not
invalidate those spectral caches. A journal-only force option affects only these
new caches. A global journal lock prevents two writers from running concurrently.

Artefacts are generated in a staging directory, inventories are checked, and the
compact bundle is replaced only after generation succeeds. The bundle contains
exact tables, figures, source metadata and sampled review curves; raw NPY/Parquet
and full-resolution NPZs are intentionally excluded. It is a review bundle, not
a self-contained raw-data regeneration archive. The inventory describes precisely
the included files (excluding itself). Strict JSON uses null instead of NaN/Inf.

The normal auto pipeline invokes the separate journal stage after its existing
stages. A compatible legacy cache-version token and byte-identical analysis
configuration reference are preserved to avoid installation-path/version-only
invalidations. Existing input/configuration changes still invalidate normally.
The safest first extension run is `COMMONREF_JOURNAL_ONLY=1 ./run_auto_pipeline.sh`:
this bypasses all legacy analysis and artifact stages entirely.

## Primary API documentation

- SciPy 1.13.1 `scipy.signal.welch`: https://docs.scipy.org/doc/scipy-1.13.1/reference/generated/scipy.signal.welch.html
- NumPy 1.26 `numpy.load` (read-only memory mapping and allow_pickle=False): https://numpy.org/doc/1.26/reference/generated/numpy.load.html

Dependency pins remain those of v0.8.2; this release adds no runtime dependency.
