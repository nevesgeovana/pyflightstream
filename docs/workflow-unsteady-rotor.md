# The unsteady rotor workflow

The `unsteady_rotor` run type: a blade-resolved rotor, how a rotor row states its decisions, several rotors in one row, the exports that begin after a threshold and the reductions of an unsteady rotor case.

`unsteady_rotor` is a blade-resolved rotor run: a rotor coordinate
system at the hub the row declares, one rotary motion turning at the
row's `RPM` about the row's `ROTOR_AXIS`, and a physical time loop. The
values it needs come off the row and nowhere else, and a row missing one
of them is refused before anything runs, naming the row and the cell.

**A mean taken from few revolutions, or at a coarse time step, sits below
the developed wake.** An `unsteady_rotor` point's thrust and torque are still
moving after the start-up revolution: on a six-blade research propeller
measured on 26.124 the thrust gained about 0.5 % per revolution and had not
levelled at revolution 6. A finer time step raises the mean thrust
too, not only more revolutions: at the third revolution the thrust sat 8.4 %
below the quasi-steady wheel's at 10 deg per step, 6.6 % at 5 deg and 4.0 %
at 2.5 deg, and halving the step roughly doubled the gain per revolution, so
neither the step nor the revolution count had converged at the finest step
run. A `LAST_REVS_AVG` window over the third revolution of a
three-revolution run at 10 deg per step is therefore a mean of a wake still
developing; refine the step and run more revolutions before the window when
the absolute level matters, and compare points at the same step and the same
revolution count when the difference between them is what matters.

The licensed measurements of workflow-built rotor scripts cover the first
round (26.120), the following two rounds (26.124), and a further round
(26.124). Blade counts come from `families_blades`; `BLADES` applies only
to a row that names no rotor.

## A rotor row states the decisions, and the arithmetic is derived

A rotor study is designed in an advance ratio and an azimuthal step.
The rev/min, the seconds per step and the number of steps are what those
work out to at the run's own velocity, so an `unsteady_rotor` row states
the decisions and the package derives the rest.

* `ADVANCE_RATIO: <J>` sets the rotor speed as `n = V / (J D)`, against
 the velocity this row already resolves and the diameter `D`. **That diameter is the ROTOR'S OWN** where the motion names a
 rotor block of the reference, so one ratio written once gives rotors
 of different sizes different speeds; where no alias is cited it
 is the `rotor_diameter_m` the reference artifact carries, which is
 one number for the whole configuration. `RPM: <rev/min>` states the
 speed directly instead. A row states exactly one of the two, and stating
 both is refused: the rev/min are what the ratio works out to, so a
 second stated form is a second number nobody keeps in agreement with
 the first.

 **Why the ratio is the better one to keep in a file.** Rev/min are
 true at ONE velocity. A matrix stating them pins the rotor to that
 velocity silently: change the flight condition and the row keeps a
 speed that no longer means the ratio it was chosen for.

 **A row's rotor speed is a MAGNITUDE, in both forms.** It says how
 fast; it never says which way. A negative `RPM` is refused by name,
 and so is a negative `ADVANCE_RATIO`.

 **The hand of the rotation is the ROTOR's**, declared once as
 `rpm_sign = 1` or `rpm_sign = -1` on that rotor's block in the
 reference artifact, beside the axis, the origin and the blade count
 it already declares there. The row says how fast and the block says
 which way, so neither states what the other does and the two cannot
 contradict each other. A row that restates `RPM_SIGN` beside a rotor
 the reference declares is refused -- whether or not it agrees, because
 a row that agrees today says nothing when the reference is corrected
 tomorrow.

 **One exception, for a row whose reference declares no rotor at
 all**: the pre-0.15.0 spelling, which states `ROTOR_AXIS` and
 `MOVING_BOUNDARIES` rather than naming a block. Such a row has
 nowhere else to put the hand, so `RPM_SIGN: -1` beside the speed is
 the correct and only way to write it there. This is narrower than it
 sounds: if the boundary the row turns is one of a declared block's
 own families, that block is the rotor and its `rpm_sign` governs.

 A configuration whose isolated and installed meshes are opposite
 hands declares the sign on each mesh's own rotor block, which is
 where the fact lives.

* `DELTA_THETA: <deg>` and `REVOLUTIONS: <turns>` set the clock:
  `DELTA_TIME = theta / (6 rpm)`, emitted as derived, and
  `TIME_ITERATIONS = REVOLUTIONS * 360 / DELTA_THETA`. `DELTA_TIME` and
  `TIME_ITERATIONS` state the same thing directly and still work; a row
  states one pair, and half a pair is refused naming the key that is
  missing, because neither half implies the other.

 An unsteady run that meshes nothing turning takes this pair too, when
    the row states the speed whose azimuth the step measures
    (`ADVANCE_RATIO` or `RPM`). A wing-body in a propeller's slipstream is
    the case it exists for. Stating the pair with no speed is refused
    naming both keys.

 Revolutions that do not work out to a WHOLE number of steps are
 refused naming both numbers. Rounding silently would end the run
 part way through a step, at an azimuth nobody chose, and that run
 converges and exports like any other.

* `RUN_WAKE_LENGTH_R: <L>` states the run length as the wake length the
  run should reach, in rotor radii, in place of `REVOLUTIONS` or
  `TIME_ITERATIONS`. The row states it with exactly one of
  `DELTA_THETA` or `DELTA_TIME`, and the step count is
  `TIME_ITERATIONS = ceil(L R Omega / (V_ax dtheta))`: R the tip radius of the
  largest rotor the row turns, Omega its speed, dtheta the step in radians and
  V_ax the axial velocity. It is the conversion and the axial velocity rule of
  the wake termination's `wake_termination_length`: V_ax is the free stream,
  or the induced velocity `sqrt(T / (2 rho A))` of the setup's
  `wake_termination_thrust_n` where that is larger. A positive target always
  marches at least one step, even below the conversion's roundoff tolerance.
  On a row turning 1200
  rev/min at 30 m/s, whose rotor block states `diameter_m = 3.6576` (R =
  1.8288 m), at `DELTA_THETA: 10` (Omega / dtheta = 720 per second),

 ```text
 RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_THETA: 10 / RUN_WAKE_LENGTH_R: 4 / LAST_REVS_AVG: 0.25
 ```

 marches `ceil(4 x 1.8288 x 720 / 30) = 176` steps, 4.89 revolutions of 36
    steps. The script, the averaging window and every export threshold read
    that count, so `EXPORT_UNSTEADY_LAST_REV: 1` on this row exports steps 141
    to 176. `pyfs-matrix plan` prints the count per point, with the
    revolutions and V_ax:

 ```text
    <run id>: run length RUN_WAKE_LENGTH_R = 4 R: 176 steps, 4.889 revolution(s), V_ax 30 m/s (free_stream)
 ```

 and the run record's solver-flag snapshot carries `run_wake_length`,
 `run_wake_rule`, `run_wake_v_ax_m_s` and `run_wake_time_iterations`.

 **The length is nominal**: the helical travel of the wake at V_ax, not
    a measured wake. Near hover the free stream goes to zero and the count
    grows without bound, and the wake termination's revolution cap does not
    bound the run length; read the printed revolutions before running.
    Refused at plan, each naming the remedy: the key beside `TIME_ITERATIONS`
    or `REVOLUTIONS` (both named); both or neither of `DELTA_THETA` and
    `DELTA_TIME`; a length that is not positive; a rotor with no known
    diameter; and an axial velocity that is not positive (state
    `wake_termination_thrust_n` in the setup, or state `REVOLUTIONS`).

The solver log is always exported through the pproc `[exports]` table. `LOG_OUTPUT` applies only to cases written in Python. A row declaring it is refused; use `pyfs-matrix upgrade <matrix> --in-place` to migrate the matrix.

* `EXPORT_UNSTEADY_AFTER_REV: <turns>` or `EXPORT_UNSTEADY_AFTER_ITER:
  <steps>`, at most one per row, is the step the PER-STEP exports begin
  on. From that step to the end of the run the solver exports every
  per-step kind of the row's output set after each time step, and stamps
  each file with the iteration: a row whose stem is `P7001-...`
  leaves `P7001-..._iteration=72.txt`, `_iteration=73.txt` and so
  on beside the end-of-run export of the same name. Revolutions are
  counted on the rotor the run turns, so that form belongs to
  `unsteady_rotor`; `unsteady` takes the iterations form only, and a
  steady row is refused either, having no time loop for an action to
  run in. `EXPORT_UNSTEADY_LAST_REV: <turns>` and `EXPORT_UNSTEADY_LAST_ITER:
  <steps>` state the same exports from the END of the run instead: the last
  turns or the last steps (the first form belongs to `unsteady_rotor`, the
  second to both unsteady types), and the row still states at most one of the
  four. See [exports that begin after a threshold](#exports-that-begin-after-a-threshold)
  for the worked example and what the run leaves.

**The plan states how fast each rotor's tip moves (0.30.0).** For every
point of an `unsteady_rotor` row, a `steady` row that states `RPM` and a
row that names an actuator disc, `pyfs-matrix plan` prints the tip and
helical Mach numbers of each rotor and disc, from the speed the run turns,
the rotor's diameter (a disc's `tip_radius_m`) and the point's own free
stream and speed of sound, one row per rotor per point under the title
`Rotor Mach numbers`:

```text
Rotor Mach numbers
  POL   point                    rotor       M_tip  M_hel  M_adv
  9001  M144RE438AL+000RPM03000  rotor PORT  0.554  0.572  0.572
  9001  M144RE438AL+000RPM06000  rotor PORT  1.108  1.117  1.117
```

and warns, naming each point, when the advancing-tip Mach number is 1 or more
(`M_adv >= 1`, the advancing tip sonic or supersonic):

```text
advancing-tip Mach M_adv >= 1 on 1 polar point(s): POL 9001 point M144RE438AL+000RPM06000,
rotor PORT, M_adv 1.117 (M_hel 1.117)....
```

`M_adv = sqrt((Omega R + V_ip)^2 + V_ax^2) / a`, with `V_ax` the free-stream
component along the rotor axis and `V_ip` the component in the rotor plane.
`M_hel = sqrt(V^2 + (Omega R)^2) / a` bounds the tip only in axial flow, where
`M_adv = M_hel` (the example above); in edgewise flow `M_adv = (Omega R + V) / a`
is larger. Where a row's rotor axis cannot be resolved, `M_adv` is that
edgewise bound and the plan line says so.

A disc's row reads `actuator PROP` in the rotor column. The plan refuses nothing for
the warning. A rotor whose reference states no diameter for it has no known
radius: the plan says so naming the row instead of a number. The
definitions, and where else the two numbers appear (the run record, the
rotor table), are in
[the definition of record](post-processing-definitions.md#tip-and-helical-mach-numbers).

`VAR_NAMES_VALUES` is your namespace except for the keys the package
itself reads, which the [input glossary](inputs.md#tables-and-reserved-keys)
lists; a cell of yours that spells one of them is read by the package
rather than ignored. The [upgrade index](upgrading.md) links the release
records for retired spellings and changes to their interpretation.

**`BASE_REGIONS` NAMES THE BASE, NOT THE BODY.** The command it emits,
`DETECT_BASE_REGIONS_BY_SURFACE <index>`, takes the boundary that becomes the
base region. On a body whose flat base is its own boundary, 20_BODY's
`[Body, Base]`, `BASE_REGIONS: Base` marks the base, the same faces
`AUTO_DETECT_BASE_REGIONS` marks, and `BASE_REGIONS: Body` marks nothing and
says nothing. A row naming the body therefore solves with no
base region and no error; name the base boundary. A pproc's `base_regions`
list follows the same rule. A raw mesh's sidecar can ask for the whole-mesh
detection instead, `[base_regions] detect = "auto"`
([mesh inputs](mesh/reference.md#the-boundary-conditions-of-a-raw-mesh)).

**A WORKFLOW ROW STATES ONLY WHAT THE SCRIPT WILL CARRY.** Each run type
registers the keys it reads (`Workflow.keys` in
`pyflightstream.cases.workflows`, the wider types extending the
narrower), and a row naming a run type is refused at `pyfs-matrix plan`
for any key outside that vocabulary. Measured on 2026-09-08: a copy of
the suite's own tour with `FOO_BAR: 1` appended to a row planned READY on
every point, and the run would have spent a seat on a row stating
something the script does not carry. The row

```text
7007 | Wing | REFUSED | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 | r001 | s001 | p002 | 26.120 | 0 | 1 | steady | GEOMETRY: 10_WING.fsm / SYMMETRY: NONE / FOO_BAR: 1
```

is marked BLOCKED with the reason naming the row (`case '7007'`), the run
type, the key and what reads it (`FOO_BAR (a key of no run type)`), and
the keys `steady` registers. A key ANOTHER run type reads is refused the
same way and named with that type: `LAST_REVS_AVG: 0.25` on a `steady` row
is `a key of unsteady, unsteady_rotor`. The refusals a builder already
had for a key it cannot honor come first and keep their own sentences: a
rotor key on `unsteady` still says that nothing would turn, and an export
threshold on `steady` still says there is no time loop. A LEGACY row
keeps its free keys, because its RECIPE is their reader: the tour's own
LEGACY row with `FOO_BAR: 1` appended plans READY.

`VELOCITY` is registered on every run type and is unreachable from a
matrix row: the mandatory `FLIGHT_CONDITION` column resolves the
velocity onto the case and the builders read that first, so the key is
read for a case authored in Python and nowhere else. A matrix row that also
states `VELOCITY` warns that it is ignored; remove the key and specify the
velocity through `TASmps` or `MACH` in `FLIGHT_CONDITION`. `ADVANCE_RATIO` is
registered on every run type because the point NAME reads it and the export names carry it into the script.

**`MOVING_BOUNDARIES` NAMES SURFACES, AND SHOULD NOT COUNT THEM.** Write
the boundary names the geometry carries, or a FAMILY name, which is a
boundary label with its trailing number removed:

```
MOVING_BOUNDARIES: Blade,S
```

One cell, and it is right for every geometry in a study. On a sector mesh
holding `Blade1, S, N` it moves the first two; on the full wheel holding
`Blade1, S, N, Blade2... Blade6` it moves all six blades and the spinner.
The package reads the names out of the saved simulation the row opens and
resolves them to the solver's own boundary indices, so the cell follows
the geometry instead of pinning it.

A cell of NUMBERS still works and now warns, naming the surfaces those
positions actually select. A position is a place in one file's boundary
order: it is right for the file it was written against and means a
different surface in any file that orders them differently, and before
this release nothing said so. The run completed, exported, and reported
loads for a rotor whose moving set was wrong.

An exact label beats a family, so `Blade1` is one blade and `Blade` is all
of them. Between the two sits an ALIAS the row's REFERENCE declares in its
`[aliases]` table, so a study may give one word to a set of families and a
member the file lacks is ignored; a cell naming an alias none of whose
members the file carries is refused naming the alias. A name the geometry
does not carry is refused, listing the ones it
does: `MOVING_BOUNDARIES: Blade1,S` on the suite's pusher row, whose
geometry `40_PUSHER.fsm` carries `Body`, `Base` and `Blade1`, is marked
BLOCKED at `pyfs-matrix plan` naming the row, `'S'`, the file, the
sidecar `40_PUSHER.boundaries.toml` it was read from and the three names
it declares; `Blade1` alone moves boundary 3, and so does `3`, with the
warning.

**A cell may also name a GROUP of the row's pproc artifact**, spelled
`g<number>`: `MOVING_BOUNDARIES: g4` moves the members of
`[groups]` entry `"4"`, resolved against the geometry the way the polar
tables resolve them, a member the file does not carry being left out.
The letter is what tells a group from a position, since `4` alone is
still the fourth boundary. A group that names nothing the file holds is
refused naming the group, its members, the artifact, the file and its
inventory; on the pusher, `g2` (group 2 of `p001`, which is `Wing`)
is refused that way.

**And the pproc artifact itself is judged against the geometry at plan
time.** A row whose artifact's groups cite no name the opened file
carries is BLOCKED naming the row, the artifact, the names, the file and
its inventory: `"1" = ["Wing"]` against `14_WING_RENAMED.fsm`, whose
inventory reads `MainWing` because the boundary was renamed in the solver
before the save, is blocked instead of producing an empty polar sum. What is refused is the
artifact and the geometry sharing NO name, not a member missing from one
group: an artifact is written once for a study and shared by rows
opening different geometries, so a family a file lacks is left out by
design, and `p002`'s group 3 (`Body`, `Base`) sums to zero on the wing
rows exactly as the reference products carry it.

`angle_sweep_deg` IS RESERVED TOO, and it is the one whose
match FOLDS CASE rather than being exact: a cell spelling it in any
casing is read as a sweep of a geometric rotation, and a row that also
sweeps an aerodynamic axis is REFUSED for it. Its lookalike `angle_deg`
is a value you write and nothing reads at run time. Only one of the two
can stop a campaign.

The `matrix_` prefix is the CONVERTER's rather than yours:
`matrix_ref`, `matrix_set`, `matrix_pproc`, `matrix_fs_script`,
`matrix_fs_build`, `matrix_hidden` and `matrix_workflow` are written
over whatever your cell said, after your cell is read. A key of yours
spelling one of those is not read by the package; it is replaced.

## One row, several rotors

A rotor row states its motion flat, `RPM`, `RPM_SIGN`, `ROTOR_AXIS`,
`ROTOR_ORIGIN` and `MOVING_BOUNDARIES` as keys of the cell, and that is one
rotor. A row may state several: `MOTIONS: {...},
{...}`, each pair of braces one rotor holding those same keys, the pairs
inside separated by `/` as in the flat cell and the records by commas. The
builder then creates, per record, a fixed frame at the record's hub
(`<ALIAS>_SMRP`, one per record), a moving frame turned by the motion
(`RotorAxis1`,...) and one `CREATE_NEW_MOTION` block citing its own frame,
axis, speed and boundaries; each rotor's `<ALIAS>_SMRP` is the frame the pproc
entries cite, the time step follows the rotor `CLOCK_MOTION` names, and the run record
lists every record as bound. A record's `ROTOR_ORIGIN` may name a point of
`inputs/reference_points.toml` instead of three coordinates; the point must
be a rotor point, `ERP` or `ERP1` through `ERPn` by the naming convention,
and a motion on a point declared `kind = "airframe"` is refused naming the
point and its kind. A name outside the convention is refused when the file is
read, whatever kind it declares, because the names are what say how many
propulsors the campaign describes (measured 2026-09-08 on the tier-3
workspace, which had named a hub `HUB`). The flat rotor row's
own `ROTOR_ORIGIN` may name a point the same way; until then
only a `MOTIONS` record could, and the one-rotor row demanded three numbers. A flat row renders
exactly as before; a row with a `MOTIONS` list and a flat motion key beside
it is refused, as is an unclosed brace or a record repeating a key.

A point opens its geometry through a link: `sims/<sim>/inputs`
is a directory junction on Windows and a symbolic link elsewhere, pointing at
`inputs/geometries/`, so a campaign of forty points holds one copy of each
mesh and the record still carries the opened path and its sha256, with
`staged_as: link`. A geometry that has its own folder,
`inputs/geometries/30_WB/`, is linked at that folder, so the
point's inputs show that geometry's files, its boundary inventory among
them, and never the rest of the library. Where a link cannot be made, the
inputs are copied and the record says `staged_as: copy` with the reason.
Archiving writes the link as a one-line `inputs/STAGED_AS_LINK.txt` and
never the library's bytes.

The boundary order of a staged geometry is read from the file and written
beside it, never stated in a setup,
which puts it inside the geometry's folder when the geometry has one:

```text
pyfs-matrix inventory inputs/geometries/30_WB.fsm    # writes 30_WB.boundaries.toml
```

An `.obj` gets its sidecar from its groups the same way, and from the plan
itself when it has none.

A workspace using the retired artifact names moves in one command:

```text
pyfs-matrix upgrade matriz.fs --in-place --inputs inputs
```

which renames the column, drops `FS_SCRIPT`, moves `inputs/groups/e001.toml`
to `inputs/pproc/p001.toml` under a `[groups]` header (the file's own lines,
comments and all), and gives the cells that named it their `p`.

**A workspace with a `SWEEP_TYPE` column moves with the same command**, which
also folds `SWEEP_TYPE` into the flight condition: `AL` becomes
`ALPHA:sweep`, `BE` becomes `BETA:sweep`, and a paired `AL/BE` whose second
axis held one value becomes `ALPHA:sweep, BETA:<value>` with the same rows.
Until you run it, `read_matrix` refuses the matrix with a message that
names this command.

Two things about that conversion are worth knowing before you run it:

* **It does not rename a run.** A held angle is carried at every point, so
  the point names that end every `run_id` in `runs.json` are the ones the
  converted file plans under, and a `--resume` finds the records it has.
  (The 0.21.0 point NAME is a separate move, made once by `pyfs-matrix
  rename`; see [migrating to 0.21.0](upgrading.md#older-layouts).)

* **It stops on a row that varies BOTH angles**, naming every such row.
 That row is one run per sideslip and each new row needs a POL of its
 own, which is run identity and not a converter's to invent. Split them
 by hand, giving each the POL you want, then run the command.

## Normal probes on a rotor row

A `[[probes]]` entry of a rotor row is a fluid plot per point and parameter,
written at every time step, unless it states `kind = "normal"`: then it is a
probe point created after the march and exported once, at the last time step,
as on the `unsteady` run type
([Probes: unsteady or normal](workflow-unsteady.md#probes-unsteady-or-normal)).
With `EXPORT_UNSTEADY_AFTER_REV` or `EXPORT_UNSTEADY_LAST_REV` they are also
exported at every step of that window, `<point>_probes_iteration=<step>.txt`.

## Exports that begin after a threshold

A rotor run settles over its first revolutions, and the loads, sections
and probes worth keeping are the ones after that. `EXPORT_UNSTEADY_AFTER_REV`
states the revolution the per-step exports begin at; `EXPORT_UNSTEADY_AFTER_ITER`
states it as a time step instead. Put one of them on row 7001 of [the workflow matrix](workspace-and-workflows.md),
with the azimuthal clock:

```text
RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_THETA: 10 / REVOLUTIONS: 3 / LAST_REVS_AVG: 0.25 / EXPORT_UNSTEADY_AFTER_REV: 2
```

Ten degrees a step and three revolutions are 108 steps, and two
revolutions are step 72, so the solver exports after each of steps 72 to
108: 37 files per kind, each stamped with its iteration by the solver
itself, `P7001-..._iteration=72.txt` and so on, beside the
end-of-run export of the same name. The script the row builds registers
two unsteady solver actions before the solver is initialized, in this
order:

```text
SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter
"<python>" "actions/pfs_unsteady_actions.py"

SET_NEW_UNSTEADY_SOLVER_ACTION SCRIPT pfs_unsteady_exports
actions/pfs_unsteady_exports.txt
```

`<python>` is the interpreter that built the script; on Windows it is that
interpreter's `pythonw.exe` sibling, so no console window opens after each
time step, and a Python installation without one is refused before the run
is prepared. The solver hands an
action nothing about where it is in the run, no step, no azimuth, no
environment, so the first action is a small Python program the
run layer writes into the point's `actions/` folder. It counts its own
invocations in a file beside itself, derives the azimuth and the
revolution from the count with the step in degrees and the rotor speed
the package wrote into it, and rewrites the second action's file: empty
until the count reaches the threshold, and from then on the export of
every per-step kind the row's output set declares. The solver runs the
two in creation order after every time step and re-reads the file each
time, so the rewrite is what it executes. Both files are staged inputs
of the point: the run record names them as `action_program` and
`action_script`, hashes them in `inputs_sha256`, and keeps in
`action_count` the count the program reached, which is the number of time
steps the solver completed.

What is exported per step is read from the row's outputs and nowhere
else: the loads table, the surface (the VTK, from which the run writes each
step's Tecplot file), the sections, the sectional
loads and the probes, whichever the pproc artifact's export set kept.
The saved simulation, the plots file and the log describe the whole run
and stay at the end.

**A row that states neither key registers the counter alone**, on a build that documents the actions: only the first of
the two registrations above, whose program counts the time steps and
writes nothing else, so no exports file exists and no exports action runs.
The record names the program as `action_program` and keeps `action_count`,
with no `action_script` and no `export_window`, and the progress bar of a
local run reads that count, as it reads it on a row with exports. A row stating both keys is refused naming both; a
threshold beyond the run is refused naming both numbers; the revolutions
form on `unsteady` is refused naming the iterations form that would work,
because a run that turns nothing has no revolution to count.

`WINDOW_*` keys keep their one job, the averaging window of the
reductions.

### The last revolutions or the last steps of a run

To export the end of a run without counting its length yourself, state how
much of the end instead of where it begins. `EXPORT_UNSTEADY_LAST_REV:
<turns>` on a rotor row, or `EXPORT_UNSTEADY_LAST_ITER: <steps>` on a rotor or
an `unsteady` row, makes the per-step exports cover the last `n` time steps of
the run, with `n = ceil(turns x steps per revolution - 1e-9)` (the tolerance of the after form) for the first form
(`steps per revolution` is the rotor clock's, `360 / DELTA_THETA`) and `n = <steps>`
for the second. The first exported step is `TIME_ITERATIONS - n + 1` and the last
is `TIME_ITERATIONS`. On row 7001 above, three revolutions of 36 steps, the last
revolution is

```text
RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_THETA: 10 / REVOLUTIONS: 3 / LAST_REVS_AVG: 0.25 / EXPORT_UNSTEADY_LAST_REV: 1
```

and exports steps 73 to 108. From the first step on, the script, the counter
program and the files written per step are exactly those of
`EXPORT_UNSTEADY_AFTER_ITER: 73`. The run length is resolved before the threshold,
so `n` counts back from the `TIME_ITERATIONS` the run really marches, the one
`RUN_WAKE_LENGTH_R` resolves included.

What is refused, at plan: two of the four keys on one row, naming both; the
revolutions form on `unsteady`, naming `EXPORT_UNSTEADY_LAST_ITER` as the form
that works; a value that is not positive or rounds to no step; a huge value; an `n` larger than `TIME_ITERATIONS`,
naming the run length (an `n` equal to it exports every step); and, with a pproc
`[time_averaging]`, a first step after the averaging window's first step, as for
the after-threshold forms. The run record's `export_window` states the form
(`iterations` and `revolutions` for the after forms, `last_iterations` and
`last_revolutions` for these), the value as written and the resolved
`first_step`, which every reader of the window reads as before.

**One file per sections distribution (0.25.0).** Post always writes
`sections/<point>_sloads_<name>.csv` and `sections/<point>_cp_<name>.csv` for
each `[[sections.distributions]]` entry with usable exports and recorded layout.
The name is its `families` word or alias, or its list joined with `-`
(`Blade1-Blade2`). Invalid filename characters become `_`; trailing spaces
and dots are removed. Colliding names receive the 1-based entry position
`_<k>` (repeated if needed), including collisions introduced by sanitization
or case differences. One entry's planes and expanded blade blocks stay together.

With either per-step export threshold, these files contain **all exported
steps**, with `STEP, time_s, FAMILY, PLANE, ROTOR, AZIMUTH`, the condition block,
and the export's own columns. Cp adds the export's cross-section index as
`SECTION`, followed by all twenty chordwise columns, one row per station.
Without a threshold, the files hold the end-of-run exports and state their
step as the existing sections table does. That table and the combined sections
series remain available. `products.json` records each distribution, its original
families/alias and `steps_tabled`, with named skips for missing exports or steps.
No recorded `sections_layout` means no split: post names the missing layout.
A point whose script created no distribution records the empty layout, `[]`,
and has nothing to split and nothing named; a record without a layout is given the empty one when its recorded script still hashes
as recorded and creates no surface section, and a continuation records the
layout of the run it continues. Older layouts require an unambiguous match to their recorded pproc, read over the
geometry's boundary names where the record carries them or its geometry hash
recovers them, for a block recorded in a common frame; a block in a frame spelt
like a rotor's is matched over the recorded cuts, as in 0.26.0. See the
[sections definitions](post-processing-definitions.md#per-distribution-sectional-loads-and-cp-0250).

**The stamped files as a series**. Thirty
seven spreadsheets are not a history until something tables them, so the
products stage writes, per windowed point, one table per export kind
under `post/<matrix stem>/series/`:

```text
post/matriz/series/P7001-M144RE438AL+000BE+000_loads_series.csv
post/matriz/series/P7001-M144RE438AL+000BE+000_sections_series.csv
post/matriz/series/P7001-M144RE438AL+000BE+000_probes_series.csv
```

Every table leads with `POL`, then `STEP`, `time_s` and `azimuth_deg`, and then states the point's condition
block; the probes series says WHICH probe each row is in `PROBE`, and the
sections series leads with `POL`, `STEP`, `time_s`, `FAMILY`, `PLANE`, `ROTOR`,
`AZIMUTH`, the identity the
sections table carries. `time_s` and `azimuth_deg` are the step's
time and azimuth computed from the clock the run record carries
(`export_window.delta_time_s` and `step_deg`, written by the run) by the same arithmetic the counter program runs on the machine,
so the two agree by construction; a record written before the clock
leaves the time unstated -- which the table writes as `NA` -- and reads the azimuth off its reductions plan. The
loads series is wide, one row per step and one column per surface and
coefficient (`Total_CL`, `Blade1_CMx`,...); its moment columns are about
the row's moment point, and historical unsteady loads series affected by the moment-origin defect need the correction described in [the migration](upgrading.md#older-layouts); the sections series (from
the sectional loads export, `_sloads`, the same export the sections
table of the products reads) and the probes series are long, one row per
step and section or probe, with the export's own columns. A kind with no
stamped file is NOT written, and `products.json` names it under `skipped`
with the folders that were searched. The stamped files are looked for where the point RAN: its
`datapoints/DP-<point>/`, where every point runs, and the
simulation folder used by historical local runs. A
step the solver never stamped is absent and the `products.json` entry
says which steps were tabled; the surface sections export (`_cp`) and
the Tecplot file (`.dat`) of the window are listed there by path, as
`sections_files` and `tecplot_files`. Cp is also tabled in the per-distribution
files above; each step's Tecplot is the one the run wrote from that step's VTK
([the definitions](post-processing-definitions.md#native-surface-flow-exports)),
and is not rewritten by the post. A stamped file the parsers cannot read costs that
point its series, recorded under `skipped` as `series/<run id>`, and
never the stage. These tables are not the "raw series" the reductions
write beside the plots table: that one is the plots export's history of
the coefficients per step, this one is the stamped spreadsheets, surface
by surface and section by section, over the exported window. The series
rest on the stamped files and the record alone, so a simulation whose
polar the stage refuses keeps them.

## The reductions of an unsteady rotor case

The post writes the reductions of an unsteady rotor point beside its plots
table, the raw series, which is never replaced by them. Which reductions a
rotor row gets, over which windows, and how a row naming its rotors reduces
per rotor are defined on [the definition of
record](post-processing-definitions.md#the-reductions-of-an-unsteady-point);
[the unsteady workflow](workflow-unsteady.md#the-reductions-of-an-unsteady-point)
shows them on a worked example. In the code, `reduction_plan(case)` resolves
a row's windows and `pyflightstream.post.reductions` writes them.
