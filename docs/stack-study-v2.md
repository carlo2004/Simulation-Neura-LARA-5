# Testlauf 2: 32 Stapelversuche je Modell auf A100

[Notebook direkt in Colab öffnen](https://colab.research.google.com/github/carlo2004/Simulation-Neura-LARA-5/blob/main/notebooks/colab_stack_study_v2.ipynb).

Der Lauf erzeugt Daten für die anschließende manuelle Modellauswahl: **sechs Modelle × 32 Startlagen × ein Generierungsseed = 192 geplante Modell-Episoden**. Die einzige Aufgabe lautet „Staple den roten Würfel auf den blauen Würfel.“ Das Notebook sichert jeden Versuch automatisch nach Drive und HF. Die sechs Stunden sind eine Obergrenze; die Sicherung beginnt schon vor dem ersten Versuch. Es gibt keine Bewegungsaufgabe und keine zusätzlichen gescorten Wiederholungen.

## Was verglichen wird

| Alias | Modell | Rolle im Vergleich |
|---|---|---|
| `qwen4b` | Qwen3.5-4B | Kleinere Baseline |
| `qwen9b` | Qwen3.5-9B | Kandidat um 8B |
| `ministral8b` | Ministral 3 8B Reasoning 2512 | Kandidat um 8B |
| `nemotron8b` | NVIDIA Nemotron 3.5 Bolt E4B | Rund 8B Gesamtparameter; BF16-Ausgangspunkt für späteres Training im Katalog |
| `granite8b` | IBM Granite 4.2 8B | Kandidat um 8B |
| `lfm2.6b` | LiquidAI LFM2.5-2.6B | Kleine effiziente Baseline mit dokumentierten LoRA-Rezepten |

**Dory4B ist für diesen Lauf ausgeschlossen.** Seine experimentelle, rekurrente normalized-GPT-Architektur und der Sonderpfad der Runtime sind in unserem Projekt noch nicht als A100-LoRA-/QLoRA-Trainingsweg validiert. Das ist eine praktische Vorauswahl für das Seminar, keine Behauptung, Dory sei grundsätzlich untrainierbar: Die Herstellerkarte nennt selbst SFT und RL. Der Hersteller beschreibt für Dory eine Schleife geteilter Schichten und einen eigenen Inferenzpfad; bei LFM sind dagegen konkrete TRL-/Unsloth-LoRA-Anleitungen veröffentlicht. [Dory-Herstellerkarte](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16) · [LFM-Herstellerkarte und Training](https://huggingface.co/LiquidAI/LFM2.5-2.6B#-fine-tuning).

Fine-Tuning verwendet später die Original-/BF16-Trainingsmodelle, nicht die GGUF-Inferenzdateien. IDs und Revisionen stehen bereits in den Modellmetadaten. Hier wird noch kein Modell trainiert. Ein gutes Basisergebnis allein beweist keinen späteren Fine-Tuning-Gewinn.

## Versuchsdesign

| Größe | Festlegung |
|---|---|
| Versuchsaufgabe | Ausschließlich Rot auf Blau, identischer deutscher Auftrag |
| Unterschiedliche Startlagen | 32; alle Modelle erhalten exakt dieselben |
| Abdeckung | Vier relative Richtungen × zwei Abstände × vier Lagen je Gruppe |
| Abstände | Nah: 10–14 cm; fern: 20–26 cm zwischen den Würfelzentren |
| Richtung | Vektor von Rot nach Blau; Ost = +X, Nord = +Y |
| Generierungsseeds | Ein eigener Seed je Startlage, zwischen Modellen gepaart; Rundenoffset bleibt dokumentiert |
| Simulationsstart | Neue Szene und neue Agentenhistorie für jede Episode |
| Objekte | Genau zwei gleich große, achsenparallele 40-mm-Würfel; gleiche physikalische Parameter |
| Modellkontext | 16.384 Tokens für alle Modelle, keine Musterlösung/Few-Shot-Beispiele |
| Programmblöcke | Bis zu vier mit tatsächlichem Ausführungsfeedback innerhalb derselben Episode |
| Generierung | Thinking an, maximal 3.072 Ausgabetokens insgesamt je Block; darin angefragtes Thinking-Limit von 1.024 Tokens |
| Zeitbudgets | 240 s Generierung und 180 s Ausführung je Block; Transport hat kurze Rückgabe-Kulanz |
| Gewichte | Für alle sechs Modelle die gesperrten Q4_K_M-Dateien mit SHA-256-Prüfung |
| GPU | Genau eine A100; tatsächlich alle Modellschichten ausgelagert, kein CPU-Fallback |
| Server | Zwei Threads, Modell bleibt je Gruppe geladen, Promptcache deaktiviert |
| Aufzeichnung | Vollständige Eingaben/Antworten, Code, Feedback, Physik, Token-/Zeitdaten; Bewegung mit 10 Hz |
| Direkte Videos | Ausgeschaltet; später aus den tatsächlich aufgezeichneten Posen erzeugbar |
| Wiederholungen | Keine automatischen Wiederholungen – auch technische oder abgebrochene Versuche bleiben erhalten |
| Datensplit | `model_selection`, kein unberührtes Abschlusstestset |

Die Modellgruppen laufen über vier Szenenblöcke. Gespiegelte Reihenfolgen gleichen frühe und späte Modellpositionen aus; die mittlere Position ist für jedes Modell gleich. Damit läuft nicht jedes Modell immer an derselben Stelle eines mehrstündigen Tests. Alle Szenen und Seeds sind vor der ersten Modellantwort festgelegt.

Die 32 Szenen wurden bei ihrer Erstellung mit einem separaten handgeschriebenen Kontrollprogramm und anschließendem unabhängigem Kontakt-/Stabilitätstest physisch ausgeführt und bestanden. Prüfsummen, Geometrie und Paketstände werden in Colab abgeglichen. Diese Kontrollen werden dort **nicht nochmals simuliert** und gehen nicht als Modellleistung ein. Kontrollcode oder Musterantworten werden den Modellen nicht gegeben.

Es werden konfigurierte Modellsysteme verglichen. Hersteller-Samplingprofile, native Tokenizer, Ministrals Systempräfix und LFMs bestehende JSON-Antworthülle bleiben dokumentierte Unterschiede. Die Bedingungen sind damit nachvollziehbar, aber keine reine Ablation ausschließlich der Gewichte. Tokens/s verschiedener Tokenizer sind ebenfalls keine direkte gemeinsame Textmenge.

## In Colab starten

1. Das Notebook öffnen und unter **Laufzeit → Laufzeittyp ändern → A100** auswählen.
2. Die voreingestellte Commit-Revision und das Protokoll beibehalten. `MAX_HOURS=6` begrenzt die Sammlung zwischen Episoden. Du musst nicht sechs Stunden am Stück behalten, damit Daten gesichert werden.
3. Links über das Schlüsselsymbol das Colab-Secret **`HF_TOKEN`** hinzufügen und den Notebook-Zugriff aktivieren. Der Token braucht Schreibzugriff auf `HF_REPOSITORY`. Alternativ fragt das Notebook ihn verdeckt ab. Standardziel ist das bestehende Projekt-Dataset `Carlo0001/neura-lara5-cube-stacking-sim-v1`. Ein bestehendes Dataset behält seine Sichtbarkeit; ein fehlendes wird privat erstellt.
4. Zellen der Reihe nach ausführen und Drive verbinden. Vor Modell-Downloads erfolgen automatischer HF-Login und ein echter Schreib-/Lese-/Löschtest mit einer kleinen Testdatei. Bei fehlendem Schreibzugriff stoppt dieser Schritt. Danach werden HF-Checkpoints wiederhergestellt und der Plan gesichert. Pakete kommen aus `requirements-study.txt`; ein Notebook-Python außerhalb 3.12/3.13 bekommt eine eigene Python-3.12-Umgebung.
5. Nur die sechs gewählten Modelle werden installiert. Vor der Erhebung lädt der Server jedes Modell und prüft die echte vollständige GPU-Auslagerung. Diese Infrastrukturchecks steuern keinen Roboter und zählen nicht als weitere Simulationen.
6. Die Sammelzelle laufen lassen. Neue Episode, tatsächlicher Programmblock, Physikfeedback, native Geschwindigkeit und bestätigte HF-Backups bleiben im Protokoll erkennbar.

Modell und Simulation laufen auf Colab. SSH und ein lokales Simulationsfenster werden für diese Sammlung nicht benötigt. Für die Daten gibt es pro abgeschlossener Episode ein eigenes unveränderliches ZIP-Checkpoint auf Drive und HF. Bereits bestätigte Dateien werden übersprungen; es wird nicht nach jeder Episode der gesamte wachsende Datensatz erneut hochgeladen. Der Token liegt nur im Colab-Prozess/der VM-Anmeldung und wird nicht als Aufzeichnung, Notebook-Ausgabe oder Git-Credential gespeichert.

Nach Abschluss, geplantem Zeitstopp oder einem abgefangenen Fehler erzeugt die Sammelzelle zusätzlich einen gesamten, checksummierten Export. Erst wenn die Drive-Kopie geprüft und der HF-Export bestätigt wurde, gibt `AUTO_RELEASE_GPU=True` die VM frei. Bei fehlgeschlagenem Export bleibt sie offen, damit Daten gerettet werden können. Bei einem harten Sitzungsabbruch kann die Zelle nicht mehr exportieren; zuvor bestätigte Einzelcheckpoints liegen dann bereits außerhalb der VM auf Drive und HF.

Die erste Einrichtung kann bei älterer GLIBC einen CUDA-Quellbuild benötigen. Die Dauer hängt von tatsächlich erzeugten Antworten und benötigten Blöcken ab; feste A100-Geschwindigkeit oder CU-Abrechnung sind nicht angenommen.

## Unterbrechen und fortsetzen

Der neue Drive-Ordner heißt standardmäßig `MyDrive/LARA-Stack-Lab/stack-study-v2-32-hf/`. Er enthält `study.json`, `feasibility.json`, `sessions/`, `batches/<batch>/context.zip`, `batches/<batch>/starts/`, `batches/<batch>/episode-….zip` und `exports/`.

Nach einer neuen Colab-Laufzeit das gleiche gepinnte Notebook mit **demselben Drive-Ordner, `HF_REPOSITORY` und `HF_PREFIX`** ausführen. Login und Schreibtest laufen erneut. Fehlende Checkpoints werden anhand eines festen HF-Commits heruntergeladen und vor dem Wiederherstellen per SHA-256 geprüft. Abweichende unveränderliche Versuchsdaten werden nicht überschrieben. Unterschiedliche Sitzungs-Metadaten bleiben bei Bedarf als beide Varianten erhalten.

Der neue Ordner trennt diese Version vom älteren Notebook ohne HF-Sicherung. Einen bereits mit der alten Version begonnenen Lauf mit seinem damaligen gepinnten Notebook weiterführen; Aufzeichnungen unterschiedlicher Implementierungsstände werden nicht still vermischt.

Die ursprünglichen Batch-Manifeste behalten ihre damalige GPU-UUID, Treiber und Software. Noch ungestartete Slots bekommen neue Batch-Manifeste für die aktuelle A100-Sitzung. Ein neues Gerät wird nicht rückwirkend in einen alten Plan geschrieben.

**Vor jeder Simulation** wird ihre Startmarkierung auf Drive gespeichert und der HF-Commit bestätigt. **Nach jeder Episode** wird ihr vollständiges Archiv bestätigt, bevor die nächste Simulation startet. Bei einem harten Abbruch können die noch nicht gesicherten Ausgaben der laufenden Episode fehlen; die Startmarkierung bleibt als unvollständiger Versuch erhalten und verhindert eine versehentliche Wiederholung. Vorangehende bestätigte Checkpoints bleiben erhalten. Ein abgefangener Abbruch versucht auch Teilprotokolle zu sichern. Infrastrukturfehler werden sichtbar erfasst und nicht als Roboter-Misserfolg ausgegeben.

HF-Übertragungen haben drei begrenzte Versuche. Danach stoppt die Sammlung; lokale/Drive-Daten bleiben erhalten. Das wiederholt nur die Übertragung, keinen Modellversuch. Datei und `checkpoint-index.json` werden gemeinsam in einem HF-Commit veröffentlicht. Ein verlorenes HTTP-Acknowledgement verursacht so keine doppelte Modell-Ausführung. Nach Behebung eines HF-Ausfalls dieselben Einstellungen verwenden. Immer nur eine aktive Colab-Sammlung pro Studienordner.

**192 ist die Zahl der geplanten Versuchseinheiten.** Technische Ausfälle und Abbrüche bleiben mit unbekanntem physischem Ergebnis erhalten; der Export behauptet dann nicht, alle 192 seien auswertbar. Modell-/Token-/aktive Generierungsbudgetfehler zählen als Misserfolg; reine Transportfehler bleiben getrennt. Weitere technische Wiederholungen benötigen einen separat benannten neuen Versuch.

## Datensatz für die manuelle Auswertung

Der Exportordner enthält:

| Datei | Inhalt |
|---|---|
| `README.md` | Aufgabe, Einheit der Untersuchung und Hinweise zu den Daten |
| `study.json` | Vollständiger eingefrorener Plan, Modelle/Revisionen, 32 Szenen, Seeds, Budgets und Quellenhashes |
| `trials.csv`, `trials.jsonl` | Exakt 192 Zeilen, einschließlich ungestarteter/technischer/teilweiser Versuche |
| `attempts.jsonl` | Jeder tatsächliche Versuch mit ursprünglicher Plan-/Episodenidentität und relativem Pfad |
| `collection-status.json` | Vollständigkeit und technische Zählwerte; keine Gesamt-Modellrangliste |
| `snapshot.json` | Inhalt und SHA-256-Prüfsummen des Snapshots und Archivs |
| `evidence.zip` | Alle Anfragen, vollständigen Antworten mit geliefertem Reasoning, Code, Rückmeldungen, Aktionen, Physikzustände, Bewegung und Sitzungs-/GPU-Protokolle |

Bei den Zeilen stehen unter anderem Modell, Layout-ID, Richtung/Abstand, Szenen-/Generierungsseed, physischer Erfolg, Programmblockzahl, erste erfolgreiche Runde, erste Fehlerrückmeldung und native Token-/Zeitmessungen. Technische Zeilen behalten ihre vorhandenen Teilmessungen und den Link zur eigenen Rohaufzeichnung. Nicht vorhandene Messwerte werden nicht erfunden. Der gelieferte Denktext ist Modellausgabe, keine verifizierte Erklärung des Lösungsprozesses und kein automatisch genehmigtes Trainingsziel.

Die vollständigen Daten eines Versuchs liegen im Archiv unter `batches/<batch>/episode-…/`. Pro Programmblock bleiben `request.json`, `response.json`, `generation.json`, `generated.py` und `feedback.json` erhalten. Szene, Anfangs-/Endphysik und 10-Hz-Bewegung erlauben eine spätere Prüfung. Die schlanke Aufzeichnung lässt lediglich doppelte Token-/Transportstreams und direktes Video-Encoding weg.

Nach Unterbrechungen können frühere Batch-Pläne ungestartete Slots enthalten. **Nicht deren geplante Fallzahlen addieren:** `trials.csv` ist das verbindliche Inventar der 192 Untersuchungsfälle. `trial_id` ist innerhalb des eingefrorenen Studienplans der gemeinsame Schlüssel. Bei Zusammenführungen verschiedener Studien zusätzlich `protocol_sha256` verwenden.

Die 20 Stabilitätsproben über zwei Simulationssekunden und mehrere Programmblöcke gehören zur selben Episode. Sie erhöhen die Stichprobe nicht. Mit 32 gepaarten Startlagen je Modell ist dies ein erster überschaubarer Vergleich. Kleine Erfolgsunterschiede erlauben noch keine sichere allgemeine Bestenliste; neue Bestätigungs- und spätere Fine-Tuning-Tests brauchen unbenutzte Startlagen. Erfolgscode und Diagnose bleiben getrennt von einer späteren manuellen Fehlerursachen-Einordnung.

## Automatische HF-Ablage

Standardpfad im Dataset ist **`backups/stack-study-v2-32-hf/`**:

| Pfad | Inhalt |
|---|---|
| `checkpoint-index.json` | Prüfsummen und Größen aller bestätigten Checkpoint-Dateien |
| `study.json`, `feasibility.json` | Eingefrorener Plan und Machbarkeitsprüfung |
| `sessions/` | Sitzungsdaten und Erfolgsbelege des HF-Schreibtests |
| `batches/<batch>/context.zip` | Ursprünglicher Plan und Modell-/GPU-Metadaten |
| `batches/<batch>/starts/` | Vor der Ausführung bestätigte Startmarkierungen |
| `batches/<batch>/episode-….zip` | Unveränderliche Einzelversuche mit vollständigen Rohdaten |
| `exports/<snapshot_id>/` | Gesamtexport mit `trials.csv`, `snapshot.json` und `evidence.zip` |

Die Testdatei wird nach dem Schreiben/Lesen aus dem aktuellen HF-Baum gelöscht; ihre kleinen Test-Commits bleiben in der Repository-Historie. Der Schreibtest führt keine Simulation aus. Es werden ausschließlich festgelegte Checkpoint-Dateien bzw. der kuratierte Export hochgeladen: keine Gewichte, Anmeldedateien oder allgemeinen VM-Verzeichnisse.

Nach hartem Abbruch muss noch kein Gesamtexport existieren. Er lässt sich aus den Einzelcheckpoints wieder erzeugen. Wiederherstellen und lokaler Export benötigen keine neue Modellantwort. Ein zusätzlicher manueller Upload ist für dieses Notebook nicht erforderlich. Der bisherige Einzelplan-Befehl `experiment publish` bleibt vom Studien-Backup getrennt.

## Ohne Notebook / technische Prüfung

Auf dem Sammelrechner mit eingerichteter Python-Umgebung und A100:

```bash
.venv/bin/python -m stacklab experiment stack-study prepare --output runs/stack-v2 --checkpoint-dir /PFAD/ZU/DRIVE/stack-v2
.venv/bin/python -m stacklab serve --model qwen4b --device cuda --threads 2 --context-tokens 16384 --allow-model-switch --install-missing
```

In einem zweiten Terminal auf derselben Maschine:

```bash
.venv/bin/python -m stacklab experiment stack-study run runs/stack-v2 --server-url http://127.0.0.1:8765 --checkpoint-dir /PFAD/ZU/DRIVE/stack-v2 --max-hours 6
.venv/bin/python -m stacklab experiment stack-study export runs/stack-v2 --output output/stack-v2-export
```

Für ausgewählte Episoden lassen sich später lokal mit `experiment replay` Videos aus den aufgezeichneten Posen rendern. Dabei werden weder das Modell noch die Physikbewertung erneut ausgeführt.

Geprüft werden Szenenvielfalt, Paarung und exakte Fallzahlen, physische Kontrollen, A100-/Offload-Anforderungen, Kontextwechsel, Stoppen/Fortsetzen, unveränderliche Checkpoints und Korruptionserkennung. HF-Tests prüfen Schreibtest/Cleanup, fehlende Berechtigungen, inkrementelle Uploads, verlorene Commit-Antworten, Wiederherstellen nach Verlust von VM und Drive und Stoppen vor ungesicherter Simulation. API-/Modell-Fixtures sind als solche gekennzeichnet. Der echte Schreibtest mit deinem Token und der neue A100-Modelllauf starten erst durch deine Notebook-Ausführung; dafür sind keine Ergebnisse vorab eingetragen.
