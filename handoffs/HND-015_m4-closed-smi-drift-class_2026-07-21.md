# HND-015: M4 closed with the SMI drift class (2026-07-21)

## 1. Context

Same-session continuation after HND-014, on Geovana's instruction to
complete the whole M4 scope now. Delivered the SMI drift class: two
local-only cases over the research corpus, first measurements and
seeded references on 26.120, band calibration from the measured
magnitudes, and the capstone complete-matrix drift 26.100 versus
26.120. M4 content is complete (PHY-01/02, synthetic drift, SMI
drift). Suite at 174 tier 1 tests, ruff and format clean, mkdocs
strict green.

## 2. Decisions

1. SMI cases are ordinary registry cases behind an explicit gate:
   they join `registered_cases(include_smi=True)` only when the run
   receives `--smi-root` (never guessed, geometry never enters Git);
   without the root a requested SMI case is refused before any solver
   time. Committed artifacts carry aggregated Total coefficients (CL,
   CDi, CDo, CMy at 2 deg) plus the sha256 of the opened .fsm.
2. Two corpus cases: SMI-01 (28_B, isolated body, smallest file) and
   SMI-02 (31_WBH_IH0, wing-body-tail full configuration). The script
   is the M2-shaped steady setup the M3 preludes proved on this
   corpus (OPEN, FLUID_PROPERTIES ISA, steady incompressible init on
   all boundaries, converged solve at 2 deg), with the unit reference
   area and length convention: coefficients scale consistently on
   both sides of any comparison, which is all drift needs.
3. Band kinds are a per-case calibration from the first measurement:
   absolute half widths for the near-zero body coefficients, relative
   0.5 percent warn / 2 percent fail for the O(1..100) unit-reference
   full-configuration coefficients. The calibration commit cites the
   measured magnitudes; the references were seeded after it so they
   carry the calibrated bands.
4. SET_SOLVER_STEADY joined the 26.100 backfill (FS 26.1 manual
   p.340, identical) when the SMI script build for 26.100 refused it,
   proving the evidence gate works.
5. First real finding of the SMI class (capstone report): the
   isolated-body pitching moment moved between builds (CMy -1.7702 to
   -1.7843, about 0.8 percent, 26.100 build 5012026 to 26.120 build
   7012026), a WARN inside the FAIL band; every synthetic delta is
   zero and the full configuration stays inside 0.35 percent. The
   WARN goes to triage, not to a reference change; it is exactly the
   sensitivity the SMI class exists for (SAD Section 11).

## 3. Changes persisted

* `src/pyflightstream/qa/physics.py`: SMI section (build_smi_script,
  smi_metrics, per-case band specs, SMI_CASES, sha256 stamping),
  `registered_cases`, `smi_root` through context and `run_physics`.
* `src/pyflightstream/qa/drift.py` and `cli.py`: `--smi-root` on
  physics and drift; combined registry in the drift diff and
  update-reference.
* `src/pyflightstream/commands/solver_settings.yaml`:
  SET_SOLVER_STEADY 26.100 documented line.
* Tests 170 -> 174 (registry gating, refusal without root, script
  pins for both versions, metric reduction).
* `reports/physics/PHY-26120_2026-07-21_smi`: first SMI measurements
  (28_B converged at 25 iterations, 31_WBH_IH0 at 94).
* `src/pyflightstream/qa/references/SMI-01.yaml` and `SMI-02.yaml`:
  seeded references (reference-only commit ebb5d4f).
* `reports/physics/DRF-26100-26120_2026-07-21_complete`: the capstone
  matrix, 17 pass, 1 warn (SMI-01 CMy), 0 fail.
* `.gitignore` drift_runs*/; STATUS.md (M4 Done), plan.csv (PLN-008
  done), logbook row, this handoff.

## 4. Open questions and contradictions

New (PLN-013 candidate): triage of the SMI-01 CMy warn - whether the
0.8 percent pitching-moment movement between builds is a solver
change, a case-setup sensitivity, or noise; a re-run and a
per-boundary look at 28_B would decide. Carried: SRC id for the 26.1
manual (Geovana will register; asked again at this session's close);
PLN-012; xarray gate at `post/`; SMI genericization option; SWEEPER
pass; probe specs for the import trio and SET_ANALYSIS_SYMMETRY_LOADS;
26.100 Tier 2 backfill probing at v0.2+. The actuator-disc SMI drift
case (the corpus path the SAD names for v0.2+ PHY cases) joins the
same registry when defined.

## 5. Single highest-value next action

Start M5 (PLN-009/010): mkdocs command reference and compatibility
matrix generated from the database (now carrying 26.100 and 26.120
evidence) plus the steady polar example; en route, decide the SMI-01
CMy triage (PLN-013) and register the 26.1 manual source id.
