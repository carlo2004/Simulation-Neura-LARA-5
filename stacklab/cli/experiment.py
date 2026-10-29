"""Plan, run and inspect a small reproducible development comparison."""
import argparse
import os
from pathlib import Path
import sys

from stacklab.cli.benchmark import CASES
from stacklab.experiments import create_plan, run_plan, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Reproducible development comparisons; no automatic downloads')
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='Freeze cases, models, seeds and budgets before execution')
    plan.add_argument('--output', type=Path, required=True, help='New empty experiment directory')
    plan.add_argument('--models', nargs='+', required=True)
    plan.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    plan.add_argument('--video', action='store_true')
    plan.add_argument('--cases', nargs='+', choices=CASES, default=['move-right', 'red-on-blue'])
    plan.add_argument('--scene-seeds', type=int, nargs='+', default=[42])
    plan.add_argument('--generation-seeds', type=int, nargs='+', default=[42])
    plan.add_argument('--blocks', type=int, nargs='+', default=[1, 4])
    plan.add_argument('--max-tokens', type=int, default=2048)
    plan.add_argument('--threads', type=int, default=min(8, os.cpu_count() or 1))
    plan.add_argument('--thinking', action=argparse.BooleanOptionalAction, default=None)
    plan.add_argument('--thinking-budget', type=int)
    plan.add_argument('--generation-timeout', type=int, default=600)
    plan.add_argument('--execution-timeout', type=int, default=180)
    for command, help_text in [('run', 'Run pending episodes; preserve existing attempts'),
                                ('report', 'Rebuild JSON, CSV and Markdown without starting a model'),
                                ('backup', 'Save existing raw evidence and reports in an atomic ZIP')]:
        child = sub.add_parser(command, help=help_text)
        child.add_argument('directory', type=Path)
        if command == 'run':
            child.add_argument('--backup-dir', type=Path, help='Checkpoint after each episode, e.g. a mounted Drive folder')
        if command == 'backup':
            child.add_argument('--output', type=Path, required=True, help='Destination folder outside the experiment')
    args = parser.parse_args(argv)
    try:
        if args.command == 'backup':
            from stacklab.backup import backup_experiment
            print(backup_experiment(args.directory, args.output))
            return 0
        if args.command == 'plan':
            options = vars(args).copy()
            options.pop('command')
            directory = options.pop('output')
            frozen = create_plan(directory, **options)
            write_report(directory)
            print(f'{len(frozen["episodes"])} planned episodes: {directory.resolve()}')
            print('Install selected models with stacklab setup, then: stacklab experiment run '+str(directory))
            return 0
        report = run_plan(args.directory, backup_dir=args.backup_dir) if args.command == 'run' else write_report(args.directory)
        success = sum(g['success'] for g in report['groups'])
        print(f'{success}/{report["planned"]} planned episodes physically successful; '
              f'complete={report["complete"]}; report: {args.directory.resolve()}/report.md')
        if args.command == 'report':
            return 0
        return 0 if success == report['planned'] else 1
    except KeyboardInterrupt:
        print('Interrupted; existing evidence was preserved. Run again to process only pending episodes.', file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        print('Error: '+str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
