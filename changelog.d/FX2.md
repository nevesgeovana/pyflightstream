## Changed

- FR-295, FR-296, FR-297: a CCS wing whose control surface states `space = "REAL"` is refused when the row is planned, on every build, naming RPT-097 and the PARAMETRIC form to use. Licensed round 2 on FlightStream 26.124 completed the PARAMETRIC form and ended the REAL form `FAILED_EXECUTION` with no saved simulation; see [CCS geometry](docs/ccs-geometry.md).
- FR-298, FR-299: the PARAMETRIC form plans as before, and the command database entry of `NEW_CCS_WING_CONTROL_SURFACE` on 26.124 stays `documented` with a note of what round 2 measured; promotion needs a `pyfs-qa probe` run.

## Added

- **`reports/RPT-097`, CCS confirmation, round 2 of 0.32.0** on FlightStream 26.124: the wing, the fuselage, the body of revolution, the control surface in the PARAMETRIC form and the G35 axial and azimuth files confirmed through the package route; the REAL control surface form not confirmed. (no requirement: licensed report RPT-097, not a capability)
- **`reports/RPT-098`, the acoustic chain on `unsteady_rotor`, wake stabilisation and surface removal, round 3 of 0.32.0** on FlightStream 26.124: the noise emission through the package route, the `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` DISABLE, ENABLE and absent-key comparison, and `DELETE_SURFACES` with the renumbered inventory. (no requirement: licensed report RPT-098, not a capability)
