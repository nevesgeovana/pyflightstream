# RPT-067: the plot commands write the plotted series as text (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed probe T13 of the 0.27.0 work
**Status:** CLOSED in 0.27.0 (G04 saves the residual and load plots of every point by default, and the section Cp plot when the point has sections)
**Affects:** `SET_PLOT_TYPE` and `SAVE_PLOT_TO_FILE`, which the command database records as documented and not run on 26.124

## What this settles

The GUI's plot window shows the residual history, the load history and the
section Cp of a solve. Two script commands reach it: `SET_PLOT_TYPE <type>` picks
what is plotted, and `SAVE_PLOT_TO_FILE` saves it. Before a run saves these by
default, three things had to be known: whether the commands run in a script on
26.124, what they leave, and whether they disturb the solve. **They run, they
write the plotted SERIES as a text file rather than an image, and the solve and
its exports are unchanged.** The residual and load histories carry one row per
solver iteration, and the section Cp carries one x/Cp pair per section.

## What was run

FlightStream 26.124, four solves of one point, launched one at a time, detached,
with no solver alive before the first. The point is RPT-060's control: the half
wing-body of RPT-052 at alpha 2, steady, `SOLVER_SET_FARFIELD_LAYERS 5`, twelve
surface sections. The control adds nothing to the script. Each variant adds ONE
plot type after the exports, with the path on the line after the save, as the
manual's sample writes it:

    SET_PLOT_TYPE RESIDUALS
    SAVE_PLOT_TO_FILE
    <path of the file to write>

    build       FlightStream 26.124 (build 8172026, executable sha256 68e64e66...)

## What came back

| run | the one addition | return code | file written | what it holds |
|---|---|---|---|---|
| control | nothing | 0 | none | |
| residuals | `SET_PLOT_TYPE RESIDUALS` and the save | 0 | yes | velocity and pressure residuals, 181 rows |
| loads | `SET_PLOT_TYPE LOADS` and the save | 0 | yes | lift, induced drag (vorticity) and pitching moment, 181 rows |
| section Cp | `SET_PLOT_TYPE SECTIONS_CP` and the save | 0 | yes | 12 sections, one x/Cp column pair each |

The solve converged at iteration 181, and each history has exactly 181 rows. The
file opens with the same run header as the loads export, then the column names,
then the rows, then the units footer. The loads export of every variant has the
same `Total` row as the control's, digit for digit. The solver prints nothing when
it saves a plot.

## What it means for the package

- A run can save these three plots per point with no cost to the solve. What it
  keeps is data, not a picture, and that makes it more useful: the residual
  history shows how the point converged, and a reader can re-plot it.
- **A plot is a display of the solve, and never a second source of a
  coefficient.** The last plotted lift equals the exported CL. The last plotted
  induced drag (0.0043877) is close to the exported CDi (0.0043872) but not equal
  to it. The plotted pitching moment (-0.897) is not the exported CMy (-0.0247) at
  all, so it is taken about some other point or scale that this run does not
  identify. Every coefficient the package reports keeps coming from the loads
  export.

## What this does NOT establish

- **One build, one steady point.** The other plot types, and unsteady runs, were
  not tried.
- **What the plotted pitching moment is.** Only that it is not the exported CMy.
- **A save before a solve**, or a save to a path whose folder does not exist.

## Evidence

`reports/probes/RPT-067_2026-09-24_evidence.yaml`: per run, the plot type, the
return code, the size of the file written, the exported `Total` row, and the
script's digest; the eight checks as booleans, and the columns and last values
compared above. The solver outputs stayed on the measuring machine (invariant 5).

## Addendum, 2026-09-24: the relative form

The run above saved one plot per script to an absolute path. A steady
workflow point saves two in a row, each to its own RELATIVE name, after its
exports and before its log. One more run of the same control point, launched
detached with no solver alive before it, emitted exactly that block:

    SET_PLOT_TYPE RESIDUALS
    SAVE_PLOT_TO_FILE
    <point>_plot_residuals.txt

    SET_PLOT_TYPE LOADS
    SAVE_PLOT_TO_FILE
    <point>_plot_loads.txt

Both files landed in the run's working folder, each under the plot header,
the loads export was identical to the control's, and the log was exported
after them. So the form a campaign writes is the form measured, on 26.124.
Evidence: `reports/probes/RPT-067_2026-09-24_relative-form.yaml`. No line
above was changed.
