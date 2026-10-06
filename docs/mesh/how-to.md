# Mesh inputs and GUI-only operations

This page is for a user who brings a mesh to a run. Two inputs are canonical,
and a workflow row takes both:

* a raw surface mesh, an `.obj` or an `.stl`, which the script IMPORTS through
  the mesh-import family, with OBJ as the reference format; and
* a saved simulation, a `.fsm`, which the script OPENS, made once in the
  FlightStream GUI when a step has no scripting command.

This page walks through preparing a raw mesh or a saved simulation. The
[reference](reference.md) defines their sidecars, build support and measured
limits; [the complete example](example.md#a-complete-example-a-wing-obj-with-its-trailing-edge-by-file)
provides a wing OBJ setup to copy.

A workflow row imports `.obj` and `.stl` and opens `.fsm`. Explicit IGES
conversion is a separate route described in the [reference](reference.md); STEP remains refused. A
recipe of your own reaches every format the mesh-import family documents;
the other formats `IMPORT` documents stay there, because what the solver
makes of their surfaces' names and order is unmeasured.

## Starting from an OBJ or STL

A mesh file carries surfaces and nothing else: no length unit, no name this
package reads, no trailing edge. So everything a run needs to know about it is
written in one file beside it, `<stem>.boundaries.toml` (`wing.boundaries.toml`
beside `wing.obj`), and every row that names the mesh shares it. The row names
the mesh as it names any geometry, `wing.obj` in its `GEOMETRY` column.

The sidecar says, in this order:

1. `boundaries`: the names of the mesh's surfaces, in the order the solver
   numbers them, which the plan writes for an `.obj` from its groups when it
   has no sidecar;
2. `[import]`: `units`, the length unit the file is written in;
3. `[[import.operations]]`: the operations that make the file into the body,
   when it is not the body yet;
4. `[trailing_edges]`: how the trailing edge is marked, by a points file (the
   default), by detection, or explicitly absent with `none = true`;
5. `[wake_termination]` and `[base_regions]`: two detections, each applied
   only when written.

The [reference](reference.md) describes each sidecar field, build support and
measured limits. The next section shows how to write the points file.

### Writing a points file from a blade's mesh

`pyflightstream.workspace.trailing_edge_midpoints` reads a blade surface and
returns the mid-point of every mesh edge on its trailing edge, in order along
the span, and `write_trailing_edge_node_file` writes them as the blade's
points file. The points come back in the MESH's own reference frame and length
units, because they are mid-points of mesh edges and nothing transforms them.
The rotor axis and hub you pass in are what the CRITERION is computed in, not
what the output is expressed in. The file it writes is the file a
`[trailing_edges]` table names, `file = "blade.te.txt"`, and a row naming the
blade then marks exactly these edges.

<!-- skip: next -->
```python
from pyflightstream.workspace import write_trailing_edge_node_file

write_trailing_edge_node_file(
    "blade.obj", "blade.te.txt", axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), unit="METER"
)
```

That block is skipped by the executable-examples run, because it names a
blade mesh and this repository commits no blade. The name it imports is
checked all the same: `tests/tier1_offline/test_mesh_inputs_page.py` resolves
every name a python block on this page imports, so a rename fails the suite
rather than leaving the block stale.

The vertices and the faces are read. The mesh need not be watertight and no
proximity query is made, so this runs on a base install with no extra.
`extract_trailing_edge` still returns one aftmost vertex per section, and
`TrailingEdge.write_node_file` refuses: a list of vertices marks nothing.

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
direction taken from the section's own extent. The trailing edge between two
sections is the shortest chain of mesh edges joining their aftmost points,
along edges that are the aft ridge of both their faces: the far vertex of each
face lies forward of the edge, forward meaning against the section's aft chord.
The chain continues past the first and last section while exactly one such edge
leads outward, and each edge of it gives one mid-point. No angle is compared
with a threshold. A blunt trailing edge, two aft corners at each station, is
refused rather than guessed. The reasoning, and the alternatives that were
rejected, are in the design note `DD-27`.

An OBJ file's named group for the trailing edge would have been the preferred
route and was measured and dropped: the mesh library this package reads the
mesh through does not surface OBJ group names, so a blade exported with its
trailing edge already named as a group offers nothing that library can see.
The groups ARE read for the SURFACE NAMES from the file's own text
(G30, RPT-078: `IMPORT` makes one boundary per group holding a face, in file
order).

## Refining or coarsening a mesh

`pyfs-matrix refine` writes a finer or a coarser LEVEL of a panel mesh from its
OBJ, without returning to the pre-processor, and keeps what the mesh's author
chose: the clustering, the trailing edge, the junctions between surfaces and
the face order the solver reads. The source is never modified. The command
needs no executable, no matrix and no workspace.

In the examples below `W1.obj` holds two families, a wing grid `Wing` and a
triangulated tip `Tip`.

```text
pyfs-matrix refine inputs/geometries/W1/W1.obj 2
```

This writes the level folder `inputs/geometries/W1_R2/`:

```text
inputs/geometries/W1_R2/
    W1_R2.obj               the refined mesh
    W1_R2.te.txt            the trailing-edge points, rewritten from the new mesh
    W1_R2.boundaries.toml   the source's sidecar, naming the new points file
    W1_R2.refine.json       what was done to each family
    W1_R2.audit.json        the audit of the level against its source
```

The console names each family with the method it took (`Wing: grid`), prints
the audit's summary and then every file written. The level is a geometry of its
own, so a row names it as it names any geometry, `W1_R2.obj` in its `GEOMETRY`
column, and the sidecar written beside it is the one the run reads.

The level folder goes beside the folder holding the source. For a geometry kept
in its own folder (`inputs/geometries/W1/W1.obj`) that is the geometry library,
which is where a row looks. For a geometry in the flat layout
(`inputs/geometries/W1.obj`) the default would be `inputs/`, outside the
library, so give the folder: `--out-dir inputs/geometries`. An existing level
folder is refused unless `--overwrite` is given, and a refused request writes
nothing.

### Choosing the factors

The FACTOR multiplies the number of intervals of a structured grid along each
of its two index directions (2 doubles them, 0.5 halves them) and divides the
target edge length of any other family. A study of three levels is three
commands:

```text
pyfs-matrix refine inputs/geometries/W1/W1.obj 0.5
pyfs-matrix refine inputs/geometries/W1/W1.obj 1
pyfs-matrix refine inputs/geometries/W1/W1.obj 2
```

They write `W1_R0p5`, `W1_R1` and `W1_R2` (`p` is the decimal point). The
level at factor 1 is the control of the study: its OBJ holds the source's
vertex and face lines, in the source's order.

`--families A,B` changes only the named families and leaves the others as
they are. `--chordwise F` and `--spanwise F` replace the factor in one index
direction of the selected grid families (around the section and along the
stations); they are refused for a family that is remeshed, so here they go with
`--families Wing`:

```text
pyfs-matrix refine inputs/geometries/W1/W1.obj 2 --families Wing
pyfs-matrix refine inputs/geometries/W1/W1.obj --chordwise 1.5 --spanwise 0.7 --families Wing
```

The first writes `W1_R-Wing2`, the second `W1_R-Wing1c1p5s0p7`. A mesh whose
families are all grids takes `--chordwise 1.5 --spanwise 0.7` alone, tagged
`R1c1p5s0p7`.

### Which families stay grids

Each family of the OBJ (each `g` or `o` group) is handled on its own. A family
whose faces form a structured grid, read from the connectivity alone, is
resampled along its two index directions by a cubic spline through its nodes:
quadrilaterals, or quadrilaterals each split into two triangles, laid out as a
sheet, or as a tube whose ends are open, closed by a fan of triangles around one
pole node, or closed by a zipper of triangles. The trailing edge, the leading
edge and the end stations are knots of the spline, so the clustering is kept
and they do not move, and the level is written in the source's face order.

Any other family is remeshed: refined towards the source's local edge length
divided by its factor, into triangles whose nodes lie on the source surface.
Open boundaries, the trailing edge and every edge whose dihedral exceeds 40
degrees are curves the nodes move along and never leave. Remeshing needs the geometry extra,
`pip install pyflightstream[geom]`; a mesh whose families are all grids refines
without it. `W1_R2.refine.json` names, per family, the method taken and the
reason a grid was or was not recovered.

When two families meet, they keep meeting on shared nodes. A family that shares
a curve with a refined grid is rebuilt on the grid's new nodes; a family the
refinement does not change is remeshed only in a band of two face layers along
that curve, and is otherwise the source's face for face.

### Tubes and multiblock families

Two more layouts are recovered as grids, from the connectivity alone, when a
family holds quadrilaterals only. A SMOOTH TUBE (a nacelle, a duct, a spinner
cut open at both ends) has no trailing edge and no edge sharper than the ridge
angle; it is resampled as a grid whose circumferential direction is a periodic
spline, so the seam has no kink, and it writes no trailing-edge points. A
MULTIBLOCK family, such as a body with a cap or a junction, is cut into
four-sided patches along the grid lines that run from its singular nodes (a
node of other than four faces inside, of other than two at the boundary); each
patch side is resampled once, so two patches hold the same nodes on the side
they share.

`W1_R2.refine.json` reports the layout `multiblock` for such a family, with the
number of patches and each patch's rows and columns. Because a multiblock
family has no single chordwise or spanwise direction, `--chordwise` and
`--spanwise` are refused on it, naming it; give it `FACTOR` or a `factor` in
its table. Across a patch side the level is continuous but not smooth: no
spline crosses it. A family with a triangle, one patch, or a patch that is not
four-sided or wraps onto itself is not a multiblock and is remeshed under
`method = "auto"`, as before.

### Quadrilateral elements for a remeshed family

A remeshed family is written in triangles. The key `elements` in a family
table, or in `[refine]` as the default of every remeshed family, asks for
`"quad-dominant"` instead:

```toml title="inputs/geometries/W1/W1.refine.toml"
[refine]
elements = "quad-dominant"

[families.Tip]
factor = 2
elements = "triangles"
```

The remeshed triangles are paired into convex quadrilaterals (every angle
between 30 and 150 degrees, warp at most 10 degrees), never across an open
boundary, the trailing edge or a ridge, best pairs first, and the interior
nodes are smoothed along the surface. `refine.json` reports per family the
elements, the quads, the triangles and the quad share. An unknown value, and
`elements` on a table that states `method = "grid"`, are refused; on a family
that `"auto"` resolves to a grid the key is ignored and `refine.json` says so.
The audit's size growth and skewness checks read a quadrilateral beside a
triangle as a size jump and a paired rhombus as skewed, so a quad-dominant
level warns by construction; the level is written.

### Factor 1

At factor 1 a family under `method = "auto"` is copied: a grid family keeps the
source's nodes and faces in order, and a family that would be remeshed is
unchanged. A family whose table states `method = "remesh"` is remeshed at any
factor, factor 1 included.

### A solid blade kept structured by dummy families

A blade whose tip is closed by a triangulated cap is not one grid: a cap is part
of a grid only when it is a pole fan or a zipper. The pre-processor route is to
split the blade into DUMMY FAMILIES, each region a family of its own, for
example `Blade1_side` (the lateral grid) and `Blade1_tip` (the cap). The
refinement then resamples the side as a grid and remeshes the cap on its
new nodes (with the geometry extra), and `[components]` writes the two as the one family the solver must see,
`Blade1`:

```toml title="inputs/geometries/B1/B1.refine.toml"
[refine]
tag = "R2"

[families.Blade1_side]
factor = 2
method = "grid"

[families.Blade1_tip]
factor = 2

[components]
Blade1 = ["Blade1_side", "Blade1_tip"]
```

```text
pyfs-matrix refine inputs/geometries/B1/B1.obj
```

With no factor on the command line the factors come from `B1.refine.toml`
beside the mesh (or from `--config FILE`). `B1_R2.obj` holds one family
`Blade1`, the side's faces then the cap's, and `B1_R2.boundaries.toml` names
`Blade1` in place of its members. `method = "grid"` makes the refinement refuse
the side, naming why, if its grid is not recovered, rather than remesh it. The
`[components]` and `[refine] tag` of a file beside the mesh are read whatever
gives the factors, so `pyfs-matrix refine inputs/geometries/B1/B1.obj 2`
merges the families too.

### A body, and a periodic sector

A body of revolution (a fuselage, a nacelle, a spinner) can be refined along its
axis and around it independently. Its table states `axial`, `circumferential`
and `axis` in place of `factor`:

```toml title="inputs/geometries/S1/S1.refine.toml"
[families.Spinner]
axial = 2
circumferential = 1
axis = [1.0, 0.0, 0.0]
```

When `Spinner` is the mesh's only family the level is `S1_Ra2t1`; beside
other families it is `S1_R-Spinnera2t1`. Remeshing a body needs the geometry
extra. A periodic sector, one blade of a rotor cut by two planes
through its axis, keeps its two cut faces matched node for node when the file
states the rotation that maps one onto the other:

```toml title="inputs/geometries/P1/P1.refine.toml"
[families.Blade1]
factor = 2

[periodic]
axis = [1.0, 0.0, 0.0]
origin = [0.0, 0.0, 0.0]
copies = 6
```

### Checking a level before a run

Every refinement audits its level against its source and writes
`<stem>_<tag>.audit.json`. A gate or check that fails is a WARNING naming it,
the family and both values; the level is still written and `refine` exits 0, so
read the summary before spending a licensed run:

```text
audit of W1_R2.obj against W1.obj
G1 pass on (whole mesh): edges_of_more_than_two_faces 0, node_pairs_at_one_position 0, faces_of_zero_area 0
G2 pass on (whole mesh): neighbours_of_opposite_orientation 0
G3 pass on (whole mesh): open_loops 1, source_open_loops 1, unmatched_loops 0
G4 pass on (whole mesh): points 16, points_on_edges 16, chains 1, source_chains 1
G5 pass on Wing and Tip: shared_nodes 37, source_shared_nodes 19
G6 not judged on (whole mesh): grid_families_at_factor_1 0
relative checks: 8 pass, 0 fail, 1 not judged
every gate and check passed
```

A level written with `[components]` is audited against the union of each
component's members in the source (the components are read from the level's
`refine.json`), so the dummy families of the example above are compared as the
one family the solver sees. A figure within a millionth of a limit or a floor
meets it.

`pyfs-matrix audit-mesh` runs the same audit on any OBJ, alone or against the
mesh it was made from, and its exit status is the verdict: 0 when every gate
and check passes, 1 when one fails, 2 when the input is refused.

```text
pyfs-matrix audit-mesh inputs/geometries/W1_R2/W1_R2.obj --against inputs/geometries/W1/W1.obj --csv W1_R2_audit.csv
```

### From Python

`refine_mesh` and `audit_mesh` of `pyflightstream.workspace` are the functions
the two commands call, with the same files and the same refusals:

<!-- skip: next -->
```python
from pyflightstream.workspace import audit_mesh, refine_mesh

level = refine_mesh("inputs/geometries/W1/W1.obj", 2)
print(level.folder.name)  # W1_R2
for name, family in level.report.items():
    print(name, family["method"])
if not level.audit.passed:
    for item in level.audit.failures:
        print(item.line())

audit = audit_mesh("inputs/geometries/W1_R2/W1_R2.obj", against="inputs/geometries/W1/W1.obj")
print(audit.passed, audit.path.name)  # True W1_R2.audit.json
```

That block is skipped by the executable-examples run because it names a mesh
this repository does not commit; the names it imports are resolved by
`tests/tier1_offline/test_mesh_inputs_page.py`. The refinement file, every key,
the files of a level and the audit's gates are in the
[reference](reference.md#the-refinement-file-and-the-audit).

## The saved simulation: GUI once, script everything after

### The gap this route closes

See [Saved simulation](../continuation-recovery.md#saved-simulation) for the reason this route exists.

### The supported pattern

When a step is GUI-only, the supported workflow is:

1. Perform the GUI-only procedure interactively, once: import the geometry,
   run the manual meshing or repair step, configure what has no command.
2. Save the result as a `.fsm` simulation file. That file is now an input
   artifact: store it in the campaign workspace input library under
   `inputs/`, selected by id like any other artifact, and treat it as
   immutable (redo the GUI step, save a new artifact, never edit in place).
3. Everything downstream stays scripted: scripts `OPEN` the saved `.fsm`,
   `declare_existing` tells the builder which entities (boundaries, frames,
   actuators, motions) the file already contains so index and label checks
   keep working, and solver setup, sweeps, and exports run reproducibly on
   top.

The GUI step itself is the one part the library cannot replay; the saved
`.fsm` is its record. The workspace stages inputs with content hashes following
[`pyflightstream._digest`'s sha256 rule](reference.md#what-that-content-hash-is-and-what-it-leaves-out)
in the run manifest (`inputs_sha256`), so every run names exactly which saved file it
consumed. This policy dates from 2026-07-23.

When a mesh exists only inside a `.fsm`, the pre-processing export
(`run.export_surface_mesh`) produces the OBJ counterpart through a solver run,
which is how the geometry gate of the probe planner gets its watertight
surface.
