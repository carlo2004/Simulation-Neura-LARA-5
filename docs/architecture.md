# Struktur und Erweiterung

Eine lokale Simulationsanwendung, ein Python-Paket, wenige direkte Schnittstellen. Die Inferenz kann lokal laufen oder über einen optionalen Modellserver auf einer GPU-Maschine angebunden werden.

## Zuständigkeiten

| Schicht | Verantwortung | Erweiterung |
|---|---|---|
| `sim/robot.py` | MuJoCo-Zustand, Bewegung, Kontakte | Controller oder Roboterdefinition |
| `config.py`, `scenes/` | Daten einer Szene | Neue Szenendatei oder Objektform |
| `llm/catalog.py`, `config/models.lock.json` | Reproduzierbare Modell- und Runtime-Auswahl | Katalogeintrag |
| `llm/runtime.py` | Modell laden, Text streamen, abbrechen | Anderen Inferenz-Client implementieren |
| `llm/remote.py`, `llm/service.py` | Inferenz über SSH-Portforward, native Evidenz, Abbruch | Andere Compute-Maschine mit demselben Protokoll |
| `llm/agent.py` | Sprache → Code → Ausführung → Feedback | Kontext- oder Planungsstrategie |
| `policy.py` | Öffentliche Modellbefehle und Ausführungsbudgets | Fähigkeit an einer Stelle hinzufügen |
| `evaluation.py` | Ziele aus realem Physikzustand prüfen | Neue unabhängig definierte Metrik |
| `cli/` | Argumente, Terminaldarstellung, Prozessgrenzen | Neuer Befehl |

Der Agent erhält den Modell-Client als Objekt; er erzeugt keine konkrete Runtime selbst. Ein anderer Client braucht `config`, `complete(messages, output, **options)` und `cancel()`. Damit lassen sich spätere Finetuning-Backends oder Test-Clients anschließen. Es gibt keine abstrakte Basisklasse ohne aktuellen Nutzen.

`RemoteModel` erfüllt dieselbe Schnittstelle. Der optionale Befehl `serve` betreibt genau einen `LocalModel` und nimmt nacheinander Generierungsanfragen entgegen. NDJSON über eine ausschließlich an Loopback gebundene HTTP-Verbindung überträgt Text, Fortschritt und unveränderte native Streamingdaten. Der Client verwendet dieselbe lokale Roboterausführung und Rückmeldeschleife. Ein verbindungsbezogener Serverbezeichner erkennt Neustarts; Anfragen haben eigene IDs für Abbruch und Protokolle. SSH ist der Transport und die Zugangskontrolle, kein Bestandteil der Physik. [Einrichtung und Datenformat](remote-live.md).

Die Simulation kennt keine Modellnamen. Der Evaluator kennt keine Modellantwort. Ein Modell-`done` gilt bei vorgegebenem Ziel erst dann als Erfolg, wenn die unabhängige Prüfung besteht. Freie Live-Anweisungen haben ohne definierte Metrik `success: null`.

## Daten und Orte

`paths.py` ist die gemeinsame Pfadquelle. `STACKLAB_PROJECT_ROOT` kann einen anderen vollständigen Projektbaum wählen; das normale Setup nutzt die editierbare Installation dieses Checkouts. Ressourcen werden relativ dazu gefunden, nicht relativ zum aktuellen Terminalverzeichnis.

`STACKLAB_MODEL_REGISTRY` erlaubt einen eigenen Modellkatalog. `STACKLAB_CACHE_DIR` und `STACKLAB_RUN_DIR` trennen große Downloads und neue Versuchsergebnisse vom Quellcode. Eine verteilbare Wheel-Datei mit gebündelten Roboterressourcen ist derzeit kein unterstützter Installationsweg.

## Einfach erweitern

1. **Szene:** JSON unter `scenes/` anlegen, mit `console --config …` prüfen. Für zusätzliche Würfel ist kein Python-Umbau nötig.
2. **Modell:** Eintrag im Katalog kopieren, Revision, Gesamtparameterzahl, Dateigröße, SHA-256, Vorlage und Sampling bewusst setzen. Danach `models` und `setup --model …` verwenden.
3. **Modellfähigkeit:** API-Dispatch und Validierung in `policy.py`, Dokumentation in `config/prompts/robot_api.md` und passenden Fähigkeitstest gemeinsam ändern.
4. **Aufgabe:** Bewertungsmetrik in `evaluation.py` und Benchmark-Fall ergänzen. Die Zieldefinition stammt vom Versuchsaufbau.
5. **Neues Backend:** Client mit derselben kleinen Schnittstelle übergeben. Die Agententests verwenden bereits solche Clients.

Arbeitsraum- und Kontaktprüfungen hängen an realer Geometrie. Ressourcenbudgets begrenzen Laufzeit und Speicher; sie sollten im Versuchsaufbau explizit gewählt und im Ergebnis protokolliert werden. Keine versteckte Aufgabenerfüllung durch handgeschriebene Stapelfunktionen in der Modell-API.

## Versionspflege

`stacklab.__version__` ist die Versionsquelle; `pyproject.toml` übernimmt sie. `requirements.txt` ist die Abhängigkeitsquelle für Setup und Paketinstallation. Eingefrorene Paketstände eines alten Experiments gehören zu dessen Archiv, nicht zu einer zweiten Installationsanleitung.

## Budgets anpassen

`config/policy.json` enthält Überschreibungen der Defaults aus `ExecutionLimits`; eine leere Datei mit `{}` verwendet sie unverändert. Zum Beispiel:

```json
{"api_calls": 128, "wait_per_call_s": 10, "wait_total_s": 30}
```

Alternativ `STACKLAB_POLICY_LIMITS` auf eine Versuchskonfiguration setzen oder `Agent(..., policy_limits=ExecutionLimits(...))` übergeben. Die aufgelösten Werte werden jeder Aufgabe mitgegeben und im Ergebnis gespeichert. Die aktuelle Sprache bleibt ein kleiner Interpreter für einzelne Roboteraktionen und Variablen; eigener direkter Python-Code kann die normale Simulations-API verwenden.

Runden, Threads und Timeouts haben keine versteckte obere Produktgrenze. Ausgabetokens müssen zum Modellkontext passen. Der Modellkatalog behält für die Seminar-Auswahl ein 10B-Gesamtparameterbudget; ein anderer Katalog darf dieses Budget ändern oder mit `null` entfernen.
