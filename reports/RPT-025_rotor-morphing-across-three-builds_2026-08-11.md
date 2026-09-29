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

## Correction (2026-09-28): where the morphed rotor surface went

This report measured integrated coefficients at the end of each run and
nothing else. It never exported the surface, so it never located the
morphed blade. A later measurement shows that where the blade went is
exactly what decides how its numbers read. Nothing above this section is
edited; this section says which of its claims still hold.

### What was measured since

On 26.124, with the aeroelastic surface list holding the blade's boundary
ID, the solver maps the rotating blade (936 vertices) and applies the morph
after every structural call. It applies the morph to the blade at its
IMPORT azimuth, though, not to the rotated one. Every surface export
written after a call shows the blade at 0.000 deg from its imported
position, carrying the flap. The solver then iterates again on that
geometry (20 to 77 extra iterations), and the next time step restores the
rigid, rotated blade. The morph replaces the rotation instead of being
composed with it. The result is the same with the structural nodes inside
the blade, and a self-contained reproduction on the package's synthetic
blade (boundary ID 1) behaves the same way. Source: the 26.124 aeroelastic
probes of 2026-09-28, [RPT-093](RPT-093_aeroelastic-coupling-on-26124_2026-09-29.md).

### What that does to this report's numbers

Under that mechanism, the deformed arm's final coefficients are those of a
blade that has been put back to its import azimuth, with part of its wake
shed from there. The rigid arm's blade sits at its rotated azimuth. The
rigid coefficients are byte-identical across the three builds, so the rigid
arm's blade was not put back, whether or not that arm had the coupling
enabled. The table therefore compares two geometries that differ by a rigid
rotation as well as by the flap, and the report holds no measurement that
separates the two.

The magnitude fits the return to the import azimuth. On the probe case,
that return alone took the blade CL from 0.0045 to 0.0119 in the rotating
solves down to about 0.0009 in the post-call passes, a change of 80 to 92
percent. Within nine steps it also moved the rotating solves' own loads, by
up to 17 percent in CL and 6.5 percent in blade Fx. The changes in this
report's table (CL 99.4, CDi 71.4, CDo 25.9 and CMy 70.1 percent) are of the
same order. A real flap of the size imposed here cannot produce them. A
0.10 m tip flap in pure bending, with no twist, on a 1.83 m blade is about
3 deg of coning, and blade-element reasoning puts its effect on thrust and
torque at a few percent, not 70 to 99 percent. The table's percentages are
unsigned, so the direction of the CL change cannot be recovered from this
report either.

Neither the aeroelastic block nor the coupling cadence (six structural calls
against the builder's 54 time steps) is in the committed builder, and no
script, log or `.fsm` of these runs survives. So neither the azimuth at
which each arm's final loads were integrated nor the number of returns can
be reconstructed now.

### Limits of this correction

The return to the import azimuth was MEASURED on 26.124 only. The one
26.122 diagnostic made since ran with the surface list pointing at a
boundary that does not exist. It mapped no vertices and says nothing about
where 26.122 puts a mapped rotor. That 26.122, with this report's STL route
(boundary ID 1), behaves like 26.124 is an inference from the two builds
behaving alike on the OBJ route. It is not a measurement. No measurement
shows the opposite either.

### What this report still establishes

* On 26.120 and 26.121 an imposed displacement leaves the rotating-blade
  loads unchanged (0.009 to 0.72 percent), with the structural program
  called and its file read every time. On 26.122 the same script changes
  them strongly. The builds differ in whether the morph touches a rotating
  boundary at all.
* The rigid coefficients are byte-identical across the three builds.
* On 26.122 the morph acts on a motionless boundary (the wing control).
  That control shows the surface responds. It does not show that the
  surface took the imposed shape. A CL increase of 101 percent from 0.40 m
  of bend with no twist on an 8 m wing is larger than a pure bend can
  produce, so the morphed wing was probably not the imposed shape either.
  That is an inference; the surface was not exported.
* The Aeroelastic Coupling Toolbox refuses the built-in analysis frame
  (the second side finding).
* The `Infinity` coefficients at 0.30 m of flap show that a rotor surface
  moved. They do not show where it moved.

### What this report can no longer claim

* That on 26.122 the morph is applied to the rotating blade. What it
  supports is "applied to the rotor boundary, at a position not measured".
* That the CL change of 99.4 percent, or any other percentage in the table,
  measures the aerodynamic effect of the imposed flap. The change can be
  wholly or partly the blade's return to its import azimuth.
* "The defect is FIXED, in 26.122". The evidence supports "the defect
  changed form after 26.121": the morph went from dropped (26.120 and
  26.121) to applied at the import azimuth (26.124, measured; 26.122, not
  measured with a mapped rotor).
* Consequences 1 and 4 ("Two-way rotor FSI is unblocked on 26.122"; "closed
  by the vendor having fixed it"). This report's evidence does not support
  them. FSI on `unsteady_rotor` is refused by the 0.30.0 plan while the
  rotor morph is in debug.
* Consequences 2 and 3 (re-reading the RPT-006 near-rigid acceptance, and
  the coupled re-run of the soft-blade pilot). Both assumed a morph applied
  to the rotating blade. On this evidence they stay open; they are not
  enabled.

### The measurement that would separate the two readings

A rotor run on 26.122 through this report's STL route (boundary ID 1) that
exports the surface before and after every structural call and records the
azimuth of the morphed blade. A coupled arm that imposes zero displacement
would serve as the control, separating the return to the import azimuth
from the flap.

The CHANGELOG entry of 0.8.0 that cites this report (the line reading "26.122
and NOT fixed in 26.121 (RPT-025)") carried the same claim as the withdrawn
headline; a dated correction line now follows it there.
