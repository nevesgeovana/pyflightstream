# Migrating to 0.15.0

> Historical record assembled at 0.36.0 from the reference pages; frozen from now on.

## Historical row-key changes

- v0.15.0: `MOVING_BC_ALIAS`, the rotor a motion record moves, an alias the reference declares as a rotor block. It is the ONLY rotor identity a row carries: the hub, the axis, the sign, the blade count and the diameter come from that block, and a record stating `MOVING_BOUNDARIES`, `ROTOR_AXIS`, `ROTOR_ORIGIN`, `RPM_SIGN` or `BLADES` beside it is refused naming both (FR-61)
- v0.15.0: `CLOCK_MOTION`, which of the row's motions owns the time step and the run length. REQUIRED on any row that states a `MOTIONS` list: a row that states the list and no key is refused, naming the motions it could have named. The flat pre-0.15.0 form, which names one rotor in its own keys, is exempt because it has nothing to choose between; that form becomes required at 0.17.0 too (FR-64)
- v0.15.0: `SYMMETRY_LOADS`, whether the solver reports the loads of the meshed sector or of the whole wheel. On every run type, because a mirrored or periodic mesh is opened by a steady row too; a row stating it overrides the preset and warns naming both files (FR-66)
- v0.15.0: `RAW`, a list of records, one raw solver command each or one file of them, in the order written: `RAW: {COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}, {FILE: raw/extra.txt / BEFORE: init}`; a record states `COMMAND` or `FILE` and never both, and `BEFORE`, the phase it goes before, spelled as the preset's `[[raw]]` table spells it. **ITS PAIRS SPLIT ON A SPACED SLASH**, ` / `, and not on the bare one every other record kind uses, because its values are a path and a command line and both carry slashes of their own. A raw file is a path under `inputs/` whose blank lines and `#` lines are skipped (FR-67), see [What a solver preset may say](workflow-input-library.md#what-a-solver-preset-may-say-and-what-happens-to-a-key-that-reaches-nothing)
