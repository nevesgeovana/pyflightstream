# Command compatibility reports

Committed evidence from Tier 2 probe runs on licensed machines: for each
FlightStream version, which database commands are verified, broken,
removed or unprobed, with pointers to the evidence. Re-applying a
report that a later run has contradicted is refused, so an older report
cannot revert a status. Command database statuses are
promoted only from these reports, never hand-edited (CLAUDE.md
invariant 3). Reports are named `CMP-<version digits>_<date>[_label]`
and are never overwritten.

A report is corrected by a new dated report or by an ERRATUM beside it,
named `<report stem>_erratum_<date>.md`, never by editing the file:
reports are evidence.

An erratum names the RECORD it corrects, not the whole report, and
carries no judgment, so it never promotes a status. It states three
things: the sentence that is wrong, why it is wrong for the build
reported on, and what changed so no future report repeats it.

Whatever cites the corrected RECORD cites the erratum beside it.
Citations of other records in the same report are unaffected, which is
why the rule is not "anything citing the report": the first erratum
corrects one record of a report 84 database rows cite.

A REPORT-LEVEL ERRATUM is admitted since 2026-08-17, and it is the
exception rather than a second shape to reach for. Everything above is
record-scoped by construction, and a defect in a report's own metadata
belongs to no record: there is no sentence to name and no subset of
citations to redirect. The first one corrects a `date` field that a
transient defect in the writer left null while the file name carried the
date correctly. It states the same three things, with the record replaced
by the field, and like every erratum it carries no judgment and promotes
nothing.

Whether this is the right extension of the contract was the author's and
is DECIDED, on 2026-08-18: the extension stands, and the report it was
written for stays as it is rather than being re-emitted under a new
label. The reasoning behind both halves, including what re-emitting would
have cost, is in the erratum rather than repeated here.


## Which binary produced a report

A report records the executable it ran. Until 2026-08-19 it recorded the
NAME alone, and the name does not identify the binary: the vendor
installer calls four registered builds `Flightstream_2612.exe` (26.120,
26.121, 26.122 and 26.123) and three more `FlightStream.exe` (25.000,
26.000 and 26.101). So a reader holding one of those reports could not
say which of the four or three produced it, except by the build number
in the solver identity lines.

Reports written from now on carry `fs_exe_sha256` beside `fs_exe`, in the
YAML and in the Markdown Executable row, and the drift reports carry a
digest per compared version beside `fs_exes`. The field is written even
when it is `None`, which happens when a run went through a stand-in
executor: a key that appears only when a digest was taken makes absence
look like an older schema.

THE COMMITTED CORPUS IS NOT BACK-FILLED and never will be. A digest
nobody measured cannot be recovered from a basename, and these files are
evidence rather than records to be improved. Every report committed
before that date states its executable by name only, and that limitation
is theirs permanently. `COMPAT_SCHEMA` did not move for the addition:
the reader checks the schema marker alone, so old and new reports read
the same way.

The digests of the executables in hand are recorded in
`reports/RPT-032_executable-identity-baseline_2026-08-19.md`, measured by
hashing the files with no solver started. That table is the OLD side of
the comparison a replacement executable will need, and it exists because
on the day of a swap there would otherwise have been nothing to compare
against.

## What a digest does not answer: the licence

The same bytes under two licence seats can behave differently. Command
evidence here is keyed by the canonical version string alone, so a
relicensed binary reporting the same version is the same solver to every
lookup, promotion and refusal in this package, and a command the new seat
REFUSES keeps a `verified` status taken under the old one.

What a licence change could falsify is derived rather than guessed:
`pyflightstream.qa.compat.licence_sensitive_candidates` returns the rows
of a build that came from RUNNING the solver, grouped by chapter, each
naming the report its measurement came from. A `documented` row rests on
a manual page and no licence changes a page, so it is not a candidate.

Which of those candidates a licensed seat is actually spent re-measuring
is a domain judgment the author holds, and no subset is recorded here.
The general rule and the reasoning live in the header of
`src/pyflightstream/commands/_meta.yaml`, beside the version rows it is
about.

## Before a replacement executable spends a seat

Hash it and compare it against the baseline report above; nothing here
starts a process. A recorded digest means the same binary and the
evidence transfers untouched. An unknown digest authorises exactly one
piece of licensed work, `pyfs-qa probe --fs-version <v> --fs-exe <path>
--identity-only`, and its printed build number decides the rest: equal to
the registry's, the evidence transfers and both digests are recorded;
different, and it is a different build, so no further licensed work
starts on that identifier and the disagreement is reported with both
numbers. `pyflightstream.qa.compat.classify_executable` is that decision,
and the three run skills carry it as their step zero.
