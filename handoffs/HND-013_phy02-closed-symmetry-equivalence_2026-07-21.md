# HND-013: PHY-02 closed on the symmetry-equivalence calibration (2026-07-21)

## 1. Context

Same-session continuation after HND-012, on Geovana's instruction to
proceed. Delivered the second half of the PHY pair of PLN-008: the
SET_ANALYSIS_SYMMETRY_LOADS calibration on the real solver, the PHY-02
case (half versus full symmetry equivalence), its first committed
evidence and seeded reference, and the full-matrix report with all 10
metrics passing. The version-comparison suite remains the open tail of
PLN-008. Suite at 165 tier 1 tests, ruff and format clean.

## 2. Decisions

1. Calibration before implementation (the HND-012 deferral honored):
   a three-export script on the mirrored half wing observed that after
   a MIRROR initialization the solver default already includes the
   symmetry-plane loads (default equals ENABLE: CL 0.3385 both ways),
   and DISABLE halves the loads and exposes the one-wing rolling
   moment (CL 0.1693, CMx 0.3077). PHY-02 still emits
   SET_ANALYSIS_SYMMETRY_LOADS ENABLE explicitly, pinned by a test,
   because the case must not lean on a default that could move
   between versions.
2. PHY-02 shape: full-span baseline and open-root MIRROR half, both
   on the full planform reference area, one angle (4 deg). Metrics:
   CL_full_a4 and CL_half_a4 (relative bands) plus delta_CL_a4 and
   delta_CDi_a4 (absolute bands 0.005/0.02 and 0.0005/0.002), the
   equivalence being the physics content.
3. The one-point wing script builder is shared between PHY-01 and
   PHY-02 (symmetry and symmetry-loads arguments); report points
   carry labels so two points at the same angle stay distinguishable
   in both report faces.
4. Version-comparison suite deliberately not stubbed: the database is
   evidence-strict for 26.120 only, so a 26.100 script is refused at
   emission until backfill probing (v0.2+ in the milestone map);
   dead-code stubs would add nothing the handoff cannot say.

## 3. Changes persisted

* `src/pyflightstream/qa/physics.py`: shared `_build_wing_point_script`
  (symmetry, symmetry_loads), `build_phy02_script`, `phy02_metrics`,
  `_run_phy02`, PHY-02 registry entry, labeled points in both report
  faces.
* `tests/test_qa_physics.py`: PHY-02 script pins (MIRROR plus explicit
  ENABLE; baseline without it), metric reduction, label round-trip;
  suite 161 -> 165.
* `reports/physics/PHY-26120_2026-07-21_phy02` (yaml plus md): first
  PHY-02 evidence; full CL 0.3370 (reproduces PHY-01 exactly), half
  CL 0.3385, delta_CL +0.0015 (0.4 percent), delta_CDi 0.0, both
  points converged.
* `src/pyflightstream/qa/references/PHY-02.yaml`: seeded reference
  (reference-only commit 27ea057).
* `reports/physics/PHY-26120_2026-07-21_full` (yaml plus md): the
  whole matrix against both references, 10 pass, bit-identical to the
  seeding runs.
* STATUS.md, plan.csv PLN-008 note, logbook row, this handoff.

## 4. Open questions and contradictions

Carried: PLN-012; xarray gate at `post/`; SMI genericization; SWEEPER
manual pass; probe specs for the import trio (IMPORT, CCS_IMPORT,
EXPORT_SURFACE_MESH) and now SET_ANALYSIS_SYMMETRY_LOADS, whose
loads-spreadsheet instrument this session proved workable. New: the
version-comparison suite needs a design call on how the drift runner
handles versions the database cannot emit for yet (backfill probing
first, or a raw-script escape recorded in the manifest).

## 5. Single highest-value next action

Close PLN-008 with the version-comparison suite skeleton on synthetic
geometry (26.120 self-comparison as the degenerate case, structure
ready for 26.100 once backfill probing lands), or jump to M5 docs
(PLN-009/010) if Geovana prefers the milestone cut; the physics matrix
itself is done and green.
