# RPT-079: the solver's time averaging counts time steps, on the one build that runs it (2026-09-25)

**Date:** 2026-09-25
**Found by:** the licensed probe T21 of the 0.28.0 work
**Status:** CLOSED in 0.28.0 (the command database records 26.122 verified and 26.123 removed; G25 averages the per-step surfaces in the package, the same average)
**Affects:** `SOLVER_TIME_AVERAGING`, documented from the 26.122 edition, measured hanging 26.124 (C01, 2026-09-19)

## What this settles

The solver can average the surface flow over a window of an unsteady run,
`SOLVER_TIME_AVERAGING ENABLE <first> <last>`. Two things were not known: whether
any build runs it (26.124 hangs on it), and whether its two bounds count TIME STEPS
or inner iterations, which the manual's words do not say. 0.28.0 averages the
surface in the package from the per-step exports (G25), so the solver's own average,
where a build computes one, is the reference that average must meet. **On 26.122 the
command runs, and the final surface is the uniform mean of the run's own per-step
surfaces over the TIME STEPS it names, inclusive, to machine precision; the skin
friction is not averaged. On 26.123 the build does not carry the command.**

## What was run

FlightStream 26.122 (build 8092026) and 26.123 (build 8112026), one unsteady point of
a wing (T09's point 4301 of the tier-3 workspace: 12 time steps of 30 deg,
`SOLVER_SET_FARFIELD_LAYERS 5`, its action program exporting the surface in Tecplot at
every step from step 6, as `<point>_iteration=<N>.dat`), run four times in one
detached batch with no solver alive before it, 300 s allowed each:

| variant | build | added just before `INITIALIZE_SOLVER` |
|---|---|---|
| A_C_26123 | 26.123 | nothing (the control) |
| A_AVG_26123 | 26.123 | `SOLVER_TIME_AVERAGING ENABLE 7 12` |
| A_C_26122 | 26.122 | nothing (the control) |
| A_AVG_26122 | 26.122 | `SOLVER_TIME_AVERAGING ENABLE 7 12` |

The line is where the package emitted the command before it was refused (C01).

## What came back

- **26.123 does not know the command.** The log reads "Unrecognized command in
  script ... at line 379: 'SOLVER_TIME_AVERAGING ENABLE 7 12'", the script stops
  there and the run returns 0 after 0.97 s with nothing exported. The control ran to
  the end in 12.2 s. The same line, byte for byte, ran on 26.122 in the same batch.
- **26.122 runs it**: the averaging run returned 0 in 10.5 s (control 10.2 s), with
  every export and all seven per-step surfaces (steps 6 to 12).
- **Its final surface is the mean over time steps 7 to 12.** Compared node by node
  with the mean of the run's own per-step surfaces:

  | window of per-step surfaces | largest difference in Cp | in Vx (m/s) | in speed (m/s) |
  |---|---|---|---|
  | steps 7 to 12 (the stated bounds) | 4.3e-14 | 1.1e-13 | 1.7e-13 |
  | steps 6 to 12 | 0.60 | 1.36 | 1.98 |
  | steps 8 to 12 | 0.60 | 1.36 | 1.97 |
  | step 12 alone | 2.43 | 5.77 | 8.32 |

  The control's final surface is step 12's instant; the averaging run's is not.
- **The skin friction CF is not averaged**: the final CF equals step 12's to the
  digit, and differs from every window's mean.
- The per-step surfaces are instants in both runs.

## What it means for the package

- The bounds are **time steps, inclusive and 1-based**, and the weights are uniform:
  the definition the averaging window of the package already used, now measured.
- **The package's average (G25) is the solver's own**, on the one build where the
  solver computes it, for the flow variables; the package averages the skin friction
  too, where the solver keeps the last instant, and says so.
- The command database records the command `verified` on 26.122 and `removed` on
  26.123 from this run's transcriptions; 26.124 stays `broken` (C01). 0.28.0 never
  emits the command: the package averages the per-step exports on every build.

## What this does not settle

- Any other window, a rotor row, a run stopped by the wall clock.
- Why 26.123 lost the command and 26.124 hangs on it.

## Evidence

The scripts the solver received, the per-step and final surfaces and the comparison
are kept machine-local with the probe driver `p28t_driver.py` and `compare.py`; the
GOAL-032 ledger's T21 receipt names every path, both executables' sha256 and the
batch's preflight. The compat transcriptions are
`reports/compat/CMP-26122_2026-09-25_time-averaging.yaml` and
`reports/compat/CMP-26123_2026-09-25_time-averaging.yaml`.

**Verdict: VERIFIED**, for what was run: `SOLVER_TIME_AVERAGING ENABLE 7 12` runs on
26.122 and makes the final surface the uniform mean over time steps 7 to 12
inclusive, to 1e-13 in the flow variables, the skin friction excepted; 26.123 does
not carry the command.
