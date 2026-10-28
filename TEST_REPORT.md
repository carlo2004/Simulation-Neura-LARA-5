# Ergänzung — Version 2.6: 8B-/9B-Modelle und Live-Feedback

Ausgeführt am 28.10.2026 unter Linux x86_64/Python 3.12.14, MuJoCo 3.3.7,
acht Inferenzthreads, ohne GPU und ohne gehostete Modell-API.

## Einrichtung und Software

- Qwen3.5-9B (9.653.104.368 Originalparameter), Ministral 3 8B Reasoning
  (8.918.026.240) und Nemotron 3.5 Bolt (7.996.156.490) vollständig heruntergeladen,
  jeweils Q4_K_M. Die 4B-Referenz bleibt verfügbar. Alle liegen unter der auf deinen
  Wunsch erweiterten 10B-Grenze. Revisionen und Prüfsummen sind festgelegt.
- Der abschließende reale Aufruf `llm_test.py setup --all` prüft alle vier
  Gewichtedateien per SHA-256 und beendet sich erfolgreich.
- **65/65 Softwaretests bestanden.** Sie prüfen auch echte Kontaktphysik,
  Einzelbefehle über denselben Interpreter, Feedbackkorrekturen, Jog-Invarianten,
  Pausieren der Physik während der Inferenz, SSE, Modellauswahl und Abbrüche.
- Ein bekanntes Kontrollprogramm stapelt weiterhin mit 20/20 stabilen Proben.
  Es wurde den echten Modellen nicht als Beispiel mitgegeben. No-op wird abgelehnt.
- Die Live-Konsole hält die Szene und das Modell über mehrere Prompts offen.
  Sichtbar sind generierter Code, Aktionen und tatsächliches Ausführungsfeedback.
  `/stop` wurde zusätzlich im echten interaktiven Terminal während der Generierung
  geprüft: abgebrochene Episode und unveränderte TCP-Position.
- Ein beim abschließenden Setup gefundener Alias-/Dateipfadfehler ist korrigiert
  und durch einen Regressionstest sowie den erfolgreichen Gesamtlauf abgesichert.

## Tatsächliche Modellversuche

Die vorgegebene 5-cm-Rechtsbewegung wird von **allen drei neuen Modellen** erreicht.
Das Ziel stammt aus dem Testfall, nicht aus einer Selbsteinschätzung des Modells.

In der finalen Live-Probe werden zwei Prompts in derselben Szene nacheinander
gegeben: 5 cm rechts, dann 5 cm links. Gemessen werden die tatsächlichen TCP-
Verschiebungen einschließlich der unveränderten beiden anderen Achsen:

| Modell | Modus | Korrekte Bewegungen | Abschluss |
|---|---|---:|---|
| Qwen3.5-9B | Non-Thinking | 2/2 | beide Aufgaben beendet |
| Ministral 3 8B Reasoning | Thinking | 2/2 | beide Aufgaben beendet |
| Nemotron 3.5 Bolt | Non-Thinking | 1/2 | zweite Aufgabe am Blocklimit; etwa 10 cm statt 5 cm |

Die beiden Qwen-Aufgaben benötigen zusammen rund 80 Sekunden, die beiden
Ministral-Aufgaben rund 638 Sekunden auf dieser CPU und mit den protokollierten
Modi. Das ist eine kleine Entwicklungsprobe, kein allgemeiner Modell- oder
Geschwindigkeitsbenchmark. Für den ersten Live-Test ist Qwen9B/Non-Thinking
hier der sinnvollste Ausgangspunkt; Thinking und die anderen Modelle sind wählbar.

**Stapelversuche bleiben erfolglos.** Zwei-Block-Versuche aller drei Modelle,
ein Vier-Block-Versuch von Bolt, ein Qwen-Versuch mit höherem Denk-/Ausgabebudget
und ein abschließender Qwen-Vier-Block-Versuch mit Jog-API bestehen die Kriterien
nicht. Der letzte Qwen-Lauf endet mit 0/20. Das Feedback bewirkt bislang keine
zuverlässige vollständige Greif-/Ablagestrategie. Ein früher Bolt-Versuch erreicht
Kontakt und passende Stapelhöhe, verfehlt aber mit ca. 5,7 mm XY-Fehler die
unveränderte 4-mm-Grenze. Er wird ausdrücklich nicht als Erfolg gezählt.

Die Rohantworten und Zustände sind erhalten. Code wird nicht repariert oder durch
handgeschriebene Stapelprogramme ersetzt. Diese Fehlversuche sind ein Ausgangspunkt
für euer Finetuning, kein fertiger autonomer Stapelagent.

## Grenzen und Reproduzierbarkeit

Während der Entwicklung wurden API, Feedbackprotokoll und Zahlenformatierung
verbessert; die verschiedenen Versuchsbedingungen sind getrennt archiviert und
werden nicht zu einer gemeinsamen Erfolgsquote addiert. Gegenüber dem alten
4B-Pilot sind unter anderem Beobachtungen und API verändert. Ein direkter
4B-/9B-Leistungsvergleich lässt sich daraus nicht ableiten.

Die finale Schnittstelle besitzt Position, absolute Bewegung, relatives Joggen,
Greifer und begrenztes Warten. Für freie Sprache bleibt semantischer Erfolg ohne
extern vorgegebenes Ziel unbestätigt; tatsächliche Stapelprüfungen sind separat
sichtbar. Die Modellinferenz pausiert die Physik, die Ansicht bleibt bedienbar.
Die Simulation bleibt Kontaktphysik ohne Objekt-Teleportation oder Attach-Constraints.

Noch kein Training und kein unabhängiges Testset. Für den Seminarvergleich müssen
API, Prompts, Szenen/Seeds und Budgets vorab eingefroren werden. Originalmodell
und finetuniertes Modell bekommen dieselben Bedingungen. Kein manueller Test des
nativen Desktopfensters und kein Modell-Inferenztest auf Windows/macOS; die
GitHub-Softwarematrix prüft diese Plattformaspekte nur soweit dort konfiguriert.

Anleitung: `LOCAL_LLM.md`. Messdaten, Setupnachweis und vollständige Erklärungen:
`test_results/models_8b/`. Die unveränderten bisherigen Berichte folgen darunter.

---

# Ergänzung — Version 2.5, lokales Sprachmodell

Ausgeführt am 28.10.2026 unter Linux x86_64, Python 3.12.14 und MuJoCo 3.3.7.
Qwen/Qwen3.5-4B (Original: 4.659.865.088 Gesamtparameter) wurde als Q4_K_M
vollständig heruntergeladen und SHA-256-geprüft. llama.cpp b11951 läuft lokal
auf der CPU; acht Inferenzthreads, kein Cloud-Modell und keine GPU.

- **47/47 Softwaretests bestanden.** Darunter sind die 35 bisherigen Tests,
  die Begrenzung der generierten Programme und unabhängige Physikkontrollen.
- Das bekannte Kontrollprogramm besteht durch denselben AST-Interpreter und
  Physikauswerter mit **20/20**, ohne `stack()` aufzurufen. Ein No-op scheitert
  erwartungsgemäß mit 0/20. Das Kontrollprogramm war nicht Teil des Modellprompts.
- Der finale Non-Thinking-Entwicklungspilot erzeugt und führt drei Programme
  tatsächlich aus: **0/3 erfolgreiche Stapel**, jeweils 0/20 Stabilitätsproben.
  Gültiges Python und ein laufender Arm allein werden nicht als Erfolg gewertet.
- Die Programme verwenden feste Koordinaten und führen die notwendige
  Abfrage-/Greif-/Ablagefolge nicht korrekt aus. Die unabhängige Prüfung erkennt
  fehlende Zentrierung, Höhe und Kontakt korrekt als Fehlschlag.
- Generierung inklusive Modellstart: rund **20–22 Sekunden pro Fall**;
  reine Ausgabe ungefähr **12–13 Tokens/s** auf dieser CPU.
- Modell, Runtime, API-Prompt, Szenen, Seed, Sampling, Ausgabetokens und Rohantworten
  sind dokumentiert. Das finale Instruct-Profil verwendet Temperatur 0,7/top-p 0,8,
  768 Ausgabetokens, 4096 Kontexttokens und keine zusätzliche Decoding-Grammatik.
- Ein zusätzlicher Thinking-Versuch mit 2048 Tokens scheitert ebenfalls: **0/1**,
  0/20 Stabilitätsproben. Das Modell fragt Positionen ab, schließt den Greifer
  aber auf 24 cm Höhe und greift den Würfel nicht. Generierung inklusive Start:
  75,3 Sekunden / 842 Ausgabetokens einschließlich Thinking. Separater Nachweis:
  `test_results/local_llm/thinking/summary.json`.
- Vorversuche mit rohem ChatML, dem hier abstürzenden nativen Completion-CLI,
  anderem Sampling und JSON-Grammatik sind getrennt archiviert. Im finalen Pfad
  startet und beendet Python selbst einen nur an Loopback gebundenen llama-server.

**Ergebnis:** Download, lokale Inferenz, begrenzte Programmausführung und
physikalische Bewertung funktionieren. Die geprüfte Modellkonfiguration löst
unsere Stapelaufgaben bislang nicht. Das ist ein erster Ausgangsbefund für den
späteren Finetuning-Vergleich, kein Nachweis allgemeiner Untauglichkeit eines
4B-/7B-Modells. Quantisierung, kurzer Kontext, begrenzte Ausgabelänge und
Non-Thinking sind eigene Versuchsbedingungen; keine Gleichsetzung mit den
vollständigen Benchmark-Ergebnissen des Herstellers.

Anleitung: `LOCAL_LLM.md`; tatsächlich übergebene Befehlsbeschreibung: `LLM_API.md`.
Messdaten und Entwicklungsprotokoll: `test_results/local_llm/`. Gewichte sind
absichtlich nicht auf GitHub; `llm_test.py setup` lädt die festgelegte Datei.
Der native Desktopviewer wurde hier nicht manuell bedient. Python 3.13 und
Windows werden zusätzlich über GitHub Actions geprüft; das ist kein lokaler
Modell-Inferenztest auf Windows. Modell-/Dynamikgrenzen aus dem bisherigen
Bericht gelten unverändert.

---

# Ergänzung — Version 2.4.1, Python-Umgebung und Git

Ausgeführt am 27.10.2026. Frisch eingerichtete lokale Umgebung mit Python 3.13.16
unter Linux; kein PYTHONPATH auf die früher installierten Pakete.

- bootstrap.py verwendet ausschließlich den angegebenen .venv-Interpreter für
  Paketinstallation, Diagnose und Tests; bestehende Umgebungen werden weiterverwendet.
- 35/35 Unittests bestanden, einschließlich Kinematik, freier Kontaktphysik,
  Mesh-Import, Tastatursteuerungslogik und Szenenänderungen.
- 14/14 Standardszenarien und 8/8 Objektszenarien erneut bestanden.
- 5/5 Schiebeversuche sowie der zusätzliche Test mit eingespeisten Tasten/Mausziel
  bestanden. trimesh 4.9.0 wurde aus dieser lokalen Umgebung importiert.
- Die MuJoCo-Version bleibt 3.3.7; Physikparameter und Modell wurden nicht geändert.
- Eine weitere frische Python-3.12-Umgebung besteht ebenfalls 35/35 Tests.
- Ein frischer Code-Checkout ohne große Quelldateien oder erzeugte Meshes wurde
  mit bootstrap.py eingerichtet: beide Downloads SHA-256-geprüft, LARA konvertiert,
  Entengeometrie erzeugt und anschließend 35/35 Tests erfolgreich ausgeführt.
- Alle zehn neu erzeugten LARA-OBJ-Dateien entsprechen bytegenau den bisherigen
  Geometrien. Die versionierten XML-/Parameterdefinitionen bleiben unverändert.
- check_env.py zeigt den konkreten Interpreter und alle sieben direkten Pakete.
- Die GitHub-Actions-Konfiguration richtet eine lokale Umgebung für Python
  3.12 und 3.13 auf Linux und Windows ein. Ihr Live-Status steht in GitHub Actions;
  die Konfigurationsdatei allein ist noch kein bestandener Windows-Test.

Paketversionen und Ergebnisse des 3.13-Laufs: test_results/python313.json.
Die vollständige Python-3.13-Paketliste steht in test_results/python313-requirements.txt
und ist ein Umgebungsnachweis, kein plattformübergreifendes Lockfile.
Die unverändert gültigen Modell-/GUI-Grenzen stehen im folgenden Bericht.
Erzeugte output-Dateien sind absichtlich nicht mit Git versioniert.

---

# Testbericht — Stack Lab LARA 5, Version 2.4

Ausgeführt am 27.10.2026 unter Linux / Python 3.12.14, MuJoCo 3.3.7,
NumPy 2.5.4, SciPy 1.17.0 und trimesh 4.9.0.

## Ergebnis

- 35/35 Unittests erfolgreich, einschließlich aller bisherigen Modell-/Physiktests.
- 14/14 Standard-Stapelszenarien und 8/8 Objektszenarien erneut erfolgreich.
- 5/5 zusätzliche physische Schiebeversuche erfolgreich.
- Zusätzlicher Test mit eingespeisten Tasten, Stoppen/Esc und Mausziel-Fahrt erfolgreich.
- Echte Terminaldatei examples/import_duck.txt: Import, Physikszene und Ente-Schieben
  erfolgreich; Befehl meldet Fingerkontakt und rund 4.95 cm Objektverschiebung.
- EGL-Bilder der importierten Szene, vor/nach dem Schieben und des Handmodus erstellt
  und visuell geprüft. Keine manuelle Desktopprüfung.

## Gemessene Schiebewege

| Fall | Weg in gewünschter Richtung | Fingerkontakt erkannt |
|---|---|---|
| cube_x | 60.26 mm | True |
| cube_y | 59.91 mm | True |
| ball | 65.31 mm | True |
| cylinder | 58.87 mm | True |
| duck_mesh | 49.55 mm | True |

Wünsche: je 60 mm bei Würfeln/Kugel/Zylinder, 50 mm bei der Ente. Abweichungen
sind reale Ergebnisse der Kontakt-/Reibungssimulation, keine nachträglich gesetzten
Objektpositionen. Freie Objekt-Joints und fehlende Attach-Constraints bleiben erhalten.
Während dieser Tests waren Objekt-Hilfskräfte und externe Körperkräfte null.
Nur der Arm und die Finger wurden über die vorhandenen Aktuatoren gesteuert.

## Neue Verhaltensprüfungen

- Der Handmodus ist standardmäßig aus. Der Viewer-Callback reiht ausschließlich
  Tastenereignisse ein; er verändert keine MuJoCo-Daten im Render-Thread.
- Arrows/Home/End erreichen die jeweiligen 5-mm-TCP-Ziele mit weniger als 1 mm
  Fehler. Der Eingabepuffer nimmt keine lange Tastenfolge vorweg; ein Burst von
  100 Wiederholungen vor der Verarbeitung führt nur zu einem Zielschritt.
- Insert/Delete öffnen/schließen tatsächlich die Finger. Leertaste leert den Puffer
  und hält die aktuelle Gelenkstellung, Esc beendet zusätzlich den Modus.
- Ziele außerhalb des Arbeitsraums werden vor Änderung des Reglerziels abgelehnt.
  Während Terminalbefehlen erzeugte Tasten werden nicht anschließend abgespielt.
  Reset beendet den Handmodus.
- Tischpunkte und objektlokale Doppelklick-Punkte werden in Weltkoordinaten
  umgerechnet. Auswahl des Roboters wird ignoriert; unzulässige Zielhöhe wird vor
  Bewegung abgelehnt. Der Arm erreicht den eingespeisten Mauszielpunkt auf 24 cm Höhe.
- Alle vier Importformate (OBJ, STL, PLY, GLB) wurden mit einem bekannten Quader
  eingelesen; Proportionen und GLB-Y-oben-Umrechnung sind geprüft. Die importierte
  Sony-Ente aus einer echten GLB-Datei steht stabil auf dem Tisch und lässt sich schieben.
- Vorbereitete Meshes besitzen relative Pfade; eine gespeicherte Szene funktioniert
  auch nach Entfernen der ursprünglichen Quelldatei. Die separate Darstellung ist
  kollisionsfrei, die physische Geometrie verwendet eine konvexe Hülle.
- Ungültige, flache/fehlende Mesh-Dateien und Pfade außerhalb des Asset-Verzeichnisses
  werden abgelehnt. Ungültige Schiebebefehle verändern weder Zustand noch Simulationszeit.

Die 22 Stapelszenarien wurden nach den Codeänderungen erneut ausgeführt; alle
blieben erfolgreich. Wandzeit: 81.0 s für die 14 Standardfälle,
56.9 s für die acht Objektszenarien (parallel ausgeführt).

## Grenzen

Die Tastenereignisse und ausgewählten Punkte wurden für die automatisierten
Steuerungstests eingespeist. Danach liefen die echten IK-, Regler- und Physikpfade.
Das native Fenster und tatsächliche Betriebssystem-Tasten-/Mausereignisse wurden
hier nicht manuell auf einem Desktop getestet. Die Darstellung wurde mit EGL geprüft.
MuJoCos vorhandene Doppelklick-/Mauskraftfunktion wird gemäß seiner öffentlichen
Viewer-Schnittstelle verwendet; keine privaten GLFW-Fensterhooks.

Mesh-Import: starr und einfarbig, keine Texturen/Animationen. Konvexe Kollisionshüllen
füllen Löcher und Vertiefungen. Masse/Reibung sind eigene Annahmen. Insbesondere ist
die Ente kein elastisches Gummimodell. Diese Tests beweisen eine funktionierende
Implementierung im Teststand, keine genaue Nachbildung realer Materialeigenschaften.
Die einfache Schiebestrategie und Mausziel-Fahrt haben keine allgemeine Hindernisplanung.

LARA-Dynamik, Greifer und Kollisionsnäherungen bleiben wie zuvor nicht vom Hersteller
kalibriert. Kein Hardwaretest. Die mitgelieferten Szenarien sind Entwicklungstests,
kein unabhängiges LLM-Testset. Handmodus und Mauskräfte bei automatischer Evaluation
nicht verwenden; Szenen und erlaubte API vorher festlegen.

## Prüfdateien

- output/unit_tests_2.4.txt: aktueller Testlauf.
- output/validation.json, output/objects_validation.json: 22 erneut ausgeführte Stapelszenarien.
- output/controls_validation.json und .txt: Schiebe- und Steuerungsversuche.
- output/import_duck_console.txt: tatsächlich ausgeführter Konsolenimport mit Schieben.
- output/duck_scene.png, duck_before_push.png, duck_after_push.png: echte Renderzustände.
- output/manual_preview.png: Handmodus-Darstellung mit eingespeister Auswahl.
- source/duck: unveränderte Quelle, Lizenz und dokumentierte Bearbeitung.

Ältere output/overlays_* Dateien und output/annotated_demo stammen aus Version 2.3.
Deren Video ist ein Referenzlauf der früheren Achsen-/Stapeldarstellung, kein neuer
Tastatur-/Maus-Mitschnitt dieser Version. Bedienung und Herkunft: README.md / SETTINGS.md.
