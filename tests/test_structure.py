"""Check the maintained entry points and the Workbench policy boundary."""
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from stacklab import __version__
from stacklab.workbench_policy import ExecutionLimits, PolicyError, WorkbenchPolicy


class StructureTests(unittest.TestCase):
    def test_package_commands_work_outside_the_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            for args, expected in [
                (['workbench', '--help'], '--models'),
                (['prompt2robo', '--help'], 'replay'),
                (['setup', '--help'], '--model'),
                (['console', '--help'], '--config'),
                (['--version'], __version__),
            ]:
                result = subprocess.run([sys.executable, '-m', 'stacklab', *args], cwd=directory,
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)

    def test_workbench_execution_limits_are_configurable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            path.write_text('{"api_calls": 2}', encoding='utf-8')
            limits = ExecutionLimits.load(path)
            calls = []
            robot = SimpleNamespace(data=SimpleNamespace(time=0.), open_gripper=lambda: calls.append('open'))
            code = 'def run(robot):\n    for i in range(3):\n        robot.open_gripper()'
            with self.assertRaisesRegex(PolicyError, 'API call budget reached'):
                WorkbenchPolicy(robot, limits=limits).run(code)
            self.assertEqual(calls, ['open', 'open'])
