# Compact inputs for the MLSys R22 publication profile

These specifications and additional compact source records support the [R22 publication assets](../../publications/mlsys-r22/README.md). Reproduce them through the existing [split-inference entry point](../../../../scripts/split-inference/README.md); the manuscript archive is not a runtime input. The current 450-deployment dataset and existing historical-study data remain at their canonical repository locations.

The reference is `MLSys_Split_Selection_20261018_LaTeX_R22.zip`, SHA256 `da510863479b8bfc7096d41e017e77879a8df3db1e1c0cad1bf952c35179c5a7`. It was inspected outside the repository. The complete manuscript ZIP, models, datasets and large source archives are not copied here.

| Input | Purpose and binding |
|---|---|
| [asset_spec.json](asset_spec.json) | Active labelled environments from the frozen `main.tex` and `supplement.tex`, including document/include paths, original file hashes and numbering: 37 occurrences of 36 unique assets. The shared stage-cost table appears twice. |
| [methods_spec.json](methods_spec.json) | Versioned recorded setup, scope and endpoint descriptions for editorial method tables. These are descriptions, not invented measurement rows. |
| [evidence_sources.json](evidence_sources.json) | Logical evidence paths mapped to canonical repository inputs or unchanged compact imports; each entry retains UID, reference member, size and SHA256. Five byte-identical existing files are reused. Code origins and checker adaptations are recorded here. |
| [R15 source manifest](evidence/r15/SOURCE_MANIFEST.json) | Original archive/member bindings for the quality inventory, calibration features/folds/memberships/predictions, frozen protocols and 100 process reports. Original evidence remains unchanged. |
| [R20 source provenance](evidence/r20/SOURCE_PROVENANCE.json) | Original archive/member and projection hashes for endpoint contracts, workload/preprocessing records, DeepX energy windows and CPU-relative YOLOv7 quality evidence. |

The logical path map resolves all reads inside this repository. Historical `/home/` and `/workspace/` strings within original records are provenance labels, not required local directories. Approximately 5.29 MB of missing compact evidence is added; existing summaries and canonical measurements are reused where byte-identical. The original [R15](evidence/r15/README.md) and [R20](evidence/r20/README.md) notes remain unchanged source documentation; their manuscript-local command examples are superseded here by the central repository command.

The R15 checker refits the fixed ridge model using training-only scaling, an unpenalized intercept and entire held-out architectures, then reconstructs group budgets and scheduling contrasts from their bound inputs. The two forty-process studies and earlier twenty-process Native-only series remain separate. The R20 checker verifies the published projections and all existing value contracts offline; reconstruction from large original archives is optional. No new inference, energy acquisition or quality evaluation occurs.

The generated [asset manifest](../../publications/mlsys-r22/ASSET_MANIFEST.json) connects these inputs to output labels and checks. [Reference differences](../../publications/mlsys-r22/REFERENCE_DIFFERENCES.md) explain the vendor generator's corrected current-data binding and the existing YOLO26s/H8 energy repeats added beyond the paper extract. Existing [rights and notices](../../../../RIGHTS_AND_NOTICES.md) apply.
