# Colab mit NVIDIA L4 und A100

[Notebook direkt in Colab öffnen](https://colab.research.google.com/github/carlo2004/Simulation-Neura-LARA-5/blob/main/notebooks/colab_gpu.ipynb).

Dasselbe Notebook unterstützt beide Karten. In Colab eine GPU-Laufzeit auswählen, zunächst L4, und die Zellen der Reihe nach ausführen. Es werden nur die ausgewählten Modelle installiert. Die Standardeinstellung ist Granite 8B mit einem Bewegungs- und einem Stapelfall sowie einem beziehungsweise bis zu vier Programmblöcken.

## Was eingerichtet wird

- Eine eigene `.venv` mit Python 3.12/3.13 und den bisherigen Simulationspaketen. Bei einem anderen Notebook-Python wird Python 3.12 über `uv` eingerichtet.
- Dieselben auf Revision und SHA-256 festgelegten GGUF-Gewichte wie im CPU-Modus.
- Ein separater CUDA-Runtimecache für Linux x86-64. CPU-Installationen bleiben erhalten. Die sechs Modelle mit Standard-Runtime verwenden weiterhin llama.cpp `b11951`; Dory bleibt auf seinem empfohlenen Quellcommit.
- Tatsächliche NVIDIA-Inventardaten: Name, UUID, gesamter GPU-Speicher in MiB und Treiber. `memory.total` bedeutet nicht freier Speicher.
- Eine CUDA-Geräteprüfung vor dem Gewichtsdownload und eine Prüfung der echten Offloading-Meldung beim Modellstart. Ein CPU-Fallback geschieht nicht still.
- Optional ein Video eines separaten Modell-Bewegungsversuchs. OSMesa rendert auf der CPU; die Inferenz verwendet CUDA. Die Hauptvergleichsläufe zeichnen standardmäßig kein Video auf.

CUDA nutzt standardmäßig alle verfügbaren Modellschichten auf der GPU. Modell, Kontext und Puffer müssen in den verfügbaren Speicher passen; Fehler stehen in `inference.log`. Der bezahlte Colab-Tarif allein aktiviert CUDA nicht im Programm. Gerätewahl erfolgt ausdrücklich über `--device cuda`.

`CUDA_RUNTIME="auto"` verwendet die geprüften CUDA-12.8-Pakete auf kompatiblen Systemen. Diese Pakete benötigen GLIBC 2.38; bei älterer GLIBC wird derselbe Commit `a71c00f0bb2d60a4a52837d80baa534b651ebd91` aus den Quellen gebaut. `CUDA_RUNTIME="source"` erzwingt einen Quellbuild, etwa um auf beiden Karten dieselbe Variante zu verwenden. Außerhalb des Notebooks steuert `STACKLAB_CUDA_RUNTIME=auto|binary|source` diese Wahl. Die aufgelöste Variante steht in der Modellkonfiguration des Versuchs. Quellbuilds prüfen erforderliche Werkzeuge vor dem Gewichtsdownload, zeigen Fortschritt an und halten auch die NVCC-Version fest. Der erste Build kann mehrere Minuten dauern.

## L4 und A100 vergleichen

1. Auf L4 ausführen und die ausgegebene Commit-SHA, Modellwahl, Budgets und Seeds festhalten.
2. Prüfen, dass die ZIP-Sicherung in `MyDrive/LARA-Stack-Lab/experiments` angekommen ist.
3. Eine neue Laufzeit mit A100 auswählen. `REPO_REF` auf dieselbe Commit-SHA setzen und dieselben Modelleinstellungen benutzen.
4. Dasselbe Notebook erneut ausführen und denselben Drive-Ordner wählen. Die letzte Auswertungszelle liest alle Sicherungen und erzeugt `comparison.csv`.

Die Tabelle nennt Hardware, Modell, Blockbudget, Aufgabenfamilie, Erfolge/bewertete/geplante Episoden, technische Ausfälle, offene Versuche, native Tokens/s und mittlere Episodenzeit. Sie weist fehlerhafte Archive aus und mischt unterschiedliche Pläne nicht still zu einer Erfolgsquote. Nur passende Fall-/Bedingungsidentitäten mit gleichem API-, Prompt- und Softwarestand direkt vergleichen. Die tatsächlichen GPU-Daten und Treiber bleiben als Versuchsbedingung sichtbar. GPU-Inferenz verspricht keine bitgleichen Antworten auf anderer Hardware.

Für den Vergleich ist neben Tokens/s die Zeit pro vollständigem Versuch relevant. `COMPUTE_UNITS_PER_HOUR` kann den aktuell in Colab angezeigten Verbrauch aufnehmen. Die Schätzung gilt für die Versuchszelle einschließlich ihrer Sicherungen und ohne vorherige Einrichtung, Downloads und Vorschau. Sie ist keine tatsächliche Google-Abrechnung. Es gibt keine im Code angenommene feste L4-/A100-Preistabelle.

Die ersten Modellversuche sind Entwicklungsdaten. Der Kontrollaufruf `demo` verwendet ein handgeschriebenes Stapelprogramm und prüft die Simulation; das ist kein Erfolg des Modells. Neue Benchmark-Programme stammen unverändert vom Modell. Ein nachgelagertes Fine-Tuning ist noch nicht eingerichtet.

## Ergebnisse sichern

Gewichte und Arbeitsdateien liegen auf der Colab-VM. Ergebnisse werden dort geschrieben und nach jeder beendeten Episode als ZIP nach Drive gesichert, um viele einzelne Schreiboperationen auf Drive zu vermeiden. Bei Strg+C beendet der Runner den Worker und versucht eine Sicherung der Teilprotokolle. Ein hartes Abschalten der VM kann die zuletzt laufende Episode verlieren. Die vorherige fertige ZIP wird erst nach Abschluss der neuen ersetzt. Ein Sicherungsfehler stoppt den Lauf und erhält die vorhandenen lokalen Daten.

`SAVE_TO_DRIVE=False` verwendet nur `/content/lara-backups`; diese Daten vor dem Löschen der Laufzeit selbst herunterladen. Ergebnisse sind nicht automatisch auf GitHub. Mit folgenden Befehlen lassen sich vorhandene lokale Versuche auswerten oder erneut sichern:

```bash
.venv/bin/python -m stacklab experiment report runs/mein-pilot
.venv/bin/python -m stacklab experiment backup runs/mein-pilot --output /content/drive/MyDrive/LARA-Stack-Lab/experiments
```

Ein neuer GPU-Typ, eine andere UUID oder ein anderer Treiber gehört in einen neuen Plan. Vorhandene Episoden werden bei einer Fortsetzung nicht überschrieben. Szenen- und Generierungsseeds bleiben unabhängig. Die vollständige Episodenidentität ist `(plan_sha256, episode_id)`.

## Ohne Notebook verwenden

Auf einer Linux-x86-64-Maschine mit NVIDIA-GPU:

```bash
.venv/bin/python -m stacklab setup --model granite8b --device cuda
.venv/bin/python -m stacklab doctor --model granite8b --device cuda
.venv/bin/python -m stacklab chat --model granite8b --device cuda --headless --prompt "Bewege den Greifer 5 cm nach rechts."
.venv/bin/python -m stacklab benchmark --model granite8b --device cuda --case move-right
.venv/bin/python -m stacklab experiment plan --output runs/gpu-pilot --models granite8b --device cuda --blocks 1 4
.venv/bin/python -m stacklab experiment run runs/gpu-pilot --backup-dir /content/drive/MyDrive/LARA-Stack-Lab/experiments
```

Ohne `--device` bleibt CPU der Standard. Chat und Benchmark zeigen weiterhin native Tokens/s und Ladezeit. GPU-/Offloading-Diagnosen liegen neben `inference.log` in `device.json` und in den Generierungsmetadaten. Der Experimentbericht speichert Gerätewahl, GPU und Treiber auch in CSV. CUDA ist derzeit auf Linux x86-64 begrenzt; die bisher unterstützten CPU-Plattformen bleiben erhalten.

### Dory

Dory verwendet auch unter CUDA seinen separaten Quellbuild. Neben Git/CMake/C++ wird das CUDA Toolkit mit `nvcc` benötigt. Die beiden Zielarchitekturen sind SM 80 (A100) und SM 89 (L4). Zwei parallele Buildprozesse begrenzen den Speicherbedarf. Der erste Build dauert länger; ein unveränderter Build wird anschließend wiederverwendet. Die erforderlichen Werkzeuge stehen normalerweise in einer Colab-GPU-Laufzeit bereit; fehlende Werkzeuge werden ausdrücklich gemeldet.

## Prüfstand

Softwaretests prüfen Gerätewahl, unveränderte Gewichte, Paket-/Binärhashes, CUDA- und Offloading-Prüfungen, GLIBC-Auswahl, Quellenbuild-Konfiguration, Notebook-Syntax sowie Sicherungen bei Abbrüchen und Schreibfehlern. Die echte CUDA-Paketinstallation wird zusätzlich ohne GPU gestartet; die CI kompiliert den normalen und Dorys CUDA-Quellpfad für beide Zielarchitekturen und prüft OSMesa-Video. Das ersetzt keinen Inferenztest auf einer echten L4/A100: Diesen führt das Notebook auf deiner zugeteilten Karte aus. Hier sind keine solchen GPU-Leistungswerte als vorab gemessen eingetragen.

Quellen: [Colab-FAQ](https://research.google.com/colaboratory/faq.html), [llama.cpp b11951 und Paketprüfsummen](https://github.com/ggml-org/llama.cpp/releases/tag/b11951), [Dory-Modellkarte](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-GGUF).
