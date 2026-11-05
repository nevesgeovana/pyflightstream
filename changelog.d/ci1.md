### CI integration corrections

- Rotor section modules load on lean installations. Surface matching requires
  SciPy only when requested and names the missing dependency in a package error.
- Blade-order and rotor-section refusals use package errors and retain their
  ValueError base. Repitch and far-field warnings declare their package category.
- Shared wake arithmetic and reference dynamic pressure have internal homes;
  the wheel symmetry measurement is named for its returned result.
- The public module inventory, docstrings, dimensionless chord-fraction entry,
  input-template omissions and exact repitch hash representation are declared.
- The retained single-sheet wake crossing Python API is recorded separately
  from the workspace's multiple-sheet route.
- Product snapshots reflect FR-1062's polar stage following far-field projection.
  Only JSON manifest key order changes: every parsed JSON field and every other
  product byte is unchanged, including archived manifests.

Migration: no new numerical or input-format change. Code catching ValueError
continues to catch these input refusals. Submitted-point reruns require the
existing explicit `redo_submitted=True`; the old scheduler job is not cancelled.
