# Vorhandene Energiekalibrierung

Auszug aus der gespeicherten Anpassung und den Qualitätsprüfungen. Keine neue Anpassung oder Messung. Der Achsenabschnitt ist auf null festgelegt. Anpassungsresiduen, Punktstreuung und Wiederholungsvariabilität bilden kein vollständiges Unsicherheitsbudget mit Fehlerfortpflanzung für Sensor und Referenz. Ein gemeinsamer multiplikativer Faktor kürzt sich innerhalb eines Systems heraus. Für nichtlineare oder lastabhängige Fehler gilt dies nicht zwingend.

| System | Energiefälle | Abtastrate (Samples/s) | Skalierungsfaktor | Max. Anpassungsresiduum (%) | Punktstreuung (%) | Leerlaufdrift (W) | Gespeicherte Prüfung bestanden | Warnungen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H8 | 77 | 2000 | 0.913634 | 1.45 | 1.84 | 0.003 | Ja | Keine |
| H10 | 77 | 2000 | 0.896397 | 1.60 | 2.03 | 0.005 | Ja | point_factor_spread_too_high;scale_factor_outside_configured_range |
| DeepX | 77 | 2000 | 0.903508 | 0.54 | 0.68 | 0.005 | Ja | Keine |
