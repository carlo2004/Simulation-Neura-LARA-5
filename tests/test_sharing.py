"""Team namespaces, readable evidence, contribution PRs and concurrent writers."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import httpx
from huggingface_hub.errors import HfHubHTTPError
from stacklab import experiments
from stacklab.config import write_json
from stacklab.llm.catalog import lock
from stacklab import sharing


class TeamHub:
    def __init__(self, cache):
        self.cache = cache
        self.user = 'Carlo0001'
        self.refs = {'main': '1'*40}
        self.trees = {'1'*40: {'.gitattributes': b'controlled fixture'}}
        self.discussions = {}
        self.calls = []
        self.race = False
        self.serial = 1

    def whoami(self):
        return {'name': self.user}

    def repo_info(self, *, revision='main', **kwargs):
        return SimpleNamespace(sha=self.refs.get(revision, revision))

    def file_exists(self, *, filename, revision, **kwargs):
        return filename in self.trees[revision]

    def download(self, repo, filename, *, revision, **kwargs):
        path = self.cache/revision/filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.trees[revision][filename])
        return path

    def create_commit(self, *, revision, parent_commit, create_pr, operations, **kwargs):
        self.calls.append(dict(revision=revision, parent=parent_commit, create_pr=create_pr))
        if self.race:
            self.race = False
            self.serial += 1
            head = f'{self.serial:040x}'
            self.trees[head] = dict(self.trees[self.refs['main']], other_contributor=b'preserve this')
            self.refs['main'] = head
        if not create_pr and self.refs[revision] != parent_commit:
            raise HfHubHTTPError('Concurrent writer', response=httpx.Response(409,
                                   request=httpx.Request('POST', 'https://huggingface.co/fixture')))
        pr_url = None
        if create_pr:
            number = len(self.discussions)+1
            revision = 'refs/pr/'+str(number)
            pr_url = 'https://huggingface.co/datasets/Carlo0001/neura-lara5-cube-stacking-sim-v1/discussions/'+str(number)
            self.discussions[number] = SimpleNamespace(num=number, status='open', is_pull_request=True,
                                                       title=kwargs['commit_message'], url=pr_url)
        tree = dict(self.trees[parent_commit])
        for operation in operations:
            tree[operation.path_in_repo] = Path(operation.path_or_fileobj).read_bytes()
        self.serial += 1
        head = f'{self.serial:040x}'
        self.trees[head] = tree
        self.refs[revision] = head
        return SimpleNamespace(oid=head, pr_revision=revision if create_pr else None, pr_url=pr_url)

    def get_discussion_details(self, repo, number, **kwargs):
        return self.discussions[number]

    def get_repo_discussions(self, repo, **kwargs):
        return iter(self.discussions.values())

    def change_discussion_status(self, repo, number, status, **kwargs):
        self.discussions[number].status = status

    def list_repo_files(self, repo, *, revision, **kwargs):
        return list(self.trees[revision])


class SharingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hub = TeamHub(self.root/'cache')
        self.addCleanup(patch.stopall)
        patch('stacklab.sharing.HfApi', return_value=self.hub).start()
        patch('stacklab.sharing.hf_hub_download', side_effect=self.hub.download).start()
        self.run = self.make_task(self.root/'run')

    def make_task(self, path):
        path.mkdir(parents=True)
        result = dict(instruction='Nur eine kontrollierte Test-Fixture.', status='model_finished', success=None,
                      goal=None, model=lock('lfm2.6b'), rounds=[dict(round=1, feedback={'error': None})],
                      inference_performance=dict(decode_tokens_per_second=12.5))
        write_json(path/'task.json', result)
        write_json(path/'result.json', result)
        write_json(path/'scene.json', {'fixture': True})
        write_json(path/'round_01/response.json', {'choices':[{'message':{'content':'{"code":"robot.step(0.1)"}'}}]})
        (path/'round_01/generated.py').write_bytes(b'robot.step(0.1)\r\n')
        (path/'unrelated.env').write_text('keep local', encoding='utf-8')
        (path/'round_01/password.txt').write_text('not generated run evidence', encoding='utf-8')
        return path

    def make_experiment(self):
        with patch.object(experiments, 'source_hashes', return_value={}), \
                patch.object(experiments, 'environment', return_value={}):
            experiments.create_plan(self.root/'series', models=['lfm2.6b'], cases=['move-right', 'red-on-blue'],
                                    scene_seeds=[42], generation_seeds=[5], blocks=[1])
        return self.root/'series'

    def tree(self, receipt):
        return self.hub.trees[receipt['revision']]

    def test_offline_preview_does_not_change_sources_and_preserves_ungraded_status(self):
        before = {p.relative_to(self.run).as_posix():p.read_bytes() for p in self.run.rglob('*') if p.is_file()}
        result = sharing.share_run(self.run, title='Ein interessanter Versuch', dry_run=True)
        self.assertEqual(result['kind'], 'playground')
        self.assertNotIn('unrelated.env', result['files'])
        self.assertNotIn('round_01/password.txt', result['files'])
        self.assertEqual(before,{p.relative_to(self.run).as_posix():p.read_bytes() for p in self.run.rglob('*') if p.is_file()})
        self.assertEqual(self.hub.calls, [])
        receipt = sharing.share_run(self.run)
        record = json.loads(self.tree(receipt)[receipt['run_path']+'/run.json'])
        self.assertEqual(record['ungraded'], 1)
        self.assertEqual(record['verified_successes'], 0)

    def test_owner_direct_upload_is_named_readable_and_repeatable(self):
        receipt = sharing.share_run(self.run, title='Greifer prüfen', note='Dieser Fehler ist interessant', tags=['cpu'])
        self.assertTrue(receipt['run_path'].startswith('playground/Carlo0001/'))
        self.assertIsNone(receipt['pr_url'])
        tree = self.tree(receipt)
        prefix = receipt['run_path']+'/snapshots/'+receipt['snapshot_id']
        self.assertIn('unbewertet', tree[prefix+'/README.md'].decode())
        self.assertIn('robot.step', tree[prefix+'/details/00001.md'].decode())
        self.assertIn('12.50', tree[prefix+'/README.md'].decode())
        with zipfile.ZipFile(io.BytesIO(tree[prefix+'/evidence.zip'])) as archive:
            self.assertEqual(archive.read('round_01/generated.py'), b'robot.step(0.1)\r\n')
            self.assertNotIn('sharing.json', archive.namelist())
            self.assertNotIn('share-receipt.json', archive.namelist())
            self.assertNotIn('unrelated.env', archive.namelist())
        again = sharing.share_run(self.run)
        self.assertEqual(again, receipt)
        self.assertEqual(len(self.hub.calls), 1)

    def test_same_named_laptop_runs_never_overwrite_each_other(self):
        second = self.make_task(self.root/'other-laptop/run')
        one, two = sharing.share_run(self.run), sharing.share_run(second)
        self.assertNotEqual(one['run_id'], two['run_id'])
        self.assertNotEqual(one['run_path'], two['run_path'])
        self.assertIn(one['run_path']+'/run.json', self.tree(two))

    def test_owner_card_is_preserved_and_navigation_is_added_only_once(self):
        original = b'# User-authored dataset card\n\nKeep this text.\n'
        self.hub.trees['1'*40]['README.md'] = original
        first = sharing.share_run(self.run)
        card = self.tree(first)['README.md']
        self.assertTrue(card.startswith(original))
        self.assertEqual(card.count(b'<!-- stacklab:team-sharing -->'), 1)
        second = sharing.share_run(self.make_task(self.root/'second-run'))
        self.assertEqual(self.tree(second)['README.md'], card)

    def test_existing_crlf_card_is_preserved_byte_for_byte(self):
        original = b'# Dataset card\r\n\r\nExisting CRLF bytes must stay identical.\r\n'
        self.hub.trees['1'*40]['README.md'] = original
        receipt = sharing.share_run(self.run)
        self.assertTrue(self.tree(receipt)['README.md'].startswith(original))

    def test_teammate_uses_own_account_and_updates_the_same_open_hf_pr(self):
        self.hub.user = 'teammate'
        first = sharing.share_run(self.run)
        self.assertTrue(first['run_path'].startswith('playground/teammate/'))
        self.assertEqual(first['pr_revision'], 'refs/pr/1')
        self.assertNotIn(first['run_path']+'/run.json', self.hub.trees[self.hub.refs['main']])
        write_json(self.run/'result.json', dict(sharing.read_json(self.run/'result.json'), error='new information'))
        second = sharing.share_run(self.run)
        self.assertEqual(first['pr_url'], second['pr_url'])
        self.assertNotEqual(first['snapshot_id'], second['snapshot_id'])
        self.assertFalse(self.hub.calls[-1]['create_pr'])
        self.assertEqual(self.hub.calls[-1]['revision'], 'refs/pr/1')
        old = first['run_path']+'/snapshots/'+first['snapshot_id']+'/snapshot.json'
        self.assertIn(old, self.tree(second))
        self.assertEqual(len(self.hub.discussions), 1)

    def test_closed_hf_pr_is_not_reopened_or_silently_written_to(self):
        self.hub.user = 'teammate'
        first = sharing.share_run(self.run)
        self.hub.discussions[1].status = 'closed'
        second = sharing.share_run(self.run, note='Separate follow-up')
        self.assertNotEqual(first['pr_url'], second['pr_url'])
        self.assertEqual(second['pr_revision'], 'refs/pr/2')

    def test_lost_local_receipt_recovers_existing_contribution_without_another_pr(self):
        self.hub.user = 'teammate'
        first = sharing.share_run(self.run)
        (self.run/'share-receipt.json').unlink()
        second = sharing.share_run(self.run)
        self.assertEqual(first, second)
        self.assertEqual(len(self.hub.discussions), 1)
        self.assertEqual(len(self.hub.calls), 1)

    def test_complete_draft_submission_is_published_and_reused(self):
        self.hub.user = 'teammate'
        first = sharing.share_run(self.run)
        self.hub.discussions[1].status = 'draft'
        (self.run/'share-receipt.json').unlink()
        second = sharing.share_run(self.run)
        self.assertEqual(first, second)
        self.assertEqual(self.hub.discussions[1].status, 'open')
        self.assertEqual(len(self.hub.discussions), 1)

    def test_concurrent_other_writer_is_preserved_and_upload_retries(self):
        self.hub.race = True
        receipt = sharing.share_run(self.run)
        self.assertEqual(len(self.hub.calls), 2)
        self.assertEqual(self.tree(receipt)['other_contributor'], b'preserve this')

    def test_frozen_series_and_pending_episodes_remain_separate_from_playground(self):
        series = self.make_experiment()
        result = sharing.share_run(series)
        self.assertTrue(result['run_path'].startswith('experiments/Carlo0001/'))
        record = json.loads(self.tree(result)[result['run_path']+'/run.json'])
        self.assertEqual(record['planned'], 2)
        self.assertFalse(record['complete'])
        rows = self.tree(result)[record['snapshot_path']+'/episodes.jsonl'].decode().splitlines()
        self.assertEqual([json.loads(r)['status'] for r in rows], ['pending','pending'])
        self.assertTrue(all(json.loads(r)['tokenizer']['tokenizer_class']=='TokenizersBackend' for r in rows))
        with self.assertRaisesRegex(ValueError, 'frozen experiment'):
            sharing.share_run(self.run, kind='experiment')

    def test_chat_session_and_case_probe_are_supported(self):
        chat = self.root/'chat'
        task = self.make_task(chat/'task_001')
        write_json(chat/'session.json', {'tasks':[{'instruction':'fixture'}]})
        result = sharing.share_run(chat)
        self.assertIn('task_001', self.tree(result)[result['run_path']+'/snapshots/'+result['snapshot_id']+'/README.md'].decode())
        probe = self.root/'probe'
        probe.mkdir()
        write_json(probe/'result.json', {'case':'move-right','instruction':'fixture','execution':sharing.read_json(task/'result.json')})
        write_json(probe/'scene.json', {'fixture':True})
        result = sharing.share_run(probe)
        self.assertEqual(result['kind'],'playground')

    def test_one_interesting_episode_from_a_series_preserves_original_identity(self):
        series = self.make_experiment()
        plan = experiments.load_plan(series)
        identity = dict(schema_version=1, **plan['episodes'][0], plan_sha256=plan['plan_sha256'])
        episode = series/identity['episode_id']
        episode.mkdir()
        write_json(episode/'manifest.json', identity)
        write_json(episode/'scene.json', {'fixture':True})
        write_json(episode/'result.json', {'case':'move-right','instruction':'fixture',
                   'execution':sharing.read_json(self.run/'result.json')})
        receipt = sharing.share_run(episode)
        self.assertEqual(receipt['kind'],'playground')
        prefix = receipt['run_path']+'/snapshots/'+receipt['snapshot_id']
        with zipfile.ZipFile(io.BytesIO(self.tree(receipt)[prefix+'/evidence.zip'])) as archive:
            self.assertEqual(json.loads(archive.read('manifest.json')),identity)

    def test_listing_filters_category_user_and_includes_pending_contributions(self):
        owner = sharing.share_run(self.run)
        series = sharing.share_run(self.make_experiment())
        self.hub.user = 'teammate'
        sharing.share_run(self.make_task(self.root/'team-run'))
        self.assertEqual(len(sharing.list_runs()), 2)
        self.assertEqual(len(sharing.list_runs(kind='experiment')), 1)
        self.assertEqual(len(sharing.list_runs(uploader='teammate', pending=True)), 1)
        records = sharing.list_runs(pending=True)
        self.assertEqual(len(records), 3)
        self.assertTrue(any(r['pr_url'] for r in records))

    def test_namespace_or_snapshot_corruption_is_rejected_without_overwrite(self):
        receipt = sharing.share_run(self.run)
        prefix = receipt['run_path']+'/snapshots/'+receipt['snapshot_id']
        self.tree(receipt)[prefix+'/snapshot.json'] = b'{"corrupt":true}'
        with self.assertRaisesRegex(ValueError,'immutable snapshot'):
            sharing.share_run(self.run)
        self.assertEqual(len(self.hub.calls),1)

    def test_kind_is_stable_and_invalid_plan_never_falls_back_to_playground(self):
        sharing.share_run(self.make_experiment())
        with self.assertRaisesRegex(ValueError,'keeps its category'):
            sharing.share_run(self.root/'series',kind='playground')
        write_json(self.run/'manifest.json', {'broken':True})
        with self.assertRaisesRegex(ValueError,'schema'):
            sharing.share_run(self.run)

    def test_symlinked_selected_evidence_is_rejected(self):
        (self.run/'scene.json').unlink()
        try:
            (self.run/'scene.json').symlink_to(self.run/'task.json')
        except OSError:
            self.skipTest('OS does not permit unprivileged symlinks')
        with self.assertRaisesRegex(ValueError,'symbolic links'):
            sharing.share_run(self.run,dry_run=True)

    def test_cli_accepts_simple_folder_form_and_list_pending(self):
        from stacklab.cli.share import main
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([str(self.run),'--title','Ein Versuch','--dry-run']),0)
        self.assertEqual(json.loads(output.getvalue())['kind'],'playground')
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([str(self.run),'--title','Ein Versuch']),0)
        self.assertIn('Ansehen:', output.getvalue())
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['list','--kind','playground','--json']),0)
        self.assertEqual(len(json.loads(output.getvalue())),1)

    def test_experiment_publish_routes_into_the_named_experiment_collection(self):
        from stacklab.cli.experiment import main
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['publish',str(self.make_experiment()),'--title','Vergleich auf Laptop']),0)
        self.assertIn('Bereich: experiment', output.getvalue())
        self.assertIn('experiments/Carlo0001/', output.getvalue())


if __name__ == '__main__':
    unittest.main()
