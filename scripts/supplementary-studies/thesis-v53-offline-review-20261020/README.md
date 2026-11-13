# Bounded v53 offline audit

From the repository root, use an existing Python >=3.10 environment:

```bash
python3 -I -B scripts/supplementary-studies/thesis-v53-offline-review-20261020/reproduce.py \
  --output ../v53-audit-check --verify
```

The output directory must be absent or empty and outside the repository. This
standard-library command checks compact provenance and the frozen canonical
inputs, runs the focused audit tests, generates the complete audit and requires
byte equality with the committed outputs. It does not fetch sources or run a
model, evaluator, bootstrap, raw-trace integration or hardware command.

The [study README](../../../results/supplementary-studies/thesis-v53-offline-review-20261020/README.md)
describes the exact graph scope, historical unit-sensitivity comparison,
remaining MobileNet source gap and the separately recorded A/B/C paths.
`report.py` generates the study README and English thesis insertion from the
same computed facts. `source_manifest.json` and `task_closeout.json` contain
source/code hashes, checks, limits and a dated Git receipt.

`capture_operator_sources.py` is a separate, bounded original-source capture
helper. It requires the explicit canonical archive, original ONNX files and
the existing ONNX environment recorded in the source bindings. It is not called
by normal reproduction. `binding.py --verify-originals` separately rechecks
only the indexed original hashes and projections when their original roots
are supplied; its CLI help describes the required arguments. Neither operation
establishes the still-missing historical process-to-evaluator binding.
