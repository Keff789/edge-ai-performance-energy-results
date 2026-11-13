# Stufenkosten

Unabhängiges Stufenkostenexperiment mit vier Cuts. Mediane Abschlussraten von Erzeuger, Verbraucher und Pipeline über drei Blöcke. Die Vorhersage ist min(F_P,F_C). Der Fehler ist der Median der blockweisen absoluten prozentualen Fehler. Diese Messreihe ist von Ausführungs- und Scheduling-Daten getrennt.

| Modell/Cut | F_P | F_C | F_PC | Fehler (%) |
| --- | ---: | ---: | ---: | ---: |
| ResNet/DX b045 | 230 | 669 | 225 | 2.24 |
| ResNet/DX b002 | 473 | 520 | 444 | 5.50 |
| RegNet/H10 b059 | 1565 | 500 | 477 | 4.77 |
| RegNet/H10 b123 | 1577 | 1999 | 1518 | 3.85 |
