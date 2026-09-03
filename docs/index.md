# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. MIT licensed.

Status: v0.11.0 is the current release; the changelog records what
each release adds and what each one asks you to do.

**v0.11.0 changes the run-matrix FILE FORMAT, and one command moves a
workspace.** The `ENTRY` column is now `PPROC` and names the post-processing
artifact, the `FS_SCRIPT` column is gone and a `LEGACY` row carries its recipe
code in its cell, and the `GEOMETRY` cell names the file with its extension.
Run `pyfs-matrix upgrade matriz.fs --in-place --inputs inputs` once in the
workspace: it rewrites the matrix, moves the groups library to `inputs/pproc/`
and strips the four rotor facts from the reference artifact. What you get is
the study stated once, in the workspace: the campaign is named after its
directory, the post-processing artifact says which exports, sections, plots,
probes and products every point leaves, the products are CSV tables the run
writes itself (`pyfs-matrix post` rewrites them with no solver), the boundary
order of a geometry is read from the file (`pyfs-matrix inventory`), a row may
state several rotors, and every point opens its geometry through a link
rather than a copy. The reproduction of the author's recorded campaign, script
by script and product by product, is the exit condition of GOAL-011 and is
what the release was built against.

**v0.10.1 changed no column of the run-matrix file and no cell you had
already written.** What it changed is what one cell MEANS. A rotor row's
`MOVING_BOUNDARIES` used to cite boundaries by their POSITION in one
geometry's order; those positions were right for the file they were
written against and named different surfaces in any file that ordered
them differently, and nothing said so. Write the names now, or the
FAMILY they belong to, and the package reads the geometry and resolves
them. Positions still work and now warn, naming what they actually
selected.

**It also carries a third run type, `unsteady`,** an unsteady run with
nothing turning, which is a new capability under a patch number by the
author's explicit exception. It is named here because a patch number
will not carry that news on its own, and it asks nothing of you: no
existing row changes. See the workspace and workflows page.

**v0.10.0 changes no column of the run-matrix file.** Two things still
want a look. Your solver preset now REACHES THE SCRIPT: twelve settings
and eleven of the solver's own spellings that used to be dropped are now
emitted, silently and with no warning, so a campaign whose preset states
anything non-default will move its numbers and wants re-baselining. And
five names became the package's inside `VAR_NAMES_VALUES`:
`ADVANCE_RATIO`, `RPM_SIGN`, `DELTA_THETA`, `REVOLUTIONS` and
`LOG_OUTPUT`, matched on the exact key, with a row spelling one of the
first two beside an existing `RPM` refused for stating the rotor speed
twice.

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
