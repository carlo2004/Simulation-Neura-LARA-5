"""First local-model pilot: natural language -> bounded Python -> independent physics check."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from core import Config, write_json
from llm_runtime import ROOT, generate, lock, setup
from policy_language import validate

CASES = {
    'red-on-blue': ('Staple den roten Würfel auf den blauen Würfel.', 'red', 'blue', 'scenario.json', 0),
    'blue-on-red': ('Staple den blauen Würfel auf den roten Würfel.', 'blue', 'red', 'scenario.json', .015),
    'green-on-blue': ('Staple den grünen Würfel auf den blauen Würfel.', 'green', 'blue', 'scenes/three_cubes.json', .015),
}


def run_case(name, args, directory):
    instruction, source, target, filename, jitter = CASES[name]
    config = replace(Config.load(ROOT/filename), seed=args.seed, random_jitter_m=jitter)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory/'scene.json', config.to_dict())
    user = dict(instruction=args.instruction or instruction,
                objects=[dict(name=s.name, shape=s.shape, full_size_m=s.dimensions()) for s in config.object_specs()],
                units='metres', table_z=0, suggested_transport_z=config.hover_z_m)
    system = (ROOT/'LLM_API.md').read_text(encoding='utf-8')
    result = dict(case=name, instruction=user['instruction'], source=source, target=target,
                  success=False, stage='generation', seed=args.seed)
    print('Generate: '+name, flush=True)
    try:
        program, metadata = generate(system, json.dumps(user, ensure_ascii=False), directory,
                                     max_tokens=args.max_tokens, seed=args.seed,
                                     threads=args.threads, timeout=args.generation_timeout, thinking=args.thinking)
        result['generation'] = metadata
        result['stage'] = 'validation'
        validate(program)
        print('Generated program validated. Running real contact physics...', flush=True)
        result['stage'] = 'execution'
        command = [sys.executable, str(ROOT/'llm_worker.py'), '--config', str(directory/'scene.json'),
                   '--code', str(directory/'generated.py'), '--result', str(directory/'execution.json'),
                   '--source', source, '--target', target]
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
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     timeout=args.execution_timeout)
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


def main():
    parser = argparse.ArgumentParser(description='Run the first local 7B-budget model pilot')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('setup', help='Download and SHA-256-verify model and CPU runtime')
    test = sub.add_parser('test', help='Generate a program and test it in MuJoCo')
    test.add_argument('--case', choices=CASES, default='red-on-blue')
    test.add_argument('--suite', action='store_true', help='Run three development cases')
    test.add_argument('--instruction', help='Override wording; expected source/target remain those of --case')
    test.add_argument('--gui', action='store_true', help='Show the generated program acting in the native viewer')
    test.add_argument('--axes', action='store_true', help='Optional coordinate overlay')
    test.add_argument('--stackviz', action='store_true', help='Optional independent evaluation overlay')
    test.add_argument('--thinking', action='store_true', help='Enable reasoning; defaults to a 2048-token output budget')
    test.add_argument('--seed', type=int, default=42)
    test.add_argument('--max-tokens', type=int)
    test.add_argument('--threads', type=int, default=min(8, os.cpu_count() or 1))
    test.add_argument('--generation-timeout', type=int, default=300)
    test.add_argument('--execution-timeout', type=int, default=180)
    test.add_argument('--output', type=Path, help='New output directory; existing nonempty directories are rejected')
    args = parser.parse_args()
    try:
        if args.command == 'setup':
            setup()
            return 0
        if args.max_tokens is None:
            args.max_tokens = 2048 if args.thinking else 768
        if not 128 <= args.max_tokens <= 3072 or not 1 <= args.threads <= 64:
            raise ValueError('max-tokens must be 128–3072; threads must be 1–64')
        if not 10 <= args.generation_timeout <= 1800 or not 10 <= args.execution_timeout <= 600:
            raise ValueError('Generation timeout: 10–1800 s; execution timeout: 10–600 s')
        if args.suite and args.instruction:
            raise ValueError('Use --instruction for one case, not --suite')
        directory = (args.output or ROOT/'output'/('llm_'+time.strftime('%Y%m%d_%H%M%S'))).resolve()
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Choose a new output directory to preserve previous test evidence')
        names = list(CASES) if args.suite else [args.case]
        results = [run_case(name, args, directory/name) for name in names]
        report = dict(model=lock(), passed=sum(r['success'] for r in results), total=len(results),
                      results=results, note='Development pilot; not a held-out scientific evaluation')
        write_json(directory/'summary.json', report)
        print(f'{report["passed"]}/{report["total"]} successful; results: {directory}', flush=True)
        return 0 if report['passed'] == report['total'] else 1
    except (ValueError, OSError, RuntimeError) as error:
        print('Error: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
