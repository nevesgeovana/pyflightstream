# Non-functional requirements

!!! requirement "NFR-01 Didactic policy <span class='srs-implemented'>implemented</span>"
    *Origin: BRF-04.*

    Every public function has a numpydoc docstring with units and
    reference frames; every module states its pipeline role in its
    top docstring; error messages name the physical or version cause,
    not the internal symptom; the docs include worked examples.

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
    on Linux. HPC submission stays a deferred executor (FR-15).

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

    | Through v0.4.0 | From v0.5.0 |
    |---|---|
    | numpy, pandas, pydantic, PyYAML, xarray | numpy, itaca, pydantic, PyYAML |

    pandas and xarray leave and ITACA arrives as one move, not per
    structure (AD-06, AD-07). The count does not grow: five becomes
    four. Reading the right-hand column as already true is the error
    this table exists to prevent; `pyproject.toml` carries the
    left-hand column today and the migration commit moves it.

    Two satellites restate the set for their own readers and are not
    generated from this table, so they move with the migration commit
    rather than on their own: `pyproject.toml`, which is the machine
    authority, and the user guide, which is refreshed per release. Home
    of record means this table is what they are checked against, not
    that no other copy exists.

    The removal release, v0.5.0, is a fact of the same kind. Other
    pages print the number rather than sending a reader two documents
    deep for it, and cite this requirement as the home the number is
    checked against.

!!! requirement "NFR-07 Reproducibility <span class='srs-implemented'>implemented</span>"
    *Origin: PP-6.*

    A run is reproducible from its manifest entry alone: inputs
    hashed, versions recorded, solver setup snapshotted, script
    regenerable. Publications cite run ids.

!!! requirement "NFR-08 Confidentiality <span class='srs-implemented'>implemented</span>"
    No employer or third-party proprietary content, no proprietary
    geometry, no research-specific aircraft data ever enter the
    repository. Synthetic geometry only in tests and examples; local
    research cases contribute only aggregated coefficients to
    committed reports.

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

Identifiers NFR-13 to NFR-18 and NFR-21 are RESERVED, not missing. They
were accepted in the same 2026-07-27 batch as the five below and are
written by the lanes that own their subjects; identifiers are assigned
at acceptance and never renumbered, so the gap is the convention working
rather than an omission.

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
