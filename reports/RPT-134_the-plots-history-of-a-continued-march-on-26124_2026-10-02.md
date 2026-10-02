# RPT-134 - The plots history of a continued march on FlightStream 26.124 (2026-10-02)

The licensed confirmation of **FR-96** that pyflightstream 0.33.0 left owed (FR-96,
"Owed"), run after the 0.34.0 release. Two package runs
(`pyfs-matrix plan`, then `pyfs-matrix run --local`) of pyflightstream 0.34.0 (package tree
at `ed06e86d`, `package_dirty: false` in every record) and one script launched by hand
ran on **FlightStream 26.124, build 8172026**, executable SHA-256 withheld from the public
tree per NFR-31, one solver instance at a time, hidden. Far field 5 layers is stated in the
setup of the point and of the control: the control's script carries
`SOLVER_SET_FARFIELD_LAYERS 5`, and the point's run record states that command with the
value 5, stated and emitted. The continuation's script and the resume arm's state no far
field: they inherit it from the saved simulation they reopen, the point's. The run window:
2026-10-02T14:32:21-03:00 to 2026-10-02T14:39:55-03:00; the three launches ran from
14:32:21 to 14:32:40, from 14:33:40 to 14:33:55 and from 14:39:47 to 14:39:55, and the
launches of RPT-135 ran between the second and the third, never at the same time.

Only nondimensional values are stated: step numbers, row counts, iteration counts,
coefficients and relative differences. The geometry is the synthetic blade of the tier-3
library (`30_BLADE.fsm`).

## 1. The question

FR-96, as the requirement states what is owed: "which history the solver's plots export of
a continuation holds, the whole march or the continuation's steps only, and how it numbers
them, is not on record; R6 reads each shape and is correct in each. The licensed
confirmation, a CONVERGED `unsteady_rotor` point continued by `{ADDITIONAL_REVS=1}` on
26.124 with its plots export read, is owed to the licensed round of 0.33.0."

## 2. The case

One synthetic blade, periodic with six copies, `unsteady_rotor`, advance ratio 1.7, alpha 0,
30 degrees a step (12 steps a revolution), `LAST_REVS_AVG: 1`, far field 5 layers.

| launch | row | what it is |
|---|---|---|
| package run 1 | 9341, 1 revolution (12 steps) | the point, recorded `CONVERGED` |
| package run 1 | 9342, 2 revolutions (24 steps) straight, the same settings | the control: an unbroken march of the same length |
| package run 2 | 9341 with `RESTART: {ADDITIONAL_REVS=1}` | the continuation as 0.34.0 emits it: 12 more steps, opening the point's archived saved simulation |
| by hand | the continuation's script without its `INITIALIZE_SOLVER` block, nothing else changed | the resume arm: the reopened state kept |

The shape of a continuation's plots export is read from its own rows, against the point's
archived export: the whole march (24 rows numbered 1 to 24, the first 12 restating the
point's), numbered on (12 rows numbered 13 to 24), or the count restarted (12 rows numbered
1 to 12 holding new values). The control's steps 1 to 12 against the point's are the
comparator's "identical", its steps 13 to 24 against its own 1 to 12 the comparator's
"different".

## 3. Measurements

The three package records name build 8172026 and package `ed06e86d`, not dirty: the point,
`CONVERGED`, 12 steps, continuing nothing; the continuation, `CONVERGED`, 12 steps,
`continues` the point, `restart` `{form: ADDITIONAL_REVS, value: 1.0}`; the control,
`CONVERGED`, 24 steps. The continuation's script opens the archived saved simulation
(`OPEN`, then `LOAD_SOLVER_INITIALIZATION ENABLE`), states `TIME_ITERATIONS 12`, registers
the step actions, and then emits an `INITIALIZE_SOLVER` block before `START_SOLVER`. The
resume arm's script is that script without the six lines of the `INITIALIZE_SOLVER` block.
Every launch exited with status 0.

| export | rows | numbered | solver iteration counter |
|---|---|---|---|
| the point's, archived by the continuation | 12 | 1 to 12 | 462 |
| the continuation's, as 0.34.0 emits it | 12 | 1 to 12 | 462 |
| the resume arm's | 24 | 1 to 24 | 635 |
| the control's | 24 | 1 to 24 | 635 |

| comparison | rows that differ | worst relative difference |
|---|---|---|
| control 1-12 vs the point 1-12 (comparator: identical) | 0 of 12 | 0 |
| control 13-24 vs control 1-12 (comparator: different) | 12 of 12 | 1.863e-01 |
| the 0.34.0 continuation 1-12 vs the point 1-12 | 0 of 12 | 0 |
| the 0.34.0 continuation vs the control's 13-24 | 12 of 12 | 1.863e-01 |
| the resume arm 1-12 vs the point 1-12 | 0 of 12 | 0 |
| the resume arm 13-24 vs its own 1-12 | 12 of 12 | 1.863e-01 |
| the resume arm 1-24 vs the control 1-24 | 4 of 24 | 4.4e-05 |

The four rows of the resume arm that differ from the control (steps 14, 15, 18 and 21)
differ in one force or moment column each, by one unit of the last printed digit.

The solver's own numbering in the logs (`Solving unsteady time-step iteration (k/N)`): the
0.34.0 continuation opens the archived file, then prints "Solution cleared. Initialization
removed." and marches from (1/12) to (12/12). The resume arm prints no such line and marches
from (13/24) to (24/24), 12 step lines. In both, the step-counter action ran 24 times for 12
steps (48 runtime commands), twice a step, the doubling RPT-135 measured on a reopened file
that keeps the actions its run saved (FR-308).

FR-96 R6 through the package: `pyfs-matrix post` (no executable) on the package workspace
posted the continued point's plots table with steps 1 to 12, each once, and the averaging
window `[[1, 12]]`; the post log says: "this run continues 'ws/sim_9341/M144RE438AL+000BE+000',
and its plots table is the march as joined here: 'ws/sim_9341/M144RE438AL+000BE+000' steps 1
to 12; 'ws/sim_9341/r20261002-143343/M144RE438AL+000BE+000' restating the march from step 1
to step 12. The averaging window ends at step 12, the last step the table holds." The resume
arm ran outside the workspace; its recorded export, posted by the tier-1 test as the
continuation's, gives steps 1 to 24, each once, the window `[[13, 24]]`, and the post log
says "restating the march from step 1".

## 4. Verdict

The plots export of a continuation on 26.124 (build 8172026), when the reopened state is
kept, holds the WHOLE march, numbered continuously 1 to 24: its first 12 rows are the
point's rows exactly, its last 12 the continued steps, equal to an unbroken march of 24
steps within the last printed digit (4 of 24 rows, 4.4e-05). FR-96 R6 reads that shape: the
history restates the march, the joined table holds every step once, and the window is the
last revolution of the whole march.

The continuation 0.34.0 emits does not continue. Its `INITIALIZE_SOLVER` block, emitted
after the `OPEN` of the saved simulation, clears the reopened solution on 26.124, and the
march restarts at step 1: its export is the point's 12 rows, its iteration counter the
point's 462, and the post joins what it is given (the march restated, 12 steps, the window
`[[1, 12]]`). The emission is `cases/workflows/_skeleton.py:360`, `_initialize(case, script)`
called without a `reopens_a_saved_state` guard, reached on a continuation from
`cases/workflows/_unsteady.py:146` (`OPEN ... ENABLE`) and `:161` (`_script_tail(...,
reopens_a_saved_state=True)`). Its fix changes emitted bytes in `src/`; a post-release
commit does not change the package source, so the fix is 0.35.0 scope by decision of
2026-10-02.

The FR-96 "Owed" paragraph is replaced by a dated evidence line citing this report and the
tier-1 test `tests/tier1_offline/test_rpt134_fr96_continuation_history.py`, which posts the
four recorded exports through the package, with the point alone as its control, and pins
the `INITIALIZE_SOLVER` block the package emits today on a continuation.

## 5. What this does not show

- One geometry, one build, one condition, one continuation by one revolution of a
  `CONVERGED` point. A continuation of a run the wall clock stopped, a second continuation,
  `{ADDITIONAL_ITERS=n}` and `{FINISH_PENDING}` are not measured here.
- The resume arm is a script edited by hand and launched outside the package's workspace;
  no package release emits it yet.
- Whether the continued steps reproduce an unbroken march is stated above for context; it is
  not what FR-96 asks.
