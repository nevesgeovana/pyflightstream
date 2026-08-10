# RPT-024: the scripting surface of every build (2026-08-09)

What each registered FlightStream build documents as its scripting
command set, and what changed from one build to the next. Command names
only; nothing of the manual's text appears here or in the tool that
produced it.

This report is REGENERATED rather than maintained. Everything below the
first two sections is the output of

```
pyfs-manual surface --editions <manifest> --markdown
```

reading the local edition manifest, so re-running it after a new install
arrives is the whole update procedure. The manifest is local because it
names licensed manual paths; registering a build is adding a row to it.

## What "gained" and "lost" mean here, and what they do not

Gained means the newer manual carries a signature heading the older one
does not. Lost means the older manual carries one the newer one does
not.

Lost is NOT a claim that the solver stopped accepting the command. A
command can disappear from a manual and keep working, and this
repository has measured the opposite case too: 26.101 reports the
February flow-separation family as deprecated and then refuses it
(RPT-018). Deciding which happened for a given command needs a probe on
that build, so this report is evidence for a question rather than an
answer to it. The command database records the answer per version once
a probe or a page settles it.

The count is of DOCUMENTED commands, read from the scripting chapter
body rather than from the Script Index. That distinction is load
bearing: the index is incomplete, and an index-driven reading reports a
smaller surface for every edition, which would look like the vendor
removing commands.

## The reading was cross-checked against the command database

For the four builds the database records, every command the manual
documents has an entry: manual-only is ZERO on all four. That is the
check that the page ranges are right, since a range that missed pages
would show up here as commands the manual documents and the database
never heard of.

The reverse direction is not zero and is expected. The database records
1 command 26.100's manual does not document, 1 for 26.101, 2 for 26.120
and 7 for 26.121. Two causes account for all of them: an entry
documented by no edition and carried on probe evidence instead
(`SONIC_VELOCITY`), and 26.121 inheriting its base release's records for
commands its own manual stops printing, which is what `inherits_base`
means and what the compatibility matrix marks per cell.

## 25.000 is measured but not by this tool

The 25.000 install ships its manual only as a compiled HTML help
archive, and `pyfs-manual` reads pdf, so that build has no row in the
manifest and does not appear in the generated sections below. Its
surface was measured separately, by extracting the archive and counting
the same signature headings in the extracted topics:

**272 commands documented.**

Against 25.100 it gained 10 and lost 8.

Gained: `CLEAR_SOLUTION`, `CREATE_NEW_MOTION`,
`DISABLE_WAKE_NODES_ON_TRAILING_EDGE`, `OUTPUT_SETTINGS_AND_STATUS`,
`REMOVE_INITIALIZATION`, `REYNOLDS_AVERAGED_DRAG_FORCES`, `RUN_SCRIPT`,
`SELECT_BASE_REGION_FACES`, `SELECT_MESH_NODE`,
`TRANSFORM_SELECTED_NODES`

Lost: `BOOLEAN_UNITE_GEOMETRY`, `CREATE_NEW_MOTION_6DOF`,
`CREATE_NEW_MOTION_CUSTOM`, `CREATE_NEW_MOTION_EUCLIDEAN`,
`CREATE_NEW_MOTION_FSI`, `SET_SOLVER_MODEL`, `SOLVER_CLEAR`,
`SOLVER_UNINITIALIZE`

Read that pair together rather than as two lists. The four
`CREATE_NEW_MOTION_*` commands become one `CREATE_NEW_MOTION`, and
`SOLVER_CLEAR` becomes `CLEAR_SOLUTION`: this is one vendor renaming,
not eight removals and ten additions. The counts cannot see that and a
reader can, which is the reason this report lists names and not only
numbers.

Adding a reader for the help archive so 25.000 joins the generated
sections is registered as PLN-20260809-2200.

## The shape of the whole history

The surface grew from 272 to 364 across seven builds, and it did not
grow smoothly. One step accounts for most of it: 26.000 to 26.100 gained
75 commands, essentially the whole CAD and cross-section family arriving
at once. The next step, 26.100 to 26.101, is the one to be careful
with: 35 gained and 16 lost between two builds the vendor ships under
the SAME release name, "26.1". A reader who recorded only that name in a
paper cannot tell which of those two surfaces was available to them.

The two 25 builds and 26.000 differ from each other by single digits,
so a script written for one of them is close to portable across the
three; the boundary that matters in that range is not the command set
but the command line, where the 25 series and 26.000 disagree
(RPT-023).

## Command surface per edition

| Build | Commands documented |
|---|---|
| 25.100 | 274 |
| 26.000 | 276 |
| 26.100 | 344 |
| 26.101 | 363 |
| 26.120 | 363 |
| 26.121 | 364 |

## What changed between consecutive builds

### 25.100 to 26.000

Gained 3, lost 1.

Gained: `AUTO_DETECT_TRAILING_EDGES`, `AUTO_DETECT_WAKE_TERMINATION_NODES`, `SET_TRAILING_EDGE_TYPE`

Lost: `PHYSICS`

### 26.000 to 26.100

Gained 75, lost 7.

Gained: `ADDITIONAL_WAKE_RELAXATION_ITERATION`, `CAD_BODY_DELETE`, `CAD_BODY_MIRROR`, `CAD_BODY_ROTATE`, `CAD_BODY_SCALE`, `CAD_BODY_SELECT_BY_THRESHOLD`, `CAD_BODY_TRANSLATE`, `CAD_CREATE_BOX`, `CAD_CREATE_CONNECT_CURVES`, `CAD_CREATE_CYLINDER`, `CAD_CREATE_FUSELAGE_MESH_FROM_CCS`, `CAD_CREATE_IMPORT_CURVE_P3D`, `CAD_CREATE_MIRROR_CURVES`, `CAD_CREATE_PROJECT_CURVE`, `CAD_CREATE_PROJECT_MULTI_CURVE`, `CAD_CREATE_REORDER_CURVES`, `CAD_CREATE_REVOLVE_MESH_FROM_CCS`, `CAD_CREATE_ROTATE_CURVES`, `CAD_CREATE_SCALE_CURVES`, `CAD_CREATE_SELF_MEDIAN_FROM_CURVES`, `CAD_CREATE_SHEET`, `CAD_CREATE_SPHERE`, `CAD_CREATE_TRANSLATE_CURVES`, `CAD_CREATE_WING_MESH_FROM_CCS`, `CCS_FUSELAGE_MESH_GROWTH_RATE`, `CCS_FUSELAGE_MESH_GROWTH_SCHEME`, `CCS_FUSELAGE_MESH_PERIODICITY`, `CCS_FUSELAGE_MESH_SUBDIVISIONS`, `CCS_REVOLVE_MESH_GROWTH_RATE`, `CCS_REVOLVE_MESH_GROWTH_SCHEME`, `CCS_REVOLVE_MESH_PERIODICITY`, `CCS_REVOLVE_MESH_SUBDIVISIONS`, `CCS_WING_MESH_GROWTH_RATE`, `CCS_WING_MESH_GROWTH_SCHEME`, `CCS_WING_MESH_PERIODICITY`, `CCS_WING_MESH_SUBDIVISIONS`, `CREATE_NEW_OUTLET`, `DEFAULT_CCS_FUSELAGE_MESH_SETTINGS`, `DEFAULT_CCS_REVOLVE_MESH_SETTINGS`, `DEFAULT_CCS_WING_MESH_SETTINGS`, `DELETE_CCS_FUSELAGE_REFINEMENT_ZONES`, `DELETE_CCS_FUSELAGE_RELAXED_TE`, `DELETE_CCS_REVOLVE_REFINEMENT_ZONES`, `DELETE_CCS_REVOLVE_RELAXED_TE`, `DELETE_CCS_WING_CONTROL_SURFACE`, `DELETE_CCS_WING_REFINEMENT_ZONES`, `DELETE_OUTLET`, `DELETE_VALAREZO_CRITERION_BOUNDARIES`, `EXPORT_FUSELAGE_CCS_FILE`, `EXPORT_REVOLVE_CCS_FILE`, `EXPORT_WING_CCS_FILE`, `KUTTA_JOUKOWSKI_LIFT_FORCES`, `LAMINAR_SEPARATION`, `NEW_CCS_FUSELAGE_REFINEMENT_ZONE`, `NEW_CCS_FUSELAGE_RELAXED_TE`, `NEW_CCS_REVOLVE_REFINEMENT_ZONE`, `NEW_CCS_REVOLVE_RELAXED_TE`, `NEW_CCS_WING_CONTROL_SURFACE`, `NEW_CCS_WING_FLAP_COVE`, `NEW_CCS_WING_MORPHING_SURFACE`, `NEW_CCS_WING_REFINEMENT_ZONE`, `OUTPUT_SURFACE_INDICES`, `PRINT_ROTOR_INDUCED_VELOCITIES`, `REMESH_BASE_REGION`, `REMESH_OUTLET`, `SET_ADAPTIVE_FIELD_GRID_REFINEMENT`, `SET_CAD_CREATE_MERGE_TOLERANCE`, `SET_CAD_CREATE_SPLINE_LOFT`, `SET_CAD_CREATE_SPLINE_SEGMENTS`, `SET_CAD_CURVATURE_REFINEMENT`, `SET_CROSSFLOW_SEPARATION_AXISYMMETRIC`, `SET_CROSSFLOW_SEPARATION_DIAMETER`, `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION`, `SET_VALAREZO_SEPARATION_BOUNDARIES`, `SET_WAKE_ON_WAKE_INDUCTION`

Lost: `SET_CROSSFLOW_SEPARATION_CP`, `SET_UNSTEADY_VISCOUS_COUPLING_ITERATION`, `SET_WAKE_RELAXATION`, `SET_WAKE_STREAMWISE_AGGLOMERATION`, `SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER`, `SOLVER_VORTEX_RING_NORMALIZATION`, `VALAREZO_CRITERION`

### 26.100 to 26.101

Gained 35, lost 16.

Gained: `AEROELASTIC_RBF_TYPE`, `ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS`, `ASSIGN_AEROELASTIC_SURFACES`, `CREATE_AIRFOIL_SEPARATION`, `CREATE_AXIAL_VORTEX_SEPARATION`, `CREATE_BULK_SEPARATION`, `DELETE_AEROELASTIC_STRUCTURAL_NODES`, `DELETE_SEPARATION`, `DELETE_THIN_BOUNDARIES`, `EXECUTE_AEROELASTIC_ANALYSIS`, `IMPORT_AEROELASTIC_STRUCTURAL_NODES`, `MARK_WAKE_TERMINATION_NODES`, `ROTOR_INDUCED_VELOCITY_BLENDING`, `SET_AEROELASTIC_COUPLING_IN_UNSTEADY`, `SET_AEROELASTIC_ITERATIONS`, `SET_AEROELASTIC_POST_PROCESSING_SCRIPT`, `SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND`, `SET_AEROELASTIC_WORKING_DIRECTORY`, `SET_JET_WAKE_DECAY_NORMALIZED_LENGTH`, `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION`, `SET_MOTION_ROTOR_AXIS`, `SET_MOTION_ROTOR_RPM`, `SET_THIN_BOUNDARIES`, `SET_WAKE_NUMERICAL_RELAXATION`, `SOLVER_STABILIZATION`, `SURFACE_SELECT_BY_ID`, `SWEEPER_CLEAR_SOLUTION`, `SWEEPER_EXPORT_SPREADSHEET`, `SWEEPER_POST_RUN_SCRIPT`, `SWEEPER_REF_VELOCITY_SAME`, `SWEEPER_SET_AOA_SWEEP`, `SWEEPER_SET_BETA_SWEEP`, `SWEEPER_SET_MACH_SWEEP`, `SWEEPER_SET_VELOCITY_SWEEP`, `SWEEPER_START`

Lost: `DELETE_AXIAL_SEPARATION_BOUNDARIES`, `DELETE_CROSSFLOW_SEPARATION_BOUNDARIES`, `DELETE_VALAREZO_CRITERION_BOUNDARIES`, `DISABLE_ACTUATOR`, `EXECUTE_SOLVER_SWEEPER`, `SELECT_GEOMETRY_BY_ID`, `SET_AXIAL_SEPARATION_BOUNDARIES`, `SET_CROSSFLOW_SEPARATION_AXISYMMETRIC`, `SET_CROSSFLOW_SEPARATION_BOUNDARIES`, `SET_CROSSFLOW_SEPARATION_DIAMETER`, `SET_MOTION_ACCELERATION`, `SET_MOTION_ANGULAR_ACCELERATION`, `SET_MOTION_ANGULAR_VELOCITY`, `SET_MOTION_IS_ROTOR`, `SET_MOTION_VELOCITY`, `SET_VALAREZO_SEPARATION_BOUNDARIES`

### 26.101 to 26.120

Gained 1, lost 1.

Gained: `EXPORT_SURFACE_SECTIONS`

Lost: `VOLUME_SECTION_BOUNDARY_LAYER`

### 26.120 to 26.121

Gained 6, lost 5.

Gained: `CREATE_CYLINDRICAL_BULK_SEPARATION`, `CREATE_STRATFORD_BULK_SEPARATION`, `DELETE_SURFACES`, `DISABLE_SOLVER_REF_VELOCITY`, `NEW_UNSTEADY_SOLVER_SURFACE_PROBE`, `SET_WAKE_DECAY_CONSTANT`

Lost: `CREATE_BULK_SEPARATION`, `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION`, `SURFACE_CLEARALL`, `SURFACE_DELETE`, `SWEEPER_REF_VELOCITY_SAME`
