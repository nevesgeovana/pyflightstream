# RPT-088 - A 26.124 unsteady log without a completion line is read, not refused (2026-09-28)

A re-measurement on **FlightStream 26.124, build #8172026**, of the unsteady
log of a six-copy periodic probe row on this machine (`SYMMETRY PERIODIC 6`,
run 2026-09-28). It establishes that a real 26.124 unsteady log carries no
`converged`, `completed` or `simulation complete` line, and that the
package's log readers (`parse_residual_history`, `parse_log_times`,
`frozen_time_steps`, in `pyflightstream.results`) read it without requiring
one. The row's own log is also the exact source of the two figures commit
`d1db61fa` cites (2333 residual rows, 346.8 s), matched exactly; its real
tail line order differs from the commit's description and from the shipped
test's fixture (see "What differs from the commit").

## Why it was run

Commit `d1db61fa` ("test: a 26.124 log ending in 'Script run complete.' is
judged, not refused (P3)", branch `fix/0-30-robust`) states: the 26.124
unsteady native log ends with "Unsteady solver run time: N minutes." and
"Script run complete." and carries no completion line; the real log reads
2333 residual rows, 346.8 s and no frozen solve. This report re-measures
those readers against the real log of a six-copy periodic probe row,
identified as the exact source of both cited figures.

## Method

Twenty-nine real unsteady logs were read: the six-copy periodic probe row's
own log, plus twenty-eight further logs from a separate research campaign on
this machine, using the project's own readers, unmodified, from the
`fix/0-30-robust` branch (branch tip `e481753e`, with `105bc274` and
`d1db61fa` both ancestors):

```
python -c "from pyflightstream.results import parse_residual_history, parse_log_times, frozen_time_steps; ..."
python -m pytest tests/tier1_offline/test_log_without_a_completion_line.py -v
```

For each log: `parse_residual_history(text)` (row count, last iteration),
`parse_log_times(text)` (`solver_run_time_s`, `solver_mode`, `time_steps`),
`frozen_time_steps(text)`, and a case-insensitive search for `converged`,
`completed` or `simulation complete` anywhere in the text. NUL bytes
(`\x00`), which every one of these logs carries between lines, are stripped
by the readers themselves, not by this script.

## Result

| Figure | Commit `d1db61fa` states | Measured, the probe row's own log |
| --- | --- | --- |
| Residual rows | 2333 | **2333** (exact match) |
| Run time | 346.8 s (5.78 minutes) | **346.8 s** (5.78 minutes) (exact match) |
| Solver mode | unsteady | unsteady |
| Frozen solve (`frozen_time_steps`) | none | `None` |
| Completion line present | no | no |

This log's own SHA-256 is recorded in the JSON sidecar. Of the twenty-eight
further logs read from a separate research campaign on this machine, none
carries a `converged`, `completed` or `simulation complete` line either;
eight of them independently read exactly 2333 residual rows, none of them
346.8 s exactly (closest: 356.4 s), which is consistent with 2333 rows being
a common count for this row shape and 346.8 s being specific to the probe row
identified here as the commit's real source.

## What differs from the commit

- **Tail order.** The commit's own wording and the shipped test's fixture
  (`TAIL_26124` in `tests/tier1_offline/test_log_without_a_completion_line.py`)
  both order the log's final lines as "Unsteady solver run time..." followed
  later by "Script run complete." as the true last line, then nothing further.
  The real log's true final non-empty lines, in order, are:

  1. `Script run complete.`
  2. `Unsteady solver run time: 5.78 minutes.`
  3. `Simulation file saved to following location:` / the `.fsm` filename
  4. `Data written to external text file:` / the `.txt` filename
  5. `Data written to external text file:` / the native Tecplot filename
  6. `Data written to external text file:` / the `.vtk` filename

  `TAIL_26124` matches neither the order (it puts "Script run complete." last,
  the real log puts it first) nor the full content (it stops after one "Data
  written" line for the `.txt` export; the real log has two further "Data
  written" lines, for the native Tecplot and VTK exports, which this row also
  produced). The substantive claim under test, that no completion line is
  present and the readers do not require one, holds in the real log
  regardless of this difference: `TAIL_26124` does not match the real tail it
  is meant to represent, but it does not misstate the absence of a completion
  line.
- No other figure differs: the row count and run time are exact matches (see
  "Result").

## Independent confirmation via the package's own tests

The shipped tier-1 test module for this fix was run unmodified from the
`fix/0-30-robust` branch: both tests passed
(`test_the_assessor_judges_a_log_that_ends_in_script_run_complete`,
`test_every_log_reader_reads_that_log`), against `TAIL_26124`, not the real
log measured above. This confirms the readers' code behaves as designed on
the shipped fixture; it does not by itself confirm the fixture's tail order
or content matches the real log it represents (see above).

## What is not established

- `reads_as_residual_history`, `collected_solver_log` and `LoadsAssessor`,
  named in the commit message alongside the three readers this report
  exercised directly, were not independently re-run against the real log in
  this report; the shipped test module exercises the first two against its
  own fixture (see above), and passed.
- No claim is made about how representative this one probe row's log shape
  is of every unsteady 26.124 run; the twenty-eight further campaign logs
  read for this report all share the same no-completion-line shape, which is
  the only generalisation this report supports.
