"""Inspect tasks and run handwritten policies without model weights."""
import argparse
import json
from pathlib import Path
import sys
import time

from stacklab.cli.benchmark import CASES, case_definition
from stacklab.config import write_json
from stacklab.paths import RUNS_ROOT
from stacklab.tasks import TASKS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List the available development tasks')
    show = commands.add_parser('show', help='Show a seeded scene, instruction and trusted goal')
    run = commands.add_parser('run', help='Run a Python policy or a JSON reply in the simulator')
    for command in (show, run):
        command.add_argument('task', choices=CASES)
        command.add_argument('--seed', type=int, default=42)
    run.add_argument('--code', type=Path, required=True)
    run.add_argument('--output', type=Path)
    run.add_argument('--gui', action='store_true')
    run.add_argument('--axes', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'list':
        for name, task in TASKS.items():
            print(f'{name:23} {task["group"]:6} {task["instruction"]}')
        return 0
    try:
        case = case_definition(args.task, args.seed)
        if args.command == 'show':
            print(json.dumps(case, ensure_ascii=False, indent=2))
            return 0
        if not args.code.is_file():
            raise ValueError('Choose an existing Python policy or JSON reply file')
        directory = (args.output or RUNS_ROOT/f'task_{args.task}_{time.strftime("%Y%m%d_%H%M%S")}').resolve()
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Choose a new output directory to preserve previous evidence')
        write_json(directory/'case.json', case)
        write_json(directory/'scene.json', case['config'])
        write_json(directory/'goal.json', case['goal'])
        from stacklab.cli.worker import main as worker
        command = ['--config', str(directory/'scene.json'), '--goal', str(directory/'goal.json'),
                   '--code', str(args.code), '--result', str(directory/'execution.json')]
        if args.gui:
            command += ['--gui']
        if args.axes:
            command += ['--axes']
        result = worker(command)
        print('Evidence: '+str(directory))
        return result
    except (OSError, ValueError) as error:
        print('Error: '+str(error), file=sys.stderr)
        return 1
