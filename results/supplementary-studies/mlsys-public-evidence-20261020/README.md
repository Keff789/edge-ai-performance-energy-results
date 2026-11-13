# Original audit and scheduling evidence

These extracts publish existing records from the two source archives bound in the study provenance files. They complement the [R22 numerical reproduction](../../split-inference/publications/mlsys-r22/README.md) and the [complete supplement](../../../publications/mlsys/supplement/MLSys_Supplement.pdf).

| Evidence | Content |
|---|---|
| [Audit CSV](../mlsys-evidence-mechanism-20261017/EVIDENCE_AUDIT.csv) and [flag resolutions](../mlsys-evidence-mechanism-20261017/FLAG_RESOLUTION.csv) | Unchanged originals: 450 audit rows and 972 flag-resolution rows covering the same 450 configurations. |
| [RegNet evidence archive](../mlsys-evidence-mechanism-20261017/evidence/regnet_scheduling_evidence.tar.xz) · [member manifest](../mlsys-evidence-mechanism-20261017/evidence/regnet_scheduling_evidence.manifest.json) | 40 RegNet factorial processes and the separate earlier 20-process Native-only ResNet series, with 180 state records and complete protocol-bound runtime sources. |
| [ResNet evidence archive](../mlsys-resnet-replication-20261017/evidence/resnet_scheduling_evidence.tar.xz) · [member manifest](../mlsys-resnet-replication-20261017/evidence/resnet_scheduling_evidence.manifest.json) | 40 fresh ResNet factorial processes, 120 state records and complete protocol-bound runtime sources. |

Each original member retains its path and bytes. The manifests bind it to the source archive and SHA256, and identify the two generated `EXTRACT_*` metadata files. All 316/312 protocol-deployed files and separately pinned controller sources are included. Every loaded-source hash recorded by the 100 confirmed process reports resolves to an included file. [Audit validation](AUDIT_VALIDATION.json) and the [package summary](PACKAGE_SUMMARY.json) record the checks.

The earlier twenty-process Native-only series is indexed separately and must not be pooled with either forty-process study. Frozen functional prerequisites retain original `canary`/`pilot` paths and small input/reference tensors. They are supporting functional evidence, not additional timing measurements. Model binaries, manuscript inputs, personal task prompts and pilot timing measurements are excluded.

For inspection, extract either archive with `tar -xJf ARCHIVE.tar.xz`. Numerical reproduction of the paper assets uses the existing R22 command and does not require the original source ZIPs. To rebuild these evidence extracts, provide the two original archives listed in the [RegNet](../mlsys-evidence-mechanism-20261017/PROVENANCE.json) and [ResNet](../mlsys-resnet-replication-20261017/PROVENANCE.json) provenance files:

```bash
python results/supplementary-studies/mlsys-public-evidence-20261020/rebuild_evidence.py \
  --input-dir /path/to/original-archives --output-dir /path/to/evidence-rebuild
```

The extractor verifies archive hashes, original member checksums, source bindings and process-group counts. New hardware collection additionally requires the recorded H10/Orin setup, SDK/TensorRT/Python environment, model artifacts and benchmark/quality dependencies identified in the protocols. Original absolute paths are provenance labels and may require explicit mapping. The historical archival-status records remain separate from this public evidence release.
