# v0.20.1 is released by this sequence, followed as written

**THE OWNER ASKED FOR THIS RELEASE AS A BUG FIX** on 2026-09-15: the
`unsteady_rotor` workflow runs on 26.100, which 0.20.0 refused. The tag is cut
when the sequence below reaches step 2 with the gate green.

0.20.1 is one fix: a rotor row on 26.100 is written as a Euclidean motion with
no rotor mark and its speed in rev/min, by the maintainer's decision and not by
a measurement (RPT-051).

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.20.1.dev0 until this step, deliberately: a tree that
#    already said 0.20.1 would have every run made from it reporting the
#    released version while being a different tree. The [0.20.1] section is
#    dated 2026-09-15; if the tag is cut on another day, correct that date
#    here, because it is the one line of the section that stops being true by
#    waiting.
#    (pyproject.toml: version = "0.20.1")
#
#    AND BOTH FRONT PAGES NAME THE NEW VERSION: the status line of README.md,
#    which is the PyPI project page, and of docs/index.md. Missed at the v0.18.1
#    release commit and caught by CI before the tag, by test_claim_currency.
#
#    AND CITATION.cff MOVES IN THE SAME COMMIT, all three fields together:
#    version, date-released, and the header paragraph that says whether this
#    is a DEVELOPMENT or a RELEASE tree, with its tally. The tally has TWO
#    sentences that count, and the 0.20.0.dev0 bump moved one and not the
#    other; read both.
#
#    AND THE CHANGE LOG'S Owed SECTION NAMES THE NEW TAG. Its absence cost the
#    v0.18.0 publish: the gates run against the TAGGED tree, where the version
#    has no archive row yet, and only an Owed line naming the tag lets
#    `test_every_released_tag_has_an_archive_row_or_the_changelog_says_it_is_owed`
#    pass there. It cannot be added afterwards; it must be in the commit the tag
#    names.
git commit -m "chore: v0.20.1"

# 2. the tag, annotated, on that commit, once CI is green on it
git tag -a v0.20.1 -m "v0.20.1"

# 3. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.20.1

# 4. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.20.1 --title "v0.20.1" --notes-file <the section body and its limitations>

# 5. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 4,
#    not on the tag of step 3. Read the new version DOI off the Zenodo record.

# 6. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 5, and the Owed line for
#    v0.20.1 leaves the change log in the same commit.
git commit -m "chore: the v0.20.1 archive row"

# 7. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 4 WAS MISSED AT v0.17.0** and the release was archived nowhere for a day;
**THE OWED LINE OF STEP 1 WAS MISSING AT v0.18.0** and its publish was skipped
until a follow-up commit and a second tag run; **THE FRONT PAGES WERE MISSED AT
THE v0.18.1 RELEASE COMMIT** and CI caught them before the tag. Each is written
into the sequence rather than remembered, because a fast release is exactly when
a step gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive
has minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number below comes from a command run at the moment this file was
written, and the command and the tree it read are beside it. The release commit
after a5ef1ae changes no executable code (it sets versions and prose), so a
reading taken on the code of a5ef1ae is a reading of the code this tag carries.

| what | command | reading |
|---|---|---|
| the tier-1 suite | `python -m pytest tests/tier1_offline` (eight slices) | 4243 passed, 6 skipped, on the code of a5ef1ae |
| the type checker | `python -m mypy src/pyflightstream tests/tier3_licensed/rotation_null.py` | Success, no issues in 86 source files, on the code of a5ef1ae |
| the linter | `python -m ruff check src tests scripts tools` | All checks passed, on the code of a5ef1ae |
| the tier-3 suite | `python -m pytest -m needs_flightstream tests/tier3_licensed` | not run for this release; no solver run has used the 26.100 rotor motion (RPT-051) |
| the review | five lenses over 5cad0ba..91a597f | one round, 22 findings, no behaviour defect; fixed in a5ef1ae, TW-1 by this file |

## What this release carries

The change log's `[0.20.1]` section is the record, its Limits first, and is not
restated here. In one line:

- **a rotor row renders on 26.100**, as a Euclidean motion without the rotor
  mark, its speed in rev/min, with a comment in the script saying so (RPT-051).

## What is NOT done, and is not being hidden

- **Three cells of the support matrix are refused**: every run type on 25.000.
  Whether to fill them is the owner's.
- **The 26.100 rotor's unit, its sense of rotation, whether the unmarked motion
  turns the blade at all, and what the missing mark changes are not measured.**
  RPT-051 describes the run that settles the first three.
- **Every limit the change log's `[0.20.0]` section lists still holds**, apart
  from the 26.100 rotor cell this release fills.
- **v0.14.0 is still not archived**, carried in the change log's Owed section.
