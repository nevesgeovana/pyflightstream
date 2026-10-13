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

## Fixed

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
