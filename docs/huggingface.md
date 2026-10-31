# Versuchsdaten auf Hugging Face

GitHub bleibt für Quellcode, kleine Konfigurationen, Modell-/Tokenizer-Locks,
Tests und Dokumentation. Das Dataset
[`Carlo0001/neura-lara5-cube-stacking-sim-v1`](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1)
ist das voreingestellte Ziel für Versuchsaufzeichnungen. Hugging Face ergänzt
GitHub an dieser Stelle; es ersetzt das Code-Repository nicht.

| Inhalt | Ablage |
|---|---|
| Code, Tests, Prompt-/Weltkonfigurationen, kleine Versuchsdefinitionen | GitHub |
| Prompts, Antworten, Code, Feedback, Physik, Zeiten und optionale Videos eines Laufs | HF-Dataset, unveränderlicher Snapshot |
| Später fachlich geprüfte SFT-Daten mit eingefrorenen Splits und Herkunft | Separat versionierter Dataset-Export auf HF |
| Spätere LoRA-Adapter, Checkpoints, Trainingskonfiguration und Modellkarte | Eigenes HF-**Modell**-Repository mit Datasetrevision |
| Laufende Dateien und Sicherungen | Lokal/Colab, optional weiterhin Drive |

Es gibt noch keinen implementierten Fine-Tuning-Runner oder geprüften SFT-Export.
Der Upload bewahrt auch Fehler, offene Versuche und `success: null`; er erklärt
sie nicht automatisch zu korrekten Trainingsantworten. Die bisherigen, in Git
vorhandenen Archive bleiben historische Referenzen. Neue Rohdaten werden nicht
mehr in Git oder GitHub Releases exportiert. Bestehende Archive erst nach einer
separat geprüften Übertragung entfernen.

## Anmelden und veröffentlichen

Nach `python bootstrap.py` gehört die Hub-Bibliothek zur Projektumgebung.
Einmal auf dem **Rechner, der hochlädt**, anmelden:

```powershell
.\.venv\Scripts\hf.exe auth login
```

Linux/macOS: `.venv/bin/hf auth login`. Alternativ nutzt die Bibliothek ein lokal
gesetztes `HF_TOKEN` mit Schreibrecht für dieses Dataset. Der Chat-Connector und
die Anmeldung deines Rechners sind unabhängig. Tokenwerte gehören weder in
Git-Konfigurationen noch in Chatnachrichten oder Versuchsprotokolle.

Zuerst genau ansehen, was exportiert würde; dieser Aufruf bleibt offline:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment publish runs/l4-pilot --dry-run
```

Danach denselben Lauf hochladen:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment publish runs/l4-pilot
```

Oder nach einem neuen Pilot automatisch hochladen:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment pilot --server-url http://127.0.0.1:8765 --output runs/l4-pilot --publish
```

`--repository OWNER/DATASET` bei `publish` beziehungsweise `--publish OWNER/DATASET`
beim Runner überschreibt das Ziel aus `config/huggingface.json`. Es wird immer ein
Dataset-Repository angesprochen. Ein fehlendes Dataset wird nicht still erzeugt;
der vorhandene GitHub-Release-Pfad ist entfernt. Bei Uploadfehlern bleiben die
lokalen Versuche erhalten und können später mit `publish` übertragen werden.

## Was genau gespeichert wird

Unter `runs/<Snapshot-SHA256>/` liegen `snapshot.json`, das eingefrorene Manifest,
lesbare Tabellen/Berichte, `episodes.jsonl` und `evidence.zip`. Das ZIP enthält die
unveränderten ausgewählten Rohdateien, Kontextprotokolle und eine aus der Kopie
erzeugte Offline-Sichtung. Die Quelldateien werden beim Export nicht verändert.
Unbeteiligte Dateien, Zugangsdaten-Dateitypen, Modelldateien und temporäre Dateien
werden nicht übernommen; symbolische Links innerhalb der Versuchsdaten werden
abgelehnt. `--dry-run` nennt alle eingeschlossenen Dateien samt Prüfsummen.

Der Snapshot bezeichnet den Inhalt, nicht nur den Plan. Ein später gesicherter
Zwischenstand desselben Plans erhält eine neue ID. Ein identischer Export wird
wiedererkannt. Frühere Snapshots und eine vorhandene Datasetkarte werden nicht
überschrieben; beim ersten Upload wird die vorbereitete Karte nur angelegt, wenn
noch keine `README.md` existiert. Ein Hub-Commit umfasst den gesamten Snapshot.

`hub-receipt.json` im lokalen Lauf nennt Dataset, Snapshot-ID, Hub-Commit und
Direktlink. Diese **beiden** Identitäten für die Seminararbeit festhalten.
Zwischenstände desselben Plans niemals als zusätzliche unabhängige Versuche
zusammenzählen. `episodes.jsonl` ist eine Auswertung mit einer Zeile pro geplantem
Versuch, kein automatisch geeigneter SFT-Trainingssplit.

## Wieder herunterladen

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment fetch SNAPSHOT_SHA256 --revision HUB_COMMIT_SHA --output runs/restored-l4
.\.venv\Scripts\python.exe -m stacklab experiment report runs/restored-l4
```

Die vollständigen IDs aus der Uploadquittung einsetzen. Der Download prüft die
Snapshot-Identität, ZIP-Größe/-Hash, alle Pfade und jede ausgepackte Datei. Das
Ziel muss neu oder leer sein. Berichte lesen erfordert kein Modell und kein
erneutes Ausführen der Physik. Für ein Fortsetzen bleiben die bisherigen strengen
Software-/Hardwareprüfungen des Runners gültig.

Im Chat kann der verbundene **Hugging-Face-Connector** die Datasetkarte, Manifeste,
JSONL-Tabellen und Berichte lesen. Ein Snapshot-Link genügt, um veröffentlichte
Messwerte einzuordnen. Große ZIP-Roharchive müssen dafür nicht in Git liegen.

Primärdokumentation: [Hub-Uploads](https://huggingface.co/docs/huggingface_hub/guides/upload),
[Dateien revisionsgenau laden](https://huggingface.co/docs/huggingface_hub/guides/download),
[Datasetkarten](https://huggingface.co/docs/hub/datasets-cards).
