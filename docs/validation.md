# Prüfen und auswerten

## Software und Physik

```bash
python bootstrap.py --test
.venv/bin/python tools/validate.py
.venv/bin/python tools/validate_objects.py
.venv/bin/python tools/validate_controls.py
```

Die Tests prüfen Modellkinematik, echte Kontakte und Stabilität, Objektbearbeitung, Terminalbefehle, manuelle Steuerung, Overlays, Codevalidierung, Downloads, Streaming und Abbrüche. Ein bekanntes Kontrollprogramm wird durch denselben Interpreter ausgeführt wie Modellcode: es muss stapeln; ein No-op muss die Stapelprüfung verfehlen.

GitHub Actions prüft Linux und Windows mit Python 3.12/3.13. Die Linux-Prüfung führt zusätzlich die Physik-Szenarien aus. Große Modellgewichte werden dabei nicht heruntergeladen. Ein grüner Testlauf prüft die Software, keine neue Modellqualität.

Optionales Rendering benötigt OpenGL, z. B. `MUJOCO_GL=egl` auf einem passenden Linux-System. Native Fenster müssen zusätzlich auf dem Vorführrechner angesehen werden; Headless-Tests prüfen keine Desktopbedienung.

## Auswertung

Beim Stapeln werden Zentrierung, Höhe, Kontakte, Geschwindigkeiten und Freigabe durch den Greifer geprüft. Die Evaluation verlangt 20 gültige Stabilitätsproben. Die detaillierten aktuellen Kriterien stehen in `evaluation.py` und `sim/robot.py`; [historische Messungen](../experiments/README.md) nennen die damaligen Bedingungen.

Ein Agentenbericht mit `success: null` bedeutet: eine freie Anweisung wurde nicht semantisch durch ein vorgegebenes Ziel bewertet. `model_finished` ist eine Modellmeldung. Nur `verified_success` bezeichnet einen bestandenen vorgegebenen physikalischen Test.

Neue Ergebnisse unter `runs/` werden nicht automatisch in Git aufgenommen. Relevante Versuche mit `stacklab share` auf HF teilen; Konfiguration, Softwarestand, Prompt, Modellrevision, Antwort und unabhängige Messung bleiben im Snapshot erhalten. Geplante Serien und Playground werden getrennt abgelegt. Für einen Paper-Vergleich dieselbe API, Seeds, Budgets, Sampling-Profile und Metriken einfrieren. Unterschiedliche Entwicklungsbedingungen nicht zu einer gemeinsamen Erfolgsquote mischen.

Neue Agentenberichte enthalten Softwareversion, verfügbaren Git-Commit und Änderungsstatus, Python-/Systemangaben und die wirksamen Ausführungsbudgets. Fehlen Git oder Repositorymetadaten, bleiben die entsprechenden Felder `null`; die Simulation funktioniert weiter.
