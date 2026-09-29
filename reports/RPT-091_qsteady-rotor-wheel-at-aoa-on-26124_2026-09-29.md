# RPT-091 - The qsteady_rotor wheel at an AoA, confirmed on 26.124 (2026-09-29)

A short licensed confirmation of the 0.30.0 `qsteady_rotor` workflow on a whole
**wheel** at an angle of attack (**AoA** 5 deg), no FSI, run through the
package's own path (`pyfs-matrix plan`, `pyfs-matrix run`, the post that `run`
performs) on **FlightStream 26.124, build 8172026**, executable SHA-256
`68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65` (measured
from the executable that ran, and recorded as `fs_exe_sha256` in the run
records). Package at commit `0331fe91` (0.30.0.dev2, `package_dirty: false`).
One solver instance at a time, hidden, far field 5 layers.

## What was run

A six-blade research propeller (its geometry is not published): six blades, one
OBJ group each (5616 vertices), no spinner, no nacelle, no symmetry. Shaft
along X through the origin. Mach 0.1441, Re 4.38 million on the reference chord,
alpha 5 deg, 473.17227304307556 rev/min (49.036 m/s, 0.63261 kg/m3 as the run
resolves them), steady solver, convergence 1e-5, `PASSAGE_POSITIONS: 2`, the
count RPT-089 section 4 measured as converging thrust and torque to about
0.2 %. The run solved the clockings 0 and 30 deg inside one 60 deg blade
passage (`P9101-..._qsteady.json` in the datapoint folder; clocking 0 carries
the point's full exports, clocking 30 deg its loads export
`P9101-..._qs01.txt`).

| row | run id | trailing edges | status | wall time (record `wall_time_s`) |
|---|---|---|---|---|
| 9101 | `pfs0300-l1-ws/sim_9101/M144RE438AL+050BE+000RPM00473` | points file (the file route) | **FAILED_INCOMPLETE_OUTPUT** (finding F1) | 12.6 s |
| 9102 | `pfs0300-l1-ws/sim_9102/M144RE438AL+050BE+000RPM00473` | the solver's detection | CONVERGED | 11.7 s |

Row 9102 is the same mesh, byte for byte, with the trailing edges marked by
detection instead of the points file: the control that isolates F1. Each
`pyfs-matrix run` took 13 to 14 s. Each clocking converged in 61 iterations
(both loads exports of 9101).

## The plan

`pyfs-matrix plan` printed the four validity values of the wheel point and its
warning (`post/l1_wheel/plan.json`, the point's `qsteady_validity`, chord read
off the mesh at 20 stations):

```
[warning] quasi-steady rotor: the 1P reduced frequency k = Omega c / (2 V_rel) exceeds 0.1 on
part of the blade at 1 point(s): POL 9101 point M144RE438AL+050BE+000RPM00473: k > 0.1 over
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

## The per-point validity file

The post wrote `P9101-M144RE438AL+050BE+000RPM00473_qsteady_validity.json` into
the point's datapoint folder, beside the run's record, with the chord read off
the sectional loads export (`K_1P_SOURCE` `sections`) and the plan's values
beside it:

| value | from the sections (post) | from the mesh (plan) |
|---|---|---|
| K_1P_MIN | 0.0 | 0.0421 |
| K_1P_MAX | 0.1308 | 0.1315 |
| K_1P_MEAN | 0.0923 | 0.0898 |
| SPAN_PCT_K_GT_0_05 | 94.8 % | 97.4 % |
| SPAN_PCT_K_GT_0_1 | 37.9 % | 28.9 % |
| THRUST_PCT_K_GT_0_1 | 15.1 % | not computed at plan |
| TORQUE_PCT_K_GT_0_1 | 13.4 % | not computed at plan |

Row 9102 gives the same k values and 15.13 % / 13.40 % for the shares
(`polars/P9102-ROTOR_qs_avg.csv`). The two sets differ because of finding F2.

## The averaged six components

The mean of the two clockings (`polars/P9101-ROTOR_qs_avg.csv`,
`polars/P9102-ROTOR_qs_avg.csv`; rotor loads in N and N m about the hub, in
the loads frame's axes), against the earlier licensed quasi-steady study of the
same propeller at the same point with the same two clockings (RPT-089 section
4, k = 2, trailing edges by detection):

| component | 9101 (points file) | 9102 (detection) | RPT-089, k = 2 | 9102 against RPT-089 |
|---|---|---|---|---|
| Fx (N) | -2300.04 | -2255.30 | -2206.12 | +2.2 % |
| Fy (N) | -23.90 | -24.32 | -23.81 | +2.1 % |
| Fz (N) | +267.27 | +263.59 | +257.17 | +2.5 % |
| Mx (N m) | -2547.92 | -2488.18 | -2434.21 | +2.2 % |
| My (N m) | +40.96 | +41.43 | +40.64 | +1.9 % |
| Mz (N m) | -364.10 | -356.62 | -346.05 | +3.1 % |

(percentages in magnitude). Every sign agrees with RPT-089, and the in-plane
pattern RPT-089 measured (Fy and My small, Fz and Mz of the order of 10 % of
the thrust and torque) is reproduced. The package's wheel sits 2 to 3 % above
RPT-089 in magnitude with detection, and 3.9 to 5.2 % in Fx, Fz, Mx and Mz with the points file. The
clocking spread inside each run is small (9101: Fx -2305.33 at 0 deg and
-2294.75 at 30 deg, `polars/P9101-ROTOR_qs_positions.csv`). What makes the
remaining 2 to 3 % (the package's own mesh of the six blades against the
study's, its wake-termination detection after a second initialisation, or its
exports) was not separated by these runs.

## Findings

- **F1, a defect: the wheel's solver log holds every clocking, and the
  package then cannot read it.** The exported log of 9101 carries three
  initialisations (`Solution cleared. Initialization removed.` twice) and the
  residual tables of both clockings, whose iteration counter goes from 61 back
  to 1. `results.parse_residual_history` refuses such a table ("the residual
  table's iteration counter goes from 61 to 1, so it does not increase",
  `results/__init__.py:1382`), so the assessor reads no log (`log_file_used`
  and `residual` are null in both records), and on the points-file route the
  trailing-edge verdict (`run/_wake_edge_verdict.py:384-391`,
  `wake_edge_import_verdict`, reached from `collected_solver_log` at `:155`)
  records the point FAILED_INCOMPLETE_OUTPUT: "the script imported 150
  trailing-edge points and no solver log was read". The log itself states
  "150 trailing edges imported", the count the verdict wants. With detection
  (9102) nothing asks for the count and the point is CONVERGED, with its
  residual still unread. The documentation's sentence "clocking 0 is solved
  last, with the point's full set of exports, so its loads export and its log
  are of one solve" (`docs/workspace-and-workflows.md:3235`) does not hold for
  the log. The post wrote every product of 9101 anyway and its `post.log`
  warns about the status, as invariant 12 requires.
- **F2: the sections of a clocked wheel do not cover the blade.** The
  sectional loads export of clocking 0 (9101 and 9102) places its 30 cuts at
  0.347 to 1.586 m from the shaft, while the blade spans 0.41 to 1.824 m (the
  sector of RPT-090 cuts the same blade at 0.434 m upward). The two innermost
  cuts are empty (chord 0, so `K_1P_MIN` is 0.0) and the outer 0.24 m of the
  blade has no cut, so the post's span fractions and thrust and torque shares
  above k = 0.1 are computed over the wrong stations. The distribution appears
  to keep an extent taken with the blades clocked (30 deg); that cause is an
  inference, not measured.
- **F3: no rotor table** for either point ("its record states no speed for
  'ROTOR'"), as in RPT-090.

## What this does not establish

- One point, two clockings; the in-plane components converge only with more
  clockings (RPT-089 section 4 recommends 6 or more for them).
- The quasi-steady wheel's agreement with an unsteady rotor is RPT-089's, not
  re-measured here.
