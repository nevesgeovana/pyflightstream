# Migrating to 0.37.0

> Frozen record: not edited after its release.

A workspace using 0.36.0 needs no changes to its inputs. A row, setup or pproc
that states none of the keys this release adds renders the same scripts and
writes the same records as in 0.36.0. Three outputs change by default, each
named by the parity comparison against 0.36.0 (`scripts/check_parity.py`):
the settings table joins the products (FR-419), the super content states each
rotor's diameter and fills a quasi-steady point's clock (FR-89), and the
plan's left-out line of a coupled steady row names its remedy (FR-421). The
other changes a reader must act on are a new run status, `RAN_MISSING_LOG`
(FR-413), the matrix a command reads when the working directory holds a file
of the same name (FR-411), the keys a `[[prune_step_exports]]` table accepts
(FR-416), the sign of four columns of the installed-frame copy (FR-420), and
FlightStream 26.125 as a registered build (FR-423).

## Outputs that change by default

### The settings table and its codebook (FR-419)

`pyfs-matrix post` writes the solver settings of every recorded point as one
numeric table per matrix, `settings/<matrix>_settings.csv`, one row per point
opening with `POL` and `RUN_ID`, and its codebook
`settings/<matrix>_settings.codebook.json`. Both are listed in
`products.json` with kind `settings_codebook`. A point whose record holds no
solver-setup snapshot (a record written before the snapshot existed) gets no
row and one INFO line in `post.log`; with no snapshot anywhere neither file is
written and `post.log` says so once.

A workspace posted with 0.36.0 therefore gains a `settings/` folder, two
entries in `products.json` and possibly INFO lines in `post.log`. To keep the
products exactly as 0.36.0 wrote them, state in the pproc:

```toml
[products]
settings_codebook = false
```

See [The numeric settings codebook](settings-codebook.md).

### Each rotor's diameter in the super content (FR-89)

The steady and quasi-steady super files and the unsteady polar
(`polars/P<sim>_<name>_uns_avg.csv`) carry `DIAMETER_<alias>`, in metres,
right after each `RPM_<alias>`: the `diameter_m` of the rotor block the row's
reference declares, the number the rotor table divides by, and `NA` where the
reference declares no block of that alias. A row that turns no rotor gains no
column; in a campaign whose super file has the column, that row reads `NA`.

A `qsteady_rotor` point, whose plan states no rotor speed, now takes its speed
from its quasi-steady record, the source its rotor table already read: its
super-file row gains `RPM_<alias>` beside `DIAMETER_<alias>`, and `RPM_CLOCK`
and `J_CLOCK` are filled in every product of the point that states the
condition, where 0.36.0 wrote `NA`. `RPM` keeps what the row and the plan
state.

A script that reads the super file or the unsteady polar by column position
must read by name. Every other column keeps its name, its order and its cells.

### The left-out line of a coupled steady row (FR-421)

The plan still leaves a coupled `steady` or `qsteady_rotor` row out of
`--batch` and `--polar-sweep` (FR-410); its reason now ends with the remedy and
cites no report id:

> a coupled row on steady or qsteady_rotor: its coupling loop starts only after the script ends, and on 26.124 the next point of the job crashed the instance; run these rows point by point, without --batch or --polar-sweep

`plan.json` keeps the same `left_out` keys; only the reason string changed. A
script or note that matched the old text must match the new one. The
`--batch` and `--polar-sweep` help of `plan` and `run` now names every class of
row the grouped modes leave out and says to run those rows point by point.

## The run records

### `RAN_MISSING_LOG`, a point that ended with its outputs and without its log (FR-413)

A point whose declared outputs are all present while its declared solver log
is absent (deleted after the run, or never copied back) is recorded
`RAN_MISSING_LOG` by `collect`, the grouped collect and `rebuild`, instead of
waiting for the log or failing as `FAILED_EXECUTION`. The record's
`residual_note` names what only the log carries (the residual history, the
convergence verdict, the frozen-point reading, the solver clock and the
iteration count), `wall_time_s` is null and the point is never `CONVERGED`.
The post writes every product of such a point, with or without
`--check-frozen`, and `post.log` carries one WARNING per point. In a steady
job that lost only some point logs, only the affected points take the status,
and a grouped point that also has a wall-clock stop keeps `stopped_at`.

A reader of `runs.json` must accept the status. It is not a failure: a script
that counted only `CONVERGED` and `COMPLETED_MAX_ITER` as runs that ended
should count it too. `status` counts it among the runs that ended, apart from
`CONVERGED`, and `run --resume` does not run such a point again.

### Rebuilding grouped runs (FR-412)

`pyfs-matrix rebuild` rebuilds the records of grouped runs (`--batch`,
`--polar-sweep`): a batch point's script is compared at its batch folder, the
rebuilt record names its batch and its job, and a simulation still in its batch
folder is rebuilt from there and left `SUBMITTED` for `collect` to finish.
Every simulation it refuses is named with its reason and what to do, and the
summary ends with the counts rebuilt and refused.

### `mark-converged` records a person's verdict (FR-414)

```text
pyfs-matrix mark-converged --sims 2006 2007 --reason "residuals flat over the last revolution"
pyfs-matrix mark-converged --sims 2006 --points AL+020 --reason "..." --apply
```

It is the twin of `mark-failed`: it previews unless `--apply`, requires
`--reason`, copies `runs.json` to the archive first, and keeps under `marked`
the status each record had, the time, the reason and the verdict. A point
still `SUBMITTED`, one whose loads export is not on disk, a deleted
simulation and a point marked failed are refused by name. `show`,
`status --points`, `post.log` and every `products.json` entry built from a
marked point name the verdict, and `rebuild` and `sync` keep it. From Python:
`pyflightstream.run.records.mark_converged`. A hand edit of `runs.json`, or a
separate script, that set `CONVERGED` loses the status the record had; use the
command instead. See [Restore and rebuild the run records](restore-and-rebuild.md).

## The matrix in the working directory (FR-411)

A bare matrix name or stem found in the workspace's root or in
`inputs/matrices/` is the matrix of every command, `rebuild` included. A file
of the same name in the working directory is no longer read and no longer
stops the command; when its bytes differ, a WARNING names both files and says
the workspace's was read. To read the other file, name it with its folder, for
example by its absolute path. The same stem in both workspace homes with
different bytes is still refused. See
[Sync every folder, and the two matrix homes](sync-folders-and-matrix-homes.md).

## `[[prune_step_exports]]` keys (FR-416)

A `[[prune_step_exports]]` table of a `free-space` recipe accepts `sims`,
`status`, and either `keep_last = K` (keep the last `K` steps of each per-step
export) or `delete_steps = [A, B]` (delete the steps `A` to `B` inclusive),
never both. Any other key is now refused before any file is touched, naming
the key and the accepted ones; a recipe carrying a key the mode never read (for
example `older_than_days`) must drop it. A table that states neither
`keep_last` nor `delete_steps` deletes and records exactly what it did in
0.36.0. See [Storage and sync](storage-and-sync.md).

## The installed-frame copy (FR-420)

`to_installed_frame` and the new `[products] installed_frame` copies read one
classification, which now also negates the `Y` position, the `VY` velocity and
the x and z components of a vorticity (`VORTICITY_X`, `VORTICITY_Z`), and no
longer negates a `CREF` column, which the roll pattern `CR[A-Z]*` matched by
mistake. A copy written by 0.36.0 from a table carrying either kind of column
differs from the one written now. See
[The installed-frame copy of a product table](definitions/the-installed-frame-copy-of-a-product-table.md).

## FlightStream 26.125 (FR-423)

26.125 is a registered build, named `26.125`: the vendor name it prints is
shared by its whole family, so resolution refuses that name and lists the
family. It is ordered after 26.124, and its manual edition backs a row for
every command it documents. The probe campaign of the release verified 141 of its commands on
the build, so `pyflightstream.support_table()` lists it at level
`operational`. To run on it, add its executable to the machine's executables
configuration under `26.125`. Nothing changes for 26.124
and earlier: every script, record and product of another build is
byte-identical.

What differs on 26.125:

- **Identity.** The log and every loads export name the build as
  `Simcenter Flightstream 2612, build #10052026`, where 26.124 printed release
  26.1 at build 8172026. Every export title that read `FlightStream <kind>`
  reads `Simcenter Flightstream <kind>`. The readers accept both forms, and a
  recorded 26.124 export reads as before.
- **The drag split, under its printed names.** The 26.125 loads export prints
  `CDp, CDv` (pressure drag; viscous and separation drag) where earlier builds
  printed `CDi, CDo` (induced drag; skin friction drag). The parsed loads
  report and the loads series keep the names the export printed. The polar
  never reads one pair as the other: a 26.125 point writes `CDV` where an
  earlier point writes `CD0`, and `CDP` where it writes `CDI`. A table whose
  points all ran on one build carries that build's pair, and a table holding
  points of both builds carries `CD0, CDI, CDV, CDP`, `NA` under the pair a
  point's export did not print. The force-plot parameters `CDP` and `CDV` are
  accepted. The declined induced drag rule reads `CDi` only, so a 26.125 point
  declines nothing. See
  [The drag split of 26.125](definitions/the-axes-of-a-steady-polar.md).
- **The forms its manual documents.** A raw mesh's `detect = "auto"`
  detections and the minimal workflow write the every-boundary (`-1`) form of
  `DETECT_TRAILING_EDGES_BY_SURFACE`, `DETECT_BASE_REGIONS_BY_SURFACE` and
  `DETECT_WAKE_TERMINATION_NODES_BY_SURFACE`; the wake-edge import writes
  `EDGE_TYPE` `1` as its third token; the CCS curve route assigns the selected
  curves to the component.
- **Commands it no longer documents.** `AUTO_DETECT_TRAILING_EDGES`,
  `AUTO_DETECT_BASE_REGIONS`, `AUTO_DETECT_WAKE_TERMINATION_NODES` and
  `SOLVER_TIME_AVERAGING` have no 26.125 row, so a script for 26.125 that
  emits them, through `Script.emit` or a row's `RAW` column, is refused; the
  workflows write the forms above instead.
- **Recorded broken on 26.125.** `CREATE_FREE_SURFACE_TFI_MESH` and
  `NEW_OFF_BODY_STREAMLINE` failed on the documented form in the probe
  campaign; no run type writes either, and the emitter refuses both.
- **Arguments 26.125 requires.** `DIRECTION` of the relaxed CCS trailing edges
  (`NEW_CCS_FUSELAGE_RELAXED_TE`, `NEW_CCS_REVOLVE_RELAXED_TE`), and `SPACE`
  and `AXIS` of the flap cove and the morphing surface
  (`NEW_CCS_WING_FLAP_COVE`, `NEW_CCS_WING_MORPHING_SURFACE`) are required on
  26.125, and the revolve CCS export (`EXPORT_REVOLVE_CCS_FILE`) takes the
  revolve loft's arguments.
- **Refused on 26.125, admitted on 26.124 only.** Normal probes on an unsteady
  row (`kind = "normal"`, FR-417) and the additional post. Direct mesh
  morphing (FR-341) is the reverse: refused on 26.124, whose build does not run
  the command.
- **New commands.** Twelve commands the 26.125 manual documents first enter the
  command database, each with a probe specification, and reach a workspace as
  the keys below or through a row's `RAW` column.

## New keys

Each key below is optional; a row, setup or pproc that does not state it is
unchanged.

| key | where | what it does | requirement |
|---|---|---|---|
| `RUN_WAKE_LENGTH_R: <L>` | `unsteady_rotor` row, with `DELTA_THETA` or `DELTA_TIME` | the run length from a target wake length in rotor radii; `plan` prints and `plan.json` records the resolved steps | FR-422 |
| `EXPORT_UNSTEADY_LAST_REV: <turns>` | `unsteady_rotor` row | the per-step exports cover the last revolutions | FR-415 |
| `EXPORT_UNSTEADY_LAST_ITER: <steps>` | `unsteady` or `unsteady_rotor` row | the per-step exports cover the last steps | FR-415 |
| `kind = "unsteady"` or `"normal"` | pproc `[[probes]]` entry | normal probes are created after the march and exported once; admitted on 26.124 only | FR-417 |
| `reusable_inflow`, `field_formats` on a normal entry | pproc `[[probes]]` entry of an unsteady row | the field products at the run's last time step | FR-418 |
| `keep_last`, `delete_steps` | `[[prune_step_exports]]` of a `free-space` recipe | which steps are kept | FR-416 |
| `settings_codebook` | pproc `[products]`, true by default | the settings table and its codebook | FR-419 |
| `installed_frame` | pproc `[products]`, a list of `probes` and `inflow` | copies mirrored through `y = 0` | FR-420 |
| `morphing = "direct"` | FSI input `[config]` | couples a `qsteady_rotor` sector by direct mesh morphing on 26.125 | FR-341 |
| `solver_time_averaging = [first, last]` | setup, unsteady rows | `ENABLE_SOLVER_TIME_AVERAGING` (26.125) | FR-423 |
| `aeroelastic_convergence_threshold` | setup | `SET_AEROELASTIC_CONVERGENCE_THRESHOLD` (26.125) | FR-423 |
| `te_blend_length_pct`, trailing edge `ROUNDED_BLEND` | `[import.ccs]` | `SET_CCS_TE_BLEND_LENGTH` (26.125) | FR-423 |

Two of the four per-step export keys (`EXPORT_UNSTEADY_AFTER_REV`,
`EXPORT_UNSTEADY_AFTER_ITER`, `EXPORT_UNSTEADY_LAST_REV`,
`EXPORT_UNSTEADY_LAST_ITER`) on one row are refused at plan, naming both. An
unsteady row whose pproc mixes normal and unsteady probe entries is refused,
naming the entries of each kind.

The direct morphing route and its refusals are in
[FSI workspace inputs](fsi-workspace.md); normal probes in
[The post-processing artifact and its products](pproc-artifact.md); the run length and the export window
in [The unsteady rotor workflow](workflow-unsteady-rotor.md).
