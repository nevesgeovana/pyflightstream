# Geometry: build a body before the run

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
script.

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
the script.

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
pass in a fresh work folder. An existing FSM requires `--overwrite`.

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
marked by `TRAILING_EDGES_IMPORT`, which reads a file of vertices. The pass matches the
entry's mid-point file to mesh edges, splits those edges into rims and writes one vertex file
per rim beside the work script, with one import each, so no file names the edges that join
the two sides of a blunt trailing edge. The read-back counts the saved trailing edges that
join two rims of one entry, records the count in `wing.mark.json` and refuses a count above
zero. Detection entries use the detection commands the 26.100 manual documents; an entry
with an edge type other than `STANDARD`, and explicit wake-termination nodes, have no form on
that build and are warned and skipped. The preview renders the script; `--apply` stays
refused, naming the commands, until a probe on 26.100 has verified them. If a probe shows the
solver route cannot mark the rims, the pass on 26.100 warns, names
`pyfs-workspace geometry sector-to-wheel` on a saved sector and writes nothing.

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
    [--hub X Y Z] [--tolerance 1e-4] [--out wheel.obj] [--overwrite]
```

The OBJ gives an OBJ and a saved simulation (`.fsm`) gives a `.fsm`; an `--out`
of the other kind is warned and takes the input's kind. Copy `k` is the sector
turned right-handed about `--axis` (`x`, `y`, `z`, a signed one, or three
numbers) through `--hub` (default the origin, in the mesh's unit) by
`360 k / copies` degrees. Nodes of the copies within `--tolerance`, in metres,
are one node. The default is `1e-4`: a seam that sits `1e-5` m apart is merged
by it and so is one that sits `1e-4` m apart. The mesh unit is the `[import]
units` of the boundaries file; a unit that is not stated or that the package
does not know is warned and read as metres.

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
no base. The wheel is written beside the OBJ as:

```text
wheel.obj                     one group per surface
wheel.obj.boundaries.toml     the named form: [trailing_edges.<label>_<k>] and [base_regions.Base<k>] per copy
wheel.<label>_<k>.te.txt      one points file per rim per blade
wheel.wheel.json              source sha256, copies, axis, hub, tolerance and the checks
```

`mark-boundaries` reads that boundaries file as it is. The checks are printed
and written to `wheel.wheel.json`: nodes merged, degenerate faces removed,
open and non-manifold edges of the sector, of the copies unmerged and of the
wheel, the area of the wheel over the copies times the sector, and the turn by
`360 / copies` degrees against a turn by one degree more (every node and face
of the wheel maps onto the wheel for the first, and the second must not).
The merge uses a grid search, not a pairwise comparison: a sector of 100
thousand faces (a wheel of 600 thousand) takes about twenty seconds on a
laptop, one of 48 thousand about eight.

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
files; the vendor does not document it.** A file whose layout the reader does
not recognize (a name in the physics block that is no boundary, a row of
another length, a termination count that differs) is warned with the reason,
nothing is written and the exit code is 2. The wheel is read back with the
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

The kept part does not change: its vertex lines and their order and its faces and their
order lead the output, to the byte. Along the interface the adapted part takes the kept
nodes, in one of two ways, per chain:

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

- A threshold that finds no interface warns, writes nothing and exits non-zero.
- A threshold smaller than part of the gap merges what it found and leaves the rest open.
  The open edges still facing the other part are warned with their count; an open boundary
  that runs away from the interface, such as a symmetry plane, is not.
- A degenerate face left in the output, and an adapted face turned against the source face
  nearest it, are warned with their count.
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
with a base and a rim. A sector without this topology (a sharp trailing edge, more
than one blade, a nacelle without a base, a blade that is not a quad grid between
two rims) is warned, naming what was not found; nothing is written and the exit
code is 2. **A sharp trailing edge is not covered yet.** **The saved layout is
inferred from saved files**, as for `sector-to-wheel`; the rows written are stated
in the writer's docstring.

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
- cuts: every row at one radius from mid blade outward, blended from the root row
  inboard. The tip radius is the blade's largest radius about the axis unless
  `--tip-radius` states it, and the default is warned with the value used;
- the root row follows the chord law and is never moved: the spinner adapts to it
  with an O-grid around the root loop (`--spinner-layers` layers, smoothed by
  Winslow's equations), rings forward (`--spinner-rings`) and a kite of quads at
  the nose. A grid that folds is warned, names `--spinner-layers` to raise and
  writes nothing;
- the base between the two trailing edges is one row of quads flagged from root to
  tip, and the tip is closed by quads.

`--root-margin-r` and `--nose-radius-r` are fractions of the tip radius (0.038),
not metres, so no length of one rotor is in the code. The sector's angle is read
from the seams and warned when it is not 360/N for a whole number N. The nacelle
(`--nacelle-theta` cells around the sector, `--nacelle-cells` rings) is built by
one function with the same arguments by both verbs, so the nacelle of the remeshed
wheel and of the body have the same nodes. `--axis` is `x`, `y` or `z`; the flow
direction is the one from the spinner to the nacelle's base.

**The body** is `--copies` sectors of a closed spinner (`--spinner-theta`,
`--spinner-rings`, no hole) and that nacelle, merged across the seams, full quad,
with the nacelle's base region and rim group as its only physics entries. Its quads
are counted in the record; the method asks for fewer than 2000.

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
