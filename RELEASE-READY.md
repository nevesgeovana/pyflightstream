# v0.29.0 is released by this sequence, followed as written

0.29.0 is the release of COMPLETE SETUP AND BOUNDARY-CONDITION ACCESS: didactic
standard setups and their physical guidelines written by `pyfs-matrix plan`, and
`pyfs-matrix inspect-setups` showing what a setup resolves to; inlets, outlets,
trailing edges, wakes and base regions as typed setup entries; workspace FSI
inputs staged from named files with their calibration; velocity fields and
volume sections sampled through probes; an optional macro-free Excel workbook
synchronized with the matrix by the Python CLI; and execution and post logs that
say their stage and outcome. It carries a QUALITY GATE: before the tag, every
refusal the development work had turned into an acceptance was restored, or kept
only on a recorded owner decision. IT CHANGES WHAT A READER DOES in three ways: a
steady sweep starts every point cold by default, `[volume_section]` is sampled
rather than natively exported, and `ROTOR_SHEDDING` is refused. The change log's
`[0.29.0]` section is the record; `docs/migrating-to-0.29.0.md` says what a
reader's files must change.

The ownership of inputs is part of the contract: mesh-invariant geometry beside
the mesh, simulation settings in the setup, variable physical conditions in
MATRIX. Excel uses a macro-free workbook and CLI synchronization; VBA is outside
this release. The normal volume-section path uses probes; an automatic inventory
of manual native section indices is outside it.

**THIS FILE IS RE-TITLED AND RE-MEASURED PER TAG.** It carried the v0.22.0 title,
commands and readings through the whole 0.23.0 release, and it carried the v0.24.0
title and readings up to the eve of v0.25.0, where the INDEPENDENT REVIEW OF GitHub
main caught it (finding 6, 2026-09-20): a reader following it would have tagged the
previous release. Whether it is re-titled each time or split into a version-free
sequence plus a per-release readings file is still the owner's call; until she
rules, it is re-titled. The v0.28.0 edition is in the history of this file
(`git show ad237d2b:RELEASE-READY.md`).

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.29.0.dev0 (the development tree) until this step, deliberately: a tree that
#    already said 0.29.0 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.29.0")
#
#    AND BOTH FRONT PAGES NAME THE NEW VERSION: the status line of README.md,
#    which is the PyPI project page, and of docs/index.md.
#
#    AND THE GUIDE'S COVER: guide/pyflightstream_user_guide.tex carries the
#    version in \institute, and test_guide_currency compares it to pyproject.
#
#    AND CITATION.cff MOVES IN THE SAME COMMIT, all three fields together:
#    version, date-released, and the header paragraph that says whether this is a
#    DEVELOPMENT or a RELEASE tree, with its tally. The tally has TWO sentences
#    that count; read both.
#
#    AND THE MODULE RE-COUNT: `python scripts/mypy_recount.py` ON A SETTLED TREE
#    (it says so itself when the tree is not), and its sentence goes, identical,
#    into reports/RPT-029, pyproject.toml, tests/tier1_offline/test_traceability.py
#    and CHANGELOG.md. test_traceability re-counts the package on every run. THE
#    RECOUNT BELONGS TO THE RELEASE THAT MEASURED IT: writing this release's
#    reading into the previous release's section gives a reader comparing two
#    releases a false delta (the release-tail review, 2026-09-20).
#
#    AND THE CHANGE LOG'S Owed SECTION SAYS THE NEW TAG'S ROW IS *OWED*. The
#    guard asks each BULLET for three things: the tag, an archive word, and a DEBT
#    word (`owed`, `owe`, `not exist`, `missing`). Write the word. Do not explain
#    the rule inside the bullet: a footnote mentioning `owed` satisfies the guard
#    on its own. IT GOES UNDER [Unreleased] -> Owed, not under the dated section:
#    under the dated section the tag fails its own archive gate.
git commit -m "chore: v0.29.0"

# 2. THE INTERNAL REVIEW ROUND over the release range, every finding fixed or
#    registered, recorded in the lane's rounds ledger.

# 3. merge to main and PUSH main. No tag yet.
git push origin main
#    THE PUSH GATE READS THE ATTESTATION OF THE PUSHING WORKTREE, not of the main
#    checkout, and a pass scope must be `name@<sha>..<sha>`: a tag name on the left
#    does not resolve, and ONE scope is kept per pass name, so two review rounds
#    under one name overwrite each other. Give each lens the union range it read.

# 4. THE INDEPENDENT REVIEW, OF GitHub main, AFTER THE PUSH AND BEFORE THE TAG.
#    A FIXED STEP SINCE 0.24.0, not a reminder. A second reader, given the
#    repository as GitHub serves it and nothing from the session that wrote it,
#    looks for defects. Every finding is FIXED (and pushed, and the review re-read
#    on the new main) or REGISTERED with its reason, and the record names the
#    commit of main it read and says it ran before the tag.
#
#    GIVE THE READER THE CLONE. A read-only pass cannot clone the repository
#    itself, and a directory that is not a repository is refused outright; make
#    the clone first and point the pass at it (2026-09-20).
#
#    WHY IT IS A STEP. The gate was created on 2026-09-12; 0.17.0, 0.23.0 and
#    every release from 0.24.0 carry its record. Every time it has run it found
#    defects no internal round had: at 0.23.0, seven of the first severity after
#    four internal rounds and ninety-two internal findings; at 0.25.0, six after
#    two rounds and thirty-one findings, three of them behaviour.

# 5. the tag, annotated, on the reviewed commit, once CI is green on it
git tag -a v0.29.0 -m "v0.29.0"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.29.0

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.29.0 --title "v0.29.0" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.29.0 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.29.0 archive row"

# 10. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 7 WAS MISSED AT v0.17.0** and the release was archived nowhere for a day;
**THE OWED LINE OF STEP 1 WAS MISSING AT v0.18.0** and its publish was skipped;
**IT WAS PRESENT BUT WORDLESS AT v0.21.0** and the publish was skipped again;
**IT WAS IN THE WRONG SECTION AT v0.25.0** and the release-tail review caught it
before the tag; **AN UNRELEASED SECTION DESCRIBED BEHAVIOUR THE TAG WOULD SHIP AT
v0.25.1**, caught by the version-identity guard, because a patch cut from the
development tree carries what that tree already changed; **THE FRONT PAGES WERE
MISSED AT v0.18.1** and CI caught them before the tag; **THE POST-TAG DEV BUMP WAS
MISSED AFTER v0.21.1**; **THE INDEPENDENT REVIEW WAS SKIPPED FROM v0.18.0 TO
v0.22.0**; **THIS FILE ITSELF WAS STILL RELEASING v0.24.0 ON THE EVE OF v0.25.0**.
Each is written into the sequence rather than remembered, because a fast release
is exactly when a step gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive has
minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number comes from a command run at the moment this file was written, with
the command beside it. A reading of an earlier commit is evidence only for that
commit, and no count of 0.28.0 is reused here.

Readings of 2026-09-28, on the tree of the release commit, each status read from
the process:

- `ruff check .` exit 0, "All checks passed!"; `ruff format --check .` exit 0,
  "572 files already formatted".
- `python scripts/mypy_recount.py`, on a tree the script reported clean: 922 errors
  in 18 of 128 modules, against 0.28.0's 863 in 18 of 104 (reports/RPT-029); the
  shipped configuration's invocation in the same run, "Success: no issues found in
  128 source files".
- The test files that read the change log, the citation, the front pages and the
  house rules were run over the release commit (`test_g47_input_template.py`,
  `test_version_identity.py`, `test_metadata_currency.py`,
  `test_citation_claim_currency.py`, `test_claim_currency.py`,
  `test_traceability.py`, `test_house_style.py`, `test_repository_guards.py`,
  `test_goal031_d07_pages.py`); their results are recorded with that commit.

PENDING, and not claimed by this file until its evidence is attached to the
commit it names:

- **The full tier-1 suite over the release commit.** Runs over earlier commits of
  this release do not stand in for it.
- **The review attestation over the release range** (step 2) and **the
  independent reading of GitHub main** on the pushed commit (step 4).
- **CI green on the commit to be tagged**, including the release workflow's single
  build and its clean installed-wheel jobs.
- **The tag, its PyPI publication, the release object and the Zenodo version
  DOI** (steps 5 to 10). The v0.29.0 archive row is owed in the change log.
- **The approved research against the released wheel**, using the generated
  standard setups and including the FSI workspace cases. It follows the release
  and is not closed by it.

## What this release carries

In one line each:

- **Setups.** A library of standard setups and their physical guidelines
  (`--setup-standards`, `--setup-guidelines`), and `inspect-setups` reporting each
  resolved value, its origin, its boundary selections and its raw commands.
- **Boundaries.** Typed inlet and outlet ports, trailing-edge, wake and base
  selectors, initialization removal and transition-trip deletion as setup entries;
  port creation with unknown saved indices is refused.
- **Workspace FSI.** Named FSI input files with complete distributions or solid
  homogeneous sections from one sourced material, matrix calibration factors
  applied once, staged with their hashes.
- **Probe-based post-processing.** Sampled velocity fields and volume sections
  written by the package with their provenance; section-integral boundary-layer
  tables from the VTK cells; nodal strength beside the VTK surface fields.
- **Excel.** A macro-free `.xlsx` synchronized with the matrix by explicit
  preview, apply and cancel commands; no Excel process is required.
- **Logs and runs.** Execution and post logs that say their stage and outcome;
  submitted additional-post extractions completed by `collect`; continuation
  checked against its recorded inputs.

## What the licensed campaign measured, and what it did not

[RPT-085](reports/RPT-085_native-workspace-evidence_2026-09-27.md) records bounded
native observations on FlightStream 26.124: the synthetic wing and rotor routes
agree over six printed time steps, which is not convergence, a full revolution or
complete saved-state equivalence; an existing native section and surface mesh
survive probe sampling, with the CSV's five-decimal limit; uniform inlet and
outlet changes produce a local response; two steady actuators and a supplemental
actuator with rotating geometry produce local field effects, which is not
rotor-performance validation. [RPT-081](reports/RPT-081_typed-boundary-and-base-region-operations_2026-09-27.md)
keeps the earlier no-solve observations, and RPT-082 to RPT-084 the unit, inflow,
probe-frame and Excel readings. These observations do not turn a
documented-only command into a verified one.

## What is NOT done, and is not being hidden

- Profile interpolation at an inlet and its sign convention are not proved (T15);
  the rotor-induced velocity blending pair is inconclusive.
- Manual native section indices stay manual; the velocity-profile export is a
  named refusal on a build without positive unattended-profile evidence.
- `ROTOR_SHEDDING` is refused; direction control for the relaxed wake is planned
  for 0.30.0.
- The workspace FSI wiring stages the existing driver; it does not establish
  native coupled accuracy.
- VBA in the workbook is outside this release; an existing `.xlsm` is not
  converted silently.
- The Zenodo version DOI of v0.29.0 is owed one commit after the tag.
