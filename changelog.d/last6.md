PFS-2084.004, PFS-2084.005, PFS-2094.040, PFS-2100.019, PFS-2104.032, PFS-2104.035

- Script.park_input_file applies the shared case-insensitive collision rule.
  Script.observe_commands records accepted emissions within a scope; cases use
  these public APIs and Script.entry instead of private builder state.
- Restart records have declared ExportThresholdRecord and StoppedStepRecord
  types. The persisted export_window key remains compatible.
- Matrix selection precedes build and artifact resolution; excluded rows do
  not refuse a missing default build or change the selected run's HIDDEN mode.
- Run, post, collect and regeneration overwrite products without an archive by
  default. collect --archive and delete-sims --archive preserve replaced products.
  post --force-overwrite explicitly selects no archive and still confirms it.
- Continued per-step exports record their predecessor step_offset and local
  first_step. LAST and AFTER thresholds reach the continued march's counter;
  thresholds in the span already run, or unprovable predecessor counts, refuse
  at plan. Additional marches resolve LAST windows against their new end.
