# Separate full ResNet scheduling-by-runtime replication

State: FROZEN. Protocol SHA256: `c57205b0cbcdd2c7862bf0c21d88eec585a374c7b566bb6896a8571f37be2601`.

This optional study supplements the completed prior study; it repairs no missing block. The old RegNet extension remains unstarted. ResNet was selected because this cut pair was already known to change ranking.

The sole primary phase contains 40 fresh independent processes: ResNet b002 and b095, Generic and Native, productive and global one-task schedules, five complete jointly randomized eight-cell blocks. Seed: 20261017. All Native cells are measured again; no old timing cell enters a new block. No outcome-dependent extension is defined.

The runtime adapter and all 308 backend source files, four case configs/argv files, R14 HEFs, TensorRT engines, prepared UINT8 inputs, precision, compiler metadata and completed classification Top-1/Top-5 endpoint retain their prior exact bindings. Only the task namespace and bounded controller study validation change. The saved eight-cell ResNet canary audit covers the exact runtime chains and is reused without new hardware pilots.

Generic productive uses two workers/queue2; Native productive uses eight Hailo async slots/queue3. Global one-task scheduling retains admission ownership through required output materialization, synchronized suffix execution and Top-1/Top-5 processing. Native additionally uses one async slot; reducing slot or queue size alone is not the global completion barrier.

Each process has 30 seconds warmup followed by full drain, then 60 seconds admission followed by full drain. Throughput is all completed accepted tasks divided by the full measured makespan; warmup is excluded. No continuous profiling or energy capture is added.

Unchanged comparability policy: CPU1984MHz, GPU1173MHz, MAXN_SUPER, CPU affinity0..7, start CPU temperature40..65C with at most2C drift over2seconds, no active throttle alert, at least5seconds rest, maximum120seconds state wait. End temperature is descriptive. Registered physical identity, no competing work, product DUT lock and exact file pins are checked before/after; no clock or power setting is changed.

Primary contrast: r=R(b095)/R(b002) within each variant/block; I=(r_N_product/r_N_single)/(r_G_product/r_G_single), calculated as the corresponding within-block log contrast. Report all four ratios, block values, geometric means, log SD and nominal t95percent intervals (df4). I is a ratio of ratios, not a per-cut speedup. Five blocks and selection of known cases limit generalization.

All failed/excluded attempts remain in the journal. Stop on failure. Only explicitly documented corrected technical causes permit a fresh replacement; an excluded completed attempt requires its exact saved state reasons. No admitted completed cell or unfavorable FPS may be repeated. At most44 attempts are allowed for40 admitted cells: four extra processes form an administrative technical-replacement ceiling, not a sample extension. Uncertain own work is never blindly relaunched.

The provisional protocol cannot run. Root freezes the final protocol and analysis only after independent review, then records external authorization binding that final hash and review. Product physical-device exclusivity is retained with a fresh task lease namespace. No product/old-series/manuscript changes, builds, push or production deployment are permitted.

```sh
/home/kmika/ONNX-Splitpoint-Tool/.venv/bin/python analysis/run_mechanism.py --protocol PROTOCOL.json
/home/kmika/ONNX-Splitpoint-Tool/.venv/bin/python analysis/run_mechanism.py --protocol PROTOCOL.json --run --phase primary --resume
```
