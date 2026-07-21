# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. MIT licensed.

Status: pre-alpha, milestone M0 (repository skeleton).

## The idea in one paragraph

FlightStream is scripted through ASCII command files, and the command set
changes between solver versions with an incomplete changelog. This package
makes the FlightStream version an explicit input. A per-version command
database, with a manual page citation for every entry and empirical probe
evidence for every verified status, backs a script builder that refuses to
emit anything invalid for the requested version. Old versions are only ever
added, never dropped.

## Planned documentation

* Getting started: install, license prerequisites, first steady polar.
* Campaign tutorial: the native campaign format and the legacy matrix.
* Command reference: auto-generated from the database, with per-version
  status badges.
* Version compatibility matrix: generated from committed probe reports.
* Physics QA methodology: the regression matrix and its tolerance policy.
* Migrating from the legacy run-matrix scripts.

These pages arrive with milestones M1 through M5.
