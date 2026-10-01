# RPT-112 - pyflightstream 0.33 licensed round L1: the step counter on an unsteady row without per-step export, on FlightStream 26.124 (2026-10-01)

The report of the counter rows of licensed round L1 of pyflightstream 0.33.0
(GOAL-038, arm L1), for **FR-314** (item PROGRESS-ALL-UNSTEADY of the 0.33.0
scope): every unsteady row registers the step counter, and on a row that asks
no per-step export the counter only counts. The rows ran through the package
route (`pyfs-matrix plan`, then `pyfs-matrix run --local --progress-every 2`)
on **FlightStream 26.124, build 8172026**, executable SHA-256 withheld from
the public tree per NFR-31. One solver instance at a time, hidden, far field
5 layers. The package is the tree at `6e046291`. No solver was run to write
this report.

Only nondimensional values are stated: Mach and Reynolds numbers, angles,
counts, coefficients and ratios.

## 1. What the emitted scripts changed

Before the round, the scripts 0.33.0 emits for these rows were compared with
the ones v0.32.0 emits for the same matrices: the only difference is the
counter's registration, three lines (`SET_NEW_UNSTEADY_SOLVER_ACTION
COMMAND_LINE pfs_unsteady_counter`, the program line, a blank line), placed
before the wall-clock action (FR-314 R4). The program staged beside each
point is the count-only one: it writes no export file and triggers no
exports script (FR-314 R2).

## 2. One row per point

| row | run type | geometry | steps | record status | counter count | progress lines on the local run | actions that failed to execute |
|---|---|---|---|---|---|---|---|
| 3312 | unsteady (no rotor) | tier-3 wing, Mach 0.1, angle of attack 2 degrees | 12 | `CONVERGED` | 12 of 12 | 2 (steps 6 and 11) | 0 |
| 3311 | unsteady, periodic sector (RPT-111) | private | 8 | `CONVERGED` | 8 of 8 | 4 (steps 3, 5, 6, 8) | 0 |
| 9321 | unsteady_rotor (parity, RPT-113) | the rotor of RPT-094 | 36 | `CONVERGED` | 36 of 36 | 17 (steps 2 to 34, every 2) | 0 |
| 9322 | unsteady_rotor (parity, RPT-113) | the rotor of RPT-094 | 36 | `CONVERGED` | 36 of 36 | 18 (steps 2 to 36, every 2) | 0 |

The count file of each point equals its steps, and the solver log shows the
counter executed once per step (8, 12, 36, 36), with 0 error or unrecognized
lines on every row.

What the rows show:

- The solver accepted the counter on every row without per-step export; the
  count equals the time steps (FR-314 R1).
- The local run printed the progress bar from the counter on all four rows.
  On the 36 step rows the bar advanced every 2 steps; on the short rows (8 and
  12 steps) it printed at the polling instants, so the steps it names (3, 5,
  6, 8 and 6, 11) are not all multiples of 2. The summary script's own count
  of "progress lines naming steps" read 0 because it looked at standard
  output, while the bar is written to standard error: the lines above were
  counted from the per-step logs by hand.
- No export file was written by the counter: the staged program is the
  count-only one and the actions folder of each of the four points holds only the count file, the counter program and the wall-clock actions, and no export file.

## 3. The counter and the results (FR-314 R5)

Rows 9321 and 9322 are rows of the parity campaign (RPT-113): their 0.33.0
scripts differ from the recorded ones by the counter alone. Every coefficient,
section and probe table of the two rows is identical to the recorded run in
every cell (the only differing cells are run timings), so the counter does not
leave the solver's results changed: it leaves them unchanged on a row without
export.

## 4. Verdict

FR-314 licensed confirmation on 26.124 (build 8172026): the counter runs on an
unsteady row without per-step export, on four rows of three kinds (a wing, a
periodic sector and a rotor), counts every step, fails no action, writes no
export and leaves the results unchanged. The exact cadence of the bar on a row
shorter than the polling interval is a limit of what was read, stated in
section 2.
