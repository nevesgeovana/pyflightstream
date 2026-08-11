# RPT-026: what the solver says when it refuses a name (2026-08-11)

`PLN-20260809-0300` asks for a `removed` probe outcome recognised from
"the solver's own unrecognised-command wording".

THE PREMISE THAT JUSTIFIED SPENDING A LICENSED SEAT WAS WRONG, and it is
corrected here rather than left standing, because the same mistake
shaped the detector. The search for that wording stopped at RPT-021,
which paraphrases it ("an unrecognised command error naming the line")
and cites no string; probe logs are local scratch, so the conclusion
drawn was that the repository did not hold the wording at all. It did.
`reports/RPT-012_bulk-separation-spelling_2026-07-23.md` had recorded
it since 2026-07-23, quoted field and all, and had it been read the
whole-line shape would have been known before the run rather than
after it.

The measurement below is still worth having: it is on the build being
registered, it carries a control RPT-012 does not, and it settled the
NUL question. But it is a confirmation of committed evidence, not a
first sighting.

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
whose third quotes the offending SCRIPT LINE, and whose fourth begins
`Unrecognized command in script`, followed by the script path and the
line number. A second record follows it on the `Scripting` channel
naming the same line.

THE THIRD FIELD IS THE WHOLE LINE, NOT THE COMMAND, and the three arms
above could not show it: each spliced a target with no arguments, so
the two readings coincide. The detector was written against a bare
token on the strength of that. A fourth arm, emitting
`SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE`, records
`'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE'` in that field, and
RPT-012 had recorded the same shape since 2026-07-23
(`'CREARE_BULK_SEPARATION sep1 -1 0.5'`).

The population that would have been missed, measured on the catalog
rather than estimated: 109 probe specifications exist, and of the 87
whose target line renders in isolation, 49 carry arguments on that
line. The remaining 22 need prelude state before they render at all and
were not measured this way. Two different readings of this number were
offered during review, 49 of 87 and 71 of 109; both are wrong, and the
denominator 87 is the renderable subset rather than the catalog.

The crash log also carries stray NUL bytes, 12 in the measured run. It
is the one log of this pipeline that the harness reads without the
scrubbing every other log gets.

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
harness recorded it `broken` on 26.122. The second field is what
separates the two: `Syntax` names the line it did not recognise,
`Scripting` carries `N/A` and a sentence about the call. The probe
specification now creates a `6DOF` motion for that one setter, and the
command records `unprobed` (it runs; its effect is not observable with
the current instruments), which is honest.

STATED EXACTLY, because the first version of this paragraph claimed a
harm that was averted and it was not. Not promoting `broken` on 26.122
does NOT stop the refusal there: the build inherits its base release's
records, it has no row of its own for this command, and 26.120 records
`broken`, so the emitter refuses it on 26.122 today. What the
correction prevented is one more measured `broken` joining three
inherited ones. Lifting the refusal needs the three older statuses
demoted, and an `unprobed` result cannot demote them
(`PLN-20260811-1300`).

**One command crashes the solver.** `NEW_OFF_BODY_STREAMLINE` on
26.122 aborts with return code 3221225477, which is `0xC0000005`, an
access violation, and writes no crash log at all. It is correctly
`broken`, and it is the only broken command of the run.

## Consequence for the harness

`ProbeOutcome.REMOVED` exists and is promotable. It is recognised from
the LEADING TOKEN of the quoted line, when that token names the probed
command, and it is read before every other branch: before the
missing-sentinel branch, before the generic error scan
(`(?i)not recognized` is already in the default patterns and returns
`broken`), and before the halting branch, which reads the very same
signature as SUCCESS and would have recorded a refused `STOP` as
`verified`. When the crash log names a DIFFERENT command, the target
never ran and the result is `unprobed` with the offender named, because
recording it `removed` would delete a command from the version view on
the strength of another command's absence.

## What this outcome cannot do, stated because it is not symmetric with broken

A `removed` row takes the command out of the version view, and the
version view is what the harness iterates to build a run's candidate
list. So a removal cannot be re-measured by the ordinary path: naming
the command explicitly is refused, and `allow_broken` refuses it too.
`broken` is recoverable by a later probe; `removed` is not.

Read that beside the identical-wording finding above. A misspelled
target in a probe specification produces the same evidence as a genuine
withdrawal, and promoting it would remove a working command for every
caller and close the route by which the mistake would be found. Two
refusals in `apply_compat` stand between those cases and the database
(a page citation of that edition, and a per-version argument grammar),
and neither covers a row whose only manual evidence is entry-level.
The residual is the author's accepted risk, recorded in
`PLN-20260811-1400`.

Measured consequence for this run: the report records zero removals,
because the four commands 26.122 records as `removed` are already out
of the version view and were never candidates.

## Reproduction

`_private/exe/FlightStream_26122/`, driven through `LocalExecutor`.
Scripts and logs are local scratch; this report is the committed
evidence. The measured strings are pinned as fixtures in
`tests/test_qa_probes.py`, including the semantic refusal, which is the
negative control that keeps the pattern from widening into it.
