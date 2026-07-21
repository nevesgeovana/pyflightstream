# HND-009: M2 closed with the legacy matrix reader (2026-07-21)

## 1. Context

Same-day continuation after HND-008, on Geovana's instruction to
close M2. Delivered the last M2 content item, the legacy matrix
reader with convert-matrix; M2 is done (exit criterion met in
HND-008, content complete here). Suite at 117 tier 1 tests, ruff and
format clean, mkdocs strict build, CI green.

## 2. Decisions

1. The legacy semantics were pinned from the author's own driver
   script in the legacy research workspace before coding (her IP,
   read for format evidence; the vendored AGPL package stays
   untouched, invariant 2, and the workspace is referenced only
   generically, invariant 5). Verified: SWEEP_TYPE splits its axis
   codes on '/'; SWEEP_VALUES carries one comma-separated list per
   axis, also '/'-separated; variables split on '/' then on the
   first ':' (values may contain spaces); HIDDEN is 0/1; the four
   3-digit codes were resolved to files by number at run time.
2. Verified sweep codes only: AL (alpha) and BE (beta) are mapped;
   an unknown code is refused with a message saying the mapping
   grows on evidence. The legacy workflow varies one axis while the
   other holds a single value, so AL/BE lists broadcast into native
   alpha_beta pairs.
3. RE is stored in millions and converts to an absolute Reynolds
   number in the native model, cross-evidenced by the SAD Section 5
   example (the same POL 9001 case shows RE 4.38 and reynolds
   4.38e6).
4. Lossless conversion (FR-11): to_campaign maps FS_SCRIPT to a
   recipe through an explicit mapping (PP-7/FR-12) and preserves
   REF, SET, ENTRY, FS_SCRIPT, FS_BUILD, and HIDDEN in the case
   variables (legacy_* keys). convert_matrix emits campaign.toml
   text with a hand-rolled writer (quoted keys, escaped strings; the
   stdlib has no TOML writer) and the round trip through
   load_campaign is a test.
5. convert-matrix ships as a function; console-script wiring waits
   for the first CLI entry points (noted in STATUS).

## 3. Changes persisted

* `src/pyflightstream/cases/matrix_legacy.py`: LegacyMatrixError,
  LegacyRow, read_matrix (verified layout enforcement, RUN
  filtering), to_campaign, convert_matrix.
* `tests/fixtures/matrix_legacy.fs` (sanitized, first row shaped
  like the real POL 9001 case) and `tests/test_matrix_legacy.py`
  (9 tests, including the TOML round trip).
* STATUS.md (M2 milestone row Done; current focus moves to M3),
  plan.csv (PLN-005 done), this handoff, logbook row.

## 4. Open questions and contradictions

Carried over: SWEEPER chapter follow-up pass, xarray gate when
`post/` starts, SMI genericization, FR-18 string-only limitation.
New: an advance-ratio sweep code exists per the SRS but no legacy
matrix using it was seen; the mapping refuses it until one appears
(decision 2).

## 5. Single highest-value next action

Start M3: the Tier 2 probe harness (PLN-007), per-command probe
scripts with a sentinel export, log-pattern matching, and effect
assertions, feeding `pyfs-qa probe --version 26.12` and the first
committed compat report under `reports/compat/`; newly feasible on
this machine since both executables live in `_private/exe/` (26.100
build #5012026, 26.120 build #7012026, RPT-001).
