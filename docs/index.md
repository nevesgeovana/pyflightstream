# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. MIT licensed.

Status: v0.10.0 is the current release; the changelog records what
each release adds and what each one asks you to do.

**v0.10.0 asks nothing of a run matrix you already have.** Every key it
adds is optional and every older form still resolves. It refuses one
thing it used to drop: a solver preset stating a key this package cannot
emit, which used to be warned about and dropped and is now refused
naming the key.

**v0.9.0 breaks the run-matrix file format**, and it is the one
upgrade action that cannot be skipped: the `RE` and `MACH` columns are
replaced by one mandatory `FLIGHT_CONDITION` cell. An older file is
recognised and refused rather than misread, and
`pyfs-matrix upgrade your_matrix.fs --in-place` converts it. The
conversion is lossless as a file and **not neutral as a result**,
because a Reynolds number stops being recorded metadata and becomes a
constraint that solves for density: an upgraded row emits a fluid state
it never emitted before and its numbers move. [Flight
conditions](flight-conditions.md) is the whole grammar and the
migration.

v0.8.1 before it was a patch: a run
matrix can name its geometry, so a workflow no longer builds a script
that opens nothing and solves whatever the solver already had in memory,
and a row can declare the symmetry a periodic sector needs. It reserves
three names inside the matrix's free cell, `GEOMETRY`, `SYMMETRY` and
`PERIODIC_COPIES`, which was its own upgrade action. Earlier releases,
and what each of them registered or broke, are in the changelog rather
than re-threaded here. Five command-line
tools ship with the package: `pyfs-qa`
(probes, physics regression, drift), `pyfs-workspace` (campaign
workspace init), `pyfs-matrix` (run-matrix upgrade, convert, pre-flight and run),
`pyfs-fsi` (the aeroelastic coupling executable), and `pyfs-manual`
(maintainer tool: compares a vendor manual against the command
database, reports what each build documents and what changed between
builds, and re-reads the page citations already written to check they
still point where they say; needs the `[manual]` extra). Two of
`pyfs-manual`'s six subcommands WRITE, and `register` is the only thing
in this package that edits the shipped command database from a reading:
it carries a build's documentation forward for the commands its edition
describes exactly as the edition before it did, and reports the rest for
a person. Both write only with an explicit `--write`.

## The idea in one paragraph

FlightStream is scripted through ASCII command files, and the solver is
under active development, with intermediate hotfix builds consolidating
user requests into stable releases; the command set evolves with it. This
package makes the FlightStream version an explicit input. A per-version command
database, with a manual page or probe-report citation on every entry and
empirical probe evidence for every verified status, backs a script builder
that refuses to
emit anything invalid for the requested version. Old versions are only ever
added, never dropped.

## The documentation

* [Software Requirements Specification](srs/index.md): the living SRS,
  from the founding requirements to the usage-feedback line, each with
  origin, status, and evidence.
* [Architecture overview](architecture.md): the layered pipeline and one
  section per subpackage, generated at every docs build from the live
  module docstrings. `pyflightstream.overview()` renders the same page
  offline.
* [Getting started](getting-started.md): install, pick a version, build a
  script, declare and pre-flight a campaign, read the results. Half an hour,
  and no solver until the last step.
* [Flight conditions](flight-conditions.md): what a row states about the
  flow it runs at, which quantity gets solved for, the units that ride
  the key names, and what to run on a matrix written before v0.9.0.
* [The workspace and the workflow](workspace-and-workflows.md): what a
  workspace is and what it is for, in plain language, then the path from a
  filled-in run matrix to results. Every artefact on it is lifted from an
  executed test, and it states what is NOT built as plainly as what is.
* [The numeric settings codebook](settings-codebook.md): the frozen
  encoding of the optional all-numeric settings table, for tools that
  cannot read strings. The page is the contract and a test holds the
  library to it.
* [Replaying a recorded run](tutorial-replay.md): what the manifest keeps,
  how to rebuild the exact invocation from it, how to tell whether the
  evidence still matches, and what a record cannot give you.
* [What a run cost](solver-cost.md): what a completed campaign spent, read
  from the records it already keeps rather than from a stopwatch.
* [Command reference](reference/index.md): generated from the database at
  every docs build, one page per manual chapter, with per-version evidence
  for every command. `pyflightstream.help()` renders the same database
  offline.
* [Which build do I have](builds.md): the release name and build number
  your solver prints, mapped onto the identifier to pass. The release
  name alone does not identify a build, and for the 26.12 builds it
  is not even the name the vendor sells them under.
* [Compatibility matrix](compatibility.md): every command against every
  registered FlightStream version, generated from the same database. Cells
  are filled only by evidence: for `documented`, the manual page or a
  committed probe report where no edition documents the command; for
  `verified`, `broken` and a measured `removed`, a committed probe
  report. Empty cells are
  honest gaps awaiting backfill.
* [House conventions](conventions.md): the naming and nomenclature rules
  the library holds itself to, generated from `reference.CONVENTIONS`,
  the same source as the offline `help()` section.
* [Mesh inputs and GUI-only operations](mesh-inputs.md): the supported
  workflow when a step exists in the GUI but has no scripting command,
  the canonical mesh input routes, and the mesh format policy.
* [Sister library (ITACA)](sister-itaca.md): the co-development model,
  the division of labor, and the cross-requirement convention shared
  with the ITACA analysis library.

## Evidence discipline

The three QA tiers behind the statuses:

* Tier 1 runs in CI without the solver: schema integrity, builder
  goldens, parser fixtures.
* Tier 2 probes command validity on a licensed machine; reports live
  under `reports/compat/` and statuses are promoted only from them.
* Tier 3 runs a physics regression matrix and a cross-version drift
  suite; reports live under `reports/physics/`.

The [campaign from a run matrix](examples/campaign_matrix.md) example
already walks the run-matrix to `campaign.toml` to pre-flight path
end to end; the LaTeX user guide (`guide/`) covers the full workflow.

## Planned next

The campaign walkthrough this section used to promise SHIPPED on
2026-08-19 as [the workspace and the workflow](workspace-and-workflows.md),
so the bullet is retired rather than left standing beside the page that
delivers it. What that page does not cover, it says so itself, in its own
closing section.
