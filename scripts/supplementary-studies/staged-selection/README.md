# Staged split selection

`reproduce.py` replays graph preselection, Generic ranking and final Native testing from the current paired measurements. It does not refit graph weights or run hardware.

```sh
python3 scripts/supplementary-studies/staged-selection/reproduce.py \
  --output local-output/staged-selection --languages en de --verify
```

Use `--paired-study PATH` to evaluate a newly regenerated paired study. Candidate counts, quality membership and all reported values come from its `quality_pairs.csv` and complete graph rankings. The primary policy uses Bytes, up to five or twelve Generic tests, and up to two Native tests per group. Smaller candidate pools are exhausted rather than padded.

The command exports all budget points, per-group selected cuts, task breakdowns, English/German figures and tables, and source hashes. It checks the direct-graph calculations against the published paired-study curves before reporting a verified build. Required plotting dependency: Matplotlib. The analysis itself uses the Python standard library.

The additional `staged_selection_flow` schematic illustrates candidate-pool construction, Generic screening, and the final Native tests. Its YOLO11l graph-size example comes from the recorded graph metadata, selected with `--graph-metadata`. This count is not the measured Native pool. The default paired detector groups contain three cuts each. Diagram widths illustrate the selection sequence and are not a quantitative scale.

Run the targeted tests with:

```sh
python3 -m unittest discover -s scripts/supplementary-studies/staged-selection -p 'test_*.py'
```
