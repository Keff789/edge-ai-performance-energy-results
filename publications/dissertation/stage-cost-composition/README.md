# Stage-cost composition: dissertation module

The [English section](section_stage_costs.tex) and [standalone preview](preview.pdf) prepare the completed `stage_cost_composition_20261014` experiment (source export `20261014T102852Z`) for later dissertation integration. Choose its location within the current dissertation when integrating it; no complete dissertation or chapter numbering has been changed.

The [shared study](../../../results/supplementary-studies/stage-cost-composition/README.md) provides the results, methods and numerical/figure reproduction. The section loads the generated vector [stage-cost figure](../../../results/supplementary-studies/stage-cost-composition/figures/stage_costs.pdf) and [LaTeX table](../../../results/supplementary-studies/stage-cost-composition/tables/stage_cost_table.tex) directly from that study. The second generated figure, [prediction versus observation](../../../results/supplementary-studies/stage-cost-composition/figures/prediction_observation.pdf), is also available there. These assets are stored only once.

The test composes independently measured capacities of four known cuts on two model/backend combinations. Its positive Oracle result does not validate a general cost predictor, dataset accuracy, CNNParted/Timeloop/Accelergy, saved measurements or an energy improvement.

## Integration

Load `amsmath`, `graphicx`, `booktabs`, `tabularx` and `siunitx` in the main document. Numerical cells inherit that document's `siunitx` settings. With the repository root as the TeX working directory:

```latex
\newcommand{\StageCostBundlePath}{results/supplementary-studies/stage-cost-composition}
\input{publications/dissertation/stage-cost-composition/section_stage_costs.tex}
```

When building elsewhere, prefix both paths with the path to this results draft. `\StageCostBundlePath` points to the shared results directory, not the dissertation module. Labels include the experiment date.

Merge the supplied entry from [stage_cost_evidence.bib](stage_cost_evidence.bib) into the existing bibliography without overwriting an existing key. A `biblatex` project can instead load this file with `\addbibresource`. The entry is unchanged from the supplied package and cites its experimental evidence. No DOI or public repository URL has been added.

## Standalone preview

From the repository root, build with a local TeX installation; auxiliary files and the rebuilt PDF go to a fresh directory outside the draft:

```bash
cd publications/dissertation/stage-cost-composition
stage_cost_build_dir="$(mktemp -d)"
pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$stage_cost_build_dir" preview.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$stage_cost_build_dir" preview.tex
```

The supplied `preview.pdf` was rebuilt from the adapted paths and visually checked. This preview uses the package's German numeric formatting and the regenerated English vector figure. The study reproduction rebuilds the shared figures and table before this optional TeX build.
