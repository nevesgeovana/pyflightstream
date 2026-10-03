# Migrating to 0.14.0

> Frozen record: not edited after its release.

## Historical row-key changes

- v0.14.0: none. What changed again is what `MOVING_BOUNDARIES` ACCEPTS: a name the row's setup defines under `[aliases]`, between the exact label and the family, see What a solver preset may say
- v0.14.0: `ROTATE`, a list of records, one rotation of the opened mesh each, in the order written: `ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: Blade,S / AUX_FRAMES: ROTOR_MRP}, {...}`; on every run type; the frame is one the setup defines or the package creates, the families are names, never indices (PFS-2034.02), see [One row, one geometry, turned](workflow-row-geometry-motion.md#one-row-one-geometry-turned)
