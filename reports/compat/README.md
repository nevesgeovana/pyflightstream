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

Whether this is the right extension of the contract is the author's, and
is marked as owed in the erratum itself rather than settled here.
