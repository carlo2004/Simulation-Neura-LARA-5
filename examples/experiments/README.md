# Versuchsindex

Hier liegen ausgewählte **tatsächlich ausgeführte** Entwicklungsversuche vom 28.10.2026. Modellcode wurde nicht nachträglich repariert. Test-Fixtures der Software sind getrennt unter `tests/`.

## Ergebnisse

| Versuch | Bedingungen | Beobachtung |
|---|---|---|
| [Qwen4B-Baseline](archive/2026-10-28/local_llm/pilot/) | Drei Stapelfälle, ein Block, Instruct, Seed 42 | 0/3 Erfolge, je 0/20 Stabilitätsproben |
| [Qwen4B mit Thinking](archive/2026-10-28/local_llm/thinking/) | Separater Stapelfall, 2048 Ausgabetokens | 0/1 Erfolg |
| [Fortgesetzte Live-Szene](archive/2026-10-28/models_8b/live_current/) | Je rechts 5 cm, dann links 5 cm in derselben Szene, Jog-API, vier Blöcke | Qwen9B 2/2; Ministral 2/2; Bolt 1/2 |
| [Vorgegebene Bewegungsziele](archive/2026-10-28/models_8b/motion_and_stack_probes/) | Je neue Szene, vor finaler Jog-Erweiterung | Alle drei Modelle bestehen die Rechtsbewegung; zusätzlicher Bolt-Stapelversuch scheitert |
| [Qwen9B-Stapeln](archive/2026-10-28/models_8b/stack_current/) | Finale damalige Jog-API, Non-Thinking, vier Blöcke | Fehlschlag, letzte Prüfung 0/20 |

Die Live-Bewegung wird in `live_current/measured.json` separat mit 4 mm TCP-Toleranz gemessen. Die freien Agentenberichte selbst behalten `success: null`. Bolt bewegt sich beim zweiten Prompt ungefähr 10 cm statt 5 cm. Qwen benötigt insgesamt etwa 80 s, Bolt 73 s und Ministral 638 s für die jeweilige Zwei-Prompt-Folge auf der damaligen CPU. Einzellauf, unterschiedliche Modusprofile: kein allgemeiner Geschwindigkeitsvergleich.

API, Prompt und Abschlussprotokoll änderten sich zwischen Entwicklungsphasen. Diese Ergebnisse werden **nicht zu einer gemeinsamen Erfolgsquote addiert**. Die neue Paketversion verändert keine archivierten Messdaten und wurde damit noch nicht erneut an echten Modellen bewertet.

## Reproduzierbarkeit

Das [Manifest](archive/2026-10-28/manifest.json) nennt Originalpfad, Quellcommit, Git-Blob und SHA-256 jeder übernommenen Rohdatei. Bytes wurden unverändert verschoben. Erhalten sind Anfragen mit tatsächlich gesendeten Prompts, vollständige Antworten einschließlich vorhandenem Reasoning, Generierungsmetadaten, exportierter Code, Szenen, Ergebnisse und bei den Feedback-Versuchen Physikzustände/Trajektorien. Ein Bericht kann dieselben Informationen zusätzlich als Zusammenfassung enthalten.

Umgebung, beobachtete Paketstände und Modellprovenienz stehen jeweils daneben. Die Gewichte sind nicht versioniert. Der API-/Softwarestand ergibt sich aus dem ursprünglichen Commit und der aufgezeichneten Anfrage; aktuelle Dateipfade und Defaults gelten nicht rückwirkend.

## Archivumfang

Entfernt wurden doppelte Klartextkopien von Prompts/Antworten und reine technische Vorversuche. Kanonische JSON-Anfragen und -Antworten bleiben erhalten. Frühere abgeschnittene Antworten, Schema-Experimente, der native Completion-Absturz sowie frühere Stapel-/Abbruchproben sind vollständig im [unveränderten Stand 9e21335](https://github.com/carlo2004/Simulation-Neura-LARA-5/tree/9e21335661a5d267259ad0f6b8069e5a7a533950/test_results) nachlesbar. [Entscheidungen](../docs/history/README.md) fasst ihre Bedeutung zusammen.

Neue Durchläufe schreiben nach `runs/`. Nur für die Arbeit relevante abgeschlossene Versuche gezielt mit Provenienz übernehmen. Vor dem Originalmodell-/Finetuning-Vergleich API, Budgets, Seeds und unabhängige Metriken einfrieren und ein getrenntes Testset festlegen.
