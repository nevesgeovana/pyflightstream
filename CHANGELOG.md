# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [Unreleased]

### Added

- **`inputs/input_template.md`, a template of every input file (G47).**
  `pyfs-workspace init`, `pyfs-matrix plan` and `pyfs-matrix post` write it at
  the root of `inputs/`, rewriting it only when its content changes: one section
  per kind of input file a user writes (the run matrix, the setup, the pproc,
  the reference with its rotor, actuator and point blocks, the named reference
  points, the geometry sidecar of a saved simulation and of a raw mesh, the
  trailing-edge points file, the provenance record, the actuator radial thrust
  profile and the probe survey of `profiles/`, the STRUCTURED custom free
  stream, the HPC profile, and the build registry with its local overlay), each
  saying what the file is for and where it lives, with a commented, complete
  example to copy to the path its block's title names, and links to
  `pproc/INPUTS.md` and to the page of the documentation that covers it. The
  examples cite each other, so the matrix plans against the rest as written.
  Generated from the code where the format is the code's: the matrix header is
  the layout's registry, the values a comment lists are read from the
  registries that check them, and each section names, with the reason, every
  key of the glossary's tables its example leaves out. The suite writes every
  example where its title says and reads it with the reader the run uses, holds
  every registered key to an example or to that list, and refuses a misspelled
  copy of each. Library: `pyflightstream.post.write_input_template` and
  `INPUT_TEMPLATE_NAME`; `pyflightstream.post.guides.input_template_markdown`.
- **An actuator disc takes its speed from the advance ratio (G20).** A row naming
  a disc and stating `ADVANCE_RATIO` (in its flight condition, swept or held) and
  no `ACTUATOR_RPM` turns the disc at n = V / (J D) by the rotors' rule, with the
  DISC's own diameter (twice its `tip_radius_m`) and the row's velocity; the hand
  stays the block's `rpm_sign`. A row stating neither is refused naming both.
  A steady row whose disc speed moves with a swept advance ratio runs one job
  per point, as a flow sweep does, so each point sets its own speed.
- **A local run's log reads at a glance, and an unsteady point says how far it
  is (G43).** A run opens with a banner naming the campaign and how many points
  it runs, numbers each point (`(3 of 17)`, a steady job its range, `(1-3 of
  17)`), and closes with a table of how the points ended, a job's points counted
  one by one, and the time it took. An unsteady point that carries its step
  counter prints a progress bar with its step, its share and the time so far
  every N completed time steps, read from the run's own counter while the
  solver runs, never from what the solver prints: `pyfs-matrix run
  --progress-every N` (10 by default, 0 for none); library
  `run_matrix(progress_every=...)` and `LocalExecutor(progress_every=...)`.
- **`CampaignErrors.records`.** Every record the failing call wrote, failed or
  not, beside `failures`; `pyfs-matrix run` reads it to tell a run that also
  submitted a point, which writes no table.
- **`pyfs-matrix run --force-rerun-all [--sims SIM ...]` (G44).** Every recorded
  point of the matrix, or of the simulations `--sims` names, is archived and runs
  again, a steady row recorded as one job as one job; one line gives the count of
  points and jobs before anything runs. `--sims` narrows the run to those
  simulations. Refused beside `--resume` or `--force-rerun`, for an id the matrix
  does not carry, and when nothing is recorded. Library: `run_matrix(...,
  force_rerun_all=True, sims=[...])`.
- **The plan warns when a pproc plot group takes the rotor table's plot name
  (G42).** A group named like the automatic `ROTOR_<ALIAS>` group, such as
  `ROTOR_{family}` in a rotor's own frame, emits the names the rotor table reads,
  so the run keeps that group and writes no global-frame history for the rotor,
  and the post cannot write its table. `pyfs-matrix plan` and `pyfs-matrix run`
  now say so before a seat is spent, naming the pproc, the name and the rotor,
  and suggesting a rename (`SHAFT_{family}`). Nothing is refused or renamed.

### Fixed

- **Three input files are read as documented (found by the input template's
  test, G47).** A reference whose recorded `[rotor]` states `hub_radius_m`, a key
  of that table, was refused as "an actuator disc with no kind", because the
  guard for a disc that forgot its `kind` read the key as a disc's; a table of
  the model's own is no longer judged by that guard. A pproc stating the
  top-level `vtk_variables` (documented since 0.25.0) was refused as a groups
  file of the shape before 0.11.0, because the reader's list of the model's own
  top-level lists was kept by hand and lacked it; it is now read from the model.
  And a steady row whose pproc draws a probe rectangle or circle (FR-79) failed
  to plan on every build, its `NEW_PROBE_POINT` lines missing the required
  `type`; they now state `VOLUME`, as the package's other probe points do.
- **Naming one point of a recorded steady job redoes the whole job (G37).** A
  steady row runs as one warm job recorded under the row's id. `--force-rerun`
  naming the job redid every angle, but naming one of its points, by its point
  name or its run_id, archived the job's record and ran that point alone and
  cold, leaving the other angles in no record. Now any point of a recorded job
  resolves to the whole job before anything is archived, and a warning lists the
  points that run again. A point of the row recorded on its own after the job
  ran (a new angle run with `--resume`) is archived with the job's record, by
  `--force-rerun` and `--force-rerun-all` alike, so the new job's record is the
  only active one.

### Changed

- **A run that submits to a cluster does not post (G43).** Its points are in a
  queue with no outputs yet, so the post could only print a skip per point: the
  run now writes no product and no sweep table and ends with one line saying how
  many points it submitted and ran here, and the command that collects and then
  posts (`pyfs-matrix collect --workspace <root>`, `--watch` to wait). A run whose
  every point ran here posts as before.
- **An unsteady or rotor row refuses `COLD_START` at plan (G36).** The key clears
  the solution between the points of a steady sweep over the attitude; every
  point of an unsteady row is its own job and starts cold, so the key, true or
  false, changed nothing there and is now refused naming it. The glossary
  says so. See `docs/migrating-to-0.28.0.md`.

### Owed

- **The submitting half of the additional post** (0.29.0; the approved 0.28.0
  scope leaves it out): completing an extraction handed to a scheduler.

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

## [0.27.0] - 2026-09-24

THE BASIC GUI STEPS THROUGH pyfs. A raw OBJ or STL runs from a matrix row with
its unit declared, its mesh operations in the declared order and its trailing
edges read from a node file by default or detected; the solver saves its own
plots; a volume section, an actuator disc and a custom free stream sit on a
row; the loads' surfaces, units and inviscid part are setup keys; every point
keeps its final saved simulation, and a new pproc extracts from it without
solving again. Every table the post writes opens with POL and holds no comma
in a cell. Each route is proved on 26.124 by a licensed run (RPT-069 to
RPT-073). A reader of the post tables changes one thing: the POLAR column is
gone (`docs/migrating-to-0.27.0.md`).

### Added

- **`pyfs-matrix run --local` keeps a run on this machine.** Linux is the
  cluster (FR-99): a workspace carrying a submission profile submits from
  Linux and runs locally on Windows, with no cell to remember. The flag keeps
  a Linux run local, for a workstation or a smoke test on the machine itself;
  the executable resolves as on Windows, and each point the switch kept on a
  machine that would have submitted (Linux with a profile) records
  `forced_local` on its executor entry. It changes nothing, and records
  nothing, on a machine that would not have submitted or beside an executor
  the caller supplies; it is refused beside any executor that submits, the
  package's own or a caller's adapter implementing the `Submitting`
  protocol. `LocalExecutor` takes `forced_local` by keyword only.
- **`post.log.json` beside `post.log`.** The same records, machine-readable:
  the header (`version`, `workspace`, `matrix`, `time`, `check_frozen`) and
  `records`, one per WARNING line in the same order, each with `point`,
  `product`, `message` and `remedy` (`null` where the warning states its
  remedy inside its message). Both files are written from one list of
  records on a clean, a failed and an interrupted post, so they cannot
  disagree. `products.json` names it under `log_json`, and a rebuild
  archives it with the log (R02).
  A manifest holding a forced-local record needs 0.27.0 to read it: an
  older reader refuses the key (measured 2026-09-23 against the 0.26.0
  schema), so post such a workspace with the same version that ran it.
- **The axes and signs of every emitted coefficient are published in one
  place**, `help()` and the conventions page, and each family says whether it
  is scored against the solver's own recorded output, and by which test, or
  not yet, and which export it waits for. The emitted steady polar row is now
  scored column by column against 48 recorded loads exports, and the body-rate
  sense against the recorded rate probes (OPS-2011.01, RPT-063, FR-42).

- **Every point of a row naming a run type leaves its final saved
  simulation, now a written guarantee.** After the point's solve, first
  among its exports, the script saves the solver state as `<point file
  stem>.fsm`. It is collected into `sims/sim_<POL>/datapoints/DP-<point>/`
  and listed in the run record's `outputs`, with its sha256 in
  `outputs_sha256`, on every run type, on every build a run type renders on
  (25.000 renders none), and for each point of a steady sweep. Every
  workflow script already did this; the workflows page now states it and
  `tests/tier1_offline/test_saved_simulation.py` holds it. A case written in
  Python that declares its own `outputs` still exports exactly those (G11).
- **`pyfs-matrix plan` warns naming each `LEGACY` row whose `OUTPUTS`
  declare no `.fsm`**, because no final state of such a row is collected or
  hashed in its record. It blocks nothing; the row plans and runs as before
  (G11).
- **Each run record carries its geometry's boundary names** (`inventory`,
  in the solver's order as the script read them at `OPEN`, the name at
  position i being boundary i), on the point path and the steady one-job
  path alike. A run that opened no geometry declaring names (a `LEGACY`
  recipe, a file without a mesh block) writes no key.
  `CampaignWorkspace.recorded_inventory(record)` returns them, and for a
  record written before 0.27.0 reads them from the mesh block of the
  geometry file whose sha256 the record carries. A manifest holding such a
  record needs 0.27.0 to read it: an older reader refuses the key (measured
  2026-09-24 against the 0.26.0 `RunRecord`), so post such a workspace with
  0.27.0 (R03).

- **A workflow row imports an OBJ or STL.** `GEOMETRY: wing.obj` runs when
  `wing.boundaries.toml` beside it states the unit the file is written in,
  `[import]` `units` (a length unit `IMPORT` takes on the row's build;
  `OTHER` is refused), its surface names in the file's order, written by hand
  as `boundaries`, and its trailing edge (below). The script starts a new
  simulation, imports the point's staged copy in that unit and sets the
  simulation's length unit to metres, the unit of every length the reference
  and the row state; whether `IMPORT` converts the body from the file's unit
  is not measured on any build. A raw mesh without a unit is refused before
  any seat, naming the table, the key and the sidecar; so are an `[import]`
  table beside a `.fsm` and any other suffix. The run record of a point that
  imported a raw mesh carries the table as `mesh_import`; a point that opened
  a `.fsm` writes no such key (G01).
- **The mesh operations of an import are declared with the geometry.**
  `[[import.operations]]` in the sidecar of a raw mesh scales, renames,
  mirrors (joined to its source), translates (in the `[import]` unit) and
  rotates surfaces named by the file's names, in the reference frame. They
  are emitted in the order written, right after the import, and the renamed
  names are the boundary inventory a row cites. An order the solver's phases
  cannot emit is refused naming both operations; a name absent at its step, a
  name two surfaces carry and a rename onto a name in use are refused before
  anything is emitted (G03).
- **A raw mesh declares its trailing edge in its sidecar** (G02, T06).
  `[trailing_edges]` with `file = "<points file>"` is the default route, with
  optional `type` (STANDARD unless written) and `tolerance`. The points file
  (a unit line, then one edge mid-point per line) is checked against the mesh
  when the row is bound, converted to metres, written as the solver's node
  file in the folder the point runs in, and imported with
  `IMPORT_WAKE_EDGES_FROM_FILE` on 26.124, where that command is verified by
  a compat probe; 26.122 and 26.123 are refused naming RPT-061, and earlier
  builds are refused. `detect = "auto"` or `detect = { surfaces = [...],
  sweep_angle = ... }` applies automatic detection only when written.
  `[wake_termination]` (automatic or by surface; on 26.124 it marked the root
  end of a twisted blade, RPT-069) and `[base_regions]` (`detect = "auto"`)
  apply only when written. Refused at plan: a raw mesh with no trailing
  edge; a table stating both routes or neither; a file-route row whose outputs carry no
  solver log, or that states `EXPORT_LOG: false`, which leaves its script
  exporting none (a machine whose HPC profile turns the export off and
  names a `native_log` runs the row, and the count is read from the log
  its scheduler writes); the file route beside an import operation that
  scales, mirrors, translates or rotates the body; a `.fsm` whose sidecar
  states any of the three tables. New names: `cases.TrailingEdgeMarking`,
  `cases.RawMeshConditions`, `SimCase.raw_mesh_conditions`,
  `MeshImport.moving_operations`, `MeshImport.names_after_renames`,
  `workspace.inputs.read_raw_mesh_conditions`.
- **A run that imports trailing edges is held to the solver's own count.**
  It writes the node file before the solver starts, hashes it into the
  record's inputs, and compares the solver's count of imported edges with
  the points it wrote: FAILED_SCRIPT when they differ, FAILED_INCOMPLETE_OUTPUT
  when no log was read, on the local path and at collect. The log is the
  collected one the assessor names or, for an assessor of the caller's that
  names none, the one collected output that reads as a residual history, as
  the package's assessor finds it. A point that matches no mesh edge is
  dropped by the solver in silence (RPT-061), and initialisation adds
  nothing to an import (RPT-065), so this count is the only warning of a
  wrong file. `results.imported_trailing_edges` reads the
  count; the sweep-job path now writes the files a script parks (G02).
- **A trailing-edge points file is checked against the mesh before the
  run** (T05): `read_trailing_edge_points`, `matched_trailing_edge_points`,
  `TrailingEdgePoints`, `write_trailing_edge_points` and `length_scale` in
  `pyflightstream.workspace.wake_edges`. Its unit line must name a solver
  length unit, and every point must lie within the tolerance of a mesh-edge
  mid-point; the first point that does not is refused by its line and
  position. `workspace.trailing_edge_midpoints` gives the mid-points of every
  trailing-edge mesh edge of a blade.
- **A probe specification for `IMPORT_WAKE_EDGES_FROM_FILE`**, and its 26.124
  row verified by the compat probe of 2026-09-24 (the qa wing's sixteen
  trailing edges imported and saved). The probe verifies only the import it
  wrote: exactly one import line, 16 edges for boundary `Wing`; another
  count, another boundary or a second import line is `broken`. The report of
  2026-09-24 was judged before that criterion and records the verdict, not
  the lines the solver printed; a re-run on 26.124 records them.

- **A steady point saves the solver's own plots, by default.** After its other
  exports and before its log, every point of a steady workflow row chooses a
  plot with `SET_PLOT_TYPE` and saves it with `SAVE_PLOT_TO_FILE`. The
  residual history goes to `<point>_plot_residuals.txt`, the load history to
  `<point>_plot_loads.txt`, and, where the pproc declares
  `[[sections.distributions]]`, the section Cp to
  `<point>_plot_cp_sections.txt`. Each file is the plotted series as text
  (RPT-067). It is collected into `datapoints/DP-<point>/`, hashed in
  `outputs_sha256`, and never read as a coefficient source. Each is an
  `[exports]` kind that `false` switches off (`plot_residuals`, `plot_loads`,
  `plot_sections_cp`), and `plot_sections_cp = true` without sections is
  refused. An unsteady row saves none, and a pproc stating one `true` on an
  unsteady row is refused at plan (G04).
- **`[exports] force_distributions = true`** saves
  `<point>_force_distributions.txt`, the per-panel pressure and viscous force
  coefficients of every surface, on every run type. It is off by default like
  VTK and CSV, exported once at the end of the run, and never written by an
  unsteady row's per-step exports (G10).
- **Setup keys for the loads analysis, on steady rows:** `analysis_families`
  (`SET_SOLVER_ANALYSIS_BOUNDARIES`, family names resolved like
  `vorticity_drag_families`); `load_units` (`SET_LOADS_AND_MOMENTS_UNITS`, one
  of COEFFICIENTS, NEWTONS, KILO-NEWTONS, POUND-FORCE, KILOGRAM-FORCE);
  `inviscid_loads` (`SET_INVISCID_LOADS`). They are stated after
  `START_SOLVER` on every point, and the solver's own spellings are aliases. A
  row of an unsteady run type stating one is refused at plan. A point whose
  loads table is not in coefficients writes no product row, and the post stage
  names the unit (G09).
- **Setup keys `vorticity_lift_model` and
  `unsteady_viscous_coupling_iteration`** reach `SET_VORTICITY_LIFT_MODEL`
  (every run type) and `SET_UNSTEADY_VISCOUS_COUPLING_ITERATION` (unsteady run
  types; refused on a steady row) before `INITIALIZE_SOLVER`. Each is checked
  against the command database for the row's build: the coupling step emits on
  25.100 and 26.000 alone, and neither runs on 26.124 (RPT-068), where a row
  stating either is refused at plan naming the report. The lift model stated
  beside `kutta_joukowski_lift = true` plans with a warning (G14).
- **A volume section, declared in the pproc and exported by every steady point
  (G05, FR-110).** `[volume_section]` declares ONE flow-field plane: `shape =
  "rectangle"` (`corners_m = [x1, y1, x2, y2]`, optional `refinement_layers`)
  or `"circle"` (`radii_m = [r1, r2]`, `points = [ipts, jpts]`), in a `plane`
  (XY, XZ, YZ) of a `frame` (`MRP` unless stated) at an `offset_m`, every
  length in metres, with `format` `vtk` or `tecplot`. Each point of a steady row cuts it after its solve and
  exports it to `<point>_vsec.vtk` or `<point>_vsec.dat`, collected into its
  `datapoints/DP-<point>/` and hashed in its record; a later point of a sweep
  deletes the previous section first. The five commands are verified one at a
  time on 26.120 to 26.124 and documented on earlier builds; the
  delete-then-create sequence is not measured. An unsteady or rotor row naming
  such a pproc is refused before anything is emitted.
- **An actuator disc on a matrix row (G06, FR-109).** A reference block of
  `kind = "actuator"` declares the disc (`frame`, `axis`, `offset_m`,
  `tip_radius_m`, `hub_radius_m`, `rpm_sign`, optional `blades`, `swirl`,
  `profile_units`). A row names it with `ACTUATOR`, gives its speed with
  `ACTUATOR_RPM` (a magnitude; the block's `rpm_sign` is the hand) and exactly
  one loading: `ACTUATOR_THRUST` (net thrust, N) or `PROFILE` (a file of
  `inputs/profiles/`, rows `r,F`, resolved and checked at plan; the solver
  reads the run's own copy, below under Fixed). Every run type emits it before
  the solver is initialised. `SET_PROP_ACTUATOR_PROFILE` ran on 26.124 under a
  licensed probe that measured the file form it reads (RPT-070); the thrust
  and enable commands ran with their effect unobserved, and a disc on unsteady
  and rotor rows is not measured. `helpers.actuator_disc` refuses the profile
  route on 25.000 and 25.100 before writing anything.
- **A custom free stream on a matrix row (G15).** `FREESTREAM: <stem>` names a
  file of the workspace's `inputs/freestreams/`, which `pyfs-workspace init`
  now creates: `<stem>.txt` in the manual's STRUCTURED form (a first line
  `Npts Mpts`, then Npts x Mpts rows `x y z vx vy vz`) or `<stem>.dat` in its
  UNSTRUCTURED form (the rows alone), a velocity field over the YZ plane of the
  global frame in m and m/s, converted in no way. Every run type writes
  `SET_FREESTREAM CUSTOM STRUCTURED` or `UNSTRUCTURED` and the file's absolute
  path in place of `SET_FREESTREAM CONSTANT`, once for a steady sweep, and
  nothing else of the script moves. The file is resolved at plan, read where it
  lives and hashed into the record's `inputs_sha256`; a case written in Python
  states it in `SimCase.freestream_profile`. The plan refuses, by name, a stem
  the folder does not hold or holds as both forms, the key on a `LEGACY` row,
  the key beside a non-zero or swept body rate (a run has one
  `SET_FREESTREAM`), the key beside a non-zero angle of attack or sideslip,
  fixed or swept (below), and a file not in its form, naming the file, the line
  and what the form asks. MEASURED on 26.124 by the licensed probe T14
  (RPT-071), the CUSTOM STRUCTURED form's first runs, rows 5012 to 5014 of
  `tests/tier3_licensed/matriz_gui.fs`: a uniform field of the row's own speed
  loads as the CONSTANT free stream to the printed digits, so the file is read
  in m and m/s as written, and a field sheared in z moves the lift. And
  `SOLVER_SET_AOA` does not turn a custom field: at 4 deg the uniform field
  loaded near its own 0 deg self (CL 0.0021) and far from the CONSTANT free
  stream at 4 deg (CL 0.3385). So a row stating the key states `ALPHA` and
  `BETA` as 0 and writes its incidence into the field's `vy` and `vz`; the
  sideslip, not measured, is refused for the same reason. The probe's row at
  4 deg (5011) is retired from the matrix. The UNSTRUCTURED form, and a custom
  field on an unsteady or rotor row, are not measured.

- **`pyfs-matrix post --additional-pproc` extracts more from a finished point
  without solving it again** (G12, FR-111). A row may state `ADDITIONAL_PPROC:
  p<id>` in its `VAR_NAMES_VALUES` cell; no builder reads it, the row's script
  is byte for byte the one without it, and the run record never carries it.
  The command takes every recorded point of such a row whose final `.fsm` is
  on disk and hashes as its record says, copies it into
  `datapoints/DP-<point>/additional/<pid>/`, and runs one script there that
  opens the copy, creates the pproc's section distributions in the frames the
  run created, updates the sections, computes their sectional loads, exports
  the loads, the surface solution `[exports]` selects, the sections, the
  sectional loads, the log and, on an unsteady point, the plots history, and
  closes: no solve, no save, no probe. Each extraction is recorded in a new
  `additional.json` beside `runs.json`, which is never written, and the
  original `.fsm` is hashed again after the launch. The post then writes the
  products of every current extraction under
  `post/<matrix>/additional/<pid>/`, each `products.json` entry marked
  `"pproc"`, `"additional": true`, `"extraction"` and `"derives_from"`. A
  point is skipped by name when its row states no key, its `.fsm` is absent or
  does not hash as recorded, it was already extracted from the same bytes, its
  build changed, its run averaged its surface in time, or its row no longer
  creates the frames its run created. The plan refuses an additional pproc
  declaring probes or a volume section (RPT-062: the field off the body does
  not come back), plots, time averaging or base regions, or an `[exports]`
  turning the sections or their loads off; the key on a `LEGACY` row; and a
  row on a build other than 26.124, the one build RPT-062 measured. It warns
  that an unsteady row's extraction is its last instant. The executor is the
  one `run` would build and `--local` means the same; a machine that would
  submit is refused naming `--local`. Library: `plan_additional_post` and
  `run_additional_post` in `pyflightstream.run.matrix`, `AdditionalRecord` and
  `ExtractionStatus` in `pyflightstream.workspace`, `build_additional_script`
  and its helpers in `pyflightstream.cases.workflows`, and
  `Script.frames_by_name`. A licensed run on 26.124 extracted two finished
  points end to end, the loads equal to the run's own, and a second post
  extracted nothing again (`reports/RPT-072`).

- **`inputs/pproc/INPUTS.md`, the glossary of every input key, generated from
  the code (G08).** Beside `VARIABLES.md`, `pyfs-workspace init`, `pyfs-matrix
  plan` and `pyfs-matrix post` write one table per table of each input
  artifact: the matrix (its columns, the `FLIGHT_CONDITION` cell and the row
  keys by run type), the setup (its settings, the solver's own names read as
  aliases, the keys recorded and emitted nowhere, the reserved keys and
  tables), the pproc (every table, and `[exports]` kind by kind), the
  reference (its keys, frames, and rotor, actuator and point blocks) and the
  geometry sidecar (`[import]`, `[[import.operations]]`, `[trailing_edges]`,
  `[wake_termination]`, `[base_regions]`). Each key gets one row: what it
  sets, its unit or values, the run types or builds that accept it where the
  code says, and the solver command it reaches. The keys are read from the
  registries the readers and builders use, and each meaning from the code
  beside its key, so a key added without one fails
  `tests/tier1_offline/test_goal031_g08_input_glossary.py`. The page is
  rewritten only when its content changes, and the documentation site renders
  the same page as "The input glossary". `pyflightstream.post.guides` gains
  `input_glossary_tables`, `input_glossary_markdown`, `write_input_glossary`
  and `write_workspace_input_glossary`; `pyflightstream.post` re-exports
  `INPUT_GLOSSARY_NAME` and `write_input_glossary`. The meanings live in
  public registries: `cases.InputKey`, `cases.EXPORT_KIND_MEANINGS`,
  `cases.SOLVER_SETTING_COMMANDS`, `cases.matrix.COLUMN_MEANINGS`,
  `cases.workflows.ROW_KEY_MEANINGS`, `workspace.matrix.PRESET_ALIASES`,
  `PRESET_RECORDED_ONLY` and `PRESET_RESERVED_KEYS`, and
  `workspace.inputs.GEOMETRY_SIDECAR_KEYS`, `RAW_MESH_CONDITION_KEYS` and
  `TRAILING_EDGE_DETECT_KEYS`. The workflows page and the user guide cite the
  page (D08).
- **An example for each new capability, run by the suite** (D11).
  `examples/obj_wing_trailing_edge_file.py` writes a wing OBJ in millimetres
  from the package's own geometry, with its sidecar and trailing-edge points
  file. It plans one row on 26.124 and prints each point's import, rename and
  trailing-edge import, with the node file in metres.
  `examples/roll_rate_row.py` sweeps `roll_rate` over -40, 0 and +40 deg/s on
  one row and prints the free-stream line each point emits: `ROTATION ... X`
  with the sign opposite to the rate (p = -omega_x of the geometry's frame),
  and `CONSTANT` at zero. It fails on any other sign or axis. Both run without
  FlightStream in tier 1 (`tests/tier1_offline/test_examples.py`) and appear
  on the documentation site.
- **An example of the additional post, `examples/additional_post.py`.** It
  records one steady point on 26.124 the way a run records it: its script, its
  outputs with the saved simulation among them, and the run record with every
  hash. It plans `pyfs-matrix post --additional-pproc` over that point with
  `plan_additional_post` and prints the extraction script: the `OPEN` of a
  copy of the `.fsm`, the additional pproc's sections cut in the frame the run
  created, `UPDATE_ALL_SURFACE_SECTIONS`, `COMPUTE_SURFACE_SECTIONAL_LOADS`,
  the exports, and no `START_SOLVER`. It then shows an additional pproc
  declaring `[[probes]]` refused, naming RPT-062. It runs with no solver in
  tier 1, and the documentation site renders it beside the other examples
  (D11).

### Fixed

- **The tier-3 twin configuration turns its rotors about their own hubs.** From
  0.15.0 the reference `r006` of the tier-3 workspace put the hubs of `PORT` and
  `STARBOARD` at y = +0.9144 and -0.9144 m while the twin mesh has its blades at
  +2.5 and -2.5 m, so row 1022 and the vocabulary rows 8001 to 8006 turned each
  blade about an axis 1.5856 m from its hub, and their licensed loads from 0.15.0 to
  0.26.0 are not the twin rotors' loads: the thrust landed on the body. The
  licensed regression of this release found it against the 0.13.0 run of 1022; the
  reference now states 2.5 m and the rows ran again, the thrust back on the blades
  (`reports/RPT-073`). The package is unchanged by it; a workspace of your own whose
  rotor blocks were copied from `r006` should check its hubs against its mesh.
- **A continuation no longer passes over its row's custom free stream** (G15).
  A row stating `RESTART` built its continuation before reading `FREESTREAM`,
  so it planned and ran beside a non-zero `ALPHA` or `BETA` the same row is
  refused without `RESTART`, and a key added to a row that stopped under the
  CONSTANT free stream reopened that state, wrote no `SET_FREESTREAM` and was
  recorded with the field's sha256 as read. A continuation still writes no free
  stream, since the saved simulation carries the stopped run's; the row's field
  is now read and refused as a run from the mesh reads and refuses it, and a
  field the stopped run's record does not hash, or hashes with other bytes, is
  refused at plan and at run, naming the point, the key and the run continued.
- **`pyfs-matrix plan` calls a recorded job's points recorded, and resume
  runs a recorded job's new angles one each.** A steady row of several points
  is one job, recorded under the row's id and not under its points', and the
  plan looked for the points' own ids: it reported every point of a recorded
  steady sweep ready while `run --resume` skipped them all. It now reports
  them already recorded, from the same question resume asks, so its ready
  points are the ones resume runs. Resume ran two or more angles added to such
  a row as a second job under the recorded job's id, so the solver ran and the
  manifest then refused the record as a duplicate; they now run one each, as a
  single added angle did, and naming the job to `--force-rerun` still runs the
  whole row as one job. A row cut back to angles its job ran runs nothing,
  where it was run again as a point and refused by that point's own outputs.
- **A point whose script created no section distribution is no longer refused
  its split.** Its record carried no `sections_layout`, which reads as a record
  written before 0.24.0, so the post named `sections/<point>_sloads#distributions`
  and `..._cp#distributions` as skipped on every steady point of a pproc
  declaring no distribution, and advised a new run that recorded nothing more
  (0.25.0 to 0.26.0). A run now records `sections_layout = []` where its
  rendered script adds or removes no surface section, on the point path and
  the steady one-job path, and a continuation records the layout of the run it
  continues. A record written before this is given the empty layout at post
  when its recorded script hashes as the record says and creates no surface
  section, so no new run is needed; a script that creates one, one that no
  longer hashes, and an older continuation keep the refusal.
  `pyflightstream.cases.workflows.creates_surface_sections` answers the
  question for a rendered script.
- **`pyfs-matrix run --local` applies the HPC profile's log decision.** A
  profile stating `[log] export_log = false` says the solver build on that
  cluster aborts at `EXPORT_LOG`; the decision reached a submitted job only,
  so a run kept local there still exported the log, the solver stopped at
  `EXPORT_LOG` after every other export, and every point was recorded
  `FAILED_INCOMPLETE_OUTPUT`.
  Under `--local` on such a machine the script now leaves `EXPORT_LOG` out, and
  the run writes the declared log from the solver's captured standard output
  then standard error; when the solver printed nothing the log is not a
  missing output, the point is judged from its loads export, and
  `residual_note` says why. A steady row of several points, one job, writes no
  point's log from the job's output and says so on the job. A file-route row
  whose solver printed nothing is recorded `FAILED_INCOMPLETE_OUTPUT` naming
  the machine. `LocalExecutor` takes `export_log` by keyword only; profiles
  that disagree about the log are refused under `--local`.
- **The additional post and the identity pre-flight follow the profile's log
  decision too.** On a cluster whose profile states `export_log = false`, the
  extraction scripts of `pyfs-matrix post --additional-pproc` exported the log
  whether planned for `--local` or for a submission, so every extraction on
  that build stopped at `EXPORT_LOG`; they now carry none, write the declared
  log from what the solver printed, and, with nothing printed, record in the
  extraction's `note` why there is no log instead of failing it. The
  build-identity pre-flight no longer exports a log there: it reads the build
  from the solver's printed output and warns, naming the profile, when it
  finds none. `ExecutionResult.captured_output()` returns that printed output,
  standard output then standard error.
- **The additional post reads an older record's boundaries by its geometry's
  hash** (G12). A run record written before 0.27.0 states no boundary names,
  and the extraction compared none, so a point whose saved simulation holds
  `W, B` over a geometry that declares `B, W` today was extracted with today's
  indices: a distribution asked of `W` cut the body and was recorded as the
  wing. The names are now read from the geometry file whose sha256 the record
  carries, as the post reads them, and compared; a point whose names nothing
  on disk recovers, while the geometry declares names today, is skipped
  `SCRIPT_DRIFT` naming the record and the file.
- **The additional post compares a frame by everything the script says of it**
  (G12). The run's frames were compared with the row's by index and name
  alone, so a reference frame turned since the run under the same name and
  origin passed, and a distribution the additional pproc cited in it was cut
  in the frame the saved simulation holds rather than the one it meant. Every
  command of a coordinate system is now compared with all its lines (origin,
  three axes, and any later turn, move, copy or deletion), and the skip names
  the first line that differs. `cases.workflows.frame_definitions` replaces
  `frame_pairs`, which no release carried.
- **An additional product stops being current when its saved simulation
  leaves the disk** (G12). The post compared the hash the point's record
  holds with the one the extraction opened, and never the file, so a `.fsm`
  deleted or replaced under an unchanged `runs.json` kept its additional
  products published. The saved simulation on disk must now hash as the state
  extracted, as the definition of record says; otherwise each extraction of it
  is skipped under `additional/<pid>/runs/<extraction id>`, naming the path.
- **An extraction whose file changed is extracted again** (G12). The
  extraction pass reused an extraction whose files were merely present, while
  the post withheld its products because a file no longer hashed as recorded,
  so a truncated export was never extracted again and the point's additional
  products stayed withheld whatever was rerun. Both now ask one question,
  `CampaignWorkspace.changed_extraction_file(record)`, which hashes every file
  an extraction wrote and names the first gone or changed; the next
  `pyfs-matrix post --additional-pproc` extracts such a point again.
- **`pyfs-matrix collect` finishes a submitted steady job on a machine that
  exports no log.** A steady row of several points is one job, and where the
  profile states `export_log = false` its scheduler writes ONE log of the job.
  The collector copied it to the first point's declared log and waited for
  every other point's, which no scheduler writes, so the job stayed WAITING
  and `collect --watch` never ended. The job's log is now filed once, as
  `<job script stem>_log.txt` in the simulation folder where the job ran, no
  point waits for a log of its own, each point is judged from its loads
  export, each point's and the job's `residual_note` names the job's log, and a
  file-route row holds every point to the import count in it.
- **A missing declared output no longer strands the others.** Collection
  refused before moving anything when one declared output was missing, so a
  point whose log never came left every other export in the solver's working
  directory under a record with `outputs = []`, and the post skipped it as
  naming no output file. Every declared output that exists is now filed in the
  point's `datapoints/DP-<point>/`, listed in `outputs` and hashed in
  `outputs_sha256`, and the error names only the missing files; the status is
  still `FAILED_INCOMPLETE_OUTPUT`. `CampaignWorkspace.collect_outputs` raises
  the new `MissingOutputsError`, a `WorkspaceError` whose `collected` lists
  what it filed, and `pyfs-matrix collect` lists them on the record too.
- **A workflow refusing a mesh file no longer promises a release.** The
  refusal of a non-`.fsm` geometry said 0.12.0 would define boundary
  conditions for a mesh cell; 0.12.0 shipped without them. A raw mesh is now
  imported when its sidecar states its unit and its trailing edge (G01, G02),
  and the refusal of one that states no unit names the key to write,
  `[import]` `units`, and promises no release (PFS-2029.09.03).
- **A steady row emits each probe line once.** A pproc declaring N probe
  lines gave N squared `NEW_PROBE_LINE` commands on a steady row, so the
  solver created and exported every point N times: three lines of eleven
  points gave 99 points where 33 were asked for (RPT-062). A single line hid
  it. A steady probe export made before this release from a probe entry with
  more than one line holds that entry's lines N times over, in N repeated
  blocks; rectangles and circles were emitted once (B04).
- **The limits list of `docs/workspace-and-workflows.md` no longer denies
  what ships.** It said nothing runs the four reductions after a campaign
  (the products stage has since 0.13.0), that a row's `REF` changes no
  emitted line (the reference and the fluid state reach the script since
  0.9.0), that no cell reaches the symmetry-loads setting (`SYMMETRY_LOADS`,
  FR-66, since 0.15.0) and that no `unsteady_rotor` script had run on a
  licensed solver (26.000, 0.20.0). The solver model is still the preset's
  and no row cell chooses it; `BLADES` still changes no emitted line (B02).
- **Two campaign posts in two threads of one process no longer share
  warnings.** Each post collects the package's warnings in a sink of its own
  thread, so a warning reaches only its own campaign's `post.log` and is
  re-emitted only by the thread that raised it. One post silencing the sweep
  table's warning no longer silences, and loses, another post's warning
  ([RPT-058](reports/RPT-058_post-log-captures-warnings-process-wide_2026-09-23.md)).
- **The unsteady step exports and the loads series state moments about the
  row's moment point.** The loads frame and the moments model were emitted
  after `START_SOLVER`, so every step export written during an unsteady march
  printed `Coordinate frame for analysis: Reference` and stated its moments
  about the reference frame's origin, while the final export stated the row's
  frame. Both lines are now emitted before `START_SOLVER` on every run type
  (each point of a sweep restates them), and are init-phase commands in the
  database, so a script placing either after the start is refused. A loads
  series (`series/<point>_loads_series.csv`) written before 0.27.0 from an
  unsteady row states its moment columns about the reference origin; its
  forces are right
  ([RPT-064](reports/RPT-064_a-loads-frame-set-before-the-solve-reaches-every-step_2026-09-24.md),
  B05).

- **Integrated sectional loads match where the geometry settles the
  selection.** With the geometry's names in hand, recorded since 0.27.0 or
  recovered by the hash an older record carries, a selection is read by the
  export builder's own expansion over them. A family stem (`families =
  "Blade"` over Blade1 and Blade2), a numbered name over a wider family
  (`Blade1` over Blade11 and Blade12) and `all` now integrate where 0.26.0
  kept the raw columns. They stay refused by name where the geometry also
  carries the stem as a boundary, a third blade, or the numbered name
  itself; a rotor's name with no rotor definition in hand is still refused
  by name, and so is a record whose geometry is gone or changed. The names
  settle a selection only for a block recorded in a common frame, or where
  the live reference's rotor definitions are in hand: in a frame spelt like
  a rotor's the builder resolved an expanding entry against the rotor
  families, never over the names alone, so without them such a block is
  matched as in 0.26.0, and two entries on a user's own `X_RMRP` stay
  refused by name; so is any block of a run that turned a rotor, since the
  builder reads a rotor's name before any stem. A geometry that gives one name to two boundaries settles
  nothing: the builder leaves that name out, so the names no longer say
  what `all` or a stem selected, and the match is read over the cuts as in
  0.26.0
  ([RPT-059](reports/RPT-059_integration-match-without-rotor-definition-refuses-by-name_2026-09-23.md),
  R03).
- **A sections split of a record written before 0.25.0 is named after the
  entry that emitted it.** The post reads the geometry's names from the mesh
  block of the file whose sha256 the record carries, the simulation's staged
  copy first, then the library's file. A block recorded in a common frame
  that the builder's reading leaves to one entry alone is that entry's: a
  block of rotor ACTIVE's blades in `MRP`, beside an entry `Blade1` the
  geometry carries as a boundary and an entry `ACTIVE`, moves from
  `sections/<point>_sloads_Blade1.csv` to `..._ACTIVE.csv`, and
  `products.json` says `distribution` 2. In a frame spelt like a rotor's
  (`ACTIVE_RMRP`) this match holds no rotor definition, so the cuts decide
  as in 0.26.0, as they do where the geometry names no single entry or gives
  one name to two boundaries. A geometry changed since the run recovers
  nothing: the file is hashed each time its names are read, before and after
  the read, and never remembered by path, size or time. The unhashed
  `.boundaries.toml` sidecar is not read (RPT-059, R04).
- **A steady row of several points records its sections layout.** Since
  0.24.0 the one-job path recorded no `sections_layout`, so the post refused
  the per-distribution split of every multi-point steady row with sections,
  and the FAMILY, PLANE and ROTOR columns read `NA`. A job run before 0.27.0
  keeps that; run it again for the split (R03).

- **The wake-edge import emitted since 0.8.0 marked nothing on 26.124.** Its
  two-value line is a syntax error there, and the node file written since
  0.8.0 (a unit line, ids, vertices) marks nothing; 26.124 reads the count,
  one placeholder coordinate line, then the edge mid-points in the
  simulation's unit, from the path on the line after the command
  (RPT-061). `TRAILING_EDGES_IMPORT` is recorded removed on 26.124, where the
  build answers "Unrecognized command" (G02).
- **Six tier-3 rows (1005, 1021, 4003, 9001 to 9003) named the body in
  `BASE_REGIONS` and so solved with no base region**; they name `Base`
  (RPT-066).
- **The plan's cost table counts a raw-mesh row's marked boundaries** from
  its sidecar's names as the renames leave them; it printed NA for every
  raw-mesh row (G02).
- **Two runs on one mesh no longer share a trailing-edge node file.** The
  node file was named beside the point's staged geometry, and staging links a
  simulation's inputs to the geometry library, so every simulation on one mesh
  wrote one file in `inputs/geometries/`. A case submitted while another case
  on the same mesh was queued replaced that job's points before it read them,
  and the count check could not tell when both imported the same number of
  edges; a points file named `<stem>.wake_nodes.txt` was written over. The
  node file is now written in the folder the point runs in,
  `sims/sim_<id>/datapoints/DP-<point>/`, or the simulation folder for a
  steady row of several points, which runs as one job; the script names it
  there by absolute path and the record hashes those bytes. Nothing is written
  into `inputs/geometries/`. New: `Script.working_dir`, the folder the run
  gives a script before building it; a script built outside a run names its
  node file by its bare name (G02).
- **A file-route row's wake-termination detection marks its node.** On 26.124
  the detection emitted right after `IMPORT_WAKE_EDGES_FROM_FILE` marks
  nothing, so a raw mesh that marks its trailing edge by file and writes
  `[wake_termination]` solved with no termination node: a twisted blade lost
  the node at its root and solved 1.8 % low in induced drag against the same
  blade detected and saved (RPT-069). The script now initializes the solver,
  detects, and initializes it again with the same settings before the solve,
  on every run type; the detection route, a file route without
  `[wake_termination]` and a continuation are unchanged. New:
  `Script.emit_after_initialization`, the one way a setup command reaches an
  initialized solver, which refuses the solver's start until it is initialized
  again (G02).
- **The compat report of the trailing-edge import records the lines its
  verdict was made on.** Its evidence line was the specification's fixed
  note, which names the import the probe wrote, so it read the same whatever
  the solver printed and a report could not be judged again from what it
  recorded. A probe specification may now state `observe`
  (`ProbeSpec.observe`), and the evidence line of a judged effect then ends
  with `The instrument read: ...`; the `IMPORT_WAKE_EDGES_FROM_FILE` probe
  records every import line of the target region as the judge parsed it,
  `import lines [{"Wing": 16}]` when verified (G02).
- **The `AUTO_DETECT_TRAILING_EDGES` probe no longer says initialisation
  detects trailing edges.** Its evidence line, quoted by every compat report,
  said `INITIALIZE_SOLVER` marks them on its own and that no instrument
  separates the two. On 26.124 initialisation alone marks none, and the
  saved-state reader of RPT-065 is that instrument. The line now states that,
  and that the probe still asserts on the log line, a silent region being
  unprobed
  ([RPT-065](reports/RPT-065_what-detection-and-initialisation-mark_2026-09-24.md)).
- **An actuator disc's and a volume section's metres reach the solver in the
  simulation's length unit.** `offset_m`, `tip_radius_m`, `hub_radius_m`,
  `corners_m` and `radii_m` went to commands that carry no unit and are read in
  the simulation's unit, unconverted, so a simulation in millimetres read a
  0.5 m radius as 0.5 mm. They are now converted into the unit the script set
  after the open (the metres of a raw mesh, or a setup line's
  `SET_SIMULATION_LENGTH_UNITS`), and on a saved simulation it set none on,
  into the unit the file was saved in, read from the head of its global block.
  Only the head every save read carries, the saves known to be in metres among
  them, is read, as metres; a file opening otherwise is refused at plan naming
  the keys, since whether a save in another unit writes another head is not
  measured. `Script.simulation_length_unit` follows the unit a script sets, and
  the length table moved to `pyflightstream._lengths`, which the trailing-edge
  node file is converted with too (G05, G06).
- **A row's disc on a saved simulation that already carries an actuator is
  refused at plan, naming it.** `CREATE_NEW_ACTUATOR` appends to the file's
  actuators while the script cited its disc as actuator 1, so the axis,
  radius, speed and loading configured the saved actuator. The saved
  simulation's actuators are read from its physics block, walked by its own
  counts, and a block out of the measured shape is refused as unreadable
  (G06).
- **A run recorded before 0.27.0 keeps its `_vsec` files as surface exports.**
  The post read every recorded output by this release's suffixes, so a 0.26.0
  record's `P_vsec.vtk` or `P_vsec.dat`, a surface VTK or Tecplot export when
  written, became a volume section: it left the native-surface entries of
  `products.json` and lost its surface metadata in PROV-JSON. A recorded
  output is now read by the kinds its record's `package_version` knew:
  `classify_outputs` takes `package_version`, and
  `cases.EXPORT_KIND_SINCE` names the release each kind of 0.27.0 entered
  (the volume-section, force-distribution and solver-plot kinds) (G05).
- **A volume section's export and delete cite the pproc's own section.** Both
  cited index 1, so a raw line cutting a section before the analysis made the
  pproc's file hold the raw section's plane, and a later point of a sweep
  deleted the raw section instead of its own. They now cite the index the
  pproc's section takes, counting every section the script cuts: a raw circle
  cut first makes the pproc's rectangle 2, exported as 2. A raw line deleting
  the pproc's section before its export is refused when the script is built.
  `Script.volume_sections` counts the sections a script has cut, and
  `Script.volume_section_index`, the pproc's own, replaces
  `volume_section_created` (G05).
- **A volume section is updated before it is exported.** Each point cut its
  section after the solve and exported it at once, and the licensed run of
  2026-09-24 (RPT-070, 26.124) wrote both points of a steady sweep as
  byte-identical files whose every cell value was 0.0: the manual computes the
  flow on a section with "Update all", after the solution has converged. Every
  point, each point of a steady one-job sweep included, now emits
  `UPDATE_ALL_VOLUME_SECTIONS` after cutting its section and before its
  export. The command is documented on every build of the range and ran
  without abort in the probes of 26.120 to 26.124; the row run again with it on
  26.124 read every one of the 96 cell values of each point non-zero and
  different between its two points (RPT-070, G05).

- **A row stating `roll_rate` or `yaw_rate` turns the free stream the way the
  rate says.** From 0.21.0 all three body rates were emitted with one sign of
  +1. The licensed probe T11 on 26.124 (build 8172026, seven converged solves,
  [RPT-060](reports/RPT-060_roll-and-yaw-rates-are-emitted-reversed_2026-09-23.md))
  measured that sign right for pitch and reversed for roll and yaw: +40 deg/s
  of roll gave the left wing more lift and a positive rolling increment, the
  damping of -p, and +40 deg/s of yaw gave it less lift. Each rate now takes the
  sign of its body axis in the geometry's frame (x aft, y right, z up): roll and
  yaw are negated and pitch is not, so `roll_rate:40` writes
  `SET_FREESTREAM ROTATION <frame> X -6.667` where 0.26.0 wrote `X 6.667`. A row
  of 0.21.0 to 0.26.0 stating `roll_rate` or `yaw_rate` was solved at the
  opposite rate; a row stating `pitch_rate` is unchanged.
  `cases.workflows.FREESTREAM_ROTATION_SIGN` is now a read-only mapping of the
  three body axes to their signs (`roll` -1, `pitch` +1, `yaw` -1) where it was
  one float. The roll and yaw scorings of OPS-2011.01.03 against the recorded
  probes pass, and their strict xfails are removed (G13).
- **`INPUTS.md` no longer lists a key the script never carries as a setting
  the run applies.** `ROTOR_SHEDDING` read as the direction a rotor's relaxed
  wake sheds in, and two rotor rows stating `AXIAL` and `AZIMUTH` build the
  same script: a workflow row checks the value and does not apply it. Its row
  now says so, and says how the direction is applied: through
  `rotor_relaxed_trailing_edges`, into the component definition the geometry
  carries. Every row key and solver setting whose value reaches no line of the
  script now says "No line of the script carries its value" and what takes it:
  `WALLTIME` (the scheduler and the wall-clock program),
  `EXPORT_UNSTEADY_AFTER_ITER` and `EXPORT_UNSTEADY_AFTER_REV` (the per-step
  program), `LAST_ITERS_AVG`, `LAST_REVS_AVG` and `BLADES` (the post stage),
  `ADDITIONAL_PPROC` (`pyfs-matrix post --additional-pproc`), `timeout_s` (the
  executor) and `walltime_margin_s` (the wall-clock program). `COLD_START`
  says that a row whose every point is its own job starts every point cold.
  The unit of `WALLTIME` reads a number and its unit, as `240m` or `4h`, where
  it read `s`, a bare number the reader refuses. `InputKey` takes
  `unscripted`, the sentence a key registers for this (G08).
- **`examples/additional_post.py` leaves a workspace its licensed
  continuation runs in.** Its refusal demonstration rewrote `wing.fs` to name
  the probing `p003` and never restored it, and its stand-in point sat in the
  same manifest, so `pyfs-matrix run wing.fs` refused the recorded point and
  `pyfs-matrix post wing.fs --additional-pproc` refused `p003` at binding. The
  stand-in point is now recorded in a rehearsal copy beside the workspace, the
  refusal is shown on a matrix of its own, `wing_probes.fs`, and the example
  ends by checking that the workspace it printed records no point, that
  `wing.fs` still plans and that its additional post binds `p002` (D11).
- **`INPUTS.md` lists the builds a key is accepted on by the rule that
  refuses it.** `Accepted by` read a command documented on a build as the key
  accepted there, so `time_averaging` listed 26.122 and 26.123, where an
  unsteady row stating `[time_averaging]` is refused: the table needs
  `SOLVER_TIME_AVERAGING` verified on the build, and no build records it so.
  The column now reads the builds off `cases.workflows.command_accepted_on`,
  the rule the builder refuses by, which asks a verified record of a command
  in `cases.workflows.VERIFIED_ONLY_COMMANDS`; `time_averaging` reads "no
  registered build" (G08).

- **A point whose solver could not use its actuator disc's profile file is no
  longer recorded as a success.** When the solver cannot use the radial thrust
  profile a row's `PROFILE` names, it logs `Failed to find`, `Failed to read`,
  `No data found in` or `Failed to load custom radial thrust profile file:
  <path>` and runs on to the end with the disc acting on a loading that is not
  the file's; the point was recorded with the assessor's status, `CONVERGED` on
  loads that are not the row's. A point whose solver log carries one of the
  four lines is now `FAILED_SCRIPT` over any status that is not already a
  failure, whichever assessor judged it, on a local point, on each point of a
  steady row run as one job, and at `pyfs-matrix collect`; its `error` quotes
  the line, names the file and says the disc did not use it (G06).
- **The profile file's refusal is read in every collected log, not only in a
  log that reads as a residual history.** The four lines were looked for in the
  log the assessor named or found by its residual table, so a log carrying no
  residual table, as a scheduler's log copied to the row's declared log can,
  was never read for them: a submitted point whose loads converged was recorded
  `CONVERGED` at `pyfs-matrix collect` with the line in its log, and so was a
  local point whose solver left no log of its own beside the export. Every
  collected output named as a log (`_log.txt`) is now read for them too, on a
  local point, on each point of a steady row run as one job and at collect,
  and the point is `FAILED_SCRIPT` (G06).
- **A log is every file the point was told to write its log to, whatever its
  name.** The four lines were read in the outputs named `_log.txt` alone, so a
  log with no residual table that a case built in Python or a LEGACY row named
  otherwise, `FlightStreamLog.txt` through its `LOG_OUTPUT` or
  `log_<point>.txt` through its script's `EXPORT_LOG`, was never read for
  them: a submitted point a caller's assessor passed was recorded `CONVERGED`
  at `pyfs-matrix collect`, and so was a local point whose script named its log
  so, where the same log named `run_log.txt` was `FAILED_SCRIPT`. The file every
  `EXPORT_LOG` of the point's script names, and the output its `LOG_OUTPUT`
  names, are now read for them too, beside the `_log.txt` names and the
  scheduler's log, on a local point, on each point of a steady row run as one
  job and at collect; no other export is read. A submitted record's
  `submission` lists them as `declared_logs`, and a job submitted before this
  is read by the script it ran (G06).
- **The actuator disc's profile file is read as it was written, and never
  stops an unattended run in a dialog.** The script named the user's file under
  `inputs/profiles/`, and an editor ends a file in a newline: 26.124 reads
  every line of the file as a point, so eleven rows read as twelve, the file
  was logged as unreadable and refused in a modal dialog that held the solver
  until a person closed it, and the point ran on with a loading that was not
  the file's (measured by a licensed probe, RPT-070). The run now writes its
  own copy, `<stem>.actuator_profile.txt`, in the folder the point runs in (a
  steady row of several points: its simulation folder): the user's rows, blank
  lines and surrounding spaces removed, joined by a newline and with NO final
  newline, the one form measured to be read, radii and forces. The script
  names the copy, the record hashes it in `inputs_sha256` (the user's file,
  which the solver does not read, is not hashed), and the user's file is left
  as saved, on every run type that emits a disc. The plan refuses, naming the
  file and the line, a profile the solver would misread: a header or a count
  first (26.124 reads either as one more point, and every value then reads as
  zero), a row that is not two numbers separated by one comma, a number that
  is not finite, or fewer than two rows; a case built in Python is held to the
  same form when its script is built. New: `helpers.render_actuator_profile`,
  the form; `helpers.actuator_disc(profile_text=...)`, which parks the copy on
  the script; `cases.workflows.read_actuator_profile`; and
  `Script.pending_input_files` values may be bytes, written as they are (G06).
- **`reconstruct()` checks each recorded input where the run read it.** It
  looked for every name of a record's `inputs_sha256` in the simulation's
  `inputs/`, where only the staged geometry is: the trailing-edge node file,
  the actuator profile's copy and the unsteady action and clock programs, all
  written in the folder the point ran in, read `missing`, so no record
  carrying one was `faithful`, and a node file whose name the input library
  also held read `differs` against a file the run never read. Each input is
  now checked at the path the script names for it, among the staged inputs,
  or in the folder the run ran in (the record's `cwd`), reads `missing` only
  when it is not there, and still reads `differs` once changed; the keys of
  `Reconstruction.verified` are unchanged. An action script rewritten during
  the run reads `differs`, since the record hashes the empty file the run
  wrote.
- **Two different files the solver reads no longer share one key of
  `inputs_sha256`.** The record keys each input by its file name, and the
  digests of the files a run writes for the solver, the trailing-edge node
  file `<geometry stem>.wake_nodes.txt` and the actuator profile's copy
  `<profile stem>.actuator_profile.txt`, were merged over the inputs the case
  declared. A custom free stream named like either,
  `FREESTREAM: wing.wake_nodes` beside the file-route wing `wing.stl`, ran with
  the generated file's digest in place of the field's, so the record no longer
  said which field the solver read, and `reconstruct()` verified the node file
  under that key and never the field. A file the run writes under a name
  another input of the case already holds with different bytes is now refused
  before the solver starts, on a point and on a steady row run as one job: the
  point is `FAILED_SCRIPT`, its error names the key and both files, and its
  record keeps the declared file's digest. The same bytes under one name are
  one file and run (G15, G02, G06).
- **Two disc profiles whose paths differ only in case are refused, not merged
  into one file.** A recipe calling `helpers.actuator_disc(profile_text=...)`
  twice, on `prop.txt` and `PROP.txt` with different loadings, passed both
  guards, which compared names as written: on a case-insensitive file system,
  as on Windows, the second write replaced the first before the solver started,
  so both discs read the second loading while `inputs_sha256['prop.txt']`
  recorded the first. Names equal but for case are now one file to both
  guards: `actuator_disc` refuses a second profile whose path differs from a
  parked one only in case, before a line of its disc is written, and the run
  refuses, before the solver starts, any file it writes for the solver whose
  name differs only in case from another input of the case with different
  bytes, naming both files. The same bytes under both spellings still run, and
  the record keeps each name as the script spelled it (G06).
  `helpers.mark_wake_edges` holds a trailing-edge node file to the same rule,
  and a declared log whose collected name differs from the script's only in
  case is read for the profile's refusal (G02, G06). So does
  `helpers.unsteady_action` for an action script, and the run checks every file
  it writes for the solver, action scripts and data files together, before it
  writes the first: two paths equal but for case with different contents are
  refused, since one action or import would read the other's text. The
  solver's own `FlightStreamLog.txt` is read for the profile's refusal wherever
  it is collected, a job submitted before the declared logs were recorded
  included. A path through a parent folder (`sub/../x`) is the file it names
  under the same rule, and a file cannot be parked on a path the run writes
  itself (the unsteady counter and wall-clock programs and their state files),
  which would replace or remove it after its digest was recorded. On a machine
  that cannot export the log, what a local point's solver printed is read for
  the imported trailing-edge count and the profile's refusal when the row
  declares no log output, as a local steady job's already was (G02, G06).
  Every collected text output (`.txt`, `.log`) is now read for the profile's
  refusal, whatever its name, a log a SCRIPT action exports at each step
  included, since naming the logs one route at a time left the next route
  unread; and the point's main script, its probe points file and a submitting
  executor's descriptor are files the run writes itself, so nothing parked may
  replace them (G06). A file parked on an input the record already hashed (the
  staged geometry, which can be the library's own file through the inputs
  folder) is refused before it is written, so the input keeps its bytes; and
  collection reads the solver's own `FlightStreamLog.txt` where the job ran,
  declared or not, in the datapoint folder the submission names even when the
  workspace was moved (G06). A data file the run writes and hashes (the
  trailing-edge node file, a disc's profile copy) is the point's own and is
  written in the folder the point runs in: one a recipe parks anywhere else,
  beside the geometry or on a path several points share, is refused before the
  solver starts, since another point's run would rewrite it before a queued
  point read it. Pass `mark_wake_edges` and `actuator_disc` a path in
  `script.working_dir`, as the workflow builders do (G02, G06). The files the
  run writes itself are checked against one another, so a machine profile's
  descriptor name on the main script's or a program's path is refused naming
  the descriptor; and every collected output that is not a binary kind is
  scanned for the profile's refusal, line by line, whatever its suffix (G06).
  Windows reads some names as another file's: a trailing dot or space
  (`prop.txt.`), an 8.3 short name (`PROP~1.TXT`), a stream (`prop.txt:x`).
  Paths are compared by the real path with those folded, and a file the run
  would write under such a name is refused naming the reason, the scheduler's
  descriptor included; a data file's place in the point's folder is judged
  through its resolved path, a link or a junction followed (G06). An action
  script a recipe parks is written in the folder the point runs in, as a data
  file is; one parked anywhere else (the simulation folder, where a queued
  steady job's hashed copies live, another point's folder, another simulation
  or workspace) is refused before the solver starts, and a steady job, which
  runs in the simulation folder, stays out of its `scripts/` and `datapoints/`
  folders, where other points' records name the files their solvers read. A machine
  profile names its descriptor with a plain file name, with no folder, no
  parent folder and no name Windows reads as another file's, since the
  descriptor is written in the folder each point runs in; `HpcProfile`
  refuses such a name however it is built, a profile made in Python included. The line-by-line
  scan for the profile's refusal reads a log written as UTF-16 as the
  whole-file reader does (G06). A simulation folder holds one campaign's
  queued work: a campaign whose row names a simulation in which another
  campaign's work is still in a scheduler's queue is refused before anything
  is prepared, whatever the executor, since the folder carries no campaign
  name and staging re-links or re-copies its inputs; within one campaign, a
  new point is refused when the geometry changed since a point of the same
  simulation was submitted and that job is still queued, since staging would
  replace the copy it opens, whatever the case of the new file name, and a
  row whose staging would change anything the simulation's inputs folder
  presents to a queued job (re-pointing its link to another geometry folder,
  copying other bytes) is refused the same way (`staging_would_change`); and
  `--force-rerun` refuses a point still in a
  queue, which is collected first (G06). What these
  guards cover, and the file-system arrangements they do not defend against,
  is stated in `docs/workspace-and-workflows.md`, "What the record's digests
  guard, and where that stops".

### Changed

- **A local point runs in its own datapoint folder.** A point run on this
  machine, with `--local` or on Windows, now runs the solver with
  `sims/sim_<id>/datapoints/DP-<point>/` as its working directory, as a
  submitted point has since 0.18.1, so every export, the per-step ones and the
  solver's own `FlightStreamLog.txt` included, is written where it is filed
  rather than moved there by collection, and a point whose run fails leaves
  nothing in the folder its row shares. The script is unchanged, and its hash
  with it: its exports are named relative to the working directory and its
  inputs by absolute path. The action program, the wall clock and the
  trailing-edge node file a point writes before its solve are written there
  too, and the record's `cwd` names the folder. A steady row of several
  points is one job over one script and still runs in the simulation folder,
  as its submitted form does.
- **An induced drag the solver did not compute is `NA` in every sum the
  package makes.** A boundary on the vorticity induced-drag list
  (`SET_VORTICITY_DRAG_BOUNDARIES`) without a defined trailing edge is not
  computed, and the export prints its `CDi` as zero (SRC-003 p.202). The
  steady polar summed that zero as a measurement, so a group holding such a
  surface wrote a `CDI`, `CDB`, `CDS` and `CDW` short by an induced drag
  nobody computed. A surface the point's run record puts on the list, and
  whose printed `CDi` is exactly zero, now makes the group's `CDI` `NA` in the
  polar table and the superfile, and so does every axis column the export's x
  force reaches at that point's angles: `CDB`, `CDS` and `CDW`; `CLS` and
  `CLW` at a non-zero angle of attack; `CYW` under sideslip. The moments,
  `CYB`, `CLB`, `CYS` and `CD0` keep their numbers; the fixed-width custom
  polar writes the missing value as `nan`. The solver's Total row and the
  parsed per-surface `CDi` keep what the export printed, and `post.log` names
  the declined surfaces of each point. A surface off the list keeps its
  printed zero. A trailing-edged surface whose induced drag rounds to zero at
  the printed precision reads `NA` too; `SET_SIGNIFICANT_DIGITS` narrows that
  band. `write_recorded_polar`, which holds no run record, is unchanged
  (PFS-2006.03, FR-22a).
- **The induced-drag default lives in the command database.**
  `SET_VORTICITY_DRAG_BOUNDARIES` records `default: []` with
  `default_ref: SRC-003 p.202`, and the solver-setup snapshot reads both from
  the entry instead of restating them in code; a command entry's `default`
  accepts a tuple of boundary indices, the empty one meaning a default that
  emits no line. The snapshot of a script that selects nothing is unchanged
  (PFS-2006.01).
- **A `post.log` WARNING line names the point and product its warning
  names**: `WARNING point=camp/sim_7001/AL-020 product=available-exports:
  ...` where 0.26.0 wrote `WARNING point=campaign product=stage:
  point=camp/sim_7001/AL-020 product=available-exports: ...`. A warning that
  names none still reads `point=campaign product=stage`, and an interrupted
  post's line ends `Remedy: correct the stated input and post again.` (R02).
- **A warning raised during a post by code outside the package is no longer
  written to `post.log`.** It reaches the caller's warning filters as before;
  the package's own warnings are logged as they were (RPT-058).

- **`[exports] simulation = false` is refused**, as `loads = false` has
  been: every point of a row naming a run type leaves its final saved
  simulation (G11). `pyfs-matrix plan` refuses an artifact stating it with
  `matrix not planned: ...` and exit 2, naming the row and the file; remove
  the key.

- **`helpers.mark_wake_edges` takes `units`, `node_file` and `midpoints`.**
  On 26.124 it emits `IMPORT_WAKE_EDGES_FROM_FILE <TYPE> <TOLERANCE> <UNITS>`
  with the node file on the next line, the form that build reads, parks the
  file on the script and records the count. 26.122 and 26.123 refuse the file
  route as unmeasured, and builds before 26.122 refuse it as before (G02).
- **`workspace.write_node_file` writes the node list 26.124 reads**: the
  count, one placeholder coordinate line, then the edge mid-points converted
  to the simulation's length unit (new `simulation_unit`), in plain decimals.
  `write_trailing_edge_node_file` writes the mid-points of every trailing-edge
  mesh edge under a unit line, as the points file a geometry names, and
  `TrailingEdge.write_node_file` refuses: a list of vertices marks nothing
  (G02).
- **`BASE_REGIONS` (and a pproc's `base_regions`) names the boundary that
  becomes the base** (RPT-066). `DETECT_BASE_REGIONS_BY_SURFACE` given a
  body's own boundary marks nothing and says nothing; the page and FR-55
  state it, and the emission is unchanged.

- **Every steady workflow script gains its plot saves**, eight lines per point
  between `EXPORT_PROBE_POINTS` and `EXPORT_LOG`. Every steady point declares
  two more outputs (three with sections), and a missing one fails the point
  `FAILED_INCOMPLETE_OUTPUT`. LEGACY rows and outputs declared in Python are
  unchanged (G04).
- **Command database:** `SET_PLOT_TYPE` and `SAVE_PLOT_TO_FILE` are
  export-phase commands, `verified` on 26.124 from the transcription
  `reports/compat/CMP-26124_2026-09-24_plots.yaml` of RPT-067's run; verified
  26.124 rows go from 87 to 89 (G04). `SET_VORTICITY_LIFT_MODEL` and
  `SET_UNSTEADY_VISCOUS_COUPLING_ITERATION` are `removed` on 26.124, citing
  RPT-068; emittable 26.124 commands go from 371 to 370 (G14).
- An output name ending `_vsec.vtk` or `_vsec.dat` is now the volume-section
  export, not a surface VTK or Tecplot export, in a case being built and in a
  run recorded by 0.27.0 or later; a run recorded before keeps the surface
  meaning. A case declaring one without a cut section is refused (G05).
- `ACTUATOR`, `ACTUATOR_RPM`, `ACTUATOR_THRUST` and `PROFILE` are row keys of
  every run type, so a setup flag taking one of those words is refused (FR-74)
  (G06).
- **The first column of every table is the polar, and no line precedes the
  header (G16).** Every table the post writes under `post/<matrix>/`, the
  additional post's included, and `campaign_sweep.csv` open with `POL`, named as
  the run matrix names its polar column, holding the POL of the point each row
  comes from; the sweep, whose rows mix polars, carries each row's own. The
  rotor table's alias, alone on its first line before the header since 0.23.0,
  is now the `ROTOR` column right after `POL`, so its first line is its header
  and a CSV reader takes the file as written. **`POLAR` is gone:** the steady
  polar and its super file, which opened with `POLAR` in 0.26.0, open with
  `POL` in its place and carry no `POLAR` column, so a reader by name reads
  `POL` where it read `POLAR`, and a reader by position finds every column of
  those two tables where it was. Every other column keeps its name and its
  order after them: a reader of any other table by position finds each column
  one place to the right, two in a rotor table. The package's own readers
  follow: the reductions read every plots column but `POL` as a plotted
  quantity, the super file's union reads a rotor table's header from its first
  line, passes over the alias line of one written before and reads the `POLAR`
  of a polar table written before as `POL`, and `REDUCTION_COLUMNS` begins with
  `POL`, so a `[names]` entry cannot take the name. The public table writers
  take `pol=` (`NA` where the caller states none), `results.sweep_table` and `results.run_table` lead with
  `POL`, `ROTOR_TABLE_LEAD_LINES` is 0, and `rotor_table_alias_line` is removed
  with the line it wrote. The solver's own files are not touched. See
  `docs/migrating-to-0.27.0.md`.
- **No cell of a table holds a comma or a double quote, and nothing is quoted
  (G16).** A reader that splits each line on `,`, as `numpy.genfromtxt` does,
  counted the commas inside the quoted list cells a super file and an unsteady
  polar echo from the matrix row (`SWEEP_VALUES`, `FLIGHT_CONDITION`) as
  columns, so a row read wider than its header. Every text cell of
  every table the post writes, header names included, and of the campaign
  sweep now writes a comma as `;`, a double quote as a single one and a line
  break as a space, through one rule, `pyflightstream._tokens.plain_cell`,
  called by the products' funnel and by the tabular layer's `write_table`.

### Changed (the type-checker debt, re-measured on the release tree)

- mypy recount 2026-09-24: 812 errors in 18 of 100 modules, against 0.26.0's 710 in 18 of 97. The three
  modules that arrived, `_decimal.py`, `run/_wake_edge_verdict.py` and
  `_lengths.py`, are clean; the hundred and two errors more sit inside the
  exempted set, most on the run module's record builders, which carry 628
  of the 812 (`reports/RPT-029`).

### Documentation

- **`docs/mesh-inputs.md` reads in the order a user who starts from an OBJ or
  an STL needs it** (D05). It starts with what the sidecar says, in order: the
  surface names, `[import]` units, `[[import.operations]]`, `[trailing_edges]`
  by a points file (the default) or by detection, then `[wake_termination]`
  and `[base_regions]`. Next come the points file (its format, how the package
  checks it, the node file the run writes and the count check) and one table
  of which build runs what and what is measured, by report (RPT-061, RPT-065,
  RPT-066, RPT-048). One complete example follows: a wing OBJ in millimetres,
  its sidecar, its points file, the artifacts its row cites, a row on 26.124,
  the plan command, and the head of the script and the node file it builds.
  `tests/tier1_offline/test_mesh_inputs_page.py` runs that example from the
  page's own blocks, plans it and renders both points without a solver. It
  fails when the script or the node file differs from the page, or when a key
  a sidecar block on the page writes is not one the sidecar's readers read, or
  the other way round. Two statements were stale and are corrected:
  `SET_OUTLET_TRAILING_EDGES` has been in the command database since 0.8.0,
  and the detect-by-surface forms were written only in TOML comments.
- **From the GUI to pyfs** (`docs/gui-to-pyfs.md`): each step of a
  FlightStream GUI session, in six stages (geometry and mesh, boundary
  conditions, frames, motion and actuators, flight conditions and solver, the
  run, basic post), with the key that takes it in a workspace, the solver
  commands that key emits and the builds the command database records those
  commands verified on; or `not yet`, with the commands the raw route
  (`[[raw]]`, a row's `RAW`, a `[[flags]]` word) would state. It is on the
  site menu, the home page and the README.
  `tests/tier1_offline/test_gui_to_pyfs_page.py` reads the page beside the
  registries and the database: a row key, setup key, pproc table or sidecar
  table added without a line fails, and so does a command the database lacks,
  a build it does not record verified, a not-yet line with no route, or a link
  to no heading (D06).
- **Every guarantee of the definition and workflow pages names the test that
  holds it** (D07). This covers the final saved simulation of every point
  (G11), the additional post and what a reopened `.fsm` gives back (G12), and
  the body rates (G13), each sentence citing its tests by name. The workflows
  page and the definition of record state the T09 result (RPT-062): a reopened
  saved simulation gives back the total loads, the surface solution, the
  sections and, once computed, their sectional loads identical, and does not
  give back the probe points off the body. The flight-conditions page tables
  the measured sense of all three rates: the line emitted for +40 deg/s and
  the solver's answer to it (T11, RPT-060; RPT-052 for pitch). Twelve
  guarantees that had no test got one.
  `tests/tier1_offline/test_goal031_d07_pages.py` fails when a sentence loses
  its citation or a cited test disappears.
- **The documentation site renders its pages as written.** The site's Markdown
  did not read a titled code fence (```` ```text title="matrix_registry.fs"
  ````), so the fence closing it opened a block. 286 lines of the workflows
  page rendered as one code block: the heading "A rotor row states the
  decisions, and the arithmetic is derived" had no anchor, and the
  reserved-names table was plain text. The complete example of the mesh page
  was cut the same way, and four code blocks inside list items were lost on
  four pages. The site now reads fences with `pymdownx.superfences` and
  `pymdownx.highlight`, which ship with the material theme, so a titled block
  shows its file name; no word of any page changed. Two faults the code block
  had hidden are fixed: a blank line splitting the reserved-names table, and a
  link to a heading that no longer exists. A tier-1 test renders every page
  with the site's extensions and fails on a fence, a heading, a table row or a
  table cell the site would lose. The site's table reader cuts a row wider
  than its header to the header's width and renders the rest of the row as a
  row, so the test compares every cell of every table a page writes with the
  table the site renders, and names each cell the rendering drops (D07).

- **The tier-3 page states which induced-drag form each case uses.** Every
  row whose golden script carries `SET_VORTICITY_DRAG_BOUNDARIES` names its
  selection, the single-boundary wing geometries on which `-1` and `1` are
  the same set, and the two local-only SMI cases that put a body on the
  vorticity list; a test keeps the page in step with the goldens. The re-run
  of those references is 1.0 work (PFS-2006.02).

## [0.26.0] - 2026-09-23

THE POST NEVER BLOCKS BY DEFAULT AND ALWAYS WRITES ITS LOG, the blade loads come
integrated per strip, the freeze check is rearchitected so the reducer states the
samples it reads, and no compatibility promise waits past this release.

### Added

- Every campaign post writes `post.log` beside `products.json`, even when clean.
  It records every named skip and stage warning, carries the invocation header,
  and is archived with the products on rebuild. The manifest names the log.
  Warning capture is process-wide, so concurrent posts in threads can mix
  campaign warnings; post one campaign per process until
  [RPT-058](reports/RPT-058_post-log-captures-warnings-process-wide_2026-09-23.md)
  is resolved in the planned 0.27.0 work.
- Optional integrated sectional loads: `integrate = true` on a pproc
  `[[sections.distributions]]` entry appends `Strip_length`, `Fx_int`, `Fz_int`
  and `My_int` to the same sectional CSV. Each instant uses exported station
  midpoints, half intervals at the ends, and moments about the local quarter
  chord. Invalid distributions warn and keep the original columns; the default
  is off and preserves the previous file bytes. Without a live rotor
  definition the match is conservative and refuses by name wherever the
  recorded evidence cannot say what the builder would emit
  ([RPT-059](reports/RPT-059_integration-match-without-rotor-definition-refuses-by-name_2026-09-23.md)).

### Removed

- `write_sections_table(iteration=)`: use `step=`. The old keyword raises
  `ProductArgumentError` naming `step=`.
- `run.assess_unsteady_from_plots`: use `LoadsAssessor` for campaign assessment
  of native loads and solver residuals. Analyze history settling separately.
  Importing the removed name raises ImportError with those repair instructions.
- Row key `WINDOW_STEPS`: write `LAST_ITERS_AVG` with the same count.
- Row key `WINDOW_REVOLUTIONS`: write `LAST_REVS_AVG` with the same count.
- Row key `WINDOW_DEGREES`: divide the value by 360 and write `LAST_REVS_AVG`.
- Member lists in pproc `[groups]`: write one alias as a string. Put several
  members in the reference's `[aliases]` table; use `"all"` for an empty list
  only after the [collision check](docs/migrating-to-0.26.0.md#6-a-pproc-group-names-one-alias).
  All three retired row keys and all member lists are refused before running.

### Changed

- Nothing in the post blocks by default: frozen solves and unread blocks warn
  while computable products are written. `--check-frozen` refuses affected
  averages instead of warning alone. Failed status alone no longer excludes
  usable exports in default mode.
- Malformed loads skip their point by name, preserving healthy points' products.
  Empty unsteady logs warn by default and refuse averages only when asked.
  Sparse per-blade tables use their combined window, and the unsteady polar
  and rotor guards judge the plotted steps their averages actually read.
  Integrated sectional columns follow the matrix's current PPROC selection
  while distribution identity remains recorded.
- The reducer states its exact plotted sample set using its resolved families.
  The freeze guard no longer reconstructs azimuthal samples. Every nonzero
  interpolation weight counts, including weights near 5e-11 (RPT-057).
- See [Migrating to 0.26.0](docs/migrating-to-0.26.0.md) for each replacement.
- Recorded manifest key `broken_commands` is read silently as `waived_commands`
  for as long as such manifests exist. It is plain compatibility, with no
  removal countdown; recorded manifests are never rewritten. Re-measured on
  2026-09-23: 46 matching rows in the canonical repository's
  `tests/tier3_licensed/runs.json`; `post/matriz/plan.json`,
  `post/matriz_time/plan.json` and `post/matriz_builds/plan.json` are absent.
  All four are absent from this isolated worktree. The historical census of
  74 rows (46, 18, 8, 2) across four manifests does not reproduce here;
  absent files are not a measurement of zero recorded rows.

### Fixed

- Preserve healthy polars when a metadata-poor failed record comes first;
  name opt-in status refusals and retire their previous products on rebuild;
  resolve integration selections through live reference aliases while keeping
  recorded distribution ownership. The second independent reading adds three
  corrections: only contributing records name a polar, and a moved or stale
  previous table is retired by name; integration requires the builder's exact
  expanded family set rather than a subset; rotor names and live aliases of
  rotor names resolve through the export builder's own expansion; and a legacy
  layout with no rotor definition still owns each recorded block of an entry on
  an expanding frame (`LOCAL_AXIS`, `RMRP`, `SMRP`) by the grouping the recorded
  frame names carry: the block is exactly the selected families recorded in its
  frame, the rest of the selection is recorded in sibling frames, a per-blade
  block is one blade; two blocks in one rotor frame are never one entry's, and
  a common frame still requires the whole selection. The third independent
  reading adds per-point skips for polar groups selecting no surface, isolates
  an unassignable analysis frame to its own point, includes families absent
  from sectional layouts in integration matching, and names unsteady polars
  from the points whose histories actually contribute rows. The released
  section no longer states a development version.
- Legacy sectional and Cp ownership uses the recorded pproc, while the effective
  pproc selects integration, including `families = "each"`. An unresolved pproc
  preserves histories supported by recorded layouts and names integration skips.
- Per-blade guards judge all samples in the final combined span, including gaps
  between passages, while preserving end trimming. Malformed-run rebuilds retire
  stale products through manifest run associations and keep regenerated files.
- Steady-log recognition follows printed solver mode, with the loads export as
  the fallback when the log's mode is unknown. Empty-group migration diagnostics
  explain collisions with `all` and the unique-reference-alias alternative.
- Section integration follows a uniquely matching current pproc entry by
  families, plane, frame and count, preserving recorded block ownership after
  entries are reordered. Ambiguous matches warn and retain raw columns.
- A terminal residual block cut before the `Iteration` anchor is unread only
  when an earlier unsteady marker block printed at least one residual page.
  A log whose markers never carry pages is not classified as cut.
  Page-less repeated markers for the same step retain their residual evidence
  and do not create false unread steps (RPT-055).

### Changed (the type-checker debt, re-measured on the release tree)

- The type-checker re-count of 2026-09-23 read 710 errors in 18 of 97 modules, against 0.25.1's 713 in 18 of 97. No
  module arrived and none left; the three errors that went were in the post
  stage's products module, rewritten around the post log and the
  reducer-stated samples (`reports/RPT-029`).

## [0.25.1] - 2026-09-22

A PATCH RELEASE FOR ONE DEFECT THAT STOPS THE POST STAGE DEAD, measured on a
cluster and on Windows within an hour of each other, on campaigns recorded with
0.24.0 and posted with 0.25.0.

### Added

- **`J_CLOCK` and `RPM_CLOCK`, beside `J` in every product's condition.** `J` is
  the advance ratio the ROW REQUESTED, so a row that states `RPM` and sweeps
  alpha reads `NA` in every one of its rows while carrying the velocity and the
  speed that determine the ratio -- measured on a real polar whose `VINF` is
  61.4 and whose `RPM` is 7585, two thousand columns apart. The two new columns
  state what the CLOCK rotor RAN at: its speed with its hand, and
  `V / (n D)` from this point's own free stream, the speed the record kept and
  the rotor's diameter. THE CLOCK ROTOR is the one `CLOCK_MOTION` names, or the
  only rotor the row turns; a row turning several and naming none has no clock
  and both columns are `NA`, because one rotor's ratio is not another's. A flat
  single-rotor reference, with no named rotor block and a top-level
  `rotor_diameter_m`, supplies the span of its one rotor; beside named blocks the
  flat diameter answers for nobody. The rotor table keeps `J_<alias>` per rotor,
  unchanged.
  This is why 0.25.1 adds columns rather than only fixing defects: the owner
  asked for it in this release (2026-09-22).

### Changed (breaking: the native-log freeze check is OPT-IN)

- **`post` and `collect` no longer refuse anything from a point's native log
  unless asked.** `--check-frozen` turns the refusal on; without it the stage reads a log for a
  freeze only to ADMIT a point recorded as `FAILED_DIVERGED` whose solver froze,
  so that point's histories, instants and pre-freeze averages are written as
  they were in 0.25.0, and nothing is refused from what it reads. The provenance
  digest still hashes every recorded output, the log included, in every mode, and
  a file it cannot open is recorded from the record. THE CONSEQUENCE, stated
  where it can be read: the averages of a FROZEN
  solve are published like any other, and a frozen solve prints plausible
  numbers, so nothing in the products says they are wrong. 0.25.0 added that
  refusal; 0.25.1 makes it a choice.
  WHY: the reading decides which steps an INTERPOLATED average reads, and eight
  rounds of review on that one corner found the guard wrong in one direction or
  the other each time -- publishing an average over a step nobody read, then
  refusing averages that read no such step. The owner's decision of 2026-09-22
  is to ship the release with the reading off and re-discuss the architecture in
  0.26.0, where the reducer states the moments it samples instead of a second
  implementation guessing them (`reports/RPT-057`).
  WHAT IS NOT A CHOICE: the crash. A log that cannot be read never ends the
  post, with the reading on or off.

### Fixed

- **A residual block the solver stopped under no longer ends the whole post.**
  The freeze check of 0.25.0 reads the native log, and a run stopped by its
  walltime guard, killed, or aborted leaves a residual header with no rows and
  no closing rule under it. `frozen_time_steps` refuses such a table, by
  design, and the post stage let that refusal travel: `pyfs-matrix collect`
  died with `IncompleteOutputError` and its traceback, `pyfs-matrix post`
  printed the one-line message and wrote NOTHING. One unreadable block cost
  every product of every simulation, which is the opposite of this package's
  rule that a point that cannot be judged loses its own products and no more.
- **The blocks the solver did finish are still judged.** A real log measured
  here carries 144 step blocks of which exactly ONE cannot be read; the steps
  around it are as measurable as they ever were. The post stage now reads the
  log tolerantly, names the time steps it could not read, and refuses ONLY the
  averages whose window covers one of them, under the file's own name with the
  reason and what would settle it. Histories, instants and every other product
  of the point are untouched.
- **A freeze beside an unreadable block is not lost.** A freeze needs two
  consecutive frozen steps, so a step that froze with its neighbour unreadable
  would have vanished into silence and its average published. Both steps are
  reported as unread instead, and the windows covering either lose their
  averages. THE LIMIT, measured by the independent review and older than this
  patch: a block whose `Iteration` anchor is itself cut mid-word carries no
  residual table to refuse, so it is read as a step with no evidence rather
  than as an unread one (`reports/RPT-055`).
- **A phase-locked average is judged over the steps it READS**, which its
  declared window does not name: the azimuthal one is interpolated, so it also
  reads the plotted steps BRACKETING each moment it samples, one per azimuth of
  the final revolution per blade offset; a sample that is a whole step AND is
  in the plotted history brackets to itself and widens nothing, while a
  whole-step sample the history does not hold is read from its neighbours like
  any other. The passage series a pproc without a `[phase_locked]` table produces reads only
  the steps of its passages and is judged as it states. An unread step there
  moved a published average while the manifest stated a clean window. THE BOUND
  IS THE SAMPLES, not a revolution and not the window's opening: three readings
  of GitHub main measured each wrong bound in turn -- a revolution is too narrow
  on a sparse history, where the interpolation reaches step 1 of a window opening
  at 95, and too wide on a dense one; and the opening is still too wide, because
  with whole-step blade offsets every sample lands on a plotted step and nothing
  outside the window is read. The guard is proved at the product, on an azimuthal
  rotor campaign, against a mutant that restores the opening bracket.
- **A point whose log proves a freeze is still posted** for everything the
  freeze does not touch, even when another block of that log cannot be read.
  Excluding it removed its histories, instants and earlier averages before
  their own checks could run.
- **A refused rotor table names the plot group that took its name.** Where a
  pproc declares a group that emits `ROTOR_<ALIAS>` in the rotor's own frame
  (`SMRP` or `RMRP`), the run does not add its automatic `ROTOR_<ALIAS>` in the
  global MRP frame, because two plots cannot share a name -- and the rotor table
  then had no source and was refused with "looked for none", which names nothing
  a reader can act on. Eight rotor tables across two campaigns were refused that
  way. The refusal now names the declaring group, its frame, and what to rename
  it to. NOTHING IS RECOVERED BY POST-PROCESSING: a run whose global-frame rotor
  history was never written does not have it, and the message says so.
- **A window is refused exactly when it touches an unread step**, and a
  confirmed freeze no longer discards them: a log can hold both kinds of
  evidence and the verdict carries both, so a window before the freeze and over
  an unread block is refused too. The neighbour rule runs in BOTH directions and
  only across consecutive step numbers, so a frozen step after an unread block
  is unread as well, and a frozen step separated from one by a gap is not.
- **The per-blade table never bridges a refused passage.** It states ONE window
  collapsed from its passages, so dropping a refused passage BETWEEN two kept
  ones and collapsing the rest averaged the steps the refusal had just removed.
  It now refuses whole and says why; passages lost from an END still keep their
  product, which is what the definitions page asks.
- `results.frozen_time_steps` gains an opt-in `unjudged` list. Given one, it
  skips a block it cannot read and records the step; without one it raises
  exactly as before, which is what the collect path needs to record
  `FAILED_INCOMPLETE_OUTPUT` (FR-17). `results.UnjudgeableSolve` is the verdict
  such a log earns, and it is a `FrozenSolve`, so a reader that knows only the
  older type refuses rather than accepts.

## [0.25.0] - 2026-09-20

### Changed (the type-checker debt, re-measured on the release tree)

- The type-checker re-count of 2026-09-20 read 713 errors in 18 of 97 modules, against 0.24.0's 661
  in 18 of 93. The four modules this release adds --
  `post/section_distributions.py`, `post/provenance.py`, `post/custom_polar.py`
  and `script/_surface_averaging.py` -- and the sites they carry are the rise;
  the number of modules holding an exemption is unchanged at eighteen
  (`reports/RPT-029`).

### Owed



### Changed (breaking: the probe source follows the run type)

- **On an unsteady row every `[[probes]]` entry is a fluid plot, and its table is the
  plots history.** A cited `points_file` is read at plan and each of its points,
  for each listed parameter, becomes a fluid plot on the same vertex counter as the
  drawn lines; the row no longer imports the file (`PROBE_POINTS_IMPORT`) nor exports
  probe points (`EXPORT_PROBE_POINTS`, the LAST STEP only). `post` builds an unsteady
  point's probes table from the plots history, never from a probe-points export, so
  a pproc mixing drawn lines and a cited profile yields ONE history table holding
  both. A steady row is unchanged: both forms use the probe-points path.
- **Re-posting an unsteady run recorded before 0.25.0**: its cited-profile probes
  were exported as a last-step instant and have no history; posting again cannot
  create one. They are left out with that reason in `products.json`, and the
  drawn-line probes of the same run keep their history. A new run is needed for the
  cited probes' history.
- An unsteady row's default outputs lose `{name}_probes.txt` (seven, not eight).

### Known limitations

- **The time-averaged surface cannot be produced on FlightStream 26.124.** The
  licensed verification of this release measured `SOLVER_TIME_AVERAGING` HANGING the
  solver. The script the package writes, run WITHOUT that one line, finished in 133.0
  seconds and wrote all seven outputs including its final log export; WITH the line in
  the position the package emits it, nothing was written and the solver had to be
  killed at 240.5 seconds. Both runs left a receipt carrying the executable's sha256
  and the script's, under `reports/pfs0250/time_averaging/`. (An earlier run with the
  line moved after `INITIALIZE_SOLVER` hung the same way; it predates the receipts and
  is recorded as an observation rather than as certified evidence.) The command is emitted exactly as
  its manual documents it (SRC-750 p.353). The package therefore REFUSES a pproc
  carrying `[time_averaging]` when the run's build does not record the command as
  verified, at plan, naming the build and the measurement; it does not hang. The
  key, its validation, the window resolver and the provenance ship, so the feature
  works on a build where the command runs. Evidence:
  `reports/pfs0250/pfs0250_verification.json` and
  `reports/compat/CMP-26124_2026-09-19_time-averaging.yaml`.

### Added

- **A time-averaged surface, from the pproc.** A `[time_averaging]` table with exactly
  one of `last_revs` (revolutions of the rotor clock, converted through the same
  resolver as `LAST_REVS_AVG`) or `last_iters` emits `SOLVER_TIME_AVERAGING ENABLE
  <first> <last>` in the initialisation phase, so the surface flow exports (Tecplot,
  VTK, CSV) state the average over that window instead of the last step.
  **ON A BUILD WHERE THE COMMAND IS RECORDED VERIFIED, AND NO BUILD IS TODAY**: see
  the known limitation above, which is why a pproc carrying the key is refused at
  plan on 26.124 and on every build before 26.122. WHETHER THE COMMAND'S BOUNDS ARE
  TIME STEPS OR INNER ITERATIONS IS UNMEASURED: the command hangs the one build this
  release could run it on. The package converts to time steps, the database records
  the semantics as UNVERIFIED, and the conversion is a single function so the day a
  build settles it the correction is one line. The run records the window it emitted, and
  the products manifest marks those exports `kind: average` with the window, read
  from the record even if the pproc is edited later.
- **Surface flow in VTK and CSV.** Two `[exports]` kinds, `vtk` and `csv`, OFF BY
  DEFAULT, emit `EXPORT_SOLVER_ANALYSIS_VTK` (with `SET_VTK_EXPORT_VARIABLES` when the
  pproc lists `vtk_variables`, each validated against the build's database; absent,
  every variable) and `EXPORT_SOLVER_ANALYSIS_CSV`. Both join the per-step exports of
  `EXPORT_UNSTEADY_AFTER_REV` / `..._ITER` like the Tecplot file, and are the averaged
  surface when `[time_averaging]` is set.
- **Fourteen advanced solver settings have a setup key of their own**, so they no
  longer need `[[raw]]`: `laminar_separation`, `kutta_joukowski_lift`,
  `aeroelastic_rbf_type`, `print_rotor_induced_velocities`,
  `adaptive_field_grid_refinement`, `rotor_induced_velocity_blending`,
  `wake_numerical_relaxation`, `wake_relaxation`, `wake_decay_constant_per_m`,
  `wake_streamwise_agglomeration`, `jet_wake_decay_normalized_length`,
  `jet_wake_filaments_grid_induction`, `adverse_gradient_boundary_layer` and
  `vortex_ring_normalization`. Each emits its solver command when set and nothing
  when absent, so existing setups produce the same script; a value or command the
  run's build does not carry is refused naming the build; `[[raw]]` still works and
  an unknown key is still refused.
- **The six boundary-layer fluid-plot parameters** (`BL_MOMENTUM_THICKNESS`,
  `BL_DISPLACEMENT_THICKNESS`, `BL_TOTAL_THICKNESS`, `BL_SHAPE_FACTOR`,
  `BL_SKIN_FRICTION`, `BL_TRANSITION_MARKER`) are accepted in a pproc probe's
  `parameters` on the builds whose manual lists them (26.122 and 26.123 manuals,
  p.352; 26.124 carries the 26.123 manual). A parameter the run's build does not
  document is refused naming the parameter and the build. The pproc's own
  vocabulary refused them on every build before.

### Added

- **One sections file and one Cp file per distribution**, under `sections/`, named
  with the distribution's alias or families (the entry's position is added when two
  would collide): `<point>_sloads_<name>.csv` and `<point>_cp_<name>.csv`. With the
  per-step exports on (`EXPORT_UNSTEADY_AFTER_REV` / `..._ITER`) each file holds every
  exported step in a `STEP` column; without them it holds the end-of-run export. The
  Cp export was only listed in the manifest before and is now tabled. Every block a
  pproc entry emits, over its planes and blades, lands in that entry's file. A record
  that does not identify its distributions is a named skip: the split is never
  guessed. The combined sections series and the end-of-run sections table are
  unchanged. New public module: `pyflightstream.post.section_distributions`.

### Changed

- **Two public modules split out of `post.products`**: `post.provenance` and
  `post.custom_polar`. Every name importable from `post.products` today is still
  importable from there under the same spelling, and no product's format changed.

- **New catalogued exception `ProductArgumentError`** (base `TypeError`), raised when
  a product writer is called with arguments that contradict each other, such as
  `write_sections_table(step=..., iteration=...)`. `except TypeError` catches it as it
  caught the bare raise it replaces, and `except PyflightstreamError` now catches it too.

- **The recorded-export fixture carries a second witness**: a `sha256` column beside
  each row, so an export replaced on disk is caught even when its `Total` row still
  agrees. No printed value moved (48 rows, the value columns byte-identical).
- Source documentation and the requirements specification state requirements rather
  than attributing them to a person; no behaviour and no doctest changed.

### Deprecated

- **`write_sections_table(iteration=)` is now `step=`**, the one name for a solver
  step across the package's tables. The old keyword still works, with the ledger's
  deprecation warning, until 0.26.0; passing both is refused.
- **`run.assess_unsteady_from_plots` is deprecated**, for removal in 0.26.0: the
  collect path judges a point through `LoadsAssessor`, and this helper has no caller
  on it. It still returns what it returned.

### Fixed

- **A probes table combines every available history.** Where a pproc's `[[probes]]`
  entries ask for different parameters, the table carries a column per requested
  parameter and a point states `NA` where it was not sampled. Until 0.25.0 a point
  missing one column of its group was dropped, and entries asking for different
  parameters produced no table at all, whose refusal also cost the simulation its
  other products. A probe failure is now contained to the probes table. A RECORDED
  PROBE THE HISTORY CARRIES NO COLUMN FOR IS NAMED under `probes/<point>_probes.csv
  #positions` and the probes that have a history keep it: until the independent review
  of GitHub main it was dropped in silence and the point's skip was cleared, so a short
  table was indistinguishable from a whole one.
- **A refused or frozen rebuild retires the file it refuses**, under both archive
  policies: `products.json` said "skipped" while the stale table stayed at its
  normal path when archiving was off. THIS NOW REACHES THE ROTOR TABLES, whose skip
  is named for the simulation (`polars/<sim>#rotor_tables`) and whose files are named
  for the rotor, so cutting the skip key at `#` never found them and a refused rotor
  rebuild left its previous CSV current (the independent review of GitHub main).
- **A frozen point keeps what the freeze did not touch**: its histories, its
  last-step products and the averages whose window ends before the first frozen
  step. Only the averages that reach the freeze are left out, with their reason.
  THIS IS TRUE WINDOW BY WINDOW, not file by file: a reduction carrying several
  passages keeps the passages that end before the freeze and names the ones that
  reach it under `<file>#windows`. Until the independent review of GitHub main, one
  frozen passage took the whole file, including passages the freeze never touched.
- **A continuation keeps the surface averaging window** its predecessor recorded;
  it was lost, so the continued run's exports called themselves instants.
- **A recorded averaging window is validated when it is read**: a malformed one is
  refused naming the run, the field and the remedy, instead of raising KeyError or
  IndexError inside the post stage.

- **A campaign recorded with 0.24.0 posts with 0.25.0 without a re-run.** Measured on
  a recorded licensed campaign of five points: the stage exits 0, every product is
  written or skipped WITH ITS REASON, and no recorded file is rewritten. Two defects
  of the per-distribution split were found that way and fixed: a legacy record's
  section frame was matched loosely, so a block could be claimed by the wrong
  distribution, and the refusal of a record that cannot be split now names the
  missing evidence and says a new run is needed.
  See [RPT-054](reports/RPT-054_0-25-0-legacy-repost_2026-09-19.md).

- **A frozen unsteady solve is a failure, and its averages are not published.** A
  time step whose inner iterations after the first print a velocity residual of
  exactly zero, and whose last prints both residuals exactly zero, is frozen; two or
  more consecutive frozen steps make the point `FAILED_DIVERGED`, with the first
  frozen step and the count in its reason. `post` reads each point's native log too,
  so a run RECORDED as a success before 0.25.0 is caught on re-post: every average
  (unsteady polar row, rotor table, reduction) whose window reaches the first frozen
  step is left out with that reason in `products.json`, and an earlier post's stale
  file is archived. Windows ending before the freeze, raw histories and last-step
  products are kept. Measured on a recorded licensed campaign: two of four unsteady
  points froze, from steps 60 and 64 of 144.
  See [RPT-054](reports/RPT-054_0-25-0-legacy-repost_2026-09-19.md).
- **An unsteady polar of an `ADVANCE_RATIO` sweep states `ADVANCE_RATIO` on every
  row** (it wrote `NA`); the column under the matrix's key carries the point's `J`.
- **A rotor table that cannot be planned says why.** When a simulation's matrix row
  was deleted or its reference no longer resolves, the rotor tables are a named skip
  (`polars/<sim>#rotor_tables`) in `products.json` instead of vanishing.
- **The per-point skip reasons reach `products.json` when no point of a simulation
  has usable loads**; they were collected and then lost.
- **A `[names]` target that collides with a heading the product always writes**
  (a condition column such as `ALPHA` or `MACH`, the window and reference columns,
  `REDUCTION`, `ROTOR`) is refused when the pproc is read, naming the heading; it
  was found at write time and the product was dropped.
- **A rotor table from a family-templated plot group over the blades** (a group
  named with `{family}`) is written: a run now records the plot groups it emitted,
  with each one's frame, families and parameters, and post sums an exact,
  non-overlapping set of recorded MRP groups covering the rotor. A run recorded
  before 0.25.0 keeps the named skip.
- **A steady probe's `parameters` list is documented and warned about**: on a steady
  run it only enables the entry and does not select the exported variables, which
  are the probe-points export's fixed set; `pyfs-matrix plan` warns naming the entry.
- **An input artifact that exists and does not validate now says so first.** A matrix
  row naming a reference, setup or pproc whose file is present but invalid is refused
  with "the <kind> artifact at <path> does not validate" followed by the validation
  errors; "cannot resolve ... put the artifact at <path>" is said only when no file
  exists.
- **The run manifest's lock is recovered by ownership, not by age.** The lock records
  its owner (process, host and a token) and a live holder renews it every 5 s, so a
  slow writer is no longer displaced after 30 s. A waiter takes the lock over only
  when its owner's process is gone on this host or its heartbeat is older than 300 s,
  and a release removes only a lock its releaser owns. A writer of 0.24.0 or earlier
  does not follow this protocol: do not run two package versions against one
  workspace at once.

### Documentation

- `rotor_coefficients` and the user guide state the rotation sign:
  `J = V / (|n| D)` and `CP = 2 pi CQ sign(n)`, with `CQ` the signed torque about
  the fixed rotor axis. No computed value changes.
- The definitions page states that on a multi-rotor run each blade's window follows
  its own rotor's clock.

## [0.24.0] - 2026-09-19

### Fixed (refusals that protect a run and its products)

- Matrix rows stating `ALPHA` or `BETA` in both `FLIGHT_CONDITION` and
  `VAR_NAMES_VALUES` are refused, even when the values agree. Keep each attitude
  key in one interface and plan again.
- A steady polar whose loads vectors are in an analysis frame the package
  cannot rotate is refused. Workspaces exporting a rotor or custom frame must
  export loads in the global `MRP` frame and post those exports again.
- Staging refuses a destination that links to another file. Workspaces reusing
  linked input destinations must choose an ordinary destination or remove the
  link before staging again; the linked file is not overwritten.
- Staging refuses destination names that differ only by case. Campaigns with
  inputs such as `Wing.fsm` and `wing.fsm` must give them distinct names and
  update their references before staging again.
- Setup presets stating stabilisation through both `solver_stabilization` and
  `stabilization` / `stabilization_strength` are refused. Keep one interface in
  the preset and plan again.
- A pproc plot-group name whose placeholder carries a format spec or a
  conversion (`{family:.0}`, `{family!r}`) is refused when the pproc is read:
  the name may carry only the bare `{family}`. Rename the group. A name is
  letters, digits, underscores and that placeholder: no space and no other
  character, since the export reader strips whitespace from column names.
- A plot-group name another declaration could also produce is AMBIGUOUS and is
  never read as a rotor's or the geometry's global loads: its rotor table or axis
  block is skipped with the reason, never written from a history that may be
  another frame's. Give each group a name no other can produce.

### Known limitations

- The run manifest lock treats a lock older than 30 seconds as abandoned,
  even if its writer is still running. Workspaces with manifest updates lasting
  that long must serialize writers: let an update finish before another submit,
  collect or run operation writes the manifest.
  Lock ownership and renewal are registered for 0.25.0.

### Changed (breaking: a steady polar is built from the export's vector)

- **Every axis column of a steady polar row comes from the force
  `(Cx, Cy, Cz)` and the moment `(CMx, CMy, CMz)` the export states**, turned
  through `post/axes.py` (`polar_axis_coefficients`). `CDB` is now the `Cx`
  of the export and `CLB` its `Cz`. The row used to take the solver's `CL` and
  `CDi + CDo` as stability-axis forces and turn them BACK to body axes.
- **`CLS` and `CLW` fall, zero sideslip included, by
  between 0.10 and 0.25 per cent on 27 of the 28 lifting recorded exports
  (lift above 0.05); one sits at 0.71 per cent.** The `CL` an export prints sits that far
  above the wind-axis lift of the vector printed beside it; the cause is not
  known. The range is measured over the recorded exports of
  `tests/tier1_offline/fixtures/recorded_total_rows.csv`, and a tier-one test re-measures it. On the
  recorded point at alpha -2 the exports differ by 0.135 per cent, and at the
  five decimals a polar prints `CLS` 0.18828 becomes 0.18800, `CLB` 0.18744
  becomes 0.18716, `CDB` 0.02744 becomes 0.02743. `CDS`, `CDW`, `CD0`, `CDI`
  and every moment at zero sideslip are unchanged.
- **A point under sideslip gets its polar row.** It was refused, because the
  wind-axis turn had been checked against nothing. It is checked against
  scipy's rotations under both angles and against the recorded exports, whose
  own drag is the wind-axis drag of their own vector. `BETA` states the
  sideslip; the axes turn by the geometric angles of the velocity the solver
  flies, which the definitions page gives.
- `polar_row` takes `beta_deg=`; `GroupCoefficients` carries `force` and
  `moment`, the export-frame sums.
- Public surface: the new module `pyflightstream.post.axes`:
  `polar_axis_coefficients`, `EXPORT_TO_BODY`, `dcm`, `body_to_stability`,
  `body_to_wind`, `free_stream_in_export_frame`, `velocity_in_body_frame`,
  `wind_angles`, `stability_force_coefficients`, `wind_force_coefficients`,
  and `blade_azimuth_deg`, where a blade is at a step: the one rule the
  sections table, the per-blade table and the per-blade rows call.

### Added (the `[names]` dictionary of the pproc)

- `[names]` maps a plot column as the export prints it to the name a reader's
  tool expects (`CL_MRP_TOTAL = "CL_TOTAL"`). It renames columns of the unsteady
  polar and of the averaged reductions; the plots table stays raw, and absent,
  every name passes through as printed. The axes and the equations read the
  export's names, and the dictionary is applied last.
- The whole dictionary applies or none of it does: an entry naming a column no
  plot prints, or a name the table already carries, leaves the export's names
  in place and is said under `polars/<file>#names` or `probes/<point>#names`.
  The unsteady polar already carries the native export's last-step `CL`, so that
  name is taken; `CL_TOTAL` is not. Two entries for one name are refused at load.
- Public surface: `post.products.renamed_columns`.

### Added (three pproc tables, which ship together)

- **`[phase_locked]`** (`min_revolutions`, `last_revolutions_avg`), optional. With
  it, `probes/<point>_phase_locked[_<ALIAS>].csv` is one row per AZIMUTHAL
  position of the rotor's last revolution, each value the mean of the samples at
  that azimuth across the last `last_revolutions_avg` revolutions. It is generated
  when the row turns at least `min_revolutions` (`>=`); a shorter run skips THIS
  table only, with both numbers in `products.json`, and keeps its polar and every
  other product. The table is read again at `post`, so adding or editing it needs
  no solver run. A pproc without it keeps the passage series it always got.
- **`[equations]` and `[glossary]`.** An equation names an ALIAS and a frame, never
  a mesh family, so every derived column is `<NAME>_<alias>`; equations may chain
  and a cycle is refused when the pproc is read. They are EVALUATED at `post`
  into `P<sim>_<name>_uns_avg.csv`, after the axis block. The expression is parsed
  and walked, never executed: numbers, names, `+ - * / **`, parentheses and `abs,
  sqrt, sin, cos, tan, radians, degrees, min, max`. A symbol reads another
  equation first, then `<S>_<alias>` in its frame, then the exact column. A symbol
  that resolves to nothing refuses the equations block, named under
  `polars/<file>#equations`, and never writes a column of `NA`.
- **`inputs/pproc/VARIABLES.md` and `WRITING-EQUATIONS.md`**, generated from the
  code by `pyfs-workspace init`, `pyfs-matrix plan` and `pyfs-matrix post`, and
  rewritten only when their content would change. No other file of that folder is
  touched. Commit them or ignore them.
- 0.23.0 refused all three table names by name, because a pproc written for a
  release carrying only some of them is unreadable by it. They bind together.
- Public surface: `pyflightstream.post.equations`; `post.unsteady.phase_locked_rows`
  and `blade_one_azimuth`; `post.products.write_phase_locked_table` and
  `PHASE_LOCKED_COLUMNS`; `cases.windows.phase_locked_entry`, `regate`, `AZIMUTHAL`;
  `workspace.register_input_guide` and `write_input_guides`; `CampaignPlan.guides`.
- Public surface, also: `post.equations.apply_equations`, `resolve_symbol`,
  `derived_column`; `post.guides.write_pproc_guides`,
  `write_workspace_pproc_guides`, `PPROC_GUIDE_NAMES`, `VARIABLE_DEFINITIONS`.

### Added (the super file in fixed-width text)

- `[products] superfile_format = "legacy_polar"` writes the super file as
  fixed-width text, sixteen characters a field, with the same columns and values
  as the `csv` form, which stays the default. 0.23.0 moved this out and refused
  the key by name; the writer stayed and ten tests were parked, and they run
  again. A pproc that CHOSE `csv` is not overridden by a campaign-wide format.

### Added (the unsteady polar states its axes)

- **`P<sim>_<name>_uns_avg.csv` carries the eighteen axis coefficients**,
  under the steady polar's own eighteen names (`CDW .. CNW25`, `CDS .. CNS25`,
  `CDB .. CNB25`), after the plot columns, EACH suffixed with its plot group's
  whole name: `CLW_MRP_TOTAL`, `CMW25_MRP_TOTAL`. They come
  from the plots of the global `MRP` frame: the window average of `FX, FY, FZ,
  MX, MY, MZ` of a plot group declared in that frame, made coefficients by the
  row's own `RHO`, `VINF`, `SREF` and `CREF` and turned through `post/axes.py`.
  Never a rotor's own frame. The suffix is there with one group or several,
  so adding a group to the pproc renames no column a reader is keyed to, and two
  groups can never write one column. The groups are read off the pproc
  artifact, because a plot's column states its group's name and not its frame.
- **An unsteady run whose pproc plots those six for no global-frame group gets
  the group `MRP_TOTAL` added** (six more `UNSTEADY_SOLVER_NEW_FORCE_PLOT`
  commands, where the run has an `MRP` frame). A pproc that already plots them
  renders the same script, byte for byte. Ten tier-3 goldens gained the six
  plots and nothing else.
- Where the block cannot be written, no such plots in a run made before
  0.24.0 or a row stating no density, `products.json` says why under
  `polars/<file>#axes`. `pyfs-matrix post --strict` counts that as a skip.
- Public surface: `post.products.UNSTEADY_AXIS_COLUMNS`, the eighteen names
  before their suffix; `cases.AXES_PLOT_GROUP`, `AXES_PLOT_COMPONENTS` and
  `ROTOR_PLOT_GROUP_PREFIX`, the plot groups a run adds.

### Changed (breaking: `per_blade` is one row per blade)

- **`probes/<point>_per_blade_<ALIAS>.csv` holds one row PER BLADE over the one
  shared window**, each with `BLADE`, `FAMILY`, `AZIMUTH_START` and
  `AZIMUTH_END`, which is the definition the definitions page has carried
  since 0.23.0. The file was one row with the time average's shape, the
  TOTAL's columns included, under the per-blade name; `per_blade_rows` had no
  caller and the record's `blade1_azimuth_deg` no reader.
- A blade's columns are the plots ENDING in its family (`CL_MRP_Blade1`),
  written with the family removed (`CL_MRP`). The azimuths are where that blade
  is at the window's first and last step: its rotor's datum, the blade's
  position by `360 / blades`, the rotor's sense and its own steps per
  revolution, wrapped.
- The run records each rotor's blade families in the reductions plan
  (`blade_families`), so a workspace posted without its matrix still knows
  them; an older record asks the reference the row names.
- **A row that states its rotor with flat keys and cites no rotor block gets no
  per-blade table**, with the reason in `products.json`: nothing says which
  families are its blades. So does a run whose plots hold no column of a blade.
  `write_per_blade_table` is public; `per_blade_rows` takes `blade_families=`
  and `sense=`.
- Public surface: `post.products.PER_BLADE_COLUMNS`.

### Fixed (changes a published number: an unsteady rotor table is the window average)

- **Every rotor table of an unsteady point held the LAST TIME STEP, and it now
  holds the average over the row's window.** The average was looked for under
  `FX_<alias>` ... `MZ_<alias>`, and a force plot is named for its pproc group
  (`FX_HUB_PUSHER`), so the lookup missed on every campaign and the fallback to
  the native export was silent. On a recorded licensed rotor point the two
  differ by 43 per cent: -410.75 N at the last step against -287.82 N over the
  row's window (`reports/RPT-053_what-an-unsteady-export-states-and-when_2026-09-19.md`, campaign `pfs0230`
  row 2302 at alpha 10). The history is found through the
  pproc now: the plot group in the global `MRP` frame whose families are
  exactly the rotor's (`post.products.rotor_plot_source`).
- **An unsteady run adds that group where the pproc plots none:** six Newton
  plots per rotor the row turns, `FX_ROTOR_<ALIAS>` and its siblings, over the
  rotor's general and blade families, where the run has an `MRP` frame. A pproc
  that already plots the six over exactly those families renders the same
  script for that rotor. Twelve tier-3 goldens gained the plots and nothing
  else.
- **A group in a rotor's own frame is never the source**, and neither is a group
  that only shares the alias's name over other families. A bare `FX_<alias>`
  arises only from `{family}` in an expanding frame, in axes that turn with the
  rotor and with its moment about the hub; the table used to average it and
  then transfer that moment to the hub a second time.
- **A row that states a window never gets an instant in its rotor table.** A
  point with no usable history is left out and named under `skipped`, as the
  unsteady polar beside it does; the table used to write the last step beside
  averaged rows under one header. The manifest entry states `source` and
  `window`. A campaign run before 0.24.0 whose pproc plots no such group gets
  NO rotor table for its unsteady points, with the reason: declare the group
  and run again, or read the steady points.
- Public surface: `post.products.ROTOR_TABLE_LEAD_LINES` and
  `ROTOR_TABLE_SUFFIX`, the first lines and the file-name suffix of a rotor table.

### Fixed (changes a published number)

- **`ETAW` AND THE SHAFT ANGLE WERE COMPUTED AGAINST A FREE STREAM WITH TWO
  WRONG SIGNS**, in every rotor table row with a non-zero incidence or sideslip.
  0.23.0 built the free stream as `(cos a cos b, +sin b, -sin a cos b)`; the
  export's frame is x aft, y right, z up, and the air moves along
  `(cos a cos b, -cos a sin b, +sin a)`. It is measured, not derived: a loads
  export states its own drag, and projecting its total force on the old vector
  gave -0.01058 where the export of incidence 4, sideslip 2 states +0.03578.
  A rotor whose force has a component off its shaft therefore had its wind-axis
  force, and `ETAW`, wrong; a rotor pushing exactly along the stream at zero
  angles is unaffected. `pyfs-matrix post` rewrites the tables; no re-run.
  The rotation now lives in ONE module, `pyflightstream.post.axes`, whose tests
  take their expected values from scipy's `Rotation` and from the recorded
  exports' own drag, never from the implementation.
- The force along the stream takes the SENSE the reference gave the rotor's
  shaft, so `ETAW` reduces to `ETA` at zero angles whether the axis was
  declared pointing aft or forward.

- **EDITING THE AVERAGING WINDOW MOVED THE POLAR AND LEFT THE REDUCTIONS
  BEHIND.** 0.23.0 resolved `LAST_REVS_AVG` / `LAST_ITERS_AVG` from the matrix for
  the unsteady polar alone; `<point>_time_average.csv`, the per-blade table and
  the phase-locked passages kept the window the RUN had recorded, in the same
  folder, under a manifest calling both "the row's window". Every window of a
  point now comes from one resolver, `pyflightstream.cases.windows`, which the
  plan and the post stage both call: the matrix wins the record, the record is
  never rewritten, and each rotor's span is cut on ITS OWN steps per revolution.
  The post stage says so when the matrix and the record differ. No re-run.
- The window is resolved PER POINT. It was resolved once per simulation, off the
  first record, which is right only while every point of a row shares one clock.

- **A ROW SWEEPING A FLOW VARIABLE RECORDED, AND PUBLISHED, THE FIRST POINT'S
  STATE ON EVERY POINT.** Each point of a `MACH`, `TASmps`, `REmi`, `ALTFT` or
  `dISA` sweep ran at its own velocity and density, and its run record was
  written from the simulation-level case: a Mach 0.3 run recorded Mach 0.1, the
  polar printed 0.1 on its row, and the rotor table divided by another point's
  density. New records carry the point's own state. For records ALREADY written
  the post stage resolves each point again from its row, uses that, and says so;
  the record is left as it was. No re-run. A row that sweeps an angle or an
  advance ratio is unaffected.

### Changed (breaking: every product table gains columns)

- **EVERY PRODUCT STATES EVERY DIVISOR OF ITS COEFFICIENTS.** The condition block
  every composed table carries is now

      ALPHA, BETA, MACH, RE, VINF, VREF, ALT, RHO, TEMP, MU, J, SREF, CREF, BREF

  `VREF` is the solver's reference velocity, read off that point's export; `RHO`,
  `TEMP` and `MU` are the air the run resolved for that point (kg/m3, K, Pa s,
  the last in scientific notation). 0.23.0 stated the coefficient and the area
  and neither the density nor the velocity it was divided by. A READER THAT
  SELECTS COLUMNS BY NAME IS UNAFFECTED; ONE THAT READS BY POSITION OR COUNTS
  COLUMNS MUST BE UPDATED. The list is defined on the definitions page, and a test
  compares the package with the page rather than with itself.
- **THE UNSTEADY POLAR IS `polars/P<sim>_<name>_uns_avg.csv`**, where 0.23.0 wrote
  `<sim>_<name>_unsteady.csv`. A rebuild ARCHIVES the file under the old name
  rather than leaving it beside the new one. Each row opens with `FIRST_STEP`,
  `LAST_STEP`, `STEPS`, the window THAT point was averaged over, which was in
  `products.json` alone; the moment point `XMOM`, `YMOM`, `ZMOM` follows the
  reference lengths, because the table carries the plots' moments; and THE SUPER
  FILE'S CONTENT IS ADDED to the table, after the plot columns: the matrix row's
  cells, the record's scalars, each rotor's speed and the solver flags. The super
  file is what the polar does not have, and for an unsteady point it is not a
  second file.
- **THE REDUCTION TABLES** (`<point>_time_average.csv` and the per-rotor
  `per_blade` and `phase_locked` files) gain `ROTOR` after `REDUCTION`, the alias
  the reduction is cut for and `NA` on the time average, and `XMOM`, `YMOM`,
  `ZMOM` after the reference lengths. THE COLUMNS `Time-step` AND `Time (sec)`
  LEAVE THEM: every column of the plots table was averaged, the clock included,
  so a row stated steps 1 to 8 beside `Time-step 4.50000`. The plots table itself
  keeps its clock, which is its axis.
- **THE ROTOR TABLE** gains `RPM_<alias>` and `DIAMETER_<alias>` before its
  coefficients: every one of them divides by `rho n^2 D^4` or `D^5`, and with
  `RHO` in the shared block the table now states all three. `J` (what the row
  REQUESTED) stays beside `J_<alias>` (what that rotor RAN at, and the one the
  coefficients use); the post stage says so when they differ on the rotor the row
  sweeps. `J_<alias>` is computed with the FREE-STREAM velocity, not the solver's
  reference velocity: it is a ratio of the flight speed. No recorded campaign
  sets the two velocities apart, so no recorded number moves.
- The post stage WARNS, naming the point, when an export's reference velocity is
  not its free stream: the steady polar's coefficients are by `VREF`, while the
  plots table, its reductions and the unsteady polar are rescaled to `VINF`.

### Changed (breaking: the sections table and the series name their rows)

- **`ITERATION` is `STEP`, and so is the series' `step`.** One name for the
  solver step across every table the package writes.
- **A sections row says which distribution it belongs to:** `FAMILY`, `PLANE`
  and `ROTOR` follow `STEP`. The export concatenates every distribution the
  pproc declares with no marker, and with `Offset` the only coordinate two
  distributions of similar span could not be told apart. The run records the
  blocks (`sections_layout` on the run record); a record written before this
  release states `NA`.
- **`AZIMUTH` is blade one of the row's OWN rotor**, from that rotor's datum,
  in its sense of rotation, on its own steps per revolution, wrapped. It was
  one number for the whole file: the row's clock rotor, turned from zero,
  unsigned, written on wing rows too. `write_sections_table` takes `layout=`
  and `rotors=` and no longer takes `step_deg=`.
- The sections entry of `products.json` says `"kind": "instant"`.
- **The series state the condition block**, as every other product does; the
  probes series says WHICH probe a row is in `PROBE`; the sections series
  leads with `STEP, time_s, FAMILY, PLANE, ROTOR, AZIMUTH`.
- **A submitted point gets its series.** The stamped per-step exports are
  looked for in the point's datapoint folder as well as the simulation
  folder; they were searched for at the simulation's top level only, so a
  point collected from a cluster got three header-only tables recorded as
  written. A kind with no stamped file is no longer written: it is a named
  skip.
- Public surface: `post.products.section_identity`; `post.series.SECTIONS_SERIES_LEAD`
  and `PROBE_COLUMN`.

### Changed (breaking: a reference the solver did not use is refused)

- **A simulation whose loads export was normalised by another area or chord
  than the products would state gets NO product, and the two numbers are
  named.** The package emits no reference-setting command, so the solver
  divides by the area and the length of the project file it opened, and the
  export prints both; every product states `SREF` and `CREF` from the
  reference artifact, and nothing compared the two. A project carrying 40 m2
  beside an artifact stating 50 posted `SREF 50.00000` next to coefficients
  divided by 40. The comparison allows the export's printed precision, three
  decimals. A workspace whose artifact and project agree is unaffected; one
  that is refused was publishing coefficients wrong by a constant factor.

### Fixed (a row stating its one rotor with flat keys gets that rotor's table)

- A row that states `RPM` and `ROTOR_AXIS` and no `MOTIONS` list plans no
  per-rotor block, and the rotor table read a rotor's speed from that block
  alone, so such a row never got its table; 0.23.0 made that a named skip. The
  plan of such a row now records the speed it turned at (`rpm`, signed), and the
  table is written when the row's reference declares EXACTLY ONE rotor, whose
  speed it can only be. With several rotors nothing says whose speed it is and
  the skip stays. A run made before 0.24.0 recorded no such speed and keeps its
  skip; state the rotor through `MOTIONS` or run the row again.

### Fixed (the step of an unsteady point's sections table)

- On an unsteady run the export header's `Current solver iteration number` counts
  the solver's INNER iterations, summed over every time step: 2813 on a licensed
  run of 144 steps (`RPT-053`, campaign `pfs0240` row 2411; the mechanism was
  first recorded in `RPT-005`). The sections table took it for the step, so
  `STEP` read 2813
  and `AZIMUTH` was computed from it (25 degrees for a blade that was back at 0).
  The sections export of an unsteady point is written when the march ends, so its
  `STEP` is the run's last time step, which the record states (the step a
  watchdog stopped it at, else the steps the plan marched). A steady point still
  reads the iteration its own export states. 0.23.0 published the same column as
  `ITERATION` with the same number.

### Fixed (a held inputs folder costs a link, never the run)

- Staging makes `sims/sim_<id>/inputs` a link to the geometry library, and first
  removes the empty folder that stood there. Where a sync client holds that
  folder for a moment, the removal is refused with "access denied", and the
  whole matrix stopped before any solver started (`matrix not run: [WinError 5]`).
  The removal is covered by the fallback the link already had: the inputs are
  copied and the record says why. Met on a licensed campaign whose workspace
  sits under a synced folder.

### Fixed (a continued point is in its tables once)

- A run that was CONTINUED is left out of the products and of the sweep table,
  and named: under `skipped` in `products.json`, in a warning from
  `sweep_table`. A continuation writes into the folder of the run it continues
  and no record is rewritten, so the stopped run's record went on naming files
  its continuation wrote; a run that reached its iteration limit and was then
  continued put the point in its polar twice, both rows carrying the
  continuation's coefficients. Only the record's own `continues` field is read
  (`results.superseded_by_a_continuation`): two runs that merely resemble each
  other are both kept, and a chain recorded before 0.24.0 states nothing and is
  unchanged.

### Fixed (a rotor's alias in a file name and in the union)

- The rotor table's file name takes the alias through the same sanitiser as
  that rotor's passage reductions. Raw, an alias holding a slash wrote the
  table into a subfolder and keyed the manifest with the slash, and a colon on
  Windows wrote a stream nobody can see. The rotor's own spelling is still the
  file's first line and the manifest's `rotor` field.
- The union of what the workspace knows (`reports/superfile-<tag>.json`,
  `known`) reads a rotor table's HEADER, its second line. It read the first,
  the alias alone, so `known` carried the alias as if it were a column and
  none of the table's real columns. `known` now lists `J_<alias>`,
  `CT_<alias>` and the rest. The super file does not carry those columns, so a
  reader comparing the two now sees that difference, which is real.

### Fixed (one column name, one source)

- **`ALT` CAME FROM THREE SOURCES IN ONE FOLDER.** The sections table read the
  export's `Altitude (ft)` line, which a campaign never sets, and printed
  `0.00000` on a row whose cell says `ALTFT:10000`, beside a polar printing 10000
  and a rotor table printing `NA`. The sections table now states the point's
  condition through the same assembly as every other family, and the rotor table
  reads the point's own cell. A row that states no altitude reads `NA`.

### Changed (breaking: an unsteady row states its averaging window)

- **`LAST_REVS_AVG` ON AN `unsteady_rotor` ROW, AND `LAST_ITERS_AVG` ON AN
  `unsteady` ONE, ARE REQUIRED.** `pyfs-matrix plan` refuses a row that states
  neither, naming the case and the key with an example. The definitions page
  always said the window is a required matrix input; 0.23.0 did not refuse, and a
  row without it took the STEADY route at post: polars read off the LAST TIME STEP
  under the steady names, beside a time average over a window the package had
  defaulted, with nothing marking either. A row that still states `WINDOW_STEPS`,
  `WINDOW_REVOLUTIONS` or `WINDOW_DEGREES` satisfies the rule until 0.26.0.
- **A RECORD ALREADY WRITTEN WITHOUT A WINDOW IS NEVER REFUSED, AND ITS POLAR
  CHANGES KIND.** `pyfs-matrix post` averages it over the window its run
  recorded (its default: the last revolution with a rotor, the whole run without;
  or a retired `WINDOW_*` key of the row, named as such), writes
  `P<sim>_<name>_uns_avg.csv`, and SAYS which steps that was and how to choose
  another. The group polars, the super file and the `.dat` that such a point
  used to get were read off the last time step and are no longer written for it.
  State the key on the row and post again to choose the window; no re-run.
- Public surface: `cases.windows.averaging_steps`, `averaging_span`, `passages`,
  `stated_key`, `replan`, and the two keys `LAST_REVS_AVG` and `LAST_ITERS_AVG`.

### Changed (an input format, with the old form still read)

- **A PPROC GROUP IS ONE ALIAS, WRITTEN AS A STRING.** `[groups]` took a list of
  members; it takes the alias the group names:

      [groups]
      PUSHER   = "PUSHER"      # a rotor of the reference: its own families
      AIRFRAME = "airframe"    # an alias of the reference's [aliases] table
      TOTAL    = "all"

  The key still names the product file (`..._PUSHER.csv`), so a steady polar per
  alias is one line. A group that names a rotor, under any key, is that rotor's
  families. THE LIST FORM STILL BINDS and warns with the line to write instead,
  until 0.26.0: a one-member list becomes its string, and several members become
  ONE alias declared in the reference. A list holding a position, which the
  motion path reads, has no alias to be rewritten as and says nothing.
- The members of a group resolve through the reference AS IT STANDS when
  `pyfs-matrix post` runs, not through the alias table frozen into the run
  record, so renaming or extending an alias needs no re-run. The record is the
  fallback where the reference no longer resolves.

### Fixed (the word the deprecation tells you to write)

- A `[groups]` entry written as an EMPTY list is every family, and the
  deprecation of the list form tells its owner to write `NAME = "all"`. As a
  group's one alias, `"all"` selected nothing, so following the package's own
  advice turned the polar of the whole configuration into a named skip. `"all"`
  selects every family (`cases.EVERY_FAMILY`); an alias, a boundary or a family
  of that name is tried first. The workflows page teaches a group as ONE named
  alias written as a string; it still taught four numbered member lists.

### Fixed (a zero that was not a measurement)

- A group whose alias selects NO surface of any loads export of the simulation
  wrote a polar table of `0.00000` in every column. The table is not written and
  the group is named under `skipped` with the surfaces the export does carry.
- A rotor whose families select no surface of a point's loads export printed
  `CT 0.00000` for that point. The point is left out of the rotor table and
  named, like every other point that is not a row.

### Changed (the type-checker debt, re-measured on the release tree)

- the type-checker debt of this release, re-measured on its own tree, was 661
  errors in 18 of 93 modules (the sentence in the guarded form belongs to the
  newest measurement, which is 0.25.0's). The four modules that release adds, `post/axes.py`, `cases/windows.py`, `_expressions.py` and
  `post/equations.py`, arrive with no error; the 22 more than 0.23.0's reading
  sit in modules that were already exempt (`reports/RPT-029`).
- The old entry of 0.8.0 that stated the reading was redated at every recount,
  so it said a figure measured five weeks after it was written. It now points
  here and states no number of its own.

### Changed (a removal promise that moved)

- The manifest key `broken_commands` is still READ, and its removal moves from
  0.24.0 to 0.26.0. Re-measured when this cycle opened: 74 recorded rows across
  4 manifests still carry it, and a recorded manifest is never rewritten.

### Fixed (the cluster path: collect, the run records and the manifest)

- **A STEADY SWEEP SUBMITTED TO A QUEUE WAS COLLECTED AS ONE POINT.** One status
  was stamped on every point and no point carried its outputs, so the post stage
  passed over all of them: no product, no skip, exit 0. Each point is now
  collected, assessed and finalised on its own, and the job's status is its
  worst point. A sweep collected BEFORE this release keeps the record it has;
  repairing it from its collected folders is a one-off step, not a re-run.
- The collected verdict is asked the velocity the row requested, as the local
  verdict always was: a point exported at 30 m/s against a request of 80 was
  FAILED locally and CONVERGED once collected.
- **A solver log no longer excuses an unfinished solve.** A forced run exported
  before its last iteration was refused without a log and ACCEPTED with one, and
  a log ending at another iteration than the export was read as that export's.
  Completeness is checked first, and a log whose last iteration is not the
  export's is refused naming both files. SOME ROWS THAT WERE ACCEPTED WILL NOW BE
  REPORTED AS FAILED WHEN RE-ASSESSED; they were never complete.
- Readiness is judged on the scheduler's OWN log file, copied to the declared
  name after it settles. The copy was made first and then watched, so a job
  still running was collected on the log of the moment it was copied.
- `pyfs-matrix collect` posts each matrix it collected. It called the stage with
  no matrix, which selects no named-matrix record, so it posted nothing.
- A queue profile that says `export_log = false` governs every route that emits
  the log export; the ordinary matrix route ignored it and spent a seat on a job
  the cluster aborts.
- A continuation that cannot be resolved is RECORDED as a failure and reported.
  A continuation's record names the run it continues in the new field
  `continues`, and a row stopped by the wall clock whose pproc declares sections
  can be continued (the section distributions live in the saved state).
- Two writers on one `runs.json` keep both changes: the manifest is rewritten
  under `runs.json.lock`, through a temporary file per process.
- A `VAR_NAMES_VALUES` key stated twice, and one solver setting spelled two ways
  in a setup, are REFUSED by name; the last one written used to win in silence.
- `--sweep-csv` writes ONE sweep table, where the help says it does; `run_matrix`
  and `run_campaign` take `sweep_csv`, and `collect_and_post` takes `post_matrix`.
- The refusal of a negative `ALTFT` said the flight condition cannot hold one. It
  can; the point NAME cannot carry it, and the sentence now says that.

### Fixed (a product that vanished now says why)

- **`products.json` NEVER CLAIMS A FILE THAT IS NOT ON DISK.** It was written
  once, last, after every existing product had been moved into `archive/`; a
  rebuild that died on anything but a product refusal left the PREVIOUS manifest
  naming files that had just been moved away. The previous manifest is removed
  first, and a rebuild that dies still writes one: `complete: false`, the reason
  under `interrupted`, and only the products that are on disk. A finished rebuild
  says `complete: true`.
- A matrix the post stage cannot read, or that is not at the workspace root, is
  SAID. It used to fall back to the run records in silence: an edited window did
  nothing and the rotor tables, which take their geometry from the row's
  reference, left the disk and the manifest with the stage reporting success.
- The products follow the pproc the ROW names today, and the stage says so when
  that is not the one the run recorded. The row's PPROC cell only stamped the
  super file before, so pointing a row at another pproc changed nothing else.
- The sections report is written for a windowed unsteady campaign. It sat in the
  branch that writes a super file, which such a campaign does not draft.

- A pproc that NAMES its groups and sets `custom_polar_format = true` stopped the
  whole products stage on a bare `ValueError`: the fixed-width format states the
  group as a two-digit number. A named group states its position in the
  `[groups]` table, counted from one, and the file's name carries the alias.

- A run recorded as successful whose loads table is not on disk, or that names
  no output, left every product in silence. It is named under `skipped`.
- The unsteady probe table was unreachable on a default unsteady row: its gate
  asked whether the steady probe export existed, and every such row leaves one
  declaring zero points. It asks what the steady writer wrote.
- An export one reader refuses now costs THAT product. A sectional-loads or
  plots export that could not be read aborted the whole simulation after its
  polars were on disk, so the manifest disowned files it had just written.
- `[products] polars = false` on an unsteady row with a stated window was an
  `UnboundLocalError` that aborted the post stage for every simulation.
- The unsteady polar's `runs` named every run of the simulation while the
  writer left points out. It names the points the file holds.

### Removed (names nothing called)

- `post.unsteady.converged_window`, `post.products.group_product_name`,
  `post.superfile.declared_sweep` and `post.superfile.SUPER_PREFIX`. None had a
  caller. `converged_window` held the opposite of the shipped window rule; the
  window is `cases.windows.averaging_span`. The super file's prefix is
  `workspace.naming.SUPER_FILE_PREFIX`. `post.products.SECTIONS_DIR` is added,
  the `sections/` folder as a constant beside `POLARS_DIR` and `PROBES_DIR`.

### Fixed (a warning and three docstrings that said the wrong thing)

- The deprecation warnings of `WINDOW_STEPS`, `WINDOW_REVOLUTIONS` and
  `WINDOW_DEGREES` name the replacement keys as the matrix reads them,
  `LAST_ITERS_AVG` and `LAST_REVS_AVG`. They spelled them in lower case, and a
  row written that way is not read.
- The `rotor_coefficients` docstring states `ETAW = J CTW / CP`, as the
  definitions page does, and no longer the cosine form. The `post.products` and
  `super_file_name` docstrings state the file names the stage writes.
- The layer rule is now held over module-level imports across the whole package,
  with no allowlist; two upward imports planted at module level used to pass
  both existing guards.

## [0.23.0] - 2026-09-18

Sixteen items, all of them about the same thing: **every file the post stage
writes says what it is.** The release opened with one message, and both halves
of it shipped -- a super file that could not be written in the format she reads,
and a super file whose blank cells broke her CSV reader.

**NOTHING HERE NEEDS A RE-RUN.** Every change below is produced by
`pyfs-matrix post --workspace <root>` over outputs already collected, on
Windows and on the cluster, with one exception -- `submitted_by`, the first
bullet of *Owed* at the end.
See `docs/migrating-to-0.23.0.md` before upgrading a workspace you care about.

### The independent review, and what it changed before the tag

This release was read by an **independent reviewer** -- a separate tool, on a
clean clone of `main` from GitHub, after the push and before the tag. It ran
after four in-house review rounds had closed with 92 findings between them, and
**it found seven more that none of them had.** Every one was a wrong number or a
missing product. They are fixed here, and the fixes were themselves reviewed,
which found four more. The record is `GEO-055`.

Three of the seven matter to anyone with a rotor:

- **A rotor table's rows were dimensionalised by the FIRST point of the sweep.**
  The rotor speed, air density and velocity were read once and reused for every
  row, so an advance-ratio sweep -- the one shape the table exists for -- came out
  a factor of four wrong from its second point. The flight-condition columns in
  the same row were correct, so nothing looked wrong.
- **A counter-rotating rotor produced no table at all**, with nothing recorded
  to say it was missing. A negative rotor speed is a direction and was read as a
  stopped rotor.
- **An unsteady rotor table published one instant of a cycle** beside a polar
  that averaged correctly, in the same folder, with neither file saying which it
  was.

### `LAST_REVS_AVG` and `LAST_ITERS_AVG` now work from POST alone

**This is the change most likely to affect what you do next.** The averaging
window was resolved when a point RAN and stored in its record, so editing the
key in the matrix and re-running only the post stage changed nothing -- and a
workspace recorded before 0.23.0 fell back to the last time step, silently, in
both cases.

The post stage now resolves the window from **the matrix as it reads it**,
against the clock the record already carries. Change the key, re-run `post`, get
the new window. No solver run, on Windows or on the cluster. Where the matrix
names no key, the window the run recorded still stands.


### Changed (breaking)

- **A polar group is named, and the product file carries its NAME instead of
  `_g01`.** `GROUPS` takes one named input per group, and a number told you
  which position the group held in a list, which is a fact about the list and
  not about the group.
  - **YOUR EXISTING PRODUCTS ARE RENAMED, NOT ORPHANED**, by
    `pyflightstream.workspace.rename_group_products(root, {1: "PUSHER", ...})`.
    You supply the mapping because nothing in a workspace records which group
    `_g03` was; a number it is not given is LEFT ALONE rather than renamed on a
    guess, and `pyflightstream.workspace.unmapped_group_numbers(root, mapping)`
    NAMES the numbers you left out, with the products carrying each. Run it
    before the migration, which is while you can still act on it: a number you
    forgot is otherwise indistinguishable from a number that was never there.
  - **IT REFUSES BEFORE IT MOVES ANYTHING.** Every product is checked first and
    moved second, so a refusal saying nothing was moved is true of the FOLDER
    and not only of the moment it was written. Two numbers you mapped to one
    name are refused too, which the per-file check cannot see: neither
    destination exists when the first is tested.
  - **IT ARCHIVES BEFORE IT MOVES**, and deletes nothing. A copy of each file
    lands under `archive/rename-groups-<stamp>/` first and stays there after a
    successful move: the cheapest way to be wrong about a migration is to be
    unable to look at what was there before. That is the default; `archive=False`
    moves without a copy. `dry_run=True` reports what would move, moves nothing,
    and its records name NO archive, because none was written.
  - A destination that already exists is REFUSED, naming both paths, and
    nothing moves. Two products cannot share a name and one of the two is a
    result.
  - A group whose name IS the old numbered form (`g01`) is refused, because a
    file named after it could not be told from the form it supersedes and the
    migration needs that difference to know what it has already moved.
  - **The super file's union was the trap and it is closed.** That union is
    built by matching file names, so a renamed group would simply not be there
    and the assertion that the union is a superset would have stayed green
    over the smaller set. The pattern now matches both eras and a test asserts
    the pattern itself rather than an outcome that nothing satisfies.

- **A CSV cell that does not apply to a row now reads `NA`, where it was
  blank.** This changes the bytes of every CSV product, so a reader that
  already works on 0.22.0 output has to be told about it -- this entry is for
  anyone who PARSES a product rather than reads one.
  - **WHY A BLANK WAS THE DEFECT.** It is ambiguous three ways -- zero,
    not-measured, or this-column-is-not-for-this-row -- and no reader can tell
    them apart. Measured on a production super file, 50 of 628 columns in one
    row were blank for the third reason alone: a key declared for the union of
    every run type, on a row whose run type does not have it.
  - **`NA` SAYS THE THIRD OF THOSE THREE, WITH ONE NAMED EXCEPTION.** A value
    that was EXPECTED and went missing is not meant to be spelled this way.
    The exception is the probes table of a run recorded before 0.16.0: it
    names no positions file, so its position and frame cells are a value the
    package could not derive, and they read `NA` because a blank is the one
    thing a product may not write. Refusing those tables would take a product
    away from a campaign that already happened, so the exception is carried
    rather than removed -- and named here rather than left for you to infer
    from a cell.
  - **Where it reaches**, which is the products and not every line of CSV the
    package writes: the polars, the super file, the sections, the probes, the
    campaign reduction table, the point series and the settings table. The two
    `reductions` writers and the run stage's probe-positions file render their
    own rows and are unchanged.
  - **What you will see.** A steady polar row's advance ratio, which has no `J`
    to state, goes from `...,0.00000,,-2.00000,...` to
    `...,0.00000,NA,-2.00000,...`. A rotorless series row's `azimuth_deg` and
    a probe row's `FRAME` change the same way.
  - **WHAT TO CHANGE IN YOUR READER, and for one whole class of reader the
    answer is NOTHING.** Measured on pandas 3.0.5 rather than asserted: both
    `''` and `'NA'` are default missing tokens, for EVERY column and not only
    numeric ones, so `read_csv` returned `NaN` for these cells before and
    returns `NaN` for them now. **A pandas reader sees no change at all.**
  - **IF YOU PARSE BY HAND, it does change**, and that is who this entry is
    for. The `csv` module gives `""` for an empty cell and now gives `"NA"`,
    so a reader that tested `cell == ""` must test for `NA`. A reader that
    called `float(cell)` is unaffected in the sense that matters: `float("")`
    raised before and `float("NA")` raises now, so code that was already
    correct about the failure stays correct.
  - If `NA` is meaningful data in your own columns, pass
    `keep_default_na=False` and name your own `na_values`.
  - The constant is public as `pyflightstream.post.products.NOT_APPLICABLE`,
    so a reader written against this package can compare to it by name rather
    than by a literal.
  - **ONE TOKEN, NOT TWO: the probes table's `STEP` said `-` on a steady row
    and now says `NA` too.** A steady probes row read `FRAME=NA` beside
    `STEP=-`, two spellings for one meaning in one row, because `-` is
    non-blank and passed the funnel untouched. The owner's rule settles it --
    *when it does not apply, always `NA`* -- so `-` is gone from the products
    and every spine cell the package cannot fill now reads `NA`, including the
    position and frame columns of a run recorded before 0.16.0, which were
    blank. A reader keying on `-` must change; one keying on `NA` already
    covers both.

- **Every product carries the whole flight condition and the reference
  lengths.** The sections, probes and reduction tables carried no reference
  length at all, and the polar carried no `VINF` or `ALT`. These are NEW
  COLUMNS: a reader that selects by name is unaffected, one that assumes a
  column count is not.

- **`_sections` carries `ITERATION` and `AZIMUTH` instead of `POINT`.** `POINT`
  held the polar's name, which the file name already carries, while the two
  things that vary down the table were absent. `AZIMUTH` is `NA` without a
  rotor and never `0`, which is a real azimuth.

- **`per_blade` is ONE window**, shared by every blade, taken from the averaging
  window the matrix row states. It averaged each blade over its OWN passage
  before, which mixed a real azimuthal difference with a difference in WHEN each
  blade was sampled, and nothing in the file said which was which.

  **ONE ROW PER BLADE, WITH THE AZIMUTHS IN COLUMNS, IS 0.24.0** and this entry
  claimed it. `per_blade_rows` holds that shape and has no caller, so the table
  still carries one row per window -- which, with a shared window, is one row.
  The migration page said so correctly and this page did not; the architect and
  V&V lenses of the closing round found the two disagreeing.

- **The POLAR of an unsteady point is the plots HISTORY, time-averaged over the
  window the row states**, and no longer the single row the native coefficient
  export leaves behind. The table, its name and its columns are under *Added*
  below. A row that states no averaging window (`LAST_REVS_AVG` or
  `LAST_ITERS_AVG`) has no window to average over, and its polar is still read
  from the native export.

  **WHAT JUDGES AN UNSTEADY POINT DID NOT CHANGE, and this entry said it had.**
  Until it was corrected on 2026-09-18 this bullet said the run assessor judges
  an unsteady point from the plots history and that a history holding no step is
  unjudgeable. Neither is true of 0.23.0: `assess_unsteady_from_plots` exists, is
  tested, and is called by nothing on the run or collect path. An unsteady point
  is judged exactly as in 0.22.0, by the standard loads assessor, from the
  collected loads table and the solver log where one was exported. The same
  bullet also said THE POLAR STILL READS THE NATIVE EXPORT, which contradicted
  *Added*; what *Added* says is what shipped.

### Changed

- **The `broken_commands` manifest key is promised for removal at 0.24.0**, its
  NINTH deadline, and the extension is deliberate rather than a slip. The tree
  moved to `0.23.0.dev0` and the promise fell due at that bump; the guard said
  so and this is the answer to it.
  - **RE-MEASURED at the bump, not carried.** Counting rows at this bump:
    **74 rows across 4 manifests**, and the manifests are named in full because
    a bare file name would send a reader to their own workspace instead --
    46 in `tests/tier3_licensed/runs.json`, 18 in
    `tests/tier3_licensed/post/matriz/plan.json`, 8 in `matriz_time` and 2 in
    `matriz_builds`. That reproduces the figure taken at 0.22.0, so the
    conclusion stands on a measurement made twice rather than one carried.
  - **The counter is committed: `scripts/count_manifest_key_rows.py`**, which
    takes `--root` so it can be pointed at a workspace, reports the files it
    could not read instead of dropping them, and says when its total is a
    floor. The QA lens of this range could not check the figure at all, and a
    number only its author can reproduce is not a measurement.
  - **IT WILL NOT PRINT 74 IN A CLEAN CHECKOUT, and that is not a defect in
    the counter.** All four manifests are gitignored (`.gitignore:116` and
    `:118`), so a reviewer who clones this repository and runs the script gets
    `0 row(s)`. To reproduce the figure you need a tree where tier-3 has been
    run, or your own workspace passed with `--root`. The first writing of this
    entry carried the counting code inline and did NOT say this, which would
    have had a reviewer run it, see zero, and have no reason to suspect
    anything was missing.
  - **AND THE USER POPULATION IS MEASURED TOO, which is what makes the
    conclusion stand.** Those 74 are all in this repository and a fixture is
    regenerable, so they never carried the argument on their own. Counted at
    this bump over the recorded research workspaces: **43 further rows across
    15 manifests** (`pfs0100`, `pfs0101`, `pfs0110`, `pfs0120`, `pfs040`,
    `pfs090`), each a plan or runs manifest of a campaign that actually ran.
  - **117 rows across 19 manifests in total**, and the 43 are the half nothing
    can regenerate: removing the shim would make a user's own records
    unreadable by the package that wrote them. Write `waived_commands` in
    anything new.
  - The figure this promise carried BEFORE 0.22.0 -- "UNCHANGED at 18 rows
    across 6 live manifests" -- did not reproduce and was corrected then. It
    was stated at EVERY extension from the third to the seventh, five readings
    and not the "two" this entry claimed until the closing round of FIX-0230
    counted them, and neither tree produces it today. What was counted to get
    18 and 6 is not recoverable, and the entry no longer guesses: a promise
    whose subject is a number asserted without measurement must not explain it
    with another one.


### Added

- **A rotor table per rotor**, carrying `J`, `CT`, `CQ`, `CP`, `ETA` and
  `ETAW`, each column suffixed with the rotor's alias. These make physical
  sense for ONE rotor and not for several summed: the diameters and speeds that
  normalise them are different numbers.

  **ON A STATIC POINT EVERY ONE OF THESE READS `NA` EXCEPT `J`**, and not only
  `ETA` and `ETAW` as this entry first said. The reason is the export, not the
  package: it states DIMENSIONLESS coefficients normalised by the run's own
  dynamic pressure, which is zero at rest, so a hovering rotor's real thrust has
  been divided away before any of this is computed. No rotor coefficient is
  recoverable from a static point whatever the package does, which is also why a
  figure of merit cannot be offered here -- it needs a force the run does not
  state. `J` is a real `0.00000`: at rest with a turning rotor it is genuinely
  zero. A figure of merit is the static measure and the user defines it.
- **`ETAW` IS A DIFFERENT NUMBER, by the owner's correction of 2026-09-18.** It
  was `ETA * cos(theta)`, the thrust projected on the free stream by the cosine
  of the shaft angle. It is now built on the rotor's WIND-AXIS FORCE: the whole
  force vector carried from the rotor frame to body axes by the transpose of the
  rotor-to-body rotation, then to wind axes by the AIAA rotation with alpha AND
  beta, taking `Fx_W`; `ETAW = J * CTW / CP` with `CTW = Fx_W / (rho n^2 D^4)`.

  **A cosine is a scalar where the physics is a vector.** It keeps only the force
  lying along the shaft and discards every component an installed rotor produces
  off it, which is exactly the part the rotation chain preserves. The two agree
  only when the shaft is already aligned with the stream -- the case that needed
  no correction -- which is why no test in this suite caught the change until one
  was written with a rotor pushing off its own shaft.

  `ETAW` still reduces to `ETA` for an aligned rotor, and a caller that states no
  wind-axis force now reads `NA` rather than the superseded number.
- **The rotor table names its alias on its first line, alone**, so a script
  that has already loaded the file still knows which group it holds.
- **A rotor carries its INSTALLATION VECTOR.** `axis` accepts three components
  as well as a letter, for a mesh that arrives with its pitch and toe already
  in it. A letter keeps its exact meaning and takes the same code path, so
  every existing reference emits the same script. The blade datum is now
  refused by ANGLE rather than by comparing two strings.
- **An integration group for every rotor the reference declares**, created from
  that rotor's own families when the pproc declares none, as a normal group. A
  declared group under a rotor's alias whose families are not that rotor's is
  refused at plan time, naming both sets.
- **A preset selects the AXIAL FLOW SEPARATION boundaries by family**,
  `axial_separation_families`, resolved against the opened geometry by the same
  rule and the same function as `vorticity_drag_families`: a family the geometry
  does not carry is left out, and a list that resolves to nothing is refused
  naming what it could not find.

  **THE KEYWORD, THE COMMAND AND THE SETTINGS TABLE ALL EXISTED ALREADY.** What
  did not exist was a path from a preset to any of them: the campaign's call into
  `solver_settings` is a hand-written argument list and it never named this one,
  so `SET_AXIAL_SEPARATION_BOUNDARIES` was unreachable from a workspace. Found by
  grepping for the CALLER rather than the definition, which is this release's own
  rule applied one level below the products.

  It is documented to 26.100 and no further -- RPT-018 measured it reported
  deprecated and then refused by the 26.101 and 26.121 solvers -- so a row naming
  it on a later build is refused at PLAN time, naming the build. That costs an
  edit; a line emitted into a script the solver rejects costs a run.
- **The operator in the provenance**, as a `prov:Person` agent, resolved by one
  standard-library call that answers on Windows and on the cluster alike.
- **THE UNSTEADY POLAR COMES FROM THE PLOTS**, time-averaged over the window the
  row states, one table per simulation and one row per point:
  `polars/<sim>_<sweep>_unsteady.csv`.

  **Its columns are the plot variables under the names the export prints them.**
  It does NOT carry the steady polar's twenty-four fixed coefficients. Nothing
  here knows which plot label carries which of them, and a label invented by the
  package would not fail loudly -- it would write `NA` down a whole column.

  **The premise is the owner's answer of 2026-09-18, not a measurement**, and it
  is attributed here because this is the page a user reads: asked whether the
  native coefficient export writes the time average or the last time step, she
  answered the LAST TIME STEP. On an oscillating rotor that is one instant of a
  cycle, so a polar read from it is a polar of an instant that looks exactly like
  a polar of an average. This repository previously asserted BOTH readings, in
  two files, with no manual citation and no characterised export for either; the
  contradiction and its evidence are recorded in `QUESTION-0230`. The native
  export still ships, as a health check.

  **OWED, and named rather than left to be discovered:** the plots parser's only
  fixture states in its own header that it is SYNTHETIC -- written by hand from a
  paraphrase of one manual sentence, with its delimiter assumed and not observed
  -- and that "a real export is owed before this parser may be called verified".
  This release builds a published product on that parser. **The group polars are not written for an unsteady point**,
  because writing both would put two files with one name's worth of meaning in
  one folder.

- **ONE AVERAGING WINDOW, STATED ON THE MATRIX ROW**: `LAST_REVS_AVG` on an
  `unsteady_rotor` row, which **accepts a float**, and `LAST_ITERS_AVG` on an
  `unsteady` one, both in UPPER CASE because a row's keys are matched on the
  exact spelling. It is the same window the POLAR, the time average and
  `per_blade` all use.

  **It is on the ROW because it converses with the temporal setup** --
  `DELTA_TIME`, `TIME_ITERATIONS` and `RPM` are on that row -- and a window
  stated elsewhere sits apart from the quantities that give it a length.

  **`LAST_REVS_AVG` IS A COUNT OF REVOLUTIONS AND NOT A RANGE OF STEPS**, which
  is what lets one instruction serve a row turning two rotors at two speeds: each
  converts the count with its OWN revolution, so a lifter at 2200 rev/min and a
  pusher at 900 get different spans from the same key, and neither has the
  other's turn imposed on it (FR-68). A window longer than the run is the whole
  run rather than a refusal.

  `WINDOW_STEPS`, `WINDOW_REVOLUTIONS` and `WINDOW_DEGREES` are DEPRECATED, due
  for removal at 0.26.0. They were one idea in another place under another name.
  A row stating none of the new keys keeps the answer it has always had.

- **ITEMS 7, 9, 10 AND 11 ARE NOT IN THIS RELEASE**, by the owner's decisions of
  2026-09-18, and they are listed here because an absence a reader has to
  discover is worse than one they are told:

  - the super file in the fixed-width `legacy_polar` format,
  - the `[phase_locked]` pproc table,
  - the `[equations]` table and its `[glossary]`,
  - the generated `VARIABLES.md` and `WRITING-EQUATIONS.md`.

  **0.23.0 therefore adds NO pproc table at all**, which satisfies the rule those
  items were grouped under -- they rise together or none -- from the side where
  none of them ships. A pproc written for 0.22.0 binds unchanged, and the three
  keys are REFUSED BY NAME rather than accepted and ignored. Accepting a table
  the release does not implement would let a user write it and get nothing back;
  a refusal says the feature is not here.

  **The `phase_locked` REDUCTION is untouched** and every workspace that produces
  one still does. What waits is the table that would let a pproc gate it, and the
  azimuthal shape: the mean at each azimuth across several revolutions, which the
  current reduction does not compute.

### Fixed

- `check_release_published.py <tag>` answered "TAGGED BUT NOT RELEASED: no
  release object" for a tag the checkout does not carry at all. The verdict was
  right by accident and the reason was false, sending a reader to look for a
  missing release object on a tag nobody ever cut. An absent tag now reads NOT
  TAGGED.


### Owed

- **`submitted_by` is `NA` on every run that finished before this release.** It
  is a RUN-time fact, nobody recorded it, and it cannot be recovered. No value
  is invented. It is filled from the next run onward.
- **The installation vector is not validated against a licensed run.** No run
  with pitch and toe exists yet. What is proved offline is that the letter path
  is unchanged and that a vector spelling of a letter emits the same script;
  whether the frames a TILTED shaft produces match the hardware is owed to one
  licensed run at a known pitch.
- **`ETAW`: nothing is owed on its definition, and this bullet said there was.**
  Until it was corrected on 2026-09-18 it described `ETAW` as the thrust
  component along the free stream, awaiting confirmation. That is the form this
  release SUPERSEDED: what shipped is the wind-axis force form under *Added*,
  `ETAW = J * CTW / CP`, and a caller that states no wind-axis force reads `NA`.
  The definition is `docs/post-processing-definitions.md`. A defect in the
  free-stream vector that form shipped with is recorded under the release that
  fixes it.


## [0.22.0] - 2026-09-17

### Changed (breaking)

- **A row's `RPM` is a MAGNITUDE, and the hand of the rotation comes from the
  reference.** A matrix row stating a negative rev/min is refused by name; write
  the speed positive and set `rpm_sign` on the rotor block of the reference,
  beside the axis, the origin and the blade count it already declares. The row
  says how fast and the block says which way, so the two cannot contradict each
  other, and a row restating `RPM_SIGN` beside a rotor the reference declares is
  refused whether it agrees with the block or not: a row that agrees today says
  nothing when the reference is corrected tomorrow, which is the same silence
  this entry exists to end. The hand has one home.
  - **The FLAT pre-0.15.0 spelling keeps its own `RPM_SIGN`, with one
    exception.** A row stating `ROTOR_AXIS` and `MOVING_BOUNDARIES` rather than
    naming a rotor block has nowhere else to put the hand, so `RPM_SIGN` beside
    `RPM` is the correct and only spelling there, and it plans as it always did.
    THE EXCEPTION: if the boundary that row turns is one of a DECLARED rotor
    block's own families, that block is the rotor, it governs the hand, and the
    row restating `RPM_SIGN` is refused. A flat row whose reference declares no
    rotor at all is the shape that is genuinely untouched. Until 0.21.1
    that pair was refused outright, on the reading that a rev/min a user writes
    carries its own sign; with the speed a magnitude everywhere, the pair is no
    longer a contradiction.
  - **THIS FIXES A WRONG-WAY ROTATION THAT NOTHING REPORTED.** Until 0.21.1 the
    reference's hand was copied into the case ONLY when the row stated no speed
    of its own, so a row stating `RPM` turned whichever way its number happened
    to be written and the reference's `rpm_sign` was dropped in silence: no
    refusal, no warning, and a rotor turning backwards converges and reports
    numbers. The same rotor stating `ADVANCE_RATIO` turned correctly, because
    the hand was read on that path only.
  - The sign is now applied to BOTH speed forms, the stated rev/min and the one
    derived from an advance ratio.
  - **THE HAND REACHES THE ROW HOWEVER THE ROW NAMES ITS ROTOR**, which took
    three tries and two of them were this same defect wearing another row
    shape. A row may cite its rotor in a `MOTIONS` record, in its own
    `MOVING_BC_ALIAS` cell, or -- on the pre-0.15.0 spelling -- through the
    boundary it turns. The first writing filled the hand at ONE seam, the view
    built per RECORD, so the other two still emitted a positive rev/min against
    a block declaring `-1`, silently. Both were measured emitting `+800` where
    the reference said `-800`, and both are closed. One resolution serves all
    three.
  - **The point NAME writes `RPM` in magnitude**, so a folder is `RPM00473`
    whichever way the rotor turns. The hand is a property of the ROTOR and not
    of the point; naming it in the point would give one operating point two
    identities.
  - A row that wrote its hand into the number (`RPM: -2400`) must move it to the
    reference. That spelling is now refused -- in a SWEEP too, where absorbing
    the sign silently gave `600, -600` two identical point names, so the user
    met a file-name collision instead of the sentence saying where the hand
    belongs.
  - **A workspace whose rotor already ran the wrong way needs a RE-RUN, not a
    rename.** See [Migrating to 0.22.0](docs/migrating-to-0.22.0.md): renaming
    files a wrong-direction result under the corrected point's identity, and
    `--force-rerun` is the command for redoing the points whose sign was wrong
    while leaving the rest alone.

### Added

- **`CampaignWorkspace.supersede_records(run_ids)`** is public: it copies the
  manifest to `archive/runs-<stamp>.json`, removes the named rows and writes the
  result atomically. `--force-rerun` is its one caller.

- **`pyfs-matrix run --force-rerun <point>`**, for a matrix row that was wrong.
  A point whose `run_id` is already in the manifest is refused, because
  re-running a recorded point would fork the run identity, and `--resume` SKIPS
  such a point rather than re-running it. So when the correction does not change
  the point's NAME -- a pproc, a geometry, a solver variable, a wall clock -- the
  corrected point had the same identity and there was no way to redo it inside
  the package at all.
  - **NOTHING IS DELETED.** The manifest is copied whole to
    `archive/runs-<stamp>.json`, the named records leave it, and each point's
    collected outputs move into that point's own `archive/<stamp>/`. The run
    that was wrong stays readable, which is the point: the row that produced it
    is what somebody may need to look at.
  - **IT NAMES POINTS AND IS NOT A SWITCH.** Give it a point name, a full
    `run_id`, or the job id of a swept row (a swept steady row is ONE job, so
    naming it names every point of the row); repeat the flag for several. A name
    no recorded point carries is refused rather than passed over. Redoing a
    whole matrix because one row was wrong would spend a licensed seat per
    point, and a seat is the one thing archiving cannot give back.
  - Points it does NOT name and that are already recorded are skipped, so the
    flag works on a matrix with more than one row. It is refused together with
    `--resume`, which skips a recorded point instead of redoing it.
  - A point of a row stating `RESTART` is CONTINUED rather than superseded, and
    naming one warns rather than passing over the flag.
  - The library takes the same keyword: `run_campaign(..., force_rerun=[...])`
    and `run_matrix(..., force_rerun=[...])`.

### Changed

- **The refusal of an already-recorded point names `--force-rerun` first**, and
  says in the word that `--resume` SKIPS such a point and does not re-run it.
  The earlier text offered `resume=True` inside a sentence about re-running, so
  a user who followed it got a call that returned successfully having executed
  nothing, which is worse than the refusal.
- **A refusal from `pyfs-matrix run` is printed rather than raised.**
  `WorkspaceError` is neither a `ValueError` nor an `OSError`, and the command
  caught neither it nor `PyflightstreamError`, so every workspace refusal it
  writes -- the already-recorded point among them -- reached the user as a
  Python traceback with the sentence at the bottom of it.

- **A refused motion no longer reads as an ABSENT one.** A row naming its
  `CLOCK_MOTION` whose clock rotor was refused for some other reason was told
  "no motion of this row moves it", naming a rotor the row plainly states, which
  sends the user to the one key that was right. The refusal now says which
  motions were refused and why. Reachable on a correct row from this release,
  because a hand written into a speed is now a refusal.
- **The `broken_commands` manifest key is promised for removal at 0.23.0**, its
  eighth deadline. RE-MEASURED at the bump, by counting ROWS rather than files:
  74 recorded rows carry it across four manifests. **The figure this promise
  carried before does not reproduce**: it said "UNCHANGED at 18 rows across 6
  live manifests" at two successive extensions, and 18 is the row count of ONE
  of the four files while 6 is what a grep returns when an index and a search
  blob are counted as manifests. The conclusion is unchanged and stronger:
  recorded rows still need the reader. Write `waived_commands`.

## [0.21.1] - 2026-09-16

### Fixed

- **A 0.20.x workspace holding SUBMITTED points could not be migrated by either
  command.** `pyfs-matrix rename` refuses a submitted record whose folder would
  move and says to collect it first; `pyfs-matrix collect` refused a record
  carrying no point name and said to rename first. Each pointed at the other,
  so a workspace whose points had been submitted -- and had finished, with every
  export on disk -- could not be moved to the 0.21.0 names at all.
  - **THE COST WAS NOT A REFUSAL.** The refusal is caught by the collecting
    sweep and the record rewritten as `FAILED_INCOMPLETE_OUTPUT`, so runs that
    had converged were stamped failed and lost the `SUBMITTED` state that is
    what lets them be collected. Back up `runs.json` before collecting a
    workspace this happened to.
  - `collect` now files such a record's outputs in the datapoint folder the
    record's OWN submission block names, read and never recomputed, which is
    what the refusal existed to protect. A record naming neither a point name
    nor a datapoint folder is still refused: that is a point submitted before
    0.18.1, whose job ran in the simulation folder, and the refusal now names
    the field to set.
  - The `[0.21.0]` section below says "`collect` and `products` refuse a record
    written without them". The products stage still does; `collect` does not,
    as of this release.
- **One bad folder name no longer aborts the whole collecting sweep.** A
  datapoint folder whose name is not a portable point name -- a space in it is
  enough -- raised an error the sweep does not catch, so every OTHER submitted
  point in the workspace went uncollected. `workspace.naming.datapoint_name_of`
  reads a folder name back into a checked `PointName` and answers None for
  anything it cannot check, so the collector refuses in its own vocabulary.

## [0.21.0] - 2026-09-16

### Changed (breaking)

- **The `WALLTIME` column carries its unit**: `240m`, `4h`, `90s`, `1d`. A bare
  number is refused by name. It read as SECONDS in this package and as minutes
  on the scheduler it was written for, and a wall clock that means two things
  is a job that dies early or holds a node for a day.
  - What the DESCRIPTOR carries is the HPC profile's to say:
    `walltime_arithmetic = "wall"`, the default, puts the cell in as written,
    and `"seconds"` puts the whole clock in integer seconds, which is what this
    package wrote until 0.20.x. An arithmetic this package does not implement
    is refused by name. Neither moves the Python clock's deadline.
  - The descriptor also gets `{walltime_s}` and `{walltime_written}`, so a
    profile can ask for either by name.

- **A point is named by its flight condition.** The name writes every variable
  the row's `FLIGHT_CONDITION` cell declares, in the order written, each as a
  code and a fixed-width integer: `M144RE438AL+000BE+000J+080`. The code table is
  in [How a point is named](docs/workspace-and-workflows.md#how-a-point-is-named).
  One name does every job: it ends the `run_id`, names the datapoint folder
  `DP-<name>`, and is the stem of every file, `P<sim>-<name>`. The superfile is
  `SUPER-<sim>-<name>`, with the swept field written `<code>+sweep`, for example
  `J+sweep`. Until 0.20.x the `run_id` and the folder ended in the tag
  `a+00.0_b+00.0_j+00.8`, and the files were named `POLAR-<sim>_M14AL+000BE+000J+080`.
  Under that tag J 0.80 and 0.84 shared a folder; under the new name they get
  two. The run record gains `point_name` and `sweep_name`. `collect` and
  `products` refuse a record written without them, and point to the renaming
  command.
  - `{point}` in a naming template is now the point name, and `{polar}` is
    `P<sim>-<name>`. `pyflightstream.cases.point_name` and `sweep_name` compute
    them, `POINT_NAME_FIELDS` is the code table they write from, and
    `point_tag` still returns the 0.20 tag. A template of your own still
    renders and produces different names WITHOUT a message, which is the one
    change in this release that does not refuse: check your `--point-name`
    before the first run.
  - `CampaignWorkspace.collect_outputs` and `archive_datapoint` take a
    `workspace.PointName` and no longer take a point mapping.
  - [Migrating to 0.21.0](docs/migrating-to-0.21.0.md) is the step-by-step
    for a workspace, a matrix and a profile written under 0.20.x.

### Added

- **The HPC profile's `[log]` table**, for a machine that aborts at
  `EXPORT_LOG` and writes its own log beside the run.
  - `export_log = false` leaves `EXPORT_LOG` out of the script.
  - `native_log = "FTS{sim}.l*"` names the file the scheduler writes, and
    `collect` copies it to the name the row declared, so everything downstream
    reads one log.
  - `export_log = false` with no `native_log` is refused: it asks for a run
    with no log at all, and an unsteady run cannot be judged without one.
  - Several files matching `native_log` are refused by name.
  - **`EXPORT_LOG` in a cell reads a yes-or-no word through one reader**, so
    a word this package does not know is refused by name rather than read as
    the permissive side. `disable`, which the earlier reader accepted as
    false, is no longer among them: write `false`, `no` or `0`.
  - **The profile's keys are a CLOSED set now**, at the top level
    (`application_id`, `descriptor`, `submit`, `defaults`, `builds`,
    `walltime_arithmetic`, `log`) and inside `[log]` (`export_log`,
    `native_log`). A key outside either is refused by name rather than
    ignored. A profile carrying a note of your own, or a misspelt key, stops
    at the refusal instead of reaching the cluster and aborting the job at
    `EXPORT_LOG`, which is the failure the table exists to prevent.
- **A collected point's record carries what its log said**: the iteration it
  reached, the residual, the times the solver printed, and which file they were
  read from. The cluster path judged the point by the log and then kept only
  the verdict, and on a cluster the log is the whole of the evidence.
- **A rotating free stream, stated as a body rate.** A row states one of
  `roll_rate`, `pitch_rate` or `yaw_rate` in deg/s, in flight-mechanics signs,
  and the script writes `SET_FREESTREAM ROTATION` about the moment reference
  point of the row's `REF` instead of `CONSTANT`: it is how a run states a
  pull-up, a roll or a yaw rather than straight flight. The rate sweeps like
  any other variable of the cell.
  - Which axis of the model each rate turns about is the CONFIGURATION's to
    state: the reference artifact declares `[body_axes]` (`roll`, `pitch`,
    `yaw` against `X`, `Y` or `Z`), and a row stating a rate against a
    reference that declares none is refused by name.
  - Two non-zero rates in one row are refused by name: the free stream turns
    about one axis at one speed.
  - Every rate zero, or no rate at all, writes `CONSTANT`, so a row written
    before this release renders exactly what it rendered before.
  - WHAT THE SOLVER DOES WITH A POSITIVE ANGULAR VELOCITY is not stated by any
    edition of the manual, so it was MEASURED: three pitch rates on one
    wing-body on 26.124, reported in
    `reports/RPT-052_the-sense-of-a-rotating-free-stream_2026-09-15.md`. A
    positive rate came back with the nose-down moment increment that opposes a
    nose-up rotation, so the sign stands as written; it is one named constant,
    `cases.workflows.FREESTREAM_ROTATION_SIGN`.
- **`RPM` is a `FLIGHT_CONDITION` variable**, stated once for the row and
  reaching every motion that states no speed of its own, exactly as
  `ADVANCE_RATIO` does. It can be swept, which is what a rotor study varies;
  until 0.20.x the speed could only be written on a motion record, where it
  cannot be swept and where every motion needs its own copy.
  - A `MOTIONS` record naming a speed still wins over it.
  - `RPM` with `ADVANCE_RATIO` and a velocity (`MACH` or `TASmps`) is refused
    by name: the three are one relation, V = J x (RPM/60) x D.
  - `RPM` with `ADVANCE_RATIO` and no velocity COMPUTES the velocity from them,
    with D the diameter of the rotor `CLOCK_MOTION` names; a row naming no such
    rotor is refused by name.
  - The flat `RPM` of `VAR_NAMES_VALUES` is unchanged: it is one rotor's speed,
    it does not reach a motion record, and a row whose records resolve to a
    speed still names its `CLOCK_MOTION`.
- **Every `FLIGHT_CONDITION` variable can be swept** (FR-69, the rule
  implemented). Until 0.20.x a row could vary `ALPHA`, `BETA` and
  `ADVANCE_RATIO`, and a row sweeping any other key was refused naming those
  three. A row may now write `sweep` against `MACH`, `TASmps`, `REmi`,
  `ALTFT`, `dISA` or any of the five pins, with its values in `SWEEP_VALUES`
  as before; a key that does not define the condition is still refused.
  - A swept FLOW variable is resolved per point: each point carries its own
    density, velocity and Mach number (`SimCase.point_states`, applied by
    `cases.case_at_point`), and the point's name carries the swept field.
  - Such a row is ONE JOB PER POINT rather than one warm job, because the air
    state is a setup command the solver takes before it is initialised. A row
    that sweeps an attitude is the warm job it was.
- **`pyfs-matrix rename --workspace <root>`**, the one command that moves a
  workspace written under 0.20.x to the new names. It reads the matrices beside
  `runs.json`, works out each record's new name from its row and its recorded
  point, and moves the datapoint folders, the scripts, the collected files, the
  manifest and the plan; the manifest it replaces is archived first. It prints
  every change, `--dry-run` rehearses it, and a second run changes nothing.
  Before touching anything it refuses, by name, a record whose row is gone, a
  record whose point the matrix no longer holds, two points that would share a
  name, and a SUBMITTED record whose folder would move: collect that one first.
- **`plan` and `run` take `--accept-unregistered-build`.** On a workstation,
  the pre-flight refuses an installed build other than the one registered for
  the version a row names. With the flag the run proceeds and warns, its
  compatibility is your responsibility, and every run record carries
  `accept_unregistered_build` beside the build the solver printed (`fs_build`).
  `plan` launches no solver and records the flag in `plan.json`. Without the
  flag the refusal stands and now names it. The library takes the same keyword
  (`run_campaign`, `run_matrix`, `plan_campaign`, `plan_matrix`,
  `check_solver_identity`).
- **The run record carries the times the solver log prints**:
  `solver_run_time_s` (the last `Solver run time` or `Unsteady solver run time`
  line), `solver_initialization_s` and, on an unsteady run, `time_steps`. The
  superfile carries them as columns. `results.parse_log_times` reads them, and a
  field the log does not print is None, never zero.

### Fixed

- **`collect` names each declared output that has not arrived**, not only how
  many: "1 of 8 declared output(s) not there yet: <point>_log.txt".

- **A final residual the solver printed as a field of asterisks no longer reads
  as a divergence.** The solver prints a run of asterisks when a number does not
  fit its column. On the last iteration that turned a converged run into
  `FAILED_DIVERGED` ("pressure=nan"). The column is now read from its last
  printed value when that value is already within the convergence limit, and
  the run record's new `residual_note` says which column, which iteration and
  what value. A column that overflowed from above the limit, and a NaN the
  solver printed, are still divergences.
  - `ResidualSample` gains `overflowed`, the columns printed as asterisks on
    that row.
- **A section distribution plans on the builds before 26.120.** Those builds'
  `NEW_SURFACE_SECTION_DISTRIBUTION` takes no `INCLUDE_SYMMETRY`, and the
  package wrote `INCLUDE_SYMMETRY DISABLE` anyway, so every pproc with sections
  was refused there. The switch is now written only on a build that takes it;
  on the others a pproc with `include_symmetry = false` writes none, and one
  with `include_symmetry = true` is refused by name. What 26.120 and later
  render is unchanged.

### Changed

- **The `broken_commands` manifest key is promised for removal at 0.22.0**, its
  seventh deadline, on the same re-count as the six before it: re-measured the
  moment the 0.21.0 cycle opened and UNCHANGED at 18 recorded rows across 6
  manifests. The reader stays while a recorded row needs it; write
  `waived_commands`.

## [0.20.1] - 2026-09-15

### Limits

- **The 26.100 rotor's unit is a maintainer decision, not a measurement.**
  `SET_MOTION_ANGULAR_VELOCITY` is written in rev/min there. That build's
  manual tutorial gives rad/s for the same field, and 26.000 measured rad/s
  (RPT-049). If 26.100 also reads rad/s, the rotor turns about 9.55 times
  faster than the row states (RPT-051).
- **The 26.100 rotor carries no rotor mark**, so the solver is never told the
  motion is a rotor. The effect of that on the solution is not measured.
- **No solver run in this repository has used the 26.100 rotor motion.** Its
  sense of rotation is not measured, and neither is whether the unmarked
  motion turns the blade at all.
- **Three cells of the support matrix are refused**, every run type on 25.000.
  Every other limit of [0.20.0] still holds; its fourth refused cell, the
  26.100 rotor, is the one this release fills.

### Fixed

- **`unsteady_rotor` runs on 26.100 instead of being refused.** 26.100
  documents the Euclidean angular velocity (SRC-741 p.329) and does not
  recognize the rotor mark (RPT-049). The rotor is now written there as a `EUCLIDEAN` motion whose
  `SET_MOTION_ANGULAR_VELOCITY` is the row's speed in rev/min along its axis,
  with no `SET_MOTION_IS_ROTOR`.
  - A comment above the motion says, in the script itself, that the rotor is
    unmarked, that the unit and sense are not measured, and what a rad/s
    reading would do.
  - `script.rotor_vocabulary` gains `unmarked_euclidean_rotor`,
    `UNMARKED_EUCLIDEAN_ROTOR_COMMANDS` and `UNMARKED_EUCLIDEAN_ROTOR_UNIT`.
    Coverage and `helpers.rotary_motion` read the predicate, so the choice is
    made in one place, and the helper converts each Euclidean speed by its
    unit constant, so a constant and the value written cannot disagree.
  - A stabilization blade count and an axis given by index are refused on
    26.100 by name, as on 25.100 and 26.000 (RPT-051).

## [0.20.0] - 2026-09-15

### Limits

- **What each build runs is in the per-build table of
  `docs/workspace-and-workflows.md`, and four cells are refused:** every run
  type on 25.000, whose `INITIALIZE_SOLVER` takes five settings no later
  edition exposes and none gives a default for, and `unsteady_rotor` on
  26.100, which has no scripted rotor mark (RPT-049).
- **The table is about the run types.** A solver preset or a post-processing
  artifact can name a command an older build lacks (stabilization before
  26.101, wake-on-wake induction and additional wake relaxation before
  26.100, a section distribution's `INCLUDE_SYMMETRY` before 26.120); such a
  point is BLOCKED at plan time naming the command, and nothing substitutes it.
- **A build without unsteady solver actions offers no snapshot threshold, no
  in-run wall clock and no continuation from their records.** Rows asking for
  them are refused on those builds, never run without them.
- **The Euclidean rotor was run on 26.000 only**; 25.100 rests on its manual
  and that measurement. One axis, one sense and one speed were run, and the
  loads of the two builds were not compared beyond three steps.
- **26.124 carries the 26.123 documentation and a different executable**
  (RPT-050); every workflow renders the same script on both, and nothing in
  this release states whether the two executables compute the same numbers.
- **No row asked for actions in the licensed runs of this release**, so the
  actions march and the single march were not compared on one build.
- **The internal-defect refusal of `build_script`** (a march label that
  disagrees with the actions its script registers) is a `WorkflowCoverageError`,
  so a package bug there reads as a blocked row; a class of its own is owed.
- **Whether the solver's stop verb inside an action's script ends the run or
  only that script** is still unmeasured, carried from 0.18.0.

### Added

- **FlightStream 26.124 is registered, at `operational`.** Vendor build 8172026,
  the fourth hotfix of the 26.12 release, alias `26.12`, read from its own
  banner (`reports/compat/CMP-26124_2026-09-14.yaml`). Its package carries the
  26.123 user guide byte for byte, and the same release notes and libraries;
  only the executable differs (every file's digest, RPT-050). So all 372
  rows 26.123 records (371 documented commands and one removal) were
  carried to 26.124 citing that manual, nothing was inherited from 26.120,
  and a probe run on the build then measured 86 verified and the same single
  broken command, `NEW_OFF_BODY_STREAMLINE`
  (`reports/compat/CMP-26124_2026-09-14_full-sim.yaml`). Every workflow
  renders on 26.124 exactly what it renders on 26.123; the workflow goldens
  for 26.124 are byte-identical to 26.123's. `"26.12"` now names five builds
  and is still refused as ambiguous.
- **Every unsteady row says how it is marched on its build.** The builds
  before 26.122 document no unsteady solver action
  (`SET_NEW_UNSTEADY_SOLVER_ACTION`), so on them an unsteady row runs as a
  single march: its plots declared before one solver start over every time
  step it states, and its exports after it. That was already what a row with
  no threshold and no wall clock rendered on every build; it is now decided in
  one place, `march_strategy(case, *, capabilities)`, and reported.
  `PointPlan.march_strategy` and the run record's `march_strategy` carry
  `"actions"` or `"single_march"` (None for a steady point), a closed set
  named by `pyflightstream.script.MarchStrategy` with `MARCH_ACTIONS` and
  `MARCH_SINGLE`, so a record carrying any other string is refused; the
  superfile carries it as a column. `BuildCapabilities.for_build("26.120")`
  answers for a build named as a matrix cell names it. `build_script` refuses,
  as an internal defect, a script whose registered actions disagree with its
  label.
- **`BuildCapabilityError`**, a `WorkflowCoverageError`, refuses an unsteady row
  that asks a build without actions for what only actions provide: the
  `EXPORT_UNSTEADY_AFTER_ITER` or `EXPORT_UNSTEADY_AFTER_REV` threshold, the
  `WALLTIME` clock, or `RESTART: {FINISH_PENDING}` and `{ADDITIONAL_REVS=n}`.
  The message names the build, each feature asked for, the builds that
  document the actions, and the change to the row that runs on the build
  named. Nothing is emulated: a row the build cannot run as written is
  refused at plan time, before any seat is used, and never rendered with the
  feature silently dropped.
- **A rotor row renders on 25.100 and 26.000.** Those editions name the
  motion type `EUCLIDEAN` and have no rotor axis or speed command, so
  `unsteady_rotor` writes the rotor in their vocabulary: a Euclidean motion
  whose `SET_MOTION_ANGULAR_VELOCITY` is the row's speed in rad/s along its
  axis, and `SET_MOTION_IS_ROTOR` along the same axis. The row is unchanged.
  The unit and the sense were measured on 26.000: a blade driven this way
  turned exactly as the rotary motion at the same speed turns it on 26.120
  (RPT-049, with its evidence under `reports/probes/`). 25.100 was not run;
  there the substitution rests on its manual (SRC-748 pp.306-307), which
  prints the same grammar, and on the 26.000 measurement.
  `helpers.rotary_motion` takes the same arguments on every build and
  refuses, on a Euclidean build, an axis given by index and a wake
  stabilization blade count, neither of which that vocabulary can state,
  naming the builds that take the count.
  `pyflightstream.script.rotor_vocabulary.euclidean_rotor(view)`, in a new
  public module beside the rotor command tuples, is the one decision both the
  helper and the workflow coverage read; it chooses the vocabulary and does not
  say a build runs a rotor.

### Changed

- **`unsteady_rotor` on 26.100 is still refused, now for a measured reason.**
  Its manual prints `SET_MOTION_IS_ROTOR` and its solver answers the name as
  an unrecognized command, the answer it gives a name no build has, in every
  form tried; the command is recorded as removed on 26.100 (RPT-049), and the
  refusal names the half of the Euclidean rotor the build carries and the half
  it does not.
- **The `broken_commands` manifest key is promised for removal at 0.21.0**, its
  sixth deadline, on the same re-count as the five before it: re-measured the
  moment the 0.20.0 cycle opened and UNCHANGED at 18 recorded rows across 6
  manifests. The reader stays while a recorded row needs it; write
  `waived_commands`.

### Fixed

- **`CREATE_NEW_MOTION` on 25.100 and 26.000 takes `EUCLIDEAN`, as their pages
  say.** Both rows were recorded as "same grammar as 26.120", which put the
  `ROTARY` type in two editions that never name it (SRC-748 p.306, SRC-747
  p.305); re-read from the pages on 2026-09-15.
- **A rebuild archives the series tables it rewrites.** `pyfs-matrix post`
  archived every existing product into `<its folder>/archive/<day and hour>/`
  before writing, except the tables under `series/`, which it rewrote in place:
  the products stage accepted the archive flag and never passed it to the
  series writer. They now go through the same archiver, under the same stamp,
  and `--force-overwrite` still keeps no copy. `write_point_series` gains an
  optional `target` callable, the seam `write_superfiles` already takes: each
  table is written to the path it returns, and when it is given it alone
  decides what becomes of an existing table. BEHAVIOUR CHANGE for a library
  caller: `write_campaign_products` over existing series tables used to raise
  `ProductExistsError` without `overwrite=True`; it now archives them and
  succeeds, as it did for every other product. `write_point_series` called
  without a target still refuses, and its message no longer names a
  command-line flag.
- **The warning a failed products write prints offers a command that runs.**
  It told the user to rebuild with `pyfs-matrix post --workspace <root>
  --overwrite`, a flag `post` has not accepted since 0.17.0. It now offers
  `pyfs-matrix post --workspace <root>`.

## [0.19.0] - 2026-09-14

### Added

- **A matrix row translates an alias the way it rotates one.** `TRANSLATE:
  {DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}, {...}` in the variables
  cell moves the boundaries of one declared alias by `DISTANCE` metres along one
  axis of the named frame, record by record in the order written, on every run
  type that reads `ROTATE`. Every frame the alias owns, every `AUX_FRAMES` entry
  and every frame the package placed from them moves too, once each, to its new
  origin; `<ALIAS>_SMRP_ORIGINAL` is kept once per alias and shared with a
  rotation; every translation is emitted before every rotation. One row is one
  position, so it is not swept. The super file carries a `TRANSLATE` column.
  Each surface moves with `SPLIT_VERTICES ENABLE`, because surfaces of one set
  share the vertices where they meet and a translation without the split moved
  those vertices once per surface (RPT-048, measured on 26.123). A frame moves
  by `SET_COORDINATE_SYSTEM_ORIGIN` to an absolute origin, computed from where
  the script placed it, because the manual does not state the axes of
  `TRANSLATE_COORDINATE_SYSTEM`'s vector (SRC-751 pp.335-336); a frame whose
  placement the script cannot state is refused by name, and a frame's origin
  is read in metres, so a translation is right only on a simulation whose
  length unit is metres. Moving part of a set that touches the rest leaves
  that part no longer joined to it, observed on a saved mesh and not solved.
  From Python: `SimCase.translations`, the read-only `Script.frame_placements`
  and `FramePlacement`. FR-100.

### Changed

- **`TRANSLATE_SURFACE_IN_FRAME` is phase setup**, as the two rotations are, so
  it may cite a frame the setup created. Exercised on 26.123 only (RPT-048).
  BEHAVIOUR CHANGE for a script built by hand: the command now follows the
  frames rather than leading the script, and a geometry-phase command emitted
  after it is refused as out of order.

- **The `broken_commands` manifest key is promised for removal at 0.20.0**, its
  fifth deadline, on the same re-count as the four before it: re-measured the
  moment the 0.19.0 cycle opened and UNCHANGED at 18 recorded rows across 6
  manifests. The reader stays while a recorded row needs it; write
  `waived_commands`.

### Fixed

- **A plot on a rotated hub is written in both frames.** A post-processing entry
  naming a hub frame a row rotated was to be emitted in the turned frame and in
  `<ALIAS>_SMRP_ORIGINAL`, and a rendered script emitted it once: the copy was
  kept in the rotation's own mapping and never reached the post-processing. The
  rotation now returns it to the builder. BEHAVIOUR CHANGE: a row that rotates a
  rotor and plots on its hub gains the second plot, `<name>_ORIGINAL`. FR-71.

## [0.18.1] - 2026-09-14

### Added

- **A swept row submits every point.** On a cluster each submitted point now
  runs in its own datapoint folder, `sims/sim_<id>/datapoints/DP-<tag>/`, which
  is where its outputs are filed. The files a point used to share with every
  other point of its row move with it: the unsteady action program and its
  export script, the wall clock and its state, and the scheduler's descriptor.
  So a second point of a row is no longer refused while the first is queued,
  and `pyfs-matrix collect` waits for each point's outputs in that folder and
  files them in place, including an output declared in a subfolder of it. The
  SAME point is still not submitted again while a job of it is queued, under
  any campaign name, and is refused before any of its files is written. The record's submission block names the folder as
  `working_dir`. A local run is unchanged and still runs in the simulation
  folder, and a steady row, which is one job over all its points, still
  submits one job from the simulation folder. Proved against a submitting
  executor that calls no scheduler and a solver stand-in; not yet run on a
  cluster.
  `CampaignWorkspace.collect_outputs` gains `ran_in_datapoint=True`, which
  accepts a declared output already in its own datapoint folder and records it
  without moving it; without it such a file is still refused, as is a file in
  any other managed folder. The collect stage passes it only for a record whose
  submission names a `working_dir`, and refuses a `working_dir` that is not a
  datapoint folder of the record's own simulation.

- **The HPC profile names a build the way its scheduler does.** A row's
  `FS_BUILD` names one build, `26.123`; a scheduler may accept only an
  application family such as `26.1`, which this package refuses because it
  covers more than one build. A `[builds]` table in `inputs/hpc/h<>.toml` maps
  each canonical build to the scheduler's name, and a descriptor field writes
  it with `{fs_build_alias}`, so the matrix cell stays the same on every
  machine. It is keyed by build because several builds can share one scheduler
  name. A profile that writes the substitution and maps no alias for a build a
  row names is refused before any point is submitted, whether the platform chose
  the submitting executor or a caller passed one; a key that is not one
  registered build is refused when the profile is read. THE TABLE IS A
  DECLARATION: nothing checks that the scheduler starts that build, which only
  the build number in a collected log shows. A profile that does not write the
  substitution is unaffected. This adds a section to a published file format.
  From Python the table is `HpcProfile.builds`, and the substitution's name is
  `pyflightstream.workspace.inputs.HPC_BUILD_ALIAS`.

- **`pyfs-matrix plan --update-ids` renumbers the repeated POLs of the matrix
  being planned** (also accepted as `--updateIDs`). A row keeps its POL unless
  another matrix of the workspace or an earlier row of the same file already
  states it; each row that must move takes the next free number above every
  POL, run record and `sims/sim_<id>` folder of the workspace. Only that
  matrix's POL cells change, each change is printed, and the plan then runs on
  the rewritten file; the renumbering is written first and stays written if the
  plan then refuses, and the command says so. From Python,
  `renumber_repeated_pols` writes only when called with `in_place=True`. Inside one matrix the first row
  stating a POL keeps it and later rows move; a row whose POL another matrix
  also states, and which already has runs of the planned matrix, is refused
  rather than moved, because moving it would orphan those runs. From Python:
  `renumber_repeated_pols`, returning a list of `PolChange`, in
  `pyflightstream.workspace.matrix`, over `renumber_pols` in
  `pyflightstream.cases.matrix`.

### Fixed

- **A probe survey cited from a pproc artifact reaches the solver.** The
  script imported `profiles/<file>` from the simulation folder, where nothing
  had put the file, so the script named a file that was not there. The survey
  is now read where
  it lives, `inputs/profiles/<file>`, by absolute path resolved when the row
  binds, and a name that folder does not hold is refused when the row is
  planned, naming the files it does hold.
  BEHAVIOUR CHANGE: a script built outside a workspace from a case whose
  pproc cites a survey is refused rather than emitting the import, and a pproc
  file may not state `resolved_points_file`, which the package sets.

- **A continuation opens the saved simulation it continues.** It archived the
  stopped run's outputs and then opened the saved simulation at the path it
  had just been moved from. It now opens the archived copy by absolute path.

- **A `RESTART` row runs under the campaign that recorded the stopped run.** It
  was refused as a re-run of a recorded point, and with `resume` it was skipped
  as done, so it ran only under another campaign name. A point of a `RESTART`
  row is now run when its most recent record stopped with more to do, and is
  skipped when its most recent run finished or is still queued; a point whose
  most recent run FAILED is refused by name at plan and at the run's
  pre-flight, never skipped in silence. The continuation reads that most
  recent record, and no longer an earlier stopped one when a later
  continuation has already completed.

- **A repeated POL is found in every matrix of the workspace, on every row.**
  Since 0.13.0 `plan` and `run` refused a POL two matrices shared, and three
  shapes went through: a POL on another matrix's RUN = 0 row, a POL on a RUN = 0
  row of the matrix being planned, and any collision at all when the matrix
  was planned from outside the workspace root. A POL repeated inside one matrix
  was refused only by a validation error that named no row. One message now
  names every repeated POL and every row stating it, and gives a repeat that
  `--update-ids` cannot move a remedy of its own.

- **A point still in a scheduler's queue is no longer counted as a run that
  owed coefficients.** The sweep table decided success by whether the status
  began with `FAILED`, and `SUBMITTED` does not, so every successful cluster
  submission warned that none of its "successful runs" yielded a coefficient
  table. BEHAVIOUR CHANGE: with `require_loads=True`, a workspace whose only
  non-failed records are `SUBMITTED` used to raise `LoadsNotFoundError` and no
  longer does.

- **That complaint's example never renders an empty list.** It took its
  example from the first record, which on a cluster row is often a point with
  no outputs, and read `for example [] for run ...`. It now names a record that
  collected something, or says in words that none did.

- **`pyfs-matrix run` prints that complaint once.** The library leaves the
  sweep table and the command line wrote it again from the same manifest, so
  one invocation emitted every warning of that derivation twice.

- **The per-rotor skip line states its reason once.** For a row that names its
  rotors, the skipped `phase_locked` and `per_blade` entries repeated the
  reason and buried the file names at the end; the clause after the reason now
  names the per-rotor files and nothing else.

- **No message names a released version as a future fix.** A refusal shipped in
  0.18.0 told its reader to wait "until 0.18.0 gives a submitted point its own
  working directory"; a deprecation said a form was exempt "until 0.17.0, when"
  the key became required; another refusal said "0.15.0 has not shipped". Each
  is reworded to state the limitation without dating it, and a tier-1 guard
  reads every user-facing string of the package for a version at or below the
  current release described as still to come.

## [0.18.0] - 2026-09-14

### Corrected

- **The v0.17.0 entry above says twelve deprecations fell due and moved to
  0.18.0. They did not fall due, because they were never promises, and the
  correction is written here rather than by editing that entry.**
  WHAT IT SAID: "Twelve deprecations fell due at 0.17.0 and every one of them
  moves to 0.18.0, on a re-count", with a measurement of 39 files still
  stating one of them and the residual that "the deadline test goes red at
  0.18.0 whatever the count is".
  WHAT IS TRUE, measured on the tree at 0.18.0.dev0: the twelve live in
  `REFUSED_IN_0_15_0`, which is deliberately OUTSIDE the `DEPRECATIONS` tuple
  the tier-1 deadline guard reads, and the module says why in its own words:
  they were written in 0.15.0 before 0.15.0 shipped, so nobody ever had a
  workspace that was told the old spelling would keep working, and there is no
  shim left for the guard to watch expire. **The spellings are REFUSED today
  and have been since 0.15.0.** Exercised on this tree: a row stating
  `RPM_SIGN` beside `RPM` is refused by name with the replacement given. So
  there was never a deadline for the guard to enforce, nothing to remove at
  0.18.0, and the sentence promising the test would go red was describing a
  mechanism that does not watch these entries.
  WHAT THE 39 COUNTED: files whose spellings already do not run. Two counting
  defects inflated it to 39 where the corrected walk reads 17, and the
  corrected script is committed; but the deeper point is that the count was
  never the deadline's input, because the deadline does not exist for these
  entries.
  WHAT REMAINS TRUE OF THAT PARAGRAPH: the remedy it gives a reader is right.
  Write the `MOTIONS` record form and put the aliases and frames on the
  reference artifact. And `broken_commands`, which IS a promise and IS
  watched, is extended on its measurement rather than removed on its date, as
  that entry has always said.

### Added

- **A row may state `RESTART` and the solver continues the march it stopped.**
  v0.17.0 parsed the cell and refused to run it, naming this release. It runs
  now, in all three forms, and the whole design rests on one measured fact
  about the solver: it resumes an unsteady march from a saved file, picks up
  where it stopped, and runs the new number of iterations it is given.
  SO THE STEP COUNT IS A REMAINDER AND NOT A TOTAL. The continuation asks for
  what is LEFT, because the solver has already marched what it marched; a row
  asking for the whole history again would re-run the part that is already on
  disk and call the result a continuation. The time step is the row's own.
  AND IT ARCHIVES WHAT IT REPLACES, into `archive/<day and hour>/` under the
  datapoint's own folder. The stamp is what makes a second continuation
  possible: a point can be continued more than once, so an unstamped archive
  would have the second continuation destroy the first one's evidence. It is
  per datapoint because every point has its own folder even under a warm
  sweep. A continuation's run id is `<campaign>/sim_<id>/r<stamp>/<tag>`,
  so the point tag still ENDS the run id, which is the invariant every existing
  manifest rests on.

- **A tag is not released until somebody releases it, and a script asks.**
  `scripts/check_release_published.py` reads a tag as RELEASED only when the
  release object exists at that tag AND the archive has minted a version DOI
  that `CITATION.cff` records. It has an offline half a clone can run and an
  online half that asks the two services.
  IT EXISTS BECAUSE v0.17.0 WAS ARCHIVED NOWHERE FOR A DAY. The `Release`
  workflow publishes to the package index on a tag; the release object is a
  manual step, the archive webhook fires on that object and not on the tag, and
  no gate saw the gap because every gate this repository had asks its question
  BEFORE the push. It was found by looking at the archive record.

- **The physics cases are compared across builds by a page that generates itself.**
  `reports/physics/LIVING-PHYSICS-ACROSS-BUILDS.md`, written by
  `scripts/build_living_physics.py`, one row per case and one column per build,
  carrying the verdict tally each per-build report already recorded. A tier-1
  test refuses a stale copy through the generator's own `--check`, so a build
  that arrives shows up without anyone remembering to add it, which is the
  whole of what living means here.
  IT BEGINS AT 26.123 AND DOES NOT BACK-FILL.
  The four per-build physics reports and the two drift reports already
  committed stay as the historical record. It does not JUDGE: every verdict is
  the one the per-build report recorded, and a case that never ran on a build
  reads `not run`, which is not a pass.

- **A submitted job's outputs are collected when they land, and then posted.**
  `pyfs-matrix collect` sweeps every `SUBMITTED` record and, for each, waits
  until the outputs that point declared are PRESENT AND SETTLED, then collects
  them, assesses the run and rewrites the record with what it did. One sweep by
  default; `--watch` loops until nothing is outstanding. Until this release a
  `SUBMITTED` record was completed by hand, which is what 0.17.0 said it would
  be (FR-99).
  IT WATCHES THE WORKSPACE AND NOT THE SCHEDULER, which is what keeps it free
  of a second scheduler vocabulary: no status command in the submission
  profile, no job-script template, and the same stage therefore serves a
  cluster job, a local run somebody interrupted, and outputs a colleague
  dropped in by hand.
  SETTLED IS TWO SIGNALS THAT FAIL DIFFERENTLY, because **a file exists before
  it is finished**: size and modification time stable across two observations
  catches a file still being written, and the last declared output present is
  the stronger statement, since every emitted script ends with the log export
  and the close. A stage that fired on appearance alone would post-process a
  half-written loads table and report numbers for it.
  THE DECLARED SET IS RECORDED AT SUBMISSION, in the run record, and is not
  re-read from the matrix at collection: a matrix edited in between is exactly
  the shape that made a recorded flight condition read back as a different
  number in a regenerated product (GEO-039-F02).
  NO NINTH STATUS. The closed set stays at eight; a collection that refuses is
  `FAILED_INCOMPLETE_OUTPUT` with the reason.
  THE PRODUCTS ARE REBUILT ONLY WHERE SOMETHING WAS COLLECTED, because a
  rebuild archives what it replaces and a watch that posted on every sweep
  would fill the archive with copies of an unchanged answer.

- **One method completes a submitted record, and it refuses every other row.**
  `CampaignWorkspace.complete_submitted_record` is the only thing in this
  package that rewrites a manifest row. `append_record` carries existing rows
  across as they were written because historical evidence is not this class's
  to edit; a `SUBMITTED` row is the one deliberate exception, and in a precise
  sense: it is not a finished record a later reading disagrees with, it is a
  record that says in its own status that the run has not come back. Completing
  it is not editing evidence, it is the evidence arriving. The refusal is on
  the EXISTING row rather than on the new one, which is what stops this
  becoming the general-purpose rewrite `append_record` exists to prevent.

### Fixed

- **`pyfs-matrix collect` JUDGES a collected point instead of declaring it converged.**
  The stage recorded every settled point `CONVERGED` whatever the solver had
  done, while its own `--help`, FR-99, this change log and the submitting
  executor's docstring all said it assesses the run. A diverged cluster job, a
  job the scheduler killed after writing its exports, and a clean run were
  recorded identically, and the products were built from that.
  IT NOW USES THE SAME ASSESSOR THE LOCAL PATH USES, so a point run here and a
  point run on a cluster are judged by one rule rather than by two that can
  drift, and `None` is no longer a way to reach the old behaviour.

- **A collected SWEEP files each point's outputs under that point.** The record
  of a swept job carries the first point, so the collector filed every point's
  exports into the first point's datapoint folder. That is the defect the local
  path pays two passes to avoid: an assessor reading a sibling point's file and
  reporting the run against the wrong incidence. The submission now records the
  declared set per point, and the flat union stays as what the collector WAITS
  for, because the job is one job and one script. A completed sweep's per-point
  list is rewritten too, so no point of a converged row still reads SUBMITTED.

- **`collect --watch` over a point submitted before 0.18.0 terminates.** Such a
  record names no declared outputs, so nothing knows what to wait for it; it
  counted as outstanding, and the loop stops only when nothing is outstanding,
  so the watch swept forever. That state is now reported and excluded from the
  stop condition, because it is a terminal answer rather than one a later sweep
  changes. `--rounds` and `--watch-interval` are refused without `--watch`
  instead of being accepted and ignored, and the exit status now distinguishes
  everything-collected from gave-up-still-waiting.

- **A row may not state `RESTART_FROM` or `RESTART_ITERATIONS`.** They are how
  the run path hands a RESOLVED continuation to the builder, and they travelled
  in the same free-variable namespace a user's cell writes into: a row stating
  them built a continuation directly, skipping the resolution that checks a
  recorded run exists, that it stopped in a state a continuation may resume,
  and that its outputs are archived before they are replaced. Refused at plan
  time, naming what to write instead.

- **`RESTART: {FINISH_PENDING}` refuses a record that never said where it
  stopped, instead of re-marching the whole history.** `stopped_at` is written
  by the wall clock, and a run recorded at its ITERATION LIMIT never carries
  it, so a row that asked for 400 steps and reached all 400 came back owing 400
  MORE and spent a licensed seat re-marching a saved state that already held
  them. Reachable from one cell: a row whose post-processing turns the log off
  has no residual history and is recorded at its limit rather than as
  converged. An absent value is not zero, and a recorded zero still owes the
  whole march.

- **`pyfs-matrix plan` rehearses a continuation instead of blocking it.** The
  pre-flight built the script with nothing resolved, so a legitimate `RESTART`
  row raised in the builder and was reported BLOCKED; since v0.17.0 a run needs
  a plan, so this release's own headline feature was unreachable through its
  documented sequence. It resolves and does not archive, because a pre-flight
  spends nothing.

- **A tag whose archive row is still owed after a NEWER tag has shipped now
  fails the release check.** The window is the one commit between a tag and the
  row that pays it, and nothing bounded it: a sentence in this change log kept
  any tag reading RELEASED for as long as the sentence stood. v0.14.0, three
  releases old and archived nowhere, read RELEASED from the check written to
  catch exactly that. A checkout carrying no tags now exits non-zero as well,
  because found-nothing is not a pass.

- **`run/collect.py` no longer reaches the layer above it.** It imported the
  package exception CATALOG, which imports `post`, so a `run` module depended
  upward at import time. The layering guard did not see it because the catalog
  carries no layer row, and an unrowed module can be a conduit; the exceptions
  now come from the modules that define them.


- **The geometry library's own instruction page is not a geometry.**
  `pyfs-workspace init` now writes `inputs/geometries/README.md`, saying where
  a mesh goes (one folder per mesh, named for the mesh), that the `GEOMETRY`
  cell does not change, that the boundary sidecar travels with the file, and
  the one command that moves a flat library over. It is written into the
  folder somebody about to drop a mesh in is already looking at, because
  `migrate-geometries` existed for two releases and the layout it exists for
  was adopted only after a user asked for it by hand. A second `init` leaves
  an edited page alone.
  TWO DEFECTS CAME WITH IT AND BOTH ARE FIXED HERE, found by existing tests in
  the same session and worth naming because they are one mistake made twice: a
  file in that folder was assumed to be a mesh. The resolver offered
  `README.md` in the list of what the library holds, so a user who mistyped a
  mesh name was shown the instruction page as a file they might have meant;
  and `migrate-geometries` filed the page under `geometries/README/`, which
  both hid it from its reader and left a folder the resolver reads as a
  geometry's home.

- **The mesh rotation of `ROTATE` is measured on the solver, as a null test.**
  `tests/tier3_licensed/matriz_rotate.fs` turns a full two-blade wheel and its
  spinner by six degrees about a fixed hub frame and gives the flow the
  opposite angle, so the physical problem is unchanged and the answer is known
  exactly before the solver runs. `reports/RPT-047` is the committed evidence
  and `python -m tests.tier3_licensed.rotation_null` is the measurement.
  IT HOLDS ACROSS 209 COMPARISONS OF FOUR KINDS, worst gap 5.6e-06 against a
  band of 5e-04: the wind-axis coefficients are invariant, the global force
  and moment vectors come back rotated by exactly the stated angle, the
  per-step series agrees step by step, and the sectional loads in the blade's
  own frame agree to the last digit that export prints.
  AND A THIRD ROW EXISTS TO FAIL. It turns the flow the SAME way as the mesh,
  meets the propeller at twelve degrees, and differs on every one of the four
  checks, so the test is shown to discriminate rather than merely to accept.
  The pair also settled a convention nobody had measured: with the mesh turned
  +6 degrees about the hub frame's Y axis, `SOLVER_SET_AOA -6.0` is what
  restores the uniform flow.

## [0.17.0] - 2026-09-13

### Changed

- **Twelve deprecations fell due at 0.17.0 and every one of them moves to
  0.18.0, on a re-count.** They are the two setup preset tables, `[aliases]`
  and `[[frames]]`, and the ten flat row spellings the rotor work of 0.15.0
  replaced with `MOTIONS` records and a reference's rotor block:
  `MOVING_BOUNDARIES`, `ROTOR_AXIS`, `ROTOR_ORIGIN`, `RPM_SIGN`, `BLADES`,
  the flat-row `CLOCK_MOTION`, `ROTATE`'s families selector, and the
  `airframe`, `blades` and `each_blade` selectors of a families cell.
  THE COUNT IS WHY, and it is committed as `reports/RPT-046_the-deprecation-recount_2026-09-13.md`
  with the script that takes it, so the person deciding at 0.18.0 whether the
  deadline may move again can re-run it rather than trust this paragraph.
  Measured on 2026-09-13 over every committed matrix,
  reference, setup and post-processing artifact in this repository and in the
  recorded workspaces beside it: **39 files still state one of them**, 54
  occurrences of `MOVING_BOUNDARIES`, 53 of `ROTOR_AXIS`, 52 of `RPM_SIGN`,
  22 `[aliases]` tables and 8 `[[frames]]`. Eight of those files are recorded
  campaigns, which a run cannot regenerate, and the rest are the tier-3
  fixtures that reproduce them. Removing the readers would orphan all of it.
  WHAT A READER SHOULD DO NOW: write the `MOTIONS` record form and put the
  aliases and frames on the reference artifact. Nothing this package writes
  has emitted any of the twelve since 0.15.0, and the deprecation warning
  names the remedy for each.
  THE HONEST RESIDUAL, the same one the `broken_commands` row carries: the
  exit is a measurement and no mechanism takes it. What is mechanised is the
  DATE, and the deadline test goes red at 0.18.0 whatever the count is.

### Added

- **The run matrix carries nineteen columns.** `GEOMETRY`, `CONFIGURATION`,
  `NCPUS`, `WALLTIME`, `SYMMETRY` and `SYMMETRY_LOADS` are columns of their
  own, and `HIDDEN | RUN` moved to sit directly after `POL`. Every one of the
  six was already stated in the free variables cell of the rows that used
  them; the release moves WHERE a fact lives and makes no fact required, which
  is measured rather than promised: a row that states none of the six reads
  exactly as it did.
  A file in any older layout is upgraded on read, and the upgrade carries
  every cell it does not move as its own bytes: a cell it promises not to
  touch comes out byte-identical, spacing included. A key with an EMPTY value
  stays in the free cell, because `GEOMETRY:` with nothing after it means
  "opens no geometry" and a column cannot say that.

- **A steady matrix row is ONE job and leaves ONE record.** The whole sweep is
  one script the solver never clears between points, which is the warm start:
  the panelling and the wake survive from one angle to the next, so a sweep
  costs one setup instead of one per point. A row that wants the other
  behaviour states `COLD_START: True` and gets a `CLEAR_SOLUTION` between
  points; warm is the default because it is what a polar sweep is.
  The record names the job, carries `points_ran`, and `as_points()` reads it
  back one point at a time, so nothing downstream had to learn a new shape.

- **`WALLTIME` is watched from inside the run.** The row states the wall clock,
  the setup states the margin (twenty minutes by default), and an unsteady run
  registers a solver-side clock that writes the exports and stops the solver
  when the two meet. It is a pair of actions: a python that keeps its own
  state and fires ONCE, and a FlightStream script it rewrites, which does
  nothing until it does. Where a row also exports on a counter the clock pair
  takes positions (3) and (4) behind it, because the solver runs actions in
  creation order.
  A run the clock stopped is recorded `WALLTIME_REACHED`, which is not a
  failure: the numbers up to that step are real, and the record says where it
  stopped and what clock and margin it was given.
  WHAT IS NOT MEASURED, and it is named here rather than left in one source
  comment: whether the stop verb inside an action's script ends the RUN or only
  that script. The command database records it verified on 26.120 to 26.123
  with the manual's own note that it halts SCRIPT PROCESSING at that location,
  which is the ambiguity and not its resolution. Settling it needs a licensed
  probe that moves one thing, and the verb is kept to one substitutable line to
  make that probe cheap. The exports are written either way; what is unproved
  is whether the solver then stops or runs on to its own end.
  `RESTART` is the continuation, spelled `{FINISH_PENDING}`,
  `{ADDITIONAL_ITERS=<n>}` or `{ADDITIONAL_REVS=<n>}`. THIS RELEASE PARSES IT
  AND REFUSES TO RUN IT, naming 0.18.0: the arithmetic exists, no builder
  shortens a march, and a row stating it is refused at plan rather than
  accepted and silently re-run from step one.

- **Linux is the cluster, and no cell says so.** The run path reads the
  platform: on Linux with a profile in `inputs/hpc/h<>.toml` it renders that
  cluster's descriptor, hands the job to the scheduler and returns without
  waiting, and the record is `SUBMITTED`. The setup artifact stays
  multiplatform and states nothing about a cluster, and the same matrix,
  unchanged in every cell, runs locally on Windows and submits on Linux.
  A workspace carrying several profiles and nothing to choose between them is
  REFUSED rather than guessed, because guessing spends a queue. A Linux
  machine with NO profile runs locally, deliberately: not every Linux box is a
  cluster, and a study that wrote no profile is saying it does not submit.
  A submitted point is not assessed and carries no outputs, because it has
  none yet; the record names the descriptor, the profile and whether the
  submit command ran, which is the only thing that says where the job went.
  The local solver-identity pre-flight is skipped on a cluster: asking would
  submit a probe job to a queue to answer a question the descriptor states.
  **WHAT THIS RELEASE DOES NOT DO: collect a submitted job's outputs when they
  land.** There is no collect stage, so a `SUBMITTED` record is completed by
  hand until 0.18.0. It is said here and in FR-99 rather than only in a
  release note, because a reader of the requirement owes the same warning.

### Changed

- **`plan` is mandatory, and `run` will not start without its receipt.** The
  plan carries the warning and asks for the confirmation, and it pins the
  digest of the matrix it read, so a matrix edited between planning and
  running is visible rather than silent.

- **A product is ARCHIVED before it is rewritten, never lost.** A rebuild moves
  the old product into `archive/<day and hour>/` and writes the new one in its
  place: nothing is refused and nothing is destroyed. The old `--overwrite`
  flag is now `--force-overwrite`, it keeps no copy, and it asks for a
  confirmation, so it cannot be reached by habit; a non-interactive session
  answers no.

- **A recorded point's conditions come from its run record, not from the
  current matrix.** The superfile assembled the matrix row before the record
  and never replaced a field an earlier block wrote, so editing the matrix
  after a run relabelled a result that had already happened: a recorded REmi
  of 11.7716754 read back as 99.0 with the manifest untouched. The recorded
  flight condition is now taken first. The matrix still supplies every key the
  record does not, which is every key of every row that has not run. This adds
  no gate; it removes a wrong number. (GEO-039-F02.)

- **A collection that is going to refuse refuses before it moves anything.**
  The destination-exists check was asked immediately before each move, so a
  collision on the second file left the first already moved and the second
  still at its source, with no manifest record and a recovery to do by hand.
  The whole destination set is resolved first and the refusal names every held
  file. Nothing that succeeded before refuses now. (GEO-039-F07.)

- **The `broken_commands` manifest key is promised for removal at 0.18.0, and
  that is its THIRD deadline.** It was 0.15.0, then 0.16.0, then 0.17.0. Each
  move was made on a re-count rather than on a preference, and the count is
  the same one every time: how many recorded rows still carry the old key.
  Re-measured the moment the 0.17.0 cycle opened and UNCHANGED at 18 rows
  across 6 manifests. A manifest is the one surface a run cannot regenerate,
  so removing the reader orphans every one of those rows.
  WHAT A READER SHOULD TAKE FROM A DEADLINE THAT HAS MOVED THREE TIMES: write
  `waived_commands` now. The reader is kept for records already on disk and
  not as a second supported spelling, and nothing this package writes has used
  the old key since 0.13.0.
  THE HONEST RESIDUAL, because a promise this often extended deserves it: the
  ledger entry says the exit is a measurement and not a date, and no mechanism
  measures it. What is mechanised is the DATE: the deadline test compares the
  entry against the project version and goes red at 0.18.0 whatever the count
  is, and the warning a user is shown names that release. So the count is
  re-run when a human remembers, and the guard is what forces the question.

### Fixed

- **A steady sweep no longer changes the physics after its first point.** The
  per-point angle update went through the settings emitter, which writes its own
  default for every argument it is not given, so a sweep whose setup states any
  `SOLVER_MINIMUM_CP` other than the library default solved point one at the
  stated value and every point after it at `-100`. The whole sweep is ONE script
  and the solver keeps the last value it was given, so points two and three ran
  under different physics from point one with nothing in the record saying so.
  Reproduced on a three-point sweep stating `-3.0`: `-3.0`, then `-100`, then
  `-100`. The update now emits the two angles and nothing else, so the settings
  block written once at the top is the one the whole sweep runs under, and the
  recorded setup snapshot is no longer replaced per point either.

- **A one-job sweep now writes one polar row per point.** The job record reached
  the product stage whole, so every point's outputs were classified together and
  ONE loads file selected: a three-point sweep produced a polar table and a
  SUPER file with a single row, named for its first point. The aggregate status
  was also the filter, so one failed point excluded every successful point of
  the same job from products. `RunRecord.as_points()` exists for exactly this
  and was called by the sweep table and by the QA matrix and not here.
  Measured on the release's own example workspace: the three-angle row's polar
  went from one row to three.

- **A steady sweep refuses a folder that already holds its outputs.** The
  single-point path has refused declared outputs that already exist since
  0.16.0, because collection asks only whether a declared output EXISTS and
  cannot tell a file this solver wrote from one that was already there. The
  sweep path started the solver without that check, so a leftover from an
  interrupted run was collected and assessed as fresh evidence and its digest
  recorded as the new run's. Every point of the job is checked before the shared
  script runs.

- **`resume` runs the points a job did not.** Once a steady row had a job
  record, resume discarded every requested point on the strength of the job id
  alone, so extending a sweep from two angles to three and re-running returned
  successfully having executed nothing at all. It now reads the points the job
  recorded and schedules the difference.

- **The wall clock's rescue writes the whole-run exports again.** Sharing one
  emitter between the per-step action and the rescue was the right fix for a
  real divergence, and the shared emitter drops the simulation file, the plots
  table and the log because a per-step action must: a simulation file written
  every time step is not a per-step export. The rescue is the opposite case, the
  LAST thing a stopped run does, and it needs them most.

- **A setup can state the watchdog margin it is documented to state.** The
  settings model forbids unknown keys and had no field for it, so a setup
  stating a margin was refused by name and every run was locked to the
  twenty-minute default: a documented override nobody could exercise.

- **A second point of one row is not submitted over a queued one.** Every point
  of a case shares one simulation folder, including the action program the wall
  clock runs and the state file it keeps its clock in, and a submission does not
  wait. The second point is refused, naming the queued one, until 0.18.0 gives a
  submitted point its own working directory. And a submission whose scheduler is
  not installed is now this point's failure with the profile and the descriptor
  named, rather than an uncaught error that ends the campaign.

- **A submitted row that inherits the campaign's build no longer asks for an
  empty version**, and a row that resolves neither a processor count nor a wall
  clock no longer inherits the previous row's and reserves resources it never
  asked for.

- **A regenerated product no longer claims the run that did not write it.**
  The provenance document preferred a fresh file digest whenever the file
  existed and then bound that entity to the original run through
  `wasGeneratedBy`, so bytes changed after recording were attributed to a run
  that never produced them. Where the two digests disagree the output entity
  now keeps the RECORDED digest and the generation claim, which is true, and
  what the file holds now becomes a separate `pyfs:ChangedOutput` entity under
  `wasDerivedFrom` that no activity claims. A record that states no digest
  reads as it always did: unknown is not changed. It does not refuse, because
  a refusal would stop the post stage on any workspace whose outputs were ever
  touched, a legitimate re-export included. (GEO-039-F01.)

- **Two rotor names a file name cannot tell apart are refused before any
  write.** `A/B` and `A:B` both sanitize to `A_B`, and the product path writes
  with overwrite, so one rotor's reduction silently replaced another's and the
  file left carried the wrong rotor's identity. The complete target set is
  resolved before the first product of that simulation is written. The
  readable file name is unchanged: a name that survives sanitizing untouched,
  which is every alias in every reference here, is not affected.
  (GEO-039-F03.)

- **A reduction reads the clock the export states.** The plots reader built
  steps 1..N even where the table carried an explicit `Time-step` column, so a
  window was labelled with row ordinals and an export whose clock does not
  begin at one could not be reduced by its own step numbers: the real window
  (101, 102) was rejected as reaching past a three-row table. The column is
  read where it is there and strictly increasing, and the ordinal remains the
  fallback for a table that states no clock. Every export this solver has
  produced here begins at 1 and steps by 1, so nothing already recorded
  changes. (GEO-039-F05.)

- **A probe shape the writer cannot serve says so instead of producing
  nothing.** Two probe entries asking for different parameters produced four
  valid samples and NO table, with no message, which was indistinguishable
  from a row that declared no probes at all. That case is now refused by name.
  A single incomplete point among whole ones is still left out, as before.
  (GEO-039-F06.)

- **A non-finite coordinate does not reach a file the solver opens.** A NaN
  never fails a comparison, so `nan < 1e-10` is False and a NaN frame axis
  walked past the degeneracy check, past the parallelism check, and out as
  `nan,nan,nan,1` rows in a probe csv that reported two points written. Frame
  axes, frame origins and serialized coordinates are checked finite.
  (GEO-039-F08.)

## [0.16.0] - 2026-09-11

### Removed

- **The five names the 0.14.0 polar rename deprecated are gone, on time at
  0.16.0.** The pproc `[products]` key `her_polar_format` and the four module
  names `HerPolarTable`, `write_her_polar_format`, `read_her_polar_format` and
  `her_polar_file_name`. THE FORMAT IS UNTOUCHED: only the spelling that named
  a person rather than the thing was ever deprecated, and
  `custom_polar_format` writes exactly what `her_polar_format` wrote. The nine
  committed artifacts that still stated the key were migrated in the same
  change, in this order deliberately: the artifacts first, the reader second,
  so nothing was left unable to parse in between. A file still stating the old
  key is now refused by name.

### Fixed

- **Every reduction of a rotor row that sweeps its advance ratio was being
  skipped.** Measured on a workspace built for 0.16.0: `time_average`,
  `phase_locked` and `per_blade` all came back skipped for the rotor point,
  each naming the same reason, "its reference carries no rotor diameter ...
  Add `rotor_diameter_m`" -- a key the reference is right not to carry, since
  the diameter belongs to the rotor block (FR-63) and a configuration turning
  two sizes of rotor has no one length to put at the top level. The speed
  reader asked two questions in the wrong order: does the row state an advance
  ratio or an rpm, and only then, does the row turn rotors. A row that does
  BOTH, which is what `ADVANCE_RATIO: sweep` beside a `MOTIONS` list is, took
  the flat branch, and the branch that could answer was never reached. THE RUN
  ITSELF WAS NEVER WRONG: the script for such a point builds with the right
  clock, because the builder goes through the motion views. Only the
  reductions were lost, silently, behind a message pointing at the wrong fix.
  This is the defect FR-64 fixed for a row carrying no speed at all,
  surviving one branch over.

- **A changelog entry claimed a feature for a version that does not have it.**
  The FR-89 entry below sat under `## [0.15.0]`. Measured 2026-09-11:

      git merge-base --is-ancestor a21df03 v0.15.0   ->  exit 1

  so the commit that built it is not in that release, and a user who installed
  0.15.0 was told it writes a SUPER file per polar. It is moved rather than
  reworded, and the entry is byte-identical either side of the move.

### Added

- **Each datapoint collects its outputs into its own folder, and a swept row
  runs end to end (FR-92).** `sims/<sim>/outputs/` becomes
  `sims/<sim>/datapoints/DP-<point>/`, one folder per point, named by the point
  tag that already ends the run id and names the generated script. Until this
  release every point of one row wrote into one folder, so from the SECOND
  point onward the standard assessor found two files that both read as loads
  tables and refused rather than guess which point ran; the remedy that refusal
  offered, naming the file, was the one its own documentation ruled out for a
  swept case. The selection was not the defect: a folder holding several
  points' evidence cannot say which file is whose, and every consumer
  downstream then has to re-derive it. This release's headline is sweeps, so
  the case that could not be judged was the case the release is for.

  ONE REFUSAL CHANGES ITS REASON AND NEITHER IS RELAXED. Two outputs of ONE
  point that collect to one name are still refused, at plan time AND at
  collection: they still land in one folder under one base name. Two POINTS
  declaring the same name are still refused too, and the reason moved: they no
  longer collide in the collection folder, which is each point's own now, but
  `post/products.py` names every per-point product after the loads file's stem,
  so they would collide in the PRODUCT tree instead. Measured at the release
  boundary after a first version of this change had relaxed that check: two
  points, one declared name, produced ONE probes table naming both runs while
  holding the last point's data and a superfile recording one point twice.
  Making those product names carry the point tag the folder already carries is
  what would let the check be lifted, and it is registered rather than taken on
  release eve, because it moves file names a user's downstream scripts read.

  A WORKSPACE RECORDED BEFORE THIS RELEASE IS READ WHOLE. `outputs/` and
  `raw/` are read where a workspace holds them and neither is created. Their
  points share a folder, so there the assessor keeps the export whose printed
  operating conditions match the point it is judging, and refuses unchanged
  where that does not settle it.

- **A section distribution over a rotor cuts its blades and not the whole
  rotor (FR-75).** A cut through the whole disk crosses the air between the
  blades and reports a section of nothing, so a distribution laid out in a
  rotor's own frame emits one cut per BLADE. The PLOTS keep the total, which is
  the decision of 2026-09-11: a section distribution over a whole rotor makes
  no sense, so a rotor's distribution count is per blade, unlike the plots'.
  One test pins both counts, so a change to either is visible.

- **A section distribution states its own cut count and plot direction
  (FR-76).** `count` and `plot_direction` per entry, each defaulting to the
  artifact's own value. `include_symmetry` deliberately gains no per-entry
  form: it is a property of the configuration and not of one cut.

- **`[probes]` becomes `[[probes]]`, a LIST of tables (FR-77).** One artifact
  can now probe several frames, each entry carrying its own, with the vertex
  counter running ACROSS the entries so the numbered plot names stay unique.
  THIS BREAKS EVERY 0.15.0 ARTIFACT and does so deliberately: breaking them is accepted, and the artifacts
  will be adjusted. The old spelling is refused by name rather
  than silently accepted. Nineteen artifacts were migrated in the same change,
  and the noun matters: measured 2026-09-11, THREE of them are committed pproc
  artifacts of this repository (the tree holds six, and none carries the old
  spelling) and the other SIXTEEN are in the reference campaign workspaces.

- **The console says which point a campaign is on while it runs (FR-78).** The
  request: a log in the terminal while a campaign runs, saying which stage it is
  on and carrying any warning it raises on the way. Two lines per
  point on STDERR, flushed per line. STDERR because nobody asked for them; the
  cost table of FR-82 goes to STDOUT because an operator asked for it with a
  flag. THE SWITCH IS A PYTHON PARAMETER AND NOT YET A COMMAND-LINE FLAG:
  `run_campaign(..., quiet=True)` silences the lines, and no `--quiet` is
  offered by any console program. Whether one should be is not yet settled.

- **A probe entry prescribes a rectangular or a circular PLANE, not only a line
  (FR-79).** A rectangle by three corners with a discretisation along each
  edge, a circle by centre, normal, radius and a polar discretisation. Both are
  emitted POINT BY POINT by decision, so one declaration produces the same
  export on either run path. The circle's centre appears ONCE rather than once
  per azimuth, which would weight it in anything that averages the file.

- **A probe entry may cite a points file the user wrote (FR-80).** Under
  `inputs/profiles/probes/`, staged into `sims/<sim>/profiles/` and imported by
  the SOLVER. The package does not parse the file to re-emit it point by point,
  which would make it the second author of a survey the user wrote; the entry still
  states its frame and its normalisation.

- **A steady row creates the probe points it exports (FR-81).** Until now a
  steady row emitted `EXPORT_PROBE_POINTS` and no creation verb at all, so the
  script asked the solver to export a thing nobody made and the export returned
  whatever the geometry arrived carrying. That is the fifty-dummy-sections
  defect one family over. A steady row now emits one `NEW_PROBE_LINE` per
  declared line with the entry's own point count, and `NEW_PROBE_POINT` per
  vertex of a plane.

- **A section distribution is created AFTER the solver is initialised
  (FR-83).** A distribution created before the solver is initialised returns
  the declared number of surface sections and every one of them is empty. THE
  COMMAND WAS NEVER THE
  PROBLEM, and the first diagnosis of this said it was: that reading was
  refused, and the recorded reference scripts settled it, and the key the wrong diagnosis
  had introduced was reverted in full before the real fix landed. The cause is
  POSITION. The distributions are now emitted between `INITIALIZE_SOLVER` and
  `START_SOLVER`, which is where the reference scripts put them.

- **`pyfs-matrix plan --cost` tables what each polar will cost (FR-82).** One
  row per point beside the READY and BLOCKED report: mesh size, trailing edges
  marked, farfield layers, viscous coupling, steady or unsteady, time steps,
  processors, an expected time and the number of samples behind it. The flag
  spends no solver time. EVERY COLUMN BUT THE TIME IS A READING, each from the
  thing that owns it; a cell the package cannot derive prints `-` and never a
  zero. THE TIME IS AN EXTRAPOLATION AND THE TABLE SAYS SO UNDER EVERY
  PRINTING, fitted from the wall times this workspace recorded, comparably by
  run type, with one basis line per run type. An UNSTEADY row's estimate is
  linear in the time steps the point asks for; a STEADY row asks for none, so
  its work is one solve and its basis line says that instead. A point with no
  comparable recorded run prints `unknown` rather than a figure with no basis,
  and a recorded unsteady run whose step count cannot be resolved is left out
  of the fit rather than counted as one step.
  It is a crude model on purpose, pending a scalability study to calibrate it
  against.

- **A probe table says WHERE each point is, beside what the flow did there
  (FR-91).** `post/<matrix>/probes/<point>_probes.csv` now opens with the same
  six columns whichever run type filled it, `PROBE, X, Y, Z, FRAME, STEP`, and
  then carries its own export's fluid quantities in their own names and units.
  An unsteady plots export numbers its probe columns, one per parameter the
  row's own probe entry declares, `MACH7, VELOCITY7, STATIC_PRESSURE_RATIO7`
  on the recorded rotor point of `pfs0160`, and it never says where point 7
  is, so its samples could not be placed at all. A steady export does state
  its coordinates, and the frame it names is the ANALYSIS frame rather than
  the one the probe entry laid its points out in, so it could not be placed
  either without knowing the artifact. The package now records the vertex, the coordinates and the
  frame IN THE LOOP THAT EMITS THE POINT, writes them to
  `sims/<sim>/profiles/<sim>_probe_points.csv`, and joins them here. THE FLUID
  COLUMNS ARE NOT FORCED TO MATCH between run types: a steady export returns
  the boundary layer and an unsteady one returns a static pressure ratio, and
  keeping both beats intersecting them. A run recorded before 0.16.0 names no
  positions file, so its `FRAME` cells are empty and its steady coordinates
  still come from the export; the table is written either way. `STEP` carries
  `-` on a steady row, which has one step, and an EMPTY cell means a value the
  package could not derive.

- **One derived file per polar and group carries everything the workspace
  knows about that simulation (FR-89).** Written by the post stage beside the
  polar table, `post/<matrix>/polars/SUPER-0001_M15AL+000BE+000J+sweep_g01.csv`:
  the standard point convention with `SUPER-` in place of `POLAR-`, the swept
  variable written literally as `sweep`, and the group suffix at the end. One
  row per CONVERGED point and no time series, because it is written AFTER the
  unsteady post-process. ITS COLUMN SET IS A SUPERSET of the union of what the
  workspace knows: every column the polar table has, everything
  `campaign_sweep.csv` holds, every parameter the unsteady plots produce with
  forces and fluids alike, RPM and the advance ratio, every variable that
  defines the flight condition as stated, pinned and resolved, every input of
  the matrix row including `DESCRIPTION`, and the solver flags by their own
  command names. The column set is the CAMPAIGN'S and not the polar's, so a
  steady polar's file carries the same header as the rotor's beside it and a
  reader cannot tell from the file which kind of run is behind a row. NO FIELD
  IS LEFT OUT BY JUDGEMENT: the test BUILDS the union by reading the
  workspace's own files rather than listing the names, so a field added
  anywhere upstream fails it until it reaches the superfile, and the stage
  leaves the same measurement under `reports/superfile-<release>.json`.

### Changed

- **A simulation's collected outputs live under `sims/<sim>/outputs/`, not
  `raw/` (FR-84).** SUPERSEDED WITHIN THIS RELEASE BY FR-92 below, which gives
  each point its own folder; kept because it is the history of the word. `raw` named how the data arrived; `outputs` names what it
  is, and the second is what a reader opening a simulation folder wants. A
  workspace that already holds `sims/<sim>/raw/` IS STILL READ, so no
  recorded point is orphaned: the assessor judges a point over both folders,
  a record naming `raw/loads.txt` resolves unchanged, and `raw/` stays a
  MANAGED folder that a declared output may not be collected out of. Nothing
  creates one. THE WORD MEANS THREE THINGS IN THIS PACKAGE AND ONLY THIS ONE
  MOVED: the result column `data_origin`, whose values are `raw` and
  `reduced`, and the `RAW` table of verbatim solver commands a setup states
  are both untouched, and a test asserts the first after the rename.

- **The per-polar tables live under `post/<matrix>/polars/` (FR-88), named by
  the point convention with the swept variable written `sweep` (FR-85).**
  Measured in the reference workspace recorded after running 0.15.0: the
  polar tables sat loose at the top of `post/matriz/` beside `sections/`,
  `plots/` and `provenance/`, so the folder read as a directory and a drawer
  at once; and one point was written under two conventions, the script
  `POLAR-0001_M15AL+000BE+000J+100.txt` and the table `0001_M15_g01.csv`. The
  table is now
  `polars/POLAR-0001_M15AL+000BE+000J+sweep_g01.csv` with the `.dat` of the
  custom format on the same stem. The campaign-level files stay where they
  are: they are about the campaign rather than about one polar's sweep.
  `write_recorded_polar` keeps the recorded convention, because it
  regenerates the reference historical tables and is compared with them
  name for name.

- **A polar table carries `J`, the advance ratio of each row (FR-85).**
  Measured on the reference `0001_M15_g01.csv`: the three rows of a
  three-value sweep carried identical `ALPHA`, `BETA`, `MACH` and `RE` and no
  column naming the swept value, so the only thing distinguishing the first
  row from the third was its position in the file. The column sits outside
  the twenty-four `COEFFICIENT_COLUMNS`, so the custom `.dat` format is
  unchanged; a row whose ratio was not recorded writes an EMPTY cell, because
  zero is a value a rotor row can hold and "not recorded" is not it.

- **Flow-field samples go to `post/<matrix>/probes/`, whatever the run type
  was (FR-87).** The folder was named after the solver verb that produced the
  file rather than after what the file holds. The unsteady plots table and
  its reductions moved there, and the PROBE-POINTS export of a row of any
  kind is tabled there beside them as `probes/<point>_probes.csv`, which is
  new: that export was collected and never read until now. A probe export
  this release cannot parse is a recorded SKIP naming the file and costs the
  simulation none of its other products, unlike the sections and plots
  readers beside it, because every already-recorded workspace holds files
  this reader meets for the first time.

- **A provenance document is named by the point convention its script carries
  (FR-86).** `provenance/pfs0150-eve_sim_0001_a+00.0_b+00.0_j+01.0.prov.json`
  was the run id, which is a good identifier and is simply not the name every
  other generated file of that point carries, so a reader sorting
  `scripts/` and `provenance/` side by side could not line them up. NOTHING
  RENAMES A RUN: the id still keys `products.json` and is still a field
  inside the document. A POINT NAME NEED NOT BE UNIQUE AND A RUN ID IS, so a
  stem two records claim sends both back to the run id rather than letting
  one document overwrite the other.

- **`pyfs-matrix run` writes the campaign sweep table ONCE (FR-90).**
  Measured in the reference `post/matriz/`: `sweep.csv` and
  `campaign_sweep.csv`, both 1012 bytes, one sha256 between them, the same 27
  columns. A reader who found both could not know they were the same without
  hashing them, and a reader who edited one had silently disagreed with the
  other. `campaign_sweep.csv` is the name that survives, and it is what the
  default of `--sweep-csv` now writes; an operator who names a target still
  gets the file where they asked for it.

- **`broken_commands` moves once more, and this time it carries the condition
  that ends it.** A manifest is the one surface a run cannot regenerate, and
  measured on 2026-09-11 over
  `GeoverseResearch/tools/fts_workspace/*/runs.json`, 18 recorded rows in 6
  manifests still carry the old key, among them the recorded
  campaign. The promise had already moved once, from 0.15.0 to 0.16.0, and a
  promise moved twice with no condition is a promise that never expires. THE
  EXIT IS NOW A MEASUREMENT AND NOT A DATE: when that count reaches zero the
  reader goes, whatever release it is. The test asserts the condition rather
  than a version number, so it cannot become a record of the deadline moving.

### Specified, not built

- **NOTHING OF 0.16.0'S SCOPE IS IN THIS SECTION ANY MORE, and the sentence
  that stood here is kept below rather than deleted.** FR-75 to FR-82 were
  logged as written and PENDING when this section was first filled; all eight
  are now implemented, and so are FR-83 to FR-91, so the section that told a
  reader what was specified but not built would be telling them about work
  that is done. The entries above are where each of them now is, and eight of
  those entries were written only after the technical writing lens measured
  that this sentence routed a reader to entries that did not exist.

  What it said: "FR-75 to FR-82 are written and PENDING, the eight
  requirements the open questions and requests of 2026-09-10 produced,
  carried by PFS-2035.22 to .29 at milestone 0.16.0. Seven are capability additions;
  FR-81 is a defect found while measuring for the others, where a steady row
  citing a valid `[probes]` table emits no probe creation verb and still emits
  `EXPORT_PROBE_POINTS`."

### Owed

- **The Zenodo archive of v0.14.0 DOES NOT EXIST**, and that is stronger
  than the sentence that stood here, which said the row was deferred until
  Zenodo answered. Measured 2026-09-10 against Zenodo's own API over ALL
  versions: fifteen pyflightstream records are archived, the newest is
  v0.13.1, and no v0.14.0 is among them. The GitHub release v0.14.0 has
  existed since 2026-09-09T21:42:45Z, so the archive is not late, it was
  never minted. This paragraph said the cause was an outage, that Zenodo
  answered 504 all that evening and the release webhook fired into it. That
  reading is no longer safe. On 2026-09-10 the v0.15.0 tag was pushed, PyPI
  served the wheel, and NO archive appeared either, for a reason that has
  nothing to do with Zenodo's health: `gh release list` showed no GitHub
  release for v0.15.0 at all, because `release.yml` has four jobs, build,
  test-artifact, gates and publish, and none of them creates one; it
  declares `contents: read` and could not. What is measured is the workflow's
  permission, not fifteen past releases: `release.yml` has never been able to
  create one, and how each earlier release got its GitHub release was not
  checked. Creating v0.15.0's by hand minted its archive within minutes,
  which shows the link worked on 2026-09-10; it is one observation and not a
  control, and it says nothing about 2026-09-09. So v0.14.0's absence has two
  candidate causes and the outage is only one of them. It will not appear
  on its own either way. What it takes is a new release event on that tag
  or a manual deposit, and that is an action on a published artifact rather
  than a wait.
  It is recorded here rather than remembered. The guard that would ask for
  it by version, `test_the_newest_archive_row_names_the_version_this_tree_states`,
  skips on a development tree, which is what let the row go missing in the
  first place; the guard that closed that gap walks the TAGS instead and is
  what these two paragraphs answer. The gap in the
  guard, which is that a released TAG with no archive row is invisible
  whatever the tree's version says, is registered as PFS-2024.09 for
  0.15.0. Until the row lands, cite v0.14.0 by the concept DOI, which
  resolves to the newest archived version.

## [0.15.0] - 2026-09-10

### Added

- **A setup declares CUSTOM FLAGS, and a row sets a solver command by
  name** (FR-74, PFS-2035.20, the instruction of 2026-09-10). A preset
  states `[[flags]]` once per flag with `name`, the word a row writes, and
  `command`, the FlightStream command it becomes, bare; a row citing that
  preset then writes `base_bending: 12.5` and the script carries
  `SET_BASE_REGION_BENDING_ANGLE 12.5`. THE DIFFERENCE FROM `[[raw]]`, which
  is the whole point: a raw entry is a whole line with its arguments, fixed
  in the preset, so every row citing it emits the same one; a flag names the
  command and the ROW states the value, so one preset serves a SWEEP over it.
  That is what leaves RAW to the particular case its name promises. The line
  passes the same emit check every curated emission passes, so a flag naming
  a command this build cannot emit, or a value of the wrong type, is refused
  at PLAN time with the flag, the preset and the value named, never at the
  machine. A flag reaches the three seams a raw entry reaches; one whose
  command belongs to a later phase is refused naming that phase rather than
  quietly not appearing. Worked and RENDERED, which is the claim the
  evidence supports: `SET_BASE_REGION_BENDING_ANGLE` is `documented` on
  every registered build and probed on none, so this package has never
  observed the solver accept it and does not say it has.
  `tests/tier3_licensed/inputs/setups/s006.toml` declares it, row 8006 of
  `matriz_vocab.fs` sets it, and the committed golden carries the line.

- **A study's vocabulary lives in the reference artifact** (FR-59, FR-60,
  FR-72, the design of 2026-09-10). `inputs/references/<id>.toml` now reads
  three tables: `[aliases]`, where a member may be another alias and the
  reader follows to the end, refusing a ring by naming both sides;
  `[[frames]]`, unchanged in shape; and ONE BLOCK PER ROTOR, `kind =
  "rotor"`, whose name is an alias over everything that rotor owns. A
  rotor block states its hub, `axis`, `rpm_sign`, `diameter_m`,
  `families_general`, `families_blades` and `blade1`; the BLADE COUNT is
  the length of `families_blades`, so a row states no count and a sector
  mesh carrying one blade of four still reduces over four.
- **A row names its rotor by alias and states nothing else about it**
  (FR-61). A motion record carries `MOVING_BC_ALIAS` and takes the hub, the
  axis, the sign, the blade count and the diameter from the block it names.
- **An advance ratio resolves against that rotor's own diameter** (FR-63),
  so one ratio written once gives a 1.20 m lifter and a 1.80 m pusher two
  different speeds, which one `propeller_diameter_m` could not express.
- **The frames a rotor instantiates take its alias as their radical**
  (FR-62): `<ALIAS>_SMRP` at the hub, `<ALIAS>_RMRP` turning with the
  motion, `<ALIAS>_RMRP<k>` per blade and turning with it. Nine rotors
  instantiate nine sets rather than colliding on one radical. A
  post-processing entry may cite them; the 0.14.0 names still resolve.
- **`CLOCK_MOTION`**, the motion that owns the time step (FR-64), REQUIRED
  on any row that states a `MOTIONS` list. Which rotor bounds the time step
  and counts the revolutions is a decision the row states, not arithmetic
  the package performs in silence: without the key the clock followed the
  fastest rotor and nothing in the row said so. A row states the key or it
  is refused, naming the motions it could have named.

  The flat pre-0.15.0 form is EXEMPT: it names one rotor in its own keys and
  has nothing to choose between. `rotor_speed` keeps its name; the draft of
  FR-64 renamed it `rotor_speed_ref` and the owning seat struck the rename.
- **`<ALIAS>_SMRP_ORIGINAL`, the frame a rotation turned FROM** (FR-71).
  Once per alias, before its FIRST rotation, the builder copies that rotor's
  hub frame; nothing turns the copy, so a study of an installed propeller can
  still be read in the frame it started in. Before this release that frame was
  lost the moment the mesh moved. ONCE PER ALIAS AND NOT ONCE PER RECORD is
  the decision of 2026-09-10: a row that turns one alias twice keeps the state
  before the first rotation and adds nothing at the second.
- **AND YOU DO NOT HAVE TO CITE IT.** A post-processing entry naming a hub
  frame this row ROTATED is written in BOTH: once in `<ALIAS>_SMRP`, where
  the rotation left it, and once in `<ALIAS>_SMRP_ORIGINAL`, where it
  started, the two plot names differing by the same suffix so neither
  overwrites the other. The rule of 2026-09-10: an entry says which ROTOR it
  is about, and the row's rotation decides how many readings of it there
  are, exactly as the frame decides how many emissions an entry stands for.
  The alternative was a second entry written by hand on every row that
  rotates, which is a second home for one question. A rotor this row did not
  turn has no copy and doubles nothing; `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>`
  never double, because they turn WITH the motion at every step and so have
  no single frame they turned from.
- **`SYMMETRY_LOADS` on the row** (FR-66), overriding the preset with a
  warning, because whether the solver reports the sector's loads or the
  wheel's is a per-row choice.
- **THE FRAME DECIDES HOW A POST-PROCESSING ENTRY EXPANDS** (FR-65), so
  there is no `expand` key: a reader who has said which frame a quantity is
  measured in has already said how many of it there are. An entry in `MRP`
  or a declared frame is ONE over the set it names; one in `SMRP` or `RMRP`
  is one per ROTOR, in that rotor's own frame; one in `LOCAL_AXIS` is one
  per BLADE, plus one for the rotor's general families, which have no local
  axis and ride the rotor's. Six lines of a `[plots]` table become
  twenty-seven emissions on a nine-rotor aircraft. The same rule governs
  the `[sections]` distributions and the `[probes]` table.
- **An alias may name ROTORS, and a rotor's name stands for its own
  families.** `lifters = ["LIFT_L1", "LIFT_L2"]` in the reference's
  `[aliases]` is how a group of rotors is written, and an entry citing it
  reaches every rotor in it: the words are matched against each rotor's
  families by INTERSECTION, so an alias spanning several is not a subset
  of any one of them and still reaches all. An entry citing PART of a
  rotor emits that part, not the block's union under the name you wrote.
- **An entry this run cannot place is left out; one the reference cannot is
  refused.** A steady row places no rotor frames and a lifters-only row
  places no pusher frames, and one artifact serves all three, so such an
  entry is skipped with a warning exactly as an entry whose families the
  geometry lacks is, and the warning NAMES the frames it dropped, so a
  partly working entry is as visible as a wholly skipped one. An entry whose families reach no rotor the REFERENCE
  declares is refused instead, naming the entry, the set and the rotors,
  because that one cannot come right on another row.
- **A probe table's `rotor_radius` is the radius of the rotor whose frame
  it names.** The reference states a diameter per rotor since 0.15.0
  (FR-60), so reading the configuration's would lay a lifter's probes out
  over a pusher's disk without saying so.
- **The flight condition's `ADVANCE_RATIO` reaches every motion that states
  no speed of its own** (FR-70), as a value or as `sweep`. A record stating
  its own `RPM` or `ADVANCE_RATIO` holds it and the condition's ratio passes
  it by, which is what lets one row sweep the pusher while the lifters hold.
  A record may not state the word `sweep`: sweeping is the condition's job,
  stated once for the row, and a record that writes it is refused.
- **THE THREE REFERENCE CASES RAN AGAINST THIS RELEASE'S WHEEL BEFORE THE
  TAG, AND IT MOVED NO NUMBER.** Rows 3207, 3224 and 9001, rewritten in the
  new vocabulary, reproduce the 0.14.0 run coefficient for coefficient and
  residual for residual, and the rotor case's emitted script is byte for
  byte 0.14.0's. The comparison is `reports/master-cases-0150.json`, whose
  band is read from the reference recorded deltas rather than chosen, and the
  report is `reports/RPT-046_her-master-cases-against-the-0-15-0-wheel_2026-09-10.md`,
  which also lists what it could NOT check. Both are committed, and this
  entry exists because a V&V lens found the release's headline evidence
  cited by no shipped artifact.
- **`--ignore-missing-families`, on `pyfs-matrix plan` and `run`** (FR-73,
  the design of 2026-09-10). The default is true and it reads a word, so
  `--ignore-missing-families false` is what a shell writes. With false, three silences become refusals ON A
  POST-PROCESSING `families` SELECTION, each naming the geometry's own boundaries beside what was
  cited: an alias member no boundary answers, which the resolver drops so
  quietly that an alias of six members over a mesh carrying five still
  expands and writes its plot, and whose message names the alias that
  DECLARES the member rather than the word the entry wrote; a LIST member
  that names nothing, which is worse, because a list aggregates into one set
  that is non-empty as soon as one member resolves, so `["WING", "BLADE_1"]`
  over a mesh with no blade selects the wing and passes; and an entry that
  selects nothing at all, which is left out of the products. An alias cited
  by `MOVING_BC_ALIAS`, `BASE_REGIONS` or a `[groups]` member is NOT covered
  and still drops an absent member in silence.

  A WORD OUTSIDE THE VOCABULARY IS REFUSED. `true`, `yes` and `1` mean yes;
  `false`, `no` and `0` mean no; anything else is a usage error naming the
  flag and the word. The first version read every other word as yes, so
  `--ignore-missing-families off` would have given you the silence you were
  turning off and said nothing about it.

  The skip is what lets one reference and one post-processing artifact serve
  a wing-body and an isolated rotor, and from the emitted script that skip
  and a MISSPELLED family are the same event. Which of the two you are
  looking at is a property of what THIS RUN was for, not of the row or of
  the artifact, so it is a flag and not a cell. `convert` does not take it:
  it writes a file that outlives the command, and a per-invocation choice
  frozen into an artifact stops being one. AT THE DEFAULT NOTHING IS WRITTEN
  onto a case, so every recorded run keeps its identity and every emitted
  script its bytes.
- **A row may state raw solver commands of its own** (FR-67), in a `RAW`
  list inside the row's `VAR_NAMES_VALUES` cell, beside `MOTIONS` and
  `ROTATE`. A record writes the line itself or names a text file of the
  workspace whose lines are emitted in order:

  ```
  ... / RAW: {COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}, {FILE: raw/extra.txt / BEFORE: init}
  ```

  **A raw record's pairs split on a SPACED slash**, ` / `, and not on the
  bare one every other record kind uses, because its values are a path and
  a command line and both carry slashes of their own; a record written
  with tight slashes is refused naming the spacing. A blank line and a line opening with `#` are skipped, so a
  raw file may explain itself. Every line passes the same emitter checks
  the preset's `[[raw]]` table passes, and a file carrying a command this
  build lacks is refused naming THE FILE AND THE LINE rather than the
  cell, because the cell holds a path and the mistake is thirty lines
  away. At one seam the preset's lines come first and the row's after,
  which is the ground and the specific over it. The run record names each
  line's source: the setup's id, the word `matrix`, or `<path>:<line>`. A
  LEGACY row may not state the key, for the reason its preset table may
  not: that row is built by its own recipe, which emits no raw command, so
  the lines would be recorded as taken and never emitted.
- **Each rotor reduces over its OWN blade passage** (FR-68). A transition
  row turns the lifters and the pusher in one run at different speeds and
  with different blade counts, so one blade passage of the ROW has no
  length: the phase-locked and per-blade reductions are computed per
  rotor, each from its own engine block's blade count and its own
  revolution, and the files name the rotor
  (`<point>_per_blade_PUSHER.csv`) on every row that names its rotors,
  one rotor or nine. A row turning one rotor takes the count from that
  rotor's block, so `BLADES` and `PERIODIC_COPIES` are no longer the only
  places a blade count can be written. **A row stating no motion keeps
  the flat file names it has always had**, which is every row written
  before 0.15.0. The manifest entry of each per-rotor file carries a
  `rotor` field, so the rotor is readable without taking a file name
  apart, and the flat entry's skip names the files that were written
  instead. A rotor whose motion cannot be resolved is a skip under its
  own name rather than an absence.
- **A row that states its speeds in `MOTIONS` reduces at all.** It carried
  no `RPM` of its own, so the window reader found no speed and every
  reduction of the point was skipped, the time average included, with a
  sentence saying the row states no rotor speed on a row that states
  several. The row's window is the clock motion's (FR-64).
- **A sector row takes its copy count from its two files** (FR-61, "a
  property of the file the row opens rather than of the rotor the
  reference declares"). A row
  declaring `SYMMETRY: PERIODIC` and no `PERIODIC_COPIES` reads the
  wheel's blade families from the reference and divides by the ones the
  geometry it opens actually carries, which is how many times the slice
  repeats: a rotor of four blade families meshed as a sector carrying one
  stands for four copies, and the same rotor meshed as a half, carrying
  two, stands for two. A pair that does not divide evenly is refused
  rather than rounded, and so is a geometry carrying every blade family
  of the rotor, which is the whole wheel and not a slice of anything. One
  rotor only: a sector is a slice of ONE wheel, so a row turning several
  still states a count. The per-rotor REDUCTIONS that also read a blade
  count are FR-68 and are not in this release.
- **A rotation names what it turns by ALIAS** (FR-71), the same word a
  motion uses, so every surface that names a group of boundaries now names
  it the same way and the reference is the one place a study says what its
  groups are. It names exactly ONE declared word: a rotation carries the
  frames of what it turns, and those belong to one rotor. A word the
  reference does not declare is refused at plan time, naming it, and a
  word naming two declared rotors is refused telling you to write one
  record per rotor.
- **Every frame an alias owns turns with it.** Turning a rotor turns
  `<ALIAS>_SMRP`, `<ALIAS>_RMRP` and each `<ALIAS>_RMRP<k>`, so a row no
  longer lists by hand the frames its own rotor placed, and the motion
  created after the turn spins about the pitched axis.
- `SweepAxis.held`, the coordinates a row holds at every point of its
  sweep. A converted `campaign.toml` writes them beside `values`.
- Public names: `EngineBlock`, `BladeDatum` and `AliasCycleError` in
  `pyflightstream.cases`, the last also in `pyflightstream.exceptions`; and
  `SWEEP_WORD` in `pyflightstream.cases.matrix`, the word a swept key
  carries, for the script that WRITES a matrix rather than the person who
  types one.

### Changed

- **ONE WORD FOR THE ROTATING THING: ROTOR, everywhere** (PFS-2035.21, the
  design decisions of 2026-09-10: between `engine` and `rotor` the word is
  `rotor`, everything normalising to it as the most general term). Engine,
  propeller and
  PROP named one object across three artifacts, and each was a guess about
  the configuration; a propeller is a rotor and so is a lift fan, so the
  general word is the one that never has to change again. The reference
  block is `kind = "rotor"`, its length is `rotor_diameter_m`, the recorded
  block is `[rotor]`, the point kind is `rotor`, the probe scale is
  `rotor_radius` and the workspace accessor is `rotor_point`.

- **A RETIRED ATTRIBUTE REFUSES WITH AN ERROR THE PACKAGE CATEGORY CATCHES**
  (PFS-2035.21, delegated on 2026-09-10 as a detail to be settled whichever way
  is most reasonable). `CampaignWorkspace.engine_point` is kept so that
  it can refuse, and it raised a bare `AttributeError`: correct about what
  the attribute is, and silent to the one category this package tells
  callers to catch. A caller wrapping workspace work in
  `except PyflightstreamError` got a traceback instead of the sentence the
  retirement registry wrote for that moment. It now raises
  `pyflightstream.exceptions.RetiredAttributeError`, which inherits
  `PyflightstreamError` and `AttributeError`, in that order, as every other
  dual-base class in the catalogue does; no caller who was catching the
  second is broken.

  **IT IS NAMED FOR AN ATTRIBUTE AND NOT FOR THE REGISTRY, deliberately.**
  The registry retires nine spellings and this class covers one. The other
  eight are values inside FILES, and they cannot use it rather than merely
  declining to: they refuse inside pydantic field validators, which
  intercept only `ValueError` and `AssertionError`, so an `AttributeError`
  raised there would escape the model uncaught instead of arriving as the
  artifact's own refusal. They keep raising `ValueError` and surface as
  `InputArtifactError`, which is already in the package category. A name
  like `RetiredNameError` would have promised that one `except` catches a
  retired `[propeller]` table, and it does not. The interface and
  technical-writing lenses of the release review reached that finding
  independently and the architecture lens measured the pydantic reason.

- **THE PACKAGE-LEVEL ROTOR FRAME IS GONE, not renamed** (the owning seat, on the
  rename made first: it should not exist at all now that the convention is per `<ALIAS>`). At 0.14.0 a reference described one propulsor, so one frame at
  one position was the whole story; a reference declares one block per rotor
  now and each carries `<ALIAS>_SMRP` at its hub, `<ALIAS>_RMRP` turning
  with it and `<ALIAS>_RMRP<k>` per blade. `PROP_MRP` was the one-propulsor
  assumption spelled out. The positional `PROP_MRP<k>` and `RotorAxis<k>` go
  with it: they read as names and were an INDEX, so a post-processing entry
  citing one silently followed the ORDER of the MOTIONS list.

- **NO OLD SPELLING IS ACCEPTED, and each refuses naming its replacement**
  (the owning seat: an old spelling is to raise, with a message saying which
  name it became and how to correct it). The principle that decides
  which promises break is recorded in `_deprecations.py`: A DEPRECATION
  INTRODUCED IN AN UNRELEASED VERSION IS NOT A PROMISE ANYONE HAS RECEIVED.
  The twelve entries of the 0.15.0 batch were written in 0.15.0, which had
  not shipped, so no workspace was ever told the old spelling would keep
  working. Seven move to `REFUSED_IN_0_15_0`; `ROW_PROBE_SCALE` moves
  instead to `_retired_names`, because it renames a WORD rather than a
  structure; and five were created in this release and were never
  promises at all. THE 0.14.0 BATCH IS
  UNTOUCHED: those promises were published, they expire at 0.16.0 anyway,
  and breaking them would break a workspace that upgraded on their strength.
  A new module, `_retired_names.py`, holds what each word became and why.

- **THE RUN MATRIX LOST A COLUMN: `SWEEP_TYPE` is gone** (FR-69, the rule of
  2026-09-10). A sweep is applied to a variable that DEFINES the flight
  condition, and to exactly one, so the `FLIGHT_CONDITION` cell says which
  by carrying the word `sweep` where that key's value would be, and
  `SWEEP_VALUES` holds its values. The verified layout is 13 columns. A
  file at the 14-column layout is RECOGNISED by its header and refused
  naming `pyfs-matrix upgrade <path> --in-place`, which folds the cell:
  `AL` becomes `ALPHA:sweep`, `BE` becomes `BETA:sweep`, and a paired
  `AL/BE` whose second axis held ONE value becomes `ALPHA:sweep, BETA:<v>`
  with the same rows. **THE UPGRADE DOES NOT RENAME A RUN**: a held angle
  is carried at every point, so the point tags that end every `run_id` in
  every existing manifest are the ones the converted file plans under, and
  a resume after the upgrade finds its records.
- A row that sweeps BOTH angles is the one case the converter refuses
  rather than guessing: it is one row per sideslip, each needing a POL of
  its own, and a POL is run identity. The refusal names every such row.
  A paired `AL/BE` whose second axis holds ONE value is not one of those:
  it varied one variable all along and it converts with the same rows, so
  check your matrices for the shape rather than for the code.
- The keys a row may sweep today are `ALPHA`, `BETA` and `ADVANCE_RATIO`.
  Any other key of the cell is refused NAMING those three, rather than
  accepted and silently run as a single point.
- `EngineBlock.alias` is REQUIRED on the model. A reference file may still
  omit it and the reader fills it in from the block's name, so nothing a
  user writes changes; a block built in Python without one used to build
  frames named `None_RMRP1` instead of refusing.
- `resolve_alias` follows a member that is itself an alias, and can now
  raise `AliasCycleError`. A member the mesh carries is that boundary
  first, so no file that resolved before resolves differently.
- The `broken_commands` MANIFEST key now reads until **0.16.0** rather
  than 0.15.0. The promise moved deliberately and the ledger carries the
  measurement: a manifest is the one surface this package cannot
  regenerate, and recorded campaigns still carry the old key. The three
  PROPERTY shims of the same rename went on time.

### Deprecated

- `SweepAxis(type="alpha_beta")`, the paired sweep. A matrix row cannot ask
  for one since the layout lost `SWEEP_TYPE`, and a hand-written
  `campaign.toml` still can: a sweep is ONE variable, so write
  `type = "alpha"` with `values` and put the second angle in
  `held = {beta = ...}`, which plans the same runs under the same names.
  Removed at 0.17.0.

### Removed

- **REFUSED, not deprecated, and each names its replacement.** These stood
  under `Deprecated` for one round, promising a warning and a 0.17.0
  deadline; the release review measured that every one of them refuses. The
  promise was written in 0.15.0 and 0.15.0 had not shipped, so no workspace
  ever received it (`_deprecations.REFUSED_IN_0_15_0`).

  - The setup preset's `[aliases]` and `[[frames]]` tables. Write them in
    the reference. A boundary name and a coordinate system are properties of
    the CONFIGURATION and a preset is per condition, so a file stating both
    is a file with two answers.
  - A motion record's `MOVING_BOUNDARIES`, `ROTOR_AXIS`, `ROTOR_ORIGIN`,
    `RPM_SIGN` and `BLADES`: the reference states each once, in the rotor's
    own block, and the record names that rotor by alias.
  - A `families` entry's `airframe` and `blades` SELECTORS. They are the two
    that decided what a BLADE is from a regular expression over the family
    name, so a mesh whose blades are spelled another way got an airframe
    with blades in it and nothing said so. Declare the set in the
    reference's `[aliases]` table and cite it by name; `all` and `each`
    stay, because they guess nothing. AN ALIAS OF THAT NAME IS READ FIRST,
    which is what makes the migration cheap: a reference that already
    declares `airframe` is untouched, and every one of the reference artifacts does.
  - A post-processing entry's `families = "each_blade"`. The FRAME says it
    now: write `frame = "LOCAL_AXIS"`, which is one per blade.
  - A probe table's `scale = "propeller_radius"`. Write `rotor_radius`.
  - A rotation record's `FAMILIES`, which named its boundaries inline.
    Write `ALIAS` and let the reference say what that rotor owns. THE VALUE
    CHANGES WITH THE KEY, which a rename does not:

        ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: Blade,S / AUX_FRAMES: PROP_MRP}
        ROTATE: {ANGLE: 3 / AXIS: NAC-Y / ALIAS: PUSHER}

    `ALIAS` names the ROTOR those families belong to, not the list. `ANGLE`
    and `AXIS` are unaffected, `AUX_FRAMES` is no longer needed because the
    alias carries that rotor's frames, and a families list spanning two
    rotors becomes one record per rotor. The refusal names the words your
    own reference declares, so the value to write is in front of you.

Five shims whose ledger promise named this release. Each has warned since
0.13.0:

- `Script.broken_commands`, `PointPlan.broken_commands` and
  `RunRecord.broken_commands`. Use `waived_commands`: the entries are
  waivers a recipe registered, not commands that broke in a run.
- `pyflightstream.utils.sweep_editions`. Use `manual_editions`.
- The positional call of `propose_type`. The two strings are keyword-only
  and the signature now refuses a positional call itself.

## [0.14.0] - 2026-09-09

### Changed

- **The polar format's five names are spelled `custom`** (closing the 0.13.0
  review's finding API-4, that the previous prefix on five public names had no
  antecedent a reader could resolve):
  `[products] custom_polar_format` on the pproc artifact,
  `CustomPolarTable`, `custom_polar_file_name`, `write_custom_polar_format`
  and `read_custom_polar_format`, and the fixture
  `tests/tier1_offline/fixtures/custom_polar_format_sample.dat`. The old
  key `her_polar_format` is read as the new one, and the four old Python
  names, `HerPolarTable`, `her_polar_file_name`, `write_her_polar_format`
  and `read_her_polar_format`, forward to the new ones, each warning from
  the deprecation ledger with the removal version, 0.16.0. The format
  itself does not change by a byte.

- **An empty `[groups]` entry of the pproc artifact is every family the
  geometry carries, and a group member may be a family name or an alias
  of the setup** (the design decisions of 2026-09-09, settling the verdict
  PFS-2005.02, "an empty boundary list is refused wherever the solver
  would read it as disable everything", left to the domain seat). `"1" = []` was refused at plan
  time as "domain seat, not yet decided"; it now plans READY, its polar
  table sums every surface row of the loads table, and
  `MOVING_BOUNDARIES: g1` naming it moves every boundary of the file. A
  member is resolved by the one function `pyflightstream.cases.select_group_members`,
  on the script path against the file's boundary labels and at products
  time against the loads table's surface rows: an exact name first, then
  an alias, then a family, the label without its trailing number, so
  `"2" = ["Blade"]` sums `Blade1` to `Blade6` where it summed nothing
  before. A `families` entry resolves the alias FIRST, before the five
  selector words, because shadowing them is what an alias is for; a
  boundary-citing cell and a group member take the exact name first, so
  a preset's word cannot shadow a label the file carries. `expand_group`, the recipe tool that numbers members by
  position, refuses an empty group naming the meaning.
  `ENTITY_SELECTIONS` carries the verdict beside the key.

- **Two readings of the pproc artifact widen with them** (the reference p001 of
  the same day): a `families` entry may be a bare word, an alias or a
  family name, judged at build time and skipped when it resolves to
  nothing, where the reader refused any word outside the five selectors;
  and an entry's `frame` may name a frame the setup's `[[frames]]` table
  defines or, on a row with several rotors, one rotor's own `PROP_MRP<k>`
  or `RotorAxis<k>`, where the reader accepted MRP, PROP_MRP and
  BLADE_AXIS alone. A frame the run did not create is still refused at
  plan time naming the frames it did.

### Added

- **A setup preset names groups of mesh families under `[aliases]`, read
  wherever a boundary is cited** (the design decision of 2026-09-09). One key per
  alias, a list of boundary names or families in any mix; a member the
  file does not carry is ignored, so one preset serves every geometry of
  a study. The alias resolves in `MOVING_BOUNDARIES`, `ROTATE`'s
  `FAMILIES`, `BASE_REGIONS`, a pproc `[groups]` member and a `families`
  entry, between the exact boundary name and the family, and before the
  five selector words of a `families` entry, so `airframe` and `blades`
  are the preset's own where it defines them and nothing is hardcoded
  (`pyflightstream.cases.resolve_alias`; `SetupArtifact.aliases`;
  `SimCase.aliases`; `select_families` and `group_coefficients` take
  `aliases=`). The run record carries them as `aliases` (the manifest
  schema does not move; a record written before reads them as empty)
  and the provenance document as `pyfs:aliases`, so the products stage
  resolves a group by them without opening the preset. A cell naming an
  alias none of whose members the file carries is refused naming the
  alias.

- **A setup artifact defines custom coordinate systems, created after the
  package's own** (PFS-2034.01, the design of 2026-09-09, design/69, the
  first node of the incidence study). A `[[frames]]` table, one entry per
  frame with `name`, `origin` and optionally `x_axis` and `y_axis` in the
  geometry's own frame, read out of the raw settings by `resolve_setup`
  so the solver-setting loop never meets it, carried on the case as
  `SimCase.frames`, and emitted by every run type after `MRP` and
  `PROP_MRP` and before any motion, through `helpers.coordinate_frame`.
  A name the package creates itself (`RESERVED_FRAME_NAMES`, public in
  `pyflightstream.cases` beside `FrameSpec`), a name defined twice, or an origin
  that is not three numbers is refused at plan time naming the preset. A
  setup defining none emits nothing: the seven tier-3 matrices render
  byte-identical (`python -m tests.tier3_licensed.offline`, 0 differing).
  RED on b376b14: the table was refused as a key naming no solver setting.
- **A row turns the mesh: `ROTATE`, a list of records like `MOTIONS`,
  one rotation each in the order written** (PFS-2034.02, the design of
  2026-09-09, design/69: the incidence study's pitch and toe from a row,
  the geometry file untouched). `ROTATE: {ANGLE: 3 / AXIS: NAC-Y /
  FAMILIES: Blade,S / AUX_FRAMES: PROP_MRP}, {...}`: `AXIS` names a
  frame the setup defines or the package creates and one of its axes,
  `FAMILIES` resolves by name against the geometry's inventory as
  `MOVING_BOUNDARIES` does, `AUX_FRAMES` names the frames that turn with
  the mesh, and a frame the package derived from one of them (the blade
  axis frames, from `PROP_MRP`) turns with it. Registered on every run
  type; emitted after every frame exists and before any motion, so a
  rotor whose axis frame is among the auxiliaries turns about the
  pitched axis. A family the inventory lacks, a frame nothing defined,
  an axis token of another shape, a missing or unknown record key and a
  non-numeric angle are refused at plan time naming the row. The reader
  generalized the `MOTIONS` record grammar (`_parse_records`), which
  the two keys share. RED on bf9fe31, fifteen tests: the tour's rotor
  row stating the key was BLOCKED as a key of no run type, the built
  case rendered no rotation, the reader had no records.
- **The two mesh rotations, `SURFACE_ROTATE` and `ROTATE_SURFACE`, are
  setup-phase commands** (PFS-2034.02). Both cite a frame, and the
  manual's own sample cites frame 3, a created one; under the package's
  ordering a geometry-phase rotation could never follow the
  `CREATE_NEW_COORDINATE_SYSTEM` that makes the frame it cites, so the
  row above was refused at the frame it named (`ScriptOrderError`,
  measured on bf9fe31). The rest of the mesh-operations chapter keeps
  the geometry phase and the narrowing the CAD chapter's header records
  (`test_the_threshold_command_can_only_cite_the_reference_frame`);
  whether the solver accepts the rotation after the frame is the seat
  run's measurement (PFS-2034.05). The chapter test emits its rotation
  sample last and its golden moved with it, byte for byte otherwise.
- **The rotation's refusals, and the rotor axis turning with its blades**
  (PFS-2034.03). `ROTATE` on a `LEGACY` row is refused when the matrix is
  read, naming the POL, because that row's recipe reads its keys and
  reads no rotation, so the list would have turned nothing in silence; a
  frame nothing defined and an axis token of another shape block the row
  at plan time naming what the case does define (tests pinned at the
  tier-3 workspace). `PROP_MRP` named among the auxiliaries is turned
  before the motion is created and the motion cites that same frame, so
  it spins about the pitched axis. A rotor row that turns its blades and
  does not name the frame they spin about warns naming the frame, and is
  not refused: the blades alone turning is a call the row may mean. RED
  on d665201: the LEGACY row read fine, the blades-only row warned
  nothing.
- **The per-step exports of a windowed point as a series**
  (PFS-2031.18.01, the reference incidence study's unsteady plots and surface
  sections after N revolutions). The products stage tables the stamped
  files of the export window, one table per kind under
  `post/<matrix stem>/series/` (the new public module
  `pyflightstream.post.series`: `write_point_series`, `stamped_exports`,
  `SERIES_DIR`, `SERIES_KINDS`, `SERIES_LEAD`): the loads wide (a row per step, a column per
  surface and coefficient), the sections and the probes long (a row per
  step and section or probe), every table leading with `step`, `time_s`
  and `azimuth_deg` computed from the clock the run record now carries
  (`export_window.delta_time_s`, `step_deg`) by the counter program's own
  arithmetic; the Tecplot and `_cp` files listed in `products.json` by
  path. A record without the clock leaves the time blank and reads the
  azimuth off its reductions plan; a step never stamped is absent and
  named; a run with no section or probe gets the header alone. The
  series rest on the record and the stamped files, so a simulation whose
  polar is refused keeps them. RED on d908092: no series folder, the
  record's window without a clock.
- **A probe export declaring no point reads as an empty table**
  (PFS-2031.18.01, found on the reference workspace on 2026-09-09; the fixture is
  the solver's own file from the tier-3 actions row 6002, committed). Every stamped
  probes file of the reference rows 1226 and 5913 declares `Number of Probe
  Points: 0` with the header and the opening and closing dashed lines
  and nothing between them, and the parser refused it as a file cut
  mid-table, because its walker skips every dashed line after the header
  until a row appears. A declared count of zero is now a complete table
  of no rows. RED on d908092 with the fixture's rows removed.
- **The blade count of a sector mesh comes from `PERIODIC_COPIES` when
  `BLADES` is absent** (PFS-2015.04.01, found by the reproduction on
  2026-09-09: rows 5901, 5903 and 5913 of pfs0131, one blade meshed and
  `PERIODIC_COPIES: 6`, had their phase-locked and per-blade reductions
  skipped for want of a key saying the same number twice). A row stating
  both keeps `BLADES`; a row stating neither is skipped or refused naming
  both keys. RED on d908092: `blades` None and the skip naming `BLADES`
  alone.
- **A setup artifact states raw solver commands, each before a named
  phase, through the same emitter as every curated line** (PFS-2033.01
  and .02, the design of 2026-09-09, design/69). A `[[raw]]` table, one
  entry per line with `command` (the line as the solver reads it) and
  `before` (geometry, setup, init, exec, analysis, export, or control
  for the head of the script), read out of the raw settings by
  `resolve_setup`, validated as `RawCommand` (its phases `RAW_PHASES`,
  both public in `pyflightstream.cases`), carried on the case as
  `SimCase.raw_commands` naming the preset, and emitted by every run type
  at the seam before the first command of the phase, in the order
  written, through `Script.emit` after splitting the line and coercing
  its arguments to the database's types. A command the build lacks, an
  argument of the wrong type, a command whose grammar is a block, and a
  command of a later phase than the one named are each refused at plan
  time naming the preset and the line, the first three by the emitter's
  own sentence. The run record gains `raw_commands` (absent on older
  records, read as empty) and the provenance document carries them on
  the solver run. The four builders' tails (init, exec, analysis,
  export) are one `_script_tail`, so the seam exists once. A setup
  stating none changes nothing: the seven tier-3 matrices render
  byte-identical. RED on aff689e: the table refused as a key naming no
  solver setting, and no `RAW_TABLE`.
- **The tier-3 setup study gains a row carrying one raw line, for the
  licensed seat** (PFS-2033.03). Setup `s008` is the tour preset plus
  `SOLVER_SET_ITERATIONS 350` before init, over the preset's 300; row
  2004 of `matriz_setup.fs` states it, its golden is rendered offline,
  and the tier-3 test that reads the record, the script order, the loads
  spreadsheet's requested iterations and the provenance skips with its
  reason until the row runs on the licensed machine. `docs/tiers.md`
  counts eight setups and four rows of the study.

## [0.13.1] - 2026-09-09

### Fixed

- **`pyfs-matrix run` pre-flights a row on a second build under that
  build's grammar, as `plan` already did** (PFS-2009.05.02, met by pfs0130
  on the published 0.13.0 on 2026-09-09). The first fix (PFS-2009.05.01)
  reached `plan_matrix` alone: `pyfs-matrix plan` said READY and
  `pyfs-matrix run` refused the same matrix, whole, with
  `CommandNotInVersionError` for 26.120 on the row that named 26.123, so
  the matrix of the reference cases that states the unsteady actions on a
  second build could not run from the released package. One function,
  `_row_versions`, now feeds both pre-flights. RED on 7b20deb: MatrixError,
  pre-flight blocked 1 matrix point(s); the tier-1 test runs the two-build
  matrix on a stand-in solver and reads both records.

- **A nonzero sideslip under `SYMMETRY: MIRROR` is refused at plan time,
  naming the cell** (PFS-2005.09, met by pfs0130 row 4207 on 2026-09-09).
  MEASURED on 26.120: a script stating `SOLVER_SET_SIDESLIP -4.0` under
  mirror symmetry ran to completion at zero sideslip, the log reading
  "Symmetry is mirror." and then "Side-slip angle (Deg): .000", and the
  export printing .000; the run layer recorded the point
  FAILED_INCOMPLETE_OUTPUT because the export was evidence of another
  operating point, two seats after the plan had said READY. A mirrored
  half model is a valid model of the full one only while the free stream
  lies in the symmetry plane, and a nonzero sideslip takes it out of that
  plane, so the refusal is physics rather than grammar; the command
  database carries the fact
  on `SOLVER_SET_SIDESLIP`. RED on 7b20deb: 3 ready, 0 blocked.

## [0.13.0] - 2026-09-09

### Added

- **The geometry library reads one subfolder per geometry beside the flat
  layout, and a point's staged inputs show one geometry's files**
  (PFS-2032.04, the reading of 2026-09-08, design 68 section A3). The cell
  keeps saying `GEOMETRY: 30_WB.fsm`; the resolver looks for
  `inputs/geometries/30_WB/30_WB.fsm` first and `inputs/geometries/30_WB.fsm`
  second, so no matrix written since 0.11.0 changes and a library can hold
  both layouts. The boundary inventory `pyfs-matrix inventory` writes and
  the provenance record sit inside the folder when the geometry has one,
  the binding reads the sidecar from there, and a point staged from a
  folder is linked at that folder (PFS-2029.17's junction, pointed one
  level down), so `sims/<sim>/inputs` holds that geometry's files and
  never the whole library; the record still says `staged_as: link` with
  the file's sha256. A bare stem or an absent file is refused naming the
  geometries of both layouts, and the two sidecars are no longer offered
  as geometries a cell could name. The flat layout is not deprecated: the
  tier-3 library stays flat and is the control that nothing broke (every
  matrix READY, every golden equal), and the cycle that retires the flat
  form is for the owning seat to open once the folders have run a campaign.

- **`pyfs-workspace migrate-geometries <root>` moves a flat geometry library
  into one folder per geometry, idempotently** (PFS-2032.05). Every
  `inputs/geometries/<stem>.<ext>` moves to `inputs/geometries/<stem>/`
  with its `<stem>.boundaries.toml` and `<stem>.provenance.toml`; the
  command prints each move and each folder it left alone, a folder that
  already exists is not touched whatever it holds, a second run moves
  nothing and says so, and a root with no `inputs/geometries` is refused
  with exit 2 and nothing created. A workspace whose manifest records
  runs keeps working, because a record names its inputs by file name and
  hashes their bytes, and neither moved; a recorded simulation re-staged
  from the folder is re-pointed rather than copied. The Python surface is
  `pyflightstream.workspace.migrate_geometry_layout`, returning what
  moved and what was kept. Nothing migrates by itself, and the flat
  layout is not deprecated.

- **The products stage writes a PROV-JSON provenance document per recorded
  run** (PFS-2012.08, PFS-2012.08.01). The run record carried every fact a
  provenance document needs and lacked a shape another tool reads without
  reading this package's docs; the design decision of 2026-09-08 (design 68) is
  W3C PROV, serialized as PROV-JSON, one document per recorded run, a
  product and never a function a user calls on a record. `pyfs-matrix
  post` and the run's own products stage write
  `post/<matrix stem>/provenance/<run id>.prov.json`, every status, and
  `products.json` names each under `provenance` keyed by run id. Entities
  are every staged input, the script and every collected output with its
  sha256 under `pyfs:sha256`, an output's computed from the file when it is
  still there; the activity is the solver run with `prov:startTime`,
  `prov:endTime`, the wall time, the status and the executor's argv; the
  agents are the package at its version and commit and the solver build at
  its executable identity. For the start and end the run record gained
  `started_at` and `finished_at`, ISO 8601 in UTC, read off the executor's
  clock (`ExecutionResult` carries them; a stub that reports none leaves
  None), and adding them did not move the manifest schema. Standard
  library only; the tier-1 test reads the document back with a reader of
  a few lines and requires every relation to name a declared node.

- **The campaign stage writes the reference plot format beside the polar tables, and
  the format is specified against a committed sample** (PFS-2014.01.01,
  PFS-2014.01.02). The existing tooling opens a fixed-width text polar
  file; `[products] her_polar_format = true` on the pproc artifact writes
  `<polar>_M<code>_g<group>.dat` beside every `.csv` the stage writes, the
  same twenty-four columns a second time at `%10.5f`, and
  `pyflightstream.post.read_her_polar_format` reads it back. The shape was
  read off a recorded file and is pinned by
  `tests/tier1_offline/fixtures/her_polar_format_sample.dat`, every value
  of which is synthetic (the tour's wing at Mach 0.1); the writer's
  docstring names every line of the format and the tier-1 test feeds the
  fixture's rows through the writer and requires the fixture's bytes with
  the date line masked, then writes, reads and rewrites what the stage
  produced and requires equal bytes.

- **Every command-line option of every console script has chosen: it reads
  its default from the options registry or carries the reason it is not a
  knob** (PFS-2022.06.01, on the decision of design/68 section PFS-2022.06).
  FR-40's quantifier was "every user-facing option or parameter", a set
  nothing could enumerate; it is now "every command-line option", and
  `tests/tier1_offline/test_cli_options_registry.py` builds the parser of
  each of the five scripts named in `pyproject.toml` and holds each option
  to the rule. Six flags of `pyfs-qa` resolve through the three registry
  keys, which the test measures by moving a key and watching the default
  move; the other fifty-odd flags are allowlisted in the test with the
  reason beside each (the subject of the command, a case fact the manifest
  records, a mode switch, an output place, licensed material named per
  call). A new flag that does neither fails the suite in the commit that
  adds it. `pyfs-fsi` builds its parser in `_build_parser()` like the other
  scripts, so the test can enumerate it. The SRS is 1.33.0 and the
  requirement is marked; it stays pending on its Python-API half.

- **Names, not indices, on every boundary-citing surface, judged at plan
  time; and FR-30b carries a test at the matrix surface it claims**
  (PFS-2028.00). The RED of RPT-044: a pproc group citing the mesh solid
  name `Wing` against `14_WING_RENAMED.fsm`, whose inventory carries
  `MainWing` because the boundary was renamed before the save, planned
  READY, since a steady row's groups resolve at products time after the
  seat is spent. A row whose pproc artifact's groups cite no name the
  opened geometry carries is now BLOCKED at `pyfs-matrix plan` naming the
  row, the artifact, the names, the file and its inventory. What is refused
  is the artifact and the geometry sharing no name, not a member missing
  from one group: the tier-3 artifacts are written once and shared by rows
  opening different geometries, a family a file lacks is left out by
  design, and every tier-3 matrix still plans READY with every golden
  unchanged, which is the control. `MOVING_BOUNDARIES` accepts a group of
  the artifact as `g<number>`, resolved to the members the geometry
  carries and refused when it names nothing the file holds; a bare number
  is still a position, so the goldens that carry one are untouched. FR-30b's
  evidence now names `test_tier3_offline.py`, where a one-row copy of the
  tour plans `MOVING_BOUNDARIES: Blade1,S` on the pusher row against its
  inventory sidecar and is refused as the sidecar says, `Blade1` and `3`
  both moving the third boundary.

- **A key no run type registers is refused at plan time, naming the row, the
  key and the keys the run type does register** (PFS-2008.02.01, the rule of
  2026-09-08 recorded in design 68: a row states only what the script will
  carry). Each run type carries its vocabulary on the `Workflow` object
  (`keys`, beside `commands`), the wider types extending the narrower, and
  each builder refuses a row stating a key outside it after its own
  refusals and before its first emission, so a rotor key on `unsteady` and
  an export threshold on `steady` keep the sentences that say why. Measured
  before the change: a one-row copy of the tier-3 tour with `FOO_BAR: 1`
  appended planned READY, and the run would have spent a seat on a row
  stating something the script does not carry. A key another run type
  reads is named with that type (`WINDOW_DEGREES (a key of unsteady,
  unsteady_rotor)` on a `steady` row); a LEGACY row keeps its free keys,
  because its RECIPE is their reader, and the tour's own LEGACY row with
  `FOO_BAR: 1` appended plans READY. `VELOCITY` is registered and
  unreachable from a matrix row (the flight condition resolves the
  velocity first), and `MOTIONS` moved home to `cases.workflows` so the
  rotor run type could register it; `cases.matrix` re-exports it.

- **A boundary renamed in the solver before the save reaches every export by
  its new name, measured** (PFS-2007.01, RPT-044). The tier-3 library gained
  `14_WING_RENAMED.fsm`, the tour's wing with `SURFACE_RENAME 1 MainWing`
  applied by the preparation script before the save; its inventory sidecar,
  read off the file's own mesh block, carries `MainWing` and not the mesh
  solid's `Wing`. Row 4004 of `matriz_geometry.fs` cites `MainWing` through
  a pproc group and nothing else: the loads table, the log and the saved file
  of the run say `MainWing`, the mesh name appears nowhere, the products stage
  resolved the group by it, and the lift equals the plain wing's to every
  printed decimal. The same measurement showed that a group citing the mesh
  name plans READY, since groups resolve at products time; that is
  PFS-2028.00's ground and is recorded there.

- **The unsteady run types' plots export is measured through the workflow,
  and the three plot commands have a coupled probe specification written
  from it** (PFS-2015.02.01). Every recorded point of an `unsteady` or
  `unsteady_rotor` row in the tier-3 workspace names one `_plots.txt`, the
  file is present at that path and says the solver ran unsteady
  (`test_tour.py::test_every_unsteady_row_left_the_plots_export_its_record_names`);
  tier 1 holds that every rendered unsteady script exports it under the
  record's name. `UNSTEADY_SOLVER_NEW_FORCE_PLOT`,
  `UNSTEADY_SOLVER_NEW_FLUID_PLOT` and `UNSTEADY_SOLVER_EXPORT_PLOTS` enter
  the probe catalog as one coupled specification in the shape the rows
  measured: the definition before `INITIALIZE_SOLVER`, the export after
  `START_SOLVER`, the exported file carrying the plot by name as the effect.
  The catalog holds 112 specifications, 90 of which render their target
  line in isolation.

- **The thirteen solver-setting emitters of the rotor path are measured on
  every build this machine holds** (PFS-2028.02, RPT-043). `matriz_builds.fs`
  states the tour's one-blade periodic row once per build, 7001 on 26.120 and
  7002 on 26.123, both CONVERGED through `pyfs-matrix run`; `test_builds.py`
  asserts each row ran terminal on the build it names, that every one of the
  thirteen reached the script the solver received, that the log names no
  error for any of them, and that the database says `verified` on that build
  citing the sweep's compat report (`reports/compat/CMP-<build>_2026-09-08_rotor-path`),
  from which `pyfs-qa apply-compat` promoted 13 statuses on 26.120 and eight
  on 26.123, the five already verified there keeping their earlier probe
  citation, which the tool now does by construction (a verified row is
  corroborated by a later verified report, never re-cited). 26.121 and
  26.122 are named as not covered: no executable of theirs is registered here.
  The sweep was the known gap the 0.10.0 note recorded.
- **Repository guard: a spreadsheet cannot enter the public tree**
  (OPS-2010.23). The geometry guard keys on the extensions a mesh travels in
  and says itself what it cannot see: coordinates in a generic container. A
  spreadsheet (`.xlsx`, `.xlsm`, `.xlsb`, `.xls`, `.ods`) is that container,
  opaque to a diff and to a review, and measured before the guard existed a
  `.xlsx` staged under `examples/` passed every pre-commit hook. A
  `forbid-spreadsheets` hook refuses the class at commit time and a tier-1
  walk over every tracked path refuses it in the suite, with a mutation
  proof that restores the defect and watches the guard deny; the allowlist
  beside it takes an entry only with the reason written, and was measured
  empty. `.csv` stays allowed: it is text a reader can check.

- **`pyfs-workspace archive <root> <sim_id>` zips one recorded simulation
  under `archive/`** (OPS-2009.01.10). Two refusals already told the user to
  run it: collecting onto a name already in `raw/`, and starting a point
  whose declared output is already in the simulation folder, both say to
  archive the simulation and re-run, and the command they named was not
  there. It is `CampaignWorkspace.archive_sim` from the terminal and nothing
  more: a simulation the manifest does not record is refused by name with
  exit 2 and nothing written or deleted, as is a campaign root without
  `runs.json` and an archive name already taken. Both refusal messages now
  spell the whole command. The workspace page carries the worked example,
  which the suite runs on a recorded and on an unrecorded simulation.

- **The deprecation ledger holds a parameter, a flag, a manifest key and a
  matrix column, not only a module** (PFS-2021.07.01).
  `pyflightstream._deprecations` gained `DeprecatedParameter`,
  `DeprecatedFlag`, `DeprecatedManifestKey` and `DeprecatedColumn` beside
  `DeprecatedModule`, each carrying the old name, the new name, the
  release that introduced the shim and the removal version, and
  `DEPRECATIONS` enumerates every live promise of every kind. The Tier 1
  deadline guard judges each of them through one checker,
  `expired_promise`, which is the red this item was built on: the guard
  iterated modules alone, and a promise of any other shape could not be
  refused because it could not be recorded. Every shim builds its warning
  text from its entry, so the release a warning names and the one the
  guard enforces cannot disagree. The two promises that said "a future
  release", the `fs_version=` keyword of `plan_matrix` and the
  `vorticity_drag_boundaries=` parameter of `analysis_setup`, joined the
  ledger the same night naming 1.0.0; see the PFS-2021.02 entry below.

- **The run record carries how the solver was called, and the evidence
  reports read it rather than assert it** (PFS-2012.04). `RunRecord`
  gained `executor`, the executor's class name with the argv it ran, read
  off the executor and its result by `pyflightstream.run.invocation_record`
  once the point has run, and `export_window`, the unsteady export window
  as resolved for the point, which is `None` for every row this version
  writes because no row key states one yet (PFS-2031.18 fills it). Both
  default to `None`, a manifest without them reads, and neither moved
  `MANIFEST_SCHEMA`. The probe, physics and drift runs record the same
  fact off their own solver calls, and `describe_invocation(record)` builds
  the executor sentence of a compat, drift or physics report from it,
  marked `as run`; a run with no record keeps the asserted sentence, which
  is the stated fallback and is what every report written before this
  release carries.

- **The campaign products stage writes every reduction of an unsteady
  point beside its plots table, over the window the row states**
  (PFS-2015.04, PFS-2015.03, OPS-2008.01). The four reductions existed as
  library functions since 0.8.0 and nothing on the campaign path called
  them; under the rule of 2026-09-08 that every capability enters through
  the workflow, `pyfs-matrix run` now resolves the windows off the row when
  it writes the run record (`reductions` in `runs.json`, from
  `pyflightstream.cases.workflows.reduction_windows`), and the products
  stage, run by `run` and by `pyfs-matrix post` alike, writes
  `plots/<point>_time_average.csv`, `plots/<point>_phase_locked.csv` and
  `plots/<point>_per_blade.csv` beside `plots/<point>_plots.csv`, each named
  in `products.json` with the reduction and the windows it used. The time
  average is over the export window the row states, else a rotor row's last
  revolution, else a rotorless row's whole run; the phase-locked passages
  cut that window into blade passages; the per-blade split is the last
  revolution, one window per blade, as `ReductionPlan` already defined it.
  Raw is the plots table itself, written once. A reduction the row cannot
  window (no `BLADES`, a run shorter than one revolution, a plots table
  shorter than the window, a record written before the field existed) is
  recorded under `skipped` with the reason, keyed by the file it would have
  been; a rotorless point lists no passage reduction at all. The plots table
  is written first and the reductions are read off the written file, which
  is PFS-2015.03's rule (a reduction ships beside the history and never in
  its place) kept by construction and now proved:
  `test_the_reductions_sit_beside_the_plots_table_and_never_replace_it`
  reads the table byte-identical before and after the reductions. And the
  seventh propagation test of the far-field ledger,
  `test_a_missing_sample_poisons_the_harmonic_in_plane_moment_product`,
  turns red when the harmonic in-plane-moment branch stops propagating a
  missing sample; it is written at the reduction's own seam because the
  products stage carries no far-field product yet, and the test says so.

- **Exports that begin after a threshold the row states** (PFS-2031.18,
  the design of 2026-09-08, GeoversePlan design 67). Two row keys enter the
  vocabulary of the two unsteady run types, `EXPORT_UNSTEADY_AFTER_REV` on
  `unsteady_rotor` and `EXPORT_UNSTEADY_AFTER_ITER` on both, one per row at
  most and refused on a steady row. A row stating one registers two unsteady
  solver actions before the solver is initialized: a `COMMAND_LINE` running a
  counter program the run layer writes into the point's `actions/` folder,
  which counts its own invocations, derives the azimuth and the revolution
  from the count with the step in degrees and the rotor speed written into
  it, and rewrites the second action's file; and a `SCRIPT` pointing at that
  file, empty until the count reaches the threshold and carrying the export
  of every per-step kind of the row's output set from then on. The scheme
  rests on the five facts RPT-041 measured on 26.123: the SCRIPT file is
  re-read on every invocation, the count is the step count exactly, the
  action gets no arguments and no solver-named environment, it runs from the
  simulation folder, and the solver stamps `_iteration=N` on each export.
  The run record names the two files as `action_program` and
  `action_script`, hashes them in `inputs_sha256`, and keeps in
  `action_count` the count the program reached. Row 6002 of
  `tests/tier3_licensed/matriz_actions.fs` runs the `unsteady` type with
  the threshold at iteration 4 of 8 on 26.123; its golden is new and no
  other moved. The row RAN on 26.123 the same night (RPT-045):
  CONVERGED, count 8, 25 stamped exports for iterations 4 to 8 and none
  before, and the four things design 67 left unmeasured are measured, all
  four as the design assumed; `test_actions.py` reads the run back.

- **`tests/tier3_licensed` is a campaign workspace, run on the licensed
  machine, with one test per row** (PFS-2031.03, PFS-2031.05, PFS-2031.07,
  GOAL-012). Seven run matrices over a synthetic library of nine saved
  simulations: the tour (`matriz.fs`), which states every column, every key,
  every run type and every input kind the package reads; a setup study, a
  time-step study and a geometry study; the qa physics cases PHY-01, PHY-02,
  PHY-05 and PHY-06 as rows of `matriz_physics.fs`, reduced with the
  functions of `pyflightstream.qa.physics` and judged against the same
  committed references; and the action re-read probe. `test_tour.py`,
  `test_studies.py`, `test_physics.py` and `test_actions_probe.py` read the
  manifest, the script each solver received, the loads and the products,
  and assert per row what the cell was meant to reach. Tier 1 keeps the
  offline control: every matrix plans READY and every rendered script equals
  its golden, and seven plan-time refusals are asserted over a copy of the
  library, six one-row matrices and one second matrix stating a POL the tour
  states. The new page `docs/tiers.md` walks it; the README, CONTRIBUTING
  and the guide name the three tiers by their folders.

- **A `LEGACY` row may name its recipe in the cell**, as
  `RECIPE: package.module:function`, and then plans and runs with no
  `--recipe` option, which is what FR-50 promises of a matrix. A bare code
  is still mapped by the option, and a mapping given for the same string wins,
  so nothing a user mapped changes meaning (PFS-2031.11). Found by the first
  matrix of the tier-3 workspace, whose preparation rows carried the whole
  reference and could not be planned without repeating it on the command line.

- **A flat rotor row may name its hub by a reference point**, `ROTOR_ORIGIN:
  ERP1`, exactly as a `MOTIONS` record has since 0.11.0: the point's
  coordinates are bound from `inputs/reference_points.toml`, the name stays
  beside them as `ROTOR_ORIGIN_POINT` in the case and the run record, and a
  point that is not an engine point is refused naming its kind (PFS-2031.12).
  Found by the tier-3 tour's installed rotor row, which was refused with
  "a rotor hub is three coordinates" for the same cell a two-rotor row accepts.

- **`pyfs-matrix post` takes the matrix whose products to rebuild**, and with
  none given rebuilds every matrix the manifest names (PFS-2031.04). Its
  `--strict` flag makes a product skipped by design exit 3, a code of its
  own beside 2 for a refusal, after every product is written; without it a
  recorded skip is printed and the exit is 0, since everything producible was
  produced (the design decision of 2026-09-08, PFS-2031.19). `pyfs-matrix run`
  prints the same skip lines at the end of the run, so the surface that spent
  the seat is not silent about them.

- **A workspace kept in version control runs on this machine through
  `inputs/executables.local.toml`** (PFS-2031.15): the committed registry
  carries placeholder paths, because an installation path is machine
  configuration, and the gitignored overlay beside it supplies the real path
  of a build id. A bare local path keeps the committed entry's declared
  version, a local table replaces the entry, a build id the overlay is
  silent on reads as committed, and a build id the committed registry does
  not declare is refused naming both files, so a row cannot run on one
  machine and be unregistered on another from the same tree. A refusal
  about an entry names the file the entry came from. Found by the tier-3
  tour, whose second-build
  row could reach the second installation only through the override, which
  overrules every row.

- **A POL stated by two matrices of one workspace is refused at plan time**,
  naming both files and both rows: a POL names the simulation folder and the
  run ids of the one manifest, so each matrix of a workspace states its own
  (PFS-2031.04).

### Changed

- **`utils.ManualCallError`, in the catalogue**: `propose_type` called with the
  wrong argument shape raised a bare `TypeError` after its keyword-only
  change (PFS-2022.05), which the FR-39 ratchet refused; the class keeps
  `TypeError` as its base so an existing `except TypeError` catches what it
  caught before.

- **Two type-check exemptions retired, `qa.cli` and `qa.physics`**, which the
  physics rewrite (PFS-2031.17) left clean under the strict configuration;
  the exemption recount of RPT-029 is re-measured for 2026-09-09 and its four
  records move together. The command census moves with RPT-043's promotions
  (26.120 from 66 to 79 verified rows, 26.123 from 84 to 92), and a verified
  row measured through a workflow row counts as re-measurable by that row.

- **An enum's `values` list is the accepted vocabulary, in every chapter**
  (PFS-2003.03). One entry listed the letters and the digits its page
  accepts for an axis while ten neighbours listed the letters alone, so the
  field meant "what the solver takes" in one file and "what the library
  offers" in another and the rule in force was unwritten. It is written now,
  in `docs/srs/data-model.md` and on `ArgSpec.values`: `values` is
  everything the manual page states or samples for the argument, because
  the emitter reads it to refuse and a refusal of a token the solver accepts
  is a false refusal; a narrowing the library chooses belongs to the helper
  that offers it, and the field such a narrowing would take, `offered`, is
  named without any entry needing it. Measured on 2026-09-09, the only enums
  mixing names and digits are the six of the axis family, and
  `tests/tier1_offline/test_command_db_grammar.py` now pins both halves of
  that family (six with the index form, ten with letters alone) so a reading
  that moves one costs a line. No status or evidence field changed.

- **The Python and dependency window follows SPEC 0; Python 3.11 leaves it,
  and numpy and pandas gain floors** (PFS-2024.07). `requires-python` was
  `>=3.11` since the first release and the numerical dependencies carried no
  floor, so a user reading the window to learn whether their environment
  is supported could see it and not how it would move. The window now
  follows the scientific-python community schedule (three years of support
  after a Python version's initial release, two after a core package
  version's), computed on 2026-09-09 and stated beside the floor in
  `pyproject.toml`: Python 3.12 (3.11 left the window in 2025-10), numpy 2.2
  and pandas 2.3, neither above the versions this tree runs with; pydantic
  declares the major its API is written against, and xarray's floor waits
  for the next date move because its oldest in-window release leaves the
  window two days after the computed date. The CI matrices, the ruff target
  and the classifiers follow the same line, the one `sys.version_info`
  branch the 3.11 leg needed is gone, NFR-05 says how the floor moves, and
  `tests/tier1_offline/test_support_window.py` re-derives every floor from
  the release dates and the stated date so the schedule overtaking the
  declaration fails the suite. Decision to adopt SPEC 0 taken in the
  session's seat under the delegation recorded for 2026-09-08.
  ANNOUNCEMENT, for NFR-21: 3.11 is dropped in this release without a
  release before it saying so; NFR-21 is pending and this entry is the
  announcement it asks for. No leg runs 3.13 or 3.14 yet, so no classifier
  claims them; SPEC 0 holds both inside the window.

- **`sweep_editions` is `manual_editions`, and `propose_type` takes its two
  strings by keyword; `probe_ref` stays** (PFS-2022.05). The maintainer
  function that reads every registered manual edition was named for the
  motion of reading, and `sweep` is the solver's own word for a parameter
  sweep (`SWEEPER_START`, the `sweep` run type), so one word meant two
  things in one library. The old name warns from the ledger and forwards
  until 0.15.0; the `pyfs-manual sweep` subcommand keeps its name and its
  help line now says it reads the manuals. `propose_type(placeholder,
  description)` took two adjacent strings positionally and nothing at the
  call site said which was which: both are keyword-only, and a positional
  call warns from the ledger and still answers until 0.15.0. `probe_ref`,
  the third name the node measured, is a committed YAML key of the command
  database on both the entry and the version row, with no Python-side name
  apart from the key; it is deliberately not renamed, and the ledger comment
  records why.

- **The two deprecation warnings that promised removal "in a future release"
  now name it: both shims stay until 1.0.0** (PFS-2021.02).
  `analysis_setup(vorticity_drag_boundaries=)` and the `fs_version=` keyword
  of `plan_matrix` and `run_matrix` warned without a version, which the
  deprecation policy of NFR-20 forbids from 1.0 and which no test could hold
  to a date. Each is now a `DeprecatedParameter` row of the ledger
  (`pyflightstream._deprecations`) with `removal_version` 1.0.0, the warning
  text is built from the row, and the tier-1 deadline guard judges them with
  every other promise. The decision to keep them until 1.0.0 rather than
  pick an earlier minor was taken in the session's seat under the
  delegation recorded for 2026-09-08 and is recorded beside the entries: each
  shim is a keyword that forwards to its replacement, so removing it earlier
  saves nothing and costs an outside caller a release they were never told
  about. Nothing changes for a caller except the sentence they read.

- **A simulation folder has three managed subfolders, and `parsed/` is no
  longer created** (PFS-2032.01). `CampaignWorkspace.create_sim` makes
  `inputs/`, `scripts/` and `raw/`; the fourth folder existed from the first
  release and nothing in the package ever wrote to it, since the typed
  extracts it was named for are built at campaign level under
  `post/<matrix stem>/`. A workspace made by an earlier release may still
  carry an empty `parsed/` beside each simulation: it is left where it is,
  nothing refuses it, and it travels into the archive like any other
  unmanaged subfolder. The data-model page and the docstrings list three
  folders.

- **The waived-command surface says waived** (PFS-2022.01.05,
  OPS-2009.02.08). The entries a run manifest held under `broken_commands`
  are waivers, commands the database records broken that a recipe emitted
  anyway under `Script.allow_broken`, and the key read as the commands
  that broke in the run, which is the opposite claim. The manifest key
  `pyfs-matrix run` writes is `waived_commands`, and so are
  `Script.waived_commands`, `PointPlan.waived_commands` (with the
  `plan.json` key) and `RunRecord.waived_commands`; each old name reads
  until 0.15.0 with a DeprecationWarning built from its ledger entry, a
  manifest written under the old key reads the same way, and a row
  carrying both spellings is refused. `MANIFEST_SCHEMA` moved to
  `pyfs-manifest/3` because the rule on that constant says a removal bumps
  it and a key no longer written is a removal: a reader of "2" that
  tolerates unknown keys would read a row with no `broken_commands` as a
  run that waived nothing. Every stamp from `pyfs-manifest/2` on still
  satisfies the waiver writer's stamp arm, named apart as
  `SOURCE_VERSION_REQUIRED_SINCE`, so a row stamped "2" is not refused as
  the layout in which `source_version` was optional.

- **`pyfs-qa physics` reads the workspace, and the hand-built physics
  builders retire** (PFS-2031.17, the design decision B of 2026-09-08 in
  design study 66). `pyfs-qa physics --workspace <root>` runs the
  workspace's `matriz_physics.fs` through the run layer exactly as
  `pyfs-matrix run` does, reduces the records with the reductions of
  `pyflightstream.qa.physics` (`phy01_metrics`, `phy02_metrics`, and the
  new `phy05_metrics` and `phy06_metrics`, which the tier-3 test carried
  inline until now) and writes the same `reports/physics/PHY-*` pair, with a
  `Source` row naming the matrix and the workspace; `--resume` on a
  workspace whose matrix already ran executes nothing and reports what
  `runs.json` holds, which is the form for the tier-3 workspace after
  `pyfs-matrix run`. `pyfs-qa drift --workspace <root>` is two runs of the
  same matrix, one workspace per side under `--workroot` with an
  `executables.local.toml` overlay naming that side's executable, and a diff
  of the two reductions inside the case bands (`DRF-*`). The row names its
  case at the head of its DESCRIPTION (`PHY-01_...`), and the package makes
  the link: PHY-02 is the full-span row and the row under `SYMMETRY
  MIRROR`, PHY-06 is its own unsteady row against the steady polar of the
  PHY-01 row. BREAKS: `build_phy01_script`, `build_phy02_script`,
  `build_phy05_script`, `build_phy06_unsteady_script`, `run_physics`,
  `run_drift` and `PhysicsCase.runner` are gone, and the `physics` and
  `drift` subcommands lost `--fs-version`, `--fs-exe` (physics), `--cases`,
  `--workroot` (physics), `--timeout` and `--smi-root` for `--workspace`,
  `--matrix`, `--name` and `--resume`. The SMI class keeps its script
  builder, specifications and references and has no runner until it is a
  row of a private workspace. WHERE THE DRIVER LIVES,
  `pyflightstream.qa.matrix`, is the decision the study said the design
  settles first: the study feared that reading the workspace inverts the
  direction, "qa sits below workspace", and the package's own layer table
  (`pyflightstream.overview._CORE_LAYERS`, asserted by
  `tests/tier1_offline/test_conventions.py`) puts qa on the top row beside
  post, above run and workspace, with the qa package already importing both
  at module level before this release; so the driver's imports point down,
  and `tests/tier1_offline/test_qa_matrix.py` measures that no module of a
  lower row imports qa back. RPT-042 is the measurement that the workflow
  rows reproduce every coefficient of the hand-built scripts inside the reference
  bands, which is what made the second builder redundant. The first report written this way from the tier-3 workspace, with no seat spent, is
  `reports/physics/PHY-26120_2026-09-09`: 30 pass, 0 warn, 0 fail on 26.120,
  the same four cases the hand-built scripts judged.

- **Each matrix of a workspace keeps its own plan, sweep table and products
  under `post/<matrix stem>/`** (PFS-2031.04). `plan.json` moves from the
  workspace root to `post/<stem>/plan.json`, the default `sweep.csv` of
  `pyfs-matrix run` from the root to `post/<stem>/sweep.csv`, the run's own
  `campaign_sweep.csv` from `post/` to `post/<stem>/`, and the product tables
  with `products.json` from `post/products/` to `post/<stem>/`. `runs.json`
  stays the one manifest, and every record now names the matrix its point
  came from (`matrix_stem`, named so on the design decision of 2026-09-08 to stay
  apart from `DerivedFrom.matrix`, the path a conversion read; the field had
  been `matrix` for one day of the 0.13.0 development line and no release
  carried it, PFS-2031.20), which is what `sweep_table(..., matrix_stem=)` and
  `write_campaign_products(..., matrix_stem=)` filter by, and both refuse a stem
  the manifest never recorded naming the stems it does; `pyfs-matrix post`
  refuses the same way, and refuses an empty manifest naming `runs.json`.
  A campaign authored in Python or loaded from a file has no matrix and
  keeps the previous places, which `CampaignWorkspace.plan_dir`, `sweep_dir`
  and `products_dir` state in one place. A registered post stage is now
  called with a third keyword, `matrix_stem`, which moved with the field; a
  stage written to the earlier two-argument shape fails with a `TypeError`
  naming it, and `register_post_stage`'s contract says so. A manifest or a
  campaign file written on the one day the field was called `matrix` still
  reads: the old key is taken as the new one.
  The reason is the tier-3 workspace, which holds seven matrices over one
  library and could not keep their tables apart.

- **The test suite is organized by tier**, explicitly: `tests/tier1_offline`
  runs without a solver and is what `pytest` runs by default,
  `tests/tier2_validity` holds the per-command probes and
  `tests/tier3_licensed` IS a campaign workspace run on a licensed solver;
  both licensed tiers carry `needs_flightstream` on every module. Every
  existing module moved into tier 1 with `git mv` and changed in no other
  way; the paths that cited them followed. The reason is GOAL-012: every
  capability of the run matrix becomes a row a fresh clone can plan and a
  licensed seat can run, and tier 3 is the worked example of how each one is
  set through the workspace.

### Fixed

- **The release review of 0.13.0, round one: five lenses over
  237a47a..83d856a, thirty-three findings, twenty-six fixed here, two
  registered for 0.14.0, five questions to the owning seat** (the round ledger
  REL-0130 in the coordination tree). What moved in the package:
  `apply-compat` never replaces the citation of a row already `verified`
  elsewhere, the new report corroborates it (outcome `corroborated`, counted
  apart from promotions), and the five 26.123 rows of the rotor-path sweep
  carry their 2026-08-17 full-sim citation again (RPT-043 amended); a
  physics matrix whose one-row case is named by two rows is refused BEFORE
  the run by `physics_rows`, at plan time in both drivers and `pyfs-qa
  physics`, where the refusal had sat in the reduction after every seat was
  spent, and the two-builds test now measures the manifest empty; the record
  of an unsteady row carries the resolved export threshold in
  `export_window` (`stated_form`, `stated_value`, `first_step`,
  `time_iterations`), which had shipped permanently None under a comment
  calling it future work; a name 0.13.0 removed from `qa.physics`
  (`run_physics`, `run_drift`, the four `build_phy*_script`) answers an
  import with the release that removed it and the workspace call that
  replaced it, rather than a bare name error; a `MOVING_BOUNDARIES` token
  spelled as a group is refused as a group problem, naming the missing
  PPROC artifact or the groups the artifact carries; `pyfs-workspace
  migrate-geometries` takes the current directory when no root is given;
  `her_polar_file_name` takes `mach` and `group` by keyword only. What the
  tests gained: the emitted counter program is loaded as a module and its
  first exporting step compared with the package's `first_step` in every
  threshold form (the revolutions branch had been executed by nothing at any
  tier, two mutants survived); `propose_type`'s two `ManualCallError`
  refusals asserted; the forbid-spreadsheets hook's suffix pattern compared
  with `SPREADSHEET_SUFFIXES`. What the prose gained: the guide's Python
  floor, NFR-27's example and NFR-05's evidence line follow the declared
  floor; seven matrices everywhere a live sentence counts them; the
  PFS-2021.07.01 entry no longer says two promises sit outside the ledger;
  the moment point's frame on `ReferenceValues`; `test_support_window`'s
  docstring says the stated date is frozen on purpose.

- **A row on a second build is pre-flighted under that build's grammar**
  (the residual PFS-2009.05 left, met while pfs0130 was written on
  2026-09-09). `pyfs-matrix plan` validated every point under the campaign
  default, so a row on 26.123 in a matrix whose default is 26.120, stating
  the unsteady actions, was BLOCKED with `CommandNotInVersionError` for a
  build the row never named, and would have run. The plan now reads each
  named build's version off the registry, with no executable bound, and
  validates the row against it; a build whose entry declares no version is
  pre-flighted under the default, which is what its scripts run under.

- **A pproc group named by a word is refused at plan time, naming the
  artifact, the key and the polar table the number is for** (PFS-2032.03).
  `polar_file_name` writes the group NUMBER into the polar table's name
  (`<polar>_M<mach>_g<number>.csv`), so an artifact whose `[groups]` table
  was keyed `wing` planned READY and stopped the whole products stage with a
  bare ValueError, outside the skip mechanism and after the seat was spent
  (measured 2026-09-08). `resolve_matrix` now refuses it at binding for every
  row whose artifact writes polar tables, and an artifact whose groups are
  for something else says so with `products.polars = false`. The shape stays
  free: `expand_group` numbers a group's members by the group's own name
  and reads no polar. The tier-1 fixtures that carried `wing` and `body`
  groups are keyed `"1"` and `"2"` now, which is what they encoded wrongly.

- **A top-level `base_regions` list in a pproc artifact is read as the
  documented off switch** (PFS-2005.04). The reader refused `base_regions =
  []` at the top level as a groups file of before 0.11.0, the bare-list
  check that tells the old shape apart, while the docs page showed exactly
  that form; measured 2026-09-08. The one top-level list the pproc shape
  itself defines is exempt from that check, so the empty list plans READY
  and `base_regions = ["Base"]` reaches the script as one
  `DETECT_BASE_REGIONS_BY_SURFACE` per boundary of the family; a bare list
  under any other key is still the old shape and is still refused naming
  the migration. The docs example placed the key UNDER `[groups]`, where
  TOML makes it a group named base_regions; it sits above the header now,
  and a tier-1 test resolves the documented block off the page.

- **An axis printed as a digit on the manual page is accepted as an
  integer, and the refusal names every spelling** (PFS-2003.04). A caller
  transcribing `CAD_BODY_ROTATE 1 2 15.0` off the page had two integers and
  a float in front of them and exactly one of the integers had to be
  written in quotes; the refusal listed `2` among the accepted values and
  then rejected the integer 2, naming no remedy. The emitter now accepts an
  integer that prints as a listed digit and prints it as that digit, on
  every one of the six axis arguments whose page takes the index form
  (`CAD_BODY_ROTATE`, `CAD_CREATE_ROTATE_CURVES`, `ROTATE_COORDINATE_SYSTEM`,
  `SURFACE_ROTATE`, `SET_MOTION_ROTOR_AXIS`, `CREATE_AXIAL_VORTEX_SEPARATION`);
  a value outside the set is refused by a message that lists the letters
  and the digits and says a listed digit may be passed as an int. A bool is
  not an integer here, and an enum that lists no digit still refuses one.
  The getting-started page shows the transcribed line, and the same
  calls are exercised in tests/tier1_offline/test_script.py.

- **The data-model page and the workspace docstring name `pproc/` as the
  fourth input kind, not `groups/`** (PFS-2032.02). The kind has been `pproc`
  since 0.11.0 and two pages still listed the old folder, because nothing
  read them back against the package. A tier-1 test now parses the folder
  tree of `docs/srs/data-model.md` and requires the kinds it lists under
  `inputs/` to be exactly `pyflightstream.workspace.INPUT_KINDS`, in order,
  so the next rename moves the page in the same commit or goes red. The
  history paragraphs that say the folder was renamed stay as they are.

- **`campaign.toml` stores the resolved build identifier, never the vendor
  name the row typed** (PFS-2009.04). The campaign model resolved the version
  a user wrote and then stored what they wrote, so a matrix converted with a
  vendor name such as `26.0` wrote `26.0` into the file, and the day a second
  build claimed that name the file was refused on a machine where nothing
  changed but the installed package, in a file its owner never edited (that
  day came for `26.1` on 2026-08-04, when 26.101 was registered). The model
  now keeps the canonical identifier the validator resolves, so
  `pyfs-matrix convert` writes `fs_version = "26.000"` for a row typing
  `26.0`, whether the name arrives as the default or as the first active
  row's `FS_BUILD`, and `pyfs-matrix plan` on that file reads the same build
  on the day the alias is reused. The `matrix_fs_build` variable keeps the
  cell as typed: it is the key a workspace resolves through its own build
  registry, and a registry key is not required to be a version.

- **A manifest whose snapshot marks a selection flag explicit with an empty
  selection is refused where the manifest is read, naming the manifest, the
  run and the flag** (PFS-2012.01). No run writes that record, since the
  curated helper refuses an empty selection before the script exists, so a
  manifest carrying one was edited or written by hand; replaying it through
  `script_from_setup` reached the helper's own refusal, which told the reader
  to omit an argument nobody wrote. `read_manifest` refuses the row naming
  `runs.json`, the run id and the flag by command and keyword, and
  `SolverSetup.explicit_kwargs` refuses the snapshot naming the flag, and
  neither names an argument for removal. There is no `pyfs-matrix`
  subcommand that regenerates a script from a record; the regeneration path
  is `pyflightstream.script.solver_setup.script_from_setup`, and the reader
  is where a hand-edited row is judged.

- **An empty list for an entity-selecting key of a setup or pproc artifact
  is refused at plan time, naming the artifact file, the key as the file
  spells it, and what the empty list would have disabled** (PFS-2005.02). A
  setup stating `vorticity_drag_boundaries = []` planned READY, because the
  reader accepted the list and a LEGACY row's recipe never read it; a pproc
  group `"1" = []` was refused by the model naming the file and the group
  and not what the group feeds. Both readers now consult one table,
  `pyflightstream.workspace.inputs.ENTITY_SELECTIONS`, which carries per key
  the command or product the list feeds and the domain seat's verdict on an
  empty list: refused on the manual's word for the induced-drag selection
  and for the families of a plot group or a section distribution, admitted
  for `base_regions` (its documented off switch), and "domain seat, not yet
  decided: refused until the owning seat says" for a group, which is this package's own
  concept and one the manual has no sentence about. The refusal prints the
  verdict beside the key.

- **The tier-3 goldens are the same file on Windows and on Linux.** CI on
  Linux measured every tier-3 golden as differing from its render, because a
  golden written on Windows carried the backslash in its placeholder paths;
  the portable form now writes those paths with forward slashes on every
  machine, and the 44 goldens were regenerated.

- **The run writes the child script of a `SCRIPT` action before the solver
  starts** (PFS-2031.13). `helpers.unsteady_action` has parked the child
  script "for the run layer to write" since 0.8.0, and nothing in the run
  layer wrote it, so a `SCRIPT` action registered through the helper named a
  file that was never there. The run now writes every parked script where
  the registration line names it, relative to the simulation folder, right
  after the point script and before the executor is called. Found by the
  tier-3 action re-read probe row, the first script in this repository to
  register one.

- **A product refused by design no longer costs the other simulations their
  products** (PFS-2031.16). The polar under sideslip is refused, as before,
  because its wind-axis columns are checked at zero sideslip only; until now
  that one refusal aborted the products stage of the whole run, and the
  tier-3 tour's sideslip row left the nine rows after it without a table and
  the workspace without `products.json`. The refusal is now a `skipped`
  entry of `products.json` carrying the reason, warned about and printed by
  `pyfs-matrix post`, and every other simulation's products are written;
  the `skipped` key is always present, empty when nothing was refused. An
  existing product without `--overwrite` still stops the stage, as its own
  `ProductExistsError`.

- **An executable override with no default version is refused naming the
  option** (PFS-2031.14). `pyfs-matrix plan <matrix> --fs-exe <path>` over a
  matrix whose every row names a build ended in a bare `StopIteration`: the
  override overrules the cells and nothing was left to say which version to
  build for. It is now a `MatrixError` naming the matrix, the override and
  `--fs-version`. Found by the first pre-flight of the tier-3 actions matrix
  on the licensed machine.

## [0.12.0] - 2026-09-04

### Added

- **A setup artifact may carry the campaign's fluid constants**, in a
  `[flight_condition]` table, so a row states only what varies from point to
  point. The five pins of v0.11.0 keep working exactly as they did on a row,
  and a row that states one overrides the setup's; a row that states none
  inherits it. The reason is repetition: a thirteen-point polar repeats the
  same four numbers thirteen times down the `FLIGHT_CONDITION` column, and one
  mistyped digit on one row is then a physics nobody selected on that row
  alone. The table holds the pins and nothing else: `MACH`, `TASmps` and
  `REmi` are what a point IS and are refused there with that reason, and
  `ALTFT` and `dISA` locate a point in the atmosphere the pins exist to
  replace. A setup pinning `RHOkgm3` under a row stating `REmi` has that one
  default dropped rather than refused, since the row has determined the
  density itself. The run record gains `flight_condition_defaults`, the pins
  that came from the setup with their values, and
  `flight_condition_defaults_from`, which names the setup by id AND path, so
  a record stays recomputable once the constants leave the row. Pin names in
  that table match **case-insensitively**, exactly as they do in a
  `FLIGHT_CONDITION` cell and for the same reason: `MUPas`, `ASMPS` and
  `TASmps` carry internal capitals a user types from memory, and one
  vocabulary may not have two matching rules. Two spellings of one pin are
  refused as one pin stated twice. A table misspelt `[flight_conditions]` is
  refused AS THAT, rather than as an unknown solver setting whose stock
  remedy (`recorded_only`) would have made it legal, silent and inert.

### Changed

- **A time step derived from `DELTA_THETA` and `REVOLUTIONS` is emitted as
  derived, never rounded.** That was always so and is stated here because a
  session briefly made it otherwise: the reference scripts write
  `DELTA_TIME 0.00352` where the same derivation gives 0.0035223250952, and
  the correction is that the rounding belongs to that file rather than to
  what a run emits. Rounding would end a run at an azimuth nobody chose,
  which is what stating the revolutions exists to prevent. The steps per
  revolution come from the azimuthal step itself rather than from a
  quotient of the seconds and the speed.
- **An unsteady run that meshes nothing turning may state its clock
  azimuthally**, when the row states the speed whose azimuth the step
  measures. The reference `POLAR-3224` is the case: a wing-body in a propeller's
  slipstream at an advance ratio of 1.3, described as
  `UNS_WB_DTHETA20deg_REV8p0`, whose recorded step is twenty degrees at that
  propeller's speed. A row stating the pair and no speed is still refused,
  and the refusal now names `ADVANCE_RATIO` and `RPM` as the two keys that
  would resolve it.

### Fixed

- The default loads assessor judges the point's OWN declared outputs, not
  every file in the simulation folder. Under the standard naming each
  point's loads table is `<point>.txt`, so the second point of a two-point
  sweep found the first point's table beside its own and was refused as
  ambiguous ("several of them parse"); measured on the reference campaign on
  2026-09-03, row 3207 at alpha 0 after alpha -2. A case declaring no
  outputs is judged over the whole folder as before.
- A rotor speed derived from `ADVANCE_RATIO` is emitted at four decimals,
  the precision the reference tooling wrote it with: the recorded 9001 script
  states 473.1723 rev/min (quoted in `reports/RPT-040`, the reproduction
  report) where the unrounded derivation gives 473.17227304,
  and the run that produced the reference tables turned at the four-decimal value.
  Found by the scripts arm of GOAL-011 on 2026-09-03 as the one difference
  on that point once the row stated the advance ratio the reference name carries.

## [0.11.0] - 2026-09-03

### Fixed

- A staged junction is recognised on Python 3.11 as well: `os.path.isjunction`
  arrived in 3.12, and the first release commit read it unconditionally on
  Windows, so on 3.11 the staging link was reported as a folder and the
  Ubuntu 3.11 leg of CI refused a test helper that read it too; the fact is
  now read off `lstat` where the function is absent. Found by CI on the
  release commit, before the tag.

### Added

- FR-54, PFS-2030.02: a flight condition may PIN the fluid constants the
  standard atmosphere would otherwise supply, with five new keys
  (`RHOkgm3`, `MUPas`, `ASMPS`, `TK`, `PPA`), so a row can state the fluid its
  the reference scripts pinned, and the emitted `FLUID_PROPERTIES` block carries
  those numbers; the resolved condition records which fields were pinned.
- FR-54, PFS-2030.03: every builder now states the reference velocity
  (`SOLVER_SET_REF_VELOCITY`, the free stream unless the setup states
  `reference_velocity_mps`), the sideslip even at zero, and the
  `LOAD_SOLVER_INITIALIZATION` flag on `OPEN` (DISABLE unless the setup states
  `load_solver_initialization = true`); a reference artifact's moment point
  becomes a coordinate system named MRP and the analysis loads frame, with
  `SET_ANALYSIS_MOMENTS_MODEL PRESSURE`; a setup's `vorticity_drag_boundaries`
  may be written as family names and is resolved through the opened geometry's
  inventory; `significant_digits` and `wake_termination_steps` have emitters,
  the second on the run type that turns nothing. The two unsteady run types
  create a `PROP_MRP` frame at the reference's propeller position, which is the
  one field of the propeller block the package now reads.
- PFS-2028.05, the design decision of 2026-09-02: a setup that states
  `symmetry_loads` emits `SET_ANALYSIS_SYMMETRY_LOADS` as stated; an absent key
  still emits nothing. The measurement behind it: the 0.10.1 reproduction of the reference
  isolated rotor reported loads six times the reference because the reference preset stated the
  symmetry loads off and nothing was emitted.

- FR-51, PFS-2029.14.01 and PFS-2029.18: a workflow row that declares no
  `OUTPUTS` gets the study's export set by default, seven kinds for a steady
  point and eight for an unsteady one, every one named for the point with the
  reference suffixes (`.fsm`, `.txt`, `.dat`, `_cp.txt`, `_sloads.txt`,
  `_probes.txt`, `_plots.txt`, `_log.txt`); the three builders export them in
  the order, the saved simulation first, with `UPDATE_ALL_SURFACE_SECTIONS`,
  `COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS` and `UPDATE_PROBE_POINTS` before
  them whenever a section, sectional-loads or probe export is asked for. A row
  that still declares `OUTPUTS` exports exactly what it declares, paired with
  its verb by suffix, so a matrix written before this release renders what it
  rendered. The workflow coverage tables name the new verbs, so a build on
  which one carries no row is reported rather than assumed.

- FR-50, FR-52, FR-53 and FR-55, PFS-2029.07: the groups artifact is now the
  POST-PROCESSING artifact, `inputs/pproc/p<id>.toml`, named by the matrix's
  `PPROC` cell (the column that was `ENTRY`), and it carries six tables, every
  one optional: `[groups]` exactly as the groups file held it; `[exports]`,
  which of the eight export kinds a point writes (all unless a kind is set to
  false, the loads table never); `[sections]`, one
  `NEW_SURFACE_SECTION_DISTRIBUTION` per entry and plane; `[plots]`, one
  `UNSTEADY_SOLVER_NEW_FORCE_PLOT` per group and parameter, named
  `{parameter}_{group}` in COEFFICIENTS or NEWTONS; `[probes]`, one
  `UNSTEADY_SOLVER_NEW_FLUID_PLOT` per vertex and parameter along lines laid
  out in metres or propeller radii; and `[products]`, which post-processed
  CSV tables the campaign writes (`polars`, `sections`, `plots`). An entry names families, or a selector (`all`,
  `airframe`, `blades`, `each`, `each_blade`), and cites a frame by name
  (`MRP`, `PROP_MRP`, `BLADE_AXIS`); a family the geometry does not carry is
  left out, as the reference driver filtered its tables, and an entry that
  resolves to nothing is skipped. The three builders emit the definitions
  before the solver runs; the run record names the pproc id
  (PFS-2029.16), and a setup artifact naming a post-processing table is
  refused pointing at the pproc artifact.
- PFS-2029.11.03, the first half: the rotor run type creates one
  `BladeAxis<k>` frame per blade family of the opened geometry, at the
  propeller frame's origin and turned about the rotor axis by the blade's
  share of a turn, registers them as the motion's moving frames, and the
  pproc artifact's `BLADE_AXIS` entries cite them per blade. A geometry with
  no blade family creates none, so every existing rotor golden is unchanged.
- PFS-2029.04 and PFS-2029.07.02: the run matrix has a 0.11.0 layout, fourteen
  columns: `FS_SCRIPT` went, and `ENTRY` became `PPROC`. A row naming a
  registered run type names its builder already; a `LEGACY` row carries its
  recipe code as the `RECIPE` key of its variables. The v0.9.0 to v0.10.1
  layout is recognised by its header row and refused naming `pyfs-matrix
  upgrade`, whose third stage renames the column, drops the `FS_SCRIPT` cell of
  every row, moves a LEGACY row's code into its variables, gives an `e` id its
  `p` letter, and takes `OUTPUTS` and `LOG_OUTPUT` out of a workflow row's
  variables; `--inputs <dir>` beside `--in-place` moves `inputs/groups/e*.toml`
  to `inputs/pproc/p*.toml` under `[groups]`, comments and all. A workflow row
  that still carries `OUTPUTS` is refused naming the pproc artifact.
- FR-52 and FR-53, PFS-2029.15.01 and PFS-2029.15.02: the post-processed
  products, as CSV. `pyflightstream.post.products` writes one polar table per
  group of the pproc artifact (`<polar>_M<mach code>_g<group>.csv`: the
  reference block and the twenty-four coefficients of the group per point,
  in body, stability and wind axes with the two drag parts, at five
  decimals), one sections table per point from its sectional loads export
  (`sections/<point>_sections.csv`, nothing for an export declaring zero
  sections), and one plots table per unsteady point from its plots export
  (`plots/<point>_plots.csv`, the coefficient columns brought from the
  reference velocity to the free stream); a reader round-trips each, a
  plots export the reader cannot parse is refused naming the file, and
  `write_recorded_polar` drives the three over a recorded polar's point
  folders. The numbers are the reference: the recorded tables, converted to
  the same CSV shape outside the package, are equal text (the products arm
  of GOAL-011, 32 of 32). The products are CSV by the design decision of
  2026-09-02; the layout the owning seat recorded in is a third party's and the package
  neither names nor writes it.
- PFS-2029.03: the workspace directory names the campaign. `pyfs-matrix
  plan` and `run` need no `--name`: the campaign is named after the
  workspace directory, and the plan and every run record say where the name
  came from (`campaign_name_from`: `directory`, or `option` when `--name`
  was given); a directory whose name is not a plain token is refused naming
  `--name`, and `convert`, which has no workspace, still needs it. A resume
  from a workspace renamed since its first run is refused naming the
  recorded name, the derived name and `--name`, since every run id begins
  with the campaign's name and nothing would be recognised as recorded.
- PFS-2029.09, the design decision of 2026-09-02 amending PFS-2009.01:
  the `GEOMETRY` cell carries the FILE NAME with its extension.
  `30_WB.fsm` resolves to `inputs/geometries/30_WB.fsm` and `blade.v2.fsm`
  reads one way; a bare stem is refused naming the files that carry it, a
  file the directory lacks is refused naming what it holds, and a path is
  refused naming the file name to write. `pyfs-matrix upgrade` gains a
  fourth stage that completes every stem-only `GEOMETRY` value with `.fsm`,
  on an older matrix and on a current one alike, so the reference
  workspaces and the fixtures moved in one command. A workflow row naming a
  mesh (`.obj`, `.stl`) is still refused before any seat is spent, and the
  refusal now names 0.12.0 as the release that defines a mesh's boundary
  conditions. A profile still resolves by its stem.
- PFS-2029.06: the boundary inventory is read from the file, never stated
  in a preset. `mesh_order_list` in a setup artifact is refused naming
  `pyfs-matrix inventory` (.06.01): a preset shared by several geometries
  cannot state the order of any one of them, and an order nothing checks is
  read as documentation. `pyfs-matrix inventory inputs/geometries/30_WB.fsm`
  reads the mesh block and writes `30_WB.boundaries.toml` beside the file
  (.06.02); it refuses to overwrite an existing sidecar without
  `--overwrite` and refuses a file without a mesh block by name. A row whose
  geometry has a sidecar is checked at `OPEN`: a sidecar that disagrees with
  the file's own block is refused before the solver starts, naming both
  lists, in the pre-flight of `plan` and `run` alike; an agreeing sidecar
  is recorded in the run record as `inventory_source: sidecar`, a file whose
  block is the only source as `mesh_block`, and a sidecar beside a file
  without a block declares the names the file cannot (.06.03). The two
  reference setups that carried the key no longer do.
- PFS-2029.11: one row states more than one rotor. The `VAR_NAMES_VALUES`
  cell reads `MOTIONS: {KEY: value / ...}, {...}`, one brace-closed record
  per rotor (.11.01); an unclosed brace, a repeated key inside a record, a
  brace on any other key and a flat motion key beside the list are each
  refused naming the cell, and every cell without the key reads as before.
  A reference point may declare `kind = "engine"` or `"airframe"`, the
  convention (`ERP`, `ARP`) answering when it does not, and a record whose
  `ROTOR_ORIGIN` names a point that is not an engine point is refused
  naming the point and its kind (.11.02). N records become N motions: a
  fixed frame at each hub, a moving frame per motion, and one
  `CREATE_NEW_MOTION` block per record citing its own frame, axis, speed
  and boundaries; the time step follows the fastest rotor and the run
  record lists the records as bound (.11.03). A flat rotor row renders byte
  for byte as its 0.10.1 golden.
- PFS-2029.17: a point opens the staged geometry through a link, not through
  a copy. When every input of a simulation sits in the workspace geometry
  library, `sims/<sim>/inputs` is a directory junction on Windows and a
  symbolic link elsewhere, so a campaign leaves no second copy of a geometry
  on disk; the record still carries the opened path and its sha256, and now
  `staged_as: link`. A filesystem that refuses the link, a source outside the
  library, or an inputs folder holding copies from an earlier release fall
  back to a copy, and the record says `staged_as: copy` with the reason.
  `archive_sim` writes the link as a one-line `inputs/STAGED_AS_LINK.txt`
  naming its target and never the bytes behind it, and both `archive_sim` and
  `clean_sim` unlink before removing, so neither crosses into the library.
- PFS-2029.10: base region is an optional input naming mesh families.
  A pproc artifact's `base_regions` list, or a row's `BASE_REGIONS` key
  which overrides it, names the families the base-region autodetect may
  consider, and the builder emits one `DETECT_BASE_REGIONS_BY_SURFACE` per
  boundary of those families right after `OPEN`. Naming none emits nothing,
  so every golden and every recorded script is unchanged; a family the
  geometry does not carry is refused naming what the inventory declares.
- PFS-2029.12: an undeclared boundary inventory says why it is undeclared.
  A row citing a boundary NAME against a geometry that carries no mesh
  block is refused naming the file and saying so, with the sidecar and the
  positional forms as the routes; a name the declared inventory lacks is
  refused naming the inventory it was read from, the mesh block or the
  sidecar, and what it declares. The silent `except OSError` in the mesh
  reader is gone: a file that cannot be opened is reported by name and
  cause, as a warning at `OPEN` and in the refusal of any name cited
  against it.
- PFS-2029.08: the four rotor facts leave the reference artifact.
  `rotation`, `blade_travel`, `rpm_sign_installed` and `rpm_sign_isolated`
  were recorded in the `[propeller]` block from 0.8.0 to 0.10.1 and read by no
  builder; a file carrying them is refused naming the row keys that state
  the rotor speed's sign and axis (`RPM`, `RPM_SIGN`, `ROTOR_AXIS`), and
  `pyfs-matrix upgrade --inputs` strips exactly those lines from every
  reference artifact, leaving every other byte. The measured argument that
  related the datasheet's sense to the sign about the rotor axis is on
  `docs/mesh-inputs.md`. The rotor goldens are unchanged.
- PFS-2029.05: the reference artifact needs no propeller radius. The
  diameter at the artifact's root is the length the package reads (the
  advance ratio, the probe lines); `[propeller] radius_m` is optional, a file
  stating both is refused when twice the radius is not the diameter, naming
  both values, and a file stating the radius alone is refused naming the
  diameter key it must carry. The rotor goldens are unchanged.
- FR-55, PFS-2029.15.03: the run leaves its products. After collection
  `run_campaign` and `pyfs-matrix run` write the polar, section and plot
  tables of every simulation under `post/products`, and
  `post/products/products.json` names each file with the run ids it derives
  from and the pproc id; `pyfs-matrix post --workspace <root>` rebuilds them
  from the manifest alone, with no executable configured, and refuses an
  existing product without `--overwrite`. The run record carries what that
  needs (`description`, `mach`, `reference`), and `ReferenceData` carries
  the reference span (`span_m`), which the polar tables scale the rolling
  and yawing moments to.
- FR-33a and FR-33b, PFS-2029.19: the reference naming convention names
  every point and its exports. A new placeholder `{polar}` renders
  `POLAR-<sim>_M<mach*100:02d>AL<alpha*10:+04d>BE<beta*10:+04d>`, with
  `J<J*100:+04d>` appended when the case has an advance ratio, fixed width so
  a directory of them sorts (`POLAR-3207_M20AL-020BE+000`,
  `POLAR-9001_M14AL+000BE+000J+170`); `{name}`, inside an output name, is the
  rendered point stem, and the default export set hangs off it. `pyfs-matrix
  plan` and `run` name points by `{polar}` unless `--point-name` says
  otherwise, because a matrix row always resolves a Mach number; the library
  default stays `{point}`, so hand-built campaigns, goldens and manifests are
  what they were. The run record carries the template that rendered its names
  (`point_name_template`). A rotorless unsteady row may state `ADVANCE_RATIO`,
  the J of the propeller it did not mesh, as the reference wing-body rows did; it names
  the point and turns nothing, and the keys that would turn something are
  still refused.
- PFS-2029.01 and PFS-2029.02: `pyfs-matrix run` and `plan` need no
  `--fs-version` when every active row fills `FS_BUILD` (a silent row is still
  refused by name), and no `--workflow CODE=NAME` for a row naming a registered
  run type; `--recipe` is still required by a `LEGACY` row.

### Changed

- A workflow row that declares no `OUTPUTS` is no longer refused before the
  run; it runs with the default export set and a point whose declared exports
  are not all written is `FAILED_INCOMPLETE_OUTPUT` naming them, as before.
- The workflow goldens were regenerated for the lines above; every emitted
  script gains the sideslip, the reference velocity and the initialisation flag.

## [0.10.1] - 2026-09-02

### Fixed -- a row names the mesh family, and the package makes the link

- **`MOVING_BOUNDARIES` accepts boundary NAMES and FAMILY names, and a
  family is one word that is right for every geometry in a study.** A
  rotor row cited its moving boundaries by POSITION in one geometry's
  boundary order. Those positions are correct for the file they were
  written against and name different surfaces in any file that orders
  them differently, and nothing said so: the run completed, exported,
  and reported loads for a rotor whose moving set was wrong. That is the
  same silent-wrong-answer shape as a periodic sector solved under
  `NONE` before 0.8.1.

  A cell now reads `MOVING_BOUNDARIES: Blade,S`. A family name is a
  boundary label with its trailing number removed, so `Blade` selects
  every blade the opened geometry carries: on a three-boundary sector
  holding `Blade1, S, N` that cell moves boundaries 1 and 2, and on the
  eight-boundary wheel holding `Blade1, S, N, Blade2 ... Blade6` the
  same cell moves 1, 2, 4, 5, 6, 7 and 8. Measured against the reference
  own campaign: **one cell reproduces all ten of its positional cells
  exactly, across five geometries**, and every emitted script is byte
  for byte what it was. Those two tables, and the evidence that a
  boundary's POSITION in the mesh block is the solver's index, are in
  `reports/RPT-039_boundary-position-is-the-solver-index_2026-09-02.md`.
  The campaign's own files stay outside this repository, so what is
  committed is the measurement rather than the geometry.

  An exact label beats a family, so `Blade1` is one blade and `Blade` is
  all of them. A name the geometry does not carry is refused, listing
  the ones it does.

- **The package reads the boundary names out of the saved simulation it
  opens.** They were always there, in the file's own mesh block, and
  nothing looked. The reader takes the 1-based POSITION of each record
  as the boundary index and discards the number printed on the record's
  first line, which is not the index: across the reference set of eight
  geometries, seven start that number at 2 and one starts at 1, so a map
  built from it would be off by one almost everywhere.

  The declaration is bound to the `OPEN`, so the inventory and the file
  the script loads are the same file by construction. A script this
  package did not open a geometry into is untouched, which keeps the
  user-recipe route documented in `docs/mesh-inputs.md` working exactly
  as before.

- **A named boundary group can be written in names.** `expand_group`
  refused a member that was a boundary label and instructed the user, in
  its own message, to "declare the group with indices". It now takes the
  geometry's inventory and resolves the names; only its absence refuses,
  and that refusal names the route instead of prescribing positions.

- **`FR-30b Index or label, everywhere` came off implemented and went
  back on in the same release.** The requirement is unchanged in wording.
  It was true where its evidence looked, which was the script layer, and
  false where a user writes, because nothing in the package ever declared
  a boundary inventory. Its evidence line now names a test at the surface
  the requirement claims, and that test fails on 0.10.0.

### Added -- a third run type, by an agreed exception on a patch

- **`unsteady`: an unsteady run with nothing turning.** The package built
  two of the three shapes a study needs, and the third had no name a
  matrix row could write, so two cases of the reference exercise were
  left out of the reference campaign rather than forced into a run type that is not
  theirs. One of them is a wing-body in the time domain; the other is a
  power-off configuration on the powered run's discretisation, which
  exists precisely so the two are comparable.

  **THIS IS A NEW CAPABILITY IN A PATCH RELEASE, and it is stated here
  rather than left for a reader to infer from the version number.** The
  owning seat widened 0.10.1 by explicit exception so these items would not
  block downstream work. A reader of the version history should know that 0.10.1
  is a patch by its numbering and by its priority-zero defect fix, and
  that it also carries this addition because the owning seat asked for it that way.

  Its clock is `DELTA_TIME` and `TIME_ITERATIONS`, and the azimuthal pair
  is REFUSED on it. `DELTA_THETA` and `REVOLUTIONS` are not a clock; they
  become one by dividing by a rotor speed, and this run has none. The
  refusal deliberately does not offer a rotor speed: an author who stated
  one to satisfy it would get a run that builds, solves and exports with
  its physical time step set from a number nothing turns at.

  A rotor key on such a row is refused rather than dropped, for the reason
  this package already gives about a preset key that validates and reaches
  no emitted line: it is the same wrong answer with a longer path to it.

  It covers all nine registered solver builds, derived from the command
  database rather than declared, against the rotor type's five, because
  it emits neither motion command. The difference is four.

### Fixed -- pointers to a file this repository does not publish

- **70 tracked pointers retargeted, and the paragraph that shipped a
  false sentence corrected.** A file at the repository root stopped being
  published in 0.9.0. Two pointers to it were corrected then; the rest
  were never swept. Measured now: 116 occurrences of that filename in the
  tracked tree, and the file is not there.

  `reports/` and `CHANGELOG.md` keep theirs, deliberately, which is why
  46 remain. Those are committed evidence and history: a pointer inside
  either was TRUE when it was written, and editing one would be rewriting
  a record of what somebody knew at the time. The other 70 now name
  `CONTRIBUTING.md`, which carries the numbered hard invariants. 116
  before, 46 after, and the two figures close.

- **The numbering is the retired file's, kept exactly.** 129 places cite
  an invariant BY NUMBER, so the numbering is an interface. Renumbering
  to match a shorter prose list was refused because it cannot be
  completed: 44 of those citations sit in evidence and history and cannot
  be rewritten, so a renumber would leave 85 under one numbering and 44
  under another in one tree, with nothing marking which is which.

- **A fresh clone is NOT owed the machine-configuration variable list.**
  Measured rather than asserted: no tracked file in this repository reads
  any of those variables. The published page said they "locate the
  licensed solver and its manuals", and that was wrong twice over: the
  solver is located by a required argument that is never guessed, and the
  variables never described a solver at all. That paragraph was inside
  the published package metadata, so it reached every reader of the
  project page.

- **An exemption naming a file that is not there is now caught.** The
  shipped-surface configuration excused that same retired file for three
  releases after it left. An exemption for an absent path never fires, so
  it never fails, so it could not go stale loudly. A tier-1 test now
  refuses one, with a control beside it.

### Measured -- what the evidence says about the rotor default path

- **RPT-038: every command the rotor path emits, on every registered
  build.** The seat-free half of the compatibility item. It is a
  statement about this repository's own evidence and never a claim that
  a command works on a build; the sweep that would earn the second claim
  needs a licensed solver and is for the owning seat to authorise.

  Nineteen commands, nine of them not emitted by the steady path, over
  nine builds: 63 cells verified, 93 documented, and **15 carrying no
  evidence row at all**, which is a third state the item was not written
  to expect.

  A row's absence is NOT the command being unavailable: the build view
  accepts every one of them, so the derived coverage is right and no run
  is affected. NINE of the fifteen are the honest record of a rotor
  vocabulary that arrives at 26.101. The other SIX are one build, 26.122,
  where six commands that carry a row on 26.121 and on 26.123 alike carry
  none, which is a build whose evidence was never recorded rather than a
  vocabulary boundary. That measurement answers the item's own open
  question about which build a sweep should cover: 26.123 is fully
  recorded and 26.122 is the one with the hole.

### Kept working, deliberately

- **A row of positions still runs and emits what it always emitted**, so
  a matrix already written keeps working. It now warns, and the warning
  names the surfaces those positions actually select in that geometry,
  which is a migration instruction rather than a scold. Only a package
  that reads the file can write that sentence.

- One refusal does arm, and it is correct: a position ABOVE the opened
  geometry's boundary count now stops the run instead of reaching the
  solver. No row of the reference campaign does that, and a row that did
  was always wrong.


## [0.10.0] - 2026-09-01

### Added -- a rotor row states the study's decisions, not their arithmetic

- **`ADVANCE_RATIO` and `RPM_SIGN`.** A row states its rotor speed as
  the advance ratio the study was designed at, and the rev/min are
  resolved as `n = V / (J D)` against the run's own velocity and the
  reference propeller diameter. `RPM` stays; a row states exactly one of
  the two, and stating both is refused.

  A ratio is a magnitude, so `RPM_SIGN` (`1` or `-1`, default `1`)
  carries the hand of the rotation. It is refused beside an explicit
  `RPM`, which carries its sign in the number itself.

  **Why the derived form is the better one to keep in a file.** Rev/min
  are what a ratio works out to at ONE velocity. A matrix stating them
  pins the rotor to that velocity silently: change the flight condition
  and the row keeps a speed that no longer means the ratio it was chosen
  for, and nothing says so.

- **`DELTA_THETA` and `REVOLUTIONS`,** the azimuthal step in degrees and
  the length of the run in whole turns, from which the clock follows:
  `DELTA_TIME = theta / (6 |rpm|)` and
  `TIME_ITERATIONS = REVOLUTIONS * 360 / DELTA_THETA`. `DELTA_TIME` and
  `TIME_ITERATIONS` stay for the matrices already written in them; a row
  states one pair, and half a pair is refused naming the missing key.

  Revolutions that do not work out to a WHOLE number of time steps are
  refused naming both numbers, because such a run ends part way through
  a step at an azimuth nobody chose.

  Measured on the reference campaign: rows carrying a hand-typed
  `DELTA_TIME` of `0.00352` were carrying `0.0035222840` rounded to
  three figures, so 54 steps covered 1.4990 revolutions and not the 1.5
  the campaign documented.

- **`propeller_diameter_m` on the reference artifact,** beside
  `area_m2`, `chord_m` and `span_m` rather than inside the propeller
  block, and carried onto the case as
  `ReferenceData.propeller_diameter`. It is a divisor of published
  numbers exactly like the area and the chord: it is what an advance
  ratio is a ratio against and what the propeller coefficients
  normalise on.

- **`LOG_OUTPUT`,** the 1-based position of the solver log among the
  row's own `OUTPUTS`. Both workflows then emit `EXPORT_LOG`, and
  `LoadsAssessor` finds a collected log BY CONTENT, the same rule it
  already finds the loads table by.

  **This changes a published status.** An unsteady run used to be
  recorded `COMPLETED_MAX_ITER` unconditionally, because the time loop
  always reaches its prescribed end and the iteration counter therefore
  judges nothing: a run that converged at every time step and one that
  converged at none came out with the same word. With a log the verdict
  is the residual. A campaign that exports no log is judged exactly as
  it was.

**New public names in `pyflightstream.cases.workflows`:** `rotor_speed`,
`rotor_time_stepping`, `RotorSpeed`, `TimeStepping`, and the cell-key
constants `ADVANCE_RATIO_VARIABLE`, `RPM_SIGN_VARIABLE`,
`DELTA_THETA_VARIABLE`, `REVOLUTIONS_VARIABLE` and `LOG_OUTPUT_VARIABLE`.

**New public model fields:** `ReferenceArtifact.propeller_diameter_m`,
`ReferenceData.propeller_diameter`, the twelve `SolverSettings` fields
listed under Changed below, and `log_file_used` on both `run.Assessment` and
`workspace.RunRecord`.

**Removed public name:** none. **Deprecations:** none, and no shim is
added or retired by this release.

### Known gap -- the rotor default path gained thirteen emitters nobody has swept

Neither the command database nor `reports/` is touched by this release,
so no compatibility or physics report it holds is STALE: nothing they
measure changed. That is not the same as their being COMPLETE for what
this release ships, and the difference is worth stating rather than
leaving an empty diff to imply the stronger thing.

The change is on the caller side. The rotor workflow now emits thirteen
more solver-setting commands per run than it did, so grammar that was a
latent property of entries nobody emitted is now a property of the
DEFAULT path. Most of those entries carry `documented` rather than
`verified` status on most registered builds, which means the manual says
the solver takes them and no committed probe report shows that it does.

WHAT IS MEASURED: the new rotor path ran end to end on a
licensed 26.123, two points, both CONVERGED at residuals of 7.59e-06 and
4.73e-06 against their own 1e-05 limit. WHAT IS NOT: a compatibility
sweep re-examining the verified and documented split for those thirteen
on the builds this workflow covers. That sweep is owed and is not in this
release.

### Changed -- BREAKING for a preset that states a key nothing can emit

A solver preset that resolved yesterday can be REFUSED today, so this is
a change to an input format and not a repair. The remedy is one line in
the preset file; the third bullet says which.

- **A preset key that named no `SolverSettings` field was warned about
  and DROPPED.** A preset asking for `SUBSONIC_PRANDTL_GLAUERT` ran
  `INCOMPRESSIBLE`, and one asking for a turbulent boundary layer ran
  the solver's default. Each is a run that converges, exports and
  publishes numbers against a physics nobody selected. (`NITER` is read
  as an alias now and was not before, but the campaign that surfaced
  this cannot demonstrate that one: its preset states 500 and the model
  default is 500, so both runs emitted the same line.)

  An unknown key is now REFUSED, naming the key and listing what
  applies, so a typo finds the field it meant.

  **What was measured, stated to the precision it was measured at.** On
  the reference campaign, honouring the preset moved the axial force
  coefficient `Cx` from -0.0535 to -0.0541 on one rotor point and from
  -0.0542 to -0.0548 on another, which is about one percent in the
  direction expected. Those operands are printed to four decimals, so
  each difference carries ONE significant figure, and the band the two
  pairs together support is 0.92 to 1.31 percent.

  **The attribution to any single setting is NOT earned**, and an
  earlier draft of this entry claimed the move WAS the Prandtl-Glauert
  factor. It is worth writing down why that was wrong, because the
  arithmetic is seductive: the factor at M 0.1441 is +1.05 percent and
  the measured move is about +1.1 percent, so the two agree inside the
  band above. **Agreement is not evidence here**, because FOURTEEN
  emitted solver settings differ between the two runs and only one of
  them is the flow model.

  That count is measured, by diffing the two emitted scripts, **and the
  filter is stated because a reader who diffs them sees sixteen
  differing lines rather than fourteen.** Thirteen SOLVER-SETTING
  commands appear in the current script and in neither the control, and
  `SOLVER_MODEL` is the one command present in both with a different
  value. Two further differences are excluded and named rather than
  dropped: `EXPORT_LOG`, which is an export and not a setting, and
  `SOLVER_MINIMUM_CP`, which reads `-100` in one and `-100.0` in the
  other and is one number written two ways.

  Among the thirteen are wake-on-wake induction, the farfield layer
  count, the mesh-induced wake velocity and the wake termination, each
  of which feeds the same wake and farfield model the axial force is
  integrated from. **That last clause is a statement about the emitted
  script and not about the solver**, deliberately: saying those four
  settings move rotor axial force would be a claim about what the
  solver computes, which is the thing the paragraph below says this
  repository does not make, and an earlier draft made it three lines
  above that sentence. Earning the attribution needs a run that changes
  `SOLVER_MODEL` and nothing else.

  And this package's command database is a GRAMMAR record: by its own
  stated policy it carries no claim about what any solver model
  computes, for any token. So what `SUBSONIC_PRANDTL_GLAUERT` does is
  not something this repository asserts anywhere, and a changelog entry
  is not the place to start.

  **The runs are not in this repository.** They live in the reference
  campaign workspace at `tools/fts_workspace/pfs090`, measured
  2026-09-01: the after-state under `sims/`, the before-state under
  `archive/run_26123_preset_nao_mapeado`, and that tree is not tracked
  here. Both arms ran the same executable and recorded solver build
  `8112026`, read from each arm's own `runs.json` rather than from the
  scripts, which record no build at all. The numbers above are reported as the reference
  measurement and are not a repository guarantee.

- **Twelve settings joined `SolverSettings`,** every one of which has an
  emitter: `solver_model`, `wall_collision_avoidance`,
  `convergence_iterations`, `minimum_cp`, `farfield_layers`,
  `mesh_induced_wake_velocity`, `unsteady_pressure_and_kutta`,
  `wake_on_wake_induction`, `additional_wake_relaxation`,
  `reynolds_averaged_drag`, `solver_stabilization` and
  `wake_termination_revolutions`. All optional and all defaulting to
  None, so a campaign that states none emits exactly what it emitted
  before.

- **The solver's own key spellings are read as aliases,** not as junk:
  `NITER`, `boundary_layer_type`, `max_parallel_threads`,
  `set_solver_model`, `proximity_avoidance`, `solver_minimum_cp`,
  `induced_wake_velocity`, `unsteady_pressure_kutta`,
  `additional_wake_relaxation_iteration`,
  `reynolds_averaged_drag_forces` and `unsteady_N_revolutions_wake`.
  A preset transcribed from a working FlightStream session keeps working
  as written.

- **A closed set of keys is declared recorded-only, each with its
  reason,** and the warning prints the reason rather than only the key.
  The count is deliberately not written here: it has already been wrong
  once, and the refusal and the warning both print the live list. A preset may declare its own with a
  `recorded_only` list, so a setting from a build this package has not
  met is not a hard block. `stabilization` and `stabilization_strength`
  resolve as a PAIR into `solver_stabilization`; disabled means absent
  and not a strength of zero, which would still be switched on.

  `symmetry_loads` is recorded-only deliberately although it has an
  emitter: applying it multiplies or divides every published coefficient
  of a periodic or mirrored case by the copy count, which is a decision
  to make with a measurement in hand.

## [0.9.0] - 2026-08-25

### Changed -- BREAKING, and it changes the run-matrix file format

- **The `RE` and `MACH` columns are REMOVED. A row states its whole flow
  condition in one `FLIGHT_CONDITION` cell** (PFS-2027.01). The run
  matrix goes from sixteen columns to fifteen.

  **What to do if you have a matrix.** Nothing is guessed and nothing is
  silently reinterpreted: `read_matrix` RECOGNISES a file written under
  either older layout and refuses it naming the converter. Run:

  ```
  pyfs-matrix upgrade your_matrix.fs --in-place
  ```

  It needs no recipes, no version and no executable, because upgrading a
  file needs none of those. Without `--in-place` the upgraded matrix
  goes to standard output, so you can diff before you overwrite. From
  Python it is the same converter:

  ```python
  from pyflightstream.cases.matrix import upgrade_matrix
  upgrade_matrix("your_matrix.fs", in_place=True)
  ```

  It folds `RE` and `MACH` into one cell reading
  `MACH:<mach>, REmi:<re>`. Every VALUE moves across verbatim -- `0.20`
  keeps its trailing zero -- and every other cell, separator and line
  ending is untouched. What cannot survive is the two folded columns'
  own PADDING, because two cells become one and the original widths are
  not recoverable from the joined text. A file written before v0.8.0
  needs both stages and gets both from the same call: it gains the
  `WORKFLOW` cell and then the fold.

  **THE CONVERSION IS LOSSLESS AS A FILE. IT IS NOT NEUTRAL AS A RESULT,
  and this is the paragraph to read before you upgrade a campaign you
  have already run.** Under 0.8.x the `RE` column was RECORDED METADATA:
  it reached the run record and no emitter, so a row's declared Reynolds
  number changed nothing about what the solver was asked to do. From
  0.9.0 `REmi` is a CONSTRAINT that solves for density. Every legacy row
  carried both `RE` and `MACH`, so every upgraded row now states both
  keys, takes the solved-density branch, and emits an explicit
  `FLUID_PROPERTIES` block it never emitted before.

  Measured on this repository's own committed fixture, POL 9001 at
  `RE 4.38`, `MACH 0.1441` against a 1.2 m reference: the upgraded row
  solves at 1.3319 kg/m3, **8.7 percent above sea level**, where the
  same row previously emitted no fluid state at all. The numbers will
  differ, and they differ because the old behaviour was the defect this
  release fixes -- a declared Reynolds number that changed nothing is
  the same class of gap as the reference artifact that reached no
  emitted line.

  **If you want the previous behaviour**, state the condition without
  `REmi` and let the Reynolds number be derived from the atmosphere:
  `MACH:0.1441` alone resolves at the standard density for its altitude
  and emits what 0.8.x emitted. Keep `REmi` when you meant it as a
  constraint, which is what a wind-tunnel or validation case wants.

  **Why the columns went rather than gained a neighbour.** A flight
  condition is a SET OF CONSTRAINTS on one flow state, and which
  quantity gets solved for follows from which keys are present. Keeping
  `RE` and `MACH` as mandatory columns beside a cell that can also state
  them would have meant two homes for the same two numbers, and a reader
  would have had to look in both to know what was actually solved. One
  home per question, and no precedence rule BETWEEN homes to learn.

  There is exactly one interaction BETWEEN keys, and it is stated here
  rather than left to be inferred, because the sentence above read "no
  precedence rule to learn" until a release review pointed out that it
  is false of the key set that replaced the columns. `ALTFT` beside
  `REmi` gives the altitude's temperature, and with it the speed of
  sound and the viscosity, while the Reynolds number still solves the
  density: the altitude half-applies on that branch. That is exactly
  what a wind-tunnel-at-altitude row means, so it is a feature and not
  a defect, and it is worth knowing before you write one.

  The accepted keys, **with their units, because the units ride the key
  names and a reader who has not been told the suffixes cannot infer
  them**: `MACH` (dimensionless), `TASmps` (true airspeed, metres per
  second), `REmi` (Reynolds number **in millions**, so 5.5 means
  5 500 000), `ALTFT` (pressure altitude **in feet**), and `dISA` (a
  temperature offset from standard, **in Celsius, as a delta**). The set
  is CLOSED: an unrecognised key is refused naming it and
  listing the accepted set, which is the difference between a typo that
  costs a message and a typo that costs a campaign. Keys match
  case-insensitively; a duplicated key is refused rather than taking the
  last one, because these are constraints on one state and a silently
  dropped constraint changes what is solved.

  **The cell is MANDATORY**, exactly as the two columns it replaced
  were. A row that states no flow condition at all is refused by the
  reader, naming the row and the columns it replaced: letting one
  through would be a loosening smuggled in by a format change, and the
  case would reach a builder with no velocity, no density and no
  Reynolds number while looking exactly like a working row.

- **A constraint set resolves to one flow state, or is refused**
  (PFS-2027.02, PFS-2027.04). The keys a row states decide WHICH
  quantity is solved for. `MACH` with `REmi` at no stated temperature is
  sea level with the DENSITY solved to meet the Reynolds number;
  `TASmps` with `ALTFT` and `dISA` is an atmosphere point with Reynolds
  derived. One resolver answers both.

  A set that determines no velocity is refused as under-determined,
  naming which keys would supply one. A set stating both `MACH` and
  `TASmps` is refused as a contradiction rather than resolved by
  preferring one silently. `dISA` defaults to 0 and an absent altitude
  to sea level, and those defaults are what make a short set legal.

  **A Reynolds number needs a reference length, and says so.** `REmi` on
  a row naming no reference is refused naming both, because the same
  `MACH:0.20, REmi:5.5` against a unit chord and against a rotor's mean
  face length of about 0.15 m gives densities differing by the ratio of
  the two lengths, near a factor of seven. On this branch density is
  inversely proportional to the reference length and to nothing else,
  which is why the length is the whole of the difference. The length
  actually used is recorded beside the resolved state, since the state
  cannot be checked without it.

  **The solved-density state is not a point in any atmosphere**, and it
  says so about itself. Holding Mach and Reynolds together at a fixed
  temperature is what a wind tunnel does; the implied pressure is then
  not any altitude's. The record carries which branch produced the
  density, so a later reader cannot mistake it for an altitude and
  "fix" it into one.

### Removed

- **`MatrixRow.mach` and `MatrixRow.re_millions` are gone**, with the
  columns behind them. `MatrixRow` is published API, so this is a Python
  break as well as a file-format one and it is announced here rather
  than left to be met at run time. Read `row.flight_condition["MACH"]`
  and `row.flight_condition["REmi"]` instead; a key a row did not state
  is ABSENT from that mapping rather than present as `None`.

  Note also that `SimCase.mach` is now `None` for a row that states
  `TASmps` rather than `MACH`, because the case records what was stated
  before the resolver has run. The resolved Mach number is on the
  resolved condition, which `resolve_matrix` returns.

- **`SimCase.reynolds` is `None` for a row that states no `REmi`, and
  the `reynolds` key is then OMITTED from a generated
  `campaign.toml`.** Under v0.8.x `RE` was a mandatory column, so that
  value was on every case of every row and the key was in every
  campaign file. This one is easy to meet by accident, because the way
  to meet it is to follow the advice two paragraphs above: state the
  condition without `REmi` to keep the previous behaviour, and the key
  your previous campaign file always carried is gone. A script reading
  `campaign["sims"][i]["reynolds"]` raises `KeyError`; arithmetic on
  `case.reynolds` raises `TypeError`.

  If the row names a `REF`, the DERIVED Reynolds number is on the
  resolved condition as `ResolvedCondition.reynolds`, which is the
  number that was actually true of the run rather than the number that
  was declared.

### Added

- **A standard atmosphere the package computes itself** (PFS-2027.03), as
  a floor module below every layer: ISA temperature, pressure, density,
  speed of sound and Sutherland viscosity, with an ISA deviation that
  moves temperature and leaves pressure alone. That last point is the
  convention worth writing down, because the other reading -- shifting
  pressure too -- is what a reader who has not met "ISA+5" will assume,
  and it is asserted rather than left to be inferred.

  It is NOT in `utils`, and the reason is the package's declared
  architecture rather than a preference: `utils` is a side branch outside
  the pipeline, and putting the atmosphere there would have created the
  first pipeline-to-`utils` dependency in the one module family whose
  position in the layer rule is undefined.

  The constants are ISO 2533:1975 and the viscosity law is White's
  Sutherland form, both cited in the module. The tier-1 test asserts
  against the values the standard DEFINES -- sea level, the tropopause,
  and the top of the isothermal layer -- and checks the quantities the
  standard does not tabulate at every boundary by derivation instead,
  because this repository holds no copy of ISO 2533 and a test that
  restated a remembered table figure would reproduce the very defect the
  item exists to retire. Sea-level density is derived rather than
  stored, and reproducing the standard's 1.225 kg/m3 to 1e-8 is what
  checks the three constants behind it together.

  It computes; it does not emit. `script.helpers.atmosphere` remains the
  emitter and remains one.

- **Three new names on the public surface**, listed because an export that
  arrives with no line here is an export a user meets by accident. The
  release audit found all three missing from this section while the
  behaviour they belong to was described at length above.

  - `cases.FluidState`, the resolved flow state carried on a `SimCase`.
    It is what `SimCase.fluid` holds once `resolve_matrix` has run, and
    it is `None` before that, because a case records what was STATED and
    the resolver is what turns it into a state.
  - `exceptions.FlightConditionError`, raised when a cell PARSED and the
    state it asks for cannot be resolved. Four cases, and the list is
    complete rather than illustrative: a condition that states nothing at
    all, no velocity, two velocities, and a Reynolds number on a row with
    no reference length.
  - `exceptions.AtmosphereError`, raised when the cell is well-formed,
    the state is determined, and the atmosphere has no answer there: an
    altitude outside the model's range, or a temperature at or below
    absolute zero.

  **Three exceptions, not two, and the third is the one already there.**
  A malformed cell -- an unknown key, a duplicate key, a value that is
  not a number, a NaN, an infinity, a missing colon -- raises
  `MatrixError` as it always has, because at that point the defect is in
  the FILE and no flight condition has been constructed to complain
  about. The boundary is worth knowing before you write an `except`
  clause: `MatrixError` means the cell is wrong, `FlightConditionError`
  means the cell is fine and the state is under- or over-determined, and
  `AtmosphereError` means both are fine and the physics does not reach.

- **The run record carries the resolved state** (PFS-2027.05). Beside the
  fields it already had, a `RunRecord` now carries `flight_condition` as
  the cell was WRITTEN, the resolved `density_kg_m3`, `temperature_k` and
  `viscosity_pa_s`, the `reference_length_m` the resolution used, and
  `density_source`, which says WHICH BRANCH produced the density.

  The last one is the load-bearing field, and it is why the others are
  worth recording at all. A density solved to meet a Reynolds number is
  deliberately not a point in any atmosphere, so a record without that
  marker gives a later reader no way to tell a wind-tunnel state from an
  altitude. With it, and with the condition as written beside it, the
  resolution in the artifact that outlives the session can be recomputed
  rather than trusted.

  **Mind the spelling: the same fact has two names.** On a `RunRecord` it
  is `density_source`; on the `FluidState` above it is `source`. Reaching
  for `case.fluid.density_source` raises `AttributeError` rather than
  returning `None`, because `FluidState` forbids extras. Both take the
  same two values, `"atmosphere"` and `"solved-from-reynolds"`. That the
  two names have not converged is registered against the release review
  as a naming decision the product owner owns, and it is written here so
  a user meets it in prose rather than at run time.

### Fixed

- **A commit that missed its clean-room trailer can now be corrected,
  which is what three documents already said and none could do.** The
  Tier 1 provenance guard is a WALK over every commit since its
  baseline, so the remedy printed by the guard itself, by
  `CONTRIBUTING.md` and by the control plane's commit-message hook -- "a
  commit that missed it is corrected by a follow-up commit that says so"
  -- could never clear it: a follow-up adds a commit to the population
  and removes nothing from it. The named mechanism did not exist, which
  is the same defect class FR-08 was reworded for in the first place.

  A later commit now declares on an earlier one's behalf with a
  `Clean-room-for` trailer naming its full hash, beside the unchanged
  `Clean-room` declaration. It is an exemption and deliberately the
  in-band kind: it lives in the history it describes, carries the full
  declaration rather than a waiver token, and is signed by its own
  author and date. The alternatives were moving the baseline, which
  un-checks every commit before it, and rewriting history, which is
  banned here.

  The follow-up is held to every rule a first-hand declaration is held
  to, each with its own test: the declarer must itself declare, must
  name a commit git can resolve, must name one inside the range under
  review, must come after the commit it covers, and may not name itself.

  Measured twice before it was believed: 2026-08-09, when a release
  commit could not be tagged until its message was rewritten, and
  2026-08-24, when a thirteen-line `.gitignore` change turned CI red on
  `main` and no follow-up could clear it.

## [0.8.1] - 2026-08-22

### Fixed

- **A matrix row can name its geometry, and the workflow opens it**
  (PFS-2025.02.01, PFS-2025.02.02). Until this release it could not, and
  the consequence was that the workflow capability v0.8.0 introduced, a
  run type the package builds itself off the matrix `WORKFLOW` column,
  could not be used at all: a case CARRYING a geometry rendered byte for byte identically
  to one that did not, because nothing in the matrix reader assigned the
  field and neither workflow builder read it. The run layer was already
  doing its half, staging the file and hashing it into the record, and
  the value was prepared and read by nobody.

  `GEOMETRY: <stem>` in `VAR_NAMES_VALUES` resolves against
  `inputs/geometries/` the way `REF`, `SET` and `ENTRY` already do, and
  is refused with the available stems and the row's own identifier when
  the id is not staged. Both builders emit `OPEN` first, before anything
  else, on the STAGED path, so the file the manifest hashed and the file
  the solver read are the same bytes.

  A WORKFLOW opens a saved simulation, a `.fsm`, and nothing else; a
  recipe of your own receives whatever the library staged and imports it
  declaring the units itself. Another suffix is REFUSED naming the
  suffix and the documented route, and the refusal is a decision rather
  than a gap: importing a raw mesh needs the row to declare its UNITS,
  and a silently defaulted unit is the same class of failure this
  release exists to remove.

  **If your `VAR_NAMES_VALUES` cells already spell `GEOMETRY`,
  `SYMMETRY` or `PERIODIC_COPIES`, the package now reads them.** That is
  the only upgrade risk in this release: those three names were yours
  before it and are the package's now. Rename your key, or stage the
  file the id names. The match is on the exact key, so a cell spelling
  it `SYMMETRY_TYPE` is untouched. A row carrying a geometry under a key
  of its own, `FSM_FILE` being the common one, is unaffected and also
  unread: rename it to `GEOMETRY` when you move the row off `LEGACY`, or
  keep the recipe. `upgrade_matrix` deliberately does NOT rewrite it,
  because a `LEGACY` row's recipe may still be reading that key.

  **WORSE THAN THE GAP WAS ITS SHAPE, and that is why this is a patch
  rather than a 0.9.0 item.** Every other limit in this capability
  refuses early and names itself. This one did not refuse at all: the
  script built, the campaign ran, and the solver solved whatever it
  already had in memory. No refusal anywhere, and the numbers wrong with
  nothing said, which is the failure this package exists to stop.

- **A row declares its symmetry, so a periodic sector is no longer solved
  as a one-bladed rotor** (PFS-2025.02.03). `SYMMETRY` and, where the
  mode needs it, `PERIODIC_COPIES` come off the row. The accepted modes
  are read from the command database for the row's own build rather than
  from a list written in this package, so a build that spells the
  argument differently reports no accepted set instead of pretending one.

  This is not a convenience. Symmetry was fixed at `NONE`, so a sector
  ran as a one-bladed rotor and the run COMPLETED: the numbers were
  wrong and nothing said so.

- **A matrix that names none of the three keys behaves exactly as it did**,
  and that is now measured rather than promised: every workflow crossed
  with two case shapes and every build it covers, 28 renders, is
  committed under `tests/goldens/workflows/` and compared byte for byte
  on every run of the suite. The one build whose grammar the steady
  builder cannot express is pinned as its REFUSAL text, so that wording
  is fixed too, and the set of pairs allowed to refuse is declared as
  data: an unexpected refusal aborts the generator instead of being
  written as evidence that the tree then accepts.

  The claim is measured rather than asserted, and it was not before: a
  QA pass inserted one extra emitted line into the steady builder, which
  changes the bytes of every geometry-less steady script on every build,
  and the whole tier 1 suite stayed green. It does not now; the same
  mutant fails every steady render on every build that renders one.

  Both halves of the claim are measured, because they are two claims.
  The goldens are generated from THIS release, so on their own they can
  only pin what happens from here. The backward half was measured
  separately and once: the same four case shapes, rendered on all 28
  combinations against a worktree at the `v0.8.0` tag, come out byte for
  byte identical, and the receipt is committed beside the goldens.

- **A campaign no longer fails when the workspace root is relative**, and
  this one was found by the review of the fix above rather than by a
  user. `pyfs-matrix run` and `plan` default `--workspace` to `"."`, and
  `CampaignWorkspace` kept the root exactly as given, while the solver
  runs with its working directory set to the simulation folder. Both the
  script's path and the geometry path the script names were therefore
  spelled from the caller's directory and re-resolved from the solver's,
  one level too deep, so the documented default invocation died with a
  `FileNotFoundError` naming a script that was sitting right there. It
  failed for EVERY row, with or without a geometry.

  The root is now resolved once, at construction, which is the one place
  that covers every path derived from it rather than the three boundaries
  that hand something to the solver today. `CampaignWorkspace.root` is
  therefore absolute even when the caller passed a relative path;
  `RunRecord.script_path` stays relative to the simulation directory, so
  manifests written by earlier releases still read. `RunRecord.cwd` and the SCRIPT PATH inside
  `RunRecord.argv` now carry absolute paths under a relative root, where
  they previously carried the caller's spelling; older rows read
  unchanged. `argv[0]` is the executable as the campaign declared it and
  is unchanged.

  `run.export_surface_mesh` and `run.check_solver_identity` had the same
  defect and no workspace to inherit the fix from, since a caller hands
  each of them a directory directly. Both now resolve their own working
  directory, and with it every path they build from it, including the
  ones that become script text. The second is the sharper of the two: it
  writes its log path into an `EXPORT_LOG`, so a relative working
  directory left the log where nothing read it, no build number was
  parsed, and the identity check WARNED instead of raising. A campaign
  aimed at the wrong FlightStream build proceeded, and the warning said
  the build number could not be read from the solver.

  `LocalExecutor._argv` deliberately does NOT resolve. It did for one
  commit, on the argument that every caller passes through it, and CI
  showed what this Windows-primary machine could not: `Path("C:/runs/x")`
  is absolute here and RELATIVE on Linux, so resolving rewrote it against
  the working directory and broke the documented headless mechanism on
  half the platforms. What a relative path means there is the caller's
  business and is unchanged.

  Every guard in the suite had built its workspace on an absolute
  temporary directory, where a path spelled from the caller and one
  spelled from the solver are the same string, which is why 3143 tests
  passed over a shipped default that could not work.

### Known gaps

A row's `REF` code still changes no emitted line, so coefficients come
out against solver defaults rather than the campaign's areas and lengths;
the solver model and the fluid state are still decided in the builders;
and `BLADES` divides the averaging window and configures no rotor. Where
those belong, a row or a solver-setup preset, is an open design question
and not an oversight: a fluid and a solver model are campaign-wide
conditions rather than case identity.

A workflow row that names no `GEOMETRY` opens nothing and says nothing,
which is what keeps every earlier matrix rendering as it did, and which
means a row migrated off `LEGACY` while keeping its own `FSM_FILE` key
is accepted in silence.

`covered_builds` reports FlightStream 25.000 as covered by `steady`,
because that build's database carries every command the workflow always
emits, while `initialize_solver` refuses that edition's grammar outright.
The refusal is loud and arrives before the script is written and before
any solver is started, so no seat is spent and no numbers are produced.
(A row naming a `GEOMETRY` does emit its `OPEN` first and then refuses;
the script is discarded either way, which is why the guarantee is worded
about the solver rather than about the first emission.) The
over-approximation is pinned as a golden and registered rather than
hidden.

### API surface delta

- **Added** to `pyflightstream.cases.workflows`: `GEOMETRY_VARIABLE`,
  `SYMMETRY_VARIABLE`, `PERIODIC_COPIES_VARIABLE`, `SIMULATION_SUFFIX`
  and `accepted_symmetry`.
- **Added** to `pyflightstream.workspace.inputs`: `is_valid_artifact_id`,
  which publishes the input-library id shape rule. It exists because two
  layers now need to ask it, and reaching for the private pattern across
  a module boundary is a layer crossing a tier 1 guard refuses.
- `GEOMETRY_VARIABLE` is DEFINED in `cases.workflows`, beside the other
  cell keys, and re-exported from `pyflightstream.workspace.matrix`,
  where the resolver that reads the cell lives. Both import paths work,
  neither is deprecated, and the second is the one the resolver's own
  documentation names.
- `accepted_symmetry` returns `tuple[str, ...] | None`. `None` means the
  build does not express symmetry through an argument of that name; an
  empty tuple would mean it declares one that is not an enumeration.
  Both mean "this build cannot judge a mode", so a caller tests
  truthiness unless it needs to tell the two apart.
- Nothing was removed, renamed or deprecated.

### Documentation

- `docs/workspace-and-workflows.md` gained the three keys, the reserved
  names, the `.fsm`-only narrowing and the two limits above, and lost a
  claim that no unsteady rotor case had run on a licensed solver, which
  the QA physics suite's own PHY-05 contradicts.
- `docs/mesh-inputs.md` says which of its two canonical routes a workflow
  takes, since the refusal cites that page and its canonical section read
  as permission for the route just refused.
- `examples/campaign_matrix.py` no longer tells the reader that a matrix
  row cannot name a geometry. It was true when it was written and shipped
  unchanged through v0.8.0; the key that falsifies it and the correction
  land together here, and a currency guard now holds it.

## [0.8.0] - 2026-08-20

**26.122 answers for 84 commands, and the vendor's build fixes the
rotor morphing defect.** 26.122 was `operational` purely by inheritance from
26.120 with nothing measured on it; a Tier 2 run now promotes 84
statuses and a Tier 3 run passes 30 of 30 metrics against the stored
references, inside the WARN and FAIL bands
(`reports/physics/PHY-26122_2026-08-11_rotor.yaml`). Separately, the FlightStream defect RPT-007 recorded on 26.120,
where an imposed FSIDisp deformation was silently dropped for a
boundary attached to a rotary motion definition, is measured fixed in
26.122 and NOT fixed in 26.121 (RPT-025). Two-way rotor FSI is
unblocked on 26.122 and still NOT VALIDATED: that report says an
imposed deformation reaches the mesh, not that the morphing is
correct, and no coupled acceptance run has been made against a build
where it applies.

Read the Tier 3 pass with its scope. The first run
(`reports/physics/PHY-26122_2026-08-11.yaml`) covered PHY-01 and
PHY-02, both static rigid wings, which look at nothing the build was
measured to have changed; `PHY-05` and `PHY-06` were pinned to 26.120
for a reason that never covered later builds, and they are widened here
and run, which is where 20 of the 30 metrics come from. And read the pass itself
precisely: all thirty metrics reproduce the 26.120-seeded references to
the last stored digit, float artefacts included, which demonstrates
ABSENCE OF DRIFT and not sensitivity to what this build changed. RPT-025
remains the only discriminating measurement, and its own finding that
all three builds give byte-identical rigid coefficients is why a rigid
matrix could not have discriminated.

### API surface delta

**The propeller reference admits the vocabulary a real campaign uses**
(PFS-2009.02). `PropellerReference` gains THREE optional fields and
`rotation` itself is unchanged, still `clockwise` or `counterclockwise`
viewed from behind the aircraft.

`blade_travel` records the SAME physical fact in the vocabulary a vendor
datasheet prints, `inboard_up` or `inboard_down`, naming where the blade
nearest the fuselage travels in the aircraft body frame. Case, hyphens
and spaces are folded, so a datasheet's `inboard-up` is read as written;
it is the one field in the model whose value is transcribed off paper. It is a separate field rather
than two more values of `rotation` because the two vocabularies are not
interchangeable: this one is side-independent, so the left and the right
propeller of a symmetric pair carry the same word, and converting it to
a viewed-from-behind sense needs to know which side the propeller is on.
Keeping them apart also keeps `rotation` a two-value `Literal`, so a
downstream exhaustive match over it stays exhaustive.

`rpm_sign_installed` and `rpm_sign_isolated` each record a measured sign,
plus or minus one, for the installed and the isolated meshes of the
configuration. Both are closed to coercion as well as to value, so `true`
and `1.0` are refused rather than read as `1`, and the model validates on
assignment, so the domain holds after loading and not only at it.

THE SENSE DOES NOT DETERMINE THE SIGN OF THE ROTOR SPEED, which is why
the two fields exist and why they are not derived. Going from a published
sense to the number a motion command takes needs the rotor axis, the side
of the aircraft and the handedness of the mesh actually loaded; the
installed and isolated meshes of one aircraft may be opposite hands and
then take opposite signs for the same published sense, which the one
campaign this vocabulary has been checked against was. A campaign
that established its signs by measurement records them, so a later run
reproduces the measurement rather than re-deriving it. Absence means not
established and must not be read as plus one.

Read that against `script.helpers.ROTATION_SENSE_SIGN`, which DOES derive
a sign from a sense and is not contradicted: it signs the AZIMUTH
INCREMENT, which way round the disc the blades are numbered, and that is
a different quantity from the sign of the rotor speed.

NOTHING IN THE PACKAGE READS THE PROPELLER BLOCK, the signs included and
`rotation`, `blade_travel`, `radius_m`, `n_blades` and `position` too.
The block is recorded, and setting any of it changes no emitted script on
its own. The artifact also does not reach a recipe: `resolve_matrix`
narrows it to the reference area and length the case carries, so a recipe
that wants a sign reads it from the workspace or the resolved matrix it
closes over, and `case.reference.propeller` does not exist. That absence
is now guarded by a test rather than only stated
(`test_no_module_outside_the_model_reads_the_propeller_block`).

Purely additive to the propeller block: its content validates unchanged.
The FILE still needs the kind letter this release introduced, so a
pre-0.8.0 library is migrated with `migrate_input_ids` before any of it
resolves.

`script.helpers.blade_frames` refuses an unknown sense with a message
that now ROUTES the other vocabulary rather than treating it as a typo:
a caller passing `inboard_up` or `inboard_down` is told that this is the
same fact in the vocabulary a datasheet prints, that `blade_travel`
records it, and that converting it here would need the side of the
aircraft, which is not among the function's arguments.

THE CHANGE CAME FROM A MEASUREMENT RATHER THAN FROM A DESIGN REVIEW, and
that is worth the sentence. The shipped input vocabulary had never been
checked against a real campaign's library; checked for the first time on
2026-08-19, it REFUSED that campaign's own reference artifact, on all
three counts at once. The same walk also showed why this release's
kind-letter break is right: that library's references and setups folders
each held a `003.toml` and its matrix named `003` in both columns, so a
number mistyped between REF and SET resolved to another artifact's file
with no signal at all.

**BREAKING, manifest schema.** `workspace.MANIFEST_SCHEMA` moves from
`pyfs-manifest/1` to `pyfs-manifest/2`, because
`script.BrokenCommandUse.source_version` stopped being optional and the
ABSENCE of that key therefore changed meaning.
`workspace.KNOWN_MANIFEST_SCHEMAS` is new and lists every stamp this
version can still READ, so a manifest written under the earlier schema
keeps loading rather than being refused for having been written before
the rule existed.

**BREAKING, waiver records** (PFS-2012.03).
`script.BrokenCommandUse.source_version` is REQUIRED. It names the build
whose database record says the command is broken, which is the build the
cited probe report was run on; the optional form allowed a waiver that
cites a report without saying which build it rests on, and a waiver whose
evidence cannot be located is a waiver nobody can check.

**BREAKING, run matrix** (PFS-2009.08.03). A matrix with an active row
whose `FS_BUILD` cell strips to empty, run or planned with a campaign
default that also strips to empty, raises `MatrixError` naming every such
row by row number and POL, and naming the option that supplies the
default. It is refused BEFORE the matrix is bound, so no campaign is
built, no executable is resolved and no executor is constructed.

**BREAKING, input-library ids** carry a kind letter, and the migration is
now a call rather than a rename by hand:
`workspace.migrate_input_ids(inputs_dir, matrices, apply=False)` renames
every artifact to its lettered form AND rewrites the `REF`, `SET` and
`ENTRY` cells of every matrix it is given, in the same call. A rename
that would land on an existing file, and a matrix that does not exist,
are refused before anything moves. `cases.matrix.rewrite_codes` is the
byte-for-byte rewriter under it and `cases.matrix.CODE_COLUMNS` names the
three columns that carry a library id (PFS-2009.03).

**BREAKING, and it is the one to read if you script `pyfs-matrix`:**
`parse_run_loads` and `sweep_table` already required a constructed
workspace as of this cycle; `run.cli`'s `run` subcommand now writes its
sweep table through `results.tables.write_table` rather than
`DataFrame.to_csv`, so a frame that cannot say what produced its numbers
is refused rather than written (PFS-2014.03).

**New catalogued exceptions:** `results.UnsupportedResultTypeError` and
`script.entities.ScriptDeclarationTypeError`, both keeping `TypeError` as
their second base (OPS-2009.01.08), and `post.writers.OutputExistsError`,
raised where a writer refuses to overwrite (PFS-2011.02).

**New catalogued warning categories:** `PyflightstreamWarning` and
`PyflightstreamDeprecationWarning`, in the shared-vocabulary module below
every layer. The first keeps `UserWarning` as its base and the second
keeps `DeprecationWarning` as a second base, so every filter and every
`except` a caller already wrote selects exactly what it selected. The
catalogue covers exceptions AND warnings, and both join it.

**New record fields:** `RunRecord.fs_version_source`, which says whether
a point's solver build was chosen FOR THE ROW or inherited from the
campaign default (`None` on a record that predates the field), and
`RunRecord.velocity_requested_m_s`, the free-stream velocity in m/s the
case asked for, where `None` means none was requested and is not zero.

**New elsewhere:** `cases.matrix.MatrixRow.row_number`, the row's 1-based
position among the file's DATA rows, assigned before the activity filter;
`results.to_table` now tabulates an unsteady plot report.

**BREAKING, and it is the release's headline: the verified run-matrix
layout is SIXTEEN columns** (PFS-2025.12.01). `WORKFLOW` joins the
pipe-delimited format between `RUN` and `VAR_NAMES_VALUES` and names the
workflow type that builds the row's script. It is a column of its own
rather than a pair inside `VAR_NAMES_VALUES`, because that cell is where
free case data lives and a type competing with it would be
indistinguishable from a user's own key.

A FIFTEEN-column file is RECOGNISED rather than merely rejected
(PFS-2025.12.02): the reader names it as a matrix written before v0.8.0
and names the call that fixes it, and nothing parses after that.
`pyflightstream.cases.matrix.upgrade_matrix(path, in_place=True)` adds
the column and leaves every other byte alone (PFS-2025.12.03). The
refusal messages count the width from the column list rather than
writing the number, so the next column cannot leave a stale figure in a
message.

**BREAKING: a workspace input id declares its kind** (PFS-2009.01,
PFS-2009.03). A reference, setup or group id now begins with a letter
(`r`, `s`, `e`), so a number mistyped between the `REF`, `SET` and
`ENTRY` cells of a run matrix is refused instead of resolving to another
artifact's file. The refusal names the id, the letter, the file to rename
and the matrix cell to change in the same edit. An existing library needs
its files renamed; the letter is part of the id, not a prefix the library
adds or strips.

**New module `pyflightstream.cases.workflows`** (PFS-2025.02), with
`WORKFLOWS`, `workflow_names`, and `WorkflowCoverageError` in the
exception catalog, deriving from `PyflightstreamError` and keeping
`RuntimeError` as its standard-library base.

**BREAKING: a case cannot ask for a geometric sweep and an aerodynamic sweep
at once** (PFS-2025.17, PFS-2025.17.02). A case declaring a multi-value
`angle_sweep_deg` beside a multi-point sweep is REFUSED at load time, through
both doors: `campaign.toml` and the run matrix. A file that loaded before this
release and asks for both will now stop, which is the whole point of the
change.

The reason is identity, not taste. The two sweeps MULTIPLY, into runs the case
never names, and the products cannot be told apart: a run is identified by its
aerodynamic point alone, so every geometry in the product would produce the
same `run_id` and the same output file names. Silently writing one over
another is the failure this refuses.

The refusal teaches both shapes rather than only refusing, and they are the
two things a user might mean. A rotation held FIXED across an aerodynamic
sweep is `angle_deg = <angle>`, one value, which costs one campaign. A sweep
OF the geometry is one case per geometry, each with its own `sim_id` and its
own single-valued angle.

`pyflightstream.cases` gains `ROTATION_SWEEP_KEY`, `ROTATION_OFFSET_KEY`,
`geometric_sweep_values` and `multiplied_sweep`, and the limit is stated where
a user meets it, at the declaration site, rather than in a page they would
have to already know to consult.

**BREAKING FOR AN INSTALL FOOTPRINT, not for any code: `trimesh` becomes a
RUNTIME dependency** (PFS-2025.20, PFS-2025.20.02), pinned `>=4.12,<6`. It was
previously behind the `[geom]` extra and is now installed by `pip install
pyflightstream` with nothing named. Cost, measured rather than assumed: ONE new
distribution and 3.89 MiB, and the hard dependency it drags is `numpy>=1.21`,
which this package already requires. A fresh install resolves 5.0.0, not the
4.12.2 a development tree happens to carry, which is why the envelope declares
both ends and a test asserts the installed version falls inside it.

Read that against `NFR-06`, which says the runtime dependency count does not
grow, because this release AMENDS it rather than quietly stepping over it. The
reason is recorded with the amendment: extracting a trailing edge is on the
default path of a rotor campaign, and a capability gated behind an extra makes
the library promise what a default install cannot do. The rejected candidates
are recorded too. `meshio` was refused on the committed weight budget, at five
new distributions and 12.26 MiB against limits of one and five, one of them a
syntax highlighter; `numpy-stl` was refused on capability and explicitly NOT
measured, since it reads STL where this package's seam is OBJ and it supplies no
face adjacency at all; an in-house reader was refused on the standing
engineering policy that prefers a public library for a generic need.

A BASE INSTALL CAN NOW MARK A TRAILING EDGE END TO END, and two independent
proofs say so rather than one (PFS-2025.20.03): a CI job that installs `[dev]`
alone, and an in-suite child interpreter whose meta-path REFUSES `scipy`,
`rtree`, `PyNite`, `pypdf` and `matplotlib` and then runs the whole route.

**BREAKING FOR A CONSTRAINT, and it is a constraint being LIFTED: one run
matrix may now name several solver builds** (PFS-2009.05). A matrix whose
active rows named two `FS_BUILD` values was refused outright, on the ground
that a campaign binds to exactly one installation. It runs now, and each
point's record names in `fs_exe` and `fs_exe_sha256` the executable ITS OWN
ROW asked for, with its script emitted under that build's declared version.

The version is a DECLARATION and never an inference, which is why
`inputs/executables.toml` grew a second entry shape rather than the code
growing a guess:

```toml
"26.120" = "C:/builds/26120/FlightStream.exe"
"26.123" = { path = "C:/builds/26123/FlightStream.exe", version = "26.123" }
```

A bare path means exactly what it has always meant and declares no version, so
every registry written before this release is byte-identical in behaviour; the
table declares the version that build's scripts are emitted under. An unknown
key inside the table is REFUSED naming itself and listing the keys that are
read, because a silently ignored `verison` is how a run gets emitted under the
wrong version while the file looks correct. The declared version is checked
against the version registry when the file is READ, so the refusal points at
the file that is wrong rather than at the first emission that fails.

One asymmetry is deliberate and documented at the call: a registry entry never
overrules the caller's `default_fs_version` for a row that names NO build. A
silent row falls back to the campaign default, as it always has.

`pyflightstream.workspace` gains `resolve_build` and `RegisteredBuild`, and
`CampaignWorkspace.resolve_build` beside the unchanged `resolve_executable`.
`ResolvedMatrix` gains `builds` beside an unchanged `fs_exe`.

READ THE RESIDUAL WITH IT, because it is stated rather than left to be found:
the PRE-FLIGHT still plans under one version. `plan_matrix` has no executor and
`run_matrix` pre-flights before its executors exist, so a two-build matrix is
planned against `default_fs_version` and run against each row's own. Both
docstrings say so. Closing it means constructing executors ahead of the
pre-flight, which would trade away pre-flighting away from the licensed
machine.

**New module `pyflightstream.workspace.trailing_edges`** (PFS-2025.16,
PFS-2025.20). It extracts a trailing edge from a mesh and writes it as the NODE
LIST both documented marking routes consume, through
`workspace.wake_edges.write_node_file`, which already existed and needed no
change. The criterion is the AFTMOST POINT OF EACH CHORDWISE SECTION in the
rotor frame, computed here rather than delegated: a dihedral-angle threshold is
the crease criterion, which is exactly what this capability exists to escape,
because a strongly twisted blade has a trailing edge that is not a crease.
READ THE FRAME PRECISELY, because it is the one thing here a reader can act
on wrongly. The rotor frame is where the CRITERION is computed: the axis and
the hub define the spanwise and tangential directions that decide which end of
a section is aft. The COORDINATES returned are selected mesh vertices, never
transformed, so they are an `(n, 3)` array in the MESH's own reference frame
and length units. The unit is declared once, at `write_node_file`, because a
mesh file does not carry one.

`pyflightstream._mesh` is where the mesh library is imported, through ONE lazy
accessor, on the precedent `_digest.py` set: it sits below every layer rather
than becoming a third hand-rolled copy of the same import guard.

**New public names in `pyflightstream.workspace`:**
`CampaignWorkspace.open`, `check_unique_stems`, `STEM_REGISTERED_KINDS`,
`expand_group`, `CampaignWorkspace.expand_group`, `reference_points`,
`reference_point`, `ReferencePoints`, `check_reference_point_names`,
`extract_trailing_edge`, `TrailingEdge`, `write_trailing_edge_node_file`,
`resolve_build`, `RegisteredBuild` and `CampaignWorkspace.resolve_build`.
`DEFAULT_SECTIONS` and `MINIMUM_SECTION_VERTICES` stay reachable as
`pyflightstream.workspace.trailing_edges.*` rather than at the package,
deliberately: they are the extraction's own tuning constants and not part
of the promise the package namespace makes.
`RunRecord.broken_commands` is annotated `list[BrokenCommandRecord]`,
a new `TypedDict` mirroring the script-layer record field for field.

**In `pyflightstream.results`:** `write_table`, `DATA_ORIGIN_CODES`,
`REDUCTION_CODES`, `REDUCTION_WINDOW_CODES`, `REDUCTION_WINDOW_COLUMN`,
`origin_code`, `reduction_code`, `reduction_for_solver_mode`,
`window_for_reduction`, `EXPORT_CONVERSIONS`, `ExportConversion`,
`export_conversion` and `require_export_parser`; `sweep_table` gains
`require_loads`; `PROVENANCE_COLUMNS` widens from two labels to three.

**In `pyflightstream.script`:** `helpers.blade_frames`,
`helpers.AZIMUTH_BASIS`, `helpers.RotationSense`,
`helpers.ROTATION_SENSE_SIGN`, `helpers.rotate_surfaces`,
`helpers.unsteady_action`, `helpers.mark_wake_edges`,
`UnsteadyActionUse`, `Script.unsteady_actions`, `Script.pending_actions`
and `Script.registry`. `RotationSense` is the SINGLE HOME of the sense
vocabulary: `workspace.inputs.PropellerReference.rotation` imports it
rather than restating the two words, which is a downward import the
layer rule permits, and a test refuses a second declaration.
In `pyflightstream.workspace.wake_edges`,
`write_node_file` and `node_file_units`.

**In `pyflightstream.cases`:** `DerivedFrom`, `Campaign.derived_from`,
`Campaign.is_derived`, `derived_body_sha256`, `stamp_derived_campaign`,
`ExportWindow`, `export_window`, `ReductionPlan` and `reduction_plan`.

**`pyfs-matrix run`, a third subcommand** (PFS-2025.09), taking a matrix
all the way to manifest records and a sweep table. `--workflow CODE=NAME`
maps an FS_SCRIPT code onto a run type, `--sweep-csv` names the table,
and `--resume`, `--workspace` and `--fs-exe` behave as on `plan`.

**`results.tables.to_csv` refuses a table carrying no `data_origin`,
`reduction` or `reduction_window`**, raising `MalformedOutputError`. Every table this package
builds carries them, so a caller passing a parsed result is unaffected; a
caller passing a hand-built frame is not.

**The run matrix is split across the layers it actually uses**
(OPS-2007.01, PFS-2009.05). `pyflightstream.cases.matrix` now holds the
reader and the converter and nothing that plans or runs: `MatrixError`,
`MatrixRow`, `read_matrix`, `to_campaign`, `convert_matrix`, and the names
the sixteenth column brought with it (`CODE_COLUMNS`,
`DEFAULT_VERSION_OPTION`, `LEGACY_WORKFLOW`,
`refuse_silent_rows_without_default`, `rewrite_codes`, `upgrade_matrix`,
`workflow_types`). `ResolvedMatrix` and `resolve_matrix`
moved to the new `pyflightstream.workspace.matrix`, which is where the
input library they bind against lives; `plan_matrix` and `run_matrix`
moved to the new `pyflightstream.run.matrix`, which is where the campaign
loop they compose lives. No shim and no re-export: import from the new
module. Nothing about the matrix format, the flags, the records or the
behaviour moved with them.

The reader used to reach up into both layers through five imports written
inside its function bodies plus two under `TYPE_CHECKING`, which recorded
the dependency while hiding it from every module-level reader. The count
is now zero at every level and a tier-1 test holds it there.

**`pyfs-matrix` is the same command from a different module.** The
console entry point is now `pyflightstream.run.cli:main`, and
`pyflightstream.cases.cli` is REMOVED. The command name, both
subcommands, every flag and every line of output are unchanged, so
nothing a user writes changes; what moved is the dotted module path. A
command line that plans a campaign composes the workspace input library
with the campaign pre-flight, so it belongs at or above both, and it sat
two layers below what it drove. It moved in the SAME change as the
reader, because in between the tree carries a module-level cases-to-run
import and no commit could be green on its own.

**BREAKING: `parse_run_loads` and `sweep_table` require a constructed
`CampaignWorkspace`** (OPS-2009.02.05). Both used to accept the campaign
root as a path as well and build the workspace themselves, which made the
results layer import the execution layer above it. The import was
deferred to call time, which changed nothing about the direction and only
hid it from a module-level reader, so the convenience is gone rather than
blessed as an exception. Write `sweep_table(CampaignWorkspace(root))`
instead of `sweep_table(root)`. Passing a path now raises
`MalformedOutputError` with the import line and the corrected call in the
message; it is a catalogued class keeping `ValueError` as its second
base, so an existing `except ValueError` still catches. Every shipped
example and doc page already passed a constructed workspace.

**BREAKING: `post.write_vtk_points` and `post.write_tecplot_points` take
a required keyword-only `provenance` and return `(output, record)`**
(PFS-2012.11, FR-31), rather than a single path. New public names:
`post.OutputProvenance`, `post.settings_records`,
`post.writers.provenance_path`, `post.writers.PROVENANCE_SCHEMA` and
`post.writers.PROVENANCE_SUFFIX`.

**`InputArtifactError` is defined in `pyflightstream._errors`, below every
layer** (OPS-2007.02.01). Both bases and all three attributes (`kind`,
`artifact_id`, `available`) are unchanged, and it is still imported from
`pyflightstream.workspace` and `pyflightstream.exceptions`, which resolve
to the same object; nothing a user catches changes. It moved because more
than one layer names it, and an exception type is vocabulary rather than
behaviour: leaving it in the layer that raises it made the layers that
catch it reach upward for the name alone.

**`SimCase` gains an optional `fs_build`; `pyflightstream.run` gains
`SolverBuild`** (PFS-2009.05), and `run_campaign` and `plan_campaign`
take a `builds` mapping from that id to a `SolverBuild`.

**New modules on the affirmed public surface:**
`pyflightstream.post.reductions`, `pyflightstream.post.settings_table`,
`pyflightstream.post.unsteady`, `pyflightstream.run.cli`,
`pyflightstream.run.matrix`, `pyflightstream.workspace.matrix`,
`pyflightstream.workspace.trailing_edges` and
`pyflightstream.workspace.wake_edges`. **Removed:**
`pyflightstream.cases.cli`.

**New public names elsewhere:** in `pyflightstream.script.helpers`,
`RelaxedTrailingEdge`, `parse_relaxed_trailing_edge`,
`resolve_shedding_direction`, `RELAXED_SHEDDING_DIRECTIONS`,
`DEFAULT_SHEDDING_DIRECTION` and `RotationSense`; in
`pyflightstream.cases.workflows`, `ROTOR_SHEDDING_VARIABLE`,
`rotor_shedding_direction` and `rotor_relaxed_trailing_edges`; in
`pyflightstream.cases`, `ROTATION_SWEEP_KEY`, `ROTATION_OFFSET_KEY`,
`geometric_sweep_values` and `multiplied_sweep`;
`pyflightstream.results.parse_unsteady_plots`
and `UnsteadyPlotsReport`; in `pyflightstream.qa.compat`,
`EXECUTABLE_BASELINE_REPORT`, `read_executable_baseline`,
`classify_executable`, `ExecutableIdentity`, `ExecutableVerdict`,
`licence_sensitive_candidates`, `LicenceCandidate` and
`MEASURED_STATUSES`. `ProbeRun` and `PhysicsRun` gain `fs_exe_sha256`;
`DriftRun` gains `fs_exe_sha256s`. `COMPAT_SCHEMA` is unchanged at
`pyflightstream-compat-report/1`.

**Changed shape, not a new name:** `pyflightstream.utils.manual.citation_reach`
returned two-slot lists and now returns mappings keyed by
`CITATION_REACH_OUTCOMES`. A caller reading the old shape by index must
move to the keys.

`pyflightstream.fsi.config_hash` is RENAMED `config_sha256`, and so are its
two package exports, the `FsiState.config_sha256` field and the
`check_state_matches_config(config_sha256=...)` keyword (OPS-2009.01.14).
The name now states the algorithm, matching `RunRecord.script_sha256` and
`outputs_sha256`, so a reader meeting the value in a saved state or a
convergence log can tell what it is without opening the code. An approved
public break for 0.8.0 under NFR-20's pre-1.0 clause: there is no shim and
no deprecation warning, because `_deprecations.DEPRECATED_MODULES` models
module shims only and a function-name row there fails tier 1.

`pyflightstream.qa` gains eight names, all new and none renamed or removed
(PFS-2018.02): `BuildComparison`, `BuildKey`, `CostCell`, `CostView`,
`PointCost`, `PointKey`, `cost_rows` and `cost_view`, from the new
`pyflightstream.qa.cost`. The physics report schema is unchanged at
`pyflightstream-physics-report/1`; an earlier reading of this work would
have bumped it to `/2`, which would have made every committed
`reports/physics/PHY-*.yaml` unreadable through `read_physics_report`, and
`tests/test_qa_cost.py` now guards that it stays put.

`scripts/gen_requirements_index.py` takes its inputs as arguments,
`collect(srs_dir)`, `traceability(ids, tests_dir)` and
`build(srs_dir, tests_dir)`, so a deliberately malformed page can be fed to
it in a test (OPS-2005.09). The command line is unchanged and still writes
`reports/requirements-index.json`. A new `MalformedRequirementPageError`
carries every problem found rather than the first.

One new module, `pyflightstream.qa.reports`, exporting `report_paths`,
`refuse_existing_report` and `resolve_report_date`, all three re-exported
from `pyflightstream.qa`:
the one home of the report-naming and never-overwrite rule the three
evidence writers share, including the build key each of them used to
derive for itself. Each series keeps a helper of its own that calls it,
so a writer and the pre-flight protecting it ask one question rather
than two that agree by coincidence: `compat_report_paths`,
`physics_report_paths` and `drift_report_paths`, all three new in this
cycle and all three re-exported from `pyflightstream.qa`. Each resolves
its version through the registry before naming anything, so asking with
a vendor release name cannot predict a stem the writer will not produce,
and `resolve_report_date` refuses a date that is not `YYYY-MM-DD` rather
than putting it in a file name.

Other new public names in `pyflightstream.qa`: `ProbeOutcome.REMOVED`,
`unrecognised_commands`, `read_compat_reports`, `contradicting_evidence`,
`Judgment` and `PROMOTABLE_OUTCOMES`. In `pyflightstream.qa.physics`,
`PhysicsCase` and `case_table`, which were reachable as the element type
of two exported inventories and as the function this release breaks, and
were missing from the module's own list. In `pyflightstream.qa.geometry`:
`mean_edge_length`. One new keyword argument: `reports_dir` on
`apply_compat`; `translation_m` on `wing_triangles` and
`generate_wing_stl`, and `name` on `generate_wing_stl` alone, all
keyword-only. `wing_triangles` returns an array and has no solid to name.

New public names in `pyflightstream.utils.manual`, the maintainer reading
layer: `EditionDelta`, `EditionVerdict`, `documentation_delta`,
`read_edition` and `insert_version_row`, which are what `pyfs-manual
register` is built on, plus `Reachability`, which was reachable as the
return type of an exported function and was missing from the subpackage's
own list. One new module, `pyflightstream.utils.database`, exporting
`register_edition` and `Registration`: the registration transaction,
which was written inside the argument parser and is now importable and
testable. One new command-line surface: the `register` subcommand of
`pyfs-manual`.

**Incompatible changes: four, and ONE of them is quiet.** The first
breaks loudly, the second is the quiet one, and the third replaces a
quiet success with a loud refusal.

- `PhysicsCase.versions` is now `PhysicsCase.minimum_version`, and its
  type changed from a tuple of canonical identifiers to `str | None`.
  `PhysicsCase` is public API (`pyflightstream.qa.physics` is an affirmed
  public module), so this is a break, and it is a LOUD one:
  `PhysicsCase(versions=...)` is a `TypeError` and `case.versions` an
  `AttributeError`. No shim: the deprecation regime binds from a stable
  release and the ledger covers modules rather than fields, so a pre-1.0
  minor may rename with this line.
- `case_table()` now emits the key `minimum_version` where it emitted
  `versions`. This is the quiet one and it is why the key moved rather
  than keeping its name: the VALUE became a sentence when the field
  became a minimum, so `if "26.123" in row["versions"]` stopped being a
  membership test over identifiers and became a substring test over
  English, answering False for 26.123 and True for 26.120. A missing key
  raises; a changed meaning does not.
- `run_physics` and `run_drift` now REFUSE a build on which any requested
  case has no command evidence, where they used to run the supported
  subset and report success. `pyfs-qa physics --fs-version 26.100` used
  to run four cases and write a report; it now exits 2 and names the
  runnable subset. Pass `cases=` (or `--cases`) to ask for a subset
  deliberately.

A FOURTH, and it is the cheapest one on this list: FIVE boolean
arguments became keyword-only. `half` on `wing_triangles`,
`generate_wing_stl` and `build_phy02_script`, and `include_smi` on
`registered_cases` and `case_table`. On `build_phy02_script` THREE
MORE parameters moved with it, `stl_path`, `loads_name` and
`log_name`, none of them boolean: `half` sat immediately after
`version`, so the star had to go there and swept the rest of the
signature. It is the only one of the five with collateral, its
sibling `build_phy01_script` still takes those three positionally,
and every in-tree caller of both already used keywords. The count read four until the fifth
signature was found by a review pass, in the same module as two of the
others; a sweep that stops at the sites review named is not a class fix,
which is this repository's own rule and is why the number is stated
rather than the word. `wing_triangles(spec, True)` was legal and read as nothing
in particular; so did `case_table(True)`. The debt is paid in the window
this release already opens rather than in the next one, because paying it
later would be a SECOND break for the same callers and for the same
functions, three of which are being broken here anyway. Every caller in
this repository, in its tests, its scripts and its one shipped example,
already passed these by keyword, so nothing in the tree moved.

**Deprecations: ONE, and this line said "none" until 2026-08-20.**
`plan_matrix(fs_version=...)` and `run_matrix(fs_version=...)` are
deprecated in favour of `default_fs_version` (PFS-2009.08.01). The old
spelling still works and warns with `PyflightstreamDeprecationWarning`.

The rename is not cosmetic: beside a per-row `FS_BUILD` column,
`fs_version` reads as an OVERRIDE of that column, and it is the opposite,
the version that rows naming NO build fall back to. The `pyfs-matrix
--fs-version` command-line flag is unaffected and keeps its spelling.

The removal release is not named, because NFR-20 does not bind before 1.0
and the number is a seat decision. That this line is the one a
downstream reader greps to decide whether an upgrade breaks them is why
it is corrected here rather than at the next release: publishing it false
costs the reader the whole warning window the shim exists to buy.

### Added

- **Five parsers for the six exports that had none, each written against
  a real observed file** (PFS-2014.02). Five functions rather than six
  because `parse_surface_sections` answers for both surface-section
  commands, on the evidence below. `parse_force_distributions`,
  `parse_off_body_streamlines`, `parse_surface_sections` (which answers
  for BOTH surface-section commands, on the evidence that the two
  captures carry the same banner, count label, twenty-column header and
  `Edges=` block structure), `parse_sweep_spreadsheet` and
  `parse_solver_analysis_csv`. With them: `ExportSolution`, the solution
  block all four text formats print identically, plus one typed report
  per format and the record types `OffBodyStreamline` and
  `SurfaceSection`; the column pins `FORCE_DISTRIBUTION_COLUMNS`,
  `OFF_BODY_STREAMLINE_COLUMNS`, `SURFACE_SECTION_COLUMNS`,
  `SWEEP_COLUMNS` and `SOLVER_ANALYSIS_CSV_COLUMNS`; and
  `SOLVER_ANALYSIS_CSV_FIELD_UNSTATED`. `to_table`, `to_csv` and
  `write_table` accept all five.

  **THE CSV'S FOURTH COLUMN IS NOT LABELLED, deliberately.** That export
  writes no header at all, so the columns cannot be read from the file.
  The first three are settled by MEASUREMENT rather than inference:
  column one takes exactly the seven cosine-spaced chordwise node
  stations of the captured mesh, column two exactly its seven spanwise
  stations, and column three the NACA 0012 half-thickness at each, so it
  is a node-based export as the entry's note says. The fourth is a
  pressure coefficient and not a pressure in the units the call names,
  which the surface-section export from the same run confirms. WHICH
  coefficient cannot be settled: that run set the reference velocity
  equal to the free-stream velocity, so `Cp` and `Cp_ref` are identical
  to seven digits and the two tokens are indistinguishable from the
  numbers. So the column is `scalar`, the caller may declare the token,
  and the table carries `scalar_field` with the word `UNSTATED` where
  nobody said. A word rather than an empty cell, because an empty cell
  reads back as NaN.

  Two further readings are recorded in the code rather than smoothed
  over. Every streamline in the captured file declares 31 points and
  writes 30; nothing settles what the extra one is, so the declared
  count is recorded verbatim and never equated with the rows, and a test
  pins the off-by-one as a measurement so a build that changes it goes
  red rather than silent. A section declaring zero edges is RETURNED as
  an empty section rather than refused, because the file declares it.

- **A completed sweep leaves its table beside its runs without anyone
  asking** (PFS-2014.03). `run_campaign` writes `post/campaign_sweep.csv`
  at the end of its third pass, one row per point, with the integrated
  forces and, for an unsteady point, the solver's own time average with
  the window token beside it, so no row is ambiguous about what produced
  its numbers.

  TWO THINGS ABOUT WHEN IT IS WRITTEN, because both are the point rather
  than details. It is written BEFORE `CampaignErrors` is raised, so a
  campaign whose every point failed still leaves the table this exists to
  leave. And a failed write costs the campaign nothing: it is reported as
  a warning naming the exception, the target and the call that rebuilds
  the table, because a sweep that ran is not undone by a table that did
  not.

- **The two field writers and the coupling drivers refuse a silent
  overwrite** (PFS-2011.02). The VTK and Tecplot point writers refuse an
  existing path naming the file, with `overwrite=True` the only way
  through; a script emitting the same probe export path twice is refused
  naming BOTH call sites rather than the second one; and `coupling_step`
  refuses a run folder that holds a convergence log with no state beside
  it, naming the log. Each refusal names what to do instead.

- **An explicit classification of every export command, with the debt
  named one file at a time** (PFS-2014.02). `results.EXPORT_CONVERSIONS`
  says which exports read and tabulate, which formats are deliberately
  outside the default conversion set, which carry the export phase and
  write no file at all, and which are debt; `require_export_parser`
  refuses each missing one BY NAME rather than in the aggregate.

  READ THE COUNT WITH IT. **Ten of the eleven default-set exports now
  read and tabulate**, up from four, and the eleventh is not an omission:
  `EXPORT_BL_VELOCITY_PROFILE` is the one format nobody has observed,
  because IT IS INTERACTIVE. It opens a modal window carrying a plot and
  a Done button, and script processing stops there until a person
  dismisses it, even under `-hidden` with both standard streams
  redirected. That was measured on 26.122 and recorded in
  `reports/RPT-027` on 2026-08-17; `reports/RPT-037` adds that it happens
  on 26.123 too, across three unattended runs that returned nothing on a
  mesh which solves in two seconds. Its classification note now carries
  that reason in place of "no observed export captured", which had come
  to read as though nobody had tried. No status moved: `broken` travels
  only through the sanctioned probe path, and in any case "opens a
  window" is not the claim "the solver rejects it".

  Every new parser is written against a REAL observed export, captured on
  a licensed solver and committed as a fixture. The captures are
  deliberately small: the same wing at 6 by 6 panels writes the same
  FORMAT in a few kilobytes, where the mesh a physics reference wants
  produces a 508 KiB force distribution. A parser is pinned by the shape
  of a table, its header, its terminator and its column names, and none
  of those vary with panel count; no coefficient in any of those fixtures
  is evidence of anything.

- **A Tier 1 guard binding the examples run's promotion to the categories
  the package actually raises.** It derives the six command homes from
  the tracked tree rather than listing them, asserts they all spell the
  SAME filter, drives a warning of each kind through a real pytest under
  both the shipped filter and the narrowed one, and refuses a narrowed
  filter while any warning site still names a foreign category. The
  ordering rule is enforced rather than described.

- **`results.to_table` refuses an unsteady plot export whose plot name
  collides with a provenance column.** Plot names are the user's own, so
  stamping the provenance over one would have replaced a column of
  physical numbers with a constant token and left a table that still
  writes and still looks right.

- **A workflow: a run type the package builds by itself** (PFS-2025.02),
  named by the run matrix's `WORKFLOW` column and resolved by TABLE
  LOOKUP, never by import. Two types ship: `steady`, one point of a
  polar, and `unsteady_rotor`, a rotor coordinate system, one rotary
  motion at the row's RPM about the row's axis, and a physical time
  loop. The matrix reader asks the registry for the accepted set at call
  time rather than keeping a second list, so a type cannot exist in one
  place and not the other.

  **A workflow declares the commands it always emits and DERIVES the
  solver builds it covers from the command database** (PFS-2025.18).
  Asked for a build outside that range it refuses BEFORE emitting its
  first line, naming the build received, the covered builds in release
  order, and the commands whose absence excludes it. It refuses about
  the ENVIRONMENT rather than about an argument, which is why its
  standard-library base is `RuntimeError`; that choice is the lane's
  default and is a public contract callers catch on, so it is a marked
  proposal until the owning seat rules.

- **`pyfs-matrix run` takes a matrix from trigger to reductions**
  (PFS-2025.09). **IT REVERSES A DECISION RECORDED IN THE TOOL ITSELF**,
  whose docstring said there was deliberately no run subcommand, because
  the solver-quality judgment and the recipe registry are code and not
  command-line strings. The lane built it under that reading and does not
  own it: the reversal is for the domain seat to confirm.

- **The window the expensive exports and the unsteady reductions apply
  over, counted BACKWARDS from the end of the run** (PFS-2025.08). State
  it in degrees of rotor rotation, in solver steps or in revolutions; the
  record carries the form you wrote beside every form it derived, so a
  later reader can tell which was which. An angular window with no rotor
  speed or no time step is refused naming what is missing rather than
  assuming a default.

  `reduction_plan` says which windows the four reductions of one unsteady
  rotor case are taken over (PFS-2025.06): the export window for the time
  average, one blade passage for the phase-locked average, and one window
  per blade of the last revolution for the per-blade split. The raw
  series is FIRST in the list and is never replaced by a reduction.

- **One motion-following coordinate system per rotor blade**
  (PFS-2025.04), placed arithmetically at 360/N from a first blade that
  must lie on a quadrant, each with its x axis radial and its z axis
  along the rotor axis. THE AZIMUTH DATUM IS A NAMED TABLE rather than
  arithmetic scattered through the emitter, because it is the one
  convention on this release whose wrong value produces plausible numbers
  rather than a failure: a wrong datum rotates every blade frame and
  every phase-locked reduction keyed to blade index. The table is the
  lane's proposal and the owning seat's to rule on; changing it is one edit
  and not a search.

- **`rotate_surfaces` rotates existing mesh surfaces about an axis of a
  named coordinate system** (PFS-2025.14), choosing between the two
  spellings from the script's own build, because the capability changed
  name and grammar at 26.122. Selecting a component turns all N blades in
  one call.

- **`unsteady_action` registers an action the solver runs after each
  unsteady time step** (PFS-2025.07), so sections come out mid-run rather
  than by stopping and restarting. The record it returns carries the
  command's recorded evidence status on that build and whether it was
  inherited, so a caller can tell a measured capability from an inherited
  one without leaving the call.

- **`mark_wake_edges` marks wake edges from an imported node list**
  instead of by the angle criterion (PFS-2025.13), and refuses on a build
  that does not document the import, naming the build, the route and the
  angle criterion it will NOT substitute unasked.
  `wake_edges.write_node_file` writes the list the import reads, from an
  `(n, 3)` array plus a declared length unit, refusing an empty list, a
  wrong shape, a non-finite coordinate, an unrecognised unit token and an
  existing destination (PFS-2025.16.02). Whether the solver ACCEPTS the
  layout is open until a committed probe report says so.

- **A campaign file the package generated says so in the file**
  (PFS-2009.07.01). A generated `campaign.toml` carries a table naming
  the matrix it came from, the moment it was written and two digests, so
  a copy carried out of its folder still says where it came from.
  Running an EDITED derived campaign is refused naming the matrix
  (PFS-2009.07.02); with no matrix, an authored campaign is the source
  and is treated as one (PFS-2009.07.03), which is what keeps the
  refusal from catching every hand-written campaign in existence.

- **The pre-flight groups the matrix by build and checks each build
  once** (PFS-2009.09.01), and a row whose build fails identity stops the
  campaign BEFORE a seat is spent (PFS-2009.09.02). It composes the
  identity machinery that landed the day before rather than writing a
  second one.

- **Named reference points, declared once** (PFS-2025.15). `ARP` is the
  airframe reference point and the engine one is `ERP`, or `ERP1` through
  `ERPn` with more than one propulsor; a name outside the convention is
  refused. A named boundary group expands to `{name}1` through `{name}N`
  over its members' 1-based positions in declared order (PFS-2025.03), so
  a blade group resolves identically on every re-resolution.

- **An input library in which two files answer to one id is refused when
  the library OPENS** (OPS-2005.08.05), naming the stem and the full path
  of every file carrying it, rather than lazily at the resolution that
  happens to hit it. `CampaignWorkspace.open` is the validating
  constructor and `check_unique_stems` is the same rule as a callable.

- **Every table the results layer builds carries `data_origin`,
  `reduction` and `reduction_window`** (PFS-2014.05, and the window at
  PFS-2014.03), so a reader can tell a direct integration from a time
  average, AND over what window, with the one file in hand. `data_origin`
  is `raw` for anything read off a solver export and `reduced` for
  anything post-processing produced; `reduction` is `none`,
  `time_average` or `unknown`; `reduction_window` is `not_applicable`
  where nothing was averaged, `not_printed` where the solver averaged and
  its spreadsheet printed no window, and `unknown` where the solver mode
  itself never printed, so whether anything was averaged is unknown too.
  `results` gains `REDUCTION_WINDOW_CODES`, `REDUCTION_WINDOW_COLUMN` and
  `window_for_reduction` as public names, and `PROVENANCE_COLUMNS` widens
  from two labels to three: a consumer that UNPACKED the pair breaks on
  the widening, which is why it is announced here rather than noticed
  later. THE VOCABULARY IS A SEAT DECISION and this is the lane's
  default: a failed row with no loads report says `unknown` rather than
  `none`, because `none` would assert a direct integration that never
  happened. The published integer codes are APPEND ONLY: a published
  integer never changes meaning, because a file written last month is
  read with today's table.

- **An explicit classification of every export command the database
  carries** (PFS-2014.02). The debt is ENUMERATED rather than described,
  so the acceptance's own sentence can be checked against it. THE COUNTS
  ARE NOT REPEATED HERE and this bullet used to carry them: it said four
  parsed and seven owed, which was the census when the classification
  landed and not the one this release ships. `EXPORT_CONVERSIONS` owns
  that fact and the parsers entry above states the release's own figures;
  a second home for a count is how the two came to disagree inside one
  section.

- **`sweep_table(..., require_loads=False)`** returns the identity rows it
  has already assembled, with a warning, where it used to raise because
  no run yielded a coefficient table (PFS-2014.03). The default is
  unchanged. It exists so a campaign whose points all failed can still
  leave a table a colleague can open.

- **A campaign can send some of its cases to a different solver build**
  (PFS-2009.05). A case naming a build is RECORDED against that build's
  executable, its sha256 and its version, and its script is emitted under
  that build's version, so a study across two installations no longer has
  to lie about which one produced a point. A case naming no build runs
  and records exactly as before. A case naming a build the mapping does
  not carry is refused before anything is staged, rather than falling
  back to the campaign's executable, because that fallback is the record
  this exists to prevent. The build's version is DECLARED in
  `SolverBuild` and never inferred from an executable path or a build id.

  THAT SEPARATE DECISION WAS TAKEN LATER IN THIS SAME RELEASE, and this
  paragraph said the opposite until 2026-08-20. It read "the run matrix
  still refuses a second `FS_BUILD` value", which was true when the
  campaign-level capability landed and stopped being true when
  PFS-2009.05 closed. The rule that was missing is now the registry's
  second entry shape: a build's version is DECLARED beside its path in
  `inputs/executables.toml`, never mapped from the build id. See the
  multi-build matrix entry above, which is the successor to this
  sentence.

- **A tier-1 layering guard with an EMPTY permitted set** (OPS-2007.02.03).
  Any import inside a function body that resolves to a module in a higher
  layer now fails the suite, with no allowlist, no per-module skip and no
  exception list, because deferring an import to call time does not
  change its direction. Layer rows are read from
  `pyflightstream.overview`, the single home of the stack, so the guard
  spells no layer name of its own. It deliberately does not fire on a
  side branch with no layer row, on a same-layer import, or on a
  standard-library or third-party one, and each of those shapes is
  measured rather than asserted in prose.

- **Every table the results layer returns pins its complete column set**
  (OPS-2009.01.03). The loads frame, the probe-point frame and the sweep
  table each carry a label-to-meaning literal beside the run row's, so a
  column added, dropped or renamed is a deliberate two-file edit. The
  loads frame was pinned only at its first four and last two columns, the
  sweep table only by three per-name lookups, and the probe-point frame
  was compared against the report it was built from and therefore could
  not fail at all. Column ORDER is still not part of the NFR-19 promise
  and is not asserted.

- **`pyflightstream.results.parse_unsteady_plots` reads the unsteady plot
  export** (PFS-2015.02.02), the only file this package reads that
  carries one row per TIME STEP rather than one converged state. The
  report gives the plot names in file order, the step count and one array
  per column, resolved by label through `series()`; the column ORDER is
  data and not a contract. It refuses a duplicated or unnamed column, a
  cell that is not a solver-printed number and a row narrower or wider
  than the header, each naming the step and the column it read, and it
  refuses a probe export outright rather than reading a table of
  positions as a history.

  READ THE GROUNDING WITH IT, because it decides what the parser can be
  trusted for. No export of that command exists in this repository: the
  row and column meaning is the manual's, the DELIMITER is documented
  nowhere and is assumed to be a comma because every other table export
  of this solver uses one, and the committed fixture is SYNTHETIC and
  says so in its own first line. A file delimited some other way is
  refused by the anchor rather than misread. The command's database entry
  stays at `documented` and a real export is owed before the parser can
  be called verified.

- **`pyflightstream.post.unsteady`, the per-timestep reader and the
  blade-passage average** the post layer's own docstring had advertised
  since v0.5.0 without having (PFS-2015.01, FR-20).
  `read_timestep_series` reads the frames of an animation export back as
  one ordered series, in either of the two data filetypes that command
  documents. It takes the order from EVIDENCE and never from a file name:
  the caller declares that the sequence is already in solver order, or
  each frame carries its own solution time, and it REFUSES when it has
  neither, saying that settling the vendor's frame naming needs one
  licensed run and a committed probe report. `blade_passage_average`
  averages a declared window of solver steps and is the only
  implementation of that average in the release; `passage_windows` hands
  out the successive passages so a phase-locked reduction composes it
  rather than duplicating it.

- **`pyflightstream.post.reductions`, the writing seam** that holds the
  rule a reduction never overwrites the file it came from and the time
  series keeps its own dedicated file (file rule of 2026-08-16).
  `write_series` writes the history; `write_reduction` refuses a
  destination equal to any file the reduction read, refuses an average
  whose series file is missing or is not beside it, and refuses an
  existing destination. The rule lives at the seam rather than in a
  workflow, so a caller who bypasses the workflow cannot obtain an
  average with no history beside it.

- **Every post-processing file carries the settings that produced it**
  (PFS-2012.11, FR-31). Every file either flow-visualization writer
  produces is now accompanied by `<name>.provenance.json`, carrying the
  run identity, the campaign, the FlightStream version and the COMPLETE
  solver-flag record: all 65 flags, each with its value, its provenance
  and its citation, with a flag nobody has established for that build
  present and named `unknown` rather than omitted. A post-processing file
  previously had to be joined back to `runs.json` to learn what produced
  it, and a file that needs another file is not self-contained: delete
  `runs.json` and the numbers survived while their meaning did not.

  The record's suffix is APPENDED rather than substituted (`ring.vtk` is
  described by `ring.vtk.provenance.json`), because two exports of one
  survey share a stem and a stem-named record would be one file
  describing both. The no-silent-overwrite refusal covers the record as
  well as the data file, and neither is written when either is refused.

- **`pyflightstream.post.settings_table` and the page that freezes it,
  `docs/settings-codebook.md`** (PFS-2012.12). An OPTIONAL all-numeric
  projection of a solver-setup snapshot, for tools that cannot read
  strings, tidy by default and wide on request. Every column is numeric
  and no column carries two meanings: the value columns hold values only,
  and unknown is expressed by the provenance code with the value columns
  empty, because a sentinel may only appear in a column whose domain the
  library controls. A caller may ask for empty CODE cells to be filled;
  asking to fill a value column is refused, naming the flags whose legal
  range contains the fill. A list-valued flag contributes its length and
  the file's own legend says the form is lossy. Every file names the
  codebook version that wrote it, and reading a file written under
  another one is refused rather than silently reinterpreted. It is lossy
  by construction and never replaces the full record.

- **`docs/workspace-and-workflows.md`, the page a newcomer reads**
  (PFS-2025.21, NFR-01d). It explains what a workspace is and what the
  path from a filled-in run matrix to results actually does, in plain
  language before any signature, and then walks that path end to end.
  Every artefact on it is LIFTED from the test suite rather than written
  for the page: the matrix is a committed fixture byte for byte, and the
  input library, the recipe, the call and the four run identifiers are
  those of an executed test. A tier-1 guard holds the two together, so
  the page cannot drift from the suite without the suite going red. It
  also states plainly what is NOT built. That clause used to end
  "including that there is no workflow object in the package", which
  stopped being true LATER IN THIS SAME RELEASE, when `cases.workflows`
  shipped `Workflow` and `WORKFLOWS`; the entry further down recording
  that the page corrected itself is the surviving statement, and this
  one no longer contradicts it. The "Planned next" bullet on the
  documentation home page that promised this walkthrough is retired
  against it.

- **`SET_OUTLET_TRAILING_EDGES`, the 26.123 spelling of
  `SET_OUTFLOW_TRAILING_EDGES`** (PFS-2026.05). The newest edition
  renames the command in the chapter body and in the Script Index alike,
  with no transitional spelling documented, so a script written for
  26.122 stops working on the build issued after it. The database carries
  both names rather than one name with an alias field, and the old one
  gains a `removed` row on 26.123 naming the successor: emitting it there
  is refused with the successor's name and the page of the edition that
  documents it. Nothing was probed; the row counts a document.

- **QA reports identify the executable by its hash as well as by its
  name** (PFS-2026.17). The compat, physics and drift writers put the
  digest in the YAML beside `fs_exe` and in the rendered Executable row,
  and write it as null rather than omitting it when no digest was
  measured. The vendor installer gives four registered builds one file
  name and three more another, so a report naming one could not say which
  binary produced it. The 27 committed compat reports are untouched and
  never back-filled: a digest nobody measured cannot be recovered from a
  basename.

- **The identity question a replacement executable answers before any
  seat is spent** (PFS-2026.15). `classify_executable` and the baseline
  in `reports/RPT-032_executable-identity-baseline_2026-08-19.md`, the
  digests of the nine executables in hand, measured by hashing files with
  no solver started. An unchanged binary transfers its evidence untouched
  and spends nothing; an unknown one authorises the identity-only probe
  and nothing else; a printed build number that disagrees with the
  registry refuses with both numbers.

- **`licence_sensitive_candidates`, deriving the command rows a licence
  change could falsify for one build** (PFS-2026.16). A licence changes
  what the solver permits, so it can only falsify evidence that came from
  RUNNING the solver; a `documented` row rests on a manual page and is
  not a candidate. The function proposes candidates grouped by the
  chapter split and deliberately writes no membership: which of them a
  licensed seat is spent re-measuring is a seat judgement.

- **`tests/test_release_readiness.py`, a tier-1 guard that refuses a
  0.8.x release while 26.123 is unevidenced** (PFS-2026.14), naming that
  build as the release's LAST step rather than as one item among many. It
  requires four committed artefacts to be PRESENT and asserts no
  threshold on the number of commands absent on that build, which it
  prints instead. The `release` skill's first pause point carries it.

- **A licence-evidence card for every distribution the `[dev]` extra
  installs** (OPS-2009.02.01, PFS-2022.01.03),
  `reports/RPT-033_development-tool-licences_2026-08-19.md`, closing the
  gap RPT-016 registered in its own verdict on 2026-08-03. Each card
  names the version read, the metadata FIELD it was read from, the value
  found, the SPDX identifier and the MIT-compatibility verdict. Nine
  distributions publish a PEP 639 `License-Expression`; two publish none,
  and their MIT identifiers are recorded as readings of the legacy
  `License` field rather than flattened, because a published expression
  and a sentence somebody read are not the same grade of evidence. Every
  identifier is permissive and MIT-compatible (NFR-02). RPT-016 is
  deliberately unedited: it is what the closure is checked against.

  The guard that holds it, `test_every_development_tool_has_a_license_card`,
  reads the dev list live from `pyproject.toml` and requires each
  distribution to have a card SECTION of its own, a heading whose text
  normalises to the distribution's name. It is deliberately NOT the
  substring shape of the two coverage tests beside it, and the difference
  was MEASURED rather than argued: run over `dev`, a substring sweep is
  green today with zero cards written, because RPT-016's gap paragraph
  enumerates the uncarded names in order to say they have no card. A
  check satisfied by the sentence saying the work is undone reports the
  gap closed.

- **A stated weight budget for a mesh reader, and three candidates
  measured against it** (PFS-2025.20.01),
  `reports/RPT-034_mesh-reader-weight-budget_2026-08-19.md`. Three
  limits, each anchored to a repository fact that PREDATES the
  measurements: at most 5 MiB added, at most one new transitive runtime
  distribution, and an SPDX identifier read from installed metadata that
  is permissive and MIT-compatible. Measured in clean per-candidate
  environments: one candidate adds five distributions and 12.26 MiB and
  fails two limits, one adds a single distribution and 3.89 MiB and meets
  all three, and a NumPy-only in-house reader meets the numbers and is
  refused by the standing engineering policy instead. Coverage against
  the solver's eleven import file types is recorded per candidate and is
  deliberately not a limit. The card does not decide whether a reader
  becomes a required dependency: NFR-06's table governs that, and it is
  the reference.

- **`reports/RPT-035_mesh-reader-licence_2026-08-19.md`**, the NFR-02
  card a mesh reader would need to become a REQUIRED runtime dependency
  rather than an optional extra. It does not replace RPT-003, which is
  the adoption-time card for the `[geom]` extra; it measures the
  different surface a promotion exposes, the reader's transitive closure
  with no extras bracket. The delta a promotion adds is one distribution
  under one permissive licence. It also records that the reader publishes
  no PEP 639 `License-Expression`, so its identifier is a reading of the
  legacy field, which is worth naming where a dependency reaches every
  user with no opt-in.

- **`pyflightstream.qa.cost`, a wall-time cost view built from campaign
  manifests alone** (PFS-2018.02). `cost_view()` returns a `CostView` with
  sweep points down and solver builds across, so the same points measured
  on two builds are read side by side; `cost_rows()` is the long form, one
  row per recorded run, carrying `fs_build` and `fs_exe_sha256` as columns.

  A COLUMN IS THE PAIR, build string and executable sha256, so two
  executables reporting the same vendor build number stay two columns. A
  run recorded with no `wall_time_s` is reported as absent, `None`, never
  as zero and never as a floating-point NaN: `results.tables.run_table`
  maps the same missing field to NaN because its substrate is a numeric
  frame, and this reader deliberately does not, so a caller who sums a
  column meets a `TypeError` rather than a total that is silently short.
  `CostView.compare()` pairs only the points BOTH builds timed and names
  the rest as unpaired, so a total is never a sum over two different sets
  of work.

  `pyfs-qa cost <campaign-root>` prints that table from a campaign's
  `runs.json` with a legend mapping each column label back to its full
  build and executable hash; `--compare BASELINE,CANDIDATE` prints the
  per-point and overall ratio over the points both builds timed. It starts
  no solver and needs no licensed machine, which is now true of four of
  the seven `pyfs-qa` subcommands. The page a reader meets it on is
  `docs/solver-cost.md`, whose worked example is executed by the docs
  suite.

- **`pyflightstream._digest` states this package's hashing rule as data
  rather than as prose** (PFS-2012.10). `ALGORITHM` (sha256),
  `EXCLUDED_FROM_EVERY_DIGEST` (wall-clock timestamps, elapsed and wall
  time, absolute paths, the machine and environment, staging order) and
  `CANONICAL_FORMS`, which names the exact byte string every
  digest-computing module of the package feeds to the hash. A new tier-1
  guard walks the package for every `hashlib` constructor call and fails
  when a module hashes without declaring its canonical form, or when a
  second algorithm appears. The rule was previously written nowhere, which
  is why NFR-15 CARRIED a `pending` badge; a private module gains
  no public API, so this is an internal guarantee behind a public claim
  rather than a new public surface.

  THE OWNING SEAT RULED INSIDE THIS CYCLE and this bullet published the
  pre-ruling state until 2026-08-20. It said the NFR-15 sentence was a
  marked proposal awaiting a seat decision, and that NFR-15 therefore carried a
  `pending` badge. The owning seat rewrote the statement on 2026-08-19 and the
  requirement is `implemented`, citing `_digest` and
  `tests/test_digest.py`, on the ground that the rule is DATA in that
  module rather than prose about it. A reader following this bullet to
  NFR-15 was being sent for the opposite of what they would find.

- **The two independent reviews are transcribed into a committed report**
  (OPS-2005.11), `reports/RPT-028_independent-review-findings_2026-08-18.md`,
  one heading per finding carrying its statement, the severity the review
  published for it and the files that cite it. 41 identifiers of the
  `PYFS-nnn` and `REV010-nnn` series were cited in `src/` and `tests/` and
  exactly ONE, `PYFS-025`, was named anywhere under `reports/`, in a
  sentence rather than a heading. Every other citation resolved only into
  review documents held outside this repository, and one read-only survey
  had already concluded from that dead end that the findings could not be
  worked. The report heads all 45 findings of both reviews rather than
  only the cited 41, so a citation added later resolves without amending
  it.

- **`tests/test_review_citations.py`, a tier-1 walk that holds those
  citations to the report.** Every `PYFS-nnn` and `REV010-nnn` identifier
  appearing in a `.py` file under `src/` or `tests/` must be named in a
  HEADING of a report under `reports/`, so a deleted report or a renamed
  identifier turns the suite red instead of leaving the citation pointing
  outside the repository. A mention is not a heading and a line inside a
  code fence is not a heading, on the same reasoning as the probe-citation
  walk that requires a cited report to name the command it backs. The walk
  REFUSES when it collects zero identifiers, which is how this class of
  walk otherwise dies silently: an empty collection satisfies every
  per-identifier assertion ever written.

- **A tier-1 house-style guard refuses a NEW citation of a private ledger
  identifier** in any file the style walk reaches (OPS-2010.15). This
  remote is public and the records those identifiers name are not: the
  plan ledger and the design documents are local-only, and the incident
  ledger and the coordination hub are other repositories, so a committed
  sentence citing one sends its reader to a document that does not exist
  for them. The guard counts occurrences per unit against a committed
  inventory (`tests/data/private_id_inventory.py`) and fails four ways: a
  count above its row, a unit with occurrences and no row, a count BELOW
  its row (lower the row in the same commit), and a row over a unit now
  clean or no longer walked. Report identifiers, SRS requirement
  identifiers and plan node identifiers stay legal, because they resolve.
  No identifier is checked against a ledger: the ledgers live outside this
  repository and CI cannot reach them, so what is checked is the shape.

- **`reports/RPT-029_mypy-exemption-recount_2026-08-18.md`, the
  type-checker exemption re-count at 0.8.0.dev0** (OPS-2006.11.01). It
  carries the per-module and per-error-code tables with every
  `ignore_errors` override off, the reproduction command, the dependency
  versions the count depends on, the delta against 2026-08-03, and the
  finding that 275 errors sit on only 99 distinct source lines with six
  lines producing 73 of them, so the grind should be sized by LINES rather
  than by errors. The report was amended before it was ever committed,
  by its own reproduction rule: mypy walks the filesystem, the tree moved
  under the first measurement, and the module total is the
  re-measurement.

- **Four tier-1 tests in `tests/test_traceability.py` hold the records of
  that re-count to each other and to the package.** The module total every
  record states is compared against the tracked `.py` files under
  `src/pyflightstream` on every run, the unclean count is compared against
  the number of `ignore_errors` overrides that actually exist, and a
  record stating the measurement twice with different numbers is reported
  as stating none. The 53 in the old records went stale in silence because
  no guard compared any written record against the tree.

- **FlightStream 26.123 is registered, measured and `operational`, and it
  is the first build here that INHERITS NOTHING.** Vendor hotfix build 3 of the 26.12 release,
  delivered 2026-08-16 and registered 2026-08-17. The two hotfixes
  before it descend from 26.120, on evidence rather than on the last
  digit, and the default is right for them. The instruction for
  this one is the opposite, and the reason is a number rather than a
  preference: with descent on, a build issued the day before would have
  answered for the 363 commands 26.120 can EMIT without one page of its
  own manual being read or one line being run, and the compatibility
  matrix would have printed a full column on the strength of it.

  **What that costs a caller, stated plainly because it is a refusal
  surface.** Until a row exists for a command on 26.123, `Script.emit`
  REFUSES it, exactly as it refuses a command a build never had. All 414
  entries start in that state and the enumeration is committed as
  `tests/goldens/absent_on_26123.txt`, with its own counts in its header,
  so the gap is a number a reader can check rather than an impression.
  Every row written from here shrinks that file, and a tier 1 test
  compares it against what the emitter actually does. Regenerate it with
  `python scripts/gen_absent_commands.py 26.123`.

  Its support level is DERIVED and not declared, and it moved twice in
  one day for that reason: `registered` while no command answered for it,
  then `documented` once the pass below wrote its rows. Its `build` and
  `prints` come from `reports/compat/CMP-26123_2026-08-17_identity.yaml`,
  and the order those were established in is the registry's own
  chicken-and-egg: the two fields are admitted only from a committed
  report's `solver_identity`, and the run that writes one refuses an
  unregistered version, so the row was written with both unset and they
  followed. That report is also the first in this corpus to record the
  executable by a version-named name, `FlightStream_26123.exe`, rather
  than the installer's name which four builds share.
- `scripts/gen_absent_commands.py`, which writes the same enumeration for
  any registered build. General rather than named for this one, because
  the question arrives again with the next build the owning seat decides
  should inherit nothing.
- **`pyfs-manual register`, which carries a build's documentation forward
  from a reading rather than a copy.** It compares a new edition against
  the one before it command by command and writes a `documented` version
  row for every command both editions describe IDENTICALLY: same
  signature placeholders, same sample block, same parameter table. Dry
  run by default, like `draft`.

  **It compares what the edition SAYS, never which page it says it on**,
  and that is the difference that matters. A local reflow moves a run of
  commands back by one page without changing a word, so a rule keyed on
  the page number drops every one of them; THREE of 26.123's commands
  are in exactly that position, and all three carry it in their rows. Commands the new edition describes
  DIFFERENTLY are reported and never written, because those are a reading
  somebody owes.

  On 26.123 it wrote **369 of the 371 commands SRC-751 documents**. The
  two it left are each their own work: `SET_SCENE_CONTOUR`, which the
  edition describes differently, and `SET_OUTLET_TRAILING_EDGES`, which it
  documents and this database does not carry. It also NAMES the two
  commands the new edition stops documenting, `TRAILING_EDGES_IMPORT` and
  `SET_OUTFLOW_TRAILING_EDGES`, separately from the commands neither
  edition documents: each of those two owes a reading before anything is
  written for it. 26.123 moves from `registered` to `documented` and
  `tests/goldens/absent_on_26123.txt` shrinks from 414 entries to the
  count its own header states. The digit is not repeated here: it was
  written as 45 and the golden says 43, which a release audit found on
  2026-08-20 in the third of five places that stated it.
- **26.123 is MEASURED, and reaches `operational` on the same day it was
  registered.** A Tier 2 probe run promotes 85 statuses, 84 verified and
  one broken (`reports/compat/CMP-26123_2026-08-17_full-sim.yaml`). Read
  it against 26.122's 83 and 1: one more verified, the extra being
  `SET_INVISCID_LOADS` which was unprobed there, and nothing 26.122
  verified is unverified here, so the newer build refuses nothing the
  older one accepted. The single broken command is
  `NEW_OFF_BODY_STREAMLINE`, which aborts script processing on 26.120,
  26.121, 26.122 and now this build, each on its own evidence rather than
  by inheritance.

  284 rows stay unprobed and the two reasons are the standing debts
  rather than this build's: 261 have no probe specification at all, and
  23 ran without abort or logged error while no instrument can observe
  their effect.
- **A change the vendor described directly is MEASURED, and no
  edition's text carries it**
  (`reports/RPT-027_boundary-layer-across-a-proximity-gap_2026-08-17.md`).
  Read the wording: what was measured is the integrated viscous DRAG in
  the configuration the vendor's caveat describes. That the mechanism is
  the boundary-layer mapping he named is his explanation for why the drag
  should move, and the report lists it as NOT established, because the
  instrument that would show the mechanism itself opens a modal window.
  Two copies of one wing at two gap widths expressed as a ratio of the
  measured local face length, with `SOLVER_PROXIMAL_BOUNDARIES` on and
  off, steady and unsteady, on both builds: sixteen cases. The question
  came from the vendor describing the change to the owning seat directly, so
  this is a measurement of something volunteered rather than a gap found
  by audit.

  At two face lengths of separation the proximity setting changes the
  viscous drag by NOTHING, to every printed digit, on both builds and in
  both modes, which is the vendor's own caveat behaving as stated. At a
  quarter of a face length it changes it by 75 to 84 percent, depending
  on the build and the mode. And the two builds differ far more where
  that mapping engages than anywhere else measured: 26.123's total `CDo`
  is 32 percent lower at the narrow gap, steady and unsteady agreeing to
  two significant figures, against a few tenths of a percent at the wide
  gap.

  Read three limits with it. A lower viscous drag is a DIFFERENT answer,
  not a better one, and nothing here judges which is right. Two gap
  ratios were run, so the regime's boundary is bounded and not located.
  And the wide-gap control is not the smallest movement between these
  builds: the same day's drift run moved three viscous drag coefficients
  by 1.8, 2.2 and 9.0 percent on cases with no gap in them at all.
- **`EXPORT_BL_VELOCITY_PROFILE` cannot be used in an unattended run**,
  measured rather than inferred. It opens a modal window with a plot and
  a Done button, and script processing stops until somebody dismisses it,
  under `-hidden` with both streams redirected. Its entry records the
  behaviour and its status is unchanged: that is a fact about the
  interface rather than a refusal by the solver, and a status comes from
  a committed probe report.
- `qa.geometry.mean_edge_length`, and keyword-only `translation_m` and
  `name` arguments on `wing_triangles` and `generate_wing_stl`. Two components at a
  controlled gap need the offset in the MESH: translating one with a
  solver command would put the transform under test as well.
- **`pyfs-qa probe`, `physics` and `drift` all refuse an existing report
  BEFORE they start the solver.** The refusal itself is unchanged and
  correct, a report is evidence and is never overwritten; it was asked
  after the run. A full campaign on 26.123 executed 111 command probes
  over five minutes of licensed solver and then the write refused on a
  stem that already existed, so a licence checkout was spent and
  discarded on a collision knowable from the command line. The repair
  first reached `probe` alone and the other two kept the defect, where
  it was worse: the whole Tier 3 matrix could run and then die on an
  uncaught `FileExistsError`, which probe at least caught and printed.
  Three copies of one rule is why a repair could reach one of them, so
  the rule now lives in `pyflightstream.qa.reports` and all three ask it
  first; the identical command refuses in under a second saying
  `nothing run`. The date is resolved once per run and handed to the
  writer, so a matrix started before midnight cannot check one stem and
  write another.
- `ProbeOutcome.REMOVED`, promotable like any other outcome. A build
  that does not carry a command used to record `broken`, which is a
  different claim. Both refuse at build time, so the difference is
  WHICH refusal: `broken` keeps the command in the version view and
  raises `BrokenCommandError`, whose message says the solver accepts
  the line and would return numbers nothing marks as wrong, and which
  `allow_broken` waives. Both halves are false for a build that does
  not carry the command, and a waiver would emit a line the solver
  rejects outright. The signal is the solver's own refusal naming that command,
  measured rather than paraphrased (RPT-026), read from the crash log
  the harness had never opened.
- A supersession check in `apply_compat`. Re-running the sanctioned
  write path on an older report used to revert a status a later run had
  already moved, with a citation that agreed with itself and every
  guard green (`PLN-20260804-1500`). A tier 1 guard asserts the same
  invariant over the committed database.

### Changed

- **A citation re-check records how each row it SAW ended, not only how
  many it saw and how many it read** (OPS-2003.10.02).
  `utils.manual.citation_reach` returns the four outcomes named by the
  new `CITATION_REACH_OUTCOMES` (`no_note`, `no_page`, `removed`,
  `checked`) plus `range_cited`, and `pyfs-manual citations` prints the
  four per edition.

  The four PARTITION the rows seen, which is the point: the report used
  to print the whole difference between seen and checked as one
  unexplained gap, and attributing all of it to one reason is the mistake
  the counter's own comment warns about. `range_cited` is a stated subset
  of `checked` and never an addend, and a row whose edition the manifest
  does not list is counted in none of them, because the run has no
  reading to check it against; those builds keep their own line.
  Separating the outcomes corrected a published number immediately: of
  26.120's 381 rows, 359 carry no note at all and 4 carry a note with no
  page of its own, where one sentence had covered both.

- **`pyflightstream.post`'s module docstring stops advertising what the
  layer does not have** (PFS-2015.01, NFR-11). It had claimed the layer
  "performs blade-passage averaging for unsteady runs" while importing
  that name raised `ImportError`, and announced a `ResultArray` facade as
  planned. The averaging now exists; the facade does not, and the
  docstring says so in its own section rather than describing it as
  forthcoming.

- **One type-checker exemption is REMOVED, the first this project has
  been able to remove on evidence.** `pyflightstream.results.tables` was
  exempt and is now clean: deleting `_as_workspace` took the module's
  last type error with it, measured with every override off. The
  `[tool.mypy]` header has promised since 2026-08-03 that an exemption is
  removed as its module is typed and never added, and this is that
  direction happening rather than being restated. The re-count moves with
  it, and the tree had carried 275 errors in 21 of 64 modules two days
  before; the current reading is the one `reports/RPT-029` and the
  [Unreleased] section state, which a tier-1 guard holds together.

  It was re-measured a THIRD time on 2026-08-20, when this release's last
  two modules landed and the module-total guard went red exactly as
  designed. `scripts/mypy_recount.py` emits every figure the report
  states from ONE run now, so the failure that started this, a sentence
  retyped while the tool output beside it was not, cannot be repeated by
  hand.

- **The FSI persisted state and its convergence log name the digest
  `config_sha256` rather than `config_hash`** (OPS-2009.01.14). A
  `state.json` written by an earlier release STILL LOADS: `FsiState`
  carries `validation_alias=AliasChoices("config_sha256", "config_hash")`
  with `populate_by_name=True`, so the legacy key is accepted on the way
  in and only the new name is written on the way out, and a resumed run
  migrates its own run folder on its first write.

  Without that alias the rename would have been silently DESTRUCTIVE
  rather than merely breaking, because the model forbids extra keys: the
  old key would not have been ignored, it would have been refused, and the
  whole state file with it.

  One consequence worth planning for: a run resumed into an EXISTING
  `fsi_convergence_log.csv` keeps that file's old header word, because the
  header is written only when the file is absent. The column order, the
  column count and the meaning of every column do not move. The three
  committed `reports/fsi/*_convergence.csv` keep the old header as
  historical evidence.

- **`scripts/gen_requirements_index.py` refuses a malformed requirement
  page instead of publishing it**, exits non-zero and writes nothing
  (OPS-2005.09). Four shapes: a requirement box with no `srs-` badge,
  which used to default to `implemented` and so published a requirement
  nobody has built to an external dashboard as done and mandatory; a badge
  token outside implemented/pending/deferred/deprecated; a repeated
  identifier; and a `!!! requirement "` header the box pattern cannot
  read, which produced no entry at all while its body was absorbed into
  the previous requirement. The first three name the page and the
  identifier; the fourth names the page and the line number. The emitted
  payload is unchanged: the same 96 requirements, byte for byte.

- **The push-gate suite says WHICH refusal fired** (OPS-2006.08). A deny is
  not one outcome: the gate brackets a sub-kind because the remedies
  differ, `[review]` meaning run the reviewers, `[ledger]` meaning repair
  infrastructure, `[config]` meaning export one variable, `[gate]` meaning
  the gate itself crashed and fell closed.

  Measured rather than argued: a copy of the gate was sabotaged with one
  statement, `raise RuntimeError` at the top of `main`'s try block, so
  every push denied through the fail-closed arm with no check in the body
  reached, and 21 of the file's 69 cases STILL PASSED. Fifteen of those 21
  exist to assert a REFUSAL. One passed on a substring collision rather
  than on a bracketless assertion: the case pinning that a deletion deny
  does not prescribe pushing the ref looks for "author decision", and the
  fail-closed message ends "an author decision, not a workaround".

  Every refusal case now names its sub-kind, and the check reads the
  bracket that OPENS the message and compares it for equality rather than
  searching the reason for a substring. `[gate]` is refused everywhere
  except in the one case that is about the fail-closed arm, so the rule
  holds for cases that name no expectation at all. Against the same
  sabotage the file now fails 65 of 74, and the survivors are the cases
  that read text rather than drive the gate. The gate's message prefix and
  the incident-ledger environment variable are READ out of the gate body
  instead of mirrored: a rename in the kit used to leave the suite
  stripping a variable nothing reads, which silently pointed every hook
  subprocess at the reference real ledger with nothing going red. A new
  partition guard fails when a sub-kind arrives in a re-vendored body that
  no case pins and no declaration excuses. Test-only: no public name, CLI,
  extra or behavior moves.

- **The `[tool.mypy]` header comment no longer states the 2026-08-03
  measurement as though it were current** (OPS-2006.11.01). It records the
  first measurement as history and the re-count beside it, and it
  separates the two kinds of number: the error total is a DATED
  measurement that moves with the code and with numpy's, xarray's and
  pandas' own stubs, while the module total is re-counted from the tracked
  tree on every test run. No override was added and none was removed,
  which is the measurement rather than restraint: the set of modules that
  report an error with the overrides off is exactly the set the overrides
  name.

- **The `pyflightstream.versions` module docstring no longer calls itself
  "the lowest layer"** (OPS-2005.12), which stopped being true once the
  base-exception module was recorded below it. It now reads "the bottom of
  the pipeline proper, above only `_errors`". This is a user-visible
  documentation change rather than an internal comment: that sentence is
  published verbatim on the generated architecture page.

- **Four writers stopped replacing a file without saying so**
  (PFS-2011.02, FR-33c, FR-33b, FR-29). PYFS-005 records the class: one
  point of a campaign overwrote another's output while the run record
  listed both complete, which cost licensed solver time and could have
  published a report from one point counted twice. The guard written
  afterwards covered the surface where it was found; three others took a
  caller-chosen path with no case and no manifest to key on.

  EACH SURFACE REFUSES DIFFERENTLY, because the signal is different in
  each, and that is the whole content of the change rather than an
  inconsistency. `post.writers.write_vtk_points` and
  `write_tecplot_points` ended in a plain file write, so the signal is
  that the destination exists; both gain `overwrite=False` and raise the
  new `OutputExistsError`. `script.helpers.export_probes` asks the SOLVER
  to write, so nothing exists yet at script-build time and the signal is
  that this script already asked for that path; the register lives on the
  `Script` because the collision is between two CALLS and only the script
  sees both, and the refusal names BOTH call sites, since one naming only
  the second sends the reader to the line they do not need to change.
  `fsi.driver.coupling_step` APPENDS by design, so neither the log's
  presence nor its absence is the signal: it is the PAIR, a convergence
  log with no `state.json` beside it, which is a previous run's history
  in a folder being reused.

  `OutputExistsError` is new in `pyflightstream.exceptions` and keeps
  `FileExistsError` as its second base, so an existing handler around a
  write catches what it always did. The evidence writers under `qa` keep
  raising the builtin for the same situation, deliberately: that predates
  the catalogue's reach, and a new raise site takes the catalogued type.

  `script.helpers.export_results` is a fourth writer of the same shape
  and is deliberately NOT covered: the item names three surfaces, and
  widening a guard beyond them would put a decision nobody made into the
  tree.

- **`collect_outputs` refuses a source that escapes the run** (PFS-2011.01
  and PFS-2011.03, FR-28 and FR-29, one piece of work). Collection MOVES,
  and the method moved any path it was handed: naming
  `sims/sim_OTHER/raw/loads.txt` as an output took another run's
  collected evidence into this simulation's `raw/`, and both manifests
  then named a file only one of them had.

  The rule is on RESOLVED paths and never on the declared string, which
  is why it is not the check in `naming.py`: that one refuses any
  ABSOLUTE path, and every production caller here passes absolute paths,
  so reusing it would have refused the normal case. A produced path that
  resolves INSIDE the campaign root must resolve inside this
  simulation's own folder and not under one of its four managed
  subdirectories; the refusal names the ROLE of the folder it landed in,
  and names the simulation a file belongs to when it belongs to one.

  Two acceptances are deliberate and are stated in the docstring rather
  than left to be discovered. A source OUTSIDE the campaign root still
  collects: that is the ordinary case, since the solver's working
  directory is not managed by this class. And an unmanaged subfolder of
  the simulation, `sim/out/`, still collects, because nothing here owns
  it and moving a file out of it destroys no record. A blunt "under the
  simulation" rule would have refused that one.

  The check runs before the collision pre-scan and therefore before any
  move, so a refusal leaves every source exactly where it was. The
  summary line now says collection MOVES, which a reader has had to infer
  from the collision message until now.

- **One owner for the checksum that decides whether two runs used the
  same inputs** (PFS-2012.02, NFR-07). The sha256 behind that claim was
  written in FOUR places: a chunked read in `workspace`, a second in
  `run` differing only in its failure policy, and two inline text hashes,
  one in `run` and one in `qa.probes`. Nothing stopped two of them
  diverging and nothing would have noticed if they had; the manifest
  would simply have said two identical runs were different, or two
  different runs the same. And the run layer reached ACROSS A LAYER
  BOUNDARY for `workspace._sha256`, an underscore-private name, rather
  than write a fifth.

  `pyflightstream._digest` is now the one home, below every layer exactly
  as `_errors` is and for the same reason: it imports nothing from the
  package, so every layer may use it and none imports another to get it.
  It exports `file_sha256`, which RAISES, `optional_file_sha256`, which
  answers `None`, and `text_sha256`. The two file functions differ only
  in their failure policy and the policy is carried by the NAME, because
  a caller who picks the wrong one gets either a run that dies on a
  provenance field or a manifest that silently records nothing.

  The VALUE did not move: one fixture hashes identically through the old
  chunked read and the new owner, which matters because every committed
  manifest records digests written by the old one. No public signature
  moved either, and the module is private, so nothing is added to the
  surface. A FOURTH caller the plan had not named, in the resume
  comparison, was found by the linter when the upward import went and
  takes the raising form.

- A compat report's `summary` now carries one key per outcome, derived
  from the enum, so `removed` appears beside the other three. Readers
  keying on the old three names are unaffected.
- An abort caused by a command OTHER than the probed one now records
  `unprobed` naming the offender, where it previously recorded the
  probed command `broken`.

- `AIR_ALTITUDE` is emittable on 26.122. It had inherited `broken` from
  26.120, where the solver reads its `METERS` argument as feet, and the
  first probe on this build reads the 5000 m standard-atmosphere
  density correctly, so the builder no longer refuses it there. This is
  the one caller-visible change to what a 26.122 script may emit
  (`reports/compat/CMP-26122_2026-08-11_full.yaml`, read with
  `CMP-26122_2026-08-11_full_erratum_2026-08-11.md` beside it: the
  report's own note for this command carries a sentence that is false
  on this build, and the report is evidence and is never edited).
- `PHY-05` and `PHY-06` are registered for 26.121 and 26.122, not
  26.120 alone. Their pin cited a backfill owed for EARLIER builds,
  which never applied to later ones.

- **Process only, no package change: the CI-green tag rule moved from a
  repository-owned hook into the shared push gate.** Ten kit bodies were
  re-vendored (kit 0.2.18/0.2.19/0.2.15/0.2.11/0.2.10/0.2.5, per file),
  and `.claude/hooks/ci_release_gate.py`, its wiring in
  `.claude/settings.json`, `tests/test_ci_release_gate.py` and that
  hook's mutation battery were deleted in the SAME commit, never before
  it and never after. Two new vendored files sit beside the gate,
  `ci_state.py` and `ci_state_mutations.py`, because the 0.2.18 gate runs
  the first as a subprocess and treats its absence as a refusal.
  `scripts/prove_extras_and_ci_guards.py` is renamed
  `scripts/prove_extras_isolation.py`, having lost the half it was named
  for. Contributor-visible: the mutation battery's path and its label
  prefixes changed (`BM*` are gone); the gate's hook timeout in
  `.claude/settings.json` is 90 seconds rather than 30, because the
  vendored body budgets 50 seconds of CI work and a hook the harness
  kills emits no decision at all.
- **Every skill now declares `side-effects:`, and none carries
  `disable-model-invocation`.** The owning seat retired the human-only flag at
  kit 0.2.19 on 2026-08-11, across all skills with no exception,
  including `release` and the three that spend a licensed solver seat.
  Six skills that had declared nothing (`add-command`, `audit`,
  `derive-requirements`, `handoff`, `plan`, `role-review`) now do; the
  guard's own measurement went from `4 declaring, 6 undeclared` to zero
  undeclared, over a population it derives at run time. The end-state
  count is deliberately not quoted here: it was ten when this was
  written and eleven a few hours later, when the vendored
  `version-control` skill arrived.
- **`PYFS_INCIDENT_LEDGER` is retired**, and a fresh clone now sets four
  machine-configuration variables rather than five. The 0.2.11
  incident-analyst charter reads `COORD_INCIDENT_LEDGER` like everything
  else, so the old name had no consumer left. CLAUDE.md keeps a
  retirement notice so a machine that already exports it learns why to
  stop.
- CLAUDE.md gains an `## Execution rules` section (pointers, not
  reasoning) and a pointer to `BRF-082`, whose wording lives in
  `.claude/skills/role-review/SKILL.md`: the adversarial pass runs BEFORE
  a completion claim rather than as a review round after it.
- **Process only, no package behaviour change: the shared process kit is
  fully vendored.** Twenty-four further artifacts arrived on 2026-08-11,
  taking the drift manifest from 11 rows to 35, each pinned to its own
  `body-sha256` at mixed kit versions from 0.1.0 to 0.2.22. Two kit
  artifacts are absent BY DECISION
  and not by omission: the `release_caller.yml` and `release_gate.yml`
  workflow templates, declined because this repository's `release.yml` is
  a single workflow that has published v0.4.0 through v0.7.0.
  Contributor-visible: a `version-control` skill is now available, and
  `CLAUDE.md` gains a `## The vendored process kit` section recording
  which checkers are wired and the reason beside every one that is not.
- **A second PreToolUse hook now refuses two shell shapes.** The kit's
  `execution_guard.py` (0.2.22) denies a status-bearing command (`pytest`,
  `mypy`, `ruff`, `git push`, or a `check_*.py` / `*_mutations.py`
  script) piped into a line filter (`head`, `tail`, `wc`,
  `Select-Object`, `Measure-Object`, `select`, `measure`), and a heredoc
  whose body carries a backslash or a control byte. Both denies name a
  category (`[piped-status]`, `[heredoc-content]`) and a remedy, and
  neither can block a push. Contributor-visible because it changes what
  a shell command may look like; the arms, the remedies and the one
  known false positive are in `CLAUDE.md` under `## The second PreToolUse
  hook: the execution guard`.
- Tier 1 now runs a tree-wide forbidden-identifier scan and four vendored
  mutation companions, and takes roughly ten minutes rather than six. The
  single largest term is the push gate's own companion at 244 seconds.
- Every `subprocess.run` under `src/` and `scripts/` now passes an
  explicit `env=`. The value is `os.environ.copy()` in each case, which
  is exactly what an omitted `env=` gave, so no child's environment
  changed; what changed is that the inheritance is a decision at the call
  site. Found by the newly vendored `check_spawn_env.py`, which is wired
  in tier 1 over those two trees; the 24 unguarded spawns under `tests/`
  are pinned as a ratchet rather than silently excluded.

### Fixed

- **The FR-39 TypeError tranche is EMPTY, not merely smaller**
  (OPS-2009.01.08). Three raise sites on the public path raised a bare
  `TypeError`, so `except PyflightstreamError` caught none of them: two
  in `results.to_table` and one in the entity registry. All three now
  raise a catalogued class keeping `TypeError` as its second base, and
  both ratchet rows came out in the same edit that re-based their raises.
  It is the first tranche this ratchet has emptied rather than shrunk,
  and the ratchet's own header now counts 13 entries over 16 raises
  rather than 15 over 19.

  The decision that had deferred it stopped being open on 2026-08-17,
  when the first non-ValueError base entered the table and made its shape
  a precedent rather than new ground.

- **The examples run promotes only THIS package's warnings**
  (OPS-2006.02.02), and the two halves landed in one change because
  either alone is worse than neither. Eleven `warnings.warn` sites are
  retagged onto the package's own categories, the ratchet that recorded
  them is empty, and the six command homes are narrowed from a bare
  `-W error` to the package category. Narrowing first would have stopped
  catching ours; retagging first would have left a dependency's
  deprecation still able to redden the build.

  `VersionMismatchWarning` settled four of the eleven sites at once by
  being re-parented, keeping `UserWarning` in its MRO. A strict expected
  failure stood in the suite saying it would turn into a failure on the
  day the narrowing landed; it did, and it is gone.

  WORTH KNOWING BEFORE YOU COPY THE FILTER: `python -W
  error::pyflightstream...` does not work and fails SILENTLY. The
  interpreter parses its own `-W` before this package is importable,
  prints `Invalid -W option ignored` and promotes nothing at all.
  `pytest -W` parses later and does work, which is why every promotion
  home here is a pytest command line and why the category lives in a
  module that imports nothing.

- **A campaign with a failing point left no sweep table at all**
  (PFS-2014.03). The command line caught the after-the-loop failure with
  the refusals that fire BEFORE the campaign ran and returned without
  writing, so every point that did run lost its evidence with the exit
  status. The two are separate arms now: a run that executed and had
  failures still writes its table and still reports the failure. It also
  passes `require_loads=False`, the keyword written for exactly the
  condition it was printing "sweep table not written" over.

- **The reader weighed fewer axes than the assessor** (OPS-2009.01.13).
  The table reader compared only the point's own axes, so a requested
  free-stream velocity the assessor checks was invisible to it. The
  requested velocity now joins the axes, with `setdefault` and not
  assignment, because the point's own value wins over the case default
  and a plain assignment would have reversed that precedence silently.

- **An example run's warnings are read off stderr rather than promoted.**
  The run checked the exit status only, so an example that started
  warning kept exiting 0 and the reader met the warning before anyone
  here did.

- **The solver-setup provenance snapshot read the PACKAGED command
  database rather than the one its script was built with** (PFS-2012.05),
  so a run manifest could carry an availability, a default or an evidence
  sentence from a database no line of the script was ever checked
  against. `build_setup` now takes the registry and the settings helper
  passes the script's own, and `Script.registry` exposes it so a caller
  can ask the same question the script answered.

- **A fixture library staged six files no id could ever reach.** The
  builder behind the workspace walkthrough wrote both the bare
  three-digit codes and the new letter-prefixed ones, so the bare files
  sat on disk unreachable under the id rule that landed with them. Found
  by the page-currency guard over that builder rather than by any test of
  the library, and only because that guard asserts its collection is
  non-empty BEFORE it compares: its first version matched a literal path
  spelling out of the source text, and the rewrite to a loop left it
  matching nothing while every artefact was still staged. It now RUNS the
  builder and reads what lands on disk, so it survives any rewriting of
  how the paths are spelled, which is the only thing that ever broke it.

- **A refusal that used to name what is available named nothing.** The
  structured `available` attribute is populated on a not-found refusal
  and empty on a refusal about the id's own shape, which is about what
  the caller wrote rather than about what the library holds. Both
  branches are now pinned and the class docstring states the difference,
  because an empty tuple would otherwise be read as an empty library.

- **Every byte of a vendored process-kit file is now pinned, its
  provenance header included** (OPS-2013.30). Only the BODY was hashed
  before, and the header was reached by three assertions that each read
  one field, so an arbitrary extra line above the END KIT PROVENANCE
  marker, a `contact:` field carrying a personal address for instance,
  passed the body hash, all four field assertions and the header parser.
  That is in exactly the directory where a vendored kit body once
  published a personal name, address and user-profile path on this public
  remote.

  `tests/test_kit_drift.py` now carries a header sha256 pin per manifest
  row, asserts that the two tables carry the same keys in both directions,
  asserts that the header and body regions are exact COMPLEMENTS so the
  coverage claim is a measurement rather than a claim, and proves the
  refusal with a mutation: the same vendored file with one injected
  contact line fails the header pin while its body sha256 still matches.
  No test enumerates permitted header keys or line shapes, because the
  headers are not uniform and a shape rule would be a whitelist of prose.

- **The last vendored provenance note stops pointing at a kit directory
  retired on 2026-07-27** (OPS-2013.04). `.claude/tools/check_incidents.py`
  now names the live kit path, which is the prescribed per-copy restamp of
  an unhashed header line and leaves the pinned body untouched, and
  `tests/test_kit_drift.py` records that target. Two new guards keep it:
  one forbids the retired path in any provenance note whatever the
  manifest says, one forbids pinning it in the manifest. Both are needed
  because the kit README still prescribes the OLD wording, so a re-vendor
  performed to its letter reproduces the stale pointer while updating the
  manifest row in the same edit.

- **The user guide guard covers all six objects the guide hands the
  reader, not three** (OPS-2005.05). `campaign` joins the objects whose
  taught attributes are held against the real class, and any pydantic
  model's fields count as known, which is what makes `Campaign.fs_exe`
  visible at all since it is absent from `dir(Campaign)`. A second half
  checks that every class name the guide names in a code span resolves in
  one of the modules the guide's own import lines name, plus
  `pyflightstream.exceptions` and `pyflightstream.qa.geometry`:
  `CampaignWorkspace` and `RunRecord` are taught that way and carry no
  dotted usage at all, so renaming `RunRecord` used to leave the whole
  module green.

- **The premise of the exemption re-count item is recorded as false rather
  than worked around** (OPS-2006.11.01). `pyproject.toml` carries 21
  `ignore_errors` blocks and the test module's inventory carries 21 names,
  `pyflightstream.workspace.inputs` and `pyflightstream.workspace.naming`
  among them in BOTH, so nothing was excused without being recorded.
  RPT-029 cites the lines and a test asserts it.

- A probe detail carrying a backslash reached the rewritten chapter
  unescaped, because the `note` key was interpolated between two
  literal quotes while every other key went through the module's
  renderer. A Windows path in a solver message therefore either aborted
  a whole promotion or, where the backslashes happened to precede valid
  YAML escapes, wrote a silently corrupted note and reported success.
  Shipped since v0.4.0; no committed row carries the corruption
  (`INC-20260811-1511-both`). There is now one emitter and its escaper
  has exactly one caller, both asserted.
- `apply_compat` is all-or-nothing across chapters. A refusal raised
  while rewriting chapter n used to leave chapters 1..n-1 promoted on
  disk, under a message naming one command in one file, while the
  docstring said nothing was written.
- Three reachable inputs escaped both the documented `QaEvidenceError`
  and the CLI's trap as Python stacks: a mistyped report path, an
  unparsable report, and an unparsable file anywhere in
  `reports/compat/`. A rewritten entry that fails the command schema
  now refuses in the same type rather than surfacing pydantic's.
- The probe specification for `SET_MOTION_START_TIME` created a rotary
  motion, which that command refuses by design, so the abort it was
  recorded for was the probe's and not the solver's.

  NOT RESOLVED BY THAT FIX, and stated here because the guide says so
  and this file said the opposite: the command is still recorded
  `broken` on 26.101, 26.120 and 26.121, and 26.122 inherits 26.120, so
  the emitter refuses it on four builds TODAY. The corrected
  specification is measured to run on all four
  (`reports/compat/CMP-26101_2026-08-11_starttime.yaml` and the same
  stem for 26120 and 26121, plus the 26.122 full report), and an
  `unprobed` result cannot demote a `broken` one through the sanctioned
  write path. Lifting the refusal needs a demotion path that does not
  exist yet (`PLN-20260811-1300`).

- **A compat report carried `date: null` in its body while its own file
  name carried the date**, and 85 database rows cite it
  (`INC-20260817-2210-pyflightstream`). The cause was a transient state
  of the same session: the date defaulting moved into the path helper
  while the refusal was being hoisted ahead of the solver, and the probe
  run landed in the window before it was restored beside the writer.
  Deleting exactly one line from the current writer reproduces both
  committed files byte for byte, which also rules out a hand edit. Three
  guards now hold it: the writer is called with NO date and the stem, the
  body and the rendered header are required to agree; the path helper is
  required to default the same way, because the mirror-image mutation
  corrupts the pre-flight rather than the file; and every committed compat
  report is walked and its body date required to equal the date in its
  stem. The report itself stays as it is, on the design decision of
  2026-08-18, with an erratum beside it and a single named exemption in
  the walk; `reports/compat/README.md` gained the report-level erratum
  contract that shape needs.

- **The refusal that protects a licensed seat was decorative for two of
  the three evidence writers.** `physics` and `drift` predicted their
  report name from a series prefix and a build key the CLI pasted
  together itself, while each writer pasted the same thing together a few
  hundred lines away; the two agreed by coincidence and nothing tied
  them. Measured by sabotage: changing `write_physics_report`'s own
  prefix from `PHY` to `PHZ` left forty-five tests green while the
  pre-flight silently inspected a name nothing would ever write, which is
  the incident the pre-flight exists to prevent, one field over. The
  build key is derived in one place now, each series has a helper its
  writer and the CLI both call, and each writer's output path is asserted
  against that helper rather than against a literal.

- **The date was resolved twice per run**, once for the pre-flight and
  once inside the writer, so a Tier 3 matrix started at 23:59 cleared the
  collision check against one day and wrote under the next. The failure
  is a MISSED refusal, so its cost is the licensed seat. Each command
  resolves it once and hands it to its writer.

- **A library refusal told a Python caller to pass `--smi-root`**, a flag
  that exists only on a command line the library knows nothing about. The
  same class was corrected at two sites on 2026-08-17 and this one, one
  screen below a corrected sibling, was missed. The rule is mechanical
  now and carries no exemption list: a refusal raised outside a CLI that
  names `--some-flag` must also name `some_flag`.

- **Two mutation batteries and a reproducibility script reported success
  they had not earned.** `prove_alias_tally_guard.py` still read a kill
  off any non-zero exit, so pytest's collection error, usage error and
  no-tests-selected all scored as the guard denying; since its selector
  is a long node id, renaming the guard would have printed "6 of 6
  mutants killed" and exited 0 while judging nothing. It takes the shared
  three-valued verdict now and an inconclusive stops the run.
  `restate_26123_notes.py`'s reach floor short-circuited on zero
  recognised rows, which is exactly the post-restatement shape it was
  written from, and its own docstring documented a `--dry-run` its parser
  rejects.

- **Two published reproduction commands exited 2 for anyone who tried
  them**: the version registry's own command for the seventeen-page
  edition delta omitted its required `--editions`, and the restate
  script's docstring named a flag that does not exist. Both were found by
  a reader trying the command. Every published `scripts/*.py` invocation
  in the tree is now checked, statically and without executing anything,
  against the target script's own parser.

### Documentation

- **`docs/workspace-and-workflows.md` no longer says there is no workflow
  object, because there is one** (PFS-2025.10, PFS-2025.21). The page
  explains what a workflow IS before it shows a signature, carries the
  committed workflow matrix byte for byte, shows the one-line terminal
  command, and states the assessor's swept-row limitation plainly. Its
  "what does not exist yet" section was rewritten so nothing on it is
  false. The page was written the day before the capability landed and
  would have become a lie in one commit; a tier-1 guard is what made that
  impossible rather than merely unlikely.

- **The user guide's curated-helper count is a digit rather than a
  word.** The set passed twenty when the rotor emitters landed, and the
  guard that holds the guide to the module reads one word at a time, so a
  two-word number could never be read through it. The guard's own message
  named the remedy and the guide takes it; the word table deliberately
  stops at twenty and says why.

- **A trailing-edge parameter's fifth field is READ, RESTATED and
  reachable from a rotor row** (PFS-2026.06). The newest edition gives
  the relaxed trailing-edge component parameter an integer shedding
  direction, axial by default and azimuthal otherwise.
  `script.helpers.parse_relaxed_trailing_edge` reads a specification in
  either shape, `RelaxedTrailingEdge.render()` writes it back, and
  `cases.workflows.rotor_relaxed_trailing_edges` restates a rotor case's
  specifications in the direction its `ROTOR_SHEDDING` cell asks for.

  READ THE BOUNDARY WITH IT, because this bullet said the opposite half
  of it until 2026-08-20 and both halves are true. NO SCRIPTING COMMAND
  on any registered build takes the direction, so the emitted script is
  byte-identical with and without the cell, and no status, manual
  reference or version row moved. And THIS PACKAGE STILL WRITES NO
  COMPONENT FILE: the restated specifications are returned as text for
  the caller to write where their geometry keeps them. Whether the
  package should own that file is a product-owner question and is still
  open.

  The four-field form is not silently widened. A specification parsed
  with four fields renders with four, and asking for the axial direction
  on one that leaves the field unwritten returns it unchanged, because
  writing the 0 would hand a five-field specification to a build that
  reads four. A direction a row invents is refused before the first
  emission, naming the case, the key, the value and both accepted
  directions.

- **`reports/compat/README.md` gained three sections** (PFS-2026.15,
  PFS-2026.16, PFS-2026.17): which binary produced a report and why the
  committed corpus can no longer answer that, what a digest does NOT
  answer (the licence), and the identity check a replacement executable
  goes through before it spends a seat.

- **The command database's version metadata records what a licence tier
  could falsify**, beside the version rows it is about, and records the
  two statements the newest manual edition WITHDREW (PFS-2026.10,
  PFS-2026.16): the claim that at higher control-surface deflection
  angles the solver captures the tip vortices directly, printed twice in
  the previous edition and in neither place now, and the guidance to set
  the wake decay constant to zero for marine applications. Nothing in
  this repository asserted either as current, which is recorded as a
  measurement with its exclusions rather than as a reassurance.

- **Two new committed reports** (PFS-2026.08, PFS-2026.15). RPT-031
  records the search of the 26.123 scripting reference and Script Index
  for the command that sets the aeroelastic coupling tolerance: the
  answer is that NO such command is documented, with nine candidates
  rejected and a reason for each, and the modal-representation claim
  measured as absent from all nine manual editions. The chapter header
  that asked for that search is updated to cite it, so the file no longer
  asks for work already done. RPT-032 records the digests of the
  executables in hand as the baseline a replacement is compared against.

- **The three skills that spend a licensed solver seat carry an
  identity-first step** for a REPLACEMENT executable of an
  already-registered version (PFS-2026.15), a case that previously fell
  between all three.

- **`RPT-024`'s Script Index caution is amended with a DIRECTION rather
  than a correction.** It recorded only that the index UNDER-reports; the
  newest edition lists a command in its Script Index that its chapter
  body no longer prints at all, which is the mirror failure. The rule
  does not change and the body is still what is read; what changes is
  that a disagreement between the two is not by itself evidence of which
  one moved.

- **The getting-started page gains the time-resolved history section**,
  with an executed example, and states plainly that the file's shape is
  documented and not yet OBSERVED.

- **`docs/solver-cost.md`, a new page explaining what a run cost and how
  to show that a build got slower** (PFS-2018.02), with a worked example
  the docs suite executes, so it cannot rot into a lie. It says in plain
  words the three numbers the view refuses to invent: an untimed run is
  absent rather than zero, a column is a build AND an executable, and a
  comparison counts only work both builds did.

- **The Role-based review row of `docs/srs/standards.md` names the two
  mechanical refusals the project already relies on** (OPS-2005.07,
  closing OPS-2005.23 against the same edit). The PreToolUse hook denies a
  `git push` carrying no attestation over every commit the push makes new
  plus each ref it sends, and the same hook denies while a blocking
  incident is open in the shared ledger, whose one home stays the
  machine-configuration table in `CLAUDE.md`. The row previously stopped
  at the five reviewer charters, so the SRS published a WEAKER discipline
  than the one this changelog had already announced.
  `tests/test_claim_currency.py` holds the row per clause, so a gate
  described as a reminder fails tier 1.

- **The Adopted table of `docs/srs/standards.md` gains an `Enforced by`
  column on all 14 rows** (OPS-2005.08.01), with a lead paragraph defining
  the three answers it accepts: a repository path or a CI command, a named
  review seat with its charter, or the literal word convention for a
  practice nothing mechanical refuses. Five of the fourteen say so on
  purpose. `tests/test_claim_currency.py` fails when a cell is empty, when
  it names a repository path the tree does not hold, or when it names a CI
  command that appears in no workflow, and it resolves the column BY LABEL
  rather than by position.

- **The published layer map records `_errors`** (OPS-2005.12,
  OPS-2006.02.01). The generated architecture page and the SRS
  architecture chapter now carry `pyflightstream._errors`, the
  base-exception module, as the row below `versions`. It imports nothing
  from the package and most of the package imports it, and it appeared in
  none of the places the layering was stated. The page also renders that
  module's own docstring as its own section, so a reader asking why one
  module sits outside the pipeline gets the answer from the module rather
  than from prose about it.

  Four tier-1 guards now derive every prose restatement of the layer stack
  from the single home of it, the layer data in `pyflightstream.overview`,
  and fail naming the one file that disagrees: the fence in the SRS
  architecture chapter, that chapter's side-branch paragraph, the layout
  rule in `CLAUDE.md`, and the layer diagram in the user guide. The guards
  write out no layer name of their own, so they are a check rather than a
  fifth copy to drift, and the guide is covered for the first time by
  anything at all, since it is not built by CI.

- **The print-precision premise behind the operating-point tolerances
  cites its source** (OPS-2009.01.01). `results.conditions.FIELD_BINDINGS`
  and the `tolerance` attribute of `ConditionCheck` name the committed
  export the three-decimal print width was read from, state that this is
  ONE measured build rather than a solver guarantee, and say that beyond
  that file the threshold is project-chosen and claims nothing about the
  export. RPT-006 is cited as corroboration of the header's three-decimal
  print for a different header quantity, not as a second reading of these
  three fields. Five tests read the citation out of the source, open the
  export it names and assert the printed width against each tolerance, so
  the premise fails the suite instead of quietly becoming a recollection.
  No tolerance value and no behaviour changed.

- **The deprecation ledger's comment stops saying there is nothing to
  track** (PFS-2021.01.01). It said an empty tuple meant the package made
  no deprecation promises. TWO are live and neither is a module shim,
  which is all that tuple can hold: the
  `analysis_setup(vorticity_drag_boundaries=...)` parameter warning, and
  the dry-run rename that the v0.5.0 notes recorded as announced and not
  landed, and that is still unlanded. The comment now names both with the
  line and the quoted text of each, says the tuple models module shims
  only, and records no removal version, that being a seat decision while
  NFR-20 does not bind before 1.0.

- **The FSI package no longer cites a private tracking identifier** for
  the unverified status of the structural model's primary sources
  (PFS-2017.01.02). `fsi/centrifugal.py` and the FSI README now say in
  plain words that the primary sources have not been independently checked
  against the formulas implemented here, and that the formulas should be
  read as transcribed from the coupling plan and believed correct rather
  than as verified against the papers. The identifier's only home was
  another repository and no committed report carries it, so a reader
  following it reached nothing. Every `Source:` citation is unchanged, and
  a new tier-1 table pins the primary source each of the fourteen FSI
  physics functions names, so a future rewording cannot quietly drop one.

- **`CLAUDE.md`'s machine-configuration table no longer claims
  documented-here-only enforcement for the shared-ledger tree variable**
  (OPS-2013.03, OPS-2013.29). It names `tests/test_snap_skip_status.py`,
  which measures the vendored snapshot tool against a sandboxed copy in a
  child environment with the variable cleared: green that an unconfigured
  tree is really skipped and that `log` refuses one on stderr with a
  nonzero status, and, until the kit promotion landed later in this same
  cycle, a strict expected failure that `snapshot` exited 0 having taken
  nothing.

  THE PROMOTION LANDED, so all three arms are ordinary passing cases now:
  the 0.2.25 kit body was vendored on 2026-08-20, and vendoring it turned
  the three strict markers into XPASS in one run, which is what the
  strictness was for. **A BEHAVIOUR CHANGE TRAVELS WITH IT and it is not
  only a bug fix**: on a machine that has never set
  `COORD_SHARED_LEDGER_TREE`, the no-argument `snap.sh` now exits 1 every
  time, because a skipped tree reaches the aggregate status instead of
  being swallowed. Nothing in either repository reads that status, so
  nothing breaks; the alternative was a recovery tool reporting a snapshot
  of the shared incident ledger it had not taken. Set the variable, or
  call `snap.sh pyflightstream` by name. The same section now says
  to check the process ENVIRONMENT as well as `.claude/settings.local.json`
  before concluding the shared tree is unconfigured, because a user-scope
  export satisfies a bash script just as well and leaves that file with no
  row.

- The two Tier 3 WARNs on 26.123, both `CDo` and both on SMI cases, gain
  a committed triage (`reports/physics/TRI-26123-CDo_2026-08-18.md`).
  Eleven of the thirty-eight metrics moved, `CDo` is the only one that
  moved OUT of band, every `CDo` METRIC moved and all three moved down,
  and both exceedances sit below their fail bands. On the reference
  decision the references stay untouched and the warns stand. The 26.123
  side turns out to be REPRODUCED already, by two independent executions
  of 2026-08-17 that agree on all thirty-eight metrics, because
  `pyfs-qa drift` runs its own physics for each build; the rerun owed is
  26.122's alone, and is registered rather than implied.

- **A guard added the day before was vacuous, and its own predicate was
  satisfied by the defect.** The rule "a library refusal naming
  `--some-flag` must also name `some_flag`" derived the parameter by
  de-hyphenating the flag, and for any flag without an internal hyphen
  that string is a SUBSTRING OF THE FLAG: `"cases"` is in `"--cases"`.
  Of the three raise sites it walks it genuinely checked one, the site
  the same commit had just repaired. It now asks for the two shapes this
  package actually uses, `parameter (CLI: --flag)` and `parameter=`, and
  it is driven by fixtures as well as by the tree, so it has a red case
  that does not move when the source does.

- **The FR-02c rewording silently dropped a normative sentence from the
  published requirements index.** `gen_requirements_index.py` publishes a
  requirement's FIRST paragraph as its statement, and the rewrite opened
  a second paragraph above the shadowing rule. The statement is one
  paragraph again and the requirement text says why the break matters.

- Two requirement texts move, both on the ruling of 2026-08-18.
  FR-02c stops enumerating the builds that share a vendor name, an
  enumeration that had gone stale twice by construction and was removed
  from six other homes on 2026-08-17 for that reason. NREQ-05 stops
  saying it excludes NOTHING, which was true of the eight editions swept
  on 2026-08-08 and stopped being true when SRC-751 was registered
  documenting a command the database does not carry; the corrected
  wording separates an exclusion from a dated debt.

- One count was wrong in two places and right in two others. 369 database
  rows carry 26.123; 85 cite the probe report, 84 `verified` and one
  `broken`; and 368 carry the restated note, because `apply_compat`
  overwrites the note for a broken outcome instead of carrying it
  through. The restate script said 85 in its docstring and 84 in its
  code, twenty-six lines apart.

## [0.7.0] - 2026-08-11

**Eight builds, and every command every one of them documents.** A
FlightStream build is registered, 26.122, and every command any of the
eight registered editions documents now has an entry: `pyfs-manual
sweep` reports zero absent, which it has never done for more than the
newest four builds before.

READ THAT CLAIM AT THE LEVEL IT IS MEASURED AT, because the first
version of this paragraph did not. Zero absent is a statement about
ENTRY NAMES. Ten readings across four commands are deliberately
withheld, so `IMPORT_CAD` and `CAD_CREATE_IMPORT_CURVE_CCS` cannot be
emitted on three builds and `NEW_OFF_BODY_STREAMTUBE` and
`SET_SCENE_CONTOUR` cannot on two, even though those manuals document
them: each of those editions writes the command in a LAYOUT a version
row cannot express, and a row that ignored the difference would emit
the newer shape under the older edition's citation. The entries say so and
`PLN-20260810-1200` holds the schema decision. The sweep now reports
that second measure beside the first, so the gap is named by the tool
rather than by this sentence alone.

### API surface delta

New public names: `pyflightstream.utils.stale_citations`,
`pyflightstream.utils.StaleCitation`,
`pyflightstream.utils.unreachable_commands`,
`pyflightstream.utils.UnreachableCommand`, the three protocols
`pyflightstream.utils.RegistryLike`, `CommandEntryLike` and
`VersionRowLike`, `pyflightstream.utils.manual.citation_reach`, the
`pyflightstream.utils.manual.Reachability`, the `pyfs-manual
citations` subcommand, seven keyword arguments on
`pyflightstream.script.helpers.solver_settings`, one (`sonic_velocity`)
on `pyflightstream.script.helpers.atmosphere`, and the `source` field on
`pyflightstream.utils.Edition` with the matching `source:` key in the
edition manifest, which is what lets a citation be checked against the
document it names.

Behaviour changes a caller can see. `atmosphere` takes `sonic_velocity`
and reads its script's version to decide which five fluid properties
FLUID_PROPERTIES wants, so it serves the three pre-26.100 builds it had
stopped serving. Its `altitude_units` defaults to None instead of
`"METERS"`, so an omission can be told from an explicit pass: nothing
changes on the seven builds that take a units token, which still emit
METERS when nothing is given, but 25.000 takes no token and reads the
bare AIR_ALTITUDE value in FEET (SRC-749 p.286), so there the helper
REQUIRES `altitude_units='FEET'` and refuses silence. The same call is
metres on the other seven, a factor of 3.28, which is the one silence
worth refusing. `initialize_solver` refuses at entry on 25.000 rather
than dying inside the binder on a keyword the caller never typed: that
edition's grammar takes ten arguments and this helper's parameters do
not map onto it. The refusal for a command
with no evidence lists builds by reachability and marks inherited ones,
so it no longer hides the newest build; and `pyfs-manual sweep` reports
a second finding, and `--fail-if-absent` gates on the row-level measure
alone: a name with no entry is unreachable too, so one term covers both
and the other could not have been falsified by any test.

Incompatible changes: none for a released signature. Deprecations:
none.

### Added

- **FlightStream 26.122 is registered**, vendor build 8092026, the day
  after it was issued. It is the second hotfix of the 26.12 release and
  says so from evidence rather than from its index: the vendor sells it
  as 26.12, its executable is named for 26.12, its solver prints 26.1
  like the other two, and the three build numbers are one release six
  weeks apart. Its manual documents the largest scripting surface of the
  eight editions, 372 commands. Read its `operational` level with its
  evidence: it reaches that level entirely on records inherited from
  26.120, because no command has been probed on this build.
- **Ten commands the 26.122 edition is the first to document**, among
  them `ROTATE_SURFACE`, `SOLVER_TIME_AVERAGING`,
  `SET_NEW_UNSTEADY_SOLVER_ACTION`, `EXPORT_BL_VELOCITY_PROFILE` and
  `SET_ACTUATOR_WAKE_TYPE`. Two of the ten stand where a command this
  edition stops printing stood, and neither pair is a plain rename:
  `ROTATE_SURFACE` takes six arguments, five on the command line and the
  surface indices on the next, where `SURFACE_ROTATE` is a keyword block
  of eight, and the two options
  `SPLIT_VERTICES` and `ADAPTIVE_MESH` have no equivalent in the newer
  form. Both superseded commands carry a `removed` row for 26.122 naming
  its successor.
- **Sixteen commands only the pre-26.100 editions document**, which
  closes the last gap in coverage. Three are version stories rather than
  disappearances: `SET_SOLVER_MODEL` becomes an argument of
  `INITIALIZE_SOLVER` in the edition that drops it,
  `SOLVER_UNINITIALIZE` and `REMOVE_INITIALIZATION` are exactly
  complementary across the eight editions, and the `PHYSICS` block
  becomes the two standalone autodetection commands at 26.000. That last
  one explains a gap this repository had already measured and misread:
  the two 25 builds are not missing trailing-edge autodetection, they
  spell it as one block.
- **Nineteen per-version argument grammars** for the three pre-26.100
  editions, read page against page. `FLUID_PROPERTIES` takes a sonic
  velocity and no specific heat ratio on all three; `INITIALIZE_SOLVER`
  has a different argument list on each of them.
- **`pyfs-manual citations`**, which re-reads every version row's cited
  page against the edition it names and exits non-zero when one does not
  hold. It exists because ten citations were found pointing at a
  document that had moved underneath them, each at a real page of a real
  manual, and nothing re-checked a citation once written.
- **Seven solver-setup flags** on `solver_settings`, for the
  settings-family commands only the older editions document:
  `solver_model`, `valarezo_criterion`, `crossflow_separation_cp`,
  `wake_relaxation`, `wake_streamwise_agglomeration`,
  `adverse_gradient_boundary_layer` and `vortex_ring_normalization`.

### Changed

- **A per-version argument override now states only its difference.**
  Unstated fields are filled from the base argument of the same name, so
  changing one field no longer means restating every other field of
  every argument. That restating is how a second field changes by
  accident: writing this release's overrides lost a list separator and
  an entity citation, which is the same defect this repository already
  had a test for. Writing `cites: null` still clears an inherited value,
  since inheritance reads the raw file where an unstated field and one
  stated at its default are distinguishable.
- **A `removed` row's citation no longer counts as manual coverage.** An
  absence is read across a whole chapter, so one such note marked every
  page of an edition as cited and the published coverage section went
  from a page-by-page gap listing to "every page is cited".
- The steady-polar example's version-awareness section now shows the two
  refusals that differ, a command a build does not carry and a command
  it carries with a different argument list, replacing a claim about
  26.0 having no recorded evidence that stopped being true.

### Fixed

- Ten version rows citing pages of the 25.000 manual were five or six
  pages off, from the conversion of that edition being corrected after
  the rows were written.
- **Three builds could not emit a command their own manuals document.**
  `EXPORT_ALL_SURFACE_STREAMLINES` had no row for 25.000, 25.100 or
  26.000 while its two family siblings on the same manual pages did, and
  the coverage sweep reported zero absent throughout, because it
  compares entry names and an entry missing one edition's row reads as
  covered.
- **26.122 would have emitted two commands the build before it has a
  negative record for.** Inheritance runs from the base release rather
  than from the sibling hotfix, so a `removed`-on-a-run record and a
  `broken` record on 26.121 were both overturned by 26.120's
  `documented` one.
- The README's opening example promised a refusal it no longer made and
  printed nothing, and CI could not see it: an example whose only claim
  is that something is refused goes green the day the refusal stops
  firing. It asserts now, and CONTRIBUTING states the limit.
- A note on `SET_SOLVER_MODEL` said the successor takes the same four
  tokens. It takes six, of which one is shared.
- **`atmosphere` serves the three pre-26.100 builds again.** Those
  editions take a sonic velocity and no specific heat ratio on
  `FLUID_PROPERTIES`, so entering their grammar closed both doors on
  them at once: passing the five newer properties was refused by the
  binder for a keyword the edition does not have, and omitting one was
  refused by the helper, which quoted a page of a different edition.
  The helper reads its script's version now and takes a new
  `sonic_velocity` keyword. The 25 series is the series registered so
  published work can be reproduced, so the curated path has to serve it.

### What the review changed

Reviewer passes over four rounds read this work, and the entries above
are what survived them. The count is deliberately not given: it was
written three times in this release at two different numbers and no
scope, and an unanchored count is worse than none. Four findings are
worth a reader's attention because they were wrong in ways nothing
mechanical could see.

The completeness claim was measured by a tool that cannot measure it.
`pyfs-manual sweep` compares entry NAMES, so an entry carrying no row
for one edition read as covered, and it reported zero absent while
three builds could not emit a command their own manuals document. The
sweep now reports both halves, and the completeness gate reads the
row-level one.

Four `removed` rows said the 26.122 edition does not print a command
while that edition's Script Index names it. The body does not, the
index does, and the body is what a script is written from, so the
conclusion stands and the citation did not. Each row states both
sources now. Measuring it inverted something worth knowing: the three
commands still emitted for that build are absent from the body AND the
index, while the four refused are absent from the body and present in
the index.

And two curated helpers stopped serving three builds the moment their
grammar was entered. `atmosphere` is fixed on both halves of its
signature; the second half was found only because a reviewer
parametrised over the builds instead of testing the one that changed.

The fourth is this release's own tag, and it is recorded here because
the fix ships inside the artifact. A tier 1 test imported the `[manual]`
extra with no guard, so the suite failed on the four platform legs and
on the coverage job, five of the run's eight checks, and the v0.7.0 tag
was pushed anyway, fifteen seconds after the branch, while seven of
eight jobs were still running. Nothing was published: `release.yml`
binds publishing to its gates and they held. Release process only; no
runtime change.

The account first written into the fixing commit was wrong, and the
correction is the useful part: the defect was NOT visible only in a
wheel environment, it was red in the ordinary matrix too, and the real
failure was a tag that did not wait for an answer CI was still
computing. The first red conclusion landed a minute and a half after the
tag, the last four minutes after it.

Both causes now carry a guard rather than a sentence:
`tests/test_extras_isolation.py` refuses an unguarded import of any
distribution a CI job may lack, `.claude/hooks/ci_release_gate.py`
refuses a version-tag push while that commit's CI is red, pending,
absent or unreachable, and a third guard, the `test-all-extras` CI leg,
installs all five declared extras so an assertion gated behind one is
executed somewhere rather than skipped everywhere
(INC-20260810-2140-shared).

One thing a reader comparing the tag to this section would otherwise
have to infer: the `v0.7.0` tag is MOVED onto the corrected commit
before publication. The first tag of that name published nothing, and
0.7.0 ships from this tree rather than from the commit that tag
originally pointed at.

### Known gaps

- **Three commands the 26.122 edition stops printing are still
  emitted for it.** That build inherits from its base release 26.120,
  and `CREATE_BULK_SEPARATION`, `SURFACE_DELETE` and `SURFACE_CLEARALL`
  have no record on the builds inheritance reaches past. Not that they
  have no successor and no measurement, which an earlier draft said and
  this repository's own files refute three times over: `DELETE_SURFACES`
  is recorded as replacing two of them and RPT-015 measured 26.121
  rejecting the third. The four that ARE refused
  are refused on stronger evidence, and the split is not a rule anyone
  chose: it is what the available evidence happens to look like. One
  probe run of seven names settles it (`PLN-20260810-1600`, and the
  licensed-evidence queue in `docs/srs/roadmap.md`).
- **Nothing has been probed on 26.122 at all.** It derives
  `operational` entirely on inherited records; the README row says so.
  The same is true of 25.000, 25.100 and 26.000, so four of the eight
  registered builds rest on manual evidence or on inheritance and no
  COMMAND has been measured on any of the four. Each has met a solver:
  an identity probe read its banner, which is where its build number
  comes from and is all it claims.
- **`initialize_solver` does not serve the three pre-26.100 builds.**
  Their INITIALIZE_SOLVER takes a different argument set, and this
  release fixes only `atmosphere`, the other helper the same gap hit.
  The refusal names the page and points at `script.emit`.

## [0.6.0] - 2026-08-09

**Seven builds, every one of them identified.** Three more FlightStream
builds are registered and every registered build now carries the vendor
build number its solver prints, read from a committed report. The three
that joined are the ones the published work was run on, so a
reader reproducing any of it has an identifier that resolves to a number
they can check against their own install.

Getting there meant finding out why three installs had looked broken.
They were not: the package was calling them with a command line they do
not accept, and a FlightStream build given a script argument it does not
recognise starts, checks out its licence, receives no script, and waits.
That reads as a hang with a clean licence and an empty log, which is why
two wrong diagnoses were written down before the right one. The fix is
one dash instead of two, measured across all seven builds.

The rest of the release follows from having seven readable builds. A
generated page maps what a solver prints onto the identifier to pass,
because a release name does not identify a build: the vendor ships two
builds as "26.1" and two more as "26.12". A new `pyfs-manual surface`
reports what each build documents and what changed between them, and
RPT-024 is its first output: the scripting surface grew from 272
commands to 364, unevenly, with 75 arriving in a single step.

### API surface delta

New public names: `pyflightstream.run.SCRIPT_ARGUMENT`,
`pyflightstream.run.describe_invocation`,
`pyflightstream.run.ExecutionResult.diagnosis`,
`pyflightstream.versions.FsVersion.prints`,
`pyflightstream.reference.markdown_build_table`,
`pyflightstream.utils.edition_surfaces`,
`pyflightstream.utils.surface_changes`,
`pyflightstream.utils.SurfaceChange`, and the `pyfs-manual surface`
subcommand. Incompatible changes: none for callers; the solver command
line changes, see below. Deprecations: none.

### Added

* **Three more FlightStream builds are registered, and every registered
  build now carries its vendor build number.** 25.000 (build 12162024,
  December 2024), 25.100 (build 5062025, May 2025) and 26.000 (build
  10202025, October 2025) join the registry at `registered` level. They
  are there for reproducibility rather than coverage: published work was
  run on the 25 series, and a reader of it needs the identifier to exist
  and to resolve to a build number they can check against their own
  install.

  Read their POSITION rather than assuming it. They precede every build
  the registry had, so they were inserted at the FRONT. The rule that
  versions are only added and never dropped is about dropping, not about
  the end of the list: the list is ordered by RELEASE order, so a build
  obtained later can belong earlier in it.

  The canonical scheme generalises from `26.XXX` to `YY.XXX` in the same
  change, which is what it always meant; the major was written as a
  literal while 26 was the only one registered. No identifier was
  reassigned. SRS FR-02a and BRF-19 carry the amendment.

* **`pyfs-manual surface` reports what each build documents and what
  changed between builds.** The sibling of `sweep`, off the same edition
  manifest: `sweep` asks what the database is missing, `surface` asks
  what each build documents so two builds can be compared. RPT-024 is
  its first output and is regenerated rather than maintained.

  The measurement, since it is the answer to "what changed between the
  builds I ran my research on": the scripting surface grew from 272
  commands to 364 across the seven builds, and 75 of that arrived in one
  step, 26.000 to 26.100, essentially the whole CAD and cross-section
  family at once. The step to watch is 26.100 to 26.101, which gained 35
  and lost 16 between two builds the vendor ships under the SAME release
  name.

  Lost means the newer manual stops printing the command, never that the
  solver stopped accepting it; those are different facts and only a
  probe separates them. The report says so rather than letting a reader
  infer a removal, and it lists names rather than only counts, because
  the counts cannot see that the four `CREATE_NEW_MOTION_*` commands of
  25.000 are one renamed `CREATE_NEW_MOTION` in 25.100 rather than four
  removals and one addition.

  The reading is cross-checked against the command database: for all
  four builds the database records, every command the manual documents
  has an entry, which is what makes the page ranges trustworthy.

* **A generated "Which build do I have" page.** The vendor ships two
  builds as "26.1" and two more as "26.12", so a paper recording
  "FlightStream 26.1" has not said which solver produced its numbers.
  The page maps the release name and build number a solver prints onto
  the canonical identifier to pass, and it is generated from the
  registry at docs build time so it cannot drift from it. It shows the
  two fields separately rather than the banner line, because that line
  is not byte-identical across builds: the 25.0 solver writes a NUL byte
  into it where the newer builds write a space.

  The registry gained a field for this and the reason is the sharper
  half of the release. `FsVersion.prints` records the release name the
  solver STATES ABOUT ITSELF, which is not the name the vendor sells the
  build under and may not be derived from it: 26.120 and 26.121 are sold
  as "26.12" and both binaries print "26.1". A first draft of the page
  keyed the column on the sold name, which would have sent the owner of
  either build to a row naming a different solver. It is recorded from a
  committed report's `solver_identity`, like the build number, and a
  tier 1 guard cross-checks it against the banners in those reports.

* **`pyfs-qa probe --identity-only`.** Judges no command: it runs the
  baseline, captures the solver's identity banner, and writes the report
  pair. That is how a newly registered build gets its build number into
  a committed report, which is the only place the registry accepts one
  from. Registering the three new builds is what it was built for, and
  it reads a build in about a second.

* **The probe baseline can run on a build that records no command.**
  Such a build has no grammar of its own for the three instruments, so
  the baseline borrows it from the newest build that records all three
  and reports the build unusable if the borrowed grammar does not work
  there. Without this the three builds registered in this release could
  not be probed at all, since a baseline needed a row and a row needed a
  probe. What the report does not yet say is that the borrowing
  happened, which is registered as PLN-20260809-2410.

### Fixed

* **The solver command line was version dependent and hardcoded as if it
  were not, which made three builds look broken.** The executor passed
  the script argument with two dashes, the spelling SRC-003 documents.
  The 25 series does not recognise it: the 25.0 manual documents the
  one-dash form. `pyflightstream.run.SCRIPT_ARGUMENT` is now the
  one-dash form, which RPT-023 measured working on all seven registered
  builds.

  The failure mode is the part worth publishing. A build given the
  spelling it does not know does not refuse it. It starts, prints its
  banner, checks out its licence successfully, receives no script, and
  waits for a user. Under `-hidden` with the standard streams redirected
  there is no console for it to report on, so the Fortran runtime raises
  `severe (30)` on `CONOUT$` and opens a modal dialog that no timeout can
  answer. What the harness sees is a clean licence checkout, an empty
  log, and a wall-clock time equal to its own timeout. Two diagnoses
  were written down before the right one, one of them naming a licence
  seat that was never held.

* **Every report derives its executor line instead of restating it.**
  That sentence sat as six literals across the three report writers, one
  machine-readable and one rendered each, and nothing would have noticed
  them disagreeing with the code: changing the argument would have left
  forty reports describing an invocation the package no longer made. It
  comes from `describe_invocation()` now, and a tier 1 guard compares
  the flags in the sentence with the flags the executor passes, as whole
  tokens. The first version of that guard asked whether each flag
  appeared in the sentence and a wrong sentence satisfied it, because
  `-script` is a substring of `--script`.

* **A failed solver run now says what the solver said.** Four sites
  composed `log_text or stderr or return code` by hand and all four
  omitted the same field: standard output, which the executor captures
  on every run and which nothing in the package read. A fifth, the
  timeout branch, discarded even those and recorded only "timed out and
  was killed".

  That is what made this release's own defect cost a day. Everything the
  harness reads is written by the solver AFTER it accepts a script, so
  every failure BEFORE that point looks identical; the baseline refusal
  told the operator the environment was unusable and offered the licence
  checkout as one of three candidate causes, while holding unprinted the
  line saying the checkout had succeeded. About a dozen licensed solver
  launches went into the licence hypothesis.

  `ExecutionResult.diagnosis()` is now the single composer, reporting
  the outcome and every non-empty channel, and the refusal quotes it
  instead of naming suspects it cannot rank. A tier 1 AST guard refuses
  any module outside the composer's home that reads two or more captured
  channels in one expression, which guards the shape rather than the
  five sites (INC-20260809-2230).

* **A stale editable install no longer stamps the wrong version into
  evidence.** Every compat, drift and physics report records
  `package_version` from the installed metadata, which for an editable
  install is whatever was recorded the last time the project was
  installed rather than what the source says today. That gap put
  `package_version: 0.5.0` into seven identity reports produced by the
  0.6.0 tree, one of them for a build the published 0.5.0 could not have
  driven at all. The reports were not rewritten, the writer refusing to
  overwrite evidence and rightly so; a tier 1 guard now fails when the
  installed metadata disagrees with the source tree, before a licensed
  run is spent, and names the one-line remedy.

* **The compatibility matrix and the offline `help()` page define their own
  cells.** Both carried a definition of the empty cell and of the
  inheritance mark and left the four status words to be inferred from
  their names. A legend now names all five, what each rests on, and what
  `Script.emit` does with it, which is the half no status name carries:
  three of the five are REFUSALS, each with a different exception class.
  Both layers render one tuple, so they cannot come to disagree, and the
  per-chapter reference pages stop restating the definitions and link to
  it instead.

  The reasoning worth keeping is about the guard rather than the text.
  The first version of it let eight of nine mutants through: every check
  was a search for a fragment ANYWHERE on the page, so the two columns
  could be swapped between `documented` and `verified`, the named
  exception class could be the wrong one, and the two non-refusing rows
  were proven by an `except Exception` that read an argument refusal as
  a successful emission. An emitter that could emit nothing at all left
  the file green. The guards now locate a row and assert inside it, tie
  each cell's opening clause to whether the model refuses that status
  without a committed report, and prove emission by emitting. Eleven of
  thirteen mutants die; the two that live are inversions of explanatory
  prose and are registered rather than papered over.

## [0.5.0] - 2026-08-09

**The command database is complete.** Every command that any of the four
registered FlightStream manual editions documents is in it, 388 entries,
and every entry carries a version row for each edition that documents the
command. Before this release the database held 147 commands and answered
for a curated subset of the solver; it answers for the whole scripting
surface now, and all four registered builds derive the `operational`
support level, which is checked by building a minimal end-to-end workflow
for each of them.

The rest of the release follows from that. Reading the command pages of
four editions found the ways a manual contradicts itself, and each
one is recorded on the entry it affects rather than smoothed over: a
sample copied from the neighbouring command, a heading and a table
disagreeing about an argument count, one command documented on two pages
where only one says anything, and a value set that gained a token between
builds. Where a page could not settle a question, the solver was asked on
a licensed machine and the answer is a committed report.

### API surface delta

* **Eighteen commands verified through the saved-state instrument, and
  four reverted to unobservable WITH their measurement.** 26.121 goes
  from 66 verified to 84: the full run of the same day recorded 66
  (`CMP-26121_2026-08-08_full`) and the saved-state run added 18
  (`CMP-26121_2026-08-08_savedstate2`). New public assertion `qa.fsm_changed`
  (`RPT-022`), for the
  commands whose effect is real and has no distinctive value to search
  for: a toggle writes T or F and a binding writes an index of 1, which
  match everywhere, so what it asserts is that the saved state MOVED.

  The four that came back broken were triaged rather than recorded, and
  none of them is broken: an actuator appears to be enabled at creation,
  the constant free-stream form is the documented solver default, every
  boundary appears pre-selected for analysis, and a clean synthetic wing
  has no wake termination nodes to detect. Each keeps an unobservable
  record whose note is now a measurement instead of a guess.

  BOTH SAVED-STATE ASSERTIONS COMPARED SETS OF LINES AND BOTH WERE WRONG
  FOR IT. The simulation file is positional and most of its lines are
  short tokens, so a line that genuinely changed from `0` to `1`
  contributes nothing to a set difference. Two commands that had really
  written to the state were recorded broken under that reading. They
  read a positional diff now.

* **Four chapter questions measured, and one was a command the emitter
  was building and the solver rejects** (`RPT-021`).

  `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` IS REMOVED ON 26.121. It is
  documented by the 26.101 and 26.120 editions and by neither
  neighbour; with no 26.121 row the registry handed it 26.120's
  evidence by hotfix inheritance, so a caller on that build got a
  validated script the solver refuses with an unrecognised command. The
  row is `removed` now, promoted from the run rather than read off the
  hotfix edition's silence, and a caller on 26.121 gets a refusal naming
  the build instead of a line the solver rejects. Second measured
  counter-example to that inheritance after `AIR_ALTITUDE`, and the
  first where the inherited evidence was optimistic.

  That row also needed a citation kind the database did not have.
  `ProbeOutcome` has no `removed` member, so the harness records a build
  that lacks a command as `broken`, which claims something else, and the
  guard that checks a status against its own compat yaml therefore had
  nothing to open. `VersionStatus` gains `probe_ref`, a committed
  narrative report of a run, admissible for `removed` and REFUSED for
  every other status: `verified` and `broken` stay checkable against
  harness output, because a guard whose population quietly shrinks
  reports green either way.
  `PLN-20260809-0300-the-harness-has-no-removed-outcome` carries the
  harness change that retires the field.

  `CREATE_NEW_BASE_REGION` GAINS `CUSTOM`: the solver accepts either
  that or `USER` there, while `SET_BASE_REGION_CP` accepts `CUSTOM`
  alone. The two pages disagreed and both are right about their own
  command; the manual is merely incomplete about the creator.

  DELETING A COORDINATE SYSTEM RENUMBERS the ones above it, so a frame
  index recorded before a delete means something else after it. Nothing
  in the library emits that delete and the entry states the safe
  pattern; what to do in `EntityRegistry` is a design decision left
  registered (`PLN-20260808-2100`).

  Two judgements this sweep took on reasoning were confirmed by
  measurement: `SURFACE_ROTATE` takes the sample's `SURFACES` and
  refuses the table's `SURFACE`, and `CAD_CREATE_MIRROR_CURVE`, the
  sample's spelling, is not a command.

* **26.100 IS OPERATIONAL, and it was the DATABASE holding it back, not
  the solver.** A per-edition sweep found 122 pairs of (command, manual
  edition) that an edition documents and this database had no version
  row for, so the emitter refused a command the caller's own manual
  prints and nothing distinguished that from the command not existing.
  Forty of them were on the February build, which is why its minimal
  end-to-end workflow could not be built. All four registered builds now
  derive `operational`.

  WHAT 122 COUNTS, since a reader comparing it against the diff will
  otherwise reach for the wrong number: pairs, not commands. One command
  documented by three editions and carrying a row for none of them is
  three pairs, and the backfill wrote 124 version rows, the two over
  being the per-version grammars written the same day. The count of
  distinct COMMANDS touched is smaller than 122 and is not the figure
  this stanza is about.

  EVERY PAIR WAS READ ON ITS PAGE, and four of the 122 turned out to
  differ, each now carrying its own per-version grammar rather than a
  copied row:

  - `NEW_SURFACE_SECTION_DISTRIBUTION` on 26.100 and 26.101 takes six
    keywords, not seven. The optional `INCLUDE_SYMMETRY` reached this
    database from a PROBE of a working 26.120 script and is first
    documented in 26.121, so a copied row would have offered older
    builds a keyword no evidence places in them.
  - `SET_TRAILING_EDGE_TYPE` on 26.100 closes its type set at three
    tokens; `VORTEX_SHEDDING` first appears in the May edition.
  - `SOLVER_PROXIMAL_BOUNDARIES` on 26.121 documents a second call form
    the older editions do not print, a count of -1 selecting every
    boundary and taking no index lines, so that row declares the
    sentinel and makes the list optional.
  - `NEW_CCS_WING_CONTROL_SURFACE` on 26.100 and 26.101 takes eight
    arguments and not ten: `SPACE` and `AXIS` arrive with 26.120, so
    spanwise placement is parametric only on the older builds.

* **The saved simulation is an instrument, and forty commands stop being
  unobservable** (`RPT-020`, `RPT-022`). The compat reports called their effects
  "stored in binary form"; the .fsm is sectioned TEXT and carries them.
  `ProbeSpec.save_state` brackets the target with SAVEAS and the new
  `qa.fsm_gained` asserts a distinctive value appears on a line the
  target added or changed. Eighteen commands verified on 26.121 with it across the two saved-state
  runs, eight of them through `fsm_gained`,
  among them the actuator axis, radius, rpm and swirl, and the frame
  origin and axes.

  It reads the DIFF rather than the whole file, because the first
  version did the latter and marked a working command BROKEN: the token
  it searched for also occurred somewhere innocent in the before-state.

  THE SOLVER NORMALISES A COORDINATE-SYSTEM AXIS WHATEVER THE FLAG SAYS.
  Found because the instrument reported `SET_COORDINATE_SYSTEM_AXIS`
  broken and the diff disagreed: a direction passed with the normalise
  flag FALSE is stored divided by its magnitude, to all seventeen
  digits. A direction cannot carry a scale.

* **MEASURED: a keyword block is read by NAME, not by position**
  (`RPT-019`, closing `PLN-20260808-2200`). Every `keyword_block` entry
  in the database fixes an order and nothing had ever asked whether the
  solver reads it. On the 26.121 build, the same five `FLUID_PROPERTIES`
  keyword lines in documented, transposed and fully REVERSED order leave
  the identical solver state, which a positional reader could not do.

  So the order an entry fixes is cosmetic, the
  `STABILITY_TOOLBOX_NEW_COEFFICIENT` table-versus-sample disagreement
  has no consequence, and the database-wide audit that a positional
  answer would have forced is not owed. The residual is in the report:
  one command, one build, and a parser being uniform over its own
  grammar is an inference.

  A GRAMMAR FACT FELL OUT OF BREAKING IT. A keyword block is terminated
  by a BLANK LINE; without one the solver reads the next command as a
  keyword line, and the error names that following command rather than
  the block. The emitter has always written the separator, which is why
  no script this library builds had ever hit it and why nothing asserted
  it. A tier-1 guard does now, proven by removing the separator.

* **The emitter has ONE way to know what an index cites, where it had
  two** (`PLN-20260807-1410`, the design decision of 2026-08-08). An
  argument declares `cites` on its own entry, and the two global maps
  from argument NAME to entity kind are gone.

  They were already the fallback rather than the rule, and a fallback
  quietly covering 101 arguments is not a fallback. A name is a guess
  about an argument; a declaration is the argument saying so, which is
  why the maps could not carry `index`, a spelling that means a surface
  in one chapter and a section in three others. All 101 now declare it,
  including three that declare it on a per-version grammar rather than
  the default one.

  The visible gain is in the database rather than in the code: reading
  an entry now tells you whether its index is resolved and range
  checked, where before you had to know the map. The tier-1 closure
  guard lost one of its three ways to be satisfied, found the three
  per-version sites the bulk pass had missed, and was re-proven by
  mutation.

* **What the five reviewer passes changed, because two of it is
  user-visible.** `read_editions` is renamed `read_edition_manifest`
  before anyone depends on it, `Edition` is keyword-only (its two page
  ranges are the same type, so positionally they are interchangeable and
  a swap reads the Script Index as the scripting reference with nothing
  able to detect it), `sweep_editions` takes `recorded` by keyword and a
  `reader` for its one pdf dependency, and the manifest refuses an
  unknown key, a missing manual and a bad row before any manual is
  opened.

  THE SNAPSHOT NOW REPORTS THREE MORE SOLVER DEFAULTS.
  `rotor_induced_velocity_blending`, `wake_numerical_relaxation` and
  `jet_wake_decay_normalized_length` had their manual defaults written in
  prose; they are `default` and `default_ref` fields now, so a caller who
  leaves them unset gets the documented value and its page in
  `SolverSetup` rather than an `unknown`. A default the database records
  is a default the snapshot reports.

  `ArgSpec.on_command_line` gained a third refusal: an OPTIONAL argument
  cannot sit on the command line, where arguments are positional and
  unnamed, because omitting it would shift the ones after it into its
  place and the solver would read the line without complaint. Both
  current users are required, so the gap was latent, and it is the same
  failure class the field was added to prevent.

**INCOMPATIBLE CHANGES, first because they are what an upgrade can
break.** Five, all of them from earlier in this development cycle and
each explained in its own stanza below.

* `resolve("26.1")` RAISES `AmbiguousVersionAliasError` where it
  returned 26.100. The vendor shipped two releases under that one name,
  so the alias no longer identifies a build; pass a canonical
  identifier, `"26.100"` or `"26.101"`, and the refusal names both.
* `FsVersion(...)` refuses construction at a hotfix index, one whose
  last digit is not zero, unless the call states `inherits_base`.
  Whether a build carries its base release's command evidence is a fact
  about two vendor builds, and defaulting it let a hand-built version
  inherit a whole command set by omission. Registered builds are
  unaffected: `resolve` fills the field from the registry.
* `SWEEPER_SET_VELOCITY_SWEEP`'s file path moved from the second
  positional argument to the third. Pass it as `filename=`.
* `solver_settings(viscous_excluded=[])` now emits
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES` rather than a `SET` with a count
  of zero and an empty payload line, which the solver misread.
* A database entry with an inline list argument may no longer declare a
  separator other than `space`, and an `on_command_line` argument may no
  longer be optional or be preceded by a keyword line; the load refuses
  each. Both reach an entry author rather than a caller, and no shipped
  entry breaks.
* `Script.emit` refuses a payload count with no payload under it, on any
  command whose list argument is optional, unless the count is the
  documented all-entities `-1`. One grammar in the database allowed the
  refused shape (`SOLVER_PROXIMAL_BOUNDARIES` on 26.121) and it rendered
  a count line the solver would have followed by reading the NEXT
  commands as its data.

**Deprecations: none.**

**ONE THING THE v0.4.0 NOTES PROMISED FOR THIS RELEASE AND THIS RELEASE
DOES NOT DO.** Those notes announced the dry-run rename, breaking and
with no alias: `plan_matrix` to `dryrun_matrix`, `plan_campaign` to
`dryrun_campaign`, and `pyfs-matrix plan` to `pyfs-matrix dryrun`. It
has not landed. Nothing in the deprecation ledger held it, so no guard
noticed, and it surfaced in this release's own documentation review.

Said plainly rather than quietly carried forward, because an announced
break that does not arrive is a promise a reader planned around. The
three names are unchanged and keep working. The rename moves to the
next minor and is registered as `PLN-20260809-0200` with the ledger
entry it should have had.

**The public surface ADDED, in one place.** A new console script,
`pyfs-manual`, with the subcommands `coverage`, `draft` and `sweep`,
behind a new optional extra `[manual]` (pypdf). A new subpackage,
`pyflightstream.utils`, exporting `Edition`, `SweptCommand`,
`sweep_editions`, `read_edition_manifest`, `Coverage`, `ManualCommand`,
`ManualDraftError`, `TypeRule`, `TYPE_RULES`, `coverage_against`,
`parse_script_index`, `parse_signatures`, `propose_layout`,
`propose_type`, `read_pdf_pages`, `render_chapter`, `render_entry`,
`sample_contradiction` and `write_chapter`.

`helpers.solver_settings` gains TEN keyword parameters
(`kutta_joukowski_lift`, `print_rotor_induced_velocities`,
`adaptive_field_grid_refinement`, `jet_wake_filaments_grid_induction`,
`rotor_induced_velocity_blending`, `wake_numerical_relaxation`,
`jet_wake_decay_normalized_length`, `wake_decay_constant`,
`solver_stabilization`, `disable_ref_velocity`). `ArgSpec` gains the
fields `on_command_line`, `cites`, `all_sentinel` and `fixed_length`.
The database gains two evidence citations: `probe_ref` on an ENTRY, for
a command the solver accepts and no edition documents, and `probe_ref`
on a VERSION ROW, for a measured removal, admissible there for `removed`
alone. `qa` gains `fsm_gained`, `fsm_changed` and
`ProbeSpec.save_state`. `script.solver_setup` gains the four separation
models `AirfoilSeparation`, `AxialVortexSeparation`,
`CylindricalBulkSeparation` and `StratfordBulkSeparation`. The version
registry gains `inherits_base` and the registered version 26.101.

The stanzas below give the reasoning per chapter.

* **The tail entered: 28 commands across 21 sections, and THE SWEEP
  REACHES ZERO.** Every command that any of the four registered manual
  editions documents is now in the database: 388 entries, of which 387
  cite a manual page and one rests on a committed probe report
  (`DELETE_VALAREZO_SEPARATION_BOUNDARIES`, which the solver accepts and
  no edition names). Emittable per version at this release: 345 on
  26.100, 363 on 26.101, 363 on 26.120, 368 on 26.121.

  MEASURED ON 2026-08-08 against the four editions of the maintainer's
  own manifest: `pyfs-manual sweep` reports 0 absent. State it as a
  measurement of that date rather than as a property CI holds, because
  the manifest names licensed manual paths and cannot be committed, so
  no test in this repository can re-run it. What CI does hold is that
  every entry carries exactly one evidence citation. The sweep also now
  takes `--fail-if-absent` for a maintainer who wants the check to fail
  rather than to report.

  **Two more keyword parameters on `helpers.solver_settings`:**
  `solver_stabilization` and `disable_ref_velocity`, the latter on a new
  `bare_request` flag kind for a command that takes no argument at all,
  where False is the ABSENCE of the request rather than a way to ask for
  the opposite.

  Three commands exist in one edition only, which is the clearest
  evidence this sweep produced that the scripting surface is moving in
  both directions: `DISABLE_ACTUATOR` and `EXECUTE_SOLVER_SWEEPER` in
  the February edition alone, `DISABLE_SOLVER_REF_VELOCITY` in the
  26.121 hotfix alone. `EXECUTE_SOLVER_SWEEPER` does in one 21-parameter
  command what the later `SWEEPER_` family splits across ten, so that
  family was redesigned rather than extended.

  `CAD_CREATE_MIRROR_CURVES` HAS TWO SPELLINGS: the heading and the
  Script Index say CURVES and the sample beneath the heading says
  CURVE, in all four editions. The heading is recorded, and the
  reasoning is the reverse of this database's usual preference for
  samples: a sample is the stronger source for an ARGUMENT because the
  vendor ran the line, but a sample with the wrong NAME is a sample of
  nothing. `PLN-20260808-2300` carries the probe.

  Two chapters are worth naming for what they lack. Boundary Layer
  Transition Trips is ONE COMMAND AND IT IS A DELETE: no edition
  documents creating a trip, so a script can remove them and never add
  one. And `SET_PLOT_TYPE` prints `RESIDUALS` twice in its value list in
  every edition, so it takes 23 tokens rather than the 24 rows printed.

* **Coordinate Systems, both streamline families and the Stability and
  Control Toolbox entered: 19 commands, all four chapters complete.**
  Database 341 to 360; emittable per version 280, 307, 340, 345. Nine
  older entries across the frames and streamlines chapters get their
  missing edition rows in the same pass, the streamlines header having
  deferred the whole on-body family to the cases that would exercise it.

  `NORMALIZE_COORDINATE_SYSTEM` takes the index its sample passes,
  against a heading with no placeholder and a table reading N/A: the
  same shape as the February edition's `ENABLE_ACTUATOR` and read the
  same way. It is also the one command in its chapter that accepts frame
  1, every other requiring an index above the reference frame.

  `MIRROR_COORDINATE_SYSTEM` DUPLICATES AND THEN MIRRORS, which the
  manual states in a parameter row rather than in the command's
  description. Reading the name alone suggests the frame is mirrored in
  place, which is a different result for everything already pointing at
  it.

  `STABILITY_TOOLBOX_NEW_COEFFICIENT`'s keyword order follows its two
  printed samples, which agree with each other and not with the
  parameter table above them. That raised a question no chapter had
  asked: every keyword_block in the database fixes an order and nothing
  has tested whether the solver reads order at all
  (`PLN-20260808-2200`). `STABILITY_TOOLBOX_SETTINGS` carries a unit
  trap worth naming: its `UNITS` argument selects per-radian or
  per-degree OUTPUT, while `ANGULAR_RATE_INCREMENT` is an input the
  manual gives in rad/s regardless, so reading one as governing the
  other is a factor of about 57 in every dynamic derivative.

  Two further probes registered: what a deleted coordinate system does
  to the indices above it, which matters here because the builder TRACKS
  frames and would be wrong if the solver renumbers
  (`PLN-20260808-2100`).

* **The Advanced Settings and Inlets and Outlets chapters entered: 15
  commands, both complete.** Database 326 to 341; emittable per version
  253, 280, 321, 326.

  **Eight new keyword parameters on `helpers.solver_settings`:**
  `kutta_joukowski_lift`, `print_rotor_induced_velocities`,
  `adaptive_field_grid_refinement`, `jet_wake_filaments_grid_induction`,
  `rotor_induced_velocity_blending`, `wake_numerical_relaxation`,
  `jet_wake_decay_normalized_length` and `wake_decay_constant`, each with
  a snapshot flag. Not optional extra work: every command of a settings
  family is a snapshot flag, and the tier-1 guard refused the chapter
  until the model matched, so these arrived with the commands instead of
  a release later.

  ADVANCED SETTINGS IS THE CHAPTER WHERE THE EDITIONS DISAGREE ABOUT
  WHAT EXISTS, so its version rows differ per command. Four commands are
  absent from the February edition. `SET_WAKE_DECAY_CONSTANT` exists in
  the 26.121 hotfix alone, so it cites SRC-740 rather than the flagship,
  and its unit of 1/m is DERIVED from the manual's formula and printed
  nowhere: the constant is 19.1 over a characteristic length in metres,
  and a value computed with that length in other units gives a wake
  decaying orders of magnitude too fast or not at all, with nothing in
  the number to reveal which.

  `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` is documented by 26.101 and
  26.120 and dropped by the hotfix that follows, the only such command
  in the sweep. It entered with no 26.121 row and deliberately not a
  `removed` status, since a document going quiet is not a statement
  about a solver, and so it emitted on that build by inheritance from
  its base release. `PLN-20260808-2000` carried the probe that settled
  it, and the probe ran later the same day: the build does not have the
  command. What the row says now, and why a measured removal cites its
  run differently from a read one, is under the chapter-questions entry
  above.

  Inlets and Outlets is asymmetric and the asymmetry is the manual's: an
  inlet takes a custom velocity profile from a file and an outlet cannot,
  in any edition, so a case needing a non-uniform exhaust has no scripted
  way to ask for one. A test asserts the absence, the natural reading of
  a symmetric chapter being that the missing command was overlooked.

* **The Acoustics Toolbox and Base Regions chapters entered: 18
  commands, both complete.** Database 308 to 326; emittable per version
  243, 266, 307, 311.

  `ACOUSTIC_SOURCES` is a SETUP command in a post-processing toolbox,
  because the manual states it must be enabled before solver
  initialization; enabling it afterwards costs a whole unsteady run and
  produces no sources. `CREATE_ACOUSTIC_SECTION` creates and exports in
  one call, which is why its path names a folder: one VTK file per
  observer per time step, a count no edition warns about.

  `SET_BASE_REGION_BENDING_ANGLE` IS DOCUMENTED ON TWO PAGES AND ONLY
  ONE SAYS ANYTHING. The Base Regions chapter prints its heading with
  nothing beneath it; p.284 gives it a table, a range and a sample
  passing a value. Recorded from p.284. An empty heading is read as a
  bare command only where nothing in the manual argues with it, which is
  the rule the Scenes chapter rests on, and here the same manual argues
  with it 33 pages earlier.

  THE USER-SPECIFIED PRESSURE MODEL IS SPELLED TWO WAYS TWO COMMANDS
  APART: `USER` on `CREATE_NEW_BASE_REGION` and `CUSTOM` on
  `SET_BASE_REGION_CP`, in all four editions, both described as the
  model under which the caller's CP applies. Each entry records its own
  page and refuses the other's, because a keyword is emitted literally
  and accepting both would rest on a guess that one of the two pages is
  wrong. `PLN-20260808-1900` carries the probe.

  `SET_BASE_REGION_CP`'s CP is optional and its own page PROVES it, by
  printing a second sample that passes only the model. Its sibling makes
  the same claim about the empirical model in prose and prints no short
  sample, so there the argument stays required: a sample settling an
  arity question rather than contradicting one is rare enough in this
  manual to act on. And `REMESH_BASE_REGION` spells its growth scheme
  numerically, 1 and 2, where the three CCS chapters spell the same two
  schemes as words.

* **The Mesh Wrapper chapter entered: 11 commands, and NREQ-05 now
  excludes nothing.** The design decision of 2026-08-08. This was the
  last family the scope excluded, so the non-requirement is narrowed to
  an empty set rather than retired, the two narrowings together being
  the record of a scope decision reversing itself. Database 297 to 308;
  emittable per version 225, 248, 289, 293.

  The wrapper builds one clean watertight surface over a set of input
  surfaces, which is what a dirty import needs before a panel method can
  run on it; `WRAPPER_EXECUTE` performs it and everything else
  configures it.

  **New public field: `ArgSpec.on_command_line`.** A keyword_block whose
  LEADING arguments sit on the command's own line, which the emitter
  could not express and which `WRAPPER_EDIT_LOCAL_CONTROL` needs. The
  attempt to spell it with `joins_previous` was refused by the schema,
  correctly: that flag appends to the line the PRECEDING ARGUMENT wrote,
  and in first position there is none. Two new refusals hold the shape,
  a list cannot take it and it must lead. An excluded family hiding a
  missing emitter capability is itself an argument against excluding
  families.

  `num_surfaces` is the FOURTH spelling in the database for a count of
  surfaces, after `surface_count`, `surfaces` and `boundaries`. All four
  are the manual's own on their own pages and the entries go on
  mirroring them; the tier-1 guard over the count-name set is what
  reported this one, before the entry could ship a count nothing
  compares against its list.

* **The Scenes and Scene Settings chapters entered: 18 commands, both
  complete.** Scenes had held ONE command, `CHANGE_SCENE_TO_PLOTS`,
  drafted under a rule that only entered commands with observed
  scripted use; that rule is gone with this sweep and the entry's three
  missing edition rows are backfilled in the same pass. Database 279 to
  297; emittable per version 214, 237, 278, 282, the 26.100 and 26.101
  figures gaining nineteen rather than eighteen because the backfill
  closes one older entry as well.

  Twelve of the thirteen Scenes commands take nothing at all, eleven of
  them printed as a signature heading with no table, no sample and no
  prose. That is the manual stating the command takes nothing, and it is
  read as such here because no edition contradicts it anywhere, which is
  precisely what distinguishes it from the February edition's
  `DISABLE_ACTUATOR`, where the same empty shape sits beside a sample
  passing an index.

  Scene Settings is six keyword blocks over the colour scale, every one
  selecting its target with the same first keyword. `CUT_OFF_MODE`'s
  `OFF` is quoted in the database because YAML 1.1 reads the bare word
  as the boolean false; the schema refuses a non-string enum value, so
  the mistake is loud, and a test now pins the token.
  `SET_SCENE_COLORMAP_CUSTOM_RANGE` HAS NO SAMPLE OF ITS OWN IN ANY
  EDITION: all four print one whose first line names the neighbouring
  command while its keyword lines are this one's, so the sample is not a
  runnable call of either.

* **The CCS Fuselage Mesh and CCS Body of Revolution Mesh chapters
  entered: 20 commands, both chapters complete.** The two remaining
  parametric component definitions beside the wing, each with its own
  grid controls (subdivisions, growth scheme and rate, periodicity, and
  the per-direction reset), axial refinement zones, relaxed
  trailing-edge boundaries, and the export that writes the lofted
  component to a file. Entered from all four editions in one pass, every
  signature identical across them. Database 259 to 279; emittable per
  version 195, 218, 260, 264.

  THE TWO COMPONENTS DO NOT SHARE A SECOND DIRECTION. A fuselage is
  AXIAL and RADIAL, a body of revolution AXIAL and AZIMUTH, and the two
  chapters are otherwise line for line the same commands. That makes a
  value carried across from one to the other the easy mistake and an
  invisible one, since both words are plausible for a body of
  revolution, so the enums are stated per chapter and a test emits each
  one against the other's token.

  `EXPORT_FUSELAGE_CCS_FILE` and `EXPORT_REVOLVE_CCS_FILE` ARE RECORDED
  FROM THEIR HEADING AGAINST TWO SOURCES THAT SAY OTHERWISE. The heading
  prints six placeholders, the parameter table documents four, and the
  sample is the neighbouring create command's with the name swapped.
  The revolve page proves the copy: its sample passes a frame index, an
  axis and two angles that appear nowhere in the export's own signature.
  The wing sibling prints the same six and documents all six, so these
  tables are missing rows rather than describing a shorter command. The
  solver has not been asked, and `PLN-20260808-1730` carries the probe.

* **`pyfs-manual sweep`, and the four-edition worklist becomes a
  committed tool rather than a session's scratch script.** New public
  names in `pyflightstream.utils`: `Edition`, `SweptCommand`,
  `sweep_editions` and `read_edition_manifest`, the last renamed from
  `read_editions` before release. `coverage` answers what ONE
  manual documents and the database does not; no sweep asks that
  question. A command absent from one edition may be recorded from
  another, and a command the database lacks must be entered for every
  edition documenting it at once, so both halves need the union of the
  registered builds and neither is obtainable by reading four
  single-edition reports side by side.

  The editions come from a YAML manifest, `--editions`, which is not
  committed and cannot be: it names the paths of licensed manuals
  (invariant 1). Registering a new build is adding a row to it. `index`
  is optional, because it supplies the section label only and skipping
  an edition for want of one would silently drop a whole build from the
  union; a sweep of NO editions raises instead of reporting the entire
  database absent, which is a configuration error wearing the costume of
  a catastrophic finding. `--by-section` groups by the chapter that
  documents each command, largest first, which is the order the
  remaining work is done in.

* **The CCS Wing Mesh chapter entered: 11 commands, the chapter
  complete.** The parametric wing definition that a mesh is lofted from,
  so everything here configures a definition rather than acting on an
  existing mesh: the per-direction grid (subdivisions, growth scheme and
  rate, periodicity, and the reset), the spanwise refinement zones, the
  morphing control surface and the flap cove, and the export that writes
  a lofted wing to a file instead of into the simulation. Entered from
  all four editions in one pass under the rule below. Database 248 to
  259; per version 118, 166, 238, 242.

  `NEW_CCS_WING_FLAP_COVE` REACHED THE DATABASE ONLY BECAUSE A PAGE WAS
  READ. It carries a signature heading in every edition and no Script
  Index row at all, and the coverage sweep was index-driven, so it
  reported the command as covered and would have gone on doing so
  indefinitely. A false absent is visible the moment someone looks for
  the command; a false covered is invisible by construction. The sweep
  now walks chapter bodies (`PLN-20260808-1200`), and the two
  measurements agreeing on a total of 140 turned out to be a
  coincidence, the index-driven set carrying one false positive and
  missing one command.

  `COVE_TYPE` is an index and not a word, 1 for a blended Bezier cove
  and 2 for a rectangular one, among a family whose every other shape
  argument is a token. `U00` and `U01` are upper- and lower-surface slot
  locations, which is a different pairing from the `U0` and `U1` of the
  two control-surface commands on the same page. And the -1 that deletes
  every refinement zone or control surface is recorded in the notes
  rather than declared as `all_sentinel`: those objects belong to the
  parametric definition and not to the loaded geometry, so the builder
  tracks neither and there is no inventory for a sentinel to be read
  against.

* **The design decisions of 2026-08-08 on what this sweep owes the
  older builds, and what it does not.** A chapter now enters for every
  registered version in one pass, which is written into the
  chapter-entry guidance in `docs/srs/data-model.md`. The entries still
  documented in an edition they carry no row for, counted in the
  2026-08-07 stanza below, drain as the sweep reaches their chapters
  rather than as a task of their own, so the number falls without a
  separate push. Named rather than left to be discovered, because until
  it reaches zero a caller on 26.100 or 26.101 still meets a refusal for
  a command their own manual describes.

  Applying that rule to this commit closed ten of them at once. The
  whole Aeroelastic Coupling Toolbox carried a 26.120 row alone while
  its 26.101 and 26.121 pages had just been read here, so the rule was
  broken by the commit that introduced it; the rows are written with
  their own pages (SRC-725 pp.374-375, SRC-740 pp.378-379), the
  grammars being identical across the three editions that carry the
  chapter. 26.101 goes 145 to 155.

  Not changed, each deliberately: argument names go on mirroring each
  manual page rather than being harmonised; the count spelled
  `surfaces` stays, being the house spelling on eight commands and not a
  slip in one; the positivity bounds the manual states on the spring
  force stay unenforced; and the emitter's two argument-name maps were
  to stay beside the `cites` declaration rather than be replaced by it.
  THAT LAST DECISION WAS REVERSED THREE DAYS LATER and the maps are
  gone, which is the stanza at the top of this release; the reasoning
  that kept them, recorded here as it was taken, is what the reversal
  had to answer.

  One decision could not be carried out as taken.
  `ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS` was to have its lower bound
  enforced, and reading the page to do it showed the manual does not say
  WHICH value of 1 it forbids: the sentence sits on the count row and
  its gloss describes the reference index, the sample satisfies both
  readings, and the three editions that carry the chapter word it
  identically. Enforcing
  the wrong one would refuse a valid script, so nothing is enforced and
  `PLN-20260808-1100` carries the probe. The entry's note, which had
  stated one reading as fact, now states the ambiguity.

* **Fourth round, and the sweep itself verified clean.** An independent
  seat read all four editions page by page and confirmed the fifteen
  boundary indices: nine state an all-form, six state none, no edition
  disagrees with another. What the round found was around it.

  `Script.resolve_boundary(-1)` had started raising. It is a public
  method resolving a citation with no command attached, so the generic
  all-boundaries form is right there; it was passing through the
  per-kind default that the round before had deleted. The call site now
  states -1 explicitly, and the docstring says why that differs from
  `emit`, where six commands refuse it.

  `SURFACE_ROTATE`'s own all-form was unreachable. Its page states -1 in
  the COUNT row and the index line then has nothing to list, but the
  list was required, so the documented call was refused outright and an
  empty list emitted a stray blank line into the keyword block.

  Three of the nine declared sentinels were pinned only by a literal in
  the test inventory, which is not a guard: editing the declaration and
  the literal together left the suite green with the documented all-form
  refused. All nine are asserted behaviourally now. The
  undeclared-inventory branch was untested the same way, and every
  negative count, not only -1, was bypassing the count-versus-list
  check.

  Two claims corrected: the `all_sentinel` docstrings still taught the
  per-kind default in both homes, and the closure guard's docstring
  called the vocabulary closed when it is a heuristic over name stems,
  which a QA pass demonstrated by getting seventeen invented spellings
  past it. The stems were widened with all seventeen and the claim now
  matches what it measures. The goldens are compared for carriage
  returns directly, since `read_text` had been hiding exactly what the
  LF pin was added to prevent.

* **The same inversion, found a THIRD time, and now fixed at its root.**
  `-1` was still the all-boundaries default for every entity of that
  kind, so the six surface commands whose page states no all-form
  accepted it anyway: `SURFACE_RENAME` renamed all surfaces to one name,
  `SURFACE_MIRROR` mirrored them, and the refusal text OFFERED `-1` on
  pages that never mention it. The two earlier rounds each moved this
  rule somewhere better without asking whether the default itself was a
  claim, and it is one.

  There is no per-kind default now. Absent means the page states no
  all-form and every non-positive index is refused. SRC-003 pp.307 and
  309-313, SRC-741 p.305 and SRC-740 p.315 were read command by command:
  nine boundary indices state one and declare it, six state none and
  declare nothing. Both halves are asserted, so a rule that simply says
  yes or simply says no fails.

  The refusal wording moved with it. A command with no all-form says so
  rather than naming a value the solver was never told to accept, which
  is where the original defect did its damage.

* **The three declarations below, reviewed in turn, and the round found
  the repair less finished than it looked.** Three of its four new
  guards were untested, and the QA pass measured all three mutations
  surviving a green suite: deleting every `cites:` declaration, deleting
  the whole `fixed_length` refusal, and deleting the backfilled version
  rows. Each is now asserted as behaviour and each mutation is caught.

  `all_sentinel` was not self-sufficient. It reached the emitter only
  because a name map happened to resolve the spelling beside it, so
  renaming that map row would have made the sentinel inert and silent,
  which is the class of defect the field was added to end. It now
  requires `cites:`, and the database is refused at load without it.

  The list path still hardcoded `-1` for every entity kind, which is the
  per-family rule the change below removed from the scalar path and left
  standing next to it. A list of frames or motions has no documented
  all-form at all. Both paths now read the argument.

  The sentinel was also swallowed whenever no boundary inventory had
  been declared. An inventory bounds an index from above; being 1-based
  bounds it from below, and that half needs no inventory, so `-1` on a
  zero-sentinel command emitted silently on any script that had not
  called `declare_existing`.

  The precedence rule was written out four times, once per
  scalar-or-list branch in each of two paths; it is now
  `_reference_kind`, consulted by both.

* **A guard now closes the argument vocabulary, and it found five gaps
  the review did not.** An index argument whose name says it cites
  something must declare what it cites, be a spelling the emitter
  already resolves, be a count, or be listed as an index of an object
  the entity tracker does not model (CAD bodies, curves, sections,
  trailing edges). Running it first reported `DELETE_SURFACES`, both
  surface-section distributions, `ROTATE_COORDINATE_SYSTEM`'s second
  frame and the aeroelastic structural frame: all confirmed against the
  manual and now declared. The Mesh Operations chapter header states the
  rule, since mirroring the manual's own argument spellings is what
  makes the declaration necessary.

* **Three facts an argument used to only describe, it now declares, after
  the review of the four chapters above found each one wrong in the
  emitter.** `ArgSpec` gained `all_sentinel`, `cites` and `fixed_length`.

  The all-surfaces sentinel was fixed per ENTITY KIND at `-1`, and the
  two `TRANSLATE_SURFACE` commands document zero. So the emitter refused
  the documented `0` and accepted the meaningless `-1`, exactly
  inverted, and its refusal message steered the caller to `-1`. The
  notes said so in prose, and the test asserted the prose on the
  reasoning that "nothing can refuse it, since both are valid
  integers". That reasoning was the defect: the sentinel is a
  per-command fact, so the argument carries it.

  Which entity an index cites was inferred from the ARGUMENT NAME, and
  the Mesh Operations chapter mirrors each manual page's own spellings.
  Five of them reached neither map, so `SURFACE_DELETE` accepted a
  declared label and `SURFACE_INVERT` did not, and `SURFACE_COMBINE`'s
  index list and `TRANSLATE_SURFACE_BY_FRAME`'s two frames were range
  checked against nothing. The name map stayed at this point for a
  spelling that means one thing database-wide, and could not be extended
  to `index`, which is a surface here and a section or separation index
  in three other chapters. An argument that needs it now says what it
  cites, and the map itself was deleted later in this release.

  `SET_MOTION_6DOF_ACTIVE_VARIABLES` writes six toggle lines with no
  count before them, and a short payload made the solver read the next
  command as data. The length is declared and a short or long one is
  refused, naming the corruption rather than the arity.

  The count-spelling guard was blind in the same way and the QA pass
  proved it: renaming a real count to `surface` left the whole suite
  green while the emitter stopped comparing the count to its list. The
  exemption now reads the argument's declaration, not its name.

* **Corrected: `solver_settings(thin_boundaries="all")` was refused, and
  the refusal recommended a call that failed again.** `SET_THIN_BOUNDARIES
  -1` marks every mesh boundary thin and takes no index line; the helper
  rejected the bare label and suggested `["all"]`, which then failed as
  an unknown boundary label. The keyword now has three distinct states,
  documented together: absent leaves the solver's list alone, `"all"`
  emits the `-1` form, and the empty sequence erases.

* **Corrected: nine commands the manual documents in the February and
  May 2026 builds carried no row for them,** so the emitter refused them
  on builds whose manual describes them. Six in Motion Definitions
  (boundaries, moving frames, coordinate system, start time and the two
  rotor commands), the two FSI seam commands, and four in Solver
  Settings. This was a pre-existing gap rather than one the sweep
  introduced, and it is not the whole of it: **117 entries are still
  documented in an edition they carry no row for**, all of them 26.100
  and 26.101. Registered as `PLN-20260807-1400`; whether early-build
  parity is a v0.5.0 goal is a seat decision.

  Database 248 entries, unchanged by this pass; per version 26.100 106,
  26.101 145, 26.120 227, 26.121 231. The figures previously recorded
  here for 26.120 and 26.121 were wrong before the gap was closed, not
  because of it.

* **Solver Settings is complete.** Three commands remained:
  `SET_SURFACE_ROUGHNESS`, whose height is in NANOMETRES and not the
  metres every other length in this helper takes, and the
  `SET_THIN_BOUNDARIES` and `DELETE_THIN_BOUNDARIES` pair, absent from
  the February 2026 build. Both reach `solver_settings()` as new
  keywords, which the snapshot guard required rather than suggested:
  every command of the settings families must carry a FlagSpec or the
  provenance record silently lags the database.

  A fourth name looks absent and is not. Every edition's Script Index
  spells `CREATE_STRATFORD_BULK_SEPARATION` as
  `CREATE_STARTFORD_BULK_SEPARATION`, and the command is recorded under
  the spelling its chapter body and sample use, which RPT-015 measured
  the solver accepting. A coverage sweep driven from the index will keep
  reporting the misspelling as a gap, and a test now says so.

* **Motion Definitions is complete: 17 commands entered.** The 6DOF
  family (mass and inertia, gravity, initial conditions, active
  variables, the external, custom and spring forces, the trajectory
  export), the custom motion table, and the five kinematic commands
  that exist in the February 2026 build alone. Database 228 to 245.

  THREE COORDINATE SYSTEMS APPEAR IN THAT CHAPTER and no argument name
  distinguishes them: `SET_MOTION_GRAVITY` reads the REFERENCE system,
  the 6DOF initial conditions and forces read the BODY frame, and the
  February kinematic family reads the MOTION DEFINITION system. A
  script setting gravity and an initial velocity writes two vectors
  into two different frames, and the notes are the only place that is
  said.

  `SET_MOTION_CUSTOM_TABLE` takes its TYPE before the motion id, the
  only command in the chapter that does not open with the id.
  `CREATE_NEW_6DOF_SPRING_FORCE` is the third of the five wrapped
  signatures and declares eleven arguments, three of them lengths that
  are not interchangeable. `SET_6DOF_MOTION_SYMMETRY_LOADS` prints a
  shorter name in its sample than in its heading; the heading is
  recorded, on the measured record that a heading has won every case a
  solver has settled. The chapter header, which said the 6DOF family was
  pending, now records the chapter complete and carries the
  three-coordinate-system warning; chapter headers render live in the
  overview, so the stale text was public.

* **Corrected: `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` had one
  grammar and the manual has two.** The February 2026 edition takes two
  arguments and later editions three, the blade count arriving with the
  rotary motion, and the entry carried the three-argument form with a
  26.120 row alone. The February grammar was neither recorded nor
  reachable.

* **The Mesh Operations chapter entered: 22 commands, the whole chapter
  bar one already present.** Everything that moves, copies, cuts,
  selects or deletes a mesh surface between import and solver
  initialization. Database 206 to 228.

  Two things in that chapter are not uniform and both are recorded
  because nothing else would carry them. The all-surfaces sentinel is
  `-1` on most commands and **zero** on `TRANSLATE_SURFACE_IN_FRAME` and
  `TRANSLATE_SURFACE_BY_FRAME`, which the manual states per command and
  never contrasts, so a script reaching for `-1` out of habit translates
  surface `-1` rather than every surface. And `SURFACE_MIRROR`'s
  `MIRROR_PLANE` is an INDEX, 1 for YZ, 2 for XZ and 3 for XY, the only
  plane argument in the database that refuses the two-letter token every
  neighbouring command takes.

  Two version stories the manual tells by omission rather than
  statement. `SELECT_GEOMETRY_BY_ID` is the February spelling of
  `SURFACE_SELECT_BY_ID`, and each carries only the editions that
  document it, so emitting the wrong one for a build is refused.
  `SURFACE_DELETE` and `SURFACE_CLEARALL` are documented in three
  editions and replaced by `DELETE_SURFACES` in the fourth; neither is
  `removed`, because a removal here means a manual stating one. The
  emitter still accepts both for 26.121 through hotfix inheritance,
  which is per version and cannot be denied per command
  (PLN-20260807-1010), and a test pins that permissive behaviour so the
  fix cannot land quietly.

  `SURFACE_ROTATE`'s surface keyword is spelled `SURFACE` in its table
  and `SURFACES` in its sample. A keyword is emitted rather than
  matched, so unlike a value set this cannot accept both. Both spellings
  are printed, the table's and the sample's; the SAMPLE's is used,
  because the sample is the only runnable line on the page, and
  PLN-20260807-1000 carries the probe.

* **The CAD chapters entered the database: 42 commands across all four
  registered builds, and CAD Create is COMPLETE.** Six CAD body commands
  in `cad.yaml`, and 36 in `cad_create.yaml`: the pane settings and the
  basic shapes, the virtual curve constructors with their index and
  delete commands, the three file importers, the three cross-section
  commands that cut curves out of an existing mesh body, the curve
  transforms, and the three loft commands that turn curves into a mesh
  boundary. With `SWEEPER_SET_MACH_SWEEP` and the flow-separation
  family, the database went from 147 entries at v0.4.0 to 206. Every
  entry carries its own page per edition rather than one citation
  reused, and every command emits on all four builds.

  One command was held back at this point in the cycle: the CAD Create
  mirror, whose name the manual spells one way in its heading and
  another in the sample beneath it. IT ENTERED LATER IN THIS SAME
  RELEASE, under the heading's spelling `CAD_CREATE_MIRROR_CURVES`,
  which the Script Index agrees with; the sample's singular was then
  measured not to be a command at all (RPT-021). The stanza on the tail
  of the sweep carries it.

  Facts the argument names do not carry, which is why these were read
  one at a time rather than pattern-matched:
  `CAD_CREATE_CURVE_ARC` takes NINE coordinates whose FIRST triple is
  the arc's ORIGIN and not a vertex on it; the three curve index
  commands take -1 for every curve; `CAD_CREATE_PROJECT_CURVE` reads its
  PLANE in the frame it names and its projection VECTOR in the global
  reference frame, so a script using a local frame projects along the
  wrong direction with nothing to object;
  `CAD_CREATE_PROJECT_MULTI_CURVE`'s two indices are not
  interchangeable, the first being projected and the second a guide; and
  `CAD_CREATE_REORDER_CURVES` takes a SIGNED axis, six tokens rather
  than three, where every other axis argument in the family takes a bare
  letter. `CAD_CREATE_AUTO_CROSS_SECTIONS` and
  `CAD_CREATE_REVOLVE_MESH_FROM_CCS` each declare EIGHT arguments and a
  signature parser reports seven, because their manual headings wrap and
  the eighth placeholder sits alone on the second line; both samples pass
  eight tokens, which is what settles it. `LOFT_TYPE_U` and
  `LOFT_TYPE_V` mean chordwise and spanwise on the wing loft and radial
  and axial on the other two, so a value carried across means something
  else. And `CLOSE_ENDS` is documented as OPEN or CLOSED on all three
  lofts while all three of their printed samples pass `TRUE`: the table's
  pair and the printed token are all accepted, because refusing either
  side would refuse something the manual states. `FALSE` is NOT among
  them, and was until the review caught it: it is the value set of the
  neighbouring `MARK_TRAILING_EDGES` argument, pasted across.

  `CAD_CREATE_CURVE_EXPORT_CCS` carries phase `geometry` despite its
  name, following `EXPORT_SURFACE_MESH`: a phase is the position the
  ordering rule assigns, and filing a curve export under `export` would
  let a script emit it once and then refuse every remaining CAD Create
  command.

  Not entered at this point: the CAD Create mirror, whose name the
  manual spells two ways, the heading and the Script Index together
  against the sample. It entered later in the same release under the
  heading's spelling, and the sample's spelling was measured not to be a
  command (RPT-021).

* **The Sweeper Toolbox chapter was drafted from a worked example and
  has been redrafted from the reference pages, which changes what the
  emitter accepts.** The example at SRC-003 p.406 exercises two of the
  three sweep modes and three of the four sweep axes, so every gap
  followed from it: `UNIFORM` was missing from all three enumerations,
  `SWEEPER_SET_MACH_SWEEP` was missing entirely, and the velocity axis
  could take a file where the angle axes could take a list, an asymmetry
  the manual does not have. The reference pages give all four axes one
  parameter table, word for word.

  New command: `SWEEPER_SET_MACH_SWEEP`. New accepted mode on all four:
  `UNIFORM`, which takes start, stop and INCREMENT (the parameter table
  labels the triple STEPS, and the Mach sample passes 0.05 there, which
  no count can be). Every axis now takes the value list inline or a file
  path, whichever the caller has.

  Consequence for the caller: `script.emit("SWEEPER_SET_AOA_SWEEP",
  "UNIFORM", [-10.0, 20.0, 1.0])` used to be refused as an unknown mode
  and now emits. No script the emitter accepted before renders
  differently, but the velocity axis gained the inline value list its
  three siblings already had, so its `filename` moved from the second
  positional to the third: a positional `emit("SWEEPER_SET_VELOCITY_SWEEP",
  "CUSTOM", path)` now binds the path to `values` and is refused. Pass
  it as `filename=`. The
  curated `sweep()` helper still covers the CUSTOM subset and says so
  in its docstring, with the extension registered.

* **Eight commands became available on 26.101, and two on 26.121, that
  the database was silent about.** The whole Sweeper family gains a
  26.101 row, `AEROELASTIC_RBF_TYPE` gains 26.101 and 26.121, and
  `CREATE_NEW_MOTION` gains 26.100 and 26.101. Emitting any of them for
  those builds raised `CommandNotInVersionError` before; the manual
  documents them and now the database does.

* **`CREATE_NEW_MOTION` carries a per-version vocabulary.** The February
  2026 build names the first motion type `EUCLIDEAN` and every later
  edition names it `ROTARY`, and the two are not one capability
  relabelled: four commands that configure the February form exist in no
  later edition and two that configure the later one exist in no earlier
  edition. Emitting `ROTARY` on 26.100 is now refused with the February
  token list.

* **A refusal about a per-version grammar cites that version's page.**
  It used to cite the entry-level one, so the refusal above would have
  listed February's tokens beside a page number from the current manual.
  An error message naming the wrong page is worse than one naming none,
  because the reader goes and reads it.

* **`CAD_BODY_ROTATE` accepts the axis index as well as the letter.**
  Its parameter table names only X, Y or Z, in every edition, and the
  sample printed beneath that same table passes `2`, also in every
  edition, so the declared set refused the manual's own call. Pass the
  index as the string `"2"`.

* **`parse_signatures` reads a signature heading that WRAPS.** Five
  commands continue their placeholders onto a second line, identically
  in all four registered editions, and the parser reported every one of
  them short: `CREATE_NEW_RECTANGLE_VOLUME_SECTION` by three arguments,
  the other four by one. A short signature is the worst output this
  module has, because the draft it feeds LOADS: the schema accepts an
  entry with fewer arguments, the emitter then accepts a call with fewer
  tokens, and the solver reads the line differently with nothing between
  them to object. The rule is strict about what continues a heading, a
  line of placeholders and nothing else, so a following heading cannot
  donate its arguments to the command above it.

  No committed entry was wrong: the two affected commands already in the
  database were hand-authored from the page rather than from the parser,
  which is the argument for reading the page that this session has now
  made twice.

* **New public function `pyflightstream.utils.sample_contradiction`**,
  and `render_entry` now writes `???` for a type the manual's own sample
  refuses instead of writing the type. Drafts of commands whose
  parameter table and sample disagree no longer load.

* **New public property `CommandEntry.citation`**, the entry's evidence
  citation whichever kind it carries. A message built from `manual_ref`
  alone printed an empty pair of brackets for an entry resting on a
  probe report.

* **An inline list argument may no longer declare a separator other than
  `space`.** The inline renderer joins with a space and never consulted
  the field, so the two SWEEPER sweep commands spent a release declaring
  `comma` and rendering spaces: right by accident, and unreadable as a
  statement of the grammar. The database now refuses the declaration at
  load time rather than ignoring it. Other layouts honour the field and
  are unchanged.

* **Corrected: the registered scripting-reference page range of two
  manual editions.** SRC-003 was recorded as pp.286-371 against a
  measured pp.281-376, and SRC-740 was short by the same five pages at
  each end. The published manual-coverage page listed ten real reference
  pages as uncited and described 22 in-chapter citations as material
  beyond the reference chapter. A tier-1 guard now fails when an
  evidence citation falls outside its edition's registered range, which
  needs no pdf: both facts are committed.

* Deprecations: none.

* **New database field `probe_ref`, and the first command recorded on
  one.** Until now every entry needed a manual page, which refused a fact
  this repository holds evidence for: RPT-018 measured
  `DELETE_VALAREZO_SEPARATION_BOUNDARIES` accepted on 26.100 while the
  name SRC-741 p.339 prints for the same erase is unrecognised, and
  RPT-015 measured `CREATE_STRATFORD_BULK_SEPARATION` accepted on a build
  whose manual does not mention it. Such a command could not be recorded,
  so the user was pushed to `Script.raw()`, the one emission path with no
  validation at all.

  A committed probe report may now stand where the page would, and the
  entry says which report. Exactly one citation per entry, enforced by
  the model and by a walk over the files: neither is an assertion, both
  leaves a reader unable to say which the entry rests on. A tier-1 guard
  checks that a cited report exists AND names the command, the same rule
  the status citations carry, because a citation pasted from a sibling is
  the defect this database has already produced once.

  It does not relax the status rules. `verified` and `broken` still come
  only from a compat report applied by `pyfs-qa apply-compat` (invariant
  3); `probe_ref` records that a command EXISTS, which is a different
  claim from how it behaves.

  Consequence for the caller:
  `solver_settings(valarezo_separation_boundaries=[])` emits the erase
  again. It was REFUSED between 2026-08-05 and 2026-08-06, which was the
  right answer to a database that could not hold the working name and the
  wrong one once it could.


* **The flow-separation family is in the database, across all four
  registered builds, and `solver_settings()` emits every command of
  it.** That includes the Valarezo erase, whose working spelling is the
  one RPT-018 measured rather than the one SRC-741 prints; the helper
  refused that keyword for one day, between the probe and the
  `probe_ref` field that let the working name be recorded at all, and
  the entry above is the same change seen from the database side.
  Sixteen commands entered, the sixteenth being the probe-backed erase
  named below: the per-mechanism boundary lists of
  26.100 (axial, Valarezo criterion, cross-flow, each a SET and a
  DELETE, plus the cross-flow diameter and its axisymmetric toggle), the
  named assignment models of 26.101 and later
  (`CREATE_AIRFOIL_SEPARATION`, `CREATE_AXIAL_VORTEX_SEPARATION`,
  `DELETE_SEPARATION`), the 26.121 split of the bulk model
  (`CREATE_CYLINDRICAL_BULK_SEPARATION`,
  `CREATE_STRATFORD_BULK_SEPARATION`), and the two members documented in
  every edition and recorded in none of them,
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES` and `LAMINAR_SEPARATION`.

  Four new public models, one per assignment command:
  `AirfoilSeparation`, `AxialVortexSeparation`,
  `CylindricalBulkSeparation`, `StratfordBulkSeparation`, exported from
  `pyflightstream.script.solver_setup` beside the existing
  `BulkSeparation`. Eleven new `solver_settings()` keywords carry them
  and the 26.100 lists. Every keyword whose command belongs to ONE
  generation is version-gated: a 26.100 keyword on a 26.101, 26.120 or
  26.121 script refuses naming the command, and the reverse too.
  `laminar_separation` is the exception and is not a gap, its command
  being documented in all four editions. The database records the two
  generations on disjoint builds; RPT-018 measured part of that
  disjointness, five of the eight February commands on 26.101 and three
  on 26.121, and none of them on 26.120, which sits between two measured
  builds by inference.

  **A probe decided the names rather than a reading, and it had to.**
  The February manual documents the Valarezo pair under two spellings,
  one in a function header and one in a sample, so the RPT-012 rule
  (the header wins) had nothing to decide between. On the licensed
  February build the solver accepts `SET_VALAREZO_SEPARATION_BOUNDARIES`
  and does not recognise `SET_VALAREZO_CRITERION_BOUNDARIES`, and the
  delete is the reverse of what the manual says: the documented
  `DELETE_VALAREZO_CRITERION_BOUNDARIES` is unrecognised while an
  undocumented `DELETE_VALAREZO_SEPARATION_BOUNDARIES` works. The
  database records the documented name with the contradiction on it, and
  the working name has an entry of its own, resting on that report
  through `probe_ref`: it was unrecordable for one day, which is the
  entry above.
  Full method and results in
  `reports/RPT-018_separation-family-across-builds_2026-08-05.md`.

* **Behaviour change: `solver_settings(viscous_excluded=[])` now emits
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES`.** It used to emit
  `SET_VISCOUS_EXCLUDED_BOUNDARIES 0` followed by an empty index line,
  which asks the parser to read a line carrying nothing. The empty
  sequence is the erase for the viscous exclusion list and for two of
  the three 26.100 separation lists; omitting the keyword, or passing
  None, still leaves the list as the script found it. A caller who
  wanted the old emission was writing a malformed script.

  Three empty sequences are REFUSED rather than acted on, and the
  message says why in each case. `valarezo_separation_boundaries=[]` would emit
  the one name in this family the solver does not recognise, so it
  names `Script.raw()` and the spelling that works. An empty sequence of
  assignment models (`airfoil_separation=[]` and its three siblings)
  emits nothing, which would be a third meaning for `[]` in one
  signature and the only silent one; it names `delete_separations`,
  which is how the solver erases. And an assignment model whose own
  `boundaries` is empty would emit the count 0 followed by an empty
  index line, the malformed shape the viscous-exclusion refusal was
  written for, reached through a different keyword. That refusal covers
  `bulk_separation` too, which routed onto the shared renderer in this
  release: it had its own emission block predating the renderer and was
  the one assignment keyword the refusal did not reach.

  A single assignment model may be passed where a sequence is expected,
  since `bulk_separation` takes one and the habit crosses over; it used
  to die on `object of type CylindricalBulkSeparation has no len()`.
  `delete_separations` reads its `"all"` sentinel case-insensitively and
  refuses any other string didactically, where `"ALL"` reached a `<`
  comparison and raised a bare `TypeError`. `AxialVortexSeparation.frame`
  accepts a declared coordinate-system LABEL as well as an index, like
  every other frame citation in the library.

* **New registry field `inherits_base`, and a build that stopped
  inheriting.** A hotfix build falls back to its base release's command
  evidence, which is right for a real hotfix and was applied on the
  strength of the identifier alone: last digit not zero meant hotfix.
  The 2026-08-04 renumbering put the February 2026 build at 26.100 and
  appended the May build as 26.101, so that rule made the May release a
  hotfix of the February one. It inherited eight February-only commands,
  and `Script(version="26.101")` emitted lines that solver reports as
  deprecated and refuses.

  Inheritance is now stated per build in `commands/_meta.yaml` with the
  reason beside it, and the silent default is gone from four places
  rather than one, each closed after the previous close was measured
  incomplete by the next review round. The registry refuses to load a hotfix index that states
  nothing. **`FsVersion` refuses to be BUILT as one**, which is a
  breaking change to a public constructor: `FsVersion(canonical="26.121",
  alias="26.12", index=4)` raised nothing before and raises
  `UnknownVersionError` now, because `Script` accepts an `FsVersion` and
  the field default made the original defect reachable through the
  documented public surface. And **`resolve()` reconciles an `FsVersion`
  argument against the registry** instead of handing it back, so a
  hand-built object cannot state a wrong descent for a REGISTERED build
  either. And **the REGISTRY answers, in the layer that reads the
  fact**: `CommandEntry.evidence_in` asks the ordering authority rather
  than the object it is handed, so a caller cannot assert a descent in
  either direction, and a canonical the registry has never heard of
  inherits nothing. An unregistered `26.122` used to receive the whole
  26.120 command view while the string `"26.122"` raised for not being
  registered, so the two documented input types of one parameter
  disagreed about whether a build exists. A synthetic version still
  resolves and still sees its own direct records, which is what this
  package's own fixture registries need.

  `bulk_separation` refuses on a build whose grammar drops
  SEPARATION_TYPE, naming that build, both manual editions and the
  `Script.emit` escape. The binder's generic message named an argument
  the caller never typed and cited the 26.120 page to somebody whose
  grammar is documented at SRC-725 p.341.

  26.121 still inherits from 26.120, which is a genuine hotfix pair.

* **New subpackage `pyflightstream.utils`, and its first member
  `utils.manual`**: read a FlightStream manual and report what the
  command database does not record. Point it at a new build's manual and
  it returns the vendor's own Script Index, each command's page,
  signature and sample, and the three-way difference against the
  database (absent, recorded, recorded-but-undocumented).

  ```python
  from pyflightstream.utils import read_pdf_pages, parse_signatures, coverage_against
  ```

  **It proposes and does not write, and the reason is measured rather
  than cautious.** Checked against the 147 entries this database held
  when the tool was written, authored by hand from these same manuals
  (162 since the flow-separation family landed), it reproduces 77
  percent of their argument lists. The remaining quarter are not parser
  bugs: a variable-length list is one `int_list` argument in the database
  and N lines in the manual's sample, a keyword block has no inline
  signature at all, some commands document alternative forms in one
  sample, and the manual names arguments `value` where the database names
  them `layers`. Every layout proposal carries the sentence saying what
  it was read from, so a reviewer can disagree cheaply.

  New optional extra `[manual]` (pypdf, BSD-3-Clause, license card in
  `reports/RPT-017`). Maintainer tooling: no run path imports it, and the
  parsing half needs nothing, because it takes text. Only the pdf reader
  needs the extra.

  **New console script `pyfs-manual`**, the fifth, with two subcommands
  at this point in the cycle; `sweep` joined later and the shipped CLI
  has three.
  `coverage` reports what a build's manual documents and the database
  does not. `draft` renders entries for those commands, and **writes
  nothing unless `--write` is passed with `--out`**; without a
  destination it refuses rather than guessing where to put a draft.

  A drafted entry writes `???` wherever no rule reads a value: every
  phase whose section is unmapped, and every argument type the parameter
  table does not decide (see the entry below, which added that reading;
  before it, every type was unanswered). That
  is deliberate and it is the safety property: the database schema
  refuses `???`, so an unreviewed draft turns the suite red instead of
  quietly becoming grammar the emitter validates other people's scripts
  against. Each also carries a `drafted:` line naming the tool, the
  manual and the page, so one grep finds every machine-drafted entry.

  New public exception `utils.ManualDraftError`, in the catalog and
  keeping `ValueError` as its second base. It refuses a request to draft
  a `verified` or `broken` status: those are promoted from a committed
  probe report by `pyfs-qa apply-compat`, never from a page citation
  (invariant 3).

  **`utils.manual` now reads the manual's parameter table, which is
  where argument types live**, and proposes them: new public
  `propose_type`, and a new `ManualCommand.parameters` field carrying
  the table. Every argument used to draft as `???`, because the
  signature line and the sample block say nothing about a type.

  The rules are public DATA rather than control flow: `TYPE_RULES` and
  its element type `TypeRule`, both exported from
  `pyflightstream.utils`. The ORDER of that table is the specification,
  each row carrying a docstring and the four whose position has been
  wrong once saying why they sit where they do, and the tests pin every
  adjacent pair. Three review rounds each found one rule in
  the wrong place while the order lived in a chain of ifs, and each fix
  was invisible on a revert.

  `Coverage` and `ManualDraftError` are exported from
  `pyflightstream.utils`, which the entry above announced and the
  subpackage did not do: `Coverage` is the return type of a public
  function and could not be named to annotate a variable, and
  `ManualDraftError` was importable only from its own module.

  `read_pdf_pages` takes its page range keyword-only and refuses a range
  it cannot honour. A reversed pair read no pages and `coverage_against`
  reports an empty manual as one that documents nothing, which is a
  confident answer produced by a typo; a first page of zero indexed the
  pdf at -1 and keyed the manual's LAST page as page 0, so a drafted
  entry cited `p.0`. Reaching past the end now refuses too, naming the
  page count, which is also the cheapest sign of the wrong edition.

  `pyfs-manual draft` spells the version flag `--fs-version`, as every
  other CLI of this package does; `--version` is what a reader expects
  to print the package's own version. Every argument is checked before
  the manual is opened, so `--write` without `--out` refuses in a second
  rather than after two full pdf reads on a 400-page document, and a
  malformed page range exits 2 with the flag named instead of raising a
  raw `ValueError`.

  Measured against 148 arguments this repository typed by hand: **57
  percent agreed, 43 percent proposed nothing, none disagreed.** The
  third number is the one to hold. A rule that cannot read a type
  returns None and the draft still writes `???`, so a tranche is still a
  person's work; the failure that matters is a wrong type, because that
  one loads and then validates other people's scripts. The one
  disagreement found while measuring is pinned as a test: matching the
  toggle tokens case-insensitively read the ordinary words "enabled" and
  "disabled" out of a sentence about boundaries and proposed an enum for
  a count.

* **Breaking, and it can affect a script you already wrote:
  `resolve("26.1")` now raises `AmbiguousVersionAliasError` where it
  returned 26.100.** Two registered builds carry that vendor name since
  the February 2026 install was registered, exactly as 26.120 and 26.121
  have shared "26.12" all along. The refusal names both candidates; pass
  the canonical identifier. No deprecation cycle is possible for this:
  the name stopped being unique because the vendor shipped another build
  under it, not because this package renamed anything.

  Read the general lesson rather than only the instance: a vendor
  release name is unique only until the vendor reuses it, so a script
  that passes one is correct until it silently is not. Canonical
  identifiers are the stable input.
* **New registered version: 26.101**, the May 2026 build (vendor build
  5012026). Purely additive, and no version was dropped (CLAUDE.md
  invariant 4).
* **26.100 now names the FEBRUARY 2026 build** (vendor build 2122026,
  read from the solver's own identity line). Its 38 records did not
  disappear: they describe the May build, which was appended as 26.101,
  and they moved there with it. It began this release with no command
  evidence of its own and holds 11 entries since the flow-separation
  family landed, so its derived support level is `documented` rather
  than `registered`. It reaches `operational` later in this same
  release, at 345 emittable commands, which is the per-edition residual
  stanza above.

### Changed

* **Every committed report of a 26.1x run had its version LABEL
  corrected, and nothing else.** Eleven reports recorded runs of vendor
  build 5012026 under the name 26.100, which this repository reassigned
  on 2026-08-04 when the earlier February build took that index under
  the append-only ordering rule. The build number, the executable name,
  the date, the measurements and the outcomes are byte-identical; each
  report carries a note saying so, and each keeps its original id
  because ids are cited elsewhere. The `fs_exes` field of the drift
  reports confirms the reattribution independently: they ran
  `FlightStream.exe`, which is the executable of the install now named
  26.101.
* The `26.100` manual edition is now SRC-741 (Altair FlightStream User
  Guide, February 2026, 396 pages). SRC-725 moves to 26.101, which is
  the edition every existing SRC-725 citation was read from, so no page
  citation changed meaning.

## [0.4.0] - 2026-08-04

### API surface delta

* **Incompatible change, numerical: `farfield.plane_integral` returns
  NaN where it used to return a finite number.** This is the one entry
  in this release that changes an EXISTING result rather than refusing a
  new input, so it is stated here rather than only among the fixes.

  It inherited xarray's `skipna=True`, so an absent sample left the sum
  while its ring weight stayed in the geometry. Flux, force, torque and
  energy shrank in exact proportion to how much data was missing, with
  no warning, no flag and no non-zero status. A 0.3.0 result computed
  over a complete lattice is unaffected; one computed over an incomplete
  lattice was wrong and now says so.

  **How to tell whether your existing evidence is affected**, because
  "recompute everything" is not a triage:

  ```python
  from pyflightstream.farfield import sample_coverage

  # Same integrand you would pass to plane_integral. Returns the finite
  # fraction of the (r, psi) samples, per remaining dimension, so a
  # sweep answers per plane rather than once for the whole array.
  coverage = sample_coverage(integrand)
  bool((coverage == 1.0).all())   # True: nothing changed for this data
  ```

  Where the coverage is 1.0 the old number and the new number agree and
  no action is needed, and that half is exact. Anywhere below 1.0 the old
  number was low by the AREA-WEIGHTED share of the missing samples, which
  the coverage number bounds but does not quantify: `plane_integral`
  weights each sample by its annulus area, so a sample missing at the tip
  costs far more of the integral than one missing at the hub. Coverage
  tells you WHICH planes are affected; recompute to learn by how much.
  The NaN is not a regression, it is the first time the gap was visible. `sample_coverage` is new in this
  release for exactly this question, and it reports per plane rather
  than one number for the sweep, so one dead probe is distinguishable
  from a half-empty lattice.
* **New public names: `script.ScriptLineBreakError`,
  `farfield.sample_coverage` and `fsi.state.check_state_matches_config`,
  and `Script.comment()` renders differently.** All three names and the
  rendering change come from the blocker fixes, and they are listed here
  because this section is where a reader scans for what the surface did.

  `ScriptLineBreakError` subclasses `CommandArgumentError` and is raised
  when a text or path argument contains a line terminator, which used to
  become a line boundary and turn the text after it into the next
  command with `raw_flag` still False. `Script.comment()` now prefixes
  EVERY physical line of a multi-line comment, so a comment can no
  longer end and a command begin inside what was written as prose. If
  you passed multi-line text through a text argument and relied on it
  splitting, `Script.raw()` is the sanctioned route and still sets the
  flag.

  Seven refusals are new in the blocker fixes below, and they are not
  every refusal this release adds; the entries above carry more. A line
  terminator in a text
  argument, a non-finite scalar or list value in an FSI configuration, a
  probe lattice outside its documented domain, an out-of-domain Omega in
  a Campbell sweep, a duplicate column in a parsed table, trailing
  content after an export block, and a solver mode the package has not
  been taught. Each replaces a path that previously produced a result.
* **FR-37 closes as covered and the terminal-status set stays closed at
  six** (SRS 1.13.0). The requirement collided with FR-46, which closes
  the set at the six values `RunStatus` carries: FR-37 asked for a status
  distinct from a COMPLETED one, and a run reaching its iteration cap
  lands in `COMPLETED_MAX_ITER`. It was resolved in FR-46's favour
  and the requirement is RESTATED rather than merely declared satisfied:
  it now asks for a status distinct from the CONVERGED one, which is what
  this library guarantees. Two of the six give it, `COMPLETED_MAX_ITER`
  for a run that reached its cap and `FAILED_INCOMPLETE_OUTPUT` for one
  whose loop did not complete. Requirement text and docstrings only; no
  runtime change, and no status value was added, removed or renamed.
* **New public names: `commands.Evidence` and
  `CommandEntry.evidence_in`.** The compatibility matrix showed 76 of
  147 cells for 26.121 as though that build had been probed, and it had
  not.

  A hotfix build inherits its base release's evidence until a probe on
  the hotfix overrides it. That default is right and it is not what
  changed. What changed is that the inheritance was INVISIBLE:
  `status_in` returned the base record with nothing saying it had, so an
  inherited cell and a directly probed cell were indistinguishable, and
  each inherited cell carried a citation to a report run on the OTHER
  build.

  It mattered because a hotfix had already been measured changing a
  command: `AIR_ALTITUDE` is broken on 26.120 and verified on 26.121. So
  the inherited answer was known to be falsifiable at the moment it was
  being published as fact.

  ```python
  evidence = entry.evidence_in(resolve("26.121"))
  evidence.record      # the VersionStatus, as status_in returns
  evidence.source      # "26.120" when it came from the base release
  evidence.inherited   # True: an assumption, not a measurement
  ```

  `status_in` is unchanged in behaviour and is now implemented on top of
  `evidence_in`, so the two cannot drift. Prefer `evidence_in` wherever
  the answer reaches a person or a report.

  The published matrix marks every inherited cell and its per-version
  summary gains an **Of which inherited** column, which reads 76 for
  26.121 and 0 everywhere else. A tier-1 guard asserts that the marked
  set and the inherited set are the same set, in both directions:
  showing an assumption as a measurement and showing a measurement as
  an assumption are the same defect pointing opposite ways.

  Not changed, and measured rather than assumed: `version_support`
  counts 69 probed commands for 26.121 of which 68 were probed on that
  build, so its overstatement is one command and its level is unaffected.
* **New public name: `workspace.collection_name`.** It answers one
  question, "what name does this declared output take once collected",
  and it exists because two layers were answering it differently.

  **Behaviour change, and it moves a refusal earlier.** Three campaigns
  used to plan as `READY` and fail at collection, which is after the
  solver has run:

  ```python
  case.outputs = ["loads.txt", "loads.txt"]      # one point
  case.outputs = ["a/loads.txt", "b/loads.txt"]  # one point
  case.outputs = ["a/loads.txt", "b/loads.txt"]  # two points of one case
  ```

  Collection moves every declared output into `raw/` under its BASE
  name, so all three collide there. The plan-time check keyed on the
  declared string, where `a/loads.txt` and `b/loads.txt` differ, and it
  skipped a repeated name carrying the same point tag as itself, which
  is what let the first case through. So the cheap boundary passed what
  the expensive one refused, and the difference was paid in licensed
  solver time.

  This contradicted two statements this project publishes: the case
  model says a case whose points would render the same output name is
  blocked before it runs, and the entry below says every collision is
  refused before anything moves. Both are now true.

  A declared name with a directory part is still legitimate; it simply
  does not make two outputs differ, and the refusal says so.

* **The run matrix collects its outputs, honours its HIDDEN column, and
  says when an override overrules a row.** **Breaking**: a matrix row
  that declares no outputs is now refused. Found by running the
  reference research campaign, not by a review.

  Three defects, one theme: *the matrix states a fact, a function
  parameter states the same fact, and the parameter wins silently.*

  **Outputs, the one that lost work.** `to_campaign` never set
  `outputs`, so every matrix-driven case carried the empty default and
  the collection step had nothing to look for. With the standard
  `LoadsAssessor`, which the README and the guides tell you to pass, a
  point lands `FAILED_INCOMPLETE_OUTPUT` *after* the solver has run.
  Measured: a thirty-minute unsteady run completed, the solver wrote
  all eight expected files into the run folder, and the point was
  recorded as a failure with the files sitting beside it.

  A row declares them in `VAR_NAMES_VALUES` as
  `OUTPUTS: loads.txt, loads_cp.txt`, **comma**-separated, because the
  slash already separates the `KEY:VALUE` pairs. A row that declares
  none is refused before the solver starts, since a refusal costs
  nothing and the silent empty list cost half an hour.
  `convert_matrix` carries them into `campaign.toml`, so FR-11 stays
  lossless.

  **HIDDEN.** The column existed and was read into the `matrix_hidden`
  variable and never acted on, so a row saying `0` (show the window)
  ran headless because `run_matrix(hidden=...)` defaulted to `True`.
  The parameter now defaults to `None`, meaning the row decides; an
  explicit `True` or `False` still wins.

  **The override.** The explicit `fs_exe` override is the only way to
  run a `MANUAL` row, so it has to win, and it used to win silently
  over a row naming a real build: a row saying `FS_BUILD 26.121` ran on
  the 26.120 executable and was recorded as having requested 26.120.
  It warns now, naming the builds it overruled.

  **Why tier 1 never saw any of it.** The one end-to-end matrix test
  passed a stub assessor that returns `CONVERGED` without reading a
  file, the fixture recipe exported a literal instead of
  `case.outputs[0]`, and the stub solver wrote a fixed name regardless
  of what the script asked for. All three are corrected, and the test
  now asserts the collected files and their hashes.
* **Announced for v0.5.0, breaking, with no alias: the dry-run pair is
  renamed.** No change in this release; this notice is what makes the
  direct break available, the same way the v0.3.0 notes made this
  release's tabular renames available.

  ```python
  dryrun_matrix(...)     # was plan_matrix
  dryrun_campaign(...)   # was plan_campaign
  ```

  `plan_matrix` reads as "plan what is in the matrix" and the function
  dry-runs it: it resolves, validates, builds every script and checks
  the geometry, executing nothing. The prose has called that a
  pre-flight all along, so the divergence was already here.

  `preflight_*` was considered and rejected, because *pre-flight* is
  already the name of a different thing: the solver-identity check
  runs the solver once, lazily, to read which build is installed.
  Collapsing the two under one public name would erase exactly the
  distinction "executes or does not execute" that the rename exists
  to carry.

  `dryrun` is the verb; **`plan` stays the noun**. `CampaignPlan`,
  `PointPlan`, `PlanStatus`, `plan.json` and `write_plan` are
  unchanged, because what the action returns and writes *is* a plan.
  The old names used the noun as a verb.

  Both are renamed rather than only the matrix one: the matrix
  delegates to the campaign, so renaming one would move the asymmetry
  somewhere deeper and less visible.

  **The CLI follows**: `pyfs-matrix plan` becomes
  `pyfs-matrix dryrun`. A library function and the console subcommand
  that fronts it carrying different verbs would put one fact in two
  homes on the surface a user types.
* **Every public refusal the guard reaches now carries the package's
  base exception** (SRS FR-39, whose first clause was false in 70
  places; 24 named sites remain, see the end of this entry).
  **Widening only**: every new class keeps its standard-library base,
  so an existing `except ValueError` or `except RuntimeError` catches
  exactly what it caught before, and `except PyflightstreamError` now
  catches these too.

  FR-39 has read *implemented* since 2026-07-27 and its two guards
  inspect exception CLASSES, never a `raise` statement. An independent
  review found three public functions raising a bare `ValueError`;
  walking the tree found **70 sites across 11 modules**; widening the
  walk to the modules that declare no `__all__` found 46 more; and
  widening it again to reachability, because a bare raise inside a
  module-private helper that a public function calls reaches the caller
  exactly as an exported one does, found 21 more. Nine
  catalogued classes are added for the conditions that had no home:

  * `results.MalformedOutputError`, the sibling of
    `IncompleteOutputError` for a file that is whole and still cannot
    be read as itself (a duplicated column, a second concatenated
    export, an impossible count).
  * `results.FieldNotInExportError`, for a field name absent from an
    export's columns; `KeyError` stays as its second base.
  * `probes.ProbeGeometryError`, shared by the cylindrical lattice, the
    planar grids and the geometry gate.
  * `cases.CampaignConfigError`, for a campaign or recipe that cannot
    be used as written.
  * `farfield.FarfieldInputError`, for fields a reduction cannot
    integrate.
  * `qa.QaEvidenceError`, for a committed QA artifact that cannot be
    read as the evidence it claims.
  * `extras.UnknownExtraError`, for a name used as an extra that this
    package does not have.
  * `commands.CommandDatabaseError`, for a command database that cannot
    be read as the evidence record it claims to be.
  * `fsi.errors.FsiInputError`, for a coupling input a run cannot use.
    Written with the submodule because that is where it is reachable:
    the `fsi` package root re-exports no exception at all, and making
    this one the first is a convention decision left to v0.5 rather
    than taken here by a one-line paste. Both classes are also
    re-exported from `pyflightstream.exceptions`, as every catalogued
    class is.

  New `pyflightstream.probes.errors`, `pyflightstream.qa.errors` and
  `pyflightstream.fsi.errors` hold one shared class each, because the
  package `__init__` imports the submodules that raise them.

  A third guard walks every exported public name, and every
  module-private helper an exported one calls, for bare
  standard-library raises. It is the one that measured 70 when the
  review had reported three. **It does not make the headline
  universally true, and this note says so rather than leaving the SRS
  to say it alone**: 24 sites are exempt by name in a ratchet, three
  `TypeError` raises needing a base this catalogue does not have
  (`PLN-20260803-2340`) and the 21-site reachability tranche deferred
  to v0.5 (`PLN-20260804-0130`). The list is the debt, it is countable,
  and any site the walk reaches that is not on it fails today. SRS
  FR-39 carries the residual and the two measured limits of the walk's
  own reach.
* **The FSI and probe paths are declared experimental, behind an
  explicit boundary** (design decision, 2026-08-03; REV010-017).
  Documentation only.

  The README gains a **Capability status** table saying, per
  capability, what is supported, what is experimental, what is not
  validated, and what evidence stands behind each. Experimental means
  the interface may change without NFR-20's deprecation window and
  that the evidence is narrower than the supported rows: replaying
  archived fixtures shows the machine runs, not that its physics is
  right for a case nobody has measured. The rotary two-way coupling
  is listed as **not validated**, which `reports/RPT-007` and the
  roadmap's M6 row have said since 2026-07-21 and which no page a
  reader lands on repeated.
* **Six documentation claims corrected, and guarded** (REV010-017,
  REV010-018).

  `pyflightstream.files` was removed at v0.4.0 and three surfaces
  still described it as surviving. NFR-18 said "the manifest carries
  no version field today" while the field had been live since
  `c7cfdad`, so it now reads **implemented**. The README said the
  worked examples reach "coupled aeroelastic runs" and no example
  calls the coupling driver. The index generator documented three
  emitted fields while writing six. NFR-25's evidence line still named
  `require_extra` after the rename to `missing_extra`. And the
  role-review skill called the attestation "the mechanical proof that
  the real agents ran", which the hook implementing it explicitly
  refuses to claim about itself: the `passes` field is recorded and
  never checked, the file is local and gitignored, and any process
  that can write it clears the gate.

  New `tests/test_claim_currency.py` compares each of these claims
  with its subject, so the next drift fails tier 1 instead of waiting
  for a reader.
* **The far-field coverage metric counts what it says it counts**
  (REV010-011). **Breaking** for readers of `masked_fraction`, whose
  value changes when inputs are non-finite.

  `irreversible_deficit` masked on `radicand < 0`, and every
  comparison against NaN is False, so a NaN radicand was neither
  masked nor counted while `sqrt` returned NaN anyway. For radicands
  `[-1, NaN, 1]` two of three outputs were NaN and `masked_fraction`
  reported 1/3, overstating how much of the field the evaluation had
  honored, which is the one thing the metric exists to prevent.

  The dataset now carries `negative_radicand_fraction` (a physical
  statement about the solution: the local state is unreachable on an
  isentropic rothalpy-conserving streamline) and
  `invalid_input_fraction` (a statement about the input), with
  `masked_fraction` their non-overlapping union.
* **NFR-07 says what the implementation delivers** (REV010-013).
  Requirement text only; no code change.

  It promised inputs and invocation "reproducible from its manifest
  entry alone", while `RunRecord` stores hashes and paths rather than
  content and `reconstruct()` requires the workspace and refuses when
  the staged script is absent. The implementation was sound under a
  "manifest plus preserved artifacts" contract, which is what the code
  docstrings had said all along; the requirement now says it too. The
  entry alone identifies and verifies the artifacts by hash and states
  when one is missing or changed.
* **FSI state and loads are bound to the physical model they belong
  to** (REV010-008, REV010-009, REV010-010). **Breaking** for runs
  that were relying on any of the three.

  `FsiState` gains `config_hash`, and a resume across a different
  configuration is refused. Shape compatibility is not physical
  identity: a state saved at `stiffness_scale_factor=1` was accepted
  by a configuration with 999, because blade and station counts
  survive a change of stiffness, mass, rotational speed, offsets or
  relaxation policy. Pass `allow_config_change=True` to carry the
  memory across deliberately. The shape check still runs first, so a
  moved station keeps its specific message.

  `to_elastic_axis` now requires the sections to **cover** the
  configured blade, not merely to fit inside it. `numpy.interp`
  extrapolates constantly from the endpoints, so sections covering
  `[0.8, 1.2] m` were spread across a blade spanning `[0.25, 1.85] m`
  and the structural model received an applied load over a domain the
  evidence never measured, while the logged integral covered only the
  measured interval. The allowed margin is 5% of span at each end,
  calibrated from the committed WP1 export, whose real margins are
  2.49% and 2.31%.

  Phase 3 now requires **both** of its documented criteria before
  phase 4 begins: tip twist settled *and* integrated normal force
  stable between revolutions, the latter against the new
  `PhaseSchedule.thrust_tolerance_fraction` (default 0.02).
  `RevolutionSample.total_normal_force_n` carries the force that was
  previously computed, written to the convergence log, and never
  compared with anything. The configuration docstring had described
  this two-criterion model all along.
* **Publication is coupled to the gates, and to the exact wheel they
  tested** (REV010-016, REV010-019). Release process only; no runtime
  change.

  `publish` depended on `build` alone, so a tag could publish while CI
  was failing, and what shipped had never been exercised: CI installs
  the source in editable mode and tests that instead. The release
  workflow now builds once, records the wheel's SHA-256, installs
  **that wheel** into clean jobs on Linux and Windows at both declared
  Pythons, runs the tier-1 suite and the executable examples against
  it, runs the lint, type, coverage and docs gates, and re-checks the
  digest immediately before publishing. `publish` waits for all of it.

  Every action in all three workflows is pinned by commit digest: a tag
  is mutable and can be repointed at new code with nothing appearing in
  this repository's diff. The release build installs pinned `pip`,
  `build` and `twine` rather than whatever is current. The docs
  workflow no longer grants `pages: write` and `id-token: write` at
  workflow scope, where the dependency-installing build job also
  received them; only `deploy` asks for them.

  New `tests/test_workflow_supply_chain.py` holds all of this as
  repository guards, so a regression fails tier 1 rather than waiting
  for a reviewer to notice.
* **The development tree no longer identifies as the last release**
  (REV010-015). `pyproject.toml` and `CITATION.cff` read
  `0.4.0.dev0`; the release commit sets `0.4.0`.

  HEAD was 66 commits past `v0.3.0` and carried landed v0.4.0 breaking
  removals while every identity still said `0.3.0`, so two
  behaviorally incompatible artifacts answered to one number and no
  bug report, manifest, cached environment or citation could tell them
  apart. A wheel built from this tree now reports `0.4.0.dev0`,
  verified on the built artifact rather than on source metadata.

  New `tests/test_version_identity.py` refuses the combination that
  causes it: a **final** version and a non-empty `Unreleased`
  changelog section may not coexist. It is deliberately conditional.
  The obvious form of this check, "the version must name the current
  commit", is red on every ordinary commit because ordinary commits
  are not tagged, and a suite that is red by construction is worse
  than no suite (`PLN-20260803-1650` recorded that trap before the
  guard existed).

  Choosing the versioning **scheme**, a static development version as
  now or a VCS-derived one such as `setuptools_scm`, remains the
  reference release-time decision and is not made here.
* **A historical manifest row is no longer rewritten as current**
  (REV010-014). **Breaking**: `RunRecord.manifest_schema` is
  `str | None` with default `None`, and `reconstruct` refuses a row
  that carries no schema.

  `manifest_schema` defaulted to `MANIFEST_SCHEMA`, so reading a
  historical manifest stamped every row in it with a positive claim
  about a layout that never described it, and `append_record`
  re-serialized the validated models back to disk, persisting the
  claim: appending one run rewrote each older row with more than
  twenty defaulted fields. `None` now means "predates the field",
  which is a different fact from "asserts the current schema".

  `CampaignWorkspace.read_raw_manifest()` is new and returns the rows
  as written, with nothing defaulted; `append_record` writes through
  it, so existing rows are carried across byte for byte. Migrating a
  manifest is a separate, deliberate act rather than a side effect of
  recording the next run.

  **Correction to the record.** The commit message of `4beb710`
  (v0.4.0 development, pushed) states that this default became `None`
  in that commit. It did not: the only change that commit made to
  `workspace/__init__.py` was an `__all__` sort-order move, and the
  default was still `MANIFEST_SCHEMA` until the present change. The
  claim described work that was intended and not done. History is not
  being rewritten, so the correction is recorded here and in the plan
  ledger instead.
* **An ambiguous export is refused instead of resolved by position**
  (REV010-003, REV010-006). **Breaking** for files that were being
  silently half-read.

  `parse_probe_points` did not require unique header names, while
  `ProbePointsReport.field` returns the first tuple index of a name and
  `fields()` collapses duplicates into one key. A header rewritten from
  `Mach, Cp_ref` to `Cp_ref, Cp_ref` was accepted and
  `field("Cp_ref")[0]` returned the Mach value. The loads parser has
  refused this since PYFS-009; both call the shared
  `results.reject_duplicate_columns` now, which also compares case
  folded, so `Cp_ref` and `CP_REF` no longer count as different fields.

  Two concatenated exports were accepted as one: the software footer is
  located with a first-match search and the table helper stops at the
  first closing separator, so a second complete export was invisible
  even to the duplicate-`Total` guard that exists for this class of
  confusion. `results.reject_trailing_export` refuses a second footer
  in both parsers, because which export a file is evidence of must not
  be decided by position.
* **Non-finite values are refused at the choke points that emit and
  place geometry** (REV010-004, REV010-005, REV010-012). **Breaking**
  for code that passed NaN or an infinity into any of the three.

  `Script.emit` type checked a FLOAT and NaN *is* a float, so
  `emit("SOLVER_SET_CONVERGENCE", math.nan)` rendered
  `SOLVER_SET_CONVERGENCE nan`. `SolverSettings` guards finiteness one
  layer up; `emit` is a documented public interface that goes past it.
  Scalars and every element of a FLOAT_LIST are checked now.

  `ProbeLattice` gains `allow_inf_nan=False`, which is not redundant
  with its validator but what makes it work: every check there is an
  inequality and every inequality against NaN is False, so a NaN tip
  radius, station or ring edge passed by not being caught. The lateral
  closure cylinder gains the domain checks it never had, a positive
  radius and strictly increasing stations.

  `campbell_sweep` built each point with `model_copy(update=...)`,
  which assigns without validating, so a negative or non-finite Omega
  reached the modal solve although `FsiConfig` refuses both at
  construction. Each sweep point is validated through that same model
  now, before the first solve rather than after two of them.
* **A result is now bound to the operating point it claims**
  (REV010-001; independent review REV-010 of commit `4beb710`).
  **Breaking**: a collected export whose printed conditions disagree
  with the requested point is `FAILED_INCOMPLETE_OUTPUT` instead of
  `CONVERGED`.

  `LoadsAssessor` received the `SimCase` and never read it. A valid,
  complete, genuinely converged export printing `alpha=2 deg` was
  accepted as the evidence of a point requesting `alpha=0 deg`, and
  the manifest recorded `CONVERGED` for the wrong engineering case.
  Nothing about such a file is malformed, which is why no parser guard
  could see it. The comparison existed in the tabular layer, which the
  manifest never consults, so the status was authorized long before
  anything disagreed.

  New `pyflightstream.results.conditions` holds the comparison once:
  `bind_conditions`, `ConditionBinding`, `ConditionCheck` and the
  `FIELD_BINDINGS` table (alpha and beta in deg, free-stream velocity
  in m/s, each with a tolerance that is print resolution rather than
  an allowance for drift). Both consumers call it: the assessor before
  a status is decided, and `run_table`/`parse_run_loads` when reading
  a recorded run back.

  `Assessment.conditions` and `RunRecord.conditions` persist the
  decision on **every** outcome: axis, requested, reported, deviation,
  tolerance, unit and whether it was accepted. `None` means an
  assessor that does not compare, including every row written before
  the field existed; an empty list means the comparison ran with
  nothing to compare. A reader must be able to tell "checked and
  agreed" from "never checked".
* **An impossible count and an unrecognized solver mode are no longer
  successful outcomes** (REV010-002, REV010-007; independent review
  REV-010 of commit `4beb710`). **Breaking** for anything that fed the
  parsers malformed exports and got a number back.

  `parse_count` refused a fractional count and accepted `-1`, which is
  a perfectly whole number and not a possible iteration. It takes a
  `minimum` now, defaulting to 0 for iteration NUMBERS and passed as 1
  where the field is a requested budget, because a solve of zero
  iterations did not produce the export the number is printed in.

  The loads assessor tested for `"steady"` and let every other value
  fall through to the unsteady branch, which returns
  `COMPLETED_MAX_ITER` with no error: a mode this package has never
  seen became a successful terminal state. The vocabulary is now
  explicit as `results.SOLVER_MODES`, `results.classify_solver_mode`
  answers whether a printed mode is one of them, and an unrecognized
  one is `FAILED_INCOMPLETE_OUTPUT` before any judgment rule is
  chosen, including the residual path. The printed string stays on the
  report as evidence; only the judgment changed.

  `fsi/loads.py` kept its own `int(parse_number(...))` after the
  results parser had already centralized the exact form, so a declared
  `100.9` sections truncated to `100` and then agreed with the 100 rows
  below it. Both sites use the shared parser now. That is the review's
  own diagnosis of this repository's recurring shape: a guard added at
  one layer while the same invariant stays false at another.
* **FR-08's evidence line names a mechanism that exists** (SRS FR-08,
  reworded; new `tests/test_clean_room.py`). No runtime change.

  The requirement said clean-room provenance "is verified by the
  contribution attestation recorded per change". Measured: 200 commits,
  0 `Signed-off-by` trailers, no per-change attestation of any kind.
  The evidence line named an artifact that had never been in this
  repository.

  Every commit now carries a `Clean-room` trailer, and a tier-1 test
  asserts it for every commit since a stated baseline, with the
  declaration's text pinned so it cannot degrade to a bare "yes". The
  push gate is deliberately NOT cited as the evidence: it records that
  a review happened, says so about itself, and is silent on
  provenance, so pointing FR-08 at it would be a second overclaim
  narrower than the first.

  The limit is stated in the requirement rather than left to a reader:
  nothing can prove "the predecessor was never read". What a process
  can preserve is a declaration and an auditable record of who made it.
* **Two guides join the docs**: [Getting
  started](docs/getting-started.md), which goes from `pip install` to a
  read result with the solver appearing only at the last step, and
  [Replaying a recorded run](docs/tutorial-replay.md), which is what
  the manifest keeps, how to rebuild the exact invocation from it, how
  to tell whether the evidence still matches, and what a record cannot
  give you.

  Sybil gains its `SkipParser` on the docs tree so a page can hold an
  illustrative block that needs a licensed solver or a populated
  workspace, marked and still syntax highlighted. Every block NOT
  marked is executed, so the default stays "checked".
* **The v0.4.0 tabular renames and the keyword-only conversion have
  landed** (PLN-067; SRS NFR-20's accepted consequences). **Breaking**,
  directly, with no aliases and no warning release, exactly as the
  v0.3.0 notes announced them:

  ```python
  to_table(result)                                        # was to_dataframe
  run_table(record, *, loads=None)                        # was run_frame
  sweep_table(workspace, *, loads_file=None)              # was sweep_frame
  parse_run_loads(workspace, record, *, loads_file=None)  # name unchanged
  plan_campaign(campaign, workspace, *, recipes=None, write_plan=True)
  ```

  The word "frame" carried the pandas sense on the public surface while
  this package writes about aerodynamic reference frames in the same
  sentence. The run row's `frame` COLUMN keeps its name, and that is the
  point: once the functions stop using the word, the column means what
  it says.

  `plan_campaign` joins the same window. Its selectors become
  keyword-only, matching `run_campaign` and killing the `write_plan`
  boolean trap: `plan_campaign(campaign, workspace, None, False)` said
  nothing about which False that was.

  No deprecation cycle, per DEP-1: NFR-20's policy takes effect at 1.0,
  so nothing before it owes a warning release.
* **`pyfs-qa` speaks `--fs-version` like every other console command.**
  **Breaking**: `--version` becomes `--fs-version` on `probe` and
  `physics`, and `--versions` becomes `--fs-versions` on `drift`.

  `--version` collides with the convention where it prints the tool's
  own version, and `--versions` differed from its sibling by one letter.
  `pyfs-matrix` already used `--fs-version`, so this is the odd one out
  joining the rest rather than a new convention.
* **The requirement index says how each requirement is verified, and a
  test can now declare which requirement it falsifies** (SRS NFR-13,
  partially delivered and still pending; NFR-25 moves to implemented).
  No runtime change.

  The index published `id`, `text` and `priority`, so a consumer could
  not tell an implemented requirement from a pending one nor find what
  backs either. It now carries `status`, `evidence` and a
  `verification` method, where the distinction that matters is `test`
  (something fails when the requirement stops holding) against `review`
  (a human checks it and nothing fails). The generated
  `reports/requirements-index.json` is the home of record for that
  distribution; the four numbers are deliberately not copied here,
  because a hand-copied count beside a generated artifact is the exact
  drift this bullet is about, and it drifted within this same Unreleased
  block when NFR-18 moved from pending to implemented.

  A `requirement` pytest marker declares that a test falsifies a
  requirement. Every marker must resolve to a live identifier, and the
  covered set is a ratchet. NFR-13 stays **pending** on purpose: 96
  requirements exist and 8 are marked. Marking one on a test that does
  not actually falsify it would be worse than leaving it unmarked,
  because the index would then count a trace that is not one.
* **The package is type checked, and the worked examples run**
  (SRS NFR-27, new; NFR-01d's evidence line corrected). No runtime
  change; `mypy` joins `[dev]` and a `types` job joins CI.

  The four `examples/*.py` were in no CI step. NFR-01d's evidence line
  said they ran under Sybil, and Sybil runs docstring doctests and
  markdown code blocks: the first code a new user runs was the code
  nothing checked. A tier-1 test now runs each one and holds each to
  the extras it declares, so an example that reaches into `[fsi]`
  without saying so fails here rather than in a reader's base install.

  The type check is a **ratchet**, and the measurement is why: the
  first run reported 223 errors in 21 of 53 modules. Those 21 are
  exempted by name, the other 32 are held clean, and a newly dirty
  module fails. The exemption list is the debt, written down.
  `py.typed` is deliberately not shipped: it would tell every
  downstream checker to trust annotations that 223 errors say are not
  trustworthy, and PEP 561 is promised nowhere here, so nothing is
  broken by the absence.
* **Every optional extra refuses the same way, and every dependency
  has a license card** (SRS NFR-02; new public
  `pyflightstream.extras` with `MissingExtraError`, `EXTRAS` and
  `missing_extra`). **Breaking within 0.x** for one narrow clause: the
  `[fsi]` import gate raised a bare `ModuleNotFoundError` and now
  raises `MissingExtraError`, which is an `ImportError` but not a
  `ModuleNotFoundError`.

  Three gated paths raised three different types with three
  hand-written remedy strings, so handling "an extra is missing" meant
  knowing all three, and nothing checked that the remedy printed was
  the remedy that works. There is one type now, and its `remedy` is
  composed from the extra's own name rather than typed, so a message
  cannot name an extra that does not exist.
  `GeometryEngineMissingError` becomes a SUBCLASS rather than
  disappearing: the geometry gate is the one extra whose absence is
  recoverable, so a caller has a reason to single it out.

  The license half: `reports/RPT-016` cards the five runtime
  dependencies and `[plot]`, which had none. The runtime set is the one
  that reaches every user. `xarray` is Apache-2.0, the only non-BSD,
  non-MIT term in it, and the card states why that is accepted rather
  than leaving a reader to re-derive it. Tests now hold the coverage:
  every extra's distributions and every runtime dependency must be
  named in a committed report.
* **The SRS stops being the only judge of its own shape** (SRS
  FR-43, new and deferred; a new `tests/test_srs_consistency.py`). No
  runtime change.

  The document stated its own shape in several places, each maintained
  by hand: the chapter list's identifier range, the acceptance mapping,
  the roadmap backlog. One parser now derives the set and the tests
  assert the prose against it, so a claim about the requirement set can
  no longer be true only on the day it was written.

  It found a seventh drift instance on its first run, past the six the
  review listed: the acceptance mapping recorded an accepted item
  against `FR-43` and no such requirement had ever been written. FR-43
  is added rather than the mapping row removed, because deleting the
  row would hide an acceptance. Its band stays unnamed and the
  requirement is `deferred`: the sister library computes the imbalance
  and returns no acceptance criterion, and setting the number is the
  numerical-analyst seat.
* **A recorded run reconstructs from the manifest alone** (new
  `run.reconstruct()` and `run.Reconstruction`; `RunRecord` gains
  `manifest_schema`, `fs_exe`, `fs_exe_sha256`, `argv`, `cwd`,
  `timeout_s`, `recipe`, `recipe_sha256` and `script_path`;
  `ExecutionResult` gains `argv`, `cwd` and `timeout_s`). Additive.

  NFR-07 promised that the record plus the staged inputs reproduce the
  run. The record held 17 fields and none of them was the command line,
  the working directory, the effective timeout, the executable, or the
  identity of the recipe that built the script, so "reproduce" meant
  re-deriving all of it from executor code that may have changed since.

  `reconstruct()` returns the invocation, the script text, and a
  per-artifact verdict on whether each file still hashes to what the
  record says, with `faithful` as the summary. It refuses a record
  written under a manifest schema it does not know, and one whose
  script is gone, rather than rebuilding something that is not the run.

  `recipe_sha256` is the one that needed a decision: a recipe is user
  code resolved by a dotted name and editable between two runs that
  record the same name, so the name says which function and the hash
  says which version of it. A callable with no retrievable source
  records None, because hashing the repr would make two identical runs
  look different.
* **An unconverged twist iterate is no longer flown.** **Breaking
  within 0.x**: the FSI driver raises the new `TwistIterationError`
  where it used to write the displacements.

  `solve_rotating_static` returns its last iterate whatever happens,
  and above tolerance that iterate is not a solution: the twist was
  still moving when the solve budget ran out. The driver read
  `result.solution` and never `result.twist_residual_rad`, so those
  deflections went into `FSIDisp.txt`, the solver flew a blade shape
  the structural model never settled on, and the only trace was a
  `logger.warning` nobody reads in a batch run. The refusal sits one
  line above the write, because the write is the irreversible act.

  `RotatingSolution` gains `tolerance_rad` and a `converged` property,
  and the convergence log gains `twist_residual_rad` and
  `twist_tolerance_rad` beside the inner-solve count it already
  carried. Phase 1 leaves both cells empty rather than zero: no solve
  ran, and a zero would read as a perfectly converged iteration.
* **CI runs on Windows for the first time, and the coverage floor of
  SRS NFR-16 exists.** No public API change; both are build and
  process.

  NFR-05 has always said Windows is the primary execution target,
  because FlightStream runs on Windows, and CI ran on `ubuntu-latest`
  alone: the platform every user is on was the one platform nothing
  tested. The test job is now two platforms by the two declared Python
  bounds, four legs, with `fail-fast` off so a failure on one leg does
  not hide the others. The docs build and the repository guards moved
  to their own Linux-only jobs, because they test the repository rather
  than the package on a platform.

  NFR-16 has been pending since 2026-07-27 with its floor deliberately
  unnamed until a first measurement. Here it is, whole tier 1 suite:
  6774 statements with 515 missing, 2058 branches with 213 partial, a
  branch-mode total of **90.69%**. The floor is set below that, at 87, in
  `pyproject.toml` where the tool reads it, and it moves as a ratchet
  in a commit that explains it. The margin absorbs the difference
  between the Windows measurement and the Linux enforcement.
* **`RunRecord` records which commit of this package ran**
  (`package_commit`, `package_dirty`), from the new public
  `run.package_vcs_state()`. Additive.

  `package_version` reads the installed distribution's metadata, a
  static string, so every commit between two tags reports the earlier
  tag: measured at 28 commits and 85 files past `v0.3.0` with every
  identity still `0.3.0`. A campaign run from a development tree was
  indistinguishable, in its own manifest, from one run against the
  release. Both fields are None together for a wheel install, and None
  means "not knowable here" rather than "clean".

  The rest of that finding is a versioning-scheme change (a dev version
  carrying the sha, and a guard refusing a final version string off a
  tag). It is release mechanics and is registered, not taken here.
* **Six ways a malformed solver export produced a plausible number are
  refused.** **Breaking within 0.x** for a file with any of them; every
  one used to parse clean and return a number, which is why none was
  noticed.

  * A repeated column in the loads header. Measured: a header naming
    `CL` twice built the row with `CL` winning twice, so the report lost
    `CDi` entirely and published `CDi`'s value under `CL`.
  * A second `Total` row, and a repeated surface name. The later row
    replaced the earlier in silence, so which total the run produced
    was not determined by the file.
  * A fractional value in an iteration field. `int(parse_number(...))`
    truncated, so a printed `312.9` became `312`, and 312 is a
    perfectly ordinary count. The new `results.parse_count` refuses it
    and names the field.
  * An unrecognised token for a printed solver flag. The reading was
    `token.upper().startswith("T")`, so `yes`, `0` and `banana` all
    read as OFF with the same confidence as a real `F`. The tokens are
    now enumerated. A flag read wrongly as off is worse than an
    unreadable one, and `LoadsAssessor` now depends on this exact flag.
  * A residual-history counter that repeats or decreases. `[1, 2, 1574,
    2]` parsed clean, and that shape is two logs concatenated. The
    convergence judgment reads the LAST row, so the run would be judged
    on a residual from an earlier iteration of a different solve.
  * An interior empty cell in an FSI row. Both readers dropped empty
    cells BEFORE counting them, so `1,,2,3` passed the three-field
    check as the triple `(1, 2, 3)` with every value after the hole
    shifted one slot left. The single TRAILING separator the solver
    writes is still accepted, because that is the file format rather
    than a hole, and both cases are tested.
* **A file that was already in the simulation folder is no longer
  collected as a point's evidence.** **Breaking within 0.x**: a point
  whose declared outputs already exist when it starts is refused
  (`FAILED_INCOMPLETE_OUTPUT`) instead of running.

  Every point of a case shares one folder and collection asked only
  whether the declared output existed. Measured with a solver that
  wrote nothing at all: the point was published `CONVERGED`, its record
  named `raw/loads_a+00.0.txt` as its evidence, and that file held
  whatever had been left in the folder. Nothing distinguished the
  record from a real one. The remedy the refusal names is to archive
  the simulation or remove the leftover.
* **`RunRecord` carries a sha256 per collected output**
  (`outputs_sha256`), keyed by the same relative name as `outputs`.
  Additive; empty on manifests written before v0.4.0. Inputs have
  carried a hash since the first manifest and outputs carried a name
  and nothing else, so evidence edited, truncated or replaced after the
  run still matched its record.
* **Archiving a simulation twice refuses instead of replacing the first
  archive.** The archive name derives from the sim id, so the second
  render collides; the zip was opened truncating and the source folder
  deleted afterwards, so both copies of the earlier run were gone and
  nothing was raised. The operation that exists to preserve a run was
  the one that lost it. The refusal names the remedy: move the existing
  archive, or give the workspace an archive template that
  distinguishes the runs.
* **A run that forced all its iterations is no longer called CONVERGED
  for stopping early.** **Breaking within 0.x**: with
  `SOLVER_SET_FORCED_ITERATIONS` enabled, no declared solver log, and
  an iteration counter below the requested budget, `LoadsAssessor` now
  returns `FAILED_INCOMPLETE_OUTPUT` where it returned `CONVERGED`.

  The no-log judgment infers convergence from an early stop, and that
  inference holds only while the convergence threshold is what can stop
  the solver. Forcing all iterations turns the threshold off, so an
  early stop means the opposite. `LoadsReport.forced_iterations` was
  parsed and never consulted, so a run that stopped at 312 of a forced
  500 was published converged, indistinguishable in the manifest from
  one that genuinely met the threshold at 312.

  Narrow on purpose, and the three unchanged cases are tested as
  controls: an unforced early stop is still `CONVERGED`, a forced run
  that reaches its budget is still `COMPLETED_MAX_ITER`, and a footer
  that does not print the line at all still gets the count judgment,
  because not knowing is not the same as knowing it was forced.

  The status is a constrained choice rather than the right name for it,
  and the assessor's docstring says so: the terminal set is closed at
  six (SRS FR-46), and it was resolved on 2026-08-03 that it stays
  closed. FR-37 is restated
  to ask for a status distinct from the CONVERGED one, which is what the
  library guarantees, and closes as covered (SRS 1.13.0).
* **"Supported" was one word covering four states, and is now four
  named values** (SRS FR-49, new). New public names at the top of the
  package: `SupportLevel`, `support_table()`, `version_support()`,
  `support_level()`, plus the `pyflightstream.support` module with
  `minimal_workflow()`, the `VersionSupport` record those functions
  return, and the two data members a caller reads rather than
  reconstructs, `SUPPORT_LADDER` and `MINIMAL_WORKFLOW_COMMANDS`.
  Purely additive.

  ```python
  >>> import pyflightstream
  >>> pyflightstream.support_level("26.000")
  <SupportLevel.REGISTERED: 'registered'>
  ```

  Registering a version made every public surface call it supported.
  26.000 is registered, is accepted by `Script(version="26.000")` and
  by a campaign, and carries evidence for zero of the database's
  commands, so nothing whatever can be built for it. The README said so
  in a sentence; nothing said it in a value a caller could read.

  The levels ascend `registered`, `documented`, `verified`,
  `operational`, and every one is derived from the command database
  rather than declared in a file, for the same reason a command status
  is: a hand-set level outlives the fact behind it. Today that reads
  26.000 registered, 26.100 documented, 26.120 and 26.121 operational.

  `operational` is the level that claims a user can get from geometry
  to a loads file, and its claim is checked by performing it:
  `minimal_workflow(version)` builds the shortest complete script, and
  a tier 1 test builds it for every version reported operational. The
  README's version table is pinned to the derived values by a test, so
  the published claim and the computed fact cannot drift.
* **A command a probe measured broken is refused at emission, and the
  way through is recorded** (SRS FR-48, new). **Breaking within 0.x**:
  a recipe that emitted `AIR_ALTITUDE`, `NEW_OFF_BODY_STREAMLINE`,
  `SET_MOTION_START_TIME` or `SWEEPER_REF_VELOCITY_SAME` against a
  version whose record is `broken` now raises `BrokenCommandError`
  where it used to build a script.

  `broken` is the one status backed by a probe that WATCHED the command
  fail, and it was the one status the emitter did not act on. The
  consequence is not a crash. An absent command produces no run at all;
  a broken one produces a complete run with wrong numbers in it. On
  26.120 the solver reads AIR_ALTITUDE's METERS argument as feet
  (`reports/compat/CMP-26120_2026-07-23_pln012.yaml`), so
  `atmosphere(script, altitude=1000.0)` would have asked for 1000 in
  whatever unit the solver defaulted to, and written a manifest
  calling the script fully validated. The measurement is at one
  altitude only: at 5000 the default read as feet.

  ```python
  script.allow_broken("AIR_ALTITUDE", reason="reproducing a 2026-07 run")
  helpers.atmosphere(script, altitude=1000.0)
  ```

  The waiver emits the command and records it through the new exported
  type `script.BrokenCommandUse`, one instance per waived command:
  `script.broken_commands`
  and the new `broken_commands` field of `RunRecord` carry the command,
  TWO versions, the committed report, the recorded observation, the
  justification and the script line the first waived emission rendered.
  The two versions are `version`, the build the script targeted, and
  `source_version`, the build whose record is broken and therefore the
  build the cited report was run on; they differ exactly when a hotfix
  inherits its base release's record, and reading either as the other is
  the defect this release is named for.

  The same promise `raw_flag` makes for unvalidated
  text, for a case that is worse, because a raw line at least looks
  unusual. `reason` is required; it is the only field nothing
  automated can supply.

  Registered on the script rather than passed per call, so it reaches
  the curated helpers without every helper growing an argument, and a
  waiver for a command that is not broken in the target version is
  accepted and records nothing: AIR_ALTITUDE is broken in 26.120 and
  verified in 26.121, and one recipe is meant to run against both.

  Two of this repository's own goldens were pinning the mistake and
  were corrected in the same change, which is the part worth reading
  before dismissing this as defensive: the actuator polar golden pinned
  `altitude=1000.0` on 26.120, and the rotor unsteady golden pinned
  `SET_MOTION_START_TIME`, at which the solver ABORTS script
  processing, so everything after it never ran. The altitude rendering
  is still pinned, on 26.121, where the command is recorded verified.
  Not "where the hotfix fixed it": RPT-014 refuses that attribution in
  its own words, because three variables separate the two runs (the
  build, the harness and the session file) and the disambiguating
  probe has not been made.
* **A truncated evidence note now says that it is truncated.** The
  `note` a compat promotion writes into the command database is capped
  at one line, and the cap used to cut mid-word with nothing to show
  for it: AIR_ALTITUDE's read "reports the 5000 m standa", losing the
  measured diagnosis that followed. The cut is now made at a word
  boundary and marked `[...]`, because that note is what the new
  `BrokenCommandError` shows the caller, and a refusal that looks like
  a corrupt database is a refusal that gets worked around.

* **Research geometry can no longer enter the repository unnoticed**
  (SRS NFR-14, which was pending). A tier-1 guard walks every tracked
  path and fails on any geometry or mesh extension outside a small
  allowlist of provably synthetic fixtures, and a `forbid-geometry`
  pre-commit hook refuses the same class at commit time.

  This closes the one breach this project calls irreversible: a push
  publishes, and deleting the file afterwards does not unpublish it from
  any clone that already fetched. It was enforced by discipline alone
  until now, and discipline was measured to be all there was: a 37 kB
  mesh added under `examples/` and staged passed the entire tier-1 suite
  and the CI guard job, which looks only for pdf, notebook and
  `_private/` paths.

  The suffix set is derived rather than invented: `IMPORT`'s
  `file_type` enum in the command database, plus the saved simulation
  `.fsm`, plus the CAD interchange formats research geometry arrives in.
  Stated as a residual rather than hidden: the guard keys on extension,
  so geometry carried in a generic container (a node list in a `.csv`)
  is outside it, and NFR-08 stays a discipline for that.
* **`PyflightstreamError` is the package base exception, and every
  CATALOGUED exception descends from it** (SRS FR-39, which was pending
  on exactly this clause). Read that word before relying on the
  sentence: a residual of bare standard-library raises survives. Every
  site the guard's walk reaches is named in the ratchet in
  `tests/test_exceptions_catalog.py`, which is the single home of that
  list; SRS FR-39 states the walk's reach and the count, and at least
  one site sits outside the walk. One except clause
  catches the catalog:

  ```python
  from pyflightstream.exceptions import PyflightstreamError
  ```

  Purely additive, and deliberately so: every type keeps the
  standard-library base it already had as a second base, so
  `UnknownVersionError` is still a `ValueError`, `WorkspaceError` still
  a `RuntimeError`, `OptionError` still a `KeyError`. No `except` clause
  that worked before stops working, and a table in
  `tests/test_exceptions_catalog.py` pins each of those builtin bases so
  a later edit cannot quietly move one.

  The base parents the exceptions and not `VersionMismatchWarning`,
  which is a warning: it stays in the catalog, because the catalog
  covers exceptions and warnings alike, and it stays out of the
  hierarchy, because calling it an `Error` would mislead whoever reads
  the traceback. Two separate guards now run: one fails when a class
  does not join the catalog, one fails when it joins the catalog
  without joining the hierarchy.

  Why it lands before any renaming: a name is the dispatch key only
  while there is no base to catch. With the base in place, renaming a
  leaf stops costing a deprecation cycle, so the naming questions the
  API vocabulary review raised get answered later and more cheaply.
  The cause-versus-rule split in the current names is therefore left
  open on purpose, not overlooked.
* House conventions gain two entries, in the same `CONVENTIONS` home
  that feeds `help()` and the docs site: **diagnostics are nouns and
  validators say `check_`** (`sample_coverage` beside `check_recipe`),
  and **a validator takes the values it compares where the object would
  reverse the dependency direction**. The second is a layering rule
  wearing a naming hat: `check_state_matches_config` takes two integer
  counts rather than the config object, so `fsi.state` keeps its import
  surface to pydantic, and those counts are keyword-only because
  same-typed scalars transpose silently. Both halves that can be checked
  mechanically now are: a `check_` function returning a value fails the
  suite, and so does `fsi.state` importing `fsi.config`.
* **FlightStream 26.121 is registered, and the vendor name "26.12" stops
  resolving.** The vendor ships the hotfix build under the same release
  name as 26.120, so that name now identifies two registered builds.
  `versions.resolve` refuses it with the new
  `AmbiguousVersionAliasError` (catalogued, carrying `alias` and
  `candidates`) naming both candidates, instead of returning one of
  them. Every caller that passed the vendor name must pass a canonical
  identifier: `Script(version="26.120")`, `--fs-version 26.120`,
  `fs_version = "26.120"`.

  Incompatible by intent, and the alternative was worse: `resolve`
  matched canonical-or-alias and returned the first hit in release
  order, so once 26.121 was registered the vendor name would have
  handed back the pre-hotfix solver silently. A caller who wrote the
  vendor name meaning "the current 26.12" would have got the build
  before the hotfix, with no error anywhere. The refusal is loud; the
  old behaviour was not.

  Resolution also matches canonical identifiers across the whole
  registry before considering any alias, so an entry can no longer be
  shadowed by an earlier one carrying its canonical as an alias.
  Registered versions are now 26.000, 26.100, 26.120, 26.121; the last
  digit indexes vendor hotfix builds, so 26.121 is hotfix build 1 of
  the 26.12 release (SRS FR-02c, new).
* **A campaign pointed at the wrong FlightStream installation now stops
  before its first point**, not after its last. `run.check_solver_identity`
  is new and public: it runs the cheapest possible script (a sentinel, a
  log export, and close), reads the build number out of the exported
  log, and refuses when it is not the build the campaign's version
  declares. `run_campaign` calls it once, lazily, just before the first
  point that will really execute, so a resume with nothing pending still
  spends no solver process, and takes `preflight=False` to skip it.

  Layered rather than sole. A mismatch is refused there on positive
  evidence; an identity the check cannot read warns and falls through to
  the parse-time comparison below, because refusing on an unreadable log
  would make the guard's own failure mode "no campaign runs at all".
  Nothing is checked, and no solver process spent, for a version with no
  registered build.
* **A run can now tell which solver build actually produced it.** The
  registry records each version's vendor build number (`FsVersion.build`,
  new, read from `commands/_meta.yaml`), and parsing a loads or probe
  export compares it against the build the output printed, warning when
  they differ.

  This is the run-time half of the alias refusal above, and without it
  that refusal was only half a guard: it settled which build the run
  ASKED for and could not show which one ran. The version string cannot
  show it either, because 26.120 and 26.121 both print "26.1" and they
  carry different records, `AIR_ALTITUDE` being the measured case. So a user
  who took the refusal seriously, moved to 26.121 and left `fs_exe`
  pointing at the 26.120 install got no warning at all, on exactly the
  command whose units defect that build carries.

  Build numbers are evidence, not configuration: each is taken from a
  committed report's `solver_identity` for its own version, and a
  tier-1 guard fails if a registered build appears in no such report.
  26.000 has none registered, because no committed report records one;
  there the version-string check remains, unchanged.
* `pyfs-qa probe`, `physics` and `drift` now refuse an unresolvable
  `--fs-version` (`--fs-versions` on `drift`) with the library's own message on stderr and exit code 2,
  instead of a traceback. Both refusals it covers are ordinary user
  error: an unregistered identifier, and a vendor name shared by several
  builds. A wrapper keying on the exit code sees 2 where it used to see
  1.
* **The 26.121 manual edition is registered as SRC-740**, a separate
  source rather than a re-issue of SRC-003, and the edition entry says
  why: its scripting reference is shifted by three pages throughout, so
  an SRC-003 page number does not address the same page in it.

  Two of the commands it documents join the database with a 26.121
  status only, so a 26.120 script still refuses them:
  `DELETE_SURFACES` (p.315) and `NEW_UNSTEADY_SOLVER_SURFACE_PROBE`
  (p.350), the latter being where the six boundary-layer parameters
  enter the unsteady vocabulary. `UNSTEADY_SOLVER_NEW_FLUID_PLOT` gains
  a 26.121 grammar override for the same six values SRC-740 adds to its
  `PARAMETER` enum.

  `DELETE_SURFACES` is registered narrow, with the single index its
  parameter table declares, because one of its samples passes three
  bare integers under a multiple-surface heading and the two readings
  delete different surfaces.

  The other four are **not** landed, and the reason is worth stating:
  they belong to the settings families, where a command is not
  registered by a database entry alone. A tier-1 guard requires every
  such command to carry a snapshot flag and a keyword on the public
  `solver_settings()` helper, because a solver setting the snapshot
  does not know is a run whose manifest describes the solver state
  incompletely. They are backed out rather than shipped half-wired.
* `UNSTEADY_SOLVER_DELETE_ALL_PLOTS` joins the command database
  (`documented`, SRC-003 p.347). It was documented in the 26.12 manual
  and never registered; the gap surfaced while diffing the 26.121
  manual against the database.
* Solver toggles read the solver's own vocabulary as well as Python
  booleans: `ENABLE` and `DISABLE` (any case) are accepted by every
  helper argument and every `cases.SolverSettings` field that switches a
  flag, resolved before the helper emits anything, and stored and
  snapshotted as bools. New public module
  `pyflightstream.script.toggles` (`resolve_toggle`,
  `SOLVER_TOGGLE_WORDS`, the `Toggle` annotation), used by both the
  helpers and the case models so the vocabulary has one home, plus
  `cases.SolverToggle`, the annotated field type any settings model can
  reuse.
* `LoadsAssessor()` now takes no argument by default and reads the
  case's first declared output as the loop rendered it for that point,
  which is what a swept case needs; naming the file explicitly still
  works.
* Incompatible changes: a toggle value in neither vocabulary is refused
  where a truthy string used to pass silently (a helper call passing
  `'yes'`, and a settings file or preset whose flag reads `"true"`,
  `"on"`, `"1"` or `0`, which pydantic's lax bool parsing used to
  accept); a multi-point case whose declared output names lack the
  `{point}` placeholder is refused, because those points would
  overwrite each other's evidence; and a recipe reference whose
  callable does not take `(case, script)` is refused at resolution
  instead of raising a bare `TypeError` once per point.
* `solver_settings(vorticity_drag_boundaries=...)` is optional again
  (a relaxation, so no caller breaks). Omitted on a script that has not
  selected yet, it emits no selection command and the snapshot records
  the flag as `default` with an empty selection and its citation, or as
  `unknown` on a FlightStream version where the command has no recorded
  evidence; omitted on a second settings call of the same script, the
  selection of the earlier call stands, in the script and in the
  snapshot. An empty sequence is refused.

### Removed

* **`pyflightstream.files` and `pyflightstream.cases.matrix_legacy` are
  gone**, on the horizon their own deprecation-ledger entries recorded:
  `removal_version="0.4.0"`, set when they were introduced in v0.3.0.
  Import `pyflightstream.workspace` and `pyflightstream.cases.matrix`
  instead; `LegacyMatrixError` was already `MatrixError` and `LegacyRow`
  already `MatrixRow` through the shim, so only the module path moves.

  Kept rather than extended because NFR-20 says a promise already
  recorded is kept regardless of version, and because the deadline guard
  would otherwise have turned the suite red at the release commit's
  version bump, which is the worst moment to discover a removal window.
  The deprecation ledger is now empty and the machinery stays: the
  policy binds from 1.0 and the next shim registers there.

### Added

* **The user guide is refreshed for 26.121, and a guard now keeps it
  current.** Six claims went stale when the 26.121 onboarding landed
  and nothing caught any of them: the guide is neither built nor
  executed by CI, so every claim in it was true only until the next
  licensed session moved the evidence underneath it.

  Corrected: the version diagram, which drew three nodes ending at
  26.120 beside a listing that printed four; the pinned refusal
  transcript, which listed two recorded versions where the library
  prints three; AIR_ALTITUDE, which the guide called broken without
  saying on which build, when in fact the vendor hotfix fixes it and the
  probe on 26.121 promoted it to verified; SET_MOTION_START_TIME, which
  said "await re-probe" after the re-probe had run and found the same
  abort; and the pitfall table, which now names the builds each finding
  applies to and gained the SWEEPER_REF_VELOCITY_SAME row it was
  missing.

  The AIR_ALTITUDE entry is the one with user consequence, so it now
  carries the number: on 26.120, 5000 METERS produced 1.056 kg/m^3, the
  5000 ft standard state, where 0.736 is correct. A density 43 percent
  high with no error, and the hotfix digit in the version identifier is
  what lets the database say the two builds disagree.

  The counts are gone rather than corrected (design decision,
  2026-08-03). "144 commands" was wrong by three, and the plan item
  recording that it was wrong was itself wrong by two the day after it
  was written. The compatibility matrix generates the current numbers on
  every docs build, and the guide points at it.

  `tests/test_guide_currency.py` is the guard, and it is a different
  failure class from `test_guide_api_names.py`: that one checks the
  names the guide teaches, this one the facts it states. No
  hand-written command count, the curated-helper count equal to what the
  module defines, every registered version mentioned, every pinned
  transcript equal to what the library prints, every pitfall row naming
  the builds the database calls broken, and every broken command having
  a row at all. That last one closes the hole the others leave: a
  missing row is invisible to a check that reads the rows present, and a
  missing row is what happened. Six mutants, one per original stale
  claim, all caught.
* **A tracked file may no longer name the workspace container's
  absolute path.** CLAUDE.md has always said machine configuration is
  never a literal path in a committed file; a tier-1 guard now holds
  it, alongside the email-address and user-profile-path checks that
  landed on 2026-07-28.

  Not an absolute-path shape, which was measured to be the wrong guard:
  32 tracked files match one and 30 of them are illustrative solver
  paths in examples, goldens and fixtures (`C:/cases/wing.fsm`). The
  guard keys on the container directory's name, which is what separates
  a path that teaches from a path that leaks, and is the same on any
  clone. The two files that carry it today are hash-pinned vendored kit
  bodies this repository cannot edit, so they are allowlisted by name
  with their kit rows, the allowlist itself is checked for stale
  entries, and the fix is routed to the level that owns those bodies.
* **FlightStream 26.121 is onboarded with solver evidence, not just
  registration**: `reports/compat/CMP-26121_2026-08-02_full.yaml` is a
  licensed tier-2 run of 109 probe specifications against solver build
  #7262026, and 68 statuses are promoted from it.

  One command changed for the better: `AIR_ALTITUDE` was `broken` on
  26.120 because its `METERS` argument read as ignored (5000 m gave the
  5000 *foot* standard density, 1.056 kg/m^3, observed twice on the
  pre-hotfix build); on 26.121 the same assertion observes
  0.736 kg/m^3, the 5000 m value. Anyone setting altitude in metres on
  26.120 was solving at the wrong density, silently, and that half
  stands on the 26.120 evidence alone.

  One changed the other way: `SWEEPER_REF_VELOCITY_SAME` ran without a
  script abort on 26.120 and aborts on 26.121.
  `NEW_OFF_BODY_STREAMLINE` and `SET_MOTION_START_TIME` are broken on
  both builds.

  Attribution is deliberately withheld, because three things differ
  between the two runs and not one: the solver build, the probe harness
  (0.0.1.dev0 to 0.3.0, with the specifications changing inside that
  window), and the session file. The run establishes what was observed
  on each build, not what the vendor changed. The disambiguating run,
  this harness against the 26.120 executable, was not made.
* `reports/RPT-015_bulk-separation-family-acceptance_2026-08-02.md`:
  the bulk-separation family probed on both builds, because RPT-014's
  rename checklist held one item that was a physics question rather than
  a naming one. It turned out to rest on a false premise and is
  withdrawn rather than answered.
  `CREATE_STRATFORD_BULK_SEPARATION` is **not new in 26.121**: the
  26.120 solver accepts it too, where no manual documents it, so the new
  edition documented an existing command rather than introducing one.
  And `CREATE_BULK_SEPARATION`, which the database records as
  `documented` for 26.120, is **refused by the 26.120 solver in every
  documented form**, including the three-argument one RPT-012 ran
  successfully on 26.100. No status moves on this report: it came from
  an ad-hoc probe rather than the harness, so `apply-compat` cannot read
  it, and a status promoted outside that path is what invariant 3
  forbids. Registered instead.
* `reports/RPT-014_26121-manual-diff-and-probe_2026-08-02.md`: the
  26.121 onboarding record. It documents that the hotfix carries its own
  manual edition (413 pages against 410, every scripting-reference
  citation shifted by +3) while the vendor release-notes PDF is
  byte-identical between the two installs and documents none of it; the
  six commands the new edition adds and the three it drops; two
  signature changes on commands already in the database; four defects in
  the vendor's own document; and the human decision checklist for three
  suspected renames, one of which (`FLAT_PLATE` bulk separation to
  Stratford) is a physics question and not a naming one.
* User guide section on migrating a loose script builder to the
  `ScriptRecipe` protocol: the before and after of
  `build(workdir) -> Script` becoming `build(case, script) -> None`,
  with the five moves it takes (do not create the Script, open
  `case.geometry` so the run identity is the staged file, read the
  point from the case, export the rendered `case.outputs` names, and
  give the function an importable address). This is the path of
  everyone arriving from a driver script, and it was documented
  nowhere (feedback channel item 4, PLN-074).
* House conventions gain "Toggles read both vocabularies", rendered in
  `help()` and on the docs site from the same `CONVENTIONS` home.
* House conventions page on the docs site
  (`reference.conventions_markdown`, the same source as the offline
  `help()` conventions section), wired into the generator and nav.
* Automated PyPI release through trusted publishing (OIDC):
  `.github/workflows/release.yml` builds, checks the tag against the
  `pyproject.toml` version, and publishes from the GitHub `pypi`
  environment on a `v*` tag, so no API token is stored in the
  repository (mirrors the ITACA release workflow). Development process:
  a mandatory role-review push/release gate now blocks a `git push`
  until the specialist reviewer agents have run and attested every
  commit the push would make new, plus the ref being pushed, and denies
  any push while the incident ledger shared with ITACA has an open
  blocking incident for this repository; a new `incident-analyst`
  charter owns the structural-cause analysis, and `tests/test_push_gate.py`
  pins the gate's decisions (`.claude/` hooks, agents and skills;
  internal tooling, not a package surface).
* Development process: the session documents (state file, handoffs,
  logbook, inbox, progress reports) moved out of the repository-local
  private tree into the coordination hub, where they gain version
  control, and are located by a new `PYFS_SESSION_ROOT` environment
  variable read by the `handoff`, `plan`, `audit` and
  `derive-requirements` skills. Unlike the two existing
  machine-configuration variables it is documented as stop-on-unset
  rather than skip-on-unset, because a session that cannot find its
  state file would otherwise close by writing its record nowhere. The
  plan ledger and the design documents deliberately did NOT move: a
  repository's own plan and architecture are its own facts. Two new
  tier-1 guards came with it, `tests/test_env_contract.py` (the
  documented variables and their consumers agree, and no skill prints
  the bash-form variable as a path, which in PowerShell expands to
  nothing silently) and a house-style check that no committed file
  re-hardcodes a migrated session path; `tests/test_plan_checker.py`
  now also pins the plan checker's exit taxonomy, seven tests over the
  six documented outcomes plus the usage branch that shares an exit code
  with one of them, including two weaknesses recorded rather than hidden
  (an empty ledger directory exits zero, and a DELETED exemption list
  stays silent while every legacy id fails at once) (`.claude/` skills
  and `CLAUDE.md`; internal tooling, not a package surface).
* Documentation and process: the shared process kit is re-vendored from
  0.2.2 to 0.2.3 for the plan checker and its mutation companion, a
  promotion this repository's own adoption review produced and then ran
  three days behind. The hardening it brings is that a `legacy_ids.txt`
  which exists but cannot be read is now a named `CONFIG ERROR` at exit
  2 before validation, instead of being swallowed into an empty
  exemption set and reported as 88 ledger defects pointing at the one
  fix the plan rules forbid. Also recorded, because the drift test's
  green is easy to over-read: that test detects a hand-edit and cannot
  detect falling behind, which is why the lag was invisible. The drift
  test also gained pins on the two provenance-header fields that sit
  outside the body hash and that no assertion previously reached: the
  `note:` target of each vendored copy, and the `canonical-source:`
  line, which is where a copy records that its body was built for the
  kit rather than adapted from the AGPL predecessor (`.claude/tools/`,
  `tests/test_kit_drift.py`; internal tooling, not a package surface).
* Documentation and process: the push gate is re-vendored from the kit at
  0.2.16, alone, to close a FAIL-OPEN it carried at 0.2.4
  (`INC-20260802-1450-shared`). `_strip_heredocs` removes heredoc bodies
  before tokenizing so a commit message that merely describes a push is
  not misread as one; its opener pattern matched anywhere in a line,
  including inside a quoted commit message, and when no matching
  delimiter ever arrived it dropped every remaining line. A real push on
  the next line went with them, and the gate returned without requiring
  an attestation, reading the ledger, or checking for a release tag. Not
  a weaker refusal: no refusal, reachable in two lines of ordinary shell
  with no heredoc anywhere in them. Measured here against the deployed
  0.2.4 body before it was replaced: three reduced reproductions each
  produced no decision at all while a bare unattested push denied; on the
  0.2.16 body all four deny, and neither pinned heredoc behaviour moved.
  The cases are now permanent in `tests/test_push_gate.py` and were
  proven by mutation, failing on the 0.2.4 body restored from git.
  TWO THINGS RIDE THIS VENDOR that are not the heredoc fix, both from kit
  0.2.8, and both change behaviour. The incident-ledger variable the gate
  reads is renamed from `PYFS_INCIDENT_LEDGER` to
  `COORD_INCIDENT_LEDGER`, retiring the last per-repo difference between
  a vendored body and its master; `PYFS_INCIDENT_LEDGER` stays live for
  the `incident-analyst` agent, whose charter is a hash-pinned body on a
  kit row NOT taken here, so a clone now sets both to the same directory.
  And an unset variable now DENIES a push where it used to mean the check
  did not apply, which sounds like a courtesy to a fork and was measured
  to be something else: the level that writes the incidents pushed past a
  blocking incident of its own authorship, on a variable name that had
  never existed. Order matters on a fresh clone and is the reverse of the
  obvious one: export the variable BEFORE this body is in place, since a
  PreToolUse hook without its configuration denies every command. The
  rest of the kit is deliberately NOT adopted; see below (`.claude/`,
  `CLAUDE.md`, `tests/`; internal tooling, not a package surface).
* Measured and NOT adopted, recorded so the gap is a decision rather than
  a discovery: against kit master 0.2.17 on 2026-08-02, six of the nine
  kit artifacts this repository vendors are behind their masters and the
  kit manifest carries 25 further rows never vendored here, an adoption
  surface of 31 artifacts. Only the push gate was taken, because it alone
  was blocking. The earlier estimate of "17 findings across 8 files" was
  measured against kit 0.2.7 in July and is superseded by this one
  (`tests/test_kit_drift.py` records the same numbers next to the pins;
  internal tooling, not a package surface).
* Documentation and process: the shared process kit is re-vendored to
  0.2.4 for the push gate, the incident-analyst charter and the private
  snapshot tool, a promotion whose reason is privacy rather than
  behaviour. `.claude/tools/snap.sh` is tracked and this remote is
  public, and its hashed body set the snapshot repositories' git
  identity from a personal name and a personal email address and located
  the shared ledger at an absolute path under a personal user profile.
  The 0.2.4 body reads the ambient git configuration with a neutral
  fallback and locates the shared tree through a new
  `COORD_SHARED_LEDGER_TREE`; three occurrences of a personal first name
  in the gate's deny messages and one in the analyst charter now read
  "the owning seat", as do one line each in the `handoff` and `plan` skills.
  No allow or deny decision changed, which was verified per replacement
  rather than assumed: each sits inside a deny message string, none in a
  condition, a return value, a constant set or a comparison. Removing
  the identifiers from HEAD stops them spreading and does not unpublish
  them; they remain in this repository's published history, and the
  address is in the project metadata of every commit already on the
  remote. Two things arrived with the promotion and are recorded rather
  than smoothed. The new variable is documented in `CLAUDE.md`, which is
  the only place it CAN be documented because the body that introduced
  it is hash-pinned. And the 0.2.4 body's claim that an unset variable
  skips the shared tree is false once the snapshot repository exists,
  where it instead reports a snapshot it did not take; that is a kit
  defect, registered against the coordination level that owns the
  master, with the interim mitigation in `CLAUDE.md`
  (`.claude/`, `CLAUDE.md`, `README.md`, `tests/`; internal tooling, not
  a package surface).

  **The push-gate half of this promotion is superseded within the same
  release.** The entry above re-vendors the gate alone to 0.2.16 to
  close a fail-open the 0.2.4 body carried, so the gate this release
  ships is 0.2.16 and not the 0.2.4 described here. The other three
  artifacts of this bullet, the analyst charter, the snapshot tool and
  the skill wording, are still at 0.2.4. Both entries stay: this one
  records why the privacy promotion happened, the other why the gate
  moved again, and a reader arriving at either needs the pointer.
* The rule that machine-specific values never appear in a committed file
  stops being prose. A tier-1 guard now fails on an email address or a
  user-profile path in any TRACKED file, scanning `git ls-files` rather
  than Markdown and Python only, which is how the file that leaked sat
  outside every house-style guard by file type. The name is
  deliberately NOT guarded: it is published on purpose in `LICENSE`,
  `CITATION.cff`, `pyproject.toml`, the SRS and the guide, and guarding
  a string that is meant to be published would need an allow-list long
  enough to be its own defect. The guard carries its own falsification,
  asserting that it fires on both shapes and stays quiet on the
  impersonal forms the tree legitimately holds (a reserved
  documentation domain, a loopback address, a forge no-reply sender, and
  an action version pin, which is the mail shape without a dotted
  top-level domain). Separately, `tests/test_env_contract.py` now reads
  the vendored shell tools and the `COORD_` prefix, closing the two
  independent reasons a new machine variable stayed invisible to the
  guard built for exactly that (`tests/test_house_style.py`,
  `tests/test_env_contract.py`; internal tooling, not a package
  surface).
* SRS 1.2.0 to 1.3.0: the Phase 4 acceptance batch, landed in full.
  NFR-19 (result column-schema stability), NFR-20 (deprecation policy),
  NFR-22 (dependency version envelope, with the pre-1.0 pin form and
  the Python-ceiling propagation), NFR-23 (layering guard) and NFR-24
  (software jargon glossed) are added; two of them were sharpened by
  seat answers the same day, so NFR-20 now states as the reference
  decision that within 0.x a break lands only in a MINOR release and a
  patch never changes the public surface, which is what lets a user
  write a version specifier against a 0.x package, and NFR-19 states
  that its column schema lives in the `results/tables.py` docstrings and
  that no rendered API reference is planned. AD-05, AD-06 and AD-07 are
  restated; the glossary gains the software terms NFR-24 requires.

    Phase 5 consolidation, same day: the batch is now written in full
    rather than in part. Twenty-six identifiers are added, covering the
    far-field ledgers (FR-38), the public exception hierarchy (FR-39),
    the options registry (FR-40), the ITACA adapter (FR-41), the
    reference-frame and sign conventions (FR-42), the console
    entry-point contract (FR-44), the strict manifest record (FR-45),
    the closed terminal-status set (FR-46), the probe-data export
    writers (FR-47), the public test-support assertions (FR-48),
    traceability closure (NFR-13), a confidentiality commit guard
    (NFR-14), manifest hash canonicalization (NFR-15), a coverage floor
    (NFR-16), one float-comparison convention (NFR-17), a manifest
    schema version (NFR-18), the support window (NFR-21), the
    optional-dependency error shape (NFR-25), and one term per level for
    the unit of work (NFR-26), plus the accepted splits of FR-02, FR-22,
    FR-30, FR-31, FR-33 and NFR-01 into singular claims that a single
    test can falsify. Ten requirements are reworded to say something
    checkable: FR-06 drops "no hidden logic" for a property of the
    emitted script, FR-08 names the attestation that verifies it rather
    than implying a test that cannot exist, FR-10 scopes "forever" to
    the external format and stops an unknown column being dropped
    silently, FR-11 replaces "lossless" with a reverse conversion, FR-20
    loses its status narration, FR-26 states its metric and that its
    bands are measured, FR-31 adds the per-version completeness
    confirmation, NFR-07 scopes reproducibility to the inputs and names
    the solver determinism boundary it does not control, and NFR-08
    defines "aggregated" as a line rather than a judgment.

    Two of the acceptances contradict each other and the SRS says so
    rather than silently picking one: FR-46 closes the terminal-status
    set at six values and FR-37 asks for a status the set does not
    contain as written. Resolved on 2026-08-03: the set stays closed at
    six and FR-37 is restated to ask for a status distinct from CONVERGED,
    which two of the six give.

    The
  user-facing consequences are in Deprecated below.

* The requirement set is published as a machine-readable index at
  `reports/requirements-index.json`, generated from `docs/srs` by
  `scripts/gen_requirements_index.py` and checked against it by a Tier 1
  test, carrying each requirement's id, statement and mandatory or
  deferred priority plus the two traceability counts (how many
  requirement ids any test cites, over the total). It exists because the
  external dashboard that consumes those numbers was maintaining them by
  hand and had fallen behind the SRS. New public page: the
  [acceptance mapping](https://nevesgeovana.github.io/pyflightstream/requirement-mapping/),
  which records which accepted item became which identifier, including
  the twenty-four that arrived without an identifier of their own.

### Deprecated

Keep a Changelog's sense of the word, soon-to-be removed, and NOT the
runtime-warning sense: nothing below emits a warning, because the
policy that would require one takes effect at 1.0 (SRS NFR-20). This
section is the notice, and for the removals it is the only one there
will be.

* **pandas and xarray leave the runtime dependencies at v0.5.0, and
  ITACA becomes a core dependency in their place** (SRS AD-06 and
  AD-07, the design decision of 2026-07-27). Nothing changes in this
  release: both are still declared, still imported, and everything
  works exactly as it does today.

    What actually breaks at v0.5.0, stated in full rather than by its
    most visible case. The tabular layer (`results.tables`) stops
    returning pandas DataFrames. AND the far-field and plot-writer
    surface goes with it: `farfield` takes and returns
    `xarray.Dataset`/`DataArray` in the signatures of some fifteen
    public functions (`lattice_dataset`, `mass_closure`, `shaft_torque`,
    `azimuthal_harmonics` and the rest of the ledgers), and
    `post.writers` consumes those structures. A rotor or far-field user
    is affected as much as a table user.

    What survives: the column NAMES and their units are unchanged (SRS
    NFR-19); the container type is what changes. What to do if that is
    not your schedule: pin `pyflightstream<0.5` and stay on the
    pandas/xarray surface.

* **The tabular layer rename has LANDED**, so the forward notice that
  stood here is now a record rather than a warning. What it announced
  is in this release's API surface delta above; the notice as it was
  written stands unaltered in the v0.3.0 notes, which is where a reader
  looking for the warning they were given will find it.
* **Erratum to the 0.3.0 notes**, which said the ITACA data adapter
  "is declared as a pyflightstream `[itaca]` extra". It was not: no
  such extra was ever added to `pyproject.toml`, and none will be.
  ITACA arrives as a core, non-optional dependency instead (AD-07).
  A released entry is never rewritten, so that one carries a
  supersession note in place and the correction itself lives here,
  which is what this file already does for three 0.3.0 entries.

### Fixed

* **`pyfs-qa apply-compat` could not promote the first probe run of a
  newly registered FlightStream version**, which is the one run a
  version onboarding exists to produce. It rewrote an existing
  single-line version entry and refused when the command had none, but
  a version starts life recorded only in `commands/_meta.yaml`, so on
  its first run every judged command has no line to rewrite. The whole
  run was unpromotable, and the only route left was a hand edit, which
  invariant 3 forbids. It now inserts the entry at the version's release
  position among the lines already there. A command whose version block
  holds no single-line entry to pattern on is still refused loudly.
* **Two commands were emitted with no count-versus-list check at all,
  which the solver turns into a corrupted script rather than an error.**
  A command that declares how many indices follow makes the solver read
  that many tokens; a count disagreeing with its list therefore makes it
  consume the next command line as data. The check keyed on the
  argument's NAME against a hand-kept set, because the vendor spells the
  count differently per command, so `UNSTEADY_SOLVER_NEW_FORCE_PLOT`
  (count spelled `boundaries`) and `ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS`
  (spelled `num_index`) escaped it entirely: `boundaries=3` with two
  indices rendered without complaint.

  Both names join the set, and the class is closed rather than the two
  instances: a tier-1 guard now walks the whole database and fails on
  any integer argument that introduces a list from outside the known
  set, so the next new spelling fails the suite instead of shipping
  unchecked. Found while diffing the 26.121 manual; the second instance
  was found by the guard, not by reading.
* **The eight blocker findings of the independent review are fixed, and
  every release up to and including v0.3.0 carries all of them.** They
  are one class in eight places, which is why they are listed together:
  a step that reduced, rendered or resumed its input before validating
  it, and so produced a plausible result from data that could not
  support one. **None of them raised, warned, set a flag or returned a
  non-zero status**, so a user of 0.3.0 cannot tell the failing case
  from the correct one from the library's own output. Each fix is at
  the structural cause and carries a guard proven by mutation against
  the pre-fix body.

  * *Command injection through any string or path argument.* A newline
    inside an emitted argument became a line boundary, so the text
    after it became the next command while `raw_flag` stayed False, the
    flag whose only job is to record that a script holds something
    unvalidated. `comment()` had the same hole. Text arguments now
    refuse a line terminator (new `ScriptLineBreakError`, subclassing
    `CommandArgumentError`), `comment()` prefixes every physical line,
    and `emit()` re-checks the rendered block so a future argument type
    cannot reopen it. `Script.raw()` remains the sanctioned route for
    unvalidated text, and still sets the flag.
  * *A NaN residual published as CONVERGED.* `max(velocity, pressure)`
    was tested for NaN after the fact, but every comparison against NaN
    is False, so `max` returned the other column: a NaN pressure
    residual was swallowed and the point converged on a residual that
    is not the one that decided it. An infinite residual reported
    `COMPLETED_MAX_ITER`, a status asserting the solver merely ran out
    of iterations. Both are now `FAILED_DIVERGED`.
  * *Missing far-field samples became a physical reduction.*
    `plane_integral` inherited xarray's `skipna=True`, so an absent
    sample left the sum while its ring weight stayed in the geometry,
    shrinking flux, force, torque and energy in exact proportion to how
    much data was missing. It now propagates NaN, and the new
    `farfield.sample_coverage` reports the finite fraction so the
    result is diagnosable rather than merely opaque.
  * *A cross-check that could not fail.* The harmonic transverse-flux
    path summed azimuthal orders up to `n/2 - 1`, omitting Nyquist, so
    on the one signal class where the two documented-independent paths
    disagree the check returned zero. It now sums the true half-band
    with Nyquist counted once.
  * *`resume` corrupted the manifest it protects.* Inputs were staged
    before the already-recorded test, so a resume with nothing to do
    called the solver zero times and still replaced the staged input
    while the manifest kept the old hash. Pending points are now
    decided before anything is prepared, and a partial resume whose
    input changed is refused.
  * *Declared outputs could leave the run, and collisions destroyed
    data.* An output name such as `../outside.txt` skipped validation
    entirely and was then collected with a MOVE, taking a file the run
    did not own. Two outputs, or two staged inputs, sharing a base name
    silently overwrote each other while the manifest recorded both.
    Names are now contained, and every collision is refused before
    anything moves.
  * *Two sweep points could share one `run_id`.* Point tags format at
    one decimal, so alpha 1.01 and 1.04 collide; nothing refused it and
    the duplicate surfaced only when the second point tried to record,
    leaving a half-executed campaign. Ambiguous sweeps and duplicate
    `sim_id`s are refused at load. The tag format is deliberately
    unchanged: it is run identity and appears in every existing
    manifest.
  * *An all-NaN blade passed every structural check.* Each validator is
    a comparison, and NaN fails them all, so it satisfied
    increasing-radii, positive-chord, positive-stiffness and
    nonnegative-inertia at once. Non-finite values are now refused
    first. Separately, a resumed FSI `state.json` was validated for
    types but never for shape, so a run resumed on memory from a
    differently shaped blade; new `fsi.state.check_state_matches_config`
    refuses it.

  Incompatible by intent: input that used to be accepted and produce a
  wrong answer is now refused. If a campaign, blade configuration or
  recipe starts failing to load, the refusal names the value and what
  it would have produced.
* A personal given name no longer ships inside the wheel. It sat in
  the `reason:` field of `qa/references/PHY-06.yaml`, which is declared
  package data, so it travelled to every machine that installed the
  library. The field itself is kept, including the probe reports it
  cites, which are the provenance that makes the reference defensible;
  only the attribution is rewritten. The name stays where it is
  authorship rather than incident (`LICENSE`, `CITATION.cff`, `README`,
  the docs), and a tier-1 guard now scopes the refusal to `src/`.
* The role-review push gate no longer lets a release reach PyPI with no
  release attestation. Its release detection was a denylist of exact
  option spellings (`--tags`, `--follow-tags`) plus a version-tag
  pattern that did not accept the `refs/tags/vX` form, so
  `git push --follow-tag origin main` (git accepts any unambiguous
  option prefix) and `git push origin HEAD:refs/tags/vX` both cleared as
  ordinary branch pushes and, with the branch already pushed and
  review-attested, shipped the tag with no release attestation into the
  live trusted-publishing workflow. The hardened gate and multi-ref
  attestation writer were promoted from the sister library as one
  matched change: option handling is now a fail-closed allowlist that
  denies any leading-dash token it cannot prove ref-neutral, release
  classification reads both sides of a refspec, push scope is resolved
  per ref (and per the remote the command would actually use), the
  repository identity for the incident query comes from
  `pyproject.toml` rather than the checkout folder, and
  `write_attestation.py` validates the pass names and covers every named
  ref in one run so a branch-and-tag release is attestable. Both
  original inputs were reproduced allowing against the pre-port gate and
  denying against the ported gate. `tests/test_push_gate.py` grows to
  the sister library's end-to-end case set and a new
  `tests/test_write_attestation.py` pins the writer. Incident
  INC-20260724-0839-pyflightstream (`.claude/` hooks; internal tooling,
  not a package surface).
* The push gate no longer falsely blocks a commit whose message is a
  heredoc that mentions a push. The gate's `_strip_heredocs`, which is
  meant to drop heredoc bodies before tokenizing, carried a stray
  U+0001 control byte at the end of its opener regex (invisible in an
  editor), so the pattern matched nothing, the stripper was dead, and
  the body was tokenized: a routine `git commit` documenting a push was
  denied. The byte is removed and a test pins all three delimiter
  forms. Same control-byte class as INC-20260724-0410-shared. Incident
  INC-20260724-0912-pyflightstream (`.claude/` hooks; internal tooling,
  not a package surface).
* A settings preset written in the solver's own words no longer fails
  to convert, and the same words can no longer invert a run in silence.
  `viscous_coupling = 'DISABLE'` in a settings file was refused with a
  bool-parsing message that named neither the vocabulary nor the
  translation; passing the same string to `solver_settings` emitted
  `ENABLE`, because a non-empty Python string is truthy and the toggle
  renderer only tested truthiness. Both directions of the vocabulary now
  live in one place (`script.toggles.resolve_toggle`), the helpers read their
  toggles before the first emission, and a word in neither vocabulary is
  refused naming the helper and the argument. Every release up to and
  including v0.3.0 is affected: a toggle passed as `'DISABLE'` emitted
  ENABLE, and the solver-setup snapshot recorded the inverted value as
  if it had been chosen. Runs whose recipes passed Python booleans are
  unaffected; to check an archived campaign, read the toggle lines of
  the rendered scripts under the managed simulation folders, or the
  `solver_setup` block of `runs.json`. Incident
  INC-20260723-2027-pyflightstream (feedback channel item 2, PLN-074).
* A swept case no longer loses the evidence of every point but the
  last. All points of a case run in the same simulation folder and are
  collected into `raw/` under their own names, so a declared output
  without the `{point}` placeholder was written, collected, and
  overwritten once per point, while the manifest listed the surviving
  file for all of them. The campaign loop now renders every point's
  output names before running the case and blocks it when two points
  would write the same one, so the check judges the actual collision
  rather than the presence of a particular placeholder (any template
  that distinguishes the points passes, and `{mach}`, which does not,
  is caught). The campaign example and the guide teach
  `outputs = ["loads_{point}.txt"]` with the recipe exporting
  `case.outputs[0]`, and `LoadsAssessor()` finds the loads table by
  content, so per-point evidence and convergence judgment are no longer
  exclusive. Incident INC-20260723-2113-pyflightstream.
* The user guide's flagship campaign listing imported `LoadsAssessor`
  from `pyflightstream.results`, where it does not exist; the guard
  below now checks every `from pyflightstream... import ...` line the
  guide teaches.
* The user guide taught `case.staged_geometry`, which `SimCase` never
  had: the campaign loop stages the geometry and rewrites
  `case.geometry`. A reader copying the campaign recipe got an
  `AttributeError` on their first point. Both occurrences corrected, and
  `tests/test_guide_api_names.py` now asserts that every `case.`,
  `helpers.` and `script.` name the guide teaches exists, and that every
  import line it shows resolves, so an unexecutable sample cannot ship
  again. Incident INC-20260723-2041-pyflightstream (PLN-084).
* `solver_settings(vorticity_drag_boundaries=...)` is optional again,
  and the guard that made it mandatory in v0.3.0 is gone: it stated the
  inverse of the manual page it cited. Boundaries left off the vorticity
  CDi list use the solver's surface pressure integration, a complete
  induced-drag calculation; the zero-drag pitfall happens the other way
  around, to a bluff body without a user-defined trailing edge that is
  put *on* the list, which also made the guard's suggested remedy
  (`"all"`) the very trap it claimed to prevent (SRC-003 p.202).
  Omitting the argument now emits no selection command and the
  solver-setup snapshot records the flag as a `default` with an empty
  selection and the citation, so the manifest still says which
  boundaries used vorticity integration (none). An empty sequence is
  refused (the same refusal now guards the deprecated `analysis_setup`
  keyword) with a message pointing at the omission that means the
  solver default. This restores the pre-v0.3.0 reproduction path (a
  legacy setup that never sets the list), which the guard had broken.
  The documentation carrying the inverted claim moved with it: the
  helper docstrings, the user guide (including the pitfalls slide),
  SRS FR-22 and its revision history, the command-database note, the
  examples, and the api-designer reviewer charter, which cited the
  guard as a didactic precedent (PLN-075).
* The deprecated `analysis_setup(vorticity_drag_boundaries=...)` no
  longer leaves the solver-setup snapshot describing a script that was
  never built: it now restamps the induced-drag record it overrides,
  records resolved boundary indices like the settings path rather than
  raw labels, and resolves and emits before touching the snapshot, so a
  bad label leaves the script, the deferred selection, and the record
  untouched. The corrected snapshot is `script.solver_setup`; a
  snapshot returned by an earlier `solver_settings` call is frozen at
  its own state. `Script` declares `solver_setup` and its induced-drag
  state as real attributes instead of carrying them as patched-on
  names.
* CI lint stage restored to green: the `ruff` dev dependency is pinned
  to `0.15.22` (matching the pre-commit hook) and Markdown files are
  excluded from ruff via `extend-exclude`. An unpinned ruff had begun
  reformatting the Python code samples inside `fsi/README.md` (an
  illustrative developer README, not a `.py` source the formatter
  owns), failing `ruff format --check`. The pin restores the known-good
  formatter and keeps CI, the hook, and developer machines identical;
  the `*.md` exclude makes the formatter's scope version-independent for
  any later ruff (PLN-024).
* Role-review gate before lane D caught residual user-guide staleness
  the v0.3.0 refresh missed: the Tier 2 pitfalls slide still listed
  `NEW_SURFACE_SECTION_DISTRIBUTION` as broken (it was promoted to
  verified in the licensed session), the install slide said "not yet
  on PyPI", the runtime-dependency list omitted xarray, and `post`
  and `fsi` were called reserved seams though both shipped; all
  corrected. The `NEW_SURFACE_SECTION_DISTRIBUTION` database note
  dropped its pending-re-probe language now that the re-probe decided,
  the `campaign_matrix` example's licensed `run_campaign` call names
  the required `assess`, and the `[plot]` extra records its
  matplotlib license note.
* Post-release front-page currency: README and the docs home announce
  v0.3.0 as public (they lagged at v0.2.0), the SRS roadmap moves the
  v0.3.0 release to Delivered, the standards page moves the Sybil
  executable-examples row to Adopted, the README DOI badge points at
  the Zenodo concept DOI, the CHANGELOG gains its `[Unreleased]` and
  `[0.3.0]` link references, and the user guide architecture labels
  use `workspace` (not the deprecated `files`).

## [0.3.0] - 2026-07-23

The v0.3.0 line: the usage-feedback workstreams (PLN-022) triaged from
the first outside-the-repo use of 0.2.0, delivered 2026-07-22,
plus the protocol and library-review adoptions of the ultraplan week.

### API surface delta

* New public names: the `workspace` package (renamed from `files`);
  `options` (plus top-level `get_option`, `set_option`,
  `reset_option`, `describe_option`, `option_context`); `exceptions`
  (the 25-class catalog); `testing` (`assert_records_close`,
  `assert_scripts_equal`); `overview()`; `solver_settings`,
  `SolverSetup`, `script_from_setup`; `cases.matrix` (`MatrixError`,
  `MatrixRow`, `resolve_matrix`, `plan_matrix`, `run_matrix`,
  `convert_matrix`, `to_campaign`); the pandas tables (`to_dataframe`,
  `to_csv`, `run_frame`, `sweep_frame`); `reference.CONVENTIONS`;
  `EntityRegistry`; the `pyfs-workspace` and `pyfs-matrix` CLIs.
* Incompatible changes: `solver_settings` requires
  `vorticity_drag_boundaries` (superseded: the requirement rested on a
  misread of SRC-003 p.202 and was removed, see Unreleased); the
  behavior selectors of `help`, `overview`, `run_campaign`,
  `register_option`, and `read_matrix` are keyword-only;
  `pyflightstream.files` and
  `pyflightstream.cases.matrix_legacy` are renamed (import shims kept
  through v0.4.0); converted campaigns carry `matrix_*` variable keys
  (were `legacy_*`).
* Deprecations: `pyflightstream.files` and
  `pyflightstream.cases.matrix_legacy` (removal v0.4.0,
  deadline-guarded); the `analysis_setup(vorticity_drag_boundaries=...)`
  path toward `solver_settings`.
* Removed: none (the `Legacy*` names survive as shim aliases).

Known gaps named for the next window: the formal `verified`
promotions of the version-sensitive commands (PLN-015) and the
aeroelastic family (PLN-019), and the unsteady-chapter backfill of
PHY-05/06 across versions.

### Added

* `workspace` package (renamed from `files`): the campaign workspace
  now organizes inputs as well as outputs, with a declarative
  input-artifact library under `inputs/` (references, solver-setup
  presets, boundary groups, geometries, profiles, and an executables
  registry by build id with an explicit-override rule), output naming
  templates (`NamingTemplate`, output-only by design: the manifest
  stays the sole identity authority and no parse-back API exists),
  `CampaignWorkspace.init()` behind the new `pyfs-workspace` CLI,
  campaign pre-flight (`plan_campaign`, zero solver time), and
  resumable incremental sweeps (`run_campaign(resume=True)`).
* Entity label registry in the script builder: frames, actuators,
  motions, and boundaries can carry user labels; every entity-citing
  argument accepts index or label; `declare_existing` accepts named
  boundary inventories; boundary range checks apply once declared.
* Solver-setup provenance: `solver_settings` becomes the single entry
  point for all 28 commands of the runtime, solver, and advanced
  settings families and returns a `SolverSetup` snapshot recording
  every flag's effective value with provenance (explicit,
  evidence-backed default, or unknown, never guessed); the snapshot
  rides the run manifest and `script_from_setup` regenerates the
  script from it.
* Tabular results layer on pandas: `to_dataframe`/`to_csv` for every
  parser, `run_frame` (one wide row per run), and `sweep_frame` (the
  whole sweep from the manifest).
* The run matrix as a first-class interface: `resolve_matrix`,
  `plan_matrix`, and `run_matrix` bind the matrix columns to the
  workspace input library; new `pyfs-matrix` CLI (convert, plan);
  the matrix fixture grows to eight rows.
* Two-level help: `pyflightstream.overview()` renders the
  architecture from the live module docstrings (docs Architecture
  page from the same source), and the command reference gains a
  manual-coverage section with explicit gap notes.
* `pyfs-qa cases`: the Tier 3 physics registry printed as a numbered
  test matrix.
* Command schema: optional evidence-cited default metadata.
* Deprecation ledger (`pyflightstream._deprecations`): every shim's
  removal promise recorded as a concrete version, with a Tier 1
  deadline guard that fails the suite when a shim survives past its
  recorded removal version or its warning stops citing it. Both live
  shims (`files`, `cases.matrix_legacy`) are registered with removal
  at v0.4.0, and their warnings now state that exact version instead
  of "a future minor release".
* `pyflightstream.options`: the declared-knob registry in the pandas
  `register_option` model (D1 adoption), with per-key validators,
  `option_context`, and `describe_option`. Keys are exact by design
  (never pattern-matched) and refusals follow the openmdao message
  contract (unknown keys list every registered key; rejected values
  name the option, the value, and the accepted form). First
  registered knobs: `qa.scratch_root`, `qa.probe_timeout_s`,
  `qa.case_timeout_s`; the `pyfs-qa` CLI scratch and timeout defaults
  now read from them. `get_option`, `set_option`, `reset_option`,
  `describe_option`, and `option_context` are re-exported at the
  package top level (pandas-style access); path options accept
  `pathlib.Path`.
* The public import surface is now affirmed by test (scipy
  `_public_api` model): `tests/test_public_api.py` declares every
  public module; a new module must join the list consciously or carry
  a leading underscore, deprecated modules are documented by the
  ledger alone, and every public module must import cleanly (or
  refuse with the install remedy) and carry its pipeline docstring.
  Lazy loading deliberately not adopted (D3 resolution).
* Tier 1 wording pins for the main didactic refusals
  (`tests/test_error_messages.py`, xarray pattern): versions,
  `solver_settings` (mandatory vorticity selection with the
  zero-induced-drag cause, mode regime, unsteady time stepping),
  workspace input library (id model, empty-library remedy, available
  ids listing), and the run-matrix reader (verified codes and layout).
  A refactor that keeps the exception type but drops the explanation
  now fails the suite. The mandatory-selection pin is superseded in
  Unreleased by the empty-selection refusal (SRC-003 p.202).
* `pyflightstream.exceptions`: single public catalog of all 25
  exception and warning classes (pandas errors model); completeness
  is test-asserted mechanically, so a new exception class must join
  the catalog in its defining commit. Structured refusals:
  `UnknownVersionError` now carries `version` and `known`,
  `InputArtifactError` carries `kind`, `artifact_id`, and
  `available`, so callers react without parsing messages.
* `pyflightstream.testing`: public assertions with quantified
  violation reports under the golden philosophy split;
  `assert_records_close` (count, violating keys, worst offender) and
  `assert_scripts_equal` (first differing line, total differing
  count, exact by policy).
* House conventions get a single home: `reference.CONVENTIONS`
  (naming, unit suffixes, keyword-only selectors, refusal style)
  rendered by `pyflightstream.help()` with a tier 1 adherence audit
  (`tests/test_conventions.py`) sweeping the code against the
  mechanical rules.
* Test-isolation hygiene: an autouse fixture snapshots every
  module-level registry and cached mutable default (physics and SMI
  cases, probe specs, derived flag map, sweep codes, entity nouns,
  the cached command database and manual-edition map) before each
  test and restores it after, so a mutating test cannot leak state;
  the inventory lives in one place in `tests/conftest.py` and the
  mechanism is itself tested.

### Changed

* `solver_settings` now requires `vorticity_drag_boundaries`
  (breaking; forgetting the selection silently zeroes the
  induced-drag accounting. Superseded: that rationale states the
  inverse of SRC-003 p.202, the requirement was removed in Unreleased,
  and boundaries left off the list keep the solver's surface pressure
  integration) and emits `SOLVER_MINIMUM_CP -100` by
  default when the flag is not passed, retiring the earlier
  reference-velocity workaround for rotor Cp clipping (override by
  passing the parameter). The PHY references were re-validated under
  the emitted default on a licensed 26.120 machine (build 7012026):
  all 30 metrics reproduce bit-identically, so no reference value
  changed (report
  `reports/physics/PHY-26120_2026-07-23_reseed-cp100-2026-07-23.md`).
* The run-matrix vocabulary drops the word "legacy" everywhere users
  see it: `LegacyMatrixError` and `LegacyRow` are renamed
  `MatrixError` and `MatrixRow`, and `to_campaign`/`convert_matrix`
  now preserve the matrix codes as `matrix_*` case variables
  (previously `legacy_*`; campaign files converted earlier keep their
  old keys and stay loadable, test-pinned). `read_matrix` makes
  `active_only` keyword-only, matching the rest of the module.
* Behavior-selecting arguments are keyword-only where the naming
  conventions already claim it (breaking, inside the unreleased v0.3
  window): `help(version, *, path, open_browser)`,
  `overview(*, path, open_browser)`, `run_campaign(campaign,
  executor, workspace, *, assess, recipes, resume)`, and
  `register_option(key, *, default, doc, validator)`. Positional
  calls to these selectors now raise `TypeError`.
* The motivation narrative (README, docs home, SRS introduction, user
  guide) now frames version drift as the natural counterpart of an
  actively developed solver whose team is responsive and consolidates
  user requests through intermediate hotfix builds into stable
  releases, instead of reading as criticism of the changelog; the
  documented facts and citations are unchanged.
* The docs toolchain migrated from MkDocs to ProperDocs, the
  maintained fork (license evidence RPT-009), after a green test:
  drop-in at the config and CLI level, with strict build and an
  identical page set and content on the same sources. The config
  file is renamed `properdocs.yml`, CI builds with
  `properdocs build --strict`, and the `[dev]` extra gains
  `properdocs` (the material theme and the nav plugins keep their
  mkdocs package names during the ecosystem transition; the build
  hook now imports from the `properdocs` namespace).

### Deprecated

* `pyflightstream.files`, in favor of `pyflightstream.workspace`: the
  shim re-exports everything with a DeprecationWarning until its
  recorded removal at v0.4.0 (deprecation ledger, deadline-guarded).
  The `analysis_setup(vorticity_drag_boundaries=...)` path is
  deprecated toward `solver_settings`.
* `pyflightstream.cases.matrix_legacy`, in favor of
  `pyflightstream.cases.matrix`: the shim re-exports everything until
  its recorded removal at v0.4.0 (deprecation ledger,
  deadline-guarded), keeping `LegacyMatrixError` and `LegacyRow` as
  aliases of the renamed classes. Both shims attribute their
  DeprecationWarning to the importing line on Python 3.12+, so plain
  script runs see it too.

### Fixed

* `__version__` now derives from the installed metadata (the
  published 0.2.0 wheel answered `0.0.1.dev0`), and the package
  docstring no longer describes the M0 skeleton.
* The public documentation caught up with the code after a full
  staleness audit: README rewritten to the released state, docs home
  updated, all three examples rendered on the site, CONTRIBUTING
  setup corrected.
* `pyflightstream.exceptions` now imports on a base install without
  the `[fsi]` extra: `StaleLoadsError` moved to `pyflightstream.fsi.state`
  (still re-exported by `fsi.driver`) so the catalog no longer pulls
  PyNite through the FSI modules on import.

### Evidence (licensed 26.1x session, 2026-07-23)

* `NEW_SURFACE_SECTION_DISTRIBUTION` moves broken to verified on
  26.120: the phase and `INCLUDE_SYMMETRY` grammar correction is
  confirmed by a re-probe (`CMP-26120_2026-07-23_pln012`);
  `AIR_ALTITUDE`, `SET_MOTION_START_TIME`, and
  `NEW_OFF_BODY_STREAMLINE` are re-confirmed broken.
* The bulk-separation spelling is resolved (`RPT-012`): the 26.100
  solver accepts `CREATE_BULK_SEPARATION` and rejects the manual
  sample-block spelling `CREARE` as unrecognized, so the database
  keeps the header spelling and no alias is added.
* Two research findings backing future features: `EXPORT_SURFACE_MESH`
  OBJ writes one named object block per boundary from the source mesh
  solid name (`RPT-010`, a fsm-to-obj boundary inspector is feasible),
  and the settings-and-status export exposes only the steady-mode
  default, not the wake and viscous toggles (`RPT-011`, their
  provenance stays honestly unknown).

### Added (documentation and process)

* Executable documentation examples in CI (Sybil): the docstring
  doctests and the python code blocks in the root README and `docs/`
  run as a CI step with warnings promoted to errors, so a stale
  example fails the build; `sybil` joins the `[dev]` extra. Three
  path-scoped Sybils leave the default `pytest` run untouched;
  CONTRIBUTING documents the local command. The README quickstart and
  the four example blocks execute green on 3.11 and 3.12.
* The user guide (`guide/`) is refreshed to the v0.3 surface
  (PLN-030): version 0.3.0, sixteen curated helpers (with
  `start_solver` and `coordinate_frame`), 144 commands, the current
  26.120 evidence counts, the `workspace` import path, and a
  four-tool command-line cheat sheet (`pyfs-qa` including `cases`,
  `pyfs-workspace`, `pyfs-matrix`, `pyfs-fsi`).
* New worked example `examples/campaign_matrix.py` (rendered on the
  docs site): the campaign side end to end without a license, run
  matrix to `campaign.toml` to a zero-solver `plan_campaign`
  pre-flight reporting the ready sweep points.
* Mesh inputs and GUI-only operations policy page in the docs
  (PLN-028): the supported GUI-once-then-script workflow when a step
  has no scripting command, the two canonical mesh input routes
  (geometry meshed inside FlightStream carried as a saved `.fsm`
  artifact, or a direct OBJ mesh), and the mesh format policy (OBJ
  as the reference format; further formats only ever behind a
  project-owned adapter).
* The Software Requirements Specification is published as a living
  document in the docs (`docs/srs/`): founding requirements with
  implementation statuses, the usage-feedback requirements, explicit
  non-requirements, architectural rules, standards alignment with
  verified references, and the roadmap.
* Documentation-currency policy (SRS NFR-11) with Tier 1 guards:
  version-bearing metadata files must agree, the changelog always
  carries its Unreleased section, SRS requirement ids never repeat.
* CONTRIBUTING discloses the AI-assisted development model and the
  process safeguards around it (evidence discipline, role-based
  review, the non-delegable seats, the clean-room rule
  extended to the AI), per the pyOpenSci disclosure item.
* README opens with status badges and a runnable quickstart snippet
  (validated build plus the didactic version refusal), and its
  feature list caught up with the cycle (options registry, exceptions
  catalog, testing assertions); live counts now stay with the
  generated compatibility matrix instead of hardcoded prose.
* Published package metadata completed per the PyPA well-known
  guidance (audit 2026-07-23): trove classifiers (beta status,
  science audience, Python versions, physics topic) and the
  Documentation, Changelog, and Issues project URLs join the
  Repository link.
* The documentation site is published to GitHub Pages on every push
  to main (`nevesgeovana.github.io/pyflightstream`), so the generated
  command reference, compatibility matrix, and architecture pages are
  reachable without a local build. The unused `mkdocstrings[python]`
  dev dependency was dropped (it was never wired into the build; the
  offline `help()` and `overview()` remain the docstring surface).
* Repository top level reduced to the public essentials: the
  reference session records left Git versioning (history preserved),
  and a `deprecated/` folder now groups discontinued public items.
* Role-based review process: five reviewer charters in
  `.claude/agents/` (architect, QA engineer, V&V engineer, technical
  writer, API designer) and the `role-review` skill that runs the
  applicable passes on a work item's diff before it closes, per the
  team-role model adopted 2026-07-23; the definition of done cites
  the passes, the owning seat keeps the non-delegable seats (product
  owner, domain expert, numerical analyst), and the standards
  alignment chapter records the model's public anchors.
* Co-development with the sister library ITACA (AD-07): the two
  libraries may generate requirements for each other, the docs gain
  the sister library page describing the division of labor and the
  cross-requirement convention, and the future data adapter is
  declared as a pyflightstream `[itaca]` extra (superseded: no such
  extra was ever added to `pyproject.toml` and none will be; ITACA
  arrives as a core dependency, see Unreleased) (ITACA stays
  solver-agnostic and never imports this package).

## [0.2.0] - 2026-07-22

First public release (PyPI and Zenodo). Milestones M6 (FSI) and M7
(far-field probes) landed between the tags, together with the Tier 3
matrix growth and a round of solver findings, every one backed by a
committed report.

### Added

* `fsi` subpackage (optional `[fsi]` extra, PyNiteFEA): validated
  `FsiConfig` with canonical hashing; sectional loads parser with the
  SI assertion, family-per-blade attribution with geometric
  cross-checks, and the pitch-axis to elastic-axis moment transfer;
  PyNite beam of the (w, theta) blade with exact massless-DOF
  condensation and clamped-beam benchmarks; centrifugal terms
  (tension through P-Delta, propeller moment with inner twist
  iteration) with the Campbell/Southwell verification; twist encoded
  as three-node differential translations with the exact inverse;
  node file, ordering map, and FSIDisp writer/reader from one
  generator, embedding sections at the local blade angle on spinning
  blades; four-phase coupling driver (wake, averaged relaxed
  coupling, convergence watch, unrelaxed recording) with atomic
  state, per-call freshness assertions, frozen replay mode, and a
  hash-carrying convergence log; `pyfs-fsi` executable dispatching
  between the coupled driver and the interface-evidence dummy.
* `probes` and `farfield` (far-field extraction line): serializable
  cylindrical lattice with version-aware emission; planar Cartesian
  probe grids on explicit frames with element-size and
  cosine/geometric distributions; geometry gate (optional `[geom]`
  extra) with containment culling, boundary-layer band refinement,
  and a wall standoff margin; single quadrature, azimuthal FFT
  harmonic spine, and the conservation ledgers with the synthetic G0
  gate in Tier 1; probe-export parser with the row-order contract
  check; `run.export_surface_mesh` pre-processing; `post` VTK and
  Tecplot probe-data writers.
* `qa`: PHY-05 (generic-blade unsteady periodic propeller) and
  PHY-06 (steady-versus-unsteady polar trend, 16 metrics) in the
  Tier 3 matrix with a per-version evidence gate; the `BladeSpec`
  generic propeller blade generator (public analytic shape laws).
* Command database grown from 116 to 144 entries: motion, unsteady
  solver, scenes, and advanced-settings backfill from the
  case-reproduction run; the mesh-import family; the Aeroelastic Coupling
  Toolbox family; per-version argument grammars
  (`versions.<v>.args`) with hotfix inheritance for the 26.1/26.12
  manual delta.
* Examples: FSI Campbell diagram and the wing static deflection
  worked cases; the beamer user guide source under `guide/`.

### Changed

* Two emission phases corrected on reproduction evidence
  (`SET_ANALYSIS_SYMMETRY_LOADS` and
  `NEW_SURFACE_SECTION_DISTRIBUTION` are in-solve consumers and
  precede `START_SOLVER`).
* `xarray` promoted to a runtime dependency (the far-field ledgers
  live on labeled arrays).

### Evidence

* FSI interface established on 26.120 build 7012026
  (`reports/RPT-005` to `RPT-007`): the implemented scripting
  interface is the Aeroelastic Coupling Toolbox family (the manual's
  `SET_MOTION_FSI` pair is unrecognized, candidate broken); the
  sectional loads export carries line densities and a three-decimal
  time-increment header (both folded back as code); the coupled loop
  ran 54/54 and 90/90 calls with the full phase machine and frozen
  replay reproducing held deformations to 5e-6.
* Probe round trip on 26.120 (`reports/RPT-004`): imported probe
  count and row order preserved exactly; boundary-layer export
  columns are geometric (erratum), motivating the standoff margin.
* PHY-05 bit-identical to its shareable-case baseline; PHY-06 polar
  trend 16 pass with monotonic steady-versus-unsteady deltas.

### Known limitations

* Two-way rotor FSI is blocked on FlightStream 26.120 build 7012026:
  the solver silently does not apply `FSIDisp.txt` morphing to
  boundaries attached to a rotary motion, while a motionless boundary
  morphs correctly with the same command sequence
  (`reports/RPT-007`; vendor report prepared). The coupling loop
  mechanics, the structural side, and the motionless path are fully
  functional.

## [0.1.0] - 2026-07-21

First tagged release, private phase. Everything below landed between
the repository seeding and this tag (milestones M0 through M5).

### Added

* `versions`: canonical 26.XXX version scheme with the ordered
  registry in `commands/_meta.yaml` as the only ordering authority;
  display aliases; registered manual editions (SRC-003 for 26.120,
  SRC-725 for 26.100).
* `commands`: version-aware command database, 116 commands drafted
  from the manual with a page citation each, typed argument
  specifications, script layout grammars, emission phases, and
  per-version evidence statuses (documented, verified, broken,
  removed) enforced at load time; hotfix builds inherit their base
  release record.
* `script`: builder with validating emit against the per-version
  database view, phase ordering, five layout renderers, and curated
  workflow helpers with a cross-reference ledger.
* `files` and `run`: managed campaign workspace with staging hashes
  and an append-only run manifest; local headless executor using the
  documented `-hidden --script` invocation.
* `cases`: SIM campaign model with TOML loading, recipe registry,
  campaign loop with six run statuses, and the pipe-delimited
  15-column run-matrix reader with lossless code preservation and
  TOML round-trip conversion.
* `results`: loads and residual-history parsers with sanitized
  fixtures from real 26.120 output; version cross-check recording the
  solver-reported version and build verbatim.
* `qa`: three-tier evidence harness. Tier 2 probe suite (109 specs)
  with committed compat reports and status promotion only through
  `pyfs-qa apply-compat`; Tier 3 physics regression matrix (PHY-01
  wing polar, PHY-02 symmetry equivalence) against banded references,
  plus the cross-version drift suite with the local-only SMI class
  behind an explicit `--smi-root`; `pyfs-qa` CLI with probe,
  apply-compat, physics, drift, and update-reference.
* `reference`: single rendering source for the command reference.
  `pyflightstream.help()` writes a self-contained HTML page offline;
  the mkdocs site renders the same database into a per-chapter
  command reference and a version compatibility matrix at build time
  (nothing generated is committed).
* Docs site (mkdocs-material, strict): generated reference and
  matrix, evidence-discipline overview, and the steady polar example
  rendered from its percent-format source.
* `examples/steady_polar.py`: synthetic NACA 0012 wing, one
  version-validated script per angle, the didactic refusal for a
  version without evidence, optional solver execution behind an
  explicit executable path; executed on 26.120 build 7012026 with
  lift slope 4.83 per rad against the finite-wing anchor 5.03.

### Evidence

* 26.120 (build 7012026): 64 commands verified, 4 broken, full
  physics matrix 10 pass (`reports/compat/CMP-26120_2026-07-21_full`,
  `reports/physics/PHY-26120_2026-07-21_full`).
* 26.100 (build 5012026): 28 commands documented from the 26.1 manual
  (SRC-725), one removal; first real cross-version drift 17 pass
  1 warn (`reports/physics/DRF-26100-26120_2026-07-21_complete`); the
  warn triaged as a deterministic solver change between builds
  (`reports/physics/TRI-SMI01-CMy_2026-07-21`).
* 26.000: registered, no recorded evidence yet (honest empty column;
  backfill planned for v0.2+).

[Unreleased]: https://github.com/nevesgeovana/pyflightstream/compare/v0.27.0...HEAD
[0.27.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.27.0
[0.26.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.26.0
[0.25.1]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.25.1
[0.25.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.25.0
[0.24.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.24.0
[0.23.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.23.0
[0.22.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.22.0
[0.21.1]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.21.1
[0.21.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.21.0
[0.20.1]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.20.1
[0.20.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.20.0
[0.19.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.19.0
[0.18.1]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.18.1
[0.18.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.18.0
[0.17.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.17.0
[0.16.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.16.0
[0.15.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.15.0
[0.14.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.14.0
[0.13.1]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.13.1
[0.13.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.13.0
[0.12.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.12.0
[0.11.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.11.0
[0.10.1]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.10.1
[0.10.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.10.0
[0.9.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.9.0
[0.8.1]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.8.1
[0.8.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.8.0
[0.7.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.7.0
[0.6.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.6.0
[0.5.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.5.0
[0.4.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.4.0
[0.3.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.3.0
[0.2.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.2.0
[0.1.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.1.0
