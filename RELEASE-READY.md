# v0.26.0 is released by this sequence, followed as written

0.26.0 is the release in which THE POST NEVER BLOCKS BY DEFAULT AND ALWAYS WRITES
ITS LOG, the owner's rule of 2026-09-22 made code: every `pyfs-matrix post` writes
`post.log` beside `products.json`, a clean campaign included, and a doubt about a
point (a frozen solve, a block the solver stopped under, a failed status, a
reference mismatch) is a warning line naming the point, the product, the step and
what would settle it, while every computable product is written; `--check-frozen`
refuses instead of warning. It ADDS THE INTEGRATED SECTIONAL LOADS she asked for:
`integrate = true` on a pproc distribution appends the strip length and the
integrated force and moment per station to the sloads file, strips midpoint to
midpoint, the moment about the quarter chord. It REARCHITECTS THE FREEZE CHECK:
the reducers state the plotted steps they read and the guard does no arithmetic
of its own (RPT-057 closed), a residual block cut before its anchor is unread
where the log has printed a page (RPT-055 closed). And NO COMPATIBILITY PROMISE
WAITS PAST IT: six forms are refused naming their replacement, and the reader of
`broken_commands` in recorded manifests stays as plain compatibility with no
countdown. IT CHANGES PUBLISHED NUMBERS BY THE OWNER'S DECISION, in the one way
the rule implies: what 0.25.x refused for a doubt is now written and warned. The
change log's `[0.26.0]` section is the record; `docs/migrating-to-0.26.0.md`
says what a reader's files must change (the removals) and what they may add.

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
#    pyproject.toml says 0.26.0.dev0 (the development tree) until this step, deliberately: a tree that
#    already said 0.26.0 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.26.0")
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
git commit -m "chore: v0.26.0"

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
git tag -a v0.26.0 -m "v0.26.0"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.26.0

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.26.0 --title "v0.26.0" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.26.0 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.26.0 archive row"

# 10. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 7 WAS MISSED AT v0.17.0** and the release was archived nowhere for a day;
**THE OWED LINE OF STEP 1 WAS MISSING AT v0.18.0** and its publish was skipped;
**IT WAS PRESENT BUT WORDLESS AT v0.21.0** and the publish was skipped again;
**IT WAS IN THE WRONG SECTION AT v0.25.0** and the release-tail review caught it
before the tag; **AN UNRELEASED SECTION DESCRIBED BEHAVIOUR THE TAG WOULD SHIP AT
v0.25.1**, caught by the version-identity guard, because a patch cut from the
development tree carries what that tree already changed; **THE FRONT PAGES WERE MISSED AT v0.18.1** and CI caught them
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

Readings of 2026-09-23, each status read from the process:

- `ruff check .` exit 0; `ruff format --check .` exit 0; `mypy` exit 0, "Success: no issues
  found in 97 source files".
- The full tier-1 suite, detached, one process per file, through
  `check_goal_030.py --suite`, on the release tree.
- `python scripts/mypy_recount.py`: 710 errors in 18 of 97 modules, against 0.25.1's 713
  (reports/RPT-029).
- Review OF THIS RELEASE, recorded in REL-0260_rounds.ledger: an OPENING round of five
  lenses over v0.25.1..d2fa9d3 (21 findings, 13 distinct defects, 11 fixed in two passes,
  one registered as RPT-058, one answered in the docs; four lenses found the same P1
  independently, a failed point's malformed export removing the healthy points'
  products), then a CLOSING round of five lenses over v0.25.1..12a488b (11 findings, 8
  distinct, EVERY ONE about an opening-round fix; fix D had been widened, found by all
  five), fixed in one pass with 29 regression cases red at 12a488b, then a QA read of
  that fix merge. Between the merges the suite arm one file per process found nine red
  files the passes had not run, four of them behaviour. Then THE INDEPENDENT REVIEW OF
  GitHub main, recorded in `REL-0260_independent-review.json`.
  The reviews of 0.25.1 belong to that release and are recorded with it.

## What this release carries

In one line each:

- **`post.log`, always.** Beside `products.json`, named in the manifest, archived with
  the products on a rebuild; every named skip and every warning is a line.
- **Nothing blocks by default.** A doubt is a warning and the product is written;
  `--check-frozen` refuses instead. What still skips is an impossibility (no data, a
  malformed export, an unassignable layout, frame, family or clock), each a log line.
- **The reducer states its samples.** `read_steps` from the averaging code path, the
  guard judges that set; the polar, the rotor table and the reductions agree on it.
- **Integrated sectional loads**, `integrate = true`, off by default and byte-identical
  when off; the strip rule and the moment point are on the definitions page.
- **The seven promises settled.** Six refused with the replacement named; the seventh
  read silently.
- **A failed point fails alone.** Its malformed export is its own named skip and its
  previous products are retired; the healthy points keep theirs.

## What the licensed campaign measured, and what it did not

NO SEAT WAS SPENT ON THIS RELEASE. The owner granted seats on her master's
geometries for the strips-against-the-polar case; they were not needed, because
the vendor manual states the moment point (SRC-751 p.253) and the offline fixture
states its own polar, and a seat would only have re-read what the manual says.
The road-to-1.0 report (in the control plane) carries the licensed tests this
release leaves owed, each with its build, its run count and what only a seat
proves.

The licensed campaigns of 0.25.0 (`reports/pfs0250/`) and 0.24.0 (`reports/pfs0240/`)
are unchanged by this release; `SOLVER_TIME_AVERAGING` stays refused on every
selectable build for the reason 0.25.0 recorded.

## What is NOT done, and is not being hidden

- `SOLVER_TIME_AVERAGING` is measured broken on 26.124 and unverified on the other
  builds; the averaging feature is refused on every selectable build.
- RPT-058: `post.log` is built from a process-wide warning capture, so two campaigns
  posting concurrently in threads of one process can cross their lines; every
  documented path posts one campaign per process. Registered for 0.27.0.
- The envelope of the integrated loads over a revolution, which the owner left out of
  this release deliberately; and an unambiguous whole-family selector for a pproc group,
  since `"all"` collides with a reference alias of that name (documented; 0.27.0).
- The Zenodo version DOI of v0.26.0 is owed one commit after the tag.
