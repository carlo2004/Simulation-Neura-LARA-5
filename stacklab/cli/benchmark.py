"""First local-model pilot: natural language -> bounded Python -> independent physics check."""
from stacklab.paths import ROOT, CACHE_ROOT
from stacklab.paths import RUNS_ROOT
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time
from stacklab.config import Config, write_json
from stacklab.llm.catalog import lock, setup, model_keys
from stacklab.cli.speed import format_speed
from stacklab.cli.process import run_logged

CASES = {
    'red-on-blue': ('Staple den roten Würfel auf den blauen Würfel.', 'red', 'blue', 'scenes/default.json', 0),
    'blue-on-red': ('Staple den blauen Würfel auf den roten Würfel.', 'blue', 'red', 'scenes/default.json', .015),
    'green-on-blue': ('Staple den grünen Würfel auf den blauen Würfel.', 'green', 'blue', 'scenes/three_cubes.json', .015),
    'move-right': ('Bewege den Greifer um 5 cm nach rechts, ohne die Höhe zu verändern.', None, None, 'scenes/default.json', 0),
    'move-forward': ('Bewege den Greifer um 5 cm nach vorne, ohne die Höhe zu verändern.', None, None, 'scenes/default.json', 0),
    'move-up': ('Bewege den Greifer um 5 cm nach oben.', None, None, 'scenes/default.json', 0),
    'red-on-blue-jitter': ('Staple den roten Würfel auf den blauen Würfel.', 'red', 'blue', 'scenes/default.json', .015),
}


def case_definition(name, scene_seed):
    instruction, source, target, filename, jitter = CASES[name]
    config = replace(Config.load(ROOT/filename), seed=scene_seed, random_jitter_m=jitter)
    return dict(name=name, instruction=instruction, source=source, target=target,
                scene_seed=scene_seed, config=config.to_dict(), initial_object_positions=config.scene(),
                goal=dict(type='stack', source=source, target=target) if source else
                dict(type='move', delta_m={'move-right': [.05, 0, 0], 'move-forward': [0, .05, 0],
                                         'move-up': [0, 0, .05]}[name]))


def run_case(name, args, directory, *, case=None):
    scene_seed = getattr(args, 'scene_seed', None)
    generation_seed = getattr(args, 'generation_seed', None)
    case = case or case_definition(name, args.seed if scene_seed is None else scene_seed)
    config = Config(**case['config']).validate()
    source, target = case['source'], case['target']
    generation_seed = args.seed if generation_seed is None else generation_seed
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory/'scene.json', config.to_dict())
    instruction = args.instruction or case['instruction']
    result = dict(case=name, instruction=instruction, source=source, target=target,
                  success=False, stage='generation', seed=generation_seed,
                  scene_seed=config.seed, generation_seed=generation_seed)
    print('Generate: '+name, flush=True)
    try:
        result['stage'] = 'execution'
        command = [sys.executable, '-m', 'stacklab.cli.worker', '--config', str(directory/'scene.json'),
                   '--result', str(directory/'execution.json')]
        if source is None:
            command += ['--move-delta', *map(str, case['goal']['delta_m'])]
        else:
            command += ['--source', source, '--target', target]
        command += ['--feedback-rounds', str(args.feedback_rounds), '--model', lock(args.model)['model_key'],
                    '--device', getattr(args, 'device', 'cpu'),
                    '--instruction', instruction, '--max-tokens', str(args.max_tokens),
                    '--threads', str(args.threads), '--seed', str(generation_seed),
                    '--generation-timeout', str(args.generation_timeout),
                    '--execution-timeout', str(args.execution_timeout),
                    '--thinking' if args.thinking else '--no-thinking']
        if getattr(args, 'server_url', None):
            command += ['--server-url', args.server_url, '--expected-server-id', args.expected_server_id]
        if getattr(args, 'batch', False):
            command += ['--result-hold-seconds', '0']
        command += ['--recording', getattr(args, 'recording', 'full'),
                    '--motion-fps', str(getattr(args, 'motion_fps', 0))]
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
        if getattr(args, 'video', False):
            command += ['--video', str(directory/'simulation.mp4')]
        env = os.environ.copy()
        env['OPENBLAS_NUM_THREADS'] = '1'
        with (directory/'simulation.log').open('w', encoding='utf-8') as log:
            worker_timeout = ((args.generation_timeout+args.execution_timeout+30)*args.feedback_rounds
                              if args.feedback_rounds else args.generation_timeout+args.execution_timeout+30)
            process = run_logged(command, log, cwd=ROOT, env=env, timeout=worker_timeout,
                                 on_progress=lambda line: print(line, flush=True))
        if not (directory/'execution.json').is_file():
            raise RuntimeError('Simulation worker did not produce a result; see simulation.log')
        execution = json.loads((directory/'execution.json').read_text(encoding='utf-8'))
        result.update(success=execution['success'], stage=execution['stage'], execution=execution,
                      worker_returncode=process.returncode)
        if execution.get('inference_performance', {}).get('measured_rounds'):
            print('[Inferenz] '+format_speed(execution['inference_performance']), flush=True)
    except Exception as error:
        result['error'] = type(error).__name__+': '+str(error)
        # A timed-out worker can still finish writing partial native token counters.
        if (directory/'execution.json').is_file():
            try:
                result['execution'] = json.loads((directory/'execution.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
    write_json(directory/'result.json', result)
    print(('PASS' if result['success'] else 'FAIL')+' '+name+' ('+result['stage']+')', flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Compare local robot-programming models')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('models', help='List pinned models and their local download status')
    install = sub.add_parser('setup', help='Download and SHA-256-verify model and CPU runtime')
    install.add_argument('--model', help='Model alias or exact Hugging Face model ID')
    install.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    install.add_argument('--all', action='store_true', help='Install all catalog models sequentially')
    test = sub.add_parser('test', help='Generate a program and test it in MuJoCo')
    test.add_argument('--case', choices=CASES, default='red-on-blue')
    test.add_argument('--model', help='Model alias or exact Hugging Face model ID; default: qwen9b')
    test.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    test.add_argument('--video', action='store_true', help='Record actual simulated execution to simulation.mp4')
    test.add_argument('--feedback-rounds', type=int, default=0,
                      help='0: one-block baseline; positive N: up to N blocks using real simulation feedback')
    test.add_argument('--suite', action='store_true', help='Run all development cases')
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
                runtime = 'source build' if c.get('runtime_source') else c['runtime_version']
                print(f'{name:14} {c["total_parameters"]/1e9:.2f}B total | {c["quantization"]} | '
                      f'{c["model_bytes"]/1e9:.2f} GB | {status} | {runtime} | {c["model_id"]}')
                tokenizer = c.get('tokenizer')
                if tokenizer:
                    print(f'  Tokenizer: {tokenizer["tokenizer_class"]} ({tokenizer["algorithm"]}) | '
                          f'{tokenizer["repository"]}@{tokenizer["revision"][:12]} | GGUF / llama.cpp')
            return 0
        if args.command == 'setup':
            if args.all and args.model:
                raise ValueError('Choose --all or --model')
            for name in model_keys() if args.all else [args.model]:
                setup(name, device=args.device)
            return 0
        config = lock(args.model, device=args.device)
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
