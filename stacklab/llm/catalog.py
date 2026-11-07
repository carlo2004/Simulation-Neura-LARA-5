"""Verified GGUF downloads and the shared llama.cpp runtime."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile

from stacklab.paths import ROOT, CACHE_ROOT, REGISTRY_PATH
DOWNLOAD_RESERVE_BYTES = 512*1024*1024


def lock(model=None, device='cpu'):
    if device not in ('cpu', 'cuda'):
        raise ValueError('device must be cpu or cuda')
    registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    models = registry['models']
    key = model or registry['default_model']
    if key not in models:
        query = key.casefold()
        matches = [alias for alias, entry in models.items()
                   if query in (alias.casefold(), entry['model_id'].casefold(),
                                entry['model_id'].rsplit('/', 1)[-1].casefold())]
        if len(matches) != 1:
            raise ValueError('Choose a model from the GGUF catalog: '+', '.join(models))
        key = matches[0]
    config = {k: v for k, v in registry.items() if k not in ('models', 'default_model')}
    config.update(models[key], model_key=key)
    if device == 'cuda':
        config.update(cuda_runtime())
    return config


def cuda_runtime():
    """Resolve the pinned Colab runtime independently of the supplied GGUF."""
    spec = json.loads((ROOT/'config/cuda.runtime.lock.json').read_text(encoding='utf-8'))
    mode = os.environ.get('STACKLAB_CUDA_RUNTIME', 'auto')
    if mode not in ('auto', 'binary', 'source'):
        raise ValueError('STACKLAB_CUDA_RUNTIME must be auto, binary or source')
    if platform_key() not in spec['runtime_assets']:
        raise ValueError('Pinned CUDA support targets Linux x86-64, including Colab L4/A100')
    libc, libc_version = platform.libc_ver()
    old_glibc = (libc == 'glibc' and libc_version and
                 tuple(map(int, libc_version.split('.'))) < tuple(map(int, spec['minimum_binary_glibc'].split('.'))))
    if mode == 'source' or mode == 'auto' and old_glibc:
        return dict(runtime_version=spec['base_runtime_version']+'-cuda-source', device='cuda',
                    runtime_source=dict(repository=spec['source_repository'], revision=spec['source_revision']),
                    cuda_architectures=spec['source_cuda_architectures'], cuda_runtime_kind='source',
                    cuda_flash_attention_quants=spec['source_flash_attention_quants'])
    return dict(runtime_version=spec['runtime_version'], runtime_assets=spec['runtime_assets'],
                runtime_dependencies=spec['runtime_dependencies'], device='cuda', cuda_runtime_kind='binary')


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def require_download_space(path, remaining_bytes):
    free = shutil.disk_usage(Path(path).parent).free
    needed = max(0, remaining_bytes)+DOWNLOAD_RESERVE_BYTES
    if free < needed:
        raise OSError(f'Not enough free disk space for {Path(path).name}: need {needed/1e9:.2f} GB '
                      f'including reserve, available {free/1e9:.2f} GB. Free storage or choose another model.')


def download(url, path, expected_sha, expected_bytes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if path.stat().st_size == expected_bytes and sha256(path) == expected_sha:
            return path
        raise ValueError('Existing file failed verification; move it aside before retrying: '+str(path))
    partial = path.with_name(path.name+'.part')
    offset = partial.stat().st_size if partial.exists() else 0
    if offset == expected_bytes:
        if sha256(partial) != expected_sha:
            raise ValueError('Completed partial file failed SHA-256 verification: '+str(partial))
        partial.replace(path)
        return path
    if offset > expected_bytes:
        raise ValueError('Partial file exceeds the expected size: '+str(partial))
    require_download_space(path, expected_bytes-offset)
    headers = {'User-Agent': 'StackLab-Workbench'}
    if offset:
        headers['Range'] = f'bytes={offset}-'
    print('Download: '+path.name, flush=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        append = offset > 0 and response.status == 206
        done = offset if append else 0
        last = done
        with partial.open('ab' if append else 'wb') as stream:
            for block in iter(lambda: response.read(8*1024*1024), b''):
                require_download_space(path, len(block))
                stream.write(block)
                done += len(block)
                if done > expected_bytes:
                    raise ValueError('Download exceeds the expected size')
                if done-last >= 128*1024*1024:
                    print(f'  {done/expected_bytes:.0%}', flush=True)
                    last = done
    if partial.stat().st_size != expected_bytes or sha256(partial) != expected_sha:
        raise ValueError('Download failed size/SHA-256 verification: '+str(partial))
    partial.replace(path)
    return path


def platform_key():
    machine = platform.machine().lower()
    machine = {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(machine, machine)
    system = platform.system().lower()
    return system+'-'+machine


def setup(model=None, device='cpu'):
    if device == 'cuda':
        from stacklab.llm.hardware import gpu_inventory, check_cuda_backend
        gpu_inventory(required=True)
        config = lock(model, device=device)
        executable = install_cuda_runtime(config)
        check_cuda_backend(executable, runtime_env(executable))
        download(config['model_url'], CACHE_ROOT/'models'/config['model_filename'],
                 config['model_sha256'], config['model_bytes'])
        print('Model and CUDA runtime verified: '+str(executable), flush=True)
        return executable
    config = lock(model, device=device)
    key = platform_key()
    if key not in config['runtime_assets']:
        raise ValueError('No pinned CPU runtime for '+key)
    weights = CACHE_ROOT/'models'/config['model_filename']
    download(config['model_url'], weights, config['model_sha256'], config['model_bytes'])
    asset = config['runtime_assets'][key]
    archive = download(asset['url'], CACHE_ROOT/'downloads'/asset['filename'], asset['sha256'], asset['bytes'])
    directory = CACHE_ROOT/'runtime'/config['runtime_version']
    marker = directory/'installed.json'
    if not marker.exists() or json.loads(marker.read_text())['sha256'] != asset['sha256']:
        directory.mkdir(parents=True, exist_ok=True)
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as bundle:
                for entry in bundle.infolist():
                    target = (directory/entry.filename).resolve()
                    if not target.is_relative_to(directory.resolve()) or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Unsafe runtime archive entry')
                bundle.extractall(directory)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(directory, filter='data')
        marker.write_text(json.dumps(dict(sha256=asset['sha256'], platform=key))+'\n')
    executable = find_executable(model)
    print('Local model and runtime verified: '+str(executable), flush=True)
    return executable


def install_cuda_runtime(config):
    """Install the pinned CUDA binaries and libraries or build the same revision."""
    if config.get('device') != 'cuda':
        raise ValueError('Expected an explicitly resolved CUDA configuration')
    directory = CACHE_ROOT/'runtime'/config['runtime_version']
    if config.get('runtime_source'):
        from stacklab.llm.source_runtime import build_runtime
        return build_runtime(config, directory)
    key = platform_key()
    assets = [config['runtime_assets'][key], *config.get('runtime_dependencies', {}).get(key, [])]
    marker = directory/'installed.json'
    expected = [a['sha256'] for a in assets]
    if marker.is_file():
        installed = json.loads(marker.read_text(encoding='utf-8'))
        if installed.get('archive_sha256') == expected:
            return find_cuda_executable(config)
    directory.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        archive = download(asset['url'], CACHE_ROOT/'downloads'/asset['filename'], asset['sha256'], asset['bytes'])
        with tarfile.open(archive) as bundle:
            bundle.extractall(directory, filter='data')
    matches = sorted(directory.rglob('llama-server'))
    if not matches:
        raise ValueError('CUDA archive contains no llama-server')
    executable = matches[0].resolve()
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(archive_sha256=expected, platform=key, device='cuda',
                                         executable=str(executable.relative_to(directory.resolve())),
                                         executable_sha256=sha256(executable)), indent=2)+'\n', encoding='utf-8')
    temporary.replace(marker)
    return executable


def find_cuda_executable(config):
    directory = CACHE_ROOT/'runtime'/config['runtime_version']
    if config.get('runtime_source'):
        from stacklab.llm.source_runtime import ready_runtime
        executable = ready_runtime(config, directory)
        if executable:
            return executable
    else:
        marker = directory/'installed.json'
        if marker.is_file():
            installed = json.loads(marker.read_text(encoding='utf-8'))
            executable = (directory/installed.get('executable', '')).resolve()
            assets = [config['runtime_assets'][platform_key()],
                      *config.get('runtime_dependencies', {}).get(platform_key(), [])]
            if (installed.get('archive_sha256') == [a['sha256'] for a in assets]
                    and executable.is_relative_to(directory.resolve()) and executable.is_file()
                    and sha256(executable) == installed.get('executable_sha256')):
                return executable
    raise ValueError('Pinned CUDA runtime missing or changed. Run the Colab Workbench starter again.')


def find_executable(model=None, device='cpu'):
    config = lock(model, device=device)
    if device == 'cuda':
        return find_cuda_executable(config)
    directory = CACHE_ROOT/'runtime'/config['runtime_version']
    suffix = '.exe' if os.name == 'nt' else ''
    matches = list(directory.rglob('llama-server'+suffix))
    if matches:
        return matches[0].resolve()
    raise ValueError('Local runtime missing. Run python -m stacklab setup first.')


def _cuda_library_directories():
    """Driver and pip-installed CUDA libraries, including outside Colab's venv."""
    directories = [Path('/usr/lib64-nvidia'), Path('/usr/local/cuda/lib64'),
                   Path('/usr/local/nvidia/lib'), Path('/usr/local/nvidia/lib64')]
    package_roots = [Path(p) for p in sys.path if p]
    # Colab can install CUDA wheels into its base Python, while our server uses
    # a separate Python version/environment. No NVIDIA modules need importing.
    for root in dict.fromkeys([Path('/usr/local/lib'), Path(sys.base_prefix)/'lib']):
        for pattern in ('python*/dist-packages', 'python*/site-packages'):
            package_roots.extend(sorted(root.glob(pattern)))
    for root in dict.fromkeys(package_roots):
        for package in ('cuda_runtime', 'cublas'):
            directories.append(root/'nvidia'/package/'lib')
    return [p for p in dict.fromkeys(directories) if p.is_dir()]


def runtime_env(executable):
    executable = Path(executable)
    env = os.environ.copy()
    # Also works when /proc/self/exe is unavailable: the cwd is the runtime folder.
    env.pop('GGML_BACKEND_PATH', None)
    if platform.system() == 'Linux':
        root = next((p for p in executable.parents if (p/'installed.json').is_file()), executable.parent)
        directories = [executable.parent, *sorted({p.parent for p in root.rglob('*.so*')})]
        backends = sorted(root.rglob('libggml-cuda.so'))
        if backends:
            # This is a library filename, not a directory. Load only the backend
            # belonging to the selected pinned runtime, never an inherited one.
            env['GGML_BACKEND_PATH'] = str(backends[0].resolve())
            directories.extend(_cuda_library_directories())
        paths = [str(p) for p in directories]
        paths.extend(p for p in env.get('LD_LIBRARY_PATH', '').split(os.pathsep) if p)
        env['LD_LIBRARY_PATH'] = os.pathsep.join(dict.fromkeys(paths))
    return env
