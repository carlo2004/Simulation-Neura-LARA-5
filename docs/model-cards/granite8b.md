# granite8b — ibm-granite/granite-4.2-8b

[Modellübersicht und Bedienung](../models.md) · [Maschinenlesbarer Katalog](../../config/models.lock.json)

| Eigenschaft | Festgelegter Wert |
|---|---|
| Originalmodell | `ibm-granite/granite-4.2-8b` |
| Originalrevision | `a7042144125ce5ae64f89610e8289647fc000b9a` |
| Gesamtparameter | 8,791,592,960 |
| Inferenzgewichte | `ibm-granite/granite-4.2-8b-GGUF` / `granite-4.2-8b-Q4_K_M.gguf` |
| GGUF-Revision | `93f3f6a8938ee922b784cf4e5b4203cd3428df8f` |
| Quantisierung | `Q4_K_M` |
| Runtime | `llama.cpp`, `b11951` (CPU; CUDA separat konfiguriert) |
| Kontextbudget im Projekt | 8192 Tokens |
| Tokenizer-Klasse der Herstellerdatei | `GPT2Tokenizer` |
| Tokenizer-Algorithmus | `BPE` |
| Basisvokabular ohne zusätzliche Special Tokens | 100,352 Einträge |
| Tokenizer-Quelle | `ibm-granite/granite-4.2-8b` |
| Tokenizer-Revision | `a7042144125ce5ae64f89610e8289647fc000b9a` |

## Tokenizer und tatsächliche Inferenz

Die Klasse ist die Angabe aus der festgelegten Herstellerdatei, keine aus dem
Modellnamen abgeleitete Zuordnung. Die Inferenz tokenisiert mit dem im geprüften
GGUF eingebetteten Tokenizer und der nativen Chatvorlage von llama.cpp. Dabei
wird keine Transformers-Klasse nachgeladen. Die gesamte GGUF-Datei ist durch
ihre SHA-256 im Katalog festgelegt; die folgenden Hashes dokumentieren zusätzlich
die ursprüngliche Tokenizerdefinition für Herkunft und späteres Training.

- [`tokenizer_config.json`](https://huggingface.co/ibm-granite/granite-4.2-8b/blob/a7042144125ce5ae64f89610e8289647fc000b9a/tokenizer_config.json), SHA-256: `2007f26df166ed10a2d6fa881c1c8f3cdd151e451469f59b274897f14449835f`
- [`tokenizer.json`](https://huggingface.co/ibm-granite/granite-4.2-8b/blob/a7042144125ce5ae64f89610e8289647fc000b9a/tokenizer.json), SHA-256: `883975314d58743726347caaf2c32ac89afd5ad57222cffbc4f052f2ab27b2d7`

`stacklab models`, Modellkonfiguration und neue `generation.json`-Protokolle
nennen den Tokenizer. Token/s sind modellbezogene Messwerte; verschiedene
Tokenizer können denselben Text in unterschiedlich viele Tokens zerlegen.

Sampling, Thinking-Einstellungen und mögliche Antwortformatvorgaben stehen
vollständig im Katalog. Modellsupport ist kein Nachweis erfolgreicher Stapelung.
