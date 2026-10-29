# Entwicklungsvergleich

Development pilot; not a held-out test or a normalized model-speed ranking.

| Modell | Blöcke | Aufgabe | Erfolg / bewertet / geplant | Technikfehler | Abbruch | Offen | Ausgabe Token/s |
|---|---:|---|---:|---:|---:|---:|---:|
| granite8b | 1 | move-right | 1 / 1 / 1 | 0 | 0 | 0 | 6.93 |
| granite8b | 1 | red-on-blue | 0 / 1 / 1 | 0 | 0 | 0 | 7.84 |
| granite8b | 4 | move-right | 1 / 1 / 1 | 0 | 0 | 0 | 7.38 |
| granite8b | 4 | red-on-blue | 0 / 1 / 1 | 0 | 0 | 0 | 6.70 |
| lfm2.6b | 1 | move-right | 1 / 1 / 1 | 0 | 0 | 0 | 20.93 |
| lfm2.6b | 1 | red-on-blue | 0 / 1 / 1 | 0 | 0 | 0 | 23.30 |
| lfm2.6b | 4 | move-right | 1 / 1 / 1 | 0 | 0 | 0 | 21.60 |
| lfm2.6b | 4 | red-on-blue | 0 / 1 / 1 | 0 | 0 | 0 | 21.55 |

Modell-/Budgetfehler zählen als Misserfolg. Technikfehler, Abbrüche und offene Versuche bleiben in den geplanten Fallzahlen sichtbar. Token/s gewichtet native Decode-Schritte mit ihrer Decode-Zeit; unterschiedliche Modellprofile/Quantisierungen bleiben eigene Bedingungen.

Rohdaten liegen je Episode unverändert neben deren Manifest. Keine automatische Wiederholung vorhandener Versuche; ein neuer Versuch benötigt einen neuen Plan.
