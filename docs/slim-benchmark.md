# Schlanker Benchmark und einfache Sichtung

Ab Version 3.6 ist `experiment pilot` standardmäßig **schlank**. Aufgaben und
physikalische Erfolgskriterien bleiben gleich; der günstige Erstvergleich nutzt
einen Programmblock pro Episode. Zusätzliche Darstellung, Feedbackblöcke und
ausführliche Transportdiagnostik sind Optionen.

## Was im normalen Lauf nötig ist

| Behalten | Warum |
|---|---|
| Eingefrorener Plan mit Szene, Seeds, Modellen, Budgets und Software-/Hardwarestand | Vergleich und Wiederholbarkeit |
| Tatsächliche Eingaben, vollständige Antwort und erzeugter Code | Fehleranalyse und späterer Trainingsdatenexport |
| Aktionen, Rückmeldungen, Anfangs-/Endzustände und gemessene Zielprüfung | Nachvollziehbarer Erfolg oder Misserfolg |
| Native Tokenzähler und Zeiten | Tempo, Prompt-Verarbeitung, erstes Token, Generierung und Ausführung trennen |
| Kleine Bewegungsaufzeichnung mit 10 Hz | Ausgewählte Videos später ohne erneute Modellanfrage erzeugen |

Die fertige Antwort enthält auch vorhandenen, vom Modell ausgegebenen Denktext.
Dieser wird einmal als Teil der Antwort gesichert, nicht zusätzlich pro Token.
Die HTML-Seite zeigt ihn nur mit `--include-reasoning`. Er ist eine Modellausgabe,
keine verifizierte Erklärung des tatsächlichen Lösungsprozesses.

## Was standardmäßig entfällt

- Kein 3D-Fenster, kein Overlay und kein laufendes Video-Encoding während der Versuche.
- Keine rein visuellen Roboternetze im kopflosen Physikmodell; Massen, Trägheiten und Kollisionskörper bleiben erhalten.
- Keine doppelten Token-/Transportstreams und keine zweite Kopie derselben Generierungsmetadaten.
- Keine Ausgabe jedes ungenutzten Denk-/Antworttokens an die Terminal-Warteschlange.
- Keine laufende lokale Webanwendung, Datenbank, UI-Bibliothek oder zusätzlicher LLM-Bewerter.

Die unverzichtbaren drei Dateien pro Generierung bleiben `request.json`,
`response.json`, `generation.json`; dazu kommen kompakte Server-/Transportdaten.
Ein Verbindungsabbruch erhält den bereits empfangenen Antwortteil und eine
entsprechend gekennzeichnete Teilmessung. Ladezeit und Aufwärmversuch bleiben
weiterhin getrennt von den gewerteten Episoden.

Die größeren Unterschiede beim Ressourcenbedarf entstehen durch ausgelassene
Render-/Videoarbeit, ausgelassene Darstellungsnetze und weniger Stream-I/O. Die eigentliche Inferenz, Roboter-IK
und Kontaktphysik sind weiterhin erforderlich. Es wird kein pauschaler
Beschleunigungsfaktor für deinen Rechner versprochen.

## Automatisch prüfen oder händisch ansehen?

| Automatisch und unverändert | Anschließend händisch |
|---|---|
| Zielabweichung einer Bewegung | Verständlichkeit und Sinn des erzeugten Programms |
| Echte Kontakte, Ausrichtung, Höhe, Unterstützung und freier Greifer | Ursache eines falschen Griffs oder einer falschen Bewegungsfolge |
| 20 Stabilitätsproben über zwei Simulationssekunden | Grenzfälle, unerwartete Kontakte oder erkennbare Modellierungsprobleme |
| Format-/API-/Ausführungsfehler, Budgets und technische Ausfälle | Beispielvideos von Erfolg, Misserfolg und auffällig langen Versuchen |

Die Stabilitätsprüfung wird nicht durch ein Bild oder eine Modell-Fertigmeldung
ersetzt. Die 20 Proben zählen weiterhin als **eine** Episode. Ein zweites LLM
bewertet die Versuche nicht. Vermutete Fehlerursachen werden bei der Sichtung von
gemessenen Befunden getrennt.

## Start und Optionen

Den bestehenden Benchmarkserver nach dem Update erneut starten. Lokal reicht:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment pilot --server-url http://127.0.0.1:8765 --output runs/l4-slim
```

Das sind weiterhin 70 Episoden: alle sieben Modelle, fünf Bewegungs- und fünf
Stapelversuche je Modell. Auf A100 mit denselben Optionen und `runs/a100-slim`
wiederholen. [Server, GitHub-Upload und vollständiger Ablauf](remote-benchmark.md).

| Option | Auswirkung |
|---|---|
| Standard: `--recording slim` | Kerndaten, kompakte Konsole, Bewegungszustände, keine sofortigen Videos |
| Standard: `--blocks 1` | Zehn gewertete Episoden entsprechen zehn Anfragen je Modell, plus einem kurzen Aufwärmversuch |
| `--blocks 4` | Separater Versuch mit bis zu vier Blöcken und tatsächlichem Ausführungsfeedback |
| `--gui` | Lokale Simulation live ansehen; kostet zusätzliche Darstellungsarbeit |
| `--video` | Video sofort während jedes Versuchs erzeugen |
| `--recording full` | Ausführliche Streams und standardmäßig sofortige Videos |
| `--motion-fps 5` | Noch kleinere Bewegungsaufzeichnung mit fünf Posen pro Simulationssekunde |
| `--motion-fps 0` | Keine Bewegungsaufzeichnung; nachträgliches Video dann nicht möglich |

Die Aufzeichnungs-, GUI- und Videooptionen müssen auf L4 und A100 gleich sein,
damit der automatische Vergleich die Läufe zusammenführt. Bereits angelegte Pläne
behalten ihre eingefrorenen Einstellungen.

Modellspezifisches Thinking und Sampling bleiben dokumentierte Versuchsbedingungen.
Das Ausblenden von Denktext spart Anzeige-/Protokollarbeit, schaltet aber nicht
die modellinterne Generierung dieser Tokens ab.

## Benutzerfreundliche Sichtung

Nach dem Lauf liegt `review.html` im Ergebnisordner. Die Datei lokal im Browser
öffnen. Sie benötigt keinen Colab-Server und keine Internetverbindung. Sie bietet:

- Auftrag, Ergebnisstatus und nach Modell filterbare Versuche.
- Erstes Token, native Tokenrate, Anfrage-, Prompt-, Ausgabe-, Ausführungs- und Prüfzeit.
- Aufklappbare Antwort, tatsächlich geprüften Code, Eingaben und Messwerte.
- Optional echte Modellausgabe zum Denkprozess; keine nachträglich erfundene Erklärung.
- Vorhandene Videos mit Bedienelementen; sie laden erst beim Abspielen und pausieren andere Clips.

Erneut erzeugen und den gelieferten Denktext aufnehmen:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment review runs/l4-slim --include-reasoning
```

Im normalen Benchmark-Terminal bleiben Fortschritt, Programmblock, gemessene
Tokenraten, Zeit und Physikrückmeldung sichtbar. Code und Antwort stehen vollständig
im Bericht; einzelne API-Aktionszeilen werden im schlanken Modus nicht nochmals
ausgedruckt. Die bestehenden Live-Chat-Optionen `--stream` und `--show-thinking`
bleiben für interaktives Arbeiten verfügbar.

## Videos erst bei Bedarf erzeugen

Bis zu drei Beispielclips lokal aus den gespeicherten Posen erzeugen:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment review runs/l4-slim --videos 3
```

Die Auswahl beginnt mit je einem vorhandenen Misserfolg und Erfolg und ergänzt
lange Versuche. Alle Episoden bleiben in der Bewertung sichtbar. Für ein
bestimmtes Beispiel dessen `episode-…`-Ordner aus dem Bericht verwenden:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment replay runs/l4-slim/episode-DEINE_ID
```

Das Replay rendert nur die **tatsächlich aufgezeichneten Posen**, standardmäßig
mit 640 × 480 Pixeln. Es ruft weder das Modell noch `mj_step` noch die Bewertung
erneut auf. Der ursprüngliche Erfolg bleibt unverändert. Szene, Robotergeometrie
und MuJoCo-Version werden auf Übereinstimmung geprüft. Auch eine unterbrochene
Bewegungsdatei kann ein ausdrücklich gekennzeichnetes Teilvideo liefern.

Die 10-Hz-Aufzeichnung ist eine abgetastete Visualisierung. Sie kann sehr kurze
Kontaktvorgänge auslassen und dient nicht als alleiniger Erfolgsnachweis.
Simulationszeit und verstrichene Zeit bleiben getrennt; Modellwartezeit wird nicht
als minutenlanges Standbild kodiert. Videoerzeugung benötigt einen lokalen
funktionierenden Render-Unterbau; reine Datensammlung im schlanken Modus benötigt
keinen Renderer. Colabs GPU-Sitzung kann vor der nachträglichen Sichtung beendet
werden.

`--publish` sichert auch die Bewegungsdateien und `review.html` im [HF-Dataset](huggingface.md). Bereits erzeugte
Videos werden ebenfalls in das Archiv übernommen. Später erzeugte Clips liegen
zunächst lokal; ein schon veröffentlichter, unveränderlicher Release wird dadurch
nicht still überschrieben.
