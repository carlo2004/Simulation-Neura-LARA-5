"""Serve the browser workbench and run paired Prompt2Robo tasks on the LARA 5."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Timer
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4

from stacklab import __version__
from stacklab.cli.prompt2robo import (CHECKER, LOCK, PROMPT_FORMAT, load_system_prompt, prompt_for,
                                     read_samples, replay_environment, response_for, source_files)
from stacklab.config import Config, write_json
from stacklab.llm.metrics import GenerationMetrics
from stacklab.paths import ROOT, RUNS_ROOT

WEB = ROOT / 'web/public'
PROOFS = ROOT / 'examples/prompt2robo-replays/manifest.json'
SCHEMA = 'stacklab-workbench-v1'
MAX_BODY = 96 * 1024
MAX_TOKENS = 2048
SEED = 42
STANDARD_SPEED_MM_S = Config.speed_mm_s
SPEEDS_MM_S = (STANDARD_SPEED_MM_S, 120, 160)
UI_SPEED_MM_S = 120


class ClientDisconnected(Exception):
    pass


def model_endpoint(url):
    parsed = urlsplit(url.rstrip('/').removesuffix('/v1'))
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise ValueError('Use a loopback HTTP model endpoint, e.g. http://127.0.0.1:8081/v1')
    if parsed.port == 0:
        raise ValueError('Invalid server port')
    return parsed.hostname, parsed.port or 80


def load_models(path):
    models = {} if path is None else json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(models, dict) or len(models) > 20:
        raise ValueError('Expected an object with up to 20 model entries')
    for key, model in models.items():
        if (not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', key) or not isinstance(model, dict)
                or not isinstance(model.get('label'), str) or not model['label'].strip()
                or not isinstance(model.get('url'), str) or model.get('protocol', 'openai') != 'openai'):
            raise ValueError(f'Invalid model entry {key!r}')
        model_endpoint(model['url'])
        if not isinstance(model.get('model'), str) or not model['model'].strip():
            raise ValueError(f'{key} needs the model ID used by its OpenAI-compatible server')
        env_name = model.get('api_key_env', '')
        if not isinstance(env_name, str) or env_name and not re.fullmatch(r'[A-Z_][A-Z0-9_]*', env_name):
            raise ValueError(f'Invalid api_key_env in {key}')
        for field in ('weights', 'adapter'):
            if field not in model:
                continue
            artifact = model[field]
            if (not isinstance(artifact, dict) or set(artifact) != {'file', 'sha256', 'bytes'}
                    or not isinstance(artifact['file'], str)
                    or not re.fullmatch(r'[^/\\\x00-\x1f]{1,255}\.gguf', artifact['file'], re.I)
                    or not isinstance(artifact['sha256'], str)
                    or not re.fullmatch(r'[a-f0-9]{64}', artifact['sha256'])
                    or type(artifact['bytes']) is not int or artifact['bytes'] <= 0):
                raise ValueError(f'Invalid {field} identity in {key}')
    return models


def model_identity(key, model):
    return dict(id=key, label=model['label'], api_model=model['model'],
                weights=model.get('weights'), adapter=model.get('adapter'))


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def completion(model, messages):
    """Generate one policy using the workbench's fixed generation budget."""
    host, port = model_endpoint(model['url'])
    body = dict(model=model['model'], messages=messages, stream=False, max_tokens=MAX_TOKENS,
                temperature=0, seed=SEED, chat_template_kwargs={'enable_thinking': False})
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


def decode_answer(raw):
    """Separate a dataset-style program or text reply without validating its Python here."""
    answer = raw.strip()
    fenced = '\x60\x60\x60' in answer
    if fenced:
        block = re.fullmatch(r'\x60\x60\x60(?:python|py|json)?[ \t]*\r?\n(.*?)\x60\x60\x60', answer, re.I | re.S)
        if not block or '\x60\x60\x60' in block[1]:
            raise ValueError('Expected one fenced response')
        answer = block[1].strip()
    if answer.startswith('{'):
        try:
            reply = json.loads(answer)
        except json.JSONDecodeError as error:
            raise ValueError('Invalid JSON response. Return one JSON object or a Python function.') from error
        code, message = reply.get('code'), reply.get('message', '')
        if not isinstance(code, str) or not isinstance(message, str):
            raise ValueError('Expected a code string and an optional message string')
        code, message = code.strip(), message.strip()
    elif fenced or re.search(r'(?m)^[ \t]*(?:async[ \t]+)?def\b', answer):
        code, message = answer, ''
    else:
        code, message = '', answer
    if not (code or message):
        raise ValueError('Model response is empty')
    return dict(code=code, message=message)


def simulate(checker, sample, reply, output, emit, *, generated, unscored, run_id,
             speed_mm_s=STANDARD_SPEED_MM_S, video=False):
    worker = Path(__file__).with_name('_prompt2robo_worker.py')
    command = [sys.executable, '-I', str(worker), str(checker), str(output), sample['id']]
    command.extend(['--video', 'preview'] if video else ['--live'])
    if generated:
        command.append('--generated')
    if unscored:
        command.append('--unscored')
    payload = dict(sample={k: v for k, v in sample.items() if k != 'assistant_answer'},
                   response=reply, speed_mm_s=speed_mm_s)
    with (output / 'worker.log').open('w', encoding='utf-8') as log:
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                              cwd=output, env=replay_environment(offscreen=True),
                              text=True, encoding='utf-8') as process:
            timeout = Timer(180 if video else 120, process.kill)
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
                    if emit is not None and event in ('frame', 'action'):
                        emit(event, **record)
                process.wait()
            finally:
                timeout.cancel()
                if process.poll() is None:
                    process.kill()
    receipt = output / (sample['id'] + '.json')
    if not receipt.is_file():
        worker_log = (output/'worker.log').read_text(encoding='utf-8', errors='replace')
        print(f'Workbench {run_id} / {sample["id"]}\n{worker_log[-1500:]}', file=sys.stderr, flush=True)
        raise RuntimeError(f'LARA 5 worker exited with status {process.returncode}. See runner log for {run_id}.')
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
        self.system = load_system_prompt(self.lock, root)
        try:
            self.git_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                                        stderr=subprocess.DEVNULL, text=True, timeout=2).strip()
        except (OSError, subprocess.SubprocessError):
            self.git_revision = None
        proof_rows = json.loads(PROOFS.read_text(encoding='utf-8'))['results']
        proof = {row['id']: row['passed'] for row in proof_rows}
        available = {row['id']: row for row in read_samples(root, names)}
        chosen = [*proof, *(row['id'] for row in available.values() if row['split'] == 'eval_v4'), *extra_cases]
        self.cases = {key: available[key] for key in dict.fromkeys(chosen)}
        self.samples = self.cases | {key: row for key, row in available.items()
                                     if row['split'] == 'train' and row['verified'] is True}
        self.catalog = dict(protocol=SCHEMA, lane_prompts=True, prompt_format=PROMPT_FORMAT, training_cases=True,
                            speeds_mm_s=SPEEDS_MM_S, default_speed_mm_s=UI_SPEED_MM_S, video_export=True,
                            dataset=self.lock['repository'], revision=self.lock['revision'],
                            models=[model_identity(key, value) for key, value in models.items()],
                            cases=[dict(id=key, split=row['split'], reference_passed=proof.get(key),
                                        category=row['category'], subcategory=row['subcategory'],
                                        expected_behavior=row['expected_behavior'],
                                        request=row['user_prompt'].partition('\n')[2],
                                        scene=row['scene']) for key, row in self.cases.items()])
        super().__init__(('127.0.0.1', port), Handler)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def translate_path(self, path):
        local = Path(super().translate_path(path))
        if local == WEB / LOCK.name:
            return str(LOCK)
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

    def read_body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= MAX_BODY:
            raise ValueError('Request body exceeds the workbench limit')
        body = json.loads(self.rfile.read(size))
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        return body

    def read_job(self):
        body = self.read_body()
        sample = self.server.samples.get(body.get('task', ''))
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
        speed = body.get('speed_mm_s', STANDARD_SPEED_MM_S)
        if type(speed) is not int or speed not in SPEEDS_MM_S:
            raise ValueError('Choose an arm speed from the runner catalog')
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
        return mode, sample, code, lanes, speed

    def read_video_job(self):
        body = self.read_body()
        run_id, lane = body.get('id'), body.get('lane')
        if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id) or lane not in ('left', 'right'):
            raise ValueError('Choose a saved run and a side')
        path = RUNS_ROOT / 'workbench' / (run_id + '.json')
        report = json.loads(path.read_text(encoding='utf-8'))
        result = report['results'].get(lane, {})
        check = result.get('check') or {}
        sample = self.server.samples.get(report['task'])
        if (report['status'] != 'complete' or report['runner_revision'] != self.server.git_revision
                or report['revision'] != self.server.lock['revision'] or sample is None or not result.get('code')
                or not check.get('initial_state')):
            raise ValueError('Für diese Seite gibt es keinen exportierbaren Lauf auf diesem Runner.')
        return report, lane, dict(sample, user_prompt=result['user_prompt']), result

    def do_POST(self):
        if self.path not in ('/api/run', '/api/video'):
            self.send_error(404)
            return
        if not self.authorized():
            return
        video = self.path == '/api/video'
        try:
            job = self.read_video_job() if video else self.read_job()
        except FileNotFoundError:
            self.json_response(404, {'error': 'Dieser Lauf ist auf dem Runner nicht gespeichert.'})
            return
        except (ValueError, TypeError) as error:
            self.json_response(400, {'error': str(error)})
            return
        if not self.server.capacity.acquire(blocking=False):
            self.json_response(429, {'error': 'Runner busy. Start again when a comparison has finished.'})
            return
        try:
            if video:
                self.export_video(*job)
            else:
                self.stream_job(*job)
        except (ClientDisconnected, BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.server.capacity.release()

    def export_video(self, report, lane, sample, result):
        generated = report['mode'] != 'reference'
        reply = {key: result[key] for key in ('code', 'message')} if generated else response_for(sample)
        with TemporaryDirectory(prefix='stacklab-video-') as temporary:
            directory = Path(temporary)
            try:
                receipt = simulate(self.server.checker, sample, reply, directory, None,
                                   generated=generated, unscored=not result['scored'], run_id=report['id'],
                                   speed_mm_s=report.get('speed_mm_s', STANDARD_SPEED_MM_S), video=True)
                path = directory / (sample['id'] + '.mp4')
                if not receipt['video'] or not path.is_file():
                    raise ValueError('Für diesen Lauf konnte kein Video gerendert werden.')
            except (ValueError, RuntimeError, OSError) as error:
                self.json_response(422, {'error': str(error)})
                return
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Disposition', f'attachment; filename="lara-{report["id"]}-{lane}.mp4"')
            self.send_header('Content-Length', str(path.stat().st_size))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            with path.open('rb') as stream:
                shutil.copyfileobj(stream, self.wfile)

    def stream_job(self, mode, sample, code, lanes, speed_mm_s=STANDARD_SPEED_MM_S):
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
        samples_by_side = {
            side: sample if instruction == original else dict(sample, user_prompt=header + '\n' + instruction)
            for side, instruction in instructions.items()
        }
        messages_by_side = {
            side: prompt_for(lane_sample, self.server.system)
            for side, lane_sample in samples_by_side.items()
        }
        prompt_hashes = {side: hashlib.sha256(json.dumps(messages).encode()).hexdigest()
                         for side, messages in messages_by_side.items()}
        report = dict(protocol=SCHEMA, prompt_format=PROMPT_FORMAT, id=uuid4().hex,
                      started_at=utc_now(), runner_version=__version__, runner_revision=self.server.git_revision,
                      status='running', system_prompt=self.server.system,
                      dataset=self.server.lock['repository'], revision=self.server.lock['revision'],
                      mode=mode, task=sample['id'], split=sample['split'], subcategory=sample['subcategory'],
                      expected_behavior=sample['expected_behavior'],
                      instruction=lanes[0][2] if same_prompt else None, scene=sample['scene'],
                      prompt_sha256=prompt_hashes[lanes[0][0]] if same_prompt else None,
                      same_prompt=same_prompt, seed=SEED, max_tokens=MAX_TOKENS, temperature=0,
                      speed_mm_s=speed_mm_s,
                      scored=all(text == original for text in instructions.values()), results={})
        try:
            write('start', report=report)
            for lane, key, instruction in lanes:
                model = self.server.models[key] if key else None
                label = model['label'] if model else ('Referenz' if mode == 'reference' else 'Eigener Code')
                result = dict(model=key, label=label, model_identity=model_identity(key, model) if model else None,
                              instruction=instruction, user_prompt=messages_by_side[lane][-1]['content'],
                              prompt_sha256=prompt_hashes[lane], scored=instruction == original,
                              started_at=utc_now(), metrics={}, code='', message='', raw='', check=None, actions=[])
                report['results'][lane] = result
                self.run_lane(mode, samples_by_side[lane], code, model, messages_by_side[lane], result,
                              report['id'], lambda event, **data: write(event, lane=lane, **data), speed_mm_s)
                write('result', lane=lane, result=result)
            report['status'] = 'complete'
        finally:
            if report['status'] == 'running':
                report['status'] = 'interrupted'
            report['finished_at'] = utc_now()
            try:
                write_json(RUNS_ROOT/'workbench'/(report['id'] + '.json'), report)
            except OSError as error:
                print(f'Workbench {report["id"]}: {error}', file=sys.stderr, flush=True)
        write('complete', report=report)

    def run_lane(self, mode, sample, code, model, messages, result, run_id, write,
                 speed_mm_s=STANDARD_SPEED_MM_S):
        def emit(event, **data):
            if event == 'action':
                result['actions'].append(data)
            write(event, **data)

        stage = 'response'
        simulation_started = None
        try:
            if model:
                stage = 'generation'
                emit('phase', phase='generating')
                raw, metrics, actual, finish = completion(model, messages)
                result.update(raw=raw, metrics=metrics, actual_model=actual, finish_reason=finish)
                if finish == 'length':
                    raise ValueError(f'Model reached the {MAX_TOKENS}-token limit')
                stage = 'response'
                reply = decode_answer(raw)
            elif mode == 'reference':
                reply = response_for(sample)
            else:
                reply = dict(code=code, message='')
            result.update(code=reply['code'], message=reply['message'])
            emit('program', code=reply['code'], message=reply['message'], metrics=result['metrics'])
            stage = 'simulation'
            emit('phase', phase='executing')
            simulation_started = monotonic()
            with TemporaryDirectory(prefix='stacklab-workbench-') as temporary:
                result['check'] = simulate(self.server.checker, sample, reply, Path(temporary), emit,
                                           generated=mode != 'reference', unscored=not result['scored'],
                                           run_id=run_id, speed_mm_s=speed_mm_s)
        except ClientDisconnected:
            result['error_stage'] = stage
            raise
        except (ValueError, RuntimeError, OSError, KeyError, IndexError, TypeError, http.client.HTTPException) as error:
            result.update(error=str(error), error_stage=stage, error_type=type(error).__name__)
        finally:
            if simulation_started is not None:
                result['simulation_wall_seconds'] = round(monotonic() - simulation_started, 3)
            result['finished_at'] = utc_now()


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
