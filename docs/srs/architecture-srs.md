# Architecture

The architectural requirements. The live, generated
[architecture overview](../architecture.md) renders the current state
from the module docstrings at every build; this chapter states the
rules that state must obey.

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
why the arrow chains that state the flow name seven rows and this table
names nine.

Side branches follow the same downward-only rule: `fsi` (the
structural side of the aeroelastic loop), `probes` and `farfield`
(survey lattices and conservation ledgers), and the presentation layer
(`reference`, `overview`).

The shared conversion floor also includes `pyflightstream._lengths`: a
unit factor has one home, while each caller separately restricts support
to the units measured for its command or file format. Knowing a scale
does not prove that a solver boundary uses that scale.

Five private support modules are floors of the same kind: they import
nothing from the pipeline rows, only `_errors` and one another, so any
layer may import them. `_cli` reports a console command's outcome on
stderr; `_console` lays out a command's console output (its titled
blocks, wrapped lines and held warnings); `_progress` appends each
stage's activity to the workspace logs, draws the stage progress of the
long commands and writes their live log; `_signature` holds the drawings
and phrases of the box a command ends with, which `_cli` renders; and
`_fsi_calibration` holds the dimensionless structural factor names the
matrix workflows read without importing the structural side branch.

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
    example pages from the example scripts, and from 0.33.0 (NFR-29)
    the Python API reference from the docstrings, the command-line
    reference from the argument parsers and the exceptions catalog
    from the exception classes. Nothing generated is committed.

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

### The 0.33.0 architecture decisions

The decisions below are the architecture half of the 0.33.0 scope (scope
record GEO-071, section 3, and the architecture review GEO-072, whose
review lens binds every one of them). Each is pending until the work
package named in its first line lands, and each names the evidence that
package owes. None changes what the package does: AD-15 states what every
one of them keeps.

!!! decision "AD-08 The architecture guards <span class='srs-pending'>pending</span>"
    *Work package WP0 of the 0.33.0 scope, which lands before any other
    package so that every later one is measured. Evidence owed: the
    tier-1 tests of G1 to G8 below, each with its non-vacuity condition,
    `scripts/arch_metrics.py`, and the architecture metrics report under
    `reports/`.*

    The concentration measured on v0.32.0 (13 modules holding 47.7
    percent of 146,463 lines, 17 modules over 2,000 lines) does not come
    back, because each rule below is a tier-1 test whose baseline is the
    number measured at the freeze with the test's own reader and may only
    shrink. No allowlist grows. A guard that reads nothing, or that its
    own mutant does not turn red, is itself a failure.

    - G1 Module size, in the unit of the review lens: CODE lines, the
      lines that are not blank, not comment-only and not inside a
      docstring, counted with `ast`. Up to 1000 code lines a module needs
      nothing. From 1000 to 2000 its module docstring carries a line
      beginning `Size exemption:` that states, on that line, why (a
      catalog of items of one shape, or one deep abstraction); mixed
      logic has no exemption. Above 2000 a module is refused. Every
      module above 1000 code lines at the freeze is in the baseline table
      of today's counts, whatever its docstring says; an entry may not
      grow, is lowered when its module shrinks, and is deleted when the
      module falls to 1000 or under.
      The 1000 and 2000 are conventions (pylint's default applied to code
      lines, and twice it), not a law. Non-vacuity: the walk reads at
      least the module count of the G7 record and the code lines it
      totals agree with that record; one more line in a listed module,
      an unlisted module of 1001 code lines without the exemption line,
      and a deleted row of a module still over the ceiling are each red.
    - Deep modules. A module created in 0.33.0 hides substantial
      function behind a narrow interface: about 150 code lines or more,
      never a one-function file, never siblings that all import one
      another. A new module that is not a package root is refused below
      two top-level definitions or 60 code lines (the hard floor); between
      60 and 150 code lines it is a review check, and the G7 record lists
      every module created since v0.32.0 under 150 code lines so the
      reviewer reads the list rather than finds it.
    - G2 Function limits. A new or changed function stays within the
      defaults of ruff and pylint (complexity 10, branches 12, statements
      50, positional arguments 5); every function over them today is in
      a baseline that may only shrink, compared as "at most the recorded
      value". Non-vacuity: a function at the limit passes and one over
      it is red.
    - G3 Import graph. (a) A strongly connected component of the module
      graph, module-level and deferred imports together, that spans two
      top-level packages is refused unless it is in the frozen baseline;
      a baseline component may not gain a member and is deleted when it
      no longer exists; at the freeze the components found equal the
      baseline exactly, both ways, so an empty graph cannot pass. (b)
      Inside a package that declares an order (`pyflightstream.cases.workflows`,
      AD-12, and `pyflightstream.run`, AD-14), a module imports only
      modules after it in the order, at module level and deferred alike,
      and a module missing from the order fails.
    - G4 Fan-out. A module imports at most 25 distinct modules of the
      package at module level, and at most 25 in deferred imports,
      counted separately; today's excess (`post/products.py`, 32 at
      module level, and any deferred excess measured at the freeze) is a
      baseline that may only shrink. Non-vacuity: a synthetic module of
      26 imports is red.
    - G5 Private-name test coupling. The pairs (source module, private
      name) that tests reference, and the monkeypatch targets on source
      modules, are counted per source module; a count may not rise. A
      facade that re-exports a private name for tests during the cycle
      is still counted (AD-15), so the count falls only as tests are
      retargeted. Non-vacuity: a test referencing a new private name is
      red, and the totals are re-measured at the freeze with the same
      reader rather than copied from the review.
    - G6 One home per literal. Every top-level `NAME = <literal>` of the
      package (a string, a number, a tuple of literals) is grouped by the
      pair (name, value); two modules defining the same pair where
      neither imports it from the other fail, naming both files and
      lines. The allowlist is empty (AD-10). The same value under two
      different names is out of this guard's scope. Non-vacuity: the
      nine pairs measured on v0.32.0 are kept inside the test as
      synthetic sources that must always be red, beside a clean control.
    - G7 The architecture metrics record. `scripts/arch_metrics.py`
      writes a report under `reports/` stating the module count, the
      total and the code lines, the shares of the largest 1, 5 and 13
      modules, the modules over 1000 and 2000 code lines, the functions
      over the limits of G2, the cross-package components, the largest
      fan-out, the private-name coupling and the non-import lines of
      each package root. A tier-1 test re-measures the tree and compares
      it with the report and with a committed table of the same numbers
      that may only improve, so regenerating the report in the same
      commit cannot hide growth.
    - G8 Roots are facades. A package `__init__.py` holds only its
      docstring, imports, its `__all__` and at most a lazy `__getattr__`
      loader, counted with `ast` as the statements that are none of
      these; no root uses a star import. The roots that hold more today
      are a baseline that may only shrink, and a root absent from it
      holds none. Non-vacuity: a function defined in a facade root is
      red.

    The guards run in the existing `test` job of continuous integration;
    they are tier-1 tests.

!!! decision "AD-09 The row order: run above workspace <span class='srs-pending'>pending</span>"
    *Work package WP1 of the 0.33.0 scope (decision 4 of the scope).
    Evidence owed: the layer guards of NFR-23 reading the new table, the
    test that holds this chapter's table, the user-guide diagram and the
    generated overview to the module data, and a count of zero
    `workspace` to `run` imports.*

    The layered pipeline has seven rows, from the top: `post` and `qa`;
    `run` alone; `workspace` alone; `cases`; `script` and `results`;
    `commands`; `versions`; with the two floors `_atmosphere` and
    `_errors` below them. No module of `workspace` imports a module of
    `run`, at module level, inside a function body or under
    `TYPE_CHECKING`. The two imports that go the other way on v0.32.0
    are removed: the lookup of which records file a `--runs` name means
    moves down into `workspace`, beside the matrix lookup, and the
    rebuild of orphaned records that the sync reached for is inverted:
    `run.records` registers it with `workspace.storage` when it loads
    (the package root loads it, as it loads the post that registers its
    stages), and the sync calls whatever is registered after it released
    the `runs.json` lease, the order RST-6 states. The registry holds
    exactly one rebuild: the first registered is held, a rebuild of the
    same module replaces it (a reload of `run.records`), one of another
    module is not taken, and with nothing registered the restore block of
    the sync names that in its `error` while the files it copied stand.
    The library keeps its
    0.32.0 contract (FR-221: `restore=True` rebuilds), which a rebuild
    asked only by the command line would have broken. This chapter's
    table, the user-guide diagram, the layer table of
    `pyflightstream.overview` and the guards state the same rows, and
    the interim count of `workspace` to `run` imports of guard G3 is 0.

!!! decision "AD-10 One home per constant, and the loads cycle removed <span class='srs-pending'>pending</span>"
    *Work package WP2 of the 0.33.0 scope (decision 15). Evidence owed:
    G6 green with an empty allowlist, and G3 finding no component that
    holds `fsi.loads` and `results.tables`.*

    Each of the nine constants that v0.32.0 defines twice has one
    defining module, and every other module imports it from there:
    `ARCHIVE_DIR` and `ARCHIVE_STAMP` (from `workspace.naming`, the run
    records reading their pattern, `ARCHIVE_STAMP_PATTERN`, from the same
    home), `FLAG_PHASES` (from `cases`), the unit that names no length
    (`UNIT_THAT_NAMES_NO_LENGTH`, from the floor `_lengths`, for
    `cases.ccs_wing` and the workflows), the section command
    `SECTION_DISTRIBUTION_COMMAND` (from `cases.workflows`, for
    `post.superfile`), the stabilization command
    `WAKE_STABILIZATION_COMMAND` (from `script.helpers`, for
    `cases.setup_surfaces`), the length-unit command `LENGTH_UNIT_COMMAND`
    (from `script`, for `script.helpers` and `workspace.wake_edges`, whose
    public copy the guard found once the private pair had gone; the shared
    names are public, so no module imports a private name of a sibling),
    `VELOCITY_KEYS` (from
    `cases.matrix`, for `workspace.flight_condition`) and `ACOUSTICS_DIR`
    (from `cases.acoustics`, for `post.acoustics`). Two more pairs the
    guard measured, the loads export and the displacement file of the
    coupling, have their home in `fsi.state`, the import-light module the
    staging builder already reads. The duplicated module `__getattr__` of
    `post` and `post.products` is one helper in `_deprecations`
    (`removed_names_hook`). The private helpers no caller reaches
    (`_passages`, `_output`, `_cell_value`) are deleted after a search of
    the repository and the estate's tracked scripts, and so is
    `stamp_derived_campaign` (decision 9), whose marker the campaign
    loader still reads. `parse_sectional_loads`, its report and
    `UnitsError` are defined in `results.sectional_loads` and `fsi.loads`
    re-exports them, which removes the cycle between `fsi.loads` and
    `results.tables`; the coupling's refusal `FsiInputError`, which the
    parser raises too, is defined in the floor `_errors` because two
    layers name it, and `fsi.errors` re-exports it.

!!! decision "AD-11 The four cheap extractions <span class='srs-pending'>pending</span>"
    *Work package WP3 of the 0.33.0 scope. Evidence owed: G1 and G8
    entries lowered for each module named here, every public import path
    kept (AD-15), and the tests of this chapter's module lists updated
    with them.*

    Four modules are cut along the clusters the review measured, each
    public path kept by a facade and each new module within the lens:
    `post.guides` (the input template and the glossary each move to a
    module of their own, the guides of the post stay); `run.records` (the
    rebuild and the assembly move to private modules, the manifests, the
    locks, the restore and `mark_failed` stay); the `results` root (its
    parsers move to modules of their own, the errors, primitives and codes
    stay, and the root becomes a facade, which removes the only
    module-level import cycle measured on v0.32.0); and `workspace.inputs` (the
    sidecars and the HPC profile move to modules of their own, and
    `workspace.inputs` gains an `__all__`). The names of the new modules
    are the review's; a package that changes one records it in the 0.33.0
    section of this chapter.

    As WP3 landed: `post.glossary` holds the input glossary and the parts
    the three generated pages share (the names of the pproc guides, the
    banner, the idempotent write, the documentation link), so that
    `post.input_template`, whose sections are one data table, and
    `post.guides`, which keeps the pproc guides, import it and it imports
    neither. The `results` root is a facade of imports and `__all__`: its
    errors, primitives and codes stay in its public face and are defined
    in `results.core`, below `results.loads`, `results.log` and
    `results.exports`, because a root that defined them would be imported
    by its own leaves, which is the cycle; no module of the layer imports
    the root. `run.records` keeps `restore` and `mark_failed` and every
    public name of the family; the rebuild is `run._rebuild`, what it reads
    and compares `run._rebuild_evidence` (the rebuild alone is over the
    lens), the assembly `run._assemble`, and the record files, their
    archives, the lease and `RecordsError` are `run._record_files`, which
    `records` and the rebuild share so that neither imports the other.
    `workspace.inputs` keeps the artifact resolvers and an `__all__` of
    every public name it held; besides `workspace.sidecars` and
    `workspace.hpc`, the build registry is `workspace.builds` and the rule
    on empty entity selections `workspace.selections`, because the review's
    two cuts left it over the lens once its `__all__` was written. The five
    modules beyond the review's names are `results.core`,
    `run._record_files`, `run._rebuild_evidence`, `workspace.builds` and
    `workspace.selections`.

!!! decision "AD-12 cases/workflows is a package with a guarded order <span class='srs-pending'>pending</span>"
    *Work package WP4 of the 0.33.0 scope. Evidence owed: G3(b) for the
    package, the 29 goldens and the tier-3 golden diff unchanged, and G1
    for every module of the package.*

    `pyflightstream.cases.workflows` becomes a package cut along the
    measured clusters (the vocabulary, the conventions, the row readers,
    the names, the geometry, the frames, the settings, the free stream,
    the actuator, the reductions, the exports, the post-processing
    emission, the script skeleton, and the builders of each run type).
    Its `__init__` is a facade that keeps every public name, `__all__` in
    content and order, and the objects whose order feeds a generated
    page or the command line (`WORKFLOWS`, `ROW_KEY_MEANINGS`) move as
    objects, never rebuilt. Its modules import one another only in the
    declared order of G3(b), module-level and deferred imports alike.

!!! decision "AD-13 The post families are sibling modules <span class='srs-pending'>pending</span>"
    *Work package WP5 of the 0.33.0 scope (decisions 5, 8 and 15).
    Evidence owed: the byte snapshot of the products, taken before the
    first move and compared after every move, and the surface test of
    `post.products` extended to each public family module.*

    The product families of `post/products.py` become sibling modules
    under `post/` (the polar, the rotor table, the unsteady polar, the
    point tables, the rotor products, and a private module for the point
    condition), each public one with an exact `__all__`. `post/products.py`
    stays a module and a facade: every name of its `__all__` and every
    import path is kept. `read_csv_table` and the readers of the plots
    table move to `post/_tables`, which removes the sibling cycle between
    `post.products` and `post.corrections`. `_sim_products` is decomposed
    over one frozen `SimContext` that its first part resolves, with the
    product families called in the order the manifest has today; the
    proof is a byte snapshot of `products.json`, `post.log`,
    `post.log.json` and every CSV of the recorded campaigns, stamps
    normalized, taken from the tree of v0.32.0 before the first move and
    compared after each. `run_campaign`, `_execute_point` and
    `_execute_sweep` are not decomposed in 0.33.0; `PointState` stays
    until this package decides whether the two classes of that name
    converge.

!!! decision "AD-14 run is a facade over private modules and leaves the type-check exemptions <span class='srs-pending'>pending</span>"
    *Work package WP6 of the 0.33.0 scope (decision 7). Evidence owed:
    G8 for `run/__init__.py`, G3(b) for the package, and the type-check
    exemption list one module shorter in `pyproject.toml` and in the
    recount records of NFR-27.*

    `pyflightstream.run` becomes a facade over private modules (the
    executors, the assessment, the solver identity, the plan, the
    campaign, the points, the continuation and the surface-mesh export),
    keeping its `__all__` in content and order and every import path,
    and its private modules import one another only in the declared
    order of G3(b). `pyflightstream.run` leaves the list of modules the
    static type checker exempts, so the list shrinks by one; every line
    moved is typed, and a construct that resists is narrowed with a
    stated reason rather than given a new exemption. `run.matrix`,
    `run.collect`, `run.records` and `run.cli` keep importing from
    `pyflightstream.run`.

!!! decision "AD-15 The evolution policy of 0.33.0 <span class='srs-pending'>pending</span>"
    *All work packages of the 0.33.0 scope and its integration recount
    (WPX; decisions 6, 9 and 15). Evidence owed: the parity receipt of
    the release, produced by a committed script comparing tag `v0.32.0`
    with the release commit, and the recount records.*

    0.33.0 does everything 0.32.0 does. The rules that keep it so, while
    [NFR-20](nonfunctional-requirements.md) does not yet bind:

    - Every name in every `__all__` of v0.32.0 imports from the same
      dotted path in 0.33.0, and each `__all__` keeps its content and its
      order. The one exception is `stamp_derived_campaign`, removed with
      a CHANGELOG Removed entry by decision 9 of the scope.
    - During the cycle a facade may re-export a private name that tests
      use, counted by G5; every test is retargeted before the tag, so at
      the 0.33.0 tag no test reaches a private name through a facade.
    - Compared against tag `v0.32.0`, and excepting only what a named
      requirement changes (FR-314 for the emitted scripts of the unsteady
      rows without per-step export): the public API names and their
      signatures accept every call they accepted; every console tool,
      subcommand and option is still accepted; the emitted scripts of
      the golden and tier-3 campaign set are byte-identical; and the
      product bytes and `products.json` of a post over a recorded
      workspace are identical, stamps normalized. The baseline of each
      comparison is produced from the tree of that tag, never from the
      branch, and each comparison states its counts so an empty one
      cannot pass.
    - One recount per work package and one integration recount after the
      merges: the module count, the type-check exemption list, the
      metrics record of G7, the change log and this chapter's section of
      0.33.0, which the integration writes.

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

## The 0.31.0 additions and their limits

This section records what 0.31.0 adds to the paths above and the limit each
one keeps. The tracked package holds 138 modules, four more than 0.30.0; none
takes a new row of the layered pipeline, and each imports only at or below
its own row (a sibling of its own subpackage included).

### The modules and their rows

- `cases/corrections.py`, in the cases row, imports only the floors
  (`_digest`, `_errors`). It is the quasi-steady wheel's correction routes as
  a pproc names them (`[qsteady_correction]`) and the reader of a calibration
  file of `inputs/calibrations/`, refused whole naming the line
  (`CalibrationError`). The plan (`workspace.matrix`) and the post
  (`post.corrections`) both read it, which is why it lives in `cases`.
- `post/harmonics.py`, in the post row, imports `_errors`, `_tokens`,
  `post._tables`, `post.axes` and `post.qsteady`. It fits each blade station's
  0P, 1P and 2P load around the disc from a WRITTEN sections table, a wheel's
  over its blades and clockings and an unsteady rotor's over its last complete
  revolution.
- `post/corrections.py`, in the post row, imports `_errors`, `_tokens`,
  `cases.corrections`, `post._tables`, `post.harmonics` and `post.qsteady`,
  and, inside one function, `workspace` (a recorded point for a route 2
  calibration), below its row. Until 0.33.0 it also reached `post.products`
  inside a function for its table reader; the reader is in `post._tables`
  since then (AD-10), so the two modules no longer import each other. It is the one applicator of the correction routes: every corrected
  product is a new file beside its raw one, never written over it, and none is
  validated. The Theodorsen and Sears functions are a diagnostic only.
- `workspace/fields.py`, in the workspace row, imports `_digest`, `cases`,
  `cases.freestream`, `cases.workflows` and `workspace`. It builds a custom
  free-stream file of `inputs/freestreams/` from other fields (mirror, move,
  subtract, time mean), previewing until applied, with a provenance record
  beside each result; the command-line layer (`pyfs-workspace field`) is a
  thin argument layer over it.

### The one-home rules they keep

- A blade's azimuth has one home, `post.axes`: a clocked wheel's blade
  (`clocked_blade_azimuth_deg`) and blade `n` placed ahead of blade one
  (`placed_blade_azimuth_deg`). The clockings table, the sections table, the
  sections series and the harmonic product read it, so their azimuths agree
  for either sense of rotation.
- The quasi-steady record has one type, one reader and one refusal, beside the
  file name in `cases.qsteady` (`QsteadyRecord`, `read_qsteady_record`,
  `QsteadyRecordError`); the run and the post both read it.
- The harmonic fit is made once, in `post.harmonics`; the corrections read the
  file it wrote and never fit again.
- A free-stream file is read by one reader, `cases.freestream`; a field
  operation refuses a result that reader would refuse, so what it writes is
  what a row can name.
- Where a workspace's matrices are is one function, `workspace.matrix_files`
  (the root's `*.fs` and `inputs/matrices/*.fs`), read by the repeated-POL
  census of the plan, the storage commands and `sync`.
- The fixed wing's and the quasi-steady sector's FSI steps are one shared step
  in `fsi.driver`, with the structural solve as the variation point.

### The clocked wheel and its products

A `qsteady_rotor` wheel is cut into sections at every clocking: each clocking
deletes the previous clocking's distributions, turns the wheel, initialises,
creates them again in frames turned with the wheel to that clocking and held
there, updates them and exports them, so every clocking is cut at the same
stations over the blade's span. The short licensed confirmation on 26.124 is
`reports/RPT-094`. The wheel's row of the rotor table is the mean of its
clockings' force and moment, with every coefficient computed from those mean
loads; a wheel point states its rotor state (`CT_ROTOR`, `MU_ROTOR`,
`LAMBDA_I`, `CHI_DEG` and the others) from the mean thrust. The thrust and
torque shares are taken along the rotor's axis in the frame each distribution
was cut in; an XZ or an XY cut is read, and a YZ cut is `NA` because it is not
measured. The correction routes are off by default and not validated; a route
the release does not offer is refused with its reason where the pproc or the
calibration is read.

## The 0.32.0 additions and their limits

This section records what 0.32.0 adds to the paths above and the limit each
one keeps. The tracked package holds 150 modules, eleven more than 0.31.0;
none takes a new row of the layered pipeline, and each imports only at or
below its own row, a sibling of its own subpackage included. The imports
below were read from each module's import statements, those inside function
bodies and those under `TYPE_CHECKING` included.

### The modules and their rows

- `run/records.py`, in the run row, imports the floor `_errors`, the four
  private modules of the records family (`run._record_files`,
  `run._rebuild_evidence`, `run._rebuild` and `run._assemble`, since
  0.33.0, AD-11), `workspace.naming` and `workspace.storage`, and inside a
  function body `workspace`. It holds the operations on a workspace's
  records: the exact restore of a records file from the archive and the
  mark-failed, and through the four modules it re-exports the rebuild of
  run records from the simulation folders and the records a post assembles
  from them; it re-exports which manifest a command reads, defined in
  `workspace.naming`. Until 0.33.0 the rebuild and the assembly were this
  module's own, and it imported the floor `_digest`, `cases`,
  `cases.matrix`, `cases.windows`, `results`, `workspace.flight_condition`,
  `workspace.inputs` and `workspace.matrix` for them.
  Until 0.33.0, `workspace.storage` reached this module inside two function
  bodies, for the manifest name and for the sync's rebuild. Since 0.33.0
  (AD-09, P0330-WP1) the manifest name is resolved in `workspace.naming`, and
  this module registers the rebuild with `workspace.storage` when it loads,
  which calls it through that registry: the workspace row imports nothing of
  the run row above it.
- `cases/acoustics.py`, in the cases row, imports `_errors` and `cases`, and
  `script` for annotations only, under `TYPE_CHECKING`. It
  emits the solver's acoustic toolbox on an unsteady row and states the
  contract of the export the post stage reads (`AcousticSignal`, the file
  suffix), which is why it lives in `cases`: the run and the post both name
  it, and `post` may import `cases` and never the reverse.
- `cases/_ccs.py` (private), `cases/ccs_wing.py`, `cases/ccs_fuselage.py` and
  `cases/ccs_revolution.py`, in the cases row. `_ccs` imports only
  `script.helpers`; `ccs_wing` imports `_lengths`, `cases`, `cases._ccs` and
  `script`;
  the fuselage and the revolution import `ccs_wing`, which reaches them only
  inside a function body, so the siblings form no import cycle. They emit
  the commands that have the solver make a mesh of a row's CCS file.
- `cases/setup_surfaces.py`, in the cases row, imports `cases` and
  `script.helpers` (the stabilization command's one home, AD-10), and
  `script` for annotations only, under `TYPE_CHECKING`. It
  removes the surfaces a setup names and emits the slipstream wake
  stabilization of each rotor motion.
- `post/acoustics.py`, in the post row, imports `_errors`,
  `cases.acoustics` and `post._tables`. It reads the acoustic export and
  writes the per-observer products.
- `post/disc_maps.py`, in the post row, imports `_errors`, `_tokens`,
  `post._tables`, `post.axes` and `post.harmonics`. It tables a rotor's
  sectional load over its disc.
- `post/inflow_tools.py`, in the post row, imports `_errors` and
  `cases.qsteady`. It writes a product table in the installed frame and the
  blade-view harmonics of a custom inflow.
- `post/qsteady_noise.py`, in the post row, imports only `_errors` from this
  package. It holds the exploratory quasi-steady rotor noise model, not wired
  into the post stage; its report writer `write_qsteady_noise_report` is left
  unfilled on purpose and refuses with `ContractNotImplementedError`.

The floor module `_progress` now imports `_console` and `_errors`; the floors
still import nothing from the pipeline rows.

### The console and the long commands

Every `pyfs-matrix` and `pyfs-workspace` command opens standard error with a
titled block (the command, its purpose, its workspace and, for a long
command, its live log) and prints its warnings together at its end, under
`Warnings (<count>)`; `plan` keeps its own header and its own warnings
block. Standard output and exit codes do not change. The long
commands report each stage's progress through one interface,
`_progress.stage_progress` and its iterator `tracked`: `free-space`,
`delete-sims`, `collect`, `post` and `sync`. On a terminal the line is
redrawn in place; elsewhere it is plain lines, at most one every 10 s. The
live log `logs/<command>-<stamp>.log` is written by `sync`, `restore`,
`free-space`, `delete-sims`, `collect` and `post` in a campaign workspace,
every console line flushed as it is said. The progress observes a stage and
never decides it.

### The records: restore and rebuild

The two ways back to a lost or overwritten `runs.json` are kept apart.
`pyfs-matrix restore` puts back an archived copy of a records file byte for
byte (the manifest, the storage record, the additional-post record, a
matrix's products record or its plan receipt), previewing until applied,
archiving the current file first so a restore can be undone, and writing
under the leases a sync holds, refusing while one writes. The writers of
the storage record, the additional-post record, the plan receipt and the
products record archive the previous file first, through the one home of the
archive names (`workspace.naming.archive_previous`), so each kind has a copy
to restore; a failed copy warns and never blocks the write (FR-291 to
FR-294). `pyfs-matrix
rebuild` makes run records again from `sims/`: each row runs again in a
throwaway copy with nothing submitted, a record is accepted only when the
executed script is the one this version renders, and the collect stage
completes it without writing, so a truncated output is a failure and never
a convergence; every rebuilt record carries a `REBUILT` warning. The
rebuild's refusals and their remedies are requirements: a row switched off
after it ran rebuilds with the switch set only in the copy; a build the
submission profile no longer maps takes an alias for the job descriptor
only; a simulation no current matrix holds waits for the matrix revision
that ran; a run executed on a cluster is compared with separators
normalized and each root set aside, and keeps its own root and path style;
a submitted record is pointed to `collect`, and with `--all-sims` takes the
status its outputs support unless its folder was written in the last 30
minutes; and a drifted script is refused naming each changed line, its
class and the input it comes from. The migration page says never to resume
a simulation a rebuild refused, because with no record the resume runs it
again.

### Sync, the matrix homes and the other manifests

`sync` names every simulation folder of both workspaces, recorded or not,
and rebuilds the records of those no merged record carries only when asked
(`--restore`), after it has released the manifest lease. It skips every
folder named `archive` unless asked (`--include-archives`), holds the
`runs.json` lease for the whole of its merge and copy, and copies each file
under a temporary name renamed in place once its digest matches, so an
interrupted sync never leaves a partial file. The workspace root and
`inputs/matrices/` are two equal homes of the matrices: one stem in both is
read once when the files are identical, refused by the plan and `sync`
naming both paths when they differ, and warned by the post. `post`,
`collect`, `sync`, `free-space` and `delete-sims` take `--runs NAME`, a
manifest in the workspace root. A post of another manifest writes to
`post/<matrix>@<stem>/`, and `post --from-sims` assembles records in memory
from the simulation folders and writes to `post/<matrix>@sims/`, refusing
by name what cannot be recovered and never guessing it; neither ever writes
the default products folder.

### The CCS geometry route

A row whose `GEOMETRY` names a CCS file has the solver make its mesh, by the
`[import.ccs]` table of the file's sidecar: a wing, a fuselage or a body of
revolution lofted by the curve route, or every component imported whole by
the file route, the only route that reads a component's relaxed trailing
edge line, whose shedding direction the row key `CCS_SHEDDING` restates in
the run's own copy of the file. A unit that names no length is refused. The
licensed probe round of this release (reports/RPT-096) read the import and
the three lofts; it refused the control-surface command in the form the
manual prints, so the package writes every argument of it, and that form has
not been run. The round read that the shedding direction digit is accepted
and changes the saved state, not what it changes.

### The acoustic chain

An `unsteady` or `unsteady_rotor` row may switch the solver's acoustic
sources on before the solver initializes, declare observers (named points,
a file of the input library, or an annular section) over an observer time
window, and have the signals computed and exported after the solve. The
export is a declared output, collected and hashed with the point's others,
and never read as a surface or a loads export; the setup after the
initialization, the computation on a steady row or before the solve, and a
continuation of an acoustic row are refused. The post stage reads the export
into one signal per observer and writes, under `acoustics/`, the pressure
against time and the one-sided spectrum per observer, a summary with the
overall sound pressure level and the blade-passage harmonics, and the
directivity when four or more observers lie on an arc; a harmonic the record
cannot support is `NA` with a log line, and nothing blocks. The run lists
the export among the record's outputs, and the post finds it there, as the
entry that ends with the one acoustic suffix
(`cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX`), so the two halves meet on one
record field (FR-290). The quasi-steady noise report is not part of this
release.

### The rotor products and the setup keys

A quasi-steady wheel and an `unsteady_rotor` point that cut sections write
disc maps, `sections/<point>_disc_<ROTOR>_<QUANTITY>.csv`, the sectional
load by radius and azimuth, each blade placed where `post.axes` places it;
a rotor with no blade in the table is a named skip. The plan reads the chord
of a saved simulation as it reads an OBJ's, so a wheel's reduced frequency
is warned before the run. The setup key `delete_surfaces` removes surfaces by
name, alias or family, never by index, and the script's and the record's
inventories are renumbered as the solver renumbers them; the key
`slipstream_wake_stabilization` emits the stabilization, enable or disable,
for each rotor motion. A stated key that reaches no surface or no rotor
motion is refused.

### The inflow tools

The field time mean may write a per-probe fluctuation report beside the
mean, and a fill of the probes inside a body radius from the nearest probe
outside on the same azimuth, each previewing until applied and recorded with
its provenance. A product table stated in the isolated frame may be written
again in the installed frame, the mirror through y = 0, by one column
classification stated on the post-processing definitions page. The
blade-view harmonics of a custom inflow gain the variance share of harmonics
1 to 8 and a map over the advance ratio, read through the same reading of the
field the plan uses. The last two are library functions of `post.inflow_tools`:
no command calls them in this release, so they are reached from Python only.

### Rigor, requirements and the site

The native strength match has one tolerance function that allows for the
digits a native file was printed at; a static rig row stating a fixed speed
and a swept advance ratio is planned; the two quasi-steady tables state the
clock columns and, where the row requested none, the advance ratio from the
rotor's own speed and diameter. The requirements of the capabilities of
0.25.0 to 0.31.0 are written, and every capability bullet of the change log
from 0.25.0 on names the requirement that states it, which a tier-1 test
holds. The documentation site is organized by task, each run type and topic
on a page of its own.
