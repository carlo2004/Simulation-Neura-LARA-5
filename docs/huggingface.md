# Ergebnisse im Team auf Hugging Face teilen

Das gemeinsame Dataset ist
[`Carlo0001/neura-lara5-cube-stacking-sim-v1`](https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1).
Quellcode, Prompts, Konfigurationen, Tests und kurze Ergebnisindizes bleiben auf
GitHub. Rohversuche und lesbare Laufberichte werden mit `stacklab share` auf HF geteilt.

## Einmal pro Teammitglied

1. Das Projekt aktualisieren und `python bootstrap.py` ausführen.
2. Im **eigenen HF-Konto** Zugriff auf das Dataset beantragen. Das Dataset hat
   derzeit manuell freizugebenden Zugang; Carlo muss jedes Teamkonto freischalten.
3. Lokal anmelden: unter Windows `.\.venv\Scripts\hf.exe auth login`, unter
   Linux/macOS `.venv/bin/hf auth login`. Einen eigenen Token mit den nötigen
   Lese-/Beitragsrechten verwenden. Kein gemeinsamer Carlo-Token ist erforderlich.

Für neue Checkouts kann `git clone --depth 1` verwendet werden. Die alten Rohdaten
sind aus der aktuellen Projektstruktur entfernt; die Git-Historie bleibt erhalten.

| Konto / Berechtigung | Standard beim Teilen |
|---|---|
| Carlo im eigenen Dataset | Direkter Upload |
| Teammitglied mit eigenem Konto | HF-Beitrags-PR; sofort über den ausgegebenen Link einsehbar |
| Teammitglied mit direktem Dataset-Schreibrecht, etwa in einer HF-Organisation | `--direct` verwenden |

Der freigegebene Lesezugriff ist kein direktes Schreibrecht. Beiträge über PRs
müssen in den HF-Repositoryeinstellungen erlaubt sein. Carlo kann sie im
**Community**-Bereich prüfen und übernehmen. Alle Teammitglieder melden sich mit
ihrem eigenen Konto an; der hochladende Nutzer wird aus der HF-Anmeldung abgeleitet.

## Einen interessanten Versuch teilen

Nach einem Chat oder einzelnen Benchmarklauf dessen Ergebnisordner angeben:

```bash
python -m stacklab share runs/mein-chat --title "Greifer wiederholt die Bewegung" --note "Der zweite Auftrag läuft zu weit."
```

`python` hier durch den Projektinterpreter ersetzen, unter Windows beispielsweise
`.\.venv\Scripts\python.exe`. `stacklab share upload …` ist dieselbe Aktion.
Titel und Notiz sind optional; der Ordnername ist der Standardtitel.

Der Befehl gibt **Run-ID, lesbaren HF-Link und gegebenenfalls den Beitrags-PR**
aus. Statt einer ZIP-Datei per Messenger genügt anschließend etwa: „Mein Lauf
Greifer wiederholt die Bewegung ist auf HF.“ Carlo kann ihn dort oder mit der
Suchfunktion unten finden.

Eine Vorschau ohne Netzwerk und ohne Änderungen an den Quelldateien:

```bash
python -m stacklab share runs/mein-chat --dry-run
```

## Vergleichsserien und freie Versuche

| Bereich | Zweck | Automatische Einordnung |
|---|---|---|
| `experiments` | Geplante Vergleichsserien mit festgelegten Fällen, Seeds und Budgets | Gültiger eingefrorener Experimentplan |
| `playground` | Freie Chats, einzelne Versuche und Erkundungen | Erkannter Chat-/Aufgaben-/Benchmarkordner |
| `legacy` | Bereits übertragene historische Aufzeichnungen | Feste historische Migration |

Die Einordnung richtet sich nach dem Versuchsdesign, nicht nach der Dateigröße.
Ein kleiner, kontrollierter Vergleich kann ein Experiment sein. Ein großer freier
Chat bleibt ein Erkundungsversuch. Mit `--kind playground` lässt sich auch ein
kleiner Plan ausdrücklich als Erkundung teilen. `--kind experiment` erfordert
einen gültigen eingefrorenen Plan; eine kaputte Manifestdatei wird nicht still
als Playground behandelt. Kategorie und Run-ID bleiben nach dem ersten Teilen fest.

Eine geplante Serie direkt nach dem Lauf teilen:

```bash
python -m stacklab experiment run runs/vergleich --publish --title "Laptop-Vergleich" --note "Gleiche Fälle und Seeds auf allen Geräten."
```

Auch `experiment pilot --publish` und `experiment publish runs/vergleich`
verwenden diese Ablage. `--tags cpu feedback` ergänzt kurze Labels. `--submit`
erzwingt einen Beitrags-PR, `--direct` benötigt tatsächliches Dataset-Schreibrecht.
`--repository OWNER/DATASET` überschreibt das Ziel aus `config/huggingface.json`.

## Übersicht und Datenstände

| HF-Pfad | Inhalt |
|---|---|
| `experiments/<HF-Name>/<UTC-Datum>_<Titel>_<ID>/` | Eine geplante Serie |
| `playground/<HF-Name>/<UTC-Datum>_<Titel>_<ID>/` | Ein Erkundungslauf |
| `…/run.json`, `…/README.md` | Titel, Notiz, Tags, hochladender Nutzer, Run-ID und Verweis auf den neuesten Stand |
| `…/snapshots/<SHA256>/README.md` | Lesbare Übersicht mit allen Versuchen und Tokenraten |
| `…/snapshots/<SHA256>/details/*.md` | Auftrag, Modellantwort, geprüfter Code und gemessene Rückmeldung pro Versuch |
| `…/snapshots/<SHA256>/evidence.zip` | Vollständige ausgewählte Rohdateien einschließlich optionaler Bewegungsdaten/Videos |
| `…/snapshots/<SHA256>/snapshot.json` | Dateigrößen, Prüfsummen und Archividentität |

Der Titel im Ordnerpfad wird beim ersten Teilen festgelegt; die Beschreibung kann
später aktualisiert werden. Eine zufällige Run-ID verhindert Kollisionen zwischen
gleich benannten Laptop-Ordnern. Jeder geänderte Stand erhält einen eigenen
Snapshot. Alte Snapshots werden nicht überschrieben. Wiederholtes Teilen identischer
Daten erzeugt keinen zusätzlichen Commit. Ein eigener `run.json` pro Lauf vermeidet
einen gemeinsam überschriebenen globalen Index. Gleichzeitige Änderungen werden
mit einer Prüfung der aktuellen Hub-Revision behandelt.

Lokal hält `sharing.json` die Run-Identität fest; `share-receipt.json` enthält den
festen Hub-Link und einen vorhandenen Beitrags-PR. Weitere Uploads desselben Laufs
aktualisieren einen offenen PR. Nach einer verlorenen lokalen Quittung kann der
Helfer den vorhandenen Beitrag wiederfinden. Geschlossene PRs werden nicht verändert.
Diese Verwaltungsdateien sind keine Zugangsdatenspeicher und werden nicht als
Rohversuch exportiert.

Beim ersten direkten Upload des Dataset-Eigentümers wird der bestehenden
Datasetkarte einmalig eine Navigation zu den Bereichen angehängt. Vorhandener Text
bleibt erhalten. Beitrags-PRs ändern diese gemeinsame Karte nicht.

## Läufe finden und ansehen

```bash
python -m stacklab share list --pending
python -m stacklab share list --kind playground --user HF_NAME --pending
python -m stacklab share list --kind experiment --limit 20
```

`--pending` nimmt offene Teambeiträge hinzu; ohne diese Option werden die auf dem
HF-Hauptbranch übernommenen Läufe angezeigt. `--json` liefert maschinenlesbare
Metadaten. Das Auflisten lädt keine Roharchive herunter. Die festen Links öffnen
lesbare Markdown-Berichte auf HF, einschließlich Programmcode und Fehlern. Das ZIP
ist nur für vollständige lokale Analyse nötig. Die Chat-Verbindung zu HF kann
diese veröffentlichten Texte und Metadaten ebenfalls lesen.

Freie Aufgaben ohne vertrauenswürdiges Ziel stehen ausdrücklich als **unbewertet**
in der Übersicht. Modell-Fertigmeldungen ersetzen keine Physikprüfung. Fehlversuche,
abgebrochene und offene geplante Episoden bleiben sichtbar. Playground und
Experimente werden nicht zu einer gemeinsamen Erfolgsquote zusammengefasst.
Die Tokenraten stammen aus der jeweiligen Runtime; verschiedene Tokenizer bleiben
unterschiedliche Messbedingungen. Rohdaten sind kein automatisch geprüfter SFT-Split.

Die [historische Migration](archive-migration.md) ist abgeschlossen und über
[festgelegte Revisionen und Prüfnachweise](../experiments/archive-location.json)
nachvollziehbar. Der ursprüngliche Snapshot-Download `experiment fetch` bleibt
für das ältere `runs/<SHA256>`-Exportformat verfügbar.

Primärdokumentation: [Hub-Uploads](https://huggingface.co/docs/huggingface_hub/guides/upload),
[HF-Beitrags-PRs](https://huggingface.co/docs/hub/repositories-pull-requests-discussions),
[Zugriffsfreigabe für Datasets](https://huggingface.co/docs/hub/datasets-gated).
