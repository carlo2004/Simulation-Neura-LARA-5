"""Pinned local GGUF inference through a temporary, loopback-only llama.cpp process."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import tarfile
import urllib.request
import zipfile

from stacklab.paths import ROOT
from stacklab.paths import CACHE_ROOT, REGISTRY_PATH
DOWNLOAD_RESERVE_BYTES = 512*1024*1024


def lock(model=None):
    registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    if 'models' in registry:
        key = model or registry['default_model']
        if key not in registry['models']:
            key = next((k for k, v in registry['models'].items() if v['model_id'] == key), None)
        if key is None or key not in registry['models']:
            raise ValueError('Unknown model. Use python -m stacklab models for the available aliases.')
        config = {k: v for k, v in registry.items() if k not in ('models', 'default_model')}
        config.update(registry['models'][key], model_key=key)
    else:
        config = registry  # Read older single-model locks and archived configurations.
    if not 0 < config['total_parameters'] <= config['max_total_parameters'] <= 10_000_000_000:
        raise ValueError('Model exceeds the configured total-parameter limit (maximum 10B)')
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


def setup(model=None):
    config = lock(model)
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


def find_executable(model=None):
    config = lock(model)
    directory = CACHE_ROOT/'runtime'/config['runtime_version']
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
        env['LD_LIBRARY_PATH'] = str(executable.parent)+(os.pathsep+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    return env


def extract_program(raw):
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != '{':
            continue
        try:
            value, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and set(value) == {'code'} and isinstance(value['code'], str):
            return value['code']
    raise ValueError('Model did not return a complete JSON object with one code field')


def generate(system, user, output, *, max_tokens=2048, seed=42, threads=8, timeout=600, thinking=None, model=None, on_delta=None):
    from stacklab.llm.runtime import LocalModel
    with LocalModel(model, threads=threads) as client:
        raw, metadata = client.complete([dict(role='system', content=system), dict(role='user', content=user)],
                                        output, max_tokens=max_tokens, seed=seed, timeout=timeout,
                                        thinking=thinking, on_delta=on_delta)
    program = extract_program(raw)
    (Path(output)/'generated.py').write_text(program.rstrip()+'\n', encoding='utf-8')
    return program, metadata
