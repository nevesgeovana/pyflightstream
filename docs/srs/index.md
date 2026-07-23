# Software Requirements Specification

The SRS of pyflightstream: the authoritative public reference for what
the package must do, must not do, how it must behave, and how the
requirements trace to evidence. It follows the author's SRS template
(shared with her ITACA library), adapted to this documentation site.

## Document identity

| Field | Value |
|---|---|
| Document | pyflightstream Software Requirements Specification |
| Version | 1.1.0 |
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
   NFR-01 to NFR-12.
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

## Revision history

| Version | Date | Change |
|---|---|---|
| 1.1.0 | 2026-07-23 | Role-based review model added to the standards alignment; AD-07 co-development with ITACA added to the architecture chapter, with the sister library page and the ITACA adapter open line |
| 1.0.0 | 2026-07-22 | First public edition: the founding requirements (FR-01 to FR-29) updated with implementation statuses through v0.2.0 and the v0.3 line, plus the usage-feedback requirements (FR-30 to FR-36) and the documentation-currency policy (NFR-11) |

## Glossary

| Term | Meaning |
|---|---|
| Campaign | A declared set of simulations sharing a FlightStream version, executable, and workspace |
| Command database | The machine-readable registry of FlightStream script commands with per-version evidence |
| Manifest | The append-only `runs.json` record that is the sole authority on run identity |
| Probe | A minimal solver run asserting one command's real effect on a licensed machine |
| SIM | The native unit of work (a simulation case with a `sim_id`); the legacy vocabulary used POLAR/POL |
| Tier 1/2/3 | The QA ladder: CI-runnable tests / licensed command-validity probes / licensed physics regression |
| Workspace | The managed folder tree owning inputs, runs, and post-processing outputs |
