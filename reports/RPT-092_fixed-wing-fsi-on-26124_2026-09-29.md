# RPT-092 - Fixed-wing FSI with the wing's own weight, confirmed on 26.124 (2026-09-29)

A short licensed confirmation of the 0.30.0 **fixed-wing FSI** route (FSI-G):
a steady row, the structure one clamped wing under its aerodynamic loads and
its own weight, no centrifugal load, run through the package's own path
(`pyfs-matrix plan`, `pyfs-matrix run`, the post that `run` performs) on
**FlightStream 26.124, build 8172026**, executable SHA-256
`68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65` (measured
from the executable that ran, and recorded as `fs_exe_sha256` in both run
records). The package is the tree of `feat/0-30-storage-sync` at `4f12aede`,
which carries the four fixes listed at the end (the records name `c89c603d`,
this report branch on top of it, whose `src/` is identical;
`package_dirty: false`). One solver instance at a time, hidden, far field 5
layers. **Both rows use the pproc's default exports.**

## What was run

The wing is the synthetic NACA 0012 wing of RPT-025 and of the RPT-093 vendor
case (chord 1 m, public shape law), taken as its closed right half: semi-span
4 m from y = 0, root and tip capped, meshed by the package's own generator
(`pyflightstream.qa.geometry.wing_triangles`, 25 chordwise panels per side, 20
spanwise) and imported as an OBJ (1052 vertices). A half wing because the
route is one cantilever clamped at its first station and refuses symmetry
copies. Reference: area 4 m2, chord 1 m, moment point on the quarter chord
(0.25, 0, 0). Mach 0.147, Re 3.42 million on the chord, alpha 5 deg (50.023 m/s,
1.22312 kg/m3 as the run resolves them), steady solver, convergence 1e-5.

The FSI input: `mode = "calculated"`, Ti-6Al-4V grade 5 annealed, nine
stations 0 to 4 m, each the NACA 0012 contour about the quarter chord,
`[config.wing]` with `self_weight = true`, gravity (0, 0, -9.80665) m/s2,
`span_axis = "+Y"`, `origin_m = (0.25, 0, 0)`, `omega_rad_per_s = 0`. The
staged `config.json` states a running mass of 361.006 kg/m, EI 7.6613e6 N m2 and
GJ 1.1587e7 N m2 per station. The section distribution: 20 cuts on XZ in the
MRP frame.

| row | run id | FSI | status | wall time (record `wall_time_s`) |
|---|---|---|---|---|
| rigid | `pfs0300-l1-ws/sim_9211/M147RE342AL+050` | none | CONVERGED (62 iterations) | 2.6 s |
| coupled | `pfs0300-l1-ws/sim_9212/M147RE342AL+050` | `FSI: f011` | CONVERGED (461 cumulative iterations) | 47.0 s |

The whole `pyfs-matrix run` of both rows took 50 s. The post wrote every
product of both points, the coupled point's sections, sectional-loads and Cp
products included, and recorded no skip (`post/l2_wing/products.json`).

## What was measured

**Vertices mapped: 1052 of 1052.** The `$AEROELASTIC$` header of the coupled
run's saved state (`P9212-...fsm`) reads `1,1052,1,50,4`. The script assigns
the surface as `ASSIGN_AEROELASTIC_SURFACES 1` / `2`, the OBJ wing's boundary
ID.

**The residual converges.** Twenty lines in the coupled run's log
(`P9212-..._log.txt`), from `8.8888889E-1` at iteration 1 through
`1.0091703E-2` (8), `4.4380126E-4` (14), `2.0001533E-5` (19) to
`3.5770635E-6` at iteration 20 of 50, below the 1e-5 limit; the configured
relaxation is 0.4 (`fsi_convergence_log.csv`, phase `fixed_wing`). The package
stopped the solver after the completion line (`pyfs-aeroelastic-stop.log`).
The post-processing script (`fsi_post.txt`) updates the sections once, first,
then carries the structure's sectional loads and the row's whole default
export block.

**Tip deflection: -12.71 mm, downward, weight-dominated.** The written tip
displacement (`FSIDisp.txt`, the tip station's three nodes) is -12.705 to
-12.724 mm along z, and 0 in x and y. The convergence log's `tip_flap_m`
column states 1.270541e-02 m, as a magnitude (`fsi/driver.py:653`), so the
sign is read from `FSIDisp.txt`. As a check on the weight, the package's own
structural solve of the staged configuration under its weight alone gives
-14.787 mm at the tip, equal to the cantilever's q L^4 / (8 EI) =
-3540.26 x 4^4 / (8 x 7661281) = -14.787 mm; the aerodynamic normal load of
the last call (1978.8 N) takes 2.08 mm of it back. The exported deformed
surface (`P9212-...vtk`) against the rigid one (`P9211-...vtk`) moves at most
11.73 mm, downward, at the tip's leading edge, and less than 0.02 mm in x and
y.

**CL against rigid.** From the two loads exports:

| quantity | rigid | coupled | coupled against rigid |
|---|---|---|---|
| CL | 0.3383257 | 0.3393173 | +0.29 % |
| CDi | 0.0126215 | 0.0126148 | -0.05 % |
| CDo | 0.0093534 | 0.0000000 | (not in the coupled export) |
| CMy (about the quarter chord) | +0.0027989 | +0.0023671 | -15 % |

The wing bends down by about 0.3 % of its semi-span and its lift barely moves.
As in RPT-090, the coupled export states no viscous drag.

## The two checks the route's memory asked of this run

**(a) The sign of the XZ-cut moment.** The route reads the sectional loads
export's `Moment` of an XZ cut as positive about +y, nose up. Measured: the
rigid run's 20 cuts (`P9211-..._sloads.txt`, every `X_QC` and `Z_QC` 0 in MRP,
so every section moment is about the MRP's own spanwise line) integrate, over
their 0.2 m strips, to **+7.49 N m**; the solver's total moment about the same
line, CMy x q S c = 0.0027989 x 6121.24 N x 1 m, is **+17.13 N m**. The two
agree in sign and not in size (44 %). The same integral of the section forces
Fz gives 2038.4 N against Cz x q S = 2070.7 N (98.4 %), so the strips hold the
lift. The coupled run's own sectional export (`P9212-..._sloads.txt`, equal
to the structure's `FS_SurfaceSection_Loads.txt`) gives +4.91 against
+14.49 N m. The section moment also changes sign along the span (+8.26 N m
near the root, -2.23 N m at 1.9 m, +8.23 N m at 3.7 m), and on a symmetric
section at the quarter chord it is small. So the sign reading is consistent
with the export at the level of the integral; it is not corroborated in
magnitude, and a cambered section (a larger moment about the quarter chord)
would be the sharper test.

**(b) The coupling block after INITIALIZE_SOLVER.** Measured in the coupled
run's script (`sims/sim_9212/scripts/P9212-M147RE342AL+050.txt`, 101 lines):
`INITIALIZE_SOLVER` at lines 54 and 62 (the file route's two
initialisations), then `AEROELASTIC_RBF_TYPE MULTI_QUADRATIC` (78),
`DELETE_AEROELASTIC_STRUCTURAL_NODES` (79), `ASSIGN_AEROELASTIC_SURFACES` (80),
`ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS` (83),
`IMPORT_AEROELASTIC_STRUCTURAL_NODES 2 DISABLE` (86), the working directory,
post-processing script and execution command (89 to 95),
`SET_AEROELASTIC_ITERATIONS 50` (98) and `EXECUTE_AEROELASTIC_ANALYSIS` (101),
the last line. With that order the solver mapped all 1052 vertices and morphed
the wing, so the order works on a wing.

## Found and fixed before release

The first confirmation of this route, on `0331fe91`, found four package
defects; each was fixed on `feat/0-30-storage-sync` before this run:

- a coupled row with the default exports did not build (the sections were
  updated twice, the second time after an export), so that run needed its
  section-type exports turned off: **69cffa41** (this run uses the defaults);
- a clocked wheel's log was refused by the residual reader: **c46bee0e**
  (RPT-091);
- a clocked wheel's sections were not cut over the blade: **24edb353**
  (RPT-091);
- a `qsteady_rotor` point had no rotor table: **4113de02** (RPT-090, RPT-091).

The solver-side numbers of this point are identical to every printed digit to
the first confirmation's.

## What remains an observation

- The coupled export's `CDo` is 0 where the rigid one is 0.0093534.
- `tip_flap_m` in `fsi_convergence_log.csv` is unsigned; a wing bending down
  reads +1.27e-2 there.
- One point, one material, alpha 5 deg; a free half wing, not a half wing on a
  symmetry plane (the route refuses symmetry copies).
- The XZ-moment sign in magnitude (check (a)).
