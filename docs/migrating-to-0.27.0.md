# Migrating to 0.27.0

This release takes the basic steps of a FlightStream session through pyfs and
fixes inputs and outputs that were wrong. Nothing is removed, and recorded run
manifests are read without rewriting them. What changes for you is what some
products hold, and what a few files say.

## 1. A steady probe export holds each declared line once (B04)

A pproc declaring N probe lines gave N squared `NEW_PROBE_LINE` commands on a
steady row: three lines of eleven points exported 99 points where 33 were asked
for, as N repeated blocks of the declared lines. From 0.27.0 each line is
emitted once.

The repetition was of the LINES of one probe entry: rectangles and circles
were emitted once, point by point. So for an export made before 0.27.0 from a
pproc whose only probe entry declares lines and nothing else, keep its first
N-th rows: they are the declared lines, in declaration order, and the other
blocks repeat them value for value (measured on a 26.124 export of three
lines). For any other layout (several entries, or lines beside a rectangle or
a circle) do not cut the file: rerun the point, or rebuild the post from a
0.27.0 run. An export from an entry with one line is unaffected.

## 2. An induced drag the solver did not compute is `NA` (B03)

A boundary on the vorticity induced-drag list (`SET_VORTICITY_DRAG_BOUNDARIES`)
without a defined trailing edge is not computed, and the export prints its
`CDi` as zero. A polar group holding such a surface summed that zero. From
0.27.0, when the point's run record puts a surface on the list and its printed
`CDi` is exactly zero, the group's `CDI` is `NA`, and so is every axis column
the export's x force reaches at that point's angles (`CDB`, `CDS`, `CDW`; `CLS`
and `CLW` off zero incidence; `CYW` under sideslip). `post.log` names the
surfaces. The fixed-width custom polar writes the same missing value as `nan`.

If a table of yours now shows `NA` where it showed a number, the surface is on
the list without a trailing edge: give it one, or leave it off the list, which
is what the manual prescribes for a bluff body. A trailing-edged surface whose
induced drag rounds to zero at the printed precision reads `NA` too; raise
`SET_SIGNIFICANT_DIGITS` to narrow that band.

## 3. `post.log` logs the package's own warnings only (R01)

Each post now collects the package's warnings in a sink of its own thread, so
two posts running in two threads of one process no longer write each other's
warnings. A warning raised during a post by code outside pyflightstream is no
longer written to `post.log`; it still reaches your warning filters, and
pyflightstream's own warnings are logged as before.

## 4. The moments of the unsteady step exports are about the moment point (B05)

The loads frame and the moments model were emitted after `START_SOLVER`, so
every step export an unsteady row wrote during the march stated its moments
about the reference frame's origin, while the final export stated the row's
moment point. Both are now emitted before the solve, on every run type, and
are init-phase commands: a script of yours that places either after
`START_SOLVER` is refused. A loads series (`series/<point>_loads_series.csv`)
made before 0.27.0 from an unsteady row states its moment columns about the
reference origin; its forces are right, so rebuild it from a rerun if you
need the moments. In your own scripts, call
`analysis_setup(loads_frame=..., moments_model=...)` before `start_solver`,
and the analysis selections (`load_units`, `boundaries`, `inviscid_only`)
in a second call after it.

## 5. `post.log.json` beside `post.log`, and a WARNING line names its own point (R02)

The top of each matrix's products folder holds a third loose file,
`post.log.json`, beside `post.log` and `products.json`. It carries the same
header and records as the log, one per WARNING line, each with `point`,
`product`, `message` and `remedy`. `products.json` names it under a new key,
`log_json`, and `log` still names `post.log`. A check that lists that
folder's loose files or the manifest's keys will see one more of each. A
rebuild archives it with the log.

A warning that names its own point and product is now logged under them:
`WARNING point=camp/sim_7001/AL-020 product=available-exports: ...` where
0.26.0 wrote `WARNING point=campaign product=stage: point=camp/sim_7001/AL-020
product=available-exports: ...`. A warning that names none still reads
`point=campaign product=stage`. An interrupted post's line ends `Remedy:
correct the stated input and post again.` If you parse `post.log`, read
`post.log.json` instead: it holds the same records as fields.

## 6. A pproc can no longer switch the saved simulation off (G11)

A post-processing artifact whose `[exports]` table says `simulation = false`
is refused, as one saying `loads = false` has been. `pyfs-matrix plan` stops
with `matrix not planned: matrix row POL <pol>: the pproc artifact at <path>
does not validate ... the saved simulation cannot be deselected`; remove the
key. This applies to every row whose `PPROC` names such an artifact, `LEGACY`
rows included, where the key never had an effect. Every point of a row that
names a run type then saves its final state as
`datapoints/DP-<point>/P<POL>-<point>.fsm`, one `.fsm` per point on disk.
Separately, `pyfs-matrix plan` now warns naming each `LEGACY` row whose
`OUTPUTS` declare no `.fsm`; the warning blocks nothing.

## 7. Run records carry the geometry's names, and some sections files change (R03, R04)

- A manifest holding a 0.27.0 workflow record of a `.fsm` with a mesh block
  carries `inventory`, and 0.26.0 refuses it (`extra_forbidden`); post it
  with 0.27.0. A 0.27.0 record with no names writes no key, and 0.26.0 still
  reads it.
- Integrated columns now appear where 0.26.0 kept the raw ones: a stem, a
  numbered name, `all`, for a block recorded in a common frame, or in any
  frame with the live rotor definitions in hand. This applies to 0.25 and
  0.26 records too, while their geometry file still matches the recorded
  hash, and it changes those CSVs' column set. A block in a frame spelt like
  a rotor's with no rotor definition in hand, a user's own `X_RMRP`
  included, is matched as in 0.26.0, and so is every block of a geometry
  that gives one name to two boundaries: those names settle no selection.
- A 0.24.x split recorded in a common frame may be renamed after the entry
  that emitted it (a block of rotor ACTIVE's blades in `MRP`:
  `..._sloads_Blade1.csv` becomes `..._ACTIVE.csv`, `distribution` 2). A
  check that lists the sections files will see the new name. A split in a
  frame spelt like a rotor's keeps its 0.26.0 name.
- A multi-point steady row now writes per-distribution sections files and
  identity columns where 0.26.0 wrote a named `#distributions` skip. A job
  run before 0.27.0 keeps the skip; run it again.

## 8. A raw mesh runs through a workflow, with its unit and its trailing edge (G01, G02, G03, T06)

A row whose `GEOMETRY` names an `.obj` or `.stl` was refused before any seat.
It now runs once the sidecar beside the file, `<stem>.boundaries.toml`,
states the unit the file is written in, its surface names and its trailing
edge:

```toml
boundaries = ["Wing"]      # the file's surfaces, in its order, written by hand

[import]
units = "MILLIMETER"       # the unit the mesh file is written in

[trailing_edges]
file = "wing.te.txt"       # a unit line, then one edge mid-point per line
# or: detect = "auto"
```

The simulation's length unit is metres whatever the file's unit; whether
`IMPORT` converts a body written in another unit is measured on no build
yet, and a mesh written in metres (`units = "METER"`) does not depend on the
answer. A raw mesh whose sidecar declares no trailing edge is refused at
plan. On the file route the row must export its solver log (a run type's
default outputs do), and a pproc that turns `[exports] log` off, or a row
that states `EXPORT_LOG: false`, is refused there, because the run compares
the solver's count of imported edges with the points it wrote. The file
route runs on 26.124 only. A `.fsm` row is unchanged, except that a `.fsm`
whose sidecar states an `[import]`, `[trailing_edges]`, `[wake_termination]`
or `[base_regions]` table is now refused, because nothing would read it;
delete the table. The raw-mesh
refusal's text changed: it names `[import]` and `units =`, and quotes the
anchor 'A RAW MESH STATES ITS UNITS'. A record of a point that imported a
raw mesh carries `mesh_import`, which 0.26.0 refuses; post such a workspace
with 0.27.0.

## 9. The wake-edge helpers write what 26.124 reads (G02, T05)

- `mark_wake_edges(script, edge_type=, tolerance=)` becomes
  `mark_wake_edges(script, edge_type=, tolerance=, units="<simulation unit>",
  node_file="<absolute path>", midpoints=<edge mid-points in that unit>)`. It
  works on 26.124 only; 26.122 and 26.123 now refuse.
- `write_node_file(path, nodes, unit=U)` becomes `write_node_file(path,
  midpoints, unit=U, simulation_unit=<simulation unit>)`. The file has no unit
  line and no ids, and it takes mid-points, not vertices.
- `extract_trailing_edge(...).write_node_file(...)` now refuses. Use
  `write_trailing_edge_node_file(mesh, path, axis=, hub=, unit=)` or
  `trailing_edge_midpoints(...)`; the output of
  `write_trailing_edge_node_file` is a unit line, then one mid-point per
  trailing-edge mesh edge, not one per section.

## 10. `BASE_REGIONS` names the base boundary (RPT-066)

A row writing `BASE_REGIONS: Body` on a body whose base is its own boundary
got no base region and no error: `DETECT_BASE_REGIONS_BY_SURFACE` marks the
boundary it is given as the base, and given the body it marks nothing. Write
the base boundary (`BASE_REGIONS: Base`), and the same in a pproc's
`base_regions`. Nothing refuses the body's name, since nothing offline tells a
base from a body.

## 11. A steady point saves its residual and load plots (G04)

- Every steady workflow script now saves the solver's residual and load plots
  after its exports and before `EXPORT_LOG`, and the section Cp plot where the
  pproc declares sections. Each point leaves two more files (three with
  sections) in `datapoints/DP-<point>/`, listed in its run record with their
  sha256. A missing one fails the point `FAILED_INCOMPLETE_OUTPUT`, as any
  declared export does.
- To keep the previous export set, state `plot_residuals = false`, `plot_loads
  = false` and `plot_sections_cp = false` under `[exports]`.
- A stand-in solver or harness that writes each declared export must also
  write the file named on the line after `SAVE_PLOT_TO_FILE`.
- Unsteady rows, `LEGACY` rows and cases written in Python with their own
  `outputs` are unchanged.
- A `[[raw]]` `SET_PLOT_TYPE` declared before `analysis` or `exec` is now
  refused at plan, because the command is export-phase; declare it before
  `export`.
- `plot_sections_cp = true` with no `[[sections.distributions]]` is refused.

## 12. Two setup commands 26.124 does not answer, and loads not in coefficients (G14, G09)

- A `[[raw]]` `SET_VORTICITY_LIFT_MODEL` on a 26.124 row is refused at plan,
  naming RPT-068. Until now it reached the solver, which stops the script at
  that line.
- A point exported with `SET_LOADS_AND_MOMENTS_UNITS` set to anything but
  `COEFFICIENTS` (through `[[raw]]` before 0.27.0, or `load_units` now) writes
  no product row. Its loads export is still collected and hashed.

## 13. Two new tables, and four words a flag can no longer take (G05, G06)

- A case written in Python that declares an output ending in `_vsec.vtk` or
  `_vsec.dat` used to export it as a surface file. That suffix now names the
  volume-section export, and without a `[volume_section]` table the case is
  refused. Rename the output.
- A setup whose `[[flags]]` declares a flag named `ACTUATOR`, `ACTUATOR_RPM`,
  `ACTUATOR_THRUST` or `PROFILE` (any case) is now refused, because a run type
  reads those words. Rename the flag.
- A reference block with `kind = "actuator"` used to be refused as naming no
  point kind; it is now an actuator disc.

## 14. A row may name an additional pproc, and the products gain an `additional/` family (G12)

- A matrix whose rows state `ADDITIONAL_PPROC` cannot be planned by 0.26.0 or
  older, which refuses it as a key of no run type. A row without the key plans
  and runs exactly as before.
- `products.json` may hold entries under `additional/<pid>/`, and entries for
  native files under `datapoints/DP-<point>/additional/<pid>/`, each marked
  `"additional": true`, carrying `extraction` and `derives_from` and no
  `runs`. A reader that iterates every entry as a product of a run filters on
  that key.
- `additional.json` is new, at the workspace root beside `runs.json`, and
  nothing older reads it. `runs.json` and every run record are unchanged by
  the additional post.
- `pyfs-matrix post` gains `--additional-pproc`, and with it `--fs-version`,
  `--fs-exe`, `--local` and `--recipe`, each refused without it.
- A forced rerun or a continuation archives a point's `additional/` folder
  with the rest of its files; extract it again after one.
- `ResolvedMatrix` gains a last field, `additional_pprocs`; positional
  construction keeps working.

## 15. A roll or yaw rate turns the other way (G13)

A row stating `roll_rate` or `yaw_rate` now writes its free-stream rotation with
the opposite sign to 0.26.0: `roll_rate:40` writes
`SET_FREESTREAM ROTATION <frame> X -6.667` where 0.26.0 wrote `X 6.667`, and
`yaw_rate` likewise about `Z`. The old line solved the OPPOSITE rate on 26.124
(RPT-060, the probe T11): the coefficients of such a point are those of -p or
-r, and they are not converted. A row stating `pitch_rate` writes what it wrote.

- A point of 0.21.0 to 0.26.0 is affected when its name carries a non-zero `P`
  (roll) or `R` (yaw). Its name does not change, so `--resume` skips it: redo it
  by naming it, `--force-rerun <point>`, which archives the old record and its
  outputs first.
- If you wrote the opposite sign in the cell to get the rate you meant, remove
  that: 0.27.0 solves the rate as written.
- Code that read `cases.workflows.FREESTREAM_ROTATION_SIGN` as a number now gets
  a mapping: read `FREESTREAM_ROTATION_SIGN["roll"]`, `["pitch"]` or `["yaw"]`.

## 16. Where a local point runs, its log on a cluster that aborts at `EXPORT_LOG`, and a missing output

- On a cluster whose HPC profile states `[log] export_log = false`,
  `pyfs-matrix run --local` no longer writes `EXPORT_LOG` into the script, as
  a submitted job never did. The declared log of such a point holds what the
  solver printed, written by the run, and a point whose solver printed nothing
  has no log among its `outputs`, a `residual_note` saying why, and the status
  its loads export gives it. Nothing changes on any other machine.
- On such a cluster the extraction scripts of `pyfs-matrix post
  --additional-pproc` carry no `EXPORT_LOG`, with `--local` or planned for a
  submission; an extraction's log is what the solver printed, or absent with
  the reason in its `note`. The build-identity pre-flight exports no log there
  either, and a build the solver did not print is a warning, not a refusal.
- A submitted steady job of several points on such a cluster is collected
  once its points' other outputs and its scheduler's log have settled: the log
  is filed as `<job script stem>_log.txt` in the simulation folder, its points
  carry no `_log.txt` among their `outputs`, and each point's `residual_note`
  names the job's log. A job left WAITING by an earlier version is collected
  by running `pyfs-matrix collect` again.
- A record `FAILED_INCOMPLETE_OUTPUT` for a missing declared output now lists
  the outputs that were written, in `datapoints/DP-<point>/`, with their
  hashes; before, it listed none and they stayed where the solver wrote them.
  Code that took `outputs == []` to mean such a failure reads `status`.
- `CampaignWorkspace.collect_outputs` files the declared outputs that exist
  before it raises for the missing ones, and raises `MissingOutputsError`, a
  `WorkspaceError`, so an existing `except WorkspaceError` still catches it.
- A point run on this machine runs in its own `datapoints/DP-<point>/`, as a
  submitted point does: its exports, per-step ones included, its
  `FlightStreamLog.txt`, its action files and its node file are written there,
  and its record's `cwd` names the folder. A script of your own that looked for
  them in `sims/sim_<id>/` looks in the point's folder; a leftover in the
  simulation folder no longer stops a point, and a leftover in the point's
  folder does. A steady row of several points still runs in the simulation
  folder.

## 17. A row may name a custom free stream (G15)

- A matrix whose rows state `FREESTREAM` cannot be planned by 0.26.0 or older,
  which refuses it as a key of no run type. A row without the key plans and runs
  exactly as before, its script byte for byte what it was.
- `pyfs-workspace init` creates `inputs/freestreams/` beside `inputs/profiles/`;
  run it again on an existing workspace, which keeps everything it holds, or
  make the folder by hand. `workspace.INPUT_KINDS` lists it.
- A setup whose `[[flags]]` declares a flag named `FREESTREAM` (any case) is now
  refused, because a run type reads that word. Rename the flag.
- The record of a point that ran with a custom field carries the file's sha256
  in `inputs_sha256`, under the file's name. A record without it, which is every
  record written before, posts as it did.
- `SimCase` gains `freestream_profile`, None by default.
