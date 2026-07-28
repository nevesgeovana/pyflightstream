# Software Requirements Specification

The SRS of pyflightstream: the authoritative public reference for what
the package must do, must not do, how it must behave, and how the
requirements trace to evidence. It follows the author's SRS template
(shared with her ITACA library), adapted to this documentation site.

## Document identity

| Field | Value |
|---|---|
| Document | pyflightstream Software Requirements Specification |
| Version | 1.2.0 |
| Status | Living document |
| Author | Geovana Neves |
| First published | 2026-07-22 |
| Supersedes | The private founding SRS (design record DLV-002, 2026-07-21), sanitized and updated for publication |

This SRS is a living document. Requirements are added, refined, or
deprecated as use consolidates; every change increments the document
version and lands in the revision history below. Deprecated
requirements are never deleted: they keep their identifier forever and
are tagged deprecated.

The package is implemented with assistance from large language model
tooling. Every implementation derived from these requirements goes
through review by the project author before acceptance. The SRS
describes the desired behavior; the code is verified against the SRS,
and the SRS is corrected only when a requirement itself is found wrong
or ambiguous.

## Chapters

1. [Introduction](introduction.md): purpose, context, and motivation.
2. [Philosophy](philosophy.md): the evidence discipline and the
   didactic policy that shape every requirement.
3. [Scope](scope.md): what is in, and the explicit non-requirements.
4. [Data and evidence model](data-model.md): the command database, the
   run manifest, and the workspace.
5. [Architecture](architecture-srs.md): the layered pipeline and its
   rules, with the generated [architecture overview](../architecture.md)
   as the live companion.
6. [Functional requirements](functional-requirements.md): FR-01 to
   FR-36, each with origin, status, and evidence.
7. [Non-functional requirements](nonfunctional-requirements.md):
   NFR-01 to NFR-12, plus NFR-19, NFR-20 and NFR-22 to NFR-24 from the
   2026-07-27 acceptance batch (NFR-13 to NFR-18 and NFR-21 are
   reserved identifiers their own lanes write).
8. [Standards alignment](standards.md): the external practices this
   project adopts, with references.
9. [Roadmap](roadmap.md): delivered milestones and the open lines.

## Conventions

Requirement identifiers are stable and never renumbered:

| Prefix | Meaning |
|---|---|
| FR-XX | Functional requirement (what the package shall do) |
| NFR-XX | Non-functional requirement (how the package shall behave) |
| NREQ-XX | Non-requirement (what the package shall not do or be) |
| BRF-XX | Stakeholder brief item (a confirmed founding decision) |
| PP-X | Pain point verified in the predecessor toolchain |

Each requirement carries an origin tag (the BRF and PP items it
answers) and one status:

| Status | Meaning |
|---|---|
| <span class="srs-implemented">implemented</span> | Corresponding code exists, tested, and shipped |
| <span class="srs-pending">pending</span> | Agreed, not yet implemented |
| <span class="srs-deferred">deferred</span> | Implementation waits on an external gate (usually licensed-machine evidence) |
| <span class="srs-draft">draft</span> | Still being refined |
| <span class="srs-deprecated">deprecated</span> | Superseded; kept for traceability |

Statuses cite their evidence: a milestone in [the roadmap](roadmap.md),
a committed report under `reports/`, or a plan item. Nothing is marked
implemented without a shipped test behind it.

One clarification, because the 2026-07-27 batch made the distinction
visible and a reader met the same badge meaning two things. A
requirement whose normative core is shipped and guarded is
<span class="srs-implemented">implemented</span> even when it names an
open half, and the open half is named in its origin tag rather than
hidden by the badge (NFR-19 is the example: its schemas are documented
and tested, and publishing them as an API reference page is open). A
requirement whose normative core does not bind yet is
<span class="srs-pending">pending</span> even when the mechanism it
will use is already shipped (NFR-20 is the example: the deprecation
ledger and its deadline guard exist, and the policy itself starts at
1.0).

## Revision history

| Version | Date | Change |
|---|---|---|
| 1.2.0 | 2026-07-27 | The author's Phase 4 acceptance batch begins landing, and with it one architectural move: pandas and xarray leave the runtime set at v0.5.0 and the sister library becomes a core dependency. AD-06 restated (invalidated, not adapted), AD-07 restated from a future optional extra to a core dependency, AD-05 stops restating the dependency set, NFR-06 gives the set one home with the release that changes it, and five requirements are added: NFR-19 (result column-schema stability, written substrate-neutral, separating universal documentation from a scoped stability promise and naming what the promise excludes), NFR-20 (deprecation policy: it states in its own text that it governs from 1.0, which supersedes the 2026-07-23 answer that had put a deprecation cycle on the `run_frame`/`sweep_frame` rename; that from 1.0 the removal itself lands in a major release, so it cannot be read against NFR-04's SemVer commitment; that within 0.x a break lands only in a minor and never in a patch, a bound codified by the API-design review and awaiting the author's confirmation; and that its code-enforced half covers module shims only. Its status is pending, because the policy does not bind until 1.0), NFR-22 (dependency version envelope, with the pre-1.0 pin form, the Python-ceiling propagation that no requirement covered, and NFR-02's license-evidence obligation for the new core dependency), NFR-23 (layering guard, accepted as this package's own rather than a mirror) and NFR-24 (software jargon glossed, with the glossary rows it requires). The conventions section gains the rule that distinguishes an implemented requirement with a named open half from a pending one whose mechanism already ships, and NFR-11 gains the home-of-record clause that covers a copy which can be neither generated nor linked |
| 1.1.3 | 2026-07-23 | FR-33 gains the per-point output-name rule: a case whose sweep points would render the same output name is blocked before it runs, because they share one simulation folder (incident INC-20260723-2113) |
| 1.1.2 | 2026-07-23 | FR-22 restated after a re-reading of the manual page (SRC-003 p.202): the vorticity CDi selection is an optional input, leaving it unset is the documented solver default (surface pressure integration on every boundary) and is recorded in the solver-setup snapshot rather than refused, and the snapshot states unknown on a version without recorded evidence for the command (PLN-075) |
| 1.1.1 | 2026-07-23 | Standards alignment updated: the docs toolchain row moved to ProperDocs after the green drop-in test (this row also repairs the missed increment of that edit), the Sybil vehicle recorded on the executable-examples backlog row, and the pyproject metadata row updated for the landed classifiers and URLs |
| 1.1.0 | 2026-07-23 | Role-based review model added to the standards alignment; AD-07 co-development with ITACA added to the architecture chapter, with the sister library page and the ITACA adapter open line |
| 1.0.0 | 2026-07-22 | First public edition: the founding requirements (FR-01 to FR-29) updated with implementation statuses through v0.2.0 and the v0.3 line, plus the usage-feedback requirements (FR-30 to FR-36) and the documentation-currency policy (NFR-11) |

## Glossary

The software terms below are here because this document declares a
readership of aerodynamicists rather than software engineers, which
makes unexplained software jargon a clarity defect (NFR-24).

| Term | Meaning |
|---|---|
| Campaign | A declared set of simulations sharing a FlightStream version, executable, and workspace |
| Clean-room | Written from the vendor manual and from probe evidence alone, never by reading another implementation; the rule that keeps this package free of the AGPL-3.0 licensed predecessor named in the [introduction](introduction.md), whose license would otherwise reach this code |
| Command database | The machine-readable registry of FlightStream script commands with per-version evidence |
| Escape hatch | A deliberate way out of the validated path (here, emitting a raw solver line the builder does not model), allowed but recorded so its use is visible |
| Golden | A committed reference output a test compares against byte for byte, so an unintended change to generated text fails loudly |
| Manifest | The append-only `runs.json` record that is the sole authority on run identity |
| Probe | A minimal solver run asserting one command's real effect on a licensed machine |
| Round-trip | Writing a structure out and reading it back, asserting the result equals the original; the test that proves a writer and its reader agree |
| `shell=True` | A Python option that hands a command to the operating system shell to interpret; refused here, because it makes a path containing a space or a quote behave as syntax |
| Shim | A thin stand-in left at an old name so existing code keeps working after a rename, warning as it goes; it is removed at the version its warning names |
| SIM | The native unit of work (a simulation case with a `sim_id`); the run-matrix vocabulary uses POLAR/POL |
| Substrate | The library the values physically live in (today pandas for tables and xarray for labeled fields), as distinct from the shape they are arranged in, which is what a requirement promises |
| Tidy table | One row per observation and one column per variable, the shape FR-32 converts every parser result into. The substrate holding that shape is pandas today and changes at v0.5.0 (AD-06); the shape is what the name means, not the library |
| Tier 1/2/3 | The QA ladder: CI-runnable tests / licensed command-validity probes / licensed physics regression |
| Workspace | The managed folder tree owning inputs, runs, and post-processing outputs |
