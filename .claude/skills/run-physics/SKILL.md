---
name: run-physics
description: Run the Tier 3 physics regression matrix and the cross-version drift suite, compare against stored references, and write the report. Requires a licensed machine.
# Side effect: consumes the licensed solver machine (tier 3). Never model-invoked.
disable-model-invocation: true
---

# run-physics

Run the physics regression evidence for one FlightStream version.

## Inputs

* Target version (26.XXX).
* The PHY case list (synthetic, committed) and, locally, the SMI
  version-comparison cases from `_private/geometry/smi/` (geometry never
  committed; reports carry aggregated coefficients only).

## Steps

1. Run the physics matrix: `pyfs-qa physics --version <v>`.
2. Compare each metric against its stored reference using the WARN and
   FAIL tolerance bands stored with the reference.
3. Triage every WARN and FAIL: physics change in the solver, database
   error, or stale reference.
4. Any reference update goes through the update tool, which demands a
   reason string; reference updates never share a commit with code
   changes.

## Outputs

* Physics report under `reports/physics/` with a pass/warn/fail table.
* Reference updates, each with its recorded reason, when justified.
