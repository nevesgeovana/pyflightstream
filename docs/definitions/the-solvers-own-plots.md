## The solver's own plots

A steady point, and an unsteady one (the first two),
saves the plots the solver draws of its own solve, next to its exports, one
text file each:

| `[exports]` key | The plot | File | Default |
|---|---|---|---|
| `plot_residuals` | the residual history | `<point>_plot_residuals.txt` | on |
| `plot_loads` | the load history | `<point>_plot_loads.txt` | on |
| `plot_sections_cp` | the Cp of every surface section | `<point>_plot_cp_sections.txt` | on where `[[sections.distributions]]` declares sections |

Each is switched off with `false` under `[exports]`. `plot_sections_cp = true`
in an artifact that declares no sections is refused, because the plot would
show no section.

The script chooses each plot with `SET_PLOT_TYPE` (`RESIDUALS`, `LOADS`,
`SECTIONS_CP`) and saves it with `SAVE_PLOT_TO_FILE`, the file on the line
after the command, after every other export of the point and before its log.
Both commands are `verified` on 26.124 (RPT-067) and documented, never run,
on every other build.

**What a file holds.** The plotted SERIES as text, not an image: the run header
the loads export prints, the column names, one row per point of the plot and
the units footer. The residual and the load histories have one row per solver
iteration (residuals of velocity and pressure; lift, induced drag from
vorticity and pitching moment). The section Cp has one x/Cp column pair per
section.

**A plot is a display of the solve, never a source of a coefficient.** The
files are collected into `datapoints/DP-<point>/` and hashed in the run record
like every export of the point, and nothing in this package reads a number
from them. On 26.124 the last plotted lift equals the exported CL, the plotted
induced drag is close to the exported CDi without equalling it, and the
plotted pitching moment is not the exported CMy at all (-0.897 against
-0.0247). Every coefficient on this page comes from the loads export.

**An unsteady point saves the residual and the load plots too** (G26), on by default as on a steady point, ONCE, after the march and before its
log, and again in the wall clock's rescue, which is the end of the run; never
inside the per-step exports, which would save the same growing file at every
step. After an unsteady solve on 26.124 each file holds the series of the
whole march, one row per INNER iteration (857 rows over 12 time steps), and the
last plotted lift is the exported CL (RPT-076). A history per time step is the
unsteady force plot, `<point>_plots.txt` through `[plots]`, as before. **The
section Cp plot joins supported unsteady rows in 0.29.0**: it is saved once
after the march when the pproc declares section distributions, never by each
per-STEP action. The earlier steady-only refusal applies to prior releases.
A plot is not a sectional-load table; see [unsteady plots and averages](../unsteady-postprocessing.md)
for the measured final-export control and history-coverage limits.
