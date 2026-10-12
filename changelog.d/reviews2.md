## Fixed

- A `TK` pin is the temperature of the whole flow state: the speed of sound (`sqrt(gamma R T)`), the Sutherland viscosity, the Mach to velocity conversion, the derived Reynolds number and the density now follow it, as they follow a `dISA`.
- The emitted density, pressure and temperature satisfy `p = rho R T`: a density solved from `REmi` or pinned by `RHOkgm3` is emitted beside its own ideal-gas pressure, and a `PPA` pin sets the density at the state's temperature.
- A refined level whose kept-row trailing edge was detected names its points file in its boundaries file (`file = "<level>.te.txt"` in place of `detect`) when every family the detection route covers was detected, so the run marks the line the refinement kept; otherwise a warning names the points file the run does not read.
- Audit gate G4 fails a trailing-edge line that a source chain no longer reaches (a shortened chain), and reports the level's and the source's trailing-edge lengths.

## Migration

- Rows pinning `TK` without `ASMPS` or `MUPas` resolve a different speed of sound, viscosity, density and (with `MACH`) velocity: those of the pinned temperature instead of the standard atmosphere's. Pin `ASMPS` and `MUPas` as well to keep the previous numbers.
- Rows stating `REmi`, or pinning `RHOkgm3`, without `PPA` emit the pressure `rho R T` instead of the altitude's pressure, so their `PRESSURE` line changes. Rows pinning `PPA` without a density constraint resolve the density `PPA / (R T)` instead of the altitude's density. Pin `PPA` (and `RHOkgm3`) to keep a specific value.
- A level refined with `keep_first_row` on a detected trailing edge now writes `[trailing_edges] file = "<level>.te.txt"` instead of the source's `detect` when the route covers only the detected families, so its run marks the refined line rather than detecting again.
- The G4 values of `<stem>.audit.json` gain `length`, `source_length`, `source_ends` and `source_ends_missing`; a level whose trailing edge no longer reaches a source chain's end now fails G4.
