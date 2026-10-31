"""Sealed legacy selection and real archive/hash handling with a simulated Hub."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import migrate_archives as migration

ROOT = Path(__file__).resolve().parents[1]


def seal(plan):
    plan = {k: v for k, v in plan.items() if k not in ('plan_sha256', 'hub_path')}
    plan['plan_sha256'] = migration.digest(plan)
    plan['hub_path'] = 'legacy/github-'+plan['source_commit'][:12]+'-'+plan['plan_sha256'][:12]
    return plan


class SimulatedHub:
    def __init__(self):
        self.files = {'README.md': b'existing user dataset documentation'}
        self.head = f'{1:040x}'
        self.commits = 0
        self.downloads = []
        self.corrupt = False

    def whoami(self):
        return {'name': 'Carlo0001'}

    def repo_info(self, repo_id, **options):
        assert repo_id == migration.DATASET_REPOSITORY and options['repo_type'] == 'dataset'
        return SimpleNamespace(sha=self.head)

    def file_exists(self, repo_id, filename, **options):
        assert repo_id == migration.DATASET_REPOSITORY and options['revision'] == self.head
        return filename in self.files

    def create_commit(self, repo_id, *, operations, **options):
        assert repo_id == migration.DATASET_REPOSITORY and options['parent_commit'] == self.head
        assert options['repo_type'] == 'dataset'
        for operation in operations:
            assert operation.path_in_repo.startswith('legacy/') or operation.path_in_repo == 'README.md'
            self.files[operation.path_in_repo] = Path(operation.path_or_fileobj).read_bytes()
        self.commits += 1
        self.head = f'{self.commits+1:040x}'
        if self.corrupt:
            name = next(n for n in self.files if n.endswith('/result.json'))
            self.files[name] = b'x'*len(self.files[name])
        return SimpleNamespace(oid=self.head)

    def download(self, repo_id, filename, **options):
        assert repo_id == migration.DATASET_REPOSITORY
        assert options['repo_type'] == 'dataset' and options['force_download'] is True
        assert len(options['revision']) == 40
        self.downloads.append(filename)
        path = Path(options['local_dir'])/filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.files[filename])
        return path


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = {'experiments/archive/fixture/result.json': b'{"fixture": true}\r\n',
                    'experiments/archive/fixture/video.gif': b'controlled binary test fixture'}
        items = []
        for path, data in self.raw.items():
            items.append(dict(path=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                              git_blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()))
        self.plan = seal(dict(schema_version=1, source_repository=migration.GITHUB_REPOSITORY,
            source_commit='a'*40, source_tree='b'*40, selection_roots=list(migration.ROOTS),
            files=items, aliases=[dict(path='examples/experiments/archive/fixture/result.json',
                                      canonical_path='experiments/archive/fixture/result.json')],
            source_file_count=3, canonical_file_count=2,
            source_bytes=sum(map(len,self.raw.values()))+len(self.raw[items[0]['path']]),
            canonical_bytes=sum(map(len,self.raw.values()))))
        self.plan_path = self.root/'plan.json'
        migration.write_json(self.plan_path, self.plan)
        self.hub = SimulatedHub()
        self.addCleanup(patch.stopall)
        patch('huggingface_hub.HfApi', return_value=self.hub).start()
        patch('huggingface_hub.hf_hub_download', side_effect=self.hub.download).start()

    def source_archive(self, *, corrupt=False, missing=False):
        buffer = io.BytesIO()
        files = dict(self.raw)
        files['examples/experiments/archive/fixture/result.json'] = self.raw['experiments/archive/fixture/result.json']
        files['not-selected/.env'] = b'not evidence'
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for name, data in files.items():
                if missing and name.startswith('examples/'):
                    continue
                if corrupt and name.startswith('examples/'):
                    data = b'x'*len(data)
                info = tarfile.TarInfo('source-root/'+name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        buffer.seek(0)
        return buffer

    def prepare(self):
        with patch('urllib.request.urlopen', return_value=self.source_archive()) as download:
            data = migration.prepare_source(self.plan, self.root/'prepared')
        self.assertIn(self.plan['source_commit'], download.call_args.args[0])
        return data

    def test_actual_sealed_selection_preserves_the_inventory_after_git_cleanup(self):
        plan = migration.load_plan(ROOT/'config/evidence-migration.json')
        self.assertEqual(plan['source_file_count'], 491)
        self.assertEqual(plan['canonical_file_count'], 251)
        location = json.loads((ROOT/'experiments/archive-location.json').read_text(encoding='utf-8'))
        self.assertEqual(location['plan_sha256'], plan['plan_sha256'])
        self.assertEqual(location['bytes_verified'], sum(item['bytes'] for item in plan['files']))
        for item in plan['files']:
            self.assertFalse((ROOT/item['path']).exists(), item['path'])
        for alias in plan['aliases']:
            self.assertFalse((ROOT/alias['path']).exists(), alias['path'])

    def test_prepare_checks_duplicate_paths_and_stores_only_canonical_bytes(self):
        data = self.prepare()
        self.assertEqual({p.relative_to(data).as_posix(): p.read_bytes() for p in data.rglob('*') if p.is_file()}, self.raw)
        with patch('urllib.request.urlopen', side_effect=AssertionError('No second download needed')):
            self.assertEqual(migration.prepare_source(self.plan, self.root/'prepared'), data)
        (data/next(iter(self.raw))).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'evidence'):
            migration.prepare_source(self.plan, self.root/'prepared')

    def test_corrupt_or_missing_original_duplicate_is_not_ignored(self):
        for label, options in [('corrupt', {'corrupt': True}), ('missing', {'missing': True})]:
            with patch('urllib.request.urlopen', return_value=self.source_archive(**options)):
                with self.assertRaisesRegex(ValueError, 'checksum|missing'):
                    migration.prepare_source(self.plan, self.root/label)
            self.assertFalse((self.root/label/'prepared.json').exists())

    def test_publish_verifies_downloads_preserves_card_and_is_idempotent(self):
        data = self.prepare()
        receipt = migration.publish(self.plan, data, self.root/'prepared')
        self.assertEqual(receipt['canonical_files_verified'], 2)
        self.assertEqual(receipt['original_paths_preserved'], 3)
        self.assertEqual(self.hub.commits, 2)  # Atomic data commit, then verification proof.
        self.assertEqual(self.hub.files['README.md'], b'existing user dataset documentation')
        self.assertIn(self.plan['hub_path']+'/verification.json', self.hub.files)
        for path, raw in self.raw.items():
            self.assertEqual(self.hub.files[self.plan['hub_path']+'/'+path], raw)
            self.assertEqual((data/path).read_bytes(), raw)
        again = migration.publish(self.plan, data, self.root/'prepared')
        self.assertEqual(again['hub_revision'], receipt['hub_revision'])
        self.assertEqual(self.hub.commits, 2)
        self.assertEqual(sum(n.endswith('/video.gif') for n in self.hub.downloads), 2)

    def test_failed_remote_checksum_never_produces_success_receipt(self):
        data = self.prepare()
        self.hub.corrupt = True
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            migration.publish(self.plan, data, self.root/'prepared')
        self.assertFalse((self.root/'prepared/migration-receipt.json').exists())
        self.assertNotIn(self.plan['hub_path']+'/verification.json', self.hub.files)
        self.assertEqual({path:(data/path).read_bytes() for path in self.raw}, self.raw)

    def test_invalid_selection_or_commit_is_rejected_before_network(self):
        value = json.loads(self.plan_path.read_text())
        value['source_file_count'] += 1
        migration.write_json(self.plan_path, value)
        with self.assertRaisesRegex(ValueError, 'identity check'):
            migration.load_plan(self.plan_path)
        value = dict(self.plan, source_repository='another/repository')
        migration.write_json(self.plan_path, seal(value))
        with self.assertRaisesRegex(ValueError, 'Unexpected source'):
            migration.load_plan(self.plan_path)
        for path in ('../outside', 'experiments/archive/../outside', 'experiments/archive/a\\b', '/experiments/archive/a'):
            with self.assertRaises(ValueError):
                migration.source_path(path)
        with self.assertRaisesRegex(ValueError, 'full Hub commit'):
            migration.verify_remote(self.plan, 'main', self.root/'verify')


if __name__ == '__main__':
    unittest.main()
