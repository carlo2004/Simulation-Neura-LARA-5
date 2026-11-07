const get = (id) => document.getElementById(id);
const protocol = 'stacklab-workbench-v1';
const redOnBlue = 'bse-drop_onto_cube-000';
const replayTitles = {
  [redOnBlue]: 'Rot auf Blau',
  'abs-pyramid_2_layer-000': 'Pyramide',
  'abs-arrange_2d_line-000': 'Viererlinie',
  'abs-stack_cube_on_cube-117': 'Stapel mit Drehung',
  'bse-drop_height_position-000': 'Fall aus 10 cm',
  'sexp-v2-rotation_explicit_turn-001': 'Greiferdrehung',
};
const laneNames = { left: 'Basismodell', right: 'Fine-Tuning' };
const lanes = {};
let cases = [];
let catalog = null;
let connection = null;
let active = null;
let report = null;

function option(text, value) {
  return new Option(text, value);
}

for (const [side, label] of Object.entries(laneNames)) {
  const node = get('lane-template').content.firstElementChild.cloneNode(true);
  const parts = Object.fromEntries(
    ['lane-index', 'lane-title', 'lane-state', 'model', 'frame', 'frame-label', 'clock', 'score',
      'rate', 'duration', 'feedback', 'program', 'output'].map((name) => [name, node.querySelector('.' + name)]));
  parts['lane-index'].textContent = side === 'left' ? 'A' : 'B';
  parts['lane-title'].textContent = label;
  parts.model.add(option('Runner verbinden', ''));
  parts.model.addEventListener('change', controls);
  get('lanes').append(node);
  lanes[side] = parts;
}

get('code-input').value = `def run(robot):
    x, y, z = robot.get_gripper_position()
    robot.move_to(x, y, z + 0.05)
`;

function notify(text, error = false) {
  get('notice').textContent = text;
  get('notice').classList.toggle('error', error);
}

function controls() {
  const ready = Boolean(connection && get('task').value && !active);
  const left = lanes.left.model.value;
  const right = lanes.right.model.value;
  get('run').disabled = !(ready && left && right && left !== right);
  get('reference').disabled = !ready;
  get('run-code').disabled = !ready;
  get('stop').hidden = !active;
  get('export').disabled = !report || Boolean(active);
  get('task').disabled = Boolean(active);
  get('prompt').disabled = Boolean(active);
  get('code-input').disabled = Boolean(active);
  get('connect').disabled = Boolean(active);
  get('import').disabled = Boolean(active);
  for (const lane of Object.values(lanes)) lane.model.disabled = !ready || !catalog.models.length;
}

function showCase() {
  const selected = cases.find((item) => item.id === get('task').value);
  get('task-text').textContent = selected?.request ?? 'Wähle eine Aufgabe.';
  const objects = Object.entries(selected?.scene?.objects ?? {});
  get('scene').hidden = objects.length === 0;
  get('objects').replaceChildren(...objects.map(([id, object]) => {
    const item = document.createElement('li');
    item.textContent = '#' + id + ' ' + object.color + '  [' + object.position.join(', ') + '] m';
    return item;
  }));
  controls();
}

function setCases(items) {
  const previous = get('task').value;
  cases = items;
  get('task').replaceChildren(...items.map((item) => option(
    (replayTitles[item.id] ?? item.id) + ' · ' + item.split, item.id)));
  if (items.some((item) => item.id === previous)) get('task').value = previous;
  else if (items.some((item) => item.id === redOnBlue)) get('task').value = redOnBlue;
  showCase();
}

function showConnection() {
  const visible = get('connection').open;
  get('connection-button').setAttribute('aria-expanded', String(visible));
}

get('connection-button').addEventListener('click', () => {
  get('connection').open = !get('connection').open;
  showConnection();
  if (get('connection').open) get('runner').focus();
});
get('connection').addEventListener('toggle', showConnection);
get('task').addEventListener('change', showCase);

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
  get('connect').disabled = true;
  try {
    const url = runnerOrigin(get('runner').value);
    const key = get('key').value.trim();
    const response = await checked(await fetch(url + '/api/catalog', {
      headers: { Authorization: 'Bearer ' + key }, cache: 'no-store', redirect: 'error',
      signal: AbortSignal.timeout(8000),
    }));
    const data = await response.json();
    if (data.protocol !== protocol || !Array.isArray(data.models) || !Array.isArray(data.cases)) {
      throw new Error('Unter dieser Adresse läuft kein kompatibler LARA Runner.');
    }
    connection = { url, key };
    catalog = data;
    get('key').value = '';
    get('connection').open = false;
    get('connection-status').textContent = 'Runner verbunden';
    get('connection-button').classList.add('connected');
    for (const [index, side] of Object.keys(lanes).entries()) {
      const model = lanes[side].model;
      model.replaceChildren(...data.models.map(({ id, label }) => option(label, id)));
      if (!model.options.length) model.add(option('Keine Modelle eingetragen', ''));
      model.selectedIndex = Math.min(index, model.options.length - 1);
    }
    setCases(data.cases);
    notify(data.models.length >= 2 ? 'Aufgabe und zwei Modelle wählen, dann Vergleich starten.'
      : 'Runner verbunden. Referenzläufe und Python-Konsole sind verfügbar. Für den Vergleich braucht der Runner zwei Modelle.');
  } catch (error) {
    notify(error instanceof TypeError ? 'Runner nicht erreichbar. Prüfe die URL, das Teamnetz und die erlaubte Browser-Origin.' : error.message, true);
  } finally {
    controls();
  }
});

const jpegPattern = /^[A-Za-z0-9+/]+={0,2}$/;
function frame(side, jpeg, time, label = 'LIVE · LARA 5') {
  if (typeof jpeg !== 'string' || jpeg.length > 180000 || !jpegPattern.test(jpeg)) return;
  lanes[side].frame.src = 'data:image/jpeg;base64,' + jpeg;
  lanes[side]['frame-label'].textContent = label;
  lanes[side].clock.textContent = Number.isFinite(time) ? 'T = ' + time.toFixed(2) + ' s' : 'T = —';
}

function resetLanes() {
  for (const lane of Object.values(lanes)) {
    lane['lane-state'].textContent = 'Bereit';
    lane.frame.src = 'lara-start.webp';
    lane['frame-label'].textContent = 'REFERENZANSICHT';
    lane.clock.textContent = 'T = —';
    lane.score.textContent = lane.rate.textContent = lane.duration.textContent = '—';
    lane.score.className = 'score';
    lane.program.textContent = '';
    lane.feedback.textContent = 'Ergebnisse erscheinen hier.';
  }
}

function showMetrics(lane, metrics = {}) {
  const native = metrics?.decode_tokens_per_second;
  const effective = metrics?.effective_tokens_per_second;
  const rate = native ?? effective;
  lane.rate.textContent = Number.isFinite(rate) ? rate.toFixed(1) : '—';
  lane.rate.title = Number.isFinite(native) ? 'Native Decode-Tokens pro Sekunde'
    : Number.isFinite(effective) ? 'Ausgabetokens pro Sekunde über die gesamte Anfrage' : 'Kein Zähler verfügbar';
  lane.duration.textContent = Number.isFinite(metrics?.request_seconds)
    ? metrics.request_seconds.toFixed(2) + ' s' : '—';
}

function showResult(side, result, archived = false) {
  if (!result || typeof result !== 'object') return;
  const lane = lanes[side];
  const passed = result.check?.passed;
  const reasons = Array.isArray(result.check?.reasons) ? result.check.reasons.join(' · ') : '';
  const error = result.error || (passed === null && reasons);
  lane['lane-state'].textContent = String(result.label || laneNames[side]);
  lane.score.textContent = passed === true ? 'Bestanden' : passed === false ? 'Verfehlt'
    : error ? 'Fehler' : passed === null ? 'Frei' : '—';
  lane.score.className = 'score' + (passed === true ? ' pass' : passed === false || error ? ' fail' : '');
  showMetrics(lane, result.metrics);
  lane.program.textContent = String(result.code || result.raw || '');
  lane.feedback.textContent = [result.actual_model, result.message, result.error || reasons].filter(Boolean).join(' · ')
    || (passed === true ? 'Zielbedingungen erfüllt.' : 'Ausführung abgeschlossen.');
  if (archived && result.frame) frame(side, result.frame.jpeg, result.frame.time_s, 'ERGEBNIS · LARA 5');
}

function streamEvent(event, frames) {
  if (event.event === 'complete') {
    report = event.report;
    for (const [side, value] of Object.entries(frames)) {
      if (report.results[side]) report.results[side].frame = value;
    }
    return;
  }
  if (!Object.hasOwn(lanes, event.lane)) return;
  const side = event.lane;
  const lane = lanes[side];
  switch (event.event) {
    case 'phase':
      lane['lane-state'].textContent = event.phase === 'generating' ? 'Generiert …' : 'Führt aus …';
      break;
    case 'metrics':
      showMetrics(lane, event.metrics);
      break;
    case 'program':
      lane.program.textContent = event.code || '';
      lane.feedback.textContent = event.message || 'Programm empfangen.';
      showMetrics(lane, event.metrics);
      break;
    case 'action':
      if (event.phase === 'start') lane['lane-state'].textContent = event.method;
      break;
    case 'frame':
      frames[side] = { jpeg: event.jpeg, time_s: event.time_s };
      frame(side, event.jpeg, event.time_s);
      break;
    case 'result':
      showResult(side, event.result);
      break;
  }
}

async function run(mode) {
  if (!connection || active) return;
  const controller = new AbortController();
  const task = get('task').value;
  const prompt = get('prompt').value;
  const payload = { task, mode, prompt };
  if (mode === 'compare') Object.assign(payload, { left: lanes.left.model.value, right: lanes.right.model.value });
  if (mode === 'code') payload.code = get('code-input').value;
  report = null;
  active = controller;
  resetLanes();
  controls();
  notify(mode === 'compare' ? 'Zwei Läufe auf derselben Startszene. A startet zuerst, danach B.' : 'LARA 5 wird gestartet.');
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
    const frames = {};
    let rest = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const lines = (rest + decoder.decode(value, { stream: true })).split('\n');
      rest = lines.pop();
      if (rest.length > 512000) throw new Error('Live-Datensatz zu groß.');
      for (const line of lines) if (line) streamEvent(JSON.parse(line), frames);
    }
    if (!report) throw new Error('Verbindung endete vor dem Ergebnis.');
    notify(report.scored ? 'Lauf abgeschlossen. Programm, Messwerte und Zielprüfung können als JSON gespeichert werden.'
      : 'Freier Lauf abgeschlossen. Zustandsdaten und Programm können als JSON gespeichert werden.');
  } catch (error) {
    notify(controller.signal.aborted ? 'Live-Ansicht abgebrochen.' : error.message, !controller.signal.aborted);
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
  link.download = 'lara-vergleich.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
get('import').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 2 * 1024 * 1024) throw new Error('Bericht zu groß.');
    const value = JSON.parse(await file.text());
    if (value?.protocol !== protocol || typeof value.task !== 'string'
        || !value.results || typeof value.results !== 'object') throw new Error('Kein LARA-Workbench-Bericht.');
    resetLanes();
    report = value;
    for (const side of Object.keys(lanes)) showResult(side, report.results[side], true);
    notify('Bericht geöffnet · ' + report.task);
  } catch (error) {
    notify(error.message, true);
  } finally {
    event.target.value = '';
    controls();
  }
});

async function replays() {
  const response = await checked(await fetch('proof/manifest.json'));
  const manifest = await response.json();
  const items = manifest.results.filter((item) => /^[\w-]+\.mp4$/.test(item.video ?? ''));
  if (!connection) setCases(items.map((item) => ({ ...item, scene: item.initial_state })));
  const buttons = items.map((item) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = replayTitles[item.id] || item.id;
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => pick(item, true));
    return button;
  });
  function pick(item, play) {
    if (!item) return;
    const player = get('proof-player');
    player.src = 'proof/' + item.video;
    for (const [index, button] of buttons.entries()) button.setAttribute('aria-pressed', String(items[index] === item));
    if (play) player.play().catch(() => {});
  }
  get('replays').replaceChildren(...buttons);
  pick(items.find((item) => item.id === redOnBlue) || items[0], false);
}

replays().catch(() => notify('Die Replay-Bibliothek konnte nicht geladen werden.', true));
