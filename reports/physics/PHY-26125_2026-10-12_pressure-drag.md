# Physics report: FlightStream 26.125 (2026-10-12)

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
| Source | matriz_physics.fs in workspace phys-ws |
| Executable | Flightstream_26125.exe (sha256 withheld; build 10052026, local, never committed) |
| Executor | LocalExecutor, `-script` (as run; mechanism SRC-003 pp.279-280; argument spelling RPT-023) |
| Package | pyflightstream 0.39.0 |
| Solver identity | Flightstream version 2612, build 10052026 |

## Summary

0 pass, 0 warn, 0 fail, 4 without reference.

## PHY-01: NACA wing polar (synthetic NACA 0012, AR 8)

Case aborted: row 5001 has 3 point(s) the run did not finish: phys-ws/sim_5001/V0300RHO12250AL+020: FAILED_INCOMPLETE_OUTPUT (V0300RHO12250AL+020: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+020_log.txt holds 2, so which solve is the point's cannot be told; V0300RHO12250AL+040: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+040_log.txt holds 3, so which solve is the point's cannot be told; V0300RHO12250AL+060: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+060_log.txt holds 4, so which solve is the point's cannot be told); phys-ws/sim_5001/V0300RHO12250AL+040: FAILED_INCOMPLETE_OUTPUT (V0300RHO12250AL+020: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+020_log.txt holds 2, so which solve is the point's cannot be told; V0300RHO12250AL+040: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+040_log.txt holds 3, so which solve is the point's cannot be told; V0300RHO12250AL+060: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+060_log.txt holds 4, so which solve is the point's cannot be told); phys-ws/sim_5001/V0300RHO12250AL+060: FAILED_INCOMPLETE_OUTPUT (V0300RHO12250AL+020: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+020_log.txt holds 2, so which solve is the point's cannot be told; V0300RHO12250AL+040: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+040_log.txt holds 3, so which solve is the point's cannot be told; V0300RHO12250AL+060: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+060_log.txt holds 4, so which solve is the point's cannot be told)

## PHY-02: Half versus full symmetry equivalence (NACA 0012, AR 8)

row 5002 of matriz_physics.fs, steady workflow over 12_WING_PHY.fsm under SYMMETRY NONE; row 5003 of matriz_physics.fs, steady workflow over 13_HALFWING_PHY.fsm under SYMMETRY MIRROR

Minimum Cp clip for sim_5002/V0300RHO12250AL+040: -100.
Minimum Cp clip for sim_5003/V0300RHO12250AL+040: -100.

| point | alpha (deg) | CL | CDp | iterations | converged |
|---|---|---|---|---|---|
| sim_5002/V0300RHO12250AL+040 | +4.0 | 0.33850 | 0.00490 | 58 | yes |
| sim_5003/V0300RHO12250AL+040 | +4.0 | 0.34040 | 0.00500 | 64 | yes |

| Metric | Measured | Reference | Bands (warn/fail) | Verdict |
|---|---|---|---|---|
| CL_full_a4 | 0.33850 | NA | NA | no_reference |
| CL_half_a4 | 0.34040 | NA | NA | no_reference |
| delta_CL_a4 | 0.00190 | NA | NA | no_reference |
| delta_CDp_a4 | 0.00010 | NA | NA | no_reference |

## PHY-06: Steady versus unsteady polar equivalence (NACA 0012, AR 8)

Case aborted: row 5001 has 3 point(s) the run did not finish: phys-ws/sim_5001/V0300RHO12250AL+020: FAILED_INCOMPLETE_OUTPUT (V0300RHO12250AL+020: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+020_log.txt holds 2, so which solve is the point's cannot be told; V0300RHO12250AL+040: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+040_log.txt holds 3, so which solve is the point's cannot be told; V0300RHO12250AL+060: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+060_log.txt holds 4, so which solve is the point's cannot be told); phys-ws/sim_5001/V0300RHO12250AL+040: FAILED_INCOMPLETE_OUTPUT (V0300RHO12250AL+020: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+020_log.txt holds 2, so which solve is the point's cannot be told; V0300RHO12250AL+040: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+040_log.txt holds 3, so which solve is the point's cannot be told; V0300RHO12250AL+060: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+060_log.txt holds 4, so which solve is the point's cannot be told); phys-ws/sim_5001/V0300RHO12250AL+060: FAILED_INCOMPLETE_OUTPUT (V0300RHO12250AL+020: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+020_log.txt holds 2, so which solve is the point's cannot be told; V0300RHO12250AL+040: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+040_log.txt holds 3, so which solve is the point's cannot be told; V0300RHO12250AL+060: a collected solver log holds another number of solves than this point solved (1): P5001-V0300RHO12250AL+060_log.txt holds 4, so which solve is the point's cannot be told)
