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
    example pages from the example scripts, and (NFR-29)
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
review lens binds every one of them). Each was pending until the work
package named in its first line landed, and each names the evidence that
package owed; all eight are implemented, accepted on 2026-10-01 after the
0.33.0 release. None changes what the package does: AD-15 states what every
one of them keeps.

!!! decision "AD-08 The architecture guards <span class='srs-implemented'>implemented</span>"
    *Work package WP0 of the 0.33.0 scope, which lands before any other
    package so that every later one is measured. Evidence owed: the
    tier-1 tests of G1 to G8 below, each with its non-vacuity condition,
    `scripts/arch_metrics.py`, and the architecture metrics report under
    `reports/`.*

    Read with PFS-2074, PFS-2074.15 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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
      every module absent from the frozen v0.32.0 tree and under 150 code lines so the
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

    As WP0 landed and the integration recount measured: the guards are
    `tests/tier1_offline/test_architecture_metrics.py` over the baselines
    of `tests/tier1_offline/architecture_baselines.json`, and
    `python scripts/arch_metrics.py check` runs G1 to G6 and G8 alone.
    The freeze record is `reports/RPT-100` (the tree of v0.32.0: 150
    modules, 79,704 code lines, the largest 13 holding 48.2 percent of
    them, 17 modules over 1000 code lines and 6 over 2000, two
    cross-package components); the newest is the integration recount of
    the merged 0.33.0 tree, `reports/RPT-119` (219 modules, 85,208 code
    lines, the largest 13 holding 21.7 percent, 11 modules over 1000
    code lines and 1 over 2000, one cross-package component). The 47.7
    percent above is the review's measure in lines; the records count
    code lines.

!!! decision "AD-09 The row order: run above workspace <span class='srs-implemented'>implemented</span>"
    *Work package WP1 of the 0.33.0 scope (decision 4 of the scope).
    Evidence owed: the layer guards of NFR-23 reading the new table, the
    test that holds this chapter's table, the user-guide diagram and the
    generated overview to the module data, and a count of zero
    `workspace` to `run` imports.*

    Read with PFS-2074, PFS-2074.16 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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
    As WP1 landed, the count is 0 on the merged tree (2 on v0.32.0,
    `reports/RPT-100`), held as an exact ratchet.

!!! decision "AD-10 One home per constant, and the loads cycle removed <span class='srs-implemented'>implemented</span>"
    *Work package WP2 of the 0.33.0 scope (decision 15). Evidence owed:
    G6 green with an empty allowlist, and G3 finding no component that
    holds `fsi.loads` and `results.tables`.*

    Read with PFS-2074, PFS-2074.17 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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

    As WP2 landed: G6 holds with an empty allowlist, and G3 finds one
    cross-package component on the merged tree, which holds neither
    `fsi.loads` nor `results.tables` (`reports/RPT-119`; two on
    v0.32.0).

!!! decision "AD-11 The four cheap extractions <span class='srs-implemented'>implemented</span>"
    *Work package WP3 of the 0.33.0 scope. Evidence owed: G1 and G8
    entries lowered for each module named here, every public import path
    kept (AD-15), and the tests of this chapter's module lists updated
    with them.*

    Read with PFS-2074, PFS-2074.18 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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
    neither; `post.input_template` stays within the lens by its
    `Size exemption:` line, not by its count, because the table is the
    text of the examples in the order the generated template prints them.
    The `results` root is a facade of imports and `__all__`: its
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
    every public name it held, and, like `run.records`, still imports
    every other name 0.32.0 offered from it, so each keeps importing from
    there; besides `workspace.sidecars` and
    `workspace.hpc`, the build registry is `workspace.builds` and the rule
    on empty entity selections `workspace.selections`, because the review's
    two cuts left it over the lens once its `__all__` was written. The five
    modules beyond the review's names are `results.core`,
    `run._record_files`, `run._rebuild_evidence`, `workspace.builds` and
    `workspace.selections`. Measured on the merged tree, the four cut
    modules hold 441 (`post.guides`), 289 (`run.records`), 203 (the
    `results` root) and 899 (`workspace.inputs`) code lines, from 2729,
    1954, 1583 and 1831 on v0.32.0.

!!! decision "AD-12 cases/workflows is a package with a guarded order <span class='srs-implemented'>implemented</span>"
    *Work package WP4 of the 0.33.0 scope. Evidence owed: G3(b) for the
    package, the 29 goldens and the tier-3 golden diff unchanged, and G1
    for every module of the package.*

    Read with PFS-2074, PFS-2074.19 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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

    As WP4 landed: the root holds the module docstring, the re-exports and
    `__all__`, and nothing else (G8). Its 23 private modules, in the
    declared order from the top (the `package_order` entry of
    `tests/tier1_offline/architecture_baselines.json`), are `_additional`
    (the extraction script of a saved simulation), `_registry` (the entries
    of the run-type table, `build_script`, `workflow_registry`), the
    builders `_qsteady_rotor`, `_rotor`, `_unsteady` and `_steady`,
    `_skeleton` (initialization, solve, tail), `_pproc` (entries, plots,
    sections), `_probes` (probes and the sampled volume), `_clock` (export
    threshold, rotor clock, action counter, wall clock), `_exports`,
    `_reductions`, `_freestream`, `_solver_settings`, `_frames`,
    `_geometry`, `_names`, `_timing` (time stepping, `march_strategy`),
    `_motion` (the rotor a row turns, its clock speed and Mach numbers),
    `_actuator`, `_rows` (the typed readers of the row's keys),
    `_conventions` (the `Workflow` type, the conventions, selection and
    build coverage) and `_vocabulary`, the leaf. The run-type table is one
    dict created empty in `_conventions` and filled by `_registry` when the
    package is imported: the entries name the builders and the readers of
    the table sit below them, and one object filled at import is what lets
    both hold with no import pointing up; the root exports that object. A
    new run type is a builder module and one entry of `_registry`; a row
    key is registered in `_vocabulary` (`ROW_KEY_MEANINGS`) and read in
    `_rows`; an export kind is emitted by `_exports`; a geometry operation
    by `_geometry`; a post-processing block by `_pproc`, a probe kind by
    `_probes`. The module of the settings is `_solver_settings` and that of
    the quasi-steady builder `_qsteady_rotor`, because `_settings` and
    `_qsteady` are names the code already binds (a function and an import
    alias). Each module is within the lens and deep; the record of the
    package is RPT-116, and on the merged tree its 24 modules hold 10,492
    code lines, the largest 910 (`_rows`), where `cases/workflows.py`
    held 9,000 in one module on v0.32.0.
    The `modules_at_freeze` list of the baselines keeps `cases/workflows.py`:
    it is the snapshot of the tree at the freeze, read only as the set of
    modules the depth rule does not hold, and a retired path in it holds
    nothing, since the module cannot return beside the package.

!!! decision "AD-13 The post families are sibling modules <span class='srs-implemented'>implemented</span>"
    *Work package WP5 of the 0.33.0 scope (decisions 5, 8 and 15).
    Evidence owed: the byte snapshot of the products, taken before the
    first move and compared after every move, and the surface test of
    `post.products` extended to each public family module.*

    Read with PFS-2074, PFS-2074.20 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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

    As WP5 landed: four family modules are public, `post.polar` (the group
    polar, `group_polar_rows`, published from the private `_polar_rows`,
    and `write_recorded_polar`), `post.rotor_table`, `post.unsteady_polar`
    and `post.point_tables` (which also holds the per-revolution table), and
    the stage around them is private: `post._stage` (the products layout,
    the one verdict of a frozen solve, which every stage looks up there,
    the names a file may carry, the reduction plans, the post log records
    and the partial post), `post._condition` (the point condition, state,
    clock, windows and reference), `post._admit` (the records that can
    supply a row), `post._sim` (the `SimContext` and the six steps),
    `post._rotor_plan` (the rotor tables' plan), `post._reduction_stage`,
    `post._rotor_products` (a record's series and its quasi-steady,
    harmonic, noise and disc-map products) and `post._additional`. A
    private helper two modules share lives in a private module, because a
    private name is never imported out of a public one. `post.products`
    keeps the campaign stage, within the review lens (the sizes are the
    newest architecture metrics record's, not this text's), and
    `_sim_products` is cut to a short function over the six steps. The
    other long functions of the post stage MOVED and were not reduced:
    `_rotor_tables` (now in `post._rotor_plan`), `_point_reductions` (now
    in `post._reduction_stage`), `_write_the_products` and
    `_campaign_products` keep their sizes, and their entries in the
    architecture baselines are the old ones under the new module names.
    Decomposing them is later work; this package does not claim it. The
    byte snapshot (P0330-PRODUCTS-SNAPSHOT) was taken from the
    tree of `rel/0-33` at 56f7b8bd, after the product changes of FR-314
    and FR-180, over 25 recorded offline campaigns of the tier-1 suite and
    292 files; it is compared by its tier-1 test and by
    `scripts/products_snapshot.py`, each with two controls: differences
    planted into the regenerated bytes, and a probe value shifted in the
    product code, which must change the probes table. `PointState` stays as it is: the post
    stage's class carries the products' resolved state and the cases one
    the run's, and converging them is not a structural move.

!!! decision "AD-14 run is a facade over private modules and leaves the type-check exemptions <span class='srs-implemented'>implemented</span>"
    *Work package WP6 of the 0.33.0 scope (decision 7). Evidence owed:
    G8 for `run/__init__.py`, G3(b) for the package, and the type-check
    exemption list one module shorter in `pyproject.toml` and in the
    recount records of NFR-27.*

    Read with PFS-2074, PFS-2074.21 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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

    The cut of WP6 holds ten private modules, in the declared order:
    `_campaign` (the loop and the case preparation), `_sweep` (a steady
    row run as one job), `_points` (one point), `_pending` (the files a
    run writes before the solver starts), `_plan` (the plan, its cost
    table and receipt), `_continuation`, `_identity` (the package and
    solver-build checks and `reconstruct`), `_assessment`, `_executors`
    (the surface-mesh export with them) and `_ids` at the bottom (run ids,
    point names, job shape and `CampaignErrors`); the parser of
    `pyfs-matrix` is `run/_cli_parsers.py`, which brings `run/cli.py`
    under the hard limit.

    As WP6 landed: the root holds 149 code lines (4,539 on v0.32.0),
    `run/cli.py` 1,201 with its `Size exemption:` line (2,018), and the
    static type checker exempts seventeen modules, eighteen before; the
    integration recount of NFR-27 states the errors inside them.

!!! decision "AD-15 The evolution policy of 0.33.0 <span class='srs-implemented'>implemented</span>"
    *All work packages of the 0.33.0 scope and its integration recount
    (WPX; decisions 6, 9 and 15). Evidence owed: the parity receipt of
    the release, produced by a committed script comparing tag `v0.32.0`
    with the release commit, and the recount records.*

    Read with PFS-2074, PFS-2074.22 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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

    The committed script is `scripts/check_parity.py`, described in the
    0.33.0 section of this chapter; the receipt of the release is
    produced on the release commit.

### The architecture decisions shipped in 0.34.0

The decisions below are the three cuts of the 0.34.0 scope (scope record
GEO-071, section 4.11; the release goal GOAL-039, arms W8 and W9): only
the cuts that the release's features must wait for, by the rule that a
module or function in the size tables of AD-08 may only shrink, so a
feature that would add lines to one lands after its cut, in the cut's new
home. The remaining cuts are now specified for 0.36.0 in AD-19 to AD-23.
AD-16 to AD-18 shipped in 0.34.0; their named modules are tracked at HEAD
(`42cf219a`, checked with `git ls-files` on 2026-10-03), and their statuses
are reconciled to implemented. Each keeps everything 0.33.0 does, under the evolution policy of
AD-15 carried into 0.34.0 (every public path and every `__all__` in content
and order kept, a facade may re-export a private name under the G5
ratchet until the tag and none re-exported through a facade at the tag
v0.34.0, as at v0.33.0, one recount per package and per wave), and each is
proved by the oracles of the review (the 29 goldens, the tier-3 golden
diff, the products snapshot, the record fixtures and
`scripts/check_parity.py`), run in the commit that could break them.

!!! decision "AD-16 The models of the cases root leave for six modules <span class='srs-implemented'>implemented</span>"
    *Work package WP8 of the 0.34.0 scope (GEO-072, section 4.6), which
    lands before WAKE-LENGTH (FR-321 to FR-325) because `SolverSettings`
    holds the wake keys. Evidence owed: G1 for `cases/__init__.py` (under
    2000 code lines, out of the table or carrying a stated `Size
    exemption:` line), its G8 facade entry lower, the type-check
    exemption list not grown, the oracles above unchanged, and the
    package record RPT-120. Evidence:
    `tests/tier1_offline/test_p0340_cases_cut.py`.*

    Read with PFS-2075.22 at 0.34.0 (GOAL-039, arm W8): the 0.34.0 package work reads this decision.

    Measured at v0.33.0, in the unit of the AD-08 tables (code lines
    without docstrings, counted by `scripts/arch_metrics.py` into
    `tests/tier1_offline/architecture_baselines.json`):
    `cases/__init__.py` holds 2316 code lines, the one module of the
    package over the hard limit of AD-08, and its G8 facade entry is
    4916. The models leave the root for six
    modules of `pyflightstream.cases`:

    - `cases/pproc.py`: `PprocSpec` and its parts,
      `global_frame_plot_declarations` and the group-alias rule;
    - `cases/reference_blocks.py`: `RotorBlock`, `ActuatorBlock`,
      `BladeDatum`, `frame_basis_for_shaft`, `AliasCycleError` and
      `AXIS_UNIT_VECTORS`;
    - `cases/settings.py`: `SolverSettings`, `SOLVER_SETTING_COMMANDS`,
      `FluidState`, `PointState`, `point_state_key` and `ReferenceData`;
    - `cases/mesh.py`: `MeshOperation`, `CadImportOptions`, `MeshImport`,
      `TrailingEdgeMarking`, `RawMeshConditions`, `BaseRegionOperation`
      and `PortBoundary`;
    - `cases/naming.py` and `cases/selection.py`: the naming and the
      selection models of the root.

    The root keeps `InputKey`, `CampaignConfigError`, `ScriptRecipe`,
    `SweepAxis`, the exports vocabulary, `CustomFlag`, `RawCommand`,
    `FrameSpec`, `SimCase`, `Campaign` and the recipes, and re-exports
    every name it exported, its `__all__` unchanged in content and
    order. The forward references between `SolverSettings`,
    `PortBoundary` and `BaseRegionOperation` become imports from
    `cases/mesh.py` into `cases/settings.py`, in that direction only.
    None of the six imports the root `pyflightstream.cases`, and the six
    form no import cycle among themselves, module-level and deferred
    imports alike; a tier-1 test of the work package asserts both, with
    a planted import of the root as its control.
    `pyflightstream.cases` is exempt from the static type checker and
    the six modules are not: every moved line is typed, and a construct
    that resists is narrowed with a stated reason rather than given an
    exemption. Each new module is public, declares `__all__` and has its
    page in the API reference (NFR-29). A moved name is supported at both
    paths, the root re-export and its new module; the documentation cites
    the new module, and no removal of the root re-export is planned.

    For the backlog: the six homes are where the 0.34.0 features add
    their fields (the wake keys of FR-321 to FR-324 in `settings`), so
    the root does not grow again; and the modules of the package that
    use a moved name import it from its new module rather than through
    the root, so the 0.35.0 cuts of `cases/matrix.py` and of the
    `workspace` root read the models from their homes and the root adds
    no import edge from `workspace` to `cases`.

    Measured at the cut (work package WP8, 2026-10-01, record RPT-120):
    `cases/__init__.py` holds 609 code lines and is off the G1 table, its
    G8 facade entry falls from 4916 to 1128, and the six modules hold 855
    (`pproc`), 201 (`reference_blocks`), 222 (`settings`), 265 (`mesh`),
    189 (`naming`) and 214 (`selection`) code lines, each within the lens
    and deep. Two placements differ from the list above, because a model
    the six hold reads them and none of the six may import the root:
    `CampaignConfigError` is defined in `cases/reference_blocks.py`, the
    floor of the six, beside `AliasCycleError`, since `frame_basis_for_shaft`,
    the selection and the naming raise it; and the exports vocabulary
    (`EXPORT_KINDS` to `classify_outputs`) is defined in `cases/pproc.py`,
    since `PprocSpec` reads it. The root re-exports both at their 0.33.0
    paths, as it does every moved name. `SweepAxis` and `SimCase` stay in
    the root; the naming functions read a case and a sweep through two
    private protocols of `cases/naming.py`, which state the attributes they
    use. The six import one another in one order, `reference_blocks`,
    `selection`, `pproc`, `naming`, `mesh`, `settings`, each only those
    before it.

    The 0.35.0 cut this keeps easy is the cut of `cases/matrix.py` (WP9d,
    1808 code lines): of the names the matrix reader takes from the root,
    the naming ones (`POINT_AXIS_KEYS`, the two rotation keys and
    `multiplied_sweep`) and the exports vocabulary (`default_outputs`) now
    have homes below the root, so the modules that cut makes for the
    sweep names and the default outputs import those homes and not the
    root; only the part that builds `SimCase`, `Campaign`, `SweepAxis`,
    `InputKey` and `RawCommand` still reads the root. The field
    WAKE-LENGTH adds to `SolverSettings` lands in `cases/settings.py`. The
    modules that import a moved name still import it through the root at
    0.34.0, and the docstrings of modules outside the six still cite a
    moved name by its root path (34 citations in 20 modules, counted at
    the cut; each resolves through the re-export, and the pages under
    `docs/` cite none): moving those imports and repointing those
    citations edits files other packages of the same wave edit, so both
    are left to the 0.35.0 cuts that open those files. The API reference
    pages and the six modules' own docstrings cite the new modules.

!!! decision "AD-17 The solver settings are emitted by family, behind the facade of solver_settings <span class='srs-implemented'>implemented</span>"
    *Work package WP9a of the 0.34.0 scope (GEO-072, section 4.7), which
    lands before WAKE-LENGTH because the wake emission is in
    `solver_settings`. Evidence owed: `script/helpers.py` out of the G1
    table, `solver_settings` out of the G2 length table, the 29 goldens
    and the tier-3 golden diff unchanged, and the package record
    RPT-121.*

    Read with PFS-2075.23 at 0.34.0 (GOAL-039, arm W9): the 0.34.0 package work reads this decision.

    Measured at v0.33.0, in the unit of the AD-08 tables (code lines
    without docstrings, counted by `scripts/arch_metrics.py` into
    `tests/tier1_offline/architecture_baselines.json`):
    `script/helpers.py` holds 1678 code lines and `solver_settings` is
    461 code lines long with 61 parameters. The function
    `pyflightstream.script.helpers.solver_settings` keeps its signature,
    its defaults, its docstring's contract and its public path, and
    becomes the facade over per-family emitters in a private module
    `script/_settings.py`, one emitter per family of settings, each
    called in the order the 0.33.0 function emitted, so the emitted
    lines and their order are byte-identical. The relaxed trailing edge
    emission moves to a private module `script/_relaxed_te.py`.
    `solver_settings` leaves the G2 length table; its parameter count is
    its public signature and stays.

    For the backlog: the wake emission of FR-321 and FR-324 lands in the
    wake family's emitter, and a later setup key of the solver chapters
    (the audit of FR-319) lands in its family's emitter without growing
    the facade; the families do not import `cases` or `workspace`, so the
    0.35.0 cut of `workspace/matrix.py` (its setup binding) calls the
    facade as it does today.

    As WP9a landed (GOAL-039, arm W9; record RPT-121), in code lines of the
    AD-08 unit: `script/helpers.py` holds 951 and leaves the G1 table;
    `solver_settings` is 67 code lines long with its 61 parameters and
    leaves the G2 length and limits tables. `script/_settings.py` (598)
    holds `emit_solver_settings`, which reads every argument before the
    first emission in the 0.33.0 order, then emits the time regime and
    the five family tables (the runtime settings, the boundary layer,
    separation, convergence and the advanced settings, each a table of
    rows whose order is the emission order) with the separation models
    and the minimum-Cp default between them, then builds the snapshot.
    Every ARGUMENT refusal therefore fires on an untouched script; a
    VERSION refusal still fires when the emission reaches a command the
    build lacks, as in 0.33.0. `script/_relaxed_te.py` (119) holds the
    relaxed trailing edge. The cut of the function and of the relaxed
    trailing edge alone left `helpers.py` at 1,128 code lines, so the
    helpers that set up a run moved to `script/_settings.py` with it,
    unchanged apart from type annotations: the flow conditions
    (`free_stream`, `fluid_fifth_property`, `atmosphere`),
    `unsteady_solver`, and the solver initialization
    (`initialize_solver`, whose arguments carry `WAKE_TERMINATION_X`, and
    `start_solver` with the flush of the deferred induced-drag
    selection), and the toggle readers the helpers share. They sit in
    the private module rather than in the public `script/toggles.py`,
    because a private name imported out of a public module is a layer
    crossing the tier-1 suite refuses. The wake keys therefore have one
    module: the `SET_WAKE_TERMINATION_TIME_STEPS` row of the advanced
    family and the wake termination plane of `initialize_solver`.
    `pyflightstream.script.helpers` imports every moved name, so every
    public path of 0.33.0 is kept. `script/_relaxed_te.py` is a new
    module between 60 and 150 code lines, the review check of the deep
    modules rule; it is kept because this decision names it and it holds
    one specification behind eight public names (the keyword, its two
    field tuples, the shedding directions and their default, the parser,
    the resolver and the parsed record). Evidence:
    tests/tier1_offline/test_p0340_settings_cut.py (the 0.33.0
    signature; the emission of four builds, 26.121 with the bulk model,
    against the scripts the 0.33.0 tree rendered; every separation model
    in one call in the 0.33.0 order; every adjacent pair of argument
    refusals raising the earlier one, as 0.33.0 did; one family per
    keyword; the public path of every moved name), and the goldens of
    tests/tier1_offline/test_workflows.py unchanged.

!!! decision "AD-18 The parser of pyfs-matrix is built by family, and run/cli.py leaves its size exemption <span class='srs-implemented'>implemented</span>"
    *Work package WP9b of the 0.34.0 scope (GEO-072, section 4.7), which
    lands before the run-usability commands (FR-326, FR-327) and the
    thin-blade command (FR-330). Evidence owed: `run/cli.py` under 1000
    code lines with its `Size exemption:` line removed and out of the G1
    table, `_build_parser` out of the G2 length table, the command-line
    parity of `scripts/check_parity.py` (every console tool, subcommand,
    option and choice) unchanged, and the package record RPT-122.*

    Read with PFS-2075.24 at 0.34.0 (GOAL-039, arm W9): the 0.34.0 package work reads this decision.

    Measured at v0.33.0, in the unit of the AD-08 tables (code lines
    without docstrings, counted by `scripts/arch_metrics.py`):
    `run/cli.py` holds 1201 code lines under a `Size exemption:` line,
    and `_build_parser` of `run/_cli_parsers.py` is 556 code lines long. `_build_parser` becomes a short function that calls
    one `_add_<family>_parsers` function per family of subcommands, in
    the pattern of `_add_storage_parsers` and `_add_records_parsers`,
    adding the subcommands in the order 0.33.0 added them, so the help
    text and every accepted command line are unchanged. The print
    helpers of `run/cli.py` move to a private module `run/_cli_print.py`.
    `run.cli.main` and every public name of `run.cli` keep their path;
    the tests that patch or import private names of `run.cli` are
    retargeted before the tag.

    For the backlog: the selection options of FR-326, the message of
    FR-327 and the thin-blade subcommand of FR-330 land in their family
    functions, and each later subcommand adds one family function or
    extends one, so `run/cli.py` and `_build_parser` do not grow back;
    the cheatsheet test of FR-328 walks the same parser and is unchanged
    by the cut.

    As built by WP9b: `_build_parser` is 20 code lines and calls ten family
    functions (`_add_workspace_parsers`, `_add_storage_parsers`,
    `_add_records_parsers`, `_add_convert_parsers`, `_add_plan_parsers`,
    `_add_run_parsers`, `_add_run_option_parsers`, `_add_collect_parsers`,
    `_add_post_parsers`, `_add_post_selection_parsers`), each of the new ones
    under 100 code lines, so that no function joins the list of
    functions over 100 code lines. The generated command-line reference is
    byte-identical to the one of the tree before the cut. The eight print
    functions of plan and of the storage commands moved to `run/_cli_print.py`.

    Evidence: tests/tier1_offline/test_p0340_cli_cut.py.

### The 0.36.0 architecture decisions

The five cuts below are implemented. Each carries AD-15's evolution policy
into 0.36.0: every public path and every `__all__` in content and order is kept, private facade re-exports
remain under G5 and are retargeted before the tag, and each package and the
integration have a recount. NFR-40 is the no-behaviour-change clause, with
v0.35.1 as the baseline for scripts, products, records, console text and
exit codes. A named difference needs its FR id and migration entry.

!!! decision "AD-19 WP7 The workspace root becomes a facade over its record, layout and registries <span class='srs-implemented'>implemented</span>"
    *Work package WP7 of 0.36.0. Verification:
    `tests/tier1_offline/test_p0360_w7.py` compares the complete public
    export order and object identity; `test_p0360_identity.py` checks
    public class module names and pickle identity;
    `test_architecture_metrics.py` checks G1, G3, G5 and G8;
    `test_goal028_module_level_layering.py` checks the downward edges;
    `test_workspace.py` and `test_products_snapshot.py` retain the record
    and product oracles.*

    The record models and `WorkspaceError` live in `workspace/manifest.py`,
    and the matrix layout helpers and `ReferencePoints` live in
    `workspace/_layout.py`. The three registries (post stages, post
    diagnostics and input guides) stay in `workspace/__init__.py`: a
    separate module measured 32 code lines, below the depth minimum
    (goal record 2.3.0).
    `workspace/__init__.py` keeps every public import path under AD-15's
    evolution policy. It leaves the G1 table, and its G8 facade lines
    fall by at least the code moved out; neither baseline grows.
    NFR-40 governs every observable output of the cut.

    Moved public classes retain their public `__module__`, including
    `ReferencePoints` and the manifest classes. Pickle resolves the same
    public object. `inspect.getsource` on a moved class may raise
    `OSError`, because its public module now re-exports the definition;
    source inspections must read the defining module. This also applies
    to `ResolvedMatrix` in AD-20 and `MatrixError` in AD-21.

    ARCH-3: AD-01's order is `run` above `workspace` above `cases` above
    `script` and `results`. A module-level import by `workspace` of
    `cases.matrix` or `cases.workflows` is DOWNWARD and legal. It is
    pinned by NFR-23's module-level guard,
    `tests/tier1_offline/test_goal028_module_level_layering.py::test_no_module_level_import_reaches_a_higher_layer`,
    whose legitimate-shapes control includes `workspace` importing
    `cases.matrix`. The work package extends that control to both named
    edges and an upward-import failing control, alongside AD-08 G3;
    `test_architecture_metrics.py::test_the_workspace_to_run_count_is_an_exact_ratchet`
    keeps `workspace` to `run` at zero. Cross-package consumers use
    public re-exports, including `cases.workflows` and `workspace.ledger`,
    never another package's private modules.

!!! decision "AD-20 WP9c Matrix binding is phased over one private context <span class='srs-implemented'>implemented</span>"
    *Work package WP9c of 0.36.0. Verification:
    `tests/tier1_offline/test_p0360_w9c.py` compares complete resolved
    matrices with the pre-cut `fixtures/p0360_w9c.json` golden;
    `test_p0360_identity.py` pins `ResolvedMatrix` identity;
    `test_architecture_metrics.py` checks the G1 and layer ratchets;
    `test_goal028_module_level_layering.py` checks downward imports.*

    `workspace/matrix.py::resolve_matrix` is decomposed into phases over
    one `_Binding` context in `workspace/_matrix_binding.py`, which also
    owns `ResolvedMatrix` and preset binding. `workspace/_matrix_phases.py`
    owns the ordered build, artifact, row and flight-state resolution
    phases. `workspace/matrix.py` orchestrates them and leaves G1.
    Every public path is kept under AD-15's evolution policy, and NFR-40
    preserves scripts, products, records, console text and exit codes.

    ARCH-3 has the same answer as AD-19: AD-01 places `workspace` above
    `cases`, so module-level imports of `cases.matrix` and
    `cases.workflows` are legal downward edges. The NFR-23 guard and the
    AD-08 G3 controls named in AD-19 pin that direction; moving binding
    into private modules does not permit an import of `run` or a
    cross-package reach into a private module.

!!! decision "AD-21 WP9d Matrix layouts and upgrading have private homes <span class='srs-implemented'>implemented</span>"
    *Work package WP9d of 0.36.0. Verification:
    `tests/tier1_offline/test_p0360_w9d.py` compares rows, converted text
    and warnings with `fixtures/p0360_w9d_goldens.json`;
    `test_p0360_identity.py` pins `MatrixError` identity;
    `test_p0360_rv.py::test_mypy_exempt_module_count_cannot_grow` checks
    the exemption ratchet; `test_architecture_metrics.py` checks G1 and G3.*

    The column layouts and `MatrixError` of `cases/matrix.py` live in
    `cases/_matrix_layouts.py`, and the upgrader lives in
    `cases/_matrix_upgrade.py`. Both are private modules below the
    `cases.matrix` entry point; neither imports that entry point back.
    They remain in the cases layer of AD-01. Every moved line is
    type-clean, and the mypy exemption list shrinks or stays unchanged,
    as NFR-27 requires; no extraction earns a new exemption.
    AD-15's evolution policy keeps every public path, and NFR-40 keeps
    the emitted scripts, product bytes, records, console text and exit
    codes unchanged except for a named requirement's difference.

!!! decision "AD-22 WP10a The long run functions are decomposed within G2 <span class='srs-implemented'>implemented</span>"
    *Work package WP10a of 0.36.0. Verification:
    `tests/tier1_offline/test_architecture_metrics.py` checks the WP10a
    removals from `architecture_baselines.json`'s `function_lines` and
    `function_limits` tables; `test_run_campaign.py`, `test_run.py` and
    `test_matrix_run.py` retain
    the run and assessment fixtures; `test_products_snapshot.py` retains
    the product oracle; `test_p0360_rv.py` checks the plan lookup.*

    `run_campaign`, `_execute_point`, `_execute_sweep` and
    `LoadsAssessor.__call__` are decomposed into private helpers in
    `run/`, in the existing modules listed below. Every resulting function
    is within AD-08 G2: complexity 10, branches 12, statements 50 and positional
    arguments 5, with no raised baseline. The modules obey the run
    package's guarded order and AD-01's layer direction.
    AD-15's evolution policy keeps every public path, and NFR-40 is the
    no-behaviour-change clause. This decision imposes no order between
    the GF probe and WP10a work in `run/_batch_plan.py`.

    WP10a keeps the helpers in their existing modules; no module is added.
    The campaign phases share `_CampaignState`, the point and sweep phases
    use `_PointJob` and `_SweepJob`, and assessment uses `_LoadsJudgment`.
    The private helpers are:

    - `run/_campaign.py`: `_resolve_campaign_schedule`,
      `_schedule_campaign_case`, `_resolve_campaign_redo`,
      `_check_campaign_staged_inputs`, `_preflight_campaign_schedule`,
      `_start_campaign_progress`, `_prepare_campaign_case`,
      `_start_campaign_sweep`, `_execute_campaign_sweep`,
      `_execute_campaign_points`, `_resolve_campaign_continuation`,
      `_execute_campaign_point`, `_finish_campaign`.
    - `run/_points.py`: `_prepare_point_script`, `_retain_point_provenance`,
      `_retain_point_translations`, `_write_point_script`,
      `_write_point_pending_files`, `_run_point_solver`,
      `_collect_point_outputs`, `_assess_point_record`,
      `_retain_continued_field_inputs`.
    - `run/_sweep.py`: `_prepare_sweep_script`, `_write_sweep_script`,
      `_run_sweep_solver`, `_collect_sweep_outputs`, `_assess_sweep_points`,
      `_record_sweep_outcome`.
    - `run/_assessment.py`: `_find_assessment_outputs`,
      `_read_assessment_loads`, `_validate_assessment_loads`,
      `_find_assessment_log`, `_judge_assessment_log`,
      `_judge_assessment_iterations`.

    The four entry points leave both G2 baseline tables. The plan resolves
    `_is_cold_start` through `run._ids`, the same module attribute as the
    campaign. Evidence for QA2 (FR-364):
    `tests/tier1_offline/test_p0360_rv.py::test_plan_resolves_the_patched_cold_start_check`.

!!! decision "AD-23 WP10b The long post functions are decomposed within G2 <span class='srs-implemented'>implemented</span>"
    *Work package WP10b of 0.36.0. Verification:
    `tests/tier1_offline/test_architecture_metrics.py` checks the WP10b
    `architecture_baselines.json` entries: all four functions are absent
    from `function_lines`, with reduced `function_limits` entries only for
    the retained rotor and writer signatures. `test_products_snapshot.py`
    compares the unchanged product fixtures; `test_public_api.py`
    classifies the private campaign module.*

    `_rotor_tables`, `_write_the_products`, `_campaign_products` and
    `_point_reductions` are decomposed into private helpers in `post/`,
    with new helpers within AD-08 G2 (complexity 10, branches 12,
    statements 50 and positional arguments 5), with no raised baseline.
    The existing rotor and writer signatures retain their positional
    argument allowances under AD-15; their complexity, branch and
    statement baselines fall.
    `post/_products_campaign.py` owns the `_CampaignProducts` context,
    `_admit_campaign_records` for ordered record admission,
    `_record_has_frozen_failure` for failed-status warnings and freeze
    evidence, `_index_record_surfaces` for native surface indexing and
    missing or refused inputs, and `_warn_unreadable_matrix` for the
    fallback to recorded matrix values. The remaining helpers stay in
    their existing post modules. The modules stay in the post layer and
    obey AD-01.
    AD-15's evolution policy keeps every public path. NFR-40 is the
    no-behaviour-change clause: the products snapshot and parity
    comparisons must preserve product bytes as well as scripts,
    records, console text and exit codes.

## Command-line surface

Five console entry points, one per operational concern: `pyfs-qa`
(evidence tiers 2 and 3), `pyfs-workspace` (workspace initialization,
archiving of a recorded simulation, and migration of a flat geometry
library into one folder per geometry),
`pyfs-matrix` (run-matrix upgrade, conversion, pre-flight, run, boundary
inventory, collection of a submitted job's outputs, post-processing, and
the workspace's disk and its other copies: `space-in-use`,
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
  calibration), below its row. Its table reader is in `post._tables` (AD-10), so it does not import `post.products`. It is the one applicator of the correction routes: every corrected
  product is a new file beside its raw one, never written over it, and none is
  validated. The Theodorsen and Sears functions are a diagnostic only.
- `workspace/fields.py`, in the workspace row, imports `_digest`, `cases`,
  `cases.freestream`, `cases.workflows` and `workspace`. It builds a custom
  free-stream file of `inputs/freestreams/` from other fields (mirror, move,
  subtract, time mean), previewing until applied, with a provenance record
  beside each result; the command-line layer (`pyfs-workspace field`) is a
  thin argument layer over it.
- `workspace/actuator_profiles.py` (0.34.0, FR-347), in the workspace row,
  imports `_digest`, `_textio`, `script`, `script.helpers`, `workspace` and
  `workspace.inputs`. It builds the radial thrust profile of an actuator disc,
  `inputs/profiles/<stem>.csv`, from a POL's written sections or a generic
  shape, scales it to a thrust or a CT, checks the integral of the written rows
  and reads the text back through the run's profile renderer before writing it
  beside its provenance record; the command-line layer (`pyfs-workspace
  profile`) is a thin argument layer over it, as for the field operations.

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
  `run._rebuild_evidence`, `run._rebuild` and `run._assemble`, AD-11), `workspace.naming` and `workspace.storage`, the alias helper
  `run._alias` (the point selector of mark-failed), `run._mark_converged`
  (the person's verdict of CONVERGED, re-exported as `mark_converged`, FR-414), and inside a
  function body `workspace`. It holds the operations on a workspace's
  records: the exact restore of a records file from the archive and the
  mark-failed, and through the four modules it re-exports the rebuild of
  run records from the simulation folders and the records a post assembles
  from them; it re-exports which manifest a command reads, defined in
  `workspace.naming`. The rebuild and assembly implementations live in their private modules. It still imports the
  floor `_digest`, `cases`, `cases.matrix`, `cases.windows`, `results`,
  `workspace`, `workspace.flight_condition`, `workspace.inputs` and
  `workspace.matrix`, for one reason only: every name 0.32.0 offered from
  this module, which had no `__all__`, keeps importing from it, and the
  parity check (`scripts/check_parity.py`) holds each one.
  Under AD-09 (P0330-WP1), the manifest name is resolved in `workspace.naming`, and
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
- `post/inflow_tools.py`, in the post row, imports `_decimal`, `_errors`,
  `_textio` and `cases.qsteady`. It writes a product table in the installed frame and the
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
in the requirement-traced release series (0.25.0 and later) names the requirement that states it, which a tier-1 test
holds. The documentation site is organized by task, each run type and topic
on a page of its own.

## The 0.33.0 additions and their limits

This section records what 0.33.0 changes in the structure above and the limit
each change keeps. The tracked package holds 219 modules: seventy arrived and
one, `cases/workflows.py`, became a package, so the count is sixty-nine more
than 0.32.0. The release moves code and changes no product, emitted script or
console behaviour for the sake of a move: the decisions AD-08 to AD-15 above
state each move and what it keeps, and this section adds what was measured
once every work package had merged. Every new module sits in the row of its
package; the layer guards of NFR-23 (module level and function bodies) and,
inside the two packages that declare an order, guard G3(b) hold on the merged
tree.

### The measured structure

The freeze record measured the tree of v0.32.0; the integration recount
measured the merged 0.33.0 tree with the same reader. Sizes are code lines,
docstring and comment lines excluded.

| measure | v0.32.0 (`reports/RPT-100`) | 0.33.0 (`reports/RPT-119`) |
|---|---:|---:|
| modules | 150 | 219 |
| code lines | 79,704 | 85,208 |
| share of the largest module | 11.3 percent | 2.7 percent |
| share of the largest 5 modules | 30.6 percent | 10.4 percent |
| share of the largest 13 modules | 48.2 percent | 21.7 percent |
| modules over 1000 code lines | 17 | 11 |
| modules over 2000 code lines | 6 | 1 |
| functions over a limit of G2 | 230 | 227 |
| cross-package import components | 2 | 1 |
| `workspace` to `run` imports | 2 | 0 |
| package-root lines beyond a facade | 23,961 | 12,834 |
| private names reached by tests | 242 | 240 |

The one module over 2000 code lines is `cases/__init__.py`, a baseline entry
that may only fall. The one cross-package component left joins the package
root, `post` and `run` (the root imports them so that their registrations run);
it is the frozen baseline's and may not gain a member.

### The 0.33.0 modules and their rows

- The cases row: `cases.workflows` is a package of 24 modules, its root a
  facade and its 23 private modules in the declared order of AD-12. Four
  private modules carry the 0.33.0 features of the row: `cases._setup_keys`
  (the setup keys of a preset and the command each reaches, FR-316, FR-317,
  FR-319), `cases._setup_link` (the analysis settings of a setup: the loads
  selections, the moments model and its rotor link, the unsteady solver
  actions, FR-317, FR-318), `cases._skipped_families` (each family a row's
  geometry does not carry, named once per matrix at plan, FR-320) and
  `cases._unsteady_actions` (the step counter and the per-step actions every
  unsteady march registers, FR-314).
- The workspace row: `workspace.sidecars`, `workspace.hpc`,
  `workspace.builds` and `workspace.selections` (AD-11), and three private
  modules: `workspace._matrix_homes` (the one lookup of a matrix by name over
  both homes, which every command that takes a matrix reads, FR-310),
  `workspace._row_setup` (the setup keys a row states over its preset,
  FR-316) and `workspace._geometry_clean` (a geometry reduced to its meshes and
  boundary conditions, and the plan warning that asks for it, FR-308, FR-312,
  FR-313).
- The run row: the four private modules of the records family (AD-11), the
  ten private modules of the facade and `run._cli_parsers`, the parser of
  `pyfs-matrix` (AD-14). The package's declared order puts `run.cli`,
  `run.rename`, `run.records`, `run.collect` and `run.matrix` above the root,
  because they import it, and the private modules below it.
- The results row: `results.core`, `results.loads`, `results.log` and
  `results.exports` under a facade root (AD-11), and
  `results.sectional_loads`, the parser the structural side branch now
  re-exports (AD-10).
- The post row: `post.glossary` and `post.input_template` (AD-11); the public
  family modules `post.polar`, `post.rotor_table`, `post.unsteady_polar` and
  `post.point_tables`, and eight private modules of the stage (AD-13).
- Beside the private reader of a saved simulation, `_fsm_fresh` states what a
  freshly imported simulation holds, block by block, for the geometry clean of
  FR-312; it imports only `_errors`.

### The parity of the release

`scripts/check_parity.py` is the committed script of AD-15. It exports two
trees from git, the tag `v0.32.0` and the release commit, never a working
tree, runs each in an interpreter of its own and compares four things: every
public name, including those of a module without `__all__`, at the same
dotted path; every console tool, subcommand, option and choice of the
argument parsers; the emitted scripts of the golden and tier-3 campaign set,
byte for byte; and every byte a post over one recorded workspace writes,
`products.json` included, with only the measured wall-clock stamps of the
post log normalized. A difference in the scripts or the products passes only
when the script names it with a requirement this SRS defines, and only when
every changed line matches that entry's lines, in order and number. Two
requirements are named: FR-314 (every unsteady script gains the three lines
of the step counter's registration and nothing else) and FR-180 (the
per-revolution drift warnings of the post log are worded and counted anew;
the products are byte-identical). Each run plants one difference per
comparison and fails unless every planted difference is caught, and its
receipt names the digest of the script that produced it. The receipt of the
release is produced on the release commit.

### What moved and was not reduced

The long functions of the run and post stages moved whole into the modules
that hold them now, and keep their sizes and their baseline entries:
`run_campaign`, `_execute_point`, `_execute_sweep`, the assessor's verdict,
the `pyfs-matrix` parser builder, the rotor tables' plan and the campaign
loop of the post stage. Nine package roots still hold statements beyond a
facade and stay in the G8 table, each entry only falling. Decomposing them is
later work, and this release does not claim it.

## The 0.34.0 additions and their limits

This section records what 0.34.0 changes in the structure above and the limit
each change keeps, measured on the merged first wave of the release (the
three cuts AD-16 to AD-18 and the features built beside them), against
v0.33.1. The tracked package holds 234 modules: fifteen arrived and none
left. The cuts move code and change no product, emitted script or console
behaviour for the sake of a move; the decisions AD-16 to AD-18 above state
each cut and what it keeps, under the evolution policy of AD-15. One emitted
line changes on purpose, the speed handed to an actuator disc (FR-331), and
the parity script names it. Every new module sits in the row of its package,
and the layer guards of NFR-23 (module level and function bodies) and, inside
the two packages that declare an order, guard G3(b) hold on the merged tree.
The items of the second wave are listed at the end, as integrated.

### The measured structure of the first wave

Both columns are measured with the same reader, `scripts/arch_metrics.py`.
No record was written for the patch release v0.33.1, whose structure is that
of 0.33.0 (`reports/RPT-119`, 219 modules); the first wave's record is
`reports/RPT-123`. Sizes are code lines, docstring and comment lines
excluded.

| measure | v0.33.1 | 0.34.0, first wave (`reports/RPT-123`) |
|---|---:|---:|
| modules | 219 | 234 |
| code lines | 85,250 | 86,961 |
| share of the largest module | 2.7 percent | 2.1 percent |
| share of the largest 5 modules | 10.4 percent | 8.9 percent |
| share of the largest 13 modules | 21.7 percent | 18.0 percent |
| modules over 1000 code lines | 11 | 7 |
| modules over 2000 code lines | 1 | 0 |
| functions over 250 code lines | 11 | 9 |
| functions over a limit of G2 | 227 | 225 |
| cross-package import components | 1 | 1 |
| `workspace` to `run` imports | 0 | 0 |
| package-root lines beyond a facade | 12,834 | 9,046 |
| private names reached by tests | 240 | 240 |
| type-check errors in the exempted modules | 192 in 17 | 160 in 16 |

No module is over 2000 code lines. The seven over 1000 are baseline entries
that may only fall: `cases/matrix.py`, `workspace/__init__.py`,
`workspace/storage.py`, `post/input_template.py` (with its `Size exemption:`
line), `workspace/matrix.py`, `run/matrix.py` (with its line) and
`post/corrections.py`. Four modules left the size table in the first wave:
`cases/__init__.py` (AD-16), `script/helpers.py` (AD-17), `run/cli.py`
(AD-18, its `Size exemption:` line removed) and `qa/specs.py` (the probe
catalog cut below). Two functions left the length table:
`solver_settings` (AD-17) and `_build_parser` (AD-18). `pyflightstream.qa.specs`
left the type checker's exempted set, so the exempted modules are sixteen.

### The 0.34.0 modules and their rows

- The cases row: the six public modules of AD-16, in the order they import
  one another, each importing only those before it and none importing the
  root `pyflightstream.cases`. `cases.reference_blocks` (201 code lines)
  imports only `_errors`; `cases.selection` (214) imports `_errors`,
  `_deprecations`, `_fsm` and `cases.reference_blocks`; `cases.pproc` (855)
  imports `_errors`, `_deprecations`, `_expressions`, `_retired_names`,
  `_tokens`, `commands`, `cases.corrections` and `cases.selection`, and
  `cases.acoustics` inside a function; `cases.naming` (189) imports
  `cases.reference_blocks`; `cases.mesh` (265) imports the private
  `cases._ccs`; `cases.settings` (222) imports `_atmosphere`, `commands`,
  `cases._setup_keys`, `cases.mesh`, `cases.reference_blocks`,
  `script.solver_setup` and `script.toggles`. The root holds 609 code lines
  (2316 at v0.33.1) and its facade entry of G8 fell from 4,916 to 1,128.
- The script row: `script._settings` (598), the emitters by family behind
  `solver_settings`, the run-setup helpers and the toggle readers they share,
  importing `commands`, `script`, `script.solver_setup` and `script.toggles`;
  and `script._relaxed_te` (119), the relaxed trailing edge, importing
  `script`. `script.helpers` is the only module that imports either, and it
  imports every moved name, so each 0.33.0 path is kept.
- The run row: `run._cli_print` (274), the printing of `plan` and of the
  storage commands, importing `run`, `run._continuation_frame`, `_console`
  and `_progress`, and `workspace.setup_inspection` and `workspace.storage`
  inside its functions; `run.cli` is the only module that imports it, and the
  package's declared order places it after `_cli_parsers`.
- The qa row: the probe catalog of `qa.specs` is cut into five private
  modules that register into one shared table: `qa._spec_kit` (94, the
  instruments and the registry, importing `qa.probes` and `script`),
  `qa._spec_catalog_b` (592), `qa._spec_ccs_noise` (612, which also imports
  `_fsm` and `script.helpers`), `qa._spec_ccs_mesh` (207) and `qa._spec_t1`
  (69). `qa.specs` (710) imports all five and re-exports `PROBE_SPECS`.
- The workspace row: `workspace._degenerate` (445), the library core of the
  thin blade of FR-330, importing `_digest`, `_errors`, `_fsm`, `cases` and
  `workspace.sidecars`. No module of the package calls it in the first wave.

Three of the fifteen are under 150 code lines (`qa._spec_kit`, `qa._spec_t1`
and `script._relaxed_te`), the review list of the deep-modules rule of AD-08.

### The first-wave features and their homes

- FR-328 and FR-329, the guides numbered from 01 with the cheatsheet as guide
  04: the `guide/` tree, its build scripts and the admitted-PDF rule of the
  CI; no package module changes.
- FR-330, the thin blade from a blade mesh, its library core:
  `workspace/_degenerate.py`.
- FR-331, the swirl of an actuator disc: `cases/workflows/_actuator.py`, and
  the named difference of `scripts/check_parity.py`, which accepts the disc
  speed line with its sign changed and nothing else; FR-332, the warning on a
  RELAXED disc naming a profile: `run/_plan.py`.
- FR-333 to FR-335 and FR-342, the probe specifications: the catalog modules
  above; the licensed verdicts are owed.
- FR-339, the signed tip deflection as the last column of the FSI
  convergence log: `fsi/driver.py`.
- FR-337, FR-343, FR-344 and FR-346: records of the repository (RPT-132,
  RPT-131, the digests out of the tracked tree, `RELEASE-READY.md`); no
  package module changes. FR-345: the dry-run trigger of the release workflow
  and the report-index test that reads its own release section.

### The second wave

The second wave of 0.34.0, as integrated into `rel/0-34`:

- the LF line ends of every text file the package writes (NFR-32), through
  one private floor module, `pyflightstream._textio`, which every writer
  calls and a guard test walks `src/` for;
- the wake length of a rotor row (FR-321 to FR-325): its keys on
  `SolverSettings` in `cases/settings.py` (`wake_termination_length`,
  `wake_termination_thrust_n`, `wake_termination_revolutions_cap` and the
  end plane `wake_termination_x_m`), routed by `cases/_setup_keys.py`; the
  conversion into steps in `cases/workflows/_freestream.py`, whose steps the
  `SET_WAKE_TERMINATION_TIME_STEPS` row of `script/_settings.py` emits, and
  the end plane written into `INITIALIZE_SOLVER` by
  `cases/workflows/_skeleton.py`; the plan's record and warnings in
  `run/_plan.py`;
- the selection of a simulation or a point for `plan` and `run`, and the
  message of a second run (FR-326, FR-327): the options in the family
  functions of `run/_cli_parsers.py` (with `resume_hint`, the command that
  continues), the selection in `run/_ids.py` (`narrow_to_selection`,
  `already_recorded_error`), and the `sims` and `points` arguments of
  `plan_matrix` and `run_matrix` in `run/matrix.py`;
- the thin-blade command `pyfs-matrix degenerate` over
  `workspace/_degenerate.py` (FR-330), with its `--boundary` option;
- the five toggle keywords that emitted ENABLE when DISABLE was asked
  (FR-349), now read with the other toggles by `READ_TOGGLES` of
  `script/_settings.py`, with a named parity difference;
- the registration of build 8242026 of 26.124 in the field conventions of
  `post/field_frames.py` (FR-153, RPT-136);
- the actuator-disc profile generator `workspace/actuator_profiles.py` and
  the `profile` command of `pyfs-workspace` (FR-347), and the mesh face
  count (FR-348): counted when the inventory is taken
  (`pyflightstream._fsm.mesh_face_counts`, `obj_face_counts` of
  `workspace/sidecars.py`), read by the post from the inventory
  (`recorded_mesh_faces`, `post/_sim.py`) and written last by the super
  file and the unsteady polar.

## The 0.35.0 additions and their limits

This section records what 0.35.0 changes in the structure above and the limit
each change keeps, measured on the merged tree of the release against v0.34.0
(`reports/RPT-144` and `reports/RPT-145`, from `scripts/arch_metrics.py`). The
tracked package holds 260 modules, of which 24 are absent from the v0.34.0 baseline; the
largest module holds 1.9 percent of the code lines and the number of modules
over 2000 code lines is zero. `workspace_to_run_imports`
is 0 in the record, so the rule that the workspace layer never imports the run
layer holds on the tree, and every new module sits in the row of its package.
The layer guards of NFR-23 and guard G3(b) hold on the merged tree.

### The grouped run path

0.35.0 adds two run modes, `run --polar-sweep` and `run --batch N`, in which
several points are solved in one FlightStream instance (FR-350 to FR-378). The
design keeps the per-point run path unchanged and adds only what surrounds it:

- `run/_grouped.py` is the dispatch and the helpers the grouped modes share:
  the command line chooses between the per-point path and the grouped one
  there and nowhere else, and it reads the plan receipt that gates the run
  (FR-365);
- `run/_batch_split.py` and `run/_batch_plan.py` decide the split of the polars
  into batches and price each job's walltime for `plan --batch` (FR-362 to
  FR-364, FR-378); `run/_batch_run.py` and `run/_batch_exec.py` are the grouped
  run and the two adapters it hands to the per-point campaign loop;
  `run/_batch_collect.py` is the prepare step `collect` runs for the points of
  a grouped job (FR-367 to FR-370, FR-400);
- the job script is built from the same per-point builder output by
  `cases/workflows/_batch_script.py`, and the action programs of one job, one
  counter and one clock for many points, by `cases/workflows/_batch_actions.py`
  (FR-352 to FR-356, FR-359);
- the workspace layer owns what a grouped run writes and reads back:
  `workspace/_batches.py` (the batch layout under
  `sims/batch/<matrix>_b<ID>/`, the grouping receipt and the job entry),
  `workspace/_batch_life.py` (what the other commands do with a batch's folders
  while its job runs, FR-372) and `workspace/_batch_relocate.py` (the copy and
  the move of a batch's points to their simulations, FR-367). They are
  imported by the run layer and import nothing from it.

The limit this keeps: no grouped module writes a record the per-point path
does not write. A point of a grouped job is recorded as a point run alone is,
naming its batch in the submission entry (FR-366), which is what lets every
other command read a collected point unchanged.

### The ledger and the query verbs

The query verbs `status`, `show`, `log`, `trace`, `history` and `diff` (FR-379
to FR-394) read one snapshot and write nothing:

- `workspace/ledger.py` is the public reader: `read_ledger` returns a snapshot
  whose methods return plain dictionaries, and the module offers the same rows
  as functions for a script, with no optional dependency (FR-388);
  `workspace/_ledger_api.py` adapts paths and snapshots to those functions and
  `workspace/_ledger_history.py` holds the archive-aware queries, `history` and
  `diff`, apart from the present-state reader;
- `workspace/_effective.py` is the one home of the rules that choose the
  effective record of a datapoint (FR-381): the run layer and the ledger both
  read it, where the run layer alone held those rules before;
- `workspace/_query_files.py` and `workspace/_query_logs.py` read evidence and
  registers in an ordinary home, a running batch's folder and a compacted
  archive, in place and without expanding anything;
- the command side is `run/_cli_query.py` (`status`), `run/_cli_query_point.py`
  (`show`, `log`, `trace`) and `run/_cli_query_history.py` (`history`, `diff`),
  which only select and render rows; `run/_alias.py` derives the run id alias
  (FR-395).

The limit this keeps: a query takes no lock, writes no file and imports nothing
from a layer above the workspace. A tier-1 test compares the bytes of a
workspace tree before and after each verb (FR-383).

### The cost file

`workspace/costs.py` reads the per-machine cost file `inputs/costs/c<NNN>.toml`
(FR-398). It is a reader and an estimator over plain data: an unknown or
misplaced key is refused by name and a processor count outside the stated
efficiency curve is never extrapolated. The package ships only a synthetic
example, and a guard refuses a tracked cost file that does not say it is
synthetic.

### Other changes of the release

The archive default of `post` is the argument `archive` of
`write_campaign_products`, now false (FR-397). The continuation script no longer
re-initializes a reopened state (FR-396) and a rotor march lists its vorticity
drag boundaries before `START_SOLVER` (FR-318 R6); the parity script names both
differences. The CCS mesh probe judges classify by geometry (FR-401).


## The 0.35.1 sweep validation

- `cases/_sweep_names.py` is private to the cases row. It builds a matrix row's
  sweep and refuses repeated point names (FR-408), importing `cases.SweepAxis`,
  `cases.naming` and the public `cases.workflows.SWEEP_WORD`. It defines the condition
  vocabulary and takes the row error class as a keyword-only parameter from
  `cases.matrix`, with no import back into that module. `cases.matrix` keeps the
  existing helper names; name precision remains defined only by `cases.naming.name_field`.

## The 0.37.0 additions and their limits

0.37.0 adds thirteen modules, each in the row of its package, and no new row.
The order of the stack is unchanged: `post` and `qa`, then `run`, then
`workspace`, then `cases`, then `script` and `results`, then `commands`, then
`versions`, then the floors; the `fsi` side branch keeps its place between the
`script` and `results` row and the `cases` row. `scripts/arch_metrics.py`
measures the release tree, and its record is the release's architecture
record. The two packages that declare an order to guard G3(b) place the new
modules inside it: `cases.workflows` places `_export_first_step` after `_clock`
and `_wake_length` after `_timing`; `run` places `_rebuild_grouped` and
`_mark_converged` after `_rebuild_evidence`, and `_collect_logs` after
`_batch_collect`.

### Recovery: the missing log, grouped rebuild and the person's verdicts

- `workspace/_missing_log.py` is the one rule that names a point whose
  declared outputs other than its solver log are present while its declared
  log is absent, `RAN_MISSING_LOG` (FR-413), and the one statement of what is
  unavailable without the log. It imports `workspace.manifest` alone and sits
  beneath its three callers: `run/collect.py`, `run/_batch_collect.py` and
  `run/_rebuild.py`, which each ask it before any rule that would wait for the
  log or read a job's end files. The post reads only the status they recorded.
- `run/_collect_logs.py` holds the half of `run/collect.py` that resolves the
  log a point is judged by (the scheduler's own log, and a job that ended
  without it), moved out unchanged so the collect stage stays one module under
  the G1 soft limit.
- `run/_rebuild_grouped.py` is what a rebuild reads about a grouped run: the
  batch home of a simulation, the batch its executed script names, and the job
  entry read off the plan receipt (FR-412). It writes nothing and imports
  `run._batch_exec` and `workspace._batches`, both below it.
- `run/_mark_converged.py` is `mark-converged` (FR-414), the twin of
  `mark-failed`: under the manifest lock, `runs.json` archived first, every
  refusal checked again under the lock before anything is written. It also
  registers the two marking commands' parsers, which share their options.
- `workspace/_verdicts.py` is the one inventory of a person's marks, on a
  record and on a steady job's point entries. `workspace/storage.py` (the
  sync) and `run/_rebuild.py` read it, so a later writer never replaces a
  person's verdict with a computed one (FR-414 R4).

The limit this keeps: no writer of `runs.json` gains a second rule for the
missing log or for a mark, and the `workspace` row still imports nothing from
`run`.

### Run length, export windows and pruning

- `cases/workflows/_wake_length.py` is the one conversion of a rotor wake
  length into time steps, `n = ceil(L R Omega / (V_ax dtheta))`, with one rule
  for the axial convection speed. The wake termination of FR-321 and the run
  length of `RUN_WAKE_LENGTH_R` (FR-422) both read it; it lives below the
  clock because the run length is the clock.
- `cases/workflows/_export_first_step.py` resolves the four per-step export
  keys to one first exported step, with their refusals (FR-415);
  `unsteady_export_threshold` calls it before its first emission, and every
  later stage reads the resolved step as it read the after-threshold forms.
- `workspace/_step_prune.py` holds the choice of `keep_last` and
  `delete_steps` with no file system action: the check of a table's keys
  before any file is touched, the split of an export's steps into kept and
  deleted, and the words the record, the console and a later refusal use
  (FR-416). The deleting and the protection of a record's files stay in
  `workspace/storage.py`.

### Products: the settings table and the installed-frame copies

- `post/_settings_product.py` is the caller of the library writer
  `post.settings_table.write_settings_table`: one numeric table per matrix
  from the solver-setup snapshot each record carries, and its codebook
  (FR-419). A point with no snapshot gets no row and one INFO line.
- `post/_installed_copies.py` writes the installed-frame copies of the probes
  table and the reusable inflow profile (FR-420). It holds no classification
  of its own: the one list is `post.inflow_tools.FLIPPED_COLUMNS`, which
  `to_installed_frame` reads too, and the sign flip of a cell is
  `_decimal.negated_text`, below both.

### FlightStream 26.125

- The version registry orders 26.125 after 26.124 with its manual edition, its
  printed release `2612` and its build `10052026`, inheriting no rows; every
  command its manual documents carries a 26.125 row, and the four it stops
  printing answer absent (FR-423). The release's probe campaign
  (`reports/compat/CMP-26125_2026-10-05_probe-campaign.yaml`) verified 141 of
  them on the build and recorded two broken, which the emitter refuses, so the
  build is `operational`. The registry is data in
  `commands/_meta.yaml`, read by `versions`.
- `script/_build_forms.py` writes the one form the target build documents
  where two builds document two forms of one request: the every-boundary
  detections, the wake-edge import token, the CCS curve assignment and the
  solver time averaging. A build that carries the older form keeps it, so a
  script for 26.124 and earlier is byte-identical.
- The readers in `results` accept the 26.125 export titles, footer and loads
  header, and the polar carries the 26.125 drag pair under its own names
  (`CDV`, `CDP`) beside the earlier pair (`CD0`, `CDI`), never one read as the
  other.
- `qa/_spec_26125.py` holds the probe specifications of the twelve commands
  the 26.125 manual documents first, registered into the shared catalog of
  `qa._spec_kit`.

### The FSI side branch: direct mesh morphing

`fsi/_direct_morphing.py` is the structural program's half of direct mesh
morphing (FR-341, route C): with RIGID aerodynamic nodes the solver lists the
undeformed surface vertices at every call, and the module evaluates the beam
solution at each vertex by the rigid-section kinematics the mapped route
encodes at its structural nodes, blending linearly between stations and
holding the end station's motion outside them. It imports only `fsi` modules.
`cases/fsi_workspace.py` refuses every combination the route does not support
(DEFLECTED nodes, `unsteady_rotor`, `steady`, `unsteady`, a wheel, a build
that does not run the command), so an FSI input that does not state
`morphing` renders, stages and hashes as before.

### What the release keeps

A key or pproc entry this release adds, when absent, leaves every script,
record and product byte-identical to 0.36.0. `scripts/check_parity.py` against
v0.36.0 names the three differences the requirements state: the settings table
and its manifest entries (FR-419), the rotor diameter and quasi-steady clock
cells of the super content (FR-89), and the left-out reason of a coupled
steady row (FR-421).

## The 0.38.0 additions and their limits

0.38.0 adds ten modules, each in the row of its package, and no new row. The
order of the stack is unchanged: `post` and `qa`, then `run`, then
`workspace`, then `cases`, then `script` and `results`, then `commands`, then
`versions`, then the floors; the `fsi` side branch keeps its place.
`scripts/arch_metrics.py` measures the release tree, and RPT-161 is the
release's architecture record (292 modules; no import from `workspace` to
`run`). Nine of the ten modules are the private package
`workspace/_refine/`; the tenth is `run/_cli_mesh.py`.

### The refinement package and its layering

`workspace/_refine/` refines, coarsens and audits a panel mesh from its OBJ
(FR-424 to FR-428). It is private: its public names are re-exported by
`pyflightstream.workspace` (`refine_mesh`, `RefinedMesh`, `audit_mesh`,
`MeshAudit`), and nothing outside the package imports its modules. Its modules,
from the floor up:

- `_geometry.py` holds every numerical threshold of the section (the ridge
  angle, the edge-length band, the audit margins and floors, the periodic
  tolerances, the axial band, the band depth and the `schema_version`), each
  defined once and read by every module that uses it, and the primitives the
  others share: edge and face adjacency, boundary loops, dihedral angles, the
  nearest-face order and a nearest-point index in numpy.
- `_obj.py` reads and writes the OBJ and the trailing-edge points file through
  the package's one text route (NFR-32), keeping the source's family order and
  header.
- `_audit.py` is the audit (FR-426): gates, relative checks and figures. It
  imports `_geometry` and `_obj` and nothing of the refinement modules, so it
  judges a level, or any OBJ, without them.
- `_config.py` is the refinement request (FR-424 R1 to R3): the factors of the
  call or of the refinement file, `[components]`, `[periodic]` and the tag.
  Every refusal it raises comes before any family is touched.
- `_grid.py` recovers a family's structured grid from the connectivity and
  resamples it in index space by a cubic spline written in numpy, keeping the
  source's sweep and face starts (FR-424 R6, R7, R9).
- `_remesh.py` remeshes the other families with conforming interfaces (FR-424
  R8, FR-425 R2) and the stretched remesh of a body (FR-428). It alone needs
  the geometry extra, and every import of trimesh and of the spatial index is
  deferred to the call that remeshes.
- `_periodic.py` finds the two cut faces of a sector and matches them node for
  node in the level (FR-427).
- `_level.py` writes a level: grids first, then the bands of unchanged
  neighbours, the cut faces and the remeshed groups, the components, the files
  and the audit (FR-424, FR-425). It imports `_remesh` deferred, inside the step
  that remeshes, so a refinement whose families are all grids never loads it.

The rule this keeps, read by
`test_r14_the_refinement_audit_and_command_import_only_what_the_layering_allows`:
the package imports nothing of `run`; `run` reaches it only through
`refine_mesh` and `audit_mesh` of `pyflightstream.workspace`; `_audit.py`
imports none of `_config`, `_grid`, `_remesh`, `_periodic` and `_level`.
Neither the grid path nor the audit imports scipy or rtree, at module level or
deferred (FR-424 R10): the spline and the nearest-point search are numpy, so a
base install refines a mesh whose families are all grids and audits any mesh.

### The two verbs

`run/_cli_mesh.py` registers `pyfs-matrix refine` and `pyfs-matrix
audit-mesh`. Each parser names its handler as the `mesh_command` default, so
`run/cli.py` dispatches them with the geometry commands without importing the
module's handlers by name, and the handlers call the public functions with the
caller's arguments: the command and a Python caller run the same code and
refuse with the same text. The module holds the console contract of FR-426 R1
(exit 0, 1 and 2) and nothing of the geometry. `pyfs-matrix degenerate` calls
`pyflightstream.workspace.derive_thin_blade`, now public (FR-429), in place of
its earlier deferred import of the private module.

### What 0.38.0 keeps

No key, script, record or product of 0.37.0 changes. The new verbs need no
executable, no matrix and no workspace: they read the OBJ they are given and
write a level folder beside it, never into the source's folder.
