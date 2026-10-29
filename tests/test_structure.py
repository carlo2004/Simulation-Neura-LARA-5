"""Behavior at the package, configuration and historical-data boundaries."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stacklab import __version__
from stacklab.llm import catalog
from stacklab.llm.responses import parse_reply
from stacklab.paths import ROOT
from stacklab.policy import ExecutionLimits, Interpreter, PolicyError


class StructureTests(unittest.TestCase):
    def test_package_commands_work_outside_the_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            for args, expected in [(["models"], "qwen9b"), (["chat", "--help"], "--max-rounds"),
                                   (["console", "--help"], "--config"), (["experiment", "--help"], "plan"),
                                   (["--version"], __version__)]:
                result = subprocess.run([sys.executable, "-m", "stacklab", *args], cwd=temp,
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)

    def test_optional_parameter_budget_is_configuration_not_a_hardcoded_ceiling(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"catalog.json"
            for budget in (None, 20_000_000_000):
                path.write_text(json.dumps(dict(total_parameters=12_000_000_000, max_total_parameters=budget)))
                with patch.object(catalog, "REGISTRY_PATH", path):
                    self.assertEqual(catalog.lock()["total_parameters"], 12_000_000_000)
            path.write_text(json.dumps(dict(total_parameters=12_000_000_000, max_total_parameters=10_000_000_000)))
            with patch.object(catalog, "REGISTRY_PATH", path), self.assertRaises(ValueError):
                catalog.lock()

    def test_execution_budgets_are_overridable_and_stop_at_the_selected_boundary(self):
        class Robot:
            def __init__(self):
                from types import SimpleNamespace
                self.data = SimpleNamespace(time=0.)
            def step(self, seconds):
                self.data.time += seconds

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"policy.json"
            path.write_text(json.dumps(dict(api_calls=2, wait_per_call_s=10, wait_total_s=20)))
            with patch.dict(os.environ, STACKLAB_POLICY_LIMITS=str(path)):
                limits = ExecutionLimits.load()
                robot = Robot()
                runner = Interpreter(robot)
                runner.run("robot.step(8)\nrobot.step(8)")
                self.assertEqual(robot.data.time, 16)
                with self.assertRaises(PolicyError):
                    runner.run("robot.step(1)")
                self.assertEqual(robot.data.time, 16)
            self.assertEqual(limits.api_calls, 2)
            for override in (dict(api_calls=0), dict(wait_total_s=float("nan")), dict(unknown=2)):
                path.write_text(json.dumps(override))
                with self.assertRaises(ValueError):
                    ExecutionLimits.load(path)

    def test_transport_formats_preserve_the_program_without_repair(self):
        code = 'robot.jog("x", 0.05)'
        for raw in (code, "\x60\x60\x60python\n"+code+"\n\x60\x60\x60",
                    json.dumps(dict(code=code))):
            self.assertEqual(parse_reply(raw), dict(code=code, done=True, message=""))
        self.assertFalse(parse_reply(json.dumps(dict(code=code, done=False)))["done"])
        for raw in ("\x60\x60\x60python\n"+code+"\n\x60\x60\x60\n\x60\x60\x60python\n"+code+"\n\x60\x60\x60",
                    "import os", "robot.jog(\"x\", ) broken"):
            with self.assertRaises(ValueError):
                parse_reply(raw)

    def test_archived_evidence_matches_the_original_recorded_checksums(self):
        root = ROOT/"experiments/archive/2026-10-28"
        manifest = json.loads((root/"manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["files"])
        for item in manifest["files"]:
            with self.subTest(path=item["path"]):
                content = (root/item["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), item["sha256"])
