/* Obsidian glue for Study Graph. Bundled after core.js into .obsidian/plugins/study-graph/main.js
 * by `python scripts/study_graph.py build`. Edit the sources in tools/study-graph/, not main.js. */
const obsidian = require('obsidian');

const VIEW_TYPE = 'study-graph';
const CONCEPT_PATH = /^courses\/([^/]+)\/concepts\/[^/]+\.md$/;
const FIELD = (label) => new RegExp('^\\*\\*' + label + ':\\*\\*(.*)$', 'mi');
const engine = () => (typeof window !== 'undefined' && window.StudyGraph) || StudyGraphFactory();

function list(value) {
  if (Array.isArray(value)) return value.map((v) => String(v).trim()).filter(Boolean);
  if (typeof value === 'string') return value.split(',').map((v) => v.trim()).filter(Boolean);
  return [];
}

class StudyGraphView extends obsidian.ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
    this.graph = null;
    this.closed = false;
    this.signature = '';
    this.seq = 0;
    this.md = null;  // Component owning the currently rendered statement
  }
  getViewType() { return VIEW_TYPE; }
  getDisplayText() { return 'Study graph'; }
  getIcon() { return 'network'; }
  async onOpen() {
    this.closed = false;
    this.contentEl.empty();
    const data = await this.plugin.collect();
    if (this.closed) return;  // closed while we were reading the notes
    this.signature = JSON.stringify(data);
    this.graph = engine().createGraphView(this.contentEl, data, this.plugin.hooks(this));
  }
  async refresh() {
    if (!this.graph) return;
    const seq = ++this.seq;
    const data = await this.plugin.collect();
    if (this.closed || !this.graph || seq !== this.seq) return;  // a newer refresh won, or the view closed
    const signature = JSON.stringify(data);
    if (signature === this.signature) return;  // nothing that the graph shows has changed
    this.signature = signature;
    this.graph.update(data);
  }
  onResize() { if (this.graph) this.graph.resize(); }
  async onClose() {
    this.closed = true;
    if (this.md) { this.md.unload(); this.md = null; }
    if (this.graph) this.graph.destroy();
    this.graph = null;
  }
}

class StudyGraphPlugin extends obsidian.Plugin {
  async onload() {
    this.noteLeaf = null;
    this.registerView(VIEW_TYPE, (leaf) => new StudyGraphView(leaf, this));
    this.addRibbonIcon('network', 'Open study graph', () => this.activate());
    this.addCommand({ id: 'open', name: 'Open study graph', callback: () => this.activate() });
    this.refreshSoon = obsidian.debounce(() => this.refreshViews(), 700, true);
    const touches = (path) => typeof path === 'string' && CONCEPT_PATH.test(path);
    this.registerEvent(this.app.metadataCache.on('changed', (file) => { if (touches(file.path)) this.refreshSoon(); }));
    this.registerEvent(this.app.vault.on('delete', (file) => { if (touches(file.path)) this.refreshSoon(); }));
    this.registerEvent(this.app.vault.on('rename', (file, old) => { if (touches(file.path) || touches(old)) this.refreshSoon(); }));
    // At start-up the index may not be finished when a restored graph tab first reads it: refresh once when it is.
    let initial = true;
    this.registerEvent(this.app.metadataCache.on('resolved', () => { if (initial) { initial = false; this.refreshSoon(); } }));
  }

  onunload() {
    if (this.refreshSoon && this.refreshSoon.cancel) this.refreshSoon.cancel();
  }

  async activate() {
    let leaf = this.app.workspace.getLeavesOfType(VIEW_TYPE)[0];
    if (!leaf) {
      leaf = this.app.workspace.getLeaf('tab');
      await leaf.setViewState({ type: VIEW_TYPE, active: true });
    }
    this.app.workspace.revealLeaf(leaf);
  }

  refreshViews() {
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE)) {
      if (leaf.view && typeof leaf.view.refresh === 'function') leaf.view.refresh();
    }
  }

  /** Read every concept note into {nodes, edges}. Same shape as scripts/study_graph.py export. */
  async collect() {
    const files = this.app.vault.getMarkdownFiles()
      .filter((f) => CONCEPT_PATH.test(f.path))
      .sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
    const byName = new Map();
    const infos = files.map((f) => {
      const cache = this.app.metadataCache.getFileCache(f) || {};
      const fm = cache.frontmatter || {};
      return { f, fm, tags: list(fm.tags).map((t) => t.replace(/^#/, '')), aliases: list(fm.aliases) };
    });
    for (const { f } of infos) if (!byName.has(f.basename.toLowerCase())) byName.set(f.basename.toLowerCase(), f.path);
    for (const info of infos) {
      for (const a of info.aliases) if (!byName.has(a.toLowerCase())) byName.set(a.toLowerCase(), info.f.path);
    }
    const texts = await Promise.all(infos.map((i) => this.app.vault.cachedRead(i.f)));
    const nodes = [];
    const edges = [];
    infos.forEach(({ f, fm, tags, aliases }, i) => {
      const text = texts[i] || '';
      const field = (label) => { const m = text.match(FIELD(label)); return m ? m[1].trim() : ''; };
      const statusTag = tags.find((t) => t.toLowerCase().startsWith('status/'));
      for (const m of field('Follows from').matchAll(/\[\[([^\]|#\\]+)/g)) {
        const name = m[1].trim();
        const dest = this.app.metadataCache.getFirstLinkpathDest(name, f.path);
        const target = dest && CONCEPT_PATH.test(dest.path) ? dest.path : byName.get(name.toLowerCase());
        if (target && target !== f.path) edges.push({ source: f.path, target });
      }
      const slide = field('Slides').match(/\[\[([^\]|]+)/);
      nodes.push({
        id: f.path,
        name: f.basename,
        course: CONCEPT_PATH.exec(f.path)[1],
        status: statusTag ? statusTag.slice(7).toLowerCase() : 'unknown',
        kind: String(fm.kind || ''),
        statement: field('Statement'),
        aliases,
        slide: slide ? slide[1].trim() : '',
      });
    });
    return { nodes, edges, vault: this.app.vault.getName() };
  }

  /** Open a file to the side of the graph, reusing the same pane each time. */
  async openBeside(path, subpath) {
    let file = this.app.vault.getAbstractFileByPath(path);
    if (!(file instanceof obsidian.TFile)) file = this.app.metadataCache.getFirstLinkpathDest(path, '');
    if (!(file instanceof obsidian.TFile)) { new obsidian.Notice('Not found: ' + path); return; }
    let alive = false;
    if (this.noteLeaf) this.app.workspace.iterateAllLeaves((l) => { if (l === this.noteLeaf) alive = true; });
    if (!alive) this.noteLeaf = this.app.workspace.getLeaf('split', 'vertical');
    await this.noteLeaf.openFile(file, subpath ? { eState: { subpath } } : undefined);
  }

  hooks(view) {
    return {
      openNote: (n) => this.openBeside(n.id),
      openSlide: (n) => {
        const [path, sub] = n.slide.split('#');
        this.openBeside(path, sub ? '#' + sub : '');
      },
      renderStatement: (el, text, n) => {
        el.empty();
        // A fresh Component per render, so rendered children don't pile up on the view.
        if (view.md) view.md.unload();
        view.md = new obsidian.Component();
        view.md.load();
        const MR = obsidian.MarkdownRenderer;
        const done = typeof MR.render === 'function'
          ? MR.render(this.app, text, el, n.id, view.md)
          : MR.renderMarkdown(text, el, n.id, view.md);
        Promise.resolve(done).catch(() => { el.textContent = text; });
      },
      copy: (text) => {
        navigator.clipboard.writeText(text).then(
          () => new obsidian.Notice('Copied: ' + text),
          () => new obsidian.Notice('Copy failed'),
        );
      },
    };
  }
}

module.exports = StudyGraphPlugin;
