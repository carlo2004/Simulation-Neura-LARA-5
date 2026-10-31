"""Regression tests for observed A100-pilot faults; no model inference."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from stacklab.cli.presentation import Presenter
from stacklab.llm.agent import Agent, resolve_prompt_profile, system_prompt
from stacklab.llm.source_runtime import cuda_build_environment
from stacklab.paths import ROOT
from stacklab.experiments import create_plan
from stacklab.sim.robot import Simulation
from test_llm_feedback import FakeModel


class FollowupTests(unittest.TestCase):
    def test_original_granite_unicode_message_does_not_prevent_movement(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.closing(Simulation(visuals=False)) as robot:
            client = FakeModel([dict(code='robot.jog("x", .05)', done=True,
                                     message='Move the gripper 5\u202fcm to the right')])
            goal = dict(type='move', target_m=(robot.data.site_xpos[robot.sid]+[.05, 0, 0]).tolist())
            buffer = io.BytesIO()
            stream = io.TextIOWrapper(buffer, encoding='cp1252')
            with contextlib.redirect_stdout(stream):
                report = Agent(robot, client, max_rounds=1,
                    on_event=Presenter(compact=True, stats_stream=stream).event).run_task(
                        'right', Path(temp)/'episode', goal)
            stream.flush()
            self.assertIn(b'5\\u202fcm', buffer.getvalue())
            self.assertTrue(report['success'])
            self.assertEqual(len(client.requests), 1)
            self.assertEqual([m['role'] for m in client.requests[0]], ['system', 'user'])
            self.assertEqual(report['prompt_profile'], 'one-shot')
            self.assertEqual(report['mode'], 'one_shot')

    def test_observer_io_failure_is_an_infrastructure_outcome(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.closing(Simulation(visuals=False)) as robot:
            def observer(kind, data):
                if kind == 'program':
                    raise OSError('fixture output is unavailable')
            report = Agent(robot, FakeModel([dict(code='robot.jog("x", .05)', done=True)]),
                           max_rounds=1, on_event=observer).run_task('right', Path(temp)/'episode')
            self.assertEqual(report['status'], 'error')
            self.assertEqual(report['rounds'][0]['execution_outcome'], 'infrastructure_error')
            self.assertEqual(report['rounds'][0]['actions'], [])

    def test_one_shot_prompt_is_short_and_cannot_request_more_blocks(self):
        text = system_prompt(1)
        self.assertLess(len(text), len(system_prompt())*.5)
        self.assertIn('No imports', text)
        self.assertIn('no later correction', text)
        self.assertNotIn('done=false', text)
        self.assertEqual(system_prompt(1, 'legacy'), system_prompt(4))
        with self.assertRaises(ValueError):
            resolve_prompt_profile(4, 'one-shot')

    def test_execution_timeout_remains_a_model_budget_failure(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.closing(Simulation(visuals=False)) as robot:
            goal=dict(type='move', target_m=(robot.data.site_xpos[robot.sid]+[.05, 0, 0]).tolist())
            with patch('stacklab.llm.agent.Interpreter', return_value=Mock(actions=[])) as runner:
                runner.return_value.run.side_effect=TimeoutError('Execution time limit reached')
                report=Agent(robot, FakeModel([dict(code='robot.jog("x", .05)', done=True)]),
                             max_rounds=1).run_task('right', Path(temp)/'episode', goal)
            self.assertEqual(report['status'], 'budget_exhausted')
            self.assertEqual(report['rounds'][0]['execution_outcome'], 'execution_error')

    def test_prompt_profile_changes_the_frozen_comparison_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            options=dict(models=['nemotron8b'], cases=['move-right'], scene_seeds=[100],
                         generation_seeds=[1000], blocks=[1], paired_seeds=True)
            a=create_plan(Path(temp)/'legacy', prompt_profile='legacy', **options)
            b=create_plan(Path(temp)/'one-shot', prompt_profile='one-shot', **options)
            self.assertNotEqual(a['comparison_sha256'], b['comparison_sha256'])
            self.assertNotEqual(a['episodes'][0]['condition_id'], b['episodes'][0]['condition_id'])
            self.assertEqual(a['cases'], b['cases'])

    def test_cuda_home_finds_compiler_without_mutating_the_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            compiler=Path(temp)/'bin'/('nvcc.exe' if __import__('os').name=='nt' else 'nvcc')
            compiler.parent.mkdir();compiler.write_text('fixture');compiler.chmod(0o755)
            original=dict(PATH='', CUDA_HOME=temp)
            env=cuda_build_environment(original)
            self.assertEqual(env['CUDACXX'], str(compiler.resolve()))
            self.assertEqual(original, dict(PATH='', CUDA_HOME=temp))
            self.assertIn(str(compiler.parent.resolve()), env['PATH'])

    def test_missing_nvcc_reports_the_compiler_separately_from_the_driver(self):
        with patch('stacklab.llm.source_runtime.shutil.which', return_value=None), \
                patch.object(Path, 'is_file', return_value=False):
            with self.assertRaisesRegex(ValueError, 'nvcc.*nvidia-smi'):
                cuda_build_environment(dict(PATH=''))


class BootstrapTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('followup_bootstrap', ROOT/'bootstrap.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_colab_ensurepip_failure_repairs_partial_environment(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'venv';calls=[];ready=False
            python=target/('Scripts/python.exe' if module.os.name=='nt' else 'bin/python')
            def run(command, **kwargs):
                nonlocal ready
                calls.append(command)
                if command[1:3]==['-m','venv']:
                    target.mkdir(exist_ok=True);(target/'pyvenv.cfg').touch()
                    python.parent.mkdir(parents=True,exist_ok=True);python.touch()
                    raise subprocess.CalledProcessError(1,command)
                if command[1:3]==['-m','virtualenv']:
                    ready=True
                return subprocess.CompletedProcess(command,0 if ready else 1)
            with patch.object(module.subprocess,'run',side_effect=run), \
                    patch('importlib.util.find_spec',return_value=object()):
                self.assertEqual(module.ensure_environment(target),python)
            self.assertTrue(any(c[1:3]==['-m','virtualenv'] for c in calls))
            self.assertFalse(any('install' in c for c in calls))

    def test_unrelated_directory_is_not_recreated(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);(target/'keep.txt').write_text('keep')
            with patch.object(module.subprocess,'run') as run, self.assertRaises(ValueError):
                module.ensure_environment(target)
            run.assert_not_called()
            self.assertEqual((target/'keep.txt').read_text(),'keep')


class PreparationTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('followup_preparation', ROOT/'tools/prepare_followup.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.recipe=json.loads((ROOT/'experiments/one-shot-followup.json').read_text(encoding='utf-8'))
        self.recipe.update(cases=['red-on-blue-jitter'], scene_seeds=[100], generation_seeds=[1000])

    def recipe_path(self):
        path=self.root/'recipe.json'
        path.write_text(json.dumps(self.recipe), encoding='utf-8')
        return path

    def test_failed_physics_control_never_contacts_the_model_server(self):
        robot=Mock()
        runner=Mock(actions=[])
        with patch('stacklab.sim.robot.Simulation', return_value=robot), \
                patch.object(self.module, 'Interpreter', return_value=runner), \
                patch.object(self.module, 'evaluate', return_value=dict(success=False)), \
                patch.object(self.module, 'create_plan') as plan:
            with self.assertRaisesRegex(ValueError, 'Physics reference failed'):
                self.module.prepare(self.root/'out', recipe=self.recipe_path(),
                                    server_url='http://127.0.0.1:8765')
        plan.assert_not_called()
        robot.close.assert_called_once()
        self.assertTrue((self.root/'out/controls.json').is_file())
        self.assertFalse((self.root/'out/proposal.json').exists())

    def test_success_only_freezes_two_separate_plans_without_running_inference(self):
        with patch('stacklab.sim.robot.Simulation', return_value=Mock()), \
                patch.object(self.module, 'Interpreter', return_value=Mock(actions=[])), \
                patch.object(self.module, 'evaluate', return_value=dict(success=True)), \
                patch.object(self.module, 'source_hashes', return_value={}), \
                patch.object(self.module, 'create_plan', return_value=dict(episodes=[{}])) as plan:
            proposal=self.module.prepare(self.root/'out', recipe=self.recipe_path(),
                                         server_url='http://127.0.0.1:8765')
        self.assertEqual([call.kwargs['prompt_profile'] for call in plan.call_args_list], ['legacy', 'one-shot'])
        self.assertTrue(all(call.kwargs['paired_seeds'] for call in plan.call_args_list))
        self.assertEqual(proposal['status'], 'remote_plans_frozen')
        self.assertFalse(proposal['model_inference_started'])

    def test_duplicate_prompt_profile_is_rejected_before_controls_or_server_access(self):
        self.recipe['prompt_profiles']=['one-shot', 'one-shot']
        with patch('stacklab.sim.robot.Simulation') as simulation, \
                patch.object(self.module, 'create_plan') as plan:
            with self.assertRaisesRegex(ValueError, 'exactly once'):
                self.module.prepare(self.root/'out', recipe=self.recipe_path())
        simulation.assert_not_called();plan.assert_not_called()
        self.assertFalse((self.root/'out').exists())


if __name__ == '__main__':
    unittest.main()
