# RPT-133 - The vorticity drag list and the step exports of a rotor march on FlightStream 26.124 (2026-10-02)

The licensed confirmation of **FR-318** R5 that pyflightstream 0.33.0 left owed
(registered in RPT-106, "Licensed confirmation registered (FR-318)"), run after the
0.34.0 release. Three arms ran on **FlightStream 26.124, build 8172026**, executable
SHA-256 withheld from the public tree per NFR-31, one solver instance at a time, hidden,
far field 5 layers stated in every setup. The scripts are the ones pyflightstream 0.34.0
emits (package tree at `ed06e86d`, no file changed), one arm with one block of three lines
moved by hand. The run window: 2026-10-02T14:30:20-03:00 to 2026-10-02T14:30:59-03:00.

Only nondimensional values are stated: force and moment coefficients of the loads
spreadsheet's Total row, and relative differences. The geometry is the synthetic blade of
the tier-3 library (`30_BLADE.fsm`, generated from public shape laws).

## 1. The question

FR-318 R5, as the requirement states it: "The two settings do not yet reach the same
exports of an unsteady row. The moments model precedes `START_SOLVER`, so every step export
carries it. The vorticity drag list is an analysis-phase command in every edition of the
command database and follows `START_SOLVER`, so it reaches the final loads export and not
the step exports. The order is kept as documented; whether the solver takes the list before
the solve and the step exports then carry it is owed to a licensed round, registered in
RPT-106."

RPT-106 names the run: "on 26.124, an `unsteady_rotor` row with `vorticity_drag_families`
emitting `SET_VORTICITY_DRAG_BOUNDARIES` before `START_SOLVER`, to measure whether the
solver accepts it there and whether the step exports then report the induced drag by
vorticity integration."

Two answers are asked: Q1, does the solver accept the list before `START_SOLVER`; Q2, do
the step exports then carry it.

## 2. The case and the arms

One synthetic blade, periodic with six copies, `unsteady_rotor`, advance ratio 1.7, alpha 0,
30 degrees a step, one revolution (12 steps), every step exported from step 1
(`EXPORT_UNSTEADY_AFTER_ITER: 1`, the per-step loads spreadsheet among the exports), far
field 5 layers, the moments model `VORTICITY` stated in every arm, so that the only
setting that differs between arms is the drag list and its place.

| arm | the drag list (`SET_VORTICITY_DRAG_BOUNDARIES` on the blade) | what it is |
|---|---|---|
| A | after `START_SOLVER`, as 0.34.0 emits it | the released order |
| B | immediately before `START_SOLVER`, the three lines moved and nothing else | the probe |
| C | absent | the control: a step export that does not carry the list |

A and C differ by the three lines of the list; A and B by their place. The control's power
is the final export: if the list did not move A's final loads away from C's, no step export
could show it, and the verdict would be inconclusive. The comparator is also scored on a
derangement (the control's step k against its step k + 1).

## 3. Measurements

Each of the three arms exited with status 0, solved 12 of 12 steps, executed 24 runtime
commands, named build #8172026 in its log, printed no error-like line and wrote 12 per-step
loads spreadsheets (steps 1 to 12). No line of any log names the drag list: arm B's log
says nothing about the list that arm A's does not.

| comparison | steps that differ | worst relative difference | coefficient |
|---|---|---|---|
| derangement, C step k vs C step k + 1 | 11 of 11 | 1.017e+00 | |
| final A vs final C (the control) | | 1.623e-01 | Cx |
| steps A vs C (the released order) | 0 of 12 | 0 | |
| steps B vs C (the probe) | 12 of 12 | 2.238e-01 | |
| steps B vs A | 12 of 12 | 2.238e-01 | |
| last step B vs final A | | 0 | Cx |
| final B vs final A | | 0 | Cx |

| arm | final Cx | final CDi | last-step Cx | last-step CDi |
|---|---|---|---|---|
| A | -0.0500793 | -0.0505247 | -0.0419517 | -0.0423971 |
| B | -0.0500793 | -0.0505247 | -0.0500793 | -0.0505247 |
| C | -0.0419517 | -0.0423971 | -0.0419517 | -0.0423971 |

The list moves the drag only: CL (-0.0003636) and CMx (-0.027837) of the final and the
last-step exports are the same in the three arms. Arm A's last step differs from its own
final export by 1.623e-01 in Cx; arm B's and arm C's last steps equal their final exports.

The plots export (the solver's force plots, one row per step) compared the same way: A vs C,
0 of 12 rows differ; B vs C, 12 of 12 rows differ, worst 2.238e-01; B vs A, 12 of 12 rows
differ, worst 2.238e-01.

## 4. Verdict

- Q1: YES, the solver accepts `SET_VORTICITY_DRAG_BOUNDARIES` before `START_SOLVER` on
  26.124 (build 8172026): exit 0, 12 of 12 steps, no error-like line.
- Q2: YES, with the list before the solve every step export carries the vorticity
  integration (12 of 12 step exports differ from the control's), and the last step equals
  the released final export (worst relative difference 0).
- The released order: the step exports do not carry the list (0 of 12 differ from the
  control's); the final export carries it, and differs from the last step export of the
  same run by 1.623e-01 in Cx.

What follows for FR-318 R5: the statement it makes about the released order is confirmed,
and its open question is answered. Moving the list before `START_SOLVER` is a change of
emitted bytes in `src/`; a post-release commit does not change the package source, so the
fix is 0.35.0 scope, and FR-318 R5 now cites this measurement.
The tier-1 test `tests/tier1_offline/test_rpt133_fr318_vorticity_order.py` reads the
recorded exports of the three arms, with the control, and pins the order the package emits
today.

## 5. What this does not show

- One geometry (a synthetic blade with its trailing edge detected), one build, one
  condition, one revolution. A body on the list, a list without a trailing edge (whose
  induced drag the solver prints as zero), and other builds are not measured.
- The list was moved before `START_SOLVER` only, not before `INITIALIZE_SOLVER`.
- The quasi-steady rotor and the steady rows, where every export follows the solve, are
  not concerned.
