# v0.18.1 is released by this sequence, followed as written

**THE OWNING SEAT SET THIS RELEASE AS A GOAL** (GOAL-021, item 6: release it,
following this file as written). So unlike v0.18.0, whose tag waited on her
word, the tag is cut when the sequence below reaches step 2 with the gate green.

A patch is only for a bug found after the release ships, and every item of
0.18.1 was found on 2026-09-14, the day v0.18.0 shipped. The diff being small is
the reason the sequence is cheap, not a reason to shorten it.

## The sequence, in order, and the two steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.18.1.dev0 until this step, deliberately: a tree that
#    already said 0.18.1 would have every run made from it reporting the
#    released version while being a different tree. The [0.18.1] section is
#    dated 2026-09-14; if the tag is cut on another day, correct that date
#    here, because it is the one line of the section that stops being true by
#    waiting.
#    (pyproject.toml: version = "0.18.1")
#
#    AND BOTH FRONT PAGES NAME THE NEW VERSION: the status line of README.md,
#    which is the PyPI project page, and of docs/index.md. Missed at the v0.18.1
#    release commit and caught by CI before the tag, by test_claim_currency.
#
#    AND CITATION.cff MOVES IN THE SAME COMMIT, all three fields together:
#    version, date-released, and the header paragraph that says whether this
#    is a DEVELOPMENT or a RELEASE tree, with its tally.
#
#    AND THE CHANGE LOG'S Owed SECTION NAMES THE NEW TAG. Its absence cost the
#    v0.18.0 publish: the gates run against the TAGGED tree, where the version
#    has no archive row yet, and only an Owed line naming the tag lets
#    `test_every_released_tag_has_an_archive_row_or_the_changelog_says_it_is_owed`
#    pass there. It cannot be added afterwards; it must be in the commit the tag
#    names.
git commit -m "chore: v0.18.1"

# 2. the tag, annotated, on that commit, once CI is green on it
git tag -a v0.18.1 -m "v0.18.1"

# 3. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.18.1

# 4. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.18.1 --title "v0.18.1" --notes-file <the section body and its limitations>

# 5. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 4,
#    not on the tag of step 3. Read the new version DOI off the Zenodo record.

# 6. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 5, and the Owed line for
#    v0.18.1 leaves the change log in the same commit.
git commit -m "chore: the v0.18.1 archive row"

# 7. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 4 WAS MISSED AT v0.17.0** and the release was archived nowhere for a day;
**THE OWED LINE OF STEP 1 WAS MISSING AT v0.18.0** and its publish was skipped
until a follow-up commit and a second tag run. Both are written into the
sequence rather than remembered, because a fast release is exactly when a step
gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive
has minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number below comes from a command run at the moment this file was
written, and the command is beside it.

| what | command | reading |
|---|---|---|
| the tier-1 suite | `python -m pytest tests/tier1_offline` (eight slices) | 4082 passed, 6 skipped |
| the type checker | `python -m mypy src/pyflightstream tests/tier3_licensed/rotation_null.py` | Success, no issues in 85 source files |
| the linter | `python -m ruff check src tests scripts tools` | All checks passed |
| the tier-3 suite | `python -m pytest -m needs_flightstream tests/tier3_licensed` | not run for this patch: nothing in it spends a seat, and a seat is the owning seat's to spend |
| the goal | `python GeoversePlan/goals/check_goal_021.py` | the exit condition is 10 of 10 |

## What this release carries

The change log's `[0.18.1]` section is the record and is not restated here.
In one line each:

- **a swept row submits every point**, each running in its own datapoint
  folder, collected there;
- **the HPC profile's `[builds]` table**, naming a build the way its scheduler
  does;
- **a repeated POL is found in every matrix of a workspace**, and
  `plan --update-ids` renumbers the planned matrix;
- **a cited probe survey reaches the solver**, and a continuation opens the
  saved simulation it continues and runs under the campaign that stopped;
- **four message fixes** and a guard against messages that promise a release
  already out.

## What is NOT done, and is not being hidden

- **The swept row on a real cluster.** Proved against a submitting executor
  that calls no scheduler; the first real submission is the owning seat's.
- **Which build a cluster starts under a family name.** The `[builds]` table
  declares it; only a collected log shows it.
- **Retrying a failed continuation.** A failed one is refused by name, and its
  stop's saved simulation is kept under the point's `archive/`.
- **v0.14.0 is still not archived**, carried in the change log's Owed section.
- **Whether the solver's stop verb inside an action's script ends the RUN or
  only that script** is still unmeasured, carried from 0.18.0.
