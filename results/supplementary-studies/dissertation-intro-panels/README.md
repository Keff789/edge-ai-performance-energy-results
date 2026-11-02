# Standalone hardware and runtime illustrations

The three panels reuse the author-supplied editable MLSys Figure 1. The original paper figure is unchanged. Each standalone panel has a matching English/German export and no panel letter or internal figure heading.

| Panel | Natural width | Files |
|---|---:|---|
| urecs_modular_hardware | 3.0 in | [EN PDF](artifacts/en/figures/urecs_modular_hardware.pdf) · [DE PDF](artifacts/de/figures/urecs_modular_hardware.pdf) |
| accelerator_gpu_execution | 4.9 in | [EN PDF](artifacts/en/figures/accelerator_gpu_execution.pdf) · [DE PDF](artifacts/de/figures/accelerator_gpu_execution.pdf) |
| runner_interfaces | 4.9 in | [EN PDF](artifacts/en/figures/runner_interfaces.pdf) · [DE PDF](artifacts/de/figures/runner_interfaces.pdf) |

The SVG source retains the original vector geometry and references the original photograph in a separate lossless PNG. Exports encode that photograph as JPEG at quality 95 without resampling; annotations remain vectors. German labels are translated locally, including one line break for prepared input. The hardware overlays indicate module locations on an unpopulated carrier.

```sh
python3 scripts/dissertation/intro_panels.py --output local-output/intro-panels --languages en de
```

Only the finished PDFs are needed by the dissertation. Source files and this generator stay in the Results repository.
