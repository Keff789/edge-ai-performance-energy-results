# Historical graph inventory inputs

`method_graph_features.csv` and `native_cases.csv` link to the unchanged THESIS20 inputs. All 2,111 graph descriptors are reused. `graph_positions.csv` adds only the original manuscript's `node_count` and `topological_position`, keyed by model and case. The generator reconstructs the original descriptor projection from the shared fields and their stored-name aliases; every source descriptor has `source_role=base_saved_candidate_ranking`.

Suffix capability requires `part2_input_count == 1`. A single crossing tensor (`n_cut_tensors == 1`) is insufficient if the suffix needs another input. Native exclusions and their reason `part2_input_count_not_one` are retained in the vendor input table. The 183 matching cuts across seven models are an inventory, not 183 new measurements.
