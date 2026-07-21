# HND-012: M4 opened with PHY-01 end to end (2026-07-21)

## 1. Context

M4 session (PLN-008) after HND-011 closed M3. Objective against
STATUS.md: build the Tier 3 harness under `qa/` and close PHY-01 (NACA
wing polar) up to the first committed physics report, with PHY-02 if it
fit. Delivered PHY-01 end to end: the mesh-import command family, the
synthetic wing generator, the banded-reference harness, two real runs
on 26.120 build #7012026, the first two physics reports under
`reports/physics/`, and the seeded PHY-01 reference. PHY-02 and the
version-comparison suite stay for the next session, as the objective
allowed. Suite at 161 tier 1 tests, ruff and format clean, mkdocs
strict green.

## 2. Decisions

1. Mesh Import / Export family drafted from SRC-003 pp.307-308:
   IMPORT and CCS_IMPORT as keyword_block, EXPORT_SURFACE_MESH as
   inline with own-line path. The bare CLEAR line of IMPORT needed a
   schema extension: a `bool` argument type meaning presence keyword
   (True emits the bare keyword, False emits nothing), valid only in
   keyword_block; recorded as an M4 deviation in STATUS.md.
2. Synthetic geometry lives in `qa/geometry.py` (invariant 5): NACA
   4-digit analytic contour with the closed-trailing-edge polynomial,
   watertight full-span wing or open-root half wing (the shape MIRROR
   symmetry expects, per the tip-treatment caveat of SRC-003 p.386),
   deterministic ASCII STL. Tests prove watertightness (paired directed
   edges), outward winding (positive divergence-theorem volume), and
   the open root of the half wing.
3. Tier 3 references are package data (`qa/references/*.yaml`) written
   only by `pyfs-qa update-reference`, which refuses an empty reason;
   bands are half-widths, relative for O(1) coefficients and absolute
   for near-zero metrics (CL of the symmetric wing at zero incidence);
   an existing reference keeps its curated bands on update, new metrics
   take the defaults declared in the case's MetricSpec. A reference
   update never shares a commit with code changes (SAD Section 11);
   this session's reference commit is 0e20fbb, reference-only.
4. PHY-01 avoids AIR_ALTITUDE (broken on 26.120 per
   CMP-26120_2026-07-21_full) and sets the fluid state through the
   verified FLUID_PROPERTIES block; a tier 1 test pins this choice.
5. Report discipline mirrors compat: stem `PHY-<digits>_<date>[_label]`,
   YAML plus Markdown, never overwritten. First report (measured,
   no_reference) commits before seeding; the `_banded` report proves the
   comparison loop.
6. Real-run defect found and fixed: the executor sets the solver cwd to
   the case workdir, so a workdir-relative `--script` path resolved
   against itself and FlightStream exited code 0 with zero outputs.
   Script and geometry paths are now absolute in the harness
   (`physics.py`), matching the absolute-path lesson of HND-010.
7. PHY-02 deferred deliberately: judging half-model coefficients needs
   the SET_ANALYSIS_SYMMETRY_LOADS semantics calibrated first, and
   guessing bands without that would produce false evidence.

## 3. Changes persisted

* `src/pyflightstream/commands/mesh_import_export.yaml`: IMPORT,
  CCS_IMPORT, EXPORT_SURFACE_MESH, documented for 26.120.
* `src/pyflightstream/commands/__init__.py` and `script/__init__.py`:
  bool presence-keyword type (validator, checker, renderer).
* `src/pyflightstream/qa/geometry.py`: WingSpec, naca4_contour,
  wing_triangles, write_stl, generate_wing_stl.
* `src/pyflightstream/qa/physics.py`: PHY-01 case, banded references,
  compare/report/update machinery.
* `src/pyflightstream/qa/cli.py`: `pyfs-qa physics` (exit 1 on FAIL or
  aborted case) and `pyfs-qa update-reference`.
* `src/pyflightstream/qa/references/PHY-01.yaml`: seeded reference
  (reference-only commit 0e20fbb).
* `reports/physics/PHY-26120_2026-07-21` and `_banded` (yaml plus md):
  first physics evidence; polar converged at every point, CL slope
  4.83/rad against the AR-8 finite-wing anchor 5.0, CDi(4 deg) 0.0049
  (span efficiency about 0.92), bit-identical repeat run, 6 pass.
* `pyproject.toml` package data for references; `.gitignore`
  physics_runs/; tests 141 -> 161; STATUS.md, plan.csv, logbook row,
  this handoff.

## 4. Open questions and contradictions

Carried: PLN-012 (four broken commands re-review), xarray gate when
`post/` starts, SMI genericization, SWEEPER chapter pass. New: the
IMPORT trio is documented-only; probe specs for the family (file-based
effects exist: EXPORT_SURFACE_MESH round-trip) would promote them on
the next sweep. PHY-02 needs the symmetry-loads calibration decision.

## 5. Single highest-value next action

Continue PLN-008: PHY-02 (half versus full equivalence, calibrating
SET_ANALYSIS_SYMMETRY_LOADS on the real solver first) and the
version-comparison suite skeleton (synthetic first, SMI local), reusing
the PHY-01 machinery as the template.
