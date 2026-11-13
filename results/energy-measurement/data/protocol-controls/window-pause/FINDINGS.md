# Findings and limitations

Source IDs resolve through sources.json. These exported outcomes involve no new
measurement, raw-sample integration or calibration.

## Fixed versus unforced windows: same 45 stored traces

| Rate S/s | n | Median legacy E J | Median unforced E J | Median unforced span s | Unforced change vs 2 kS/s |
|---:|---:|---:|---:|---:|---:|
| 2000 | 15 | 3585.775574 | 3998.095334 | 111.198500 | 0.000000% |
| 250000 | 15 | 3599.480124 | 3942.563416 | 109.470708 | -1.388959% |
| 5000000 | 15 | 3708.508000 | 3679.184790 | 97.344281 | -7.976562% |

S04 / window_runs.csv. All 15 repetitions retained. The legacy high-rate difference
is +3.422758%, versus -7.976562% without forced duration. These are different windows,
not an 8% accuracy improvement. 2 kS/s is an internal comparator, not a reference
instrument. Largest old-energy reproduction difference: 5.603988029179163e-8 J.
Raw NPY integration occurred on the measurement host; this freeze preserves exports.
Energy, duration and power are separately aggregated; median(E)/median(T) need not
equal median(E/T). Unforced signal boundaries are not exact synchronized query markers.

## Analysis time changes the benchmark schedule

Actual order: 15 at 5 MS/s, then 15 at 250 kS/s, then 15 at 2 kS/s (S03/S06).

| Rate S/s | Median analysis s | Median prior process-end to next-start s | Median TRT trace s |
|---:|---:|---:|---:|
| 5000000 | 101.322 | 121.196 | 97.4798 |
| 250000 | 5.458 | 21.614 | 109.554 |
| 2000 | 0.072 | 16.172 | 111.334 |

All 45 timing traces report 100 queries, one warm-up query, PASSED and exit 0;
there is one additional unscored dry-run. The first 250-kS/s run retains a long
preceding pause and takes 97.632 s, whereas run 7 at the same rate takes 109.765 s.
The benchmark itself changes duration, not just the Pico integration result.
Rate, session order and prior pause were not independently randomized.
Process gaps are not proof of complete electrical idle.

The middle-rate collector log reports 249999 rather than 250000 S/s. Its rounded
integer does not establish the actual sample interval and cannot explain the
multi-percent endpoint trend. No automatic timebase correction is applied.

## Targeted pause test: unchanged 2 kS/s

One continuous legacy-Pico capture; one conditioner, then pauses
20, 120, 120, 20, 20, 120 s. No inline analysis or repeated device opening between
processes. Telemetry is a deliberate protocol addition (S05/S07).

| Median of three scored runs | 20-s pause | 120-s pause | Long vs short |
|---|---:|---:|---:|
| TRT timing-trace s | 105.302 | 96.1504 | -8.691% |
| Signal-envelope E J | 3836.719262 | 3646.686735 | -4.953% |
| Interior P W, 10 s trimmed each side | 36.109712 | 38.168160 | +5.701% |

Short-pause GPU start temperatures: approximately 72.5–76.0 C; long-pause starts:
58.2–59.0 C. Start temperature is the median of the final five seconds before process
start. Every long-pause run is faster than every short-pause run, including the last
long-pause run after two short ones. Ten successive groups of ten queries show
slowing within each run, earlier and larger after short pauses.

**Counterevidence retained:** all 1147 Sysfs rows show 1173 MHz GPU cur_freq and
1984 MHz CPU scaling_cur_freq. No decrease in those readouts was observed. Fan,
EMC, thermal trip/cooling states and OC/throttle counters were not captured.
No particular 95-C threshold or hardware-throttling mechanism is proven.
Tegrastats VDD_IN shows the same power direction (+4.904%) in a separately defined
process-interior window, not an absolute calibration.

Waiting energy is excluded from envelope energy: this is not a claim that longer
waits reduce the energy of the complete schedule. Current NvGpu scaling at the
Jetson remains electrically unvalidated. The 0.4/0.5/0.6 detector thresholds give
-4.961/-4.953/-5.025% respectively; the sign survives this limited sensitivity check.
The original Parquet was excluded from the review. Bin consistency is not another
integration of the raw channel values.

## Scope for the paper

Software-induced pauses, independently logged timing changes and window sensitivity
identify a substantial confound of direct rate sweeps. They do not prove a common
cause for every historical dataset or exclude all acquisition errors. One session
with three scored repeats per pause is diagnostic evidence, not a population-level
randomized causal trial. Retain all original records; no universal -5%/-8% correction,
no invented temperature normalization and no removal of inconvenient repetitions.
