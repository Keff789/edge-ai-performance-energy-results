# Reproduce the current results

The current split-inference analysis has one entry point for the runner comparison, graph-score evaluation, and English/German publication outputs. It uses the supplied measurements and does not start hardware acquisition.

## Setup

Use Python 3.12 and install the pinned dependencies in a virtual environment. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r scripts/split-inference/requirements-r30.txt -r scripts/supplementary-studies/rq3-generic420/requirements.txt
```

Activate the environment, then generate the current outputs:

```sh
. .venv/bin/activate
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

Use a fresh output directory. The command reconstructs the current RQ2 and RQ3 analyses and feeds both into the publication generators. It also replays the graph–Generic–Native selection procedure on the resulting paired set, writing bilingual budget figures and tables to `staged-selection/artifacts/`. It keeps the measured Full/split throughput and energy values used by RQ1. The outputs include numerical tables, figures and their source references.

The English and German outputs use identical numerical inputs. Models, datasets and accelerator hardware are not required for this offline reproduction. Detailed configuration-level methods are documented with the [runner-selection inputs](../results/supplementary-studies/rq2-native-scope-20261027/README.md) and [graph-selection inputs](../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/README.md).

The build also writes `boundary-performance/artifacts/{en,de}/`: aligned YOLOv7/Hailo-8 plots of measured throughput, logical boundary tensor size, and graph-estimated prefix/suffix compute. The two lower panels cover all graph boundaries; the upper panel shows only measured cuts. The [standalone generator](split-inference/boundary_performance.py) can regenerate this figure without rebuilding the other artifacts. Its [published output](../results/supplementary-studies/boundary-performance/README.md) includes the numerical plot data and source hashes.

`dissertation-intro-panels/artifacts/{en,de}/` contains separate hardware, execution-path, and runner-interface figures from the editable MLSys overview. [Regenerate these panels](dissertation/intro_panels.py) without rebuilding numerical results: `python3 scripts/dissertation/intro_panels.py --output local-output/intro-panels --languages en de`. The author SVG and original board photo are retained under `publications/dissertation/intro-panels/source/`.

## Other analyses

| Area | Instructions |
|---|---|
| Energy measurement | [Signal processing, calibration and measurement comparisons](../results/energy-measurement/README.md) |
| Independent stage-cost composition | [Stage capacities and pipeline predictions](supplementary-studies/stage-cost-composition/README.md) |
| Hailo-10H format measurements | [Measurement sources and hardware requirements](hardware/hailo10/README.md) |
| Earlier publication profiles and studies | [Research archive](../docs/archival_studies.md) |

The individual generator scripts remain available for targeted work. The unified command above is the normal entry point for the current paper and dissertation figures and tables.
