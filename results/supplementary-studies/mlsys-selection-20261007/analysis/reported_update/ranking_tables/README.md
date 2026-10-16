# Current report-overlay selection outputs

    These are the active selection metrics for the updated paper. Reproduce with
    the documented study command. The script reads the supplied
    report-derived CSV and the bundled historical tables, retaining candidate and
    quality-transfer gates. It does not inspect a raw ZIP or run inference.

    Nine YOLOv7 native rates and 27 native repetitions are report-based replacements;
    their Generic counterparts are historical. The other 195 native rows are
    unchanged. These comparisons describe selector transfer across recorded
    campaigns, not a controlled same-state runner comparison. Historical command
    hashes, runner IDs, endpoint IDs and makespans are cleared from overlaid rows;
    the report SHA identifies the replacement source. Current energy is unavailable
    for YOLOv7 and excluded from method energy summaries.

    Frozen method selections remain available for every displayed selector. Four
    static methods can also reconstruct their YOLOv7 score vectors from bundled
    graph fields; the stored H10 hardware-fit vector is not bundled, so its updated
    YOLOv7 rank correlations are NA. `rank_evaluable_group_count` reports correlation
    scope, while selection loss/hit scope remains 21 technical groups. This is not a
    refit. Existing historical tables in `analysis/evidence/tables` and
    `analysis/methods/tables` are provenance inputs, not current overlay outputs.
    