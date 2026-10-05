# Compat report: FlightStream 26.125 (2026-10-05)

Tier 2 command-validity evidence produced by the probe harness
(`pyfs-qa probe`); one evidence line per database command of this
version. Database statuses are promoted from this report only
through `pyfs-qa apply-compat`, never edited by hand (CONTRIBUTING.md
invariant 3). Probe scripts and logs are local scratch; this
report is the committed evidence.

## Setup

| Item | Value |
|---|---|
| Executable | Flightstream_26125.exe (sha256 withheld; build 10052026, local, `_private/exe/`, never committed) |
| Executor | GatedExecutor, `-hidden -script` (as run; mechanism SRC-003 pp.279-280; argument spelling RPT-023) |
| Package | pyflightstream 0.35.1 |
| Solver identity lines | Simcenter Flightstream 2612, build #10052026 |

## Summary

141 verified, 2 broken, 0 removed, 236 unprobed.

## Evidence per command

| Command | Outcome | Evidence |
|---|---|---|
| ACOUSTIC_SOURCES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals exported after a marched rotor carry nonzero pressures with the sources enabled. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| CREATE_NEW_ACOUSTIC_OBSERVER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals file holds an observer block named for the observer created. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| ACOUSTIC_OBSERVERS_IMPORT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals file holds the two observers read from the observer file, named by index. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| DELETE_ACOUSTIC_OBSERVER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: of the two observers created, exactly one is left in the signals file (the manual counts the index in the application's own tree). The instrument read: 1 observer blocks, rows per block [16], 0 nonzero pressure values |
| DELETE_ALL_ACOUSTIC_OBSERVERS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals file holds no observer block after both observers were deleted. The instrument read: 0 observer blocks, rows per block [], 0 nonzero pressure values |
| SET_ACOUSTIC_OBSERVER_TIME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: every observer block of the signals file has 16 rows and starts at the requested time. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| COMPUTE_ACOUSTIC_SIGNALS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals exported after the computation carry data rows. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| EXPORT_ACOUSTIC_SIGNALS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the signals file the command names exists and holds observer blocks. The instrument read: 3 observer blocks, rows per block [16, 16, 16], 96 nonzero pressure values |
| CREATE_ACOUSTIC_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the section's storage folder holds files after the section is created on a computed solution. The instrument read: 16 files in the section storage folder |
| CREATE_NEW_ACTUATOR | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the actuator name is readable in the saved simulation file |
| SET_ACTUATOR_NAME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the new actuator name is readable in the saved simulation file |
| SET_ACTUATOR_AXIS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive axis offset 0.6622 |
| SET_ACTUATOR_RADIUS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries both distinctive radii, 1.234 tip and 0.321 hub |
| SET_PROP_ACTUATOR_RPM | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive rpm 3456.7 |
| SET_PROP_ACTUATOR_PROFILE | unprobed | not probed in this run |
| SET_PROP_ACTUATOR_THRUST | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the actuator thrust is stored in binary form; no instrument yet |
| SET_PROP_ACTUATOR_SWIRL | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive swirl fraction 0.777 |
| ENABLE_ACTUATOR | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved simulation does not move when an actuator is enabled (RPT-020); an actuator appears to be enabled already when created, so the state instrument cannot separate the two |
| DELETE_ACTUATOR | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the deleted actuator's name is no longer readable in the saved simulation file |
| SET_ACTUATOR_WAKE_TYPE | unprobed | not probed in this run |
| SET_SOLVER_CONVERGENCE_ITERATIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive convergence window 37. The value is 37 rather than the 7 this probe used before instruments reached it: a single digit matches somewhere in any simulation file |
| SOLVER_MINIMUM_CP | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive minimum-Cp floor |
| REYNOLDS_AVERAGED_DRAG_FORCES | unprobed | not probed in this run |
| SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY | unprobed | not probed in this run |
| SOLVER_SET_FARFIELD_LAYERS | unprobed | not probed in this run |
| SOLVER_UNSTEADY_PRESSURE_AND_KUTTA | unprobed | not probed in this run |
| SET_WAKE_TERMINATION_TIME_STEPS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the wake termination step count, set under the unsteady mode the rotor goldens render it in |
| SET_WAKE_ON_WAKE_INDUCTION | unprobed | not probed in this run |
| ADDITIONAL_WAKE_RELAXATION_ITERATION | unprobed | not probed in this run |
| AEROELASTIC_RBF_TYPE | unprobed | not probed in this run |
| LAMINAR_SEPARATION | unprobed | not probed in this run |
| KUTTA_JOUKOWSKI_LIFT_FORCES | unprobed | not probed in this run |
| PRINT_ROTOR_INDUCED_VELOCITIES | unprobed | not probed in this run |
| SET_ADAPTIVE_FIELD_GRID_REFINEMENT | unprobed | not probed in this run |
| ROTOR_INDUCED_VELOCITY_BLENDING | unprobed | not probed in this run |
| SET_WAKE_NUMERICAL_RELAXATION | unprobed | not probed in this run |
| SET_JET_WAKE_DECAY_NORMALIZED_LENGTH | unprobed | not probed in this run |
| SET_WAKE_DECAY_CONSTANT | unprobed | not probed in this run |
| EXECUTE_AEROELASTIC_ANALYSIS | unprobed | not probed in this run |
| ASSIGN_AEROELASTIC_SURFACES | unprobed | not probed in this run |
| ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS | unprobed | not probed in this run |
| IMPORT_AEROELASTIC_STRUCTURAL_NODES | unprobed | not probed in this run |
| DELETE_AEROELASTIC_STRUCTURAL_NODES | unprobed | not probed in this run |
| SET_AEROELASTIC_WORKING_DIRECTORY | unprobed | not probed in this run |
| SET_AEROELASTIC_POST_PROCESSING_SCRIPT | unprobed | not probed in this run |
| SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND | unprobed | not probed in this run |
| SET_AEROELASTIC_ITERATIONS | unprobed | not probed in this run |
| SET_AEROELASTIC_COUPLING_IN_UNSTEADY | unprobed | not probed in this run |
| SET_AEROELASTIC_CONVERGENCE_THRESHOLD | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across a threshold a hundred times below the documented default; a still file records unprobed |
| CREATE_NEW_BASE_REGION | unprobed | not probed in this run |
| SET_BASE_REGION_CP | unprobed | not probed in this run |
| SET_BASE_REGION_BENDING_ANGLE | unprobed | not probed in this run |
| DETECT_BASE_REGIONS_BY_SURFACE | unprobed | not probed in this run |
| SET_BASE_REGION_TRAILING_EDGES | unprobed | not probed in this run |
| DELETE_BASE_REGION | unprobed | not probed in this run |
| SELECT_BASE_REGION_FACES | unprobed | not probed in this run |
| REMESH_BASE_REGION | unprobed | not probed in this run |
| SET_OUTLET_TRAILING_EDGES | unprobed | not probed in this run |
| SET_TRAILING_EDGE_TYPE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the trailing-edge type |
| DISABLE_WAKE_NODES_ON_TRAILING_EDGE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the wake-node state |
| SET_FREESTREAM | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved simulation does not move (RPT-020). The reading is that CONSTANT is the state the simulation was already in, which would make the call a no-op rather than a failure; no page has been found stating the default, so the entry carries no default_ref and this stays a hypothesis. The CUSTOM and ROTATION forms await fixtures |
| FLUID_PROPERTIES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings dump reports the distinctive density 1.179 kg/m^3 |
| AIR_ALTITUDE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings dump reports the 5000 m standard-atmosphere density (0.736 kg/m^3) |
| DETECT_TRAILING_EDGES_BY_SURFACE | unprobed | not probed in this run |
| DETECT_WAKE_TERMINATION_NODES_BY_SURFACE | unprobed | not probed in this run |
| MARK_WAKE_TERMINATION_NODES | unprobed | not probed in this run |
| DETECT_LEADING_EDGES_WAKES_BY_SURFACE | unprobed | not probed in this run |
| IMPORT_WAKE_EDGES_FROM_FILE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the solver logs one import line, 16 trailing edges imported for boundary Wing, one per trailing-edge mesh edge of the wing, and no other; it prints the line only when the import marks something (RPT-061). The instrument read: import lines [{"Wing": 16}] |
| CAD_BODY_DELETE | unprobed | not probed in this run |
| CAD_BODY_MIRROR | unprobed | not probed in this run |
| CAD_BODY_ROTATE | unprobed | not probed in this run |
| CAD_BODY_SCALE | unprobed | not probed in this run |
| CAD_BODY_TRANSLATE | unprobed | not probed in this run |
| CAD_BODY_SELECT_BY_THRESHOLD | unprobed | not probed in this run |
| IMPORT_CAD | unprobed | not probed in this run |
| CONVERT_CAD_TO_MESH | unprobed | not probed in this run |
| CAD_CREATE_INITIALIZE | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the loft that follows the initialization names its wing in the saved simulation; no instrument reads the initialization itself, so absence records unprobed |
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
| CAD_CREATE_CURVE_SELECT | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the loft that consumes the selected curves names its wing in the saved simulation |
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
| CAD_CREATE_IMPORT_CURVE_CCS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the loft that consumes the imported curves names its wing in the saved simulation |
| CAD_CREATE_IMPORT_CURVE_P3D | unprobed | not probed in this run |
| CAD_CREATE_CROSS_SECTION | unprobed | not probed in this run |
| CAD_CREATE_AUTO_CROSS_SECTIONS | unprobed | not probed in this run |
| CAD_CREATE_AUTO_ANNULAR_CROSS_SECTIONS | unprobed | not probed in this run |
| CAD_CREATE_WING_MESH_FROM_CCS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation names the lofted wing |
| CAD_CREATE_FUSELAGE_MESH_FROM_CCS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation names the lofted fuselage |
| CAD_CREATE_REVOLVE_MESH_FROM_CCS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation names the body of revolution |
| CAD_CREATE_MIRROR_CURVES | unprobed | not probed in this run |
| SET_CCS_TE_BLEND_LENGTH | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: a blended-edge wing lofted after a 40 per cent blend length has a different mesh from the same wing lofted before it at the default 10. The instrument read: reference 0 vertices 0 faces; variant 0 vertices 0 faces |
| DEFAULT_CCS_FUSELAGE_MESH_SETTINGS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: after the axial subdivisions were changed and the defaults restored, the loft equals the first loft. The instrument read: reference 1975 vertices 1896 faces; variant 2449 vertices 2370 faces; control 2449 vertices 2370 faces; restored 1975 vertices 1896 faces |
| CCS_FUSELAGE_MESH_SUBDIVISIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a fuselage lofted after 30 axial subdivisions has a different mesh. The instrument read: reference 1975 vertices 1896 faces; variant 2449 vertices 2370 faces |
| CCS_FUSELAGE_MESH_GROWTH_SCHEME | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: a fuselage lofted after a successive axial growth scheme has a different mesh. The instrument read: reference 1975 vertices 1896 faces; variant 1975 vertices 1896 faces |
| CCS_FUSELAGE_MESH_GROWTH_RATE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a fuselage lofted after a axial growth rate of 1.2 has a different mesh. The instrument read: reference 1975 vertices 1896 faces; variant 1975 vertices 1896 faces |
| CCS_FUSELAGE_MESH_PERIODICITY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a fuselage lofted after a radial periodicity of 2 has a different mesh. The instrument read: reference 1975 vertices 1896 faces; variant 1872 vertices 1794 faces |
| NEW_CCS_FUSELAGE_REFINEMENT_ZONE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a fuselage lofted after a refinement zone has a different mesh. The instrument read: reference 1975 vertices 1896 faces; variant 2844 vertices 2765 faces |
| DELETE_CCS_FUSELAGE_REFINEMENT_ZONES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: after a refinement zone was added and deleted, the loft equals the first loft. The instrument read: reference 1975 vertices 1896 faces; variant 2844 vertices 2765 faces; control 2844 vertices 2765 faces; restored 1975 vertices 1896 faces |
| NEW_CCS_FUSELAGE_RELAXED_TE | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: a fuselage lofted after a relaxed trailing edge has a different mesh. The instrument read: reference 1975 vertices 1896 faces; variant 1975 vertices 1896 faces. Re-probed the same day with the form SRC-753 prints; the first pass emitted the three-token line of 26.124 (no DIRECTION) and the script aborted at it |
| DELETE_CCS_FUSELAGE_RELAXED_TE | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved per-face state returns to the reference after relaxed trailing-edge deletion, while an unchanged control retains the modification and all four geometries agree. The instrument read: reference 1975 vertices 1896 faces; variant 1975 vertices 1896 faces; control 1975 vertices 1896 faces; restored 1975 vertices 1896 faces; saved mesh state: reference read, variant read, control read, restored read; control equals modified: False; restored equals reference: False. Re-probed the same day with the form SRC-753 prints; the first pass did not reach it, its precondition having aborted |
| EXPORT_FUSELAGE_CCS_FILE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the CCS file the command names exists and is not empty, written from the six arguments of the signature heading. The instrument read: fuselage_export.csv written, 18255 bytes, 10 lines, first line 'Aircraft;CCS' |
| ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the loft after the assignment names its fuselage in the saved simulation |
| DEFAULT_CCS_REVOLVE_MESH_SETTINGS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: after the axial subdivisions were changed and the defaults restored, the loft equals the first loft. The instrument read: reference 4584 vertices 4661 faces; variant 2293 vertices 2370 faces; control 2293 vertices 2370 faces; restored 4584 vertices 4661 faces |
| CCS_REVOLVE_MESH_SUBDIVISIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a revolve lofted after 30 axial subdivisions has a different mesh. The instrument read: reference 4584 vertices 4661 faces; variant 2293 vertices 2370 faces |
| CCS_REVOLVE_MESH_GROWTH_SCHEME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a revolve lofted after a successive axial growth scheme has a different mesh. The instrument read: reference 4584 vertices 4661 faces; variant 4584 vertices 4661 faces |
| CCS_REVOLVE_MESH_GROWTH_RATE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a revolve lofted after a axial growth rate of 1.2 has a different mesh. The instrument read: reference 4584 vertices 4661 faces; variant 4584 vertices 4661 faces |
| CCS_REVOLVE_MESH_PERIODICITY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a revolve lofted after a azimuth periodicity of 2 has a different mesh. The instrument read: reference 4584 vertices 4661 faces; variant 4526 vertices 4602 faces |
| NEW_CCS_REVOLVE_REFINEMENT_ZONE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a revolve lofted after a refinement zone has a different mesh. The instrument read: reference 4584 vertices 4661 faces; variant 5058 vertices 5135 faces |
| DELETE_CCS_REVOLVE_REFINEMENT_ZONES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: after a refinement zone was added and deleted, the loft equals the first loft. The instrument read: reference 4584 vertices 4661 faces; variant 5058 vertices 5135 faces; control 5058 vertices 5135 faces; restored 4584 vertices 4661 faces |
| NEW_CCS_REVOLVE_RELAXED_TE | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: a revolve lofted after a relaxed trailing edge has a different mesh. The instrument read: reference 4584 vertices 4661 faces; variant 4584 vertices 4661 faces. Re-probed the same day with the form SRC-753 prints; the first pass emitted the three-token line of 26.124 (no DIRECTION) and the script aborted at it |
| DELETE_CCS_REVOLVE_RELAXED_TE | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved per-face state returns to the reference after relaxed trailing-edge deletion, while an unchanged control retains the modification and all four geometries agree. The instrument read: reference 4584 vertices 4661 faces; variant 4584 vertices 4661 faces; control 4584 vertices 4661 faces; restored 4584 vertices 4661 faces; saved mesh state: reference read, variant read, control read, restored read; control equals modified: False; restored equals reference: False. Re-probed the same day with the form SRC-753 prints; the first pass did not reach it, its precondition having aborted |
| EXPORT_REVOLVE_CCS_FILE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the CCS file the command names exists and is not empty, written from the six arguments of the signature heading. The instrument read: revolve_export.csv written, 5526 bytes, 9 lines, first line 'Aircraft;CCS'. Re-probed the same day with the form SRC-753 prints; the first pass emitted the six-placeholder form of the page heading and the script aborted at it |
| ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the loft after the assignment names its revolved body in the saved simulation |
| NEW_CCS_WING_CONTROL_SURFACE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a wing lofted after a gapped control surface has a different mesh from the same wing lofted before it (the PARAMETRIC form of RPT-097). The instrument read: reference 1302 vertices 1108 faces; variant 743 vertices 492 faces |
| DEFAULT_CCS_WING_MESH_SETTINGS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: after the chord subdivisions were changed and the defaults restored, the loft equals the first loft. The instrument read: reference 4484 vertices 4366 faces; variant 588 vertices 560 faces; control 588 vertices 560 faces; restored 4484 vertices 4366 faces |
| CCS_WING_MESH_SUBDIVISIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a wing lofted after 30 chordwise subdivisions has a different mesh from the same wing lofted before them. The instrument read: reference 4484 vertices 4366 faces; variant 588 vertices 560 faces |
| CCS_WING_MESH_GROWTH_SCHEME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a wing lofted after a successive chord growth scheme has a different mesh. The instrument read: reference 4484 vertices 4366 faces; variant 3894 vertices 3776 faces |
| CCS_WING_MESH_GROWTH_RATE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a wing lofted after a chord growth rate of 1.2 has a different mesh. The instrument read: reference 4484 vertices 4366 faces; variant 2478 vertices 2360 faces |
| CCS_WING_MESH_PERIODICITY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a wing lofted after a span periodicity of 2 has a different mesh. The instrument read: reference 4484 vertices 4366 faces; variant 4484 vertices 4366 faces |
| NEW_CCS_WING_REFINEMENT_ZONE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a wing lofted after a refinement zone has a different mesh. The instrument read: reference 4484 vertices 4366 faces; variant 8142 vertices 8024 faces |
| DELETE_CCS_WING_REFINEMENT_ZONES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: after a refinement zone was added and deleted, the loft equals the first loft. The instrument read: reference 4484 vertices 4366 faces; variant 8142 vertices 8024 faces; control 8142 vertices 8024 faces; restored 4484 vertices 4366 faces |
| NEW_CCS_WING_MORPHING_SURFACE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a wing lofted after a morphing surface has a different mesh. The instrument read: reference 4484 vertices 4366 faces; variant 3925 vertices 3750 faces. Re-probed the same day with the form SRC-753 prints; the first pass emitted the seven-argument line of 26.124 (no SPACE, AXIS) and the script aborted at it |
| NEW_CCS_WING_FLAP_COVE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: a wing lofted after a flap cove has a different mesh. The instrument read: reference 4484 vertices 4366 faces; variant 3561 vertices 3358 faces. Re-probed the same day with the form SRC-753 prints; the first pass emitted the six-argument line of 26.124 (no SPACE, AXIS) and the script aborted at it |
| DELETE_CCS_WING_CONTROL_SURFACE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: after a control surface was added and deleted, the loft equals the first loft. The instrument read: reference 4484 vertices 4366 faces; variant 3925 vertices 3750 faces; control 3925 vertices 3750 faces; restored 4484 vertices 4366 faces |
| EXPORT_WING_CCS_FILE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the CCS file the command names exists and is not empty, written from the six arguments of the signature heading. The instrument read: wing_export.csv written, 12706 bytes, 9 lines, first line 'Aircraft;CCS' |
| ASSIGN_SELECTED_CURVES_TO_CCS_WING | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the loft after the assignment names its wing in the saved simulation |
| CREATE_NEW_COORDINATE_SYSTEM | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the epilogue names the created frame and the name is readable in the saved simulation file (via EDIT_COORDINATE_SYSTEM, whose own probe disambiguates) |
| EDIT_COORDINATE_SYSTEM | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the frame name set by the command is readable in the saved simulation file |
| SET_COORDINATE_SYSTEM_ORIGIN | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the distinctive frame origin |
| SET_COORDINATE_SYSTEM_AXIS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the axis direction 0.28, 0.96, which is stored unchanged because it is already a unit vector. THE SOLVER NORMALISES THE DIRECTION WHATEVER THE NORMALIZE FLAG SAYS: this probe first passed 0.61234, 0.79012 with the flag FALSE and the file stored that vector divided by its magnitude, to all seventeen digits (RPT-020). A unit vector is used so the value asserted is the value passed |
| ROTATE_COORDINATE_SYSTEM | unprobed | not probed in this run |
| SET_COORDINATE_SYSTEM_NAME | unprobed | not probed in this run |
| NORMALIZE_COORDINATE_SYSTEM | unprobed | not probed in this run |
| TRANSLATE_COORDINATE_SYSTEM | unprobed | not probed in this run |
| DUPLICATE_COORDINATE_SYSTEM | unprobed | not probed in this run |
| MIRROR_COORDINATE_SYSTEM | unprobed | not probed in this run |
| DELETE_COORDINATE_SYSTEM | unprobed | not probed in this run |
| OPEN | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the log confirms 'Simulation file opened' for a file the probe saved just before |
| SAVEAS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the simulation file the command names exists and is not empty |
| NEW_SIMULATION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: after NEW_SIMULATION on an opened 582 kB simulation, the session saved by the epilogue is below 100 kB (the geometry is gone) |
| CLOSE_FLIGHTSTREAM | verified | script processing halted at the command: the log before it exists, the one after it never appeared; expected: script processing ends at CLOSE_FLIGHTSTREAM and the solver exits |
| EXPORT_LOG | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the log file the command names exists and is not empty |
| OUTPUT_SETTINGS_AND_STATUS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings file the command names exists and is not empty |
| CLEAR_LOG | unprobed | not probed in this run |
| OUTPUT_SURFACE_INDICES | unprobed | not probed in this run |
| CREATE_FREE_SURFACE_TFI_MESH | broken | script processing aborted at the command: the log exported before it exists, the one after it never appeared (END sentinel missing) |
| FREE_SURFACE_EXPORT_TYPE | unprobed | the probe prelude did not reach the BEGIN sentinel although the baseline passed; the target was not judged. Inspect the prelude and its support commands (return code 1). 2026-10-05T16:54:54+00:00 solver modal/error detected pid=1092; terminating this owned solver process without clicking its dialog. |
| DELETE_FREE_SURFACE | unprobed | the probe prelude did not reach the BEGIN sentinel although the baseline passed; the target was not judged. Inspect the prelude and its support commands (return code 1). 2026-10-05T16:54:38+00:00 solver modal/error detected pid=21980; terminating this owned solver process without clicking its dialog. |
| CREATE_NEW_INLET | unprobed | not probed in this run |
| SET_INLET_CUSTOM_PROFILE | unprobed | not probed in this run |
| REMESH_INLET | unprobed | not probed in this run |
| DELETE_INLET | unprobed | not probed in this run |
| CREATE_NEW_OUTLET | unprobed | not probed in this run |
| REMESH_OUTLET | unprobed | not probed in this run |
| DELETE_OUTLET | unprobed | not probed in this run |
| IMPORT | unprobed | not probed in this run |
| CCS_IMPORT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation names the imported wing component |
| EXPORT_SURFACE_MESH | unprobed | not probed in this run |
| DELETE_SURFACES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved boundary inventory after the command is the inventory before it without its first boundary, the rest renumbered. The instrument read: inventory before ('Blade1',), after () |
| TRANSLATE_SURFACE_IN_FRAME | unprobed | not probed in this run |
| TRANSLATE_SURFACE_BY_FRAME | unprobed | not probed in this run |
| SURFACE_SCALE | unprobed | not probed in this run |
| SURFACE_MIRROR | unprobed | not probed in this run |
| SURFACE_LINEAR_COPY_PASTE | unprobed | not probed in this run |
| SURFACE_CIRCULAR_COPY_PASTE | unprobed | not probed in this run |
| SURFACE_SELECT_BY_ID | unprobed | not probed in this run |
| SURFACE_SELECT_BY_THRESHOLD | unprobed | not probed in this run |
| CREATE_NEW_SURFACE_FROM_SELECTION | unprobed | not probed in this run |
| SURFACE_CUT_BY_PLANE | unprobed | not probed in this run |
| SURFACE_COMBINE | unprobed | not probed in this run |
| SURFACE_AUTO_HOLE_FILL | unprobed | not probed in this run |
| SURFACE_INVERT | unprobed | not probed in this run |
| SURFACE_RENAME | unprobed | not probed in this run |
| DELETE_SELECTED_FACES | unprobed | not probed in this run |
| DELETE_DEGENERATE_FACES | unprobed | not probed in this run |
| SELECT_MESH_NODE | unprobed | not probed in this run |
| TRANSFORM_SELECTED_NODES | unprobed | not probed in this run |
| ROTATE_SURFACE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: rotating every surface about the global frame changes the saved mesh |
| BOOLEAN_UNITE_PATH | unprobed | not probed in this run |
| BOOLEAN_UNITE_MESH | unprobed | not probed in this run |
| WRAPPER_SET_INPUT | unprobed | not probed in this run |
| WRAPPER_SET_GLOBAL_SIZE | unprobed | not probed in this run |
| WRAPPER_SET_VERTEX_PROJECTION | unprobed | not probed in this run |
| WRAPPER_SET_ANISOTROPY | unprobed | not probed in this run |
| WRAPPER_CREATE_LOCAL_CONTROL | unprobed | not probed in this run |
| WRAPPER_EDIT_LOCAL_CONTROL | unprobed | not probed in this run |
| WRAPPER_DELETE_ALL_LOCAL_CONTROLS | unprobed | not probed in this run |
| WRAPPER_NEW_VOLUME_CONTROL | unprobed | not probed in this run |
| WRAPPER_DELETE_ALL_VOLUME_CONTROLS | unprobed | not probed in this run |
| WRAPPER_EXECUTE | unprobed | not probed in this run |
| WRAPPER_TRANSFER | unprobed | not probed in this run |
| CREATE_NEW_MOTION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: motions are unnamed and stored in binary form (recon-checked); no instrument observes them yet |
| SET_MOTION_BOUNDARIES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: motion boundary lists are stored in binary form; no instrument yet |
| SET_MOTION_MOVING_FRAMES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: motion frame lists are stored in binary form; no instrument yet |
| SET_MOTION_COORDINATE_SYSTEM | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the motion frame binding |
| SET_MOTION_START_TIME | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the motion start time is stored in binary form; no instrument yet |
| SET_MOTION_ROTOR_AXIS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the rotor axis is stored in binary form; no instrument yet |
| SET_MOTION_ROTOR_RPM | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the rotor rpm is stored in binary form; no instrument yet |
| SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: DISABLE after ENABLE changes the saved simulation, which stores the key (the one-line difference of the 0.32.0 round 1, RPT-096) |
| SET_MOTION_FSI_EXECUTABLE | unprobed | not probed in this run |
| SET_MOTION_FSI_STRUCTURAL_NODES | unprobed | not probed in this run |
| DELETE_MOTION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: motions are unnamed in the saved file, so deletion is not discriminated yet |
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
| SET_PLOT_TYPE | unprobed | not probed in this run |
| SAVE_PLOT_TO_FILE | unprobed | not probed in this run |
| NEW_PROBE_POINT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export lists the distinctive point coordinate 0.1234E+01 |
| NEW_PROBE_LINE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export counts exactly the 3 requested line points |
| UPDATE_PROBE_POINTS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the probe export may refresh; the stored points do not move |
| PROBE_POINTS_IMPORT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export counts exactly the 2 imported lattice points |
| EXPORT_PROBE_POINTS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export file the command names exists and is not empty |
| DELETE_PROBE_POINTS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe export counts 0 points after the prelude created one |
| SOLVER_SET_AOA | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive angle of attack 7.253 deg |
| SOLVER_SET_SIDESLIP | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive side-slip 3.414 deg |
| SOLVER_SET_VELOCITY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive free-stream velocity 51.617 m/s |
| SOLVER_SET_MACH_NUMBER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the initialized settings dump reports the distinctive Mach number .213 |
| SOLVER_SET_ITERATIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive iteration count 123 |
| SOLVER_SET_CONVERGENCE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive convergence limit 2.718E-04 |
| SOLVER_SET_FORCED_ITERATIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports forced iterations as T |
| SOLVER_SET_REF_VELOCITY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive reference velocity 47.513 m/s |
| SOLVER_SET_REF_MACH_NUMBER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the initialized settings dump reports the distinctive reference Mach .157 |
| SOLVER_SET_REF_AREA | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive reference area 2.727 m^2 |
| SOLVER_SET_REF_LENGTH | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive reference length 3.131 m |
| SET_MAX_PARALLEL_THREADS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the thread count |
| SET_SCENE_COLORMAP_TYPE | unprobed | not probed in this run |
| SET_SCENE_COLORMAP_SIZE | unprobed | not probed in this run |
| SET_SCENE_COLORMAP_POSITION | unprobed | not probed in this run |
| SET_SCENE_COLORMAP_SHADING | unprobed | not probed in this run |
| SET_SCENE_COLORMAP_CUSTOM_MODE | unprobed | not probed in this run |
| SET_SCENE_COLORMAP_CUSTOM_RANGE | unprobed | not probed in this run |
| VIEW_RESIZE | unprobed | not probed in this run |
| CHANGE_SCENE_TO_CAD | unprobed | not probed in this run |
| CHANGE_SCENE_TO_GEOMETRY | unprobed | not probed in this run |
| CHANGE_SCENE_TO_SOLVER | unprobed | not probed in this run |
| CHANGE_SCENE_TO_PLOTS | unprobed | not probed in this run |
| SAVE_SCENE_AS_IMAGE | unprobed | not probed in this run |
| SET_SCENE_DEFAULTVIEW | unprobed | not probed in this run |
| SET_SCENE_XY_POSITIVE | unprobed | not probed in this run |
| SET_SCENE_XY_NEGATIVE | unprobed | not probed in this run |
| SET_SCENE_XZ_POSITIVE | unprobed | not probed in this run |
| SET_SCENE_XZ_NEGATIVE | unprobed | not probed in this run |
| SET_SCENE_YZ_POSITIVE | unprobed | not probed in this run |
| SET_SCENE_YZ_NEGATIVE | unprobed | not probed in this run |
| STOP | verified | script processing halted at the command: the log before it exists, the one after it never appeared; expected: script processing halts at STOP (the idle hidden process was killed at the timeout) |
| PRINT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the probe message PYFS_EFFECT_PRINT appears as a log line of its own |
| RUN_SCRIPT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the nested script's message PYFS_EFFECT_NESTED appears in the log, so the called script really ran |
| SET_SIMULATION_LENGTH_UNITS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the initialized settings dump reports lengths in cm |
| SET_SIGNIFICANT_DIGITS | unprobed | not probed in this run |
| SET_TRAILING_EDGE_SWEEP_ANGLE | unprobed | not probed in this run |
| SET_VERTEX_MERGE_TOLERANCE | unprobed | not probed in this run |
| SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE | unprobed | not probed in this run |
| SET_VORTICITY_DRAG_BOUNDARIES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the vorticity-drag list |
| DELETE_VORTICITY_DRAG_BOUNDARIES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the vorticity-drag boundary list is not exposed by any instrument yet |
| SET_SOLVER_ANALYSIS_LOADS_FRAME | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet exported after the solve reports the analysis frame set before it, by its probe-given name PYFS_FRAME_NAME |
| SET_ANALYSIS_MOMENTS_MODEL | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the moments-model choice |
| SET_ANALYSIS_SYMMETRY_LOADS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the symmetry-loads toggle is not exposed by any instrument yet; probed pre-solve since the 2026-07-21 phase correction (the in-solve monitors consume it) |
| SET_LOADS_AND_MOMENTS_UNITS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet footer reports the force units as Newtons |
| SET_SOLVER_ANALYSIS_BOUNDARIES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the saved simulation does not move (RPT-020); every boundary appears to be selected already, so setting all of them changes nothing to observe |
| SET_INVISCID_LOADS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the loads exported after enabling inviscid-only report CDo exactly zero (the viscous default on this run is nonzero) |
| SET_VORTICITY_LIFT_MODEL | unprobed | not probed in this run |
| SET_SCENE_CONTOUR | unprobed | not probed in this run |
| EXPORT_SOLVER_ANALYSIS_SPREADSHEET | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty |
| EXPORT_SOLVER_ANALYSIS_TECPLOT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty |
| EXPORT_SOLVER_ANALYSIS_VTK | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty |
| SET_VTK_EXPORT_VARIABLES | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the VTK exported afterwards carries the selected CP_REFERENCE variable |
| EXPORT_SOLVER_ANALYSIS_CSV | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty |
| EXPORT_SOLVER_ANALYSIS_PLOAD_BDF | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty |
| EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the export file the command names exists and is not empty |
| EXPORT_BL_VELOCITY_PROFILE | unprobed | not probed in this run |
| DELETE_BL_VELOCITY_PROFILE | unprobed | not probed in this run |
| INITIALIZE_SOLVER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the log reports 'Solver initialized' with the mesh statistics |
| SOLVER_PROXIMAL_BOUNDARIES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the proximal-boundary marking |
| REMOVE_INITIALIZATION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings dump flips from the initialized solver state to 'Not initialized' |
| START_SOLVER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the log carries the iteration table and 'Solver run time' |
| CLEAR_SOLUTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the solver iteration counter back at 0 |
| SET_SOLVER_STEADY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports Steady after the prelude set the unsteady mode |
| SET_SOLVER_UNSTEADY | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the settings sheet reports the distinctive time increment .012 s |
| SET_BOUNDARY_LAYER_TYPE | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the boundary-layer model choice |
| SET_SOLVER_VISCOUS_COUPLING | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the viscous-coupling choice |
| SET_VISCOUS_EXCLUDED_BOUNDARIES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation carries the viscous exclusion list |
| DELETE_VISCOUS_EXCLUDED_BOUNDARIES | unprobed | not probed in this run |
| CREATE_AIRFOIL_SEPARATION | unprobed | not probed in this run |
| CREATE_AXIAL_VORTEX_SEPARATION | unprobed | not probed in this run |
| CREATE_CYLINDRICAL_BULK_SEPARATION | unprobed | not probed in this run |
| CREATE_STRATFORD_BULK_SEPARATION | unprobed | not probed in this run |
| DELETE_SEPARATION | unprobed | not probed in this run |
| SET_SURFACE_ROUGHNESS | unprobed | not probed in this run |
| SET_THIN_BOUNDARIES | unprobed | not probed in this run |
| DELETE_THIN_BOUNDARIES | unprobed | not probed in this run |
| SOLVER_STABILIZATION | unprobed | not probed in this run |
| DISABLE_SOLVER_REF_VELOCITY | unprobed | not probed in this run |
| STABILITY_TOOLBOX_SETTINGS | unprobed | not probed in this run |
| STABILITY_TOOLBOX_NEW_COEFFICIENT | unprobed | not probed in this run |
| STABILITY_TOOLBOX_DELETE_ALL | unprobed | not probed in this run |
| COMPUTE_STABILITY_COEFFICIENTS | unprobed | not probed in this run |
| STABILITY_TOOLBOX_EXPORT | unprobed | not probed in this run |
| STABILITY_TOOLBOX_ANGLE_INCREMENT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across the angle step; a still file records unprobed |
| NEW_OFF_BODY_STREAMLINE | broken | script processing aborted at the command: the log exported before it exists, the one after it never appeared (END sentinel missing) |
| NEW_STREAMLINE_DISTRIBUTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the streamline export written after generation carries data for the seeded distribution |
| GENERATE_ALL_OFF_BODY_STREAMLINES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the streamline export written afterwards carries generated data |
| EXPORT_ALL_OFF_BODY_STREAMLINES | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the streamline export file the command names exists and is not empty |
| NEW_OFF_BODY_STREAMTUBE | unprobed | not probed in this run |
| SET_OFF_BODY_STREAMLINE_LENGTH | unprobed | not probed in this run |
| SET_ALL_OFF_BODY_STREAMLINES_UPSTREAM | unprobed | not probed in this run |
| SET_ALL_OFF_BODY_STREAMLINES_DOWNSTREAM | unprobed | not probed in this run |
| DELETE_ALL_OFF_BODY_STREAMLINES | unprobed | not probed in this run |
| GENERATE_ALL_SURFACE_STREAMLINES | unprobed | not probed in this run |
| DELETE_ALL_SURFACE_STREAMLINES | unprobed | not probed in this run |
| EXPORT_ALL_SURFACE_STREAMLINES | unprobed | not probed in this run |
| CREATE_NEW_SURFACE_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the all-sections export written afterwards carries the created section |
| NEW_SURFACE_SECTION_DISTRIBUTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the all-sections export written afterwards carries the distribution |
| COMPUTE_SURFACE_SECTIONAL_LOADS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sectional-loads export written afterwards carries computed loads |
| EXPORT_SURFACE_SECTIONAL_LOADS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sectional-loads file the command names exists and is not empty |
| UPDATE_ALL_SURFACE_SECTIONS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the sections export may refresh on its own, so it cannot discriminate the update command; needs a dedicated instrument |
| EXPORT_ALL_SURFACE_SECTIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the all-sections file the command names exists and is not empty |
| EXPORT_SURFACE_SECTIONS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the solver adds a file to its working folder: the manual states no file name for the one-section export, so the folder is read, and silence records unprobed. The instrument read: files added to the working folder: PRINT PYFS_PROBE_END_EXPORT_SURFACE_SECTIONS, logs |
| DELETE_SURFACE_SECTION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the surviving-section listing format is not pinned yet, so deletion is not discriminated; needs a dedicated instrument |
| DELETE_ALL_SURFACE_SECTIONS | unprobed | not probed in this run |
| SWEEPER_SET_AOA_SWEEP | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sweep spreadsheet carries both requested angles 2.000 and 4.000 |
| SWEEPER_SET_BETA_SWEEP | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sweep spreadsheet carries both requested side-slips 1.500 and 3.500 |
| SWEEPER_SET_VELOCITY_SWEEP | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: only the DISABLE form is probed (the CUSTOM velocity list file format awaits a manual pass); the disabled state leaves no observable trace |
| SWEEPER_SET_MACH_SWEEP | unprobed | not probed in this run |
| SWEEPER_POST_RUN_SCRIPT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the post-run script's message PYFS_POSTRUN appears in the log after the sweep |
| SWEEPER_CLEAR_SOLUTION | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the sweeper clear-solution toggle is not exposed by any instrument yet |
| SWEEPER_START | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sweep run prints the solver iteration table and run time |
| SWEEPER_EXPORT_SPREADSHEET | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the sweep spreadsheet the command names exists and is not empty |
| RESET_SOLVER_SWEEPER | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across the reset of a configured angle sweep; a still file records unprobed |
| DELETE_TRANSITION_TRIP | unprobed | not probed in this run |
| UNSTEADY_SOLVER_NEW_FORCE_PLOT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the plots file exported after the unsteady solve carries the CL plot by name |
| UNSTEADY_SOLVER_NEW_FLUID_PLOT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the plots file exported after the unsteady solve carries the fluid plot by name |
| UNSTEADY_SOLVER_DELETE_ALL_PLOTS | unprobed | not probed in this run |
| UNSTEADY_SOLVER_EXPORT_PLOTS | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the plots file the command names exists and is not empty after an unsteady solve |
| NEW_UNSTEADY_SOLVER_SURFACE_PROBE | unprobed | not probed in this run |
| UNSTEADY_SOLVER_ANIMATION | unprobed | not probed in this run |
| SET_NEW_UNSTEADY_SOLVER_ACTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the message the registered script prints appears in the log after the unsteady solve, so the solver ran the action; silence records unprobed |
| ENABLE_SOLVER_TIME_AVERAGING | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across the command under an unsteady state of three steps; a still file records unprobed. Killed after a minute, since the command it replaces hung 26.124 (C01) |
| DISABLE_SOLVER_TIME_AVERAGING | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the saved simulation moves across the command after the averaging was enabled; a still file records unprobed |
| CREATE_NEW_RECTANGLE_VOLUME_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: exporting volume section 1 afterwards succeeds, so the section exists |
| CREATE_NEW_CIRCLE_VOLUME_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: exporting volume section 1 afterwards succeeds, so the section exists |
| UPDATE_ALL_VOLUME_SECTIONS | unprobed | the command ran without a script abort or logged error, but its effect is not observable with the current instruments; asserted effect: the section export may refresh on its own, so it cannot discriminate the update command; needs a dedicated instrument |
| EXPORT_VOLUME_SECTION_VTK | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the VTK file the command names exists and is not empty |
| EXPORT_VOLUME_SECTION_TECPLOT | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: the Tecplot file the command names exists and is not empty |
| DELETE_VOLUME_SECTION | verified | script processing continued past the command, no error between the sentinels, and the effect was observed: exporting the deleted section 1 afterwards produces no file (the export command's own probe rules out an export failure) (the epilogue instruments aborted after the target; the effect was judged from the artifacts they left) |
| DELETE_ALL_VOLUME_SECTIONS | unprobed | not probed in this run |
| VOLUME_SECTION_WIREFRAME | unprobed | not probed in this run |
| EXPORT_VOLUME_SECTION_2D_VTK | unprobed | not probed in this run |

## Erratum (2026-10-05): three CCS mesh rows re-read

The rows CCS_FUSELAGE_MESH_GROWTH_RATE, CCS_REVOLVE_MESH_GROWTH_SCHEME and
CCS_REVOLVE_MESH_GROWTH_RATE above print equal vertex and face counts for
the reference and the variant loft, which reads as "identical". The judge
never compared counts alone: it compares the whole normalized geometry of
each loft (every vertex coordinate and every face resolved to its
coordinates, sorted, names and normals ignored). The instrument read of
that run printed only the counts. The read now prints the geometry digest
the judge compares and states whether the variant equals the reference.

Re-read from the campaign folders of this run with the new read; the
verdicts are unchanged (verified):

| Command | Instrument read (new) | Vertices in one loft only |
|---|---|---|
| CCS_FUSELAGE_MESH_GROWTH_RATE | reference 1975 vertices 1896 faces geometry digest 1b8d868e6abd65c5; variant 1975 vertices 1896 faces geometry digest a59538f10ad69ed3; variant geometry differs from reference | 1817 of 1975 |
| CCS_REVOLVE_MESH_GROWTH_SCHEME | reference 4584 vertices 4661 faces geometry digest 5ec7cc9e3af6cf68; variant 4584 vertices 4661 faces geometry digest 8493918eca6b3b98; variant geometry differs from reference | 4582 of 4584 |
| CCS_REVOLVE_MESH_GROWTH_RATE | reference 4584 vertices 4661 faces geometry digest 5ec7cc9e3af6cf68; variant 4584 vertices 4661 faces geometry digest 2db8826a8997fa0a; variant geometry differs from reference | 4582 of 4584 |

The first differing line of the fuselage exports is line 82 (reference
`v .17916665 .21997041 .00000000`, variant `v 2.00000000 .19303000 .00000000`);
of both revolve exports, line 4. The original rows above are left as
written.
