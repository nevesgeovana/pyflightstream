# RPT-041: a SCRIPT action re-reads its file on every time step, measured on 26.123 (2026-09-08)

The licensed run that RPT-030 named and could not make. One row of the
tier-3 workspace, `tests/tier3_licensed/matriz_actions.fs` row 6001,
registered two unsteady solver actions on build 26.123 and ran eight
time steps; this report reads what the run left in the simulation folder.
GOAL-012 item 7b, PFS-2031.08.

Verdict: YES
Build: 26.123
Invocations: 8

## The question

`SET_NEW_UNSTEADY_SOLVER_ACTION` registers an action the solver runs after
each unsteady time step, a FlightStream script or a shell command. The
unsteady-actions design of the 0.13.0 scope rests on one property no
edition states: when the action is a SCRIPT, does the solver read the file
again on every invocation, so a program can rewrite it between steps, or
does it read the file once at registration and run that text every time?
RPT-030 read both manual editions and found the four things a step-aware
action would need unstated too: arguments, working directory, step index
and environment. This run answers the re-read question and the four.

## How it was measured

The row is a LEGACY row whose recipe,
`tests.tier3_licensed.recipes:actions_reread_probe`, builds an unsteady
point of the synthetic wing (`10_WING.fsm`, 12 by 16 panels, alpha 2 deg,
Mach 0.1) with `SET_SOLVER_UNSTEADY` at 8 time iterations of 0.01 s, and
registers, before `INITIALIZE_SOLVER` and in this order:

1. a `COMMAND_LINE` action running `tests/tier3_licensed/actions_probe.cmd`,
   which runs `actions_probe.py` beside it. Each invocation appends one
   record (its count, its argument vector, its working directory, the
   environment variables naming the solver, a clock) to
   `sims/sim_6001/actions_probe.log`, and REWRITES the file below so that
   it exports the loads spreadsheet to `probe_export_<count>.txt`;
2. a `SCRIPT` action pointing at `sims/sim_6001/actions/reread.txt`, whose
   registration-time text, written by the run layer before the solver
   started (PFS-2031.13), exports to `probe_export_initial.txt`.

The solver runs actions in creation order, so at every step the program
rewrites the file and then the solver runs the SCRIPT action. If the file
is re-read, the folder fills with exports named for distinct counts; if it
is read once, the folder holds `probe_export_initial.txt` and nothing else.
The verdict is derived from the files by
`python -m tests.tier3_licensed.actions_probe --verdict`, and
`tests/tier3_licensed/test_actions_probe.py` asserts that this report and
the command database state the verdict the files give.

The run was made three times on the same build with the same script,
the second and third after two defects of the row's own recipe (the
velocity source and a collision on a collected name), and the verdict and
the counts were identical on all three; the record below is the third.

    python -m pyflightstream.run.cli run tests/tier3_licensed/matriz_actions.fs --workspace tests/tier3_licensed --fs-exe <26.123> --fs-version 26.123
    -> run id tier3_licensed/sim_6001/a+02.0, COMPLETED_MAX_ITER, 173 solver iterations, 4.8 s wall
    -> fs_version_reported 26.1, fs_build 8112026

## What the folder holds

| File | Solver iteration printed inside |
|---|---|
| `probe_export_001_iteration=1.txt` | 61 |
| `probe_export_002_iteration=2.txt` | 77 |
| `probe_export_003_iteration=3.txt` | 93 |
| `probe_export_004_iteration=4.txt` | 109 |
| `probe_export_005_iteration=5.txt` | 125 |
| `probe_export_006_iteration=6.txt` | 141 |
| `probe_export_007_iteration=7.txt` | 157 |
| `probe_export_008_iteration=8.txt` | 173 |

Eight exports, one per invocation, each a complete loads spreadsheet of
the state at that step, and no `probe_export_initial.txt` at all. The log
holds eight records, invocations 1 to 8, about 0.2 s apart.

## Findings

1. **A SCRIPT action's file is re-read on every invocation.** Every one of
   the eight exports carries the name the rewrite of that step gave it.
   The text registered before the run was never executed: the first
   invocation of the command rewrote it before the first SCRIPT action ran.

2. **The invocation count equals the time-step count, exactly, and nothing
   fires before the first step.** Eight steps, eight invocations, eight
   exports, and no export for an initial condition. The step-gated action
   of the 0.13.0 design can therefore count invocations to know the step.

3. **The solver stamps the export name with the time iteration.** The
   script asked for `probe_export_003.txt` and the solver wrote
   `probe_export_003_iteration=3.txt`: an export made from an action
   script gets `_iteration=<time iteration>` appended before the suffix.
   A design that names its exports must expect the stamp, and may use it
   as a second handle on the step. Measured on this build alone.

4. **The four RPT-030 silences, answered on this build:**
   * Arguments: none. The argument vector of every invocation is empty.
   * Working directory: the simulation folder, which is the directory the
     executor started the solver in, read from the record each invocation
     wrote. That a relative path inside an action would resolve there
     FOLLOWS from it and was not measured: the probe used absolute paths.
   * Step index or physical time: not passed. The stamp of finding 3 is the
     one place the solver states the step to an action, and it is on the
     export name, not in the invocation.
   * Environment: no variable naming the solver is set for the child.

5. **The mid-run export is the loads at that step.** Each spreadsheet
   prints the solver iteration reached at its step, 61 to 173 in steps of
   16, so the solver runs its inner iterations, then the actions, per time
   step, and the export made by an action sees the state after that
   step's iterations.

## What this does not say

Nothing here was measured on 26.122, where the command is documented too;
the local installations are 26.120 and 26.123 and the command is absent
from 26.120. The findings are about the SCRIPT route with a
`COMMAND_LINE` action ahead of it; a run with the SCRIPT action alone was
not made, and whether the solver waits for a COMMAND_LINE action to exit
before running the next action was not measured separately (the ordering
of the rewrites and the exports is consistent with it, on every step, but
a race that happened to lose eight times is not excluded by eight
samples). The verdict is about the file being re-read; it says nothing
about a script that changes length or registers further actions.

## Status of the command

`SET_NEW_UNSTEADY_SOLVER_ACTION` stays `documented` on 26.122 and 26.123:
this is a tier-3 row of the workspace, not the tier-2 probe harness that
promotes a command to `verified`. Its notes carry findings 1 to 4 and the
26.123 row cites this report.
