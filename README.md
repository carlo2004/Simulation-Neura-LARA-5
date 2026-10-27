# Stack Lab — NEURA LARA 5, Version 2.4

Ein Python-Teststand für euer Praktikum: den LARA 5 sichtbar bewegen, benannte Objekte
platzieren und Würfel/Quader durch physisches Greifen aufeinander stapeln. Szene, Maße, Seed
und Geschwindigkeit lassen sich anpassen. Das Projekt läuft eigenständig mit
MuJoCo; für den Betrieb ist keine RoboDK-Installation nötig.

**Modellstatus:** Die Geometrie, Kinematiktabelle und Gelenkgrenzen stammen aus
dem öffentlich herunterladbaren RoboDK-Modell des LARA 5. Massenverteilung,
Trägheiten, Kollisionskörper, Regler und Parallelgreifer sind eigene
Simulationsannahmen. Die Konvertierung wurde gegen die extrahierte Kinematik
geprüft, nicht gegen einen echten NEURA-Controller oder Hersteller-URDF.
Das ist ein funktionsfähiger Referenz-Teststand, kein vom Hersteller validierter
dynamischer Zwilling des realen Roboters.

## 1. Voraussetzungen

- Empfohlen: Python 3.12. Das Projekt verwendet Python, MuJoCo, NumPy und SciPy;
  für den Mesh-Import zusätzlich trimesh. Alles wird über requirements.txt installiert.
- Windows, Linux oder macOS mit Desktop und OpenGL für das interaktive Fenster.
- Internet nur zur Installation der Python-Pakete. Modelldaten sind enthalten.
- Kein ROS, keine RoboDK-Lizenzdatei und kein LLM-API-Key für diese Simulation nötig.

Die mitgelieferte Ausführung wurde unter Linux/Python 3.12 geprüft, einschließlich
Kontaktphysik und EGL-Videoexport. Das native Desktopfenster konnte hier nicht
manuell bedient werden. Die Windows-/macOS-Befehle sind Startanleitungen;
es wurden hier keine Tests auf diesen Plattformen ausgeführt.

## 2. Schnellstart

ZIP entpacken. Im Ordner `lara5_lab` ein Terminal öffnen.

Windows, PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py --gui
```

Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py --gui
```

macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/mjpython run.py --gui
```

Der LARA startet oberhalb des Tisches, greift Rot und setzt Rot auf Blau.
Nach der Stabilitätsprüfung erscheint `SUCCESS: stable physical stack`.
Das Fenster bleibt geöffnet; mit der Maus Ansicht drehen und zoomen.
Fenster schließen beendet das Programm. Erneutes Starten setzt die Szene zurück.
Je nach Rechner kann die Ansicht langsamer als Echtzeit laufen.

In den folgenden Befehlen bedeutet `python` den Interpreter der eingerichteten
virtuellen Umgebung. Alternativ den vollständigen `.venv`-Pfad wie oben verwenden.

## Einstellungsleisten einklappen

Die MuJoCo-Seitenleisten starten ab Version 2.2.1 eingeklappt. Zum Umschalten
zuerst das **3D-Fenster anklicken**, dann:

- **Tab**: linke Einstellungsleiste ein-/ausblenden.
- **Umschalt+Tab**: rechte Einstellungsleiste ein-/ausblenden.

Im Terminal selbst haben diese Tasten eine andere Bedeutung. Die Funktion nutzt
die vorhandene MuJoCo-Bedienung; ein zusätzliches Einstellungsfenster ist nicht nötig.
Wenn du mit sichtbaren Einstellungen starten möchtest:

```bash
python console.py --show-settings
python run.py --gui --show-settings
```

Unter macOS entsprechend `mjpython console.py --show-settings` verwenden.
Die gewählte Startoption wird bei Szenenwechseln beibehalten. Ein Szenenneuaufbau
öffnet die Leisten wieder entsprechend dieser Startoption; der gerade per Taste
umgeschaltete Sichtbarkeitszustand wird dabei nicht separat gespeichert.

**Herkunft der Einstellungen:** Das Menü und seine Bedienelemente stammen aus
MuJoCo. Seine angezeigten Werte sind eine Mischung aus MuJoCo-Standardwerten,
importierten Modelldaten und eigenen Simulationsannahmen. Eine genaue Zuordnung
steht in [SETTINGS.md](SETTINGS.md). Die Annahmen sind keine offiziellen
NEURA-Dynamik- oder Reglerparameter.

## 2a. Den Roboter direkt über das Terminal steuern

Die neue Konsole öffnet die 3D-Ansicht und wartet auf deine Befehle:

```bash
python console.py
```

Unter macOS: `mjpython console.py`. Verwende auch hier den Interpreter der
virtuellen Umgebung. Im Terminal erscheint `lara>`. Die Physik läuft weiter,
während du tippst. Befehle werden nacheinander ausgeführt. Die Koordinaten
sind Weltkoordinaten in **Metern**; der Greifer zeigt bei `move` nach unten.

Zum Einstieg diese Befehle einzeln eingeben:

```text
help
status
move 0.4 -0.12 0.24
jog z 0.03
open
reset
stack red blue
check red blue
quit
```

`move` bewegt den Werkzeugmittelpunkt auf eine absolute Position, `jog` um einen
relativen Betrag. `open` und `close` betätigen den Greifer. `status` zeigt auch die
Würfelpositionen. `joints` zeigt die sechs Armwinkel in Grad. `reset` stellt den
Anfangszustand wieder her und hält das Fenster offen. Für einen neuen Stapelversuch
zuerst `reset` verwenden. `stack` nutzt die handgeschriebene Referenzstrategie;
es interpretiert keine freie Sprache und plant keine beliebigen Szenen.

Komplette Befehlsdateien lassen sich ebenfalls im Terminal ausführen:

```bash
python console.py --commands examples/manual_stack.txt
python console.py --commands examples/stack_reverse.txt
python console.py --headless --commands examples/manual_stack.txt
```

Die erste Datei stapelt mit einzelnen Bewegungs-/Greiferbefehlen. Sie enthält
fünf Sekunden Halten nach dem Anheben. Die zweite nutzt den fertigen Stapelbefehl
in umgekehrter Richtung. Die Zahlen der manuellen Datei sind für die unveränderte
40-mm-Standardszene gedacht. Im Dateimodus wird nach der letzten Zeile beendet;
ein Fehler stoppt die Datei mit Exitcode 1. In der interaktiven Konsole wird eine
Fehlermeldung ausgegeben, danach kannst du weiterarbeiten oder `reset` eingeben.

Weitere Befehle: `pos red`, `pos blue`, `pos tcp`, `wait 2`. `wait` akzeptiert
0 bis 60 Sekunden pro Befehl. `check red blue` misst zwei Sekunden lang, ob der
Stapel die Erfolgskriterien erfüllt. Kommentare beginnen mit `#`.
`--config meine_szene.json` wählt eine andere Anfangsszene.

Die Konsole akzeptiert nur diese bekannten Befehle. Sie ist keine Python-Shell.
Für Python-Code wie im methodischen Aufbau von Code as Policies ist weiterhin
`example_program.py` vorgesehen: Dort steht der Code in `program(robot)`, und
`python example_program.py` führt ihn aus. Beide Wege verwenden dieselbe
`Simulation`-Schnittstelle. Ein LLM ist dafür noch nicht erforderlich oder angebunden.

## 2b. Koordinatensystem und Stapelprüfung einblenden

Beide Hilfsanzeigen sind beim normalen Start **ausgeschaltet**. In der laufenden
Konsole kannst du sie einzeln ein- und ausblenden; die Physik läuft dabei unverändert:

```text
axes on
pos tcp
pos red
move 0.40 -0.12 0.24
jog z 0.03
stackviz red blue
stack red blue
check red blue
stackviz off
axes off
```

`axes on` zeigt farbige **Weltachsen** (X rot, Y grün, Z blau), ein 10-cm-Raster
auf dem Tisch und die aktuellen Koordinaten von Werkzeug und Objekten. Der Ursprung
liegt in der Mitte der Roboterbasis auf der Tischfläche; **z=0 ist die Tischhöhe**.
Die x/y-Rasterlinien werden nur zur sauberen Darstellung knapp über dem Tisch gezeichnet.
Positive Achsenrichtungen sind mit Pfeilen markiert. Alle Werte sind **Meter**.

- `pos red` gibt den **Mittelpunkt** des roten Objekts aus. Bei einem 4-cm-Würfel
  auf dem Tisch liegt dieser ungefähr auf z=0.020.
- `pos tcp` gibt den Werkzeugmittelpunkt zwischen den Greiferfingern aus.
- `move 0.40 -0.12 0.24` bewegt **den TCP** absolut auf x=40 cm, y=−12 cm,
  z=24 cm. In der Standardszene liegt das über Rot. Der Greifer bleibt nach unten gerichtet.
- `jog z 0.03` fährt vom aktuellen TCP aus 3 cm nach oben; auch x und y sind möglich.
- Der unterstützte TCP-Bereich bleibt x=0.20–0.60, y=−0.30–0.30, z=0.01–0.45 m.
  Die Visualisierung ergänzt keine Hindernisplanung. Für seitliche Fahrten zwischen
  den Standardwürfeln eignet sich zunächst z=0.24 m wie in der Referenzstrategie.

`stackviz red blue` umrahmt die gewählten Objekte und zeigt die **wirklichen
Prüfkriterien** mit ihren aktuellen Werten: horizontaler Mittelpunktversatz,
Höhenfehler, Kontakt, Ruhe und eine Unterstützungskette bis zum Tisch.
Die Rahmen folgen den tatsächlichen Objektpositionen und Orientierungen.

| Rahmenfarbe / Status | Bedeutung |
|---|---|
| Grau, NOT CHECKED | Für dieses Paar liegt noch keine Prüfung vor. Auch passende Koordinaten reichen allein nicht. |
| Gelb, CHECKING | Die Zwei-Sekunden-Prüfung läuft; der Zähler zeigt den Fortschritt. |
| Grün, PASS 20/20 | Alle 20 Zustandsproben im Abstand von 0.1 Simulationssekunden waren erfolgreich. |
| Rot, FAIL | Mindestens eine Probe hat die Kriterien nicht erfüllt. |
| Rot, CHANGED SINCE PASS | Der zuvor erfolgreiche Stapel wurde anschließend gestört; erneut prüfen. |

`check red blue` führt die Prüfung aus. Auch `stack red blue` enthält zum Schluss
diese Prüfung. `stackviz` selbst bewegt keine Objekte und führt noch keine
Zwei-Sekunden-Prüfung aus. Wenn die Anzeige eingeschaltet ist, richtet ein neuer
`check`/`stack`-Abschluss sie auf das gerade geprüfte Paar aus. Mit ausgeschalteter
Anzeige bleiben diese Befehle ohne sichtbare Hilfsrahmen.

Die angezeigten Kontakte/Positionen stammen direkt aus MuJoCo, nicht aus einer
Kameraerkennung. Die Toleranzen sind unsere offengelegte Versuchsdefinition,
keine NEURA-Vorgaben. `stack_diagnostics()` und `is_stacked()` verwenden dieselben
Kriterien; die Anzeige hat keine eigene, vereinfachte Erfolgserkennung.

Beim `reset` bleiben die gewählten Anzeigen sichtbar, das Prüfergebnis wird
gelöscht. Bei einem Szenenneuaufbau durch `add`/`place`/`load-scene` bleiben die
Anzeigeoptionen erhalten; fehlt ein ausgewähltes Objekt oder hat es keine passende
Form mehr, wird die Stapelanzeige abgeschaltet. Es wird kein früheres Prüfergebnis
auf eine neue Szene übertragen. `save-scene` speichert die Versuchskonfiguration,
keine Anzeigeoptionen.

Optional gleich mit Hilfsanzeigen starten:

```bash
python console.py --axes --stackviz red blue
python run.py --gui --axes --stackviz red blue
```

Unter macOS wie bisher `mjpython` verwenden. `run.py` führt die automatische Demo
aus; für das laufende Umschalten per Terminal `console.py` verwenden. Ohne die
Optionen bleiben die Hilfen aus. Auch Videoexporte können sie enthalten:

```bash
python run.py --video --axes --stackviz red blue --output output/annotated_demo
python console.py --commands examples/visual_checks.txt
```

Die Beispieldatei zeigt Bewegung, relativen Hub, Stapeln, Prüfung und Ausschalten.
Im Dateimodus endet die Simulation nach der letzten Zeile. Für eine frei steuerbare
Vorführung einfach `python console.py` starten und die Befehle einzeln eingeben.
Das enthaltene Referenzvideo aus Version 2.3 mit eingeblendeten Hilfen liegt unter
`output/annotated_demo/demo.mp4`, das Schlussbild daneben in `final.png`.

## 2c. Tastatursteuerung und Mausziele — optional

Die Tastatursteuerung ist beim normalen Start **aus**. Öffne die Konsole, gib
`manual on` ein und klicke dann in die **3D-Ansicht**, damit diese den Tastaturfokus
hat. Alternativ gleich so starten:

```bash
python console.py --manual --axes
python console.py --config scenes/duck.json --manual --axes
```

Unter macOS `mjpython` verwenden. Im Terminal selbst bleiben die Tasten normale
Eingabetasten. Für das Eingeben von Befehlen zurück ins Terminal klicken.

| Taste im 3D-Fenster | Funktion |
|---|---|
| Pfeil hoch / runter | TCP um +X / −X bewegen |
| Pfeil links / rechts | TCP um +Y / −Y bewegen |
| Home / End (Pos1 / Ende) | TCP um +Z / −Z bewegen |
| Insert / Delete (Einfg / Entf) | Greifer öffnen / schließen |
| Leertaste | Bewegungsziel stoppen, Handmodus bleibt an |
| Esc | Stoppen und Handmodus ausschalten |

Die Richtungen beziehen sich auf die **Weltachsen**, auch wenn die Kamera gedreht
wird. Ein Tastendruck ändert das Ziel standardmäßig um 5 mm; die Wiederholung
beim Halten folgt der Tastaturwiederholung des Betriebssystems. Das Ziel wird
mit höchstens 4 cm/s angefahren. Es wird nur ein ausstehendes Tastenereignis
gepuffert, und der Zielvorlauf ist auf 2.5 cm begrenzt. Es gibt keine lange
Bewegungsschlange nach dem Loslassen. Leertaste leert die Eingaben und hält die
aktuelle Gelenkstellung mit der vorhandenen Regelung.

Die Schrittweite lässt sich ändern: `manual on 0.002` verwendet 2 mm.
Zulässig sind 1–20 mm. `manual off` schaltet den Modus im Terminal aus. Die
Terminalbefehle `open` und `close` bleiben verfügbar, wenn die Tastatur keine
Insert-/Delete-Tasten hat. Arbeitsraum und feste Greiferorientierung bleiben
wie bei `move`. Eine Kollisionserkennung als Bewegungsplaner gibt es nicht:
Du kannst mit dem Greifer absichtlich gegen Objekte fahren und sie verschieben.

Terminalbefehle haben Vorrang vor Tastatureingaben. Während `stack`, `push` oder
eines anderen Terminalbefehls eingegebene Bewegungstasten werden verworfen.
`reset` und Szenenneuaufbau (`add`, `place`, `load-scene` usw.) schalten den
Handmodus aus. Anschließend bei Bedarf wieder `manual on` eingeben.

**Mausziel auswählen:** Mit der linken Maustaste einen Punkt auf Tisch oder
Objekt **doppelt anklicken**, dann im Terminal:

```text
goto-selected
```

Der Arm fährt zunächst hoch, dann über den gewählten x/y-Punkt. Der TCP bleibt
standardmäßig mindestens auf Transporthöhe beziehungsweise 6 cm über dem
angeklickten Oberflächenpunkt. `goto-selected 0.30` setzt die Zielhöhe auf
30 cm über dem Tisch; sie muss mindestens 4 cm über dem gewählten Punkt liegen.
Die Vorauswahl wird bei aktivem Handmodus als gelber Punkt dargestellt. Klicks
auf den Roboter und Punkte außerhalb des Arbeitsbereichs werden abgelehnt.
Ein Doppelklick allein löst **keine Armbewegung** aus. Es wird die vorhandene
MuJoCo-Auswahl benutzt; eine eigene Shift-Klick-Belegung ist nicht erforderlich.
Es gibt keine allgemeine Hindernisplanung bei der Fahrt zum Mausziel.

**Objekte direkt mit der Maus anstoßen:** Links doppelt auf ein Objekt klicken,
dann **Strg + rechte Maustaste ziehen**. Mit zusätzlicher **Umschalt-Taste**
erfolgt die Verschiebung in der horizontalen Ebene. MuJoCo setzt dabei Kräfte
am ausgewählten Körper an; ohne Strg bewegt Ziehen weiterhin die Kamera.
Das ist eine Physikstörung von außen, keine Bewegung des Greifers. Damit lässt
sich etwa ein zuvor erfolgreicher Stapel gezielt stören. Diese MuJoCo-Funktion
ist auch ohne unseren Tastaturmodus verfügbar.

Die Steuerlogik wurde mit eingespeisten Tasten/ausgewählten Punkten und echter
Physik geprüft. Eine manuelle Desktopbedienung auf Windows/macOS wurde hier
nicht durchgeführt; entsprechende Grenzen stehen im TEST_REPORT.md.

## 3. Startpositionen, grüner Würfel und andere Objekte

Ab Version 2.2 lassen sich diese Änderungen direkt in der Konsole durchführen:

```text
place red 0.38 -0.14
add green cube 0.50 0.00 0.04
objects
stack green blue
check green blue
```

`place` legt eine **Startposition** in Metern fest. `add` fügt ein neues Objekt
zur Startszene hinzu. Beide Befehle bauen die Szene neu auf und setzen den Arm,
den Greifer und **alle** Objekte zurück. Bei sichtbarer Simulation wird das
3D-Fenster dafür neu geöffnet. Das ist Szeneneinrichtung; im eigentlichen
Greif-/Stapelablauf bleiben die Körper frei und werden durch Fingerkontakt bewegt.
`place` schaltet zufällige Verschiebungen ab, damit die angegebene Position gilt.

Zufällige Anfangspositionen und wiederverwendbare Konfigurationen:

```text
randomize 123 0.01
save-scene meine_szene.json
load-scene meine_szene.json
remove green
```

`randomize 123 0.01` verschiebt jedes Objekt reproduzierbar um bis zu ±1 cm je
x/y-Achse um seine konfigurierten Ausgangskoordinaten. Ohne zweiten Wert wird
vorhandener Jitter oder sonst ±2 cm verwendet. Gleicher Seed und gleiche
Konfiguration ergeben dieselben Starts. Überlappende oder zu eng stehende
Objekte werden vor dem Szenenwechsel abgelehnt; die bisherige Szene bleibt erhalten.

Weitere Grundformen kannst du so hinzufügen:

```text
add yellow box 0.52 -0.20 0.06 0.045 0.05
add ball sphere 0.52 0.20 0.045
```

Ein Zylinder ist beispielsweise `add can cylinder 0.28 0.00 0.04 0.06`.
Die Beispiele setzen genügend freien Platz voraus. Formen und Maße:

| Form | Bedeutung der Größenwerte | Automatisches Stapeln |
|---|---|---|
| `cube` | Kantenlänge | Geprüft für passende Größen |
| `box` | Volle Seitenlängen x, y, z | Geprüft für passende Größen |
| `sphere` | Durchmesser | Als frei bewegliches Szenenobjekt unterstützt |
| `cylinder` | Durchmesser, Höhe | Als frei bewegliches Szenenobjekt unterstützt |

Alle Maße sind Meter. Es gibt bis zu zwölf eindeutig benannte Objekte.
Grundformen dürfen Außenmaße von 0.02 bis 0.12 m haben. Der automatische Griff
ist enger begrenzt: Quellobjekte müssen Würfel/Quader mit x=0.03–0.10,
y=0.035–0.05 und z=0.035–0.06 m sein. Zielobjekte müssen ebenfalls Würfel/Quader
sein. Das ist keine allgemeine Greifstrategie für beliebige Formen. Für starre
Mesh-Objekte gibt es ab Version 2.4 den begrenzten Import unter Abschnitt 3b;
automatisches Stapeln importierter Formen ist nicht enthalten.

Zum direkten Öffnen der enthaltenen Beispielszenen:

```bash
python console.py --config scenes/three_cubes.json
python console.py --config scenes/mixed_objects.json
python run.py --config scenes/three_cubes.json --source green --target blue --gui
```

In der Drei-Würfel-Szene kannst du auch einen Turm bauen:

```text
stack red blue
stack green red
check green red
check red blue
```

Die Erfolgskontrolle verlangt Kontakt und eine ruhende Unterstützungskette bis
zum Tisch; ein schwebendes Zielobjekt zählt nicht. Die fertige Befehlsfolge liegt
unter `examples/three_cube_tower.txt`. Ausführung ohne Fenster:

```bash
python console.py --headless --config scenes/three_cubes.json --commands examples/three_cube_tower.txt
python console.py --headless --commands examples/edit_scene.txt
```

Für JSON-Szenen beschreibt `objects` die benannten Körper. Beispiel:

```json
{
  "seed": 42,
  "random_jitter_m": 0.01,
  "objects": [
    {"name": "red", "shape": "cube", "xy_m": [0.40, -0.12], "size_m": 0.04},
    {"name": "blue", "shape": "cube", "xy_m": [0.40, 0.12], "size_m": 0.04},
    {"name": "green", "shape": "cube", "xy_m": [0.50, 0.00], "size_m": 0.04}
  ]
}
```

`mass_kg` (0.005–0.5 kg, Standard 0.06 kg) und `color` als RGBA-Liste können
optional je Objekt angegeben werden. Die Namen red/blue/green/yellow erhalten
passende Farben; andere Namen standardmäßig Grau. Ausgangsorientierungen sind
achsparallel. Ist `objects` vorhanden, haben diese Beschreibungen Vorrang vor
den alten Feldern `red_xy_m`, `blue_xy_m` und `cube_size_m`.

Die bisherige Zwei-Würfel-Konfiguration bleibt verwendbar:


```bash
python run.py                         # Simulation ohne Fenster
python run.py --gui --reverse         # Blau auf Rot, mit 3D-Fenster
python run.py --video                 # MP4 und Schlussbild
python run.py --config meine_szene.json --output mein_ergebnis
```

`scenario.json` bearbeiten und neu starten. Die Objekte sind frei bewegliche
Körper, deren Anfangspositionen über diese Datei gesetzt werden.

| Feld | Bedeutung | Zugelassener Bereich |
|---|---|---|
| `red_xy_m`, `blue_xy_m` | Würfelzentren auf dem Tisch, Weltkoordinaten | x: 0.25–0.55 m; y: −0.25–0.25 m |
| `cube_size_m` | Gemeinsame Kantenlänge | 0.035–0.05 m |
| `hover_z_m` | Anfahr- und Transporthöhe | größer als 3 × Kantenlänge, höchstens 0.4 m |
| `speed_mm_s` | Referenzgeschwindigkeit für die Bewegungsdauer | 10–120 mm/s |
| `random_jitter_m` | Zufällige Verschiebung je x/y-Achse | 0–0.03 m |
| `seed` | Reproduzierbare Zufallsfolge | Ganzzahl |
| `fps` | Viewer- und Video-Bildrate | 10–60 |

Die Bereiche begrenzen Eingaben; sie garantieren keinen Erfolg für jede mögliche
Kombination. Die Referenzstrategie setzt eine freie Transportbahn voraus und hat
keine allgemeine Hindernisplanung. Neue Szenen deshalb separat ausführen und prüfen.

`output/result.json` enthält Erfolg, Objektpositionen beim Greifen/Anheben/Ablegen,
Stabilitätsprüfungen, Simulationszeit und den Modellstatus. Fehlschläge liefern
Exitcode 1, manuelle Unterbrechung 130. `--video` erzeugt außerdem `demo.mp4` und
`final.png`. Ein neuer Lauf im selben Ausgabeordner überschreibt die Ergebnisse.

## 3b. Objekte schieben und Modelle aus dem Internet importieren

Zum schnellen Physiktest in der Konsole:

```text
add ball sphere 0.50 0.00 0.04
push ball 0.05 0.00
```

Die Kugel ist 4 cm groß; der Greifer schiebt sie in +X-Richtung. `push NAME DX DY`
verwendet Meter und unterstützt Verschiebungswünsche mit 1–12 cm Länge. Er fährt
mit geschlossenen Fingern hinter das Objekt, senkt ab, schiebt und zieht sich
nach oben zurück. Der tatsächliche Weg kann je nach Form, Reibung, Masse und
Kontakten abweichen. Die Konsole meldet den gemessenen Objektweg und ob
Fingerkontakt erkannt wurde. Es werden keine Objektpositionen gesetzt und keine
Hilfskräfte an Objekte angelegt. Das ist eine einfache Tischstrategie, kein
allgemeiner Schiebeplaner; hohe Turmebenen werden nicht automatisch geschoben.
Zum freien Experimentieren den Tastaturmodus oder die MuJoCo-Mauskräfte nutzen.

Die **Gummiente** ist bereits samt Quelldatei und Lizenz enthalten:

```bash
python console.py --config scenes/duck.json --axes
```

In dieser Szene: `push duck 0.05 0.00`. In einer normalen Konsole kannst du sie
alternativ selbst importieren:

```text
add-mesh duck source/duck/Duck.glb 0.50 0.00 0.08
```

Die letzte Zahl ist die **längste Außenabmessung** in Metern: hier 8 cm. Der
Import zentriert das Modell und skaliert es unter Erhaltung seiner Proportionen.
Bei GLB wird die standardmäßige Y-Hochachse nach Z-oben umgerechnet. OBJ/STL/PLY
werden als bereits Z-oben interpretiert. Gedrehte Modelle vorher etwa in Blender
ausrichten und die Transformation anwenden.

Eigene Downloads funktionieren mit demselben Befehl:

```text
add-mesh toy "C:/Downloads/mein_objekt.obj" 0.50 0.00 0.08
add-mesh toy "/Users/ich/Downloads/mein_objekt.glb" 0.50 0.00 0.08 0.10
```

Dies sind alternative Beispiele, nicht nacheinander mit demselben Namen
auszuführen. Das optionale letzte Argument ist die Masse in kg, hier 0.10 kg.
Ohne Angabe gelten 0.06 kg. Namen müssen wie bei `add` eindeutig sein. Auch
`add-mesh` baut die komplette Anfangsszene neu auf und schaltet den Handmodus aus.
Bei Validierungsfehlern bleibt die vorherige Szene aktiv.

**Unterstützt:** lokale OBJ-, STL-, PLY- und GLB-Dateien mit starrer, nicht
komprimierter Dreiecksgeometrie, maximal 25 MiB, 100000 Vertices und 200000
Dreiecken. Längste Seite 2–12 cm; nach Skalierung jede Seite mindestens 5 mm.
Keine CAD-Baugruppen, Animationen, verformbaren Körper oder direkte URL-Downloads
im Befehl. Materialien/Texturen werden bewusst weggelassen; die Geometrie wird
einfarbig dargestellt. Farben lassen sich wie bei anderen Objekten im JSON
über `color` setzen; `duck` erhält standardmäßig Gelb.

**Kollisionen:** Der sichtbare Umriss stammt aus dem importierten Modell.
Für die Physik wird eine separate **konvexe Hülle** verwendet. Vertiefungen und
Löcher werden dabei gefüllt. Beispielsweise lässt sich in eine hohle Tasse
damit nichts hineinlegen. Für einfache Schiebeversuche mit geschlossenen Formen
ist dies eine überschaubare Näherung. Ein hübsches Modell ist kein kalibriertes
Physikmodell: Masse und Reibung bleiben ausdrücklich angesetzte Werte.

Aufbereitete Geometrie, Hülle und Herkunftsmetadaten liegen unter `models/objects`.
Szenen speichern relative Pfade darauf; der ursprüngliche Download wird nach
dem Import nicht mehr zum Ausführen benötigt. Beim Weitergeben einer eigenen
Szene auch diese Dateien und die jeweilige Lizenz/Attribution mitnehmen.
`save-scene` allein ist eine JSON-Datei, kein vollständiges Asset-Paket.

Passende Quellen für weitere Modelle:

- **Google Scanned Objects:** echte Haushaltsgegenstände als 3D-Scans;
  Forschungsbeschreibung und Zugang: https://research.google/blog/scanned-objects-by-google-research-a-dataset-of-3d-scanned-common-household-items/
  Die veröffentlichte Sammlung umfasst unter anderem OBJ-Geometrie. Lizenz CC BY 4.0,
  Attribution bei eigenen Downloads übernehmen.
- **Khronos glTF Sample Assets:** kleine Beispielmodelle mit GLB-Downloads,
  Vorschauen und Lizenzangaben pro Modell: https://github.khronos.org/glTF-Assets/
  Für diesen Import einfache statische Modelle ohne Draco-/Meshopt-Kompression wählen.
- **YCB:** wissenschaftlicher Objekt-/Benchmarkdatensatz für Manipulation:
  https://arxiv.org/abs/1502.03143 . Die Projekt-Downloadseite war bei der Recherche
  nicht zuverlässig erreichbar; deshalb ist die enthaltene Ente der direkte Einstieg.

Die Ente stammt aus Khronos' Sony-Duck-Modell (© 2006 Sony, SCEA Shared Source
License 1.0). Quelle, unveränderte GLB-Datei, Lizenz, Originalbeschreibung und
unsere Bearbeitung sind in `source/duck` dokumentiert. Das Modell stellt kein
gemessenes reales Gummiverhalten dar; hier ist es ein starrer Körper.

Fertige Konsolenabläufe: `examples/push_playground.txt` und
`examples/import_duck.txt`. Im Projektordner etwa:

```bash
python console.py --commands examples/import_duck.txt
```

## 4. Eigener Python-Code und späterer LLM-Anschluss

`example_program.py` zeigt ein vollständiges Stapelprogramm mit wenigen Funktionen:

```python
robot.position('green')               # Für jedes in der Szene vorhandene Objekt
robot.move_to([0.4, -0.12, 0.24])      # TCP bewegen; Orientierung nach unten
robot.gripper(closed=True)            # Finger schließen
robot.gripper(closed=False)           # Finger öffnen
robot.step(1.0)                       # Eine Sekunde Physik weiterschalten
robot.is_stacked('green', 'blue')      # Unabhängige Zustandsprüfung
```

`python example_program.py` führt das Beispiel ohne Fenster aus. In der Funktion
`program(robot)` könnt ihr später erzeugten Code einsetzen. `robot.stack()` ist
die fertige Referenzstrategie. Für Codegenerierungsversuche sollte das Modell
nur die niedrigeren Bewegungs-/Greiferfunktionen erhalten, damit es das Programm
selbst zusammensetzen muss.

Die ausgelieferte Strategie ist handgeschrieben. Finetuning, Sprachverständnis
und automatische Ausführung unkontrollierten generierten Codes sind nicht enthalten.
Für eine spätere LLM-Evaluation generierten Code in einem separaten Prozess/Container
mit Laufzeit- und Ressourcenlimits ausführen. Das ist ein eigener nächster Schritt.

## 5. Reproduzierbare Prüfung

Im Projektordner:

```bash
python -m unittest discover -s tests -v
python validate.py
python validate_objects.py
python validate_controls.py            # Schieben, eingespeiste Tasten, Mausziel-Logik
MUJOCO_GL=egl python validate_controls.py --images  # Linux: zusätzliche Vorschaubilder
MUJOCO_GL=egl python validate_overlays.py  # Linux: Bilder und Anzeige-/Bewegungsprüfung
python example_program.py
```

Die bisherige Integrationssuite umfasst 14 Szenen: Standardszene, zehn Seeds mit bis zu
±25 mm Verschiebung je Achse und wechselnder Stapelrichtung sowie Würfel mit
35, 45 und 50 mm Kantenlänge. Der Bericht liegt in `output/validation.json`.
`validate_objects.py` prüft acht weitere Fälle mit Grün, verschobenen Starts,
Quadern, gemischten Grundformen und einem Drei-Würfel-Turm. Der Bericht liegt in
`output/objects_validation.json`. Mit `MUJOCO_GL=egl python validate_objects.py --images`
lassen sich auf einem passenden Linux-System Bilder dieser Szenen erzeugen.
`TEST_REPORT.md` beschreibt den tatsächlich ausgelieferten Teststand.
Die zusätzlichen Tests prüfen unter anderem die Vorwärtskinematik über
100 Gelenkstellungen, Gelenkgrenzen, freie Würfelkörper, Konfiguration und einen
negativen Fall mit 1 mm Luftspalt zwischen passend positionierten Würfeln.

Als Erfolg zählt: Nach Loslassen und Rückzug des Greifers sind über 20 Messungen
im Abstand von 0.1 s alle Bedingungen erfüllt: horizontaler Mittelpunktversatz
unter 4 mm, Höhenabstand der Mittelpunkte gleich der Summe beider halben
Objekthöhen (±3 mm), kaum Bewegung und von MuJoCo bestätigter Kontakt. Das Ziel
muss auf dem Tisch (±3 mm) oder auf einer ebenfalls ruhenden, durch Kontakt
bestätigten Kette aus Würfeln/Quadern stehen. Die Geschwindigkeitsprüfung verwendet den
Betrag des sechsachsigen Geschwindigkeitsvektors unter 0.02, dessen Translation
in m/s und Rotation in rad/s vorliegt. Die genaue Metrik steht in `stack_diagnostics()`
(von `is_stacked()` verwendet)
und sollte für ein Paper vor der eigentlichen Evaluation festgelegt werden.

## 6. Was am LARA-Modell übernommen wurde

| Bestandteil | Herkunft / Status |
|---|---|
| Sieben sichtbare Körper | Aus dem RoboDK-LARA-5-Modell; Maße von mm nach m konvertiert |
| Sechs Gelenke | Aus der dort gespeicherten modifizierten DH-Tabelle aufgebaut |
| Gelenkgrenzen | Aus derselben Modelldatei |
| Visuelle Dreiecksflächen | Quellgeometrie, mit korrigierter Flächenorientierung für MuJoCo |
| Kollisionskörper | Vereinfachte Kapseln/Kugeln aus den Geometriegrenzen |
| Massenverteilung | Angenommene Werte: 3.5, 4, 6, 3.5, 3, 2, 1 kg |
| Trägheiten / Schwerpunkte | Näherungen aus den jeweiligen Begrenzungsquadern |
| Regelung | Positionsregelung mit idealer Modellkompensation von Schwerkraft/Coriolis |
| Greifer | Eigener generischer Parallelgreifer |

Alle Werte stehen in `models/lara5/parameters.json` und `lara5.xml`.
Die angenommenen 23 kg Gesamtmasse sind keine aktuelle Hersteller-Spezifikation.
Die Bibliotheksversion darf nicht ohne Prüfung mit einer bestimmten realen
LARA-Hardwaregeneration gleichgesetzt werden. Daten wie echte Trägheiten,
Antriebskennlinien, Gelenknachgiebigkeit und Herstellerregelung fehlen.

Der Kontaktablauf nutzt MuJoCo-Schwerkraft und Reibung. Die Würfel sind frei;
im Demoablauf werden sie weder teleportiert noch durch Welds/Attach-Constraints
am Greifer gehalten. Ihre Positionen stammen direkt aus dem Simulator.
Es gibt keine Kameraerkennung und keine Behauptung einer vollständigen
Reproduktion von Code as Policies.

## 7. Konvertierung und Nachvollziehbarkeit

Die Quelldatei unter `source/Neura-LARA-5.robot` wurde über den öffentlichen
Download der RoboDK-Bibliothek bezogen. URL und SHA-256 stehen in `parameters.json`.
Die Binärstruktur wurde für genau diese Version interpretiert; der Konverter
verweigert andere Prüfsummen. Es wurde kein Hersteller-URDF vorausgesetzt.

```bash
python convert_model.py
```

Dieser Befehl erzeugt MJCF, OBJ-Dateien und Parameterdatei reproduzierbar neu.
Er benötigt nur NumPy/SciPy; keine RoboDK-Anwendung und kein Internet.
Der Kinematiktest kontrolliert die Übereinstimmung der MuJoCo-Kette mit einem
separaten analytischen Produkt der extrahierten DH-Matrizen. Er belegt die
Konsistenz der Konvertierung, nicht die Genauigkeit am realen Roboter.

## 8. Bedeutung für die wissenschaftliche Arbeit

Die Umgebung eignet sich als abgegrenzter Teststand für Python-Codegenerierung.
Handmodus und Mauskräfte sind Werkzeuge zum Vorführen und Debuggen. Für
automatische Modellvergleiche ohne GUI/Handeingriffe ausführen und dieselben
Szenen, Objektmodelle und Parameter verwenden. Bei importierten Formen gehört
die konvexe Kollisionsnäherung ausdrücklich zur Beschreibung des Versuchsaufbaus.
Trainings- und zurückgehaltene Testszenen trennen, Baseline und finetunetes Modell
mit denselben Szenen bewerten und Syntax-/API-Fehler, fehlgeschlagene Griffe sowie
instabile Stapel getrennt erfassen. Die mitgelieferten Testszenen sind bereits
Entwicklungstests und kein unabhängiges Testset für Modellvergleiche. Szenen-
Einrichtungsfunktionen wie place, add und reset gehören nicht in die erlaubte
Bewegungsschnittstelle eines zu evaluierenden LLM; die Testszene wird vorher festgelegt.

Die erfolgreichen Läufe gelten für diesen Simulator und diese Modellannahmen.
Sie belegen keine Übertragbarkeit auf echte Hardware. Für die spätere reale
LARA-Anbindung wären Herstellerdaten und ein kontrollierter Abgleich von
Koordinaten, Grenzwerten, Greifer und Regelung erforderlich.

## 9. Fehlerbehebung

- `ModuleNotFoundError`: Installation und Start müssen denselben Python-Interpreter
  verwenden. Die vollständigen `.venv`-Pfade aus dem Schnellstart verhindern Verwechslungen.
- Kein Fenster / GLFW-Fehler: lokal auf einem Desktop starten. Ohne Display zuerst
  `python run.py` ohne `--gui` ausführen; dieser Physiktest benötigt keinen Renderer.
- macOS fordert `mjpython`: `.venv/bin/mjpython run.py --gui` verwenden.
- EGL-/OpenGL-Fehler beim Video: passenden EGL-/Mesa-/GPU-Treiber verwenden. Unter
  einem Linux-Desktop kann `MUJOCO_GL=glfw python run.py --video` funktionieren.
- Eigene Szene scheitert: unveränderte Standardszene prüfen, Positionen näher an
  die Vorgaben setzen und langsamer bewegen. Fehlertext in `output/result.json` lesen.

## Quellen und Lizenzhinweise

- LARA-5-Modell: https://robodk.com/robot/Neura/LARA-5
- Direkte Quelle: https://cdn.robodk.com/downloads-library/library-robots/Neura-LARA-5.robot
- Hersteller: https://neura-robotics.com/products/lara/
- MuJoCo: https://mujoco.org/
- Modifizierte DH-Konvention: https://robodk.com/doc/en/Robots-Universal-Robots-Update-Robot-Kinematics.html
- Methodischer Bezug: https://code-as-policies.github.io/

Die MIT-Lizenz in `LICENSE` gilt für den eigenen Anwendungscode. Für die
übernommenen Robotermodell-Daten wird keine zusätzliche Lizenz eingeräumt;
Herkunft und Abgrenzung stehen in `source/NOTICE.md`.
