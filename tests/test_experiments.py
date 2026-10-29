"""Experiment bookkeeping with declared fixtures, never evidence of model quality."""
from contextlib import redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stacklab import experiments as exp
from stacklab.config import write_json


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)/'experiment'
        for name, value in [('source_hashes', {'fixture.py': 'declared-test-source'}),
                            ('environment', {'fixture': 'not a measured machine'}),
                            ('software_provenance', {'git_commit': 'test-fixture'})]:
            mock = patch.object(exp, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def plan(self, **overrides):
        options = dict(models=['lfm2.6b'], cases=['move-right'], scene_seeds=[3],
                       generation_seeds=[109], blocks=[1], max_tokens=1024)
        options.update(overrides)
        return exp.create_plan(self.directory, **options)

    def result(self, episode, *, status='verified_success', success=True, error=None, generation=None,
               performance=None):
        self.identity(episode)
        execution = dict(status=status, success=success, evaluation=dict(success=success), error=error,
                         rounds=[dict(model_declared_done=True, execution_outcome='executed',
                                      generation=generation or {})], inference_performance=performance or {})
        write_json(self.directory/episode['episode_id']/'result.json', dict(execution=execution))

    def identity(self, episode):
        write_json(self.directory/episode['episode_id']/'manifest.json',
                   dict(schema_version=exp.SCHEMA, **episode,
                        plan_sha256=exp.load_plan(self.directory)['plan_sha256']))

    def test_model_independent_cases_and_separate_seed_matrix(self):
        plan = self.plan(models=['lfm2.6b', 'granite8b'], cases=['move-right', 'blue-on-red'],
                         scene_seeds=[3, 4], generation_seeds=[109, 110], blocks=[1, 4])
        self.assertEqual(len(plan['cases']), 4)
        self.assertEqual(len(plan['conditions']), 4)
        self.assertEqual(len(plan['episodes']), 32)
        self.assertEqual(len({e['episode_id'] for e in plan['episodes']}), 32)
        for case in plan['cases']:
            self.assertEqual(case['config']['seed'], case['scene_seed'])
            self.assertEqual(sum(e['case_id'] == case['case_id'] for e in plan['episodes']), 8)
        self.assertEqual(plan['split'], 'development')
        self.assertEqual({e['generation_seed'] for e in plan['episodes']}, {109, 110})
        self.assertTrue(any(c['model_config'].get('response_format') for c in plan['conditions']))

    def test_case_identity_survives_model_order_changes(self):
        first = self.plan(models=['lfm2.6b', 'granite8b'])
        second = exp.create_plan(Path(self.temp.name)/'other', models=['granite8b', 'lfm2.6b'],
                                 cases=['move-right'], scene_seeds=[3], generation_seeds=[109], blocks=[1])
        self.assertEqual(first['cases'], second['cases'])

    def test_rejects_duplicate_trials_and_impossible_conditions_before_writing(self):
        for override in [dict(models=['lfm2.6b', 'LiquidAI/LFM2.5-2.6B']), dict(scene_seeds=[3, 3]),
                         dict(generation_seeds=[42, 42]), dict(blocks=[1, 1]), dict(blocks=[0]),
                         dict(cases=['move-right', 'move-right']), dict(thinking=False),
                         dict(max_tokens=50000), dict(thinking_budget=1024), dict(threads=0),
                         dict(generation_seeds=[2**31-1], blocks=[4])]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.plan(**override)
        self.assertFalse((self.directory/'manifest.json').exists())

    def test_manifest_tampering_is_rejected_and_existing_evidence_preserved(self):
        plan = self.plan()
        original = (self.directory/'manifest.json').read_bytes()
        with self.assertRaises(ValueError):
            self.plan()
        self.assertEqual(original, (self.directory/'manifest.json').read_bytes())
        plan['conditions'][0]['max_tokens'] += 1
        write_json(self.directory/'manifest.json', plan)
        with self.assertRaisesRegex(ValueError, 'modified'):
            exp.write_report(self.directory)

    def test_success_denominators_keep_failed_missing_and_technical_trials_visible(self):
        plan = self.plan(generation_seeds=list(range(8)))
        episodes = plan['episodes']
        self.result(episodes[0])
        self.result(episodes[1], status='budget_exhausted', success=False)
        self.result(episodes[2], status='error', success=False, error='RuntimeError: runtime exited')
        self.result(episodes[3], status='cancelled', success=False)
        (self.directory/episodes[4]['episode_id']).mkdir()  # Interrupted before result.
        self.result(episodes[5], status='error', success=False, error='ValueError: length',
                    generation=dict(finish_reason='length'))
        self.result(episodes[6], status='error', success=False, error='TimeoutError: limit',
                    generation=dict(performance=dict(request_seconds=60)))
        report = exp.write_report(self.directory)
        group = report['groups'][0]
        self.assertEqual((group['success'], group['scored'], group['planned'], group['attempted']), (1, 4, 8, 7))
        self.assertEqual(group['success_rate_scored'], .25)
        self.assertEqual(group['infrastructure_error'], 1)
        self.assertEqual(group['cancelled'], 1)
        self.assertEqual(group['incomplete'], 1)
        self.assertEqual(group['pending'], 1)
        self.assertFalse(report['complete'])
        self.assertTrue(report['episodes'][1]['model_declared_done'])
        self.assertFalse(report['episodes'][1]['goal_success'])
        with (self.directory/'results.csv').open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[-1]['goal_success'], '')

    def test_root_success_flag_and_done_claim_do_not_replace_independent_evaluation(self):
        plan = self.plan()
        episode = plan['episodes'][0]
        self.identity(episode)
        write_json(self.directory/episode['episode_id']/'result.json', dict(success=True))
        row = exp.write_report(self.directory)['episodes'][0]
        self.assertEqual(row['status'], 'infrastructure_error')
        self.assertIsNone(row['goal_success'])
        self.result(episode, success=False)  # Claimed verified_success with failed trusted check.
        row = exp.write_report(self.directory)['episodes'][0]
        self.assertNotEqual(row['status'], 'success')

    def test_transport_timeout_is_not_claimed_as_a_model_or_physics_failure(self):
        plan = self.plan()
        self.result(plan['episodes'][0], status='error', success=False, error='TimeoutError: connection limit',
                    generation=dict(transport_complete=False, performance=dict(request_seconds=60)))
        group = exp.write_report(self.directory)['groups'][0]
        self.assertEqual(group['infrastructure_error'], 1)
        self.assertEqual(group['scored'], 0)

    def test_partial_worker_metrics_survive_a_missing_parent_result(self):
        plan = self.plan()
        episode = plan['episodes'][0]
        self.identity(episode)
        write_json(self.directory/episode['episode_id']/'execution.json',
                   dict(status='cancelled', rounds=[], inference_performance=dict(output_tokens=7, partial=True)))
        row = exp.write_report(self.directory)['episodes'][0]
        self.assertEqual(row['status'], 'incomplete')
        self.assertEqual(row['performance']['output_tokens'], 7)
        self.assertIsNone(row['goal_success'])

    def test_aggregate_rate_uses_matching_decode_counts_and_times(self):
        first = dict(schema_version=2, native_decode_tokens=10, decode_seconds=1,
                     decode_tokens_per_second=10, output_tokens=11, measured_rounds=1, total_rounds=1)
        second = dict(schema_version=2, native_decode_tokens=90, decode_seconds=3,
                      decode_tokens_per_second=30, output_tokens=92, measured_rounds=2, total_rounds=2)
        combined = exp.aggregate_performance([dict(performance=first), dict(performance=second)])
        self.assertEqual(combined['decode_tokens_per_second'], 25)
        self.assertEqual(combined['measured_rounds'], 3)
        self.assertEqual(combined['total_episodes'], 2)
        self.assertEqual(combined['output_tokens'], 103)

    def test_source_or_environment_drift_stops_before_using_a_model(self):
        plan = self.plan()
        with patch.object(exp, 'source_hashes', return_value={'changed': 'bytes'}), \
                self.assertRaisesRegex(ValueError, 'changed'):
            exp.verify_environment(plan)
        with patch.object(exp, 'environment', return_value={'changed': 'machine'}), \
                self.assertRaisesRegex(ValueError, 'changed'):
            exp.verify_environment(plan)

    def test_missing_weights_stops_before_first_attempt(self):
        self.plan()
        with patch.object(exp, 'CACHE_ROOT', Path(self.temp.name)/'empty-cache'), \
                self.assertRaisesRegex(ValueError, 'setup --model lfm2.6b'):
            exp.run_plan(self.directory)
        self.assertFalse(any(p.name.startswith('episode-') for p in self.directory.iterdir()))

    def test_resume_keeps_interrupted_attempt_and_runs_only_pending_episodes(self):
        plan = self.plan(generation_seeds=[109, 110])
        seen = []
        def interrupted(name, args, path, *, case):
            seen.append((args.scene_seed, args.generation_seed, args.feedback_rounds))
            raise KeyboardInterrupt()
        with patch.object(exp, 'verify_environment', return_value={'fixture-runtime': 'hash'}), \
                patch.object(exp, 'run_case', side_effect=interrupted), redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                exp.run_plan(self.directory)
        self.assertEqual(seen, [(3, 109, 0)])
        first_manifest = (self.directory/plan['episodes'][0]['episode_id']/'manifest.json').read_bytes()
        def completed(name, args, path, *, case):
            seen.append((args.scene_seed, args.generation_seed, args.feedback_rounds))
            self.result(plan['episodes'][1])
        with patch.object(exp, 'verify_environment', return_value={'fixture-runtime': 'hash'}), \
                patch.object(exp, 'run_case', side_effect=completed), redirect_stdout(io.StringIO()):
            report = exp.run_plan(self.directory)
        self.assertEqual(seen, [(3, 109, 0), (3, 110, 0)])
        self.assertEqual(first_manifest, (self.directory/plan['episodes'][0]['episode_id']/'manifest.json').read_bytes())
        self.assertEqual([r['status'] for r in report['episodes']], ['incomplete', 'success'])

    def test_runtime_change_is_rejected_before_continuing(self):
        self.plan()
        write_json(self.directory/'runtime-verification.json', {'fixture-runtime': 'old-hash'})
        with patch.object(exp, 'verify_environment', return_value={'fixture-runtime': 'new-hash'}), \
                patch.object(exp, 'run_case') as worker, self.assertRaisesRegex(ValueError, 'Runtime executable changed'):
            exp.run_plan(self.directory)
        worker.assert_not_called()

    def test_result_from_another_episode_is_not_counted(self):
        plan = self.plan(generation_seeds=[109, 110])
        self.result(plan['episodes'][0])
        wrong = self.directory/plan['episodes'][0]['episode_id']/'manifest.json'
        identity = json.loads(wrong.read_text())
        identity['generation_seed'] = 110
        write_json(wrong, identity)
        report = exp.write_report(self.directory)
        self.assertEqual(report['groups'][0]['success'], 0)
        self.assertEqual(report['groups'][0]['infrastructure_error'], 1)

    def test_cuda_plan_keeps_case_identity_and_exports_gpu_provenance(self):
        cpu=self.plan()
        gpu=dict(name='fixture NVIDIA L4',memory_total_mib=23034,driver_version='fixture-driver',uuid='fixture-uuid')
        with patch.object(exp, 'environment', return_value=dict(gpus=[gpu])), \
                patch('stacklab.llm.catalog.platform_key', return_value='linux-x86_64'):
            cuda=exp.create_plan(Path(self.temp.name)/'cuda',models=['lfm2.6b'],cases=['move-right'],
                                 scene_seeds=[3],generation_seeds=[109],blocks=[1],max_tokens=1024,device='cuda')
        self.assertEqual(cpu['cases'],cuda['cases'])
        self.assertNotEqual(cpu['conditions'][0]['condition_id'],cuda['conditions'][0]['condition_id'])
        report=exp.write_report(Path(self.temp.name)/'cuda')
        self.assertEqual(report['episodes'][0]['device'],'cuda')
        self.assertEqual(report['episodes'][0]['gpu_names'],'fixture NVIDIA L4')
        self.assertEqual(report['episodes'][0]['plan_sha256'],cuda['plan_sha256'])


if __name__ == '__main__':
    unittest.main()
