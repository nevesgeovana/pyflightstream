# HND-031: soft pilot ran, rotor morphing found dropped by the build

Date: 2026-07-21. Third block of the HND-029/030 session line, on the
author's instruction to proceed with the next stage in-session and her
recollection about output decimal places. Full evidence:
`reports/RPT-007_soft-pilot-morphing-investigation_2026-07-21.md`.

## Delivered

1. Digits probe (author's recollection checked):
   SET_SIGNIFICANT_DIGITS 8 does not change the sectional loads
   export (header dt stays three-decimal, rows keep four mantissa
   digits); the `FsiConfig.time_increment_s` remedy stands and was
   validated in the soft pilot (phase boundaries exactly 18/36).
2. PLN-020 beta(r) projection (commit 5e47df6): `frame_embedding`
   rule shared by nodes and loads; `station_triads` places nodes on
   the local twisted chord and embeds/extracts FSIDisp components
   exactly (scalar twist encoding survives; nose-up is about -Z for
   this geometry); `project_rotor_frame_loads` maps the cut-plane
   densities onto section axes and flips the export moment (positive
   nose-down, magnitude matching |Cm| q c^2) into the nose-up
   convention. Rigid-rotation and machine-precision round-trip tests
   at nonzero blade angle; wing case unchanged at Omega zero.
3. Soft-blade pilot (EI 1e5, GJ 2e3, 90 steps): the complete machine
   in-solver - phases 17/18/37/18 with unrelaxed phase 4 recording
   (closing RPT-006 finding 4), convergence declared at revolution 2,
   tip twist -1.029 deg nose-down and tip flap +4.86 mm suction-side
   (signs corroborate the projection), frozen replay of the real
   4.2 mm deformation reproducing to 5e-6 over 90 steps.
4. The morphing investigation: the soft response was aerodynamically
   invisible (CDi 6e-6 versus a matched 90-step near-rigid), and the
   controlled series (RBF type explicit, iterations 2, aeroelastic
   block before initialization, plain-decimal FSIDisp, a garbage
   FSIDisp crashing the solver and proving the file is read, and a
   motionless wing control that morphs decisively: CL +0.48 to +0.86
   under a held 0.4 m bend) concludes that build 7012026 silently
   drops FSIDisp morphing on rotary-motion boundaries. Two-way rotor
   FSI is solver-blocked; the pyflightstream interface is proven
   correct end to end by the wing control. RPT-006 carries the
   reinterpretation addendum; `aeroelastic_coupling.yaml` notes the
   behavior finding and the crash robustness note; PLN-020 is marked
   blocked with the interim static-wing option.

Suite at 321 tier 1 tests, strict docs green; soft convergence log
committed under `reports/fsi/`.

## Pending

1. Vendor-facing question on the motion-plus-morphing defect
   (Geovana's call; the reproducible package is the rigid/norbf/
   wendland probes against the wing control, RPT-007 Sections 3-4).
2. PLN-019 Tier 2 sweep (unchanged).
3. Optional interim two-way pilot on the static wing (no defect in
   the way); the rotor Tier 3 near-rigid regression remains
   meaningful as loop mechanics.
4. Research side: the FSI Blade Coupling Plan should record the
   solver-blocked status of rotor two-way coupling on 26.120 build
   7012026 before any campaign planning (WP8/WP9).
