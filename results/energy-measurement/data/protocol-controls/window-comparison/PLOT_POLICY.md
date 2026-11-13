# Result-only postpass v0.3.0

The frozen input is the completed v0.2.0 review, identified in sources.json. No NPY/Parquet read, no new detector, no changed calibration, no changes to the v0.2.0 cache.

## Quality and cohorts

- Parent envelope flags are inherited by interior windows.
- The previously declared >1% envelope sensitivity flags exclude new primary curves, not the archived candidates or reported legacy results.
- 105 unresolved LLM mismatches remain blocked for an unmarked new primary comparison. Original reported YAML values remain separately visible.
- Eight hash-bound, locally checked monotone-prefix results are imported as derived views. Exactly one terminal duplicate-power row was omitted per case; original arrays are unchanged. Positive gaps remain flagged.
- Main old/new window plots use matching eligible participants per series and x group. Interior plots can have fewer participants when their duration is insufficient; counts are retained.
- No physical-repetition percentile trimming, no cross-root pooling, no zero scatter asserted at n=1. Unclear or missing windows remain gaps.

## Measurement-device comparisons are INCLUDED

Pair by the same source series and record_id, with PicoScope as the comparison reference. Where present, include u.RECS, Shelly, Jetson telemetry and HailoRT. For each pair compute `100*(E_sensor/E_pico-1)`, analogous mean-power and duration ratios, THEN aggregate the pair ratios. Positive reference denominators are required. Report participant IDs, excluded pairs, duration differences and gap warnings.

These are paired observations using independently stored/detected windows: NOT hardware-synchronized sensor errors. Different physical boundaries, AC/DC supply components, telemetry smoothing and stored scaling can affect the ratios. No automatic Shelly correction, no gain fit from workloads, no inferred NVML series when absent.

A synchronized common-window instrument comparison requires separately justified time alignment and boundaries. Approximate capture pre/post timing does not establish it. The current outputs explicitly stop short of that claim.

## Figures

Native-rate energy boxplots, repetition spread, internal group-relative differences, separate energy/duration/power trends and measurement-path/static comparisons. PNG/PDF, optional SVG; one readable figure per metric. Historical figure register retained with output mappings. Synthetic 1/5/10/25-S/s points, PSD/common-reference, SINAD, calibration figures, photographs and schematics are not fabricated from result tables.

The original acquisition campaign remains the dataset. Full-spectrum reanalysis or a repeated hardware campaign is not required by this postpass.
