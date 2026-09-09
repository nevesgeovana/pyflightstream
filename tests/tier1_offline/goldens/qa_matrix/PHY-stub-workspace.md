# Physics report: FlightStream 26.120 ({date})

Tier 3 physics regression evidence produced by `pyfs-qa physics`
(SAD Section 11): the physics cases as rows of a run matrix in a
campaign workspace, built by the package's workflows over the
workspace's synthetic library, their loads reduced to the case
metrics and compared against stored references inside WARN and
FAIL bands. References change only through
`pyfs-qa update-reference`, which records a reason; no research
geometry is involved.

## Setup

| Item | Value |
|---|---|
| Source | matriz_physics.fs in workspace ws |
| Executable | FlightStream_26120.exe (sha256 not recorded, local, never committed) |
| Executor | StubSolver, `stub_solver.py POLAR-5001_M09AL+000BE+000.txt` (as run; mechanism SRC-003 pp.279-280; argument spelling RPT-023) |
| Package | pyflightstream {package_version} |
| Solver identity | Flightstream version 26.1, build 7012026 |

## Summary

30 pass, 0 warn, 0 fail, 0 without reference.

## PHY-01: NACA wing polar (synthetic NACA 0012, AR 8)

row 5001 of matriz_physics.fs, steady workflow over 12_WING_PHY.fsm under SYMMETRY NONE

| point | alpha (deg) | CL | CDi | iterations | converged |
|---|---|---|---|---|---|
| sim_5001/a+00.0 | +0.0 | 0.00000 | 0.00000 | 312 | yes |
| sim_5001/a+02.0 | +2.0 | 0.16850 | 0.00122 | 312 | yes |
| sim_5001/a+04.0 | +4.0 | 0.33700 | 0.00490 | 312 | yes |
| sim_5001/a+06.0 | +6.0 | 0.50550 | 0.01103 | 312 | yes |

| Metric | Measured | Reference | Bands (warn/fail) | Verdict |
|---|---|---|---|---|
| CL_a0 | 0.00000 | -0.00040 | 0.005/0.02 (abs) | pass |
| CL_a2 | 0.16850 | 0.16840 | 0.02/0.05 (rel) | pass |
| CL_a4 | 0.33700 | 0.33700 | 0.02/0.05 (rel) | pass |
| CL_a6 | 0.50550 | 0.50500 | 0.02/0.05 (rel) | pass |
| CL_slope_per_rad | 4.82717 | 4.82660 | 0.02/0.05 (rel) | pass |
| CDi_a4 | 0.00490 | 0.00490 | 0.05/0.15 (rel) | pass |

## PHY-02: Half versus full symmetry equivalence (NACA 0012, AR 8)

row 5002 of matriz_physics.fs, steady workflow over 12_WING_PHY.fsm under SYMMETRY NONE; row 5003 of matriz_physics.fs, steady workflow over 13_HALFWING_PHY.fsm under SYMMETRY MIRROR

| point | alpha (deg) | CL | CDi | iterations | converged |
|---|---|---|---|---|---|
| sim_5002/a+04.0 | +4.0 | 0.33700 | 0.00490 | 312 | yes |
| sim_5003/a+04.0 | +4.0 | 0.33840 | 0.00490 | 312 | yes |

| Metric | Measured | Reference | Bands (warn/fail) | Verdict |
|---|---|---|---|---|
| CL_full_a4 | 0.33700 | 0.33700 | 0.02/0.05 (rel) | pass |
| CL_half_a4 | 0.33840 | 0.33850 | 0.02/0.05 (rel) | pass |
| delta_CL_a4 | 0.00140 | 0.00150 | 0.005/0.02 (abs) | pass |
| delta_CDi_a4 | 0.00000 | 0.00000 | 0.0005/0.002 (abs) | pass |

## PHY-05: Rigid unsteady periodic propeller (generic BladeSpec blade)

row 5005 of matriz_physics.fs, unsteady_rotor workflow over 31_BLADE_PHY.fsm under SYMMETRY PERIODIC

| point | alpha (deg) | CL | CDi | iterations | converged |
|---|---|---|---|---|---|
| sim_5005/a+00.0_b+00.0 | +0.0 | -0.00010 | -0.04517 | 500 | no |

| Metric | Measured | Reference | Bands (warn/fail) | Verdict |
|---|---|---|---|---|
| CL | -0.00010 | -0.00010 | 0.002/0.01 (abs) | pass |
| CDi | -0.04517 | -0.04517 | 0.01/0.03 (rel) | pass |
| CDo | 0.00070 | 0.00070 | 0.0005/0.002 (abs) | pass |
| CMy | 0.02864 | 0.02864 | 0.01/0.03 (rel) | pass |

## PHY-06: Steady versus unsteady polar equivalence (NACA 0012, AR 8)

row 5006 of matriz_physics.fs, unsteady workflow over 12_WING_PHY.fsm under SYMMETRY NONE; row 5001 of matriz_physics.fs, steady workflow over 12_WING_PHY.fsm under SYMMETRY NONE

| point | alpha (deg) | CL | CDi | iterations | converged |
|---|---|---|---|---|---|
| sim_5001/a+00.0 | +0.0 | 0.00000 | 0.00000 | 312 | yes |
| sim_5001/a+02.0 | +2.0 | 0.16850 | 0.00122 | 312 | yes |
| sim_5001/a+04.0 | +4.0 | 0.33700 | 0.00490 | 312 | yes |
| sim_5001/a+06.0 | +6.0 | 0.50550 | 0.01103 | 312 | yes |
| sim_5006/a+00.0 | +0.0 | 0.00000 | 0.00000 | 500 | no |
| sim_5006/a+02.0 | +2.0 | 0.16850 | 0.00122 | 500 | no |
| sim_5006/a+04.0 | +4.0 | 0.33700 | 0.00490 | 500 | no |
| sim_5006/a+06.0 | +6.0 | 0.50550 | 0.01103 | 500 | no |

| Metric | Measured | Reference | Bands (warn/fail) | Verdict |
|---|---|---|---|---|
| delta_CL_a0 | 0.00000 | 0.00040 | 0.005/0.02 (abs) | pass |
| delta_CD_a0 | 0.00000 | -0.00010 | 0.001/0.004 (abs) | pass |
| delta_CMy_a0 | 0.00000 | -0.00010 | 0.005/0.02 (abs) | pass |
| delta_CL_a2 | 0.00000 | 0.00130 | 0.005/0.02 (abs) | pass |
| delta_CD_a2 | 0.00000 | -0.00010 | 0.001/0.004 (abs) | pass |
| delta_CMy_a2 | 0.00000 | -0.00020 | 0.005/0.02 (abs) | pass |
| delta_CL_a4 | 0.00000 | 0.00220 | 0.005/0.02 (abs) | pass |
| delta_CD_a4 | 0.00000 | -0.00040 | 0.001/0.004 (abs) | pass |
| delta_CMy_a4 | 0.00000 | -0.00020 | 0.005/0.02 (abs) | pass |
| delta_CL_a6 | 0.00000 | 0.00300 | 0.005/0.02 (abs) | pass |
| delta_CD_a6 | 0.00000 | -0.00050 | 0.001/0.004 (abs) | pass |
| delta_CMy_a6 | 0.00000 | -0.00040 | 0.005/0.02 (abs) | pass |
| CL_slope_steady_per_rad | 4.82717 | 4.82660 | 0.02/0.05 (rel) | pass |
| CMy_slope_steady_per_rad | -1.21467 | -1.21496 | 0.02/0.05 (rel) | pass |
| CL_slope_unsteady_per_rad | 4.82717 | 4.85152 | 0.02/0.05 (rel) | pass |
| CMy_slope_unsteady_per_rad | -1.21467 | -1.21754 | 0.02/0.05 (rel) | pass |
