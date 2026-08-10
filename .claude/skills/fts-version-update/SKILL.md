---
name: fts-version-update
description: Onboard a new FlightStream version into the command database, from manual ingestion to compat report. Use when a new FlightStream version or hotfix build is released.
side-effects: spends a licensed solver seat (tier 2 probe run) and appends a supported version to the append-only version list in commands/_meta.yaml (invariant 4: versions are only added, never dropped)
disable-model-invocation: true
---

# fts-version-update

Onboard a new FlightStream version end to end.

## Inputs

* New manual pdf placed in `_private/manual/` (never committed).
* The new version identifier in the canonical YY.XXX scheme.
* Optionally: vendor release notes (treat as incomplete; the database diff
  and the probe suite are the authority, not the changelog).

## Steps

1. Register the version in `src/pyflightstream/commands/_meta.yaml`:
   append to the ordered list (release order, append only) with its alias.
   A canonical identifier whose last digit is not zero must also state
   `inherits_base`, with the reason beside it: whether the build carries
   its base release's command evidence is a fact about the two vendor
   builds and not about the index. The registry refuses to load a hotfix
   index that leaves it unstated, and `FsVersion` refuses to be built one.
   26.121 inherits from 26.120 (a real hotfix, one manual re-issue apart);
   26.101 does not inherit from 26.100 (two vendor releases under one
   name, different manuals, different command sets).
2. **Capture the build's identity before anything else.** On the
   licensed machine, run
   `pyfs-qa probe --fs-version <v> --fs-exe <path> --identity-only`.
   It judges no command: it runs the baseline, reads the solver's own
   banner, and writes the report pair. Two registry fields are admitted
   ONLY from that report's `solver_identity` and never from a note or a
   download page: the vendor `build` number, and `prints`, the release
   name the binary states about itself. Those two are not the same fact
   as the alias, and for 26.120 and 26.121 they differ from it.

   Read the run itself as a measurement too. It is the first evidence
   that this package can drive the build at all, and the failure it most
   plausibly hides is silent: a build given a command-line spelling it
   does not know starts, checks out its licence, receives no script and
   waits (RPT-023). A clean licence checkout is not evidence the run
   reached the script.

3. **Add the build to the edition manifest and read what changed.**
   A row in the manifest (`--editions`) is what makes both multi-edition
   tools see the build. Then
   `pyfs-manual surface --editions <manifest> --names` reports what this
   build documents and what it gained and lost against its predecessor,
   and `pyfs-manual sweep --editions <manifest> --by-section` reports
   what no edition's entry covers. Reading the chapter by hand is the
   step these replace; what still needs a person is the judgement on
   each pair the surface diff turns up.

   Extract facts as paraphrase only: names, argument counts and types,
   layouts, page numbers. Never copy manual text.

4. Judge the diff: new commands, removed commands, changed signatures,
   and suspected renames. `surface` reports a rename as one loss and one
   gain and cannot tell you it is a rename.
5. Propose database edits with page citations, status `documented`.
6. Regenerate golden scripts for the new version.
7. On a licensed machine, run the Tier 2 probe suite
   (`pyfs-qa probe --fs-version <v>`); flag every manual-versus-reality
   discrepancy prominently: documented but broken, or working but changed
   without documentation.
8. Present a human-decision checklist for suspected renames. A rename is
   an engineering judgment; never decide it automatically.
9. Run Tier 1; update the docs compatibility matrix and the changelog.

## Outputs

* Database diff with citations, as a reviewable change.
* New golden scripts.
* Compat report under `reports/compat/`.
* Updated compatibility matrix in docs; decision checklist for the human.
