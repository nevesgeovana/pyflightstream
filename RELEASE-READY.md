# v0.19.0 is released by this sequence, followed as written

**THE OWNING SEAT SET THIS RELEASE AS A GOAL** (GOAL-022: release it, following
this file as written). The tag is cut when the sequence below reaches step 2
with the gate green.

0.19.0 is one feature, a matrix row that translates an alias the way it rotates
one, and the fixes it brought with it. The diff being focused is the reason the
sequence is cheap, not a reason to shorten it.

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.19.0.dev0 until this step, deliberately: a tree that
#    already said 0.19.0 would have every run made from it reporting the
#    released version while being a different tree. The [0.19.0] section is
#    dated 2026-09-14; if the tag is cut on another day, correct that date
#    here, because it is the one line of the section that stops being true by
#    waiting.
#    (pyproject.toml: version = "0.19.0")
#
#    AND BOTH FRONT PAGES NAME THE NEW VERSION: the status line of README.md,
#    which is the PyPI project page, and of docs/index.md. Missed at the v0.18.1
#    release commit and caught by CI before the tag, by test_claim_currency.
#
#    AND CITATION.cff MOVES IN THE SAME COMMIT, all three fields together:
#    version, date-released, and the header paragraph that says whether this
#    is a DEVELOPMENT or a RELEASE tree, with its tally. The tally has TWO
#    sentences that count, and the 0.19.0.dev0 bump moved one and not the
#    other; read both.
#
#    AND THE CHANGE LOG'S Owed SECTION NAMES THE NEW TAG. Its absence cost the
#    v0.18.0 publish: the gates run against the TAGGED tree, where the version
#    has no archive row yet, and only an Owed line naming the tag lets
#    `test_every_released_tag_has_an_archive_row_or_the_changelog_says_it_is_owed`
#    pass there. It cannot be added afterwards; it must be in the commit the tag
#    names.
git commit -m "chore: v0.19.0"

# 2. the tag, annotated, on that commit, once CI is green on it
git tag -a v0.19.0 -m "v0.19.0"

# 3. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.19.0

# 4. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.19.0 --title "v0.19.0" --notes-file <the section body and its limitations>

# 5. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 4,
#    not on the tag of step 3. Read the new version DOI off the Zenodo record.

# 6. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 5, and the Owed line for
#    v0.19.0 leaves the change log in the same commit.
git commit -m "chore: the v0.19.0 archive row"

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
written, and the command is beside it.

| what | command | reading |
|---|---|---|
| the tier-1 suite | `python -m pytest tests/tier1_offline` (eight slices) | 4126 passed, 6 skipped |
| the type checker | `python -m mypy src/pyflightstream tests/tier3_licensed/rotation_null.py` | Success, no issues in 85 source files |
| the linter | `python -m ruff check src tests scripts tools` | All checks passed |
| the tier-3 suite | `python -m pytest -m needs_flightstream tests/tier3_licensed` | not run for this release; the translation was measured on 26.123 by RPT-048 on a seat the owning seat authorized |
| the goal | `python GeoversePlan/goals/check_goal_022.py` | the exit condition is 10 of 10 |

## What this release carries

The change log's `[0.19.0]` section is the record and is not restated here.
In one line each:

- **a matrix row translates an alias** with the grammar of `ROTATE`, its frames
  moving to their new origins, before every rotation;
- **every vertex of a moved set moves once**, the split measured on the solver
  (RPT-048);
- **a plot on a rotated hub is written in both frames**, as FR-71 always said;
- **`TRANSLATE_SURFACE_IN_FRAME` is phase setup**, a behaviour change for a
  script built by hand.

## What is NOT done, and is not being hidden

- **A rotor moved on an unsteady row was not run on the solver.** That its motion
  spins about the moved hub follows from the frames the script moves.
- **Only build 26.123 was run** for the split and the setup phase.
- **A translation reads a frame's origin in metres**, so it is right only on a
  simulation whose length unit is metres.
- **A flat rotor row cannot move its hub through `AUX_FRAMES`**: its blade axis
  frames are placed at the reference rotor position and turned about the hub, so
  where they stand after a move cannot be stated, and the move is refused.
- **`ROTATE`'s `ANGLE` still accepts `nan` and `inf`**, the gap `TRANSLATE` closes
  for its `DISTANCE`.
- **v0.14.0 is still not archived**, carried in the change log's Owed section.
