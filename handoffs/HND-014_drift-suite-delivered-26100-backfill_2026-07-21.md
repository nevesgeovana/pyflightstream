# HND-014: Drift suite delivered with the scoped 26.100 backfill (2026-07-21)

## 1. Context

Same-session continuation after HND-013, on Geovana's approval of the
version-comparison design (five points: scoped documented backfill
over raw-script escape; drift runner reusing the PHY registry; diff
bands reusing the MetricSpec half widths; degenerate self-comparison
first; SMI class later on the same runner). All three execution steps
landed: the drift machinery with its degenerate proof, the 26.100
manual pass and backfill, and the first real cross-version drift
report. Suite at 170 tier 1 tests, ruff and format clean.

## 2. Decisions

1. Drift needs no stored references: version B is judged against the
   version-A baseline inside the same WARN/FAIL half widths the case
   MetricSpecs declare, so "the physics moved too much" means the same
   thing in the regression and drift suites; `diff_runs` is a pure
   reduction testable without a solver.
2. One explicit executable per version on the CLI
   (`--fs-exe VERSION=PATH`, repeatable, never guessed); drift
   compares exactly two versions, baseline first, and the same version
   twice is the accepted degenerate form (second run under a separate
   workroot so the comparison is between independent executions).
3. Scoped backfill, not chapters: only the 27 commands the physics
   scripts and the file_io family use were checked in the 26.1 manual,
   each with a page citation in the version note ("FS 26.1 manual
   p.N"); the manual edition is registered in `_meta.yaml` and the
   SRC id assignment stays with Geovana's source registry. Every
   grammar was found identical to 26.120; the raw-script escape was
   rejected because identical text across versions is exactly what
   cannot be assumed (the SONIC_VELOCITY case).
4. Evidence bonus recorded: SONIC_VELOCITY was already deprecated in
   26.1 (the solver warns and ignores the value, FS 26.1 manual
   p.327), so its removal record now starts at 26.100.
5. Report naming: `DRF-<A digits>-<B digits>_<date>[_label]` under
   `reports/physics/`, same never-overwrite discipline.

## 3. Changes persisted

* `src/pyflightstream/qa/drift.py`: DriftMetric/DriftCaseResult/
  DriftRun, pure `diff_runs`, `run_drift` over `run_physics`,
  `write_drift_report` (yaml plus md).
* `src/pyflightstream/qa/cli.py`: `pyfs-qa drift` with per-version
  executables; exit 1 on FAIL or aborted case.
* `tests/test_qa_drift.py`: band centering on the baseline, zero-delta
  pass, undeclared-metric NO_REFERENCE, error propagation, report
  round-trip; suite 165 -> 170.
* Chapter YAMLs (9 files): 27 documented `"26.100"` lines with
  page citations plus the SONIC_VELOCITY 26.100 removed line;
  `_meta.yaml` manual_editions entry for the 26.1 edition.
* `reports/physics/DRF-26120-26120_2026-07-21_self`: degenerate proof,
  10 pass, all deltas zero.
* `reports/physics/DRF-26100-26120_2026-07-21`: first real
  cross-version evidence, builds 5012026 versus 7012026, 10 pass, all
  deltas zero at spreadsheet precision - no physics drift between 26.1
  and 26.12 on the synthetic cases.
* `.gitignore`: drift_runs/ beside physics_runs/; STATUS.md, plan.csv,
  logbook row, this handoff.

## 4. Open questions and contradictions

New: whether the SMI drift class (local geometry, aggregated
coefficients only) closes PLN-008 inside M4 or moves to v0.2+ is
Geovana's milestone call; the runner needs only new registry cases
pointing at `_private/geometry/smi/`. The SRC id for the 26.1 manual
awaits registration in the author's source registry (then the version
notes can be normalized from "FS 26.1 manual" to the SRC id). Carried:
PLN-012; xarray gate at `post/`; SMI genericization; SWEEPER pass;
probe specs for the import trio and SET_ANALYSIS_SYMMETRY_LOADS.
Note: 26.100 command statuses are documented only; Tier 2 backfill
probing of 26.100 stays at v0.2+ as planned.

## 5. Single highest-value next action

Geovana's call between: defining the SMI drift cases (closing PLN-008
entirely inside M4) or declaring M4 done on the synthetic suite and
jumping to M5 docs (PLN-009/010), where the command reference and the
compatibility matrix now have three versions of evidence to render.
