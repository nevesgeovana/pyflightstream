# v0.25.0 is released by this sequence, followed as written

0.25.0 changes what the post stage writes for a probe, a section and a surface, adds
features the owner decided, and refuses one solver command that hangs the build this
release could measure. It is a MINOR bump for that reason.
`docs/migrating-to-0.25.0.md` is the reader's account; the change log's `[0.25.0]`
section is the record.

**THIS FILE IS RE-TITLED AND RE-MEASURED PER TAG.** It carried the v0.22.0 title,
commands and readings through the whole 0.23.0 release, and it carried the v0.24.0
title and readings up to the eve of this tag, where the INDEPENDENT REVIEW OF GitHub
main caught it (finding 6, 2026-09-20): a reader following it would have tagged the
previous release. That is the third instance of the same lapse, TW-F7 of FIX-0211
being the first. Whether it is re-titled each time or split into a version-free
sequence plus a per-release readings file is still the owner's call; until she rules,
it is re-titled, and the lapse is recorded here rather than repeated silently.

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.25.0.dev0 until this step, deliberately: a tree that
#    already said 0.25.0 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.25.0")
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
git commit -m "chore: v0.25.0"

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
#    WHY IT IS A STEP. The gate was created on 2026-09-12 and only 0.17.0, 0.23.0,
#    0.24.0 and this release carry its record. Every time it has run it found
#    defects no internal round had: at 0.23.0, seven of the first severity after
#    four internal rounds and ninety-two internal findings; at 0.25.0, six after
#    two rounds and thirty-one findings, three of them behaviour.

# 5. the tag, annotated, on the reviewed commit, once CI is green on it
git tag -a v0.25.0 -m "v0.25.0"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.25.0

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.25.0 --title "v0.25.0" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.25.0 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.25.0 archive row"

# 10. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 7 WAS MISSED AT v0.17.0** and the release was archived nowhere for a day;
**THE OWED LINE OF STEP 1 WAS MISSING AT v0.18.0** and its publish was skipped;
**IT WAS PRESENT BUT WORDLESS AT v0.21.0** and the publish was skipped again;
**IT WAS IN THE WRONG SECTION AT v0.25.0** and the release-tail review caught it
before the tag; **THE FRONT PAGES WERE MISSED AT v0.18.1** and CI caught them
before the tag; **THE POST-TAG DEV BUMP WAS MISSED AFTER v0.21.1**; **THE
INDEPENDENT REVIEW WAS SKIPPED FROM v0.18.0 TO v0.22.0**; **THIS FILE ITSELF WAS
STILL RELEASING v0.24.0 ON THE EVE OF v0.25.0**. Each is written into the sequence
rather than remembered, because a fast release is exactly when a step gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive has
minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number comes from a command run at the moment this file was written, with
the command beside it.

Readings of 2026-09-20, each status read from the process:

- `ruff check .` exit 0; `ruff format --check .` exit 0; `mypy` exit 0, "Success: no issues
  found in 97 source files".
- The full tier-1 suite, detached, one process per file, on the tree carrying the
  independent review's fixes: exit 0, 0 red files.
- The executable examples, using CONTRIBUTING.md's command with package warnings
  promoted to errors: 383 passed, exit 0.
- `python -m tests.tier3_licensed.offline`: every matrix 0 differing, 0 orphan, exit 0.
- mypy recount 2026-09-20: 713 errors in 18 of 97 modules (reports/RPT-029).
- Review: round 1 and round 2 as codex lens passes, REL-0250_rounds.ledger VERIFIED,
  2 rounds, 31 findings; a release-tail review over the release commits (5 findings, all
  fixed); and THE INDEPENDENT REVIEW OF GitHub main at 7fddf7b (6 findings: three
  behaviour, three documentation and release chore; all fixed, recorded in
  `REL-0250_independent-review.json`).

## What this release carries

The change log's `[0.25.0]` section is the record, and `docs/migrating-to-0.25.0.md`
says what a reader of existing files must know. In one line each:

- **A refusal that protects a run:** a pproc carrying `[time_averaging]` is refused at
  PLAN on any build where `SOLVER_TIME_AVERAGING` is not recorded verified, which is
  every build today, because the licensed verification measured it HANGING 26.124.
- **The probe source follows the run type:** an unsteady row samples every `[[probes]]`
  entry through fluid plots, and its table is the plots history.
- **One sections file and one cp file per distribution**, named for the alias or the
  concatenated families, for every exported step when per-step export is on.
- **Surface flow in VTK and CSV**, off by default, validated against the build's
  command database.
- **Fourteen advanced solver settings** have a setup key of their own.
- **`post` reads a simulation recorded with 0.24.0**, whose records carry none of the
  new fields.
- **Structure without behaviour change:** one phase-locked policy, one MRP reader, two
  ledger deprecations, and `post/products.py` split into `provenance` and
  `custom_polar`.

## What the licensed campaign measured, and what it did not

The licensed campaign of this release is the C01 verification under `reports/pfs0250/`.
On FlightStream 26.124, with receipts carrying the executable's digest: the script the
package writes, WITHOUT `SOLVER_TIME_AVERAGING`, exited 0 in 133.0 seconds with all seven
outputs and its final log export; WITH that one line, in the position the package emits
it, nothing was written and the solver was killed at 240.5 seconds. An earlier run with
the line moved after `INITIALIZE_SOLVER` hung the same way and predates the receipts, so
it is recorded as an observation.

WHAT IT DID NOT MEASURE: whether the command's bounds are time steps or inner iterations.
The command hangs the one build this release could run it on, so the conversion the
package performs is unverified, the database says so, and the conversion is a single
function for the day a build settles it.

`pfs0240`'s coherence evidence stays committed under `reports/pfs0240/` and is unchanged
by this release.

## What is NOT done, and is not being hidden

- The full-wheel runs are recorded in `reports/pfs0240/README.md`, with all eight
  coherence checks passing. They are no longer outstanding release work.
- `SOLVER_TIME_AVERAGING` is measured broken on 26.124 and unverified on the other
  builds. No build currently satisfies the workflow's verification requirement,
  so the averaging feature is refused on every selectable build.
- The items registered for 0.26.0 in REL-0250_rounds.ledger, with their reasons.
- The owner's open questions of this release are registered in the ledger and are
  summarised to her after the goal's checker proves, per her mandate of 2026-09-19.
- The Zenodo version DOI of v0.25.0 is owed one commit after the tag.
