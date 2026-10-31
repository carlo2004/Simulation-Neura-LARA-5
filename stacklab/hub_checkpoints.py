"""Incremental, transactional HF backups of the study's existing checkpoints."""
import json
from pathlib import Path
import re
import shutil
import time
from uuid import uuid4

import httpx
from huggingface_hub import CommitOperationAdd, HfApi, get_token, login
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

from stacklab.llm.catalog import sha256
from stacklab.publication import dataset_repository, safe_relative

DEFAULT_PREFIX = 'backups/stack-study-v2-32-hf'
INDEX = 'checkpoint-index.json'


def checkpoint_path(name):
    parts = safe_relative(name).parts
    return (name in ('study.json', 'feasibility.json')
        or len(parts) == 2 and parts[0] == 'sessions' and parts[1].endswith('.json')
        or len(parts) == 3 and parts[0] == 'batches'
           and (parts[2] == 'context.zip' or parts[2].startswith('episode-') and parts[2].endswith('.zip'))
        or len(parts) == 4 and parts[0] == 'batches' and parts[2] == 'starts'
           and parts[3].startswith('episode-') and parts[3].endswith('.json'))


class HubCheckpoints:
    def __init__(self, repository=None, prefix=DEFAULT_PREFIX, *, api=None):
        self.repository = dataset_repository(repository)
        self.prefix = safe_relative(prefix).as_posix()
        self.api = api if api is not None else HfApi()
        self._hashes = {}

    def _retry(self, operation):
        for attempt in range(3):
            try:
                return operation()
            except (httpx.HTTPError, HfHubHTTPError) as error:
                status = getattr(getattr(error, 'response', None), 'status_code', None)
                if status in (408, 409, 412, 429, 500, 502, 503, 504) or status is None:
                    if attempt < 2:
                        time.sleep(attempt+1)
                        continue
                # Neither credentials nor the HTTP request/headers enter an evidence file.
                detail = f'HTTP {status}' if status else type(error).__name__
                raise RuntimeError('HF backup failed ('+detail+'). Local/Drive checkpoints are retained; '
                                   'fix access or connectivity before continuing.') from None

    def _download(self, name, revision):
        return Path(self.api.hf_hub_download(repo_id=self.repository, repo_type='dataset',
                    filename=self.prefix+'/'+name, revision=revision))

    def login(self):
        token = get_token()
        if not token:
            raise ValueError('Provide HF_TOKEN via Colab Secrets/a masked prompt, or run hf auth login locally')
        self._retry(lambda: login(token=token, add_to_git_credential=False, skip_if_logged_in=False))

    def connect(self):
        def operation():
            try:
                info = self.api.repo_info(repo_id=self.repository, repo_type='dataset')
            except RepositoryNotFoundError:
                self.api.create_repo(repo_id=self.repository, repo_type='dataset', private=True, exist_ok=True)
                info = self.api.repo_info(repo_id=self.repository, repo_type='dataset')
            self.api.auth_check(repo_id=self.repository, repo_type='dataset', write=True)
            return dict(repository=self.repository, private=bool(info.private), prefix=self.prefix)
        return self._retry(operation)

    def write_test(self):
        """A real upload/read/delete roundtrip, before downloading/loading models."""
        receipt = self.connect()
        name = '_write-tests/'+uuid4().hex+'.json'
        payload = json.dumps(dict(purpose='StackLab write/read test; no experiment data',
                                  nonce=uuid4().hex), sort_keys=True).encode()
        commit = self._retry(lambda: self.api.upload_file(repo_id=self.repository, repo_type='dataset',
            path_in_repo=self.prefix+'/'+name, path_or_fileobj=payload,
            commit_message='Check StackLab checkpoint write access'))
        try:
            data = self._retry(lambda: self._download(name, commit.oid).read_bytes())
            if data != payload:
                raise ValueError('HF write-test readback differs from the uploaded bytes')
        finally:
            self._retry(lambda: self.api.delete_file(repo_id=self.repository, repo_type='dataset',
                path_in_repo=self.prefix+'/'+name, commit_message='Remove StackLab write-test file'))
        return dict(receipt, kind='hf-write-test', scored_model_data=False, verified=True,
                    cleaned_up=True, revision=commit.oid, bytes=len(payload))

    def _state(self):
        info = self.api.repo_info(repo_id=self.repository, repo_type='dataset')
        if not self.api.file_exists(repo_id=self.repository, repo_type='dataset',
                                   filename=self.prefix+'/'+INDEX, revision=info.sha):
            return info.sha, dict(schema_version=1, kind='stacklab-study-checkpoints', files={})
        value = json.loads(self._download(INDEX, info.sha).read_text(encoding='utf-8'))
        if value.get('schema_version') != 1 or value.get('kind') != 'stacklab-study-checkpoints':
            raise ValueError('Unexpected HF checkpoint index')
        for name, identity in value['files'].items():
            if (not checkpoint_path(name) or type(identity.get('bytes')) is not int or identity['bytes'] < 0
                    or not re.fullmatch(r'[0-9a-f]{64}', identity.get('sha256', ''))):
                raise ValueError('Unsafe HF checkpoint index entry')
        if 'study.json' in value['files'] and 'feasibility.json' not in value['files']:
            raise ValueError('Incomplete HF root checkpoint')
        return info.sha, value

    def _identity(self, path):
        stat = path.stat()
        key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if key not in self._hashes:
            self._hashes[key] = dict(bytes=stat.st_size, sha256=sha256(path))
        return self._hashes[key]

    def push(self, directory):
        """Commit only new/changed checkpoint files, with their index in the same commit."""
        directory = Path(directory)
        files = {}
        for path in sorted(directory.rglob('*')):
            name = path.relative_to(directory).as_posix()
            if not checkpoint_path(name):
                continue
            if path.is_symlink():
                raise ValueError('HF checkpoints cannot contain symbolic links')
            if path.is_file():
                files[name] = (path, self._identity(path))
        if 'study.json' not in files or 'feasibility.json' not in files:
            raise ValueError('Prepare the study root before uploading checkpoints')

        def operation():
            head, index = self._state()
            operations = []
            for name, (path, identity) in files.items():
                previous = index['files'].get(name)
                if previous == identity:
                    continue
                if previous is not None and not name.startswith('sessions/'):
                    raise ValueError('HF already contains different immutable evidence: '+name)
                operations.append(CommitOperationAdd(path_in_repo=self.prefix+'/'+name, path_or_fileobj=str(path)))
                index['files'][name] = identity
            if not operations:
                return dict(repository=self.repository, revision=head, uploaded_files=0)
            count = len(operations)
            operations.append(CommitOperationAdd(path_in_repo=self.prefix+'/'+INDEX,
                path_or_fileobj=json.dumps(index, sort_keys=True, ensure_ascii=False).encode()))
            commit = self.api.create_commit(repo_id=self.repository, repo_type='dataset', operations=operations,
                parent_commit=head, commit_message=f'Back up {count} StackLab checkpoint files')
            print(f'HF backup confirmed: {count} files @ {commit.oid[:12]}', flush=True)
            return dict(repository=self.repository, revision=commit.oid, uploaded_files=count)
        return self._retry(operation)

    def restore(self, directory):
        """Read one pinned commit; verify every downloaded byte before merging into Drive."""
        directory = Path(directory).resolve()
        def operation():
            head, index = self._state()
            restored = 0
            # Restore study.json last: it is the existing root-checkpoint commit marker.
            for name in sorted(index['files'], key=lambda n: (n == 'study.json', n)):
                identity = index['files'][name]
                target = directory/safe_relative(name)
                if target.is_symlink() or not target.resolve().is_relative_to(directory):
                    raise ValueError('Restore target must not be a symbolic link')
                if target.is_file() and self._identity(target) == identity:
                    continue
                if target.exists() and not name.startswith('sessions/'):
                    raise ValueError('HF restore would overwrite different evidence: '+name)
                source = self._download(name, head)
                if source.stat().st_size != identity['bytes'] or sha256(source) != identity['sha256']:
                    raise ValueError('HF checkpoint failed SHA-256 verification: '+name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_file():
                    # A Drive session can be newer than its last HF copy; retain both.
                    alternative = target.with_name(target.stem+'-variant-'+sha256(target)[:12]+'.json')
                    if alternative.exists() and alternative.read_bytes() != target.read_bytes():
                        raise ValueError('Conflicting preserved session variant')
                    shutil.copyfile(target, alternative)
                temporary = target.with_suffix(target.suffix+'.tmp')
                shutil.copyfile(source, temporary)
                temporary.replace(target)
                restored += 1
            return dict(repository=self.repository, revision=head, restored_files=restored,
                        indexed_files=len(index['files']))
        return self._retry(operation)

    def publish_export(self, directory):
        """Publish the existing curated export as one immutable HF commit."""
        directory = Path(directory)
        snapshot = json.loads((directory/'snapshot.json').read_text(encoding='utf-8'))
        snapshot_id = snapshot['snapshot_id']
        if not re.fullmatch(r'[0-9a-f]{64}', snapshot_id):
            raise ValueError('Invalid export snapshot identity')
        archive = directory/'evidence.zip'
        if archive.stat().st_size != snapshot['archive']['bytes'] or sha256(archive) != snapshot['archive']['sha256']:
            raise ValueError('Local export archive failed verification')
        names = ('README.md', 'study.json', 'trials.csv', 'trials.jsonl', 'attempts.jsonl',
                 'collection-status.json', 'snapshot.json', 'evidence.zip')
        prefix = self.prefix+'/exports/'+snapshot_id

        def operation():
            head = self.api.repo_info(repo_id=self.repository, repo_type='dataset').sha
            marker = prefix+'/snapshot.json'
            if self.api.file_exists(repo_id=self.repository, repo_type='dataset', filename=marker, revision=head):
                old = Path(self.api.hf_hub_download(repo_id=self.repository, repo_type='dataset',
                           filename=marker, revision=head)).read_bytes()
                if old != (directory/'snapshot.json').read_bytes():
                    raise ValueError('HF export already contains different immutable evidence')
                revision = head
            else:
                operations = [CommitOperationAdd(path_in_repo=prefix+'/'+name,
                              path_or_fileobj=str(directory/name)) for name in names]
                revision = self.api.create_commit(repo_id=self.repository, repo_type='dataset',
                    parent_commit=head, operations=operations,
                    commit_message='Record StackLab study export '+snapshot_id[:12]).oid
            return dict(repository=self.repository, revision=revision, snapshot_id=snapshot_id,
                        url=f'https://huggingface.co/datasets/{self.repository}/tree/{revision}/{prefix}')
        return self._retry(operation)
