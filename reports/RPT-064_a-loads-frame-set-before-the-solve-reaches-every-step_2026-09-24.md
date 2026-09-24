# RPT-064: a loads frame set before the solve reaches every step export (2026-09-24)

**Date:** 2026-09-24
**Found by:** the acceptance run of item B05 of the 0.27.0 work, before its code
**Status:** REGISTERED for 0.27.0 (B05 moves the loads frame and the moments model before `START_SOLVER`)
**Affects:** every unsteady row since the per-step exports existed: its step
spreadsheets, and the loads series built from them, state moments about the
reference frame's origin rather than about the row's moment point

## What this settles

RPT-062 saw the unsteady step exports print `Coordinate frame for analysis:
Reference` while the final export printed the row's frame. The cause is the
order the package emits: `SET_SOLVER_ANALYSIS_LOADS_FRAME` and
`SET_ANALYSIS_MOMENTS_MODEL` come after `START_SOLVER`, and the step exports
are written during the march. This run moves ONLY those two lines, and asks
whether the solver honours them there. **It does. Set before `START_SOLVER`,
or before `INITIALIZE_SOLVER`, every step export states the row's frame, and
the last step's moments equal the final export's.**

## What was run

The unsteady point of RPT-062 (40_PUSHER, one revolution at 30 degrees per step,
step exports from half a revolution, farfield layers 5), solved again on
FlightStream 26.124 twice, detached, with no solver alive before each. Every
line of the script is the original's except where the two analysis lines sit:

| run | the two lines |
|---|---|
| control (RPT-062's run) | after `START_SOLVER`, as the package emits them |
| A | just before `START_SOLVER`, after `INITIALIZE_SOLVER` and the sections |
| B | before `INITIALIZE_SOLVER`, after the action registrations |

## What came back

| run | frame printed by steps 6 to 12 | step 12 CMy, CMz | final CMy, CMz |
|---|---|---|---|
| control | Reference, all seven | -0.0000602, +0.0013362 | +0.0002003, -0.0006288 |
| A | MRP, all seven | +0.0002003, -0.0006288 | +0.0002003, -0.0006288 |
| B | MRP, all seven | +0.0002003, -0.0006288 | +0.0002003, -0.0006288 |

The forces agree in every run: the step-12 total `Cx` is -0.6573515 in all
three. So the frame is the only thing the order changes, and both earlier
positions fix it.

## What it means for the package

- The two analysis lines move before `START_SOLVER` for every run type. A
  steady row is unaffected in its numbers, since its exports come after the
  solve, but one position for all run types keeps one rule.
- A loads series (`series/<point>_loads_series.csv`) made before this release
  from an unsteady row states its moment columns about the reference frame's
  origin. Its forces are right. The row's final export, and every product built
  from the plots table, were already in the row's frame.

## What this does NOT establish

- **One build and one point.** 26.124, a pusher rotor turning about its hub.
- **The moment model.** `SET_ANALYSIS_MOMENTS_MODEL PRESSURE` moved with the
  frame. Its effect was not separated here, because the package emits the two
  lines together and moves them together.

## Evidence

`reports/probes/RPT-064_2026-09-24_evidence.yaml`: per run, the frame each step
export printed, the last step's and the final export's totals, and each script's
digest. The solver outputs stayed on the measuring machine (invariant 5).
