## Added

- cases.TEMPLATE_SETTINGS_LEFT_OUT and workspace.missing_log_warning are now public contracts for the post layer. (no requirement: PFS-2098.004 fix)
- On 26.125 exports, post.log now warns, once per point, that surfaces on the vorticity drag list were not judged by the declined-drag rule, so their axis drag columns are unjudged numbers. (no requirement: PFS-2085.021 fix)
- Settings table adds an f<id>_kind column to distinguish enumeration codes from list lengths. Codebook version 1 retains its existing code meanings. (no requirement: PFS-2105.042 fix)

## Changed

- An unsteady simulation with no resolvable window keeps its group polars from the last time step, now labelled kind: instant in the table entries, and post.log warns once naming the simulation. (no requirement: PFS-2105.011 fix)
- Custom polar fields now always keep a blank before each number; long values may be written with fewer decimals or digits, and a value that cannot fit raises ProductError. (no requirement: PFS-2105.012 fix)
- The inflow result is renamed InflowStationHarmonics. The old inflow_tools.StationHarmonics import warns and remains available until 1.0.0. The loads-harmonics class keeps its name. (no requirement: PFS-2089.007 fix)
- Native file lists are now relative to the products folder, matching product keys. Resolve these paths from the folder containing products.json. (no requirement: PFS-2089.001 fix)
- Sections measurement expected and emitted now list all block counts, including duplicates. (no requirement: PFS-2105.021 fix)

## Fixed

- The stale-extraction message now names the full command, pyfs-matrix post <matrix stem> --additional-pproc, which the CLI accepts; the old text omitted the matrix and was refused.
- The frozen-window message names the rotor table by the one builder of its file name, with the alias sanitised, so the file named is the file written.
- A windowed rotor row whose average cannot be made into coefficients is left out of the table with its reason stated, instead of being written.
- The J-mismatch rotor warning now compares CLOCK_MOTION with the rotor alias ignoring case, so differently cased aliases no longer raise a false warning.
- A rotor record that states no Mach now takes the simulation's Mach, or NA where none is stated, never 0.0.
- An acoustic export that cannot be read or written is now skipped per point, under acoustics/<stem>_acoustics_summary.csv in products.json, so each point keeps its own reason.
- Unsteady harmonics and disc maps now end at the last step actually written, for example after a wall-clock stop, never at the planned last step.
- For an OBJ geometry the mesh-faces warning no longer suggests --overwrite; it points to the manual route in docs/mesh-inputs.md. A saved simulation still gets --overwrite.
- Recorded polar file-name helpers now raise ProductError, not a bare ValueError, when the group is a name; pass the group number, or use swept_polar_file_name.
- read_csv_table now reports the file's own line number in errors when lines are skipped before the header.
- Acoustic tables are written at round-trip float precision instead of five decimals. Rebuild acoustic tables to recover small amplitudes and exact time samples.
- A calibration correction now also invalidates derived columns that depend on the corrected components: ETAW now includes CN and CS, and THRUST, TORQUE and the rotor-state columns read NA unless their source forces are stated.
- read_custom_polar_format now raises ProductError naming the line for non-numeric values, a bad reference count, or non-ASCII bytes, instead of a bare ValueError or UnicodeDecodeError.
- The generated input glossary page keeps the line endings the page already has, so a CRLF checkout is no longer rewritten with mixed endings on every plan or post.
- Mirroring an installed-frame table now also flips YMOM and every *_PHASE_DEG column. Rebuild installed-frame copies from their source tables.
- Blade-view harmonics refuse a negative X rotor axis; specify positive X and signed omega.
- Probe fields, reductions and the probe table now read the Time-step clock through one reader; native fields are refused unless their steps are finite, whole and strictly increasing.
- At nonpositive free-stream velocity, plots coefficient columns read NA and post warns; physical forces remain exported values.
- write_probe_field and write_recorded_probe_fields test every destination first, so an existing file refuses before anything is written, not after a partial set.
- products.json is now written atomically, and an interrupted write leaves no truncated file; a cut-off manifest is named with its remedy (post again without --sims) instead of a bare JSON error.
- An unknown matrix stem is refused before post/<stem>/ or its log files are created.
- Section radii and torque arms are now measured from the hub for geometry-frame cuts. K_1P reads NA, with a warning, where the recorded frame and hub cannot place the station.
- A clocking export without a positive reference velocity is now skipped with its reason named, instead of being read at the free-stream velocity.
- The rotor table's ETAW sign is now fixed once per rotor against body +x, so it no longer flips between alpha -2 and +2 for a shaft square to the stream.
- Rotor table rows that state no ALPHA or BETA now write NA for shaft angle and ETAW, with a warning, instead of assuming level flight.
- A rotor row whose loads export states an unrecognised analysis frame is now refused with the frame named, and static points warn that rotor coefficients except J read NA.
- Warnings raised by the pproc builder while matching section distributions no longer appear in post output.
- Section-distribution tables now keep only stamped files inside the record's export window; files outside it are named in skipped.
- The sections series steps_tabled now lists only steps that produced rows; a step whose export declared no sections is no longer listed.
- The wide settings table no longer carries the fill sentinel in f<id>_value; a list-valued flag keeps its length, not 999.
- average_surface_exports now raises ProductError when the window ends before it starts, instead of failing later on an empty range.
- write_surface_average now tests both destinations first, so an existing file raises ProductExistsError before either the Tecplot or VTK file is written.
- Integrated tip Strip_length, Fx_int, Fz_int and My_int increase by the missing half strip; rebuild post products.

## Migration

- An unsteady simulation with no resolvable window keeps its group polars from the last time step, now labelled kind: instant in the table entries, and post.log warns once naming the simulation.
- Recorded polar file-name helpers now raise ProductError, not a bare ValueError, when the group is a name; pass the group number, or use swept_polar_file_name.
- Acoustic tables are written at round-trip float precision instead of five decimals. Rebuild acoustic tables to recover small amplitudes and exact time samples.
- A calibration correction now also invalidates derived columns that depend on the corrected components: ETAW now includes CN and CS, and THRUST, TORQUE and the rotor-state columns read NA unless their source forces are stated.
- read_custom_polar_format now raises ProductError naming the line for non-numeric values, a bad reference count, or non-ASCII bytes, instead of a bare ValueError or UnicodeDecodeError.
- Custom polar fields now always keep a blank before each number; long values may be written with fewer decimals or digits, and a value that cannot fit raises ProductError.
- The inflow result is renamed InflowStationHarmonics. The old inflow_tools.StationHarmonics import warns and remains available until 1.0.0. The loads-harmonics class keeps its name.
- Mirroring an installed-frame table now also flips YMOM and every *_PHASE_DEG column. Rebuild installed-frame copies from their source tables.
- Blade-view harmonics refuse a negative X rotor axis; specify positive X and signed omega.
- cases.TEMPLATE_SETTINGS_LEFT_OUT and workspace.missing_log_warning are now public contracts for the post layer.
- Probe fields, reductions and the probe table now read the Time-step clock through one reader; native fields are refused unless their steps are finite, whole and strictly increasing.
- At nonpositive free-stream velocity, plots coefficient columns read NA and post warns; physical forces remain exported values.
- Section radii and torque arms are now measured from the hub for geometry-frame cuts. K_1P reads NA, with a warning, where the recorded frame and hub cannot place the station.
- The rotor table's ETAW sign is now fixed once per rotor against body +x, so it no longer flips between alpha -2 and +2 for a shaft square to the stream.
- Rotor table rows that state no ALPHA or BETA now write NA for shaft angle and ETAW, with a warning, instead of assuming level flight.
- A rotor row whose loads export states an unrecognised analysis frame is now refused with the frame named, and static points warn that rotor coefficients except J read NA.
- Native file lists are now relative to the products folder, matching product keys. Resolve these paths from the folder containing products.json.
- The wide settings table no longer carries the fill sentinel in f<id>_value; a list-valued flag keeps its length, not 999.
- Settings table adds an f<id>_kind column to distinguish enumeration codes from list lengths. Codebook version 1 retains its existing code meanings.
- Sections measurement expected and emitted now list all block counts, including duplicates.
- average_surface_exports now raises ProductError when the window ends before it starts, instead of failing later on an empty range.
- Integrated tip Strip_length, Fx_int, Fz_int and My_int increase by the missing half strip; rebuild post products.
