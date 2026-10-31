# Versuchsindex

Der [Experiment-Runner](../docs/experiments.md) unterstützt eingefrorene Entwicklungsvergleiche und CSV-/JSON-Auswertung. Der [Plan für Ergebnisarchitektur und Vergleichsdesign](../docs/results.md) beschreibt zusätzlich noch offene Ausbauschritte. Beides bleibt von den hier tatsächlich gemessenen Ergebnissen getrennt.

Die ausgewählten **tatsächlich ausgeführten** Entwicklungsversuche liegen jetzt vollständig auf Hugging Face. [Übertragung und feste Revisionen](archive-location.json). Modellcode wurde nicht nachträglich repariert. Test-Fixtures der Software sind getrennt unter `tests/`.

## Modellsupport und Tokenmessung, 29.10.2026

[Erster eingefrorener Pilot](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/blob/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-29/experiment-pilot/README.md): Granite8B und LFM2.6B, jeweils Rechtsbewegung und Rot-auf-Blau mit einem beziehungsweise bis zu vier Blöcken. Bewegung 4/4, Stapeln 0/4. Die acht geplanten Episoden sind vollständig erhalten, einschließlich ungültiger Programme und einer am Tokenbudget abgeschnittenen Generierung. Keine Technikfehler oder ausgeschlossenen Versuche. Gleiche Fälle, aber unterschiedliche native Modellprofile; Entwicklungsprobe, kein allgemeines Qualitäts- oder Geschwindigkeitsranking. [Tabelle](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/blob/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-29/experiment-pilot/report.md) · [CSV](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/blob/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-29/experiment-pilot/results.csv).

[Neue Integrationstests](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/blob/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-29/model-support/README.md): Dory4B, Granite 4.2 8B und LFM2.5-2.6B wurden mit nativen Tokenzählern ausgeführt. Alle drei bestehen einen vorgegebenen Bewegungstest; LFM benötigt eine JSON-Antworthülle. Der vorherige freie Formatfehler und eine unzuverlässig beendete freie LFM-Chatprobe bleiben erhalten. Rohdaten liegen kompakt mit Prüfsummen vor. Dies ist eine Integrationsprüfung, kein standardisierter Modellvergleich.

Der A100-Pilot enthält zusätzlich einen [sechsfachen Stapelvergleich als Endlos-GIF](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/blob/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-29/a100-pilot-stapelvergleich-6-modelle.gif). Er zeigt ausgewählte, tatsächlich aufgezeichnete Fehlversuche nebeneinander; das GIF wurde aus den gespeicherten Posen erzeugt und führt keine Modellanfragen oder neue Bewertungen aus.

## Frühere Entwicklungsproben, 28.10.2026

| Versuch | Bedingungen | Beobachtung |
|---|---|---|
| [Qwen4B-Baseline](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/tree/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-28/local_llm/pilot/) | Drei Stapelfälle, ein Block, Instruct, Seed 42 | 0/3 Erfolge, je 0/20 Stabilitätsproben |
| [Qwen4B mit Thinking](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/tree/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-28/local_llm/thinking/) | Separater Stapelfall, 2048 Ausgabetokens | 0/1 Erfolg |
| [Fortgesetzte Live-Szene](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/tree/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-28/models_8b/live_current/) | Je rechts 5 cm, dann links 5 cm in derselben Szene, Jog-API, vier Blöcke | Qwen9B 2/2; Ministral 2/2; Bolt 1/2 |
| [Vorgegebene Bewegungsziele](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/tree/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-28/models_8b/motion_and_stack_probes/) | Je neue Szene, vor finaler Jog-Erweiterung | Alle drei Modelle bestehen die Rechtsbewegung; zusätzlicher Bolt-Stapelversuch scheitert |
| [Qwen9B-Stapeln](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/tree/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-28/models_8b/stack_current/) | Finale damalige Jog-API, Non-Thinking, vier Blöcke | Fehlschlag, letzte Prüfung 0/20 |

Die Live-Bewegung wird in `live_current/measured.json` separat mit 4 mm TCP-Toleranz gemessen. Die freien Agentenberichte selbst behalten `success: null`. Bolt bewegt sich beim zweiten Prompt ungefähr 10 cm statt 5 cm. Qwen benötigt insgesamt etwa 80 s, Bolt 73 s und Ministral 638 s für die jeweilige Zwei-Prompt-Folge auf der damaligen CPU. Einzellauf, unterschiedliche Modusprofile: kein allgemeiner Geschwindigkeitsvergleich.

API, Prompt und Abschlussprotokoll änderten sich zwischen Entwicklungsphasen. Diese Ergebnisse werden **nicht zu einer gemeinsamen Erfolgsquote addiert**. Die neue Paketversion verändert keine archivierten Messdaten und wurde damit noch nicht erneut an echten Modellen bewertet.

## Reproduzierbarkeit

Das [Manifest](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/blob/0993b4b79f2d98f5b68bc45810a954573989c4b9/legacy/github-40790e3addb6-7ae3ed9e3645/experiments/archive/2026-10-28/manifest.json) nennt Originalpfad, Quellcommit, Git-Blob und SHA-256 jeder übernommenen Rohdatei. Bytes wurden unverändert verschoben. Erhalten sind Anfragen mit tatsächlich gesendeten Prompts, vollständige Antworten einschließlich vorhandenem Reasoning, Generierungsmetadaten, exportierter Code, Szenen, Ergebnisse und bei den Feedback-Versuchen Physikzustände/Trajektorien. Ein Bericht kann dieselben Informationen zusätzlich als Zusammenfassung enthalten.

Umgebung, beobachtete Paketstände und Modellprovenienz stehen jeweils daneben. Die Gewichte sind nicht versioniert. Der API-/Softwarestand ergibt sich aus dem ursprünglichen Commit und der aufgezeichneten Anfrage; aktuelle Dateipfade und Defaults gelten nicht rückwirkend.

## Archivumfang

Entfernt wurden doppelte Klartextkopien von Prompts/Antworten und reine technische Vorversuche. Kanonische JSON-Anfragen und -Antworten bleiben erhalten. Frühere abgeschnittene Antworten, Schema-Experimente, der native Completion-Absturz sowie frühere Stapel-/Abbruchproben sind vollständig im [unveränderten Stand 9e21335](https://github.com/carlo2004/Simulation-Neura-LARA-5/tree/9e21335661a5d267259ad0f6b8069e5a7a533950/test_results) nachlesbar. [Entscheidungen](../docs/history/README.md) fasst ihre Bedeutung zusammen.

Neue Durchläufe schreiben nach `runs/` und werden über die
[HF-Pipeline](../docs/huggingface.md) mit Provenienz und Prüfsummen archiviert.
Neue Rohdaten oder Trainingsläufe nicht in dieses Git-Verzeichnis übernehmen.
Vor dem Originalmodell-/Finetuning-Vergleich API, Budgets, Seeds und unabhängige
Metriken einfrieren und ein getrenntes Testset festlegen. Die Referenzen oben zeigen auf die unabhängig geprüfte, feste HF-Datenrevision.
Neue Team-Läufe werden mit `stacklab share` nach `experiments/` oder `playground/` hochgeladen.
