# RPT-071 and RPT-077 in this checkout: the custom free stream on 26.124 (summary, 2026-10-22)

The package cites RPT-071 (2026-09-24, licensed probe T14) and RPT-077 (2026-09-25, licensed probe T16) for the
custom free stream; both are kept with the project's internal reports. This page restates, with no new solver
execution, the measurements those citations rely on, so they resolve in this checkout. FlightStream 26.124
(build 8172026), one wing of 8 m span at 30 m/s and sea level, `SOLVER_SET_FARFIELD_LAYERS 5`; every field a grid
at x = 0 over y from -8 to 8 m (9 stations) and z from -5 to 5 m (11 stations) unless stated. The loads table
prints four decimals; every point converged; a dash is a value RPT-071 did not tabulate.

| run | free stream | angle | CL | CDi | CMx | CMz |
|---|---|---|---|---|---|---|
| constant (control) | `SET_FREESTREAM CONSTANT` | 0 deg | 0.0023 | 0.0000 | 0.0011 | 0.0000 |
| constant | `SET_FREESTREAM CONSTANT` | 4 deg | 0.3385 | 0.0049 | 0.0009 | 0.0000 |
| T14 uniform field | STRUCTURED, vx = 30 m/s | 4 deg | 0.0021 | 0.0002 | - | - |
| T14, T16 uniform field | STRUCTURED, and UNSTRUCTURED (the same rows without the grid-count line) | 0 deg | 0.0023 | 0.0000 | 0.0011 | 0.0000 |
| T14 sheared field | STRUCTURED, vx = 30 + 2.5 z | 0 deg | 0.0045 | 0.0000 | - | - |
| T16 y-gradient field | STRUCTURED, vx = 30 + 0.5 y over the whole grid | 0 deg | 0.0023 | 0.0000 | 0.0014 | -0.0016 |
| T16 field cut to abs(y) <= 2 m | as above, narrower than the wing | 0 deg | 0.0023 | 0.0000 | 0.0012 | -0.0002 |
| T16 field held at abs(y) = 2 m beyond | the whole grid, vx clamped beyond 2 m | 0 deg | 0.0023 | 0.0000 | 0.0013 | -0.0011 |
| T16 field at 30 m/s beyond | the whole grid, vx = 30 m/s beyond 2 m | 0 deg | 0.0023 | 0.0000 | 0.0012 | -0.0005 |

What the citations rest on, for what was run:

- The angle of attack does not turn a custom field (T14): at 4 deg the uniform field loads as at 0 deg, nowhere near
  the constant row at 4 deg. The sideslip was not measured.
- The UNSTRUCTURED form runs and reads as the STRUCTURED one (T16): the same uniform rows give the same loads, which
  are the constant row's.
- Beyond its grid the solver does not extend a field, neither linearly nor by holding the edge station; what it
  applies there is closest to the free stream the script states (T16), which four decimals do not settle to the digit.
- A sheared field reaches the solve (T14): it doubles the lift of the uniform one.

Not established: interpolation accuracy inside a grid, the unit of the grid's coordinates, other angles, other builds.
