# lfm2.6b — LiquidAI/LFM2.5-2.6B

[Modellübersicht und Bedienung](../models.md) · [Maschinenlesbarer Katalog](../../config/models.lock.json)

| Eigenschaft | Festgelegter Wert |
|---|---|
| Originalmodell | `LiquidAI/LFM2.5-2.6B` |
| Originalrevision | `b212e75975bbda9676a94d3cb7b2ca25b65fed48` |
| Gesamtparameter | 2,697,198,592 |
| Inferenzgewichte | `LiquidAI/LFM2.5-2.6B-GGUF` / `LFM2.5-2.6B-Q4_K_M.gguf` |
| GGUF-Revision | `e7caca5d835a3901a8e0d63e94009429bafafdfc` |
| Quantisierung | `Q4_K_M` |
| Runtime | `llama.cpp`, `b11951` (CPU; CUDA separat konfiguriert) |
| Kontextbudget im Projekt | 8192 Tokens |
| Tokenizer-Klasse der Herstellerdatei | `TokenizersBackend` |
| Tokenizer-Algorithmus | `BPE` |
| Basisvokabular ohne zusätzliche Special Tokens | 124,893 Einträge |
| Tokenizer-Quelle | `LiquidAI/LFM2.5-2.6B` |
| Tokenizer-Revision | `b212e75975bbda9676a94d3cb7b2ca25b65fed48` |

## Tokenizer und tatsächliche Inferenz

Die Klasse ist die Angabe aus der festgelegten Herstellerdatei, keine aus dem
Modellnamen abgeleitete Zuordnung. Die Inferenz tokenisiert mit dem im geprüften
GGUF eingebetteten Tokenizer und der nativen Chatvorlage von llama.cpp. Dabei
wird keine Transformers-Klasse nachgeladen. Die gesamte GGUF-Datei ist durch
ihre SHA-256 im Katalog festgelegt; die folgenden Hashes dokumentieren zusätzlich
die ursprüngliche Tokenizerdefinition für Herkunft und späteres Training.

- [`tokenizer_config.json`](https://huggingface.co/LiquidAI/LFM2.5-2.6B/blob/b212e75975bbda9676a94d3cb7b2ca25b65fed48/tokenizer_config.json), SHA-256: `11f1de897317b489dd09199284528382eeb17f566398b16e2039bb2266d26b09`
- [`tokenizer.json`](https://huggingface.co/LiquidAI/LFM2.5-2.6B/blob/b212e75975bbda9676a94d3cb7b2ca25b65fed48/tokenizer.json), SHA-256: `695be7802a0e4b8a81048f0ff5ebb7fc811a0ba5a6be63dbb24deb5a81096f41`

`stacklab models`, Modellkonfiguration und neue `generation.json`-Protokolle
nennen den Tokenizer. Token/s sind modellbezogene Messwerte; verschiedene
Tokenizer können denselben Text in unterschiedlich viele Tokens zerlegen.

Sampling, Thinking-Einstellungen und mögliche Antwortformatvorgaben stehen
vollständig im Katalog. Modellsupport ist kein Nachweis erfolgreicher Stapelung.
