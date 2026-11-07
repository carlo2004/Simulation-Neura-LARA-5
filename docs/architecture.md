# Architektur

| Ort | Aufgabe |
|---|---|
| `web/` | Statische Workbench für Prompts, Live-Bilder, Replays und Ergebnisexport |
| `tools/start_colab_workbench.py` | Startet llama.cpp und den Runner auf Colab. Beide Modellendpunkte binden an Loopback. |
| `stacklab/cli/workbench.py` | Verbindet die Oberfläche mit den Modellendpunkten und startet pro Seite eine frische Simulation. |
| `stacklab/cli/prompt2robo.py` | Lädt den festgelegten Datensatz, baut die nativen HF-Nachrichten und exportiert SFT-Daten. |
| `stacklab/cli/_prompt2robo_worker.py` | Führt Programme in einem separaten Prozess aus und protokolliert die Zielprüfung. |
| `stacklab/workbench_policy.py` | Interpretiert den begrenzten Python-Umfang für Modellprogramme. |
| `stacklab/prompt2robo.py` | Bildet die Prompt2Robo-API und Startzustände auf den Simulator ab. |
| `stacklab/sim/` | LARA 5, MuJoCo-Physik, Rendering und manuelle Steuerung |
| `config/` | Prüfsummen, Modell- und Runtime-Downloads, Ausführungsbudgets |
| `notebooks/colab_workbench.ipynb` | Einrichtung und Start für die Team-Session |

Der Browser sendet den ausgewählten Szenenfall und den Prompt zum Runner. Dieser erzeugt einen Zero-shot-Dialog aus dem HF-Systemprompt, Objektliste und Auftrag. Der Modellserver liefert `def run(robot)` oder Text. Die Workbench leitet das Programm an den Simulationsworker weiter. Die Zielprüfung liest die gemessene Szene aus MuJoCo. Bei eigenen Prompts zeigt die Oberfläche Code, Bewegung und Endzustand. Beim unveränderten Datensatzauftrag erscheint zusätzlich die zugehörige Zielwertung.

Für den Vergleich durchlaufen A und B denselben Code. Beide starten aus derselben Szene und laufen nacheinander. Der SFT-Export verwendet dieselbe Funktion zum Erzeugen der Eingabe. [Details zu Daten und Antwortformat](prompt2robo.md) · [Bedienung](workbench.md)
