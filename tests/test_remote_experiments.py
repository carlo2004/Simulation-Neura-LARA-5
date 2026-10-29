"""Remote benchmark harness: declared replies, real HTTP and local contact physics."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from stacklab import experiments as exp
from stacklab.cli.experiment import main
from stacklab.comparison import compare_experiments, ranking, wilson
from stacklab.llm.catalog import lock, model_keys
from stacklab.llm.remote import RemoteControl, RemoteModel
from stacklab.llm.service import InferenceServer
from test_remote import ControlledModel


class SwitchableFixture(ControlledModel):
    gpu = dict(name='CONTROLLED L4 FIXTURE, NOT REAL INFERENCE', uuid='fixture-l4',
               memory_total_mib=23034, driver_version='fixture-driver')

    def __init__(self, model='lfm2.6b', threads=1, device='cpu'):
        super().__init__()
        self.config = lock(model)
        self.device = device
        self.threads = threads
        self.hardware = dict(gpus=[self.gpu])

    def start(self, output, timeout=180):
        if self.config['model_key'] == 'dory4b':
            raise RuntimeError('CONTROLLED setup failure, not a real model result')
        Path(output).mkdir(parents=True, exist_ok=True)

    def close(self):
        self.cancel()


class RemoteExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = SwitchableFixture()
        self.server = InferenceServer(self.fixture, self.root/'server', port=0, allow_model_switch=True)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs=dict(poll_interval=.02), daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        factory = patch('stacklab.llm.runtime.LocalModel', side_effect=SwitchableFixture)
        factory.start()
        self.addCleanup(factory.stop)
        self.url = 'http://127.0.0.1:'+str(self.server.server_port)
        self.control = RemoteControl(self.url)

    def stop_server(self):
        self.server.client.cancel()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def plan(self, path='run', **overrides):
        options = dict(models=['lfm2.6b'], cases=['move-right'], scene_seeds=[100],
                       generation_seeds=[1000], paired_seeds=True, blocks=[1], max_tokens=1024,
                       server_url=self.url)
        options.update(overrides)
        return exp.create_plan(self.root/path, **options)

    def test_pilot_has_ten_paired_trials_per_model_and_no_local_weight_requirement(self):
        planned = self.plan(models=model_keys(), cases=['move-right', 'red-on-blue-jitter'],
                            scene_seeds=list(range(100, 105)), generation_seeds=list(range(1000, 1005)))
        self.assertEqual(len(planned['episodes']), 70)
        cases = {c['case_id']: c for c in planned['cases']}
        for episode in planned['episodes']:
            self.assertEqual(episode['generation_seed']-cases[episode['case_id']]['scene_seed'], 900)
        self.assertEqual(len({tuple(c['initial_object_positions']['red']) for c in planned['cases']
                              if c['source']}), 5)
        self.assertEqual(exp.verify_environment(planned)['remote']['gpus'][0]['uuid'], 'fixture-l4')

    def test_select_rejects_unknown_model_and_busy_switch_without_interrupting_generation(self):
        with self.assertRaisesRegex(RuntimeError, 'exact model alias'):
            self.control.select('../../some-file')
        self.server.generation_lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, 'busy'):
                self.control.select('granite8b')
            self.assertEqual(self.server.client.config['model_key'], 'lfm2.6b')
        finally:
            self.server.generation_lock.release()

    def test_model_change_invalidates_old_clients_and_recovers_from_failed_load(self):
        old = RemoteModel(self.url)
        selected = self.control.select('granite8b')
        self.assertIsNone(selected['error'])
        self.assertEqual(selected['info']['config']['model_key'], 'granite8b')
        self.assertIs(self.server.client.cache_prompt, False)
        with self.assertRaisesRegex(RuntimeError, 'changed or restarted'):
            old.complete([dict(role='user', content='must not execute')], self.root/'stale')
        failed = self.control.select('dory4b')
        self.assertIn('CONTROLLED setup failure', failed['error'])
        with self.assertRaisesRegex(RuntimeError, 'No model is ready'):
            RemoteModel(self.url)
        self.assertIsNone(self.control.select('lfm2.6b')['error'])
        self.assertEqual(RemoteModel(self.url).model, 'lfm2.6b')

    def test_setup_failure_remains_a_technical_failure_for_every_planned_episode(self):
        self.plan(models=['dory4b', 'lfm2.6b'], generation_seeds=[1000, 1001], paired_seeds=False)
        with redirect_stdout(io.StringIO()):
            report = exp.run_plan(self.root/'run')
        self.assertTrue(report['complete'])
        self.assertEqual(report['groups'][0]['infrastructure_error'], 2)
        self.assertEqual(report['groups'][0]['scored'], 0)
        self.assertEqual(report['groups'][0]['success'], 0)
        self.assertEqual(report['groups'][1]['success'], 2)

    def test_gpu_change_stops_resume_before_running_any_model(self):
        plan = self.plan()
        self.server.info['hardware'] = dict(gpus=[dict(SwitchableFixture.gpu, uuid='changed')])
        with self.assertRaisesRegex(ValueError, 'Remote GPU'):
            exp.verify_environment(plan)

    def test_worker_executes_both_models_in_real_local_physics_and_resume_never_repeats(self):
        self.plan(models=['lfm2.6b', 'granite8b'])
        with redirect_stdout(io.StringIO()):
            report = exp.run_plan(self.root/'run')
        self.assertEqual([r['status'] for r in report['episodes']], ['success', 'success'])
        for row in report['episodes']:
            path = self.root/'run'/row['episode_id']/'episode'
            result = json.loads((path/'result.json').read_text(encoding='utf-8'))
            before, after = result['initial_observation']['tcp_m'], result['final_observation']['tcp_m']
            self.assertAlmostEqual(after[0]-before[0], .05, delta=.001)
            self.assertEqual(result['rounds'][0]['generation']['transport']['server_id'],
                             json.loads((path/'round_01/remote-server.json').read_text(encoding='utf-8'))['server_id'])
            self.assertTrue((path/'round_01/generated.py').is_file())
        self.assertTrue((self.root/'run/ranking.md').is_file())
        before = {p.relative_to(self.root/'run'): p.read_bytes() for p in (self.root/'run').rglob('*.json')
                  if p.name not in ('summary.json', 'ranking.json')}
        with patch.object(self.control.__class__, 'select', side_effect=AssertionError('must not select again')), \
                redirect_stdout(io.StringIO()):
            again = exp.run_plan(self.root/'run')
        self.assertTrue(again['complete'])
        for path, data in before.items():
            self.assertEqual((self.root/'run'/path).read_bytes(), data)

    def test_pilot_cli_counts_complete_model_failures_as_a_completed_benchmark(self):
        with patch('stacklab.cli.experiment.run_plan', return_value=dict(complete=True)) as run, \
                redirect_stdout(io.StringIO()):
            code = main(['pilot', '--server-url', self.url, '--output', str(self.root/'pilot'),
                         '--no-video'])
        self.assertEqual(code, 0)
        self.assertEqual(len(exp.load_plan(self.root/'pilot')['episodes']), 70)
        run.assert_called_once()

    def test_gpu_comparison_requires_identical_cases_profiles_and_budgets(self):
        first = self.plan('l4')
        self.server.info['hardware'] = dict(gpus=[dict(SwitchableFixture.gpu, uuid='fixture-a100',
                                                    name='CONTROLLED A100 FIXTURE')])
        second = self.plan('a100')
        self.assertEqual(first['comparison_sha256'], second['comparison_sha256'])
        rows = compare_experiments([self.root/'l4', self.root/'a100'], self.root/'comparison')
        self.assertEqual(len(rows), 2)
        self.assertTrue((self.root/'comparison/comparison.csv').is_file())
        self.plan('other-budget', blocks=[4])
        with self.assertRaisesRegex(ValueError, 'Suites differ'):
            compare_experiments([self.root/'l4', self.root/'other-budget'], self.root/'wrong')

    def test_ranking_keeps_ties_technical_errors_and_uncertainty_visible(self):
        def row(model, status):
            return dict(model=model, blocks=4, status=status, performance={}, execution_outcomes=[])
        report = dict(episodes=[row('a', 'success'), row('a', 'infrastructure_error'),
                               row('b', 'success'), row('b', 'model_failure')])
        a, b = ranking(report)
        self.assertEqual(a['success_rate_planned'], b['success_rate_planned'])
        self.assertEqual(a['success_rate_scored'], 1.)
        self.assertEqual(b['success_rate_scored'], .5)
        self.assertEqual(a['infrastructure_error'], 1)
        self.assertIsNone(wilson(0, 0))
        self.assertLess(wilson(5, 5)[0], .6)
        report['episodes'].append(row('a', 'pending'))
        self.assertIsNone(next(r for r in ranking(report) if r['model'] == 'a')['success_rate_planned'])

    def test_start_helper_prepares_later_source_builds_even_when_first_model_uses_a_binary(self):
        import importlib.util
        from stacklab.paths import ROOT
        spec = importlib.util.spec_from_file_location('test_remote_helper', ROOT/'tools/start_remote.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        calls = []
        def which(name, **kwargs):
            return None if name == 'cmake' else '/fixture/bin/'+name
        with patch.object(helper, 'ROOT', self.root/'helper'), \
                patch.object(helper, 'run', side_effect=lambda args, env=None: calls.append(list(map(str, args)))), \
                patch.object(helper.subprocess, 'check_output', return_value='{"cuda_runtime_kind":"binary"}'), \
                patch.object(helper.shutil, 'which', side_effect=which):
            result = helper.main(['--benchmark'])
        self.assertEqual(result, 0)
        self.assertTrue(any(call[-3:] == ['pip', 'install', 'cmake'] for call in calls))
        self.assertIn('--allow-model-switch', calls[-1])
        self.assertIn('--install-missing', calls[-1])


if __name__ == '__main__':
    unittest.main()
