## Native surface flow exports

VTK (`.vtk`) and FEM CSV (`.csv`) are native solver surface exports; the
Tecplot (`.dat`) is written by the package from the VTK ([below](#the-tecplot-surface-is-written-from-the-vtk-since-0280)). New Tecplot requests also retain the native nodal-strength source described in
[the 0.29 amendment](#native-nodal-strength-in-0290). VTK and CSV
are **off by default**. The pproc can request them and select VTK variables by
their command-database names:

```toml
vtk_variables = ["X", "Y", "Z", "CP_FREESTREAM"] # top-level; optional

[exports]
vtk = true
csv = true

[time_averaging]
last_revs = 1.5 # OR last_iters = 54; exactly one, positive
```

**The force distribution is off by default too**.
`force_distributions = true` under `[exports]` saves
`<point>_force_distributions.txt` on every run type: the pressure and viscous
force coefficients of every surface panel, by boundary, which
`pyflightstream.results.parse_force_distributions` reads. It is exported once,
at the end of the run, with every surface (`SURFACES -1`): an unsteady row does
not add it to its per-step exports, and its wall-clock rescue does write it.
The file grows with the mesh, which is why it is asked for rather than given.
An export taken before the solver has iterated can hold no panel.

Without `vtk_variables`, VTK uses the command's all-variables form. Both forms
exclude the wake. CSV exports `CP-FREESTREAM`, `PASCALS`, all surfaces, in the
solver reference frame (frame 1 on builds whose grammar includes it). Unknown
VTK variables and commands unavailable on the selected build are refused at
plan. Both formats also join the per-step `EXPORT_UNSTEADY_AFTER_REV` or
`EXPORT_UNSTEADY_AFTER_ITER` exports.

<a id="the-tecplot-surface-is-written-from-the-vtk-since-0280"></a>

### The Tecplot surface is written from the VTK

**Historical 0.28.x contract.** The following description applies to records
without the native-source declaration. New 0.29.0 records follow
[the amendment below](#native-nodal-strength-in-0290); historical outputs keep
the meaning their recorded release gave them.

**A 0.28.x campaign point does not request native Tecplot.** Where `[exports]`
keeps `tecplot` (the default), the script exports the surface as VTK
(`EXPORT_SOLVER_ANALYSIS_VTK`, every surface) and the package writes the `.dat`
from it, at the name the solver's own Tecplot had, in the point's
`datapoints/DP-<point>/`, before the point's outputs are collected. The run
hashes it with them, so every reader downstream finds it where it was. **One VTK
export per point feeds both**: where the pproc also asks `[exports] vtk`, the
user's VTK is that very file. Where it does not, the VTK is exported under the
Tecplot's own name with `.vtk`, kept beside it and listed among the point's
outputs, because the `.dat` names it. Without `vtk_variables` it is the
all-variables form, `SET_VTK_EXPORT_VARIABLES -1 DISABLE`, which writes no
`<name>_wakes.vtk` (RPT-074).

| | the solver's own Tecplot, to 0.27.x | the package's 0.28.x contract |
|---|---|---|
| zone | one FEPolygon zone, BLOCK packing | the same |
| nodes | `X`, `Y`, `Z`, in the reference frame | the same nodes, in the reference frame; under mirror or periodic symmetry, followed by the images of the surface (below) |
| values | per NODE, by a cell-to-node rule of the solver's | per CELL, `VARLOCATION` cell-centred: exactly the value the solver computed on each panel, nothing interpolated |
| variables | sixteen, `Singularity_strength` among them | every variable the VTK carries, under the VTK's names: nineteen in the all-variables form |
| faces | each polygon's edges, the polygon on the left, none on the right | the same |

- **The frame.** The solver writes the VTK in the ANALYSIS LOADS FRAME, the frame
  `SET_SOLVER_ANALYSIS_LOADS_FRAME` names: a point `p` is written
  `p' = R (p - o)`, `R`'s rows the frame's axes in the reference frame and `o`
  its origin (RPT-074). The package undoes it with the loads frame the script
  itself set, as the script placed it: it emitted the frames and the
  loads-frame command, so it knows `R` and `o`. A loads frame the script did not
  place (one an opened project carries, or one a command moved in a way the
  package does not follow) is refused at plan, naming the frame.
- **The velocity components are written back the way the solver wrote them, as
  a point is, origin included.** On RPT-074's recorded files the norm of `Vx`,
  `Vy`, `Vz` equals the panel's own `Velocity` to 7e-15 at the median only once
  the frame's origin is put back, `v = R^T v' + o`, on 6867 of 7167 panels of
  both the plain and the turned frame; turned back as a vector alone it misses
  by 9.0 m/s at the median, the origin's 9.152 m read as a speed. So the
  components are undone exactly as the nodes are. Every other value is a scalar
  and is written as the VTK holds it. A `vtk_variables` naming some of `VX`,
  `VY`, `VZ` and not all three is refused at plan where the loads frame is not
  the reference frame, since each component was written from all three.
- **A row under symmetry carries its images.** Under mirror symmetry the VTK,
  and so the `.dat`, holds the modelled surface followed by its mirror image in
  `y`; under periodic symmetry, the modelled blade followed by its copies turned
  about the rotor's axis, one per other blade. The solver's own Tecplot held the
  modelled surface alone. The first block of nodes and polygons is that surface,
  node for node: the 99 Tecplot files of the tier-3 points on 26.124 against the
  solver's own of the same solves are equal on 86, and on the 13 mirrored or
  periodic ones the first block is equal to 3e-17 m and the rest are the images
  (RPT-080). A reader that sums over every panel of such a `.dat` sums the whole
  body, not the half or the one blade the solver's file held.
- **`Singularity_strength` is not carried.** It is the panel strength the
  solver's Tecplot prints, and the VTK does not hold it. The VTK adds seven the
  solver's Tecplot did not carry: `Normalized_Vorticity`, `Cp_freestream`, the
  momentum and displacement thicknesses and the shape factor of the boundary
  layer, `Static_pressure_ratio` and `Boundary_Index`.
- **The names are the VTK's.** Where the solver's Tecplot printed `CF`, `Cp`,
  `Mach Number`, `BL Thickness`, the `.dat` carries `skin_friction_coeff.`,
  `Cp_reference` (and `Cp_freestream` beside it), `Mach_Number`, `BL_Thickness`,
  and so on; nothing is renamed, because which of the two pressure coefficients
  the solver's `Cp` was is not identified (RPT-074). With `vtk_variables` a
  subset, the `.dat` carries that subset.
- **Cell values against nodal ones.** A translated file is not the solver's
  Tecplot to the digit: that one holds nodal values, this one the cell values
  they were averaged from. On RPT-074's solve, each cell value against the mean
  of the solver's nodal values at that polygon's nodes differs by a median of
  0.0025 in `Cp` (1.66 at most) and 3.3e-6 in `CF`.
- **What the file states about itself.** Its `DATASETAUXDATA` records name its
  VTK (`SOURCE_VTK`) and that file's sha256 (`SOURCE_VTK_SHA256`), say it is a
  translation, cell-centred, in the reference frame (`TRANSLATION`), name the
  frame undone (`SOURCE_FRAME`) and say `Singularity_strength` is not carried
  (`NOT_CARRIED`). Its `products.json` entry states the same as
  `translated_from`, `source_sha256`, `location` (`cell-centred`), `frame`
  (`reference`) and `not_carried`; the PROV document attributes it to the
  package and derives it from the VTK. The run record's `surface_translations`
  states each translation, its frame and the files written, and why one could
  not be; a Tecplot the run could not write is a named skip,
  `tecplot/<run id>`.
- **Per step, the same route.** `EXPORT_UNSTEADY_AFTER_ITER` and
  `EXPORT_UNSTEADY_AFTER_REV` export the step's VTK, and the run writes each
  `<name>_iteration=<step>.dat` from the `<name>_iteration=<step>.vtk` beside it.
  The wall clock's rescue exports the VTK too, and its `.dat` is written the same
  way.
- **The additional post** writes its Tecplot the same way, in the run's loads
  frame as the run's own script placed it. **A continuation's** loads frame is
  the saved simulation's, and the run takes its placement from the run it
  continues; a record stating no placement requires recovery, and an unrecoverable continuation is
  refused at plan, before anything is archived, unless its pproc sets
  `tecplot = false`.
- **What keeps its own route.** The volume section's Tecplot
  (`[volume_section] format = "tecplot"`, `EXPORT_VOLUME_SECTION_TECPLOT`), the
  probe files of `pyflightstream.post.writers` and a hand-written script's
  `helpers.export_results(tecplot=...)` are what they were. Only the campaign's
  surface export, `[exports] tecplot`, is written from the VTK.
- **A record carrying native Tecplot** keeps that file and its recorded meaning: nothing reads it again.

### Native nodal strength in 0.29.0

A new workspace Tecplot surface request retains both its VTK source and a
native auxiliary `*_native_tecplot.dat`, including each requested STEP. The
package-written product keeps the VTK's physical cell fields and adds the
native source's actual nodal `Singularity_strength` after a unique coordinate
bijection and complete polygon-topology match. It does not derive strength
from Cp, interpolate cell Cp to nodes, or treat equal counts as equal geometry.

Both source hashes, the complete recorded loads frame, output hash and matching
evidence accompany the mixed nodal/cell association. Each STEP uses its own
source; missing or ambiguous evidence is named rather than filled from the
final export. Historical records without that declaration keep the 0.28.x
VTK-only contract and its explicit missing-strength statement. See
[surface translation](../surface-translation.md) for the exact source/association
and recovery contract.

<a id="the-strength-is-asked-for-since-0300"></a>

### The strength is asked for

**The native export is made only where the row's pproc sets
`singularity_strength = true`.** The key is off by default. Off, the point
exports no `*_native_tecplot.dat`, at the end of the run or at any step; its
translation record names no native source; the `.dat` follows the 0.28.x
contract above, every VTK variable cell-centred with `Singularity_strength` in
`NOT_CARRIED` and `not_carried`; and the point is not
`FAILED_INCOMPLETE_OUTPUT` for a native file it was never asked to write. The
time-averaged surface below averages the VTK variables and states the strength
not carried. On, every point and step is exported, matched and recorded exactly
as in 0.29.0. `pyfs-matrix plan` states per row declaring a Tecplot surface
whether the strength is carried.

<a id="the-time-averaged-surface-is-the-packages-since-0280"></a>

### The time-averaged surface is the package's

**`[time_averaging]` makes the run export the surface at every step of its
window, and the post averages those exports.** `SOLVER_TIME_AVERAGING` is never
emitted: on 2026-09-19 licensed C01 measured it hanging FlightStream 26.124 in
the position the package emitted it (no output was written before the
termination at 240.5 seconds; receipts under `reports/pfs0250/`), and 26.123
stops at it (RPT-079). The table is `last_iters` or `last_revs`, exactly one,
positive, as before.

- **The window.** Inclusive, 1-based time steps ending at the run's last time
  step: `last_iters` is a count of steps; `last_revs` uses the rotor clock and
  the rounding of `LAST_REVS_AVG` (with `DELTA_THETA`, steps per revolution is
  `360 / DELTA_THETA`). A window longer than the run is clipped at step 1. The
  steps are the time steps the per-step counter counts and the solver stamps on
  each export as `_iteration=<step>` (RPT-041); the export header's
  inner-iteration counter is never read for them.
- **How the steps are exported.** Through the per-step export machinery of
  [the sections](the-sections-table-and-which-row-is-which.md#per-distribution-sectional-loads-and-cp-0250): a row stating no
  `EXPORT_UNSTEADY_AFTER_ITER` or `EXPORT_UNSTEADY_AFTER_REV` exports as one
  stating `EXPORT_UNSTEADY_AFTER_ITER: <the window's first step>` would, every
  per-step kind of its outputs from that step to the end, the surface's VTK among
  them. A row stating a threshold at or before the window's first step keeps it;
  one after it is refused at plan, naming both steps, since the steps before it
  would never be exported. The build must carry the unsteady solver action
  (`SET_NEW_UNSTEADY_SOLVER_ACTION`, 26.122 on); the point must export its
  Tecplot, which the average is written as. A steady row, and an additional
  pproc, refuse the table.
- **What is averaged.** The same PANEL, the VTK's cell index, across the steps of
  the window, each step's values first written back in the reference frame as
  its Tecplot is (the velocity components undone as a point is, above). Every
  step weighs the same, and nothing is interpolated. The average is
  `blade_passage_average`, the package's one averaging routine, with the panels
  as its samples and the steps as its frames. Every physical cell field the VTK
  carries is averaged, `skin_friction_coeff.` (CF) included. In 0.29.0, available native
  nodal strength is averaged separately from the cell fields using every
  selected STEP's matched source. Coordinate fields retain the last selected
  STEP; they are never averaged into a different geometry.
- **What the solver's own average says about it.** On 26.122, where the solver
  runs `SOLVER_TIME_AVERAGING`, its final surface equals, to 1e-13, the uniform
  mean of the same run's per-step instants over the same inclusive time steps,
  for `Cp`, `Vx` and `Velocity`: the package's average matches the solver's to
  machine precision for the flow variables (RPT-079). The solver keeps CF at its
  last instant; the package averages CF as it averages every other variable.
- **Refused, or skipped, by name; never partial.** Steps that do not share one
  topology (the node count, the polygon count and the nodes around every
  polygon) refuse the average, naming the step: a panel cannot be followed
  across them. A step of the window that was not exported (a run stopped by its
  wall clock before the window ended, a continuation, whose step counter starts
  again) skips the average, naming the missing steps: an average of the steps
  that were would not be the window's. Both are named skips in `products.json`
  and `post.log`. A window that reaches a frozen part of the solve is warned
  about, as every other average is, and under `--check-frozen` it is refused
  before anything is written: no file, no entry, the reason under its name.
- **Where its nodes are.** The averaged file's nodes are those of the window's
  LAST step: on a turning rotor the nodes move from step to step, and their mean
  would be a surface nobody flew.
- **The product.** `surfaces/<point>_time_average.dat` under the matrix's
  products, written by the writer of every Tecplot (one FEPolygon zone, every
  VTK value per panel, cell-centred, in the reference frame, plus real nodal
  strength for 0.29.0 records declaring that source), and
  `surfaces/<point>_time_average.vtk` beside it where the pproc asks
  `[exports] vtk`. Its `DATASETAUXDATA` records say what it is an average of
  (`AVERAGE_OF`, `WINDOW`, `COORDINATES`, `TRANSLATION`, `SOURCE_FRAME` and
  either the actual native-source evidence or the historical `NOT_CARRIED`). Its `products.json` entry carries `kind: average`, the
  recorded `window`, the `steps` averaged, `inputs` (each per-step VTK read and
  its sha256), `averaged_by: pyflightstream`, `weighting: uniform`,
  `coordinates_step`, and `location`, `frame` and `not_carried` as every
  translated Tecplot does. The frozen-solve rule of every average applies: a
  freeze inside the window warns, and `check_frozen` refuses.
- **Native comparison limits in 0.29.0.** Native fields can retain a final
  instant even where the package computes their temporal mean. Those statistics
  are not equivalent. The measured WALLTIME discrepancy retains a named
  surface-average refusal; see [unsteady products](../unsteady-postprocessing.md)
  for the observed build, STEP coverage and accepted limits.
- **The instants stay.** Every per-step VTK and the Tecplot written from it stay
  on disk and in `products.json` as `kind: instant`, and so do the end of the
  run's surface exports.
- **The run records the window**, as `surface_average_window`, and the post reads
  that record, never a pproc edited since; a continuation keeps the window of
  the run it continues. Changing the window of a recorded run needs a new run,
  since the steps before the window's first were not exported.
- **A historical record** that carries the solver's window
  (`surface_time_averaging`, `verification: UNVERIFIED`) keeps the meaning its
  release gave it: its native surface exports are `kind: average` over that
  window, per-step entries end their window at the export's step, and exports
  before the window's start are named skips.

---
