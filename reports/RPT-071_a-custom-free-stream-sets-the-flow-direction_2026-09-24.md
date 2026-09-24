# RPT-071: a custom free stream sets the flow's direction, and the angle of attack does not turn it (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed probe T14 of the 0.27.0 work
**Status:** CLOSED in 0.27.0 (G15: a row names a custom free stream; a row that also states a non-zero ALPHA or BETA is refused at plan)
**Affects:** `SET_FREESTREAM CUSTOM STRUCTURED`, which the command database recorded as documented and never run on any build

## What this settles

The GUI's free-stream node has a custom option: a velocity field over the YZ
plane of the global frame, read from a file. 0.27.0 reaches it from a matrix
row (`FREESTREAM: <stem>`, a file of `inputs/freestreams/`). Three things had
to be known before a campaign could lean on it: in what units the solver reads
the file, whether the angle of attack still turns the flow when a field is
given, and whether a field that varies over the plane changes the loads.
**The file is read in metres and metres per second; the angle of attack does
not turn the field; and a sheared field changes the loads.**

## What was run

FlightStream 26.124 (build 8172026, executable sha256 68e64e66...), five
steady points of one wing (`12_WING_PHY.fsm`, reference r008, setup s010 with
`SOLVER_SET_FARFIELD_LAYERS 5`, pproc p002), 30 m/s, sea-level density,
launched in one detached run with no solver alive before it. Each row moves
ONE thing against a control:

| row | free stream | angle | compared with |
|---|---|---|---|
| 5010 | `SET_FREESTREAM CONSTANT` (the control, run earlier the same day) | 4 deg | |
| 5011 | a uniform field, vx = 30 m/s, vy = vz = 0 | 4 deg | 5010 |
| 5012 | the same uniform field | 0 deg | 5013 |
| 5013 | `SET_FREESTREAM CONSTANT` | 0 deg | |
| 5014 | a sheared field, vx = 30 + 2.5 z m/s | 0 deg | 5013 |

Both fields are STRUCTURED files of 9 x 11 stations over y from -8 to 8 m and
z from -5 to 5 m at x = 0, a margin of 4 m beyond the wing's extent on each
side, written by the package's test tooling with its own numbers.

## What came back

The loads table prints four decimals.

| row | CL | CDi | CDo | iterations |
|---|---|---|---|---|
| 5010 CONSTANT, 4 deg | 0.3385 | 0.0049 | 0.0071 | 58 |
| 5011 uniform field, 4 deg | 0.0021 | 0.0002 | 0.0065 | 51 |
| 5012 uniform field, 0 deg | 0.0023 | 0.0000 | 0.0066 | 51 |
| 5013 CONSTANT, 0 deg | 0.0023 | 0.0000 | 0.0066 | 51 |
| 5014 sheared field, 0 deg | 0.0045 | 0.0000 | 0.0066 | 51 |

Every point converged, and its loads export states the angle and the
free-stream velocity the script set.

## What it means for the package

- **The speed is read in m/s.** The uniform field equal to the row's own free
  stream gives the CONSTANT row's loads to the print (5012 = 5013), and every
  coefficient is divided by the reference velocity the script states (30 m/s,
  the same in both): a field read in another unit of speed would scale every
  force, and so CDo (0.0066 in both) and CL, by that unit's factor squared. The
  grid's coordinates were not probed on their own: the field is uniform, so
  where its stations sit does not reach the loads. No conversion is applied.
- **At 4 deg the angle does not turn the lift of a uniform field.** At 4 deg
  the uniform field loads as it does at 0 deg (CL 0.0021 against 0.0023), and
  nowhere near the CONSTANT row at 4 deg (CL 0.3385); one angle was run. With a custom field the direction of the flow is
  the field's own; `SOLVER_SET_AOA` still moves the result a little (CDi
  0.0002 against 0.0000), which this run does not explain. A row that swept
  ALPHA over a custom field would therefore have run every point at the field's
  incidence and reported the angle it stated. **0.27.0 refuses a row that
  states a custom free stream beside a non-zero ALPHA or BETA, fixed or
  swept**, and its message says to write the incidence into the field's vy and
  vz components. Sideslip was not measured and is refused for the same reason.
  Row 5011 is retired from the tier-3 matrix: it would now be refused, and this
  report is its record.
- **The field reaches the solve.** The sheared field doubles the lift of the
  uniform one at 0 deg (0.0045 against 0.0023).

## What this does not settle

- The UNSTRUCTURED form (`.dat`) did not run.
- The unit of the grid's coordinates, which a uniform field cannot show; a
  sheared field against the same field shifted in z would.
- Angles other than 4 deg, and a field that carries the incidence in its vz
  compared with the CONSTANT row at that angle (the advice of the refusal).
- What the solver does with a point of the geometry outside the field's grid.
- Why the angle still moves the result a little over a custom field (CDi 0.0002
  against 0.0000).
- Whether a saved simulation reopened later carries the custom field.

## Evidence

The scripts the solver received are `sims/sim_5010` to `sims/sim_5014` of the
tier-3 workspace of this run; each states `SOLVER_SET_FARFIELD_LAYERS 5`, and
the four custom-field rows name their field file on the line after
`SET_FREESTREAM CUSTOM STRUCTURED`. The record of each point carries the
field file's sha256 in `inputs_sha256`. The licensed checks of rows 5012 to
5014 are `tests/tier3_licensed/test_freestream.py`; the refusal is
`tests/tier1_offline/test_g15_custom_freestream.py`.

**Verdict: VERIFIED**, for what was run: `SET_FREESTREAM CUSTOM STRUCTURED` runs
on 26.124, a uniform field's speed is read in m/s, and at 4 deg the angle of
attack does not turn its lift. The grid's unit and other angles are open.
