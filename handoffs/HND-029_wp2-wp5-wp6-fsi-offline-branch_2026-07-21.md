# HND-029: WP2, WP5, and WP6 close the offline FSI branch

Date: 2026-07-21. Continuation of the M6 session line (HND-021,
HND-026) from the resume prompt of the HND-026 close: open WP2 on the
committed dry-run fixtures and follow the interface branch to the
driver. All three offline packages landed; every deliverable below is
tier 1, no solver in the loop.

## Delivered

1. WP2, `fsi/loads.py` (commit 3dcd173): the
   `FS_SurfaceSection_Loads.txt` parser on the anchor primitives of
   `results/`. SI asserted on the labeled header and the units footer
   (`UnitsError` names the `COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS`
   fix, FSI-R03); declared count, table terminator, and footer are
   structural (FR-17). Attribution is the family-per-blade bookkeeping
   of RPT-005 finding 6: `SectionFamilyMap` (emitted by whoever
   creates the distributions; `is_blade` flag for non-blade families)
   partitions the flat table, and the split cross-checks the geometry:
   in-block offsets must march monotonically and a boundary where both
   offset and chord continue smoothly is refused. `to_elastic_axis`
   transfers the quarter-chord moments with the configured e(r)
   (M_EA = M_PA + e x F, FSI-R04), interpolated at the section radii,
   with span-coverage validation and midpoint tributary widths giving
   the line densities the beam consumes. `cross_check_totals` compares
   block sums against integrated loads of the same run.
2. WP5, `fsi/kinematics.py` and `fsi/nodes.py` (commit 5edd758):
   twist encoded as differential translations (dy = w + theta d,
   DLV-007 Section 4.4) with the exact linear inverse;
   `generate_node_layout` is the single source of the imported node
   CSV, the serialized `NodeOrderingMap`, and the FSIDisp writer and
   reader (FSI-R14). Formats are the dry-run evidence: comma
   separated three-column files (node CSV in the fixture's decimal
   style, FSIDisp at 17 significant digits so the file round trip is
   bit exact). WP5 acceptance met: impose, write, read, reconstruct
   at machine precision; the fixture files parse with the same
   readers.
3. WP6, `fsi/driver.py` and `fsi/state.py` (commit 3b158d0):
   `coupling_step(run_dir)` is the complete file-driven call. Phases
   keyed on the step counter with revolutions from the configured
   Omega and the export's own time increment; phase 1 zeros, phases
   2-3 window-averaged loads with relaxed updates (FSI-R07), phase 3
   declares convergence from the per-revolution tip twist change
   (FSI-R09), phase 4 instantaneous with lambda = 1 and per-step
   twist recording. Freshness asserted per call (advancing solver
   iteration; `StaleLoadsError` names `SET_AEROELASTIC_ITERATIONS 1`,
   FSI-R12); staged node map verified against the regenerated layout
   (FSI-R14); `state.json` written atomically (FSI-R13); frozen mode
   replays a stored deformation with no loads and no solve (FSI-R10);
   the convergence log states the quasi-steady validity boundary and
   carries the config hash per row (FSI-R15).

## Verification

Replay harness `tests/test_fsi_driver.py` feeds the machine archived
WP1 fixtures with patched solver iterations: phase sequence
1,2,2,3,3,3,3,3,4,4,4 on a 4-step-per-revolution schedule; relaxation
algebra checked against the formula (0.4 d_calc then 0.64 d_calc);
phase 4 unrelaxed and repeatable; stale loads refused; a run resumed
from a copied folder replays the next call byte-identically (crash
recovery); frozen mode needs no loads file; node-map disagreement and
blade-count mismatches refused. The sources schema test now covers
loads, kinematics, nodes, driver, and state. Suite at 312 tier 1
tests, ruff clean, strict docs build green. fsi/README gained the
four module sections (FSI-R16).

## Pending

1. WP7 coupled pilot on the licensed machine: near-rigid synthetic
   blade against the PHY-05 rigid baseline (HND-025), frozen replay
   reproducing the deformed solution; wire `pyfs-fsi` bare calls to
   `driver.coupling_step` when the run folder carries `config.json`
   (the dummy stays the fallback), and decide the FFT helper location
   at close (DLV-007 Section 7).
2. PLN-019 Tier 2 sweep: probe specs for the aeroelastic family
   (verified) and the SET_MOTION_FSI pair (broken), promotion via
   apply-compat; 26.100 unprobed.
3. Sign confirmation of the export-axes mapping (chordwise = export
   X, normal = export Z) via the WP7 deliberate-offset check,
   recorded in the loads module docstring.
4. The real-run totals cross-check (sectional sums against the
   integrated export of the same run) becomes a per-run assertion at
   WP7; the tier 1 tests exercise the machinery only.
