# HND-007: M2 results parsers and standard assessor (2026-07-21)

## 1. Context

Same-day continuation after HND-006, on Geovana's instruction to
proceed to `results/` and the loads parser, with permission to
consult example run files in the legacy research workspace
(referenced generically per invariant 5). Delivered and green: 107
tier 1 tests (up from 96), ruff and format clean, mkdocs strict
build.

## 2. Decisions

1. Evidence handling: only solver output files of one local 26.12
   run were read from the legacy research workspace (loads
   spreadsheet, exported log, plots export); the vendored AGPL
   package present there was not opened (invariant 2), and the
   workspace is never named in committed artifacts (invariant 5).
2. Fixtures are committed with the structure of the real files
   preserved (labels, spacing style, dashed table delimiters,
   footer) and every value, path, and surface name replaced with
   synthetic ones. Four fixtures: unsteady loads, steady loads
   (synthesized variant), truncated loads (no footer), and the log
   residual table.
3. FR-18 version cross-check is prefix-lax by design, on observed
   evidence: the 26.120 build prints ``Flightstream version 26.1,
   build #7012026``, and the string "26.1" is also the display alias
   of canonical 26.100. The check compares the requested alias by
   prefix (warning ``VersionMismatchWarning`` only on inconsistency)
   and records the printed string and build verbatim in the
   manifest; the build number is the precise discriminator. A true
   26.100-versus-26.120 confusion is therefore not detectable from
   the string alone; recorded as a known limitation for Tier 2.
4. The standard assessor (``run.LoadsAssessor``) judges from
   evidence in this order: non-finite Total coefficients are
   FAILED_DIVERGED; with a declared log export, the final velocity
   and pressure residuals against the run's convergence limit decide
   CONVERGED versus COMPLETED_MAX_ITER (NaN residuals diverge);
   without a log, steady runs use the iteration heuristic (counter
   below the requested limit means the threshold stopped the
   solver), and unsteady runs are recorded COMPLETED_MAX_ITER
   because the time loop always runs to its prescribed end. An
   unusable loads file is FAILED_INCOMPLETE_OUTPUT.
5. ``Assessment`` gained ``fs_version_reported`` and ``fs_build``,
   copied by the campaign loop into the manifest record (FR-18
   recording without touching the assessor protocol shape).
6. The plots export (large per-time-step CSV) is out of scope here;
   it belongs to `post/` sweep assembly.

## 3. Changes persisted

* `src/pyflightstream/results/__init__.py`: AnchorNotFoundError,
  IncompleteOutputError, VersionMismatchWarning, labeled_value,
  parse_number (solver forms `.000`, `4380000.`, `1.000E-05`),
  delimited_table (structural terminator), LoadsReport with
  diverged_columns(), parse_loads, ResidualSample,
  parse_residual_history.
* `src/pyflightstream/run/__init__.py`: LoadsAssessor; Assessment
  extended with the version stamps; record copying in
  _execute_point.
* `tests/fixtures/` (4 sanitized fixtures), `tests/test_results.py`
  (8 tests), `tests/test_run_campaign.py` extended (assessor unit
  judgments plus the end-to-end run with LoadsAssessor).
* STATUS.md current focus, plan.csv PLN-005 note, this handoff,
  logbook row.

## 4. Open questions and contradictions

Carried over: SWEEPER chapter follow-up pass, xarray gate at post/
time, SMI genericization. New: the FR-18 string-only limitation of
decision 3 (Tier 2 probes can verify the build-to-version mapping).

## 5. Single highest-value next action

The legacy matrix reader (`matrix_legacy.py`, FR-10: the verified
15-column pipe-delimited layout, RUN = 1 filtering, '/'-separated
KEY:VALUE variables, POL mapped to sim_id; plus `convert-matrix`,
FR-11), with fixtures from a sanitized legacy matrix; then the M2
exit real local run, which is feasible on this machine: a 26.12
installation exists in the research workspace, so the run needs only
a small real campaign pointed at it.
