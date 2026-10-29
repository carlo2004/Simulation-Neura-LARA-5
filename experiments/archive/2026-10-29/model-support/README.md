# Neue Modelle und native Tokenmessung — 29.10.2026

Tatsächlich ausgeführte CPU-Integrationstests. Dies ist kein zurückgehaltenes Testset und kein standardisierter Geschwindigkeitsvergleich. Gewichte wurden über ihre gepinnten Herstellerrevisionen heruntergeladen und mit SHA-256 geprüft. Dory verwendet den gepinnten separaten CPU-Quellbuild mit zwei Loops; die übrigen Modelle llama.cpp b11951.

| Bedingung | Beobachtung |
|---|---|
| Dory4B, freie Antwort | 5 cm nach rechts, unabhängiges Bewegungsziel bestanden; Modell meldet done=true |
| Granite 4.2 8B, freie Antwort | Gleiches Bewegungsziel bestanden; Modell meldet done=true |
| LFM2.5-2.6B, freie Antwort | Native Tool-Syntax statt gültigem Python; zwei Blöcke, kein Zielerfolg |
| LFM2.5-2.6B, JSON-Antworthülle | Bewegungsziel nach dem ersten Block bestanden; das Modell selbst meldet done=false |
| LFM2.5-2.6B, freier Terminalchat mit JSON-Hülle | Anzeige funktioniert; Modell wiederholt die Bewegung bis zum Blockbudget, insgesamt etwa 20 statt 5 cm |

Das JSON-Schema beschränkt ausschließlich die äußere Antwort mit einem frei erzeugten Code-String und done. Es enthält kein Kontrollprogramm, keine Zielkoordinate und keine Stapelstrategie. Modellcode wurde nicht nachträglich repariert. Das Profil wird im Modellkatalog und den tatsächlichen Requests ausgewiesen.

Der Benchmark stoppt bei einem unabhängig erfüllten vorgegebenen Ziel. Der freie Live-Chat hat keinen extern festgelegten semantischen Grader und behält success=null. Deshalb sind die beiden LFM-Ergebnisse verschiedene Aussagen: Bewegung möglich, autonome Beendigung in dieser Probe unzuverlässig. Es wurden keine Stapelfähigkeiten oder allgemeinen Erfolgsquoten nachgewiesen.

Die Proben entstanden während der Entwicklung; ihre Softwaremetadaten kennzeichnen den damaligen Arbeitsbaum ausdrücklich als verändert. Physik, Evaluator und Modell-API-Prompt waren gegenüber dem aufgezeichneten Basiscommit unverändert. Die hier genannten Geschwindigkeiten sind keine Zusage für andere Rechner, Promptlängen, Thinking-/Loop-Einstellungen oder Cachezustände.

[summary.json](summary.json) enthält die gemessenen Zustände, Statuswerte und Geschwindigkeiten. [raw-evidence.zip](raw-evidence.zip) bewahrt die tatsächlich gespeicherten Requests, Responses, SSE-Tokenzähler, Programme, Physikzustände und Logs in ihrer ursprünglichen Bytefolge. [manifest.json](manifest.json) nennt die SHA-256 des Archivs und jeder enthaltenen Datei. Modellgewichte und Runtime-Binärdateien sind nicht enthalten.

Die Rohdaten bewahren auch die frühe Metrikversion: Deren Episodensumme zählte zunächst das erste, schon beim Prompt berechnete Token zum Decode-Zähler. Die abgeleitete Zusammenfassung verwendet den korrigierten Summierer aus Schema 2 und entspricht den unveränderten nativen Tokenraten der einzelnen Blöcke. Ursprüngliche Requests, Responses und Berichte wurden nicht nachträglich umgeschrieben.

Die Anzeige verwendet native Token-/Zeitdaten und zählt auch verborgenes Reasoning. Die lokale Suite und zusätzliche Messungstests bestanden; die GitHub-Actions-Läufe prüfen Linux/Windows und den zusätzlichen Windows-Quellbuild separat. Eine native Desktop-GUI wurde hier nicht manuell geprüft; der Live-Terminalpfad wurde mit einem echten Modell im Headless-Modus bedient.
