# Architecture

The architectural requirements. The live, generated
[architecture overview](../architecture.md) renders the current state
from the module docstrings at every build; this chapter states the
rules that state must obey.

## The layered pipeline

Dependencies flow strictly downward; no module imports upward:

```
post   qa          engineering data | probe and regression evidence
run    workspace   headless execution | input library, run layout, manifest
cases              simulation and campaign definitions
script results     validating script builder | output parsers
commands           the evidence-backed per-version command database
versions           canonical version identifiers and ordering
_atmosphere        the standard atmosphere, importing only the base exception below it
_errors            the package base exception, imported by every layer and importing none
```

The bottom two rows are not pipeline stages. `_errors` defines the
package base exception and the refusals more than one layer names, and
it imports nothing from this package, so every layer above may import it
without a cycle. `_atmosphere` holds the standard atmosphere and imports
only `_errors`; it is a floor for the same reason, that it needs no layer
above it and any of them may import it, and nothing flows THROUGH either.

The claim is stated that way deliberately. An architect pass found an
earlier wording asserting that "several layers need it" while, at the
time, only the exception catalog imported anything from it. Today the
workspace layer's flight-condition resolver imports it as well. What
makes it a floor is the DIRECTION, which is checkable, rather than a
count of consumers, which changes.
They are the floor the stack stands on rather than steps in it, which is
why the arrow chains that state the flow name six rows and this table
names eight.

Side branches follow the same downward-only rule: `fsi` (the
structural side of the aeroelastic loop), `probes` and `farfield`
(survey lattices and conservation ledgers), and the presentation layer
(`reference`, `overview`).

The shared conversion floor also includes `pyflightstream._lengths`: a
unit factor has one home, while each caller separately restricts support
to the units measured for its command or file format. Knowing a scale
does not prove that a solver boundary uses that scale.

Three private support modules are floors of the same kind: they import
nothing from this package, so any layer may import them. `_cli` reports
a console command's outcome on stderr, `_progress` appends each stage's
activity to the workspace logs, and `_fsi_calibration` holds the
dimensionless structural factor names the matrix workflows read without
importing the structural side branch.

## Architectural rules

!!! decision "AD-01 Downward dependencies only"
    A module may import only from layers below its own. Upward
    imports are forbidden, including deferred imports. Historical
    convenience entry points must not be treated as permission to add
    another upward dependency; their boundary must remain explicit,
    and introducing a cycle is a defect.

    An import made only for the type checker counts as an import: it
    never executes, but it records the same upward dependency. Where a
    lower layer reads an object of a higher one, it states the attributes
    it reads as a structural protocol of its own. Every module must also
    import cleanly as the first import of a fresh interpreter, because a
    cycle can be hidden by the order in which a test suite happens to
    import modules.

!!! decision "AD-02 Single rendering sources"
    Anything presented in two places is rendered from one source: the
    command reference and compatibility matrix from the database, the
    architecture overview from the module docstrings, the docs
    example pages from the example scripts. Nothing generated is
    committed.

    One stated exception, and its condition:
    `reports/requirements-index.json` IS generated and committed,
    because its consumer is a dashboard outside this repository that
    cannot run a generator here and reads the file directly. The
    condition that makes it safe is that a Tier 1 test regenerates and
    compares, and a second test sweeps the SRS independently so a
    parser miss cannot pass as a clean regeneration. An exception
    without that pair is the staleness this decision exists to
    prevent.

!!! decision "AD-03 No global mutable state"
    Script construction and every other stateful operation happen on
    objects; two scripts, two campaigns, or two workspaces never
    interfere through module state (PP-2).

!!! decision "AD-04 Explicit inputs, never guessed"
    FlightStream version and executable path are explicit inputs of a
    campaign. Nothing is read from environment variables or guessed
    from the filesystem.

!!! decision "AD-05 Optional heavy dependencies behind extras"
    The core runtime set stays minimal; [NFR-06](nonfunctional-requirements.md)
    is its single home and this decision does not restate it.
    Structural analysis (`[fsi]`), geometry gating (`[geom]`), manual
    reading for the maintainer tool (`[manual]`, licence card
    `reports/RPT-017_manual-extra-license_2026-08-04.md`), and
    plotting (`[plot]`) and workbook creation (`[excel]`, license card
    `reports/RPT-084_excel-extra-license_2026-09-27.md`) are optional extras with license evidence
    recorded before adoption; a missing extra fails with the didactic
    install hint, never an ImportError traceback.

!!! decision "AD-06 One substrate for results (restated 2026-07-27)"
    Tabular results and multidimensional labeled fields rest on one
    substrate ([glossary](index.md#glossary)): the sister library's
    structures over NumPy. pandas and xarray leave the runtime set.

    This decision previously read "tables are pandas; multidimensional
    labeled fields are xarray, and the two never substitute". The
    reference decision of 2026-07-27 does not adapt that reading, it
    invalidates it: the package stops carrying its own table and
    labeled-field stack. The old text is recorded here rather than
    deleted, because a decision that changes content is only readable
    against what it replaced.

    Transition, stated because the code and this decision do not yet
    agree. pandas and xarray are still declared and still imported at
    three sites in `src/` (`results/tables.py`, `farfield/__init__.py`,
    `post/writers.py`, with the test suite as a fourth surface), and
    they stayed through v0.5.0, which shipped without the migration; the removal release number is NFR-06's to state and is unset, that release number
    being stated by [NFR-06](nonfunctional-requirements.md) as its home
    of record. There is no deprecation cycle in between and that is
    deliberate:
    [NFR-20](nonfunctional-requirements.md) governs from 1.0, so a
    consumer finds out on upgrade. The accepted cost is stated in the
    decision record, not softened here.

    Who "a consumer" means is worth naming, because the shorthand for
    this decision has been "the tidy table"
    ([glossary](index.md#glossary)) and that is the smaller half.
    `farfield` carries xarray in the SIGNATURES of its public ledger
    functions, so a rotor or far-field user is affected exactly
    as much as a table user. The changelog notice states both.

!!! decision "AD-07 ITACA as a core dependency (2026-07-23, restated 2026-07-27)"
    pyflightstream and [ITACA](https://github.com/nevesgeovana/itaca)
    are sister libraries by the same author, born integrated: each may
    generate requirements for the other, and each documents awareness
    of the other's architecture (see the
    [sister library page](../sister-itaca.md)). ITACA stays
    solver-agnostic and never imports pyflightstream (its DD-22 and
    DD-23 record the same seam from the other side), so anything
    crossing the seam takes generic arrays and never FlightStream
    probes.

    What changed on 2026-07-27: ITACA was a *future optional* `[itaca]`
    extra and becomes a *core runtime dependency*, because AD-06 now
    rests on it. Two things follow that are easy to get wrong.

    - This is a creation, not a promotion. No `[itaca]` extra has ever
      existed here; the string does not appear in `pyproject.toml`. A
      review pass that asserted otherwise was wrong.
    - The dependency's own metadata propagates to ours: its version pin
      form and its `requires-python` ceiling are governed by
      [NFR-22](nonfunctional-requirements.md), which is their single
      home.

    The direction is not a change of direction. The sister already
    recorded that this driver's pandas and xarray usage migrates to it;
    what changed is the pace and the granularity, from per
    structure to one move.

## Command-line surface

Five console entry points, one per operational concern: `pyfs-qa`
(evidence tiers 2 and 3), `pyfs-workspace` (workspace initialization,
archiving of a recorded simulation, and migration of a flat geometry
library into one folder per geometry),
`pyfs-matrix` (run-matrix upgrade, conversion, pre-flight, run, boundary
inventory, collection of a submitted job's outputs, post-processing, and,
since 0.30.0, the workspace's disk and its other copies: `space-in-use`,
`free-space`, `delete-sims` and `sync`; submission is not a command of its
own, it is what `run` does on Linux with a cluster profile),
`pyfs-fsi` (the coupling-loop executable), and `pyfs-manual`
(reading a vendor manual against the command database, and WRITING
documented version rows back into it from that reading; maintainer
tooling outside the run pipeline). CLIs are thin argument
layers over the public Python API; execution paths always require the
explicit executable. The registration transaction is
`pyflightstream.utils.database`, not the argument parser, for that
reason: it is the second writer into the evidence authority and it owes
the guards the first one has.


## The 0.29.0 architecture and its limits

This section records the 0.29.0 paths and the limit each one keeps. It
does not widen a native measurement to builds it was not taken on.
Historical decisions above retain their dates and stated transition
status. The generated [architecture overview](../architecture.md) reads the
module docstrings through `pyflightstream.overview.markdown_overview()`;
`scripts/gen_docs_pages.py`, configured in `properdocs.yml`, publishes it
at build time. Edit those source docstrings, not a generated page.

### Inputs, geometry and dimensional boundaries

The workspace resolves declarative inputs into the existing case and script
layers. `plan --setup-standards` and `plan --setup-guidelines` write ordinary
complete setup files and `inputs/setups/SETUP_GUIDELINES.md`; they use the
existing setup model and emitter, preserve user files and distinguish physical
recommendations from measured accuracy. Every generated standard states
`farfield_layers = 5`, and the setup model refuses more than five far-field
layers, the documented range of the command; a retired standard keeps its
identifier reserved rather than renumbering the others.

A key that no workflow command applies is refused rather than accepted and
ignored. In 0.29.0 the matrix key `ROTOR_SHEDDING` is refused on every
build, because the relaxed-wake direction it names reaches no line of a
matrix script; the Python component helper still sets it. An unreadable
`COLD_START` value blocks its row at plan and, at run, is recorded as a
failed script for that row.

Boundary inputs have three owners: mesh-sidecar `[ports]` and geometric
TE/wake/base declarations identify the mesh; setup `[[ports]]` and application
selectors choose simulation behavior; MATRIX supplies operating velocities and
profile filenames. Profiles resolve under `inputs/profiles`. False application
selectors skip redefinition without clearing a saved FSM. New port creation
with unknown inherited native indices is refused. See
[boundary conditions](../boundary-conditions.md).

CAD and mesh adapters retain this resolution sequence. CAD conversion extends the raw-mesh import sequence: import CAD,
convert to a mesh, then apply the same boundary and setup operations. The
[CAD route](../cad-inputs.md) is supported within its measured format and
unit limits; an empty or unproved import is not an accepted mesh. OBJ
automatic boundary naming likewise follows measured numbering forms,
including positional duplicate labels, with named refusal for unresolved
forms. It does not replace the explicit sidecar.

Saved FSM length metadata is decoded for measured METER/MILLIMETER heads.
Metre-labelled lengths convert once through the shared `_lengths` floor.
Direct Python reference normalization retains its native-unit default; the
workspace's SI reference inputs declare their units explicitly. A command
may have a different boundary convention from the geometry it samples:
measured unsteady fluid-plot coordinates are SI, while native steady probe
coordinates use the simulation length unit. Export-kind and build evidence
must remain distinct. See [units and starts](../geometry-units-and-starts.md)
and [simulation controls](../simulation-geometry-controls.md).

[Custom inflow](../custom-field-units.md) keeps the supplied physical
orientation. Explicit SI input may produce a separate solver-unit copy,
with both source and effective hashes; undeclared files keep their bytes.
No automatic incidence/vector rotation is implied. Coverage uses the final
emitted placement and a conservative swept envelope for a rotor. Bounds
containment does not certify interior interpolation support; unknown
placement stays unknown, and overcoverage is reported as conservative. A
frame whose motion is unknown refuses the coverage claim rather than being
read as fixed.

### Execution evidence and derived products

A script carries emitted geometry and motion provenance separately from
resolved scientific proof. A consumer may interpret motion timing and
velocity components only when the recorded executable/build and export
kind match measured evidence. Continuation reuses validated predecessor
metadata; it cannot recover an unknown frame by guessing a GUI name.

The placement ledger refuses what it cannot prove. A post-processing
section placed in a frame the run did not create is refused. A turn of zero degrees is
recorded as a turn, so it does not exempt a frame from the refusals that
apply to a rotated frame. An origin given in a unit other than metres,
while the simulation's own unit is unknown, is not converted: the origin
is forgotten and a later translation of that frame is refused. A declared
native volume section that a raw line deleted is refused rather than
exported under another index, and a legacy script that changes its
sections outside an append-only history, including an inline section
delete, is refused rather than reconstructed.

The existing run/manifest and post layers remain the owners of execution
status and collected products. Per-step surface sequences use the existing
action/export route; adding a parallel native-animation subsystem is not
part of this architecture. Surface translation, sampled fields and
boundary-layer products keep their own association, unit and completeness
requirements rather than converting parser success into physical proof.
Sampled volume uses steady probes or unsteady fluid plots and writes a
vertex cloud with actual source, frame and unit evidence. A steady field
that expands a probe profile into volume points refuses a surface row of
that profile rather than sampling it in the flow, and recorded probe
positions are written at round-trip precision so the provenance check
compares the exact coordinates the script emitted. An additional
extraction whose surface translation reports any problem is refused
before it is recorded, and the reopened copy it could be remade from is
kept. Existing native
sections in a saved FSM do not index that grid; manual native/custom APIs
still require the caller to establish those indices. Native nodal strength
joins VTK cell fields only through the recorded auxiliary source and exact
geometry association. Missing data are not reconstructed.

Read-only diagnostics are registered by post through workspace, just like
the existing post stages and input guides. The run CLI calls that lower-layer
entry, preserving downward dependencies. Stage duration, failure context and
post warnings remain in recorded logs even when concise terminal presentation
hides optional warnings. The activity log observes a stage and never
changes its result: a log that cannot be written is reported on stderr,
and the stage's own outcome stands.

See [surface translation](../surface-translation.md),
[sampled fields](../sampled-fields.md), and
[continuation](../continuation-recovery.md).

Workspace FSI inputs resolve calculated or supplied structural properties
and explicit calibration overrides into the existing coupling loop. Fresh
unsteady-rotor mesh cases use the existing nodes, section-family map and
synchronous driver callbacks through `cases.fsi_workspace`. The adapter
refuses unproved saved-state/continuation, units, symmetry or rotor/frame
ordering; staging and callback wiring do not prove coupled physical accuracy. Base
and effective properties have separate provenance; derived quantities
must not be scaled twice. This input route does not itself establish a new
solver-side coupling capability. See [workspace FSI](../fsi-workspace.md).

### Optional workbook adapter

The [Excel route](../excel-matrices.md) creates a macro-free `.xlsx` and
synchronizes saved files through
`python -m pyflightstream.workspace.excel`. It is an optional adapter to
the existing ASCII matrix parser and synchronization engine, not another
case model or a solver dependency. The five installed console scripts
listed above remain unchanged.

All runs share one sheet. Dictionary names, not positions, map fields;
MATRIX/POL identifies a row. Explicit preview/apply/cancel operations retain
custom columns, formulas and untouched workbook parts, reject stale or
ambiguous mappings, and preserve recoverable originals. There is no
automatic synchronization or implicit deletion. Per-file atomic replacement
does not promise an all-files transaction; a partial failure reports what
completed and where originals remain. The earlier embedded-VBA direction
was superseded by the approved macro-free CLI route; macro execution and
Excel trust changes are not requirements of this delivery. The built
distribution excludes macro modules, binary workbook residue and log
files, so a working copy's leftovers cannot ship. An Excel edit to a
column the target matrix's legacy layout lacks is refused with the
migration remedy rather than dropped.

## The 0.30.0 additions and their limits

This section records what 0.30.0 adds to the paths above and the limit each
one keeps. The tracked package holds 134 modules, six more than 0.29.0; none
takes a new row of the layered pipeline, and each imports only at or below
its own row.

### The modules and their rows

- `cases/qsteady.py`, in the cases row, imports only `cases`. It is the
  arithmetic of the quasi-steady rotor: the clocking angles of a wheel, the
  1P reduced frequency and its validity figures, the harmonic content of a
  custom inflow as one blade meets it, and the names of the files a wheel
  point leaves. Both the plan (`cases.workflows`) and the post
  (`post.qsteady`) call it, which is why it lives in `cases`: `post` may
  import `cases` and never the reverse.
- `post/qsteady.py`, in the post row, imports `_errors`, `_tokens`,
  `cases.qsteady`, `post._tables`, `results` and `workspace.inputs`. It
  writes the quasi-steady rotor's positions and average tables and the
  validity of its sections, from the recorded loads exports.
- `fsi/wing.py`, in the `fsi` side branch, imports only `fsi` modules
  (`beam`, `config`, `errors`, `loads`, `nodes`). It is the fixed wing's
  structural solve: one beam clamped at its first station, loaded by the
  aerodynamic sectional loads and by the wing's own weight.
- `workspace/storage.py`, in the workspace row, imports `workspace`,
  `workspace._links` and `workspace.naming`. It owns the four storage
  commands and the record they keep; the command-line layer is a thin
  argument layer over it.
- `workspace/_links.py` holds the directory-link primitives the workspace
  stages and archives with, private to `workspace` and `workspace.storage`,
  and imports nothing from this package.
- `_signature.py` holds the drawings and phrases of the box a console
  command ends with on stderr, rendered by `_cli`; it imports nothing from
  this package, so it is a floor of the same kind as `_cli`.

### The quasi-steady rotor

The `qsteady_rotor` run type solves an isolated, axisymmetric rotor steady,
its blades held still in a free stream that turns about the shaft at the
rotor's speed. It is one workflow of `cases.workflows` beside the others, and
a row states it the way it states any run type. A periodic SECTOR solves one
blade, and is accepted only in an inflow that varies with the radius alone;
a WHEEL solves every blade, and in an inflow that varies around the disc it
is solved at `PASSAGE_POSITIONS` clockings inside one blade passage, which
the post averages. The builder refuses what it can detect is not an isolated
rotor (a second rotor, an actuator disc, a body rate, a boundary that is none
of the rotor's families); whether the blades are alike is not checked. The
validity parameter, the 1P reduced frequency, is computed once in
`cases.qsteady` and read by the plan, the per-point validity file and every
product of the point. The assessor reads a wheel's log solve by solve and
records one verdict per clocking. The wheel's corrections for unsteady
effects are not part of this release.

### The FSI routes

The workflow a row runs decides whether it may couple, and one table in
`cases.fsi_workspace` states it for every workflow. A fixed wing couples on
`steady` and on `unsteady` without rotor motion; the rotating blade of a
`qsteady_rotor` sector couples at the row's speed; a `qsteady_rotor` wheel is
refused by its builder, because several clockings averaged are not the state
of one structure, and `unsteady_rotor` by the plan, because on the measured
build the morph of a mapped rotating blade replaces its rotation. The
structural executable stays the side branch it was: `fsi` imports only the
floors, `extras` and `results`, so it sits between the script/results row
and the cases row, which reach it downward. A steady
coupled script ends at its aeroelastic analysis, which returns at once, so
the run waits for the solver's own completion line and nothing may follow
the analysis in the script. On 26.124 the fixed-wing route converged and
mapped 1052 of 1052 vertices (reports/RPT-092); its XZ moment column agrees
in sign at the integral (+7.49 against +17.13 N m) and not in magnitude
(44 %), so that sign is not confirmed in magnitude.

### Storage and sync

The four storage commands act on the workspace's own folders and records.
Every call
previews by default, changes files only when applied, and is recorded in
`storage_management.json` at the workspace root. A synced simulation's
inputs are a link into the main workspace's geometry library, and a
removal undoes every link first, so the mesh it points at survives. A
pruning of per-step exports keeps each point's last step; a later post that
needs a pruned step refuses the product by name rather than writing it from
the steps that remain.
