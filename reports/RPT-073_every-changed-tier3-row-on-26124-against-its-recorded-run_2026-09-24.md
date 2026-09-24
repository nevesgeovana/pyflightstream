# RPT-073: every changed tier-3 row on 26.124 against its recorded run (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed test T12 of the 0.27.0 work
**Status:** VERIFIED in 0.27.0 (T12: the 76 point scripts that changed since 0.26.0 ran on 26.124; each converged, or completed its declared time steps, and collected every declared output, and the 83 licensed checks over the run pass. Against the recorded runs, the deltas above 5 percent come from the build, the far field and four changes the rows took since then. The comparison also found a defect of the tier-3 inputs, row 1022's rotor hubs 1.5856 m from its blades since 0.15.0, fixed in 0.27.0 at af13e23c; the nine points it moved ran again)
**Affects:** every tier-3 matrix on 26.124; `SOLVER_SET_FARFIELD_LAYERS`, `CLEAR_SOLUTION`, `DETECT_BASE_REGIONS_BY_SURFACE`, `SET_MOTION_ROTOR_RPM`, `SET_MOTION_COORDINATE_SYSTEM`, `SET_NEW_UNSTEADY_SOLVER_ACTION`

## What this settles

T12 re-runs on 26.124 every tier-3 point whose script changed in 0.27.0, and
holds each against what was recorded before. The points are not chosen by hand:
they are the tier-3 `.txt` paths of `git diff --name-only v0.26.0 <head> --
tests/tier1_offline/goldens tests/tier3_licensed/goldens`, 76 at 2a7ba141. They
are the same 76 at 7ae26337 and at af13e23c: the source changes after 2a7ba141
(three refusals at plan and at collect) move no golden, and af13e23c moves nine
goldens that are already among the 76. The pass condition was fixed before the
run. Every point converges, or completes its declared time steps if it is
unsteady, and collects every output it declares. A coefficient that moves more
than 5 percent from its recorded run is a finding to investigate, reported with
the two causes known in advance: every setup now states
`SOLVER_SET_FARFIELD_LAYERS 5` where the records stated none or three, and every
build id now runs on the 26.124 executable where the records ran 26.120 or
26.123. **All 76 points pass, and the 83 licensed checks pass. Where a point has
a recorded run, its deltas above 5 percent come from the build, the far field,
and changes the rows took since their records: a base region now marked, a
rotor turning the hand its reference declares, a setup rewritten, a steady sweep
that now starts each point warm. The comparison also found a defect of the
tier-3 inputs: from 0.15.0, row 1022 and the six vocabulary rows turned their
rotors about hubs 1.5856 m from their blades. It is fixed in 0.27.0 (af13e23c),
and the nine points it moved ran again within the pass condition.**

## What was run

FlightStream 26.124 (build 8172026, executable sha256 68e64e66...), detached,
one solver at a time, no solver alive before each launch, in a fresh copy of
`tests/tier3_licensed` with no run state. A local executables overlay sent every
build id the rows name (26.120, 26.123 and 26.124) to the 26.124 executable. No
committed `FS_BUILD` changed, so `matriz_builds` keeps its meaning.

- **The points.** 76 point scripts in eleven matrices: 60 whose goldens changed
  since 0.26.0, and 16 added since then (the eight of `matriz_mesh`, the eight of
  `matriz_gui`). They are 66 solving scripts, because five steady rows are each
  one job over several points (FR-95). All 66 state
  `SOLVER_SET_FARFIELD_LAYERS 5`.
- **The scripts are the release's.** Each script the solver received was
  compared with its point's golden at af13e23c, with the workspace path made
  portable. 51 are equal line for line. 10 differ only in how a path is spelled
  (the interpreter of an action, a staged file). The five sweep jobs carry their
  goldens' commands, plus `CLEAR_SOLUTION` (1003) and `DELETE_VOLUME_SECTION 1`
  between the two points of 5007.
- **The sequence.** The eleven matrices ran one after another from 14:22 to
  14:33. Three rows were re-run at 15:10, each with `--force-rerun` and its first
  outputs archived. 1090 and 6001 were re-run because their test recipes had not
  handed the setup's far field to the script helper, so their first scripts had
  no `SOLVER_SET_FARFIELD_LAYERS` line (fixed at 159851cf, which moved their three
  goldens and widened the tier-1 guard to every matrix). 1003 was re-run because
  it now states `COLD_START: true` (d2b78f0e, below). Row 6001 ran once more at
  15:13 (see the licensed checks). An attempt at 15:07 was refused at plan,
  before any solve, because the copy's root was not on the path the recipe rows
  import from. After af13e23c (below), 1022 and the eight points of 8001 to 8006
  ran again at 15:49, the same way.
- **The package.** 0.27.0.dev7. The first pass ran source equal to 2a7ba141's.
  The 15:10 and 15:13 re-runs imported the package at e305d21e. Its source
  differs from 2a7ba141's only by G06 (the actuator profile's copy) and G16
  (POLAR leaving the tables), and none of the three rows uses either. Their
  scripts are among the 51 equal to the goldens (1090, 6001) or carry the
  goldens' commands (1003). The 15:49 re-run imported the package at f2d91ea9
  (0.27.0), whose source equals af13e23c's; its nine scripts are among the 51.

## What came back

### Every point ran and collected what it declares

| matrix | points | CONVERGED | COMPLETED_MAX_ITER |
|---|---|---|---|
| `matriz` | 18 | 17 | 1 (1022) |
| `matriz_setup`, `matriz_time`, `matriz_geometry` | 16 | 16 | |
| `matriz_physics` | 11 | 11 | |
| `matriz_actions` | 2 | 1 | 1 (6001) |
| `matriz_builds`, `matriz_rotate` | 5 | 5 | |
| `matriz_vocab` | 8 | 1 | 7 |
| `matriz_mesh`, `matriz_gui` | 16 | 16 | |
| **all** | **76** | **67** | **9** |

The nine COMPLETED_MAX_ITER points are all unsteady. Each log shows the time
loop reaching its last declared step (6 of 6 for 1022 and the seven vocabulary
points, 8 of 8 for 6001), with the final residual above the convergence limit.
That is what the status means for an unsteady run with a log. 1022 and 6001
read the same status in their records; the vocabulary rows have no record. No
point FAILED, and all 596 outputs the 76 records list are on disk.

### The licensed checks

`pytest tests/tier3_licensed` over the run's workspace:

- **First pass: 24 failed, 59 passed.** 23 were the checks' own expectations,
  most of them older than 0.27.0: the layout of 0.16.0 on, the point names of
  0.21.0, the build registry read under an overlay, a copy outside Git. They
  were rewritten at 2b48b3fc, each to the behaviour the release that changed it
  documents. **One of those 23 was not stale.** 1022's check asserted the rotor
  hubs at y = +2.5 and -2.5 m, which is where the twin geometry's blades are.
  2b48b3fc rewrote it to r006's +/-0.9144 m, and af13e23c set it back (the first
  item under "What it means for the package"). The 24th failure was 1003's
  side-force antisymmetry: 5.31 percent against its 5 percent band.
- **After the 15:10 re-runs: 1 failed, 82 passed.** The failure was 6001's action
  probe reading "Invocations: 16". The probe's own log and numbered exports are
  the fixture's files, not the row's collected outputs, so `--force-rerun` did
  not archive them, and the re-run's eight invocations were appended to the
  first run's eight. Both runs' files were moved into the simulation folder's
  `probe-archive/`, with nothing deleted, and 6001 ran once more: eight
  invocations. Each run of the probe needs its files moved aside first.
- **After the 15:13 run: 83 passed, 0 failed.**
- **Final, after af13e23c and the 15:49 re-run: 83 passed, 0 failed.** 1022's
  check asserts the hubs at (2.5, -2.5) again. The 14 warnings are of four kinds:
  an unregistered pytest mark, a dependency's deprecation, 6002's probe series
  not written (an unsteady row has exported no probe points since 0.25.0), and
  6001's loads export stating a reference area of 1 where the products would
  state 8 (its recipe writes the solver settings itself).

### Against the recorded runs

The control is the tier-3 workspace's recorded runs of 2026-09-08 to
2026-09-13: 52 points, 44 on 26.120 and 8 on 26.123, package 0.13.0.dev0 (48)
and 0.18.0.dev0 (4). Every record's script is on disk with the digest its record
states. 32 of those scripts stated no far field, 19 stated three layers, and
one (5005) stated five. The source read on both sides is each matrix's
`campaign_sweep.csv`, whose data origin, reduction, frame and units agree for
every pair. Where a delta had to be located, the per-surface lines of the two
loads exports were read. The records carry no rotor table, so rotor rows are
compared on the same totals (on a blade-only row, Cx and CMx are the rotor's
axial force and torque coefficients).

- **52 points compared.** 16 more have no record because their rows are new in
  0.27.0 (mesh and GUI). Their T12 coefficients equal, to the print, the numbers
  RPT-069 to RPT-072 published for the same rows on 26.124 earlier the same day.
  8 more (the vocabulary rows) had goldens at 0.26.0 but no recorded run.
- **145 deltas above 5 percent** on coefficients at or above 1e-3, and 92 more
  on coefficients below 1e-3 on both sides: a symmetric wing's Cy and CMz at zero
  sideslip, a rotor's CL, Cz and CDo at zero incidence. There the relative delta
  is noise; the largest absolute delta is 6.1e-4 (a pusher's Cy). All 237 are in
  the evidence file with their causes.

**The two known causes, measured apart.** Two rows separate them. Their first
attempts ran on 26.124 with no far-field line, which means the same commands, in
the same order, as their records:

| row (reference area 1, four decimals) | record, no far field | T12 first, 26.124, no far field | T12 re-run, 26.124, far field 5 |
|---|---|---|---|
| 1090 at 0 deg (26.120) | CL 0.0313, CMx 0.0136, CMy -0.0146 | CL 0.0578, CMx 0.0186, CMy -0.0256 | the same to the print |
| 1090 at 2 deg (26.120) | CL 1.3375, CMx 0.0135 | CL 1.3427, CMx 0.0180 | the same to the print |
| 6001 at 2 deg (26.123) | CL 1.4798, CMx 0.0181, CMz 0.0010 | CL 1.4857, CMx 0.0234, CMz 0.0015 | CL 1.4857, CMx 0.0232, CMz 0.0014 |

On this wing it is the build that moves the loads. Stating five layers where
none was stated moves them by at most two units of the last printed decimal.
Rows 2001 (recorded on 26.120) and 2004 (26.123) move by the same amount (CMx
0.0017258 and 0.0017259, both to 0.0021894), so the change arrived with 26.124.

| rows | what differs from the record | deltas above 5 percent |
|---|---|---|
| 1001, 1003, 1004, 2001 to 2004, 4001, 4004 (the full wing) | build; far field none to 5; the later points of 1001 and 1004 warm | CMx +24 to +50 percent (from 0.0016 to 0.0018 on the rows at zero sideslip), +105 at 1004's warm second point; CMy +9 at 4 deg, -43 to -67 near its zero crossing; Cx +6 to +8; CDi +6 to +10 below 4 deg; CL at 0 deg from 0.0039 to 0.0072 and 0.0075 |
| 1002, 4002 (the mirrored half wing) | build; far field none to 5 | CDi +14.5, Cx +31.8, CMy +19.3 percent (CL -4.1) |
| 1090, 6001 (the recipe rows) | build, as measured above | CL at 0 deg, CMx, CMy and CMz, as above |
| 5001, 5006 (the physics wing, four decimals) | build; far field none to 5; 5001 warm after its first point | CL at 0 deg from -0.0004 and 0.0000 to 0.0023 and 0.0031, CMy there from 0.0001 and 0.0000 to -0.0014 and -0.0016; CMx +22 to +75 percent at 0.0007 to 0.0014; Cx and CDi by one or two units of the last decimal |
| 1010, 1011, 3010, 3011, 6002 (the unsteady wing) | build; far field 3 to 5 | CDi +7, Cx +6, CMx +29 percent |
| 1020, 3001 to 3006, 7001, 7002 (the blade) | build; far field 3 to 5 | none at or above 1e-3 (axial force -2.0 to -3.5, torque -2.4 to -4.3 percent) |
| 5005 (the periodic propeller) | build; far field already 5; its script now states 300 iterations for 500, 10 convergence iterations for 20, a stabilization of 1.0, and no wake-termination time steps | none at or above 1e-3 |
| 1005, 4003 (the blunt body) | base region now marked (RPT-066); build; far field none to 5 | CDi 0.0499 to 0.2553 and 0.0493 to 0.2554, Cx 0.085 to 0.298 and 0.297, CDo +21 and +14 percent; Cy, CMy, CMz of other sizes or signs |
| 1021 (the pusher behind the body) | base region now marked; build; far field 3 to 5 | axial force and torque -7.6 and -8.8 percent in size; Cy from +0.0014 to -0.0003 |
| 9001 to 9003 (the pusher, turned) | rotation hand reversed since 0.22.0; base region now marked; build 26.123 to 26.124; far field 3 to 5 | axial force -15, torque -38, CDo -60 percent; 9002 CL -12.6; Cy and CMz of other sizes or signs |
| 1022 (twin rotors, after af13e23c) | build; far field 3 to 5; the hubs where the record had them (below) | none on the axial force (-2.4 percent in size); CL and Cz -13 percent in size, CDo -17.5, CMy -24 percent; Cy +37 percent in size (-0.0015 to -0.0020); CMx and CMz (-0.0014 and +0.0018 before) change sign |

### Row 1003, warm and cold

T12's first pass ran 1003 warm, the default since 0.16.0 (FR-95): one script,
with each later point starting from the previous point's solution. Its side force
missed its antisymmetry band. One licensed probe moved that one thing: row 1003
alone, `COLD_START: true`, in a separate fresh copy, with the same build,
package and far field.

| row 1003, BETA -4, 0, +4 | Cy | CMz at 0 and +4 | sum over Cy(+4) | iterations |
|---|---|---|---|---|
| warm, T12's first pass | +0.000476, -0.0000242, -0.0005027 | -0.00046, -0.00051 | 5.31 percent | 66, then 23 and 27 more |
| cold, the probe | +0.000476, -0.0000099, -0.0004883 | +0.00021, +0.00015 | 2.52 percent | 66, 67, 67 |
| cold, T12's re-run of the row as committed | the probe's, to the last digit | | 2.52 percent | 66, 67, 67 |
| the record (26.120, no far field, cold) | +0.000471, -0.0000033, -0.0004864 | +0.00016, +0.000065 | 3.17 percent | 66, 68, 67 |

The warm run's first point equals the cold run's to the last digit. Its later
points' CL is 1.8 and 3.0 percent above cold, and its CMz takes the other sign.
The band was set on points that each started cold, so the row now states
`COLD_START: true` (d2b78f0e) and its check passes on the cold re-run. The same
comparison on an alpha polar is in the run too. 1001's fourth point (4 deg,
warm after -2, 0 and 2 deg) receives the same commands as 4001 at 4 deg, which
ran cold. Warm against cold: CL 0.3298506 against 0.3293351 (+0.16 percent), CDi
0.0287527 against 0.0288962 (-0.5 percent), CMy equal to 3e-7, CMx 0.0025827
against 0.0021894 (+18 percent). The warm point took 48 iterations after the
previous one; the cold point took 63. The warm sweep's own difference is
registered for 0.28.0 (R13), where the default is still an open decision. This
report does not decide it.

## What it means for the package

- **Row 1022 and the six vocabulary rows turned their rotors 1.5856 m from their
  blades; fixed in 0.27.0.** From 0.15.0 (41bbb1c7), row 1022 and rows 8001 to
  8006 named r006, whose PORT and STARBOARD blocks put the hubs at
  (4.5, +/-0.9144, 0) m. The geometry they open, `41_TWIN.fsm`, carries its
  blades at (4.5, +/-2.5, 0) m: the points the recipe built it on, and the
  reference points ERP1 and ERP2 the 0.13.0 row turned its motions about. So each
  blade turned about an axis 1.5856 m inboard of its hub. The package emitted
  what the rows stated; the defect was in the tier-3 inputs, and no check held
  it, because 1022's check, which asserted `ORIGIN_Y 2.5`, failed in T12's first
  pass and was rewritten at 2b48b3fc to assert r006's hubs. T12 found it in the
  comparison with the record. The record put the thrust on the blades (Cx
  -0.7823 and -0.7772, the body +0.0056). The first pass put Cx -7.3899 on the
  body, with its CL, Cy and CDo at exactly zero, and +0.0001 on each blade, and
  8001 carried Cy +2.08 at zero sideslip. **af13e23c** puts r006's hubs at
  y = +2.5 and -2.5 m, and 1022's check asserts (2.5, -2.5) again. Nine goldens
  moved by their `ORIGIN_Y` line, all of them already among the 76, and the nine
  points ran again at 15:49. 1022 read COMPLETED_MAX_ITER at 6 of 6 time steps,
  as its record did; 8001 to 8004 and 8006 read COMPLETED_MAX_ITER and 8005
  CONVERGED, each at 6 of 6. 1022's blades carry the thrust again (Cx -0.7605
  and -0.7617, the body +0.0052). Its total axial force is 2.4 percent below the
  record's in size (Cx -1.5171 against -1.5539), inside the blade rows' -2.0 to
  -3.5 percent, and its deltas above 5 percent are the small coefficients in the
  table above. At zero sideslip, 8001 now carries Cy +0.0016.
- **26.124 moves the wing's lift at zero incidence and its rolling moment.** On
  1090, where the build is the only change, the NACA 0012 wing's CL at 0 deg
  moves from 0.0313 to 0.0578 on a reference area of 1. That is about the shift
  1001 shows on the wing's 8 m2 (0.0040 to 0.0075). CMx moves +33 and +37
  percent (+29 on 6001). 26.120 and 26.123 agree with each other. The commands
  are the same, so the package does not cause it, and what changed inside 26.124
  is not established here. PHY-01 bands the lift at 0 deg in absolute terms
  (warn 0.005, fail 0.02, around -0.0004), and the physics wing's 0.0023 sits
  inside the warn band. No licensed check reads 1001's or 1003's lift at 0 deg.
  The mirrored half wing moves the most (CDi +14.5 percent).
- **A marked base region adds the base's drag.** 1005 and 4003 are the first
  solves of these rows with a base region. RPT-066 measured what the command
  marks, not a solve. The Base boundary, which carried nothing (Cx 0.0000074),
  now carries Cx 0.2029636, almost all of the change; the body's own CDi moves
  +4.9 and +7.3 percent. On 1021 and 9001 to 9003 the base adds about 0.015 in
  Cx.
- **The pusher of 9001 to 9003 turns the hand its reference declares.** Since
  0.22.0 the script sends `SET_MOTION_ROTOR_RPM 1 -800.0` for r007's
  `rpm_sign = -1`, where the record sent +800. On 9001 the blade's axial force
  falls from -0.748 to -0.655, its torque from -0.215 to -0.133 and its CDo from
  0.0100 to 0.0019. Those rows' deltas are the corrected hand, the base, the far
  field and the build together.
- **`SET_NEW_UNSTEADY_SOLVER_ACTION` ran on 26.124.** In each of 6001's three
  runs of eight time steps: eight invocations, no arguments, no solver-named
  environment, the point's datapoint folder as the working folder (0.27.0), and
  exports stamped `_iteration=1` to `_iteration=8`. The files give re-read
  verdict YES, as RPT-041 measured on 26.123. The command database's 26.124 row
  still reads "not run on 26.124". This report is evidence available for that
  row, and it does not edit the row.

## What this does NOT establish

- Which change inside 26.124 moves the wing's lift at zero incidence and its
  rolling moment; only that the build does it and the package and the far field
  do not, on the rows that separate them.
- The far field's own share where the records stated three layers (the unsteady
  wing, the blade, the pushers, the twin rotors). No T12 run held the build and
  moved only the far field there.
- Whether the base drag the marked region now adds is the right size for these
  bodies.
- The 9001 to 9003 deltas cause by cause: the hand, the base, the far field and
  the build moved together.
- Any comparison for the vocabulary rows, which have no record.
- Whether a steady sweep should start each point warm or cold (R13).

## Evidence

`reports/probes/RPT-073_2026-09-24_evidence.yaml` holds: the 76 golden paths as
the diff selects them; each point's status, iterations and outputs; the 66
scripts' digests and those of the replaced attempts; the pytest summaries;
every delta above 5 percent grouped by cause, and the near-zero ones; the
one-thing pairs; the 1022 defect, its fix and its re-run; row 1003's warm, cold
and recorded values; and the action counts. The checks are
`tests/tier3_licensed/` at af13e23c. The far-field line in every matrix, a
recipe row's included, is held offline by
`tests/tier1_offline/test_tier3_offline.py::test_every_solving_script_of_every_matrix_states_five_farfield_layers`.
The solver outputs stayed on the measuring machine (invariant 5).

**Verdict: VERIFIED.** Every point whose script changed since 0.26.0 converged,
or completed its declared time steps, on 26.124, and collected every declared
output, and the licensed checks pass, 83 of 83. Against the recorded runs, the
deltas above 5 percent come from the build, the far field, and changes the rows
took since then. The comparison also found row 1022's rotor hubs 1.5856 m from
its blades since 0.15.0; af13e23c fixed them, and the nine points it moved ran
again within the pass condition.
