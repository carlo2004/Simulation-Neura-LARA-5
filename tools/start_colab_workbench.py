"""Start the live LARA 5 runner and optional GGUF model pair in a Colab runtime."""
import argparse
from contextlib import ExitStack, closing
from ctypes.util import find_library
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from tempfile import mkdtemp
import time

from stacklab.llm.catalog import cuda_runtime, install_cuda_runtime, runtime_env, sha256
from stacklab.llm.hardware import check_cuda_backend, gpu_inventory, gpu_offload
from stacklab.paths import ROOT, RUNS_ROOT


def gguf(path):
    path = path.expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != '.gguf':
        raise ValueError(f'Expected an existing .gguf file: {path}')
    return path


def gguf_identity(path):
    return dict(file=path.name, sha256=sha256(path), bytes=path.stat().st_size)


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def cuda_server():
    config = cuda_runtime()
    if config.get('cuda_runtime_kind') == 'source' and not shutil.which('nvcc'):
        cuda_bin = Path('/usr/local/cuda/bin')
        if (cuda_bin/'nvcc').is_file():
            os.environ['PATH'] = str(cuda_bin) + os.pathsep + os.environ.get('PATH', '')
    return install_cuda_runtime(config)


def launch_model(executable, env, weights, adapter, key, log, cleanup, gpu_layers):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    command = [str(executable), '--model', str(weights), '--alias', key,
               '--host', '127.0.0.1', '--port', str(port), '--ctx-size', '4096',
               '--threads', '2', '--parallel', '1', '--jinja', '--reasoning', 'auto',
               '--gpu-layers', str(gpu_layers), '-lv', '5']
    if adapter:
        command.extend(['--lora', str(adapter)])
    print(f'Lade {key} · Log {log}', flush=True)
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.Popen(command, cwd=executable.parent, env=env, stdout=output, stderr=output,
                                   start_new_session=True)
    cleanup.callback(stop, process)
    deadline = time.monotonic() + 300
    while process.poll() is None and time.monotonic() < deadline:
        try:
            with closing(http.client.HTTPConnection('127.0.0.1', port, timeout=2)) as conn:
                conn.request('GET', '/health')
                response = conn.getresponse()
                if response.status == 200:
                    with log.open(encoding='utf-8', errors='replace') as stream:
                        details = gpu_offload(stream.read())
                    print(f"{key} bereit · {details['offloaded_layers']}/{details['total_layers']} GPU-Layer", flush=True)
                    return f'http://127.0.0.1:{port}/v1'
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(.5)
    raise RuntimeError(f'{key} wurde nicht bereit. Siehe {log}.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, help='Basismodell als GGUF')
    tuning = parser.add_mutually_exclusive_group()
    tuning.add_argument('--tuned', type=Path, help='Zusammengeführtes Fine-Tuning als GGUF')
    tuning.add_argument('--lora', type=Path, help='GGUF-LoRA zum angegebenen Basismodell')
    parser.add_argument('--llama-server', type=Path, help='Vorhandener CUDA-llama-server')
    parser.add_argument('--gpu-layers', type=int, default=999)
    parser.add_argument('--render', choices=['osmesa', 'egl'], default='osmesa')
    parser.add_argument('--source', type=Path, help='Lokaler Prompt2Robo-Snapshot')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--origin', action='append', default=[])
    parser.add_argument('--concurrent', type=int, choices=range(1, 5), default=1)
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r'[a-zA-Z0-9_\-]{16,128}', os.environ.get('STACKLAB_WORKBENCH_TOKEN', '')):
            raise ValueError('Setze STACKLAB_WORKBENCH_TOKEN im Colab-Terminal.')
        if not 1 <= args.port <= 65535 or args.gpu_layers < 1:
            raise ValueError('Wähle einen gültigen Port und mindestens einen GPU-Layer.')
        if args.base is None and (args.tuned or args.lora or args.llama_server):
            raise ValueError('Gib das Basismodell mit --base an.')
        base = gguf(args.base) if args.base else None
        tuned = gguf(args.tuned) if args.tuned else None
        adapter = gguf(args.lora) if args.lora else None
        if args.render == 'osmesa' and not find_library('OSMesa'):
            raise ValueError('Installiere auf Colab libosmesa6 vor dem Start.')
        env = dict(os.environ, MUJOCO_GL=args.render, PYOPENGL_PLATFORM=args.render)
        preflight = (
            'from contextlib import closing; import mujoco; from stacklab.sim.robot import Simulation\n'
            'with closing(Simulation()) as sim, mujoco.Renderer(sim.model, 720, 960) as renderer:\n'
            '    assert sim.render_frame(renderer).shape == (720, 960, 3)\n'
        )
        subprocess.run([sys.executable, '-c', preflight], cwd=ROOT, env=env, check=True)
        command = [sys.executable, '-m', 'stacklab', 'workbench', '--port', str(args.port),
                   '--concurrent', str(args.concurrent)]
        for origin in args.origin:
            command.extend(['--origin', origin])
        if args.source:
            command.extend(['--source', str(args.source.resolve())])

        with ExitStack() as cleanup:
            if base:
                devices = gpu_inventory(required=True)
                print('GPU: ' + ', '.join(f"{d['name']} ({d['memory_total_mib']} MiB)" for d in devices), flush=True)
                executable = args.llama_server.resolve() if args.llama_server else cuda_server()
                model_env = runtime_env(executable)
                model_env.pop('STACKLAB_WORKBENCH_TOKEN', None)
                model_env.pop('HF_TOKEN', None)
                check_cuda_backend(executable, model_env)
                RUNS_ROOT.mkdir(parents=True, exist_ok=True)
                directory = Path(mkdtemp(prefix='colab-workbench-', dir=RUNS_ROOT))
                models = {}
                tuned_weights = tuned or (base if adapter else None)
                artifacts = {path: gguf_identity(path) for path in dict.fromkeys(
                    path for path in (base, tuned, adapter) if path is not None)}
                for key, label, weights, lora in (
                        ('base', 'Basismodell', base, None),
                        ('tuned', 'Fine-Tuning', tuned_weights, adapter)):
                    if weights:
                        url = launch_model(executable, model_env, weights, lora, key,
                                           directory/(key + '.log'), cleanup, args.gpu_layers)
                        models[key] = dict(label=label, protocol='openai', url=url, model=key,
                                           weights=artifacts[weights])
                        if lora:
                            models[key]['adapter'] = artifacts[lora]
                catalog = directory/'models.json'
                catalog.write_text(json.dumps(models, indent=2)+'\n', encoding='utf-8')
                command.extend(['--models', str(catalog)])
            return subprocess.run(command, cwd=ROOT, env=env).returncode
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Colab-Runner: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
