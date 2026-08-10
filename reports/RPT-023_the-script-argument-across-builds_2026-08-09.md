# RPT-023: the script argument across seven builds (2026-08-09)

Measurement of how each registered FlightStream build accepts the
command-line argument that names a script file, and of what a build
does when it is given the spelling it does not know. Run on the
licensed machine against every install under `_private/exe/`.

This report exists because the answer was not what a day of diagnosis
said it was, and because three identity reports written the same day
cite it for the argument their executor line prints.

## What was measured

One script, the probe harness baseline: a `PRINT` of a sentinel, an
`EXPORT_LOG` of the log to a named file, and `CLOSE_FLIGHTSTREAM`. The
grammar came from the command database rather than from hand, which
matters here: `EXPORT_LOG` takes its filename on the following line,
and a hand-written inline form is what made the first day of diagnosis
measure the wrong thing entirely.

Each build was launched windowless (`-hidden`) with both spellings of
the script argument, standard output and standard error redirected to
files, and a 60 second limit. Success means the sentinel reached the
exported log.

## Result

| Build | Release, build number | `-script` | `--script` |
|---|---|---|---|
| 25.000 | 25.0, #12162024 | success, 1.0 s | no log, 60 s limit |
| 25.100 | 25.1, #5062025 | success, 1.2 s | no log, 60 s limit |
| 26.000 | 26.0, #10202025 | success, 1.4 s | success |
| 26.100 | 26.1, #2122026 | success, 1.1 s | success |
| 26.101 | 26.1, #5012026 | success, 0.9 s | success |
| 26.120 | 26.12, #7012026 | success, 1.1 s | success |
| 26.121 | 26.12, #7262026 | success, 0.9 s | success |

One dash works on every registered build. Two dashes work from 26.000
onward and on nothing before it.

Both spellings are documented, each by its own manual edition, which is
why neither is a discovery: the 25.0 edition documents the one-dash
form on its command-line inputs topic, and SRC-003 documents the
two-dash form at pp.279-280. What was not documented anywhere is that
they are not interchangeable.

## What a build does with the spelling it does not know

It does not refuse it. It starts, prints its banner, checks out its
licence successfully, receives no script, and waits for a user who is
never coming. Under `-hidden` with the standard streams redirected
there is no console attached, so when the solver tries to report on
one, the Intel Fortran runtime raises `severe (30): open failure, unit
-1, file CONOUT$` and opens a modal dialog. Nothing answers it. The
harness reaches its timeout and kills a process that was, the whole
time, asking a question.

Three consequences follow, and all three had been read wrongly before
this measurement:

* A clean licence checkout in the captured output is not evidence that
  the run got as far as the script. On these failures the EDU checkout
  succeeded every time.
* An empty log is not evidence of a solver that crashed. Here it is a
  solver that never received work.
* The elapsed time of a failed run carries no information about the
  cause: it is the timeout, chosen by the caller.

## What this refutes

Two diagnoses recorded earlier the same day, both now dead by
measurement, are listed because the plan row and the version registry
carried them in writing.

**The licence-seat hypothesis.** It held that a forced kill did not
release the EDU seat, since one hand run had worked and roughly a dozen
launches after it had not. Every run in this report checked out the EDU
feature successfully, including the first one after that sequence of
kills. The seat was never held.

**The release boundary.** It was recorded as release 26.1. The boundary
is between 25.100 and 26.000, and 26.000 accepts both spellings, so it
is not a boundary between the 25 and 26 series either.

A third claim, recorded in `_private/plan/` and in the version registry
as an open question, was that the harness could not read the 25.000
manual because that install ships only a `.chm`. The file extracts to
960 HTML topics and its command-line topic is where the one-dash form
was read. The claim was true about the pdf sweep tool and false about
the manual.

## What changed in the package

`pyflightstream.run.SCRIPT_ARGUMENT` is `-script`, and every report's
executor line derives from `pyflightstream.run.describe_invocation()`
rather than restating it. The six restatements that lived in the three
report writers are gone; a tier 1 guard asserts the derivation, so the
flag and the sentence describing it cannot disagree again.

One spelling is used for every build rather than one per build,
because one spelling is measured to work on all of them. A future build
that drops it fails its probe baseline loudly, since the baseline
asserts the sentinel reached the exported log and reports the
environment unusable when it did not.

## Reproduction

```
pyfs-qa probe --fs-version 25.000 --fs-exe <install>/FlightStream.exe --identity-only
```

The identity reports written from these runs are
`reports/compat/CMP-25000_2026-08-09_identity.yaml` and its 25100 and
26000 siblings; each carries the solver's own banner, which is where
the build numbers in the table above come from.
