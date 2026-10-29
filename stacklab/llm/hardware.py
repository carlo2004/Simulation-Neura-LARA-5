"""Small NVIDIA inventory and explicit backend checks; no automatic CPU fallback."""
import csv
import io
import re
import subprocess


def gpu_inventory(required=False):
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,uuid,memory.total,driver_version',
                                 '--format=csv,noheader,nounits'], capture_output=True, text=True,
                                timeout=15, check=True)
        devices = [dict(index=int(row[0]), name=row[1].strip(), uuid=row[2].strip(),
                        memory_total_mib=int(row[3]), driver_version=row[4].strip())
                   for row in csv.reader(io.StringIO(result.stdout)) if row]
        if not devices:
            raise ValueError('No NVIDIA devices reported')
        return devices
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
        if required:
            raise ValueError('CUDA requested but no usable NVIDIA GPU was reported by nvidia-smi. '
                             'Select a GPU runtime in Colab, or choose --device cpu.') from error
        return []


def check_cuda_backend(executable, env):
    result = subprocess.run([str(executable), '--list-devices'], env=env, cwd=executable.parent,
                            capture_output=True, text=True, timeout=30)
    output = result.stdout+'\n'+result.stderr
    if result.returncode or not re.search(r'^\s*CUDA\d+:', output, re.MULTILINE):
        raise RuntimeError('CUDA runtime did not report an available CUDA device. '
                           'Check the NVIDIA driver and runtime libraries.\n'+output[-4000:])
    return output


def gpu_offload(log):
    match = re.search(r'offloaded\s+(\d+)/(\d+)\s+layers\s+to\s+GPU', log)
    if not match or int(match[1]) < 1:
        raise RuntimeError('CUDA startup did not confirm GPU layer offloading; see inference.log')
    return dict(offloaded_layers=int(match[1]), total_layers=int(match[2]))
