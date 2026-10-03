# Migrating to 0.19.0

> Frozen record: not edited after its release.

## Historical row-key changes

- v0.19.0: `TRANSLATE`, a list of records, one translation of the opened mesh each, in the order written and before every rotation: `TRANSLATE: {DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}, {...}`; on every run type that reads `ROTATE`, the distance in metres along one axis of the named frame (FR-100), see [One row, one geometry, moved](workflow-row-geometry-motion.md#one-row-one-geometry-moved)
