## Added

- Disc maps (FR-270, FR-271, FR-272): `sections/<point>_disc_<ROTOR>_<QUANTITY>.csv`, the sectional load by radius and azimuth over the disc, one file per rotor and quantity, from a quasi-steady wheel's sections at every clocking and from an `unsteady_rotor` point's last complete revolution. A rotor with no blade in the table is named in the skips and never blocks.
- `pyflightstream._fsm.boundary_vertices` (FR-273): each boundary's vertices of a saved simulation by name, from the block's per-face boundary row.
- The plan reads the chord of a saved simulation (FR-274), so `pyfs-matrix plan` warns before the run when a quasi-steady wheel's reduced frequency passes 0.1, as it did for an OBJ.

## Migration

- A quasi-steady wheel point and an `unsteady_rotor` point that cut sections now also write disc map files beside `sections/<point>_harmonics.csv` and register them in `products.json` with `kind` `disc_map` (FR-270). Nothing existing changes; a consumer that lists `sections/` will see the new files.
- A wheel row that opens a `.fsm` now shows its chord-based `k` in the plan, and its warning, where it showed k per metre of chord (FR-274).
