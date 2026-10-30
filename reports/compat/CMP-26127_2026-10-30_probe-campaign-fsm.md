# Compat report: FlightStream 26.127 (2026-10-30)

Tier 2 command-validity evidence produced by the probe harness
(`pyfs-qa probe`); one evidence line per database command of this
version. Database statuses are promoted from this report only
through `pyfs-qa apply-compat`, never edited by hand (CONTRIBUTING.md
invariant 3). Probe scripts and logs are local scratch; this
report is the committed evidence.

## Setup

| Item | Value |
|---|---|
| Executable | Flightstream_2612.exe (sha256 withheld; build 10282026, local, `_private/exe/`, never committed) |
| Executor | LocalExecutor, `-hidden -script` (as run; mechanism FSM-26.120 pp.279-280; argument spelling RPT-023) |
| Package | pyflightstream 0.43.0 |
| Solver identity lines | Simcenter Flightstream version 2612, build #10282026 |

## Summary

89 verified, 3 broken, 1 removed, 288 unprobed.

## Evidence per command

| Command | Outcome | Evidence | Expected effect | Observation |
|---|---|---|---|---|
| ACOUSTIC_SOURCES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals exported after a marched rotor carry nonzero pressures with the sources enabled. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values | the signals exported after a marched rotor carry nonzero pressures with the sources enabled | 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| CREATE_NEW_ACOUSTIC_OBSERVER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals file holds an observer block named for the observer created. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values | the signals file holds an observer block named for the observer created | 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| ACOUSTIC_OBSERVERS_IMPORT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals file holds the two observers read from the observer file, named by index. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values | the signals file holds the two observers read from the observer file, named by index | 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| DELETE_ACOUSTIC_OBSERVER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: of the two observers created, only the second is left in the signals file after deleting index 1 (verified for observer 1 only). The instrument read: 1 observer blocks, rows per block [16], 0 nonzero pressure values | of the two observers created, only the second is left in the signals file after deleting index 1 (verified for observer 1 only) | 1 observer blocks, rows per block [16], 0 nonzero pressure values |
| DELETE_ALL_ACOUSTIC_OBSERVERS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals file holds the block of an observer created after the deletion (the positive control) and none of the two observers deleted. The instrument read: 1 observer blocks, rows per block [16], 0 nonzero pressure values | the signals file holds the block of an observer created after the deletion (the positive control) and none of the two observers deleted | 1 observer blocks, rows per block [16], 0 nonzero pressure values |
| SET_ACOUSTIC_OBSERVER_TIME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: every observer block of the signals file has 16 rows and starts at the requested time. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values | every observer block of the signals file has 16 rows and starts at the requested time | 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| COMPUTE_ACOUSTIC_SIGNALS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals exported after the computation carry data rows. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values | the signals exported after the computation carry data rows | 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| EXPORT_ACOUSTIC_SIGNALS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals file the command names exists and holds observer blocks. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values | the signals file the command names exists and holds observer blocks | 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| CREATE_ACOUSTIC_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the section's storage folder holds files after the section is created on a computed solution. The instrument read: 16 files in the section storage folder | the section's storage folder holds files after the section is created on a computed solution | 16 files in the section storage folder |
| CREATE_NEW_ACTUATOR | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the actuator name is readable in the saved simulation file | the actuator name is readable in the saved simulation file | missing |
| SET_ACTUATOR_NAME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the new actuator name is readable in the saved simulation file | the new actuator name is readable in the saved simulation file | missing |
| SET_ACTUATOR_AXIS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive axis offset 0.6622 | the saved simulation carries the distinctive axis offset 0.6622 | missing |
| SET_ACTUATOR_RADIUS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries both distinctive radii, 1.234 tip and 0.321 hub | the saved simulation carries both distinctive radii, 1.234 tip and 0.321 hub | missing |
| SET_PROP_ACTUATOR_RPM | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive rpm 3456.7 | the saved simulation carries the distinctive rpm 3456.7 | missing |
| SET_PROP_ACTUATOR_PROFILE | unprobed | not probed in this run | NA | missing |
| SET_PROP_ACTUATOR_THRUST | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the actuator thrust is stored in binary form; no instrument yet | the actuator thrust is stored in binary form; no instrument yet | missing |
| SET_PROP_ACTUATOR_SWIRL | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive swirl fraction 0.777 | the saved simulation carries the distinctive swirl fraction 0.777 | missing |
| ENABLE_ACTUATOR | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved simulation does not move when an actuator is enabled (RPT-020); an actuator appears to be enabled already when created, so the state instrument cannot separate the two | the saved simulation does not move when an actuator is enabled (RPT-020); an actuator appears to be enabled already when created, so the state instrument cannot separate the two | missing |
| DELETE_ACTUATOR | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the actuator name is present before deletion and absent afterwards; a missing before-state control is inconclusive | the actuator name is present before deletion and absent afterwards; a missing before-state control is inconclusive | missing |
| SET_ACTUATOR_WAKE_TYPE | unprobed | not probed in this run | NA | missing |
| SET_SOLVER_CONVERGENCE_ITERATIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive convergence window 37. The value is 37 rather than the 7 this probe used before instruments reached it: a single digit matches somewhere in any simulation file | the saved simulation carries the distinctive convergence window 37. The value is 37 rather than the 7 this probe used before instruments reached it: a single digit matches somewhere in any simulation file | missing |
| SOLVER_MINIMUM_CP | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive minimum-Cp floor | the saved simulation carries the distinctive minimum-Cp floor | missing |
| REYNOLDS_AVERAGED_DRAG_FORCES | unprobed | not probed in this run | NA | missing |
| SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY | unprobed | not probed in this run | NA | missing |
| SOLVER_SET_FARFIELD_LAYERS | unprobed | not probed in this run | NA | missing |
| SOLVER_UNSTEADY_PRESSURE_AND_KUTTA | unprobed | not probed in this run | NA | missing |
| SET_WAKE_TERMINATION_TIME_STEPS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command, set under the unsteady mode the rotor goldens render it in; the stored wake termination step count itself is not read back | the saved simulation differs after the command, set under the unsteady mode the rotor goldens render it in; the stored wake termination step count itself is not read back | missing |
| SET_WAKE_ON_WAKE_INDUCTION | unprobed | not probed in this run | NA | missing |
| ADDITIONAL_WAKE_RELAXATION_ITERATION | unprobed | not probed in this run | NA | missing |
| AEROELASTIC_RBF_TYPE | unprobed | not probed in this run | NA | missing |
| LAMINAR_SEPARATION | unprobed | not probed in this run | NA | missing |
| KUTTA_JOUKOWSKI_LIFT_FORCES | unprobed | not probed in this run | NA | missing |
| PRINT_ROTOR_INDUCED_VELOCITIES | unprobed | not probed in this run | NA | missing |
| SET_ADAPTIVE_FIELD_GRID_REFINEMENT | unprobed | not probed in this run | NA | missing |
| ROTOR_INDUCED_VELOCITY_BLENDING | unprobed | not probed in this run | NA | missing |
| SET_WAKE_NUMERICAL_RELAXATION | unprobed | not probed in this run | NA | missing |
| SET_JET_WAKE_DECAY_NORMALIZED_LENGTH | unprobed | not probed in this run | NA | missing |
| SET_WAKE_DECAY_CONSTANT | unprobed | not probed in this run | NA | missing |
| EXECUTE_AEROELASTIC_ANALYSIS | unprobed | not probed in this run | NA | missing |
| ASSIGN_AEROELASTIC_SURFACES | unprobed | not probed in this run | NA | missing |
| ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS | unprobed | not probed in this run | NA | missing |
| IMPORT_AEROELASTIC_STRUCTURAL_NODES | unprobed | not probed in this run | NA | missing |
| DELETE_AEROELASTIC_STRUCTURAL_NODES | unprobed | not probed in this run | NA | missing |
| SET_AEROELASTIC_WORKING_DIRECTORY | unprobed | not probed in this run | NA | missing |
| SET_AEROELASTIC_POST_PROCESSING_SCRIPT | unprobed | not probed in this run | NA | missing |
| SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND | unprobed | not probed in this run | NA | missing |
| SET_AEROELASTIC_ITERATIONS | unprobed | not probed in this run | NA | missing |
| SET_AEROELASTIC_COUPLING_IN_UNSTEADY | unprobed | not probed in this run | NA | missing |
| SET_AEROELASTIC_CONVERGENCE_THRESHOLD | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across a threshold a hundred times below the documented default; a still file records unprobed | the saved simulation moves across a threshold a hundred times below the documented default; a still file records unprobed | missing |
| SET_DIRECT_AEROELASTIC_MESH_MORPHING | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_BASE_REGION | unprobed | not probed in this run | NA | missing |
| SET_BASE_REGION_CP | unprobed | not probed in this run | NA | missing |
| SET_BASE_REGION_BENDING_ANGLE | unprobed | not probed in this run | NA | missing |
| DETECT_BASE_REGIONS_BY_SURFACE | unprobed | not probed in this run | NA | missing |
| SET_BASE_REGION_TRAILING_EDGES | unprobed | not probed in this run | NA | missing |
| DELETE_BASE_REGION | unprobed | not probed in this run | NA | missing |
| SELECT_BASE_REGION_FACES | unprobed | not probed in this run | NA | missing |
| REMESH_BASE_REGION | unprobed | not probed in this run | NA | missing |
| SET_OUTLET_TRAILING_EDGES | unprobed | not probed in this run | NA | missing |
| SET_TRAILING_EDGE_TYPE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored trailing-edge type itself is not read back | the saved simulation differs after the command; the stored trailing-edge type itself is not read back | missing |
| DISABLE_WAKE_NODES_ON_TRAILING_EDGE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored wake-node state itself is not read back | the saved simulation differs after the command; the stored wake-node state itself is not read back | missing |
| AUTO_DETECT_WAKE_TERMINATION_NODES | unprobed | not probed in this run | NA | missing |
| SET_FREESTREAM | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved simulation does not move (RPT-020). The reading is that CONSTANT is the state the simulation was already in, which would make the call a no-op rather than a failure; no page has been found stating the default, so the entry carries no default_ref and this stays a hypothesis. The CUSTOM and ROTATION forms await fixtures | the saved simulation does not move (RPT-020). The reading is that CONSTANT is the state the simulation was already in, which would make the call a no-op rather than a failure; no page has been found stating the default, so the entry carries no default_ref and this stays a hypothesis. The CUSTOM and ROTATION forms await fixtures | missing |
| FLUID_PROPERTIES | unprobed | not probed in this run | NA | missing |
| AIR_ALTITUDE | unprobed | not probed in this run | NA | missing |
| DETECT_TRAILING_EDGES_BY_SURFACE | unprobed | not probed in this run | NA | missing |
| DETECT_WAKE_TERMINATION_NODES_BY_SURFACE | unprobed | not probed in this run | NA | missing |
| MARK_WAKE_TERMINATION_NODES | unprobed | not probed in this run | NA | missing |
| DETECT_LEADING_EDGES_WAKES_BY_SURFACE | unprobed | not probed in this run | NA | missing |
| IMPORT_WAKE_EDGES_FROM_FILE | unprobed | not probed in this run | NA | missing |
| CAD_BODY_DELETE | unprobed | not probed in this run | NA | missing |
| CAD_BODY_MIRROR | unprobed | not probed in this run | NA | missing |
| CAD_BODY_ROTATE | unprobed | not probed in this run | NA | missing |
| CAD_BODY_SCALE | unprobed | not probed in this run | NA | missing |
| CAD_BODY_TRANSLATE | unprobed | not probed in this run | NA | missing |
| CAD_BODY_SELECT_BY_THRESHOLD | unprobed | not probed in this run | NA | missing |
| IMPORT_CAD | unprobed | not probed in this run | NA | missing |
| CONVERT_CAD_TO_MESH | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_INITIALIZE | unprobed | not probed in this run | NA | missing |
| SET_CAD_CREATE_MERGE_TOLERANCE | unprobed | not probed in this run | NA | missing |
| SET_CAD_CREATE_SPLINE_SEGMENTS | unprobed | not probed in this run | NA | missing |
| SET_CAD_CREATE_SPLINE_LOFT | unprobed | not probed in this run | NA | missing |
| SET_CAD_CURVATURE_REFINEMENT | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_BOX | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_SPHERE | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CYLINDER | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_SHEET | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_POINT | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_LINE | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_ARC | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_SELECT | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_UNSELECT | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_REVERSE | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_DELETE_ALL | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_DELETE_SELECTED | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_DELETE_UNSELECTED | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_ROTATE_CURVES | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_TRANSLATE_CURVES | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_SCALE_CURVES | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_PROJECT_CURVE | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_PROJECT_MULTI_CURVE | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_REORDER_CURVES | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CONNECT_CURVES | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_SELF_MEDIAN_FROM_CURVES | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CURVE_EXPORT_CCS | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_IMPORT_CURVE_TXT | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_IMPORT_CURVE_CCS | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_IMPORT_CURVE_P3D | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_CROSS_SECTION | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_AUTO_CROSS_SECTIONS | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_AUTO_ANNULAR_CROSS_SECTIONS | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_WING_MESH_FROM_CCS | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_FUSELAGE_MESH_FROM_CCS | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_REVOLVE_MESH_FROM_CCS | unprobed | not probed in this run | NA | missing |
| CAD_CREATE_MIRROR_CURVES | unprobed | not probed in this run | NA | missing |
| SET_CCS_TE_BLEND_LENGTH | unprobed | not probed in this run | NA | missing |
| DEFAULT_CCS_FUSELAGE_MESH_SETTINGS | unprobed | not probed in this run | NA | missing |
| CCS_FUSELAGE_MESH_SUBDIVISIONS | unprobed | not probed in this run | NA | missing |
| CCS_FUSELAGE_MESH_GROWTH_SCHEME | unprobed | not probed in this run | NA | missing |
| CCS_FUSELAGE_MESH_GROWTH_RATE | unprobed | not probed in this run | NA | missing |
| CCS_FUSELAGE_MESH_PERIODICITY | unprobed | not probed in this run | NA | missing |
| NEW_CCS_FUSELAGE_REFINEMENT_ZONE | unprobed | not probed in this run | NA | missing |
| DELETE_CCS_FUSELAGE_REFINEMENT_ZONES | unprobed | not probed in this run | NA | missing |
| NEW_CCS_FUSELAGE_RELAXED_TE | unprobed | not probed in this run | NA | missing |
| DELETE_CCS_FUSELAGE_RELAXED_TE | unprobed | not probed in this run | NA | missing |
| EXPORT_FUSELAGE_CCS_FILE | unprobed | not probed in this run | NA | missing |
| ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE | unprobed | not probed in this run | NA | missing |
| DEFAULT_CCS_REVOLVE_MESH_SETTINGS | unprobed | not probed in this run | NA | missing |
| CCS_REVOLVE_MESH_SUBDIVISIONS | unprobed | not probed in this run | NA | missing |
| CCS_REVOLVE_MESH_GROWTH_SCHEME | unprobed | not probed in this run | NA | missing |
| CCS_REVOLVE_MESH_GROWTH_RATE | unprobed | not probed in this run | NA | missing |
| CCS_REVOLVE_MESH_PERIODICITY | unprobed | not probed in this run | NA | missing |
| NEW_CCS_REVOLVE_REFINEMENT_ZONE | unprobed | not probed in this run | NA | missing |
| DELETE_CCS_REVOLVE_REFINEMENT_ZONES | unprobed | not probed in this run | NA | missing |
| NEW_CCS_REVOLVE_RELAXED_TE | unprobed | not probed in this run | NA | missing |
| DELETE_CCS_REVOLVE_RELAXED_TE | unprobed | not probed in this run | NA | missing |
| EXPORT_REVOLVE_CCS_FILE | unprobed | not probed in this run | NA | missing |
| ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY | unprobed | not probed in this run | NA | missing |
| NEW_CCS_WING_CONTROL_SURFACE | unprobed | not probed in this run | NA | missing |
| DEFAULT_CCS_WING_MESH_SETTINGS | unprobed | not probed in this run | NA | missing |
| CCS_WING_MESH_SUBDIVISIONS | unprobed | not probed in this run | NA | missing |
| CCS_WING_MESH_GROWTH_SCHEME | unprobed | not probed in this run | NA | missing |
| CCS_WING_MESH_GROWTH_RATE | unprobed | not probed in this run | NA | missing |
| CCS_WING_MESH_PERIODICITY | unprobed | not probed in this run | NA | missing |
| NEW_CCS_WING_REFINEMENT_ZONE | unprobed | not probed in this run | NA | missing |
| DELETE_CCS_WING_REFINEMENT_ZONES | unprobed | not probed in this run | NA | missing |
| NEW_CCS_WING_MORPHING_SURFACE | unprobed | not probed in this run | NA | missing |
| NEW_CCS_WING_FLAP_COVE | unprobed | not probed in this run | NA | missing |
| DELETE_CCS_WING_CONTROL_SURFACE | unprobed | not probed in this run | NA | missing |
| EXPORT_WING_CCS_FILE | unprobed | not probed in this run | NA | missing |
| ASSIGN_SELECTED_CURVES_TO_CCS_WING | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_COORDINATE_SYSTEM | unprobed | not probed in this run | NA | missing |
| EDIT_COORDINATE_SYSTEM | unprobed | not probed in this run | NA | missing |
| SET_COORDINATE_SYSTEM_ORIGIN | unprobed | not probed in this run | NA | missing |
| SET_COORDINATE_SYSTEM_AXIS | unprobed | not probed in this run | NA | missing |
| ROTATE_COORDINATE_SYSTEM | unprobed | not probed in this run | NA | missing |
| SET_COORDINATE_SYSTEM_NAME | unprobed | not probed in this run | NA | missing |
| NORMALIZE_COORDINATE_SYSTEM | unprobed | not probed in this run | NA | missing |
| TRANSLATE_COORDINATE_SYSTEM | unprobed | not probed in this run | NA | missing |
| DUPLICATE_COORDINATE_SYSTEM | unprobed | not probed in this run | NA | missing |
| MIRROR_COORDINATE_SYSTEM | unprobed | not probed in this run | NA | missing |
| DELETE_COORDINATE_SYSTEM | unprobed | not probed in this run | NA | missing |
| OPEN | unprobed | not probed in this run | NA | missing |
| SAVEAS | unprobed | not probed in this run | NA | missing |
| NEW_SIMULATION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved session after NEW_SIMULATION is smaller than its before-state; a before-state below 100 kB is inconclusive | the saved session after NEW_SIMULATION is smaller than its before-state; a before-state below 100 kB is inconclusive | missing |
| CLOSE_FLIGHTSTREAM | unprobed | not probed in this run | NA | missing |
| EXPORT_LOG | unprobed | not probed in this run | NA | missing |
| OUTPUT_SETTINGS_AND_STATUS | unprobed | not probed in this run | NA | missing |
| CLEAR_LOG | unprobed | not probed in this run | NA | missing |
| OUTPUT_SURFACE_INDICES | unprobed | not probed in this run | NA | missing |
| CREATE_FREE_SURFACE_TFI_MESH | broken | script processing aborted at the command: the log exported before it exists, the one after it never appeared (END sentinel missing); the solver said: ERROR \| Scripting \| N/A \| Error in script '<probe folder>\probe_script.txt' at line 12: 'CREATE_FREE_SURFACE_TFI_MESH 0.5 -1.0 3.0 2.0 20 10' \| Review command s | NA | missing |
| FREE_SURFACE_EXPORT_TYPE | unprobed | the probe prelude did not reach the BEGIN sentinel although the baseline passed; the target was not judged. Inspect the prelude and its support commands (return code 0). ERROR \| Scripting \| N/A \| Error in script '<probe folder>\probe_script.txt' at line 6: 'CREATE_FREE_SURFACE_TFI_MESH 0.5 -1.0 3.0 2.0 20 10' \| Review command sy | NA | missing |
| DELETE_FREE_SURFACE | unprobed | the probe prelude did not reach the BEGIN sentinel although the baseline passed; the target was not judged. Inspect the prelude and its support commands (return code 0). ERROR \| Scripting \| N/A \| Error in script '<probe folder>\probe_script.txt' at line 6: 'CREATE_FREE_SURFACE_TFI_MESH 0.5 -1.0 3.0 2.0 20 10' \| Review command sy | NA | missing |
| CREATE_NEW_INLET | unprobed | not probed in this run | NA | missing |
| SET_INLET_CUSTOM_PROFILE | unprobed | not probed in this run | NA | missing |
| REMESH_INLET | unprobed | not probed in this run | NA | missing |
| DELETE_INLET | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_OUTLET | unprobed | not probed in this run | NA | missing |
| REMESH_OUTLET | unprobed | not probed in this run | NA | missing |
| DELETE_OUTLET | unprobed | not probed in this run | NA | missing |
| IMPORT | unprobed | not probed in this run | NA | missing |
| CCS_IMPORT | unprobed | not probed in this run | NA | missing |
| EXPORT_SURFACE_MESH | unprobed | not probed in this run | NA | missing |
| DELETE_SURFACES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved boundary inventory after the command is the inventory before it without its first boundary, the rest renumbered. The instrument read: inventory before ('Wing',), after () | the saved boundary inventory after the command is the inventory before it without its first boundary, the rest renumbered | inventory before ('Wing',), after () |
| TRANSLATE_SURFACE_IN_FRAME | unprobed | not probed in this run | NA | missing |
| TRANSLATE_SURFACE_BY_FRAME | unprobed | not probed in this run | NA | missing |
| SURFACE_SCALE | unprobed | not probed in this run | NA | missing |
| SURFACE_MIRROR | unprobed | not probed in this run | NA | missing |
| SURFACE_LINEAR_COPY_PASTE | unprobed | not probed in this run | NA | missing |
| SURFACE_CIRCULAR_COPY_PASTE | unprobed | not probed in this run | NA | missing |
| SURFACE_SELECT_BY_ID | unprobed | not probed in this run | NA | missing |
| SURFACE_SELECT_BY_THRESHOLD | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_SURFACE_FROM_SELECTION | unprobed | not probed in this run | NA | missing |
| SURFACE_CUT_BY_PLANE | unprobed | not probed in this run | NA | missing |
| SURFACE_COMBINE | unprobed | not probed in this run | NA | missing |
| SURFACE_AUTO_HOLE_FILL | unprobed | not probed in this run | NA | missing |
| SURFACE_INVERT | unprobed | not probed in this run | NA | missing |
| SURFACE_RENAME | unprobed | not probed in this run | NA | missing |
| DELETE_SELECTED_FACES | unprobed | not probed in this run | NA | missing |
| DELETE_DEGENERATE_FACES | unprobed | not probed in this run | NA | missing |
| SELECT_MESH_NODE | unprobed | not probed in this run | NA | missing |
| TRANSFORM_SELECTED_NODES | unprobed | not probed in this run | NA | missing |
| ROTATE_SURFACE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: rotating every surface about the global frame changes the saved mesh | rotating every surface about the global frame changes the saved mesh | missing |
| BOOLEAN_UNITE_PATH | unprobed | not probed in this run | NA | missing |
| BOOLEAN_UNITE_MESH | unprobed | not probed in this run | NA | missing |
| WRAPPER_SET_INPUT | unprobed | not probed in this run | NA | missing |
| WRAPPER_SET_GLOBAL_SIZE | unprobed | not probed in this run | NA | missing |
| WRAPPER_SET_VERTEX_PROJECTION | unprobed | not probed in this run | NA | missing |
| WRAPPER_SET_ANISOTROPY | unprobed | not probed in this run | NA | missing |
| WRAPPER_CREATE_LOCAL_CONTROL | unprobed | not probed in this run | NA | missing |
| WRAPPER_EDIT_LOCAL_CONTROL | unprobed | not probed in this run | NA | missing |
| WRAPPER_DELETE_ALL_LOCAL_CONTROLS | unprobed | not probed in this run | NA | missing |
| WRAPPER_NEW_VOLUME_CONTROL | unprobed | not probed in this run | NA | missing |
| WRAPPER_DELETE_ALL_VOLUME_CONTROLS | unprobed | not probed in this run | NA | missing |
| WRAPPER_EXECUTE | unprobed | not probed in this run | NA | missing |
| WRAPPER_TRANSFER | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_MOTION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: motions are unnamed and stored in binary form (recon-checked); no instrument observes them yet | motions are unnamed and stored in binary form (recon-checked); no instrument observes them yet | missing |
| SET_MOTION_BOUNDARIES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: motion boundary lists are stored in binary form; no instrument yet | motion boundary lists are stored in binary form; no instrument yet | missing |
| SET_MOTION_MOVING_FRAMES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: motion frame lists are stored in binary form; no instrument yet | motion frame lists are stored in binary form; no instrument yet | missing |
| SET_MOTION_COORDINATE_SYSTEM | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored motion frame binding itself is not read back | the saved simulation differs after the command; the stored motion frame binding itself is not read back | missing |
| SET_MOTION_START_TIME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation changes across the motion start time (the line also survives reopening the saved file, 26.124, L4 X-F-0163) | the saved simulation changes across the motion start time (the line also survives reopening the saved file, 26.124, L4 X-F-0163) | missing |
| SET_MOTION_ROTOR_AXIS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the rotor axis is stored in binary form; no instrument yet | the rotor axis is stored in binary form; no instrument yet | missing |
| SET_MOTION_ROTOR_RPM | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the rotor rpm is stored in binary form; no instrument yet | the rotor rpm is stored in binary form; no instrument yet | missing |
| SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: DISABLE after ENABLE changes the saved simulation, which stores the key (the one-line difference measured by RPT-096) | DISABLE after ENABLE changes the saved simulation, which stores the key (the one-line difference measured by RPT-096) | missing |
| SET_MOTION_FSI_EXECUTABLE | unprobed | not probed in this run | NA | missing |
| SET_MOTION_FSI_STRUCTURAL_NODES | unprobed | not probed in this run | NA | missing |
| DELETE_MOTION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: motions are unnamed in the saved file, so deletion is not discriminated yet | motions are unnamed in the saved file, so deletion is not discriminated yet | missing |
| SET_MOTION_MASS_PROPERTIES | unprobed | not probed in this run | NA | missing |
| SET_MOTION_GRAVITY | unprobed | not probed in this run | NA | missing |
| SET_MOTION_CUSTOM_TABLE | unprobed | not probed in this run | NA | missing |
| SET_MOTION_6DOF_INITIAL_VELOCITY | unprobed | not probed in this run | NA | missing |
| SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY | unprobed | not probed in this run | NA | missing |
| SET_MOTION_6DOF_ACTIVE_VARIABLES | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_6DOF_EXTERNAL_FORCE | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_6DOF_CUSTOM_FORCE | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_6DOF_SPRING_FORCE | unprobed | not probed in this run | NA | missing |
| DELETE_6DOF_EXTERNAL_FORCE | unprobed | not probed in this run | NA | missing |
| SET_6DOF_MOTION_SYMMETRY_LOADS | unprobed | not probed in this run | NA | missing |
| EXPORT_6DOF_TRAJECTORY | unprobed | not probed in this run | NA | missing |
| SET_PLOT_TYPE | unprobed | not probed in this run | NA | missing |
| SAVE_PLOT_TO_FILE | unprobed | not probed in this run | NA | missing |
| NEW_PROBE_POINT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export lists the distinctive point coordinate 0.1234E+01 | the probe export lists the distinctive point coordinate 0.1234E+01 | missing |
| NEW_PROBE_LINE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export counts exactly the 3 requested line points | the probe export counts exactly the 3 requested line points | missing |
| UPDATE_PROBE_POINTS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the probe export may refresh; the stored points do not move | the probe export may refresh; the stored points do not move | missing |
| PROBE_POINTS_IMPORT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export counts exactly the 2 imported lattice points | the probe export counts exactly the 2 imported lattice points | missing |
| EXPORT_PROBE_POINTS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export file the command names exists and is not empty | the probe export file the command names exists and is not empty | missing |
| DELETE_PROBE_POINTS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export counts 0 points after the prelude created one | the probe export counts 0 points after the prelude created one | missing |
| SOLVER_SET_AOA | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive angle of attack 7.253 deg | the settings sheet reports the distinctive angle of attack 7.253 deg | missing |
| SOLVER_SET_SIDESLIP | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive side-slip 3.414 deg | the settings sheet reports the distinctive side-slip 3.414 deg | missing |
| SOLVER_SET_VELOCITY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive free-stream velocity 51.617 m/s | the settings sheet reports the distinctive free-stream velocity 51.617 m/s | missing |
| SOLVER_SET_MACH_NUMBER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the initialized settings dump reports the distinctive Mach number .213 | the initialized settings dump reports the distinctive Mach number .213 | missing |
| SOLVER_SET_ITERATIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive iteration count 123 | the settings sheet reports the distinctive iteration count 123 | missing |
| SOLVER_SET_CONVERGENCE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive convergence limit 2.718E-04 | the settings sheet reports the distinctive convergence limit 2.718E-04 | missing |
| SOLVER_SET_FORCED_ITERATIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports forced iterations as T | the settings sheet reports forced iterations as T | missing |
| SOLVER_SET_REF_VELOCITY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive reference velocity 47.513 m/s | the settings sheet reports the distinctive reference velocity 47.513 m/s | missing |
| SOLVER_SET_REF_MACH_NUMBER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the initialized settings dump reports the distinctive reference Mach .157 | the initialized settings dump reports the distinctive reference Mach .157 | missing |
| SOLVER_SET_REF_AREA | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive reference area 2.727 m^2 | the settings sheet reports the distinctive reference area 2.727 m^2 | missing |
| SOLVER_SET_REF_LENGTH | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive reference length 3.131 m | the settings sheet reports the distinctive reference length 3.131 m | missing |
| SET_MAX_PARALLEL_THREADS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored thread count itself is not read back | the saved simulation differs after the command; the stored thread count itself is not read back | missing |
| SET_SCENE_COLORMAP_TYPE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_COLORMAP_SIZE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_COLORMAP_POSITION | unprobed | not probed in this run | NA | missing |
| SET_SCENE_COLORMAP_SHADING | unprobed | not probed in this run | NA | missing |
| SET_SCENE_COLORMAP_CUSTOM_MODE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_COLORMAP_CUSTOM_RANGE | unprobed | not probed in this run | NA | missing |
| VIEW_RESIZE | unprobed | not probed in this run | NA | missing |
| CHANGE_SCENE_TO_CAD | unprobed | not probed in this run | NA | missing |
| CHANGE_SCENE_TO_GEOMETRY | unprobed | not probed in this run | NA | missing |
| CHANGE_SCENE_TO_SOLVER | unprobed | not probed in this run | NA | missing |
| CHANGE_SCENE_TO_PLOTS | unprobed | not probed in this run | NA | missing |
| SAVE_SCENE_AS_IMAGE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_DEFAULTVIEW | unprobed | not probed in this run | NA | missing |
| SET_SCENE_XY_POSITIVE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_XY_NEGATIVE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_XZ_POSITIVE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_XZ_NEGATIVE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_YZ_POSITIVE | unprobed | not probed in this run | NA | missing |
| SET_SCENE_YZ_NEGATIVE | unprobed | not probed in this run | NA | missing |
| STOP | unprobed | not probed in this run | NA | missing |
| PRINT | unprobed | not probed in this run | NA | missing |
| RUN_SCRIPT | unprobed | not probed in this run | NA | missing |
| SET_SIMULATION_LENGTH_UNITS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the initialized settings dump reports lengths in cm | the initialized settings dump reports lengths in cm | missing |
| SET_SIGNIFICANT_DIGITS | unprobed | not probed in this run | NA | missing |
| SET_TRAILING_EDGE_SWEEP_ANGLE | unprobed | not probed in this run | NA | missing |
| SET_VERTEX_MERGE_TOLERANCE | unprobed | not probed in this run | NA | missing |
| SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE | unprobed | not probed in this run | NA | missing |
| SET_VORTICITY_DRAG_BOUNDARIES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored vorticity-drag list itself is not read back | the saved simulation differs after the command; the stored vorticity-drag list itself is not read back | missing |
| DELETE_VORTICITY_DRAG_BOUNDARIES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the vorticity-drag boundary list is not exposed by any instrument yet | the vorticity-drag boundary list is not exposed by any instrument yet | missing |
| SET_SOLVER_ANALYSIS_LOADS_FRAME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet exported after the solve reports the analysis frame set before it, by its probe-given name PYFS_FRAME_NAME | the settings sheet exported after the solve reports the analysis frame set before it, by its probe-given name PYFS_FRAME_NAME | missing |
| SET_ANALYSIS_MOMENTS_MODEL | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored moments-model choice itself is not read back | the saved simulation differs after the command; the stored moments-model choice itself is not read back | missing |
| SET_ANALYSIS_SYMMETRY_LOADS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the symmetry-loads toggle is not exposed by any instrument yet; probed pre-solve because the in-solve monitors consume it | the symmetry-loads toggle is not exposed by any instrument yet; probed pre-solve because the in-solve monitors consume it | missing |
| SET_LOADS_AND_MOMENTS_UNITS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet footer reports the force units as Newtons | the settings sheet footer reports the force units as Newtons | missing |
| SET_SOLVER_ANALYSIS_BOUNDARIES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved simulation does not move (RPT-020); every boundary appears to be selected already, so setting all of them changes nothing to observe | the saved simulation does not move (RPT-020); every boundary appears to be selected already, so setting all of them changes nothing to observe | missing |
| SET_INVISCID_LOADS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the viscous drag column (field 6, CDo or CDv by build) of the loads exported after enabling inviscid-only reads exactly zero (nonzero by default on this run) | the viscous drag column (field 6, CDo or CDv by build) of the loads exported after enabling inviscid-only reads exactly zero (nonzero by default on this run) | missing |
| SET_VORTICITY_LIFT_MODEL | removed | the solver refused the name as an unrecognised command, so this build does not carry it; measured, not read off an edition's silence | NA | missing |
| SET_SCENE_CONTOUR | unprobed | not probed in this run | NA | missing |
| EXPORT_SOLVER_ANALYSIS_SPREADSHEET | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty | the export file the command names exists and is not empty | missing |
| EXPORT_SOLVER_ANALYSIS_TECPLOT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty | the export file the command names exists and is not empty | missing |
| EXPORT_SOLVER_ANALYSIS_VTK | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty | the export file the command names exists and is not empty | missing |
| SET_VTK_EXPORT_VARIABLES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the VTK exported afterwards carries the selected CP_REFERENCE variable | the VTK exported afterwards carries the selected CP_REFERENCE variable | missing |
| EXPORT_SOLVER_ANALYSIS_CSV | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty | the export file the command names exists and is not empty | missing |
| EXPORT_SOLVER_ANALYSIS_PLOAD_BDF | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty | the export file the command names exists and is not empty | missing |
| EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty | the export file the command names exists and is not empty | missing |
| EXPORT_BL_VELOCITY_PROFILE | unprobed | not probed in this run | NA | missing |
| DELETE_BL_VELOCITY_PROFILE | unprobed | not probed in this run | NA | missing |
| INITIALIZE_SOLVER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the log reports 'Solver initialized' with the mesh statistics | the log reports 'Solver initialized' with the mesh statistics | missing |
| SOLVER_PROXIMAL_BOUNDARIES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored proximal-boundary marking itself is not read back | the saved simulation differs after the command; the stored proximal-boundary marking itself is not read back | missing |
| REMOVE_INITIALIZATION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings dump flips from the initialized solver state to 'Not initialized' | the settings dump flips from the initialized solver state to 'Not initialized' | missing |
| START_SOLVER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the log carries the iteration table and 'Solver run time' | the log carries the iteration table and 'Solver run time' | missing |
| CLEAR_SOLUTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the solver iteration counter back at 0 | the settings sheet reports the solver iteration counter back at 0 | missing |
| SET_SOLVER_STEADY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports Steady after the prelude set the unsteady mode | the settings sheet reports Steady after the prelude set the unsteady mode | missing |
| SET_SOLVER_UNSTEADY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive time increment .012 s | the settings sheet reports the distinctive time increment .012 s | missing |
| SET_BOUNDARY_LAYER_TYPE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored boundary-layer model choice itself is not read back | the saved simulation differs after the command; the stored boundary-layer model choice itself is not read back | missing |
| SET_SOLVER_VISCOUS_COUPLING | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored viscous-coupling choice itself is not read back | the saved simulation differs after the command; the stored viscous-coupling choice itself is not read back | missing |
| SET_VISCOUS_EXCLUDED_BOUNDARIES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation differs after the command; the stored viscous exclusion list itself is not read back | the saved simulation differs after the command; the stored viscous exclusion list itself is not read back | missing |
| DELETE_VISCOUS_EXCLUDED_BOUNDARIES | unprobed | not probed in this run | NA | missing |
| CREATE_AIRFOIL_SEPARATION | unprobed | not probed in this run | NA | missing |
| CREATE_AXIAL_VORTEX_SEPARATION | unprobed | not probed in this run | NA | missing |
| CREATE_CYLINDRICAL_BULK_SEPARATION | unprobed | not probed in this run | NA | missing |
| CREATE_STRATFORD_BULK_SEPARATION | unprobed | not probed in this run | NA | missing |
| DELETE_SEPARATION | unprobed | not probed in this run | NA | missing |
| SET_SURFACE_ROUGHNESS | unprobed | not probed in this run | NA | missing |
| SET_THIN_BOUNDARIES | unprobed | not probed in this run | NA | missing |
| DELETE_THIN_BOUNDARIES | unprobed | not probed in this run | NA | missing |
| SOLVER_STABILIZATION | unprobed | not probed in this run | NA | missing |
| DISABLE_SOLVER_REF_VELOCITY | unprobed | not probed in this run | NA | missing |
| STABILITY_TOOLBOX_SETTINGS | unprobed | not probed in this run | NA | missing |
| STABILITY_TOOLBOX_NEW_COEFFICIENT | unprobed | not probed in this run | NA | missing |
| STABILITY_TOOLBOX_DELETE_ALL | unprobed | not probed in this run | NA | missing |
| COMPUTE_STABILITY_COEFFICIENTS | unprobed | not probed in this run | NA | missing |
| STABILITY_TOOLBOX_EXPORT | unprobed | not probed in this run | NA | missing |
| STABILITY_TOOLBOX_ANGLE_INCREMENT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across the angle step; a still file records unprobed | the saved simulation moves across the angle step; a still file records unprobed | missing |
| NEW_OFF_BODY_STREAMLINE | broken | script processing aborted at the command: the log exported before it exists, the one after it never appeared (END sentinel missing); the solver said: ERROR \| Scripting \| N/A \| Error in script '<probe folder>\probe_script.txt' at line 24: 'NEW_OFF_BODY_STREAMLINE' \| Review command syntax and arguments. | NA | missing |
| NEW_STREAMLINE_DISTRIBUTION | broken | script processing aborted at the command: the log exported before it exists, the one after it never appeared (END sentinel missing) | NA | missing |
| GENERATE_ALL_OFF_BODY_STREAMLINES | unprobed | the probe prelude did not reach the BEGIN sentinel although the baseline passed; the target was not judged. Inspect the prelude and its support commands (return code 0). ERROR \| Scripting \| N/A \| Error in script '<probe folder>\probe_script.txt' at line 20: 'NEW_STREAMLINE_DISTRIBUTION' \| Review command syntax and arguments. | NA | missing |
| EXPORT_ALL_OFF_BODY_STREAMLINES | unprobed | the probe prelude did not reach the BEGIN sentinel although the baseline passed; the target was not judged. Inspect the prelude and its support commands (return code 0). ERROR \| Scripting \| N/A \| Error in script '<probe folder>\probe_script.txt' at line 20: 'NEW_STREAMLINE_DISTRIBUTION' \| Review command syntax and arguments. | NA | missing |
| NEW_OFF_BODY_STREAMTUBE | unprobed | not probed in this run | NA | missing |
| SET_OFF_BODY_STREAMLINE_LENGTH | unprobed | not probed in this run | NA | missing |
| SET_ALL_OFF_BODY_STREAMLINES_UPSTREAM | unprobed | not probed in this run | NA | missing |
| SET_ALL_OFF_BODY_STREAMLINES_DOWNSTREAM | unprobed | not probed in this run | NA | missing |
| DELETE_ALL_OFF_BODY_STREAMLINES | unprobed | not probed in this run | NA | missing |
| GENERATE_ALL_SURFACE_STREAMLINES | unprobed | not probed in this run | NA | missing |
| DELETE_ALL_SURFACE_STREAMLINES | unprobed | not probed in this run | NA | missing |
| EXPORT_ALL_SURFACE_STREAMLINES | unprobed | not probed in this run | NA | missing |
| CREATE_NEW_SURFACE_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the all-sections export written afterwards carries the created section | the all-sections export written afterwards carries the created section | missing |
| NEW_SURFACE_SECTION_DISTRIBUTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the all-sections export written afterwards carries the distribution | the all-sections export written afterwards carries the distribution | missing |
| COMPUTE_SURFACE_SECTIONAL_LOADS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sectional-loads export written afterwards carries computed loads | the sectional-loads export written afterwards carries computed loads | missing |
| EXPORT_SURFACE_SECTIONAL_LOADS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sectional-loads file the command names exists and is not empty | the sectional-loads file the command names exists and is not empty | missing |
| UPDATE_ALL_SURFACE_SECTIONS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the sections export may refresh on its own, so it cannot discriminate the update command; needs a dedicated instrument | the sections export may refresh on its own, so it cannot discriminate the update command; needs a dedicated instrument | missing |
| EXPORT_ALL_SURFACE_SECTIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the all-sections file the command names exists and is not empty | the all-sections file the command names exists and is not empty | missing |
| EXPORT_SURFACE_SECTIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the solver adds the requested section export to its working folder; silence records unprobed. The instrument read: files added to the working folder: logs, section_1.txt | the solver adds the requested section export to its working folder; silence records unprobed | files added to the working folder: logs, section_1.txt |
| DELETE_SURFACE_SECTION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the surviving-section listing format is not pinned yet, so deletion is not discriminated; needs a dedicated instrument | the surviving-section listing format is not pinned yet, so deletion is not discriminated; needs a dedicated instrument | missing |
| DELETE_ALL_SURFACE_SECTIONS | unprobed | not probed in this run | NA | missing |
| SWEEPER_SET_AOA_SWEEP | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sweep spreadsheet carries both requested angles 2.000 and 4.000 | the sweep spreadsheet carries both requested angles 2.000 and 4.000 | missing |
| SWEEPER_SET_BETA_SWEEP | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sweep spreadsheet carries both requested side-slips 1.500 and 3.500 | the sweep spreadsheet carries both requested side-slips 1.500 and 3.500 | missing |
| SWEEPER_SET_VELOCITY_SWEEP | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: only the DISABLE form is probed (the CUSTOM velocity list file format awaits a manual pass); the disabled state leaves no observable trace | only the DISABLE form is probed (the CUSTOM velocity list file format awaits a manual pass); the disabled state leaves no observable trace | missing |
| SWEEPER_SET_MACH_SWEEP | unprobed | not probed in this run | NA | missing |
| SWEEPER_POST_RUN_SCRIPT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the post-run script's message PYFS_POSTRUN appears in the log after the sweep | the post-run script's message PYFS_POSTRUN appears in the log after the sweep | missing |
| SWEEPER_CLEAR_SOLUTION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the sweeper clear-solution toggle is not exposed by any instrument yet | the sweeper clear-solution toggle is not exposed by any instrument yet | missing |
| SWEEPER_START | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sweep run prints the solver iteration table and run time | the sweep run prints the solver iteration table and run time | missing |
| SWEEPER_EXPORT_SPREADSHEET | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sweep spreadsheet the command names exists and is not empty | the sweep spreadsheet the command names exists and is not empty | missing |
| RESET_SOLVER_SWEEPER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across the reset of a configured angle sweep; a still file records unprobed | the saved simulation moves across the reset of a configured angle sweep; a still file records unprobed | missing |
| DELETE_TRANSITION_TRIP | unprobed | not probed in this run | NA | missing |
| UNSTEADY_SOLVER_NEW_FORCE_PLOT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the plots file exported after the unsteady solve carries the CL plot by name | the plots file exported after the unsteady solve carries the CL plot by name | missing |
| UNSTEADY_SOLVER_NEW_FLUID_PLOT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the plots file exported after the unsteady solve carries the fluid plot by name | the plots file exported after the unsteady solve carries the fluid plot by name | missing |
| UNSTEADY_SOLVER_DELETE_ALL_PLOTS | unprobed | not probed in this run | NA | missing |
| UNSTEADY_SOLVER_EXPORT_PLOTS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the plots file the command names exists and is not empty after an unsteady solve | the plots file the command names exists and is not empty after an unsteady solve | missing |
| NEW_UNSTEADY_SOLVER_SURFACE_PROBE | unprobed | not probed in this run | NA | missing |
| UNSTEADY_SOLVER_ANIMATION | unprobed | not probed in this run | NA | missing |
| SET_NEW_UNSTEADY_SOLVER_ACTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the message the registered script prints appears in the log after the unsteady solve, so the solver ran the action; silence records unprobed | the message the registered script prints appears in the log after the unsteady solve, so the solver ran the action; silence records unprobed | missing |
| ENABLE_SOLVER_TIME_AVERAGING | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across the command under an unsteady state of three steps; a still file records unprobed. Killed after a minute, since the command it replaces hung 26.124 (C01) | the saved simulation moves across the command under an unsteady state of three steps; a still file records unprobed. Killed after a minute, since the command it replaces hung 26.124 (C01) | missing |
| DISABLE_SOLVER_TIME_AVERAGING | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across the command after the averaging was enabled; a still file records unprobed | the saved simulation moves across the command after the averaging was enabled; a still file records unprobed | missing |
| CREATE_NEW_RECTANGLE_VOLUME_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: exporting volume section 1 afterwards succeeds, so the section exists | exporting volume section 1 afterwards succeeds, so the section exists | missing |
| CREATE_NEW_CIRCLE_VOLUME_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: exporting volume section 1 afterwards succeeds, so the section exists | exporting volume section 1 afterwards succeeds, so the section exists | missing |
| UPDATE_ALL_VOLUME_SECTIONS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the section export may refresh on its own, so it cannot discriminate the update command; needs a dedicated instrument | the section export may refresh on its own, so it cannot discriminate the update command; needs a dedicated instrument | missing |
| EXPORT_VOLUME_SECTION_VTK | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the VTK file the command names exists and is not empty | the VTK file the command names exists and is not empty | missing |
| EXPORT_VOLUME_SECTION_TECPLOT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the Tecplot file the command names exists and is not empty | the Tecplot file the command names exists and is not empty | missing |
| DELETE_VOLUME_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: of two sections, exporting index 1 after deleting section 1 holds the section at the second offset: the survivor is renumbered to 1 (exporting index 2 aborts) | of two sections, exporting index 1 after deleting section 1 holds the section at the second offset: the survivor is renumbered to 1 (exporting index 2 aborts) | missing |
| DELETE_ALL_VOLUME_SECTIONS | unprobed | not probed in this run | NA | missing |
| VOLUME_SECTION_WIREFRAME | unprobed | not probed in this run | NA | missing |
| EXPORT_VOLUME_SECTION_2D_VTK | unprobed | not probed in this run | NA | missing |
