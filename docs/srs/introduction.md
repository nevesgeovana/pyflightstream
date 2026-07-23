# Introduction

## Purpose

pyflightstream is a Python package that drives the FlightStream
panel-method solver programmatically: it builds native ASCII scripts,
executes them headlessly, parses the outputs, and post-processes them
into engineering results. It is the open-source successor of the
author's legacy research scripts, which worked but were built under
research time pressure and accumulated structural debt.

The product vision in one sentence: a version-aware, didactic,
permissively licensed driver for FlightStream that makes silent
failure structurally impossible.

## Context and motivation

### The version-drift problem

FlightStream changes its ASCII scripting commands between versions
with incomplete changelogs. Documented examples from the v26.12 manual
(SRC-003):

- `SONIC_VELOCITY` is no longer supported (SRC-003 p.328).
- The `CP` export variable is deprecated in favor of `CP_REFERENCE`
  and `CP_FREESTREAM` (SRC-003 p.352).
- A slipstream wake stabilization script variable present in earlier
  versions is missing in v26.1.

The predecessor toolchain handled these breaks by commenting commands
in and out per version; nothing recorded which command works in which
version. This recurring pain is the primary design driver.

### The ecosystem gap

The official Python API, pyFlightscript
([github.com/altairengineering/pyFlightscript](https://github.com/altairengineering/pyFlightscript)),
is licensed AGPL-3.0 and deprecated: its repository states it is no
longer supported and that FlightStream 26.0 is the final compatible
version. There is therefore no maintained, version-aware, permissively
licensed Python driver for FlightStream. pyflightstream fills that gap.

### The licensing constraint

pyflightstream is MIT licensed. Because the ecosystem predecessor is
AGPL-3.0, the command-emitter layer is a clean-room implementation,
specified only from the official manual and from observed solver
behavior on licensed machines. The AGPL code is never read at code
level. The author's own logic in her legacy scripts (run-matrix
driver, output parsers, writers, axis transforms) is her intellectual
property and migrates freely.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| The author (owner, maintainer) | Runs FlightStream campaigns for her research; needs the legacy run-matrix files to keep working |
| Aerospace engineers without software background | Primary external audience; need a didactic API, readable errors, and worked examples |
| Future contributors | Need tests, contribution rules, and a command database they can extend with evidence |
| Research groups and co-authors | Need reproducible run provenance for publications |

## Founding decisions (stakeholder brief)

Confirmed decisions recorded at the founding planning session
(2026-07-21) and during execution. Each functional requirement cites
the items it answers.

| Id | Brief item |
|---|---|
| BRF-01 | One single package replaces the fragmented predecessor scripts and notebooks |
| BRF-02 | Open source under MIT, publishable on PyPI |
| BRF-03 | Version-aware by design: FlightStream command drift is a first-class concern, not a patch |
| BRF-04 | Didactic: usable and readable by engineers without software background |
| BRF-05 | Developed in a dedicated repository, separate from the author's research workspace |
| BRF-06 | Private GitHub first; public at a presentable release |
| BRF-07 | FlightStream versions supported at launch: 26.0, 26.1, 26.12 |
| BRF-08 | The existing legacy run-matrix workflow keeps working unchanged |
| BRF-09 | Examples are percent-format `.py` scripts rendered in the docs; no committed notebooks |
| BRF-10 | Clean-room command emitter; no AGPL-derived code |
| BRF-11 | FSI: only an extension seam at v0.1; no structural solver inside the package at launch |
| BRF-12 | The failure modes of the predecessor scripts (silent skips, unverifiable runs, untested parsers) must be structurally impossible, not merely discouraged |
| BRF-13 | Pre-solver definitions (auxiliary coordinate systems and similar) are ordered and enforced by the builder, not left to user discipline |
| BRF-14 | All folder and file names in the repository are in English |
| BRF-15 | The package is also responsible for file management: run folder layout, input staging, output collection, archiving |
| BRF-16 | Simulation-centric naming: SIM replaces POLAR/POL in the native vocabulary |
| BRF-17 | Version-comparison test cases use simple synthetic geometries plus local-only research cases whose geometry never enters the repository |
| BRF-18 | The author's prior analysis pipelines are the design reference for the post-processing layer |
| BRF-19 | FlightStream versions are identified as 26.XXX with a three-digit fractional part; the last digit indexes intermediate hotfix builds |
| BRF-20 | The workspace organizes inputs as well as outputs: a support library of reusable artifacts selected by id, per the author's legacy research workflow (usage-feedback review, 2026-07-22) |

## Pain-point catalog

Defects verified first-hand in the predecessor toolchain's working
tree (2026-07-21). The requirements exist to eliminate them.

| Id | Pain point |
|---|---|
| PP-1 | Duplicated, diverged driver copies |
| PP-2 | Global mutable script state with manual resets between cases |
| PP-3 | Hardcoded user and network paths; dead imports |
| PP-4 | Output parsers indexing results by absolute line number, breaking across versions |
| PP-5 | Silent failure swallowing: bare exception handlers skipping failed cases, unchecked return codes, no convergence pass/fail |
| PP-6 | Run identity only in folder names; no manifest; scripts re-parsed to recover a run's inputs |
| PP-7 | Copy-paste configuration and geometry variants with mislabeled documentation |
| PP-8 | Version gaps handled by commented-out commands |
| PP-9 | No tests, no dependency manifest, private dependencies blocking anyone else from running it |

## References

- SRC-003: Altair FlightStream User Manual, v26.12 (licensed; cited by
  page number throughout the command database; the manual itself never
  enters the repository).
- SRC-725: the 26.1 manual edition, the second citation source of the
  database.
- pyFlightscript repositories (AGPL-3.0, deprecated): prior art for
  scope only, never read at code level.
- The committed evidence trail: `reports/` (probe compat reports,
  physics regression reports, research cards) and the session records
  (`handoffs/`, `STATUS.md`).
