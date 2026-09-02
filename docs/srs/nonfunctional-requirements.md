# Non-functional requirements

!!! requirement "NFR-01 Didactic policy <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-04. Split into four singular claims 2026-07-27, each
    with its own identifier, so each can be falsified on its own; this
    box is the umbrella and adds nothing the four do not say.*

    The package is didactic by construction: NFR-01a to NFR-01d state
    what that means in four claims.

!!! requirement "NFR-01a Docstrings carry units and frames <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of NFR-01, accepted 2026-07-27. Evidence:
    the numpydoc convention enforced by ruff (NFR-09) for the docstring
    STRUCTURE, and the unit-suffix audit of
    `tests/test_conventions.py` for model fields. That units and frames
    are actually stated in the prose of every public function is
    checked by review, because the tools check shape and not meaning,
    and this tag says so rather than letting the badge imply a guard.*

    Every public function has a numpydoc docstring stating units and
    reference frames.

!!! requirement "NFR-01b Modules state their pipeline role <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of NFR-01, accepted 2026-07-27. Evidence:
    `tests/test_package_imports.py`, which asserts a non-empty top
    docstring on every subpackage, and the architecture overview, which
    renders them. What is guarded is that the docstring EXISTS at
    subpackage level; that its text states a pipeline role, for every
    one of the modules below that level, is a review check.*

    Every module's top docstring states its role in the pipeline.

!!! requirement "NFR-01c Errors name the cause, not the symptom <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of NFR-01, accepted 2026-07-27, absorbing
    the C3 acceptance on error content. Evidence:
    `tests/test_error_messages.py` and the attribute cases of
    `tests/test_exceptions_catalog.py`, which pin a named list of
    errors rather than enumerating every raise site. The list is the
    guard's scope, in the manner NFR-24 states for its own.*

    Every raised error names the physical or version cause rather than
    the internal symptom, identifies the object or version involved and
    the operation attempted, states a suggested fix where a remedy is
    known, and carries the machine-readable attributes a caller needs
    to recover.

!!! requirement "NFR-01d Worked examples per workflow <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of NFR-01, accepted 2026-07-27. Evidence:
    `tests/test_examples.py` runs each of the `examples/*.py` and holds
    each to the extras it declares; the Sybil run covers the docstring
    doctests and the markdown code blocks. Nothing enumerates the public
    workflows and checks one example per workflow, so the per-workflow
    coverage is a review check and the badge covers the examples'
    correctness.*

    The published docs include at least one worked example per public
    workflow.

    Evidence line corrected 2026-08-03 (review finding PYFS-026). It
    said the executable examples ran in CI under Sybil, and Sybil runs
    docstring doctests and markdown code blocks: the four
    `examples/*.py` were in no CI step at all, so the badge rested on a
    mechanism that did not cover them. They are the first code a new
    user runs.

    Paragraph order corrected 2026-08-03 (tech-writer pass). The note
    above sat before the statement, and the index generator publishes
    the first non-italic paragraph as the requirement text, so the
    external dashboard received this correction note as NFR-01d's
    mandatory requirement and the actual statement was published
    nowhere.

!!! requirement "NFR-02 Licensing <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-02, BRF-10.*

    MIT license; no AGPL-derived code; dependency licenses must be
    clearly MIT-compatible, with committed license-evidence cards
    before adoption (RPT-002, RPT-003, RPT-008 are the precedents).

!!! requirement "NFR-03 Licensed-content policy <span class='srs-implemented'>implemented</span>"
    The repository never reproduces FlightStream manual text,
    screenshots, or example blocks. Manual facts appear only as
    paraphrases with page citations. The manual itself never enters
    the repository; repository guards reject pdf files.

!!! requirement "NFR-04 Version-support promise <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-07.*

    Supported FlightStream versions are only added, never dropped.
    The package version follows SemVer, decoupled from FlightStream
    version numbers; while the package is at 0.x, the API is
    unstable by SemVer's own rule.

!!! requirement "NFR-05 Platforms <span class='srs-implemented'>implemented</span>"
    Windows is the primary execution target (FlightStream runs on
    Windows); the package itself is pure Python >= 3.11 and passes CI
    on Linux AND on Windows, at both declared Python bounds. HPC
    submission stays a deferred executor (FR-15).

    The Windows leg was added 2026-08-02 (review finding PYFS-024) and
    the gap it closes is worth naming: this requirement said Windows
    was the primary target and CI ran on Linux alone, so the platform
    the package exists to serve was the one platform nothing tested. A
    Windows-only break could have reached a user with every check
    green.

    The floor is stated here; the UPPER bound is governed by NFR-22
    rule 3, which narrows it when a core dependency declares one. Said
    explicitly so the migration commit has one place to look rather
    than two statements to reconcile.

!!! requirement "NFR-06 Minimal public dependencies <span class='srs-implemented'>implemented</span>"
    *Origin: PP-9. Runtime set restated 2026-07-27 under AD-06 and
    AD-07.*

    Runtime dependencies form a minimal, public, permissively licensed
    set; heavier needs live behind optional extras; no private or
    absolute-path dependencies, ever. The standing engineering policy
    prefers existing public libraries over in-house code for generic
    needs.

    This requirement is the single home OF RECORD for the set and for
    the release that changes it, so it names both the shipped set and
    the one it is moving to:

    | Today | From the migration release |
    |---|---|
    | numpy, pandas, pydantic, PyYAML, trimesh, xarray | numpy, itaca, pydantic, PyYAML, trimesh |

    pandas and xarray leave and ITACA arrives as one move, not per
    structure (AD-06, AD-07). Reading the right-hand column as already
    true is the error this table exists to prevent; `pyproject.toml`
    carries the left-hand column today and the migration commit moves
    it.

    **AMENDED AT v0.8.0, AND THE COUNT GREW.** This requirement said
    "the count does not grow: five becomes four", and v0.8.0 makes it
    six becoming five, because `trimesh` was promoted out of the
    `[geom]` extra into the runtime set. The amendment is recorded here
    rather than only in the decision note, because this table calls
    itself the home OF RECORD and a runtime-dependency change whose
    reason lives nowhere public is the failure the phrase exists to
    prevent.

    The reason: extracting a trailing edge from a blade mesh is on the
    DEFAULT PATH of a rotor campaign, and a capability gated behind an
    extra makes the library promise what a default install cannot do.
    The cost was measured rather than estimated and is the smallest a
    new runtime dependency has been asked to be: ONE new distribution
    and 3.89 MiB, whose only hard dependency is `numpy`, which this
    package already requires (`reports/RPT-034`). Its licence is
    MIT-compatible under NFR-02 with the evidence card committed
    (`reports/RPT-035`). The candidates that were refused are recorded
    with it: `meshio` on that same weight budget, at five new
    distributions and 12.26 MiB against limits of one and five;
    `numpy-stl` on capability; an in-house reader on the standing
    engineering policy.

    What did NOT change is the rule this requirement is about. A
    heavier need still lives behind an extra: `[geom]` keeps the
    SPATIAL INDEX, `rtree` and `scipy`, because containment culling is
    an optional capability where reading a mesh is not.

    A tier-1 guard now compares this table against
    `[project].dependencies` name for name
    (`tests/test_extras.py`), because until v0.8.0 nothing did, and
    that is why the promotion reached `pyproject.toml`, the extras
    module, three documentation pages and the changelog without ever
    reaching the requirement that answers for it.

    Two satellites restate the set for their own readers and are not
    generated from this table, so they move with the migration commit
    rather than on their own: `pyproject.toml`, which is the machine
    authority, and the user guide, which is refreshed per release. Home
    of record means this table is what they are checked against, not
    that no other copy exists.

    The removal release NUMBER is deliberately unset here as of 2026-08-09: v0.5.0 shipped without the migration, so naming it would repeat the error this table exists to prevent. The author sets the number when ITACA's `pproc/` and `aerospace/` halves are ready (PLN-20260809-0210). Other
    pages print the number rather than sending a reader two documents
    deep for it, and cite this requirement as the home the number is
    checked against.

!!! requirement "NFR-07 Reproducibility <span class='srs-implemented'>implemented</span>"
    *Origin: PP-6.*

    A run's INPUTS and invocation are reproducible from its manifest
    entry together with the workspace artifacts the entry identifies:
    input hashes, versions, the solver-setup snapshot, the recorded
    argv, and the staged script reconstruct the exact call. The entry
    alone IDENTIFIES and VERIFIES those artifacts, by hash, and states
    when one is missing or has changed; it does not carry their
    content. Publications cite run ids.

    Narrowed 2026-08-03 (REV010-013), from "reproducible from its
    manifest entry alone". `RunRecord` stores hashes and paths rather
    than content, and `reconstruct()` requires the workspace and
    refuses when the staged script is absent, which a test pins
    deliberately. The implementation was sound under a "manifest plus
    preserved artifacts" contract while this sentence promised a
    self-contained evidence object, so the requirement moved to the
    contract that is actually kept. Storing or archiving enough
    canonical content for entry-alone reconstruction remains a
    possible future capability; it is not what is delivered, and the
    requirement no longer says it is.

    Reproducibility of the solver's numerical results is bounded by the
    FlightStream determinism boundary and is not asserted here.
    Reworded 2026-07-27, because the original promised something this
    package cannot deliver and does not control: the same inputs on the
    same build reproduce, and that is a property of the solver, which
    this repository has measured but does not own. Promising it here
    would have made a vendor change look like a defect in this package.

    The provenance model behind it is the static-origin and
    operation-log split the manifest already implements. A standardized
    interoperability export of that provenance was proposed with it and
    the author deferred that half, so it is a candidate rather than a
    promise.

!!! requirement "NFR-08 Confidentiality <span class='srs-implemented'>implemented</span>"
    No employer or third-party proprietary content, no proprietary
    geometry, no research-specific aircraft data ever enter the
    repository. Synthetic geometry only in tests and examples; local
    research cases contribute only aggregated coefficients to
    committed reports.

    Aggregated is defined rather than left to judgment, accepted
    2026-07-27: integrated force and moment coefficients and their
    sweep-indexed scalars, and never a per-panel or per-node field from
    which a geometry or a pressure distribution could be reconstructed.
    The line matters because the two are the same numbers at different
    resolutions, and only the second leaks the shape.

!!! requirement "NFR-09 Style <span class='srs-implemented'>implemented</span>"
    ruff for lint and format; numpydoc convention; naming checks
    exempted for standard aerodynamic symbols (CL, CDi, J, CT). House
    style forbids em and en dash characters in Markdown and
    docstrings, enforced by a Tier 1 test.

!!! requirement "NFR-10 English naming <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-14.*

    Every folder, file, module, function, and identifier in the
    repository is in English.

!!! requirement "NFR-11 Documentation currency <span class='srs-implemented'>implemented</span>"
    *Origin: the 2026-07-22 staleness audit, which found the public
    documentation frozen at earlier milestones while the code moved.
    Evidence: the process rules below plus the consistency guard
    test.*

    Documentation may never drift silently from the code. The
    mechanisms, in force from 2026-07-22:

    - Single home per fact: any fact presented in more than one place
      is generated from one source or stated once and linked. Version
      strings live in single sources; a Tier 1 test asserts the
      version-bearing metadata files agree. Where a copy can be neither
      generated nor replaced by a link, because it is machine metadata
      or release-refreshed material, one statement is the declared HOME
      OF RECORD and the copies are checked against it rather than left
      to agree by habit (NFR-06's dependency table is the instance).
    - Documentation changes ride with the code change that makes them
      true: a session that changes the public surface updates the
      changelog's Unreleased section and the affected public pages in
      the same session, as part of the definition of done.
    - The changelog follows Keep a Changelog: the Unreleased section
      always exists (test-enforced) and is promoted, never rewritten,
      at release.
    - The docs build runs with warnings as errors in CI.
    - A periodic audit (the `audit` maintenance skill) retrospectively
      sweeps the repository for staleness, checks it against the
      external guides adopted in [standards](standards.md), and turns
      every finding into an update or a deletion, never a
      leave-for-later.

!!! requirement "NFR-12 Citation and archival <span class='srs-implemented'>implemented</span>"
    *Origin: the v0.2.0 public release.*

    Every public release carries citation metadata: CITATION.cff is
    validated and its version and date match the tag before tagging
    (release-skill pause point), and the GitHub release is archived
    with a DOI. The citation file is the single home of the citation
    facts.

!!! requirement "NFR-13 Traceability closure <span class='srs-pending'>pending</span>"
    *Origin: Phase 4 review theme 1, accepted 2026-07-27, absorbing the
    T3 traceability acceptance and the TRC-01 marker convention, which
    is the mechanism this requirement asserts.*

    A Tier 1 test asserts requirement-to-test closure: every
    requirement whose status is not pending resolves to at least one
    marked falsifying test, and every requirement marker resolves to an
    identifier defined in the SRS. Each Tier 1 test that falsifies a
    requirement declares that requirement's identifier in a
    machine-readable marker.

    Pending, and the gap it measures is the reason it exists. The code
    is tested; what is thin is the chain that lets a requirement prove
    itself by a cited test. `reports/requirements-index.json` publishes
    the current numbers so the gap is visible rather than asserted, and
    NFR-13 is what turns them into a gate.


    Partly delivered 2026-08-03 (review finding PYFS-020) and still
    pending, because the closure this requirement names is not reached.
    What landed: the published index now carries `status`, `evidence`
    and a `verification` method per requirement, where it published id,
    text and priority alone; a `requirement` pytest marker declares
    that a test FALSIFIES a requirement; and `tests/test_traceability.py`
    holds every marker to a live identifier and ratchets the covered
    set so it cannot shrink by accident.

    Why it stays pending rather than moving: 99 requirements exist and
    the marked set is a fraction of them. Marking a requirement on a
    test that does not actually falsify it would be worse than leaving
    it unmarked, because the index would then count a trace that is not
    one, so the set grows by hand, one verified pair per commit.
!!! requirement "NFR-14 Confidentiality commit guard <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review, accepted 2026-07-27. Evidence: PFS-3
    (2026-08-02);
    `tests/test_house_style.py::test_no_geometry_file_is_tracked_outside_the_synthetic_allowlist`
    walks every tracked path and fails on a geometry suffix outside the
    allowlist, with
    `test_the_geometry_guard_fires_on_what_it_exists_to_catch` as its
    mutation proof; the `forbid-geometry` pre-commit hook refuses the
    same class at commit time.*

    A Tier 1 guard rejects the commit of any file whose extension is in
    the known geometry or mesh set unless its path is in the
    synthetic-fixtures allowlist.

    This extends the pdf-rejection pattern NFR-03 already uses to the
    class NFR-08 forbids, which was until PFS-3 enforced by discipline
    rather than by a guard. Under this repository's own structural-fix
    rule that difference is exactly the kind that eventually costs an
    incident.

    Measured before the guard existed, on a real case rather than in the
    abstract: a 37 kB mesh added under `examples/` and staged passed the
    entire tier-1 suite and the CI guard job, which looks only for pdf,
    notebook and `_private/` paths. The suffix set is derived from
    `IMPORT`'s `file_type` enum in the command database, plus the saved
    simulation `.fsm`, plus the CAD interchange formats research
    geometry arrives in.

    Scope stated as a residual, not as a guarantee: the guard keys on
    EXTENSION, which is what this requirement asks for and which cannot
    see geometry carried in a generic container. A node coordinate list
    in a `.csv` is invisible to it, and one is tracked
    (`tests/fixtures/fsi/structural_nodes.csv`). NFR-08 is the wider
    requirement and stays a discipline for that residual. The guard also
    walks the TREE, not the built wheel. The tool that can also read the
    ARTIFACT side, `tools/check_shipped_surface.py`, has its tree
    boundary wired in tier 1 by `tests/test_repository_guards.py`; its
    `--dist` boundary over a built wheel and sdist is not, because that
    needs a build in the loop and two archive floors, recorded in
    `tools/shipped_surface.conf`. Note the scope difference rather than
    reading it as coverage of this requirement: that tool judges personal
    and institutional IDENTIFIERS, and NFR-14 is about geometry
    suffixes. No artifact-side check for geometry exists in either
    repository today.

!!! requirement "NFR-15 Manifest hash canonicalization <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review, accepted 2026-07-27, absorbing the M3b
    state-hash mirror. Statement rewritten 2026-08-19 (PFS-2012.10),
    the author's decision. Evidence: `pyflightstream._digest`, which
    carries `ALGORITHM`, `EXCLUDED_FROM_EVERY_DIGEST` and
    `CANONICAL_FORMS` as data; `tests/test_digest.py`, including the
    walk that fails a module hashing without declaring its canonical
    form.*

    Every digest this package writes is sha256, and the canonical form
    it is taken over is stated per kind rather than implied. A FILE
    digest (a staged input, a collected output, the written script, the
    solver executable) is taken over the file's raw bytes. A TEXT digest
    (the rendered script text, the recipe source) is taken over the
    UTF-8 encoding of that text. No wall-clock timestamp, elapsed time,
    absolute path, machine name or staging order enters any of them, so
    two runs with identical inputs produce identical digests.

    The two kinds are distinguished because they answer different
    questions and a file checked out with different line endings is a
    different file while the same text is the same text. The
    determinism this promises is bounded to one platform and one set of
    library versions, and that boundary is stated rather than implied.

    Implemented rather than pending since the rule is data in
    `_digest` rather than prose about it, which is what makes a
    volatile field entering a digest a tier-1 failure rather than a
    thing nobody would notice.

!!! requirement "NFR-16 Test-coverage floor <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review, accepted 2026-07-27, absorbing the M5
    coverage mirror. Measured for the first time 2026-08-02 (session
    PFS-B1, review finding PYFS-024). Evidence:
    `[tool.coverage.report] fail_under` in `pyproject.toml`; the
    `coverage` job of `.github/workflows/ci.yml`.*

    The Tier 1 suite holds STATEMENT and BRANCH coverage at or above a
    stated floor, set against measured coverage rather than aspiration,
    and CI fails when either falls below it.

    The number is deliberately NOT written here. It lives in
    `pyproject.toml`, where the tool that enforces it reads it, so
    raising the floor is one edit in one place rather than a number in
    two homes drifting apart. This requirement states the rule; the
    build states the value.

    Two things about how the floor is set, because a floor set wrongly
    is worse than none. It is set BELOW the first measurement, with
    margin, so it is a ratchet against regression rather than a target
    to be gamed: the measurement is the fact and the floor is the
    promise. And it is enforced on ONE CI leg rather than on all four,
    because coverage is a property of the test suite and four
    measurements would be four numbers to reconcile with one floor.

!!! requirement "NFR-17 One float-comparison convention <span class='srs-pending'>pending</span>"
    *Origin: Phase 4 review, accepted 2026-07-27.*

    The repository defines one float-comparison convention, a named
    helper with default absolute and relative tolerances, and every
    numerical-equivalence assertion references it rather than an ad hoc
    literal.

!!! requirement "NFR-18 Manifest schema version <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review, accepted 2026-07-27.*

    The `runs.json` manifest records a manifest schema version, and
    manifest keys are added, renamed, or removed only under the
    deprecation policy of NFR-20, so a run cited in a publication stays
    readable across package versions.

    `RunRecord.manifest_schema` carries it, `workspace.MANIFEST_SCHEMA`
    names the current value, and `reconstruct()` refuses a row written
    under a schema this version does not know. A row that carries no
    schema predates the field, is represented as `None` rather than
    defaulted to the current value, and is refused rather than
    reconstructed (REV010-014).

    Status corrected 2026-08-03 (REV010-017). This said "pending, and
    the manifest carries no version field today" while the field had
    been live since `c7cfdad`, so the requirement understated what the
    package delivers, in a document whose whole job is to say what it
    delivers. The direction is unusual and worth noting: the surfaces
    this review corrected mostly claimed MORE than the code did.

    Note the dependency on NFR-20's window: before 1.0 that policy does
    not bind, so what protects a cited run until then is this
    requirement's own promise plus the changelog, not the policy.

!!! requirement "NFR-21 Support and compatibility window <span class='srs-pending'>pending</span>"
    *Origin: Phase 4 review, accepted 2026-07-27.*

    Each release states the range of FlightStream versions and the
    range of Python versions it supports, and a supported version
    leaves that range only after a release that announces the removal.

    The FlightStream half is already promised more strongly by NFR-04,
    which never drops a supported solver version. What this adds is the
    Python half and the announcement, and it is the requirement NFR-22
    rule 3 will act on when a core dependency's ceiling narrows the
    range.

!!! requirement "NFR-19 Result column-schema stability <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review theme 5, accepted 2026-07-27. Evidence:
    the column schemas documented in the docstrings of
    `results/tables.py`; `tests/test_tables.py` pins the run row's
    COMPLETE column list against a literal, so a column added or
    reordered in the middle fails the suite rather than passing the
    per-name lookups.*

    Every table the results layer produces exposes a documented column
    schema. Where this requirement additionally promises STABILITY, in
    the scope stated below, a change to that schema is announced in the
    changelog's API surface delta, and from 1.0 a column is renamed or
    removed only under NFR-20. Documentation is universal; the
    stability promise is not, and separating the two is what lets the
    exclusion below be an exclusion from a promise rather than from the
    docs.

    Deliberately written without naming a substrate
    ([glossary](index.md#glossary)), because the substrate changes at
    v0.5.0 (AD-06, with NFR-06 as the home of that release number) and
    the promise does not. Users build downstream
    analysis on these column names, which makes them a public contract
    whichever library holds the values.

    Three boundaries, because a contract that does not state its edges
    is read wider than it is meant:

    - It covers the column NAMES and their units, not their ORDER.
    - It covers the tables this package composes: the per-run row, the
      sweep table, the parsed loads and residual tables, and the
      sectional-loads table of the `[fsi]` extra, whose unit-suffixed
      names (`offset_m`, `fx_n_per_m`, `moment_qc_nm_per_m` and the
      rest) this package invents from the solver's printed header
      rather than copying.
    - The probe-point table is documented like the others and is NOT
      covered by the stability promise, because its columns ARE the
      solver's own printed header. This package reports what the solver
      prints and cannot promise a vendor's column set will not move.

    Where the schema is documented, decided 2026-07-27 rather than left
    as an open half. It lives in the docstrings of `results/tables.py`.
    The only other copy is the deliberate literal in the test named
    above, which exists precisely so a schema change costs two files. The docs site publishes no Python API reference
    and will not gain one for this requirement's sake (mkdocstrings was
    evaluated and declined at v0.3.0), so a reader who wants the exact
    column set opens that module. The cost is stated rather than
    softened, because this SRS declares a readership that does not read
    source by preference: the honest form of the promise is that
    `overview()` and the Architecture page carry the narrative, both
    rendering the same module docstrings, the changelog carries the
    announcement, and the module carries the list. Not `help()`, which
    renders the FlightStream command reference and says nothing about
    result tables.

!!! requirement "NFR-20 API deprecation and removal policy <span class='srs-pending'>pending</span>"
    *Origin: Phase 4 review theme 5; the window decided by the author
    2026-07-27 and recorded in the [revision history](index.md).
    Pending because the policy it states begins at 1.0 and the package
    is at 0.x; the recorded-promise mechanism it relies on is already
    shipped and guarded (the ledger in `pyflightstream._deprecations`
    and the Tier 1 deadline guard `tests/test_deprecation_deadline.py`).*

    **This policy takes effect at 1.0.** From 1.0, a public API element
    (function, parameter, CLI flag, manifest key, or result column) is
    removed only after the warning has shipped in at least one
    released minor version, naming the replacement and the removal
    version, and is still present in the last release before the
    removal; the removal itself lands in a MAJOR release. Stated as
    releases rather than as "one full minor" because the latter has no
    meaning when a major follows a minor directly. Naming the
    removal release is not a detail: a policy that says only "after a
    warning" permits deleting public API in a minor, which NFR-04's
    SemVer commitment forbids, and this requirement exists to stop a
    reader having to reconcile the two.

    Before 1.0 it does not apply, and this requirement says so in its
    own text rather than leaving that reconciliation to the reader.
    While the package is at 0.x the API is unstable by SemVer's own
    rule, so a public element may be renamed or removed with no warning
    release before it. It is announced in the changelog: under
    Deprecated when it is notice of a future release, and in the API
    surface delta of the release that lands it.
    Two bounds on that, so a 0.x user can still write a version
    specifier: a break lands only in a MINOR release (0.N.0), and a
    patch release never changes the public surface. Both bounds are the
    author's decision of 2026-07-27, taken on the API-design review's
    proposal and knowing that the package has never shipped a patch
    release, so they state intent rather than describe history.

    Consequences the author accepted knowingly, among them: v0.5.0
    removes the tidy table with no exit path; v0.4.0 renames
    `to_dataframe`, `run_frame` and `sweep_frame` directly (the
    2026-07-23 answer that had put a deprecation cycle on the last two
    is superseded); and v0.4.0 also converts optional parameters of the
    tabular layer to keyword-only, which is a public PARAMETER breaking
    in a minor with no warning release, the same posture applied to the
    element kind this requirement names second. A declared posture is
    not the same as a warned user.

    Both landed on 2026-08-03, unchanged from the announcement: the
    three names are `to_table`, `run_table` and `sweep_table`, the
    optional parameters of those and of `parse_run_loads` are
    keyword-only, and `plan_campaign` joined the same window for the
    same reason. Recorded here rather than left as intent, because a
    consequence that stays in the future tense after it happens is the
    drift the SRS guard exists to catch.

    A promise ALREADY recorded is kept regardless of version. Every live
    MODULE shim ([glossary](index.md#glossary)) is an entry in the
    deprecation ledger naming its removal version, and the Tier 1
    deadline guard fails the suite the moment the package version
    reaches that removal version with the shim still importable.

    That enforcement is narrower than this requirement's scope and the
    difference is stated rather than implied. The ledger models modules
    and nothing else, so a deprecated parameter, CLI flag, manifest key
    or column has no representable entry and no deadline a test can
    check. Those four are policy-only until the ledger grows an entry
    type for them.

!!! requirement "NFR-22 Dependency version envelope <span class='srs-pending'>pending</span>"
    *Origin: Phase 4 review theme 3 plus the numerical seat, accepted
    2026-07-27; the pre-1.0 pin form and the ceiling rule added the same
    day, covering dependency metadata that no requirement reached.*

    This requirement is the single home of how dependency versions are
    declared. Three rules:

    1. **Tested range per dependency.** Each runtime dependency
       declares a tested version range, and CI runs the Tier 1 suite at
       the declared lower and upper bound of each range. An unbounded
       range silently widens the reproducibility surface NFR-07 rests
       on.
    2. **Pre-1.0 dependencies pin to the current minor.** A core
       dependency below 1.0 makes no compatibility promise, by SemVer's
       own rule, so it is pinned in the form `>=X.Y,<X.(Y+1)`. ITACA at
       0.1 is the first such dependency and takes `>=0.1,<0.2`. The
       maintenance cost is one deliberate edit per sister minor, which
       is the point: a sister release becomes a reviewed change here
       instead of an install-time surprise. The USER's cost is the
       larger one, and the install documentation gains it in the same
       commit that creates the dependency: while this package is
       installed, ITACA cannot be upgraded past the pinned minor in the
       same environment, and a third package requiring a later ITACA
       cannot be co-installed.
       ITACA is a general-purpose library this project encourages its
       users to adopt on its own, so that constraint is theirs, not
       only ours.
    3. **A core dependency's Python ceiling propagates.** This
       package's `requires-python` is never wider than any core
       dependency's. ITACA declares `>=3.11,<3.14`, so taking it as a
       core dependency narrows this package from `>=3.11` to
       `>=3.11,<3.14`. Leaving ours open would keep the metadata
       claiming 3.14 works while the resolver proves it does not. The
       narrowing is not metadata alone: NFR-05, the README install
       section and the `pyproject.toml` classifiers state the supported
       Python versions to a reader, and they move in the same commit.

    Pending, and honest about what is missing: no runtime dependency
    declares a range today, no CI leg runs at a bound, `pyproject.toml`
    still carries neither ITACA nor a ceiling, and neither the README
    nor the docs site yet carries the co-installation sentence rule 2
    promises. Rules 2
    and 3 land in the same commit that creates the dependency, which is
    the migration commit, not before it; rule 1 is independent of that
    commit and is scheduled separately, since nothing forces it and an
    accepted rule with no landing point is how a requirement becomes
    decoration.

    NFR-02's license-evidence card for ITACA is committed with that same
    migration commit. A core dependency adopted without one would breach
    a requirement this batch did not touch.

!!! requirement "NFR-23 Layering guard <span class='srs-pending'>pending</span>"
    *Origin: the ITACA mirror review (item M2), accepted 2026-07-27 as
    a new requirement rather than a mirror.*

    A Tier 1 mechanism enforces AD-01: a module that imports from a
    layer above its own fails the suite, rather than being caught by
    review.

    What this is NOT, since the item arrived as a candidate mirror of
    the sister's REQ-82 and its rationale has since been rewritten. The
    sister uses a lint rule to forbid pandas and xarray in its
    NumPy-only core. Only the MECHANISM is borrowed. The original
    rationale said this package enforces "the opposite policy", and
    after AD-06 the two dependency policies are no longer opposite,
    which retires that framing entirely. The requirement survives it
    because what it guards is downward layering, which is this
    package's own rule, has never been the sister's, and has nothing to
    do with which array library either package uses.

!!! requirement "NFR-24 Software jargon glossed <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 review theme 7 (item TERM-software-jargon),
    accepted 2026-07-27. Evidence: the glossary in
    [the SRS index](index.md), pinned by
    `tests/test_metadata_currency.py`.*

    Each software term on this requirement's list (clean-room, golden,
    round-trip, escape hatch, tidy table, shim, substrate,
    `shell=True`) has a glossary entry and is glossed at its first use
    in the SRS. The list is the authority: a chapter that introduces a
    new software term adds it here, and the guard follows.

    The audience this SRS declares is not a software audience, which
    makes undefined software jargon a clarity defect rather than a
    style preference. Scoped to a list rather than to "every software
    term" because the list is what a test can check, and a requirement
    whose universal claim its own guard cannot see is worse than a
    narrow one that holds: the two terms added when this batch
    introduced them, shim and substrate, are the evidence that a
    universal wording drifts on the day it is written.

    The glossary half is guarded: a Tier 1 test parses this list out of
    the requirement itself, so naming a term here without adding its
    row fails, as does emptying a row a listed term relies on. The
    glossed-at-first-use half is a documentation review check, because
    no cheap test distinguishes a first use from a later one.

!!! requirement "NFR-25 Optional-dependency error shape <span class='srs-implemented'>implemented</span>"
    *Origin: the C9 acceptance and the M6 mirror of the same subject,
    2026-07-27, which the author accepted as elevating AD-05 to a
    tested requirement. Evidence:
    `pyflightstream.extras.MissingExtraError` and `missing_extra`;
    `tests/test_extras.py`, parametrized over every extra;
    `tests/test_extras_isolation.py` and the `test-all-extras` job in
    `ci.yml`, added 2026-08-10 for the residual below.*

    A missing optional dependency raises a typed error carrying the
    exact `pip install pyflightstream[<extra>]` remedy, never a bare
    ImportError.

    This is AD-05's promise made falsifiable, which is what the
    acceptance asked for: a decision states an intent, and only a
    requirement with a test behind it can be broken visibly.

    Implemented 2026-08-03 (review finding PYFS-025). What it was
    pending on, stated here because the shape of the fix is the
    interesting part: three sites raised three different types, one a
    package type and two stdlib errors, each with its own hand-written
    remedy string, and no test exercised the missing-extra path at all.
    There is one type now, and the remedy is COMPOSED from the extra's
    name rather than written, so a message cannot name an extra that
    does not exist. A tier 1 test asserts the shape per extra, and an
    AST guard refuses any raise that writes the remedy by hand.

    One residual, stated rather than left: the missing-extra paths are
    verified by construction and by source, not by uninstalling the
    extras, because the suite runs with them installed. What that
    leaves unverified is the import machinery of each gate, not the
    shape of its refusal.

    That residual came due on 2026-08-10, and the correction belongs
    here rather than in a commit message. The gap was wider than the
    sentence above admits, because no environment carried every extra
    and nothing said so: every install line in all three workflows named
    the same three of the five extras, and a test importing one of the
    other two passed on every maintainer machine and failed in CI. It
    reached the v0.7.0 tag (INC-20260810-2140-shared).

    Two things closed it. `tests/test_extras_isolation.py` derives, from
    pyproject and the workflow install lines, which distributions a CI
    job may lack, and refuses an unguarded import of one in `src/`,
    `tests/`, `examples/`, `scripts/`, `tools/`, the root conftest, the
    doctests inside all of those, and the executable fenced blocks of the
    README and the docs pages. And the
    `test-all-extras` job in `ci.yml` installs all five, so the gated
    assertions execute somewhere rather than skipping everywhere.

    Three residuals survive, narrowed. The refusal SHAPE is still
    verified statically rather than by absence: no job runs with an extra
    deliberately uninstalled. The scan does not reach an import made
    through a console script, an entry point, a pytest plugin, or
    `import_module` with a computed argument. And, from 2026-08-11,
    import roots are resolved from installed metadata, so a
    distribution's non-obvious import names join the forbidden set only
    on a leg that HAS the distribution: the guard degrades to the bare
    distribution name on the lean legs, which are the ones it most
    protects, rather than to nothing.

!!! requirement "NFR-26 One term per level for the unit of work <span class='srs-pending'>pending</span>"
    *Origin: the TERM-unit-of-work acceptance, 2026-07-27, allocated an
    identifier by this consolidation.*

    The unit of work is named SIM at the case level and datapoint at
    the execution level throughout the SRS and the docs, and every other
    term for it is either replaced or given a glossary entry mapping it
    to one of those two.

    Pending, and the honest reason is that the alternatives are still in
    use: case, simulation, run, point and sweep point all appear, some
    of them correctly in their own register. Sorting which are synonyms
    to replace and which are distinct concepts to gloss is the work this
    requirement names, and it is the sibling of NFR-24 for the domain
    vocabulary rather than the software one.

!!! requirement "NFR-27 Static type checking of the package <span class='srs-implemented'>implemented</span>"
    *Origin: the independent review's finding PYFS-026, 2026-08-03.
    Evidence: `[tool.mypy]` in `pyproject.toml`; the `types` job of
    `.github/workflows/ci.yml`.*

    A static type checker runs over the whole package in CI, and the
    modules it does not yet pass are exempted BY NAME rather than by a
    blanket setting, so the exemption list is the debt and shrinks.

    A ratchet rather than a clean adoption, and the measurement is why:
    the first run reported 223 errors in 21 of 53 modules. A blanket
    adoption would have meant either 223 rushed annotations or a
    permanently red check, and both teach a reader to ignore the check.
    Exempting by name means a new module, or a clean one that goes
    dirty, fails today, while the 21 are cleared on their own schedule.

    `py.typed` is deliberately NOT shipped and this requirement does not
    ask for it. Shipping it tells every downstream type checker to trust
    these annotations, and 223 errors say they are not trustworthy yet;
    a wrong annotation trusted by a consumer's checker is worse than no
    annotation, because it produces a confident false positive in
    somebody else's build. PEP 561 is promised nowhere in this
    repository, so nothing is broken by the absence. It ships when the
    exemption list is empty, and the promise joins this requirement
    then rather than now.

!!! requirement "NFR-28 A shipped workspace reads as a set-up, not as a diary <span class='srs-pending'>pending</span>"
    *Origin: the author's item #0 of 2026-09-02, "tratar como um teste
    simples sem comentarios de historico". Carried by PFS-2029.13.
    Evidence owed: the checker that node names.*

    Every comment in a workspace artifact this repository ships or
    reproduces from is one a person setting up a run needs to set up the
    run: what a value means, its unit, or why it is what it is when the
    reason is not recoverable from the number. No comment records what a
    value used to be called, what an earlier release did, or addresses
    the reader; history belongs to version control. An open question
    found inside an artifact moves to where open questions live before
    its comment is deleted.

    Measured 2026-09-02 in the 0.10.1 reproduction workspace: 189 of 301
    lines across five artifacts are comments, and the reference artifact
    is seventy eight percent comment, most of it the dated history of the
    migration that produced the file. Whether the cleaned workspace stays
    a reproduction record, whose receipt is then retaken, or becomes a
    plain example is the author's decision and is asked in GOAL-011.
