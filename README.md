# LARA Stack Lab

Interaktive MuJoCo-Simulation eines NEURA LARA 5 mit Greifer, Kontaktphysik und lokaler LLM-Steuerung in Python. Das Seminarziel: prüfen, ob kleine Sprachmodelle aus Sprache brauchbare Roboterprogramme erzeugen, und später ein Finetuning mit denselben Aufgaben vergleichen.

## Schnell starten

Voraussetzung: Git, Python **3.12 oder neuer**, Internet für die erste Einrichtung. CI prüft Python 3.12 und 3.13 auf Linux und Windows. Ein Desktop wird für das 3D-Fenster benötigt; Tests funktionieren ohne Fenster.

```bash
git clone https://github.com/carlo2004/Simulation-Neura-LARA-5.git
cd Simulation-Neura-LARA-5
python bootstrap.py --test
```

Die Einrichtung legt eine lokale Python-Umgebung an, installiert das Projekt und erzeugt die geprüfte Robotergeometrie. Danach **diesen Interpreter** verwenden:

| System | Python-Befehl |
|---|---|
| Linux / macOS | `.venv/bin/python` |
| Windows PowerShell | `.\.venv\Scripts\python.exe` |

Beispiele für Linux; unter Windows den Interpreter aus der Tabelle einsetzen:

```bash
.venv/bin/python -m stacklab demo --gui
.venv/bin/python -m stacklab console --axes
.venv/bin/python -m stacklab models
.venv/bin/python -m stacklab setup --model qwen9b
.venv/bin/python -m stacklab chat --model qwen9b --no-thinking --axes
```

Im Chat z. B. `Bewege den Greifer 5 cm nach rechts.` eingeben. Code, Aktionen und echte Zustandsrückmeldungen werden angezeigt. `/stop` unterbricht die Aufgabe; `/help` zeigt weitere Befehle. Im manuellen Terminal helfen `help`, `objects` und die [Beispiele](examples/).

**Nach einem Update aus einem alten Checkout einmal `python bootstrap.py --test` ausführen.** Die bisherigen einzelnen Startskripte wurden durch Paketbefehle ersetzt; siehe [Migration](docs/history/README.md).

## Was funktioniert und was noch offen ist

Der Roboter kann über Terminal, Tastatur und Python gesteuert werden. Szenen, Objektpositionen, zusätzliche Würfel und importierte Meshes sind anpassbar. Achsen und Stapelprüfung sind optional einblendbar. Die Physik-Kontrollprogramme stapeln mit echten Kontakten und unabhängigen Stabilitätsprüfungen.

Die Modellanbindung unterstützt Qwen3.5-4B/9B, Ministral 3 8B Reasoning, Nemotron 3.5 Bolt, Nemotron Labs Dory1.0-4B, IBM Granite 4.2 8B und LiquidAI LFM2.5-2.6B. Chat und Benchmark zeigen echte Tokens pro Sekunde, Prompttempo und Ladezeit an. Dory benötigt einen einmaligen separaten Quellbuild; die [Modellanleitung](docs/models.md) erklärt die Voraussetzungen. In den bisherigen echten Versuchen gelangen einfache Bewegungen; **zuverlässiges Stapeln durch die unveränderten Modelle ist noch nicht erreicht**. Negative Ergebnisse stehen im [Versuchsindex](experiments/README.md). Softwaretests mit vorgegebenen Antworten sind kein Nachweis für Modellqualität.

Die Geometrie und Kinematik stammen aus einer RoboDK-Quelldatei. Dynamik, Greifer und Regelung enthalten eigene Annahmen; dies ist eine Forschungsumgebung für die Tischaufgabe, kein validierter digitaler Zwilling. [Herkunft und Lizenzen](assets/sources/NOTICE.md).

## Orientierung

| Ort | Inhalt |
|---|---|
| `stacklab/sim/` | Roboter, Physik, manuelle Steuerung, Overlays, Mesh-Import |
| `stacklab/llm/` | Modellkatalog, lokale Inferenz, Feedback-Agent |
| `stacklab/cli/` | Terminalbefehle und Prozesseinstieg |
| `stacklab/config.py`, `policy.py`, `evaluation.py` | Szenendaten, ausführbare Roboter-API, unabhängige Bewertung |
| `config/`, `scenes/` | Modellrevisionen, Prompts, Szenen |
| `assets/` | Roboterdefinitionen, Quellen und erzeugte Geometrie |
| `tests/`, `tools/` | Softwaretests und ausführbare Physikprüfungen |
| `examples/` | Kleine Terminal- und Python-Beispiele |
| `experiments/` | Ausgewählte tatsächliche Versuchsdaten mit Herkunft |
| `docs/` | Bedienung, Architektur, Versuchsablauf, Entscheidungsgeschichte |
| `runs/` | Neue Ergebnisse; nicht versioniert |

[Bedienung und Einrichtung](docs/start.md) · [Modelle und Live-Chat](docs/models.md) · [Einstellungen](docs/settings.md) · [Architektur erweitern](docs/architecture.md) · [Prüfen und wissenschaftlich auswerten](docs/validation.md) · [Ergebnisarchitektur und Vergleichsplan](docs/results.md)

Für wiederholbare Entwicklungspiloten gibt es `stacklab experiment plan`, `run` und `report`: dieselben Startfälle über mehrere Modelle und Blockbudgets, getrennte Szenen-/Generierungsseeds und automatisch JSON, CSV und Markdown. [Vergleich Schritt für Schritt](docs/experiments.md).

Modellgewichte liegen standardmäßig im lokalen Cache. Mit `STACKLAB_CACHE_DIR` kann ein anderer Datenträger gewählt werden; `STACKLAB_RUN_DIR` steuert den Ergebnisordner. Das Projekt wird aus diesem Checkout mit editierbarer Installation betrieben.
