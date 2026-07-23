---
name: release
description: Cut a pyflightstream release, checking definition of done, evidence currency, SemVer bump, changelog, and tag. Public releases add the invariants audit.
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
   version (check the shims by hand until the tier 1 deadline-guard
   test lands), and every version string inside a shim's warning
   matches the version being released.

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

## Pause point 4: build and tag

1. Build sdist and wheel from a clean checkout; inspect the contents
   once (no private material, no generated docs).
2. Annotated tag; push with CI green.

## Pause point 5: public releases only

1. Invariants audit with the repository-wide guards: no manual
   content, no AGPL-derived code, no proprietary data, no employer
   or internal-toolchain names.
2. Upload to PyPI (tokens per the author's keyring setup); verify the
   PyPI page renders.
3. GitHub release with the changelog entry; confirm the Zenodo DOI
   minted and CITATION.cff still matches what shipped.
4. Install the published package in a fresh venv and check
   `pyflightstream.__version__` reports the release.

## Outputs

Tagged release, promoted changelog, synchronized citation metadata,
refreshed guide; PyPI upload and DOI in the public phase.
