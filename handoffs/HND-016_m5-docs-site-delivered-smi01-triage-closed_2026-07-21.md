# HND-016: M5 docs site delivered, SMI-01 triage closed (2026-07-21)

## 1. Context

M5 opening session (PLN-009 plus PLN-010 layer 2) against STATUS.md.
Delivered the whole scope: the mkdocs site with the command reference
and the compatibility matrix generated from the database at build time,
the steady polar example rewritten from its M0 placeholder and executed
on the real solver, SRC-725 registered as the 26.1 manual source id,
and, en route, the SMI-01 CMy triage (PLN-013) closed. Suite at 179
tier 1 tests, ruff and format clean, mkdocs build --strict green.

## 2. Decisions

1. Single rendering source (PLN-009 requirement): `reference.py` holds
   shared extraction helpers; the existing HTML page (layer 1, now the
   offline fallback) and the new markdown generators (layer 2, the
   site) both sit on them. The site pages are generated at build time
   by mkdocs-gen-files through `scripts/gen_docs_pages.py` and are
   never committed, so site and database cannot drift.
2. mkdocs-gen-files and mkdocs-literate-nav joined the dev extras
   (both MIT, public-libraries policy). The literate-nav input file
   (`reference/SUMMARY.md`, generated) is kept out of the rendered
   site by a small mkdocs hook (`scripts/docs_hooks.py`), because
   `exclude_docs` cannot see gen-files virtual files.
3. The compatibility matrix renders every command against every
   registered version with status spans, per-version evidence counts,
   and the manual edition per version (SRC-003, SRC-725); cells
   without evidence stay empty on purpose (26.000 column: 116 empty).
4. The example is rendered into the site by `percent_script_markdown`
   (percent-format cells to prose plus fenced code), an in-house ~40
   lines instead of mkdocs-jupyter: the docs CI has no solver, so
   executed-notebook rendering buys nothing today, and the mkdocs
   plugin ecosystem is in flux (see 6). Revisit if executed outputs
   are ever wanted on the site.
5. The example takes the executable as an explicit argv path (never an
   environment variable), mirroring the LocalExecutor rule; without it
   the dry build and the didactic 26.0 refusal still run anywhere.
6. Toolchain finding: the freshly released versions of both nav
   plugins depend on and advertise ProperDocs, a fork of MkDocs by its
   last active maintainer (public governance dispute, February-March
   2026; Material endorses the fork). The advertisement prints to
   stderr and does not break the strict build. No migration decided in
   this session; Geovana's call, noted as an open question toward
   v0.1.0.
7. PLN-013 verdict: the SMI-01 CMy movement is a deterministic
   solver-side change between builds 5012026 and 7012026. Both reruns
   are bit-identical to the capstone values, the opened .fsm sha256 is
   identical, and 28_B has a single boundary, so noise and case
   sensitivity are excluded. Reference untouched; the cross-version
   WARN stands by design (`TRI-SMI01-CMy_2026-07-21`).

## 3. Changes persisted

* `src/pyflightstream/reference.py`: shared extraction helpers,
  `markdown_reference_pages`, `markdown_compatibility_matrix`,
  `percent_script_markdown`; HTML layer unchanged in behavior.
* `src/pyflightstream/versions.py`: `manual_editions()` accessor.
* `scripts/gen_docs_pages.py` and `scripts/docs_hooks.py`; mkdocs.yml
  with gen-files, literate-nav, hooks, nav, extra CSS;
  `docs/stylesheets/extra.css`; `docs/index.md` rewritten for M5.
* `examples/steady_polar.py`: real example (synthetic NACA 0012 wing,
  7 validated scripts, 26.0 refusal demo, optional execution);
  executed on 26.120 build 7012026, all points converged, lift slope
  4.83 per rad against the finite-wing anchor 5.03 (matches PHY-01).
* SRC-725 in `_meta.yaml` manual_editions and in all 28 version notes
  formerly citing "FS 26.1 manual" (commit 2c8fb0d).
* Tests 174 -> 179 (markdown pages coverage and navigation, matrix
  honesty, percent-script conversion).
* `reports/physics/PHY-26100_2026-07-21_smi01-triage-rerun`,
  `PHY-26120_2026-07-21_smi01-triage-rerun`, and
  `TRI-SMI01-CMy_2026-07-21.md` (PLN-013 evidence and verdict).
* STATUS.md (M5 Done), plan.csv (PLN-009/010/013 done), logbook row,
  this handoff.

## 4. Open questions and contradictions

New: whether to follow the MkDocs-to-ProperDocs fork before the public
release (decision 6; the nav plugins already pull it in as a
dependency). Carried: PLN-012 (four broken commands); xarray gate at
`post/`; SMI genericization option; SWEEPER manual pass; probe specs
for the import trio and SET_ANALYSIS_SYMMETRY_LOADS; 26.100 Tier 2
backfill probing at v0.2+; getting-started and campaign tutorial pages
(listed as planned on the docs home).

## 5. Single highest-value next action

v0.1.0 (private tag): run the release skill's definition-of-done and
evidence-currency checks over the delivered M0..M5 chain and cut the
tag; en route, decide the ProperDocs question if the release checklist
touches the docs toolchain.
