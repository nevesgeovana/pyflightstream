# HND-033: post-release credential hygiene, session line closed

Date: 2026-07-22. Final block of the HND-029..032 session line; no
repository code changed in this block (machine-local credential work
plus this closing ritual). The next-session resume prompt lives at
`_private/inbox/ContinuarPosPublicacao.md` (local-only, at the
author's request).

## What happened

* PyPI tokens moved to least privilege on the author's machine, at
  her request and with her performing every secret-handling step in
  her own terminal: the account-scoped token used for the v0.2.0
  upload was replaced by project-scoped tokens, stored in the Windows
  keyring under `upload.pypi.org/legacy/` as username `__token__`
  (pyflightstream, twine's default slot) and username `itaca` (the
  ITACA release one-liner reads it into TWINE_PASSWORD). The
  redundant entry under her username was deleted.
* Both slots verified functionally by idempotent re-uploads of
  already-published, byte-identical artifacts (authentication and
  project scope exercised, no state changed on PyPI). Revocation of
  the old account-scoped token is visible only in her PyPI token
  list and was left to her visual check.
* No secret entered the session at any point: tokens were pasted
  only into her terminal, and the one in-keyring move (copying the
  mis-named entry to `__token__` during the release) was done by a
  script that never printed the value.

## Session line summary (HND-029..033, one day)

WP2/WP5/WP6 offline; WP7 near-rigid pilot (M6 exit met, RPT-006);
beta(r) embedding and the soft pilot; the rotor-morphing solver
defect established with a controlled probe series (RPT-007,
two-way rotor FSI solver-blocked, vendor package ready in
`_private/vendor/`); v0.2.0 public on PyPI and Zenodo
(DOI 10.5281/zenodo.21482925). Suite at 321, CI green throughout.

## Pending (unchanged from HND-032)

1. Author sends the vendor email (`_private/vendor/`).
2. PLN-019 Tier 2 sweep for the FSI families.
3. Optional static-wing two-way pilot; Tier 3 registration of the
   near-rigid loop-mechanics regression.
4. v0.3+ line; ProperDocs decision for public docs hosting.
