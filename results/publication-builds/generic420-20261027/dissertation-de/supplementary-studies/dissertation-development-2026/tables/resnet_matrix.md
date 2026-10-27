Berichtete ResNet50/Imagenette-Entwicklungsmatrix. Bereiche behalten die unterschiedlichen ursprünglichen Zeitmessverträge. Nicht verfügbarer Durchsatz ist NA und wird nie aus der Latenz abgeleitet. Qualität ist als Anteil angegeben. Dies ist weder ImageNet noch B500.

| Ausführungspfad | Top-1 | Top-5 | Latenz (ms) | Durchsatz (FPS) | Status |
| --- | --- | --- | --- | --- | --- |
| TensorRT Full | 0.82 | 0.96 | 7.5–7.8 | 129–134 | gültige kanonische Full-Referenz. |
| DEEPX DX-M1 Full | 0.84 | 0.94 | 3.2 | 310.9 | gültiger Full-Backend-Pfad mit wiederholter Eingabe. |
| DEEPX DX-M1→TensorRT | 0.76–0.78 | 0.94 | 20.3–23.5 | 62.5–72.9 | Entwicklungsstand des Generic-Runners. |
| Hailo-8 Full/zusammengesetzt | 0.82–0.84 | 0.96 | 12–13 | NA | gültig mit Warnung zur quantisierten Schnittstelle. |
| Hailo-8→TensorRT | 0.82 | 0.96 | 9–10 | NA | gültig mit Schnittstellenwarnung. |
| TensorRT→Hailo-8 | 0.82 | 0.96 | 8–9 | NA | gültige, mit Aktivierungs-Proxys kalibrierte Stufe 2. |
| TensorRT→DEEPX DX-M1 | splitabhängig | splitabhängig | NA | NA | kompilierbar und erst nach einer Vertragsprüfung mit mehreren Eingaben zugelassen. |
