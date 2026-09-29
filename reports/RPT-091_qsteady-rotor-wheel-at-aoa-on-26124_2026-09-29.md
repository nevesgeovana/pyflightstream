# RPT-091 - The qsteady_rotor wheel at an AoA, confirmed on 26.124 (2026-09-29)

A short licensed confirmation of the 0.30.0 `qsteady_rotor` workflow on a whole
**wheel** at an angle of attack (**AoA** 5 deg), no FSI, run through the
package's own path (`pyfs-matrix plan`, `pyfs-matrix run`, the post that `run`
performs) on **FlightStream 26.124, build 8172026**, executable SHA-256
`68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65` (measured
from the executable that ran, and recorded as `fs_exe_sha256` in the run
record). The package is the tree of `feat/0-30-storage-sync` at `4f12aede`,
which carries the four fixes listed at the end (the record names `c89c603d`,
this report branch on top of it, whose `src/` is identical;
`package_dirty: false`). One solver instance at a time, hidden, far field 5
layers. **The row uses the pproc's default exports.**

## What was run

A six-blade research propeller (its geometry is not published): six blades, one
OBJ group each (5616 vertices), no spinner, no nacelle, no symmetry, trailing
edges from the mesh's points file (the file route, 150 points; the log states
"150 trailing edges imported"). Shaft along X through the origin. Mach 0.1441,
Re 4.38 million on the reference chord, alpha 5 deg, 473.17227304307556 rev/min
(49.036 m/s, 0.63261 kg/m3 as the run resolves them), steady solver,
convergence 1e-5, `PASSAGE_POSITIONS: 2`, the count RPT-089 section 4
measured as converging thrust and torque to about 0.2 %. The run solved the
clockings 0 and 30 deg inside one 60 deg blade passage (`P9111-..._qsteady.json`
in the datapoint folder; clocking 0 carries the point's full exports,
clocking 30 deg its loads export `P9111-..._qs01.txt`).

| run id | status | wall time (record `wall_time_s`) |
|---|---|---|
| `pfs0300-l1-ws/sim_9111/M144RE438AL+050BE+000RPM00473` | **CONVERGED** | 12.4 s |

The whole `pyfs-matrix run` took 13 s. The record now reads the solver log
(`log_file_used` `P9111-..._log.txt`, final residual 1.23e-6) and carries one
verdict per clocking (`clocking_verdicts`):

| clocking | status | iterations | residual |
|---|---|---|---|
| 30 deg (index 1, solved first) | CONVERGED | 61 | 1.157e-6 |
| 0 deg (index 0, solved last) | CONVERGED | 61 | 1.230e-6 |

The post wrote every product and recorded no skip
(`post/l2_wheel/products.json`).

## The plan

`pyfs-matrix plan` printed the four validity values of the wheel point and its
warning (`post/l2_wheel/plan.json`, the point's `qsteady_validity`, chord read
off the mesh at 20 stations):

```
[warning] quasi-steady rotor: the 1P reduced frequency k = Omega c / (2 V_rel) exceeds 0.1 on
part of the blade at 1 point(s): POL 9111 point M144RE438AL+050BE+000RPM00473: k > 0.1 over
28.9 % of the span, k min 0.0421, k max 0.1315, k mean 0.0898. There the unsteady wake lags
the once-per-revolution load and the quasi-steady load is an estimate. Nothing is refused;
every product of these points carries the values.
```

| per cent of the span with k > 0.1 | k min | k max | k mean (span-weighted) |
|---|---|---|---|
| 28.9 % | 0.0421 | 0.1315 | 0.0898 |

`pyfs-matrix plan --inflow-fft` on the same matrix printed no inflow-harmonics
line: its output equals the plan without the option apart from the banner, and
the point's record carries no `inflow_fft` entry. The option reads a custom
inflow (`FREESTREAM`), and this row states an angle of attack, so there is
nothing for it to read; that is the documented scope, not a refusal.

## The sections and the per-point validity file

The 30 section cuts of the point (`P9111-..._sloads.txt`, the sections table
`post/l2_wheel/sections/P9111-..._sections.csv`) run from 0.4336 m (chord
0.2823 m) to 1.8000 m (chord 0.1419 m) from the shaft: first and last cut
inside the blade's 0.41 to 1.824 m, and no empty cut.

The post wrote `P9111-M144RE438AL+050BE+000RPM00473_qsteady_validity.json` into
the point's datapoint folder, beside the run's record, with the chord read off
the sectional loads export (`K_1P_SOURCE` `sections`) and the plan's values
beside it:

| value | from the sections (post) | from the mesh (plan) |
|---|---|---|
| K_1P_MIN | 0.0345 | 0.0421 |
| K_1P_MAX | 0.1306 | 0.1315 |
| K_1P_MEAN | 0.0895 | 0.0898 |
| SPAN_PCT_K_GT_0_05 | 91.4 % | 97.4 % |
| SPAN_PCT_K_GT_0_1 | 32.8 % | 28.9 % |
| THRUST_PCT_K_GT_0_1 | 11.7 % | not computed at plan |
| TORQUE_PCT_K_GT_0_1 | 10.3 % | not computed at plan |

The same values are in the clockings and average tables and in the point's
super-file rows. `THRUST_PCT_K_GT_0_1` and `TORQUE_PCT_K_GT_0_1` read the
export's `Fx` as the force along the shaft and `Fz` as the in-plane force;
`docs/post-processing-definitions.md` states that this axis reading is not
yet measured on a licensed run, and this run does not measure it either. The post's minimum is at the tip cut (1.8 m, chord
0.1419 m), the plan's at its outermost band; the two read the chord in
different places, and the mean agrees to 0.3 %.

## The averaged six components and the rotor table

The mean of the two clockings (`post/l2_wheel/polars/P9111-ROTOR_qs_avg.csv`;
rotor loads in N and N m about the hub, in the loads frame's axes), against
the earlier licensed quasi-steady study of the same propeller at the same point
with the same two clockings (RPT-089 section 4, k = 2, trailing edges by
detection):

| component | 9111 (points file) | RPT-089, k = 2 | 9111 against RPT-089 |
|---|---|---|---|
| Fx (N) | -2300.04 | -2206.12 | +4.3 % |
| Fy (N) | -23.90 | -23.81 | +0.4 % |
| Fz (N) | +267.27 | +257.17 | +3.9 % |
| Mx (N m) | -2547.92 | -2434.21 | +4.7 % |
| My (N m) | +40.96 | +40.64 | +0.8 % |
| Mz (N m) | -364.10 | -346.05 | +5.2 % |

(percentages in magnitude). Every sign agrees with RPT-089, and the in-plane
pattern RPT-089 measured (Fy and My small, Fz and Mz of the order of 10 % of
the thrust and torque) is reproduced. The clocking spread is small (Fx
-2305.33 N at 0 deg and -2294.75 N at 30 deg,
`post/l2_wheel/polars/P9111-ROTOR_qs_positions.csv`). A control on the earlier
code (`pfs0300-l1-ws/sim_9102/M144RE438AL+050BE+000RPM00473`, the same OBJ
with the trailing edges by detection, CONVERGED, 11.7 s) gave Fx -2255.30 N,
Fy -24.32 N, Fz +263.59 N, Mx -2488.18 N m, My +41.43 N m, Mz -356.62 N m,
2 to 3 % above RPT-089. That control ran on `0331fe91`, the code of the first
confirmation's points-file run `sim_9101`, so the trailing-edge route is
compared on one code: 9101 against 9102, about half of the gap to RPT-089.
24edb353 changed the emitted script (the section distribution declared at
clocking 0, the 30 deg rotation moved after it and after the wake-termination
detection, and one more initialisation after the rotation), and the
integrated loads of 9111 are equal to those of 9101 to every printed digit:
both loads exports (clocking 0 and 30 deg) equal in every coefficient to their
seven printed decimals, and the averaged six components to their five
(measured, fields `first_confirmation.loads_qs_avg.sim_9101` and
`averaged_six_components.sim_9111`). The detection route was not re-run on the
fixed code. What makes the remaining 2 to 3 % was not separated by these runs.

The rotor table (`post/l2_wheel/polars/P9111-ROTOR_rotor.csv`) is written:

| RPM_ROTOR | J_ROTOR | CT_ROTOR | CQ_ROTOR | CP_ROTOR | ETA_ROTOR | ETAW_ROTOR |
|---|---|---|---|---|---|---|
| 473.17227 | 1.70001 | -0.32740 | -0.09911 | -0.62272 | 0.89379 | 0.88126 |

(CT and CQ negative by the shaft sense of the loads frame; ETAW the
wind-axis efficiency, which at 5 deg differs from ETA.)

## Found and fixed before release

The first confirmation of this row, on `0331fe91`, was recorded
FAILED_INCOMPLETE_OUTPUT and found four package defects; each was fixed on
`feat/0-30-storage-sync` before this run:

- a coupled row with the default exports did not build: **69cffa41**
  (RPT-090, RPT-092);
- the wheel's exported log holds every clocking and the residual reader
  refused it, so the trailing-edge verdict read no log and failed this row:
  **c46bee0e** (the log is now read solve by solve, one verdict per clocking,
  above);
- the wheel's 30 cuts ran from 0.347 to 1.586 m, two of them empty and the
  outer 0.24 m of the blade uncut: **24edb353** (the wheel is cut at clocking
  0 over the blade's radial span, above);
- a `qsteady_rotor` point had no rotor table: **4113de02** (above).

## First confirmation (draft, 0331fe91, not released)

Dated 2026-09-29. The first confirmation ran on `0331fe91` and was committed
as a draft of this report in `c89c603d`; it was never pushed and never on
main, and git history keeps that draft. Its values, from its own run files:

| run id (code `0331fe91`) | status | iterations per clocking | wall time |
|---|---|---|---|
| `pfs0300-l1-ws/sim_9101/M144RE438AL+050BE+000RPM00473` (points file) | FAILED_INCOMPLETE_OUTPUT | 61 | 12.6 s |
| `pfs0300-l1-ws/sim_9102/M144RE438AL+050BE+000RPM00473` (detection) | CONVERGED | 61 | 11.7 s |

- Loads (quasi-steady average, 9101): Fx -2300.04 N, Fy -23.90 N,
  Fz +267.27 N, Mx -2547.92 N m, My +40.96 N m, Mz -364.10 N m; the same as
  9111's above.
- Residuals: neither record read the log (`log_file_used` null, residual
  null); the residual reader refused the two-clocking log.
- Sections: 30 cuts from 0.347 to 1.586 m, two of them empty (chord 0), the
  outer 0.238 m of the blade uncut; so `K_1P_MIN` 0, `K_1P_MAX` 0.1308,
  `K_1P_MEAN` 0.0923, 37.9 % of the span above 0.1, `THRUST_PCT_K_GT_0_1`
  15.1 % and `TORQUE_PCT_K_GT_0_1` 13.4 %.
- No FSI on this row, so no mapping and no tip deflection.

What changed: the four fixes listed above. The loads are equal to the
re-run's; the sections, and every validity value read from them, changed.

## What this does not establish

- One point, two clockings; the in-plane components converge only with more
  clockings (RPT-089 section 4 recommends 6 or more for them).
- The quasi-steady wheel's agreement with an unsteady rotor is RPT-089's, not
  re-measured here.
