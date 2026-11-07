"""Serve the browser workbench and run paired Prompt2Robo tasks on the LARA 5."""
import argparse
from contextlib import closing
import hashlib
import hmac
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Timer
from urllib.parse import urlsplit
from uuid import uuid4

from stacklab.cli.prompt2robo import (CHECKER, LOCK, PROMPT, prompt_for, read_samples,
                                     replay_environment, response_for, source_files)
from stacklab.llm.metrics import GenerationMetrics
from stacklab.llm.remote import RemoteModel, endpoint
from stacklab.llm.responses import parse_reply
from stacklab.paths import ROOT

WEB = ROOT / 'web/public'
PROOFS = ROOT / 'examples/prompt2robo-replays/manifest.json'
SCHEMA = 'stacklab-workbench-v1'
MAX_BODY = 96 * 1024
MAX_TOKENS = 2048
SEED = 42


class ClientDisconnected(Exception):
    pass


def load_models(path):
    models = {} if path is None else json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(models, dict) or len(models) > 20:
        raise ValueError('Expected an object with up to 20 model entries')
    for key, model in models.items():
        if (not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', key) or not isinstance(model, dict)
                or not isinstance(model.get('label'), str) or not model['label'].strip()
                or not isinstance(model.get('url'), str) or model.get('protocol') not in ('openai', 'stacklab')):
            raise ValueError(f'Invalid model entry {key!r}')
        endpoint(model['url'].rstrip('/').removesuffix('/v1') if model['protocol'] == 'openai' else model['url'])
        if model['protocol'] == 'openai' and (not isinstance(model.get('model'), str) or not model['model'].strip()):
            raise ValueError(f'{key} needs the model ID used by its OpenAI-compatible server')
        env_name = model.get('api_key_env', '')
        if not isinstance(env_name, str) or env_name and not re.fullmatch(r'[A-Z_][A-Z0-9_]*', env_name):
            raise ValueError(f'Invalid api_key_env in {key}')
    return models


def completion(model, messages, directory, emit):
    """Generate one policy using the workbench's fixed generation budget."""
    if model['protocol'] == 'stacklab':
        client = RemoteModel(model['url'], recording='slim')
        raw, result = client.complete(messages, directory, max_tokens=MAX_TOKENS, seed=SEED,
                                      timeout=150, on_progress=lambda metrics: emit('metrics', metrics=metrics))
        return raw, result.get('performance', {}), client.config['model_id'], result.get('finish_reason')

    host, port = endpoint(model['url'].rstrip('/').removesuffix('/v1'))
    body = dict(model=model['model'], messages=messages, stream=False, max_tokens=MAX_TOKENS,
                temperature=0, seed=SEED)
    headers = {'Content-Type': 'application/json'}
    if model.get('api_key_env'):
        key = os.environ.get(model['api_key_env'])
        if not key:
            raise ValueError('Model API key is missing on the runner')
        headers['Authorization'] = 'Bearer ' + key
    metrics = GenerationMetrics()
    metrics.ready(None)
    with closing(http.client.HTTPConnection(host, port, timeout=150)) as connection:
        connection.request('POST', '/v1/chat/completions', json.dumps(body), headers)
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f'Model server returned HTTP {response.status}')
        content = response.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError('Model response is too large')
    result = json.loads(content)
    choice = result['choices'][0]
    raw = choice['message']['content']
    if not isinstance(raw, str) or len(raw) > 64000:
        raise ValueError('Invalid model response')
    metrics.update(result)
    return raw, metrics.snapshot(finished=True), result.get('model', model['model']), choice.get('finish_reason')


def simulate(checker, sample, reply, output, emit, *, generated, unscored):
    worker = Path(__file__).with_name('_prompt2robo_worker.py')
    command = [sys.executable, '-I', str(worker), str(checker), str(output), sample['id'], '--live']
    if generated:
        command.append('--generated')
    if unscored:
        command.append('--unscored')
    payload = dict(sample={k: v for k, v in sample.items() if k != 'assistant_answer'}, response=reply)
    with (output / 'worker.log').open('w', encoding='utf-8') as log:
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                              cwd=output, env=replay_environment(offscreen=True),
                              text=True, encoding='utf-8') as process:
            timeout = Timer(120, process.kill)
            timeout.daemon = True
            timeout.start()
            try:
                process.stdin.write(json.dumps(payload))
                process.stdin.close()
                for line in process.stdout:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    event = record.pop('event', None)
                    if event in ('frame', 'action'):
                        emit(event, **record)
                process.wait()
            finally:
                timeout.cancel()
                if process.poll() is None:
                    process.kill()
    receipt = output / (sample['id'] + '.json')
    if not receipt.is_file():
        print(log.name + ' ' + (output/'worker.log').read_text(encoding='utf-8', errors='replace')[-1500:],
              file=sys.stderr, flush=True)
        raise RuntimeError('The LARA 5 worker stopped without a result. Check the runner log.')
    return json.loads(receipt.read_text(encoding='utf-8'))


class Workbench(ThreadingHTTPServer):
    def __init__(self, port, *, token, origins, models, source, extra_cases, concurrent):
        self.token = token
        self.origins = set(origins)
        self.models = models
        self.capacity = BoundedSemaphore(concurrent)
        self.lock = json.loads(LOCK.read_text(encoding='utf-8'))
        names = [name for name in self.lock['files'] if name.endswith('.jsonl')]
        root = source_files(self.lock, [*names, CHECKER], source)
        self.checker = root / CHECKER
        self.system = PROMPT.read_text(encoding='utf-8')
        proof_rows = json.loads(PROOFS.read_text(encoding='utf-8'))['results']
        proof = {row['id']: row['passed'] for row in proof_rows}
        available = {row['id']: row for row in read_samples(root, names)}
        chosen = [*proof, *(row['id'] for row in available.values() if row['split'] == 'eval_v4'), *extra_cases]
        self.cases = {key: available[key] for key in dict.fromkeys(chosen)}
        self.catalog = dict(protocol=SCHEMA, lane_prompts=True, dataset=self.lock['repository'],
                            revision=self.lock['revision'],
                            models=[dict(id=key, label=value['label']) for key, value in models.items()],
                            cases=[dict(id=key, split=row['split'], reference_passed=proof.get(key),
                                        request=row['user_prompt'].partition('\n')[2],
                                        scene=row['scene']) for key, row in self.cases.items()])
        super().__init__(('127.0.0.1', port), Handler)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def translate_path(self, path):
        local = Path(super().translate_path(path))
        parts = local.relative_to(WEB).parts
        if len(parts) == 2 and parts[0] == 'proof' and re.fullmatch(r'[\w-]+\.(mp4|json)', parts[1]):
            return str(PROOFS.parent / parts[1])
        return str(local)

    def setup(self):
        self.timeout = 30
        super().setup()

    def allowed_origin(self):
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        return origin in self.server.origins or origin in ('http://' + host, 'https://' + host)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if self.allowed_origin():
            self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
            self.send_header('Vary', 'Origin')
        super().end_headers()

    def json_response(self, status, value):
        payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        if self.headers.get('Origin') and not self.allowed_origin():
            self.json_response(403, {'error': 'This browser origin is not on the runner allowlist'})
            return False
        expected = ('Bearer ' + self.server.token).encode('ascii')
        if not hmac.compare_digest(self.headers.get('Authorization', '').encode('utf-8'), expected):
            self.json_response(401, {'error': 'Runner key missing or incorrect'})
            return False
        return True

    def do_OPTIONS(self):
        if not self.path.startswith('/api/') or not self.allowed_origin():
            self.send_error(403)
            return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.send_header('Access-Control-Max-Age', '600')
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/catalog':
            if self.authorized():
                self.json_response(200, self.server.catalog)
        else:
            super().do_GET()

    def read_job(self):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= MAX_BODY:
            raise ValueError('Request body exceeds the workbench limit')
        body = json.loads(self.rfile.read(size))
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        sample = self.server.cases.get(body.get('task', ''))
        if sample is None:
            raise ValueError('Choose a case from the catalog')
        mode = body.get('mode', 'compare')
        custom = body.get('prompt', '')
        code = body.get('code', '')
        if (mode not in ('compare', 'single', 'reference', 'code') or not isinstance(custom, str)
                or len(custom) > 4000 or not isinstance(code, str) or len(code) > 64000):
            raise ValueError('Invalid workbench request')
        if mode == 'code' and not code.strip():
            raise ValueError('Enter a Python function')
        original = sample['user_prompt'].partition('\n')[2].strip()
        lanes = [('left', None, original if mode == 'reference' else custom.strip() or original)]
        if mode == 'compare':
            left, right = body.get('left'), body.get('right')
            if left == right or left not in self.server.models or right not in self.server.models:
                raise ValueError('Choose two distinct configured model entries')
            prompts = body.get('prompts', {})
            if (not isinstance(prompts, dict) or set(prompts) - {'left', 'right'}
                    or any(not isinstance(value, str) or len(value) > 4000 for value in prompts.values())):
                raise ValueError('Prompts must be text with at most 4,000 characters per side')
            lanes = [(side, key, prompts.get(side, custom).strip() or original)
                     for side, key in (('left', left), ('right', right))]
        elif mode == 'single':
            side, key = body.get('side'), body.get('model')
            if side not in ('left', 'right') or key not in self.server.models:
                raise ValueError('Choose a side and a configured model')
            lanes = [(side, key, custom.strip() or original)]
        return mode, sample, code, lanes

    def do_POST(self):
        if self.path != '/api/run':
            self.send_error(404)
            return
        if not self.authorized():
            return
        try:
            mode, sample, code, lanes = self.read_job()
        except (ValueError, TypeError) as error:
            self.json_response(400, {'error': str(error)})
            return
        if not self.server.capacity.acquire(blocking=False):
            self.json_response(429, {'error': 'Runner busy. Start again when a comparison has finished.'})
            return
        try:
            self.stream_job(mode, sample, code, lanes)
        except (ClientDisconnected, BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.server.capacity.release()

    def stream_job(self, mode, sample, code, lanes):
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()

        def write(event, **data):
            try:
                self.wfile.write((json.dumps(dict(event=event, **data), ensure_ascii=True, allow_nan=False)
                                  + '\n').encode('utf-8'))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError) as error:
                raise ClientDisconnected from error

        header, _, original = sample['user_prompt'].partition('\n')
        original = original.strip()
        instructions = {side: instruction for side, _, instruction in lanes}
        same_prompt = len(set(instructions.values())) == 1
        samples_by_side = {side: dict(sample, user_prompt=header + '\n' + instruction)
                           for side, instruction in instructions.items()}
        messages_by_side = {
            side: prompt_for(lane_sample, self.server.system) for side, lane_sample in samples_by_side.items()
        }
        prompt_hashes = {side: hashlib.sha256(json.dumps(messages).encode()).hexdigest()
                         for side, messages in messages_by_side.items()}
        report = dict(protocol=SCHEMA, id=uuid4().hex, dataset=self.server.lock['repository'],
                      revision=self.server.lock['revision'], mode=mode, task=sample['id'],
                      instruction=lanes[0][2] if same_prompt else None, scene=sample['scene'],
                      prompt_sha256=prompt_hashes[lanes[0][0]] if same_prompt else None,
                      same_prompt=same_prompt, seed=SEED, max_tokens=MAX_TOKENS,
                      scored=all(text == original for text in instructions.values()), results={})
        write('start', report=report)
        for lane, key, instruction in lanes:
            def emit(event, **data):
                write(event, lane=lane, **data)

            unscored = instruction != original
            model = self.server.models[key] if key else None
            result = dict(model=key, label=model['label'] if model else 'Referenz' if mode == 'reference' else 'Eigener Code',
                          instruction=instruction, prompt_sha256=prompt_hashes[lane], scored=not unscored,
                          metrics={}, code='', message='', raw='', check=None)
            try:
                with TemporaryDirectory(prefix='stacklab-workbench-') as temporary:
                    output = Path(temporary)
                    if model:
                        emit('phase', phase='generating')
                        raw, metrics, actual, finish = completion(model, messages_by_side[lane], output/'generation', emit)
                        result.update(raw=raw, metrics=metrics, actual_model=actual)
                        if finish == 'length':
                            raise ValueError('Model reached the token limit')
                        reply = parse_reply(raw)
                        if not reply['code'].strip() and not reply['message'].strip():
                            raise ValueError('Model response is empty')
                    elif mode == 'reference':
                        reply = response_for(sample)
                    else:
                        reply = dict(code=code, message='')
                    result.update(code=reply['code'], message=reply['message'])
                    emit('program', code=reply['code'], message=reply['message'], metrics=result['metrics'])
                    emit('phase', phase='executing')
                    result['check'] = simulate(self.server.checker, samples_by_side[lane], reply, output, emit,
                                               generated=mode != 'reference', unscored=unscored)
            except ClientDisconnected:
                raise
            except (ValueError, RuntimeError, OSError, KeyError, IndexError, TypeError, http.client.HTTPException) as error:
                result['error'] = str(error)
            report['results'][lane] = result
            emit('result', result=result)
        write('complete', report=report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--models', type=Path, help='JSON file describing the model endpoints')
    parser.add_argument('--source', type=Path, help='Existing copy of the pinned Prompt2Robo snapshot')
    parser.add_argument('--origin', action='append', default=[], help='Exact HTTPS origin for a hosted frontend')
    parser.add_argument('--case', action='append', default=[], help='Additional Prompt2Robo sample ID')
    parser.add_argument('--concurrent', type=int, choices=range(1, 5), default=1)
    args = parser.parse_args(argv)
    try:
        token = os.environ.get('STACKLAB_WORKBENCH_TOKEN', '')
        if not re.fullmatch(r'[a-zA-Z0-9_\-]{16,128}', token):
            raise ValueError('Set STACKLAB_WORKBENCH_TOKEN to a URL-safe key of at least 16 characters')
        if not (WEB/'index.html').is_file():
            raise ValueError('Run the workbench from a checkout that includes web/public')
        from stacklab.sim.assets import model_ready
        if not model_ready():
            raise ValueError('Run python bootstrap.py to prepare the LARA 5 assets')
        for origin in args.origin:
            parsed = urlsplit(origin)
            if parsed.scheme != 'https' or not parsed.hostname or origin != 'https://' + parsed.netloc or parsed.username:
                raise ValueError('An allowed origin must be an exact HTTPS origin without a path')
        with Workbench(args.port, token=token, origins=args.origin, models=load_models(args.models),
                       source=args.source, extra_cases=args.case, concurrent=args.concurrent) as server:
            print(f'Workbench http://127.0.0.1:{server.server_port}', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, KeyError) as error:
        print('Workbench: ' + str(error), file=sys.stderr)
        return 1
