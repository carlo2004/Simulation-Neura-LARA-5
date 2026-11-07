# LARA 5 im Browser

Wähle eine Startszene und prüfe Würfel und Greifer in der Draufsicht. **Beide testen** führt die Läufe nacheinander aus derselben Startszene aus. **Gleicher Prompt für beide Modelle** ist voreingestellt. Schalte die Option aus, um pro Seite einen anderen Auftrag einzugeben.

Der unveränderte Datensatzauftrag erhält eine Zielprüfung. Bei eigenen Aufträgen siehst du das Programm, die Bewegung und den Endzustand. **Referenzprogramm ausführen** führt die Antwort aus dem Datensatz aus. Für die sechs aufgezeichneten Szenen kannst du außerdem das Referenzvideo ohne Runner abspielen.

## Trainingsdaten

Die Workbench lädt die verifizierten Trainingszeilen aus der in [`prompt2robo.lock.json`](../config/prompt2robo.lock.json) festgelegten Revision. Sie zeigt die Nutzereingabe, die Referenzantwort und die Startszene. Ein aktueller Runner kann die gewählte Trainingsszene ausführen. Der Viewer zeigt `data_v4`. Der genaue Trainingsstand eines Checkpoints ergibt sich aus seiner Modellkarte.

## Laufberichte

**Programm und Protokoll** zeigt den Auftrag, die erzeugte Antwort, die Roboterbefehle mit Simulationszeit und die Zustände vor und nach dem Lauf. Fehler beim Antworten, beim Ausführen und bei der Zielprüfung sind separat erkennbar. **Laufbericht speichern** exportiert die Lauf-ID, Prompts, Modellkennung, Messwerte und die Endbilder als JSON. Der Runner schreibt den Bericht anhand derselben ID nach `runs/workbench/`. Bei einem Abbruch können Teile des Berichts fehlen.

## Modellformat

Beide Seiten verwenden den festgelegten HF-Systemprompt und einen Zero-shot-Nutzerturn. Er enthält `Objects: 1 (red), 2 (blue)` und darunter den Auftrag. Das Programm liest Positionen zur Laufzeit mit `robot.get_object_position(id)`. Qwen3 wird im Non-Thinking-Modus angefragt. `def run(robot)` wird über den begrenzten Interpreter auf dem LARA 5 ausgeführt. Textantworten lassen den Arm stehen. [Modellkarte](https://huggingface.co/moritzzzz/Prompt2Robo-Qwen3-4B-v3-full-4b-full) · [Datensatzformat](prompt2robo.md)

Für den Vergleich des Trainingseffekts verwende den Ausgangscheckpoint des Fine-Tunings und dieselbe GGUF-Präzision auf beiden Seiten.

## Runner starten

Für Colab und den Team-Zugang folge der [Schritt-für-Schritt-Anleitung](colab-workbench.md). Der Colab-Starter berechnet beim Start den SHA-256-Fingerabdruck der geladenen GGUF-Dateien und eines gegebenenfalls geladenen LoRA-Adapters. Die Workbench zeigt die Dateinamen direkt an. Unter **Modellkennung** stehen die Prüfsummen und die API-ID.

Wenn bereits OpenAI-kompatible Modellserver laufen, verwende deren Loopback-Adressen in einer Kopie der [Beispielkonfiguration](../config/workbench-models.example.json). `model` ist die vom jeweiligen Server erwartete ID. Ein optionales `api_key_env` verweist auf eine Umgebungsvariable des Runners. Falls nur die API-ID bekannt ist, zeigt die Workbench sie als solche an.

~~~bash
.venv/bin/python -m stacklab workbench --models runs/workbench-models.json
~~~

`STACKLAB_WORKBENCH_TOKEN` muss in der Umgebung gesetzt sein. Die [lokale Workbench](http://127.0.0.1:8787/) erreicht den Runner mit leerem URL-Feld. Vercel ist als Oberfläche über `--origin https://simulation-neura-lara-5.vercel.app` zugelassen. Der Colab-Starter setzt diese Origin im Notebook.

Die Rate in der UI verwendet die nativen Decode-Zähler, soweit der Modellserver sie liefert. Sonst zeigt sie die Ausgabetokens pro Sekunde über die gesamte Anfrage. Die Messbasis steht in der Anzeige und im Export.
