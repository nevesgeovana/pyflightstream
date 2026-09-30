## Added

- FR-240: a matrix row whose `GEOMETRY` names a CCS file (`.csv` or `.ccs`) has the solver loft one of its components as a wing, by the `[import.ccs]` table of the file's sidecar (`kind = "wing"`, `component`, the loft settings and `subdivisions`); see [CCS geometry](docs/ccs-geometry.md).
- FR-241: `kind = "fuselage"` lofts one component of a CCS file as a fuselage.
- FR-242: `kind = "revolution"` revolves one component's profile into a body of revolution about an axis of the reference frame.
- FR-243: a CCS wing declares its gapped control surfaces as `[[import.ccs.control_surfaces]]`, each written with all ten arguments of `NEW_CCS_WING_CONTROL_SURFACE`, since 26.124 refused the eight-argument line the manual prints.
- FR-244: `kind = "file"` imports every component of a CCS file whole by `CCS_IMPORT`, and the row key `CCS_SHEDDING` (`AXIAL`/`0`, `AZIMUTH`/`1`) chooses the direction of every `Relaxed_TE` shedding line, applied to the run's own copy of the file.

## Fixed

- FR-244: `script.helpers.parse_relaxed_trailing_edge` and `RelaxedTrailingEdge` count the values of the manual's line `Relaxed_TE;u;v1;v2;direction`: three, or four with the direction. They counted four leading values and a fifth for the direction, so `0.5;0.2;0.8;1` read as a specification stating no direction and was restated as `0.5;0.2;0.8;1;1`. The line may now be written with its `Relaxed_TE` keyword, which the rendering keeps. `RELAXED_TE_FIELDS_WITHOUT_DIRECTION` is 3 and `RELAXED_TE_FIELDS_WITH_DIRECTION` is 4.

## Migration

- FR-244: a relaxed trailing-edge specification passed to `parse_relaxed_trailing_edge` or to `cases.workflows.rotor_relaxed_trailing_edges` is read as the manual writes it. Four numbers are `u`, `v1`, `v2` and the direction; write three (`0.5;0.1;0.9`) for a specification stating no direction. A text with five numbers is refused. `RelaxedTrailingEdge(fields=...)` takes the three values.
