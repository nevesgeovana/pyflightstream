# v0.22.0 is released by this sequence, followed as written

0.22.0 carries one BREAKING change, one feature and one fix. Breaking: a row's
`RPM` is a MAGNITUDE and the hand of the rotation comes from the reference's
`rpm_sign`, so a row stating a negative rev/min is refused by name. It is a
MINOR bump and not a patch for exactly that reason.

**THIS FILE IS RE-TITLED AND RE-MEASURED PER TAG, and it was not for v0.21.1.**
It carried the v0.21.0 title, commands and readings through the whole 0.21.1
release, so a reader following it would have run `git tag -a v0.21.0`, which
fails, and read a readings table two patches old. Whether it is re-titled each
time or split into a version-free sequence plus a per-release readings file is
the owner's call, registered as TW-F7 of FIX-0211; until she rules, it is
re-titled, and the reuse is recorded here rather than repeated silently.

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.22.0.dev0 until this step, deliberately: a tree that
#    already said 0.22.0 would have every run made from it reporting the
#    released version while being a different tree. THAT IS NOT HYPOTHETICAL:
#    the post-tag dev bump was missed after v0.21.1, so the tree sat at the
#    released identity while carrying code 0.21.1 does not have.
#    (pyproject.toml: version = "0.22.0")
#
#    AND BOTH FRONT PAGES NAME THE NEW VERSION: the status line of README.md,
#    which is the PyPI project page, and of docs/index.md.
#
#    AND THE GUIDE'S COVER: guide/pyflightstream_user_guide.tex carries the
#    version in \institute, and test_guide_currency compares it to pyproject.
#
#    AND CITATION.cff MOVES IN THE SAME COMMIT, all three fields together:
#    version, date-released, and the header paragraph that says whether this
#    is a DEVELOPMENT or a RELEASE tree, with its tally. The tally has TWO
#    sentences that count; read both.
#
#    AND THE CHANGE LOG'S Owed SECTION SAYS THE NEW TAG'S ROW IS *OWED*.
#    NAMING THE TAG IS NOT ENOUGH, and that cost the v0.21.0 publish on
#    2026-09-16: the bullet was there, it named the tag and it named the
#    archive, and it said "is not minted yet". The guard asks each BULLET for
#    three things -- the tag, an archive word, and a DEBT word (`owed`, `owe`,
#    `not exist`, `missing`) -- and the third was missing, so `publish` was
#    skipped and the tag had to be re-cut. Write the word. And do not explain
#    the rule inside the bullet: a footnote mentioning `owed` satisfies the
#    guard on its own, which is measurable and was measured.
git commit -m "chore: v0.22.0"

# 2. the tag, annotated, on that commit, once CI is green on it
git tag -a v0.22.0 -m "v0.22.0"

# 3. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.22.0

# 4. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.22.0 --title "v0.22.0" --notes-file <the section body and its limits>

# 5. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 4,
#    not on the tag of step 3. Read the new version DOI off the Zenodo record.

# 6. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 5, and the Owed line for
#    v0.22.0 leaves the change log in the same commit.
git commit -m "chore: the v0.22.0 archive row"

# 7. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 4 WAS MISSED AT v0.17.0** and the release was archived nowhere for a day;
**THE OWED LINE OF STEP 1 WAS MISSING AT v0.18.0** and its publish was skipped;
**IT WAS PRESENT BUT WORDLESS AT v0.21.0** and the publish was skipped again, for
the debt word; **THE FRONT PAGES WERE MISSED AT v0.18.1** and CI caught them
before the tag; **THE POST-TAG DEV BUMP WAS MISSED AFTER v0.21.1**. Each is
written into the sequence rather than remembered, because a fast release is
exactly when a step gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive
has minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number comes from a command run at the moment this file was written, with
the command beside it. The release commit changes no executable code, so a
reading taken on the code below is a reading of the code the tag carries.

| what | command | reading |
|---|---|---|
| the tier-1 suite | `python -m pytest tests/tier1_offline` (one file per process) | 145 files, 4361 passed, 0 failures |
| the type checker | `python -m mypy src/pyflightstream tests/tier3_licensed/rotation_null.py` | Success, no issues in 87 source files |
| the linter | `python -m ruff check src tests scripts tools` | All checks passed |
| the formatter | `python -m ruff format --check src tests scripts tools` | all files formatted |
| the review | qa, architect, api-designer and tech-writer over dd1010f..d2a1e24 | one round, FIX-0212; one BLOCKING finding, and the flag was rebuilt on it |
| the review | qa, architect, vv and tech-writer over d2a1e24..90c45fc | one round, FIX-0220, over the ROTOR SIGN; two BLOCKING, and each was a second live path to the same wrong-way rotation |
| the mutants | the module's companion, six sited on this change | 6 of 6 killed against a green control |
| the tier-3 suite | `python -m pytest -m needs_flightstream tests/tier3_licensed` | NOT RUN. See below: this release DOES change the emitted script |

## What this release carries

The change log's `[0.22.0]` section is the record. In one line:

- **BREAKING: a row's `RPM` is a magnitude and the reference's `rpm_sign` is the
  hand.** Until 0.21.1 the reference's hand was dropped in silence for a row that
  stated its own speed, so such a rotor turned whichever way its number was
  written: no refusal, no warning, and a rotor turning backwards converges and
  reports numbers. The point's name writes `RPM` in magnitude.
- **`pyfs-matrix run --force-rerun <point>`** redoes a point whose matrix row
  was wrong, archiving its record and its collected outputs rather than deleting
  them, and naming points rather than redoing a whole matrix.
- **A refused motion no longer reads as an absent one**, and a refusal from
  `pyfs-matrix run` is printed rather than raised as a traceback.

(The 0.20.x migration deadlock between `rename` and `collect` was fixed in
**0.21.1** and is already released; it is not carried by this tag.)

## What no seat confirmed, stated plainly

**This release changes the emitted script, and no licensed run was made.**

Seven tier-3 goldens move in this range, each on one line, each the same shape:
`SET_MOTION_ROTOR_RPM n 800.0` becomes `-800.0`. Those rows state `RPM: 800` and
their reference declares `rpm_sign = -1`, so the OLD goldens are the defect
frozen in place. The new ones are the package's own PLAN-TIME RENDER, compared
offline by `tests/tier1_offline/test_tier3_offline.py`; a golden is not evidence
about the solver and was never validated against a run.

What the tree measures, and what it does not:

- **RPT-049 measured the POSITIVE hand on a seat**: `SET_MOTION_ROTOR_RPM 1
  473.1723` about axis `X` turned the export centroid `+90.000`, which is a
  right-handed rotation about `+X` and is the convention FR-60 states.
- **Nothing in the tree measures the NEGATIVE hand.** That the solver reads the
  minus as a reversal -- rather than refusing it, clamping it, or taking the
  magnitude -- is INFERRED from the positive measurement. It is the step this
  release turns on, and it is asserted rather than measured.

The smallest run that would settle it is one rotor at `+N` and the same rotor at
`-N`, reading the exported centroid angle: one point, one seat. **Whether to
spend it before or after the tag is the owner's call**, and this file does not
decide it.

## What is NOT done, and is not being hidden

- **THE REVIEW FOUND THE FIRST WRITING OF THIS FLAG BROKEN**, in a way that
  archived the evidence and then ran nothing, and the six tests covering it
  could not fail because every one used a fixture whose shape could not reach
  the defect. It is fixed and scored; the episode is the reason this release
  carries a round rather than a patch.
- **A refusal in the collecting sweep still rewrites the record as
  `FAILED_INCOMPLETE_OUTPUT` and clears `SUBMITTED`**, so any refusal costs the
  ability to retry that point. Unchanged here; the owner's call.
- **`plan` does not know the flag**, so a plan marks a point ALREADY_RECORDED
  and a run with `--force-rerun` then executes it. Registered, the owner's call.
- **No cluster has confirmed 0.21.0, 0.21.1 or this.**
- **v0.14.0 is still not archived**, carried in the change log's Owed section.
