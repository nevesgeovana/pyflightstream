# The unsteady rotor workflow

The `unsteady_rotor` run type: a blade-resolved rotor, how a rotor row states its decisions, several rotors in one row, the exports that begin after a threshold and the four reductions of an unsteady rotor case.

`unsteady_rotor` is a blade-resolved rotor run: a rotor coordinate
system at the hub the row declares, one rotary motion turning at the
row's `RPM` about the row's `ROTOR_AXIS`, and a physical time loop. The
values it needs come off the row and nowhere else, and a row missing one
of them is refused before anything runs, naming the row and the cell.

That combination, periodic copies together with a rotary motion in an
unsteady run, HAS been run on a licensed solver by this repository's own
QA case PHY-05, on 26.120 and again on 26.123, inside its bands. Read
that as evidence about the SOLVER and not about this workflow: PHY-05 is
a hand-built script, and no script the `unsteady_rotor` workflow builds
has run on a licensed solver. What is not established here is whether a
`BLADES` count may divide the phase-locked averaging window on the
strength of it, which is why the limits list still says `BLADES`
configures no rotor.

**A mean taken from few revolutions, or at a coarse time step, sits below
the developed wake.** An `unsteady_rotor` point's thrust and torque are still
moving after the start-up revolution: on a six-blade research propeller
measured on 26.124 the thrust gained about 0.5 % per revolution and had not
levelled at revolution 6 (RPT-089). A finer time step raises the mean thrust
too, not only more revolutions: at the third revolution the thrust sat 8.4 %
below the quasi-steady wheel's at 10 deg per step, 6.6 % at 5 deg and 4.0 %
at 2.5 deg, and halving the step roughly doubled the gain per revolution, so
neither the step nor the revolution count had converged at the finest step
run. A `LAST_REVS_AVG` window over the third revolution of a
three-revolution run at 10 deg per step is therefore a mean of a wake still
developing; refine the step and run more revolutions before the window when
the absolute level matters, and compare points at the same step and the same
revolution count when the difference between them is what matters.

## A rotor row states the decisions, and the arithmetic is derived

A rotor study is designed in an advance ratio and an azimuthal step.
The rev/min, the seconds per step and the number of steps are what those
work out to at the run's own velocity, so an `unsteady_rotor` row states
the decisions and the package derives the rest.

* `ADVANCE_RATIO: <J>` sets the rotor speed as `n = V / (J D)`, against
  the velocity this row already resolves and the diameter `D`. **Since
  0.15.0 that diameter is the ROTOR'S OWN** where the motion names an
  rotor block of the reference, so one ratio written once gives rotors
  of different sizes different speeds (FR-63); where no alias is cited it
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

* `LOG_OUTPUT: <n>` names WHICH of the row's own `OUTPUTS` is the solver
  log, counted from 1, and the workflow then emits `EXPORT_LOG` for it.

    **It is what makes a convergence verdict possible at all.** An
    unsteady time loop always reaches its prescribed end, so the
    iteration counter judges nothing, and without a log every unsteady
    run is recorded `COMPLETED_MAX_ITER` whether it converged at every
    time step or at none. That word is a statement about the evidence
    and it reads as a statement about the solver. With a log the verdict
    is the final residual against the row's own convergence limit.

    It is a POSITION and not a file name because the names carry the
    point placeholder in the cell and reach a builder already rendered:
    the cell says `loads_{point}.txt` and the case carries
    `loads_M200RE230AL+000.txt`, so a name could never match. Order survives
    rendering; a name does not.

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
  run in. See [exports that begin after a threshold](#exports-that-begin-after-a-threshold)
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
  POL   point                    rotor       M_tip  M_hel
  9001  M144RE438AL+000RPM03000  rotor PORT  0.554  0.572
  9001  M144RE438AL+000RPM06000  rotor PORT  1.108  1.117
```

and warns, naming each point, when a helical Mach number is 1 or more
(`M_hel >= 1`, the tip sonic or supersonic):

```text
helical Mach >= 1 on 1 polar point(s): POL 9001 point M144RE438AL+000RPM06000,
rotor PORT, M_hel 1.117. ...
```

A disc's row reads `actuator PROP` in the rotor column. The plan refuses nothing for
the warning. A rotor whose reference states no diameter for it has no known
radius: the plan says so naming the row instead of a number. The
definitions, and where else the two numbers appear (the run record, the
rotor table), are in
[the definition of record](post-processing-definitions.md#tip-and-helical-mach-numbers).

**THE RESERVED NAMES ARE THESE, AND THE LIST HAS GROWN TWICE.**
`VAR_NAMES_VALUES` is your namespace except for the keys the package
itself reads, and a cell of yours that already spells one of them is
read by the package rather than ignored:

| release | names it reserved |
|---|---|
| before v0.8.1 | `VELOCITY`, `RPM`, `ROTOR_AXIS`, `ROTOR_ORIGIN`, `ROTOR_SHEDDING`, `BLADES`, `MOVING_BOUNDARIES`, `DELTA_TIME`, `TIME_ITERATIONS`, `WINDOW_DEGREES`, `WINDOW_STEPS`, `WINDOW_REVOLUTIONS`, `OUTPUTS` |
| v0.8.1 | `GEOMETRY`, `SYMMETRY`, `PERIODIC_COPIES` |
| v0.10.0 | `ADVANCE_RATIO`, `RPM_SIGN`, `DELTA_THETA`, `REVOLUTIONS`, `LOG_OUTPUT` |
| v0.10.1 | none. What changed is what `MOVING_BOUNDARIES` ACCEPTS: see below |
| v0.11.0 | `MOTIONS`, a list of records, one rotor each: `MOTIONS: {MOVING_BOUNDARIES: Blade1 / RPM: 1200 / RPM_SIGN: 1 / ROTOR_AXIS: X / ROTOR_ORIGIN: ERP1}, {...}`; a record's `ROTOR_ORIGIN` is three coordinates or the name of a rotor point of `inputs/reference_points.toml`, and no flat motion key may stand beside the list (PFS-2029.11) |
| v0.11.0 | `BASE_REGIONS`, the boundaries that BECOME base regions, one `DETECT_BASE_REGIONS_BY_SURFACE` per boundary of them after `OPEN`: a body's flat base (`BASE_REGIONS: Base`), never the body that carries it, which the command takes and marks nothing on, silently (stated since 0.27.0, RPT-066; see below). It overrides the pproc artifact's `base_regions`, and naming none emits nothing (PFS-2029.10) |
| v0.13.0 | `EXPORT_UNSTEADY_AFTER_REV` and `EXPORT_UNSTEADY_AFTER_ITER`, the step the per-step exports begin on, one per row at most; the first on `unsteady_rotor` only, both refused on `steady` (PFS-2031.18) |
| v0.13.0 | none. What changed is that the list above is now CLOSED for a workflow row: a key no run type registers is refused at `pyfs-matrix plan` (PFS-2008.02.01), see below |
| v0.14.0 | none. What changed again is what `MOVING_BOUNDARIES` ACCEPTS: a name the row's setup defines under `[aliases]`, between the exact label and the family, see What a solver preset may say |
| v0.14.0 | `ROTATE`, a list of records, one rotation of the opened mesh each, in the order written: `ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: Blade,S / AUX_FRAMES: ROTOR_MRP}, {...}`; on every run type; the frame is one the setup defines or the package creates, the families are names, never indices (PFS-2034.02), see [One row, one geometry, turned](workflow-row-geometry-motion.md#one-row-one-geometry-turned) |
| v0.15.0 | `MOVING_BC_ALIAS`, the rotor a motion record moves, an alias the reference declares as a rotor block. It is the ONLY rotor identity a row carries: the hub, the axis, the sign, the blade count and the diameter come from that block, and a record stating `MOVING_BOUNDARIES`, `ROTOR_AXIS`, `ROTOR_ORIGIN`, `RPM_SIGN` or `BLADES` beside it is refused naming both (FR-61) |
| v0.15.0 | `CLOCK_MOTION`, which of the row's motions owns the time step and the run length. REQUIRED on any row that states a `MOTIONS` list: a row that states the list and no key is refused, naming the motions it could have named. The flat pre-0.15.0 form, which names one rotor in its own keys, is exempt because it has nothing to choose between; that form becomes required at 0.17.0 too (FR-64) |
| v0.15.0 | `SYMMETRY_LOADS`, whether the solver reports the loads of the meshed sector or of the whole wheel. On every run type, because a mirrored or periodic mesh is opened by a steady row too; a row stating it overrides the preset and warns naming both files (FR-66) |
| v0.15.0 | `RAW`, a list of records, one raw solver command each or one file of them, in the order written: `RAW: {COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}, {FILE: raw/extra.txt / BEFORE: init}`; a record states `COMMAND` or `FILE` and never both, and `BEFORE`, the phase it goes before, spelled as the preset's `[[raw]]` table spells it. **ITS PAIRS SPLIT ON A SPACED SLASH**, ` / `, and not on the bare one every other record kind uses, because its values are a path and a command line and both carry slashes of their own. A raw file is a path under `inputs/` whose blank lines and `#` lines are skipped (FR-67), see [What a solver preset may say](workflow-input-library.md#what-a-solver-preset-may-say-and-what-happens-to-a-key-that-reaches-nothing) |
| v0.17.0 | `COLD_START`, whether a steady row clears the solver between the points of its sweep. Warm is the default and this is the opt-out (FR-95); and `RESTART`, how to continue a run the wall clock stopped, which v0.17.0 PARSED and refused to run (FR-96) |
| v0.17.0 | **FOUR NAMES LEFT THIS CELL AND BECAME COLUMNS**: `GEOMETRY`, `SYMMETRY`, `SYMMETRY_LOADS` and `NCPUS`, which lived here or in the setup and now have a column each, beside the two that are new in both homes, `CONFIGURATION` and `WALLTIME` (FR-93). A row that states one of the six in BOTH homes is refused naming both. The rows above still show the cell spelling because that is what a file written before 0.17.0 carries, and `pyfs-matrix upgrade` moves them |
| v0.18.0 | `RESTART` now RUNS (FR-96). Two further names are reserved and they are the PACKAGE'S to set, never a row's: `RESTART_FROM`, the saved simulation a continuation opens, and `RESTART_ITERATIONS`, the remaining step count. The run path resolves both from the recorded run being continued and writes them onto the case; a row that states either is refused, because stating them by hand would skip the resolution that checks a recorded run exists, that its status is continuable, and that its outputs are archived before they are replaced |
| v0.19.0 | `TRANSLATE`, a list of records, one translation of the opened mesh each, in the order written and before every rotation: `TRANSLATE: {DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}, {...}`; on every run type that reads `ROTATE`, the distance in metres along one axis of the named frame (FR-100), see [One row, one geometry, moved](workflow-row-geometry-motion.md#one-row-one-geometry-moved) |
| v0.23.0 | `LAST_REVS_AVG` and `LAST_ITERS_AVG`, the AVERAGING WINDOW of an unsteady point, one per row at most: the first on `unsteady_rotor` only, a count of the last revolutions that accepts a float (`LAST_REVS_AVG: 0.25`); the second a count of the last iterations, the key of an `unsteady` row and read on a rotor row too. Written in UPPER CASE like every key of this cell, which is matched on its exact spelling: `last_revs_avg` is refused as a key of no run type. A row stating both is refused naming both. Since 0.26.0, `WINDOW_DEGREES`, `WINDOW_STEPS` and `WINDOW_REVOLUTIONS` are refused: write `LAST_REVS_AVG` or `LAST_ITERS_AVG`, dividing degrees by 360. See [The window, said once](workflow-plan-and-cost.md#the-window-said-once) and [the definition of record](post-processing-definitions.md#the-averaging-window) |
| v0.27.0 | `ADDITIONAL_PPROC`, ONE pproc id (`ADDITIONAL_PPROC: p002`), on every run type and read by NO builder: a row stating it runs byte for byte as it would without it, and `pyfs-matrix post --additional-pproc` extracts that pproc from each point's final saved simulation with no solve (G12). Refused on a `LEGACY` row and on a build other than 26.124; a comma list is not one id and is refused like any id of the wrong shape. See [Extracting more from a finished point](workflow-additional-post.md#extracting-more-from-a-finished-point-the-additional-post) |

**`BASE_REGIONS` NAMES THE BASE, NOT THE BODY.** The command it emits,
`DETECT_BASE_REGIONS_BY_SURFACE <index>`, takes the boundary that becomes the
base region. On a body whose flat base is its own boundary, 20_BODY's
`[Body, Base]`, `BASE_REGIONS: Base` marks the base, the same faces
`AUTO_DETECT_BASE_REGIONS` marks, and `BASE_REGIONS: Body` marks nothing and
says nothing (RPT-066, 26.124). A row naming the body therefore solves with no
base region and no error; name the base boundary. A pproc's `base_regions`
list follows the same rule. A raw mesh's sidecar can ask for the whole-mesh
detection instead, `[base_regions] detect = "auto"`
([mesh inputs](mesh-inputs.md#the-boundary-conditions-of-a-raw-mesh)).

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
read for a case authored in Python and nowhere else. `ADVANCE_RATIO` is
registered on every run type because the point NAME reads it (the `J`
field, PFS-2029.19) and the export names carry it into the script.

**`MOVING_BOUNDARIES` NAMES SURFACES, AND SHOULD NOT COUNT THEM.** Write
the boundary names the geometry carries, or a FAMILY name, which is a
boundary label with its trailing number removed:

```
MOVING_BOUNDARIES: Blade,S
```

One cell, and it is right for every geometry in a study. On a sector mesh
holding `Blade1, S, N` it moves the first two; on the full wheel holding
`Blade1, S, N, Blade2 ... Blade6` it moves all six blades and the spinner.
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
`g<number>` (PFS-2028.00): `MOVING_BOUNDARIES: g4` moves the members of
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
before the save (RPT-044), planned READY until 0.13.0 and every polar
table of the row would have summed nothing. What is refused is the
artifact and the geometry sharing NO name, not a member missing from one
group: an artifact is written once for a study and shared by rows
opening different geometries, so a family a file lacks is left out by
design, and `p002`'s group 3 (`Body`, `Base`) sums to zero on the wing
rows exactly as the reference products carry it.

`angle_sweep_deg` IS RESERVED TOO, since v0.7.0, and it is the one whose
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

**`REVOLUTIONS` AND `DELTA_THETA` ARE THE TWO TO CHECK FIRST**, because
they are ordinary words a rotor study is likely to have already used for
its own bookkeeping. A cell of yours spelling either is now the
package's, so rename yours or adopt the meaning.

The match is on the EXACT key, so a cell spelling it `SYMMETRY_TYPE` or
`N_REVOLUTIONS` is untouched. The rows of [the run matrix](workflow-run-matrix.md) use `FSM_FILE`, a key of
their own that nothing in the package reads; moving a row off `LEGACY`
is the moment to rename it to `GEOMETRY`, and a row that stays on
`LEGACY` keeps its recipe and its own key with nothing changed for it.

v0.9.0 added a larger upgrade risk than any name, the removal of the
`RE` and `MACH` columns, which is handled by
`pyfs-matrix upgrade <path> --in-place` and described on
[the flight-condition page](flight-conditions.md).

A row that names none of the three behaves exactly as it did before, and
that is measured rather than promised, in two separate ways because they
are two separate claims.

Going forward, every workflow crossed with three case shapes and every
build it covers is pinned as a committed golden under
`tests/tier1_offline/goldens/workflows/` and compared byte for byte on every run of the
suite. On one of the workflow-and-build pairs, `steady` on FlightStream
25.000, the builder refuses instead of rendering, and both of that pair's
goldens pin the refusal text; the changelog's "Known gaps" says why.

Looking back, the same four case shapes were rendered against a worktree
at the `v0.8.0` tag: every render came out byte for byte identical, and
the two refusals matched their text as well. That is the half the goldens
cannot prove on their own, since they were generated from this release.
The receipt is committed beside them.

Four runs come out of those two rows of `matrix_registry.fs`. Nothing in the matrix says where
anything is written, and that is deliberate: naming is the workspace's
job.

## One row, several rotors

A rotor row states its motion flat, `RPM`, `RPM_SIGN`, `ROTOR_AXIS`,
`ROTOR_ORIGIN` and `MOVING_BOUNDARIES` as keys of the cell, and that is one
rotor. Since v0.11.0 a row may state several (PFS-2029.11): `MOTIONS: {...},
{...}`, each pair of braces one rotor holding those same keys, the pairs
inside separated by `/` as in the flat cell and the records by commas. The
builder then creates, per record, a fixed frame at the record's hub
(`<ALIAS>_SMRP`, one per record), a moving frame turned by the motion
(`RotorAxis1`, ...) and one `CREATE_NEW_MOTION` block citing its own frame,
axis, speed and boundaries; each rotor's `<ALIAS>_SMRP` is the frame the pproc
entries cite, the time step follows the rotor `CLOCK_MOTION` names, and the run record
lists every record as bound. A record's `ROTOR_ORIGIN` may name a point of
`inputs/reference_points.toml` instead of three coordinates; the point must
be a rotor point, `ERP` or `ERP1` through `ERPn` by the naming convention,
and a motion on a point declared `kind = "airframe"` is refused naming the
point and its kind. A name outside the convention is refused when the file is
read, whatever kind it declares, because the names are what say how many
propulsors the campaign describes (measured 2026-09-08 on the tier-3
workspace, which had named a hub `HUB`). Since 0.13.0 the flat rotor row's
own `ROTOR_ORIGIN` may name a point the same way (PFS-2031.12); until then
only a `MOTIONS` record could, and the one-rotor row demanded three numbers. A flat row renders
exactly as before; a row with a `MOTIONS` list and a flat motion key beside
it is refused, as is an unclosed brace or a record repeating a key.

A point opens its geometry through a link (PFS-2029.17): `sims/<sim>/inputs`
is a directory junction on Windows and a symbolic link elsewhere, pointing at
`inputs/geometries/`, so a campaign of forty points holds one copy of each
mesh and the record still carries the opened path and its sha256, with
`staged_as: link`. A geometry that has its own folder,
`inputs/geometries/30_WB/`, is linked at that folder (PFS-2032.04), so the
point's inputs show that geometry's files, its boundary inventory among
them, and never the rest of the library. Where a link cannot be made, the
inputs are copied and the record says `staged_as: copy` with the reason.
Archiving writes the link as a one-line `inputs/STAGED_AS_LINK.txt` and
never the library's bytes.

The boundary order of a staged geometry is read from the file and written
beside it, never stated in a setup (PFS-2029.06; `docs/mesh-inputs.md`),
which puts it inside the geometry's folder when the geometry has one:

```text
pyfs-matrix inventory inputs/geometries/30_WB.fsm    # writes 30_WB.boundaries.toml
```

An `.obj` gets its sidecar from its groups the same way, and from the plan
itself when it has none (since 0.28.0, G30, `docs/mesh-inputs.md`).

A workspace written before v0.11.0 moves in one command:

```text
pyfs-matrix upgrade matriz.fs --in-place --inputs inputs
```

which renames the column, drops `FS_SCRIPT`, moves `inputs/groups/e001.toml`
to `inputs/pproc/p001.toml` under a `[groups]` header (the file's own lines,
comments and all), and gives the cells that named it their `p`.

**A workspace written before v0.15.0 moves with the same command**, which
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
  rename`; see [migrating to 0.21.0](migrating-to-0.21.0.md).)
* **It stops on a row that varies BOTH angles**, naming every such row.
  That row is one run per sideslip and each new row needs a POL of its
  own, which is run identity and not a converter's to invent. Split them
  by hand, giving each the POL you want, then run the command.

## Exports that begin after a threshold

A rotor run settles over its first revolutions, and the loads, sections
and probes worth keeping are the ones after that. `EXPORT_UNSTEADY_AFTER_REV`
states the revolution the per-step exports begin at; `EXPORT_UNSTEADY_AFTER_ITER`
states it as a time step instead. Put one of them on row 7001 of [the workflow matrix](workspace-and-workflows.md),
with the azimuthal clock:

```text
VELOCITY: 30.0 / RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_THETA: 10 / REVOLUTIONS: 3 / LAST_REVS_AVG: 0.25 / EXPORT_UNSTEADY_AFTER_REV: 2
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
environment (RPT-041), so the first action is a small Python program the
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
step's Tecplot file since 0.28.0), the sections, the sectional
loads and the probes, whichever the pproc artifact's export set kept.
The saved simulation, the plots file and the log describe the whole run
and stay at the end. A row stating both keys is refused naming both; a
threshold beyond the run is refused naming both numbers; the revolutions
form on `unsteady` is refused naming the iterations form that would work,
because a run that turns nothing has no revolution to count.

This replaces the degrees-backwards window of PFS-2025.08 for the mid-run
exports: the exports begin AFTER a threshold, in the reference definition, and the
`WINDOW_*` keys keep their one job, the averaging window of the
reductions.

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
and has nothing to split and nothing named; a record written before 0.27.0
without a layout is given the empty one when its recorded script still hashes
as recorded and creates no surface section, and a continuation records the
layout of the run it continues. Older layouts require an unambiguous match to their recorded pproc, read over the
geometry's boundary names where the record carries them or its geometry hash
recovers them, for a block recorded in a common frame; a block in a frame spelt
like a rotor's is matched over the recorded cuts, as in 0.26.0. See the
[sections definitions](post-processing-definitions.md#per-distribution-sectional-loads-and-cp-0250).

**The stamped files as a series** (since 0.14.0, PFS-2031.18.01). Thirty
seven spreadsheets are not a history until something tables them, so the
products stage writes, per windowed point, one table per export kind
under `post/<matrix stem>/series/`:

```text
post/matriz/series/P7001-M144RE438AL+000BE+000_loads_series.csv
post/matriz/series/P7001-M144RE438AL+000BE+000_sections_series.csv
post/matriz/series/P7001-M144RE438AL+000BE+000_probes_series.csv
```

Every table leads with `POL` (since 0.27.0), then `STEP` (spelled `step` until
0.24.0), `time_s` and `azimuth_deg`, and then states the point's condition
block; the probes series says WHICH probe each row is in `PROBE`, and the
sections series leads with `POL`, `STEP`, `time_s`, `FAMILY`, `PLANE`, `ROTOR`,
`AZIMUTH`, the identity the
sections table carries. `time_s` and `azimuth_deg` are the step's
time and azimuth computed from the clock the run record carries
(`export_window.delta_time_s` and `step_deg`, written by the run since
0.14.0) by the same arithmetic the counter program runs on the machine,
so the two agree by construction; a record written before the clock
leaves the time unstated -- which the table writes as `NA`, blank until
0.23.0 -- and reads the azimuth off its reductions plan. The
loads series is wide, one row per step and one column per surface and
coefficient (`Total_CL`, `Blade1_CMx`, ...); its moment columns are about
the row's moment point, and a loads series written before 0.27.0 from an
unsteady row states them about the reference frame's origin, with its
forces right (RPT-064); the sections series (from
the sectional loads export, `_sloads`, the same export the sections
table of the products reads) and the probes series are long, one row per
step and section or probe, with the export's own columns. A kind with no
stamped file is NOT written, and `products.json` names it under `skipped`
with the folders that were searched (a header-only table recorded as written,
until 0.24.0). The stamped files are looked for where the point RAN: its
`datapoints/DP-<point>/`, where every point runs since 0.27.0, and the
simulation folder, where a local point ran before 0.27.0. A
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

## The four reductions of an unsteady case

An unsteady rotor case asks for four things and gets four files: the
**raw series**, the **time average** over [the window](workflow-plan-and-cost.md#the-window-said-once), the
**phase-locked** average (the same average, once per blade passage) and
the **per-blade split**. The raw series is written first and ships
beside all three; it is never replaced by them, so an average always has
its history next to it.

`reduction_plan(case)` is what says WHICH windows those are, off the
row: one revolution is `60 / (RPM * DELTA_TIME)` solver steps and one
blade passage is that divided by the blade count, which a row naming its
rotors takes from each rotor's own block and a row naming none takes from
`BLADES`. The averaging itself is
`pyflightstream.post.unsteady.blade_passage_average`, the one
implementation of that average in the package, and writing one is
`pyflightstream.post.reductions`, which refuses to write a reduction
over a file it read.

What does NOT ship yet is the step that runs those four automatically
after a campaign. The composition is executed in the suite, so the path
is proven; wiring it into the run is the next item, and the reason it is
not here is the layer order rather than an oversight (post-processing
sits above execution, so the runner cannot call it).
