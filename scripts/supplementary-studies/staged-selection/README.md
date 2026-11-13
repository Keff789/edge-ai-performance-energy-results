# Staged split selection

`reproduce.py` replays graph preselection, Generic ranking and final Native testing from the current paired measurements. It does not refit graph weights or run hardware.

```sh
python3 scripts/supplementary-studies/staged-selection/reproduce.py \
  --output local-output/staged-selection --languages en de --verify
```

Use `--paired-study PATH` to evaluate a newly regenerated paired study. Candidate counts, quality membership and all reported values come from its `quality_pairs.csv` and complete graph rankings. The primary policy uses Bytes, up to five or twelve Generic tests, and up to two Native tests per group. Smaller candidate pools are exhausted rather than padded.

The command exports all budget points, per-group selected cuts, task breakdowns, English/German figures and tables, and source hashes. It checks the direct-graph calculations against the published paired-study curves before reporting a verified build. Required plotting dependency: Matplotlib. The analysis itself uses the Python standard library.

The `staged_selection_budget` figure compares one and two final Native tests on identical graph-selected Generic shortlists. Both series are exported in its CSV and JSON.

The additional `staged_selection_flow` schematic places a horizontal process chain below exact square counts for an illustrative 615-to-5-to-2-to-1 workflow. Its YOLO11l graph-size example comes from the recorded graph metadata, selected with `--graph-metadata`. This count is not the measured Native pool. The default paired detector groups contain three cuts each. The five Generic and two Native tests are an illustrative budget, not a measured YOLO11l full-graph trial. Each square represents one option; process boxes have no quantitative scale.

Run the targeted tests with:

```sh
python3 -m unittest discover -s scripts/supplementary-studies/staged-selection -p 'test_*.py'
```

The generator also exports `selection_diagnostics.csv` for all 21 combinations at budgets five and twelve, plus `selection_failures_k5` and `selection_failures_k12` tables in English and German. Failure stages distinguish a Native optimum excluded by graph preselection from one present in the graph shortlist but excluded by Generic ranking. Tied Native optima are handled without treating an alternative optimal cut as a failure. Existing outputs remain unchanged.

`staged_selection_flow_review` adds a separate prospective-versus-retrospective workflow view. The original workflow figure is retained. Rendering this additional PNG preview uses PyMuPDF (`pymupdf`), which is also used by the current publication renderer.
