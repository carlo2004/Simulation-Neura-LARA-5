"""Plan, run and inspect a small reproducible development comparison."""
import argparse
import os
from pathlib import Path
import sys
import subprocess

from stacklab.cli.benchmark import CASES
from stacklab.experiments import create_plan, run_plan, write_report
from stacklab.llm.catalog import model_keys


def main(argv=None):
    parser = argparse.ArgumentParser(description='Reproducible development comparisons with local physics')
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='Freeze cases, models, seeds and budgets before execution')
    plan.add_argument('--output', type=Path, required=True, help='New empty experiment directory')
    plan.add_argument('--models', nargs='+', required=True)
    plan.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    plan.add_argument('--video', action='store_true')
    plan.add_argument('--recording', choices=['slim', 'full'], default='full')
    plan.add_argument('--motion-fps', type=int, default=0)
    plan.add_argument('--gui', action='store_true')
    plan.add_argument('--server-url', help='SSH loopback URL of a benchmark-enabled model server')
    plan.add_argument('--paired-seeds', action='store_true', help='Zip scene/generation seeds instead of a Cartesian product')
    plan.add_argument('--cases', nargs='+', choices=CASES, default=['move-right', 'red-on-blue'])
    plan.add_argument('--scene-seeds', type=int, nargs='+', default=[42])
    plan.add_argument('--generation-seeds', type=int, nargs='+', default=[42])
    plan.add_argument('--blocks', type=int, nargs='+', default=[1, 4])
    plan.add_argument('--max-tokens', type=int, default=2048)
    plan.add_argument('--threads', type=int, default=min(8, os.cpu_count() or 1))
    plan.add_argument('--thinking', action=argparse.BooleanOptionalAction, default=None)
    plan.add_argument('--thinking-budget', type=int)
    plan.add_argument('--prompt-profile', choices=['auto', 'legacy', 'one-shot'], default='auto')
    plan.add_argument('--generation-timeout', type=int, default=600)
    plan.add_argument('--execution-timeout', type=int, default=180)
    pilot = sub.add_parser('pilot', help='Plan and run ten trials per model with automatic remote model changes')
    pilot.add_argument('--output', type=Path, required=True)
    pilot.add_argument('--server-url', required=True)
    pilot.add_argument('--models', nargs='+', default=['all'])
    pilot.add_argument('--repetitions', type=int, default=5, help='Paired trials for EACH task; 5 x 2 tasks = 10/model')
    pilot.add_argument('--cases', nargs='+', choices=CASES, default=['move-right', 'red-on-blue-jitter'])
    pilot.add_argument('--blocks', nargs='+', type=int, default=[1], help='One-block screening by default; select 4 for feedback trials')
    pilot.add_argument('--max-tokens', type=int, default=2048)
    pilot.add_argument('--prompt-profile', choices=['auto', 'legacy', 'one-shot'], default='auto')
    pilot.add_argument('--generation-timeout', type=int, default=180)
    pilot.add_argument('--execution-timeout', type=int, default=180)
    pilot.add_argument('--recording', choices=['slim', 'full'], default='slim')
    pilot.add_argument('--motion-fps', type=int, default=10, help='Small pose records for later replay; 0 disables them')
    pilot.add_argument('--video', action=argparse.BooleanOptionalAction, default=None,
                       help='Encode video during the trial; default off in slim, on in full mode')
    pilot.add_argument('--gui', action='store_true', help='Watch the local viewer; use identically on both GPUs')
    pilot.add_argument('--backup-dir', type=Path)
    pilot.add_argument('--publish', metavar='OWNER/REPO', help='Publish evidence as a GitHub Release after the run')
    comparison = sub.add_parser('compare', help='Compare matching L4/A100 plans without rerunning inference')
    comparison.add_argument('directories', type=Path, nargs='+')
    comparison.add_argument('--output', type=Path, required=True)
    publication = sub.add_parser('publish', help='Upload recorded raw data/video and reports as a GitHub Release')
    publication.add_argument('directory', type=Path)
    publication.add_argument('--repository', required=True)
    review = sub.add_parser('review', help='Build an offline HTML report with prompts, code, timing and optional videos')
    review.add_argument('directory', type=Path)
    review.add_argument('--include-reasoning', action='store_true', help='Include actual model-provided reasoning, folded by default')
    review.add_argument('--videos', type=int, default=0, help='Render at most N sample clips from saved poses')
    replay = sub.add_parser('replay', help='Render a recorded episode; no inference or physics evaluation')
    replay.add_argument('directory', type=Path, help='episode-... directory containing motion.jsonl and scene.json')
    replay.add_argument('--output', type=Path)
    for command, help_text in [('run', 'Run pending episodes; preserve existing attempts'),
                                ('report', 'Rebuild JSON, CSV and Markdown without starting a model'),
                                ('backup', 'Save existing raw evidence and reports in an atomic ZIP')]:
        child = sub.add_parser(command, help=help_text)
        child.add_argument('directory', type=Path)
        if command == 'run':
            child.add_argument('--backup-dir', type=Path, help='Checkpoint after each episode, e.g. a mounted Drive folder')
            child.add_argument('--publish', metavar='OWNER/REPO')
        if command == 'backup':
            child.add_argument('--output', type=Path, required=True, help='Destination folder outside the experiment')
    args = parser.parse_args(argv)
    try:
        if args.command == 'review':
            from stacklab.review import write_review
            print(write_review(args.directory, include_reasoning=args.include_reasoning, videos=args.videos))
            return 0
        if args.command == 'replay':
            from stacklab.sim.recording import render_replay
            output = (args.output or args.directory/'simulation.mp4').resolve()
            print(render_replay(args.directory, output))
            print('Video: '+str(output))
            if (output == (args.directory/'simulation.mp4').resolve()
                    and (args.directory.parent/'manifest.json').is_file()):
                from stacklab.review import write_review
                print(write_review(args.directory.parent))
            return 0
        if args.command == 'compare':
            from stacklab.comparison import compare_experiments
            compare_experiments(args.directories, args.output)
            print('Comparison: '+str(args.output.resolve()/'comparison.md'))
            return 0
        if args.command == 'publish':
            from stacklab.publication import publish_experiment
            print(publish_experiment(args.directory, args.repository))
            return 0
        if args.command == 'backup':
            from stacklab.backup import backup_experiment
            print(backup_experiment(args.directory, args.output))
            return 0
        if args.command == 'pilot':
            if not 1 <= args.repetitions <= 10000:
                raise ValueError('repetitions must be 1–10000')
            models = model_keys() if args.models == ['all'] else args.models
            frozen = create_plan(args.output, models=models, cases=args.cases,
                scene_seeds=list(range(100, 100+args.repetitions)),
                generation_seeds=list(range(1000, 1000+args.repetitions)), paired_seeds=True,
                blocks=args.blocks, max_tokens=args.max_tokens, server_url=args.server_url,
                video=(args.video if args.video is not None else args.recording == 'full'),
                gui=args.gui, generation_timeout=args.generation_timeout,
                execution_timeout=args.execution_timeout, recording=args.recording, motion_fps=args.motion_fps,
                prompt_profile=args.prompt_profile)
            print(f'{len(frozen["episodes"])} planned episodes; all outputs: {args.output.resolve()}', flush=True)
            report = run_plan(args.output, backup_dir=args.backup_dir)
            from stacklab.review import write_review
            print('Review: '+str(write_review(args.output, report=report)), flush=True)
            if args.publish:
                from stacklab.publication import publish_experiment
                print(publish_experiment(args.output, args.publish))
            print('Pilot finished. Observed ranking: '+str(args.output.resolve()/'ranking.md'), flush=True)
            return 0 if report['complete'] else 1
        if args.command == 'plan':
            options = vars(args).copy()
            options.pop('command')
            directory = options.pop('output')
            if options['models'] == ['all']:
                options['models'] = model_keys()
            frozen = create_plan(directory, **options)
            write_report(directory)
            print(f'{len(frozen["episodes"])} planned episodes: {directory.resolve()}')
            print('Install selected models with stacklab setup, then: stacklab experiment run '+str(directory))
            return 0
        report = run_plan(args.directory, backup_dir=args.backup_dir) if args.command == 'run' else write_report(args.directory)
        from stacklab.review import write_review
        write_review(args.directory, report=report)
        if args.command == 'run' and args.publish:
            from stacklab.publication import publish_experiment
            print(publish_experiment(args.directory, args.publish))
        success = sum(g['success'] for g in report['groups'])
        print(f'{success}/{report["planned"]} planned episodes physically successful; '
              f'complete={report["complete"]}; report: {args.directory.resolve()}/report.md')
        if args.command == 'report':
            return 0
        return 0 if success == report['planned'] else 1
    except KeyboardInterrupt:
        print('Interrupted; existing evidence was preserved. Run again to process only pending episodes.', file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, KeyError, subprocess.CalledProcessError) as error:
        print('Error: '+str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
