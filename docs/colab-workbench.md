# LARA-Workbench in Colab starten

[Notebook in Google Colab öffnen](https://colab.research.google.com/github/carlo2004/Simulation-Neura-LARA-5/blob/main/notebooks/colab_workbench.ipynb) · [Workbench auf Vercel](https://simulation-neura-lara-5.vercel.app/)

Für die interaktive Nutzung ist eine Colab-Pro-Laufzeit mit positivem Recheneinheiten-Guthaben vorgesehen. Für einen Referenztest genügt eine CPU. Für zwei Modelle wähle eine GPU wie die A100. Die Verfügbarkeit der GPU hängt vom Konto und von der aktuellen Auslastung ab. [Colab-FAQ](https://research.google.com/colaboratory/faq.html)

## Erster Test im Notebook

1. Öffne das Notebook in Colab und speichere eine Kopie in Drive. Verbinde die Laufzeit. Wenn du zwei Modelle laden willst, wähle vorher unter **Laufzeit → Laufzeittyp ändern** die GPU.
2. Lege links unter **Secrets** `STACKLAB_WORKBENCH_TOKEN` an und aktiviere den Zugriff für das Notebook. Verwende einen zufälligen Schlüssel mit mindestens 24 URL-sicheren Zeichen. Den kannst du lokal mit `python -c "import secrets; print(secrets.token_urlsafe(24))"` erzeugen. Dieser Schlüssel gehört zum LARA-Runner.
3. Lass in Zelle 1 die Modellpfade für den ersten Test leer. Für den Vergleich setze `BASE_GGUF` und `TUNED_GGUF`. Bei einem kompatiblen GGUF-LoRA setzt du `LORA_GGUF` anstelle von `TUNED_GGUF`. Dateien in Drive kannst du mit einem Pfad wie `/content/drive/MyDrive/LARA/base.gguf` angeben. Die Einrichtungszelle bindet Drive bei Bedarf ein.
4. Führe die Zellen 1 bis 4 aus. Warte auf **Runner bereit**. In der Vorschau unter Zelle 4 **Runner verbinden** wählen, URL leer lassen und den Sitzungsschlüssel eingeben.
5. Wähle **Rot auf Blau**. Unter **Startkoordinaten und Python** auf **Referenz ausführen** klicken. Mit geladenen Modellen kannst du danach A und B einzeln oder gemeinsam starten.

Die Colab-Vorschau ist für deine eigene Notebook-Sitzung gedacht. Für einen Team-Link verwende den folgenden Ablauf mit einer per CLI angelegten Laufzeit.

## Team-Link mit ngrok

Der Colab-Runner bleibt an Port 8787 der Laufzeit gebunden. Der offizielle Colab-SSH-Zugang leitet diesen Port auf deinen Rechner. ngrok läuft auf diesem Rechner und liefert die HTTPS-Adresse für das Team. [Colab-SSH](https://github.com/googlecolab/google-colab-cli/blob/main/docs/06_ssh_access.md) · [ngrok-CLI](https://ngrok.com/docs/gateway/endpoints/agent-cli-quickstart)

**1. Auf deinem Rechner die offizielle Colab-CLI einrichten.** Verwende Linux, macOS oder unter Windows WSL. Wenn das Repo schon vorhanden ist, genügt im Repo `git pull --ff-only`.

~~~bash
git clone https://github.com/carlo2004/Simulation-Neura-LARA-5.git
cd Simulation-Neura-LARA-5
python3 -m venv .venv-colab
.venv-colab/bin/python -m pip install -U google-colab-cli
COLAB="$(pwd)/.venv-colab/bin/colab"
"$COLAB" --auth=oauth2 sessions
~~~

**2. Die benannte Colab-Laufzeit anlegen.** Wenn `lara-workbench` schon läuft, verwende dieselbe Sitzung. Für einen CPU-Referenztest kannst du `--gpu A100` weglassen.

~~~bash
"$COLAB" --auth=oauth2 new -s lara-workbench --gpu A100
~~~

**3. Das Notebook in genau dieser Laufzeit ausführen.** Für den ersten Test genügt dieser Befehl.

~~~bash
"$COLAB" --auth=oauth2 exec -s lara-workbench --timeout 3600 \
  --env STACKLAB_COLAB_MODE=team -f notebooks/colab_workbench.ipynb
~~~

Für den Modellvergleich stelle die beiden GGUF-Dateien in der Laufzeit bereit. Liegen sie in Drive, verwende zuerst `"$COLAB" --auth=oauth2 drivemount -s lara-workbench`. Dann setze die tatsächlichen Pfade ein.

~~~bash
"$COLAB" --auth=oauth2 exec -s lara-workbench --timeout 3600 \
  --env STACKLAB_COLAB_MODE=team \
  --env "STACKLAB_BASE_GGUF=/content/drive/MyDrive/LARA/base.gguf" \
  --env "STACKLAB_TUNED_GGUF=/content/drive/MyDrive/LARA/tuned.gguf" \
  -f notebooks/colab_workbench.ipynb
~~~

Für einen GGUF-LoRA-Adapter verwende `STACKLAB_LORA_GGUF` anstelle von `STACKLAB_TUNED_GGUF`. Falls du erst den Referenzmodus getestet hast, stoppe ihn mit `printf 'stop_runner()\n' | "$COLAB" --auth=oauth2 exec -s lara-workbench` und starte anschließend den Lauf mit Modellpfaden. Nach **Runner bereit** bleiben Workbench und Modelle in der Laufzeit aktiv.

**4. Den SSH-Portforward öffnen.** Erzeuge mit `ssh-keygen -t ed25519` einen Schlüssel, falls du noch keinen hast. Der Befehl öffnet den Browserport und zeigt dir den Sitzungsschlüssel im privaten Terminal. Lass dieses Terminal offen.

~~~bash
ssh -t -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new \
  -o "UserKnownHostsFile=$HOME/.ssh/known_hosts_lara_workbench" \
  -o "ProxyCommand='$COLAB' --auth=oauth2 ssh --proxy-mode -s lara-workbench" \
  -L 127.0.0.1:8787:127.0.0.1:8787 root@lara-workbench \
  'cat /content/lara-workbench/runner.key; exec bash -l'
~~~

Teste zuerst [localhost:8787](http://127.0.0.1:8787). Wenn der SSH-Endpunkt in einer neu per CLI angelegten Laufzeit mit 404 antwortet, steht Colab-SSH für diese Laufzeit nicht zur Verfügung. Der persönliche Test im Notebook bleibt nutzbar.

**5. ngrok auf deinem Rechner starten.** Installiere den ngrok-Agent und konfiguriere dort deinen Authtoken über den Befehl aus dem Dashboard. Den Sitzungsschlüssel aus Schritt 4 brauchst du später in der Workbench. [ngrok einrichten](https://ngrok.com/docs/gateway/endpoints/agent-cli-quickstart)

~~~bash
ngrok http http://127.0.0.1:8787 --inspect=false
~~~

Teile die ausgegebene HTTPS-Adresse mit dem Team und übermittle den LARA-Sitzungsschlüssel getrennt. Am einfachsten öffnet ihr die ngrok-Adresse direkt. Unter **Runner verbinden** bleibt die URL dann leer. Alternativ könnt ihr auf der Vercel-Seite die ngrok-Adresse im Feld **Runner-URL** eintragen. Wenn die ngrok-Startseite dazwischenkommt, öffnet die ngrok-Adresse direkt.

**6. Beenden.** ngrok und den SSH-Tunnel schließen. Danach die Colab-Sitzung freigeben.

~~~bash
"$COLAB" --auth=oauth2 stop -s lara-workbench
~~~

## Wenn der Start hängt

- **Datei fehlt**. Prüfe den tatsächlichen Pfad in Colab. Ein PEFT-Adapter im Safetensors-Format braucht zuerst einen GGUF-Export.
- **GPU oder Speicher reicht nicht**. Beginne mit dem Referenzmodus und prüfe die Größe beider GGUF-Dateien. Der Runner startet beide Modelle auf derselben GPU.
- **Runner wurde nicht bereit**. Das Startprotokoll steht unter `/content/lara-workbench/runner.log`. Ein erster CUDA-Quellbuild kann mehrere Minuten dauern.
- **Port 8787 ist belegt**. Stoppe den früheren Runner in derselben Laufzeit, bevor du das Notebook erneut startest.
