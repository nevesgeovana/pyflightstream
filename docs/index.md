# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. MIT licensed.

Status: v0.16.0 is the current release; the changelog records what
each release adds and what each one asks you to do.

**v0.16.0 is the sweep release.** A surface-section distribution is created
AFTER the solver is initialised; created before, the distribution returns the
declared number of sections and every one of them is empty. A steady row now
CREATES the probe points it exports, instead of asking the solver to export
something nobody made; a probe entry prescribes a rectangular
or a circular plane, point by point, or cites a points file the user wrote; and
`[probes]` became `[[probes]]`, a list of tables, so one artifact can probe
several frames.

What a campaign WRITES moved with it. A simulation's collected outputs live
under `sims/<sim>/datapoints/DP-<point>/`, the per-polar tables under
`post/<matrix>/polars/`, and the flow-field samples under
`post/<matrix>/probes/` whatever the run type was. Each polar and group also
gets one derived file, `SUPER-...csv`, whose columns are a superset of
everything the workspace knows about that simulation: if you have to open a
second file to know something about it, that file failed.

Two new answers a study wants before it is run and after. `pyfs-matrix plan
--cost` tables what each POINT will cost: mesh size, trailing edges marked,
farfield layers, viscous coupling, run type, time steps, processors, an
expected time, and the number of recorded runs that estimate was fitted
from. The table says under every printing that the time is an extrapolation
from this workspace's own recorded wall times and not a measurement, and a
point with no comparable recorded run gets no number at all. And a probe
table now says WHERE each sample is, with the frame it is measured in,
which an unsteady export never stated at all.

**A swept row now runs and is judged end to end.** Each point collects its
outputs into its own folder, `sims/<sim>/datapoints/DP-<point>/`, named by the
same point tag that ends the run id and names the generated script. Until this
release every point of a row wrote into one shared folder, so from the second
point onward the standard assessor found two files that both read as loads
tables and refused rather than guess between them. Name your outputs per
point, as before: two points of one row still may not share a file name,
because the per-point products are named after it and would collide there
even though the folders no longer do. A workspace recorded under the older
layout is read exactly as before.

**What changes for you at v0.16.0.** This is the most breaking release of
the set, and the break is first: `[probes]` IS NOW `[[probes]]`, a list of
tables, and the old spelling is REFUSED BY NAME, so every 0.15.0 artifact
that declares probe lines must be edited. That is a recorded decision rather
than an accident. Beside it: the five names the 0.14.0 polar rename
deprecated are gone; a simulation's collected outputs are under
`sims/<sim>/datapoints/DP-<point>/`, one folder per point, and a workspace
holding either older folder is still read;
the per-polar tables moved to `post/<matrix>/polars/` and are named by the
point convention with the swept variable written literally as `sweep`; and
`sweep.csv` is gone in favour of `campaign_sweep.csv`, which it duplicated
byte for byte.

**What changes for you at v0.15.0.** The run matrix LOSES A COLUMN:
`SWEEP_TYPE` is gone, because a sweep is applied to a variable that DEFINES
the flight condition and the `FLIGHT_CONDITION` cell says which by carrying
the word `sweep` where that key's value would be. Run `pyfs-matrix upgrade
<path> --in-place`, which folds the cell and DOES NOT RENAME A RUN: a held
angle is carried at every point, so the point tags that end every `run_id`
in your manifests are the ones the converted file plans under, and a resume
after the upgrade finds its records. The one row it refuses to convert is
one that sweeps BOTH angles, which is one row per sideslip and each needs a
POL of its own. `CLOCK_MOTION` is now REQUIRED on a row that states a
`MOTIONS` list, naming the rotor that owns the time step; the flat
pre-0.15.0 form is exempt. The `airframe` and `blades` family SELECTORS are
REFUSED since 0.15.0, not warned about: declare the set in your reference's
`[aliases]` table and cite it by name, because those two decided what a
blade IS from a pattern over the family name and a mesh spelled another way
was guessed wrong in silence. An alias of the same name is read FIRST and
keeps its own meaning, so a reference that already declares `airframe` is
untouched. New: `--ignore-missing-families false` on `plan` and `run` turns
a family the opened mesh does not carry from a skip into a refusal, for a
run against the one geometry you believe carries everything.

**What changes for you, and what you must do.** v0.13.0 changes no
column of the run-matrix file. Two inputs that used to plan are refused at
plan time now, each naming the cell: a row carrying a key its run type does
not register (a misspelt key planned READY and reached the solver as
nothing), and a pproc artifact whose `[groups]` table is keyed by a word or
whose groups cite a boundary name the opened geometry does not carry.
Python 3.11 leaves the supported window: the floor follows SPEC 0, the
scientific-python schedule, computed on 2026-09-09 as Python 3.12, numpy
2.2 and pandas 2.3, and the window now moves by a published rule rather
than by choice. The hand-built physics runner is gone: `run_physics`,
`run_drift` and the four `build_phy*_script` builders are removed, and
`pyfs-qa physics --workspace <root>` and `pyfs-qa drift --workspace <root>`
read the physics cases as rows of a campaign workspace; an import of a
removed name says so and names the replacement. Anything you wrote against
`runs.json` or the campaign products meets three moves: the manifest key
`broken_commands` is `waived_commands` and the schema stamp is
`pyfs-manifest/3` (the old key is still read; its removal is promised for
0.18.0 and has moved three times, each move on a re-count of the recorded
manifests that still carry it); `plan.json`,
`campaign_sweep.csv` and the product tables live under
`post/<matrix stem>/`, one folder per matrix; and a registered post stage is
called with a third keyword, `matrix_stem`. `sweep_editions` is
`manual_editions` and `propose_type` takes its two strings by keyword; the
old spellings warn and name the release that removes them. A simulation
folder has three managed subfolders, since `parsed/` was never written to;
an empty one left by an earlier release is left alone. At v0.14.0 one
artifact key is renamed: `[products] her_polar_format` is
`custom_polar_format`, and the four Python names `HerPolarTable`,
`her_polar_file_name`, `write_her_polar_format` and
`read_her_polar_format` are spelled `custom`; the old spellings were read
and warned until 0.16.0, WHICH REMOVES THEM. The format itself is untouched:
only the spelling that named a person was ever deprecated.

**What it adds.** An unsteady row may say when its exports begin,
`EXPORT_UNSTEADY_AFTER_REV` or `EXPORT_UNSTEADY_AFTER_ITER`, and the run
registers the two solver actions that make the solver export from that
step on, measured on 26.123. The products stage writes a PROV-JSON
provenance document per point, every reduction of an unsteady row (the
time average over the window the row states, the phase-locked passages,
the per-blade split), and the polar tables in the custom polar format
when the pproc artifact asks for it. The geometry library may hold one
folder per geometry beside the flat layout, `pyfs-workspace
migrate-geometries` moves a library into it, and `pyfs-workspace archive
<root> <sim_id>` zips one recorded simulation. Every command-line option
states what it reads, the run record says how the solver was called
(`executor`, `export_window`, the waived commands by their name), and the
whole test suite is organized by tier, with the licensed tier a campaign
workspace of seven run matrices whose goldens are rendered offline on every
commit.

**v0.12.0 changed no column of the run-matrix file and no cell already in
one.** It added two ways to say what you were already saying. A setup
artifact may carry a
`[flight_condition]` table holding the fluid pins (`RHOkgm3`, `MUPas`,
`ASMPS`, `TK`, `PPA`), so a thirteen-point polar states its campaign's
constants once instead of thirteen times; a row that states a pin still
overrides the setup's, and the resolved state is the same state either way,
which a test holds to the rendered script BYTE FOR BYTE. And an unsteady run
that meshes nothing turning may state its clock as `DELTA_THETA` and
`REVOLUTIONS`, resolved against the rotor speed whose azimuth the step
measures, where before only the seconds and the step count were accepted.
The reproduction workspace of the reference campaign needs both,
which is why that release existed.

**Two derived numbers moved with it, and a row already written felt
them.** A rotor speed derived from `ADVANCE_RATIO` is emitted at four
decimals, the reference precision: 473.1723 rev/min where the unrounded
derivation gives 473.17227304. And the default loads assessor judged a
point's OWN declared outputs, so a two-point sweep whose points name their
own tables is judged where it used to be refused as ambiguous. Re-baseline
against v0.12.0 rather than comparing its tables with v0.11.0's.

**v0.11.0 changed the run-matrix FILE FORMAT, and one command moved a
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
rather than a copy. The reproduction of the reference campaign, script
by script and product by product, is the exit condition of GOAL-011 and is
what that release was built against.

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
nothing turning, which is a new capability under a patch number, by
an explicit exception. It is named here because a patch number
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
workspace init, archive and migrate-geometries), `pyfs-matrix` (run-matrix upgrade, convert, pre-flight and run),
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
* [The test tiers and the licensed workspace](tiers.md): the three
  folders of the suite and what each proves, and `tests/tier3_licensed`,
  which IS a campaign workspace: seven matrices over one synthetic library,
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
  licensed machine: seven matrices over a synthetic library, the qa
  physics cases among them judged against `qa/references/`; the
  cross-version drift suite (`pyfs-qa`) writes under `reports/physics/`.
  [The tiers page](tiers.md) walks it.

The [campaign from a run matrix](examples/campaign_matrix.md) example
already walks the run-matrix to `campaign.toml` to pre-flight path
end to end; the LaTeX user guide (`guide/`) covers the full workflow.

## Planned next

The campaign walkthrough this section used to promise SHIPPED on
2026-08-19 as [the workspace and the workflow](workspace-and-workflows.md),
so the bullet is retired rather than left standing beside the page that
delivers it. What that page does not cover, it says so itself, in its own
closing section.
