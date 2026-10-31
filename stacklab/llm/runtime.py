"""Reusable local llama.cpp session with streamed output and explicit cancellation."""
from stacklab.paths import ROOT, CACHE_ROOT
import hashlib
from contextlib import nullcontext
import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from stacklab.llm.catalog import find_executable, lock, runtime_env
from stacklab.llm.metrics import GenerationMetrics
from stacklab.llm.hardware import gpu_inventory, check_cuda_backend, gpu_offload


class GenerationCancelled(RuntimeError):
    pass


class LocalModel:
    def __init__(self, model=None, threads=8, device='cpu'):
        if type(threads) is not int or threads < 1:
            raise ValueError('threads must be a positive integer')
        self.config = lock(model, device=device)
        self.device = device
        self.hardware = None
        self.model = self.config.get('model_key', model)
        self.threads = threads
        self.process = None
        self.log = None
        self.address = None
        self.load_seconds = 0.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def start(self, output, timeout=90, cancelled=None):
        if self.process is not None and self.process.poll() is None:
            return
        self.close()
        config = self.config
        weights = CACHE_ROOT/'models'/config['model_filename']
        if not weights.is_file() or weights.stat().st_size != config['model_bytes']:
            raise ValueError('Model missing/incomplete. Run python -m stacklab setup --model '+str(self.model))
        exe = find_executable(self.model, device=self.device) if self.device != 'cpu' else find_executable(self.model)
        output = Path(output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        if self.device == 'cuda':
            self.hardware = dict(gpus=gpu_inventory(required=True),
                                 backend_devices=check_cuda_backend(exe, runtime_env(exe)))
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.address = 'http://127.0.0.1:'+str(port)
        command = [str(exe), '--model', str(weights), '--host', '127.0.0.1', '--port', str(port),
                   '--ctx-size', str(config.get('context_tokens', 4096)), '--threads', str(self.threads),
                   '--gpu-layers', '999' if self.device == 'cuda' else '0',
                   '--parallel', '1', '--jinja', '--reasoning', 'auto']
        extra = config.get('server_args', [])
        reserved = {'--host', '--port', '--model', '-m', '--gpu-layers', '-ngl'}
        if not isinstance(extra, list) or any(not isinstance(arg, str) or arg.split('=')[0] in reserved for arg in extra):
            raise ValueError('server_args must be strings and must preserve the private model/device/loopback configuration')
        command += extra
        if self.device == 'cuda':
            # Offload diagnostics can be hidden at the default log level.
            # Keep the independent layer check; do not infer offload from /health.
            command += ['-lv', '5']
        self.log = (output/'inference.log').open('w', encoding='utf-8')
        started = time.monotonic()
        self.process = subprocess.Popen(command, cwd=exe.parent, env=runtime_env(exe), stdout=self.log, stderr=self.log)
        try:
            while True:
                if cancelled and cancelled():
                    raise GenerationCancelled('Generation cancelled')
                if self.process.poll() is not None:
                    raise RuntimeError('Local runtime exited; see '+str(output/'inference.log'))
                if time.monotonic()-started >= timeout:
                    raise TimeoutError('Local runtime did not become ready; see inference.log')
                try:
                    with self.opener.open(self.address+'/health', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.25)
            self.load_seconds = time.monotonic()-started
            if self.device == 'cuda':
                self.hardware.update(gpu_offload((output/'inference.log').read_text(encoding='utf-8', errors='replace')))
                (output/'device.json').write_text(json.dumps(self.hardware, indent=2)+'\n', encoding='utf-8')
        except BaseException:
            self.close()
            raise

    def complete(self, messages, output, *, max_tokens=2048, seed=42, thinking=None,
                 timeout=600, on_delta=None, cancelled=None, thinking_budget=None, on_progress=None,
                 on_native=None, record_stream=None):
        config = self.config
        if record_stream is None:
            record_stream = getattr(self, 'record_stream', True)
        if type(max_tokens) is not int or not 0 < max_tokens < config.get('context_tokens', 4096):
            raise ValueError('max-tokens must be positive and smaller than the model context')
        if timeout <= 0:
            raise ValueError('Generation timeout must be positive')
        thinking = config.get('default_thinking', False) if thinking is None else thinking
        if not thinking and not config.get('supports_thinking_toggle', True):
            raise ValueError('This reasoning model has no non-thinking mode')
        sampling = config['profiles']['thinking' if thinking else 'instruct']
        output = Path(output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        messages = [dict(m) for m in messages]
        prefix = config.get('system_prompt_file')
        if prefix:
            messages[0]['content'] = (ROOT/prefix).read_text(encoding='utf-8')+'\n\n'+messages[0]['content']
        canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        template = dict(config.get('chat_template_kwargs', {}))
        thinking_key = config.get('thinking_template_key', 'enable_thinking')
        if thinking_key:
            template[thinking_key] = thinking
        payload = dict(model='local', messages=messages, max_tokens=max_tokens, **sampling,
                       seed=seed, chat_template_kwargs=template, stream=True,
                       stream_options={'include_usage': True}, timings_per_token=True)
        if hasattr(self, 'cache_prompt'):
            payload['cache_prompt'] = self.cache_prompt
        if config.get('response_format'):
            payload['response_format'] = config['response_format']
        if thinking:
            budget = config.get('thinking_budget_tokens', -1) if thinking_budget is None else thinking_budget
            if budget < -1 or budget >= max_tokens:
                raise ValueError('Thinking budget must be -1 or smaller than max-tokens')
            payload['reasoning_budget_tokens'] = budget
        (output/'request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        metadata = {k: config[k] for k in ('model_id', 'original_revision', 'total_parameters',
                    'model_sha256', 'quantization', 'runtime', 'runtime_version')}
        metadata.update(training_model_id=config.get('training_model_id', config['model_id']),
                        training_revision=config.get('training_revision', config['original_revision']),
                        tokenizer=config.get('tokenizer'))
        metadata.update(model_key=self.model, thinking=thinking, **sampling, seed=seed, threads=self.threads,
                        context_tokens=config.get('context_tokens', 4096), max_output_tokens=max_tokens,
                        prompt_sha256=hashlib.sha256(canonical.encode()).hexdigest(), device=self.device.upper(),
                        inference='Local subprocess; temporary loopback HTTP; no hosted API',
                        prompt_format='GGUF native chat template / Jinja',
                        constrained_decoding=bool(config.get('response_format')))
        metadata['reasoning_budget_tokens'] = payload.get('reasoning_budget_tokens', -1)
        metadata['server_args'] = config.get('server_args', [])
        metadata['prompt_cache_enabled'] = getattr(self, 'cache_prompt', True)
        metadata['runtime_source'] = config.get('runtime_source')
        metadata['native_stream_recorded'] = bool(record_stream)
        started = time.monotonic()
        metrics = GenerationMetrics()
        last_progress = float('-inf')
        last_phase = None

        def progress(force=False, finished=False):
            nonlocal last_progress, last_phase
            now = time.monotonic()
            value = metrics.snapshot(finished=finished, partial=finished and finish != 'stop')
            if force or value['phase'] != last_phase or now-last_progress >= 1:
                if on_progress:
                    on_progress(value)
                last_progress = now
                last_phase = value['phase']

        content, reasoning = [], []
        reply = dict(choices=[], usage=None)
        finish = None
        try:
            progress(force=True)
            warm = self.process is not None and self.process.poll() is None
            self.start(output, timeout=min(120, timeout), cancelled=cancelled)
            metadata['model_load_seconds'] = 0. if warm else self.load_seconds
            metadata['hardware'] = self.hardware
            installation = CACHE_ROOT/'runtime'/config['runtime_version']/'installed.json'
            try:
                metadata['runtime_installation'] = json.loads(installation.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                metadata['runtime_installation'] = None
            metrics.ready(metadata['model_load_seconds'])
            progress(force=True)
            request = urllib.request.Request(self.address+'/v1/chat/completions',
                        data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            remaining = max(1, timeout-(time.monotonic()-started))
            with self.opener.open(request, timeout=remaining) as response, \
                    ((output/'stream.jsonl').open('w', encoding='utf-8') if record_stream else nullcontext(None)) as events:
                for line in response:
                    if cancelled and cancelled():
                        raise GenerationCancelled('Generation cancelled')
                    if time.monotonic()-started > timeout:
                        raise TimeoutError('Generation exceeded the time limit')
                    line = line.decode('utf-8').strip()
                    if not line.startswith('data: '):
                        continue
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    chunk = json.loads(data)
                    if events is not None:
                        events.write(json.dumps(chunk, ensure_ascii=False)+'\n')
                        events.flush()
                    if on_native:
                        on_native(chunk)
                    metrics.update(chunk)
                    progress()
                    if chunk.get('error'):
                        raise RuntimeError(str(chunk['error']))
                    if chunk.get('usage'):
                        reply['usage'] = chunk['usage']
                    if chunk.get('timings'):
                        reply['timings'] = chunk['timings']
                    for choice in chunk.get('choices', []):
                        delta = choice.get('delta', {})
                        for key, buffer in [('content', content), ('reasoning_content', reasoning)]:
                            piece = delta.get(key) or ''
                            if piece:
                                buffer.append(piece)
                                if on_delta:
                                    on_delta(key, piece)
                        finish = choice.get('finish_reason') or finish
            metadata.update(finish_reason=finish, usage=reply.get('usage'), timings=reply.get('timings'))
            if finish != 'stop':
                raise ValueError('Generation did not finish normally: '+str(finish))
        except BaseException as error:
            if cancelled and cancelled():
                error = GenerationCancelled('Generation cancelled')
            metadata['error'] = type(error).__name__+': '+str(error)
            raise error
        finally:
            # Preserve timing and partial-token evidence on cancellation/truncation as well.
            metadata.update(finish_reason=finish, usage=reply.get('usage'), timings=reply.get('timings'))
            metadata['performance'] = metrics.snapshot(finished=True, partial=finish != 'stop')
            raw, thoughts = ''.join(content), ''.join(reasoning)
            reply['choices'] = [dict(finish_reason=finish, message=dict(role='assistant', content=raw, reasoning_content=thoughts))]
            (output/'response.json').write_text(json.dumps(reply, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            metadata['generation_seconds'] = time.monotonic()-started
            (output/'generation.json').write_text(json.dumps(metadata, indent=2)+'\n')
            progress(force=True, finished=True)
        return raw, metadata

    def cancel(self):
        # Terminating the private process interrupts a blocked HTTP read as well.
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

    def close(self):
        self.cancel()
        if self.process is not None:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
