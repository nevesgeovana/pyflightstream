## Added

- A setup key `delete_surfaces` removes surfaces by name, alias or family with `DELETE_SURFACES` after the geometry opens, and the script's inventory and the run record's inventory are renumbered as the solver renumbers (FR-275, FR-276). See `docs/removing-surfaces.md`.
- A setup key `slipstream_wake_stabilization` emits `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION`, ENABLE or DISABLE, for each rotor motion of the row (FR-277).
- A stated `delete_surfaces` or `slipstream_wake_stabilization` that reaches no surface or no rotor motion is refused, naming the key (FR-278).
- `DELETE_SURFACES` and `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` carry their 26.124 probe evidence in the command database, still documented and not promoted (FR-279).

## Changed

- `slipstream_wake_stabilization` is no longer a recorded-only setup key: it reaches the script (FR-277).

## Migration

- A setup that states `slipstream_wake_stabilization` no longer gets the recorded-only warning; the value is emitted for each rotor motion, and an ENABLE on a row that states no blade count is now refused (FR-277).
