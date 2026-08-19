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
POL  | AIRCRAFT  | DESCRIPTION            | RE      | MACH    | SWEEP_TYPE  | SWEEP_VALUES   | REF  | SET  | ENTRY  | FS_SCRIPT | FS_BUILD | HIDDEN | RUN | WORKFLOW | VAR_NAMES_VALUES
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
8001 | TestWing  | REGISTRY_ALPHA         |  3.10   | 0.0890  | AL          | 0.0,2.0        | r003 | s002 | e001   | 003       | 26.120   |    0   |  1  | LEGACY   | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt
8002 | TestWing  | REGISTRY_BETA          |  3.10   | 0.0890  | BE          | -3.0,3.0       | r003 | s002 | e001   | 003       | 26.120   |    1   |  1  | LEGACY   | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt
```

Read one row across. `POL` is the point of interest, and it becomes the
simulation identifier (`sim_8001`). `SWEEP_TYPE` and `SWEEP_VALUES` say
what varies: `AL 0.0,2.0` is an angle-of-attack sweep at zero and two
degrees, so this one row is two runs. `REF`, `SET` and `ENTRY` are the
three identifiers that reach into the input library. `FS_BUILD` names
the FlightStream build the row wants, and `FS_SCRIPT` names the recipe
that builds its script. `WORKFLOW` names the run type; `LEGACY` means
"none, use the recipe", which is what every matrix written before v0.8.0
means and what these two rows say. `RUN` is the switch that says whether
the row takes part at all.

Four runs come out of those two rows. Nothing in the matrix says where
anything is written, and that is deliberate: naming is the workspace's
job.

## The input library those identifiers resolve against

The three code columns are looked up in the workspace's own `inputs/`
folder. This is the library the suite stages for the example below:

```text
inputs/
  references/r003.toml    area_m2 = 10.0, chord_m = 1.2, span_m = 8.0
  references/r004.toml    area_m2 = 12.0, chord_m = 1.5, span_m = 9.0
  setups/s002.toml        iterations = 800, convergence = 1e-6
  setups/s003.toml        iterations = 400, wake_layers = 4
  groups/e001.toml        wing = ["wing_left", "wing_right"], body = [1]
  executables.toml        which executable each build identifier means
```

`REF r003` therefore means "the reference quantities in
`inputs/references/r003.toml`", and both rows of the matrix above use
the same one. The identifier is yours to choose; the matrix and the
file name simply have to agree. An identifier that is not staged is
refused before anything runs, and the refusal names the identifier, the
kind and what is available.

`inputs/executables.toml` is the one file that is about your machine
rather than about your study: it maps a build identifier such as
`26.120` onto the executable on this computer. It is why the matrix can
name a build and stay portable.

### What a reference artifact holds beyond the three lengths

The two files above carry only the lengths the sweep table needed. A
reference artifact also carries the moment point and, for a propelled
configuration, a `[propeller]` block. A fuller artifact than either of
the two above, shown whole:

```toml
area_m2 = 10.0
chord_m = 1.2
span_m = 8.0

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

`[propeller.position]` is the hub position in the simulation geometry
frame, in m, and it defaults to the origin if you leave the table out,
which is a default and not a measurement.

THE SENSE OF ROTATION IS RECORDED TWICE ON PURPOSE, in the two
vocabularies vendors publish it in, and the second one arrived at 0.8.0
because the first campaign this library was checked against recorded it
the other way.

`rotation` is `clockwise` or `counterclockwise` viewed from behind the
aircraft looking forward. `blade_travel` is `inboard_up` or
`inboard_down` and names where the blade nearest the fuselage travels,
in the aircraft body frame with the aircraft upright; it describes the
blade at its inboard azimuth and not the disc as a whole. That is the
form the datasheet of the one campaign this library has been checked
against printed, and it is common enough that the field exists; how
common is not something this repository has measured. Case, hyphens and
spaces are folded, so `inboard-up` and `Inboard Up` are read as written.

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
resolved = resolve_matrix("matrix_registry.fs", workspace, fs_version="26.120")
propeller = resolved.references["r003"].propeller
rpm = propeller.rpm_sign_installed * 2400.0   # your recipe knows which mesh it staged
```

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
POL  | AIRCRAFT  | DESCRIPTION            | RE      | MACH    | SWEEP_TYPE  | SWEEP_VALUES   | REF  | SET  | ENTRY  | FS_SCRIPT | FS_BUILD | HIDDEN | RUN | WORKFLOW       | VAR_NAMES_VALUES
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
7001 | RotorRig  | ROTOR_UNSTEADY         |  1.20   | 0.0800  | AL          | 0.0            | r003 | s002 | e001   | 010       | 26.120   |    1   |  1  | unsteady_rotor | OUTPUTS: loads_{point}.txt / VELOCITY: 30.0 / RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_TIME: 0.0001 / TIME_ITERATIONS: 720 / WINDOW_DEGREES: 90
7002 | RotorRig  | STEADY_REFERENCE       |  1.20   | 0.0800  | AL          | 0.0,2.0        | r003 | s002 | e001   | 003       | 26.120   |    1   |  1  | steady         | OUTPUTS: loads_{point}.txt / VELOCITY: 30.0
```

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

- **You cannot add a workflow of your own.** The table is this
  package's, and there is deliberately no way to register into it: a
  type this package builds is a type it can also refuse before it runs,
  and that guarantee is exactly what a user-supplied entry would remove.
  Your own physics goes in a recipe, which is what recipes are for.
- **Nothing runs the four reductions for you after a campaign.** The
  reader, the average, the writing seam and the plan that says which
  windows all ship, and the composition is executed in the suite. What
  does not exist is the step that fires it at the end of a run.
- **No unsteady rotor case has been run on a licensed solver yet.** The
  rotor workflow is proven to build a script every registered build's
  command database accepts, which is not the same fact as a solver
  accepting it. Read `unsteady_rotor` as evidenced against the database
  and not against a run.
- **`pyfs-matrix run` cannot judge a swept row yet.** Stated above where
  the command is, and repeated here because this is the list people
  read: the standard assessor sees every point of a row in one folder
  and refuses from the second point onward. One sweep value per row
  runs today.
- **A campaign declares ONE FlightStream build.** The matrix has an
  `FS_BUILD` column per row, and a matrix whose active rows name two
  different builds is refused today. Comparing two builds means two
  campaigns.
- **There is no result-array facade.** No interpolation along a named
  axis, no re-parameterisation, no trim extraction. FR-20 carries that
  promise and is `pending`.

Where a capability above matters to you, the roadmap and the SRS
requirement statuses are where its state is tracked, and the changelog
is where it will be announced.
