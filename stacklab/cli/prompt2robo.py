"""Read, replay and export the pinned Prompt2Robo dataset."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import urlopen

from stacklab.config import write_json
from stacklab.paths import CACHE_ROOT, ROOT

LOCK = ROOT / 'config/prompt2robo.lock.json'
SPLITS = ('train', 'eval', 'eval_v2', 'eval_v3', 'eval_v4')
TOOLS = ('tools/scene.py', 'tools/robot.py', 'tools/check.py')
PROMPT = ROOT / 'config/prompts/prompt2robo.md'


def source_files(lock, paths, source=None):
    root = Path(source).resolve() if source else CACHE_ROOT / 'prompt2robo' / lock['revision']
    for name in paths:
        path = root / name
        if not path.exists() and source is None:
            url = f"https://huggingface.co/datasets/{lock['repository']}/resolve/{lock['revision']}/{name}"
            with urlopen(url, timeout=90) as response:
                content = response.read()
            if hashlib.sha256(content).hexdigest() != lock['files'][name]:
                raise ValueError(f'SHA-256 mismatch for {name}')
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
                temporary.write(content)
            Path(temporary.name).replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != lock['files'][name]:
            raise ValueError(f'SHA-256 mismatch for {path}')
    return root


def read_samples(root, names):
    ids = set()
    for name in names:
        with (root / name).open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():
                    continue
                sample = json.loads(line)
                identifier = sample['id']
                if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_+-]*', identifier) or identifier in ids:
                    raise ValueError(f'Invalid or duplicate sample ID {identifier!r}')
                ids.add(identifier)
                if sample['split'] not in SPLITS:
                    raise ValueError(f"Unknown split {sample['split']!r} in {identifier}")
                yield sample


def response_for(sample):
    answer = sample['assistant_answer']
    if sample['expected_behavior'] == 'execute':
        return {'code': answer, 'message': ''}
    if sample['expected_behavior'] == 'refuse':
        return {'code': '', 'message': answer}
    raise ValueError(f"Unsupported expected behavior in {sample['id']}")


def prompt_for(sample, system):
    _, separator, instruction = sample['user_prompt'].partition('\n')
    if not separator or not instruction.strip():
        raise ValueError(f"Missing instruction in {sample['id']}")
    objects = dict(sorted(sample['scene']['objects'].items(), key=lambda item: int(item[0])))
    scene = dict(sample['scene'], objects=objects)
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': json.dumps({'user_prompt': instruction, 'scene': scene}, ensure_ascii=False)},
    ]


def messages_for(sample, system):
    return [*prompt_for(sample, system),
            {'role': 'assistant', 'content': json.dumps(response_for(sample), ensure_ascii=False)}]


def select(samples, split, identifiers, limit):
    if identifiers:
        by_id = {s['id']: s for s in samples if s['split'] == split}
        if len(set(identifiers)) != len(identifiers) or not set(identifiers) <= by_id.keys():
            raise ValueError(f'Use distinct sample IDs from split {split}')
        return [by_id[i] for i in identifiers]
    return [s for s in samples if s['split'] == split][:limit]


def replay_one(root, sample, output, video, gui, timeout):
    # The worker runs only reference programs from the checked snapshot.
    keys = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TMP', 'TEMP', 'TMPDIR', 'DISPLAY',
            'XAUTHORITY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR', 'LD_LIBRARY_PATH',
            'MUJOCO_GL', 'EGL_DEVICE_ID', 'MUJOCO_EGL_DEVICE_ID', 'IMAGEIO_FFMPEG_EXE')
    env = {key: os.environ[key] for key in keys if key in os.environ}
    if video and not gui and sys.platform.startswith('linux'):
        env.setdefault('MUJOCO_GL', 'egl')
    env.update(OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', OMP_NUM_THREADS='1')
    command = [sys.executable, '-I', str(Path(__file__).with_name('_prompt2robo_worker.py')),
               str(root / 'tools'), str(output), sample['id']]
    if video:
        command.append('--video')
    if gui:
        command.append('--gui')
    log = output / f"{sample['id']}.log"
    payload = dict(sample={key: value for key, value in sample.items() if key != 'assistant_answer'},
                   response=response_for(sample))
    with log.open('w', encoding='utf-8') as stream:
        try:
            result = subprocess.run(command, input=json.dumps(payload), text=True, env=env,
                                    cwd=output, timeout=timeout, stdout=stream, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired:
            return {'id': sample['id'], 'passed': False, 'reasons': ['Replay timed out'], 'log': log.name}
    receipt = output / f"{sample['id']}.json"
    if not receipt.is_file():
        return {'id': sample['id'], 'passed': False, 'reasons': [f'Worker exited with {result.returncode}'], 'log': log.name}
    return json.loads(receipt.read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='Show split counts and sample IDs')
    replay = commands.add_parser('replay', help='Run and grade reference programs in their original simulator')
    export = commands.add_parser('export', help='Write one SFT messages JSONL file per dataset split')
    prompt = commands.add_parser('prompt', help='Print the zero-shot messages for one dataset scene')
    for command in (listing, replay, export, prompt):
        command.add_argument('--source', type=Path, help='Use an already downloaded copy of the pinned snapshot')
    prompt.add_argument('--split', choices=SPLITS, default='train')
    prompt.add_argument('--id', required=True)
    for command in (listing, replay):
        command.add_argument('--split', choices=SPLITS, default='train')
        command.add_argument('--id', action='append', help='Select an exact sample ID. May be repeated.')
        command.add_argument('--limit', type=int, default=5)
    for command in (replay, export):
        command.add_argument('--output', type=Path, required=True)
    replay.add_argument('--video', action='store_true')
    replay.add_argument('--gui', action='store_true')
    replay.add_argument('--timeout', type=int, default=180, help='Wall-clock seconds per sample')
    args = parser.parse_args(argv)

    try:
        lock = json.loads(LOCK.read_text(encoding='utf-8'))
        data = [name for name in lock['files'] if name.endswith('.jsonl')]
        files = [*data, *TOOLS] if args.command == 'replay' else data
        root = source_files(lock, files, args.source)
        samples = list(read_samples(root, data))
        if args.command == 'prompt':
            sample, = select(samples, args.split, [args.id], 1)
            print(json.dumps(prompt_for(sample, PROMPT.read_text(encoding='utf-8')), ensure_ascii=False, indent=2))
            return 0
        if args.command in ('list', 'replay'):
            if args.limit < 1:
                raise ValueError('Choose a positive limit')
            selected = select(samples, args.split, args.id, args.limit)
        if args.command == 'list':
            print(json.dumps({'counts': dict(Counter(s['split'] for s in samples)),
                              'samples': [{'id': s['id'], 'request': s['user_prompt'].partition('\n')[2],
                                           'behavior': s['expected_behavior']} for s in selected]},
                             ensure_ascii=False, indent=2))
            return 0

        output = args.output.resolve()
        if args.command == 'replay':
            from importlib.metadata import version
            for name in ('mujoco', 'numpy'):
                if version(name) != lock[name]:
                    raise ValueError(f'Replay requires {name}=={lock[name]}; use requirements-prompt2robo.txt')
            if args.timeout < 1 or not selected:
                raise ValueError('Choose a positive timeout and at least one sample')
        output.mkdir(parents=True, exist_ok=False)
        manifest = {'dataset': lock['repository'], 'revision': lock['revision']}
        if args.command == 'export':
            system = PROMPT.read_text(encoding='utf-8')
            counts = {}
            for split in SPLITS:
                rows = [s for s in samples if s['split'] == split and s['verified'] is True]
                with (output / f'{split}.jsonl').open('w', encoding='utf-8') as stream:
                    for row in rows:
                        stream.write(json.dumps({'id': row['id'], 'messages': messages_for(row, system)},
                                                ensure_ascii=False) + '\n')
                counts[split] = len(rows)
            manifest.update(prompt_sha256=hashlib.sha256(system.encode()).hexdigest(), splits=counts,
                            excluded_unverified=len(samples) - sum(counts.values()))
            write_json(output / 'manifest.json', manifest)
            print(json.dumps(manifest, indent=2))
            return 0

        manifest.update(split=args.split, mode='dataset_reference_replay', mujoco=lock['mujoco'],
                        numpy=lock['numpy'], results=[])
        for sample in selected:
            report = replay_one(root, sample, output, args.video, args.gui, args.timeout)
            manifest['results'].append(report)
            write_json(output / 'manifest.json', manifest)
            print(f"{report['id']} {'PASS' if report['passed'] else 'FAIL'}", flush=True)
        return 0 if all(r['passed'] for r in manifest['results']) else 1
    except (OSError, ValueError, KeyError, ImportError) as error:
        print(f'Prompt2Robo: {error}', file=sys.stderr)
        return 1
