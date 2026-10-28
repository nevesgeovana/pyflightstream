# Mesh inputs and GUI-only operations

A matrix row names a saved simulation (`.fsm`). Start from an OBJ by
preparing its named declarations, running `geometry mark-boundaries --apply`
once, and inspecting the resulting FSM. GUI-prepared FSM files are accepted
without a marking record. CAD, CCS and STL construction belong to
[geometry build](../geometry.md), which keeps its own solver pass.

## Starting from an OBJ or STL

For an OBJ, write `<stem>.obj.boundaries.toml` with the boundary inventory,
`fs_build`, `[import] units`, and named `[trailing_edges.<label>]` entries.
Termination nodes belong to their trailing-edge entry and base regions to
`[base_regions.<family>]`. Use the [reference](reference.md) for the complete
form. Preview marking without a solver, then apply it with a licensed solver.
The matrix names `<stem>.fsm`, never the OBJ. An STL first needs geometry
preparation into a saved body or an OBJ suitable for marking.

### Writing a points file from a blade's mesh

`pyflightstream.workspace.trailing_edge_midpoints` reads a blade surface and
returns the mid-point of every mesh edge on its trailing edge, in order along
the span, and `write_trailing_edge_node_file` writes them as the blade's
points file. The points come back in the MESH's own reference frame and length
units, because they are mid-points of mesh edges and nothing transforms them.
The rotor axis and hub you pass in are what the CRITERION is computed in, not
what the output is expressed in. The file it writes is the file a
`[trailing_edges]` table names, `file = "blade.te.txt"`, and the marking pass saves these edges before a row runs.

<!-- skip: next -->
```python
from pyflightstream.workspace import write_trailing_edge_node_file

write_trailing_edge_node_file(
    "blade.obj", "blade.te.txt", axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), unit="METER"
)
```

That block is skipped by the executable-examples run, because it names a
blade mesh and this repository commits no blade. The name it imports is
checked all the same: the offline suite resolves
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

## Refining or coarsening a mesh

`pyfs-matrix refine` writes a finer or a coarser LEVEL of a panel mesh from its
OBJ, without returning to the pre-processor, and keeps what the mesh's author
chose: the clustering, the trailing edge, the junctions between surfaces and
the face order the solver reads. The source is never modified. The command
needs no executable, no matrix and no workspace.

In the examples below `W1.obj` holds two families, a wing grid `Wing` and a
triangulated tip `Tip`.

Refine with a factor on the command line:

```text
pyfs-matrix refine inputs/geometries/W1/W1.obj 2
```

The level keeps the source's marking declarations. To mark its edges, edit the
level's `[trailing_edges.<label>] file`; the next section shows how the trailing
edges are listed and exported.

This writes the level folder `inputs/geometries/W1_R2/`:

```text
inputs/geometries/W1_R2/
    W1_R2.obj               the refined mesh
    W1_R2.obj.boundaries.toml   preserved declarations and updated inventory
    W1_R2.refine.json       what was done to each family
    W1_R2.audit.json        the audit of the level against its source
```

While it runs, `refine` prints timed progress lines to stderr, one per stage and
family (`[refine 14:02:11 +3.2 s] grid 1 of 2: Wing (...)`), so a long
refinement shows it is moving; `--log-level quiet` hides them. At the end the
console names each family with the method it took (`Wing: grid`), prints
the audit's summary and then every file written. The level is a geometry of its
own and is marked like any OBJ:
`pyfs-workspace geometry mark-boundaries inputs/geometries/W1_R2/W1_R2.obj --apply`,
and the saved `W1_R2.fsm` is named in a row's `GEOMETRY` column. A row naming
`W1_R2.obj` is refused ([matrix geometry](../geometry.md#matrix-geometry)).

The level folder goes beside the folder holding the source. For a geometry kept
in its own folder (`inputs/geometries/W1/W1.obj`) that is the geometry library,
which is where a row looks. For a geometry in the flat layout
(`inputs/geometries/W1.obj`) the default would be `inputs/`, outside the
library, so give the folder: `--out inputs/geometries`. An existing level
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
they are. `--parallel F` and `--normal F` replace the factor in one direction
of the selected grid families: `--parallel` runs along the family's reference
perimeter, `--normal` across it. They are refused for a family that is
remeshed, so here they go with `--families Wing`:

```text
pyfs-matrix refine inputs/geometries/W1/W1.obj 2 --families Wing
pyfs-matrix refine inputs/geometries/W1/W1.obj --normal 1.5 --parallel 0.7 --families Wing
```

The first writes `W1_R-Wing2`, the second `W1_R-Wing1c1p5s0p7`. A mesh whose
families are all grids takes `--normal 1.5 --parallel 0.7` alone, tagged
`R1c1p5s0p7`. A family that is not a grid but is given a directional factor is
refused; `--accept-remesh` remeshes it with FACTOR instead, with a warning.
The earlier names `--chordwise` and `--spanwise` (and the keys `chordwise` and
`spanwise`) are read as `--normal` and `--parallel`, with a warning.

A tag built from a long selection, more than 32 characters, is shortened to
`R-<n>fam-<hash>`: the number of selected families and a hash of the
selection, so `W1_R-12fam-<hash>` for twelve families. The selected families
are then listed under `tag_selection` in the level's `refine.json`. To choose
the name yourself, state `[refine] tag` in the refinement file.

### Which families stay grids

Each family of the OBJ (each `g` or `o` group) is handled on its own. A family
whose faces form a structured grid, read from the connectivity alone, is
resampled along its two index directions by a cubic spline through its nodes:
quadrilaterals, or quadrilaterals each split into two triangles, laid out as a
sheet, or as a tube whose ends are open, closed by a fan of triangles around one
pole node, or closed by a zipper of triangles. A sheet is oriented by its reference perimeter: the line of
the grid that fixes which edge is index 0, taken from a `[[perimeter]]` node
list (see [From an OBJ to a marked level](#from-an-obj-to-a-marked-level)) or
else from the mesh. A grid family with no trailing edge takes the side of its
boundary that holds a neighbouring family's trailing edge, else its longest
side, and warns which. A smooth tube is recovered without one, its seam
standing in. The reference perimeter, the leading
edge and the end stations are knots of the spline, so the clustering is kept
and they do not move, and the level is written in the source's face order.

Any other family is remeshed: refined towards the source's local edge length
divided by its factor, into triangles whose nodes lie on the source surface.
Open boundaries, the trailing edge and every edge whose dihedral exceeds 40
degrees are curves the nodes move along and never leave. A mesh whose families are all grids refines
without any remesh. `W1_R2.refine.json` names, per family, the method taken and the
reason a grid was or was not recovered.

Grids that share nodes stay grids together. Grid families of quadrilaterals
that touch (a stabilizer, its centre strip and its junction strips, say) are
resampled as one layout: each curve two of them share is resampled once, so
both hold the same nodes on it, and each family keeps its own faces, their
orientation and its face order. The factors of the two families must give a
shared curve the same number of intervals, or the refinement is refused
naming both families and the curve; `refine.json` names under `grouped_with`
the families each grid was resampled with. A tube or a family with triangles joins no such layout: of grids that share
nodes, the first in the file's family order is then a grid and a later one is
remeshed under `method = "auto"`, or refused under `method = "grid"`.

When two families meet, they keep meeting on shared nodes. A family that shares
a curve with a refined grid is rebuilt on the grid's new nodes; a family the
refinement does not change is remeshed only in a band of two face layers along
that curve, and is otherwise the source's face for face. When that band would
hold every face of the family (a cap two face layers deep, say), the family is
rebuilt whole at factor 1 instead, as if its table stated `factor = 1` and
`method = "remesh"`; one warning names it and its face count, and
`refine.json` records it as `rebuilt_whole`. A family rebuilt at factor 1
beside a refined grid takes, along the shared curve, the spacing of the grid's
new nodes there, graded back to its own size over two face layers, so no face
of the rebuilt family is squeezed at the shared curve.

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
number of patches and each patch's rows and columns. A multiblock family has
no single normal or parallel direction, so `--normal` and `--parallel`
apply to it side by side: a patch side running within 45 degrees of the
family's reference perimeter is parallel, any other normal, so a junction strip
can be coarsened normal only with `normal_factor = 0.77` and `parallel_factor = 1`.
Opposite sides of a patch must read alike and its two directions must
differ; a patch whose directions cannot be told apart is refused naming it,
and then `FACTOR` or a `factor` in its table applies to both directions. Across a patch side the level is
continuous but not smooth: no spline crosses it.

A patch side of m intervals that a factor below 1/m cannot coarsen (a strip
one face wide, say, at any factor below 1) is kept, with `max(1, round(f m))`
intervals, and the rest of the family is resampled as asked. One warning names
the family and, for each kept side, its patch, which side, both counts and
where the patch lies (centroid and bounding box in the mesh's units), and
`refine.json` lists the same under `kept_sides`. A family with a triangle, one patch, or a patch that is not
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
Pairing can raise the audit's size growth and skewness figures, since a
quadrilateral beside a triangle reads as a size jump and a paired rhombus as
skewed; the audit warns only when a figure exceeds its limit, and the level
is written. Read the reported values in the audit.

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
new nodes, and `[components]` writes the two as the one family the solver must see,
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

### From an OBJ to a marked level

The path from a mesh to a marked, refined geometry has six steps; the first is
optional.

1. **Prepare the patches (optional).** `prepare-to-refine` cuts every family at
   its sharp edges into patches that the refinement recovers as grids
   (`<family>_<NNN>_grid`) and patches that it remeshes (`<family>_<NNN>_mixed`):

   ```text
   pyfs-workspace geometry prepare-to-refine inputs/geometries/W1/W1.obj
   ```

   It writes, beside the mesh and without modifying it, `W1_patches.obj`,
   `W1_patches.refine.toml` and `W1_patches.nodes.txt`. The refine file holds
   every patch at factor 1 and `[components]` putting each family back
   together; the node list holds the rearmost line of each grid patch, the
   edges within `--max-angle` (default 45 degrees) of the plane across the
   aft direction, as an ANSA SET node list. `--aft X Y Z` states the nose to
   tail direction (default +x, so the plane is the yz plane). Any OBJ and refine file refine without this step.

   To follow the pre-processor's meshing macros instead of the sharp edges,
   give an ANSA NASTRAN export written with the FE perimeters on
   (`comment_output_fe_perimeters`): each family is then cut along those
   perimeters, so each patch is one macro. `--unit` states the export's
   length unit (default MILLIMETER) and `--obj-unit` the unit the patches OBJ
   is written in (default METER):

   ```text
   pyfs-workspace geometry prepare-to-refine inputs/geometries/W1/W1.nas
   ```
2. **Edit the refine file.** Set the factors of the patches and their
   `method`. The file names the node list in a `[[perimeter]]` table:

   ```toml title="inputs/geometries/W1/W1_patches.refine.toml"
   [refine]
   filename = "W1_fine"

   [families.Wing_001_grid]
   parallel_factor = 2
   normal_factor = 1.5
   method = "grid"

   [components]
   Wing = ["Wing_001_grid", "Wing_002_mixed"]

   [[perimeter]]
   file = "W1_patches.nodes.txt"
   export_te_per_family = true
   te_families = ["Wing"]
   ```

   A node list can also come from the pre-processor: save the nodes of an
   ANSA SET from its node window. One list may hold the perimeters of every
   component, in any node order. With `export_te_per_family = true` the list
   holds trailing edges, and the level writes them; `te_families` instead
   takes the rearmost line of each named family from a list that holds every
   perimeter.
3. **Refine.**

   ```text
   pyfs-matrix refine inputs/geometries/W1/W1_patches.obj
   ```

   With no factor on the command line the factors come from the refine file
   beside the mesh. `[refine] filename` names the level's folder and OBJ in
   place of `<stem>_<tag>`. The level `inputs/geometries/W1_fine/` holds the
   refined mesh, the trailing edges as `W1_fine.te.txt` and
   `W1_fine.<family>.te.txt`, and its boundaries file.
4. **Edit the level's boundaries file types.** When the trailing edges were
   exported and the source declares none, the level's
   `<level>.obj.boundaries.toml` declares one table per component:

   ```toml
   [trailing_edges.Wing]
   file = "W1_fine.Wing.te.txt"
   type = "STANDARD"
   ```

   Change the `type` of each, and add `fs_build`, `[import] units` and the
   other declarations as for any OBJ ([the reference](reference.md)). A
   source file that declares its own trailing edges keeps them.
5. **Mark the boundaries.** The level is a geometry of its own:

   ```text
   pyfs-workspace geometry mark-boundaries inputs/geometries/W1_fine/W1_fine.obj --apply
   ```

6. **Name the saved simulation** in a row's `GEOMETRY` column.

### Looking at a mesh and its marked points

`visual-inspect` writes a PDF of an OBJ or NASTRAN mesh: the top, front,
side and isometric views as a technical drawing (one scale, aligned, a scale
bar), each patch in its own color from `--cmap` with its perimeter in a
thick line, node lists (`--nodes`) and trailing-edge points files (`--te`)
over the surface, and a table of each patch's faces and marked points.
`--png` also writes the pages of views as PNG files.

```text
pyfs-workspace geometry visual-inspect inputs/geometries/W1/W1_patches.obj --nodes inputs/geometries/W1/W1_patches.nodes.txt --mesh-unit METER
```

From Python, `visual_inspect` of `pyflightstream.workspace` takes the same
inputs and returns the path of the PDF.

### Marking trailing edges without refining

`identify-te` writes the trailing edges of an OBJ in the format the solver
imports, for a mesh that is not refined:

```text
pyfs-workspace geometry identify-te inputs/geometries/W1/W1.obj
pyfs-workspace geometry identify-te inputs/geometries/W1/W1.obj --families Wing,Tail
```

Without a node list the edges are found from the mesh: each family is cut at
its sharp edges and its rearmost boundary edges within `--max-angle` of the
plane across `--aft` (the yz plane by default) are kept. The command writes `W1.nodes.te.txt` for every family (or
`W1.<family>.fs.te.txt` for each family named by `--families`) and, beside it,
`W1.nodes.txt`, the ANSA node list a refine file reads. With a node list
saved from a SET, `identify-te W1.obj nodes.txt` takes the trailing edges among
its lines, on a refined level with merged families too. `--unit` states the
coordinates' unit and `--simulation-unit` the unit the solver reads the file
in. Name the written file in the boundaries file,
`[trailing_edges.<label>] file = "W1.nodes.te.txt"`, and mark the OBJ.

A node list saved from the pre-processor in any node order becomes a points file
with `convert2midnodes`:

```text
pyfs-workspace geometry convert2midnodes nodes.txt wing.te.txt
pyfs-workspace geometry convert2midnodes nodes.txt wing.te.txt --per-family inputs/geometries/W1/W1.obj
```

The nodes are ordered along their lines (a long jump starts a new line), and
each neighbouring pair gives one mid-point. With `--per-family` the file is
written per family of the OBJ, as `wing.<family>.te.txt`, from the mesh edges
joining two listed nodes.

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
G4 pass on (whole mesh): points 16, points_on_edges 16, chains 1, source_chains 1, length 3.2, source_length 3.2, source_ends 2, source_ends_missing 0
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
pyfs-matrix audit-mesh inputs/geometries/W1_R2/W1_R2.obj --against inputs/geometries/W1/W1.obj --out W1_R2_audit.csv
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
the offline suite. The refinement file, every key,
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
consumed.

When a mesh exists only inside a `.fsm`, the pre-processing export
(`run.export_surface_mesh`) produces the OBJ counterpart through a solver run,
which is how the geometry gate of the probe planner gets its watertight
surface.
