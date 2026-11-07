"""Install the optional, checksum-pinned GGUF and llama.cpp runtime."""
import argparse
import sys

from stacklab.llm.catalog import setup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', help='Catalog alias or Hugging Face model ID')
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    args = parser.parse_args(argv)
    try:
        setup(args.model, device=args.device)
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Setup: {error}', file=sys.stderr)
        return 1
    return 0
