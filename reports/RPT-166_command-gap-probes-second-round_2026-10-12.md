# RPT-166 - The command-gap probes, second round, and the licensed items of 0.40.0 (2026-10-12)

The record of the licensed probe work that closes the first command-gap batch of
0.40.0 (PFS-2081.13 to .17) and the licensed items PFS-2135.060, .061, .066 and
PFS-2085.021. Every verdict below was written by the package's probe harness;
the committed evidence is the compat report pairs named in section 6, which
`pyfs-qa apply-compat` promotes from. The probe folders themselves (scripts,
logs, saved simulations, exports) stay on the licensed machine.

## 1. What the first batch left

The first batch ran 88 probes on 26.124 and 26.125 (176 runs): 95 verified,
4 removed, 10 broken, 67 unprobed. Reading each unprobed run's log and probe
script sorted them into four kinds: an instrument that could not read what the
solver did, a missing precondition, a wrong argument, and a harness blind spot.

## 2. The harness

- **26.125 reports script errors on standard output only.** Under `-hidden`
  build #10052026 writes no `FlightStreamLog.txt`; a two-line script naming an
  unknown command left no file in its folder and printed the
  `ERROR | Syntax | ... | Unrecognized command` line on stdout. The judge read
  the file alone, so every name 26.125 refuses was recorded as an abort
  (broken, no line to show). It now reads both channels. Effect: P5-A1 to A3
  and P3-02, P3-02u move from broken to removed on 26.125.
- **26.100 words a refusal without the table**: "Unrecognized command in script
  <path> at line N: <line>". Both wordings are read now (DELETE_VALAREZO_CRITERION_BOUNDARIES
  and the FSI motion pair on 26.100).
- An abort's own solver lines now reach the evidence line, with the probe
  folder written as `<probe folder>`.

## 3. What each fix measured

- **Instruments.** P1-06 and P1-06c read the surface that replaces the emptied
  one (a SELECTED_FACES threshold of surface 2 gives a new surface of 120 faces,
  ALL_FACES one of 408); P1-05c is a control (no selection, no change); P2-05c
  reads one converted surface spanning both IGES sheets (the file imports as one
  CAD body); P2-07 and P2-08 export each loft right after it is made; P3-06
  reads the streamline table.
- **Preconditions.** P1-03 cuts between two mesh stations (y = 0.5 is a station
  line; y = 0.75 cuts); P2-16 to P2-23 import their sections through the CCS
  curve route and select before exporting (the curve an operation makes is not
  selected, and an export of nothing stops on a dialog); P5-3 couples on a frame
  the run creates (the reference frame is refused: "No user-defined coordinate
  systems available to assign as aeroelastic frames") and states
  INCLUDE_SYMMETRY in its section block.
- **P4.** The trajectory exported before the march, the phase the database
  records, holds its header and no row on both builds (P4-04: 470 bytes after a
  20-step march); exported after the march it holds the rows (P4-04m). Each
  registered P4 probe therefore reads the saved simulation across its setter
  (every one moves a value: gravity -9.81, the rates, the freedom flags, the
  symmetry flag, the forces), and its battery twin P4-<n>m reads the trajectory
  after the march.

## 4. Broken, with the line that shows it

| Command | Builds | What the solver said |
|---|---|---|
| CAD_CREATE_IMPORT_CURVE_TXT | 26.124, 26.125 | "Error in script ... at line 8: 'CAD_CREATE_IMPORT_CURVE_TXT METER 2D 1 XZ' / Review command syntax and arguments", for space, comma and counted layouts alike (P2-14, P2-14c, P2-14n) |
| NEW_OFF_BODY_STREAMTUBE | 26.124, 26.125 | "WARNING / Syntax / NEW_OFF_BODY_STREAMTUBE / Unexpected argument PRINT" then the error at the next line, for the X axis, the numeric axis of the manual's sample and a closing blank line (P3-01, P3-01a, P3-01b) |
| CREATE_NEW_6DOF_EXTERNAL_FORCE | 26.124, 26.125 | the error at the command line, for the probe's pulse and for the manual's own sample line (P4-06, P4-06s) |
| CREATE_BULK_SEPARATION | 26.120 | "WARNING / Deprecation / Command is deprecated; use CREATE_CYLINDRICAL_BULK_SEPARATION", then the error at the line |

## 5. Unprobed, with the reason

- P1-08 (DELETE_DEGENERATE_FACES): no input reaches the command holding a
  degenerate face. The STL importer drops a zero-area triangle (12 faces saved
  from 13), a node moved onto its neighbour takes its two faces out before the
  command (288 to 286), and a 0.1 mm sliver is kept by it (288 to 288).
- P2-09 (SET_CAD_CREATE_MERGE_TOLERANCE): the loft after the setting is empty
  (0 vertices) at 0.01 m and at 0.002 m on both builds, while the reference
  loft beside it has 4366 faces and the same epilogue keeps them for the other
  two settings. The setting reaches the loft; whether an empty loft is its
  intended effect is not decided here.
- P2-22 (CAD_CREATE_CURVE_REVERSE): the exported section starts at the file's
  first point after the reverse; the CCS export may write a curve in its own
  direction, so the instrument cannot read a reversal.
- P2-17n: the import does not select the curve; the reference export of the
  prelude stopped on "No virtual curves selected for export" (the question is
  answered, the target never ran).
- P3-05, P3-08 (GENERATE_ALL_SURFACE_STREAMLINES, DELETE_ALL_SURFACE_STREAMLINES):
  no script command seeds an on-body streamline (SRC-753 p.263, each starts from
  a click on the surface; p.382 lists generate, delete and export only), so the
  table counts 0 lines in a batch run. The first batch's "verified" for P3-08
  read zero lines after a delete of nothing and is withdrawn.
- P4-04 (EXPORT_6DOF_TRAJECTORY in its recorded phase): header only, see
  section 3. The command works placed after the march (P4-04m).
- G-09 on 26.124: 26.124 cannot open a simulation saved by 26.125
  ("Simulation file loading error in CAD module. / Error opening simulation
  file.").

## 6. The licensed items

- **PFS-2135.061.** SET_MOTION_FSI_EXECUTABLE and SET_MOTION_FSI_STRUCTURAL_NODES
  are refused as unrecognised on 26.100, 26.101, 26.120, 26.124 and 26.125;
  DELETE_VALAREZO_CRITERION_BOUNDARIES on 26.100. Route B, the user's program as
  SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND, is verified on 26.124 and 26.125:
  the stand-in is called three times in a three-step march and finds
  FS_SurfaceSection_Loads.txt in its folder (P5-3, P5-3f).
- **PFS-2135.066.** SET_MOTION_START_TIME on a 6DOF motion moves the saved
  simulation on 26.120, 26.124 and 26.125 (verified). 26.101 cannot open the
  probe's simulation (saved by 26.120); 26.121, 26.122 and 26.123 refused to
  start: "License has expired. Contact Altair for assistance."
- **PFS-2135.060.** CREATE_BULK_SEPARATION is broken on 26.120 (section 4). The
  26.121 and 26.122 editions do not print the name and print
  CREATE_CYLINDRICAL_BULK_SEPARATION (SRC-740 pp.345-346, SRC-750 p.347); those
  two builds could not run (licence expired).
- **PFS-2085.021, the declined surface on 26.125 (D-01, D-01c).** A wing and a
  solver-meshed sphere with no trailing edge, solved at 4 deg, then the
  vorticity drag list with the sphere on it (D-01) and off it (D-01c). On
  26.125 the sphere prints CDp 0 on the list and CDp -0.0005 off it, its Cx
  0.0009 and 0.0004: a declined surface prints a zero CDp, as earlier builds
  print a zero CDi. On 26.124 the sphere prints CDi 0 both on and off the list,
  so the 26.124 reading does not separate the two.

Compat reports: `reports/compat/CMP-26124_2026-10-12_gap-probes.yaml`,
`CMP-26125_2026-10-12_gap-probes.yaml` (the registered probes, the latest round
of each), and `CMP-<build>_2026-10-12_pfs2135-items.yaml` for 26.100, 26.101,
26.120, 26.124 and 26.125.

## 7. Every probe, final verdict

210 runs of 105 probes: 165 verified, 12 removed, 18 broken, 15 unprobed.

| Probe | Command | Registered | 26.124 | 26.125 |
|---|---|---|---|---|
| P5-A0 | CREATE_NEW_MOTION | no | verified | verified |
| P5-A1 | SET_MOTION_FSI_EXECUTABLE | no | removed | removed |
| P5-A2 | SET_MOTION_FSI_EXECUTABLE | yes | removed | removed |
| P5-A3 | SET_MOTION_FSI_EXECUTABLE | no | removed | removed |
| G-01a | CCS_IMPORT | no | verified | verified |
| G-01x | CCS_IMPORT | no | verified | verified |
| G-01b | SAVEAS | no | verified | verified |
| G-02a | CAD_CREATE_WING_MESH_FROM_CCS | no | verified | verified |
| G-02b | SAVEAS | no | verified | verified |
| G-03a | NEW_CCS_WING_CONTROL_SURFACE | no | verified | verified |
| G-03b | SAVEAS | no | verified | verified |
| G-04obj | EXPORT_SURFACE_MESH | no | verified | verified |
| G-04stl | EXPORT_SURFACE_MESH | no | verified | verified |
| G-04tri | EXPORT_SURFACE_MESH | no | verified | verified |
| G-03x | NEW_CCS_WING_CONTROL_SURFACE | no | verified | verified |
| G-03y | NEW_CCS_WING_CONTROL_SURFACE | no | verified | verified |
| G-05r | IMPORT_WAKE_EDGES_FROM_FILE | no | verified | verified |
| G-05s | IMPORT_WAKE_EDGES_FROM_FILE | no | verified | verified |
| G-06 | EXPORT_SURFACE_MESH | no | verified | verified |
| G-07 | EXPORT_SURFACE_MESH | no | verified | verified |
| G-08 | EXPORT_SURFACE_MESH | no | verified | verified |
| G-09 | SAVEAS | no | unprobed | verified |
| P1-01 | SURFACE_CIRCULAR_COPY_PASTE | yes | verified | verified |
| P1-02 | SURFACE_LINEAR_COPY_PASTE | yes | verified | verified |
| P1-03 | SURFACE_CUT_BY_PLANE | yes | verified | verified |
| P1-04 | SURFACE_SELECT_BY_THRESHOLD | yes | verified | verified |
| P1-05 | CREATE_NEW_SURFACE_FROM_SELECTION | yes | verified | verified |
| P1-05c | CREATE_NEW_SURFACE_FROM_SELECTION | no | verified | verified |
| P1-06 | SURFACE_SELECT_BY_ID | yes | verified | verified |
| P1-06c | SURFACE_SELECT_BY_ID | no | verified | verified |
| P1-07 | SURFACE_AUTO_HOLE_FILL | yes | verified | verified |
| P1-08 | DELETE_DEGENERATE_FACES | yes | unprobed | unprobed |
| P1-09 | DELETE_SELECTED_FACES | yes | verified | verified |
| P1-10 | SELECT_MESH_NODE | yes | verified | verified |
| P1-11 | TRANSFORM_SELECTED_NODES | yes | verified | verified |
| P1-12 | TRANSFORM_SELECTED_NODES | no | verified | verified |
| P2-01 | CAD_BODY_DELETE | yes | verified | verified |
| P2-02 | CAD_BODY_MIRROR | yes | verified | verified |
| P2-03 | CAD_BODY_SCALE | yes | verified | verified |
| P2-04 | CAD_BODY_TRANSLATE | yes | verified | verified |
| P2-05 | CAD_BODY_SELECT_BY_THRESHOLD | yes | verified | verified |
| P2-05c | CAD_BODY_SELECT_BY_THRESHOLD | no | verified | verified |
| P2-06 | SET_CAD_CURVATURE_REFINEMENT | yes | verified | verified |
| P2-07 | SET_CAD_CREATE_SPLINE_SEGMENTS | yes | verified | verified |
| P2-08 | SET_CAD_CREATE_SPLINE_LOFT | yes | verified | verified |
| P2-09 | SET_CAD_CREATE_MERGE_TOLERANCE | yes | unprobed | unprobed |
| P2-10 | CAD_CREATE_BOX | yes | verified | verified |
| P2-11 | CAD_CREATE_SPHERE | yes | verified | verified |
| P2-12 | CAD_CREATE_CYLINDER | yes | verified | verified |
| P2-13 | CAD_CREATE_SHEET | yes | verified | verified |
| P2-14 | CAD_CREATE_IMPORT_CURVE_TXT | yes | broken | broken |
| P2-14c | CAD_CREATE_IMPORT_CURVE_TXT | no | broken | broken |
| P2-14n | CAD_CREATE_IMPORT_CURVE_TXT | no | broken | broken |
| P2-15 | CAD_CREATE_IMPORT_CURVE_P3D | yes | verified | verified |
| P2-16 | CAD_CREATE_CURVE_UNSELECT | yes | verified | verified |
| P2-17 | CAD_CREATE_SCALE_CURVES | yes | verified | verified |
| P2-17n | CAD_CREATE_SCALE_CURVES | no | unprobed | unprobed |
| P2-18 | CAD_CREATE_ROTATE_CURVES | yes | verified | verified |
| P2-19 | CAD_CREATE_TRANSLATE_CURVES | yes | verified | verified |
| P2-20 | CAD_CREATE_REORDER_CURVES | yes | verified | verified |
| P2-21 | CAD_CREATE_CURVE_EXPORT_CCS | yes | verified | verified |
| P2-22 | CAD_CREATE_CURVE_REVERSE | yes | unprobed | unprobed |
| P2-23 | CAD_CREATE_MIRROR_CURVES | yes | verified | verified |
| P3-01 | NEW_OFF_BODY_STREAMTUBE | yes | broken | broken |
| P3-01a | NEW_OFF_BODY_STREAMTUBE | no | broken | broken |
| P3-01b | NEW_OFF_BODY_STREAMTUBE | no | broken | broken |
| P3-01c | NEW_STREAMLINE_DISTRIBUTION | no | verified | verified |
| P3-02 | SET_OFF_BODY_STREAMLINE_LENGTH | yes | removed | removed |
| P3-02u | SET_OFF_BODY_STREAMLINE_LENGTH | no | removed | removed |
| P3-03 | SET_ALL_OFF_BODY_STREAMLINES_UPSTREAM | yes | verified | verified |
| P3-04 | SET_ALL_OFF_BODY_STREAMLINES_DOWNSTREAM | yes | verified | verified |
| P3-05 | GENERATE_ALL_SURFACE_STREAMLINES | yes | unprobed | unprobed |
| P3-06 | EXPORT_ALL_SURFACE_STREAMLINES | yes | verified | verified |
| P3-07 | DELETE_ALL_OFF_BODY_STREAMLINES | yes | verified | verified |
| P3-08 | DELETE_ALL_SURFACE_STREAMLINES | yes | unprobed | unprobed |
| P3-09 | GENERATE_ALL_OFF_BODY_STREAMLINES | no | verified | verified |
| P3-10a | GENERATE_ALL_OFF_BODY_STREAMLINES | no | verified | verified |
| P3-10b | GENERATE_ALL_OFF_BODY_STREAMLINES | no | verified | verified |
| P4-01 | SET_MOTION_GRAVITY | yes | verified | verified |
| P4-01m | SET_MOTION_GRAVITY | no | verified | verified |
| P4-02 | SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY | yes | verified | verified |
| P4-02m | SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY | no | verified | verified |
| P4-03 | SET_MOTION_6DOF_ACTIVE_VARIABLES | yes | verified | verified |
| P4-03m | SET_MOTION_6DOF_ACTIVE_VARIABLES | no | verified | verified |
| P4-04 | EXPORT_6DOF_TRAJECTORY | yes | unprobed | unprobed |
| P4-04m | EXPORT_6DOF_TRAJECTORY | no | verified | verified |
| P4-05 | SET_6DOF_MOTION_SYMMETRY_LOADS | yes | verified | verified |
| P4-05m | SET_6DOF_MOTION_SYMMETRY_LOADS | no | verified | verified |
| P4-06 | CREATE_NEW_6DOF_EXTERNAL_FORCE | yes | broken | broken |
| P4-06m | CREATE_NEW_6DOF_EXTERNAL_FORCE | no | broken | broken |
| P4-06s | CREATE_NEW_6DOF_EXTERNAL_FORCE | no | broken | broken |
| P4-07 | CREATE_NEW_6DOF_CUSTOM_FORCE | yes | verified | verified |
| P4-07m | CREATE_NEW_6DOF_CUSTOM_FORCE | no | verified | verified |
| P4-08 | SET_MOTION_MASS_PROPERTIES | yes | verified | verified |
| P4-08m | SET_MOTION_MASS_PROPERTIES | no | verified | verified |
| P4-09 | SET_MOTION_6DOF_INITIAL_VELOCITY | yes | verified | verified |
| P4-09m | SET_MOTION_6DOF_INITIAL_VELOCITY | no | verified | verified |
| P4-10 | CREATE_NEW_6DOF_SPRING_FORCE | yes | verified | verified |
| P4-10m | CREATE_NEW_6DOF_SPRING_FORCE | no | verified | verified |
| P4-11 | SET_MOTION_6DOF_ACTIVE_VARIABLES | no | verified | verified |
| P5-2 | SET_MOTION_FSI_STRUCTURAL_NODES | yes | removed | removed |
| P5-3 | SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND | yes | verified | verified |
| P5-3f | SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND | no | verified | verified |
| D-01 | SET_VORTICITY_DRAG_BOUNDARIES | no | verified | verified |
| D-01c | SET_VORTICITY_DRAG_BOUNDARIES | no | verified | verified |

## 8. The CCS confirmation campaign

Run through the real command line (`pyfs-matrix plan`, `run --local`, `post`)
in a managed workspace on 26.124 and 26.125, a synthetic NACA 0012 wing
(chord 1 m, half span 4 m, mirrored) and a circular pod, every row hidden and
far-field layers 5. It drives the routes the 0.40.0 geometry and CCS lanes test
offline: the CCS curve route of a whole wing, a control surface declared in the
sidecar (deflected 10 deg against 0 deg), and the file route with Relaxed_TE
under AXIAL and AZIMUTH shedding.

The first pass wrote the section with the open-edge thickness law missing its
x^4 term (a 0.124 c blunt trailing edge), and the wing read CL -0.925 at
alpha 0. The second pass moved that one thing, the closed-edge law, and read:

| Row | Build | alpha | Status | CL | CMy |
|---|---|---|---|---|---|
| plain wing | 26.124 | 0 | CONVERGED | 0.0003 | -0.0012 |
| plain wing | 26.125 | 0 | CONVERGED | 0.0006 | -0.0012 |
| plain wing | 26.124 | 4 | FAILED_INCOMPLETE_OUTPUT | 0.2840 | -0.0129 |
| plain wing | 26.125 | 4 | FAILED_INCOMPLETE_OUTPUT | 0.2838 | -0.0128 |
| aileron 10 deg | 26.124 | 4 | CONVERGED | 0.4570 | -0.0485 |
| aileron 10 deg | 26.125 | 4 | CONVERGED | 0.4540 | -0.0479 |
| aileron 0 deg | 26.124 | 4 | CONVERGED | 0.2835 | -0.0116 |
| aileron 0 deg | 26.125 | 4 | CONVERGED | 0.2800 | -0.0110 |
| pod, AXIAL | 26.124 | 4 | CONVERGED | 0.0002 | 0.0050 |
| pod, AXIAL | 26.125 | 4 | CONVERGED | 0.0000 | 0.0053 |
| pod, AZIMUTH | 26.124 | 4 | MAX_ITER_REACHED (80) | -0.0226 | 0.0311 |
| pod, AZIMUTH | 26.125 | 4 | CONVERGED | -0.0171 | 0.0250 |

Against what the lanes' tests assume: every script those tests emit offline was
accepted and solved by both builds; the declared control surface moves the
wing (a 10 deg deflection adds 0.17 to CL and a nose-down moment) and its 0 deg
twin matches the plain wing within 0.004; the two builds agree within 1.3
percent. Two differences from the tests' picture:

- The second point of an alpha sweep is recorded FAILED_INCOMPLETE_OUTPUT on
  both builds with its loads present ("a collected solver log holds another
  number of solves than this point solved"): the solve-count check of the
  release head refuses every point after the first of a sweep. A release
  regression, not a CCS one. After its fix (a0be2112, merged with cd8d3647)
  rows 9101 and 9102 were run again in a fresh workspace: all four points
  CONVERGED, with the same loads (CL 0.2840 and 0.2838 at alpha 4).
- `pyfs-matrix run` warns that building a .csv geometry inside the run is a
  route the geometry stage replaces and 0.41.0 refuses; the campaign used it
  because the CCS rows of the lanes' tests do.

## 9. Physics on 26.125 (PFS-2084.006)

`pyfs-qa physics` on 26.125 wrote
`reports/physics/PHY-26125_2026-10-12_pressure-drag.yaml`. PHY-02 (half against
full symmetry) was measured and its 26.125 reference seeded from that report
through `pyfs-qa update-reference` (CL full 0.3385, CL half 0.3404, delta CL
0.0019, delta CDp 0.0001). PHY-01 and PHY-06 aborted on the same solve-count
check as section 8; PHY-05 (the rotor) was not planned, the workspace refusing
its blade alias ("the geometry lacks boundary 'Blade1'").

After both fixes (3fbdb589, a0be2112) the matrix ran again with all five rows
active and wrote `reports/physics/PHY-26125_2026-10-12_all-cases.yaml`: 11
points converged, PHY-02 passes its four metrics against its reference, and
PHY-01 (CL 0.3385 at 4 deg, slope 4.807 per rad), PHY-05 (the rotor) and PHY-06
(steady against unsteady, |delta CL| at most 0.0031) were seeded from it through
`pyfs-qa update-reference`. Every 26.125 physics case now has a reference.
