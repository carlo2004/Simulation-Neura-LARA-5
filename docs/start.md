# Einrichtung und Bedienung

## Eine Python-Umgebung

Im Projektordner `python bootstrap.py --test` ausführen. Es wird kein bestimmter globaler Python-Pfad vorausgesetzt. Das Setup verwendet den Python-Interpreter, mit dem es gestartet wurde, und installiert alle Abhängigkeiten einschließlich `trimesh` in die lokale Umgebung.

Nach erfolgreicher Einrichtung den ausgegebenen Interpreter verwenden. Linux-Beispiele:

```bash
.venv/bin/python -m stacklab doctor
.venv/bin/python -m stacklab console
.venv/bin/python -m stacklab demo --gui
.venv/bin/python -m stacklab demo --video
```

Windows: `.\.venv\Scripts\python.exe` statt `.venv/bin/python`. macOS-Fenster benötigen MuJoCos `mjpython`. Für Demo und Konsole z. B. `.venv/bin/mjpython -m stacklab console` verwenden. Chat und Benchmark erkennen den Wrapper automatisch in derselben Umgebung.

Jeder Befehl hat `--help`. `python -m stacklab --version` zeigt die Softwareversion.

## Terminal und Szenen

`console` öffnet die bestehende Befehlszeile. `help` beschreibt die tatsächliche Syntax. Beispiele:

```text
objects
pos red
move 0.40 0.00 0.25
jog x 0.02
open
close
axes on
stackviz red blue
check red blue
```

Die vollständigen Abläufe stehen in [examples](../examples/). Mit `--config scenes/three_cubes.json` eine andere Szene wählen. Die JSON-Dateien enthalten Objektform, Masse, Größe und Startposition; [Einstellungen](settings.md) erklärt ihre Bedeutung. Achsen, Auswertungsboxen und die Einstellungstafel sind optional. Die Einstellungstafel lässt sich einklappen.

Für die flüssigste Ansicht zunächst ohne `--axes` und `--stackviz` starten.
Die [Performance-Einstellungen](settings.md#performance-und-empfohlener-start) enthalten
Startbefehle für lokale Modelle und den Colab-Remote-Modus.

Die Konsole enthält manuelle Steuerung und Mesh-Import. Für Physikversuche eignet sich die vorbereitete Ente aus `scenes/duck.json`; fremde Meshes werden als konvexe Kollisionshülle importiert. Hohlräume und Texturen sind dabei keine detaillierte Kollisionsgeometrie.

## Eigener Python-Code

[examples/python_program.py](../examples/python_program.py) zeigt die direkte Simulations-API:

```python
from contextlib import closing
from stacklab.config import Config
from stacklab.sim.robot import Simulation

with closing(Simulation(Config(), gui=True)) as robot:
    robot.move_to([0.4, 0.0, 0.25])
    robot.gripper(closed=False)
```

Direkter eigener Python-Code hat die normale Simulations-API. Modellcode läuft durch die begrenzte API in `stacklab/policy.py`; [robot_api.md](../config/prompts/robot_api.md) beschreibt die verfügbaren Modellbefehle.

## Dateien und Fehlersuche

Neue Ergebnisse landen unter `runs/`, Modelle unter dem bisherigen Cache. Diese Dateien werden nicht in Git aufgenommen. `STACKLAB_RUN_DIR` und `STACKLAB_CACHE_DIR` können vor dem Start auf andere Ordner gesetzt werden. Bereits geladene Gewichte werden geprüft und wiederverwendet.

Wenn ein Paket fehlt, `doctor` mit demselben Interpreter ausführen, der die Simulation startet. Bei Änderungen an der Paketstruktur einmal `python bootstrap.py --test` ausführen. Erzeugte Modelldaten werden aus SHA-256-geprüften Quellen wiederhergestellt.
