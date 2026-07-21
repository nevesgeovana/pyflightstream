---
name: release
description: Cut a pyflightstream release, checking definition of done, evidence currency, SemVer bump, changelog, and tag. Public releases add the invariants audit.
---

# release

Cut a release with the evidence checks that make it trustworthy.

## Steps

1. Check the definition of done (CLAUDE.md) across the open work.
2. Verify Tier 1 is green in CI, and that compat and physics reports are
   current for the flagship FlightStream version.
3. Bump the SemVer version in `pyproject.toml` (package versioning is
   decoupled from FlightStream versions).
4. Assemble the changelog from merged changes.
5. Build the sdist and wheel; tag the release.
6. Public releases additionally audit hard invariants 1, 2, and 5 with
   the repository-wide guards (no manual content, no AGPL-derived code,
   no proprietary data) before pushing the tag, then upload to PyPI.

## Outputs

* Tagged release and changelog; PyPI upload in the public phase.
