"""Study design, immutable checkpoints and real HTTP/physics with declared replies.

Controlled replies here are harness checks, never model-quality measurements.
"""
from contextlib import redirect_stdout
import ast
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from stacklab import experiments as exp, stack_study as study
from stacklab.config import Config, write_json
from stacklab.llm.catalog import lock
from stacklab.llm.runtime import LocalModel
from stacklab.llm.service import InferenceServer


class StudyModel:
    gpu = dict(index=0, name='CONTROLLED A100 FIXTURE, NOT REAL INFERENCE', uuid='fixture-first',
               memory_total_mib=40000, driver_version='fixture-driver')
    scored_calls = 0

    def __init__(self, model='lfm2.6b', threads=2, device='cuda', context_tokens=16384):
        self.config = lock(model, device=device)
        self.config['context_tokens'] = context_tokens
        self.context_tokens, self.threads, self.device = context_tokens, threads, device
        self.hardware = dict(gpus=[self.gpu], offloaded_layers=8, total_layers=8)

    def start(self, output, timeout=180):
        Path(output).mkdir(parents=True, exist_ok=True)

    def complete(self, messages, output, **kwargs):
        if kwargs['max_tokens'] != 64:
            type(self).scored_calls += 1
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        raw = '{"code":"","done":true,"message":"CONTROLLED EMPTY PROGRAM; NOT REAL INFERENCE"}'
        metadata = dict(finish_reason='stop', performance=dict(partial=False, decode_tokens_per_second=1.))
        write_json(output/'request.json', dict(messages=messages))
        write_json(output/'response.json', dict(choices=[dict(message=dict(content=raw))]))
        write_json(output/'generation.json', metadata)
        return raw, metadata

    def cancel(self):
        pass

    def close(self):
        pass


class StudyDesignTests(unittest.TestCase):
    def test_notebook_is_a_pinned_a100_collector_without_motion_probes_or_uploads(self):
        notebook = json.loads((study.ROOT/'notebooks/colab_stack_study_v2.ipynb').read_text(encoding='utf-8'))
        code = []
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                source = ''.join(cell['source'])
                ast.parse(source)
                self.assertEqual(cell['outputs'], [])
                code.append(source)
        text = '\n'.join(code)
        for forbidden in ('move-right', 'move-forward', 'benchmark --case', 'upload_folder', 'HF_TOKEN', '--publish'):
            self.assertNotIn(forbidden, text)
        self.assertIn('"A100"', text)
        self.assertIn('runtime.unassign()', text)
        self.assertIn('snapshot["archive"]["sha256"]', text)

    def test_frozen_design_is_stack_only_paired_diverse_and_excludes_the_special_runtime(self):
        settings, bank = study.spec(), study.load_bank()
        self.assertEqual(settings['models'], ['qwen4b', 'qwen9b', 'ministral8b', 'nemotron8b', 'granite8b', 'lfm2.6b'])
        self.assertNotIn('dory4b', settings['models'])
        self.assertEqual(len(bank['cases']), 32)
        strata = {}
        unique = set()
        seeds = []
        for item in bank['cases']:
            case = item['case']
            self.assertEqual(case['goal'], dict(type='stack', source='red', target='blue'))
            self.assertEqual(case['instruction'], 'Staple den roten Würfel auf den blauen Würfel.')
            self.assertEqual(set(case['initial_object_positions']), {'red', 'blue'})
            self.assertEqual(Config(**case['config']).scene(), case['initial_object_positions'])
            unique.add(json.dumps(case['initial_object_positions'], sort_keys=True))
            seeds += case['generation_seeds']
            strata[case['stratum']] = strata.get(case['stratum'], 0)+1
            self.assertEqual(item['quality'], dict(success=True, stable_checks=20, checks=20, tool_clear=True))
        self.assertEqual(len(unique), 32)
        self.assertEqual(sorted(strata.values()), [4]*8)
        self.assertEqual(len(set(seeds)), 32)
        frozen = dict(settings=settings, cases=[c['case'] for c in bank['cases']], protocol_sha256='fixed')
        trials = study.expected_trials(frozen)
        self.assertEqual(len(trials), 192)
        self.assertEqual(len({r['trial_id'] for r in trials}), 192)
        for model in settings['models']:
            rows = [r for r in trials if r['model'] == model]
            self.assertEqual(len(rows), 32)
            self.assertEqual({(r['layout_id'],r['generation_seed']) for r in rows},
                             {(r['layout_id'],r['generation_seed']) for r in trials if r['model'] == settings['models'][0]})

    def test_model_order_balances_early_and_late_positions(self):
        settings = study.spec()
        orders = [study.model_order(settings, block) for block in range(1,5)]
        for model in settings['models']:
            self.assertEqual(sum(order.index(model)+1 for order in orders), 14)
        self.assertEqual(orders[1], list(reversed(orders[0])))
        self.assertEqual(orders[3], list(reversed(orders[2])))

    def test_context_override_is_explicit_and_does_not_mutate_the_catalog(self):
        before = lock('qwen4b')
        model = LocalModel('qwen4b', context_tokens=16384)
        self.assertEqual(model.config['context_tokens'], 16384)
        self.assertEqual(lock('qwen4b'), before)
        self.assertEqual(model.config['model_sha256'], before['model_sha256'])
        with self.assertRaises(ValueError):
            LocalModel('qwen4b', context_tokens=0)

    def test_sample_from_each_stratum_is_physically_stackable_with_a_free_gripper(self):
        for item in study.load_bank()['cases'][:8]:
            with self.subTest(stratum=item['case']['stratum']):
                quality = study.physics_control(Config(**item['case']['config']))
                self.assertTrue(quality['success'])
                self.assertTrue(quality['evaluation']['stack_checks'][0]['tool_clear'])

    def test_checkpoint_detects_corruption_and_restoration_does_not_overwrite_other_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'source'
            source.mkdir()
            (source/'record.json').write_text('{"original":true}', encoding='utf-8')
            archive = study.checkpoint_zip(source, source.iterdir(), root/'record.zip')
            study.restore_zip(archive, root/'restored')
            self.assertEqual((root/'restored/record.json').read_bytes(), (source/'record.json').read_bytes())
            (root/'restored/record.json').write_text('different', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                study.restore_zip(archive, root/'restored')
            with zipfile.ZipFile(root/'corrupt.zip', 'w') as z:
                z.writestr('_checkpoint.json', json.dumps({'record.json':dict(bytes=3,sha256='wrong')}))
                z.writestr('record.json', 'bad')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                study.restore_zip(root/'corrupt.zip', root/'bad')


class StudyCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        settings = study.spec()
        settings.update(scene_blocks=1, models=['lfm2.6b', 'granite8b'], generation_repetitions=1,
                        max_program_blocks=1, max_tokens=512, thinking_budget=128)
        cases = []
        for item in study.load_bank()['cases'][:2]:
            copied = json.loads(json.dumps(item))
            copied['case']['generation_seeds'] = copied['case']['generation_seeds'][:1]
            cases.append(copied)
        fake_bank = dict(bank_sha256='CONTROLLED TEST BANK', cases=cases,
                         validation_fingerprint=study.physics_fingerprint())
        StudyModel.scored_calls = 0
        self.addCleanup(setattr, StudyModel, 'gpu', StudyModel.gpu)
        self.patches = [patch.object(study, 'spec', return_value=settings),
                        patch.object(study, 'load_bank', return_value=fake_bank),
                        patch.object(study, 'physics_control', return_value=dict(success=True)),
                        patch('stacklab.llm.catalog.platform_key', return_value='linux-x86_64'),
                        patch('stacklab.llm.runtime.LocalModel', side_effect=StudyModel)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.directory = self.root/'collection'
        self.checkpoint = self.root/'drive'
        with redirect_stdout(io.StringIO()):
            self.frozen = study.prepare(self.directory, self.checkpoint)
        self.server = InferenceServer(StudyModel(), self.root/'server', port=0, allow_model_switch=True)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs=dict(poll_interval=.02), daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = 'http://127.0.0.1:'+str(self.server.server_port)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def collect(self, **kwargs):
        with redirect_stdout(io.StringIO()):
            return study.collect(self.directory, self.url, checkpoint_dir=self.checkpoint, max_hours=1, **kwargs)

    def test_stop_resume_on_another_a100_preserves_trials_and_does_not_retry_model_failures(self):
        first = self.collect(max_episodes=1)
        scored = [r for r in first if r['status'] in study.VALID]
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0]['status'], 'model_failure')
        self.assertEqual(StudyModel.scored_calls, 1)
        original = scored[0]['primary_attempt_id']
        StudyModel.gpu = dict(StudyModel.gpu, uuid='fixture-second')
        self.server.info['hardware'] = dict(gpus=[StudyModel.gpu], offloaded_layers=8, total_layers=8)
        rows = self.collect()
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r['status'] == 'model_failure' for r in rows))
        self.assertEqual(StudyModel.scored_calls, 4)
        self.assertIn(original, [r['primary_attempt_id'] for r in rows])
        self.collect()
        self.assertEqual(StudyModel.scored_calls, 4)
        identities = {exp.load_plan(p)['remote']['identity']['gpus'][0]['uuid']
                      for p in (self.directory/'batches').iterdir()}
        self.assertEqual(identities, {'fixture-first', 'fixture-second'})

    def test_context_survives_every_model_switch_and_non_a100_is_rejected(self):
        self.collect(max_episodes=1)
        self.assertEqual(self.server.client.config['context_tokens'], 16384)
        self.server.info['hardware']['gpus'] = [dict(StudyModel.gpu, name='NVIDIA L4')]
        with self.assertRaisesRegex(ValueError, 'A100'):
            self.collect()

    def test_restore_and_hf_ready_export_keep_all_trials_without_network_or_upload(self):
        rows = self.collect(max_episodes=1)
        restored = self.root/'restored'
        with patch('stacklab.publication.HfApi', side_effect=AssertionError('must not use HF credentials')):
            study.restore(restored, self.checkpoint)
            self.assertEqual(study.write_index(restored), rows)
            export = study.export_collection(restored, self.root/'export')
            self.assertIs(export['uploaded'], False)
            snapshot = json.loads((self.root/'export/snapshot.json').read_text(encoding='utf-8'))
            self.assertEqual(snapshot['planned'], 4)
            self.assertFalse(snapshot['complete'])
            self.assertTrue((self.root/'export/trials.csv').is_file())
            with zipfile.ZipFile(self.root/'export/evidence.zip') as z:
                records = [json.loads(line) for line in z.read('trials.jsonl').decode().splitlines()]
                self.assertEqual(len(records), 4)
                self.assertEqual(sum(r['status'] == 'model_failure' for r in records), 1)
                self.assertFalse(any('.gguf' in name or '.env' in name for name in z.namelist()))

    def test_start_marker_keeps_a_hard_interrupted_trial_from_being_silently_repeated(self):
        self.collect(max_episodes=1)
        # Model a VM loss after the persisted start but before any final output ZIP.
        archive = next((self.checkpoint/'batches').glob('*/episode-*.zip'))
        archive.unlink()
        restored = self.root/'hard-stop'
        study.restore(restored, self.checkpoint)
        rows = study.write_index(restored)
        self.assertEqual(sum(r['status'] == 'incomplete' for r in rows), 1)
        with redirect_stdout(io.StringIO()):
            resumed = study.collect(restored, self.url, checkpoint_dir=self.checkpoint, max_hours=1)
        self.assertEqual(StudyModel.scored_calls, 4)  # 1 original + 3 previously unstarted slots.
        self.assertEqual(sum(r['status'] == 'incomplete' for r in resumed), 1)
        self.assertTrue(all(r['attempt_count'] == 1 for r in resumed))


if __name__ == '__main__':
    unittest.main()
