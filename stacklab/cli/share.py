"""Share an interesting local run, or find the team's runs on the Hub."""
import argparse
import json
from pathlib import Path
import sys

from httpx import HTTPError
from huggingface_hub.errors import HfHubHTTPError, LocalTokenNotFoundError
from stacklab.sharing import KINDS, list_runs, share_run


def add_options(parser):
    parser.add_argument('--kind', choices=KINDS, help='experiment: planned comparison; playground: exploration')
    parser.add_argument('--title', help='Readable name; defaults to the local directory name')
    parser.add_argument('--note', help='What makes this run interesting?')
    parser.add_argument('--tags', nargs='*', help='Short labels for the team')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--submit', dest='direct', action='store_false', help='Submit as an HF contribution PR with your own account')
    mode.add_argument('--direct', dest='direct', action='store_true', help='Write directly when your account has dataset write access')
    parser.set_defaults(direct=None)


def options(args):
    return {name: getattr(args, name, None) for name in ('kind', 'title', 'note', 'tags', 'direct')}


def show_receipt(receipt):
    print('Bereich: '+receipt['kind']+' | Hochgeladen von: '+receipt['uploader'])
    print('Run-ID: '+receipt['run_id'])
    print('Ansehen: '+receipt['url'])
    if receipt.get('pr_url'):
        print('HF-Beitrags-PR: '+receipt['pr_url'])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ('upload', 'list', '-h', '--help'):
        argv.insert(0, 'upload')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    upload = sub.add_parser('upload', help='Share a local chat, task or experiment folder')
    upload.add_argument('directory', type=Path)
    upload.add_argument('--repository', help='HF dataset owner/name; default from project configuration')
    upload.add_argument('--dry-run', action='store_true', help='Offline preview; changes no local run or remote files')
    add_options(upload)
    listing = sub.add_parser('list', help='Find shared runs without downloading raw archives')
    listing.add_argument('--repository')
    listing.add_argument('--kind', choices=KINDS)
    listing.add_argument('--user', dest='uploader')
    listing.add_argument('--pending', action='store_true', help='Include open team contribution PRs')
    listing.add_argument('--limit', type=int, default=50)
    listing.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            records = list_runs(args.repository, kind=args.kind, uploader=args.uploader,
                                pending=args.pending, limit=args.limit)
            if args.json:
                print(json.dumps(records, ensure_ascii=False, indent=2))
            else:
                for row in records:
                    print(row['kind']+' | '+row['uploader']+' | '+row['title']+' | '+row['run_id'][:12]+
                          (' | HF-PR' if row.get('pr_url') else ''))
                    print(row['url'])
                if not records:
                    print('Keine passenden Läufe gefunden. Für offene Beiträge --pending verwenden.')
            return 0
        receipt = share_run(args.directory, args.repository, dry_run=args.dry_run, **options(args))
        if args.dry_run:
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
        else:
            show_receipt(receipt)
        return 0
    except (HfHubHTTPError, LocalTokenNotFoundError) as error:
        print('HF-Zugriff fehlgeschlagen: '+str(error)+'\nMit hf auth login im eigenen Konto anmelden. '
              'Bei manuellem Dataset-Zugriff muss dieses Konto zuerst freigeschaltet sein. '
              'Für Beiträge ohne direktes Schreibrecht --submit verwenden.', file=sys.stderr)
        return 2
    except (ValueError, OSError, RuntimeError, KeyError, HTTPError) as error:
        print('Fehler: '+str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
