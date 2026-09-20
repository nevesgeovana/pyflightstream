# Compat report: FlightStream 26.124 (2026-09-19)

This is a compat-format transcription of the licensed C01 one-line comparison
supplied for F02. No solver was invoked while implementing the planning refusal.
The paired YAML records the same measured numbers and the `broken` outcome for
`SOLVER_TIME_AVERAGING`; it does not claim a new probe-harness execution.

| Script | Position of `SOLVER_TIME_AVERAGING ENABLE` | Result | Outputs | Receipt |
|---|---|---|---|---|
| Control, command omitted | NA | Exit 0 in 133.0 seconds | All seven outputs and the final log export | `reports/pfs0250/time_averaging/without/receipt.json` |
| Command present | INIT, before `INITIALIZE_SOLVER`, the position the package emits | Hangs; killed at 240.5 seconds | 0 | `reports/pfs0250/time_averaging/with/receipt.json` |
| Same command moved | After `INITIALIZE_SOLVER` | Hung the same way; terminated at 300 seconds | 0 | none; this run predates the receipts and is an observation, not certified evidence |

Only the averaging line changed. Its emitted grammar agrees with the manual
(SRC-750 p.353, sample `SOLVER_TIME_AVERAGING ENABLE 72 108`), so moving the line
or following that sample does not establish that the command runs on 26.124.
The hang prevented measurement of the averaging bounds' solver interpretation.

The pproc key is refused at plan time unless the selected build records the
command as verified. Removing `[time_averaging]` leaves surface exports as
instants. No successful execution or measured failure on 26.122 or 26.123 is
claimed by this report; manual documentation alone does not enable the key.
