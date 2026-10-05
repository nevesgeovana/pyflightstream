# RPT-156 - The same scripts on builds 26.124 and 26.125 (2026-10-05)

FlightStream 26.124, build 8172026, and 26.125, build 10052026. This report transcribes retained runs and comparisons; it does not rerun the solver. Evidence is cited by file name relative to the run folder.

## Purpose

Record the FR-423, S10 comparison of six campaign points run with their exact 26.124 scripts unchanged on build 26.125, with paths rewritten only.

## Method

The six recorded points comprise a steady body, a quasi-steady six-blade wheel, an unsteady single blade, a quasi-steady wheel with a spinner and nacelle body, an unsteady periodic sector, and an unsteady six-blade wheel at 5 degrees. Each retained 26.124 script was run on build 26.125 with paths rewritten only. The comparison uses `manifest.json`, `rewrites.json`, `run_log.csv`, `verdict.json`, each point folder, and `judge.log`.

## Results

The log identity line changed from `FlightStream version 26.1, build #8172026` to `Simcenter Flightstream 2612, build #10052026`. Export headers now read `Simcenter Flightstream <kind>` where the prior headers read `FlightStream <kind>`. No settings or model line of the log banner differed. Iteration counts matched on the steady point and on the quasi-steady six-blade wheel (49 per solve); the quasi-steady wheel with the spinner and nacelle body took 97 instead of 99 per solve. The unsteady points used fewer iterations on build 26.125, by about 3 percent.

| Point | Run type and generic configuration | CX, 26.124 | CX, 26.125 | Relative change |
|---|---|---:|---:|---:|
| 4820 | Steady body | 0.000863 | 0.001036 | +20.05%* |
| 4311 | Quasi-steady six-blade wheel | -0.017440 | -0.017335 | +0.60% |
| 4500 | Unsteady single blade | -0.010597 | -0.010598 | -0.01% |
| 4612 | Quasi-steady wheel with spinner and nacelle body | -0.016451 | -0.016237 | +1.30% |
| 4100 | Unsteady periodic sector | -0.008635 | -0.008732 | -1.12% |
| 4902 | Unsteady six-blade wheel at 5 degrees | -0.044385 | -0.044497 | -0.25% |

Relative change is `(26.125 - 26.124) / abs(26.124)`. *The steady value is near zero, so its percentage is not a useful measure of the absolute difference, which is 0.000173. Rotor totals changed by up to about 1.3 percent in this sample.

The largest field differences were in near-zero cells, including Delta Cp values, where relative percentages magnify small absolute differences. The solver numbers changed between builds despite no logged settings or model-line change. A campaign that mixes these builds therefore mixes numerically different results.

## Limits

This comparison covers six recorded points and these specific scripts, inputs, and outputs. It does not establish which build is more accurate or explain the numerical differences. Export header wording changed alongside the identity line; the comparison does not establish other compatibility effects. The near-zero field differences and the steady near-zero CX percentage should be read in absolute context.
