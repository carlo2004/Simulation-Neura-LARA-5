# Modelle mit denselben Aufgaben vergleichen

Für den automatischen Vergleich **aller Modelle auf Colab mit lokaler Simulation**
gibt es den [Remote-Piloten für L4 und A100](remote-benchmark.md), einschließlich
Modellwechsel, Videoaufzeichnung, Rangliste und GitHub-Release-Upload.

Der `experiment`-Befehl plant mehrere Episoden vorab, führt sie nacheinander ohne Fenster aus und erzeugt eine lesbare Auswertung. Er benutzt dieselbe Inferenz, Python-API und unabhängige Physikprüfung wie `benchmark`. Neue Dienste oder zusätzliche Python-Pakete sind nicht nötig.

Dies ist ein **Entwicklungspilot**. Er richtet noch kein unberührtes Testset und keine Trainingspipeline ein. Insbesondere ist ein erfolgreiches Bewegungsprogramm kein Beleg für zuverlässiges Stapeln.

## Einrichten und starten

Nach einem Update `python bootstrap.py --test` ausführen. Danach den Interpreter aus `.venv` benutzen. Die Beispiele zeigen Windows PowerShell; auf Linux/macOS stattdessen `.venv/bin/python` verwenden.

Zunächst die gewünschten Modelle installieren:

```powershell
.\.venv\Scripts\python.exe -m stacklab setup --model granite8b
.\.venv\Scripts\python.exe -m stacklab setup --model lfm2.6b
```

Ein kurzer erster Pilot: zwei Modelle, eine Rechtsbewegung und Rot-auf-Blau, jeweils höchstens ein Programmblock. Das sind vier Episoden:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment plan --output runs/pilot-01 --models granite8b lfm2.6b --cases move-right red-on-blue --blocks 1
.\.venv\Scripts\python.exe -m stacklab experiment run runs/pilot-01
```

Die Tokens/s erscheinen während jeder Generierung automatisch. Ein Rückgabecode `1` bedeutet, dass nicht alle geplanten Episoden physisch erfolgreich waren; Modellfehler sind erwartbare Versuchsergebnisse. Ein Plan-/Einrichtungsfehler liefert `2`, ein Abbruch mit Strg+C `130`.

Für den Vergleich von einem gegen bis zu vier Blöcke denselben Planungsbefehl mit einem **neuen** Ergebnisordner und `--blocks 1 4` ausführen. Weitere Startvarianten und Generierungen:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment plan --output runs/pilot-02 --models granite8b lfm2.6b --cases blue-on-red green-on-blue --scene-seeds 42 43 --generation-seeds 42 43 --blocks 1 4
```

Das ergibt 32 Episoden. Bei `blue-on-red` und `green-on-blue` verändern Szenenseeds die anfänglichen Würfelpositionen. Die bisherigen Fälle `move-right` und `red-on-blue` haben keinen Positions-Jitter; verschiedene Szenenseeds machen diese Startlagen nicht physisch verschieden. Generierungsseed und Szenenseed sind unabhängig. Innerhalb einer Episode nutzt Runde N den Generierungsseed `seed + N - 1`.

`plan --help` zeigt die verfügbaren Optionen für Tokens, Thinking-Budget, Threads und Zeitlimits. Ohne Overrides bleiben modellabhängige Thinking-/Sampling-/Antwortformatprofile erhalten und werden vollständig gespeichert. LFM verwendet zum Beispiel seine deklarierte JSON-Antworthülle. Solche Modellvergleiche sind keine reine Ablation der Gewichte. Für Basismodell gegen Fine-Tuning müssen die übrigen Bedingungen übereinstimmen; spätere Modelle lassen sich über den bestehenden Modellkatalog ergänzen.

## Ergebnisse lesen

Direkt im Ergebnisordner öffnen:

| Datei | Inhalt |
|---|---|
| `manifest.json` | Versionierter Plan mit Fällen, Bedingungen, Episoden-IDs und SHA-256 des Plans |
| `runtime-verification.json` | Vor dem ersten Versuch überprüfte Gewichts- und ausführbare Runtime-Hashes |
| `report.md` | Tabelle pro Modell, Blockbudget und Aufgabenfamilie |
| `results.csv` | Eine Zeile pro geplanter Episode, einschließlich offener Versuche |
| `summary.json` | Maschinenlesbare Episoden und Gruppenmetriken |
| `episode-…/manifest.json` | Identität des begonnenen Versuchs und Verweis auf den Plan |
| `episode-…/scene.json`, `result.json`, `execution.json`, `simulation.log` | Aufgelöste Szene, Worker-Ergebnis und Protokoll |
| `episode-…/episode/` | Bisherige kanonische Agentenprotokolle: tatsächliche Requests, Antworten, Streams, Code, Feedback und Physikzustände |

Die Zusammenfassungen können ohne Modellstart neu erzeugt werden:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment report runs/pilot-01
```

Die vollständige Episodenidentität ist `(plan_sha256, episode_id)`. Beim Zusammenführen mehrerer CSV-Dateien das jeweilige Planmanifest mitführen; `episode_id` allein ist kein experimentübergreifender Primärschlüssel. Während eines aktiven `run` die laufend erzeugten Berichte lesen; `report` nach dessen Ende aufrufen, damit nur ein Prozess die Zusammenfassungen schreibt.

Die Tabelle zeigt **Erfolge / bewertete Episoden / geplante Episoden**. Modellfehler, ungültige Programme und aktive Generierungsbudgets zählen als Misserfolg. Ein Modell, das `done=true` meldet, hat damit noch keinen physischen Erfolg. Infrastrukturfehler und Abbrüche werden gesondert ausgewiesen. Offene oder technisch fehlgeschlagene Versuche verschwinden nicht aus dem geplanten Nenner. `goal_success` bleibt bei diesen nicht bewertbaren Episoden leer beziehungsweise `null`.

Tokenraten entstehen aus passenden nativen Decode-Zählern und Decode-Zeiten, nicht aus dem Mittelwert einzelner Raten. Ausgabe umfasst vorhandene Thinking-Tokens. CSV enthält Lade-, Inferenz-, Ausführungs- und Prüfzeiten getrennt, soweit gemessen; fehlende Messwerte bleiben leer. Ein neuer Runtime-Prozess wird pro Episode gestartet, der Dateicache des Betriebssystems aber nicht geleert. Deshalb keine Behauptung einer normierten Kaltstartmessung. Details zur [Tokenmessung](models.md).

## Abbrechen, fortsetzen und Bedingungen ändern

Strg+C unterbricht den laufenden Worker und erhält seine vorhandenen Dateien. Derselbe `run`-Befehl führt später nur **noch nicht begonnene** Episoden aus. Eine begonnene Episode ohne vollständiges Ergebnis bleibt `incomplete`; sie wird nicht still neu gestartet. Auch bereits dokumentierte Modell- oder Technikfehler werden nicht automatisch wiederholt. Für eine Wiederholung einen neuen Plan erzeugen und die Wiederholung in der späteren Analyse kenntlich machen.

Vor dem ersten Modellstart prüft der Runner die Gewichte per SHA-256 und den lokalen Runtime-Pfad. Für eine Fortsetzung müssen Code, Prompts, Robotergeometrie, Policy-Limits, Python-/Paketstände, Hardwaremerkmale, ausgewählte Modellprofile und Runtime-Binärhash übereinstimmen. Bei geänderten Bedingungen einen neuen Plan anlegen. Absolute Bitgleichheit auf anderer Hardware wird damit nicht versprochen. Die Prüfsummen sind eine Identitätsprüfung, keine Signatur gegen absichtliche Datenmanipulation.

Pro Episode gibt es eine frische Szene und kein vorheriges Modellgedächtnis. Während der Inferenz pausiert die Physik. Modellcode wird nicht repariert. Stabilitätsproben innerhalb einer Episode sind keine unabhängigen Wiederholungen; dieselben Szenen mit mehreren Generierungsseeds bleiben gruppierte Beobachtungen. Der Pilot erstellt bewusst noch keine Unsicherheitsintervalle oder Signifikanztests.

`runs/` ist weiterhin nicht in Git und allein keine dauerhafte Sicherung. Relevante Rohdaten mit Prüfsummen gezielt archivieren; ausgewählte echte Entwicklungsproben stehen im [Versuchsindex](../experiments/README.md). Der weitergehende [Architekturplan](results.md) beschreibt unter anderem den noch offenen gemeinsamen Event-Recorder und den Trainingsdatenexport.

## Kontext und dauerhafte Datenablage

Die [Kontextkonfiguration](context.md) trennt Systemregeln, World Info, Beobachtung,
Budgets, optionale Beispiele und den unveränderten Auftrag. Andere Kontextdateien
oder eine andere Reihenfolge erfordern einen neuen eingefrorenen Plan.

`stacklab experiment publish runs/NAME --dry-run` zeigt den vollständigen Export
ohne Netzwerk. `stacklab experiment publish runs/NAME` lädt ihn nach der lokalen
HF-Anmeldung ins konfigurierte Dataset. `run` und `pilot` unterstützen `--publish`
für den Upload nach Abschluss. GitHub Releases werden dafür nicht mehr verwendet.
[Format, Anmeldung und Wiederherstellung](huggingface.md).
