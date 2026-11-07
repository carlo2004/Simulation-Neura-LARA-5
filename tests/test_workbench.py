from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from io import BytesIO
import json
import unittest
from unittest.mock import patch

import numpy as np

from stacklab.cli.workbench import Handler, decode_answer, load_models
from stacklab.workbench_policy import PolicyError, WorkbenchPolicy


class Robot:
    def __init__(self):
        self.data = SimpleNamespace(time=0.)
        self.moves = []

    def get_object_position(self, oid):
        return np.array([.4, float(oid)/10, .02])

    def move_to(self, *position):
        self.moves.append(position)


class WorkbenchTests(unittest.TestCase):
    def test_hf_answer_reaches_the_policy_without_flattening_run(self):
        code = "def run(robot):\n    x, y, z = robot.get_object_position(2)\n    robot.move_to(x, y, z + 0.1)"
        legacy = json.dumps({'code': code, 'message': ''})
        for raw in (code, "\x60\x60\x60python\n" + code + "\n\x60\x60\x60",
                    legacy, "\x60\x60\x60json\n" + legacy + "\n\x60\x60\x60"):
            with self.subTest(raw=raw):
                reply = decode_answer(raw)
                self.assertEqual(reply, {'code': code, 'message': ''})
                robot = Robot()
                WorkbenchPolicy(robot).run(reply['code'])
                np.testing.assert_allclose(robot.moves, [[.4, .2, .12]])

        refusal = 'I only see 1 (red) and 2 (blue). Which cube should I use?'
        self.assertEqual(decode_answer(refusal), {'code': '', 'message': refusal})
        with self.assertRaisesRegex(ValueError, 'empty'):
            decode_answer('  ')

    def test_mixed_json_and_python_is_reported_as_invalid_json(self):
        with self.assertRaisesRegex(ValueError, 'Invalid JSON response'):
            decode_answer('{}\ndef run(robot):\n    robot.open_gripper()')

    def test_comparison_sends_native_user_messages_for_both_sides(self):
        sample = {'id': 'scene', 'user_prompt': 'Objects: 1 (red), 3 (blue)\nStack the cubes.\n',
                  'split': 'train', 'subcategory': 'stack', 'expected_behavior': 'execute',
                  'scene': {'objects': {'1': {'position': [.4, .1, .02]}}},
                  'destination': 'private goal', 'assistant_answer': 'private reference'}
        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(
            system='HF system prompt', lock={'repository': 'fixture', 'revision': 'abc'}, git_revision='def',
            models={'base': {'label': 'Base', 'model': 'base'}, 'tuned': {'label': 'Fine-Tuning', 'model': 'tuned'}},
            checker=Path('check.py'))
        handler.wfile = BytesIO()
        for name in ('send_response', 'send_header', 'end_headers'):
            setattr(handler, name, lambda *args: None)

        code = 'def run(robot):\n    robot.open_gripper()'
        message = 'Which cube should I move?'
        answers = [(code, {}, 'base', 'stop'), (message, {}, 'tuned', 'stop')]
        with patch('stacklab.cli.workbench.completion', side_effect=answers) as generate, \
                patch('stacklab.cli.workbench.simulate', return_value={}) as simulate, \
                patch('stacklab.cli.workbench.write_json') as save:
            handler.stream_job('compare', sample, '', [('left', 'base', 'Stack the cubes.'),
                                                      ('right', 'tuned', 'Move up.')], 120)

        system = {'role': 'system', 'content': handler.server.system}
        self.assertEqual(generate.call_args_list[0].args[1],
                         [system, {'role': 'user', 'content': sample['user_prompt']}])
        self.assertEqual(generate.call_args_list[1].args[1],
                         [system, {'role': 'user', 'content': 'Objects: 1 (red), 3 (blue)\nMove up.'}])
        self.assertEqual(simulate.call_args_list[0].args[2], {'code': code, 'message': ''})
        self.assertEqual(simulate.call_args_list[1].args[2], {'code': '', 'message': message})
        self.assertFalse(simulate.call_args_list[0].kwargs['unscored'])
        self.assertTrue(simulate.call_args_list[1].kwargs['unscored'])
        self.assertEqual([call.kwargs['speed_mm_s'] for call in simulate.call_args_list], [120, 120])
        self.assertTrue(all(not call.kwargs.get('video') for call in simulate.call_args_list))
        report = json.loads(handler.wfile.getvalue().splitlines()[-1])['report']
        self.assertEqual(report, save.call_args.args[1])
        self.assertEqual(report['runner_revision'], 'def')
        self.assertEqual(report['speed_mm_s'], 120)
        self.assertGreaterEqual(report['results']['left']['simulation_wall_seconds'], 0)
        self.assertEqual(report['results']['left']['model_identity']['api_model'], 'base')
        self.assertEqual(report['results']['right']['user_prompt'], 'Objects: 1 (red), 3 (blue)\nMove up.')

    def test_run_trace_separates_malformed_replies_from_execution(self):
        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(checker=Path('check.py'))
        invalid = '{"code":'
        output = {'actions': [], 'scored': True, 'metrics': {}}
        with patch('stacklab.cli.workbench.completion', return_value=(invalid, {}, 'base', 'stop')), \
                patch('stacklab.cli.workbench.simulate') as simulate:
            handler.run_lane('single', {}, '', {'model': 'base'}, [], output, 'run', lambda *a, **kw: None)
        simulate.assert_not_called()
        self.assertEqual(output['raw'], invalid)
        self.assertEqual(output['error_stage'], 'response')

        step = {'method': 'move_to', 'args': [.4, .1, .2], 'time_s': 1.0, 'step': 1, 'status': 'error'}

        def failed_motion(checker, sample, reply, directory, emit, **kwargs):
            emit('action', **step)
            return {'passed': False, 'stage': 'execution', 'reasons': ['Target unreachable']}

        output = {'actions': [], 'scored': True, 'metrics': {}}
        with patch('stacklab.cli.workbench.simulate', side_effect=failed_motion):
            handler.run_lane('code', {}, 'def run(robot):\n    pass', None, [], output, 'run', lambda *a, **kw: None)
        self.assertEqual(output['actions'], [step])
        self.assertEqual(output['check']['stage'], 'execution')

    def test_model_policy_uses_helpers_positions_and_bounded_loops(self):
        robot = Robot()
        policy = WorkbenchPolicy(robot)
        actions = policy.run("""def run(robot):
    ids = [1, 2]
    def hover(obj):
        x, y, z = robot.get_object_position(obj)
        if z < 0.03:
            return [x, y, z + 0.2]
        return [x, y, z]
    for p in [hover(i) for i in ids]:
        robot.move_to(*p)
""")
        self.assertEqual(len(actions), 4)
        np.testing.assert_allclose(robot.moves, [[.4, .1, .22], [.4, .2, .22]])

    def test_unknown_attributes_reject_the_whole_program_before_motion(self):
        robot = Robot()
        for statement in ('np.load("/tmp/example")', 'robot.__class__', 'import os'):
            with self.subTest(statement=statement), self.assertRaises(PolicyError):
                WorkbenchPolicy(robot).run('def run(robot):\n    robot.move_to(.4, .1, .2)\n    ' + statement)
        self.assertEqual(robot.moves, [])

    def test_large_values_and_loops_are_rejected(self):
        for statement in ('for i in range(10000):\n        pass',
                          'np.array([1], "U100000")',
                          'x = [1]\n    for i in range(8):\n        x = [x, x, x, x]'):
            with self.subTest(statement=statement), self.assertRaises(PolicyError):
                WorkbenchPolicy(Robot()).run('def run(robot):\n    ' + statement)

    def test_model_hosts_are_loopback_only(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'models.json'
            model = {'label': 'Base', 'protocol': 'openai', 'url': 'http://127.0.0.1:8081/v1', 'model': 'base'}
            path.write_text(json.dumps({'base': model}), encoding='utf-8')
            self.assertEqual(load_models(path), {'base': model})
            model['weights'] = {'file': 'Model-Q4_K_M.gguf', 'sha256': 'a' * 64, 'bytes': 123}
            path.write_text(json.dumps({'base': model}), encoding='utf-8')
            self.assertEqual(load_models(path), {'base': model})
            model['weights']['file'] = '/private/Model-Q4_K_M.gguf'
            path.write_text(json.dumps({'base': model}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'weights identity'):
                load_models(path)
            model['url'] = 'https://external.example/v1'
            path.write_text(json.dumps({'base': model}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'loopback'):
                load_models(path)

    def test_paired_and_individual_jobs_keep_prompts_on_their_side(self):
        original = {'id': 'scene', 'user_prompt': 'Objects: 1 (red)\nStack the cubes.'}
        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(samples={'scene': original}, models={'base': {}, 'tuned': {}})

        def job(**values):
            body = json.dumps(dict(task='scene', **values)).encode()
            handler.headers = {'Content-Length': str(len(body))}
            handler.rfile = BytesIO(body)
            return handler.read_job()

        _, sample, _, lanes, speed = job(mode='compare', left='base', right='tuned', speed_mm_s=120,
                                         prompts={'left': 'Stack the cubes.', 'right': 'Move up.'})
        self.assertEqual(sample, original)
        self.assertEqual(lanes, [('left', 'base', 'Stack the cubes.'), ('right', 'tuned', 'Move up.')])
        self.assertEqual(job(mode='single', side='right', model='tuned', prompt='Rotate.')[3:],
                         ([('right', 'tuned', 'Rotate.')], 80))
        with self.assertRaisesRegex(ValueError, 'Prompts must be text'):
            job(mode='compare', left='base', right='tuned', prompts={'right': ['invalid']})
        with self.assertRaisesRegex(ValueError, 'arm speed'):
            job(mode='reference', speed_mm_s='120')

    def test_video_export_replays_saved_lane_without_model_inference(self):
        handler = Handler.__new__(Handler)
        sample = {'id': 'scene', 'user_prompt': 'Original'}
        handler.server = SimpleNamespace(checker=Path('check.py'), git_revision='code',
                                         lock={'revision': 'data'}, samples={'scene': sample})
        run_id = 'a' * 32
        code = 'def run(robot):\n    robot.open_gripper()'
        result = dict(code=code, message='', scored=False, user_prompt='Custom', check={'initial_state': {'ok': True}})
        report = dict(id=run_id, task='scene', mode='single', runner_revision='code', revision='data',
                      status='complete', speed_mm_s=120, results={'right': result})
        body = json.dumps({'id': run_id, 'lane': 'right'}).encode()
        handler.headers = {'Content-Length': str(len(body))}
        handler.rfile, handler.wfile = BytesIO(body), BytesIO()
        for name in ('send_response', 'send_header', 'end_headers'):
            setattr(handler, name, lambda *args: None)

        def encode(checker, scene, reply, output, emit, **kwargs):
            self.assertEqual(scene, dict(sample, user_prompt='Custom'))
            self.assertEqual(reply, {'code': code, 'message': ''})
            self.assertIsNone(emit)
            self.assertEqual(kwargs, dict(generated=True, unscored=True, run_id=run_id, speed_mm_s=120, video=True))
            (output/'scene.mp4').write_bytes(b'video')
            return {'video': 'scene.mp4'}

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)/'workbench'
            directory.mkdir()
            (directory/(run_id + '.json')).write_text(json.dumps(report), encoding='utf-8')
            with patch('stacklab.cli.workbench.RUNS_ROOT', Path(tmp)), \
                    patch('stacklab.cli.workbench.simulate', side_effect=encode), \
                    patch('stacklab.cli.workbench.completion') as generate:
                handler.export_video(*handler.read_video_job())
                generate.assert_not_called()
        self.assertEqual(handler.wfile.getvalue(), b'video')
