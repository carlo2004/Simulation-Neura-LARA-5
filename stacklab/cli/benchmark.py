"""First local-model pilot: natural language -> bounded Python -> independent physics check."""
from stacklab.paths import ROOT, CACHE_ROOT
from stacklab.paths import RUNS_ROOT
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from stacklab.config import Config, write_json
from stacklab.llm.catalog import lock, setup, model_keys

CASES = {
    'red-on-blue': ('Staple den roten Würfel auf den blauen Würfel.', 'red', 'blue', 'scenes/default.json', 0),
    'blue-on-red': ('Staple den blauen Würfel auf den roten Würfel.', 'blue', 'red', 'scenes/default.json', .015),
    'green-on-blue': ('Staple den grünen Würfel auf den blauen Würfel.', 'green', 'blue', 'scenes/three_cubes.json', .015),
    'move-right': ('Bewege den Greifer um 5 cm nach rechts, ohne die Höhe zu verändern.', None, None, 'scenes/default.json', 0),
}


def run_case(name, args, directory):
    instruction, source, target, filename, jitter = CASES[name]
    config = replace(Config.load(ROOT/filename), seed=args.seed, random_jitter_m=jitter)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory/'scene.json', config.to_dict())
    user = dict(instruction=args.instruction or instruction,
                objects=[dict(name=s.name, shape=s.shape, full_size_m=s.dimensions()) for s in config.object_specs()],
                units='metres', table_z=0, suggested_transport_z=config.hover_z_m)
    result = dict(case=name, instruction=user['instruction'], source=source, target=target,
                  success=False, stage='generation', seed=args.seed)
    print('Generate: '+name, flush=True)
    try:
        result['stage'] = 'execution'
        command = [sys.executable, '-m', 'stacklab.cli.worker', '--config', str(directory/'scene.json'),
                   '--result', str(directory/'execution.json')]
        if source is None:
            command += ['--move-delta', '.05', '0', '0']
        else:
            command += ['--source', source, '--target', target]
        command += ['--feedback-rounds', str(args.feedback_rounds), '--model', lock(args.model)['model_key'],
                    '--instruction', user['instruction'], '--max-tokens', str(args.max_tokens),
                    '--threads', str(args.threads), '--seed', str(args.seed),
                    '--generation-timeout', str(args.generation_timeout),
                    '--execution-timeout', str(args.execution_timeout),
                    '--thinking' if args.thinking else '--no-thinking']
        if args.thinking_budget is not None:
            command += ['--thinking-budget', str(args.thinking_budget)]
        if args.gui:
            if sys.platform == 'darwin':
                mjpython = Path(sys.executable).with_name('mjpython')
                if not mjpython.is_file():
                    raise ValueError('For macOS GUI install MuJoCo in the same .venv (mjpython missing)')
                command[0] = str(mjpython)
            command.append('--gui')
        if args.axes:
            command.append('--axes')
        if args.stackviz:
            command.append('--stackviz')
        env = os.environ.copy()
        env['OPENBLAS_NUM_THREADS'] = '1'
        with (directory/'simulation.log').open('w', encoding='utf-8') as log:
            worker_timeout = ((args.generation_timeout+args.execution_timeout+30)*args.feedback_rounds
                              if args.feedback_rounds else args.generation_timeout+args.execution_timeout+30)
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     timeout=worker_timeout)
        if not (directory/'execution.json').is_file():
            raise RuntimeError('Simulation worker did not produce a result; see simulation.log')
        execution = json.loads((directory/'execution.json').read_text())
        result.update(success=execution['success'], stage=execution['stage'], execution=execution,
                      worker_returncode=process.returncode)
    except Exception as error:
        result['error'] = type(error).__name__+': '+str(error)
    write_json(directory/'result.json', result)
    print(('PASS' if result['success'] else 'FAIL')+' '+name+' ('+result['stage']+')', flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Compare local robot-programming models around 8B')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('models', help='List pinned models and their local download status')
    install = sub.add_parser('setup', help='Download and SHA-256-verify model and CPU runtime')
    install.add_argument('--model', help='Model alias or exact Hugging Face model ID')
    install.add_argument('--all', action='store_true', help='Install all four pinned models sequentially')
    test = sub.add_parser('test', help='Generate a program and test it in MuJoCo')
    test.add_argument('--case', choices=CASES, default='red-on-blue')
    test.add_argument('--model', help='Model alias or exact Hugging Face model ID; default: qwen9b')
    test.add_argument('--feedback-rounds', type=int, default=0,
                      help='0: one-block baseline; positive N: up to N blocks using real simulation feedback')
    test.add_argument('--suite', action='store_true', help='Run four development cases')
    test.add_argument('--instruction', help='Override wording; expected source/target remain those of --case')
    test.add_argument('--gui', action='store_true', help='Show the generated program acting in the native viewer')
    test.add_argument('--axes', action='store_true', help='Optional coordinate overlay')
    test.add_argument('--stackviz', action='store_true', help='Optional independent evaluation overlay')
    test.add_argument('--thinking', action=argparse.BooleanOptionalAction, default=None,
                      help='Override model-specific reasoning default')
    test.add_argument('--thinking-budget', type=int, help='Maximum reasoning tokens; -1 for no separate cap')
    test.add_argument('--seed', type=int, default=42)
    test.add_argument('--max-tokens', type=int)
    test.add_argument('--threads', type=int, default=min(8, os.cpu_count() or 1))
    test.add_argument('--generation-timeout', type=int, default=600)
    test.add_argument('--execution-timeout', type=int, default=180)
    test.add_argument('--output', type=Path, help='New output directory; existing nonempty directories are rejected')
    args = parser.parse_args(argv)
    try:
        if args.command == 'models':
            for name in model_keys():
                c = lock(name)
                path = CACHE_ROOT/'models'/c['model_filename']
                status = 'downloaded' if path.is_file() and path.stat().st_size == c['model_bytes'] else 'not downloaded'
                print(f'{name:14} {c["total_parameters"]/1e9:.2f}B total | {c["model_bytes"]/1e9:.2f} GB | {status} | {c["model_id"]}')
            return 0
        if args.command == 'setup':
            if args.all and args.model:
                raise ValueError('Choose --all or --model')
            for name in model_keys() if args.all else [args.model]:
                setup(name)
            return 0
        config = lock(args.model)
        if args.feedback_rounds < 0:
            raise ValueError('feedback-rounds must be non-negative')
        if args.thinking is None:
            args.thinking = config.get('default_thinking', False)
        if args.max_tokens is None:
            args.max_tokens = 2048 if args.thinking else 768
        if min(args.max_tokens, args.threads) < 1:
            raise ValueError('tokens and threads must be positive')
        if min(args.generation_timeout, args.execution_timeout) <= 0:
            raise ValueError('Generation and execution timeouts must be positive')
        if args.suite and args.instruction:
            raise ValueError('Use --instruction for one case, not --suite')
        directory = (args.output or RUNS_ROOT/('llm_'+time.strftime('%Y%m%d_%H%M%S'))).resolve()
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Choose a new output directory to preserve previous test evidence')
        names = list(CASES) if args.suite else [args.case]
        results = [run_case(name, args, directory/name) for name in names]
        report = dict(model=config, passed=sum(r['success'] for r in results), total=len(results),
                      results=results, mode='closed_loop_feedback' if args.feedback_rounds else 'open_loop',
                      feedback_rounds=args.feedback_rounds, note='Development pilot; not a held-out scientific evaluation')
        write_json(directory/'summary.json', report)
        print(f'{report["passed"]}/{report["total"]} successful; results: {directory}', flush=True)
        return 0 if report['passed'] == report['total'] else 1
    except (ValueError, OSError, RuntimeError) as error:
        print('Error: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
