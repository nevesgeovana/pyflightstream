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

!!! nonrequirement "NREQ-02 No general-purpose meshing product"
 The package imports meshes, refines or coarsens panel meshes, derives thin
 blades and audits meshes. Its geometry instruction route can ask FlightStream
 to build a panel mesh from supported CAD or CCS inputs, subject to the target
 build's command evidence. It is not a general-purpose volume mesher and does
 not overwrite the imported source. See [geometry inputs](../cad-inputs.md).

!!! nonrequirement "NREQ-03 No solver-accuracy claims"
 The physics regression matrix guards regressions of the pipeline
 and of solver behavior across versions. It does not validate
 FlightStream physics against nature, and the package makes no
 accuracy claims on the solver's behalf.

!!! nonrequirement "NREQ-04 Only registered FlightStream builds"
 The registry includes the 25 series as well as the 26 series. Its ordered
 build list is authoritative; a version number alone does not establish
 command availability or inherited evidence. Registered builds are retained,
 and earlier builds may be added without renumbering existing identifiers.

!!! nonrequirement "NREQ-05 No command family is excluded from the database"
 Every command a registered manual edition documents enters the
 database, chapter by chapter, and no family is excluded by decision.
 A newly registered edition may document a command not yet entered;
 that is a dated debt in the evidence queue and never an exclusion,
 and the emitter refuses such a command rather than guessing at it.

!!! nonrequirement "NREQ-06 No GPL or AGPL dependencies"
 Not as runtime dependencies, not as extras, not vendored. GPL
 tools are reachable only as user-run external executables through
 file exchange.

## Boundary notes

- The FSI structural solver is available through the optional `[fsi]` extra.
- Cluster submission is available through the run executor and explicit HPC
 profiles. It shares the campaign model with local execution; collection
 records the submitted job's observed results. A configured cluster and its
 scheduler remain external prerequisites.
