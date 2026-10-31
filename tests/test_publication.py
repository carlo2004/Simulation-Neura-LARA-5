"""Hub transport contract, immutable snapshots and verified restore; no real upload."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from stacklab import experiments as exp
from stacklab.config import write_json
from stacklab.llm.catalog import sha256
from stacklab.publication import (dataset_repository, fetch_experiment, prepare_snapshot,
                                  publish_experiment, safe_relative)


class FakeHub:
    """In-memory HTTP boundary; actual ZIP generation and extraction stay real."""
    def __init__(self, cache):
        self.cache = cache
        self.files = {'.gitattributes': b'fixture'}
        self.head = '1'*40
        self.calls = []

    def repo_info(self, **kwargs):
        self.calls.append(('repo_info', kwargs))
        return SimpleNamespace(sha=self.head)

    def file_exists(self, **kwargs):
        self.calls.append(('file_exists', kwargs))
        return kwargs['filename'] in self.files

    def create_commit(self, **kwargs):
        self.calls.append(('create_commit', kwargs))
        assert kwargs['parent_commit'] == self.head
        assert kwargs['repo_type'] == 'dataset'
        for operation in kwargs['operations']:
            self.files[operation.path_in_repo] = Path(operation.path_or_fileobj).read_bytes()
        self.head = '2'*40
        return SimpleNamespace(oid=self.head)

    def download(self, repository, filename, **kwargs):
        self.calls.append(('download', dict(repository=repository, filename=filename, **kwargs)))
        target = self.cache/filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.files[filename])
        return str(target)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root/'run'
        with patch.object(exp, 'source_hashes', return_value={}), patch.object(exp, 'environment', return_value={}):
            self.plan = exp.create_plan(self.run, models=['lfm2.6b'], cases=['move-right'],
                                       scene_seeds=[1], generation_seeds=[2], blocks=[1])
        self.episode = self.run/self.plan['episodes'][0]['episode_id']
        self.episode.mkdir()
        self.raw = b'unchanged\r\nresponse bytes'
        (self.episode/'simulation.log').write_bytes(self.raw)
        (self.episode/'simulation.mp4').write_bytes(b'controlled video fixture; not measured inference')
        (self.run/'unrelated.env').write_text('must stay local', encoding='utf-8')
        (self.episode/'.env').write_text('also not evidence', encoding='utf-8')
        self.hub = FakeHub(self.root/'cache')
        self.addCleanup(patch.stopall)
        patch('stacklab.publication.HfApi', return_value=self.hub).start()
        patch('stacklab.publication.hf_hub_download', side_effect=self.hub.download).start()

    def test_dry_run_is_offline_and_does_not_modify_source(self):
        before = {p.relative_to(self.run).as_posix(): p.read_bytes() for p in self.run.rglob('*') if p.is_file()}
        preview = json.loads(publish_experiment(self.run, dry_run=True))
        self.assertEqual(preview['repository'], dataset_repository())
        self.assertEqual(preview['repo_type'], 'dataset')
        self.assertIn(self.episode.name+'/simulation.mp4', preview['files'])
        self.assertNotIn('unrelated.env', preview['files'])
        self.assertNotIn(self.episode.name+'/.env', preview['files'])
        self.assertFalse(preview['complete'])
        self.assertEqual(self.hub.calls, [])
        self.assertEqual(before, {p.relative_to(self.run).as_posix(): p.read_bytes() for p in self.run.rglob('*') if p.is_file()})

    def test_publish_and_fetch_roundtrip_keeps_raw_bytes_and_pins_revision(self):
        url = publish_experiment(self.run)
        receipt = json.loads((self.run/'hub-receipt.json').read_text(encoding='utf-8'))
        snapshot_id = receipt['snapshot_id']
        self.assertIn('/tree/'+'2'*40+'/runs/'+snapshot_id, url)
        snapshot = json.loads(self.hub.files['runs/'+snapshot_id+'/snapshot.json'])
        self.assertEqual(snapshot['files'][self.episode.name+'/simulation.log']['sha256'], sha256(self.episode/'simulation.log'))
        self.assertIn('README.md', self.hub.files)
        rows = [json.loads(line) for line in self.hub.files['runs/'+snapshot_id+'/episodes.jsonl'].decode().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'incomplete')
        self.assertEqual(rows[0]['split'], 'development')
        self.assertEqual(rows[0]['tokenizer']['tokenizer_class'], 'TokenizersBackend')
        restored = fetch_experiment(snapshot_id, receipt['revision'], self.root/'restored')
        self.assertEqual((restored/self.episode.name/'simulation.log').read_bytes(), self.raw)
        self.assertEqual(exp.load_plan(restored), self.plan)
        self.assertFalse((restored/'unrelated.env').exists())
        for name, args in self.hub.calls:
            if name in ('file_exists', 'download'):
                self.assertEqual(args['revision'], '1'*40 if name == 'file_exists' else '2'*40)
                self.assertEqual(args['repo_type'], 'dataset')

    def test_repeated_publication_is_idempotent_and_never_overwrites_dataset_card(self):
        self.hub.files['README.md'] = b'user-authored dataset documentation'
        first = publish_experiment(self.run)
        receipt = json.loads((self.run/'hub-receipt.json').read_text(encoding='utf-8'))
        # A report rebuild's timestamp must not produce a new snapshot.
        exp.write_report(self.run)
        second = publish_experiment(self.run)
        self.assertEqual(first, second)
        self.assertEqual(sum(name == 'create_commit' for name, _ in self.hub.calls), 1)
        self.assertEqual(self.hub.files['README.md'], b'user-authored dataset documentation')
        marker = 'runs/'+receipt['snapshot_id']+'/snapshot.json'
        saved = json.loads(self.hub.files[marker])
        saved['archive']['sha256'] = '0'*64
        self.hub.files[marker] = json.dumps(saved).encode()
        with self.assertRaisesRegex(ValueError, 'not be overwritten'):
            publish_experiment(self.run)

    def test_changed_evidence_creates_another_snapshot_of_the_same_plan(self):
        publish_experiment(self.run)
        first = json.loads((self.run/'hub-receipt.json').read_text(encoding='utf-8'))
        (self.episode/'simulation.log').write_bytes(b'later evidence')
        publish_experiment(self.run)
        second = json.loads((self.run/'hub-receipt.json').read_text(encoding='utf-8'))
        self.assertNotEqual(first['snapshot_id'], second['snapshot_id'])
        self.assertEqual(first['plan_sha256'], second['plan_sha256'])
        self.assertIn('runs/'+first['snapshot_id']+'/evidence.zip', self.hub.files)

    def test_corrupted_download_is_rejected_before_output_is_created(self):
        publish_experiment(self.run)
        receipt = json.loads((self.run/'hub-receipt.json').read_text(encoding='utf-8'))
        archive = 'runs/'+receipt['snapshot_id']+'/evidence.zip'
        self.hub.files[archive] += b'corruption'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            fetch_experiment(receipt['snapshot_id'], receipt['revision'], self.root/'restored')
        self.assertFalse((self.root/'restored').exists())

    def test_file_corruption_cannot_be_hidden_by_updating_only_the_zip_hash(self):
        publish_experiment(self.run)
        receipt = json.loads((self.run/'hub-receipt.json').read_text(encoding='utf-8'))
        prefix = 'runs/'+receipt['snapshot_id']
        changed = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.hub.files[prefix+'/evidence.zip'])) as old, \
                zipfile.ZipFile(changed, 'w') as new:
            for name in old.namelist():
                data = old.read(name)
                if name == self.episode.name+'/simulation.log':
                    data = b'x'*len(data)
                new.writestr(name, data)
        self.hub.files[prefix+'/evidence.zip'] = changed.getvalue()
        marker = json.loads(self.hub.files[prefix+'/snapshot.json'])
        import hashlib
        marker['archive'].update(bytes=len(changed.getvalue()), sha256=hashlib.sha256(changed.getvalue()).hexdigest())
        self.hub.files[prefix+'/snapshot.json'] = json.dumps(marker).encode()
        with self.assertRaisesRegex(ValueError, 'Extracted evidence'):
            fetch_experiment(receipt['snapshot_id'], receipt['revision'], self.root/'restored')
        self.assertFalse((self.root/'restored').exists())

    def test_invalid_refs_paths_and_symlinked_evidence_are_rejected(self):
        for name in ('../outside', '/absolute', 'a/../../b', 'a\\b', 'C:/file'):
            with self.assertRaises(ValueError):
                safe_relative(name)
        with self.assertRaisesRegex(ValueError, 'full snapshot'):
            fetch_experiment('short', 'main', self.root/'output')
        (self.root/'nonempty').mkdir()
        (self.root/'nonempty/user.txt').write_text('keep', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'empty'):
            fetch_experiment('a'*64, 'b'*40, self.root/'nonempty')
        try:
            (self.episode/'linked.json').symlink_to(self.run/'manifest.json')
        except OSError:
            return  # Creating symlinks may need an OS privilege on Windows.
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            prepare_snapshot(self.run, self.root/'stage')

    def test_cli_defaults_to_hub_and_dry_run_makes_no_network_calls(self):
        from contextlib import redirect_stdout
        from stacklab.cli.experiment import main
        with redirect_stdout(io.StringIO()) as output:
            code = main(['publish', str(self.run), '--dry-run'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['repository'], dataset_repository())
        self.assertEqual(self.hub.calls, [])


if __name__ == '__main__':
    unittest.main()
