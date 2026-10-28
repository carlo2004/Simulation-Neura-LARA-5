# Modelle um 8B und Live-Feedback — 28.10.2026

Dies sind tatsächliche Modellantworten und Physikmessungen aus der Entwicklung
von Version 2.6. Keine Antwort wurde nachträglich zu einem funktionierenden
Programm umgeschrieben. Die Softwarekontrollen mit FakeModel sind davon getrennt.

## Finale Live-Probe mit Jog-API

Unter `live_current/` wurden jeweils in derselben Szene zwei Prompts ausgeführt:
5 cm nach rechts, danach 5 cm nach links. Die zweite Aufgabe verwendet den
Endzustand der ersten. Die Messdatei `measured.json` vergleicht unabhängig den
tatsächlichen TCP-Versatz mit `[+0.05, 0, 0]` bzw. `[-0.05, 0, 0]` und 4 mm Toleranz.

| Modell / Modus | Rechts | Links | Gesamtdauer beider Aufgaben |
|---|---|---|---:|
| Qwen3.5-9B, Non-Thinking | bestanden | bestanden | 80,0 s |
| Nemotron Bolt, Non-Thinking | bestanden | fehlgeschlagen, etwa 10 cm statt 5 cm | 73,2 s |
| Ministral 8B Reasoning | bestanden | bestanden | 637,7 s |

Qwen benötigt zwei Blöcke pro Aufgabe, einschließlich der Bestätigung nach dem
Feedback. Ministral benötigt drei bzw. zwei. Bolt beendet die erste Aufgabe nach
drei Blöcken; die zweite erreicht das Vier-Block-Limit. Die Dauer ist eine einzelne
Beobachtung auf dieser CPU und mit unterschiedlichen Modusprofilen, kein
standardisierter Geschwindigkeitstest. Freie Live-Aufgaben behalten im eigentlichen
Agentenbericht `success: null`: ihre Bedeutung wird dort nicht unabhängig bewertet.
Die hier zusätzlich berechnete Bewegungsmetrik ersetzt diese Unterscheidung nicht.

## Vorab festgelegte Bewegungs- und Stapelprüfungen

`motion_and_stack_probes/` enthält die unabhängigen 5-cm-Prüfungen aller drei Modelle:
alle erreichen das Ziel. Die Szene wird pro Modell neu erstellt; es sind andere
Versuche als die obige fortgesetzte Live-Szene. Diese Proben liefen noch vor der
abschließenden Jog-/Formatierungserweiterung. Der dortige Bolt-Stapellauf mit vier
Blöcken schlägt fehl.

`stack_current/` enthält einen weiteren Qwen9B-Non-Thinking-Stapelversuch mit der
finalen Jog-API und vier erlaubten Blöcken: **fehlgeschlagen**, 0/20 gültige
Stabilitätsproben in der letzten Auswertung. Trotz Fehlerfeedback korrigiert das
Modell die unvollständige Greif-/Ablagestrategie nicht ausreichend.

Unter `preflight/` bleiben die vorherigen Versuche erhalten:

- Drei Zwei-Block-Stapelproben: Qwen9B und Ministral mit Reasoning, Bolt ohne.
  Alle drei schlagen fehl. Bolt erzeugt dabei einen echten Kontaktstapel, der
  mit etwa 5,7 mm Zentrierfehler die unveränderte 4-mm-Grenze verfehlt.
- Qwen ohne separates Denkbudget bei 2048 Tokens: abgeschnittene Antwort;
  keine Ausführung. Daraus folgt das explizit dokumentierte Denkbudget.
- Qwen mit 4096 Ausgabetokens und Denkbudget 2048: ebenfalls kein erfolgreicher
  Stapel; die Antwort endet regulär, der Code greift aber nicht auf Würfelhöhe.
- Frühere freie Live-Proben zeigen unerwünschte Zusatzbewegungen und unvollständige
  Abschlussmeldungen. Die Daten bleiben als negative Beispiele erhalten.
- Ein echter interaktiver Terminaldurchlauf prüft Modellwechsel und `/stop` während
  der Generierung: Episode `cancelled`, keine Roboterbewegung. Ein dabei gefundener
  falscher Abschlusstext wurde korrigiert und durch einen Softwaretest abgesichert.

## Software und Versuchsbedingungen

**65/65 Softwaretests bestanden.** Dazu gehören echte MuJoCo-Kontrollen: No-op
scheitert, bekannte Einzelbefehle stapeln mit 20/20, Fehlerfeedback führt über den
gleichen Interpreter zu einer gültigen Bewegung, und ein Modell-`done` kann ein
fehlgeschlagenes unabhängiges Ziel nicht überschreiben. Weitere Tests betreffen
Jog-Invarianten, Unterbrechen innerhalb einer Bewegung, Generierungsabbruch,
Ctrl+C-Protokollierung, SSE, Downloads und wiederholte Live-Prompts. Die bekannten
Kontrollprogramme sind ausschließlich Test-Fixtures und wurden nicht den echten
Modellen als Beispiel mitgegeben.

`setup_verification.txt` dokumentiert den erneut vollständig erfolgreichen
Einrichtungsbefehl für alle vier Gewichte nach der Korrektur der Modellauswahl.
Alle Gewichte wurden nach dem Download und beim abschließenden Setup mit
SHA-256 geprüft. Sie sind nicht Teil dieses Repositorys.

Die API und Beobachtungsdarstellung wurden während der Entwicklung verbessert.
Deshalb werden die unterschiedlichen Bedingungen **nicht zu einer gemeinsamen
Erfolgsquote addiert**. Jede gespeicherte Anfrage enthält den tatsächlich gesendeten
Prompt; die Metadaten enthalten Modellrevision, Hash, Modus, Sampling und Budgets.
Die finale API, gleiche Beobachtung und feste Testbudgets müssen vor dem späteren
Originalmodell-/Finetuning-Vergleich eingefroren werden. Diese Fälle sind ein
Entwicklungspilot, kein zurückgehaltenes wissenschaftliches Testset.

Die Inferenz läuft unter Linux x86_64/Python 3.12.14, acht CPU-Threads, ohne GPU.
Die Physik pausiert im finalen Aufbau während der Inferenz; nur der Hauptthread
bedient MuJoCo. Paket-/Hardwaredaten und Modellprovenienz liegen daneben. Der native
Desktopviewer wurde hier nicht manuell bedient. GitHub Actions prüft separat die
Software auf Linux/Windows und Python 3.12/3.13, ohne mehrgigabytegroße Modellgewichte.

Die originalen SSE-Ereignisdateien und vollständigen Inferenzlogs bleiben lokal unter
`output/`. Hier sind tatsächliche Anfragen/Antworten, Reasoning, Code, Physikzustände,
Trajektorien, Feedback und Ergebnisse versioniert. `checksums.json` enthält die
SHA-256-Werte dieser archivierten Dateien. Finetuning wurde noch nicht ausgeführt.
