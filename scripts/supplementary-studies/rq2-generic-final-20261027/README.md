# Current Generic / existing Native adapter

This offline adapter joins the immutable 420-cell Generic projection to the
existing Native measurements using the public original graph binding audit.
It verifies model and device identities, graph frontier, P1 and consumer engine
hashes, input identities, recorded precision and the Native measurement source.
Unknown Native precision strings stay null. Where the original audited runtime
and exact same build/engine establish equivalence, that executable relation is
recorded separately; no missing precision string is invented.

```bash
python scripts/supplementary-studies/rq2-generic-final-20261027/reproduce.py \
  --output /tmp/current-rq2-reproduction --verify
python -m unittest discover -s scripts/supplementary-studies/rq2-generic-final-20261027
```

The numerical path needs only Python's standard library. Rendering uses the
maintained split-inference Matplotlib environment and paper style. Use
`--numeric-only` to omit images. The reproducible compact input is committed;
no private filesystem or accelerator access is needed.

`export_inputs.py --ledger <immutable-ledger> --output <new-json>` reproduces
the portable projection when the original ledger is available. It retains
source hashes and selectors and discards local paths and large payloads.

The adapter was checked against the newer local v3.3 paper adapters and the
subsequent classifier420 package. Their source-preservation, explicit cohort
and no-imputation rules are retained. The prior public graph weights and full
normalization universes are replayed unchanged. No new model fit, Native
measurement, quality admission or energy measurement is performed.

Pass the generated study directory to the paper/dissertation entry points with
`--rq2-study <study-directory>`. The R30 profile independently reproduces and
verifies the supplied study, replaces current RQ2 assets, and verifies that all
unrelated RQ1 and YOLOv7 numerical values remain identical.
