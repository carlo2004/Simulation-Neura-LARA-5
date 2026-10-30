"""Publish benchmark evidence as immutable GitHub Release assets, outside source history."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from stacklab.backup import backup_experiment
from stacklab.config import write_json
from stacklab.experiments import load_plan, write_report
from stacklab.llm.catalog import sha256


def publish_experiment(directory, repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Repository must be owner/name')
    executable = shutil.which('gh')
    if not executable:
        raise ValueError('GitHub CLI is missing; install gh and run gh auth login on the local computer')
    directory = Path(directory).resolve()
    plan = load_plan(directory)
    report = write_report(directory)
    from stacklab.review import write_review
    write_review(directory, report=report)
    allowed_roots = {e['episode_id'] for e in plan['episodes']} | {'model-setups'}
    allowed_files = {'manifest.json', 'runtime-verification.json', 'summary.json', 'results.csv',
                     'report.md', 'ranking.json', 'ranking.md', 'review.html'}
    # Export only the benchmark's own records, not unrelated local files.
    paths = [p for p in directory.rglob('*') if
             p.relative_to(directory).parts[0] in allowed_roots or p.name in allowed_files
             and len(p.relative_to(directory).parts) == 1]
    if any(p.is_symlink() for p in paths):
        raise ValueError('Benchmark evidence must not contain symbolic links')
    subprocess.run([executable, 'auth', 'status', '--hostname', 'github.com'], check=True)
    tag = 'benchmark-'+plan['plan_sha256'][:16]
    exists = subprocess.run([executable, 'release', 'view', tag, '--repo', repository],
                            capture_output=True, text=True)
    if exists.returncode == 0:
        raise ValueError('A release for this immutable plan already exists; it will not be overwritten')
    with tempfile.TemporaryDirectory(prefix='stacklab-publish-') as temp:
        root = Path(temp)
        staged = root/'evidence'
        staged.mkdir()
        checksums = {}
        for path in sorted(paths):
            if path.is_file() and path.suffix != '.tmp':
                relative = path.relative_to(directory)
                target = staged/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                checksums[relative.as_posix()] = sha256(target)
        write_json(staged/'checksums.json', checksums)
        archive = backup_experiment(staged, root/'assets')
        digest = sha256(archive)
        checksum_file = root/'archive-sha256.txt'
        checksum_file.write_text(digest+'  '+archive.name+'\n', encoding='utf-8')
        notes = root/'release-notes.md'
        notes.write_text((staged/'ranking.md').read_text(encoding='utf-8')+'\n'+
                         (staged/'report.md').read_text(encoding='utf-8'), encoding='utf-8')
        command = [executable, 'release', 'create', tag, '--repo', repository,
                   '--title', 'Benchmark '+plan['plan_sha256'][:16], '--notes-file', str(notes),
                   '--latest=false', str(archive), str(checksum_file),
                   *[str(staged/name) for name in ('manifest.json', 'summary.json', 'results.csv', 'ranking.json')]]
        # Tag the recorded source revision when available; no local git staging/push.
        commit = plan.get('software', {}).get('git_commit')
        if commit and re.fullmatch(r'[0-9a-f]{40}', commit):
            command += ['--target', commit]
        subprocess.run(command, check=True)
    return 'https://github.com/'+repository+'/releases/tag/'+tag
