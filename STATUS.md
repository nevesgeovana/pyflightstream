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
| M3 | Tier 2 probe harness, first compat report for 26.120, apply-compat | Committed compat report; statuses promoted | Done 2026-07-21 (pilot HND-010, full sweep HND-011: `reports/compat/CMP-26120_2026-07-21_full`, 64 verified, 4 broken, 44 unprobed with reasons, 68 promotions) |
| M4 | PHY-01/02 plus version-comparison suite (synthetic committed, SMI local) | Committed physics report | Started 2026-07-21 (exit criterion met by PHY-01: `reports/physics/PHY-26120_2026-07-21` and `_banded`, HND-012; PHY-02 and version comparison pending) |
| M5 | mkdocs site, command reference and compatibility matrix generated from the database, steady polar example | Docs build strict; example runs | Planned |
| v0.1.0 | Tag, private | All above green | Planned |
| v0.2+ | Remaining PHY cases, 26.000/26.100 backfill probing, declarative matrix successor, public release, PyPI | Public checklist (invariants audit) passes | Planned |

## Current focus

M4 is open and PHY-01 is closed end to end (PLN-008 started, HND-012):
the mesh-import family (IMPORT, CCS_IMPORT, EXPORT_SURFACE_MESH;
SRC-003 pp.307-308) entered the database, `qa/geometry.py` generates
the committable NACA wing STL, and `qa/physics.py` runs the Tier 3
matrix against banded references (`pyfs-qa physics`), with reference
updates only through the reason-demanding `pyfs-qa update-reference`.
Two real runs on 26.120 build #7012026 are committed under
`reports/physics/`: the polar converged at every point (CL slope
4.83/rad against the AR-8 finite-wing anchor 5.0, CDi at 4 deg 0.0049),
the repeat run was bit-identical, and all 6 metrics pass against the
seeded reference. Single next action: continue PLN-008 with PHY-02
(calibrate SET_ANALYSIS_SYMMETRY_LOADS on the real solver first) and
the version-comparison suite skeleton (synthetic first, SMI local).
Probe specs for the import trio would promote them from documented on
the next sweep. PLN-012 stays parked. The xarray gate (PLN-006) is
decided when `post/` starts. `convert-matrix` CLI wiring can join the
`pyfs-qa` precedent when convenient.

## Open questions

| Question | Waiting on |
|---|---|
| Whether the four broken commands of CMP-26120_full are solver defects or drafted-grammar defects | Manual re-review (PLN-012) |
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
  `ArgSpec.required` flag for optional parameters. At M4 it adds the
  `bool` presence-keyword argument type, keyword_block only, for
  valueless keyword lines (the bare CLEAR of IMPORT, SRC-003 p.307).
* PLN-003 grew from the ~40 estimate to 113 entries because the four
  approved families (author's decision of 2026-07-21) were delivered
  as complete manual chapters; statuses stay evidence-strict, 26.120
  only.
