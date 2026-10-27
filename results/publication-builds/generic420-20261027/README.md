# Split-selection results

This study evaluates split deployment benefits, selection with a universal runner, and graph-based selection before measurement.

The study selects 420 candidate splits: twenty per model and accelerator. Of these, 359 have throughput and quality measurements, 61 have technical exclusions, and 28 measured candidates exceed the 5% relative quality-loss limit. The remaining 331 candidates support graph-score evaluation.

The paired runner comparison contains 204 compatible cuts: 192 from that pool and 12 additional single-input cuts. It retains 187 quality-admissible pairs in 21 model–device groups. The deployment comparison includes 42 host-specific Full alternatives. The three analyses connect graph preselection, Generic testing and final Native selection.

| Result | Figures and tables |
|---|---|
| Split benefits and paired runner selection | [Paper assets](paper/publications/mlsys-r30/) |
| Graph-selected shortlists | [English artifacts](paper/rq3-generic420/en/) |
| Graph–Generic–Native selection | [Workflow, budget curves and tables](staged-selection/artifacts/en/) |
| German dissertation artifacts | [German collection](dissertation-de/README.md) |

Reproduce the entire study from the repository root:

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

Use a fresh output directory. Verification is enabled for every build. CSV and JSON files contain the unrounded values. Input manifests retain the measurement sources.
