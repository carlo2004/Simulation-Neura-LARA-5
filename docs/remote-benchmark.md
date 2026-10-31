# Automatischer Modellvergleich auf L4 und A100

Ab Version 3.6 ist der Pilot standardmäßig schlank: kompakte Bewegungsdaten statt
laufendem Video-Encoding. Die [schlanke Aufzeichnung und HTML-Sichtung](slim-benchmark.md)
erklärt Datenumfang, optionale Videos und die Aufteilung zwischen automatischer
Bewertung und händischer Fehleranalyse.

## Der erste sinnvolle Vergleich

Eine kleine **Entwicklungsprobe mit zehn Episoden je Modell und GPU** beantwortet
zunächst: Welche der derzeit eingebundenen Modellkonfigurationen funktionieren
praktisch, und wo scheitern sie?

| Teil | Standard des Piloten |
|---|---|
| Einfache Bewegung | 5 Episoden: Greifer 5 cm nach rechts |
| Seminaraufgabe | 5 Episoden: Rot auf Blau stapeln, mit leicht variierenden Startpositionen |
| Wiederholungen | Szenenseeds 100–104, gepaart mit Generierungsseeds 1000–1004 |
| Programmblockbudget | 1 Block für das günstige Screening; `--blocks 4` für einen gesonderten Feedbackvergleich |
| Generierung | 2048 Ausgabetokens pro Block, 180 s Zeitlimit; dokumentierte Modellprofile |
| Modelle / GPUs | Alle 7 Katalogmodelle, nacheinander auf L4 und A100 |
| Umfang | 70 Episoden pro GPU, insgesamt 140 |

Bei der Bewegung bleibt die Szene gleich; die Generierungsseeds wechseln. Beim
Stapeln wechseln zusätzlich die Startpositionen. Jeder Seed wird zwischen allen
Modellen und beiden GPUs identisch verwendet. Szenen- und Generierungsseeds werden
gepaart, statt versehentlich ein 5-mal-5-Kreuzprodukt zu erzeugen.

Danach die aussichtsreichsten Modelle mit mehr **neuen** Fällen prüfen. Zehn
Episoden liefern noch keinen allgemeinen statistischen Sieger. Diese
Entwicklungsfälle nicht als ungesehenen Test eines später darauf abgestimmten
Fine-Tunings ausgeben. Als nächste Aufgaben eignen sich `move-forward`, `move-up`,
`blue-on-red` und `green-on-blue`. Nach dem Screening können ausgewählte Modelle
mit `--blocks 4` und neuen Ausgabeordnern Feedback nutzen. `--blocks 1 4`
verdoppelt den Umfang. Bei durchgehend misslungenem Stapeln zuerst die
Fehlerursachen und Feedbackbedingungen prüfen, bevor identische Fälle vielfach
wiederholt werden.

## Was automatisch abläuft

Der lokale Runner wählt über den vorhandenen SSH-Tunnel ein Modell aus. Colab
entlädt das vorherige Modell, prüft/installiert Gewichte und Runtime und lädt das
nächste Modell mit nachgewiesenem GPU-Offload. Nur ein Modell liegt gleichzeitig
im GPU-Speicher. Ladezeit und ein kurzer, **unbewerteter Aufwärmversuch** stehen
separat in `model-setups/`. Auch ein dort abgeschnittener Text ist kein gewerteter
Aufgabenfehler.

Jede Episode erhält einen neuen lokalen Worker, eine frische Szene und ein neues
Gespräch. Der Benchmarkserver deaktiviert die Wiederverwendung des Prompt-KV-
Caches. Ein Modellwechsel ändert die Serverkennung; ein alter Client kann das
neue Modell nicht unbemerkt verwenden. Der normale Chatserver erlaubt
Modellwechsel erst nach ausdrücklichem Start im Benchmarkmodus.

GPU-Auswahl, Google-Anmeldung und SSH-Tunnel richtest du einmal pro Laufzeit ein.
Der Runner kann Colabs Karte nicht selbst von L4 auf A100 umschalten. Während des
Benchmarks denselben Server nicht gleichzeitig für einen weiteren Chat verwenden.

## 1. Aktualisieren und Colab-Server starten

Den bisherigen Server mit Strg+C beenden. **Lokal und auf Colab** im Projektordner
`git pull --ff-only` ausführen. Beide Seiten sollten denselben Code-Stand nutzen.
Die [Remote-Anleitung](remote-live.md) erklärt Einrichtung, Tunnel und den
`virtualenv`-Ausweichweg, falls Colab kein `ensurepip` bereitstellt.

In der Colab-Shell bei offenem SSH-Tunnel:

```bash
python tools/start_remote.py --model granite8b --device cuda --threads 2 --benchmark
```

Der Helfer richtet zunächst Granite ein. Weitere Modelle werden beim Wechsel
geprüft und gegebenenfalls heruntergeladen; Dory benötigt seinen eigenen Build.
Die Colab-Shell zeigt den Fortschritt. Die Ersteinrichtung zählt nicht zur nativen
Tokenrate. Der Runner verwendet den bestehenden Tunnel und erstellt keine zweite
Colab-/SSH-Sitzung.

Der Starthelfer bereitet im Benchmarkmodus die Werkzeuge für spätere Quellbuilds
bereits vor, auch wenn Granites erste Runtime als Binärpaket installiert wird.

In einer bereits eingerichteten Umgebung ohne Starthelfer:

```bash
.venv/bin/python -m stacklab serve --model granite8b --device cuda --threads 2 --allow-model-switch --install-missing
```

## 2. Lokal starten

Windows PowerShell im lokalen Projektordner:

```powershell
.\.venv\Scripts\python.exe -m stacklab doctor --server-url http://127.0.0.1:8765
.\.venv\Scripts\python.exe -m stacklab experiment pilot --server-url http://127.0.0.1:8765 --output runs/l4-pilot
```

Das sind standardmäßig alle sieben Modelle mit je zehn Episoden. Die Physik läuft
ohne Fenster und Video-Encoding; kleine Bewegungsdaten erlauben späteres Replay.
`--gui` zeigt die Versuche live, `--video` zeichnet sofort auf, und
`--recording full` aktiviert ausführliche Streams samt sofortiger Videos.
Auf beiden GPUs dieselben Optionen verwenden. Videos folgen der Simulationszeit;
Modellwartezeiten stehen separat in den Messdaten.

Ein kleiner Verbindungscheck vor dem Hauptlauf:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment pilot --server-url http://127.0.0.1:8765 --models granite8b --repetitions 1 --output runs/connection-check --gui
```

Diese zwei Zusatzepisoden sind getrennte Entwicklungsproben.

Nach einem Abbruch denselben Plan fortsetzen:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment run runs/l4-pilot
```

Vorhandene Episoden werden nie still überschrieben oder neu generiert.
Abgebrochene Versuche bleiben sichtbar. Nach GPU-/Treiber-, Code-, Paket- oder
Katalogwechsel einen neuen Plan anlegen. Ein Modell, das nicht lädt, erhält
technische Ausfälle für seine vorgesehenen Episoden; der Runner versucht danach
das nächste Modell. Verbindungsprobleme sind keine nachgewiesenen Stapelfehler.

## 3. Auf A100 wiederholen und vergleichen

Die unbenutzte L4-Sitzung beenden und GPU-Ressourcen freigeben. Auf A100 denselben
Code-Stand und Serverbefehl mit neuem Tunnel verwenden. Dann lokal:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment pilot --server-url http://127.0.0.1:8765 --output runs/a100-pilot
.\.venv\Scripts\python.exe -m stacklab experiment compare runs/l4-pilot runs/a100-pilot --output runs/l4-a100-comparison
```

Der Vergleich lehnt unterschiedliche Aufgaben, Seeds, Budgets, Modellprofile,
Prompt-/Quellcode-Hashes und Laufzeitkonfigurationen ab. Erfasst wird die wirklich
erkannte GPU samt UUID, Speicher und Treiber; der Ordnername ist keine Messung.
Gleiche Seeds garantieren keine bitgleichen Antworten auf verschiedener Hardware.

## Aufzeichnungen und Bewertung

| Datei / Bereich | Inhalt |
|---|---|
| `manifest.json` | Eingefrorener Plan, Modelle, Quantisierung, Profile, Seeds, lokale und entfernte Hardware/Software/Quellcode-Hashes |
| `model-setups/` | Einrichtung, Ladezeit, Modellwechsel, Offload-Diagnose und gesonderter Aufwärmversuch |
| `episode-…/` | Szene, rohe Antworten/Streams, erzeugter Code, API-Aktionen, Fehler, Physikzustände und Bewertung |
| `episode-…/motion.jsonl` | Kompakte Posen der tatsächlichen Bewegung für späteres Replay |
| `episode-…/simulation.mp4` | Optional sofort oder später erzeugtes Video |
| `results.csv`, `summary.json`, `report.md` | Ergebnisse pro Episode, Modell, Aufgabe und Blockbudget |
| `ranking.json`, `ranking.md` | Vorläufiger Modellvergleich, Technikfehler, Tokenrate, erstes Token und Episodendauer |
| `review.html` | Offline-Sichtung mit Auftrag, Antwort, Code, Zeiten und optionalen Videos |
| Vergleichsordner | `comparison.csv`, `.json`, `.md` mit beiden GPU-Läufen |

**Qualität:** Gemessener Zielerfolg. Eine Fertigmeldung des Modells genügt nicht.
Beim Stapeln gilt die unabhängige Kontakt-/Stabilitätsprüfung mit freiem Greifer.
Die 20 Stabilitätsmessungen sind **eine** Episode. Format-, API-, Ausführungs- und
Budgetfehler bleiben erhalten.

**Geschwindigkeit:** Passende native Token-/Zeit-Summen statt Mittelwerten von
Tokenraten. Zeit bis zum ersten Token und vollständige Episodendauer ergänzen das
Ausgabetempo. Tokenizer unterscheiden sich zwischen Modellen; gleiche Tokenraten
stehen nicht für eine universell gleiche Arbeitsmenge. Schnellstes und
zuverlässigstes Modell können verschieden sein.

**Aussagegrenzen:** Profile und Quantisierungen folgen dem vorhandenen Katalog.
Verglichen werden einsatzfähige Modellkonfigurationen, keine isolierten Gewichte.
Die End-to-End-Quote behält alle geplanten Episoden im Nenner; Technikfehler
erscheinen separat. Die Modellquote verwendet nur bewertete Episoden.
Unsicherheitsintervalle stehen in JSON unter der angegebenen Bernoulli-Annahme.
Der kleine Pilot rechtfertigt keine starke statistische Siegerbehauptung.

## Upload nach Hugging Face

Der lokale Runner veröffentlicht neue Rohdaten im Dataset
[`Carlo0001/neura-lara5-cube-stacking-sim-v1`](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1).
Dafür einmal `.\.venv\Scripts\hf.exe auth login` auf dem lokalen Rechner ausführen.
Colab braucht für diese Aufteilung keine Schreibanmeldung. Code bleibt auf GitHub.

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment pilot --server-url http://127.0.0.1:8765 --output runs/l4-pilot --publish
```

Einen vorhandenen Lauf erst prüfen und später hochladen:

```powershell
.\.venv\Scripts\python.exe -m stacklab experiment publish runs/l4-pilot --dry-run
.\.venv\Scripts\python.exe -m stacklab experiment publish runs/l4-pilot
```

Jeder Inhaltsstand erhält eine Snapshot-ID und einen festen Hub-Commit. Das ZIP
enthält die Rohaufzeichnungen einschließlich optionaler Videos; lesbare Tabellen
und JSONL-Episoden stehen daneben. Alle Dateien besitzen Prüfsummen. Bei einem
Uploadfehler bleiben die lokalen Dateien erhalten. Für A100 einen neuen
Versuchsordner mit denselben eingefrorenen Bedingungen verwenden.

Die Ausgabe und `share-receipt.json` nennen den exakten Snapshot-Link. Die beiden
Links können im Chat über den Hugging-Face-Connector gelesen werden.
[Anmeldung, Speicherformat und geprüfter Download](huggingface.md).
