export const get = (id) => document.getElementById(id);
export const categoryNames = {
  basic_single_explicit: 'Grundbewegungen',
  single_explicit: 'Einzelaufgaben',
  abstract: 'Zusammengesetzte Aufgaben',
  edge_cases: 'Grenzfälle',
};

const colors = {
  red: ['#c83c3e', 'Rot'], blue: ['#315ea9', 'Blau'], green: ['#2a774c', 'Grün'],
  yellow: ['#e9b83c', 'Gelb'], purple: ['#79559e', 'Violett'], orange: ['#d98331', 'Orange'],
  white: ['#fff', 'Weiß'], black: ['#252b31', 'Schwarz'], pink: ['#d989a9', 'Rosa'],
  brown: ['#9b633d', 'Braun'], gray: ['#959ba2', 'Grau'], grey: ['#959ba2', 'Grau'],
  cyan: ['#38b0bb', 'Cyan'],
};

function svgNode(name, attrs, text = '') {
  const node = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text) node.textContent = text;
  return node;
}

function validPosition(value) {
  return Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
}

export function showScene(target, scene) {
  const cubes = Object.entries(scene?.objects ?? {})
    .filter(([, cube]) => validPosition(cube?.position));
  const gripper = scene?.gripper;
  const tcp = validPosition(gripper?.position) ? gripper.position : null;
  if (!cubes.length && !tcp) {
    target.replaceChildren();
    target.hidden = true;
    return;
  }
  target.hidden = false;

  const points = cubes.map(([, cube]) => cube.position);
  if (tcp) points.push(tcp);
  const near = Math.min(0, ...points.map(([x]) => x - .04));
  const far = Math.max(.8, ...points.map(([x]) => x + .04));
  const halfWidth = Math.max(.4, ...points.map(([, y]) => Math.abs(y) + .04));
  const view = svgNode('svg', { viewBox: '0 0 212 204', role: 'img', 'aria-label': 'Draufsicht der Startszene' });
  const scale = Math.min(150 / (far - near), 156 / (2 * halfWidth));
  const width = 2 * halfWidth * scale;
  const height = (far - near) * scale;
  const left = (212 - width) / 2;
  const top = (200 - height) / 2;
  const plot = ([x, y]) => [106 - y * scale, top + (far - x) * scale];
  view.append(svgNode('rect', { x: left, y: top, width, height, fill: '#f5f7f8', stroke: '#b9c3cb' }));
  for (const fraction of [.25, .5, .75]) {
    const x = left + width * fraction;
    const y = top + height * fraction;
    view.append(svgNode('path', { d: `M${x} ${top}v${height} M${left} ${y}h${width}`, stroke: '#dce2e6' }));
  }
  view.append(
    svgNode('text', { x: 106, y: top - 7, 'text-anchor': 'middle', fill: '#43515c', 'font-size': 11 }, '+x vorn'),
    svgNode('text', { x: 26, y: top + height + 15, fill: '#43515c', 'font-size': 11 }, '+y links'),
    svgNode('text', { x: 186, y: top + height + 15, 'text-anchor': 'end', fill: '#43515c', 'font-size': 11 }, '−y rechts'),
  );
  const [rx, ry] = plot([0, 0]);
  view.append(svgNode('circle', { cx: rx, cy: ry, r: 3, fill: '#5e6974' }));

  const groups = [];
  for (const [id, cube] of cubes) {
    const [x, y] = plot(cube.position);
    const group = groups.find((item) => Math.hypot(item.x - x, item.y - y) < 4);
    if (group) group.cubes.push([id, cube]);
    else groups.push({ x, y, cubes: [[id, cube]] });
  }
  for (const { x, y, cubes: stack } of groups) {
    stack.sort((a, b) => a[1].position[2] - b[1].position[2]);
    const [topId, topCube] = stack.at(-1);
    view.append(svgNode('rect', { x: x - 7, y: y - 7, width: 14, height: 14, rx: 2,
      fill: colors[topCube.color]?.[0] ?? '#87929b', stroke: '#32404c' }));
    view.append(svgNode('text', { x, y: y - 10, 'text-anchor': 'middle', fill: '#202832', 'font-size': 11 },
      '#' + topId + (stack.length > 1 ? ' (' + stack.length + ')' : '')));
  }
  if (tcp) {
    const [x, y] = plot(tcp);
    view.append(svgNode('circle', { cx: x, cy: y, r: 5, fill: 'none', stroke: '#202832', 'stroke-width': 1.4 }));
  }

  const figure = document.createElement('figure');
  const caption = document.createElement('figcaption');
  caption.textContent = ['Draufsicht', tcp && '○ Greifer', groups.length < cubes.length && '(n) Würfel im Stapel']
    .filter(Boolean).join(' · ');
  figure.append(view, caption);
  const list = document.createElement('ul');
  list.className = 'positions';
  list.setAttribute('aria-label', 'Positionen x, y und z in Metern');
  function position(label, point, state = '') {
    const item = document.createElement('li');
    const name = document.createElement('strong');
    const xyz = document.createElement('code');
    name.textContent = label;
    xyz.textContent = '(' + point.join(', ') + ') m';
    item.append(name, xyz);
    if (state) item.append(' · ' + state);
    list.append(item);
  }
  for (const [id, cube] of cubes) position('#' + id + ' ' + (colors[cube.color]?.[1] ?? cube.color), cube.position);
  if (tcp) {
    const state = [Number.isFinite(gripper.angle_deg) ? gripper.angle_deg + '°' : '',
      typeof gripper.is_open === 'boolean' ? (gripper.is_open ? 'offen' : 'geschlossen') : ''];
    position('Greifer', tcp, state.filter(Boolean).join(' · '));
  }
  target.replaceChildren(figure, list);
}
