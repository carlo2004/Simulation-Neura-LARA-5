"""Generate the GitHub model cards from the pinned catalog, without network access."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def card(alias, model):
    tokenizer = model['tokenizer']
    source = f'https://huggingface.co/{tokenizer["repository"]}/blob/{tokenizer["revision"]}'
    return f'''# {alias} — {model['model_id']}

[Modellübersicht und Bedienung](../models.md) · [Maschinenlesbarer Katalog](../../config/models.lock.json)

| Eigenschaft | Festgelegter Wert |
|---|---|
| Originalmodell | `{model['model_id']}` |
| Originalrevision | `{model['original_revision']}` |
| Gesamtparameter | {model['total_parameters']:,} |
| Inferenzgewichte | `{model['gguf_repository']}` / `{model['model_filename']}` |
| GGUF-Revision | `{model['gguf_revision']}` |
| Quantisierung | `{model['quantization']}` |
| Runtime | `llama.cpp`, `{model.get('runtime_version', 'b11951')}` (CPU; CUDA separat konfiguriert) |
| Kontextbudget im Projekt | {model.get('context_tokens', 4096)} Tokens |
| Tokenizer-Klasse der Herstellerdatei | `{tokenizer['tokenizer_class']}` |
| Tokenizer-Algorithmus | `{tokenizer['algorithm']}` |
| Basisvokabular ohne zusätzliche Special Tokens | {tokenizer['base_vocab_size']:,} Einträge |
| Tokenizer-Quelle | `{tokenizer['repository']}` |
| Tokenizer-Revision | `{tokenizer['revision']}` |

## Tokenizer und tatsächliche Inferenz

Die Klasse ist die Angabe aus der festgelegten Herstellerdatei, keine aus dem
Modellnamen abgeleitete Zuordnung. Die Inferenz tokenisiert mit dem im geprüften
GGUF eingebetteten Tokenizer und der nativen Chatvorlage von llama.cpp. Dabei
wird keine Transformers-Klasse nachgeladen. Die gesamte GGUF-Datei ist durch
ihre SHA-256 im Katalog festgelegt; die folgenden Hashes dokumentieren zusätzlich
die ursprüngliche Tokenizerdefinition für Herkunft und späteres Training.

- [`tokenizer_config.json`]({source}/tokenizer_config.json), SHA-256: `{tokenizer['tokenizer_config_sha256']}`
- [`tokenizer.json`]({source}/tokenizer.json), SHA-256: `{tokenizer['tokenizer_json_sha256']}`

`stacklab models`, Modellkonfiguration und neue `generation.json`-Protokolle
nennen den Tokenizer. Token/s sind modellbezogene Messwerte; verschiedene
Tokenizer können denselben Text in unterschiedlich viele Tokens zerlegen.

Sampling, Thinking-Einstellungen und mögliche Antwortformatvorgaben stehen
vollständig im Katalog. Modellsupport ist kein Nachweis erfolgreicher Stapelung.
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    models = json.loads((ROOT/'config/models.lock.json').read_text(encoding='utf-8'))['models']
    stale = []
    for alias, model in models.items():
        target = ROOT/'docs/model-cards'/(alias+'.md')
        content = card(alias, model)
        if args.check:
            if not target.is_file() or target.read_text(encoding='utf-8') != content:
                stale.append(alias)
        else:
            target.parent.mkdir(exist_ok=True)
            target.write_text(content, encoding='utf-8')
    if stale:
        print('Regenerate model cards: python tools/model_cards.py ('+', '.join(stale)+')', file=sys.stderr)
        return 1
    print(f'{len(models)} model cards '+('verified' if args.check else 'written'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
