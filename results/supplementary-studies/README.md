# Supporting studies

The three current analyses share the experimental definitions in the [study overview](../../docs/current-study.md). Their input populations overlap and should **not** be counted as separate measurement campaigns.

| Current analysis | Main question |
|---|---|
| [RQ2 — Generic to Native](rq2-native-scope-20261027/README.md) | How accurately do Generic throughput rankings select Native cuts? |
| [RQ3 — Graph preselection](rq3-generic420-detector-corrected-20261027/README.md) | How much throughput is retained when only a small shortlist is measured? |
| [Staged selection](staged-selection/README.md) | What happens when graph ranking, Generic testing and Native testing are combined? |

**Additional measurements and perspectives:** [stage-cost composition](stage-cost-composition/README.md) treats independently measured stage capacities; [Native energy selection](native-energy-selection-20261030/README.md) studies throughput-constrained energy choices; [review tables](mlsys-review-tables-20261030/README.md) provide compact presentation exports.

**Preserved sources and audits:** The [historical research index](../../docs/archival_studies.md) contains earlier rankings, publication versions, reproduction checks and dissertation development records. The [dissertation appendix supplement](dissertation-appendix-20261111/README.md) preserves the original methodological annex, including the documented use of AI tools in software development.

To regenerate the current English and German results offline:

```bash
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

See [setup and reproduction](../../scripts/README.md). The command does not perform fresh hardware measurements.
