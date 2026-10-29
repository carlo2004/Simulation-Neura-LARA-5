"""Inference across a loopback SSH forward; the robot and its interpreter stay local."""
import http.client
import json
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from stacklab.llm.runtime import GenerationCancelled

PROTOCOL = 'stacklab-inference-v1'
MAX_RECORD = 16 * 1024 * 1024


def endpoint(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise ValueError('Use a loopback HTTP URL, e.g. http://127.0.0.1:8765, through an SSH port forward')
    port = parsed.port or 80
    if not 0 < port < 65536:
        raise ValueError('Invalid server port')
    return parsed.hostname, port


class RemoteModel:
    """Same complete/cancel interface as LocalModel, with native evidence copied back."""
    def __init__(self, url, model=None):
        self.host, self.port = endpoint(url)
        self.address = url.rstrip('/')
        self._guard = threading.Lock()
        self._cancelled = threading.Event()
        self._socket = None
        self._active = None
        self._last_cancel = 0.
        self.info = self._json('GET', '/info')
        if (not isinstance(self.info, dict) or self.info.get('protocol') != PROTOCOL
                or not isinstance(self.info.get('server_id'), str)
                or not isinstance(self.info.get('config'), dict)
                or any(key not in self.info['config'] for key in ('model_key', 'model_id', 'model_sha256'))
                or not isinstance(self.info.get('threads'), int)
                or not isinstance(self.info.get('software'), dict)):
            raise ValueError('Endpoint is not a compatible Stack Lab inference server')
        self.config = self.info['config']
        self.model = self.config['model_key']
        if model is not None:
            from stacklab.llm.catalog import lock
            expected = lock(model)
            if expected['model_sha256'] != self.config['model_sha256']:
                raise ValueError('Requested model differs from the server model. Restart serve with that model, or omit --model.')

    def _json(self, method, path, data=None, timeout=5):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        try:
            body = None if data is None else json.dumps(data).encode('utf-8')
            connection.request(method, path, body, {'Content-Type': 'application/json'})
            response = connection.getresponse()
            value = json.loads(response.read(MAX_RECORD))
            if response.status != 200:
                raise RuntimeError(value.get('error', 'Remote HTTP '+str(response.status)))
            return value
        except (OSError, http.client.HTTPException) as error:
            raise RuntimeError('Inference server unreachable at '+self.address+'; check the server and SSH forward: '+str(error)) from error
        finally:
            connection.close()

    def complete(self, messages, output, *, max_tokens=2048, seed=42, thinking=None,
                 timeout=600, on_delta=None, cancelled=None, thinking_budget=None, on_progress=None):
        if timeout <= 0:
            raise ValueError('Generation timeout must be positive')
        if cancelled and cancelled():
            raise GenerationCancelled('Generation cancelled')
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        (output/'remote-server.json').write_text(json.dumps(self.info, indent=2)+'\n', encoding='utf-8')
        request_id = uuid4().hex
        payload = dict(server_id=self.info['server_id'], request_id=request_id, messages=messages,
                       options=dict(max_tokens=max_tokens, seed=seed, thinking=thinking,
                                    timeout=timeout, thinking_budget=thinking_budget))
        (output/'remote-request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        connection = http.client.HTTPConnection(self.host, self.port, timeout=min(10, timeout))
        started = time.monotonic()
        self._cancelled.clear()
        with self._guard:
            if self._active:
                raise RuntimeError('This remote client already has a running request')
            self._active = request_id
            self._last_cancel = 0.
        timer = threading.Timer(timeout, self.cancel)
        timer.daemon = True
        timer.start()
        final = None
        partial_content, partial_reasoning = [], []
        partial_performance = {}
        error = None
        try:
            connection.connect()
            with self._guard:
                self._socket = connection.sock
            connection.sock.settimeout(timeout+5)
            if self._cancelled.is_set() or cancelled and cancelled():
                raise GenerationCancelled('Generation cancelled')
            connection.request('POST', '/generate', json.dumps(payload).encode('utf-8'),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(json.loads(response.read(MAX_RECORD)).get('error', 'Remote request failed'))
            with (output/'remote-stream.jsonl').open('w', encoding='utf-8') as wire, \
                    (output/'stream.jsonl').open('w', encoding='utf-8') as native:
                while True:
                    line = response.readline(MAX_RECORD+1)
                    if len(line) > MAX_RECORD:
                        raise RuntimeError('Remote stream record is too large')
                    if not line:
                        raise RuntimeError('Remote connection ended before the result; partial evidence retained')
                    record = json.loads(line)
                    wire.write(line.decode('utf-8'))
                    wire.flush()
                    kind, data = record['event'], record['data']
                    if kind == 'native':
                        native.write(json.dumps(data, ensure_ascii=False)+'\n')
                        native.flush()
                    elif kind == 'delta':
                        (partial_content if data['kind'] == 'content' else partial_reasoning).append(data['text'])
                        if on_delta:
                            on_delta(data['kind'], data['text'])
                    elif kind == 'progress':
                        partial_performance = data
                        if on_progress:
                            on_progress(data)
                    elif kind == 'result':
                        final = data
                        break
                    if self._cancelled.is_set() or cancelled and cancelled():
                        self.cancel()
                        raise GenerationCancelled('Generation cancelled')
            if final.get('error'):
                detail = final['error']
                failure = {'GenerationCancelled': GenerationCancelled, 'TimeoutError': TimeoutError,
                           'ValueError': ValueError}.get(detail['type'], RuntimeError)
                raise failure(detail['message'])
            if (not isinstance(final.get('raw'), str) or not isinstance(final.get('files'), dict)
                    or any(name not in final['files'] for name in ('request.json', 'response.json', 'generation.json'))):
                raise RuntimeError('Remote result is incomplete; no robot program will run')
            if self._cancelled.is_set() or cancelled and cancelled():
                raise GenerationCancelled('Generation cancelled')
        except BaseException as failure:
            if time.monotonic()-started >= timeout:
                failure = TimeoutError('Remote generation exceeded the time limit')
            elif self._cancelled.is_set() or cancelled and cancelled():
                failure = GenerationCancelled('Generation cancelled')
            error = failure
            self.cancel()
            raise failure
        finally:
            timer.cancel()
            connection.close()
            with self._guard:
                self._socket = None
                self._active = None
            files = final.get('files', {}) if final else {}
            for name in ('request.json', 'response.json', 'generation.json'):
                if name in files:
                    value = files[name]
                    if name == 'generation.json':
                        (output/'server-generation.json').write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
                        value = self._metadata(value, started)
                    (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            if error:
                path = output/'generation.json'
                metadata = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else self._metadata(
                    dict(model_id=self.config['model_id'], model_key=self.model,
                         device=self.config.get('device', 'unknown'), hardware=self.info.get('hardware'),
                         threads=self.info['threads'], finish_reason=None,
                         performance=dict(partial_performance, partial=True)), started)
                metadata['error'] = type(error).__name__+': '+str(error)
                metadata['transport_complete'] = final is not None
                if final is None:
                    metadata['finish_reason'] = None
                    metadata['performance']['partial'] = True
                path.write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
                if 'response.json' not in files:
                    response = dict(choices=[dict(finish_reason=None, message=dict(role='assistant',
                        content=''.join(partial_content), reasoning_content=''.join(partial_reasoning)))])
                    (output/'response.json').write_text(json.dumps(response, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        return final['raw'], json.loads((output/'generation.json').read_text(encoding='utf-8'))

    def _metadata(self, original, started):
        return dict(original, inference='Remote Stack Lab inference through a loopback SSH forward',
                    transport=dict(protocol=PROTOCOL, url=self.address, server_id=self.info['server_id'],
                                   server_software=self.info['software'],
                                   client_round_trip_seconds=time.monotonic()-started))

    def cancel(self):
        self._cancelled.set()
        with self._guard:
            request_id, stream_socket = self._active, self._socket
            now = time.monotonic()
            send = request_id is not None and now-self._last_cancel >= .5
            if send:
                self._last_cancel = now
        if send:
            try:
                self._json('POST', '/cancel', dict(server_id=self.info['server_id'], request_id=request_id), timeout=1)
            except (RuntimeError, OSError, ValueError):
                pass
        if stream_socket:
            try:
                stream_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close(self):
        # Closing a GUI session cancels its request, never the shared server.
        self.cancel()
