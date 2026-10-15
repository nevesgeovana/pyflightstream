# Architecture

This is the current architecture core. It describes dependency boundaries,
the execution paths and the owners of persistent state. The public architecture
page is generated from this chapter; Contributing links to its architectural
decisions section. This source chapter is not published as a second page.
API signatures and command options come
from their generated references; historical release measurements remain in Git.

## The layered pipeline

Dependencies flow strictly downward; no module imports upward:

```
post   qa          engineering data | probe and regression evidence
run                headless execution
workspace          input library, run layout, manifest
cases              simulation and campaign definitions
script results     validating script builder | output parsers
commands           the evidence-backed per-version command database
versions           canonical version identifiers and ordering
_atmosphere        the standard atmosphere, importing only the base exception below it
_errors            the package base exception, imported by every layer and importing none
```

This is the dependency rule, not a claim that the implementation has no recorded
exceptions. Module-level, deferred and type-checking imports all count. The
layer guards rank every root unit and retain the package-root initialization
cycle as an explicit exception. Existing cross-package private imports have a
separate shrink-only baseline; that baseline does not permit new such imports.

Side branches follow the same downward-only rule: `fsi`, `probes`, `farfield`,
`reference`, `overview`, `utils`, `options`, `exceptions`, `extras` and `testing`.

The core rows are declared by `pyflightstream.overview._CORE_LAYERS`.
`tests/tier1_offline/test_conventions.py` supplies the complete root-unit ranks
used by both layer checks. Lower numeric ranks mean higher layers:

| Rank | Units outside the core rows |
|---|---|
| 0 | `exceptions`, which assembles the exception catalog |
| 3.25 | `farfield` |
| 3.5 | `fsi`, `probes`, `support` |
| 4.5 | `utils`, `reference` |
| 6.25 | `_cli` |
| 6.5 | `_deprecations`, `_progress`, `overview` |
| 7 | `_errors`, `_atmosphere`, `_expressions`, `_lengths`, `_textio`, `_tokens`, `_console`, `_decimal`, `_digest`, `_fsi_calibration`, `_fsm`, `_fsm_fresh`, `_maturity`, `_mesh`, `_retired_names`, `_signature`, `_yamlflow`, `extras`, `options`, `testing` |

Floor modules provide shared primitives; they are not stages through which a
campaign flows. `_cli` and `_progress` have their own ranks because their
imports place them above those primitives. A module's underscore prefix alone
does not make it a floor. The package `__init__` initializes registrations and
is the named unranked root exception.

## Architectural decisions

The AD identifiers remain stable. The statements below describe current
boundaries; they do not repeat the chronology of each extraction.

!!! decision "AD-01 Downward dependencies only"
    Imports follow the ranks above, including deferred and annotation-only
    imports. Lower layers use their own structural protocols when they need
    attributes of a higher-layer object. Existing exceptions are guarded;
    a convenience facade is not permission to introduce another cycle.

!!! decision "AD-02 Single rendering sources"
    Database references come from command data, API pages from docstrings and
    CLI pages from parsers. The architecture page renders this core. Requirement
    indexes are generated from the requirement source and checked for drift.

!!! decision "AD-03 State has an explicit owner"
    Each Script and campaign owns its working state. Options are process-wide
    configuration, and import-time registries connect workflow builders, post
    stages, diagnostics, input guides and rebuild handlers. These registries
    are extension seams, not independent copies of a workspace's run state.

!!! decision "AD-04 Explicit execution inputs"
    Solver identity and executable selection come from explicit arguments or
    workspace configuration, including the executable registry. The solver
    subprocess inherits its ambient environment for licensing and installation.
    Storage provenance may read USERNAME or USER; that does not select a solver.

!!! decision "AD-05 Optional heavy dependencies behind extras"
    Structural analysis, spatial geometry queries, plotting, workbook creation
    and manual reading use their declared extras. A missing extra produces an
    installation remedy at the operation that needs it. Runtime dependencies
    and version bounds have their authoritative list in pyproject.toml.

!!! decision "AD-06 Numerical and table substrates"
    Numerical arrays use NumPy. The far-field core has no xarray dependency.
    pandas remains a runtime dependency for current table paths; its removal
    is future work, not a property of this release.

!!! decision "AD-07 External numerical integration"
    Numerical integration crosses a solver-independent array boundary.
    Available runtime dependencies and extras are declared in pyproject.toml.

!!! decision "AD-08 Structural guards"
    Layering, import cycles, optional-dependency isolation, facade size and
    private-import coupling are checked against their current guard inputs.
    Structural refactors do not raise shrink-only baselines to hide growth.
    A source layout change preserves behavior unless a requirement changes it.

!!! decision "AD-09 Run above workspace"
    Run orchestrates execution and imports workspace services. Workspace owns
    layout and storage and does not import run to invoke execution. Registered
    callbacks connect the layers where workspace needs a higher-layer service.

!!! decision "AD-10 Shared operations have one home"
    Shared numerical conventions, parsing and rendering helpers live below
    their callers. Public facades preserve supported paths; callers do not
    duplicate a helper or reach through another package's private module.

!!! decision "AD-11 Public modules expose their domain services"
    Workspace sidecars, build lookup, HPC profiles and selections have public
    domain modules. Results parsing has core, loads, log and exports modules.
    Run records exposes recovery operations over workspace-owned storage.

!!! decision "AD-12 Workflow builders share one registry"
    cases.workflows is a facade over builders and their ordered helpers. The
    registry selects builders, the vocabulary owns row keys, and each helper
    owns one emission concern. A new route reuses the script builder and its
    command validation rather than constructing a second command language.

!!! decision "AD-13 Product families share a resolved context"
    Post resolves input records into a context, then calls the polar, rotor,
    unsteady and point-product families. Common table readers live below those
    families. A product failure is reported at its declared scope; a missing
    quantity is not invented to keep a table numeric.

!!! decision "AD-14 Run orchestration has private phases"
    Campaign, point, sweep, plan, assessment, identity and executor modules
    implement the public run facade. The CLI parses and dispatches; it does
    not supply a second implementation of these operations.

!!! decision "AD-15 Observable changes are named"
    Parity compares public paths and signatures, CLI arguments, emitted scripts
    and product bytes. Intended differences name their requirement and exact
    allowed shape; unrelated differences fail. Incidental bindings in private
    modules are not public API. Current migration policy is in upgrading.md.

!!! decision "AD-16 Case models have domain homes"
    Settings, mesh declarations, reference blocks, naming, selection and pproc
    models have their own modules below the cases facade. Public re-exports
    preserve the supported import paths and model identity.

!!! decision "AD-17 Solver settings emit by family"
    script.helpers.solver_settings delegates to the settings emitters. Argument
    validation precedes emission; build-specific command refusals still belong
    to Script.emit. Units and command order remain part of the public contract.

!!! decision "AD-18 CLI parsers are organized by operation"
    Parser families register subcommands and handlers. The generated CLI
    reference reads those parsers, so this chapter does not copy option lists.

!!! decision "AD-19 Workspace owns record models and registries"
    workspace.manifest owns RunRecord and manifest mutation primitives.
    workspace.record_document owns the serialized document and resolution of
    shared definitions. The workspace facade keeps public re-exports and
    registration seams. These are distinct from execution orchestration.

!!! decision "AD-20 Matrix binding is phased"
    workspace.matrix.resolve_matrix orchestrates the binding context and phases
    in _matrix_binding and _matrix_phases. Parsing, artifact resolution and
    build selection occur before the run layer submits work.

!!! decision "AD-21 Matrix parsing and workspace migration are separate"
    cases._matrix_layouts defines the supported matrix layout. Ordinary readers
    refuse obsolete layouts and keys. workspace.migrate is the explicit
    workspace conversion route; no retired matrix-upgrade module is required.

!!! decision "AD-22 Run phases share execution state"
    Campaign, point, sweep and assessment helpers share explicit context objects
    within run. Splitting a function does not change verdict severity, resume
    selection, output admission or the order of record transitions.

!!! decision "AD-23 Post phases share product state"
    Admission, reduction, rotor and campaign product helpers operate on resolved
    records and one product context. Moving a helper does not change scientific
    formulas, output ordering or the interpretation of recorded evidence.

!!! decision "AD-24 Every root unit is ranked"
    Root-unit coverage and private cross-package imports are checked, including
    imports inside functions and TYPE_CHECKING blocks. A newly introduced root
    unit needs a rank; existing private-import exceptions may only shrink.

## Run paths and state ownership

The matrix is the campaign declaration route. cases parses its rows and models;
workspace resolves inputs, geometry, settings and build identity; run plans and
executes; results parses exports; post derives engineering products. Ordinary
Python APIs remain available. The retired authored-Python campaign-file route
is not an alternative declaration format.

Planning validates without launching a solver. Per-point, polar-sweep and batch
execution use the same workflow builders. A grouped job records each point's
outcome and submission association; collect resolves the job outputs into those
point records. Resume uses effective recorded outcomes, not folder existence
alone. A failed or missing output is not convergence.

| State | Owning service | Persistence contract |
|---|---|---|
| Command evidence | commands | Version rows and cited manual/probe evidence |
| Resolved case | workspace.matrix | Explicit inputs and selected build |
| Plan | run._plan | Plan receipt and rendered scripts, without submission |
| Run document | workspace.record_document | schema_version 4; run headers and immutable shared definitions |
| Run transitions | workspace.manifest and run callers | Under the writer lease, one manifest replacement per transition |
| Product inventory | post | Derived files, source provenance and per-product outcomes |
| Storage actions | workspace.storage | Preview/apply operations and storage_management.json |
| Query snapshot | workspace.ledger | Read-only resolved evidence, without modifying the workspace |

Run documents store shared solver setups, frames and geometry once, by content
identity. Readers resolve historical definitions from the document, not today's
input files. Requested values, observed values, provenance and distinct times
retain their separate meanings. An in-memory RunRecord is a resolved view;
serializing that view directly is not the on-disk schema. Ordinary readers
refuse older documents; the explicit migration route is described in
[upgrading](../upgrading.md).

The manifest is mutable under controlled operations: collect completes submitted
records, marks change verdicts, sync merges evidence, and storage may record a
deletion. New-run append rejects duplicate identities, but the document as a
whole is not append-only. Restore recovers an archived file; rebuild reconstructs
evidence from simulation folders and checks it against rendered scripts. Rebuild
may parse sim_<id> folder names as recovery candidates; it does not treat a name
alone as proof of the executed inputs or outcome.

## Scientific and geometric seams

Definitions of reductions, windows, frames and products live in
[post-processing definitions](../post-processing-definitions.md) and the
[far-field definition](../definitions/the-far-field-family.md).
Implementation notes cannot override those definitions.

The farfield package is a NumPy numerical core. Post adapts solver units, signs
and frames before passing arrays to it. Probe layouts belong to probes;
geometry gating checks proposed sample positions against the declared body.
The balance and Trefftz methods share quadrature. Parsing a file successfully
does not establish a native convention or validate a physical model.

Geometry instruction models belong to cases; workspace plans, audits and stores
geometry builds; run supplies the executor. The geometry command group registers
with workspace.cli, preserving the dependency direction. Grid refinement and
audit run without the spatial-query extras; remeshing uses its declared extras.
Native geometry commands remain gated by their build evidence.

FSI owns structural solves and the coupling-program interface. Workspace binds
structural inputs, and cases chooses the supported coupling route. A staged
program or a rendered coupling script is not evidence of coupled accuracy.
Unsupported build, frame, symmetry or motion combinations must retain their
named refusals.

ROTOR_SHEDDING is refused on the matrix route. CCS_SHEDDING controls the
component-file shedding digit on the CCS file-import route; it is not a general
rotor wake-direction switch. A measured change in a saved state does not by
itself establish the physical meaning of that digit.

## Console and optional adapters

The installed tools divide responsibilities: pyfs-matrix plans, runs, collects,
queries and post-processes matrices; pyfs-workspace manages inputs and workspace
geometry; pyfs-fsi runs structural coupling; pyfs-qa runs validity and regression
work; pyfs-manual inspects manual/database correspondence. See the generated
[command-line reference](../cli/index.md) for the complete parsers.

The macro-free Excel adapter, invoked as
`python -m pyflightstream.workspace.excel`, reads and writes saved workbooks.
It maps columns by dictionary names and rows by MATRIX/POL. Preview, apply and
cancel preserve recoverable originals. Per-file atomic replacement does not
promise a transaction across every file; partial completion must be reported.

Console status, progress and logs observe the operation's outcome. A logging
failure is reported without replacing the underlying result. Expected refusals
name their cause and remedy; validation and failure reporting remain bounded
contracts, not a guarantee that all conceivable failures are impossible.
