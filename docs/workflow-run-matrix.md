# The run matrix, a campaign and its record

What a run matrix is, how its points are named and redone, how several matrices share a workspace, and what comes back. The other pages of the [workflows section](workspace-and-workflows.md) each take one run type or one topic.

## What a run matrix is

A run matrix is a pipe-separated table, one row per simulation, that
this package reads forever: the format is a first-class interface
rather than an import step (FR-10, FR-35). Each row names a point of
interest, the sweep it wants, and, by identifier, the reference, the
solver preset and the boundary group it should be resolved against.

This is the matrix the test suite runs, byte for byte:

```text title="matrix_registry.fs"
POL  | HIDDEN | RUN | AIRCRAFT  | CONFIGURATION | DESCRIPTION            | FLIGHT_CONDITION | SWEEP_VALUES   | GEOMETRY | REF  | SET  | PPROC  | SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
8001 |    0   |  1  | TestWing  | -             | REGISTRY_ALPHA         | MACH:0.0890, REmi:3.10, ALPHA:sweep | 0.0,2.0        | -        | r003 | s002 | p001   | -        | -              | -     | -        | 26.120   | LEGACY   | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt / RECIPE: 003
8002 |    1   |  1  | TestWing  | -             | REGISTRY_BETA          | MACH:0.0890, REmi:3.10, BETA:sweep | -3.0,3.0       | -        | r003 | s002 | p001   | -        | -              | -     | -        | 26.120   | LEGACY   | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt / RECIPE: 003
```

Read one row across. `POL` is the point of interest, and it becomes the
simulation identifier (`sim_8001`). `FLIGHT_CONDITION` states the flow
condition the row runs at, as comma-separated `KEY:value` pairs from a
closed set; it is MANDATORY, and it replaced the `RE` and `MACH` columns
at v0.9.0. What it means and which quantity gets solved for is
[its own page](flight-conditions.md). The same cell says WHAT VARIES,
and `SWEEP_VALUES` says over which values: `ALPHA:sweep` with `0.0,2.0`
is an angle-of-attack sweep at zero and two degrees, so this one row is
two runs. Exactly one key of the cell may carry the word `sweep`; every
other key is a quantity the row HOLDS. `pyfs-matrix upgrade` folds a legacy `SWEEP_TYPE` column into this cell. `REF`, `SET` and `PPROC` are the
three identifiers that reach into the input library; `PPROC` names the post-processing artifact (PFS-2029.07). `FS_BUILD` names the FlightStream
build the row wants. `WORKFLOW` names the run type, and a row naming one
needs nothing else to build its script; `LEGACY` means "none, use the
recipe", as these two example rows declare, and such a row names its recipe code as the `RECIPE`
key of its variables (`pyfs-matrix upgrade` moves a legacy `FS_SCRIPT` column here). The cell may
carry the reference itself, `package.module:function`, and a row written so
plans and runs with no `--recipe` option at all; a bare code such as `003`
is still mapped by that option (PFS-2031.11). A `LEGACY` row's recipe also
decides what it saves: these two rows declare a loads table and no `.fsm`,
so `pyfs-matrix plan` warns, naming both, that no final saved
simulation of theirs is collected, and plans them as before
(`test_g11_a_legacy_row_without_a_saved_simulation_is_warned_at_plan`). `HIDDEN` and
`RUN` sit directly after `POL`; `RUN` is the switch that says
whether the row takes part at all, and `HIDDEN` whether the solver shows a
window.

**SIX COLUMNS ARRIVED AT v0.17.0** and each of them was expressible before,
four as keys inside `VAR_NAMES_VALUES` and two inside the setup artifact.
`CONFIGURATION` is your own name for what is in the wind, beside
`AIRCRAFT`; it labels and configures nothing, and it reaches two places you
open: the first line of the emitted script, as a comment, and the title line
of the custom polar file after ` - `.
`GEOMETRY` names the mesh file. `SYMMETRY` says what was MESHED, a mirrored
half or a periodic sector. `SYMMETRY_LOADS` says whether the loads that
come back are the whole aircraft's or the modelled slice's. `NCPUS` is the
processor count, ONE number that reaches the solver's thread count and, on
a cluster, the scheduler's request. `WALLTIME` is the wall clock, written
WITH ITS UNIT (`240m`, `4h`, `90s`, `1d`; a bare number is
refused by name), which on an unsteady row also arms the watchdog. What the
scheduler's own field is given is the HPC profile's to say
(`walltime_arithmetic`), and it never moves the watchdog's deadline.

**A COLUMN SAYS NOTHING WITH `-`.** One character rather than an empty
cell, so a reader can tell "states nothing" from "the line is truncated".
Where one of the six says nothing, the older home still answers: `NCPUS`
falls back to the cited setup's `max_parallel_threads` and
`SYMMETRY_LOADS` to its `symmetry_loads`, so a matrix upgraded from an
older layout behaves exactly as it did.

**`-` IS NOT THE SAME AS SAYING "NONE".** There is one case where the two
part company and it is worth knowing before you meet it: a row that opens
NO geometry cannot say so in the `GEOMETRY` column, because `-` there means
"states nothing, take the default". It says it with an empty-valued
`GEOMETRY:` key in `VAR_NAMES_VALUES`, and the upgrade leaves such a key
where it found it for exactly that reason.

**A FACT MAY NOT BE STATED IN BOTH HOMES.** A row that puts one of the six
in its column AND as a key of the free cell is refused naming both, because
two homes for one fact is how the two come to disagree.

`VAR_NAMES_VALUES` is the last cell and the one that carries everything
else, as `KEY: value` pairs separated by ` / `. The rows above use
`FSM_FILE`, which is a key of THEIR OWN: nothing in the package reads it,
and the recipe named by the row's `RECIPE` code is what resolves it and
opens the file. That is still how a recipe works.

**A WORKFLOW reads keys the package defines**, and three of
them close the gap that made the capability unusable:

* `GEOMETRY: <file name>` names a geometry staged under
  `inputs/geometries/` by its FILE NAME, extension included: with
  `wing_clean.fsm` staged, the cell reads `GEOMETRY: wing_clean.fsm`, and
  `blade.v2.fsm` reads one way and no other. A bare stem is refused
  naming the files that carry it, and `pyfs-matrix upgrade` completes
  every stem-only cell of an older matrix with `.fsm` (PFS-2029.09). What the name buys is that the cell
  says what the file is: a `.fsm` is a saved simulation and is opened,
  and an `.obj` or `.stl` is a raw mesh and is imported.
  The workflow opens or imports the file first, before anything else,
  and it reads the STAGED copy, so the file the manifest hashed and the
  file the solver read are the same bytes.

    A WORKFLOW opens a `.fsm` and imports an `.obj` or `.stl`, and
    refuses any other suffix. A raw mesh takes its length units as an
    argument (SRC-003 p.307) and the file carries none, so the
    `<stem>.boundaries.toml` beside it states them in an `[import]`
    table, `units = "MILLIMETER"`, beside the `boundaries` list: for an
    `.obj` with no sidecar the plan writes that list from the file's
    groups, in the order the solver numbers them (G30), and
    for an `.stl` it is written by hand. A raw mesh without the table is
    refused before any seat is spent, naming the key, because a defaulted
    unit is a body of the wrong size whose coefficients solve, export and
    report without a word. The file's unit goes to `IMPORT` alone and the
    simulation is set to metres, the unit of every length the row states.
    The same sidecar declares the mesh's trailing edge in a
    `[trailing_edges]` table (G02): `file = "<points
    file>"`, the default route, whose edge mid-points are checked against
    the mesh at plan and imported with `IMPORT_WAKE_EDGES_FROM_FILE` on
    26.124, or `detect = "auto"` (or by surface), detection, which applies
    only when written; `[wake_termination]` and `[base_regions]` detect
    when written. A raw mesh that declares no trailing edge is refused
    before any seat is spent, since without one there is no wake and the
    solver answers anyway, and a `.fsm` whose sidecar states any of the
    three tables is refused, since its own marking is in the file.
    [Mesh inputs and GUI-only operations](mesh-inputs.md) carries the
    route in full. A recipe of your own receives whatever the library
    staged and imports it declaring the units itself.
* `SYMMETRY: <mode>` and, where the mode needs it, `PERIODIC_COPIES: <n>`.
  The accepted modes are read from the command database for the row's own
  build, never from a list written here. **This one is not a
  convenience.** A periodic sector requires periodic symmetry; treating it as `NONE` solves a one-bladed rotor without diagnosing the physical error.

    `MIRROR` carries three cautions, and the cell enforces
    one of them: a nonzero sideslip (a swept or held `BETA` in the flight
    condition) under `SYMMETRY: MIRROR` is refused at plan time, naming the
    cell, because a mirrored half model is a valid model of the full one
    only while the free stream lies in the symmetry plane, and the solver
    was measured (26.120, 2026-09-09) running such a point at zero
    sideslip whatever the script states, saying so only in its log. Sweep
    the sideslip on a full geometry with `SYMMETRY: NONE`. The other two
    the cell cannot enforce. The mode
    describes what you MESHED, so a row declaring it must have staged the
    half model; initializing a mirrored solution with the full model
    loaded diverges immediately, because the model is then its own mirror
    image (SRC-003 p.217). Whether the loads are the full model's or the
    half's is the row's `SYMMETRY_LOADS` column (FR-66), emitted as
    `SET_ANALYSIS_SYMMETRY_LOADS`; where the row says `-` the setup's
    `symmetry_loads` answers, and where neither does the run takes the
    solver's own default, calibrated as ENABLE on a licensed 26.120 and
    measured on that one build only.

## How a point is named

Every export hangs off the point's NAME. The name writes
every variable the row's `FLIGHT_CONDITION` declares, in the order the cell
declares them, each as a code and a fixed-width integer so a folder of them
sorts:

| Key | Code | Written as |
|---|---|---|
| `MACH` | `M` | Mach × 1000, 3 digits |
| `TASmps` | `V` | m/s × 10, 4 digits |
| `REmi` | `RE` | millions × 100, 3 digits |
| `ALTFT` | `ALT` | ft, 5 digits |
| `dISA` | `DT` | K × 10, 4 digits, signed |
| `RHOkgm3` | `RHO` | kg/m³ × 10⁴, 5 digits |
| `MUPas` | `MU` | Pa·s × 10⁹, 5 digits |
| `ASMPS` | `A` | m/s × 10, 4 digits |
| `TK` | `T` | K × 10, 4 digits |
| `PPA` | `PS` | Pa, 6 digits |
| `ALPHA`, `BETA` | `AL`, `BE` | deg × 10, 4 digits, signed |
| `ADVANCE_RATIO` | `J` | × 100, 4 digits, signed |
| `RPM` | `RPM` | rev/min, 5 digits, signed |
| `roll_rate`, `pitch_rate`, `yaw_rate` | `P`, `Q`, `R` | deg/s × 10, 4 digits, signed |

A row whose cell reads `MACH:0.144, REmi:4.38, ALPHA:0, BETA:0,
ADVANCE_RATIO:sweep` names its point at J 0.8 `M144RE438AL+000BE+000J+080`.
The name ends the `run_id`, names the datapoint folder `DP-<name>`, and is
the stem of every file of the point: `P<sim>-<name>`, so that point's script
in simulation 9001 is `P9001-M144RE438AL+000BE+000J+080.txt` and its exports
are `..._cp.txt`, `..._log.txt` and the rest. `pyfs-matrix plan` and `run`
name points this way unless `--point-name` gives another template; the
placeholders are `{polar}` (`P<sim>-<name>`), `{point}` (the name),
`{alpha}`, `{beta}`, `{mach}`, `{advance_ratio}`, `{sim}` and `{campaign}`,
and inside an output name `{name}` is the rendered stem. The run record
carries the name (`point_name`), the name of its sweep (`sweep_name`) and
the template that named each point (`point_name_template`). A workspace may carry the old names; `pyfs-matrix rename` renames
it, as [migrating to 0.21.0](migrating-to-0.21.0.md) describes.

## Several matrices in one workspace

One workspace may hold several matrices, each a study of its own over the
same input library: a tour, a setup study, a time-convergence study. The
rule that keeps them apart is one folder per matrix (PFS-2031.04): `plan`
writes `post/<stem>/plan.json`, `run` writes
`post/<stem>/campaign_sweep.csv` ONCE (FR-90: the two names were the same
bytes twice), and the products of that matrix's points
land beside them. `runs.json` stays the one manifest of the workspace, and
every record in it names the matrix its point came from, so the sweep table
and the products of one matrix are rebuilt from its own records alone. From
Python the same identity is the `matrix_stem` keyword of `sweep_table` and
`write_campaign_products`, and the `matrix_stem` field of a run record.

What no two rows of one workspace may share is a POL, in one matrix or in two.
A POL names the simulation folder `sims/sim_<POL>` and the run ids of the
manifest, so two rows stating one POL would write into one folder and a resume
of either would find the other's points already recorded. Before anything
binds, `plan` and `run` read every `*.fs` in the workspace root and the matrix
being planned, wherever it is, EVERY ROW OF EACH, including rows with RUN = 0,
because a row switched off today is switched on tomorrow and its POL already
names a folder. One message names every repeated POL and every row stating it:

```text
matrix not planned: 2 POL(s) are stated more than once across the matrices of
this workspace, RUN = 0 rows included: POL 1001 in matriz.fs row 1,
matriz_setup.fs row 3; POL 1004 in matriz.fs row 4, matriz.fs row 6. A POL names
the simulation folder sims/sim_<POL> and the run ids of the one manifest,
runs.json, so each POL is stated once in the whole workspace. POL(s) 1001, 1004:
renumber by hand, or run `pyfs-matrix plan matriz.fs --update-ids`, which gives
each repeated row of matriz.fs the next free POL and leaves every other matrix as
it is.
```

A repeat that sits only between two OTHER matrices is named with its own
remedy in the same message, because `--update-ids` on the matrix being planned
cannot move it.

`pyfs-matrix plan <matrix> --update-ids` (also accepted as `--updateIDs`) rewrites
THAT MATRIX before planning it. A row keeps its POL unless another matrix
already states it or an earlier row of the same file does; each row that must
move takes the next free number above every POL of every matrix, every run in
`runs.json` and every `sims/sim_<id>` folder, so a new POL never lands on the
evidence of a study whose matrix has been removed. Only the POL cells change,
each change is printed, and the plan then runs on the rewritten file:

```text
pyfs-matrix plan matriz.fs --update-ids ...
--update-ids: matriz.fs row 6: POL 1004 -> 2013
```

Inside one matrix the FIRST row stating a POL keeps it and every later row
moves, including when that POL already has runs in `runs.json`: a run record
names the POL and not the row, and the first row is taken as the one that ran.
A row whose POL another matrix also states, and which already has runs of
THIS matrix, is refused rather than moved, and nothing is written; renumber the
other matrix instead, or archive the simulation first.

THE RENUMBERING IS WRITTEN BEFORE THE PLAN RUNS, so the receipt the plan writes
is pinned to the file as renumbered. If the plan then refuses for another
reason, the renumbering stays written, and the command says so beside the
refusal. From Python the same step is
`pyflightstream.workspace.matrix.renumber_repeated_pols(path, workspace)`.

The tier-3 workspace of this repository, `tests/tier3_licensed`, is the
worked example: eleven matrices, one library, one manifest, and POLs no two
matrices share.

## Worked rows, and where to get the files

Every row below is a real row of `tests/tier3_licensed/matriz_vocab.fs`,
rendered to a script on every commit by
`python -m tests.tier3_licensed.offline` and compared against a committed
golden by `tests/tier1_offline/test_tier3_offline.py`. They are not
sketches: copy the workspace at `tests/tier3_licensed/inputs/` and these
rows plan as they stand. The geometry they open, `41_TWIN.fsm`, is
synthetic, generated by a committed generator, with its provenance recorded
beside it.

The artifacts they name are worth reading in this order:
`inputs/references/r006.toml` (the lengths, the aliases, one block per
rotor), `inputs/setups/s002.toml` (how the solver runs) and
`inputs/pproc/p005.toml` (what gets written down). `r004.toml` and
`p003.toml` state the same aircraft in the vocabulary of 0.14.0, so the
migration can be diffed rather than described.

**A rotor named by alias.** The row says which rotor turns and how fast;
the hub, the axis, the sign, the blade families and the diameter are the
reference's, stated once in that rotor's block.

```
8001 | ... | r006 | s002 | p005 | ... | unsteady_rotor | GEOMETRY: 41_TWIN.fsm /
  SYMMETRY: NONE / DELTA_THETA: 30 / REVOLUTIONS: 0.5 / CLOCK_MOTION: PORT /
  MOTIONS: {MOVING_BC_ALIAS: PORT / RPM: 2400} / LAST_REVS_AVG: 1
```

**Two rotors, two speeds, from ONE advance ratio.** The ratio is written
once in the flight condition and reaches every motion that states no speed
of its own, resolving against each rotor's own `diameter_m`.

```
8002 | ... | MACH:0.1, REmi:2.3, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.6,0.8 |
  r006 | s002 | p005 | ... | CLOCK_MOTION: PORT /
  MOTIONS: {MOVING_BC_ALIAS: PORT}, {MOVING_BC_ALIAS: STARBOARD}
```

The rendered script for its first point,
`goldens/matriz_vocab/P8002-M100RE230AL+000BE+000J+060.txt`, emits
`SET_MOTION_ROTOR_RPM 1 930.3642` and `SET_MOTION_ROTOR_RPM 2 -1860.7283`:
twice the speed on the rotor of half the diameter, negative because that
block declares `rpm_sign = -1`.

**One rotor held while the other sweeps**, which is how a transition row is
written: a motion stating its own speed holds it against the condition's
ratio.

```
8003 | ... | ADVANCE_RATIO:sweep | 0.6,0.8 | ... |
  MOTIONS: {MOVING_BC_ALIAS: PORT}, {MOVING_BC_ALIAS: STARBOARD / RPM: 1800}
```

**Turning the mesh before the run.** A `ROTATE` record cites the ALIAS, and
every frame that alias owns turns with its boundaries; the frame it turned
FROM is kept as `<ALIAS>_SMRP_ORIGINAL`, and a post-processing entry naming
the turned frame is written in both.

```
8004 | ... | ROTATE: {ANGLE: 3 / AXIS: NACELLE-Y / ALIAS: STARBOARD}
```

**Raw solver commands the row states itself**, each before a named phase and
through the same emitter checks every curated line passes.

```
8005 | ... | RAW: {COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}
```

## From a filled-in matrix to results, in one call

<!-- skip: next -->
```python
from pyflightstream.run.matrix import run_matrix

records = run_matrix(
    "matrix_registry.fs",
    workspace,
    name="matrix",
    fs_version="26.120",
    recipes={"003": "steady"},
    assess=converged,
    executor=executor,
    recipe_registry={"steady": matrix_recipe},
)
```

Four arguments carry the study and the rest carry your machine.
`recipes` maps a LEGACY row's `RECIPE` code onto the name of a recipe,
`recipe_registry` maps that name onto the function that builds the
script, `assess` is what decides whether a finished run converged, and
`executor` is how a script is actually launched.

A **recipe** is an ordinary Python function taking the resolved case and
an empty script, and emitting into it. It is the only place your study's
physics decisions live:

<!-- skip: next -->
```python
def matrix_recipe(case, script):
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        aoa=case.point.get("alpha", 0.0),
        velocity=30.0,
        iterations=case.solver.iterations,
        convergence=case.solver.convergence,
    )
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    script.emit("CLOSE_FLIGHTSTREAM")
```

Note `case.solver.iterations`. Nothing in the recipe read
`inputs/setups/s002.toml`: the matrix said `SET s002` and the resolved
case arrived carrying 800 iterations and a convergence of 1e-6. The same
holds for `case.outputs[0]`, which is the workspace's rendered output
name for this point, not a literal the recipe chose. A recipe that
writes a literal file name is how two points of one campaign come to
overwrite each other.

## What comes back

`run_matrix` returns one record per JOB, and the same rows are on disk
in the workspace's manifest:

```text
matrix/sim_8001/sweep
matrix/sim_8002/sweep
```

Two rows of a matrix, four points, TWO records, because a
steady row is one job: its points run in one process, one after another.
Every point starts cold, including the first. Set
`COLD_START: false` to retain the previous warm behavior explicitly; see
[geometry units and steady starts](geometry-units-and-starts.md).
A run id that ends `sweep` names a job, and a run id that ends with a
point NAME names a point; the token is the one the per-polar product
tables already use for a swept variable, with the swept field written
`<code>+sweep`.

Every point is still there and still named. The record lists them in the
order the job ran them, with the status each ended in, and the sweep
table and the products are one row per point exactly as before:

<!-- skip: next -->
```python
for entry in record.points_ran:
    print(entry["tag"], entry["status"])
```

A point a recorded job ran is recorded, although no record carries its own
point name: `pyfs-matrix plan` reports it as already recorded and
`run --resume` skips it (`test_the_plan_reports_a_recorded_jobs_points_as_recorded`).
Angles added to such a row later run one each on resume, each its own record
ending with its point name, because the row's job id is taken
(`test_two_new_angles_of_a_recorded_job_are_recorded_one_each`); the plan
calls exactly those ready. To run the whole row again as one job, name the
job to `--force-rerun`, which archives it first.

An unsteady row is unchanged: a point that marches in time starts from
its own initial state, so it is its own job and its own record.

Each record carries its terminal status, and there is no missing state: a
point that did not finish says so rather than being absent.

## Redoing a point whose row was wrong

A point already in the manifest is refused, because re-running a recorded point
would fork the run identity. When the correction to the row does NOT change the
point's name -- a pproc, a geometry, a solver variable, a wall clock -- the
corrected point has the same identity, and `--force-rerun` is how it is redone:

```text
pyfs-matrix plan <matrix> --workspace .
pyfs-matrix run  <matrix> --workspace . \
    --force-rerun 'camp/sim_3207/M144RE438AL+000BE+000J+080'
```

Re-plan first: the plan carries the digest of the matrix it read, and an edited
matrix is refused until it is planned again.

It names points, by point name, by full `run_id`, or by the job id of a swept
row, and the flag repeats. Nothing is deleted: the manifest is copied to
`archive/runs-<stamp>.json` and each named point's outputs move into that
point's own `archive/<stamp>/`. A name no recorded point carries is refused, and
recorded points it does not name are skipped rather than refused. It cannot be
combined with `--resume`, which SKIPS a recorded point instead of redoing it.
Naming one point of a steady row recorded as one job redoes the whole job, and
the run says which points run again.

**To redo EVERY recorded point**, of the matrix or of some of its simulations,
name none of them:

```text
pyfs-matrix run <matrix> --workspace . --force-rerun-all
pyfs-matrix run <matrix> --workspace . --force-rerun-all --sims 2031 2032 2033
```

Each recorded point is archived as `--force-rerun` archives it and runs again, a
steady row recorded as one job as one job. Before anything runs, one line says
how many points and jobs will run again, which is the licences the command
spends. `--sims` takes the simulation ids as the matrix spells them and narrows
the whole run to them, so the other simulations are not touched, their new
points included. Refused beside `--resume` or `--force-rerun`, for an id the
matrix does not carry, and when nothing of the selection is recorded.

**To plan and run ONE simulation, or some of its points, without editing the
matrix**, select them on both commands:

```text
pyfs-matrix plan <matrix> --workspace . --sims 2031 --points M144RE438AL+040BE+000
pyfs-matrix run  <matrix> --workspace . --sims 2031 --points M144RE438AL+040BE+000
```

`--sims` takes simulation ids as the matrix spells them, and `--points` takes
the point names the plan prints, only beside `--sims`. Only the selection is
planned, staged and run: every other point keeps its record, and the matrix
file is not written. An id or a point the matrix does not carry is refused
before anything runs, naming the ones that exist. A selected point that is
already recorded follows the rules above (refused, `--resume`,
`--force-rerun`). Without `--force-rerun-all`, `--sims` alone runs those
simulations; in 0.33.0 that was refused.

**A second run of the same matrix without `--resume`** is refused, as before,
with exit status 2 and nothing run; the message says how many
points are recorded and how many would run, and prints the command you typed
with `--resume` added, ready to paste.

**A correction that DOES change the point's name needs none of this.** The name
is written by the row's `FLIGHT_CONDITION`, so correcting a value in that cell
gives the point a new identity: it is simply a new point, and `--resume` runs it
beside the old record.

Three things are refused, each by name and with
nothing written or deleted: a simulation the manifest does not record
(`refusing to archive sim_8001: the manifest has no record of this
simulation`), a campaign root without `runs.json`, and an archive name
already taken, since writing it would replace an earlier archive and
then delete the folder it came from. The Python surface is
`CampaignWorkspace.archive_sim`, and this command does the same thing
and nothing more; the suite runs the line above on a recorded
simulation and on an unrecorded one
(`test_workspace.py::test_archive_subcommand_zips_a_recorded_simulation`
and the refusal beside it).
