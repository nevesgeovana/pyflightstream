# v0.24.0 is released by this sequence, followed as written

0.24.0 changes numbers that 0.23.0 published, changes the header of almost every
table the post stage writes, and asks one new thing of a matrix row. It is a MINOR
bump for that reason. `docs/migrating-to-0.24.0.md` is the reader's account; the
change log's `[0.24.0]` section is the record.

**THIS FILE IS RE-TITLED AND RE-MEASURED PER TAG.** It carried the v0.22.0 title,
commands and readings through the whole 0.23.0 release, which is the reuse TW-F7 of
FIX-0211 registered and the second time it happened. Whether it is re-titled each
time or split into a version-free sequence plus a per-release readings file is
still the owner's call; until she rules, it is re-titled, and the lapse is recorded
here rather than repeated silently.

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.24.0.dev0 until this step, deliberately: a tree that
#    already said 0.24.0 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.24.0")
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
#    and CHANGELOG.md. test_traceability re-counts the package on every run.
#
#    AND THE CHANGE LOG'S Owed SECTION SAYS THE NEW TAG'S ROW IS *OWED*. The
#    guard asks each BULLET for three things: the tag, an archive word, and a DEBT
#    word (`owed`, `owe`, `not exist`, `missing`). Write the word. Do not explain
#    the rule inside the bullet: a footnote mentioning `owed` satisfies the guard
#    on its own.
git commit -m "chore: v0.24.0"

# 2. THE INTERNAL REVIEW ROUND over the release range, every finding fixed or
#    registered, recorded in the lane's rounds ledger.

# 3. merge to main and PUSH main. No tag yet.
git push origin main

# 4. THE INDEPENDENT REVIEW, OF GitHub main, AFTER THE PUSH AND BEFORE THE TAG.
#    A FIXED STEP SINCE 0.24.0, not a reminder. A second reader, given the
#    repository as GitHub serves it and nothing from the session that wrote it,
#    looks for defects. Every finding is FIXED (and pushed, and the review re-read
#    on the new main) or REGISTERED with its reason, and the record names the
#    commit of main it read and says it ran before the tag.
#
#    WHY IT IS A STEP. The gate was created on 2026-09-12 and only 0.17.0 and
#    0.23.0 carry its record; 0.18.0 to 0.22.0 carry none. Both times it ran it
#    found defects no internal round had: at 0.23.0, seven of the first severity
#    after four internal rounds and ninety-two internal findings.

# 5. the tag, annotated, on the reviewed commit, once CI is green on it
git tag -a v0.24.0 -m "v0.24.0"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.24.0

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.24.0 --title "v0.24.0" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.24.0 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.24.0 archive row"

# 10. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 7 WAS MISSED AT v0.17.0** and the release was archived nowhere for a day;
**THE OWED LINE OF STEP 1 WAS MISSING AT v0.18.0** and its publish was skipped;
**IT WAS PRESENT BUT WORDLESS AT v0.21.0** and the publish was skipped again;
**THE FRONT PAGES WERE MISSED AT v0.18.1** and CI caught them before the tag;
**THE POST-TAG DEV BUMP WAS MISSED AFTER v0.21.1**; **THE INDEPENDENT REVIEW WAS
SKIPPED FROM v0.18.0 TO v0.22.0**. Each is written into the sequence rather than
remembered, because a fast release is exactly when a step gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive has
minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number comes from a command run at the moment this file was written, with
the command beside it.

Readings of 2026-09-19, each status read from the process:

- `ruff check .` exit 0; `ruff format --check .` exit 0; `mypy` exit 0, "Success: no issues
  found in 93 source files".
- The full tier-1 suite, detached, at 056067e: 4974 passed, 6 skipped, exit 0; re-run on
  the release commit before the tag.
- The executable examples (`src/pyflightstream README.md docs`, warnings as errors): 381
  passed.
- `python -m tests.tier3_licensed.offline`: every matrix 0 differing, 0 orphan.
- mypy recount 2026-09-19: 661 errors in 18 of 93 modules (reports/RPT-029).
- Review: round 1 (five lenses, 52 findings) and round 2 (five codex lenses, 15 findings),
  REL-0240_rounds.ledger VERIFIED, 2 rounds, 67 findings; three independent codex passes
  (numbers, unsteady reductions, inputs and infrastructure) before round 2.

## What this release carries

The change log's `[0.24.0]` section is the record, and `docs/migrating-to-0.24.0.md`
says what a reader of existing files must know. In one line each:

- **Numbers that change:** `ETAW` and the shaft angle wherever alpha or beta is not
  zero (two wrong signs in the free-stream vector of 0.23.0); `CLS`, `CLW`, `CDB`
  and `CLB` of every steady polar, now built from the export's own vector; the
  rotor table of an unsteady point, which held the last time step and now holds
  the window average.
- **One new thing a row must say:** an unsteady row states its averaging window.
- **One header migration, once:** the condition block with the air and the
  reference velocity; the unsteady polar as `P<sim>_<name>_uns_avg.csv` with its
  window, its axes and the super content; sections, series, reductions, per-blade
  and rotor tables that say which step, surface, rotor, blade and window a row is.
- **Axes under sideslip**, in one module checked against scipy and against the
  recorded exports.
- **New, optional, in the pproc:** `[phase_locked]`, `[equations]`, `[glossary]`,
  `[names]`, the fixed-width super file, two generated guides.
- **The cluster path:** collect, the run records and the manifest as a transaction.

## What the licensed campaign measured, and what it did not

The licensed campaign `pfs0240` (FlightStream 26.124; a steady wing under sideslip, the
owner's periodic rotor sector, her full wheel at alpha 0 and 10) is committed under
`reports/pfs0240/`: six of seven coherence checks hold, re-measured from the raw exports
with the standard library. The seventh, the sector against the full wheel, reads 1.297
because the full wheel used a nacelle that is not axisymmetric; the owner named the right
geometry (`17_NX_B30_NMIN_FW.fsm`) and decided the release is not held for its run.

## What is NOT done, and is not being hidden

- The full-wheel run on `17_NX_B30_NMIN_FW.fsm` is owed, after this release, by the owner's
  decision; until it runs, GOAL-028's campaign arm reads NOT YET.
- The manifest lock treats a lock older than 30 s as abandoned (codex review I01): a
  recovery policy that holds across cluster hosts is owed to 0.25.0.
- Registered for 0.25.0 in REL-0240_rounds.ledger: ARCH-A1, ARCH-A5, API-B6, TW-F4b,
  TW-F6, QA-Q4, SES-05 to SES-08, VV-V4, VV-V5, R2-TW-4, and the per-blade window of a
  legacy record (codex U01, second half).
- The Zenodo version DOI of v0.24.0 is owed one commit after the tag.
