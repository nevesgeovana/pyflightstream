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
| The adapter between the two | pyflightstream, behind a future optional `[itaca]` extra |

ITACA is solver-agnostic by requirement and never imports
pyflightstream; pyflightstream's exporter will map the run manifest,
the solver-setup provenance snapshot, and the parsed result tables
into ITACA datasets, so a campaign's outputs arrive in the data layer
with their provenance already attached.

## The cross-requirement convention

Each library may generate requirements for the other:

* A need discovered here that belongs to generic data management is
  not solved here with a third dependency; it is recorded as a
  candidate requirement for ITACA, carrying a pyflightstream origin.
* An ITACA requirement may cite pyflightstream as its consumer, and
  this SRS may cite ITACA REQ ids where a requirement here depends on
  a capability there.
* How the pandas and xarray layers evolve toward ITACA is governed by
  [AD-07](srs/architecture-srs.md), not restated here.

## Shared process

Both repositories follow the same role-based review process (five
reviewer charters and the `role-review` skill; see the
[standards alignment](srs/standards.md) chapter) and the same
documentation-currency discipline, with the author holding the
non-delegable seats in both.
