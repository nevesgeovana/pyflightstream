# v0.28.0 is released by this sequence, followed as written

0.28.0 is the release of USER CAPABILITIES, the owner's approval of 2026-09-24:
a submitting run ends on one summary line and a local run keeps a log that says
its progress; one point of a recorded steady job reruns the whole job, and
`--force-rerun-all` reruns a matrix or the simulations named with `--sims`; an
unsteady row can start cold; every input file has a worked example in
`inputs/input_template.md`; the custom free stream is read from an input file in
either form and warned when its grid misses the body; an OBJ's surface names come
from its groups; an actuator disc takes its speed from the advance ratio; the
Tecplot surface is written by the package from the solver's VTK, per cell and in
the reference frame; `[time_averaging]` works, averaged by the package; an
unsteady row saves the solver's residual and load plots; and the FSI's blade
properties come from its sections and a cited material. IT CHANGES WHAT A READER
OF THE TECPLOT SURFACE READS: values per cell under the VTK's names, no
`Singularity_strength`, and the symmetry images on a symmetric row. The change
log's `[0.28.0]` section is the record; `docs/migrating-to-0.28.0.md` says what a
reader's files must change.

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
#    pyproject.toml says 0.28.0.dev4 (the development tree) until this step, deliberately: a tree that
#    already said 0.28.0 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.28.0")
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
git commit -m "chore: v0.28.0"

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
git tag -a v0.28.0 -m "v0.28.0"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.28.0

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.28.0 --title "v0.28.0" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.28.0 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.28.0 archive row"

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

Readings of 2026-09-25, each status read from the process:

- `ruff check .` exit 0; `ruff format --check .` exit 0, "483 files already
  formatted"; `mypy` exit 0, "Success: no issues found in 104 source files".
- The full tier-1 suite, detached, one process per file, through
  `check_goal_032.py --suite`, each run over the commit named: every gate green
  on 1917362e (block D), on 35917503 (the fix of the independent reading C32) and
  on a3ef9f1e (the closing round's fixes 42e9ee65, the release commit ad237d2b,
  the fix of reading D33 b6664116 and a test fixture after it; the run over
  b6664116 was red in that one fixture, fixed at a3ef9f1e). The commit after
  a3ef9f1e fixes reading E34 in the section calculator; the suite over the tagged
  commit is the push gate and its record is the goal's suite arm.
- `python scripts/mypy_recount.py`: 863 errors in 18 of 104 modules, against
  0.27.0's 812 in 18 of 100 (reports/RPT-029).
- Review OF THIS RELEASE: an OPENING round of five lenses on the approved scope,
  whose questions were decided before the blocks that needed them; a CLOSING round
  of five lenses over v0.27.0..35917503, all GO (sixteen findings: five fixed, ten
  registered for the rigor track of 0.29.0, one checked and left as it is); an
  INDEPENDENT READING OF GitHub main
  exactly on the commit of every development wheel and after every pushed block,
  each finding fixed before the next block. THE READING OF THIS COMMIT ON GitHub
  main is step 4 of the sequence and is owed until it runs; the tag waits on it.

## What this release carries

In one line each:

- **Run and log.** One summary line for a submitting run, a local log with
  `--progress-every` (G43); a warning for a pproc plot group named like the
  automatic rotor group (G42); `COLD_START` on unsteady rows (G36); one point of a
  steady job reruns the job (G37); `--force-rerun-all` and `--sims` (G44).
- **Inputs.** `inputs/input_template.md`, an example of every input file (G47); the
  custom free stream by an input file, warned when it misses the body (G18); an
  OBJ's surface names from its groups (G30); a disc's speed from the advance ratio
  (G20).
- **The surface.** The Tecplot written from the VTK (G45); the time average by the
  package (G25); the solver's plots after an unsteady march (G26); the boundary
  layer profile export recorded broken on 26.124 (G24).
- **The FSI blade.** A cited material database and a solid-section calculator for
  the beam's properties, with their provenance (G41).

## What the licensed campaign measured, and what it did not

Every route this release adds that the solver answers ran on 26.124, or on 26.122
where 26.124 cannot, one run at a time, each with five far-field layers: the VTK
export's frame and variables (RPT-074), the boundary layer profile (RPT-075), the
solver's plots after an unsteady solve (RPT-076), the custom free stream's forms
and its reach (RPT-077), an OBJ's group order (RPT-078), the solver's own time
average (RPT-079), and the licensed regression of every tier-3 point (RPT-080):
every point ran, the 83 licensed checks pass, all 76 loads tables equal the 0.27.0
run's, and the package's Tecplot puts every real surface where the solver's own
file put it, carrying the symmetry images on a symmetric row. It found no defect
of the solve.

## What is NOT done, and is not being hidden

- A loads frame a rotor motion carries: no tier-3 row has one, and whether the
  frame moves during the solve is not measured (R24 of the rigor track).
- The section calculator does not cross-check a section against its chord, so a
  section in millimetres passed as metres is not refused (R20).
- A continuation of a run recorded before 0.28.0 is refused unless its pproc
  exports no Tecplot; recovering that run's loads frame is proposed for 0.29.0.
- The warm sweep against a cold one (R13), inlets and outlets on a row (G07), the
  submitting half of the additional post: carried to 0.29.0.
- The Zenodo version DOI of v0.28.0 is owed one commit after the tag.
