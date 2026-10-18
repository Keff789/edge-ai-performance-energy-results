# Paper delta: drei Befunde, bestehende Struktur

Drei Fragen begrenzen die Hauptbefunde. Audit als Methode. Ziel: zehn Haupttextseiten. Die Mechanismusstudie erhält höchstens eine neue Grafik.

## Methodenabsicherung

**English replacement passage.** We audit all 450 configurations using artifact hashes and contracts. These link dataset quality, compiled artifacts, executed runners, timing and energy receipts. The numerical 5% relative quality-loss rule admits 407 configurations: 187 Native splits, 187 Generic splits and 33 Full alternatives. All fourteen headline configurations remain admissible. No stronger Full reference is removed. Timers include task completion, required postprocessing and materialization. The throughput contract starts from prepared input. Distinct-input association is separately verified for eight exact R14 configurations. These checks establish neither equal accuracy nor matched historical device conditions.

**Redaktion.** In `04_protocol.tex`, „Task quality and uncertainty“, ergänzen und den pauschalen Restriktionsverweis konkretisieren. Datensatzumfang, Qualitätsformel und Unsicherheitsgrenzen erhalten. `supplement.tex`, „Source limitations“, ersetzen. Originalflags, Receipt-Versionen, Producer-Ketten und Ausschlusslisten ausschließlich dort erklären.

## 1. Wann lohnt sich ein Split gegenüber der besten verfügbaren Full-Ausführung?

**English replacement passage.** The fastest split beats the strongest available Full for six of seven models. Three also use less energy per image. RegNet-X reaches 2.54 times the Full throughput at 49.8% lower energy. All seven pairs meet the numerical quality rule, which permits accuracy differences. Full remains preferable for YOLO11l. These global comparisons allow different hosts. A large gain against a weaker local Full does not establish the same deployment benefit.

**Redaktion.** `05_benefits.tex`, „Global and host-specific benefits differ“, kürzen. Aktive `best_cases_table.tex`, `r14_winner_quality.tex` und die Referenzdefinition erhalten. Die konkreten ResNet-/YOLOv7-Quotienten und YOLO26m-Energiealternative ins Supplement verschieben. Keine neue Nutzenabbildung.

## 2. Wie zuverlässig lässt sich ein guter Split mit begrenztem Messbudget auswählen?

**English replacement passage.** We add one fixed device-specific ridge correction to the Generic proxy. It fits the log Native/Generic ratio using prefix compute fraction and log(1+boundary bytes). The objective is mean squared error plus the squared slopes, with an unpenalized intercept. Each fold holds out an entire classifier architecture and uses only training statistics for scaling. All methods use the same 151 admissible candidates in nine equally weighted groups.

| Method | Mean Native throughput loss %, k=1 / 3 / 5 |
|---|---:|
| Generic | 32.80 / 23.77 / 20.45 |
| Calibrated Generic | 28.32 / 23.15 / 15.43 |
| Uniform Random, exact expectation | 32.29 / 15.41 / 9.10 |
| Boundary bytes, recomputed | 32.97 / 21.75 / 8.86 |

Calibration includes the exact Native winner in 1/9, 3/9 and 4/9 shortlists. Its improvement comes from DeepX. H10 worsens at every budget and H8 worsens at five. Random sampling has lower expected loss than calibration at three and five. The bytes rule is newly applied to verified graphs. Historical graph scores retain their separate runtime reference.

Retrospective validation on three known architectures does not establish generalization. Random expectations are distinct from measurement uncertainty. The budget counts held-out Native trials. Generic acquisition, Native training, compilation and quality evaluation cost extra. Training uses 151 distinct Native configurations. Total search-cost savings are unmeasured. Detectors remain separate: Generic loses 1.78% at one trial versus 14.09% for Random. Twelve groups have three cuts each. Three trials exhaust them and five are unavailable.

**Redaktion.** Ausschließlich aktive `r14_budget_table.tex` erweitern, einschließlich Gewinnerabdeckung und Detektorgrenze. In `06_selection.tex`, „Quality filtering and measurement budgets“, die letzten beiden Absätze ersetzen. Die Graphscore-Vergleichsstudie auf einen Verweis kürzen und ins Supplement verschieben. Foldparameter und Geräteverschlechterungen dort vollständig erhalten. Keine zusätzliche Baseline-Sektion.

## 3. Warum kann sich seine Rangfolge bei der tatsächlichen Ausführung umkehren?

**English replacement passage.** Five randomized RegNet process blocks reproduce the ranking reversal. The b123/b052 throughput ratio is 0.660 for Generic and 3.371 for Native under their productive schedules. Limiting execution to one outstanding task changes these ratios to 1.029 and 1.028. Both runners then prefer b123 slightly. The scheduling-by-runtime interaction is 5.108, with a nominal 95% interval of 4.990–5.229. This is a ratio of cut ratios, not a per-cut speedup. Native b052 shows substantial consumer backpressure, while b123 has shorter synchronized suffix service. The intervention establishes a scheduling-dependent ranking difference in these runtime chains. It does not isolate a copy or conversion cost. The unchanged Native intervention also reverses the ResNet cut ordering, from a b095/b002 ratio of 2.054 to 0.831 across five blocks. This twenty-process check contains no new Generic comparison. The two pairs were selected for known reversals. Current-code experiments do not reconstruct historical software conditions or establish prevalence across models.

**Redaktion.** In `09_vendor_toolchains.tex` die Compiler-/HAR-Diagnosen und isolierten Formatproben ins Supplement verschieben. Die neue Fallstudie ersetzt „Testing composition with measured stage costs“ samt aktiver `stage_cost_summary.tex`. Auch „Predicting from independent stage costs“ in `04_protocol.tex` ins Supplement verschieben und durch den kurzen kontrollierten Versuchsvertrag ersetzen. Die Vier-Cut-Studie bleibt dort als Diagnose, ausdrücklich b059/b123 statt b052/b123. Höchstens eine Mechanismengrafik zeigt Prozessblockverhältnisse. Vollständige Faktorläufe und ResNet-Replikation ins Supplement. `08_discussion.tex`, Mechanismusabsatz und Schlussfolgerung, danach ersetzen. In `main.tex`, Abstract ab „A separate experiment“, entsprechend aktualisieren.
