# v0.20.0 is released by this sequence, followed as written

**THE OWNING SEAT SET THIS RELEASE AS A GOAL** (GOAL-023: 0.20.0 released, and
every matrix workflow runs on every build we hold, 26.124 included; followed as
this file is written). The tag is cut when the sequence below reaches step 2
with the gate green.

0.20.0 is one promise: the same matrix row on every registered build, with only
`FS_BUILD` changed. It brings 26.124, the single march on the builds without
unsteady solver actions, the refusal by name of what only actions give, and the
Euclidean rotor on the builds before the rotary motion.

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.20.0.dev0 until this step, deliberately: a tree that
#    already said 0.20.0 would have every run made from it reporting the
#    released version while being a different tree. The [0.20.0] section is
#    dated 2026-09-15; if the tag is cut on another day, correct that date
#    here, because it is the one line of the section that stops being true by
#    waiting.
#    (pyproject.toml: version = "0.20.0")
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
git commit -m "chore: v0.20.0"

# 2. the tag, annotated, on that commit, once CI is green on it
git tag -a v0.20.0 -m "v0.20.0"

# 3. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.20.0

# 4. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.20.0 --title "v0.20.0" --notes-file <the section body and its limitations>

# 5. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 4,
#    not on the tag of step 3. Read the new version DOI off the Zenodo record.

# 6. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 5, and the Owed line for
#    v0.20.0 leaves the change log in the same commit.
git commit -m "chore: the v0.20.0 archive row"

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
| the tier-1 suite | `python -m pytest tests/tier1_offline` (eight slices) | 4234 passed, 6 skipped, on the code of b9025c1 |
| the type checker | `python -m mypy src/pyflightstream tests/tier3_licensed/rotation_null.py` | Success, no issues in 86 source files |
| the linter | `python -m ruff check src tests scripts tools` | All checks passed |
| the tier-3 suite | `python -m pytest -m needs_flightstream tests/tier3_licensed` | not run for this release; the builds were measured by RPT-049 (26.000, 26.100, 26.120) and a private workspace of three rows on 26.124, 26.123 and 26.120 |
| the goal | `python GeoversePlan/goals/check_goal_023.py` | the exit condition is 12 of 12; the release and guides arms prove only after the tag, the archive and the guides land |

## What this release carries

The change log's `[0.20.0]` section is the record, its Limits first, and is not
restated here. In one line each:

- **26.124 is registered** at `operational`, its documentation the 26.123 files
  byte for byte (RPT-050);
- **every unsteady row is marched on its build**, with actions where the row asks
  for what only they give, as a single march otherwise, and the choice recorded;
- **what a build without actions cannot give is refused by name**, at plan time;
- **a rotor row renders on 25.100 and 26.000** as a Euclidean rotor (RPT-049);
- **a rebuild archives the series tables it rewrites**.

## What is NOT done, and is not being hidden

- **Four cells of the support matrix are refused**: every run type on 25.000 and
  `unsteady_rotor` on 26.100. Whether to fill them is the owner's.
- **A row's preset or post-processing can still ask an older build for a command
  it lacks**, and that point is blocked at plan time.
- **The actions march and the single march were not compared on one build.**
- **The Euclidean rotor was run on 26.000 only**, for kinematics over three steps.
- **Whether 26.124 and 26.123 compute the same numbers is not stated.**
- **The internal-defect refusal of `build_script` is a `WorkflowCoverageError`**,
  so a package bug there reads as a blocked row; registered for a later release.
- **Whether the solver's stop verb inside an action's script ends the RUN or
  only that script** is still unmeasured, carried from 0.18.0.
- **v0.14.0 is still not archived**, carried in the change log's Owed section.
