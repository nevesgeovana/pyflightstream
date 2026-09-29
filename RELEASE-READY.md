# v0.30.0 is released by this sequence, followed as written

0.30.0 is the release of THE QUASI-STEADY ROTOR, FSI ON THE STEADY ROUTES, AND
THE WORKSPACE'S STORAGE: the `qsteady_rotor` run type solves an isolated,
axisymmetric rotor steady, as a periodic SECTOR or a clocked WHEEL whose
`PASSAGE_POSITIONS` clockings the post averages, with its 1P reduced frequency
as a validity parameter at plan and at post and `pyfs-matrix plan --inflow-fft`
for a custom inflow; FSI couples a fixed wing on `steady` and on `unsteady`
without rotor motion, and the rotating blade of a `qsteady_rotor` sector, while
FSI on `unsteady_rotor` is refused by the plan; `pyfs-matrix space-in-use`,
`free-space`, `delete-sims` and `sync` manage a workspace's disk and bring
runs and results from other workspaces into it, and `free-space` can prune an
unsteady row's per-step exports to each point's last step. IT CHANGES WHAT A
READER DOES: a Tecplot surface no longer carries the native nodal strength
unless the pproc sets `singularity_strength = true`, a coupled blade route
emits `AEROELASTIC_RBF_TYPE MULTI_QUADRATIC` unless the setup states a kernel,
the structural nodes sit inside a blade that carries its sections, and the
console ends each command with a drawn box on stderr. The change log's
`[0.30.0]` section is the record; `docs/migrating-to-0.30.0.md` says what a
reader's files must change.

**THIS FILE IS RE-TITLED AND RE-MEASURED PER TAG.** It carried the v0.22.0 title,
commands and readings through the whole 0.23.0 release, and it carried the v0.24.0
title and readings up to the eve of v0.25.0, where the INDEPENDENT REVIEW OF GitHub
main caught it (finding 6, 2026-09-20): a reader following it would have tagged the
previous release. Whether it is re-titled each time or split into a version-free
sequence plus a per-release readings file is still the owner's call; until she
rules, it is re-titled. The v0.29.0 edition is in the history of this file
(`git show v0.29.0:RELEASE-READY.md`).

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.30.0.devN (the development tree) until this step, deliberately: a tree that
#    already said 0.30.0 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.30.0")
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
git commit -m "chore: v0.30.0"

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
git tag -a v0.30.0 -m "v0.30.0"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.30.0

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.30.0 --title "v0.30.0" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.30.0 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.30.0 archive row"

# 10. confirm, rather than assume
python scripts/check_release_published.py    # online is the default; --offline skips the network
```

**STEP 7 WAS MISSED AT v0.17.0** and the release was archived nowhere for a day;
**THE OWED LINE OF STEP 1 WAS MISSING AT v0.18.0** and its publish was skipped;
**IT WAS PRESENT BUT WORDLESS AT v0.21.0** and the publish was skipped again;
**IT WAS IN THE WRONG SECTION AT v0.25.0** and the release-tail review caught it
before the tag; **AN UNRELEASED SECTION DESCRIBED BEHAVIOUR THE TAG WOULD SHIP AT
v0.25.1**, caught by the version-identity guard, because a patch cut from the
development tree carries what that tree already changed; **THE FRONT PAGES WERE
MISSED AT v0.18.1** and CI caught them before the tag; **THE POST-TAG DEV BUMP WAS
MISSED AFTER v0.21.1**; **THE INDEPENDENT REVIEW WAS SKIPPED FROM v0.18.0 TO
v0.22.0**; **THIS FILE ITSELF WAS STILL RELEASING v0.24.0 ON THE EVE OF v0.25.0**.
Each is written into the sequence rather than remembered, because a fast release
is exactly when a step gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive has
minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number comes from a command run at the moment this file was written, with
the command beside it. A reading of an earlier commit is evidence only for that
commit, and no count of 0.29.0 is reused here.

Readings of 2026-09-29, on the release tree (the source of `4f12aede` with the
release documentation), each status read from the process:

- `ruff check .` exit 0, "All checks passed!"; `ruff format --check .` exit 0,
  "606 files already formatted".
- `python scripts/mypy_recount.py`, on a tree the script reported clean: 1065
  errors in 18 of 134 modules, against 0.29.0's 922 in 18 of 128
  (reports/RPT-029); the shipped configuration's invocation in the same run,
  "Success: no issues found in 134 source files".
- The test files that read the change log, the citation, the front pages, the
  requirement set and the house rules are run over the release documentation
  commits; their results are recorded with those commits.

PENDING, and not claimed by this file until its evidence is attached to the
commit it names:

- **The full tier-1 suite over the release commit.** Runs over earlier commits of
  this release do not stand in for it.
- **The review attestation over the release range** (step 2) and **the
  independent reading of GitHub main** on the pushed commit (step 4).
- **CI green on the commit to be tagged**, including the release workflow's single
  build and its clean installed-wheel jobs.
- **The tag, its PyPI publication, the release object and the Zenodo version
  DOI** (steps 5 to 10). The v0.30.0 archive row is owed in the change log.

## What this release carries

In one line each:

- **The quasi-steady rotor.** `qsteady_rotor`: one rotor solved steady in a
  free stream turning about its shaft, as a periodic sector or a clocked wheel
  (`PASSAGE_POSITIONS`), averaged by the post into `_qs_positions.csv` and
  `_qs_avg.csv`, with the 1P reduced frequency `k` at plan, in a per-point
  validity file and in every product of the point.
- **The inflow's harmonics.** `pyfs-matrix plan --inflow-fft` reads a custom
  inflow as one blade meets it and suggests the clockings a wheel point needs.
- **FSI.** A fixed wing on `steady` and on `unsteady` without rotor motion, with
  its own weight; the rotating blade of a `qsteady_rotor` sector at the row's
  speed; FSI on `unsteady_rotor` refused by the plan; structural nodes inside
  the blade; `MULTI_QUADRATIC` by default; the in-plane centrifugal softening.
- **Storage and sync.** `space-in-use`, `free-space` (with the per-step export
  pruning), `delete-sims` and `sync`, every call recorded in
  `storage_management.json`; the plan warns when the points to run may not fit
  on the disk.
- **Rotor Mach numbers.** Tip and helical Mach per rotor per point at plan, in
  the run record and as the rotor table's last two columns.
- **Surfaces and logs.** The native nodal strength by request
  (`singularity_strength`); a periodic row's native Tecplot read one zone per
  copy; a completed solve kept when only its translation failed; a cleaner
  console log with `--verbose`.

## What the licensed campaign measured, and what it did not

All on FlightStream 26.124. [RPT-086](reports/RPT-086_gui-launch-windows_2026-09-28.md)
records the windows the GUI shows at launch, which the window watcher now
spares; [RPT-087](reports/RPT-087_periodic-native-tecplot-one-zone-per-copy_2026-09-28.md)
the periodic row's native Tecplot, one zone per copy;
[RPT-088](reports/RPT-088_26124-unsteady-log-without-a-completion-line_2026-09-28.md)
an unsteady log with no completion line;
[RPT-089](reports/RPT-089_qsteady-rotor-vs-unsteady_2026-09-29.md) the
quasi-steady wheel against the unsteady rotor on a six-blade propeller,
including the clockings a wheel needs and the unsteady time-step study; and
[RPT-093](reports/RPT-093_aeroelastic-coupling-on-26124_2026-09-29.md) the
aeroelastic coupling toolbox on a fixed wing and on a propeller blade. The
long licensed campaigns were not run for this release.

## What is NOT done, and is not being hidden

- FSI on `unsteady_rotor` is refused: on 26.124 the morph of a mapped rotating
  blade replaces its rotation (RPT-025, RPT-093).
- The fixed-wing FSI route and the sign of the XZ cut's moment column wait on
  their licensed confirmation.
- The quasi-steady wheel is valid for an isolated, axisymmetric rotor; its
  corrections for unsteady effects are not part of this release.
- The change log cites RPT-090, RPT-091 and RPT-092 for the short licensed runs
  whose four defects this release fixes; those reports are not in this tree.
- `ROTOR_SHEDDING` stays refused; direction control for the relaxed wake is
  not part of this release.
- The Zenodo version DOI of v0.30.0 is owed one commit after the tag.
