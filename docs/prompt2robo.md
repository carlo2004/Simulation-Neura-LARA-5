# Prompt2Robo

Alle Replays laufen mit der LARA-5-Geometrie, Kinematik und Kontaktphysik aus Stack Lab. Der Arm verwendet das RoboDK-basierte Modell und den simulierten Parallelgreifer aus der Live-Ansicht. Prompt2Robo liefert die Startszene, das Referenzprogramm und die Zielprüfung. Die Würfelkoordinaten bleiben in Metern erhalten, einschließlich der Höhe in bestehenden Türmen. Der Datensatz verwendet vorne +X, links +Y und oben +Z. [Snapshot auf Hugging Face](https://huggingface.co/datasets/Carlo0001/Prompt2Robo/tree/32360b8d733e9afc46062c3f421598381eb07c91)

## Wiedergabe und Export

Im Repo-Ordner dieselbe Python-Umgebung wie für Demo und Live-Chat verwenden.

```bash
python bootstrap.py
.venv/bin/python -m stacklab prompt2robo list --split train
.venv/bin/python -m stacklab prompt2robo replay --id bse-drop_onto_cube-000 --video --output runs/lara-rot-auf-blau
.venv/bin/python -m stacklab prompt2robo export --replay-report runs/lara-rot-auf-blau/manifest.json --output runs/prompt2robo-sft
```

Unter Windows verwende `.venv\Scripts\python.exe`. Mit `--gui` läuft die Wiedergabe im MuJoCo-Fenster, mit `--video` entsteht eine MP4-Datei. Die CLI lädt die öffentlichen Daten und den Zielchecker ohne Zugangsdaten und prüft ihre SHA-256-Prüfsummen. `--source` akzeptiert eine lokale Kopie desselben Snapshots. `--split` wählt einen Datensplit. `--id` kann für mehrere Zeilen wiederholt werden. Ohne `--id` bestimmt `--limit` die Zahl der Zeilen. Für Prüfserien genügt der Aufruf ohne Video oder Fenster.

Der Bericht hält die gemessene Start- und Endszene, die Prüfergebnisse und die Videonamen fest. Der unterstützte TCP-Bereich beträgt in Stack Lab X 0,20–0,60 m, Y −0,30–0,30 m und Z 0,01–0,45 m. Auch innerhalb dieser Grenzen muss der Arm den gewählten Pfad erreichen können. Abweichungen vom Startzustand, unzulässige Bewegungen und verfehlte Ziele werden getrennt ausgewiesen.

## Schnittstelle für das Modell

Der Zero-shot-Input enthält einen Systemprompt mit den LARA-Grenzen und einen Nutzerturn mit `user_prompt` und `scene`. Die Szene enthält die numerisch sortierten Objekt-IDs, Farben, Mittelpunkte und den Greiferzustand. Die IDs behalten ihren Wert, auch wenn die Nummerierung Lücken hat. `prompt --id abs-pyramid_2_layer-000` gibt die beiden Nachrichten für die Inferenz aus.

Der gemeinsame Antwortumschlag hat zwei Stringfelder. Bei einer Aktion enthält `code` die Funktion `run(robot)`. Bei einer Rückfrage oder Ablehnung bleibt `code` leer und `message` enthält die Antwort. Der Replay-Worker führt bei Aktionszeilen das Referenzprogramm aus. Textzeilen werden mit dem Refusal-Checker geprüft und lösen keine Simulation aus.

`export` schreibt JSONL mit `id` und `messages`. Jede Zeile enthält den Systemprompt, die Aufgabe mit Anfangsszene und genau eine Zielantwort. Die Zielfelder des Checkers bleiben in der Quelldatei. Für SFT wird `train.jsonl` verwendet. `eval.jsonl`, `eval_v2.jsonl`, `eval_v3.jsonl` und `eval_v4.jsonl` bleiben getrennt. Die Inferenz verwendet das gleiche Nachrichtenformat bis zur Nutzerrolle.

Mit `--replay-report` übernimmt der Export nur bestandene Zeilen aus den angegebenen LARA-Berichten. Die Option lässt sich für mehrere Berichte und Splits wiederholen. Der oben gezeigte Einzeltest ergibt eine Trainingszeile. Ohne Berichte exportiert der Befehl die ursprünglich verifizierten Labels und kennzeichnet sie als `source_dataset`.

Für den Modellvergleich dieselben Eval-Splits vor und nach SFT verwenden. Physischer Aufgabenerfolg, angemessene Ablehnungen und Fehler in der räumlichen Zuordnung sollten separat ausgewiesen werden. Der Vergleich des Allgemeinwissens braucht zusätzlich denselben externen Benchmark vor und nach dem Training.

Ein OOD-Test über die Würfelanzahl braucht einen Trainingssplit mit höchstens fünf Würfeln. Der exportierte Originalsplit aus `data_v4` enthält bereits 240 Trainingszeilen mit sechs Würfeln.

## Nachweise

Die MP4s zeigen Programme aus dem Trainingssplit auf dem LARA 5. Der Zielchecker bewertet die gemessenen Zustände anhand der Sollpositionen oder räumlichen Bedingungen des Datensatzes. Die Ergebnisse zeigen, welche Referenzprogramme auf dieser Simulation funktionieren. [Wiedergaben und Prüfergebnisse](../examples/prompt2robo-replays/)
