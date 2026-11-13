# Automatic Edge-AI workload pipeline

- Tool version: `0.8.1`
- Dataset root: `/homes/jwachsmuth/power_measurements/tek_scope_comparison`
- Discovered workload campaigns: **6**
- Generated multi-workload config: `/homes/kmika/common_trace_analysis/edge_ai_auto_pipeline_v1/generated_configs/config_multi_workload_auto.yaml`

| Workload | Family | Precision | Rates | Paired records | 5-MS/s pairs | Scope stage |
|---|---|---:|---:|---:|---:|---|
| GEMM-FP32 | GEMM | FP32 | 10 | 99 | 10 | completed |
| GEMM-INT8 | GEMM | INT8 | 10 | 106 | 10 | completed |
| YOLO-FP32 | YOLO | FP32 | 10 | 131 | 10 | completed |
| YOLO-INT8 | YOLO | INT8 | 10 | 105 | 10 | completed |
| Gemma3-4B | Gemma3-4B | unspecified | 10 | 100 | 10 | completed |
| ResNet-50 FP32 | ResNet-50 | FP32 | 10 | 132 | 9 | completed |

## Multi-workload analysis and paper artifacts

- Status: **completed**
- Output root: `/homes/kmika/common_trace_analysis/edge_ai_multi_workload_v1`
- Summary: `/homes/kmika/common_trace_analysis/edge_ai_multi_workload_v1/MULTI_WORKLOAD_SUMMARY.md`
- Compact review bundle: `/homes/kmika/common_trace_analysis/edge_ai_multi_workload_v1/paper_artifacts/multi_workload_documentation_artifacts_review.zip`

## Result

All requested stages completed or were safely reused from matching fingerprints.

The measurement trees were treated read-only. Empty directories, unpaired files, and partial high-rate campaigns remain visible in the generated inventories.
