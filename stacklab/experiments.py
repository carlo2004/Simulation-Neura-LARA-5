"""Frozen development experiments and rebuildable reports over existing raw logs."""
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
from types import SimpleNamespace

from stacklab.cli.benchmark import case_definition, run_case
from stacklab.config import write_json
from stacklab.llm.catalog import CACHE_ROOT, find_executable, lock, sha256
from stacklab.llm.metrics import summarize
from stacklab.paths import ROOT
from stacklab.policy import ExecutionLimits
from stacklab.provenance import software_provenance

SCHEMA = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def environment():
    return dict(python=platform.python_version(), platform=platform.platform(), machine=platform.machine(),
                processor=platform.processor(), logical_cpus=os.cpu_count(),
                packages={name: version(name) for name in ('mujoco', 'numpy', 'scipy', 'trimesh')})


def source_hashes():
    # Include generated collision/visual geometry: a git commit alone cannot identify it.
    paths = set((ROOT/'stacklab').rglob('*.py'))
    for directory in ('config/prompts', 'assets/robots/lara5'):
        paths.update(p for p in (ROOT/directory).rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(paths)}


def create_plan(directory, *, models, cases, scene_seeds, generation_seeds, blocks,
                max_tokens=2048, threads=8, thinking=None, thinking_budget=None,
                generation_timeout=600, execution_timeout=180):
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Choose a new empty experiment directory; existing evidence is preserved')
    if not all((models, cases, scene_seeds, generation_seeds, blocks)):
        raise ValueError('Models, cases, seeds and block budgets must not be empty')
    for values, minimum, label in ((scene_seeds, 0, 'scene seeds'), (generation_seeds, 0, 'generation seeds'),
                                    (blocks, 1, 'blocks')):
        if any(type(v) is not int or not minimum <= v <= 2**31-1 for v in values):
            raise ValueError(label+' must contain integers in the supported range')
        if len(set(values)) != len(values):
            raise ValueError('Duplicate '+label+' would repeat identical trials')
    if any(type(v) is not int or v < 1 for v in (max_tokens, threads, generation_timeout, execution_timeout)):
        raise ValueError('Token, thread and time budgets must be positive integers')
    if max(generation_seeds)+max(blocks)-1 > 2**31-1:
        raise ValueError('Generation seeds plus round offsets exceed the supported range')
    definitions = []
    for name in cases:
        for seed in scene_seeds:
            case = case_definition(name, seed)
            case['case_id'] = 'case-'+digest(case)[:16]
            definitions.append(case)
    if len({c['case_id'] for c in definitions}) != len(definitions):
        raise ValueError('Duplicate cases')
    conditions = []
    aliases = set()
    for model in models:
        config = lock(model)
        key = config['model_key']
        if key in aliases:
            raise ValueError('Duplicate model: '+key)
        aliases.add(key)
        enabled = config.get('default_thinking', False) if thinking is None else thinking
        budget = config.get('thinking_budget_tokens', -1) if thinking_budget is None else thinking_budget
        if not enabled and not config.get('supports_thinking_toggle', True):
            raise ValueError(key+' has no non-thinking mode')
        if max_tokens >= config.get('context_tokens', 4096):
            raise ValueError('max-tokens must be smaller than every model context')
        if enabled and (budget < -1 or budget >= max_tokens):
            raise ValueError('Thinking budget must be -1 or smaller than max-tokens')
        for count in blocks:
            condition = dict(model=key, model_config=config, blocks=count, max_tokens=max_tokens,
                             threads=threads, thinking=enabled, thinking_budget=budget if enabled else None,
                             generation_timeout=generation_timeout, execution_timeout=execution_timeout)
            condition['condition_id'] = 'condition-'+digest(condition)[:16]
            conditions.append(condition)
    episodes = []
    # Interleave conditions per case/seed. Each worker starts a fresh model process and scene.
    for case in definitions:
        for seed in generation_seeds:
            for condition in conditions:
                item = dict(case_id=case['case_id'], condition_id=condition['condition_id'], generation_seed=seed)
                item['episode_id'] = 'episode-'+digest(item)[:16]
                episodes.append(item)
    plan = dict(schema_version=SCHEMA, created_at_utc=utc_now(), split='development',
                note='Development pilot; not a held-out test or a normalized model-speed ranking.',
                software=software_provenance(), environment=environment(), source_hashes=source_hashes(),
                policy_limits=asdict(ExecutionLimits.load()), cases=definitions, conditions=conditions,
                episodes=episodes, physics_during_inference='paused', model_memory='reset per episode',
                loading='fresh runtime process per episode; OS file cache is not cleared',
                seed_schedule='generation_seed + round_index - 1')
    write_json(directory/'manifest.json', dict(plan, plan_sha256=digest(plan)))
    return load_plan(directory)


def load_plan(directory):
    plan = json.loads((Path(directory)/'manifest.json').read_text(encoding='utf-8'))
    if plan.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported experiment schema')
    content = {k: v for k, v in plan.items() if k != 'plan_sha256'}
    if digest(content) != plan.get('plan_sha256'):
        raise ValueError('Experiment manifest was modified; create a new plan for changed conditions')
    return plan


def verify_environment(plan):
    if source_hashes() != plan['source_hashes'] or asdict(ExecutionLimits.load()) != plan['policy_limits']:
        raise ValueError('Code, prompts, robot geometry or policy limits changed; create a new plan')
    if environment() != plan['environment']:
        raise ValueError('Hardware or package versions changed; create a new plan')
    checked = set()
    installations = {}
    for condition in plan['conditions']:
        key = condition['model']
        if key in checked:
            continue
        checked.add(key)
        config = lock(key)
        if config != condition['model_config']:
            raise ValueError('Model catalog changed for '+key+'; create a new plan')
        weights = CACHE_ROOT/'models'/config['model_filename']
        if (not weights.is_file() or weights.stat().st_size != config['model_bytes']
                or sha256(weights) != config['model_sha256']):
            raise ValueError('Model missing or checksum mismatch. Run python -m stacklab setup --model '+key)
        executable = find_executable(key)
        installations[key] = dict(model_sha256=config['model_sha256'], executable_sha256=sha256(executable),
                                  runtime_version=config['runtime_version'])
    return installations


def run_plan(directory):
    directory = Path(directory).resolve()
    plan = load_plan(directory)
    installations = verify_environment(plan)
    runtime_record = directory/'runtime-verification.json'
    if runtime_record.is_file():
        if json.loads(runtime_record.read_text(encoding='utf-8')) != installations:
            raise ValueError('Runtime executable changed since the first attempt; create a new plan')
    else:
        write_json(runtime_record, installations)
    cases = {c['case_id']: c for c in plan['cases']}
    conditions = {c['condition_id']: c for c in plan['conditions']}
    try:
        for index, episode in enumerate(plan['episodes'], 1):
            path = directory/episode['episode_id']
            if path.exists():
                # An interrupted attempt is evidence too. Never re-run or overwrite it implicitly.
                print(f'Skip existing attempt {episode["episode_id"]}', flush=True)
                continue
            case, condition = cases[episode['case_id']], conditions[episode['condition_id']]
            path.mkdir()
            write_json(path/'manifest.json', dict(schema_version=SCHEMA, **episode,
                       plan_sha256=plan['plan_sha256'], started_at_utc=utc_now()))
            args = SimpleNamespace(**{k: v for k, v in condition.items()
                                     if k not in ('condition_id', 'model_config', 'blocks')},
                                   seed=episode['generation_seed'], generation_seed=episode['generation_seed'],
                                   scene_seed=case['scene_seed'],
                                   feedback_rounds=0 if condition['blocks'] == 1 else condition['blocks'],
                                   instruction=None, gui=False, axes=False, stackviz=False)
            print(f'[{index}/{len(plan["episodes"])}] {condition["model"]} / {case["name"]} / '
                  f'{condition["blocks"]} blocks / scene {case["scene_seed"]} / generation {args.seed}', flush=True)
            run_case(case['name'], args, path, case=case)
            write_report(directory)
    finally:
        # This also exposes pending and interrupted episodes after Ctrl+C.
        report = write_report(directory)
    return report


def episode_result(directory, episode, condition, case, plan_sha256):
    path = Path(directory)/episode['episode_id']
    row = dict(**episode, model=condition['model'], blocks=condition['blocks'], case=case['name'],
               scene_seed=case['scene_seed'], status='pending', goal_success=None,
               model_declared_done=None, error=None, rounds=0, execution_outcomes=[], performance={})
    if not path.exists():
        return row
    row['status'] = 'incomplete'
    complete = (path/'result.json').is_file()
    if not complete and not (path/'execution.json').is_file():
        return row
    try:
        identity = json.loads((path/'manifest.json').read_text(encoding='utf-8'))
        expected = dict(schema_version=SCHEMA, **episode, plan_sha256=plan_sha256)
        if any(identity.get(key) != value for key, value in expected.items()):
            raise ValueError('Episode identity does not match the experiment plan')
        result = (json.loads((path/'result.json').read_text(encoding='utf-8')) if complete else
                  dict(execution=json.loads((path/'execution.json').read_text(encoding='utf-8'))))
        execution = result.get('execution', {})
        turns = execution.get('rounds', [])
        row.update(error=result.get('error') or execution.get('error') or
                   (turns[-1].get('feedback', {}).get('error') if turns else None), rounds=len(turns),
                   model_declared_done=turns[-1].get('model_declared_done') if turns else None,
                   execution_outcomes=[r.get('execution_outcome', 'unknown') for r in turns],
                   wall_seconds=execution.get('wall_seconds'),
                   execution_seconds=sum(r.get('execution_seconds', 0) for r in turns),
                   evaluation_seconds=sum(r.get('evaluation_seconds', 0) for r in turns),
                   performance=execution.get('inference_performance', {}))
        if not complete:
            return row
        status = execution.get('status')
        if (status == 'verified_success' and execution.get('success') is True
                and execution.get('evaluation', {}).get('success') is True):
            row.update(status='success', goal_success=True)
        elif status == 'budget_exhausted':
            row.update(status='model_failure', goal_success=False)
        elif status == 'cancelled':
            row['status'] = 'cancelled'
        elif status == 'error' and turns:
            generation = turns[-1].get('generation', {})
            timeout = str(execution.get('error', '')).startswith(('TimeoutError:', 'TimeoutError('))
            # Output truncation and an exhausted active request budget are model/resource failures.
            if (generation.get('finish_reason') == 'length'
                    or timeout and generation.get('performance', {}).get('request_seconds') is not None):
                row.update(status='model_failure', goal_success=False)
            else:
                row['status'] = 'infrastructure_error'
        else:
            row['status'] = 'infrastructure_error'
    except (OSError, ValueError, TypeError, AttributeError) as error:
        row.update(status='infrastructure_error', error='Unreadable result: '+str(error))
    return row


def aggregate_performance(rows):
    metrics = [r['performance'] for r in rows if r['performance']]
    combined = summarize([dict(performance=m) for m in metrics])
    for key in ('measured_rounds', 'total_rounds', 'counted_rounds', 'partial_rounds'):
        combined[key] = sum(m.get(key, 0) for m in metrics)
    combined['measured_episodes'] = len(metrics)
    combined['total_episodes'] = len(rows)
    combined['partial'] = len(metrics) != len(rows) or any(m.get('partial') for m in metrics)
    return combined


def write_report(directory):
    directory = Path(directory)
    plan = load_plan(directory)
    conditions = {c['condition_id']: c for c in plan['conditions']}
    cases = {c['case_id']: c for c in plan['cases']}
    rows = [episode_result(directory, e, conditions[e['condition_id']], cases[e['case_id']], plan['plan_sha256'])
            for e in plan['episodes']]
    groups = []
    for condition in plan['conditions']:
        for name in dict.fromkeys(c['name'] for c in plan['cases']):
            selected = [r for r in rows if r['condition_id'] == condition['condition_id'] and r['case'] == name]
            counts = {status: sum(r['status'] == status for r in selected) for status in
                      ('success', 'model_failure', 'infrastructure_error', 'cancelled', 'pending', 'incomplete')}
            scored = counts['success']+counts['model_failure']
            groups.append(dict(condition_id=condition['condition_id'], model=condition['model'],
                               blocks=condition['blocks'], case=name, planned=len(selected),
                               attempted=len(selected)-counts['pending'], scored=scored, **counts,
                               success_rate_scored=counts['success']/scored if scored else None,
                               performance=aggregate_performance(selected)))
    report = dict(schema_version=SCHEMA, plan_sha256=plan['plan_sha256'], split=plan['split'],
                  generated_at_utc=utc_now(), planned=len(rows),
                  complete=all(r['status'] not in ('pending', 'incomplete') for r in rows),
                  groups=groups, episodes=rows, note=plan['note'])
    write_json(directory/'summary.json', report)
    columns = ('episode_id', 'case_id', 'condition_id', 'model', 'blocks', 'case', 'scene_seed',
               'generation_seed', 'status', 'goal_success', 'model_declared_done', 'rounds', 'wall_seconds',
               'execution_outcomes', 'execution_seconds', 'evaluation_seconds', 'request_seconds', 'total_seconds',
               'output_tokens', 'native_decode_tokens', 'decode_seconds', 'decode_tokens_per_second',
               'model_load_seconds', 'partial', 'error')
    temporary = directory/'results.csv.tmp'
    with temporary.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            flattened = dict(row, **{key: row['performance'].get(key) for key in columns
                                     if key in row['performance']})
            flattened['execution_outcomes'] = json.dumps(row['execution_outcomes'])
            writer.writerow(flattened)
    temporary.replace(directory/'results.csv')
    text = ['# Entwicklungsvergleich', '', plan['note'], '',
            '| Modell | Blöcke | Aufgabe | Erfolg / bewertet / geplant | Technikfehler | Abbruch | Offen | Ausgabe Token/s |',
            '|---|---:|---|---:|---:|---:|---:|---:|']
    for group in groups:
        rate = group['performance'].get('decode_tokens_per_second')
        speed = f'{rate:.2f}' if rate is not None else '—'
        text.append(f'| {group["model"]} | {group["blocks"]} | {group["case"]} | '
                    f'{group["success"]} / {group["scored"]} / {group["planned"]} | '
                    f'{group["infrastructure_error"]} | {group["cancelled"]} | '
                    f'{group["pending"]+group["incomplete"]} | {speed} |')
    text += ['', 'Modell-/Budgetfehler zählen als Misserfolg. Technikfehler, Abbrüche und offene Versuche '
             'bleiben in den geplanten Fallzahlen sichtbar. Token/s gewichtet native Decode-Schritte mit '
             'ihrer Decode-Zeit; unterschiedliche Modellprofile/Quantisierungen bleiben eigene Bedingungen.',
             '', 'Rohdaten liegen je Episode unverändert neben deren Manifest. Keine automatische Wiederholung '
             'vorhandener Versuche; ein neuer Versuch benötigt einen neuen Plan.', '']
    temporary = directory/'report.md.tmp'
    temporary.write_text('\n'.join(text), encoding='utf-8')
    temporary.replace(directory/'report.md')
    return report
