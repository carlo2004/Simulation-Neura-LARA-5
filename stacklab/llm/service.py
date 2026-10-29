"""A single-model inference service, bound only to loopback for SSH forwarding."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from uuid import uuid4

from stacklab.llm.remote import PROTOCOL
from stacklab.llm.runtime import GenerationCancelled
from stacklab.provenance import software_provenance


class InferenceServer(ThreadingHTTPServer):
    def __init__(self, client, output, port=8765):
        self.client = client
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.info = dict(protocol=PROTOCOL, server_id=uuid4().hex, config=client.config,
                         software=software_provenance(), hardware=client.hardware,
                         threads=client.threads)
        self.generation_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.active = None
        super().__init__(('127.0.0.1', port), InferenceHandler)


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
            if self.path != '/generate':
                self.reply(404, dict(error='Unknown endpoint'))
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
