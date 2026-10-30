# Nächster Versuch nach dem A100 Pilot

Version 3.7 trennt den kurzen Einblockprompt vom bisherigen Systemtext.
`--prompt-profile auto` verwendet bei einem Block `one-shot`, bei mehreren
Blöcken `legacy`. Für einen kontrollierten Vergleich lässt sich bei einem
Block ausdrücklich `--prompt-profile legacy` wählen. Die aufgelöste Auswahl
steht in Manifest, Bedingungs-ID, Ergebnis und CSV. Unterschiedliche
Promptprofile erhalten verschiedene Vergleichsprüfsummen.

Die vorhandenen A100-Rohdaten und ihre ursprüngliche Rangliste bleiben
archivierte Ergebnisse von Version 3.6. Der neue Prompt ist noch kein
Nachweis einer höheren Modellqualität.

## Lokal vorbereiten ohne Colab und ohne Modellaufruf

Im Projektordner, unter Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe tools/prepare_followup.py --output runs/followup-v37
```

Der Helfer prüft zehn handgeschriebene CPU-Kontrollen: fünf Bewegungen und
fünf Stapelaufgaben in den ursprünglichen Szenen. Er speichert die tatsächlichen
Aktionen und die unabhängigen Physikurteile in `controls.json`. Erst nach
allen Erfolgen schreibt er `proposal.json`. Diese Datei ist ein Vorschlag,
kein ausführbares, bereits mit einer GPU verbundenes Experimentmanifest.
Es werden keine Modellgewichte heruntergeladen, keine Generierungen ausgeführt
und keine VMs angelegt. Für einen erneuten Aufruf einen neuen Ausgabeordner
verwenden; vorhandene Belege werden nicht überschrieben.

Die Rezeptdatei `experiments/one-shot-followup.json` sieht Nemotron, Granite
und Qwen 9B vor, jeweils dieselben fünf Szenen- und Generierungsseedpaare,
dieselben beiden Aufgaben und genau einen Programmblock. Beide Promptprofile
ergeben jeweils 30 geplante Episoden, insgesamt 60. Sampling, Thinking,
Aufgabenwortlaut, Tokenbudget und Physik bleiben im direkten Vergleich gleich.
Die neue eindeutigere englische Aufgabenformulierung sollte erst in einem
weiteren Vergleich geprüft werden, damit ihre Wirkung nicht mit der des
Systemprompts verwechselt wird.

## Später mit dem einen vorhandenen Server einfrieren

Den bestehenden SSH-Tunnel und den bereits gestarteten Benchmarkserver benutzen.
Der Helfer enthält keine Colab-CLI und keinen SSH-Aufruf. Eine fehlende Verbindung
führt zu einem Fehler, nicht zur Anlage einer neuen Sitzung.

```powershell
.\.venv\Scripts\python.exe tools/prepare_followup.py --output runs/followup-v37-a100 --server-url http://127.0.0.1:8765
```

Nach den CPU-Kontrollen werden zwei getrennte Manifeste mit der tatsächlich
gemeldeten GPU, Serverfassung und dem Modellkatalog geschrieben:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment run runs/followup-v37-a100/legacy
.\.venv\Scripts\python.exe -m stacklab experiment run runs/followup-v37-a100/one-shot
```

Diese beiden Befehle starten die Modellversuche. Ein Plan allein tut das nicht.
Keine Modellantwort wird repariert oder nach einem Fehler erneut angefordert.
Die bestehende Agentenregelung bleibt aktiv; der LLM bekommt eine einzige
Gelegenheit für das vollständige Programm. Nach der Auswahl eines Prompts
zusätzliche neue Stapelszenen verwenden, bevor eine allgemeine Rangfolge
behauptet wird. L4 gegen A100 nur mit demselben Promptprofil vergleichen;
der GPU-Vergleich lehnt unterschiedliche Promptbedingungen bewusst ab.

## Belegte technische Korrekturen

- Modelltext mit nicht darstellbaren Zeichen wird in der Terminalansicht
  ersatzweise escaped. Workerprotokolle verwenden explizit UTF-8. Ein zusätzlicher
  I/O-Ausfall vor der Ausführung ist ein Infrastrukturfehler des Agenten.
- Fehlendes `ensurepip` beim Erstellen der Umgebung wird mit `virtualenv`
  behandelt, auch bei einer bereits angefangenen `.venv`. Ein beliebiger
  nichtleerer Ordner wird nicht als Python-Umgebung überschrieben.
- CUDA-Quellbuilds suchen `nvcc` zusätzlich über `CUDACXX`, `CUDA_HOME`,
  `CUDA_PATH` und `/usr/local/cuda/bin`. Der Buildprozess erhält dessen Pfad,
  ohne die Umgebung des aufrufenden Prozesses zu verändern. Fehlt der Compiler,
  wird genau das gemeldet. Ein funktionierendes `nvidia-smi` reicht dafür nicht.

Die zusätzlichen Compilerpfade lösen eine fehlende PATH-Eintragung. Sie
installieren kein fehlendes CUDA Toolkit. Dory benötigt weiterhin einen
erfolgreichen Quellbuild, bevor seine Qualität beurteilt werden kann.

Primärquellen für diese Unterscheidungen:
[NVIDIA zur CUDA-Umgebung und zu nicht gefundenem nvcc](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/),
[virtualenv zu eingebetteten pip-Seedern](https://virtualenv.pypa.io/en/latest/explanation.html),
[Python zu PYTHONIOENCODING](https://docs.python.org/3.13/using/cmdline.html#envvar-PYTHONIOENCODING),
[Mistral zu eindeutigen und widerspruchsfreien Prompts](https://docs.mistral.ai/inference/prompting).
