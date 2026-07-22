# HND-024: probe round trip verified, export parser delivered (2026-07-21)

## 1. Context

Geovana's instruction: address the single open risk of HND-023, the
row-order contract of the planar-probe loading chain. The licensed
26.120 build lives on this machine, so PLN-018 ran now instead of
waiting, and its export unblocked and closed PLN-016 (the probe
export parser) in the same session.

## 2. The round trip (reports/RPT-004)

All through the library's own code paths, on 26.120 build 7012026:
phase A built the fsm from the committed QA wing and
`run.export_surface_mesh` produced a watertight 4100-triangle obj
(the pre-processing path works against the real solver); phase B
culled the mid-span planar grid against the solver's own obj (1275
base, 35 culled, 388 band nodes, 1628 total), imported the csv,
solved (converged at iteration 58), and exported the probes.

Verdict: count and row order preserved exactly. 1628 declared = rows
= planned; row-aligned maximum relative mismatch 3.3e-4 (the export
prints four significant mantissa digits), versus 2.0e+3 against a
shuffled reference. The PlannedProbes ordering contract holds.

Side findings, recorded in RPT-004 and the probe_points.yaml notes:

* The solver's viscous coupling defaults on: 37 near-surface probes
  carried nonzero boundary-layer columns. The DLV-006 inert-BL
  assertion requires emitting SET_SOLVER_VISCOUS_COUPLING DISABLE in
  the inviscid-first campaign scripts.
* Strict-interior containment keeps on-surface points: one node on
  the leading edge exported zero velocity. A standoff margin in the
  geometry gate is a recorded option.

## 3. Parser (PLN-016 closed)

`results.parse_probe_points` follows the anchor-based idiom: count
from its label, table from the `X, Y, Z,` header to the dashed
terminator, declared-versus-parsed mismatch raises, version
cross-check warns (FR-18). `ProbePointsReport` exposes positions,
named columns, and `fields()` shaped for the post/ flow-vis writers.
`PlannedProbes.verify_positions` re-validates the row-order contract
at the export's 5e-4 precision on every load. Fixture
`tests/fixtures/probe_points_26.120.txt` is the real export's
structure with the first 12 rows. Both ran green against the raw
1628-probe export before the fixture was cut.

## 4. State at close

Suite at 272 green, docs strict green. The full chain now works end
to end on the real solver: grid, gate, csv, import, solve, export,
parse, verify, write VTK/Tecplot. Re-verify order preservation per
new build (behavior, not documentation); the compat sweep of the
fts-version-update flow is the natural place.

## 5. Single highest-value next action

Wire the chain into a case recipe (planar survey as a campaign
step), and pick up the M7 main line: G1-G5 case-level checks of the
far-field ledgers on the isolated-propeller campaign, with
SET_SOLVER_VISCOUS_COUPLING DISABLE in the inviscid-first scripts
per the RPT-004 finding.
