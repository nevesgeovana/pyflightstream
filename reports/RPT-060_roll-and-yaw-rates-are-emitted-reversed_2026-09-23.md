# RPT-060: the roll and yaw rates are emitted reversed (2026-09-23)

**Date:** 2026-09-23
**Found by:** the licensed probe T11 of the 0.27.0 work, run to measure what RPT-052 left unmeasured
**Status:** REGISTERED for 0.27.0 (G13 fixes the sign per axis)
**Affects:** every matrix row that states `roll_rate` or `yaw_rate`, since 0.21.0; `pitch_rate` is right

## What this settles

From 0.21.0 a matrix row states one body rate in deg/s with flight-mechanics signs,
and the script writes `SET_FREESTREAM ROTATION <frame> <axis> <rev/min>` about the
moment reference point, with one sign for all three axes
(`cases/workflows.py`, `FREESTREAM_ROTATION_SIGN = 1.0`). RPT-052 measured that sign
for `pitch_rate` only and said the other two rest "on an argument and not a run".
This is the run. **For `roll_rate` and `yaw_rate` the emitted rotation is the
opposite of the rate the row states.** `pitch_rate` stays right.

## The prediction, written before the run

The export frame is x aft, y right, z up, and the package's body axes are that
frame turned half a turn about y (`post/axes.py`, `EXPORT_TO_BODY`), so the body
rates are p = -omega_x, q = +omega_y, r = -omega_z. RPT-052 found +rpm about y is
nose-up. If the solver's positive sense is the same right-hand rotation on x and z,
one sign of +1 is right for pitch and reversed for roll and yaw. The prediction was
registered before the solver ran.

## What was run

One probe workspace, seven steady points, ONE THING MOVED per point: the rate.

    geometry    30_WB, the same half wing-body mesh as RPT-052 (sha256 3a5f174c...)
    build       FlightStream 26.124 (build 8172026, executable sha256 68e64e66...)
    package     0.27.0.dev0 at b705329
    condition   MACH 0.2, REmi 11.7716754, alpha 2 deg, beta 0
    setup       RPT-052's preset plus farfield_layers = 5; SYMMETRY NONE
    reference   SREF 50, CREF 2.526, BREF 20, moment point x = 9.152;
                body axes roll = X, pitch = Y, yaw = Z
    points      control 0; roll_rate +4, +40, -40; yaw_rate +4, +40, -40 (deg/s)

Every row states both keys (`roll_rate`, `yaw_rate`), so each script differs from
the control only in its free-stream line and its names. All seven CONVERGED in
173 to 187 iterations, 9 to 10 s wall each. A fresh control was solved rather than
reusing RPT-052's: that one ran on an older package and without the far-field line.

## What came back

Increments over the control, group 1 the airframe, group 2 the wing (the meshed
y < 0 half):

| row | rate | free-stream line | dCLB wing | dCRB25 airframe | dCNB25 airframe |
|---|---|---|---|---|---|
| 4202 | roll +4 | `ROTATION 2 X 0.667` | +0.00989 | +0.00287 | +0.00035 |
| 4203 | roll +40 | `ROTATION 2 X 6.667` | +0.09946 | +0.02880 | +0.00479 |
| 4204 | roll -40 | `ROTATION 2 X -6.667` | -0.09980 | -0.02892 | -0.00188 |
| 4205 | yaw +4 | `ROTATION 2 Z 0.667` | -0.00148 | -0.00055 | +0.00003 |
| 4206 | yaw +40 | `ROTATION 2 Z 6.667` | -0.01391 | -0.00517 | +0.00021 |
| 4207 | yaw -40 | `ROTATION 2 Z -6.667` | +0.00889 | +0.00386 | -0.00034 |

**The axis is right.** The roll increment of each wing section, over that
section's own control load, grows with span: 0.22 at the root cut, 0.49 at mid
span, 0.75 at the tip cut; the pitching increment stays small (dCMB25 +0.0026).
That is a rotation about x, not about y.

**The sense is reversed.**

- Roll: a positive flight-mechanics p lowers the right wing and raises the left,
  so the meshed left wing loses lift and the rolling moment opposes the motion
  (roll damping, Cl_p < 0). The row stating +40 deg/s gave the left wing MORE lift
  and a positive rolling-moment increment, which no damped wing produces. The
  response is linear (40 over 4 is 10.06) and odd (-40 gives -0.0998 against +0.0995).
- Yaw: a positive r moves the nose right, so the left wing advances and gains
  lift, and Cl_r > 0. The row stating +40 deg/s gave the left wing LESS lift and a
  negative rolling increment. Linear (9.4) and of opposite sign for -40, though
  not symmetric (+0.0089 against -0.0139): the half model's open cut and the
  side-wash at the root, where the section increment changes sign, are the likely
  cause and are not separated here.

So the solver turns the free stream as a right-hand rotation about each frame axis,
and the package, emitting the row's rate as written, asks for the opposite roll and
yaw.

## What it means for results already produced

A row of 0.21.0 to 0.26.0 that stated `roll_rate` or `yaw_rate` was solved at the
opposite rate: the coefficients are those of -p or -r. Its record carries the
free-stream line it emitted, so an affected run can be found by its script. A row
stating `pitch_rate` is unaffected.

## What this does NOT establish

- **One build.** 26.124. The emitted grammar is identical across the editions that
  document the command.
- **One geometry, one incidence.** The verdict rests on which surfaces gained lift
  and on the damping sign, not on the magnitude; no stability derivative is
  compared with theory.
- **The yaw asymmetry is recorded, not explained.**

## Evidence

`reports/probes/RPT-060_2026-09-23_evidence.yaml`: the scripts' digests, the
free-stream line of every point, the convergence of each, and the increments per
group. The solver outputs stayed on the measuring machine (invariant 5).
