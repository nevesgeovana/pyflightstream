## Added
- `pyfs-workspace init` and `migrate-geometries` accept `--workspace PATH`, as every other subcommand but `archive` does; their positional root still works, and two different folders are refused (no requirement: PFS-2089.004 fix).
- A refinement file that selects a family with no `[families.<name>]` table warns, naming the family and the remedy, and `refine.json` records it under `missing_families_tables` (no requirement: PFS-2089.003 fix).

## Changed
- Workspace storage and batch commands read one end rule for a grouped job: the end record, the job log, every `job_end_files` glob, or a point whose wall-clock state says it fired; delete-sims, free-space and sync now treat a clock-stopped batch as ended, as collect does (no requirement: PFS-2094.041, PFS-2094.044 fix).
- Sync and free-space share one log-name rule: `FS_runtime_output.txt`, `FlightStreamLog.txt`, `*_log.txt`, `*-log.txt` and `*.log`, in any case (no requirement: PFS-2087.002 fix).
- `ledger diff` normalises each executed script against its own run root and words a changed command as `a ...` and `b ...` (no requirement: PFS-2103.013 fix).
- `show` reads only the end of an evidence file and reports a binary file by size and sha256 (no requirement: PFS-2101.004 fix).
- `log --sims 20` no longer selects simulation `20-b`; a row's own `sim_id` or `sims` decides before its text (no requirement: PFS-2094.043 fix).
- A thin blade's rows all run from the leading edge, and a blunt trailing edge ends the mean line at the midpoint of its base (no requirement: PFS-2099.001, PFS-2099.002 fix).
- A thin blade cut from a multi-body OBJ carries only the mesh operations that act on it, and names the ones left out in its sidecar (no requirement: PFS-2099.003, PFS-2099.013 fix).
- Refined meshes order faces within one source face by vertex index, then distance, so a millimetre mesh orders as a metre one does, and a one-row or one-column grid is written in the source's own run (no requirement: PFS-2099.019, PFS-2099.018 fix).

## Fixed
- `pyfs-workspace init` on a bad root prints the refusal and exits 2 (PFS-2095.059).
- Staging replaces a dangling inputs link, every link removal falls back to a copy, a failed archive leaves no fragment, and collection names files by `collection_name` (PFS-2095.056, PFS-2095.062, PFS-2096.010, PFS-2094.042).
- `--cost-file` and `--hpc` end with the command that set them (PFS-2094.045).
- A cost flag counts only when its row value is True or ENABLE (PFS-2094.046).
- The cost file refuses a zero, negative, text or non-finite reference figure or curve entry, naming the table and key (PFS-2097.019).
- An encrypted or damaged workbook, and a short bridge record, are refused as `ExcelSyncError` (PFS-2095.060).
- Excel sync strips the MATRIX and POL cells, so `1001 ` no longer appends a duplicate row (PFS-2096.025).
- A reference artifact's `[frames]` table or non-list aliases are refused by name (PFS-2095.058).
- A manifest row whose `points_ran` entry has an unknown status or a non-text tag is unreadable when read (PFS-2093.005).
- POL renumbering counts compacted `sim_<id>.zip` and batch simulations as taken (PFS-2085.020).
- `rename_group_products` and `unmapped_group_numbers` read only products under `post/`, never links (PFS-2096.012).
- `write_inventory` quotes boundary names and the file name as TOML strings (PFS-2095.034).
- A free-space recipe is checked whole before its first step: unknown keys, shapes, statuses, extensions, actions and `keep_latest` are refused naming the recipe and table (PFS-2093.007, PFS-2096.028, PFS-2097.020).
- Sync refusals name the keyword `source (CLI: --from)` (PFS-2100.018).
- Trailing-edge extraction accepts a numpy integer section count (PFS-2095.061).
- A job-end glob that cannot be formatted with the job's values warns instead of keeping the batch running silently (PFS-2094.050).
- Cleaning a held saved simulation is refused naming the file and leaves no temporary file (PFS-2099.012).
- The ledger query readers raise `WorkspaceError`, as documented (PFS-2095.028).
- `ledger diff` finds a recorded script under its simulation folder (PFS-2103.039).
- A torn or malformed activity line, or a non-ISO timestamp, is skipped with a warning naming it (PFS-2081.25).
- A point card lists only its own archives (PFS-2094.020).
- A flat rotor row with a named `ROTOR_ORIGIN` keeps its row-setup keys out of the variables (PFS-2095.029).
- A refinement table stating only `keep_first_row` names the fix (PFS-2093.013).
- A refinement or trailing-edge points file that is not UTF-8 is refused (PFS-2099.004).
- An empty family selection is refused before anything is written (PFS-2099.005).

## Migration
- The ledger query readers (`activity_rows`, `additional_rows`, `post_log_groups`, `point_card`) raise `WorkspaceError`, a `RuntimeError`, where they raised `ValueError`; catch `PyflightstreamError` (PFS-2095.028).
- A cost flag set in a row by `1`, `ON` or `true` no longer applies its multiplier; write `ENABLE` (PFS-2094.046).
- A free-space recipe with a misspelt key, a string `status`, or a negative or fractional `keep_latest` is refused before any file is touched; correct the recipe (PFS-2093.007, PFS-2097.020).
- A manifest row whose `points_ran` holds an unknown status is reported as unreadable when the manifest is read (PFS-2093.005).
- Refined meshes in large length units, and one-row or one-column grids, may list their faces in a different order than 0.39.0 wrote them; FlightStream results can depend on face order, so regenerate a level before comparing it with an earlier one (PFS-2099.019, PFS-2099.018).
- A thin blade derived from a blunt trailing edge ends at the base midpoint, not at one corner (PFS-2099.002).
