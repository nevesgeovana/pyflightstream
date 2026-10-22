# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [Unreleased]

### Added

- `pyfs-fsi` writes `fsi_convergence_verdicts.log` in the run folder, and the external step
  record carries `loads_file_present`. An external call that finds no loads file in the point
  folder fails before the program runs.
- A row that states no `ALPHA` or `BETA` flies that angle at 0.0 and says so: the plan summary
  shows `ALPHA = 0.0 (default)`, and the run record lists the angles in `angles_not_stated`.
- `[products] trimmed_polar = true` on a pproc artifact writes, beside every polar table,
  `<polar stem>_trim.csv`: the polar's row at zero pitching moment (`CMB25`), interpolated
  between the two points that bracket it and never extrapolated. A polar whose sampled
  moments do not change sign, or change sign more than once, is named under `skipped`.
  `pyflightstream.post.write_trimmed_polar` writes the same file from any polar table.
- A `[refinement]` table on a pproc artifact declares a three-level refinement study (mesh
  levels or time steps, finest first); the post writes `polars/GCI-P<finest>_g<group>.csv`
  with the observed order, the Richardson extrapolation, the grid convergence index and the
  numerical uncertainty of every coefficient of every point. `pyflightstream.post.polar.grid_convergence`
  computes one estimate.
- `pyfs-workspace` commands take `--log-level` and `--verbose`, as `pyfs-matrix` does; a level
  typed there wins over the `[log] console` of `pyfs.local.toml` and `pyfs.toml`. The geometry
  verbs `refine`, `audit`, `inventory` and `degenerate` take them too, and so do their
  `pyfs-matrix` twins, whose options they keep exactly.

### Changed

- `pyfs-qa physics` runs the physics cases the selected build supports and reports each case it
  cannot run as INAPPLICABLE with its reason; the Markdown report summary states how many cases
  ran and how many were left out (`PhysicsRun.ran_count`, `PhysicsRun.inapplicable_count`).
- A grouped job that runs on this machine and states no `WALLTIME` and no `timeout_s` takes the
  HPC profile's `max_walltime` with a warning; the plan refuses it, naming `WALLTIME` and
  `timeout_s`, when the profile has none. It is never unbounded.
- An unsteady averaging window longer than the run is still cut to the whole run, and the
  window record now carries the span the row asked for (`ExportWindow.clipped_from_steps`).
- The public writers of `pyflightstream.post` that lacked it take `overwrite` (`True` by default,
  as they always replaced a file); `overwrite=False` refuses an existing file with
  `ProductExistsError`. The campaign writer is unchanged.
- A `ROTOR_AXIS` cell that disagrees with the axis of the single rotor block, and a `VELOCITY`
  cell that contradicts the velocity the row already resolves, are refused before any script is
  written, naming the cell and the resolved value. The `VELOCITY` case was a warning.
- A `--matrix` value loses only its final extension: `wing.v2.fs` and `wing.v2.toml` name the
  matrix `wing.v2`, and a bare `wing.v2` is no longer cut to `wing`.
- `HpcProfile.defaults` is removed. A profile that still carries a `[defaults]` block loads with
  a warning that the block is ignored.
- Only `c<digits>.toml` is a cost file: any other `c*.toml` in `inputs/costs/` is refused,
  naming the file and the pattern. A name given to `select_cost_file` loses only a final `.toml`.
- The wake-edge type has no default: a `[trailing_edges]` table with `file` and no `type`, and
  a `WakeEdgeImport` without `edge_type`, are refused naming VORTEX_SHEDDING and STANDARD.
  Sidecars written by the geometry converter now carry `type = "STANDARD"`.
- The refusal of an artifact id with a space, a bracket or another character outside letters,
  digits, `.`, `_` and `-` names the character and suggests the renamed id.
- `pyfs-matrix mark-converged` without `--apply` exits 2 when its preview holds a refused
  point, as `--apply` does; a preview without refusals still exits 0.
- Altitude and compatibility reports state that they analyse retained evidence, not probe
  harness output. The loft geometry digest printed in compatibility reports is now a SHA-256
  prefix, so digests in reports written before this change are not comparable.
- The `pyfs-matrix` install check is documented as `--help`, and the guide and documentation
  pages state what the code does.
- `pyflightstream.testing.assert_records_close` counts a NaN on either side, both sides
  included, as a violation, as its rule `|a - e| <= atol + rtol * |e|` reads: a golden that
  holds NaN no longer passes.
- The QA `--timeout` option keeps its behaviour, and its help states the limit each solved
  probe keeps: 180 s for a solving probe of the gap catalog, 240 s for a solving probe that
  carries it, and 60 s for the hang guards of build 26.125.
- FSI node and displacement inputs refuse what they would misread: non-finite values, a node
  clearance that rounds away and a path-like external manifest name. NACA names are four
  digits. The displacement reader accepts a byte-order mark and returns an empty `(0, 3)`
  array for an empty file.
- Probe controls capture the before state reliably and export each loft immediately before
  removing it. Applied-twist convergence, revolution history validation and the provenance of
  the actual external call are checked, and a failed UTF-8 call is archived.
- The withheld executable identity names the build the binary printed.
- A rotor whose recorded steps per revolution is infinite is a named skip of the harmonics
  product instead of aborting the point, and `last_complete_revolution` refuses a clock that is
  not finite with `ProductError`.
- Thin blade: unused vertices of the implicit group are ignored, an offset that leaves no
  section is refused, the chord ends are the exact farthest pair and OBJ vertices keep full
  precision. `torsion_constant` accepts numpy integers.
- Simulation archives record a file link as `<name>.LINK.txt` and never store the bytes it
  points at. A cloud-backed placeholder is not a link.
- `history` reports one corrupt archive as one identified row and no longer hides the readable
  records. Actuator profiles serialise the provenance record before the profile is written,
  the last station is the tip and a product key with parent segments is not read. A cost file
  flag multiplier must be positive.
- `pyflightstream.post.qsteady.clockings_of` and `mean_clocking_surfaces` raise `ProductError`
  naming the clocking and the reason when a clocking cannot be read, instead of returning the
  reason as a string in place of the result. Migration: catch `ProductError` where the code
  tested the result with `isinstance(result, str)`.
- The per-point quasi-steady validity file is written only for a point whose loads export is
  on disk, and a file already there is replaced only by a post called with `overwrite=True`
  (which `pyfs-matrix post` passes, archiving the old file with `--archive`); otherwise it is
  left in place and the point is named under `skipped`.
- An unexpected failure in one post product (an error that is not a package refusal) costs
  only that product: it is named under `skipped` with its type and message, and the
  independent products of the simulation and of its points are still written and indexed,
  instead of the failure ending the whole post.
- The rotor-coefficients definition of a static point now states what the rotor table
  does: coefficients are taken back to loads with the reference dynamic pressure
  `rho VREF^2 / 2`, so a static point with a positive `VREF` has `CT`, `CQ` and `CP`, and
  only a zero or unstated `VREF` reads `NA`; `VREF` also sets the Reynolds number in hover.
- `pyfs-manual draft --write` refuses an `--out` file that already exists unless `--force`
  is given; the refusal comes before the manual is read and leaves the file unchanged.
- The `--cost` table of `pyfs-matrix plan` never shortens a run id: its point column widens
  to the longest id, so two points whose ids differ only in the simulation part no longer
  print alike.
- A grouped job run with `--local` and no `WALLTIME` is limited by the solver `timeout_s` of
  its cases (the largest of them for each of its points) instead of running with no limit,
  and the grouped plan states the limit of every job without a walltime.
- `WorkflowConventions(animation_folder=...)` stays accepted and warns that it has no
  effect: no workflow writes animation frames into it.
- The probe positions file a run writes (`sims/<sim>/profiles/<sim>_probe_points.csv`) starts
  with the line `# pyflightstream probe positions`, and the run replaces only a file that
  starts with it: a file of your own with the same name and header is refused instead of
  overwritten. A file in the earlier layout (header first) is replaced once with a warning.
- On build 26.123, `TRAILING_EDGES_IMPORT` is refused as removed, citing the page of the
  26.123 edition that stops printing it, and names `IMPORT_WAKE_EDGES_FROM_FILE`, instead of
  being refused as a command with no evidence.
- On build 26.121, `SET_MOTION_START_TIME` is emitted as the edition documents it; it was
  refused as broken on a probe abort whose cause was the probe's own rotary motion.

### Fixed

- The refusal of an angle of attack or sideslip under `SYMMETRY PERIODIC` stays and states why:
  on 26.124 and 26.125 the solver solves an angle of attack there and silently resets a
  sideslip to 0.
- The `DELETE_ACOUSTIC_OBSERVER` probe of `pyfs-qa` requires the second observer to be the one
  left after deleting index 1, so deleting the wrong observer no longer reads as a deletion.
- The `SET_INVISCID_LOADS` probe of `pyfs-qa` judges the viscous drag column (field 6, named
  `CDo` on 26.124 and `CDv` on 26.125) only once the sheet header names it, so a sheet whose
  sixth column is another quantity is no longer verified or broken by it.
- The `DELETE_VOLUME_SECTION` probe of `pyfs-qa` exports the survivor at its new index 1 and
  identifies it by its offset, where it exported index 2, which the solver refuses after a
  deletion and which aborted the probe script.
- The wake-termination detection emits `AUTO_DETECT_WAKE_TERMINATION_NODES` on build 26.125 as
  on the other builds: both builds then give the same lift, where the by-surface `-1` form
  marked no node and lowered the 26.125 lift by about 5 percent. The command database carries a
  26.125 row for it.
- `read_timestep_series` numbers its frames from solver step 1 (the step axis is 1 plus the
  frame index times the frequency), as the solver writes animation frames: the first frame is
  step 1, and a frequency of 2 writes steps 1, 3 and 5. Windows read against it move with it.
- Reading and cleaning the unsteady solver actions saved in a geometry counts a command's
  length in bytes, as the solver saves it, so a saved action whose command holds a non-ASCII
  character is read instead of refusing the geometry.
- A probe drawn after an imported survey is numbered after the survey's points, as the solver
  numbers them (imported and drawn probes share one id space), and the survey's points are
  recorded under their ids.
- Build-all guide scripts exit 1 when the selector matches no guide.
- Geometry build treats a failed final overlay replace as a build error, records the sidecars
  it reads as inputs, honours the memory floor at each variant start and refuses an unreadable
  trailing-edge readback. `geometry accept` refuses a malformed record without stamping any
  and a partial folder name with a trailing separator. `geometry clean` never overwrites an
  existing backup, and `geometry from-sidecar` resolves `folder/name`, refuses a missing CAD
  or CCS sidecar and writes names that read back unchanged.
- `free-space` no longer fails an apply after files were deleted when `products.json` has the
  wrong shape, and its preview lists each file once.
- `delete-sims` treats a single id given as a string as one simulation, refuses product paths
  that leave the post folder (also through a linked folder), and restore never extracts
  through a planted staging link.
- Batch relocation refuses overlapping source and destination folders and a destination
  reached through a link, and a failed copy or move keeps the published file whole.
- `sync` at the `all` level brings the files of a job folder's subfolders.
- `free-space` keeps the staged inputs a record names by digest, and compacting a post archive
  never overwrites an existing archive.
- `history` and the product trace name the record that made an indexed product, not a later
  continuation of its point.
- The thin blade mesh and its sidecar are both prepared before either is written.
- A geometry rebuild stops on an unreadable retained sidecar instead of dropping its settings,
  and every string of the instruction `geometry from-sidecar` writes reads back unchanged.
- A `kind` key inside `[moment_point]` no longer reroutes the table.
- FSI refuses a revolution increment that is not positive and finite and non-finite inputs to
  the force closure and the load cross-check; the dummy step reports an unreadable
  `node_count` in its error log.
- `pyfs-qa probe` records a token the dump held before the target as unobservable, and a log
  without its BEGIN or END sentinel as unprobed rather than broken.
- Reading compatibility evidence (`read_compat_reports`, `apply_reanalysis`,
  `record_unprobed_build`, `cost_view`, `WingSpec`) refuses malformed input with
  `QaEvidenceError` instead of `AttributeError` or `KeyError`, and `WingSpec` refuses nan and
  inf lengths.
- `read_timestep_series` refuses irregular or duplicated solution times, non-finite times or
  coordinates, frames whose sample moves and a VTK POINTS record without a count, and refuses a
  frequency below 1 or an unknown order with `ProductError`. `per_blade` and `phase_locked`
  assign each column to its longest matching family suffix, and `phase_locked` takes
  REVOLUTIONS as the fewest samples of any column of the row.
- Far-field coverage in the ledger and the Trefftz plane is a fraction of area
  (`sample_area_coverage`); `sample_coverage` still counts samples.
- Sectional products of a point whose saved simulation is not in metres are not written, and a
  named skip says so; the additional post gains the skip reason `NO_SECTIONS_LAYOUT`.
- The probe points reader refuses a table with more rows than declared and reports fewer as
  incomplete, a sectional loads export printed twice is refused, and the residual history
  table gains `velocity_overflowed` and `pressure_overflowed`.
- A missing cell of every table `write_table` and `to_csv` write, the campaign sweep table
  included, is written as the NA token, not an empty field.
- `show` lists the outcome first and the record last; `diff` names the input a changed script
  line comes from; a rebuild refusal names every changed line; `history` reports an unreadable
  zip as an error row; `trace` refuses provenance outside the workspace.
- Reference point names such as `ERP01` and zero padded names are refused, and the point gap
  message lists at most 8 points; a fractional `STEP`, a non-positive CT tip radius and a
  two-station Betz-Prandtl profile are refused, the last with its remedy.
- The workspace reads a Windows reparse point that is not a symbolic link or a junction (a
  cloud-backed file) as the regular file it is.
- Output and manifest names with a drive, a colon, a control character or a reserved Windows
  device name are refused where names are rendered; a dangling link is not a free archive
  path. `Ledger.status` and `Ledger.points` refuse a status word no status takes.
- Storage TOML and JSON files that cannot be read are refused by path, a malformed storage
  register raises `StorageError`, `delete-sims` archives `products.json` before rewriting it,
  and restoring an archive whose hash table names a missing member raises `StorageError`; an
  archive without a hash table warns that nothing is verified.
- A `job_end_files` glob that starts at a root or a drive is refused where it is written, a
  dotted HPC profile name can be selected, a limit written under `[submit]` is an error
  instead of being dropped, and a string for `outputs` or `boundaries` of a geometry
  instruction is refused.
- Cost files: a NaN or non-positive processor count and an undefined size no longer give a
  finite or negative estimate, and a repeated flag multiplies once.
- Reference artifacts refuse NaN and infinite coordinates and divisors, and two folders that
  derive one mesh file name are refused by name.
- `write_script` refuses a name that is not a plain file name, `read_manifest` and
  `GroupingReceipt.from_json` raise `WorkspaceError`, `Preview` refuses a path that holds a
  file that is not a preview, and a recorded-only key is never applied.
- The mesh audit judges warp and growth against the larger of the source's value and the
  floor, a closed shell split over several families is judged on the whole mesh, a missing
  family fails G5, and the last line of the summary states how many checks were not judged.
- `refine` refuses an OBJ that is not UTF-8 and a file in the place of the level folder, and
  its refusals offer valid TOML for a value they cannot rewrite.
- `field time-mean --vinf` refuses non-finite and non-positive values, field provenance holds
  workspace-relative paths with sorted keys, a sidecar suffix is a dot and a plain name, and a
  pinned pressure beside a Reynolds number earns the `p = rho R T` warning.
- A corrupt `additional.json` raises `WorkspaceError`; `pyfs-workspace migrate` converts an
  empty named manifest and refuses a symbolic-link backup; the Excel workbook reader reads
  boolean cells as TRUE and FALSE and refuses an error cell by address; a workbook digest
  ignores save time stamps.
- A declined value is stated as NA in more tables: the custom polar, series, reduction, inflow
  and installed-frame tables write NA, the readers take NA (and the historical dash) back as
  missing, and the custom polar header refuses a character outside ASCII by naming its line.
- The VTK and Tecplot probe writers refuse NaN and infinite values, an empty point set, repeated
  variable names and names, titles or zones that hold a blank, quote or line break (all
  `ProductError`, still a `ValueError`); they create their destination folder, write portable
  JSON for a non-finite sampling value, and `write_output_pair` withdraws the data file when its
  record cannot be written. An existing destination is one class for every writer.
- The settings table reader and writer hold to the frozen codebook: keys may arrive in any
  insertion order, a non-finite number or a repeated header label is refused, and a table from
  another codebook version is named.
- Post products name what they skip: a coupling history, an unreadable loads, sectional or probe
  export, a rotor in two planes, a non-finite clock or speed, and a simulation whose step cannot
  re-resolve each cost only themselves and are said once in `post.log`.
- Noise, structure and boundary-layer tables open with POL and the condition block; noise
  products are per observer, harmonics use the recorded blade count, and a constant record has no
  level.
- Disc maps refuse two rotors that share a file name, keep six significant digits for VALUE and
  keep a tiny negative azimuth below 360; per_blade STEPS counts the frames that entered the
  average.
- The reference check holds to the export's printed precision and says how coarsely a small
  model could be checked; a backwards recorded window is no window.
- Far-field tables: the wake calibration and E_T use the lift on one dynamic pressure basis,
  spanwise tables carry the condition and reference block, a plane refuses an empty selection,
  the window average needs the whole window, and the continuation join keeps an exact seam and
  the march end. Bessel and Theodorsen functions hold at the float extremes.
- Rotor tables and noise: false zeros are refused, a negative speed or zero shaft axis gives NA
  loads, zero density is a `ProductError`, subsonic moving rotors are accepted, comparisons
  stay finite at extreme scales, and the quasi-steady noise model refuses what it would drop.
  MADV is computed for a row that states no ALPHA or BETA, the angle taken as 0.0 (FR-69).
- Products: a wrong-shape `products.json` is refused with a remedy and a rebuild keeps the old
  inventory until replaced; provenance files are never shared between runs; the far-field
  columns BERNOULLI_RESIDUAL, W_M_S, GAMMA_M2_S, DI_N_M and ALPHA_I_DEG print six significant
  digits; the spanwise file name is made safe.
- Cases and workflows: an empty sweep axis, a held angle on an alpha_beta sweep, a non-finite
  rotation angle or free-stream speed, a negative rotor speed handed to a builder, a non-finite
  walltime margin and a rotor speed that differs from the row's are refused; a changed section
  definition in a grouped job is refused, shell paths with spaces are quoted, and the counter
  program refuses a corrupt count checkpoint and a foreign schedule. A row's `RPM_SIGN` beside
  a declared rotor block is accepted when it equals the block's hand and refused only when it
  disagrees.
- Matrix and setup files: a malformed matrix id is refused, GEOMETRY is a file name with its
  extension everywhere it is documented, direct `INITIALIZE_SOLVER` refuses periodic-copy mismatches and non-finite
  wake terminations, selections accept ALL, `SET_FREESTREAM` refuses another form's arguments,
  a parked input may not be a folder or device name, and airfoil separation on 26.125 takes
  `leading_edge_type`.
- Workspace files: a field stem Windows reads as another file, a trailing-edge points file that
  is not beside its sidecar, a frozen displacement file outside the FSI folder and a superscript
  digit POL are refused or named; `migrate` publishes its backup whole and no longer asks a user
  with another schema version to run itself.
- Field, motion and pproc inputs: a near-unit rotation axis is normalised, a constant rotation
  without a motion index is refused, a custom field file that is not UTF-8 is refused by name
  (a byte order mark is read), the field hash describes the bytes the rows came from, two plot
  groups writing one name are refused, and a pproc dump of groups and circle volume sections
  reads back.
- The input glossary states no solver command the package never emits, and its guides and
  defaults are placed and quoted as TOML.
- Result readers: a second export cut before its footer, a bare numeric unsteady table, a
  second table after the closing rule, repeated VTK or wake blocks, non-finite VTK and wake
  values, an unknown loads flag, undeclared probe rows and a file of separators are refused;
  residual columns follow the header names; the freeze detector reads spaced (k/N) markers,
  lists an interior step without a page as unjudged and diagnoses malformed residual cells;
  a wake line starting downstream, a malformed wake line and oversized wake tokens are named,
  and the wake constant-line tolerance is the line's own. `write_table` creates its file
  exclusively and raises `ProductExistsError`, and `loads_file` accepts a recorded path.
- Far field: the Trefftz trace no longer returns NaN for a zero-strength filament, refuses a
  trace point on a nonzero shed filament, coincident trace points and a wake whose strengths
  do not sum to zero; `symmetry_floor` refuses `m_max=0`; rotor coverage counts v, w and
  p_prime; the atmosphere refuses non-finite inputs; the far-field functions refuse
  malformed shapes, non-finite samples and invalid densities by name; `lateral_flux` refuses an
  outlet upstream of its inlet instead of returning 0.0.
- Probes: a lateral cylinder inside the outer ring edge, a non-(n, 3) points array, a probe
  layout count that divides by zero, an infinite extent and a lateral station list without a
  radius are refused; a geometric axis can neither overflow nor coincide; frames keep huge
  axes and a stored frame survives the JSON round trip exactly.
- Script helpers refuse a string row read as coordinates, actuator disc radii that enclose no
  area, a boolean swirl, a wake stabilization count below one, an unsteady regime that cannot
  advance in time, an empty `vtk_boundaries`, a `probe_line` with fewer than one point, a
  `coordinate_frame` origin that is not three numbers and a separation-model diameter that is
  not positive; an array is judged as a selection, not compared with `"all"`.
- FSI and structure: the dummy step refuses a node count below one and archives the solver's
  node list, a failed archive is an error-logged failure, swapped major and minor inertia
  lists are refused, and a material suitability note is kept in the provenance. Generated
  blades from materials with a note now carry `provenance.material.notes`, so their
  `config_sha256` changes; configs from materials with an empty note are unchanged.
- QA and physics: reference bands refuse inverted widths, unknown kinds and non-finite
  numbers; the physics pre-flight refuses a case the build has no evidence for and a matrix
  naming no case before a seat is spent; the physics YAML says `not recorded` for a run that
  took no digest; a withdrawal report without detail and a report without a build are
  `QaEvidenceError`; summaries count aborted cases; blade and wing end caps no longer face
  inward; the loft reference is exported before the second loft.
- Run layer: a collect sweep survives one simulation that cannot be expanded, retries a file
  error while completing an extraction and drops a point collected in a later sweep from the
  failed total; a submitted extraction keeps an earlier archive written in the same second;
  a profile placeholder an extraction cannot fill is a refusal; a crashed or timed-out local
  grouped job fails the run; `collect --watch-interval` refuses zero, negative and non-finite
  values with exit 2; `status --csv` keeps full float precision; `log --sims` takes
  blank-separated ids; a continuation refuses a replaced saved state; a relative `fs_exe`
  is resolved; descriptor strings are escaped in TOML and YAML; `reconstruct` expands a
  compacted simulation first; a rewritten point script keeps the replaced bytes under
  `scripts/archive/`; a live scheduler log is no proof that an extraction job ended.
- Removed names answer `hasattr` with False (the 0.13.0 names of `pyflightstream.run` and
  `pyflightstream.qa.physics`), and the import statement still gives the migration
  instruction; `report_paths` refuses a report label longer than 64 characters.
- Maintainer scripts and the manual register: `pyfs-manual` withholds measured-broken rows,
  `draft` accepts `--overwrite`, the corpus capture scripts exit non-zero when an export is
  missing or stale, and `build_living_physics` writes into a missing folder.
- An `[equations]` block evaluated in an order that reads an equation before it is evaluated,
  or holding an equation that reads itself, is refused before any derived column is written,
  instead of writing `NA` in the dependent column.
- `blade_passage_harmonics` and `write_acoustic_products` refuse a `harmonics` count that is
  not a positive integer, and `gutin_harmonic_rms` refuses a harmonic below 1, instead of
  tabling nothing or returning zero.
- An `[equations]` block evaluated in an order that reads an equation before it is evaluated,
  or holding an equation that reads itself, is refused before any derived column is written,
  instead of writing `NA` in the dependent column.
- `blade_passage_harmonics` and `write_acoustic_products` refuse a `harmonics` count that is
  not a positive integer, and `gutin_harmonic_rms` refuses a harmonic below 1, instead of
  tabling nothing or returning zero.
- `write_series` writes a solution time that is not finite as `NA`, as it already wrote a
  sample, and both reduction writers state their precision: finite values at full precision
  (the shortest decimal that reads back to the same number), unavailable values as `NA`.
- `probe_version` refuses a specification mapping that registers a probe under a name other
  than its own command, so two definitions never claim one probe; nothing is started.
- A table entry of `inputs/executables.local.toml` replaces only the fields it states: a
  committed `version` the overlay does not repeat is kept.
- The geometry clean refuses a saved simulation whose block markers nest or close a block
  that is not open, naming the block and the line, and writes nothing.
- `isa()` refuses a NaN or infinite `delta_isa_c`, and the inflow J map refuses a
  non-finite diameter, free-stream speed or advance ratio, each naming the value.
- `write_chapter` and `pyfs-manual draft --write` refuse an existing destination unless
  `overwrite=True` (`--overwrite`). A compacted simulation whose archive records another
  simulation or holds a file its table does not list is not restored, a compacted post
  archive is read back before its folder is deleted, and a file met at a refinement level's
  path during the run is refused as before the run.
- `pyfs-workspace excel create|preview|apply|cancel|check` runs the matrix workbook
  commands, with `--workspace` defaulting to the current directory;
  `python -m pyflightstream.workspace.excel` is the same command.
- `plan.json` records each solver executable a matrix plan measured with its SHA-256
  (`instrument`) and the SHA-256 of every geometry file a row opens (`inputs_sha256`);
  `pyfs-matrix run` refuses a plan whose executable or geometry changed since, or a
  `--fs-exe` other than the planned one.
- A CCS wing's sidecar declares morphing surfaces in `[[import.ccs.morphing_surfaces]]`, and
  a matrix row deflects one with `MORPHING` and `MORPHING_ANGLE`
  (`NEW_CCS_WING_MORPHING_SURFACE`), without regenerating the CCS file.
- A point alias whose index is a digit-like Unicode character (a superscript two, for
  example) is not an alias and no longer stops the command with a conversion error.
- The `WALLTIME` watchdog of an unsteady row measures elapsed time with the monotonic clock
  between solver steps, so a system clock set forward or back during a run no longer stops
  it early or late.
- An unsteady or rotor row that continues a stopped run (`RESTART`) refuses a key its run type
  does not register, as a row that starts from a mesh does, instead of ignoring it.
- A per-blade row whose run history holds only part of the averaging window states the span
  it averaged: `FIRST_STEP` and `LAST_STEP` are the first and last step held inside the
  window, `STEPS` counts the steps that entered the average, and the azimuths are at those
  steps.
- An unreadable stamped file of one series kind costs that kind's series only: the loads,
  sections and probe series read from other files are still written and indexed, and the
  point's skip names the table that was not written.
- A continuation (`RESTART`) whose point is refused before the solver starts moves the
  stopped run's archived outputs back into the datapoint folder, so the stopped record
  still names files that exist.

### Deprecated

- Calling `polar_row` without `beta_deg` is deprecated with a removal version: it keeps
  zero sideslip and warns until 0.45.0, which requires the argument.

## [0.42.0] - 2026-10-16

### Added

- The documentation site is organised around Workspace CLI, Python API, Reference and
  Understanding pyflightstream, with the owl theme. Linked requirement, code, execution
  and workspace-file data are generated from the approved SRS and the tagged checkout,
  with immutable source links and CI drift checks. A public references page enumerates
  the literature citations, and manual citations use public FSM build identifiers.
- The software requirements specification is organised by numerical laboratory stage,
  with eleven stage requirements, the workspace version-control principle, stable numeric
  identities and a complete migration table. Pending obligations tied to planning nodes
  may keep absent code and test anchors until they are implemented.
- The README support table ends with the vendor build number of each build, and the
  installation extras are explained. The experiment protocol versus the generated
  procedure, and the lifecycle of the version-controlled workspace files, are explained.
- The BPF CSV adds `BIN_OFFSET_BINS`; off-bin notes disclose the unwindowed amplitude bias.
- `window_from` states the rotor's own averaging span; reduction values are unchanged.
- `Script` exposes the carried-action and deferred-selection methods, and the averaging
  window types are public exports.
- Volume-section references require an existing section, and `declare_existing` accepts
  `volume_sections` for opened projects.
- `pyfs-matrix` selects simulations with one `--sims` grammar, and both marking commands
  accept point aliases. The positional ids of `delete-sims` still work and are deprecated
  in favour of `--sims`.
- Cost tables name each exact planned point and classify custom LEGACY recipes by their
  declared clock. Plans dry-build and render one-job steady sweeps, and a builder refusal
  blocks every point of its row.
- `pyfs-fsi` refuses recognizable command-line mistakes before running a step, and
  coupling JSON accepts a UTF-8 byte-order mark.
- Structural resume errors name mismatched arrays and validate persisted load shapes.
  Staged boundary totals are checked before coupling, and node clearance scales with the
  local section dimensions.

### Changed

- Command emission validates enumerations, entity references and free labels before a
  script is written. Numeric rotor axes 1, 2 and 3 resolve to X, Y and Z; toggles accept a
  boolean or the literal `ENABLE`/`DISABLE`; inline strings require one non-empty token;
  `PRINT` keeps its documented remainder-of-line message; `SURFACE_MIRROR` accepts only
  the mirror planes 1, 2 and 3; `BOOLEAN_UNITE_GEOMETRY` accepts the documented `-1` form.
- Skipped inline positional slots and required inline arguments after optional ones are
  refused, duplicate blade labels are rejected before emission, `CREATE_NEW_ACTUATOR`
  requires its subtype, and `EXECUTE_SOLVER_SWEEPER` requires `export_folder` exactly when
  per-step export is enabled. Surface deletion reduces known boundary counts and
  renumbers the surviving labels.
- Public parking rejects absolute, drive-relative and parent-traversal paths.
- Command metadata distinguishes `mixed_inline` from `inline`, and undeclared own-line
  inline arguments are refused. Older CAD import, contour and streamtube forms are
  emitted according to their own manual editions, and 26.122 and 26.123 accept the
  documented all-boundaries proximal selection.
- Workflow convergence alone no longer verifies a command: compatibility rows keep
  independent effect measurements or become explicitly inconclusive. The 26.122
  `SET_INVISCID_LOADS` claim is documented with direct inconclusive evidence, and the
  free-surface command is unprobed because its precondition was not established.
  Compatibility diagnostics distinguish a manual withdrawal from a command that was
  never documented.
- Validated 26.122 emission refuses the modal profile export; an explicitly supervised
  script may use the recorded raw bypass. Older unmeasured CCS revolve forms emit
  `PyflightstreamWarning`, and `emit_ccs_wing` refuses REAL controls.
- Use `edge_type=` for 26.124 wake imports; `units=` remains accepted as an alias.
- `pyfs-manual register --write` requires `--commands-dir`, and the manual comparison
  reports description changes beyond the former fixed windows. Operational support
  requires a buildable minimal workflow. Version-scoped reference pages show the target
  grammar.
- Workbook creation no longer accepts `python`; the inert Matrices and Python executable
  cells are removed.
- Reference lattice surveys require at least 14 azimuths for six stored harmonics, and
  `PHYSICS` flags may be omitted independently.
- Public documentation, docstrings, source prose and diagnostic messages state current
  behaviour without release history or dated editing history. Concepts holds the single
  architecture page, and the documentation delivery check resolves same-site section links.
- Results of letter-path rotors with a non-default `blade1` datum change, because the
  solver now honours that datum. The 26.100 unmarked Euclidean motion uses measured
  rev/min.
- Positional calls of `airfoil_section_contour`, `solid_section_properties` and
  `blade_properties_from_sections` after the primary input still work and warn; use
  keyword arguments. They are removed in 0.43.0.
- Coverage is measured by the release's frozen full suite, with the floor kept in
  `pyproject.toml`; push CI and the release workflow's wheel tests run without coverage
  instrumentation, and both release runners still test the built wheel. Contributor
  coverage evidence comes from the `suite-full` release receipt, run with
  `--cov --cov-branch`.
- Documentation builds print the last 80 LaTeX log lines and the first TeX error with its
  following 10 lines before failing, and failed guide logs are kept as a CI artifact. The
  docs workflow installs scalable T1 fonts (`cm-super`). A manual dispatch builds the site
  and the guides without publishing them; it publishes only from main with `deploy=true`,
  and a version tag still publishes the site.

### Fixed

- Undefined rotor coefficients raise `ProductError` instead of `ZeroDivisionError`, and
  empty passage series raise `MalformedOutputError` instead of `IndexError`. Catch
  `CampaignConfigError` for row and artifact naming refusals, and `SolverSetupError` or
  `PyflightstreamError` for unsupported setup entries; `RuntimeError` handlers still work.
- `per_blade_rows` is in `unsteady.__all__`, and its refusals derive from `ProductError`.
  Multi-plane rotor sections are skipped instead of pooled in harmonics and validity
  summaries, and rotorless unsteady marches apply the requested vorticity selection.
- `solver_settings` scalar and version refusals preserve the existing script content.
- Direct morphing refuses multiple blades and frozen coupling.
- Steady coupled completion recognizes stderr and polls appended output incrementally;
  discarding a steady job marks every one of its points failed.
- Extraction records launch exceptions, cleans local copies in `finally`, and archives
  previous scripts in collision-safe stamp folders. Per-mesh geometry discovery accepts
  derived thin-blade OBJ names beside their source.
- Surface probe coordinate systems cite their frames.

## [0.41.0] - 2026-10-15

### Added

- `pyfs-workspace geometry export-surface-mesh` previews or exports a saved body's surface to the mesh file probe planning reads; `--apply` runs the solver and `--overwrite` replaces an existing mesh after a successful export.

- `pyfs-matrix support [build]` reports evidence-derived build support without
  launching the solver; omit the build to list every registered version.
- Matching steady-wing, unsteady isolated-propeller, quasi-steady rotor and
  mesh-refinement examples under `examples/using-CLI/` and `examples/using-API/`
  include solver-free planning steps. Specialist examples are published as site pages.
- An explicit exploratory `[noise]` request writes compact loading-noise observer
  signals from recorded quasi-steady wheel loads, labelled as unvalidated.
  Its report indexes the generated signals, observer positions and source runs.
- `[products].polar_axes` selects wind or stability force coefficients while
  retaining explicit frame columns. Steady selections use `CD`, `CY` and `CL`;
  averaged unsteady selections retain their plot group under
  `selected_drag_coefficient_<group>`, `selected_side_force_coefficient_<group>`
  and `selected_lift_coefficient_<group>`.
- Coupled polar and rotor tables include each blade's last recorded tip deflection
  and twist; missing structural values remain `NA`. Averaged unsteady polars list
  these final displacements in contributing-point order, rather than time-averaging them.
- Located post-processing declarations accept `attach = "space" | "body"`.
  Coupled rows refuse unmeasured body attachment and warn about surface taps
  that remain at declared spatial locations.
- `plan --inflow-fft` writes per-point blade-view harmonic tables at the resolved
  advance ratio, including variance shares and effective reduced frequency.
- `pyfs-workspace geometry trailing-edge` extracts a mesh's trailing-edge midpoint
  file with explicit axis, hub and length unit.
- `pyfs-workspace calibrate` derives a sector-offset calibration from two recorded
  rotor points, retaining the evidence checks and unvalidated status.
- FSI workspace inputs can stage a checked frozen displacement file and explicitly
  allow configuration changes through the coupling driver controls.
- Workspace post-processing tables recorded force-distribution and surface CSV
  exports, preserving force units and explicitly unstated scalar identities.
- Workspace post-processing writes mapped and direct structural deflection, twist
  and available coupling history from admitted coupled points, with input-digest checks.
- Planar probe grids can be declared in `[[probes]]`, with reference-frame placement,
  axis distributions and near-surface refinement checked during plan. Saved
  simulations require a separate surface mesh export before this route plans.
- Calculated FSI sections accept unit-chord airfoils or NACA four-digit contours.
- Coupled plans report effective station properties, natural frequencies and
  rotational excitation warnings before a licensed run.

### Changed

- `--no-ignore-missing-families` explicitly disables missing-family tolerance.
  It is mutually exclusive with `--ignore-missing-families`, including an
  explicit false value; use exactly one form.
- Migration instructions live in `docs/upgrading.md`. Current help names the
  required input fields, geometry folders and supported migration routes.
  Upgrading guidance explains `inputs/INPUTS.md`, generated-block refresh and
  preservation of the legacy pproc copy.
- Run manifests use a versioned document with one status header, shared immutable
  solver/frame/geometry definitions and one ordered artifact list. Old record
  arrays are refused; `pyfs-workspace migrate` previews the 0.38.0-format conversion
  and `--apply` preserves exact backups. Resolved run display includes all record
  fields. Migration leaves scientific products unchanged. Reposting 0.38.0 data
  uses 0.40.0's coefficient precision; affected columns are named in `docs/upgrading.md`.
- Requirement references in diagnostics use stable child identifiers. Contributor
  requirement pages link the hierarchy, code anchors and behavioral tests, and
  reserve retired identifiers. Command names, options and configuration keys are unchanged.
- Contributor conventions describe current rules and evidence. Release notes are
  written directly in this changelog, which covers 0.38.0 onward.
- Maintainer CI skips duplicate, docs-only and dry-run branch runs and cancels
  superseded runs. Release requires the newest main CI run at its SHA to be green
  on its latest attempt, measures coverage in the tag's artifact tests, and deploys
  documentation on version tags.
- Numerical validation includes recorded acoustic blade-passage harmonics, numeric
  tables for both harmonic-fit campaigns and dependency checks for changed fit and
  FFT columns. These checks do not change production numerical behavior.
- Workspace coverage checks include sector-offset calibration and the quasi-steady
  noise report, with no additional exemption for an unreachable public name.
- Excel subcommand help explains workbook paths, preview direction,
  matrix selection and batch files.
- Drift help and API documentation state the default campaign
  name separately for each comparison workspace.
- Manual CLI documentation distinguishes reporting success,
  findings, missing dependencies and argument errors.
- The FSI calibration example checks its template edit and reports
  the factor read from the input file, with the matrix override kept separate.
- Setup and flight-condition pages include
  solver-free examples for separation assignments and requested/report binding.
- The Campbell example explains rotational harmonics and
  distinguishes them from blade-passing excitation.
- Refusal guidance distinguishes CCS file-import
  shedding from rotor wake direction and motion-record refusals from accepted
  flat rotor keys. The refusal catalog no longer lists unused entries.
- Rotor-table documentation describes rejected rows, static
  rows, reference and flight velocities, and both vertical shaft directions.
- The overview guide describes build-specific validity and
  the acoustics toolbox without categorically excluding acoustics.
- Torsion accuracy is checked numerically against analytic
  sections. The guide directs readers to grid convergence and the runnable
  blade-properties example instead of promising a shape-independent error.
- Versions, builds and evidence distinguishes command
  statuses from build support levels and links both definitions.
- Preserve existing products before reposting an older
  workspace. Post applies the current strip integration, rotor averaging
  windows, installed-frame transformations and coefficient precision to
  retained exports. Compare the recorded windows, units and references;
  rerun the solver only when required exports are missing or inputs change.
  The definitions page links the release-by-release upgrading guidance.
- Public entry pages describe
  current behavior, the cheatsheet states drift's per-side default names,
  and redundant cheatsheet wording is shortened to fit its page.

### Removed

- `cases.point_tag` and `cases.naming.point_tag`, the unused pre-0.21 naming
  helper. Use `point_name(case, point)` for current workspace point names.
- Authored campaign-file loading and matrix-to-campaign-file conversion, including
  `pyfs-matrix convert`. The matrix is the sole campaign declaration; use
  `pyfs-matrix plan` or the public `plan_matrix` API.

### Fixed

- Superfiles retain the recorded structural tip deflection and twist fields in ordinary polar row order, without replacing existing columns.
- Probe models refuse non-finite float fields with `ProbeGeometryError` naming
  the field, including nested and serialized inputs. Mapping and JSON validation
  preserve explicit `strict=True`, including nested grid axes, and refuse numeric
  strings in strict mode. Default coercion remains available.
- Setup reading refuses solver settings outside their declared model bounds,
  including output precision and stabilization strength, naming the setup file,
  field and bound.
- Generated setup headers distinguish boundary lists from family-selector keys;
  legacy native volume-section output refusals point to probe sampling and post fields.
- Sampled-field warnings name only velocity or rotation-timing conventions that
  lack evidence on the run's build.
- Refinement refusals name the selected configuration file when no factor is given.
  WALLTIME surface-average refusals describe the incomplete averaging window.
- Direct-morphing structural products use recorded applied station displacements
  with a matching configuration digest instead of refusing every direct-morphing point.
- Coupling projects spatial-cut loads using applied station slope and twist before
  elastic-axis moment transfer, including relaxed direct-morphing state.
  Station-force projection reports a changed node count before decoding restored displacements.
- Averaged unsteady polars preserve existing columns whose names match structural
  tip columns. A collision omits the tip block and records the conflicting names
  under `#structure` in `products.json`. Rename conflicting pproc names or equations
  to include the block; separate structural products remain available.
- The manual converter prints help for `--help` and `-h` without conversion
  inputs or optional conversion dependencies.
- Dummy FSI failures append to the error log, retaining earlier call evidence.
  Its API documentation distinguishes a nonzero exit from a confirmed solver abort.
- Loads-assessment documentation describes residual and iteration-limit verdicts.
  Default-output documentation explains unsteady normal probes and solver residual
  and load plots.
- Release compatibility checks compare complete batches and bound numeric CSV
  differences by the base writer's printed rounding while preserving rows, column
  order and unchanged text. Cost estimates exclude failed and incomplete runs.
- Public import bindings in `run.cli` and `script.helpers` remain available.
  Compatibility checks exclude private paths, scope retirements to fully qualified
  names and include the requirements-path helper needed by exported test collectors.
- Local-run progress tests use deterministic polling.

### Owed

- **The licensed confirmations of 0.34.0 are owed after the release.** By
  decision of 2026-10-02 they are made on the released package and
  recorded as post-release commits, outside the `[0.34.0]` section. Each lands
  as a commit of its own after the tag, so the 0.34.0 package does not change
  with it. RPT-130 is still owed. Five are
  paid, measured on 26.124 (build 8172026) with the released package; the
  requirements' evidence lines now cite them, FR-318 R5 records the answer to
  the question it left open, and only FR-338 and FR-340 change status, to
  implemented:
  - RPT-133 (FR-318 R5): the solver accepts the vorticity drag list before
    `START_SOLVER`, and every step export then carries it; in the order 0.34.0
    emits, only the final export does. Moving the list is done in 0.35.0
    (R6 of the same requirement).
  - RPT-134 (FR-96): when the reopened state is kept, a continuation's plots
    export holds the whole march numbered from 1, which the post joins with
    every step once. The continuation 0.34.0 emits does not keep that state
    (fixed in 0.35.0, FR-396).
  - RPT-135 (FR-312): 26.124 opens and runs a file whose blocks are reset to
    the 26.124 fresh import; the uncleaned control differs in its saved
    actions only, and the blocks are compared offline. Registering the 26.124
    table in the package is not in 0.35.0 and stays owed.
  - RPT-128 (FR-338, FR-340): `CDo` reads zero in a coupled FSI run because
    the solver prints it so, not because of the package's order, and the
    magnitude of the XZ cut moment is confirmed on a cambered wing. The FSI
    page states both, and the definitions page that `CD0` reads that zero in
    a coupled run; nothing the package emits changes.
  - RPT-126 (FR-334, FR-335): of 43 acoustic, CCS and surface-removal
    commands probed on 26.124, 26 are verified and 7 broken, and the command
    database follows the run's report. Ten CCS commands stay unprobed, the
    arity of the two CCS exports stays undetermined because neither wrote a
    file, and the REAL control-surface form stays refused: its failure follows
    the limits, not the REAL token. Citing RPT-126 in the refusal message is done in
    0.35.0 (FR-336 R4), and 0.35.0 adds the probe waiver (FR-333), which removes the
    two strict expected failures of the `DELETE_CCS_*_RELAXED_TE` probe scripts.
    Judging the ten unprobed commands and measuring the arity of the two CCS exports
    stay owed: the two strict expected failures of the CCS export arity case
    (`test_p0340_arity_2003_06`) remain until the arity is measured and the emitter
    corrected if needed.

- **The licensed confirmations of 0.35.0 are owed after the release.** The continuation the
  package emits no longer re-initializes a reopened state (FR-396); this is
  verified offline against RPT-134's resume arm, the hand-edited script that
  marched on, and the continuation the package itself emits has not run on a
  licensed seat. The continuation of a run the wall clock stopped shares the
  emission path and is not measured. The absolute paths of the grouped job
  scripts (FR-359) and the CCS mesh probe judges (FR-401) are likewise
  verified offline and wait for a licensed run.

- **`pyfs-qa apply-compat` writing a 26.124 row into a command's multi-line version block itself is owed.** In 0.35.0 the `SET_NEW_UNSTEADY_SOLVER_ACTION` row was folded by hand as the tool directs, and a tier-1 test checks the result (FR-342).

- **The Zenodo archive of v0.14.0 DOES NOT EXIST**, re-measured against
  Zenodo's own API on 2026-09-14, when the v0.18.0 archive row was paid: the
  concept record lists NINETEEN archived versions and v0.14.0 is not among
  them. The earlier reading of 2026-09-10 said the same and could not be
  confirmed for four days because the service was answering 504; it is
  confirmed now, so this is a fact about the archive rather than about its
  availability.
  THE RELEASE OBJECT FOR v0.14.0 EXISTS, published 2026-09-09, so the webhook
  had what it needs and the archive still has no version for it. Whatever
  failed, it failed silently, and re-triggering it is the repair.
  Until that row lands this section says so, because a shipped release that
  quietly stops being citable is the gap PFS-2024.09 is about. Cite that
  release by the concept DOI, which resolves to the newest archived version.

## [0.40.0] - 2026-10-14

### Added

- The far-field family (FR-450 to FR-456): the `[farfield]` table of the pproc artifact selects the Trefftz-plane analyses (`variant = "sections"`, `"wake"`, `"plane"`) and the survey balances (`[farfield.ledgers]`); `pyfs-matrix post` writes `farfield/<group>_trefftz.csv`, `farfield/<group>_ledgers.csv` and `sections/<point>_trefftz_<family>.csv`, each file of an unsteady row as `_instant` and `_average`, and the super file gains `CL_T_<V>`, `CDI_T_<V>` and `E_T_<V>` after every other column.
- `pyfs-matrix plan` reuses what the artifact declares for the far field, adds what is missing (a section distribution, the wake in the VTK export, the far-field plane or lattice as probe points) and refuses only the impossible, stating each input under the point's `farfield` key of `plan.json` (FR-455).
- A `[[probes]]` entry's `field_formats` takes `"tecplot-points"`: the post writes `fields/<point>_field_<entry>[_step_<step>]_points.dat`, every sample in one ordered Tecplot POINT zone, through `pyflightstream.post.write_tecplot_points`; the `"tecplot"` product, one zone per sample, is unchanged (FR-153).
- `results.wake.parse_wake_export` reads the solver's `<name>_wakes.vtk` (FR-452).
- A `[[probes]]` entry declares survey `lattices`; every probe point is checked against the body at plan, a package-added point inside it refused and a declared one warned (FR-459).
- A pproc `[streamlines]` table traces surface friction lines and off-body streamlines (seed lines and tubes) on every point of a row, exports them, and the post writes a VTK polyline product of the off-body lines; the plan states the count per point (FR-460).
- The `unsteady` row key `SIXDOF: d<id>` frees a body to move under its loads from an input of `inputs/sixdof/`: families, body frame, mass and inertia, gravity, initial state, free degrees, external, spring and custom forces, and the trajectory export (FR-461).
- An FSI input with `mode = "external"` couples a fixed wing to a structural program of the user's own through the step `pyfs-fsi external`, which runs the program per coupling iteration and archives and validates every call (FR-462).
- The streamline and 6DOF commands a row reaches are refused at plan on a build where no licensed run verified them, naming the command. (FR-460, FR-461)
- The geometry stage: `pyfs-workspace geometry build` reads `<name>.geometry.toml` (one source table, `[ccs]`, `[cad]`, `[create]` or `[mesh]`, then `[[operations]]` and `[trailing_edges]`), previews the build without running anything, and with `--apply` runs the solver once with no solve, reads the saved body back against the stated boundaries, audits it, and writes a ParaView preview and a `<name>.build.json` record (FR-470, FR-471).
- A control-surface deflection sweep builds one sibling geometry per angle, `<name>_<SURFACE><sign><tenths>` (FR-472).
- `pyfs-workspace geometry accept` records the inspection of a built body; `pyfs-matrix plan` refuses a row whose body is stale against its instruction and warns on a resaved, unaccepted, audit-failed or other-build body (FR-473).
- Mesh operations in the instruction file: circular and linear copies, a cut by a plane, hole filling, degenerate-face removal, face extraction and deletion by threshold, and node moves pinned to the mesh's sha256 (FR-474).
- CAD body operations before the conversion of an IGES file, and bodies and section-lofted wings built by the solver's CAD Create commands (FR-475).
- `pyfs-workspace geometry build --rows POL --matrix FILE` prints one whole matrix row per built variant, copied from the row `POL`; nothing is written into the matrix (FR-472).
- `pyfs-workspace geometry build --parallel 2` runs up to two variants of a sweep at once and reruns alone a variant that failed beside another (FR-472). If the optional `psutil` package is absent, free memory cannot be measured: the command warns and runs one variant at a time. See [geometry sweeps](docs/geometry.md) for the memory condition.
- A deflection sweep writes `<name>.sweep.vtk` in the base folder, the swept control surface of every variant overlaid (FR-472).
- `pyfs-matrix plan` warns on a row whose `SYMMETRY` is `MIRROR` and whose built body carries a deflected control surface, naming the surface and the angle (FR-473).
- A rebuilt mesh's sidecar keeps the `translate` and `rotate` operations, `[wake_termination]` and `[base_regions]` of the sidecar it replaces, or of its `[mesh]` source (FR-471).
- `pyfs-workspace geometry from-sidecar` writes the instruction of a geometry a matrix row builds today (FR-476).
- `pyfs-workspace geometry refine`, `audit`, `inventory` and `degenerate`, the homes of the `pyfs-matrix` verbs of the same results (FR-477).
- `cases.windows` exposes `ExportThresholdRecord`, `StoppedStepRecord` and `RESTART_STEP_OFFSET_VARIABLE`; the generated API reference classifies it as provisional (FR-409, NFR-29).
- The generated input template carries the example `inputs/pproc/p003.toml`,
  covering `[streamlines]` lines and tubes, `[[probes.lattices]]` and
  `[farfield]` with `trefftz` and `ledgers` (FR-460, FR-450).
- `farfield.plane_lift`: the Kutta-Joukowski lift of the streamwise vorticity a Trefftz C plane holds. The C row of a wing states it as `CL_T`, and post warns where it departs from the solver's CL by more than 10 percent: the probe field then does not hold the circulation the loads shed (FR-453 R9, PFS-2081.95, RPT-171).
- Every row of `farfield/<group>_trefftz.csv`, `farfield/<group>_ledgers.csv` and `sections/<point>_trefftz_<family>.csv` ends with `STATUS`, the point's solver termination status as `campaign_sweep.csv` writes it (FR-456 R10, PFS-2081.97).
- The run record carries `farfield_layout`, the far-field plane and lattice each point laid or reused (a steady job keys it by point name), and `plan.json` states it under the row's `farfield` `probes` (FR-455 R4, PFS-2081.58).

### Changed

- NFR-20, FR-457: New far-field and probe-layout functions require keywords after their primary argument, so coordinates, field arrays, forces and sampling scales cannot be exchanged silently by position. The numpy harmonic functions likewise take the new azimuth array as `psi=...`. See [far-field signatures](docs/upgrading.md#far-field-signatures) for migration examples.
- mypy recount 2026-10-13: 165 errors in 13 of 343 modules, on the 0.40.0 tree; the shipped
  configuration is green over all 343. Three exempted modules are clean and their overrides are
  deleted (`pyflightstream.farfield`, `pyflightstream.fsi.driver` and `pyflightstream.script.entities`),
  the exempted set falls from sixteen modules to thirteen, and the error total inside it moves from 159
  to 165 (`qa.probes` 79 to 92, `script.helpers` 2 to 4, `script` 17 to 13, `post.writers` 2 to 1). The
  forty-six modules the package gained since 0.39.0 are all clean and none is exempted (NFR-27, RPT-029).
- `pyflightstream.farfield` takes and returns numpy arrays and small frozen containers; `xarray` is no longer a required dependency (FR-457). Baseline bit parity has the z-axis moment exception and platform limits stated below.
- `farfield/<group>_ledgers.csv` takes `FY_LATERAL_N` and `FZ_LATERAL_N` from the transverse-force record of `pyflightstream.farfield.transverse_force` and computes `COVERAGE` with `pyflightstream.farfield.sample_coverage`, so the public balance functions are what the workspace runs; every value is unchanged to the last bit (FR-38).
- `pyflightstream.probes` is the one home of probe geometry: the line, rectangle and circle layouts, the survey lattice and the far-field plane (FR-459).
- A steady row creates its probe lines and its drawn probe points through `pyflightstream.script.helpers.probe_line` and `probe_points`, the helpers a Python script uses; the emitted script is unchanged (FR-79).
- A row's probe-points export is emitted through `pyflightstream.probes.emit_probe_export`, after the one `UPDATE_PROBE_POINTS` of the row's updates; the script is unchanged, and a second export to the same probes file is refused naming `emit_probe_export` (FR-81).
- The csv a steady row's plan stages for the far-field plane and lattice it adds is written by `pyflightstream.probes.write_points_csv`, byte for byte the text it was before, and `write_points_csv` also writes to an open text stream such as `io.StringIO` (FR-455, FR-459).
- `pyflightstream.probes.emit_probe_points` and `write_probe_csv` take an optional placement (`axis`, `origin`, `scale`) and `decimals`, the placement and rounding the plan applies; without them they give the lattice's own unrounded points as before. A steady reference-frame `[[probes]]` lattice is emitted by `emit_probe_points` and a far-field lattice the plan adds alone is staged by `write_probe_csv`; the scripts and staged files are unchanged byte for byte (FR-459).
- A row naming a CCS, IGES or STL file, or a sidecar whose import operations scale, rename or mirror, is warned at plan with its replacement; it still runs as before, and 0.41.0 refuses it (FR-476).
- `pyfs-matrix refine`, `audit-mesh`, `inventory` and `degenerate` warn that `pyfs-workspace geometry` is their home; their results are unchanged (FR-477).
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

- Restart records have declared ExportThresholdRecord and StoppedStepRecord
  types. The persisted export_window key remains compatible. (FR-409).
- Run, post, collect and regeneration overwrite products without an archive by
  default. collect --archive and delete-sims --archive preserve replaced products.
  post --force-overwrite explicitly selects no archive and still confirms it. (FR-397).
- Continued per-step exports record their predecessor step_offset and local
  first_step. LAST and AFTER thresholds reach the continued march's counter;
  thresholds in the span already run, or unprovable predecessor counts, refuse
  at plan. Additional marches resolve LAST windows against their new end. (FR-409).
- Point names retain the historical binary half-even rounding, so existing
datapoint folders remain readable after upgrading. A sweep whose rounded names
collide is refused before planning; 10.45 and 10.50 degrees keep AL+104 and AL+105. (FR-102, FR-408).

- Collection files and records an existing optional wake VTK beside its declared
surface export. No wake companion is required when the solver writes none. (FR-452).


- PFS-2081.49: Steady far-field planes and lattices append their points through
one bulk CSV import. The staged file keeps the recorded point order and the
simulation length unit; each distinct set has a content-derived filename.
The default 27,059-point solver timing still needs a licensed measurement. (FR-455).

- PFS-2081.51: The wake reader accepts empty polygon blocks and the solver's
point-coordinate scalars, preserving connected mirror halves and collapsed
lines. Post selects one mirror half before reflecting it once and warns when
zero-strength collapsed lines leave missing circulation in the export. (FR-452).

- PFS-2081.52: Trefftz B reconstructs strip circulation from the circulation
shed by each wake line. It integrates at the actual wake crossings, retaining
folded sheet topology. GAMMA_SCALE, induced drag and span efficiency change;
near-field lift calibration remains. The recorded fine-mesh comparison gives
raw lift within 3 percent of the near field and efficiency within 0.03 of
Trefftz A. The real solver fixture exports use LF line endings; their
coordinates, connectivity and scalar values are unchanged. (FR-452).
- The rotor Mach numbers gain the advancing-tip Mach number `M_adv = sqrt((Omega R + V_ip)^2 + V_ax^2) / a` (FR-176 R1): `M_hel` bounds the tip only in axial flow, and `M_adv` equals it there and is `(Omega R + V) / a` edgewise. `pyfs-matrix plan` prints an `M_adv` column and warns on `M_adv >= 1` (still a warning, never a refusal), `plan.json` and the run record carry `mach_advancing` beside `mach_helical`, and the rotor table gains `MADV_<alias>` as its last column. A row whose rotor axis cannot be resolved takes the edgewise bound and the plan line says so. `M_hel` is unchanged.
- EXPORT_6DOF_TRAJECTORY is now an export-phase command, and a row's SIXDOF trajectory is written after the march with the other exports, where it was written in the setup phase and held its header and no row on 26.124 and 26.125 (FR-461 R6, RPT-166 P4-04). A script of your own that places it before the march keeps working only through raw text.
- The 6DOF trajectory columns are in the solver's units, which the probes did not settle; the package does not convert them (docs/sixdof-motion.md). (FR-461)

When adopting 0.40.0, account for these changes in probe evidence, physics
references and command-line refusals.


- **PFS-2100.023, PFS-2104.015:** migration: `emit_probe_import` documents that
  coordinates use simulation length units and types `frame` as `int | str`.
  The unit of the CSV is now a required argument (no default). (FR-80)
- **PFS-2097.008, PFS-2095.022:** migration: containment culling now refuses an
  open mesh supplied as an object. Position verification refuses non-finite
  exported rows and accepts empty plans, including after JSON loading. (FR-459, FR-79)
- **PFS-2102.013:** migration: saved-state probe assertions require the correct
  numeric value, including sign and exponent. A substring of another number
  no longer verifies a command; re-run probes whose old evidence depended on it. (FR-25)
- **PFS-2102.033, PFS-2102.028:** migration: an unsupported prelude argument or
  an exception in an effect instrument records the affected probes as
  `unprobed` instead of terminating the probe run. (FR-25)
- **PFS-2102.005:** migration: `WingSpec` and `BladeSpec` refuse a cambered
  four-digit section with a zero camber-position digit at construction. (FR-27)
- **PFS-2102.003:** migration: executable identity is `unknown` when the version
  registry has no build number, even if the executable prints one. Record a
  build from identity evidence before treating the executable as confirmed. (FR-25)
- **PFS-2102.030, PFS-2102.010, PFS-2102.002:** migration: malformed compatibility
  reports and unreadable physics evidence now raise `QaEvidenceError`.
  Invalid reference fields are refused through the same error type.
  `pyfs-qa probe` reports missing executables and evidence refusals with exit 2;
  `pyfs-qa cost` reports unreadable manifests with exit 2. (FR-25)
- **PFS-2085.017, PFS-2102.007, PFS-2102.009:** migration: physics reduction
  refuses mixed executable identities, unknown incidence, and a PHY-01 polar
  without both two distinct angles and a 4-degree point. A failed case reduction
  is recorded as a case error; a failure after execution is reported as such. (FR-26)
- **PFS-2102.015:** migration: report labels must be portable file-name tokens,
  without separators, whitespace, control characters, or Windows-forbidden
  characters. Invalid labels are refused before the solver starts. (FR-25)
- **PFS-2102.036:** migration: a relative reference band centred on exactly zero
  is refused. Drift reports such a baseline without a reference band. Reference
  updates refuse a zero-centred relative band before replacing the reference. (FR-26)
- **PFS-2085.016, PFS-2102.011 (review correction):** migration: reference
  promotion checks the source report itself for unconverged steady points,
  including the steady half of PHY-06. Historical reports are checked too;
  completed unsteady points remain eligible. Incomplete paired-polar reports
  are refused. (FR-26)
- Far-field post now uses the planning selector grammar, including numbered
family stems and nested aliases. Missing Trefftz A families each receive their
own section distribution, so their exported loads can be attributed and posted. (FR-455).

- Trefftz C converts `Cp_ref` with the recorded reference dynamic pressure.
Its Bernoulli diagnostic changes when the reference and freestream speeds
differ. The public `bernoulli_residual` return documentation now states the
integrated Betz-Maskell diagnostic in N. (FR-453).

- Truncated and invalid wake count headers produce named reader refusals and a
far-field post skip. The signed shed-circulation requirement and its verification
now agree with the definitions page and the recorded wake evidence. (FR-452).
- post help states the overwrite default once and explains confirmation controls; geometry build protects outputs used as run inputs (FR-397, FR-471; PFS-2081.110, API-001).
- matrix geometry aliases name their ledger-backed removal in v1.0.0 (FR-477, NFR-20; PFS-2081.111, API-002).
- the new external FSI command and its generated callback use only --out; external help carries no requirement id (FR-462; PFS-2081.113, PFS-2081.114, API-004, API-005).
- Setup family lists can omit absent numbered siblings on sector geometries; the strict missing-family option still refuses them. (FR-435).
- OBJ-only geometry sweep previews print the OBJ filename used by matrix rows. (FR-472).
- Geometry builds refuse unowned partial and mesh sibling folders. Retrying an owned partial build archives its evidence under `.partial.previous`; rebuilding a mesh replaces only recorded outputs and preserves other files. (FR-471).
- External FSI refuses input and output names reserved by the coupling and checks structural node digests before staging and before every structural program call. Each call records the staged node digest. (FR-462).
- Far-field bit parity explicitly excepts the approved right-handed z-axis moment sign correction. All other baseline results remain exact. Verification is supported on Windows AMD64 with CPython 3.12 and numpy 2.5.4; other platforms are unverified. (FR-457).
- Trefftz B's requirement now defines the wake export as signed shed circulation
at strip edges, accumulated to bound circulation at strip midpoints. A wake
line value must not be supplied directly as bound strip circulation. This
corrects the requirement to the existing reconstruction and native fixtures. (FR-452).

- Planning resolves the far-field plane and lattice once, by frame and by the exact laid-out points: a declared `[[probes]]` shape identical after layout is reused (a key stated at its default is the same geometry), and a `[farfield]` table stating no geometry reuses the one declared lattice or rectangle that qualifies (FR-455 R2, PFS-2081.56).
- Post matches every exported far-field position to the recorded layout, each set exactly once, and integrates with the recorded grid; a set it cannot match is a named skip. A record without a layout is matched to the table as it stands, by shape for the plane and a frame's lattice (FR-455 R4, PFS-2081.58).
- Trefftz A warns, naming the families and both lifts, where the traced families' lift departs from the solver's CL by more than 5 percent (FR-451 R13, PFS-2081.96).
- The far-field comparison columns `CDI_NEAR_PRESSURE` and `CDI_NEAR_VORTICITY` read the first column of the printed drag split, `CDp` on 26.125 (FR-456 R2, FR-423, PFS-2081.98).
- Failed geometry audits retain the built outputs and record in the partial
folder and promote nothing, including when rebuilding with `--overwrite`.
The geometry build command exits 1 and prints the retained inspection paths. (FR-471).

- Matrix planning refuses legacy or incomplete geometry build records with a
message naming the record and missing input key, instead of raising KeyError. (FR-473).
- FR-471 R2: Geometry builds set the simulation length unit and mark trailing
  edges before saving the FSM and exporting the OBJ. The OBJ now always uses
  the explicitly stated unit, independent of the solver's initial default.
  `EXPORT_SURFACE_MESH` preserves the current script phase, so it may follow
  unit setup and `SAVEAS` as well as geometry operations.
- REL7-001, FR-471 R2: Generated OBJ sidecars now state the exported metre
  unit instead of the source mesh's import unit. Millimetre-source builds
  retain their physical dimensions on re-import and pass valid trailing-edge
  audits for both OBJ-only and FSM-plus-OBJ outputs.

### Fixed

- Trefftz-plane planning refuses a spacing that leaves fewer than three points on either axis, naming the spacing and half extents to adjust, before a solver run produces a plane that post cannot integrate.
- The PDF release receipt builder reads the cheatsheet build log from the
  checkout selected by `--repo`, so another checkout's stale log cannot be
  paired with the rebuilt PDF (NFR-46, REL10-001).

- External FSI refuses aliases of reserved files, including `call.json.` and names ending in spaces, when reading inputs, planning and executing a call. On Windows the archive's call record could overwrite a structural program's output while the call reported success (FR-462 R3, R4, REL8-001).
- PFS-2089.006: Public action-export renderers require explicit keyword-only version.
- PFS-2104.031: Walltime rescue respects EXPORT_LOG and LOG_OUTPUT routing.
- PFS-2104.039: Walltime rescue respects disabled log export.
- PFS-2095.041: Quasi-steady export thresholds are refused as steady-run thresholds.
- PFS-2104.004: Original hub copies preserve the placed origin and basis; unknown placement is refused.
- PFS-2104.005: Flat-row blade frames use the declared rotor hub and blade datum.
- PFS-2104.034: Negative blade datum directions retain their sign in hub axes.
- PFS-2104.007: Raw wake nodes and tolerance use the simulation length unit.
- PFS-2104.008: Vector-shaft MOTIONS hubs align local Z with the shaft.
- PFS-2104.009: Steady survey imports honor scale and frame; unsupported transformed surface surveys are refused.
- PFS-2104.010: Quasi-steady FFT native inflow uses the same simulation unit as the builder.
- PFS-2088.011: Each rotor passage product uses that rotor averaging span, including the fallback turn.
- PFS-2095.006: Signed RPM is treated as a magnitude for windows; stationary step windows have no revolution.
- PFS-2095.007: Uninterpretable averaging windows become post skips and invalid declared windows are refused at build.
- PFS-2098.002: Public export and reduction windows clamp to run length like recorded windows.
- PFS-2100.022: Recorded averaging-window text identifies clipping to run length.
- PFS-2104.011: Rotor block blade count takes precedence; contradictory row counts are refused.
- PFS-2093.009: Averaging windows must contain one valid positive count.
- PFS-2093.010: Unsupported WALLTIME suffixes name the full supplied unit.
- PFS-2095.042: NCPUS accepts integral decimal text such as 4.0.
- PFS-2097.003: Angles and body rates refuse nonfinite values with named row errors.
- PFS-2097.014: Resolved angles, body rates and wall clocks require finite numbers.
- PFS-2097.015: Additional iteration counts must be whole; additional revolutions round before ceiling.
- PFS-2097.004: Restart counts must be finite and positive; iteration counts must be whole.
- PFS-2104.012: Steady sweep builds apply ordinary build validations and boundary-layer frame stamps.
- PFS-2104.041: Every steady sweep section product receives its loads frame.
- PFS-2104.043: Body-rate sweeps run separate jobs; grouped scripts refuse changing rates.
- PFS-2104.037: Grouped motion restatements refuse duplicate later rotor creation.
- PFS-2104.003: Export thresholds and counters honor CLOCK_MOTION.
- PFS-2096.003: LOG_OUTPUT cannot overwrite any other exported output.
- PFS-2104.006: Undeclared custom inflow units outside metre simulations yield unknown coverage and a warning.
- PFS-2104.033: Normal probes are created for averaging-only export windows.
- PFS-2104.036: Steady sweep points replace the prior point probe objects.
- PFS-2104.040: Steady sweep points replace the prior point pproc probe objects.
- PFS-2104.038: Named-frame steady probes use normalized orthogonal axes.
- PFS-2105.027: Steady field layout records reference coordinates and preserves declared frame separately.
- PFS-2104.042: Every quasi-steady clocking executes row raw phase commands.
- PFS-2081.19: Passage cuts use cumulative physical boundaries without repeated rounded-step drift.
- PFS-2081.20: Rotor revolution spans use exact angular steps when declared.
- PFS-2081.33: A missing averaging clock is recorded as a post skip; its documentation now agrees.
- PFS-2093.001: Ignored matrix VELOCITY emits a warning naming TASmps or MACH as the velocity source.
- PFS-2095.008: Zero-RPM explicit clocks build without division by zero.
- PFS-2097.005: Explicit time step and iteration counts must be positive.
- Correct indexed mesh boundary lookup, station roundoff handling, odd-grid harmonic coverage, phase origins, and right-handed in-plane moments.
- Preserve requested post-processing diagnostics in quiet mode and require meaningful scales for aerodynamic counts.
- Preserve manual chapter bytes during version insertion and recover registration writes without overwriting unrelated temporary files.
- Require complete probe execution evidence, correct surface-section export filenames, and use the configured probe timeout in the Python API.
- Tighten release fragment folding, directed parity exceptions, mutation verdicts, and temporary mutation byte restoration.
- The tier-3 maintenance programs `tests/tier3_licensed/actions_probe.py` and `duct.py` start as scripts from
  another working directory with no `PYTHONPATH` setting.
- `tests/tier3_licensed/mesh_routes.py` applies the same relative `1e-9` rounding slack to its unit-conversion
  verdict and its route comparisons, so a gap of exactly one printed unit reports `IMPORT CONVERTS`.
- `tests/tier3_licensed/rotation_null.py` resolves the simulation ID from the leading token of each point name, for
  both angle signs, and scores the recorded products instead of raising `KeyError`.
- The measured-rate table again names the pitch and roll/yaw measurements in
  readable language after internal report locators were removed (FR-101).
- The additional-post guide again names its public skip reasons, which had
  been removed with internal test citations (FR-111).
- Integration guards follow the documented post confirmation controls and
  geometry command deprecations, retain the guarantee evidence outside public
  prose, and record the current architecture and type-check measurements
  (FR-397, FR-477, NFR-13, NFR-27).
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
- read_custom_polar_format raises ProductError naming the line for non-numeric values or a bad reference count. It accepts non-ASCII input and transliterates its title, matching the writer.
- The generated input glossary page keeps the line endings the page already has, so a CRLF checkout is no longer rewritten with mixed endings on every plan or post.
- Mirroring an installed-frame table now also flips YMOM and maps azimuthal *_PHASE_DEG columns to their mirrored angles. C_PHASE_DEG and S_PHASE_DEG retain their transfer-function phases. Rebuild installed-frame copies from their source tables.
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
- On 26.125 exports, post.log now warns, once per point, for each surface on the vorticity drag list whose CDp is exactly 0 (the solver declined it, as earlier builds print CDi 0), naming the surface and the build. This replaces the former warning that the rule was not applied; build 26.124 cannot discriminate.
- docs/geometry.md states that the CAD section loft route is refused on 26.124 and 26.125 (CAD_CREATE_IMPORT_CURVE_TXT is broken there, RPT-166) and that the CCS route is the working one.
- Surface parsing reports out-of-range VTK polygon integers as malformed
  output, so translation records the problem instead of aborting with an
  uncatalogued overflow.
- Reusing a surface translation without a native source verifies its data
  against a fresh translation as well as checking its source and frame.
- A `TK` pin is the temperature of the whole flow state: the speed of sound (`sqrt(gamma R T)`), the Sutherland viscosity, the Mach to velocity conversion, the derived Reynolds number and the density now follow it, as they follow a `dISA`.
- The emitted density, pressure and temperature satisfy `p = rho R T`: a density solved from `REmi` or pinned by `RHOkgm3` is emitted beside its own ideal-gas pressure, and a `PPA` pin sets the density at the state's temperature.
- A refined level whose kept-row trailing edge was detected names its points file in its boundaries file (`file = "<level>.te.txt"` in place of `detect`) when every family the detection route covers was detected, so the run marks the line the refinement kept; otherwise a warning names the points file the run does not read.
- Audit gate G4 fails a trailing-edge line that a source chain no longer reaches (a shortened chain), and reports the level's and the source's trailing-edge lengths.
- omitted s_ref names the reference area and m2 unit without introducing a default area (FR-457; PFS-2081.112, API-003).
- 6DOF documentation lists case-sensitive freedom keys and force enums (FR-461; PFS-2081.115, API-006).
- the geometry build row-copy refusal names both required CLI options (FR-472; PFS-2081.116, API-007).
- Far-field post took a frame's lattice as the last points of the export and the plane by its point count, so a reused frame lattice followed by another probe entry, or a plane changed to another grid of the same count, was integrated with the wrong samples or the wrong area (FR-455 R4, PFS-2081.58).
- The far-field products of a `qsteady_rotor` point were skipped ("states no speed in the point's record"): the hub speed is read from the row's own quasi-steady record, as every other product reads it, signed once by the rotor's hand (FR-453 R8, PFS-2081.93).
- `CDI_NEAR_PRESSURE` and `CDI_NEAR_VORTICITY` were `NA` on every 26.125 point (FR-456 R2, FR-423, PFS-2081.98).
- Far-field post matched an unsteady run's probes without their recorded frames, taking the first coordinate convention that matched, so a declared lattice of a translated frame followed by a reference-frame entry at its reference positions read that entry's velocities. A set is now matched only among the points of the frame it was recorded in, in that frame's coordinates, and a set found twice is refused (FR-455 R4, PFS-2081.58, PFS-2081.102).
- The far-field matching tolerance grew with the distance from the origin, so a plane of another grid far from the origin was integrated with the recorded area. Each coordinate is now compared within the export's own printed precision, and a layout that precision cannot resolve is refused (FR-455 R4, PFS-2081.103).
- The plan said a rotor's Trefftz C added probe points while it reused the declared lattice the ledgers reuse; its state now follows the lattice it reads (FR-455 R4, PFS-2081.101).
- A declared `[[probes]]` lattice or plane the far field reused on an unsteady row kept only the histories it stated, so a `VX`-only declaration left `VY`, `VZ` and `CP_REF` absent and the balances `NA`. The plan now adds the missing histories at the same vertices, in the entry's frame, records them as `plots_added` and states their count (FR-455 R9, PFS-2081.99).
- Planning reused a declared section distribution over several families, or `all`, for Trefftz A while post traced only a block of one named family, so post skipped and said a new run would add the distribution. Plan and post now share one rule: a block cuts one family (`all` on a geometry of one family counts), and an aggregate of several covers none, so the plan adds their own (FR-455 R2, PFS-2081.100).
- An odd azimuth count refused the harmonic order just below half of it (order 6 on 13 azimuths) and so kept the sole declared lattice from being reused; the aliasing rule is now 2 m_max >= n_psi at load and in planning (FR-454 R2, FR-455 R2, PFS-2081.107).
- OBJ-only deflection sweeps now retain solver meshes until the required sweep overlay is produced. Unreadable or empty selected surfaces give an explicit failure, and a previous overlay cannot appear current after a failed build (FR-470 R1, FR-472 R7, PFS-2081.108, REL4-001).
- Filtered sweeps keep the original one-based angle_deg positions in the overlay's variant cell labels, including the third angle and noncontiguous selections (FR-472 R7, PFS-2081.109, REL4-002).
- Refuse an existing sweep overlay without `--overwrite`, including disjoint `--only` selections. Authorized replacements retain the old overlay as `.previous` evidence and publish the new overlay atomically (FR-471 R9, FR-472 R7, PFS-2081.117, REL5-001).
- Sweep overlays support the same exported OBJ fallback as individual previews for quadrilateral saved meshes, preserving control-surface families and original angle ordinals (FR-472 R7, PFS-2081.118, REL5-002).
- The `strip_edges` documentation now describes shape and ends-option checks, trace-order coordinates that may be constant or descending, and nonfinite propagation (FR-451 R3, PFS-2081.119, REL5-003).
- Geometry preflight checks every promoted artifact, including scripts, logs and sidecars. Sweep variants remain staged until all solver runs, audits and the overlay succeed, preserving prior outputs on failure (FR-471 R9, FR-472 R7, SWEEP-01, SWEEP-02).
- A geometry build, one body or every variant of a sweep, is one transaction: every geometry is built and judged in its partial folder, and nothing moves until all of them passed their audit and the sweep overlay is written. A record kept in a partial folder now names its files where they are, including for a variant that passed beside one that failed; the command says why such a variant was not promoted, offers `geometry accept` for promoted geometries only, and `accept` refuses a partial folder. Each record is written after its files and the overlay after the last variant, so an interrupted build never leaves a record naming an absent file, and `--overwrite` completes it (FR-471 R3, R8, FR-472 R8, FR-473 R1, PFS-2081.120, REL6-002).
- An external FSI input can no longer declare an input or output under a name the archiving step owns, such as `call.json`, which the step's record silently overwrote in every call's archive. The name is refused when the input is read, at plan, and by the step before the program runs (FR-462 R3, R4, PFS-2081.121, REL6-001).
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
- cases.TEMPLATE_SETTINGS_LEFT_OUT and workspace.missing_log_warning are now public contracts for the post layer. (no requirement: PFS-2098.004 fix)
- Settings table adds an f<id>_kind column to distinguish enumeration codes from list lengths. Codebook version 1 retains its existing code meanings. (no requirement: PFS-2105.042 fix)
- `pyfs-workspace init` and `migrate-geometries` accept `--workspace PATH`, as every other subcommand but `archive` does; their positional root still works, and two different folders are refused (no requirement: PFS-2089.004 fix).
- A refinement file that selects a family with no `[families.<name>]` table warns, naming the family and the remedy, and `refine.json` records it under `missing_families_tables` (no requirement: PFS-2089.003 fix).
- `pyfs-workspace archive SIM_ID --workspace ROOT` names the campaign folder like the other subcommands; the positional `archive ROOT SIM_ID` still works and warns that it is deprecated (no requirement: the archive subcommand takes --workspace like the others).
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
- PFS-2084.004, PFS-2084.005, PFS-2094.040, PFS-2100.019, PFS-2104.032, PFS-2104.035 (no requirement: identifiers retained from the correction fragment).
- Script.park_input_file applies the shared case-insensitive collision rule.
  Script.observe_commands records accepted emissions within a scope; cases use
  these public APIs and Script.entry instead of private builder state. (no requirement: shared script APIs for existing workflows).
- Matrix selection precedes build and artifact resolution; excluded rows do
  not refuse a missing default build or change the selected run's HIDDEN mode. (no requirement: correction of excluded-row handling).
- CSV coefficient columns now retain at least six significant figures when five
decimals lose precision, including small induced-drag values. Readers must
accept scientific notation. Settings retain their stated form and drift
percentages keep five decimals. The optional legacy custom polar format keeps
its external fixed-width contract, with up to five decimals and fewer when needed to retain a leading blank. (no requirement: preserve small coefficient values when writing CSV).
- Forced reruns support Windows archive paths longer than the ordinary path limit
and tolerate an output that disappears during archiving. An archive
failure retains the old manifest records, and a later failure restores any
superseded record for which no replacement was written. Existing output
archives remain available for recovery. (no requirement: preserve records during Windows archive failures).
- An unsteady simulation with no resolvable window keeps its group polars from the last time step, now labelled kind: instant in the table entries, and post.log warns once naming the simulation. (no requirement: PFS-2105.011 fix)
- Custom polar fields now always keep a blank before each number; long values may be written with fewer decimals or digits, and a value that cannot fit raises ProductError. (no requirement: PFS-2105.012 fix)
- The inflow result is renamed InflowStationHarmonics. The old inflow_tools.StationHarmonics import warns and remains available until 1.0.0. The loads-harmonics class keeps its name. (no requirement: PFS-2089.007 fix)
- Native file lists are now relative to the products folder, matching product keys. Resolve these paths from the folder containing products.json. (no requirement: PFS-2089.001 fix)
- Sections measurement expected and emitted now list all block counts, including duplicates. (no requirement: PFS-2105.021 fix)
- Small dimensional CSV values retain significant digits where five decimal
  places would lose precision. This covers viscosity, time (including the
  native plots clock), positions, sectional loads, velocities, boundary-layer
  lengths, and dimensional rotor and group columns. Coefficient precision
  follows the significant-digit rule above. Readers must accept scientific notation in physical columns. (no requirement: PFS-2105.041 fix)
- A probe history containing `NA` or blank cells keeps its other values and
  produces a probes table. Previously one such cell could skip the whole table. (no requirement: PFS-2105.016 fix)
- Malformed recorded reduction windows are listed under that reduction's
  `skipped` key instead of aborting the post. Each window must contain two
  bounds, the first and last solver steps. (no requirement: PFS-2095.016 fix)
- Truncated VTK vector blocks raise `IncompleteOutputError`; malformed vector
  rows and non-UTF-8 frames raise `MalformedOutputError`, instead of raw Python
  indexing, conversion or decoding exceptions. (no requirement: PFS-2095.020 fix)
- A failing post keeps its original exception if a log write, log close or
  interrupted-manifest write also fails, including when the log reader sees
  partial JSON from that failed rewrite. The secondary failure is attached
  as an exception note. A log failure after a successful post still raises. (no requirement: PFS-2086.002 fix)
- A rerun whose export now declares zero sections or zero probe points retires
  the previous table under both archive settings. Under `--force-overwrite` it
  removes the old file and records the skipped product. (no requirement: PFS-2100.004 fix)
- Harmonics now require angular coverage as well as distinct sample counts.
  See [the fit definition](definitions/the-per-station-harmonics.md) for the
  180-degree maximum-gap rule, omitted terms and `HarmonicFit.reason`. (no requirement: PFS-2086.007 fix)
- The CLI scheduler regression now exercises the scheduler on Windows and isolates its selected profile. The mark-failed mutation test follows the per-point implementation. Command parsing, record marking, renaming and sweep collection retain their behavior while shared steps are factored into helpers to satisfy source limits (no requirement: test and internal helper changes, no behaviour change).
- Workspace storage and batch commands read one end rule for a grouped job: the end record, the job log, every `job_end_files` glob, or a point whose wall-clock state says it fired; delete-sims, free-space and sync now treat a clock-stopped batch as ended, as collect does (no requirement: PFS-2094.041, PFS-2094.044 fix).
- Sync and free-space share one log-name rule: `FS_runtime_output.txt`, `FlightStreamLog.txt`, `*_log.txt`, `*-log.txt` and `*.log`, in any case (no requirement: PFS-2087.002 fix).
- `ledger diff` normalises each executed script against its own run root and words a changed command as `a ...` and `b ...` (no requirement: PFS-2103.013 fix).
- `show` reads only the end of an evidence file and reports a binary file by size and sha256 (no requirement: PFS-2101.004 fix).
- `log --sims 20` no longer selects simulation `20-b`; a row's own `sim_id` or `sims` decides before its text (no requirement: PFS-2094.043 fix).
- A thin blade's rows all run from the leading edge, and a blunt trailing edge ends the mean line at the midpoint of its base (no requirement: PFS-2099.001, PFS-2099.002 fix).
- A thin blade cut from a multi-body OBJ carries only the mesh operations that act on it, and names the ones left out in its sidecar (no requirement: PFS-2099.003, PFS-2099.013 fix).
- Refined meshes order faces within one source face by vertex index, then distance, so a millimetre mesh orders as a metre one does, and a one-row or one-column grid is written in the source's own run (no requirement: PFS-2099.019, PFS-2099.018 fix).

### Removed

- `farfield.rothalpy` and `farfield.irreversible_deficit`, with no deprecation release: both apply to an Euler CFD field, where total enthalpy and entropy exist, and no FlightStream output carries either; a call refuses, naming ITACA, where they went for evaluation (FR-458).
- `farfield.lattice_dataset` and `post.dataset_to_points`; a call refuses, naming the replacement (FR-457 R3).

## [0.39.0] - 2026-10-11

### Added

- **A grid can keep the spanwise width of its row of panels at another component**
  (FR-430). A grid family with a trailing edge asked to keep its first row refines the row
  between each end station that meets another component and the station next to it
  chordwise only, so the row's spanwise width and the mid-point of its trailing-edge edge are
  the source's at every factor; every other row is refined chordwise and spanwise as before.
  Three routes ask it and give the same level: `keep_first_row = true` in the family's
  `[families.<name>]` table of the refinement file, `pyfs-matrix refine --keep-first-row
  FAMILY[,FAMILY...]`, and `refine_mesh(..., keep_first_row=["Wing", "Tail"])`. An end
  station is an interface when an edge of it is shared with a family of another component.
  The trailing edge is the one listed in the points file, else the detected one, and the
  family's entry of `refine.json` states which (`trailing_edge`, `"points file"` or
  `"detected"`) and the kept end stations (`kept_rows`); a detected one adds
  `trailing_edge_points`, the mid-points of the line detected on the source, from which the
  audit counts the source's trailing-edge chains with the listed edges (G4), so a detected
  line that a listed edge continues is one chain. Refused before any work, ending
  "Nothing was written.": a remeshed, axial or circumferential, multiblock or unrecovered
  grid, a grid without a trailing edge or with no end at another component, a grid
  remeshed because it shares nodes with a grid refined first, kept rows that leave no
  spanwise interval, and a family the mesh does not hold or the selection leaves out.
- **`MAX_ITER_REACHED`, a terminal status for a steady point stopped at its requested
  iteration limit without settling** (FR-434, amending FR-46). It is recorded when the
  iteration counter of the point's evidence (the solver log, else the loads footer) equals
  the requested limit and the residual history of the solver log shows the final residual
  above the convergence limit. It is not a failure: the post writes every product of the
  point with one WARNING in `post.log` naming the point and the limit, `run --resume` does
  not run it again, `status` counts it apart from the converged points, and the cost
  estimate, `delete-sims` and the grouped collect read it as an ended run. The record keeps
  `iterations` for the counter reached and gains `iterations_requested`, written only for
  this status. A point that lacks either piece of evidence, and an unsteady point, keep
  `COMPLETED_MAX_ITER`.
- **A reference can declare the surfaces of a study, so one setup, pproc and reference
  serve every model of it** (FR-435, amending FR-275 and FR-73). A top-level `[study]` table
  of the reference artifact with one key, `surfaces`, declares the study's vocabulary. On a
  row citing such a reference, a name the vocabulary holds and the row's model does not
  carry is skipped, key by key, in the setup's `delete_surfaces`, `analysis_families`,
  `vorticity_drag_families`, `axial_separation_families` and `base_region_operations`
  boundaries and in the pproc's `base_regions` and `[groups]` members; the plan says each
  skip once per artifact, key and name as a WARNING naming every row concerned, and the run
  record of each point lists them in `skipped_names`. A name neither the vocabulary nor the
  model holds is a misspelling, and the row is BLOCKED naming the artifact, the key, the
  name and the vocabulary. A reference without `[study]` reads as before.
- **`pyfs.toml` and `pyfs.local.toml`, the workspace's defaults of the command options**
  (FR-436). `pyfs.toml` at the workspace root, meant to be versioned, and
  `pyfs.local.toml` beside it, this machine's overlay read over it key by key, hold an
  optional `schema_version = 1`, a `[defaults]` table (`fs_version`, `hpc`, `cost_file`,
  `runs`, `accept_unregistered_build`, `fs_exe`, `point_name`, `recipe`, `workflow`,
  `ignore_missing_families`, `check_frozen`, `progress_every`, `local`) and a `[log]` table
  (`console`, `pproc_warnings`). An option typed on the command line wins over
  `pyfs.local.toml`, which wins over `pyfs.toml`, which wins over the package default. A key
  that acts on one invocation, a key no command takes, `workspace`, another table, a value of
  the wrong type and invalid TOML are each refused before any work, naming the key and the
  file. `plan.json` and every run record name each value taken from a file and its source in
  `settings_sources`. `pyfs-workspace` reads the same files and takes the console level only.
- **The acceptance of an unregistered build by a file** (FR-436 R7).
  `accept_unregistered_build` in `[defaults]` accepts the installed build for the
  workspace, and `accept_unregistered_build = true` on a table entry of
  `inputs/executables.local.toml` accepts that entry's build only; the key is refused in
  `inputs/executables.toml`. The run warns as `--accept-unregistered-build` does, and the
  plan and the records name the source of the acceptance.
- **`--log-level quiet|normal|verbose` and the `--no-` form of every boolean a file can set**
  (FR-436 R5, R6). Every command that takes `--verbose` takes `--log-level`; `quiet` shows
  the errors, the final summary line and the package signature, and `logs/activity.log`
  keeps its full detail at every level. `--no-accept-unregistered-build`,
  `--no-check-frozen`, `--no-local` and `--no-pproc-warnings` set the option to false for
  one command whatever the files state; an option typed with its `--no-` form, and
  `--verbose` with another `--log-level`, are refused by the parser.
- **`pyfs-matrix refine --out DIR` and `pyfs-matrix audit-mesh --out FILE`** (NFR-45 R2),
  the option name their sibling commands use (`rebuild --out`, `pyfs-workspace ... --out`):
  the folder the level goes to, and the CSV of the audit's figures.

### Changed

- **A quoted `--sims` holding several ids is several ids** (NFR-45 R2). The commands that
  read `--sims` as one value (`mark-failed`, `rebuild`, `delete-sims`, `post`, `collect`,
  `status`, `log`) read a blank or a tab between ids as a comma: `--sims "2006 2007"` is
  the two ids 2006 and 2007, where it was the single id `20062007`. Every form accepted
  before (`2006,2007`, `[2006,2007]`, `2006, 2007`) reads the same ids.
- **A long automatic level tag is a summary and a short hash** (FR-433). A tag built from
  the selection keeps its form while it is at most 32 characters; a longer one becomes
  `R-<n>fam-<hash>`, the number of selected families and the first 8 hexadecimal
  characters of the SHA-256 of the canonical selection, so a selection of many families
  writes a folder name that fits on Windows instead of failing after its work.
  `refine.json` lists the selected families under `tag_selection` for such a tag. A
  family that keeps its first row writes `k` in its part of a short tag (FR-430 R8).
- **The refusal of a sweeper export with an unknown header names the column that differs**
  (NFR-45 R2): for each known layout, the first differing column with its position, the
  expected name and the name found, or the counts when the header is a prefix. The
  `mark-converged` help names the single quoted value and the mixed shape.
- **`refine` and `audit-mesh` refuse a `[trailing_edges] detect` the workflow refuses**
  (NFR-45 R3). Both read `detect` through the workflow's reader, so a shape it refuses (a
  word other than `"auto"`, a key it does not read, an empty surface list, `file` and
  `detect` together) is refused before any work in the same words, ending
  `Nothing was written.`; 0.38.0 ignored such a shape in the mesh verbs.
- **The user guide and the cheatsheet are built from the release sources** (NFR-46). The
  user guide compiles to its end, guide 04 compiles to the page count its source states
  with no overfull box, and each PDF names the release it was built from. The user guide
  PDF is available from the documentation downloads, and each of
  the two PDFs has its build log beside it.
- The mesh how-to and reference pages, the status pages, the reference artifact page and a
  new page on the workspace settings files describe the changes above (FR-430 to FR-436,
  NFR-45).

### Deprecated

- `pyfs-matrix refine --out-dir DIR` and `pyfs-matrix audit-mesh --csv FILE` (NFR-45 R2).
  Each is a deprecated alias of `--out` on its command, gives the identical result and
  warns once that it is deprecated; an alias given together with `--out` is refused, naming
  both.

### Fixed

- **A point submitted without a recorded list of its solver logs is still
  `RAN_MISSING_LOG` when its log is gone** (FR-413 R8). When a record carries no
  `submission["declared_logs"]`, the names of its solver logs are read from the job's own
  script on disk, so collect, the grouped collect and rebuild decide such a point as
  `RAN_MISSING_LOG` instead of waiting on it. A recorded list, an empty one included,
  stays authoritative and is never extended by the script's names.
- **A neighbour family the band covers whole is rebuilt whole at factor 1** (FR-431). When
  the band of two face layers beside a refined grid holds every face of an unchanged
  neighbour, the refinement wrote no level and stopped on an internal error; it now rebuilds
  that family whole at factor 1, as if stated `factor = 1`, `method = "remesh"`, warns once
  naming the family and its face count, and records in `refine.json` `"method":
  "rebuilt_whole"`, `"reason": "band_covers_family"`, `"band"` and `"faces"`.
- **A family rebuilt at factor 1 beside a refined side takes the spacing of the shared
  edge** (FR-432, RPT-164). The target size of the rebuilt family along the shared curve is the mean
  length of the new shared edges at each node, interpolated back to the family's own
  target over two face layers, so the edges crossing from that curve no longer stretch to
  several times the new shared edges and no face falls under the zero-area threshold of
  gate G1. `refine.json` records `shared_edge_target_m` (minimum, mean and maximum) under
  each rebuilt family and under the band of an unchanged neighbour; a family that shares no curve with a refined side is unchanged.

### Known limitations

- `MAX_ITER_REACHED` needs both the counter at the requested limit and a readable residual
  history: a point with no solver log, a run whose iterations are forced with no residual
  threshold, and a point whose evidence states no counter keep `COMPLETED_MAX_ITER`. A
  manifest holding the new status is refused by a 0.38.0 reader (FR-434 R2, R5).
- Keeping the first row holds a geometric invariant, the interface row's width and the
  place of its trailing-edge edge; it does not claim that a study holding it isolates the
  discretisation from every other effect of refinement (FR-430). The levels are verified
  offline on synthetic meshes; their confirmation on a real multi-component panel mesh is a
  release receipt outside the offline suite.
- The 8-character digest of a summary tag tells selections apart; it is not a guarantee
  against collision (FR-433 R3).

### Internal

- The tests of each requirement of the release carry its marker: FR-413 R8 by P0390-COLLECT,
  FR-430 by P0390-FIRSTROW, FR-431 by P0390-BANDSWALLOW, FR-432 by P0390-ZEROAREA,
  FR-433 by P0390-TAGLEN, FR-434 by P0390-ITERLIMIT, FR-435 by P0390-R02, FR-436 by
  P0390-R03, NFR-45 by P0390-REV38 and P0390-REV37, NFR-46 by P0390-PDFS.
  FR-413 is proved by the P0390-COLLECT tests.
  FR-430 is proved by the P0390-FIRSTROW tests.
  FR-431 is proved by the P0390-BANDSWALLOW tests.
  FR-432 is proved by the P0390-ZEROAREA tests.
  FR-433 is proved by the P0390-TAGLEN tests.
  FR-434 is proved by the P0390-ITERLIMIT tests.
  FR-435 is proved by the P0390-R02 tests.
  FR-436 is proved by the P0390-R03 tests.
  NFR-45 is proved by the P0390-REV38 tests (the 0.38 findings) and by the P0390-REV37
  tests; NFR-45 for the 0.37 findings: P0390-REV37.
- mypy recount 2026-10-11: 159 errors in 16 of 296 modules; the three new modules of 0.39.0,
  `workspace/_settings_file.py` and the two `workspace/_refine/_remesh_*` modules, are clean and not
  exempted (RPT-029).
- The registered findings of the 0.37.0 and 0.38.0 reviews are fixed, each with a test or
  a named page, or closed with a justification in the release's rigor register (NFR-45).
  The help of the simulation ids lives beside the one reader of `--sims`; the boundaries
  file's `[trailing_edges]` table has one reader; no private name crosses the package
  boundary of `pyflightstream.workspace`.
- PUSH-W12-QA-3: the history of the four FR-424 R7 cherry-picks that share one commit
  message is kept as published; a published branch is not rewritten, and the register
  records the justification (NFR-45 R5).
- R37-11: the original 26.125 probe-campaign exports behind the two fixtures of
  tests/tier1_offline/fixtures/s10_26125 were not found, so the fixtures are not compared
  with the originals byte for byte; their recorded source hashes in PROVENANCE.md stand
  (NFR-45 R5).

### Migration

- Read [Migrating to 0.39.0](docs/migrating-to-0.39.0.md). Nothing is removed. A
  workspace without `pyfs.toml`, `pyfs.local.toml` and a `[study]` table reads its inputs
  as before; the changed readings are the new status `MAX_ITER_REACHED`, which a 0.38.0
  reader refuses, a quoted `--sims` of several ids, and the summary tag of a long
  selection. `--out-dir` and `--csv` of the mesh verbs are deprecated aliases of `--out`.

## [0.38.0] - 2026-10-06

### Added

- `pyfs-matrix refine MESH [FACTOR] [--families A,B] [--chordwise F] [--spanwise F]
  [--config FILE] [--out-dir DIR] [--overwrite]` refines or coarsens a panel mesh from its
  OBJ into a new geometry folder, a level, `<out-dir>/<stem>_<tag>/` (by default beside the
  folder holding the source), and never modifies the source or its folder. FACTOR multiplies
  the intervals of each index direction of a grid family (2 doubles them, 0.5 halves them)
  and divides the target edge length of any other family; `--chordwise` and `--spanwise`
  replace it in one direction of the grid families, and `--families` selects the families to
  change. A family whose faces form a structured grid (a sheet, or a tube whose ends are open,
  closed by a pole fan or closed by a zipper) is resampled by a cubic spline that keeps the
  trailing edge, the leading edge and the end stations, and is written in the source's face
  order; any other family is remeshed into triangles projected onto the source surface,
  keeping open boundaries, the trailing edge and ridges as curves. The level holds
  `<stem>_<tag>.obj`, the trailing-edge points file rewritten from the new mesh, the
  boundaries file naming it, `<stem>_<tag>.refine.json` (per family the method, the reason,
  the layout and the counts before and after) and the audit. The tag is `R2`, `R0p5`,
  `R1c1p5s0p7` or `R-<family><factor>-...`, or the file's `[refine] tag`. Every refusal comes
  before any file is written and ends with "Nothing was written."; remeshing needs the
  `geom` extra. From Python: `pyflightstream.workspace.refine_mesh`, which returns a
  `RefinedMesh` (FR-424).
- The refinement file, `--config FILE` or `<stem>.refine.toml` beside the mesh, read for the
  factors when the command gives none: `[families.<name>]` tables with `factor`, `chordwise`,
  `spanwise` and `method` (`"auto"`, `"grid"` or `"remesh"`), and `[refine] tag`. A family
  that shares nodes with a refined grid is rebuilt on the grid's new nodes, an unchanged one in
  a band of two face layers, so the level stays one welded mesh with the source's open
  boundary loops. `[components]`, `NAME = ["A", "B"]`, writes several families as one family
  of the output OBJ and names it in the level's boundaries file: the dummy families that keep
  a region structured in the pre-processor reach the solver as the component (FR-424,
  FR-425).
- `pyfs-matrix audit-mesh OBJ [--against SOURCE] [--csv FILE]` audits any OBJ, alone or
  against its source, and writes `<stem>.audit.json` beside it: the gates G1 to G6 (topology,
  orientation, open boundary loops, trailing edge, shared nodes, the faces of a grid at factor
  1), relative checks of the 95th percentiles of skewness, warp and size growth against the
  source's, and figures reported and never judged (aspect ratio, the pre-processor's quality
  counts, the face quality ratio, faces on the plane y = 0). It exits 0 when every gate and
  check passes, 1 when one fails (the audit is still written) and 2 on a refusal; `--csv`
  writes one row per family and figure. Every `refine` audits its level against its source
  the same way and reports a failure as a warning. From Python:
  `pyflightstream.workspace.audit_mesh`, which returns a `MeshAudit` (FR-426). A level
  written with `[components]` is audited against the union of each component's members in the
  source, and a figure within 1e-6 of a limit or a floor meets it.
- A smooth tube, a tube of quadrilaterals with no trailing edge and no edge sharper than the
  ridge angle, is a grid family: its seam is the lowest source node index on its first end
  station, its circumferential direction is a periodic cubic spline, it writes no
  trailing-edge points, and at factor 1 it is the source (FR-424 R15).
- A multiblock family, an all-quadrilateral family cut into four-sided patches along the grid
  lines through its singular nodes, is recovered and resampled patch by patch with each shared
  side resampled once, so neighbouring patches hold the same nodes; `refine.json` reports the
  layout `multiblock`, the patches and each patch's rows and columns, and `--chordwise` and
  `--spanwise` are refused on it, naming it (FR-424 R16).
- `elements = "quad-dominant"`, in a family table or in `[refine]`, pairs the remeshed
  triangles of a family into convex quadrilaterals (angles 30 to 150 degrees, warp at most 10
  degrees), never across a curve, and reports the quads, the triangles and the quad share per
  family; `"triangles"` stays the default, and the key is ignored on a family that resolves to
  a grid (FR-424 R17).
- `[periodic]` in the refinement file, `axis`, `origin` and `copies`, refines a periodic
  sector so that its two cut faces still match node for node; a source whose cut faces do not
  match is refused naming the largest distance (FR-427).
- `axial`, `circumferential`, `axis` and optionally `origin` in a `[families.<name>]` table
  refine a body (a fuselage, a nacelle, a spinner) along its axis and around it
  independently; the tag carries them as `a<axial>t<circumferential>` (FR-428).
- `derive_thin_blade`, `ThinBlade` and `thin_blade_path` are public names of
  `pyflightstream.workspace`: a script derives the thin blade of `pyfs-matrix degenerate` with
  the command's files and refusals (FR-429).

### Changed

- **`pyfs-matrix degenerate` calls the public `derive_thin_blade`.** The command calls
  `pyflightstream.workspace.derive_thin_blade`; its files and its refusals are unchanged, and
  `pyflightstream.workspace._degenerate` stays importable with the same objects (FR-429).
- The Origin lines of the SRS that quoted a person or spoke in the first person name the
  scope item, the plan node or the report instead; no other text of a box changed (NFR-43).
- The `pyfs-matrix` cheatsheet names `refine` and `audit-mesh` with every option, and is one
  ten-page guide again (FR-328). The guides explain the grouped run: `plan` and `run` with
  `--batch N` or `--polar-sweep`, the batch folder and its collect, what a grouped plan leaves
  out, and `--hpc` among several profiles (FR-410).
- The mesh how-to and reference pages describe refining a mesh and its refinement file,
  and the audit's gates, checks and exit status (FR-424, FR-426).

### Known limitations

- The audit's relative checks warn only when a level's 95th percentile exceeds its limit:
  the skewness above the source's plus 0.05, the warp and the size growth above the larger
  of the source's and 10 degrees or 2 (FR-426 R3). A body refined with different `axial` and
  `circumferential` factors stretches its faces and can exceed the skewness limit: on the
  tested cylinder, axial 2 with circumferential 1 and the reverse both warned (95th
  percentile 0.42 and 0.49 against the source's 0.017, limit 0.067). The level is written;
  read the reported values before taking a warning for the stretch asked for (FR-428).
- A lateral grid that mixes quadrilateral and triangulated cells is remeshed under `auto` (a
  family of quadrilaterals only is recovered as one grid, a smooth tube or a multiblock), and
  refused under `method = "grid"` naming the reason (FR-424 R9).
- Pairing remeshed triangles into quadrilaterals can raise the audit's growth and skewness
  figures, a quadrilateral beside a triangle reading as a size jump and a paired rhombus as
  skewed: the tested two-family plate remeshed quad-dominant at factor 2 warned on both
  (skewness 0.47 to 0.50 against a limit of 0.35, growth 2.2 to 2.7 against a limit of 2).
  A quad-dominant level warns only when its figures exceed the limits; read the reported
  values (FR-424 R17, FR-426 R3).
- Across a multiblock patch side the surface is continuous, not smooth: no spline crosses it
  (FR-424 R16).
- A tube closed at both ends by pole fans is recovered as a grid only while each pole fan has
  its own size: when the fan size of a pole is shared by more than two nodes, or equals the
  valence of a near-pole ring (5 on split cells), the tube is not recovered as a grid and is
  remeshed, never refined as a wrong grid (FR-424 R9).
- A triangulated tip cap (any triangulation other than a pole fan or a zipper) is not part of
  a grid. Give it a family of its own in the pre-processor, refine the blade as a grid, and
  merge the two with `[components]` (FR-425).
- Whether a refined level gives the solver the result of a mesh made at that size in the
  pre-processor is validation, not verified offline: RPT-162 reports one isolated propeller
  on 26.124, where the level refined at factor 1 reproduces the source level.

### Internal

- mypy recount 2026-10-06: 159 errors in 16 of 293 modules, on `rel/0-38` with every package merged;
  the eleven new modules are clean and none is exempted (RPT-029).
- `python scripts/run_guards.py` runs the cross-cutting guard tests in one pytest invocation of
  four workers and prints each guard file's result: exit 1 when one fails or runs no test, 2
  when a listed file is missing. A test that pins the digest of rendered text holding a path
  folds every backslash to a forward slash first, so the digest is the same on Windows and on
  Linux (NFR-44).
- The refinement and the audit are the private package `pyflightstream.workspace._refine`;
  the command layer reaches it only through `refine_mesh` and `audit_mesh`. Grids and the
  audit need numpy alone; remeshing imports the `geom` extra's spatial index only when a family
  is remeshed (RPT-161).

### Migration

- Read [Migrating to 0.38.0](docs/migrating-to-0.38.0.md). Nothing is removed, and no input
  key, command or product of 0.37.0 changes. The release adds two verbs, `pyfs-matrix refine` and `pyfs-matrix audit-mesh`, and
  seven public names of `pyflightstream.workspace`; `pyflightstream.workspace._degenerate`
  stays importable.

[Unreleased]: https://github.com/nevesgeovana/pyflightstream/compare/v0.41.0...HEAD
[0.41.0]: https://github.com/nevesgeovana/pyflightstream/compare/v0.40.0...v0.41.0
[0.40.0]: https://github.com/nevesgeovana/pyflightstream/compare/v0.39.0...v0.40.0
[0.39.0]: https://github.com/nevesgeovana/pyflightstream/compare/v0.38.0...v0.39.0
[0.38.0]: https://github.com/nevesgeovana/pyflightstream/compare/v0.37.0...v0.38.0
[0.34.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.34.0
