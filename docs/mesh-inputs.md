# Mesh inputs and GUI-only operations

This page is for a user who brings a mesh to a run. Two inputs are canonical,
and a workflow row takes both since 0.27.0:

* a raw surface mesh, an `.obj` or an `.stl`, which the script IMPORTS through
  the mesh-import family, with OBJ as the reference format; and
* a saved simulation, a `.fsm`, which the script OPENS, made once in the
  FlightStream GUI when a step has no scripting command.

The first half of the page is the raw mesh: the file that goes beside it, the
points file that marks its trailing edge, which build runs it and what is
measured, and [one complete example](#a-complete-example-a-wing-obj-with-its-trailing-edge-by-file)
to copy. The second half is the saved simulation and the policies that bound
both routes.

A workflow row imports `.obj` and `.stl` and opens `.fsm`, and any other
suffix is refused naming the three that work. A recipe of your own reaches
every format the mesh-import family documents; the other formats `IMPORT`
documents stay there, because what the solver makes of their surfaces' names
and order is unmeasured.

## Starting from an OBJ or STL

A mesh file carries surfaces and nothing else: no length unit, no name this
package reads, no trailing edge. So everything a run needs to know about it is
written in one file beside it, `<stem>.boundaries.toml` (`wing.boundaries.toml`
beside `wing.obj`), and every row that names the mesh shares it. The row names
the mesh as it names any geometry, `wing.obj` in its `GEOMETRY` column.

The sidecar says, in this order:

1. `boundaries`: the names of the mesh's surfaces, in the order the file
   holds them;
2. `[import]`: `units`, the length unit the file is written in;
3. `[[import.operations]]`: the operations that make the file into the body,
   when it is not the body yet;
4. `[trailing_edges]`: how the trailing edge is marked, by a points file (the
   default) or by detection;
5. `[wake_termination]` and `[base_regions]`: two detections, each applied
   only when written.

The sections below take them in that order, then the points file, then which
build runs what and what is measured.

### The surface names

**A raw mesh's names are written by hand.** For an `.obj` or `.stl` you write
the `boundaries` list yourself, one name per surface in the order the file
holds them, and a row cites those names as it cites a `.fsm`'s. They are a
statement the run trusts rather than verifies: the file carries nothing this
package reads its names from, so a name in the wrong position cites the wrong
surface, and nothing refuses it before the solver runs. `pyfs-matrix
inventory`, which writes a saved simulation's names for you
([below](#the-boundary-inventory-sidecar)), refuses a raw mesh by name, since
it has no mesh block to read the order from.

### The unit

**A RAW MESH STATES ITS UNITS.** The mesh-import family takes the file's
length units as an argument (SRC-003 p.307), and a mesh file carries none. So
the sidecar states the unit the mesh is written in, in an `[import]` table:

```toml
# inputs/geometries/wing.boundaries.toml, beside wing.obj
boundaries = ["Wing"]

[import]
units = "MILLIMETER"
```

`units` is one of the length units `IMPORT` takes on the row's build, read
from the command database: `INCH`, `MILLIMETER`, `FEET`, `MILE`, `METER`,
`KILOMETER`, `MILS`, `MICRON`, `CENTIMETER` or `MICROINCH`. `OTHER`, which
the command also lists, is refused because it names no length. The script
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

Around the length unit come the operations and the trailing-edge marking the
same sidecar declares (below), and the script goes on exactly as it does after
opening a `.fsm`. The file's unit goes to `IMPORT` and nowhere else. The simulation's length unit is always
metres, because every length the reference and the row state is in metres:
the reference area, chord and span, a `TRANSLATE` distance, the frames the
package places. The run record keeps the table as `mesh_import`, because the
geometry's digest alone cannot tell a run in millimetres from the same file
run in metres.

**Whether `IMPORT` converts the body from the file's unit into the
simulation's metres is not measured on any build.** The command database
records the grammar, and no licensed run has yet compared one body imported in
millimetres with the same body in metres. Until one has, a mesh written in
metres (`units = "METER"`) is the one case whose scale does not depend on the
answer.

A unit is never assumed. A raw mesh whose sidecar states no `[import]` table
is refused when the script is built, before any seat is spent, naming the
table, the key, the sidecar and the units the build takes. So is a unit
`IMPORT` does not take, and so is a setup asking to load the solver
initialization, since a new simulation has no stored state to load. An
`[import]` table beside a `.fsm` is refused too, since a saved simulation
carries its own units and nothing would read it.

### The mesh operations of an import

A raw mesh is often not yet the body: a CAD export at another scale, half a
model, surfaces named by the tool that wrote them. The operations that make it
the body are declared with the geometry, in its sidecar, one
`[[import.operations]]` table each, so every row that names the file shares
them:

```toml
boundaries = ["naca", "tail"]

[import]
units = "MILLIMETER"

[[import.operations]]
op = "scale"
factors = [2.0, 2.0, 2.0]

[[import.operations]]
op = "rename"
surface = "naca"
to = "Wing"

[[import.operations]]
op = "mirror"
surface = "Wing"
plane = "XZ"

[[import.operations]]
op = "translate"
surface = "tail"
vector = [500.0, 0.0, 0.0]

[[import.operations]]
op = "rotate"
axis = "Y"
angle_deg = 2.0
```

| `op` | it states | it emits | every surface |
|---|---|---|---|
| `scale` | `factors = [fx, fy, fz]`, each above zero | `SURFACE_SCALE` | `-1` |
| `rename` | `surface` and `to`, a name without spaces | `SURFACE_RENAME` | none: it names one surface |
| `mirror` | `surface` and `plane`: `YZ`, `XZ` or `XY` | `SURFACE_MIRROR` | none: it names one surface |
| `translate` | `vector = [x, y, z]`, in the `[import]` unit | `TRANSLATE_SURFACE_IN_FRAME` | `0` |
| `rotate` | `axis` (`X`, `Y` or `Z`) and `angle_deg` | the build's rotation command | `-1` |

Each acts in the reference frame, the one frame that exists before the setup
creates any. `surface` names the surface acted on by the name the file gives
it, or by the name an earlier rename gave it, exactly as written and never by
position; it is `"all"`, every surface, when left out, and the last column is
the value each command takes for that. A named surface's translation splits
its vertices from its neighbours, as a row's own translation does; every
surface together is moved without the split. The rotation is `SURFACE_ROTATE`
up to 26.121 and `ROTATE_SURFACE` from 26.122, as for a row's `ROTATE`.

**They are applied in the order written, right after the import.** The script
reads:

```text
NEW_SIMULATION
IMPORT ...
SURFACE_SCALE 1 2.0 2.0 2.0 -1
SURFACE_RENAME 1 Wing
SURFACE_MIRROR 1 1 2 TRUE FALSE
SET_SIMULATION_LENGTH_UNITS METER
TRANSLATE_SURFACE_IN_FRAME 1 500.0 0.0 0.0 MILLIMETER 2 ENABLE
<the rotation>
```

Scale, rename and mirror are geometry commands and come before the
simulation's length unit; translate and rotate are setup commands and come
after it. A script's phases only move forward, so an order the phases cannot
emit, a scale written after a translation, is refused naming both operations
by position and kind, and is never reordered: write every scale, rename and
mirror before the first translate or rotate, and restate a translation in the
scaled size if the scale was meant to act on it.

**A mirror joins its source.** It is emitted with the combine flag on and the
delete-source flag off, so the mirrored copy is combined with the surface it
came from and the source is kept, and the inventory the run declares is the
one it had. The command's other three outcomes, which add or replace a
surface, are not offered: the name and position the solver gives that surface
are unmeasured.

**A rename feeds the inventory.** Operations before it cite the file's name,
and operations after it and every row cite the new one: the names the run
declares are the sidecar's `boundaries` as the renames leave them. A name
absent at its step is refused listing the names at that step, and so are a
name two surfaces carry and a rename onto a name another surface carries, each
before anything is emitted. A file whose surfaces share a name cannot cite
them apart; give them distinct names in the mesh file.

**These are the file's, and a row's `TRANSLATE` and `ROTATE` stay the row's.**
The sidecar's operations make the file into the body, once, for every row that
names it, before any frame exists. A row's `TRANSLATE` and `ROTATE` are the
study's own moves of a part, emitted after the frames, and they act on the
body the operations left. The run record keeps the operations in
`mesh_import`, beside the unit.

### The boundary conditions of a raw mesh

**A RAW MESH DECLARES ITS TRAILING EDGE.** A raw mesh carries no trailing
edge, and without one the solver makes no wake and still runs and answers. So
the sidecar declares how the trailing edge is marked, in a `[trailing_edges]`
table, and a raw mesh whose sidecar has none is refused when the script is
built, before any seat is spent. The table takes one of two routes, and the
first is the default.

**The file route, the default.** `file` names a points file beside the
sidecar ([its format below](#the-points-file)):

```toml
# inputs/geometries/wing.boundaries.toml, beside wing.stl
boundaries = ["Wing"]

[import]
units = "METER"

[trailing_edges]
file = "wing.te.txt"   # the points file, beside the sidecar
type = "STANDARD"      # optional: STANDARD (the default), RELAXED, JET_OUTFLOW, VORTEX_SHEDDING
tolerance = 0.0001     # optional: in the simulation's metres
```

The points are checked against the mesh when the row is bound, converted to
metres, the simulation's unit, and marked right after the import and its
operations:

```text
IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER
<the point's staged folder>/wing.wake_nodes.txt
```

The points name edges of the mesh as the FILE holds it, so the route is
refused beside an `[[import.operations]]` that scales, mirrors, translates or
rotates the body; a rename is accepted. `type` is STANDARD unless written, the
type the solver's detection gives the edges it marks, so one mesh marked by
file and by detection carries one type.

**Detection, the second route, applies only when written.** It is never a
default:

```toml
[trailing_edges]
detect = { surfaces = ["Wing"], sweep_angle = 60 }   # or detect = "auto", every surface
```

`detect = "auto"` emits `AUTO_DETECT_TRAILING_EDGES`. A table of `surfaces`
emits `DETECT_TRAILING_EDGES_BY_SURFACE` on them, cited by the sidecar's names
as the renames left them, exactly and never by position (`surfaces = "all"`
is every surface), and `sweep_angle`, in degrees, emits
`SET_TRAILING_EDGE_SWEEP_ANGLE` before it. Detection marks an edge where the
surface creases, so the angle decides what a twisted blade gets (measured
below). It gives every edge the STANDARD type and matches no points, so `type`
and `tolerance` beside `detect` are refused. A table stating both `file` and
`detect`, or neither, is refused, and so is a key it does not read.

**Two options, each only when written.**

```toml
[wake_termination]
detect = { surfaces = ["Wing"] }   # or detect = "auto", every surface

[base_regions]
detect = "auto"
```

`[wake_termination]` emits `AUTO_DETECT_WAKE_TERMINATION_NODES`, or one
`DETECT_WAKE_TERMINATION_NODES_BY_SURFACE` per surface named.
`[base_regions]` emits `AUTO_DETECT_BASE_REGIONS`. It is refused beside a
row's `BASE_REGIONS` or a pproc's `base_regions`, which would mark the base a
second time.

**A saved simulation declares none of the three.** A `.fsm` carries the
trailing edges, wake-termination nodes and base regions it was saved with, so
a sidecar beside one stating any of these tables is refused: a second marking
pass would mark them twice. A row marks base regions on a saved simulation
with its `BASE_REGIONS` key.

### The points file

The wake-edge import matches a mesh edge by its MID-POINT: an edge is marked
when a point in the file lies within the import's tolerance of the edge's
mid-point, and a point farther than that from every mid-point marks nothing
and reports nothing. So a points file names edges by their mid-points, never
by their end vertices. Its first line names the length unit of its points (a
token of `SET_SIMULATION_LENGTH_UNITS`, `OTHER` excepted), and every later
line is one `x,y,z` mid-point:

```text
METER
0.216872113,-0.002159825,0.223199974
0.250942335,-0.004761036,0.219139256
```

The points file is the package's, not the solver's: its unit is stated once,
on the first line, since a mesh file does not carry one, and the run converts
its points to the simulation's length unit and writes the file the solver
imports.

**It is checked before any seat is spent.** When the row is bound, the file is
read and every point is checked against the mesh (`read_trailing_edge_points`
and `matched_trailing_edge_points`, in `pyflightstream.workspace.wake_edges`),
compared in the simulation's length unit. The first point farther than
`tolerance` from every mesh-edge mid-point is refused by its position, its
file line, its coordinates and its distance, and two points nearest one edge
are refused as well, since the solver would mark that edge once. A file of the
edges' end vertices fails this check at its first point. The checked points
come back in metres.

**The run writes the solver's node file and holds the solver to it.** The run
writes the node file beside the point's staged geometry before the solver
starts and records its digest among the run's inputs. A point that matches no
edge marks nothing and the solver says nothing about it, so after the run the
package compares the number of edges the solver logs as imported with the
points it wrote, and records the point `FAILED_SCRIPT` when they differ. That
number is read from the solver log, so the log has to be among the row's
outputs: a file-route row declares one, a name ending in `_log.txt`, which a
run type's default outputs carry, and a row that declares none is refused when
its script is built, and a row that states `EXPORT_LOG: false`, which leaves
the script exporting no log, is refused at plan. A machine whose HPC profile
turns the export off itself (`export_log = false` beside a `native_log`) runs
the row: `collect` copies the log its scheduler writes to the declared name,
and the count is read from it there. Run there with `--local`, where no
scheduler writes a log, the count is read from what the solver printed, and a
point whose solver printed nothing is recorded `FAILED_INCOMPLETE_OUTPUT`
naming the machine. A recipe of your own that imports a file
and exports no log is recorded `FAILED_INCOMPLETE_OUTPUT`. The count is read
from the collected log the assessor names; an assessor of your own that names
none, locally or at `collect`, has it read from the one collected output that
parses as a residual history, the log the package's own assessor would find.

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

An OBJ file's named groups would have been the preferred route and were
measured and dropped: the mesh library this package reads through does not
surface OBJ group names, so a blade exported with its trailing edge already
named as a group offers nothing the reader can see.

### Which build runs what, and what is measured

| What | Where it stands | Evidence |
|---|---|---|
| The file route: the import line, the node file, a file of mid-points | Runs on FlightStream 26.124, the one build it was run on. 26.122 and 26.123 document a form 26.124 refuses, and are refused naming the report; a build that does not carry the command is refused too. | RPT-061 |
| What the file marks | Exactly the edges it names, since initialisation adds none. | RPT-065 |
| What detection marks | An edge where the surface creases, so the angle decides: on 26.124 a blade detected with the default angle marked 12 edges, and with 10 degrees 3 of them. | RPT-065 |
| `[base_regions]` | On 26.124 it marked the flat base of a body, the same faces the by-surface form marks when given the base boundary. | RPT-066 |
| `[wake_termination]` | **What it marks is not verified**: on the one geometry tried on 26.124, neither command changed the saved state or printed a line, so a geometry that needs termination nodes is still owed before the option can be called measured. | RPT-066 |
| The mesh operations | Not measured after an import: the grammar is the manual's, and the vertex split is carried over from the row's translation, where it was measured. | RPT-048 |
| `IMPORT`'s unit | Whether it converts the body from the file's unit into metres is not measured on any build (above). On the file route, a body that does not come out in metres leaves the node file's points off its edges, and the count check records the point `FAILED_SCRIPT`. | none yet |
| The surface names | Trusted, not verified: the file carries nothing this package reads them from. | none |

## A complete example: a wing OBJ with its trailing edge by file

A rectangular NACA 0012 wing of chord 1 m and span 4 m, exported in
millimetres with its one surface named `wing_skin`, as a CAD tool might write
it, run at two angles of attack on FlightStream 26.124 with its trailing edge
marked by a points file. Every path below is relative to the root of a
workspace made by `pyfs-workspace init`.

**The mesh.** Your own export goes to `inputs/geometries/wing.obj`. To follow
along without one, this writes a stand-in with the package's synthetic wing,
eight panels across the span; run it from the workspace root:

<!-- skip: next -->
```python
import numpy as np

from pyflightstream.qa.geometry import WingSpec, wing_triangles

spec = WingSpec(naca="0012", chord_m=1.0, span_m=4.0, n_chord=12, n_span=8)
corners = wing_triangles(spec).reshape(-1, 3) * 1000.0  # metres to millimetres
vertices, faces = np.unique(corners.round(6), axis=0, return_inverse=True)
with open("inputs/geometries/wing.obj", "w", encoding="utf-8") as obj:
    obj.write("o wing_skin\n")
    obj.writelines(f"v {x:.4f} {y:.4f} {z:.4f}\n" for x, y, z in vertices)
    obj.writelines(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in faces.reshape(-1, 3))
```

**The sidecar** names the surface as the file holds it, states the unit,
renames the surface to the name the study cites, and marks the trailing edge
by file. The rename is emitted by position, so after it the surface is `Wing`
whatever name the solver took from the file:

```toml title="inputs/geometries/wing.boundaries.toml"
boundaries = ["wing_skin"]

[import]
units = "MILLIMETER"

[[import.operations]]
op = "rename"
surface = "wing_skin"
to = "Wing"

[trailing_edges]
file = "wing.te.txt"
```

**The points file.** The trailing edge is the line x = 1000 mm, z = 0, and
its eight mesh edges have their mid-points every 500 mm of span:

```text title="inputs/geometries/wing.te.txt"
MILLIMETER
1000,-1750,0
1000,-1250,0
1000,-750,0
1000,-250,0
1000,250,0
1000,750,0
1000,1250,0
1000,1750,0
```

**The reference, the setup and the post-processing artifact** the row cites,
the smallest that serve this wing:

```toml title="inputs/references/r001.toml"
area_m2 = 4.0      # SREF, chord x span
chord_m = 1.0      # CREF
span_m = 4.0       # BREF

[moment_point]
x_m = 0.25         # the quarter chord, in metres like every length here
y_m = 0.0
z_m = 0.0
```

```toml title="inputs/setups/s001.toml"
NITER = 300        # SOLVER_SET_ITERATIONS
```

```toml title="inputs/pproc/p001.toml"
[groups]
"1" = "Wing"       # the name the rename gave the surface
```

**The row** names the mesh, sweeps two angles and runs on 26.124, the build
the file route was run on:

```text title="wing.fs"
POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION                    | FLIGHT_CONDITION                | SWEEP_VALUES | GEOMETRY | REF  | SET  | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
1001 |    0   |  1  | Wing     | -             | OBJ_wing_trailing_edge_by_file | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0,4.0      | wing.obj | r001 | s001 | p001  | NONE     | -              | -     | -        | 26.124   | steady   |
```

With `inputs/executables.toml` naming your 26.124 installation, as for any
row ([workspaces and workflows](workspace-and-workflows.md)), plan it and run
it from the workspace root:

```text
pyfs-matrix plan wing.fs
pyfs-matrix run wing.fs
```

The plan spends no seat. It binds the row, reads the points file and checks
every point against the mesh, and builds each point's script; a point that
misses the mesh, a missing unit or a missing log among the outputs stops it
here. The script it builds for each point starts:

```text
NEW_SIMULATION
IMPORT
UNITS MILLIMETER
FILE_TYPE OBJ
FILE <the point's staged copy of wing.obj>
CLEAR

SURFACE_RENAME 1 Wing
SET_SIMULATION_LENGTH_UNITS METER
IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER
<the point's staged folder>/wing.wake_nodes.txt
```

and the node file the run writes beside the staged mesh holds the count, the
coordinate line the solver consumes, and the eight points in metres:

```text
8
0,0,0
1.0,-1.75,0.0
1.0,-1.25,0.0
1.0,-0.75,0.0
1.0,-0.25,0.0
1.0,0.25,0.0
1.0,0.75,0.0
1.0,1.25,0.0
1.0,1.75,0.0
```

**Read the unit once more before copying this.** The mesh is in millimetres,
as a CAD export usually is, which puts the example on the one question above
that no build has answered: whether `IMPORT` converts the body into metres. If
it does not, the body the solver holds is not the one the node file describes,
none of this example's points lies on it, and the count check records each
point `FAILED_SCRIPT` rather than letting a solve of the wrong body pass.
Written in metres, the mesh and the points file both, the example does not
depend on the answer.

The suite runs this example as printed: `tests/tier1_offline/test_mesh_inputs_page.py`
writes every titled block above into a temporary workspace, runs the python
block there, plans the matrix with the command above, and renders both points
without a solver. It fails when the scripts the package builds and the two
blocks above differ, and when a key a sidecar block on this page writes is not
one the sidecar's readers read, or the other way round. A runnable script of
the same route is `examples/obj_wing_trailing_edge_file.py`.

## The saved simulation: GUI once, script everything after

### The gap this route closes

The FlightStream scripting interface covers a subset of what the GUI can do.
The command database only ever contains commands the manual documents, or that
a committed probe report measured the solver accepting (each entry carries one
citation or the other), so a workflow step with no script command cannot be
emitted by the script builder, and no amount of library code changes that.
Geometry preparation and meshing are the common case, and the picture there
changed on 2026-08-06 through 2026-08-08, when the sweep finished: every
command the eight editions registered at that date documented entered the
database, so the CAD, CAD Create and Mesh Operations chapters are emittable in
full, and the last of those is this page's own subject, everything that
translates, rotates, scales, mirrors, copies, cuts, selects or deletes a
surface between import and solver initialization. The mesh-wrapper chapter is
in too, as of 2026-08-08. Since 0.27.0 five of those commands, scale, rename,
mirror, translate and rotate, are also declared with a raw mesh's geometry and
applied by a workflow row ([above](#the-mesh-operations-of-an-import)).

**Read the scope of that claim.** It is a statement about the eight editions
swept in August 2026, not a standing promise about every edition the vendor
publishes. SRS non-requirement NREQ-05 excludes no command family by
decision, and an edition registered after the sweep may document a command
the database does not yet carry, which is a dated debt in the SRS evidence
queue rather than an exclusion. The first was `SET_OUTLET_TRAILING_EDGES`,
which the 26.123 edition (SRC-751) documented when it was registered on
2026-08-17 and which the database carries since 0.8.0; it belongs to the
boundary conditions rather than to meshing. What has NOT changed is the reason
this route exists. A command being in the database means the script builder
will emit and validate it; it does not mean the GUI-driven parts of geometry
preparation have a scripted equivalent, and the pattern below is still the
supported one.

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
`.fsm` is its record. The workspace stages inputs with content hashes in the
run manifest (`inputs_sha256`), so every run names exactly which saved file it
consumed. This policy dates from 2026-07-23.

When a mesh exists only inside a `.fsm`, the pre-processing export
(`run.export_surface_mesh`) produces the OBJ counterpart through a solver run,
which is how the geometry gate of the probe planner gets its watertight
surface.

### What that content hash is, and what it leaves out

Stated here because this page is where a user is told to trust it, and a
checksum whose rule is unstated cannot settle the question it exists for: two
people holding what they believe is the same input file must be able to tell
whether they really do.

**The algorithm is sha256, and there is no other.** Every digest this library
writes into a manifest comes from `pyflightstream._digest`, which holds the
algorithm as a value rather than as a sentence, so a tier 1 test spends it and
a second algorithm cannot arrive quietly.

**The canonical form is the raw bytes of the staged file**, read in blocks and
never decoded. One manifest field is not a file digest and is named here so
the rule is not over-read: `recipe_sha256` records the recipe function's
SOURCE, and a source text is hashed as its UTF-8 encoding, which is the second
canonical form `pyflightstream._digest` states.

**Nothing around the file enters the digest.** Not the path it was staged
from, not the file name, not its modification time, not the machine or the
user that staged it, and not the order the inputs were staged in. Those are
exactly the fields that differ between two runs which are otherwise the same
run, so admitting one would make the manifest report two identical runs as
different. They are absent by construction rather than by filtering: the
digest reads bytes and reads nothing else.

Read the consequence for a text mesh, because it is the one that surprises. An
OBJ is bytes like anything else, so the same mesh checked out with CRLF line
endings on one machine and LF on another is two different files carrying two
different digests. That is the digest being correct about the file rather than
wrong about the content: the solver reads the file, not an idea of it. A
`.fsm` artifact is binary and has no such ambiguity, which is a further reason
the pattern above treats it as immutable. Where a comparison has to survive a
line-ending change, compare the parsed geometry rather than the manifest
digest.

### The boundary inventory sidecar

A saved simulation carries its boundary names in the solver's own order, and a
workflow row cites boundaries by those names (`MOVING_BOUNDARIES:
Blade1,Blade2`). The order is a property of the file, so it is never stated
by hand: since v0.11.0 a setup artifact that carries `mesh_order_list` is
refused (PFS-2029.06.01), and the order is written from the file itself:

```text
pyfs-matrix inventory inputs/geometries/30_WB.fsm
```

writes `inputs/geometries/30_WB.boundaries.toml`, a `boundaries` list in the
file's order, and refuses to overwrite one that exists without `--overwrite`.
The sidecar sits beside the file, so a geometry kept in its own folder,
`inputs/geometries/30_WB/30_WB.fsm` (PFS-2032.04, the layout `pyfs-workspace
migrate-geometries` produces), has it inside that folder, and the run reads it
from there. `pyfs-matrix inventory` refuses a file without a mesh block (a raw
mesh, or a file the solver never saved) by name, because it has no block to
read the order from.

A row whose `.fsm` has a sidecar is checked when the script opens the file: a
sidecar that disagrees with the file's own block is refused before any seat is
spent, naming both lists, and an agreeing one is recorded in the run record as
the inventory source (`inventory_source: sidecar`; `mesh_block` when the file
alone declared the names). Since 0.27.0 the record also carries the names
themselves, `inventory`, in the file's order; the post reads a section
distribution's selection over them. The sidecar is what lets a name resolve
for a file whose mesh block a reader cannot open, and it is otherwise a
statement the run verifies rather than trusts.

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
