# Scope

## In scope

The package owns the full pipeline from case definition to
engineering results:

- The per-version command database with evidence-backed statuses.
- Validating script construction (builder plus curated helpers).
- Campaign and case modeling, including the pipe-delimited run-matrix
  format as a first-class interface.
- Headless execution with a manifest recording every outcome.
- Output parsing and tabular post-processing.
- The managed workspace: input-artifact library, run layout, naming,
  archiving.
- Far-field probe surveys and their conservation ledgers.
- Aeroelastic coupling (the `fsi` subpackage, optional extra).
- The QA ladder: CI tests, licensed command-validity probes, licensed
  physics regression and cross-version drift.

## Non-requirements

Explicit exclusions. Like requirements, they carry stable identifiers
and are never silently dropped.

!!! nonrequirement "NREQ-01 No GUI"
    The package is a library and a set of command-line tools. No
    graphical interface is planned or accepted.

!!! nonrequirement "NREQ-02 No geometry generation or meshing"
    The predecessor imported pre-built meshes; so does pyflightstream.
    Synthetic QA geometry generators exist for testing, not as a
    meshing product. Open-source meshers are reachable only as
    external tools through file exchange (see the integrations
    research card, RPT-008).

!!! nonrequirement "NREQ-03 No solver-accuracy claims"
    The physics regression matrix guards regressions of the pipeline
    and of solver behavior across versions. It does not validate
    FlightStream physics against nature, and the package makes no
    accuracy claims on the solver's behalf.

!!! nonrequirement "NREQ-04 No FlightStream versions older than 26.0"
    The registry starts at 26.000. Supported versions are only ever
    added going forward, never dropped (NFR-04).

!!! nonrequirement "NREQ-05 No mesh-wrapper command family by default (narrowed 2026-08-06)"
    The mesh-wrapper chapter may be added later under the same database
    rules; it is not part of the core scope.

    NARROWED, and the identifier is kept rather than deleted because
    identifiers here are never reused. As written until 2026-08-06 this
    also excluded the CAD and CCS families and said individual commands
    would enter only when a workflow needed one. The CAD and CAD Create
    chapters then entered WHOLESALE, 33 commands read chapter by chapter
    from all four registered manual editions rather than pulled in one
    at a time, so the sentence had become false in both halves: the
    families are in, and they did not arrive the way this said they
    would.

    The reason for the change is worth recording, since a non-requirement
    is a scope decision and not an oversight. The database's own coverage
    measurement showed the manuals describing 386 commands against 162
    recorded, and the author's decision of 2026-08-06 was that everything
    the manual documents enters, chapter by chapter, rather than on
    demand. Entering a family whole is also what surfaced the
    parameter-table-versus-sample defect class, which reading one command
    at a time would not have shown.

    The page range this used to cite (SRC-003 pp.286-317) rested on a
    scripting-reference span that was itself wrong by five pages at each
    end; the corrected span is recorded in `commands/_meta.yaml`.

!!! nonrequirement "NREQ-06 No GPL or AGPL dependencies"
    Not as runtime dependencies, not as extras, not vendored. GPL
    tools are reachable only as user-run external executables through
    file exchange (NFR-02; RPT-008 records the per-candidate
    evidence).

## Boundary notes

- The FSI structural solver was out of scope at v0.1 (seam only) and
  entered in-package at M6 as the optional `[fsi]` extra; the
  requirement history (FR-23, FR-23a) records the amendment rather
  than rewriting it.
- HPC execution remains deferred (FR-15): the executor interface must
  allow it without changes to the campaign model, but no cluster
  submission ships today.
