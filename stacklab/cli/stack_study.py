"""Prepare, resume and export the paired A100 red-on-blue study."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

from stacklab import stack_study as study


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Freeze the protocol and verify the prevalidated scene bank')
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--checkpoint-dir', type=Path)
    run = commands.add_parser('run', help='Collect pending trials; never retry a scored model failure')
    run.add_argument('directory', type=Path)
    run.add_argument('--server-url', required=True)
    run.add_argument('--checkpoint-dir', type=Path)
    run.add_argument('--max-hours', type=float, default=6.)
    run.add_argument('--max-episodes', type=int, help='Optional additional limit; checked between episodes')
    restore = commands.add_parser('restore', help='Restore verified immutable episode checkpoints from Drive')
    restore.add_argument('--output', type=Path, required=True)
    restore.add_argument('--checkpoint-dir', type=Path, required=True)
    inventory = commands.add_parser('status', help='Rebuild collection inventory without model inference or ranking')
    inventory.add_argument('directory', type=Path)
    export = commands.add_parser('export', help='Create a checksummed local HF-ready snapshot; no login or upload')
    export.add_argument('directory', type=Path)
    export.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            frozen = study.prepare(args.output, args.checkpoint_dir)
            print(json.dumps(dict(protocol_sha256=frozen['protocol_sha256'],
                layouts=len(frozen['cases']), models=frozen['settings']['models'],
                planned=len(study.expected_trials(frozen))), indent=2))
            return 0
        if args.command == 'restore':
            study.restore(args.output, args.checkpoint_dir)
            print('Restored: '+str(args.output.resolve()))
            return 0
        if args.command == 'export':
            print(json.dumps(study.export_collection(args.directory, args.output), indent=2))
            return 0
        if args.command == 'run':
            from filelock import FileLock, Timeout
            try:
                with FileLock(str(args.directory/'.collection.lock'), timeout=0):
                    study.collect(args.directory, args.server_url, checkpoint_dir=args.checkpoint_dir,
                                  max_hours=args.max_hours, max_episodes=args.max_episodes)
            except Timeout as error:
                raise ValueError('Another collector is already using this working directory') from error
        else:
            study.write_index(args.directory)
        status = study.read(args.directory/'collection-status.json')
        print(json.dumps(status, indent=2))
        # A deliberate wall-time stop is a resumable collection, not a model failure.
        return 0 if args.command == 'status' or status['collection_complete'] else 1
    except KeyboardInterrupt:
        print('Interrupted. Existing model and partial attempts are preserved; resume the same study.', file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, KeyError, zipfile.BadZipFile) as error:
        print('Study error: '+str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
