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
                  'scene': {'objects': {'1': {'position': [.4, .1, .02]}}},
                  'destination': 'private goal', 'assistant_answer': 'private reference'}
        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(
            system='HF system prompt', lock={'repository': 'fixture', 'revision': 'abc'},
            models={'base': {'label': 'Base'}, 'tuned': {'label': 'Fine-Tuning'}}, checker=Path('check.py'))
        handler.wfile = BytesIO()
        for name in ('send_response', 'send_header', 'end_headers'):
            setattr(handler, name, lambda *args: None)

        code = 'def run(robot):\n    robot.open_gripper()'
        message = 'Which cube should I move?'
        answers = [(code, {}, 'base', 'stop'), (message, {}, 'tuned', 'stop')]
        with patch('stacklab.cli.workbench.completion', side_effect=answers) as generate, \
                patch('stacklab.cli.workbench.simulate', return_value={}) as simulate:
            handler.stream_job('compare', sample, '', [('left', 'base', 'Stack the cubes.'),
                                                      ('right', 'tuned', 'Move up.')])

        system = {'role': 'system', 'content': handler.server.system}
        self.assertEqual(generate.call_args_list[0].args[1],
                         [system, {'role': 'user', 'content': sample['user_prompt']}])
        self.assertEqual(generate.call_args_list[1].args[1],
                         [system, {'role': 'user', 'content': 'Objects: 1 (red), 3 (blue)\nMove up.'}])
        self.assertEqual(simulate.call_args_list[0].args[2], {'code': code, 'message': ''})
        self.assertEqual(simulate.call_args_list[1].args[2], {'code': '', 'message': message})
        self.assertFalse(simulate.call_args_list[0].kwargs['unscored'])
        self.assertTrue(simulate.call_args_list[1].kwargs['unscored'])

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
            model['url'] = 'https://external.example/v1'
            path.write_text(json.dumps({'base': model}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'loopback'):
                load_models(path)

    def test_paired_and_individual_jobs_keep_prompts_on_their_side(self):
        original = {'id': 'scene', 'user_prompt': 'Objects: 1 (red)\nStack the cubes.'}
        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(cases={'scene': original}, models={'base': {}, 'tuned': {}})

        def job(**values):
            body = json.dumps(dict(task='scene', **values)).encode()
            handler.headers = {'Content-Length': str(len(body))}
            handler.rfile = BytesIO(body)
            return handler.read_job()

        _, sample, _, lanes = job(mode='compare', left='base', right='tuned',
                                  prompts={'left': 'Stack the cubes.', 'right': 'Move up.'})
        self.assertEqual(sample, original)
        self.assertEqual(lanes, [('left', 'base', 'Stack the cubes.'), ('right', 'tuned', 'Move up.')])
        self.assertEqual(job(mode='single', side='right', model='tuned', prompt='Rotate.')[3],
                         [('right', 'tuned', 'Rotate.')])
        with self.assertRaisesRegex(ValueError, 'Prompts must be text'):
            job(mode='compare', left='base', right='tuned', prompts={'right': ['invalid']})
