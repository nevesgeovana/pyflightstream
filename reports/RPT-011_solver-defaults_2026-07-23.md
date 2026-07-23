# RPT-011: solver-flag defaults from the settings-and-status export (PLN-023)

Date: 2026-07-23. Licensed machine, FlightStream 26.120
(`Flightstream_2612.exe`, solver build #7012026). Synthetic geometry
only (a generated NACA 0012 wing); no research geometry involved.

## Question

The solver-setup provenance snapshot marks 25 of 29 flags `unknown`
(no in-repo evidence of their default). Can `OUTPUT_SETTINGS_AND_STATUS`
capture those defaults on a freshly initialized model, so the
provenance can move from `unknown` to evidence-backed `default`?

## Method

Through the library's own builder: `OPEN` a base wing model,
`FLUID_PROPERTIES`, `SET_FREESTREAM CONSTANT`, `INITIALIZE_SOLVER`
(incompressible, no symmetry), then `OUTPUT_SETTINGS_AND_STATUS` to a
file, without setting any optional flag. The dump is the solver's own
report of its default state.

## Finding

The export reports only the fluid properties and the core solver
settings, and stops at the reference area:

* Mode is reported `Steady` on a fresh model: the solver initializes
  steady, so `SET_SOLVER_STEADY` is the effective default and
  `SET_SOLVER_UNSTEADY` is off until set. This is a citable default.
* Angle of attack, sideslip, velocity, reference velocity, Mach,
  reference Mach, reference length, and reference area are reported
  with their initialized values (0, 0, 100 m/s, unit references).
  These are always set explicitly in any real case, not defaults a
  user relies on.
* The optional toggles whose provenance is `unknown` (viscous
  coupling, viscous-excluded boundaries, mesh-induced wake velocity,
  wake-on-wake induction, additional wake relaxation, wake-termination
  time steps, Reynolds-averaged drag forces, unsteady pressure and
  Kutta, convergence-iteration count, parallel threads, RBF type,
  bulk separation) are NOT reported by the export at all. The
  settings-and-status sheet does not expose them.

## Conclusion

The settings-and-status export cannot seed the toggle defaults: it
does not report them. Those provenances stay honestly `unknown`, by
evidence limitation and not omission, which is the correct state under
the evidence rule (a default is never guessed). The one promotable
result is the steady-mode default.

## Follow-up

* `SET_SOLVER_STEADY` provenance can move `unknown` to `default` with
  this report as evidence (a lane A change to `FLAG_SPECS` in
  `script/solver_setup.py`).
* Capturing the toggle defaults needs the physics-difference route
  (an advanced-flag PHY case comparing the flag set versus unset),
  which is the PLN-023 advanced-settings line, named as a next-window
  known gap.
