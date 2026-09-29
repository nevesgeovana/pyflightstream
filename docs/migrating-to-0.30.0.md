# Migrating to 0.30.0

Keep a copy of the workspace and install the release in a separate Python
environment before running existing matrices. Planning and post-processing can
check most changes without starting FlightStream. Solver operations still use
the selected build's command evidence. The package's dependencies and extras
are the ones 0.29.0 declared: the FSI solver still comes with the optional
`[fsi]` extra, and a workbook still needs no Excel process.

A row stating `ROTOR_SHEDDING` is still refused on every build, as in 0.29.0;
direction control for the relaxed wake is not part of this release.

## Storage and sync

Four `pyfs-matrix` commands manage a workspace's disk. `space-in-use` reports
the sizes on disk by top-level folder, by `sims/sim_*` and by extension.
`free-space m<id>` runs a recipe from `inputs/management/m<id>.toml` that
compacts simulation folders into `sims/sim_<id>.zip`, deletes files of named
extensions under `sims/`, or compacts or deletes the post's
`archive/<stamp>/` folders. `delete-sims` deletes named simulations, their own
post products and their `runs.json` records, and refuses to apply against a
matrix product shared with other points until `--matrix-products` says what
happens to it. `sync` brings runs, results and matrices from the workspaces
named in `inputs/sync-workspaces.toml` into the main one, at a cumulative
level (`runs`, `post`, `fsm`, `all`).

Every command PREVIEWS by default and changes files only with `--apply`. Read
the preview before applying. Every call is recorded in
`storage_management.json`; if you used the standalone `fts_sync.py` script, the
record keeps its schema. A synced simulation's `inputs` is a link into the
main workspace's geometry library, never a copy, and `delete-sims` and
`free-space` undo every link in a simulation folder before removing it, so
the mesh it points at survives.

In a `sync`, the main workspace wins a conflict unless you pass
`--prefer-other`, and `--overwrite` archives main's copy of a conflicting file
before taking the other's. A matrix is owned by the one workspace that
declares it (`matrices = [...]`), every difference in it is reported as a
merge conflict, and the owner's copy wins. `sync` also lists, per matrix, the
points the other workspace planned that no record carries
(`PLANNED WITHOUT RECORD`).

A `delete-sims` call may leave a note row (`deleted_sim`) in `runs.json`
beside the run records. `read_manifest` skips it; a tool of your own that
reads `runs.json` directly must skip a row with that key too.

`pyfs-matrix plan` now warns when the points still to run may not fit on the
workspace's disk, estimated from the mean size of a recorded datapoint. It
never refuses for it. See [storage and sync](storage-and-sync.md).

## Pruning an unsteady row's per-step exports

A `free-space` recipe may carry a `[[prune_step_exports]]` table. For an
unsteady row that exported at every step, it keeps the last step of each
per-step export (`<name>_iteration=<step>`) of each point and deletes the
earlier steps, again previewing by default. The recorded call lists the steps
deleted per point, and the listings of the deleted files leave
`products.json`. A product made before the pruning stays, file and entry,
marked `kept_after_pruning`.

The pruning is not undone by a later `post`. A post that needs a deleted step
refuses the series, the time-averaged surface or the section distribution by
name, naming the missing steps and the storage call, rather than writing the
product from the steps that remain. Post every product you need from the full
history BEFORE pruning. See
[the recipe table](storage-and-sync.md#prune_step_exports-keep-only-the-last-step-of-each-per-step-export).

## The quasi-steady rotor

The `qsteady_rotor` run type solves an ISOLATED, AXISYMMETRIC rotor steady: the
blades are held still and the free stream turns about the shaft at the rotor's
speed. The reference declares exactly one rotor block. A second rotor, an
actuator disc, a body rate or a boundary that is none of the rotor's families
is refused; whether the blades are alike is yours to know. A rotor on an
airframe still runs as `unsteady_rotor`.

The row's `SYMMETRY` decides the case:

| case | the row states | what is solved |
|---|---|---|
| SECTOR | `SYMMETRY PERIODIC` and `PERIODIC_COPIES` | one blade, once |
| WHEEL | no symmetry | every blade, once per clocking |

A sector stands for the wheel only in an inflow that varies with the radius
alone: an angle of attack or of sideslip is refused on it, and a custom inflow
is accepted only where it is axisymmetric (to 0.1 % of its largest speed and
1e-4 of its largest radius).

On a wheel in an inflow that varies around the disc (an angle of attack or of
sideslip, or a custom inflow), the row must state `PASSAGE_POSITIONS: k`. The
wheel is solved at `theta_i = i * (360 / N) / k`, inside one blade passage,
and the post averages the clockings. Two clockings converge thrust and torque
to about 0.2 %; the in-plane loads need six or more (RPT-089). A custom inflow
on a wheel is the TOTAL velocity at the disc; the package removes the rotation
of each point from it (`pyflightstream.cases.freestream.prepare_rotating_field`),
so do not subtract it yourself.

The validity parameter is the 1P reduced frequency `k = Omega c / (2 V_rel)`,
the `1P` counted on the blade: one blade meets the inflow's non-uniformity once
per revolution. For every wheel point, `pyfs-matrix plan` shows the per cent of
the span with `k > 0.1` and `k` minimum, maximum and mean, and warns, naming
the point, when that per cent is above zero. Each wheel point leaves
`<point>_qsteady.json` in its datapoint folder, and after the post
`<point>_qsteady_validity.json` beside it, carrying the validity and the
thrust and torque shares from the stations above `k = 0.1`; the point's
super-file row carries the validity columns.

`pyfs-matrix plan --inflow-fft` adds, for every wheel point in a custom inflow,
the harmonic content of that inflow as one blade meets it over a revolution:
per station `n95` and `k_eff = n95 k_1P`, per point `k_eff` minimum, maximum
and mean, the per cent of the span above 0.1, `n_max` and the suggested
`PASSAGE_POSITIONS >= n_max / N + 1`. It warns when the row states fewer, and
with the option the reduced-frequency warning reads `k_eff`. A radial profile
or a uniform field gives `n95` 0 and one clocking.

The post writes two new products per rotor,
`polars/P<sim>-<ALIAS>_qs_positions.csv` (the rotor's and each blade's loads
at every clocking) and `_qs_avg.csv` (their mean per point), and a
`qsteady_rotor` point gets its rotor table. That table's loads are the point's
own solve: a sector's export as it stands, never multiplied by the copies, and
a wheel's clocking 0, whose mean with the other clockings is the average
table's. A wheel's sections table carries `K_1P` per station.

A wheel solved at several clockings exports one log holding its solves in
sequence. The assessor reads it solve by solve and records one verdict per
clocking in the run record's new `clocking_verdicts`, the worst of them being
the point's status. The new `pyflightstream.results.parse_residual_solves`
reads such a log from Python. See
[the quasi-steady rotor](workspace-and-workflows.md#the-quasi-steady-rotor-qsteady_rotor)
and its [definitions](post-processing-definitions.md#the-quasi-steady-rotor).

If you compare against `unsteady_rotor`: a mean thrust taken from few
revolutions sits below the developed wake, and a coarser time step lowers it
further; the documentation states both, with the figures of RPT-089.

## FSI routes

Which workflows accept FSI in 0.30.0:

| workflow | FSI |
|---|---|
| `steady`, `unsteady` without rotor motion | accepted: the fixed-wing route |
| `qsteady_rotor`, periodic sector | accepted: the rotating blade at the row's speed |
| `qsteady_rotor`, wheel | refused |
| `unsteady_rotor` | refused by the plan: "FSI on unsteady_rotor is still in debug on this release (the morph is applied to the un-rotated blade, reported to the vendor)." |

A matrix that couples an `unsteady_rotor` row no longer plans. Run the row
without FSI, or move the study to a `qsteady_rotor` sector where the inflow
allows it. On 26.124 the morph of a mapped rotating blade is applied at its
import azimuth and replaces the rotation (RPT-025 carries the dated
correction), so no coupled rotor number of that route was a rotor result.

A fixed wing is an FSI input stating `[config.wing]`, with
`omega_rad_per_s = 0` and `blade_count = 1`: one wing clamped at its first
station, fed by one XZ section distribution over its one family, in a frame
with the reference axes at the wing's origin (`origin_m`, `span_axis` `+Y` or
`-Y`). Its structural solve applies the aerodynamic loads plus the wing's own
weight under gravity, a vector of the reference frame (-z by default) that the
angle of attack and the sideslip never turn; `self_weight = false` removes it,
for a wind-tunnel model. A steady coupled row runs each point as its own
process and allows at most 50 coupling iterations; a submitting executor
refuses the script, and the probe points, the volume section and the loads
selections are refused on that route. The route and the sign of the XZ cut's
moment column wait on their licensed confirmation.

A `qsteady_rotor` sector takes its `omega_rad_per_s` from the row's `RPM`, so
the structural solve applies the centrifugal terms at the speed the free
stream turns. It couples blade one at azimuth 0 on Z, shaft X through the
origin, one XY section distribution in a frame coinciding with the reference,
and refuses anything else by name.

The pieces a coupled route calls are public in
`pyflightstream.cases.fsi_workspace` (`wire_fixed_wing_fsi`,
`wire_quasi_steady_sector_fsi`, `aeroelastic_surface_ids`,
`structural_node_layout`, `aeroelastic_rbf_type`, `aeroelastic_post_script`,
`emit_steady_aeroelastic_analysis` and the others the change log names), and
the fixed wing's structural solve is `pyflightstream.fsi.wing`
(`weight_loads`, `solve_wing_static`).

Four changes reach a coupled blade you already have:

- The structural nodes sit INSIDE a blade whose configuration carries its
  sections: on each section's camber line, the elastic-axis node at the
  configured chord fraction (30 % when that lies outside 20 to 50 %), the
  leading-edge and trailing-edge nodes at 10 % and 90 %. Planning refuses a
  node outside its section or too close to its surface. A calculated
  configuration's `config.json`, and so its `config_sha256`, now include the
  sections, so the hash of an unchanged calculated input moves once.
- The coupled route emits `AEROELASTIC_RBF_TYPE MULTI_QUADRATIC` unless the
  row's setup states a kernel. State the kernel in the setup to keep another.
- The rotating structural solve includes the in-plane centrifugal softening
  of the flap, about 2.7 % more tip flap on a solid metal propeller blade.
  `RotatingSolution` gains `flap_residual_m` and `flap_tolerance_m`, and
  `converged` requires both residuals.
- The aeroelastic surface list holds the blade's boundary ID. A blade imported
  from an OBJ was given a surface that did not exist and mapped no vertex;
  rerun any coupled OBJ blade of an earlier release.

See [FSI in a workspace](fsi-workspace.md).

## Surfaces: the native strength is opt-in

A Tecplot surface no longer exports the native Tecplot by default. A row whose
pproc does not set `singularity_strength = true` exports the VTK alone: its
`.dat` carries every VTK variable and states `Singularity_strength` as not
carried (`NOT_CARRIED`, and `not_carried` in `products.json`), and no
`<point>_native_tecplot.dat` is written, listed or hashed. To keep the 0.29.0
behaviour, set the key in the pproc:

```toml
singularity_strength = true
```

The value is a TOML boolean; `"true"` or `1` is refused. `pyfs-matrix plan`
states on each row that declares a Tecplot surface whether its strength is
carried. A row under `SYMMETRY PERIODIC` is translated to Tecplot again, its
native file read one zone per periodic copy (RPT-087). See
[surface translation](surface-translation.md).

## Rotor Mach numbers

Every point of an `unsteady_rotor` row, of a `steady` row that states `RPM`
and of a row naming an actuator disc carries its tip and helical Mach numbers,
`M_tip = Omega R / a` and `M_hel = sqrt(V^2 + (Omega R)^2) / a`. The plan
prints them and warns, never refuses, when `M_hel >= 1`; `plan.json` and the
run record carry them under `rotor_mach`. The rotor table
`polars/P<sim>-<alias>_rotor.csv` gains two LAST columns, `MTIP_<alias>` and
`MHEL_<alias>`, so every existing column keeps its position; a reader that
counts the columns must allow two more. See
[tip and helical Mach numbers](post-processing-definitions.md#tip-and-helical-mach-numbers).

## Console and runs

Every console command now ends with a drawn box on stderr instead of the
one-line signature, and the run banner draws an aircraft. Both stay on stderr:
stdout and the exit code are unchanged, so a script that reads stdout is not
affected. A warning of the package's own categories prints as
`[warning] <message>`; the stage lines print the workspace root once and paths
under it relative. `logs/activity.log` keeps every point and absolute paths,
and `--verbose` on `run`, `collect` and `post` prints Python's full warning
format and the per-point lines again.

A run now closes with one line per row saying how many of its planned points
ran, and a point whose files cannot be written is recorded FAILED_SCRIPT (or
FAILED_INCOMPLETE_OUTPUT when the solver had already run) instead of ending
the run. A completed solve is no longer recorded FAILED_INCOMPLETE_OUTPUT only
because the package could not translate one of its surfaces; the failure is in
the record's `warnings`. A row stating `HIDDEN 0` runs with the solver's GUI
again.
