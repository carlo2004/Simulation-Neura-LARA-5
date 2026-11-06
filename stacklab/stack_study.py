"""A paired stack-only collection, built from the existing frozen experiment runner."""
from contextlib import closing, redirect_stdout
from dataclasses import asdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import tempfile
import time
from uuid import uuid4
import zipfile

from stacklab.config import Config, write_json
from stacklab import experiments as exp
from stacklab.llm.catalog import lock, sha256
from stacklab.llm.remote import RemoteControl
from stacklab.paths import ROOT
from stacklab.policy import ExecutionLimits
from stacklab.publication import safe_relative

SPEC = ROOT/'config/studies/stack-v2.json'
BANK = ROOT/'config/studies/stack-v2-scenes.json'
VALID = {'success', 'model_failure'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def spec():
    return read(SPEC)


def physics_control(config):
    """Feasibility control only. Its code/trajectory is never passed to the LLM."""
    from stacklab.evaluation import evaluate, observe
    from stacklab.sim.robot import Simulation
    with closing(Simulation(config, visuals=False)) as robot:
        initial = observe(robot)
        with redirect_stdout(io.StringIO()):
            result = robot.stack('red', 'blue')
            grading = evaluate(robot, dict(type='stack', source='red', target='blue'))
        return dict(success=bool(result['success'] and grading['success']),
                    initial_observation=initial, evaluation=grading,
                    simulation_seconds=float(robot.data.time))


def physics_fingerprint():
    sources = {name:value for name,value in exp.source_hashes().items()
               if name.startswith(('stacklab/sim/', 'assets/robots/lara5/'))
               or name in ('stacklab/config.py', 'stacklab/evaluation.py')}
    return dict(packages=exp.environment()['packages'], source_hashes=sources)


def build_bank(settings=None, control=physics_control):
    settings = settings or spec()
    rng = random.Random(settings['layout_seed'])
    accepted, rejected = [], []
    angles = dict(east=0., north=math.pi/2, west=math.pi, south=-math.pi/2)
    candidate = 0
    for block in range(settings['scene_blocks']):
        for direction in settings['directions']:
            for distance, limits in settings['distances_m'].items():
                for _ in range(300):
                    candidate += 1
                    angle = angles[direction]+rng.uniform(-math.pi/7, math.pi/7)
                    gap = rng.uniform(*limits)
                    centre = [rng.uniform(.29, .51), rng.uniform(-.18, .18)]
                    delta = [gap*math.cos(angle), gap*math.sin(angle)]
                    red = [round(centre[k]-delta[k]/2, 6) for k in (0, 1)]
                    blue = [round(centre[k]+delta[k]/2, 6) for k in (0, 1)]
                    if any(not .26 <= p[0] <= .54 or not -.22 <= p[1] <= .22 for p in (red, blue)):
                        continue
                    config = Config(seed=settings['layout_seed']+candidate, red_xy_m=red, blue_xy_m=blue).validate()
                    try:
                        quality = control(config)
                    except (ValueError, RuntimeError) as error:
                        quality = dict(success=False, error=type(error).__name__+': '+str(error))
                    if not quality['success']:
                        rejected.append(dict(candidate=candidate, config=config.to_dict(), quality=quality))
                        continue
                    index = len(accepted)
                    case = dict(name='red-on-blue', instruction=settings['instruction'],
                        source='red', target='blue', scene_seed=config.seed, config=config.to_dict(),
                        initial_object_positions=config.scene(), goal=dict(type='stack', source='red', target='blue'),
                        layout_id=f'layout-{index+1:03d}', scene_block=block+1,
                        stratum=direction+'-'+distance,
                        generation_seeds=[100003+index*97+r*1000000 for r in range(settings['generation_repetitions'])])
                    check = quality.get('evaluation', {}).get('stack_checks', [{}])[0]
                    accepted.append(dict(case=case, quality=dict(success=True,
                        stable_checks=check.get('stable_checks'), checks=check.get('checks'),
                        tool_clear=check.get('tool_clear'))))
                    print(f'Feasible scene {len(accepted)}: {case["stratum"]}', flush=True)
                    break
                else:
                    raise RuntimeError('Could not construct a feasible scene in '+direction+'-'+distance)
    value = dict(schema_version=1, spec_sha256=exp.digest(settings), cases=accepted, rejected=rejected,
                 validation_fingerprint=physics_fingerprint(),
                 control='Handwritten Simulation.stack plus the independent contact/stability evaluator; not model inference')
    return dict(value, bank_sha256=exp.digest(value))


def load_bank():
    bank = read(BANK)
    if exp.digest({k:v for k,v in bank.items() if k != 'bank_sha256'}) != bank.get('bank_sha256'):
        raise ValueError('Scene bank checksum mismatch')
    if bank['spec_sha256'] != exp.digest(spec()):
        raise ValueError('Scene bank belongs to a different protocol')
    if any(not item['quality']['success'] for item in bank['cases']):
        raise ValueError('Scene bank includes an infeasible control scene')
    return bank


def trial_id(study, model, case, seed):
    return 'trial-'+exp.digest(dict(protocol=study['protocol_sha256'], model=model,
                                   layout=case['layout_id'], generation_seed=seed))[:20]


def expected_trials(study):
    return [dict(trial_id=trial_id(study, model, case, seed), model=model,
                 layout_id=case['layout_id'], scene_block=case['scene_block'], stratum=case['stratum'],
                 scene_seed=case['scene_seed'], generation_seed=seed)
            for case in study['cases'] for seed in case['generation_seeds'] for model in study['settings']['models']]


def load_study(directory):
    value = read(Path(directory)/'study.json')
    if value.get('schema_version') != 1 or exp.digest({k:v for k,v in value.items() if k != 'protocol_sha256'}) != value.get('protocol_sha256'):
        raise ValueError('Study protocol was modified; use a new collection for a new protocol')
    return value


def prepare(directory, checkpoint_dir=None):
    directory = Path(directory).resolve()
    if (directory/'study.json').exists():
        study = load_study(directory)
        if study['settings'] != spec() or study['bank_sha256'] != load_bank()['bank_sha256']:
            raise ValueError('Existing collection uses another study design; use its original notebook or a new Drive folder')
        if (directory/'feasibility.json').exists():
            if not read(directory/'feasibility.json').get('complete'):
                raise ValueError('Feasibility failed in this collection; preserve the evidence and investigate')
            if checkpoint_dir:
                root_checkpoint(directory, checkpoint_dir)
            return study
        verify_feasibility(directory, study)
        if checkpoint_dir:
            root_checkpoint(directory, checkpoint_dir)
        write_index(directory)
        return study
    if checkpoint_dir and (Path(checkpoint_dir)/'study.json').exists():
        restore(directory, checkpoint_dir)
        return prepare(directory, checkpoint_dir)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Choose an empty study directory')
    settings, bank = spec(), load_bank()
    models = {}
    for key in settings['models']:
        config = lock(key)
        config['context_tokens'] = settings['context_tokens']
        if config['quantization'] != settings['quantization']:
            raise ValueError('Study expects the same weight quantization for every model')
        models[key] = config
    directory.mkdir(parents=True, exist_ok=True)
    value = dict(schema_version=1, settings=settings, bank_sha256=bank['bank_sha256'], models=models,
                 created_at_utc=exp.utc_now(), software=exp.software_provenance(),
                 cases=[c['case'] for c in bank['cases']], source_hashes=exp.source_hashes(),
                 registry_sha256=sha256(ROOT/'config/models.lock.json'),
                 cuda_runtime_sha256=sha256(ROOT/'config/cuda.runtime.lock.json'),
                 policy_limits=asdict(ExecutionLimits.load()),
                 physics_packages=exp.environment()['packages'])
    study = dict(value, protocol_sha256=exp.digest(value))
    write_json(directory/'study.json', study)
    verify_feasibility(directory, study)
    if checkpoint_dir:
        root_checkpoint(directory, checkpoint_dir)
    write_index(directory)
    return study


def verify_feasibility(directory, study):
    # Controls were already physically executed while constructing the frozen bank.
    # Verify that evidence instead of adding extra simulation episodes to this run.
    bank = load_bank()
    if bank['validation_fingerprint'] != physics_fingerprint():
        raise ValueError('Physics differs from the validated scene bank; install requirements-study.txt and use the pinned source')
    qc = [dict(layout_id=item['case']['layout_id'], **item['quality']) for item in bank['cases']]
    write_json(Path(directory)/'feasibility.json', dict(complete=True, scored_model_data=False,
        method='Frozen independently executed physical controls; environment/source fingerprints verified; no additional simulation episodes',
        validation_fingerprint=bank['validation_fingerprint'], checks=qc))


def write_index(directory):
    directory = Path(directory)
    study = load_study(directory)
    expected = {row['trial_id']: row for row in expected_trials(study)}
    attempts = []
    for batch in sorted((directory/'batches').glob('*')) if (directory/'batches').exists() else []:
        if not (batch/'manifest.json').exists():
            continue
        plan = exp.load_plan(batch)
        metadata = plan.get('metadata', {})
        if metadata.get('study_protocol_sha256') != study['protocol_sha256']:
            raise ValueError('Batch belongs to another study')
        cases = {c['case_id']: c for c in plan['cases']}
        conditions = {c['condition_id']: c for c in plan['conditions']}
        for episode in plan['episodes']:
            row = exp.episode_result(batch, episode, conditions[episode['condition_id']], cases[episode['case_id']], plan['plan_sha256'])
            if row['status'] == 'pending':
                continue
            identity = metadata['trial_ids'][episode['episode_id']]
            if identity not in expected:
                raise ValueError('Batch contains an unknown trial')
            attempts.append(dict(row, trial_id=identity, attempt_id=batch.name+'/'+episode['episode_id'],
                                 relative_path='batches/'+batch.name+'/'+episode['episode_id']))
    rows = []
    for identity, expected_row in expected.items():
        selected = [r for r in attempts if r['trial_id'] == identity]
        valid = next((r for r in selected if r['status'] in VALID), None)
        primary = valid or (selected[0] if selected else None)
        row = dict(expected_row, attempt_count=len(selected),
                   status=valid['status'] if valid else selected[-1]['status'] if selected else 'pending',
                   primary_attempt_id=primary['attempt_id'] if primary else None,
                   goal_success=valid['goal_success'] if valid else None,
                   scored=valid is not None,
                   rounds=primary['rounds'] if primary else None,
                   relative_path=primary['relative_path'] if primary else None,
                   performance=primary['performance'] if primary else {})
        for field in ('wall_seconds', 'execution_seconds', 'evaluation_seconds', 'model_declared_done',
                      'recording_error', 'error'):
            row[field] = primary.get(field) if primary else None
        if primary:
            attempt_path = directory/primary['relative_path']
            execution = (read(attempt_path/'result.json').get('execution', {})
                         if (attempt_path/'result.json').exists() else
                         read(attempt_path/'execution.json') if (attempt_path/'execution.json').exists() else {})
            turns = execution.get('rounds', [])
            row['first_block_goal_success'] = (turns[0].get('feedback', {}).get('evaluation', {}).get('success')
                                               if turns else None)
            row['first_success_round'] = next((r['round'] for r in turns
                if r.get('feedback', {}).get('evaluation', {}).get('success') is True), None)
            row['first_feedback_error'] = next((r['feedback']['error'] for r in turns
                if r.get('feedback', {}).get('error')), None)
        rows.append(row)
    for filename, values in [('trials.jsonl', rows), ('attempts.jsonl', attempts)]:
        temporary = directory/(filename+'.tmp')
        with temporary.open('w', encoding='utf-8', newline='\n') as stream:
            for row in values:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        temporary.replace(directory/filename)
    statuses = {name:sum(r['status'] == name for r in rows) for name in
                ('pending', 'success', 'model_failure', 'infrastructure_error', 'incomplete', 'cancelled')}
    value = dict(schema_version=1, protocol_sha256=study['protocol_sha256'], planned=len(rows),
                 scored=sum(r['status'] in VALID for r in rows), attempts=len(attempts), statuses=statuses,
                 collection_complete=all(r['status'] in VALID for r in rows),
                 note='Collection inventory only; no model ranking. All attempts are retained.')
    write_json(directory/'collection-status.json', value)
    return rows


def root_checkpoint(directory, checkpoint_dir):
    directory, destination = Path(directory).resolve(), Path(checkpoint_dir).resolve()
    if destination.is_relative_to(directory):
        raise ValueError('Checkpoint folder must be outside the working collection')
    destination.mkdir(parents=True, exist_ok=True)
    # study.json is the commit marker read by prepare/restore; publish it last.
    for name in ('feasibility.json', 'study.json'):
        source, target = directory/name, destination/name
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise ValueError('Checkpoint folder contains different study or feasibility evidence')
        else:
            temporary = target.with_suffix('.tmp')
            shutil.copyfile(source, temporary)
            temporary.replace(target)


def checkpoint_zip(base, paths, target):
    """One immutable context or episode archive; never rewrite the growing collection."""
    target = Path(target)
    if target.exists():
        return target
    base = Path(base)
    files = {p.relative_to(base).as_posix(): p for p in paths if p.is_file() and p.suffix != '.tmp'}
    if any(p.is_symlink() for p in files.values()):
        raise ValueError('Checkpoint data must not contain symbolic links')
    manifest = {name:dict(bytes=p.stat().st_size, sha256=sha256(p)) for name,p in files.items()}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('_checkpoint.json', json.dumps(manifest, sort_keys=True))
            for name, path in sorted(files.items()):
                archive.write(path, name)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def checkpoint_batch(batch, checkpoint_dir):
    batch = Path(batch)
    target = Path(checkpoint_dir)/'batches'/batch.name
    paths = [batch/'manifest.json', batch/'runtime-verification.json']
    paths += list((batch/'model-setups').rglob('*')) if (batch/'model-setups').exists() else []
    checkpoint_zip(batch, paths, target/'context.zip')
    plan = exp.load_plan(batch)
    for episode in plan['episodes']:
        folder = batch/episode['episode_id']
        if folder.exists():
            checkpoint_zip(batch, folder.rglob('*'), target/(episode['episode_id']+'.zip'))


def checkpoint_start(path, checkpoint_dir):
    """Persist intent before starting physics, without freezing an unfinished episode ZIP."""
    path = Path(path)
    batch = path.parent
    target = Path(checkpoint_dir)/'batches'/batch.name
    context = [batch/'manifest.json', batch/'runtime-verification.json']
    context += list((batch/'model-setups').rglob('*')) if (batch/'model-setups').exists() else []
    checkpoint_zip(batch, context, target/'context.zip')
    write_json(target/'starts'/(path.name+'.json'), read(path/'manifest.json'))


def restore_zip(archive_path, destination):
    with zipfile.ZipFile(archive_path) as archive:
        checks = json.loads(archive.read('_checkpoint.json'))
        if set(archive.namelist()) != set(checks)|{'_checkpoint.json'}:
            raise ValueError('Unexpected files in checkpoint '+str(archive_path))
        for name, identity in checks.items():
            relative = safe_relative(name)
            data = archive.read(name)
            if len(data) != identity['bytes'] or hashlib.sha256(data).hexdigest() != identity['sha256']:
                raise ValueError('Checkpoint checksum mismatch: '+name)
            target = Path(destination)/relative
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError('Restoring would overwrite different evidence: '+str(target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix+'.tmp')
            temporary.write_bytes(data)
            temporary.replace(target)


def restore(directory, checkpoint_dir):
    directory, checkpoint_dir = Path(directory).resolve(), Path(checkpoint_dir).resolve()
    if directory == checkpoint_dir or checkpoint_dir.is_relative_to(directory):
        raise ValueError('Working collection and checkpoint folder must be separate')
    directory.mkdir(parents=True, exist_ok=True)
    for name in ('study.json', 'feasibility.json'):
        source, target = checkpoint_dir/name, directory/name
        if not source.is_file():
            raise ValueError('Incomplete root checkpoint: '+name)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError('Local collection differs from checkpoint')
        shutil.copyfile(source, target)
    load_study(directory)
    for batch in sorted((checkpoint_dir/'batches').glob('*')) if (checkpoint_dir/'batches').exists() else []:
        safe_relative(batch.name)
        for marker in sorted((batch/'starts').glob('*.json')) if (batch/'starts').exists() else []:
            identity = read(marker)
            episode = safe_relative(identity['episode_id'])
            if episode.as_posix() != marker.stem or len(episode.parts) != 1:
                raise ValueError('Invalid episode start marker')
            target = directory/'batches'/batch.name/episode/'manifest.json'
            if target.exists():
                if read(target) != identity:
                    raise ValueError('Different episode identity already exists')
            else:
                write_json(target, identity)
        for archive in sorted(batch.glob('*.zip')):
            restore_zip(archive, directory/'batches'/batch.name)
    sessions = checkpoint_dir/'sessions'
    if sessions.exists():
        for path in sessions.glob('*.json'):
            target = directory/'sessions'/path.name
            target.parent.mkdir(exist_ok=True)
            if target.exists() and target.read_bytes() != path.read_bytes():
                raise ValueError('Different session record already exists')
            shutil.copyfile(path, target)
    write_index(directory)


def check_server(study, info):
    settings = study['settings']
    hardware = info.get('hardware') or {}
    gpus = hardware.get('gpus', [])
    if info.get('device') != 'cuda' or len(gpus) != 1 or settings['gpu_family'] not in gpus[0]['name']:
        raise ValueError('This study requires one NVIDIA A100 and CUDA inference')
    if (hardware.get('offloaded_layers', 0) < 1
            or hardware.get('offloaded_layers') != hardware.get('total_layers')):
        raise ValueError('Every model layer must be offloaded to the GPU')
    if info.get('prompt_cache') is not False or not info.get('capabilities', {}).get('model_switch'):
        raise ValueError('Use a benchmark server with model switching and prompt cache disabled')
    if info['threads'] != settings['threads']:
        raise ValueError('Server threads differ from the study protocol')
    if info.get('source_hashes', {}).get('config/models.lock.json') != study['registry_sha256']:
        raise ValueError('Server model registry differs from the frozen study')
    if info.get('source_hashes', {}).get('config/cuda.runtime.lock.json') != study['cuda_runtime_sha256']:
        raise ValueError('Server CUDA recipe differs from the frozen study')
    for name, value in study['source_hashes'].items():
        if name.startswith(('stacklab/', 'config/prompts/')) and info.get('source_hashes', {}).get(name) != value:
            raise ValueError('Server source differs: '+name)
    for model in settings['models']:
        actual = info['model_catalog'][model]
        if actual['model_sha256'] != study['models'][model]['model_sha256']:
            raise ValueError('Server model weights differ: '+model)
        if actual['context_tokens'] != settings['context_tokens'] or actual['quantization'] != settings['quantization']:
            raise ValueError('Server context or quantization differs: '+model)


def model_order(settings, block):
    models = settings['models']
    offset = ((block-1)//2 * max(1, len(models)//2)) % len(models)
    order = models[offset:]+models[:offset]
    return order if block % 2 else list(reversed(order))


def collect(directory, server_url, *, checkpoint_dir=None, max_hours=6., max_episodes=None, on_checkpoint=None):
    directory = Path(directory).resolve()
    study = load_study(directory)
    if study['settings'] != spec() or study['bank_sha256'] != load_bank()['bank_sha256']:
        raise ValueError('Study design differs; use the original pinned implementation')
    if exp.source_hashes() != study['source_hashes'] or sha256(ROOT/'config/models.lock.json') != study['registry_sha256']:
        raise ValueError('Code, prompts, robot or catalog changed; use the pinned study implementation')
    if (sha256(ROOT/'config/cuda.runtime.lock.json') != study['cuda_runtime_sha256']
            or asdict(ExecutionLimits.load()) != study['policy_limits']):
        raise ValueError('CUDA recipe or robot execution budgets changed; use the frozen study conditions')
    if exp.environment()['packages'] != study['physics_packages']:
        raise ValueError('Physics packages changed; install requirements-study.txt before resuming')
    qc = read(directory/'feasibility.json')
    if not qc.get('complete') or len(qc.get('checks', [])) != len(study['cases']) or any(not r['success'] for r in qc['checks']):
        raise ValueError('A complete independent stacking feasibility check is required')
    if not math.isfinite(max_hours) or max_hours <= 0 or max_episodes is not None and max_episodes < 1:
        raise ValueError('Use positive wall-time and episode limits')
    if on_checkpoint is not None and checkpoint_dir is None:
        raise ValueError('A checkpoint folder is required for remote backups')
    check_server(study, RemoteControl(server_url).info())
    rows = write_index(directory)
    by_id = {r['trial_id']:r for r in rows}
    settings = study['settings']
    deadline, completed = time.monotonic()+max_hours*3600, 0
    session = dict(session_id=uuid4().hex, started_at_utc=exp.utc_now(), environment=exp.environment(),
                   remote_server=RemoteControl(server_url).info(), max_hours=max_hours,
                   note='New sessions may have another A100 UUID/driver; each batch retains its exact environment.')
    session_file = directory/'sessions'/(session['session_id']+'.json')
    def save_session():
        write_json(session_file, session)
        if checkpoint_dir:
            write_json(Path(checkpoint_dir)/'sessions'/session_file.name, session)
            if on_checkpoint:
                on_checkpoint(checkpoint_dir)
    save_session()
    current = None

    def stop():
        return time.monotonic() >= deadline or max_episodes is not None and completed >= max_episodes

    def completed_episode(path):
        nonlocal completed
        completed += 1
        if checkpoint_dir:
            checkpoint_batch(path.parent, checkpoint_dir)
            if on_checkpoint:
                on_checkpoint(checkpoint_dir)

    def starting_episode(path):
        checkpoint_start(path, checkpoint_dir)
        if on_checkpoint:
            on_checkpoint(checkpoint_dir)  # Acknowledged before the physics worker is started.

    try:
        session['preflight'] = []
        for model in settings['models']:
            print('GPU load preflight (not a scored task): '+model, flush=True)
            response = RemoteControl(server_url).select(model)
            info = response['info']
            session['preflight'].append(dict(model=model, error=response.get('error'),
                setup_seconds=response.get('setup_seconds'), load_seconds=response.get('load_seconds'),
                model_config=info['config'], hardware=info.get('hardware'),
                startup_log=response.get('startup_log'), scored_model_data=False))
            save_session()
            if response.get('error'):
                raise RuntimeError('Model setup failed before scored trials: '+str(response['error']))
            check_server(study, info)
        for attempt in range(settings['technical_attempt_limit']):
            for block in range(1, settings['scene_blocks']+1):
                # Mirrored pairs balance early/late model position over four scene blocks.
                for model in model_order(settings, block):
                    if stop():
                        return write_index(directory)
                    definitions = []
                    for case in study['cases']:
                        if case['scene_block'] != block:
                            continue
                        seeds = [seed for seed in case['generation_seeds'] if
                            by_id[trial_id(study, model, case, seed)]['status'] not in VALID and
                            by_id[trial_id(study, model, case, seed)]['attempt_count'] <= attempt]
                        if seeds:
                            definitions.append(dict(case, generation_seeds=seeds))
                    if not definitions:
                        continue
                    # Never attach a new GPU/environment to an old frozen batch manifest.
                    current = directory/'batches'/('batch-'+exp.utc_now().replace(':','-')+'-'+model+'-'+uuid4().hex[:8])
                    metadata = dict(split='model_selection', study_protocol_sha256=study['protocol_sha256'],
                                    scene_block=block, session_id=session['session_id'], trial_ids={})
                    plan = exp.create_plan(current, models=[model], cases=['red-on-blue'],
                        case_definitions=definitions, scene_seeds=[c['scene_seed'] for c in definitions],
                        generation_seeds=sorted({s for c in definitions for s in c['generation_seeds']}),
                        blocks=[settings['max_program_blocks']], max_tokens=settings['max_tokens'],
                        thinking=settings['thinking'], thinking_budget=settings['thinking_budget'],
                        server_url=server_url, generation_timeout=settings['generation_timeout'],
                        execution_timeout=settings['execution_timeout'], recording=settings['recording'],
                        motion_fps=settings['motion_fps'], metadata=metadata)
                    lookup = {c['case_id']:c for c in plan['cases']}
                    metadata['trial_ids'] = {e['episode_id']:trial_id(study, model, lookup[e['case_id']],e['generation_seed'])
                                             for e in plan['episodes']}
                    # Finalize identifiers before any model request or checkpoint is made.
                    content = {k:v for k,v in plan.items() if k != 'plan_sha256'}
                    content['metadata'] = metadata
                    write_json(current/'manifest.json', dict(content, plan_sha256=exp.digest(content)))
                    report = exp.run_plan(current, on_episode=completed_episode, should_stop=stop,
                        on_model_ready=lambda info: check_server(study, info),
                        on_episode_start=starting_episode if checkpoint_dir else None)
                    if checkpoint_dir:
                        checkpoint_batch(current, checkpoint_dir)
                    rows = write_index(directory)
                    by_id = {r['trial_id']:r for r in rows}
                    if any(g['infrastructure_error'] for g in report['groups']):
                        raise RuntimeError('Infrastructure failure recorded. Fix the server/storage, then resume; model failures are not retried.')
    finally:
        if checkpoint_dir and current is not None and (current/'manifest.json').exists():
            checkpoint_batch(current, checkpoint_dir)
        session.update(ended_at_utc=exp.utc_now(), attempted_in_session=completed)
        save_session()
        write_index(directory)
    return rows


def export_collection(directory, output):
    """Create a local HF-ready snapshot. This function never logs in or uploads."""
    from stacklab.publication import package_evidence
    directory, output = Path(directory).resolve(), Path(output).resolve()
    if output.is_relative_to(directory) or output.exists():
        raise ValueError('Choose a new export folder outside the collection')
    rows = write_index(directory)
    study = load_study(directory)
    with tempfile.TemporaryDirectory(prefix='stack-study-export-') as temp:
        evidence = Path(temp)/'evidence'
        evidence.mkdir()
        roots = {'study.json', 'feasibility.json', 'trials.jsonl', 'attempts.jsonl', 'collection-status.json', 'batches', 'sessions'}
        for path in sorted(directory.rglob('*')):
            relative = path.relative_to(directory)
            if relative.parts[0] not in roots or path.suffix == '.tmp':
                continue
            if path.is_symlink():
                raise ValueError('Evidence cannot include symbolic links')
            if path.is_file():
                target = evidence/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        fields = ['trial_id', 'model', 'layout_id', 'scene_block', 'stratum', 'scene_seed', 'generation_seed',
                  'status', 'goal_success', 'scored', 'attempt_count', 'primary_attempt_id', 'rounds', 'relative_path',
                  'first_block_goal_success', 'first_success_round', 'first_feedback_error',
                  'wall_seconds', 'execution_seconds', 'evaluation_seconds', 'model_declared_done',
                  'recording_error', 'error', 'request_seconds', 'total_seconds', 'model_load_seconds',
                  'first_token_seconds_mean', 'decode_tokens_per_second', 'output_tokens',
                  'native_decode_tokens', 'decode_seconds', 'partial']
        with (evidence/'trials.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row, **{k:v for k,v in row['performance'].items() if k in fields}))
        text = ('# A100 stack study v2\n\nModel-selection data: red on blue, no movement screening.\n\n'
                f'Planned trials: {len(rows)}. Models: '+', '.join(study['settings']['models'])+'.\n\n'
                'trials.csv / trials.jsonl contain exactly one row per planned trial. attempts.jsonl retains every attempt. '
                'One attempt per planned trial; no automatic retries or replacement of failures. '
                'Batch plans can contain unstarted slots after interruptions; do not sum their planned counts.\n\n'
                'All raw code, model-provided reasoning, feedback, physics and motion records are in evidence.zip. '
                'No weights, credentials or model server cache are included.\n\n'
                'Compare models on the same paired layouts. Stability samples and program blocks are not additional independent trials. '
                'These are selection data, not an untouched final test set or automatically approved fine-tuning targets.\n')
        (evidence/'README.md').write_text(text, encoding='utf-8')
        snapshot, upload = package_evidence(evidence, output,
            dict(schema_version=1, source_format='stack-study', protocol_sha256=study['protocol_sha256']),
            public_files=['README.md', 'study.json', 'trials.csv', 'trials.jsonl', 'attempts.jsonl', 'collection-status.json'],
            planned=len(rows), complete=all(r['status'] in VALID for r in rows))
    return dict(snapshot_id=snapshot['snapshot_id'], output=str(upload), planned=len(rows), uploaded=False)
