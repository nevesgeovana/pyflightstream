# Geometry: build a body before the run

A run matrix names a finished body: a saved simulation (`.fsm`) or a mesh
(`.obj`). Everything that makes that body, lofting a CCS file, converting and
cleaning an IGES assembly, building a primitive or a wing from section files,
scaling, renaming, mirroring, copying, cutting or repairing a mesh, happens
once, before any run, in the geometry stage:

```text
pyfs-workspace geometry build              # preview: the script, the names after each step
pyfs-workspace geometry build --apply      # one solver execution, no solve
pyfs-workspace geometry accept wing        # after looking at the body
```

Translate and rotate are not geometry operations: they stay in the run, as the
row keys `TRANSLATE` and `ROTATE` and as the `translate` and `rotate`
operations of a mesh's sidecar ([Mesh sidecar reference](mesh/reference.md)).

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
`--overwrite`. Use the resulting file in the mesh sidecar's `[trailing_edges]`
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
| `<name>.boundaries.toml` | its boundary inventory |
| `<name>.preview.vtk` | open it in ParaView: the surfaces coloured by boundary, the trailing edges as lines |
| `<name>.audit.json` | the audit of the exported mesh |
| `<name>.build.json` | every input with its sha256, the build, the solver, the outputs, the audit |
| `<name>.build.txt`, `<name>.build.log` | the script the solver ran and its log |

With `outputs = ["obj"]` the folder holds `<name>.obj`, its sidecar and its
trailing-edge points file `<name>.te.txt` instead of the saved simulation; with
both outputs the mesh is a geometry of its own, `<name>_obj/`. `--png` also
draws `<name>.preview.png` (the `plot` extra).

Existing partial and mesh sibling folders must carry a build ownership record
for this instruction. A retry preserves an owned partial folder as
`<folder>.partial.previous/` (with a numeric suffix when needed), including its
script and log. `--overwrite` replaces recorded mesh outputs individually and
keeps other files in the sibling folder. An unowned destination is refused
before the solver runs; preserve or rename it before building.

**What a rebuilt mesh keeps.** The built mesh's sidecar carries over what the
run reads of a mesh and the build does not make: the `translate` and `rotate`
operations of `[[import.operations]]`, `[wake_termination]` and
`[base_regions]`. They are taken from the sidecar the mesh had before the
rebuild, else from the sidecar of the `[mesh]` source. With a carried
`translate` or `rotate`, the sidecar marks the trailing edges by detection
(`detect = "auto"`), because the run refuses a points file beside an
operation that moves the body; `<name>.te.txt` stays beside the mesh. The
build prints what it carried over.

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
reference frame, where the probe gate already looks. The geometry extra is
needed for containment queries, not for this export.

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

## The other geometry verbs

`pyfs-workspace geometry refine`, `audit`, `inventory` and `degenerate` take
the arguments of `pyfs-matrix refine`, `audit-mesh`, `inventory` and
`degenerate` and give the same result. The `pyfs-matrix` names still work and
warn that the group is their home.
