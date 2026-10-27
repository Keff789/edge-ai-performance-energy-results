# Current Generic / existing Native comparison

192 verified pairs across 21 model/device groups; 159 pairs pass both numerical Native quality and current Generic quality across 13 groups. Eight groups have no eligible paired candidate. The prior publication used 204 pairs (187 quality-eligible); the fixed420 intersection changes the evaluated candidate set. Unproven pairs remain in data/pair_identity_audit.json with reasons. Model, physical device, graph frontier, execution precision, exact P1/engine bytes and original I/O bindings are checked.

Mean Generic Top-1 selection loss: 2.159239%; old Generic on these same pairs: 22.959196%. The prior full 187-pair/21-group value (15.077129%) uses a different cohort and stays separate in summary.json. Weights and normalizations are frozen from the original study; no fit is repeated. Energy is excluded from refreshed pairs, preserving its original observations and bindings.

H8 / YOLOv7 / b009 retains a measured FPS observation, but its historical quality association lacks original executed preprocessing authority. Its quality remains unresolved and it is excluded from the quality-eligible pairs. No current quality admission is inferred from its historical label.

Reproduce with `python scripts/supplementary-studies/rq2-generic-final-20261027/reproduce.py --output <empty-dir> --verify`. Add `--numeric-only` to omit rendering.
