# HND-011: M3 closed with the full 26.120 compat sweep (2026-07-21)

## 1. Context

Same-day continuation after HND-010, on Geovana's instruction to
complete M3. Delivered PLN-011: the probe specification catalog now
covers 109 of the 112 available commands, the sweep ran twice for
real on 26.120 build #7012026 (a draft run that exposed an
attribution flaw, then the final run), and the full compat report is
committed with 68 statuses promoted through apply-compat. M3 is
closed. Suite at 141 tier 1 tests, ruff and format clean, mkdocs
strict green.

## 2. Decisions

1. Prelude tiers (none, sim, solver, solution) manufacture the
   session state a target needs: OPEN of a local .fsm (28_B, the
   smallest SMI file, local only), the minimal M2-shaped solver
   setup plus INITIALIZE_SOLVER, and a 5-iteration START_SOLVER.
   Each tier used by a run is validated by its own baseline first; a
   failing prelude downgrades its probes to unprobed instead of
   blaming the targets.
2. Effect assertions may return None: the command ran without abort
   or logged error, but no instrument observes its state. Strict
   assertions (absence is broken) only where the instrument is
   recon-proven; a probe never guesses. This split produced 44
   honest unprobed lines with per-line reasons.
3. Instruments pinned from real 26.120 recon runs: the settings
   sheet header of EXPORT_PROBE_POINTS reflects solver settings even
   before initialization (angle, velocity, iterations, convergence,
   forced flag, time increment, analysis frame name, probe count and
   coordinates); OUTPUT_SETTINGS_AND_STATUS always exposes the fluid
   state and, once initialized, the solver state; object names
   (frames via EDIT, actuators) survive as readable text in SAVEAS
   files while numeric fields are binary; OPEN, INITIALIZE_SOLVER,
   and START_SOLVER print distinctive log messages.
4. Abort attribution: the after-log is exported immediately after
   the END sentinel and before the epilogue, with a separate final
   log for epilogue-dependent effects. The draft sweep proved the
   need: DELETE_VOLUME_SECTION read broken because its epilogue (the
   export of the just-deleted section, whose failure is the expected
   effect) aborted the script; the final sweep verifies it.
5. Broken judgments kept (all target-attributed, no error lines):
   AIR_ALTITUDE ignores the METERS units argument (density 1.056
   kg/m^3 observed, the 5000 ft standard state, against 0.736 for
   5000 m); SET_MOTION_START_TIME, NEW_OFF_BODY_STREAMLINE, and
   NEW_SURFACE_SECTION_DISTRIBUTION abort script processing as
   drafted from the manual. These four deserve a focused manual
   re-review (PLN-012): the break may be the solver's or the drafted
   grammar's.
6. Support instruments must themselves be verified commands where
   possible; where a chain exists (frame creation proven through
   EDIT naming, deletion proven through a failing export), the
   chain partner's own probe line disambiguates, and the effect
   notes say so.
7. Three commands stay without specification (honest unprobed):
   SET_PROP_ACTUATOR_PROFILE and the two FSI commands need
   input-file fixtures whose format awaits a manual pass.

## 3. Changes persisted

* `src/pyflightstream/qa/probes.py`: Requires tiers with baselines,
  early_prelude hook, epilogue with separate final log, effect None
  semantics, emit_solver_setup/emit_tier_prelude, dump and file and
  region effect helpers.
* `src/pyflightstream/qa/specs.py`: the 109-spec catalog, organized
  by manual chapter, with recon-pinned instruments and per-spec
  strictness rationale.
* `src/pyflightstream/qa/cli.py` (--fsm, --label) and
  `qa/compat.py` (report label).
* `reports/compat/CMP-26120_2026-07-21_full.yaml` and `.md`: the
  full compat report (64 verified, 4 broken, 44 unprobed, one line
  per available command).
* 16 chapter YAMLs: 68 statuses promoted via apply-compat citing the
  full report (supersedes the pilot citations).
* Tests extended to 141 (catalog build validation, tier gating,
  unobservable-effect path, abort-attribution ordering).
* STATUS.md (M3 Done, focus to M4), plan.csv (PLN-011 done, PLN-012
  added), this handoff, logbook row.

## 4. Open questions and contradictions

New (PLN-012): manual re-review of the four broken commands; effect
instruments for the 41 unobservable setters (actuator and motion
numerics, toggles); input-file fixtures for the three unspecified
commands. Carried: SWEEPER chapter follow-up pass, xarray gate when
`post/` starts, SMI genericization, FR-18 string-only limitation.
Resolved: M3 closes on the full sweep (Geovana's call this session).

## 5. Single highest-value next action

Start M4 (PLN-008): the Tier 3 physics regression cases PHY-01/02
plus the version-comparison suite, synthetic geometry first; the
probe harness and the verified command set now give the physics
scripts a fully evidence-backed emission path.
