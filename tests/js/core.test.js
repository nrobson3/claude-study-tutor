'use strict';
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const SG = require(path.join(__dirname, '..', '..', 'tools', 'study-graph', 'core.js'));
const { analyze, louvain, Simulation, STATUS, courseLabel } = SG;

const N = (id, o = {}) => ({ id, name: id, course: 'c1', status: 'solid', ...o });
const E = (source, target) => ({ source, target });
const names = (arr) => arr.map((n) => n.id);

function clique(prefix, k, o = {}) {
  const nodes = [], edges = [];
  for (let i = 0; i < k; i++) nodes.push(N(`${prefix}${i}`, o));
  for (let i = 0; i < k; i++) for (let j = i + 1; j < k; j++) edges.push(E(`${prefix}${i}`, `${prefix}${j}`));
  return { nodes, edges };
}

test('exports expected API', () => {
  for (const k of ['VERSION', 'STATUS', 'louvain', 'analyze', 'Simulation', 'createGraphView', 'standaloneHooks', 'courseLabel']) {
    assert.ok(k in SG, k);
  }
  assert.strictEqual(courseLabel('chem-1302'), 'Chemistry');
  assert.strictEqual(courseLabel(''), 'Other');
  assert.strictEqual(courseLabel('zzz'), 'zzz');
});

// ------------------------------------------------------------ analyze --
test('analyze: empty / null / missing fields', () => {
  for (const d of [undefined, null, {}, { nodes: null, edges: null }, { nodes: 'x' }, { nodes: [], edges: [] }]) {
    const m = analyze(d);
    assert.strictEqual(m.nodes.length, 0);
    assert.strictEqual(m.edges.length, 0);
    assert.strictEqual(m.communities.length, 0);
    assert.strictEqual(m.insights.orphanCount, 0);
    assert.deepStrictEqual(m.insights.gaps, []);
  }
});

test('analyze: node with only an id gets defaults; null nodes skipped; numeric id stringified', () => {
  const m = analyze({ nodes: [null, undefined, { id: 5 }, { name: 'noid' }, { id: null }, { id: 'a', aliases: 'nope' }], edges: [null, {}, undefined] });
  assert.deepStrictEqual(names(m.nodes), ['5', 'a']);
  const n = m.nodes[0];
  assert.strictEqual(n.name, '5');
  assert.strictEqual(n.course, '');
  assert.strictEqual(n.status, 'unknown');
  assert.strictEqual(n.kind, '');
  assert.strictEqual(n.statement, '');
  assert.deepStrictEqual(n.aliases, []);
  assert.strictEqual(n.slide, '');
  assert.deepStrictEqual(m.nodes[1].aliases, []);
  assert.strictEqual(m.edges.length, 0);
});

test('analyze: id 0 and empty-string id are kept (only null/undefined dropped)', () => {
  const m = analyze({ nodes: [{ id: 0 }, { id: '' }] });
  assert.deepStrictEqual(names(m.nodes), ['0', '']);
});

test('analyze: aliases are stringified', () => {
  const m = analyze({ nodes: [N('a', { aliases: [1, 'x'] })] });
  assert.deepStrictEqual(m.nodes[0].aliases, ['1', 'x']);
});

test('analyze: duplicate ids keep the first', () => {
  const m = analyze({ nodes: [N('a', { name: 'First' }), N('a', { name: 'Second' }), N('b')] });
  assert.strictEqual(m.nodes.length, 2);
  assert.strictEqual(m.byId.get('a').name, 'First');
  assert.deepStrictEqual(m.nodes.map((n) => n.index), [0, 1]);
});

test('analyze: self edges, duplicate edges and unknown ids are dropped', () => {
  const m = analyze({
    nodes: [N('a'), N('b')],
    edges: [E('a', 'a'), E('a', 'b'), E('a', 'b'), E('a', 'zzz'), E('zzz', 'a'), E('zzz', 'yyy')],
  });
  assert.strictEqual(m.edges.length, 1);
  const a = m.byId.get('a'), b = m.byId.get('b');
  assert.deepStrictEqual(a.premises, [b]);
  assert.deepStrictEqual(b.dependents, [a]);
  assert.strictEqual(a.degree, 1);
  assert.strictEqual(b.degree, 1);
});

test('analyze: reciprocal edges a->b and b->a both kept but neighbour counted once', () => {
  const m = analyze({ nodes: [N('a'), N('b')], edges: [E('a', 'b'), E('b', 'a')] });
  assert.strictEqual(m.edges.length, 2);
  assert.strictEqual(m.byId.get('a').degree, 1);
  assert.strictEqual(m.byId.get('a').neighbors.length, 1);
});

test('analyze: edge endpoints coerced to strings', () => {
  const m = analyze({ nodes: [{ id: 1 }, { id: 2 }], edges: [{ source: 1, target: 2 }] });
  assert.strictEqual(m.edges.length, 1);
});

test('analyze: unknown / missing status -> unknown; known preserved; prototype keys rejected', () => {
  const m = analyze({ nodes: [
    N('a', { status: 'solid' }), N('b', { status: 'shaky' }), N('c', { status: 'not-yet' }),
    N('d', { status: 'great' }), N('e', { status: undefined }), N('f', { status: null }),
    N('g', { status: 'toString' }), N('h', { status: 'hasOwnProperty' }), N('i', { status: '__proto__' }),
  ] });
  const s = Object.fromEntries(m.nodes.map((n) => [n.id, n.status]));
  assert.deepStrictEqual(s, { a: 'solid', b: 'shaky', c: 'not-yet', d: 'unknown', e: 'unknown', f: 'unknown', g: 'unknown', h: 'unknown', i: 'unknown' });
  assert.strictEqual(m.counts.unknown, 6);
  for (const n of m.nodes) assert.ok(STATUS[n.status]);
});

test('analyze: reach = transitive dependents (chain)', () => {
  // x follows from y follows from z  => z has 2 dependents transitively
  const m = analyze({ nodes: [N('x'), N('y'), N('z')], edges: [E('x', 'y'), E('y', 'z')] });
  assert.strictEqual(m.byId.get('z').reach, 2);
  assert.strictEqual(m.byId.get('y').reach, 1);
  assert.strictEqual(m.byId.get('x').reach, 0);
});

test('analyze: reach counts diamond dependents once', () => {
  const m = analyze({
    nodes: [N('top'), N('l'), N('r'), N('base')],
    edges: [E('top', 'l'), E('top', 'r'), E('l', 'base'), E('r', 'base')],
  });
  assert.strictEqual(m.byId.get('base').reach, 3);
});

test('analyze: cycles terminate with correct reach (3-cycle)', () => {
  const m = analyze({ nodes: [N('a'), N('b'), N('c')], edges: [E('a', 'b'), E('b', 'c'), E('c', 'a')] });
  for (const n of m.nodes) assert.strictEqual(n.reach, 2, n.id);
});

test('analyze: 2-cycle with a tail; start node not counted in own reach', () => {
  const m = analyze({ nodes: [N('a'), N('b'), N('t')], edges: [E('a', 'b'), E('b', 'a'), E('t', 'a')] });
  assert.strictEqual(m.byId.get('a').reach, 2); // b and t
  assert.strictEqual(m.byId.get('b').reach, 2); // a and (t via a)
  assert.strictEqual(m.byId.get('t').reach, 0);
});

test('analyze: long chain does not overflow the stack', () => {
  const nodes = [], edges = [];
  for (let i = 0; i < 3000; i++) { nodes.push(N('n' + i)); if (i) edges.push(E('n' + i, 'n' + (i - 1))); }
  const m = analyze({ nodes, edges });
  assert.strictEqual(m.byId.get('n0').reach, 2999);
});

test('analyze: degree, premises, dependents', () => {
  const m = analyze({
    nodes: [N('a'), N('b'), N('c'), N('d')],
    edges: [E('a', 'b'), E('a', 'c'), E('d', 'a')],
  });
  const a = m.byId.get('a');
  assert.deepStrictEqual(names(a.premises), ['b', 'c']);
  assert.deepStrictEqual(names(a.dependents), ['d']);
  assert.strictEqual(a.degree, 3);
  assert.strictEqual(m.byId.get('b').degree, 1);
});

test('analyze: frontier = not-yet/unknown, all premises solid, not in missing', () => {
  const m = analyze({
    nodes: [
      N('base', { status: 'solid' }),
      N('ready', { status: 'not-yet' }),
      N('readyUnk', { status: 'weird' }),
      N('leaf', { status: 'not-yet' }),
      N('shakyBase', { status: 'shaky' }),
      N('blocked', { status: 'not-yet' }),
      N('missingOne', { status: 'not-yet' }),
      N('studiedDep', { status: 'solid' }),
      N('notYetDep', { status: 'not-yet' }),
      N('target', { status: 'not-yet' }),
    ],
    edges: [
      E('ready', 'base'), E('readyUnk', 'base'), E('blocked', 'shakyBase'),
      E('studiedDep', 'missingOne'), E('notYetDep', 'target'),
    ],
  });
  const f = names(m.insights.frontier);
  assert.ok(f.includes('ready'));
  assert.ok(f.includes('readyUnk'));
  assert.ok(f.includes('leaf'));
  assert.ok(f.includes('target'));
  assert.ok(!f.includes('blocked'));
  assert.ok(!f.includes('missingOne'));
  assert.ok(!f.includes('base'));
  assert.ok(!f.includes('shakyBase'));
  assert.ok(!f.includes('studiedDep'));
  assert.deepStrictEqual(names(m.insights.missing), ['missingOne']);
});

test('analyze: missing = not-yet with a studied (solid OR shaky) dependent; sorted by reach', () => {
  const m = analyze({
    nodes: [
      N('m1', { status: 'not-yet' }), N('m2', { status: 'unknown' }), N('m3', { status: 'not-yet' }),
      N('s', { status: 'solid' }), N('sh', { status: 'shaky' }), N('ny', { status: 'not-yet' }),
      N('deep', { status: 'solid' }),
    ],
    edges: [E('s', 'm1'), E('sh', 'm2'), E('ny', 'm3'), E('deep', 's')],
  });
  assert.deepStrictEqual(names(m.insights.missing), ['m1', 'm2']);
});

test('analyze: shaky insight = shaky with reach > 0', () => {
  const m = analyze({
    nodes: [N('sh1', { status: 'shaky' }), N('sh0', { status: 'shaky' }), N('dep', { status: 'solid' }), N('sol', { status: 'solid' })],
    edges: [E('dep', 'sh1'), E('sol', 'dep')],
  });
  assert.deepStrictEqual(names(m.insights.shaky), ['sh1']);
});

test('analyze: insight lists capped (8 / 12) and orphanCount is full count', () => {
  const nodes = [];
  for (let i = 0; i < 30; i++) nodes.push(N('o' + i, { status: 'not-yet' }));
  const m = analyze({ nodes, edges: [] });
  assert.strictEqual(m.insights.orphans.length, 12);
  assert.strictEqual(m.insights.orphanCount, 30);
  assert.strictEqual(m.insights.frontier.length, 8);
});

test('analyze: hubs ordered by degree desc then reach; orphans excluded', () => {
  const m = analyze({
    nodes: [N('a'), N('b'), N('c'), N('d'), N('lone')],
    edges: [E('b', 'a'), E('c', 'a'), E('d', 'a'), E('c', 'b')],
  });
  const h = names(m.insights.hubs);
  assert.strictEqual(h[0], 'a');
  assert.ok(!h.includes('lone'));
  // b and c both degree 2; b reach=1 (c), c reach 0 -> b before c
  assert.ok(h.indexOf('b') < h.indexOf('c'));
});

test('analyze: bridges = has a neighbour in another course', () => {
  const m = analyze({
    nodes: [N('a', { course: 'x' }), N('b', { course: 'y' }), N('c', { course: 'x' }), N('d', { course: 'x' })],
    edges: [E('a', 'b'), E('c', 'd')],
  });
  assert.deepStrictEqual(names(m.insights.bridges).sort(), ['a', 'b']);
});

test('analyze: orphans (degree 0) sorted by name; orphanCount', () => {
  const m = analyze({ nodes: [N('z'), N('m'), N('a'), N('p'), N('q')], edges: [E('p', 'q')] });
  assert.deepStrictEqual(names(m.insights.orphans), ['a', 'm', 'z']);
  assert.strictEqual(m.insights.orphanCount, 3);
});

test('analyze: orphan after dropped edges (self / unknown) still orphan', () => {
  const m = analyze({ nodes: [N('a')], edges: [E('a', 'a'), E('a', 'q')] });
  assert.strictEqual(m.insights.orphanCount, 1);
});

test('analyze: every node gets a community; communities sorted largest first and cover all nodes', () => {
  const a = clique('a', 6), b = clique('b', 4);
  const nodes = [...a.nodes, ...b.nodes, N('lone1'), N('lone2')];
  const m = analyze({ nodes, edges: [...a.edges, ...b.edges, E('a0', 'b0')] });
  for (const n of m.nodes) assert.ok(Number.isInteger(n.community), n.id);
  const sizes = m.communities.map((c) => c.size);
  assert.deepStrictEqual(sizes, [...sizes].sort((x, y) => y - x));
  assert.strictEqual(sizes.reduce((x, y) => x + y, 0), nodes.length);
  m.communities.forEach((c, i) => { assert.strictEqual(c.id, i); for (const mem of c.members) assert.strictEqual(mem.community, i); });
  assert.strictEqual(m.communities[0].size, 6);
  assert.ok(m.communities[0].hubs.length <= 3);
  assert.strictEqual(typeof m.communities[0].label, 'string');
});

function twoClusters(links) {
  const a = clique('a', 5, { course: 'x' }), b = clique('b', 5, { course: 'y' });
  const edges = [...a.edges, ...b.edges];
  for (let i = 0; i < links; i++) edges.push(E(`a${i}`, `b${i}`));
  return analyze({ nodes: [...a.nodes, ...b.nodes], edges });
}

test('analyze gaps: two dense clusters with 0 links appear', () => {
  const m = twoClusters(0);
  assert.strictEqual(m.communities.filter((c) => c.size >= 3).length, 2);
  assert.strictEqual(m.insights.gaps.length, 1);
  assert.strictEqual(m.insights.gaps[0].links, 0);
});

test('analyze gaps: 1 link appears', () => {
  const m = twoClusters(1);
  assert.strictEqual(m.insights.gaps.length, 1);
  assert.strictEqual(m.insights.gaps[0].links, 1);
});

test('analyze gaps: 2+ links do not appear', () => {
  for (const k of [2, 3]) {
    const m = twoClusters(k);
    assert.strictEqual(m.communities.length, 2, `k=${k} communities`);
    assert.strictEqual(m.insights.gaps.length, 0, `k=${k}`);
  }
});

test('analyze gaps: clusters smaller than 3 never produce gaps; capped at 3', () => {
  const m = analyze({ nodes: [N('a'), N('b'), N('c'), N('d')], edges: [E('a', 'b'), E('c', 'd')] });
  assert.deepStrictEqual(m.insights.gaps, []);
  let nodes = [], edges = [];
  for (let k = 0; k < 5; k++) { const c = clique('t' + k + '_', 3); nodes = nodes.concat(c.nodes); edges = edges.concat(c.edges); }
  const m2 = analyze({ nodes, edges });
  assert.strictEqual(m2.insights.gaps.length, 3);
});

test('analyze: courseStats / counts consistent', () => {
  const m = analyze({ nodes: [N('a', { course: 'chem-1302' }), N('b', { course: 'calc-1412', status: 'shaky' }), N('c', { course: 'calc-1412', status: 'x' })] });
  assert.strictEqual(m.courseStats.length, 2);
  assert.deepStrictEqual(m.counts, { solid: 1, shaky: 1, 'not-yet': 0, unknown: 1 });
  const calc = m.courseStats.find((c) => c.course === 'calc-1412');
  assert.strictEqual(calc.total, 2);
  assert.strictEqual(calc.label, 'Calculus');
});

test('analyze: larger random graph is fast and consistent', () => {
  let seed = 7; const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
  const nodes = [], edges = [];
  for (let i = 0; i < 1500; i++) nodes.push(N('n' + i, { course: 'c' + (i % 5), status: ['solid', 'shaky', 'not-yet', 'x'][i % 4] }));
  for (let i = 0; i < 4000; i++) edges.push(E('n' + Math.floor(rnd() * 1500), 'n' + Math.floor(rnd() * 1500)));
  const t = Date.now();
  const m = analyze({ nodes, edges });
  assert.ok(Date.now() - t < 10000);
  assert.strictEqual(m.communities.reduce((s, c) => s + c.size, 0), 1500);
  for (const n of m.nodes) assert.ok(Number.isInteger(n.community) && n.reach >= 0);
});

// ------------------------------------------------------------ louvain --
test('louvain: two 5-cliques joined by one edge -> 2 communities', () => {
  const pairs = [];
  for (let i = 0; i < 5; i++) for (let j = i + 1; j < 5; j++) { pairs.push([i, j]); pairs.push([5 + i, 5 + j]); }
  pairs.push([0, 5]);
  const c = louvain(10, pairs);
  assert.strictEqual(new Set(c).size, 2);
  assert.strictEqual(new Set(c.slice(0, 5)).size, 1);
  assert.strictEqual(new Set(c.slice(5)).size, 1);
  assert.notStrictEqual(c[0], c[9]);
});

test('louvain: empty graph', () => {
  assert.deepStrictEqual(louvain(0, []), []);
  assert.deepStrictEqual(louvain(0, [[0, 1]]), []);
});

test('louvain: isolated nodes each in own community', () => {
  const c = louvain(4, []);
  assert.strictEqual(c.length, 4);
  assert.strictEqual(new Set(c).size, 4);
});

test('louvain: out-of-range indices, negatives and self-pairs ignored', () => {
  const c = louvain(3, [[0, 1], [1, 7], [-1, 0], [2, 2], [5, 6]]);
  assert.strictEqual(c.length, 3);
  assert.strictEqual(c[0], c[1]);
  assert.notStrictEqual(c[2], c[0]);
});

test('louvain: only out-of-range pairs -> all singletons', () => {
  const c = louvain(2, [[0, 5], [9, 1]]);
  assert.strictEqual(new Set(c).size, 2);
});

test('louvain: single node; connected pair merges', () => {
  assert.deepStrictEqual(louvain(1, []), [0]);
  const c = louvain(2, [[0, 1]]);
  assert.strictEqual(c[0], c[1]);
});

test('louvain: duplicate pairs do not crash', () => {
  const c = louvain(3, [[0, 1], [0, 1], [1, 0], [1, 2]]);
  assert.strictEqual(c.length, 3);
});

// ---------------------------------------------------------- Simulation --
function mkSimNodes(n, spread, rnd) {
  return Array.from({ length: n }, (_, i) => ({ id: 'n' + i, index: i, x: (rnd() - 0.5) * spread, y: (rnd() - 0.5) * spread, vx: 0, vy: 0, course: 'c' + (i % 3) }));
}
const finite = (nodes) => nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y) && Number.isFinite(n.vx) && Number.isFinite(n.vy));

test('Simulation: 200 random nodes, 300 ticks, all finite', () => {
  let seed = 3; const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
  const nodes = mkSimNodes(200, 400, rnd);
  const links = [];
  for (let i = 0; i < 300; i++) links.push({ source: nodes[Math.floor(rnd() * 200)], target: nodes[Math.floor(rnd() * 200)] });
  const sim = new Simulation();
  sim.groupOf = (n) => n.course;
  sim.setGraph(nodes, links.filter((l) => l.source !== l.target));
  const t = Date.now();
  for (let i = 0; i < 300; i++) sim.tick();
  assert.ok(finite(nodes));
  assert.ok(Date.now() - t < 5000, 'too slow');
});

test('Simulation: coincident nodes at (0,0) stay finite and separate', () => {
  const nodes = Array.from({ length: 50 }, (_, i) => ({ id: 'n' + i, index: i, x: 0, y: 0, vx: 0, vy: 0 }));
  const sim = new Simulation();
  sim.setGraph(nodes, []);
  for (let i = 0; i < 300; i++) sim.tick();
  assert.ok(finite(nodes));
  const pos = new Set(nodes.map((n) => n.x.toFixed(4) + ',' + n.y.toFixed(4)));
  assert.ok(pos.size > 1, 'coincident nodes never separated');
});

test('Simulation: coincident linked nodes stay finite', () => {
  const nodes = [0, 1, 2].map((i) => ({ id: 'n' + i, index: i, x: 5, y: 5, vx: 0, vy: 0 }));
  const sim = new Simulation();
  sim.setGraph(nodes, [{ source: nodes[0], target: nodes[1] }, { source: nodes[1], target: nodes[2] }]);
  for (let i = 0; i < 200; i++) sim.tick();
  assert.ok(finite(nodes));
});

test('Simulation: single node and empty graph', () => {
  const one = [{ id: 'a', index: 0, x: 0, y: 0, vx: 0, vy: 0 }];
  const sim = new Simulation();
  sim.setGraph(one, []);
  for (let i = 0; i < 100; i++) sim.tick();
  assert.ok(finite(one));
  const s2 = new Simulation();
  s2.setGraph([], []);
  s2.tick();
});

test('Simulation: single node away from origin is pulled toward centre', () => {
  const one = [{ id: 'a', index: 0, x: 100, y: -100, vx: 0, vy: 0 }];
  const sim = new Simulation();
  sim.setGraph(one, []);
  for (let i = 0; i < 100; i++) sim.tick();
  assert.ok(Math.abs(one[0].x) < 100 && Math.abs(one[0].y) < 100);
});

test('Simulation: fixed nodes (fx/fy) stay put', () => {
  let seed = 11; const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
  const nodes = mkSimNodes(40, 200, rnd);
  nodes[0].fx = 50; nodes[0].fy = -30;
  nodes[1].fx = 7; // only x fixed
  const sim = new Simulation();
  sim.setGraph(nodes, [{ source: nodes[0], target: nodes[2] }, { source: nodes[1], target: nodes[3] }]);
  const y1 = nodes[1].y;
  for (let i = 0; i < 200; i++) sim.tick();
  assert.strictEqual(nodes[0].x, 50);
  assert.strictEqual(nodes[0].y, -30);
  assert.strictEqual(nodes[1].x, 7);
  assert.notStrictEqual(nodes[1].y, y1, 'unfixed axis should move');
  assert.ok(finite(nodes));
});

test('Simulation: alpha cools, active flips off, reheat raises it', () => {
  const nodes = [{ id: 'a', index: 0, x: 1, y: 1, vx: 0, vy: 0 }, { id: 'b', index: 1, x: -1, y: 2, vx: 0, vy: 0 }];
  const sim = new Simulation();
  sim.setGraph(nodes, []);
  assert.ok(sim.active);
  for (let i = 0; i < 400; i++) sim.tick();
  assert.ok(!sim.active);
  sim.reheat(0.5);
  assert.ok(sim.active);
  sim.reheat(0.1);
  assert.strictEqual(sim.alpha, 0.5);
});

test('Simulation: setGraph computes link strength/bias; alphaTarget keeps active', () => {
  const a = { id: 'a', index: 0, x: 0, y: 0, vx: 0, vy: 0 }, b = { id: 'b', index: 1, x: 10, y: 0, vx: 0, vy: 0 }, c = { id: 'c', index: 2, x: 20, y: 0, vx: 0, vy: 0 };
  const l1 = { source: a, target: b }, l2 = { source: b, target: c };
  const sim = new Simulation();
  sim.setGraph([a, b, c], [l1, l2]);
  assert.strictEqual(l1.strength, 1);
  assert.strictEqual(l1.bias, 1 / 3);
  sim.alpha = 0;
  sim.alphaTarget = 0.25;
  assert.ok(sim.active);
});

test('Simulation: many near-coincident nodes beyond quadtree depth limit stay finite', () => {
  const nodes = Array.from({ length: 300 }, (_, i) => ({ id: 'n' + i, index: i, x: 1e-9 * (i % 3), y: 0, vx: 0, vy: 0 }));
  const sim = new Simulation();
  sim.setGraph(nodes, []);
  for (let i = 0; i < 50; i++) sim.tick();
  assert.ok(finite(nodes));
});

test('Simulation: analyze output feeds Simulation end to end', () => {
  const a = clique('a', 5), b = clique('b', 5);
  const m = analyze({ nodes: [...a.nodes, ...b.nodes], edges: [...a.edges, ...b.edges, E('a0', 'b0')] });
  m.nodes.forEach((n, i) => { n.x = Math.cos(i) * 20; n.y = Math.sin(i) * 20; n.vx = 0; n.vy = 0; });
  const sim = new Simulation();
  sim.groupOf = (n) => n.community;
  sim.setGraph(m.nodes, m.edges);
  for (let i = 0; i < 300; i++) sim.tick();
  assert.ok(finite(m.nodes));
});
