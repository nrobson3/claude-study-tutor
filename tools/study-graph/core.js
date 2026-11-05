/* Study Graph: a knowledge-graph visualiser for the study vault.
 *
 * One engine, two hosts:
 *   - the Obsidian plugin (.obsidian/plugins/study-graph, built by scripts/study_graph.py build)
 *   - a standalone page   (.cache/study-graph.html, built by scripts/study_graph.py html)
 *
 * Data in:  { nodes: [{id, name, course, status, kind, statement, aliases, slide}],
 *             edges: [{source, target}]   // source "follows from" target (target is the premise)
 *             vault: "study-vault" }
 *
 * No dependencies: a d3-style force simulation with a Barnes-Hut quadtree, Louvain
 * communities, canvas rendering with glow sprites, and an "Insight" panel that turns the
 * graph structure into study advice (what to learn next, shaky foundations, gaps).
 */
function StudyGraphFactory() {
  'use strict';

  const VERSION = '0.1.0';
  const STATUS = {
    solid: { label: 'Solid', color: '#3FA45B' },
    shaky: { label: 'Shaky', color: '#E8A33D' },
    'not-yet': { label: 'Not yet', color: '#7E8696' },
    unknown: { label: 'No status', color: '#5C6370' },
  };
  const STATUS_ORDER = ['solid', 'shaky', 'not-yet', 'unknown'];
  const PALETTE = ['#5B8DEF', '#F2555A', '#F5C542', '#3DBE8B', '#A47CF3', '#F28C38', '#2EC4C4',
    '#EC6FB5', '#9BD15B', '#7F8CFF', '#E0A96D', '#56B6C2'];
  const LONE = '#4B5260';
  const COURSE_NAMES = {
    'chem-1302': 'Chemistry', 'calc-1412': 'Calculus', 'phys-1401': 'Physics',
    'materials-1021': 'Materials', 'statics-1022': 'Statics', 'eng-1050': 'Foundations',
    'bus-1299': 'Business',
  };
  const courseLabel = (c) => COURSE_NAMES[c] || c || 'Other';
  const studied = (s) => s === 'solid' || s === 'shaky';

  // ------------------------------------------------------------ analysis --

  /** Louvain community detection on an undirected, unweighted edge list. Returns a community index per node. */
  function louvain(n, pairs) {
    let membership = Array.from({ length: n }, (_, i) => i);
    if (n === 0) return membership;
    let size = n;
    let adj = Array.from({ length: n }, () => new Map());
    for (const [a, b] of pairs) {
      if (a === b || a < 0 || b < 0 || a >= n || b >= n) continue;
      adj[a].set(b, (adj[a].get(b) || 0) + 1);
      adj[b].set(a, (adj[b].get(a) || 0) + 1);
    }
    let self = new Float64Array(n);
    for (let level = 0; level < 12; level++) {
      const k = new Float64Array(size);
      let m2 = 0;
      for (let i = 0; i < size; i++) {
        let s = self[i] * 2;
        for (const w of adj[i].values()) s += w;
        k[i] = s;
        m2 += s;
      }
      if (m2 === 0) break;
      const c = Array.from({ length: size }, (_, i) => i);
      const tot = Float64Array.from(k);
      let moved = false;
      for (let pass = 0; pass < 25; pass++) {
        let improved = false;
        for (let i = 0; i < size; i++) {
          const ci = c[i];
          const wTo = new Map();
          for (const [j, w] of adj[i]) wTo.set(c[j], (wTo.get(c[j]) || 0) + w);
          tot[ci] -= k[i];
          let best = ci;
          let bestGain = (wTo.get(ci) || 0) - (tot[ci] * k[i]) / m2;
          for (const [cc, w] of wTo) {
            const gain = w - (tot[cc] * k[i]) / m2;
            if (gain > bestGain + 1e-12) { bestGain = gain; best = cc; }
          }
          tot[best] += k[i];
          if (best !== ci) { c[i] = best; improved = true; moved = true; }
        }
        if (!improved) break;
      }
      if (!moved) break;
      const remap = new Map();
      for (let i = 0; i < size; i++) if (!remap.has(c[i])) remap.set(c[i], remap.size);
      membership = membership.map((s) => remap.get(c[s]));
      const next = remap.size;
      const nadj = Array.from({ length: next }, () => new Map());
      const nself = new Float64Array(next);
      for (let i = 0; i < size; i++) {
        const ci = remap.get(c[i]);
        nself[ci] += self[i];
        for (const [j, w] of adj[i]) {
          const cj = remap.get(c[j]);
          if (ci === cj) nself[ci] += w / 2;
          else nadj[ci].set(cj, (nadj[ci].get(cj) || 0) + w);
        }
      }
      adj = nadj;
      self = nself;
      size = next;
    }
    return membership;
  }

  function reachCount(start, key) {
    const seen = new Set([start]);
    const stack = [start];
    while (stack.length) {
      const n = stack.pop();
      for (const m of n[key]) if (!seen.has(m)) { seen.add(m); stack.push(m); }
    }
    return seen.size - 1;
  }

  function reachSet(start, key) {
    const seen = new Set([start]);
    const stack = [start];
    while (stack.length) {
      const n = stack.pop();
      for (const m of n[key]) if (!seen.has(m)) { seen.add(m); stack.push(m); }
    }
    seen.delete(start);
    return seen;
  }

  /** Normalise the data and compute structure plus study insights. Pure: no DOM. */
  function analyze(data) {
    const raw = (data && Array.isArray(data.nodes)) ? data.nodes : [];
    const nodes = [];
    const byId = new Map();
    for (const r of raw) {
      if (!r || r.id == null || byId.has(String(r.id))) continue;
      const n = {
        id: String(r.id),
        name: String(r.name || r.id),
        course: String(r.course || ''),
        status: Object.prototype.hasOwnProperty.call(STATUS, r.status) ? r.status : 'unknown',
        kind: String(r.kind || ''),
        statement: String(r.statement || ''),
        aliases: Array.isArray(r.aliases) ? r.aliases.map(String) : [],
        slide: String(r.slide || ''),
        index: nodes.length,
        premises: [], dependents: [], neighbors: [],
      };
      nodes.push(n);
      byId.set(n.id, n);
    }
    const edges = [];
    const seen = new Set();
    for (const e of (data && Array.isArray(data.edges)) ? data.edges : []) {
      if (!e) continue;
      const s = byId.get(String(e.source));
      const t = byId.get(String(e.target));
      if (!s || !t || s === t) continue;
      const key = s.index + '>' + t.index;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({ source: s, target: t });
      s.premises.push(t);
      t.dependents.push(s);
    }
    for (const n of nodes) {
      n.neighbors = [...new Set([...n.premises, ...n.dependents])];
      n.degree = n.neighbors.length;
    }
    for (const n of nodes) n.reach = reachCount(n, 'dependents');

    // Communities ("topic clusters"), relabelled largest first.
    const member = louvain(nodes.length, edges.map((e) => [e.source.index, e.target.index]));
    const groups = new Map();
    nodes.forEach((n, i) => {
      if (!groups.has(member[i])) groups.set(member[i], []);
      groups.get(member[i]).push(n);
    });
    const communities = [...groups.values()]
      .sort((a, b) => b.length - a.length || a[0].name.localeCompare(b[0].name))
      .map((members, id) => {
        const hubs = members.slice().sort((a, b) => b.degree - a.degree || b.reach - a.reach || a.name.localeCompare(b.name));
        for (const m of members) m.community = id;
        const courseCount = {};
        for (const m of members) courseCount[m.course] = (courseCount[m.course] || 0) + 1;
        const course = Object.keys(courseCount).sort((a, b) => courseCount[b] - courseCount[a])[0];
        return { id, members, size: members.length, hubs: hubs.slice(0, 3), label: hubs.slice(0, 2).map((h) => h.name).join(' · '), course };
      });

    const courses = [...new Set(nodes.map((n) => n.course))].sort((a, b) => courseLabel(a).localeCompare(courseLabel(b)));
    const courseStats = courses.map((c) => {
      const members = nodes.filter((n) => n.course === c);
      const counts = {};
      for (const s of STATUS_ORDER) counts[s] = members.filter((n) => n.status === s).length;
      return { course: c, label: courseLabel(c), total: members.length, counts };
    });
    const counts = {};
    for (const s of STATUS_ORDER) counts[s] = nodes.filter((n) => n.status === s).length;

    const byImpact = (a, b) => b.reach - a.reach || b.degree - a.degree || a.name.localeCompare(b.name);
    const notYet = (n) => n.status === 'not-yet' || n.status === 'unknown';
    // Missing foundations: not studied, yet ideas you have studied rest on them. More urgent, so listed once, here.
    const missing = nodes.filter((n) => notYet(n) && n.dependents.some((d) => studied(d.status))).sort(byImpact);
    const missingSet = new Set(missing);
    // Ready to learn: not studied, and everything they rest on is solid.
    const frontier = nodes
      .filter((n) => notYet(n) && !missingSet.has(n) && n.premises.every((p) => p.status === 'solid'))
      .sort(byImpact);
    const shaky = nodes.filter((n) => n.status === 'shaky' && n.reach > 0).sort(byImpact);
    const hubs = nodes.filter((n) => n.degree > 0).sort((a, b) => b.degree - a.degree || b.reach - a.reach || a.name.localeCompare(b.name));
    const bridges = nodes
      .filter((n) => n.neighbors.some((m) => m.course !== n.course))
      .sort((a, b) => b.degree - a.degree || a.name.localeCompare(b.name));
    const orphans = nodes.filter((n) => n.degree === 0).sort((a, b) => a.name.localeCompare(b.name));

    // Structural gaps: two sizeable topic clusters with (almost) nothing connecting them.
    const big = communities.filter((c) => c.size >= 3).slice(0, 14);
    const between = new Map();
    for (const e of edges) {
      const a = e.source.community, b = e.target.community;
      if (a === b) continue;
      const key = Math.min(a, b) + ':' + Math.max(a, b);
      between.set(key, (between.get(key) || 0) + 1);
    }
    const gaps = [];
    for (let i = 0; i < big.length; i++) {
      for (let j = i + 1; j < big.length; j++) {
        const a = big[i], b = big[j];
        const links = between.get(Math.min(a.id, b.id) + ':' + Math.max(a.id, b.id)) || 0;
        if (links > 1) continue;
        gaps.push({ a, b, links, score: Math.min(a.size, b.size) * (a.course === b.course ? 1.5 : 1) - links * 2 });
      }
    }
    gaps.sort((x, y) => y.score - x.score);

    return {
      nodes, edges, byId, communities, courses, courseStats, counts,
      insights: {
        frontier: frontier.slice(0, 8), shaky: shaky.slice(0, 8), missing: missing.slice(0, 8),
        hubs: hubs.slice(0, 8), bridges: bridges.slice(0, 8), orphans: orphans.slice(0, 12),
        orphanCount: orphans.length, gaps: gaps.slice(0, 3),
      },
    };
  }

  // ---------------------------------------------------------- simulation --

  function quadInsert(q, n, depth) {
    if (q.kids === null) {
      if (q.pts === null) { q.pts = [n]; return; }
      if (depth > 16) { q.pts.push(n); return; }
      const old = q.pts;
      q.pts = null;
      q.kids = [null, null, null, null];
      for (const p of old) quadPush(q, p, depth);
    }
    quadPush(q, n, depth);
  }

  function quadPush(q, n, depth) {
    const h = q.size / 2;
    const i = (n.x >= q.x0 + h ? 1 : 0) + (n.y >= q.y0 + h ? 2 : 0);
    if (!q.kids[i]) {
      q.kids[i] = { x0: q.x0 + (i & 1 ? h : 0), y0: q.y0 + (i & 2 ? h : 0), size: h, kids: null, pts: null, mass: 0, cx: 0, cy: 0 };
    }
    quadInsert(q.kids[i], n, depth + 1);
  }

  function quadMass(q) {
    if (q.kids === null) {
      let sx = 0, sy = 0;
      for (const p of q.pts) { sx += p.x; sy += p.y; }
      q.mass = q.pts.length;
      q.cx = sx / q.mass;
      q.cy = sy / q.mass;
      return;
    }
    let m = 0, sx = 0, sy = 0;
    for (const k of q.kids) if (k) { quadMass(k); m += k.mass; sx += k.cx * k.mass; sy += k.cy * k.mass; }
    q.mass = m;
    q.cx = sx / m;
    q.cy = sy / m;
  }

  function quadApply(q, n, sa, theta2) {
    if (q.kids === null) {
      for (const p of q.pts) {
        if (p === n) continue;
        let x = p.x - n.x, y = p.y - n.y, l = x * x + y * y;
        if (l < 1) { x = (n.index - p.index) * 1e-3 || 1e-3; y = 1e-3; l = 1; }
        n.vx += (x * sa) / l;
        n.vy += (y * sa) / l;
      }
      return;
    }
    const dx = q.cx - n.x, dy = q.cy - n.y;
    let d2 = dx * dx + dy * dy;
    if ((q.size * q.size) / theta2 < d2) {
      if (d2 < 1) d2 = 1;
      n.vx += (dx * q.mass * sa) / d2;
      n.vy += (dy * q.mass * sa) / d2;
      return;
    }
    for (const k of q.kids) if (k) quadApply(k, n, sa, theta2);
  }

  class Simulation {
    constructor() {
      this.nodes = [];
      this.links = [];
      this.alpha = 1;
      this.alphaMin = 0.002;
      this.alphaDecay = 1 - Math.pow(this.alphaMin, 1 / 320);
      this.alphaTarget = 0;
      this.velocityDecay = 0.42;
      this.params = { repel: 70, distance: 34, center: 0.035, cluster: 0.06 };
      this.groupOf = () => 0;
    }
    setGraph(nodes, links) {
      this.nodes = nodes;
      this.links = links;
      const count = new Map();
      for (const l of links) {
        count.set(l.source, (count.get(l.source) || 0) + 1);
        count.set(l.target, (count.get(l.target) || 0) + 1);
      }
      for (const l of links) {
        const cs = count.get(l.source), ct = count.get(l.target);
        l.bias = cs / (cs + ct);
        l.strength = 1 / Math.min(cs, ct);
      }
    }
    reheat(alpha) { this.alpha = Math.max(this.alpha, alpha); }
    get active() { return this.alpha > this.alphaMin || this.alphaTarget > 0; }
    tick() {
      const nodes = this.nodes;
      if (!nodes.length) return;
      this.alpha += (this.alphaTarget - this.alpha) * this.alphaDecay;
      const alpha = this.alpha;
      const P = this.params;

      for (const l of this.links) {
        const s = l.source, t = l.target;
        let x = t.x + t.vx - s.x - s.vx, y = t.y + t.vy - s.y - s.vy;
        let len = Math.sqrt(x * x + y * y) || 1e-6;
        len = ((len - P.distance) / len) * alpha * l.strength;
        x *= len; y *= len;
        t.vx -= x * l.bias; t.vy -= y * l.bias;
        s.vx += x * (1 - l.bias); s.vy += y * (1 - l.bias);
      }

      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const n of nodes) {
        if (n.x < x0) x0 = n.x; if (n.y < y0) y0 = n.y;
        if (n.x > x1) x1 = n.x; if (n.y > y1) y1 = n.y;
      }
      const root = { x0, y0, size: Math.max(x1 - x0, y1 - y0, 1) * 1.0001, kids: null, pts: null, mass: 0, cx: 0, cy: 0 };
      for (const n of nodes) quadInsert(root, n, 0);
      quadMass(root);
      const sa = -P.repel * alpha;
      for (const n of nodes) quadApply(root, n, sa, 0.81);

      if (P.cluster > 0) {
        const sums = new Map();
        for (const n of nodes) {
          const g = this.groupOf(n);
          const s = sums.get(g) || { x: 0, y: 0, c: 0 };
          s.x += n.x; s.y += n.y; s.c++;
          sums.set(g, s);
        }
        for (const n of nodes) {
          const s = sums.get(this.groupOf(n));
          if (s.c < 2) continue;
          n.vx += (s.x / s.c - n.x) * P.cluster * alpha;
          n.vy += (s.y / s.c - n.y) * P.cluster * alpha;
        }
      }
      for (const n of nodes) {
        n.vx -= n.x * P.center * alpha;
        n.vy -= n.y * P.center * alpha;
      }
      for (const n of nodes) {
        if (n.fx != null) { n.x = n.fx; n.vx = 0; } else { n.vx *= 1 - this.velocityDecay; n.x += n.vx; }
        if (n.fy != null) { n.y = n.fy; n.vy = 0; } else { n.vy *= 1 - this.velocityDecay; n.y += n.vy; }
        // One bad coordinate would spread to every node through the repulsion sums: reset it.
        if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) {
          n.x = (n.index % 17) - 8; n.y = (n.index % 13) - 6; n.vx = 0; n.vy = 0;
        }
      }
    }
  }

  // ---------------------------------------------------------------- view --

  function el(tag, attrs, children) {
    // el('div', [kids]) or el('div', 'text') are shorthand for el('div', null, kids).
    if (Array.isArray(attrs) || typeof attrs === 'string' || (attrs && attrs.nodeType)) { children = attrs; attrs = null; }
    const e = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === 'class') e.className = v;
        else if (k === 'text') e.textContent = v;
        else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
        else if (k === 'style') e.style.cssText = v;
        else e.setAttribute(k, v === true ? '' : v);
      }
    }
    for (const c of [].concat(children || [])) if (c != null) e.append(c);
    return e;
  }

  /** replaceChildren that skips null/false (replaceChildren would print them as text). */
  function put(parent, ...kids) {
    parent.replaceChildren(...kids.filter((k) => k != null && k !== false));
  }

  function rgba(hex, a) {
    const h = hex.replace('#', '');
    const v = parseInt(h.length === 3 ? h.split('').map((x) => x + x).join('') : h, 16);
    return `rgba(${(v >> 16) & 255},${(v >> 8) & 255},${v & 255},${a})`;
  }

  const LABEL_FONT = '600 12px Inter, "Segoe UI", system-ui, -apple-system, sans-serif';

  /** Build the interactive view inside `container`. Returns {update, resize, destroy, select}. */
  function createGraphView(container, data, hooks) {
    hooks = hooks || {};
    const state = {
      colorBy: 'status',
      filters: { courses: new Set(), statuses: new Set() },  // hidden ones
      hideOrphans: false,
      labelSize: 6, nodeScale: 1, linkWidth: 1, arrows: true,
      hovered: null, selected: null, highlight: null, chain: true, search: '',
    };
    let model = null;
    let visible = [];
    let visibleSet = new Set();
    let links = [];
    let focusCache = null;
    let sized = false;
    const sim = new Simulation();
    const cam = { k: 1, x: 0, y: 0 };
    let anim = null;
    let W = 0, H = 0, dpr = 1;
    let raf = 0, dirty = true, destroyed = false;
    const sprites = new Map();
    const positions = new Map();

    // ----- DOM
    const root = el('div', { class: 'sg' });
    const canvas = el('canvas', { class: 'sg-canvas' });
    const ctx = canvas.getContext('2d');
    const left = el('div', { class: 'sg-panel sg-left' });
    const right = el('div', { class: 'sg-panel sg-right' });
    const legend = el('div', { class: 'sg-legend' });
    const card = el('div', { class: 'sg-panel sg-card sg-hidden' });
    const empty = el('div', { class: 'sg-empty sg-hidden' });
    const tip = el('div', { class: 'sg-tip sg-hidden' });
    const toolbar = el('div', { class: 'sg-toolbar' });
    root.append(canvas, left, right, legend, card, empty, tip, toolbar);
    container.append(root);

    // ----- controls (left)
    const search = el('input', { class: 'sg-search', type: 'search', placeholder: 'Search concepts…' });
    const results = el('div', { class: 'sg-results' });
    const courseChips = el('div', { class: 'sg-chips' });
    const statusChips = el('div', { class: 'sg-chips' });
    const orphanToggle = el('label', { class: 'sg-check' }, [
      el('input', { type: 'checkbox', onchange: (e) => { state.hideOrphans = e.target.checked; rebuild(true); } }), 'Hide unlinked ideas']);
    const groupRadios = el('div', { class: 'sg-seg' });
    for (const [key, label] of [['status', 'Status'], ['course', 'Course'], ['community', 'Topic clusters']]) {
      groupRadios.append(el('button', {
        class: 'sg-seg-btn' + (state.colorBy === key ? ' on' : ''), 'data-key': key, text: label,
        onclick: () => {
          state.colorBy = key;
          for (const b of groupRadios.children) b.classList.toggle('on', b.dataset.key === key);
          applyColors(); sim.reheat(0.5); kick(); renderLegend();
        },
      }));
    }
    const slider = (label, min, max, step, value, onInput) => {
      const out = el('span', { class: 'sg-val', text: String(value) });
      const input = el('input', { type: 'range', min, max, step, value, oninput: (e) => { const v = parseFloat(e.target.value); out.textContent = String(v); onInput(v); } });
      return el('label', { class: 'sg-slider' }, [el('span', { text: label }), input, out]);
    };
    const section = (title, open, body) => el('details', { class: 'sg-sec', open }, [el('summary', { text: title }), ...[].concat(body)]);
    left.append(
      el('div', { class: 'sg-searchwrap' }, [search, results]),
      section('Filters', false, [el('div', { class: 'sg-sub', text: 'Courses' }), courseChips, el('div', { class: 'sg-sub', text: 'Status' }), statusChips, orphanToggle]),
      section('Groups', true, [el('div', { class: 'sg-sub', text: 'Colour by' }), groupRadios]),
      section('Display', false, [
        slider('Labels', 0, 20, 1, state.labelSize, (v) => { state.labelSize = v; kick(); }),
        slider('Node size', 0.4, 2.5, 0.1, state.nodeScale, (v) => { state.nodeScale = v; kick(); }),
        slider('Link width', 0.2, 3, 0.1, state.linkWidth, (v) => { state.linkWidth = v; kick(); }),
        el('label', { class: 'sg-check' }, [el('input', { type: 'checkbox', checked: true, onchange: (e) => { state.arrows = e.target.checked; kick(); } }), 'Arrows']),
      ]),
      section('Forces', false, [
        slider('Repel', 10, 300, 5, sim.params.repel, (v) => { sim.params.repel = v; sim.reheat(0.4); kick(); }),
        slider('Link distance', 10, 150, 2, sim.params.distance, (v) => { sim.params.distance = v; sim.reheat(0.4); kick(); }),
        slider('Center pull', 0, 0.2, 0.005, sim.params.center, (v) => { sim.params.center = v; sim.reheat(0.4); kick(); }),
        slider('Cluster pull', 0, 0.4, 0.01, sim.params.cluster, (v) => { sim.params.cluster = v; sim.reheat(0.4); kick(); }),
        el('button', { class: 'sg-btn', text: 'Shake it up', onclick: () => { sim.reheat(1); kick(); } }),
      ]),
    );

    search.addEventListener('input', () => { state.search = search.value.trim().toLowerCase(); renderResults(); kick(); });
    search.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { const first = results.querySelector('.sg-result'); if (first) first.click(); }
      if (e.key === 'Escape') { search.value = ''; state.search = ''; renderResults(); kick(); }
    });

    // ----- toolbar
    // The insight panel follows the user's choice, but folds away by itself on a narrow pane
    // and while a concept card is open there, so the two never sit on top of each other.
    let insightWanted = true;
    let narrow = false;
    function layoutPanels() {
      const showRight = insightWanted && !(narrow && state.selected);
      right.classList.toggle('sg-hidden', !showRight);
      insightBtn.classList.toggle('on', insightWanted);
      legend.classList.toggle('sg-hidden', !!state.selected || legend.childElementCount === 0);
    }
    const insightBtn = el('button', { class: 'sg-tbtn', title: 'Show or hide insights', text: 'Insights', onclick: () => { insightWanted = !insightWanted; layoutPanels(); } });
    toolbar.append(
      el('button', { class: 'sg-tbtn', title: 'Fit the graph to the window', text: 'Fit', onclick: () => fit(visible, true) }),
      el('button', { class: 'sg-tbtn', title: 'Show or hide the controls', text: 'Controls', onclick: () => left.classList.toggle('sg-hidden') }),
      insightBtn,
    );

    // ----- helpers
    const isVisible = (n) => !state.filters.courses.has(n.course) && !state.filters.statuses.has(n.status) && !(state.hideOrphans && n.degree === 0);
    const radius = (n) => (3 + Math.sqrt(n.degree + n.reach * 0.6) * 1.7) * state.nodeScale;
    const kick = () => { dirty = true; schedule(); };
    function schedule() { if (!raf && !destroyed) raf = requestAnimationFrame(frame); }

    function applyColors() {
      if (!model) return;
      const courseIdx = new Map(model.courses.map((c, i) => [c, i]));
      for (const n of model.nodes) {
        if (state.colorBy === 'status') n.color = STATUS[n.status].color;
        else if (state.colorBy === 'course') n.color = PALETTE[courseIdx.get(n.course) % PALETTE.length];
        else {
          const c = model.communities[n.community];
          n.color = c && c.size > 1 ? PALETTE[c.id % PALETTE.length] : LONE;
        }
      }
      sim.groupOf = state.colorBy === 'community' ? (n) => n.community : (n) => n.course;
      dirty = true;
    }

    function seedPosition(n, i) {
      const prev = positions.get(n.id);
      if (prev) { n.x = prev.x; n.y = prev.y; n.vx = 0; n.vy = 0; return; }
      const placed = n.neighbors.map((m) => positions.get(m.id)).filter(Boolean);
      if (placed.length) {
        n.x = placed.reduce((a, p) => a + p.x, 0) / placed.length + (Math.random() - 0.5) * 30;
        n.y = placed.reduce((a, p) => a + p.y, 0) / placed.length + (Math.random() - 0.5) * 30;
      } else {
        const ci = Math.max(0, model.courses.indexOf(n.course));
        const ang = (ci / Math.max(1, model.courses.length)) * Math.PI * 2;
        const R = 60 + 18 * Math.sqrt(model.nodes.length);
        const r = 6 * Math.sqrt(i + 0.5), a = i * Math.PI * (3 - Math.sqrt(5));
        n.x = Math.cos(ang) * R + r * Math.cos(a);
        n.y = Math.sin(ang) * R + r * Math.sin(a);
      }
      n.vx = 0; n.vy = 0;
    }

    function rebuild(reheat) {
      visible = model.nodes.filter(isVisible);
      visibleSet = new Set(visible);
      links = model.edges.filter((e) => visibleSet.has(e.source) && visibleSet.has(e.target));
      sim.setGraph(visible, links);
      if (state.selected && !visibleSet.has(state.selected)) select(null);
      if (reheat) sim.reheat(0.6);
      focusCache = null;
      updateEmpty();
      kick();
    }

    function load(d, first) {
      if (model) {
        positions.clear();
        for (const n of model.nodes) positions.set(n.id, { x: n.x, y: n.y });
      }
      // Remember the selection and highlight by id: the old node objects die with the old model.
      const selectedId = state.selected && state.selected.id;
      const highlightIds = state.highlight ? new Set([...state.highlight].map((n) => n.id)) : null;
      state.selected = null; state.hovered = null; state.highlight = null;
      focusCache = null;
      model = analyze(d);
      model.vault = (d && d.vault) || '';
      model.nodes.forEach((n, i) => seedPosition(n, i));
      applyColors();
      renderChips();
      rebuild(false);
      if (first) {
        sim.alpha = 1;
        for (let i = 0; i < 120 && sim.active; i++) sim.tick();
        fit(visible, false);
      } else {
        sim.reheat(0.3);
      }
      renderInsights();
      renderLegend();
      renderResults();
      const sel = selectedId ? model.byId.get(selectedId) : null;
      state.selected = sel && visibleSet.has(sel) ? sel : null;
      if (highlightIds) {
        const h = new Set(model.nodes.filter((n) => highlightIds.has(n.id)));
        state.highlight = h.size ? h : null;
      }
      renderCard();
      kick();
    }

    function updateEmpty() {
      const none = model.nodes.length === 0;
      empty.classList.toggle('sg-hidden', !none);
      empty.replaceChildren(
        el('div', { class: 'sg-empty-title', text: none ? 'No concepts yet' : '' }),
        el('div', { text: 'Concept notes appear here when a study session closes. To see a whole course at once, say "map chem" (or another course) in a Claude Code session in this vault.' }),
      );
    }

    // ----- chips, legend, search results
    function chip(label, color, on, onclick, count) {
      return el('button', { class: 'sg-chip' + (on ? '' : ' off'), onclick }, [
        el('span', { class: 'sg-dot', style: `background:${color}` }), label,
        count != null ? el('span', { class: 'sg-count', text: String(count) }) : null]);
    }

    function renderChips() {
      courseChips.replaceChildren(...model.courseStats.map((c, i) => chip(c.label, PALETTE[i % PALETTE.length], !state.filters.courses.has(c.course), () => {
        toggle(state.filters.courses, c.course); renderChips(); rebuild(true); renderLegend();
      }, c.total)));
      statusChips.replaceChildren(...STATUS_ORDER.filter((s) => model.counts[s] > 0 || s !== 'unknown').map((s) => chip(STATUS[s].label, STATUS[s].color, !state.filters.statuses.has(s), () => {
        toggle(state.filters.statuses, s); renderChips(); rebuild(true); renderLegend();
      }, model.counts[s])));
    }

    function toggle(set, v) { if (set.has(v)) set.delete(v); else set.add(v); }

    function renderLegend() {
      let items = [];
      if (state.colorBy === 'status') {
        items = STATUS_ORDER.filter((s) => model.counts[s] > 0).map((s) => ({ color: STATUS[s].color, label: STATUS[s].label, count: model.counts[s] }));
      } else if (state.colorBy === 'course') {
        items = model.courseStats.map((c, i) => ({ color: PALETTE[i % PALETTE.length], label: c.label, count: c.total }));
      } else {
        items = model.communities.filter((c) => c.size > 1).slice(0, 8).map((c) => ({
          color: PALETTE[c.id % PALETTE.length], label: c.label, count: c.size,
          onclick: () => focusSet(new Set(c.members)),
        }));
      }
      legend.replaceChildren(...items.map((it) => el('div', { class: 'sg-leg' + (it.onclick ? ' click' : ''), onclick: it.onclick }, [
        el('span', { class: 'sg-dot', style: `background:${it.color};box-shadow:0 0 8px ${it.color}` }), el('span', { text: it.label }), el('span', { class: 'sg-count', text: String(it.count) })])));
      layoutPanels();
    }

    function renderResults() {
      if (!state.search) { results.replaceChildren(); return; }
      const q = state.search;
      const hits = model.nodes.filter((n) => n.name.toLowerCase().includes(q) || n.aliases.some((a) => a.toLowerCase().includes(q))).slice(0, 8);
      results.replaceChildren(...(hits.length ? hits.map((n) => el('div', { class: 'sg-result', onclick: () => { search.value = ''; state.search = ''; renderResults(); focusNode(n); } }, [
        el('span', { class: 'sg-dot', style: `background:${n.color}` }), n.name, el('span', { class: 'sg-muted', text: courseLabel(n.course) })])) : [el('div', { class: 'sg-muted', text: 'No match' })]));
    }

    // ----- insights (right)
    function nodeRow(n, note) {
      return el('div', { class: 'sg-row', onclick: () => focusNode(n) }, [
        el('span', { class: 'sg-dot', style: `background:${STATUS[n.status].color}` }),
        el('span', { class: 'sg-row-name', text: n.name }),
        note ? el('span', { class: 'sg-muted', text: note }) : null]);
    }

    function block(title, help, rows) {
      if (!rows.length) return null;
      return el('div', { class: 'sg-block' }, [el('div', { class: 'sg-block-title', text: title }), help ? el('div', { class: 'sg-help', text: help }) : null, ...rows]);
    }

    const restsOn = (n) => (n.reach ? `${n.reach} rest on it` : '');

    function renderInsights() {
      const I = model.insights;
      const total = model.nodes.length;
      const bar = el('div', { class: 'sg-bar' }, STATUS_ORDER.filter((s) => model.counts[s]).map((s) =>
        el('span', { style: `flex:${model.counts[s]};background:${STATUS[s].color}`, title: `${STATUS[s].label}: ${model.counts[s]}` })));
      const summary = total
        ? `${total} concepts · ${model.counts.solid} solid · ${model.counts.shaky} shaky · ${model.counts['not-yet'] + model.counts.unknown} not yet`
        : 'No concepts yet.';
      const coursesRows = model.courseStats.map((c) => el('div', { class: 'sg-course' }, [
        el('span', { class: 'sg-course-name', text: c.label }),
        el('div', { class: 'sg-bar sg-bar-sm' }, STATUS_ORDER.filter((s) => c.counts[s]).map((s) => el('span', { style: `flex:${c.counts[s]};background:${STATUS[s].color}` }))),
        el('span', { class: 'sg-muted', text: `${c.counts.solid}/${c.total}` })]));
      const gapRows = I.gaps.map((g) => el('div', { class: 'sg-gap', onclick: () => focusSet(new Set([...g.a.members, ...g.b.members])) }, [
        el('div', [el('b', { text: g.a.hubs[0].name }), ' and ', el('b', { text: g.b.hubs[0].name })]),
        el('div', { class: 'sg-muted', text: g.links ? 'Only one link between these topics.' : 'Nothing links these topics yet.' }),
        el('button', { class: 'sg-mini', text: 'Copy prompt', onclick: (e) => { e.stopPropagation(); copy(`explain how ${g.a.hubs[0].name} relates to ${g.b.hubs[0].name}`); } })]));

      put(right, 
        el('div', { class: 'sg-title', text: 'Insight' }),
        el('div', { class: 'sg-summary', text: summary }),
        total ? bar : null,
        model.courseStats.length > 1 ? el('div', { class: 'sg-block' }, [el('div', { class: 'sg-block-title', text: 'By course' }), ...coursesRows]) : null,
        block('Ready to learn next', 'Not studied yet, and everything they rest on is solid.', I.frontier.map((n) => nodeRow(n, restsOn(n)))),
        block('Shaky foundations', 'Fixing these steadies everything built on them.', I.shaky.map((n) => nodeRow(n, restsOn(n)))),
        block('Missing foundations', 'Not studied, but ideas you have studied rest on them.', I.missing.map((n) => nodeRow(n, restsOn(n)))),
        block('Gaps between topics', 'Two clusters with nothing connecting them. Ask how they relate.', gapRows),
        block('Hubs', 'The most connected ideas.', I.hubs.map((n) => nodeRow(n, `${n.degree} links`))),
        block('Bridges between courses', 'Ideas that tie your courses together.', I.bridges.map((n) => nodeRow(n, courseLabel(n.course)))),
        block(`Unlinked ideas (${I.orphanCount})`, 'Nothing connects these yet, so they are held by memory alone.', I.orphans.map((n) => nodeRow(n, courseLabel(n.course)))),
      );
    }

    // ----- detail card
    function renderCard() {
      const n = state.selected;
      card.classList.toggle('sg-hidden', !n);
      layoutPanels();
      if (!n) return;
      const pill = (text, color) => el('span', { class: 'sg-pill', style: color ? `border-color:${color};color:${color}` : '' , text });
      const list = (title, arr) => arr.length ? el('div', { class: 'sg-card-list' }, [el('div', { class: 'sg-sub', text: title }),
        el('div', { class: 'sg-links' }, arr.map((m) => el('button', { class: 'sg-link', onclick: () => focusNode(m) }, [el('span', { class: 'sg-dot', style: `background:${STATUS[m.status].color}` }), m.name])))]) : null;
      const statement = el('div', { class: 'sg-statement' });
      if (n.statement) {
        if (hooks.renderStatement) {
          try { hooks.renderStatement(statement, n.statement, n); } catch (e) { statement.textContent = n.statement; }
        } else statement.textContent = n.statement;
      } else statement.append(el('span', { class: 'sg-muted', text: 'No statement yet.' }));
      const chainBox = el('input', { type: 'checkbox', checked: state.chain, onchange: (e) => { state.chain = e.target.checked; kick(); } });
      put(card, 
        el('div', { class: 'sg-card-head' }, [el('div', { class: 'sg-card-title', text: n.name }), el('button', { class: 'sg-x', title: 'Close', text: '×', onclick: () => select(null) })]),
        el('div', { class: 'sg-pills' }, [pill(courseLabel(n.course)), pill(STATUS[n.status].label, STATUS[n.status].color), n.kind ? pill(n.kind) : null]),
        statement,
        list('Rests on', n.premises),
        list('Used by', n.dependents),
        el('div', { class: 'sg-muted', text: n.reach ? `${n.reach} idea${n.reach === 1 ? '' : 's'} rest on this, directly or further down.` : 'Nothing rests on this yet.' }),
        el('label', { class: 'sg-check' }, [chainBox, 'Highlight the full chain']),
        el('div', { class: 'sg-actions' }, [
          hooks.openNote ? el('button', { class: 'sg-btn', text: 'Open note', onclick: () => hooks.openNote(n) }) : null,
          n.slide && hooks.openSlide ? el('button', { class: 'sg-btn', text: 'Open slide', onclick: () => hooks.openSlide(n) }) : null,
          el('button', { class: 'sg-btn primary', text: 'Copy "study" prompt', onclick: () => copy(`study ${n.name}`) }),
        ]),
      );
    }

    function copy(text) {
      if (hooks.copy) { hooks.copy(text); return; }
      const done = () => toast(`Copied: ${text}`);
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
      else fallbackCopy(text, done);
    }

    function fallbackCopy(text, done) {
      const ta = el('textarea', { style: 'position:fixed;opacity:0' });
      ta.value = text; document.body.append(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { toast('Copy failed'); }
      ta.remove();
    }

    let toastTimer = 0;
    function toast(msg) {
      tip.textContent = msg; tip.classList.remove('sg-hidden');
      clearTimeout(toastTimer); toastTimer = setTimeout(() => tip.classList.add('sg-hidden'), 1800);
    }

    // ----- selection & camera
    function select(n) {
      state.selected = n;
      state.highlight = null;
      renderCard();
      kick();
    }

    function focusNode(n) {
      if (!isVisible(n)) {
        state.filters.courses.delete(n.course); state.filters.statuses.delete(n.status);
        if (n.degree === 0) state.hideOrphans = false;
        renderChips(); rebuild(true);
      }
      select(n);
      animateTo({ k: Math.max(cam.k, 1.6), x: W / 2 - n.x * Math.max(cam.k, 1.6), y: H / 2 - n.y * Math.max(cam.k, 1.6) });
    }

    function focusSet(set) {
      state.selected = null; renderCard();
      state.highlight = set;
      fit([...set].filter((n) => visibleSet.has(n)), true);
      kick();
    }

    /** The part of the canvas not covered by the side panels (on wide views). */
    function freeArea() {
      let l = 0, r = W;
      if (W >= 760) {
        if (!left.classList.contains('sg-hidden')) l = left.offsetLeft + left.offsetWidth;
        if (!right.classList.contains('sg-hidden')) r = right.offsetLeft;
        if (r - l < W * 0.4) { l = 0; r = W; }
      }
      return { l, r, t: 0, b: H - 40 };
    }

    function fit(nodes, animate) {
      if (!nodes.length || !W || !H) return;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const n of nodes) { x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x); y1 = Math.max(y1, n.y); }
      const A = freeArea();
      const pad = 50;
      const w = A.r - A.l - pad * 2, h = A.b - A.t - pad * 2;
      const k = Math.min(3, Math.max(0.05, Math.min(w / Math.max(1, x1 - x0), h / Math.max(1, y1 - y0))));
      const target = { k, x: (A.l + A.r) / 2 - ((x0 + x1) / 2) * k, y: (A.t + A.b) / 2 - ((y0 + y1) / 2) * k };
      if (animate) animateTo(target); else { Object.assign(cam, target); kick(); }
    }

    function animateTo(target) {
      anim = { from: { ...cam }, to: target, t0: performance.now(), dur: 450 };
      kick();
    }

    // ----- interaction
    let drag = null;
    const toWorld = (px, py) => ({ x: (px - cam.x) / cam.k, y: (py - cam.y) / cam.k });
    function pick(px, py) {
      const p = toWorld(px, py);
      let best = null, bestD = Infinity;
      for (let i = visible.length - 1; i >= 0; i--) {
        const n = visible[i];
        const r = Math.max(radius(n), 6 / cam.k);
        const d = (n.x - p.x) ** 2 + (n.y - p.y) ** 2;
        if (d < r * r && d < bestD) { best = n; bestD = d; }
      }
      return best;
    }
    const localXY = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };

    canvas.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || !e.isPrimary || drag) return;  // left button, first finger only
      const [px, py] = localXY(e);
      const n = pick(px, py);
      try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* synthetic events can't be captured */ }
      drag = { n, sx: px, sy: py, moved: false, camX: cam.x, camY: cam.y };
      anim = null;
      if (n) { n.fx = n.x; n.fy = n.y; }
    });
    canvas.addEventListener('pointermove', (e) => {
      const [px, py] = localXY(e);
      if (drag) {
        if (Math.abs(px - drag.sx) + Math.abs(py - drag.sy) > 3) drag.moved = true;
        if (drag.n) {
          const p = toWorld(px, py);
          drag.n.fx = p.x; drag.n.fy = p.y;
          if (drag.moved) { sim.alphaTarget = 0.25; sim.reheat(0.25); }
        } else {
          cam.x = drag.camX + (px - drag.sx); cam.y = drag.camY + (py - drag.sy);
        }
        kick();
        return;
      }
      const n = pick(px, py);
      if (n !== state.hovered) { state.hovered = n; canvas.style.cursor = n ? 'pointer' : 'grab'; kick(); }
    });
    const endDrag = (e) => {
      if (!drag) return;
      const d = drag;
      drag = null;
      sim.alphaTarget = 0;
      if (d.n) { d.n.fx = null; d.n.fy = null; }
      if (!d.moved) {
        if (d.n) select(state.selected === d.n ? null : d.n);
        else { select(null); state.highlight = null; }
      }
      kick();
    };
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);
    canvas.addEventListener('lostpointercapture', endDrag);
    canvas.addEventListener('pointerleave', () => { if (!drag && state.hovered) { state.hovered = null; kick(); } });
    canvas.addEventListener('dblclick', (e) => {
      const [px, py] = localXY(e);
      const n = pick(px, py);
      if (n && hooks.openNote) hooks.openNote(n);
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      anim = null;
      const [px, py] = localXY(e);
      const k = Math.min(8, Math.max(0.05, cam.k * Math.exp(-e.deltaY * 0.0015)));
      cam.x = px - ((px - cam.x) * k) / cam.k;
      cam.y = py - ((py - cam.y) * k) / cam.k;
      cam.k = k;
      kick();
    }, { passive: false });
    const onKey = (e) => {
      if (!root.isConnected || !root.contains(document.activeElement) && document.activeElement !== document.body) return;
      if (e.key === 'Escape') { select(null); state.highlight = null; kick(); }
      if (e.key === '/' && document.activeElement !== search) { e.preventDefault(); left.classList.remove('sg-hidden'); search.focus(); }
    };
    root.tabIndex = 0;
    root.addEventListener('keydown', onKey);

    // ----- drawing
    function sprite(color) {
      let c = sprites.get(color);
      if (c) return c;
      c = document.createElement('canvas');
      c.width = c.height = 64;
      const g = c.getContext('2d');
      const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      grd.addColorStop(0, rgba(color, 0.7));
      grd.addColorStop(0.25, rgba(color, 0.3));
      grd.addColorStop(0.6, rgba(color, 0.08));
      grd.addColorStop(1, rgba(color, 0));
      g.fillStyle = grd;
      g.fillRect(0, 0, 64, 64);
      sprites.set(color, c);
      return c;
    }

    /** Which nodes are lit for the current hover/selection/highlight. Cached: draw() runs every frame. */
    function focusSets() {
      const focus = state.hovered || state.selected;
      const chain = !!(focus && state.chain && focus === state.selected);
      if (focusCache && focusCache.focus === focus && focusCache.chain === chain && focusCache.highlight === state.highlight) {
        return focusCache.value;
      }
      let value = null;
      if (!focus) {
        value = state.highlight ? { lit: state.highlight, up: null, down: null, focus: null, nbr: null } : null;
      } else {
        const nbr = new Set(focus.neighbors);
        const lit = new Set([focus, ...nbr]);
        let up = null, down = null;
        if (chain) {
          up = reachSet(focus, 'premises');
          down = reachSet(focus, 'dependents');
          for (const n of up) lit.add(n);
          for (const n of down) lit.add(n);
        }
        value = { lit, up, down, focus, nbr };
      }
      focusCache = { focus, chain, highlight: state.highlight, value };
      return value;
    }

    function draw() {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      if (!model || !visible.length) return;
      const k = cam.k;
      const F = focusSets();
      const lit = F && F.lit;
      const qmatch = state.search ? (n) => n.name.toLowerCase().includes(state.search) : null;
      ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * cam.x, dpr * cam.y);

      // edges
      const base = 0.9 * state.linkWidth / k;
      ctx.lineWidth = base;
      ctx.strokeStyle = lit ? 'rgba(140,150,170,0.06)' : 'rgba(150,160,182,0.22)';
      ctx.beginPath();
      for (const l of links) {
        if (lit && lit.has(l.source) && lit.has(l.target)) continue;
        ctx.moveTo(l.source.x, l.source.y); ctx.lineTo(l.target.x, l.target.y);
      }
      ctx.stroke();
      if (lit) {
        for (const l of links) {
          if (!(lit.has(l.source) && lit.has(l.target))) continue;
          let color = 'rgba(205,212,228,0.7)';
          if (F.up && (F.up.has(l.target) && (F.up.has(l.source) || l.source === F.focus))) color = 'rgba(110,168,255,0.9)';
          else if (F.down && (F.down.has(l.source) && (F.down.has(l.target) || l.target === F.focus))) color = 'rgba(236,111,181,0.85)';
          ctx.strokeStyle = color;
          ctx.lineWidth = base * 1.8;
          ctx.beginPath(); ctx.moveTo(l.source.x, l.source.y); ctx.lineTo(l.target.x, l.target.y); ctx.stroke();
          if (state.arrows) arrow(l, color, base);
        }
      } else if (state.arrows && k > 1.4) {
        for (const l of links) arrow(l, 'rgba(150,160,182,0.45)', base);
      }

      // glow
      ctx.globalCompositeOperation = 'lighter';
      for (const n of visible) {
        const dim = (lit && !lit.has(n)) || (qmatch && !qmatch(n));
        if (dim) continue;
        const r = radius(n) * 3.4;
        ctx.globalAlpha = n.status === 'not-yet' || n.status === 'unknown' ? 0.35 : 0.8;
        ctx.drawImage(sprite(n.color), n.x - r, n.y - r, r * 2, r * 2);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';

      // nodes
      for (const n of visible) {
        const dim = (lit && !lit.has(n)) || (qmatch && !qmatch(n));
        ctx.globalAlpha = dim ? 0.13 : 1;
        const r = Math.max(radius(n), 1.4 / k);
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = n.color;
        ctx.fill();
        if (n === state.selected || n === state.hovered) {
          ctx.lineWidth = 2 / k;
          ctx.strokeStyle = '#ffffff';
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;

      // labels (screen space)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = LABEL_FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.lineJoin = 'round';
      const cands = [];
      for (const n of visible) {
        const sr = radius(n) * k;
        // "must" labels always show (the focused node); "pref" labels (its neighbours, cluster hubs,
        // search hits) show before others but still give way when they would overlap.
        const must = n === state.hovered || n === state.selected;
        const pref = must || (F && F.nbr && F.nbr.has(n)) || (state.highlight && state.highlight.has(n) && n.community != null && model.communities[n.community].hubs.includes(n));
        const searchHit = qmatch && qmatch(n);
        if (lit && !lit.has(n) && !searchHit) continue;
        // Labels appear once a node is big enough on screen; the Labels slider lowers that bar.
        const fade = state.labelSize >= 20 ? 1 : Math.min(1, Math.max(0, (sr - (20 - state.labelSize) * 0.6) / 3));
        if (!pref && !searchHit && fade < 0.5) continue;
        cands.push({ n, sr, a: pref || searchHit ? 1 : Math.max(0.8, fade), forced: must, pref: pref || searchHit });
      }
      cands.sort((a, b) => (b.forced - a.forced) || (b.pref - a.pref) || (b.sr - a.sr));
      const placed = [];
      for (const c of cands) {
        const sx = c.n.x * k + cam.x, sy = c.n.y * k + cam.y + c.sr + 3;
        if (sx < -100 || sx > W + 100 || sy < -20 || sy > H + 20) continue;
        const w = ctx.measureText(c.n.name).width;
        const box = { x0: sx - w / 2 - 2, x1: sx + w / 2 + 2, y0: sy - 1, y1: sy + 15 };
        if (!c.forced && placed.some((b) => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0)) continue;
        placed.push(box);
        ctx.globalAlpha = c.a;
        ctx.lineWidth = 3.5;
        ctx.strokeStyle = 'rgba(20,22,28,0.92)';
        ctx.strokeText(c.n.name, sx, sy);
        ctx.fillStyle = c.pref ? '#ffffff' : '#dfe3ea';
        ctx.fillText(c.n.name, sx, sy);
      }
      ctx.globalAlpha = 1;
    }

    function arrow(l, color, base) {
      const s = l.source, t = l.target;
      const dx = t.x - s.x, dy = t.y - s.y;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const ux = dx / len, uy = dy / len;
      const r = radius(t) + 1.5 / cam.k;
      const tipX = t.x - ux * r, tipY = t.y - uy * r;
      const size = Math.max(3.2, 5 * base * cam.k) / cam.k;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(tipX, tipY);
      ctx.lineTo(tipX - ux * size * 2 - uy * size, tipY - uy * size * 2 + ux * size);
      ctx.lineTo(tipX - ux * size * 2 + uy * size, tipY - uy * size * 2 - ux * size);
      ctx.closePath();
      ctx.fill();
    }

    function frame(now) {
      raf = 0;
      if (destroyed) return;
      let again = false;
      if (anim) {
        const t = Math.min(1, (now - anim.t0) / anim.dur);
        const e = 1 - Math.pow(1 - t, 3);
        cam.k = anim.from.k + (anim.to.k - anim.from.k) * e;
        cam.x = anim.from.x + (anim.to.x - anim.from.x) * e;
        cam.y = anim.from.y + (anim.to.y - anim.from.y) * e;
        if (t >= 1) anim = null; else again = true;
        dirty = true;
      }
      if (sim.active) { sim.tick(); dirty = true; again = true; }
      if (dirty) { draw(); dirty = false; }
      if (again) schedule();
    }

    function resize() {
      const r = root.getBoundingClientRect();
      // A hidden tab (Obsidian restoring a background tab) measures 0×0: wait for a real size.
      if (r.width < 2 || r.height < 2) return;
      const w = Math.round(r.width), h = Math.round(r.height);
      const ratio = window.devicePixelRatio || 1;
      if (w === W && h === H && ratio === dpr) return;
      const firstSize = !sized;
      sized = true;
      W = w; H = h; dpr = ratio;
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      const nowNarrow = W < 760;
      if (firstSize) {
        narrow = nowNarrow;
        root.classList.toggle('sg-narrow', narrow);
        insightWanted = W >= 900;
        layoutPanels();
      } else if (nowNarrow !== narrow) {
        narrow = nowNarrow;
        root.classList.toggle('sg-narrow', narrow);
        insightWanted = !narrow;  // fold the insights away on narrow panes, bring them back when wide
        layoutPanels();
      }
      if (firstSize && model) fit(visible, false);
      kick();
    }
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    if (ro) ro.observe(root);
    resize();
    layoutPanels();

    load(data, true);

    return {
      update(d) { if (!destroyed) load(d, false); },
      resize,
      select(id) { const n = model && model.byId.get(id); if (n) focusNode(n); },
      destroy() {
        destroyed = true;
        if (raf) cancelAnimationFrame(raf);
        clearTimeout(toastTimer);
        if (ro) ro.disconnect();
        root.remove();
      },
      get model() { return model; },
    };
  }

  /** Hooks for the standalone page: open notes in Obsidian through obsidian:// links, render math with KaTeX if loaded. */
  function standaloneHooks(data) {
    const vault = (data && data.vault) || 'study-vault';
    const uri = (file) => `obsidian://open?vault=${encodeURIComponent(vault)}&file=${encodeURIComponent(file)}`;
    return {
      openNote(n) { window.location.href = uri(n.id); },
      openSlide(n) { window.location.href = uri(n.slide.split('#')[0]); },
      renderStatement(elm, text) {
        elm.textContent = text;
        if (typeof window.renderMathInElement === 'function') {
          window.renderMathInElement(elm, { delimiters: [{ left: '$$', right: '$$', display: true }, { left: '$', right: '$', display: false }], throwOnError: false });
        }
      },
    };
  }

  return { VERSION, STATUS, louvain, analyze, Simulation, createGraphView, standaloneHooks, courseLabel };
}

if (typeof window !== 'undefined') {
  window.StudyGraph = StudyGraphFactory();
} else if (typeof module === 'object' && module.exports) {
  module.exports = StudyGraphFactory();
}
