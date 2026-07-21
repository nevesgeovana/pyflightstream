# HND-006: M2 cases model and campaign loop (2026-07-21)

## 1. Context

Same-day continuation after HND-005, on Geovana's instruction to
execute the next M2 step: the `cases/` SIM model (SAD Section 5) and
the campaign loop (SAD Section 7). Delivered and green: 96 tier 1
tests (up from 82), ruff and format clean, mkdocs strict build; the
tier 1 end-to-end dry run of the M2 exit criterion passes. gh is
authenticated persistently since this day (Geovana ran the browser
login in-session).

## 2. Decisions

1. The SIM model uses pydantic, not the plain dataclasses the SAD
   sketch mentions (Claude): `campaign.toml` loading gets field
   validation, unknown-key rejection, and the registered-version
   check (`fs_version` resolved at load time) for free, consistent
   with the M1 engineering decision that made pydantic the schema
   backend.
2. The `ScriptRecipe` protocol stays exactly `build(case, script)`;
   the campaign loop specializes the case per point by filling
   `SimCase.point` (model_copy) and rewrites `case.geometry` to the
   staged copy under `inputs/`, so recipes OPEN exactly the file the
   manifest hashed (Claude).
3. Recipe output convention: recipes export with paths relative to
   the execution directory; the executor runs with cwd at the sim
   folder, and `SimCase.outputs` declares the names the loop
   collects into `raw/` (missing one: FAILED_INCOMPLETE_OUTPUT).
4. `run_campaign` requires an `OutcomeAssessor` (Claude): the
   CONVERGED versus COMPLETED_MAX_ITER versus FAILED_DIVERGED
   judgment needs solver outputs, and the loop refuses to invent
   convergence evidence it cannot see. The standard assessor ships
   with the results parsers (next step); tests inject stubs.
   Execution failure, script failure, and incomplete outputs are
   decided by the loop itself.
5. Preparation failures of a case (unresolvable recipe, missing
   geometry at staging) land every point of that case as
   FAILED_SCRIPT with the error text: loud, per point, never a
   silent skip (PP-5). Truly unexpected internal exceptions crash
   the loop instead of masquerading as solver statuses.
6. `run_campaign` accepts a named recipe registry (`recipes=`),
   consulted before the `module:function` resolution; the legacy
   matrix reader will register its historical recipe names there
   (PP-7, FR-12).
7. `CampaignErrors` keeps the SAD Section 7 name over ruff's N818
   suffix convention (per-line noqa with justification).

## 3. Changes persisted

* `src/pyflightstream/cases/__init__.py`: SweepAxis (alpha, beta,
  alpha_beta, advance_ratio; typed values validation; points()),
  point_tag (stable signed tags, `a+02.0_b+00.0`), ReferenceData,
  SolverSettings (helper-aligned names plus timeout_s), SimCase,
  Campaign, load_campaign (tomllib), ScriptRecipe protocol,
  resolve_recipe with didactic errors.
* `src/pyflightstream/run/__init__.py`: Assessment, OutcomeAssessor,
  CampaignErrors, run_campaign with _prepare_case and _execute_point
  (exactly one manifest record per point, appended unconditionally).
* `tests/test_cases.py` (8 tests) and `tests/test_run_campaign.py`
  (6 tests, StubSolver-driven dry run covering all failure paths and
  the full success path).
* STATUS.md current focus, plan.csv PLN-005 note, this handoff,
  logbook row.

## 4. Open questions and contradictions

Carried over: SWEEPER chapter follow-up pass, xarray gate at post/
time, SMI genericization. New: none.

## 5. Single highest-value next action

`results/`: the two anchor-based primitives (`labeled_value`,
`delimited_table`) and the loads-spreadsheet parser with fixtures
from real 26.120 output (fixture capture needs the licensed machine
or an existing output file from the research workspace), shipping
the standard `OutcomeAssessor` so `run_campaign` gains its default
convergence judgment; then the legacy matrix reader, and the M2 exit
real local run.
