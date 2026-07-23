# Roadmap

The delivered milestones and the open lines. This chapter is the
SRS-level summary and is updated when milestones close; the author's
private session records carry the day-to-day detail.

## Delivered

| Milestone | Content | Closed |
|---|---|---|
| M0 | Repository skeleton, CI, guards | 2026-07-21 |
| M1 | Version registry, command database schema and loader, core steady commands with citations | 2026-07-21 |
| M2 | Script builder, helpers, workspace, executor, campaign loop, manifest, parsers, run-matrix reader | 2026-07-21 |
| M3 | Probe harness, first compat report, status promotion | 2026-07-21 |
| M4 | Physics cases, version-comparison (drift) suite, local research-case class | 2026-07-21 |
| M5 | Docs site generated from the database, steady polar example | 2026-07-21 |
| v0.1.0 | First tag (private phase) | 2026-07-21 |
| M6 | FSI subpackage: structural branch, coupled driver, near-rigid pilot; two-way rotor coupling solver-blocked with the finding reported upstream | 2026-07-21 |
| M7 | Far-field extraction: probe lattices, planar grids with geometry gating, conservation ledgers, licensed round trip | started 2026-07-21, core delivered |
| v0.2.0 | First public release: PyPI, Zenodo DOI, citation metadata | 2026-07-22 |
| Usage-feedback line | FR-30 to FR-36: labels, provenance, tables, workspace input library, pre-flight and resume, matrix first-class, two-level help | 2026-07-22 |

## Open lines

| Line | Content | Gate |
|---|---|---|
| Licensed evidence queue | OBJ export group-name probe (FR-30 inspector), undocumented solver defaults (FR-31), physics reference re-validation under the new minimum-Cp default, mesh-refinement and solver-flag physics cases, FSI family sweep, broken-command re-probes, 26.100 backfill | Licensed machine sessions |
| v0.3.0 release | Promote the Unreleased changelog; user guide refresh; metadata completeness | The author calls the release |
| Post-processing completion | FR-20 (labeled result arrays, interpolation, trim extraction) and FR-21 (established plot-file writers) | Design session |
| Process adoption backlog | VCS-derived versioning, executable doc examples, mechanical repo review, supply-chain posture, support-window declaration (see [standards](standards.md)) | The author's per-item decisions |
| Integrations | The RPT-008 decision list: pyvista viz extra, documented external-tool bridges | The author's review |
| ITACA adapter | The `[itaca]` extra of AD-07: manifest, solver-setup snapshot, and result tables exported as ITACA datasets with provenance (supersedes the RPT-008 on-hold entry) | Dedicated session; ITACA capability per structure |
| HPC executor | FR-15 | Research-group cluster path |
| Docs toolchain | The generator's upstream governance question | The author's decision |

## Requirement-to-work traceability

Every functional requirement above carries its status and evidence
inline. The working queue and session records live in the author's
private planning files (stable PLN and HND ids); committed reports
under `reports/` are the public evidence terminal. This SRS points at
those records rather than duplicating them, per the single-home rule
of NFR-11.
