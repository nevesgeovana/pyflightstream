# RPT-052: the sense of a rotating free stream (2026-09-15)

**WHAT THIS SETTLES.** From 0.21.0 a matrix row states one body rate --
`roll_rate`, `pitch_rate`, `yaw_rate` -- in deg/s and in flight-mechanics
signs, and the script writes `SET_FREESTREAM ROTATION <frame> <axis> <rev/min>`
about the moment reference point instead of `SET_FREESTREAM CONSTANT` (FR-105).
The package emits the rate AS WRITTEN. **What the solver does with a positive
angular velocity about a frame axis is stated by no edition of the manual**,
and this report is the measurement that decides whether the emitted sign means
what a flight-mechanics rate means.

**THE VERDICT: it does.** A positive `pitch_rate` produces the flow field of a
NOSE-UP rotation on FlightStream 26.124, so
`cases.workflows.FREESTREAM_ROTATION_SIGN` stays `+1`.

## The question a fixture cannot answer

A fixture can assert that the command is written, with the frame the reference
declares and the rate converted to rev/min. It cannot say which way the flow
then turns: that is a property of the solver, and the manual's page on
`SET_FREESTREAM` (SRC-003 p.322) gives the arguments and not the sense.

The consequence of getting it wrong is silent. A row asking for a pull-up would
be solved as a push-over: every coefficient plausible, every residual clean, and
the damping term of the wrong sign.

## What was run

One workspace, three points, ONE THING MOVED between them: the rate.

    workspace   GeoverseResearch/tools/fts_workspace/pfs0210-probe-rotation
    geometry    30_WB.fsm, the wing-body of pfs0160, READ and never written
    build       FlightStream 26.124
    row         MACH:0.2, REmi:11.7716754, ALPHA:sweep, BETA:0.0, pitch_rate:<rate>
    points      alpha 2 deg, pitch_rate 0.0, 4.0 and 40.0 deg/s
    reference   SREF 50.0, CREF 2.526, BREF 20.0, MRP at x = 9.152 m
    axes        [body_axes] roll = X, pitch = Y, yaw = Z

The two scripts of the first pair were rendered offline and diffed before the
seat was spent: **102 lines each, ONE differing line**.

```
-SET_FREESTREAM CONSTANT
+SET_FREESTREAM ROTATION 2 Y 0.6666666666666666
```

Frame 2 is the `MRP` coordinate system the builder creates at the reference's
moment point; `Y` is the axis `[body_axes]` gives the pitch rate; 0.6667 rev/min
is 4 deg/s.

All three points converged.

## What came back

Group 1 is the airframe, group 2 the wing alone, group 3 the body alone, as
`p001` defines them. Body axes, moments about the MRP at the quarter-chord
reference.

| pitch_rate | CL (airframe) | dCL | CM25 (airframe) | dCM25 | dCL wing | dCL body |
|---|---|---|---|---|---|---|
| 0 deg/s | 0.24116 | -- | -0.02467 | -- | -- | -- |
| 4 deg/s | 0.24349 | +0.00233 | -0.02481 | -0.00014 | +0.00262 | -0.00029 |
| 40 deg/s | 0.26383 | +0.02267 | -0.02583 | -0.00116 | +0.02569 | -0.00302 |

**The response is linear in the rate**: ten times the rate gives 9.7 times the
lift increment and 8.3 times the moment increment. That is what says the
solver is reading the command rather than being perturbed by it, and it is why
the second rate was run at all: at 4 deg/s the moment increment is 0.6% of the
base and could be argued with; at 40 deg/s it is 4.7% and cannot.

## Why that is a nose-up rate

**The moment opposes the rotation.** A lifting surface rotating about a point
near its own quarter chord sees an increased local angle of attack behind the
centre of rotation and a decreased one ahead of it, so the increment of
pitching moment OPPOSES the rotation: pitch damping, `Cm_q < 0`. The measured
increment is NEGATIVE (nose-down) for a positive emitted rate, so the emitted
rotation is the one a nose-up rate produces. Had the solver read the positive
value as nose-down, the damping would have been nose-UP and `dCM25` positive.

**The lift moves the way it must.** The wing, whose centroid is behind the MRP,
GAINS lift (+0.0257 at 40 deg/s) while the body, most of which is ahead of it,
LOSES lift (-0.0030). Aft up, forward down, which is the same nose-up rotation
read a second way.

## What this does NOT establish

- **The other two rates are not measured.** Roll and yaw are emitted by the
  same code with the same sign against the axis the reference declares, and
  nothing here ran one. A row that rolls or yaws rests on this measurement plus
  the argument that one axis is not special, which is an argument and not a run.
- **The magnitude is not calibrated against theory.** No `Cm_q` was computed
  from a strip model and compared; the measurement is of the SENSE, and the
  linearity is evidence that the command is read, not that the value is right.
- **One build.** 26.124. No other build was asked, and the command's grammar is
  identical across the editions that document it.
- **One geometry, one incidence.** The argument above is about where the
  surfaces sit relative to the moment point, which is a property of this
  configuration; a configuration whose lifting surfaces sit entirely ahead of
  its moment point would show the opposite lift increments and the same
  moment sign, and the moment is the half the verdict rests on.
