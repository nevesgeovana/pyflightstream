# RPT-051: a rotor on 26.100 without the rotor mark (2026-09-15)

**WHAT THIS SETTLES.** Up to 0.20.0 the `unsteady_rotor` workflow refused
26.100. That build names the motion type `EUCLIDEAN`, documents
`SET_MOTION_ANGULAR_VELOCITY` and no rotor axis or speed command, and its
solver does not recognize `SET_MOTION_IS_ROTOR` (RPT-049). From 0.20.1 the
workflow writes the rotor there as a Euclidean motion without the rotor mark.
This report records what is written, on what basis, and what no run in this
repository has measured.

**THIS IS A DECISION RECORD, NOT A MEASUREMENT.** No solver run in this
repository has used the motion this report describes.

## What 0.20.1 writes on 26.100

The committed render `tests/tier1_offline/goldens/workflows/unsteady_rotor__bare__26.100.txt`
(a rotor at 1200 rev/min about X) carries, in this order:

```
# FlightStream 26.100 has no scripted rotor mark: this motion is a Euclidean motion ...
CREATE_NEW_MOTION EUCLIDEAN
SET_MOTION_BOUNDARIES 1 -1
SET_MOTION_MOVING_FRAMES 1 -1
SET_MOTION_COORDINATE_SYSTEM 1 2
SET_MOTION_ANGULAR_VELOCITY 1 1200.0 0.0 0.0
```

- The angular velocity is the row's speed IN REV/MIN, along the row's axis in
  the motion's coordinate system. The value is not converted.
- No rotor mark is written. The solver is never told the motion is a rotor.
- The comment line above the motion says both things in every script that
  carries such a motion.
- `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` is not written. On 26.100 it takes
  no blade count, and `helpers.rotary_motion` refuses a blade count on this
  build by name, as it does on 25.100 and 26.000.

On 25.100 and 26.000 nothing changes: rad/s with the rotor mark (RPT-049).

## The basis

The maintainer decided on 2026-09-15 that the 26.100 rotor is written this way,
with the speed in rev/min.

## What argues against the unit, recorded so it is not lost

- The rotor tutorial of the 26.100 manual has the reader enter the rotor speed
  in radians per second in the dialog field that this command sets
  (SRC-741 p.394).
- On 26.000, which prints the same command grammar, RPT-049 measured rad/s. A
  blade driven at 49.55 rad/s turned exactly as the 26.120 rotary motion at
  473.1723 rev/min turned it.
- If 26.100 reads the value in rad/s, the rotor written by 0.20.1 turns
  60/(2π), about 9.55 times faster than the row states.

## What this does NOT say

- The unit on 26.100 is not measured.
- The sense of rotation on 26.100 is not measured.
- The effect of the missing rotor mark on the solution, which is the slipstream
  treatment the mark selects on 26.000, is not measured.

A run of the kind RPT-049 made settles the unit and the sense. It takes two
rows on 26.100, on the blade 26.100 saved:

- one at 49.55 and one at 473.1723 in `SET_MOTION_ANGULAR_VELOCITY`, both three
  steps of 30 degrees;
- the exported blade angle is then compared with the 90 degrees the rotary
  motion reaches on 26.120.

If that run disagrees with this record, the unit constant
`script.rotor_vocabulary.UNMARKED_EUCLIDEAN_ROTOR_UNIT` and the conversion in
`helpers.rotary_motion` change together in the same commit as its report.
