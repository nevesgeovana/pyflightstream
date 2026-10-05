# RPT-153 - Normal probes after an unsteady march (2026-10-05)

FlightStream 26.124, build 8172026; pyflightstream 0.37.0, package rel/0-37 6e039c39; far field 5. These are retained licensed runs, not a rerun. Evidence is cited by file name relative to the run folder.

## Purpose

Record the licensed evidence for FR-417 and FR-418, marker P0370-S5-PROBE-KIND: whether normal probes on unsteady rows represent the marched solution and whether the script update action is needed.

## Method

Four rows compared normal probe exports against the last sample of corresponding unsteady fluid-plot exports. Rows 3701 and 3702 were an unsteady rotor at 30 degrees per step for 6 steps, with 45 probes on 3 lines; the unsteady row exported fluid plots and the paired row exported normal probe points. Rows 3703 and 3704 were an unsteady wing for 6 steps, with 7 probes on one line; the paired exports were likewise fluid plots and normal points. Setup used far field 5. The rendered scripts are retained in `scripts/`.

The initial component-wise criterion in FR-417 compared each component's normal-to-last-sample gap against that component's change over the last step. The accepted vector criterion compares the norm of the three-component gap with either the norm of the last-step change vector or 0.5 percent of the local speed, whichever is larger. The owner accepted this criterion on 2026-10-05 as representing "the state at the end of the march". The no-update arm ran the 3704 script with `UPDATE_PROBE_POINTS` removed.

Sources are `README.md`, `verdict.json`, UTF-16 `judge.log`, `judge2.log`, and rendered scripts in `scripts/`.

## Results

All 52 normal probes moved away from their step-1 value. Under the originally written component-wise rule, 37 of 52 agreed and the verdict failed. The rule was too strict where an individual component barely changed in the last step, leaving no meaningful tolerance for its normal-to-last gap.

Using the accepted vector rule, both row pairs pass. For the rotor pair, the vector gap was at most 0.67 of the last-step vector change, with median ratio 0.22; the largest gap was 2.06 percent of local speed. For the wing pair, the gap was at most 0.15 percent of local speed. At points where the field barely moved, this could be as much as 1.67 times the last-step change. VX agreed to relative 1e-5.

The 3704 no-update arm exported different values in 52 numeric cells, with a largest difference of 33.88 m/s. `judge2.log` records `UPDATE_PROBE_POINTS` as needed. The package's rendered script includes this action, so it supplies the required update.

The evidence supports interpreting a normal probe as the solution state at the end of the march. It is not the same sample as the last fluid-plot step. RPT-083 observed the same distinction between these two export families.

## Limits

One solver build, two cases, and 6 steps per case were measured. No rotor-frame probes were followed in time. The result establishes the observed end-of-march behavior under these settings; it does not establish equivalence of the normal sample and the final fluid-plot sample.

## Addendum: normal probes exported at every step of a window (FR-417 R7)

Row 3705 repeats row 3704 (unsteady wing, 6 steps, 7 normal probes on one line) with `EXPORT_UNSTEADY_LAST_ITER: 3`, on the package at rel/0-37 42334f38, build 8172026, far field 5. The point CONVERGED. The per-step export action created the probe points on its first exporting step and, at steps 4, 5 and 6, updated and exported them as `<point>_probes_iteration=<step>.txt`; the post wrote the probes series with 21 rows (7 probes by 3 steps).

At each of steps 4 to 6 the probe values the action exported equal the fluid-plot values of row 3703 at the same step and point to 0.00048 m/s, the printed precision: probe points exported from inside the march sample the same instant as the fluid plots. The export after the march (the same probes, deleted, created again and updated) differs from the step-6 export by at most 0.051 m/s (0.15 percent of the local speed), which is the end-of-march difference recorded above. Creating probe points from an action script is therefore measured to work on this build. Limits: one case, three steps, one build.
