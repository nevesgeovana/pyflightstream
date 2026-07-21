# HND-019: legacy case reproduced through the library (2026-07-21)

## 1. Context

Same-session continuation after HND-018, on Geovana's instruction:
seed `fts_sim` in her research workspace as the pyflightstream-based
successor of the legacy driver, reproduce its POLAR-9001
run (isolated propeller, one resolved blade under PERIODIC 6, 54
unsteady steps, 1440 per-step monitors), and prove not only matching
results but matching outputs. A parallel session works the M6/FSI
line in this repository; this handoff stages and commits only the
reproduction-driven changes.

## 2. Reproduction verdict

Same solver build as the ground truth (26.12 build 7012026). After
the phase corrections below, `compare_9001.py` judges:

* loads spreadsheet, surface sections (cp), sectional loads, probe
  values, and the 1440-column per-step plots: zero substantive
  differences (only path and date lines). Every per-step sample over
  54 steps is bit identical, so the resolved flow is the same flow.
* log: equal except wall-time, memory, and path lines.
* saved .fsm: byte-identical size, 0.018 percent of bytes differing
  (timestamps, paths, export noise).
* tecplot .dat: 438 numbers at worst 2.2e-7 relative difference; the
  differing set changes between two runs of the same script, so it
  is export-time parallel accumulation noise, not a defect.
* generated script, canonical comparison: 7518 of 7521 content lines
  shared; the only differences are the legacy duplicated
  REF_AREA/REF_LENGTH pair and the two undocumented trailing zeros
  of its SET_MOTION_ROTOR_RPM line, both documented as deliberate.

## 3. What the comparison forced into the library

1. Backfill of 11 commands with SRC-003 citations (Advanced Settings
   pp.344-345; Unsteady Solver monitoring plots and export
   pp.347-348, new chapter; Scenes p.355, new chapter;
   ROTATE_COORDINATE_SYSTEM p.330; SET_SIGNIFICANT_DIGITS p.284);
   OPEN accepts LOAD_SOLVER_INITIALIZATION DISABLE. Database at 129
   commands.
2. Phase corrections on empirical evidence: SET_ANALYSIS_SYMMETRY_LOADS
   analysis -> init (the per-step force plots sample with its state
   during the solve; the post-PERIODIC default is ENABLE, recording
   six-fold copy sums until the setting preceded START_SOLVER;
   extends the HND-013 post-MIRROR calibration), and
   NEW_SURFACE_SECTION_DISTRIBUTION analysis -> init (cut planes
   freeze at creation; created post-solve, the blade sections landed
   at the final azimuth with a different point count). PHY-02, the
   analysis_setup helper, and both probe specs follow; PHY-02
   revalidated on the solver, 4 pass, values identical
   (`PHY-26120_2026-07-21_phy02-symmetry-phase-reval`).
3. PLN-012 progress: NEW_SURFACE_SECTION_DISTRIBUTION works pre-solve
   with the undocumented INCLUDE_SYMMETRY keyword (grammar extended,
   status stays broken); the aborting probe ran it post-solve, now
   the candidate abort cause for the re-probe.

## 4. Changes persisted

* pyflightstream (four commits): the 11-command backfill plus grammar
  fixes; the phase corrections with helper, PHY-02, and spec updates;
  the PHY-02 revalidation report pair; 189 tier 1 tests green.
* AeropropulsiveResearch/tools/fts_sim (research workspace, outside
  this repository): README with the verdict, case_9001.py (exact
  literals with derivations), extract_case_data.py plus the two
  monitoring CSVs, recipe_9001.py (fully validated emission),
  run_9001.py, compare_9001.py, campaign_9001.toml (lossless
  convert_matrix of the legacy matriz.fs, round-trip checked).

## 5. Open questions and contradictions

PLN-012 now has a concrete re-probe plan: run the section
distribution pre-solve with INCLUDE_SYMMETRY on the licensed machine
and promote or amend. Carried: ProperDocs decision, SMI
genericization, SWEEPER pass, 26.000/26.100 backfill probing. The
solver's tecplot export carries run-to-run last-ulp noise under 8
threads; single-thread runs may be needed wherever bit-exact .dat
files matter.

## 6. Single highest-value next action

Fold the PLN-012 re-probe into the next licensed-machine sweep, and
grow fts_sim from the reproduced single point into the native
campaign flow (the converted campaign_9001.toml plus a registered
recipe already point the way).
