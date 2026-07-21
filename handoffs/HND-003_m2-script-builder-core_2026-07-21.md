# HND-003: M2 started, script builder core (2026-07-21)

## 1. Context

Continuation of the HND-002 day, opened as the M2 start on Geovana's
instruction to begin PLN-005. Objective against STATUS.md: deliver the
script builder core (validating emit, phase ordering, layout
rendering, goldens). Delivered and green: 44 tier 1 tests, ruff clean,
mkdocs strict build, CI run 29847521806 success on commit 830ecae.

## 2. Decisions

1. Rendering grammar refinements recorded in the schema on manual
   sample evidence (proposed and applied by Claude): ArgSpec gains
   `separator` (comma, space, or newline; list separators vary per
   command, SRC-003 pp.332, 338, 352, 364) and `own_line` (inline
   commands whose file path follows on the next line, pp.323-324,
   336, 366-367).
2. Commands with the "-1 selects all, index line omitted" form mark
   their list argument optional: SET_VORTICITY_DRAG_BOUNDARIES
   (p.350) and SET_VTK_EXPORT_VARIABLES (p.352).
3. Validation order per SAD Section 4.1: existence in version, typed
   binding, enum membership with case normalization (scripting is
   case insensitive, p.279; the builder emits the spec casing),
   count-versus-list consistency, phase ordering with the control
   phase exempt.
4. Known gaps deferred to the helper layer, documented in the script
   module docstring: INITIALIZE_SOLVER per-surface lines when
   SURFACES is not -1, and the PERIODIC symmetry copy count; raw()
   covers both meanwhile.

## 3. Changes persisted

* `src/pyflightstream/script/__init__.py`: Script, ScriptOrderError,
  CommandArgumentError; render for the five layouts; raw() sets
  raw_flag for the future manifest (FR-07); no module-level state.
* `src/pyflightstream/commands/__init__.py`: ListSeparator enum,
  ArgSpec.separator and own_line with validators (separator only on
  list types, own_line only in inline layout).
* Chapter YAML updates carrying the new fields with page evidence.
* `tests/test_script.py` (13 tests) and the first golden,
  `tests/goldens/steady_polar_26.120.txt`.
* plan.csv PLN-005 in_progress with the delivered and remaining
  scope; STATUS.md current focus updated.
* Commit 830ecae, CI run 29847521806 green.

## 4. Open questions and contradictions

Carried over unchanged from HND-002: SWEEPER chapter follow-up pass,
xarray gate at post/ time, SMI genericization, gh auth browser flow.

## 5. Single highest-value next action

The curated helper layer of SAD Section 4.3 (free stream, actuator
disc, rotary motion, solver settings, sweeps, analysis and export,
probe management), thin typed functions translating into emit()
calls, closing the two INITIALIZE_SOLVER gaps above with cross
reference checks (frames and actuator ids created earlier in the
script); then files/ layout and the local executor.
