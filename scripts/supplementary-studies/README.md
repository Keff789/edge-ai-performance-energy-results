# Supplementary analysis scripts

The [all-cut RQ2 evaluator](rq2-all-cuts-20261020/README.md) reproduces complete
rankings, loss curves and exact/near-optimal Native success budgets from existing
canonical inputs. It keeps the graph-rule and current Native measurement
campaigns separate, preserves the frozen R22 profile, and generates the new
English publication figures. Numerical-only mode and published-file verification
are available through the same entry point.

The [v49 confirmation evaluator](thesis-v49-confirmation-20261019/README.md) reproduces the separately dated R3 throughput, conditional-energy and paired-quality tables from compact inputs. It preserves seventy primary throughput rows, sixty-eight primary energy records and two distinct energy supplements; full raw-archive checks and physical measurement-chain qualification remain separate.

The [historical split-selection package](../../results/supplementary-studies/thesis20-ranking-20261005/README.md) includes its existing offline score, ranking and plotting scripts with all compact inputs. From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python results/supplementary-studies/thesis20-ranking-20261005/scripts/reproduce_methods.py --output-root /tmp/thesis20-ranking-reproduced
```

Choose a fresh output directory. NumPy and Matplotlib are required; the current split-analysis environment is sufficient for numerical reproduction. Original rendering used Matplotlib 3.5.2.

The [Hailo-8 HAR comparison](../../results/supplementary-studies/hailo8-har-20260912/README.md) retains the original comparison helper. Its complete array-level calculation needs external bound arrays and metadata; compact results alone do not reconstruct the logits. No collector or publication launcher is included.

The [historical YOLOv7 completion package](../../results/supplementary-studies/yolov7-completion-20261007/README.md) includes its standard-library report extractor. It reproduces 15 reported performance rows and checks their arithmetic from the bundled report:

```bash
PYTHONDONTWRITEBYTECODE=1 python results/supplementary-studies/yolov7-completion-20261007/extract_reported_results.py --output /tmp/yolov7-completion-reproduced
```

The [independent stage-cost evaluator](stage-cost-composition/README.md) reproduces six numerical exports from its compact 36-report cohort using Python’s standard library. It preserves the supplied inputs and verifies results in a fresh external output directory; hardware/array validation and PNG generation are outside this command.
