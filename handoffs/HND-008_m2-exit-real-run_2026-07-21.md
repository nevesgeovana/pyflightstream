# HND-008: M2 exit real local run (2026-07-21)

## 1. Context

Same-day continuation after HND-007. Geovana placed the FlightStream
executables under `_private/exe/` (26.100 and 26.120) and asked for
them to be tested before progressing. Delivered: headless smoke on
both executables, the real local run of the M2 exit criterion
(CONVERGED, `reports/RPT-001`), and one parser fix from real-log
evidence. Suite at 108 tier 1 tests, ruff and docs green.

## 2. Decisions

1. Vendor files are not renamed (Claude): the campaign's `fs_exe` is
   an explicit path, so renaming licensed binaries adds risk and no
   information; the folder names (FlightStream_26100,
   FlightStream_26120) already carry the canonical identity.
2. The smoke script is built once under 26.120 validation (PRINT,
   EXPORT_LOG, CLOSE_FLIGHTSTREAM) and executed by both installed
   versions; the executor runs rendered text and does not
   revalidate. Both return code 0 and export their log. Build
   mapping evidence recorded in RPT-001: 26.100 prints build
   #5012026, 26.120 prints #7012026, both with version string
   "26.1" (confirms the HND-007 FR-18 design).
3. The real run uses a local research geometry, referenced in
   committed artifacts by sha256 only (invariant 5); the campaign
   workspace lives in the session scratchpad and stays outside Git.
   The committed report carries aggregated Total coefficients only
   and is marked pipeline validation, not physics.
4. Real-log evidence fix: hidden-mode exported logs carry stray NUL
   bytes; `parse_residual_history` scrubs them (test added). The
   first attempt honestly landed FAILED_INCOMPLETE_OUTPUT because of
   those bytes, which is the designed no-guessing behavior; the
   second run, after the fix, went CONVERGED (iteration 86 of 100,
   residual 1.81E-06, wall 5.3 s).
5. Re-running a campaign into the same workspace root correctly
   refuses on the duplicate run_id; the re-run used a fresh root.
   Ergonomics of intentional re-runs (archive first, or a new root)
   stay as documented behavior for now.

## 3. Changes persisted

* `src/pyflightstream/results/__init__.py`: NUL scrub in
  parse_residual_history with the evidence comment.
* `tests/test_results.py`: NUL scrub test (suite at 108).
* `reports/RPT-001_m2-exit-real-run_2026-07-21.md`: the committed
  evidence of the real run and the smoke findings.
* STATUS.md (M2 milestone row: exit criterion met; current focus),
  plan.csv PLN-005 note, this handoff, logbook row.
* Local only, never committed: `_private/exe/` store, scratchpad
  campaign workspaces of the two attempts.

## 4. Open questions and contradictions

Carried over: SWEEPER chapter follow-up pass, xarray gate at post/
time, SMI genericization, FR-18 string-only limitation (now with
build mapping evidence for both installed versions). New: none.

## 5. Single highest-value next action

The legacy matrix reader (`matrix_legacy.py`, FR-10: verified
15-column pipe-delimited layout, RUN = 1 filtering, '/'-separated
KEY:VALUE variables, POL mapped to sim_id; plus `convert-matrix`,
FR-11), the last M2 content item; a sanitized legacy matrix fixture
can be drafted from the research workspace matrix file, values and
names replaced.
