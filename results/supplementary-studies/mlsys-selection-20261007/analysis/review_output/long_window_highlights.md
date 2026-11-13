# Longer-window classification examples

The Full identity chosen using short Native performance remains fixed. Native and energy-window speedups use different measurement windows. FPS are rounded only for display; the CSV retains full precision.

| Model / cut | Setup | Native split (FPS) | Energy-window split (FPS) | Energy-window Full (FPS) | Native speedup | Energy-window speedup | Split window (s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MobileNet-V3-L/b074 | H10 | 1168 | 1147 | 751 | 1.50× | 1.53× | 62.03 |
| RegNet-X/b123 | H10 | 1521 | 1552 | 307 | 4.80× | 5.06× | 62.13 |
| ResNet-50/b095 | H10 | 1060 | 1064 | 508 | 2.02× | 2.10× | 62.26 |
