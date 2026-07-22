# RPT-004: probe import/export round trip, row-order contract (PLN-018)

Date: 2026-07-21. Licensed local run on FlightStream 26.120 build
7012026 (`_private/exe/FlightStream_26120`), executed through the
library's own code paths end to end. This report is the evidence
behind the order-preservation notes in `commands/probe_points.yaml`
and the `PlannedProbes.verify_positions` /
`results.parse_probe_points` contract; the sanitized fixture
`tests/fixtures/probe_points_26.120.txt` mirrors the export of this
run (first 12 rows, count adjusted accordingly, structure and footer
verbatim).

## Setup

* Geometry: the committed synthetic QA wing (`qa/geometry`,
  `WingSpec()` defaults, 4100-triangle STL).
* Phase A: NEW_SIMULATION + IMPORT + SAVEAS built the `.fsm`;
  `run.export_surface_mesh` then ran OPEN + EXPORT_SURFACE_MESH OBJ
  -1 (SRC-003 pp.307-308) and produced a watertight 4100-triangle
  `.obj` with the exact wing bounds. The pre-processing path works
  against the real solver.
* Phase B: planar grid on the mid-span chordwise plane (element size
  0.05, boundary-layer band 0.05 at factor 3), culled against the
  solver's own obj: 1275 base nodes, 35 culled inside the wing, 388
  band nodes added, 1628 probes total. Csv written by
  `write_points_csv`, imported with PROBE_POINTS_IMPORT (METER,
  frame 1) after a converged steady solve (alpha 4 deg, incompressible,
  converged at iteration 58 of 150), then UPDATE_PROBE_POINTS and
  EXPORT_PROBE_POINTS.

## Findings

| Question | Answer |
|---|---|
| Is the imported probe count preserved in the export? | Yes: 1628 declared, 1628 rows, 1628 planned |
| Is the row order preserved? | Yes: row-aligned maximum relative position mismatch 3.3e-4, within the export's four-significant-digit mantissa format; the same metric against a shuffled reference is 2.0e+3 |
| Export columns | `X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp, s_len, momentum_thickness, disp_thick, thickness, CF, Transition` |
| Are the boundary-layer columns inert? | Geometric, not configurable: 37 near-surface probes carried nonzero BL columns; every probe away from the wall exported zeros. See the follow-up below; the first edition of this report misattributed the columns to the viscous-coupling flag |
| On-surface probes | One grid node fell exactly on the leading edge (0, 2, 0) and exported zero velocity; strict-interior containment keeps surface points by design. A standoff margin in the geometry gate is a recorded option if surveys need it |

## Verification through shipped code

`results.parse_probe_points` parses the export (count and
completeness structural, version cross-check FR-18) and
`PlannedProbes.verify_positions` re-validates the row-order contract
at the default 5e-4 tolerance; both ran green against the raw export
of this run.

## Erratum and boundary-layer follow-up (same day)

The first edition claimed the BL columns would go inert with
SET_SOLVER_VISCOUS_COUPLING DISABLE. Geovana corrected this: that
flag concerns the viscous effect on the integrated loads (CL), not
the probe columns, and the boundary-layer model lives in Advanced
Settings. A three-variant control experiment on the same case (same
build, same 1628 probes, converged at iteration 58 in every variant)
then showed:

| Variant | BL columns of the 37 near-wall probes |
|---|---|
| Defaults (original run) | populated |
| REYNOLDS_AVERAGED_DRAG_FORCES DISABLE | populated, unchanged |
| REYNOLDS_AVERAGED_DRAG_FORCES DISABLE + SET_SOLVER_VISCOUS_COUPLING DISABLE + SET_INVISCID_LOADS ENABLE | populated, unchanged |

Conclusion for build 7012026: the probe-export BL columns are
evaluated at UPDATE_PROBE_POINTS for probes near the wall regardless
of the scripting-side viscous toggles (the Advanced Settings chapter,
SRC-003 pp.344-346, offers no further boundary-layer switch beyond
those tested; LAMINAR_SEPARATION is a separation model). Their
inertness is geometric: all 1591 probes away from the surface
exported zeros even with every default on. For the far-field
campaign this simplifies the DLV-006 inert-BL assertion, since the
survey lattice keeps its probes away from the wall by construction;
the geometry gate's standoff margin (added on this finding) enforces
the same for planar grids.

## Consequences

* PLN-018 closed; the ordering risk of the planar-probe loading
  contract is retired for 26.120 build 7012026.
* PLN-016 unblocked and closed in the same session: the parser exists
  with the sanitized fixture from this run.
* Re-run this round trip when a new build is onboarded: order
  preservation is behavior, not documentation, so it stays
  build-verified (the fts-version-update skill's compat sweep is the
  natural place).
