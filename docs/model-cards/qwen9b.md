# qwen9b — Qwen/Qwen3.5-9B

[Modellübersicht und Bedienung](../models.md) · [Maschinenlesbarer Katalog](../../config/models.lock.json)

| Eigenschaft | Festgelegter Wert |
|---|---|
| Originalmodell | `Qwen/Qwen3.5-9B` |
| Originalrevision | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| Gesamtparameter | 9,653,104,368 |
| Inferenzgewichte | `unsloth/Qwen3.5-9B-GGUF` / `Qwen3.5-9B-Q4_K_M.gguf` |
| GGUF-Revision | `3885219b6810b007914f3a7950a8d1b469d598a5` |
| Quantisierung | `Q4_K_M` |
| Runtime | `llama.cpp`, `b11951` (CPU; CUDA separat konfiguriert) |
| Kontextbudget im Projekt | 8192 Tokens |
| Tokenizer-Klasse der Herstellerdatei | `Qwen2Tokenizer` |
| Tokenizer-Algorithmus | `BPE` |
| Basisvokabular ohne zusätzliche Special Tokens | 248,044 Einträge |
| Tokenizer-Quelle | `Qwen/Qwen3.5-9B` |
| Tokenizer-Revision | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |

## Tokenizer und tatsächliche Inferenz

Die Klasse ist die Angabe aus der festgelegten Herstellerdatei, keine aus dem
Modellnamen abgeleitete Zuordnung. Die Inferenz tokenisiert mit dem im geprüften
GGUF eingebetteten Tokenizer und der nativen Chatvorlage von llama.cpp. Dabei
wird keine Transformers-Klasse nachgeladen. Die gesamte GGUF-Datei ist durch
ihre SHA-256 im Katalog festgelegt; die folgenden Hashes dokumentieren zusätzlich
die ursprüngliche Tokenizerdefinition für Herkunft und späteres Training.

- [`tokenizer_config.json`](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/tokenizer_config.json), SHA-256: `316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8`
- [`tokenizer.json`](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/tokenizer.json), SHA-256: `5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42`

`stacklab models`, Modellkonfiguration und neue `generation.json`-Protokolle
nennen den Tokenizer. Token/s sind modellbezogene Messwerte; verschiedene
Tokenizer können denselben Text in unterschiedlich viele Tokens zerlegen.

Sampling, Thinking-Einstellungen und mögliche Antwortformatvorgaben stehen
vollständig im Katalog. Modellsupport ist kein Nachweis erfolgreicher Stapelung.
