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

!!! requirement "NFR-06 Minimal public dependencies <span class='srs-implemented'>implemented</span>"
    *Origin: PP-9.*

    Runtime dependencies form a minimal, public, permissively
    licensed set (numpy, pandas, PyYAML, pydantic, xarray); heavier
    needs live behind optional extras; no private or absolute-path
    dependencies, ever. The standing engineering policy prefers
    existing public libraries over in-house code for generic needs.

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
      version-bearing metadata files agree.
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
