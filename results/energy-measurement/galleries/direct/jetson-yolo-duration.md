# Jetson YOLO duration sweeps

[Back to gallery](../direct-sweeps.md) · [Energy results](../../README.md) · [Methods and limits](../../METHODS.md) · [Table index](../../tables/README.md)

Each workload retains three complementary views: mean-power distributions, a full-range distribution view, and paired energy deviations. At each requested duration, the deviation bars show the median of individual matched differences, 100 × (sensor energy / PicoScope energy − 1). These per-workload device comparisons use paired executions; the separate duration-convergence overview uses a fixed 600-s median-power reference.

## YOLO FP16

### Jetson YOLO FP16: distribution detail

Mean-power distributions for each measurement path across the requested durations; each path retains its own energy and duration.

![Jetson YOLO FP16: distribution detail](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_boxplot.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_boxplot.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_boxplot.pdf)

### Jetson YOLO FP16: full-range distribution

Full-range mean-power distributions retaining the displayed spread across measurement paths and duration requests.

![Jetson YOLO FP16: full-range distribution](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_boxplot_full_range.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_boxplot_full_range.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_boxplot_full_range.pdf)

### Jetson YOLO FP16: paired energy deviations

At each requested duration, median individual matched sensor/PicoScope energy differences in percent. Ratios are formed per execution before taking the median.

![Jetson YOLO FP16: paired energy deviations](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_deviations.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_deviations.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp16_duration_sweep_deviations.pdf)

## YOLO FP32

### Jetson YOLO FP32: distribution detail

Mean-power distributions for each measurement path across the requested durations; each path retains its own energy and duration.

![Jetson YOLO FP32: distribution detail](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_boxplot.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_boxplot.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_boxplot.pdf)

### Jetson YOLO FP32: full-range distribution

Full-range mean-power distributions retaining the displayed spread across measurement paths and duration requests.

![Jetson YOLO FP32: full-range distribution](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_boxplot_full_range.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_boxplot_full_range.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_boxplot_full_range.pdf)

### Jetson YOLO FP32: paired energy deviations

At each requested duration, median individual matched sensor/PicoScope energy differences in percent. Ratios are formed per execution before taking the median.

![Jetson YOLO FP32: paired energy deviations](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_deviations.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_deviations.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_fp32_duration_sweep_deviations.pdf)

## YOLO INT8

### Jetson YOLO INT8: distribution detail

Mean-power distributions for each measurement path across the requested durations; each path retains its own energy and duration.

![Jetson YOLO INT8: distribution detail](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_boxplot.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_boxplot.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_boxplot.pdf)

### Jetson YOLO INT8: full-range distribution

Full-range mean-power distributions retaining the displayed spread across measurement paths and duration requests.

![Jetson YOLO INT8: full-range distribution](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_boxplot_full_range.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_boxplot_full_range.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_boxplot_full_range.pdf)

### Jetson YOLO INT8: paired energy deviations

At each requested duration, median individual matched sensor/PicoScope energy differences in percent. Ratios are formed per execution before taking the median.

![Jetson YOLO INT8: paired energy deviations](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_deviations.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_deviations.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/yolo_int8_duration_sweep_deviations.pdf)

## Variable YOLO

### Jetson Variable YOLO: distribution detail

Mean-power distributions for each measurement path across the requested durations; each path retains its own energy and duration.

![Jetson Variable YOLO: distribution detail](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_boxplot.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_boxplot.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_boxplot.pdf)

### Jetson Variable YOLO: full-range distribution

Full-range mean-power distributions retaining the displayed spread across measurement paths and duration requests.

![Jetson Variable YOLO: full-range distribution](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_boxplot_full_range.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_boxplot_full_range.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_boxplot_full_range.pdf)

### Jetson Variable YOLO: paired energy deviations

At each requested duration, median individual matched sensor/PicoScope energy differences in percent. Ratios are formed per execution before taking the median.

![Jetson Variable YOLO: paired energy deviations](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_deviations.png)

[PNG](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_deviations.png) · [PDF](../../figures/direct-sweeps/Jetson/duration_sweep/random_pattern_yolo_duration_sweep_deviations.pdf)

