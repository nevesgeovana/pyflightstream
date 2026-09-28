# From the GUI to pyfs

A FlightStream session in the GUI is a sequence of steps: load the geometry,
mark where its wakes leave it, place frames and set things turning, state the
flight condition and the solver, run, and export what you need. This page
takes those steps in that order and says, for each one, what does the same in
a workspace, with no Python: the key that does it, the solver commands that
key writes into the script, and the builds those commands are verified on. A
step pyfs does not take yet says **not yet**, and names the commands
[the raw route](#the-raw-route) would state instead.

How to read a line:

- **In pyfs** says which file the key lives in. A *row key* is a key of a
  matrix row, in its own column or in the `VAR_NAMES_VALUES` cell
  ([what a run matrix is](workspace-and-workflows.md#what-a-run-matrix-is));
  a *setup key* or *setup table* is in the solver preset the row's `SET`
  names; a *pproc table* or *pproc key* in the post-processing artifact its
  `PPROC` names; a *reference* table or block in the reference its `REF`
  names; and a *sidecar table* or *sidecar key* in `<stem>.boundaries.toml`,
  beside the geometry file. The link goes to the page that documents it.
- **Solver commands** are the lines the key writes into the script. Each one
  is in the [command reference](reference/index.md), with its evidence on
  every build.
- **Verified on** lists the builds on which the command database records a
  probe run of every command of the line, apart from the commands it names in
  brackets; `none` where it records none. A command with no probe run is still
  documented by its build's manual, and a key is refused, naming the build,
  where a command it needs does not exist.
  [Which build do I have](builds.md) maps your solver to these numbers.

## Workspace preparation

Generate [complete setup standards and their guide](setup-standards.md) with
`plan --setup-standards --setup-guidelines`. Inspect resolved values with
`inspect-setups` before execution. An [optional Excel workbook](excel-matrices.md)
uses Dictionary-based Preview, Apply and Cancel; no synchronization runs on open.

## Geometry and mesh

A saved simulation carries everything the GUI put in it, so the simplest
geometry is a `.fsm` you prepared once in the GUI. A raw mesh is imported, in
the unit its file is written in.

| In the GUI | In pyfs | Solver commands | Verified on |
|---|---|---|---|
| Open a saved simulation | row key `GEOMETRY` naming a `.fsm` ([what a run matrix is](workspace-and-workflows.md#what-a-run-matrix-is)); setup key `load_solver_initialization` loads the solver state it was saved with | `OPEN` | 26.100 to 26.124 |
| See the boundaries a saved simulation carries, in its order | sidecar key `boundaries`, which `pyfs-matrix inventory` writes from the file ([the boundary inventory sidecar](mesh-inputs.md#the-boundary-inventory-sidecar)) | none | none |
| Start a new simulation and import a mesh file in its length unit | row key `GEOMETRY` naming an `.obj` or `.stl`; sidecar table `[import]` with its `units`, and sidecar key `boundaries`, the file's surface names in its order, which the plan writes from an OBJ's groups ([starting from an OBJ or STL](mesh-inputs.md#starting-from-an-obj-or-stl)); setup key `simulation_length_unit` states the simulation's own length unit ([simulation units and geometry thresholds](simulation-geometry-controls.md)) | `NEW_SIMULATION`, `IMPORT`, `SET_SIMULATION_LENGTH_UNITS` | 26.101 to 26.124 (except `IMPORT`) |
| Scale, mirror, rename, move or turn a surface of the imported mesh | sidecar table `[[import.operations]]`, one per operation ([the mesh operations of an import](mesh-inputs.md#the-mesh-operations-of-an-import)) | `SURFACE_SCALE`, `SURFACE_MIRROR`, `SURFACE_RENAME`, `TRANSLATE_SURFACE_IN_FRAME`, `ROTATE_SURFACE`, `SURFACE_ROTATE` | none |
| Turn part of the geometry for one row: a flap, a blade's pitch | row key `ROTATE` ([one row, one geometry, turned](workspace-and-workflows.md#one-row-one-geometry-turned)) | `ROTATE_SURFACE`, `SURFACE_ROTATE`, `ROTATE_COORDINATE_SYSTEM` | none |
| Move part of the geometry for one row | row key `TRANSLATE` ([one row, one geometry, moved](workspace-and-workflows.md#one-row-one-geometry-moved)) | `TRANSLATE_SURFACE_IN_FRAME`, `SET_COORDINATE_SYSTEM_ORIGIN` | none |
| Name the configuration you loaded | row key `CONFIGURATION`, a label the script carries as a comment on its first line | none | none |
| Import CAD and mesh it | not yet: prepare it in the GUI once and save a `.fsm` ([GUI once, script everything after](mesh-inputs.md#the-saved-simulation-gui-once-script-everything-after)), or setup table `[[raw]]` ([the raw route](#the-raw-route)) | `IMPORT_CAD`, `CONVERT_CAD_TO_MESH` | none |
| Build a wing, a fuselage or a body of revolution from cross-section curves | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `CCS_IMPORT`, `CAD_CREATE_WING_MESH_FROM_CCS`, `CAD_CREATE_FUSELAGE_MESH_FROM_CCS`, `CAD_CREATE_REVOLVE_MESH_FROM_CCS` | none |
| Wrap or unite meshes into one closed surface | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `WRAPPER_EXECUTE`, `BOOLEAN_UNITE_MESH` | none |
| Repair a surface: delete, combine, invert, cut by a plane, fill holes | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `SURFACE_DELETE`, `SURFACE_COMBINE`, `SURFACE_INVERT`, `SURFACE_CUT_BY_PLANE`, `SURFACE_AUTO_HOLE_FILL`, `DELETE_DEGENERATE_FACES` | none |
| Copy a surface around an axis or along a line | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `SURFACE_CIRCULAR_COPY_PASTE`, `SURFACE_LINEAR_COPY_PASTE` | none |
| Export the surface mesh | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `EXPORT_SURFACE_MESH` | none |

## Boundary conditions

A saved simulation carries the trailing edges, wake-termination nodes and base
regions it was saved with. A raw mesh carries none, and its sidecar declares
them; a row marks base regions on either.

| In the GUI | In pyfs | Solver commands | Verified on |
|---|---|---|---|
| Mark the trailing edges from a file of edge points | sidecar table `[trailing_edges]` with `file`, and `type` and `tolerance` where not the default ([the boundary conditions of a raw mesh](mesh-inputs.md#the-boundary-conditions-of-a-raw-mesh)) | `IMPORT_WAKE_EDGES_FROM_FILE` | 26.124 |
| Detect the trailing edges over the whole mesh | sidecar table `[trailing_edges]` with `detect = "auto"` | `AUTO_DETECT_TRAILING_EDGES` | 26.101 to 26.122 |
| Detect the trailing edges of the surfaces you name, above a sweep angle | sidecar table `[trailing_edges]` with `detect = { surfaces = [...], sweep_angle = ... }` | `DETECT_TRAILING_EDGES_BY_SURFACE`, `SET_TRAILING_EDGE_SWEEP_ANGLE` | none |
| Mark the wake-termination nodes, over the whole mesh or by surface | sidecar table `[wake_termination]` | `AUTO_DETECT_WAKE_TERMINATION_NODES`, `DETECT_WAKE_TERMINATION_NODES_BY_SURFACE` | none |
| Make the boundaries you name base regions | row key `BASE_REGIONS`, or pproc key `base_regions`, naming the base and not the body that carries it ([the boundary conditions of a raw mesh](mesh-inputs.md#the-boundary-conditions-of-a-raw-mesh)) | `DETECT_BASE_REGIONS_BY_SURFACE` | none |
| Detect the base regions over the whole mesh | sidecar table `[base_regions]` with `detect = "auto"` | `AUTO_DETECT_BASE_REGIONS` | none |
| Apply or skip the trailing edges, wake-termination nodes and base regions the geometry declares | setup keys `apply_trailing_edges`, `apply_wake_termination` and `apply_base_regions`; `false` skips the redefinition and never clears saved state ([applying existing boundary declarations](setup-standards.md#applying-existing-boundary-declarations)) | the commands of the declaration lines above | none |
| Change one trailing edge's type: relaxed, jet outflow, vortex shedding | setup key `trailing_edge_types`, each trailing-edge index with its type ([setup standards](setup-standards.md)) | `SET_TRAILING_EDGE_TYPE` | 26.121 to 26.124 |
| Mark wake-termination nodes by hand, or stop a trailing edge's wake | setup keys `mark_wake_termination_nodes` and `disabled_wake_trailing_edges` | `MARK_WAKE_TERMINATION_NODES`, `DISABLE_WAKE_NODES_ON_TRAILING_EDGE` | 26.121 to 26.124 (except `MARK_WAKE_TERMINATION_NODES`) |
| Shed wakes from the leading edges of a surface | setup key `leading_edge_wake_boundaries` | `DETECT_LEADING_EDGES_WAKES_BY_SURFACE` | none |
| Create, remesh, delete or bend a base region, set its pressure, select its faces or mark its trailing or outflow edges | setup key `base_region_operations`, applied in the written order, and setup key `base_region_bending_angle_deg` for the detection angle ([ordered base-region actions](boundary-conditions.md#ordered-base-region-actions)) | `CREATE_NEW_BASE_REGION`, `REMESH_BASE_REGION`, `SET_BASE_REGION_BENDING_ANGLE`, `SET_BASE_REGION_CP`, `DELETE_BASE_REGION`, `SELECT_BASE_REGION_FACES`, `SET_BASE_REGION_TRAILING_EDGES`, `SET_OUTLET_TRAILING_EDGES`, `SET_OUTFLOW_TRAILING_EDGES` | none |
| Add an inlet or an outlet | the geometry's `[ports]` identifies the surfaces; setup table `[[ports]]` selects each one's role, and the matrix row supplies its velocity and profile variables ([port inputs](setup-standards.md#uniform-inlet-and-outlet-boundaries)). Creating ports on a saved simulation stays refused while its existing port indices are unknown | `CREATE_NEW_INLET`, `CREATE_NEW_OUTLET`, `SET_INLET_CUSTOM_PROFILE` | none |
| Delete an existing inlet or outlet | setup keys `delete_inlets` and `delete_outlets`, port indices in the written order ([explicit setup actions](boundary-conditions.md#explicit-setup-actions)) | `DELETE_INLET`, `DELETE_OUTLET` | none |
| Set the edge bluntness angles and the vertex merge tolerance | setup keys `geometric_edge_bluntness_angle_deg` and `vertex_merge_tolerance_m` ([simulation units and geometry thresholds](simulation-geometry-controls.md)); the trailing-edge bluntness angle through setup table `[[flags]]`, which gives a one-value command a word of your own, or setup table `[[raw]]` ([the raw route](#the-raw-route)) | `SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE`, `SET_TRAILING_EDGE_BLUNTNESS_ANGLE`, `SET_VERTEX_MERGE_TOLERANCE` | none |

## Frames, motion and actuators

| In the GUI | In pyfs | Solver commands | Verified on |
|---|---|---|---|
| Create a coordinate system | reference table `[[frames]]` ([the reference declares the study's vocabulary](workspace-and-workflows.md#the-reference-declares-the-studys-vocabulary)) | `CREATE_NEW_COORDINATE_SYSTEM`, `EDIT_COORDINATE_SYSTEM` | 26.120 to 26.124 |
| Create a rotor's hub and blade frames | reference block `kind = "rotor"`: its hub, `axis` and `families_blades` | `CREATE_NEW_COORDINATE_SYSTEM`, `EDIT_COORDINATE_SYSTEM` | 26.120 to 26.124 |
| Turn a rotor: a rotary motion about its axis, at its speed, moving its blades and frames | row keys `RPM` or `ADVANCE_RATIO`, `RPM_SIGN`, `ROTOR_AXIS`, `ROTOR_ORIGIN` and `MOVING_BOUNDARIES` ([the rotor speed, the advance ratio and the velocity](flight-conditions.md#the-rotor-speed-the-advance-ratio-and-the-velocity)) | `CREATE_NEW_MOTION`, `SET_MOTION_BOUNDARIES`, `SET_MOTION_MOVING_FRAMES`, `SET_MOTION_COORDINATE_SYSTEM`, `SET_MOTION_ROTOR_AXIS`, `SET_MOTION_ROTOR_RPM`, `SET_MOTION_ANGULAR_VELOCITY`, `SET_MOTION_IS_ROTOR` | none |
| Turn several rotors in one run | row keys `MOTIONS` and `CLOCK_MOTION`: one record per rotor, and the rotor whose turn sets the time step ([one row, several rotors](workspace-and-workflows.md#one-row-several-rotors)) | `CREATE_NEW_MOTION`, `SET_MOTION_BOUNDARIES`, `SET_MOTION_MOVING_FRAMES`, `SET_MOTION_COORDINATE_SYSTEM`, `SET_MOTION_ROTOR_AXIS`, `SET_MOTION_ROTOR_RPM` | none |
| Choose the direction a rotor's relaxed wake sheds | row key `ROTOR_SHEDDING`, read and checked; the direction is a field of the component definition, so no script command carries it | none | none |
| Turn the free stream: a roll, pitch or yaw rate | row keys `roll_rate`, `pitch_rate` and `yaw_rate` in the `FLIGHT_CONDITION` cell; reference table `[body_axes]` ([a rotating free stream](flight-conditions.md#a-rotating-free-stream)) | `SET_FREESTREAM` | none |
| Create an actuator disc: its axis, radius, speed and swirl | reference block `kind = "actuator"`; row keys `ACTUATOR` and `ACTUATOR_RPM` ([one row, one actuator disc](workspace-and-workflows.md#one-row-one-actuator-disc)) | `CREATE_NEW_ACTUATOR`, `SET_ACTUATOR_AXIS`, `SET_ACTUATOR_RADIUS`, `SET_PROP_ACTUATOR_RPM`, `SET_PROP_ACTUATOR_SWIRL`, `ENABLE_ACTUATOR` | 26.121 to 26.124 (except `ENABLE_ACTUATOR`) |
| Load the disc by its thrust | row key `ACTUATOR_THRUST` | `SET_PROP_ACTUATOR_THRUST` | none |
| Load the disc by a radial profile | row key `PROFILE`, a file of `inputs/profiles/` | `SET_PROP_ACTUATOR_PROFILE` | none |
| Rename or delete a disc | setup key `actuator_operations`, each naming one disc by its exact current name ([multiple actuator discs](setup-standards.md#multiple-actuator-discs)) | `SET_ACTUATOR_NAME`, `DELETE_ACTUATOR` | 26.120 to 26.124 |
| Disable a disc, or change its wake | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `DISABLE_ACTUATOR`, `SET_ACTUATOR_WAKE_TYPE` | none |
| Duplicate, mirror or delete a coordinate system | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `DUPLICATE_COORDINATE_SYSTEM`, `MIRROR_COORDINATE_SYSTEM`, `DELETE_COORDINATE_SYSTEM` | none |
| A motion of six degrees of freedom, with its mass, forces and gravity | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `CREATE_NEW_MOTION_6DOF`, `SET_MOTION_MASS_PROPERTIES`, `CREATE_NEW_6DOF_EXTERNAL_FORCE`, `SET_MOTION_GRAVITY` | none |
| A prescribed motion: a velocity, an acceleration, or a table in time | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `CREATE_NEW_MOTION_EUCLIDEAN`, `SET_MOTION_VELOCITY`, `SET_MOTION_ACCELERATION`, `CREATE_NEW_MOTION_CUSTOM`, `SET_MOTION_CUSTOM_TABLE` | none |
| Start a motion after the run has started | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `SET_MOTION_START_TIME` | none |

## Flight conditions and solver

| In the GUI | In pyfs | Solver commands | Verified on |
|---|---|---|---|
| Set the free stream: its speed, angle of attack and sideslip | row keys `ALPHA` and `BETA` in the `FLIGHT_CONDITION` cell, whose `MACH` or `TASmps` gives the speed ([flight conditions](flight-conditions.md)); row key `VELOCITY` from Python alone | `SET_FREESTREAM`, `SOLVER_SET_AOA`, `SOLVER_SET_SIDESLIP`, `SOLVER_SET_VELOCITY` | 26.120 to 26.124 (except `SET_FREESTREAM`) |
| Set a custom free stream: import a velocity field over the YZ plane from a file | row key `FREESTREAM`, the stem of a file of `inputs/freestreams/`, a `.txt` in the STRUCTURED form or a `.dat` in the UNSTRUCTURED form, in m and m/s; the field is the flow's direction, so the row's angle of attack and sideslip are 0 ([one row, one custom free stream](workspace-and-workflows.md#one-row-one-custom-free-stream)) | `SET_FREESTREAM` | none |
| Sweep the angle of attack or the sideslip | `ALPHA:sweep` or `BETA:sweep` in the `FLIGHT_CONDITION` cell, with the `SWEEP_VALUES` column: one script; since 0.29.0 every point starts cold, clearing the solution before it, and row key `COLD_START` set to `false` keeps the earlier warm start from the last point ([geometry units and steady starts](geometry-units-and-starts.md)) ([one sweep per row](workspace-and-workflows.md#one-sweep-per-row-and-the-geometry-variant-that-is-its-own-row)) | `SOLVER_SET_AOA`, `SOLVER_SET_SIDESLIP`, `CLEAR_SOLUTION` | 26.120 to 26.124 |
| Set the fluid: density, pressure, temperature, viscosity, speed of sound | the `FLIGHT_CONDITION` cell, or the setup's `[flight_condition]` table ([where a pin may live](flight-conditions.md#where-a-pin-may-live-the-row-or-the-setup-it-names)) | `FLUID_PROPERTIES` | 26.101 to 26.124 |
| Set the reference area, length and velocity | reference lengths ([what a reference artifact holds](workspace-and-workflows.md#what-a-reference-artifact-holds-beyond-the-three-lengths)); setup key `reference_velocity_m_per_s` | `SOLVER_SET_REF_AREA`, `SOLVER_SET_REF_LENGTH`, `SOLVER_SET_REF_VELOCITY` | 26.101 to 26.124 |
| Give the free stream as a Mach number, set the reference Mach number or the speed of sound, or switch the reference velocity off | setup keys `freestream_input`, `reference_mach`, `sonic_velocity_m_per_s` and `disable_reference_velocity` ([velocity, Mach and coefficient normalization](setup-standards.md#velocity-mach-and-coefficient-normalization)) | `SOLVER_SET_MACH_NUMBER`, `SOLVER_SET_REF_MACH_NUMBER`, `SONIC_VELOCITY`, `DISABLE_SOLVER_REF_VELOCITY` | 26.120 to 26.124 (except `SONIC_VELOCITY`, `DISABLE_SOLVER_REF_VELOCITY`) |
| State the units of a custom free-stream file | row key `FREESTREAM_UNITS`: `SI` for metres and metres per second, which the package scales once into the simulation's unit, or `NATIVE` for a file already in it ([custom-field units](custom-field-units.md)) | `SET_FREESTREAM` | none |
| Choose steady or unsteady, the time step and the number of steps | the `WORKFLOW` column: `steady`, `unsteady` or `unsteady_rotor`; row keys `DELTA_TIME` and `TIME_ITERATIONS`, or `DELTA_THETA` and `REVOLUTIONS` on a rotor row ([writing no Python at all](workspace-and-workflows.md#writing-no-python-at-all-the-workflow)) | `SET_SOLVER_UNSTEADY` | 26.100 to 26.124 |
| Set the iterations and the convergence threshold | setup keys `iterations`, `convergence`, `forced_iterations` and `convergence_iterations` ([what a solver preset may say](workspace-and-workflows.md#what-a-solver-preset-may-say-and-what-happens-to-a-key-that-reaches-nothing)) | `SOLVER_SET_ITERATIONS`, `SOLVER_SET_CONVERGENCE`, `SOLVER_SET_FORCED_ITERATIONS`, `SET_SOLVER_CONVERGENCE_ITERATIONS` | 26.120 to 26.124 |
| Set the number of processors | row key `NCPUS`, or setup key `max_threads` | `SET_MAX_PARALLEL_THREADS` | 26.120 to 26.124 |
| Choose the boundary layer and its coupling | setup keys `boundary_layer` and `viscous_coupling` | `SET_BOUNDARY_LAYER_TYPE`, `SET_SOLVER_VISCOUS_COUPLING` | 26.120 to 26.124 |
| Switch the viscous coupling on at a time step of an unsteady run | setup key `unsteady_viscous_coupling_iteration`, refused on 26.124, which does not answer the command | `SET_UNSTEADY_VISCOUS_COUPLING_ITERATION` | none |
| Initialise the solver: the compressibility model, wall-collision avoidance, a mirror plane or periodic copies | setup keys `solver_model` and `wall_collision_avoidance`; row keys `SYMMETRY` and `PERIODIC_COPIES`; setup key `legacy_solver_model` for the older model command | `INITIALIZE_SOLVER`, `SET_SOLVER_MODEL` | 26.101 to 26.124 (except `SET_SOLVER_MODEL`) |
| Remove a saved initialization, mark proximal boundaries, set the automatic trailing-edge and wake-node physics, or delete transition trips | setup keys `remove_initialization`, `proximal_boundaries`, `physics_auto_trailing_edges`, `physics_auto_wake_nodes` and `delete_transition_trips` ([explicit setup actions](boundary-conditions.md#explicit-setup-actions)) | `REMOVE_INITIALIZATION`, `SOLVER_PROXIMAL_BOUNDARIES`, `PHYSICS`, `DELETE_TRANSITION_TRIP` | 26.121 to 26.124 (except `PHYSICS`, `DELETE_TRANSITION_TRIP`) |
| Advanced settings: far-field layers, the mesh-induced wake velocity, wake-on-wake induction, a further wake relaxation | setup keys `farfield_layers`, `mesh_induced_wake_velocity`, `wake_on_wake_induction` and `additional_wake_relaxation` | `SOLVER_SET_FARFIELD_LAYERS`, `SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY`, `SET_WAKE_ON_WAKE_INDUCTION`, `ADDITIONAL_WAKE_RELAXATION_ITERATION` | 26.120, 26.122, 26.123 |
| Advanced settings: the minimum pressure coefficient, stabilisation, unsteady pressure and Kutta condition, Reynolds-averaged drag | setup keys `minimum_cp`, `solver_stabilization`, `unsteady_pressure_and_kutta` and `reynolds_averaged_drag` | `SOLVER_MINIMUM_CP`, `SOLVER_STABILIZATION`, `SOLVER_UNSTEADY_PRESSURE_AND_KUTTA`, `REYNOLDS_AVERAGED_DRAG_FORCES` | 26.120, 26.122, 26.123 |
| Advanced settings: wake relaxation, decay and agglomeration, and jet wakes | setup keys `wake_relaxation`, `wake_numerical_relaxation`, `wake_decay_constant_per_m`, `wake_streamwise_agglomeration`, `jet_wake_decay_normalized_length` and `jet_wake_filaments_grid_induction` | `SET_WAKE_RELAXATION`, `SET_WAKE_NUMERICAL_RELAXATION`, `SET_WAKE_DECAY_CONSTANT`, `SET_WAKE_STREAMWISE_AGGLOMERATION`, `SET_JET_WAKE_DECAY_NORMALIZED_LENGTH`, `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` | none |
| Advanced settings: where the wake ends | setup key `wake_termination_revolutions` or `wake_termination_steps` | `SET_WAKE_TERMINATION_TIME_STEPS` | none |
| Advanced settings: the lift and separation models | setup keys `kutta_joukowski_lift`, `vorticity_lift_model`, `laminar_separation`, `adverse_gradient_boundary_layer`, `vortex_ring_normalization` and `axial_separation_families` | `KUTTA_JOUKOWSKI_LIFT_FORCES`, `SET_VORTICITY_LIFT_MODEL`, `LAMINAR_SEPARATION`, `SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER`, `SOLVER_VORTEX_RING_NORMALIZATION`, `SET_AXIAL_SEPARATION_BOUNDARIES` | none |
| Advanced settings: rotor-induced velocities, field-grid refinement, the aeroelastic interpolation | setup keys `print_rotor_induced_velocities`, `rotor_induced_velocity_blending`, `adaptive_field_grid_refinement` and `aeroelastic_rbf_type` | `PRINT_ROTOR_INDUCED_VELOCITIES`, `ROTOR_INDUCED_VELOCITY_BLENDING`, `SET_ADAPTIVE_FIELD_GRID_REFINEMENT`, `AEROELASTIC_RBF_TYPE` | none |
| Create or delete a separation model: bulk, airfoil, axial vortex, cylindrical, Stratford | setup keys `bulk_separation`, `airfoil_separation`, `axial_vortex_separation`, `cylindrical_bulk_separation`, `stratford_bulk_separation` and `delete_separations` ([setup standards](setup-standards.md)) | `CREATE_BULK_SEPARATION`, `CREATE_AIRFOIL_SEPARATION`, `CREATE_AXIAL_VORTEX_SEPARATION`, `CREATE_CYLINDRICAL_BULK_SEPARATION`, `CREATE_STRATFORD_BULK_SEPARATION`, `DELETE_SEPARATION` | none |
| Set the Valarezo and crossflow separation criteria | setup keys `valarezo_criterion`, `valarezo_separation_boundaries`, `crossflow_separation_boundaries`, `crossflow_separation_diameter`, `crossflow_separation_mean_diameter` and `crossflow_separation_axisymmetric` | `VALAREZO_CRITERION`, `SET_VALAREZO_SEPARATION_BOUNDARIES`, `SET_CROSSFLOW_SEPARATION_BOUNDARIES`, `SET_CROSSFLOW_SEPARATION_DIAMETER`, `SET_CROSSFLOW_SEPARATION_CP`, `SET_CROSSFLOW_SEPARATION_AXISYMMETRIC` | none |
| Mark thin or viscous-excluded boundaries, or set a surface roughness | setup keys `thin_boundaries`, `viscous_excluded` and `surface_roughness` | `SET_THIN_BOUNDARIES`, `SET_VISCOUS_EXCLUDED_BOUNDARIES`, `SET_SURFACE_ROUGHNESS` | 26.121 to 26.124 (except `SET_THIN_BOUNDARIES`, `SET_SURFACE_ROUGHNESS`) |
| Couple the blade's structure to the aerodynamics (FSI) | row key `FSI`, naming a structural configuration of `inputs/fsi/`, and row keys `FSI_BENDING_STIFFNESS_N_M2_FACTOR`, `FSI_TORSION_STIFFNESS_N_M2_FACTOR`, `FSI_MASS_PER_LENGTH_KG_PER_M_FACTOR`, `FSI_INERTIA_MAJOR_KG_M_FACTOR`, `FSI_INERTIA_MINOR_KG_M_FACTOR`, `FSI_CG_OFFSET_CHORDWISE_M_FACTOR`, `FSI_CG_OFFSET_NORMAL_M_FACTOR`, `FSI_ELASTIC_AXIS_OFFSET_CHORDWISE_M_FACTOR`, `FSI_ELASTIC_AXIS_OFFSET_NORMAL_M_FACTOR`, `FSI_GEOMETRIC_PITCH_DEG_FACTOR`, `FSI_DENSITY_KG_PER_M3_FACTOR`, `FSI_YOUNGS_MODULUS_PA_FACTOR`, `FSI_SHEAR_MODULUS_PA_FACTOR` and `FSI_POISSON_RATIO_FACTOR`, each scaling one structural property of it ([FSI workspace inputs](fsi-workspace.md)) | none | none |

## The run

| In the GUI | In pyfs | Solver commands | Verified on |
|---|---|---|---|
| Start the solver | `pyfs-matrix plan`, then `pyfs-matrix run` ([writing no Python at all](workspace-and-workflows.md#writing-no-python-at-all-the-workflow)) | `START_SOLVER` | 26.101 to 26.124 |
| Close FlightStream when the script ends | every run type | `CLOSE_FLIGHTSTREAM` | 26.100 to 26.124 |
| Choose the build | the `FS_BUILD` column ([the build is an input](workspace-and-workflows.md#the-build-is-an-input)) | none | none |
| Run on this machine | `pyfs-matrix run`; on Linux with an HPC profile, `pyfs-matrix run --local` ([keeping a Linux run local](workspace-and-workflows.md#keeping-a-linux-run-local)) | none | none |
| Submit to a cluster | `pyfs-matrix run` on Linux with an HPC profile under `inputs/hpc/`, then `pyfs-matrix collect`; row keys `NCPUS` and `WALLTIME` ([where a submitted point runs](workspace-and-workflows.md#where-a-submitted-point-runs)) | none | none |
| Stop an unsteady run before its wall clock does, so it can be continued | row key `WALLTIME`, with its unit; setup key `walltime_margin_s` | `SET_NEW_UNSTEADY_SOLVER_ACTION`, `STOP` | none |
| Continue an unsteady run where it stopped | row key `RESTART`: `{FINISH_PENDING}`, `{ADDITIONAL_ITERS=n}` or `{ADDITIONAL_REVS=n}` | `OPEN`, `SET_SOLVER_UNSTEADY` | 26.100 to 26.124 |
| Limit one point's wall clock on this machine | setup key `timeout_s`, which pyfs enforces around the solver process | none | none |
| Run only the points not run yet | `pyfs-matrix run --resume` | none | none |
| Redo a point already run | `pyfs-matrix run --force-rerun <point>` ([redoing a point whose row was wrong](workspace-and-workflows.md#redoing-a-point-whose-row-was-wrong)) | none | none |
| Skip or refuse a family the mesh does not carry | `--ignore-missing-families` of `plan` and `run`, which reaches each case as row key `IGNORE_MISSING_FAMILIES` ([what the post-processing artifact holds](workspace-and-workflows.md#what-the-post-processing-artifact-holds)) | none | none |

## Basic post

| In the GUI | In pyfs | Solver commands | Verified on |
|---|---|---|---|
| Export the loads table | pproc table `[exports]`: `loads`, always on ([what the post-processing artifact holds](workspace-and-workflows.md#what-the-post-processing-artifact-holds)) | `EXPORT_SOLVER_ANALYSIS_SPREADSHEET` | 26.101 to 26.124 |
| Save the solved simulation | pproc table `[exports]`: `simulation`, always on | `SAVEAS` | 26.100 to 26.124 |
| Place the moment reference point and take the loads about it | reference table `[moment_point]`, which creates the frame `MRP` | `CREATE_NEW_COORDINATE_SYSTEM`, `EDIT_COORDINATE_SYSTEM`, `SET_SOLVER_ANALYSIS_LOADS_FRAME`, `SET_ANALYSIS_MOMENTS_MODEL` | 26.121 to 26.124 |
| Report the loads of the meshed half or sector, or of the whole | row key `SYMMETRY_LOADS`, or setup key `symmetry_loads` | `SET_ANALYSIS_SYMMETRY_LOADS` | 26.120, 26.122, 26.123 |
| Take the induced drag from the vorticity of the surfaces you name | setup key `vorticity_drag_families`; setup key `clear_vorticity_drag_boundaries` clears the selection after a steady solve ([explicit setup actions](boundary-conditions.md#explicit-setup-actions)) | `SET_VORTICITY_DRAG_BOUNDARIES`, `DELETE_VORTICITY_DRAG_BOUNDARIES` | 26.121 to 26.124 (except `DELETE_VORTICITY_DRAG_BOUNDARIES`) |
| Loads in newtons rather than coefficients, inviscid loads, or boundaries left out of the loads (steady rows) | setup keys `load_units`, `inviscid_loads` and `analysis_families` | `SET_LOADS_AND_MOMENTS_UNITS`, `SET_INVISCID_LOADS`, `SET_SOLVER_ANALYSIS_BOUNDARIES` | 26.120, 26.122, 26.123 (except `SET_SOLVER_ANALYSIS_BOUNDARIES`) |
| Print more significant digits | setup key `significant_digits` | `SET_SIGNIFICANT_DIGITS` | none |
| Export the surface solution as Tecplot, VTK or CSV, with the VTK variables you choose | pproc table `[exports]`: `tecplot` (on unless switched off), `vtk` and `csv` (off unless switched on); pproc key `vtk_variables` ([native surface flow exports](post-processing-definitions.md#native-surface-flow-exports)). The package preserves VTK cell values and adds same-step native nodal `Singularity_strength` after a unique geometry/topology match ([surface translation](surface-translation.md)) | `EXPORT_SOLVER_ANALYSIS_VTK`, `EXPORT_SOLVER_ANALYSIS_TECPLOT`, `EXPORT_SOLVER_ANALYSIS_CSV`, `SET_VTK_EXPORT_VARIABLES` | 26.120 to 26.124 (except `SET_VTK_EXPORT_VARIABLES`) |
| Export the force distribution, panel by panel | pproc table `[exports]`: `force_distributions`, off unless switched on | `EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS` | 26.120 to 26.124 |
| Average the surface solution over the last steps of an unsteady run | pproc table `[time_averaging]`: the row exports its surface at every step of the window and `pyfs-matrix post` averages them, cell by cell ([the time-averaged surface is the package's](post-processing-definitions.md#the-time-averaged-surface-is-the-packages-since-0280)) | `SET_NEW_UNSTEADY_SOLVER_ACTION`, `EXPORT_SOLVER_ANALYSIS_VTK` | none |
| Read boundary-layer integrals along configured cuts | pproc `[products]`: `boundary_layer_integrals = true`; original VTK cell values at recorded section cuts ([boundary-layer products](boundary-layer-products.md)). A fixed-frame native comparison exists on 26.124; other conventions need their own evidence | the VTK and section exports of the lines above | none |
| Write sampled velocity fields as VTK, Tecplot or reusable inflow | pproc `[[probes]]`: `field_formats` and `reusable_inflow` ([sampled fields](sampled-fields.md)); volume sections use the same probe sampling route. Evidence is specific to the export, the build and the unit; the guide states it | the probe-point exports or unsteady fluid plots of the lines below | none |
| Cut surface sections and export their Cp and sectional loads | pproc table `[sections]` ([the sections table](post-processing-definitions.md#the-sections-table-and-which-row-is-which)) | `NEW_SURFACE_SECTION_DISTRIBUTION`, `UPDATE_ALL_SURFACE_SECTIONS`, `COMPUTE_SURFACE_SECTIONAL_LOADS`, `EXPORT_ALL_SURFACE_SECTIONS`, `EXPORT_SURFACE_SECTIONAL_LOADS` | 26.120 to 26.124 (except `UPDATE_ALL_SURFACE_SECTIONS`) |
| Sample a flow-field plane and export velocity | pproc table `[volume_section]` ([a volume section](workspace-and-workflows.md#a-volume-section)); steady probes or unsteady/rotor fluid plots become package-written point fields; evidence is specific to the export, the build and the unit ([sampled fields](sampled-fields.md)) | `NEW_PROBE_POINT`, `UPDATE_PROBE_POINTS`, `EXPORT_PROBE_POINTS`, or `UNSTEADY_SOLVER_NEW_FLUID_PLOT` / `UNSTEADY_SOLVER_EXPORT_PLOTS` | 26.124 (except `UPDATE_PROBE_POINTS`) |
| Probe the flow at points and along lines (steady rows) | pproc table `[[probes]]` ([the probes table](post-processing-definitions.md#the-probes-table)) | `NEW_PROBE_POINT`, `NEW_PROBE_LINE`, `UPDATE_PROBE_POINTS`, `EXPORT_PROBE_POINTS` | 26.101 to 26.124 (except `UPDATE_PROBE_POINTS`) |
| Probe the flow through an unsteady run | pproc table `[[probes]]`, sampled as fluid plots | `UNSTEADY_SOLVER_NEW_FLUID_PLOT`, `UNSTEADY_SOLVER_EXPORT_PLOTS` | 26.124 |
| Plot the forces through an unsteady run | pproc table `[plots]` | `UNSTEADY_SOLVER_NEW_FORCE_PLOT`, `UNSTEADY_SOLVER_EXPORT_PLOTS` | 26.124 |
| Save residual, load and final section Cp plots | pproc table `[exports]`: `plot_residuals`, `plot_loads` and `plot_sections_cp` ([unsteady plots and averages](unsteady-postprocessing.md)); section Cp is exported once after the march, never at every STEP | `SET_PLOT_TYPE`, `SAVE_PLOT_TO_FILE` | 26.124 |
| Export the solver log | pproc table `[exports]`: `log`; row key `EXPORT_LOG`, which the HPC profile's `[log]` table writes, and row key `LOG_OUTPUT` from Python alone | `EXPORT_LOG` | 26.100 to 26.124 |
| Export at every step of an unsteady run, from a step on | row keys `EXPORT_UNSTEADY_AFTER_ITER` and `EXPORT_UNSTEADY_AFTER_REV` ([exports that begin after a threshold](workspace-and-workflows.md#exports-that-begin-after-a-threshold)) | `SET_NEW_UNSTEADY_SOLVER_ACTION` | none |
| Sum the loads of groups of surfaces into polars | pproc tables `[groups]` and `[products]` ([what the products are](workspace-and-workflows.md#what-the-products-are)) | none | none |
| Average an unsteady run over its last steps, per blade and at each azimuth | row keys `LAST_ITERS_AVG` or `LAST_REVS_AVG`, and `BLADES`; pproc tables `[phase_locked]`, `[equations]`, `[glossary]` and `[names]`, and pproc key `blade_pattern` ([post-processing definitions](post-processing-definitions.md)) | none | none |
| Post-process a saved simulation again, without solving it again | since 0.27.0: row key `ADDITIONAL_PPROC`, naming a second pproc of sections, sectional loads and surface exports, which `pyfs-matrix post --additional-pproc` extracts from each recorded point's final `.fsm` with no solve ([extracting more from a finished point](workspace-and-workflows.md#extracting-more-from-a-finished-point-the-additional-post)) | `OPEN`, `NEW_SURFACE_SECTION_DISTRIBUTION`, `UPDATE_ALL_SURFACE_SECTIONS`, `COMPUTE_SURFACE_SECTIONAL_LOADS`, `EXPORT_SOLVER_ANALYSIS_SPREADSHEET`, `EXPORT_ALL_SURFACE_SECTIONS`, `EXPORT_SURFACE_SECTIONAL_LOADS` | 26.124 (except `UPDATE_ALL_SURFACE_SECTIONS`) |
| Trace streamlines, on the surface or through the field | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `GENERATE_ALL_SURFACE_STREAMLINES`, `NEW_OFF_BODY_STREAMLINE`, `EXPORT_ALL_SURFACE_STREAMLINES`, `EXPORT_ALL_OFF_BODY_STREAMLINES` | none |
| Save a picture of the scene, coloured by a variable | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `SET_SCENE_CONTOUR`, `SAVE_SCENE_AS_IMAGE` | none |
| Export a boundary-layer velocity profile | Separate pproc `[products]` flag `boundary_layer_velocity_profile`; currently refused by name before execution ([profile limits](boundary-layer-products.md#the-separate-velocity-profile-request)). Integral products are not a substitute. The command has no positive unattended-build evidence: it opens a modal dialog on 26.122 and is broken on 26.124 | `EXPORT_BL_VELOCITY_PROFILE` | none |
| Export the surface pressures as structural loads | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `EXPORT_SOLVER_ANALYSIS_PLOAD_BDF` | 26.120 to 26.124 |
| Import probe points from a file | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `PROBE_POINTS_IMPORT` | 26.101 to 26.124 |
| Probe a surface property through an unsteady run | pproc table `[[surface_probes]]`, one per named point, parameter and frame ([surface-property histories](sampled-fields.md#surface-property-histories)) | `NEW_UNSTEADY_SOLVER_SURFACE_PROBE` | none |
| Animate a surface through an unsteady run | not yet: setup table `[[raw]]` ([the raw route](#the-raw-route)) | `UNSTEADY_SOLVER_ANIMATION` | none |

## The raw route

A step marked **not yet** has no key of its own, and a workflow row still
takes it, in one of three ways.

**A `[[raw]]` line in the setup preset**: the command as the solver reads it,
and the phase it goes before. Every row naming the preset emits it.

```toml
[[raw]]
command = "SET_TRAILING_EDGE_TYPE 3 RELAXED"
before = "init"
```

**A `RAW` record in the row's own cell**, for that row alone:
`RAW: {COMMAND: SET_TRAILING_EDGE_TYPE 3 RELAXED / BEFORE: init}`.

**A custom flag**, for a command that takes one value: the setup's `[[flags]]`
table gives the command a word of your own, and each row states its value
under that word, here `base_bending: 12.5`.

```toml
[[flags]]
name = "base_bending"
command = "SET_BASE_REGION_BENDING_ANGLE"
```

Each line passes the checks a curated line passes: the command exists on the
row's build, its arguments have the types the command database gives them, and
it keeps the script's phase order. A line that fails is refused at
`pyfs-matrix plan`, before any solver time is spent. A raw line names what it
acts on by index, a fact about one mesh file, so keep it to the case it is
written for. The whole grammar is under
[what a solver preset may say](workspace-and-workflows.md#what-a-solver-preset-may-say-and-what-happens-to-a-key-that-reaches-nothing).
A step that is more than a few lines, such as a geometry built from CAD, is
done once in the GUI and saved as a `.fsm`
([GUI once, script everything after](mesh-inputs.md#the-saved-simulation-gui-once-script-everything-after)),
and a `LEGACY` row runs a recipe of your own, in Python.
