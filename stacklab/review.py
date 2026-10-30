"""Offline review of measured evidence. No web service, model judge or UI dependency."""
import html
import json
from pathlib import Path
import shlex

from stacklab.comparison import number
from stacklab.experiments import load_plan, write_report


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def escaped(value):
    return html.escape(str(value), quote=True)


def details(title, value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return '<details><summary>'+escaped(title)+'</summary><pre>'+escaped(text)+'</pre></details>'


def write_review(directory, *, report=None, include_reasoning=False, videos=0):
    directory = Path(directory).resolve()
    plan = load_plan(directory)
    if report is None or 'episodes' not in report:
        report = write_report(directory)
    if type(videos) is not int or videos < 0:
        raise ValueError('videos must be a nonnegative count')
    if videos:
        from stacklab.sim.recording import render_replay
        candidates = [r for r in report['episodes'] if
                      (directory/r['episode_id']/'motion.jsonl').is_file() and
                      not (directory/r['episode_id']/'simulation.mp4').exists()]
        # A reproducible review sample; it never changes the score or hides other trials.
        selected = []
        for success in (False, True):
            item = next((r for r in candidates if r['goal_success'] is success), None)
            if item:
                selected.append(item)
        remaining = sorted((r for r in candidates if r not in selected),
                           key=lambda r: -(r.get('wall_seconds') or 0))
        for row in (selected+remaining)[:videos]:
            render_replay(directory/row['episode_id'])
    conditions = {c['condition_id']: c for c in plan['conditions']}
    cases = {c['case_id']: c for c in plan['cases']}
    labels = dict(success='Erfolgreich', model_failure='Ziel nicht erreicht', infrastructure_error='Technikfehler',
                  cancelled='Abgebrochen', pending='Noch offen', incomplete='Unvollständig')
    gpu = ', '.join(g['name'] for g in plan.get('remote', {}).get('identity', plan['environment']).get('gpus', []))
    succeeded = sum(r['status'] == 'success' for r in report['episodes'])
    tech = sum(r['status'] == 'infrastructure_error' for r in report['episodes'])
    body = ['<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
            '<title>Stack Lab · Versuchssichtung</title><style>',
            'body{margin:0;background:#f3f5f7;color:#202d3c;font:16px system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:28px}',
            'h1{font-size:30px;margin:8px 0}h2{font-size:19px}header,p{line-height:1.55}.muted{color:#596777}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}',
            '.stat,article{background:white;border:1px solid #dbe1e8;border-radius:12px;padding:18px}.stat{flex:1;min-width:150px}.stat strong{display:block;font-size:25px}',
            'article{margin:16px 0}.toolbar{display:flex;gap:12px;position:sticky;top:0;padding:12px 0;background:#f3f5f7;z-index:1}',
            'input,select{font:inherit;border:1px solid #bbc5d1;border-radius:7px;padding:10px;background:white}input{flex:1;min-width:120px}',
            '.badge{display:inline-block;padding:4px 10px;border-radius:20px;background:#eef1f5;font-size:13px;font-weight:650}',
            '.success .badge{background:#dcf3e8;color:#11653e}.model_failure .badge,.infrastructure_error .badge{background:#fff0d5;color:#8a4a00}',
            '.metrics{display:flex;gap:18px;flex-wrap:wrap;color:#415167;font-size:14px;margin:15px 0}summary{cursor:pointer;padding:10px 0;font-weight:600}',
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;border-radius:7px;padding:13px;font:13px/1.5 ui-monospace,monospace;max-height:420px;overflow:auto}',
            'video{display:block;max-width:640px;width:100%;background:#172330;border-radius:8px}a{color:#215bb8}.block{border-top:1px solid #e4e8ed;margin-top:14px}code{font-size:13px}',
            '[hidden]{display:none!important}@media(max-width:600px){main{padding:15px}.toolbar{flex-wrap:wrap}h1{font-size:25px}}',
            '</style><main><header><div class="muted">STACK LAB / ENTWICKLUNGSPILOT</div><h1>Versuche verstehen</h1>',
            '<p>Auftrag, tatsächliche Modellantwort und gemessener Erfolg bleiben sichtbar. '
            'Die Seite ist eine lokale Momentaufnahme; sie benötigt keinen laufenden Colab-Server.</p>',
            '<p class="muted">GPU: '+escaped(gpu or 'keine GPU erfasst')+' · '
            '<a href="ranking.md">Modellvergleich</a> · <a href="results.csv">CSV</a> · <a href="manifest.json">Versuchsbedingungen</a></p></header>',
            f'<div class="stats"><div class="stat"><strong>{succeeded} / {report["planned"]}</strong>physisch erfolgreich</div>'
            f'<div class="stat"><strong>{tech}</strong>technische Ausfälle</div><div class="stat"><strong>'+
            ('Abgeschlossen' if report['complete'] else 'Noch unvollständig')+'</strong>Stand dieser Momentaufnahme</div></div>',
            '<div class="toolbar"><input id="search" aria-label="Versuche durchsuchen" placeholder="Auftrag, Fehler oder Code suchen …">',
            '<select id="model" aria-label="Modell wählen"><option value="">Alle Modelle</option>']
    for model in dict.fromkeys(r['model'] for r in report['episodes']):
        body.append('<option value="'+escaped(model)+'">'+escaped(model)+'</option>')
    body += ['</select></div><p class="muted">Automatisch: Ziel, Kontakte, Stabilität und API-Fehler. '
             'Händisch: Fehlerursachen und Grenzfälle prüfen. Videos laden erst beim Abspielen; '
             'gespeicherter Denktext wird nur mit --include-reasoning eingeblendet.</p>']
    for index, row in enumerate(report['episodes'], 1):
        path = directory/row['episode_id']
        root = read_json(path/'result.json')
        execution = root.get('execution') or read_json(path/'execution.json')
        condition, case = conditions[row['condition_id']], cases[row['case_id']]
        perf = row['performance']
        body += ['<article class="'+escaped(row['status'])+'" data-model="'+escaped(row['model'])+'">',
                 '<span class="badge">'+escaped(labels.get(row['status'], row['status']))+'</span>',
                 '<h2>'+escaped(f'{index:02d} · {row["model"]} · {row["case"]}')+'</h2>',
                 '<p><strong>Auftrag:</strong> '+escaped(root.get('instruction') or case['instruction'])+'</p>',
                 '<div class="metrics"><span>'+escaped(number(perf.get('decode_tokens_per_second')))+' Token/s</span>'
                 '<span>Erstes Token: '+escaped(number(perf.get('first_token_seconds_mean')))+' s</span>'
                 '<span>Episode: '+escaped(number(row.get('wall_seconds')))+' s</span>'
                 '<span>Blöcke: '+str(row['rounds'])+' / '+str(row['blocks'])+'</span></div>']
        if row.get('error'):
            body.append(details('Fehler / Rückmeldung', row['error']))
        if row.get('recording_error'):
            body.append(details('Bewegungsaufzeichnung unvollständig', row['recording_error']))
        video = path/'simulation.mp4'
        if video.is_file():
            body.append('<video controls preload="none" src="'+escaped(row['episode_id']+'/simulation.mp4')+'"></video>')
            replay = read_json(path/'simulation.replay.json')
            if replay:
                body.append('<p class="muted">Aus tatsächlich gespeicherten Posen · '+str(replay['fps'])+
                            ' Hz · '+('vollständig' if replay['complete'] else 'Teilaufzeichnung')+
                            ' · keine neue Physikprüfung.</p>')
        elif (path/'motion.jsonl').is_file():
            from stacklab.paths import ROOT
            relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else Path('PFAD_ZUM_LAUF')/row['episode_id']
            command = shlex.join(['python', '-m', 'stacklab', 'experiment', 'replay', str(relative)])
            body.append(details('Video bei Bedarf lokal erzeugen', command))
        for item in execution.get('rounds', []):
            block = path/'episode'/('round_'+str(item['round']).zfill(2))
            response = read_json(block/'response.json')
            message = (response.get('choices') or [{}])[0].get('message', {})
            generation = item.get('generation', {}).get('performance', {})
            body.append('<div class="block"><h2>Programmblock '+str(item['round'])+'</h2>')
            body.append('<p class="muted">Anfrage: '+number(generation.get('total_seconds'))+
                        ' s · Prompt: '+number(generation.get('prompt_seconds'))+
                        ' s · Ausgabe inkl. Denktext: '+number(generation.get('decode_seconds'))+
                        ' s · Ausführung: '+number(item.get('execution_seconds'))+
                        ' s · Physikprüfung: '+number(item.get('evaluation_seconds'))+' s</p>')
            body.append(details('Antwort des Modells', message.get('content') or '(keine Antwort gespeichert)'))
            code = block/'generated.py'
            if code.is_file():
                body.append(details('Tatsächlich ausgeführter / geprüfter Code', code.read_text(encoding='utf-8')))
            if include_reasoning:
                body.append(details('Vom Modell ausgegebener Denktext · keine verifizierte Erklärung',
                                    message.get('reasoning_content') or '(kein separater Denktext geliefert)'))
            body.append(details('Gemessene Rückmeldung', item.get('feedback', {})))
            body.append(details('An das Modell gesendet', read_json(block/'request.json')))
            body.append('</div>')
        body.append(details('Fall und Aufzeichnungsmodus', dict(episode_id=row['episode_id'],
                    scene_seed=row['scene_seed'], generation_seed=row['generation_seed'],
                    recording=condition.get('recording', 'full'), motion_fps=condition.get('motion_fps', 0),
                    visual_meshes=condition.get('visual_meshes', True),
                    measured_evaluation=execution.get('evaluation'))))
        body.append('</article>')
    body += ['<p class="muted">Eine kleine feste Entwicklungsprobe. Die Modell-Fertigmeldung ist kein Erfolgskriterium. '
             '20 Stabilitätsproben zählen als eine Episode; die Videos dienen der Sichtung.</p></main>',
             '<script>const search=document.getElementById("search"),model=document.getElementById("model");'
             'let timer;function filter(){document.querySelectorAll("article").forEach(a=>{'
             'a.hidden=(model.value&&a.dataset.model!==model.value)||!a.textContent.toLowerCase().includes(search.value.toLowerCase());});}'
             'search.addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(filter,150)});'
             'model.addEventListener("change",filter);document.querySelectorAll("video").forEach(v=>v.addEventListener("play",()=>{'
             'document.querySelectorAll("video").forEach(other=>{if(other!==v)other.pause()})}));</script></html>']
    output = directory/'review.html'
    temporary = directory/'review.html.tmp'
    temporary.write_text('\n'.join(body), encoding='utf-8')
    temporary.replace(output)
    return output
