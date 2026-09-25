# Compat report: FlightStream 26.123 (2026-09-25)

This is a compat-format transcription of the licensed probe T21, reported as RPT-079
(`reports/RPT-079_the-solver-averages-the-surface-over-time-steps-on-26122_2026-09-25.md`).
No solver was invoked while writing it, and it does not claim a probe-harness
execution. The paired YAML records the `removed` outcome for `SOLVER_TIME_AVERAGING`
on 26.123, written into the command's row by hand after reading the page and the
probe script, as the promotion asks for a removal of a command an edition documents.

| Run | The one addition, just before `INITIALIZE_SOLVER` | Result |
|---|---|---|
| Control | nothing | returned 0 in 12.2 s, every export written |
| Averaging | `SOLVER_TIME_AVERAGING ENABLE 7 12` | "Unrecognized command" at that line; the script stopped there, return code 0 after 0.97 s, nothing exported |

The line is not a misspelling: the same script line, byte for byte, ran on 26.122 in the
same batch. The 26.123 edition documents the command (SRC-751 p.353); build 8112026 does
not carry it.
