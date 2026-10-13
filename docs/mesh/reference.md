# Mesh input reference

### The surface names

A row cites a raw mesh's names as it cites a `.fsm`'s. Where they come from
depends on the format.

**An OBJ's names are read from its groups.** The solver imports an `.obj` as
one surface per `o` or `g` group that holds a face, named by the group and
numbered in the order the groups appear in the file; a group holding no face
makes no surface and takes no position. So when
an `.obj` has no sidecar, the plan writes one beside it and says so on stderr:
`pyfs-matrix plan`, `pyfs-matrix run` and `pyfs-matrix inventory wing.obj`
reach it the same way. It holds the list and nothing else:

```toml
# inputs/geometries/wing.boundaries.toml, as the plan writes it beside wing.obj
# Written by pyflightstream from the groups of wing.obj, which had no sidecar;
# the OBJ's sha256 was <the sha256 of wing.obj>.
# One boundary per `o` or `g` group holding a face, named by the group, in the
# order of the file: how the solver numbers an OBJ's surfaces on import
#. The package never rewrites this file. Add the [import] table with
# the file's units, and the [trailing_edges] table, beneath the list
#.
boundaries = [
 "Wing",
 "Tail",
]
```

Add the `[import]` table and the `[trailing_edges]` table beneath the list
only you can state the unit the file is written in and
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
refuses an `.stl` by name, since it
has no mesh block to read the order from.

### The unit

**A RAW MESH STATES ITS UNITS.** The mesh-import family takes the file's
length units as an argument, and a mesh file carries none. So
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
same sidecar declares, and the script goes on exactly as it does after
opening a `.fsm`. The file's unit goes to `IMPORT` and nowhere else. The simulation's length unit defaults to metres; after import, the setup's `simulation_length_unit` replaces that default. See [simulation geometry controls].
the reference area, chord and span, a `TRANSLATE` distance, the frames the
package places. The run record keeps the table as `mesh_import`, because the
geometry's digest alone cannot tell a run in millimetres from the same file
run in metres.

**`IMPORT` converts the body from the file's unit into the simulation's
metres, measured on 26.124**: a wing OBJ written in millimetres, its trailing
edge detected, solved as the same wing written in metres to the print. The file route in millimetres and every
other build are not measured, so a mesh written in metres
is still the one case whose scale depends on nothing.

A unit is never assumed. A raw mesh whose sidecar states no `[import]` table
is refused when the script is built, before any seat is spent, naming the
table, the key, the sidecar and the units the build takes. So is a unit
`IMPORT` does not take, and so is a setup asking to load the solver
initialization, since a new simulation has no stored state to load. An
`[import]` table beside a `.fsm` is refused too, since a saved simulation
carries its own units and nothing would read it.

### Explicit CAD conversion is a separate route

For an IGES file, the sidecar explicitly selects CAD
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
[CAD geometry inputs] for the supported IGES route, explicit
options, unit observations and mesh-quality limitations. OBJ/STL inputs do not
accept CAD options.

### A CCS file is another route

A CCS file is routed by a third table of
the same `[import]`, `[import.ccs]`, which chooses what the solver builds from
it. The table's keys, what each kind of geometry reads and what is refused are
on [CCS geometry]; this page holds only its place in the
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
| `rotate` | `axis` and `angle_deg` | the build's rotation command | `-1` |

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
IMPORT...
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
sidecar:

```toml
# inputs/geometries/wing.boundaries.toml, beside wing.stl
boundaries = ["Wing"]

[import]
units = "METER"

[trailing_edges]
file = "wing.te.txt" # the points file, beside the sidecar
type = "STANDARD" # optional: STANDARD, RELAXED, JET_OUTFLOW, VORTEX_SHEDDING
tolerance = 0.0001 # optional: in the simulation's metres
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
detect = { surfaces = ["Wing"], sweep_angle = 60 } # or detect = "auto", every surface
```

`detect = "auto"` emits `AUTO_DETECT_TRAILING_EDGES`. A table of `surfaces`
emits `DETECT_TRAILING_EDGES_BY_SURFACE` on them, cited by the sidecar's names
as the renames left them, exactly and never by position, and `sweep_angle`, in degrees, emits
`SET_TRAILING_EDGE_SWEEP_ANGLE` before it. Detection marks an edge where the
surface creases, so the angle decides what a twisted blade gets. It gives every edge the STANDARD type and matches no points, so `type`
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
detect = { surfaces = ["Wing"] } # or detect = "auto", every surface

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
by their end vertices. Its first line names the length unit of its points, and every later
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
read and every point is checked against the mesh,
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
turns the export off itself runs
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
| The file route: the import line, the node file, a file of mid-points | Runs on FlightStream 26.124, the one build it was run on. 26.122 and 26.123 document a form 26.124 refuses, and are refused naming the report; a build that does not carry the command is refused too. On the steady point measured, that order made the file route equal the other routes; an unsteady run takes the same order and is not measured. On the geometry tried before, neither command changed the saved state. The file route in millimetres and other builds are not measured; on the file route, a body that does not come out in metres leaves the node file's points off its edges, and the count check records the point `FAILED_SCRIPT`. One manifest field is not a file digest and is named here so
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
the [supported pattern] treats it as immutable. Where a comparison has to survive a
line-ending change, compare the parsed geometry rather than the manifest
digest.

### The boundary inventory sidecar

A saved simulation carries its boundary names in the solver's own order, and a
workflow row cites boundaries by those names. The order is a property of the file, so it is never stated
by hand: a setup artifact that carries `mesh_order_list` is
refused, and the order is written from the file itself:

```text
pyfs-matrix inventory inputs/geometries/30_WB.fsm
```

writes `inputs/geometries/30_WB.boundaries.toml`, a `boundaries` list in the
file's order, and refuses to overwrite one that exists without `--overwrite`.
The sidecar sits beside the file, so a geometry kept in its own folder,
`inputs/geometries/30_WB/30_WB.fsm`, has it inside that folder, and the run reads it
from there. `pyfs-matrix inventory` reads an `.obj`'s order from its groups
instead, and refuses any other file without a
mesh block by name, because it
has no block to read the order from.

A row whose `.fsm` has a sidecar is checked when the script opens the file: a
sidecar that disagrees with the file's own block is refused before any seat is
spent, naming both lists, and an agreeing one is recorded in the run record as
the inventory source. The record also carries the names
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
already applied. It sets the action count to 0 and removes
the action records, and it puts every other block back to the content a
freshly imported file holds, where that content is measured for the file's
build and length unit; everything else comes from the script. The blocks and
their fresh-import content were measured on the ten tier-3 geometries, fresh
imports saved by 26.120 in metres, which hold the same
`GLOBAL`, `MOTION`, `POST`, `WAKE`, `SOLVER`, `ACOUSTIC`, `STABILITY` and
`AEROELASTIC` whatever the shape: those are the blocks reset, and each one
reset is named on standard error. Anything set by hand in them is discarded,
the reference point and frame of `GLOBAL` and the solver and wake settings of
`SOLVER` and `WAKE` included, since the script sets them again; the ten
geometries were all made by one preparation recipe, so the content is the one
common to those saves. Never reset:
`MESH`, `PHYSICS`, `WRAPPER` and `GRAPHICS`, and
`CAD`, `CADCREATE` and `CADMESHING`. A file of
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
for d in inputs/geometries/*/; do n=$; f="$d$n.fsm"; [ -f "$f" ] && pyfs-matrix inventory "$f" --clean; done
```

**The plan warns too.** `pyfs-matrix plan` reads the geometry of
every row whose run type is `unsteady` or `unsteady_rotor`, a continuation
included, with the same reader, and for each file carrying saved actions
prints a warning naming the rows that open it, the file, each action and the `--clean` command; a file whose action records cannot
be read is named as unreadable. The plan never refuses on that account: its
rows, its files and its exit status are those of the same plan without the
warnings.

## The refinement file and the audit

This section is the reference of `pyfs-matrix refine` and `pyfs-matrix
audit-mesh`; the walk-through is
[Refining or coarsening a mesh].

### The two commands

```text
pyfs-matrix refine MESH [FACTOR] [--families A,B] [--chordwise F] [--spanwise F]
 [--config FILE] [--keep-first-row FAMILY[,FAMILY...]]
 [--out DIR] [--overwrite]
pyfs-matrix audit-mesh OBJ [--against SOURCE] [--out FILE]
```

| argument | of | meaning |
|---|---|---|
| `MESH` | `refine` | the source OBJ; it and its folder are never modified |
| `FACTOR` | `refine` | the factor of every selected family, a finite number above zero |
| `--families A,B` | `refine` | the families to change, comma separated |
| `--chordwise F`, `--spanwise F` | `refine` | the factor of one index direction of every selected grid family; refused for a remeshed family |
| `--config FILE` | `refine` | the refinement file |
| `--keep-first-row FAMILY[,FAMILY...]` | `refine` | the grid families that keep the spanwise width of their row at another component, comma separated |
| `--out DIR` | `refine` | where the level folder goes; the `out_dir` keyword of `refine_mesh` in Python; `--out-dir DIR` is a deprecated alias |
| `--overwrite` | `refine` | replace an existing level folder |
| `OBJ` | `audit-mesh` | the OBJ to audit |
| `--against SOURCE` | `audit-mesh` | the OBJ it was made from; without it only G1, G2 and G4 are judged |
| `--out FILE` | `audit-mesh` | write the figures as CSV, one row per family and figure; `--csv FILE` is a deprecated alias. Refused when it names a file the command reads or writes: the OBJ, its boundaries file, its `<stem>.te.txt` or the points file the boundaries file names, the OBJ's `<stem>.refine.json`, the `<stem>.audit.json` the command writes, and every one of these files of the `--against` source |

`refine` exits 0 when the level is written, whatever the audit says, and 2 when
the request is refused. `audit-mesh` exits 0 when every gate and check passes,
1 when one fails and 2 when its input is refused.
A refusal is printed on standard error, names the object, what was refused and
what to do, and ends with `Nothing was written.`: every refusal of the
arguments, the refinement file, the family names and the installed extras comes
before any family is resampled and before any file is written, and so does a
refusal of the boundaries file or of the points file it names, which the audit
reads. Both commands read `[trailing_edges] detect` through the reader the
workflow uses, so a shape the workflow refuses is
refused here too, in the same words, before any work. A level is written into `<folder>.partial`, audited there, and renamed
once complete, so an error leaves no level folder behind; with `--overwrite`
the existing level is replaced only then, and kept when an error comes first.

`--out-dir` and `--csv` are deprecated aliases of `--out` on their command: each
gives the identical result and warns once that it is deprecated, and an alias
given together with `--out` is refused, naming both.

### Where the factors come from

1. FACTOR applies to every family `--families` selects.
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
4. A `[families.<name>]` table whose factors are not read is a
 warning naming it, and `refine.json` lists it under
 `ignored_families_tables`; an `elements` key in it still applies, and the
 warning names `keep_first_row` among what the table no longer states.
 `--keep-first-row` asks the option on either route.

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
keep_first_row = true

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
| `[refine]` | `elements` | `"triangles"` or `"quad-dominant"` | the elements of every remeshed family that does not state its own |
| `[families.<name>]` | `elements` | `"triangles"` or `"quad-dominant"` | the elements of a remeshed family: quad-dominant pairs the remeshed triangles into convex quadrilaterals, never across an open boundary, the trailing edge or a ridge; refused with `method = "grid"`, ignored on a family that `"auto"` resolves to a grid |
| `[families.<name>]` | `factor` | number above zero | multiplies the intervals of each index direction of a grid; divides the target edge length of a remeshed family |
| `[families.<name>]` | `chordwise`, `spanwise` | number above zero | the factor of one index direction of a grid, replacing `factor` there |
| `[families.<name>]` | `keep_first_row` | `true` or `false` | a grid with a trailing edge keeps the spanwise width of its row of panels at each end station that meets another component and refines that row chordwise only; the spanwise factor applies to the other rows. `--keep-first-row` on the command and the `keep_first_row` keyword of `refine_mesh` ask the same; when FACTOR, `--chordwise` or `--spanwise` give the factors the table is not read, this key included |
| `[families.<name>]` | `method` | `"auto"`, `"grid"` or `"remesh"` | `"auto"` takes the grid when it is recovered and remeshes otherwise; `"grid"` refuses a family whose grid is not recovered, naming why; `"remesh"` remeshes it |
| `[families.<name>]` of a body | `axial`, `circumferential` | number above zero | the target edge length divided by `axial` along the axis and by `circumferential` around it; the family is remeshed |
| `[families.<name>]` of a body | `axis` | three numbers, not all zero | the body's axis; required with `axial` or `circumferential` |
| `[families.<name>]` of a body | `origin` | three numbers | a point of the axis |
| `[components]` | `NAME = [...]` | a non-empty list of family names | the members written as one family `NAME` of the output, their faces in the source's family order |
| `[periodic]` | `axis` | three numbers, not all zero | the axis of the rotor the sector belongs to |
| `[periodic]` | `origin` | three numbers, in the OBJ's coordinates | a point of that axis |
| `[periodic]` | `copies` | an integer of at least 2 | the sectors in a full turn; one cut face maps onto the other by `360/copies` degrees |

Each of these is refused naming the file, the table and the key, and listing
the known keys: a table or key the list above does not hold, a family the mesh
does not hold, a family table with neither `factor` nor `chordwise` nor
`spanwise`, `chordwise` or `spanwise` on a
family whose method is `"remesh"`, `axial` or `circumferential` without `axis`,
beside `factor`, `chordwise` or `spanwise`, or with `method = "grid"`, and a
malformed `axis` or `origin`. In `[components]`, a member the mesh does not
hold, a family listed in two components, and a component named after a family
that is not one of its members are refused naming the component and the
family. A `[periodic]` table whose key is missing or malformed, or that finds
no pair of cut faces, is refused naming the key.

### The tag of a level

The tag is `[refine] tag` when the file states one, used as given. Otherwise it
is built from the factors, `p` standing for the decimal point, and a family
that keeps its first row adds `k` to its part:

| refinement | tag |
|---|---|
| factor 2 on every family | `R2` |
| factor 0.5 on every family | `R0p5` |
| chordwise 1.5 and spanwise 0.7 on every family | `R1c1p5s0p7` |
| axial 2 and circumferential 1 on every family | `Ra2t1` |
| factor 2 on `Wing` only | `R-Wing2` |
| `Wing` at 2 and `Tip` at 1.5 | `R-Wing2-Tip1p5` |
| a selection whose built tag is longer than 32 characters | `R-<n>fam-<hash>` |

A factor in a built tag shows at most 6 significant digits; `refine.json` holds
the exact factor under `specs`. For a short tag without a hash, two otherwise
identical selections whose factors agree to 6 significant digits build the
same tag, and the second level is refused as an existing one unless
`--overwrite` replaces it; give a `[refine] tag` to keep both.
Summary tags hash the exact factors, so matching rounded spellings do not
imply matching summary tags.

A built tag of at most 32 characters is the tag above. A longer one is
`R-<n>fam-<hash>`, at most 20 characters for any selection: `<n>` is the number
of selected families and `<hash>` the first 8 hexadecimal characters of the
SHA-256 of the canonical selection, encoded as UTF-8. The canonical selection
holds one line per selected family, in the source's family order, joined by a
newline: the family's name, then every option its table states that changes
the level as `key=value` pairs sorted by key and
separated by single spaces, for example `Wing factor=2 keep_first_row=true
spanwise=2`. The same selection gives the same tag on every run and machine,
and two selections that differ in a family or an option give different
canonical selections; the 8-character digest tells them apart and is not a
guarantee against collision. For such a tag `refine.json` lists the selected
families under `tag_selection`, in the source's order. A short tag tells
apart a family's factors and its `k` only: two selections that differ only
in `method` or `elements` share it. A family name that cannot be part of a
folder name is refused when the tag is built from the names, and not when
the tag is the summary and the hash.

### The files of a level

The level folder is `<out>/<stem>_<tag>/`, and every file in it is written
through the package's one text route, without a carriage return.

| file | written when | content |
|---|---|---|
| `<stem>_<tag>.obj` | always | the level, its families in the source's order |
| `<stem>_<tag>.te.txt` | the source has a trailing-edge points file | one mid-point per trailing-edge edge of the new mesh, under the source file's unit line |
| `<stem>_<tag>.boundaries.toml` | the source has a sidecar | the source's sidecar, naming the new points file and each component in place of its members |
| `<stem>_<tag>.refine.json` | always | what was done to each family |
| `<stem>_<tag>.audit.json` | always | the audit of the level against its source |

The source's points file is the one its `<stem>.boundaries.toml` names under
`[trailing_edges] file`, or else `<stem>.te.txt` beside the mesh. Its points
are in the unit its first line names; when the boundaries file states the
mesh's unit and it differs, the points are converted to it
before they are matched to the mesh's edges, by `refine` and `audit-mesh`
alike, and the level's points file is written back in the source file's unit.
A unit that names no scale is then refused.

`refine.json` states `schema_version`, `source`, `level`, `config`, `specs`,
`tag_selection`,
`components`, `ignored_families_tables`, `faces` and, with
`[periodic]`, `periodic`.
Its `families` entry holds, per family:

- a grid: `method`, `reason`, `layout`,
 `ends`, `split`, `grid`, `intervals`
`faces`,
 `order`
 and `interfaces`; a grid that keeps its
 first row adds `kept_rows` and
 `trailing_edge`; a detected one adds `trailing_edge_points`, the mid-point
 `[x, y, z]` of each edge of the line detected on the source, in the unit of
 the level's points file and written as that file writes them, which the
 audit of the level reads to count the source's trailing-edge chains;
- a smooth tube is a grid whose circumferential direction is a periodic cubic
 spline, with the seam at the lowest source node index of its first end
 station and no trailing-edge points; a multiblock family reports `layout`
 `"multiblock"`, `patches`, `blocks`, `arcs` and `order`
`--chordwise` and `--spanwise` are refused on it, and across a
 patch side the level is continuous, not smooth;
- a remeshed family: `method`, `reason`,
 `elements`, `quads`, `triangles` and `quad_share`,
 the families remeshed together, the curve edges kept, the median ratio of
 edge length to target, the interfaces rebuilt on a grid's nodes, and the
 face counts before and after; a family remeshed at factor 1 that shares a
 curve with a refined side adds `shared_edge_target_m`, the minimum, mean and
 maximum of its target length at its nodes on that curve, in metres, for
 example `{"min": 0.0021, "mean": 0.0034, "max": 0.0052}`. The mesh's
 `[import] units` supplies the conversion. If no convertible mesh unit is
 stated, the record uses `shared_edge_target_mesh_units` instead, with
 lengths in the source coordinates;
- a neighbour the two-layer band would cover whole: `method`
 `"rebuilt_whole"`, `reason` `"band_covers_family"`, `band` and `faces`, remeshed whole at factor 1 as if its
 table stated `factor = 1` and `method = "remesh"`, with one warning naming it;
- a family the refinement does not change: `method` `"copied"`, or
 `"unchanged"` with the face count of its two-layer `band` when a grid's
 nodes on a shared curve changed, and `shared_edge_target_m` as above.

A key may be added to `refine.json` or `audit.json` without changing
`schema_version`; a key is removed or changes type only with a new one.
`refine.json` uses schema version 2, which carries the conditional target
unit keys above; the audit schema remains version 1.

### The row kept at an interface

Detection that writes a trailing-edge points file requires `[import] units`
in the boundaries file. When both chordwise extremes are sharp, state
`trailing_edge_direction = [x, y, z]` in the family's refinement table: a
nonzero direction in the mesh's coordinate frame, pointing from leading to
trailing edge. Equal projections or a missing direction are refused; there
is no assumed global aft axis. Listed trailing-edge points take precedence.
As with `keep_first_row`, this family option is read when the file supplies
the refinement factors. Use the refinement file for this route.

`keep_first_row` asks a grid family with a trailing
edge to keep the spanwise width of its row of panels at another component.

- **Interface.** An end station of the grid is
 an interface when two consecutive nodes of it, an edge of the source, are
 nodes of a family of another component. A family's component is the
 `[components]` entry that lists it, else its name up to the first `_`. Every
 end station that is an interface keeps its row; an end station that meets
 only families of its own component, or no family, is refined as before.
- **Kept row.** The inner station of the row is the source's station, so the
 row keeps its source width and its trailing-edge node is the source's. The
 row takes the chordwise factor. The `m` source intervals between the kept
 rows take `max` intervals, bounded by one station
 more, when refining and when coarsening; a kept row is never split and
 never merged with its neighbour. In the level's trailing-edge points file
 the trailing-edge edge of each kept row has its mid-point where the
 source's was.
- **Neighbours.** The band of an unselected neighbour is planned with the
 kept rows, the level's open boundary loops are the source's, and the level
 passes the audit as the same refinement without the option does.
- **Trailing edge.** The one listed in the trailing-edge points file, else,
 when the boundaries file routes the trailing edge to detection, the edges
 the package detects on the source; `refine.json` states which under
 `trailing_edge`. Detection takes the edges
 sharper than the ridge angle, measured across all families,
 that form a grid line from station 0 to the far station. Two sharp extremes
 require the family's `trailing_edge_direction`; the larger projection is
 the trailing edge. Equal projections are refused. A detected line is
 written to the level's points file, `<level>.te.txt`, and when every
 family the `detect` route selects is one whose line was detected, the
 level's boundaries file states `file = "<level>.te.txt"` in place of
 `detect`, so the run marks the line the refinement kept and the audit
 checked. When the route also covers a family the refinement did not
 detect on, `detect` stays and a
 warning names the points file the run does not read.
- **Record.** The family's entry of `refine.json` holds `kept_rows`, the kept
 end stations; the key is absent when the option is not asked. The family's
 part of the tag carries `k`.

Each of these is refused before any work, naming the source, the family and
`keep_first_row`, and ending with `Nothing was written.`: a value that is not `true` or `false`; a family stated with
`method = "remesh"` or with `axial` or `circumferential`; a family whose grid
is not recovered; a multiblock grid; a grid without a trailing edge, neither
listed in the points file nor detected; a grid with no end station at another
component; a grid remeshed because it shares nodes with a grid refined
first; a grid whose kept rows leave no spanwise interval to refine; and, in
the command and the keyword, a family the mesh does not hold or that the
selection leaves out.

The option holds a geometric invariant, the interface row's width and the
place of its trailing-edge edge. It does not claim that a study holding it
isolates the discretisation from every other effect of refinement.

### What the audit judges

The audit reads the mesh, and the source when there is one, with numpy alone.
A GATE is judged on its own terms, a RELATIVE CHECK compares a 95th percentile
 of the mesh with the source's, and a
FIGURE is reported and never judged.

| gate | fails when |
|---|---|
| G1 | an edge is shared by more than two faces, two nodes sit at one position, or a face has zero area |
| G2 | two neighbouring faces have opposite orientation, or a closed family does not enclose a positive volume |
| G3 | the open boundary loops of the mesh are not the source's in number and in the opening each closes: a level loop matches one source loop, one to one, when every node of each lies within a quarter of the source loop's extent from the other's polyline |
| G4 | a trailing-edge point lies on no mesh edge, the trailing-edge chains are not the source's in number, or a chain of the source ends where no chain of the level ends; the lines' total lengths are reported, not judged |
| G5 | two families that shared nodes in the source share none |
| G6 | a grid family written at factor 1 no longer has the source's faces in coordinates and order |

| relative check | fails when the 95th percentile exceeds |
|---|---|
| equiangle skewness | the source's plus 0.05 |
| quadrilateral warp | the larger of the source's and 10 degrees |
| size growth | the larger of the source's and 2 |

Each check is made per family and on the whole mesh. A check is relative
because the source is the accepted mesh: a source that fails a practice is
reported, not judged. Reported and never judged, per family and on the whole
mesh: the face, triangle and quadrilateral counts, the aspect ratio, the faces beyond the pre-processor's quality
thresholds, a face quality ratio, the faces whose
aspect ratio exceeds 50, the trailing-edge triangles whose aspect ratio exceeds
50, and the faces lying on the plane y = 0.

Without `--against` only G1, G2 and G4 are judged and the rest is reported.
G6 is judged only for a level `refine` wrote, which names its grid families at
factor 1 in its `refine.json`
under `unchanged_grids`; `audit-mesh` reads them from the level's
`refine.json` when it names that level and the source given with `--against`,
so a saved level is re-audited as `refine` audited it. G4 reads the same
record for a family whose trailing edge `refine` detected: the source's chains
are the connected chains of its listed edges and the detected edges the record
lists under `trailing_edge_points`, together, so a detected line that a listed
edge continues is one chain.

`audit.json` holds `schema_version`, `mesh`, `source`, `passed`, `gates` and
`checks` and `figures`. A
failed gate or check is also a warning: `audit gate G3 failed on:
open_loops 2, source_open_loops 1, unmatched_loops 1`.

### The Python API

Each of these is imported from `pyflightstream.workspace`.

| name | what it is |
|---|---|
| `refine_mesh` | writes a level; `keep_first_row` names the families that keep their first row and returns a `RefinedMesh`; raises `InputArtifactError` on every refusal and `MissingExtraError` when a family must be remeshed and the geometry extra is missing |
| `RefinedMesh` | frozen: `folder`, `obj`, `files`, `report` and `audit` |
| `audit_mesh` | audits an OBJ, writes `<stem>.audit.json` beside it and returns a `MeshAudit`; `unchanged_grids` names the grid families G6 compares |
| `MeshAudit` | frozen: `mesh`, `source`, `gates` and `checks`, `figures`, `path`, `passed`, `failures`, `as_json`, `summary` and `write_csv`; the static method `MeshAudit.files_read` returns the files an audit of `mesh` reads, each with what it is, a file that does not exist included |
| `derive_thin_blade` | the function behind `pyfs-matrix degenerate`: derives the thin blade of a blade mesh, writes it beside the source and returns a `ThinBlade`; `thin_blade_path` gives the name it writes |

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
 [A solid blade kept structured by dummy families].
- **A grid that shares nodes with an earlier grid is remeshed.** Grid families
 are refined in the source's family order; a later grid that shares nodes with
 an earlier one is remeshed, or refused naming both under `method = "grid"`.
- **Offline verification, not validation.** The tests verify the geometry of a
 level offline. Whether a level gives the solver the result of a mesh made at
 that size in the pre-processor is a licensed comparison, reported for one
 READING a
mesh is a runtime capability through trimesh, because the
trailing-edge extraction sits on the default path of a rotor campaign and a
capability behind an extra makes the library promise what a default install
cannot do. What stays in the
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
retired fields; the [migration record](../upgrading.md#older-layouts)
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
