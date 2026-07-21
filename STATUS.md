# Development status

Single state file for the pyflightstream repository. Updated at every
session close (see the Session protocol in CLAUDE.md). Seeded 2026-07-21.

The design documents (SRS, SAD, Bootstrap Kit) live locally in
`_private/design/` and never enter Git. Their canonical versions live in
the author's research workspace. Public contributors rely on CLAUDE.md,
CONTRIBUTING.md, and the docs.

## Milestones

Milestone map per the Bootstrap Kit (`_private/design/DLV-004`, Section 7).

| Milestone | Content | Exit criterion | Status |
|---|---|---|---|
| M0 | Repo skeleton, pyproject, CI, pre-commit, CLAUDE.md, guards | CI green on empty package | Done 2026-07-21 (root commit acc0e0e, CI green) |
| M1 | `versions.py` (26.XXX scheme), database schema, loader, `_meta.yaml`, core steady commands with citations | Tier 1 database tests pass | Done 2026-07-21 (113 commands, commits a86600d..5233956, CI run 29845795014 green) |
| M2 | Script builder with phase ordering, helpers, `files/` layout, local executor, campaign loop, manifest, loads parser, goldens, legacy matrix reader | End-to-end dry run plus one real local run | Done 2026-07-21 (dry run in the Tier 1 suite, 117 tests; real run CONVERGED, `reports/RPT-001`; legacy matrix reader with convert-matrix closing the content, HND-009) |
| M3 | Tier 2 probe harness, first compat report for 26.120, apply-compat | Committed compat report; statuses promoted | Planned |
| M4 | PHY-01/02 plus version-comparison suite (synthetic committed, SMI local) | Committed physics report | Planned |
| M5 | mkdocs site, command reference and compatibility matrix generated from the database, steady polar example | Docs build strict; example runs | Planned |
| v0.1.0 | Tag, private | All above green | Planned |
| v0.2+ | Remaining PHY cases, 26.000/26.100 backfill probing, declarative matrix successor, public release, PyPI | Public checklist (invariants audit) passes | Planned |

## Current focus

M2 is done (PLN-005 complete): validating script builder with curated
helpers and cross references; managed `files/` workspace with the
`runs.json` manifest; `LocalExecutor` on the documented headless
mechanism; `cases/` SIM model with `campaign.toml`; `run_campaign`
with the six terminal statuses and `LoadsAssessor` on the anchor-based
`results/` parsers; the legacy matrix reader (`matrix_legacy.py`,
FR-10) with `convert_matrix` emitting native TOML that round-trips
through `load_campaign` (FR-11), historical codes preserved in the
case variables (PP-7/FR-12). Evidence: 117 Tier 1 tests, the real
local run CONVERGED on 26.120 (`reports/RPT-001`). Single next
action: start M3, the Tier 2 probe harness (`run-validity` skill
scaffolding, per-command probe scripts with sentinel exports and
effect assertions) toward the first committed compat report for
26.120; newly feasible on this machine, since both executables live
in `_private/exe/`. The xarray gate (PLN-006) is decided when `post/`
starts. Note for M3: `convert-matrix` is a function today; CLI wiring
arrives with the first console entry points.

## Open questions

| Question | Waiting on |
|---|---|
| xarray as a runtime dependency behind the `ResultArray` facade | Geovana's confirmation at M2 (SAD Section 9; noted in `pyproject.toml`) |
| Whether to genericize the SMI name in the repository (currently kept, required by the version-comparison case design) | Open option, Geovana's decision |
| SWEEPER entries are drafted from the worked example (SRC-003 p.406) and the Script Index (p.383); the Sweeper Toolbox chapter (pp.264-279) is not deep-reviewed and may widen the argument grammars | Follow-up manual pass |

## Recorded deviations

* `mkdocs.yml` sits at the repository root, not under `docs/` as in the
  Bootstrap Kit tree, because mkdocs requires the config file outside
  `docs_dir` (recorded at M0).
* Session documentation (this file, `plan.csv`, `logbook.csv`,
  `handoffs/`) is committed, by the author's decision of 2026-07-21. It
  is not part of the Bootstrap Kit tree and must satisfy the same
  guards as the rest of the repository.
* The command schema extends the SAD Section 3.1 vocabulary on manual
  evidence (recorded at M1): a `param_lines` layout for the multi-line
  function grammar of SRC-003 p.279, `int_list` and `float_list`
  argument types for index and sweep value lists, a `control` phase
  for script-control commands exempt from phase ordering, and an
  `ArgSpec.required` flag for optional parameters.
* PLN-003 grew from the ~40 estimate to 113 entries because the four
  approved families (author's decision of 2026-07-21) were delivered
  as complete manual chapters; statuses stay evidence-strict, 26.120
  only.
