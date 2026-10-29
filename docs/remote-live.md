# Live-Simulation lokal, Modell auf Colab

Das 3D-Fenster, MuJoCo, Roboterprogramme und die Auswertung laufen auf deinem Rechner. Ein dauerhafter Modellserver auf Colab liefert Antworten über einen SSH-Portforward. Du kannst im lokalen Terminal Sprache eingeben, Code und Tokens/s verfolgen und während der Ausführung den Arm sehen. Nach jedem Programmblock erhält das Modell den tatsächlichen Zustand und die Ausführungsrückmeldung. Während der Generierung pausiert die Physik; das Fenster bleibt bedienbar. Die Bewegung beginnt nach einem vollständigen, geprüften Programmblock.

Die Modellgewichte werden auf Colab benötigt. Auf deinem Rechner genügt die normale Simulationsinstallation; ein lokaler Modelldownload und eine lokale NVIDIA-GPU sind für diesen Modus nicht nötig. Der Server hält ein Modell über mehrere Prompts geladen.

## Voraussetzungen

- Lokal: Git, Python 3.12/3.13, ein Desktop und das mit `python bootstrap.py` eingerichtete Projekt.
- Colab Pro mit positivem Recheneinheiten-Guthaben und einer verfügbaren GPU. Zunächst L4 verwenden; A100 funktioniert mit demselben Serverbefehl.
- Ein SSH-fähiger Colab-Runtime-Zugang. Die offizielle CLI dokumentiert einen Fehler 404, falls dieser Zugang nicht bereitgestellt wird. Seine Verfügbarkeit für dein Konto muss beim ersten Verbinden geprüft werden.
- Die [Colab CLI](https://github.com/googlecolab/google-colab-cli) und OpenSSH auf dem Rechner, der den Tunnel herstellt. Die CLI-README nennt Linux und macOS als unterstützte Systeme. Unter Windows die CLI und den Tunnel zunächst in **WSL** betreiben; die Simulation kann in normalem Windows-PowerShell laufen.

Nach der [Colab-FAQ](https://research.google.com/colaboratory/faq.html) kann die zusätzliche Einschränkung für SSH/Remote-Desktops bei kostenlosen Laufzeiten durch einen bezahlten Tarif und positives Guthaben entfallen. Laufzeitgrenzen und mögliche Unterbrechungen bleiben bestehen. Dieser Ablauf benutzt die offizielle CLI; er installiert keinen öffentlichen Tunnelanbieter und keinen zusätzlichen SSH-Daemon in Colab.

## 1. Lokale Simulation aktualisieren

Im vorhandenen Projektordner:

```bash
git pull --ff-only
python bootstrap.py
```

Unter Windows entspricht der Projekt-Interpreter `.\.venv\Scripts\python.exe`, unter Linux/macOS `.venv/bin/python`. Alle folgenden `stacklab`-Befehle mit diesem Interpreter ausführen.

## 2. Benannte Colab-Sitzung anlegen

In einem Linux-/macOS-Terminal oder unter Windows in WSL:

```bash
python3 -m venv ~/.venvs/lara-colab-cli
~/.venvs/lara-colab-cli/bin/python -m pip install google-colab-cli
~/.venvs/lara-colab-cli/bin/colab --auth=oauth2 sessions
```

Die CLI führt bei Bedarf zur Google-Anmeldung. Autorisierungscode und Anmeldedaten bleiben in deinem Terminal. `colab auth` ist ein anderer Befehl für Anmeldungen innerhalb der VM und wird hier nicht benötigt.

Erst prüfen, ob `lara-live` bereits existiert. Falls nicht:

```bash
~/.venvs/lara-colab-cli/bin/colab --auth=oauth2 new -s lara-live --gpu L4
~/.venvs/lara-colab-cli/bin/colab --auth=oauth2 status -s lara-live
```

Für A100 beim Anlegen `--gpu A100` verwenden. Eine neue GPU-Sitzung verbraucht deine Colab-Einheiten. Eine bestehende Browser-Sitzung mit `[?]` in der CLI-Liste ist noch kein lokal gespeicherter Sitzungsname; diesen Namen nicht als Alias übernehmen. Dieser Ablauf verwendet bewusst die über die CLI erstellte Sitzung. Eine unbenutzte andere GPU-Laufzeit vorher beenden.

## 3. SSH und Tunnel öffnen

Falls noch kein geeigneter SSH-Schlüssel vorhanden ist:

```bash
ssh-keygen -t ed25519
```

Einen vorhandenen Schlüssel beibehalten. In `~/.ssh/config` folgenden Eintrag ergänzen. `DEIN_BENUTZER` durch den tatsächlichen Linux-/macOS-/WSL-Benutzernamen ersetzen; `ProxyCommand` braucht einen **absoluten** Pfad, kein `~`.

```sshconfig
Host lara-colab
    User root
    IdentityFile ~/.ssh/id_ed25519
    ProxyCommand /home/DEIN_BENUTZER/.venvs/lara-colab-cli/bin/colab --auth=oauth2 ssh --proxy-mode -s lara-live
    StrictHostKeyChecking accept-new
    UserKnownHostsFile ~/.ssh/known_hosts_lara_colab
```

Unter macOS beginnt der absolute Pfad üblicherweise mit `/Users/DEIN_BENUTZER/`. Der Sitzungsname muss exakt stimmen: Die CLI kann bei unbekanntem Namen eine neue Sitzung anlegen. Ein bestehender verschlüsselter Schlüssel darf selbstverständlich eine Passphrase verwenden.

Mit **einer** SSH-Verbindung Shell und Portforward öffnen:

```bash
ssh -t -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 lara-colab
```

Dieses Terminal offen lassen. Es ist jetzt die Shell auf Colab. Die CLI kann weitere parallele SSH-Verbindungen ablehnen; eine zweite Verbindung ist für den Ablauf nicht nötig.

Wenn SSH einen Fehler 404 über einen fehlenden `/colab/ssh`-Endpunkt meldet, eine frisch über `colab new` erstellte Sitzung prüfen. Falls das auch dort auftritt, unterstützt der zugeteilte Zugang diese Methode noch nicht. Der Projektserver ist dann trotzdem vorbereitet; auf einer Compute-Engine-VM ist derselbe Ablauf mit deren regulärem SSH-Zugang verwendbar.

Nach dem Ersetzen einer Colab-VM kann sich deren SSH-Hostschlüssel ändern. Erst die tatsächlich neu erstellte Sitzung prüfen; danach nur den alten Eintrag dieser Verbindung entfernen:

```bash
ssh-keygen -R lara-colab -f ~/.ssh/known_hosts_lara_colab
```

## 4. Auf Colab das Modell starten

In der gerade geöffneten **Colab-Shell**:

```bash
cd /content
git clone https://github.com/carlo2004/Simulation-Neura-LARA-5.git
cd Simulation-Neura-LARA-5
python3 tools/start_remote.py --model granite8b --device cuda --threads 2
```

Bei vorhandenem Checkout stattdessen dort `git pull --ff-only` ausführen. Der Helfer erstellt `.venv`, prüft die GPU, richtet gegebenenfalls die CUDA-Buildwerkzeuge ein und installiert nur das gewählte Modell. Ein erster Quellbuild kann deutlich länger als die Paketinstallation dauern; sein Fortschritt und der Logpfad werden angezeigt. Ein unveränderter Build wird in derselben VM wiederverwendet.

Falls Colabs `python3 -m venv` wegen fehlendem `ensurepip` scheitert, die Projektumgebung mit `virtualenv` anlegen und den Helfer erneut starten (Python 3.12/3.13):

```bash
python3 -m pip install virtualenv
python3 -m virtualenv .venv
python3 tools/start_remote.py --model granite8b --device cuda --threads 2
```

Ist bereits eine unvollständige `.venv` vorhanden, vorher `mv .venv .venv-incomplete` ausführen. Das ist eine Einrichtung der jeweiligen Colab-Laufzeit; dafür muss der Projektcode nicht geändert werden.

Auf folgende Meldung warten:

```text
READY http://127.0.0.1:8765
```

Bei CUDA wird vor `READY` sowohl der CUDA-Backend als auch das tatsächliche Auslagern der Modellschichten geprüft. Ein fehlgeschlagener Start wird nicht als CPU-Erfolg ausgegeben. Der Server bindet ausschließlich `127.0.0.1`; SSH stellt die Verbindung her.

Unter Linux ergänzt der Launcher die Bibliothekssuche um `/usr/lib64-nvidia` sowie vorhandene Python-Paketpfade für CUDA-Runtime und cuBLAS, auch außerhalb der Projektumgebung. Ein vorhandenes `libggml-cuda.so` aus der installierten Runtime wird über `GGML_BACKEND_PATH` explizit geladen. Der CUDA-Server startet mit `-lv 5`, damit `inference.log` die tatsächlich ausgelagerten Schichten meldet, zum Beispiel `offloaded 41/41 layers to GPU`. Die Layerzahl hängt vom Modell ab; sie ist kein fest vorgegebener Erfolgswert. Die gemessenen Zahlen stehen zusätzlich in `device.json`.

Der Starthelfer verwendet denselben gesperrten Modellkatalog und dieselbe GLIBC-/CUDA-Auswahl wie das Batch-Notebook. Optionen: `--model`, `--device`, `--threads`, `--port`, `--cuda-runtime auto|binary|source`. Für später bereits eingerichtete Maschinen genügt:

```bash
.venv/bin/python -m stacklab serve --model granite8b --device cuda --threads 2
```

## 5. Lokal live sprechen und zuschauen

Jetzt ein zweites Terminal **auf deinem Rechner** öffnen und in den lokalen Projektordner wechseln.

Linux/macOS:

```bash
.venv/bin/python -m stacklab doctor --server-url http://127.0.0.1:8765
.venv/bin/python -m stacklab chat --server-url http://127.0.0.1:8765 --axes --stackviz red blue --stream
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m stacklab doctor --server-url http://127.0.0.1:8765
.\.venv\Scripts\python.exe -m stacklab chat --server-url http://127.0.0.1:8765 --axes --stackviz red blue --stream
```

Bei WSL ist dieser Ablauf auf die Weiterleitung von Windows-`localhost` zum WSL-Port angewiesen. Wenn `doctor` dort keine Verbindung bekommt, zuerst denselben Aufruf in WSL prüfen. Der Server und sein Protokoll müssen dafür nicht geändert oder öffentlich freigegeben werden; die WSL-Netzwerkeinstellungen sind dann der nächste Prüfpunkt.

Im geöffneten Live-Chat:

```text
Bewege den Greifer 5 cm nach rechts.
Staple den roten Würfel auf den blauen Würfel.
/status
/check red blue
/stop
/sim manual on
/help
```

`/sim manual on` aktiviert die bestehende Tastatursteuerung. Für die nächste LLM-Aufgabe wird sie während der Ausführung ausgesetzt. `/stop` unterbricht Generierung oder Bewegung. Das Fenster bleibt für weitere Prompts offen. `--show-thinking` zeigt zusätzlich den Reasoning-Text, wenn das Modell ihn liefert. Die während des Streams angezeigten Geschwindigkeiten und die abschließenden nativen Tokens/s stammen vom Modellserver.

Ohne vorgegebenes unabhängiges Ziel bleibt eine freie Modell-Fertigmeldung unbewertet (`success: null`). `/check red blue` zeigt die echte physische Stapelprüfung. Erfolgreiche Verbindung bedeutet keine Garantie, dass ein unverändertes Modell jede Stapelaufgabe löst.

Ein Server hält genau ein Modell. Zum Wechseln den Server mit Strg+C beenden, den Starthelfer mit einem anderen Modell erneut ausführen und den lokalen Chat neu starten. `/model` erklärt diese Grenze im Remote-Modus. `--model` am lokalen Chat ist optional; falls angegeben, muss die Modell-Prüfsumme zum Server passen. `--device` und `--threads` werden für Remote-Inferenz am Server gewählt.

## Protokolle und Wiederaufnahme

Die lokalen Chat-Verzeichnisse unter `runs/chat_…` enthalten Szene, unveränderten generierten Code, tatsächliche Aktionen, Beobachtungen, Rückmeldungen und Physikzustände wie bisher. Pro Modellblock kommen hinzu:

- `remote-server.json`: Modellkonfiguration, GPU-Nachweis, Server-Softwarestand und Threads.
- `request.json`, `response.json`, `stream.jsonl`: kopierte native Inferenzdaten.
- `server-generation.json`: ursprüngliche Generierungsmetadaten des Servers.
- `generation.json`: dieselben Messungen mit Verbindungsdaten und gemessener Client-Gesamtzeit.
- `remote-request.json`, `remote-stream.jsonl`: das tatsächlich verwendete Transportprotokoll, auch bei Teilantworten.

Native Tokens/s messen die Generierung auf dem Server; `transport.client_round_trip_seconds` enthält zusätzlich die Übertragung. Ein vorab geladenes Modell meldet pro Anfrage keine erneute Ladezeit. Server- und lokale Softwarestände bleiben getrennt sichtbar.

Bei Verbindungsverlust wird ein unvollständiger Programmblock nicht ausgeführt. Teilantworten und Fehlermetadaten bleiben lokal erhalten. Eine neue Verbindung setzt keine unterbrochene Bewegung automatisch fort. Nach einem Server-Neustart verlangt der Client einen neuen Chat, damit ein Modellwechsel nicht unbemerkt geschieht. Ein Client-Abbruch beendet die eigene Anfrage; andere Anfragen werden dadurch nicht abgebrochen.

Die Remote-Anbindung gilt zunächst für `chat`; die eingefrorenen Batch-Versuche bleiben im [Colab-Notebook](colab.md). Für Seminarvergleiche Modellrevision, Quantisierung, Prompt, Seeds, Budgets und Hardware aus den Protokollen festhalten. Diese Änderung führt kein Fine-Tuning ein.

## Beenden

Den lokalen Chat mit `/quit` schließen. In der Colab-Shell den Server mit Strg+C beenden und die SSH-Shell mit `exit` schließen. Anschließend lokal die GPU-Sitzung freigeben:

```bash
~/.venvs/lara-colab-cli/bin/colab --auth=oauth2 stop -s lara-live
```

## Compute Engine später

Auf der VM denselben Checkout und Starthelfer verwenden. Statt der Colab-CLI-Proxyverbindung den regulären SSH-Zugang der VM benutzen und wieder `127.0.0.1:8765` weiterleiten. Der lokale `chat --server-url …` bleibt gleich. GPU-VM-Kosten und Colab-Recheneinheiten sind getrennte Abrechnungen.

Primärquellen, geprüft am 29.10.2026: [Colab-FAQ](https://research.google.com/colaboratory/faq.html), [CLI und Plattformhinweise](https://github.com/googlecolab/google-colab-cli), [SSH-Transport und Fehlerfälle](https://github.com/googlecolab/google-colab-cli/blob/main/docs/06_ssh_access.md), [CLI-Anmeldung](https://github.com/googlecolab/google-colab-cli/blob/main/docs/04_automation_and_utility.md).
