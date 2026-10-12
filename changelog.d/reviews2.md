## Fixed

- A `TK` pin is the temperature of the whole flow state: the speed of sound (`sqrt(gamma R T)`), the Sutherland viscosity, the Mach to velocity conversion, the derived Reynolds number and the density now follow it, as they follow a `dISA`.
- The emitted density, pressure and temperature satisfy `p = rho R T`: a density solved from `REmi` or pinned by `RHOkgm3` is emitted beside its own ideal-gas pressure, and a `PPA` pin sets the density at the state's temperature.

## Migration

- Rows pinning `TK` without `ASMPS` or `MUPas` resolve a different speed of sound, viscosity, density and (with `MACH`) velocity: those of the pinned temperature instead of the standard atmosphere's. Pin `ASMPS` and `MUPas` as well to keep the previous numbers.
- Rows stating `REmi`, or pinning `RHOkgm3`, without `PPA` emit the pressure `rho R T` instead of the altitude's pressure, so their `PRESSURE` line changes. Rows pinning `PPA` without a density constraint resolve the density `PPA / (R T)` instead of the altitude's density. Pin `PPA` (and `RHOkgm3`) to keep a specific value.
