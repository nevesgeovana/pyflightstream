# Migrating to 0.25.0

This release stops publishing averages of a frozen solve, changes where an
unsteady probe gets its samples, and adds sections and Cp files named by
distribution. Read this before upgrading a workspace recorded with 0.24.0.

**Post a recorded campaign again, with no solver:**

```
pyfs-matrix post --workspace <root>
```

0.25.0 reads runs recorded with 0.24.0 without rewriting their records. Each
product is written or skipped with its reason in `products.json`. Posting again
can use only the evidence the run kept: missing probe histories, plot names and
section identities are named below where a NEW run is needed.

---

## 1. What posting again changes

### A frozen unsteady solve is a failure

A point whose averaging window touches a frozen step had no solution to average.
Re-posting such a record with 0.25.0 leaves that average out with the reason
recorded in `products.json`, even if 0.24.0 recorded the point as a success.
The unsteady polar row, rotor table and reductions follow this rule; an earlier
post's stale file is archived.

The native log identifies the freeze: at least two consecutive time steps whose
inner iterations after the first all print exactly zero velocity residual and
whose last inner iteration prints both residuals exactly zero. Assessment records
`FAILED_DIVERGED`, naming the first frozen step and the count. Post reads the log
again and excludes an average whose window ends at or after that first step.
Windows ending before it, raw histories and explicitly instant products remain
available. A new solve is needed to obtain a solution over the frozen stretch;
posting again cannot repair it.

### `ADVANCE_RATIO` in the unsteady polar

An unsteady polar of an `ADVANCE_RATIO` sweep now states the point's `J` under
`ADVANCE_RATIO` on every row. It wrote `NA` in that column before. Post again to
recover the swept axis from the recorded point.

### A rotor table that cannot be planned says why

If a simulation's matrix row was deleted, or its reference no longer resolves,
the rotor table is a named skip at `polars/<sim>#rotor_tables` in `products.json`.
It previously disappeared. Restore the matrix row or repair its reference and
post again.

### Skip reasons survive when no point has usable loads

When no point of a simulation has usable loads, its per-point reasons now reach
`products.json`. They were collected and then lost. Re-post to see which points
were left out and why; an empty simulation is no longer an unexplained absence.

### A rotor table from a family-templated group needs recorded plot names

A group named with `{family}` can supply the unsteady rotor table. A new run
records the plot names it emitted, with their frames, families and parameters.
Post sums an exact, non-overlapping set of recorded groups in the global `MRP`
frame covering all of the rotor's families, including any general families.

A run recorded before 0.25.0 lacks that emitted-group record and keeps the named
skip for this source. Editing the pproc cannot recover those plot names and
their meaning; a new run supplies the record.

---

## 2. The probe source follows the run type

### Every unsteady probe is a fluid plot

On an unsteady row, every `[[probes]]` entry uses fluid plots, whether it draws
a line or cites a `points_file`. Each point and requested parameter is sampled
through the history. A pproc mixing the two forms now yields ONE
`probes/<point>_probes.csv` table, with one row per point and solver step.
The probe-points instant export no longer supplies an unsteady probes table.

The cited profile is read at plan: a count followed by `X,Y,Z,TYPE` CSV rows,
with type 0 or 1. Both types supply fixed vertices to fluid plots, using the
entry's frame, scale and parameters. Invalid counts, coordinates or types are
refused before solving. The script no longer imports or exports standard probe
points for an unsteady row, and its default outputs lose `{name}_probes.txt`
(seven outputs instead of eight).

### A cited profile recorded as an instant has no history

An unsteady run recorded before 0.25.0 whose cited-profile probes were exported
as an instant has no history for them. Posting again leaves those probes out,
names the profile and reason in `products.json`, and keeps the drawn-line
histories the same run did record. **A new run is needed for the cited profiles'
history.** An instant cannot be turned into one by re-posting.

### A steady probe's `parameters` list only enables the entry

On a steady row, drawn probes and `points_file` profiles still use the standard
probe-points export. A nonempty `parameters` list enables the entry; an empty
one disables it. It does not filter the variables, because that export has a
fixed set. `pyfs-matrix plan` now warns for each enabled steady entry, naming
its entry number and frame. Select columns in the resulting table if a reader
needs fewer variables. On an unsteady row, the list selects the fluid-plot
variables that are sampled.

---

## 3. New surface exports and settings

### `SOLVER_TIME_AVERAGING` from the pproc

The pproc can request a time-averaged native surface export:

```toml
[time_averaging]
last_revs = 1.5 # OR last_iters = 54; exactly one, positive
```

**Time-averaged surfaces cannot be produced on the builds measured so far.**
Licensed C01 on 2026-09-19 found that `SOLVER_TIME_AVERAGING` hangs FlightStream
26.124, both before and after `INITIALIZE_SOLVER`, without writing any output
before termination at 300 seconds. The same script without that command wrote
all seven outputs and its final log export, exiting successfully in 126 seconds.

The package now refuses `[time_averaging]` at plan time, naming the build and
the dated measurement, rather than hanging the solver. **Remove this table to
run on these builds.** Tecplot, VTK and CSV surfaces are then written as
**instants**, including any requested per-step exports; the plots-history
averages remain available through the matrix's reduction window.

The key, its validation, window resolver and recorded provenance remain.
Only a build whose command-database status is `verified` may emit
`SOLVER_TIME_AVERAGING ENABLE <first> <last>` in initialisation. Documentation
alone (from 26.122) does not establish that it runs; earlier builds remain
unsupported. Without the table, no averaging command is emitted.

The resolver uses inclusive, 1-based time-step bounds ending at the run's last
step. `last_iters` counts steps; `last_revs` uses the same rotor clock and
rounding as `LAST_REVS_AVG`. A window longer than the run is clipped at step 1.
The manual does not settle time steps against inner iterations: **this solver
interpretation remains unverified because the C01 hang prevented measurement
of the bounds.** The export header's inner-iteration count is not the clock.

The run records the window it emitted. Surface entries in `products.json` and
PROV-JSON state `kind: average` and that window, even if the pproc is edited
later. Per-step exports and stopped runs end the window at the available step;
exports before the averaging start are named skips. Without the table, the
entries state `kind: instant`.

**Changing this window needs a new run.** It asks the solver for a different
surface export. The matrix's `LAST_REVS_AVG` or `LAST_ITERS_AVG` window remains
the separate post-processing choice for reductions of the plots history.

### Surface flow in VTK and CSV, off by default

Two new `[exports]` kinds request native surface flow. `vtk_variables` is a
top-level pproc key, before the tables:

```toml
vtk_variables = ["X", "Y", "Z", "CP_FREESTREAM"] # optional

[exports]
vtk = true
csv = true
```

VTK uses `EXPORT_SOLVER_ANALYSIS_VTK` and, with the list,
`SET_VTK_EXPORT_VARIABLES`; without it, the all-variables form is used. CSV
uses `EXPORT_SOLVER_ANALYSIS_CSV`, exporting `CP-FREESTREAM`, `PASCALS`, all
surfaces, in the solver reference frame. Both exclude the wake. Variables and
commands are checked against the selected build's committed command database;
an unavailable one is refused at plan, naming the build.

Both join the per-step exports of `EXPORT_UNSTEADY_AFTER_REV` or
`EXPORT_UNSTEADY_AFTER_ITER`. They are instants on the builds measured so far;
a surface average requires `[time_averaging]` on a build verified to run that
command. Enable the exports and run again to obtain files a previous run did
not export. VTK, CSV and the per-step export program completed successfully
on 26.124 in licensed C01 on 2026-09-19.

### Fourteen setup keys replace the need for `[[raw]]`

These advanced settings now have setup keys of their own:

| setup key | setup key |
|---|---|
| `laminar_separation` | `kutta_joukowski_lift` |
| `aeroelastic_rbf_type` | `print_rotor_induced_velocities` |
| `adaptive_field_grid_refinement` | `rotor_induced_velocity_blending` |
| `wake_numerical_relaxation` | `wake_relaxation` |
| `wake_decay_constant_per_m` | `wake_streamwise_agglomeration` |
| `jet_wake_decay_normalized_length` | `jet_wake_filaments_grid_induction` |
| `adverse_gradient_boundary_layer` | `vortex_ring_normalization` |

Each emits its command only when set; absent keys leave an existing setup's
script unchanged. `[[raw]]` still works. Unknown keys and values or commands
the selected build does not carry are refused, naming the build. Use a setup
key for a setting previously expressed as a raw command, then plan again.

### Boundary-layer fluid-plot parameters, by build

An unsteady probe's `parameters` can now include `BL_MOMENTUM_THICKNESS`,
`BL_DISPLACEMENT_THICKNESS`, `BL_TOTAL_THICKNESS`, `BL_SHAPE_FACTOR`,
`BL_SKIN_FRICTION` and `BL_TRANSITION_MARKER` on builds whose database
documents them: 26.122, 26.123 and 26.124. Previously the pproc vocabulary
refused them on every build. An unsupported parameter is refused naming both
the parameter and the build. A new run is needed to sample a newly requested
variable; changing the list cannot add samples to an existing history.

### What `NITER` limits on an unsteady run is still an open question

Whether `NITER` and the setup's `convergence_iterations` limit inner iterations
per time step or the total across an unsteady run remains to be measured.
**The licensed verification of this release measures it with a short run and a
low limit.** No measurement is recorded under `reports/pfs0250/` in this tree,
so this page does not claim either interpretation as a licensed result.

The export header's `Current solver iteration number` does count INNER
iterations: the recorded 0.24.0 measurement had 2813 inner iterations over
144 time steps. That observation does not answer what `NITER` limits. Do not
use that header as a time-step count or as evidence of a per-step limit.

---

## 4. Output formats changed in this pre-1.0 release

Update readers that assume a fixed list of post-stage files. The new tables
are one sectional-loads file and one Cp file per distribution:

| new file | content |
|---|---|
| `sections/<point>_sloads_<name>.csv` | sectional loads of one distribution |
| `sections/<point>_cp_<name>.csv` | Cp at every chordwise station of that distribution |

`<name>` is the distribution's alias or its families joined with `-`, not the
expanded blade names. Filename-invalid characters become `_`; colliding names
receive the entry's 1-based position as a suffix. All planes and blade blocks
of one distribution share its file. With per-step exports enabled, each file
holds EVERY available exported step in ascending `STEP` order; without them,
it holds the end-of-run export. Cp was only listed in the manifest before.

Rows lead with `STEP, time_s, FAMILY, PLANE, ROTOR, AZIMUTH`, then the condition
block and export columns. Cp also carries `SECTION`, the export's 1-based
cross-section index. Missing values are `NA`. The combined
`sections/<point>_sections.csv` and `series/<point>_sections_series.csv` remain
available. The [definitions page](post-processing-definitions.md) lists the
columns of each new table.

`products.json` records `distribution`, the original `families` selection and
`steps_tabled` for each split file. Missing exports or steps, empty Cp
distributions and malformed exports are named skips. Read the manifest to
distinguish unavailable data from a distribution that was never requested.

### A record that does not identify its distributions is not split by guess

New runs record each section block's distribution entry and original families
selection. A 0.24.0 run can be split when its recorded layout and pproc identify
each block unambiguously by families, plane, frame and count. Editing today's
pproc cannot reassign the recorded blocks.

Without that evidence, the split files are a named skip in `products.json`
instead of a guessed split. A layout whose counts disagree with an export is
also refused for that export kind. **A new run is needed when the record does
not identify its section distributions.** Posting again cannot reconstruct
an identity that was never recorded.

---

## 5. Earlier refusals and the manifest lock

### An input artifact that exists and does not validate says so first

A row citing an invalid reference, setup or pproc now says
`the <kind> artifact at <path> does not validate`, followed by its validation
errors. The advice to put an artifact at that path is reserved for a file that
does not exist. Fix the stated validation errors and plan again.

### A `[names]` target cannot take a context column's heading

A target colliding with a context column such as `ALPHA` or `MACH`, or with
a window or reference heading, `REDUCTION` or `ROTOR`, is refused when the
pproc is read. Previously the collision was found at write time and the
product was dropped. Choose a distinct target name and plan again.

### A live writer keeps its manifest lock

The lock records its process, host and owner token. A live writer renews it
every 5 seconds; a waiter no longer takes it merely because 30 seconds have
passed. Takeover requires that the owner's process is gone on this host or
that its heartbeat is older than 300 seconds. A release removes only the lock
its releaser owns.

**Do not run 0.24.0 and 0.25.0 writers against one workspace at once.** Older
writers do not follow this protocol. Finish the old writer before upgrading.

---

## 6. Python callers: moved modules and deprecations

`write_sections_table(iteration=)` is now `write_sections_table(step=)`.
The old keyword still works with a deprecation warning and is removed in
0.26.0. Passing both is refused with `ProductArgumentError`, a catalogued
`TypeError` that is also caught by `PyflightstreamError`.

`run.assess_unsteady_from_plots` is deprecated and is also removed in 0.26.0.
It still returns what it returned. Use `LoadsAssessor` for campaign assessment
of native loads and solver residuals; whether the history has settled remains
a separate judgement made from that history.

`post.provenance` and `post.custom_polar` are now separate public modules.
Existing imports from `post.products` keep their spellings. The new
`post.section_distributions` module writes the per-distribution tables.
