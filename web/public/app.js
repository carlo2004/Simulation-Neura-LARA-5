import { categoryNames, get, showScene } from './scene.js';
import { trainingViewer } from './training.js';
import { resetLane, showFrame, showMetrics, showModel, showResult } from './run-view.js';

const protocol = 'stacklab-workbench-v1';
const promptFormat = 'prompt2robo-hf-text-v1';
const redOnBlue = 'bse-drop_onto_cube-000';
const replayTitles = {
  [redOnBlue]: 'Rot auf Blau',
  'abs-pyramid_2_layer-000': 'Pyramide',
  'abs-arrange_2d_line-000': 'Viererlinie',
  'abs-stack_cube_on_cube-117': 'Stapel mit Greiferdrehung',
  'bse-drop_height_position-000': 'Würfel aus 10 cm fallen lassen',
  'sexp-v2-rotation_explicit_turn-001': 'Greiferdrehung',
};
const laneNames = { left: 'Basismodell', right: 'Fine-Tuning' };
const lanes = {};
const cases = new Map();
const videos = new Map();
let scene = null;
let connection = null;
let connecting = false;
let active = null;
let report = null;

for (const [side, label] of Object.entries(laneNames)) {
  const node = get('lane-template').content.firstElementChild.cloneNode(true);
  const parts = Object.fromEntries(
    ['lane-title', 'lane-state', 'model', 'model-note', 'model-details', 'model-identity',
      'lane-prompt', 'prompt', 'start', 'frame', 'frame-label', 'clock', 'score', 'rate', 'duration',
      'feedback', 'run-model', 'output', 'run-facts', 'program', 'action-log', 'action-title', 'actions',
      'raw-log', 'raw', 'state-log', 'states'].map((name) => [name, node.querySelector('.' + name)]));
  parts['lane-title'].textContent = label;
  parts.prompt.setAttribute('aria-label', 'Prompt für ' + label);
  parts.prompt.addEventListener('input', controls);
  parts.model.setAttribute('aria-label', 'Modell für ' + label);
  parts.model.add(new Option('Runner verbinden', ''));
  parts.model.addEventListener('change', () => {
    showModel(parts, connection?.models.get(parts.model.value));
    resetLane(parts);
    controls();
  });
  parts.start.textContent = label + ' testen';
  parts.start.addEventListener('click', () => run('single', side));
  get('lanes').append(node);
  lanes[side] = parts;
}

function showTab(training) {
  get('compare').hidden = training;
  get('training').hidden = !training;
  get('show-compare').setAttribute('aria-pressed', String(!training));
  get('show-training').setAttribute('aria-pressed', String(training));
  if (training) viewer.load();
}

const viewer = trainingViewer((row) => {
  if (active) return;
  get('scene-search').value = '';
  get('scene-filter').value = '';
  cases.set(row.id, row);
  selectScene(row);
  showTab(false);
  get('task').focus();
});
get('show-compare').addEventListener('click', () => showTab(false));
get('show-training').addEventListener('click', () => showTab(true));

get('code-input').value = `def run(robot):
    x, y, z = robot.get_gripper_position()
    robot.move_to(x, y, z + 0.05)
`;

function notify(text, error = false) {
  const notice = get('notice');
  notice.textContent = text;
  notice.hidden = !text;
  notice.classList.toggle('error', error);
}

function prompt(side) {
  const value = get('shared').checked ? get('shared-prompt').value : lanes[side].prompt.value;
  return value.trim() || scene?.request?.trim() || '';
}

function canRun() {
  if (!connection || !scene) return false;
  if (scene.revision && (scene.revision !== connection.revision || scene.dataset !== connection.dataset)) return false;
  return connection.cases.has(scene.id) || (scene.file && connection.trainingCases);
}

function controls() {
  const busy = Boolean(active);
  const ready = canRun() && !busy && !connecting;
  const left = lanes.left.model.value;
  const right = lanes.right.model.value;
  const shared = get('shared').checked;
  const original = scene?.request?.trim();
  const changed = Boolean(scene && (prompt('left') !== original || prompt('right') !== original));
  get('run').disabled = !(ready && left && right && left !== right);
  get('reference').disabled = !ready;
  get('run-code').disabled = !ready;
  get('stop').hidden = !busy;
  get('export').disabled = !report || busy;
  get('report-id').textContent = report?.id ? 'Lauf ' + report.id : '';
  get('shared-field').hidden = !shared;
  get('shared-prompt').disabled = busy || !scene;
  get('shared').disabled = busy || !scene;
  get('reset-prompt').hidden = !changed;
  get('reset-prompt').disabled = busy;
  get('scoring').textContent = !scene ? '' : connection && !canRun() ? 'Szene und Runner benötigen dieselbe Datensatzrevision.'
    : changed ? 'Eigene Prompts ohne Zielprüfung' : 'Datensatzprompt mit Zielprüfung';
  get('task').disabled = busy || ![...get('task').options].some((item) => item.value);
  for (const id of ['scene-search', 'scene-filter', 'code-input', 'import']) get(id).disabled = busy;
  get('connect').disabled = connecting || busy;
  viewer.setBusy(busy);
  for (const lane of Object.values(lanes)) {
    lane.start.disabled = !ready || !lane.model.value;
    lane.model.disabled = busy || !connection?.models.size;
    lane['lane-prompt'].hidden = shared;
    lane.prompt.disabled = busy || !scene;
  }
}

function resetPrompts() {
  get('shared-prompt').value = scene?.request ?? '';
  for (const lane of Object.values(lanes)) lane.prompt.value = get('shared-prompt').value;
  controls();
}

get('shared').addEventListener('change', () => {
  if (get('shared').checked) get('shared-prompt').value = lanes.left.prompt.value;
  else for (const lane of Object.values(lanes)) lane.prompt.value = get('shared-prompt').value;
  controls();
});
get('shared-prompt').addEventListener('input', controls);
get('reset-prompt').addEventListener('click', resetPrompts);

function sceneName(item) {
  return replayTitles[item.id] || item.request?.trim() || item.id;
}

function listScenes() {
  const search = get('scene-search').value.trim().toLowerCase();
  const filter = get('scene-filter').value;
  const items = [...cases.values()].filter((item) => {
    if (filter === 'video' && !videoFor(item)) return false;
    if (filter && filter !== 'video' && item.split !== filter) return false;
    return [sceneName(item), item.id, item.subcategory, categoryNames[item.category], item.request]
      .join(' ').toLowerCase().includes(search);
  });
  const task = get('task');
  task.replaceChildren(...items.map((item) => new Option(sceneName(item), item.id)));
  if (!items.some((item) => item.id === scene?.id)) {
    task.prepend(new Option(items.length ? 'Szene auswählen' : 'Keine Szenen gefunden', ''));
  }
  task.value = items.some((item) => item.id === scene?.id) ? scene.id : '';
  controls();
}

function videoFor(item) {
  const video = videos.get(item.id);
  if (video && item.revision === video.revision && item.dataset === video.dataset) return video.url;
}

function selectScene(item, reset = true) {
  if (!item) return;
  scene = item;
  const split = item.split === 'train' ? 'Training' : item.split === 'eval_v4' ? 'Evaluation · eval_v4' : item.split;
  get('scene-id').textContent = [split, item.id].filter(Boolean).join(' · ');
  get('scene-request').textContent = item.request;
  showScene(get('scene-preview'), item.scene);
  const recording = get('recording');
  const player = get('proof-player');
  const source = videoFor(item);
  recording.hidden = !source;
  if (source !== player.getAttribute('src')) {
    recording.open = false;
    player.pause();
    player.removeAttribute('src');
    if (source) player.src = source;
    player.load();
  }
  if (reset) {
    resetPrompts();
    for (const lane of Object.values(lanes)) resetLane(lane);
    notify('');
  }
  listScenes();
}

get('task').addEventListener('change', () => {
  const item = cases.get(get('task').value);
  if (item) selectScene(item);
});
get('scene-search').addEventListener('input', listScenes);
get('scene-filter').addEventListener('change', listScenes);

async function replays() {
  const response = await checked(await fetch('proof/manifest.json'));
  const manifest = await response.json();
  if (manifest.video_playback_speed > 1) {
    get('recording').querySelector('summary').textContent = 'Referenzvideo · ' + manifest.video_playback_speed + '×';
  }
  for (const item of manifest.results) {
    if (!/^[\w-]+\.mp4$/.test(item.video ?? '')) continue;
    const origin = { dataset: manifest.dataset, revision: manifest.revision };
    videos.set(item.id, { ...origin, url: 'proof/' + item.video });
    if (!cases.has(item.id)) cases.set(item.id, { ...item, ...origin, scene: item.initial_state });
  }
  if (scene) selectScene(scene, false);
  else if (cases.has(redOnBlue)) selectScene(cases.get(redOnBlue));
  else listScenes();
}

function runnerOrigin(value) {
  const url = new URL(value.trim() || location.origin);
  const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback))
      || url.pathname !== '/' || url.search || url.hash || url.username || url.password) {
    throw new Error('Die Runner-URL muss eine HTTPS-Adresse oder eine lokale Loopback-Adresse sein.');
  }
  return url.origin;
}

async function checked(response) {
  if (response.ok) return response;
  const body = await response.json().catch(() => ({}));
  throw new Error(body.error || 'Runner antwortet mit HTTP ' + response.status + '.');
}

get('connect-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (active || connecting) return;
  const errorLine = get('connection-error');
  errorLine.hidden = true;
  connecting = true;
  controls();
  try {
    const url = runnerOrigin(get('runner').value);
    const key = get('key').value.trim();
    const response = await checked(await fetch(url + '/api/catalog', {
      headers: { Authorization: 'Bearer ' + key }, cache: 'no-store', redirect: 'error',
      signal: AbortSignal.timeout(8000),
    }));
    if (!response.headers.get('content-type')?.startsWith('application/json')) {
      throw new Error('Kein Runner-Katalog empfangen. Bei ngrok zuerst „Visit Site“ öffnen.');
    }
    const data = await response.json();
    if (data.protocol !== protocol || !Array.isArray(data.models) || !Array.isArray(data.cases)) {
      throw new Error('Unter dieser Adresse läuft kein kompatibler LARA Runner.');
    }
    if (data.lane_prompts !== true || (data.models.length && data.prompt_format !== promptFormat)) {
      throw new Error('Für das Prompt2Robo-Format bitte das Colab-Repo aktualisieren und den Runner neu starten.');
    }
    connection = { url, key, dataset: data.dataset, revision: data.revision, trainingCases: data.training_cases,
      cases: new Set(data.cases.map((item) => item.id)), models: new Map(data.models.map((item) => [item.id, item])) };
    get('key').value = '';
    get('connection').open = false;
    get('connection-status').textContent = 'Runner verbunden';
    for (const [index, side] of Object.keys(lanes).entries()) {
      const lane = lanes[side];
      lane.model.replaceChildren(...data.models.map(({ id, label }) => new Option(label, id)));
      if (!lane.model.options.length) lane.model.add(new Option('Keine Modelle im Runner', ''));
      const preferred = side === 'left' ? 'base' : 'tuned';
      if (connection.models.has(preferred)) lane.model.value = preferred;
      else lane.model.selectedIndex = Math.min(index, lane.model.options.length - 1);
      showModel(lane, connection.models.get(lane.model.value));
      resetLane(lane);
    }
    for (const item of data.cases) {
      if (!cases.get(item.id)?.file) cases.set(item.id, { ...item, dataset: data.dataset, revision: data.revision });
    }
    selectScene((scene && cases.get(scene.id)) || cases.get(redOnBlue) || cases.values().next().value, !scene);
  } catch (error) {
    errorLine.textContent = error instanceof TypeError || error.name === 'TimeoutError'
      ? 'Runner nicht erreichbar. Prüfe URL und Tunnel. Bei ngrok gegebenenfalls zuerst „Visit Site“ öffnen.'
      : error.message;
    errorLine.hidden = false;
  } finally {
    connecting = false;
    controls();
  }
});

function streamEvent(event, frames) {
  if (event.event === 'start') {
    report = event.report;
    controls();
    return;
  }
  if (event.event === 'complete') {
    report = event.report;
    for (const [side, value] of Object.entries(frames)) {
      if (report.results[side]) report.results[side].frame = value;
    }
    return;
  }
  if (!report || !Object.hasOwn(lanes, event.lane)) return;
  const side = event.lane;
  const lane = lanes[side];
  const partial = report.results[side] ??= {
    model_identity: ['single', 'compare'].includes(report.mode) ? connection.models.get(lane.model.value) : null,
    label: report.mode === 'reference' ? 'Referenz' : 'Eigener Code',
    instruction: prompt(side), actions: [], interrupted: true,
  };
  switch (event.event) {
    case 'phase':
      lane['lane-state'].textContent = event.phase === 'generating' ? 'Generiert …' : 'Simuliert …';
      break;
    case 'program':
      Object.assign(partial, { code: event.code, message: event.message, metrics: event.metrics });
      showMetrics(lane, event.metrics);
      break;
    case 'action': {
      const { event: _event, lane: _lane, ...action } = event;
      partial.actions.push(action);
      if (action.phase === 'start') lane['lane-state'].textContent = action.method;
      break;
    }
    case 'frame':
      frames[side] = { jpeg: event.jpeg, time_s: event.time_s };
      showFrame(lane, frames[side]);
      break;
    case 'result':
      report.results[side] = event.result;
      showResult(lane, event.result);
      if (frames[side]) showFrame(lane, frames[side], 'Endbild');
      break;
  }
}

async function run(mode, side = 'left') {
  if (!canRun() || active || connecting) return;
  const controller = new AbortController();
  const payload = { task: scene.id, mode };
  if (mode === 'compare') {
    payload.left = lanes.left.model.value;
    payload.right = lanes.right.model.value;
    payload.prompts = { left: prompt('left'), right: prompt('right') };
  } else if (mode === 'single') {
    Object.assign(payload, { side, model: lanes[side].model.value, prompt: prompt(side) });
  } else if (mode === 'code') {
    Object.assign(payload, { code: get('code-input').value, prompt: prompt(side) });
  }
  report = null;
  active = controller;
  const testing = mode === 'compare' ? ['left', 'right'] : [side];
  for (const key of testing) {
    resetLane(lanes[key]);
    lanes[key]['lane-state'].textContent = 'Wartet …';
  }
  controls();
  notify('');
  const frames = {};
  try {
    const response = await checked(await fetch(connection.url + '/api/run', {
      method: 'POST', redirect: 'error', signal: controller.signal,
      headers: { Authorization: 'Bearer ' + connection.key, 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }));
    if (!response.headers.get('content-type')?.startsWith('application/x-ndjson')) {
      throw new Error('Der Runner liefert keinen Live-Datenstrom.');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let rest = '';
    let complete = false;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const lines = (rest + decoder.decode(value, { stream: true })).split('\n');
      rest = lines.pop();
      if (rest.length > 2 * 1024 * 1024) throw new Error('Live-Datensatz zu groß.');
      for (const line of lines) {
        if (!line) continue;
        const event = JSON.parse(line);
        streamEvent(event, frames);
        if (event.event === 'complete') complete = true;
      }
    }
    if (!complete) throw new Error('Verbindung endete vor dem Ergebnis.');
    if (mode === 'compare' && !report.same_prompt) notify('Die Modelle erhielten unterschiedliche Prompts.');
  } catch (error) {
    if (report) {
      report.status = 'interrupted';
      report.stream_error = controller.signal.aborted ? 'Live-Ansicht beendet' : error.message;
    }
    for (const key of testing) {
      const result = report?.results[key];
      if (result) {
        if (frames[key]) result.frame = frames[key];
        showResult(lanes[key], result);
      } else lanes[key]['lane-state'].textContent = 'Ohne Ergebnis';
    }
    notify(controller.signal.aborted ? 'Live-Ansicht beendet.' : error.message, !controller.signal.aborted);
    controller.abort();
  } finally {
    active = null;
    controls();
  }
}

get('run').addEventListener('click', () => run('compare'));
get('reference').addEventListener('click', () => run('reference'));
get('run-code').addEventListener('click', () => run('code'));
get('stop').addEventListener('click', () => active?.abort());
get('export').addEventListener('click', () => {
  if (!report) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + '\n'], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'lara-' + (String(report.id ?? '').replace(/[^a-zA-Z0-9-]/g, '') || 'lauf') + '.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
get('import').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 4 * 1024 * 1024) throw new Error('Laufbericht zu groß.');
    const value = JSON.parse(await file.text());
    if (value?.protocol !== protocol || typeof value.task !== 'string'
        || !value.results || typeof value.results !== 'object') throw new Error('Kein LARA-Workbench-Bericht.');
    const item = cases.get(value.task);
    if (item && (!item.revision || item.revision === value.revision)) {
      selectScene(item);
      get('shared').checked = value.same_prompt !== false;
      if (value.instruction) get('shared-prompt').value = value.instruction;
      for (const [side, lane] of Object.entries(lanes)) {
        lane.prompt.value = value.results[side]?.instruction || lane.prompt.value;
      }
    }
    report = value;
    for (const [side, lane] of Object.entries(lanes)) {
      resetLane(lane);
      if (report.results[side]) showResult(lane, report.results[side], true);
    }
    notify('Geöffneter Lauf · ' + report.task + (report.status === 'interrupted' ? ' · unterbrochen' : ''));
  } catch (error) {
    notify(error.message, true);
  } finally {
    event.target.value = '';
    controls();
  }
});

controls();
replays().catch(() => notify('Die Referenzszenen konnten nicht geladen werden.', true));
