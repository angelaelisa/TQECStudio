'use strict';
// Also register the icon in pages served from an existing template cache.
if (!document.querySelector('link[rel="icon"]')) {
  const icon = document.createElement('link');
  icon.rel = 'icon';
  icon.type = 'image/svg+xml';
  icon.href = new URL('favicon.svg', document.currentScript.src).href;
  document.head.append(icon);
}
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="studio-token"]').content;
const ns = 'http://www.w3.org/2000/svg';
let graph = {
    name: 'Untitled graph',
    cubes: [],
    pipes: []
  },
  selected = null,
  selectedPipe = null,
  kind = 'ZXO';
let history = [],
  future = [],
  surfaces = [],
  revision = null,
  overlay = null,
  mode = 'iso',
  angle = Math.PI / 4,
  busy = false,
  activeJob = null,
  generation = 0;
let paletteRequest = 0;
let elevation = Math.PI / 6,
  zoom = 1,
  orbit = null,
  suppressCanvasClick = false;
let drag = null,
  projectPoint = null,
  buildMode = 'pipe',
  pendingPipe = null;
const key = p => p.join(',');
const pipeKey = p => [key(p.u), key(p.v)].sort().join('|');
const clone = x => JSON.parse(JSON.stringify(x));

function message(text, error = false) {
  $('message').textContent = text;
  $('message').classList.toggle('error', error);
}
async function api(path, data, form = false) {
  const opts = data === undefined ? {} : {
    method: 'POST',
    headers: {
      'X-Studio-Token': token
    },
    body: form ? data : JSON.stringify(data)
  };
  if (data !== undefined && !form) opts.headers['Content-Type'] = 'application/json';
  const res = await fetch(path, opts);
  const result = await res.json();
  if (!res.ok) throw Error(result.error || 'The request failed.');
  return result;
}

function saveDraft() {
  try {
    localStorage.setItem('tqec-studio-draft-v1', JSON.stringify({
      schema: 'tqec-studio/1',
      graph
    }));
    $('autosave').textContent = 'Draft saved in this browser. Save a portable copy before closing.';
  } catch {
    $('autosave').textContent = 'Browser storage unavailable. Use Save project.';
  }
}

function invalidate() {
  generation++;
  if (window.markSimulationStale) window.markSimulationStale();
  surfaces = [];
  revision = null;
  overlay = null;
  $('surface-list').replaceChildren();
  $('surface-info').textContent = 'Graph changed. Validate and find surfaces again.';
  if (!$('results').hidden) $('job').textContent = 'Previous result: graph changed. Compile again for an up-to-date circuit.';
}

function commit(next, record = true) {
  if (record) {
    history.push(clone(graph));
    if (history.length > 60) history.shift();
    future = [];
  }
  graph = next;
  invalidate();
  if (!graph.cubes.some(c => key(c.position) === selected)) selected = null;
  if (!graph.pipes.some(p => pipeKey(p) === selectedPipe)) selectedPipe = null;
  saveDraft();
  render();
}
async function change(next, validateEdit = true) {
  if (busy) return false;
  busy = true;
  try {
    const result = await api('/api/graph', {
      ...next,
      validate_edit: validateEdit
    });
    commit(result.graph);
    message('Graph updated. Find surfaces to check the complete computation.');
    return true;
  } catch (e) {
    message(e.message, true);
    return false;
  } finally {
    busy = false;
  }
}

function node(tag, attrs = {}, text) {
  const e = document.createElementNS(ns, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}
// Display units match TQEC's default COLLADA geometry. Logical neighbours
// remain one coordinate apart: the visual pipe gap adds no circuit time.
const CUBE_SIZE = 1,
  PIPE_LENGTH = 2,
  BLOCK_PITCH = CUBE_SIZE + PIPE_LENGTH;
const world = p => p.map(n => n * BLOCK_PITCH);

function pipeEndpoints(u, v, kind) {
  const axis = kind.indexOf('O'),
    start = world(u),
    end = world(v);
  start[axis] += CUBE_SIZE / 2;
  end[axis] -= CUBE_SIZE / 2;
  return [start, end];
}
// Four walls, no end caps: the O axis remains open at both ends.
function pipeWalls(u, v, kind, radius = CUBE_SIZE / 2) {
  const axis = kind.indexOf('O'),
    transverse = [0, 1, 2].filter(a => a !== axis);
  const hadamard = kind.endsWith('H'),
    segments = hadamard ? [
      [0, .46, false],
      [.46, .54, null],
      [.54, 1, true]
    ] : [
      [0, 1, false]
    ];
  const faces = [];
  for (const [start, end, flipped] of segments)
    for (const wallAxis of transverse)
      for (const sign of [-1, 1]) {
        const other = transverse.find(a => a !== wallAxis);
        const points = [
          [start, -1],
          [end, -1],
          [end, 1],
          [start, 1]
        ].map(([t, side]) => {
          const p = u.map((n, i) => n + (v[i] - n) * t);
          p[wallAxis] += sign * radius;
          p[other] += side * radius;
          return p;
        });
        const basis = flipped === null ? 'H' : flipped ? (kind[wallAxis] === 'X' ? 'Z' : 'X') : kind[wallAxis];
        faces.push({
          points,
          axis: wallAxis,
          sign,
          basis
        });
      }
  return faces;
}

function wallColour(basis, axis, sign, view = [1, 1, 1]) {
  const outside = sign * view[axis] >= 0;
  return basis === 'H' ? (outside ? '#fff48a' : '#b9ac47') : basis === 'X' ? (outside ? '#ef8587' : '#82474e') : (outside ? '#7892ed' : '#3d507f');
}

function cubeColour(basis, axis) {
  if (basis === 'Y') return axis === 0 ? '#347846' : axis === 2 ? '#58b66e' : '#60bd75';
  // Gallery convention: x-normal side shaded, y-normal front bright, z on top.
  return basis === 'X' ? (axis === 0 ? '#9c4e50' : axis === 2 ? '#ed7778' : '#f47d7e') : (axis === 0 ? '#455d9b' : axis === 2 ? '#6988eb' : '#708ff3');
}

function cubeFaces(pos, kind, signs = [1, 1, 1], axes = [0, 1, 2]) {
  return axes.map(axis => {
    const sign = signs[axis],
      others = [0, 1, 2].filter(i => i !== axis);
    const points = [
      [-1, -1],
      [1, -1],
      [1, 1],
      [-1, 1]
    ].map(([a, b]) => {
      const p = [...pos];
      const half = i => kind === 'Y' && i === 2 ? .25 : CUBE_SIZE / 2;
      p[axis] += sign * half(axis);
      p[others[0]] += a * half(others[0]);
      p[others[1]] += b * half(others[1]);
      return p;
    });
    return {
      points,
      axis,
      sign,
      basis: kind === 'Y' ? 'Y' : kind[axis]
    };
  });
}

function cameraDirection() {
  return mode === 'layer' ? [0, 0, 1] : [Math.sin(angle) * Math.cos(elevation), Math.cos(angle) * Math.cos(elevation), Math.sin(elevation)];
}

function cameraProjection([x, y, z]) {
  return mode === 'layer' ? [x, -y] : [x * Math.cos(angle) - y * Math.sin(angle), (x * Math.sin(angle) + y * Math.cos(angle)) * Math.sin(elevation) - z * Math.cos(elevation)];
}

function cameraDepth(points) {
  const camera = cameraDirection();
  return points.reduce((sum, p) => sum + p.reduce((n, v, i) => n + v * camera[i], 0), 0) / points.length;
}
let paletteOrientation = '';

function refreshPaletteOrientation() {
  const orientation = [mode, angle, elevation].join(',');
  if (orientation === paletteOrientation) return;
  paletteOrientation = orientation;
  // Replace previews only; retain filtered choices, selection, and drag handlers.
  for (const icon of $('palette').querySelectorAll('svg[data-kind]')) icon.replaceWith(icon.classList.contains('cube-icon') ? cubeIcon(icon.dataset.kind) : pipeIcon(icon.dataset.kind));
}

function cubeIcon(kind) {
  const icon = node('svg', {
    viewBox: '0 0 100 92',
    class: 'cube-icon',
    'data-kind': kind,
    'aria-hidden': 'true'
  });
  const project = p => {
    const [x, y] = cameraProjection(p);
    return [50 + x * 43, 46 + y * 43];
  };
  const faces = cubeFaces([0, 0, 0], kind, cameraDirection().map(n => n >= 0 ? 1 : -1), mode === 'layer' ? [2] : [0, 1, 2]).sort((a, b) => cameraDepth(a.points) - cameraDepth(b.points));
  for (const f of faces) icon.append(node('polygon', {
    points: f.points.map(p => project(p).join(',')).join(' '),
    fill: kind === 'P' ? '#e5e9eb' : cubeColour(f.basis, f.axis),
    'fill-opacity': kind === 'P' ? .25 : 1,
    stroke: kind === 'P' ? '#81939b' : '#1e2730',
    'stroke-dasharray': kind === 'P' ? '3 2' : '',
    'stroke-width': 1.1,
    'stroke-linejoin': 'round'
  }));
  const [x, y] = project([0, 0, kind === 'Y' ? .25 : .5]);
  icon.append(node('text', {
    x,
    y: y + 3,
    'text-anchor': 'middle',
    fill: '#303b48',
    'font-size': 10,
    'font-weight': 600
  }, kind === 'P' ? 'Open' : kind));
  return icon;
}

function pipeIcon(kind) {
  const icon = node('svg', {
    viewBox: '0 0 100 76',
    class: 'pipe-icon',
    'data-kind': kind,
    'aria-hidden': 'true'
  });
  const axis = kind.indexOf('O'),
    u = [0, 0, 0],
    v = [0, 0, 0];
  u[axis] = -PIPE_LENGTH / 2;
  v[axis] = PIPE_LENGTH / 2;
  const project = p => {
    const [x, y] = cameraProjection(p);
    return [50 + x * 25, 38 + y * 25];
  };
  const faces = pipeWalls(u, v, kind).sort((a, b) => cameraDepth(a.points) - cameraDepth(b.points));
  for (const f of faces) icon.append(node('polygon', {
    points: f.points.map(p => project(p).join(',')).join(' '),
    fill: wallColour(f.basis, f.axis, f.sign, cameraDirection()),
    stroke: '#263544',
    'stroke-width': .8,
    'stroke-linejoin': 'round'
  }));
  return icon;
}

function cubeDisplayPosition(position, kind) {
  const pos = world(position);
  if (kind === 'Y') {
    const pipe = graph.pipes.find(p => key(p.u) === key(position) || key(p.v) === key(position));
    pos[2] += pipe && key(pipe.u) === key(position) ? .25 : -.25;
  }
  return pos;
}

function cubeIndices() {
  return new Map([...graph.cubes].sort((a, b) => a.position[0] - b.position[0] || a.position[1] - b.position[1] || a.position[2] - b.position[2]).map((c, i) => [key(c.position), i]));
}

function render() {
  const indices = cubeIndices();
  $('name').value = graph.name;
  $('graph-title').textContent = graph.name;
  const ports = graph.cubes.filter(c => ['P', 'PORT'].includes(c.kind)).length;
  $('counts').textContent = `${graph.cubes.length-ports} cubes · ${ports} ports · ${graph.pipes.length} pipes`;
  $('undo').disabled = !history.length;
  $('redo').disabled = !future.length;
  const list = $('cube-list');
  list.replaceChildren(new Option('Select a cube', ''));
  for (const c of graph.cubes) list.add(new Option(`#${indices.get(key(c.position))} · ${c.kind} · (${c.position.join(', ')})${c.label?' · '+c.label:''}`, key(c.position)));
  list.value = selected || '';
  const activePipe = graph.pipes.find(p => pipeKey(p) === selectedPipe);
  $('pipe-selection').hidden = !activePipe;
  $('selected-pipe-info').textContent = activePipe ? `${activePipe.kind} · (${activePipe.u.join(', ')}) → (${activePipe.v.join(', ')})` : '';
  const cube = graph.cubes.find(c => key(c.position) === selected);
  $('edit-controls').hidden = !cube;
  $('selection').textContent = cube ? `#${indices.get(key(cube.position))} · ${cube.kind} at (${cube.position.join(', ')})${cube.label?' · '+cube.label:''}` : 'Select a cube in the canvas.';
  $('pipe-list').style.height = '';
  $('pipe-list').style.paddingBottom = '0px';
  $('pipe-list').replaceChildren();
  graph.pipes.forEach((p, i) => {
    const row = document.createElement('div');
    row.className = 'pipe-row';
    const text = document.createElement('span');
    text.textContent = `(${p.u}) → (${p.v}) · ${p.kind}`;
    const b = document.createElement('button');
    b.textContent = '×';
    b.setAttribute('aria-label', `Delete pipe ${i+1}`);
    b.onclick = () => deletePipe(pipeKey(p));
    const h = document.createElement('button');
    h.textContent = p.kind.endsWith('H') ? 'Remove H' : 'Add H';
    h.className = p.kind.endsWith('H') ? 'hadamard-active' : '';
    h.setAttribute('aria-label', `${p.kind.endsWith('H')?'Remove':'Add'} Hadamard on pipe ${i+1}`);
    h.onclick = () => setHadamard(p, !p.kind.endsWith('H'));
    text.className = 'pipe-select';
    text.setAttribute('role', 'button');
    text.tabIndex = 0;
    text.setAttribute('aria-label', `Select pipe ${i+1}`);
    text.onclick = () => selectPipe(p);
    text.onkeydown = e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        selectPipe(p);
      }
    };
    row.classList.toggle('selected', pipeKey(p) === selectedPipe);
    row.append(text, h, b);
    $('pipe-list').append(row);
  });
  draw();
  if (buildMode !== 'pipe') palette();
}
async function setHadamard(pipe, enabled) {
  if (busy) return;
  busy = true;
  try {
    const result = await api('/api/pipe-hadamard', {
      graph,
      u: pipe.u,
      v: pipe.v,
      enabled
    });
    commit(result.graph);
    message(enabled ? 'Hadamard added. The yellow band swaps X and Z walls.' : 'Hadamard removed.');
  } catch (e) {
    message(e.message, true);
  } finally {
    busy = false;
  }
}

function scrollToSelectedPipe() {
  const list = $('pipe-list'),
    row = list.querySelector('.pipe-row.selected');
  if (!row) return;
  // Add scroll room below the last rows so any selection can align at the top.
  const height = list.clientHeight;
  list.style.height = height + 'px';
  list.style.paddingBottom = '0px';
  const offset = row.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
  const room = Math.max(0, offset + list.clientHeight - list.scrollHeight);
  list.style.paddingBottom = room + 'px';
  list.scrollTop = offset;
}

function selectPipe(pipe) {
  selectedPipe = pipeKey(pipe);
  selected = null;
  panel('design');
  render();
  scrollToSelectedPipe();
  message('Pipe selected. Press X, Y or Z to extend; hold Shift for the negative direction.');
}
async function deletePipe(id) {
  if (busy || !id) return;
  const pipe = graph.pipes.find(p => pipeKey(p) === id);
  if (!pipe) return;
  const next = clone(graph);
  next.pipes = next.pipes.filter(p => pipeKey(p) !== id);
  // Remove only dangling ports made empty by this deletion, retaining real cubes.
  const endpoints = new Set([key(pipe.u), key(pipe.v)]);
  next.cubes = next.cubes.filter(c => !(['P', 'PORT'].includes(c.kind) && endpoints.has(key(c.position)) && !next.pipes.some(p => key(p.u) === key(c.position) || key(p.v) === key(c.position))));
  if (await change(next, false)) message('Pipe deleted. Undo restores it.');
}

function setupPipeSelection() {
  $('canvas').setAttribute('aria-label', 'Interactive graph. Click a cube or pipe to select it; use the inspector to edit or delete.');
  const box = document.createElement('section');
  box.id = 'pipe-selection';
  box.hidden = true;
  const title = document.createElement('h3');
  title.textContent = 'Selected pipe';
  const info = document.createElement('p');
  info.id = 'selected-pipe-info';
  info.className = 'muted';
  const remove = document.createElement('button');
  remove.id = 'delete-selected-pipe';
  remove.className = 'danger';
  remove.textContent = 'Delete selected pipe';
  remove.onclick = () => deletePipe(selectedPipe);
  box.append(title, info, remove);
  $('panel-design').prepend(box);
}
setupPipeSelection();
async function replaceSelectedCube(kind) {
  if (busy || !selected || !kind) return;
  busy = true;
  try {
    const result = await api('/api/replace-cube', {
      graph,
      position: selected.split(',').map(Number),
      kind
    });
    commit(result.graph);
    message(kind === 'P' ? 'Cube reopened as a port. Its pipe is preserved.' : 'Cube replaced. All connected pipes are preserved.');
  } catch (e) {
    message(e.message, true);
  } finally {
    busy = false;
  }
}

function select(p) {
  selectedPipe = null;
  selected = key(p);
  $('build-mode').value = 'cube';
  $('build-mode').onchange();
  render();
}

function drawAxes(svg, projectDirection) {
  // Fixed-size orientation guide uses the same projection as the graph.
  const guide = node('g', {
    'aria-label': 'Coordinate axes: x and y are space; z is time',
    role: 'img',
    'pointer-events': 'none',
    class: 'axis-guide'
  });
  guide.append(node('rect', {
    x: 610,
    y: 14,
    width: 174,
    height: 164,
    rx: 12,
    fill: '#ffffff',
    'fill-opacity': .93,
    stroke: '#dce3e6'
  }));
  guide.append(node('text', {
    x: 624,
    y: 35,
    fill: '#526b77',
    'font-size': 11,
    'font-weight': 600
  }, 'Coordinate axes'));
  const origin = [697, 103],
    colours = ['#ad651b', '#147d70', '#7754ae'];
  for (const axis of [0, 1, 2]) {
    const vector = [0, 0, 0];
    vector[axis] = 1;
    const [dx, dy] = projectDirection(vector), length = Math.hypot(dx, dy), colour = colours[axis], label = ['x', 'y', 'z'][axis];
    if (length < .05) {
      guide.append(node('circle', {
        cx: origin[0],
        cy: origin[1],
        r: 7,
        fill: 'white',
        stroke: colour,
        'stroke-width': 2
      }));
      guide.append(node('circle', {
        cx: origin[0],
        cy: origin[1],
        r: 2.5,
        fill: colour
      }));
      guide.append(node('text', {
        x: origin[0] + 12,
        y: origin[1] - 10,
        fill: colour,
        'font-size': 12,
        'font-weight': 700
      }, label + ' ⊙'));
      continue;
    }
    const end = [origin[0] + dx * 47, origin[1] + dy * 47],
      ux = dx / length,
      uy = dy / length;
    guide.append(node('line', {
      x1: origin[0] - dx * 23,
      y1: origin[1] - dy * 23,
      x2: origin[0],
      y2: origin[1],
      stroke: colour,
      'stroke-opacity': .35,
      'stroke-dasharray': '3 3'
    }));
    guide.append(node('line', {
      x1: origin[0],
      y1: origin[1],
      x2: end[0],
      y2: end[1],
      stroke: colour,
      'stroke-width': 2
    }));
    guide.append(node('polygon', {
      points: [end, [end[0] - ux * 7 - uy * 3, end[1] - uy * 7 + ux * 3],
        [end[0] - ux * 7 + uy * 3, end[1] - uy * 7 - ux * 3]
      ].map(p => p.join(',')).join(' '),
      fill: colour
    }));
    guide.append(node('text', {
      x: end[0] + ux * 12,
      y: end[1] + uy * 12 + 4,
      'text-anchor': 'middle',
      fill: colour,
      'font-size': 13,
      'font-weight': 700
    }, label));
  }
  guide.append(node('text', {
    x: 624,
    y: 164,
    fill: '#75868e',
    'font-size': 10
  }, mode === 'layer' ? 'x, y: space · z: toward you' : 'x, y: space · z: time'));
  svg.append(guide);
}

function draw() {
  updateSurfaceDownloads();
  const svg = $('canvas');
  svg.replaceChildren();
  const layer = Number($('layer').value) || 0;
  refreshPaletteOrientation();
  const camera = cameraDirection(),
    rawWorld = cameraProjection;
  const visible = graph.cubes.filter(c => mode !== 'layer' || c.position[2] === layer);
  const positions = [
    [0, 0, mode === 'layer' ? layer * BLOCK_PITCH : 0], ...visible.map(c => world(c.position)), ...(drag?.options || []).filter(p => mode !== 'layer' || p.position[2] === layer).map(p => world(p.position))
  ];
  const low = [0, 1, 2].map(i => Math.min(...positions.map(p => p[i]))),
    high = [0, 1, 2].map(i => Math.max(...positions.map(p => p[i])));
  const center = positions.length ? low.map((n, i) => (n + high[i]) / 2) : [0, 0, layer * BLOCK_PITCH];
  // A bounding sphere keeps the apparent scale steady while orbiting.
  const radius = positions.length ? Math.max(1, ...positions.map(p => Math.hypot(...p.map((n, i) => mode === 'layer' && i === 2 ? 0 : n - center[i])))) + Math.sqrt(3) / 2 : 2;
  const scale = Math.min(120, 260 / radius) * zoom;
  const [cx, cy] = rawWorld(center);
  $('zoom-level').textContent = Math.round(zoom * 100) + '%';
  $('zoom-in').disabled = zoom >= 3;
  $('zoom-out').disabled = zoom <= .35;
  for (const id of ['rotate', 'rotate-left', 'tilt-up', 'tilt-down']) $(id).disabled = mode === 'layer';
  const projectWorld = p => {
    const [x, y] = rawWorld(p);
    return [400 + (x - cx) * scale, 300 + (y - cy) * scale];
  };
  const project = p => projectWorld(world(p));
  projectPoint = project;
  const worldLine = (a, b, attrs = {}) => {
    const [x1, y1] = projectWorld(a), [x2, y2] = projectWorld(b);
    svg.append(node('line', {
      x1,
      y1,
      x2,
      y2,
      ...attrs
    }));
  };
  const line = (a, b, attrs = {}) => worldLine(world(a), world(b), attrs);
  // Half-unit boundaries align grid squares with cube faces.
  const gridZ = mode === 'layer' ? layer * BLOCK_PITCH - CUBE_SIZE / 2 : Math.min(0, ...graph.cubes.map(c => c.position[2])) * BLOCK_PITCH - CUBE_SIZE / 2;
  const gridPositions = visible.map(c => world(c.position));
  const gx0 = Math.max(-310, Math.min(-5, ...gridPositions.map(p => p[0])) - 2) - .5,
    gx1 = Math.min(310, Math.max(5, ...gridPositions.map(p => p[0])) + 2) + .5;
  const gy0 = Math.max(-310, Math.min(-5, ...gridPositions.map(p => p[1])) - 2) - .5,
    gy1 = Math.min(310, Math.max(5, ...gridPositions.map(p => p[1])) + 2) + .5;
  for (let x = gx0; x <= gx1; x++) worldLine([x, gy0, gridZ], [x, gy1, gridZ], {
    stroke: '#dce7e9',
    'stroke-width': .7,
    'pointer-events': 'none'
  });
  for (let y = gy0; y <= gy1; y++) worldLine([gx0, y, gridZ], [gx1, y, gridZ], {
    stroke: '#dce7e9',
    'stroke-width': .7,
    'pointer-events': 'none'
  });
  if (mode === 'layer') {
    const gx = visible.map(c => c.position[0]),
      gy = visible.map(c => c.position[1]);
    let xmin = Math.min(-3, ...gx) - 1,
      xmax = Math.max(3, ...gx) + 1,
      ymin = Math.min(-3, ...gy) - 1,
      ymax = Math.max(3, ...gy) + 1;
    // Keep the interactive grid bounded even when distant blocks are imported.
    if ((xmax - xmin) * (ymax - ymin) > 1600) {
      xmin = -10;
      xmax = 10;
      ymin = -10;
      ymax = 10;
    }
    for (let x = xmin; x <= xmax; x++)
      for (let y = ymin; y <= ymax; y++) {
        const [cx, cy] = project([x, y, layer]);
        if (cx < 10 || cx > 790 || cy < 70 || cy > 635) continue;
        const dot = node('circle', {
          cx,
          cy,
          r: Math.max(4, scale * .055),
          fill: '#d3dfe2',
          cursor: 'crosshair'
        });
        dot.onclick = () => message('Drag a pipe from the palette to extend the graph.');
        svg.append(dot);
      }
  }
  const scene = [],
    indices = cubeIndices(),
    indexLabels = [];
  const depth = points => points.reduce((sum, p) => sum + p.reduce((n, v, i) => n + v * camera[i], 0), 0) / points.length;
  const addFace = (f, attrs = {}, onClick = null) => {
    const el = node('polygon', {
      points: f.points.map(p => projectWorld(p).join(',')).join(' '),
      fill: wallColour(f.basis, f.axis, f.sign, camera),
      stroke: '#283646',
      'stroke-width': .9,
      'stroke-linejoin': 'round',
      ...attrs
    });
    if (onClick) {
      el.onclick = onClick;
      el.style.cursor = 'pointer';
    }
    scene.push({
      depth: depth(f.points),
      el
    });
  };
  for (const pipe of graph.pipes) {
    if (mode === 'layer' && (pipe.u[2] !== layer || pipe.v[2] !== layer)) continue;
    const [u, v] = pipeEndpoints(pipe.u, pipe.v, pipe.kind);
    const faces = pipeWalls(u, v, pipe.kind);
    for (const f of faces) {
      // Top-down view retains top walls; temporal pipes are outside this slice.
      if (mode === 'layer' && (f.axis !== 2 || f.sign !== 1)) continue;
      const chosen = pipeKey(pipe) === selectedPipe;
      addFace(f, {
        class: 'pipe' + (chosen ? ' selected-pipe' : ''),
        stroke: chosen ? '#087f79' : '#283646',
        'stroke-width': chosen ? 3 : .9,
        'data-pipe-key': pipeKey(pipe)
      }, () => selectPipe(pipe));
    }
  }
  for (const c of visible) {
    const pos = cubeDisplayPosition(c.position, c.kind),
      [px, py] = project(c.position),
      chosen = key(c.position) === selected,
      port = ['P', 'PORT'].includes(c.kind);
    const badge = node('g', {
      class: 'cube-index',
      'pointer-events': 'none',
      'aria-label': `ZX vertex ${indices.get(key(c.position))} at ${c.position.join(', ')}`
    });
    const label = '#' + indices.get(key(c.position)),
      bx = px + scale * .7,
      by = py - 10;
    badge.append(node('line', {
      x1: px,
      y1: py,
      x2: bx,
      y2: by,
      stroke: '#85969d',
      'stroke-width': .8
    }));
    badge.append(node('rect', {
      x: bx - 3,
      y: by - 12,
      width: label.length * 7 + 8,
      height: 18,
      rx: 4,
      fill: '#fff',
      'fill-opacity': .94,
      stroke: '#b7c8ce'
    }));
    badge.append(node('text', {
      x: bx + 1,
      y: by + 1,
      fill: '#20333e',
      'font-size': 11,
      'font-weight': 600
    }, label));
    if ($('show-cube-numbers').checked) indexLabels.push(badge);
    if (port) {
      // Keep the open end visible; labels sit alongside it, never cap the tube.
      const attached = graph.pipes.find(p => key(p.u) === key(c.position) || key(p.v) === key(c.position));
      const end = attached ? pipeEndpoints(attached.u, attached.v, attached.kind)[key(attached.u) === key(c.position) ? 0 : 1] : pos;
      const [portX, portY] = projectWorld(end);
      const group = node('g', {
          class: 'cube'
        }),
        labelX = portX + scale * .65;
      group.append(node('circle', {
        cx: portX,
        cy: portY,
        r: scale * .12,
        fill: '#ffffff',
        'fill-opacity': .10,
        stroke: chosen ? '#087f79' : '#758c96',
        'stroke-width': 1.5,
        'stroke-dasharray': '3 3'
      }));
      group.append(node('text', {
        x: labelX,
        y: portY + 4,
        fill: '#526b77',
        'font-size': 10
      }, c.label || 'Port'));
      group.append(node('title', {}, `Open port ${c.label} (${c.position})`));
      group.onclick = () => select(c.position);
      scene.push({
        depth: depth([pos]) + .02,
        el: group
      });
      continue;
    }
    const signs = camera.map(n => n >= 0 ? 1 : -1);
    for (const f of cubeFaces(pos, c.kind, signs, mode === 'layer' ? [2] : [0, 1, 2])) {
      addFace(f, {
        class: 'cube',
        fill: cubeColour(f.basis, f.axis),
        stroke: chosen ? '#087f79' : '#1e2730',
        'stroke-width': chosen ? 2.5 : 1
      }, () => select(c.position));
    }
    const top = [pos[0], pos[1], pos[2] + (c.kind === 'Y' ? .25 : CUBE_SIZE / 2)],
      [tx, ty] = projectWorld(top);
    const text = node('text', {
      x: tx,
      y: ty + 3,
      'text-anchor': 'middle',
      fill: '#303b48',
      'font-size': Math.max(8, Math.min(12, scale * .17)),
      'font-weight': 600,
      'pointer-events': 'none',
      class: 'cube-kind-label'
    }, c.kind);
    if ($('show-cube-kinds').checked) scene.push({
      depth: depth([top]) + .001,
      el: text
    });
  }
  scene.sort((a, b) => a.depth - b.depth).forEach(item => svg.append(item.el));
  const surface = surfaces.find(s => s.index === overlay);
  if (surface)
    for (const e of surface.edges) {
      if (mode === 'layer' && (e.u[2] !== layer || e.v[2] !== layer)) continue;
      const mid = e.u.map((x, i) => (x + e.v[i]) / 2);
      if (key(e.u) === key(e.v)) {
        const [cx, cy] = project(e.u);
        svg.append(node('circle', {
          cx,
          cy,
          r: scale * .43,
          fill: 'none',
          stroke: e.ub === 'X' ? '#b63642' : '#245fa3',
          'stroke-width': 4,
          'pointer-events': 'none'
        }));
      } else {
        line(e.u, e.v, {
          stroke: '#fff',
          'stroke-width': 9,
          'pointer-events': 'none'
        });
        line(e.u, mid, {
          stroke: e.ub === 'X' ? '#b63642' : '#245fa3',
          'stroke-width': 5,
          'pointer-events': 'none'
        });
        line(mid, e.v, {
          stroke: e.vb === 'X' ? '#b63642' : '#245fa3',
          'stroke-width': 5,
          'pointer-events': 'none'
        });
      }
    }
  if (drag?.started) {
    for (const option of drag.options || []) {
      if (mode === 'layer' && option.position[2] !== layer) continue;
      const [cx, cy] = project(option.position), hot = drag.target && key(drag.target.position) === key(option.position);
      if (drag.type === 'pipe') {
        if (hot) {
          const faces = pipeWalls(...pipeEndpoints(option.u, option.v, drag.pipeKind), drag.pipeKind).sort((a, b) => depth(a.points) - depth(b.points));
          for (const f of faces) {
            if (mode === 'layer' && (f.axis !== 2 || f.sign !== 1)) continue;
            svg.append(node('polygon', {
              points: f.points.map(p => projectWorld(p).join(',')).join(' '),
              fill: wallColour(f.basis, f.axis, f.sign, camera),
              'fill-opacity': .75,
              stroke: '#078366',
              'stroke-width': 1.5,
              'pointer-events': 'none'
            }));
          }
        } else line(option.u, option.v, {
          stroke: '#69af9c',
          'stroke-width': 5,
          'stroke-dasharray': '7 4',
          'pointer-events': 'none'
        });
        svg.append(node('circle', {
          cx,
          cy,
          r: hot ? 7 : 5,
          fill: hot ? '#078366' : '#d9efe7',
          stroke: '#188b70',
          'pointer-events': 'none'
        }));
      } else {
        const previewPos = cubeDisplayPosition(option.portPosition || option.position, drag.cubeKind);
        for (const f of cubeFaces(previewPos, drag.cubeKind, camera.map(n => n >= 0 ? 1 : -1), mode === 'layer' ? [2] : [0, 1, 2])) svg.append(node('polygon', {
          points: f.points.map(p => projectWorld(p).join(',')).join(' '),
          fill: cubeColour(f.basis, f.axis),
          'fill-opacity': hot ? .85 : .35,
          stroke: '#188b70',
          'stroke-width': hot ? 3 : 1.5,
          'stroke-dasharray': hot ? '' : '5 4',
          'pointer-events': 'none'
        }));
        if (hot && option.source) line(option.source, option.position, {
          stroke: '#118b73',
          'stroke-width': 5,
          'stroke-dasharray': '6 4',
          'pointer-events': 'none'
        });
      }
    }
  }
  // An orientation marker, never a graph vertex or a placement target.
  const originPosition = [0, 0, mode === 'layer' ? layer : 0],
    [ox, oy] = project(originPosition);
  const origin = node('g', {
    'pointer-events': 'none',
    class: 'origin-marker'
  });
  origin.append(node('circle', {
    cx: ox,
    cy: oy,
    r: 8,
    fill: 'white',
    'fill-opacity': .85,
    stroke: '#087f79',
    'stroke-width': 2
  }));
  origin.append(node('line', {
    x1: ox - 13,
    y1: oy,
    x2: ox + 13,
    y2: oy,
    stroke: '#087f79',
    'stroke-width': 1.5
  }));
  origin.append(node('line', {
    x1: ox,
    y1: oy - 13,
    x2: ox,
    y2: oy + 13,
    stroke: '#087f79',
    'stroke-width': 1.5
  }));
  origin.append(node('text', {
    x: ox + 17,
    y: oy + 26,
    fill: '#076d68',
    stroke: 'white',
    'stroke-width': 3,
    'paint-order': 'stroke',
    'font-size': 12,
    'font-weight': 600
  }, mode === 'layer' && layer !== 0 ? `x=0, y=0 · layer z=${layer}` : 'Origin (0, 0, 0)'));
  if ($('show-origin').checked) svg.append(origin);
  svg.append(...indexLabels);
  drawAxes(svg, rawWorld);
}
async function palette() {
  const request = ++paletteRequest,
    modeAtRequest = buildMode,
    edge = selectedPipe,
    gen = generation,
    coord = selected;
  const container = $('palette');
  container.replaceChildren();
  let kinds = buildMode === 'pipe' ? ['OXZ', 'OZX', 'XOZ', 'ZOX', 'XZO', 'ZXO'] : ['ZXZ', 'ZXX', 'XZX', 'XZZ', 'XXZ', 'ZZX', 'Y'];
  const pipe = graph.pipes.find(p => pipeKey(p) === edge),
    cube = graph.cubes.find(c => key(c.position) === coord);
  const editCube = buildMode !== 'pipe' && cube;
  if (editCube) {
    const note = document.createElement('p');
    note.className = 'hint palette-note';
    note.textContent = 'Checking valid choices…';
    container.append(note);
    try {
      if (['P', 'PORT'].includes(cube.kind)) {
        const results = await Promise.all(kinds.map(async k => {
          const result = await api('/api/cap-options', {
            graph,
            kind: k
          });
          return {
            kind: k,
            valid: result.placements.some(p => key(p.position) === coord)
          };
        }));
        kinds = results.filter(r => r.valid).map(r => r.kind);
      } else {
        const result = await api('/api/cube-options', {
          graph,
          position: cube.position
        });
        kinds = [cube.kind, ...result.kinds, ...(result.can_reopen ? ['P'] : [])];
      }
      if (request !== paletteRequest || modeAtRequest !== buildMode || coord !== selected || gen !== generation) return;
      container.replaceChildren();
      note.textContent = 'Click a choice to update the selected cube or port. Connected pipes are kept.';
      container.append(note);
    } catch (e) {
      if (request === paletteRequest) note.textContent = 'Could not check choices: ' + e.message;
      return;
    }
  } else if (buildMode !== 'pipe' && pipe) {
    const note = document.createElement('p');
    note.className = 'hint';
    note.textContent = 'Checking caps for the selected pipe…';
    container.append(note);
    try {
      const snapshot = clone(graph),
        endpoints = new Set([key(pipe.u), key(pipe.v)]);
      const results = await Promise.all(kinds.map(async k => {
        const result = await api('/api/cap-options', {
          graph: snapshot,
          kind: k
        });
        return {
          kind: k,
          valid: result.placements.some(p => endpoints.has(key(p.position)))
        };
      }));
      if (request !== paletteRequest || modeAtRequest !== buildMode || edge !== selectedPipe || gen !== generation) return;
      kinds = results.filter(r => r.valid).map(r => r.kind);
      container.replaceChildren();
      const hint = document.createElement('p');
      hint.className = 'hint palette-note';
      hint.textContent = kinds.length ? 'Caps for the selected pipe’s open ends. Drag onto a highlighted end.' : graph.cubes.some(c => endpoints.has(key(c.position)) && ['P', 'PORT'].includes(c.kind)) ? 'No valid caps for this pipe. Validate the graph to check for errors.' : 'This pipe has no open ports to cap.';
      container.append(hint);
    } catch (e) {
      if (request !== paletteRequest) return;
      container.replaceChildren();
      const hint = document.createElement('p');
      hint.className = 'hint palette-note';
      hint.textContent = 'Could not check caps: ' + e.message;
      container.append(hint);
      return;
    }
  }
  if (buildMode !== 'pipe' && !editCube && !pipe) {
    try {
      const result = await api('/api/cap-options', {
        graph,
        kind: 'Y'
      });
      if (request !== paletteRequest || modeAtRequest !== buildMode || gen !== generation) return;
      if (!result.placements.length) kinds = kinds.filter(k => k !== 'Y');
    } catch {
      if (request !== paletteRequest) return;
      kinds = kinds.filter(k => k !== 'Y');
    }
  }
  if (!kinds.includes(kind)) kind = kinds[0] || '';
  for (const k of kinds) {
    const b = document.createElement('button');
    b.className = k === kind ? 'selected' : '';
    b.title = 'Drag ' + k + (buildMode === 'pipe' ? ' pipe onto a highlighted edge' : ' onto a compatible open port');
    const sw = buildMode === 'pipe' ? pipeIcon(k + ($('hadamard').checked ? 'H' : '')) : cubeIcon(k);
    if (k === 'Y') b.title = 'Y-basis cap · time direction only. Inspection supported; installed compiler does not implement Y cubes.';
    b.append(sw, document.createTextNode((k === 'P' ? 'Open port' : k) + (buildMode === 'pipe' && $('hadamard').checked ? 'H' : '')));
    if (editCube) {
      const current = cube.kind === k;
      b.disabled = current;
      b.classList.toggle('selected', current);
      b.title = current ? 'Current cube' : k === 'P' ? 'Reopen as a port, keeping the pipe' : 'Use ' + k + ' here, keeping connected pipes';
      b.onclick = () => {
        if (selected !== coord || generation !== gen) return;
        ['P', 'PORT'].includes(cube.kind) ? fillPort(cube.label, k) : replaceSelectedCube(k);
      };
    } else {
      b.onpointerdown = e => beginDrag(e, k);
      b.onclick = () => {
        kind = k;
        container.querySelectorAll('button').forEach(button => button.classList.toggle('selected', button === b));
      };
    }
    container.append(b);
  }
}

async function beginDrag(e, k) {
  if (e.button !== 0 || busy) return;
  kind = k;
  const session = {
    startX: e.clientX,
    startY: e.clientY,
    started: false,
    options: [],
    target: null,
    generation,
    selectedEdge: selectedPipe,
    type: buildMode,
    cubeKind: k,
    pipeKind: k + ($('hadamard').checked ? 'H' : '')
  };
  drag = session;
  try {
    const res = await api(buildMode === 'pipe' ? '/api/pipe-placements' : '/api/cap-options', {
      graph,
      kind: buildMode === 'pipe' ? session.pipeKind : k
    });
    if (drag !== session || generation !== session.generation) return;
    if (session.type !== 'pipe' && session.selectedEdge) {
      const pipe = graph.pipes.find(p => pipeKey(p) === session.selectedEdge);
      res.placements = pipe ? res.placements.filter(p => key(p.position) === key(pipe.u) || key(p.position) === key(pipe.v)) : [];
    }
    if (session.type !== 'pipe') res.placements = res.placements.map(option => {
      const pipe = graph.pipes.find(p => key(p.u) === key(option.position) || key(p.v) === key(option.position));
      const endpoint = pipe ? pipeEndpoints(pipe.u, pipe.v, pipe.kind)[key(pipe.u) === key(option.position) ? 0 : 1].map(n => n / BLOCK_PITCH) : option.position;
      return {
        ...option,
        portPosition: option.position,
        position: endpoint
      };
    });
    const seen = new Set();
    session.options = res.placements.sort((a, b) => Number(key(b.source || []) === selected) - Number(key(a.source || []) === selected)).filter(p => {
      const id = key(p.position);
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    if (session.started) {
      draw();
      message(session.options.length ? 'Drop on a green target. Matching junction cubes will be inferred.' : 'No compatible targets. Try another kind or add an open pipe first.');
    }
  } catch (err) {
    if (drag === session) {
      message(err.message, true);
      drag = null;
      draw();
    }
  }
}
document.addEventListener('pointermove', e => {
  if (!drag) return;
  if (!drag.started && Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 6) return;
  drag.started = true;
  e.preventDefault();
  document.body.classList.add('dragging');
  const svg = $('canvas'),
    rect = svg.getBoundingClientRect();
  drag.target = null;
  if (projectPoint && e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse());
    let distance = 55;
    for (const option of drag.options) {
      if (mode === 'layer' && option.position[2] !== Number($('layer').value)) continue;
      const [x, y] = projectPoint(option.position), d = Math.hypot(p.x - x, p.y - y);
      if (d < distance) {
        distance = d;
        drag.target = option;
      }
    }
  }
  draw();
  if (drag.target) message(`Release to place ${kind} at (${drag.target.position.join(', ')})${drag.target.ambiguous?' · junction choice required':''}.`);
  else message(drag.options.length ? 'Move onto a green target. Other positions cannot accept this block.' : 'Checking compatible positions…');
}, {
  passive: false
});
document.addEventListener('pointerup', async () => {
  if (!drag) return;
  const session = drag;
  drag = null;
  document.body.classList.remove('dragging');
  draw();
  if (!session.started) return;
  if (session.target && session.generation === generation) await (session.type === 'pipe' ? placePipe(session.target, session.pipeKind) : fillPort(session.target.label, session.cubeKind));
  else message('Placement cancelled. Drop on a green compatible target.', true);
  $('palette').replaceChildren();
  palette();
});
document.addEventListener('pointercancel', () => {
  drag = null;
  document.body.classList.remove('dragging');
  draw();
});

function pipeKind() {
  return kind + ($('hadamard').checked ? 'H' : '');
}
async function placePipe(option, selectedKind, choices = {}) {
  if (busy) return;
  busy = true;
  try {
    const payload = {
      graph: clone(graph),
      u: option.u,
      v: option.v,
      kind: selectedKind,
      choices
    };
    const result = await api('/api/place-pipe', payload);
    if (result.ambiguities) {
      pendingPipe = {
        option,
        kind: selectedKind,
        generation,
        choices
      };
      $('junction-choices').replaceChildren();
      for (const ambiguity of result.ambiguities) {
        const label = document.createElement('label');
        label.textContent = 'Cube at (' + ambiguity.position.join(', ') + ')';
        const select = document.createElement('select');
        select.dataset.position = key(ambiguity.position);
        select.add(new Option('Choose a cube kind…', ''));
        for (const k of ambiguity.kinds) select.add(new Option(k, k));
        label.append(select);
        $('junction-choices').append(label);
      }
      $('junction-dialog').showModal();
      message('Pipe colours allow several cubes. Choose the junction boundary to finish.');
      return;
    }
    pendingPipe = null;
    selectedPipe = pipeKey(option);
    selected = null;
    commit(result.graph);
    scrollToSelectedPipe();
    message(result.inferred.length ? 'Pipe placed. Junction cube ' + (Object.keys(choices).length ? 'chosen' : 'inferred') + ': ' + result.inferred.map(c => c.kind + ' at (' + c.position + ')').join('; ') : 'Pipe placed. Dangling ends remain open ports.');
  } catch (e) {
    message(e.message, true);
  } finally {
    busy = false;
  }
}
$('build-mode').querySelector('option[value="cube"]').textContent = 'Cubes · cap or replace';
$('hadamard').onchange = () => {
  $('palette').replaceChildren();
  palette();
};
$('build-mode').onchange = () => {
  buildMode = $('build-mode').value;
  kind = buildMode === 'pipe' ? 'ZXO' : 'ZXZ';
  $('pipe-help').hidden = false;
  $('pipe-help').textContent = buildMode === 'pipe' ? 'Drag pipes to extend the graph. Matching walls determine junction cubes.' : 'Drag a cube onto a highlighted open port to cap it. Only compatible ports accept the cube. Undo restores the port.';
  $('hadamard-control').hidden = buildMode !== 'pipe';
  $('palette').nextElementSibling.hidden = buildMode !== 'pipe';
  $('palette').replaceChildren();
  palette();
};
$('cancel-junction').onclick = () => {
  pendingPipe = null;
  $('junction-dialog').close();
  message('Pipe placement cancelled.');
};
$('junction-dialog').addEventListener('cancel', () => {
  pendingPipe = null;
});
$('confirm-junction').onclick = () => {
  if (!pendingPipe) return;
  const choices = {
    ...pendingPipe.choices
  };
  for (const select of $('junction-choices').querySelectorAll('select')) {
    if (!select.value) {
      select.focus();
      return;
    }
    choices[select.dataset.position] = select.value;
  }
  const pending = pendingPipe;
  $('junction-dialog').close();
  if (pending.generation !== generation) {
    pendingPipe = null;
    message('Graph changed. Place the pipe again.', true);
    return;
  }
  placePipe(pending.option, pending.kind, choices);
};

function panel(name) {
  if (name === 'simulate' && window.updateSimulationContext) window.updateSimulationContext();
  document.querySelector('.left').hidden = name !== 'design';
  document.querySelector('main').classList.toggle('inspection-mode', name !== 'design');
  document.querySelectorAll('.step').forEach(b => b.classList.toggle('active', b.dataset.panel === name));
  document.querySelector('.canvas-section').hidden = name === 'simulate';
  $('plot-workspace').hidden = name !== 'simulate';
  ['design', 'surfaces', 'compile', 'simulate'].forEach(p => $('panel-' + p).hidden = p !== name);
}
for (const b of document.querySelectorAll('.step')) b.onclick = () => panel(b.dataset.panel);
$('cube-list').onchange = () => {
  const value = $('cube-list').value;
  if (value) select(value.split(',').map(Number));
  else {
    selected = null;
    render();
  }
};
$('delete').onclick = () => {
  if (!selected) return;
  const next = clone(graph);
  next.cubes = next.cubes.filter(c => key(c.position) !== selected);
  next.pipes = next.pipes.filter(p => key(p.u) !== selected && key(p.v) !== selected);
  change(next);
};
async function fillPort(label, cubeKind) {
  if (busy) return;
  busy = true;
  try {
    const res = await api('/api/fill', {
      graph,
      label,
      kind: cubeKind
    });
    commit(res.graph);
    message('Port capped with ' + cubeKind + '. Undo restores the open port.' + (cubeKind === 'Y' ? ' Y caps support validation and surfaces; the installed compiler cannot compile them yet.' : ''));
  } catch (e) {
    message(e.message, true);
  } finally {
    busy = false;
  }
}
$('undo').onclick = () => {
  if (!history.length || busy) return;
  future.push(clone(graph));
  commit(history.pop(), false);
  message('Undid last edit.');
};
$('redo').onclick = () => {
  if (!future.length || busy) return;
  history.push(clone(graph));
  commit(future.pop(), false);
  message('Redid edit.');
};
$('name').onchange = () => {
  const name = $('name').value.trim() || 'Untitled graph';
  change({
    ...clone(graph),
    name
  });
};
$('iso').onclick = () => {
  mode = 'iso';
  $('iso').classList.add('selected');
  $('layer-view').classList.remove('selected');
  draw();
};
$('layer-view').onclick = () => {
  mode = 'layer';
  $('layer-view').classList.add('selected');
  $('iso').classList.remove('selected');
  draw();
};

function orbitBy(horizontal, vertical = 0) {
  angle = (angle + horizontal + Math.PI * 2) % (Math.PI * 2);
  elevation = Math.max(Math.PI / 18, Math.min(Math.PI * 4 / 9, elevation + vertical));
  draw();
}

function zoomBy(factor) {
  zoom = Math.max(.35, Math.min(3, zoom * factor));
  draw();
}

function setupCamera() {
  const controls = $('rotate').parentElement;
  controls.classList.add('camera-controls');
  const button = (id, label, title, action) => {
    const b = document.createElement('button');
    b.id = id;
    b.textContent = label;
    b.title = title;
    b.setAttribute('aria-label', title);
    b.onclick = action;
    return b;
  };
  const left = button('rotate-left', '↶', 'Rotate left', () => orbitBy(-Math.PI / 12));
  controls.prepend(left);
  $('rotate').textContent = '↷';
  $('rotate').title = 'Rotate right';
  $('rotate').setAttribute('aria-label', 'Rotate right');
  $('rotate').onclick = () => orbitBy(Math.PI / 12);
  controls.insertBefore(button('tilt-up', '↑', 'Tilt view up', () => orbitBy(0, Math.PI / 18)), $('fit'));
  controls.insertBefore(button('tilt-down', '↓', 'Tilt view down', () => orbitBy(0, -Math.PI / 18)), $('fit'));
  controls.insertBefore(button('zoom-out', '−', 'Zoom out · farther', () => zoomBy(1 / 1.2)), $('fit'));
  const level = document.createElement('span');
  level.id = 'zoom-level';
  level.setAttribute('aria-label', 'Zoom level');
  controls.insertBefore(level, $('fit'));
  controls.insertBefore(button('zoom-in', '+', 'Zoom in · nearer', () => zoomBy(1.2)), $('fit'));
  $('fit').onclick = () => {
    zoom = 1;
    draw();
  };
  controls.append(button('reset-view', 'Reset', 'Reset view', () => {
    angle = Math.PI / 4;
    elevation = Math.PI / 6;
    zoom = 1;
    draw();
  }));
  const hint = document.createElement('p');
  hint.className = 'camera-hint';
  hint.textContent = 'Drag empty canvas to rotate · Scroll to move up/down · Ctrl/Cmd + scroll to zoom';
  $('canvas').before(hint);
  const canvas = $('canvas');
  canvas.addEventListener('pointerdown', e => {
    if (e.button !== 0 || drag || mode !== 'iso' || e.target.closest('.cube,.pipe')) return;
    orbit = {
      id: e.pointerId,
      x: e.clientX,
      y: e.clientY,
      moved: false
    };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', e => {
    if (!orbit || e.pointerId !== orbit.id) return;
    const dx = e.clientX - orbit.x,
      dy = e.clientY - orbit.y;
    if (!orbit.moved && Math.hypot(dx, dy) < 4) return;
    orbit.moved = true;
    orbit.x = e.clientX;
    orbit.y = e.clientY;
    canvas.classList.add('orbiting');
    orbitBy(-dx * .008, dy * .006);
  });
  const end = e => {
    if (!orbit || orbit.id !== e.pointerId) return;
    suppressCanvasClick = orbit.moved;
    orbit = null;
    canvas.classList.remove('orbiting');
    if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    setTimeout(() => suppressCanvasClick = false, 0);
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('lostpointercapture', end);
  canvas.addEventListener('click', e => {
    if (suppressCanvasClick) {
      e.stopImmediatePropagation();
      e.preventDefault();
    }
  }, true);
  canvas.addEventListener('wheel', e => {
    // Ordinary wheel gestures scroll the workspace, including tall canvases.
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    if (drag || orbit) return;
    const delta = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 450 : 1);
    zoomBy(Math.exp(-Math.max(-100, Math.min(100, delta)) * .003));
  }, {
    passive: false
  });
}
setupCamera();

function setupWorkspaceSize() {
  const main = document.querySelector('main');
  const canvas = $('canvas');
  let width = 0, height = null;
  try {
    const saved = JSON.parse(localStorage.getItem('tqec-studio-workspace-size') || 'null');
    if (saved && Number.isInteger(saved.width)) width = Math.max(0, Math.min(2, saved.width));
    if (saved && Number.isFinite(saved.height)) height = Math.max(280, Math.min(1400, saved.height));
  } catch { /* Storage is optional. */ }
  const controls = document.createElement('div');
  controls.className = 'workspace-size-controls';
  controls.setAttribute('role', 'group');
  controls.setAttribute('aria-label', 'Drawing area size');
  const label = document.createElement('span');
  label.textContent = 'Drawing area';
  controls.append(label);
  const buttons = {};
  function add(id, text, title, action) {
    const button = document.createElement('button');
    button.textContent = text;
    button.title = title;
    button.setAttribute('aria-label', title);
    button.onclick = action;
    buttons[id] = button;
    controls.append(button);
  }
  function apply() {
    main.classList.toggle('workspace-wide', width === 1);
    main.classList.toggle('workspace-full', width === 2);
    canvas.style.height = height === null ? '' : height + 'px';
    main.classList.toggle('workspace-custom-height', height !== null);
    main.style.setProperty('--drawing-height', (height ?? 280) + 'px');
    buttons.wider.disabled = width === 2;
    buttons.narrower.disabled = width === 0;
    buttons.shorter.disabled = height !== null && height <= 280;
    buttons.taller.disabled = height !== null && height >= 1400;
    try {
      localStorage.setItem('tqec-studio-workspace-size', JSON.stringify({width, height}));
    } catch { /* The controls also work without persistent storage. */ }
  }
  function resizeHeight(delta) {
    height = Math.max(280, Math.min(1400, (height ?? canvas.getBoundingClientRect().height) + delta));
    apply();
  }
  add('wider', '↔ Wider', 'Widen drawing area; two steps to full width', () => { width++; apply(); });
  add('narrower', '→← Narrower', 'Restore space for the side panels', () => { width--; apply(); });
  add('taller', '↕ Taller', 'Increase drawing area height', () => resizeHeight(100));
  add('shorter', '↑↓ Shorter', 'Decrease drawing area height', () => resizeHeight(-100));
  add('reset', 'Reset size', 'Restore the default drawing area size', () => { width = 0; height = null; apply(); });
  document.querySelector('.canvas-toolbar').after(controls);
  apply();
}
setupWorkspaceSize();

function setupLabelControls() {
  const controls = document.createElement('div');
  controls.className = 'label-controls';
  controls.setAttribute('aria-label', 'Canvas labels');
  let preferences = {};
  try {
    preferences = JSON.parse(localStorage.getItem('tqec-studio-labels') || '{}') || {};
  } catch {}
  for (const [id, text] of [
      ['show-cube-numbers', 'Cube numbers'],
      ['show-cube-kinds', 'Cube kind labels'],
      ['show-origin', 'Show origin']
    ]) {
    const label = document.createElement('label'),
      input = document.createElement('input');
    input.type = 'checkbox';
    input.id = id;
    input.checked = id === 'show-origin' ? preferences[id] === true : preferences[id] !== false;
    input.onchange = () => {
      try {
        localStorage.setItem('tqec-studio-labels', JSON.stringify({
          'show-cube-numbers': $('show-cube-numbers').checked,
          'show-cube-kinds': $('show-cube-kinds').checked,
          'show-origin': $('show-origin').checked
        }));
      } catch {}
      draw();
    };
    label.append(input, document.createTextNode(text));
    controls.append(label);
  }
  document.querySelector('.canvas-toolbar').append(controls);
}
setupLabelControls();
$('layer').oninput = draw;
$('load-example').onclick = async () => {
  if (busy) return;
  busy = true;
  try {
    const res = await api('/api/example/' + $('example').value);
    commit(res.graph);
    message('Example loaded. Undo returns to your previous graph.');
  } catch (e) {
    message(e.message, true);
  } finally {
    busy = false;
  }
};
$('open').onclick = () => $('file').click();
$('file').onchange = async () => {
  const f = $('file').files[0];
  if (!f || busy) return;
  busy = true;
  try {
    const form = new FormData();
    form.append('file', f);
    commit((await api('/api/import', form, true)).graph);
    message('Project imported. Undo returns to your previous graph.');
  } catch (e) {
    message(e.message, true);
  } finally {
    busy = false;
    $('file').value = '';
  }
};
$('save').onclick = () => {
  const data = {
    schema: 'tqec-studio/1',
    graph
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json'
  }));
  const a = document.createElement('a');
  a.href = url;
  a.download = (graph.name.replace(/[^\w -]/g, '').trim() || 'project') + '.tqec.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  message('Project download prepared.');
};
$('find').onclick = async () => {
  if (busy) return;
  busy = true;
  $('find').disabled = true;
  message('Validating graph and finding correlation surfaces…');
  const gen = generation;
  try {
    const res = await api('/api/surfaces', graph);
    if (gen !== generation) return;
    surfaces = res.surfaces;
    revision = res.revision;
    overlay = surfaces[0]?.index ?? null;
    $('surface-list').replaceChildren();
    for (const s of surfaces) {
      const row = document.createElement('label'),
        check = document.createElement('input'),
        span = document.createElement('span'),
        view = document.createElement('button');
      check.type = 'checkbox';
      check.value = s.index;
      check.checked = true;
      span.textContent = `Observable ${s.index+1} · ${s.stabilizer}`;
      view.textContent = 'View';
      view.type = 'button';
      view.onclick = e => {
        e.preventDefault();
        overlay = s.index;
        draw();
      };
      row.append(check, span, view);
      $('surface-list').append(row);
    }
    $('surface-info').textContent = `${surfaces.length} surfaces found.${res.open_ports.length?' Fill open ports before compilation.':' Closed graph.'} Pauli strings follow TQEC leaf or port ordering.`;
    message('Graph validated. Choose observables, then open Compile.');
    draw();
  } catch (e) {
    message(e.message, true);
  } finally {
    busy = false;
    $('find').disabled = false;
  }
};

function setupSurfaceDownloads() {
  const box = document.createElement('section');
  box.id = 'surface-downloads';
  const heading = document.createElement('h3');
  heading.textContent = 'Inspect correlation surface in 3D';
  const label = document.createElement('p');
  label.id = 'surface-export-label';
  label.className = 'hint';
  box.append(heading, label);
  for (const axis of ['X', 'Y', 'Z']) {
    const button = document.createElement('button');
    button.textContent = 'Download HTML · +' + axis + ' face open';
    button.dataset.axis = axis;
    button.onclick = () => downloadSurfaceViewer(axis);
    box.append(button);
  }
  const help = document.createElement('p');
  help.className = 'hint';
  help.textContent = 'Each HTML contains a COLLADA model and its correlation surface, with only the positive face along the chosen axis removed. Open it in your browser; internet access is needed for the 3D viewer. The HTML also includes a .dae download link.';
  box.append(help);
  $('panel-surfaces').append(box);
}

function updateSurfaceDownloads() {
  const box = $('surface-downloads');
  if (!box) return;
  const available = revision && overlay !== null && surfaces.some(s => s.index === overlay);
  $('surface-export-label').textContent = available ? 'Exporting Observable ' + (overlay + 1) + '. Use View above to choose another surface.' : 'Find surfaces, then choose View on the surface to export.';
  for (const button of box.querySelectorAll('button')) button.disabled = !available;
}
async function downloadSurfaceViewer(axis) {
  if (!revision || overlay === null) return;
  const index = overlay,
    gen = generation,
    button = $('surface-downloads').querySelector('[data-axis="' + axis + '"]');
  button.disabled = true;
  try {
    const response = await fetch('/api/surface-viewer/' + axis, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Studio-Token': token
      },
      body: JSON.stringify({
        graph,
        revision,
        surface: index
      })
    });
    if (!response.ok) throw Error((await response.json()).error || 'Viewer export failed.');
    const blob = await response.blob();
    if (gen !== generation) {
      message('Graph changed during export. Find surfaces again.', true);
      return;
    }
    const url = URL.createObjectURL(blob),
      link = document.createElement('a');
    link.href = url;
    link.download = 'surface-' + (index + 1) + '-open-' + axis + '.html';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message('HTML viewer downloaded for Observable ' + (index + 1) + ' with +' + axis + ' face opened.');
  } catch (e) {
    message(e.message, true);
  } finally {
    updateSurfaceDownloads();
  }
}
setupSurfaceDownloads();
updateSurfaceDownloads();
$('clear-surface').onclick = () => {
  overlay = null;
  draw();
};
const crumbleLink = document.createElement('a');
crumbleLink.id = 'crumble';
crumbleLink.className = 'button';
crumbleLink.target = '_blank';
crumbleLink.rel = 'noopener';
crumbleLink.textContent = 'Open in Crumble ↗';
$('diagram').after(crumbleLink);
const crumbleHelp = document.createElement('p');
crumbleHelp.className = 'hint';
crumbleHelp.textContent = 'Crumble opens this compiled circuit in a new tab. Edits there do not change your graph or the saved Stim file.';
crumbleLink.after(crumbleHelp);
$('compile').onclick = async () => {
  if (activeJob) return;
  if (!revision && document.getElementById('observable-mode').value === 'selected') {
    panel('surfaces');
    message('Find correlation surfaces before compiling.', true);
    return;
  }
  const chosen = [...$('surface-list').querySelectorAll('input:checked')].map(c => Number(c.value));
  $('compile').disabled = true;
  try {
    const settings = window.compilationSettings();
    const compileRevision = revision || (await api('/api/graph', graph)).revision;
    const res = await api('/api/compile', {
      graph,
      revision: compileRevision,
      surfaces: chosen,
      ...settings
    });
    activeJob = res.id;
    $('results').hidden = true;
    const gen = generation;
    $('job').textContent = 'Compilation queued. You can keep inspecting the graph.';
    const poll = async () => {
      try {
        const job = await api('/api/jobs/' + res.id);
        if (['queued', 'running'].includes(job.status)) {
          $('job').textContent = `${job.status==='running'?'Compiling and checking detectors':'Queued'}… Large graphs can take several minutes.`;
          setTimeout(poll, 1000);
          return;
        }
        activeJob = null;
        $('compile').disabled = false;
        if (job.status === 'failed') throw Error(job.error);
        $('results').hidden = false;
        $('job').textContent = gen === generation ? 'Complete. Stim detector error model check passed.' : 'Complete for an earlier graph revision. Compile again to include your edits.';
        $('stats').textContent = `${job.statistics.qubits} qubits · ${job.statistics.measurements} measurements · ${job.statistics.detectors} detectors · ${job.statistics.observables} observables`;
        $('download').href = `/api/jobs/${res.id}/circuit.stim`;
        $('manifest').href = `/api/jobs/${res.id}/run.json`;
        $('database-download').hidden = !job.detector_database;
        $('database-download').href = `/api/jobs/${res.id}/detectors.json`;
        $('diagram').href = `/api/jobs/${res.id}/circuit.svg`;
        $('diagram').hidden = !job.diagram;
        $('crumble').href = `/api/jobs/${res.id}/crumble`;
        $('physical-layers').href = `/api/jobs/${res.id}/physical-layers`;
        message('Circuit generated. Download the Stim file and run record.');
      } catch (e) {
        activeJob = null;
        $('compile').disabled = false;
        $('job').textContent = e.message;
        message(e.message, true);
      }
    };
    poll();
  } catch (e) {
    $('compile').disabled = false;
    $('job').textContent = e.message;
    message(e.message, true);
  }
};
async function start() {
  palette();
  try {
    const draft = localStorage.getItem('tqec-studio-draft-v1');
    if (draft) {
      try {
        const restored = await api('/api/graph', JSON.parse(draft).graph);
        graph = restored.graph;
        message(restored.warning || 'Restored your browser draft.', Boolean(restored.warning));
      } catch (e) {
        message('Draft could not be restored: ' + e.message, true);
      }
    } else graph = (await api('/api/example/memory')).graph;
    render();
  } catch (e) {
    message(e.message, true);
  }
}
start();


// Keyboard edits share the same validated placement and history paths as dragging.
let keyboardPlacementBusy = false;
async function extendByKeyboard(axis, sign) {
  const pipe = graph.pipes.find(p => pipeKey(p) === selectedPipe);
  if (!pipe) {
    message('Select a pipe in the drawing first.', true);
    return;
  }
  const version = generation, edge = selectedPipe;
  const suffix = $('hadamard').checked ? 'H' : '';
  const kinds = ['OXZ', 'OZX', 'XOZ', 'ZOX', 'XZO', 'ZXO'].filter(k => k[axis] === 'O');
  keyboardPlacementBusy = true;
  try {
    const results = await Promise.all(kinds.map(async k => ({
      kind: k + suffix,
      placements: (await api('/api/pipe-placements', {graph: clone(graph), kind: k + suffix})).placements
    })));
    if (generation !== version || selectedPipe !== edge) return;
    const choices = [];
    for (const source of [pipe.u, pipe.v]) {
      const destination = [...source];
      destination[axis] += sign;
      const id = pipeKey({u: source, v: destination});
      for (const result of results) {
        const option = result.placements.find(p => pipeKey(p) === id);
        if (option) choices.push({option, kind: result.kind, source, destination});
      }
    }
    if (!choices.length) {
      message('No valid pipe in that direction from either end. Try another direction, change H, or reopen a capped endpoint.', true);
      return;
    }
    if (choices.length === 1) {
      await placePipe(choices[0].option, choices[0].kind);
      return;
    }
    $('direction-title').textContent = `Extend in ${sign > 0 ? '+' : '−'}${'XYZ'[axis]}`;
    const list = $('direction-options');
    list.replaceChildren();
    for (const choice of choices) {
      const button = document.createElement('button');
      button.textContent = `${choice.kind} · (${choice.source.join(', ')}) → (${choice.destination.join(', ')})`;
      button.onclick = async () => {
        $('direction-dialog').close();
        if (generation !== version || selectedPipe !== edge) {
          message('Selection changed. Choose the direction again.', true);
          return;
        }
        await placePipe(choice.option, choice.kind);
      };
      list.append(button);
    }
    $('direction-dialog').showModal();
  } catch (error) {
    message(error.message, true);
  } finally {
    keyboardPlacementBusy = false;
  }
}
$('cancel-direction').onclick = () => $('direction-dialog').close();
document.addEventListener('keydown', event => {
  if (event.defaultPrevented || event.isComposing || event.repeat || event.altKey) return;
  const target = event.target;
  if (target instanceof Element && (target.closest('input, textarea, select, [role="textbox"]') || target.isContentEditable)) return;
  if (document.querySelector('dialog[open]') || drag || busy || keyboardPlacementBusy) return;
  const pressed = event.key.toLowerCase();
  if (event.ctrlKey || event.metaKey) {
    if (pressed === 'z' || pressed === 'y') {
      event.preventDefault();
      $(pressed === 'y' || event.shiftKey ? 'redo' : 'undo').click();
    }
    return;
  }
  if ($('panel-design').hidden) return;
  if ('xyz'.includes(pressed) && pressed.length === 1) {
    event.preventDefault();
    extendByKeyboard('xyz'.indexOf(pressed), event.shiftKey ? -1 : 1);
  } else if (pressed === 'delete' || pressed === 'backspace') {
    if (selectedPipe) {
      event.preventDefault();
      deletePipe(selectedPipe);
    } else if (selected) {
      event.preventDefault();
      $('delete').click();
    }
  } else if (pressed === 'escape') {
    selected = selectedPipe = null;
    render();
    message('Selection cleared.');
  } else if (pressed === 'f') {
    event.preventDefault();
    $('fit').click();
  }
});


async function capAllPortsMinimally(basis) {
  if (busy || drag || keyboardPlacementBusy || document.querySelector('dialog[open]')) return;
  busy = true;
  try {
    const result = await api('/api/cap-minimal', {graph: clone(graph), basis});
    commit(result.graph);
    message(`Capped ${result.caps.length} open ports in ${basis} basis. Undo restores all ports.`);
  } catch (error) {
    message(error.message, true);
  } finally {
    busy = false;
  }
}
$('cap-minimal-x').onclick = () => capAllPortsMinimally('X');
$('cap-minimal-z').onclick = () => capAllPortsMinimally('Z');
