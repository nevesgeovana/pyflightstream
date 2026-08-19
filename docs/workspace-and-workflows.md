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

The word **workflow** on this page means something narrow and worth
being exact about, because it is used loosely elsewhere. It is the path
from a filled-in run matrix to results on disk: read the matrix, resolve
each row against the input library, build one script per point, run
them, collect the outputs, write the record. There is no workflow
object in the package, and the section at the bottom of this page says
what else is not built. What follows is what ships today.

## What a run matrix is

A run matrix is a pipe-separated table, one row per simulation, that
this package reads forever: the format is a first-class interface
rather than an import step (FR-10, FR-35). Each row names a point of
interest, the sweep it wants, and, by identifier, the reference, the
solver preset and the boundary group it should be resolved against.

This is the matrix the test suite runs, byte for byte:

```text title="matrix_registry.fs"
POL  | AIRCRAFT  | DESCRIPTION            | RE      | MACH    | SWEEP_TYPE  | SWEEP_VALUES   | REF | SET | ENTRY | FS_SCRIPT | FS_BUILD | HIDDEN | RUN | VAR_NAMES_VALUES
------------------------------------------------------------------------------------------------------------------------------------------------------------------------
8001 | TestWing  | REGISTRY_ALPHA         |  3.10   | 0.0890  | AL          | 0.0,2.0        | 003 | 002 | 001   | 003       | 26.120   |    0   |  1  | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt
8002 | TestWing  | REGISTRY_BETA          |  3.10   | 0.0890  | BE          | -3.0,3.0       | 003 | 002 | 001   | 003       | 26.120   |    1   |  1  | FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt
```

Read one row across. `POL` is the point of interest, and it becomes the
simulation identifier (`sim_8001`). `SWEEP_TYPE` and `SWEEP_VALUES` say
what varies: `AL 0.0,2.0` is an angle-of-attack sweep at zero and two
degrees, so this one row is two runs. `REF`, `SET` and `ENTRY` are the
three identifiers that reach into the input library. `FS_BUILD` names
the FlightStream build the row wants, and `FS_SCRIPT` names the recipe
that builds its script. `RUN` is the switch that says whether the row
takes part at all.

Four runs come out of those two rows. Nothing in the matrix says where
anything is written, and that is deliberate: naming is the workspace's
job.

## The input library those identifiers resolve against

The three code columns are looked up in the workspace's own `inputs/`
folder. This is the library the suite stages for the example below:

```text
inputs/
  references/003.toml     area_m2 = 10.0, chord_m = 1.2, span_m = 8.0
  references/004.toml     area_m2 = 12.0, chord_m = 1.5, span_m = 9.0
  setups/002.toml         iterations = 800, convergence = 1e-6
  setups/003.toml         iterations = 400, wake_layers = 4
  groups/001.toml         wing = ["wing_left", "wing_right"], body = [1]
  executables.toml        which executable each build identifier means
```

`REF 003` therefore means "the reference quantities in
`inputs/references/003.toml`", and both rows of the matrix above use
the same one. An identifier that is not staged is refused before
anything runs, and the refusal names the identifier, the kind and what
is available.

`inputs/executables.toml` is the one file that is about your machine
rather than about your study: it maps a build identifier such as
`26.120` onto the executable on this computer. It is why the matrix can
name a build and stay portable.

## From a filled-in matrix to results, in one call

<!-- skip: next -->
```python
from pyflightstream.cases.matrix import run_matrix

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
`inputs/setups/002.toml`: the matrix said `SET 002` and the resolved
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

## Where this example comes from

Every artefact on this page is lifted from the test suite rather than
written for the page. The matrix is `tests/fixtures/matrix_registry.fs`
byte for byte; the input library, the recipe and the call are those of
`test_run_matrix_executes_and_records_every_point` in
`tests/test_matrix_run.py`, and the four run identifiers above are the
ones that test asserts.

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

- **There is no workflow object.** No class, no registry, no
  `Workflow(...)` you can construct or name. What ships is the matrix,
  the recipe, and `run_matrix`. If you read the word workflow elsewhere
  in this project's planning, it means the path described above and not
  a thing you can import.
- **There is no unsteady or rotor workflow.** The per-timestep reader
  and the blade-passage average exist in `pyflightstream.post`, and
  nothing wires them to a campaign: you call them yourself on the files
  a run produced.
- **A campaign declares ONE FlightStream build.** The matrix has an
  `FS_BUILD` column per row, and a matrix whose active rows name two
  different builds is refused today. Comparing two builds means two
  campaigns.
- **There is no result-array facade.** No interpolation along a named
  axis, no re-parameterisation, no trim extraction. FR-20 carries that
  promise and is `pending`.
- **The command-line tool does not run anything.** `pyfs-matrix` can
  convert a matrix and pre-flight it; executing is a Python call.

Where a capability above matters to you, the roadmap and the SRS
requirement statuses are where its state is tracked, and the changelog
is where it will be announced.
