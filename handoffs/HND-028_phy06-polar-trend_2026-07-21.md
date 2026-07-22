# HND-028: PHY-06 becomes the steady-versus-unsteady polar (2026-07-21)

## 1. Context

Same-session continuation after HND-025, on Geovana's instruction:
the second case must sweep more angles and confirm the per-alpha
trend of CL, CD, and CM between the steady and unsteady solvers.
Delivered, measured, reseeded, and validated 16 pass.

## 2. Delivered

PHY-06 now solves the PHY-01 wing at 0, 2, 4, and 6 deg in both
modes (four steady points, four 120-step time marches) and judges 16
metrics: per-alpha deltas of CL, CD (CDi + CDo; the loads Total row
carries no combined column), and CMy, plus the steady and unsteady
lift and pitching-moment slopes.

Measured on 26.120 build 7012026:

* delta_CL grows monotonically with incidence: +0.0004, +0.0013,
  +0.0022, +0.0030 at 0/2/4/6 deg, all inside the 0.005 warn band;
  the unsteady march sits slightly above steady and the gap scales
  with loading, a physically sensible wake-history signature worth
  citing in the docs.
* delta_CD stays within -0.0005 and delta_CMy within -0.0004 at
  every angle.
* CL slope: steady 4.8266/rad (reproduces PHY-01's 4.83 against the
  finite-wing anchor 5.0), unsteady 4.8515/rad (0.5 percent apart);
  CMy slope: -1.2150 versus -1.2175 (0.2 percent apart). Both
  quantities carry the same trend in both modes.
* Reference reseeded through update-reference with the redefinition
  reason (the prior 4-metric equivalence set is superseded); banded
  validation landed 16 pass, 0 warn, 0 fail
  (`PHY-26120_2026-07-21_phy06-polar-banded`). Suite at 275 tier 1
  tests.

## 3. Coordination notes

The reference-only commit discipline held this time (e089cb1 alone,
report after). One follow-up reference-only commit corrected the
reason string to cite the measurement reports instead of a handoff
number the parallel sessions had meanwhile consumed; handoff ids are
racy under concurrent sessions, report ids are stable, so reference
reasons cite reports from now on.

## 4. Open questions and contradictions

Carried from HND-025: the 26.100 backfill of the unsteady chapters
plus the PLN-012 re-probe fold into the next licensed sweep, after
which drift can cover PHY-05/06 across versions. The docs physics
chapter can now cite the polar-trend equivalence with real numbers.

## 5. Single highest-value next action

Unchanged: one licensed sweep bundling the PLN-012 re-probe and the
unsteady-chapter backfill for 26.100; then the drift matrix widens to
all six committed cases.
