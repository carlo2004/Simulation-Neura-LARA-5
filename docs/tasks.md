# Folgeaufgaben in der LARA-Simulation

Die Aufgaben verwenden je nach Fall einen bis fünf Würfel mit 40 mm Seitenlänge. Szene, Aufgabenbeschreibung und Prüfziel stehen im Aufgabenkatalog. Objekt-IDs sind eindeutig, auch wenn mehrere Würfel dieselbe Farbe haben.

| Aufgabe | Fallname | Erfolgskriterium |
|---|---|---|
| Anheben und halten | `pick-up` | Ausreichende Höhe und anhaltender Kontakt an beiden Fingerflächen |
| Fallenlassen | `drop` | Freigabe aus der geforderten Höhe, danach stabil auf dem Tisch im Zielbereich |
| Absolut oder relativ ablegen | `place-absolute`, `place-relative` | Stabiler, freier Würfel an der Zielposition. Relative Ziele beziehen sich auf die gemessene Startlage der Episode. |
| Gelenkwinkel und Werkzeugpose | `move-joints`, `orient-top`, `orient-left`, `orient-right`, `orient-bottom` | Gemessene Gelenkwinkel bzw. Position und Ausrichtung des TCP |
| Würfel drehen | `rotate-cube` | Drehung um 45° um Welt-Z und stabile Ablage am Startplatz |
| Turm | `stack-ordered`, `stack-unordered` | Durchgehende Stützkontakte vom Tisch bis zur Spitze. Beim geordneten Fall zählt die Farbfolge von unten nach oben. |
| Formen | `shape-line`, `shape-l` | Jeder Zielplatz ist mit genau einem Würfel belegt. Die Farbfolge ist frei. |
| Pyramide | `pyramid` | Zwei Würfel tragen gemeinsam den mittigen oberen Würfel. |
| Sortieren | `sort-colour` | Eindeutig belegte Zielplätze, jeweils mit der geforderten Farbe |
| Hindernis | `move-around-obstacle` | Ablage am Ziel und höchstens 5 mm Bewegung des Hindernisses während der gesamten Physikaufzeichnung |
| Randfälle | `already-solved`, `missing-object`, `unrelated`, `ambiguous-colour` | Passender Antworttyp und unveränderter Zustand ohne Aktorbefehle |

## Ausführen

Verwende den Python-Interpreter der eingerichteten Projektumgebung.

```bash
python -m stacklab tasks list
python -m stacklab tasks show pyramid --seed 42
python -m stacklab tasks run pyramid --code examples/pyramid.py --gui
```

`tasks run` wertet ein eigenes Python-Programm oder eine JSON-Antwort aus. `--gui` zeigt die Ausführung im Viewer. `execution.json` enthält Aktionsprotokoll, Beobachtungen und Prüfergebnis. Die Dateien `case.json`, `scene.json` und `goal.json` halten die Versuchsbedingungen fest.

Dieselben Fälle funktionieren im Modelltest und im Experimentplan.

```bash
python -m stacklab benchmark --case pyramid --model qwen9b --feedback-rounds 4
python -m stacklab experiment plan --output runs/followup --models qwen4b qwen9b --cases pick-up pyramid sort-colour ambiguous-colour --blocks 4 --scene-seeds 42 43
python -m stacklab experiment run runs/followup
```

Für einen Lauf auf L4 oder A100 kannst du im allgemeinen Colab-Notebook `CASES = ["pick-up", "pyramid", "sort-colour", "ambiguous-colour"]` setzen. Mit `SHOW_VIDEO = False` startest du direkt mit den gewählten Aufgaben. [Allgemeines Colab-Notebook](https://colab.research.google.com/github/carlo2004/Simulation-Neura-LARA-5/blob/main/notebooks/colab_gpu.ipynb)

Die Ziele stammen aus dem Versuchsplan. Der erste Modellprompt enthält die Aufgabe und beobachtbare Szenendaten. `examples/pyramid.py` ist ein handgeschriebener Kontrolllauf. Physische Aufgaben müssen die Kriterien über 20 Stichproben in zwei Simulationssekunden erfüllen. Randfälle bewerten die erste Antwort und protokollieren den Antworttyp samt Text. Die bereits veröffentlichte Rot-auf-Blau-Studie lässt sich über ihr gepinntes Colab-Notebook fortsetzen.

## Programmierschnittstelle

| Aufruf im Modellprogramm | Einheiten und Verhalten |
|---|---|
| `robot.position("red")`, `robot.position("tcp")` | Objektmittelpunkt bzw. Werkzeugposition in Weltmetern |
| `robot.orientation("red")`, `robot.orientation("tcp")` | Gemessener Weltquaternion `[w,x,y,z]` |
| `robot.joints()`, `robot.move_joints(angles)` | Sechs Gelenkwinkel in Radiant. Die Grenzen stehen in `world_info.joint_limits_rad`. |
| `robot.move_to(xyz, orientation="top", yaw_deg=0)` | TCP-Pose. `top` zeigt nach −Z, `bottom` nach +Z, `left` nach +X und `right` nach −X. `yaw_deg` dreht den Rahmen um Welt-Z. |
| `robot.jog("x", distance, orientation="top", yaw_deg=0)` | Relative TCP-Bewegung. Die Orientierungsparameter sind optional. |
| `robot.gripper(True/False)`, `robot.step(seconds)` | Finger schließen/öffnen und Physik fortsetzen |

Die Bewegung verwendet die Aktuatoren und die vorhandene Kontaktphysik. Erreichbarkeit hängt von Position und Ausrichtung ab. Verwende erhöhte Zwischenpunkte für den Transport. Stapeln, Sortieren und Formaufgaben werden aus den einzelnen Roboteraktionen zusammengesetzt.

Die Terminalkonsole bietet zusätzlich `move X Y Z [ORIENTATION [YAW]]`, `quat NAME|tcp` und `move-joints J1 J2 J3 J4 J5 J6`. Die Konsole zeigt und erwartet Gelenkwinkel in Grad. Das Modellprogramm verwendet Radiant.

Für Rückfragen und begründete Ablehnungen liefert das Modell eine Antwort mit leerem Code.

```json
{"code":"","done":true,"intent":"clarify","message":"Meinst du red_a oder red_b?"}
```

`no_op` steht für ein bereits erfülltes Ziel, `cannot_execute` für einen unmöglichen oder sachfremden Auftrag. Geprüft werden der deklarierte Antworttyp, eine Erläuterung und der physische Zustand.
