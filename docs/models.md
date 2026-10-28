# Lokale Modelle und Feedback

## Auswahl und Start

```bash
.venv/bin/python -m stacklab models
.venv/bin/python -m stacklab setup --model qwen9b
.venv/bin/python -m stacklab chat --model qwen9b --no-thinking --axes
```

Die Modellaliase stehen im [Katalog](../config/models.lock.json). Er pinnt Revisionen, GGUF-Dateien, SHA-256, Runtime und Sampling. Gewichte und CPU-Runtime werden lokal geladen. Das Setup lädt ohne `--all` nur das gewählte Modell; es löscht keine anderen Gewichte.

| Alias | Originalmodell | Ungefähre GGUF-Größe |
|---|---|---:|
| `qwen4b` | Qwen3.5-4B, frühere Baseline | 2,74 GB |
| `qwen9b` | Qwen3.5-9B | 5,68 GB |
| `ministral8b` | Ministral 3 8B Reasoning 2512 | 5,20 GB |
| `nemotron8b` | NVIDIA Nemotron 3.5 Bolt E4B 4GB | 6,18 GB |

Die Modellgrößen beziehen sich auf die Originalparameter, nicht die quantisierte Dateigröße. Bolt hat etwa 8 Milliarden Gesamtparameter; E4B bezeichnet eine effektive Größe. Betrieb benötigt zusätzlich Arbeitsspeicher für Kontext und Runtime. Downloads prüfen freien Speicher und reservieren 512 MiB zusätzlich; ausreichend Platz für die Runtime einplanen.

Für den ersten sichtbaren Test Qwen9B ohne Thinking verwenden. Das ist eine praktische Wahl aus den bisherigen Entwicklungsproben, kein genereller Qualitätsnachweis. Ministral ist ein Reasoning-Modell und bietet hier keinen abschaltbaren Denkmodus. Reasoning-Ausgabetokens und Kontext müssen zum gewählten Budget passen.

## Live bedienen

`/help` zeigt die Befehle. Natürliche Sprache an den Agenten schicken, z. B. `Bewege den Greifer 5 cm nach rechts`. Weltachsen: rechts +X, links −X, vorwärts +Y, oben +Z. Die Kamera ändert diese Bedeutung nicht.

`--stream` zeigt Antworttext während der Generierung; `--show-thinking` zeigt einen vorhandenen Reasoning-Stream. `/stop` oder Ctrl+C unterbricht. Während die CPU das Modell ausführt, pausiert die Physik; das Fenster bleibt im Hauptthread bedienbar.

Wiederholbare Texte statt interaktiver Eingabe:

```bash
.venv/bin/python -m stacklab chat --headless --model qwen9b --no-thinking --prompt "5 cm nach rechts" --prompt "5 cm nach links"
.venv/bin/python -m stacklab benchmark --model qwen9b --no-thinking --case move-right --feedback-rounds 4
.venv/bin/python -m stacklab benchmark --model qwen9b --case red-on-blue --feedback-rounds 4
```

`--max-rounds` im Chat und `--feedback-rounds` im Benchmark bestimmen die Zahl der Programmblöcke. `--max-tokens`, `--thinking-budget`, `--threads` und die Timeouts steuern Ressourcen. `--help` ist die Referenz für Optionen.

Der Agent erhält nur dokumentierte Einzelbefehle und echte Beobachtungen. Er bekommt kein fertiges Stapelprogramm als Beispiel. [API-Prompt](../config/prompts/robot_api.md) und [Versuchsdaten](../experiments/README.md) sind einsehbar.

## Wissenschaftlicher Status

Die bisherigen Basismodelle bewegen den Greifer, stapeln aber noch nicht zuverlässig. Die nächste wissenschaftliche Aufgabe ist ein eingefrorenes Entwicklungs-/Testset und ein kontrollierter Originalmodell-/Finetuning-Vergleich. Der Code bietet Ausführung, Feedback, Protokolle und unabhängige Metriken; er behauptet keine bereits nachgewiesene Finetuning-Verbesserung.
