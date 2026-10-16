# Review inputs

The review uses the historical manuscript cohort and the later reported YOLOv7 Native overlay. The two YOLOv7 headline rows have reported quality labels only; numeric quality and matching new energy remain unavailable. No older AP or energy is attached to that implementation.

The source manifest retains the original calibration identities used by the energy records. Its `sha256` and `bytes` describe the original source files; `curated_sha256` and `curated_bytes` check the existing curated records linked here. Every fit value, stored quality gate, sample rate and timing field used by this analysis matches the manuscript source. Private paths and hardware logs are absent from the curated records. These are existing calibrations, with no new fitting. The original source digest is not the digest of the curated file.

The generated quality-tolerance sweep holds the Native-FPS-selected Full fixed across the 1%, 2% and 5% point-estimate thresholds. Both split and Full must pass the threshold and the local semantic condition. The longer-window comparison uses mean per-repeat N/T from the energy runs against the same Full identity. Existing windows are not a controlled duration or thermal experiment.
