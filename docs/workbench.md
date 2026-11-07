# Browser-Workbench für Prompt2Robo

Im Browser wählen alle dieselbe Aufgabe und vergleichen zwei Modelle nebeneinander. Der Runner führt jede Antwort in einer frischen Szene mit dem LARA 5 aus. Beide Modelle bekommen dieselben Zero-shot-Nachrichten, Seed 42 und ein Budget von 2.048 Ausgabetokens. Innerhalb eines Vergleichs startet A vor B. Die UI zeigt das erzeugte Python, Bilder aus MuJoCo, gemessene Laufzeiten und die Zielprüfung.

## Was auf Vercel läuft

Ein Vercel-Hobby-Projekt kann die statische Oberfläche, sechs Referenzaufnahmen und die zugehörigen öffentlichen Prüfberichte ausliefern. Das passt für ein nichtkommerzielles Seminarprojekt. Der Build ist rund 1,4 MB groß. Der Python-Runner und beide Modellserver laufen auf einem Teamrechner oder einer VM. Die GPU kann auch per bestehendem SSH-Portforward angebunden werden. [Vercel Hobby](https://vercel.com/docs/plans/hobby) · [Live-Modellserver](remote-live.md)

In Vercel unter **Add New → Project** das bestehende GitHub-Repo `carlo2004/Simulation-Neura-LARA-5` importieren. Das Root Directory bleibt der Repo-Stamm. `vercel.json` setzt den Build `node web/build.mjs` und das Ausgabeverzeichnis `web/dist`. Die statische Seite braucht keine Umgebungsvariablen. Nach dem Deploy die Produktions-URL im Browser öffnen. [Vercel Git-Deployments](https://vercel.com/docs/git)

Mit dem Vercel-Link sind die Aufnahmen und das Öffnen gespeicherter Vergleichsberichte unabhängig vom Runner verfügbar.

## Runner starten

Auf einem Rechner mit dem Repo, Python 3.12 oder 3.13 und Node.js einmal die LARA-Geometrie einrichten und die Oberfläche bauen.

~~~bash
python bootstrap.py
node web/build.mjs
~~~

Dann einen Schlüssel für die Sitzung im Terminal setzen und den Runner starten. Unter Windows entspricht der Interpreter `.\.venv\Scripts\python.exe`. In PowerShell wird die Variable mit `$env:STACKLAB_WORKBENCH_TOKEN = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(24))"` gesetzt.

~~~bash
export STACKLAB_WORKBENCH_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(24))')"
.venv/bin/python -m stacklab workbench
~~~

`http://127.0.0.1:8787` öffnen, **Runner verbinden** wählen und den Schlüssel eingeben. Bei dieser URL kann das Feld Runner-URL leer bleiben. Jetzt lassen sich Referenzprogramme und eigener Python-Code live ausführen. Der erste Start lädt den geprüften Prompt2Robo-Snapshot. Eine vorhandene Kopie kann mit `--source` verwendet werden.

## Beide Modelle einbinden

Basismodell und Fine-Tuning auf derselben GPU oder auf getrennten Hosts laden. Beide Endpunkte müssen vom Runner aus über Loopback erreichbar sein. Für getrennte Hosts die jeweiligen Ports per SSH weiterleiten. Zwei Varianten können auch auf demselben OpenAI-kompatiblen Server liegen, wenn ihre Modell-IDs getrennt auswählbar sind.

Beispiel für zwei GGUF-Dateien mit `llama-server` aus llama.cpp, in zwei Terminals.

~~~bash
llama-server --host 127.0.0.1 --port 8081 --alias base -m /pfad/base.gguf
llama-server --host 127.0.0.1 --port 8082 --alias tuned -m /pfad/tuned.gguf
~~~

Für einen kompatiblen GGUF-LoRA-Adapter kann der zweite Server das Basismodell mit `--lora /pfad/adapter.gguf` laden. Transformers- oder vLLM-Checkpoints können über einen passenden OpenAI-kompatiblen Modellserver angeschlossen werden. [llama.cpp Server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)

~~~bash
mkdir -p runs
cp config/workbench-models.example.json runs/workbench-models.json
.venv/bin/python -m stacklab workbench --models runs/workbench-models.json
~~~

Im lokalen JSON stehen Anzeigename, Protokoll, URL und Modell-ID. Für den vorhandenen `stacklab serve`-Endpunkt genügen `"protocol": "stacklab"`, `"label"` und `"url"`. Für einen API-Schlüssel am Modellserver kann ein OpenAI-Eintrag den Namen einer Umgebungsvariablen in `api_key_env` enthalten. Browser und Reports erhalten keine Modellserver-Schlüssel. Beide Varianten erscheinen nach dem Verbinden in den Auswahllisten.

## Team-Session

Für den Live-Zugriff kann der Host den Runner über eine private HTTPS-Adresse bereitstellen, zum Beispiel per Tailscale Serve mit `tailscale serve --bg 8787`. Die Teammitglieder öffnen diese Adresse in ihrem Teamnetz und verwenden den Sitzungsschlüssel. Auf demselben Host läuft die Oberfläche direkt mit. [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)

Wer die Vercel-Seite mit dem Runner verbinden möchte, startet ihn zusätzlich mit `--origin https://EURE-PRODUKTIONS-URL.vercel.app`. In der Oberfläche die HTTPS-Adresse des Runners und den Sitzungsschlüssel eingeben. Der Runner lauscht lokal und akzeptiert für die API nur den Schlüssel und erlaubte Browser-Origins. Den Schlüssel separat an das Team geben.

Standardmäßig verarbeitet der Runner einen Vergleich gleichzeitig. Mit `--concurrent 2` können zwei Browser gleichzeitig unabhängige Läufe ausführen. Bei belegten Slots meldet die Oberfläche den Engpass. Für eine vergleichbare Durchsatzmessung dieselbe Hardware, dasselbe Backend und einen Lauf zur Zeit verwenden.

## Vergleich auswerten

- Bei einer Datensatzaufgabe prüft der ursprüngliche Zielchecker die auf dem LARA 5 gemessenen Zustände. Ein freier Prompt liefert Zustandsdaten und Programm ohne Zielwertung.
- Die Webausführung unterstützt das Prompt2Robo-API mit begrenzten Python-Ausdrücken, Schleifen, Hilfsfunktionen und ausgewählten numerischen Operationen. Ungültiger oder nicht unterstützter Code bleibt als Fehler im Ergebnis sichtbar.
- Die UI zeigt native Decode-Tokens/s, wenn der Server diese liefert. Andernfalls zeigt sie bei bekanntem Tokenzähler den Durchsatz über die ganze Anfrage. Der Tooltip und das JSON kennzeichnen die Messbasis.
- **JSON speichern** hält beide Ergebnisse, Anfangsszene, Modell-IDs, Prompt-Prüfsumme, Code, Zielprüfung, Zeiten und je ein Endbild fest. Über **Bericht öffnen** lässt sich die Gegenüberstellung später auch auf der statischen Seite ansehen.
