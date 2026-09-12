# The workspace and the workflow

A **workspace** is the folder this package owns. You point it at a
directory, and from that moment the layout inside is the library's
business rather than yours: where a run's script goes, where its outputs
land, where the record of what happened is kept. That is the whole idea.
A study that organises itself by folder names is a study whose evidence
lives in your memory, and folder names are never authoritative here.

Two things live in a workspace and they are worth separating in your
head before anything else.

The **input library** is what you bring. Reference quantities, solver
presets, boundary groups, geometry, profiles: each is a small file with
an identifier, staged once, and referred to afterwards by that
identifier rather than by a path. Several studies reuse the same
reference area without copying it, and when you change it you change it
in one place.

The **run record** is what the library writes. Every point that
executes leaves a row saying which run it was, which build of
FlightStream ran it, the hashes of the script and the inputs, how it
terminated, how long it took and which files it produced. Nothing is
inferred from a folder name afterwards, because a folder can be renamed
and a record cannot be renamed into agreement with itself.

A **workflow** is a run TYPE the package already knows how to build. A
row says `unsteady_rotor` and the package writes the whole script for
it: no Python, no function of yours, nothing between the file and the
result. That is the difference between a workflow and a recipe, and it
is worth being exact about because the two look similar from a
distance. A recipe is a function YOU write and name by reference; the
package imports it. A workflow is looked up in this package's own
table, and there is deliberately no way to put your function in that
table, because a type this package builds is a type it can also refuse
before it runs.

The section at the bottom of this page says what is still not built.
What follows is what ships today.

## What a run matrix is

A run matrix is a pipe-separated table, one row per simulation, that
this package reads forever: the format is a first-class interface
rather than an import step (FR-10, FR-35). Each row names a point of
interest, the sweep it wants, and, by identifier, the reference, the
solver preset and the boundary group it should be resolved against.

This is the matrix the test suite runs, byte for byte:

```text title="matrix_registry.fs"
POL  | AIRCRAFT  | DESCRIPTION            | FLIGHT_CONDITION | SWEEP_VALUES   | REF  | SET  | PPROC  | FS_BUILD | HIDDEN | RUN | WORKFLOW | VAR_NAMES_VALUES
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
8001 | TestWing  | REGISTRY_ALPHA         | MACH:0.0890, REmi:3.10, ALPHA:sweep | 0.0,2.0        | r003 | s002 | p001   | 26.120   |    0   |  1  | LEGACY   | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt / RECIPE: 003
8002 | TestWing  | REGISTRY_BETA          | MACH:0.0890, REmi:3.10, BETA:sweep | -3.0,3.0       | r003 | s002 | p001   | 26.120   |    1   |  1  | LEGACY   | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt / RECIPE: 003
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
other key is a quantity the row HOLDS. Until v0.15.0 the swept variable
was named a second time in a `SWEEP_TYPE` column, which is the column
`pyfs-matrix upgrade` folds into this cell. `REF`, `SET` and `PPROC` are the
three identifiers that reach into the input library; `PPROC` was `ENTRY`
until v0.11.0, when the groups artifact it names became the
post-processing artifact (PFS-2029.07). `FS_BUILD` names the FlightStream
build the row wants. `WORKFLOW` names the run type, and a row naming one
needs nothing else to build its script; `LEGACY` means "none, use the
recipe", which is what every matrix written before v0.8.0 means and what
these two rows say, and such a row names its recipe code as the `RECIPE`
key of its variables (until v0.11.0 that code sat in a column of its own,
`FS_SCRIPT`, which `pyfs-matrix upgrade` moves). Since 0.13.0 that cell may
carry the reference itself, `package.module:function`, and a row written so
plans and runs with no `--recipe` option at all; a bare code such as `003`
is still mapped by that option (PFS-2031.11). `RUN` is the switch that
says whether the row takes part at all.

`VAR_NAMES_VALUES` is the last cell and the one that carries everything
else, as `KEY: value` pairs separated by ` / `. The rows above use
`FSM_FILE`, which is a key of THEIR OWN: nothing in the package reads it,
and the recipe named by the row's `RECIPE` code is what resolves it and
opens the file. That is still how a recipe works.

**A WORKFLOW reads keys the package defines**, and since v0.8.1 three of
them close the gap that made the capability unusable:

* `GEOMETRY: <file name>` names a geometry staged under
  `inputs/geometries/` by its FILE NAME, extension included: with
  `wing_clean.fsm` staged, the cell reads `GEOMETRY: wing_clean.fsm`, and
  `blade.v2.fsm` reads one way and no other. A bare stem is refused
  naming the files that carry it, and `pyfs-matrix upgrade` completes
  every stem-only cell of an older matrix with `.fsm` (until v0.11.0 the
  cell was the stem; PFS-2029.09). What the name buys is that the cell
  says what the file is: a `.fsm` carries its boundary conditions, a
  mesh does not, and a workflow row naming a mesh is refused before any
  seat is spent, naming 0.12.0 as the release that defines them. The
  workflow opens the file first, before anything else, and it opens the
  STAGED copy, so the file the manifest hashed and the file the solver
  read are the same bytes.

    A WORKFLOW opens a saved simulation, a `.fsm`, and nothing else. That
    is a property of the two built-in builders rather than of the key: a
    recipe of your own receives whatever the library staged and imports
    it declaring the units itself. The narrowing exists because importing
    a raw mesh takes the mesh's length units as an argument
    (SRC-003 p.307) and no matrix cell declares them, so the package
    would have to default one, and a defaulted unit is a body of the
    wrong size whose coefficients solve, export and report without a
    word. The refusal points at
    [mesh inputs and GUI-only operations](mesh-inputs.md): open the mesh
    in the window once, save a `.fsm`, script everything after.
* `SYMMETRY: <mode>` and, where the mode needs it, `PERIODIC_COPIES: <n>`.
  The accepted modes are read from the command database for the row's own
  build, never from a list written here. **This one is not a
  convenience.** Until v0.8.1 symmetry was fixed at `NONE`, so a periodic
  sector was solved as a one-bladed rotor: the run completed and the
  numbers were wrong, silently.

    `MIRROR` carries three cautions, and since 0.13.1 the cell enforces
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
    image (SRC-003 p.217). And a workflow cannot make the post-mirror
    loads setting explicit, because no cell reaches it: the run takes the
    solver's own default. That default was calibrated on a licensed
    26.120 as ENABLE, so the loads are the full model's, which is what a
    mirrored study wants. It is a default rather than a declaration, and
    it is measured on ONE build: the user guide emits it explicitly for
    that reason. A study that needs it stated is a recipe today.

### A rotor row states the decisions, and the arithmetic is derived

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

    A ratio is a magnitude, so `RPM_SIGN: 1` or `RPM_SIGN: -1` carries
    the hand of the rotation, defaulting to `1`. It is refused beside an
    explicit `RPM`, which carries its sign in the number itself. A
    configuration whose isolated and installed meshes are opposite hands
    needs opposite signs for one published sense of rotation, and the
    row is where that choice belongs, because only the row knows which
    mesh it opened.

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
    `loads_a+00.0.txt`, so a name could never match. Order survives
    rendering; a name does not.

* `EXPORT_UNSTEADY_AFTER_REV: <turns>` or `EXPORT_UNSTEADY_AFTER_ITER:
  <steps>`, at most one per row, is the step the PER-STEP exports begin
  on. From that step to the end of the run the solver exports every
  per-step kind of the row's output set after each time step, and stamps
  each file with the iteration: a row whose stem is `POLAR-7001_...`
  leaves `POLAR-7001_..._iteration=72.txt`, `_iteration=73.txt` and so
  on beside the end-of-run export of the same name. Revolutions are
  counted on the rotor the run turns, so that form belongs to
  `unsteady_rotor`; `unsteady` takes the iterations form only, and a
  steady row is refused either, having no time loop for an action to
  run in. See [exports that begin after a threshold](#exports-that-begin-after-a-threshold)
  for the worked example and what the run leaves.

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
| v0.11.0 | `BASE_REGIONS`, the mesh families the base-region autodetect may consider, one `DETECT_BASE_REGIONS_BY_SURFACE` per boundary of them after `OPEN`; it overrides the pproc artifact's `base_regions`, and naming none emits nothing (PFS-2029.10) |
| v0.13.0 | `EXPORT_UNSTEADY_AFTER_REV` and `EXPORT_UNSTEADY_AFTER_ITER`, the step the per-step exports begin on, one per row at most; the first on `unsteady_rotor` only, both refused on `steady` (PFS-2031.18) |
| v0.13.0 | none. What changed is that the list above is now CLOSED for a workflow row: a key no run type registers is refused at `pyfs-matrix plan` (PFS-2008.02.01), see below |
| v0.14.0 | none. What changed again is what `MOVING_BOUNDARIES` ACCEPTS: a name the row's setup defines under `[aliases]`, between the exact label and the family, see What a solver preset may say |
| v0.14.0 | `ROTATE`, a list of records, one rotation of the opened mesh each, in the order written: `ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: Blade,S / AUX_FRAMES: ROTOR_MRP}, {...}`; on every run type; the frame is one the setup defines or the package creates, the families are names, never indices (PFS-2034.02), see [One row, one geometry, turned](#one-row-one-geometry-turned) |

| v0.15.0 | `MOVING_BC_ALIAS`, the rotor a motion record moves, an alias the reference declares as a rotor block. It is the ONLY rotor identity a row carries: the hub, the axis, the sign, the blade count and the diameter come from that block, and a record stating `MOVING_BOUNDARIES`, `ROTOR_AXIS`, `ROTOR_ORIGIN`, `RPM_SIGN` or `BLADES` beside it is refused naming both (FR-61) |
| v0.15.0 | `CLOCK_MOTION`, which of the row's motions owns the time step and the run length. REQUIRED on any row that states a `MOTIONS` list: a row that states the list and no key is refused, naming the motions it could have named. The flat pre-0.15.0 form, which names one rotor in its own keys, is exempt because it has nothing to choose between; that form becomes required at 0.17.0 too (FR-64) |
| v0.15.0 | `SYMMETRY_LOADS`, whether the solver reports the loads of the meshed sector or of the whole wheel. On every run type, because a mirrored or periodic mesh is opened by a steady row too; a row stating it overrides the preset and warns naming both files (FR-66) |
| v0.15.0 | `RAW`, a list of records, one raw solver command each or one file of them, in the order written: `RAW: {COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}, {FILE: raw/extra.txt / BEFORE: init}`; a record states `COMMAND` or `FILE` and never both, and `BEFORE`, the phase it goes before, spelled as the preset's `[[raw]]` table spells it. **ITS PAIRS SPLIT ON A SPACED SLASH**, ` / `, and not on the bare one every other record kind uses, because its values are a path and a command line and both carry slashes of their own. A raw file is a path under `inputs/` whose blank lines and `#` lines are skipped (FR-67), see [What a solver preset may say](#what-a-solver-preset-may-say) |

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
same way and named with that type: `WINDOW_DEGREES: 90` on a `steady` row
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
`N_REVOLUTIONS` is untouched. The rows above use `FSM_FILE`, a key of
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

### One sweep per row, and the geometry variant that is its own row

A row sweeps ONE thing. The swept key of `FLIGHT_CONDITION` and
`SWEEP_VALUES` sweep the
aerodynamic condition, and a geometric variation of the same
configuration, a rotated blade or a trailing-edge variant, does **not**
multiply with it. A row that asks for both is refused when the file is
read, before a workspace is opened and before a solver is started, and
the refusal names the row, both sweeps and the count of runs they would
have produced.

The rule is the same in a hand-written `campaign.toml`: a `[[sim]]`
declaring a multi-angle `angle_sweep_deg` beside a multi-point `sweep`
is refused when the file loads, which is the moment the case is
declared. Neither door lets in what the other refuses.

### What a row's sweep looks like in `campaign.toml`

`pyfs-matrix convert` writes the row's sweep as one inline table, and a
hand-written file may write the same thing:

```toml
[[sim]]
sim_id = "9001"
sweep = {type = "alpha", values = [-4.0, 0.0, 4.0], held = {beta = 0.0}}
```

`type` is the ONE variable that varies, `values` are its values in
degrees, and **`held` is what the row keeps constant at every point of
the sweep**, in degrees, under the same axis names. `held` is what makes
`ALPHA:sweep, BETA:0.0` in a matrix row and the paired `AL/BE` cell it
replaced plan the same three runs under the same three names,
`a-04.0_b+00.0`, `a+00.0_b+00.0` and `a+04.0_b+00.0`: the point tag ends
the `run_id`, so a held angle has to reach the point or the upgrade
would rename every run that has one.

It holds the two ANGLES and nothing else. A key that is not a point axis
is refused naming the axes, and so is a `held` entry for the variable the
sweep already varies. An advance ratio the case holds goes in its
variables, where it went before this release.

`held` is omitted when the row holds nothing, so a file written before
0.15.0 loads unchanged. The paired `type = "alpha_beta"` still loads and
is deprecated: write `type = "alpha"` with the sideslip in `held`, which
plans the identical runs.

Write it one of two ways.

- **One rotation, held fixed across the aerodynamic sweep.** Put
  `angle_deg: 5.0` in `VAR_NAMES_VALUES` (or `angle_deg = 5.0` under
  `[sim.variables]`). One value. The row keeps its alpha sweep and stays
  one row.
- **A sweep of the geometry.** One row per angle, each with its own
  `POL` and a single-valued `angle_deg`. Three angles across an eleven
  point alpha sweep are three rows of eleven runs, not one row of
  thirty three.

The limit is about IDENTITY before it is about cost. A run is named by
its aerodynamic point: the folders above are `a+00.0` and `b-03.0`, and
nothing in that name is geometric. Crossing three angles into an eleven
point sweep would give thirty three runs eleven names, so each group of
three would share one `run_id` and one set of output file names, and the
cost view would average the three into a single cell. Three rows cost
the same thirty three runs and keep thirty three identities.

## The input library those identifiers resolve against

The three code columns are looked up in the workspace's own `inputs/`
folder. This is the library the suite stages for the example below:

```text
inputs/
  references/r003.toml    area_m2 = 10.0, chord_m = 1.2, span_m = 8.0
  references/r004.toml    area_m2 = 12.0, chord_m = 1.5, span_m = 9.0
  setups/s002.toml        iterations = 800, convergence = 1e-6
  setups/s003.toml        iterations = 400, wake_layers = 4
                          (wake_layers is RECORDED and emits nothing;
                           see the preset section below)
  pproc/p001.toml         [groups] wing = ["wing_left", "wing_right"], body = [1]
                          (the post-processing artifact; its [groups] table is
                           what the groups file held until v0.11.0)
  executables.toml        which executable, and optionally which version,
                          each build identifier means
  executables.local.toml  this machine's paths for the same identifiers,
                          gitignored; read over executables.toml when present
```

`REF r003` therefore means "the reference quantities in
`inputs/references/r003.toml`", and both rows of the matrix above use
the same one. The identifier is yours to choose; the matrix and the
file name simply have to agree. An identifier that is not staged is
refused before anything runs, and the refusal names the identifier, the
kind and what is available.

### The geometry library: flat, or one folder per geometry

`inputs/geometries/` is read in two layouts, and the `GEOMETRY` cell is
the same in both (PFS-2032.04, the reading of 2026-09-08). Flat, the
file sits directly in the folder with its boundary inventory beside it;
one folder per geometry, the file sits in a folder named by its stem,
and everything that belongs to that geometry sits with it:

```text
inputs/geometries/
  30_WB.fsm                    flat: the cell reads GEOMETRY: 30_WB.fsm
  30_WB.boundaries.toml
  31_TAIL/                     one folder per geometry: the same cell,
    31_TAIL.fsm                GEOMETRY: 31_TAIL.fsm, resolves here
    31_TAIL.boundaries.toml
    31_TAIL.provenance.toml
```

The package looks in `geometries/<stem>/` first and at
`geometries/<file>` second, so no matrix written since v0.11.0 changes
and a library can hold both layouts while it moves. What the folder
buys is a home: the inventory sidecar and the provenance record stop
being loose files among forty others, and a point staged from a folder
shows that geometry's files only, never the whole library (the link
under `sims/<sim>/inputs` points at the folder; see "A point opens its
geometry through a link" below). A flat library moves in one command:

```text
pyfs-workspace migrate-geometries .    # geometries/30_WB.fsm and its sidecars
                                       # become geometries/30_WB/
```

It moves every `geometries/<stem>.<ext>` with its `<stem>.boundaries.toml`
and `<stem>.provenance.toml` into `geometries/<stem>/`, prints each move
and each folder it left alone (a folder that already exists is not
touched, whatever it holds), and a second run moves nothing. A root with
no `inputs/geometries` is refused, exit 2, with nothing created. The run
records of the workspace keep reading: a record names its inputs by file
name and hashes their bytes, and neither moved. The suite runs the line
above over a library holding a saved simulation with both sidecars, a
raw mesh with none and a folder already made, then runs it again
(`test_workspace.py::test_migrate_geometries_moves_a_flat_library_into_folders_once`),
and runs a matrix row against the folder layout on the campaign path
(`test_matrix_run.py::test_a_row_naming_a_folded_geometry_runs_on_that_folder_alone`).
The flat layout is not deprecated: nothing migrates by itself, and the
cycle that retires it is for the owning seat to open once the folders have run a
campaign.

### What a solver preset may say, and what happens to a key that reaches nothing

A preset is a table of solver settings, written in the SOLVER's own key
names as often as in this package's. Both are read: `NITER`,
`boundary_layer_type`, `max_parallel_threads`, `set_solver_model`,
`proximity_avoidance`, `solver_minimum_cp`, `induced_wake_velocity`,
`unsteady_pressure_kutta`, `additional_wake_relaxation_iteration`,
`reynolds_averaged_drag_forces` and `unsteady_N_revolutions_wake` are
aliases of the fields the emitter names. A preset transcribed from a
working session keeps working as written.

Three things can happen to a key, and the third is the one worth
knowing.

1. **It names a setting this package emits**, directly or by alias, and
   it reaches the script.
2. **It is declared recorded-only.** It stays in the artifact, emits
   nothing, and a warning names it AND the reason. The eight this
   package declares today are `solver`, `motion`, `symmetry_type`,
   `unsteady_delta_theta_deg`, `unsteady_N_revolutions`,
   `set_base_region_trailing_edges`, `slipstream_wake_stabilization` and
   `wake_layers`. `symmetry_type` belongs to the geometry a row opens
   and is stated in the row's `SYMMETRY`; `solver` and `motion` are what
   the `WORKFLOW` column decides; `unsteady_delta_theta_deg` and
   `unsteady_N_revolutions` are superseded by the row's `DELTA_THETA`
   and `REVOLUTIONS`; `set_base_region_trailing_edges` is a
   separation model that selects boundaries, and a preset carries no
   selection, so it is a recipe's job; and the last two have no
   emitter in this package at all. Two keys LEFT this list at v0.11.0:
   `symmetry_loads`, on the design decision of 2026-09-02 with the
   measurement in hand (a stated key reaches
   `SET_ANALYSIS_SYMMETRY_LOADS`; an absent one still emits nothing), and
   `significant_digits`, which gained its emitter; `mesh_order_list` is
   refused outright, since the boundary order belongs to the file
   (`pyfs-matrix inventory`).

    That list is maintained by hand and this page is not generated, so
    **read the warning your own preset prints** rather than this
    paragraph: it names every key of YOUR file that was recorded, each
    with its reason. What the paragraph is for is that the set is
    closed and short enough to see at once.

    A preset may declare its own with `recorded_only = ["my_setting"]`,
    for a setting from a build or a workflow this package has not met. A
    declared key still warns, because the point is that its author knows
    it is not reaching the solver.
3. **Anything else is REFUSED**, naming the key and listing what
   applies, so `max_threds` finds `max_threads`.

Case 3 used to be a warning and a silent drop, and that is the defect
this replaced. A preset asking for `SUBSONIC_PRANDTL_GLAUERT` ran
`INCOMPRESSIBLE`; one asking for a turbulent boundary layer ran the
solver's default. Those runs converge, export and publish numbers
against a physics nobody selected. A refusal costs an edit; a silent
drop costs a result.

One key of a preset selects boundaries rather than setting a number:
`vorticity_drag_boundaries` (also spelled `set_vorticity_drag_boundaries`
or `vorticity_drag_families`), the families whose induced drag comes from
vorticity integration, `SET_VORTICITY_DRAG_BOUNDARIES`. Stating it as an
EMPTY list is refused when the file is read, at `pyfs-matrix plan`
(PFS-2005.02):

```toml
iterations = 800
vorticity_drag_boundaries = []
```

is refused naming `inputs/setups/s002.toml`, the key, the command, and
the reason: the solver's default, surface pressure integration on every
boundary, is expressed by never emitting the command (SRC-003 p.202), so
an empty list asks for a selection and names none, and the run would
converge and publish induced drag against a setup nobody selected. Drop
the key for the default, or name the families. Which entity-selecting
keys admit an empty list is the domain seat's call, written beside each
key in `pyflightstream.workspace.inputs.ENTITY_SELECTIONS`, and the
refusal prints the verdict; the post-processing artifact's keys are
listed under that artifact below.

A preset defined **custom coordinate systems** at 0.14.0
(PFS-2034.01), in a `[[frames]]` table, one entry per frame:

    [[frames]]
    name = "NAC"                # the name the solver shows and a row's rotation cites
    origin = [0.42, 0.0, 0.11]  # in the geometry's own frame, simulation length units
    x_axis = [1.0, 0.0, 0.0]    # optional; the reference axes when left unstated
    y_axis = [0.0, 1.0, 0.0]

Every row citing the preset has them created right after the frames the
package makes itself (`MRP` at the moment point on every run type,
`<ALIAS>_SMRP` at each rotor's hub on the rotor run types), in the order
written and before any motion, so a rotor whose
axis frame is one of these turns about a frame that exists. The table is
not a solver setting and never reaches the refusal above. A name the
package creates itself (`MRP`), a name defined twice, or an
origin that is not three numbers is refused at plan time naming the
preset. What the frames are FOR is the row's rotation of a boundary
family about one of their axes, which 0.14.0 adds beside them.

!!! warning "Since 0.15.0 the table's home is the REFERENCE artifact"

    A coordinate system is a place on the aircraft, so it belongs beside
    the lengths and the rotors rather than in a preset, which is per
    condition where a reference is per configuration (FR-72). **Write the
    same table, unchanged, in `inputs/references/<id>.toml`.** A preset
    that still states it is REFUSED, naming the reference to move it into.
    A boundary name and a coordinate system are properties of the
    CONFIGURATION and a preset is per condition, so a file stating both is
    a file with two answers.

A preset may declare **custom flags**, since 0.15.0 (FR-74), in a
`[[flags]]` table. A flag names a FlightStream command and the word a matrix
row writes for it, and after that the ROW states the value:

    [[flags]]
    name = "digits"                  # the word a row writes in VAR_NAMES_VALUES
    command = "SET_SIGNIFICANT_DIGITS"   # the command it becomes, bare

A row citing that preset then writes `digits: 6` in its `VAR_NAMES_VALUES`
cell and the script carries `SET_SIGNIFICANT_DIGITS 6`. The word is read case
folded, as every other key of a row is, and a row that states nothing for a
declared flag emits nothing for it.

**THIS IS WHAT LEAVES `RAW` TO THE PARTICULAR CASE ITS NAME PROMISES.** A raw
entry is a whole command line with its arguments, fixed in the preset, so
every row citing that preset emits the same one. A flag names the command and
the row supplies the value, so ONE PRESET SERVES A SWEEP over it: three rows
at three values are three rows, not three presets. Reach for a flag when a
setting varies with the point, and for `[[raw]]` when a line is the same for
every row of the study.

**A flag passes the same emit check every curated emission passes**, which is
what makes it a declaration rather than a text substitution. The line goes out
through the emitter, so the command's existence on the row's build, its
grammar and its argument types are all judged at `pyfs-matrix plan`: a flag
naming a command this build cannot emit, or a row giving it a value of the
wrong type, is refused before a seat is spent, with the flag, the preset that
declared it and the row's value all named.

A flag reaches the three seams a raw entry reaches, before the `control`,
`geometry` and `setup` phases. Leave `before` out and the flag takes the phase
its command's own database entry declares, which is the answer for every
command that has one; state it only to place a `control` command, whose phase
the database leaves open. A flag whose command belongs to a LATER phase is
refused naming that phase rather than quietly not appearing: a later command
is part of the run rather than of its setting up, this package emits those
itself, and a row that needs one states it in `[[raw]]`.

Three declarations are refused as written. A `command` that carries its own
arguments, because the value would then be stated twice and the two could
disagree, and a line with its arguments already in it is a `[[raw]]` entry.
Two records giving one word two commands, because a row stating the word would
mean whichever record was read last. And a `before` that names no phase.

A declared flag's word is a key the row MAY state: the preset registered it by
declaring it, so the guard that refuses a key no run type reads leaves it
alone. A word no flag declares is still refused, and so is a word a run type
ALREADY reads, because a row stating it would drive the curated handling AND
emit the flag's command: one cell with two readers, and nothing anywhere
saying so.

**WHY THIS TABLE DID NOT MOVE TO THE REFERENCE**, which is the question a
reader has after being told twice that a table's home changed. `[aliases]` and
`[[frames]]` moved because a boundary name and a coordinate system are
properties of the CONFIGURATION, and a preset is per condition. A flag names a
SOLVER COMMAND, and how hard to solve is what a preset answers, so the table
lives beside the settings rather than in the reference. It is not itself one
of them: the reader takes `[[flags]]` OUT of the settings it hands on, because
a declaration is not a value to send, and
`test_the_reader_takes_the_table_out_of_the_solver_settings` pins that.

The reader's own constant for it is `FLAGS_TABLE`, beside
`RAW_TABLE`, in `pyflightstream.workspace.inputs`; the model a declaration
becomes is `pyflightstream.cases.CustomFlag`, and the recorded rotor block of
a reference is `RotorReference` in the same module as the reader.

A `LEGACY` row takes no flags table, for the reason it takes no raw table:
its own recipe is the reader of its keys and reads neither.

**A worked one you can take.** `tests/tier3_licensed/inputs/setups/s006.toml`
declares

    [[flags]]
    name = "base_bending"
    command = "SET_BASE_REGION_BENDING_ANGLE"

and row 8006 of `tests/tier3_licensed/matriz_vocab.fs` writes
`base_bending: 12.5` in its cell. The rendered script,
`tests/tier3_licensed/goldens/matriz_vocab/POLAR-8006_M10AL+000BE+000.txt`,
carries `SET_BASE_REGION_BENDING_ANGLE 12.5`, and it is compared against that
golden on every commit, so the example cannot rot into a description of
something the package no longer does.

A preset may also state **raw solver commands**, since 0.14.0
(PFS-2033.01, the design of 2026-09-09), in a `[[raw]]` table, one entry
per line, each naming the phase it goes before:

    [[raw]]
    command = "SOLVER_SET_AOA 1.0"   # the line as the solver reads it, arguments included
    before = "init"                  # geometry, setup, init, exec, analysis, export, or control

The line is emitted by every run type at the seam before the first
command of that phase (`control` puts it at the head of the script, since
a control command may appear anywhere), in the order written, and it
passes exactly the checks every curated emission passes: the command's
existence on the row's build, its grammar and its argument types, and
the script's phase order. A command the build has no evidence for is the
emitter's own refusal, naming the preset and the line, at `pyfs-matrix
plan`; so is an argument of the wrong type, a command whose grammar is a
block rather than a line (the table carries one-line commands only), and
a command of a later phase than the one it is declared before, which
would put the script past that phase. The run record carries the lines
the script took as `raw_commands` (`command`, `before`, `setup`,
`source`), and the provenance document carries them on the solver run
(PFS-2033.02). A preset stating none changes nothing.

**SINCE 0.15.0 A ROW MAY STATE ITS OWN** (FR-67), which is what the
`RAW` key of `VAR_NAMES_VALUES` is, and it extends this table rather than
replacing it. A record writes the line itself or names a text file of
`inputs/`:

    ... / RAW: {COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init},
               {FILE: raw/extra.txt / BEFORE: init}

written on ONE line in the real cell. **The pairs of a raw record split on
a spaced slash**, ` / `, and not on the bare one `MOTIONS` and `ROTATE`
use, because a path and a command line carry slashes of their own; a
record written with tight slashes is read as one pair and refused for the
key it appears to be missing.

A raw FILE is read line by line, in order, with a blank line and a line
opening with `#` skipped so the file may explain itself. Every line passes
the same emitter checks a preset's line passes, and a file carrying a
command this build lacks is refused naming THE FILE AND THE LINE rather
than the cell, because the cell holds a path and the mistake may be thirty
lines away. A path that resolves outside `inputs/` is refused: a raw file
must be one a second machine has.

**AT ONE SEAM THE PRESET'S LINES COME FIRST AND THE ROW'S AFTER**, the
shared ground and then the specific over it. Within the row the records
are in cell order, so a file's lines land where its record sits. Each
line's `source` on the run record says where it came from: the setup's id,
the word `matrix` for a line written in the row's own cell, or
`<path>:<line number>` for a line read out of a file.

A script that WRITES a matrix should not repeat these literals, for the
reason `SWEEP_WORD` exists: a generator building rows in Python spells the
key by importing the name, so a row it writes is a row this reader
accepts, and the two cannot drift apart. A person typing a cell into a
text editor imports nothing and needs none of this.

<!-- skip: next -->
```python
from pyflightstream.cases.workflows import (
    RAW_BEFORE_KEY,
    RAW_COMMAND_KEY,
    RAW_FILE_KEY,
    RAW_VARIABLE,
)

# The cell tail a generator is about to write out.
record = {RAW_COMMAND_KEY: "SOLVER_SET_ITERATIONS 350", RAW_BEFORE_KEY: "init"}
cell = f"{RAW_VARIABLE}: {{" + " / ".join(f"{k}: {v}" for k, v in record.items()) + "}"
# -> 'RAW: {COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}'

# And the same for a file, which is the other of the two forms.
by_file = {RAW_FILE_KEY: "raw/extra.txt", RAW_BEFORE_KEY: "init"}
# -> 'RAW: {FILE: raw/extra.txt / BEFORE: init}'
```

Note the `" / "` in the join: the spaced separator is the raw record's
grammar, not a style choice, so a generator that writes `"/"` produces a
row this reader refuses.

A preset named **groups of mesh families** at 0.14.0 (the reference
decision of 2026-09-09), in an `[aliases]` table, one key per alias:

    [aliases]
    lifters = ["LiftBlade", "Hub1"]       # families and boundary names, in any mix
    pusher = ["PushBlade", "Spinner"]
    airframe = ["W", "B", "S", "N", "H"]  # the word means what this preset says

An alias is read wherever a boundary is cited by a row of the preset:
`MOVING_BOUNDARIES: lifters`, `ROTATE: {... / FAMILIES: pusher}`,
`BASE_REGIONS`, a `[groups]` member and a `families` entry of the pproc
artifact. Each member resolves as a name does, an exact boundary name
of the file first and a family (the label without its trailing number)
second, and a member the file does not carry is ignored, so one preset
serves the wing-body and the isolated rotor of a study. The alias is
tried before the family and, in a `families` entry, before the selector
words, so `airframe` and `blades` mean whatever the file says where it
defines them. Where it does not, both are RETIRED at 0.15.0 and REFUSED,
not warned about: this package has no stable release, so an old word owes
no compatibility window, and the refusal names what to write instead.
Declare the alias yourself, in the reference. The refusal arrives when the
ROW is built, at `plan`, and not when the artifact loads, because whether
`airframe` is an alias or the retired selector is a question about the
reference the row cites.
A cell naming an alias none of whose members the file carries is
refused as a name the inventory lacks, naming the alias. The run record
carries the preset's aliases, so the products stage resolves a group
by them without opening the preset, and the provenance document carries
them on the solver run. The alias name is matched as written and then case
folded, as a family name is, so `LIFTERS` finds `lifters`; an alias listing
no member is refused when the preset is read, because an alias stands for
the names after it.

### When a name you used no longer exists

A word this package retired refuses on sight, and the refusal names the
replacement, so the fix is in the message rather than in the changelog. Where
the old spelling was a value inside a FILE, the refusal arrives as
`InputArtifactError`, naming the artifact and the word. Where it was a METHOD
you reached for in Python, it arrives as
`pyflightstream.exceptions.RetiredAttributeError`, and both descend from
`PyflightstreamError`, so one `except` around a whole workspace load catches
either:

<!-- skip: next -->
```python
from pyflightstream.exceptions import PyflightstreamError
from pyflightstream.workspace import CampaignWorkspace

workspace = CampaignWorkspace("a-study")
try:
    workspace.engine_point("HUB")
except PyflightstreamError as refusal:
    print(refusal)
# engine_point of the CampaignWorkspace API is no longer accepted since
# v0.15.0. Write rotor_point. ...
```

Every python block on this page is marked skip, because the rest of them
need a solver. The claim this one makes is executed elsewhere: the
`RetiredAttributeError` docstring carries a doctest that asserts both
parents, and `tests/tier1_offline/test_retired_attribute_error.py` catches
the refusal through `PyflightstreamError` and compares the message against
the registry's own.

`RetiredAttributeError` also descends from `AttributeError`, which is what a
caller who typed the old method name was already catching, so nothing that
worked before the class arrived stopped working.

**It is named for an ATTRIBUTE and not for the registry**, which retires nine
spellings of which this covers the ones you reach for in code. The rest are
file values and refuse through the artifact reader, which is where a file's
mistakes belong.

!!! warning "Since 0.15.0 the table's home is the REFERENCE artifact"

    A boundary name is not a solver setting, and the words a study uses
    for its own geometry belong with the configuration (FR-59). **Write
    the same table in `inputs/references/<id>.toml`.** A preset still
    stating it is REFUSED when a row binds it, naming the reference to
    move the table into. The refusal arrives at `plan`, not when the
    preset loads, because it names the reference the ROW cites.

    The reference's table can do one thing the preset's could not: **a
    member may be another alias**, resolved to the end, so `lifters` may
    name `lifters_left` and `lifters_right` and each of those may name
    the rotors. And every rotor the reference declares is an alias over
    everything it owns, without being written in this table at all.

    Following a member to the end is what makes a RING possible, so one is
    refused rather than followed forever:
    `pyflightstream.exceptions.AliasCycleError` names the alias that
    closed the ring and the member that closed it, and prints the whole
    path, because a reader holding one of the two names would otherwise
    have to open the file to find the other. Written out, `lifters` naming
    `lifters_left` and `lifters_left` naming `lifters` back is refused
    with:

    ```text
    the alias 'lifters_left' resolves through 'lifters', which resolves
    back to 'lifters': 'lifters' -> 'lifters_left' -> 'lifters'. An alias
    may name another alias, and the reader follows to the end, so a ring
    has no end; break it in the reference
    ```

    A member that names its OWN alias is NOT a ring, and it is not
    refused: it falls back to the family reading, exactly as it did before
    aliases could nest. `wing = ["wing"]` over a mesh carrying `wing1` and
    `wing2` gives you both, and over a mesh whose wing was renamed it
    gives you nothing, which is the case that would have been reported as
    a false ring.

A preset may also carry a `[flight_condition]` table, which is not a
solver setting and is not judged as one: it holds the fluid pins
(`RHOkgm3`, `MUPas`, `ASMPS`, `TK`, `PPA`) that every row naming this
setup inherits for the keys it does not state itself. See
[Flight conditions](flight-conditions.md) for what may and may not go in
it, and why a velocity may not.

`stabilization` and `stabilization_strength` resolve as a PAIR into one
number. Disabled means ABSENT and not a strength of zero, which would
still be switched on.

`inputs/executables.toml` is the one file that is about your machine
rather than about your study: it maps a build identifier such as
`26.120` onto the executable on this computer. It is why the matrix can
name a build and stay portable.

A workspace kept in version control keeps that file portable too, by
carrying placeholder paths in it and the real ones in
`inputs/executables.local.toml` beside it, which is gitignored
(PFS-2031.15). The package reads the overlay over the registry when it
exists: a bare local path keeps the version the committed entry declares,
a local table replaces the entry, and a build identifier the overlay is
silent on reads as committed. The tier-3 workspace of this repository
runs that way, every row on the build its `FS_BUILD` cell names and no
`--fs-exe` on the command line.

An entry takes one of two shapes and the difference is what a row's
script is emitted under:

```toml
"26.120" = "C:/builds/26120/FlightStream.exe"
"26.123" = { path = "C:/builds/26123/FlightStream.exe", version = "26.123" }
```

The bare path declares no version, so rows naming that build are emitted
under the campaign's default. The table declares one, and rows naming
that build are emitted under it. That is what lets ONE matrix send some
rows to one build and some to another: since v0.8.0 a matrix whose active
rows name two builds runs, and each row's record names the executable its
own row asked for. The declared version is checked against the version
registry when the file is READ, so a typo is refused pointing at the file
that is wrong rather than at the first emission that fails.

Note the one asymmetry, because it is easy to expect the other
behaviour: a registry entry never overrules the default version for a row
that names NO build. A silent row falls back to the campaign default, as
it always has.

### What a reference artifact holds beyond the three lengths

The two files above carry only the lengths the sweep table needed. A
reference artifact also carries a FOURTH length for a propelled
configuration, the moment point, and a `[rotor]` block. This is
`inputs/references/r003.toml` in full, the same artifact the listing
above summarises by its first three lengths:

```toml
area_m2 = 10.0
chord_m = 1.2
span_m = 8.0
rotor_diameter_m = 2.0

[moment_point]
x_m = 0.3
y_m = 0.0
z_m = 0.0

[rotor]
radius_m = 1.0
n_blades = 3
pitch_deg = 0.0
toe_deg = 0.0

[rotor.position]
x_m = 0.0
y_m = 0.0
z_m = 0.0
```

`rotor_diameter_m` SITS WITH THE OTHER LENGTHS AND NOT IN THE
`[rotor]` BLOCK, which is the natural-looking home and the wrong one.
The recorded rotor block is recorded metadata of which this package reads
ONE field, the position, since 0.11.0 (the unsteady run types create the
rotor hub frame there); the diameter is a DIVISOR of published numbers,
exactly like the area and the chord. It is what an advance ratio is a ratio against, so a
row stating `ADVANCE_RATIO` and a reference without this field is
refused naming the field to add, and it is what the rotor
coefficients normalise on. It is optional, because a configuration with
no rotor has no diameter and a placeholder would be worse than
nothing.

`[rotor.position]` is the hub position in the simulation geometry
frame, in m, and it defaults to the origin if you leave the table out,
which is a default and not a measurement.

THE SENSE OF ROTATION AND THE SIGNS OF THE ROTOR SPEED ARE NOT HERE since
v0.11.0 (PFS-2029.08). Until 0.10.1 the block carried `rotation`,
`blade_travel`, `rpm_sign_installed` and `rpm_sign_isolated`; no emitter
read them, and the two signs named a configuration, installed against
isolated, which is a property of the mesh a ROW opens and not of
reference data several rows share. A row states the sign now, in
`RPM_SIGN` beside `ADVANCE_RATIO` or inside the `RPM` value, and an
artifact still carrying any of the four is refused naming the row keys;
`pyfs-matrix upgrade --inputs` strips them. The measured argument behind
the signs, and the derivation from a published sense to a sign, are on
[the mesh inputs page](mesh-inputs.md).

### The reference declares the study's vocabulary

Since 0.15.0 this artifact is where a study says what its boundaries are
CALLED, and it is the first thing to write when you set a workspace up: the
rows that come later cite these names and nothing else. Three tables carry
it, and the paragraphs above them are written for a configuration with ONE
rotor (FR-59, FR-60, FR-72).

    [aliases]                  a name for a set of boundaries; a member
                               may be another alias, resolved to the end
    [[frames]]                 the custom coordinate systems, moved here
                               from the setup preset
    [<ROTOR>] kind = "rotor"  one block per rotor, and the block's NAME
                               is an alias over everything it owns

ONE WORD, AND IT IS ROTOR. The block, the key, the frame, the point and
the probe scale all say it, because a propeller is a rotor and so is a
lift fan: the general word is the one that never has to be changed again
when the aircraft does. Every spelling this replaced is refused naming
what to write instead, so a file written before 0.15.0 stops rather than
running under a word that means something else now.

A rotor block states `alias` (optional, and equal to its name), the hub
as `x_m`, `y_m`, `z_m`, then `axis`, `rpm_sign`, `diameter_m`,
`families_general`, `families_blades` and `blade1`. **The blade count
is the length of `families_blades`** and nothing else, so a row states
no count and a sector mesh carrying one blade of four still reduces
over four.

**`diameter_m` is per rotor, and it is what an advance ratio resolves
against for a motion citing that block.** The top-level
`rotor_diameter_m` above still answers for a row that names no
alias; it is one number for a whole configuration, so it cannot answer
for a second rotor of another size, which is why the length moved into
the block.

`RPM_SIGN` on a row likewise answers only where no alias is cited: a
record naming a rotor takes the sign from its block, and a record
stating both is refused naming both.

Nothing in the package reads the recorded rotor block except its `position`,
since 0.11.0: the two unsteady run types turn it into a coordinate system
named `<ALIAS>_SMRP` for the rotor it belongs to, the frame the reference probe lines and rotor plots are
defined in, and the frame a rotor row turns about unless it states
`ROTOR_ORIGIN`. The rest of the block, `radius_m` (optional since
0.11.0, and checked against the diameter when stated) and `n_blades`,
stays recorded and changes no emitted script. The four rotor facts the
block carried until 0.10.1, `rotation`, `blade_travel`, `rpm_sign_installed`
and `rpm_sign_isolated`, are refused since 0.11.0 (PFS-2029.08): the row
states the rotor speed's sign and axis, `pyfs-matrix upgrade --inputs`
strips them, and the argument behind them is on
[the mesh inputs page](mesh-inputs.md).

AND THE ARTIFACT DOES NOT REACH A RECIPE, which is worth knowing before
you write one. `resolve_matrix` narrows this artifact to the reference
area and length the case needs, and a recipe is called with the case and
the script, so `case.reference.rotor` does not exist. The full
artifact survives in the resolved matrix, keyed by the REF code of the
row, so a recipe that wants a sign reads it from the workspace or the
resolved matrix it closes over:

<!-- skip: next -->
```python
from pyflightstream.workspace.matrix import resolve_matrix

resolved = resolve_matrix(
    "matrix_registry.fs",
    workspace,
    name="matrix",
    fs_version="26.120",
    recipes={"003": "steady"},
)


def recipe(case, script):
    # The ROW's code, not a literal: a case carries the codes of the row
    # it came from, so this reads the artifact that row named.
    reference = resolved.references[case.variables["matrix_ref"]]
    rotor = reference.rotor
    if rotor is None:
        raise ValueError(
            f"{case.sim_id}: this recipe places a probe line per blade and the "
            "reference artifact describes no rotor"
        )
    blades = rotor.n_blades   # the RESOLVED count, one under a periodic sector
```

The guard on the way to `blades` is the point rather than ceremony:
`rotor` is `None` for any reference artifact that describes no
rotor, and a recipe that assumes one writes a script the solver
cannot run. The rotor speed and its sign are the ROW's (`RPM`,
`ADVANCE_RATIO`, `RPM_SIGN`), read through `rotor_speed(case)` rather
than from the artifact, so a recipe that emits a rotor motion reads the
row exactly as the built-in `unsteady_rotor` workflow does.

### What the post-processing artifact holds

`PPROC` names `inputs/pproc/p<id>.toml`, the post-processing artifact. Until
v0.11.0 this was the groups artifact, `inputs/groups/e<id>.toml`, a flat
table of group name to members that nothing on the run path read; the
owning seat decided on 2026-09-02 that it is the home of post-processing and it
was renamed (PFS-2029.07). It carries six tables, every one optional, and a
file holding `[groups]` alone is what the old file was:

```toml
base_regions = ["W", "B"]      # families the base-region autodetect may consider; [] = off

[groups]                       # what the groups file held: number -> families
"1" = ["Blade1", "S", "N", "P", "W", "B", "H"]
"2" = ["W", "B"]
"3" = []                       # every family the geometry carries
"4" = ["Blade", "airframe"]    # a family is every member of it; airframe is the reference's alias

[exports]                      # which of the eight export kinds a point writes
tecplot = false                # a kind not named is written; loads cannot be off

[sections]                     # NEW_SURFACE_SECTION_DISTRIBUTION per entry and plane
count = 50
plot_direction = 1
include_symmetry = false
[[sections.distributions]]
families = ["W"]
frame = "MRP"
planes = ["XZ"]
[[sections.distributions]]
families = "LIFT"              # the rotor; LOCAL_AXIS makes it one per blade
frame = "LOCAL_AXIS"           # since 0.15.0 the FRAME says how the entry expands
planes = ["XY"]

[plots]                        # UNSTEADY_SOLVER_NEW_FORCE_PLOT per group and parameter
parameters = ["CL", "CDI", "CDO", "CD", "FX", "FY", "FZ", "MX", "MY", "MZ"]
[[plots.groups]]
name = "MRP_TOTAL"             # the plot is named {parameter}_{group}: CL_MRP_TOTAL
frame = "MRP"
families = "all"
[[plots.groups]]
name = "MRP_{family}"          # one group per family the geometry carries
frame = "MRP"
families = "each"

[[probes]]                     # UNSTEADY_SOLVER_NEW_FLUID_PLOT per vertex and parameter
frame = "LIFT_SMRP"            # a rotor frame: one probe set per rotor it reaches
parameters = ["MACH", "VELOCITY", "VX", "VY", "VZ", "STATIC_PRESSURE_RATIO"]
points = 25
scale = "rotor_radius"         # or "m"; the radius is THAT rotor's, not the configuration's
[[probes.lines]]
start = [-2.0, -1.0, 0.0]
end = [-2.0, 1.0, 0.0]

[products]                     # the post-processed CSV tables the campaign writes
polars = true                  # one polar table per group, per point
sections = true                # one table per point from its sectional loads export
plots = true                   # one table per unsteady point from its plots export
custom_polar_format = false    # beside each polar table, the text file the reference tooling opens
```

Three things carry the artifact across configurations. A `families` entry
is a list of family names, a bare word (an alias the row's reference
declares, read first, above; else a family name), or one of TWO SELECTORS:
`all` (every boundary, the command's own `-1` form) and `each` (one entry
per family the geometry carries, the name carrying `{family}`). A family
the geometry does not carry is left out, which is how one artifact serves
a wing-body and an isolated rotor, and an entry that resolves to nothing
is skipped; pass `--ignore-missing-families false` to `pyfs-matrix plan`
or `run` to hear about both instead of having them pass in silence. The word
is read: `true`, `yes` and `1` mean yes, `false`, `no` and `0` mean no, and
anything else is refused naming the flag and the word rather than quietly
meaning yes.

The choice reaches each case as the row variable
`IGNORE_MISSING_FAMILIES`, which is what a refusal quotes back at you and
what `pyflightstream.cases.workflows.IGNORE_MISSING_FAMILIES_VARIABLE`
spells for a Python caller:

<!-- skip: next -->
```python
from pyflightstream.cases.workflows import IGNORE_MISSING_FAMILIES_VARIABLE

case = case.model_copy(
    update={"variables": {**case.variables, IGNORE_MISSING_FAMILIES_VARIABLE: "false"}}
)
```

**A MATRIX CELL MAY NOT WRITE IT.** The reader refuses a row that states the
key and points you at the flag, because whether a family the mesh lacks is a
skip or a refusal is a property of the RUN and not of the row: the same row
is planned across a wing and a rotor, which is the whole reason the skip
exists. At the default nothing at all is written onto a case, so every
recorded run keeps its identity and every emitted script its bytes.

There were five selectors until 0.15.0 and three of them retired in one
release, leaving `all` and `each`.
`each_blade` went because the FRAME says how an entry expands now, so
`frame = "LOCAL_AXIS"` is what one distribution per blade is written as.
`airframe` and `blades` went because they are the two that decide what a
BLADE IS, from `blade_pattern`, a regular expression over the family name,
`^Blade\d+$` unless the file says otherwise: a mesh whose blades are
spelled another way gets an airframe with blades in it and nothing says
so. Declare the set in the reference's `[aliases]` table and cite it by
name, and a study that named its own surfaces cannot be guessed wrong.
All three are REFUSED, not warned about, and the refusal names what to
write instead; an alias of the same name is read FIRST, so a reference
that already declares `airframe` is untouched and keeps its own meaning.
The refusal arrives when the ROW is built, at `plan`, because whether
`airframe` is an alias or the retired selector is a question about the
reference the row cites. A `frame` is
cited by NAME: `MRP`, the moment frame the reference artifact creates;
`SMRP` and `RMRP`, a rotor's hub frame and its turning frame, and
`LOCAL_AXIS`, one frame per blade (0.15.0, and see the next paragraph for
what those three do to the entry); `<ALIAS>_SMRP`, `<ALIAS>_RMRP` and
`<ALIAS>_RMRP<k>`, the same frames named for ONE rotor, which is how an
entry says which rotor it is about on a row that turns nine; a frame the
row's REFERENCE declares in its `[[frames]]` table, by the name written
there (`LIFTERS_MRP`, `PUSHER_TIP`); and `BLADE_AXIS` on the flat rotor
row. The names of before 0.15.0, `PROP_MRP`, `PROP_MRP<k>` and
`RotorAxis<k>`, do NOT resolve: they went with the package-level rotor
frame, and an entry citing one is refused naming the shape to write.

**THE FRAME DECIDES HOW THE ENTRY EXPANDS**, which is why there is no
`expand` key and why `each_blade` retired. An entry in `MRP` or a declared
frame is ONE over the families it names. One in `SMRP` or `RMRP` is one
per ROTOR those families reach, each in that rotor's own frame. One in
`LOCAL_AXIS` is one per BLADE, plus one for the rotor's `families_general`,
which have no local axis and ride the rotor's. Six lines of a `[plots]`
table are twenty-seven emissions on a nine-rotor aircraft. A name that
would collide carries `{family}`, and the reader refuses a name without it
where the entry emits more than once.

TWO WAYS AN ENTRY CAN FAIL TO LAND, and they are deliberately different.
An entry whose families reach no rotor the REFERENCE declares is REFUSED
at plan time, naming the rotors and the aliases it could have named,
because that is a writing error and cannot come right on another mesh. An
entry whose rotors the reference does declare, but whose frames THIS RUN
did not place, is LEFT OUT with a warning, exactly as an entry whose
families the geometry lacks is: a steady row places no rotor frames and a
lifters-only row places none of the pusher's, and one artifact serves all
three rows.

!!! warning "Since 0.15.0 a rotor's frames are named from its alias"

    A motion record that names a rotor block of the reference
    instantiates `<ALIAS>_SMRP` at the hub, `<ALIAS>_RMRP` turning with
    the motion, and `<ALIAS>_RMRP<k>` per blade of that block's
    `families_blades`, turning with blade k (FR-62). Nine rotors
    instantiate nine sets rather than colliding on one radical, so a
    post-processing entry can say WHICH rotor it is about:
    `frame = "PUSHER_RMRP"`.

    A row that ROTATES that alias also gets `<ALIAS>_SMRP_ORIGINAL`, a
    copy of the hub frame as it stood before the first rotation, which
    nothing turns (FR-71). It is created once per alias, so a row that
    turns one alias twice keeps the state before the FIRST rotation.

    **AND YOU DO NOT HAVE TO CITE IT.** An entry naming a hub frame that
    this row rotated is written in BOTH: once in `<ALIAS>_SMRP`, where the
    rotation left it, and once in `<ALIAS>_SMRP_ORIGINAL`, where it
    started. The plot names differ by the same suffix, so the two tables
    sit beside each other. That is the rule of 2026-09-10: an
    entry says which ROTOR it is about, and the row's rotation decides how
    many readings of it there are, exactly as the frame decides how many
    emissions an entry stands for. A rotor this row did not turn has no
    original frame and nothing doubles. `<ALIAS>_RMRP` and
    `<ALIAS>_RMRP<k>` never double: they turn WITH the motion at every step
    of an unsteady run, so there is no single frame they turned from.

    `PROP_MRP<k>` and `RotorAxis<k>` are refused for an entry written
    against 0.14.0, and a record that names no alias still emits them, so
    a workspace may migrate its rows before its post-processing. The
    custom frames come from the REFERENCE now, not the preset, and a
    family of `families_general` gets no frame of its own: its local frame
    IS the rotor's, which is what makes the spinner ride the hub.

An entry that resolves to nothing is skipped, unless this run asked for the
refusal (see `--ignore-missing-families` above); an entry WRITTEN as nothing
is refused, at `pyfs-matrix plan`, naming the file, the key as the file
spells it, and what the empty list feeds (PFS-2005.02, "an empty boundary
list is refused wherever the solver would read it as disable everything"),
except where the
domain seat has given the empty list a meaning. A group is one such key
since 0.14.0, the design decision of 2026-09-09:

```toml
[groups]
"1" = []
```

is EVERY FAMILY the geometry carries: the polar table of group 1 sums
every surface row of the loads table, and `MOVING_BOUNDARIES: g1` moves
every boundary of the file. A member of a group is, tried in this order,
a boundary name of the file; an ALIAS of the row's REFERENCE (its
`[aliases]` table, above), so `["airframe"]` is whatever the
reference calls airframe and nothing is hardcoded; or a FAMILY, the label
without its trailing number, so `["Blade"]` sums `Blade1` to
`Blade6`, which is group 4 of the example above. A member the geometry does not carry is left out, and a
position passes through to the motion. Until 0.14.0 the empty group was
refused as the reference undecided call, and a family name in a group summed
nothing at products time. `families = []` in a
`[[plots.groups]]` or a `[[sections.distributions]]` entry is refused,
naming `UNSTEADY_SOLVER_NEW_FORCE_PLOT` or
`NEW_SURFACE_SECTION_DISTRIBUTION`: the entry exists to emit over the
families it names, and over none it would emit nothing while reading as
though it had. `base_regions` is the other selection whose empty list has
a documented meaning, the autodetect off, which is its default. The table
the readers consult is `pyflightstream.workspace.inputs.ENTITY_SELECTIONS`,
one row per key with the verdict and its reason.

`base_regions` is a TOP-LEVEL key, so it goes above the first table
header, as the example above places it: TOML puts a key written under
`[groups]` INTO that table, where it is a group named base_regions. Until
0.13.0 the reader refused the top-level form as a groups file of before
0.11.0, which is what a bare list at the top level otherwise is
(PFS-2005.04); `base_regions = []` there is the documented off switch and
plans READY, and `base_regions = ["Base"]` reaches the script as one
`DETECT_BASE_REGIONS_BY_SURFACE` per boundary of the family.

A group is keyed by its NUMBER, and a word there is refused at
`pyfs-matrix plan` (PFS-2032.03): the polar table written per group
carries the number in its name (`3207_M20_g01.csv` is group 1 of polar
3207 at Mach 0.20), so an artifact

```toml
[groups]
"wing" = ["Wing"]
```

is refused naming the row, `inputs/pproc/p006.toml`, the key `'wing'`
and the table name the number is for; write `"1" = ["Wing"]`. Until
0.13.0 that artifact planned READY and stopped the whole products stage
after the seat was spent, outside the skip mechanism. An artifact whose
groups are not for polar tables says so with `products.polars = false`
and keeps its names.

The `[exports]` table decides the row's export set (FR-51): a workflow row
declares no `OUTPUTS` of its own any more, every export is named for the
point with the study's suffixes (`.fsm`, `.txt`, `.dat`, `_cp.txt`,
`_sloads.txt`, `_probes.txt`, `_plots.txt`, `_log.txt`), and a workflow row
that still carries `OUTPUTS` is refused naming this table. A setup artifact
that names one of these tables is refused pointing here: a setup carries
solver settings only (PFS-2029.16). The run record names the pproc id each
point was run for.

### How a point is named

Every export hangs off the point's NAME, and the name is the reference
convention (PFS-2029.19): `POLAR-<sim>_M<mach*100>AL<alpha*10>BE<beta*10>`,
with `J<J*100>` appended when the row has an advance ratio, every field
fixed width so a folder of them sorts. Row 3207 at Mach 0.20 and alpha
-2 is `POLAR-3207_M20AL-020BE+000`; a rotor point at Mach 0.1441 and J 1.7
is `POLAR-9001_M14AL+000BE+000J+170`; and its exports are
`POLAR-9001_M14AL+000BE+000J+170.txt`, `..._cp.txt`, `..._log.txt` and
the rest. `pyfs-matrix plan` and `run` name points this way unless
`--point-name` gives another template; the placeholders are `{polar}`,
`{point}` (the historical `a+02.0_b+00.0` tag), `{alpha}`, `{beta}`,
`{mach}`, `{advance_ratio}`, `{sim}` and `{campaign}`, and inside an
output name `{name}` is the rendered stem. The run record carries the
template that named each point (`point_name_template`), so a name is
never mistaken for the identity beside it: identity is the `run_id`, which
no template touches. A campaign built in Python keeps the library default,
`{point}`, so nothing written before v0.11.0 is renamed under it.

### What the products are

The `[products]` table names three kinds of CSV table, every one a header
line and one row per record, so a spreadsheet or a dataframe opens it with
nothing else. A POLAR table per group of `[groups]`, under `polars/` and
named by the same convention as the point's script with the swept
variable's field written as the literal word `sweep`
(`polars/POLAR-0001_M15AL+000BE+000J+sweep_g01.csv`, FR-85 and FR-88): one
row per point of the polar with the
reference block (`SREF`, `CREF`, `BREF`, the moment point), the advance
ratio of the row in `J` (empty where the run recorded none) and twenty-four
coefficients, `ALPHA`, `BETA`, `MACH`, `RE` (Reynolds in millions), the body
axes (`CDB`, `CYB`, `CLB`, `CRB25`, `CMB25`, `CNB25`), the stability axes
(`CDS` to `CNS25`), the wind axes (`CDW` to `CNW25`), and `CD0` and `CDI`,
every value at five decimals. A SECTIONS table per point,
`sections/<point>_sections.csv`, the point's condition and the seven columns
of its sectional loads export, in the export's units; a run that defined no
distribution leaves an export declaring zero sections and gets no table. The
FLOW-FIELD SAMPLES of a point under `probes/`, whatever the run type was
(FR-87): `probes/<point>_plots.csv`, the unsteady plots export re-tabled
with its coefficient columns brought from the solver's reference
velocity to the free stream, and `probes/<point>_probes.csv`, the probe
table of a row of any kind. That table opens with the same six columns
whichever run type filled it (FR-91), `PROBE, X, Y, Z, FRAME, STEP`, and
then carries its own export's fluid quantities in their own names and
units: a steady row brings Mach, Cp, the velocity components and the
boundary-layer columns; an unsteady row brings the parameters its probe
entry asked for, one row per point and solver step. `STEP` carries `-` on a
steady row, which has one step.

The `X`, `Y`, `Z` and `FRAME` columns are why this table exists. An
unsteady plots export numbers its probe columns, one per parameter the
row's own probe entry declares, `MACH7, VELOCITY7,
STATIC_PRESSURE_RATIO7` on a row asking for three, and it never says
where point 7 is, so its samples could not be placed at all. A steady
export does state its coordinates, and the frame it names is the
ANALYSIS frame rather than the one the probe entry laid its points out
in, so it could not be placed either without knowing the artifact.

The package records the vertex, the coordinates and the entry's frame
while it emits each point, writes them to
`sims/<sim>/profiles/<sim>_probe_points.csv`, and joins them here. That
file is the package's own record: it replaces only a file carrying its own
header, so a points file of your own that happened to carry the same name is
named in a refusal rather than replaced. A run recorded before
0.16.0 named no such file, so its `FRAME` cells are empty and its steady
coordinates still come from the export; the table is written either way.
`STEP` carries `-` on a steady row, which has one step, and empty means a
value the package could not derive. A probe export this release cannot
read is a recorded skip naming the file and costs the simulation none of
its other products.

And the REDUCTIONS of the plots table, one file per applicable reduction
beside it (PFS-2015.04), over the window the row states; the next section
walks them. The arithmetic behind the polar table is the
reference and was checked column by column against the tables the owning seat
recorded: FlightStream's `CL`, `CDi + CDo` and `Cy` are the stability-axis
coefficients, the body axes follow by turning them through the angle of
attack, the wind axes by turning the stability axes through the sideslip,
and the rolling and yawing moments are `CMx` and `CMz` scaled from the chord
to the span, with the reference sign.

The run writes these after collection, under `post/<matrix stem>/`, the
folder named after the matrix file (`post/matriz/` for `matriz.fs`), and
`products.json` beside them names every file with the run ids it derives
from and the pproc artifact; a campaign resumed with new points rewrites
them, since they derive from the manifest. A simulation whose product is
refused by design, a polar under sideslip for one, is listed under
`skipped` in that file with the reason, and the others are written
(PFS-2031.16); the key is always there, empty when nothing was refused. A
windowed unsteady point also gets its per-step series under `series/`,
described with the export threshold below (the stamped files as a series). To rebuild them by hand, with no solver and no executable
configured:

```text
pyfs-matrix post matriz.fs --workspace .            # refuses a product that exists
pyfs-matrix post matriz.fs --workspace . --overwrite
pyfs-matrix post --workspace .                      # every matrix the manifest names
pyfs-matrix post --workspace . --strict             # exit 3 if any product was skipped
```

A skip is a success by default, since everything producible was produced;
`--strict` is for a wrapper that must tell a partial rebuild from a whole
one, and it changes the exit code alone, after every product is written.

#### Custom polar format

The existing tooling opens a fixed-width text polar file, not a
CSV, and `[products] custom_polar_format = true` on the pproc artifact
writes that file beside every polar table the stage writes,
`<polar>_M<code>_g<group>.dat`
beside the `.csv`, the same rows a second time (PFS-2014.01.01). Off by
default. The shape, read off a recorded file and pinned by the committed
fixture `tests/tier1_offline/fixtures/custom_polar_format_sample.dat` (every
value in it synthetic), is nine header lines and then one line per point:

```text
FlightStream - STEADY_polar_AL_sweep_MACH_REmi_pins_from_the_setup
100110
Tue Sep 08 23:41:07  2026
007 01
      MNOM      SREF      CREF      BREF      XMOM      YMOM      ZMOM
       0.1       8.0       1.0       8.0      0.25       0.0       0.0
013
024
     ALPHA      BETA      MACH        RE       CDB       CYB       CLB  ...
  -2.00000   0.00000   0.10000   2.30000   0.00398   0.00000  -0.16424  ...
```

The title carries the row's description; line 2 is the polar and the
two-digit Mach code of the file name (`1001` at Mach 0.10 is `100110`);
line 3 the write time; `007 01` the number of reference columns and the
group; then the reference names and values, the row and column counts,
the twenty-four column names of the polar table in its order, and every
number at `%10.5f`. The docstring of
`pyflightstream.post.write_custom_polar_format` is the specification, line
by line, and `read_custom_polar_format` reads the file back (before
0.14.0 the five names carried a different prefix; those names and the old
key were removed in 0.16.0); the tier-1 test
feeds the fixture's rows through the writer and requires the fixture's
bytes, and writes, reads and writes again what the stage produced,
requiring equal bytes (PFS-2014.01.02).

#### A run's provenance, in an interchange format

Beside the tables, the stage writes one provenance document per recorded
run, every status, as W3C PROV in its PROV-JSON serialization
(PFS-2012.08.01): `post/<matrix stem>/provenance/<run id>.prov.json`, the
run id's separators replaced by underscores (`camp/sim_3207/a-02.0` is
`provenance/camp_sim_3207_a-02.0.prov.json`), and `products.json` names
each under `provenance` keyed by run id. The run record already carried
every fact; the document is the shape another tool reads without reading
this page. Its entities are every staged input, the script and every
collected output, each with its sha256 under `pyfs:sha256` (an output's
computed from the file when it is still there, `pyfs:sha256_from` says
`file` or `record`); its one activity is the solver run, with
`prov:startTime` and `prov:endTime` as the executor read its clock,
the wall time, the status and the executor's argv; its agents are the
package at its version and commit and the solver build at its executable
identity. The activity `used` the inputs and the script, every output
`wasGeneratedBy` it, and it `wasAssociatedWith` both agents:

```text
"activity": {
 "pyfs:run/camp/sim_3207/a-02.0": {
  "prov:type": "pyfs:SolverRun",
  "prov:startTime": "2026-09-08T21:41:07+00:00",
  "prov:endTime": "2026-09-08T21:41:19+00:00",
  "pyfs:status": "CONVERGED", "pyfs:wall_time_s": 12.5,
  "pyfs:executor": "LocalExecutor",
  "pyfs:argv": ["C:/builds/26120/FlightStream.exe", "-hidden", "-script", "run.fs"]
 }
}
```

The document is written with the standard library alone and read back in
the suite by a reader of a few lines that checks every relation names a
node the document declares; a PROV tool reads it as any PROV-JSON.

### Archiving a completed simulation

Every point of a row runs in the same simulation folder and collects
into its OWN folder beneath it. A run refuses to collect onto a name
already in that point's folder, which is what a re-run of the same point
meets, or to start a point whose declared output is already sitting in
the simulation folder before the solver has written it, rather than
attribute somebody else's file to the new point. Both refusals say to
archive the simulation, and this is the command they mean:

```text
pyfs-workspace archive . 8001        # sims/sim_8001/ becomes archive/sim_8001.zip
```

It zips the simulation's staged inputs, scripts and raw outputs into
one file under `archive/`, then removes the folder, so the row can be
re-run into a clean one while its evidence stays and the manifest keeps
its records. The products already under `post/` are untouched, and a
later `pyfs-matrix post` reads the exports from the simulation folder,
which is now in the zip: rebuild the products first, archive after.
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

### The reductions of an unsteady point

An unsteady point's plots table is its raw time history, one row per solver
time step. The stage writes its reductions beside it, one file per
reduction, each named in `products.json` with the reduction and the window
it used (PFS-2015.04); raw is the plots table itself and is written once,
never a second time under another name. Which reductions apply is the run
type's, and the window is the one the row states:

| file | run type | window |
|---|---|---|
| `probes/<point>_time_average.csv` | `unsteady_rotor` and `unsteady` | the export window the row states (`WINDOW_DEGREES`, `WINDOW_STEPS` or `WINDOW_REVOLUTIONS`); without one, a rotor row's last revolution (from `DELTA_THETA` and `REVOLUTIONS`, or `RPM` and `DELTA_TIME`), and a rotorless row's whole run (`DELTA_TIME` and `TIME_ITERATIONS`) |
| `probes/<point>_phase_locked_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | the time-average window cut into blade passages OF THAT ROTOR, one of its revolutions over its own blade count, a trailing partial passage dropped; one row per passage |
| `probes/<point>_per_blade_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | the last revolution OF THAT ROTOR cut into one window per blade, contiguous and ending at the run's last step; one row per blade |
| `probes/<point>_phase_locked.csv` | `unsteady_rotor`, a row naming no rotor by alias | the time-average window cut into blade passages, one revolution over `BLADES` steps each, a trailing partial passage dropped; one row per passage |
| `probes/<point>_per_blade.csv` | `unsteady_rotor`, a row naming no rotor by alias | the last revolution of the run cut into one window per blade, contiguous and ending at the run's last step; one row per blade |

Every window is counted in solver steps, inclusive, 1-based, and row `k` of
the plots table is step `k`; the table's own time column is averaged like
any other column and is not read as the clock. The average is the one
implementation of blade-passage averaging the package holds
(`pyflightstream.post.blade_passage_average`), applied once per window, and
it is taken over the WRITTEN plots table, so a reduction can be recomputed
from the file beside it. The windows travel on the run record: `pyfs-matrix
run` resolves them off the row when it writes the record (`reductions` in
`runs.json`), and `pyfs-matrix post` reads the record alone. A reduction the
row cannot window is listed under `skipped` with the reason, keyed by the
file it would have been: a rotor row that names NO rotor by alias and
states no `BLADES` skips the two passage reductions; a plots table shorter
than the window skips every reduction over it; a record written before this
field existed skips the time average naming the record. Not applicable is
not skipped: a rotorless point lists no per-blade file anywhere.

**SINCE 0.15.0 A ROW THAT NAMES ITS ROTORS REDUCES PER ROTOR** (FR-68), and
it needs no `BLADES` of its own: each rotor's blade count is the one its
rotor block declares, and each rotor's blade passage is ITS OWN
revolution, `60 / (rev per minute * the solver step)`, divided by its
blades. A transition row turning four lifters at 2200 rev/min and a pusher
at 900 reduces the two over passages of different lengths in one run, which
one file per reduction cannot hold, so the files name the rotor and the
flat `<point>_per_blade.csv` is listed under `skipped` with a reason naming
the files written instead. The windows live on the run record under
`rotors` (`pyflightstream.cases.workflows.ROTORS_KEY`), alias to that
rotor's block, and each written file's manifest entry carries a `rotor`
field, so the rotor is readable without taking a file name apart. The two
reductions that are per rotor are named by
`pyflightstream.cases.workflows.PER_ROTOR_REDUCTIONS`; the time average is
not among them, because it is one window of the whole point whatever turns
in it. A rotor whose motion cannot be resolved is a SKIP under its own name
rather than an absence, so a rotor never simply vanishes from the products.

<!-- skip: next -->
```python
from pyflightstream.cases.workflows import PER_ROTOR_REDUCTIONS, ROTORS_KEY

# Reading a run record's reductions without hard-coding either name.
per_rotor = record.reductions.get(ROTORS_KEY, {})
for alias, block in per_rotor.items():
    for reduction in PER_ROTOR_REDUCTIONS:
        entry = block[reduction]
        # -> {'windows': [[448, 515], ...], 'period_steps': 68, ...}
        #    or {'skipped': '<the reason this rotor has none>'}
```

A worked example, the tier-1 fixture: a rotor row of eight steps, four
steps per revolution, two blades, an export window of six steps. The
reductions of `a-02.0_plots.csv` land as

```text
probes/a-02.0_plots.csv           raw, one row per step
probes/a-02.0_time_average.csv    one row, steps 3 to 8
probes/a-02.0_phase_locked.csv    three rows, steps 3 to 4, 5 to 6, 7 to 8
probes/a-02.0_per_blade.csv       two rows, steps 5 to 6 and 7 to 8
```

each reduction file carrying `REDUCTION,WINDOW,FIRST_STEP,LAST_STEP,STEPS`
and then the plots table's own columns, and `products.json` naming each:

```text
"probes/a-02.0_per_blade.csv": {
 "sim_id": "7001", "pproc": "p001", "runs": ["camp/sim_7001/a-02.0"],
 "reduction": "per_blade", "windows": [[5, 6], [7, 8]], "period_steps": 2,
 "window_from": "the last revolution, one window per blade"
}
```

### Several matrices in one workspace

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

What two matrices of one workspace may not share is a POL. A POL names the
simulation folder `sims/sim_<POL>` and the run ids of the manifest, so two
rows stating one POL would write into one folder and a resume of either
would find the other's points already recorded. `plan` and `run` read every
`*.fs` beside the matrix in the workspace root before anything binds, and a
shared POL is refused naming both files and both rows:

```text
matrix not planned: POL 1001 is stated by two matrices of this workspace,
matriz.fs (row 1) and matriz_setup.fs (row 3). A POL names the simulation
folder sims/sim_1001 and the run ids of the one manifest, runs.json, so each
matrix of a workspace states its own POLs; renumber the rows of one of the two.
```

The tier-3 workspace of this repository, `tests/tier3_licensed`, is the
worked example: seven matrices, one library, one manifest, and a thousands
digit per matrix in their POLs.

### One row, several rotors

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
  the point tags that end every `run_id` in `runs.json` are the ones the
  converted file plans under, and a `--resume` finds the records it has.
* **It stops on a row that varies BOTH angles**, naming every such row.
  That row is one run per sideslip and each new row needs a POL of its
  own, which is run identity and not a converter's to invent. Split them
  by hand, giving each the POL you want, then run the command.

### One row, one geometry, turned

An installed rotor's incidence is a parametric study: the same mesh, the
blade and spinner families turned a few degrees in pitch or in toe, one
run per angle. Since 0.14.0 a row states that turn in its cell
(PFS-2034.02, the design of 2026-09-09) and the geometry file stays what
it was:

```text
ROTATE: {ANGLE: 3 / AXIS: PUSHER_SMRP-Y / ALIAS: PUSHER}
```

`ROTATE` is a list of records with the `MOTIONS` grammar, braces around
each record, commas between them, `/` between the pairs inside. Each
record is ONE rotation and two records are two rotations in the order
written, so a pitch and then a toe is `{...}, {...}`. `ANGLE` is in
degrees; `AXIS` names a coordinate system and one of its axes, as
`PUSHER_SMRP-Y`, where the system is one the row's REFERENCE declares in
its `[[frames]]` table (above) or one the package creates itself (`MRP` on
every run type; and a rotor's own
`<ALIAS>_SMRP`, `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>`).

**`ALIAS` names what turns, and it is the same word a motion uses.** That
is the whole of the 0.15.0 change here: after it, every surface of this
package that names a group of boundaries names it by alias, and the
reference is the one place a study says what its groups are.

It names **exactly one** word the reference declares. Unlike
`MOVING_BC_ALIAS` it does not fall through to a bare label or a family:
a rotation carries the frames of the thing it turns, and those belong to
one rotor, so `ALIAS: PUSHER,LIFT_L1` is refused telling you to write one
record per alias, `{...}, {...}`. A word the reference does not declare
at all is refused naming it and listing the ones it does.

**EVERY FRAME THE ALIAS OWNS TURNS WITH IT**, which is why `AUX_FRAMES`
retires. A rotor's frames are placed FROM its hub, so turning the rotor
and leaving them behind was stating an incidence the axes never got, and
a row had to list them by hand to fix it. Turning `PUSHER` turns
`PUSHER_SMRP`, `PUSHER_RMRP` and every `PUSHER_RMRP<k>`, so the motion
created after it spins about the pitched axis and the blade loads a pproc
entry reads in those frames stay in the blade's own axes, with nothing
else to write. An alias that is not a rotor owns no frame and turns none.

`FAMILIES` is the 0.14.0 spelling of `ALIAS` and is REFUSED since 0.15.0,
naming `ALIAS` as the word to write. A record stating `ALIAS` and
`FAMILIES` both is refused for a second reason: one rotation turns ONE
set.

`AUX_FRAMES` is **not deprecated and not removed**: it is no longer
NEEDED for a rotor, because the alias carries that rotor's frames, and it
still names any frame you want turned that the alias does not own. Naming
a frame the alias already carries costs nothing, since no frame turns
twice however many names it answers to.

**Migrating a `FAMILIES` record.** The key changes AND SO DOES THE VALUE:
`FAMILIES: Blade,S` becomes `ALIAS: PUSHER`, the rotor those families
belong to, not the list itself. The refusal names the words the
reference declares, so the value is in front of whoever reads it. A families list
spanning two rotors becomes one record per rotor. `ANGLE` and `AXIS` are
unaffected.

The rotation is emitted after every frame exists and before any motion is
created, on every run type. One row is one geometry, so the angles of a
study are one row each, and the sweep column keeps its meaning: the
reserved key `angle_sweep_deg` (the reserved-keys paragraph above) is
still read as a geometric rotation sweep of its own, and a row sweeping it
beside an aerodynamic axis is refused as it always was; it is not the way
to state the study's angles, `ROTATE` is.

A family the geometry lacks, a frame nothing defined, an axis token not of
the form `frame-axis`, a record missing one of its three keys or carrying a
key a rotation does not read, an angle that is not a number, and the key on
a `LEGACY` row (whose recipe reads its keys and reads no rotation) are each
refused at `pyfs-matrix plan` naming the row, and the first two name what
the case DOES define:

```text
case '1020' states ROTATE with 'NoSuchFamily', and the sidecar
30_BLADE.boundaries.toml beside 30_BLADE.fsm declares no boundary of that
name or family; it declares 'Blade1', 'S', 'N'. Write one of those, or a
family name (the label without its trailing number) to select every member
the file carries.
```

A rotor row that turns its blades and does not name the frame they spin
about among the auxiliaries (`<ALIAS>_SMRP` on a flat row, one per rotor and so
on for the records of a `MOTIONS` row) is accepted and WARNS naming the
frame: the blades turn and the axis stays, which is a physics call the row
may mean, so it is not refused.

What the solver does with the rotated mesh is the measurement of the seat
run the reference study books (PFS-2034.05): the package emits the rotation the
manual documents, citing a frame the manual's own sample cites, and the
run record is where the accepted geometry will be read from.

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
  MOTIONS: {MOVING_BC_ALIAS: PORT / RPM: 2400}
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
`goldens/matriz_vocab/POLAR-8002_M10AL+000BE+000J+060.txt`, emits
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

`run_matrix` returns one record per executed point, and the same rows
are on disk in the workspace's manifest:

```text
matrix/sim_8001/a+00.0
matrix/sim_8001/a+02.0
matrix/sim_8002/b-03.0
matrix/sim_8002/b+03.0
```

Two rows of a matrix, four runs, four records. Each carries its
terminal status, and there is no fifth state: a point that did not
finish says so rather than being missing.

## Writing no Python at all: the workflow

Everything above needs a recipe, and a recipe is Python. A **workflow**
is the way out of that. Name a run type in the `WORKFLOW` column and the
package builds the whole script itself, from the row and from what the
row's identifiers resolved to.

Three types ship today.

Both open the row's `GEOMETRY` first when the row names one, and both
initialize the solver under the row's `SYMMETRY`.

`steady` is one point of a polar: a uniform free stream, the solver
settings the row's `SET` identifier resolved to, one solve, one loads
export.

`unsteady` is one point of a body that does not move, solved in the
time domain: a uniform free stream, a physical time loop the row states
directly, one solve, one loads export. It exists because a study often
needs the unsteady answer for a shape with no rotor in it, and because a
powered and an unpowered configuration are only comparable when they are
solved on the SAME discretisation.

**Its clock is `DELTA_TIME` and `TIME_ITERATIONS`, and the azimuthal pair
is refused on it.** `DELTA_THETA` and `REVOLUTIONS` are not a clock: they
become one by dividing by a rotor speed, and a run that turns nothing has
none. The refusal says so and does not offer you a rotor speed, because a
speed stated to satisfy it would set the physical time step of a run that
emits no motion. A row carrying `RPM`, `ADVANCE_RATIO`, `RPM_SIGN`,
`ROTOR_AXIS`, `ROTOR_ORIGIN` or `MOVING_BOUNDARIES` is refused for the
same reason: nothing would read them, and the run would be recorded as
though they had been honoured.

**And one refusal reaches an `unsteady` row without its author touching
the row at all.** A solver preset stating a wake termination in
REVOLUTIONS is refused on this run type, because a run that turns
nothing has no revolution for the setting to be counted in. The run
does have a time loop, so the setting is not meaningless in principle;
it is unstateable in revolutions, and this package records no
steps-spelled preset key for it. Drop the key from the preset the row
names, or give that row a preset of its own. A steady row meets a
different refusal for a different reason, and a rotor row meets none.

**`LOG_OUTPUT` applies here too**, and for the same reason it applies to
a rotor run: an unsteady time loop always reaches its prescribed end, so
the iteration counter judges nothing and the run would be recorded
`COMPLETED_MAX_ITER` whatever the solver did. Name the log among the
row's outputs and the residuals decide instead.

`unsteady_rotor` is a blade-resolved rotor run: a rotor coordinate
system at the hub the row declares, one rotary motion turning at the
row's `RPM` about the row's `ROTOR_AXIS`, and a physical time loop. The
values it needs come off the row and nowhere else, and a row missing one
of them is refused before anything runs, naming the row and the cell.

This is the matrix the suite runs for all three types, byte for byte:

```text title="workflow_rotor_matrix.fs"
POL  | AIRCRAFT  | DESCRIPTION            | FLIGHT_CONDITION | SWEEP_VALUES   | REF  | SET  | PPROC  | FS_BUILD | HIDDEN | RUN | WORKFLOW       | VAR_NAMES_VALUES
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
7001 | RotorRig  | ROTOR_UNSTEADY         | TASmps:30.0, REmi:1.20, ALPHA:sweep | 0.0            | r003 | s002 | p001   | 26.120   |    1   |  1  | unsteady_rotor | VELOCITY: 30.0 / RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_TIME: 0.0001 / TIME_ITERATIONS: 720 / WINDOW_DEGREES: 90
7002 | RotorRig  | STEADY_REFERENCE       | TASmps:30.0, REmi:1.20, ALPHA:sweep | 0.0,2.0        | r003 | s002 | p001   | 26.120   |    1   |  1  | steady         | VELOCITY: 30.0
7003 | RotorRig  | UNSTEADY_NO_ROTOR      | TASmps:30.0, REmi:1.20, ALPHA:sweep | 0.0            | r003 | s002 | p001   | 26.120   |    1   |  1  | unsteady       | VELOCITY: 30.0 / DELTA_TIME: 0.00025 / TIME_ITERATIONS: 480
```

**NO ROW HERE NAMES A `GEOMETRY`, AND THAT IS WHAT THEY ARE FOR.** This
file is the suite's proof that a matrix written before v0.8.1 renders
exactly the bytes it always did, so it deliberately names none of the
three keys; run as it stands, it solves whatever the solver already has
open, which is the defect v0.8.1 exists to remove.

**EVERY** row needs the cell, not just the rotor one: a row that keeps
none opens nothing and is told nothing. The fragment below is written for
this page rather than lifted from the suite, and shows each row's
`VAR_NAMES_VALUES` tail with the rest elided:

```text
7001 ... | unsteady_rotor | GEOMETRY: blade_sector.fsm / VELOCITY: 30.0 / RPM: 1200 / ...
7002 ... | steady         | GEOMETRY: blade_sector.fsm / VELOCITY: 30.0
```

with `blade_sector.fsm` staged under `inputs/geometries/`. A periodic
sector adds `SYMMETRY: PERIODIC / PERIODIC_COPIES: <n>`.

That combination, periodic copies together with a rotary motion in an
unsteady run, HAS been run on a licensed solver by this repository's own
QA case PHY-05, on 26.120 and again on 26.123, inside its bands. Read
that as evidence about the SOLVER and not about this workflow: PHY-05 is
a hand-built script, and no script the `unsteady_rotor` workflow builds
has run on a licensed solver. What is not established here is whether a
`BLADES` count may divide the phase-locked averaging window on the
strength of it, which is why the limits list still says `BLADES`
configures no rotor.

From the terminal, that whole study is one command:

```text
pyfs-matrix run workflow_rotor_matrix.fs \
    --name rotor --workspace . \
    --sweep-csv sweep.csv
```

No Python is written, no notebook is opened, and nothing sits between
the file and the result. The sweep table lands as `campaign_sweep.csv`
under `post/<matrix stem>/` in the workspace when you do not say where, so a
second matrix of the same workspace keeps its own.

**Each point keeps its outputs in its own folder**, and that is what lets
a swept row be judged point by point. `run` judges each finished point
with the standard assessor, which reads the loads spreadsheet that point
exported, and finds it by CONTENT rather than by name, because a swept
case names its outputs per point and no single literal could name them
all. Each point collects into `sims/<sim>/datapoints/DP-<point>/`, so
what the assessor reads is that point's evidence and nothing else. The
matrix printed above runs as printed, row 7002's two alphas included,
and that is what the acceptance case in the suite does with the
committed fixture unmodified.

**Name your outputs per point.** The folders no longer collide, but the
PRODUCTS do: a point's polar, plots and probe tables are named after the
stem of its loads file, so two points sharing a name produce one table
claiming both runs. That is refused at plan time, before anything runs,
as it was before this release; what changed is the reason, not the rule.
Two outputs of ONE point may not share a name either, and there the old
reason still holds: they land in one folder under one base name.

### Before you spend the seat: what the study will cost

`plan` answers whether a row will run. It does not, on its own, answer what
running it will cost, and the cost is a licence seat and an afternoon. Add
`--cost` and it tables one row per point beside the READY and BLOCKED report:

```text
pyfs-matrix plan matriz.fs --workspace . --fs-version 26.123 --cost
```

```text
point                                      mesh   TEs  layers  visc      type   steps  procs   expected  samples
----------------------------------------------------------------------------------------------------------------
pfs0160/sim_6001/a-02.0_b+00.0            14266     2       -    no    steady       -      8      11.9s        2
pfs0160/sim_6002/a+00.0_b+00.0_j+01.7     13502     0       5    no  unsteady      36      8     194.8s        1

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
them apart in one cell.
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

### The window, said once

`WINDOW_DEGREES: 90` is the span the expensive exports apply over,
counted BACKWARDS from the end of the run: the last quarter turn of the
rotor, which is where the settled physics is. You may write
`WINDOW_STEPS` or `WINDOW_REVOLUTIONS` instead and the package converts,
recording both the form you wrote and the one it computed, so a later
reader can see which was which. A window longer than the run is refused
naming both numbers.

The same window is the AVERAGING window of the reductions below. There
is one window, not two, because two windows you have to keep consistent
is a defect waiting to happen.

### Exports that begin after a threshold

A rotor run settles over its first revolutions, and the loads, sections
and probes worth keeping are the ones after that. `EXPORT_UNSTEADY_AFTER_REV`
states the revolution the per-step exports begin at; `EXPORT_UNSTEADY_AFTER_ITER`
states it as a time step instead. Put one of them on row 7001 above,
with the azimuthal clock:

```text
VELOCITY: 30.0 / RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_THETA: 10 / REVOLUTIONS: 3 / WINDOW_DEGREES: 90 / EXPORT_UNSTEADY_AFTER_REV: 2
```

Ten degrees a step and three revolutions are 108 steps, and two
revolutions are step 72, so the solver exports after each of steps 72 to
108: 37 files per kind, each stamped with its iteration by the solver
itself, `POLAR-7001_..._iteration=72.txt` and so on, beside the
end-of-run export of the same name. The script the row builds registers
two unsteady solver actions before the solver is initialized, in this
order:

```text
SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter
"<python>" "actions/pfs_unsteady_actions.py"

SET_NEW_UNSTEADY_SOLVER_ACTION SCRIPT pfs_unsteady_exports
actions/pfs_unsteady_exports.txt
```

`<python>` is the interpreter that built the script. The solver hands an
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
else: the loads table, the Tecplot file, the sections, the sectional
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

**The stamped files as a series** (since 0.14.0, PFS-2031.18.01). Thirty
seven spreadsheets are not a history until something tables them, so the
products stage writes, per windowed point, one table per export kind
under `post/<matrix stem>/series/`:

```text
post/matriz/series/POLAR-7001_M10AL+000BE+000J+170_loads_series.csv
post/matriz/series/POLAR-7001_M10AL+000BE+000J+170_sections_series.csv
post/matriz/series/POLAR-7001_M10AL+000BE+000J+170_probes_series.csv
```

Every table leads with `step`, `time_s` and `azimuth_deg`, the step's
time and azimuth computed from the clock the run record carries
(`export_window.delta_time_s` and `step_deg`, written by the run since
0.14.0) by the same arithmetic the counter program runs on the machine,
so the two agree by construction; a record written before the clock
leaves the time blank and reads the azimuth off its reductions plan. The
loads series is wide, one row per step and one column per surface and
coefficient (`Total_CL`, `Blade1_CMx`, ...); the sections series (from
the sectional loads export, `_sloads`, the same export the sections
table of the products reads) and the probes series are long, one row per
step and section or probe, with the export's own columns. A run defining
no section or no probe gets the table's header and nothing under it. A
step the solver never stamped is absent and the `products.json` entry
says which steps were tabled; the surface sections export (`_cp`) and
the Tecplot file (`.dat`) of the window are listed there by path, as
`sections_files` and `tecplot_files`, and not tabled, since they are the
solver's own formats. A stamped file the parsers cannot read costs that
point its series, recorded under `skipped` as `series/<run id>`, and
never the stage. These tables are not the "raw series" the reductions
write beside the plots table: that one is the plots export's history of
the coefficients per step, this one is the stamped spreadsheets, surface
by surface and section by section, over the exported window. The series
rest on the stamped files and the record alone, so a simulation whose
polar the stage refuses keeps them.

### The build is an input

A workflow declares the commands it always emits, and the builds it
covers are DERIVED from the command database rather than written down.
`steady` and `unsteady` cover every registered build. `unsteady_rotor`
covers 26.101 and later, because the earlier builds'
databases carry no `SET_MOTION_ROTOR_AXIS` and no
`SET_MOTION_ROTOR_RPM`: those builds configure a rotor by flagging an
existing motion instead, which is a different vocabulary and not a
substitution this package will make for you. Asked for a build outside
its range, the workflow refuses before it emits its first line, and the
refusal names the build you gave, the builds it covers, and the commands
that decided it.

Because the range is derived, a build registered tomorrow joins it the
moment its evidence lands, and nobody has to remember to widen a list.

### The four reductions of an unsteady case

An unsteady rotor case asks for four things and gets four files: the
**raw series**, the **time average** over the window above, the
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

## Where this example comes from

Every artefact on this page is lifted from the test suite rather than
written for the page. The first matrix is
`tests/tier1_offline/fixtures/matrix_registry.fs` byte for byte; the input library,
the recipe and the call are those of
`test_run_matrix_executes_and_records_every_point` in
`tests/tier1_offline/test_matrix_run.py`, and the four run identifiers above are the
ones that test asserts.

The workflow matrix is `tests/tier1_offline/fixtures/workflow_rotor_matrix.fs` byte
for byte, and the test that runs it is
`test_the_committed_matrix_drives_the_workflow_with_no_python_recipe` in
`tests/tier1_offline/test_workflows.py`, which builds every row of it and asserts that
no `module:function` reference appears anywhere in the call.

That is the point of doing it this way. An example written for a page is
true the day it is written and quietly false afterwards; an example
lifted from an executed test fails CI when it stops being true.
`tests/tier1_offline/test_docs_example_currency.py` holds the two together, so this
page cannot drift from the suite without the suite going red.

The code blocks are not executed by the docs build, and are marked so.
They need a temporary directory, a staged input library and a stub
standing in for FlightStream, none of which belong in a documentation
build. The guarantee is carried by the lift, not by the block.

## What does not exist yet

Said plainly, because a page that documents an unbuilt capability is
worse than no page at all.

- **A row's `REF` code changes no emitted line, and neither does its
  `BLADES` count.** The reference artifact resolves, and the solver
  model and the fluid state are still decided in the builders rather
  than by a cell, so coefficients come out against the solver's own
  defaults rather than against the areas and lengths the campaign
  declared, and a case runs `INCOMPRESSIBLE` at sea level whatever the
  campaign flew. `BLADES` divides the phase-locked averaging window of a
  row that names NO rotor by alias and nothing else, so it does not
  configure the rotor and does not interact with the symmetry the row now
  declares, however reasonably a reader pairs the two cells; since 0.15.0
  a row that names its rotors takes each blade count from that rotor's own
  block and needs the cell for nothing (FR-68). Both are scoped, and where they should live is an
  open design question: a row, like everything else a workflow reads, or
  a solver-setup preset, since a fluid and a solver model are
  campaign-wide conditions rather than case identity.

- **You cannot add a workflow of your own.** The table is this
  package's, and there is deliberately no way to register into it: a
  type this package builds is a type it can also refuse before it runs,
  and that guarantee is exactly what a user-supplied entry would remove.
  Your own physics goes in a recipe, which is what recipes are for.
- **Nothing runs the four reductions for you after a campaign.** The
  reader, the average, the writing seam and the plan that says which
  windows all ship, and the composition is executed in the suite. What
  does not exist is the step that fires it at the end of a run.
- **No cell reaches the post-mirror loads setting.** A `SYMMETRY: MIRROR`
  row takes the solver's own default for whether the reported loads are
  the half model's or the full one's. That default was calibrated on a
  licensed 26.120 as ENABLE, which is the value a mirrored study wants,
  so this is a declaration that cannot be made rather than a wrong
  number being produced, and it rests on one build's measurement. A
  study that needs it stated explicitly is a recipe today.
- **A workflow opens a saved simulation only.** No matrix cell declares
  mesh units, so a `.stl` or `.obj` staged in the library resolves
  perfectly well and is then refused when the script is built, rather
  than being imported under a unit nobody chose. Convert it once through
  [mesh inputs](mesh-inputs.md). A recipe of your own is not bound by
  this: it declares the units itself.
- **A workflow row that names no `GEOMETRY` is accepted in silence.** It
  emits no open, which is exactly what keeps every pre-v0.8.1 matrix
  rendering as it did, and it means a row migrated from a recipe by
  changing `LEGACY` to a workflow name, while keeping a `FSM_FILE` key of
  its own, opens nothing and is told nothing. Rename the key to
  `GEOMETRY` when you move a row off `LEGACY`.
- **No script BUILT BY THE `unsteady_rotor` WORKFLOW has been run on a
  licensed solver yet.** The workflow is proven to build a script every
  registered build's command database accepts, which is not the same
  fact as a solver accepting it. Read `unsteady_rotor` as evidenced
  against the database and not against a run. The QA physics suite's own
  unsteady propeller case (PHY-05) HAS run on a licensed machine and
  sits inside its bands, and it is a different script, hand-built rather
  than emitted by this workflow.
- **Naming a second build is no longer a limit.** See the executable
  registry above, which is this fact's one home.
- **There is no result-array facade.** No interpolation along a named
  axis, no re-parameterisation, no trim extraction. FR-20 carries that
  promise and is `pending`.

Where a capability above matters to you, the roadmap and the SRS
requirement statuses are where its state is tracked, and the changelog
is where it will be announced.
