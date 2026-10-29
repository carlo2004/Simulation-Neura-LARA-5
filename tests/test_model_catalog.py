"""Requested model identities, pinned runtimes and cache reuse."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stacklab.llm import catalog, source_runtime


class CatalogTests(unittest.TestCase):
    def test_requested_models_resolve_by_alias_exact_id_and_short_name(self):
        requested = dict(qwen9b='Qwen/Qwen3.5-9B', qwen4b='Qwen/Qwen3.5-4B',
                         dory4b='nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16',
                         granite8b='ibm-granite/granite-4.2-8b', **{'lfm2.6b': 'LiquidAI/LFM2.5-2.6B'})
        for alias, identifier in requested.items():
            with self.subTest(model=alias):
                config = catalog.lock(alias)
                self.assertEqual(config['model_id'], identifier)
                self.assertEqual(catalog.lock(identifier)['model_key'], alias)
                self.assertEqual(catalog.lock(identifier.rsplit('/', 1)[-1])['model_key'], alias)
                self.assertEqual(len(config['model_sha256']), 64)
                self.assertEqual(len(config['gguf_revision']), 40)
                self.assertIn(config['gguf_revision'], config['model_url'])
        self.assertEqual(catalog.lock('Nemotron Labs Dory 1.0 (4B)')['model_key'], 'dory4b')

    def test_dory_runtime_does_not_replace_the_existing_runtime(self):
        dory, qwen = catalog.lock('dory4b'), catalog.lock('qwen9b')
        self.assertNotEqual(dory['runtime_version'], qwen['runtime_version'])
        self.assertEqual(len(dory['runtime_source']['revision']), 40)
        self.assertIn('dory.num_loops=int:2', ' '.join(dory['server_args']))
        self.assertNotIn('runtime_source', qwen)

    def test_verified_source_binary_is_reused_without_a_compiler_or_network(self):
        config = catalog.lock('dory4b')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root/'build/bin/llama-server'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'fixture binary')
            marker = dict(source=source_runtime.runtime_identity(config), executable='build/bin/llama-server',
                          executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
            (root/'installed.json').write_text(json.dumps(marker))
            with patch.object(source_runtime, 'cmake_executable', side_effect=AssertionError('No compiler needed')), \
                 patch.object(source_runtime.subprocess, 'run', side_effect=AssertionError('No network/build needed')):
                self.assertEqual(source_runtime.build_runtime(config, root), executable.resolve())
            executable.write_bytes(b'changed')
            self.assertIsNone(source_runtime.ready_runtime(config, root))

    def test_unpinned_source_is_rejected_before_fetching(self):
        config = dict(runtime_source=dict(repository='https://example.invalid/runtime.git', revision='main'))
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError, 'complete Git commit'):
            source_runtime.build_runtime(config, temp)


if __name__ == '__main__':
    unittest.main()
