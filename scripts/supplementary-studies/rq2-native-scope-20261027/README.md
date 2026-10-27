# RQ2 full Native population importer

This successor leaves `rq2-generic-final-20261027` and its default reproduction intact. Its population is every original artifact-bound measured Native cut in the archived pair bindings. The input `fixed420_uids` list only annotates membership in the unchanged RQ3 cohort.

`run(output, repo=REPO, numeric_only=False, verify_reference=None, input_path=None)` reproduces into an empty directory. The default input is `results/supplementary-studies/rq2-native-scope-20261027/inputs/observations.json`. The R30 profile dispatches to this engine when the supplied study summary schema is `rq2-native-scope-pairs-v1`.

Each observation keeps the fields in the old final Generic projection and adds:

- `completed_at`: actual measurement completion timestamp with timezone, never a file-copy/import timestamp.
- `performance_source_sha256`: hash of the actual measured observation; `observation_id` may provide its stable identifier.
- `observation_origin`: `recovered` or `remeasured`.
- `observation_contract`: established complete-task contract proof.
- `quality_binding`: current normal quality evidence, including its own numerical candidate/reference values. Missing evidence remains unavailable even when an old `quality_eligible` label is true.

A hash-bound normal admission can use the compact authority form:

```json
{
  "observation_contract": {
    "valid": true,
    "contract_evidence_sha256": "hash of existing normal complete-task proof",
    "proof_type": "normal_current_ledger",
    "ledger_row_sha256": "canonical actual admitted product row hash",
    "identity_verified": true,
    "complete_task_verified": true
  },
  "quality_binding": {
    "verified": true,
    "evidence_sha256": "hash of actual bound quality evidence",
    "proof_type": "normal_current_ledger",
    "ledger_row_sha256": "canonical normal quality product admission row hash",
    "product_identity_verified": true,
    "runtime_artifacts_and_inputs_bound": true,
    "dataset_reference_evaluator_bound": true,
    "reference_runtime": "cpu_onnx",
    "normal_admission": true,
    "value": 0.45,
    "reference": 0.46
  }
}
```

These assertions must come from existing normal admission and actual evidence; the importer never creates them from outcome labels. An optional `product_identity` in each proof explicitly records `model_sha256`, `setup_id`, `part1_sha256`, and `part2_engine_sha256`; every supplied identity is checked. The independent Native binding checks always apply. A fuller explicit proof can instead bind preprocessing, prepared inputs, tensor contract, output interpretation, completion, dataset/image set, reference model, evaluator policy, and actual prediction runtime hashes directly. Historical reuse requires its existing valid complete-task contract proof. Contract names such as `fast_oracle_outside_timing` do not determine validity.

An explicit product reuse relation can prove executable equivalence when bytes differ. It must identify both actual Native and Generic artifact hashes, model, physical setup, graph boundary, and evidence hash, and affirm verified precision, tensor and complete-task equivalence. A cut name alone never establishes that relation.

Selection uses the latest compatible valid actual completion, before reading quality. Newer measured FAIL remains selected over older PASS. Unknown ordering and distinct observations with identical completion timestamps stay unresolved. Output accounting covers every original cut, labels singleton groups, reports both the established equal-group mean and its `n>=2` restriction, and compares old/current Generic choices and ranks on exactly the same eligible pairs.

`VALIDATION.json` reports offline importer/accounting validation. It does not confer missing hardware quality PASS. Native, Full, RQ1, RQ3, historical energy, and the original YOLOv7 case evidence remain unchanged.

Input assembly and pending corrections use the same original population. Run:

```sh
python scripts/supplementary-studies/rq2-native-scope-20261027/assemble_inputs.py \
  --followup <retained-followup-directory> \
  --output results/supplementary-studies/rq2-native-scope-20261027/inputs
```

The assembly keeps the original current and extra observations and portable proof projections, plus exact upstream/projection hashes in `SOURCE_PROJECTION_MANIFEST.json`. The demonstrated quality assignment scope comes from the source-bound affected-scope audit, independently of AP outcomes. Its old quality results remain history while corrected normal quality is pending. Both historical and fresh b009 Generic observations remain explicit candidates. Fresh Generic FPS and quality are complete; pairing remains held only because the original Native preprocessing authority is unproved. Another Generic capture cannot establish that missing historical Native authority.

`source_snapshot_sha256=36d0a02e…` identifies the historical 192-observation base. The separate `INPUT_MANIFEST.json` hash for `inputs/observations.json` binds the complete current RQ2 input, including the 12 extra cuts, 17 new quality captures, one new FPS capture, and their retained provenance. The adopted fixed420 ledger `d658eb19…` is separate current RQ3 authority; it does not replace the 12 RQ2 observations outside that cohort. Historical source hashes retain their original meaning.

Apply corrected results with repeated `--quality-overlay <file>` and, when necessary for b009, `--performance-overlay <file>`. A quality overlay has this shape:

```json
{
  "rows": [
    {
      "generic_uid": "generic|model|setup|backend|cut",
      "performance_source_sha256": "exact selected FPS source hash",
      "quality_completed_at": "actual quality completion timestamp with timezone",
      "quality_binding": {
        "verified": true,
        "evidence_sha256": "actual normal quality evidence hash",
        "proof_type": "normal_current_ledger",
        "ledger_row_sha256": "canonical actual quality authority row hash",
        "product_identity_verified": true,
        "runtime_artifacts_and_inputs_bound": true,
        "dataset_reference_evaluator_bound": true,
        "reference_runtime": "cpu_onnx",
        "normal_admission": true,
        "value": 0.45,
        "reference": 0.46
      }
    }
  ]
}
```

The normal admission decision is retained, including FAIL. AP and reference are actual observations. The source/evidence projection must prove actual runtime and preprocessing, artifacts, tensor/output/completion interpretation, dataset/image set, CPU reference, and evaluator policy under normal admission. Parent source-proof artifacts can be copied alongside the overlay; all input JSON files are hashed in the generated input manifest.

A performance overlay has `rows` containing full observation records or patches that include, at minimum, actual `completed_at`, `performance_source_sha256`, `effective_generic_fps`, three `effective_repeats`, `artifacts`, and `observation_contract`. Admitting a pair with a prior compatibility hold additionally requires `pair_compatibility: {"verified": true, "evidence_sha256": "actual normal pairing proof hash"}`. A fresh Generic observation alone does not prove historical Native preprocessing authority. Without an independently verified Native pairing relation, the newer Generic measurement remains standalone and the RQ2 pair remains held. Distinct actual FPS sources remain separate candidate rows. The numerical engine selects the latest compatible candidate; a newer incompatible candidate cannot discard an older compatible observation. Historical standalone measurements remain preserved as candidate records. Quality remains unavailable unless a bound quality observation is supplied for the selected FPS source. Neither FPS nor quality overlays select by outcome.

Native quality keeps its established historical normal AP/reference metric. The exact selected timed Native endpoint AP is not established merely by the original numeric record or an artifact join. The proven additional-NMS differences are bounded to the evidenced YOLO26m H8/H10 b043 identities; their source hashes, diagnostic limits, and the retained CPU harness closure caveat are in `data/quality_contract_provenance.json`. Current Generic quality evaluates actual timed completion records against the existing CPU reference under normal policy. This difference in quality definitions limits interpretation and does not change original Native values or authorize a Native measurement campaign.

Acquisition reporting separates recovered sources, compatible pairs, new FPS captures, and new quality captures. `source_found` includes any Generic observation for the original Native cut, including standalone records held from pairing. `compatible_selected` is the stricter selected-pair count. The legacy `recovered` field retains its compatible-selected meaning. `remeasured` aliases the number of original cuts with new FPS captures, including held standalone captures. Quality-only work is counted separately in `new_quality_captured`.

Actual overlay provenance declares `performance_acquisition_origin` or `quality_acquisition_origin` as `new_capture`, `reused_existing`, or `unknown`. Only explicit `new_capture` with an actual completion time and source hash enters new-capture counts. `source_capture_evidence` can retain the quality capture descriptor. Counts do not depend on quality PASS/FAIL or pair eligibility; distinct source hashes identify separate capture observations.

`tables/native_generic_quality_observations.csv` and its JSON counterpart retain own observed Generic AP, reference AP, relative loss, acquisition origin and time for all original cuts. `pair_compatible_selected`, `pair_eligible`, and exact hold reasons remain separate. A fresh b009 Generic AP therefore remains visible even when the original Native pairing authority is unresolved; it does not become unavailable merely because that pair is held.

`import_case_quality.py` projects actual per-case central receipts for the demonstrated affected quality cases into portable overlays. It checks the normal published result and own-row admission, actual source-capture closure, completed N5000/B1000 evidence, model/device/artifacts, actual completion time, the existing scoped FPS reuse authority, and scientific-field-preserving configuration derivation. It never reads a message as numerical evidence, filters by outcome, or promotes an outer quality-only FPS-normalizer exit code to whole-workflow PASS. Original selected FPS is retained. Independent b009 or extra-cut relations require their own normal authority and are not inferred from the affected-case reuse report.

Use `assemble_inputs.py --typed-admission <receipt>` to retain subsequent normal typed-import authority alongside an already verified actual-capture overlay. The original receipt hash, typed API, exact affected identities, preserved FPS authority, and immutable candidate-ledger hash are linked in each relevant observation. This adds provenance and does not change AP or FPS values.

Fresh legacy completed-task imports use `import_fresh_legacy.py`, which crosschecks actual normal accepted FPS/quality rows, three independent processes with 100 warmups and 1000 completed tasks each, terminal/cleanup receipts, source hashes, and actual quality results. These observations retain their real legacy measurement mode and are never relabelled Generic-only. A fresh observation does not clear original Native pairing holds; actual old and new completed FPS sources remain candidate records, and failed zero-FPS controller starts remain source history.

Use `--provenance-overlay` for metadata-only source-epoch additions linked to exact FPS and quality source hashes. This does not add an observation or change acquisition counts. `performance_source_epochs` and `generic_quality_source_epochs` distinguish the actual controller, hardware producer, and CPU consumer commits/source freezes. A later CPU consumer version is not assigned retrospectively to earlier captures. Missing historical epoch fields stay unreported.
