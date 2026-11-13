| Rep | P1 ms | P2 ms | Post ms | Raw FPS | Completed FPS | Completed/raw |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 10.378 | 8.760 | 2.098 | 96 | 96 | 0.999865 |
| 2 | 10.411 | 8.753 | 2.097 | 96 | 96 | 0.999869 |
| 3 | 10.412 | 8.746 | 2.120 | 96 | 96 | 0.999880 |

Three repetitions of 1,000 measured completions cycling 32 images, after 100 drained warm-ups. P1/P2/Post values are means within each repetition; observed throughput includes pipeline backpressure. Raw and completed FPS remain distinct at full precision in CSV. All 32 images pass recorded parity; the separate postflight is outside timing. These are existing measurements, not a new run.
