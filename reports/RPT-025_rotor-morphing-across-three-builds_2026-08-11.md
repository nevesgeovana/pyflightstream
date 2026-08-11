# RPT-025: the rotor morphing defect across three builds (2026-08-11)

RPT-007 measured, on 26.120 build 7012026, that the FSIDisp
deformation is not applied to a boundary attached to a ROTARY motion
definition: the coupling loop ran end to end, the executable was
called every step and its displacement file was read and parsed, but
the solid-body morphing was silently dropped for the rotating
boundary. Two-way rotor FSI has been blocked since, and the finding
was recorded as a candidate vendor defect.

This report answers one question. The defect is FIXED, in 26.122, and
the fix is not in 26.121.

## Result

The same script, the same generated geometry, the same imposed 0.10 m
tip flap, run against three executables. Percentages are the change
between the deformed arm and its own rigid arm.

| Build | CL | CDi | CDo | CMy | Verdict |
|---|---|---|---|---|---|
| 26.120 | 0.009 % | 0.059 % | 0.720 % | 0.141 % | does not respond |
| 26.121 | 0.009 % | 0.059 % | 0.720 % | 0.141 % | does not respond |
| 26.122 | 99.4 % | 71.4 % | 25.9 % | 70.1 % | responds |

26.120 and 26.121 agree to every printed digit, in both arms. All
three builds produce byte-identical RIGID coefficients (CL +0.044675,
CDi -0.052797, CDo +0.000791, CMy -0.017068), so the builds disagree
about nothing except the response to an imposed deformation. Every arm
of every build completed six coupling calls with the post-processing
script executed, no crash log, and finite coefficients.

## Why the package was rebuilt rather than re-run

The RPT-007 evidence package was scratch and did not survive. The
setup here is rebuilt from the committed generic-blade case
(`build_phy05_script` in `qa/physics.py`) and the committed node
machinery, and it is deliberately simpler than the original: one
structural node per station on a straight span line, which is the
archived WP1 layout, so the deformation is pure bending and carries no
twist. The original probe imposed 0.10 m of flap PLUS 5 deg of
nose-down twist through the mid-chord layout.

That difference is why the 26.120 and 26.121 arms are in the table at
all. Comparing 26.122 against RPT-007's published 0.09 percent would be
comparing two setups as well as two builds. Running the identical
script on the older executables leaves the build as the only variable,
and it also reproduces the original null: this setup measures 0.009 to
0.72 percent on 26.120, the same order as the 0.09 percent RPT-007
reported for a different deformation on the same build.

## The control that makes the null interpretable

A motionless full-span NACA 0012 wing, same aeroelastic block, same
node file shape, 0.40 m tip bend, on 26.122:

| Metric | Rigid | Deformed | Change |
|---|---|---|---|
| CL | +0.478159 | +0.961598 | 101.1 % |
| CDi | +0.009588 | +0.043836 | 357.2 % |
| CDo | +0.011159 | +0.015033 | 34.7 % |
| CMy | -0.123985 | -0.236126 | 90.4 % |

The rigid CL reproduces RPT-007's motionless control (+0.4803) to
within 0.4 percent, which is what establishes that this rebuilt setup
is the same physical problem. The deformed value differs from RPT-007's
+0.8577 because the node layout differs, as above.

## Two side findings

The first attempt imposed 0.30 m of tip flap. On 26.122 the deformed
arm returned `Infinity` for Cx, Cy, Cz, CDo and every moment, while CL
and CDi stayed finite: a degenerate panel in the directly integrated
forces. That is not a number to conclude from and the amplitude was
reduced, but it is evidence in its own right, because a mesh that can
be crushed is a mesh that moved. Nothing of the kind occurs on 26.120
at any amplitude tried.

The Aeroelastic Coupling Toolbox refuses the built-in analysis frame:
assigning frame 1 answers with a refusal naming the absence of a
user-defined coordinate system. The wing control therefore creates an
identity frame and assigns that. This is a fact about the interface
that no entry in the command database currently records.

## Consequences

* Two-way rotor FSI is unblocked on 26.122. `PLN-020` leaves the
  solver-blocked state it has been in since 2026-07-21.
* The RPT-006 near-rigid acceptance must be re-read on 26.122. Its
  "recovers the rigid baseline" outcome was reinterpreted by RPT-007 as
  trivially insensitive, on the ground that with morphing dropped any
  stiffness recovers the baseline. That reading was a consequence of the
  defect and does not carry over to a build where the morphing applies.
* The soft-blade pilot's structural response was recorded as the
  one-way response for the same reason. A coupled re-run on 26.122 is
  now possible and is a different measurement from the one RPT-007
  reports.
* The vendor-facing question RPT-007 left pending for the author's seat
  is closed by the vendor having fixed it.

## Limits of this report

Two builds were tested for the fix boundary and only the endpoints of
the deformation question were measured. Nothing here says the morphing
is CORRECT on 26.122, only that it is applied: the imposed shape is
arbitrary and no analytic expectation was compared against. A physical
validation of the coupled loop is a separate measurement.

## Reproduction

Three builds, `_private/exe/FlightStream_2612{0,1,2}/`, driven through
`LocalExecutor`. Geometry generated by `qa.geometry`
(`BladeSpec()` and the PHY-01 wing spec), so nothing proprietary is
involved and the whole setup regenerates from the repository. The
imposing executable is a batch file that copies one constant
displacement file into the working directory on every call and appends
a line to a call log, which is the instrument separating "no morphing"
from "no call". Scripts and logs are local scratch under `runs/`;
this report is the committed evidence.
