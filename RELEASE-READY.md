# v0.21.0 is released by this sequence, followed as written

**THE OWNER ASKED FOR THIS RELEASE** on 2026-09-15, as eight items of feedback
from a cluster run: the point name, a workspace rename, a sweep of any
flight-condition variable, `RPM` in the cell, a rotating free stream, the wall
clock's unit, the log a scheduler writes, and a way past the registered-build
refusal. The tag is cut when the sequence below reaches step 2 with the gate
green.

0.21.0 is a BREAKING release: a point is named by its flight condition, so an
existing workspace must be moved by `pyfs-matrix rename` before `collect` or
`post` will read it.

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.21.0.dev0 until this step, deliberately: a tree that
#    already said 0.21.0 would have every run made from it reporting the
#    released version while being a different tree. The [0.21.0] section is
#    dated 2026-09-16; if the tag is cut on another day, correct that date
#    here, because it is the one line of the section that stops being true by
#    waiting.
#    (pyproject.toml: version = "0.21.0")
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
#    AND THE CHANGE LOG'S Owed SECTION SAYS THE NEW TAG'S ROW IS *OWED*.
#    NAMING THE TAG IS NOT ENOUGH, and that cost the v0.21.0 publish on
#    2026-09-16: the bullet was there, it named v0.21.0 and it named the
#    archive, and it said "is not minted yet". The guard asks each BULLET for
#    three things -- the tag, an archive word, and a DEBT word (`owed`, `owe`,
#    `not exist`, `missing`) -- and the third was missing, so `publish` was
#    skipped. Write the word. And do not explain the rule inside the bullet:
#    a footnote mentioning `owed` satisfies the guard on its own, which is
#    measurable and was measured.
#    The absence of the line entirely cost the
#    v0.18.0 publish: the gates run against the TAGGED tree, where the version
#    has no archive row yet, and only an Owed line naming the tag lets
#    `test_every_released_tag_has_an_archive_row_or_the_changelog_says_it_is_owed`
#    pass there. It cannot be added afterwards; it must be in the commit the tag
#    names.
git commit -m "chore: v0.21.0"

# 2. the tag, annotated, on that commit, once CI is green on it
git tag -a v0.21.0 -m "v0.21.0"

# 3. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.21.0

# 4. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.21.0 --title "v0.21.0" --notes-file <the section body and its limitations>

# 5. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 4,
#    not on the tag of step 3. Read the new version DOI off the Zenodo record.

# 6. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 5, and the Owed line for
#    v0.21.0 leaves the change log in the same commit.
git commit -m "chore: the v0.21.0 archive row"

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
after 812a078 changes no executable code (it sets versions and prose), so a
reading taken on the code of 812a078 is a reading of the code this tag carries.

| what | command | reading |
|---|---|---|
| the tier-1 suite | `python -m pytest tests/tier1_offline` (one file per process) | 143 files, 4337 passed, 6 skipped, on the code of 812a078 |
| the type checker | `python -m mypy src/pyflightstream tests/tier3_licensed/rotation_null.py` | Success, no issues in 87 source files, on the code of 812a078 |
| the linter | `python -m ruff check src tests scripts tools` | All checks passed, on the code of 812a078 |
| the formatter | `python -m ruff format --check src tests scripts tools` | 279 files already formatted, on the code of 812a078 |
| the goal's arms | `python GeoversePlan/goals/check_goal_024.py` | 11 of 12 arms proved before this cut; `docs_release` is this cut |
| the goal's companion | `python GeoversePlan/goals/check_goal_024_mutations.py` | 20 of 21 mutants killed, 11 of 12 arms; the twelfth is `docs_release` |
| the tier-3 suite | `python -m pytest -m needs_flightstream tests/tier3_licensed` | not run for this release; the licensed evidence is RPT-052, three points on 26.124 |
| the review | five lenses over 1dab298..b906306, then qa, tech-writer and vv over b906306..812a078 | two rounds, 41 + 23 findings; two behaviour defects, both found in the CLOSING round and both introduced by a round-one fix |

## What this release carries

The change log's `[0.21.0]` section is the record and is not restated here. In
one line each:

- **a point is named by its flight condition**, and an existing workspace is
  moved to those names by `pyfs-matrix rename`;
- **any `FLIGHT_CONDITION` variable can be swept**, and a swept flow variable is
  resolved per point, which makes such a row one job per point;
- **`RPM` is a cell variable**, sweepable, and with an advance ratio it computes
  the velocity;
- **a row states a body rate** and the script writes `SET_FREESTREAM ROTATION`
  about the reference's moment point;
- **the `WALLTIME` cell carries its unit**, and a bare number is refused;
- **the HPC profile's `[log]` table** says how that machine writes the solver
  log, and the profile's keys are a closed set;
- **`--accept-unregistered-build`** lets a run proceed on an unregistered build,
  on the user's word and recorded in every record.

## What is NOT done, and is not being hidden

- **THE CLUSTER HAS NOT CONFIRMED ANY OF IT.** Every item here was specified
  from a written report and proved offline plus one licensed probe on a
  workstation. Whether the new names, the log copy and the wall clock behave on
  the machine that asked for them is the owner's to confirm.
- **The free-stream rotation's SENSE is measured and its physics is not.**
  RPT-052 measured one sign at one condition on one geometry; the report's own
  limits say what that does not establish, and its control is RECORDED rather
  than recomputable from this repository, because the probe scripts are not
  committed.
- **Two decisions are the owner's and are open**: whether `rename` should
  default to writing (as `upgrade --in-place` does) or to rehearsing, and
  whether a seat is worth spending on a roll-rate probe point.
- **Forty-five test modules narrate by pronoun.** Registered as TW-C9 of
  CLOSE-0210: pre-existing drift across the suite, not of this range.
- **v0.14.0 is still not archived**, carried in the change log's Owed section.
