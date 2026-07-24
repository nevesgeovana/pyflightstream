---
name: release
description: Cut a pyflightstream release, checking definition of done, evidence currency, SemVer bump, changelog, and tag. Public releases add the invariants audit.
# Side effect: cuts the version tag, which triggers the PyPI publish workflow. Never model-invoked.
disable-model-invocation: true
---

# release

Cut a release with the evidence checks that make it trustworthy. This
is a READ-DO checklist: execute each pause point in order, confirm,
then move on. References for the practices: docs/srs/standards.md.

## Pause point 1: state of the tree

1. Definition of done (CLAUDE.md) holds across the open work.
2. Tier 1 green in CI on the release commit's parent.
3. Compat and physics reports current for the flagship FlightStream
   version; anything stale is either refreshed or named in the
   release notes as a known gap.
4. Run the `audit` skill (full scope) and close or plan every finding.
   A release never ships over an unread audit.
5. Deprecation deadline: no shim survives past its recorded removal
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
2. Role-review the whole release diff with the specialist agents (the
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
3. Annotated tag; push with CI green.

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
