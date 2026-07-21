# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. MIT licensed.

Status: pre-alpha, milestone M5 (documentation site).

## The idea in one paragraph

FlightStream is scripted through ASCII command files, and the command set
changes between solver versions with an incomplete changelog. This package
makes the FlightStream version an explicit input. A per-version command
database, with a manual page citation for every entry and empirical probe
evidence for every verified status, backs a script builder that refuses to
emit anything invalid for the requested version. Old versions are only ever
added, never dropped.

## The documentation

* [Command reference](reference/index.md): generated from the database at
  every docs build, one page per manual chapter, with per-version evidence
  for every command. `pyflightstream.help()` renders the same database
  offline.
* [Compatibility matrix](compatibility.md): every command against every
  registered FlightStream version, generated from the same database. Cells
  are filled only by evidence: a manual citation for `documented`, a
  committed probe report for `verified` and `broken`. Empty cells are
  honest gaps awaiting backfill.

## Evidence discipline

The three QA tiers behind the statuses:

* Tier 1 runs in CI without the solver: schema integrity, builder
  goldens, parser fixtures.
* Tier 2 probes command validity on a licensed machine; reports live
  under `reports/compat/` and statuses are promoted only from them.
* Tier 3 runs a physics regression matrix and a cross-version drift
  suite; reports live under `reports/physics/`.

## Planned next

* Getting started guide: install, license prerequisites, first steady
  polar.
* Steady polar example rendered from the percent-format script in
  `examples/`.
* Campaign tutorial: the native campaign format and the legacy matrix.
* Migrating from legacy run-matrix scripts.
