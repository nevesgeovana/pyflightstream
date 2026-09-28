# 0.29.0 release sequence and pending evidence

**Target: 0.29.0. This record does not declare the release ready or published.**
The documentation worktree inspected for this update is
`1f5b7686fd70b26b1b06543f118d506cff704f82`; its package and citation versions are
`0.29.0.dev0`. Version changes, final metrics, CI, review of the pushed release
commit, the tag, PyPI and the Zenodo version DOI remain pending in this record.
Attach evidence for the final target commit before changing a gate to complete.
A successful intermediate check is evidence only for the commit it checked.

The approved release centers on complete setup and boundary-condition access,
didactic standard setups and guidelines, workspace FSI, post-processing through
probes, optional Excel files synchronized by the Python CLI, and usable runtime
and post-processing logs. The [0.29 migration guide](docs/migrating-to-0.29.0.md),
[setup guide](docs/setup-standards.md), [boundary guide](docs/boundary-conditions.md),
[Excel guide](docs/excel-matrices.md), [FSI guide](docs/fsi-workspace.md) and
[sampled-field guide](docs/sampled-fields.md) describe their public contracts.

The ownership of inputs must remain consistent: mesh-invariant geometry belongs
beside the mesh, simulation settings in the setup, and variable physical
conditions in MATRIX. Excel uses a macro-free workbook and CLI synchronization;
VBA refinement is outside this release. The normal volume-section workspace
path uses probes; automatic inventory of manual native section indices is
outside the accepted G39 scope. Preserve these boundaries when reconciling the
release notes, public architecture and evidence.

## Evidence available now

[RPT-085](reports/RPT-085_native-workspace-evidence_2026-09-27.md) records completed,
bounded native observations on FlightStream 26.124 build 8172026:

- T29: the synthetic wing and rotor routes agree over six printed time steps.
  This is not convergence, full-revolution or complete saved-state equivalence.
- T33 / G39: an existing native section and surface mesh survive probe sampling;
  the actual CSV-to-VTK product is checked, with its five-decimal CSV limit.
  Manual native indices remain manual.
- T15: uniform inlet/outlet changes produce local response. Profile persistence
  and a nonuniform field are measured; interpolation and the sign convention
  remain unproved.
- T26: two steady actuators and a supplemental actuator with rotating geometry
  produce local field effects. This is not rotor-performance validation.
- Rotor-induced velocity blending: the 0.25/0.75 pair has identical exported
  results and 837 printed iteration lines. Its operational effect remains
  inconclusive.

These observations do not turn documented-only commands into verified commands.
The remaining setup, FSI and research obligations must be reconciled with their
own evidence. [RPT-081](reports/RPT-081_typed-boundary-and-base-region-operations_2026-09-27.md)
retains the earlier no-solve observations.

## Final gate ledger

PENDING means that final-target evidence has not been attached to this document.
It does not erase successful intermediate work. No count from 0.28.0 below may
be reused as a 0.29.0 measurement.

| Gate | Current record | Evidence required before completion |
| --- | --- | --- |
| Approved scope and known limitations | PENDING final reconciliation | Each approved item maps to implementation and evidence, or an explicit accepted limitation; additional ideas remain backlog |
| Implementer checks and independent internal review | PENDING final range | QA, V&V, architecture, API and technical-writing dispositions on their declared ranges; corrections checked by a different author |
| Source checks and offline tests | PENDING final commit | Actual Ruff, formatting, mypy and required test results with target SHA; counts and exits taken from receipts |
| Current module/error recount and documentation currency | PENDING settled tree | Recount at the release commit; synchronized tallies, guides, examples and public architecture |
| Package identity and metadata | PENDING release commit | Version 0.29.0, dated changelog, front pages, guide cover and CITATION.cff agree |
| Build and installed-wheel gates | PENDING final artifacts | One sdist/wheel build, recorded digests, clean installed-wheel checks and optional-feature checks |
| Pushed-main independent review and CI | PENDING reviewed remote SHA | External reading of the pushed commit, findings disposed, CI green on that exact commit |
| Annotated tag and PyPI publication | PENDING | Tag v0.29.0 on the reviewed commit; release workflow succeeds and published wheel identity is verified |
| GitHub release and Zenodo archive | PENDING | Release object, minted version DOI, citation row and publication checker result |
| Post-release development identity and research | PENDING | Next development version after the archive row; released-wheel research using generated standards, including the approved FSI workspace cases |

## Execute in this order

1. **Settle scope, implementation and evidence.** Complete the required local
   checks and independent review dispositions. Keep inconclusive scientific
   claims visibly inconclusive. Preserve the input ownership and macro-free
   Excel decisions above. Update public architecture and guides to the actual
   integrated behavior.

2. **Prepare the release commit.** Set the package version to 0.29.0 only in the
   release commit. Date its changelog section and move the behavior that ships
   out of Unreleased. Update README.md, docs/index.md, the guide cover and
   CITATION.cff together. Its version, date-released, release/development text
   and both tally sentences must agree. Measure the settled-tree module/error
   recount and update its current record, traceability expectations and the
   current release section; do not overwrite a previous release's measurement.
   Keep the v0.29.0 archive DOI explicitly **owed** under Unreleased -> Owed until
   it exists. A dated release section is the wrong place for that debt.

3. **Check the final tree and build artifacts.** Attach the actual source,
   documentation, offline and package-check receipts to their exact SHA.
   The [release workflow](.github/workflows/release.yml) builds once, tests the
   installed wheel in clean jobs and checks its digest before publication.
   Local checks do not substitute for those artifact gates. This step records
   measured outcomes; it does not prefill them from earlier releases.

4. **Complete internal review and push the reviewed main commit.** Each lens
   records its range and finding dispositions. Review scope identifiers must
   contain resolved commit SHAs. Keep the pushing worktree's attestation aligned
   with that range. No tag yet.

5. **Obtain the independent reading of GitHub main before the tag.** Provide a
   clone of what GitHub serves, and record the exact remote commit. Fix or
   explicitly register each finding; any fix must be pushed and the affected
   review/checks completed on the changed target. CI must be green on the commit
   to be tagged. An earlier development-wheel review does not replace this step.

6. **Create the annotated v0.29.0 tag on that reviewed commit and push it.**
   Tag push triggers the trusted-publishing workflow for PyPI. Record the
   successful workflow, artifact digest and published package identity; a tag
   alone does not establish successful publication.

7. **Create the GitHub release object for v0.29.0 with its actual notes and
   limitations.** The Zenodo webhook uses the release object, not just the tag.
   Read the newly minted version DOI from the archive record. Neither the
   release object nor that DOI is asserted complete here.

8. **Record the archive and verify publication.** Add the version DOI to
   CITATION.cff and remove the v0.29.0 Owed entry in the same post-tag commit.
   Move the development tree to the next development version in that commit.
   Run the online [publication checker](scripts/check_release_published.py) and
   retain its result. An offline check cannot confirm PyPI or Zenodo.

9. **Run the approved research against the released wheel.** Use the generated
   standard setups and include the FSI workspace cases. Record the exact package,
   solver build, input identities, observed results and limits. This post-release
   work is separate from the release-cut gates and is not closed by this
   documentary update.

## Historical 0.28.0 record

The following is the earlier checklist and its dated measurements, preserved
verbatim. Its commands, open items and counts describe that historical snapshot;
they are not the active release instructions or evidence for 0.29.0. In
particular, an item marked owed there is not a new claim about its current
publication status. The active sequence is the one above.

<details>
<summary>Read the preserved 0.28.0 checklist and measurements</summary>

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


</details>
