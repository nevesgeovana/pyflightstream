# RPT-029: the type-checker exemption re-count at 0.8.0.dev0 (2026-08-18, amended twice on 2026-08-19, re-measured 2026-08-20, 2026-08-24, 2026-09-02, 2026-09-09 and 2026-09-29)

> **Amended before this file was ever committed, and the amendment is the
> report's own reproduction rule catching its own author.**
>
> The first version stated 63 modules and said both runs were taken with
> `src/pyflightstream` carrying no modification and no untracked file
> against `5f2dcf1`. That was true when the runs were made and had stopped
> being true by the time the file was staged: ten agents were working this
> tree in parallel and one of them added `src/pyflightstream/qa/cost.py`.
> mypy walks the FILESYSTEM, which is exactly what the paragraph below
> warned about, so the count it published was a count of a tree that no
> longer existed.
>
> Both runs were repeated on the settled tree. **The error count and the
> unclean-module count did not move: 275 errors in 21 files.** The module
> total moved from 63 to 64, and `qa/cost.py` is clean under both
> configurations, which is why the first two numbers survive unchanged.
>
> **Second amendment, 2026-08-19, and it is the FIRST one that was found
> by a reviewer rather than by the author.** Between the first amendment
> and this one, two more waves landed, `pyflightstream.results.tables`
> lost its exemption on evidence, and the headline sentence was RETYPED
> twice to follow the module total. Retyping is the cheap remedy of the
> two this report names below, and it is legitimate for the module total
> alone. Applied to a compound sentence that also asserts an error count
> and a dirty count, it welded a PRE-removal error total onto POST-removal
> module and dirty counts: the removed module carried one error, so the
> total could not still be 275 while the dirty count fell to 20.
>
> The report then held three mutually contradictory statements of one
> measurement, and its own guard could not see two of them: the guard
> matches the sentence FORM `mypy recount <date>: <n> errors in <d> of <m>
> modules`, and the disagreeing statements were the tool's own output
> lines and a markdown table.
>
> **The expensive remedy was applied this time.** Both runs were made
> again on the settled tree, and the headline, the reproduction outputs,
> the per-module table, the code table, the concentration lines and the
> delta table are all that run rather than edits to the previous one.
> THIS BLOCK IS LIVE: it carries the latest re-measurement, whose date
> the headline sentence below names, and each earlier run keeps its
> section further down; the two lines here were last replaced by the
> run of 2026-09-15 EVENING, on the tree that carries the 0.21.0 point name,
> its renaming command and the sweep of any flight-condition variable, and
> replaced again by the run of 2026-09-20 on the settled 0.25.0 tree, and
> by the run of 2026-09-23 on the settled 0.26.0 tree, and by the run of
> 2026-09-24 on the 0.27.0 tree once its fourth block had merged, and by the
> run of 2026-09-24 on the 0.27.0 tree that adds the length floor
> `_lengths.py`, and by the run of 2026-09-25 on the 0.28.0 tree whose block C
> adds the surface translator (G45) and the surface average (G25), and by the
> run of 2026-09-25 on the 0.28.0 tree whose block D adds the FSI's blade
> properties (G41), and by the run of 2026-09-28 on the 0.29.0 quality-gate
> candidate (GOAL-034 Q1), whose 0.29 work brought the tracked package from
> 104 to 128 modules, and by the run of 2026-09-28 on the v0.29.0 release
> tree, and by the run of 2026-09-28 on the 0.30.0 storage-and-sync
> gate-fixing tree (`feat/0-30-storage-sync`, the nine tier-1 house-style
> guards), whose one new module, `workspace/storage.py`, brought the tracked
> package from 128 to 129, and by the run of 2026-09-29 on the 0.30.0 tree
> once its quasi-steady rotor work had merged, whose three new modules,
> `cases/qsteady.py`, `fsi/wing.py` and `post/qsteady.py`, brought the
> tracked package from 131 to 134, and by the run of 2026-09-29 on the
> v0.30.0 release tree, and by the run of 2026-09-29 on the 0.31.0 release
> candidate (`feat/0-31`, every 0.31 item merged), whose four new modules,
> `cases/corrections.py`, `post/corrections.py`, `post/harmonics.py` and
> `workspace/fields.py`, brought the tracked package from 134 to 138, and by the run of 2026-09-29 on the same candidate once the console change had merged, whose one new module, the floor module `_console.py`, brought it from 138 to 139, and by the run of
> 2026-09-29 on the 0.32.0 development branch (`feat/0-32`) once its
> preparation step had laid down the ten contract modules of the 0.32 work
> packages, which brought it from 139 to 149, and by the run of
> 2026-09-30 on the integrated 0.32.0 branch (`feat/0-32`, every 0.32
> package merged), whose one further module, the CCS floor
> `cases/_ccs.py`, brought it from 149 to 150, and by the run of 2026-09-30 on
> the 0.33.0 branch of work packages WP1 and WP2 (`feat/0-33-wp12`), whose one
> new module, `results/sectional_loads.py`, brought it from 150 to 151, and by
> the run of 2026-09-30 on the 0.33.0 branch of the functional requirements
> FR-310 to FR-314 (`feat/0-33-fr`), whose four new modules, `_fsm_fresh.py`,
> `cases/_unsteady_actions.py`, `workspace/_geometry_clean.py` and
> `workspace/_matrix_homes.py`, brought it from 150 to 154, and by the run of
> 2026-09-30 on `rel/0-33` with both branches merged, which holds the 150 and
> all five new modules, 155, and by the run of 2026-09-30 on the 0.33.0
> branch of the setup requirements FR-316 to FR-319 (`feat/0-33-setup`),
> whose three new modules, `cases/_setup_keys.py`, `cases/_setup_link.py`
> and `workspace/_row_setup.py`, brought it from 150 to 153, and by the run
> of 2026-09-30 on `rel/0-33` with all three branches merged, which holds
> the 150 and all eight new modules, 158, and by the run of 2026-09-30 on
> the 0.33.0 branch of work package WP3 (`feat/0-33-wp3`), whose fourteen
> new modules, cut out of four existing ones (AD-11), brought it from 158
> to 172, and by the run of 2026-09-30 on the branch of FR-320
> (`feat/0-33-famwarn`, from `rel/0-33` with all three branches merged),
> whose one new module, `cases/_skipped_families.py`, brought it from 158
> to 159, and by the run of 2026-09-30 on `rel/0-33` with WP3 and FR-320
> merged, which holds the 158 and all fifteen new modules, 173, which the
> run of 2026-10-01 on `rel/0-33` with FR-96 also merged, adding no module,
> reads again, and by the run of 2026-10-01 on `rel/0-33` with work package
> WP4 (AD-12) also merged, whose package `cases/workflows/` of 24 modules
> replaced `cases/workflows.py` and brought it from 173 to 196, and by the run of
2026-10-01 on `rel/0-33` with work packages WP4, WP5 and WP6 merged, whose new
modules brought it from 196 to 219 and whose WP6 took `pyflightstream.run`
out of the exempted set, so that the dirty count fell from 18 to 17 and the
error total from 1122 to 192, and by the run of 2026-10-01 on the 0.34.0
branch of work package WP8 (`feat/0-34-wp8`), whose six model modules cut
out of the `cases` root (AD-16) brought it from 219 to 225 and whose typed
moved lines took the error total from 192 to 184, and by the run of
2026-10-01 on `rel/0-34` with the wave-1 work packages of 0.34.0 merged,
which brought it to 234 modules and the error total to 160 in 16, and by the
run of 2026-10-02 on `rel/0-34` with the wave-2 packages merged, which
brought it to 236 modules and left the error total at 160 in 16. (An
> earlier run of 2026-09-19 measured the 0.20.0 tree at 617 errors in 18 of 85
> modules and the 0.24.0 tree at 661 in 18 of 93; the 0.28.0 release tree read
> 863 errors in 18 of 104 on 2026-09-25; the 0.29.0 quality-gate candidate
> read 923 in 18 of 128 on 2026-09-28, the same date as the release tree;
> the 0.30.0 tree once its quasi-steady rotor work had merged read 998 in
> 18 of 134 on 2026-09-29, the same date as the v0.30.0 release tree, which
> read 1065 in 18 of 134, and as the 0.31.0 release candidate; the
> 0.32.0 preparation step read 1084 in 18 of 149 on 2026-09-29;
> the 0.33.0 branch of WP1 and WP2 read 1137 in 18 of 151 and the branch
> of FR-310 to FR-314 1133 in 18 of 154, the branch of FR-316 to FR-319
> 1137 in 18 of 153 and `rel/0-33` with WP1, WP2 and FR-310 to FR-314 merged
> 1133 in 18 of 155, `rel/0-33` with all three branches merged 1133 in
> 18 of 158, the branch of WP3 1130 in 18 of 172, the branch of FR-320
> 1133 in 18 of 159, `rel/0-33` with WP3 merged 1130 in 18 of 172 and
> `rel/0-33` with WP3 and FR-320 merged 1130 in 18 of 173, all on
> 2026-09-30, and the branch of FR-96 1125 in 18 of 158 and `rel/0-33`
> with FR-96 merged 1122 in 18 of 173 on 2026-10-01, and `rel/0-33` with WP4
> merged 1122 in 18 of 196 on the same date, and `rel/0-33` with WP4, WP5
> and WP6 merged 192 in 17 of 219 on the same date, and the 0.34.0 branch
> of WP8 184 in 17 of 225 on the same date, and `rel/0-34` with the
> wave-1 work packages merged 160 in 16 of 234 on the same date;
> measurements of different
> trees fall on one date, so each is named by its tree rather than by the date
> alone.):
>
>     Found 159 errors in 16 files (checked 292 source files)
>     Success: no issues found in 292 source files
>
> Every figure below is that re-measurement.

The result, in the sentence every record of it carries:

**mypy recount 2026-10-06: 159 errors in 16 of 292 modules.**

The quoted top block and the sentence above are the 2026-10-06 run recorded
in the dated section at the end. The module total is the 292 of `rel/0-38`
after the 0.38.0 work packages, with 159 errors in sixteen dirty modules.
The 282 were the tracked package on `rel/0-37` after the 0.37.0 work packages.
The 269 were the tracked package on `rel/0-36` after the wave-1 cuts and MM.
The earlier 236 were the tracked package on `rel/0-34` with the wave-2
packages of 0.34.0 merged, two more than the 234 of the wave-1 tip,
each reported clean: `pyflightstream._textio` (NFR-32) and
`pyflightstream.workspace.actuator_profiles` (FR-347).
The 234 were the total on `rel/0-34` with the
wave-1 work packages of 0.34.0 merged, fifteen more than the 219 of
`rel/0-33` with work packages WP4, WP5 and WP6 merged, each of the fifteen
reported clean (the section at the end names them). The cuts of WP8, WP9a
and the probe catalog type every moved line, so the error total falls from
192 to 160 and the dirty count from 17 to 16: `pyflightstream.qa.specs`
reports none, so its override is deleted and the exempted set is the sixteen
dirty modules. The branch of WP8 alone read 184 in 17 of 225.
The 219 were the total the tracked package held with work packages WP4,
WP5 and WP6 merged into `rel/0-33`, twenty-three more than the 196 of the
tree with WP4 alone, each of the twenty-three reported clean. The error total
fell from 1122 to 192 and the dirty count from 18 to 17 because WP6 made
`pyflightstream.run` a facade over typed modules and deleted its override
(decision 7): the run root carried 930 of the 1122 errors and now reports
none. The 196 were the total with work package WP4
(AD-12) merged into `rel/0-33`: `cases/workflows.py` is cut into the package
`cases/workflows/` of 24 modules, each clean, twenty-three more than before.
Before it the total was the 173 the tracked package holds on `rel/0-33` with
work package WP3, FR-320 and FR-96 merged (FR-96 adds no module),
fifteen more than the 158 of `rel/0-33` with work packages WP1 and WP2, FR-310 to FR-314 and FR-316 to
FR-319 merged, each of the fifteen clean (the fourteen modules AD-11 cut
out of `post.guides`, the `results` root, `run.records` and
`workspace.inputs`, and `cases/_skipped_families.py` from FR-320); those
158 were eight more than the integrated 0.32.0 branch's 150, each of the
eight clean (`results/sectional_loads.py` from WP1 and WP2; `_fsm_fresh.py`,
`cases/_unsteady_actions.py`, `workspace/_geometry_clean.py` and
`workspace/_matrix_homes.py` from FR-310 to FR-314; `cases/_setup_keys.py`,
`cases/_setup_link.py` and `workspace/_row_setup.py` from FR-316 to
FR-319); those 150 were eleven more than v0.31.0's 139, each of the eleven
clean
(the ten contract modules of the preparation step and `cases/_ccs.py`);
v0.31.0's own 139 were five more than
v0.30.0's 134, each of the five clean;
the error total sits inside the exempted set, the number of modules holding
an exemption fell from eighteen to seventeen with WP6, and the shipped
configuration is green over all 234. The run at 139 was taken by `python scripts/mypy_recount.py`
on the 0.31.0 release candidate at `33c1d7ef`, which the script reported
clean, and the runs at 149 and 150 are stated in their own sections at the end; the v0.30.0 release tree's reading, 1065 errors in 18 of 134, is
stated in its own section below.

THE NINETIETH TO THE NINETY-THIRD ARRIVED AT 0.24.0 and all four arrive
CLEAN: `post/axes.py`, the one home of the frame conventions; `cases/windows.py`,
the one resolver of an unsteady row's averaging window; `_expressions.py`, the
floor module that evaluates a pproc equation; and `post/equations.py`, which
applies them to the unsteady polar. None of the four is among the 18 files the
run reports. The count rose from 639 to 661, 22 errors, on sites in modules
that already carried exemptions, `pyflightstream.run` above all; the run
measured the tree as it is and assigns no share of the 22 to a change.

The previous reading, 639 errors in 18 of 89 modules on 2026-09-18, measured the 0.23.0 tree.

THE EIGHTY-SEVENTH, EIGHTY-EIGHTH AND EIGHTY-NINTH ARRIVED AT 0.23.0 and all
three arrive CLEAN:

- `post/guides.py`, the generated pproc guides of item 11;
- `workspace/rename_groups.py`, the migration that moves a workspace's polar
  products onto the named-group form for item 14;
- `_tokens.py`, created when the owner decided the `-` token converges on `NA`
  and `qa` needed to reach it without importing `post`. It holds one constant
  and a docstring and imports nothing from this package.

Not one of the three appears in the per-file breakdown. The count rose from 626
to 639 on sites in modules that already carried exemptions, which is worth
saying plainly: **the three new modules did not add one error between them.**

ITEM 11 MOVED TO 0.24.0 AFTER THIS PARAGRAPH WAS WRITTEN, and `post/guides.py`
is still on disk and still measured, because the recount measures the TREE and
not the release scope. The sentence describing what the module is FOR is the
part that is now ahead of the release; the count is not.

The eighty-sixth is `run/rename.py`, added at 0.21.0 for the command that
moves a workspace to the point names, and it arrives CLEAN: it appears nowhere
in the per-file breakdown of the `scripts/mypy_recount.py` run, and the FILE
count is unchanged at 18. The error count moved from 617 to 626 while the
0.21.0 naming work changed, among others, `run/__init__.py`,
`cases/__init__.py`, `cases/matrix.py` and `workspace/matrix.py`; the run
measured the tree as it is, not the difference between the two trees, so no
share of the 9 is assigned to a file here. The guard asked for this
re-measurement, as it did for the eighty-fifth and the eighty-fourth: the
records said 85 while the package held 86.

The eighty-fifth was `script/rotor_vocabulary.py`, added at 0.20.0 for the
per-build rotor vocabulary, and it arrived CLEAN by the same test, at 617
errors in 18 of 85 modules. Its figures are not repeated in this part of the
report, which carries ONE live measurement.

The runs before this one keep their own sections below, except the
eighty-fifth's: it fell on the same day as this one, and its figures are in the
paragraph above rather than in a section of its own.

## Re-measured 2026-09-14: the eighty-fourth module arrived, and the debt grew inside the exempted set

That run found 585 errors in 18 files with every override off, and no issue
in any of the 84 source files with the shipped configuration. Every statement
of this section is about that run.

The eighty-fourth is `run/collect.py`, added at 0.18.0 for the collect stage,
and it arrives CLEAN: it appears nowhere in the per-file breakdown, and the
FILE count is unchanged at 18, so the new module carries no exemption and adds
no debt of its own.

THE ERROR COUNT MOVED AND THE MODULE DID NOT MOVE IT, which is the part worth
stating rather than leaving for a reader to infer from two numbers. It went
from 370 to 585 between the 2026-09-11 run and the 2026-09-14 run. Measured per
file on that run: `run/__init__.py` alone carries 451 of the 585, and it is the module
0.17.0's submission and warm-start work and 0.18.0's continuation all landed
in. The remaining seventeen files carry 134 between them.

WHAT THIS DOES NOT ESTABLISH, said because two numbers a fortnight apart
invite a causal reading they do not support: that run measured the tree as it
was then, not the difference between two trees. That one file holds 451 errors
is measured; that the growth of that file is the whole of the 215 is not, and
nothing here re-ran the older tree to find out.

THE TRACEABILITY GUARD ASKED FOR THIS RE-MEASUREMENT rather than a reader did,
for the second time and in the same way: the records said 83 while the package
held 84, and the guard went red at the tip of the range that added the module.

The eighty-third was `post/superfile.py`, added at 0.16.0, and it arrived
CLEAN by the same test: neither the error count nor the file count moved when
it landed. Its own figures are not repeated here, because this report carries
ONE live measurement and a second set of numbers in the prose is how it came
to hold three contradictory ones at once; the earlier run keeps its own
section below.

## Re-measured 2026-09-09, second run: two modules arrived with the 0.14.0 series, and the debt moved inside the exempted set

The first run of the day, superseded by this one and kept here as the
erratum the in-place replacement would otherwise erase: `Found 345
errors in 18 files (checked 79 source files)`, `Success: no issues found
in 79 source files`, 345 errors on 110 distinct source lines.

`python scripts/mypy_recount.py` on 2026-09-09, at the tree that holds the
per-step series of 0.14.0 (PFS-2031.18.01): 356 errors in 18 of 80
modules. Two modules arrived, `post/series.py` and the private
`post/_tables.py` the review's architecture lens asked for (the CSV writer
and the product errors below both, so neither imports the other), both
type-clean, and the tracked total moved 79 to 81, which is what the tier-1
guard asked about. The
error total moved 345 to 356, and none of it is the new module's: the
eleven sit inside the eighteen modules exempted since the first count,
`pyflightstream.run` leading the table at 189 on 31 lines (the export
window's clock and the raw commands of the record are written into the
same untyped base dict the earlier errors sit on). No override was added
or removed; the override count and the dirty count both still read 18.

## Re-measured 2026-09-09, first run: two modules arrived with the 0.13.0 night, and the debt moved with them

`python scripts/mypy_recount.py` on 2026-09-09, at the tree that holds the
0.13.0 scope: 345 errors in 18 of 79 modules. Two modules arrived (the
qa driver that reads the workspace, `qa/matrix.py`, and the counter
program template of the unsteady actions, `run/_actions_counter.py`),
two dirty modules left the dirty set with the physics runner's
retirement, and the total rose by 27 with the actions and reductions
code under the existing overrides. Two overrides were retired with the rewrite,
`pyflightstream.qa.cli` and `pyflightstream.qa.physics`, so the override
count and the dirty count both read 18 (the invariant the tier-1 guard
holds). The sentence above is this measurement; the earlier ones stay
below as the history of the figure.

## Re-measured 2026-09-02: one module arrived, and the error total had gone stale unwatched

`_fsm.py` (PFS-2028.00, the saved-simulation boundary reader) moved the module
total to 76 and `tests/test_traceability.py` refused the tree until every
record of the count moved with it. The module delta is the whole of what that
guard asked about: **75 to 76 modules**, and again on 2026-09-02 when `post/products.py` joined: **76 to 77 modules**, the eight new errors all inside the already-exempted modules the tool lists above.

**The error total moved too, 276 to 310, and none of it belongs to the change
that triggered the re-count.** Not one of the four modules 0.10.1 touched
appears in the debt table below: `_fsm`, `cases.workflows`, `workspace` and
`exceptions` are all absent, which is to say all four are type-clean. The
entire delta sits in `pyflightstream.run`, which went from 108 errors on 18
lines to 142 on 29, and that module was last changed by the 0.10.0 release on
2026-09-01.

So the sentence was already stale when this session opened, and nothing was
wrong with the guard. `pyproject.toml`'s own header says to read the two
numbers differently: the ERROR TOTAL is a dated measurement that moves with
the code and with the dependencies' own stubs, while the MODULE TOTAL is
re-counted from the tracked tree on every run. 0.10.0 added no module, so the
module total did not move, so nothing asked, and the error total drifted by 34
between one release and the next with every record agreeing on the old figure.
That is the residual of a guard that watches one of two numbers, and it is
recorded here rather than presented as a finding of this release: the design
was deliberate and is written down in the file that carries it.

**The exempted set did NOT move.** The same 20 modules are exempted, every one
of them still reports at least one error, and no override was added or removed.
`_fsm.py` arrives type-clean and adds no debt to the ratchet, which is the
third floor module in a row to do so.

## Re-measured 2026-08-24: one module arrived and nothing else moved

`_atmosphere.py` (PFS-2027.03) moved the module total to 74 and
`workspace/flight_condition.py` (PFS-2027.02) to 75, and
`tests/test_traceability.py` refused the tree until every record of the
count moved with it. **That is the whole delta: `73 -> 74 -> 75` modules,
`276 -> 276` errors, `20 -> 20` dirty files.** The floor module appears
in neither error list, so it arrives type-clean and adds no debt to the
ratchet, and no override was added or removed.

### The measurement was wrong once during this session, and the trap is worth more than the correction

The first re-run here reported **283 errors in 25 files**, and a
detached worktree at the `v0.8.1` tag reported the same. Two independent
readings agreeing is persuasive, and the conclusion drawn from them was
that the records had drifted and the shipped release had been
misdescribed. **That conclusion was false and it was written into this
report before it was checked.**

The cause was the environment, not the source. `types-PyYAML` was not
installed, so mypy raised `Library stubs not installed for "yaml"` in
`versions.py`, `utils/manual.py`, `utils/database.py`, `qa/compat.py`
and `qa/drift.py` -- five modules, one error each, in BOTH invocations.
The FILE count reconciles exactly: 20 dirty + 5 stub-only files = 25.
**The ERROR count does not, and it is left undecomposed rather than
explained away.** `276 + 5 = 281`, not 283. An earlier version of this
paragraph disposed of the residual two with "the same five files counted
under a second code", which is incoherent -- five files under a second
code is five errors, not two -- and a V and V pass refused it. The bad
run was not decomposed per file and per error code before the
environment was corrected, so the two are simply unaccounted for. What
is measured is that with the stubs installed both invocations return the
recorded figures exactly; the bad run's total is not a measurement of
this source and is not reconciled here.

**What caught it was this report's own invariant, not the arithmetic.**
`test_the_recorded_dirty_count_is_the_number_of_overrides_that_exist`
holds the dirty count equal to the number of `ignore_errors` overrides,
on the reasoning that the re-count finds an error in every exempted
module and in no other. 25 dirty against 20 overrides is not a drifted
number, it is an impossible one: it claims five unexempted modules are
dirty while the config claims none are. A guard that ties two records to
each other refused a measurement that a guard checking either one alone
would have accepted.

**The rule this produces, for whoever re-runs it next.** A recount taken
in an environment missing a stub package is not a measurement of the
source, and it will look like drift rather than like a broken
environment, because every count moves together and in the same
direction. Install `.[dev,fsi,geom]` and `types-PyYAML`, or run
`python scripts/mypy_recount.py`, and check the dirty count against the
override count BEFORE believing any story the numbers seem to tell.
CI's `types` job is the reference environment and it is green.

Taken at version `0.8.0.dev0`, on the working tree at commit `5f2dcf1` plus
the wave-1 changes of 2026-08-18, with every `ignore_errors`
override in `[tool.mypy]` turned off and nothing else about the configuration
changed. It replaces the 2026-08-03 figure, 223 errors in 21 of 53 modules,
which four separate records still stated as though it were current. A fifth
record, the override blocks themselves, states no number and needed no
correction; it is counted with the others below because it is the inventory
the numbers describe.

No override was removed. That is not restraint, it is the measurement: the set
of modules that report an error with the overrides off is EXACTLY the set of
modules the overrides name. Nothing outside the 18 is dirty, and nothing
inside the 18 is clean (20 until 2026-09-09), so there is no override here whose removal could be
justified on evidence today and no clean module quietly going unchecked.

THOSE FOUR NUMBERS SAID 21 UNTIL 2026-08-20, which is the third recurrence
of the defect this report was amended twice for and the reason its
reproduction is a script now. `results.tables` was removed from the exempted
set and the delta table two sections down records that removal correctly; the
prose around it was the pre-removal edition welded onto post-removal figures.
At 21 the sentence above is self-contradictory rather than merely stale: 21
exempted against 20 dirty leaves one exempted module clean, which is exactly
what it denies. A V and V pass found it, not the guard, because the guard
parses the ONE re-count sentence and nothing else.

## Why this was measured at all

OPS-2006.11.01 exists because the plan for clearing the type-checker
exemptions rests on a per-module error table, and that table was written on
2026-08-03, three releases ago. A planner reading it would have sized the
grind at 223 errors over 53 modules. Neither number survives contact with the
tree, and nothing in the repository would have said so: the ratchet test
guarded the exempted SET and the config guarded the clean modules, but no
guard compared any written record against the package.

## How to reproduce it

**IT IS ONE COMMAND SINCE 2026-08-20**, and that is the structural half of
this report's own defect rather than a convenience:

    python scripts/mypy_recount.py

It runs both invocations and emits every figure below from ONE run: the dated
sentence, both tool lines, the per-module table, the per-code table and the
concentration list. The failure this report was amended twice for is a
sentence retyped while the tool output beside it was not, and that failure is
now not available: there is nothing to retype. It also prints `git status
--short`, so a reader of its output can see whether the tree was settled, and
it writes its config to a temporary directory rather than into the repository.

The manual procedure is kept below because the script has to be checkable
against something.


The configuration used is `[tool.mypy]` exactly as committed, minus the 18
override blocks (20 until 2026-09-09). It was supplied as a separate config file rather than by
editing `pyproject.toml`, so the measurement never required the shipped
configuration to be in a state the repository does not ship:

    [tool.mypy]
    files = ["src/pyflightstream"]
    ignore_missing_imports = true
    disallow_untyped_defs = false
    warn_return_any = false

    python -m mypy --config-file <that file> --no-color-output

The final line of that run is the measurement:

    Found 159 errors in 16 files (checked 292 source files)

The same run with the shipped configuration, overrides and all, is green:

    Success: no issues found in 242 source files

mypy walks the FILESYSTEM rather than the git index, so the state of the
working tree is part of the measurement, and this report has already been
corrected once for exactly that reason: the numbers above are the
re-measurement taken on the settled wave-1 tree, not the first run's. The
sentence the first version carried, that both runs were taken against an
unmodified `src/pyflightstream`, is the check that failed rather than the
check that passed, because the tree changed under a measurement that had
already been written down.

Re-running these commands in a tree that carries uncommitted work will not
reproduce these numbers, and the difference will not announce itself. What
makes the drift catchable rather than silent is not this paragraph: it is
`tests/test_traceability.py::test_the_recorded_module_total_is_the_one_the_package_actually_has`,
which re-counts the tracked package on every run and fails when a record
states a total the tree no longer has. That guard is what produced this
amendment.

### The environment the count depends on, and it does depend on it

    python   3.12.0 (Windows)
    mypy     2.3.1
    numpy    2.5.3
    xarray   2026.7.0
    pandas   3.0.6
    pydantic 2.13.5

This matters more than it looks. `[tool.mypy]` deliberately does not pin
`python_version`, so the check runs under whichever interpreter invokes it,
and a large share of the errors below are `arg-type` findings against the
stubs shipped by numpy, xarray and pandas rather than against anything this
package declares. A count taken on a different leg, or after a dependency
bumps its stubs, will not be this number. That is why the error total is
recorded as a DATED measurement and why nothing in the test suite pins it.

The module total is different in kind and is guarded:
`tests/test_traceability.py` re-counts the tracked `.py` files under
`src/pyflightstream` on every run and fails when a record states a different
number. The 53 went stale silently precisely because nothing did that.

The consequence is deliberate and is written here so it is not read as a
defect: **the next commit that adds a module to the package turns that test
red.** The remedy is one of two and the test's own message names both. Re-run
this re-count and re-date it, which is the honest answer. Or state the new
total in every record at once, which is cheaper and leaves the error figure
older than the module figure. What the guard makes impossible is the third
option, and the third option is what happened between 2026-08-03 and today.

## The debt, per module (historical)

**Superseded by the recount dated 2026-09-19 above.** The following per-module
table, per-code tally and source-line concentration discussion retain earlier
measurements for history; they do not break down the current recount.

    errors   lines   module
       142      29   pyflightstream.run
        79      13   pyflightstream.qa.probes
        22       9   pyflightstream.script.solver_setup
        17      16   pyflightstream.script.helpers
        13      13   pyflightstream.script
         8       2   pyflightstream.qa.specs
         6       6   pyflightstream.probes.planar
         5       5   pyflightstream.workspace.inputs
         2       2   pyflightstream.cases
         2       2   pyflightstream.cases.matrix
         2       2   pyflightstream.commands
         2       2   pyflightstream.farfield
         2       2   pyflightstream.fsi.nodes
         2       2   pyflightstream.probes.geometry
         1       1   pyflightstream.fsi.driver
         1       1   pyflightstream.post.writers
         1       1   pyflightstream.qa.cli
         1       1   pyflightstream.qa.physics
         1       1   pyflightstream.script.entities
         1       1   pyflightstream.workspace.naming
       ---     ---
       310     111   20 modules of 76

`pyflightstream.results.tables` stood in this table on 2026-08-18 with one
error and is absent from it now. That is the row the exemption removal rests
on, and it is left out rather than shown at zero: a module with no error is
not debt, and a table of the debt that lists it would need a reader to know
which zeros mean clean and which mean unmeasured.

By error code:

    269  arg-type
      9  return-value
      8  assignment
      6  misc
      5  operator
      5  union-attr
      3  call-overload
      2  var-annotated
      1  attr-defined
      1  dict-item
      1  index

The code column is read from the bracketed code that ENDS each line and not
from the first bracket on it. That is worth one sentence because reading the
first bracket is wrong in a way that looks right: a message about `list[str]`
offers `[str]` before it offers its real code, and a tally built that way
reported four codes this checker does not emit.

## The second column is the one to plan with

The 2026-08-03 table had one column, and the plan built on it says two modules
carry 73 percent of the debt and sizes the small modules at an afternoon each.
The error count is a poor size estimate here, and the re-count shows why
rather than asserting it: **356 errors sit on 112 distinct source lines** (re-measured 2026-09-09, second run;
the 2026-08-19 pass read 310 on 111, and the 2026-08-03 table's own
figures are the ones this paragraph analyses).

While reading that table a second defect in it surfaced, small and worth one
sentence because it is the same class: its prose says "the eleven with one or
two errors", and its own rows list thirteen such modules. The re-count's rows
are the fact; the prose beside them is now written to be countable against
them.

The concentration is extreme at the top. Six lines produce 73 of the errors,
better than a quarter of the whole count, because each is a call site that
mypy reports once per argument it cannot match:

    13  src/pyflightstream/script/solver_setup.py:898
    12  src/pyflightstream/run/__init__.py:2502
    12  src/pyflightstream/run/__init__.py:2507
    12  src/pyflightstream/run/__init__.py:2519
    12  src/pyflightstream/run/__init__.py:2557
    12  src/pyflightstream/run/__init__.py:2583

`run` reads as 108 errors and is 18 lines, 6.0 errors per line.
`script.helpers` reads as 17 and is 16, so it is nearly one error per line and
is genuinely more scattered work than its rank suggests. Sizing the grind by
errors overstates `run` and `qa.probes` and understates everything shaped like
`script.helpers` and `script`, which have the widest spread relative to their
totals.

This is a planning observation and not a claim that the top lines are easy.
One `**` splat rejected per field may be one annotation or it may be a
signature that is genuinely wrong; the re-count does not answer that and did
not try to.

## What moved since 2026-08-03

| | 2026-08-03 | 2026-08-19 | 2026-08-20 | delta since 08-03 |
|---|---|---|---|---|
| modules in the package | 53 | 71 | 73 | +20 |
| modules exempted | 21 | 20 | 20 | -1 |
| modules held clean | 32 | 51 | 53 | +21 |
| errors with the overrides off | 223 | 274 | 276 | +53 |

The third column is the release's own last measurement, taken on 2026-08-20
after `workspace/trailing_edges.py` and `_mesh.py` landed. Its two new modules
are both clean, and the two errors it adds are both in
`pyflightstream.workspace.inputs`, which went from three to five: an already
excused module, which is the pattern the column beside it describes rather
than an exception to it.

Read the middle two rows together. Twenty modules were added over four
releases and every one of them is clean, which is the ratchet doing exactly
what it was built to do: new code is type checked from the day it lands. The
debt grew by 53 errors entirely INSIDE the modules that were already excused,
where nothing is watching. Both halves of that are worth knowing before anyone
plans the grind, and neither was visible from the old table.

THE EXEMPTED COLUMN MOVED DOWN FOR THE FIRST TIME, which the 2026-08-18
edition of this table could not show because it had not happened yet.
`pyflightstream.results.tables` was excused on 2026-08-03 and is clean on
2026-08-19: deleting `_as_workspace` took its last error with it. That is one
override removed on evidence, and it is the direction the `[tool.mypy]` header
has promised since the ratchet was written.

## The item's own premise does not survive reading, and this is where it is written down

OPS-2006.11.01 states, as the reason it exists, that "the packaging file
carries twenty-one excused blocks against the nineteen recorded, the two
unlisted ones being the workspace input and naming modules".

That is false. It is recorded here as false rather than quietly worked around,
because the item's purpose sentence will outlive this session and the next
reader would otherwise go looking for a discrepancy that is not there.

`pyproject.toml` carries 20 `ignore_errors = true` blocks as this commit
leaves the file. Two of them are:

    pyproject.toml:276   module = "pyflightstream.workspace.inputs"
    pyproject.toml:280   module = "pyflightstream.workspace.naming"

`MYPY_EXEMPTIONS` in `tests/test_traceability.py` carries 20 names, and the
same two are among them:

    tests/test_traceability.py:198   "pyflightstream.workspace.inputs",
    tests/test_traceability.py:199   "pyflightstream.workspace.naming",

The third record is the debt table, which lives in this repository's
local-only plan ledger and so cannot be cited here by a name a reader of this
remote could open. It recorded both modules from the beginning, in the
2026-08-03 table that is preserved beneath the new one, on the rows reading
`3  workspace.inputs, script.helpers` and `1  script.entities, commands,
workspace.naming, results.tables,`. The two public records above settle the
question on their own.

So the count is 20 in the configuration against 20 in the test record, the
ledger table agrees with both, and nothing is unlisted. Where "nineteen" came
from is not recoverable from the tree; the two modules named as missing are
the two that appear at the END of an alphabetically sorted list, which is the
shape of a list read short rather than of a list that was short.

The line numbers above are a convenience and will drift as these files change.
The durable citation is the anchor text: the two `module = "..."` assignments,
the two quoted names in the frozenset, and the two table rows. The equality
itself is not left to prose either;
`test_the_two_modules_called_unlisted_are_listed_in_both_homes` asserts it,
and `test_the_recorded_dirty_count_is_the_number_of_overrides_that_exist`
asserts that the recorded 20 is the number of overrides that actually exist.

## The records reconciled in the same commit

Five records carried the 2026-08-03 measurement.

1. `pyproject.toml`, the `[tool.mypy]` header comment. Corrected, and it now
   distinguishes the dated error total from the guarded module total.
2. The 20 override blocks in `pyproject.toml`. Matched and correct as they
   stand. No override was ADDED; one was deleted, on the evidence that its
   module is clean.
3. `MYPY_EXEMPTIONS` in `tests/test_traceability.py`. The frozenset LOST one
   name, `pyflightstream.results.tables`, because that module became clean and
   its override was deleted on evidence; its comment carries the re-count
   sentence. This item said the frozenset was unchanged and that the set had
   not moved, eleven lines above the comment recording the removal.
4. The debt table in this repository's local-only plan ledger, which is why it
   is described here rather than named: this remote is public and that record
   is not. Re-counted, with the 2026-08-03 table kept beneath it so the delta
   is readable, and with the stale "other 32 held clean" replaced.
5. `docs/srs/nonfunctional-requirements.md`, the NFR-27 paragraph, which
   states "223 errors in 21 of 53 modules" twice. **NOT corrected here.** That
   file is a requirement sentence and this session does not hold the seat that
   moves one; the correction is proposed to the author instead. Until the accepting seat
   takes it, NFR-27 is the one record still reading 223 of 53, and a reader
   who lands there first should come back to this report.

## The sweep behind that list, and the two records that keep the old number

The five were not taken on trust. Every tracked file carrying the string
"21 of 53 modules" was swept, and the sweep names two files the list above
does not:

    CHANGELOG.md
    docs/srs/index.md
    docs/srs/nonfunctional-requirements.md
    pyproject.toml
    tests/test_traceability.py

`pyproject.toml` and `tests/test_traceability.py` still appear because they now
carry BOTH figures, the 2026-08-03 one as history and the re-count beside it,
which is the intended state.

The two the list did not name are records of a different kind and are
deliberately untouched.
`CHANGELOG.md`'s entry is a released section and the SRS revision history row
in `docs/srs/index.md` is dated 2026-08-03. Both state what was true on their
date and both are correct as they stand; editing either would be rewriting
history rather than correcting a claim, which is the same distinction the
repository's own currency guard draws when it excludes released sections and
everything under `reports/` from the live prose it polices. A record that says
"on 2026-08-03 the first run reported 223 in 21 of 53" has not gone stale. A
configuration comment that says "the first run reported" in the present tense
of a planner reading it today had.

## What this report is not

It is not the grind, and it removes no exemption. Mixing a removal into a
re-measurement makes both unreadable: the ratchet test only shrinks, so a
removal is legible only against a count taken before it. This is that count.

## Re-measured 2026-09-23, the v0.26.0 release tree: three errors fewer, the same eighteen modules

`python scripts/mypy_recount.py` on 2026-09-23, at the tree tagged v0.26.0: 710 errors in 18 of 97 modules,
against 0.25.1's 713 in 18 of 97. No module arrived and none left; the three
errors that went were in the post stage's products module, rewritten around
the post log and the reducer-stated samples. The override count and the dirty
count both still read 18. The sentence above is this measurement; the earlier
ones stay below as the history of the figure.

## Re-measured 2026-09-24, the 0.27.0 tree after its fourth block: two modules arrived clean, twenty-six errors more

`python scripts/mypy_recount.py` on 2026-09-24, on a clean tree at the merge of
the fourth block of 0.27.0: 736 errors in 18 of 99 modules, against the v0.26.0
tree's 710 in 18 of 97. The two modules that arrived are private helpers
published beneath the layers that share them, `_decimal.py` and
`run/_wake_edge_verdict.py`, and both arrive clean: the dirty modules are still
eighteen and the shipped configuration is green over all 99. The twenty-six
errors more sit inside the exempted set; the run module carries 554 of the 736,
on the record builders the 0.27.0 blocks extended. The sentence at the top of
this report is this measurement; the earlier ones stay above as the history of
the figure.

## Re-measured 2026-09-24, the 0.27.0 tree with the length floor: one module arrived clean

`python scripts/mypy_recount.py` on 2026-09-24, on a clean clone of the commit
that publishes `_lengths.py` (the metres of each length unit, which the cases
layer converts the actuator disc and the volume section with): 761 errors in 18
of 100 modules. The same script on a clean clone of that commit's parent
measures 761 errors in 18 of 99 modules, so the new module arrives clean and
moves no error; the twenty-five errors between the parent's 761 and the 736 of
the section above arrived with the commits between the two runs, all of them
in the exempted set (the run module carries 578 of the 761). The dirty
modules are still eighteen and the shipped configuration is green over all
100. The sentence at the top of this report is this measurement; the earlier
ones stay above as the history of the figure.

## Re-measured 2026-09-24, the v0.27.0 release tree

`python scripts/mypy_recount.py` on 2026-09-24, at the release commit of v0.27.0: 812 errors in 18 of 100 modules,
against 0.26.0's 710 in 18 of 97. Three modules arrived clean (`_decimal.py`,
`run/_wake_edge_verdict.py`, `_lengths.py`); the errors more sit inside the
exempted set, most on the run module's record builders, which carry 628 of the
812. The dirty count still reads 18 and the shipped configuration is
green over all 100 modules. The quoted mypy lines above are this run's.
The sentence at the top of this report is this measurement; the earlier ones
stay above as the history of the figure.

## Re-measured 2026-09-25, the 0.28.0 tree with the surface translator: two modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-25, on the 0.28.0 block C tree
(`results/surface.py`, the VTK-to-Tecplot translation of G45, and
`post/surfaces.py`, the package's surface average of G25): 863 errors in 18 of
102 modules, against the v0.27.0 release tree's 812 in 18 of 100. Both new
modules arrive clean; the fifty-one errors more sit inside the exempted set, on
the run module's record builders the 0.28.0 blocks extended. The dirty count
still reads 18 and the shipped configuration is green over all 102 modules. The
quoted mypy lines above are this run's. The sentence at the top of this report
is this measurement; the earlier ones stay above as the history of the figure.

## Re-measured 2026-09-25, the 0.28.0 tree with the FSI's blade properties: two modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-25, on the 0.28.0 block D tree
(`fsi/materials.py`, the material database, and `fsi/sections.py`, the
solid-section calculator, of G41): 863 errors in 18 of 104 modules, against the
block C tree's 863 in 18 of 102. Both new modules arrive clean and the error
count does not move. The dirty count still reads 18 and the shipped
configuration is green over all 104 modules. The quoted mypy lines above are
this run's. The sentence at the top of this report is this measurement; the
earlier ones stay above as the history of the figure.

## Re-measured 2026-09-25, the v0.28.0 release tree: unchanged

`python scripts/mypy_recount.py` on 2026-09-25, on the release tree of v0.28.0
(the block D tree with the fixes of the independent reading C32 and of the
closing review round): 863 errors in 18 of 104 modules, the block D tree's
figure exactly, against the v0.27.0 release tree's 812 in 18 of 100. The
shipped configuration is green over all 104 modules. The quoted mypy lines
above are this run's as well, and the sentence at the top of this report is
this measurement.

## Re-measured 2026-09-28, the 0.29.0 quality-gate candidate: twenty-four modules arrived

`python scripts/mypy_recount.py` on 2026-09-28, on the 0.29.0 candidate under
the GOAL-034 quality gate (`fix/q1b` on the header-free tree `b2f270c1`): 923
errors in 18 of 128 modules, against the v0.28.0 release tree's 863 in 18 of
104. The module guard in `tests/tier1_offline/test_traceability.py` had gone
red at 128 against the recorded 104, which is what asked for this run. The
dirty count still reads 18, every dirty module is exempted by name, and the
shipped configuration is green over all 128 modules. The sixty errors more sit
inside the exempted set, whose largest holder is `pyflightstream.run` at 734
errors on 83 lines. The
script reported three uncommitted paths, none of which carries typed code (a
documentation page, one string built through an existing helper in
`post/guides.py`, and a test import); its full output is the GOAL-034 receipt
`q1-evidence/b-mypy-recount.txt`. The quoted mypy lines above were this run's
until the release tree was measured, next.

## Re-measured 2026-09-28, the v0.29.0 release tree: one error fewer

`python scripts/mypy_recount.py` on 2026-09-28, on the v0.29.0 release tree
(the source the tag is cut from, after the quality gate's last repairs, which
the script reported clean; re-run after those repairs, GOAL-034 Q8 VV-3, it
read the same figure): 922 errors in 18 of 128 modules, one fewer than the
candidate's 923, against the v0.28.0 release tree's 863 in 18 of 104. The
dirty count still reads 18, `pyflightstream.run` still holds 734 errors on 83
lines, and the shipped configuration is green over all 128 modules; the run
measured the tree as it is and assigns the one error to no change. The quoted
mypy lines above were this run's until the 0.30.0 storage-and-sync tree was
measured, next.

**Erratum 2026-09-28** (GOAL-034 Q8 VV2-2/VV6-2): the section above names no
commit for the v0.29.0 release tree it measured. That tree is HEAD
`2626467cf979ee261f5e1f27baaa4507adfd4900`; the receipt is
`GOAL-034-receipts/q8-evidence/vv3-mypy-recount-2626467c.txt` (922 errors in
18 of 128 modules, mypy 1.20.2, 0 changed paths). This line is added after the
fact and the measurement above is unedited.

## Re-measured 2026-09-28, the 0.30.0 storage-and-sync gate-fixing tree: one module arrived

`python scripts/mypy_recount.py` on 2026-09-28, on `feat/0-30-storage-sync`
fixing the nine tier-1 house-style/registry guards this branch's own tests
named: 921 errors in 18 of 130 modules, against the v0.29.0 release tag's 922
in 18 of 128 (the two trees differ by the whole 0.30.0 storage-and-sync
branch, not by one file, so the one-error difference is not attributed to a
single change). The module guard in `tests/tier1_offline/test_traceability.py`
had gone red at 129 against the recorded 128, which is what asked for this
run. The one module the tracked-module count gained since the release tag is
`workspace/storage.py`, the home of the five `pyfs-matrix` storage commands;
it is not itself exempted and the tool reports it CLEAN, so the dirty count
still reads 18. The shipped configuration is green over all 130 modules. The
quoted mypy lines above were this run's until the next run, below.

## Re-measured 2026-09-29, the 0.30.0 tree with the quasi-steady rotor: three modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-29, on `feat/0-30-storage-sync`
once its quasi-steady rotor work had merged (1f6999aa): 998 errors in 18 of
134 modules. The three modules that brought the tracked package from 131
to 134, `cases/qsteady.py`, `fsi/wing.py` and `post/qsteady.py`, are clean,
and the shipped configuration is green over all 134. This section is
written after the fact from that commit's own record, and its figure is
unedited; the quoted mypy lines above were this run's until the release
tree was measured, next.

## Re-measured 2026-09-29, the v0.30.0 release tree

`python scripts/mypy_recount.py` on 2026-09-29, on the release tree of
v0.30.0 (the source of `4f12aede`, on which the release commit is made and
which the script reported clean), with python 3.12.0, mypy 2.3.1, numpy
2.5.3, xarray 2026.7.0, pandas 3.0.6 and pydantic 2.13.5: 1065 errors in 18
of 134 modules, against the 998 of the same date before the last four fixes
of the quasi-steady rotor merged and the v0.29.0 release tree's 922 in 18
of 128 (read with mypy 1.20.2). The dirty count still reads 18,
`pyflightstream.run` holds 870 errors on 97 lines, and the shipped
configuration is green over all 134 modules. The trees differ by source
and the environments by the type checker's own version, so the run
measured the tree as it is and assigns the difference to no single change.
The quoted mypy lines above were this run's until the 0.31.0 release
candidate was measured, next.

Re-run the same day on `97279f15`, after the review fixes changed `src/`
(one module-level import in `cases/fsi_workspace.py` and docstrings only):
1065 errors in 18 of 134 modules, 198 distinct source lines, unchanged.

## Re-measured 2026-09-29, the 0.31.0 release candidate: four modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-29, on the 0.31.0 release
candidate (`feat/0-31` at `33c1d7ef`, every 0.31 item merged, which the
script reported clean), with python 3.12.0, mypy 2.3.1, numpy 2.5.3,
xarray 2026.7.0, pandas 3.0.6 and pydantic 2.13.5: 1084 errors in 18 of
138 modules on 198 distinct source lines, against the v0.30.0 release
tree's 1065 in 18 of 134 in the same environment. The guard in
`tests/tier1_offline/test_traceability.py` had gone red at 138 against the
recorded 134, which is what asked for this run. The four modules the 0.31
work adds, `cases/corrections.py`, `post/corrections.py`,
`post/harmonics.py` and `workspace/fields.py`, are not exempted and the
tool reports each CLEAN, so the dirty count still reads 18.
`pyflightstream.run` holds 889 errors on 97 lines (870 at v0.30.0). The
shipped configuration is green over all 138 modules; the run measured the
tree as it is and assigns the nineteen errors more to no single change.
The quoted mypy lines above are this run's, and the sentence at the top of
this report is this measurement.

Re-run the same day on `97682ca2`, after the reconciliation's last source
change (the harmonic skip scoped to a point that cuts sections, in
`post/products.py`), with only `RELEASE-READY.md` uncommitted: 1084 errors in
18 of 138 modules, 198 distinct source lines, unchanged.

## Re-measured 2026-09-29, the 0.31.0 release candidate with the console change: one module arrived clean

`python scripts/mypy_recount.py` on 2026-09-29, on the 0.31.0 release
candidate at `7d71fdbb` once the console change had merged (the script
reported the tree unsettled only by the uncommitted release edits of
`CHANGELOG.md` and one test, neither of which mypy reads), with python
3.12.0, mypy 2.3.1, numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and
pydantic 2.13.5: 1084 errors in 18 of 139 modules on 198 distinct source
lines, the same errors as the run at 138. The one module the console change
adds, the private floor module `_console.py`, is not exempted and the tool
reports it CLEAN, so the dirty count still reads 18. The shipped
configuration is green over all 139.

## Re-measured 2026-09-29, the 0.32.0 preparation step: ten modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-29, on the 0.32.0 development
branch (`feat/0-32`, from v0.31.0 at `4d1c813f`) with the preparation step's
work uncommitted (the script reported the tree unsettled by exactly those
paths, and counted 149 source files against 139 tracked, the difference being
the ten new modules not yet added), with python 3.12.0, mypy 2.3.1, numpy
2.5.3, xarray 2026.7.0, pandas 3.0.6 and pydantic 2.13.5: 1084 errors in 18
of 149 modules on 198 distinct source lines, the same errors as the run at
139. The ten contract modules, `run/records.py`, `cases/acoustics.py`, `cases/ccs_wing.py`, `cases/ccs_fuselage.py`, `cases/ccs_revolution.py`, `cases/setup_surfaces.py`, `post/acoustics.py`, `post/qsteady_noise.py`, `post/disc_maps.py` and `post/inflow_tools.py`, are not exempted and the tool
reports each CLEAN, so the dirty count still reads 18. The shipped
configuration is green over all 149.

## Re-measured 2026-09-30, the integrated 0.32.0 branch: one module arrived clean

`python scripts/mypy_recount.py` on 2026-09-30, on the integrated 0.32.0
branch (`feat/0-32` at `44635709`, every 0.32 package merged, the source
tree committed; the script reported the tree unsettled only by the
uncommitted fold of the change log and SRS fragments, none of which mypy
reads), with python 3.12.0, numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and
pydantic 2.13.5 (the script printed mypy's version as unknown): 1112
errors in 18 of 150 modules on 199 distinct source lines, against 1084 on
198 at 149. The one module added since the preparation step,
`cases/_ccs.py`, is not exempted and the tool reports it CLEAN, so the
dirty count still reads 18; the 28 further errors sit in modules that
already carried exemptions, and the run measured the tree as it is and
assigns no share of them to a change. The shipped configuration is
green over all 150. The quoted mypy lines and the sentence at the top of
this report are this run's.

## Re-measured 2026-09-30, the 0.33.0 branch of WP1 and WP2: one module arrived clean

`python scripts/mypy_recount.py` on 2026-09-30, on `feat/0-33-wp12` at
`29d5bbf4` (work packages WP1 and WP2 of 0.33.0, the source tree committed and
clean), with python 3.12.0, numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and
pydantic 2.13.5 (the script printed mypy's version as unknown): 1137 errors in
18 of 151 modules on 199 distinct source lines. The one module the two
packages added, `results/sectional_loads.py`, is not exempted and the tool
reports it CLEAN, so the dirty count still reads 18, and the shipped
configuration is green over all 151. The same invocation over the base of
the branch, `rel/0-33` at `5df3d692`, read 1137 errors in 18 of 150 on the
same environment, so the two packages moved the error total by none; the 25
over the 1112 of the integrated 0.32.0 branch were already on that base, and
this run assigns no share of them to a change. The quoted mypy lines and the
sentence at the top of this report are this run's.

## Re-measured 2026-09-30, the 0.33.0 branch of FR-310 to FR-314: four modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-30, on `feat/0-33-fr` at
`e127c8fc` (the functional requirements FR-310 to FR-314 of 0.33.0, the source
tree committed and clean), with python 3.12.0, numpy 2.5.3, xarray 2026.7.0,
pandas 3.0.6 and pydantic 2.13.5 (the script printed mypy's version as
unknown): 1133 errors in 18 of 154 modules on 199 distinct source lines. The
four modules the branch added, `_fsm_fresh.py`, `cases/_unsteady_actions.py`,
`workspace/_geometry_clean.py` and `workspace/_matrix_homes.py`, are not
exempted and the tool reports each CLEAN, so the dirty count still reads 18,
and the shipped configuration is green over all 154. The base of the branch,
`rel/0-33` at `5df3d692`, read 1137 errors in 18 of 150 on the same
environment (the run recorded by work packages WP1 and WP2), so this branch
reads four errors fewer; this run assigns no share of the difference to one
change. The quoted mypy lines and the sentence at the top of this report are
this run's.

## Re-measured 2026-09-30, the 0.33.0 branch with WP1, WP2 and FR-310 to FR-314 merged: five modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-30, on `rel/0-33` during the
merge of `feat/0-33-fr` at `a438aea1` into `rel/0-33` at `3f42e2ad` (which
carries WP1 and WP2), every file under `src/` resolved and staged, with
python 3.12.0, numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and pydantic
2.13.5 (the script printed mypy's version as unknown): 1133 errors in 18 of
155 modules on 199 distinct source lines. The five modules the two branches
added, `results/sectional_loads.py`, `_fsm_fresh.py`,
`cases/_unsteady_actions.py`, `workspace/_geometry_clean.py` and
`workspace/_matrix_homes.py`, are not exempted and the tool reports each
CLEAN, so the dirty count still reads 18, and the shipped configuration is
green over all 155. The script read 151 tracked modules because it lists
the tree of HEAD, and the four modules the merge stages are the four of
FR-310 to FR-314; the merge commit brings the tracked total to the 155 mypy
checked. WP1 and WP2 alone read 1137 in 18 of 151 and FR-310 to FR-314
alone read 1133 in 18 of 154, each against the base `rel/0-33` at
`5df3d692` at 1137 in 18 of 150, and the merged tree reads 1133; this run
assigns no share of the difference to one change. The quoted mypy lines and
the sentence at the top of this report are this run's.

## Re-measured 2026-09-30, the 0.33.0 branch of FR-316 to FR-319: three modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-30, on the 0.33.0 branch of the
setup requirements FR-316 to FR-319 (`feat/0-33-setup` at `ef831369`, the
tree committed and clean, as the script reported), with python 3.12.0, numpy
2.5.3, xarray 2026.7.0, pandas 3.0.6 and pydantic 2.13.5 (the script printed
mypy's version as unknown): 1137 errors in 18 of 153 modules on 199 distinct
source lines. The three modules the branch adds, `cases/_setup_keys.py`, `cases/_setup_link.py` and `workspace/_row_setup.py`,
are not exempted and the tool reports each CLEAN, so the dirty count still
reads 18. The base of the branch, `rel/0-33` at `8bf21f3b`, was not
re-measured; `rel/0-33` at `5df3d692`, four source files earlier, read 1137 in
18 of 150 on the same environment. The run assigns no share of any difference
to a change. The shipped configuration is green over all 153. The quoted mypy
lines and the sentence at the top of this report are this run's.

## Re-measured 2026-09-30, the 0.33.0 branch with WP1, WP2, FR-310 to FR-314 and FR-316 to FR-319 merged: eight modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-30, on `rel/0-33` during the
merge of `feat/0-33-setup` at `a031f5ac` into `rel/0-33` at `7d1f50ac`
(which carries WP1, WP2 and FR-310 to FR-314), every file under `src/`
resolved and staged, with python 3.12.0, numpy 2.5.3, xarray 2026.7.0,
pandas 3.0.6 and pydantic 2.13.5 (the script printed mypy's version as
unknown): 1133 errors in 18 of 158 modules on 199 distinct source lines.
The eight modules the three branches added are not exempted and the tool
reports each CLEAN, so the dirty count still reads 18, and the shipped
configuration is green over all 158. The script read 155 tracked modules
because it lists the tree of HEAD, and the three modules the merge stages
are the three of FR-316 to FR-319; the merge commit brings the tracked
total to the 158 mypy checked. `rel/0-33` before this merge read 1133 in 18
of 155 and FR-316 to FR-319 alone read 1137 in 18 of 153, and the merged
tree reads 1133; this run assigns no share of any difference to one
change. The quoted mypy lines and the sentence at the top of this report
are this run's.

## Re-measured 2026-09-30, the 0.33.0 branch of WP3: fourteen modules arrived clean

`python scripts/mypy_recount.py` on 2026-09-30, on the 0.33.0 branch of work
package WP3 (`feat/0-33-wp3` at `a17a0a3f`, the tree committed and clean, as
the script reported), with python 3.12.0, numpy 2.5.3, xarray 2026.7.0,
pandas 3.0.6 and pydantic 2.13.5 (the script printed mypy's version as
unknown): 1130 errors in 18 of 172 modules. The fourteen modules the branch
cut out of `post.guides`, the `results` root, `run.records` and
`workspace.inputs` (AD-11) are not exempted and the tool reports each CLEAN,
so the dirty count still reads 18. Three errors of the code that left the
exempted `workspace.inputs` for `workspace/sidecars.py` were fixed in the
move (two casts and one renamed local), which is the difference from the
1133 in 18 of 158 of its base, `rel/0-33` at `277b29c3`, measured on the
same environment by the run above this one. The shipped configuration is
green over all 172. The quoted mypy lines and the sentence at the top of
this report are this run's.

## Re-measured 2026-09-30, the branch of FR-320: its one module arrived clean

`python scripts/mypy_recount.py` on 2026-09-30, on `feat/0-33-famwarn` (the
plan's warning for a family a row's geometry does not carry) over `rel/0-33`
at `277b29c3`, with the work of the branch not yet committed and the new
module untracked, as the script reported, with python 3.12.0, numpy 2.5.3,
xarray 2026.7.0, pandas 3.0.6 and pydantic 2.13.5 (the script printed
mypy's version as unknown): 1133 errors in 18 of 159 modules on 199
distinct source lines. The script read 158 tracked modules and mypy checked
159; the one between them is the untracked `cases/_skipped_families.py`,
which the commit of the branch tracks. It is not exempted and the tool
reports it CLEAN, so the dirty count still reads 18, the error count is the
1133 of `rel/0-33` with all three branches merged, and the shipped
configuration is green over all 159. The quoted mypy lines and the sentence
at the top of this report are this run's.

## Re-measured 2026-09-30, `rel/0-33` with WP3 and FR-320 merged: fifteen modules clean

`python scripts/mypy_recount.py` on 2026-09-30, on `rel/0-33` with the merge
of `feat/0-33-wp3` committed and the merge of `feat/0-33-famwarn` resolved in
the working tree and not yet committed, as the script reported, with python
3.12.0, numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and pydantic 2.13.5 (the
script printed mypy's version as unknown): 1130 errors in 18 of 173 modules
on 196 distinct source lines. The script read 172 tracked modules and mypy
checked 173; the one between them is `cases/_skipped_families.py`, which the
merge adds and its commit tracks. The 173 are the 172 of `rel/0-33` with WP3
merged and that module from FR-320; neither branch's new
modules are exempted and the tool reports each CLEAN, so the dirty count
still reads 18. The error count is WP3's 1130: the branch of FR-320 alone
read 1133 in 18 of 159 over the 1133 of its base, so it adds none, and the
three WP3 fixed in the move from `workspace.inputs` stay fixed. The shipped
configuration is green over all 173. The quoted mypy lines and the sentence
at the top of this report were this run's until the run below.

## Re-measured 2026-10-01, `rel/0-33` with FR-96 also merged: no module added, eight errors fewer

`python scripts/mypy_recount.py` on 2026-10-01, on `rel/0-33` with the merges
of WP3, FR-320, FR-153 and the setup-link fix committed (`a5e66d9a`) and the
merge of `feat/0-33-contrevs` (the continuation of a CONVERGED unsteady run,
FR-96) resolved in the working tree and not yet committed, as the script
reported, with python 3.12.0, numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and
pydantic 2.13.5 (the script printed mypy's version as unknown): 1122 errors
in 18 of 173 modules on 189 distinct source lines. The same script read 1130
in 18 of 173 on 196 lines at `a5e66d9a`, and 1125 in 18 of 158 on 192 lines
on the branch of FR-96 alone (`feat/0-33-contrevs` at `3f370448`, the tree
committed and clean). FR-96 adds no module; the eight errors fewer are all in
the exempted `pyflightstream.run` root, 938 before and 930 after, whose code
the branch reworked, and `run/_continuation_frame.py`, which it extends,
stays clean. The dirty count still reads 18 and the shipped configuration is
green over all 173. The quoted mypy lines and the sentence at the top of
this report were this run's until the run below.

## Re-measured 2026-10-01, `rel/0-33` with WP4 merged: the workflows package, 24 modules clean

`python scripts/mypy_recount.py` on 2026-10-01, on the branch of work package
WP4 (`feat/0-33-wp4`) rebased onto `rel/0-33` at `99cf19d6`, the tree
committed and clean, as the script reported, with python 3.12.0, numpy 2.5.3,
xarray 2026.7.0, pandas 3.0.6 and pydantic 2.13.5 (the script printed mypy's
version as unknown): 1122 errors in 18 of 196 modules on 189 distinct source
lines. The cut of `cases/workflows.py` into the package `cases/workflows/` of
24 modules (AD-12) adds twenty-three modules, each reported CLEAN, so the
error count and the dirty count are those of the base: 1122 in 18. The
shipped configuration is green over all 196. The quoted mypy lines and the
sentence at the top of this report are this run's.

## Re-measured 2026-10-01, `rel/0-33` with WP4, WP5 and WP6 merged: `pyflightstream.run` leaves the exemptions

`python scripts/mypy_recount.py` on 2026-10-01, on `rel/0-33` at `f888d704`
(the merges of WP4, WP5, WP6 and D1 committed, the tree clean, as the script
reported), with python 3.12.0, numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and
pydantic 2.13.5 (the script printed mypy's version as unknown): 192 errors
in 17 of 219 modules on 98 distinct source lines. The tracked package holds
219 modules, twenty-three more than the 196 of the WP4 run, each reported
clean. WP6 made `pyflightstream.run` a facade over typed modules and
deleted its `[[tool.mypy.overrides]]` entry (decision 7), so the exempted set
shrank from eighteen to seventeen modules and the 930 errors the run root
carried left the debt: 1122 less 930 is 192. The 192 are in
`qa.probes` (79), `script.solver_setup` (22), `script` and `script.helpers`
(17 each), `fsi.nodes` (10), `cases` and `qa.specs` (9 each), `cases.matrix`
(7), `probes.planar` (6), `workspace.inputs` (4), five modules with two
(`commands`, `farfield`, `post.writers`, `probes.geometry`,
`workspace.naming`) and two with one (`fsi.driver`, `script.entities`).
`module = "pyflightstream.run"` is absent from the override list of
`pyproject.toml`, and the shipped configuration is green over all 219.

## Re-measured 2026-10-01, the 0.34.0 branch of WP8: the models of the `cases` root leave, six modules clean

`python scripts/mypy_recount.py` on 2026-10-01, on the branch of work package
WP8 of 0.34.0 (`feat/0-34-wp8`) at `13abc1a0`, the tree committed and clean,
as the script reported, with python 3.12.0, numpy 2.5.3, xarray 2026.7.0,
pandas 3.0.6 and pydantic 2.13.5 (the script printed mypy's version as
unknown): 184 errors in 17 of 225 modules on 91 distinct source lines. The
cut of AD-16 moves the models of the `cases` root into six modules,
`cases/pproc.py`, `cases/reference_blocks.py`, `cases/settings.py`,
`cases/mesh.py`, `cases/naming.py` and `cases/selection.py`, each reported
CLEAN and none of them exempted, so the tracked package grows from 219 to
225. Every moved line was typed rather than exempted, so `pyflightstream.cases`,
which keeps its override, reports 1 error where it reported 9, and the total
falls from 192 to 184 with the dirty count unchanged at 17; every other
module reports what it reported at 219. The override list of
`pyproject.toml` is unchanged, and the shipped configuration is green over
all 225.

## Re-measured 2026-10-01, `rel/0-34` with the wave-1 work packages merged: fifteen modules clean, `qa.specs` clean

`python scripts/mypy_recount.py` on 2026-10-01, on `rel/0-34` at `4b90bf5d`
(the merges of W0-CI, QA-SPECS, WP8, WP9a, WP9b, GUIDE, FSI-OFF, THIN-CORE,
ACT, RPTS and QSN committed, the tree clean, as the script reported), with
python 3.12.0, numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and pydantic
2.13.5 (the script printed mypy's version as unknown): 160 errors in 16 of
234 modules on 75 distinct source lines. The tracked package holds fifteen
modules more than the 219 of `rel/0-33`, each reported CLEAN and none of
them exempted: the six model modules of the `cases` cut (WP8, AD-16), the
two of the `script.helpers` cut (`script/_settings.py` and
`script/_relaxed_te.py`, WP9a, AD-17), `run/_cli_print.py` (WP9b, AD-18),
the five of the probe-catalog cut (`qa/_spec_catalog_b.py`,
`qa/_spec_ccs_mesh.py`, `qa/_spec_ccs_noise.py`, `qa/_spec_kit.py` and
`qa/_spec_t1.py`) and `workspace/_degenerate.py` (FR-330). Every moved line
was typed rather than exempted: `pyflightstream.cases` reports 1 error where
it reported 9, `pyflightstream.script.helpers` 2 where it reported 17, and
`pyflightstream.qa.specs` none where it reported 9, so the total falls from
192 to 160 and the dirty count from 17 to 16. The 160 are in `qa.probes`
(79), `script.solver_setup` (22), `script` (17), `fsi.nodes` (10),
`cases.matrix` (7), `probes.planar` (6), `workspace.inputs` (4), six modules
with two (`commands`, `farfield`, `post.writers`, `probes.geometry`,
`script.helpers`, `workspace.naming`) and three with one (`cases`,
`fsi.driver`, `script.entities`). `module = "pyflightstream.qa.specs"` is
deleted from the override list of `pyproject.toml` (and from
`MYPY_EXEMPTIONS`) in the commit that records this run, because the module
reports no error, and the shipped configuration is green over all 234. The quoted mypy lines and the sentence at the top of
this report are this run's.

## Re-measured 2026-10-02, `rel/0-34` with the wave-2 packages merged: two modules more, both clean

`python scripts/mypy_recount.py` on 2026-10-02, on `rel/0-34` at `6988eeef`
(the wave-2 merges of LF, RUN, THIN-CLI, WAKE, TOGGLE, FR153REG, ADPROF,
MESHFACES, the public architecture section, the migration page and the kill
tests committed, the tree clean, as the script reported), with python 3.12.0,
numpy 2.5.3, xarray 2026.7.0, pandas 3.0.6 and pydantic 2.13.5 (the script
printed mypy's version as unknown): 160 errors in 16 of 236 modules on 75
distinct source lines. The tracked package holds two modules more than the
234 of the wave-1 tip, each reported CLEAN and neither exempted:
`pyflightstream._textio`, the LF write route of NFR-32, and
`pyflightstream.workspace.actuator_profiles`, the profile generator of
FR-347. The per-module table is the wave-1 tip's, module by module: the 160
are in `qa.probes` (79), `script.solver_setup` (22), `script` (17),
`fsi.nodes` (10), `cases.matrix` (7), `probes.planar` (6),
`workspace.inputs` (4), six modules with two and three with one. The
override list of `pyproject.toml` is unchanged, and the shipped
configuration is green over all 236. The quoted mypy lines and the sentence
at the top of this report are this run's.

## Re-measured 2026-10-03, `rel/0-36` with the wave-1 cuts and MM merged: one error fewer, the count of dirty modules unchanged

`python scripts/mypy_recount.py` on 2026-10-03, on `rel/0-36` after the merges of
WP7, WP9c, WP9d, WP10a, WP10b, GF and MM, the tree clean as the script reported,
with python 3.12.0, numpy 2.5.2, xarray 2026.7.0, pandas 3.0.5 and pydantic
2.13.4: 159 errors in 16 of 269 modules on 74 distinct source lines; the shipped
configuration is green over all 269. The package grew by eight modules since the
0.35.1 recount (the WP7, WP9c, WP9d and WP10b homes and `pyflightstream._maturity`),
each reported clean and none exempted. The override list of `pyproject.toml` is
unchanged. The sentence at the top of this report is this run's. (The 0.35.1.dev1
and the first 0.36.0 module recounts changed only the module figure of the
2026-10-02 sentence; this run re-measures the errors as well, and the dated
section above is restored to the 236 modules it measured.)

## Re-measured 2026-10-05, `rel/0-37` with the 0.37.0 work packages merged: the same 159 errors in the same 16 modules, thirteen modules more, all clean

`python scripts/mypy_recount.py` on 2026-10-05, on `rel/0-37` at the merge of the
0.37.0 documentation (HEAD 6daf49ea), the tree clean as the script reported, with
python 3.12.0, numpy 2.5.3, xarray 2026.9.0, pandas 3.0.6 and pydantic 2.13.5 (the
script printed mypy's version as unknown), then 159 errors in 16 of the 282 modules on 74
distinct source lines; the shipped configuration is green over all 282. The package
grew by thirteen modules since the 0.36.0 recount of 2026-10-03, each reported clean
and none exempted: `cases/workflows/_export_first_step.py`,
`cases/workflows/_wake_length.py`, `fsi/_direct_morphing.py`,
`post/_installed_copies.py`, `post/_settings_product.py`, `qa/_spec_26125.py`,
`run/_collect_logs.py`, `run/_mark_converged.py`, `run/_rebuild_grouped.py`,
`script/_build_forms.py`, `workspace/_missing_log.py`, `workspace/_step_prune.py`
and `workspace/_verdicts.py`. The errors by module are in `qa.probes` (79),
`script.solver_setup` (22), `script` (17), `fsi.nodes` (10), `cases.matrix` (6),
`probes.planar` (6), `workspace.inputs` (4), six modules with two and three with
one; by code, 121 `arg-type`, 12 `return-value`, 7 `union-attr`, 5 `operator`,
5 `assignment`, 4 `call-overload`, 4 `misc` and 1 `attr-defined`. The override list
of `pyproject.toml` is unchanged. The sentence at the top of this report is this
run's.

## Re-count of 2026-10-06 (0.38.0)

`python scripts/mypy_recount.py` on 2026-10-06, on `rel/0-38` with every 0.38.0 package merged (the refinement, the audit, the periodic sector and the body factors), python 3.12.0: 159 errors in 16 of 292 modules on 74 distinct source lines; the shipped configuration is green over all 292 (`Success: no issues found in 292 source files`). The package grew by ten modules, each clean and none exempted: `run/_cli_mesh.py`, `workspace/_refine/__init__.py`, `_audit.py`, `_config.py`, `_geometry.py`, `_grid.py`, `_level.py`, `_obj.py`, `_periodic.py` and `_remesh.py`. The dirty set and its 159 errors are unchanged.
