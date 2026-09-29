# v0.31.0 is released by this sequence, followed as written

0.31.0 is the release of THE QUASI-STEADY WHEEL'S CORRECTION MACHINERY AND ITS
PRODUCTS: a clocked `qsteady_rotor` wheel is cut into sections at every
clocking, its rotor table is the mean of its clockings, a wheel point states
its rotor state, and a pproc's `[qsteady_correction]` writes corrected
products BESIDE the raw ones from a calibration of `inputs/calibrations/`,
off by default and not validated; every rotor point gets the per-station
harmonic product, an unsteady rotor its per-revolution table, the rotor table
its in-plane coefficients, and `pyfs-workspace field` builds a custom
free-stream file from other fields. IT CHANGES WHAT A READER DOES: a wheel's
rotor-table row is the mean of its clockings (0.30.0's rows remain a record
of clocking 0), its sections table gains `CLOCKING` and a block per clocking,
the rotor table gains four last columns, the thrust and torque shares are
taken along the rotor's axis, the clockings table of a left-hand wheel and
the blade blocks 2 to N of an unsteady rotor state other azimuths, two
quasi-steady readers are removed for one typed record, and the guide decks
are renamed `pyfts-guide-00` to `07`. The change log's `[0.31.0]` section is
the record; `docs/migrating-to-0.31.0.md` says what a reader's files must
change.

**THIS FILE IS RE-TITLED AND RE-MEASURED PER TAG.** It carried the v0.22.0 title,
commands and readings through the whole 0.23.0 release, and it carried the v0.24.0
title and readings up to the eve of v0.25.0, where the INDEPENDENT REVIEW OF GitHub
main caught it (finding 6, 2026-09-20): a reader following it would have tagged the
previous release. Whether it is re-titled each time or split into a version-free
sequence plus a per-release readings file is still the owner's call; until she
rules, it is re-titled. The v0.30.0 edition is in the history of this file
(`git show v0.30.0:RELEASE-READY.md`).

## The sequence, in order, and the steps that were missed before

```
# 1. the release commit: set the version and CONFIRM the change log's date.
#    pyproject.toml says 0.31.0.devN (the development tree) until this step, deliberately: a tree that
#    already said 0.31.0 would have every run made from it reporting the released
#    version while being a different tree.
#    (pyproject.toml: version = "0.31.0")
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
git commit -m "chore: v0.31.0"

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
git tag -a v0.31.0 -m "v0.31.0"

# 6. push the tag. THIS PUBLISHES TO PyPI and nothing else.
git push origin v0.31.0

# 7. THE RELEASE OBJECT. This is the step that was missed at v0.17.0.
gh release create v0.31.0 --title "v0.31.0" --notes-file <the section body and its limits>

# 8. the archive DOI. Zenodo's webhook fires on the RELEASE OBJECT of step 7,
#    not on the tag of step 6. Read the new version DOI off the Zenodo record.

# 9. the citation row, one commit after the tag
#    CITATION.cff gains the version DOI from step 8, and the Owed line for
#    v0.31.0 leaves the change log in the same commit. THE TREE MOVES TO THE NEXT
#    .dev0 IN THAT COMMIT: the post-tag dev bump was missed after v0.21.1.
git commit -m "chore: the v0.31.0 archive row"

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
MISSED AFTER v0.21.1**, **AND AGAIN AFTER v0.30.0** (the archive row's commit,
51cc4a82, left the tree at 0.30.0, so `test_guide_decks` reads the 0.31.0 decks
against a tree that says it releases 0.30.0 until step 1); **THE INDEPENDENT
REVIEW WAS SKIPPED FROM v0.18.0 TO
v0.22.0**; **THIS FILE ITSELF WAS STILL RELEASING v0.24.0 ON THE EVE OF v0.25.0**.
Each is written into the sequence rather than remembered, because a fast release
is exactly when a step gets skipped.

A tag is RELEASED when the release object exists at that tag AND the archive has
minted a version DOI that `CITATION.cff` records; anything less is a tag.
`scripts/check_release_published.py` asks both halves.

## What is true of the tree at the release commit

Every number comes from a command run at the moment this file was written, with
the command beside it. A reading of an earlier commit is evidence only for that
commit, and no count of 0.30.0 is reused here.

Readings of 2026-09-29, on the reconciled release candidate (`feat/0-31`,
every 0.31 item merged and reconciled, version still 0.30.0 in
`pyproject.toml`, the change log's `[Unreleased]` undated), each status read
from the process:

- `ruff check .` exit 0, "All checks passed!"; `ruff format --check .` exit 0,
  "625 files already formatted".
- `mypy` (the shipped configuration, as CI's `types` job runs it) exit 0,
  "Success: no issues found in 138 source files".
- `python scripts/mypy_recount.py`, on a tree the script reported clean
  (33c1d7ef, re-run unchanged on 97682ca2): 1084 errors in 18 of 138
  modules, against 0.30.0's 1065 in 18 of 134 (reports/RPT-029).
- `pytest` over the reconciliation's gate set (every `test_goal036_*.py`,
  `test_exceptions_catalog`, `test_products_split_surface`,
  `test_traceability`, `test_overview`, `test_repository_guards`,
  `test_guide_decks`, `test_house_style`, `test_public_api`,
  `test_conventions`, `test_goal028_module_level_layering`,
  `test_import_isolation`, `test_matrix_run`, `test_post_products`,
  `test_workflows`), on 97682ca2: exit 1, "1 failed, 969 passed, 1 skipped".
  The one failure is
  `test_guide_decks::test_the_decks_state_the_version_this_tree_releases_once`:
  the decks are written for 0.31.0 and `pyproject.toml` still says 0.30.0
  (the post-tag bump was missed, above); step 1 turns it green.
- The shipped-surface checker (`tools/check_shipped_surface.py`) reads
  "exempt 167", the cap.
- `properdocs build --strict` exit 0.

PENDING, and not claimed by this file until its evidence is attached to the
commit it names:

- **The version and the date** (step 1): `pyproject.toml`, the change log's
  `[0.31.0]` heading, both front pages, the guide's cover and `CITATION.cff`.
- **The full tier-1 suite over the release commit.** Runs over earlier commits of
  this release do not stand in for it.
- **The review attestation over the release range** (step 2) and **the
  independent reading of GitHub main** on the pushed commit (step 4).
- **CI green on the commit to be tagged**, including the release workflow's single
  build and its clean installed-wheel jobs.
- **The tag, its PyPI publication, the release object and the Zenodo version
  DOI** (steps 5 to 10). The v0.31.0 archive row is owed in the change log.

## What this release carries

In one line each:

- **The clocked wheel's sections.** A `qsteady_rotor` wheel deletes, turns,
  re-initialises, re-creates in frames held at the clocking, updates and
  exports its section distributions at every clocking
  (`<point>_qs<i>_sloads.txt` and the others); its sections table holds every
  clocking.
- **The rotor-table mean and the rotor state.** A wheel's rotor-table row is
  the mean of its clockings' force and moment, every coefficient from those
  mean loads; `_qs_avg.csv` states `CT_ROTOR`, `CT_PROPELLER`, `MU_ROTOR`,
  `LAMBDA_C`, `LAMBDA_I` and `CHI_DEG`.
- **The correction machinery, not validated.** `[qsteady_correction]` routes
  `table` and `sector_offset` from `inputs/calibrations/<id>.toml`, corrected
  files beside the raw ones, the Theodorsen and Sears diagnostic, route 1 as
  a correction and route 3 refused with their reasons.
- **The harmonic and per-revolution products.** `sections/<point>_harmonics.csv`
  per rotor point; `probes/<point>_per_revolution_<ALIAS>.csv` per rotor of an
  unsteady point, with `[per_revolution] drift_limit_pct`.
- **The rotor table's in-plane coefficients.** `CN`, `CS`, `CMN`, `CMS` per
  rotor as its last four columns.
- **One home for each rule.** The typed quasi-steady record
  (`cases.qsteady.read_qsteady_record`), a blade's azimuth (`post.axes`), the
  thrust and torque shares along the rotor's axis (XZ and XY cuts read), the
  workspace's matrices for the POL census, storage and sync
  (`workspace.matrix_files`), J of a `qsteady_rotor` row from the rotor
  block's own diameter, and one shared FSI coupling step.
- **Field operations.** `pyfs-workspace field mirror|move|subtract|time-mean`.
- **The guides.** Eight decks, `pyfts-guide-00` to `07`, guide 00 the
  overview, each with its PDF Title.

## What the licensed campaign measured, and what it did not

All on FlightStream 26.124 (build 8172026), short confirmations only.
[RPT-094](reports/RPT-094_wheel-clockings-thrust-pct-on-26124_2026-09-29.md)
confirms the clocked wheel: sections at every clocking at the same 30
stations, the XY cut's `Fx`, `Fz` and `Fz Offset` matching the blade's loads
to about 2 per cent, `THRUST_PCT_K_GT_0_1` and `TORQUE_PCT_K_GT_0_1`, the
rotor table as the mean of 3 clockings, the rotor state and the harmonic
product. [RPT-095](reports/RPT-095_custom-freestream-unsteady-rotor-on-26124_2026-09-29.md)
confirms a custom free stream on `unsteady_rotor`, read by the solver and
equal to the constant control to the fifth decimal. The 0.30.0 confirmations
that fixed that release's four defects are in this tree as well:
[RPT-090](reports/RPT-090_qsteady-rotor-sector-fsi-on-26124_2026-09-29.md)
(the `qsteady_rotor` sector with FSI),
[RPT-091](reports/RPT-091_qsteady-rotor-wheel-at-aoa-on-26124_2026-09-29.md)
(the wheel at an angle of attack, whose rotor numbers are a record of
clocking 0),
[RPT-092](reports/RPT-092_fixed-wing-fsi-on-26124_2026-09-29.md) (the fixed
wing's FSI) and
[RPT-093](reports/RPT-093_aeroelastic-coupling-on-26124_2026-09-29.md) (the
aeroelastic coupling toolbox). The long licensed campaigns were not run for
this release.

## What is NOT done, and is not being hidden

- No correction route is validated; which route to recommend, and its
  numbers, is research's.
- The unsteady harmonic product is not confirmed on a licensed run: RPT-095's
  row wrote no sections series, and such a point is now a named skip.
- The 2 per cent between RPT-094's strip integrals and the blade's loads is
  not attributed to a cause.
- FSI on `unsteady_rotor` stays refused: on 26.124 the morph of a mapped
  rotating blade replaces its rotation (RPT-025, RPT-093).
- The quasi-steady wheel stays valid for an isolated, axisymmetric rotor.
- `ROTOR_SHEDDING` stays refused; direction control for the relaxed wake is
  not part of this release.
- The shipped-surface guard's exempt count reads 167, its cap: a further
  exempt file needs the author's decision first.
- The Zenodo version DOI of v0.31.0 is owed one commit after the tag.
