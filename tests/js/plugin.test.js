// Tests for the Obsidian glue (tools/study-graph/plugin.js) with a mocked `obsidian` module.
// Run: node --test tests/js/
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..', '..');

function loadPlugin() {
  const obsidian = {
    Plugin: class { constructor(app) { this.app = app; } },
    ItemView: class { constructor(leaf) { this.leaf = leaf; } },
    MarkdownRenderer: {},
    Notice: class {},
    TFile: class {},
    Component: class { load() {} unload() {} },
    debounce: (f) => f,
  };
  // Same bundle as the build: core.js then plugin.js, evaluated as one CommonJS module.
  const src = fs.readFileSync(path.join(ROOT, 'tools/study-graph/core.js'), 'utf8') + '\n' +
    fs.readFileSync(path.join(ROOT, 'tools/study-graph/plugin.js'), 'utf8');
  const mod = { exports: {} };
  const fn = vm.runInThisContext('(function (module, exports, require) {' + src + '\n})');
  fn(mod, mod.exports, (name) => (name === 'obsidian' ? obsidian : Module.prototype.require.call(module, name)));
  return mod.exports;
}

function fakeApp(files) {
  // files: { path: { frontmatter, text } }
  const tfiles = Object.keys(files).map((p) => ({ path: p, basename: path.posix.basename(p, '.md') }));
  return {
    vault: {
      getMarkdownFiles: () => tfiles,
      cachedRead: async (f) => files[f.path].text,
      getName: () => 'study-vault',
      getAbstractFileByPath: (p) => tfiles.find((f) => f.path === p) || null,
    },
    metadataCache: {
      getFileCache: (f) => ({ frontmatter: files[f.path].frontmatter }),
      // Like Obsidian: resolve by basename only (aliases are NOT resolved here).
      getFirstLinkpathDest: (name) => tfiles.find((f) => f.basename.toLowerCase() === name.toLowerCase()) || null,
    },
    workspace: {},
  };
}

test('collect reads concepts, status, statement, slide and resolves follows-from (incl. aliases)', async () => {
  const Plugin = loadPlugin();
  const files = {
    'courses/chem-1302/concepts/Gibbs free energy.md': {
      frontmatter: { tags: ['concept', 'chem-1302', 'status/shaky'], kind: 'derived', aliases: ['ΔG'] },
      text: '---\n---\n# Gibbs\n\n**Statement:** $\\Delta G = \\Delta H - T\\Delta S$\n\n**Follows from:** [[Enthalpy]], [[Entropy (chemistry)|entropy]], [[Missing one]], [[S]]\n\n**Slides:** [[courses/chem-1302/slides/L14.pdf#page=12|L14 p. 12]], [[other.pdf]]\n',
    },
    'courses/chem-1302/concepts/Enthalpy.md': {
      frontmatter: { tags: 'concept, chem-1302, #status/solid' },
      text: '# Enthalpy\n\n**Statement:** H = U + PV\n',
    },
    'courses/chem-1302/concepts/Entropy (chemistry).md': {
      frontmatter: { tags: ['concept', 'chem-1302', 'status/not-yet'], aliases: ['S'] },
      text: '# Entropy\n',
    },
    'courses/chem-1302/sessions/2026-11-04 Gibbs.md': { frontmatter: { tags: ['session'] }, text: '[[Enthalpy]]' },
    'courses/chem-1302/concepts/sub/Nested.md': { frontmatter: {}, text: '' },
  };
  const p = new Plugin(fakeApp(files));
  const data = await p.collect();
  assert.strictEqual(data.vault, 'study-vault');
  assert.deepStrictEqual(data.nodes.map((n) => n.name).sort(), ['Enthalpy', 'Entropy (chemistry)', 'Gibbs free energy']);
  const g = data.nodes.find((n) => n.name === 'Gibbs free energy');
  assert.strictEqual(g.status, 'shaky');
  assert.strictEqual(g.course, 'chem-1302');
  assert.strictEqual(g.kind, 'derived');
  assert.strictEqual(g.statement, '$\\Delta G = \\Delta H - T\\Delta S$');
  assert.strictEqual(g.slide, 'courses/chem-1302/slides/L14.pdf#page=12');
  assert.deepStrictEqual(g.aliases, ['ΔG']);
  const targets = data.edges.filter((e) => e.source === g.id).map((e) => e.target).sort();
  // Enthalpy, Entropy via its name, Entropy again via alias S; the missing link is dropped.
  assert.deepStrictEqual(targets, [
    'courses/chem-1302/concepts/Enthalpy.md',
    'courses/chem-1302/concepts/Entropy (chemistry).md',
    'courses/chem-1302/concepts/Entropy (chemistry).md',
  ]);
  assert.strictEqual(data.nodes.find((n) => n.name === 'Enthalpy').status, 'solid', 'string tags with # are parsed');
  assert.strictEqual(data.nodes.find((n) => n.name === 'Entropy (chemistry)').status, 'not-yet');
});

test('collect handles notes with no frontmatter, no status and no fields', async () => {
  const Plugin = loadPlugin();
  const p = new Plugin(fakeApp({ 'courses/calc-1412/concepts/Limit.md': { frontmatter: undefined, text: '# Limit' } }));
  const data = await p.collect();
  assert.strictEqual(data.nodes.length, 1);
  assert.strictEqual(data.nodes[0].status, 'unknown');
  assert.strictEqual(data.nodes[0].statement, '');
  assert.strictEqual(data.nodes[0].slide, '');
  assert.deepStrictEqual(data.edges, []);
});

test('collected data analyses without errors (duplicate edges are merged)', async () => {
  const Plugin = loadPlugin();
  const core = require(path.join(ROOT, 'tools/study-graph/core.js'));
  const p = new Plugin(fakeApp({
    'courses/a/concepts/X.md': { frontmatter: { tags: ['concept', 'status/solid'] }, text: '**Follows from:** [[Y]], [[Y]]' },
    'courses/a/concepts/Y.md': { frontmatter: { tags: ['concept', 'status/shaky'] }, text: '' },
  }));
  const model = core.analyze(await p.collect());
  assert.strictEqual(model.edges.length, 1);
  assert.strictEqual(model.byId.get('courses/a/concepts/Y.md').reach, 1);
});

test('the built plugin bundle is current and exports the plugin class', () => {
  const built = fs.readFileSync(path.join(ROOT, '.obsidian/plugins/study-graph/main.js'), 'utf8').replace(/\r\n/g, '\n');
  const core = fs.readFileSync(path.join(ROOT, 'tools/study-graph/core.js'), 'utf8').replace(/\r\n/g, '\n');
  const plugin = fs.readFileSync(path.join(ROOT, 'tools/study-graph/plugin.js'), 'utf8').replace(/\r\n/g, '\n');
  assert.ok(built.includes(core.trimEnd()), 'main.js contains core.js (run: python scripts/study_graph.py build)');
  assert.ok(built.includes(plugin.trimEnd()), 'main.js contains plugin.js (run: python scripts/study_graph.py build)');
  assert.strictEqual(typeof loadPlugin(), 'function');
});
