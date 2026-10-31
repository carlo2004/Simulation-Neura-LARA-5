"""Copy the sealed GitHub archive selection to the designated HF dataset.

No robot, model, GPU, repository deletion or git-history rewrite is involved.
Credentials are read by huggingface_hub through its normal local login/HF_TOKEN.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import urllib.request

GITHUB_REPOSITORY = 'carlo2004/Simulation-Neura-LARA-5'
DATASET_REPOSITORY = 'Carlo0001/neura-lara5-cube-stacking-sim-v1'
ROOTS = ('experiments/archive/', 'examples/experiments/archive/')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    temporary.replace(path)


def source_path(name):
    if not isinstance(name, str):
        raise ValueError('Evidence paths must be strings')
    path = PurePosixPath(name)
    if (path.is_absolute() or path.as_posix() != name
            or '\\' in name or ':' in name or '..' in path.parts
            or not any(name.startswith(root) for root in ROOTS)):
        raise ValueError('Path is outside the selected GitHub archives')
    return path


def check_file(path, expected):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected['bytes']:
        raise ValueError('Missing, linked or incorrectly sized evidence: '+expected['path'])
    sha = hashlib.sha256()
    git = hashlib.sha1(b'blob '+str(expected['bytes']).encode()+b'\0')
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            sha.update(block)
            git.update(block)
    if sha.hexdigest() != expected['sha256'] or git.hexdigest() != expected['git_blob']:
        raise ValueError('Evidence checksum mismatch: '+expected['path'])


def load_plan(path):
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    body = {k: v for k, v in plan.items() if k not in ('plan_sha256', 'hub_path')}
    if plan.get('schema_version') != 1 or digest(body) != plan.get('plan_sha256'):
        raise ValueError('Migration plan failed its identity check')
    if (plan['source_repository'] != GITHUB_REPOSITORY or tuple(plan['selection_roots']) != ROOTS
            or not re.fullmatch('[0-9a-f]{40}', plan['source_commit'])
            or not re.fullmatch('[0-9a-f]{40}', plan['source_tree'])):
        raise ValueError('Unexpected source repository, revision or selection')
    prefix = 'legacy/github-'+plan['source_commit'][:12]+'-'+plan['plan_sha256'][:12]
    if plan['hub_path'] != prefix:
        raise ValueError('Migration destination differs from the sealed selection')
    files = {}
    for item in plan['files']:
        source_path(item['path'])
        if (item['path'] in files or type(item['bytes']) is not int or item['bytes'] < 0
                or not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                or not re.fullmatch('[0-9a-f]{40}', item['git_blob'])):
            raise ValueError('Invalid or duplicate canonical file in migration plan')
        files[item['path']] = item
    paths = set(files)
    for alias in plan['aliases']:
        source_path(alias['path'])
        if alias['path'] in paths or alias['canonical_path'] not in files:
            raise ValueError('Invalid duplicate-path mapping in migration plan')
        paths.add(alias['path'])
    canonical_bytes = sum(f['bytes'] for f in files.values())
    source_bytes = canonical_bytes+sum(files[a['canonical_path']]['bytes'] for a in plan['aliases'])
    if (len(paths) != plan['source_file_count'] or len(files) != plan['canonical_file_count']
            or canonical_bytes != plan['canonical_bytes'] or source_bytes != plan['source_bytes']):
        raise ValueError('Migration counts or sizes differ from the sealed selection')
    return plan


def prepare_source(plan, output):
    """Download the pinned source; check all original paths, storing duplicates once."""
    output = Path(output).resolve()
    files = {f['path']: f for f in plan['files']}
    expected = {name: item for name, item in files.items()}
    expected.update({a['path']: files[a['canonical_path']] for a in plan['aliases']})
    prepared = output/'prepared.json'
    data = output/'data'
    if prepared.is_file():
        if json.loads(prepared.read_text(encoding='utf-8'))['plan_sha256'] != plan['plan_sha256']:
            raise ValueError('Output contains another migration; choose a new directory')
        for item in files.values():
            check_file(data/item['path'], item)
        return data
    if output.exists() and any(output.iterdir()):
        raise ValueError('Preparation output must be new or empty; keep failed attempts for inspection')
    data.mkdir(parents=True, exist_ok=True)
    url = f'https://codeload.github.com/{GITHUB_REPOSITORY}/tar.gz/{plan["source_commit"]}'
    seen = set()
    with urllib.request.urlopen(url, timeout=60) as response, tarfile.open(fileobj=response, mode='r|gz') as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            name = '/'.join(parts[1:])
            if name not in expected:
                continue
            source_path(name)
            item = expected[name]
            if name in seen or not member.isfile() or member.size != item['bytes']:
                raise ValueError('Source archive entry differs from the migration plan: '+name)
            seen.add(name)
            sha = hashlib.sha256()
            git = hashlib.sha1(b'blob '+str(member.size).encode()+b'\0')
            target = data/name if name in files else None
            if target:
                target.parent.mkdir(parents=True, exist_ok=True)
            stream = target.open('wb') if target else None
            try:
                with archive.extractfile(member) as source:
                    for block in iter(lambda: source.read(1024*1024), b''):
                        sha.update(block)
                        git.update(block)
                        if stream:
                            stream.write(block)
            finally:
                if stream:
                    stream.close()
            if sha.hexdigest() != item['sha256'] or git.hexdigest() != item['git_blob']:
                raise ValueError('Pinned GitHub source failed checksum verification: '+name)
    if seen != set(expected):
        raise ValueError('Pinned GitHub archive is missing selected evidence')
    write_json(prepared, dict(plan_sha256=plan['plan_sha256'], verified_source_paths=len(seen)))
    return data


def verify_remote(plan, revision, output, token=None):
    """Read every canonical Hub file at the exact commit, forcing a fresh download."""
    from huggingface_hub import hf_hub_download
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Verification requires a full Hub commit SHA')
    output = Path(output)
    marker = hf_hub_download(DATASET_REPOSITORY, plan['hub_path']+'/migration.json',
        repo_type='dataset', revision=revision, token=token, local_dir=output, force_download=True)
    if json.loads(Path(marker).read_text(encoding='utf-8')) != plan:
        raise ValueError('Remote migration manifest differs from the approved selection')

    def verify(item):
        path = hf_hub_download(DATASET_REPOSITORY, plan['hub_path']+'/'+item['path'],
            repo_type='dataset', revision=revision, token=token, local_dir=output, force_download=True)
        check_file(path, item)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for count, _ in enumerate(pool.map(verify, plan['files']), 1):
            if count % 25 == 0 or count == plan['canonical_file_count']:
                print(f'Hub checksums verified: {count}/{plan["canonical_file_count"]}', flush=True)
    return dict(schema_version=1, dataset_repository=DATASET_REPOSITORY, data_revision=revision,
                source_repository=GITHUB_REPOSITORY, source_commit=plan['source_commit'],
                plan_sha256=plan['plan_sha256'], hub_path=plan['hub_path'],
                canonical_files_verified=plan['canonical_file_count'],
                original_paths_preserved=plan['source_file_count'], bytes_verified=plan['canonical_bytes'])


def publish(plan, data, output, card=None, token=None):
    from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
    data, output = Path(data), Path(output)
    for item in plan['files']:
        check_file(data/item['path'], item)
    api = HfApi(token=token)
    if api.whoami()['name'] != 'Carlo0001':
        raise ValueError('Sign in as Carlo0001 for this dataset migration')
    head = api.repo_info(DATASET_REPOSITORY, repo_type='dataset').sha
    marker = plan['hub_path']+'/migration.json'
    if api.file_exists(DATASET_REPOSITORY, marker, repo_type='dataset', revision=head):
        path = hf_hub_download(DATASET_REPOSITORY, marker, repo_type='dataset', revision=head,
                               token=token, local_dir=output/'existing', force_download=True)
        if json.loads(Path(path).read_text(encoding='utf-8')) != plan:
            raise ValueError('Existing migration differs and will not be overwritten')
    else:
        manifest = output/'migration.json'
        write_json(manifest, plan)
        operations = [CommitOperationAdd(path_in_repo=plan['hub_path']+'/'+item['path'],
                         path_or_fileobj=str(data/item['path'])) for item in plan['files']]
        operations.append(CommitOperationAdd(path_in_repo=marker, path_or_fileobj=str(manifest)))
        if not api.file_exists(DATASET_REPOSITORY, 'README.md', repo_type='dataset', revision=head):
            base = Path(card).read_text(encoding='utf-8') if card else '# Neura LARA 5 — archived simulation records\n'
            text = base+f'\n## Historical GitHub archive migration\n\nSource: `{GITHUB_REPOSITORY}@{plan["source_commit"]}`. '
            text += f'{plan["source_file_count"]} original paths are preserved as {plan["canonical_file_count"]} canonical files '
            text += 'plus an explicit mapping for byte-identical duplicate paths. '
            text += f'Files and checksums: [{plan["hub_path"]}/migration.json]({plan["hub_path"]}/migration.json). '
            text += 'These are historical development records, not a curated training split.\n'
            readme = output/'README.md'
            readme.write_text(text, encoding='utf-8')
            operations.append(CommitOperationAdd(path_in_repo='README.md', path_or_fileobj=str(readme)))
        print(f'Uploading {plan["canonical_file_count"]} canonical files to the dataset.', flush=True)
        head = api.create_commit(DATASET_REPOSITORY, repo_type='dataset', parent_commit=head,
            operations=operations, commit_message='Preserve verified historical GitHub evidence').oid
    print('Upload present; downloading every canonical file for verification.', flush=True)
    receipt = verify_remote(plan, head, output/'verification-download', token=token)
    proof_path = plan['hub_path']+'/verification.json'
    if not api.file_exists(DATASET_REPOSITORY, proof_path, repo_type='dataset', revision=head):
        proof = output/'verification.json'
        write_json(proof, receipt)
        head = api.create_commit(DATASET_REPOSITORY, repo_type='dataset', parent_commit=head,
            operations=[CommitOperationAdd(path_in_repo=proof_path, path_or_fileobj=str(proof))],
            commit_message='Record successful archive checksum verification').oid
    else:
        previous = hf_hub_download(DATASET_REPOSITORY, proof_path, repo_type='dataset', revision=head,
                                   token=token, local_dir=output/'existing', force_download=True)
        proof = json.loads(Path(previous).read_text(encoding='utf-8'))
        if any(proof.get(key) != value for key, value in receipt.items() if key != 'data_revision'):
            raise ValueError('Existing verification record differs and will not be overwritten')
    receipt.update(hub_revision=head, verified_at_utc=datetime.now(timezone.utc).isoformat(),
                   url=f'https://huggingface.co/datasets/{DATASET_REPOSITORY}/tree/{head}/{plan["hub_path"]}')
    write_json(output/'migration-receipt.json', receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--upload', action='store_true')
    mode.add_argument('--verify-revision', help='Read-only verification of an existing full Hub commit')
    args = parser.parse_args(argv)
    plan = load_plan(args.plan)
    if args.verify_revision:
        receipt = verify_remote(plan, args.verify_revision, args.output/'verification-download')
        write_json(args.output/'migration-receipt.json', receipt)
    else:
        data = prepare_source(plan, args.output)
        print(f'{plan["source_file_count"]} source paths verified; {plan["canonical_file_count"]} canonical files; '
              f'{plan["canonical_bytes"]:,} bytes. Destination: {DATASET_REPOSITORY}/{plan["hub_path"]}', flush=True)
        if not args.upload:
            print('Preparation only. No Hugging Face write, no GitHub deletion.', flush=True)
            return 0
        receipt = publish(plan, data, args.output, card=args.card)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
