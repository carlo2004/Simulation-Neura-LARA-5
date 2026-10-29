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
| `dory4b` | NVIDIA Nemotron Labs Dory1.0-4B, zwei Loops | 3,67 GB |
| `granite8b` | IBM Granite 4.2 8B | 5,35 GB |
| `lfm2.6b` | LiquidAI LFM2.5-2.6B | 1,67 GB |

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

## Geschwindigkeit sehen

Chat und Benchmark zeigen die Inferenzgeschwindigkeit standardmäßig an, auch ohne `--stream` oder `--show-thinking`:

```text
[Inferenz] Ausgabe: 18.2 Token/s | Prompt: 98.9 Token/s | 286 Ausgabetoken | ...
```

Das Beispiel ist eine Anzeigeform, keine Geschwindigkeitszusage. Die Werte stammen aus den Tokenzählern und Zeitmessungen von llama.cpp. Zeichen, Wörter und SSE-Nachrichten werden nicht als Tokens gezählt.

- **Ausgabe:** durchschnittliche Decodiergeschwindigkeit des laufenden Blocks, einschließlich vorhandener Denktokens. Verstecktes Reasoning zählt also mit.
- **Prompt:** Geschwindigkeit der tatsächlich verarbeiteten Eingabetokens. Bereits gecachter Kontext kann die Werte beeinflussen.
- **Laden:** Modellstart separat; bei einem warmen Modell null.
- **Erstes Token:** Wartezeit ab der Anfrage nach dem Laden; enthält die Promptverarbeitung.

Während Laden und Promptverarbeitung werden Phase und Zeit angezeigt. Ohne eine native Messung wird kein Decodiertempo erfunden. Falls nur Nutzungszähler verfügbar sind, wird ein Durchschnitt **inklusive Promptzeit** ausdrücklich anders bezeichnet.

Nach jedem Block liegen die Werte unter `round_XX/generation.json` im Feld `performance`; `result.json` enthält `inference_performance`. Auch abgeschnittene oder abgebrochene Antworten behalten ihre vorhandenen Teilmessungen. Der Episodendurchschnitt verwendet Token-/Zeit-Summen statt eines ungewichteten Mittels der einzelnen Geschwindigkeiten.

Die Decodiermessung folgt llama.cpp: Das erste Ausgabetoken entsteht noch aus dem Prompt-Durchlauf und zählt nicht als eigener Decodierschritt. Die Gesamtzahl der Ausgabetokens enthält es weiterhin. Das Messformat ab Schema 2 unterscheidet beide Zähler ausdrücklich; ältere Entwicklungsprotokolle werden beim Summieren entsprechend gelesen.

Die mitgelieferte Runtime arbeitet auf der **CPU**, auch wenn eine GPU im Rechner steckt. Modellarchitektur, Kontext, Denkbudget, Quantisierung, Arbeitsspeicher und Threadzahl beeinflussen die Laufzeit. Ein langsamer Start allein belegt keinen Quantisierungsfehler. Zum Vergleichen kalte und warme Starts getrennt betrachten und dieselben Einstellungen verwenden.

## Neue Modelle installieren

```bash
.venv/bin/python -m stacklab setup --model granite8b
.venv/bin/python -m stacklab setup --model lfm2.6b
.venv/bin/python -m stacklab chat --model granite8b --axes
```

Windows verwendet entsprechend `.\\.venv\\Scripts\\python.exe`. Alias, vollständige Modell-ID und eindeutiger Kurzname werden akzeptiert, z. B. `Qwen3.5-9B`.

Die neuen Gewichte stammen aus den offiziellen Hersteller-Repositories und sind auf Revision, Größe und SHA-256 festgelegt. Granite und LFM nutzen die bisherige Runtime. LFM2.5-2.6B ist ein Reasoning-Modell ohne abschaltbaren Denkmodus in seiner Vorlage; die Einbindung verwendet dessen Post-Training-Checkpoint, nicht `-Base`. Unterstützte Inferenz bedeutet nicht, dass jedes erzeugte Roboterprogramm korrekt ist.

LFM verwendet standardmäßig ein JSON-Schema für die äußere Antwort mit `code` und `done`. Im ersten freien Lauf lieferte es seine native Tool-Aufrufsyntax statt eines Python-Programms; mit der Formatvorgabe bestand der anschließende Bewegungstest. Der Inhalt von `code` wird vollständig vom Modell erzeugt und unverändert geprüft. Die Vorgabe steht als `response_format` im Katalog und in der tatsächlichen Anfrage; `constrained_decoding` wird protokolliert. Andere Modelle behalten ihre bisherige freie Ausgabe. Für einen wissenschaftlichen Vergleich müssen diese Transportbedingungen festgelegt und bei Basismodell und Fine-Tuning identisch bleiben.

Das belegt noch keine verlässliche Aufgabenbeendigung: In einer zusätzlichen freien LFM-Chatprobe wurde die Rechtsbewegung mehrfach wiederholt und das Blockbudget erreicht. Die Live-Anzeige funktionierte dabei; der Agent behauptete keinen unabhängigen Erfolg. Ein bestandener Benchmark mit extern festgelegtem Bewegungsziel und ein autonom beendeter freier Auftrag bleiben unterschiedliche Prüfungen.

### Dory: eigene Runtime

NVIDIAs [Dory-Anleitung](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-GGUF) verweist derzeit auf einen noch nicht in die reguläre llama.cpp-Version integrierten Modellpfad. Das Setup baut deshalb ausschließlich für Dory den empfohlenen Commit `98a74c97ea09ac72f6ceda1559808fc0a2f447ce`. Die vorhandenen Modelle behalten `b11951`.

Benötigt werden Git, CMake und ein C++-Compiler. CMake kann in dieselbe Python-Umgebung installiert werden:

```bash
.venv/bin/python -m pip install cmake
.venv/bin/python -m stacklab setup --model dory4b
.venv/bin/python -m stacklab chat --model dory4b
```

Unter Windows werden C++ Build Tools benötigt, unter macOS die Command Line Tools, unter Linux ein C++-Compiler und ein Buildwerkzeug. Der einmalige Build verwendet einen eigenen Cacheordner; Diagnoseausgaben liegen dort in `build.log`. Ein unveränderter fertiger Build wird wiederverwendet und benötigt beim normalen Start keinen Compiler. Source-Commit, Buildoptionen und Binärhash werden protokolliert. CUDA wird für diesen CPU-Pfad nicht benötigt.

Dory läuft standardmäßig mit zwei rekurrenten Loops. Diese Einstellung steht mit den übrigen Serverargumenten im Katalog und im Generierungsprotokoll. Mehr Loops ändern den Rechenaufwand pro Token und müssen bei Vergleichen berücksichtigt werden. Gewichte sind Q5_K_M; Granite und LFM verwenden Q4_K_M. Qwens bisherige Quantisierung bleibt unverändert.

Quellen: [NVIDIA Dory GGUF](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-GGUF), [IBM Granite GGUF](https://huggingface.co/ibm-granite/granite-4.2-8b-GGUF), [LiquidAI LFM GGUF](https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF), [llama.cpp-Server und `timings_per_token`](https://github.com/ggml-org/llama.cpp/blob/b11951/tools/server/README.md).

## Wissenschaftlicher Status

Die bisherigen Basismodelle bewegen den Greifer, stapeln aber noch nicht zuverlässig. Die nächste wissenschaftliche Aufgabe ist ein eingefrorenes Entwicklungs-/Testset und ein kontrollierter Originalmodell-/Finetuning-Vergleich. Der Code bietet Ausführung, Feedback, Protokolle und unabhängige Metriken; er behauptet keine bereits nachgewiesene Finetuning-Verbesserung.
