const stages = {
  generation: 'Generierung', response: 'Antwortformat', simulation: 'Simulationsprozess',
  setup: 'Szenenaufbau', policy: 'Python-Prüfung', execution: 'Roboterbefehl',
  goal_check: 'Zielprüfung', text_check: 'Antwortprüfung',
};
const jpegPattern = /^[A-Za-z0-9+/]+={0,2}$/;

function facts(target, entries) {
  target.replaceChildren(...entries.filter(([, value]) => value != null && value !== '').flatMap(([name, value]) => {
    const key = document.createElement('dt');
    const item = document.createElement('dd');
    key.textContent = name;
    item.textContent = value;
    return [key, item];
  }));
}

export function modelName(model) {
  if (model?.weights?.file) {
    return [model.weights.file, model.adapter?.file].filter(Boolean).join(' + ');
  }
  return model?.api_model || model?.label || '';
}

export function showModel(lane, model) {
  lane['model-note'].textContent = !model ? '' : model.weights?.file ? modelName(model) :
    model.api_model ? 'API-ID ' + model.api_model + ' · GGUF-Kennung fehlt' : 'GGUF-Kennung fehlt. Runner aktualisieren.';
  lane['model-details'].hidden = !model?.api_model;
  facts(lane['model-identity'], [
    ['API-ID', model?.api_model],
    ['GGUF SHA-256', model?.weights?.sha256],
    ['LoRA SHA-256', model?.adapter?.sha256],
  ]);
}

export function showFrame(lane, value, label = 'Live') {
  if (typeof value?.jpeg !== 'string' || value.jpeg.length > 1000000 || !jpegPattern.test(value.jpeg)) return;
  lane.frame.src = 'data:image/jpeg;base64,' + value.jpeg;
  lane['frame-label'].textContent = label;
  lane.clock.hidden = !Number.isFinite(value.time_s);
  if (!lane.clock.hidden) lane.clock.textContent = value.time_s.toFixed(2) + ' s Simulationszeit';
}

export function resetLane(lane) {
  lane['lane-state'].textContent = '';
  lane.frame.src = 'lara-start.webp';
  lane['frame-label'].textContent = 'Beispielbild';
  lane.clock.hidden = true;
  lane.score.textContent = lane.rate.textContent = lane.duration.textContent = lane.simulation.textContent = '—';
  lane.rate.removeAttribute('title');
  lane.score.className = 'score';
  lane.feedback.hidden = true;
  lane['run-model'].hidden = true;
  lane.output.hidden = true;
  lane.output.open = false;
}

export function showMetrics(lane, metrics = {}) {
  const native = metrics?.decode_tokens_per_second;
  const effective = metrics?.effective_tokens_per_second;
  const rate = native ?? effective;
  lane.rate.textContent = Number.isFinite(rate) ? rate.toFixed(1) : '—';
  lane.rate.title = Number.isFinite(native) ? 'Ausgabetokens pro Sekunde während der Generierung'
    : Number.isFinite(effective) ? 'Ausgabetokens pro Sekunde über die gesamte Anfrage' : 'Kein Zähler verfügbar';
  lane.duration.textContent = Number.isFinite(metrics?.request_seconds)
    ? metrics.request_seconds.toFixed(2) + ' s' : '—';
}

export function showResult(lane, result, archived = false) {
  const check = result.check;
  const reasons = Array.isArray(check?.reasons) ? check.reasons.join('\n') : '';
  const stage = result.error_stage || check?.stage;
  const rejected = ['setup', 'policy', 'execution'].includes(stage) && Boolean(reasons);
  const error = Boolean(result.error || rejected || (check?.passed === null && reasons));
  const feedback = [result.message, result.error || reasons].filter(Boolean).join('\n');
  lane['lane-state'].textContent = error ? 'Fehler · ' + (stages[stage] ?? 'Ausführung')
    : result.interrupted ? 'Unterbrochen' : 'Abgeschlossen';
  lane.score.textContent = error ? 'Fehler' : check?.passed === true ? 'Bestanden'
    : check?.passed === false ? 'Verfehlt' : result.scored === false ? 'Ohne Prüfung' : '—';
  lane.score.className = 'score' + (error || check?.passed === false ? ' fail' : check?.passed === true ? ' pass' : '');
  lane.feedback.hidden = !feedback;
  lane.feedback.textContent = feedback;
  lane.feedback.classList.toggle('error', error);
  showMetrics(lane, result.metrics);
  lane.simulation.textContent = Number.isFinite(result.simulation_wall_seconds)
    ? result.simulation_wall_seconds.toFixed(2) + ' s' : '—';
  lane.output.hidden = false;
  if (error) lane.output.open = true;
  const model = result.model_identity;
  lane['run-model'].hidden = !archived && Boolean(result.model || model);
  lane['run-model'].textContent = (archived ? 'Bericht · ' : '') + (modelName(model) || result.label || 'Modell unbekannt');
  facts(lane['run-facts'], [
    ['Modell im Lauf', modelName(model) || result.label],
    ['Serverantwort', result.actual_model],
    ['GGUF SHA-256', model?.weights?.sha256],
    ['LoRA SHA-256', model?.adapter?.sha256],
    ['Prompt', result.user_prompt || result.instruction],
    ['Phase', stages[stage]],
    ['Fehlertyp', result.error_type],
    ['Generierungsende', result.finish_reason],
    ['Armtempo', Number.isFinite(check?.speed_mm_s) ? check.speed_mm_s + ' mm/s' : null],
  ]);
  lane.program.hidden = !result.code;
  lane.program.textContent = result.code ?? '';
  lane['raw-log'].hidden = !result.raw || result.raw === result.code;
  lane.raw.textContent = result.raw ?? '';
  lane['state-log'].hidden = !check?.initial_state && !check?.final_state;
  lane.states.textContent = JSON.stringify({ Start: check?.initial_state, Ende: check?.final_state }, null, 2);

  const actionSteps = new Map();
  for (const action of Array.isArray(result.actions) ? result.actions : []) {
    if (action && Number.isInteger(action.step)) actionSteps.set(action.step, action);
  }
  lane['action-log'].hidden = !actionSteps.size;
  lane['action-title'].textContent = 'Roboterbefehle (' + actionSteps.size + ')';
  lane.actions.replaceChildren(...[...actionSteps.values()].map((action) => {
    const item = document.createElement('li');
    const args = Array.isArray(action.args) ? action.args.map((value) => JSON.stringify(value)).join(', ') : '';
    const time = Number.isFinite(action.time_s) ? action.time_s.toFixed(2) + ' s · ' : '';
    item.textContent = time + action.method + '(' + args + ')' +
      (action.error ? ' · ' + action.error : action.phase === 'start' ? ' · offen' :
        action.result?.length ? ' → ' + JSON.stringify(action.result) : '');
    item.classList.toggle('fail', action.status === 'error');
    return item;
  }));
  if (archived && result.frame) showFrame(lane, result.frame, 'Endbild');
}
