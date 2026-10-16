# Historical GEMM-FP16 inputs: 13 reference recordings

These completed outputs come from `gemm_fp16_common_reference_psd_v3`, with an analysis manifest dated 9 August 2026. They retain primary run IDs 2–14; runs 0 and 1 were excluded before that historical common-trace analysis. The current main analysis uses all 15 recordings and matched four-second spectral windows and remains separate.

| Input | Role |
|---|---|
| [common_trace_raw.csv](common_trace_raw.csv) | 16,159 previously reconstructed run/phase outcomes; joules and signed/absolute relative error in percent. Re-aggregation produces 49 mode/rate groups. |
| [real_measurements_raw.csv](real_measurements_raw.csv) | 351 independent-acquisition outcomes, 13 per tested rate; joules, reported rates in S/s and error against the fixed 5-MS/s median. |
| [variance_capture_per_run.csv](variance_capture_per_run.csv) | 351 previously integrated spectral outcomes; fraction and percentage below each tested Nyquist frequency. |
| [psd_plot_samples.npz](psd_plot_samples.npz) | 38,088 exact selected bins from the original 500,001-bin aggregate; active median/Q10/Q90, idle median and cumulative median/Q10/Q90. |
| [metadata.json](metadata.json) | Cohort, source identity, window definitions, frequency selection and units. |

PSD ordinates are W²/Hz. The frequency column is in Hz; cumulative columns are dimensionless. Figures use 10 log10 of PSD relative to 1 W²/Hz. The original one-second Hann Welch segments have 50% overlap, with ten-second active and four-second pre-benchmark idle windows at a 1-MS/s representation. Idle ends 0.5 s before the benchmark. The input is calibrated derived power, rather than separately available voltage and current channels.

For each recording the original analysis integrated `max(active PSD - idle PSD, 0)` over the full frequency grid and normalized it before across-record quantiles. The compact export retains the original plot selector's samples, every bin through 5 kHz and both original bins bracketing the median cumulative 95%/99% crossings. It contains no interpolated PSD observations. Do not reintegrate these sparse plotting curves to replace the per-run coverage inputs. A crossing of the median cumulative curve need not equal the median of per-run crossing frequencies.

The [historical gallery](../../galleries/historical-fp16.md) links generated CSV/Markdown summaries and PDF/SVG/PNG views. Reproduction re-aggregates the exported energy and coverage outcomes; spectral curves are already aggregated historical inputs. It does not redo Welch estimation, raw-signal reconstruction, calibration or acquisition. Existing [source rights and notices](../../RIGHTS_AND_NOTICES.md) apply.
