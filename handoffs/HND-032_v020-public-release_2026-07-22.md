# HND-032: v0.2.0 published on PyPI and Zenodo

Date: 2026-07-22 (UTC; fourth block of the HND-029..031 session line).
Author's instruction: publish the latest version on PyPI and Zenodo
mirroring the ITACA release flow. The vendor email and slides for the
morphing defect were also prepared this block (local-only,
`_private/vendor/`).

## What shipped

* Release process per the `/release` skill: definition of done
  checked (CI green, compat and physics reports current for 26.120,
  new commands cited, pending probes tracked as PLN rows), version
  bumped 0.1.0 to 0.2.0, changelog assembled from the 51 commits
  since v0.1.0 (M6 FSI, M7 far-field, Tier 3 growth, the RPT-004..007
  findings, the known rotor-morphing limitation), `CITATION.cff`
  added mirroring ITACA's.
* Public invariants audit (1, 2, 5) clean: zero tracked
  pdf/ipynb/_private files, naming guard green in the suite, AGPL
  sweep clean (the one mention is the clean-room policy note in
  script/helpers.py), sdist inspected entry by entry (126, no leaks).
* Artifacts: sdist and wheel built and twine-checked; tag v0.2.0
  annotated and pushed with CI green; GitHub release published
  (drafted first, published only after the author enabled the Zenodo
  integration so the webhook would fire).
* PyPI: https://pypi.org/project/pyflightstream/0.2.0/ (uploaded
  with the ITACA venv's twine; the author's account-scoped token was
  stored in the Windows keyring under her username and was copied
  inside the keyring to the `__token__` entry twine requires, the
  secret never entering the session); resolution from the public
  index verified with pip download.
* Zenodo: DOI 10.5281/zenodo.21482925 minted from the GitHub release
  via the integration the author enabled.

## Decisions and notes

* Version 0.2.0 (minor): large additive surface since 0.1.0, no
  breaking API removals.
* The GitHub release was created as a draft and published only after
  the Zenodo toggle, because the webhook fires on publish and would
  otherwise miss the release.
* Suggested to the author: now that the project exists on PyPI,
  replace the account-scoped token with a project-scoped one (and the
  redundant keyring entry under her username can be removed).

## Pending

1. Vendor contact on the rotor-morphing defect (email and slides
   ready in `_private/vendor/`; Geovana sends).
2. PLN-019 sweep; PLN-020 solver-blocked; static-wing two-way pilot
   optional.
3. v0.3+ line as re-scoped in STATUS (remaining PHY cases, backfill
   probing, declarative matrix successor).
4. Docs hosting for the public phase (the ProperDocs question) is
   still open; the PyPI page links the repository.
