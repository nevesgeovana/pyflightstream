# RPT-074: the VTK surface export carries more than the Tecplot, per cell, in the loads frame (2026-09-25)

**Date:** 2026-09-25
**Found by:** the licensed probe T45 of the 0.28.0 work
**Status:** CLOSED in 0.28.0 (G45: the Tecplot surface of a campaign point is written by the package from the VTK, cell-centred, in the reference frame, the only route)
**Affects:** `EXPORT_SOLVER_ANALYSIS_VTK` and `EXPORT_SOLVER_ANALYSIS_TECPLOT` on 26.124

## What this settles

0.28.0 makes the VTK the ONE route to a Tecplot surface: the solver exports the
VTK, which carries more variables, and the package writes the `.dat` from it.
Before a translator can be written, four things had to be known: what the VTK
holds beside the solver's own Tecplot of the same solve, whether the two describe
one surface, in which frame each is written, and how each locates its values.
**The VTK carries 19 surface variables against the Tecplot's 13, per CELL, on the
same 7252 nodes and 7167 polygons; it is written in the ANALYSIS LOADS FRAME,
points and velocity components alike, while the Tecplot stays in the reference
frame and carries its values per NODE.**

## What was run

FlightStream 26.124 (build 8172026), one steady point of a wing-body (the
control point of RPT-060: 30_WB, alpha 2 deg, `SOLVER_SET_FARFIELD_LAYERS 5`, its
loads frame 2 named MRP at x = 9.152 m, set by `SET_SOLVER_ANALYSIS_LOADS_FRAME 2`),
run four times in two detached batches with no solver alive before either, each
variant moving ONE thing against the control:

| variant | added after the Tecplot export | moved against |
|---|---|---|
| S_C | nothing (the control) | |
| S_VTK | `EXPORT_SOLVER_ANALYSIS_VTK` with `SURFACES -1` | S_C |
| S_VTKALL | `SET_VTK_EXPORT_VARIABLES -1 DISABLE`, then the same export | S_VTK |
| S_VTKROT | as S_VTK, frame 2's axes turned 90 deg about z (x' = y, y' = -x), its origin kept | S_VTK |

The export lines are the ones the package's emitter writes. A first batch wrote
them by hand, `-1` where the grammar wants `SURFACES -1`: the solver refused that
line by number, stopped the script there and still returned 0, so every export
after it was missing. That run is not evidence of anything but that.

## What came back

- **Every variant returned 0 with the control's loads to the print.** The VTK
  export changes no coefficient.
- **The VTK is legacy ASCII polydata**: `POINTS 7252`, `POLYGONS 7167`, then
  `POINT_DATA` holding X, Y and Z, then `CELL_DATA` holding 19 scalars:
  `Normalized_Vorticity`, `skin_friction_coeff.`, `Cp_reference`,
  `Cp_freestream`, `Mach_Number`, `Area`, `Vx`, `Vy`, `Vz`, `Velocity`,
  `BL_Thickness`, `BL_streamline_length`, `Transition_marker`,
  `Separation_marker`, `BL_momentum_thickness`, `BL_displacement_thickness`,
  `BL_shape_factor`, `Static_pressure_ratio`, `Boundary_Index`.
- **The solver's Tecplot is one FEPolygon zone in BLOCK packing**, 7252 nodes,
  7167 elements, 28600 faces, 16 variables: X, Y, Z, `Singularity_strength`, CF,
  Cp, Mach Number, Area, Vx, Vy, Vz, Velocity, BL Thickness, BL streamline
  length, Transition marker, Separation marker. Its value count is exactly 16 x
  7252 plus the face records (57200 face nodes, 28600 left and 28600 right
  elements), so **every Tecplot variable is nodal**.
- **One surface.** After the frame is undone, the VTK's 7252 points are the
  Tecplot's 7252 nodes, every one matched by its coordinates.
- **The VTK is written in the loads frame.** With frame 2 a translation, the VTK's
  points are the Tecplot's shifted by -9.152 m in x. With frame 2 turned, they are
  p' = R (p - o), R's rows the frame's axes in the reference frame and o its
  origin, for every point; the per-cell velocity components turn with it (Vx of
  the turned run equals Vy of the plain one and Vy equals minus its Vx, to the last
  digit), and Cp and the speed do not change. The Tecplot of both runs is in the
  reference frame. The loads export turns too (Cx and Cy exchange, as the frame
  says).
- **The default selection writes the wake as well.** Without
  `SET_VTK_EXPORT_VARIABLES` the export also writes `solution_wakes.vtk` (1364
  points, no polygon); with `-1 DISABLE` it does not. The surface file is the same
  in both.
- **The Tecplot's nodal values are not a plain or an area-weighted mean of the
  VTK's cell values.** Over the 7252 matched nodes the closest of the two rules
  still differs by up to 0.29 in Cp; the solver's own cell-to-node rule was not
  reproduced here.

## What it means for the package

- **A translator writes the VTK's values as the solver computed them, per cell**
  (`VARLOCATION` cell-centred in the Tecplot zone), and the coordinates and the
  velocity components back in the reference frame, by the loads frame the script
  itself set, so the translated file sits where the solver's Tecplot sits.
- **One variable is lost on that route: `Singularity_strength`**, the panel
  strength the Tecplot carries and the VTK does not. Every other Tecplot variable
  has its VTK counterpart (Cp as `Cp_reference`, the reference and free-stream
  velocities being equal here), and the VTK adds seven: `Normalized_Vorticity`,
  `Cp_freestream`, the momentum and displacement thicknesses and the shape factor
  of the boundary layer, `Static_pressure_ratio` and `Boundary_Index`.
- **A translated file is not the solver's Tecplot to the digit**: the solver
  averages its cells onto its nodes by its own rule, and the translation keeps the
  cells. A comparison of the two is a comparison of cell values with nodal ones.

## What this does not settle

- The solver's cell-to-node rule.
- A run whose reference and free-stream velocities differ, where `Cp_reference`
  and `Cp_freestream` part; the Tecplot's Cp was not identified between them here.
- A loads frame with an axis tilted out of the xy plane (only a turn about z was
  run), and the per-step exports of an unsteady run, which are written by the same
  command at each step.

## Addendum, 2026-09-25: the velocity components carry the frame's origin

Read from the same recorded files while G45 was built, with no new run. The
velocity components are written the way a point is, ORIGIN INCLUDED:
`v' = R (v - o)`, not `R v`. With the origin put back, `v = R^T v' + o`, the
norm of `Vx`, `Vy`, `Vz` equals the panel's own `Velocity` scalar to 7e-15 at
the median, on 6867 of the 7167 panels of S_VTK and of S_VTKROT alike; turned
back as a vector alone it misses by 9.0 m/s at the median, the origin's 9.152 m
read as a speed. The comparison with the solver's Tecplot agrees: each panel's
`Vx` against the mean of the solver's nodal `Vx` at its nodes differs by 0.087
m/s at the median once the origin is put back, and by 9.17 m/s before. The
exchange of `Vx` and `Vy` between the plain and the turned frame reported above
holds either way, because the two runs share their origin; it could not tell
the two readings apart. On the remaining 300 panels the `Velocity` scalar is
not the norm of the three components under either reading. G45 undoes the
components exactly as it undoes the points.

## Evidence

The scripts the solver received and their outputs are kept machine-local with the
probe drivers `p28_driver.py`, `compare_vtk_tecplot.py`, `nodal_rule.py` and
`frame_rule.py`; the GOAL-032 ledger's T45 receipt names every path, the
executable's sha256 and the preflight of each batch.

**Verdict: VERIFIED**, for what was run: the VTK surface export runs on 26.124
beside the Tecplot, describes the same surface with 19 per-cell variables against
the Tecplot's 13 nodal ones (Singularity_strength the one it lacks), and is written
in the analysis loads frame, points and velocity components, while the Tecplot is
written in the reference frame.
