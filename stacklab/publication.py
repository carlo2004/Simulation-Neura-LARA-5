"""Immutable evidence snapshots on the Hugging Face dataset Hub."""
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download

from stacklab.config import write_json
from stacklab.experiments import digest, load_plan, write_report
from stacklab.llm.catalog import sha256
from stacklab.paths import ROOT

REPORT_FILES = ('manifest.json', 'summary.json', 'results.csv', 'report.md',
                'ranking.json', 'ranking.md', 'episodes.jsonl')
ROOT_FILES = {*REPORT_FILES, 'runtime-verification.json', 'review.html', 'colab-session.json'}
DATA_SUFFIXES = {'.json', '.jsonl', '.csv', '.md', '.txt', '.log', '.py', '.html',
                 '.mp4', '.webm', '.png', '.jpg', '.jpeg'}


def dataset_repository(repository=None):
    if repository is None:
        repository = json.loads((ROOT/'config/huggingface.json').read_text(encoding='utf-8'))['dataset_repository']
    if not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Hugging Face dataset repository must be owner/name')
    return repository


def safe_relative(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or '\\' in name or ':' in name or '..' in path.parts
            or path.as_posix() != name):
        raise ValueError('Unsafe evidence path: '+name)
    return path


def prepare_snapshot(directory, staging):
    """Copy only this plan's evidence; never modify the original run or start a model."""
    directory, staging = Path(directory).resolve(), Path(staging).resolve()
    if staging.is_relative_to(directory):
        raise ValueError('Snapshot staging must be outside the experiment directory')
    plan = load_plan(directory)
    evidence = staging/'evidence'
    evidence.mkdir(parents=True, exist_ok=False)
    roots = {episode['episode_id'] for episode in plan['episodes']} | {'model-setups'}
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory)
        selected = relative.parts[0] in roots or len(relative.parts) == 1 and path.name in ROOT_FILES
        if not selected:
            continue
        if path.is_symlink():
            raise ValueError('Benchmark evidence must not contain symbolic links')
        if not path.is_file() or path.suffix not in DATA_SUFFIXES:
            continue
        safe_relative(relative.as_posix())
        target = evidence/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    # Reports are derived from the copied raw records, including incomplete episodes.
    report = write_report(evidence)
    report.pop('generated_at_utc', None)  # Wall-clock export time is not snapshot identity.
    write_json(evidence/'summary.json', report)
    from stacklab.review import write_review
    write_review(evidence, report=report)
    conditions = {c['condition_id']: c for c in plan['conditions']}
    with (evidence/'episodes.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
        for row in report['episodes']:
            config = conditions[row['condition_id']]['model_config']
            stream.write(json.dumps(dict(row, split=plan['split'], tokenizer=config.get('tokenizer')),
                                    ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n')
    files = {p.relative_to(evidence).as_posix(): dict(sha256=sha256(p), bytes=p.stat().st_size)
             for p in sorted(evidence.rglob('*')) if p.is_file()}
    identity = dict(schema_version=1, plan_sha256=plan['plan_sha256'], files=files)
    snapshot_id = digest(identity)
    upload = staging/'upload'
    upload.mkdir()
    archive = upload/'evidence.zip'
    # Stable archive bytes make repeated publication idempotent, including on Windows.
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            with (evidence/name).open('rb') as source, bundle.open(entry, 'w', force_zip64=True) as target:
                shutil.copyfileobj(source, target)
    snapshot = dict(identity, snapshot_id=snapshot_id, split=plan['split'], complete=report['complete'],
                    planned=report['planned'], archive=dict(filename=archive.name, sha256=sha256(archive),
                                                           bytes=archive.stat().st_size))
    write_json(upload/'snapshot.json', snapshot)
    for name in REPORT_FILES:
        shutil.copyfile(evidence/name, upload/name)
    return snapshot, upload


def publish_experiment(directory, repository=None, *, dry_run=False):
    repository = dataset_repository(repository)
    directory = Path(directory).resolve()
    with tempfile.TemporaryDirectory(prefix='stacklab-hub-') as temp:
        snapshot, upload = prepare_snapshot(directory, temp)
        prefix = 'runs/'+snapshot['snapshot_id']
        if dry_run:
            return json.dumps(dict(repository=repository, repo_type='dataset', path=prefix,
                                   complete=snapshot['complete'], planned=snapshot['planned'],
                                   archive_bytes=snapshot['archive']['bytes'], files=snapshot['files']), indent=2)
        api = HfApi()  # Uses HF_TOKEN or the user's normal local hf auth login.
        head = api.repo_info(repo_id=repository, repo_type='dataset').sha
        marker = prefix+'/snapshot.json'
        if api.file_exists(repo_id=repository, filename=marker, repo_type='dataset', revision=head):
            existing = json.loads(Path(hf_hub_download(repository, marker, repo_type='dataset', revision=head)).read_text(encoding='utf-8'))
            if existing != snapshot:
                raise ValueError('Existing immutable Hub snapshot differs; it will not be overwritten')
            commit = head
        else:
            operations = [CommitOperationAdd(path_in_repo=prefix+'/'+p.name, path_or_fileobj=str(p))
                          for p in sorted(upload.iterdir())]
            if not api.file_exists(repo_id=repository, filename='README.md', repo_type='dataset', revision=head):
                operations.append(CommitOperationAdd(path_in_repo='README.md',
                    path_or_fileobj=str(ROOT/'config/huggingface/README.md')))
            commit = api.create_commit(repo_id=repository, repo_type='dataset', operations=operations,
                parent_commit=head, commit_message='Record StackLab evidence '+snapshot['snapshot_id'][:12]).oid
        url = f'https://huggingface.co/datasets/{repository}/tree/{commit}/{prefix}'
        write_json(directory/'hub-receipt.json', dict(repository=repository, revision=commit,
                    snapshot_id=snapshot['snapshot_id'], plan_sha256=snapshot['plan_sha256'], url=url))
        return url


def fetch_experiment(snapshot_id, revision, output, repository=None):
    """Restore exact evidence at a pinned Hub revision after verifying every byte."""
    repository = dataset_repository(repository)
    if not re.fullmatch(r'[0-9a-f]{64}', snapshot_id) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Use the full snapshot SHA-256 and full Hub commit revision from the upload receipt')
    output = Path(output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Restore output must be a new or empty directory')
    prefix = 'runs/'+snapshot_id
    marker = hf_hub_download(repository, prefix+'/snapshot.json', repo_type='dataset', revision=revision)
    snapshot = json.loads(Path(marker).read_text(encoding='utf-8'))
    identity = {key: snapshot[key] for key in ('schema_version', 'plan_sha256', 'files')}
    if snapshot.get('schema_version') != 1 or snapshot.get('snapshot_id') != snapshot_id or digest(identity) != snapshot_id:
        raise ValueError('Hub snapshot manifest failed its identity check')
    for name in snapshot['files']:
        safe_relative(name)
    archive = Path(hf_hub_download(repository, prefix+'/evidence.zip', repo_type='dataset', revision=revision))
    if archive.stat().st_size != snapshot['archive']['bytes'] or sha256(archive) != snapshot['archive']['sha256']:
        raise ValueError('Hub evidence archive failed size/SHA-256 verification')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stacklab-restore-', dir=output.parent) as temp:
        extracted = Path(temp)/'evidence'
        extracted.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            if len(entries) != len(snapshot['files']) or {i.filename for i in entries} != set(snapshot['files']):
                raise ValueError('Archive entries differ from the snapshot manifest')
            if len({i.filename.casefold() for i in entries}) != len(entries):
                raise ValueError('Evidence paths collide on case-insensitive filesystems')
            for entry in entries:
                safe_relative(entry.filename)
                expected = snapshot['files'][entry.filename]
                if entry.file_size != expected['bytes'] or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Unsafe or incorrectly sized archive entry')
                target = extracted/entry.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, target.open('wb') as stream:
                    shutil.copyfileobj(source, stream)
                if sha256(target) != expected['sha256']:
                    raise ValueError('Extracted evidence failed SHA-256 verification: '+entry.filename)
        if load_plan(extracted)['plan_sha256'] != snapshot['plan_sha256']:
            raise ValueError('Restored experiment plan differs from the snapshot')
        if output.exists():
            output.rmdir()
        extracted.replace(output)
    write_json(output/'hub-receipt.json', dict(repository=repository, revision=revision,
                                             snapshot_id=snapshot_id))
    return output
