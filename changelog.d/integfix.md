## Added

- The generated input template carries the example `inputs/pproc/p003.toml`,
  covering `[streamlines]` lines and tubes, `[[probes.lattices]]` and
  `[farfield]` with `trefftz` and `ledgers` (FR-460, FR-450).

## Changed

- FR-32: a row of the unsteady polar, `polars/P<sim>_<name>_uns_avg.csv`,
  says `reduction = time_average` and `reduction_window = averaging_window`,
  a window token appended at code 4 for the averaging window the row's
  `FIRST_STEP`, `LAST_STEP` and `STEPS` state. It carried the provenance
  cells of the native export instead: `time_average` over `not_printed` in
  0.39.0, `none` over `not_applicable` where that export printed a steady
  mode.
- FR-32: a row read from a native unsteady export, in the sweep table and in
  the super polar of an unsteady simulation, says `reduction = last_step`
  and `reduction_window = last_time_step` (codes 3 and 3), the last time
  step it states, where 0.39.0 wrote `time_average` over `not_printed`.

- PFS-2029.25 (numbered boundary names): a post-processing entry whose
  `families` cites a numbered name the run's known geometry lacks (`Blade1`
  over `Blade11` and `Blade12`) matches no recorded block for integration;
  its raw columns are kept. Over a legacy layout's cuts alone, with no known
  geometry, the family reading is kept (FR-435).
- A `--png` request without matplotlib raises `MissingExtraError` naming
  `pyflightstream[plot]` (no requirement: integration fix of the geometry
  stage's hand-written remedy).
- `minimal_workflow("26.125")` declares its one imported boundary, so its
  trailing-edge detection writes `SURFACES 1` and `1` (no requirement:
  follows PFS-2104.051).
- The export verdicts name four export commands of 0.40.0:
  `EXPORT_VOLUME_SECTION_2D_VTK` is excluded like its 3D sibling;
  `EXPORT_ALL_SURFACE_STREAMLINES`, `EXPORT_6DOF_TRAJECTORY` and
  `STABILITY_TOOLBOX_EXPORT` are owed a parser (no requirement: export
  classification).

## Fixed

- FR-68: a row stating `BLADES` equal to its rotor block's families times
  `PERIODIC_COPIES` (one meshed blade of a periodic rotor) plans again; any
  other disagreement with the block is still refused (PFS-2104.011).
- The FR-419 text in the functional requirements is valid UTF-8 again
  (it had been written double-encoded).
- FR-460: a pproc asking for surface streamlines exports them in the export
  block of the point, after the off-body analysis commands, where the
  surface-streamline export now belongs by its phase; it was emitted right
  after generation and the script was refused for an analysis command after
  the export phase.

## Migration

- FR-32: select an unsteady polar row by `reduction == "time_average"`; its
  `reduction_window` reads `averaging_window` instead of `not_printed`. A
  sweep-table or super-polar row of an unsteady simulation reads
  `last_step` over `last_time_step` instead of `time_average` over
  `not_printed`. Post again to rebuild the products; no re-run is needed.
- PFS-2029.25: an integration entry citing a numbered boundary the geometry
  lacks matches nothing; cite the family (`Blade`) or the boundaries the
  geometry carries.
