# Ergebnisse und Vergleichsdesign

**Ergänzung, 31.10.2026:** Der [Modellkontext](context.md) trennt jetzt Systemregeln,
World Info, Beobachtung, Budgets, optionale Beispiele und Nutzerauftrag. Der
[HF-Export und -Download](huggingface.md) speichert unveränderliche Datenstände
im Dataset-Repository statt neue Rohdaten nach GitHub zu übertragen. Ein
fachlich geprüfter SFT-Export und Fine-Tuning bleiben eigene nächste Schritte.

**Status: teilweise umgesetzt, 29.10.2026.** Der [Experiment-Runner](experiments.md) implementiert eingefrorene Entwicklungspläne, modellunabhängige Fall-IDs, Episoden-/Bedingungs-IDs, getrennte Seeds, mehrere Modelle/Blockbudgets, Wiederaufnahme offener Pläne und CSV-/JSON-/Markdown-Auswertungen. Er verwendet die bestehenden Rohprotokolle; ein gemeinsamer neuer Event-Recorder und Trainingsdatenexport sind weiterhin Vorschläge. Die folgenden Abschnitte unterscheiden heutigen Stand und Zielarchitektur. Frühere Referenz: [9a31361](https://github.com/carlo2004/Simulation-Neura-LARA-5/tree/9a313616c48c7d55fa33a604b77553d4aeaf232d).

## Forschungsfrage und Umfang

Arbeitshypothese aus dem bisherigen Projektziel: Wie verändert aufgabenspezifisches Fine-Tuning die Fähigkeit eines lokal ausführbaren Modells um 8B, korrekte Python-Programme für LARA-Manipulation zu erzeugen? Welchen zusätzlichen Nutzen haben mehrere Codeblöcke mit Ausführungsfeedback?

Die formale Seminaraufgabe, eine eventuell vorgeschriebene Trainingsmethode, Trainingshardware und Abgabetermin sind noch zu klären. Bis dahin ist dies ein vorgeschlagenes Versuchsdesign.

Für den ersten Vergleich ein Modell auswählen, die Roboter-API einfrieren und Basismodell gegen dessen Fine-Tuning vergleichen. Modellwechsel, zusätzliche Skills, Wahrnehmungsmodelle oder neue Controller sind eigene Versuchsbedingungen. Die aktuelle Simulation bleibt der gemeinsame Prüfstand.

## Was heute vorhanden ist

Agent und Runtime speichern bereits tatsächliche Requests, Responses, Code, Feedback, Physikzustände und Ergebnisberichte. Der unabhängige Evaluator prüft echte Kontakte und Stabilität. Modellmeldungen ersetzen keine Prüfung. Freie Chat-Anweisungen ohne vorgegebenes Ziel haben `success: null`.

Der Experiment-Runner ergänzt ein versioniertes Plan-/Berichtsformat, feste Fall-/Episodenidentitäten, getrennte Zufallsseeds und reproduzierbare Mehrfachauswertung. Lade-/Tokenmetriken stammen aus der Runtime; Ausführungs- und Prüfzeiten sind zusätzlich pro Runde erfasst. Es fehlen weiterhin ein einheitlicher Event-Recorder über alle Einstiegspunkte und ein definierter Trainingsdatenexport. Das bisherige `trajectory.jsonl` enthält Agentenereignisse; es ist keine durchgehend abgetastete Gelenk- oder Kontakttrajektorie.

Die bisherigen archivierten Proben sind Entwicklungsdaten. Sie werden nicht nachträglich als unberührtes Testset bezeichnet oder mit neuen Protokollen zusammengefasst.

## Drei Begriffe

| Begriff | Bedeutung |
|---|---|
| Testfall / `case_id` | Festgelegte Anweisung, Ziel und konkrete Startszene; modellunabhängig |
| Episode / `episode_id` | Ein physisch zusammenhängender Versuch dieses Falls unter einer Modell-/Agentenkonfiguration |
| Runde / `turn_id` | Eine Modellgenerierung mit anschließender Ausführung innerhalb dieser Episode |

Mehrere Korrekturrunden bleiben dieselbe Episode. Ein Reset oder ein erneuter gesampelter Versuch erhält eine neue Episode. 20 Stabilitätsproben sind 20 Messpunkte **innerhalb einer Episode**, keine 20 unabhängigen Versuche. Wiederholungen, Varianten und Zufallsseeds werden explizit gezählt.

## Zielarchitektur für den gemeinsamen Recorder

Die folgende Vier-Dateien-Struktur ist noch nicht implementiert. Der aktuelle Experiment-Runner legt ein Planmanifest im Experimentordner sowie ein kleines Identitätsmanifest neben die bestehenden Rohdateien jeder Episode. Die tatsächlichen heutigen Pfade stehen in der [Bedienungsanleitung](experiments.md).

| Pfad innerhalb einer Episode | Rolle |
|---|---|
| `manifest.json` | Vor dem Start eingefrorene Bedingungen und Herkunft |
| `events.jsonl` | Chronologisches Protokoll der tatsächlichen Ein- und Ausgaben |
| `result.json` | Kompakte Abschlussansicht; aus Manifest und Ereignissen ableitbar |
| `artifacts/` | Optionale Bilder, Video, Diagnose- oder Zustandsdateien |

Ablage: `runs/<experiment_id>/<episode_id>/`. Ein Experiment gruppiert dieselbe Vergleichsbedingung auf einer festgelegten Fallliste. Alle Bedingungen einer Studie referenzieren dieselben `case_id`-Werte. IDs sind eindeutig; ein lesbarer Titel darf zusätzlich geändert werden.

Es gibt eine kanonische Darstellung jeder Rohinformation. Exportierte Python-Dateien, CSV-Tabellen und Abbildungen sind Ansichten. Ein Request kann bereits vorheriges Feedback enthalten: der tatsächlich übertragene Kontext wird vollständig erhalten.

Ein kleiner Recorder in einem geplanten Modul `stacklab/results.py` reicht zunächst. Der Runner erzeugt ihn; Agent, Runtime und Ausführung melden ihre Ereignisse. Ein Viewer zeigt diese an, bestimmt aber weder Dateiformat noch Bewertung. Kein neuer Hintergrunddienst ist nötig.

### Manifest

Mindestens speichern:

- Schema-/Protokollversion, Experiment-/Episoden-/Fall-ID, Modus und Split.
- Aufgelöste Szene, Anweisung und extern festgelegtes Ziel; tatsächlicher initialer Physikzustand.
- Softwarecommit, Änderungsstatus, Paket-/Runtimeversionen und relevante Roboter-, Controller- und Szenenparameter beziehungsweise unveränderliche Referenzen mit Hash.
- Modell-ID und Revision, Dateihash, Quantisierung, native Chatvorlage, System-/API-Prompt und vorhandene Skills mit Hash.
- Sampling, Kontext, Thinking-Einstellung, Token-/Block-/Aktions-/Zeitbudgets.
- Getrennte `scene_seed`, `generation_seed` und Wiederholungsnummer; Hardware und Threadzahl.
- Beobachtungsmodus, Variablen-/Gedächtnisumfang und Physikuhr: aktuell genaue Simulationszustände, lokale Variablen pro Block und pausierte Physik während der Generierung.

Für Fine-Tuning zusätzlich Basismodellrevision, Trainingslauf, Dataset-Hash, Adapter-/Checkpoint-Hash und die verwendete Inferenzfassung speichern. Eine bloße Modellbezeichnung wie „Qwen9B“ reicht nicht.

### Ereignisse

Jeder Eintrag enthält `schema_version`, fortlaufende Nummer, Episode/Runde, Ereignistyp, UTC-Zeit, vergangene Laufzeit und Simulationszeit. Typen umfassen Request, Response, ausgewählten Code, API-Aufruf, Beobachtung, Fehler, Bewertung und Abschluss.

Tatsächliche Prompts, rohe Modellantworten einschließlich vorhandenen Reasonings und Tokenverbrauch bleiben erhalten. Code vor der Ausführung unverändert protokollieren; Parser- oder Validierungsfehler gesondert erfassen. Automatisch umgeschriebene Programme wären eine neue Methode und müssten als solche ausgewiesen werden.

Bei großen Daten genügt eine relative Artefaktreferenz mit SHA-256. Für Bilder/Video ist Speicherung optional; für Text, Code und Physikmessungen standardmäßig aktiv.

Ein Schreiber pro Episode vermeidet Konflikte. Parallel laufende Episoden schreiben in getrennte Ordner. Wichtige Ereignisse werden zeitnah geschrieben; ein Absturz darf den vorhandenen Verlauf nicht überschreiben. Ein abgebrochener letzter JSONL-Eintrag wird beim Lesen als unvollständig gemeldet.

### Abschluss und Bewertung

Getrennte Felder verwenden:

- `status`: z. B. abgeschlossen, Budget erschöpft, abgebrochen, Infrastrukturfehler.
- `execution_outcome`: Programm ausführbar, API abgelehnt, Syntaxfehler, Laufzeitfehler.
- `goal_success`: wahr/falsch bei festgelegtem Ziel, sonst `null`.
- `metrics`: physische Fehlermaße, gültige Stabilitätsproben, Greiferfreigabe, Tokens, Runden und Zeiten.
- `model_declared_done`: Behauptung des Modells, unabhängig von `goal_success`.

Bewertungskriterien und Toleranzen werden vor dem Vergleich eingefroren. Kontakte und Zustand stammen aus der Simulation, nicht aus Modelltext. Der Evaluator kann die Physik zum Prüfen weiterschalten; diese Prüfschritte und die simulierte Zeit müssen im Protokoll sichtbar sein.

Das Manifest wird vor dem Start geschrieben, der Abschluss atomar gespeichert. Ein Verlauf ohne Abschluss wird als unvollständig erkannt. Eine spätere Neubewertung bekommt eine eigene Evaluatorversion und Ergebnisdatei; ursprüngliche Messdaten bleiben unverändert. Aufzeichnung und Reproduzierbarkeit bedeuten keine Garantie bitidentischer Physik auf anderer Hardware.

## Erweiterbarkeit und Archivierung

Die Formate haben wenige verpflichtende Kernfelder, eine `schema_version` und erweiterbare Metadaten/Metriken. Neue Objektformen oder Modelle verlangen keine neue Datenbanktabelle. Leser tolerieren zusätzliche Felder und melden unbekannte Versionsstände verständlich.

Anfangs genügen Dateien und eine daraus erzeugte `results.csv`. Bei Bedarf kann SQLite als wiederaufbaubarer Suchindex hinzukommen. W&B/MLflow sind mögliche zusätzliche Exporte, keine Voraussetzung und keine einzige Datenquelle.

In Git gehören Protokolle, Falllisten, Konfigurationen, kleine Zusammenfassungen, Analyseskripte und der Ergebnisindex. Große Rohdaten, Videos und Gewichte gehören in ein dauerhaft gesichertes, versioniertes Archiv mit verlinktem Manifest und Prüfsummen. Der konkrete Gruppen-/Uni-Speicher ist noch auszuwählen. Ein ignorierter lokaler `runs/`-Ordner allein ist keine dauerhafte Sicherung.

Vorhandene Archive bleiben bytegleich erhalten. Ein Legacy-Leser darf sie für die Analyse abbilden und fehlende Metadaten als unbekannt kennzeichnen; er erfindet weder Seeds noch Test-Splits.

## Erster Vergleich

| Bedingung | Modellgewichte | Maximale Programmblöcke je Episode |
|---|---|---:|
| A | Basismodell | 1 |
| B | Basismodell | 4 |
| C | Dasselbe Modell nach Fine-Tuning | 1 |
| D | Dasselbe Modell nach Fine-Tuning | 4 |

A gegen C und B gegen D messen den Trainingseffekt unter jeweils gleichem Agentenbudget. A gegen B und C gegen D messen den Nutzen zusätzlicher Blöcke samt Feedback. Die zusätzliche Rechenzeit wird mitberichtet. Ein Block kann mehrere Roboterbewegungen enthalten; die darunterliegende Bewegungsregelung arbeitet in allen Bedingungen gleich.

Für alle Bedingungen dieselben Startfälle, Prompts, API, Physik, Bewertung und zur Modellfamilie passende festgelegte Sampling-/Quantisierungsbedingungen verwenden. Modellgedächtnis vor jeder Benchmark-Episode leeren. Korrekturrunden verändern den aktuellen Zustand; sie dürfen keinen heimlichen Szenenreset enthalten.

Ein kleiner Entwicklungspilot prüft zuerst Laufzeit und Fehlerarten. Vorschlag für den späteren Hauptvergleich: 30–50 vorab festgelegte Stapelfälle pro Bedingung, soweit Hardware und Zeit dies erlauben. Dieselben Fälle paarweise vergleichen; mehrere Generierungen desselben Falls bleiben als solche gruppiert. Zusätzliche Bewegungs- und handgeschriebene Kontrolltests prüfen den Prüfstand. Ein Dreierturm ist erst ein sinnvoller Zusatz, wenn der Zwei-Würfel-Vergleich steht.

Berichten:

- Physische Erfolge / geplante und tatsächlich ausgeführte Episoden, nach Bedingung und Aufgabenfamilie.
- Gültiger Code, ausführbarer Code und erreichte Ziele getrennt.
- Tokens, Inferenz-/Ausführungs-/Prüfzeit und simulierte Zeit getrennt.
- Fehlerarten und Unsicherheitsintervalle; für Unterschiede eine paarweise Auswertung nach Fall.
- Abbrüche, Infrastrukturprobleme und alle Ausschlussregeln sichtbar.

Syntax-/API-Fehler des Modells und modellbedingte Budgetüberschreitungen zählen als Misserfolg. Technische Ausfälle werden separat dokumentiert und nur nach vorher festgelegter Regel wiederholt. Fehlversuche werden nicht still aus der Erfolgsquote entfernt.

## Trainingsdaten als eigener Export

Rohprotokolle sind kein fertiger Trainingsdatensatz. Vor der Datensammlung Fälle in Training, Entwicklung und Test aufteilen. Varianten derselben Grundszene und Wiederholungen dürfen nicht zufällig über Splits verteilt werden, wenn dadurch fast identische Beispiele in Training und Test landen.

Ein Export wählt gezielt überprüfte Zielantworten aus und speichert Herkunftsepisode, Zielrunde, ursprünglichen Kontext, Filterversion und Split. Fehlgeschlagene frühere Runden können Kontext eines Reparaturbeispiels sein; sie werden nicht automatisch als richtige Zielantwort trainiert. Handgeschriebene Referenzen, Lehrermodell-Ausgaben und echte Antworten des untersuchten Modells sind getrennt gekennzeichnet.

Der Dataset-Export erhält eine eigene Version und einen Hash. Ein Trainingslauf verweist darauf; das später evaluierte Modell verweist wiederum auf diesen Trainingslauf. Das Testset wird weder für Trainingsbeispiele noch für Prompt-/Checkpoint-Auswahl verwendet.

Als erster Trainingsweg erscheint ein SFT-/LoRA-Pilot sinnvoll, sofern die Seminaraufgabe keine andere Methode verlangt. Verfahren und Modellunterstützung müssen zur verfügbaren GPU passen. Das ist eine Arbeitsempfehlung, noch kein nachgewiesenes Ergebnis und keine bereits eingerichtete Trainingspipeline.

## Einordnung von CaP-X

[CaP-X, arXiv v2](https://arxiv.org/html/2603.22435v2), insbesondere Abschnitte 3 und 5, untersucht API-Abstraktion, Ausführungsfeedback und Post-Training. Für uns ist es eine methodische Referenz; der obige Plan ist eine eigene LARA-Adaption.

Die aktuelle Implementierung hat genaue Simulationskoordinaten, eine begrenzte API, linearen Modellcode und Variablen pro Block. Diese Bedingungen müssen sichtbar bleiben. Sie entsprechen keinem unverändert übernommenen CaP-Bench-Tier. Kamerawahrnehmung, allgemeinere Python-Programme, automatisch erzeugte Skillbibliotheken oder andere Controller wären gesondert versionierte Erweiterungen.

Eine Erweiterung der API oder des erlaubten Python-Umfangs sollte vor einem Hauptvergleich geschehen oder danach als eigene Ablation. Eine bequemere Aufgabe ist kein Beleg für ein intelligenteres Modell.

Weitere Primärquellen: [veröffentlichter CaP-X-Code](https://github.com/capgym/cap-x), [CaP-RL-Einrichtung](https://github.com/capgym/cap-x/blob/main/docs/rl-training.md), [PEFT-Dokumentation zu quantisierten LoRA-Modellen](https://huggingface.co/docs/peft/main/en/developer_guides/quantization).
