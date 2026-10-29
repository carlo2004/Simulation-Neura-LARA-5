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
            if config.get('cuda_runtime_kind') == 'source':
                if not (python.parent/'cmake').is_file() and not shutil.which('cmake'):
                    run([python, '-m', 'pip', 'install', 'cmake'], env)
                if not shutil.which('g++') or not shutil.which('make'):
                    if sys.platform != 'linux' or os.geteuid() != 0:
                        raise ValueError('Install g++ and make before building the CUDA runtime')
                    run(['apt-get', 'update', '-qq'], env)
                    run(['apt-get', 'install', '-y', '-qq', 'g++', 'make'], env)
                if not shutil.which('nvcc', path=env.get('PATH')):
                    if Path('/usr/local/cuda/bin/nvcc').is_file():
                        env['PATH'] = '/usr/local/cuda/bin:'+env.get('PATH', '')
                    else:
                        raise ValueError('CUDA Toolkit (nvcc) is missing; choose a current GPU runtime')
        run([python, '-m', 'stacklab', 'setup', '--model', args.model, '--device', args.device], env)
        run([python, '-m', 'stacklab', 'doctor', '--model', args.model, '--device', args.device], env)
        run([python, '-m', 'stacklab', 'serve', '--model', args.model, '--device', args.device,
             '--threads', args.threads, '--port', args.port], env)
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Remote setup failed: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
