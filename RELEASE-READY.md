# pyflightstream 0.34.0 is released by this sequence, followed as written

0.34.0 is THE RELEASE OF WHAT SHE USES: the wake length in rotor radii and the Trefftz
plane, the run-usability items, the thin-blade command, the actuator disc's swirl sign,
CCS and noise, FSI, LF in every text product, the cheatsheet as guide 04 with the guides
numbered from 01, and only the three cuts these need (the `cases` root, `script.helpers`,
`run.cli`). The change log's `[0.34.0]` section is the record;
`docs/migrating-to-0.34.0.md` says what a reader's files must change.

The version this file describes is the package's version without a development
suffix (`pyproject.toml`), and a test reads it (FR-346). The commands of the
sequence below were written for that version: the next release reads its own
version in their place and re-titles this file at step 1, in the same commit as any change of the version in `pyproject.toml` (the test compares the two, so a bump without the re-title fails it).

**THIS FILE IS RE-TITLED AND RE-MEASURED PER TAG.** It carried the v0.22.0 title,
commands and readings through the whole 0.23.0 release, and it carried the v0.24.0
title and readings up to the eve of v0.25.0, where the INDEPENDENT REVIEW OF GitHub
main caught it (finding 6, 2026-09-20): a reader following it would have tagged the
previous release. Whether it is re-titled each time or split into a version-free
sequence plus a per-release readings file is still the owner's call; until she
rules, it is re-titled. The v0.32.0 edition is in the history of this file
(`git show v0.32.0:RELEASE-READY.md`).

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.33.1.devN (the development tree) until this step, deliberately: a tree that
#    already said 0.33.1 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.33.1")
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
git commit -m "chore: v0.33.1"

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
git tag -a v0.33.1 -m "v0.33.1"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.33.1

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.33.1 --title "v0.33.1" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.33.1 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.33.1 archive row"

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
MISSED AFTER v0.21.1**, **AND AGAIN AFTER v0.30.0** (the archive row's commit,
51cc4a82, left the tree at 0.30.0, so `test_guide_decks` reads the 0.31.0 decks
against a tree that says it releases 0.30.0 until step 1); **THE INDEPENDENT
REVIEW WAS SKIPPED FROM v0.18.0 TO
v0.22.0**; **THIS FILE ITSELF WAS STILL RELEASING v0.24.0 ON THE EVE OF v0.25.0**.
Each is written into the sequence rather than remembered, because a fast release
is exactly when a step gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive has
minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number comes from a command run at the moment this file was written, with
the command beside it. A reading of an earlier commit is evidence only for that
commit, and no count of 0.31.0 is reused here.

The release-cut commit sets the version (`pyproject.toml` 0.33.1), dates the
change log's `[0.33.1]` section 2026-10-01, moves `CITATION.cff` to 0.33.1 with
its `date-released`, names v0.33.1 on both front pages and keeps the guide's
cover at 0.33.1. Its tests are recorded with that commit.

PENDING, and not claimed by this file until its evidence is attached to the
commit it names:

- **The full tier-1 suite over the release commit.**
- **The review attestation over the release range** (step 2) and **the
  independent reading of GitHub main** on the pushed commit (step 4).
- **CI green on the commit to be tagged**, including the release workflow's single
  build and its clean installed-wheel jobs.
- **The tag, its PyPI publication, the release object and the Zenodo version
  DOI** (steps 5 to 10). The version DOI of v0.33.1 enters `CITATION.cff` once
  Zenodo mints it; the archive of the releases is named by the concept DOI that
  `CITATION.cff` carries, 10.5281/zenodo.21482924, which resolves to the newest
  archived version.
