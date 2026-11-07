import { categoryNames, get, showScene } from './scene.js';

const pageSize = 20;

async function readFile(url, sha256) {
  const response = await fetch(url, { signal: AbortSignal.timeout(25000) });
  if (!response.ok) throw new Error('Hugging Face antwortet mit HTTP ' + response.status + '.');
  const bytes = await response.arrayBuffer();
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
    .map((value) => value.toString(16).padStart(2, '0')).join('');
  if (hash !== sha256) throw new Error('Die Dateiprüfsumme stimmt nicht mit der festgelegten Revision überein.');
  return new TextDecoder().decode(bytes);
}

export function trainingViewer(useCase) {
  let data = [];
  let snapshot;
  let selected;
  let page = 0;
  let state = 'idle';
  const use = get('use-sample');

  function select(row) {
    selected = row;
    get('training-sample').hidden = !row;
    if (!row) return;
    get('sample-id').textContent = row.id;
    get('sample-category').textContent = [categoryNames[row.category], row.subcategory].filter(Boolean).join(' · ');
    get('sample-prompt').textContent = row.user_prompt;
    get('sample-answer').textContent = row.assistant_answer;
    get('sample-answer-label').textContent = row.expected_behavior === 'execute'
      ? 'Referenzprogramm' : 'Referenzantwort';
    get('sample-source').href = snapshot + '/blob/' + row.revision + '/' + row.file;
    showScene(get('sample-scene'), row.scene);
  }

  function render() {
    const search = get('training-search').value.trim().toLowerCase();
    const category = get('training-category').value;
    const matches = data.filter((row) => (!category || row.category === category) && row.search.includes(search));
    const pages = Math.max(1, Math.ceil(matches.length / pageSize));
    page = Math.min(page, pages - 1);
    const rows = matches.slice(page * pageSize, (page + 1) * pageSize);
    if (!rows.includes(selected)) select(rows[0]);
    get('training-count').textContent = matches.length.toLocaleString('de') + ' von '
      + data.length.toLocaleString('de') + ' Einträgen';
    get('training-page').textContent = (page + 1) + ' / ' + pages;
    get('training-prev').disabled = page === 0;
    get('training-next').disabled = page + 1 >= pages;
    const items = rows.map((row) => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      const id = document.createElement('small');
      button.type = 'button';
      button.textContent = row.request;
      button.setAttribute('aria-current', String(row === selected));
      id.textContent = row.id;
      button.append(id);
      button.addEventListener('click', () => {
        get('training-list').querySelector('[aria-current="true"]')?.setAttribute('aria-current', 'false');
        button.setAttribute('aria-current', 'true');
        select(row);
      });
      item.append(button);
      return item;
    });
    get('training-list').replaceChildren(...items);
  }

  async function load() {
    if (state === 'loading' || state === 'ready') return;
    state = 'loading';
    get('training-retry').hidden = true;
    get('training-status').classList.remove('error');
    get('training-status').textContent = 'Lädt die Trainingsdaten …';
    try {
      const response = await fetch('prompt2robo.lock.json', { signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw new Error('Die Datensatzrevision konnte nicht geladen werden.');
      const lock = await response.json();
      snapshot = 'https://huggingface.co/datasets/' + lock.repository;
      const raw = snapshot + '/raw/' + lock.revision + '/';
      const files = Object.entries(lock.files).filter(([file]) => file.endsWith('.jsonl'));
      const versions = [...new Set(files.map(([file]) => file.split('/')[0]))];
      get('dataset-link').href = snapshot + '/tree/' + lock.revision;
      get('dataset-version').textContent = versions.join(', ') + ' · Verifizierte Zeilen aus dem Trainingssplit';
      get('dataset-version').title = lock.revision;
      const batches = await Promise.all(files.map(async ([file, hash]) => {
        const content = await readFile(raw + file, hash);
        return content.split('\n').filter((line) => line.trim()).map((line) => JSON.parse(line))
          .filter((row) => row.split === 'train' && row.verified === true)
          .map((row) => {
            const request = row.user_prompt.slice(row.user_prompt.indexOf('\n') + 1);
            const search = [row.id, row.user_prompt, row.subcategory, categoryNames[row.category]]
              .join(' ').toLowerCase();
            return { ...row, request, search, file, revision: lock.revision, dataset: lock.repository };
          });
      }));
      data = batches.flat();
      for (const key of new Set(data.map((row) => row.category))) {
        get('training-category').add(new Option(categoryNames[key] ?? key, key));
      }
      render();
      get('training-status').textContent = '';
      get('training-content').hidden = false;
      state = 'ready';
    } catch (error) {
      state = 'idle';
      get('training-status').classList.add('error');
      get('training-status').textContent = error instanceof TypeError
        ? 'Die Hugging-Face-Dateien konnten nicht geladen werden.' : error.message;
      get('training-retry').hidden = false;
    }
  }

  for (const event of [['training-search', 'input'], ['training-category', 'change']]) {
    get(event[0]).addEventListener(event[1], () => { page = 0; render(); });
  }
  get('training-prev').addEventListener('click', () => { page -= 1; render(); });
  get('training-next').addEventListener('click', () => { page += 1; render(); });
  get('training-retry').addEventListener('click', load);
  use.addEventListener('click', () => { if (selected) useCase(selected); });
  return { load, setBusy: (busy) => { use.disabled = busy; } };
}
