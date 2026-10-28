# Lokaler LLM-Entwicklungspilot, 28.10.2026

Diese Dateien sind tatsächliche Antworten und Messungen, keine erwarteten
Beispielausgaben. Das Modell ist Qwen3.5-4B als Q4_K_M; Originalrevision,
Parameterzahl, Quantisierungsrevision und SHA-256 stehen im Projekt-Lockfile.

`pilot/` enthält den vollständigen Drei-Fälle-Lauf mit dem finalen API-Prompt,
Qwens Instruct-Samplingprofil, Seed 42, 768 Ausgabetokens, 4096 Kontexttokens und
ohne erzwungene Decoding-Grammatik. Alle drei Programme wurden tatsächlich in
MuJoCo ausgeführt: **0/3 physikalische Erfolge**, jeweils **0/20** erfolgreiche
Stabilitätsproben. Die Programme verwenden feste Koordinaten und lassen die
notwendigen Positionsabfragen bzw. Greif-/Ablageschritte aus.

`thinking/` enthält einen zusätzlich getrennt ausgewerteten Versuch mit Thinking
und 2048 Ausgabetokens: **0/1 erfolgreich, 0/20 Stabilitätsproben**. Hier fragt
das Modell beide Objektpositionen ab, schließt den Greifer aber auf der
Transporthöhe von 24 cm und nimmt den Würfel deshalb nicht auf. Generierung
inklusive Modellstart: 75,3 Sekunden, 842 Ausgabetokens einschließlich Thinking.
Das ist eine eigene Versuchsbedingung, keine Wiederholung mit demselben Budget.

`preflight/` bewahrt die vorherigen Anbindungs- und Konfigurationsversuche auf:

- `manual_chatml/`: rohe ChatML-Promptkonstruktion, Antwort bei 768 Tokens
  unvollständig; keine Ausführung.
- `native_completion_crash/`: llama-completion mit Jinja endete mit Signal 11;
  keine Antwort/Ausführung. Der finale Pfad verwendet stattdessen llama-server.
- `server_greedy/`: funktionierende lokale Serveranbindung, Temperatur 0 und
  JSON-Schema; physikalischer Fehlschlag.
- `schema_instruct/`: drei Fälle mit offiziellem Instruct-Sampling und
  JSON-Schema; 0/3 erfolgreich.
- `schema_thinking/`: Thinking mit JSON-Schema; ungültige Variablenverwendung
  wurde von der API-Ausführung abgelehnt.
- `unconstrained_single/`: einzelner Vorlauf ohne Decoding-Grammatik;
  physikalischer Fehlschlag.

Weder Samplingwechsel noch Weglassen der Grammatik allein haben hier einen
erfolgreichen Stapel ergeben. Diese Vorversuche sind Teil der Entwicklung und
werden nicht als unabhängiger Benchmark zusammengezählt. Prompts und Programme
wurden nach den Modellantworten nicht durch eine funktionierende Lösung ersetzt.
Bei `generated.py` wird lediglich der abschließende Zeilenumbruch normalisiert;
die vollständige Originalantwort steht in `raw_response.txt` / `response.json`.

Die **47/47 Softwaretests** stehen in `unit_tests.txt`. Dazu gehören zwei wichtige
Kontrollen desselben Interpreters und Auswerters: Ein No-op scheitert mit 0/20,
ein bekanntes, ausschließlich aus den erlaubten Einzelbefehlen bestehendes
Kontrollprogramm besteht mit 20/20 und freiem Greifer. Dieses Kontrollprogramm
steht nur im Testcode und wurde dem Modell nicht mitgegeben.

`environment.json` und `requirements_observed.txt` beschreiben den Linux-CPU-Lauf;
`model_provenance.json` enthält den relevanten Ausschnitt der tatsächlichen
Hugging-Face-Metadatenabfrage. Rohlogs des Inferenzprogramms bleiben im lokalen
`output/`; Prompt, Anfrage, Antwort, erzeugter Code, Ausführung und Ergebnisse
werden hier versioniert. `checksums.json` ordnet die archivierten Dateien ihren
Inhaltsprüfsummen zu.

Der native Desktopviewer wurde hier nicht manuell bedient. Die GUI-Option nutzt
den bestehenden Viewer; der physikalische LLM-Test lief ohne Fenster. Aussagen
gelten nur für diese Quantisierung, Prompts, Budgets, Aufgaben und Seeds. Für eine
wissenschaftliche Evaluation müssen neue zurückgehaltene Fälle hinzukommen.
