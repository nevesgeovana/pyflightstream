# RPT-077: what RPT-071 left open about the custom free stream (2026-09-25)

**Date:** 2026-09-25
**Found by:** the licensed probe T16 of the 0.28.0 work
**Status:** CLOSED in 0.28.0 (G18: the UNSTRUCTURED form recorded as run, the plan warns when a field does not cover the body, the rest documented)
**Affects:** `SET_FREESTREAM CUSTOM`, its UNSTRUCTURED form never run, its STRUCTURED form verified on 26.124 (RPT-071)

## What this settles

RPT-071 verified the STRUCTURED field on 26.124 and left five questions: the
UNSTRUCTURED form, a field that does not cover the body, a field that carries the
incidence the refusal of an angle tells a user to write into it, a saved
simulation reopened later, and the small residue of the angle. **The UNSTRUCTURED
form reads as the STRUCTURED one; beyond the field's grid the solver does not
extend the field, and what it applies there is close to the free stream it was
given; a field carrying the incidence gives the body the forces of that incidence
while the lift and drag are printed in the axes of the angle the script states;
and a saved simulation carries its field until a later script sets the free
stream again.**

## What was run

FlightStream 26.124 (build 8172026), the wing of RPT-071 (`12_WING_PHY.fsm`, 30
m/s, sea level, `SOLVER_SET_FARFIELD_LAYERS 5`), its CONSTANT row at 0 deg as the
base, in two detached batches with no solver alive before either; each batch ran
the unchanged base as its control. Each variant changes the free-stream lines, the
angle or the file it opens, and nothing else. Every field is a grid at x = 0 over
y from -8 to 8 m (9 stations) and z from -5 to 5 m (11 stations), the wing's span
being 8 m, unless said.

| variant | free stream | angle | compared with |
|---|---|---|---|
| F_C0, F_C0B | `SET_FREESTREAM CONSTANT` (the controls) | 0 | |
| F_C4 | CONSTANT | 4 deg | |
| F_S | CUSTOM STRUCTURED, uniform vx = 30 m/s (RPT-071's) | 0 | F_C0 |
| F_UNS | CUSTOM UNSTRUCTURED: the same rows as a `.dat`, without the `Npts Mpts` line | 0 | F_S |
| F_TILT | STRUCTURED, vx = 30 cos 4 deg, vz = 30 sin 4 deg everywhere | 0 | F_C4 |
| F_SH | STRUCTURED, vx = 30 + 2.5 z (RPT-071's shear) | 0 | F_C0 |
| F_NOFS | no `SET_FREESTREAM` line | 0 | F_C0 |
| F_REOPEN | no `SET_FREESTREAM` line, F_SH's SAVED `.fsm` opened instead of the geometry | 0 | F_NOFS, F_SH |
| F_REOPEN_C | as F_REOPEN with the base's `SET_FREESTREAM CONSTANT` kept | 0 | F_REOPEN |
| F_Y | STRUCTURED, vx = 30 + 0.5 y over the whole grid | 0 | |
| F_YSMALL | the same field cut to abs(y) <= 2 m, narrower than the wing | 0 | the three below |
| F_YCLAMP | the whole grid, vx held at its abs(y) = 2 m value beyond | 0 | F_YSMALL |
| F_YDEF | the whole grid, vx = 30 m/s (the free stream) beyond abs(y) = 2 m | 0 | F_YSMALL |

A first cut field (F_SMALL, the UNIFORM field cut to abs(y) <= 2 m) read as the
control, which a field equal to the free stream does whatever the solver does
beyond the grid; the y-gradient fields replaced it.

## What came back

The loads table prints four decimals. Every point returned 0 and converged.

| variant | Cx | Cz | CL | CDi | CMx | CMy | CMz |
|---|---|---|---|---|---|---|---|
| F_C0 = F_C0B = F_S = F_UNS = F_NOFS = F_REOPEN_C | 0.0066 | 0.0023 | 0.0023 | 0.0000 | 0.0011 | -0.0014 | 0.0000 |
| F_C4 | -0.0116 | 0.3378 | 0.3385 | 0.0049 | 0.0009 | -0.0858 | 0.0000 |
| F_TILT | -0.0124 | 0.3381 | 0.3382 | -0.0195 | 0.0009 | -0.0858 | 0.0000 |
| F_SH = F_REOPEN | 0.0066 | 0.0045 | 0.0045 | 0.0000 | 0.0011 | -0.0021 | 0.0000 |
| F_Y | 0.0066 | 0.0024 | 0.0023 | 0.0000 | 0.0014 | -0.0014 | -0.0016 |
| F_YSMALL | 0.0066 | 0.0023 | 0.0023 | 0.0000 | 0.0012 | -0.0014 | -0.0002 |
| F_YCLAMP | 0.0066 | 0.0023 | 0.0023 | 0.0000 | 0.0013 | -0.0014 | -0.0011 |
| F_YDEF | 0.0066 | 0.0023 | 0.0023 | 0.0000 | 0.0012 | -0.0014 | -0.0005 |

## What it means for the package

- **The UNSTRUCTURED form runs and is read as the STRUCTURED one**: the same
  uniform rows as a `.dat` give the STRUCTURED field's loads, which are the
  CONSTANT row's. A row may name either.
- **Beyond its grid the solver does not extend a field**, neither linearly (F_Y:
  CMz -0.0016) nor by holding the edge station (F_YCLAMP: -0.0011). What it applies
  there is closest to the free stream the script states (F_YDEF: CMx equal, CMz
  -0.0005 against -0.0002); the four decimals do not settle it to the digit. A
  field narrower than the body therefore loads the uncovered part with something
  near the constant free stream, silently. The package warns at plan when a field
  does not cover the body's y and z extent, naming both.
- **A field carrying the incidence gives the body the forces of that incidence**:
  F_TILT at 0 deg against CONSTANT at 4 deg, Cz 0.3381 against 0.3378, Cx -0.0124
  against -0.0116, CMy -0.0858 in both. **Its lift and drag are printed in the axes
  of the angle the script states (0 deg), not of the flow**: CDi -0.0195 is the
  4 deg lift and drag projected on the 0 deg axes (0.0049 cos 4 - 0.3385 sin 4 =
  -0.0187), and CL 0.3382 the same projection (0.3380). A user reading such a row
  reads the body forces Cx, Cy, Cz, or turns CL and CDi by the field's incidence.
  The refusal of a non-zero ALPHA or BETA beside a field stays.
- **A saved simulation carries its custom field**: F_SH's `.fsm` reopened with no
  free-stream line solves the sheared field (CL 0.0045), not the free stream the
  geometry alone gives (0.0023). **The package's own `SET_FREESTREAM CONSTANT`
  line overrides it** (F_REOPEN_C: 0.0023), so a CONSTANT row that opens such a
  file solves the constant free stream; a script without the line would not.

## What this does not settle

- The solver's rule beyond the grid to the digit.
- The small residue of the angle over a custom field (RPT-071: CDi 0.0002 against
  0.0000 at 4 deg); F_TILT shows the axes the coefficients are printed in, which is
  one candidate and was not isolated.
- Sideslip, which stays refused.

## Evidence

The scripts the solver received, the fields and the result records are kept
machine-local with the probe driver `p28f_driver.py`; the GOAL-032 ledger's T16
receipt names every path, the executable's sha256 and each batch's preflight.

**Verdict: VERIFIED**, for what was run: the UNSTRUCTURED form runs on 26.124 and
reads as the STRUCTURED one; a field does not reach beyond its grid; incidence
carried in a field loads the body as that incidence with CL and CDi printed in the
stated angle's axes; and a saved simulation keeps its field until the script sets
the free stream again.
