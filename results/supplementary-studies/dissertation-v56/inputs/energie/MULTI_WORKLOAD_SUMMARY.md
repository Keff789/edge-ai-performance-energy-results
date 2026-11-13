# Multi-workload PSD and common-reference analysis

Tool version: `0.8.2`  
Common PSD rate: `5 MS/s`  
Highlighted energy rate: `2 kS/s`

## Included workloads

| Workload | 5-MS/s pairs | PSD | Common reference | Zero-offset status |
|---|---:|---:|---:|---|
| GEMM-FP32 | 10 | yes | yes | disabled |
| GEMM-INT8 | 10 | yes | yes | no_material_offset_detected |
| YOLO-FP32 | 10 | yes | yes | stable_offset_detected_and_corrected |
| YOLO-INT8 | 10 | yes | yes | no_material_offset_detected |
| Gemma3-4B | 10 | yes | yes | no_material_offset_detected |
| ResNet-50 FP32 | 9 | yes | yes | no_material_offset_detected |

## Common-rate Tektronix current PSD

| Workload | $f_{95}$ | $f_{99}$ | Variance above 77 kHz |
|---|---:|---:|---:|
| GEMM-FP32 | 374.2 kHz | 454.6 kHz | 15.24% |
| GEMM-INT8 | 424.4 kHz | 756.9 kHz | 46.44% |
| YOLO-FP32 | 363.5 kHz | 540.0 kHz | 37.99% |
| YOLO-INT8 | 348.7 kHz | 488.4 kHz | 38.69% |
| Gemma3-4B | 367.5 kHz | 645.6 kHz | 18.96% |
| ResNet-50 FP32 | 362.5 kHz | 514.9 kHz | 28.84% |

## Active versus external idle

| Workload | Idle runs | Idle duration | Active/idle | Idle-overlap of active | Additional under load |
|---|---:|---:|---:|---:|---:|
| GEMM-FP32 | 11 | 110.0 s | 11.42 dB | 0.78% | 99.22% |
| GEMM-INT8 | 11 | 110.0 s | 4.53 dB | 2.77% | 97.23% |
| YOLO-FP32 | 11 | 110.0 s | 7.75 dB | 1.93% | 98.07% |
| YOLO-INT8 | 11 | 110.0 s | 8.30 dB | 1.81% | 98.19% |
| Gemma3-4B | 11 | 110.0 s | 5.86 dB | 1.23% | 98.77% |
| ResNet-50 FP32 | 11 | 110.0 s | 8.62 dB | 1.65% | 98.35% |

Every exact-rate idle record is analysed at its full physical duration with the same Welch segment-duration and overlap policy as active records. One PSD per physical idle run enters the cross-run median, so longer idle records improve within-run averaging without receiving additional cross-run weight.

The overlap/additional decomposition is descriptive: min(active,idle) is the idle-overlapping component and max(active-idle,0) is additional variance observed under load. Because active and idle are independent acquisitions, this is not phase-coherent or causal source separation.

The 5-MS/s curves are the fair cross-workload comparison. Faster Tektronix records are used only to check how much variance lies above the 2.5-MHz PicoScope Nyquist limit.

Frequencies are reported directly in hertz by Welch using the configured sampling rate in samples per second. The DFT kernel already contains the 2*pi phase factor; no additional continuous-transform 1/(2*pi) or 1/sqrt(2*pi) normalisation is introduced. The derivative of the cumulative distribution with respect to linear frequency is the normalised PSD. The generated per-decade figure instead shows dC/dlog10(f) = ln(10) f dC/df.

## 2-kS/s energy sufficiency

| Workload | Setup | 1% minimum tested duration | 0.5% minimum tested duration |
|---|---|---:|---:|
| Gemma3-4B | PicoScope/INA225 setup | 0.500 s | 2.000 s |
| Gemma3-4B | Tektronix setup | 1.000 s | 5.000 s |
| GEMM-FP32 | PicoScope/INA225 setup | 1.000 s | 5.000 s |
| GEMM-FP32 | Tektronix setup | 1.000 s | 5.000 s |
| GEMM-INT8 | PicoScope/INA225 setup | 0.200 s | 1.000 s |
| GEMM-INT8 | Tektronix setup | 0.500 s | 2.000 s |
| ResNet-50 FP32 | PicoScope/INA225 setup | 1.000 s | 5.000 s |
| ResNet-50 FP32 | Tektronix setup | 1.000 s | 5.000 s |
| YOLO-FP32 | PicoScope/INA225 setup | 1.000 s | 5.000 s |
| YOLO-FP32 | Tektronix setup | 1.000 s | 5.000 s |
| YOLO-INT8 | PicoScope/INA225 setup | 1.000 s | 5.000 s |
| YOLO-INT8 | Tektronix setup | 2.000 s | 10.000 s |

## Method boundary

- Common reference: all lower rates are reconstructed from the same 5-MS/s physical execution; this isolates the sampling effect.
- Direct rate validation: the recorded rate sweep consists of separate executions and therefore includes run-to-run, acquisition, offset, and setup effects.
- The short paired-scope records support windows only up to their physical duration; the 104-s GEMM-FP16 analysis remains the long-duration anchor.
- Missing or incomplete workloads are skipped and remain visible in the inventory.
