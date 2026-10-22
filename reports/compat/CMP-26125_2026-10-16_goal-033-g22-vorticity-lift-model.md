# Compat report: FlightStream 26.125 (2026-10-16)

GOAL-033:G22. One command probed on Simcenter Flightstream 2612, build #10052026,
by the licensed kit of GEO-105 release 0.42.0 (receipt namespace
`3891a52dfe79a1f18685c33f342f386ec3ddbe72-a993925ac8bc46d5bc5f3af868dc8526`).
Database statuses are promoted from a report only through `pyfs-qa apply-compat`; this
report does not apply one.

## Summary

0 verified, 0 broken, 1 removed, 0 unprobed.

## Evidence per command

| Command | Outcome | Evidence | Observation |
|---|---|---|---|
| SET_VORTICITY_LIFT_MODEL | removed | Probe script line 18 `SET_VORTICITY_LIFT_MODEL ENABLE`, script sha256 `af77a43d0889bb77cf6de2b1828b0d63654ee224ade5c7dd22a8388153d65628` | The solver stdout reads `ERROR \| Syntax \| 'SET_VORTICITY_LIFT_MODEL ENABLE' \| Unrecognized command in script ... at line 18 \| Check command spelling and syntax.` The before marker was reached (line 25 of `log_before.txt`); the after marker, `log_after.txt` and `state_after.fsm` are absent; the baseline control reached `PYFS_BASELINE_OK` (`baseline.log` line 19). No effect on the model could be observed. |

## What this establishes and what it does not

The name with the argument ENABLE is not recognised by this build. No other spelling was
probed and none is claimed. The plan keeps refusing `SET_VORTICITY_LIFT_MODEL` for 26.125.

## Vendor question

Does 26.125 carry a replacement for the vorticity lift model switch that earlier builds
accept as `SET_VORTICITY_LIFT_MODEL ENABLE`, under another name or another spelling? The
question goes to the vendor; nothing is assumed until it is answered or a probe settles it.
