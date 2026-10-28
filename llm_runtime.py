"""Pinned local GGUF inference through a temporary, loopback-only llama.cpp process."""
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import tarfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
CACHE_ROOT = ROOT/'.local_llm'


def lock():
    config = json.loads((ROOT/'local_model.lock.json').read_text(encoding='utf-8'))
    if not 0 < config['total_parameters'] <= config['max_total_parameters'] <= 7_000_000_000:
        raise ValueError('Model exceeds the total-parameter limit of 7B')
    return config


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def download(url, path, expected_sha, expected_bytes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if path.stat().st_size == expected_bytes and sha256(path) == expected_sha:
            return path
        raise ValueError('Existing file failed verification; move it aside before retrying: '+str(path))
    partial = path.with_name(path.name+'.part')
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {'User-Agent': 'StackLab-local-LLM/2.5'}
    if offset:
        headers['Range'] = f'bytes={offset}-'
    print('Download: '+path.name, flush=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        append = offset > 0 and response.status == 206
        done = offset if append else 0
        last = done
        with partial.open('ab' if append else 'wb') as stream:
            for block in iter(lambda: response.read(8*1024*1024), b''):
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


def setup():
    config = lock()
    key = platform_key()
    if key not in config['runtime_assets']:
        raise ValueError('No pinned CPU runtime for '+key)
    model = CACHE_ROOT/'models'/config['model_filename']
    download(config['model_url'], model, config['model_sha256'], config['model_bytes'])
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
    executable = find_executable()
    print('Local model and runtime verified: '+str(executable), flush=True)
    return executable


def find_executable():
    config = lock()
    directory = CACHE_ROOT/'runtime'/config['runtime_version']
    suffix = '.exe' if os.name == 'nt' else ''
    for name in ('llama-server',):
        matches = list(directory.rglob(name+suffix)) if directory.exists() else []
        if matches:
            return matches[0].resolve()
    raise ValueError('Local runtime missing. Run llm_test.py setup first.')


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


def generate(system, user, output, *, max_tokens=768, seed=42, threads=8, timeout=300, thinking=False):
    config = lock()
    executable = find_executable()
    model = CACHE_ROOT/'models'/config['model_filename']
    if not model.is_file() or model.stat().st_size != config['model_bytes']:
        raise ValueError('Model weights missing/incomplete. Run llm_test.py setup first.')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    messages = [dict(role='system', content=system), dict(role='user', content=user)]
    prompt = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    (output/'messages.json').write_text(prompt, encoding='utf-8')
    (output/'system_prompt.txt').write_text(system, encoding='utf-8')
    (output/'user_prompt.txt').write_text(user, encoding='utf-8')
    schema = dict(type='object', properties={'code': {'type': 'string'}}, required=['code'], additionalProperties=False)
    (output/'response_schema.json').write_text(json.dumps(schema), encoding='utf-8')
    # The server handles the model's native chat template.
    # It exists only for this request, bound exclusively to the loopback interface.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    command = [str(executable), '--model', str(model), '--host', '127.0.0.1', '--port', str(port),
               '--ctx-size', '4096', '--threads', str(threads), '--gpu-layers', '0',
               '--parallel', '1', '--jinja', '--reasoning', 'on' if thinking else 'off']
    # Qwen's published coding-thinking / general-instruct sampling profiles.
    sampling = dict(temperature=.6 if thinking else .7, top_p=.95 if thinking else .8,
                    top_k=20, min_p=0., presence_penalty=0. if thinking else 1.5, repeat_penalty=1.)
    # Validate JSON after generation. Avoid mixing grammar and reasoning parsers;
    # formatting errors remain visible failures rather than silently repaired code.
    payload = dict(model='local', messages=messages, max_tokens=max_tokens, **sampling,
                   seed=seed, chat_template_kwargs={'enable_thinking': thinking})
    (output/'request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    metadata = dict(model_id=config['model_id'], original_revision=config['original_revision'],
                    total_parameters=config['total_parameters'], model_sha256=config['model_sha256'],
                    quantization=config['quantization'], runtime=config['runtime'],
                    runtime_version=config['runtime_version'], thinking=thinking, **sampling,
                    seed=seed, threads=threads, context_tokens=4096, max_output_tokens=max_tokens,
                    prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(), device='CPU',
                    inference='Local llama.cpp subprocess; temporary loopback HTTP; no hosted API',
                    prompt_format='GGUF chat template / Jinja', constrained_decoding=False)
    started = time.monotonic()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    address = 'http://127.0.0.1:'+str(port)
    with (output/'inference.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=executable.parent, env=runtime_env(executable),
                                   stdout=log, stderr=log)
        try:
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Local runtime exited; see inference.log')
                if time.monotonic()-started >= min(90, timeout):
                    raise TimeoutError('Local runtime did not become ready; see inference.log')
                try:
                    with opener.open(address+'/health', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.5)
            request = urllib.request.Request(address+'/v1/chat/completions',
                                             data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json'})
            with opener.open(request, timeout=max(1, timeout-(time.monotonic()-started))) as response:
                reply = json.loads(response.read())
            (output/'response.json').write_text(json.dumps(reply, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            choice = reply['choices'][0]
            raw = choice['message'].get('content') or ''
            (output/'raw_response.txt').write_text(raw, encoding='utf-8')
            metadata.update(usage=reply.get('usage'), timings=reply.get('timings'),
                            finish_reason=choice['finish_reason'])
            if choice['finish_reason'] != 'stop':
                raise ValueError('Generation did not finish normally: '+str(choice['finish_reason']))
        except Exception as error:
            metadata['error'] = type(error).__name__+': '+str(error)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            metadata.update(generation_seconds=time.monotonic()-started, runtime_returncode=process.returncode)
            (output/'generation.json').write_text(json.dumps(metadata, indent=2)+'\n')
    program = extract_program(raw)
    (output/'generated.py').write_text(program.rstrip()+'\n', encoding='utf-8')
    return program, metadata
