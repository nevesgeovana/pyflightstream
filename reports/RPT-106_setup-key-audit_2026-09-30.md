# RPT-106: setup-key audit of the solver chapters (2026-09-30)

Every command of the Solver Settings, Advanced Settings, Runtime Settings,
Unsteady Solver, Solver Analysis and Solver Initialization chapters, and whether
the value a user can choose for it reaches a script through a key, an argument
of a command with several choices being a row of its own. 98 rows: 78 covered,
2 given a key by this audit (FR-317, FR-319), 11 not a choosable value, 7 that
cannot be covered now, each with its measured or recorded reason, decided
or owed to a named release. Requirement
FR-319; its tier-1 test, `tests/tier1_offline/test_fr319_setup_key_audit.py`,
reads this table.

## Method

The command list is the union of two sources: every entry of the six
chapters of the command database (`src/pyflightstream/commands/runtime_settings.yaml`,
`solver_settings.yaml`, `advanced_settings.yaml`, `unsteady_solver.yaml`,
`solver_analysis.yaml`, `solver_initialization.yaml`), and every command the coverage census of 26.124
(GEO-068, `GEO-068_command-census.json` of the coordination reports) files under
those manual sections. A command the census lists and the database does
not carry is a row too (`SOLVER_INITIALIZATION`).

For each command the key column names where its value is chosen:

- `setup: <key>` a field of the setup preset, whose command
  `pyflightstream.cases.SOLVER_SETTING_COMMANDS` routes to this command;
- `row: <KEY>` a row key of the matrix cell; `column: <NAME>` a matrix column;
- `reference: <key>` a key of the reference artifact; `pproc: <table>` a table
  of the post-processing artifact.

A value the workflows emit hard-coded counts as MISSING even where the census
says covered: the one found was `SET_ANALYSIS_MOMENTS_MODEL PRESSURE`, written
by every builder beside the loads frame, now the setup key `moments_model`
(FR-317). A command with no argument is an action, not a value, and is listed
as such. `INITIALIZE_SOLVER` is a keyword block whose arguments are each a
choice, so each argument of the current grammar is a row (`INITIALIZE_SOLVER
<argument>`), and the tier-1 test requires one for each. Status values: `covered`, `given a key now`, `not a choosable value`,
`cannot be covered`.

The defaults of the keys given now are today's emitted values: an unstated
`moments_model` writes `PRESSURE`, an unstated `unsteady_solver_actions` writes
nothing, so every script of a setup naming neither is byte-identical (the
workflow goldens, and the parity check of the release).

## The table

| Command | Section | Status | Key | Where emitted | What the package did |
|---|---|---|---|---|---|
| `DISABLE_SOLVER_REF_VELOCITY` | Runtime Settings | covered | setup: disable_reference_velocity | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_MAX_PARALLEL_THREADS` | Runtime Settings | covered | setup: max_threads | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; the row's NCPUS bounds it | none needed |
| `SOLVER_SET_AOA` | Runtime Settings | covered | row: ALPHA | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; each point of a warm sweep | none needed |
| `SOLVER_SET_CONVERGENCE` | Runtime Settings | covered | setup: convergence | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_SET_FORCED_ITERATIONS` | Runtime Settings | covered | setup: forced_iterations | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_SET_ITERATIONS` | Runtime Settings | covered | setup: iterations | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_SET_MACH_NUMBER` | Runtime Settings | covered | setup: freestream_input | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` (the MACH pin of FLIGHT_CONDITION) | none needed |
| `SOLVER_SET_REF_AREA` | Runtime Settings | covered | reference: area_m2 | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_SET_REF_LENGTH` | Runtime Settings | covered | reference: chord_m | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_SET_REF_MACH_NUMBER` | Runtime Settings | covered | setup: reference_mach | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_SET_REF_VELOCITY` | Runtime Settings | covered | setup: reference_velocity_m_per_s | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; unstated, the free stream | none needed |
| `SOLVER_SET_SIDESLIP` | Runtime Settings | covered | row: BETA | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_SET_VELOCITY` | Runtime Settings | covered | row: VELOCITY | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `CREATE_AIRFOIL_SEPARATION` | Solver Settings | covered | setup: airfoil_separation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | a table: a preset's only (FR-316) |
| `CREATE_AXIAL_VORTEX_SEPARATION` | Solver Settings | covered | setup: axial_vortex_separation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | a table: a preset's only (FR-316) |
| `CREATE_BULK_SEPARATION` | Solver Settings | covered | setup: bulk_separation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, so refused there by the build guard | a table: a preset's only (FR-316) |
| `CREATE_CYLINDRICAL_BULK_SEPARATION` | Solver Settings | covered | setup: cylindrical_bulk_separation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | a table: a preset's only (FR-316) |
| `CREATE_STRATFORD_BULK_SEPARATION` | Solver Settings | covered | setup: stratford_bulk_separation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | a table: a preset's only (FR-316) |
| `DELETE_AXIAL_SEPARATION_BOUNDARIES` | Solver Settings | not a choosable value | none | not emitted by a workflow | no argument: an action, not a value |
| `DELETE_CROSSFLOW_SEPARATION_BOUNDARIES` | Solver Settings | not a choosable value | none | not emitted by a workflow | no argument: an action, not a value |
| `DELETE_SEPARATION` | Solver Settings | covered | setup: delete_separations | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `DELETE_THIN_BOUNDARIES` | Solver Settings | not a choosable value | none | not emitted by a workflow | no argument: an action, not a value |
| `DELETE_VALAREZO_CRITERION_BOUNDARIES` | Solver Settings | not a choosable value | none | not emitted by a workflow | no argument: an action, not a value |
| `DELETE_VALAREZO_SEPARATION_BOUNDARIES` | Solver Settings | not a choosable value | none | not emitted by a workflow | no argument: an action, not a value |
| `DELETE_VISCOUS_EXCLUDED_BOUNDARIES` | Solver Settings | not a choosable value | none | not emitted by a workflow | no argument: an action, not a value |
| `SET_AXIAL_SEPARATION_BOUNDARIES` | Solver Settings | covered | setup: axial_separation_families | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_BOUNDARY_LAYER_TYPE` | Solver Settings | covered | setup: boundary_layer | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_CROSSFLOW_SEPARATION_AXISYMMETRIC` | Solver Settings | covered | setup: crossflow_separation_axisymmetric | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_CROSSFLOW_SEPARATION_BOUNDARIES` | Solver Settings | covered | setup: crossflow_separation_boundaries | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_CROSSFLOW_SEPARATION_CP` | Solver Settings | covered | setup: crossflow_separation_mean_diameter | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_CROSSFLOW_SEPARATION_DIAMETER` | Solver Settings | covered | setup: crossflow_separation_diameter | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_SOLVER_MODEL` | Solver Settings | covered | setup: legacy_solver_model | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_SOLVER_STEADY` | Solver Settings | covered | column: WORKFLOW | the run type the WORKFLOW column names | none needed |
| `SET_SOLVER_UNSTEADY` | Solver Settings | covered | row: DELTA_TIME | script/helpers.py `unsteady_solver`, from the unsteady builders; TIME_ITERATIONS, DELTA_THETA and REVOLUTIONS too | none needed |
| `SET_SOLVER_VISCOUS_COUPLING` | Solver Settings | covered | setup: viscous_coupling | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_SURFACE_ROUGHNESS` | Solver Settings | covered | setup: surface_roughness | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_THIN_BOUNDARIES` | Solver Settings | covered | setup: thin_boundaries | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_VALAREZO_SEPARATION_BOUNDARIES` | Solver Settings | covered | setup: valarezo_separation_boundaries | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_VISCOUS_EXCLUDED_BOUNDARIES` | Solver Settings | covered | setup: viscous_excluded | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_WAKE_DECAY_CONSTANT` | Solver Settings | covered | setup: wake_decay_constant_per_m | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `VALAREZO_CRITERION` | Solver Settings | covered | setup: valarezo_criterion | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `ADDITIONAL_WAKE_RELAXATION_ITERATION` | Advanced Settings | covered | setup: additional_wake_relaxation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `AEROELASTIC_RBF_TYPE` | Advanced Settings | covered | setup: aeroelastic_rbf_type | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; cases/fsi_workspace.py on an FSI row | none needed |
| `KUTTA_JOUKOWSKI_LIFT_FORCES` | Advanced Settings | covered | setup: kutta_joukowski_lift | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `LAMINAR_SEPARATION` | Advanced Settings | covered | setup: laminar_separation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `PRINT_ROTOR_INDUCED_VELOCITIES` | Advanced Settings | covered | setup: print_rotor_induced_velocities | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `REYNOLDS_AVERAGED_DRAG_FORCES` | Advanced Settings | covered | setup: reynolds_averaged_drag | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `ROTOR_INDUCED_VELOCITY_BLENDING` | Advanced Settings | covered | setup: rotor_induced_velocity_blending | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_ADAPTIVE_FIELD_GRID_REFINEMENT` | Advanced Settings | covered | setup: adaptive_field_grid_refinement | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_ANALYSIS_MOMENTS_MODEL` | Advanced Settings | given a key now | setup: moments_model | cases/setup_link.py `analysis_frame_and_moments`, before START_SOLVER | FR-317: was hard-coded PRESSURE; unstated it still is, byte-identical. FR-318: VORTICITY implied on a rotor with vorticity drag |
| `SET_INVISCID_LOADS` | Advanced Settings | covered | setup: inviscid_loads | cases/setup_link.py `loads_selections`, after START_SOLVER, steady rows | none needed |
| `SET_JET_WAKE_DECAY_NORMALIZED_LENGTH` | Advanced Settings | covered | setup: jet_wake_decay_normalized_length | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` | Advanced Settings | covered | setup: jet_wake_filaments_grid_induction | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_SOLVER_CONVERGENCE_ITERATIONS` | Advanced Settings | covered | setup: convergence_iterations | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_WAKE_NUMERICAL_RELAXATION` | Advanced Settings | covered | setup: wake_numerical_relaxation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_WAKE_ON_WAKE_INDUCTION` | Advanced Settings | covered | setup: wake_on_wake_induction | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SET_WAKE_RELAXATION` | Advanced Settings | covered | setup: wake_relaxation | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_WAKE_STREAMWISE_AGGLOMERATION` | Advanced Settings | covered | setup: wake_streamwise_agglomeration | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SET_WAKE_TERMINATION_TIME_STEPS` | Advanced Settings | covered | setup: wake_termination_steps | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` (wake_termination_revolutions converted by the rotor builder) | none needed |
| `SOLVER_INITIALIZATION` | Advanced Settings | cannot be covered | none | nowhere | no entry in the command database: GEO-068 found the name in the manual's Script Index only, with no description or grammar; the load of a saved initialization is the OPEN argument that setup key load_solver_initialization states. Awaiting a decision |
| `SOLVER_MINIMUM_CP` | Advanced Settings | covered | setup: minimum_cp | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; unstated, the library default -100 | none needed |
| `SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER` | Advanced Settings | covered | setup: adverse_gradient_boundary_layer | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `SOLVER_SET_FARFIELD_LAYERS` | Advanced Settings | covered | setup: farfield_layers | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY` | Advanced Settings | covered | setup: mesh_induced_wake_velocity | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_STABILIZATION` | Advanced Settings | covered | setup: solver_stabilization | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` (or the stabilization pair of a preset) | none needed |
| `SOLVER_UNSTEADY_PRESSURE_AND_KUTTA` | Advanced Settings | covered | setup: unsteady_pressure_and_kutta | script/helpers.py `solver_settings`, from cases/workflows.py `_settings` | none needed |
| `SOLVER_VORTEX_RING_NORMALIZATION` | Advanced Settings | covered | setup: vortex_ring_normalization | script/helpers.py `solver_settings`, from cases/workflows.py `_settings`; no 26.124 row, refused there | none needed |
| `NEW_UNSTEADY_SOLVER_SURFACE_PROBE` | Unsteady Solver | covered | pproc: surface_probes | cases/workflows.py `_pproc_surface_probes` | none needed |
| `SET_NEW_UNSTEADY_SOLVER_ACTION` | Unsteady Solver | given a key now | setup: unsteady_solver_actions | cases/setup_link.py `emit_setup_extras`, end of the solver settings, marching rows | FR-319: the user's per-step actions, a table; the package's own counter and wall-clock actions follow |
| `SET_UNSTEADY_VISCOUS_COUPLING_ITERATION` | Unsteady Solver | covered | setup: unsteady_viscous_coupling_iteration | cases/workflows.py `_lift_and_coupling`; removed on 26.124 in the database, refused there | none needed |
| `SOLVER_TIME_AVERAGING` | Unsteady Solver | cannot be covered | none | nowhere | recorded broken on 26.124: reports/compat/CMP-26124_2026-09-19_time-averaging.yaml measured SOLVER_TIME_AVERAGING ENABLE hanging the solver; the surface average over a window is the pproc table time_averaging, computed by the post. Awaiting a decision |
| `UNSTEADY_SOLVER_ANIMATION` | Unsteady Solver | cannot be covered | none | nowhere | excluded by a recorded product decision of 2026-09-27 (the architecture record, section 16; OWNER_EXCLUDED in tests/tier1_offline/test_goal034_setup_operational_commands.py): the unsteady actions deliver the per-step exports. Awaiting a decision |
| `UNSTEADY_SOLVER_DELETE_ALL_PLOTS` | Unsteady Solver | not a choosable value | none | cases/workflows.py `_pproc_plots` | no argument: an action, not a value |
| `UNSTEADY_SOLVER_EXPORT_PLOTS` | Unsteady Solver | covered | pproc: exports | cases/workflows.py, the unsteady export block | the file is named for the point by the package's naming convention |
| `UNSTEADY_SOLVER_NEW_FLUID_PLOT` | Unsteady Solver | covered | pproc: probes | cases/workflows.py `_emit_one_probe_table` | none needed |
| `UNSTEADY_SOLVER_NEW_FORCE_PLOT` | Unsteady Solver | covered | pproc: plots | cases/workflows.py `_pproc_plots`; frame, parameter, name and boundaries from the pproc | the units argument is the next row |
| `UNSTEADY_SOLVER_NEW_FORCE_PLOT units` | Unsteady Solver | cannot be covered | none | cases/workflows.py `_pproc_plots`, from cases/__init__.py `FORCE_PLOT_PARAMETERS` | fixed per parameter: COEFFICIENTS for CL, CDI, CDO, CD and NEWTONS for the forces and moments, the units every unsteady product reads its plots in; a key would change what each product reads, which is a design decision. Awaiting it |
| `DELETE_VORTICITY_DRAG_BOUNDARIES` | Solver Analysis | covered | setup: clear_vorticity_drag_boundaries | cases/workflows.py, after START_SOLVER on a steady row | none needed |
| `SET_ANALYSIS_SYMMETRY_LOADS` | Solver Analysis | covered | setup: symmetry_loads | cases/workflows.py `_settings`; the row's SYMMETRY_LOADS column too | none needed |
| `SET_LOADS_AND_MOMENTS_UNITS` | Solver Analysis | covered | setup: load_units | cases/setup_link.py `loads_selections`, after START_SOLVER, steady rows | none needed |
| `SET_SOLVER_ANALYSIS_BOUNDARIES` | Solver Analysis | covered | setup: analysis_families | cases/setup_link.py `loads_selections`, after START_SOLVER, steady rows | none needed |
| `SET_SOLVER_ANALYSIS_LOADS_FRAME` | Solver Analysis | covered | reference: moment_point | cases/setup_link.py `analysis_frame_and_moments`, before START_SOLVER | none needed |
| `SET_VORTICITY_DRAG_BOUNDARIES` | Solver Analysis | covered | setup: vorticity_drag_families | script/helpers.py `start_solver`, after START_SOLVER | FR-318 links it to the moments model on a rotor |
| `SET_VORTICITY_LIFT_MODEL` | Solver Analysis | covered | setup: vorticity_lift_model | cases/workflows.py `_lift_and_coupling`; removed on 26.124 (RPT-068), refused there | none needed |
| `INITIALIZE_SOLVER` | Solver Initialization | covered | setup: solver_model | script/helpers.py `initialize_solver`, from cases/workflows/_skeleton.py, in every workflow; a keyword block, so the raw route cannot replace it (single lines only). Each of its arguments is a row below | none needed |
| `INITIALIZE_SOLVER solver_model` | Solver Initialization | covered | setup: solver_model | cases/workflows/_skeleton.py, `initialize_solver(solver_model=...)`; unstated, INCOMPRESSIBLE | none needed |
| `INITIALIZE_SOLVER surfaces` | Solver Initialization | cannot be covered | none | cases/workflows/_skeleton.py: always `-1`, every boundary | no measurement states a reason to leave a boundary out of the solution, and no cell or key names one; the package fixes the value on purpose: every workflow initializes all boundaries (`-1`), a design decision recorded on 2026-10-01 |
| `INITIALIZE_SOLVER surface_toggles` | Solver Initialization | cannot be covered | none | nowhere: written only with a chosen subset of surfaces, which no workflow states | the per-surface quad mesher flag exists only beside a chosen subset, so it follows the design decision of `surfaces` (all boundaries, `-1`, decided on 2026-10-01), and no workflow writes it |
| `INITIALIZE_SOLVER wake_termination_x` | Solver Initialization | cannot be covered | none | script/helpers.py `initialize_solver`, from cases/workflows/_skeleton.py: `DEFAULT` in every workflow | has no setup key, and the raw route cannot change it (a keyword block, refused). Measured on 26.124 (reports/probes/RPT-066_2026-09-24_evidence.yaml): under `DEFAULT` the solver places the end plane of the wake (the Trefftz plane) at a default distance it computes from the model (40.000 on one geometry, 8.000 on another), and a rotor wake measured later on 26.124 was bounded by that plane, so it cannot be made longer than it; that later measurement is registered with the 0.34 item and not yet a committed report. A setup key placed at least at the requested wake length with margin, and a plan warning when it is closer, is owed to 0.34 (item WAKE-LENGTH) |
| `INITIALIZE_SOLVER symmetry` | Solver Initialization | covered | row: SYMMETRY | cases/workflows/_skeleton.py, `initialize_solver(symmetry=...)`; unstated, NONE; the accepted modes are read from the build's own command database | none needed |
| `INITIALIZE_SOLVER symmetry_copies` | Solver Initialization | covered | row: PERIODIC_COPIES | cases/workflows/_skeleton.py, `initialize_solver(periodic_copies=...)`; required with PERIODIC and refused otherwise | none needed |
| `INITIALIZE_SOLVER wall_collision_avoidance` | Solver Initialization | covered | setup: wall_collision_avoidance | cases/workflows/_skeleton.py, `initialize_solver(wall_collision_avoidance=...)`; unstated, not written | none needed |
| `SOLVER_PROXIMAL_BOUNDARIES` | Solver Initialization | covered | setup: proximal_boundaries | cases/workflows/_solver_settings.py `_settings`, before INITIALIZE_SOLVER | none needed |
| `REMOVE_INITIALIZATION` | Solver Initialization | covered | setup: remove_initialization | cases/workflows/_solver_settings.py `_settings` | none needed |
| `START_SOLVER` | Solver Initialization | not a choosable value | none | script/helpers.py `start_solver`, in every workflow | no argument: an action, not a value |
| `CLEAR_SOLUTION` | Solver Initialization | not a choosable value | none | cases/workflows/_steady.py, between the points of a warm sweep | no argument: an action, not a value |
| `SOLVER_UNINITIALIZE` | Solver Initialization | not a choosable value | none | not emitted by a workflow | no argument: an action, not a value; the 25.000 spelling of `REMOVE_INITIALIZATION` |
| `SOLVER_CLEAR` | Solver Initialization | not a choosable value | none | not emitted by a workflow | no argument: an action, not a value; printed by 25.000 only, `CLEAR_SOLUTION` in its place |

## Cannot be covered now, decided or owed to a named release

- `INITIALIZE_SOLVER wake_termination_x`: written `DEFAULT` by every workflow,
  with no setup key, and not changeable by the raw route, which takes single
  lines and refuses keyword blocks. Measured on 26.124
  (`reports/probes/RPT-066_2026-09-24_evidence.yaml`): under `DEFAULT` the
  solver places the end plane of the wake at a default distance it computes
  from the model (40.000 on one geometry, 8.000 on another), and a rotor wake
  measured later on 26.124 was bounded by that plane, so it cannot be made
  longer than it. The key, placed at least at the requested wake length with
  margin, and a plan warning when the plane is closer, is owed to 0.34 (item
  WAKE-LENGTH), not to this release.
- `INITIALIZE_SOLVER surfaces` and `INITIALIZE_SOLVER surface_toggles`: every
  workflow initializes all boundaries (`-1`), and the per-surface quad mesher
  flag exists only beside a chosen subset. This is a design decision recorded
  on 2026-10-01: the value is fixed on purpose, so neither argument has a setup
  key, and `surface_toggles` is never written.
- `SOLVER_INITIALIZATION`: no entry in the command database. GEO-068 found the
  name in the manual's Script Index only, with no description and no grammar,
  so there is nothing to emit. The load of a saved initialization is the
  `OPEN` argument the setup key `load_solver_initialization` already states.
- `SOLVER_TIME_AVERAGING`: recorded broken on 26.124 in the command database,
  with the measurement `reports/compat/CMP-26124_2026-09-19_time-averaging.yaml`
  (ENABLE hangs the solver). A window average of the surface is the pproc
  table `time_averaging`, computed by the post from per-step exports.
- `UNSTEADY_SOLVER_ANIMATION`: documented on 26.124, and excluded from the
  package by a recorded product decision of 2026-09-27 (the architecture
  record, section 16; `OWNER_EXCLUDED` in
  `tests/tier1_offline/test_goal034_setup_operational_commands.py`): the
  unsteady actions deliver the per-step exports. A key waits on a new decision.
- The `units` argument of `UNSTEADY_SOLVER_NEW_FORCE_PLOT`: fixed per plotted
  parameter by `FORCE_PLOT_PARAMETERS` (`COEFFICIENTS` for CL, CDI, CDO and CD,
  `NEWTONS` for the forces and moments), the units every unsteady product reads
  its plots in. A key would change what each product reads, which is a design
  decision rather than a missing key.

## A row carries the scalar keys only

FR-316 lets a matrix row state a setup key over its preset. A row cell carries
a number, a word, true or false, or a comma-separated list of names; it cannot
carry a table. So the table-valued keys of this audit (the five separation
models, `ports`, `trailing_edge_types`, `actuator_operations`,
`base_region_operations` and `unsteady_solver_actions`) are reachable through
a preset only, and a row naming one is refused with that list.

## Licensed confirmation registered (FR-318)

On a row turning a rotor, FR-318 links `vorticity_drag_families` and
`moments_model`. The moments model is an init-phase command and precedes
`START_SOLVER`; `SET_VORTICITY_DRAG_BOUNDARIES` is an analysis-phase command in
every edition of the command database and follows it, so on an unsteady row
the drag list reaches the final loads export and not the per-step exports. Owed
to a licensed round, not run by this audit: on 26.124, an `unsteady_rotor` row
with `vorticity_drag_families` emitting `SET_VORTICITY_DRAG_BOUNDARIES` before
`START_SOLVER`, to measure whether the solver accepts it there and whether the
step exports then report the induced drag by vorticity integration. Until it
runs, the order stays as the database documents it.
