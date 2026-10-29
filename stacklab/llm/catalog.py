"""Pinned model catalog, verified downloads and local runtime installation."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import tarfile
import urllib.request
import zipfile

from stacklab.paths import ROOT, CACHE_ROOT, REGISTRY_PATH
DOWNLOAD_RESERVE_BYTES = 512*1024*1024


def lock(model=None, device='cpu'):
    if device not in ('cpu', 'cuda'):
        raise ValueError('device must be cpu or cuda')
    registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    if 'models' in registry:
        key = model or registry['default_model']
        if key not in registry['models']:
            query = str(key).casefold()
            matches = [k for k, v in registry['models'].items()
                       if query in {str(name).casefold() for name in
                                    (k, v['model_id'], v['model_id'].rsplit('/', 1)[-1], *v.get('aliases', []))}]
            if len(matches) > 1:
                raise ValueError('Ambiguous model name; use a catalog alias or full model ID')
            key = matches[0] if matches else None
        if key is None or key not in registry['models']:
            raise ValueError('Unknown model. Use python -m stacklab models for the available aliases.')
        config = {k: v for k, v in registry.items() if k not in ('models', 'default_model')}
        config.update(registry['models'][key], model_key=key)
    else:
        config = registry  # Read older single-model locks and archived configurations.
    total, ceiling = config['total_parameters'], config.get('max_total_parameters')
    if type(total) is not int or total <= 0:
        raise ValueError('total_parameters must be a positive integer')
    if ceiling is not None and (type(ceiling) is not int or ceiling <= 0 or total > ceiling):
        raise ValueError('Model exceeds the configured total-parameter budget')
    if device == 'cuda':
        spec = json.loads((ROOT/'config/cuda.runtime.lock.json').read_text(encoding='utf-8'))
        mode = os.environ.get('STACKLAB_CUDA_RUNTIME', 'auto')
        if mode not in ('auto', 'binary', 'source'):
            raise ValueError('STACKLAB_CUDA_RUNTIME must be auto, binary or source')
        libc, libc_version = platform.libc_ver()
        old_glibc = (libc == 'glibc' and libc_version and
                     tuple(map(int, libc_version.split('.'))) < tuple(map(int, spec['minimum_binary_glibc'].split('.'))))
        if platform_key() not in spec['runtime_assets']:
            raise ValueError('Pinned CUDA support currently targets Linux x86-64, including Colab L4/A100')
        if config.get('runtime_source'):
            config.update(runtime_version=config['runtime_version']+'-cuda', device='cuda',
                          cuda_architectures=spec['source_cuda_architectures'], cuda_runtime_kind='source',
                          cuda_flash_attention_quants=spec['source_flash_attention_quants'])
        else:
            if config['runtime_version'] != spec['base_runtime_version']:
                raise ValueError('No pinned CUDA recipe for '+config['runtime_version'])
            if mode == 'source' or mode == 'auto' and old_glibc:
                config.update(runtime_version=config['runtime_version']+'-cuda-source', device='cuda',
                              runtime_source=dict(repository=spec['source_repository'], revision=spec['source_revision']),
                              cuda_architectures=spec['source_cuda_architectures'], cuda_runtime_kind='source',
                              cuda_flash_attention_quants=spec['source_flash_attention_quants'])
            else:
                config.update(runtime_version=spec['runtime_version'], runtime_assets=spec['runtime_assets'],
                              runtime_dependencies=spec['runtime_dependencies'], device='cuda', cuda_runtime_kind='binary')
    return config


def model_keys():
    registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    return list(registry.get('models', {'qwen4b': registry}))


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
    headers = {'User-Agent': 'StackLab-local-LLM/2.6.1'}
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
    if device != 'cpu':
        raise ValueError('device must be cpu or cuda')
    config = lock(model)
    key = platform_key()
    if config.get('runtime_source'):
        from stacklab.llm.source_runtime import build_runtime, cmake_executable, ready_runtime
        if not ready_runtime(config, CACHE_ROOT/'runtime'/config['runtime_version']):
            cmake_executable()  # Diagnose missing build tools before a multi-GB download.
        weights = CACHE_ROOT/'models'/config['model_filename']
        download(config['model_url'], weights, config['model_sha256'], config['model_bytes'])
        executable = build_runtime(config, CACHE_ROOT/'runtime'/config['runtime_version'])
        print('Local model and pinned source runtime verified: '+str(executable), flush=True)
        return executable
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
    """Install pinned binaries/libraries, or the model-specific source build; no weights."""
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
            return find_executable(config['model_key'], device='cuda')
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


def find_executable(model=None, device='cpu'):
    config = lock(model, device=device)
    directory = CACHE_ROOT/'runtime'/config['runtime_version']
    if config.get('runtime_source'):
        from stacklab.llm.source_runtime import ready_runtime
        executable = ready_runtime(config, directory)
        if executable:
            return executable
        raise ValueError('Pinned source runtime missing or changed. Run python -m stacklab setup --model '+
                         config['model_key']+(' --device cuda' if device == 'cuda' else ''))
    if device == 'cuda':
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
        raise ValueError('Pinned CUDA runtime missing or changed. Run stacklab setup --device cuda --model '+config['model_key'])
    suffix = '.exe' if os.name == 'nt' else ''
    for name in ('llama-server',):
        matches = list(directory.rglob(name+suffix)) if directory.exists() else []
        if matches:
            return matches[0].resolve()
    raise ValueError('Local runtime missing. Run python -m stacklab setup first.')


def runtime_env(executable):
    env = os.environ.copy()
    # Also works when /proc/self/exe is unavailable: the cwd is the runtime folder.
    env.pop('GGML_BACKEND_PATH', None)
    if platform.system() == 'Linux':
        root = next((p for p in executable.parents if (p/'installed.json').is_file()), executable.parent)
        directories = [executable.parent, *sorted({p.parent for p in root.rglob('*.so*')})]
        paths = list(dict.fromkeys(str(p) for p in directories))
        if env.get('LD_LIBRARY_PATH'):
            paths.append(env['LD_LIBRARY_PATH'])
        env['LD_LIBRARY_PATH'] = os.pathsep.join(paths)
    return env

