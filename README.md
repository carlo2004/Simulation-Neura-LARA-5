# LARA Stack Lab

Workbench für den Zero-shot-Vergleich von Basismodell und Fine-Tuning auf dem simulierten NEURA LARA 5. Beide Modelle erhalten dieselbe Startszene und bei Bedarf denselben Auftrag. Die Workbench zeigt die erzeugten Programme, die Bewegung in MuJoCo, die Zielprüfung und Tokens pro Sekunde.

## Im Browser starten

1. Starte den Runner mit dem [Colab-Notebook](https://colab.research.google.com/github/carlo2004/Simulation-Neura-LARA-5/blob/main/notebooks/colab_workbench.ipynb). Für den Modellvergleich gib die beiden GGUF-Pfade oder ein Basis-GGUF mit LoRA-Adapter an.
2. Für die Team-Session leite den Runner über Colab-SSH und ngrok weiter. [Startanleitung](docs/colab-workbench.md)
3. Öffne die [Vercel-Workbench](https://simulation-neura-lara-5.vercel.app/), verbinde den Runner und wähle eine Startszene. **Beide testen** startet die Modelle mit demselben Prompt, solange **Gleicher Prompt für beide Modelle** aktiv ist.

Mit dem Referenzmodus kannst du die Szene und das Stapeln auch ohne Modellgewichte ausprobieren. Referenzvideos und der Trainingsdaten-Viewer sind auch ohne Runner verfügbar.

## Lokal entwickeln

Git und Python 3.12 oder 3.13. Die erste Einrichtung lädt die festgelegte Robotergeometrie und installiert die Abhängigkeiten in eine lokale Umgebung.

~~~bash
git clone https://github.com/carlo2004/Simulation-Neura-LARA-5.git
cd Simulation-Neura-LARA-5
python bootstrap.py --test
.venv/bin/python -m stacklab demo --gui
.venv/bin/python -m stacklab console
~~~

Unter Windows verwende `.\.venv\Scripts\python.exe`. Für das native Fenster unter macOS verwende `.venv/bin/mjpython`. [Simulator bedienen](docs/start.md)

## Daten und Code

- [Prompt2Robo-Datensatz wiedergeben und für SFT exportieren](docs/prompt2robo.md)
- [Workbench, Modellformat und Berichte](docs/workbench.md)
- [Architektur und Verantwortlichkeiten](docs/architecture.md)
- [Prüfungen](docs/validation.md) und [frühere Versuchsstände](docs/archive.md)

Vercel liefert die statische Oberfläche. Der Runner führt Modell und Simulation aus. Lokale Ergebnisse landen unter `runs/`. Die Geometrie und Kinematik stammen aus dem RoboDK-Modell. Dynamik und Greifer enthalten Simulationsannahmen. [Modellquellen und Lizenzen](assets/sources/NOTICE.md)
