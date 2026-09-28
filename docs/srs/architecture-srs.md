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

## Architectural rules

!!! decision "AD-01 Downward dependencies only"
    A module may import only from layers below its own. Upward
    imports are forbidden, including deferred imports. Historical
    convenience entry points must not be treated as permission to add
    another upward dependency; their boundary must remain explicit,
    and introducing a cycle is a defect.

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
inventory, collection of a submitted job's outputs, and post-processing;
submission is not a command of its own, it is what `run` does on Linux with a
cluster profile),
`pyfs-fsi` (the coupling-loop executable), and `pyfs-manual`
(reading a vendor manual against the command database, and WRITING
documented version rows back into it from that reading; maintainer
tooling outside the run pipeline). CLIs are thin argument
layers over the public Python API; execution paths always require the
explicit executable. The registration transaction is
`pyflightstream.utils.database`, not the argument parser, for that
reason: it is the second writer into the evidence authority and it owes
the guards the first one has.


## Implemented 0.29 architecture and its limits

This section records the implemented 0.29 paths. It does not declare an
unreleased working tree accepted or widen a native measurement to other
builds. Historical decisions above retain their dates and stated transition
status. The generated [architecture overview](../architecture.md) reads the
module docstrings through `pyflightstream.overview.markdown_overview()`;
`scripts/gen_docs_pages.py`, configured in `properdocs.yml`, publishes it
at build time. Edit those source docstrings, not a generated page.

### Inputs, geometry and dimensional boundaries

The workspace resolves declarative inputs into the existing case and script
layers. `plan --setup-standards` and `plan --setup-guidelines` write ordinary
complete setup files and `inputs/setups/SETUP_GUIDELINES.md`; they use the
existing setup model and emitter, preserve user files and distinguish physical
recommendations from measured accuracy.

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
placement stays unknown, and overcoverage is reported as conservative.

### Execution evidence and derived products

A script carries emitted geometry and motion provenance separately from
resolved scientific proof. A consumer may interpret motion timing and
velocity components only when the recorded executable/build and export
kind match measured evidence. Continuation reuses validated predecessor
metadata; it cannot recover an unknown frame by guessing a GUI name.

The existing run/manifest and post layers remain the owners of execution
status and collected products. Per-step surface sequences use the existing
action/export route; adding a parallel native-animation subsystem is not
part of this architecture. Surface translation, sampled fields and
boundary-layer products keep their own association, unit and completeness
requirements rather than converting parser success into physical proof.
Sampled volume uses steady probes or unsteady fluid plots and writes a
vertex cloud with actual source, frame and unit evidence. Existing native
sections in a saved FSM do not index that grid; manual native/custom APIs
still require the caller to establish those indices. Native nodal strength
joins VTK cell fields only through the recorded auxiliary source and exact
geometry association. Missing data are not reconstructed.

Read-only diagnostics are registered by post through workspace, just like
the existing post stages and input guides. The run CLI calls that lower-layer
entry, preserving downward dependencies. Stage duration, failure context and
post warnings remain in recorded logs even when concise terminal presentation
hides optional warnings.

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
Excel trust changes are not requirements of this delivery.
