# v0.18.0 is ready, and the tag is not mine to cut

**THE TREE IS GREEN AND PUSHED AND THE TAG IS NOT CUT.** That is deliberate.
The owning seat's stopping condition is that the work goes to the push and
stops there, with the tag one command away.

The reason is that feedback from using the previous release can still enter
this one as SCOPE while the tag is uncut, and can only arrive as a patch once
it is cut. So the work stops here, ready, and the word that fires the tag
belongs to the owning seat.

## The sequence, in order, and the step that was missed last time

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml still says 0.18.0.dev0, deliberately: the tree is not the
#    release until this step, and a tree that already said 0.18.0 would have
#    every run made from it reporting the released version while being a
#    different tree. The [0.18.0] section is written and dated 2026-09-14; if
#    the tag is cut on another day, correct that date here, because it is the
#    one line of the section that stops being true by waiting.
#    (pyproject.toml: version = "0.18.0")
#
#    AND CITATION.cff MOVES IN THE SAME COMMIT, all three fields together:
#    version, date-released, and the header paragraph that says whether this
#    is a DEVELOPMENT or a RELEASE tree. That file's own tally records three
#    occasions when the fields moved and the paragraph did not.
#
#    AND THE CHANGE LOG'S Owed SECTION NAMES THE NEW TAG. This step was
#    MISSING from this file and its absence cost the v0.18.0 publish. The
#    moment the tag exists, the tag's own tree holds a released version with
#    no archive row, and `test_every_released_tag_has_an_archive_row_or_the_
#    changelog_says_it_is_owed` fails on it. The gates run against the TAGGED
#    tree, so the owed line cannot be added afterwards: it must be in the
#    commit the tag names. v0.17.0's release commit carried it and that is why
#    v0.17.0 published.
git commit -m "chore: v0.18.0"

# 2. the tag, annotated, on that commit
git tag -a v0.18.0 -m "v0.18.0"

# 3. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.18.0

# 4. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.18.0 --title "v0.18.0" --notes-file <the section body>

# 5. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 4,
#    not on the tag of step 3, and it minted in about four seconds last time.
#    Read the new version DOI off the Zenodo record.

# 6. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 5.
git commit -m "chore: the v0.18.0 archive row"

# 7. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 4 IS THE ONE THAT WAS MISSED.** At v0.17.0 the tag was pushed, the
package index served the wheel within minutes, and the release object was never
created; the archive webhook fires on the release object rather than on the
tag, so the release was archived NOWHERE for a day and the concept DOI went on
resolving to the previous version. It was found by looking at the archive
record rather than by any gate, because every gate this repository had asks
its question BEFORE the push, and this failure happens after it.

That is why `scripts/check_release_published.py` now exists and why step 7 is
part of the sequence rather than a thing someone remembers: a tag is RELEASED
when the release object exists at that tag AND the archive has minted a version
DOI that `CITATION.cff` records, and anything less is a tag.

## What is true of the tree right now

Every number below comes from a command run at the moment this file was
written, and the command is beside it.

| what | command | reading |
|---|---|---|
| the tier-1 suite | `python -m pytest tests/tier1_offline` (four slices) | 3992 passed, 7 skipped |
| the type checker | `python -m mypy src/pyflightstream tests/tier3_licensed/rotation_null.py` | Success, no issues in 85 source files |
| the linter | `python -m ruff check src tests scripts tools` | All checks passed |
| the tier-3 suite | `python -m pytest -m needs_flightstream tests/tier3_licensed` | run on the seat on 26.123 |
| the goal | `python GeoversePlan/goals/check_goal_020.py` | see the file; the exit condition is 10 of 10 |

## What this release carries

The change log's `[0.18.0]` section is the record and is not restated here.
In one line each:

- **collect-and-post**, a stage that watches the WORKSPACE rather than the
  scheduler and fires on presence AND settled.
- **RESTART**, in all three forms, with the replaced outputs archived into
  day-and-hour stamped folders.
- **the twelve deprecations**, which never fell due, corrected BESIDE the
  entry that got it wrong rather than by editing it.
- **the four board rows the owning seat ruled on**, two of them run on the
  licensed seat.
- **the living physics report**, generated, beginning at 26.123.
- **the release-published check**, which is the subject of this file.

## One thing to know before the tag

**v0.14.0 IS NOT CITABLE AND HAS NOT BEEN SINCE IT SHIPPED.** `CITATION.cff`
carries no archive row for it; the change log's Owed section has declared this
since 2026-09-10 and it was last measured against the archive's own API that
day. This release's new `scripts/check_release_published.py` is what turned a
declared debt into a reported one: its window is one release wide, so a tag
whose row is still owed after a newer tag has shipped now FAILS rather than
sitting inside an open-ended exemption.

It could not be resolved while this work was done, and the reason is stated
rather than left as a gap: the archive service answered `504 Gateway Time-out`
to every request, including for a record known to exist. So the DOI could not
be read back. **It does not block this tag** and nothing here depends on it;
it is a separate repair, and it is one command once the service answers:

```
python scripts/check_release_published.py            # names the tag and the claim
# then read the v0.14.0 version DOI off the Zenodo record and add its row
```

## What is NOT done, and is not being hidden

- **The tag.** The owning seat's.
- **Whether the ninety-four rows extracted to GEO-049 matter to Geoverse.**
  The owning seat's, and the report ends without answering it.
- **Whether the solver's stop verb inside an action's script ends the RUN or
  only that script.** Still unmeasured; it needs a licensed probe that moves
  one thing, and no probe in this release moved one thing.
- **Whether a continuation's numbers are physically continuous** rather than
  merely recorded as such. The run record says a continuation happened; no
  measurement in this release says the march is smooth across the seam.
