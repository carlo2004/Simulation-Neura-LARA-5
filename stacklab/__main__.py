"""One entry point; command modules own their argument parsing."""
import argparse
import importlib
import sys
from . import __version__

COMMANDS = {
    "demo": ("stacklab.cli.demo", None),
    "console": ("stacklab.cli.console", None),
    "chat": ("stacklab.cli.chat", None),
    "serve": ("stacklab.cli.serve", None),
    "models": ("stacklab.cli.benchmark", "models"),
    "setup": ("stacklab.cli.benchmark", "setup"),
    "benchmark": ("stacklab.cli.benchmark", "test"),
    "experiment": ("stacklab.cli.experiment", None),
    "share": ("stacklab.cli.share", None),
    "doctor": ("stacklab.cli.doctor", None),
}

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in COMMANDS:
        module, prefix = COMMANDS[argv[0]]
        return importlib.import_module(module).main(([prefix] if prefix else [])+argv[1:])
    parser = argparse.ArgumentParser(prog="stacklab", description="LARA simulation and local code-policy experiments")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", choices=COMMANDS)
    parser.parse_args(argv)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
