# Paper-Ergänzung: vollständige ResNet-Replikation

In `09_vendor_toolchains.tex` im vorgesehenen Mechanismusabsatz die zwei bisher vorgeschlagenen Sätze zur Native-only-ResNet-Serie ersetzen. Die neue Serie umfasst ausschließlich 40 frische Prozesse; die alten 20 Native-Prozesse bleiben separat im Supplement.

**Englischer Ersatztext (zwei Sätze):**

For the ResNet pair selected for a known reversal, a separate forty-process replication in five jointly randomized blocks yields a scheduling-by-runtime interaction of 3.429 (nominal 95% interval 3.353–3.506), supporting the same direction as RegNet. Limiting execution to one outstanding task changes the b095/b002 throughput ratios from 0.606 to 0.836 for Generic and from 2.060 to 0.829 for Native, reversing the Native ordering while Generic continues to prefer b002.

Alle vier Cut-Verhältnisse mit Intervallen, die einzelnen Blockwerte, Zell-/Rohdatentabellen, Funktionsbelege und Protokolldetails gehören ins Supplement. Dort ausdrücklich festhalten: I ist ein Verhältnis von Cut-Verhältnissen; fünf Blöcke und nominale Intervalle; Auswahl wegen bekannter Rangumkehr; aktuelle Laufzeitketten; keine isolierten Kopier-/Konvertierungskosten und keine allgemeine Verbreitungsaussage. Die RegNet-Effektgröße ist ein separater Vergleich, kein Gleichheitsnachweis.

Keine zweite neue Hauptabbildung und keine neue Hauptsektion. Die im bisherigen Vorschlag vorgesehene RegNet-Mechanismusabbildung bleibt die einzige neue Hauptabbildung. Die bereits zur Verlagerung ins Supplement vorgesehenen Compiler-/HAR-Diagnosen und die Vier-Cut-Stage-Cost-Diagnose bleiben dort; die zwei neuen Sätze ersetzen die ältere ResNet-Passage innerhalb dieses bestehenden Platzbudgets. Ziel bleiben zehn Haupttextseiten. Das Manuskript wurde nicht geändert.
