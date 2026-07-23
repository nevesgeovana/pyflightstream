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

!!! nonrequirement "NREQ-05 No CAD, CCS, or mesh-wrapper command families by default"
    These manual chapters (SRC-003 pp.286-317) may be added later
    under the same database rules; they are not part of the core
    scope. Individual commands from these areas enter when a workflow
    needs them, with citations.

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
