"""Check exact release exports and command arguments without uploading anything."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from stacklab import experiments as exp
from stacklab.llm.catalog import sha256
from stacklab.publication import publish_experiment


class PublicationTests(unittest.TestCase):
    def test_release_contains_raw_bytes_video_checksums_and_reports_but_no_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(exp, 'source_hashes', return_value={}), \
                    patch.object(exp, 'environment', return_value={}):
                plan = exp.create_plan(root/'run', models=['lfm2.6b'], cases=['move-right'],
                                       scene_seeds=[1], generation_seeds=[2], blocks=[1])
            directory = root/'run'/plan['episodes'][0]['episode_id']
            directory.mkdir()
            raw = b'unchanged\r\nresponse bytes'
            (directory/'simulation.log').write_bytes(raw)
            (directory/'simulation.mp4').write_bytes(b'controlled test video placeholder')
            (root/'run/unrelated.env').write_text('must stay local')
            seen = []
            def gh(command, **kwargs):
                seen.append(command)
                if command[1:3] == ['release', 'view']:
                    return subprocess.CompletedProcess(command, 1)
                if command[1:3] == ['release', 'create']:
                    archive = next(Path(a) for a in command if str(a).endswith('.zip'))
                    with zipfile.ZipFile(archive) as saved:
                        self.assertEqual(saved.read(directory.name+'/simulation.log'), raw)
                        self.assertIn(directory.name+'/simulation.mp4', saved.namelist())
                        self.assertNotIn('unrelated.env', saved.namelist())
                        self.assertIn('checksums.json', saved.namelist())
                        hashes = json.loads(saved.read('checksums.json'))
                        self.assertEqual(hashes[directory.name+'/simulation.log'], sha256(directory/'simulation.log'))
                    checksum = Path(command[command.index(str(archive))+1]).read_text()
                    self.assertTrue(checksum.startswith(sha256(archive)))
                return subprocess.CompletedProcess(command, 0)
            with patch('stacklab.publication.shutil.which', return_value='gh'), \
                    patch('stacklab.publication.subprocess.run', side_effect=gh):
                url = publish_experiment(root/'run', 'owner/repo')
            self.assertIn('/releases/tag/benchmark-', url)
            self.assertEqual(len(seen), 3)
            self.assertTrue((directory/'simulation.log').is_file())

    def test_existing_release_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(exp, 'source_hashes', return_value={}), \
                    patch.object(exp, 'environment', return_value={}):
                exp.create_plan(temp, models=['lfm2.6b'], cases=['move-right'],
                                scene_seeds=[1], generation_seeds=[2], blocks=[1])
            with patch('stacklab.publication.shutil.which', return_value='gh'), \
                    patch('stacklab.publication.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
                with self.assertRaisesRegex(ValueError, 'not be overwritten'):
                    publish_experiment(temp, 'owner/repo')
            self.assertEqual(run.call_count, 2)


if __name__ == '__main__':
    unittest.main()
