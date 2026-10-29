# Woher kommen die Einstellungen?

## Oberfläche und Ein-/Ausklappen

Das sichtbare Einstellungsmenü gehört zum standardmäßigen MuJoCo-Viewer
(`mujoco.viewer.launch_passive`), nicht zu einer selbst entworfenen Oberfläche.
Die Einträge für Physik, Darstellung, Gelenke und Steuerung werden vom Viewer
bereitgestellt. Auch das Ein-/Ausblenden mit Tab und Umschalt+Tab ist eine
bestehende MuJoCo-Funktion.

In diesem Projekt wurde lediglich die Startansicht angepasst: Beide Leisten sind
zunächst ausgeblendet; mit `--show-settings` werden sie sichtbar gestartet.
Technisch werden die öffentlichen Argumente `show_left_ui` und `show_right_ui`
verwendet. Die Tastaturumschaltung bleibt jederzeit verfügbar, wenn das
3D-Fenster den Fokus hat.

Offizielle Dokumentation der verwendeten Version:
https://mujoco.readthedocs.io/en/3.3.7/python.html#passive-viewer

## Performance und empfohlener Start

Ab Version 3.4.1 verwenden die normalen Startbeispiele keine zusätzlichen Overlays.
Achsen/Grid, Koordinaten, Objektlabels und Stapelrahmen sind weiterhin optional.
Die MuJoCo-Einstellungsleisten starten ebenfalls ausgeblendet; `--show-settings`
blendet sie beim Start ein. Das ist unabhängig von den eigenen Overlays.

| Einstellung | Standard / Verhalten |
|---|---|
| Physikzeitschritt | 0.002 s, unverändert |
| `fps` in der Szenen-JSON | 30; steuert Videoframes nach Simulationszeit und begrenzt Viewer-Synchronisation nach Echtzeit |
| Eigene GUI-Overlays | Aus; einschaltbar über `--axes`, `--stackviz` oder Chatbefehle |
| Overlay-Neuaufbau in der GUI | Höchstens 10 Hz bei regelmäßigen Updates; Ein-/Ausblenden und abgeschlossene Prüfungen werden sofort übernommen |
| MuJoCo-Einstellungsleisten | Ausgeblendet; `--show-settings` oder Tab / Umschalt+Tab |
| Tokenanzeige | Weiterhin aktiv; fehlende Zeitwerte führen nicht mehr zu `KeyError: 'total_seconds'` |

Die Begrenzung nach Echtzeit gilt auch während der Inferenz bei pausierter Physik.
Zwischen Overlay-Updates werden Geometrien und Texte wiederverwendet. Die Physik
behält ihre Schritte; Videoframes folgen weiterhin der Simulationszeit und werden
nicht durch die GUI-Drosselung ausgelassen. FPS sind eine Obergrenze für die
Synchronisation, keine garantierte Bildrate oder garantierte Echtzeitphysik.

Nach `git pull --ff-only` im Projektordner unter Windows zunächst lokal starten:

```powershell
.\.venv\Scripts\python.exe -m stacklab chat --model qwen4b --threads 2 --stream
```

`--threads 2` ist hier ein Startwert für CPU-Inferenz auf dem lokalen Rechner,
keine allgemeine optimale Einstellung. Quantisierung und Modellgeschwindigkeit
werden durch die GUI-Optimierung nicht verändert. Das Modell muss eingerichtet sein.

Bei bereits laufendem Colab-Modellserver und SSH-Tunnel:

```powershell
.\.venv\Scripts\python.exe -m stacklab chat --server-url http://127.0.0.1:8765 --stream
```

Im Remote-Modus werden Modell und Threads am Server gewählt; die lokale Simulation
braucht keine eigenen Modellgewichte. [Vollständige Einrichtung](remote-live.md).

Optionale Anzeigen lassen sich im Chat gezielt ein- und wieder ausschalten:

```text
/axes on
/stackviz red blue
/axes off
/stackviz off
```

Ohne Overlay erfolgt dieselbe unabhängige Physikprüfung, zum Beispiel mit
`/check red blue`. Die geringere Zeichenlast garantiert noch keine flüssige
Darstellung auf jeder Hardware; bei weiteren Verzögerungen müssen Viewer und
Overlay-Berechnung getrennt gemessen werden.

## Werte im Menü

Die optionalen Koordinaten- und Stapelanzeigen ab Version 2.3 sind eigener
Anwendungscode in `stacklab/sim/overlays.py`, dargestellt mit MuJoCos Visualisierungsfunktionen.
Sie sind kein offizielles NEURA-Bedienelement. `axes on/off` und
`stackviz SOURCE TARGET` beziehungsweise `stackviz off` steuern ihre Sichtbarkeit;
beim normalen Start sind beide aus. Die Stapelanzeige verwendet dieselben
Prüfkriterien wie die Ergebnisbewertung. Grün erscheint erst nach der erfolgreichen
Prüfung über zwei Simulationssekunden, nicht allein aufgrund einer Rahmenüberlappung.


Dass MuJoCo ein Feld anbietet, bedeutet nicht, dass dessen Zahl vom
Roboterhersteller stammt. Im geladenen Modell sind folgende Quellen enthalten:

| Bereich | Herkunft | Einordnung |
|---|---|---|
| Menü, Felder, Anzeigeoptionen | MuJoCo-Viewer | Vorgegebene Softwareoberfläche |
| Nicht im Modell überschriebenes Verhalten | MuJoCo-Standardwerte | Standardeinstellungen des Simulators |
| Sichtbare LARA-Geometrie, Kinematiktabelle, Gelenkgrenzen | Öffentliches RoboDK-LARA-5-Modell | Konvertiert; nicht gegen echte NEURA-Hardware oder Hersteller-URDF validiert |
| Robotermassen, Schwerpunkte und Trägheiten | Eigene Näherungen | Keine gemessenen Herstellerdaten |
| Kollisionskapseln/-kugeln | Aus den Geometriegrenzen angenähert | Keine CAD-genaue Kollisionsdarstellung |
| Parallelgreifer | Eigene einfache Geometrie und Regelung | Kein kalibriertes Modell eines bestimmten Kaufgreifers |
| Objektgrößen, Farben, Massen, Startpositionen | Projektkonfiguration | Frei gewählte Versuchsszene |
| Reibung, Kontaktparameter, Reglerverstärkungen | Eigene Simulationsannahmen | Für die Demo verwendet und funktional erprobt; nicht am realen Roboter identifiziert |
| Erfolgskriterien wie Toleranzen und Prüfdauer | Eigene Versuchsdefinition | Müssen für eine wissenschaftliche Evaluation offengelegt und vorher festgelegt werden |

Konkrete Beispiele der eigenen Annahmen:

- Vorgabe der Robotermassen pro Körper: 3.5, 4, 6, 3.5, 3, 2 und 1 kg.
  Die Verteilung ist angesetzt; die 23 kg Summe belegt keine aktuelle reale LARA-Generation.
- Standardmasse eines Szenenobjekts: 0.06 kg; Standardwürfel: 0.04 m Kantenlänge.
- Reibungskoeffizient der Objekte: 1; der Finger: 2 (jeweils erster MuJoCo-Reibungswert).
- Simulationszeitschritt: 0.002 s; integrator: implicitfast; Solver-Iterationen: 80.
- Positionsregelung der Armachsen: kp 2000/500 und kv 180/50 je nach Achse;
  dazu ideale modellbasierte Schwerkraft-/Corioliskompensation.
- Erfolg: horizontale Zentren weniger als 4 mm versetzt und 20 bestandene
  Kontakt-/Stabilitätsprüfungen im Abstand von 0.1 s, neben weiteren Höhen-/Geschwindigkeitsbedingungen.

Schwerkraft von 9.81 m/s² ist eine übliche Näherung für Erdschwerkraft, keine
spezifische Roboteridentifikation. Die Wahl des Zeitschritts und der übrigen
Simulationsparameter ist ebenfalls keine Übernahme aus einem NEURA-Datensatz
oder eine vollständige Reproduktion des Code-as-Policies-Experiments.

## Nachvollziehbarkeit

Ab Version 2.4 sind Tastatursteuerung, `goto-selected`, die einfache Schiebestrategie
und die Mesh-Aufbereitung ebenfalls eigener Anwendungscode. Die Doppelklick-Auswahl
und das Anwenden von Mauskräften gehören zu MuJoCo. Die enthaltene Entengeometrie
stammt dagegen von Sony über Khronos; Attribution/Lizenz stehen in `assets/sources/duck`.
Konvexe Kollisionshülle, Masse und Reibung des importierten Beispiels sind keine
gemessenen Eigenschaften einer realen Gummiente.
Eigene Bedienvorgaben: 5 mm Tastenschritt, 4 cm/s Referenzbewegung, maximal
2.5 cm Zielvorlauf; beim Mausziel standardmäßig 6 cm Abstand zur ausgewählten
Oberfläche und mindestens die konfigurierte Transporthöhe.


- `assets/robots/lara5/parameters.json`: extrahierte Kinematik/Grenzen und angenommene Massen.
- `stacklab/sim/convert.py`: Näherungen für Dynamik, Kollisionskörper und Armregelung.
- `stacklab/sim/robot.py`: Tisch, Greifer, Reibung, Physikvorgaben und Erfolgskontrolle.
- `stacklab/config.py`, `scenes/default.json`, `scenes/*.json`: Versuchsszenen und Objektparameter.
- `assets/sources/NOTICE.md`: Herkunft und Prüfsumme der unveränderten RoboDK-Quelldatei.

Modellquelle: https://robodk.com/robot/Neura/LARA-5

Die bisherigen Tests zeigen, dass die implementierten Aufgaben unter diesen
Annahmen funktionieren. Sie ersetzen keine Kalibrierung oder Validierung eines
realen LARA 5. Für den Praktikumsbericht sollten diese Quellen und Annahmen
als Teil des Versuchsaufbaus angegeben werden.
# Ergänzung 2.6: lokale Modelle und Agentensteuerung

Die Parameter in `config/models.lock.json` sind keine NEURA-Einstellungen. Modell-IDs,
Revisionen, Dateigrößen und Prüfsummen stammen aus den veröffentlichten Modellquellen.
Qwen-Samplingprofile, Bolt-Temperatur/top-p und Ministrals Temperatur 0,7 folgen
den Modellkarten; die übrigen festgelegten Werte sind im Lockfile dokumentiert.
Ministrals Systemprompt unter `config/prompts/` stammt unverändert vom Hersteller.

Kontextlänge 8192, Denkbudget 768, Ausgabebudgets, maximal vier Live-Blöcke,
Zeitlimits und die Weltachsen-Konvention für „rechts“ sind eigene Entscheidungen
für diesen Teststand. Die 4-mm-Zentrierung und sonstigen Stapelkriterien bleiben
eigene Prüfkriterien. Die Physik pausiert während der Inferenz, während die Ansicht
bedienbar bleibt. Details und Überschreibungsoptionen: [Modelle](models.md).
