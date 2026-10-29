"""CUDA interface controls using explicit fixtures; no claimed GPU inference."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from stacklab.llm import catalog, hardware, source_runtime
from stacklab.llm.runtime import LocalModel


class CudaTests(unittest.TestCase):
    def cuda_config(self, name='granite8b'):
        with patch.object(catalog, 'platform_key', return_value='linux-x86_64'):
            return catalog.lock(name, device='cuda')

    def test_gpu_recipe_preserves_weights_and_cpu_installation(self):
        cpu, cuda = catalog.lock('granite8b'), self.cuda_config()
        self.assertEqual(cpu['model_sha256'], cuda['model_sha256'])
        self.assertEqual(cpu['profiles'], cuda['profiles'])
        self.assertNotEqual(cpu['runtime_version'], cuda['runtime_version'])
        self.assertIn('cuda-12.8', cuda['runtime_assets']['linux-x86_64']['filename'])
        self.assertTrue(cuda['runtime_dependencies']['linux-x86_64'])
        with self.assertRaises(ValueError):
            catalog.lock('granite8b', device='unknown')

    def test_old_colab_glibc_selects_the_same_pinned_source_version(self):
        with patch.object(catalog, 'platform_key', return_value='linux-x86_64'), \
                patch.object(catalog.platform, 'libc_ver', return_value=('glibc','2.35')), \
                patch.dict(catalog.os.environ, STACKLAB_CUDA_RUNTIME='auto'):
            config=catalog.lock('granite8b',device='cuda')
        self.assertEqual(config['cuda_runtime_kind'],'source')
        self.assertIn('-DGGML_CUDA_FA_QUANTS=f16-f16',source_runtime.build_flags(config))
        self.assertEqual(config['runtime_source']['revision'],'a71c00f0bb2d60a4a52837d80baa534b651ebd91')
        self.assertEqual(config['model_sha256'],catalog.lock('granite8b')['model_sha256'])
        with patch.object(catalog, 'platform_key', return_value='linux-x86_64'), \
                patch.object(catalog.platform, 'libc_ver', return_value=('glibc','2.39')), \
                patch.dict(catalog.os.environ, STACKLAB_CUDA_RUNTIME='source'):
            self.assertEqual(catalog.lock('granite8b',device='cuda')['cuda_runtime_kind'],'source')

    def test_dory_build_targets_a100_and_l4_without_changing_cpu_flags(self):
        cuda, cpu = self.cuda_config('dory4b'), catalog.lock('dory4b')
        self.assertEqual(cuda['runtime_source'], cpu['runtime_source'])
        self.assertNotEqual(cuda['runtime_version'], cpu['runtime_version'])
        self.assertIn('-DGGML_CUDA=ON', source_runtime.build_flags(cuda))
        self.assertIn('-DCMAKE_CUDA_ARCHITECTURES=80;89', source_runtime.build_flags(cuda))
        self.assertIn('-DGGML_CUDA_FA=OFF', source_runtime.build_flags(cuda))
        self.assertIn('-DGGML_CUDA=OFF', source_runtime.build_flags(cpu))

    def test_inventory_parses_both_devices_and_the_reported_total_memory(self):
        output='0, NVIDIA L4, GPU-fixture-l4, 23034, 570.86.10\n1, NVIDIA A100-SXM4-40GB, GPU-fixture-a100, 40514, 570.86.10\n'
        with patch.object(hardware.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
            inventory = hardware.gpu_inventory(required=True)
        self.assertEqual(inventory[0]['memory_total_mib'], 23034)
        self.assertEqual(inventory[1]['uuid'], 'GPU-fixture-a100')

    def test_missing_gpu_stops_setup_before_any_download(self):
        with patch.object(hardware.subprocess, 'run', side_effect=FileNotFoundError()), \
                patch.object(catalog, 'download') as download:
            self.assertEqual(hardware.gpu_inventory(), [])
            with self.assertRaisesRegex(ValueError, 'Select a GPU runtime'):
                catalog.setup('granite8b', device='cuda')
            download.assert_not_called()

    def test_cpu_only_backend_is_rejected_even_if_nvidia_smi_succeeded(self):
        for output in ('Available devices:\n CPU: test', 'ggml_cuda_init: no CUDA-capable device'):
            with patch.object(hardware.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                with self.assertRaisesRegex(RuntimeError, 'available CUDA device'):
                    hardware.check_cuda_backend(Path('/fixture/llama-server'), {})
        with patch.object(hardware.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'CUDA0: NVIDIA L4 (23034 MiB)', '')):
            self.assertIn('CUDA0', hardware.check_cuda_backend(Path('/fixture/llama-server'), {}))

    def test_available_gpu_alone_is_not_proof_of_model_offloading(self):
        for output in ('CUDA0: NVIDIA L4', 'load_tensors: offloaded 0/33 layers to GPU'):
            with self.assertRaises(RuntimeError):
                hardware.gpu_offload(output)
        self.assertEqual(hardware.gpu_offload('load_tensors: offloaded 33/33 layers to GPU'),
                         dict(offloaded_layers=33, total_layers=33))

    def test_cuda_archives_install_both_server_and_dependency_and_detect_tampering(self):
        config = self.cuda_config()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def bundle(name, member, content):
                path=root/name
                with tarfile.open(path, 'w:gz') as archive:
                    entry=tarfile.TarInfo(member)
                    entry.size=len(content)
                    archive.addfile(entry, io.BytesIO(content))
                return path
            main=bundle('main.tar.gz', 'llama/bin/llama-server', b'fixture binary')
            dependency=bundle('dep.tar.gz', 'cuda/lib/libcublas.so.12', b'fixture library')
            with patch.object(catalog, 'CACHE_ROOT', root/'cache'), \
                    patch.object(catalog, 'platform_key', return_value='linux-x86_64'), \
                    patch.object(catalog, 'download', side_effect=[main, dependency]) as download:
                executable=catalog.install_cuda_runtime(config)
                self.assertEqual(download.call_count, 2)
                self.assertEqual(catalog.find_executable('granite8b', device='cuda'), executable)
                with patch.object(catalog.platform, 'system', return_value='Linux'):
                    env=catalog.runtime_env(executable)
                self.assertIn(str((root/'cache/runtime'/config['runtime_version']/'cuda/lib').resolve()), env['LD_LIBRARY_PATH'])
                executable.write_bytes(b'changed binary')
                with self.assertRaisesRegex(ValueError, 'missing or changed'):
                    catalog.find_executable('granite8b', device='cuda')

    def test_requested_device_controls_native_command_and_saved_offload_evidence(self):
        class Process:
            def poll(self): return None
            def terminate(self): pass
            def wait(self, timeout): return 0
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for device in ('cpu', 'cuda'):
                path=root/device
                path.mkdir()
                with patch.object(catalog, 'platform_key', return_value='linux-x86_64'):
                    client=LocalModel('granite8b', device=device)
                config=client.config
                weights=root/'models'/config['model_filename']
                weights.parent.mkdir(exist_ok=True)
                weights.touch()
                client.config=dict(config, model_bytes=0)
                def launch(command, **kwargs):
                    if '-lv' in command and command[command.index('-lv')+1] == '5':
                        kwargs['stdout'].write('load_tensors: offloaded 41/41 layers to GPU\n')
                        kwargs['stdout'].flush()
                    return Process()
                response=io.BytesIO(b'{}')
                response.status=200
                with patch('stacklab.llm.runtime.CACHE_ROOT', root), \
                        patch('stacklab.llm.runtime.find_executable', return_value=root/'llama-server'), \
                        patch('stacklab.llm.runtime.runtime_env', return_value={}), \
                        patch('stacklab.llm.runtime.gpu_inventory', return_value=[dict(name='fixture GPU')]), \
                        patch('stacklab.llm.runtime.check_cuda_backend', return_value='CUDA0: fixture GPU'), \
                        patch('stacklab.llm.runtime.subprocess.Popen', side_effect=launch) as started, \
                        patch.object(client.opener, 'open', return_value=response):
                    client.start(path)
                command=started.call_args.args[0]
                self.assertEqual(command[command.index('--gpu-layers')+1], '999' if device=='cuda' else '0')
                self.assertEqual((path/'device.json').exists(), device=='cuda')
                if device == 'cuda':
                    self.assertEqual(json.loads((path/'device.json').read_text())['offloaded_layers'], 41)
                else:
                    self.assertNotIn('-lv', command)
                client.close()

    def test_colab_cuda_wheels_are_found_in_active_and_base_python(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            active = root/'venv/lib/python3.12/site-packages'
            base = root/'base'
            system = base/'lib/python3.13/dist-packages'
            libraries = [active/'nvidia/cuda_runtime/lib', active/'nvidia/cublas/lib',
                         system/'nvidia/cuda_runtime/lib', system/'nvidia/cublas/lib']
            for path in libraries:
                path.mkdir(parents=True)
            with patch.object(catalog.sys, 'path', [str(active)]), \
                    patch.object(catalog.sys, 'base_prefix', str(base)):
                found = catalog._cuda_library_directories()
            for library in libraries:
                self.assertIn(library, found)
            self.assertEqual(len(found), len(set(found)))

    def test_cuda_backend_and_library_paths_are_private_to_the_child_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root/'runtime/bin/llama-server'
            backend = root/'runtime/lib/libggml-cuda.so'
            backend.parent.mkdir(parents=True)
            backend.touch()
            (root/'runtime/installed.json').write_text('{}')
            colab = [root/'usr/lib64-nvidia', root/'site-packages/nvidia/cuda_runtime/lib',
                     root/'site-packages/nvidia/cublas/lib']
            inherited = str(root/'inherited')
            with patch.object(catalog.platform, 'system', return_value='Linux'), \
                    patch.object(catalog, '_cuda_library_directories', return_value=colab), \
                    patch.dict(catalog.os.environ, LD_LIBRARY_PATH=inherited,
                               GGML_BACKEND_PATH='unrelated-backend'):
                env = catalog.runtime_env(exe)
                self.assertEqual(env['GGML_BACKEND_PATH'], str(backend.resolve()))
                paths = env['LD_LIBRARY_PATH'].split(catalog.os.pathsep)
                for path in [exe.parent, backend.parent, *colab, Path(inherited)]:
                    self.assertIn(str(path), paths)
                self.assertLess(paths.index(str(backend.parent)), paths.index(str(colab[-1])))
                self.assertEqual(catalog.os.environ['GGML_BACKEND_PATH'], 'unrelated-backend')
                self.assertEqual(catalog.os.environ['LD_LIBRARY_PATH'], inherited)
                backend.unlink()
                cpu_env = catalog.runtime_env(exe)
                self.assertNotIn('GGML_BACKEND_PATH', cpu_env)
                self.assertNotIn(str(colab[0]), cpu_env['LD_LIBRARY_PATH'].split(catalog.os.pathsep))

    def test_notebook_code_cells_compile_and_contain_no_fake_measurements(self):
        from stacklab.paths import ROOT
        notebook=json.loads((ROOT/'notebooks/colab_gpu.ipynb').read_text(encoding='utf-8'))
        self.assertEqual(notebook['nbformat'], 4)
        for index, cell in enumerate(notebook['cells']):
            if cell['cell_type']=='code':
                compile(''.join(cell['source']), 'cell_'+str(index), 'exec')
                self.assertEqual(cell['outputs'], [])
                self.assertIsNone(cell['execution_count'])


if __name__ == '__main__':
    unittest.main()
