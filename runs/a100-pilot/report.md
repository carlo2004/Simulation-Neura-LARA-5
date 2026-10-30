# Entwicklungsvergleich

Development pilot; fixed paired cases. Observed model ranking is provisional, not a held-out result.

Hardware: NVIDIA A100-SXM4-40GB

| Modell | Blöcke | Aufgabe | Erfolg / bewertet / geplant | Technikfehler | Abbruch | Offen | Ausgabe Token/s |
|---|---:|---|---:|---:|---:|---:|---:|
| qwen4b | 1 | move-right | 4 / 5 / 5 | 0 | 0 | 0 | 99.01 |
| qwen4b | 1 | red-on-blue-jitter | 0 / 5 / 5 | 0 | 0 | 0 | 97.18 |
| qwen9b | 1 | move-right | 5 / 5 / 5 | 0 | 0 | 0 | 122.07 |
| qwen9b | 1 | red-on-blue-jitter | 0 / 5 / 5 | 0 | 0 | 0 | 121.69 |
| ministral8b | 1 | move-right | 5 / 5 / 5 | 0 | 0 | 0 | 115.66 |
| ministral8b | 1 | red-on-blue-jitter | 0 / 5 / 5 | 0 | 0 | 0 | 116.13 |
| nemotron8b | 1 | move-right | 5 / 5 / 5 | 0 | 0 | 0 | 83.98 |
| nemotron8b | 1 | red-on-blue-jitter | 0 / 5 / 5 | 0 | 0 | 0 | 86.81 |
| dory4b | 1 | move-right | 0 / 0 / 5 | 5 | 0 | 0 | — |
| dory4b | 1 | red-on-blue-jitter | 0 / 0 / 5 | 5 | 0 | 0 | — |
| granite8b | 1 | move-right | 2 / 5 / 5 | 0 | 0 | 0 | 107.98 |
| granite8b | 1 | red-on-blue-jitter | 1 / 5 / 5 | 0 | 0 | 0 | 107.75 |
| lfm2.6b | 1 | move-right | 5 / 5 / 5 | 0 | 0 | 0 | 184.61 |
| lfm2.6b | 1 | red-on-blue-jitter | 0 / 5 / 5 | 0 | 0 | 0 | 185.08 |

Modell-/Budgetfehler zählen als Misserfolg. Technikfehler, Abbrüche und offene Versuche bleiben in den geplanten Fallzahlen sichtbar. Token/s gewichtet native Decode-Schritte mit ihrer Decode-Zeit; unterschiedliche Modellprofile/Quantisierungen bleiben eigene Bedingungen.

Rohdaten liegen je Episode unverändert neben deren Manifest. Keine automatische Wiederholung vorhandener Versuche; ein neuer Versuch benötigt einen neuen Plan.
