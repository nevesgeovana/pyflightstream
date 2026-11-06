# Compat report: AUTO_DETECT_TRAILING_EDGES on FlightStream 26.127 (2026-11-05)

Tier 2 evidence beside `CMP-26124_2026-11-05_autodetect-te.yaml` (FR-3742). The command
database holds no 26.127 row for this command, because FSM-26.125 and FSM-26.127 no longer
print it, so `pyfs-qa probe` refuses to emit it on 26.127. The question this report answers is
the first signal of the validity sweep: does the 26.127 solver still recognise the command, and
does it mark the trailing edge it marks on 26.124.

## Setup

| Item | Value |
|---|---|
| Executable | `Flightstream_2612.exe` of the 26.127 package (sha256 withheld; Simcenter Flightstream version 2612, build #10282026, local, never committed); control `Flightstream_26124.exe` (FlightStream version 26.1, build #8172026) |
| Executor | `-hidden -script`, one solver at a time |
| Script | the probe script `pyfs-qa probe` rendered on 26.124 for `CMP-26124_2026-11-05_autodetect-te`, replayed unchanged but for its folder: the synthetic diamond wing stub joined to a body (surfaces Wing and Body), imported in metres, saved, the BEGIN sentinel and a log, the command, the END sentinel and a log, saved again |
| Instrument | the log after the END sentinel (processing continued past the command), its error lines and its trailing-edge line, and the trailing-edge groups of both saves read with `saved_trailing_edge_groups`. The edge mid-point reader of the 26.124 probe refuses a 26.126 or 26.127 save (its mesh block carries one row of edge flags where earlier builds carry five), so the edges themselves are not read here |

## Evidence

| Build | Log after the command | Errors | Trailing-edge line | Groups before | Groups after |
|---|---|---|---|---|---|
| 26.127 | written | none | one trailing edge marked on surface Wing | none | Wing |
| 26.124 (control) | written | none | one trailing edge marked on surface Wing | none | Wing |

## Reading

The 26.127 solver recognises `AUTO_DETECT_TRAILING_EDGES` and marks the wing's trailing edge,
with the same log line and the same saved group as 26.124, where the saved edges were read and
the command is verified. This is a measurement of a command the 26.127 manual does not
document; the database writes no 26.127 row for it, and the package keeps emitting the
counted `DETECT_TRAILING_EDGES_BY_SURFACE` form on that build.
