# Requirements: from mission to detail

The mission and eleven stages follow the approved SRS. Quality requirements retain a separate tree. The sunburst counts each matching requirement once; the interactive tree preserves every authored parent and level.

**Limits:** this view shows requirement structure and trace links; it does not establish verified satisfaction.

<div class="understanding" data-understanding="requirements">
<p class="ug-status" role="status">Loading repository data...</p>
<div class="ug-toolbar">
<label>Search UID, HID or statement<input id="ug-search" type="search" placeholder="FR-19, RECS or provenance"></label>
<label>Stage<select id="ug-stage"></select></label><label>Area<select id="ug-area"></select></label><label>Status<select id="ug-status-filter"></select></label>
<button class="ug-button" id="ug-reset">Reset filters</button>
</div>
<div id="ug-legend" class="ug-legend"></div>
<h2>Overview sunburst</h2>
<p>Hover for names and counts. Select a stage or area to filter, or a requirement to open its card. The center resets the filters.</p>
<div id="ug-sunburst" class="ug-chart"></div>
<h2>Authored requirement tree</h2>
<p>Start at the mission and the eleven stages, with a separate non-functional branch. Click a node, or focus it and press Enter, to expand or collapse its authored descendants. Requirement labels show HID and UID; hover for the first words of the statement. Selecting a requirement also updates its neighborhood and card below.</p>
<p>For example, search for <code>FR-19</code> to reveal and highlight every matching path. Stage, area and status filters retain ancestors as context. Use the scrollbars to explore at a readable scale.</p>
<button id="ug-expand" class="ug-button">Expand all</button>
<button id="ug-collapse" class="ug-button">Collapse to stages</button>
<p id="ug-tree-count" class="ug-status" aria-live="polite"></p>
<div id="ug-tree" class="ug-chart ug-tidy-tree" tabindex="0" aria-label="Scrollable requirements tree"></div>
<h2>Neighborhood</h2>
<p id="ug-neighborhood-summary" aria-live="polite">Select a requirement in the tree, sunburst or table to see its parent, children, satisfying modules and verifying tests. At most 30 nodes are shown; the card retains all anchors.</p>
<div class="ug-neighborhood-scroll" tabindex="0" aria-label="Scrollable requirement neighborhood"><div id="ug-neighborhood" class="ug-chart ug-cy" aria-label="Requirement neighborhood graph"></div></div>
<div id="ug-card" class="ug-card" aria-live="polite"></div>
<h2>Matching requirements</h2>
<div id="ug-results" class="ug-scroll"></div><button id="ug-more" class="ug-button">Show more matches</button>
</div>

[Code structure](code.md) | [Execution path](execution.md) | [Legend and provenance](index.md)
