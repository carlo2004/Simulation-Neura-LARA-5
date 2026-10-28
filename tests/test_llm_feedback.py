"""Offline harness controls. Fake model answers here are not model benchmark results."""
from contextlib import redirect_stdout, closing
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import numpy as np
from core import Config
from simulation import Simulation
from llm_agent import Agent, parse_reply, system_prompt, model_json
from llm_evaluation import observe
from llm_runtime import ROOT, lock, model_keys, download
from llm_session import GenerationCancelled, LocalModel
from policy_language import Interpreter, PolicyCancelled

MOVE = 'p = robot.position("tcp")\nrobot.move_to([p[0] + 0.05, p[1], p[2]])'
STACK = '''a = robot.position("red")
b = robot.position("blue")
robot.gripper(False)
robot.move_to([a[0], a[1], 0.24])
robot.move_to(a)
robot.gripper(True)
robot.move_to([a[0], a[1], 0.24])
robot.move_to([b[0], b[1], 0.24])
robot.move_to([b[0], b[1], b[2] + 0.041])
robot.gripper(False)
robot.move_to([b[0], b[1], 0.24])'''


class FakeModel:
    def __init__(self, replies, model='qwen4b', threads=1):
        self.config = lock(model)
        self.replies = iter(replies)
        self.requests = []
        self.stopped = threading.Event()

    def complete(self, messages, directory, **kwargs):
        self.requests.append(messages)
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(next(self.replies))
        (path/'raw_response.txt').write_text(raw)
        (path/'messages.json').write_text(json.dumps(messages))
        return raw, dict(model_id='TEST FIXTURE; NOT REAL INFERENCE')

    def cancel(self):
        self.stopped.set()

    def close(self):
        self.cancel()


class FeedbackTests(unittest.TestCase):
    def test_registry_accepts_requested_models_and_exact_ids(self):
        self.assertEqual(set(model_keys()), {'qwen4b', 'qwen9b', 'ministral8b', 'nemotron8b'})
        for key in ['qwen9b', 'ministral8b', 'nemotron8b']:
            config = lock(key)
            self.assertGreater(config['total_parameters'], 7_000_000_000)
            self.assertLess(config['total_parameters'], 10_000_000_000)
            self.assertEqual(lock(config['model_id'])['model_sha256'], config['model_sha256'])
        with self.assertRaises(ValueError):
            lock('nonexistent')

    def test_reply_types_and_single_unambiguous_protocol(self):
        self.assertTrue(parse_reply('{"code":"", "done":true}')['done'])
        for raw in ['{"code":"x", "done":1}', '{"code":"x", "unexpected":1}', 'bad']:
            with self.assertRaises(ValueError):
                parse_reply(raw)
        prompt = system_prompt()
        self.assertNotIn('exactly one key', prompt)
        self.assertIn('"done" (boolean)', prompt)

    def test_model_formatting_is_precise_without_float_tails_or_mutation(self):
        value = dict(tcp=[.4499999999999998, .019957398275963014, .26], valid=True)
        formatted = json.loads(model_json(value))
        self.assertEqual(formatted['tcp'][0], .45)
        np.testing.assert_allclose(formatted['tcp'], value['tcp'], atol=.0000005, rtol=0)
        self.assertEqual(value['tcp'][0], .4499999999999998)
        self.assertIs(formatted['valid'], True)

    def test_tcp_read_and_action_trace_match_measured_position(self):
        with closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            events = []
            runner = Interpreter(robot, on_action=lambda phase, data: events.append((phase, data['method'])))
            runner.run('p = robot.position("tcp")')
            np.testing.assert_allclose(runner.variables['p'], robot.data.site_xpos[robot.sid])
            self.assertEqual(events, [('start', 'position'), ('end', 'position')])

    def test_jog_is_relative_and_preserves_the_other_axes(self):
        with closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            initial = robot.data.site_xpos[robot.sid].copy()
            runner = Interpreter(robot)
            runner.run('robot.jog("x", 0.05)')
            np.testing.assert_allclose(robot.data.site_xpos[robot.sid], initial+[.05, 0, 0], atol=.001)
            runner.run('robot.jog("x", -0.05)')
            np.testing.assert_allclose(robot.data.site_xpos[robot.sid], initial, atol=.001)

    def test_invalid_jog_does_not_change_the_controller_target(self):
        from policy_language import PolicyError
        with closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            before = robot.command.copy()
            for code in ['robot.jog("bad", .05)', 'robot.jog("x", 9)', 'robot.jog("x", True)']:
                with self.assertRaises(PolicyError):
                    Interpreter(robot).run(code)
                np.testing.assert_array_equal(robot.command, before)

    def test_feedback_contains_real_error_and_repairs_movement(self):
        replies = [dict(code='robot.move_to([9, 0, .2])', done=True), dict(code=MOVE, done=True)]
        with tempfile.TemporaryDirectory() as temp, closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            target = robot.data.site_xpos[robot.sid]+[.05, 0, 0]
            client = FakeModel(replies)
            agent = Agent(robot, client, max_rounds=2)
            report = agent.run_task('5 cm nach rechts', Path(temp)/'episode',
                                    goal=dict(type='move', target_m=target.tolist()))
            self.assertTrue(report['success'])
            self.assertEqual(len(client.requests), 2)
            feedback = json.loads(client.requests[1][-1]['content'])['feedback']
            self.assertIn('workspace', feedback['error'])
            self.assertFalse(feedback['evaluation']['success'])
            self.assertLess(report['evaluation']['tcp_error_m'], .004)
            self.assertEqual(report['rounds'][0]['actions'][0]['status'], 'error')

    def test_model_done_cannot_override_failed_stack_check(self):
        with tempfile.TemporaryDirectory() as temp, closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            client = FakeModel([dict(code='robot.step(.1)', done=True), dict(code=STACK, done=True)])
            report = Agent(robot, client, max_rounds=2).run_task(
                'Rot auf Blau', Path(temp)/'episode', goal=dict(type='stack', source='red', target='blue'))
            self.assertTrue(report['success'])
            self.assertEqual(len(report['rounds']), 2)
            self.assertEqual(report['evaluation']['stack_checks'][0]['stable_checks'], 20)
            self.assertTrue(report['evaluation']['stack_checks'][0]['tool_clear'])

    def test_free_form_live_task_never_claims_independent_semantic_success(self):
        with tempfile.TemporaryDirectory() as temp, closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            before = observe(robot)['tcp_m']
            report = Agent(robot, FakeModel([dict(code=MOVE, done=True), dict(code='', done=True)])).run_task('rechts', Path(temp)/'episode')
            self.assertIsNone(report['success'])
            self.assertEqual(report['status'], 'model_finished')
            self.assertAlmostEqual(report['final_observation']['tcp_m'][0]-before[0], .05, delta=.004)

    def test_motion_can_be_interrupted_inside_a_move(self):
        with closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            before = robot.data.site_xpos[robot.sid].copy()
            count = 0
            def stop():
                nonlocal count
                count += 1
                if count == 5:
                    raise PolicyCancelled('stop fixture')
            robot.command_interrupt = stop
            with self.assertRaises(PolicyCancelled):
                robot.move_to(before+[.05, 0, 0])
            robot.command_interrupt = None
            self.assertLess(np.linalg.norm(robot.data.site_xpos[robot.sid]-before), .01)

    def test_generation_cancel_unblocks_the_agent(self):
        class SlowModel(FakeModel):
            def complete(self, messages, directory, **kwargs):
                limit = time.monotonic()+5
                while time.monotonic() < limit:
                    if kwargs['cancelled']():
                        raise GenerationCancelled('fixture cancelled')
                    time.sleep(.01)
                raise AssertionError('Cancellation failed')
        with tempfile.TemporaryDirectory() as temp, closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            agent = Agent(robot, SlowModel([]))
            agent.tick = agent.stop
            report = agent.run_task('rechts', Path(temp)/'episode')
            self.assertEqual(report['status'], 'cancelled')
            self.assertIsNone(robot.command_interrupt)

    def test_ctrl_c_is_recorded_as_cancelled_before_exiting(self):
        class InterruptedModel(FakeModel):
            def complete(self, *args, **kwargs):
                raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as temp, closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            directory = Path(temp)/'episode'
            with self.assertRaises(KeyboardInterrupt):
                Agent(robot, InterruptedModel([])).run_task('rechts', directory)
            report = json.loads((directory/'result.json').read_text())
            self.assertEqual(report['status'], 'cancelled')
            self.assertIsNone(robot.command_interrupt)

    def test_live_cli_repeated_prompts_keep_the_same_world(self):
        import llm_chat
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()) as stdout:
            client = FakeModel([dict(code=MOVE, done=True), dict(code='', done=True),
                                dict(code=MOVE, done=True), dict(code='', done=True)])
            with patch.object(llm_chat, 'LocalModel', return_value=client):
                code = llm_chat.main(['--headless', '--prompt', 'rechts', '--prompt', 'nochmal rechts',
                                      '--output', str(Path(temp)/'chat')])
            self.assertEqual(code, 0)
            first = json.loads((Path(temp)/'chat/task_001/result.json').read_text())
            second = json.loads((Path(temp)/'chat/task_002/result.json').read_text())
            self.assertAlmostEqual(second['initial_observation']['tcp_m'][0],
                                   first['final_observation']['tcp_m'][0], delta=.001)
            self.assertIn('robot.position', stdout.getvalue())

    def test_cancelled_live_task_is_not_presented_as_model_completion(self):
        import llm_chat
        class CancelledModel(FakeModel):
            def complete(self, *args, **kwargs):
                raise GenerationCancelled('fixture cancelled')
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()) as stdout:
            with patch.object(llm_chat, 'LocalModel', return_value=CancelledModel([])):
                code = llm_chat.main(['--headless', '--prompt', 'rechts', '--output', str(Path(temp)/'chat')])
            self.assertEqual(code, 1)
            self.assertIn('Status: cancelled', stdout.getvalue())
            self.assertNotIn('Fertigmeldung', stdout.getvalue())

    def test_physics_clock_pauses_during_generation(self):
        class DelayedModel(FakeModel):
            def complete(self, *args, **kwargs):
                time.sleep(.08)
                return super().complete(*args, **kwargs)
        with tempfile.TemporaryDirectory() as temp, closing(Simulation(Config.load(ROOT/'scenario.json'))) as robot:
            started = float(robot.data.time)
            measured = []
            agent = Agent(robot, DelayedModel([dict(code='', done=True)]),
                          on_event=lambda kind, data: measured.append(float(robot.data.time)) if kind == 'program' else None)
            result = agent.run_task('Keine Bewegung', Path(temp)/'episode')
            self.assertEqual(result['status'], 'model_finished')
            self.assertEqual(measured, [started])


class StreamTests(unittest.TestCase):
    def test_setup_keeps_the_model_alias_after_resolving_weight_path(self):
        import llm_runtime
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            cache = Path(temp)
            config = lock('qwen9b')
            directory = cache/'runtime'/config['runtime_version']
            directory.mkdir(parents=True)
            asset = config['runtime_assets'][llm_runtime.platform_key()]
            (directory/'installed.json').write_text(json.dumps({'sha256': asset['sha256']}))
            with patch.object(llm_runtime, 'CACHE_ROOT', cache), \
                 patch.object(llm_runtime, 'download', side_effect=lambda url, path, *args: path), \
                 patch.object(llm_runtime, 'find_executable', return_value=cache/'llama-server') as find:
                self.assertEqual(llm_runtime.setup('qwen9b'), cache/'llama-server')
                find.assert_called_once_with('qwen9b')

    def test_completed_partial_download_is_verified_and_recovered_offline(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'model.gguf'
            partial = target.with_name(target.name+'.part')
            partial.write_bytes(b'verified model fixture')
            digest = hashlib.sha256(partial.read_bytes()).hexdigest()
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network must not be needed')):
                self.assertEqual(download('unused', target, digest, partial.stat().st_size), target)
            self.assertFalse(partial.exists())
            self.assertEqual(target.read_bytes(), b'verified model fixture')

    def test_sse_preserves_content_usage_and_request_budget(self):
        pieces = [dict(choices=[dict(delta={'reasoning_content': 'think'}, finish_reason=None)]),
                  dict(choices=[dict(delta={'content': '{"code":"robot.step(0.1)"}'}, finish_reason=None)]),
                  dict(choices=[dict(delta={}, finish_reason='stop')], usage={'completion_tokens': 10})]
        data = ''.join('data: '+json.dumps(p)+'\n\n' for p in pieces)+'data: [DONE]\n\n'
        with tempfile.TemporaryDirectory() as temp:
            client = LocalModel('qwen9b')
            with patch.object(client, 'start'), patch.object(client.opener, 'open', return_value=io.BytesIO(data.encode())) as opened:
                client.address = 'http://127.0.0.1:12345'
                raw, metadata = client.complete([dict(role='system', content='fixture'),
                                                 dict(role='user', content='fixture')], temp)
            self.assertEqual(json.loads(raw)['code'], 'robot.step(0.1)')
            self.assertEqual(metadata['usage']['completion_tokens'], 10)
            self.assertEqual(metadata['reasoning_budget_tokens'], 768)
            self.assertEqual((Path(temp)/'reasoning.txt').read_text(), 'think')
            request = json.loads(opened.call_args.args[0].data)
            self.assertEqual(request['reasoning_budget_tokens'], 768)
            self.assertNotIn('response_format', request)


if __name__ == '__main__':
    unittest.main()
