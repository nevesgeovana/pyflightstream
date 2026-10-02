# RPT-135 - The block reset of a cleaned geometry against a fresh import of FlightStream 26.124 (2026-10-02)

The paired measurement and the licensed confirmation of **FR-312** that pyflightstream
0.33.0 left owed (FR-312, "Evidence owed"), run after the 0.34.0 release as GOAL-039 arm
OC, run LQ-O3. Every launch ran on **FlightStream 26.124, build 8172026**, executable
SHA-256 withheld from the public tree per NFR-31, one solver instance at a time, hidden;
the three solves state far field 5 layers. The fresh imports are the tier-3 preparation
recipe rendered for 26.124; the solve script is the one pyflightstream 0.34.0 emits
(package tree at `ed06e86d`, no file changed). The run window is recorded for arm L1
(`licensed/LQ-O3.json`: 2026-10-02T14:34:39-03:00 to 2026-10-02T14:36:06-03:00).

Only nondimensional values are stated: block names, line counts, coefficients and relative
differences. The geometries are the ten synthetic shapes of the tier-3 library, generated
from public shape laws.

## 1. The question

FR-312, as the requirement states what is owed: "the dated report of that measurement (a
simulation carrying every block against the same mesh freshly imported with the same
boundary conditions, the builds compared named); tier-1 tests on recorded fixtures, each
with a control; and the licensed confirmation, on 26.124, that the solver opens and runs a
cleaned file (licensed round L1 of the 0.33.0 release), without which the claim of R1 is
unverified." R1: "Each block other than the meshes and the boundary conditions is reset to
the content a freshly imported file holds, measured block by block."

RPT-111 confirmed that 26.124 opens and runs a 26.124 save whose saved actions alone were
removed; the block reset was not exercised, because the released table is of 26.120
(build 7012026) saves only (FR-312 R2) and no fresh import of 26.124 was measured.

## 2. The case and the arms

| launch | what it is |
|---|---|
| fresh, ten | each tier-3 shape freshly imported on 26.124: the STL parts in metres, the unit set, the trailing edges and the wake termination nodes detected, saved; no solve |
| F | the blade's fresh import (F124) opened and solved: `unsteady_rotor`, advance ratio 1.7, 30 degrees a step, 12 steps, far field 5 layers. Its save is D, a simulation carrying every block |
| R | the same script opening R: D reduced by the package's own clean, with the 26.124 table measured here added in that process only |
| D | the same script opening D itself, uncleaned: the control |

The three solve scripts differ only in the file they open. The released package keeps
every block of a 26.124 file but its saved actions (FR-312 R2); K, D cleaned by
`pyfs-matrix inventory --clean` of 0.34.0 as released, is compared block by block and not
solved.

## 3. The paired measurement

The ten fresh imports (blade, blade_phy, body, halfwing, halfwing_phy, pusher, twin, wing,
wing_phy, wing_renamed) each exited with status 0 and saved a file stating build 8172026.
The blocks they hold with the same lines in all ten, the kept blocks and `MESH` left out,
are `ACOUSTIC`, `AEROELASTIC`, `GLOBAL`, `MOTION`, `POST`, `SOLVER`, `STABILITY` and
`WAKE`: the same eight blocks the released 26.120 table resets.

The 26.124 fresh-import table against the released 26.120 table:

| block | 26.124 lines | 26.120 lines | equal |
|---|---|---|---|
| ACOUSTIC | 10 | 10 | yes |
| AEROELASTIC | 8 | 8 | no, 1 line differs |
| GLOBAL | 31 | 31 | no, 2 lines differ |
| MOTION | 5 | 5 | yes |
| POST | 8 | 8 | yes |
| SOLVER | 58 | 56 | no, 2 lines differ |
| STABILITY | 2 | 1 | no, 1 line differs |
| WAKE | 13 | 13 | no, 1 line differs |

Block by block against F124, the blade freshly imported on 26.124 (line count, and whether
the block equals F124's):

| block | F124 | D | R | K | F120 (26.120 fresh import) |
|---|---|---|---|---|---|
| CAD | 5 | 5 same | 5 same | 5 same | 5 same |
| CADCREATE | 5 | 5 same | 5 same | 5 same | 4 differs |
| MESH | 41 | 41 differs | 41 differs | 41 differs | 41 same |
| GLOBAL | 31 | 61 differs | 31 same | 61 differs | 31 differs |
| WRAPPER | 5 | 5 differs | 5 differs | 5 differs | 5 same |
| PHYSICS | 29 | 29 differs | 29 differs | 29 differs | 24 differs |
| MOTION | 5 | 29 differs | 5 same | 29 differs | 5 same |
| POST | 8 | 8 differs | 8 same | 8 differs | 8 same |
| GRAPHICS | 51 | 51 differs | 51 differs | 51 differs | 51 same |
| WAKE | 13 | 268 differs | 13 same | 268 differs | 13 differs |
| SOLVER | 58 | 720 differs | 58 same | 711 differs | 56 differs |
| ACOUSTIC | 10 | 10 differs | 10 same | 10 differs | 10 same |
| STABILITY | 2 | 2 same | 2 same | 2 same | 1 differs |
| AEROELASTIC | 8 | 8 same | 8 same | 8 same | 8 differs |
| CADMESHING | 6 | 6 same | 6 same | 6 same | 6 same |

D carries 3 saved actions; R and K carry none. The clean that made R removed the three
(`pfs_unsteady_counter`, `pfs_walltime_clock`, `pfs_walltime_stop`) and reset `GLOBAL`,
`MOTION`, `POST`, `WAKE`, `SOLVER` and `ACOUSTIC`. K, the released clean, removed the same
three actions and reset no block: its standard error says that no fresh import of build
8172026 saved in METER is measured, so every block other than the saved actions is kept.

The boundary names of F124, D and R are the same, `Blade1` in each. `MESH`, which holds the
boundaries, differs between F124 and D and is kept by rule, as are `WRAPPER`, `PHYSICS` and
`GRAPHICS`.

## 4. The licensed confirmation

| arm | exit | steps | error-like lines | runtime commands a step | step counter | final Cx | final CDi |
|---|---|---|---|---|---|---|---|
| F | 0 | 12 of 12 | 0 | 2.0 | 12 | -0.0419517 | -0.0423971 |
| R | 0 | 12 of 12 | 0 | 2.0 | 12 | -0.0419517 | -0.0423971 |
| D | 0 | 12 of 12 | 0 | 4.0 | 24 | -0.0419517 | -0.0423971 |

Each log names build #8172026 and says "Simulation file saved in version: 26.1, build
#8172026 and opening in version: 26.1, build #8172026".

| comparison | final, worst relative difference | plot rows that differ |
|---|---|---|
| derangement, F row k vs k + 1 | | 11 of 11 (worst 1.061e+00) |
| R vs F | 0 | 0 of 12; runtime commands 24 vs 24, counter 12 vs 12 |
| D vs F (the control) | 0 | 0 of 12 on the columns both carry; runtime commands 48 vs 24, counter 24 vs 12, plots columns 45 vs 23 |

D's plots export holds 45 columns: the time step and each of the 22 force plots twice, under
the same names. The package's reader of the plots export (`parse_unsteady_plots`) refuses
that file, naming the repeated columns; F's and R's exports hold 23 columns and are read.
The plot rows are compared on the columns both exports carry, the first of each repeated
name.

## 5. Verdict

- The paired measurement: a 26.124 solve leaves 10 blocks different from the fresh import
  (`MESH`, `GLOBAL`, `WRAPPER`, `PHYSICS`, `MOTION`, `POST`, `GRAPHICS`, `WAKE`, `SOLVER`,
  `ACOUSTIC`); the reset to the 26.124 fresh import puts back `GLOBAL`, `MOTION`, `POST`,
  `WAKE`, `SOLVER` and `ACOUSTIC` and leaves `MESH`, `WRAPPER`, `PHYSICS` and `GRAPHICS`,
  all four kept by rule (the meshes, and the blocks that differ between the ten fresh
  imports).
- The builds compared: the 26.124 fresh import differs from the 26.120 one in
  `AEROELASTIC`, `GLOBAL`, `SOLVER`, `STABILITY` and `WAKE` of the table, and in
  `CADCREATE` and `PHYSICS` outside it; a table of one build is not applied to the other
  (FR-312 R2), as measured.
- The confirmation: 26.124 opened and ran the block-reset file, 12 steps, no error line,
  its results identical to the fresh import's (final loads and every plot row). The
  uncleaned file gives the same loads, so on the numbers the control cannot say different;
  it differs in what its saved actions add: twice the runtime commands (48 against 24), a
  step counter of 24 for 12 steps, and 45 plots columns against 23, a plots export the
  package's reader refuses. The block-reset file matches the fresh import on each of those.

What follows for FR-312: the licensed control discriminates the saved actions only (the
uncleaned file's loads equal the fresh and reset files'); the block content of the reset is
verified block by block offline (section 3), and the solve confirms that the block-reset
file opens and runs on 26.124, for the blade, with the 26.124 table given to the package's
reset in-process. Registering that table in
`pyflightstream._fsm_fresh.FRESH_IMPORT` is a change in `src/`, which a post-release commit
of 0.34.0 may not make (GOAL-039, POST_SRC_ALLOWED); it is 0.35.0 scope (GOAL-040), with
the recorded fresh imports as its tier-1 fixture. The tier-1 test
`tests/tier1_offline/test_rpt135_fr312_fresh_import_26124.py` re-measures the table from
the recorded fresh imports, compares it with the 26.120 one, resets the recorded D with it
against the fresh import (D before the reset as the control) and pins the released
behaviour, which keeps every block of a 26.124 file.

## 6. What this does not show

- One solved geometry (the blade); the table is the content common to ten fresh imports
  made by one recipe, as the 26.120 table is.
- STL imports in metres only; a CAD import and other units are not measured.
- The block reset of the released 26.120 table is exercised offline (a cleaned 26.120 save
  is the committed fresh import byte for byte), not by this run.
