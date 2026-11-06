# Hersteller-Systemprompt

Der Zero-shot-Kontext trennt den zahlenfreien `robot_api.md`-Systemprompt,
`world_info.json`, dynamische Beobachtungen, Ressourcenbudgets und den Nutzerauftrag.
`context.json` legt Dateiquellen und Blockreihenfolge fest. Jede Aufgabe protokolliert
diese Bausteine und ihre Hashes; die Runtime speichert zusätzlich die tatsächlich
übertragene Anfrage. [Kontextaufbau](../../docs/context.md)

`ministral_system.txt` ist die unveränderte `SYSTEM_PROMPT.txt` aus
`mistralai/Ministral-3-8B-Reasoning-2512`, Revision
`81eaece1948f3875421d9a45bc55487d10e2d894`.

Quelle: https://huggingface.co/mistralai/Ministral-3-8B-Reasoning-2512/blob/81eaece1948f3875421d9a45bc55487d10e2d894/SYSTEM_PROMPT.txt

Die Modellquelle nennt Apache-2.0; der Lizenztext liegt hier bei. Die Hersteller-
Anweisungen werden vor die eigene API-/JSON-Beschreibung gesetzt. Die genaue
tatsächlich gesendete Nachricht wird je Modellaufruf gespeichert. Alle übrigen
API- und Agentenanweisungen stammen aus diesem Projekt.
