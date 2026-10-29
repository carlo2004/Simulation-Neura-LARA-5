"""Real loopback transport with controlled replies: harness tests, not model scores."""
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from stacklab.llm.catalog import lock
from stacklab.llm.remote import RemoteModel, endpoint
from stacklab.llm.runtime import GenerationCancelled
from stacklab.llm.service import InferenceHandler, InferenceServer
from stacklab.paths import ROOT


class ControlledModel:
    def __init__(self):
        self.config = lock('lfm2.6b')
        self.hardware = None
        self.threads = 1
        self.entered = threading.Event()
        self.interrupted = threading.Event()
        self.cancel_count = 0
        self.calls = []

    def complete(self, messages, output, **options):
        self.interrupted.clear()
        self.calls.append(dict(messages=messages, options={k:v for k,v in options.items() if not callable(v)}))
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(dict(code='robot.jog("x", 0.05)', done=True, message='CONTROLLED TEST REPLY'))
        request = dict(messages=messages, seed=options['seed'])
        metadata = dict(model_id='CONTROLLED TEST REPLY; NO REAL INFERENCE', finish_reason='stop',
                        performance=dict(decode_tokens_per_second=12.5, partial=False))
        self.entered.set()
        try:
            options['on_progress'](dict(phase='generating', decode_tokens_per_second=12.5))
            if messages[-1]['content'] == 'block':
                while not (options['cancelled']() or self.interrupted.wait(.01)):
                    pass
                raise GenerationCancelled('Controlled cancellation')
            chunk = dict(choices=[dict(delta=dict(content=raw), finish_reason='stop')])
            (output/'stream.jsonl').write_text(json.dumps(chunk, ensure_ascii=False)+'\n', encoding='utf-8')
            options['on_native'](chunk)
            options['on_delta']('content', raw)
            if messages[-1]['content'] == 'fail':
                raise ValueError('Controlled generation failure')
            return raw, metadata
        finally:
            (output/'request.json').write_text(json.dumps(request), encoding='utf-8')
            (output/'response.json').write_text(json.dumps(dict(choices=[dict(message=dict(content=raw))])), encoding='utf-8')
            (output/'generation.json').write_text(json.dumps(metadata), encoding='utf-8')

    def cancel(self):
        self.cancel_count += 1
        self.interrupted.set()


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = ControlledModel()
        self.server = InferenceServer(self.model, self.root/'server', port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs=dict(poll_interval=.02), daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = 'http://127.0.0.1:'+str(self.server.server_port)
        self.client = RemoteModel(self.url)

    def stop_server(self):
        self.model.cancel()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def generate(self, text='Hello Würfel', client=None, output=None, **kwargs):
        return (client or self.client).complete([dict(role='user', content=text)], output or self.root/'local', **kwargs)

    def test_only_loopback_endpoints_are_accepted_without_proxy_or_credentials(self):
        for url in ('https://example.com', 'http://192.168.1.2:8765', 'http://127.0.0.1@evil.test',
                    'http://user@localhost:8765', 'http://localhost:8765/path', 'http://localhost?key=x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                endpoint(url)
        self.assertEqual(endpoint('http://[::1]:8765/'), ('::1', 8765))

    def test_streams_and_native_evidence_survive_the_round_trip_unchanged(self):
        deltas, progress = [], []
        raw, metadata = self.generate(seed=109, thinking=False, thinking_budget=100,
            on_delta=lambda kind, text: deltas.append(text), on_progress=progress.append)
        local = self.root/'local'
        native = next((self.root/'server').iterdir())
        for name in ('request.json', 'response.json'):
            self.assertEqual(json.loads((local/name).read_text()), json.loads((native/name).read_text()))
        self.assertEqual((local/'stream.jsonl').read_bytes(), (native/'stream.jsonl').read_bytes())
        self.assertEqual(''.join(deltas), raw)
        self.assertEqual(progress[-1]['decode_tokens_per_second'], 12.5)
        self.assertEqual(metadata, json.loads((local/'generation.json').read_text()))
        self.assertEqual(metadata['transport']['server_id'], self.server.info['server_id'])
        self.assertEqual(self.model.calls[0]['options']['seed'], 109)
        self.assertIs(self.model.calls[0]['options']['thinking'], False)
        self.assertEqual(self.model.calls[0]['options']['thinking_budget'], 100)
        self.assertEqual(self.model.calls[0]['messages'][0]['content'], 'Hello Würfel')

    def test_expected_model_mismatch_fails_before_generation(self):
        with self.assertRaisesRegex(ValueError, 'differs'):
            RemoteModel(self.url, model='qwen9b')
        self.assertEqual(self.model.calls, [])

    def test_restarted_server_cannot_silently_change_the_model(self):
        self.server.info['server_id'] = uuid4().hex
        with self.assertRaisesRegex(RuntimeError, 'restarted'):
            self.generate()
        self.assertEqual(self.model.calls, [])

    def test_remote_generation_error_keeps_original_server_evidence(self):
        with self.assertRaisesRegex(ValueError, 'Controlled generation failure'):
            self.generate('fail')
        local = self.root/'local'
        self.assertTrue((local/'stream.jsonl').read_text())
        self.assertTrue((local/'server-generation.json').is_file())
        self.assertIn('Controlled generation failure', json.loads((local/'generation.json').read_text())['error'])

    def test_cancellation_stops_the_request_and_another_prompt_can_run(self):
        errors = []
        def run():
            try:
                self.generate('block')
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=run)
        worker.start()
        self.assertTrue(self.model.entered.wait(2))
        started = time.monotonic()
        self.client.cancel()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertLess(time.monotonic()-started, 3)
        self.assertIsInstance(errors[0], GenerationCancelled)
        deadline = time.monotonic()+2
        while self.server.active is not None and time.monotonic() < deadline:
            time.sleep(.01)
        raw, _ = self.generate(output=self.root/'after-cancel')
        self.assertIn('robot.jog', raw)

    def test_busy_client_cannot_cancel_another_clients_request(self):
        errors = []
        def run():
            try:
                self.generate('block')
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=run)
        worker.start()
        self.assertTrue(self.model.entered.wait(2))
        other = RemoteModel(self.url)
        with self.assertRaisesRegex(RuntimeError, 'busy'):
            self.generate(client=other, output=self.root/'other')
        self.assertFalse(self.model.interrupted.is_set())
        self.client.cancel()
        worker.join(3)
        self.assertFalse(worker.is_alive())

    def test_timeout_stops_remote_work_and_keeps_partial_metadata(self):
        with self.assertRaises(TimeoutError):
            self.generate('block', timeout=.25)
        metadata = json.loads((self.root/'local/generation.json').read_text())
        self.assertTrue(metadata['performance']['partial'])
        self.assertIsNone(metadata['finish_reason'])

    def test_dropped_connection_preserves_partial_output_and_never_returns_a_program(self):
        def disconnect(handler):
            handler.send_response(200)
            handler.end_headers()
            data = dict(event='delta', data=dict(kind='content', text='robot.jog('))
            handler.wfile.write((json.dumps(data)+'\n').encode())
            handler.wfile.flush()
        with patch.object(InferenceHandler, 'do_POST', disconnect), self.assertRaisesRegex(RuntimeError, 'ended before'):
            self.generate()
        partial = json.loads((self.root/'local/response.json').read_text())
        self.assertEqual(partial['choices'][0]['message']['content'], 'robot.jog(')
        metadata = json.loads((self.root/'local/generation.json').read_text())
        self.assertIsNone(metadata['finish_reason'])
        self.assertTrue(metadata['performance']['partial'])

    def test_server_rejects_filesystem_options_before_calling_the_model(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        body = dict(server_id=self.server.info['server_id'], request_id=uuid4().hex,
                    messages=[dict(role='user', content='hi')], options=dict(output='/tmp/not-allowed'))
        connection.request('POST', '/generate', json.dumps(body), {'Content-Type': 'application/json'})
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        connection.close()
        self.assertEqual(self.model.calls, [])

    def test_real_chat_process_executes_a_remote_program_in_local_physics_without_local_weights(self):
        output = self.root/'chat'
        result = subprocess.run([sys.executable, '-m', 'stacklab', 'chat', '--headless',
            '--server-url', self.url, '--prompt', 'Bewege nach rechts.', '--output', str(output)],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        task = json.loads((output/'task_001/result.json').read_text())
        before = task['initial_observation']['tcp_m']
        after = task['final_observation']['tcp_m']
        self.assertAlmostEqual(after[0]-before[0], .05, delta=.001)
        self.assertAlmostEqual(after[1]-before[1], 0, delta=.001)
        self.assertIn('Remote-Modell', result.stdout)
        self.assertEqual(task['rounds'][0]['execution_outcome'], 'executed')
        self.assertEqual(task['rounds'][0]['generation']['transport']['server_id'], self.server.info['server_id'])


if __name__ == '__main__':
    unittest.main()
