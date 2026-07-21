# HND-004: M2 curated helper layer (2026-07-21)

## 1. Context

Continuation session of PLN-005, opened against the STATUS.md focus
left by HND-003: the curated helper layer of SAD Section 4.3 over the
script builder core, closing the two documented INITIALIZE_SOLVER
gaps and adding cross-reference validation (SAD Section 4.2).
Delivered and green locally: 63 tier 1 tests (up from 44), ruff check
and format clean, mkdocs strict build.

## 2. Decisions

1. The two builder gaps are closed in the database, not in code
   (Claude, on the evidence already cited in the entry notes):
   INITIALIZE_SOLVER gains `surface_toggles` (new `str_list` argument
   type, one index,ENABLE line per surface, count-checked against
   SURFACES) and `symmetry_copies` (new ArgSpec flag
   `joins_previous`, appending the PERIODIC copy count to the
   SYMMETRY line, SRC-003 p.337). SET_FREESTREAM gains its optional
   CUSTOM and ROTATION arguments (p.322). Composite pair typing for
   the toggle lines lives in the initialize_solver helper, which is
   why `str_list` stays acceptable in the schema.
2. Helpers are thin module-level functions in `script/helpers.py`
   taking the Script as first argument, per the SAD 4.3 wording; one
   generated function per command stays rejected. Conditional
   argument combinations documented in manual prose (which extras
   each SET_FREESTREAM type takes, PERIODIC copies required with
   PERIODIC symmetry only) are enforced by the helpers with cited
   CommandArgumentError messages.
3. Cross-reference validation went into `emit()` itself, not only the
   helpers (Claude, stronger than the SAD 4.2 minimum): the Script
   counts created local frames, actuators, and motions
   (CREATE_NEW_*, DELETE_* adjust a ledger) and raises
   ScriptReferenceError when a citing argument (frame, load_frame,
   coordinate_system_id, actuator_index, motion_id, frame_indices)
   exceeds it. Frame index 1 (reference frame) always exists.
   `declare_existing()` covers objects carried by an OPENed project
   file, since the builder cannot see inside `.fsm` files.
4. `emit()`'s command-name parameter became positional-only so a
   command argument may itself be named `name` (CREATE_NEW_ACTUATOR).
5. Behavior note recorded: inserting the optional INITIALIZE_SOLVER
   arguments mid-order changed the meaning of long positional
   `emit()` calls; the tests moved to keyword arguments. Acceptable
   pre-1.0; keyword emission is the documented style for
   keyword_block commands.

## 3. Changes persisted

* `src/pyflightstream/script/helpers.py`: 14 curated helpers
  (free_stream, atmosphere, actuator_disc, rotary_motion,
  unsteady_solver, solver_settings, initialize_solver, sweep,
  analysis_setup, export_results, probe_points, probe_line,
  probes_from_file, export_probes); actuator_disc and rotary_motion
  return the created index; export_results warns on the deprecated CP
  variable (p.352).
* `src/pyflightstream/script/__init__.py`: cross-reference ledger,
  ScriptReferenceError, declare_existing, num_* properties,
  `str_list` checking, `joins_previous` rendering, positional-only
  emit name; module docstring rewritten (gaps closed).
* `src/pyflightstream/commands/__init__.py`: ArgType.STR_LIST,
  ArgSpec.joins_previous with schema validators (scalar only;
  keyword_block with a preceding argument).
* `commands/solver_initialization.yaml` and
  `commands/boundary_conditions.yaml`: the argument additions above
  with updated notes.
* `tests/test_script_helpers.py` (19 tests), two new goldens
  (`actuator_polar_26.120.txt`, `rotor_unsteady_26.120.txt`),
  test_script.py updated to keyword INITIALIZE_SOLVER calls and
  declare_existing, test_command_db.py schema tests extended.
* STATUS.md current focus, plan.csv PLN-005 note, this handoff,
  logbook row.

## 4. Open questions and contradictions

Carried over unchanged from HND-003: SWEEPER chapter follow-up pass
(may widen the sweep helper grammar), xarray gate at post/ time, SMI
genericization, gh auth browser flow. New: the mirror-with-full-model
build-time warning (SRC-003 p.217) still waits for case metadata,
now explicitly tied to cases/ landing.

## 5. Single highest-value next action

The `files/` run workspace layout and the local executor (SAD
Sections 6 and 7): the package-owned run folder scheme, then
LocalExecutor driving FlightStream with a rendered script, capturing
the log, and writing the manifest with the raw_flag; then the
campaign loop and the loads parser toward the M2 exit criterion
(end-to-end dry run plus one real local run).
