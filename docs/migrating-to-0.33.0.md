# Migrating to 0.33.0

> Frozen record: not edited after its release.

Keep a copy of the workspace and install the release in a separate Python
environment before running existing matrices. Planning and post-processing can
check most changes without starting FlightStream. The package's dependencies
and extras are the ones 0.32.0 declared; only the `dev` extra gains
`mkdocstrings[python]`, for the documentation build (NFR-29).

Most of 0.33.0 is internal: the largest modules were cut into packages, and
every public name, console command, emitted script and product byte stayed
where it was, with the exceptions the sections below name: one public name
removed (`stamp_derived_campaign`), one change to the emitted scripts (the
step counter of the unsteady rows), and products that change only for a
continued point and for the fields of another 26.124 build. What a user
meets is a new run status, one lookup of the run matrix over both of its
homes, a way to clean a saved geometry, and a few new options. The sections
are in the order of their impact on an existing workspace; each names what a
script of yours must allow.

## A run can be marked failed: FAILED_MARKED

`pyfs-matrix mark-failed --sims 2006,2007 --reason "wrong mesh" --apply`
records that a run which ended, `CONVERGED` or otherwise, was wrong: every
record of the named simulations takes the new status `FAILED_MARKED`, and
keeps under `marked` the status it had (`from`), when (`at`) and why
(`reason`). Without `--apply` it previews. `runs.json` is archived first, so
`pyfs-matrix restore runs` undoes it (FR-309). The status is defined on
[Restore and rebuild](restore-and-rebuild.md#mark-a-run-failed-after-the-fact-since-0330).

What a reader must allow: `FAILED_MARKED` begins with `FAILED`, and the post,
the cost estimate and `delete-sims` treat it as any failure. A script of
yours that lists the statuses one by one, rather than testing the `FAILED`
prefix, gains a ninth value. The manifest schema stays `pyfs-manifest/3`.

**A `runs.json` that holds `FAILED_MARKED` is not readable by an older
release**: a release before 0.33.0 has no such status in its set. Keep 0.33.0
or later on every machine that reads that workspace, a cluster and a
workstation joined by `sync` included, or restore the archived copy before
going back to an older release.

## A run matrix is found in either home

A matrix may sit in the workspace root or in `inputs/matrices/`. Since 0.33.0
every `pyfs-matrix` command that takes a matrix (`upgrade`, `convert`, `plan`,
`inspect-setups`, `run`, `post` and its `--additional-pproc`,
`rebuild --matrix`) and every routine that looks one up by name (`rename`,
the rebuild's scan, the Excel synchronization, the physics check of `pyfs-qa`)
reads it through one lookup over both homes (FR-310;
[the two matrix homes](sync-folders-and-matrix-homes.md#the-two-matrix-homes)):

- a bare file name or a stem is looked up in both homes; a path that names
  its folder is read from that folder, as before;
- a name in both homes with the same bytes is read once;
- a name in both homes with different bytes is refused before any work,
  naming both paths; `post` keeps its 0.32.0 behaviour, a warning naming both.

What changes for an existing workspace: `rebuild` without `--matrix` now
refuses a stem held in both homes with different bytes, where it left it out
with a note, and the Excel synchronization reads a name held in both homes
with equal bytes once, where it refused it. A bare matrix name given outside
the workspace, found in a home while the working directory holds a different
file of that name, is refused naming both, where 0.32.0 read the working
directory's file. Keep one copy of each matrix, or make the two identical.

## A saved geometry can be cleaned: `inventory --clean`

A saved simulation keeps the unsteady solver actions of the run that saved it,
and an action the script creates with the same name does not replace the saved
one. `pyfs-matrix inventory <file>` now names those actions on every call, and
`pyfs-matrix inventory <file> --clean` removes them (FR-308;
[Mesh inputs](mesh-inputs.md#actions-saved-in-the-geometry-since-0330)). For a
file saved by 26.120 in metres, `--clean` also puts the `GLOBAL`, `MOTION`,
`POST`, `WAKE`, `SOLVER`, `ACOUSTIC`, `STABILITY` and `AEROELASTIC` blocks back
to the content of a fresh import and keeps the meshes and the applied boundary
conditions; a file of another build or unit, 26.124 included, has only its
actions removed, and the command says so (FR-312).

What stays: the file is first copied to `<file>.bak-<stamp>`, an existing
sidecar is kept unless `--overwrite`, and a cleaned file has new bytes and so
a new hash: a campaign staged after the clean records the new hash, and runs
staged before it keep theirs.

`pyfs-matrix plan` reads the geometry of every `unsteady` and
`unsteady_rotor` row and warns, naming the rows, the file, each saved action
and the `--clean` command; it never refuses on that account, and the plan it
writes is the one it writes without the warning (FR-313).

## Every unsteady row registers the step counter

On a build that documents the unsteady solver action (26.122 and later), every
`unsteady` and `unsteady_rotor` row registers the step counter, so a local run
shows its progress bar on every unsteady row. A row asking no per-step export
registers it alone: it counts, writes no export file and triggers no exports
script (FR-314;
[Unsteady rotor](workflow-unsteady-rotor.md#exports-that-begin-after-a-threshold)).

- A script 0.33.0 emits for an unsteady row without per-step exports, on 26.122 or later, differs from the one 0.32.0 emitted by the counter's three registration lines; the row runs a small Python program after every time step, written into the point's `actions/` folder, with the interpreter that built the script (FR-314).

What stays: such a row's `march_strategy` is still `single_march`, its record
names the count-only program as `action_program`, and a run 0.32.0 recorded
without the counter still continues. This is the one change of an emitted
script in 0.33.0; a comparison of your own scripts against 0.32.0 sees exactly
these three lines on such rows and nothing elsewhere.

## Collecting and posting some simulations, and a job that ended

`pyfs-matrix post [matrix] --sims 2006,2007` rebuilds only the named
simulations' products, archiving and rewriting their files; every other
simulation's files and `products.json` entries stay, and the super files are
left as the last whole post wrote them, named under `partial.not_rebuilt`.
`pyfs-matrix collect --sims` sweeps only the SUBMITTED records of the named
simulations and limits its post to them (FR-307;
[Post-processing definitions](post-processing-definitions.md#posting-and-collecting-some-simulations-since-0330)).
Without `--sims` both behave as before.

The HPC profile's `[log]` table takes `job_end_files`, the files the scheduler
writes when a job ends. When every one exists in a SUBMITTED point's folder
and its solver log does not, `collect` records the point `FAILED_EXECUTION`
with the last 20 lines of each file, instead of waiting for ever (FR-311;
[Builds, local runs and clusters](workflow-builds-and-hpc.md#where-a-submitted-point-runs)).
A profile without the key waits as before.

## Storage: a listing and a forced delete

`pyfs-matrix free-space --list` prints, after each recipe step, every path
the step would touch or touched, with its size and what happens to it
(FR-305). `pyfs-matrix delete-sims --force` deletes a simulation whose record
is still SUBMITTED, which `delete-sims` otherwise refuses; the call recorded
in `storage_management.json` now states `force` and the statuses each
simulation had (FR-306; [Storage and sync](storage-and-sync.md)). Without the
two options the commands behave and print as before.

## Setup keys: on a row, and the moments model

A matrix row may state setup keys in its `VAR_NAMES_VALUES` cell under their
native names, over the preset its `SET` cell names, for that row only. `plan`
warns for every such row; a key the preset does not state, or states with an
equal value, is accepted, and one the preset states with a different value is
refused, naming both values. The run record's setup snapshot lists them under
`from_row` (FR-316;
[A row may state setup keys over its preset](workflow-input-library.md#a-row-may-state-setup-keys-over-its-preset)).

The setup key `moments_model` (`PRESSURE` or `VORTICITY`) states the moments
model; unstated, the script states `PRESSURE` as before, byte for byte
(FR-317). On a row turning a rotor, a setup stating `vorticity_drag_families`
and no `moments_model` now states `VORTICITY`, warned at plan and recorded
under `derived`, and `moments_model = PRESSURE` beside the drag list is
refused at plan (FR-318). A setup of yours that names the drag list on a rotor
row and relied on the pressure moments must state `VORTICITY` or drop the
list. The audit of every choosable command of the solver chapters, RPT-106,
gave these keys and the per-step `unsteady_solver_actions` (FR-319).

## The plan names the families a row's geometry lacks

`pyfs-matrix plan` warns, once per pproc artifact and per family, when a
section distribution or a force plot group declares a family the geometry of
some row does not carry, naming every such row; a misspelled family beside a
good one is named the same way. Every row plans as before and no emitted
script changes; `--ignore-missing-families false` refuses what it refused
before (FR-320; [Post-processing artifact](pproc-artifact.md)).

## Continuations: a converged march, and the window of a chain

`RESTART: {ADDITIONAL_REVS=n}` and `{ADDITIONAL_ITERS=n}` now continue an
`unsteady` or `unsteady_rotor` point whose latest run CONVERGED, once per
request; the continuation's record states the request under the new key
`restart`. `{FINISH_PENDING}` on a CONVERGED run is refused with the reason,
and the plan lists every point a `RESTART` key does not continue (FR-96;
[What a RESTART row continues](continuation-recovery.md#what-a-restart-row-continues-0330)).

Values that change: the averaging window of a continued point now ends at the
last step of the whole march, read across every run of the chain, so the plots
table, the reductions, the unsteady polar and the rotor table of such a point
change. A point that continues nothing posts byte for byte as before.

## The post: fields of another build, and the drift warning

A sampled velocity field of a 26.124 run on a build other than the one its
convention was measured on is now written with the measured convention, with
one warning per point and `proven` false in its `products.json` entry, where
0.32.0 skipped it (FR-153; [Sampled fields](sampled-fields.md#a-run-on-another-build)).
The per-revolution drift warning judges a force or moment column against the
largest load of its kind in its plot group, so it no longer fires on in-plane
components near zero; the `_DRIFT_PCT` columns are byte-identical (FR-180;
[`per_revolution`](post-processing-definitions.md#per_revolution)).

## The signature on standard error

Every command now always ends with its signature on standard error: a stream
that cannot encode the drawing gets it with replacement marks, and a drawing
that cannot be built is replaced by one line (FR-315). Standard output and
exit codes do not change.

## The architecture: code moved, nothing public did

The largest modules were cut into packages of smaller modules: `run` sits
above `workspace` as a row of its own (AD-09), each constant has one home
(AD-10), `post.guides`, `run.records`, the `results` root and
`workspace.inputs` were split (AD-11), `cases.workflows` and `run` became
facades over ordered modules (AD-12, AD-14), and the post's product families
became sibling modules (AD-13), under the architecture guards of AD-08. None
of this moved a public import path, a console command or option, an emitted
script or a product byte: every name every `__all__` of 0.32.0 offered still
imports from the same dotted path, except `stamp_derived_campaign`, removed
by its own decision (below) and named as such by the parity script, and
`scripts/check_parity.py` compares the release with the tag `v0.32.0` for
the public names and signatures, the commands and options, the emitted
scripts of the golden and tier-3 campaigns (FR-314 the one named exception)
and the products of a post over a recorded workspace, stamps normalized
(AD-15). Some names are now defined in a new module and re-exported where
they were, for example `parse_sectional_loads` in
`pyflightstream.results.sectional_loads`, re-exported by
`pyflightstream.fsi.loads`; import them from the path you used.

What narrows is the star import: a public module that now declares `__all__`
gives, through `from <module> import *`, its own public names and no longer
the names it imports; those still import by name (NFR-29).

**Removed:** `pyflightstream.cases.stamp_derived_campaign`, the writer of the
`[campaign.derived_from]` marker, which no code of the package called
(decision 9 of the 0.33.0 scope). `load_campaign` still reads the marker of a
campaign file an earlier release stamped, and still refuses such a file once
it is edited.

## Reports no longer publish an executable digest

The committed reports and records identify a solver executable by its build,
and a digest field reads `withheld; build <build>`: an executable digest is no
longer published in the package's tree, and the report writers of the
compatibility, physics and drift checks write that form for a recorded digest
(NFR-31). What stays: a run record still keeps its own `fs_exe_sha256`, in
your workspace, and the products carry it from there. A report you generate
names its files inside `<workspace>` rather than by a machine path. A local,
uncommitted copy of the executable baseline that keeps the digests still
compares a binary by its bytes.

## The documentation

The site is grouped into Tutorials, How-to guides, Reference, Explanation and
Project, and its reference is generated from the code: the Python API
reference and the command-line reference, under Reference in the menu, carry
every public name and every option (NFR-29). Exported functions document their parameters, results and
failures in numpydoc form (NFR-30). No page moved, so a link or a bookmark
to a page still lands on it. A one-page `pyfs-matrix` cheatsheet, every
subcommand and option by stage, joins the [PDF guides](guides.md).
