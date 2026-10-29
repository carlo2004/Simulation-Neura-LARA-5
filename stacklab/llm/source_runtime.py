"""Build a model-specific, pinned llama.cpp runtime without replacing other runtimes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from stacklab.llm.catalog import platform_key, sha256

BUILD_FLAGS = ['-DCMAKE_BUILD_TYPE=Release', '-DGGML_NATIVE=OFF', '-DGGML_CUDA=OFF',
               '-DGGML_METAL=OFF', '-DGGML_OPENMP=OFF', '-DLLAMA_BUILD_SERVER=ON',
               '-DLLAMA_BUILD_UI=OFF', '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_EXAMPLES=OFF']


def build_flags(config):
    if config.get('device') == 'cuda':
        flags = [flag.replace('GGML_CUDA=OFF', 'GGML_CUDA=ON') for flag in BUILD_FLAGS]+[
            '-DCMAKE_CUDA_ARCHITECTURES='+';'.join(map(str, config.get('cuda_architectures', [80, 89])))]
        args = config.get('server_args', [])
        flash_off = any(arg == '--flash-attn' and index+1 < len(args) and args[index+1] == 'off'
                        for index, arg in enumerate(args))
        # Current profiles use f16 KV caches; omit unused quantized-KV FA variants.
        flags.append('-DGGML_CUDA_FA=OFF' if flash_off else
                     '-DGGML_CUDA_FA_QUANTS='+config.get('cuda_flash_attention_quants', 'f16-f16'))
        return flags
    return BUILD_FLAGS


def runtime_identity(config):
    spec = config['runtime_source']
    return dict(repository=spec['repository'], revision=spec['revision'], platform=platform_key(), cmake_flags=build_flags(config))


def ready_runtime(config, directory):
    directory = Path(directory).resolve()
    marker = directory/'installed.json'
    if marker.is_file():
        installed = json.loads(marker.read_text(encoding='utf-8'))
        executable = (directory/installed.get('executable', '')).resolve()
        if (installed.get('source') == runtime_identity(config) and executable.is_relative_to(directory)
                and executable.is_file() and sha256(executable) == installed.get('executable_sha256')):
            return executable
    return None


def cmake_executable():
    local = Path(sys.executable).with_name('cmake.exe' if os.name == 'nt' else 'cmake')
    command = str(local) if local.is_file() else shutil.which('cmake')
    if not command:
        raise ValueError('This model needs a source runtime. Install CMake in this environment '
                         '(python -m pip install cmake) and a C++ compiler; then repeat setup.')
    return command


def build_runtime(config, directory):
    spec = config['runtime_source']
    revision = spec['revision']
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Source runtimes must pin a complete Git commit SHA')
    ready = ready_runtime(config, directory)
    if ready:
        return ready
    if not shutil.which('git'):
        raise ValueError('This model needs Git to fetch its pinned source runtime')
    cmake = cmake_executable()
    if config.get('device') == 'cuda' and not shutil.which('nvcc'):
        raise ValueError('This CUDA source runtime needs the NVIDIA CUDA Toolkit (nvcc), CMake and a C++ compiler')
    directory = Path(directory)
    source = directory/'source'
    build = directory/'build'
    marker = directory/'installed.json'
    flags = build_flags(config)
    identity = runtime_identity(config)
    suffix = '.exe' if os.name == 'nt' else ''
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory/'build.log'
    print('Build pinned '+config.get('device', 'cpu').upper()+' runtime: '+revision+'; log: '+str(log_path), flush=True)
    with log_path.open('a', encoding='utf-8') as log:
        def run(args, cwd=directory):
            if config.get('device') != 'cuda':
                subprocess.run(args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
                return
            with subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, bufsize=1) as process:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    if line.lstrip().startswith('['):
                        print(line.rstrip(), flush=True)
                code = process.wait()
                if code:
                    raise subprocess.CalledProcessError(code, args)
        try:
            if not (source/'.git').is_dir():
                if source.exists() and any(source.iterdir()):
                    raise ValueError('Source cache is not an empty directory: '+str(source))
                source.mkdir(exist_ok=True)
                run(['git', 'init', str(source)])
                run(['git', '-C', str(source), 'config', 'core.autocrlf', 'false'])
                run(['git', '-C', str(source), 'config', 'core.longpaths', 'true'])
                # Keep the pinned blob bytes even with Windows/global line-ending filters.
                attributes = source/'.git/info/attributes'
                attributes.parent.mkdir(parents=True, exist_ok=True)
                attributes.write_text('* -text\n', encoding='utf-8')
                run(['git', '-C', str(source), 'remote', 'add', 'origin', spec['repository']])
            head = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                  capture_output=True, text=True)
            if head.returncode:
                run(['git', '-C', str(source), 'fetch', '--depth', '1', 'origin', revision])
                run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'])
            actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            if actual != revision:
                raise ValueError('Source cache has another revision; move it aside before rebuilding')
            dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain',
                                             '--untracked-files=no'], text=True)
            if dirty.strip():
                log.write('Source cache changes:\n'+dirty+'\n')
                log.flush()
                raise ValueError('Source cache contains changes; move it aside before rebuilding: '+dirty.strip()[:1600])
            run([cmake, '-S', str(source), '-B', str(build), *flags])
            run([cmake, '--build', str(build), '--config', 'Release', '--target', 'llama-server',
                 '--parallel', str(min(2 if config.get('device') == 'cuda' else 4, os.cpu_count() or 1))])
        except subprocess.CalledProcessError as error:
            raise RuntimeError('Runtime build failed. Check CMake/C++ build tools and '+str(log_path)) from error
    candidates = sorted(build.rglob('llama-server'+suffix))
    if not candidates:
        raise RuntimeError('Build produced no llama-server; see '+str(log_path))
    executable = candidates[0].resolve()
    build_tools = {}
    if config.get('device') == 'cuda':
        tool = subprocess.run(['nvcc', '--version'], capture_output=True, text=True, timeout=15, check=True)
        build_tools['nvcc_version'] = tool.stdout+tool.stderr
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(source=identity, executable=str(executable.relative_to(directory.resolve())),
                                         executable_sha256=sha256(executable), build_tools=build_tools),
                                    indent=2)+'\n', encoding='utf-8')
    temporary.replace(marker)
    return executable
