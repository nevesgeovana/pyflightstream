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
    `tests/tier1_offline/test_conventions.py` for model fields. That units and frames
    are actually stated in the prose of every public function is
    checked by review, because the tools check shape and not meaning,
    and this tag says so rather than letting the badge imply a guard.*

    Every public function has a numpydoc docstring stating units and
    reference frames.

!!! requirement "NFR-01b Modules state their pipeline role <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of NFR-01, accepted 2026-07-27. Evidence:
    `tests/tier1_offline/test_package_imports.py`, which asserts a non-empty top
    docstring on every subpackage, and the architecture overview, which
    renders them. What is guarded is that the docstring EXISTS at
    subpackage level; that its text states a pipeline role, for every
    one of the modules below that level, is a review check.*

    Every module's top docstring states its role in the pipeline.

!!! requirement "NFR-01c Errors name the cause, not the symptom <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of NFR-01, accepted 2026-07-27, absorbing
    the C3 acceptance on error content. Evidence:
    `tests/tier1_offline/test_error_messages.py` and the attribute cases of
    `tests/tier1_offline/test_exceptions_catalog.py`, which pin a named list of
    errors rather than enumerating every raise site. The list is the
    guard's scope, in the manner NFR-24 states for its own.*

    Every raised error names the physical or version cause rather than
    the internal symptom, identifies the object or version involved and
    the operation attempted, states a suggested fix where a remedy is
    known, and carries the machine-readable attributes a caller needs
    to recover.

!!! requirement "NFR-01d Worked examples per workflow <span class='srs-implemented'>implemented</span>"
    *Origin: Phase 4 split of NFR-01, accepted 2026-07-27. Evidence:
    `tests/tier1_offline/test_examples.py` runs each of the `examples/*.py` and holds
    each to the extras it declares; the Sybil run covers the docstring
    doctests and the markdown code blocks. Nothing enumerates the public
    workflows and checks one example per workflow, so the per-workflow
    coverage is a review check and the badge covers the examples'
    correctness.*

    Read with PFS-2031.10 at 0.13.0 (GOAL-012): tests/tier3_licensed is the worked example of every feature and the pages name it.

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
    Windows); the package itself is pure Python at or above the floor
    `pyproject.toml` declares, and passes CI on Linux AND on Windows
    at that floor. The floor follows SPEC 0, the scientific-python
    community schedule (three years of support after a Python
    version's initial release, two after a core package version's),
    computed on a date `pyproject.toml` states beside it; on
    2026-09-09 that is Python 3.12, numpy 2.2 and pandas 2.3
    (PFS-2024.07). HPC submission stays a deferred executor (FR-15).

    Read with PFS-2054, PFS-2054.03, PFS-2054.04 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Following a published schedule lets a user predict the support window and its next change.
    `tests/tier1_offline/test_support_window.py` re-derives the floors
    from the release dates and the stated date, so the schedule
    overtaking the declaration fails the suite rather than going
    unnoticed. Evidence: `.github/workflows/ci.yml` (the Linux and
    Windows legs at the floor), `tests/tier1_offline/test_support_window.py`,
    and the CHANGELOG entry for PFS-2024.07.

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
    (`tests/tier1_offline/test_extras.py`), so a dependency change must also update its requirement.

    Two satellites restate the set for their own readers and are not
    generated from this table, so they move with the migration commit
    rather than on their own: `pyproject.toml`, which is the machine
    authority, and the user guide, which is refreshed per release. Home
    of record means this table is what they are checked against, not
    that no other copy exists.

    The removal release NUMBER is deliberately unset here as of 2026-08-09: v0.5.0 shipped without the migration, so naming it would repeat the error this table exists to prevent. The owning seat sets the number when ITACA's `pproc/` and `aerospace/` halves are ready (PLN-20260809-0210). Other
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
    the owning seat deferred that half, so it is a candidate rather than a
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

    Read with PFS-2077, PFS-2077.14 at 0.35.0 (GOAL-040): the 0.35.0 package work reads this requirement.

    Read with PFS-2054, PFS-2054.08, PFS-2063, PFS-2063.02, PFS-2068, PFS-2068.01, PFS-2068.02, PFS-2068.03, PFS-2068.04, PFS-2069, PFS-2069.01, PFS-2071, PFS-2071.01, PFS-2071.02, PFS-2072, PFS-2072.01, PFS-2072.03, PFS-2072.05 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    Read with PFS-2031.10 at 0.13.0 (GOAL-012): the tiers page, the workspace page, the guide and CONTRIBUTING move in the same session as the folders.

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

    Read with PFS-2054, PFS-2054.05, PFS-2054.08, PFS-2071, PFS-2071.01, PFS-2071.02, PFS-2072, PFS-2072.01, PFS-2072.03, PFS-2072.04, PFS-2072.05 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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
    that a test FALSIFIES a requirement; and `tests/tier1_offline/test_traceability.py`
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
    `tests/tier1_offline/test_house_style.py::test_no_geometry_file_is_tracked_outside_the_synthetic_allowlist`
    walks every tracked path and fails on a geometry suffix outside the
    allowlist, with
    `test_the_geometry_guard_fires_on_what_it_exists_to_catch` as its
    mutation proof; the `forbid-geometry` pre-commit hook refuses the
    same class at commit time. Extended 2026-09-08 (OPS-2010.23):
    `test_no_spreadsheet_is_tracked_outside_the_allowlist` refuses a
    spreadsheet extension the same way, with
    `test_the_spreadsheet_guard_fires_on_what_it_exists_to_catch` as
    its mutation proof and the `forbid-spreadsheets` hook at commit
    time.*

    A Tier 1 guard rejects the commit of any file whose extension is in
    the known geometry or mesh set, or in the spreadsheet set, unless
    its path is in the allowlist of that set with a written reason.

    The spreadsheet set (`.xlsx`, `.xlsm`, `.xlsb`, `.xls`, `.ods`) is
    the one generic container point coordinates of a proprietary mesh
    actually travel in, and it is opaque to a diff and to a review.
    Measured before the guard existed: a spreadsheet staged under
    `examples/` passed every pre-commit hook, and the suite reddened
    only by accident, on the control-byte scan and on the shipped-surface
    checker's undecodable count, neither of which names the class.
    `.csv` is deliberately outside the set: it is text a reader can
    check, and fixture tables are tracked in it. Its allowlist was
    measured empty when the guard was written.

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
    (`tests/tier1_offline/fixtures/fsi/structural_nodes.csv`). NFR-08 is the wider
    requirement and stays a discipline for that residual. The guard also
    walks the TREE, not the built wheel. The tool that can also read the
    ARTIFACT side, `tools/check_shipped_surface.py`, has its tree
    boundary wired in tier 1 by `tests/tier1_offline/test_repository_guards.py`; its
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
    the design decision. Evidence: `pyflightstream._digest`, which
    carries `ALGORITHM`, `EXCLUDED_FROM_EVERY_DIGEST` and
    `CANONICAL_FORMS` as data; `tests/tier1_offline/test_digest.py`, including the
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

    Read with PFS-2031.02 at 0.13.0 (GOAL-012): the floor is measured again after every module moves into its tier folder.

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

    Read with PFS-2070, PFS-2070.02, PFS-2070.03 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

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
    `results/tables.py`; `tests/tier1_offline/test_tables.py` pins the run row's
    COMPLETE column list against a literal, so a column added or
    reordered in the middle fails the suite rather than passing the
    per-name lookups.*

    Read with PFS-2074, PFS-2074.20 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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
    above, which exists precisely so a schema change costs two files. The
    generated Python API reference of NFR-29 renders those docstrings, so
    a reader finds the exact column set on the site. `overview()` and the Architecture
    page carry the narrative, both rendering the same module docstrings,
    the changelog carries the announcement, and the module carries the
    list. Not `help()`, which
    renders the FlightStream command reference and says nothing about
    result tables.

!!! requirement "NFR-20 API deprecation and removal policy <span class='srs-pending'>pending</span>"
    *Origin: Phase 4 review theme 5; the window decided by the owning seat
    2026-07-27 and recorded in the [revision history](index.md).
    Pending because the policy it states begins at 1.0 and the package
    is at 0.x; the recorded-promise mechanism it relies on is already
    shipped and guarded (the ledger in `pyflightstream._deprecations`
    and the Tier 1 deadline guard `tests/tier1_offline/test_deprecation_deadline.py`).*

    Read with PFS-2074, PFS-2074.22 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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
    design decision of 2026-07-27, taken on the API-design review's
    proposal and knowing that the package has never shipped a patch
    release, so they state intent rather than describe history.

    Consequences acceptance knowingly, among them: v0.5.0
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
       core dependency narrows this package from its declared floor (`>=3.12`
       since 2026-09-09, SPEC 0) to
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
    a new requirement rather than a mirror. Evidence:
    `tests/tier1_offline/test_goal028_module_level_layering.py::test_no_module_level_import_reaches_a_higher_layer`,
    `tests/tier1_offline/test_conventions.py::test_no_function_body_import_reaches_a_higher_layer`,
    `::test_the_matrix_reader_imports_nothing_above_the_cases_layer` and
    `::test_the_results_tables_module_imports_the_workspace_layer_nowhere_at_runtime`,
    each marked with this requirement.*

    Read with PFS-2075, PFS-2075.22, PFS-2075.23, PFS-2075.24 at 0.34.0 (GOAL-039): the 0.34.0 package work reads this requirement.

    Read with PFS-2074, PFS-2074.15, PFS-2074.16, PFS-2074.17, PFS-2074.18, PFS-2074.19, PFS-2074.20, PFS-2074.21 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

    Read with PFS-2054, PFS-2054.06, PFS-2054.07 at 0.32.0 (GOAL-037): the 0.32.0 package work reads this requirement.

    A Tier 1 mechanism enforces AD-01: a module that imports from a
    layer above its own fails the suite, rather than being caught by
    review.

    The guard reads the layer table of `pyflightstream.overview`, so it
    enforces the rows that table states and nothing finer. Until the
    row-order work of 0.33.0 (AD-09) gives `run` and `workspace` a row
    each, the two share one row and an import between them is not
    refused; from then on an import from `workspace` into `run` fails
    the suite like any other upward import.

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
    `tests/tier1_offline/test_metadata_currency.py`.*

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
    2026-07-27, which the owning seat accepted as elevating AD-05 to a
    tested requirement. Evidence:
    `pyflightstream.extras.MissingExtraError` and `missing_extra`;
    `tests/tier1_offline/test_extras.py`, parametrized over every extra;
    `tests/tier1_offline/test_extras_isolation.py` and the `test-all-extras` job in
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

    Two things closed it. `tests/tier1_offline/test_extras_isolation.py` derives, from
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

    Read with PFS-2074, PFS-2074.21, PFS-2074.22 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

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

    Re-measured on the release trees, the ratchet holding: 0.25.0 read 713
    errors in 18 of 97 modules, 0.30.0 read 1065 in 18 of 134, 0.31.0 read 1084
    in 18 of 139 (RPT-029, 2026-09-29), and the 0.32.0 development branch read
    1084 in 18 of 149 after the step that laid down its ten contract modules,
    and 1112 in 18 of 150 once every 0.32.0 package had merged (2026-09-30);
    the 0.33.0 branch of work packages WP1 and WP2 read 1137 in 18 of 151 on
    the same date, its base 1137 in 18 of 150, the one module it added clean;
    the 0.33.0 branch of FR-310 to FR-314 read 1133 in 18 of 154, the four
    modules it added clean; the branch with both merged read 1133 in 18
    of 155, every one of the five new modules clean; the 0.33.0 branch of
    FR-316 to FR-319 read 1137 in 18 of 153, the three modules it added
    clean; the branch with all three merged read 1133 in 18 of 158,
    every one of the eight new modules clean; the branch of work
    package WP3 read 1130 in 18 of 172, every one of the fourteen modules
    it cut out of four existing ones clean, and `rel/0-33` before it was
    merged 1133 in 18 of 158; `rel/0-33` with WP3 merged read 1130 in
    18 of 172; the branch of FR-320 over the branch with all three merged
    read 1133 in 18 of 159, the one module it added clean; `rel/0-33`
    with WP3 and FR-320 merged read 1130 in 18 of 173; the branch of FR-96
    read 1125 in 18 of 158 on 2026-10-01, adding no module; and `rel/0-33`
    with WP3, FR-320 and FR-96 merged read 1122 in 18 of 173 on the same
    date; `rel/0-33` with WP4 (AD-12) also merged, `cases/workflows.py`
    cut into the package `cases/workflows/` of 24 modules each clean, read
    1122 in 18 of 196 on 2026-10-01; and `rel/0-33` with WP4, WP5 and WP6
    merged read 192 errors in 17 of 219 modules on 2026-10-01, the
    exempted set shrinking from eighteen to seventeen modules because WP6
    made `pyflightstream.run` a facade over typed modules and deleted its
    override (decision 7), its 930 errors leaving the debt with it; and
    the 0.34.0 branch of work package WP8 read 184 errors in 17 of 225
    modules on 2026-10-01, the six model modules AD-16 cut out of the
    `cases` root each clean and not exempted, and the root, still exempt,
    reporting 1 error where it reported 9 because every moved line was
    typed; and `rel/0-34` with the wave-1 work packages of 0.34.0 merged
    read 160 errors in 16 of 234 modules on 2026-10-01, fifteen modules
    more than 0.33.0's 219, each clean, the cuts of WP8, WP9a and the probe
    catalog typing every moved line, and `pyflightstream.qa.specs` clean,
    so its override was deleted; and `rel/0-34` with the wave-2 packages
    merged read 160 errors in 16 of 236 modules on 2026-10-02, the two
    modules more (`pyflightstream._textio` and
    `pyflightstream.workspace.actuator_profiles`) each clean.
    The sixteen exempted modules are the set of the eighteen less
    `pyflightstream.run` and `pyflightstream.qa.specs`, every module a release
    adds is clean, and the shipped configuration is green over all of them.
    The count of errors inside the exempted set grows with the code those
    modules gain and is a measurement, not a promise; the requirement is that
    the set of modules does not grow. `py.typed` is still not shipped.

!!! requirement "NFR-28 A shipped workspace reads as a set-up, not as a diary <span class='srs-pending'>pending</span>"
    *Origin: feedback item #0 of 2026-09-02, treat it as a simple test with no comments of history. Carried by PFS-2029.13.
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
    plain example is the design decision and is asked in GOAL-011.

!!! requirement "NFR-29 The documentation reference covers every public name and every command-line option <span class='srs-implemented'>implemented</span>"
    *Origin: item DOC-A of the 0.33.0 scope (GEO-071, section 3.3, and
    its decisions 10, 11, 13 and 14), from the documentation audit of
    v0.32.0, which found no Python API reference, 427 of 577 exported
    names on no page and 30 of 112 command-line options on no page.
    Built by DOC-A; accepted on 2026-10-01 after the 0.33.0 release,
    and implemented. It reverses the position of v0.3.0, when mkdocstrings
    was evaluated and declined and the site was to gain no Python API
    reference; NFR-19 is reworded to match. Evidence offered for the
    acceptance: `tests/tier1_offline/test_p0330_doca_reference.py` (R1
    to R9), the docs build in strict mode followed by the docs job's
    check that the built inventory holds every public name, and the
    licence card RPT-101 of R7.*

    Read with PFS-2074, PFS-2074.23 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

    The documentation site is organized by kind of page and its
    reference is generated from the code, so that every public name and
    every command-line option is documented where a reader looks for it.

    - R1 The site navigation is grouped by the four Diataxis quadrants,
      Tutorials, How-to guides, Reference and Explanation, each page in
      one of them, and this SRS sits under a fifth group, Project, of the
      same site.
    - R2 A Python API reference is generated from the docstrings and
      carries every name in the `__all__` of every public subpackage; the
      tiers of a name (documented, advanced) only order the page. A
      tier-1 test proves both set differences empty: no name of an
      `__all__` is missing from the reference, and no name on the
      reference is outside every `__all__`. A public subpackage here is
      every public module at every depth, the inventory the public-API
      test affirms, each with a page of its own. A public module that
      declares no `__all__` contributes the public names it defines
      itself, by the rule the renderer applies; the list of such modules
      is pinned by the same test and only shrinks, so R8 applies to each
      as it gains an `__all__`.
    - R3 A command-line reference is generated from the argument parsers
      and carries every console tool, every subcommand and every option;
      a tier-1 test proves the same two differences empty.
    - R4 The home page offers two routes: the workspace driven by
      `pyfs-matrix`, and the Python API.
    - R5 A tutorial of the Python API is executed by the documentation
      tests.
    - R6 The catalog of exceptions is generated from the exception
      classes.
    - R7 `mkdocstrings[python]` joins the documentation dependencies with
      a licence card in the form of RPT-009.
    - R8 A name nobody should use leaves `__all__` rather than being
      hidden on the page.
    - R9 The LaTeX guides are linked from the navigation, not absorbed
      into it.

    Pages this changes besides the new ones: the navigation block of
    `properdocs.yml` and its comment, which records the grouping by task
    of 0.32.0 as the rule; the Diataxis row of the
    [standards alignment](standards.md); the sentence of the
    [architecture chapter](architecture-srs.md) that says which pages are
    generated; and the revision history of this SRS.

!!! requirement "NFR-30 Every exported function documents its parameters, result and failures in numpydoc form <span class='srs-implemented'>implemented</span>"
    *Origin: item DOC-B of the 0.33.0 scope (GEO-071, section 3.3), from
    the same audit, which found 64 percent of docstrings describing their
    parameters and result and 15 percent also carrying Raises and
    Examples, and the unsteady reductions explained on three pages that
    contradict one another. DOC-B was built in two parts and accepted
    on 2026-10-01 after the 0.33.0 release.
    Part 1 completed R2 to R4 on every module but the fifteen the other
    0.33.0 packages were cutting and the four package roots the facade
    ratchet (AD-08, G8) holds at their entry, which a tier-1 test pins and
    part 2 and the facade cuts empty. Part 2 then documented every module
    part 1 left: the numpydoc list holds four package roots, `cases`,
    `farfield`, `probes` and `workspace`, and the examples list three,
    `cases`, `script` and `workspace`, each held by the facade ratchet, which
    admits no growth, until its definitions move to a module; the entry points
    whose example needs the solver or a recorded workspace number eighteen,
    each named with its reason; and ruff's D417 is selected in
    `pyproject.toml` and reports nothing over the whole tree. Evidence:
    `tests/tier1_offline/test_p0330_docb_docstrings.py`, whose
    P0330-DOCSTRINGS-NUMPYDOC walks every exported function for R2,
    P0330-DOC-EXAMPLES the documented tier for R3 against the
    executable-examples step, and P0330-DOC-REDUCTIONS-HOME the pages
    for R4, each with a planted-defect control. Owed: the docstrings of
    the held roots, completed as each becomes a facade.*

    Read with PFS-2074, PFS-2074.24 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

    The docstring of every exported function says what it takes, what
    it returns and how it fails, in the numpydoc form, and its examples
    run.

    - R1 Ruff's rule D417 is selected and reports nothing on the exported
      functions.
    - R2 Every exported function has numpydoc `Parameters` and `Returns`
      sections, and a `Raises` section where it raises; a physical
      quantity in `Parameters` states its unit (NFR-01a).
    - R3 Each documented entry point carries an `Examples` section whose
      examples run as tests; the list of documented entry points is the
      reference's documented tier of NFR-29.
    - R4 The reductions of the unsteady run are defined on one page, the
      definitions page `docs/post-processing-definitions.md`, and every
      other page that mentions them links to it and restates no
      definition.

!!! requirement "NFR-31 The public tree carries no identity of a user's machine <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2076.07 (0.36.0).

    *Origin: an author decision of 2026-09-30 for 0.33.0. It is
    built and was accepted on 2026-10-01 after the 0.33.0 release. Evidence: the
    tier-1 guard `tests/tier1_offline/test_p0330_no_executable_hash.py`
    (P0330-NO-EXE-HASH) for R1 and R2, with a mutant control per shape;
    the tests of the three report writers and of the C01 instrument for
    R4.*

    Read with PFS-2074, PFS-2074.25 at 0.33.0 (GOAL-038): the 0.33.0 package work reads this requirement.

    What is committed (reports, compatibility, physics, drift and probe
    records, fixtures, source, scripts and tests) identifies the solver by
    its version and build, never by the machine it ran on.

    - R1 No tracked file carries the SHA-256 of a solver executable, of
      any build. The solver build identifies the executable (for example
      FlightStream 26.124, build 8172026), and a record states the digest
      as `withheld; build <build>` where its format has a digest field.
      The guard refuses a 64-hex value next to a label that names the
      executable (`fs_exe_sha256`, `exe_sha256`, `executable_sha256`, an
      `.exe` file name, the word executable) on its line, at the end of
      the line before it, as the key of the YAML or JSON block it sits in,
      or as the header of its Markdown table column; and it refuses the
      digests the executable identity baseline once recorded, anywhere,
      compared by their own SHA-256. A synthetic digest is one hexadecimal
      digit repeated, which the guard allows by rule.

      **AMENDED 2026-10-01: R1 covers the digests of the libraries,
      executables and sample script of the solver package too.** No tracked
      file carries the SHA-256 of a library, an executable or the sample
      script of the solver package (the `.dll`, `.exe`, `.so` and
      `Script.txt` files): a record states the file, its size and whether
      two packages agree, and withholds the digest. The digests of the
      package's documentation (manual, release notes, licence agreement) are
      covered by FR-344. The guard refuses a 64-hex value on
      the same line as a `.dll`, `.exe` or `.so` file name or `Script.txt`,
      with a mutant control that plants one. The digest of a script or
      product the package wrote is not a solver-package file and stays
      allowed.
    - R2 No tracked file carries an absolute user path: a user-profile or
      home folder, a OneDrive folder, or the work or estate root of a
      measuring machine. A report names a file by its path inside the
      run's workspace (`<workspace>/...`) or the local probe folder
      (`<local probe folder>/...`). No tracked file carries a host name,
      licence server or licence detail either; no committed shape exists
      for these, so they are kept out by review.
    - R3 A run record keeps its own `fs_exe_sha256`: it is written on
      the user's machine into the workspace, which is not committed, and
      the products carry it from there. The package holds no copy of it:
      evidence measured on one executable is keyed by the version, the
      build and the unit, and requires the run to have recorded a digest.
    - R4 Every writer of a committed report states the build and never a
      digest or a machine path: the compatibility, physics and drift
      reports write `withheld; build <build>` for a recorded digest (and
      "not recorded" for a run that took none), and the C01 instrument does the
      same in the receipt copies it commits. The executable baseline is
      read from a local, uncommitted copy when bytes must be compared.

!!! requirement "NFR-32 Every text file the package writes has LF line ends on every platform <span class='srs-pending'>pending</span>"
    *Origin: the author decision of 2026-10-01 to standardise LF in every
    product (scope record GEO-071, section 4.10), a behaviour change with a
    migration note. Marker P0340-LF-PRODUCTS; read at 0.34.0 (GOAL-039,
    arm LF). Built on 2026-10-01; the status stays pending until accepted. Evidence: `tests/tier1_offline/test_p0340_lf_products.py` (R2 by the walk of `src/` and its twenty-eight planted bypasses, R1 and R3 by the route and by campaigns and emitted scripts posted with text mode forced to CRLF, with a bypassed route as the control, R4 by the parity comparison, R5 by the change-log fragment, R7 by the census note), `scripts/lf_products_check.py`, and `reports/RPT-140_text-writers-crlf-census_2026-10-01.md` (the writer census of R7, measured on win32). Verification method: a tier-1 guard
    carrying the marker, with a planted control; the products snapshot
    judged on both platforms; the parity receipt of the release; and, for
    the files the solver reads, the licensed runs of R6. Evidence
    owed: the writer census of R7; a guard that walks `src/` and refuses
    a text write that bypasses the one LF route, with a planted bypass as
    its control; a test that a campaign posted on Windows holds no CR byte
    in any product and that its emitted scripts hold none, run with text
    mode forced to write CRLF as Windows does, so that it fails on Linux
    too when a writer bypasses the route; the products snapshot comparing
    line ends on Linux and Windows, which is evidence of the `ci.yml`
    matrix (the `windows-latest` runner), not of a Linux-only tier 1; the parity receipt
    naming the difference under this requirement; the paragraph of the
    migration page.*

    Read with PFS-2075, PFS-2075.12 at 0.34.0 (GOAL-039): the 0.34.0 package work reads this requirement.

    Every text file the package writes ends its lines with LF on every
    platform, through one write route that a guard holds.

    Why: a file written in text mode gets CRLF on Windows and LF on Linux,
    so the same campaign posted on two platforms can give different bytes
    and a byte snapshot cannot be portable. RPT-140 measures which writers
    produced CRLF on Windows; R7 holds that census.

    - R1 Every text file the package writes is written with LF line ends
      on every platform, with no CR byte: the products, `products.json`,
      the post log and its JSON, records, plans, receipts, the emitted
      solver scripts, the input files written for the solver to read, and
      every other text output.
    - R2 Every text write of the package goes through one route that
      writes LF, in the private floor module `pyflightstream._textio`; a
      tier-1 guard walks `src/` and refuses a text write that bypasses it,
      and a planted bypass is its control.
    - R3 A campaign posted on Windows holds no CR byte in any product or
      emitted script; the products snapshot judges line ends and compares
      equal on Linux and on Windows.
    - R4 Compared with 0.33.0, a file the package writes differs only by
      the CR bytes removed before LF, with one stated exception: the
      embedded counter and clock solver programs now state the LF line end
      in their own text, so their text and recorded sha256 change for that
      reason too; the parity script compares the post
      of a recorded workspace and the emitted scripts after removing CR
      before LF on the 0.33.0 side, and its `NAMED_DIFFERENCES` name that
      difference under this requirement.
    - R5 This is a behaviour change, permanent, with no
      switch that restores CRLF: the migration page of 0.34.0 states it
      first among the behaviour changes (a reader that split lines on
      CRLF reads LF now).
    - R6 The files the solver reads are inside R1. The evidence that the
      solver reads LF is that the licensed probes of RPT-070 found that
      line ends change nothing in the disc profile file the solver reads;
      the licensed runs of 0.34.0 made after this requirement is
      implemented run LF scripts on 26.124 and are its confirmation, each
      of their reports stating that the scripts it ran were LF.
    - R7 The writers that produce CRLF on Windows in 0.33.0 are measured
      at the start of the work package (the writer census) and listed in
      its record, with the platforms the measurement ran on.

!!! requirement "NFR-33 One home per documentation topic <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2076.04 (0.36.0).

    *Origin: the 0.36.0 scope and its S1 review, 2026-10-03.*

    Need: A topic must have one defining paragraph, so its explanations cannot drift between pages.

    Requirement: Each topic below shall have the stated home; pointer pages shall link to it rather than repeat its defining paragraph. Page names are relative to `docs/` unless stated otherwise.

    | Topic | Home page | Pointer pages |
    |---|---|---|
    | sync | `storage-and-sync.md#sync` | `sync-folders-and-matrix-homes.md`, `storage-and-sync.md#sync_1` |
    | archive and restore | `restore-and-rebuild.md#archive-and-restore` | `continuation-recovery.md`, `pproc-artifact.md` |
    | saved simulation | `continuation-recovery.md#saved-simulation` | `mesh/how-to.md`, `gui-to-pyfs.md` |
    | evidence discipline | `srs/philosophy.md#evidence-discipline` | `index.md` |
    | rotor facts | `mesh/reference.md#the-four-rotor-facts-a-reference-artifact-once-carried` | `workflow-reference-artifact.md` |
    | entry pages | `index.md#where-to-start` (the single entry page) | |

    - R1 A topic's defining paragraph is the first paragraph under its home heading, whose slug is the anchor in the table; that paragraph exists only on its home page.
    - R2 Every pointer page links to the home heading for the definition. The `sync_1` section links to `sync` on the same home page.

    Verification: tier 1, a guard carrying P0360-DOC-ONE-HOME and NFR-33 checks the home table, definitions and pointer links, with a duplicated defining paragraph planted on a pointer page as its failing control. Release 0.36.0.

    Evidence: `tests/tier1_offline/test_p0360_doc.py::test_one_home` checks the requirement and its failing controls.

!!! requirement "NFR-34 The definitions split preserves every anchor <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2076.04 (0.36.0).

    *Origin: the 0.36.0 scope and its S1 review, 2026-10-03.*

    Need: Readers must be able to use a focused definitions page without losing existing links or code and test pins.

    Requirement: `docs/post-processing-definitions.md` shall become an index page that stays the definition of record, with one page per top-level (`##`) family except "Contents", which stays on the index as its table of contents. Each family page is `docs/definitions/<the heading slug>.md`; all 53 old slugs remain as explicit `<a id="slug"></a>` anchors on the index.

    - R1 Every one of the original 53 heading slugs stays resolvable from `post-processing-definitions.md`, through an anchor per old slug on the index or a redirect section linking to the family page.
    - R2 Every code and test pin keeps its anchor value and names the new family page. Moving a pin changes its target page only, never the anchor value.

    Verification: tier 1, tests carrying P0360-DOC-DEFINITIONS-SPLIT and NFR-34 resolve a pre-split fixture of all 53 slugs, check one page per `##` family, and check every code and test pin's page and unchanged anchor. A removed anchor and a stale page pin are failing controls. Release 0.36.0.

    Evidence: `tests/tier1_offline/test_p0360_doc.py::test_definitions_split` checks the requirement and its failing controls.

!!! requirement "NFR-35 The mesh inputs split preserves every anchor <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2076.04 (0.36.0).

    *Origin: the 0.36.0 scope and its S1 review, 2026-10-03.*

    Need: Mesh instructions, reference details and examples must be independently readable while existing links keep working.

    Requirement: `docs/mesh-inputs.md` shall be split into how-to, reference and example pages.

    - R1 Every one of its 21 rendered heading slugs remains resolvable from `mesh-inputs.md`.
    - R2 The original page links each preserved heading to its destination in the split.

    Verification: tier 1, tests carrying P0360-DOC-MESH-SPLIT and NFR-35 check the three page roles and resolve the pre-split fixture of all 21 rendered heading slugs, with a removed anchor as a failing control. Release 0.36.0.

    Evidence: `tests/tier1_offline/test_p0360_doc.py::test_mesh_split` checks the requirement and its failing controls.

!!! requirement "NFR-36 No version narrative on reference pages <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2076.04 (0.36.0).

    *Origin: the 0.36.0 scope and its S1 review, 2026-10-03.*

    Need: Reference pages must state the current contract without a narrative of earlier releases.

    Requirement: The following case-insensitive regex shall match nothing on any `docs/*.md` or `docs/**/*.md` page except `migrating-to-*.md`, `release-notes.md` and `upgrading.md`; this is the reference-page set for this requirement.

    ```text
    \b(since|until|before|from|as of)\s+v?0\.\d+(\.\d+)?\b|\b(added|new|introduced|changed|removed|renamed)\s+in\s+v?0\.\d+
    ```

    - R1 The guard applies that exact regex, case-insensitively, to every page in the stated glob with only the three stated exclusions; its accepted match count is zero.
    - R2 The baseline measured on 2026-10-03 at W0 (`42cf219a`) is 242 matching lines across 51 eligible pages, counting a line once even when it contains several matches. The approximate S1 count of 297 is not the measured baseline for this regex and page set.

    Verification: tier 1, a guard carrying P0360-DOC-NARRATIVE and NFR-36 checks zero matches and fails on a planted matching phrase on a reference page; an excluded migration page is the unchanged control. Release 0.36.0.

    Evidence: `tests/tier1_offline/test_p0360_doc.py::test_narrative` checks the requirement and its failing controls.

!!! requirement "NFR-37 The upgrading index and frozen release records <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2076.04 (0.36.0).

    *Origin: the 0.36.0 scope and its S1 review, 2026-10-03.*

    Need: Readers must find every migration record from one index and know that release records are frozen.

    Requirement: `docs/upgrading.md` shall list every `docs/migrating-to-*.md` page, and every migration page and `docs/release-notes.md` shall carry exactly one of the three frozen-record lines below, selected by its history in the DOC-C diff `b656abbf..8a670a31`.

    - R1 The index's migration-page count equals the glob count, with each glob member listed exactly once and no nonexistent migration page listed.
    - R2 A page that existed at its release and received only the banner in DOC-C carries exactly `> Frozen record: not edited after its release.`
    - R3 A page that existed at its release and received an appended historical-context or historical row-key section carries exactly `> Frozen record of its release; the historical-context section at the end was appended at 0.36.0, when the reference pages stopped narrating versions, and is frozen too.`
    - R4 A page created by DOC-C carries exactly `> Historical record assembled at 0.36.0 from the reference pages; frozen from now on.`

    Verification: tier 1, tests carrying P0360-DOC-UPGRADING and NFR-37 compare the index to the glob and list each page's required banner, checking the exact line on each record. A missing index entry, a missing banner and a created page carrying R2's banner are failing controls. Release 0.36.0.

    Evidence: `tests/tier1_offline/test_p0360_doc.py::test_upgrading` checks the requirement and its failing controls.

!!! requirement "NFR-38 Requirement ids belong in the test functions that prove them <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2076.06 (0.36.0).

    *Origin: the 0.36.0 scope and its S1 review, 2026-10-03. Evidence: `tests/tier1_offline/test_p0360_frid.py::test_requirement_ids_belong_to_the_test_functions` and its planted controls.*

    Need: A module-level claim must not stand for evidence that no test function identifies.

    Requirement: An FR or NFR id named by a tier-1 test module only in a module comment or module docstring, and in no test function's own source, shall fail a guard.

    - R1 The guard uses an AST scan of tier-1 test modules to identify test functions and reads each function's own source, including its docstring.
    - R2 A module-only id fails; the same id in a test function's own source satisfies this placement rule. Placement alone does not prove the requirement's behaviour.

    Verification: `tests/tier1_offline/test_p0360_frid.py::test_requirement_ids_belong_to_the_test_functions`, `::test_module_only_control_is_refused` and `::test_function_local_control_satisfies_placement`; explicit contextual leftovers in `LEFTOVERS`, each with its reason. Tier 1, a guard carrying P0360-FR-IN-FUNCTIONS and NFR-38, with planted module-comment-only and module-docstring-only controls that fail, and a function-local control that passes. Release 0.36.0.

!!! requirement "NFR-39 Shared test helpers have one support module <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2076.06 and PFS-2076.07 (0.36.0).

    *Origin: the 0.33 review rows A1 and A2, carried into the 0.36.0 scope. Evidence: `tests/tier1_offline/test_p0360_frid.py::test_shared_helpers_have_one_definition` and `::test_shared_helpers_are_imported_by_their_consumers`.*

    Need: The shared helpers named by review rows A1 and A2 must not drift between test modules.

    Requirement: The helpers named by the 0.33 review rows A1 and A2 shall live in `tests/support_helpers.py` and shall not be redefined elsewhere.

    - R1 Every test needing those helpers imports them from that one support module.
    - R2 A second definition of any of those helpers outside that module is refused.

    Verification: `tests/tier1_offline/test_p0360_frid.py::test_shared_helpers_have_one_definition` and `::test_shared_helpers_are_imported_by_their_consumers`. Tier 1, tests carrying P0360-RV-A1 and P0360-RV-A2 with NFR-39 check the single home and its consumers; a planted duplicate helper is a failing control. Release 0.36.0.

!!! requirement "NFR-40 No behaviour change for structure <span class='srs-pending'>pending</span>"
    Plan: PFS-2076, PFS-2076.01, PFS-2076.02, PFS-2076.03 and PFS-2076.08 (0.36.0).

    *Origin: the 0.36.0 scope's no-behaviour decision and its S1 review, 2026-10-03. The licensed reproduction RPT-152 passed on three points: partial evidence from one campaign and one build; acceptance is owed and the status stays pending.*

    Need: Structural work must preserve the results and observable behaviour of v0.35.1.

    Requirement: The emitted scripts (per point and grouped job scripts), product bytes, records, console text and exit codes of 0.36.0 shall be identical to v0.35.1 except where a requirement names the difference.

    - R1 Every named difference cites its FR id and appears in `docs/migrating-to-0.36.0.md`; a structural move alone authorizes no difference. AD-15's evolution policy applies with v0.35.1 as this release's baseline.
    - R2 `scripts/check_parity.py` uses `PREVIOUS = "v0.35.1"` and compares both workspaces. The products snapshot also compares the product bytes. The parity rule's file pattern is limited to the files of the named difference, so an unrelated changed file cannot pass under that rule (review row O7-QA-1).
    - R3 The licensed parity reproduction is an RPT on FlightStream 26.124, build 8172026, never identified by an executable hash. It uses far field 5, records `farfield_layers = 5`, and records a run window not overlapping another solver run.
    - R4 The reproduction is nondimensional: every status, iteration and step count is equal, and every coefficient, section, probe and reduction table is identical in every cell, as RPT-113 did. The report states the comparison population and the measured result; a pending requirement is not evidence of equality.

    Verification: tier 1, tests carrying P0360-NOBEHAVIOUR and NFR-40 check the parity contract and products snapshot, with a planted difference as a failing control. P0360-RV35-O7-QA-1 with NFR-40 checks the parity rule's file pattern with an unrelated changed file as its failing control. `scripts/check_parity.py`, the products snapshot and the licensed RPT of R3 and R4 together verify the release. Release 0.36.0.

!!! requirement "NFR-41 Tier-1 tests never import the licensed tier <span class='srs-implemented'>implemented</span>"

    *Origin: review row C2-ARCH-1 of 0.35.1, carried into the 0.36.0 scope. Evidence: `tests/tier1_offline/test_p0360_rv35.py::test_tier1_never_imports_the_licensed_tier`.*

    Need: Offline verification must not depend on a licensed test tier.

    Requirement: No `tests/tier1_offline` module shall import `tests.tier3_licensed` or any other licensed-tier module.

    - R1 The rule covers module-level and deferred imports throughout `tests/tier1_offline`, including imports used only for annotations.
    - R2 Shared test support is imported without a licensed-tier dependency.

    Verification: `tests/tier1_offline/test_p0360_rv35.py::test_tier1_never_imports_the_licensed_tier`, including the tier-neutral support modules. Tier 1, a guard carrying P0360-RV35-C2-ARCH-1 and NFR-41 scans imports and fails on a planted import of a licensed-tier module. Release 0.36.0.

## 0.37.0

!!! requirement "NFR-42 The parity instrument's tests share one fixture home and cover its refusal fallback <span class='srs-implemented'>implemented</span>"
    Plan: PFS-2078.09 (0.37.0).

    *Origin: the 0.36.0 push review of `scripts/check_parity.py` (registered as 0.37 R4), scope GOAL-044 item S9. Verification: test, `tests/tier1_offline/test_p0370_s9_parity_tests.py`.*

    Need: The parity script decides whether a release changed behaviour; its tests must not depend on another release's test module, and its refusal comparison must be tested on every branch it has.

    Requirement: The grouped-plan workspace fixture the parity tests use lives in `tests/support_helpers.py` and is imported from there by every test that uses it; the refusal comparison of `scripts/check_parity.py` is tested without `plan.json` (the whole-message fallback) and with a one-line change of a refusal message on each branch.

    - R1 No tier-1 test imports a fixture from another test module for the parity tests.
    - R2 A one-line change of the refusal message is reported as a difference when `plan.json` is absent, and only its per-point reasons count when `plan.json` is present.

    Verification: test, `tests/tier1_offline/test_p0370_s9_parity_tests.py`, carrying P0370-S9-PARITY-TESTS (NFR-42).

    Evidence: `test_p0370_s9_the_fixture_has_one_definition_in_the_support_module` (the dependency graph: the support module imports no tier-1 test module at any depth, each builder of the fixture is defined there and nowhere in tier 1, no tier-1 module imports the fixture from a test module), `test_p0370_s9_the_shared_fixture_builds_the_grouped_plan_workspace`, `test_p0370_s9_without_a_plan_a_one_line_config_message_change_is_a_difference`, `test_p0370_s9_without_a_plan_a_point_line_of_the_message_is_compared`, `test_p0370_s9_with_a_plan_only_the_per_point_reasons_count` and `test_p0370_s9_a_refusal_on_one_side_only_is_a_difference` in `tests/tier1_offline/test_p0370_s9_parity_tests.py`. The fixture is `grouped_plan_fixture` of `tests/support_helpers.py`, with `rotor_workspace`, `rotor_row`, `make_library`, `fixture_codes` and `stage_geometry` moved there from test modules. Mutants killed: the whole-message fallback returning nothing, the `plan.json` branch comparing the whole message, the parsed-message branch comparing the heading, a lazy tier-1 import inside the support module, the fixture imported from a test module again.

!!! requirement "NFR-43 A public requirement attributes no statement to a person <span class='srs-pending'>pending</span>"
    Plan: PFS-2079.09 (0.38.0).

    *Origin: scope GOAL-045 item S7, the 0.37.0 release review. Verification: test, the P0380 tests named below.*

    Requirement: The Origin line of every requirement box of the public SRS names the scope item, the plan node, the report or the evidence that gave the requirement. The words that set a requirement live in the private record of its release.

    - R1 No Origin line of the public SRS holds a double-quoted span of four or more words, or a first-person pronoun (I, me, my, we, our) outside a code span.
    - R2 The Origin lines that held one are rewritten under R1; the text of every box outside its Origin line is unchanged, checked by a digest of each box with its Origin line removed, taken before and after.
    - R3 No line of the public SRS holds a drive-letter path or a user-profile path; names of persons and employers stay under the repository's forbidden-identifier guard.

    Verification: test, `tests/tier1_offline/test_p0380_s7_origin.py`, carrying P0380-ORIGIN (NFR-43). Controls: an Origin line holding a quotation in another language, one holding "I asked" and one holding a quoted English sentence each fail R1.

!!! requirement "NFR-44 The cross-cutting guards run alone, and a digest of rendered text does not depend on the path separator <span class='srs-pending'>pending</span>"
    Plan: PFS-2079 (0.38.0), GOAL-045 arm GD.

    *Origin: the 0.37.0 release, where full suites were run for failures the guard tests show alone, and a test pinned the digest of a rendered path and failed only on Linux. Verification: test, the P0380 tests named below.*

    Requirement: `python scripts/run_guards.py` runs the guard tests (the tier-1 tests that judge the whole tree: architecture metrics, private-name coupling, the requirements index, the repository and house-style guards, the documented rows and invocations, claim currency, the release-ready record and the SRS consistency), listed once in the script, in one pytest invocation, and prints each guard file's result.

    - R1 The command exits 1 when a guard fails, naming its file, and 2 when a listed guard file is missing; a guard file of which no test ran is reported NOT RUN and makes the command exit 1. A run on the reference machine takes under 300 seconds (186 s when the command was introduced).
    - R2 A test that pins the digest of rendered text holding a path computes it from text in which every backslash of that path is a forward slash, and which holds no absolute path, drive letter or clock reading: the same text with either separator gives one digest.

    Verification: test, `tests/tier1_offline/test_p0380_guards.py`, carrying P0380-GUARDS (NFR-44). Controls: a guard forced to fail makes the command exit 1 and print its name; a listed file removed makes it exit 2; the separator fold is called on one text with backslashes and with forward slashes. The Linux half of R2 is the CI run.
