# Command compatibility reports

Committed evidence from Tier 2 probe runs on licensed machines: for each
FlightStream version, which database commands are verified, broken,
removed or unprobed, with pointers to the evidence. Re-applying a
report that a later run has contradicted is refused, so an older report
cannot revert a status. Command database statuses are
promoted only from these reports, never hand-edited (CLAUDE.md
invariant 3). Reports are named `CMP-<version digits>_<date>[_label]`
and are never overwritten; the newest promotable one per pair is what
the database cites, and re-applying an older one is refused.

A report is corrected by a new dated report or by an ERRATUM beside it,
named `<report stem>_erratum_<date>.md`, never by editing the file. An
erratum is not a report and carries no judgment; anything citing a
report that has one cites both.
