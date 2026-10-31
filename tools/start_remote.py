"""Prepare a Colab/GPU VM and keep one inference model available over SSH."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args, env=None):
    print('$ '+' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, env=env, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='granite8b')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--cuda-runtime', choices=['auto', 'binary', 'source'], default='auto')
    parser.add_argument('--benchmark', action='store_true', help='Allow automatic catalog model changes and verified installs')
    args = parser.parse_args(argv)
    try:
        if args.threads < 1 or not 0 < args.port < 65536:
            raise ValueError('Use positive threads and a valid port')
        env = dict(os.environ, STACKLAB_CUDA_RUNTIME=args.cuda_runtime)
        if args.device == 'cuda':
            run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv'], env)
        bootstrap_python = sys.executable
        if sys.version_info[:2] not in ((3, 12), (3, 13)):
            run([sys.executable, '-m', 'pip', 'install', 'uv'])
            run([sys.executable, '-m', 'uv', 'python', 'install', '3.12'])
            bootstrap_python = subprocess.check_output([sys.executable, '-m', 'uv', 'python', 'find', '3.12'], text=True).strip()
        run([bootstrap_python, 'bootstrap.py'], env)
        python = ROOT/'.venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if args.device == 'cuda':
            recipe = "import json,sys; from stacklab.llm.catalog import lock; print(json.dumps(lock(sys.argv[1],device='cuda')))"
            config = json.loads(subprocess.check_output([python, '-c', recipe, args.model], cwd=ROOT, env=env, text=True))
            if config.get('cuda_runtime_kind') == 'source' or args.benchmark:
                if not (python.parent/'cmake').is_file() and not shutil.which('cmake'):
                    run([python, '-m', 'pip', 'install', 'cmake'], env)
                if not shutil.which('g++') or not shutil.which('make'):
                    if sys.platform != 'linux' or os.geteuid() != 0:
                        raise ValueError('Install g++ and make before building the CUDA runtime')
                    run(['apt-get', 'update', '-qq'], env)
                    run(['apt-get', 'install', '-y', '-qq', 'g++', 'make'], env)
                compiler_env = ("import json; from stacklab.llm.source_runtime import cuda_build_environment; "
                                "e=cuda_build_environment(); print(json.dumps({k:e[k] for k in ('PATH','CUDACXX')}))")
                env.update(json.loads(subprocess.check_output([python, '-c', compiler_env], cwd=ROOT, env=env, text=True)))
        run([python, '-m', 'stacklab', 'setup', '--model', args.model, '--device', args.device], env)
        run([python, '-m', 'stacklab', 'doctor', '--model', args.model, '--device', args.device], env)
        run([python, '-m', 'stacklab', 'serve', '--model', args.model, '--device', args.device,
             '--threads', args.threads, '--port', args.port,
             *(['--allow-model-switch', '--install-missing'] if args.benchmark else [])], env)
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Remote setup failed: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
