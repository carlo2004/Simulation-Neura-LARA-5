# Prompt2Robo

Der Modus verwendet den Simulator, die Referenzprogramme und den Checker aus dem festgelegten `data_v4`-Snapshot. Der Simulator hat einen generischen, fest montierten Arm mit LARA-ähnlichem Arbeitsraum. Das Koordinatensystem ist vorne +X, links +Y und oben +Z. Versionen und SHA-256-Prüfsummen stehen im Lockfile. [Snapshot auf Hugging Face](https://huggingface.co/datasets/Carlo0001/Prompt2Robo/tree/32360b8d733e9afc46062c3f421598381eb07c91)

## Wiedergabe und Export

Im Repo-Ordner eine separate Python-Umgebung für den Simulator aus dem Dataset einrichten. Die Befehle funktionieren auch in einem Colab-Terminal.

```bash
python -m venv .venv-prompt2robo
.venv-prompt2robo/bin/python -m pip install -r requirements-prompt2robo.txt
.venv-prompt2robo/bin/python -m stacklab prompt2robo list --split train
.venv-prompt2robo/bin/python -m stacklab prompt2robo replay --id abs-pyramid_2_layer-000 --video --output runs/prompt2robo-pyramid
.venv-prompt2robo/bin/python -m stacklab prompt2robo export --output runs/prompt2robo-sft
```

Unter Windows verwende `.venv-prompt2robo\Scripts\python.exe`. Mit `--gui` läuft die Wiedergabe im MuJoCo-Fenster, mit `--video` entsteht eine MP4-Datei. Die CLI lädt die öffentlichen Daten ohne Zugangsdaten. `--source` akzeptiert eine lokale Kopie desselben Snapshots. `--split` wählt einen Datensplit, `--id` kann für mehrere Zeilen wiederholt werden. Ein Bericht hält pro Zeile Checker-Ergebnis, Gründe, Endzustand und Videonamen fest.

## Schnittstelle für das Modell

Der Zero-shot-Input enthält einen Systemprompt und einen Nutzerturn mit `user_prompt` und `scene`. Die Szene enthält die numerisch sortierten Objekt-IDs, Farben, Mittelpunkte und den Greiferzustand. Die IDs behalten ihren Wert, auch wenn die Nummerierung Lücken hat. `prompt --id abs-pyramid_2_layer-000` gibt die beiden Nachrichten für die Inferenz aus.

Der gemeinsame Antwortumschlag hat zwei Stringfelder. Bei einer Aktion enthält `code` die Funktion `run(robot)`. Bei einer Rückfrage oder Ablehnung bleibt `code` leer und `message` enthält die Antwort. Der Replay-Worker führt bei Aktionszeilen das Referenzprogramm aus. Textzeilen werden mit dem Refusal-Checker geprüft und lösen keine Simulation aus.

`export` schreibt JSONL mit `id` und `messages`. Jede Zeile enthält den Systemprompt, die Aufgabe mit Anfangsszene und genau eine Zielantwort. Die Zielfelder des Checkers bleiben in der Quelldatei. Für SFT wird `train.jsonl` verwendet. `eval.jsonl`, `eval_v2.jsonl`, `eval_v3.jsonl` und `eval_v4.jsonl` bleiben getrennt. Die Inferenz verwendet das gleiche Nachrichtenformat bis zur Nutzerrolle.

Für den Modellvergleich dieselben Eval-Splits vor und nach SFT verwenden. Physischer Aufgabenerfolg, angemessene Ablehnungen und Fehler in der räumlichen Zuordnung sollten separat ausgewiesen werden. Der Vergleich des Allgemeinwissens braucht zusätzlich denselben externen Benchmark vor und nach dem Training.

Ein OOD-Test über die Würfelanzahl braucht einen Trainingssplit mit höchstens fünf Würfeln. Der exportierte Originalsplit aus `data_v4` enthält bereits 240 Trainingszeilen mit sechs Würfeln.

## Nachweise

Die MP4s zeigen Referenzprogramme aus dem Trainingssplit, die vom ursprünglichen Checker bewertet wurden. Die Ergebnisse stammen aus dem Simulatorlauf unter MuJoCo 3.17.0 und NumPy 2.4.6. [Wiedergaben und Prüfergebnisse](../examples/prompt2robo-replays/)
