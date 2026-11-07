"""One entry point; command modules own their argument parsing."""
import argparse
import importlib
import sys
from . import __version__

COMMANDS = {
    "workbench": "stacklab.cli.workbench",
    "prompt2robo": "stacklab.cli.prompt2robo",
    "setup": "stacklab.cli.setup",
    "demo": "stacklab.cli.demo",
    "console": "stacklab.cli.console",
    "doctor": "stacklab.cli.doctor",
}

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in COMMANDS:
        return importlib.import_module(COMMANDS[argv[0]]).main(argv[1:])
    parser = argparse.ArgumentParser(prog="stacklab", description="Prompt2Robo workbench and LARA 5 simulation")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", choices=COMMANDS)
    parser.parse_args(argv)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
