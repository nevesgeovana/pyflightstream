# Mesh inputs and GUI-only operations

Policy page: what the library supports when a workflow step exists in
the FlightStream GUI but has no scripting command, and which mesh
inputs are canonical. Adopted 2026-07-23 (PLN-028).

## The gap this page closes

The FlightStream scripting interface covers a subset of what the GUI
can do. The command database only ever contains commands the manual
documents, or that a committed probe report measured the solver accepting
(each entry carries one citation or the other), so a workflow step
with no script command cannot be emitted by the script builder, and
no amount of library code changes that. Geometry preparation and
meshing are the common case, and the picture there changed on
2026-08-06 through 2026-08-08, when the sweep finished: every command
the eight editions registered at that date documented entered the
database, so the CAD, CAD Create and Mesh Operations chapters are
emittable in full, and the last of those is this page's own subject,
everything that translates, rotates, scales, mirrors, copies, cuts,
selects or deletes a surface between import and solver initialization.
The mesh-wrapper chapter is in too, as of 2026-08-08.

**Read the scope of that claim, because a ninth edition has arrived
since.** It is a statement about the eight editions swept in August 2026
and it is not a standing promise about every edition the vendor will
ever publish. SRS non-requirement NREQ-05 excluded nothing at the close
of that sweep; registering 26.123 on 2026-08-17 opened exactly one
exception, `SET_OUTLET_TRAILING_EDGES`, which the SRC-751 edition
documents and this database does not yet carry. That command belongs to
the boundary conditions rather than to meshing, so this page's own subject is
unaffected, and the debt is listed in the SRS evidence queue. What has
NOT changed is the reason this page
exists. A command being in the database means the script builder will
emit and validate it; it does not mean the GUI-driven parts of geometry
preparation have a scripted equivalent, and the pattern below is still
the supported one.

## The supported pattern: GUI once, script everything after

When a step is GUI-only, the supported workflow is:

1. Perform the GUI-only procedure interactively, once: import the
   geometry, run the manual meshing or repair step, configure what
   has no command.
2. Save the result as a `.fsm` simulation file. That file is now an
   input artifact: store it in the campaign workspace input library
   under `inputs/`, selected by id like any other artifact, and treat
   it as immutable (redo the GUI step, save a new artifact, never
   edit in place).
3. Everything downstream stays scripted: scripts `OPEN` the saved
   `.fsm`, `declare_existing` tells the builder which entities
   (boundaries, frames, actuators, motions) the file already
   contains so index and label checks keep working, and solver
   setup, sweeps, and exports run reproducibly on top.

The GUI step itself is the one part the library cannot replay; the
saved `.fsm` is its record. The workspace stages inputs with content
hashes in the run manifest (`inputs_sha256`), so every run names
exactly which saved file it consumed.

### What that content hash is, and what it leaves out

Stated here because this page is where a user is told to trust it, and
a checksum whose rule is unstated cannot settle the question it exists
for: two people holding what they believe is the same input file must
be able to tell whether they really do.

**The algorithm is sha256, and there is no other.** Every digest this
library writes into a manifest comes from `pyflightstream._digest`,
which holds the algorithm as a value rather than as a sentence, so a
tier 1 test spends it and a second algorithm cannot arrive quietly.

**The canonical form is the raw bytes of the staged file**, read in
blocks and never decoded. One manifest field is not a file digest and
is named here so the rule is not over-read: `recipe_sha256` records the
recipe function's SOURCE, and a source text is hashed as its UTF-8
encoding, which is the second canonical form `pyflightstream._digest`
states.

**Nothing around the file enters the digest.** Not the path it was
staged from, not the file name, not its modification time, not the
machine or the user that staged it, and not the order the inputs were
staged in. Those are exactly the fields that differ between two runs
which are otherwise the same run, so admitting one would make the
manifest report two identical runs as different. They are absent by
construction rather than by filtering: the digest reads bytes and
reads nothing else.

Read the consequence for a text mesh, because it is the one that
surprises. An OBJ is bytes like anything else, so the same mesh
checked out with CRLF line endings on one machine and LF on another is
two different files carrying two different digests. That is the digest
being correct about the file rather than wrong about the content: the
solver reads the file, not an idea of it. A `.fsm` artifact is binary
and has no such ambiguity, which is a further reason the pattern above
treats it as immutable. Where a comparison has to survive a
line-ending change, compare the parsed geometry rather than the
manifest digest.

## Canonical mesh inputs

Two input routes are canonical:

* Geometry meshed inside FlightStream, carried as a saved `.fsm`
  artifact (the pattern above).
* A direct surface mesh imported by script through the mesh-import
  family, with OBJ as the reference format.

A workflow row takes both since 0.27.0: it opens a `.fsm` and imports an
`.obj` or an `.stl`. A recipe of your own reaches every format the
mesh-import family documents.

**A RAW MESH STATES ITS UNITS**, and a reader arriving here from a refusal
needs that said before anything else on this page. The mesh-import family
takes the file's length units as an argument (SRC-003 p.307), and a mesh
file carries none. So the file that names the mesh's boundaries,
`<stem>.boundaries.toml` beside it, states the unit the mesh is written in,
in an `[import]` table:

```toml
# inputs/geometries/wing.boundaries.toml, beside wing.obj
boundaries = ["Wing"]

[import]
units = "MILLIMETER"
```

`units` is one of the length units `IMPORT` takes on the row's build, read
from the command database: `INCH`, `MILLIMETER`, `FEET`, `MILE`, `METER`,
`KILOMETER`, `MILS`, `MICRON`, `CENTIMETER` or `MICROINCH`. `OTHER`, which
the command also lists, is refused because it names no length. The row names
the file as it names any geometry, `GEOMETRY: wing.obj`, and its script
starts:

```text
NEW_SIMULATION
IMPORT
UNITS MILLIMETER
FILE_TYPE OBJ
FILE <the point's staged copy of wing.obj>
CLEAR

SET_SIMULATION_LENGTH_UNITS METER
```

and then goes on exactly as it does after opening a `.fsm`. The file's unit
goes to `IMPORT` and nowhere else. The simulation's length unit is always
metres, because every length the reference and the row state is in metres:
the reference area, chord and span, a `TRANSLATE` distance, the frames the
package places. The run record keeps the table as `mesh_import`, because the
geometry's digest alone cannot tell a run in millimetres from the same file
run in metres.

**Whether `IMPORT` converts the body from the file's unit into the
simulation's metres is not measured on any build.** The command database
records the grammar, and no licensed run has yet compared one body imported
in millimetres with the same body in metres. Until one has, a mesh written in
metres (`units = "METER"`) is the one case whose scale does not depend on the
answer.

A unit is never assumed. A raw mesh whose sidecar states no `[import]` table
is refused when the script is built, before any seat is spent, naming the
table, the key, the sidecar and the units the build takes. So is a unit
`IMPORT` does not take, and so is a setup asking to load the solver
initialization, since a new simulation has no stored state to load. An
`[import]` table beside a `.fsm` is refused too, since a saved simulation
carries its own units and nothing would read it. Any other suffix is refused
naming the three that work. The other formats `IMPORT` documents stay with a
recipe of your own, because what the solver makes of their surfaces' names
and order is unmeasured.

When a mesh exists only inside a `.fsm`, the pre-processing export
(`run.export_surface_mesh`) produces the OBJ counterpart through a
solver run, which is how the geometry gate of the probe planner gets
its watertight surface.

### The boundary inventory sidecar

A saved simulation carries its boundary names in the solver's own order,
and a workflow row cites boundaries by those names (`MOVING_BOUNDARIES:
Blade1,Blade2`). The order is a property of the file, so it is never
stated by hand: since v0.11.0 a setup artifact that carries
`mesh_order_list` is refused (PFS-2029.06.01), and the order is written
from the file itself:

```text
pyfs-matrix inventory inputs/geometries/30_WB.fsm
```

writes `inputs/geometries/30_WB.boundaries.toml`, a `boundaries` list in
the file's order, and refuses to overwrite one that exists without
`--overwrite`. The sidecar sits beside the file, so a geometry kept in
its own folder, `inputs/geometries/30_WB/30_WB.fsm` (PFS-2032.04, the
layout `pyfs-workspace migrate-geometries` produces), has it inside that
folder, and the run reads it from there. `pyfs-matrix inventory` refuses a
file without a mesh block (a raw mesh, or a file the solver never saved) by
name, because it has no block to read the order from.

**A raw mesh's names are written by hand.** For an `.obj` or `.stl` you write
the `boundaries` list yourself, beside the `[import]` table, one name per
surface in the order the file holds them, and a row cites those names as it
cites a `.fsm`'s. They are a statement the run trusts rather than verifies:
the file carries nothing this package reads its names from, so a name in the
wrong position cites the wrong surface, and nothing refuses it before the
solver runs. A row whose `.fsm` has a sidecar is
checked when the script opens the file: a sidecar that disagrees with the
file's own block is refused before any seat is spent, naming both lists,
and an agreeing one is recorded in the run record as the inventory source
(`inventory_source: sidecar`; `mesh_block` when the file alone declared the
names). The sidecar is what lets a name resolve for a file whose mesh
block a reader cannot open, and it is otherwise a statement the run
verifies rather than trusts.

## Marking a blade's trailing edge from its mesh

Since v0.8.0 the one step of a rotor campaign that still had to be done by
hand is in the library: `pyflightstream.workspace.extract_trailing_edge` reads
a blade surface and returns its trailing-edge vertices, and
`TrailingEdge.write_node_file` writes them as the node list both documented
marking routes read.

The vertices come back in the MESH's own reference frame and length units,
because they are selected mesh vertices and nothing transforms them. The rotor
axis and hub you pass in are what the CRITERION is computed in, not what the
output is expressed in. The unit is declared once, at `write_node_file`, since
a mesh file does not carry one.

<!-- skip: next -->
```python
from pyflightstream.workspace import extract_trailing_edge

edge = extract_trailing_edge("blade.obj", axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0))
edge.write_node_file("wake_nodes.txt", unit="METER")
```

That block is skipped by the executable-examples run rather than checked,
and the reason is worth one line because every other python block on this page
IS executed: it names a blade mesh, and this repository commits no blade.
NOTHING GUARDS THE NAMES IN IT, which is said rather than left to be assumed:
`tests/tier1_offline/test_guide_api_names.py` reads the user guide alone and
`tests/tier1_offline/test_docs_example_currency.py` reads `workspace-and-workflows.md`
alone, so a rename would leave this block stale and no test would say so. The
first version of this paragraph claimed a guard that does not read this page,
which is worse than no guard at all.

Only the vertices are read. The mesh need not be watertight and no proximity
query is made, so this runs on a base install with no extra.

**THE CRITERION IS NOT A CREASE, and that is the whole point.** The obvious
implementation is a dihedral-angle threshold over face adjacency, which every
mesh library offers. This package refuses it, because marking wake edges from a
file exists precisely BECAUSE the solver's own auto-detection is an angle
criterion, and a strongly twisted blade has a trailing edge that is not a
crease. Building the extraction on adjacency angles would reimplement in Python
the criterion the capability was created to escape, and a campaign would gain a
different threshold rather than a different capability.

What is computed instead: a vertex's spanwise coordinate is its radial distance
from the rotor axis, the vertices are binned into chordwise sections by that
coordinate, and each section contributes its AFTMOST point, with the chordwise
direction taken from the section's own extent. The reasoning, and the
alternatives that were rejected, are in the design note `DD-27`.

An OBJ file's named groups would have been the preferred route and were
measured and dropped: the mesh library this package reads through does not
surface OBJ group names, so a blade exported with its trailing edge already
named as a group offers nothing the reader can see.

## Mesh format policy

The library's mesh seam is deliberately narrow: OBJ in and out. READING a
mesh is a runtime capability since v0.8.0, through trimesh, because the
trailing-edge extraction sits on the default path of a rotor campaign and a
capability behind an extra makes the library promise what a default install
cannot do (design note DD-27, closing PFS-2025.20). What stays in the
`[geom]` extra is the SPATIAL INDEX the geometry gate queries through:
rtree's bounds tree and scipy's kd-tree. Reading vertices and faces needs
neither. Two standing decisions bound any widening:

* More formats never enter through raw third-party APIs. If a
  workflow needs formats beyond OBJ, meshio joins the `[geom]` extra
  as a conversion backend behind a project-owned adapter (decision
  D8, 2026-07-23): the adapter exposes only what the workflow needs,
  a license evidence card is committed at adoption time like every
  dependency, and validity checks stay with trimesh. That decision was
  re-tested in v0.8.0 when a mesh reader had to be chosen and it held:
  meshio was refused on the committed weight budget, at five new
  distributions and 12.26 MiB against limits of one and five, one of them
  a syntax highlighter. Its route into this package is still through the
  adapter and still only if a workflow needs it.
* Until that need materializes, converting external formats to OBJ
  with your own tooling is the supported route.

## The four rotor facts a reference artifact once carried

From 0.8.0 to 0.10.1 the reference artifact's `[rotor]` block recorded
`rotation`, `blade_travel`, `rpm_sign_installed` and `rpm_sign_isolated`,
and no builder read them. From 0.11.0 to 0.21.1 a script stated the rotor
speed's sign through the sign of `RPM` (or `RPM_SIGN` beside
`ADVANCE_RATIO`) and its axis through `ROTOR_AXIS`, on the row; since
0.22.0 the speed a row states is a MAGNITUDE and the hand is `rpm_sign`
on that rotor's own block, beside the axis the block also declares.
Since 0.11.0 a file carrying the four is
refused naming those row keys, and `pyfs-matrix upgrade --in-place
--inputs <inputs dir>` strips them (PFS-2029.08). The argument that
related them is kept here, because it is what a reader setting up a new
rotor has to work out once, and it was measured on the
isolated-rotor reference case (2026-09-01):

* The frame is x aft, y starboard, z up. On a port propeller, +y is
  inboard.
* `blade_travel = "inboard_down"` is the datasheet's side-independent
  vocabulary: the blade at its inboard azimuth (the +y side of the disc)
  travels towards -z. That needs an angular velocity of negative sign about
  +x, which is the "positive rpm is inboard-up" sentence the datasheet
  states the other way round.
* `rotation` is the viewed-from-behind sense. An observer behind the
  aircraft looking forward has screen-right +y and screen-up +z; a point at
  screen-right moving down reads clockwise. So inboard-down on a port
  propeller is clockwise from behind; if the meshes' port and starboard
  assignment is the other way, it is counterclockwise, a one-word edit.
* `rpm_sign_installed = -1` was that sign about +x for the installed
  meshes, and `rpm_sign_isolated = 1` the sign for the isolated meshes,
  which were built the other way round; which of the two applies is a
  property of the mesh a row opens, which is why the row states it.

None of this was ever read by an emitter, and the sense of rotation does
not determine the sign of the rotor speed on its own: the sign is the
mesh's, the sense is the propeller's, and the row is where the two meet.

## What this policy is not

It is not a promise to wrap the GUI. Steps stay GUI-only until the
solver's scripting interface documents a command for them; when that
happens, the command enters the database with its citation and the
step graduates from this page to the reference.
