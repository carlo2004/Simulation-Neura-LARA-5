# nemotron8b — nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB

[Modellübersicht und Bedienung](../models.md) · [Maschinenlesbarer Katalog](../../config/models.lock.json)

| Eigenschaft | Festgelegter Wert |
|---|---|
| Originalmodell | `nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB` |
| Originalrevision | `1db54d5b12533ff1bcaa8e42cf4c667988a1f1be` |
| Gesamtparameter | 7,996,156,490 |
| Inferenzgewichte | `nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB` / `Nemotron-3.5-Bolt-E4B-Q4_K_M.gguf` |
| GGUF-Revision | `1db54d5b12533ff1bcaa8e42cf4c667988a1f1be` |
| Quantisierung | `Q4_K_M` |
| Runtime | `llama.cpp`, `b11951` (CPU; CUDA separat konfiguriert) |
| Kontextbudget im Projekt | 8192 Tokens |
| Tokenizer-Klasse der Herstellerdatei | `GemmaTokenizer` |
| Tokenizer-Algorithmus | `BPE` |
| Basisvokabular ohne zusätzliche Special Tokens | 262,144 Einträge |
| Tokenizer-Quelle | `nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-BF16` |
| Tokenizer-Revision | `49843eed8db1f1c616c47af75cfd36e07aec0667` |

## Tokenizer und tatsächliche Inferenz

Die Klasse ist die Angabe aus der festgelegten Herstellerdatei, keine aus dem
Modellnamen abgeleitete Zuordnung. Die Inferenz tokenisiert mit dem im geprüften
GGUF eingebetteten Tokenizer und der nativen Chatvorlage von llama.cpp. Dabei
wird keine Transformers-Klasse nachgeladen. Die gesamte GGUF-Datei ist durch
ihre SHA-256 im Katalog festgelegt; die folgenden Hashes dokumentieren zusätzlich
die ursprüngliche Tokenizerdefinition für Herkunft und späteres Training.

- [`tokenizer_config.json`](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-BF16/blob/49843eed8db1f1c616c47af75cfd36e07aec0667/tokenizer_config.json), SHA-256: `b3da1b7227c5d35fd905ad13200a08be63cb346b2d1bd4f6d58878c9783d5de1`
- [`tokenizer.json`](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-BF16/blob/49843eed8db1f1c616c47af75cfd36e07aec0667/tokenizer.json), SHA-256: `cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f`

`stacklab models`, Modellkonfiguration und neue `generation.json`-Protokolle
nennen den Tokenizer. Token/s sind modellbezogene Messwerte; verschiedene
Tokenizer können denselben Text in unterschiedlich viele Tokens zerlegen.

Sampling, Thinking-Einstellungen und mögliche Antwortformatvorgaben stehen
vollständig im Katalog. Modellsupport ist kein Nachweis erfolgreicher Stapelung.
