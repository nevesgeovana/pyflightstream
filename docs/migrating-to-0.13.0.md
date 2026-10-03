# Migrating to 0.13.0

> Historical record assembled at 0.36.0 from the reference pages; frozen from now on.

## Historical row-key changes

- v0.13.0: `EXPORT_UNSTEADY_AFTER_REV` and `EXPORT_UNSTEADY_AFTER_ITER`, the step the per-step exports begin on, one per row at most; the first on `unsteady_rotor` only, both refused on `steady` (PFS-2031.18)
- v0.13.0: none. What changed is that the list above is now CLOSED for a workflow row: a key no run type registers is refused at `pyfs-matrix plan` (PFS-2008.02.01), see below
