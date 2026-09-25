# RPT-076: the solver saves its residual and load plots after an unsteady solve too (2026-09-25)

**Date:** 2026-09-25
**Found by:** the licensed probe T22 of the 0.28.0 work
**Status:** CLOSED in 0.28.0 (G26: an unsteady row saves the residual and load plots once, after the march)
**Affects:** `SET_PLOT_TYPE` and `SAVE_PLOT_TO_FILE`, verified on 26.124 after a steady solve (RPT-067) and never run after an unsteady one

## What this settles

Since 0.27.0 a steady point saves the plots the solver draws of its own solve
(residuals, loads, sections Cp), and an unsteady row refuses them, because the
commands had only been run after a steady solve. **After an unsteady solve on
26.124 both the residual and the load plot are saved, as text, one row per inner
iteration of the whole march, and the last plotted lift is the exported CL.**

## What was run

FlightStream 26.124 (build 8172026), one unsteady point of a wing (T09's point
4301 of the tier-3 workspace, 12 time steps, `SOLVER_SET_FARFIELD_LAYERS 5`, its
per-step exports by the action program), run three times in one detached batch
with no solver alive before it:

| variant | added just before the log export |
|---|---|
| U_C | nothing (the control) |
| U_RES | `SET_PLOT_TYPE RESIDUALS`, `SAVE_PLOT_TO_FILE` and the file |
| U_LOADS | `SET_PLOT_TYPE LOADS`, `SAVE_PLOT_TO_FILE` and the file |

## What came back

- **Every variant returned 0 with the control's loads to the print**, and the
  per-step exports of all twelve steps.
- **Each plot variant wrote its file**: 82 kB for the residuals and 123 kB for the
  loads, the text form RPT-067 recorded for a steady solve: the run header
  (`Solver mode: Unsteady`, the time increment, the iteration count), the column
  names, one row per point of the series, and the units footer.
- **One row per inner iteration of the whole march**: 857 rows, the header's
  "Current solver iteration number: 857", over the twelve steps. The load plot's
  columns are lift, induced drag (vorticity) and pitching moment against the
  iteration.
- **The last plotted lift is the exported CL** (0.000228 in both).

## What it means for the package

- **An unsteady row can save the residual and the load plots**, once, after the
  march and before its log, as a steady point does; never inside the per-step
  exports, which would save one at every step.
- The series is indexed by inner iteration, not by time step: a reader wanting
  the history per step reads the unsteady force plots (`[plots]`) as before.

## What this does not settle

- `SECTIONS_CP` after an unsteady solve, which was not run.
- A rotor row, and a march stopped by the wall clock.

## Evidence

The scripts the solver received and the plot files are kept machine-local with the
probe driver `p28_driver.py` (variants U_C, U_RES, U_LOADS); the GOAL-032 ledger's
T22 receipt names every path, the executable's sha256 and the batch's preflight.

**Verdict: VERIFIED**, for what was run: after an unsteady solve on 26.124
`SET_PLOT_TYPE` with `RESIDUALS` or `LOADS` and `SAVE_PLOT_TO_FILE` run, change no
coefficient, and save the series of the whole march, one row per inner iteration.
