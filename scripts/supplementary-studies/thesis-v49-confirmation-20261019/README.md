# v49 confirmation: offline table reproduction

This entry reproduces the separate [v49 hardware confirmation and energy supplements](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/README.md). It operates on compact inputs already stored in the result repository. It does not start inference, a collector, recovery operations or a hardware campaign.

From the repository root:

```bash
python3 -B scripts/supplementary-studies/thesis-v49-confirmation-20261019/reproduce.py \
  --inputs results/supplementary-studies/thesis-v49-confirmation-20261019/inputs \
  --output /tmp/thesis-v49-confirmation-reproduced
```

Use Python 3.10 or later and NumPy 1.22 or later, below version 3, as declared in [requirements.txt](requirements.txt); the percentile calculation uses `method='linear'`. The remaining dependencies are from Python's standard library. COCO tooling, pandas, Matplotlib, network access and measurement hardware are not required. Choose a fresh output directory outside the repository. The result inputs and published tables remain unchanged.

The generator writes its CSV/JSON files directly under the selected output root. The published copies are indexed in the study's [generated records](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/README.md#generated-records). The [calculation source](calculation_core.py) and [function-origin manifest](calculation_origins.json) retain the exact reused campaign functions and their source hashes; the generated [reproduction manifest](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/tables/reproduction_manifest.json) binds compact inputs and output bytes. No figure regeneration is needed for this confirmation, and the historical 450-configuration figures remain separate.

The command was checked with Python 3.12.3 and NumPy 1.26.4, including execution from outside the checkout using absolute script/input/output paths. The focused temporary-fixture suite is:

```bash
python3 -B scripts/supplementary-studies/thesis-v49-confirmation-20261019/test_reproduce.py
```

All twelve tests passed. They check the portable calculation and input/output boundaries; they are separate from hardware acquisition and from a full archive audit.

## Calculation boundaries

The [measurement input](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/inputs/measurements.json) retains seventy primary `N/t` records, sixty-eight primary conditional energies and two separate supplements with their own `N/t/E`. The [design](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/inputs/design.json) supplies exact UID, model, host, backend, block and split/Full identities. [Historical repeats](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/inputs/history_repeats.json) retain the separate original throughput and energy observations. [Attempt history](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/inputs/attempt_history.json) and [origin provenance](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/inputs/origin_provenance.json) distinguish logical slots, actual starts and selected attempts.

The evaluator recomputes rates from actual completion counts and native intervals including drain, `E/N` from the same acquisition's energy and count, split/Full block pairs, and sample count/mean/median/minimum/maximum for each UID. Primary energy statistics preserve the two four-repeat UIDs; energy-coverage statistics separately include the supplements. Seven energy direction comparisons use arithmetic means of per-acquisition `E/N`, with signed differences and mean ratios distinguished from median contrasts. Historical repeat statistics use the same explicit summary names. Observed ranges are not confidence intervals.

It retains the original seventy throughput rows and both primary energy-null fields. The energy supplements add two explicitly cross-session pairs to thirty-three primary pairs; they do not replace primary throughput or silently fill primary energy records.

The direct quality intervals use the [supplied absolute split/Full bootstrap values and frozen plans](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/inputs/quality/index.json). Seven model pairs produce fifteen metric rows: three classifier Top-1 differences and four detector pairs evaluated at AP50:95, AP50 and AP75. Differences and percentile limits are recomputed from the saved values. This is an offline calculation over existing prediction evidence. It performs no new quality inference or prediction-level COCO evaluation and does not infer historical evaluator versions from the current environment.

## Table reproduction versus archive audit

The compact command reconstructs numerical tables from the bound primitive counts, durations, energies and quality-resampling inputs. It does not numerically reintegrate original sensor waveforms, rerun COCO evaluation from all predictions, validate model binaries, execute historical firmware or prove the physical ADC unit. Those checks require the complete external campaign archive and the independently identified model/dataset stores described in the [study provenance](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/README.md#provenance-archive-and-access).

In `primary_measurements`, inherited `joules_per_completion=null` and `energy_same_interval_verified=false` refer to fully physically qualified energy C, which remains open. Conditional same-interval energy uses the separate `B_valid`, `conditional_energy_j` and `conditional_energy_j_per_completion` fields; those retain 68 primary integrations and two primary nulls.

The seventy accepted throughput observations, sixty-eight primary conditional energy observations, two supplements and the historical R1/R2 populations remain distinct. A successful table reproduction does not change the open physical measurement-chain qualification or convert C0 into qualified absolute energy. The copied calculation sources retain their origin and existing [rights and notices](../../../RIGHTS_AND_NOTICES.md).

## CH0 documentation follow-up

The same command also renders the bound [CH0 evidence alignment](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/inputs/metrology/ch0_joris_alignment.json) as `metrology_claims.csv/json` and `metrology_conversion_paths.csv/json`. These tables distinguish documented design and original validation, observed application in the saved campaign, and remaining physical assignments. The existing numerical calculation functions and measured inputs are unchanged. The earlier 33 numerical/accounting output files remain byte-identical; the reproduction manifest additionally binds the new evidence and updated generator.

The documentation establishes the nominal design conversion of 1 mA per ADC count and identifies the correction order already used by the existing code. It does not add a unit conversion or calibration factor. The historical `calculation_origins.json` continues to identify the preserved campaign source from which those unchanged numerical functions were copied; the later documentation sources are identified separately by the [CH0 addendum reference](../../../results/supplementary-studies/thesis-v49-confirmation-20261019/METROLOGY_ADDENDUM_REFERENCE.json). The complete Joris thesis stays in the internal archive; public evidence contains bibliographic details, page references and its hash.
