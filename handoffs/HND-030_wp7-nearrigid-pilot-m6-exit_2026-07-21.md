# HND-030: WP7 near-rigid pilot executed, M6 exit criterion met

Date: 2026-07-21. Continuation of the HND-029 session on the author's
instruction to address the next steps on this (licensed) machine
instead of deferring; the consumed inbox prompt was annotated with its
intake note. Full run evidence:
`reports/RPT-006_wp7-nearrigid-pilot_2026-07-21.md`.

## What ran

1. WP7 wiring (commit cd30aa2): `pyfs-fsi` dispatches bare calls to
   `driver.coupling_step` when the working directory carries
   `config.json` (lazy PyNite import keeps the dummy working without
   the extra); coupled calls archive their interface files and log
   failures with tracebacks. Dummy mode stays the fallback.
2. The coupled pilot on 26.120 build 7012026 (commit dbb0671,
   RPT-006): PHY-05 flow plus the 9002 section distributions and the
   RPT-005 aeroelastic recipe, `pyfs-fsi` coupled, synthetic
   11-station structural blade at stiffness scale 1000. Both halves
   of the M6 exit criterion met:
   * near-rigid recovers the rigid PHY-05 baseline on all four
     metrics (CDi 0.51 percent rel against a 1 percent warn band, CL
     delta 3.5e-6; 54/54 coupled calls, counters equal, max written
     displacement 83 um, 149 s wall);
   * the frozen replay of the final deformation reproduces the
     coupled solution to 5e-6 on every metric (54 frozen calls, held
     rows written verbatim, 96 s wall).

## Findings folded back as code (same session)

* The sectional export rows are line densities ([N/m], [N m/m])
  despite the footer unit: `loads.py` columns renamed `*_per_m`,
  `ElasticAxisLoads` passes densities through (the width division
  would have inflated soft-blade loads about 30x), and
  `cross_check_totals` integrates over tributary widths (pilot
  closure: -643 N sectional versus -650/-661 N integrated axial).
* The export header prints dt with three decimals (0.003525 as
  .004), skewing revolutions by 13 percent: `FsiConfig` gained
  optional `time_increment_s`, which drives the phase schedule with
  the printed value cross-checked at print precision.
* Export axes on the rotating blade: Fx is axial (frame invariant,
  matches the integrated Cx), Fz in-plane in the rotating frame; the
  chordwise/normal projection of a twisted blade needs beta(r) (the
  scalar encoding dy = w + theta d survives, only the embedding
  rotates). Recorded as the soft-blade pilot prerequisite, with the
  deliberate-offset sign confirmation (RPT-006 finding 3).

Suite at 316 tier 1 tests; convergence logs committed under
`reports/fsi/`; strict docs green.

## Pending

1. PLN-020 soft-blade pilot: beta(r) projection in nodes/loads,
   stiffness scale 1, relaxation tuning, deliberate-offset sign
   confirmation, frozen replay of a substantive deformation.
2. PLN-019 Tier 2 sweep for the two FSI families (the pilot is
   secondary evidence; promotion needs the formal sweep).
3. Tier 3 registration of the near-rigid regression from this
   pilot's recipe (DLV-007 Section 8).
