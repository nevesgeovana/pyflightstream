# RPT-001: M2 exit real local run (2026-07-21)

> **Version identifier renumbered, 2026-08-04, and this report is a CITING
> report rather than a relabelled one.** Its own run is on 26.120, vendor build 7012026, which the
> renumbering did not touch. What moved is a build it MENTIONS: vendor build
> 5012026 was called 26.100 when this was written and is called 26.101 since
> the author added the earlier February 2026 build, which takes the earlier
> index under the append-only ordering rule. Read any bare "26.100" below as
> 26.101 where it names build 5012026. Nothing measured here changed, and the
> report id keeps its original form because it is cited elsewhere.

Evidence for the second half of the M2 exit criterion (end-to-end dry
run plus one real local run, Bootstrap Kit milestone map). The dry run
is the Tier 1 suite; this report records the real run. Executables
live locally under `_private/exe/` and never enter Git; the geometry
is local research data referenced here by hash only, and this run is
pipeline validation, not a physics reference.

## Setup

| Item | Value |
|---|---|
| Executor | LocalExecutor, `-hidden --script` (SRC-003 pp.279-280) |
| Requested version | 26.120 (alias 26.12) |
| Reported by solver | version string "26.1", build #7012026 |
| License checkout | EDU feature, success |
| Geometry (local only) | sha256 71cad6f1b37bc2a9ac767415d16d4f2589c843e4059338c040abd4f2a235a857 |
| Case | one steady point, alpha 0 deg, periodic symmetry with 6 copies |
| Solver settings | 100 iterations requested, convergence limit 1.000E-05 |
| Recipe | curated helpers only (free stream, atmosphere, initialize, solver settings, analysis, exports); raw_flag false |

## Result

| Item | Value |
|---|---|
| Manifest status | CONVERGED |
| Iterations | 86 of 100 requested |
| Final residual | 1.81E-06 (velocity/pressure maximum, from the exported log) |
| Wall time | 5.3 s |
| Outputs collected | raw/loads.txt, raw/log.txt |

Aggregated Total coefficients (coefficient units, analysis frame),
recorded per the invariant that committed reports carry aggregated
coefficients only:

| Cx | Cy | Cz | CL | CDi | CDo | CMx | CMy | CMz |
|---|---|---|---|---|---|---|---|---|
| +0.0190 | +0.0000 | -0.0000 | -0.0000 | +0.0162 | +0.0027 | +0.0369 | -0.0000 | -0.0000 |

The condition is an unpowered steady free stream on a rotor
configuration, so the values are only pipeline evidence.

## Findings feeding the database and parsers

1. Version reporting (FR-18): both installed builds print the version
   string "26.1"; the build number is the discriminator. Observed
   mapping: 26.101 prints build #5012026, 26.120 prints build
   #7012026 (headless smoke on both executables, PRINT plus
   EXPORT_LOG scripts, return code 0).
2. Hidden-mode exported logs carry stray NUL bytes between lines;
   `parse_residual_history` scrubs them (fix and test in this
   change). Before the fix, the campaign honestly recorded the point
   as FAILED_INCOMPLETE_OUTPUT instead of guessing, which is the
   designed behavior.
3. The steady loads export prints coefficients with 4 decimals,
   against 7 in the unsteady export used for the fixtures; the
   anchor-based parser is unaffected.
