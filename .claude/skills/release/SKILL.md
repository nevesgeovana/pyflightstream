---
name: release
description: Cut a pyflightstream release, checking definition of done, evidence currency, SemVer bump, changelog, and tag. Public releases add the invariants audit.
side-effects: cuts the version tag, which triggers the PyPI publish workflow (an OIDC trusted publish that reading cannot undo)
---

# release

Cut a release with the evidence checks that make it trustworthy. This
is a READ-DO checklist: execute each pause point in order, confirm,
then move on. References for the practices: docs/srs/standards.md.

## Pause point 1: state of the tree

1. Definition of done (CLAUDE.md) holds across the open work.
2. Tier 1 green in CI on the release commit's parent. Note what this
   does and does not buy, because it was read as more than it is: the
   parent is the commit the release starts FROM, so this item cannot
   fail for any of the code being released. It says the ground was solid
   before the work began. The check that covers the work itself is pause
   point 4 item 4, and at v0.7.0 this item was satisfied while that one
   was violated.
3. Compat and physics reports current for the flagship FlightStream
   version; anything stale is either refreshed or named in the
   release notes as a known gap.
4. Run the `audit` skill (full scope) and close or plan every finding.
   A release never ships over an unread audit.
5. **The release's LAST STEP carries its evidence.** For 0.8.x that step
   is FlightStream 26.123, and it is last by the author's sequencing:
   everything else planned for the release happens first, and the
   release does not go out until that build is evidenced. The check is
   `pytest tests/test_release_readiness.py`, run with `-s` so the absent
   count prints. It refuses on PRESENCE of four committed artefacts, the
   registration with its build number, the documented pass in a chapter
   YAML, a probe report that verified something, and a physics report
   with at least one case, and it names the step in its refusal rather
   than reading as one item among many.

   Two things it deliberately does NOT do. It asserts no threshold on
   the commands the golden records as absent on that build (it states
   its own count; do not repeat the digit here, it went stale twice),
   because
   at least one of them is legitimately absent and no agreed number
   exists; the count is printed for a person to read. And it is scoped
   to the milestone whose last step this build is, so it does not refuse
   0.9.0 for an artefact that release never named.
6. Deprecation deadline: no shim survives past its recorded removal
   version and every shim warning states that exact version; both are
   enforced mechanically by the tier 1 guard
   (tests/test_deprecation_deadline.py over the
   pyflightstream._deprecations ledger), so a green suite on the
   version-bump commit is the check. When the guard fires, delete the
   shim, its tests, and its ledger entry in the same commit, or move
   the promise deliberately and document the extension.

## Pause point 2: version, everywhere at once

The version-bearing files move together, in one commit:

1. `pyproject.toml` version (SemVer; package versioning decoupled
   from FlightStream versions).
2. `CITATION.cff` `version` and `date-released`; validate the file
   (`cffconvert --validate` when available, else the schema by eye).
3. The user guide title version in `guide/pyflightstream_user_guide.tex`,
   together with its content refresh for the release (helper and
   command counts, import paths, CLI list).
4. `pytest tests/test_metadata_currency.py` passes after the bump.

## Pause point 3: changelog promotion

Rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, then recreate
an empty `## [Unreleased]` section above it (the currency test
requires it to exist). Release notes for the tag derive from this
entry: human-readable, not a commit log. The entry names its
API-surface delta explicitly (library-review adoption, 2026-07-23):
new public names, incompatible changes, and deprecations each get a
line or an explicit "none", so a reader can judge upgrade risk from
the changelog alone.

## Pause point 4: build, attest, and tag

1. Build sdist and wheel from a clean checkout; inspect the contents
   once (no private material, no generated docs).
2. **Run the release job's own checks against the built wheel, locally,
   before the tag.** Install the wheel into a venv that has nothing else
   in it, with the extras named by the `Install the built wheel, not the
   source` step of `.github/workflows/release.yml` (that file is the single home of the
   set; do not copy the list here, read it there, and install exactly
   what it names and nothing more, because the extras that are ABSENT
   are what this run measures). Then run, from the repository checkout
   with that venv active and no editable install of this package in it,
   both of the job's commands and not just the first:

   ```
   pytest
   pytest README.md docs -W error::pyflightstream._errors.PyflightstreamWarning
   ```

   The tests are not in the wheel, which is why the checkout is needed.
   A pass is the suite green; a FAILURE or a COLLECTION ERROR here is
   the class of defect this step exists for. It reproduces one leg of a
   four-leg matrix, so treat it as a smoke test rather than as the job.

   Rebuild the wheel first if anything was committed since the last
   build, or this tests the previous one.
3. Role-review the whole release diff with the specialist agents (the
   `role-review` skill, not paraphrased manual checks) and drive every
   finding to fixed or registered, then write BOTH attestations,
   naming the tag ref so the record covers the ref actually pushed (the
   writer stamps HEAD by default, and a tag that sits behind HEAD would
   never become covered):
   ```
   python .claude/hooks/write_attestation.py review architect,qa,vv,tech-writer,api-designer vX.Y.Z
   python .claude/hooks/write_attestation.py release architect,qa,vv,tech-writer,api-designer vX.Y.Z
   ```
   The release attestation is what the git-push gate
   (`.claude/hooks/role_review_gate.py`) requires for a version-tag
   push, that is `git push origin vX.Y.Z`; without it the release push
   is blocked. The blanket forms (`--all`, `--mirror`, `--tags`,
   `--follow-tags`) are refused outright as unscopable, so a release is
   pushed by naming the tag, never with `--tags`. This pause point
   exists because a past release shipped paraphrased checks instead of
   the agents.
4. Annotated tag, and **push it only once CI has actually reported green
   on the commit the tag names**. Not "green last time you looked", and
   not "green on the parent": on that commit, concluded, on the remote.
   Push the branch, wait for the run to FINISH, read it, then move the
   tag and push it.

   This item used to be four words, and the four releases that have been
   measured show it decaying rather than being obeyed. Gap between the
   branch CI run and the tag push: fourteen minutes at v0.4.0, forty one
   at v0.5.0, thirteen seconds at v0.6.0, fifteen at v0.7.0. A CI run
   here takes about four and a half minutes, so the first two had an
   answer to read and the last two did not. v0.6.0 shipped over the same
   silence and survived because CI turned out green; v0.7.0 did not, and
   the tag is the one step in this checklist that cannot be retracted.

   It is no longer only a sentence. The push gate itself
   (`.claude/hooks/role_review_gate.py`, kit 0.2.18) refuses a
   version-tag push while that commit's CI is red, still running,
   unknown or unreachable (INC-20260810-2140-shared). If it denies, the
   answer is to wait or to fix, never to work around it: it is asking
   the question this item was always supposed to ask. A repository-owned
   bridge hook held that rule for one day and was deleted on 2026-08-11
   in the commit that vendored the shared body; a `[ci-config]` refusal
   means `.claude/hooks/ci_state.py` is missing rather than that the
   gate is broken.

   AND MIND THE LOOP A DENIAL PUTS YOU IN, because it crosses back into
   item 3 and nothing else says so. Fixing CI means a new commit, and a
   commit made after attesting re-arms the role-review gate, so the
   attestations written in item 3 no longer cover what you are pushing.
   After the fix is green and the tag has moved onto it, go back to item
   3, re-run the reviewer passes over the new work, and write BOTH
   attestations again naming the tag, then return here. Satisfying this
   gate and then being refused by the other one is the expected
   sequence, not a sign that something is wrong.

## Pause point 5: public releases only

1. Invariants audit with the repository-wide guards: no manual
   content, no AGPL-derived code, no proprietary data, no employer
   or internal-toolchain names.
2. Publish to PyPI through trusted publishing (OIDC), never a manual
   token upload. This is mandatory: pushing the annotated `vX.Y.Z` tag
   (pause point 4) triggers `.github/workflows/release.yml`, which
   builds, verifies the tag matches `pyproject.toml`, and publishes
   from the `pypi` GitHub environment with a short-lived OIDC token.
   Do NOT run `twine upload` by hand. Watch the Release workflow to
   green (`gh run watch`), then confirm the PyPI page renders the new
   version. Prerequisite, one-time per project: a PyPI trusted
   publisher matching `.github/workflows/release.yml` (that file is the
   single home for the workflow name and the environment) and the
   GitHub environment it names must exist; if a tag push does not
   publish, that setup is missing, not the workflow.
3. GitHub release with the changelog entry; confirm the Zenodo DOI
   minted and CITATION.cff still matches what shipped.
4. Install the published package in a fresh venv and check
   `pyflightstream.__version__` reports the release.

## Outputs

Tagged release, promoted changelog, synchronized citation metadata,
refreshed guide; PyPI upload and DOI in the public phase.
