# Reports

Four series, and they are corrected in different ways.

`RPT-nnn_<topic>_<date>.md` are NARRATIVE reports: a person writing
down what a run showed. They are AMENDABLE, and an amendment is
recorded in the title line (`RPT-024 ... (2026-08-09, amended
2026-08-10)`) and, where it retracts something, in the body at the
point it retracts. A reader must be able to see that the file moved
without reading the history.

`compat/CMP-*`, `physics/PHY-*` and `physics/DRF-*` are MACHINE-WRITTEN
evidence and are never overwritten or edited. They are superseded by a
new dated report, or corrected by an erratum beside them; each
directory's own README states its rule. The drift series `DRF-*` was
missing from this sentence until 2026-08-18, which left the
never-edited rule reading as though it did not cover the reports the
cross-version comparison writes. It always did.

`physics/TRI-*` are TRIAGE notes: a disposition of one verdict a
machine-written report recorded, written by a person and citing the
reports it reasons over. They are narrative in the sense above, so they
are amendable and say so when amended, and they never change the
measurement they discuss.

The difference is not ceremony. A narrative report is an argument and
an argument may be corrected in place as long as it says so; a
machine-written report is a measurement, and editing one would change
what a citation elsewhere in the tree resolves to.
