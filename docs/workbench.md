# LARA 5 im Browser

Links und rechts stehen je ein Modell und ein Prompt. **A starten** und **B starten** führen eine Seite aus. **Beide starten** führt die Programme nacheinander aus, jeweils aus derselben gewählten Startszene. **Prompt A → B** kopiert den Text für einen Vergleich mit identischer Anweisung. Die Live-Bilder kommen aus derselben MuJoCo-Simulation wie die lokale LARA-Ansicht.

Eine unveränderte Datensatzaufgabe erhält eine Zielprüfung. Bei geänderten Prompts zeigt der Runner die Ausführung und den Endzustand. Unter **Aufnahmen und Berichte** gibt es die Referenzvideos und JSON-Export. Ein Bericht enthält den ausgeführten Prompt, die Zielprüfung und die Messwerte pro Seite.

## Runner in Google Colab

Der Runner und die Modelle laufen auf der Colab-GPU-VM. Die Website auf Vercel dient als Oberfläche. Für die Verbindung zum Runner verwenden wir den offiziellen SSH-Zugang von Colab. Er benötigt eine dafür bereitgestellte Laufzeit. Bei Colab Pro mit positivem Guthaben gelten für SSH und interaktive Weboberflächen die Ausnahmen der Colab-FAQ. [Colab-FAQ](https://research.google.com/colaboratory/faq.html) · [SSH einmal einrichten](remote-live.md#2-benannte-colab-sitzung-anlegen)

**1. Auf deinem Rechner:** Die benannte Colab-Sitzung mit A100 anlegen, falls sie noch nicht läuft. Den SSH-Host `lara-colab` wie in der Einrichtung auf diese Sitzung zeigen lassen. Mit der Verbindung wird der Browserport weitergeleitet.

~~~bash
colab --auth=oauth2 new -s lara-workbench --gpu A100
ssh -t -o ExitOnForwardFailure=yes -L 127.0.0.1:8787:127.0.0.1:8787 lara-colab
~~~

Wenn der SSH-Zugang mit 404 antwortet, zuerst eine per CLI angelegte Laufzeit prüfen. `colab --auth=oauth2 url -s lara-workbench --open` kann dieselbe benannte Sitzung im Notebook öffnen. [Offizielle Colab-CLI](https://github.com/googlecolab/google-colab-cli)

**2. Im Colab-Terminal:** Beim ersten Mal das Repo klonen. Im vorhandenen Checkout genügt `git pull --ff-only`.

~~~bash
cd /content
git clone https://github.com/carlo2004/Simulation-Neura-LARA-5.git
cd Simulation-Neura-LARA-5
python bootstrap.py
apt-get update -qq && apt-get install -y -qq libosmesa6
export STACKLAB_WORKBENCH_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(24))')"
~~~

Den Sitzungsschlüssel im eigenen Terminal bereithalten und in der Browsermaske eingeben. In dieser Shell steht er unter `$STACKLAB_WORKBENCH_TOKEN`. Die Modellgewichte als GGUF in der Colab-Laufzeit bereitstellen und die Pfade einsetzen.

~~~bash
.venv/bin/python tools/start_colab_workbench.py \
  --base /content/base.gguf \
  --tuned /content/fine-tuning.gguf
~~~

Bei einem kompatiblen GGUF-LoRA `--lora /content/adapter.gguf` anstelle von `--tuned` verwenden. Der Starthelfer prüft die LARA-Ansicht, lädt bei Bedarf die geprüfte CUDA-Version von llama.cpp und wartet auf beide Modelle. Für ältere CUDA-Images kann dafür ein Quellbuild mit CMake, C++-Compiler und `nvcc` nötig sein. Ein vorhandenes CUDA-Binary kann mit `--llama-server` angegeben werden. Ohne Modellpfade startet der Runner für einen ersten Test der Referenzprogramme.

Falls beim Quellbuild CMake fehlt, installiere es mit `.venv/bin/python -m pip install cmake`. Die Einrichtung benötigt Python ab 3.12.

**3. Im Browser:** [Lokale Workbench öffnen](http://127.0.0.1:8787). **Runner verbinden** wählen, das URL-Feld leer lassen und den Sitzungsschlüssel eingeben. Zwei Modelle und eine Szene auswählen.

### Team-Session

Der Rechner mit dem offenen SSH-Tunnel kann Port 8787 über eine private HTTPS-Adresse im Teamnetz freigeben. Mit Tailscale Serve läuft `tailscale serve --bg 8787` auf diesem Rechner. Die Teammitglieder öffnen die ausgegebene Team-URL und geben den Sitzungsschlüssel ein. Falls der Proxy den Host-Header umschreibt, die Team-URL beim Colab-Start mit `--origin https://RECHNER.TEAM.ts.net` erlauben. Mit `--concurrent 2` können zwei Personen gleichzeitig unabhängige Läufe starten. [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)

Auf der [Vercel-Workbench](https://simulation-neura-lara-5.vercel.app/) kann das Team dieselbe HTTPS-Runner-URL unter **Runner verbinden** eintragen. Dafür beim Colab-Start zusätzlich `--origin https://simulation-neura-lara-5.vercel.app` setzen. Die Browser-Ansicht bleibt über Vercel erreichbar, wenn Colab pausiert. Live-Läufe sind während der aktiven Colab-Sitzung und des offenen SSH-Tunnels verfügbar.

## Vorhandene Modellserver

Der Runner kann auch zwei bereits gestartete OpenAI-kompatible Server oder `stacklab serve` verwenden. Beide Endpunkte müssen vom Runner aus per Loopback erreichbar sein. In `runs/workbench-models.json` die Einträge aus [der Beispielkonfiguration](../config/workbench-models.example.json) anpassen und starten.

~~~bash
.venv/bin/python -m stacklab workbench --models runs/workbench-models.json
~~~

Für `stacklab serve` verwendet der Eintrag `"protocol": "stacklab"` sowie `label` und `url`. Bei OpenAI-kompatiblen Endpunkten kann `api_key_env` auf einen Schlüssel in der Umgebung des Runners verweisen. Die UI zeigt native Decode-Tokens/s, soweit verfügbar, sonst den Durchsatz über die ganze Anfrage. Die Messbasis steht im Tooltip und im Export.

## Vercel

`vercel.json` baut die statischen Dateien mit `node web/build.mjs`. `web/dist` enthält die Oberfläche und die öffentlichen Referenzaufnahmen. Das bestehende Vercel-Projekt zieht aus `main`. Die Python-Simulation und die Modellgewichte bleiben auf dem Runner.
