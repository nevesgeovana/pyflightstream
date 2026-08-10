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

## One more thing the runs measured: the banner is not byte-identical

The 25.0 solver writes a NUL byte into its console banner where the
newer builds write a space: `FlightStream version \x00 25.0, build
#12162024` on standard output, against a plain space on 26.121. The
EXPORTED LOG carries a plain space on both, which is why the committed
reports show no difference and why this is recorded here rather than
being visible in them.

It is recorded for two reasons. It is why the build-correspondence page
shows the release name and the build number as separate fields instead
of a banner line a reader would compare character by character. And the
first version of that page's guard said "two spaces", which is what a
terminal draws that byte as: reading a rendering is not reading bytes,
and this repository has an incident on exactly that
(INC-20260724-0410-shared).

## What changed in the package

`pyflightstream.run.SCRIPT_ARGUMENT` is `-script`, and every report
written FROM NOW ON derives its executor line from
`pyflightstream.run.describe_invocation()` rather than restating it. The
six restatements that lived in the three report writers are gone; a
tier 1 guard asserts the derivation, so the flag and the sentence
describing it cannot disagree again.

Reports committed BEFORE this fix are unchanged and correct as written:
they record runs that really did pass two dashes. The four 26.1x
identity reports of 2026-08-09 are among them, so two reports produced
the same day on the same harness carry different executor lines, and
that is a record of the fix landing between them rather than an
inconsistency. Both spellings work on those four builds, which is why
those runs succeeded at all.

One spelling is used for every build rather than one per build,
because one spelling is measured to work on all of them. A future build
that drops it fails its probe baseline loudly, since the baseline
asserts the sentinel reached the exported log and reports the
environment unusable when it did not.

## How the runs were made, and what cannot be re-run

THE TWO-DASH COLUMN CANNOT BE REPRODUCED THROUGH THIS PACKAGE, and that
is by design: `SCRIPT_ARGUMENT` is a module constant and `LocalExecutor`
exposes no parameter for it, so no public surface can ask for the
spelling that fails. Reproducing that column means driving the
executables directly, as the sweep did.

The sweep was a local PowerShell script under
`_private/exe/handrun/`, NOT COMMITTED, because it names licensed
install paths (invariant 1) and a licensed machine to run on. Its shape,
so it can be rebuilt:

* One script for every run, the probe harness baseline: a `PRINT` of a
  sentinel, an `EXPORT_LOG` naming an absolute path, and
  `CLOSE_FLIGHTSTREAM`. Its grammar came from the command database
  through `Script`, not from hand; a hand-written `EXPORT_LOG` written
  inline where it is `param_lines` is what produced the first day's
  wrong diagnosis.
* Fourteen runs, seven builds by two spellings. Each launched
  `-hidden <flag> <script>` with standard output and standard error
  redirected to files, a 60 second limit, and the working directory set
  to the script's own folder.
* Success was asserted, not eyeballed: the exported log had to exist and
  contain the sentinel. A run that did not exit was force-ended before
  the next began.
* The artifacts (per-run stdout, stderr and exported log) were
  overwritten by each successive run and are not retained. The table
  above is the record.

What CAN be re-run through the package, for the chosen spelling on any
one build:

```
pyfs-qa probe --fs-version 25.000 --fs-exe <install>/FlightStream.exe --identity-only
```

The identity reports written that way are
`reports/compat/CMP-25000_2026-08-09_identity.yaml` and its 25100 and
26000 siblings; each carries the solver's own banner, which is where
the build numbers in the table above come from.

One caveat on those three reports and on the four 26.1x ones dated the
same day: each records `package_version: 0.5.0`, and the code that
produced them was the 0.6.0 tree. The environment's editable install
carried stale metadata, so the package misreported its own version. The
reports are not rewritten, a compat report being evidence that the
writer refuses to overwrite; the cause is guarded upstream instead, by
`tests/test_metadata_currency.py`, which now fails when the installed
metadata disagrees with the source tree and names the one-line remedy.
`CMP-26121_2026-08-09_v060-onedash.yaml` is the same measurement taken
after that fix and records 0.6.0.
