# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. MIT licensed.

Status: v0.2.0 is public on PyPI; the changelog records what each
release adds. Four command-line tools ship with the package: `pyfs-qa`
(probes, physics regression, drift), `pyfs-workspace` (campaign
workspace init), `pyfs-matrix` (run-matrix convert and pre-flight),
and `pyfs-fsi` (the aeroelastic coupling executable).

## The idea in one paragraph

FlightStream is scripted through ASCII command files, and the solver is
under active development, with intermediate hotfix builds consolidating
user requests into stable releases; the command set evolves with it. This
package makes the FlightStream version an explicit input. A per-version command
database, with a manual page citation for every entry and empirical probe
evidence for every verified status, backs a script builder that refuses to
emit anything invalid for the requested version. Old versions are only ever
added, never dropped.

## The documentation

* [Software Requirements Specification](srs/index.md): the living SRS,
  from the founding requirements to the usage-feedback line, each with
  origin, status, and evidence.
* [Architecture overview](architecture.md): the layered pipeline and one
  section per subpackage, generated at every docs build from the live
  module docstrings. `pyflightstream.overview()` renders the same page
  offline.
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
* Campaign tutorial: the workspace input library, pre-flight, and
  resumable sweeps.
* Migrating run-matrix files to campaign.toml (the `pyfs-matrix` CLI
  already converts and pre-flights them).
