"""A single-model inference service, bound only to loopback for SSH forwarding."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from uuid import uuid4

from stacklab.llm.remote import PROTOCOL
from stacklab.llm.runtime import GenerationCancelled
from stacklab.provenance import software_provenance
from stacklab.paths import ROOT


def server_source_hashes():
    from stacklab.llm.catalog import sha256
    paths = [*(ROOT/'stacklab').rglob('*.py'), *(ROOT/'config').rglob('*')]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(paths) if p.is_file()}


class InferenceServer(ThreadingHTTPServer):
    def __init__(self, client, output, port=8765, *, allow_model_switch=False,
                 install_missing=False, load_timeout=180):
        self.client = client
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.info = dict(protocol=PROTOCOL, server_id=uuid4().hex, config=client.config,
                         software=software_provenance(), hardware=client.hardware,
                         threads=client.threads)
        self.info['source_hashes'] = server_source_hashes()
        self.device = getattr(client, 'device', 'cpu')
        self.install_missing = install_missing
        self.load_timeout = load_timeout
        self.info['capabilities'] = dict(model_switch=allow_model_switch, install_missing=install_missing)
        if allow_model_switch:
            from stacklab.llm.catalog import lock, model_keys
            self.info['model_catalog'] = {key: lock(key, device=self.device) for key in model_keys()}
            self.client.cache_prompt = False
            self.info['prompt_cache'] = False
        self.info['device'] = self.device
        self.generation_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.active = None
        super().__init__(('127.0.0.1', port), InferenceHandler)

    def select_model(self, model):
        """Caller holds generation_lock. Paths and commands never come from HTTP."""
        from stacklab.config import write_json
        from stacklab.llm.catalog import setup
        from stacklab.llm.runtime import LocalModel
        if model not in self.info.get('model_catalog', {}):
            raise ValueError('Choose an exact model alias from the server catalog')
        started = time.monotonic()
        self.client.close()  # Free VRAM before installing/loading the next model.
        self.info.update(server_id=uuid4().hex, ready=False)
        path = self.output/('model-'+model+'-'+self.info['server_id'])
        path.mkdir()
        result = dict(model=model, setup_seconds=0., load_seconds=None, error=None)
        try:
            self.client = LocalModel(model, threads=self.info['threads'], device=self.device)
            self.client.cache_prompt = False
            self.info.update(config=self.client.config, hardware=None)
            if self.install_missing:
                setup(model, device=self.device)
            result['setup_seconds'] = time.monotonic()-started
            load_started = time.monotonic()
            self.client.start(path/'runtime', timeout=self.load_timeout)
            result['load_seconds'] = time.monotonic()-load_started
            self.info.update(hardware=self.client.hardware, ready=True)
        except Exception as error:
            result['error'] = type(error).__name__+': '+str(error)
            self.client.close()
        result['wall_seconds'] = time.monotonic()-started
        log = path/'runtime/inference.log'
        if log.is_file():
            result['startup_log'] = log.read_text(encoding='utf-8', errors='replace')[:1024*1024]
            result['startup_log_truncated'] = log.stat().st_size > 1024*1024
        result['info'] = dict(self.info)
        write_json(path/'switch.json', result)
        return result


class InferenceHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/info':
            self.reply(200, self.server.info)
        else:
            self.reply(404, dict(error='Unknown endpoint'))

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if self.headers.get_content_type() != 'application/json' or not 0 < size <= 2*1024*1024:
                raise ValueError('Expected a JSON request of at most 2 MiB')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            if data.get('server_id') != self.server.info['server_id']:
                self.reply(409, dict(error='Server changed or restarted; reconnect the local chat'))
                return
            request_id = data.get('request_id', '')
            if not isinstance(request_id, str) or len(request_id) != 32 or any(c not in '0123456789abcdef' for c in request_id):
                raise ValueError('Expected a request UUID')
            if self.path == '/cancel':
                with self.server.state_lock:
                    active = self.server.active
                    matched = active is not None and active[0] == request_id
                    if matched:
                        active[1].set()
                        self.server.client.cancel()
                self.reply(200, dict(cancelled=matched))
                return
            if self.path == '/select-model':
                if not self.server.info['capabilities']['model_switch']:
                    self.reply(403, dict(error='Model switching is disabled; start serve with --allow-model-switch'))
                    return
                model = data.get('model')
                if not isinstance(model, str) or model not in self.server.info.get('model_catalog', {}):
                    raise ValueError('Choose an exact model alias from the server catalog')
                if not self.server.generation_lock.acquire(blocking=False):
                    self.reply(409, dict(error='Model is busy; switching cannot interrupt another request'))
                    return
                try:
                    if data['server_id'] != self.server.info['server_id']:
                        self.reply(409, dict(error='Server changed during model selection; reconnect'))
                        return
                    self.reply(200, self.server.select_model(model))
                finally:
                    self.server.generation_lock.release()
                return
            if self.path != '/generate':
                self.reply(404, dict(error='Unknown endpoint'))
                return
            if self.server.info.get('ready') is False:
                self.reply(503, dict(error='No model is ready; select a working model first'))
                return
            messages, options = data.get('messages'), data.get('options')
            if not isinstance(messages, list) or not messages or not all(
                    isinstance(m, dict) and m.get('role') in ('system', 'user', 'assistant')
                    and isinstance(m.get('content'), str) for m in messages):
                raise ValueError('Expected chat messages')
            allowed = {'max_tokens', 'seed', 'thinking', 'thinking_budget', 'timeout'}
            if not isinstance(options, dict) or options.keys()-allowed:
                raise ValueError('Unexpected generation options')
            if not self.server.generation_lock.acquire(blocking=False):
                self.reply(409, dict(error='Model is busy with another request; try again when it finishes'))
                return
            if data['server_id'] != self.server.info['server_id']:
                self.server.generation_lock.release()
                self.reply(409, dict(error='Server changed before generation; reconnect'))
                return
        except (ValueError, TypeError) as error:
            self.reply(400, dict(error=str(error)))
            return
        stopped = threading.Event()
        with self.server.state_lock:
            self.server.active = (request_id, stopped)
        output = self.server.output/request_id
        try:
            output.mkdir()
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.end_headers()

            def emit(kind, value):
                try:
                    self.wfile.write((json.dumps(dict(event=kind, data=value), ensure_ascii=False)+'\n').encode('utf-8'))
                    self.wfile.flush()
                except OSError as error:
                    stopped.set()
                    self.server.client.cancel()
                    raise GenerationCancelled('Remote client disconnected') from error

            error = None
            raw = None
            try:
                emit('started', dict(request_id=request_id))
                raw, _ = self.server.client.complete(messages, output, **options,
                    cancelled=stopped.is_set,
                    on_delta=lambda kind, text: emit('delta', dict(kind=kind, text=text)),
                    on_progress=lambda value: emit('progress', value),
                    on_native=lambda value: emit('native', value))
            except Exception as failure:
                error = dict(type=type(failure).__name__, message=str(failure))
            files = {name: json.loads((output/name).read_text(encoding='utf-8'))
                     for name in ('request.json', 'response.json', 'generation.json') if (output/name).is_file()}
            emit('result', dict(raw=raw, files=files, error=error))
        except (GenerationCancelled, OSError):
            pass
        finally:
            with self.server.state_lock:
                self.server.active = None
            self.server.generation_lock.release()
