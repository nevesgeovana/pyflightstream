# Release notes

What each release from v0.8.1 to v0.17.0 changed for someone who already had a
workspace: what moved, what broke, and the one command that carries a file
across. These notes stood on the home page until 0.24.0 and are kept here
unchanged, newest first.

**This page is not the changelog.** The complete record of every release,
including the ones after v0.17.0, is
[`CHANGELOG.md`](https://github.com/nevesgeovana/pyflightstream/blob/main/CHANGELOG.md)
in the repository. The releases that ask you to change a file you already have
each have a page of their own under *Migrating to newer versions*:
[0.23.0](migrating-to-0.23.0.md), [0.22.0](migrating-to-0.22.0.md) and
[0.21.0](migrating-to-0.21.0.md).

## v0.17.0

**v0.17.0 is the release that makes a sweep ONE RUN.** A steady matrix row
is one job: every point of it runs in one script and one solver process, and
the solver is never cleared between them, so each angle begins from the
previous one's converged solution and the sweep costs one setup instead of one
per point. That is the warm start, and it is what a polar sweep IS rather than
a switch on top of it; a row that wants the other behaviour writes
`COLD_START: True`. One job leaves ONE record, naming every point it ran IN
THE ORDER IT RAN THEM, because a warm sweep's order is part of its result.

**The run matrix carries nineteen columns.** `CONFIGURATION`, `GEOMETRY`,
`SYMMETRY`, `SYMMETRY_LOADS`, `NCPUS` and `WALLTIME` become columns of their
own, and `HIDDEN | RUN` moves to sit directly after `POL`. Each of the six was
expressible before, four inside the free variables cell and two inside the
setup artifact, so the release moves WHERE a fact lives and makes no fact
required: a row that states none of them reads exactly as it did. A file in
any older layout is upgraded on read, and the upgrade RENAMES NO RUN, because
the point tag is run identity and ends every run id in every existing
manifest. A column says nothing with `-`, and where one of the six says
nothing the older home still answers.

**A run needs a plan, pinned to the matrix it read.** `pyfs-matrix plan`
spends no solver time, pre-flights every point, and writes the receipt `run`
now refuses to start without; the receipt carries the matrix digest, so a
matrix edited between planning and running is visible rather than silent.

**A product is archived before it is rewritten, never lost.** A rebuild moves
the old product into `archive/<day and hour>/` beside it and writes the new one
in its place. `--overwrite` is gone: `--force-overwrite` keeps no copy and asks
for a confirmation, so it cannot be reached by habit.

**An unsteady row can state a wall clock.** `WALLTIME` arms a pair of
solver-side actions: a program that keeps its own clock and fires once, and a
script it rewrites that does nothing until the clock and the margin meet, and
then writes the run's exports. The margin is the setup's, twenty minutes by
default. A run the clock stopped is recorded `WALLTIME_REACHED`, which is NOT
a failure: the numbers up to that step are real and the record says where it
stopped. What is NOT measured, and is said here rather than only in a source
comment: whether the stop verb inside an action's script ends the RUN or only
that script. Settling it needs a licensed probe that moves one thing.

**Linux is the cluster, and no cell says so.** On Linux with a profile in
`inputs/hpc/h<>.toml` the run path renders that cluster's descriptor, hands the
job to the scheduler and returns without waiting, and the record is
`SUBMITTED`. The setup artifact stays multiplatform, so the same matrix,
unchanged in every cell, runs locally on Windows and submits on Linux, and
`NCPUS` is one number for both. **v0.17.0 had no collect stage**, so a submitted
job's outputs were collected by hand; 0.18.0 added `pyfs-matrix collect`.

## v0.16.0

**v0.16.0 was the sweep release.** A surface-section distribution is created
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

## v0.15.0

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

## v0.13.0 and v0.14.0

One refusal below no longer stands: since 0.23.0 a `[groups]` table keyed by a
word is accepted, and the product file carries the word. See
[what the post-processing artifact holds](workspace-and-workflows.md#what-the-post-processing-artifact-holds).

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
workspace of eleven run matrices whose goldens are rendered offline on every
commit.

## v0.12.0

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

## v0.11.0

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

## v0.10.1

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

## v0.10.0

**v0.10.0 changes no column of the run-matrix file.** Two things still
want a look. Your solver preset now REACHES THE SCRIPT: twelve settings
and eleven of the solver's own spellings that used to be dropped are now
emitted, silently and with no warning, so a campaign whose preset states
anything non-default will move its numbers and wants re-baselining. And
five names became the package's inside `VAR_NAMES_VALUES`:
`ADVANCE_RATIO`, `RPM_SIGN`, `DELTA_THETA`, `REVOLUTIONS` and
`LOG_OUTPUT`, matched on the exact key, with a row spelling
`ADVANCE_RATIO` beside an existing `RPM` refused for stating the rotor
speed twice. (`RPM_SIGN` beside `RPM` was refused for the same reason
until v0.21.1; since v0.22.0 a row's speed is a magnitude and the hand of
the rotation is `rpm_sign` on the rotor's block in the reference.)

## v0.9.0

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

## v0.8.1 and earlier

v0.8.1 before it was a patch: a run
matrix can name its geometry, so a workflow no longer builds a script
that opens nothing and solves whatever the solver already had in memory,
and a row can declare the symmetry a periodic sector needs. It reserves
three names inside the matrix's free cell, `GEOMETRY`, `SYMMETRY` and
`PERIODIC_COPIES`, which was its own upgrade action. Earlier releases,
and what each of them registered or broke, are in the changelog rather
than re-threaded here.

## How each supported build reached its level (as recorded at v0.29.0)

These notes stood in the README until 0.30.0. The live levels are on
[Which build do I have](builds.md) and in `pyflightstream.support_table()`;
the sentences below are what each level rested on when they were written.

"Supported" covered four different states, so it is now four named
values (`pyflightstream.SupportLevel`), every one of them derived from
the evidence rather than declared:

| Version | Vendor name | Support level | What that means here |
|---|---|---|---|
| 25.000 | 25.0 | `documented` | Vendor build 12162024, December 2024. Registered on 2026-08-09 so that published work run on it has an identifier that resolves, and its own manual read command by command on 2026-08-10. Not yet `operational`, and the blocker is solver evidence rather than database rows: no command has been measured on this build, and the level stops at `documented` for that reason before the workflow is even considered. 26.000 shows it, having every workflow command and the same level. Its manual documents 272 commands and 268 are emittable, the difference being four readings withheld where a version row cannot express a layout. Behind the evidence gap there is also a workflow one: this edition runs the trailing-edge autodetection from inside a `PHYSICS` block and the standalone command arrives at 26.000 |
| 25.100 | 25.1 | `documented` | Vendor build 5062025, May 2025. Registered for the same reason. Its manual documents 274 commands and 270 are emittable, with the same four layout withholdings, and it uses the same `PHYSICS` block as 25.000. The 25 series checks out an EDU licence rather than the full feature set, so what either of these builds refuses may be the licence rather than the build; that is not yet measured |
| 26.000 | 26.0 | `documented` | Vendor build 10202025, October 2025. Its manual documents 276 commands and 274 are emittable, the two withheld for the same layout reason. Nothing has been probed on it either, which is what holds it at this level. The CAD BODY operations, the four CAD primitives and the three CCS mesh chapters do not exist in this edition; they arrive with 26.100. What it does document, and what its sixteen CAD rows are, is CAD import and conversion plus the curve and cross-section commands |
| 26.100 | 26.1 | `operational` | The February 2026 build, and the last of the pre-26.12 builds to reach this level, on 2026-08-08. It was held at `verified` less by the solver than by the database: the per-edition sweep that day found 40 commands its own manual documents and this database had no row for, so the emitter refused them and the minimal end-to-end workflow could not be built. With those rows written the workflow builds. Probe coverage is still thinner here than on the newer builds, the harness reaching only commands that carry a probe spec; the compatibility matrix carries the live counts |
| 26.101 | 26.1 | `operational` | The May 2026 build. Commands drafted from the manual with page citations, with the first harness promotions on 2026-08-08, which also carried it to the level where the minimal end-to-end workflow builds. It sits at a hotfix index and does NOT inherit from 26.100: the two are separate vendor releases under one name |
| 26.120 | 26.12 | `operational` | Probe evidence from a licensed machine, and the minimal end-to-end workflow builds |
| 26.121 | 26.12 | `operational` | Hotfix build 1. It inherits the 26.120 records except where a probe on this build overrode them; the compatibility matrix marks every inherited cell and counts them |
| 26.122 | 26.12 | `operational` | Hotfix build 2, vendor build 8092026, registered 2026-08-10 the day after it was issued. Its manual documents the largest command surface of the nine editions, 372 against 364 for the one before it and 371 for the one after, which deletes a command from its chapter body. Measured on 2026-08-11: 84 commands probed on this build (83 verified, 1 broken) and the Tier 3 matrix passing 30 of 30 metrics (`reports/physics/PHY-26122_2026-08-11_rotor.yaml`). The rest of its record is still inherited from 26.120 and the matrix marks every inherited cell. The run refuted the inheritance once, on `AIR_ALTITUDE`, which is broken on the base releases and works here |
| 26.123 | 26.12 | `operational` | Hotfix build 3, delivered 2026-08-16 and registered 2026-08-17, the day after. It is the first build in this project that INHERITS NOTHING, by the design decision, so it claims support only for what has been measured or read on IT rather than on 26.120. Read the level as a statement about evidence and not about the build: it reached `operational` the same day, in two steps. First 369 of the 371 commands its own edition documents were compared word for word against the edition before it and given a row. Then a probe run measured 85 of them on this build, 84 accepted and one refused (`reports/compat/CMP-26123_2026-08-17_full-sim.yaml`), which is one more verified than 26.122 has and the same single broken command, `NEW_OFF_BODY_STREAMLINE`, that three builds now carry on their own evidence. The emitter still refuses the commands that carry no row at all, and the enumeration of exactly which, with their count in its own header, is committed as `tests/tier1_offline/goldens/absent_on_26123.txt`. The number is NOT repeated here: this sentence said 45 against a golden that says 43, in the paragraph whose whole purpose is that the gap is a number a reader can check. Its manual is 417 pages like 26.122's and every page outside seventeen is text-identical, so a page citation transfers where the seventeen do not touch it |
| 26.124 | 26.12 | `operational` | Hotfix build 4, vendor build 8172026, delivered and registered 2026-09-14. Its package carries the 26.123 manual itself, byte for byte, so every command 26.123 documents was carried forward on that identity (every file's digest, RPT-050) and nothing was inherited from 26.120; only the executable differs. A probe run then measured it on this build: 86 verified and the same single broken command, `NEW_OFF_BODY_STREAMLINE` (`reports/compat/CMP-26124_2026-09-14_full-sim.yaml`) |

`operational` is the level that claims a user can get from geometry to
a loads file, and it is checkable rather than asserted: it holds only
when `pyflightstream.support.minimal_workflow(version)` builds, which a
tier 1 test builds for every version reported at that level.

Not sure which one you have? Every install prints its release name and
its build number when it starts, and the generated
[Which build do I have](https://nevesgeovana.github.io/pyflightstream/builds/)
page maps that pair onto the identifier to pass. The release name alone
does not identify a build.

Canonical identifiers use the YY.XXX scheme, the last digit indexing
vendor hotfix builds, so 26.121 is hotfix build 1 of the 26.12 release.
The vendor reuses a release name across builds, so a release name may
name more than one, and the families it has produced are not all alike: one is a release with its hotfixes, the other is
two separate releases that happen to share a name. Which builds sit in
either is a fact about the registry rather than about this page, so it
is not written here; the refusal enumerates them from the registry and
the generated build page carries the tally. Pass the canonical
identifier. A vendor name is unique only until the vendor
ships the next build under it, which is why a script should not rely on
one. The ordered list
in `src/pyflightstream/commands/_meta.yaml` is the only ordering
authority, and it orders releases, not support: 26.100 is newer than
26.000 and both sit below 26.120. Supported versions are only ever
added, never dropped, which is why the February 2026 build entered as
26.100 and the May build it displaced was appended as 26.101 rather
than either being renamed away. The compatibility matrix in the docs is generated
from the database at build time.
