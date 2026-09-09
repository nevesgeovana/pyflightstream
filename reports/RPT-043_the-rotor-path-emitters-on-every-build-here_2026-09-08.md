# RPT-043: the thirteen solver-setting emitters of the rotor path, measured on every build this machine holds (2026-09-08)

The sweep the 0.10.0 release note said was owed ("the rotor default path
gained thirteen emitters nobody has swept"). One matrix of the tier-3
workspace, `tests/tier3_licensed/matriz_builds.fs`, states the tour's
one-blade periodic rotor row once per build, run through `pyfs-matrix
run`; this report reads what the two runs left and names the builds the
sweep did not reach. PFS-2028.02.

Builds measured: 26.120 (build #7012026), 26.123 (build #8112026)
Builds NOT covered: 26.121, 26.122 (registered in the package, no
executable on this machine; their rows stay `documented` or inherit)
Verdict: all thirteen accepted on both builds, both rows CONVERGED

## The question

Since 0.10.0 the `unsteady_rotor` run type emits, from the setup preset,
thirteen solver-setting commands that the earlier rotor path did not:

| Command | Chapter |
|---|---|
| SET_MAX_PARALLEL_THREADS | runtime_settings |
| SET_BOUNDARY_LAYER_TYPE | solver_settings |
| SET_SOLVER_VISCOUS_COUPLING | solver_settings |
| SET_SOLVER_CONVERGENCE_ITERATIONS | advanced_settings |
| SOLVER_MINIMUM_CP | advanced_settings |
| REYNOLDS_AVERAGED_DRAG_FORCES | advanced_settings |
| SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY | advanced_settings |
| SOLVER_SET_FARFIELD_LAYERS | advanced_settings |
| SOLVER_UNSTEADY_PRESSURE_AND_KUTTA | advanced_settings |
| SET_WAKE_ON_WAKE_INDUCTION | advanced_settings |
| ADDITIONAL_WAKE_RELAXATION_ITERATION | advanced_settings |
| SOLVER_STABILIZATION | solver_settings |
| SET_ANALYSIS_SYMMETRY_LOADS | solver_analysis |

Before this report the database carried them `documented` on 26.120 (all
thirteen), `verified` on 26.121 and 26.122 for the first five and
`documented` for the other eight, and on 26.123 `verified` for the first
five and `documented` for the other eight. Documented means the manual
says the solver takes the command and no committed run shows that it
does.

## How it was measured

Two rows, 7001 on 26.120 and 7002 on 26.123, identical to the tour's row
1020 in every other cell: the synthetic blade `30_BLADE.fsm` under
periodic symmetry with six copies, advance ratio 1.7, azimuthal clock of
30 degrees per step over half a revolution, preset `s002`, pproc `p001`.
The FS_BUILD cell is the only difference between the rows, so the script
each solver received differs only where the package emits build-specific
grammar.

    pyfs-matrix run tests/tier3_licensed/matriz_builds.fs --workspace tests/tier3_licensed
    -> tier3_licensed/sim_7001/a+00.0_b+00.0 CONVERGED on 26.120 (#7012026), 94 iterations, residual 9.32e-06
    -> tier3_licensed/sim_7002/a+00.0_b+00.0 CONVERGED on 26.123 (#8112026), 94 iterations, residual 9.32e-06

For each row, `tests/tier3_licensed/test_builds.py` reads the record and
asserts: the run reached a terminal status on the build the row names
(`fs_version_source` is `row`); every one of the thirteen is a line of the
script the solver received; the solver's log carries no line that both
says error and names one of the thirteen; and, the side product, the
database row of each command on that build says `verified` and cites this
sweep's compat report.

The compat reports are `reports/compat/CMP-26120_2026-09-08_rotor-path.yaml`
and `CMP-26123_2026-09-08_rotor-path.yaml`, one entry per command with
the emitted line, the row, the status and the script's sha256, applied
with `pyfs-qa apply-compat`, which promoted 13 statuses on each build
("database reloaded and valid").

## What this does and does not say

It says the solver ACCEPTED each command on each build: the script ran to
a converged solve with the line in it and the log names no error for it.
That is the compatibility claim the database makes and the whole of it.
It does not say the setting took effect on the flow, which would need a
run that changes one setting and nothing else; the 0.10.0 note is
explicit that this repository does not make that claim from a
compatibility sweep, and neither does this report.

Both rows report the same final residual to three figures, 9.32e-06, and
the same iteration count. That is recorded and not interpreted: two
builds agreeing on a converged residual for one script is consistent
with the grammar being the same, and this report measured grammar.

## What is not covered, and how it is closed

26.121 and 26.122 have no executable on this machine, so no row could name
them and plan READY (the registry refuses a build it has no executable
for). When an executable is registered in `executables.local.toml`, one
more row of `matriz_builds.fs` per build, `pyfs-matrix run`, and a compat
report in the shape of the two above close the gap; the test module takes
the new rows in its `ROWS` tuple.
