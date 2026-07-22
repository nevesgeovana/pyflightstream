# RPT-006: WP7 near-rigid coupled pilot on FlightStream 26.120 (2026-07-21)

> Addendum (same day, RPT-007): the subsequent soft-blade pilot and a
> controlled probe series showed that build 7012026 does not apply the
> FSIDisp deformation to boundaries attached to a rotary motion, while
> a motionless wing control morphs correctly with the same commands
> and files. The acceptance below therefore stands as loop-mechanics
> evidence, but "recovers the rigid baseline" is trivially insensitive
> in this build: see RPT-007 Section 5 for the reinterpretation.

The WP7 coupled pilot of the M6 FSI line (DLV-007 Section 7), executed
on the licensed machine with FlightStream 26.120 build 7012026 and
`pyfs-fsi` in coupled mode (the WP6 driver behind the WP1 entry
point). Vehicle: the PHY-05 flow verbatim (generic BladeSpec blade,
one meshed blade under PERIODIC 6, 54 unsteady steps of 10 deg at rpm
472.83), plus the two section distributions of the proven 9002 case
and the aeroelastic toolbox block of the RPT-005 recipe. Structural
configuration: synthetic 11-station model on the blade span (0.274 to
1.829 m), pitch-axis elastic axis, geometric pitch from the BladeSpec
beta law, stiffness scale factor 1000 (near-rigid), 33 structural
nodes (three per station), phases 0.5 rev wake, lambda 0.4, 0.5 rev
window. Config hash
`9e81ff408da6b50ec49187c0780277fc962d023652037b079cfb6df1834d7058`.

## Acceptance (M6 exit criterion): both halves met

1. Near-rigid recovery of the rigid baseline. The coupled run's final
   loads against the PHY-05 reference (`qa/references/PHY-05.yaml`,
   rigid, same build):

   | Metric | Coupled near-rigid | Rigid reference | Delta | Band verdict |
   |---|---|---|---|---|
   | CL | -0.0000977 | -0.0001012 | +3.5e-6 | PASS (abs, warn 0.002) |
   | CDi | -0.0449457 | -0.0451749 | +2.3e-4 (0.51% rel) | PASS (rel, warn 1%) |
   | CDo | 0.0006914 | 0.0007011 | -9.7e-6 | PASS (abs, warn 5e-4) |
   | CMy | 0.0285262 | 0.0286429 | -1.2e-4 (0.41% rel) | PASS (rel, warn 1%) |

   Maximum written displacement 8.3e-5 m over the 33 nodes: the blade
   is rigid to solver resolution and the full coupling machinery
   (loads export, parse, solve, relax, FSIDisp) ran on every step.

2. Frozen replay reproduces the deformed solution (FSI-R10). A second
   run holding the coupled run's final FSIDisp as
   `fsi_frozen_displacements.txt` (54 frozen calls, no loads parsing,
   no solve; the held rows written verbatim on every call):

   | Metric | Coupled | Frozen replay | Delta |
   |---|---|---|---|
   | CL | -0.0000977 | -0.0000975 | +2e-7 |
   | CDi | -0.0449457 | -0.0449506 | -4.9e-6 |
   | CDo | 0.0006914 | 0.0006913 | -1e-7 |
   | CMy | 0.0285262 | 0.0285292 | +3.0e-6 |

## Loop mechanics evidence

54 executable calls for 54 time steps, call and step counters equal
throughout (FSI-R12; the solver iteration advanced on every call),
phases 1/2/3 executed 15/16/23 times per the revolution schedule, one
completed revolution recorded with tip twist 4.4e-4 deg, convergence
log with the config hash on every row (committed:
`reports/fsi/PILOT-26120_2026-07-21_nearrigid_convergence.csv` and
`_frozen_convergence.csv`). Cost budget: 149 s wall for the coupled
run (about 2.8 s per step, of which roughly half is the per-call
Python process start of `pyfs-fsi`), 96 s for the frozen replay.
Secondary evidence for PLN-019: the aeroelastic command family was
again exercised end to end; formal Tier 2 promotion still goes
through the validity sweep.

## Findings

1. Sectional loads are line densities. The blade family's Fx column
   integrated over the tributary widths gives -643 N against the
   integrated spreadsheet's axial force of -650 N (Cx) to -661 N
   (CDi) for the same run, while the raw sum (-20699) overshoots by
   the inverse width: the `FS_SurfaceSection_Loads.txt` rows are per
   unit span ([N/m], [N m/m]) despite the footer naming the
   computation unit ("Force Units: Newtons" versus coefficients).
   Correction applied in the same session: `fsi/loads.py` renames the
   columns `*_per_m`, `ElasticAxisLoads` passes densities through
   (the earlier width division would have inflated loads about 30x on
   a soft blade), and `cross_check_totals` integrates, never sums.
2. The export header prints the time increment with three decimals:
   dt 0.003525 s prints as `.004`, which skewed the driver's
   revolution bookkeeping by 13 percent (phase boundaries at steps
   16/32 instead of 18/36). Correction applied: `FsiConfig` gained
   optional `time_increment_s`; when set it drives the phase schedule
   and the printed value is cross-checked at print precision.
3. Export axes on a rotating blade: the Fx column matches the axial
   (rotor axis) integrated force and is invariant under blade
   rotation; Fz is the in-plane component in the rotating frame (its
   width-integrated value, +667 N, matches no static-frame component,
   as expected for a rotating reference). The cut-plane axes coincide
   with the section chordwise/normal axes only at zero local blade
   angle, so the chordwise/normal projection of a twisted blade
   requires the local blade angle beta(r); the same applies to the
   node layout (LE/TE offsets lie along the local twisted chord;
   ez x chord = normal makes the scalar encoding dy = w + theta d
   invariant, only the embedding rotates). This projection, plus the
   deliberate elastic-axis-offset sign confirmation, is the recorded
   prerequisite of the soft-blade pilot; it does not affect the
   near-rigid acceptance (displacements at the micrometer level).
4. Phase 4 never triggered in 54 steps (revolution 2 completes at
   step 64 under the printed-dt schedule); the recording phase's
   in-solver behavior remains exercised only by the offline harness.

## Pending

* Soft-blade pilot (stiffness scale 1) after the beta(r) projection
  lands: real aeroelastic response, relaxation tuning, deliberate-
  offset sign confirmation, frozen replay of a substantive
  deformation.
* PLN-019 formal Tier 2 sweep for the two FSI families.
* Tier 3 registration of the near-rigid regression (DLV-007 Section
  8) using this pilot's recipe.
