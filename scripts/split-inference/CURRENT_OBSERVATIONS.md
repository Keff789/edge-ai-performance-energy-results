# Current deployment observations

`build_paper_dataset.build` reads the established curated inputs, then optionally
applies `inputs/current_observations.json`. `--current-observations` selects a
different file. This is a small replacement input for the existing dataset,
not another deployment dataset. Original input rows remain unchanged; generated
`data/current_observation_history.json` retains every replaced row and repeat.

The envelope has `schema: current-deployment-observations-v1`, a `sources` map,
and `observations`. Every source has a relative `path` and exact file `sha256`.
Every metric value is read through an exact reference:

```json
{"source": "normal_actual_result", "pointer": "/primary/candidate"}
```

JSON Pointers are resolved against the retained, hash-checked source. A compact
projection may retain the normal result's original file hash in its source
index; `actual_result_sha256` then references that exact hash rather than using
the projection file's hash. Original source descriptors and normal admission
must remain linked. Paths or labels alone never establish observation authority.

Each observation contains:

- `uid`, the unchanged `identity` (`model_id`, `setup_id`, `backend`, `case_id`,
  `runner`, `kind`), and `identity_evidence` references into actual normal sources.
- `prior_case_sha256`, the SHA256 of the original `cases.json` row serialized
  with sorted keys, compact separators and no NaN. An addition uses null and
  `new_case` with structural metadata and null metric values. Only Generic
  splits may be added; their actual FPS and own quality sources are required.
- `generation` and `metrics`, containing only the metrics actually replaced.
- Optional `runtime_fields`, mapping current runtime metadata to actual-source
  references. They cannot replace identities or metric values.

Every metric declares `actual_result`, actual `completed_at` reference,
`acquisition_origin` (`new_capture` or `reused_existing`), and `normal_admission`.
An already admitted reused quality result may retain a null completion timestamp
when its original file did not record one; a new capture requires its actual time.
The latter identifies the existing `normal_api`, an `accepted` actual-source
reference, and `checks` of `{actual: <reference>, expected: <value>}`. Source and
normal admission checks are separate from the measured quality outcome.
`accepted` must reference the corresponding normal observation admission, not
merely a successful raw timing loop or an outer workflow exit code. Diagnostic
or rejected normal observations stay in the source archive and are not promoted
to current measurements.

Performance supplies three `repetitions`, each with references for `fps`, `pid`,
`warmups`, and `completed_tasks`. Three independent processes, 100 warmups and
1000 completed tasks are required. The stored median is derived from actual
rates. Replacing FPS without matching energy explicitly clears old energy.
If the normal Native route retains no measured-runner PID, a repetition instead
supplies `process_evidence` references for `namespace`, `process_id`,
`start_ticks`, and `runtime_instance_id`. Three separate normal controller SSH
child invocations, their start identities and three fresh Native runtime IDs
can establish the normal three-process scope. These controller process IDs are
retained under that explicit namespace and never relabelled DUT Python PIDs.
Where the pinned normal Native producer records
`request_latency.clock_domain=perf_counter_ns:process:<os.getpid()>`, references
for `clock_domain` and the actual `runtime_instance_id` directly establish the
DUT process identity. Only that exact string schema is parsed; UUIDs are not PIDs.
Replacing FPS also clears old quality unless matching actual quality is supplied.

Quality supplies references for `value`, `reference`, `n`,
`bootstrap_repetitions`, `quality_eligible`, and `quality_class`. N5000/B1000 is
required for these detector updates. `performance_source_sha256` must reference
the exact selected FPS source in the normal relation proof. Failed measured
quality and AP zero remain observed values. Quality is never selected by outcome.

Energy supplies three `repetitions`. Each has `actual_result` (or an exact
`source_sha256` reference) and `values` references for `energy_j`,
`completed_tasks`, `duration_s`, and `requested_duration_s`. The requested window
is 60 seconds; integration uses actual observed duration and completed images.
`system_scope` must resolve to `full_system` or its normal `FS` alias. The normal relation proof's
`performance_source_sha256` must equal the selected actual FPS source. Energy
is the arithmetic mean of actual per-repeat E/N, without substituting FPS×time.

Every Native replacement also has `native_binding`:

- `archived_binding_sha256` hashes the exact original archived RQ2 binding row.
- `identity` references actual `model_sha256`, `part1_sha256`,
  `part2_engine_sha256`, `boundary_id`, `preprocessing_sha256`, and
  `completion_contract_sha256`.
- `normal_admission` provides the actual normal source/reuse relation authority.

A fresh Native FPS replacement additionally supplies `generic_comparison` source
references for the exact selected Generic performance-source hash, preprocessing,
prepared-input hash and completed-endpoint contract hash. The latter identities
must match the actual Native identities. Runner-specific execution-contract
hashes remain separate and need not be equal.

Current RQ2 verifies this binding against the original Native population and
actual selected performance source. It never adds a Native pair for a Generic
deployment. `--native-dataset` supplies a materialized current dataset before
publication adoption. Historical reproduction restores the exact archived
Native rows, while current RQ2 uses the explicit replacements.

`scripts/reproduce_current.py --deployment-inputs <directory>
--current-observations <file>` materializes these same rows before both RQ1 and
RQ2. RQ3 inputs and candidate FPS are not changed. `--reuse-studies` requires the
published RQ2 study to bind the same current dataset hash.
