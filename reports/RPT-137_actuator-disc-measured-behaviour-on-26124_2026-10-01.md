# RPT-137 - The actuator disc on FlightStream 26.124: the swirl sense, the swirl factor, the thrust ELLIPTICAL and RELAXED put in the wake, and the quasi-steady probe frame (2026-10-01)

A summary of a measured research study of the actuator disc, written for
pyflightstream 0.34.0 (GOAL-039, arm MA). It states what the study measured
that the package's emission and documentation depend on: the sense in which
a disc swirls for a given `rpm_sign` (FR-331), and four behaviours a reader
would not assume (FR-332). The study ran through the package route of 0.32.0
(`pyfs-matrix plan`, then `pyfs-matrix run --local`) on **FlightStream 26.124,
build 8172026**, executable SHA-256 withheld from the public tree per NFR-31,
one solver instance at a time, hidden. **No solver was run to write this
report**, and no new run was made for it.

Only nondimensional values are stated: the Mach number, the advance ratio J,
r/R and x/R (R the rotor tip radius), velocity ratios to the free-stream
speed, swirl angles and thrust ratios. The geometry is not described.

## 1. The study and its conditions

One propeller on one body was solved four ways at the same condition: as an
actuator disc on the body (the steady solver), as a quasi-steady wheel
(`qsteady_rotor`), and as a sector and a full wheel turning in time
(`unsteady_rotor`). The disc sits in the rotor's hub frame, on the rotor's
axis, with the rotor's tip radius. The condition is Mach 0.144, J = 1.8
(the main case), alpha 0 and 5 degrees. The disc was loaded four ways: the
radial thrust of the unsteady sector (CUSTOM), a uniform pressure jump
(CUSTOM), a Betz-Prandtl-like load (CUSTOM), and the native ELLIPTICAL model
(`ACTUATOR_THRUST`), each with a RIGID and a RELAXED wake. The wake was
sampled by probe lines at x/R = 0.5, 1, 1.41, 2 and 4 behind the disc plane.
All 56 recorded points converged (the steady discs in 177 to 238 iterations,
residual below 1e-5).

The thrust a disc puts in the wake is read as the axial momentum flux of the
wake through the probe plane at x/R = 4, divided by the thrust asked.

## 2. The swirl sense (FR-331)

| model | hand | swirl angle at x/R = 1, in the rotor's sense |
|---|---|---|
| unsteady wheel | rotor `rpm_sign +1` | +5.3 deg |
| disc, handed plus the speed | block `rpm_sign +1` (0.33.0 emission) | -6.4 deg |
| disc, handed minus the speed | block `rpm_sign -1` (0.33.0 emission) | +4.8 deg |

A disc whose block stated the rotor's hand, emitted as 0.33.0 emits it
(`SET_PROP_ACTUATOR_RPM` with plus the sign times the speed), swirled its
wake AGAINST the rotor it stands for. Handed minus the speed it swirled with
the rotor, and every later disc of the study was run that way. From 0.34.0
the script hands the solver minus `rpm_sign` times the speed, so a block
stating the rotor's hand swirls with the rotor. The manual says only that
the sign sets the direction; the sense above is a measurement of one build,
and on another build the same rule is unmeasured.

## 3. The swirl is one global factor (FR-332 R2)

`SET_PROP_ACTUATOR_SWIRL` takes one number, 0 to 1, the fraction of the swirl
the solver computes for the disc from its thrust and speed that is kept
downstream; the 26.124 grammar has no command that imposes a radial swirl
distribution. The disc computes its own swirl, and the radial swirl of a
bladed rotor cannot be given to it. At J = 1.8, alpha 0, with the factor 1,
the RIGID disc loaded by the sector's radial thrust swirled 0.5 to 1.0 deg
above the sector over x/R 0.5 to 4.

## 4. ELLIPTICAL placed 0.62 of the thrust asked in the wake (FR-332 R3)

| loading, wake | thrust flux at x/R = 4 / thrust asked, J 1.8, alpha 0 | alpha 5 |
|---|---|---|
| the sector's radial thrust, RIGID | 0.952 | 0.953 |
| ELLIPTICAL, RIGID | 0.619 | 0.532 |
| uniform, RIGID | 0.979 | 0.889 |
| Betz-Prandtl-like, RIGID | 0.964 | 0.875 |
| any of the four, RELAXED | 0.510 | 0.423 |

At alpha 0 the CUSTOM profiles put 0.95 to 1.04 of the thrust asked in the
wake across the study's thrust levels and advance ratios, so the profile is
read as stated. The ELLIPTICAL
model put 0.62 of it there, at the thrust asked and at twice it alike (0.619
and 0.652), so it is linear and scaled, and its axial velocity falls from the
hub to the tip, unlike an elliptic load with its maximum inboard of the tip.
The manual gives the elliptic formula only as an image, so the definition the
solver uses cannot be read; the value is a measurement of this case, not a
guaranteed one.

## 5. RELAXED ignored a custom profile (FR-332 R4)

With `wake_type = "RELAXED"`, the four loadings gave the same wake to seven
digits: the three CUSTOM profiles and the ELLIPTICAL model alike. The wake
scales with the net thrust (twice the thrust, about twice the flux), does not
change in axial velocity with a speed 1.25 times higher, carries about half of
the thrust asked (0.51 of it at x/R = 4, more nearer the disc, so the wake also
decays downstream), and swirls 1.8 to 2.0 deg against 4.8 deg for the RIGID
disc loaded by the sector's radial thrust. This is the steady solver of 26.124;
whether a relaxed disc needs the unsteady solver or more wake iterations is
open. From 0.34.0 the plan warns on a RELAXED disc whose row names a profile,
and never refuses it.

## 6. The probe velocities of a quasi-steady run are in the blade's frame (FR-332 R1)

A `qsteady_rotor` point holds the blades still and turns the free stream, and
its probe velocities are expressed in the rotating frame of the blade: at
r/R = 1.5, outside the slipstream, at J = 1.8, a probe read a tangential
velocity of -2.618 times the free-stream speed, which is Omega r / V = pi
(r/R) / J exactly. A fixed-frame field is the probe velocity with Omega r added
back.

## 7. The solver's default wake end plane on a blades-only wheel

A wheel of blades alone, with no body behind it, had its default wake end
plane at x/R = 2.08 (its solver log), where the cases with the body behind the
rotor had it at x/R = 5.52. The blades-only wheel lost its slipstream between
x/R = 2 and 4 (axial velocity ratio 1.004 at x/R = 4), and its thrust
coefficient moved by 0.8 per cent when the plane was moved to x/R = 5.52. A
wake study states the plane rather than leaving the solver's default.

## 8. What this report does not establish

- Any build but 26.124 (build 8172026): the sign rule of section 2 is applied
  to every build by 0.34.0, and is measured on this one.
- Any case but this one: the ratios of sections 4 and 5 are measured values of
  one propeller at one condition, not properties of the solver.
- The cause of the ELLIPTICAL deficit and of the RELAXED behaviour: a question
  for the vendor, or a test with the unsteady solver.
- The loads of a disc: the study read the wake, not the body's loads.
