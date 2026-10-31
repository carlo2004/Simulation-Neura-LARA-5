# Historische Archivmigration

**Abgeschlossen:** Alle 251 kanonischen Dateien und 491 ursprünglichen Pfade sind
auf HF erhalten. Der Upload-Nachweis und alle Hub-Objekthashes wurden vor der
Git-Bereinigung unabhängig gegen den versiegelten Plan geprüft.
[Archivort, feste Revisionen und Prüfnachweis](../experiments/archive-location.json).
Die folgenden Schritte bleiben als Wiederholungs- und Prüfweg dokumentiert.

Das [Migrationsnotebook](../notebooks/migrate_evidence.ipynb) läuft auf einer
gewöhnlichen **Colab-CPU**. Es startet weder eine GPU noch Hugging-Face-Compute.
Die Verwendung des Skripts ist unabhängig davon, ob PR #4 schon in `main` liegt.

## Die festgelegte Auswahl

Der [versiegelte Plan](../config/evidence-migration.json) bezieht sich auf
`carlo2004/Simulation-Neura-LARA-5@40790e3addb62b5d9e1a9544b67bc4145a3e2f1c`.
Er enthält ausschließlich die bereits versionierten Archive unter
`experiments/archive/` und `examples/experiments/archive/`.

| Bestandteil | Umfang |
|---|---:|
| Ursprüngliche Dateipfade | 491 |
| Kanonische Dateien auf HF | 251 |
| Bytegleiche doppelte Pfade, explizit zugeordnet | 240 |
| Tatsächlich zu übertragende Dateibytes | 33.596.782 |

Die Auswahl umfasst Anfragen, Antworten, erzeugten Code, Messungen,
Fehlerprotokolle, frühere Rohdaten-ZIPs und das A100-Vergleichs-GIF. Das sind
Entwicklungsaufzeichnungen, kein bereits geprüfter Trainingsdatensatz. Es wurden
keine Fine-Tuning-Checkpoints in dieser Auswahl gefunden. Code, aktuelle Prompts,
Konfigurationen, Tests und Bedienungsdokumentation bleiben auf GitHub.

Gleiche Dateien aus dem zusätzlichen `examples/`-Archiv werden nur einmal
gespeichert. `aliases` im Plan hält jeden ursprünglichen Pfad und seine kanonische
Entsprechung fest. Es geht kein ursprünglicher Dateipfad verloren.

## Zwei Zellen ausführen

1. Das Notebook mit einer CPU-Laufzeit öffnen. Die erste Zelle lädt nur den
   festgelegten Programm-/Planstand und das ursprüngliche GitHub-Archiv.
   Alle 491 Quellpfade werden auf SHA-256 und ihre ursprünglichen Git-Blob-Hashes
   geprüft. Es wird noch nichts hochgeladen.
2. Die zweite Zelle ausführen. Sie nutzt ein vorhandenes Colab-Secret `HF_TOKEN`
   oder fragt den Token über ein verborgenes Eingabefeld ab. Der Token wird dem
   Uploadprozess über dessen Umgebung gegeben, nicht in Befehlsargumenten,
   Notebookcode oder Ergebnisdateien gespeichert.

Falls noch kein passender Token vorhanden ist: Unter
[Hugging Face → Access Tokens](https://huggingface.co/settings/tokens) einen
**Fine-grained** Token mit Lese-/Schreibzugriff ausschließlich auf
`Carlo0001/neura-lara5-cube-stacking-sim-v1` anlegen. Den Wert nur in Colab
eingeben. Die Anmeldung des Chat-Connectors ist davon unabhängig.

Die Daten gehen ausschließlich in das bereits angelegte Dataset
`Carlo0001/neura-lara5-cube-stacking-sim-v1`, unter
`legacy/github-40790e3addb6-7ae3ed9e3645/`. Es werden weder ein anderes Repository
noch neue kostenpflichtige Compute-Ressourcen angelegt.

## Was als erfolgreich gilt

Ein atomarer Hub-Commit enthält die ausgewählten Dateien und `migration.json`.
Danach lädt das Skript **jede kanonische Datei erneut** aus genau diesem Commit
herunter und prüft Größe, SHA-256 und Git-Blob-Hash. Erst nach vollständigem Erfolg
wird eine `verification.json` auf HF angelegt und eine lokale
`migration-receipt.json` mit den festen Hub-Revisionen und dem Direktlink erzeugt.
Eine vorhandene Datasetkarte wird nicht überschrieben.

Bei Abbruch bleiben GitHub und lokale Quelldateien erhalten. Ein identischer
erneuter Aufruf erkennt vorhandene Daten, prüft sie erneut und überschreibt keine
abweichenden Migrationsdateien. Nach einem fehlgeschlagenen Quelldownload einen
neuen leeren Ausgabeordner wählen.

**Dieses Skript löscht nichts auf GitHub.** Die alten Rohdatenpfade wurden nach erfolgreicher Prüfung aus der aktuellen
Git-Projektstruktur entfernt; die Dokumentationslinks zeigen auf die feste
HF-Datenrevision. Dafür ist keine Änderung der Git-Historie
erforderlich.

## Lokal oder erneut prüfen

```bash
python tools/migrate_archives.py --plan config/evidence-migration.json --output runs/legacy-transfer
# Nach normaler HF-Anmeldung bzw. lokal gesetztem HF_TOKEN:
python tools/migrate_archives.py --plan config/evidence-migration.json --output runs/legacy-transfer --card config/evidence-dataset-card.md --upload
# Nur lesen und nachprüfen, kein Upload:
python tools/migrate_archives.py --plan config/evidence-migration.json --output runs/legacy-check --verify-revision HUB_COMMIT_SHA
```

Das Skript benötigt für Vorbereitung nur die Python-Standardbibliothek und für
Hub-Zugriff `huggingface_hub`. Simulation, Gewichte und CUDA werden nicht geladen.
Der neue [Snapshot-Export in PR #4](https://github.com/carlo2004/Simulation-Neura-LARA-5/pull/4)
ist für neue Experimente vorgesehen; dieser unabhängig nutzbare Migrationsplan
bewahrt gezielt die älteren Datenformate.
