# Entscheidungen und Migration

## Warum diese Struktur

Version 2.6 bündelte Startskripte, Physik, Modellversuche und viele technische Zwischenläufe im Projektstamm. Version 3 führt ein normales Python-Paket ein. Dateien werden nach Verantwortung gefunden; Nutzungsanleitungen beschreiben den aktuellen Stand, Versuchsarchive ihren tatsächlichen historischen Stand.

| Bisher | Jetzt |
|---|---|
| `python run.py` | `python -m stacklab demo` |
| `python console.py` | `python -m stacklab console` |
| `python llm_chat.py` | `python -m stacklab chat` |
| `python llm_test.py models` | `python -m stacklab models` |
| `python llm_test.py setup` | `python -m stacklab setup` |
| `python llm_test.py test` | `python -m stacklab benchmark` |
| `python check_env.py` | `python -m stacklab doctor` |
| `from simulation import Simulation` | `from stacklab.sim.robot import Simulation` |
| `from core import Config` | `from stacklab.config import Config` |
| `scenario.json` | `scenes/default.json` |
| `models/lara5/`, `source/` | `assets/robots/lara5/`, `assets/sources/` |
| `local_model.lock.json`, `LLM_API.md` | `config/models.lock.json`, `config/prompts/robot_api.md` |
| `output/` | `runs/` für neue Standardausgaben |

Nach einem Update einmal `python bootstrap.py --test` ausführen. Der bisherige Modellcache wird weiterverwendet; es gibt keinen automatischen erneuten Download aller Gewichte. Alte eigene Mesh-Szenen mit `models/objects/` werden auf den neuen Asset-Pfad abgebildet; das eigene erzeugte Mesh-Verzeichnis entsprechend nach `assets/objects/` verschieben oder die Quelle neu importieren.

## Behaltene Entscheidungen

- Python und MuJoCo erlauben dieselbe Sprache für Modellprogramme und Simulationssteuerung. Die spezifische LARA-Kinematik wurde aus der vorhandenen RoboDK-Quelle übernommen; selbst angenommene Dynamik bleibt als solche erkennbar.
- Ein vorgegebener Roboterprogramm-Kontrolltest trennt Fehler der Simulationsumgebung von Modellfehlern.
- Der lokale llama.cpp-Server ersetzte einen frühen nativen Completion-Pfad nach einem Absturz. Die temporäre Loopback-Verbindung ist eine lokale Prozessschnittstelle, kein externer Modelldienst.
- Die erste 4B-Baseline scheiterte beim Stapeln. Die späteren 8B-/9B-Modelle verbesserten einfache Bewegungen, belegen bisher aber keine zuverlässige Stapelstrategie.
- API und Abschlussprotokoll wurden während der Entwicklung verändert. Historische Ergebnisse dürfen deshalb nicht als Versuche mit der neuen Version interpretiert werden.

[Historischer Modellguide](model-guide-v2.md) und [historischer Prüfbericht](validation-v2.md) erklären alte Bedingungen. Die ausgewählten kanonischen Daten stehen unter [experiments](../../experiments/README.md).

## Entfernte Relikte

Redundante Promptkopien, doppelte Antwortdarstellungen und technische Vorversuche liegen nicht mehr in der aktuellen Projektansicht. Die vollständige ursprüngliche Sammlung bleibt unverändert im [Stand 9e21335](https://github.com/carlo2004/Simulation-Neura-LARA-5/tree/9e21335661a5d267259ad0f6b8069e5a7a533950/test_results). Die Git-Historie wird nicht umgeschrieben. Das Archivmanifest benennt den ursprünglichen Pfad jeder übernommenen Datei.
