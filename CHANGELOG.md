# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [Unreleased]

- `pyfs-workspace geometry trailing-edge` extracts a mesh's trailing-edge midpoint
  file with explicit axis, hub and length unit.

- `pyfs-workspace calibrate` derives a sector-offset calibration from two recorded
  rotor points, preserving the existing evidence checks and unvalidated status.

- FSI workspace inputs can stage a checked frozen displacement file and explicitly
  allow configuration changes through the existing coupling driver controls.

### Changed

- Workspace post tables recorded force-distribution and surface CSV exports,
  preserving force units and explicitly unstated scalar identities.

- Workspace post writes mapped structural deflection, twist and available
  coupling history from admitted coupled points, with input-digest checks.

- Planar probe grids are declared in `[[probes]]`, with reference-frame placement,
  axis distributions and near-surface refinement checked during plan. Saved
  simulations require a separate surface mesh export before this route plans.

- Calculated FSI sections accept unit-chord airfoils or NACA four-digit contours.

- Coupled plans report effective station properties, natural frequencies and
  rotational excitation warnings before a licensed run.

- `pyfs-matrix support [build]` reports evidence-derived build support without
  launching the solver; omit the build to list every registered version.

- Migration instructions live in `docs/upgrading.md`. Current help no longer
  recommends retired input-id, geometry-folder or group-product migration tools;
  geometry instructions name the folder they require.
- Legacy-layout refusals name the required fields and the upgrading page;
  workflow pages no longer recommend removed matrix upgrade or rename commands.

- Run manifests use a versioned document with one status header,
  shared immutable solver/frame/geometry definitions and one ordered artifact
  list. Old record arrays are refused; `pyfs-workspace migrate` previews the
  0.38.0-format conversion and `--apply` preserves exact backups. Resolved run
  display includes all record fields. Migration leaves scientific products
  unchanged. Reposting 0.38.0 data uses 0.40.0's existing coefficient precision;
  the affected polar columns are named in `docs/upgrading.md`.
- Add matching steady-wing, unsteady isolated-propeller, quasi-steady rotor and
  mesh-refinement examples under `examples/using-CLI/` and `examples/using-API/`,
  with solver-free planning steps. Specialist examples are published as site pages.

- Release notes are written directly here; this changelog covers 0.38.0 onward.

- Maintainers: CI skips duplicate, docs-only and dry-run branch runs and cancels superseded runs; Release requires the newest main CI run at its SHA to be green on its latest attempt, measures coverage once in the tag's artifact tests, and docs deploy only on version tags.

### Removed

- Authored campaign-file loading and matrix-to-campaign-file conversion, including
  `pyfs-matrix convert`. The matrix is the sole campaign declaration; use
  `pyfs-matrix plan` or the public `plan_matrix` API.

### Fixed

- FR-124, FR-419: name the 0.40.0 polar, section and settings CSV format
  changes in the parity checker with bounded numeric comparisons.
- FR-362: batch script parity compares one complete batch. The 0.40.0 cost
  fit excludes failed and incomplete runs (PFS-2094.014, PFS-2094.015), so
  estimates and batch membership can change for workspaces with those records.

- FR-314: the local-run counter regression test uses deterministic polling
  instead of elapsed wall time to observe progress.

- FR-124, FR-419: parity checks numeric respelling within the base writer's
  printed rounding while preserving rows, column order and unchanged text.

- AD-15: restore four public import bindings in `run.cli` and `script.helpers`;
  parity excludes private module paths and scopes documented retirements to
  their fully qualified names (FR-457, FR-458).

- AD-15: parity exports include the requirements-path helper needed by the
  exported test collectors.

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

[Unreleased]: https://github.com/nevesgeovana/pyflightstream/compare/v0.40.0...HEAD
[0.40.0]: https://github.com/nevesgeovana/pyflightstream/compare/v0.39.0...v0.40.0
[0.39.0]: https://github.com/nevesgeovana/pyflightstream/compare/v0.38.0...v0.39.0
[0.38.0]: https://github.com/nevesgeovana/pyflightstream/compare/v0.37.0...v0.38.0
[0.34.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.34.0
