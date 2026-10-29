"""Checkpoint durability, including interrupted experiments and exact raw bytes."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from stacklab.backup import backup_experiment
from stacklab import experiments as exp


class BackupTests(unittest.TestCase):
    def test_checkpoint_preserves_bytes_and_a_failed_update_keeps_the_previous_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'source'
            source.mkdir()
            (source/'manifest.json').write_text('{"fixture":true}')
            raw=b'original\r\nraw\x00bytes'
            (source/'raw.dat').write_bytes(raw)
            (source/'active.tmp').write_text('unfinished')
            target=backup_experiment(source, root/'drive')
            before=target.read_bytes()
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(archive.read('raw.dat'), raw)
                self.assertNotIn('active.tmp', archive.namelist())
            with patch.object(zipfile.ZipFile, 'write', side_effect=OSError('fixture quota error')):
                with self.assertRaises(OSError):
                    backup_experiment(source, root/'drive')
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(list((root/'drive').glob('*.tmp')), [])
            with self.assertRaises(ValueError):
                backup_experiment(source, source/'nested')

    def test_interrupted_episode_is_checkpointed_including_the_open_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(exp, 'source_hashes', return_value={}), \
                    patch.object(exp, 'environment', return_value={}), \
                    patch.object(exp, 'verify_environment', return_value={}), \
                    patch.object(exp, 'run_case', side_effect=KeyboardInterrupt()), redirect_stdout(io.StringIO()):
                plan=exp.create_plan(root/'run', models=['qwen9b'], cases=['move-right'],
                                     scene_seeds=[42], generation_seeds=[42], blocks=[1])
                with self.assertRaises(KeyboardInterrupt):
                    exp.run_plan(root/'run', backup_dir=root/'drive')
            archive=next((root/'drive').glob('*.zip'))
            with zipfile.ZipFile(archive) as saved:
                self.assertIn(plan['episodes'][0]['episode_id']+'/manifest.json', saved.namelist())
                self.assertIn('summary.json', saved.namelist())


if __name__ == '__main__':
    unittest.main()
