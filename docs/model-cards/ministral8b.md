# ministral8b — mistralai/Ministral-3-8B-Reasoning-2512

[Modellübersicht und Bedienung](../models.md) · [Maschinenlesbarer Katalog](../../config/models.lock.json)

| Eigenschaft | Festgelegter Wert |
|---|---|
| Originalmodell | `mistralai/Ministral-3-8B-Reasoning-2512` |
| Originalrevision | `81eaece1948f3875421d9a45bc55487d10e2d894` |
| Gesamtparameter | 8,918,026,240 |
| Inferenzgewichte | `mistralai/Ministral-3-8B-Reasoning-2512-GGUF` / `Ministral-3-8B-Reasoning-2512-Q4_K_M.gguf` |
| GGUF-Revision | `4413bc9b7b091ddad28101650d1395f5e045a328` |
| Quantisierung | `Q4_K_M` |
| Runtime | `llama.cpp`, `b11951` (CPU; CUDA separat konfiguriert) |
| Kontextbudget im Projekt | 8192 Tokens |
| Tokenizer-Klasse der Herstellerdatei | `LlamaTokenizerFast` |
| Tokenizer-Algorithmus | `BPE` |
| Basisvokabular ohne zusätzliche Special Tokens | 131,072 Einträge |
| Tokenizer-Quelle | `mistralai/Ministral-3-8B-Reasoning-2512` |
| Tokenizer-Revision | `81eaece1948f3875421d9a45bc55487d10e2d894` |

## Tokenizer und tatsächliche Inferenz

Die Klasse ist die Angabe aus der festgelegten Herstellerdatei, keine aus dem
Modellnamen abgeleitete Zuordnung. Die Inferenz tokenisiert mit dem im geprüften
GGUF eingebetteten Tokenizer und der nativen Chatvorlage von llama.cpp. Dabei
wird keine Transformers-Klasse nachgeladen. Die gesamte GGUF-Datei ist durch
ihre SHA-256 im Katalog festgelegt; die folgenden Hashes dokumentieren zusätzlich
die ursprüngliche Tokenizerdefinition für Herkunft und späteres Training.

- [`tokenizer_config.json`](https://huggingface.co/mistralai/Ministral-3-8B-Reasoning-2512/blob/81eaece1948f3875421d9a45bc55487d10e2d894/tokenizer_config.json), SHA-256: `f3a437d1214f6b61c8eae19d1256b0ebbf567793f6dcc1f63f4a30b829f85235`
- [`tokenizer.json`](https://huggingface.co/mistralai/Ministral-3-8B-Reasoning-2512/blob/81eaece1948f3875421d9a45bc55487d10e2d894/tokenizer.json), SHA-256: `577575622324b2e099e2648be26bdeb5e5815ffe66d7004e9e3ddbf421db6bf1`

`stacklab models`, Modellkonfiguration und neue `generation.json`-Protokolle
nennen den Tokenizer. Token/s sind modellbezogene Messwerte; verschiedene
Tokenizer können denselben Text in unterschiedlich viele Tokens zerlegen.

Sampling, Thinking-Einstellungen und mögliche Antwortformatvorgaben stehen
vollständig im Katalog. Modellsupport ist kein Nachweis erfolgreicher Stapelung.
