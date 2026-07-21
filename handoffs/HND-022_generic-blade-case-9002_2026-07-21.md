# HND-022: generic blade and the shareable case 9002 (2026-07-21)

## 1. Context

Same-session continuation after HND-019, on Geovana's approval of the
de-characterization proposal: the reproduced legacy propeller case
must become a shareable test case with the complete workflow, without
exposing the research blade geometry (which needs its owner's
consent). Delivered: a generic parametric blade generator in the
library and case 9002 in the research workspace's tools/fts_sim,
seeded on the real solver.

## 2. Decisions

1. The blade is generated from code with analytic public shape laws
   only (invariant 5): NACA 4409 section, linear chord taper 0.14R to
   0.06R, blade-element ideal twist beta = atan(J/(pi r/R)) with the
   collective anchored at beta(0.75R) = 45 deg for design J 1.7,
   quarter-chord pitch axis, closed root and tip caps. Round
   coefficients chosen without reference to any research propeller;
   the case seeds its own baseline instead of matching anything.
2. Frame convention documented in the generator: rotor axis +X, blade
   along +Z, suction side facing -X so thrust points upstream for
   positive rotation. The seeding run confirmed the sign reasoning
   empirically (per-blade axial force -654 N at the final step).
3. Case 9002 keeps every command family of the 9001 flow (frames,
   rotary motion, PERIODIC 6, 40 force monitors, the generic
   225-station fluid lattice, unsteady 10 deg per step for 1.5
   revolutions, section distributions on the blade, probe lattice
   imported from a generated X,Y,Z,TYPE file, the eight exports) but
   swaps the OPEN of the research file for IMPORT of the generated
   STL, and uses round operating numbers (V 49.0, S_ref 10.0, L_ref
   2.0, rpm 472.83 derived from J with its formula in the case file).
4. Blade-only sector under PERIODIC 6 (no spinner): the periodic
   sector modeling of bodies of revolution is a refinement left open.

## 3. Changes persisted

* pyflightstream commit fbc852b: `BladeSpec`, `blade_triangles`,
  `generate_blade_stl` in `qa/geometry.py` (docstrings state the
  formulas and reference frame); tier 1 tests for the twist anchor
  and monotonicity, watertightness (every edge shared exactly twice),
  outward orientation (positive signed volume), and the STL writer.
* tools/fts_sim (research workspace): case_9002.py, recipe_9002.py,
  run_9002.py, README section with the de-characterization contract
  and the seeded baseline.
* Seeding run on 26.120 build 7012026 (79 s): CL -0.0001012,
  CDi -0.0451749 (net thrust), CDo 0.0007011, CMy 0.0286429; thrust
  transient decaying -826 to -654 N per blade over 1.5 revolutions;
  all eight outputs written.

## 4. Open questions and contradictions

The generic blade is the natural geometry seed for PHY-05 (PLN-014,
owned by the M6 line): promoting case 9002 into the Tier 3 matrix
with banded references is the follow-up there. Periodic spinner
sector modeling stays open. If the research propeller's owner later
consents, the real-geometry case 9001 remains the local ground truth
and nothing changes for 9002.

## 5. Single highest-value next action

Wire case 9002 into PHY-05 (PLN-014): register it as a physics case
with banded references seeded from this baseline, so the shareable
propeller flow joins the committed regression matrix.
