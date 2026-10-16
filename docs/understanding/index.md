# Understanding pyflightstream

Three linked views connect what the library must do, how it is built and what happens during a steady-polar experiment.

<div class="understanding">
<div class="ug-banner">The mission and eleven stages follow the approved numerical laboratory model. Requirement identifiers, levels, HIDs, parents and statuses come from the authored SRS.</div>
<div class="ug-links"><a href="requirements/">Requirements<br>Mission, stages and traceability</a><a href="code/">Code<br>Context, layers and module size</a><a href="execution/">Execution<br>Steady-polar steps and file flow</a></div>
</div>

Start with a requirement, open one of its modules, then follow that module to an execution step. A package selection lists its modules and every requirement that cites them. URL fragments preserve selections between views.

## Reading the views

| View | Visual encoding | Interaction |
| --- | --- | --- |
| Requirements | Sunburst rings: mission, stage, area, requirement. Equal requirement weight; status colors. The tree retains authored parent edges inside stage and area groups. | Search by UID, HID or statement; filter by stage, area and status; select a requirement for its statement, parent chain, code and tests. |
| Code | Node area and treemap area represent physical lines. Arrows point from importer to dependency; width counts AST import occurrences. Red marks upward edges or cycles. DSM rows import columns. | Select a package, module or matrix cell. The package detail exposes its module graph and traceability. |
| Execution | Ordered swimlane rows show calls and returns in a curated scenario. Sankey widths count declared relationships, with unit weights. | Select a step or module; expand reads and writes; inspect the separate asynchronous branches. |

Implemented is green, pending is amber, deferred is purple and retired is gray. Status describes the authored requirement record, not a fresh test verdict. Neutral gray denotes grouping nodes, which have no requirement status. Colors are accompanied by text in cards and tables.

## Protocol and procedure

The **protocol** is the experiment design recorded before running: the matrix,
setup standard and post-processing declaration describe the cases, conditions,
controls and measurements. The **procedure** is the sequence derived from that
design: the generated solver script and the plan, run and collect operations.
The researcher writes the protocol; the library derives and checks the procedure.

The workspace keeps its governing files in plain text so changes to the protocol
and records can be reviewed under version control. See [Workspace files](../workspace-files.md)
for each file's role and [the numerical laboratory method](../srs/numerical-laboratory-method.md)
for the solver-independent requirements.

## Numerical experiment

<div class="understanding" data-understanding="index"><p class="ug-status" role="status">Loading repository data...</p><div id="ug-mission"></div></div>

## Regeneration and limits

The [Contributing guide](../contributing.md#regenerate-the-understanding-views)
contains the regeneration commands used by CI. The generator reuses the canonical
requirement parser and the AST readers used by arch_metrics. Layer ranks come
from the architecture guard and overview declarations. Exact source hashes
accompany the JSON. Source and test links use the recorded Git revision, including
when CI builds a release tag.

Execution order and file descriptions come from a curated static source trace. Function locations and the example matrix row are regenerated. This is not a solver execution, runtime profile, timing measurement or proof of numerical accuracy. A changed function body can require editorial review even when its name still resolves.

Interactive charts require JavaScript and the chart assets distributed with the
site. A loading failure appears beside the view. The [static requirement tree](../graphs/requirements.md),
[module graph](../graphs/library.md), [data flow](../graphs/data-flow.md) and
[workspace tables](../workspace-files.md) remain available for reading and print.
