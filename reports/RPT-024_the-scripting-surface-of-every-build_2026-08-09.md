# RPT-024: the scripting surface of every build (2026-08-09, amended 2026-08-10)

What each registered FlightStream build documents as its scripting
command set, and what changed from one build to the next. Command names
only; nothing of the manual's text appears here or in the tool that
produced it.

## What is regenerated and what is written by hand

The LAST two sections, `Command surface per edition` and `What changed
between consecutive builds`, plus the coverage line that closes the
report, are the verbatim output of

```
pyfs-manual surface --editions <manifest> --names --markdown
```

reading the local edition manifest, so re-running it after a new install
arrives refreshes them. The manifest is local because it names licensed
manual paths; registering a build is adding a row to it.

Every section ABOVE those two is written by hand and does not refresh.
Re-running the command replaces the tail; the head has to be re-read.
Said plainly because "regenerated" invites the opposite assumption, and
a stale hand-written section under a freshly generated table is the
worst of both.

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

AMENDED 2026-08-19, and the amendment is a DIRECTION rather than a
correction. The index errs both ways and the other way is now on record:
the 26.123 edition lists `TRAILING_EDGES_IMPORT` in its Script Index
while its chapter body no longer prints the command at all, the block
having stood in the edition before it. So for that edition an
index-driven reading would report a command the body has dropped, which
is the mirror of the failure above. The rule does not change and the
body is still what is read; what changes is that a disagreement between
the two is not by itself evidence of which one moved, and `PFS-2026.04`
is the node that owes that reading.

## Cross-checked against the command database

RE-READ 2026-08-10, and the previous version of this section is why the
note at the top of this report exists. It described four builds under a
table regenerated for eight, which is exactly the stale hand-written
section under a fresh table that the note warns against.

Two directions, and they are different questions.

**Manual to database, now measured rather than asserted.** Every command
every edition documents has an entry: `pyfs-manual sweep` reports zero
absent across all eight. The previous wording stopped there, and
stopping there was the error, because that measure compares entry NAMES
and cannot see an entry missing one edition's ROW. It reported zero
while three builds could not emit `EXPORT_ALL_SURFACE_STREAMLINES`. The
sweep reports both halves now, and the second currently names ten
readings deliberately withheld across four commands whose older editions
use a layout a version row cannot express (PLN-20260810-1200), and
nothing else.

**Database to manual**, counting every command carrying an evidence row
for that build, direct or inherited, `removed` rows included:

| Build | Manual | Rows | Rows with no page in that manual |
|---|---|---|---|
| 25.000 | 272 | 268 | 0 |
| 25.100 | 274 | 278 | 8 |
| 26.000 | 276 | 283 | 9 |
| 26.100 | 344 | 361 | 17 |
| 26.101 | 363 | 380 | 17 |
| 26.120 | 363 | 381 | 18 |
| 26.121 | 364 | 387 | 23 |
| 26.122 | 372 | 397 | 25 |

The last column grew from eleven to a hundred and seventeen, and the
growth is one cause rather than a new disagreement. Eighty-one `removed`
rows were written on 2026-08-10 for the commands only the pre-26.100
editions document, each recording that a later edition stops printing
the command. Every one of them counts here as a row whose build's manual
does not document it, which is arithmetically right and is the database
agreeing with the sweep in its own vocabulary rather than contradicting
it. The three other causes the previous version named, inheritance on a
hotfix, an entry resting on a probe rather than a page, and one command
probed broken on a build whose manual is silent, all still stand and are
a small remainder beside that.

25.000 is the only build with a zero in that column, which is what the
START of the registered series looks like: nothing later has stopped
printing anything for it.

The cross-check is still not a committed subcommand and was run by hand;
regenerating it is PLN-20260809-2400. What IS committed now is the
row-level half of the first direction, which is the part that was
silently wrong.

## 25.000 is measured, and not by this tool

The 25.000 install ships its manual only as a compiled HTML help
archive, and `pyfs-manual` reads pdf, so that build had no row in the
manifest when this report was first written and did not appear in the
generated sections below.

THAT IS NO LONGER TRUE, and the paragraph is corrected rather than
rewritten because the reason it changed is the useful part. On
2026-08-10 the archive was converted to a pdf whose pagination is
reproducible (`scripts/chm_to_pdf.py`, registered as SRC-749) and the
build joined the manifest, so the generated sections below cover every
registered build. The figure below was measured before that, from the extracted
topics directly, and the two readings agree at 272.

One error of the first writing is corrected here too. It said the
archive extracts to 960 HTML topics. 960 is the number of FILES, images
and stylesheets included; the topics are 154, which is what the
archive's own table of contents lists.

Its surface was measured separately. The archive was extracted with
7-Zip; tags were stripped from each topic, entities unescaped, and the
same signature heading counted, the string the pdf parser keys on. That
yields:

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

Read that pair together rather than as two lists. Several entries look
like renamings rather than removals and additions: the four
`CREATE_NEW_MOTION_*` commands against one `CREATE_NEW_MOTION`,
`SOLVER_CLEAR` against `CLEAR_SOLUTION`, and `SOLVER_UNINITIALIZE`
against `REMOVE_INITIALIZATION`. Say LOOK LIKE and mean it: no probe has
shown that the new name does what the old one did, and a name is not
behaviour. What the pairing establishes is where to point a probe, not
what it will find.

TWO INSTRUMENTS, NOT ONE, when this was written: the 272 came from an
ad-hoc count over extracted HTML while every other count came from the
package's own fixtured pdf parser, and no install shipped both formats,
so the two had never been calibrated against each other.

THEY HAVE BEEN NOW, and the calibration is the reason to trust the
number rather than merely to state it. Converting the archive to a pdf
put both instruments on one document, and the package's own parser
finds 272 commands in it, the same 272 the HTML count found. The
uncertainty that rode on the 25.000 to 25.100 delta and on the "272 to
364" span is measured and is zero for this document.

The conversion is not free of assumptions and they are recorded where
the citations point, in the `manual_editions` entry for SRC-749: the
page numbers depend on the renderer, so the script strips what makes
its output unique and two runs give byte-identical bytes, and the hash
is recorded so a different renderer shows up as a different file rather
than as quietly different page numbers.

## The shape of the whole history

The surface grew from 272 to 372 across eight builds, on one instrument
since the calibration above, and it did not grow smoothly. One step
accounts for most of it: 26.000 to 26.100 gained 75 commands,
essentially the whole CAD and cross-section family arriving at once. The
next step, 26.100 to 26.101, is the one to be careful with: 35 gained
and 16 lost between two builds the vendor ships under the SAME release
name, "26.1". A reader who recorded only that name in a paper cannot
tell which of those two surfaces was available to them.

The eighth build was added on 2026-08-10, the day after the vendor
issued it, and the tail below was regenerated to include it; this
section was re-read rather than left, which is what the note at the top
of this report requires. Its step is the second largest of the history
in proportion, 10 gained and 2 lost, and it is the clearest case in the
report of why a diff of names is evidence for a question rather than an
answer to one. Two of its ten gains stand where its two losses stood.
`SURFACE_ROTATE` gives way to `ROTATE_SURFACE` and
`SET_TRAILING_EDGE_BLUNTNESS_ANGLE` to
`SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE`. Counted mechanically that is
twelve changes; read on the page it is eight new commands and two
replacements, and the rotation replacement is not even a like-for-like
one, being an inline call of five arguments where the old one was a
keyword block of eight.

The two 25 builds and 26.000 differ from each other by single digits,
so a script written for one of them is close to portable across the
three; the boundary that matters in that range is not the command set
but the command line, where the 25 series and 26.000 disagree
(RPT-023).

## Command surface per edition

| Build | Commands documented |
|---|---|
| 25.000 | 272 |
| 25.100 | 274 |
| 26.000 | 276 |
| 26.100 | 344 |
| 26.101 | 363 |
| 26.120 | 363 |
| 26.121 | 364 |
| 26.122 | 372 |

## What changed between consecutive builds

### 25.000 to 25.100

Gained 10, lost 8.

Gained: `CLEAR_SOLUTION`, `CREATE_NEW_MOTION`, `DISABLE_WAKE_NODES_ON_TRAILING_EDGE`, `OUTPUT_SETTINGS_AND_STATUS`, `REMOVE_INITIALIZATION`, `REYNOLDS_AVERAGED_DRAG_FORCES`, `RUN_SCRIPT`, `SELECT_BASE_REGION_FACES`, `SELECT_MESH_NODE`, `TRANSFORM_SELECTED_NODES`

Lost: `BOOLEAN_UNITE_GEOMETRY`, `CREATE_NEW_MOTION_6DOF`, `CREATE_NEW_MOTION_CUSTOM`, `CREATE_NEW_MOTION_EUCLIDEAN`, `CREATE_NEW_MOTION_FSI`, `SET_SOLVER_MODEL`, `SOLVER_CLEAR`, `SOLVER_UNINITIALIZE`

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

### 26.121 to 26.122

Gained 10, lost 2.

Gained: `DELETE_BL_VELOCITY_PROFILE`, `DETECT_LEADING_EDGES_WAKES_BY_SURFACE`, `EXPORT_BL_VELOCITY_PROFILE`, `IMPORT_WAKE_EDGES_FROM_FILE`, `ROTATE_SURFACE`, `SET_ACTUATOR_WAKE_TYPE`, `SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE`, `SET_NEW_UNSTEADY_SOLVER_ACTION`, `SET_OUTFLOW_TRAILING_EDGES`, `SOLVER_TIME_AVERAGING`

Lost: `SET_TRAILING_EDGE_BLUNTNESS_ANGLE`, `SURFACE_ROTATE`


Coverage: 8 of 8 registered build(s) read.
