# Compat report: FlightStream 26.122 (2026-09-25)

This is a compat-format transcription of the licensed probe T21, reported as RPT-079
(`reports/RPT-079_the-solver-averages-the-surface-over-time-steps-on-26122_2026-09-25.md`).
No solver was invoked while writing it, and it does not claim a probe-harness
execution. The paired YAML records the `verified` outcome for `SOLVER_TIME_AVERAGING`
on 26.122, folded into the command's multi-line row by hand, since the promotion
cannot rewrite a row that carries a note.

| Run | The one addition, just before `INITIALIZE_SOLVER` | Result | Final surface |
|---|---|---|---|
| Control | nothing | returned 0 in 10.2 s | the last step's instant |
| Averaging | `SOLVER_TIME_AVERAGING ENABLE 7 12` | returned 0 in 10.5 s | the uniform mean of the run's own per-step surfaces over time steps 7 to 12, to 1e-13 |

The run is a 12-step unsteady point (build 8092026). A window one step wider (6 to 12)
or narrower (8 to 12) differs from the final surface by about 0.6 in Cp, so the bounds
count time steps, inclusive and 1-based. The skin friction is not averaged: the final
CF is the last step's. The per-step exports stay instants.

What this does not claim: any other window, a rotor row, a run stopped by the wall
clock, and any build other than 26.122.
