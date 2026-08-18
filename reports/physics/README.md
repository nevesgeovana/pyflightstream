# Physics regression reports

Committed evidence from Tier 3 runs on licensed machines: the physics
regression matrix compared against stored references with WARN and FAIL
tolerance bands, plus the cross-version drift suite (synthetic cases
committed; research geometry stays local, only aggregated coefficients
appear here).

THREE SERIES LIVE IN THIS ONE DIRECTORY, and until 2026-08-18 this file
named one of them. `../README.md` is the single home of the taxonomy and
of the correction regimes; what follows is this directory's own naming
rule, which is the part `../README.md` says each directory states for
itself.

`PHY-<version digits>_<date>[_label]` is one Tier 3 physics run on one
build, judged against the stored references. Machine-written, never
overwritten and never edited; superseded by a new dated report, or
corrected by an erratum beside it.

`DRF-<A digits>-<B digits>_<date>[_label]` is one cross-version drift
comparison, the two builds in the order compared and never sorted, so
`DRF-26122-26123` and `DRF-26123-26122` would be different reports.
Machine-written under the same rule as `PHY-`. It was absent from the
never-edited sentence in `../README.md` until 2026-08-18, which is worth
one line here because the omission read as an exemption.

`TRI-<subject>_<date>.md` is a TRIAGE note: a person's disposition of one
verdict a machine-written report recorded, citing the reports it reasons
over and changing none of them. Narrative, so it is amendable and says
so in its title line when amended. Two exist,
`TRI-SMI01-CMy_2026-07-21.md` and `TRI-26123-CDo_2026-08-18.md`, and the
second amended itself the day it was written.

The stored references the `PHY-` series is judged against are not here:
they live in `src/pyflightstream/qa/references/` and are written only by
`pyfs-qa update-reference`, which demands a reason string (SAD Section
11).
