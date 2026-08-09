# Sister library: ITACA

[ITACA](https://github.com/nevesgeovana/itaca) (Integrated Toolkit
for Aerospace Computation and Analysis,
[PyPI](https://pypi.org/project/itaca/)) is this project's sister
library by the same author: a Python library for rigorous engineering
data management, analysis, and computation, with mandatory
provenance, GUM-compliant two-component uncertainty propagation
including covariance, and a NumPy-only core. The two libraries are
co-developed as consciously integrated projects: the normative seam
rules live in [AD-07](srs/architecture-srs.md) here and in DD-22 and
DD-23 of
[ITACA's decision log](https://github.com/nevesgeovana/itaca/blob/main/docs/DECISIONS.md);
this page is the narrative view.

## The division of labor

| Concern | Home |
|---|---|
| Driving FlightStream: version-aware command emission, execution, campaign management, run provenance | pyflightstream |
| Generic engineering data management: labeled datasets, provenance graphs, uncertainty propagation, publication plotting | ITACA |
| Solver-specific knowledge (command database, probe evidence, physics regression) | pyflightstream, always |
| The adapter between the two | pyflightstream, over ITACA as a core dependency |

ITACA is solver-agnostic by requirement and never imports
pyflightstream; pyflightstream's exporter will map the run manifest,
the solver-setup provenance snapshot, and the parsed result tables
into ITACA datasets, so a campaign's outputs arrive in the data layer
with their provenance already attached.

The relationship changed on 2026-07-27 and the change is larger than a
packaging detail. ITACA was going to be an optional extra a user could
decline; the author's decision makes it a core runtime dependency,
because [AD-06](srs/architecture-srs.md) drops pandas and xarray and
puts the result structures on ITACA over NumPy instead. Two practical
notes for anyone reading this page against the code:

* Nothing has been installed yet. `pyproject.toml` still declares
  pandas and xarray and does not mention ITACA in any form, core or
  optional. The dependency is created in the migration commit, under
  the pin and Python-ceiling rules of
  [NFR-22](srs/nonfunctional-requirements.md).
* The removal release NUMBER is unset (stated by
  [NFR-06](srs/nonfunctional-requirements.md), its home of record;
  v0.5.0 shipped without the migration), and
  no deprecation cycle precedes it, because
  [NFR-20](srs/nonfunctional-requirements.md) governs from 1.0. Users
  of the far-field ledgers are affected as much as users of the tidy
  table, since xarray is in those public signatures; both find out on
  upgrade.

## The cross-requirement convention

Each library may generate requirements for the other:

* A need discovered here that belongs to generic data management is
  not solved here with a third dependency; it is recorded as a
  candidate requirement for ITACA, carrying a pyflightstream origin.
* An ITACA requirement may cite pyflightstream as its consumer, and
  this SRS may cite ITACA REQ ids where a requirement here depends on
  a capability there.
* How the pandas and xarray layers move to ITACA is governed by
  [AD-06](srs/architecture-srs.md), not restated here. Note that the
  convention this bullet used to describe, per-structure evolution
  gated on ITACA capabilities landing, is what the 2026-07-27 decision
  replaced with a single move.

## Shared process

Both repositories follow the same role-based review process (five
reviewer charters and the `role-review` skill; see the
[standards alignment](srs/standards.md) chapter) and the same
documentation-currency discipline, with the author holding the
non-delegable seats in both.
