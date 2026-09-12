# RPT-042: the workspace rebuilds the physics cases inside every band the accepting seat set (2026-09-08)

The four shareable physics cases of `pyflightstream.qa.physics`, PHY-01,
PHY-02, PHY-05 and PHY-06, ran as rows of the tier-3 workspace's
`matriz_physics.fs`, built by the `steady`, `unsteady` and
`unsteady_rotor` workflows from saved synthetic geometries and the
presets `s005`, `s006`, `s007` and the reference block `r005`, on build
26.120 (#7012026). Their metrics, reduced with the qa layer's own
functions from the loads the rows exported, were judged against the
committed references under `qa/references/`. GOAL-012 item 7,
PFS-2031.07.

Verdict: every metric PASS inside the committed bands, and every metric
agreeing with its reference to the decimals printed in the table below.
The references carry more decimals than the table prints (seven for
PHY-05, sixteen for the PHY-06 slopes), and at that precision the
agreement is a PASS and not an identity: PHY-05's CL is -0.00009 against
-0.0001012, inside an absolute band of 0.002. The tier-3 test asserts the
bands (no FAIL, no metric without a reference), never equality.

## How it was measured

```text
pyfs-matrix run matriz_physics.fs --workspace tests/tier3_licensed
pytest -m needs_flightstream tests/tier3_licensed/test_physics.py   -> 5 passed
```

The workspace was cleared before the run (no `runs.json`, no `sims/`,
no `post/`); the six matrices ran one after the other and recorded 41
points, none failed. `test_physics.py` reads the manifest, parses each
row's loads spreadsheet with `parse_run_loads`, which cross-checks the
printed operating point against the record, builds `PointResult` values
and reduces them with `phy01_metrics`, `phy02_metrics` and the PHY-05
and PHY-06 reductions written the way `_run_phy05` and `_run_phy06` do,
then judges with `compare_metrics` against `load_reference`.

## The numbers

| Case | Metric | Row | Reference | Band |
|---|---|---|---|---|
| PHY-01 | CL_a0 | -0.0004 | -0.0004 | pass |
| PHY-01 | CL_a2 | 0.1684 | 0.1684 | pass |
| PHY-01 | CL_a4 | 0.337 | 0.337 | pass |
| PHY-01 | CL_a6 | 0.505 | 0.505 | pass |
| PHY-01 | CL_slope_per_rad | 4.8266 | 4.8266 | pass |
| PHY-01 | CDi_a4 | 0.0049 | 0.0049 | pass |
| PHY-02 | CL_full_a4 | 0.337 | 0.337 | pass |
| PHY-02 | CL_half_a4 | 0.3385 | 0.3385 | pass |
| PHY-02 | delta_CL_a4 | 0.0015 | 0.0015 | pass |
| PHY-02 | delta_CDi_a4 | 0.0 | 0.0 | pass |
| PHY-05 | CL | -0.00009 | -0.0001012 | pass |
| PHY-05 | CDi | -0.04517 | -0.0451749 | pass |
| PHY-05 | CDo | 0.0007 | 0.0007011 | pass |
| PHY-05 | CMy | 0.02864 | 0.0286429 | pass |
| PHY-06 | delta_CL at 0, 2, 4, 6 | 0.0004, 0.0013, 0.0022, 0.003 | the same | pass |
| PHY-06 | delta_CD at 0, 2, 4, 6 | -0.0001, -0.0001, -0.0004, -0.0005 | the same | pass |
| PHY-06 | delta_CMy at 0, 2, 4, 6 | -0.0001, -0.0002, -0.0002, -0.0004 | the same | pass |
| PHY-06 | CL_slope steady, unsteady | 4.8266, 4.8515 | the same | pass |
| PHY-06 | CMy_slope steady, unsteady | -1.21496, -1.21754 | the same | pass |

## What it took, and what it says

The first run of the same rows, earlier the same day, judged PHY-01's
induced drag FAIL (0.0082 against 0.0049), PHY-05 FAIL on thrust and
pitching moment (11 percent low), and PHY-06 FAIL on both
pitching-moment slopes (a factor of a hundred). The diff of each row's
script against the qa builder's said why, and none of it was the solver:
the physics preset carried the tour's keys (Prandtl-Glauert, stabilization,
proximity avoidance, symmetry loads, mesh-induced wake velocity) and no
vorticity drag selection; the rotor preset lacked the wake termination
steps; the saved geometries had been prepared without the wake
termination node detection; and the wing reference block put the moment
point at the quarter chord where the qa script leaves it at the origin.
With the presets rewritten to state exactly the lines the qa script
emits, the geometries regenerated and `r005` written, the diff reduced
to orderings, a boundary index in place of "all", and a rotor speed
rounded to four decimals instead of two, and the coefficients above
followed.

Two things follow for the reader. A workflow row reproduces the
hand-built script's coefficients when its setup states the same lines, and the setup is where a
physics case is stated in this repository from now on; the script diff
is the instrument that says whether it does, and it costs no seat. And
the four cases are now judged twice on this build, by `pyfs-qa physics`
and by the workspace, with one reference; which of the two stays is the
study of PFS-2031.09.

## What this does not say

Nothing here was measured on 26.123; the physics rows name 26.120, the
build the references were seeded on. The agreement is stated to the
decimals the table prints, PASS inside the bands beyond that, and the
test holds the bands and not an equality. The
SMI class, whose geometry is local and never committed, has no row.
