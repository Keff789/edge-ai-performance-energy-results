# Original YOLOv7 diagnostic profile exports

[SPLIT_STAGE_PROFILE.csv](SPLIT_STAGE_PROFILE.csv) is the original 161-row
aggregated profile export for five short diagnostic cases: H10 strict, DeepX
strict, H8 fast and H10 candidate fast at `b066`, plus H8 candidate fast at `b044`.
Each case used one process, 100 discarded warmups and 100 completed detections.

The CSV, [original explanatory report](SPLIT_STAGE_PROFILE.md) and its linked
[H8-b044 regression discussion](H8_B044_REGRESSION_ANALYSIS.md) were copied
without changes from `report/` in
`YOLOV7_SPLITS_ORIN_REVIEW_20261006_234549_focused.zip`. They also match the
original `splits_orin_20261006_222316/` report directory. The historical source
paths inside these original files are retained as provenance locators; they
are not dependencies of the publication's offline command.

The CSV contains measured profile aggregates together with explicitly labelled
derived exclusive partitions, percentages and serial subtotals. It was not
recreated from the report text. Its five `profiling/*/accepted_profile.json`
sources, including frame-level observations, were found and checked in the
same archive; those larger source records and raw timelines remain external.
This recovery checked the numerical correspondence to those records, without
rerunning the profiling programs or claiming a new raw-output verification.

The H10 CPU completion means are 63.59895807 and 6.61431660 ms/image; the
instrumented windows are 73.53095095 and 19.07346837 ms/image. Inclusive parents,
exclusive children, CUDA subintervals and overlapping pipeline stages must not
be summed indiscriminately. Queue/submission intervals are not isolated NPU
execution times. The reports retain their original missing-value and timing
qualifications. These are diagnostic observations, separate from final FPS
repeats, the September host-format experiments and the independent stage-cost
composition study.

[Back to the completion study](../README.md).
