---
name: audit
description: Retrospective repository health audit. Sweeps committed files for staleness, checks the repo against the adopted external guides, reviews implemented code for improvement opportunities, and turns every finding into an update, a deletion, or a plan item. Run periodically and before every release.
argument-hint: "[docs|code|full]"
---

Scope: `$ARGUMENTS` (default `full`). This is a DO-CONFIRM checklist
(the work is done from expertise, then verified block by block), per
the checklist-design principles recorded in docs/srs/standards.md.
Findings follow one rule, from Google's documentation practice:
**update or delete, never leave-for-later**. A finding that cannot be
fixed in-session becomes a `_private/plan.csv` item with an owner
decision named.

Output: a dated report in `_private/progress/` (the author reads it on
mobile) listing every finding with file:line evidence, what was fixed
in-session (with commits), and what became a plan item. Fixes to
committed files land as one commit per concern, pushed with CI green.

## Pause point 1: metadata and version truth

1. `pytest tests/test_metadata_currency.py` passes (version agreement,
   Unreleased section, SRS id uniqueness).
2. Grep the repo for version literals (`0\.\d+\.\d+`) outside
   pyproject/CITATION/CHANGELOG; each hit either derives from metadata
   or is a dated historical record. Hardcoded current-version strings
   are findings.
3. Shipped strings naming a future version (for example a deprecation
   citing "v0.3.0") must have that version present in the CHANGELOG
   (Unreleased counts) or the claim is unanchored.

## Pause point 2: public-surface currency (docs sweep)

Compare each claim against the code, not against memory:

1. README.md: status line, feature list, extras, CLI table, folder
   map, dev-setup extras versus `[project.scripts]`, `pyproject.toml`
   extras, and the CI install line.
2. docs/index.md and mkdocs nav: dead or missing links; every example
   in `examples/` renders on the site (`scripts/gen_docs_pages.py`
   EXAMPLES list); planned-next items that already shipped.
3. CONTRIBUTING.md: setup, tier claims, style claims versus the
   actual guards and tests.
4. CHANGELOG.md Unreleased: does it cover everything user-visible in
   `git log` since the last tag? Cross-check with
   `git diff --stat <last-tag>..HEAD -- src/`.
5. docs/srs/: requirement statuses versus reality (anything marked
   implemented must name evidence that still exists; anything shipped
   this cycle must appear as a requirement or an amendment).
6. guide/*.tex: version claims, helper and command counts, import
   paths, CLI list. The guide refreshes per release; between releases,
   findings here feed the release plan item rather than in-session
   fixes.
7. Single-home rule (NFR-11): any fact stated in two places where
   neither generates from a source is a finding; converge on one home
   and link.
8. `.claude/skills/*`: stale paths, counts, milestone maps, folder
   names inside every skill file.

## Pause point 3: external-guide conformance

Check against the adopted references (docs/srs/standards.md carries
the list and URLs):

1. pyOpenSci editor-in-chief initial checks, as a self-audit
   (docs sufficient without installing, README completeness, API
   docs, CI-run tests, license, release matching the tag, AI-use
   disclosure).
2. Scientific Python Development Guide spot-checks (packaging,
   testing, docs patterns); run `sp-repo-review` when available in
   the environment and translate red checks into findings.
3. PyPA pyproject guidance: classifiers, well-known URL labels,
   license metadata.
4. Aspirational-backlog review: for each backlog row in
   docs/srs/standards.md, has its gate cleared? If yes, propose the
   adoption as a plan item.

## Pause point 4: implemented-code review (scope `code` or `full`)

Not a bug hunt (Tier 1 and /code-review own that); this pass looks
for structural improvement opportunities in what already shipped:

1. Deprecation debt: shims and deprecated paths past their announced
   horizon (removal is a finding for the next minor).
2. Layering: imports against the CLAUDE.md dependency rule, including
   deferred-import workarounds worth hoisting.
3. Didactic debt: public functions missing numpydoc units/frames,
   error messages naming symptoms instead of causes, modules whose
   top docstring no longer matches their contents (the overview
   renders these live, so a wrong one is public).
4. Duplication worth extracting, dead code, and TODO/seam comments
   whose gate has since cleared (for example a licensed probe that
   has run).
5. Test-shape: new public APIs since the last audit with no direct
   test file, fixtures grown stale relative to the current solver
   output format.

## Closing

Write the report, commit fixes (one commit per concern), push, verify
CI, and register plan items for everything deferred. If the audit ran
clean, say so in the report; an empty findings list from a real sweep
is information, not a formality.
