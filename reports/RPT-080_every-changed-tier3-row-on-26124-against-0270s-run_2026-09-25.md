# RPT-080: every changed tier-3 row on 26.124 against the 0.27.0 run (2026-09-25)

**Date:** 2026-09-25
**Found by:** the licensed test T34 of the 0.28.0 work
**Status:** VERIFIED in 0.28.0 (T34: the 73 tier-3 goldens that changed since 0.27.0 name points of every tier-3 matrix, and every point of every matrix ran on 26.124; each converged, or completed its declared time steps, and collected every declared output, and the 83 licensed checks over the run pass. All 76 loads tables are equal, coefficient by coefficient and boundary by boundary, to the 0.27.0 regression's tables of the same points on the same executable)
**Affects:** every tier-3 matrix on 26.124; the exports 0.28.0 changed after the solve: `EXPORT_SOLVER_ANALYSIS_VTK` in place of `EXPORT_SOLVER_ANALYSIS_TECPLOT`, `SET_PLOT_TYPE` and `SAVE_PLOT_TO_FILE` after an unsteady solve

## What this settles

0.28.0 changes what a tier-3 point exports after its solve and nothing the solve
reads. The Tecplot surface is now written by the package from the solver's VTK
(G45), and an unsteady row saves the solver's residual and load plots once, after
the march (G26). Both change the point scripts, and so the goldens. T34 runs every
point whose golden changed and holds it against the 0.27.0 regression (RPT-073).

The points are not chosen by hand. They are the tier-3 `.txt` paths of `git diff
--name-only v0.27.0 51f45932 -- tests/tier1_offline/goldens
tests/tier3_licensed/goldens`: 73 goldens, naming points in all eleven tier-3
matrices. The FSI blade properties (G41) come after 51f45932 and move no golden. So
T34 ran every matrix in full.

The pass condition was fixed before the results:

- every point converges, or completes its declared time steps if it is unsteady,
  and collects every output it declares;
- the licensed checks pass;
- each point's loads table is equal to the 0.27.0 regression's table of the same
  point.

The last condition follows from the setup of both runs: the same 26.124
executable, the same five far-field layers, and scripts that differ only after
the solve. A difference would be a finding to explain.

**Every point passes, the 83 licensed checks pass, and all 76 loads tables are
equal to 0.27.0's: every coefficient of the total row and of every boundary
row.**

## What was run

FlightStream 26.124 (build 8172026, executable sha256 68e64e66...), detached, one
solver at a time, no solver alive before each launch. The run used a fresh copy of
the tier-3 folder at 51f45932 (0.28.0.dev3) with no run state. A local executables
overlay sent every build id the rows name (26.120, 26.123 and 26.124) to the 26.124
executable, as the 0.27.0 regression did. No committed `FS_BUILD` changed.

- **The records.** 66 run records holding 76 points: 12 of `matriz`, 2 of
  `matriz_actions`, 2 of `matriz_builds`, 4 of `matriz_geometry`, 7 of
  `matriz_gui`, 8 of `matriz_mesh`, 8 of `matriz_physics`, 3 of `matriz_rotate`,
  4 of `matriz_setup`, 8 of `matriz_time` and 8 of `matriz_vocab`. A steady sweep
  run as one solver job is one record over its points.
- **The scripts.** 66 solving scripts, and every one states
  `SOLVER_SET_FARFIELD_LAYERS 5`.
- **The package.** Every record names 0.28.0.dev3 at 51f45932, with a clean tree.
- **A first pass that could not plan two matrices.** The two matrices with
  LEGACY recipe rows (`matriz`, `matriz_actions`) import
  `tests.tier3_licensed.recipes`. The first driver started them with no path to
  the test tree's root, so their plans were refused before any solve. The other
  nine matrices ran, and 61 checks passed. The 22 failed checks were all of those
  two matrices. The two ran again with the root on `PYTHONPATH`, and then every
  licensed check ran again.

## What came back

### Every point ran and collected what it declares

Every matrix's run exited 0. 57 records converged. The other 9 are the rows that
march time steps: the six vocabulary rows, the two counter-rotating rotors of
1022, and the actions row 6001. Each completed its declared steps
(`COMPLETED_MAX_ITER`). The 0.27.0 regression recorded the same 57 and 9.

### The licensed checks

`pytest -m needs_flightstream tests/tier3_licensed` over the finished workspace:
83 passed.

### Against the 0.27.0 run

Each loads table T34 wrote was read with `pyflightstream.results.parse_loads`
beside the table of the same point in the 0.27.0 regression's workspace:

- the total row and every boundary row;
- every column of each row;
- the same column set required on both sides.

All 76 tables are equal. The largest relative difference over all of them is zero.

The comparison was checked against a control. Each table was paired with the
0.27.0 table of the next point in the list, a derangement, and 69 of the 76
pairs differ. The 7 that come back equal are neighbours built to give the same
case, as their row descriptions state:

- 7001 and 7002: the rotor emitters of 26.120 and of 26.123, both running
  26.124 here;
- 4101 to 4104: the saved wing simulation and three OBJ routes to it;
- 4111 to 4113: the saved blade simulation and two OBJ routes to it;
- 5012 and 5013: a uniform custom free-stream field at 0 deg and its control,
  the constant free stream at 0 deg.

## What it means for the package

- The exports 0.28.0 moved do not reach the solve. The script now asks for the
  VTK where it asked for the Tecplot, and saves two plots after an unsteady march.
  Neither changes a coefficient on 26.124.
- The package's own Tecplot (G45) and the solver's plots (G26) are written on
  every tier-3 point, of every workflow and every build id. The licensed checks
  that read the surface and the plot files pass over them.

## What this does NOT establish

- **The package's Tecplot against the solver's own.** That is RPT-074 and its
  addendum. T34 shows that every point writes the file; it does not compare the
  values again.
- **Other builds.** Every build id ran on 26.124. How the rows behave on 26.120 or
  26.123 executables is the earlier regressions' record.
- **Points whose golden did not change.** Every tier-3 matrix had at least one
  changed golden, so none was left out here. A later release whose diff selects
  fewer points runs fewer.

## Evidence

- The workspace, drivers and outputs are local to the licensed machine:
  `prepare_t34.py` (the fresh copy and the overlay), `run_t34.py` and
  `rerun_t34.py` (plan, run, checks), `compare_t12_t34.py` (the table
  comparison, with its per-table verdicts), `compare_control.py` (the
  derangement), `t34_facts.py` (the counts above).
- The 0.27.0 regression: `reports/RPT-073_every-changed-tier3-row-on-26124-against-its-recorded-run_2026-09-24.md`.
