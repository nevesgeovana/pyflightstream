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
The pages below are what ships today, one per run type or topic; each fact
has one home, and every other page links to it.

| Page | What it holds |
|---|---|
| [The run matrix, a campaign and its record](workflow-run-matrix.md) | what a run matrix is, how a point is named and redone, several matrices, what comes back |
| [The input library and the solver presets](workflow-input-library.md) | the library the identifiers resolve against, the solver presets, renamed names |
| [The reference artifact](workflow-reference-artifact.md) | the lengths, the study's vocabulary |
| [The steady workflow](workflow-steady.md) | `steady`, and one sweep per row |
| [The unsteady workflow](workflow-unsteady.md) | `unsteady`, and the reductions of an unsteady point |
| [The unsteady rotor workflow](workflow-unsteady-rotor.md) | `unsteady_rotor`, rotor rows, several rotors, exports after a threshold |
| [The quasi-steady rotor](workflow-qsteady-rotor.md) | `qsteady_rotor` |
| [One row, one actuator disc or one custom free stream](workflow-row-flow-inputs.md) | the row keys that replace the uniform free stream |
| [One row, one geometry, turned or moved](workflow-row-geometry-motion.md) | `ROTATE` and `TRANSLATE` |
| [Planning a campaign and what it costs](workflow-plan-and-cost.md) | what `plan` prints, the cost table |
| [Builds, local runs and clusters](workflow-builds-and-hpc.md) | the build as an input, where a point runs |
| [Storage and sync](storage-and-sync.md), [Excel matrix synchronization](excel-matrices.md) | the storage and sync commands |
| [The post-processing artifact and its products](pproc-artifact.md), [extracting more from a finished point](workflow-additional-post.md) | the post-processing side of a row |

## Writing no Python at all: the workflow

A recipe is Python. A **workflow**
is the way out of that. Name a run type in the `WORKFLOW` column and the
package builds the whole script itself, from the row and from what the
row's identifiers resolved to.

Four types ship today: [`steady`](workflow-steady.md),
[`unsteady`](workflow-unsteady.md), [`unsteady_rotor`](workflow-unsteady-rotor.md)
and [`qsteady_rotor`](workflow-qsteady-rotor.md).

Each opens the row's `GEOMETRY` first when the row names one, and each
initializes the solver under the row's `SYMMETRY`.

This is the matrix the suite runs for `steady`, `unsteady` and `unsteady_rotor`, byte for byte:

```text title="workflow_rotor_matrix.fs"
POL  | HIDDEN | RUN | AIRCRAFT  | CONFIGURATION | DESCRIPTION            | FLIGHT_CONDITION | SWEEP_VALUES   | GEOMETRY | REF  | SET  | PPROC  | SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW       | VAR_NAMES_VALUES
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
7001 |    1   |  1  | RotorRig  | -             | ROTOR_UNSTEADY         | TASmps:30.0, REmi:1.20, ALPHA:sweep | 0.0            | -        | r003 | s002 | p001   | -        | -              | -     | -        | 26.120   | unsteady_rotor | VELOCITY: 30.0 / RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_TIME: 0.0001 / TIME_ITERATIONS: 720 / LAST_REVS_AVG: 0.25
7002 |    1   |  1  | RotorRig  | -             | STEADY_REFERENCE       | TASmps:30.0, REmi:1.20, ALPHA:sweep | 0.0,2.0        | -        | r003 | s002 | p001   | -        | -              | -     | -        | 26.120   | steady         | VELOCITY: 30.0
7003 |    1   |  1  | RotorRig  | -             | UNSTEADY_NO_ROTOR      | TASmps:30.0, REmi:1.20, ALPHA:sweep | 0.0            | -        | r003 | s002 | p001   | -        | -              | -     | -        | 26.120   | unsteady       | VELOCITY: 30.0 / DELTA_TIME: 0.00025 / TIME_ITERATIONS: 480 / LAST_ITERS_AVG: 480
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

## Where this example comes from

Every artefact on these pages is lifted from the test suite rather than
written for the page. The first matrix is
`tests/tier1_offline/fixtures/matrix_registry.fs` byte for byte; the input library,
the recipe and the call are those of
`test_run_matrix_executes_and_records_every_point` in
`tests/tier1_offline/test_matrix_run.py`, and the four run identifiers of [the run matrix](workflow-run-matrix.md) are the
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

- **A row's `BLADES` count changes no emitted line, and no cell chooses
  the solver model.** `BLADES` sizes the phase-locked and per-blade
  windows of a row that names NO rotor by alias, and nothing else: it
  does not configure the rotor and does not interact with `SYMMETRY`.
  Since 0.15.0 a row that names its rotors takes each blade count from
  that rotor's own block (FR-68). The solver model is the setup preset's
  `solver_model`, `INCOMPRESSIBLE` when the preset states none; the row's
  `MACH` does not choose it. The reference (`REF`) and the fluid state of
  the flight condition reach the script since 0.9.0.

- **You cannot add a workflow of your own.** The table is this
  package's, and there is deliberately no way to register into it: a
  type this package builds is a type it can also refuse before it runs,
  and that guarantee is exactly what a user-supplied entry would remove.
  Your own physics goes in a recipe, which is what recipes are for.
- **A raw mesh's scale and names are stated, and neither is measured
  yet.** A workflow imports an `.obj` or `.stl` in the unit its sidecar's
  `[import]` table states into a simulation in metres, and whether
  `IMPORT` converts the file's unit into the simulation's has been
  measured on no build. Its boundary names are the sidecar's, written by
  hand, and nothing checks them against the file before the run
  ([mesh inputs](mesh-inputs.md)). The other mesh formats `IMPORT`
  documents are refused by a workflow; a recipe of your own imports them,
  declaring the units itself.
- **A raw mesh's trailing edge by file runs on 26.124 only, and its wake
  termination is measured on a steady point only.** The file route was run
  on that build alone, and the other builds are refused; detection runs on
  every build that carries it. On the file route the sidecar's
  `[wake_termination]` detection runs between two initializations of the
  solver, the order that marked a blade's root node on a steady point; an
  unsteady run takes the same order, not yet measured there
  ([mesh inputs](mesh-inputs.md#the-boundary-conditions-of-a-raw-mesh)).
- **A workflow row that names no `GEOMETRY` emits no open, and is told
  nothing.** That is what keeps every pre-v0.8.1 matrix rendering as it
  did. A row moved off `LEGACY` that keeps a `FSM_FILE` key of its own is
  refused at plan time naming the key (since 0.13.0), so rename the key
  to `GEOMETRY` when you move it.
- **There is no result-array facade.** No interpolation along a named
  axis, no re-parameterisation, no trim extraction. FR-20 carries that
  promise and is `pending`.

Where a capability above matters to you, the roadmap and the SRS
requirement statuses are where its state is tracked, and the changelog
is where it will be announced.
