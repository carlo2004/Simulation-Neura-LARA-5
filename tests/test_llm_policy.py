import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import llm_runtime
from policy_language import Interpreter, PolicyError, validate


class FakeRobot:
    object_names = ('red', 'blue')
    def __init__(self):
        self.data = SimpleNamespace(time=0.)
        self.moves = []
        self.closed = False
    def position(self, name):
        return np.array([.4, -.12 if name == 'red' else .12, .02])
    def validate_tcp(self, xyz):
        if not (.2 <= xyz[0] <= .6 and abs(xyz[1]) <= .3 and .01 <= xyz[2] <= .45):
            raise ValueError('TCP outside supported workspace')
    def move_to(self, xyz):
        self.moves.append(xyz)
    def gripper(self, closed):
        self.closed = closed
    def step(self, seconds):
        self.data.time += seconds


class PolicyLanguageTests(unittest.TestCase):
    def test_blocks_escape_routes_and_handwritten_shortcuts(self):
        examples = ['import os', 'open("file")', 'eval("1")', 'while True: pass',
                    'for i in [1]: robot.step(1)', 'def f(): pass',
                    'robot.stack("red", "blue")', 'robot.reset()', 'robot.is_stacked("red", "blue")',
                    'robot.__dict__', 'x = robot.position', 'robot = 1',
                    'x = ().__class__', 'robot.position.__call__("red")',
                    'robot.position(**{})', 'x = 10 ** 10000000']
        for code in examples:
            with self.subTest(code=code), self.assertRaises(PolicyError):
                validate(code)

    def test_positions_arithmetic_and_real_api_mapping(self):
        robot = FakeRobot()
        runner = Interpreter(robot)
        runner.run('p = robot.position("red")\nz = p[2] + 0.20\nrobot.move_to([p[0], p[1], z])\nrobot.gripper(closed=True)\nrobot.step(0.5)')
        np.testing.assert_allclose(robot.moves, [[.4, -.12, .22]])
        self.assertTrue(robot.closed)
        self.assertEqual(robot.data.time, .5)
        self.assertEqual(runner.actions[0]['result'], [.4, -.12, .02])

    def test_numeric_only_arithmetic_cannot_allocate_large_lists(self):
        for code in ['x = [1] * 1000000', 'x = "a" * 1000000', 'x = 1 / 0',
                     'robot.move_to([True, 0, .2])', 'robot.step(1e309)']:
            with self.subTest(code=code), self.assertRaises(PolicyError):
                Interpreter(FakeRobot()).run(code)

    def test_nested_lists_cannot_expand_action_logs_exponentially(self):
        with self.assertRaises(PolicyError):
            Interpreter(FakeRobot()).run('x = [1]\nx = [x, x, x]')

    def test_runtime_limits_and_unknown_objects(self):
        for code in ['robot.position("missing")', 'robot.step(-1)', 'robot.step(6)',
                     'robot.gripper(closed=1)', 'robot.move_to([9, 0, .2])',
                     'robot.step(5)\nrobot.step(5)\nrobot.step(5)\nrobot.step(1)']:
            with self.subTest(code=code), self.assertRaises(PolicyError):
                Interpreter(FakeRobot()).run(code)
        robot = FakeRobot()
        with self.assertRaises(PolicyError):
            Interpreter(robot).run('robot.move_to([9, 0, .2])')
        self.assertEqual(robot.moves, [])

    def test_api_call_budget(self):
        runner = Interpreter(FakeRobot())
        with self.assertRaises(PolicyError):
            runner.run('\n'.join(['robot.position("red")']*49))
        self.assertEqual(len(runner.actions), 48)

    def test_method_values_and_indexed_writes_are_not_an_escape(self):
        for code in ['x = robot', 'p = robot.position("red")\np[0] = .5',
                     'p = robot.position("red")\nx = p[99]']:
            with self.subTest(code=code), self.assertRaises(PolicyError):
                Interpreter(FakeRobot()).run(code)


class LocalRuntimeTests(unittest.TestCase):
    def test_response_extraction_and_truncation(self):
        raw='runtime banner\n'+json.dumps({'code': 'robot.step(1)\n'})+'\n[end of text]'
        self.assertEqual(llm_runtime.extract_program(raw), 'robot.step(1)\n')
        for text in ['{"code": "unfinished', '{"other": 1}', 'not JSON']:
            with self.assertRaises(ValueError):
                llm_runtime.extract_program(text)

    def test_parameter_limit_uses_total_not_quantized_file_size(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'local_model.lock.json').write_text(json.dumps(dict(total_parameters=8_000_000_000,
                                                                    max_total_parameters=7_000_000_000)))
            with patch.object(llm_runtime, 'ROOT', root), self.assertRaises(ValueError):
                llm_runtime.lock()

    def test_cached_download_is_verified_without_network(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'asset'
            path.write_bytes(b'good')
            digest = hashlib.sha256(b'good').hexdigest()
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network not expected')):
                self.assertEqual(llm_runtime.download('unused', path, digest, 4), path)
                path.write_bytes(b'evil')
                with self.assertRaises(ValueError):
                    llm_runtime.download('unused', path, digest, 4)

    def test_noop_program_fails_independent_physics_evaluation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            code = root/'program.py'
            result = root/'result.json'
            code.write_text('robot.step(0.1)\n')
            process = subprocess.run([sys.executable, str(llm_runtime.ROOT/'llm_worker.py'),
                                      '--config', str(llm_runtime.ROOT/'scenario.json'), '--code', str(code),
                                      '--result', str(result), '--source', 'red', '--target', 'blue'],
                                     capture_output=True, timeout=30)
            report = json.loads(result.read_text())
            self.assertEqual(process.returncode, 1)
            self.assertFalse(report['success'])
            self.assertEqual(report['stage'], 'evaluated')
            self.assertEqual(report['stable_checks'], 0)

    def test_known_control_program_passes_through_the_same_interpreter_and_physics(self):
        # Positive harness control only. This is never a model prompt or output.
        program = '''a = robot.position("red")
b = robot.position("blue")
robot.gripper(closed=False)
robot.move_to([a[0], a[1], 0.24])
robot.move_to(a)
robot.gripper(closed=True)
robot.move_to([a[0], a[1], 0.24])
robot.move_to([b[0], b[1], 0.24])
robot.move_to([b[0], b[1], b[2] + 0.041])
robot.gripper(closed=False)
robot.move_to([b[0], b[1], 0.24])
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            code, result = root/'program.py', root/'result.json'
            code.write_text(program)
            process = subprocess.run([sys.executable, str(llm_runtime.ROOT/'llm_worker.py'),
                                      '--config', str(llm_runtime.ROOT/'scenario.json'), '--code', str(code),
                                      '--result', str(result), '--source', 'red', '--target', 'blue',
                                      '--axes', '--stackviz'], capture_output=True, timeout=45)
            report = json.loads(result.read_text())
            self.assertEqual(process.returncode, 0, report)
            self.assertTrue(report['success'])
            self.assertEqual(report['stable_checks'], 20)
            self.assertTrue(report['tool_clear'])


if __name__ == '__main__':
    unittest.main()
