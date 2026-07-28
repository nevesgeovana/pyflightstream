# Acceptance to requirement mapping

Every item the author accepted at the Phase 4 gate of 2026-07-27, and
the SRS identifier it became. This page exists because 24 of her 55
acceptances arrived with no requirement id of their own, so without a
recorded mapping the question "did this land?" has no answer anyone can
check twice.

It is a register of allocations, not a second home for the requirements
themselves. Each row points at the identifier; what the requirement says
lives in the SRS and nowhere else.

## How to re-run the check

Parse the accepted set out of the decision export, parse
`!!! requirement "ID` out of `docs/srs/*.md`, and compare. The measured
result on 2026-07-27: 65 items in the export, of which 55 accepted, 7
deferred to a seat, 1 closed as a citation, and 2 answered in prose. The
machine-readable index of the resulting requirement set is published at
`reports/requirements-index.json`.

## Accepted with their own identifier

These landed under the id they were accepted with; the register records
only that they exist, since the id is its own mapping.

| Accepted as | Landed as | Note |
|---|---|---|
| NFR-19, NFR-20, NFR-22 | same | Written 2026-07-27 with the batch's own decisions folded in |
| NFR-13 to NFR-18, NFR-21 | same | Written by this consolidation; the reserved-identifier convention they were held under is retired with it |
| FR-37 to FR-42 | same | Two restated, both disclosed in their own text. FR-41: its draft placed the adapter behind an optional extra, which AD-07 removed in the same batch. FR-37: its draft named the status value NOT_CONVERGED, and the value is left unnamed here because naming it decides the FR-46 collision below, which is the product owner's call |
| FR-02b, FR-22a/b/c, FR-30a/b/c, FR-31a/b, FR-33a/b/c, NFR-01a/b/c/d | same | The SIX accepted splits, one per base. The routing brief counted five because it grouped FR-02b with the rewords; it is a split, and every base keeps its identifier and gains an umbrella role |
| FR-06, FR-08, FR-10, FR-11, FR-20, FR-26, FR-31, NFR-07, NFR-08 | same | The NINE rewords, all performed 2026-07-27, each requirement stating what changed and why. The brief listed ten by including FR-02b, which is the split above |

## Accepted without an identifier

The allocation below is this session's, per the brief that made it this
repository's call. Two of them were allocated earlier the same day and
are included so the register is complete.

| Accepted as | Landed as | Why there |
|---|---|---|
| C1 Validated option registry | FR-40 | Same subject, and FR-40's draft is the wider statement of it. Her choice also made every registered option name a stable public contract, which FR-40 now carries |
| C2 Exception catalog with a completeness guard | FR-39 | The catalog and its guard are the mechanism FR-39 asserts |
| C3 Three-part actionable errors | NFR-01c | Error content is the didactic error clause, which the NFR-01 split gave its own identifier |
| C4 Console entry-point contract | FR-44 | New identifier; no accepted id covered the CLI surface. Written in the FULL-contract form she chose, where commands and flags change only under the deprecation policy, rather than the narrower recording-only form the review recommended and she declined |
| C5 Strict manifest schema | FR-45 | New identifier; FR-19 governs the manifest's authority, not its field discipline |
| C6 Closed terminal-status set | FR-46 | New identifier. Read with FR-37, which asks for a value this set does not contain |
| C7 Probe-data export writers | FR-21, folded | NOT given an identifier, because her recorded choice was to fold it under the post-processing line rather than make it a public functional requirement, and the worksheet offered that second option explicitly. The capability ships; FR-21 records it. A first draft of this consolidation minted FR-47 for it, which was the option she declined |
| C8 Public test-support assertions | FR-47 | New identifier; no accepted id covered the testing surface |
| C9 Optional-dependency error shape | NFR-25 | Her choice was to elevate AD-05 to a tested requirement, which is what NFR-25 is |
| C11 Far-field conservation ledger | FR-38 | Same subject; the brief names the two together |
| M1 Error pattern and typed hierarchy | FR-39 | Same subject as C2, from the sister-library mirror side |
| M2 Import-policy guard | NFR-23 | Allocated 2026-07-27; accepted as this package's own rather than a mirror |
| M3b State-hash scope and determinism | NFR-15 | Same subject: what a reproducibility hash excludes |
| M4 Provenance and the PROV model | NFR-07 (part a) | She accepted the split (a) and DEFERRED the standardized export (b), so only (a) landed |
| M5 TDD and a coverage floor | NFR-16 | Same subject |
| M6 Optional-dependency handling | NFR-25 | Same subject as C9, from the mirror side |
| T3 Traceability approach | NFR-13 | Same subject |
| TRC-01 Requirement-marker convention | NFR-13 | The marker convention is the mechanism NFR-13 asserts, so it is one requirement rather than two |
| SH-manifest-authority | FR-19 | A single-home edit, not a new requirement |
| SH-dependency-set | NFR-06 | Landed 2026-07-27: AD-05 stopped restating the set and cites NFR-06 |
| SH-explicit-inputs | AD-04 | Landed: FR-09 cites AD-04 rather than restating the rule |
| SH-no-global-state | AD-03 | Landed: FR-05 cites AD-03 and states only its script-construction consequence |
| TERM-software-jargon | NFR-24 | Allocated 2026-07-27 |
| TERM-unit-of-work | NFR-26 | New identifier; the domain-vocabulary sibling of NFR-24 |

## Not landed, and why

None of these is an omission, and each is listed so that a later reader
does not have to work out whether it was forgotten.

| Item | Status | Why |
|---|---|---|
| FR-22 (probe promotion) | Blocked by EVIDENCE | Needs a licensed probe run, not a decision |
| FR-26 (reference validation) | Blocked by EVIDENCE | Needs measured data |
| FR-21 (resolution) | Blocked by EVIDENCE | Needs a byte-level comparison that has not been run |
| FR-43 (conservation imbalance band) | Blocked by EVIDENCE | Deferred to the numerical seat; the sister computes the imbalance and returns no acceptance criterion, and that judgement stays here where the case, mesh and solver context is |
| SCOPE-fsi-classification | With the author | Product-owner seat, needs no run |
| SCOPE-audience-tiebreak | With the author | Product-owner seat, needs no run |
| SCOPE-interp-trim-ownership | Deferred to the product seat, then answered | The export records a deferral; decision record DEC-002 A9 answered it afterwards. Filed here as both, because filing a deferral as answered is the direction that hides open work |
| SCOPE-farfield-mission | Answered in prose | One of the two items she answered as free text with no option selected; it is half of the single architectural move that produced AD-06 and AD-07, the other half being M3a |
| M3a (array immutability) | Answered elsewhere | Decision record DEC-002 A1; it is the prose answer that produced AD-06 |
| C10 | Closed as a citation | She closed it on FR-31 with no new requirement |
| M4 (b), the PROV export | Deferred by her | Accepted the split (a) and deferred the standardized export |

## One tension this mapping surfaced

FR-37 and FR-46 are both her acceptances and they disagree. FR-46 closes
the terminal-status set at the six values the code carries; FR-37 asks
for a status distinct from a completed one, and a run that hits the
iteration cap without converging currently lands in a value whose name
says completed. Satisfying FR-37 makes the set seven.

Recorded here rather than resolved, because choosing between two
acceptances is the product owner's call and not this consolidation's.
Both requirements state the collision in their own text.
