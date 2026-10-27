# Split-selection results

This study evaluates split deployment benefits, selection with a universal runner, and graph-based selection before measurement.

The paired comparison contains 187 quality-admissible cuts in 21 model–device groups. The graph comparison uses 331 quality-admissible Generic cuts in 21 groups.

| Result | Figures and tables |
|---|---|
| Split benefits and paired runner selection | [Paper assets](paper/publications/mlsys-r30/) |
| Graph-selected shortlists | [English artifacts](paper/rq3-generic420/en/) |
| German dissertation artifacts | [German collection](dissertation-de/README.md) |

Reproduce the entire study from the repository root:

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

Use a fresh output directory. Verification is enabled for every build. CSV and JSON files contain the unrounded values. Input manifests retain the measurement sources.
