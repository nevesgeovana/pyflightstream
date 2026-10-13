# RPT-169 - 6DOF initial angular velocity: input unit (2026-10-13)

## Scope and verdicts

Planning node PFS-2081.79 (lens finding VV-002 on FR-461 R2). `SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY` takes its three
values in a unit the manual does not name; pyflightstream converts a stated deg/s to rad/s (`cases/workflows/_sixdof.py`,
line 150). The probe sets the raw value 1.0 and reads the attitude angle after a known time.

| Build | Unit of the command's value | pyflightstream conversion |
|---|---|---|
| 26.124 | radians per second | correct (deg/s to rad/s) |
| 26.125 | radians per second | correct (deg/s to rad/s) |

## What was set

Script `gapprobes-run/p4_rate_unit.py` (scratch, outside the repository), one body of the wing stl of P4-04m, frame
`PYFS_GAP_CG` at x = 0.25 m, mass 100 kg, inertia IXX = IYY = IZZ = 1000 kg m2, gravity 0, freedoms: Q enabled, U V W P R
disabled (rotation about Y only), `SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY 1 0.0 1.0 0.0`, unsteady march of 20 steps
with `DELTA_TIME 0.02`, freestream 1 m/s (the aerodynamic moment is negligible against an inertia of 1000), the
trajectory exported after the march (RPT-167). Hidden solver, one at a time, launched outside the sandbox with the
licence environment.

## What was read

Trajectory columns x, y, z, u, v, w, p, q, r, phi, theta, psi, Fx, Fy, Fz, Mx, My, Mz (20 rows, 9870 bytes on both
builds). Rotation about Y moves theta only.

| Quantity | 26.124 | 26.125 |
|---|---|---|
| q, row 1 | 0.9999773 | 0.9999773 |
| q, row 20 | 0.99949448 | 0.99949466 |
| theta, row 1 | 2.29181817 | 2.29181818 |
| theta, row 2 | 3.43769453 | 3.43769455 |
| theta, row 20 | 24.05861298 | 24.05861512 |
| step increment of theta, mean | 1.14562 | 1.14562 |

## The arithmetic

The step is 0.02 s and the rate stays 1.0 (q drifts by 5e-4 over the march). The export's angle moves 1.1456 per step:

- 1 rad/s over 0.02 s is 0.02 rad = 1.1459 degrees. Measured 1.1456 (mean, the rate falls by 0.05 %). Match.
- 1 deg/s over 0.02 s would be 0.02 degrees: 57 times smaller than measured. Excluded.
- 1 rpm (6 deg/s) over 0.02 s would be 0.12 degrees: 9.5 times smaller. Excluded.

Total: theta 24.0586 after 21 steps of 0.02 s (row 1 already stands at 2 steps: 2.2918 deg = 0.04 rad), i.e. 0.4199 rad
= 21 x 0.02 x 1.0 rad/s x 0.9995. Further, the exported rate column q reads 1.0 where it was set to 1.0, so the rate
column is in rad/s, and the exported angles are in degrees (theta/q relation of 57.2958 deg per rad).

## Conclusion per build

- **26.124**: the value 1.0 is 1 rad/s. The conversion deg/s to rad/s in the package is right.
- **26.125**: the value 1.0 is 1 rad/s. Same.
- Side finding: in `trajectory.txt` the rates p, q, r are in rad/s and phi, theta, psi in degrees. Column units of
  RPT-167 ("unsettled") are settled for these six by this probe.
- Not probed: the P4-02 control of the battery (10 per second about X, trajectory exported before the march) is
  superseded by this probe; a calibration case with a known external pulse (`CREATE_NEW_6DOF_EXTERNAL_FORCE`) was
  attempted and the solver refused the line (`Error in script ... at line 41: 'CREATE_NEW_6DOF_EXTERNAL_FORCE 1 1.0 0.0
  0.0 0.0 0.1 0.0 0.0 500.0'`, `out-rpt169/26.124/C/FlightStreamLog.txt`) in the form used here (it is emitted by the
  P4-03 battery in the pitch-only epilogue; the grammar mismatch is not investigated here). The conclusion does not
  need it: the step increment fixes the unit by itself.

## Database route

`commands/motion_definitions.yaml`, `SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY`: the `notes` text now states the measured
unit (radians per second, both builds, RPT-169). No version row changed; the status rows stay as RPT-166 left them.

## Evidence envelope

| File | SHA-256 |
|---|---|
| gapprobes-run/out-rpt169/26.124/R/trajectory.txt | c4c79a43c45c5690a4c1fe646d2999bd40415391af2b886dbcc5efb2fc5b1e81 |
| gapprobes-run/out-rpt169/26.124/R/probe_script.txt | 87d13fcd52b7e870c8bdec206dca33caf11dd40c36b402255ad55aa9d1c7cf86 |
| gapprobes-run/out-rpt169/26.125/R/trajectory.txt | bcdde8dd3d547af2dc3d288250dec1456f15e89ad71d06837417dffede61f61f |
| gapprobes-run/out-rpt169/26.125/R/probe_script.txt | 0d38c07df2371f8cd93aa65745b2af901fdc645db69c85095dff7d038e578d88 |

No commit was made.
