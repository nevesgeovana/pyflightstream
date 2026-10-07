# Mesh input reference

### The surface names

A row cites a raw mesh's names as it cites a `.fsm`'s. Where they come from
depends on the format.

**An OBJ's names are read from its groups.** The solver imports an `.obj` as
one surface per `o` or `g` group that holds a face, named by the group and
numbered in the order the groups appear in the file; a group holding no face
makes no surface and takes no position (measured on 26.124, RPT-078). So when
an `.obj` has no sidecar, the plan writes one beside it and says so on stderr:
`pyfs-matrix plan`, `pyfs-matrix run` and `pyfs-matrix inventory wing.obj`
reach it the same way. It holds the list and nothing else:

```toml
# inputs/geometries/wing.boundaries.toml, as the plan writes it beside wing.obj
# Written by pyflightstream from the groups of wing.obj, which had no sidecar;
# the OBJ's sha256 was <the sha256 of wing.obj>.
# One boundary per `o` or `g` group holding a face, named by the group, in the
# order of the file: how the solver numbers an OBJ's surfaces on import
# (RPT-078). The package never rewrites this file. Add the [import] table with
# the file's units, and the [trailing_edges] table, beneath the list
# (docs/mesh-inputs.md).
boundaries = [
    "Wing",
    "Tail",
]
```

Add the `[import]` table and the `[trailing_edges]` table beneath the list
(the sections below): only you can state the unit the file is written in and
how its trailing edge is marked, so the plan that wrote the list then blocks
the row on the missing unit, naming the table.

**The sidecar is never rewritten.** Once one stands beside the `.obj`, written
by the plan or by you, the package leaves it as it is, and `pyfs-matrix
inventory` refuses it, `--overwrite` or not, since it carries your tables. At
each plan its list is compared with the file's groups: when they differ, in a
name or in the order, the run cites the sidecar's list as written and a
warning names both lists. Correct the list, or move the file aside, plan
again, and copy your tables beneath the list the plan writes.

**What the measurement did not settle is refused, by line, and keeps the list
by hand.** A file that opens groups with both `o` and `g`, a group name opened
in two places of the file, a face written before the first group, and a group
statement naming no group or a name of several words are refused when the
plan would write the sidecar, naming the line. Write the `boundaries` of such
a file by hand, in the order the solver numbers its surfaces; a sidecar beside
it is read as it stands.

**An STL's names are written by hand.** An `.stl` names no group this package
reads, so you write the `boundaries` list yourself, one name per surface in
the order the file holds them. They are a statement the run trusts rather
than verifies: a name in the wrong position cites the wrong surface, and
nothing refuses it before the solver runs. `pyfs-matrix inventory`, which
writes a saved simulation's names for you
([below](#the-boundary-inventory-sidecar)), refuses an `.stl` by name, since it
has no mesh block to read the order from.

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

**`IMPORT` converts the body from the file's unit into the simulation's
metres, measured on 26.124**: a wing OBJ written in millimetres, its trailing
edge detected, solved as the same wing written in metres to the print (RPT-069,
the licensed probe T07 of 0.27.0). The file route in millimetres and every
other build are not measured, so a mesh written in metres (`units = "METER"`)
is still the one case whose scale depends on nothing.

A unit is never assumed. A raw mesh whose sidecar states no `[import]` table
is refused when the script is built, before any seat is spent, naming the
table, the key, the sidecar and the units the build takes. So is a unit
`IMPORT` does not take, and so is a setup asking to load the solver
initialization, since a new simulation has no stored state to load. An
`[import]` table beside a `.fsm` is refused too, since a saved simulation
carries its own units and nothing would read it.

### Explicit CAD conversion is a separate route

For an IGES file (`.igs` or `.iges`), the sidecar explicitly selects CAD
conversion. This compact form uses the existing CAD defaults:

```toml
boundaries = ["Wing"]

[import]
units = "FILE"
cad = {}

[trailing_edges]
detect = "auto"
```

`cad = {}` selects MEDIUM tessellation, unreferenced patches, 80 curvature
subdivisions and all CAD bodies. The inventory must match the inspected
converted mesh. `units = "FILE"` uses the source CAD metadata; it is not a
raw-mesh unit or a scale correction. STEP remains refused. See
[CAD geometry inputs](../cad-inputs.md) for the supported IGES route, explicit
options, unit observations and mesh-quality limitations. OBJ/STL inputs do not
accept CAD options.

### A CCS file is another route

A CCS file (the solver's cross-section format) is routed by a third table of
the same `[import]`, `[import.ccs]`, which chooses what the solver builds from
it. The table's keys, what each kind of geometry reads and what is refused are
on [CCS geometry](../ccs-geometry.md); this page holds only its place in the
sidecar.

```toml
boundaries = ["WING"]

[import]
units = "FILE"

[import.ccs]
kind = "file"
```

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
built, before any seat is spent. The table takes one of two marking routes,
or an explicit declaration that this geometry has no trailing edges.

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
<the folder the point runs in>/wing.wake_nodes.txt
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
and `tolerance` beside `detect` are refused. Without `none = true`, a table
stating both `file` and `detect`, or neither, is refused, and so is a key it
does not read.

**A geometry without trailing edges states that explicitly.** For a body
that should not shed a trailing-edge wake, the declaration is:

```toml
[trailing_edges]
none = true
```

`none = true` must be the only key in this table. It records an intentional
absence of trailing edges; it is not automatic detection and does not make
omission of the table equivalent to this declaration.

**Two options, each only when written.**

```toml
[wake_termination]
detect = { surfaces = ["Wing"] }   # or detect = "auto", every surface

[base_regions]
detect = "auto"
```

`[wake_termination]` emits `AUTO_DETECT_WAKE_TERMINATION_NODES`, or one
`DETECT_WAKE_TERMINATION_NODES_BY_SURFACE` per surface named. On the
detection route it follows the detected edges, before the solver is
initialized.

**On the file route the wake termination waits for the solver.** Right after
the edges are imported from a file, the detection finds no termination node,
and the solver uses a node it marks only when it initializes. So the script
initializes the solver, detects, and initializes it again with the same
settings; the second initialization replaces the first, and the solver then
runs once, with the node:

```text
INITIALIZE_SOLVER
SOLVER_MODEL INCOMPRESSIBLE
SURFACES -1
WAKE_TERMINATION_X DEFAULT
SYMMETRY NONE

AUTO_DETECT_WAKE_TERMINATION_NODES
INITIALIZE_SOLVER
SOLVER_MODEL INCOMPRESSIBLE
SURFACES -1
WAKE_TERMINATION_X DEFAULT
SYMMETRY NONE

...
START_SOLVER
```

Without that order a twisted blade lost the termination node at its root and
solved 1.8 % low in induced drag; with it, the file route equals the detection
route and the saved simulation. Every run type takes this order, a steady row
of several points included, since its points all begin after the second
initialization. A file route without `[wake_termination]` initializes once, as
before.

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
writes the node file in the folder the point runs in,
`sims/sim_<id>/datapoints/DP-<point>/`, or the simulation folder for a steady
row of several points, which runs as one job, before the solver starts, and
records its digest among the run's inputs. Nothing is written into
`inputs/geometries/`: every simulation on one mesh reads that folder, so two
runs on the mesh never share a node file, and a points file named
`<stem>.wake_nodes.txt` is left as written. A point that matches no
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

### Which build runs what, and what is measured

| What | Where it stands | Evidence |
|---|---|---|
| The file route: the import line, the node file, a file of mid-points | Runs on FlightStream 26.124, the one build it was run on. 26.122 and 26.123 document a form 26.124 refuses, and are refused naming the report; a build that does not carry the command is refused too. | RPT-061 |
| What the file marks | Exactly the edges it names, since initialisation adds none. | RPT-065 |
| What detection marks | An edge where the surface creases, so the angle decides: on 26.124 a blade detected with the default angle marked 12 edges, and with 10 degrees 3 of them. | RPT-065 |
| `[base_regions]` | On 26.124 it marked the flat base of a body, the same faces the by-surface form marks when given the base boundary. | RPT-066 |
| `[wake_termination]` | On 26.124 the automatic form marked the root end of a twisted blade, on the detection route and on the file route between two initializations; right after a file import neither form marked anything. On the steady point measured, that order made the file route equal the other routes; an unsteady run takes the same order and is not measured. On the geometry tried before, neither command changed the saved state. | RPT-069, RPT-066 |
| The mesh operations | Not measured after an import: the grammar is the manual's, and the vertex split is carried over from the row's translation, where it was measured. | RPT-048 |
| `IMPORT`'s unit | Converts on 26.124: a wing OBJ in millimetres, trailing edge detected, equalled the one in metres to the print (above). The file route in millimetres and other builds are not measured; on the file route, a body that does not come out in metres leaves the node file's points off its edges, and the count check records the point `FAILED_SCRIPT`. | RPT-069 |
| The surface names | An OBJ's are read from its groups in file order, the order `IMPORT` numbers them in (G30); an STL's, which names no group, are trusted, not verified. | RPT-078 |

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
the [supported pattern](how-to.md#the-supported-pattern) treats it as immutable. Where a comparison has to survive a
line-ending change, compare the parsed geometry rather than the manifest
digest.

### The boundary inventory sidecar

A saved simulation carries its boundary names in the solver's own order, and a
workflow row cites boundaries by those names (`MOVING_BOUNDARIES:
Blade1,Blade2`). The order is a property of the file, so it is never stated
by hand: a setup artifact that carries `mesh_order_list` is
refused (PFS-2029.06.01), and the order is written from the file itself:

```text
pyfs-matrix inventory inputs/geometries/30_WB.fsm
```

writes `inputs/geometries/30_WB.boundaries.toml`, a `boundaries` list in the
file's order, and refuses to overwrite one that exists without `--overwrite`.
The sidecar sits beside the file, so a geometry kept in its own folder,
`inputs/geometries/30_WB/30_WB.fsm` (PFS-2032.04, the layout `pyfs-workspace
migrate-geometries` produces), has it inside that folder, and the run reads it
from there. `pyfs-matrix inventory` reads an `.obj`'s order from its groups
instead ([above](#the-surface-names)), and refuses any other file without a
mesh block (an `.stl`, or a file the solver never saved) by name, because it
has no block to read the order from.

A row whose `.fsm` has a sidecar is checked when the script opens the file: a
sidecar that disagrees with the file's own block is refused before any seat is
spent, naming both lists, and an agreeing one is recorded in the run record as
the inventory source (`inventory_source: sidecar`; `mesh_block` when the file
alone declared the names). The record also carries the names
themselves, `inventory`, in the file's order; the post reads a section
distribution's selection over them. The sidecar is what lets a name resolve
for a file whose mesh block a reader cannot open, and it is otherwise a
statement the run verifies rather than trusts.

<a id="actions-saved-in-the-geometry-since-0330"></a>

### Actions saved in the geometry

A saved simulation keeps the unsteady solver actions it was saved with. When
the script creates an action with the name of a saved one, the saved one
stays and the solver runs ITS command, so a geometry saved on a workstation
after an unsteady run carries that workstation's walltime clock, interpreter
path included, and every unsteady run of it on a cluster aborts when the
clock fires. `pyfs-matrix inventory` names each saved action, on every call,
with the command that removes them:

```text
pyfs-matrix inventory inputs/geometries/30_WB/30_WB.fsm --clean
```

`--clean` reduces the file to its meshes and the boundary conditions
already applied (FR-308, FR-312). It sets the action count to 0 and removes
the action records, and it puts every other block back to the content a
freshly imported file holds, where that content is measured for the file's
build and length unit; everything else comes from the script. The blocks and
their fresh-import content were measured on the ten tier-3 geometries, fresh
imports saved by 26.120 (build 7012026) in metres, which hold the same
`GLOBAL`, `MOTION`, `POST`, `WAKE`, `SOLVER`, `ACOUSTIC`, `STABILITY` and
`AEROELASTIC` whatever the shape: those are the blocks reset, and each one
reset is named on standard error. Anything set by hand in them is discarded,
the reference point and frame of `GLOBAL` and the solver and wake settings of
`SOLVER` and `WAKE` included, since the script sets them again; the ten
geometries were all made by one preparation recipe, so the content is the one
common to those saves. Never reset:
`MESH` (the meshes, the boundaries, the trailing edges and the wake
termination marks), `PHYSICS` (the surface lists the boundary conditions are
set in), `WRAPPER` and `GRAPHICS` (which differ between fresh imports), and
`CAD`, `CADCREATE` and `CADMESHING` (measured on STL imports only). A file of
another build or unit, 26.124 included, has no measured fresh import: only its
saved actions are removed, every other block is kept, and the command says
so. That the solver opens and runs a cleaned file is owed by the licensed
round of 0.33.0.

The file as it was is copied to `30_WB.fsm.bak-<stamp>` beside it first, and
it is read again after the change: its boundary names and every block kept
must be as before and its action records must read as none, or the copy is
put back and the call refused. A file whose build is measured but which lacks
one of the blocks to reset is refused before anything is written, and a file
already clean is not written. An existing sidecar is kept, since the
boundaries it lists did not change, unless `--overwrite` is given too. To
clean every geometry of a workspace kept one per folder:

```text
for d in inputs/geometries/*/; do n=$(basename "$d"); f="$d$n.fsm"; [ -f "$f" ] && pyfs-matrix inventory "$f" --clean; done
```

**The plan warns too (FR-313).** `pyfs-matrix plan` reads the geometry of
every row whose run type is `unsteady` or `unsteady_rotor`, a continuation
included, with the same reader, and for each file carrying saved actions
prints a warning naming the rows that open it, the file, each action (name,
type, command) and the `--clean` command; a file whose action records cannot
be read is named as unreadable. The plan never refuses on that account: its
rows, its files and its exit status are those of the same plan without the
warnings.

## The refinement file and the audit

This section is the reference of `pyfs-matrix refine` and `pyfs-matrix
audit-mesh` (FR-424 to FR-428); the walk-through is
[Refining or coarsening a mesh](how-to.md#refining-or-coarsening-a-mesh).

### The two commands

```text
pyfs-matrix refine MESH [FACTOR] [--families A,B] [--chordwise F] [--spanwise F]
                   [--config FILE] [--out-dir DIR] [--overwrite]
pyfs-matrix audit-mesh OBJ [--against SOURCE] [--csv FILE]
```

| argument | of | meaning |
|---|---|---|
| `MESH` | `refine` | the source OBJ; it and its folder are never modified |
| `FACTOR` | `refine` | the factor of every selected family, a finite number above zero |
| `--families A,B` | `refine` | the families to change, comma separated (default: every family) |
| `--chordwise F`, `--spanwise F` | `refine` | the factor of one index direction of every selected grid family; refused for a remeshed family |
| `--config FILE` | `refine` | the refinement file (default: `<stem>.refine.toml` beside the mesh) |
| `--out-dir DIR` | `refine` | where the level folder goes (default: the parent of the folder holding the source) |
| `--overwrite` | `refine` | replace an existing level folder |
| `OBJ` | `audit-mesh` | the OBJ to audit |
| `--against SOURCE` | `audit-mesh` | the OBJ it was made from; without it only G1, G2 and G4 are judged |
| `--csv FILE` | `audit-mesh` | also write the figures as CSV, one row per family and figure |

`refine` exits 0 when the level is written, whatever the audit says, and 2 when
the request is refused. `audit-mesh` exits 0 when every gate and check passes,
1 when one fails (the audit is still written) and 2 when its input is refused.
A refusal is printed on standard error, names the object, what was refused and
what to do, and ends with `Nothing was written.`: every refusal of the
arguments, the refinement file, the family names and the installed extras comes
before any family is resampled and before any file is written, and so does a
refusal of the boundaries file or of the points file it names, which the audit
reads. A level is written into `<folder>.partial`, audited there, and renamed
once complete, so an error leaves no level folder behind; with `--overwrite`
the existing level is replaced only then, and kept when an error comes first.

### Where the factors come from

1. FACTOR applies to every family `--families` selects (default: every family).
   `--chordwise` and `--spanwise` replace it in that index direction of each
   selected grid family; given alone, the factor of the other direction is 1.
2. When the command gives none of FACTOR, `--chordwise` and `--spanwise`, the
   factors are the `[families.<name>]` tables of the refinement file:
   `--config FILE`, or else `<stem>.refine.toml` beside the mesh. A family the
   file does not name is not changed. `--families` then selects among the
   file's tables: an unselected family is not changed, and a selected name the
   mesh does not hold is refused, as on the FACTOR route.
3. With no factor on the command and no file, a file that states no family,
   or a selection the file states no factor for, the command is refused.
4. A `[families.<name>]` table whose factors are not read (every one when the
   command gives the factors, an unselected one under `--families`) is a
   warning naming it, and `refine.json` lists it under
   `ignored_families_tables`; an `elements` key in it still applies.

The `[refine]`, `[components]` and `[periodic]` tables of the refinement file
are read whenever the file exists, whatever gives the factors.

### The keys of the refinement file

The block below names every key at once; a real file holds the tables its
own mesh needs, and every family it names must be a family of that mesh.

```toml title="every-key.refine.toml"
[refine]
tag = "fine"
elements = "triangles"

[families.Wing]
factor = 2
chordwise = 1.5
spanwise = 2
method = "grid"

[families.Tip]
factor = 2
method = "remesh"
elements = "quad-dominant"

[families.Spinner]
axial = 2
circumferential = 1
axis = [1.0, 0.0, 0.0]
origin = [0.0, 0.0, 0.0]

[components]
Blade1 = ["Blade1_side", "Blade1_tip"]

[periodic]
axis = [1.0, 0.0, 0.0]
origin = [0.0, 0.0, 0.0]
copies = 6
```

| table | key | value | meaning |
|---|---|---|---|
| `[refine]` | `tag` | text | the level's name, `<stem>_<tag>`, in place of the factors |
| `[refine]` | `elements` | `"triangles"` (default) or `"quad-dominant"` | the elements of every remeshed family that does not state its own |
| `[families.<name>]` | `elements` | `"triangles"` or `"quad-dominant"` | the elements of a remeshed family: quad-dominant pairs the remeshed triangles into convex quadrilaterals (angles 30 to 150 degrees, warp at most 10 degrees), never across an open boundary, the trailing edge or a ridge; refused with `method = "grid"`, ignored (and said so in `refine.json`) on a family that `"auto"` resolves to a grid |
| `[families.<name>]` | `factor` | number above zero | multiplies the intervals of each index direction of a grid; divides the target edge length of a remeshed family |
| `[families.<name>]` | `chordwise`, `spanwise` | number above zero | the factor of one index direction of a grid, replacing `factor` there |
| `[families.<name>]` | `method` | `"auto"` (default), `"grid"` or `"remesh"` | `"auto"` takes the grid when it is recovered and remeshes otherwise; `"grid"` refuses a family whose grid is not recovered, naming why; `"remesh"` remeshes it |
| `[families.<name>]` of a body | `axial`, `circumferential` | number above zero | the target edge length divided by `axial` along the axis and by `circumferential` around it; the family is remeshed |
| `[families.<name>]` of a body | `axis` | three numbers, not all zero | the body's axis; required with `axial` or `circumferential` |
| `[families.<name>]` of a body | `origin` | three numbers | a point of the axis (default: the family's centroid) |
| `[components]` | `NAME = [...]` | a non-empty list of family names | the members written as one family `NAME` of the output, their faces in the source's family order |
| `[periodic]` | `axis` | three numbers, not all zero | the axis of the rotor the sector belongs to |
| `[periodic]` | `origin` | three numbers, in the OBJ's coordinates | a point of that axis |
| `[periodic]` | `copies` | an integer of at least 2 | the sectors in a full turn; one cut face maps onto the other by `360/copies` degrees |

Each of these is refused naming the file, the table and the key, and listing
the known keys: a table or key the list above does not hold, a family the mesh
does not hold, a family table with neither `factor` nor `chordwise` nor
`spanwise` (nor `axial` nor `circumferential`), `chordwise` or `spanwise` on a
family whose method is `"remesh"`, `axial` or `circumferential` without `axis`,
beside `factor`, `chordwise` or `spanwise`, or with `method = "grid"`, and a
malformed `axis` or `origin`. In `[components]`, a member the mesh does not
hold, a family listed in two components, and a component named after a family
that is not one of its members are refused naming the component and the
family. A `[periodic]` table whose key is missing or malformed, or that finds
no pair of cut faces, is refused naming the key.

### The tag of a level

The tag is `[refine] tag` when the file states one. Otherwise it is built from
the factors, `p` standing for the decimal point:

| refinement | tag |
|---|---|
| factor 2 on every family | `R2` |
| factor 0.5 on every family | `R0p5` |
| chordwise 1.5 and spanwise 0.7 on every family | `R1c1p5s0p7` |
| axial 2 and circumferential 1 on every family | `Ra2t1` |
| factor 2 on `Wing` only | `R-Wing2` |
| `Wing` at 2 and `Tip` at 1.5 | `R-Wing2-Tip1p5` |

### The files of a level

The level folder is `<out-dir>/<stem>_<tag>/`, and every file in it is written
through the package's one text route, without a carriage return.

| file | written when | content |
|---|---|---|
| `<stem>_<tag>.obj` | always | the level, its families in the source's order (a component in place of its members) |
| `<stem>_<tag>.te.txt` | the source has a trailing-edge points file | one mid-point per trailing-edge edge of the new mesh, under the source file's unit line |
| `<stem>_<tag>.boundaries.toml` | the source has a sidecar | the source's sidecar, naming the new points file and each component in place of its members |
| `<stem>_<tag>.refine.json` | always | what was done to each family |
| `<stem>_<tag>.audit.json` | always | the audit of the level against its source |

The source's points file is the one its `<stem>.boundaries.toml` names under
`[trailing_edges] file`, or else `<stem>.te.txt` beside the mesh. Its points
are in the unit its first line names; when the boundaries file states the
mesh's unit (`[import] units`) and it differs, the points are converted to it
before they are matched to the mesh's edges, by `refine` and `audit-mesh`
alike, and the level's points file is written back in the source file's unit.
A unit that names no scale (OTHER) is then refused.

`refine.json` states `schema_version` (1), `source`, `level`, `config` (the
refinement file read, or null), `specs` (the factors of each family),
`components`, `ignored_families_tables` (the families whose file table was not
read for its factors), `faces` (the face count of each family of the output) and, with
`[periodic]`, `periodic` (the two cut faces, their angle, their node counts and
the largest distance between matched nodes in the source and in the level).
Its `families` entry holds, per family:

- a grid: `method` (`"grid"`), `reason` (the layout recovered), `layout`,
  `ends`, `split`, `grid` (the node counts before and after), `intervals`
  (chordwise and spanwise, before and after), `faces` (before and after),
  `order` (`"sweep"` when the source's sweep was kept, `"nearest"` otherwise)
  and `interfaces` (the nodes of each curve it shares);
- a smooth tube is a grid whose circumferential direction is a periodic cubic
  spline, with the seam at the lowest source node index of its first end
  station and no trailing-edge points; a multiblock family reports `layout`
  `"multiblock"`, `patches` (their number), `blocks` (each patch's `rows` and
  `columns` before and after), `arcs` (the patch sides) and `order`
  (`"nearest"`); `--chordwise` and `--spanwise` are refused on it, and across a
  patch side the level is continuous, not smooth;
- a remeshed family: `method` (`"remesh"`), `reason` (why no grid was taken),
  `elements`, `quads`, `triangles` and `quad_share` (the element mode and its
  counts; `elements` on a grid says the key was ignored),
  the families remeshed together, the curve edges kept, the median ratio of
  edge length to target, the interfaces rebuilt on a grid's nodes, and the
  face counts before and after;
- a family the refinement does not change: `method` `"copied"`, or
  `"unchanged"` with the face count of its two-layer `band` when a grid's
  nodes on a shared curve changed.

A key may be added to `refine.json` or `audit.json` without changing
`schema_version`; a key is removed or changes type only with a new one.

### What the audit judges

The audit reads the mesh, and the source when there is one, with numpy alone.
A GATE is judged on its own terms, a RELATIVE CHECK compares a 95th percentile
(linear interpolation between ranks) of the mesh with the source's, and a
FIGURE is reported and never judged.

| gate | fails when |
|---|---|
| G1 | an edge is shared by more than two faces, two nodes sit at one position (within 1e-9 of the size, the diagonal of the bounding box), or a face has zero area |
| G2 | two neighbouring faces have opposite orientation, or a closed family does not enclose a positive volume |
| G3 | the open boundary loops of the mesh are not the source's in number and in the opening each closes: a level loop matches one source loop, one to one, when every node of each lies within a quarter of the source loop's extent (its bounding-box diagonal) from the other's polyline |
| G4 | a trailing-edge point lies on no mesh edge, or the trailing-edge chains are not the source's in number |
| G5 | two families that shared nodes in the source share none |
| G6 | a grid family written at factor 1 no longer has the source's faces in coordinates and order |

| relative check | fails when the 95th percentile exceeds |
|---|---|
| equiangle skewness | the source's plus 0.05 |
| quadrilateral warp | the larger of the source's and 10 degrees |
| size growth (the area ratio of two neighbours, across edges whose dihedral is below 30 degrees) | the larger of the source's and 2 |

Each check is made per family and on the whole mesh. A check is relative
because the source is the accepted mesh: a source that fails a practice is
reported, not judged. Reported and never judged, per family and on the whole
mesh: the face, triangle and quadrilateral counts, the aspect ratio (95th
percentile and largest), the faces beyond the pre-processor's quality
thresholds (aspect ratio above 8 and above 20, skewness above 0.5, warp above
10 and above 45 degrees, a quadrilateral angle under 45 degrees, a triangle
angle under 30 degrees), a face quality ratio (a face's inscribed radius
against its neighbours', the solver's user's manual calling below 2 good; the
manual gives no formula, so the package's is its own reading), the faces whose
aspect ratio exceeds 50, the trailing-edge triangles whose aspect ratio exceeds
50, and the faces lying on the plane y = 0.

Without `--against` only G1, G2 and G4 are judged and the rest is reported.
G6 is judged only for a level `refine` wrote, which names its grid families at
factor 1 (and each component whose every member is one) in its `refine.json`
under `unchanged_grids`; `audit-mesh` reads them from the level's
`refine.json` when it names that level and the source given with `--against`,
so a saved level is re-audited as `refine` audited it.

`audit.json` holds `schema_version`, `mesh`, `source`, `passed`, `gates` and
`checks` (each with its `name`, `family`, `verdict` (`pass`, `fail` or
`not judged`) and `values`) and `figures` (per family and `(whole mesh)`). A
failed gate or check is also a warning: `audit gate G3 failed on (whole mesh):
open_loops 2, source_open_loops 1, unmatched_loops 1`.

### The Python API

Each of these is imported from `pyflightstream.workspace`.

| name | what it is |
|---|---|
| `refine_mesh(mesh, factor=None, *, families=None, chordwise=None, spanwise=None, config=None, out_dir=None, overwrite=False)` | writes a level and returns a `RefinedMesh`; raises `InputArtifactError` on every refusal and `MissingExtraError` when a family must be remeshed and the geometry extra is missing |
| `RefinedMesh` | frozen: `folder` (the level folder), `obj` (its OBJ), `files` (every file written, the OBJ first), `report` (the `families` entry of `refine.json`) and `audit` (the `MeshAudit` of the level) |
| `audit_mesh(mesh, *, against=None, unchanged_grids=())` | audits an OBJ, writes `<stem>.audit.json` beside it and returns a `MeshAudit`; `unchanged_grids` names the grid families G6 compares (default: those the level's `refine.json` lists) |
| `MeshAudit` | frozen: `mesh`, `source`, `gates` and `checks` (each item with `name`, `family`, `values`, `verdict`, `passed` and `line()`), `figures`, `path`, `passed`, `failures`, `as_json()`, `summary()` and `write_csv(path)` |
| `derive_thin_blade(geometry, *, root_offset, overwrite=False, boundary=None)` | the function behind `pyfs-matrix degenerate` (FR-429): derives the thin blade of a blade mesh (an `.fsm` or an OBJ), writes it beside the source and returns a `ThinBlade`; `thin_blade_path` gives the name it writes |

### Limits of the refinement

- **A stretched body can warn on skewness.** A body refined with different
  `axial` and `circumferential` factors stretches its faces, and the relative
  skewness check warns when the level's 95th percentile exceeds the source's
  plus 0.05, as it did on the tested cylinder at axial 2 with circumferential
  1 and the reverse. The level is written; read the reported values before
  taking the warning for the stretch asked for.
- **A grid that mixes cells is remeshed.** A lateral grid that mixes
  quadrilateral and triangulated cells is remeshed under `method = "auto"` and
  refused under `method = "grid"` naming the reason; a family of quadrilaterals
  only is recovered as one grid, a smooth tube or a multiblock.
- **Quad-dominant levels can warn.** The audit's growth and skewness checks
  read a quadrilateral beside a triangle as a size jump and a paired rhombus
  as skewed, so pairing can raise both figures; the tested two-family plate
  at factor 2 warned on both. A warning comes only from a figure above its
  limit; read the reported values.
- **A multiblock patch side is continuous, not smooth.** No spline crosses it.
- **Factor 1.** Under `method = "auto"` a family at factor 1 is copied; a
  family that states `method = "remesh"` is remeshed at any factor.
- **A component is audited against its members.** A level written with
  `[components]` is compared with the union of the members in the source,
  read from the level's `refine.json`.
- **A triangulated tip cap is not part of a grid.** A cap is part of a grid only
  when it is a fan of triangles around one pole node or a zipper. Give any other
  cap a family of its own in the pre-processor and merge it back with
  `[components]`, as in
  [A solid blade kept structured by dummy families](how-to.md#a-solid-blade-kept-structured-by-dummy-families).
- **A grid that shares nodes with an earlier grid is remeshed.** Grid families
  are refined in the source's family order; a later grid that shares nodes with
  an earlier one is remeshed, or refused naming both under `method = "grid"`.
- **Offline verification, not validation.** The tests verify the geometry of a
  level offline. Whether a level gives the solver the result of a mesh made at
  that size in the pre-processor is a licensed comparison, reported for one
  isolated propeller on 26.124 in RPT-162.

## Mesh format policy

The library's mesh seam is deliberately narrow: OBJ in and out. READING a
mesh is a runtime capability through trimesh, because the
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

The reference artifact refuses the retired fields `rotation`, `blade_travel`,
`rpm_sign_installed` and `rpm_sign_isolated`. The speed a row states is a
MAGNITUDE and the hand is `rpm_sign` on that rotor's own block, beside its
`axis`. `pyfs-matrix upgrade --in-place --inputs <inputs dir>` strips the
retired fields (PFS-2029.08); the [migration record](../migrating-to-0.22.0.md)
explains the historical row-sign convention. The argument that
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
