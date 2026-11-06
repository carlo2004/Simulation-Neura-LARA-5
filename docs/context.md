# Modellkontext

Chat und Benchmarks starten Zero-shot. Der Systemprompt beschreibt die API und
das Antwortformat. Die geladene Szene liefert Koordinaten, Arbeitsgrenzen und
Transporthöhe als **World Info**. [Systemprompt](../config/prompts/robot_api.md)

| Baustein | Inhalt | Quelle |
|---|---|---|
| `system_prompt` | Verhalten, Python-API und Antwortformat, ohne Zahlenliterale | `config/prompts/robot_api.md` |
| `world_info` | Einheiten, Achsen, Standardabstand, Tischhöhe, TCP-Grenzen, Transporthöhe und Objektgrößen | `config/prompts/world_info.json` und geladene Simulation |
| `observation` | Gemessene aktuelle Positionen, Greifer und Kontakte | Physikbeobachtung |
| `runtime_info` | Block-/Ausführungsbudgets und letzte Aufgaben | Agentenkonfiguration |
| `user_prompt` | Der eigentliche Auftrag | Nutzereingabe oder eingefrorener Testfall |

Zahlen in einer eigenen Anweisung, etwa eine gewünschte Bewegungsstrecke, bleiben
erhalten. Die Trennung entfernt automatisch hinzugefügte Weltangaben aus dem
Auftrag; sie verwirft keine vom Nutzer angeforderten Größen.

Die tatsächliche Tischhöhe stammt aus dem geladenen MuJoCo-Modell. Die TCP-Grenzen
verwenden dieselbe Definition wie die Ausführungsprüfung; die Transporthöhe kommt
aus der Szene. So bleibt ein Wechsel von Szene oder Höhe nachvollziehbar.

## Reihenfolge einstellen

[`config/prompts/context.json`](../config/prompts/context.json) bestimmt die
Reihenfolge der Kontextblöcke. Beispielsweise kann `user_prompt` vor `world_info`
stehen. Jeder der vier Nutzerblöcke muss genau einmal vorkommen.

Die initiale **Systemrolle** bleibt für die nativen Chatvorlagen am Anfang.
Die übrigen Bausteine stehen als getrennt benannte JSON-Felder in einem
Nutzerturn, in der konfigurierten Reihenfolge. Dadurch benötigen etwa
alternierende Chatvorlagen keine erfundenen Assistant-Bestätigungen. Logische
Kontextbausteine und technische Chatrollen sind verschiedene Dinge. Die
Hersteller-Systemanweisung von Ministral bleibt separat dokumentiert und wird
wie bisher von dessen Runtime vor die Systemanweisung gesetzt.

Mit `STACKLAB_CONTEXT_CONFIG` lässt sich eine andere Layoutdatei auswählen.
Der Agent lädt die Datei beim Start und löst ihre Dateiverweise relativ zu ihrem
Verzeichnis auf. Eigene Varianten verwenden `schema_version: 2` und dieselben
Schlüssel wie die Standarddatei.

World Info wird explizit mit dem Kontext gesendet und verbraucht Eingabetokens.
Sie wird weder in die Gewichte geschrieben noch unabhängig vom Kontext unsichtbar
im Modell gespeichert. Der Server kann einen unveränderten Präfix cachen; im
Benchmark bleibt der vorhandene Promptcache-Schalter maßgeblich.

## Nachvollziehen und vergleichen

Jede Aufgabe speichert `context.json` mit `prompt_mode: "zero_shot"`, Bausteinen,
Reihenfolge, Quellhashes und den zusammengestellten Nachrichten. Folgerunden
erhalten Rückmeldungen aus der Physikausführung desselben Versuchs.
Pro Generierung bleibt `request.json` die
maßgebliche tatsächlich gesendete Anfrage einschließlich herstellerspezifischer
Ergänzungen. Modellantworten und unabhängige Physikprüfung bleiben getrennt.

Auch extern konfigurierte Promptdateien fließen in die Integritätsprüfung des
Experimentplans ein. Bei einer Änderung von Reihenfolge, Weltbeschreibung oder
Systemprompt ist ein **neuer Plan** erforderlich. Alte Ergebnisse werden nicht mit
dem neuen Kontext umgedeutet oder zu einer gemeinsamen Vergleichsquote addiert.
