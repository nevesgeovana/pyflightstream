# Migrating to 0.11.0

> Frozen record: not edited after its release.

## Historical row-key changes

- v0.11.0: `MOTIONS`, a list of records, one rotor each: `MOTIONS: {MOVING_BOUNDARIES: Blade1 / RPM: 1200 / RPM_SIGN: 1 / ROTOR_AXIS: X / ROTOR_ORIGIN: ERP1}, {...}`; a record's `ROTOR_ORIGIN` is three coordinates or the name of a rotor point of `inputs/reference_points.toml`, and no flat motion key may stand beside the list (PFS-2029.11)
- v0.11.0: `BASE_REGIONS`, the boundaries that BECOME base regions, one `DETECT_BASE_REGIONS_BY_SURFACE` per boundary of them after `OPEN`: a body's flat base (`BASE_REGIONS: Base`), never the body that carries it, which the command takes and marks nothing on, silently (stated RPT-066; see below). It overrides the pproc artifact's `base_regions`, and naming none emits nothing (PFS-2029.10)
