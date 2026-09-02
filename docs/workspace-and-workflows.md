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
POL  | AIRCRAFT  | DESCRIPTION            | FLIGHT_CONDITION | SWEEP_TYPE  | SWEEP_VALUES   | REF  | SET  | ENTRY  | FS_SCRIPT | FS_BUILD | HIDDEN | RUN | WORKFLOW | VAR_NAMES_VALUES
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
8001 | TestWing  | REGISTRY_ALPHA         | MACH:0.0890, REmi:3.10 | AL          | 0.0,2.0        | r003 | s002 | e001   | 003       | 26.120   |    0   |  1  | LEGACY   | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt
8002 | TestWing  | REGISTRY_BETA          | MACH:0.0890, REmi:3.10 | BE          | -3.0,3.0       | r003 | s002 | e001   | 003       | 26.120   |    1   |  1  | LEGACY   | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt
```

Read one row across. `POL` is the point of interest, and it becomes the
simulation identifier (`sim_8001`). `FLIGHT_CONDITION` states the flow
condition the row runs at, as comma-separated `KEY:value` pairs from a
closed set; it is MANDATORY, and it replaced the `RE` and `MACH` columns
at v0.9.0. What it means and which quantity gets solved for is
[its own page](flight-conditions.md). `SWEEP_TYPE` and `SWEEP_VALUES` say
what varies: `AL 0.0,2.0` is an angle-of-attack sweep at zero and two
degrees, so this one row is two runs. `REF`, `SET` and `ENTRY` are the
three identifiers that reach into the input library. `FS_BUILD` names
the FlightStream build the row wants, and `FS_SCRIPT` names the recipe
that builds its script. `WORKFLOW` names the run type; `LEGACY` means
"none, use the recipe", which is what every matrix written before v0.8.0
means and what these two rows say. `RUN` is the switch that says whether
the row takes part at all.

`VAR_NAMES_VALUES` is the last cell and the one that carries everything
else, as `KEY: value` pairs separated by ` / `. The rows above use
`FSM_FILE`, which is a key of THEIR OWN: nothing in the package reads it,
and the recipe named by `FS_SCRIPT` is what resolves it and opens the
file. That is still how a recipe works.

**A WORKFLOW reads keys the package defines**, and since v0.8.1 three of
them close the gap that made the capability unusable:

* `GEOMETRY: <stem>` names a geometry staged under `inputs/geometries/`,
  resolved the same way `REF`, `SET` and `ENTRY` are, and refused with
  the available stems when the id is not there. The value is the file
  name STEM, never the file name: with `wing_clean.fsm` staged, the cell
  reads `GEOMETRY: wing_clean`. The workflow opens it first, before
  anything else, and it opens the STAGED copy, so the file the manifest
  hashed and the file the solver read are the same bytes.

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

    `MIRROR` carries two cautions the cell cannot enforce. The mode
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

A propeller study is designed in an advance ratio and an azimuthal step.
The rev/min, the seconds per step and the number of steps are what those
work out to at the run's own velocity, so an `unsteady_rotor` row states
the decisions and the package derives the rest.

* `ADVANCE_RATIO: <J>` sets the rotor speed as `n = V / (J D)`, against
  the velocity this row already resolves and the `propeller_diameter_m`
  its reference artifact carries. `RPM: <rev/min>` states the speed
  directly instead. A row states exactly one of the two, and stating
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
  `DELTA_TIME = theta / (6 rpm)` and
  `TIME_ITERATIONS = REVOLUTIONS * 360 / DELTA_THETA`. `DELTA_TIME` and
  `TIME_ITERATIONS` state the same thing directly and still work; a row
  states one pair, and half a pair is refused naming the key that is
  missing, because neither half implies the other.

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

**THE RESERVED NAMES ARE THESE, AND THE LIST HAS GROWN TWICE.**
`VAR_NAMES_VALUES` is your namespace except for the keys the package
itself reads, and a cell of yours that already spells one of them is
read by the package rather than ignored:

| release | names it reserved |
|---|---|
| before v0.8.1 | `VELOCITY`, `RPM`, `ROTOR_AXIS`, `ROTOR_ORIGIN`, `ROTOR_SHEDDING`, `BLADES`, `MOVING_BOUNDARIES`, `DELTA_TIME`, `TIME_ITERATIONS`, `WINDOW_DEGREES`, `WINDOW_STEPS`, `WINDOW_REVOLUTIONS`, `OUTPUTS` |
| v0.8.1 | `GEOMETRY`, `SYMMETRY`, `PERIODIC_COPIES` |
| this release | `ADVANCE_RATIO`, `RPM_SIGN`, `DELTA_THETA`, `REVOLUTIONS`, `LOG_OUTPUT` |

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
of them. A name the geometry does not carry is refused, listing the ones it
does.

`angle_sweep_deg` IS RESERVED TOO, since v0.7.0, and it is the one whose
match FOLDS CASE rather than being exact: a cell spelling it in any
casing is read as a sweep of a geometric rotation, and a row that also
sweeps an aerodynamic axis is REFUSED for it. Its lookalike `angle_deg`
is a value you write and nothing reads at run time. Only one of the two
can stop a campaign.

The `matrix_` prefix is the CONVERTER's rather than yours:
`matrix_ref`, `matrix_set`, `matrix_entry`, `matrix_fs_script`,
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

Going forward, every workflow crossed with two case shapes and every
build it covers is pinned as a committed golden under
`tests/goldens/workflows/` and compared byte for byte on every run of the
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

A row sweeps ONE thing. `SWEEP_TYPE` and `SWEEP_VALUES` sweep the
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
  groups/e001.toml        wing = ["wing_left", "wing_right"], body = [1]
  executables.toml        which executable, and optionally which version,
                          each build identifier means
```

`REF r003` therefore means "the reference quantities in
`inputs/references/r003.toml`", and both rows of the matrix above use
the same one. The identifier is yours to choose; the matrix and the
file name simply have to agree. An identifier that is not staged is
refused before anything runs, and the refusal names the identifier, the
kind and what is available.

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
   nothing, and a warning names it AND the reason. The eleven this
   package declares today are `solver`, `motion`, `mesh_order_list`,
   `symmetry_type`, `symmetry_loads`, `unsteady_delta_theta_deg`,
   `unsteady_N_revolutions`, `set_base_region_trailing_edges`,
   `significant_digits`, `slipstream_wake_stabilization` and
   `wake_layers`. `symmetry_type` belongs to the geometry a row opens
   and is stated in the row's `SYMMETRY`; `solver` and `motion` are what
   the `WORKFLOW` column decides; `unsteady_delta_theta_deg` and
   `unsteady_N_revolutions` are superseded by the row's `DELTA_THETA`
   and `REVOLUTIONS`; `mesh_order_list` is one mesh's boundary order and a
   preset is shared by several; `set_base_region_trailing_edges` is a
   separation model that selects boundaries, and a preset carries no
   selection, so it is a recipe's job; and the last three have no
   emitter in this package at all.

    That list is maintained by hand and this page is not generated, so
    **read the warning your own preset prints** rather than this
    paragraph: it names every key of YOUR file that was recorded, each
    with its reason. What the paragraph is for is that the set is
    closed and short enough to see at once.

    `symmetry_loads` is recorded-only although it HAS an emitter, and
    that is a decision rather than a gap: applying it multiplies or
    divides every published coefficient of a periodic or mirrored case
    by the copy count. That is a change to make with a measurement in
    hand, not a key to honour silently.

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

`stabilization` and `stabilization_strength` resolve as a PAIR into one
number. Disabled means ABSENT and not a strength of zero, which would
still be switched on.

`inputs/executables.toml` is the one file that is about your machine
rather than about your study: it maps a build identifier such as
`26.120` onto the executable on this computer. It is why the matrix can
name a build and stay portable.

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
configuration, the moment point, and a `[propeller]` block. This is
`inputs/references/r003.toml` in full, the same artifact the listing
above summarises by its first three lengths:

```toml
area_m2 = 10.0
chord_m = 1.2
span_m = 8.0
propeller_diameter_m = 2.0

[moment_point]
x_m = 0.3
y_m = 0.0
z_m = 0.0

[propeller]
radius_m = 1.0
n_blades = 3
pitch_deg = 0.0
toe_deg = 0.0
rotation = "clockwise"
blade_travel = "inboard_down"
rpm_sign_installed = -1
rpm_sign_isolated = 1

[propeller.position]
x_m = 0.0
y_m = 0.0
z_m = 0.0
```

`propeller_diameter_m` SITS WITH THE OTHER LENGTHS AND NOT IN THE
`[propeller]` BLOCK, which is the natural-looking home and the wrong one.
The propeller block is recorded metadata that nothing in this package
reads; the diameter is a DIVISOR of published numbers, exactly like the
area and the chord. It is what an advance ratio is a ratio against, so a
row stating `ADVANCE_RATIO` and a reference without this field is
refused naming the field to add, and it is what the propeller
coefficients normalise on. It is optional, because a configuration with
no propeller has no diameter and a placeholder would be worse than
nothing.

`[propeller.position]` is the hub position in the simulation geometry
frame, in m, and it defaults to the origin if you leave the table out,
which is a default and not a measurement.

THE SENSE OF ROTATION IS RECORDED TWICE ON PURPOSE, in the two
vocabularies vendors publish it in, and the second one arrived at 0.8.0
because the first campaign this library was checked against recorded it
the other way.

`rotation` is `clockwise` or `counterclockwise` viewed from behind the
aircraft looking forward. Both it and `blade_travel` fold case, hyphens
and whitespace, so a datasheet's `Counter-Clockwise` and `Inboard Up`
are read as written. `blade_travel` is `inboard_up` or `inboard_down`
and names where the blade nearest the fuselage travels,
in the aircraft body frame with the aircraft upright; it describes the
blade at its inboard azimuth and not the disc as a whole. That is the
form the datasheet of the one campaign this library has been checked
against printed, and it is common enough that the field exists; how
common is not something this repository has measured. A centreline propeller has no
inboard blade and leaves the field out.

They are separate fields rather than four values of one field because
they are not interchangeable: `blade_travel` is side-independent, so the
left and the right propeller of a symmetric pair carry the same word,
and turning it into a viewed-from-behind sense means knowing which side
this propeller is on.

Only `rotation` is required, and an artifact carrying `blade_travel`
alone is refused with that reason rather than with a bare missing-field
error. WORKING OUT THE ONE FROM THE OTHER IS MECHANICAL ONCE YOU KNOW
THE SIDE, and the library cannot do it for you because no field records
the side. Stand behind the aircraft looking forward: a right-side
propeller has its inboard blade toward the centreline, at the 9 o'clock
position of its own disc, and a blade there travelling up is moving
9 to 12, which is clockwise. So `inboard_up` on a right-side propeller
is `clockwise`, `inboard_down` there is `counterclockwise`, and a
left-side propeller is the mirror of both. Follow the derivation rather
than the conclusion: it is two sentences, and getting it backwards is
the failure this whole section exists to prevent.

`rpm_sign_installed` and `rpm_sign_isolated` are each `1` or `-1` and
record a MEASURED sign of the rotor speed, one for the installed meshes
of the configuration and one for the isolated ones, which may be the
opposite hand and then take the opposite sign for the same published
sense of rotation. Both are optional, and leaving one out means your
campaign has not established it, never that it is `+1`. A configuration
with no isolated meshes at all leaves the same silence: not measured and
not applicable are deliberately not distinguished.

Both are also closed to coercion, not only to value: `true` and `1.0`
are refused rather than read as `1`, because a sign that was never
measured must not arrive by conversion. And the domain is checked on
assignment as well as on load, so `propeller.rpm_sign_installed = 0`
after reading the artifact is refused too.

Two warnings, and neither is a detail.

Nothing in the package reads the propeller block. Not the signs, and not
`rotation`, `blade_travel`, `radius_m`, `n_blades` or `position` either:
the whole block is recorded, and writing any of it changes no emitted
script on its own.

AND THE ARTIFACT DOES NOT REACH A RECIPE, which is worth knowing before
you write one. `resolve_matrix` narrows this artifact to the reference
area and length the case needs, and a recipe is called with the case and
the script, so `case.reference.propeller` does not exist. The full
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
    propeller = reference.propeller
    if propeller is None or propeller.rpm_sign_installed is None:
        raise ValueError(
            f"{case.sim_id}: this recipe emits a rotor speed and the reference "
            "artifact records no measured sign for the installed meshes. Absence "
            "means the campaign has not established it, so there is nothing to "
            "assume here"
        )
    rpm = propeller.rpm_sign_installed * 2400.0   # your recipe knows which mesh it staged
```

The two guards on the way to `rpm` are the point rather than ceremony.
`propeller` is `None` for any reference artifact that describes no
propeller, and a sign left out means your campaign has not established
it, which is not the same as `+1`.

Which of the two signs applies is your recipe's knowledge and not the
artifact's: nothing in the library records which geometries are the
installed meshes and which the isolated ones.

And a sense of rotation does not determine that sign. Getting from a
published sense to the number a motion command takes needs the rotor
axis, the side of the aircraft and the handedness of the mesh you
actually loaded. That is the reason these are recorded rather than
derived: a campaign that established its signs by measurement reproduces
the measurement on every later run instead of re-deriving it and
possibly re-deriving it differently.

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
`recipes` maps the matrix's `FS_SCRIPT` code onto the name of a recipe,
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

Two types ship today.

Both open the row's `GEOMETRY` first when the row names one, and both
initialize the solver under the row's `SYMMETRY`.

`steady` is one point of a polar: a uniform free stream, the solver
settings the row's `SET` identifier resolved to, one solve, one loads
export.

`unsteady_rotor` is a blade-resolved rotor run: a rotor coordinate
system at the hub the row declares, one rotary motion turning at the
row's `RPM` about the row's `ROTOR_AXIS`, and a physical time loop. The
values it needs come off the row and nowhere else, and a row missing one
of them is refused before anything runs, naming the row and the cell.

This is the matrix the suite runs for those two types, byte for byte:

```text title="workflow_rotor_matrix.fs"
POL  | AIRCRAFT  | DESCRIPTION            | FLIGHT_CONDITION | SWEEP_TYPE  | SWEEP_VALUES   | REF  | SET  | ENTRY  | FS_SCRIPT | FS_BUILD | HIDDEN | RUN | WORKFLOW       | VAR_NAMES_VALUES
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
7001 | RotorRig  | ROTOR_UNSTEADY         | TASmps:30.0, REmi:1.20   | AL          | 0.0            | r003 | s002 | e001   | 010       | 26.120   |    1   |  1  | unsteady_rotor | OUTPUTS: loads_{point}.txt / VELOCITY: 30.0 / RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_TIME: 0.0001 / TIME_ITERATIONS: 720 / WINDOW_DEGREES: 90
7002 | RotorRig  | STEADY_REFERENCE       | TASmps:30.0, REmi:1.20   | AL          | 0.0,2.0        | r003 | s002 | e001   | 003       | 26.120   |    1   |  1  | steady         | OUTPUTS: loads_{point}.txt / VELOCITY: 30.0
```

**NEITHER ROW NAMES A `GEOMETRY`, AND THAT IS WHAT THEY ARE FOR.** This
file is the suite's proof that a matrix written before v0.8.1 renders
exactly the bytes it always did, so it deliberately names none of the
three keys; run as it stands, it solves whatever the solver already has
open, which is the defect v0.8.1 exists to remove.

**BOTH** rows need the cell, not just the rotor one: a row that keeps
none opens nothing and is told nothing. The fragment below is written for
this page rather than lifted from the suite, and shows each row's
`VAR_NAMES_VALUES` tail with the rest elided:

```text
7001 ... | unsteady_rotor | GEOMETRY: blade_sector / OUTPUTS: loads_{point}.txt / VELOCITY: 30.0 / RPM: 1200 / ...
7002 ... | steady         | GEOMETRY: blade_sector / OUTPUTS: loads_{point}.txt / VELOCITY: 30.0
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
    --name rotor --fs-version 26.120 --workspace . \
    --workflow 010=unsteady_rotor --workflow 003=steady \
    --sweep-csv sweep.csv
```

No Python is written, no notebook is opened, and nothing sits between
the file and the result. The sweep table lands as `sweep.csv`, in the
workspace root when you do not say where.

One limitation applies to that command TODAY and it is worth knowing
before you meet it. `run` judges each finished point with the standard
assessor, which reads the loads spreadsheet the point exported. Every
point of one row writes into the same simulation folder, so from the
SECOND point of a swept row onward the assessor finds two files that
both read as loads tables and refuses rather than guessing between
them. A row with one sweep value runs; a row with several does not yet.
Running such a row from Python, with an assessor of your own, is
unaffected.

**That limit applies to the matrix printed above, as printed.** Row 7002
sweeps two alphas, so the command shown runs 7001 and cannot judge
7002's second point. Cut 7002 to one sweep value to run the block
exactly as it stands, which is what the suite does: it keeps a helper
that rewrites `0.0,2.0` to a single value for the acceptance cases, and
the case that runs the committed fixture unmodified is marked as an
expected failure until this is fixed.

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

### The build is an input

A workflow declares the commands it always emits, and the builds it
covers are DERIVED from the command database rather than written down.
`unsteady_rotor` covers 26.101 and later, because the earlier builds'
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
blade passage is that divided by `BLADES`. The averaging itself is
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
`tests/fixtures/matrix_registry.fs` byte for byte; the input library,
the recipe and the call are those of
`test_run_matrix_executes_and_records_every_point` in
`tests/test_matrix_run.py`, and the four run identifiers above are the
ones that test asserts.

The workflow matrix is `tests/fixtures/workflow_rotor_matrix.fs` byte
for byte, and the test that runs it is
`test_the_committed_matrix_drives_the_workflow_with_no_python_recipe` in
`tests/test_workflows.py`, which builds every row of it and asserts that
no `module:function` reference appears anywhere in the call.

That is the point of doing it this way. An example written for a page is
true the day it is written and quietly false afterwards; an example
lifted from an executed test fails CI when it stops being true.
`tests/test_docs_example_currency.py` holds the two together, so this
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
  campaign flew. `BLADES` divides the phase-locked averaging window and
  nothing else, so it does not configure the rotor and does not interact
  with the symmetry the row now declares, however reasonably a reader
  pairs the two cells. Both are scoped, and where they should live is an
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
- **`pyfs-matrix run` cannot judge a swept row yet.** Stated above where
  the command is, and repeated here because this is the list people
  read: the standard assessor sees every point of a row in one folder
  and refuses from the second point onward. One sweep value per row
  runs today.
- **Naming a second build is no longer a limit.** See the executable
  registry above, which is this fact's one home.
- **There is no result-array facade.** No interpolation along a named
  axis, no re-parameterisation, no trim extraction. FR-20 carries that
  promise and is `pending`.

Where a capability above matters to you, the roadmap and the SRS
requirement statuses are where its state is tracked, and the changelog
is where it will be announced.
