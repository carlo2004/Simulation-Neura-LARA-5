# qwen4b — Qwen/Qwen3.5-4B

[Modellübersicht und Bedienung](../models.md) · [Maschinenlesbarer Katalog](../../config/models.lock.json)

| Eigenschaft | Festgelegter Wert |
|---|---|
| Originalmodell | `Qwen/Qwen3.5-4B` |
| Originalrevision | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` |
| Gesamtparameter | 4,659,865,088 |
| Inferenzgewichte | `unsloth/Qwen3.5-4B-GGUF` / `Qwen3.5-4B-Q4_K_M.gguf` |
| GGUF-Revision | `e87f176479d0855a907a41277aca2f8ee7a09523` |
| Quantisierung | `Q4_K_M` |
| Runtime | `llama.cpp`, `b11951` (CPU; CUDA separat konfiguriert) |
| Kontextbudget im Projekt | 4096 Tokens |
| Tokenizer-Klasse der Herstellerdatei | `Qwen2Tokenizer` |
| Tokenizer-Algorithmus | `BPE` |
| Basisvokabular ohne zusätzliche Special Tokens | 248,044 Einträge |
| Tokenizer-Quelle | `Qwen/Qwen3.5-4B` |
| Tokenizer-Revision | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` |

## Tokenizer und tatsächliche Inferenz

Die Klasse ist die Angabe aus der festgelegten Herstellerdatei, keine aus dem
Modellnamen abgeleitete Zuordnung. Die Inferenz tokenisiert mit dem im geprüften
GGUF eingebetteten Tokenizer und der nativen Chatvorlage von llama.cpp. Dabei
wird keine Transformers-Klasse nachgeladen. Die gesamte GGUF-Datei ist durch
ihre SHA-256 im Katalog festgelegt; die folgenden Hashes dokumentieren zusätzlich
die ursprüngliche Tokenizerdefinition für Herkunft und späteres Training.

- [`tokenizer_config.json`](https://huggingface.co/Qwen/Qwen3.5-4B/blob/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/tokenizer_config.json), SHA-256: `316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8`
- [`tokenizer.json`](https://huggingface.co/Qwen/Qwen3.5-4B/blob/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/tokenizer.json), SHA-256: `5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42`

`stacklab models`, Modellkonfiguration und neue `generation.json`-Protokolle
nennen den Tokenizer. Token/s sind modellbezogene Messwerte; verschiedene
Tokenizer können denselben Text in unterschiedlich viele Tokens zerlegen.

Sampling, Thinking-Einstellungen und mögliche Antwortformatvorgaben stehen
vollständig im Katalog. Modellsupport ist kein Nachweis erfolgreicher Stapelung.
