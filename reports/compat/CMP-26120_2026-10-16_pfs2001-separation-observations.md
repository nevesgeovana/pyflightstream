# Compat report: FlightStream 26.120 (2026-10-16)

Tier 2 command-validity evidence produced by the probe harness
(`pyfs-qa probe`); one evidence line per database command of this
version. Database statuses are promoted from this report only
through `pyfs-qa apply-compat`, never edited by hand (CONTRIBUTING.md
invariant 3). Probe scripts and logs are local scratch; this
report is the committed evidence.

## Setup

| Item | Value |
|---|---|
| Executable | FlightStream_26120.exe (sha256 withheld; build 7012026, local, `_private/exe/`, never committed) |
| Executor | recorded licensed executor, `-hidden -script` (as run; mechanism FSM-26.120 pp.279-280; argument spelling RPT-023) |
| Package | pyflightstream unrecorded; source 6bad1dac664ef7b0959e683749f4b1f437af6033 |
| Solver identity lines | FlightStream version 26.1, build #7012026 |

## Summary

0 verified, 1 broken, 1 removed, 0 unprobed.

## Evidence per command

| Command | Outcome | Evidence | Expected effect | Observation |
|---|---|---|---|---|
| CREATE_BULK_SEPARATION | broken | script processing aborted at the command: the log exported before it exists, the one after it never appeared (END sentinel missing); the solver said: ERROR \| Scripting \| N/A \| Error in script '<probe folder>\probe.txt' at line 12: 'CREATE_BULK_SEPARATION PYFS_BULK CYLINDRICAL -1 0.5' \| Review command syntax a; ERROR \| Scripting \| N/A \| Error in script '<probe folder>\probe.txt' at line 12: 'CREATE_BULK_SEPARATION PYFS_BULK CYLINDRICAL -1 0.5' \| Review command syntax a; offline report of the licensed 2026-10-15 PFS-2001.07 observations, namespace 6bad1dac664ef7b0959e683749f4b1f437af6033-29503a168256457eab4ba4bf1099439f. Only this tested spelling and syntax on build 7012026 are judged. | NA | missing |
| DELETE_VALAREZO_CRITERION_BOUNDARIES | removed | the solver refused the name as an unrecognised command, so this build does not carry it; measured, not read off an edition's silence; offline report of the licensed 2026-10-15 PFS-2001.07 observations, namespace 6bad1dac664ef7b0959e683749f4b1f437af6033-29503a168256457eab4ba4bf1099439f. Only this tested spelling and syntax on build 7012026 are judged. | NA | missing |
