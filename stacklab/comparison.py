"""Descriptive development rankings; never declare a winner from missing trials."""
import csv
import math
from pathlib import Path
from statistics import median

from stacklab.config import write_json


def wilson(success, total):
    if not total:
        return None
    z = 1.959963984540054
    proportion = success/total
    scale = 1+z*z/total
    centre = (proportion+z*z/(2*total))/scale
    radius = z*math.sqrt(proportion*(1-proportion)/total+z*z/(4*total*total))/scale
    return [max(0., centre-radius), min(1., centre+radius)]


def ranking(report):
    from stacklab.experiments import aggregate_performance
    groups = {}
    for row in report['episodes']:
        key = (row['model'], row['blocks'])
        groups.setdefault(key, []).append(row)
    result = []
    for (model, blocks), rows in groups.items():
        counts = {status: sum(r['status'] == status for r in rows) for status in
                  ('success', 'model_failure', 'infrastructure_error', 'cancelled', 'pending', 'incomplete')}
        scored = counts['success']+counts['model_failure']
        complete = counts['pending']+counts['incomplete'] == 0
        durations = [r['wall_seconds'] for r in rows if r.get('wall_seconds') is not None]
        result.append(dict(model=model, blocks=blocks, planned=len(rows), scored=scored, complete=complete,
            **counts, success_rate_scored=counts['success']/scored if scored else None,
            success_rate_planned=counts['success']/len(rows) if complete else None,
            success_interval_scored_95=wilson(counts['success'], scored),
            median_episode_seconds=median(durations) if durations else None,
            parsing_error_episodes=sum('parsing_error' in r['execution_outcomes'] for r in rows),
            validation_error_episodes=sum('validation_error' in r['execution_outcomes'] for r in rows),
            execution_error_episodes=sum('execution_error' in r['execution_outcomes'] for r in rows),
            performance=aggregate_performance(rows)))
    # Speed is deliberately not a hidden tie-breaker for task quality.
    return sorted(result, key=lambda r: (-r['success']/r['planned'], r['model'], r['blocks']))


def number(value):
    return f'{value:.2f}' if value is not None else '—'


def write_ranking(directory, report, plan):
    directory = Path(directory)
    rows = ranking(report)
    gpus = plan.get('remote', {}).get('identity', plan['environment']).get('gpus', [])
    result = dict(plan_sha256=plan['plan_sha256'], comparison_sha256=plan.get('comparison_sha256'),
                  gpus=gpus, complete=report['complete'], models=rows,
                  note='Provisional observed results. No unique/statistically established winner. '
                       'Wilson intervals assume independent Bernoulli trials; this is a small fixed development suite.')
    write_json(directory/'ranking.json', result)
    text = ['# Vorläufiger Modellvergleich', '',
            'GPU: '+(', '.join(g['name'] for g in gpus) or 'keine GPU erfasst'), '',
            'Gleiche Fälle und Budgets; Qualität und Geschwindigkeit bleiben getrennt. '
            'Reihenfolge nach erfolgreichen/geplanten Episoden, Gleichstände bleiben Gleichstände. '
            'Unvollständige Versuchsreihen haben noch keine endgültige Erfolgsquote.', '',
            '| Modell | Blöcke | Erfolg / bewertet / geplant | Technik | Offen | Ausgabe Token/s | Erstes Token s | Median Episode s |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        performance = row['performance']
        text.append(f'| {row["model"]} | {row["blocks"]} | '
                    f'{row["success"]} / {row["scored"]} / {row["planned"]} | '
                    f'{row["infrastructure_error"]} | {row["pending"]+row["incomplete"]} | '
                    f'{number(performance.get("decode_tokens_per_second"))} | '
                    f'{number(performance.get("first_token_seconds_mean"))} | '
                    f'{number(row["median_episode_seconds"])} |')
    text += ['', 'Technikausfälle sind keine nachgewiesenen Modellfehler und werden separat ausgewiesen. '
             'Die Modellquote verwendet nur bewertete Episoden; die vollständige End-to-End-Quote '
             'behält alle geplanten Versuche im Nenner. Details pro Aufgabe stehen in report.md. '
             'Die 20 Stabilitätsmessungen zählen als eine Episode.', '',
             'Bei zehn Episoden pro Modell ist dies eine Vorauswahl. Kleine Unterschiede belegen keinen '
             'generellen Sieger. Modelle haben ihre dokumentierten Sampling-/Thinking- und '
             'Quantisierungsprofile; das Ergebnis gilt für diese vollständigen Konfigurationen.', '']
    (directory/'ranking.md').write_text('\n'.join(text), encoding='utf-8')
    return result


def compare_experiments(directories, output):
    from stacklab.experiments import load_plan, write_report
    plans = [load_plan(path) for path in directories]
    if len(plans) < 2:
        raise ValueError('Compare at least two experiment directories')
    hashes = {p.get('comparison_sha256') for p in plans}
    if None in hashes or len(hashes) != 1:
        raise ValueError('Suites differ in code, cases, seeds, profiles or budgets; do not pool them')
    if len({p['plan_sha256'] for p in plans}) != len(plans):
        raise ValueError('The same experiment cannot be compared with itself')
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Choose a new comparison output directory')
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for directory, plan in zip(directories, plans):
        report = write_report(directory)
        gpus = plan.get('remote', {}).get('identity', plan['environment']).get('gpus', [])
        for row in ranking(report):
            rows.append(dict(plan_sha256=plan['plan_sha256'], gpu_names='; '.join(g['name'] for g in gpus),
                             **row))
    write_json(output/'comparison.json', dict(comparison_sha256=plans[0]['comparison_sha256'], rows=rows))
    fields = ['gpu_names', 'model', 'blocks', 'success', 'scored', 'planned', 'complete',
              'success_rate_scored', 'success_rate_planned', 'infrastructure_error', 'cancelled',
              'pending', 'incomplete', 'decode_tokens_per_second', 'first_token_seconds_mean',
              'median_episode_seconds', 'plan_sha256']
    with (output/'comparison.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(dict(row, **row['performance']) for row in rows)
    text = ['# Vergleich der GPU-Läufe', '',
            'Verglichen werden identische Fallpläne und Modellkonfigurationen. '
            'GPU-Leistung und physischer Aufgabenerfolg werden getrennt bewertet.', '',
            '| GPU | Modell | Blöcke | Erfolg / bewertet / geplant | Technik | Ausgabe Token/s | Median Episode s |',
            '|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        text.append(f'| {row["gpu_names"]} | {row["model"]} | {row["blocks"]} | '
                    f'{row["success"]} / {row["scored"]} / {row["planned"]} | {row["infrastructure_error"]} | '
                    f'{number(row["performance"].get("decode_tokens_per_second"))} | '
                    f'{number(row["median_episode_seconds"])} |')
    text += ['', 'Kleine Pilotstichprobe; kein automatischer statistischer Sieger. '
             'Native Tokenraten verwenden passende Token-/Zeit-Summen. '
             'Modell-Tokens sind zwischen unterschiedlichen Tokenizern keine einheitliche Arbeitsmenge.', '']
    (output/'comparison.md').write_text('\n'.join(text), encoding='utf-8')
    return rows
