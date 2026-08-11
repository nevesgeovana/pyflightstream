# RPT-026: what the solver says when it refuses a name (2026-08-11)

`PLN-20260809-0300` asks for a `removed` probe outcome recognised from
"the solver's own unrecognised-command wording". The repository did not
hold that wording. RPT-021 records the 26.121 build answering
`SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` with "an unrecognised command
error naming the line", which is a paraphrase, and probe logs are local
scratch. A detection pattern written from that sentence would have been
invented.

This report is the measurement, taken on 26.122 build #8092026, plus
three findings that came out of taking it.

## The wording

Three arms, each a separate process because an aborting script hides
whatever follows it. Sentinels emitted through the Script builder so
the grammar comes from the database; only the target line spliced in
raw.

| Arm | Target | Crash log | Refusal |
|---|---|---|---|
| a real command the sibling hotfix lacks | `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` | written | unrecognised |
| a token that was never a command | `PYFS_NOT_A_COMMAND` | written | unrecognised |
| a real command of this build | `SET_FREESTREAM CONSTANT` | none written | none |

The refusal is a pipe-delimited record whose second field is `Syntax`,
whose third quotes the offending token, and whose fourth begins
`Unrecognized command in script`, followed by the script path and the
line number. A second record follows it on the `Scripting` channel
naming the same line.

**The wording is identical in the first two arms.** The solver cannot
tell a caller whether a name is absent from this build or was never a
command at all, so neither can any pattern built on it. That is a
limit of the signal rather than of the reader, and it is why
`apply_compat` refuses to promote `removed` over a row that carries a
page citation of that edition: an edition documenting a command the
build does not carry, and a probe emitting a misspelling, look exactly
the same from here.

The third arm is the control. A real command wrote no crash log at all
and both sentinel logs appeared, so the discriminator is not merely
"an error happened".

## Three findings from taking the measurement

**The refusal never reaches the exported log.** The script aborts at
the offending line, so the log after the command is never written and
the only record is `FlightStreamLog.txt`.
`ExecutionResult.log_text` has carried that file all along and the
probe harness never read it. Before this, an absent command reached
`_judge` with the same signals as any other abort and was recorded
`broken`, which keeps the command in the version view with its grammar
and lets the emitter go on offering a line the solver rejects.

**A semantic refusal wears the same shape and means the opposite.**
`SET_MOTION_START_TIME`, probed against the shared rotary-motion
prelude, aborts the script and writes a crash log reading
`ERROR | Scripting | N/A | Start time cannot be set for rotary
motion.` The command exists and declined this particular call. The
harness recorded it `broken` on 26.122, which would have made the
emitter refuse a working command for every caller on the build. The
second field is what separates the two: `Syntax` names the token it did
not recognise, `Scripting` carries `N/A` and a sentence about the call.
The probe specification now creates a `6DOF` motion for that one
setter, and the command records `unprobed` (it runs; its effect is not
observable with the current instruments), which is honest.

**One command crashes the solver.** `NEW_OFF_BODY_STREAMLINE` on
26.122 aborts with return code 3221225477, which is `0xC0000005`, an
access violation, and writes no crash log at all. It is correctly
`broken`, and it is the only broken command of the run.

## Consequence for the harness

`ProbeOutcome.REMOVED` exists and is promotable. It is recognised from
the wording above NAMING THE PROBED COMMAND, checked before the
missing-sentinel branch and before the generic error scan, both of
which would otherwise answer with the wrong word (`(?i)not recognized`
is already in the default patterns and returns `broken`). When the
crash log names a DIFFERENT command, the target never ran and the
result is `unprobed` with the offender named, because recording it
`removed` would delete a command from the version view on the strength
of another command's absence.

## Reproduction

`_private/exe/FlightStream_26122/`, driven through `LocalExecutor`.
Scripts and logs are local scratch; this report is the committed
evidence. The measured strings are pinned as fixtures in
`tests/test_qa_probes.py`, including the semantic refusal, which is the
negative control that keeps the pattern from widening into it.
