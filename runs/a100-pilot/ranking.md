# Vorläufiger Modellvergleich

GPU: NVIDIA A100-SXM4-40GB

Gleiche Fälle und Budgets; Qualität und Geschwindigkeit bleiben getrennt. Reihenfolge nach erfolgreichen/geplanten Episoden, Gleichstände bleiben Gleichstände. Unvollständige Versuchsreihen haben noch keine endgültige Erfolgsquote.

| Modell | Blöcke | Erfolg / bewertet / geplant | Technik | Offen | Ausgabe Token/s | Erstes Token s | Median Episode s |
|---|---:|---:|---:|---:|---:|---:|---:|
| lfm2.6b | 1 | 5 / 10 / 10 | 0 | 0 | 184.90 | 0.14 | 10.06 |
| ministral8b | 1 | 5 / 10 / 10 | 0 | 0 | 115.94 | 0.43 | 13.74 |
| nemotron8b | 1 | 5 / 10 / 10 | 0 | 0 | 86.29 | 0.34 | 6.77 |
| qwen9b | 1 | 5 / 10 / 10 | 0 | 0 | 121.75 | 0.49 | 12.78 |
| qwen4b | 1 | 4 / 10 / 10 | 0 | 0 | 97.31 | 0.32 | 6.18 |
| granite8b | 1 | 3 / 10 / 10 | 0 | 0 | 107.85 | 0.44 | 14.97 |
| dory4b | 1 | 0 / 0 / 10 | 10 | 0 | — | — | — |

Technikausfälle sind keine nachgewiesenen Modellfehler und werden separat ausgewiesen. Die Modellquote verwendet nur bewertete Episoden; die vollständige End-to-End-Quote behält alle geplanten Versuche im Nenner. Details pro Aufgabe stehen in report.md. Die 20 Stabilitätsmessungen zählen als eine Episode.

Bei zehn Episoden pro Modell ist dies eine Vorauswahl. Kleine Unterschiede belegen keinen generellen Sieger. Modelle haben ihre dokumentierten Sampling-/Thinking- und Quantisierungsprofile; das Ergebnis gilt für diese vollständigen Konfigurationen.
