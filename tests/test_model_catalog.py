"""Requested model identities, pinned runtimes and cache reuse."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stacklab.llm import catalog, source_runtime


class CatalogTests(unittest.TestCase):
    def test_reference_weights_resolve_from_catalog_alias_and_model_id(self):
        expected = catalog.lock()
        for model in ('qwen4b', 'Qwen/Qwen3.5-4B', 'Qwen3.5-4B'):
            self.assertEqual(catalog.lock(model), expected)
        self.assertEqual(expected['model_key'], 'qwen4b')
        self.assertIn(expected['gguf_revision'], expected['model_url'])
        self.assertEqual(len(expected['model_sha256']), 64)

    def test_existing_download_is_reused_only_with_matching_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fixture.gguf'
            content = b'fixture weights'
            path.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            with patch.object(catalog.urllib.request, 'urlopen', side_effect=AssertionError('No network needed')):
                self.assertEqual(catalog.download('https://example.invalid/weights', path, digest, len(content)), path)
                path.write_bytes(b'a' * len(content))
                with self.assertRaisesRegex(ValueError, 'failed verification'):
                    catalog.download('https://example.invalid/weights', path, digest, len(content))

    def test_verified_source_binary_is_reused_without_a_compiler_or_network(self):
        with patch.object(catalog, 'platform_key', return_value='linux-x86_64'), \
                patch.dict(catalog.os.environ, STACKLAB_CUDA_RUNTIME='source'):
            config = catalog.cuda_runtime()
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
