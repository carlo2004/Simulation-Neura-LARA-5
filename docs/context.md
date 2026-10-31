# Modellkontext

Ab Protokollversion 3 stehen keine festen Weltkoordinaten, Höhen oder numerischen
Arbeitsgrenzen im [Systemprompt](../config/prompts/robot_api.md). Die bisherige
Transporthöhe und Arbeitsplatzbeschreibung werden beim Laden der Szene als
**World Info** bereitgestellt. Der Nutzerauftrag wird unverändert gespeichert.

| Baustein | Inhalt | Quelle |
|---|---|---|
| `system_prompt` | Verhalten, Python-API und Antwortformat, ohne Zahlenliterale | `config/prompts/robot_api.md` |
| `world_info` | Einheiten, Achsen, Standardabstand, Tischhöhe, TCP-Grenzen, Transporthöhe und Objektgrößen | `config/prompts/world_info.json` und geladene Simulation |
| `observation` | Gemessene aktuelle Positionen, Greifer und Kontakte | Physikbeobachtung |
| `runtime_info` | Block-/Ausführungsbudgets und letzte Aufgaben | Agentenkonfiguration |
| `few_shot` | Optionale Paare aus Eingabe und Musterantwort | `config/prompts/few_shot.json`, derzeit leer |
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
stehen. Jeder Schlüssel muss genau einmal vorkommen; ein leerer Few-Shot-Block
wird bei der Übertragung weggelassen. Es sind keine Musterlösungen voreingestellt.

Die initiale **Systemrolle** bleibt für die nativen Chatvorlagen am Anfang.
Die übrigen Bausteine stehen als getrennt benannte JSON-Felder in einem
Nutzerturn, in der konfigurierten Reihenfolge. Dadurch benötigen etwa
alternierende Chatvorlagen keine erfundenen Assistant-Bestätigungen. Logische
Kontextbausteine und technische Chatrollen sind verschiedene Dinge. Die
Hersteller-Systemanweisung von Ministral bleibt separat dokumentiert und wird
wie bisher von dessen Runtime vor die Systemanweisung gesetzt.

Mit `STACKLAB_CONTEXT_CONFIG` lässt sich eine andere Layoutdatei auswählen.
Ihre Dateiverweise gelten relativ zu ihrem Verzeichnis. Sie wird beim Erzeugen
des Agenten geladen. Eigene Varianten brauchen dieselben Schlüssel wie die
Standarddatei; Few-Shot-Paare besitzen die Textfelder `input` und `solution`.
Beispiele müssen fachlich geprüft werden, bevor sie zum Vergleich hinzukommen.

World Info wird explizit mit dem Kontext gesendet und verbraucht Eingabetokens.
Sie wird weder in die Gewichte geschrieben noch unabhängig vom Kontext unsichtbar
im Modell gespeichert. Der Server kann einen unveränderten Präfix cachen; im
Benchmark bleibt der vorhandene Promptcache-Schalter maßgeblich.

## Nachvollziehen und vergleichen

Jede Aufgabe speichert `context.json` mit Bausteinen, Reihenfolge, Quellhashes und
den zusammengestellten Nachrichten. Pro Generierung bleibt `request.json` die
maßgebliche tatsächlich gesendete Anfrage einschließlich herstellerspezifischer
Ergänzungen. Modellantworten und unabhängige Physikprüfung bleiben getrennt.

Auch extern konfigurierte Promptdateien fließen in die Integritätsprüfung des
Experimentplans ein. Bei einer Änderung von Reihenfolge, Weltbeschreibung oder
Beispielen ist ein **neuer Plan** erforderlich. Alte Ergebnisse werden nicht mit
dem neuen Kontext umgedeutet oder zu einer gemeinsamen Vergleichsquote addiert.
