---
name: run-physics
description: Run the Tier 3 physics regression matrix and the cross-version drift suite, compare against stored references, and write the report. Requires a licensed machine.
side-effects: consumes the licensed solver machine (tier 3 physics regression run), a scarce seat the author schedules
---

# run-physics

Run the physics regression evidence for one FlightStream version.

## Inputs

* Target version (YY.XXX).
* The PHY case list (synthetic, committed) and, locally, the SMI
  version-comparison cases from `_private/geometry/smi/` (geometry never
  committed; reports carry aggregated coefficients only).

## Steps

0. **Ask a replacement executable its identity before this run spends a
   seat.** Applies whenever the binary behind `--fs-exe` is not the one
   the evidence for this version was gathered on: a relicensed install,
   a reinstall, a vendor re-delivery. It is NOT the new-version case,
   which `fts-version-update` covers; here the version is already
   registered and only the file changed.

   Hash it first, which costs nothing and starts no process:
   `pyflightstream.qa.compat.classify_executable` compares the digest
   against the baseline in
   `reports/RPT-032_executable-identity-baseline_2026-08-19.md`.

   * digest recorded for this version: it is the same binary, the
     references and their bands still describe it, and this run
     proceeds;
   * digest unknown: run `pyfs-qa probe --fs-version <v> --fs-exe <path>
     --identity-only` and NOTHING else. Compare the build number it
     prints with the registry's. Equal, and the evidence transfers, with
     both digests recorded. Different, and it is a different build: stop,
     and report both numbers. A physics run against a build whose
     identity nobody checked writes a report that names the wrong solver.

1. Run the physics matrix: `pyfs-qa physics --fs-version <v>`.
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
