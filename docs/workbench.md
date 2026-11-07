# LARA 5 im Browser

Mit **A starten** oder **B starten** kannst du ein Modell testen. **Beide starten** führt die Läufe nacheinander aus derselben Startszene aus. **Prompt A → B** übernimmt den Auftrag für einen direkten Vergleich.

Der unveränderte Datensatzauftrag erhält eine Zielprüfung. Bei eigenen Aufträgen siehst du das Programm, die Bewegung und den Endzustand. Unter **Aufnahmen und Berichte** findest du die Referenzvideos und den JSON-Export. Ein Vergleichsbericht enthält Startszene, Prompts, erzeugten Code, Zielprüfung, Generierungszeit und Tokens pro Sekunde.

## Modellformat

Beide Seiten verwenden den festgelegten HF-Systemprompt und einen Zero-shot-Nutzerturn. Er enthält `Objects: 1 (red), 2 (blue)` und darunter den Auftrag. Das Programm liest Positionen zur Laufzeit mit `robot.get_object_position(id)`. Qwen3 wird im Non-Thinking-Modus angefragt. `def run(robot)` wird über den begrenzten Interpreter auf dem LARA 5 ausgeführt. Textantworten lassen den Arm stehen. [Modellkarte](https://huggingface.co/moritzzzz/Prompt2Robo-Qwen3-4B-v3-full-4b-full) · [Datensatzformat](prompt2robo.md)

Für den Vergleich des Trainingseffekts verwende den Ausgangscheckpoint des Fine-Tunings und dieselbe GGUF-Präzision auf beiden Seiten.

## Runner starten

Für Colab und den Team-Zugang folge der [Schritt-für-Schritt-Anleitung](colab-workbench.md). Nach dem Verbinden mit einem aktuellen Modellrunner zeigt die Oberfläche **Runner verbunden · HF**.

Wenn bereits OpenAI-kompatible Modellserver laufen, verwende deren Loopback-Adressen in einer Kopie der [Beispielkonfiguration](../config/workbench-models.example.json). `model` ist die vom jeweiligen Server erwartete ID. Ein optionales `api_key_env` verweist auf eine Umgebungsvariable des Runners.

~~~bash
.venv/bin/python -m stacklab workbench --models runs/workbench-models.json
~~~

`STACKLAB_WORKBENCH_TOKEN` muss in der Umgebung gesetzt sein. Die [lokale Workbench](http://127.0.0.1:8787/) erreicht den Runner mit leerem URL-Feld. Vercel ist als Oberfläche über `--origin https://simulation-neura-lara-5.vercel.app` zugelassen. Der Colab-Starter setzt diese Origin im Notebook.

Die Rate in der UI verwendet die nativen Decode-Zähler, soweit der Modellserver sie liefert. Sonst zeigt sie die Ausgabetokens pro Sekunde über die gesamte Anfrage. Die Messbasis steht in der Anzeige und im Export.
