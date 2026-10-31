# Testlauf 2: 32 Stapelversuche je Modell auf A100

[Notebook direkt in Colab öffnen](https://colab.research.google.com/github/carlo2004/Simulation-Neura-LARA-5/blob/main/notebooks/colab_stack_study_v2.ipynb).

Der Lauf erzeugt Daten für die anschließende manuelle Modellauswahl: **sechs Modelle × 32 Startlagen × ein Generierungsseed = 192 geplante Modell-Episoden**. Die einzige Aufgabe lautet „Staple den roten Würfel auf den blauen Würfel.“ Es gibt keine Bewegungsaufgabe, keine zusätzlichen gescorten Wiederholungen und keinen automatischen HF-/GitHub-Upload.

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
2. Die voreingestellte Commit-Revision und das Protokoll beibehalten. `MAX_HOURS` begrenzt die laufende Erhebung zwischen Episoden; voreingestellt sind sechs Stunden.
3. Zellen der Reihe nach ausführen und Drive verbinden. Der Paketstand kommt aus `requirements-study.txt`. Ein neues Notebook-Python außerhalb 3.12/3.13 bekommt eine eigene Python-3.12-Umgebung.
4. Nur die sechs gewählten Modelle werden installiert. Vor der Erhebung lädt der Server jedes Modell und prüft die echte vollständige GPU-Auslagerung. Diese Infrastrukturchecks steuern keinen Roboter und zählen nicht als weitere Simulationen.
5. Die Sammelzelle laufen lassen. Neue Episode, tatsächlicher Programmblock, Physikfeedback und native Geschwindigkeit bleiben im Protokoll erkennbar.

Das Notebook führt Modell und Simulation auf Colab aus. SSH und ein lokales Simulationsfenster werden für diesen Lauf nicht benötigt. Modelle, Inferenz-Cache und Arbeitsdateien bleiben auf der VM. Für die Daten gibt es pro abgeschlossener Episode ein eigenes unveränderliches ZIP-Checkpoint in Drive; nicht nach jeder Episode eine neue Kopie des gesamten Datensatzes.

Nach Abschluss, geplantem Zeitstopp oder einem abgefangenen Fehler versucht die Sammelzelle einen lokalen, checksummierten Export. Erst wenn dessen Drive-Kopie geprüft wurde, gibt `AUTO_RELEASE_GPU=True` die Colab-VM frei. Bei einem fehlgeschlagenen Export bleibt die VM offen, damit lokale Daten gerettet werden können. Die Freigabe kann bei einem harten Sitzungsabbruch nicht garantiert werden; vorhandene fertige Einzelcheckpoints bleiben in Drive.

Die erste Runtime-Einrichtung kann bei älterer GLIBC einen CUDA-Quellbuild benötigen. Die Laufzeit des gesamten Tests hängt von den tatsächlich erzeugten Antworten und der Anzahl benötigter Blöcke ab. Es ist keine feste A100-Geschwindigkeit oder feste CU-Abrechnung angenommen. Die Erhebung kann nach dem Zeitstopp mit demselben Ordner fortgesetzt werden; der erste sichtbare Zeitwert stammt aus der tatsächlichen Ausführung.

## Unterbrechen und fortsetzen

Der Drive-Ordner lautet standardmäßig:

```text
MyDrive/LARA-Stack-Lab/stack-study-v2-32/
  study.json
  feasibility.json
  sessions/
  batches/
    batch-…/
      context.zip
      starts/episode-….json
      episode-….zip
  exports/
    stack-study-v2-export-…/
```

Nach einer neuen Colab-Laufzeit das gleiche gepinnte Notebook mit **demselben Drive-Ordner** ausführen. Einzelarchive werden auf Inhalt und Prüfsummen geprüft. Die ursprünglichen Batch-Manifeste behalten ihre damalige GPU-UUID, Treiber und Software. Noch ungestartete Slots bekommen neue Batch-Manifeste für die aktuelle A100-Sitzung. So wird ein neues Gerät nicht rückwirkend in einen alten Versuchsplan geschrieben.

Vor dem Start jeder Simulation wird eine Startmarkierung gesichert. Ein bereits begonnener Versuch wird nicht erneut gestartet. Bei einem harten Abbruch können die noch nicht gesicherten Ausgaben der zuletzt laufenden Episode fehlen; ihre Startmarkierung bleibt als unvollständiger Versuch erhalten. Alle vorangehenden Checkpoints bleiben erhalten. Ein abgefangener Abbruch versucht auch Teilprotokolle zu sichern. Startfehler vor den gewerteten Versuchen und Infrastrukturfehler werden sichtbar erfasst. Sie werden nicht als Roboter-Misserfolg ausgegeben.

**192 ist die Zahl der geplanten Versuchseinheiten.** Falls technische Ausfälle oder Abbrüche auftreten, bleiben dafür Einträge mit unbekanntem physischem Ergebnis erhalten. Der Export behauptet dann nicht, alle 192 seien auswertbar. Modell-/Token-/aktive Generierungsbudgetfehler zählen als Misserfolg; reine Transportfehler bleiben davon getrennt. Weitere technische Wiederholungen würden einen separat benannten neuen Versuch benötigen.

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

## Später selbst lokal auf HF hochladen

Den neuesten **gesamten Exportordner** aus Drive lokal herunterladen. Der Token wird nur in deinem lokalen Terminal verwendet. Beispielsweise mit der vorhandenen HF-CLI:

```bash
hf auth login
hf upload DEINNAME/DEINDATASET PFAD_ZUM_EXPORT experiments/stack-v2/DEINE_SNAPSHOT_ID --repo-type dataset
```

`DEINE_SNAPSHOT_ID` stammt aus `snapshot.json`; dadurch bleiben verschiedene Exporte auseinander. Unter Windows ist die Projekt-CLI `.\.venv\Scripts\hf.exe`, unter Linux/macOS `.venv/bin/hf`. Das Notebook und die Vorbereitung führen diesen Upload nicht aus. Für eine leere Zielablage kann die HF-CLI das Dataset anlegen; Zugriffsrechte und Sichtbarkeit wählst du selbst.

Die vorbereitete Sammlung ist ein eigener exportierter Studiendatensatz. Der vorhandene Einzelplan-Befehl `experiment publish` erwartet einen normalen Plan und ist nicht der Upload-Einstieg für diese gesamte Sammlung.

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

Geprüft werden Szenenvielfalt, Paarung und exakte Fallzahlen, vollständige physische Kontrollen, A100-/Offload-Anforderungen, Kontextwechsel, Stoppen/Fortsetzen über verschiedene GPU-Identitäten, unveränderliche Checkpoints, Korruptionserkennung und ein Export ohne HF-Zugriff. Software-Fixtures sind als solche gekennzeichnet. Ein echter neuer A100-Modelllauf wird erst durch deine Ausführung gestartet; es sind keine solchen Ergebnisse vorab eingetragen.
