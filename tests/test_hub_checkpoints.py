"""HF API boundary fixtures; real hashing, ZIPs and restore, no account access."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from stacklab.config import write_json
from stacklab.hub_checkpoints import HubCheckpoints, INDEX


class FakeHub:
    def __init__(self, cache):
        self.cache = Path(cache)
        self.head = '1'*40
        self.history = {self.head:{}}
        self.commits = []
        self.access = True
        self.lose_next_commit_reply = False

    def repo_info(self, **kwargs):
        return SimpleNamespace(sha=self.head, private=True)

    def auth_check(self, **kwargs):
        assert kwargs['write'] and kwargs['repo_type'] == 'dataset'
        if not self.access:
            raise httpx.HTTPStatusError('CONTROLLED SECRET MUST NOT LEAK',
                request=httpx.Request('GET', 'https://fixture.invalid'),
                response=httpx.Response(403, request=httpx.Request('GET', 'https://fixture.invalid')))

    def file_exists(self, filename, revision=None, **kwargs):
        return filename in self.history[revision or self.head]

    def hf_hub_download(self, filename, revision, **kwargs):
        target = self.cache/revision/filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.history[revision][filename])
        return str(target)

    def _commit(self, changes, deleted=()):
        files = copy.deepcopy(self.history[self.head])
        files.update(changes)
        for name in deleted:
            files.pop(name, None)
        self.head = hashlib.sha1((self.head+str(len(self.commits))).encode()).hexdigest()
        self.history[self.head] = files
        self.commits.append((changes, deleted))
        return SimpleNamespace(oid=self.head)

    def upload_file(self, path_in_repo, path_or_fileobj, **kwargs):
        return self._commit({path_in_repo:path_or_fileobj})

    def delete_file(self, path_in_repo, **kwargs):
        return self._commit({}, [path_in_repo])

    def create_commit(self, operations, parent_commit, **kwargs):
        assert parent_commit == self.head
        changes = {op.path_in_repo:(op.path_or_fileobj if isinstance(op.path_or_fileobj, bytes)
                   else Path(op.path_or_fileobj).read_bytes()) for op in operations}
        result = self._commit(changes)
        if self.lose_next_commit_reply:
            self.lose_next_commit_reply = False
            raise httpx.ReadError('CONTROLLED lost acknowledgement after successful commit')
        return result


class HubCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'checkpoint'
        write_json(self.source/'study.json', dict(protocol='CONTROLLED FIXTURE'))
        write_json(self.source/'feasibility.json', dict(complete=True))
        self.api = FakeHub(self.root/'download-cache')
        self.store = HubCheckpoints('fixture/declared-study', api=self.api)

    def test_write_test_uploads_reads_and_removes_only_its_own_small_file(self):
        receipt = self.store.write_test()
        self.assertTrue(receipt['verified'])
        self.assertTrue(receipt['cleaned_up'])
        self.assertLess(receipt['bytes'], 512)
        self.assertEqual(self.api.history[self.api.head], {})
        self.assertEqual(len(self.api.commits), 2)

    def test_read_only_token_fails_before_creating_any_experiment_or_test_file(self):
        self.api.access = False
        with self.assertRaisesRegex(RuntimeError, 'HTTP 403') as error:
            self.store.write_test()
        self.assertNotIn('SECRET', str(error.exception))
        self.assertEqual(self.api.commits, [])

    def test_incremental_backups_are_idempotent_and_never_include_tokens_weights_or_exports(self):
        (self.source/'HF_TOKEN').write_text('must stay local', encoding='utf-8')
        (self.source/'weights.gguf').write_bytes(b'must stay local')
        write_json(self.source/'exports/ignored/study.json', dict(ignored=True))
        first = self.store.push(self.source)
        self.assertEqual(first['uploaded_files'], 2)
        self.assertEqual(self.store.push(self.source)['uploaded_files'], 0)
        self.assertEqual(len(self.api.commits), 1)
        write_json(self.source/'batches/batch-1/starts/episode-a.json', dict(episode='a'))
        self.assertEqual(self.store.push(self.source)['uploaded_files'], 1)
        changed = set(self.api.commits[-1][0])
        self.assertEqual(changed, {self.store.prefix+'/batches/batch-1/starts/episode-a.json', self.store.prefix+'/'+INDEX})
        self.assertFalse(any('HF_TOKEN' in name or '.gguf' in name or '/exports/' in name
                             for name in self.api.history[self.api.head]))

    def test_lost_commit_ack_is_recovered_without_a_second_upload(self):
        self.api.lose_next_commit_reply = True
        with patch('stacklab.hub_checkpoints.time.sleep'):
            self.store.push(self.source)
        self.assertEqual(len(self.api.commits), 1)
        self.store.restore(self.root/'recovered')
        self.assertEqual((self.root/'recovered/study.json').read_bytes(), (self.source/'study.json').read_bytes())

    def test_conflicting_immutable_checkpoint_is_never_overwritten(self):
        self.store.push(self.source)
        write_json(self.source/'study.json', dict(protocol='different'))
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.store.push(self.source)
        self.assertEqual(len(self.api.commits), 1)

    def test_remote_corruption_and_unsafe_paths_are_rejected(self):
        self.store.push(self.source)
        files = self.api.history[self.api.head]
        files[self.store.prefix+'/feasibility.json'] = b'corrupted bytes'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.store.restore(self.root/'corrupt')
        index = json.loads(files[self.store.prefix+'/'+INDEX])
        index['files']['../escape.json'] = dict(bytes=0, sha256='0'*64)
        files[self.store.prefix+'/'+INDEX] = json.dumps(index).encode()
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            self.store.restore(self.root/'unsafe')

    def test_restore_retains_newer_drive_session_evidence_and_rejects_conflicting_roots(self):
        write_json(self.source/'sessions/session.json', dict(stage='remote'))
        self.store.push(self.source)
        recovered = self.root/'recovered'
        write_json(recovered/'sessions/session.json', dict(stage='newer-drive'))
        self.store.restore(recovered)
        values = [json.loads(p.read_text(encoding='utf-8'))['stage'] for p in (recovered/'sessions').glob('*.json')]
        self.assertCountEqual(values, ['remote', 'newer-drive'])
        write_json(recovered/'study.json', dict(protocol='conflict'))
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            self.store.restore(recovered)

    def test_curated_export_is_immutable_and_excludes_extra_local_files(self):
        from stacklab.publication import package_evidence
        evidence = self.root/'evidence'
        for name in ('README.md', 'study.json', 'trials.csv', 'trials.jsonl', 'attempts.jsonl', 'collection-status.json'):
            path = evidence/name
            path.parent.mkdir(exist_ok=True)
            path.write_text('CONTROLLED export fixture', encoding='utf-8')
        snapshot, export = package_evidence(evidence, self.root/'export', dict(schema_version=1),
            public_files=('README.md', 'study.json', 'trials.csv', 'trials.jsonl', 'attempts.jsonl', 'collection-status.json'))
        (export/'HF_TOKEN').write_text('must stay local', encoding='utf-8')
        receipt = self.store.publish_export(export)
        self.assertEqual(receipt['snapshot_id'], snapshot['snapshot_id'])
        self.assertEqual(len(self.api.commits), 1)
        self.store.publish_export(export)
        self.assertEqual(len(self.api.commits), 1)
        self.assertFalse(any('HF_TOKEN' in name for name in self.api.history[self.api.head]))


if __name__ == '__main__':
    unittest.main()
