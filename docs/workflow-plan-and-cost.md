# Planning a campaign and what it costs

What `pyfs-matrix plan` prints, what a study costs before the seat is spent, and the averaging window stated once.

## What plan prints

`pyfs-matrix plan` prints its answer in blocks. Each block starts with a short
title saying what it is, and one blank line separates two blocks; a block with
nothing to say is not printed at all. A plan of two rotor rows that both block,
with two warnings:

```text
pyfs-matrix plan
  matrix: named.fs
  campaign: camp
  FlightStream build: 26.120

Warnings (2)
[warning] named.fs lies outside the workspace's matrix folders
          (C:\cases\camp and C:\cases\camp\inputs\matrices): `sync` and the
          repeated-POL census do not see it. Move it into one of the two folders.

[warning] helical Mach >= 1 on 2 polar point(s): POL 9001 point M144RE438AL+000RPM06000,
          rotor PORT, M_hel 1.117; POL 9002 point M144RE438AL+000RPM06000, rotor PORT,
          M_hel 1.117. ...

Cases
  points: 0 ready, 4 blocked, 0 already recorded
  solver installations: 1
    the campaign's own installation: 2 case(s) (9001, 9002)

Blocked points (4)
  camp/sim_9001/M144RE438AL+000RPM03000
    ScriptReferenceError: case '9001' states MOVING_BOUNDARIES with 'PORT', and
    wing_clean.fsm carries no mesh block, so no boundary name can be read from it. ...
  ...

Rotor Mach numbers
  POL   point                    rotor       M_tip  M_hel
  9001  M144RE438AL+000RPM03000  rotor PORT  0.554  0.572
  9001  M144RE438AL+000RPM06000  rotor PORT  1.108  1.117
  9002  M144RE438AL+000RPM03000  rotor PORT  0.554  0.572
  9002  M144RE438AL+000RPM06000  rotor PORT  1.108  1.117

Solver setup per case
  POL 9001 (FlightStream 26.120, setup s002)
    settings: solver_model=None, boundary_layer=None, viscous_coupling=None
    aliases: PORT
    Singularity_strength: not carried (pproc singularity_strength = false)
  POL 9002 (FlightStream 26.120, setup s002)
    ...

Files written
  plan: C:\cases\camp\post\named\plan.json
```

What each block says:

- the header names the command, the matrix, the campaign and the FlightStream
  build the campaign defaults to;
- `Warnings (n)` is every warning the plan raised, each wrapped under its text
  and followed by a blank line. A warning refuses nothing; read it before you
  run;
- `Cases` counts the points that are ready, blocked and already recorded, and
  names the solver installations the cases run on;
- `Blocked points (n)` names each point that cannot run, and why;
- `Rotor Mach numbers` is one row per rotor and actuator disc per point, and
  `Quasi-steady validity per point` the reduced frequency of each wheel point
  (below);
- `Solver setup per case` is each row's solver model, boundary layer and
  viscous coupling, its aliases and, on a row with a Tecplot surface, whether
  the surface carries `Singularity_strength`;
- `Solver cost per point` is the `--cost` table (below);
- `Files written` is the plan receipt `run` asks for and each guide the plan
  wrote.

The warnings go to stderr and everything else to stdout; the exit code is 1
when a point is blocked and 0 otherwise. The `[continuation] started` and
`finished` lines of each point print only with `--verbose`, which also prints
each warning in Python's full format; `logs/activity.log` records them either
way.

## Before you spend the seat: what the study will cost

`plan` answers whether a row will run. It does not, on its own, answer what
running it will cost, and the cost is a licence seat and an afternoon. Add
`--cost` and it tables one row per point under the title `Solver cost per point`:

```text
pyfs-matrix plan matriz.fs --workspace . --fs-version 26.123 --cost
```

```text
point                                      mesh   TEs  layers  visc      type   steps  procs   expected  samples
----------------------------------------------------------------------------------------------------------------
pfs0160/sim_6001/M200RE1177AL-020         14266     2       -    no    steady       -      8      11.9s        2
pfs0160/sim_6002/M144RE438AL+000J+170     13502     0       5    no  unsteady      36      8     194.8s        1

EXPECTED TIME IS AN EXTRAPOLATION AND NOT A MEASUREMENT:
  steady rows: fitted from 2 recorded steady run(s) of this workspace, ...
  unsteady rows: fitted from 1 recorded unsteady run(s) of this workspace, ...
```

The flag spends no solver time: every figure comes from the workspace, the
mesh and the runs already recorded.

**EVERY COLUMN BUT `expected` IS A READING**, and each is read from the thing
that owns it. `mesh` is the element count the geometry's mesh block states, AS THE FILE
STATES IT: one campaign geometry of this estate says 7848 where every array
holds 7784, so read it as the size to about a percent and not as a count of
anything. Nothing does arithmetic on it; the fit is linear in the time steps
and in nothing else.
`TEs` is the families the row marks for vorticity drag, intersected with the
inventory the geometry declares, which is what the builder does with them; a
geometry this reader cannot open prints `-` there rather than the row's own
count, because the two are different quantities and a reader could not tell
them apart in one cell. A raw mesh's inventory is its sidecar's `boundaries`
as the import's renames leave them, since the file carries no mesh block
(since 0.27.0; before it, every raw-mesh row printed no count here).
`layers`, `visc` and `procs` are the solver preset's `farfield_layers`,
`viscous_coupling` and `max_parallel_threads`. `steps` is what the row's clock
works out to: a rotor row stating `DELTA_THETA: 15` and `REVOLUTIONS: 1.5`
reads 36. A cell the package cannot derive prints `-`, never a zero, because a
zero is a measurement.

**`expected` IS NOT A READING AND THE TABLE SAYS SO UNDER EVERY PRINTING.** It
is fitted from the wall times THIS workspace has recorded, comparably by run
type, linear in the time steps the point asks for, and the row carries the
number of samples behind it. A point with no comparable recorded run prints
`unknown` rather than a figure with no basis. It is a crude model on purpose,
and it will be recalibrated when a scalability study exists to calibrate it
against.

One consequence worth knowing: `samples` counts the runs that actually entered
the fit, not the comparable runs found. An unsteady run whose step count cannot
be resolved is left out rather than counted as a single solve, and the basis
line says how many were dropped.

## The cost file

A workspace may carry one cost file for each machine, `inputs/costs/c<NNN>.toml`
(FR-398). `plan --cost` and the `plan --batch` estimate read it when it is
present, and `--cost-file NAME` names the one to read when the workspace holds
several; a single file needs no name. Without a cost file `plan --cost` fits
its expected time from the workspace's own recorded runs, as before.

The file has an anchor run (`[reference]`: the mesh size, processor count,
wall time and step count of one run measured on the machine), an efficiency
curve (`[parallel]`: a speedup for each stated processor count, interpolated
linearly between two stated points), an exponent `b` on the mesh size
(`[mesh]`, time scales as N to the power b), an exponent on the step count
(`[steps]`) and the multiplier of each solver flag the row sets (`[flags]`).
A processor count outside the stated range is never extrapolated silently: the
estimate is withheld and its basis says why. An unknown key is refused by name.
The package ships only a synthetic example, `examples/costs/c000.toml`, whose
values are invented round numbers; the measured values of a machine belong to
its user and are never part of the package.

## One job for a polar or for a batch of polars

`pyfs-matrix plan --batch N` plans the polars as N solver jobs, and
`plan --polar-sweep` as one job for each polar (FR-362). The steady run types
`steady` and `qsteady_rotor` join since 0.35.1 (FR-403). The plan groups the
polars by processor count, build, kind and the setup's own `unsteady_solver_actions`,
so that no job mixes two builds, a steady polar with an unsteady one, or two
sets of user actions (FR-405), and cuts
each group into contiguous batches of whole polars so that the largest batch
estimate is the smallest possible. Each acoustic polar is planned as a job of
its own with all its points (FR-406): opening a second polar after an acoustic
one ended the solver process on 26.124
([RPT-148](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-148_licensed-batched-versus-alone-0351_2026-10-03.md)).
It prints the split as a table with each
batch's name, working directory, polars, points, estimate and walltime, and it
names every polar a grouped job cannot take, with the reason: a LEGACY row, a
steady row stating `COLD_START` false, a steady point that initialises the solver
more than once (a quasi-steady wheel of several clockings, a wake termination
read from a file), a `RESTART` row, an unsteady row on a build without
the action command, and a polar whose points do
not splice into one script. A steady job registers no solver action: a later
point of a polar is restated from `SOLVER_SET_AOA` after
`REMOVE_INITIALIZATION`; a later point that differs before it (a swept flow
state, a quasi-steady rotor's turning free stream) reopens its geometry after
`NEW_SIMULATION`, and the plan names its polar in a warning. Each point is
recorded as the point run alone.
A collected point records the solver version and build as the point run alone
does (FR-366), and a restated point reuses its sections (FR-362).
A polar whose post asks for `[time_averaging]` now groups, with each point's
per-step exports landing in its own datapoint folder (FR-402).
A receipt in which every polar was left out holds no job, and `run` refuses it. The split is recorded per batch in the plan receipt
`post/<matrix>/plan.json`, and `run --batch N` refuses a receipt that has no
batches or was made for another N or another matrix (FR-365).

A repeated `SWEEP_VALUES` value is refused as a matrix error naming the POL,
both values and their positions, and the shared point name (FR-408).

The batch's estimate is the sum of the estimates of its points plus the start,
re-initialization, reset and save overheads. A point with no estimate is
budgeted at its row's `WALLTIME` cell, and the batch that rests on such a point
is named (FR-363).

A job's script is `FULL-POLAR.txt`, at the root of the polar's simulation
folder, or `BATCH-<first sim>-<last sim>.txt`, inside the batch's working
directory `sims/batch/<matrix>_b<ID>/`, where `<ID>` is assigned by the
package and never typed (FR-357, FR-358).

### The setup's own unsteady solver actions in a grouped job

A polar whose setup states `[[unsteady_solver_actions]]` joins a grouped job
(FR-405, 0.35.1). Inside one solver instance an action, once registered, runs
after every time step of every later point: it survives the re-initialization
between two points and the `NEW_SIMULATION` between two polars, a second
registration makes it run twice a step, and no solver command withdraws it.
So the plan puts in one job only polars that state the same actions (the same
type, name and file, in the same order), and the job registers them once, at
its start, before the package's own counter and clock, which is the order a
point run alone registers them in. Each point therefore runs exactly the
actions its own setup states, once a step.

Two things differ from a point run alone, and the plan says so:

- `--batch N` can plan more jobs than N, one per set of actions at least, and
  warns when it does.
- The working directory of the whole job is the job's folder, where a point run
  alone runs from its own datapoint folder. A `COMMAND_LINE` action whose
  command reads or writes a relative path finds it there; the plan warns, for
  each job that runs user actions, naming its polars and folder. A `SCRIPT` action
  named by a relative file also joins the grouping. The same warning names the
  file and the job folder once per job that registers it: the file resolves in
  that folder and must be placed there (FR-405). An absolute `SCRIPT` file draws
  no relative-file warning.

### A geometry that carries saved actions

A grouped plan still refuses a polar whose geometry is a saved simulation that
carries unsteady solver actions, naming the file and the command that removes
them, `pyfs-matrix inventory <file> --clean` (FR-378). Opening such a file loads
its actions, which then run beside the ones the job registers (twice the runtime
commands in the licensed measurement) and survive into every later polar of the
job; the job's step counter, which must fire once a step to tell the points
apart, would count wrong. The cleaned file groups like any other.

### Acoustic and coupled rows in a grouped job

Each acoustic polar is planned as a job of its own with all its points
(FR-406), because opening a second polar after an acoustic one in the same
instance ended the solver process on 26.124
([RPT-148](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-148_licensed-batched-versus-alone-0351_2026-10-03.md)). Each
point after the first one of the job deletes the observers that earlier points
left in the solver and then states its own acoustic setup again (the sources
switch, its observers and their time window), just before its unsteady solver
block, where a point run alone states it. Without the delete, a later point
would create its observers a second time. A point without acoustics that
follows an acoustic one switches the sources off. The signals export and the
section folder of each point are written in that point's own datapoint folder,
and collect lists the section's files as it does for a point run alone.

A row coupled with the structure (FSI) on `unsteady` also joins a grouped job
(FR-407). The coupling loop runs inside the solver: at every time step the
solver runs the post-processing script and then the structural program, in the
point's own folder. Each coupled point starts its part of the job with
`NEW_SIMULATION` and its whole script, even after a point of the same polar.
This reopens the geometry from its file, so a point never starts from the mesh
that an earlier point's coupling deformed. The job runs a copy of each coupled
point's post-processing script, `actions/pfs_fsi_post_<NNN>.txt` in the job's
folder, in which every file the script writes is in the point's own folder. A
point without coupling that follows a coupled one switches the coupling off. A
coupled point costs one model load more than the estimate counts for it (about
two seconds).

A coupled row on `steady` or `qsteady_rotor` is left out with the other steady
rows. Its script ends at `EXECUTE_AEROELASTIC_ANALYSIS`, which returns at once
and is ended by any line that follows it, so no other point can run after it in
the same instance. `unsteady_rotor` refuses FSI, whether the point is run alone
or in a grouped job.

### The walltime of a grouped job

The `WALLTIME` cell of a row is the budget of one of its datapoints. A grouped
job asks for the sum over its points of the cells of their rows, capped at the
queue's maximum with a warning that suggests a larger N; a row whose own cell
is above the maximum is refused (FR-364). The maximum is the key `max_walltime`
of the HPC profile `inputs/hpc/<cluster>.toml`, written `HH:MM:SS`; a value
that does not parse is refused naming the key, and without the key there is no
limit (FR-377).

The cell may read `BEST` instead. The package then prices the job itself: the
estimate of the batch times 1.25, plus the walltime margin, rounded up to the
next minute and written with its unit. `BEST` is a value of the grouped plan
and a plan that uses neither `--polar-sweep` nor `--batch` refuses it, naming
the row. In a mixed job, each `BEST` row adds its own priced estimate to the
other rows' cell budgets (FR-364). An unknown `BEST` point uses the profile's
`max_walltime` with a warning naming the point, or is refused without one.

## The window, said once

**THE AVERAGING WINDOW HAS A KEY OF ITS OWN, AND SINCE 0.24.0 A ROW MUST STATE
IT**: `LAST_REVS_AVG` on an `unsteady_rotor` row, a count of the last
revolutions that accepts a float, and `LAST_ITERS_AVG` on an `unsteady` row, a
count of the last iterations. `pyfs-matrix plan` refuses a new unsteady row that
states NO window key. A retired `WINDOW_*` key is refused since 0.26.0. It is the one window the unsteady polar, the time average and
`per_blade` use ([the reductions](post-processing-definitions.md#the-reductions-of-an-unsteady-point)). A window longer than the run is the whole run rather than a
refusal.

Row 7001 states `LAST_REVS_AVG: 0.25`, the last quarter revolution counted
backward from the end of the run. This is the averaging window for every
unsteady product. A window longer than the run selects the whole run.
