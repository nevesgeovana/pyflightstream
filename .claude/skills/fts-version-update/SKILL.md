---
name: fts-version-update
description: Onboard a new FlightStream version into the command database, from manual ingestion to compat report. Use when a new FlightStream version or hotfix build is released.
---

# fts-version-update

Onboard a new FlightStream version end to end.

## Inputs

* New manual pdf placed in `_private/manual/` (never committed).
* The new version identifier in the canonical 26.XXX scheme.
* Optionally: vendor release notes (treat as incomplete; the database diff
  and the probe suite are the authority, not the changelog).

## Steps

1. Register the version in `src/pyflightstream/commands/_meta.yaml`:
   append to the ordered list (release order, append only) with its alias.
2. Read the new manual's scripting reference and script index chapters.
   Extract the command surface as paraphrased facts only: names, argument
   counts and types, layouts, page numbers. Never copy manual text.
3. Diff that surface against the database: new commands, removed commands,
   changed signatures, and suspected renames (fuzzy name matching).
4. Propose database edits with page citations, status `documented`.
5. Regenerate golden scripts for the new version.
6. On a licensed machine, run the Tier 2 probe suite
   (`pyfs-qa probe --version <v>`); flag every manual-versus-reality
   discrepancy prominently: documented but broken, or working but changed
   without documentation.
7. Present a human-decision checklist for suspected renames. A rename is
   an engineering judgment; never decide it automatically.
8. Run Tier 1; update the docs compatibility matrix and the changelog.

## Outputs

* Database diff with citations, as a reviewable change.
* New golden scripts.
* Compat report under `reports/compat/`.
* Updated compatibility matrix in docs; decision checklist for the human.
