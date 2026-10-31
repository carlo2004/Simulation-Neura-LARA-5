"""Named, separately classified team runs with immutable HF snapshots."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata
from uuid import uuid4

from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
from huggingface_hub.errors import HfHubHTTPError

from stacklab.config import write_json
from stacklab.experiments import digest, load_plan
from stacklab.paths import ROOT
from stacklab.publication import (REPORT_FILES, dataset_repository, package_evidence,
                                  prepare_experiment_evidence, safe_relative)

KINDS = {'experiment': 'experiments', 'playground': 'playground'}
TASK_FILES = {'task.json', 'result.json', 'scene.json', 'context.json', 'initial_physics.json',
              'final_physics.json', 'trajectory.jsonl', 'motion.jsonl', 'execution.json',
              'simulation.log', 'simulation.mp4', 'simulation.replay.json'}
ROUND_FILES = {'request.json', 'response.json', 'generation.json', 'generated.py', 'feedback.json',
               'stream.jsonl', 'remote-server.json', 'remote-request.json', 'remote-stream.jsonl',
               'server-generation.json', 'inference.log', 'device.json'}


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def source_format(directory):
    if (directory/'manifest.json').is_file():
        load_plan(directory)  # A corrupt frozen plan must never become an ungraded playground upload.
        return 'experiment'
    if (directory/'task.json').is_file():
        return 'task'
    if any(p.is_dir() and (p/'task.json').is_file() for p in directory.glob('task_[0-9]*')):
        return 'chat'
    result = read_json(directory/'result.json')
    if result.get('case') and (directory/'scene.json').is_file():
        return 'benchmark-task'
    if any(read_json(p/'result.json').get('case') and (p/'scene.json').is_file()
           for p in directory.iterdir() if p.is_dir()):
        return 'benchmark'
    raise ValueError('No StackLab run found. Select a chat, task, benchmark or frozen experiment folder.')


def share_settings(directory, fmt, *, kind=None, title=None, note=None, tags=None):
    previous = read_json(directory/'sharing.json')
    if (directory/'sharing.json').exists() and not previous:
        raise ValueError('Unreadable sharing.json; preserve it and choose a new run folder')
    kind = kind or previous.get('kind') or ('experiment' if fmt == 'experiment' else 'playground')
    if kind not in KINDS or kind == 'experiment' and fmt != 'experiment':
        raise ValueError('experiment requires a frozen experiment plan; use playground for free attempts')
    if previous:
        if (previous.get('schema_version') != 1 or not re.fullmatch('[0-9a-f]{32}', previous.get('run_id', ''))
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}_[a-z0-9-]{1,48}_[0-9a-f]{12}', previous.get('run_key', ''))):
            raise ValueError('Invalid sharing.json; preserve it and choose a new run folder')
        if previous['kind'] != kind or previous['source_format'] != fmt:
            raise ValueError('A shared run keeps its category and identity; create a new run for a different condition')
    title = title if title is not None else previous.get('title', directory.name)
    note = note if note is not None else previous.get('note', '')
    tags = tags if tags is not None else previous.get('tags', [])
    if not isinstance(title, str) or not title.strip() or len(title) > 160 or not isinstance(note, str) or len(note) > 4000:
        raise ValueError('Choose a nonempty title up to 160 characters and a note up to 4000 characters')
    if not isinstance(tags, list) or len(tags) > 12 or any(not isinstance(t, str) or not t.strip() or len(t) > 40 for t in tags):
        raise ValueError('Use at most twelve short nonempty tags')
    run_id = previous.get('run_id') or uuid4().hex
    created = previous.get('created_at_utc') or datetime.now(timezone.utc).isoformat()
    slug = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()
    slug = re.sub('[^a-z0-9]+', '-', slug).strip('-')[:48].rstrip('-') or 'run'
    return dict(schema_version=1, run_id=run_id, run_key=previous.get('run_key') or created[:10]+'_'+slug+'_'+run_id[:12],
                created_at_utc=created, kind=kind, source_format=fmt,
                title=title.strip(), note=note, tags=list(dict.fromkeys(tags)))


def copy_file(source, destination):
    if source.is_symlink():
        raise ValueError('Run evidence must not contain symbolic links: '+source.name)
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def copy_task(source, destination):
    if source.is_symlink():
        raise ValueError('Run evidence must not contain symbolic links')
    for name in TASK_FILES:
        copy_file(source/name, destination/name)
    for path in sorted(source.glob('round_*')):
        if re.fullmatch(r'round_\d+', path.name):
            if path.is_symlink():
                raise ValueError('Run evidence must not contain symbolic links')
            if path.is_dir():
                for name in ROUND_FILES:
                    copy_file(path/name, destination/path.name/name)
    if (source/'episode').is_dir():
        copy_task(source/'episode', destination/'episode')


def unplanned_evidence(directory, evidence, fmt):
    evidence.mkdir(parents=True)
    if fmt in ('task', 'benchmark-task'):
        copy_task(directory, evidence)
        paths = [evidence]
    elif fmt == 'chat':
        copy_file(directory/'session.json', evidence/'session.json')
        originals = [p for p in sorted(directory.glob('task_[0-9]*')) if p.is_dir() and (p/'task.json').is_file()]
        for path in originals:
            copy_task(path, evidence/path.name)
        paths = [evidence/p.name for p in originals]
    else:
        originals = [p for p in sorted(directory.iterdir()) if p.is_dir()
                     and read_json(p/'result.json').get('case') and (p/'scene.json').is_file()]
        for path in originals:
            copy_task(path, evidence/path.name)
        paths = [evidence/p.name for p in originals]
    rows = []
    for index, path in enumerate(paths, 1):
        root = read_json(path/'result.json')
        execution = root.get('execution') or root
        initial = read_json(path/'task.json') or read_json(path/'episode/task.json')
        verified = (True if execution.get('status') == 'verified_success'
                    and execution.get('evaluation', {}).get('success') is True else
                    False if execution.get('goal') and execution.get('status') == 'budget_exhausted' else None)
        rows.append(dict(episode_id=path.name if path != evidence else 'task',
            relative_path=path.relative_to(evidence).as_posix(),
            instruction=root.get('instruction') or initial.get('instruction', ''),
            model=(execution.get('model') or initial.get('model') or {}).get('model_key', 'unknown'),
            tokenizer=(execution.get('model') or initial.get('model') or {}).get('tokenizer'),
            status=execution.get('status', 'incomplete'), goal_success=verified,
            rounds=len(execution.get('rounds', [])), performance=execution.get('inference_performance', {}),
            complete=bool(root), error=root.get('error')))
    return rows


def fence(text):
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, indent=2)
    if len(text) > 24000:
        text = text[:24000]+'\n[Anzeige gekürzt; die vollständigen Daten stehen in evidence.zip.]'
    delimiter = '`' * max(3, max((len(x) for x in re.findall(r'`+', text)), default=0)+1)
    return delimiter+'\n'+text+'\n'+delimiter


def cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def write_views(evidence, settings, rows):
    lines = ['# '+cell(settings['title']), '', '**Bereich:** '+settings['kind'],
             '**Run-ID:** `'+settings['run_id']+'`', '', settings['note'], '',
             'Tags: '+', '.join(settings['tags']), '',
             '[Vollständige Rohdaten](evidence.zip) · [Dateiprüfsummen](snapshot.json)', '',
             'Freie Aufgaben ohne festgelegtes Ziel bleiben unbewertet. Ein Modell-Fertigsignal ist kein gemessener Erfolg.', '',
             '| Versuch | Modell | Status | Physischer Erfolg | Token/s |', '|---|---|---|---|---:|']
    public = ['README.md', 'shared-run.json', 'episodes.jsonl']
    (evidence/'details').mkdir()
    for index, row in enumerate(rows, 1):
        name = 'details/'+str(index).zfill(5)+'.md'
        success = {True: 'ja', False: 'nein', None: 'unbewertet'}[row.get('goal_success')]
        speed = row.get('performance', {}).get('decode_tokens_per_second')
        speed = f'{speed:.2f}' if isinstance(speed, (float, int)) else '—'
        lines.append(f'| [{cell(row["episode_id"])}]({name}) | {cell(row["model"])} | '
                     f'{cell(row["status"])} | {success} | {speed} |')
        path = evidence/row.get('relative_path', row['episode_id'])
        result = read_json(path/'result.json')
        execution = result.get('execution') or result or read_json(path/'execution.json')
        text = ['# '+cell(row['episode_id']), '', '## Auftrag', '', fence(row.get('instruction', result.get('instruction', ''))),
                '', f'Physischer Erfolg: **{success}** · Status: **{cell(row["status"])}** · Ausgabe: **{speed} Token/s**', '']
        if row.get('error'):
            text += ['## Fehler', '', fence(row['error']), '']
        for item in execution.get('rounds', []):
            root = path/'episode' if (path/'episode/task.json').exists() else path
            block = root/('round_'+str(item['round']).zfill(2))
            response = read_json(block/'response.json')
            message = (response.get('choices') or [{}])[0].get('message', {})
            text += ['## Programmblock '+str(item['round']), '', fence(message.get('content') or '(keine Antwort gespeichert)'), '']
            code = block/'generated.py'
            if code.is_file():
                text += ['### Geprüfter Programmcode', '', fence(code.read_text(encoding='utf-8')), '']
            text += ['### Gemessene Rückmeldung', '', fence(item.get('feedback', {})), '']
        (evidence/name).write_text('\n'.join(text), encoding='utf-8')
        public.append(name)
    (evidence/'README.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return public


def prepare_shared(directory, staging, settings):
    if settings['source_format'] == 'experiment':
        plan, report, evidence = prepare_experiment_evidence(directory, staging)
        cases = {c['case_id']: c for c in plan['cases']}
        conditions = {c['condition_id']: c for c in plan['conditions']}
        rows = [dict(r, instruction=cases[r['case_id']]['instruction'], split=plan['split'],
                     tokenizer=conditions[r['condition_id']]['model_config'].get('tokenizer')) for r in report['episodes']]
        complete = report['complete']
        source_plan = plan['plan_sha256']
        public = list(REPORT_FILES)
    else:
        evidence = Path(staging)/'evidence'
        rows = unplanned_evidence(directory, evidence, settings['source_format'])
        complete = all(r['complete'] for r in rows)
        source_plan = None
        public = []
    write_json(evidence/'shared-run.json', settings)
    with (evidence/'episodes.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n')
    public += write_views(evidence, settings, rows)
    snapshot, upload = package_evidence(evidence, Path(staging)/'upload',
        dict(schema_version=2, run_id=settings['run_id'], kind=settings['kind'], source_format=settings['source_format']),
        public_files=list(dict.fromkeys(public)), complete=complete, planned=len(rows), source_plan_sha256=source_plan)
    return snapshot, upload, rows


def download_json(repository, name, revision):
    return read_json(hf_hub_download(repository, name, repo_type='dataset', revision=revision))


def share_run(directory, repository=None, *, kind=None, title=None, note=None, tags=None, dry_run=False, direct=None):
    directory = Path(directory).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError('Run directory does not exist')
    repository = dataset_repository(repository)
    fmt = source_format(directory)
    settings = share_settings(directory, fmt, kind=kind, title=title, note=note, tags=tags)
    with tempfile.TemporaryDirectory(prefix='stacklab-share-') as temp:
        snapshot, upload, rows = prepare_shared(directory, temp, settings)
        if dry_run:
            return dict(repository=repository, kind=settings['kind'], title=settings['title'],
                        run_id=settings['run_id'], planned=len(rows), snapshot_id=snapshot['snapshot_id'],
                        archive_bytes=snapshot['archive']['bytes'], files=snapshot['files'])
        api = HfApi()
        uploader = api.whoami()['name']
        if not re.fullmatch('[A-Za-z0-9_.-]+', uploader):
            raise ValueError('Unexpected Hugging Face username')
        write_json(directory/'sharing.json', settings)  # Stable identity survives a failed network attempt.
        prefix = KINDS[settings['kind']]+'/'+uploader+'/'+settings['run_key']
        snapshot_prefix = prefix+'/snapshots/'+snapshot['snapshot_id']
        record = dict(settings, uploader=uploader, latest_snapshot=snapshot['snapshot_id'],
                      snapshot_path=snapshot_prefix, complete=snapshot['complete'], planned=len(rows),
                      verified_successes=sum(r.get('goal_success') is True for r in rows),
                      ungraded=sum(r.get('goal_success') is None for r in rows))
        write_json(Path(temp)/'run.json', record)
        root_readme = Path(temp)/'README.md'
        root_readme.write_text('# '+cell(settings['title'])+'\n\nBereich: **'+settings['kind']+'** · Hochgeladen von **'+uploader+'**\n\n'+
            settings['note']+'\n\n[Versuche, Code und Messwerte ansehen](snapshots/'+snapshot['snapshot_id']+'/README.md)\n\n'+
            'Run-ID: `'+settings['run_id']+'`\n', encoding='utf-8')
        previous = read_json(directory/'share-receipt.json')
        use_direct = uploader == repository.split('/')[0] if direct is None else direct
        revision, create_pr, pr_url = 'main', not use_direct, None
        if not use_direct and all(previous.get(k) == v for k, v in
                                  dict(repository=repository, uploader=uploader, run_id=settings['run_id']).items()):
            if previous.get('pr_num'):
                try:
                    discussion = api.get_discussion_details(repository, previous['pr_num'], repo_type='dataset')
                    if discussion.status in ('open', 'draft'):
                        revision, create_pr, pr_url = previous['pr_revision'], False, previous['pr_url']
                except HfHubHTTPError as error:
                    if getattr(error.response, 'status_code', None) != 404:
                        raise
        if create_pr:
            # Recover a successful server-side submission after a lost local response/receipt.
            expected_title = 'StackLab: '+settings['kind']+' | '+uploader+' | '+settings['run_key']
            for discussion in api.get_repo_discussions(repository, repo_type='dataset', author=uploader,
                                                       discussion_type='pull_request'):
                if discussion.status not in ('open', 'draft') or discussion.title != expected_title:
                    continue
                candidate = 'refs/pr/'+str(discussion.num)
                head = api.repo_info(repo_id=repository, repo_type='dataset', revision=candidate).sha
                if (api.file_exists(repo_id=repository, filename=prefix+'/run.json', repo_type='dataset', revision=head)
                        and download_json(repository, prefix+'/run.json', head).get('run_id') == settings['run_id']):
                    revision, create_pr, pr_url = candidate, False, discussion.url
                    break
        for attempt in range(3):
            head = api.repo_info(repo_id=repository, repo_type='dataset', revision=revision).sha
            marker = snapshot_prefix+'/snapshot.json'
            exists = api.file_exists(repo_id=repository, filename=marker, repo_type='dataset', revision=head)
            if exists and download_json(repository, marker, head) != snapshot:
                raise ValueError('Existing immutable snapshot differs; it will not be overwritten')
            old = (download_json(repository, prefix+'/run.json', head)
                   if api.file_exists(repo_id=repository, filename=prefix+'/run.json', repo_type='dataset', revision=head) else {})
            if old and old.get('run_id') != settings['run_id']:
                raise ValueError('Run folder belongs to a different identity; it will not be overwritten')
            if exists and old == record:
                commit = head
                break
            operations = [] if exists else [CommitOperationAdd(path_in_repo=snapshot_prefix+'/'+p.relative_to(upload).as_posix(),
                                path_or_fileobj=str(p)) for p in sorted(upload.rglob('*')) if p.is_file()]
            operations += [CommitOperationAdd(path_in_repo=prefix+'/run.json', path_or_fileobj=str(Path(temp)/'run.json')),
                           CommitOperationAdd(path_in_repo=prefix+'/README.md', path_or_fileobj=str(root_readme))]
            if use_direct and uploader == repository.split('/')[0]:
                # Add navigation once, preserving the owner's existing card verbatim.
                if api.file_exists(repo_id=repository, filename='README.md', repo_type='dataset', revision=head):
                    card = Path(hf_hub_download(repository, 'README.md', repo_type='dataset', revision=head)).read_text(encoding='utf-8')
                else:
                    card = (ROOT/'config/huggingface/README.md').read_text(encoding='utf-8')
                if '<!-- stacklab:team-sharing -->' not in card:
                    web = 'https://huggingface.co/datasets/'+repository+'/tree/main/'
                    card += '\n<!-- stacklab:team-sharing -->\n## Teamversuche\n\n'
                    card += '[Geplante Experimente]('+web+'experiments) · [Playground]('+web+'playground) · [Historische Daten]('+web+'legacy)\n\n'
                    card += 'Pro Nutzer und Run gibt es einen eigenen Ordner mit Titel, Notiz und unveränderlichen Snapshots. '
                    card += 'Jeder Snapshot besitzt eine lesbare Übersicht mit Auftrag, Code, Feedback und Tokenmessungen. '
                    card += 'Noch nicht übernommene Teambeiträge stehen unter Community als StackLab-PRs.\n'
                    card_path = Path(temp)/'hub-README.md'
                    card_path.write_text(card, encoding='utf-8')
                    operations.append(CommitOperationAdd(path_in_repo='README.md', path_or_fileobj=str(card_path)))
            try:
                result = api.create_commit(repo_id=repository, repo_type='dataset', revision=revision,
                    parent_commit=head, operations=operations, create_pr=create_pr,
                    commit_message='StackLab: '+settings['kind']+' | '+uploader+' | '+settings['run_key'],
                    commit_description=settings['title']+'\n\n'+settings['note'])
                commit = result.oid
                if create_pr:
                    pr_url = result.pr_url
                    revision = result.pr_revision
                break
            except HfHubHTTPError as error:
                if getattr(error.response, 'status_code', None) not in (409, 412) or attempt == 2:
                    raise
        receipt = dict(repository=repository, uploader=uploader, run_id=settings['run_id'],
            kind=settings['kind'], snapshot_id=snapshot['snapshot_id'], revision=commit, run_path=prefix,
            url=f'https://huggingface.co/datasets/{repository}/blob/{commit}/{snapshot_prefix}/README.md',
            pr_url=pr_url, pr_revision=revision if pr_url else None,
            pr_num=int(pr_url.rstrip('/').rsplit('/', 1)[-1]) if pr_url else None)
        write_json(directory/'share-receipt.json', receipt)
        if receipt['pr_num']:
            discussion = api.get_discussion_details(repository, receipt['pr_num'], repo_type='dataset')
            if discussion.status == 'draft':
                api.change_discussion_status(repository, receipt['pr_num'], 'open', repo_type='dataset')
        return receipt


def list_runs(repository=None, *, kind=None, uploader=None, pending=False, limit=50):
    repository = dataset_repository(repository)
    if kind is not None and kind not in KINDS or type(limit) is not int or limit < 1:
        raise ValueError('Use a supported category and a positive result limit')
    api = HfApi()
    refs = [('main', None)]
    if pending:
        for discussion in api.get_repo_discussions(repository, repo_type='dataset'):
            if discussion.is_pull_request and discussion.status in ('open', 'draft') and discussion.title.startswith('StackLab: '):
                refs.append(('refs/pr/'+str(discussion.num), discussion.url))
    records = []
    for revision, pr_url in refs:
        head = api.repo_info(repo_id=repository, repo_type='dataset', revision=revision).sha
        for name in api.list_repo_files(repository, repo_type='dataset', revision=head):
            parts = name.split('/')
            if (len(parts) != 4 or parts[0] not in KINDS.values() or parts[-1] != 'run.json'
                    or kind and parts[0] != KINDS[kind] or uploader and parts[1] != uploader):
                continue
            record = download_json(repository, name, head)
            if (record.get('kind') not in KINDS or KINDS[record['kind']] != parts[0]
                    or record.get('uploader') != parts[1]
                    or not re.fullmatch('[0-9a-f]{64}', record.get('latest_snapshot', ''))
                    or record.get('snapshot_path') != '/'.join(parts[:3])+'/snapshots/'+record['latest_snapshot']):
                raise ValueError('Run index metadata does not match its namespace')
            if any(r['run_id'] == record['run_id'] and r['latest_snapshot'] == record['latest_snapshot']
                   and r['uploader'] == record['uploader'] for r in records):
                continue
            record.update(pr_url=pr_url, url=f'https://huggingface.co/datasets/{repository}/blob/{head}/'+record['snapshot_path']+'/README.md')
            records.append(record)
    return sorted(records, key=lambda r: (r['created_at_utc'], r['run_id']), reverse=True)[:limit]
