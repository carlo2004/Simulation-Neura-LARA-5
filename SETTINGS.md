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

## Werte im Menü

Die optionalen Koordinaten- und Stapelanzeigen ab Version 2.3 sind eigener
Anwendungscode in `overlays.py`, dargestellt mit MuJoCos Visualisierungsfunktionen.
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
stammt dagegen von Sony über Khronos; Attribution/Lizenz stehen in `source/duck`.
Konvexe Kollisionshülle, Masse und Reibung des importierten Beispiels sind keine
gemessenen Eigenschaften einer realen Gummiente.
Eigene Bedienvorgaben: 5 mm Tastenschritt, 4 cm/s Referenzbewegung, maximal
2.5 cm Zielvorlauf; beim Mausziel standardmäßig 6 cm Abstand zur ausgewählten
Oberfläche und mindestens die konfigurierte Transporthöhe.


- `models/lara5/parameters.json`: extrahierte Kinematik/Grenzen und angenommene Massen.
- `convert_model.py`: Näherungen für Dynamik, Kollisionskörper und Armregelung.
- `simulation.py`: Tisch, Greifer, Reibung, Physikvorgaben und Erfolgskontrolle.
- `core.py`, `scenario.json`, `scenes/*.json`: Versuchsszenen und Objektparameter.
- `source/NOTICE.md`: Herkunft und Prüfsumme der unveränderten RoboDK-Quelldatei.

Modellquelle: https://robodk.com/robot/Neura/LARA-5

Die bisherigen Tests zeigen, dass die implementierten Aufgaben unter diesen
Annahmen funktionieren. Sie ersetzen keine Kalibrierung oder Validierung eines
realen LARA 5. Für den Praktikumsbericht sollten diese Quellen und Annahmen
als Teil des Versuchsaufbaus angegeben werden.
