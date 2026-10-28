# Erstes lokales Modell im LARA-Teststand

Der Test verbindet eine Sprachaufgabe mit einem tatsächlich vom lokalen Modell
erzeugten Python-Programm und der vorhandenen MuJoCo-Kontaktphysik. Es wird kein
Cloud-Inferenzdienst verwendet. `stack()` und die handgeschriebene Stapelstrategie
sind für das Modell nicht erreichbar. Ein erfolgreicher Installations- oder
Unittest bedeutet noch keinen erfolgreichen LLM-Stapelversuch.

## Modell und Auswahl

Ausgewählt ist **Qwen/Qwen3.5-4B**, Stand 28.10.2026. Mit „Artificial Intelligent“
wurde hier **Artificial Analysis** als Vergleichsplattform angenommen. Die dort
verglichenen kleinen Modelle machten Qwen3.5-4B zu einem passenden Kandidaten;
allgemeine Ranglisten sind kein Nachweis für Roboterprogrammierung.

Die offizielle Hugging-Face-Metadatenabfrage meldet **4.659.865.088 Parameter für
das vollständige Originalmodell**, einschließlich der visuellen Komponenten.
Damit liegt es unter der strikten Grenze von **7.000.000.000 Gesamtparametern**.
Für diesen textbasierten Versuch wird nur das Sprachmodell geladen. Die Zahl
„4B“ im Namen oder die Größe einer quantisierten Datei allein wäre kein
ausreichender Nachweis für diese Grenze. Ein kleineres, geeignetes Modell ist
hier sinnvoller als eine Überschreitung der Grenze für das nächstgrößere Modell.

Das Setup lädt eine **Q4_K_M-GGUF-Quantisierung von Unsloth**, exakt 2.740.937.888
Bytes. Es ist das unverändert verwendete, bereits nachtrainierte öffentliche
Qwen-Modell, noch **kein für unser Praktikum finetuniertes Modell**. Revision,
Dateigröße, SHA-256, Originalparameterzahl und die Plattform-Downloads der
llama.cpp-Version **b11951** stehen in `local_model.lock.json`. Modell und
Runtime werden beim Setup mit Größe und SHA-256 geprüft. Gewichte bleiben lokal
und werden nicht auf GitHub hochgeladen.

Quellen für die Auswahl und Einrichtung:

- Offizielles Modell und Sampling-Empfehlungen: https://huggingface.co/Qwen/Qwen3.5-4B
- Originalmetadaten: https://huggingface.co/api/models/Qwen/Qwen3.5-4B
- Quantisierung: https://huggingface.co/unsloth/Qwen3.5-4B-GGUF
- Laufzeit: https://github.com/ggml-org/llama.cpp/releases/tag/b11951
- Vergleich: https://artificialanalysis.ai/models/qwen3-5-4b

Quantisierung, kurze Ausgabebudgets und deaktiviertes Thinking können die Qualität
beeinflussen. Diese Pilotkonfiguration entspricht keinem vollständigen
Leaderboard-Benchmark. Alle Einstellungen werden pro Versuch gespeichert.

## Voraussetzungen und Einrichtung

- Das aktuelle Repository, Python 3.12 oder 3.13 und Internet für die Einrichtung.
- Ein 64-Bit-System: Windows/Linux x86_64 oder macOS Apple Silicon/Intel.
  Der tatsächliche CPU-Inferenzlauf wurde hier unter Linux x86_64 geprüft;
  die übrigen Laufzeitarchive sind festgelegt, aber hier nicht ausgeführt worden.
- Empfohlen: 12 GB RAM und mindestens 5 GB freier Speicher. Hier liefen die
  Versuche mit ungefähr 10,4 GB System-RAM, acht CPU-Threads und ohne GPU.
- Für `--gui` zusätzlich ein lokaler Desktop mit OpenGL. Ohne `--gui` läuft die
  physikalische Prüfung ohne Fenster. Kein API-Key und kein Ollama nötig.

Im Repository-Ordner unter Windows/PowerShell:

```powershell
git pull --ff-only
py bootstrap.py
.\.venv\Scripts\python.exe llm_test.py setup
.\.venv\Scripts\python.exe llm_test.py test --case red-on-blue --gui --axes --stackviz
```

Unter Linux/macOS:

```bash
git pull --ff-only
python3 bootstrap.py
.venv/bin/python llm_test.py setup
.venv/bin/python llm_test.py test --case red-on-blue --gui --axes --stackviz
```

Für das macOS-Fenster wählt der Test automatisch `mjpython` aus derselben `.venv`.
Der erste Modell-Download umfasst etwa **2,74 GB**. Abgebrochene Downloads werden
nach Möglichkeit fortgesetzt und anschließend vollständig geprüft. Scheitert
eine Prüfsumme, wird die betreffende Datei abgelehnt. Nach erfolgreichem Setup
benötigt die Inferenz keine Internetverbindung. Ein erneutes `setup` prüft den Cache.

Es läuft vorübergehend ein llama.cpp-Prozess, ausschließlich an `127.0.0.1` mit
einem freien lokalen Port. Nach der Antwort oder einem Fehler wird er beendet.
Der Client umgeht HTTP-Proxys für diese lokale Verbindung. Es wird kein dauerhaft
laufender Dienst eingerichtet. Der erste CPU-Versuch kann ungefähr eine Minute
oder länger dauern; Thinking benötigt entsprechend mehr Zeit.

## Was das Modell darf

Die vollständige minimale Beschreibung steht in **`LLM_API.md`** und wird dem
Modell tatsächlich als Systemnachricht übergeben. Es gibt vier Methoden:

| Methode | Bedeutung |
|---|---|
| `robot.position("red")` | Aktuellen Objektmittelpunkt in Weltmetern abfragen |
| `robot.move_to([x, y, z])` | TCP bei senkrechtem Greifer an ein Ziel bewegen |
| `robot.gripper(closed=True)` / `False` | Finger schließen / öffnen |
| `robot.step(0.5)` | Physik für eine begrenzte Zeit weiterlaufen lassen |

Das Modell erhält die Aufgabe sowie Namen, Formen und Abmessungen der vorhandenen
Objekte. Positionen muss es über die API abfragen. Das sind exakte Zustandsdaten
des Simulators; Bilderkennung ist nicht Teil dieses ersten Versuchs. IK,
Interpolation und Gelenkregelung erledigt der Teststand. Das Modell programmiert
die Abfolge von Abfragen, Bewegungen und Greiferaktionen.

Die Antwort ist ein JSON-Objekt mit einem Python-Programm im Feld `code`.
Die JSON-Struktur wird nach der Generierung geprüft; es wird keine zusätzliche
Decoding-Grammatik erzwungen. Es wird kein fertiger Stapelcode als Beispiel
mitgegeben und generierter Code wird nicht von Hand repariert.

Ein kleiner AST-Interpreter führt ausschließlich die dokumentierte Python-Teilmenge
aus: lokale Variablen, kurze Listen/Tupel, Indexlesen und einfache Zahlenrechnung.
Keine Imports, Schleifen, beliebiger Python-Code oder Dateizugriffe; kein `exec()`.
Arbeitsraum, Anzahl der Anweisungen/API-Aufrufe, Wartezeit und Prozesslaufzeit sind
begrenzt. Das ist eine begrenzte Ausführungsoberfläche, keine Betriebssystem-VM.

Die getrennte Auswertung prüft 20-mal über zwei Simulationssekunden: Zentrierung,
Höhe, Ruhe, tatsächlichen Kontakt und die Stützkette zum Tisch. Zusätzlich darf
der Greifer den oberen Würfel nicht berühren und muss mindestens 7,5 cm vom
Objektmittelpunkt entfernt sein. Der generierte Code kann diese Auswertung nicht
aufrufen. Achsen und Prüfrahmen sind nur mit den entsprechenden Optionen sichtbar.

## Eigene erste Versuche

Die drei Entwicklungsszenarien umfassen Rot auf Blau, Blau auf Rot und Grün auf
Blau. Die letzten beiden variieren die Positionen mit einem festgehaltenen Seed.

```text
python llm_test.py test --suite
python llm_test.py test --case green-on-blue --seed 123 --gui
python llm_test.py test --case red-on-blue --instruction "Stack the red cube on the blue cube."
python llm_test.py test --case red-on-blue --thinking --max-tokens 2048
```

`python` meint immer den `.venv`-Interpreter. `--instruction` ändert nur die
Formulierung, nicht das ausgewertete Zielpaar des gewählten Falls. Deshalb dort
keinen anderen Zielstapel verlangen. Für `--suite` ist diese Option ausgeschlossen.

Standard ist der schnelle **Non-Thinking-Modus** mit 768 Ausgabetokens und Qwens
Instruct-Samplingprofil: Temperatur 0,7, top-p 0,8, top-k 20, min-p 0,
Presence-Penalty 1,5 und Repeat-Penalty 1,0. `--thinking` nutzt das veröffentlichte
Coding-Profil mit Temperatur 0,6, top-p 0,95 und Presence-Penalty 0; standardmäßig
2048 Ausgabetokens. Das Kontextfenster ist bewusst auf 4096 Tokens begrenzt.
Token- oder Zeitlimits werden als Fehlschlag protokolliert, nicht als fertige
Antwort ausgeführt. Ein festgehaltener Seed verbessert Wiederholbarkeit, garantiert
aber keine bitgleichen Ergebnisse über unterschiedliche CPUs/Runtime-Versionen.

Weitere Optionen zeigt `python llm_test.py test --help`, unter anderem CPU-Threads,
Zeitlimits und ein eigener neuer Ausgabeordner. Ein vorhandener nichtleerer
Ausgabeordner wird nicht überschrieben. Im GUI-Lauf erfolgt zuerst die Generierung,
dann öffnet sich das Fenster; nach der Auswertung bleibt das Ergebnis für weitere
zehn Simulationssekunden sichtbar. `Tab`/`Umschalt+Tab` schalten die Seitenleisten um.

## Ergebnisse aufbewahren und wissenschaftlich verwenden

Jeder Lauf erzeugt unter `output/llm_<Zeitstempel>/`:

- `summary.json`: Erfolg/Fehlschlag und Konfiguration aller Fälle;
- pro Fall die konkrete Szene, beide Prompttexte, Nachrichten und die Anfrage;
- `raw_response.txt`, `response.json` und unverändert extrahiertes `generated.py`;
- `generation.json`: Modellrevision/Hash, Sampling, Tokens und Laufzeiten;
- `execution.json`: tatsächliche Aktionen, Objektpositionen und unabhängige Checks;
- `result.json` sowie Inferenz-/Simulationslogs, auch bei Fehlern.

Die installierten Paketversionen lassen sich zusätzlich mit `python -m pip freeze`
festhalten. Erfolgreich ist ein Fall nur bei `success: true`, nicht schon dann,
wenn Python syntaktisch gültig war. Der Prozess endet bei einem fehlgeschlagenen
Fall mit Exitcode 1. Einrichtung und Softwareprüfungen:

```text
python bootstrap.py --check
python -m unittest discover -s tests -v
```

Die Ergebnisse dieses Arbeitsstands stehen in `TEST_REPORT.md` und die ausgewählten
unveränderten Pilotdateien unter `test_results/local_llm/`. Vorversuche an der
Anbindung werden getrennt von den eigentlichen Modellversuchen dokumentiert.

Für das Seminar ist dies ein **Entwicklungspilot**, kein unabhängiges Testset.
Vor dem Vergleich Originalmodell gegen Finetuning müssen neue, zurückgehaltene
Aufgaben/Seeds, Prompt, Quantisierung, Sampling und Zeit-/Tokenbudgets festgelegt
werden. Derselbe Prompt und dieselben APIs müssen für beide Modelle gelten.
Syntaxfehler, API-Fehler, Timeouts und physikalische Fehlschläge getrennt zählen.
Eine spätere Promptoptimierung oder ein Beispiel im Prompt ist eine eigene
Versuchsbedingung. Es wurde hier noch kein Modell trainiert.
