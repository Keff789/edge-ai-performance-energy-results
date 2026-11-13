# MobileNet-V3-L-Qualitätserholung

Top1 auf denselben 5,000 Bildern. Split b027 verwendet das zugehörige Beschleuniger-Präfix und TensorRT-Suffix. Dieses Beispiel belegt keine allgemeine Qualitätserholung für jeden Cut.

| System | CPU (%) | Beschleuniger-Full (%) | Split b027 (%) | Zugewinn (pp) |
| --- | --- | --- | --- | --- |
| H8 | 73.70 | 60.62 | 71.58 | 10.96 |
| H10 | 73.70 | 59.42 | 72.22 | 12.80 |
| DeepX | 73.70 | 71.72 | 72.22 | 0.50 |
