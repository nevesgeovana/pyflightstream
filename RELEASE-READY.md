# v0.27.0 is released by this sequence, followed as written

0.27.0 is the release in which THE BASIC GUI STEPS THROUGH pyfs, the owner's theme
of 2026-09-23: a raw OBJ or STL runs from a matrix row with its unit declared and
its mesh operations in order; its trailing edges come from a node file by default,
initialised, detected and initialised again, or from the solver's detection; the
solver saves its residual, load and section plots; a volume section, an actuator
disc (by net thrust or by a radial profile) and a custom free stream are keys of a
row; the loads' surfaces, units and inviscid part are setup keys; every point keeps
its final saved simulation as a written guarantee, and `pyfs-matrix post
--additional-pproc` extracts a new pproc from it without solving again. Every table
the post writes opens with POL and holds no comma in a cell, and a point run
locally runs in its own folder. IT CHANGES WHAT A READER OF THE POST TABLES READS
in one way: the POLAR column is gone. The change log's `[0.27.0]` section is the
record; `docs/migrating-to-0.27.0.md` says what a reader's files must change.

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
#    pyproject.toml says 0.27.0.dev7 (the development tree) until this step, deliberately: a tree that
#    already said 0.27.0 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.27.0")
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
git commit -m "chore: v0.27.0"

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
git tag -a v0.27.0 -m "v0.27.0"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.27.0

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.27.0 --title "v0.27.0" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.27.0 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.27.0 archive row"

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

Readings of 2026-09-24, each status read from the process:

- `ruff check .` exit 0; `ruff format --check .` exit 0; `mypy` exit 0, "Success: no issues
  found in 100 source files".
- The full tier-1 suite, detached, one process per file, through
  `check_goal_031.py --suite`, on the release tree.
- `python scripts/mypy_recount.py`: 812 errors in 18 of 100 modules, against 0.26.0's 710 in 18 of 97
  (reports/RPT-029).
- Review OF THIS RELEASE: an OPENING round of five lenses before the first block, a
  CLOSING round of five lenses over v0.26.0..e305d21e and the POLAR branch (nine
  findings: six fixed, three registered for 0.28.0), and eight INDEPENDENT READINGS OF
  GitHub main, one after each pushed block and one of this commit, each finding fixed
  before the next block.

## What this release carries

In one line each:

- **A raw mesh runs.** OBJ or STL, unit declared, operations in order (G01, G03).
- **Trailing edges by file or by detection** (G02), the file route checked by the
  solver's own import count.
- **The solver's plots, sections, discs and a custom free stream on a row** (G04, G05,
  G06, G15).
- **The loads' surfaces, units and inviscid part, and the force distribution** as keys
  (G09, G10); two more setup keys, refused on the build that does not know them (G14).
- **The final saved simulation of every point, and the additional post** from it (G11,
  G12).
- **The roll and yaw rates emitted with the sign the solver reads** (G13).
- **INPUTS.md**, the glossary of every input key, beside VARIABLES.md (G08).
- **POL first in every table, no comma in a cell, no title line before a header** (G16).

## What the licensed campaign measured, and what it did not

Every route this release adds ran on 26.124, one run at a time, each with five
far-field layers: the three routes to one body and the file route's root node
(RPT-069), the volume section and the actuator disc (RPT-070), the custom free
stream (RPT-071), the additional post end to end (RPT-072), and the licensed
regression of every tier-3 row whose script changed (RPT-073), whose one finding,
a warm steady sweep moving the later points' coefficients against a cold one, is
registered for 0.28.0 rather than absorbed into a band.

## What is NOT done, and is not being hidden

- The warm sweep (the default since 0.16.0) against a cold one: on one wing in
  sideslip the later points differ by 3 percent in CL and in the sign of CMz. The
  default is the owner's call, with a probe on a cruise polar first (0.28.0).
- Inlets and outlets on a row (G07), which waits for a geometry to prove it on.
- The submitting half of the additional post; the grid unit of a custom field.
- The fixed-width super file overflows a text longer than its field (registered).
- The Zenodo version DOI of v0.27.0 is owed one commit after the tag.
