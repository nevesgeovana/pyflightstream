# Compat report: FlightStream 26.100 (2026-08-08)

Tier 2 command-validity evidence produced by the probe harness
(`pyfs-qa probe`); one evidence line per database command of this
version. Database statuses are promoted from this report only
through `pyfs-qa apply-compat`, never edited by hand (CLAUDE.md
invariant 3). Probe scripts and logs are local scratch; this
report is the committed evidence.

## Setup

| Item | Value |
|---|---|
| Executable | FlightStream_26_1.exe (local, `_private/exe/`, never committed) |
| Executor | LocalExecutor, `-hidden --script` (SRC-003 pp.279-280) |
| Package | pyflightstream 0.5.0.dev0 |
| Solver identity lines | FlightStream version 26.1, build #2122026 |

## Summary

1 verified, 0 broken, 174 unprobed.

## Evidence per command

| Command | Outcome | Evidence |
|---|---|---|
| CREATE_NEW_ACTUATOR | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the actuator name is readable in the saved simulation file |
| SET_ACTUATOR_AXIS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: actuator axis fields are stored in binary form; no instrument yet |
| SET_ACTUATOR_RADIUS | unprobed | not probed in this run |
| SET_PROP_ACTUATOR_RPM | unprobed | not probed in this run |
| SET_PROP_ACTUATOR_PROFILE | unprobed | not probed in this run |
| SET_PROP_ACTUATOR_THRUST | unprobed | not probed in this run |
| SET_PROP_ACTUATOR_SWIRL | unprobed | not probed in this run |
| ENABLE_ACTUATOR | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the enable flag is stored in binary form; no instrument yet |
| SET_SOLVER_CONVERGENCE_ITERATIONS | unprobed | not probed in this run |
| SOLVER_MINIMUM_CP | unprobed | not probed in this run |
| REYNOLDS_AVERAGED_DRAG_FORCES | unprobed | not probed in this run |
| SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY | unprobed | not probed in this run |
| SOLVER_SET_FARFIELD_LAYERS | unprobed | not probed in this run |
| SOLVER_UNSTEADY_PRESSURE_AND_KUTTA | unprobed | not probed in this run |
| SET_WAKE_TERMINATION_TIME_STEPS | unprobed | not probed in this run |
| SET_WAKE_ON_WAKE_INDUCTION | unprobed | not probed in this run |
| ADDITIONAL_WAKE_RELAXATION_ITERATION | unprobed | not probed in this run |
| LAMINAR_SEPARATION | unprobed | not probed in this run |
| SET_FREESTREAM | unprobed | not probed in this run |
| AIR_ALTITUDE | unprobed | not probed in this run |
| CAD_BODY_DELETE | unprobed | not probed in this run |
| CAD_BODY_MIRROR | unprobed | not probed in this run |
| CAD_BODY_ROTATE | unprobed | not probed in this run |
| CAD_BODY_SCALE | unprobed | not probed in this run |
| CAD_BODY_TRANSLATE | unprobed | not probed in this run |
| CAD_BODY_SELECT_BY_THRESHOLD | unprobed | not probed in this run |
| CAD_CREATE_INITIALIZE | unprobed | not probed in this run |
| SET_CAD_CREATE_MERGE_TOLERANCE | unprobed | not probed in this run |
| SET_CAD_CREATE_SPLINE_SEGMENTS | unprobed | not probed in this run |
| SET_CAD_CREATE_SPLINE_LOFT | unprobed | not probed in this run |
| SET_CAD_CURVATURE_REFINEMENT | unprobed | not probed in this run |
| CAD_CREATE_BOX | unprobed | not probed in this run |
| CAD_CREATE_SPHERE | unprobed | not probed in this run |
| CAD_CREATE_CYLINDER | unprobed | not probed in this run |
| CAD_CREATE_SHEET | unprobed | not probed in this run |
| CAD_CREATE_CURVE_POINT | unprobed | not probed in this run |
| CAD_CREATE_CURVE_LINE | unprobed | not probed in this run |
| CAD_CREATE_CURVE_ARC | unprobed | not probed in this run |
| CAD_CREATE_CURVE_SELECT | unprobed | not probed in this run |
| CAD_CREATE_CURVE_UNSELECT | unprobed | not probed in this run |
| CAD_CREATE_CURVE_REVERSE | unprobed | not probed in this run |
| CAD_CREATE_CURVE_DELETE_ALL | unprobed | not probed in this run |
| CAD_CREATE_CURVE_DELETE_SELECTED | unprobed | not probed in this run |
| CAD_CREATE_CURVE_DELETE_UNSELECTED | unprobed | not probed in this run |
| CAD_CREATE_ROTATE_CURVES | unprobed | not probed in this run |
| CAD_CREATE_TRANSLATE_CURVES | unprobed | not probed in this run |
| CAD_CREATE_SCALE_CURVES | unprobed | not probed in this run |
| CAD_CREATE_PROJECT_CURVE | unprobed | not probed in this run |
| CAD_CREATE_PROJECT_MULTI_CURVE | unprobed | not probed in this run |
| CAD_CREATE_REORDER_CURVES | unprobed | not probed in this run |
| CAD_CREATE_CONNECT_CURVES | unprobed | not probed in this run |
| CAD_CREATE_SELF_MEDIAN_FROM_CURVES | unprobed | not probed in this run |
| CAD_CREATE_CURVE_EXPORT_CCS | unprobed | not probed in this run |
| CAD_CREATE_IMPORT_CURVE_TXT | unprobed | not probed in this run |
| CAD_CREATE_IMPORT_CURVE_CCS | unprobed | not probed in this run |
| CAD_CREATE_IMPORT_CURVE_P3D | unprobed | not probed in this run |
| CAD_CREATE_CROSS_SECTION | unprobed | not probed in this run |
| CAD_CREATE_AUTO_CROSS_SECTIONS | unprobed | not probed in this run |
| CAD_CREATE_AUTO_ANNULAR_CROSS_SECTIONS | unprobed | not probed in this run |
| CAD_CREATE_WING_MESH_FROM_CCS | unprobed | not probed in this run |
| CAD_CREATE_FUSELAGE_MESH_FROM_CCS | unprobed | not probed in this run |
| CAD_CREATE_REVOLVE_MESH_FROM_CCS | unprobed | not probed in this run |
| NEW_CCS_WING_CONTROL_SURFACE | unprobed | not probed in this run |
| DEFAULT_CCS_WING_MESH_SETTINGS | unprobed | not probed in this run |
| CCS_WING_MESH_SUBDIVISIONS | unprobed | not probed in this run |
| CCS_WING_MESH_GROWTH_SCHEME | unprobed | not probed in this run |
| CCS_WING_MESH_GROWTH_RATE | unprobed | not probed in this run |
| CCS_WING_MESH_PERIODICITY | unprobed | not probed in this run |
| NEW_CCS_WING_REFINEMENT_ZONE | unprobed | not probed in this run |
| DELETE_CCS_WING_REFINEMENT_ZONES | unprobed | not probed in this run |
| NEW_CCS_WING_MORPHING_SURFACE | unprobed | not probed in this run |
| NEW_CCS_WING_FLAP_COVE | unprobed | not probed in this run |
| DELETE_CCS_WING_CONTROL_SURFACE | unprobed | not probed in this run |
| EXPORT_WING_CCS_FILE | unprobed | not probed in this run |
| CREATE_NEW_COORDINATE_SYSTEM | unprobed | not probed in this run |
| OPEN | unprobed | not probed in this run |
| SAVEAS | unprobed | not probed in this run |
| NEW_SIMULATION | unprobed | not probed in this run |
| CLOSE_FLIGHTSTREAM | unprobed | not probed in this run |
| EXPORT_LOG | unprobed | not probed in this run |
| OUTPUT_SETTINGS_AND_STATUS | unprobed | not probed in this run |
| IMPORT | unprobed | not probed in this run |
| CCS_IMPORT | unprobed | not probed in this run |
| SURFACE_ROTATE | unprobed | not probed in this run |
| TRANSLATE_SURFACE_IN_FRAME | unprobed | not probed in this run |
| TRANSLATE_SURFACE_BY_FRAME | unprobed | not probed in this run |
| SURFACE_SCALE | unprobed | not probed in this run |
| SURFACE_MIRROR | unprobed | not probed in this run |
| SURFACE_LINEAR_COPY_PASTE | unprobed | not probed in this run |
| SURFACE_CIRCULAR_COPY_PASTE | unprobed | not probed in this run |
| SELECT_GEOMETRY_BY_ID | unprobed | not probed in this run |
| SURFACE_SELECT_BY_THRESHOLD | unprobed | not probed in this run |
| CREATE_NEW_SURFACE_FROM_SELECTION | unprobed | not probed in this run |
| SURFACE_CUT_BY_PLANE | unprobed | not probed in this run |
| SURFACE_COMBINE | unprobed | not probed in this run |
| SURFACE_AUTO_HOLE_FILL | unprobed | not probed in this run |
| SURFACE_INVERT | unprobed | not probed in this run |
| SURFACE_RENAME | unprobed | not probed in this run |
| DELETE_SELECTED_FACES | unprobed | not probed in this run |
| DELETE_DEGENERATE_FACES | unprobed | not probed in this run |
| SURFACE_DELETE | unprobed | not probed in this run |
| SURFACE_CLEARALL | unprobed | not probed in this run |
| SELECT_MESH_NODE | unprobed | not probed in this run |
| TRANSFORM_SELECTED_NODES | unprobed | not probed in this run |
| CREATE_NEW_MOTION | unprobed | not probed in this run |
| SET_MOTION_BOUNDARIES | unprobed | not probed in this run |
| SET_MOTION_MOVING_FRAMES | unprobed | not probed in this run |
| SET_MOTION_COORDINATE_SYSTEM | unprobed | not probed in this run |
| SET_MOTION_START_TIME | unprobed | not probed in this run |
| SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION | unprobed | not probed in this run |
| SET_MOTION_FSI_EXECUTABLE | unprobed | not probed in this run |
| SET_MOTION_FSI_STRUCTURAL_NODES | unprobed | not probed in this run |
| DELETE_MOTION | unprobed | not probed in this run |
| SET_MOTION_VELOCITY | unprobed | not probed in this run |
| SET_MOTION_ACCELERATION | unprobed | not probed in this run |
| SET_MOTION_ANGULAR_VELOCITY | unprobed | not probed in this run |
| SET_MOTION_ANGULAR_ACCELERATION | unprobed | not probed in this run |
| SET_MOTION_IS_ROTOR | unprobed | not probed in this run |
| SET_MOTION_MASS_PROPERTIES | unprobed | not probed in this run |
| SET_MOTION_GRAVITY | unprobed | not probed in this run |
| SET_MOTION_CUSTOM_TABLE | unprobed | not probed in this run |
| SET_MOTION_6DOF_INITIAL_VELOCITY | unprobed | not probed in this run |
| SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY | unprobed | not probed in this run |
| SET_MOTION_6DOF_ACTIVE_VARIABLES | unprobed | not probed in this run |
| CREATE_NEW_6DOF_EXTERNAL_FORCE | unprobed | not probed in this run |
| CREATE_NEW_6DOF_CUSTOM_FORCE | unprobed | not probed in this run |
| CREATE_NEW_6DOF_SPRING_FORCE | unprobed | not probed in this run |
| DELETE_6DOF_EXTERNAL_FORCE | unprobed | not probed in this run |
| SET_6DOF_MOTION_SYMMETRY_LOADS | unprobed | not probed in this run |
| EXPORT_6DOF_TRAJECTORY | unprobed | not probed in this run |
| NEW_PROBE_POINT | unprobed | not probed in this run |
| NEW_PROBE_LINE | unprobed | not probed in this run |
| UPDATE_PROBE_POINTS | unprobed | not probed in this run |
| PROBE_POINTS_IMPORT | unprobed | not probed in this run |
| EXPORT_PROBE_POINTS | unprobed | not probed in this run |
| SOLVER_SET_AOA | unprobed | not probed in this run |
| SOLVER_SET_VELOCITY | unprobed | not probed in this run |
| SOLVER_SET_ITERATIONS | unprobed | not probed in this run |
| SOLVER_SET_FORCED_ITERATIONS | unprobed | not probed in this run |
| SOLVER_SET_REF_VELOCITY | unprobed | not probed in this run |
| SOLVER_SET_REF_AREA | unprobed | not probed in this run |
| SOLVER_SET_REF_LENGTH | unprobed | not probed in this run |
| STOP | unprobed | not probed in this run |
| PRINT | unprobed | not probed in this run |
| SET_VORTICITY_DRAG_BOUNDARIES | unprobed | not probed in this run |
| SET_SOLVER_ANALYSIS_LOADS_FRAME | unprobed | not probed in this run |
| SET_ANALYSIS_MOMENTS_MODEL | unprobed | not probed in this run |
| SET_ANALYSIS_SYMMETRY_LOADS | unprobed | not probed in this run |
| SET_LOADS_AND_MOMENTS_UNITS | unprobed | not probed in this run |
| SET_SOLVER_ANALYSIS_BOUNDARIES | unprobed | not probed in this run |
| SET_INVISCID_LOADS | unprobed | not probed in this run |
| EXPORT_SOLVER_ANALYSIS_SPREADSHEET | unprobed | not probed in this run |
| EXPORT_SOLVER_ANALYSIS_TECPLOT | unprobed | not probed in this run |
| EXPORT_SOLVER_ANALYSIS_VTK | unprobed | not probed in this run |
| SET_VTK_EXPORT_VARIABLES | unprobed | not probed in this run |
| EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS | unprobed | not probed in this run |
| INITIALIZE_SOLVER | unprobed | not probed in this run |
| REMOVE_INITIALIZATION | unprobed | not probed in this run |
| START_SOLVER | unprobed | not probed in this run |
| SET_SOLVER_STEADY | unprobed | not probed in this run |
| SET_SOLVER_UNSTEADY | unprobed | not probed in this run |
| SET_BOUNDARY_LAYER_TYPE | unprobed | not probed in this run |
| SET_SOLVER_VISCOUS_COUPLING | unprobed | not probed in this run |
| SET_VISCOUS_EXCLUDED_BOUNDARIES | unprobed | not probed in this run |
| DELETE_VISCOUS_EXCLUDED_BOUNDARIES | unprobed | not probed in this run |
| SET_AXIAL_SEPARATION_BOUNDARIES | unprobed | not probed in this run |
| DELETE_AXIAL_SEPARATION_BOUNDARIES | unprobed | not probed in this run |
| SET_VALAREZO_SEPARATION_BOUNDARIES | unprobed | not probed in this run |
| DELETE_VALAREZO_CRITERION_BOUNDARIES | unprobed | not probed in this run |
| DELETE_VALAREZO_SEPARATION_BOUNDARIES | unprobed | not probed in this run |
| SET_CROSSFLOW_SEPARATION_BOUNDARIES | unprobed | not probed in this run |
| DELETE_CROSSFLOW_SEPARATION_BOUNDARIES | unprobed | not probed in this run |
| SET_CROSSFLOW_SEPARATION_DIAMETER | unprobed | not probed in this run |
| SET_CROSSFLOW_SEPARATION_AXISYMMETRIC | unprobed | not probed in this run |
| SET_SURFACE_ROUGHNESS | unprobed | not probed in this run |
