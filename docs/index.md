# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. MIT licensed.

Status: v0.26.0 is the current release; the changelog records what
each release adds and what each one asks you to do.

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

## Who it is for

Someone who runs FlightStream from scripts rather than from the GUI, and wants
the script to be right for the build that will run it: one polar, or a
campaign of many rows declared in a run matrix, run locally or submitted to a
cluster, and post-processed into tables with no solver in the loop. You need a
licensed FlightStream to RUN anything. You need none to build and check a
script, to declare and pre-flight a campaign, or to rebuild the products of
runs you already have, and the documentation is written so that the solver is
the last step rather than the first.

## Where to start

1. [Getting started](getting-started.md): install, pick a version, build a
   script, declare and pre-flight a campaign, read the results. Half an hour,
   and no solver until the last step.
2. [Which build do I have](builds.md): the identifier to pass for the solver
   you have, which is the question a version-aware driver exists for.
3. [The workspace and the workflow](workspace-and-workflows.md): the reference
   chapter, from a filled-in run matrix to results.
4. [From the GUI to pyfs](gui-to-pyfs.md): if you know FlightStream from its
   GUI, each step you take there and the key that takes it here, or `not yet`.
5. Upgrading a workspace you already have? Read the newest page under
   *Migrating to newer versions* below before you upgrade, then
   [the release notes](release-notes.md) for anything older.

## The command-line tools

Five command-line
tools ship with the package: `pyfs-qa`
(probes, physics regression, drift), `pyfs-workspace` (campaign
workspace init, archive and migrate-geometries), `pyfs-matrix` (run-matrix upgrade, convert, pre-flight, run, read a mesh's boundary
inventory, collect a submitted job's outputs when they land, and post-process;
there is no separate submit command, because `run` on Linux with a cluster
profile submits rather than running here),
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
* [From the GUI to pyfs](gui-to-pyfs.md): each step of a FlightStream GUI
  session, from the geometry to the post, with the key that does it in a
  workspace, the solver commands that key emits and the builds they are
  verified on; or `not yet`, and the raw route that takes the step meanwhile.
* [Flight conditions](flight-conditions.md): what a row states about the
  flow it runs at, which quantity gets solved for, the units that ride
  the key names, and what to run on a matrix written before v0.9.0.
* Migrating to newer versions, newest first. Each page says what a release
  asks of a file you already have, and the one command that carries it across:
    * [Migrating to 0.25.0](migrating-to-0.25.0.md): frozen-solve averages,
      probe histories, sections and Cp by distribution, and optional surface
      exports; what posting a 0.24.0 record again recovers and what needs a
      new run.
    * [Migrating to 0.24.0](migrating-to-0.24.0.md): the numbers 0.23.0 published
      that 0.24.0 states differently, among them `ETAW` under incidence, the
      unsteady rotor table and the steady polar's axis columns; the averaging
      window a new unsteady row must state; and what posting again gives you
      without a solver run.
    * [Migrating to 0.23.0](migrating-to-0.23.0.md): every product table
      carries the flight condition it is a file of and no cell is ever blank.
      What changes in the bytes your reader parses, and the one command that
      moves the products you already have onto the named-group form.
    * [Migrating to 0.22.0](migrating-to-0.22.0.md): a row's rotor speed is a
      magnitude and the reference says which way the rotor turns. What to
      change in your rows and reference blocks, and which recorded points have
      to be re-run rather than renamed, because they turned the wrong way.
    * [Migrating to 0.21.0](migrating-to-0.21.0.md): the one command that
      renames a workspace written under 0.20.x, and what the `WALLTIME` unit,
      the HPC profile's `[log]` table and the build flag ask of a file you
      already have.
* [Release notes](release-notes.md): what each release from v0.8.1 to v0.17.0
  changed for a workspace that already existed. These stood on this page until
  0.24.0; the complete record is `CHANGELOG.md` in the repository.
* [The workspace and the workflow](workspace-and-workflows.md): what a
  workspace is and what it is for, in plain language, then the path from a
  filled-in run matrix to results. Every artefact on it is lifted from an
  executed test, and it states what is NOT built as plainly as what is.
* [Post-processing definitions](post-processing-definitions.md): the definition
  of record for every product and reduction the post stage writes: the
  averaging window, `time_average`, `per_blade`, `phase_locked`, the unsteady
  polar and the rotor coefficients. Where that page and the code disagree, the
  page is right; it marks the sections the code does not implement yet.
* [The test tiers and the licensed workspace](tiers.md): the three
  folders of the suite and what each proves, and `tests/tier3_licensed`,
  which IS a campaign workspace: nine matrices over one synthetic library,
  every capability of the matrix as a row, one test per row, and the qa
  physics cases judged against their references through the workflow.
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

* Tier 1 (`tests/tier1_offline`) runs in CI without the solver: schema
  integrity, builder goldens, parser fixtures, and the offline control
  over the tier-3 matrices.
* Tier 2 (`tests/tier2_validity`, `pyfs-qa probe`) probes command
  validity on a licensed machine; reports live under `reports/compat/`
  and statuses are promoted only from them.
* Tier 3 (`tests/tier3_licensed`) is a campaign workspace run on the
  licensed machine: nine matrices over a synthetic library, the qa
  physics cases among them judged against `qa/references/`; the
  cross-version drift suite (`pyfs-qa`) writes under `reports/physics/`.
  [The tiers page](tiers.md) walks it.

The [campaign from a run matrix](examples/campaign_matrix.md) example
already walks the run-matrix to `campaign.toml` to pre-flight path
end to end; the LaTeX user guide (`guide/`) covers the full workflow.
