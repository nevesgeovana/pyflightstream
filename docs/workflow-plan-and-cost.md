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

## The window, said once

**THE AVERAGING WINDOW HAS A KEY OF ITS OWN, AND SINCE 0.24.0 A ROW MUST STATE
IT**: `LAST_REVS_AVG` on an `unsteady_rotor` row, a count of the last
revolutions that accepts a float, and `LAST_ITERS_AVG` on an `unsteady` row, a
count of the last iterations. `pyfs-matrix plan` refuses a new unsteady row that
states NO window key. A retired `WINDOW_*` key is refused since 0.26.0. It is the one window the unsteady polar, the time average and
`per_blade` use. A window longer than the run is the whole run rather than a
refusal.

Row 7001 states `LAST_REVS_AVG: 0.25`, the last quarter revolution counted
backward from the end of the run. This is the averaging window for every
unsteady product. A window longer than the run selects the whole run.
