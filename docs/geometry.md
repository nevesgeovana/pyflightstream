# Geometry: build a body before the run

## Gridding a named IGES

`geometry iges-grid` builds one surface grid from IGES files whose components are named, one
family per component, with conformal junctions and the spacing laws of a grid control file;
`geometry iges-convert` rewrites IGES files as one IGES of B-spline faces the solver's CAD
import reads, names kept. Both use the gmsh kernel, which installs with the package.

```text
pyfs-workspace geometry iges-grid wing-body.igs --grid grid.toml --out model.obj
pyfs-workspace geometry iges-grid wing-body.igs --grid grid.toml --out wing.obj --component Wing
pyfs-workspace geometry iges-convert fuselage.igs --out fuselage-nurbs.igs
```

`--component NAME` (repeatable) grids only the components it names, and the record measures each
junction of two components against the original faces of both.

[Grid and convert a named IGES](mesh/iges.md) gives the grid control file, the name rule and the
limits.

A named IGES can also be generated from a parametric configuration, checked against an original,
meshed into quads and read back as a planform: [Parametric aircraft
geometry](geometry-parametrization.md).

## Morphing a sector or a wheel

`geometry morph` applies the tables of one morphing file to an OBJ in a fixed order: hub
rings, repitch, the collapse of a blunt trailing edge and, for a sector, the full wheel,
without a solver. `geometry hub-rings` runs the first table alone: it rebuilds a
quad-dominant hub around each blade root as the complete rings of quads repitch needs.

```text
pyfs-workspace geometry morph sector.obj --morphing morphing.toml --out morphed.obj
pyfs-workspace geometry hub-rings sector.obj --morphing morphing.toml --out rings.obj
```

The [how-to](mesh/how-to.md#morph-a-sector-or-a-wheel) gives both files, the sector's and
the wheel's, and the [reference](mesh/reference.md#morph-control) lists the keys and checks.

## Collapsing a blunt trailing edge

`geometry collapse-te` merges the two sides of a one-cell base strip of named blades into one
sharp line on an OBJ, without a solver. A `.fsm` input is refused: the operation works on the
OBJ.

```text
pyfs-workspace geometry collapse-te sector.obj --morphing morphing.toml --out sharp.obj
```

The [how-to](mesh/how-to.md#collapse-a-blunt-trailing-edge) gives the table and the order with
repitch (repitch first), and the [reference](mesh/reference.md#collapse-trailing-edge-control)
lists the checks.

## Small blade pitch changes

`geometry repitch` changes blade pitch while retaining the blade mesh. The user names
the hub families to rebuild; every other family stays in place and is listed in the report.
It runs without a solver on `.fsm` and `.obj` files:

```text
pyfs-workspace geometry repitch sector.fsm --morphing morphing.toml --out pitched.fsm
```

Start from the [morphing template](mesh/morphing.toml). The
[how-to](mesh/how-to.md#repitch-a-blade) explains axes and the
[reference](mesh/reference.md#repitch-control) describes the checks and supported topology.
Inspect the root and leading edge before using the output in a run.
The rebuild transports every complete hub ring around the root and projects its free
interior nodes onto source faces. The shared root follows the rigid blade rotation.
The checks report root stand-off in metres and local cell edges. Above half a local
edge, one warning explains that the hub shape near the root changes by that amount.
Non-root hub nodes that leave the source surface beyond the documented tolerance
are refused before output is written.

## Preparing geometry

Inventory filenames include the mesh format: `geometry inventory wing.obj`
writes `wing.obj.boundaries.toml`, and inventory of `wing.fsm` writes
`wing.fsm.boundaries.toml`. OBJ inventories are never overwritten because
they may contain authored import and boundary declarations.

A run matrix names a finished body: a saved simulation (`.fsm`). Everything that makes that body, lofting a CCS file, converting and
cleaning an IGES assembly, building a primitive or a wing from section files,
scaling, renaming, mirroring, copying, cutting or repairing a mesh, happens
once, before any run, in the geometry stage:

```text
pyfs-workspace geometry build              # preview: the script, the names after each step
pyfs-workspace geometry build --apply      # one solver execution, no solve
pyfs-workspace geometry accept wing        # after looking at the body
```

Translate and rotate are not geometry operations: they stay in the run, as the
row keys `TRANSLATE` and `ROTATE` on the opened saved simulation.

Unlike post, a build refuses to replace outputs unless asked with `--overwrite`:
its outputs are inputs of runs. Inspect the body before replacing them.
For `build --rows POL --matrix FILE`, give both options or neither.

The `pyfs-matrix refine`, `audit-mesh`, `inventory` and `degenerate` aliases
give the identical result but will be removed in v1.0.0. Their replacements
are `pyfs-workspace geometry refine`, `audit`, `inventory` and `degenerate`,
respectively.

## A trailing-edge points file from a node list

If you already selected the trailing-edge nodes in ANSA, export the SET node
window as comma-separated `Id, Name, X, Y, Z` rows. List the nodes in their
order along one trailing edge, including both end nodes. No mesh or solver is
needed to turn each neighbouring pair into its edge midpoint:

```text
#  Id, Name, X , Y, Z
30, tip, 0, 10, 2
10, root, 2, 0, 4
20, middle, 6, 4, 8
```

```text
pyfs-workspace geometry trailing-edge --from-nodes nodes.txt --out wing.te.txt --unit METER
```

This writes the unit line `METER` and the points `(1, 5, 3)` and `(4, 2, 6)`
in that order. Coordinates keep the input frame and unit; `--unit` defaults to
`METER` for this route. Without `--out`, it writes `<input stem>.te.txt` beside
the input file, for example `nodes.te.txt` beside `nodes.txt`.
The command does not sort nodes or split gaps. Export
each chain separately. Blank lines and `#` comments are ignored. Fewer than two
nodes, repeated node ids, rows other than five fields and non-finite coordinates
are refused with the file and line to correct. An existing output needs
`--overwrite`. Use the resulting file in the mesh sidecar's `[trailing_edges.wing]`
table. The existing mesh extraction form still takes `mesh output --axis ...
--hub ... --unit ...`.

## The instruction file

Each geometry folder of the workspace, `inputs/geometries/<folder>/`, may hold
one instruction, `<name>.geometry.toml`, beside the files it reads. It states
one source table, the boundary names the saved body must carry, and the build
it runs on:

```toml
# inputs/geometries/wing/wing.geometry.toml
fs_build = "26.125"
boundaries = ["WING", "AIL"]

[ccs]
file = "wing_sections.csv"
units = "METER"
kind = "wing"
component = 1

[[ccs.control_surfaces]]
name = "AIL"
v0 = 0.5
v1 = 0.9
u0 = 0.25
u1 = 0.25
hinge_height = 0.5
angle_deg = 0.0
slot_gap_pct = 1.0
```

| key | meaning | default |
|---|---|---|
| `fs_build` | the build id of `inputs/executables.toml` the solver runs on; `--build` overrides it | required |
| `boundaries` | the names the saved body must carry, in order | required |
| `outputs` | `["fsm"]`, `["obj"]` or `["fsm", "obj"]` | `["fsm"]`; `["obj"]` for a `[mesh]` source |
| `name` | the stem of every built file | the instruction's stem |

`boundaries` is checked, never trusted: after the solver saves the body, the
package reads the saved file's boundary names and fails the build when they
differ from the list, promoting nothing.

### The four sources

- `[ccs]`: a CCS file, with every key of the sidecar's `[import.ccs]`
  ([CCS geometry](ccs-geometry.md)) plus `file`, `units` and, on
  `kind = "file"`, `shedding` (`"AXIAL"` or `"AZIMUTH"`), the direction of the
  relaxed trailing edges, which replaces the row key `CCS_SHEDDING`.
- `[cad]`: an IGES file, with the keys of `[import.cad]`
  ([CAD inputs](cad-inputs.md)), and `[[cad.operations]]` applied to the CAD
  bodies before the conversion: `delete` (`body`), `delete_by_threshold`
  (`axis` and `above_m` or `below_m`), `mirror` (`body`, `plane`), `scale`
  (`body`, `factor`), `translate` (`body`, `vector_m`) and `rotate` (`body`,
  `axis`, `angle_deg`). A body is cited by its native index, from 1.
- `[create]`: a body or a wing the solver builds. The CAD Create settings
  (`merge_tolerance_pct`, `spline_segments`, `spline_loft`,
  `curvature_points_per_circle`), then either `[[create.bodies]]` (`shape` is
  `box` with `corner_m` and `lengths_m`, `sphere` with `center_m` and
  `radius_m`, `cylinder` with `center_m`, `radii_m` and `length_m`, or `sheet`
  with `plane`, `offset_m` and `lengths_m`) or `[[create.sections]]` (`file`,
  `units`, `chord_m`, `twist_deg`, `leading_edge_m`, `plane`) lofted by
  `[create.loft]` (the wing loft keys of `[import.ccs]`, and `export_ccs` to
  keep the cross-section file the solver writes).
  **The section loft is refused on 26.124 and 26.125.** It imports each
  section with `CAD_CREATE_IMPORT_CURVE_TXT`, which is broken on both builds
  (the script aborts at the command), so the
  evidence gate refuses the route there, naming the command, until the curve
  import works. The CCS route (`[ccs]`) is the working one on those builds.
- `[mesh]`: a raw mesh (`.obj` or `.stl`) and the unit it is written in.

A source file lies in the instruction's folder and is named by its file name.
STEP files, `units = "OTHER"` and control surfaces with `space = "REAL"` are
refused, as in the run.

### Operations

`[[operations]]` are applied in the order written, after the source:

| `op` | it states | it makes |
|---|---|---|
| `scale` | `factors`, optional `surface` | the body scaled |
| `rename` | `surface`, `to` | the surface renamed |
| `mirror` | `surface`, `plane` | the mirrored copy joined to its source |
| `circular_copy` | `surface`, `axis`, `count` (the original included), `angle_deg`, `names` | `count - 1` new surfaces, named in creation order |
| `linear_copy` | `surface`, `count`, `vector` (in the source unit), `names` | as above |
| `cut` | `surface`, `plane`, `offset`, `names` | the cut surface replaced by the surfaces named |
| `fill_holes` | `surface` | the surface's holes closed |
| `delete_degenerate_faces` | nothing | the degenerate faces removed |
| `extract_faces` | `quantity` (`X`, `Y`, `Z`, `AREA`, `QUALITY`), `min` and/or `max`, optional `surface`, `name` | a new surface of the faces selected |
| `delete_faces` | the selection keys of `extract_faces`, no `name` | the faces selected removed |
| `transform_nodes` | `mesh_sha256`, `nodes`, `vector` | the nodes moved, on a `[mesh]` source |
| `remesh_from_sections` | `surface`, `axis`, `count`, `loft` (`wing` or `fuselage`), `name` | a new surface lofted from the body's own cross-sections; the source stays |

Every operation that creates a surface states its names; the build checks them
against the saved file. A node operation is pinned to the sha256 of the source
mesh, because a node number is a fact about one file: when the mesh changes,
the build is refused, naming both digests.

**Rebuilding a body from its own cross-sections.** `remesh_from_sections` cuts
the body `surface` into `count` full cross-sections spaced evenly along `axis`
of the reference frame, selects every section and lofts them with the CCS
`loft`: a `wing` marks its sharp trailing edges and closes its tips (C2
chordwise, C0 spanwise), a `fuselage` closes its ends (C2 both ways). The new
surface `name` comes after the source, which stays, so the two can be compared
in the saved body:

```toml
boundaries = ["Wing", "WingR"]

[[operations]]
op = "remesh_from_sections"
surface = "Wing"
axis = "Y"
count = 9
loft = "wing"
name = "WingR"
```

The loft reads every selected curve, so an instruction states one
`remesh_from_sections`, on a `[mesh]` or `[cad]` source; beside a `[ccs]` or
`[create]` source, whose own curves would join the sections, it is refused. The
cutter waits for a licensed probe on each build (see **Evidence on the build**
below): until one verifies it, `--apply` refuses and the preview shows the
script. On a build whose command database records the cutter broken, the preview
refuses too and exits 2.

The QA catalog now includes `CAD_CREATE_AUTO_CROSS_SECTIONS`, dry-rendered on
26.124 and 26.125. It imports the synthetic QA wing into CAD Create, asks for
nine uniformly spaced full sections along Y, and reads the saved curve count:
nine after the cutter, zero before it and zero in the unchanged control.
Missing or malformed saved state is unobservable. This judge counts curves;
it does not establish their geometric accuracy. The licensed probe remains
deferred, and adding its specification does not lift the build's refusal.

### Trailing edges

`[trailing_edges]` has the routes of a mesh's sidecar (`file`, `detect`,
`none = true`) and is read for the `[mesh]`, `[cad]` and `[create.bodies]`
sources. A CCS wing and a section loft mark their own trailing edges
(`mark_trailing_edges`), and the table is refused beside them.

## Building

Run the build from the geometry folder (no argument) or name the folder or the
file. Without `--apply` nothing runs and nothing is written: the command prints
the script, the boundary names after each step, the folder it would write into
and every refusal.

With `--apply` the solver runs once, with no solve, in `<folder>.partial/`. It
builds the body, exports its surface mesh, marks the trailing edges and saves
the simulation. The package then reads the saved file back, audits the
exported mesh ([the mesh audit](mesh/reference.md)), writes a preview and a
record, and moves the outputs into place:

| file | content |
|---|---|
| `<name>.fsm` | the saved body |
| `<name>.fsm.boundaries.toml` | its boundary inventory |
| `<name>.preview.vtk` | open it in ParaView: the surfaces coloured by boundary, the trailing edges as lines |
| `<name>.audit.json` | the audit of the exported mesh |
| `<name>.build.json` | every input with its sha256, the build, the solver, the outputs, the audit |
| `<name>.build.txt`, `<name>.build.log` | the script the solver ran and its log |

With `outputs = ["obj"]` the folder holds `<name>.obj`, its `.obj.boundaries.toml` and its
trailing-edge points file `<name>.te.txt` instead of the saved simulation; with
both outputs the mesh is a geometry of its own, `<name>_obj/`. `--png` also
draws `<name>.preview.png`.

Existing partial and mesh sibling folders must carry a build ownership record
for this instruction. A retry preserves an owned partial folder as
`<folder>.partial.previous/` (with a numeric suffix when needed), including its
script and log. `--overwrite` replaces recorded mesh outputs individually and
keeps other files in the sibling folder. An unowned destination is refused
before the solver runs; preserve or rename it before building.

The OBJ inventory includes face counts, its digest, the build that exported it,
and a named `STANDARD` trailing-edge entry whose label is the mesh stem and
whose file contains the saved edge midpoints. An export with no marked edges
declares `[trailing_edges] none = true`. Mark the OBJ before using it in a matrix.

**What a rebuilt mesh keeps.** The sidecar retains `translate` and `rotate`
operations, the generated entry's `wake_termination_nodes`, and named base
regions. These come from the rebuilt mesh's sidecar first, otherwise from its
source sidecar; qualified filenames precede legacy filenames. Operations apply
during marking, with the edge points transformed consistently. Carried sidecars
must use the named declaration schema; planning refuses retired declarations
with their translation. The build prints what it carried over.

An audit failure retains the built outputs and their record in the partial
folder, including the exported mesh in its `mesh/` subfolder. Nothing is
promoted, and a previously built body is preserved even with `--overwrite`.
The record in a partial folder names the files where they are
(`<name>.fsm`, `mesh/<name>_obj.obj`, `<name>.audit.json`), so it can be read
and checked there. A partial folder is never a geometry a row names, and
`geometry accept` refuses one.

Nothing moves into a geometry folder until the whole build succeeded. Each
geometry's record is written last, after its files, and its partial folder is
removed after that, so an interrupted build never leaves a record naming a
file that is not beside it. Building again with `--overwrite` completes it.

The exit status is 0 when the body is built, audited and promoted, 1 when it is built
and an audit gate failed (nothing is promoted; built outputs stay in the
partial folder for inspection), 2 when the build is refused and
nothing was written, 3 when the solver or the read-back failed (nothing is
promoted and the partial folder keeps the script and the log). The command
prints `geometry accept` for promoted geometries only.

**Evidence on the build.** A build runs only commands the command database
records as verified on the chosen build, for the commands the run did not
already emit: the mesh operations, the CAD body and CAD Create commands, the
CCS lofts and the surface-mesh export. Until a licensed probe verifies one,
`--apply` refuses on that build, naming the command; the preview still shows
the script. A command the build does not have, or records broken, has no script
to show: the preview refuses too, naming it, writes nothing and exits 2.
The surface-mesh export is verified on 26.100 and on 26.124 to 26.127, so a
`[mesh]` build with no operation awaits nothing on those builds and runs with
`--apply`; on another build it still names `EXPORT_SURFACE_MESH`.

## A control-surface deflection sweep

A `[ccs]` wing may vary one control surface's angle:

```toml
[sweep]
control_surface = "AIL"
angle_deg = [-10.0, 0.0, 10.0]
```

Run the build from `inputs/geometries/`, naming the folder:

```text
cd inputs/geometries
pyfs-workspace geometry build wing --apply
```

Each angle is built as its own geometry beside the base folder:
`wing_AIL-100`, `wing_AIL+000`, `wing_AIL+100` (the angle in tenths of a
degree, with its sign). `--only AIL+100` builds the variants named. The command
prints the `CONFIGURATION` and `GEOMETRY` cells of a row naming each variant;
the matrix names one variant per row.

`--rows POL --matrix FILE` prints those rows whole: the row `POL` of the
matrix, once per variant, with `CONFIGURATION` set to the variant's tag,
`GEOMETRY` to its built file and `POL` to the next free numbers of the
matrix. Nothing is written into the matrix; paste the rows where they
belong.

`--parallel 2` runs up to two variants at once, each its own solver execution,
when the optional `psutil` package measures at least 0.5 GB free. Without
`psutil`, the command warns and runs one variant at a time; install it with
`pip install psutil` to enable the memory check. A variant that fails while another runs beside it
is run again alone, so a licence refused to the second seat costs no variant.
The default is one at a time, and 2 is the limit.

After the variants are built, `wing.sweep.vtk` in the base folder overlays
the swept control surface of every variant built by that command: open it in
ParaView and colour by `variant` (the position of the angle in `angle_deg`,
counted from 1; the field `tags` lists the variants in that order).

The shared overlay counts as an existing output even when `--only` selects a
different subset. Use `--overwrite` to replace it. The old overlay is retained
as `wing.sweep.vtk.previous` (with a numeric suffix when needed), so a failed
replacement has no current overlay but keeps the earlier evidence. The new
overlay is published only after its complete contents have been written.
Variant outputs stay in their partial folders until all solver runs, audits and the
overlay succeed, preserving earlier variant outputs on those failures. A
variant that passed its audit beside one that failed stays in its partial
folder too; the command says so, naming the variant that failed, and exits 1.
The overlay is published after the last variant is promoted, so it never
shows a variant that is not in its folder.
Quadrilateral saved meshes use the exported OBJ for the overlay, with only
the selected control surface's families included.

## Looking at the body, and what the plan reads

Open the preview, then record the check:

```text
pyfs-workspace geometry accept wing
```

`pyfs-matrix plan` reads the record beside the body a row names. It refuses the
row when the instruction or a source changed after the build, naming the
rebuild command. It warns when the built file was saved again afterwards, when
the body was never accepted, when its audit failed, and when the row's
`FS_BUILD` is not the build that made it. It also warns when the row's
`SYMMETRY` is `MIRROR` and the body carries a control surface at a nonzero
angle, naming the surface and the angle: a mirrored half deflects both sides
alike, so a one-sided deflection runs with `SYMMETRY` `NONE`. A body with no
record, saved from the
solver's window or from another tool, is planned as before.

A legacy or incomplete build record that lacks an instruction's `file` or
`sha256` is refused at plan, naming the record and missing key. Rebuild the
body from a geometry instruction to create the current record format.

## From a geometry the row builds

A row that names a CCS, IGES or STL file, or a mesh whose sidecar scales,
renames or mirrors, needs conversion to a geometry instruction before running. The converter writes the instruction:

```text
pyfs-workspace geometry from-sidecar wing.csv            # print it
pyfs-workspace geometry from-sidecar wing.csv --apply    # write wing.geometry.toml
```

It never edits the sidecar or a matrix. It names the `translate` and `rotate`
operations, which stay in the sidecar of the built mesh, and the `GEOMETRY`
cell the rows should name after the build.

## Export a saved body's surface for probes

Probe planning reads a saved body's surface from `<stem>.surface.stl` beside
its `.fsm` file. Export it once on the licensed machine before planning grids
or checking points against that body. From the workspace root:

```text
pyfs-workspace geometry export-surface-mesh inputs/geometries/wing/wing.fsm --build 26.125
pyfs-workspace geometry export-surface-mesh inputs/geometries/wing/wing.fsm --build 26.125 --apply
```

The first command prints the validated export script and destination without
running the solver or writing files. The second opens the saved simulation,
exports all surfaces, and closes the solver without solving. It writes
`inputs/geometries/wing/wing.surface.stl`, in the simulation's units and
reference frame, where the probe gate already looks. Containment queries
need a closed surface; the export does not.

`--build` overrides `fs_build` in the saved body's sibling geometry instruction;
without that instruction, supply `--build`. Executable lookup uses
`inputs/executables.toml` and its local overlay; `--fs-exe PATH` overrides it.
An existing mesh requires `--overwrite`. Export runs in a fresh
`<stem>.surface-export/` folder (numbered on later attempts), retaining its
script and logs. Only a successful export replaces the target, so a failed
retry preserves the earlier mesh. Re-export after changing the saved body.

Exit status is 0 for preview or successful export, 2 for invalid inputs or
filesystem refusals, and 3 when the solver fails or writes no mesh. Planning
itself never launches the solver.

## Mark boundaries once into a saved simulation

`mark-boundaries` reads an OBJ and its `.obj.boundaries.toml`, marks the
declared trailing edges and base regions without initializing or solving,
and saves an FSM for inspection in FlightStream. A legacy `.boundaries.toml`
filename is accepted when the kind-qualified file is absent.

```text
pyfs-workspace geometry mark-boundaries inputs/geometries/wing.obj
pyfs-workspace geometry mark-boundaries inputs/geometries/wing.obj --apply --fs-exe PATH
```

Preview validates the mesh and point files, prints the ordered script and all
five destinations, and writes nothing. `--apply` refuses emitted marking commands whose
status is not VERIFIED on the declared `fs_build`, naming them. The gate covers
trailing-edge imports and detection (including a sweep angle when emitted),
termination-node selection and marking, base-region commands, and surface
combines and renames. Session and mesh-import commands are outside this gate.
In particular,
an unverified `AUTO_DETECT_WAKE_TERMINATION_NODES` blocks an `"auto"` entry.
Rendering a script does not establish solver support. Apply first checks the
executable's build banner with a small log-only pass, then runs one marking
pass in a fresh work folder. An existing FSM requires `--overwrite`. With the FSM
absent, the other outputs are replaced without it, and each one replaced is warned by name.

Explicit wake-termination nodes are selected and marked before the merges of `merge_into`. On
FlightStream 26.124, 26.125 and 26.127 a probe saved a mark made before `SURFACE_COMBINE` on the same node
after it, so a boundaries file that holds both, as the one `sector-to-wheel` writes from a sector
with explicit nodes and merged bases does, is previewed and applied there. On any other build that
pair is refused, naming those builds: declare the nodes as `"auto"` or drop the `merge_into`.

On 26.127 every base region is created before the first wake-edge import, and each base
region's rim file is written in descending order of the face outside the base that holds each
edge: that build drops an imported edge touching an already marked edge whose face comes earlier
in the mesh. Other builds keep the order of the boundaries file.
Each declared base is made by `CREATE_NEW_BASE_REGION`, which states its model and Cp and
saves both. `SET_BASE_REGION_CP <n> CUSTOM <cp>` follows it for a `USER` or `CUSTOM` model
only: on every build the pass serves, the form with `EMPIRICAL` or `AXISYMMETRIC` and a Cp
stops the script, and its two-argument form saves a Cp of zero
(`reports/compat/CMP-26127_2026-11-05_base-region-cp.md`).

The saved surface names, trailing-edge points and group count, termination
count and base-region records must agree before publication. The five outputs
are `wing.fsm`, `wing.fsm.boundaries.toml`, `wing.mark.json`, `wing.mark.txt`
and `wing.mark.log`. Publication rolls back replacements if a file operation
fails; this is not a guarantee against power loss. The declaration sidecar
is never rewritten. The clean FSM inventory sums OBJ face counts after merges,
and the JSON record hashes the inputs, script and saved FSM. Failed attempts
keep their work folder for diagnosis and preserve prior published products.

Exit codes: 0 preview or successful marking, 2 input/evidence/executable
refusal, 3 solver, saved-state or publication failure. See the
[boundary declaration reference](mesh/reference.md) for named entries.

The following solver-free preview is also exercised by the offline tests:
inventory a triangular OBJ, add `fs_build = "26.125"`, `[import] units = "METER"`
and `[trailing_edges] none = true`, then run the first command above. It emits
`SAVEAS`, never `INITIALIZE_SOLVER`, and leaves every input byte unchanged.

**FlightStream 26.100.** That build has no `IMPORT_WAKE_EDGES_FROM_FILE`, so a file entry is
marked by `TRAILING_EDGES_IMPORT`, which reads a file of vertices and marks the mesh edges
between them. The pass matches the entry's mid-point file to mesh edges, splits those edges
into rims and writes one vertex file per rim beside the work script, with one import each, so
no file names both ends of an edge that joins the two sides of a blunt trailing edge. Sides
that touch at a vertex, and a rim closed in a loop, take as many files as that needs. Every
file import stands before the first `CREATE_NEW_BASE_REGION`, because an import between two of
them leaves only the last base saved, and an `auto` rim follows the creates. The read-back counts
the saved trailing edges that join rim vertices without being rim edges, records the count in
`wing.mark.json` and refuses a count above zero. An entry with an edge type other than
`STANDARD`, and explicit wake-termination nodes, have no form on that build and are warned and
skipped. Detection entries and `auto` wake-termination nodes use commands the 26.100 manual
documents, and `--apply` stays refused, naming them, until a probe on 26.100 has verified them.
Setting `MARKING_ROUTE_26100` to `"direct"` makes the pass warn, name
`pyfs-workspace geometry sector-to-wheel` on a saved sector and write nothing.

**FlightStream 26.127.** Each `IMPORT_WAKE_EDGES_FROM_FILE` is one trailing-edge group there,
so a file whose edges form several connected runs, such as the two sides of a blunt trailing
edge, is imported one run at a time: one group per rim, the groups a sector saved by the solver
holds, with the same edges marked. The read-back expects one group per run. Unlike 26.100,
every base region is created first, then every trailing-edge entry and every base region's rim
file is imported, and the `auto` rims follow: on that build a wake-edge import placed before the
first `CREATE_NEW_BASE_REGION` is reported imported and lost when the simulation is saved.

A long preview reports each stage on standard error (reading, matching and placing each entry,
rendering), so a fine mesh is not silent.

When the sidecar's `mesh_faces`, `boundary_faces` or `mesh_sha256` is missing or stale, as it
is after a generated OBJ is built again, run
`pyfs-workspace geometry inventory <mesh> --refresh`: it rewrites only those three keys from
the file as it is now and keeps every other line, the `[import]` table and the declared
trailing edges included. A changed boundary list is refused, since it is yours to correct.
## A full wheel from a sector

A rotor, propeller or fan is meshed once, as one sector between two seams, and
`sector-to-wheel` copies it about the axis into the whole wheel. The sector
holds one blade, the hub surfaces between the seams and the declarations of its
boundaries.

```text
inputs/geometries/sector/
  sector.obj                    groups Blade1, S, N (or Blade1, Base1, S, N, NBase)
  sector.obj.boundaries.toml    fs_build, [trailing_edges.<label>] with files, [base_regions.<family>]
  sector.TE_a.te.txt            mid-points of the rim edges, one file per rim
  sector.TE_b.te.txt
  sector.N.te.txt

pyfs-workspace geometry sector-to-wheel sector.obj --copies 6 --axis x --blades Blade1 \
    [--center X Y Z] [--tolerance 1e-4] [--out wheel.obj] [--overwrite] [--no-wake-terminations]
```

`--hub` remains a deprecated coordinate alias for `--center`. The Python API accepts
`center=` and the deprecated `hub=`. Equal old/new values are accepted once; conflicting
values are refused. No removal release is assigned, and report keys remain unchanged.
The center is a rotor-axis point in mesh units, independent of repitch `reference_point`.


The OBJ gives an OBJ and a saved simulation (`.fsm`) gives a `.fsm`; an `--out`
of the other kind is warned and takes the input's kind. Copy `k` is the sector
turned right-handed about `--axis` (`x`, `y`, `z`, a signed one written
`--axis=-x`, or three numbers) through `--center` (default the origin, in the mesh's unit) by
`360 k / copies` degrees. Nodes of the copies within `--tolerance`, in metres,
are one node. The default is `1e-4`: a seam that sits `1e-5` m apart is merged
by it and so is one that sits `1e-4` m apart. The mesh unit is the `[import]
units` of the boundaries file, or the head of a saved sector; a unit that is not
stated or that the package does not know is warned and read as metres.

`--blades` names the surfaces that are blades, with no name fixed in the
code. Each is numbered one per copy, `<stem><k>` with the stem the name without
its trailing digits, and every other surface is one group shared by the
copies. A base is `Base<k>` for one blade family, `<stem>Base<k>` for several,
and `<family>Base` for a surface that is not a blade. In the OBJ every copy of
a blade surface comes first, then the other surfaces, and inside each copy the
faces keep the sector's order, because the solver's results depend on face
order.

Trailing edges and bases follow the declarations. The points of each
`[trailing_edges.<label>]` are matched to mesh edges within the entry's
tolerance. A surface with two or more rim entries that stays one piece when its
faces are joined only across edges that are not rim edges has a blunt trailing
edge, and its base is the faces whose every node lies on a rim line. A surface
that the rim edges cut into two pieces (the aft base of a body) has the
smaller piece as its base. One rim and one piece is a sharp trailing edge:
no base.

The wake terminations of the trailing-edge entries are carried by default, as the
saved route carries those of a saved sector, so both routes build the same wheel: an
entry's `wake_termination_nodes` file is turned into each copy as
`wheel.<label>_<k>.wake.te.txt`, and `"auto"` is kept as it is. A base region's rim file
carries its own `wake_termination_nodes` the same way, into `wheel.<base>.wake.te.txt` in each
copy's rim table, so a sector that declares its blunt rim once, on the base region, keeps its
terminations. `--no-wake-terminations` (`wake_terminations=False` from Python) drops them all,
and the wheel's entries and rims declare none.
`wheel.wheel.json` says which: `wake_terminations` is `"carried"` or `"dropped"`. On a saved
sector the terminations are rows of the file the route copies, so the switch is warned as not
applicable there and they are carried. The wheel is written beside the OBJ as:

```text
wheel.obj                     one group per surface
wheel.obj.boundaries.toml     the named form: [trailing_edges.<label>_<k>] and [base_regions.Base<k>] per copy
wheel.<label>_<k>.te.txt      one points file per rim per blade
wheel.<label>_<k>.wake.te.txt the wake-termination nodes of an entry that names a file, per copy
wheel.wheel.json              source sha256, copies, axis, hub, tolerance, wake_terminations and the checks
```

With `--overwrite`, a points file the earlier wheel's record lists and the new wheel does not
write is removed. No other file in the folder is touched.

`mark-boundaries` reads that boundaries file as it is. The checks are printed
and written to `wheel.wheel.json`: nodes merged, degenerate faces removed and
warned (a saved sector keeps them and warns; a tolerance that collapses every
face is refused), open and non-manifold edges of the sector, of the copies unmerged and of the
wheel, the area of the wheel over the copies times the sector, and the turn by
`360 / copies` degrees against a turn by one degree more (every node and face
of the wheel maps onto the wheel for the first, and the second must not).
The merge uses a grid search, not a pairwise comparison: a sector of 100
thousand faces (a wheel of 600 thousand) takes about twenty seconds on a
laptop, one of 48 thousand about eight.

That turn cannot see a wrong axis, since copies of anything about any axis map
onto each other, so the surfaces that are not blades are measured too. When their
span about the axis through the hub differs from `360 / copies` by more than 0.05
degrees, the wheel is still written and the verb warns: `the sector's surfaces that
are not blades: the sector spans <angle> deg about the axis through the hub, and
one of <copies> copies is <360/copies> deg, so the copies do not close. Check
--axis, --center and --copies.`

From Python, `pyflightstream.workspace.sector_to_wheel(sector, copies=6,
blades=["Blade1"], axis="x")` does the same and returns a `WheelResult`: its
`written` flag, the files and the report that `wheel.wheel.json` holds.

A saved sector is copied without a solver:

```text
pyfs-workspace geometry sector-to-wheel sector.fsm --copies 6 --axis x --blades Blade1 --out wheel.fsm
```

The mesh block is repeated with the seam nodes merged, and the base regions,
trailing-edge groups and wake terminations of the physics block are repeated
for the blade boundaries. The boundaries of the wheel are the sector's, then
the copies of each blade boundary. **The saved layout is inferred from saved
files; the vendor does not document it.** A save whose first line, its head, reads
`2612,0` (measured on build 10052026, 26.125) closes its physics block with six rows
after the base-region model codes, and the wheel keeps them unchanged, comparing each
row it copies with the sector's and writing nothing if one differs. A base region or trailing-edge group
named for no boundary, as a sector marked with `merge_into` holds, follows the
boundary its faces lie on: on a blade it is repeated, its copies named
`<stem><k>`, and elsewhere it stays single. A save of FlightStream 26.127 holds the
three per-face trailing-edge rows as integers, 0 or the rim face's trailing-edge group,
where earlier builds hold T/F; the wheel keeps that form, each copy's edges naming the
copy's own group. A file whose layout the reader does
not recognize (a name in the physics block with no face in the mesh, or with
faces both on a blade and off it, two names whose copies would be named alike,
a row of another length, a termination count that differs) is warned with the
reason, nothing is written and the exit code is 2. The wheel is read back with the
package's own saved-file readers before it replaces the output. Exit codes: 0
written, 2 a refusal, an existing output without `--overwrite`, or an
unrecognized layout.
## Merging two OBJ

`pyfs-workspace geometry merge` joins two trimmed OBJ along the open boundaries that lie
within a distance of each other. You name which part is adapted; the other is kept unchanged.

```
pyfs-workspace geometry merge wing.obj nacelle.obj --threshold 0.001 --adapt nacelle.obj --out wing_nacelle.obj [--overwrite]

wrote wing_nacelle.obj                 kept part first, in its node and face order; adapted part after it; groups kept
      wing_nacelle.merge.json          threshold, kept, adapted, interface edges, band faces, triangles created, open edges left
      wing_nacelle.audit.json          the audit of the output (see `geometry audit`)
      wing_nacelle.obj.boundaries.toml the inventory of the output
```

`--threshold` is in the OBJ's own length unit. The interface is every open-boundary chain of
either part whose nodes lie within it of the other part's open boundary. Everything else
stays as it was, so a part's far open boundary is no part of the interface, and neither is
an adapted node that touches a stretch of the kept boundary whose own nodes are out of reach.

The kept part does not change: the three coordinates of each vertex as the file wrote them
and their order, and its faces and their order, lead the output. An OBJ of `v`, `f` and `g`
lines written as `v x y z` with single spaces comes through to the byte. What a mesh of this
package does not hold is not carried from either part: `vt`, `vn`, `usemtl`, `s` and
comments after the first vertex, a vertex's words past the third, a face's texture and normal
indices, and every family takes the keyword the kept part's last `g` or `o` used. Along the
interface the adapted part takes the kept nodes, in one of two ways, per chain:

- **Node for node.** Both chains carry one node per node within the threshold. The adapted
  nodes are replaced by the kept nodes and no face changes kind: quads stay quads.
- **A band.** Otherwise two face layers of the adapted part beside the interface are
  remeshed at the source's sizes, held on the kept nodes along the interface, with every
  other node of the band on the adapted surface. A band family that held a quadrilateral is
  paired back to quads where it can; the triangles left are reported as `triangles_created`.
  A band that would hold a whole family rebuilds that family, warned.

The adapted faces and nodes outside the band do not change. In the output they keep their
relative order, with the band's faces inside their own family where they fall on the source,
because FlightStream results depend on face order. A family name found in both parts is
warned and the adapted one takes a `_2` suffix.

From Python, `pyflightstream.workspace.merge_objs` takes the same inputs and returns a
`MergedMesh` with the paths written and the counts of the record.

**What is warned.**

- An `--out` not named `.obj` is warned and the output takes that name's `.obj` form, as the
  wheel verbs take the sector's kind.
- An `--adapt` with a folder that is not the part's own path adapts the part of that file name
  and is warned, naming both paths; a bare file name selects the part with no word.
- A threshold that finds no interface warns, writes nothing and exits non-zero.
- A threshold smaller than part of the gap merges what it found and leaves the rest open.
  The open edges still facing the other part are warned with their count; an open boundary
  that runs away from the interface, such as a symmetry plane, is not.
- An interface node that travels past the threshold to reach a kept node is warned, since the
  threshold measures a node against the kept edges and the kept nodes lie further apart:
  `<part>: <far> of <n> interface node(s) moved further than the threshold <threshold> to reach
  a kept node, the furthest by <distance>: the threshold measures a node against the kept edges
  and the kept nodes lie further apart`.
- A degenerate face left in the output, and an adapted face turned against the source face
  nearest it, are warned with their count.
- A family whose faces sit in more than one place in a source file is warned: its faces are
  written together, so that part's face order is not the file's.
- Two parts whose boundaries files state different `[import] units` are warned: nothing is
  scaled, so scale one part to the other's unit and merge again.
- When the band cannot be held on the kept nodes (`faces_split` in the record), the faces on
  the interface are split onto the kept nodes instead, and the band is not remeshed.

**The boundary declarations of the two sources are not merged.** The output's
`.boundaries.toml` holds its inventory only, and a declared trailing-edge file is not
rewritten; the command says so on the console. State the output's trailing edges and base
regions in that file before marking it.

**Limits of the method.**

- It joins and adapts; it does not trim. The parts must already be cut along the interface:
  an overlap past one face layer of the adapted part folds the faces there, and a warning
  gives their count, so trim the part back and merge again.
- A gap is bridged by the first layer of faces of the adapted part, off its surface only by
  the distance to the kept nodes. The two surfaces are not blended and no intersection is
  computed.
- A threshold wider than the cell size can pair nodes that are not neighbours across the cut;
  choose it just above the largest gap.
- Normals are not reoriented: two parts whose faces run opposite ways stay so, and the audit
  of the output reports it.
- An edge shared by two faces is no open boundary, so a third part meeting the same curve
  finds nothing to join there and stays open.

## Remeshing a sector and its power-off body

A sector from a mesher often carries a distribution the solver does not need: a
blade refined at the trailing edge, an irregular spinner. Two verbs rebuild the
sector from its surface alone, with no solver and no preprocessor, and write
the matching power-off body:

```text
pyfs-workspace geometry sector-remesh sector.fsm --blades Blade1 --axis x \
    --chord-cells 26 --le 0.007 --span-cell 0.06 --out sector_new.fsm [--overwrite]
pyfs-workspace geometry power-off-body sector.fsm --blades Blade1 --axis x --copies 6 \
    --out body.fsm [--overwrite]
```

**The topology of this release.** The sector is a saved simulation of one sector
with three boundaries: one blade (`--blades` names it), a spinner and a nacelle.
The blade's quads end in two trailing-edge rim lines that start on the root loop,
with a base strip between them (a blunt trailing edge), and the nacelle has a flat
base (faces of kind 3). No boundary name is fixed in the code: the spinner is the
boundary the blade's root loop lies on, and the nacelle is the other one, the one
with a base and a rim. The axis passes through the origin of the file's coordinates:
these two verbs take no `--center`. A sector without this topology (a sharp trailing
edge, more than one blade, a nacelle without a base, a blade that is not a quad grid
between two rims, an axis off the origin) is warned, naming what was not found;
nothing is written and the exit code is 2. **A sharp trailing edge is not covered yet.** **The saved layout is
inferred from saved files**, as for `sector-to-wheel`, and a sector marked with `merge_into` is
read as it is there. `power-off-body` takes the nacelle's base region and rim group under the
nacelle's name or, as that marking leaves them, under the one name for no boundary whose faces
lie on the nacelle alone (`NBase` merged into `N`), and writes them under that name. It warns,
naming every merged family, which it keeps and which it removes with the blade (`Base1` merged
into `Blade1`); a nacelle with no such entry, or with two, is warned as not found and nothing is
written. The rows written are stated in the writer's docstring.

**The blade** is rebuilt from the source surface, not from its distribution. Each
chord ring is a monotonic spline of arc length on each side from the leading edge;
the new rows are placed by

- chord: `--chord-cells` cells on one side and one more on the other (so a ring has
  an even number of edges and the tip closes with quads alone), the first cell
  `--le` of the side's arc, growing geometrically to mid-chord and then one fixed
  width to the trailing edge, which is not refined; the widths never fall along the
  chord in any row, the root row included;
- span: constant cells of `--span-cell` metres, then a region of `--tip-length`
  metres whose cells shrink to `--tip-ratio` of the constant one at the tip;
  a `--span-cell` that asks for more than 10000 rows is refused with nothing written;
- cuts: every row at one radius from mid blade outward, blended from the root row
  inboard. The tip radius is the blade's largest radius about the axis unless
  `--tip-radius` states it, and the default is warned with the value used. A stated
  radius more than 1 percent off the blade's is warned too: `tip-radius (CLI:
  --tip-radius) is <stated> m, and the blade's largest radius about the axis is <tip> m:
  the rows of a remesh stop short of the blade's surface or run past it on an
  extrapolation. Check the value.`;
- the root row follows the chord law and is never moved: the spinner adapts to it
  with an O-grid around the root loop (`--spinner-layers` layers, smoothed by
  Winslow's equations), rings forward (`--spinner-rings`) and a kite of quads at
  the nose. A grid that folds is warned, names `--spinner-layers` to raise and
  writes nothing;
- the base between the two trailing edges is one row of quads flagged from root to
  tip, and the tip is closed by quads.

`--root-margin-r` and `--nose-radius-r` are fractions of the tip radius (0.038),
not metres, so no length of one rotor is in the code. The sector's angle is read
from the seams and warned, with the angle the copies need, when it is not 360/N for the copies asked. The nacelle
(`--nacelle-theta` cells around the sector, `--nacelle-cells` rings) is built by
one function with the same arguments by both verbs, so the nacelle of the remeshed
wheel and of the body have the same nodes. `--axis` is `x`, `y` or `z`; the flow
direction is the one from the spinner to the nacelle's base.

**The body** is `--copies` sectors of a closed spinner (`--spinner-theta`,
`--spinner-rings`, no hole) and that nacelle, merged across the seams, full quad,
with the nacelle's base region and rim group as its only physics entries. Its quads
are counted in the record; the method asks for fewer than 2000. A `--tip-radius` more
than 1 percent off the blade's is warned here with the end `the lengths given as
fractions of it are taken from the stated value, not from the blade. Check the value.`

Faces keep the order in which the quads were added, because the solver's results
depend on face order. Each file is written through a `.part` file that must read
back with the package's own saved-file readers. The checks are printed and written
to `<out stem>.remesh.json` and `<out stem>.body.json`: triangles per boundary (none
for a quad pair), the radius spread within a row at the root, mid blade and tip,
the chord widths, the root loop nodes the spinner shares with the blade, the turn by
`360 / N` degrees against a turn by one degree more, the trailing edges and groups
of the wheel, the blade's area against the source's, non-manifold and open edges.
`sector-to-wheel` on the remeshed sector then gives a wheel that a turn of 360/N
maps node on node and face on face.

From Python, `pyflightstream.workspace.sector_remesh` and `power_off_body` do the
same and return a `RemeshResult`. Exit codes: 0 written, 2 a refusal, an existing
output without `--overwrite`, or a topology not found.

## The other geometry verbs

`pyfs-workspace geometry refine`, `audit`, `inventory` and `degenerate` take
the arguments of `pyfs-matrix refine`, `audit-mesh`, `inventory` and
`degenerate` and give the same result. The `pyfs-matrix` names still work and
warn that the group is their home.

`pyfs-workspace geometry beam <geometry> --families <family ...> --stations <n>
[--visual-inspection]` cuts each named blade's sections from the mesh into
`<geometry>.<family>.beam.toml` beside it, the file an FSI input with
`[sections] source = "mesh"` reads; `--visual-inspection` also draws
`<geometry>.<family>.beam.pdf`. See
[Sections from the mesh](fsi-workspace.md#sections-from-the-mesh).

`pyfs-workspace geometry prop-slice --geometry <file>.obj|.igs --blades N
[--axis DX DY DZ] [--origin X Y Z] [--blade-dir DX DY DZ] [--stations R_R ...]
[--unit mm|cm|m|in] --out <folder>` cuts one blade of a propeller at radial
stations and writes the G17 definition that rebuilds it (`propeller.toml`),
one normalized profile per station (`sections/sNN.dat`), the table of chord,
pitch angle, thickness, camber, skew and rake over r/R (`table.csv`) and the
record `prop-slice.json`; an IGES is read with the gmsh kernel. See
[Slicing an existing propeller](propeller.md#slicing-an-existing-propeller).

## Matrix geometry

`GEOMETRY` accepts only a saved simulation (`.fsm`). No flag enables an OBJ
matrix row. Prepare and mark the OBJ once, inspect the saved geometry, and
name the FSM in the matrix:

```text
pyfs-workspace geometry mark-boundaries inputs/geometries/wing.obj --apply
pyfs-matrix plan
```

Marking requires a licensed solver; planning does not run one. Geometry build
keeps its own solver pass. Matrix runs open the saved simulation and never
import a raw mesh or mark its trailing edges or wake-termination nodes.
The row's `BASE_REGIONS` selection on an opened simulation remains supported.

For `wing.fsm`, planning reads the first existing file in this order:

1. `wing.fsm.boundaries.toml`
2. `wing.boundaries.toml`
3. `wing.obj.boundaries.toml`

The plan names the file read. Any `import`, `trailing_edges`,
`wake_termination` or `base_regions` declaration table in that file is
refused with the marking command. When none exists, the inventory read from
the FSM is written to `wing.fsm.boundaries.toml`.

If `wing.mark.json` exists, planning compares every recorded input digest.
A changed or missing mesh, declaration sidecar or points file is refused by
name; repeat marking with `--apply --overwrite`. An FSM with no marking
record is accepted, including one prepared in the GUI. A row's `FS_BUILD`
different from the record's `fs_build` produces one campaign warning listing
all affected rows. It does not prevent planning.

FSI rows retain raw OBJ imports because coupling requires the mesh at each import.
They read `<mesh>.obj.boundaries.toml` with the same strict named declarations as
`mark-boundaries` and use its marking emitter and VERIFIED command gate at each import,
where a command documented and not verified on the row's build is warned and emitted.
Every other matrix row requires an `.fsm`; prepare it once with
`pyfs-workspace geometry mark-boundaries <mesh>.obj --apply`.

Repitch accepts a reference installation-axis table, for example
`axis = { shaft = "X", vector_wrt_global = [2, 0, 0] }`. It normalizes the
physical shaft and projects `blade1.zero` into its disk plane, using the same
frame convention for automatic pitch axes, the hub chart and wheel checks.
A datum parallel to the shaft cannot define the blade plane and must be fixed.
