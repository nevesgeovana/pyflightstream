# Code: context, layers and modules

pyflightstream turns an engineer's experiment definition into validated scripts, execution records and engineering products. FlightStream is a separate licensed solver. Cluster scheduling is an alternative execution route.

**Limits:** this view shows static code structure and imports; it does not measure runtime behavior or timing.

<div class="understanding" data-understanding="code">
<h2>C4 context and containers</h2>
<div class="ug-context ug-code-context">
<svg width="100%" viewBox="0 0 1160 540" role="img" aria-labelledby="ug-context-title ug-context-desc">
<title id="ug-context-title">pyflightstream system context and containers</title>
<desc id="ug-context-desc">An engineer invokes command line tools and the Python package. The package reads and writes the workspace, launches FlightStream locally, or submits jobs to a cluster scheduler that runs FlightStream. FlightStream exports outputs to the workspace.</desc>
<defs><marker id="ug-context-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" style="fill:var(--md-typeset-a-color);stroke:none"/></marker></defs>
<rect class="ug-boundary" x="230" y="30" width="510" height="475" rx="18"/><text class="ug-boundary-title" x="485" y="62">pyflightstream system boundary</text>
<rect x="260" y="105" width="220" height="70" rx="9"/><text x="370" y="136">Command line tools</text><text x="370" y="158">Python entry points</text>
<rect x="260" y="260" width="220" height="80" rx="9"/><text x="370" y="293">Python package</text><text x="370" y="318">Library container</text>
<rect x="410" y="410" width="300" height="70" rx="9"/><text x="560" y="439">Workspace on disk</text><text x="560" y="463">Inputs, scripts, records, products</text>
<rect class="ug-external" x="940" y="100" width="200" height="75" rx="9"/><text x="1040" y="132">Cluster scheduler</text><text x="1040" y="155">External system</text>
<rect class="ug-external" x="940" y="275" width="200" height="75" rx="9"/><text x="1040" y="307">FlightStream solver</text><text x="1040" y="331">External system</text>
<circle class="ug-person" cx="85" cy="230" r="17"/><path class="ug-person" d="M85 247 V278 M60 260 H110 M85 278 L65 300 M85 278 L105 300"/><text x="85" y="325">Engineer</text>
<g class="ug-context-edges" marker-end="url(#ug-context-arrow)">
<path d="M85 208 V140 H260"/><path d="M115 285 H260"/>
<path d="M370 260 V215 H840 V138 H940"/>
<path d="M480 305 H940"/>
<path d="M1040 175 V275"/>
<path d="M480 330 H560 V410"/>
<path d="M1040 350 V445 H710"/>
</g>
<text x="175" y="127">invokes</text><text x="183" y="274">invokes</text>
<text x="630" y="202">submits jobs</text><text x="710" y="290">launches on a workstation</text>
<text x="1070" y="230">runs</text><text x="638" y="371">reads and writes</text><text x="855" y="431">exports outputs</text>
</svg>
</div>
<p class="ug-context-legend">Legend: person icon = engineer; solid boxes inside the boundary = pyflightstream containers; dashed boxes = external systems.</p>
<p class="ug-status" role="status">Loading repository data...</p>
<h2>Package layers</h2>
<p>Box width follows physical lines, with a readable minimum. Each row is one layer rank, starting at rank 0. Arrows point from importers to dependencies; red marks upward imports or cycles. Hover or focus a box to highlight incoming and outgoing imports. Select a box for its modules. Standalone root modules can be included to inspect initialization cycles.</p>
<div class="ug-toolbar"><label>Scope<select id="ug-code-scope"><option value="packages">Directory packages</option><option value="all">All root units</option></select></label><button id="ug-code-fit" class="ug-button">Reset layer view</button></div>
<div id="ug-layers" class="ug-chart ug-layer-boxes" tabindex="0" aria-label="Package layers, scroll to explore"></div>
<div id="ug-package-card" class="ug-card" aria-live="polite"></div>
<div id="ug-module-graph" class="ug-chart ug-cy" hidden></div>
<div id="ug-card" class="ug-card" aria-live="polite"></div>
<h2>Dependency structure matrix</h2>
<p>Rows import columns. Each cell gives the number of cross-unit AST import occurrences. Red has the same meaning as in the layer graph. Select a cell to inspect its import locations.</p>
<div id="ug-dsm" class="ug-scroll"></div><div id="ug-edge-card" class="ug-card"></div>
<h2>Module size treemap</h2>
<p>Each tile is a module, sized by physical lines including comments and blank lines. Select a tile or use the module selector for small tiles. Color groups packages; it does not measure quality.</p>
<div class="ug-toolbar"><label>Package<select id="ug-treemap-package"></select></label><label>Module<select id="ug-module-select"></select></label></div>
<div id="ug-treemap" class="ug-chart"></div>
</div>

[Requirements](requirements.md) | [Execution path](execution.md) | [Legend and provenance](index.md)

<style>

.ug-code-context{overflow:auto;border:1px solid var(--ug-border);border-radius:8px}
.ug-code-context svg{display:block;min-width:0;width:100%;max-width:100%;height:auto}
.ug-code-context text{font-size:18px}
.ug-code-context .ug-boundary{fill:none;stroke:var(--md-default-fg-color--light);stroke-width:2}
.ug-code-context .ug-boundary-title{font-weight:700}
.ug-code-context .ug-external{stroke-dasharray:6 4}
.ug-code-context .ug-person{fill:none;stroke:var(--md-default-fg-color);stroke-width:2}
.ug-code-context .ug-context-edges path{stroke:var(--md-typeset-a-color);fill:none;stroke-width:2}
.ug-context-legend{font-size:13px;white-space:normal}
.ug-layer-boxes{overflow:auto;max-height:1100px;min-height:300px}
.ug-chart.ug-layer-boxes svg{width:auto;max-width:none;height:auto}
.ug-layer-row{fill:var(--md-code-bg-color);opacity:.55}
.ug-layer-rank,.ug-layer-node text{fill:var(--md-default-fg-color);font:14px sans-serif}
.ug-layer-node{cursor:pointer;outline:none}
.ug-layer-node rect{fill:var(--md-default-bg-color);stroke:var(--md-typeset-a-color);stroke-width:1.5}
.ug-layer-node .ug-layer-name{font-weight:700;font-size:15px}
.ug-layer-node:hover rect,.ug-layer-node:focus rect,.ug-layer-node.ug-active rect{stroke-width:3}
.ug-layer-edge{fill:none;stroke:var(--md-typeset-a-color);stroke-width:1.3;opacity:.32;cursor:pointer}
.ug-layer-edge.ug-risk{stroke:#d64c59;opacity:.8}
.ug-layer-edge.ug-active{opacity:1;stroke-width:2.5}
.ug-layer-node.ug-dim,.ug-layer-edge.ug-dim{opacity:.1}

</style>
