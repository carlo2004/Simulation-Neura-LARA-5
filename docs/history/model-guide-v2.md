> Historisches Dokument zu Version 2.6. Die aktuellen Startbefehle stehen in [models.md](../models.md).

# Lokale Modelle, Live-Prompts und Ausführungsfeedback — Version 2.6

Der LARA-Teststand übersetzt freie Sprache mit einem lokalen Modell in Python,
führt den begrenzten Code in MuJoCo aus und meldet tatsächliche Positionen,
Kontakte und Fehler zurück. Ein Modell kann mehrere Blöcke für eine Aufgabe
verwenden. Das ist der Versuchsaufbau für euren späteren Finetuning-Vergleich;
ein erfolgreicher Softwaretest allein beweist keine erfolgreiche Modellstrategie.

## 1. Modellwahl und Größe

Die frühere strikte 7B-Grenze wurde auf deinen Wunsch erweitert. Die neue
Obergrenze beträgt 10 Milliarden **Gesamtparameter**, sodass alle drei ausdrücklich
gewünschten Modelle hineinpassen. Der vollständige Originalcheckpoint wird gezählt,
auch wenn wir für diese Textaufgaben nur den Sprachmodellteil benutzen.

| Alias | Gewünschtes Modell | Originalparameter | GGUF-Download | Modus ab Werk |
|---|---|---:|---:|---|
| `qwen9b` | `Qwen/Qwen3.5-9B` | 9.653.104.368 | 5,68 GB | Thinking |
| `ministral8b` | `mistralai/Ministral-3-8B-Reasoning-2512` | 8.918.026.240 | 5,20 GB | Reasoning, kein Abschalten |
| `nemotron8b` | `nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB` | 7.996.156.490 | 6,18 GB | Non-Thinking |
| `qwen4b` | `Qwen/Qwen3.5-4B` | 4.659.865.088 | 2,74 GB | Non-Thinking, bisherige Referenz |

„E4B“ bei Bolt bezeichnet die effektive Größe; das Modell hat insgesamt rund 8B
Parameter. „4GB“ im Modellnamen ist keine Angabe der Downloadgröße: die konkrete
GGUF-Datei hat 6.180.446.208 Bytes. Die Zahlen stammen aus den öffentlichen
Hugging-Face-Metadaten der Originalmodelle; bei Bolt aus dem BF16-Gegenstück.

Alle vier Einträge verwenden Q4_K_M. Für Ministral und Bolt wird die vom Hersteller
veröffentlichte GGUF verwendet, für Qwen die festgelegte Unsloth-Konvertierung.
`local_model.lock.json` enthält genaue Revisionen, Größen, SHA-256-Prüfsummen,
Samplingprofile, Trainingsquellen, Lizenzen und die llama.cpp-Laufzeit b11951.
Qwen/Ministral verwenden Apache-2.0, Bolt OpenMDW-1.1. Die Herstellerquellen:

- https://huggingface.co/Qwen/Qwen3.5-9B
- https://huggingface.co/mistralai/Ministral-3-8B-Reasoning-2512
- https://huggingface.co/mistralai/Ministral-3-8B-Reasoning-2512-GGUF
- https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB
- https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-BF16

Größe und allgemeine Leaderboards garantieren keinen Erfolg beim Stapeln.
Die tatsächlichen Messungen dieses Arbeitsstands stehen in `TEST_REPORT.md` und
`test_results/models_8b/`. Der unveränderte frühere 4B-Pilot bleibt unter
`test_results/local_llm/` erhalten.

## 2. Voraussetzungen und Einrichtung

Python 3.12 oder 3.13, ein 64-Bit-System und Internet für die erste Einrichtung.
Unterstützte Downloadziele: Windows/Linux x86_64 sowie macOS Intel/Apple Silicon.
Die echte Modellinferenz wurde hier unter Linux x86_64 auf der CPU geprüft.
Windows/Linux-Softwaretests laufen zusätzlich über GitHub Actions; das ist kein
Windows-Modelltest. Der native Desktopviewer wurde hier nicht manuell bedient.

Empfohlen: 16 GB RAM. Die Modelle liefen hier einzeln mit rund 10,45 GB System-RAM.
Nur ein Modell wird gleichzeitig geladen. Alle vier Gewichte belegen zusammen
rund 19,8 GB; plane mindestens 25 GB freien Speicher für Einrichtung und Projekt.
Die mitgelieferte Laufzeit verwendet die CPU. Ein API-Key oder Ollama ist nicht nötig.
Für die 3D-Ansicht benötigst du einen Desktop mit OpenGL.

Im Repository-Ordner unter Windows/PowerShell:

```powershell
git pull --ff-only
py bootstrap.py
.\.venv\Scripts\python.exe llm_test.py models
.\.venv\Scripts\python.exe llm_test.py setup --model qwen9b
.\.venv\Scripts\python.exe llm_chat.py --model qwen9b --no-thinking --axes --stackviz red blue
```

Linux/macOS entsprechend `.venv/bin/python` verwenden:

```bash
python3 bootstrap.py
.venv/bin/python llm_test.py setup --model qwen9b
.venv/bin/python llm_chat.py --model qwen9b --no-thinking --axes --stackviz red blue
```

Unter macOS wählt der Live-Einstieg für die GUI automatisch `mjpython` aus derselben
Umgebung, wenn vorhanden. Alternativ direkt `.venv/bin/mjpython llm_chat.py ...`.
Alle Pakete und Tests müssen denselben `.venv`-Interpreter benutzen.

Alle Modelle nacheinander herunterladen und prüfen:

```text
python llm_test.py setup --all
```

`python` meint in diesen Beispielen immer den `.venv`-Interpreter. `--model` akzeptiert
auch die oben genannten vollständigen Hugging-Face-IDs. Downloads sind fortsetzbar;
Größe und SHA-256 werden vor Verwendung des fertigen Downloads geprüft.
Der Downloader prüft vor dem Start den Platz für die noch fehlenden Bytes und hält
während des Transfers 512 MiB Reserve frei. Bei Platzmangel stoppt er mit einer
klaren Fehlermeldung; bereits installierte Modelle werden nicht automatisch gelöscht. Nach dem
Setup ist die Inferenz offline nutzbar. Gewichte und Runtime bleiben außerhalb von Git.

## 3. Live mit dem Roboter sprechen

Das Terminal zeigt `llm>`. Beispielsweise einzeln eingeben:

```text
Bewege den Greifer 5 cm nach rechts.
Bewege den Greifer 5 cm nach links.
Staple den roten Würfel auf den blauen Würfel.
Setze anschließend den grünen Würfel auf den roten.
```

Die Beispiele sind Testaufgaben, keine garantierten Mustererfolge. Standardmäßig
enthält die Live-Szene drei Würfel. `--config scenario.json` verwendet zwei.
Der gleiche physische Zustand bleibt über mehrere Prompts erhalten.
Für relative Verschiebungen gibt es zusätzlich `robot.jog(Achse, Strecke)`:
das ist derselbe Bewegungsweg wie `jog` in der bisherigen Terminalkonsole.
Die Zielkoordinate wird aus dem gemessenen TCP berechnet, die anderen Achsen
bleiben konstant. Achse und Strecke wählt weiterhin das Modell.

Du siehst die Generierungsphase, den erzeugten Python-Code, jeden ausgeführten
API-Aufruf und danach die Messwerte. `--stream` zeigt zusätzlich die rohe
Antwort während ihrer Entstehung, `--show-thinking` gegebenenfalls das Reasoning.
Unvollständige Antworten werden niemals stückweise als Befehle ausgeführt.

Richtungen sind bewusst in **Weltkoordinaten** festgelegt, unabhängig von der
Kamera: rechts = +X, links = −X, vorne = +Y, hinten = −Y, hoch = +Z. Ohne
Abstandsangabe sind relative Bewegungen 5 cm. Das optionale Achsensystem macht
diesen Bezug sichtbar. Es startet nur mit `--axes` oder `/axes on`.

Nützliche Steuerbefehle:

```text
/status
/axes on
/stackviz red blue
/check red blue
/stop
/reset
/models
/model qwen9b
/sim add yellow cube 0.50 -0.18 0.04
/help
/quit
```

`/stop` unterbricht die Generierung oder die laufende Bewegung. Die Regelung hält
anschließend die gemessenen Gelenke; Objektpositionen werden nicht manipuliert.
Nach einem Generierungsabbruch wird das Modell beim nächsten Prompt neu geladen.
Während einer Aufgabe sind `/stop` und `/quit` unmittelbar verfügbar. Andere
Eingaben werden währenddessen zurückgewiesen, damit sie keine Bewegung nachträglich
ungewollt starten. `Strg+C` beendet das Programm.

`/model` wechselt einen bereits heruntergeladenen Checkpoint. `/sim` verwendet
bewusst die bestehende deterministische Konsole; ihre Szenenänderungen setzen
wie bisher die Szene zurück. Solche Befehle sind Nutzereingaben, keine versteckten
LLM-Fähigkeiten. Tastatursteuerung wird während der LLM-Aufgabe ausgesetzt.
Tab/Umschalt+Tab schalten die MuJoCo-Seitenleisten um.

## 4. Feedback und längere Aufgaben

Das Modell gibt JSON mit `code`, `done` und einer kurzen `message` aus. Der Code
verwendet die kleine, versionierte Schnittstelle in `LLM_API.md`: Objekt- oder
TCP-Position abfragen, bewegen, Greifer öffnen/schließen und Physik warten lassen.
IK und Gelenkregelung erledigt die Simulation. Es gibt kein fertiges `stack()` in
der Modell-API und keinen mitgegebenen Lösungsplan für das Stapeln.

Nach jedem Block erhält das Modell die aktuellen Objekt-/Werkzeugpositionen,
Fingerkontakte, API-Ergebnisse, Fehler und die physikalischen Prüfergebnisse.
Zahlen in Modellnachrichten werden auf sechs Nachkommastellen begrenzt;
Physikzustände und Messprotokolle bleiben in voller Präzision erhalten.
Lokale Python-Variablen gelten nur im jeweiligen Block. Die physische Welt bleibt
erhalten; ein fehlgeschlagener Griff wird zwischen Korrekturen nicht zurückgesetzt.
Im Live-Modus bestätigt das Modell den Abschluss nach Sichtung des Feedbacks mit
einem leeren letzten Codeblock. Eine Fertigmeldung des Modells ist keine
unabhängige Bewertung der Bedeutung deiner freien Sprachaufgabe.

Ein Stapel wird physikalisch anhand von Zentrierung, Höhe, Ruhe, Kontakt und
Stützkette zum Tisch geprüft: 20 Proben über zwei Simulationssekunden. Zusätzlich
muss der Greifer den oberen Würfel freigeben und mindestens 7,5 cm von dessen
Mittelpunkt entfernt sein. Auch nahe, unpräzise Stapelkandidaten werden im Feedback
angezeigt. `/check SOURCE TARGET` gibt dir eine konkrete unabhängige Prüfung.

Während der Modellinferenz **pausiert die Physik**, die Ansicht bleibt bedienbar.
Das verhindert, dass die Rechenzeit eines Modells die physische Ausgangslage eines
Versuchs verändert. Während Bewegungen und Prüfungen läuft die echte Kontaktphysik.
Dieser Aufbau ist eine schrittweise Robotik-Simulation, kein Echtzeitcontroller.

Standard: höchstens vier Blöcke pro Live-Aufgabe, maximal sechs mit `--max-rounds 6`.
Pro Block: höchstens 64 Python-Anweisungen, 48 API-Aufrufe und 15 Sekunden explizite
Wartezeit. Der AST-Interpreter erlaubt keine Imports, Dateizugriffe oder `exec()`.
Arbeitsraum und Prozesslaufzeiten sind begrenzt. Das ist eine begrenzte API,
keine Betriebssystem-VM. Im Modell-API-Kontext werden die letzten beiden
Feedbackwechsel sowie die Aufgabe und aktueller Zustand gehalten.

## 5. Modi vergleichen und automatisch testen

Die vier Entwicklungsszenarien umfassen drei Stapelaufgaben mit zwei/drei Würfeln
und eine unabhängig gemessene 5-cm-Bewegung. Ein Test endet nur bei Erfüllung des
extern vorgegebenen Ziels erfolgreich; `done=true` kann das nicht überschreiben.

```text
python llm_test.py test --model qwen9b --case move-right --no-thinking
python llm_test.py test --model nemotron8b --case red-on-blue --feedback-rounds 4 --gui --stackviz
python llm_test.py test --model ministral8b --suite --feedback-rounds 4
python llm_test.py test --model qwen4b --suite
```

Ohne `--feedback-rounds` erhält das Modell genau einen Programmblock. Mit der Option
bekommt es bis zu dieser Zahl an Blöcken und echte Rückmeldung zur Korrektur.
Diese beiden Bedingungen verwenden ab Version 2.6 dieselben initialen Beobachtungen
und dieselbe Code-Schnittstelle. Mehr Feedback erlaubt mehr Aufrufe/Tokens und ist
als separate Versuchsbedingung auszuweisen. Gegenüber dem ursprünglichen
2.5-Pilot haben sich Prompt, Beobachtungen und Protokoll geändert; dessen 0/3 dürfen
nicht direkt als kontrollierter Modellvergleich mit 2.6 interpretiert werden.

Ein einzelner Live-Prompt ohne interaktive Eingabe:

```text
python llm_chat.py --model nemotron8b --prompt "Bewege den Greifer 5 cm nach rechts." --headless
python llm_chat.py --model qwen9b --prompt "Staple Rot auf Blau." --goal-stack red blue --max-rounds 4 --axes
```

`--prompt` darf mehrfach vorkommen, um Aufgaben nacheinander in derselben Szene
abzuarbeiten. `--goal-stack` gibt ein unabhängig vorgegebenes Prüfziel an und ist
nur mit genau einem Prompt zulässig. Bei beliebigen freien Live-Aufgaben bleibt
`success` im Protokoll `null`; die tatsächlichen Stapelmessungen bleiben separat sichtbar.

Thinking ist bei Qwen optional; Ministral Reasoning kann es nicht abschalten.
Bolt unterstützt beide Modi. `--thinking` / `--no-thinking` überschreibt den Modus.
Die modellabhängigen Samplingprofile sind im Lockfile festgelegt: Qwen nutzt die
veröffentlichten Coding-/Instruct-Profile, Ministral Temperatur 0,7, Bolt Temperatur
1,0 und top-p 0,95. Sonstige festgelegte Samplingwerte sind mitprotokolliert.
Ministrals unveränderter Hersteller-Systemprompt wird vor die API-Beschreibung gesetzt.

Die neuen 8B-/9B-Einträge nutzen 8192 Kontexttokens. Standardmäßig stehen für
Thinking höchstens 768 Tokens zur Verfügung, damit im 2048-Token-Budget Platz für
Code bleibt. Bei Non-Thinking ist das Standard-Testbudget 768, im Live-Modus 2048.
Mehr Raum für schwierige Aufgaben, beispielsweise:

```text
python llm_chat.py --model qwen9b --thinking --thinking-budget 2048 --max-tokens 4096 --generation-timeout 900
```

`--thinking-budget -1` entfernt nur die separate Denkgrenze; `--max-tokens` bleibt
die harte Gesamtgrenze. Antworten, die am Tokenlimit abbrechen, zählen als Fehler.
Auf der CPU sind je nach Modell und Modus erhebliche Wartezeiten möglich; Streaming
und das warm gehaltene Modell machen den Ablauf sichtbar. Es läuft ausschließlich
ein privater llama.cpp-Prozess an `127.0.0.1`, ohne Cloud-Inferenz.

## 6. Nachweise für das Seminar

Jede Aufgabe schreibt eine eigene Ausgabe unter `output/`: Szenenkonfiguration,
initialen/finalen Physikzustand, tatsächlich gesendete Prompts/Anfragen, gestreamte
Antworten, extrahierten Code, Aktionen, Feedback und Ergebnis. `stream.jsonl`
enthält die originalen SSE-Ereignisse; `response.json` setzt deren Text-/Reasoning-
Felder zusammen. Ein `trajectory.jsonl` verbindet Modellantworten und Ausführungsfeedback.
Fehlversuche werden erhalten; Code wird nicht von Hand zu einer Lösung korrigiert.

Das sind zunächst **rohe Versuchsdaten**. Fehlgeschlagene oder unbestätigte Antworten
dürfen nicht automatisch als positive SFT-Beispiele verwendet werden. Finetuning
wurde hier noch nicht ausgeführt. Dafür verwendet ihr später den jeweiligen
Originalcheckpoint aus `training_model_id`/`training_revision`, nicht die GGUF-Datei.
Die vollständigen Nachrichten und Zustands-/Fehlerinformationen sind dafür gespeichert.

Für eine wissenschaftliche Evaluation jetzt neue zurückgehaltene Aufgaben und
Seeds festlegen. Originalmodell und finetuniertes Modell müssen dieselbe API,
Beobachtung, Quantisierung, Modus, Kontext-, Token-, Zeit- und Feedbackbudgets bekommen.
Gültiger Code, API-Erfolg, Zielerfolg, Fehler, Korrekturrunden und Laufzeit getrennt
berichten. Ein fester Seed garantiert keine bitgleichen Resultate über verschiedene
CPUs und Runtime-Versionen. Der LARA-Modellstatus aus der Haupt-README gilt weiterhin.

Softwareprüfungen:

```text
python bootstrap.py --check
python -m unittest discover -s tests -v
```
