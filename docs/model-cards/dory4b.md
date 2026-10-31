# dory4b — nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16

[Modellübersicht und Bedienung](../models.md) · [Maschinenlesbarer Katalog](../../config/models.lock.json)

| Eigenschaft | Festgelegter Wert |
|---|---|
| Originalmodell | `nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16` |
| Originalrevision | `48e0c3faac0aaa8b93fc4e68256d7e58b183645e` |
| Gesamtparameter | 3,975,229,440 |
| Inferenzgewichte | `nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-GGUF` / `NVIDIA-Nemotron-Labs-Dory1.0-4B-Q5_K_M.gguf` |
| GGUF-Revision | `df53755cb8741843af8e019e088819fbef17e29b` |
| Quantisierung | `Q5_K_M` |
| Runtime | `llama.cpp`, `dory-98a74c97ea09-cpu` (CPU; CUDA separat konfiguriert) |
| Kontextbudget im Projekt | 8192 Tokens |
| Tokenizer-Klasse der Herstellerdatei | `PreTrainedTokenizerFast` |
| Tokenizer-Algorithmus | `BPE` |
| Basisvokabular ohne zusätzliche Special Tokens | 131,072 Einträge |
| Tokenizer-Quelle | `nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16` |
| Tokenizer-Revision | `48e0c3faac0aaa8b93fc4e68256d7e58b183645e` |

## Tokenizer und tatsächliche Inferenz

Die Klasse ist die Angabe aus der festgelegten Herstellerdatei, keine aus dem
Modellnamen abgeleitete Zuordnung. Die Inferenz tokenisiert mit dem im geprüften
GGUF eingebetteten Tokenizer und der nativen Chatvorlage von llama.cpp. Dabei
wird keine Transformers-Klasse nachgeladen. Die gesamte GGUF-Datei ist durch
ihre SHA-256 im Katalog festgelegt; die folgenden Hashes dokumentieren zusätzlich
die ursprüngliche Tokenizerdefinition für Herkunft und späteres Training.

- [`tokenizer_config.json`](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16/blob/48e0c3faac0aaa8b93fc4e68256d7e58b183645e/tokenizer_config.json), SHA-256: `10f93eabcb9b1602fbb991d6308e787ce1df28ee9cd7a1c6d1e8c3f338b957bc`
- [`tokenizer.json`](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16/blob/48e0c3faac0aaa8b93fc4e68256d7e58b183645e/tokenizer.json), SHA-256: `623c34567aebb18582765289fbe23d901c62704d6518d71866e0e58db892b5b7`

`stacklab models`, Modellkonfiguration und neue `generation.json`-Protokolle
nennen den Tokenizer. Token/s sind modellbezogene Messwerte; verschiedene
Tokenizer können denselben Text in unterschiedlich viele Tokens zerlegen.

Sampling, Thinking-Einstellungen und mögliche Antwortformatvorgaben stehen
vollständig im Katalog. Modellsupport ist kein Nachweis erfolgreicher Stapelung.
