# Introduction

## Purpose

pyflightstream is a Python package that drives the FlightStream
panel-method solver programmatically: it builds native ASCII scripts,
executes them headlessly, parses the outputs, and post-processes them
into engineering results. It is the open-source successor of the
reference legacy research scripts, which worked but were built under
research time pressure and accumulated structural debt.

The product vision in one sentence: a version-aware, didactic,
permissively licensed driver for FlightStream in which every failure
is reported and no run passes without its evidence.

The specification has two layers. The
[numerical laboratory method](numerical-laboratory-method.md) states,
for any solver driven as an instrument, eleven goals and the central
requirements of a numerical experiment run with the rigor of a
wind-tunnel test: instrument knowledge, experiment design, specimen
preparation, physics configuration, translation to the instrument,
execution, records, data reduction, trust, the workspace and operation.
The requirement set of this document instantiates that method for
FlightStream: each feature derives from the central requirements it
realizes and is refined down to the behaviour a test verifies.

## Context and motivation

### The version-drift problem

FlightStream is under active development, and its team is notably
responsive: user requests land quickly, often first in intermediate
hotfix builds that consolidate into stable releases. The natural
counterpart of that pace is an ASCII scripting command set that
evolves between versions faster than any single document can track.
Documented examples from the v26.12 manual (FSM-26.120):

- `SONIC_VELOCITY` is no longer supported (FSM-26.120 p.328).
- The `CP` export variable is deprecated in favor of `CP_REFERENCE`
  and `CP_FREESTREAM` (FSM-26.120 p.352).
- A slipstream wake stabilization script variable present in earlier
  versions is missing in v26.1.

The predecessor toolchain handled these changes by commenting commands
in and out per version; nothing recorded which command works in which
version. That gap, on the toolchain side rather than the solver side,
is the primary design driver.

### The ecosystem gap

The official Python API, pyFlightscript
([github.com/altairengineering/pyFlightscript](https://github.com/altairengineering/pyFlightscript)),
is licensed AGPL-3.0 and deprecated: its repository states it is no
longer supported and that FlightStream 26.0 is the final compatible
version. There is therefore no maintained, version-aware, permissively
licensed Python driver for FlightStream. pyflightstream fills that gap.

### The licensing constraint

pyflightstream is MIT licensed. Because the ecosystem predecessor is
AGPL-3.0, the command-emitter layer is a clean-room implementation
([glossary](https://github.com/nevesgeovana/pyflightstream/blob/main/docs/unpublished/requirements/index.md#glossary), where this and the other software
terms of this document are defined): specified only from the official
manual and from observed solver behavior on licensed machines. The AGPL code is never read at code
level. The engineering logic in the project's own legacy scripts (run-matrix
driver, output parsers, writers, axis transforms) is this project's own
intellectual property and migrates freely.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Maintainer | Runs FlightStream campaigns for research; needs the existing run-matrix files to keep working |
| Aerospace engineers without software background | Primary external audience; need a didactic API, readable errors, and worked examples |
| Future contributors | Need tests, contribution rules, and a command database they can extend with evidence |
| Research groups and co-authors | Need reproducible run provenance for publications |

## Founding decisions (stakeholder brief)

The stakeholder brief establishes the package
boundaries. Each functional requirement cites
the items it answers.

| Id | Brief item |
|---|---|
| BRF-01 | One single package replaces the fragmented predecessor scripts and notebooks |
| BRF-02 | Open source under MIT, publishable on PyPI |
| BRF-03 | Version-aware by design: FlightStream command drift is a first-class concern, not a patch |
| BRF-04 | Didactic: usable and readable by engineers without software background |
| BRF-05 | Developed in a dedicated repository, separate from the research workspace |
| BRF-06 | Private GitHub first; public at a presentable release |
| BRF-07 | FlightStream versions supported at launch: 26.0, 26.1, 26.12 |
| BRF-08 | The existing run-matrix workflow keeps working unchanged |
| BRF-09 | Examples are percent-format `.py` scripts rendered in the docs; no committed notebooks |
| BRF-10 | Clean-room command emitter; no AGPL-derived code |
| BRF-11 | FSI provides structural analysis and an experimental coupling interface; live coupled accuracy needs licensed validation |
| BRF-12 | The failure modes of the predecessor scripts (silent skips, unverifiable runs, untested parsers) must be structurally impossible, not merely discouraged |
| BRF-13 | Pre-solver definitions (auxiliary coordinate systems and similar) are ordered and enforced by the builder, not left to user discipline |
| BRF-14 | All folder and file names in the repository are in English |
| BRF-15 | The package is also responsible for file management: run folder layout, input staging, output collection, archiving |
| BRF-16 | Simulation-centric naming: SIM replaces POLAR/POL in the native vocabulary |
| BRF-17 | Version-comparison test cases use simple synthetic geometries plus local-only research cases whose geometry never enters the repository |
| BRF-18 | The reference prior analysis pipelines are the design reference for the post-processing layer |
| BRF-19 | FlightStream versions are identified as YY.XXX, the vendor major with a three-digit fractional part; the last digit indexes intermediate hotfix builds |
| BRF-20 | The workspace organizes inputs as well as outputs: a support library of reusable artifacts selected by id, per the research workflow |

## Pain-point catalog

Defects verified first-hand in the predecessor toolchain's working
tree. The requirements exist to eliminate them.

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

- FSM-26.120: Altair FlightStream User Manual, v26.12 (licensed; cited by
  page number throughout the command database; the manual itself never
  enters the repository).
- FSM-26.100: the 26.1 FEBRUARY 2026 manual edition, shipped with the
  26.100 install, 396 pages. A separate source rather than a
  re-issue of FSM-26.101 below: the vendor shipped two editions under
  the one release name and no page citation carries between them.
- FSM-26.101: the 26.1 MAY 2026 manual edition, the second citation source of the
  database.
- FSM-26.121: the 26.12 hotfix-1 manual edition, shipped with the 26.121
  build (licensed; local, never in the repository). A separate source
  rather than a re-issue of FSM-26.120, because its scripting reference is
  shifted by three pages throughout, so an FSM-26.120 page number does not
  address the same page in it.
- pyFlightscript repositories (AGPL-3.0, deprecated): prior art for
  scope only, never read at code level.
- The committed evidence trail: `reports/` (probe compat reports,
  physics regression reports, research cards). The reference session
  records are private and cited by HND id where relevant.
