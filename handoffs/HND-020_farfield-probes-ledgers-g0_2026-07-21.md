# HND-020: far-field probes and ledgers, G0 green (2026-07-21)

## 1. Context

New work item specified externally: the far-field probe extraction of
design note DLV-006 (probe lattice and conservation-ledger
implementation, canonical in the author's research workspace). First
action per the instruction: the specification was copied to
`_private/design/DLV-006_probe-lattice-farfield-implementation_2026-07-21.md`
after the invariant 5 naming scrub (verified programmatically: no
forbidden names, no em/en dashes; the canonical file stays untouched).
Two other sessions worked this repository concurrently (the
legacy-case reproduction, closed as HND-019 mid-session, and the
M6/FSI line, still open); see Sec. 6.

## 2. Command database: the 26.1/26.12 delta fold

The schema now expresses per-version argument grammars:
`versions.<v>.args` overrides the entry-level args, validated against
the same layout rules, forbidden for removed versions, and resolved by
the per-version view with the existing hotfix inheritance. Every new
entry was drafted from direct reads of both manual pdfs, never from
the delta review alone:

* `CREATE_BULK_SEPARATION` (solver_settings): 26.12 four-argument
  form with SEPARATION_TYPE (SRC-003 p.342); 26.100 override without
  it (SRC-725 p.341). The 26.1 manual's own sample blocks spell
  CREARE_BULK_SEPARATION while its header spells CREATE; which token
  the 26.1 solver accepts is unverifiable from the manuals (a
  documentation typo and a parser token are independent facts) and is
  tracked as a pending probe (PLN-015).
* `VOLUME_SECTION_BOUNDARY_LAYER` (volume_sections): documented in
  26.1 only (SRC-725 p.365), removed at 26.12 with no successor in
  the family.
* `EXPORT_SURFACE_SECTIONS` (surface_sections): added at 26.12
  (SRC-003 p.365), per-section export with no filename line.
* `NEW_CCS_WING_CONTROL_SURFACE` (new ccs_wing_mesh chapter file):
  the optional SPACE/AXIS pair exists only from 26.12 (SRC-003 p.299
  versus SRC-725 p.298); 26.100 carries the eight-argument override.
* Probe family backfilled for 26.100 (SRC-725 pp.361-362, grammar
  identical to 26.120 per page-level reads).

## 3. probes module

`ProbeLattice` (pydantic, frozen, JSON round-trip) per DLV-006
Sec. 2: annular planes plus optional lateral-cylinder rings, explicit
ring edges so area weights are exact, ring centers clustered near hub
and tip by an inverse-CDF density map, uniform azimuths structural
(only the count is stored, so nonuniform spacing is unrepresentable),
z-up Cartesian convention (`y = r sin psi`, `z = r cos psi`) pinned by
a test. The serialized object is the cross-solver contract (R1): the
CFD extraction consumes the same file. Emission goes through the
version-bound `Script`: per-point NEW_PROBE_POINT loop, or the
documented PROBE_POINTS_IMPORT csv (count line plus X,Y,Z,TYPE rows)
for the ~20k-point dense lattice, then UPDATE_PROBE_POINTS and
EXPORT_PROBE_POINTS via the curated helpers. 26.000 refuses with the
didactic citation.

## 4. farfield module and gate G0

On xarray with dims `(station, r, psi)` (PLN-006 closed: xarray is a
runtime dependency on the author's instruction). One quadrature
(ring-edge rule times azimuthal rectangle rule) reused by every
ledger; azimuthal FFT layer with a uniform-spacing guard that states
the physical cause; ledgers of DLV-006 Sec. 3: mass closure (G1
machinery), axial force, transverse force with the lateral term as a
separate output variable (never silently dropped), shaft torque,
in-plane moments with the 1P harmonic loading term and the moment-arm
term kept separate (the measured disk-distortion versus
tube-deflection split), crossflow kinetic energy split into swirl
(order-0 v_theta) and induced channels with no axial-deficit term by
construction, rothalpy and the guarded irreversible deficit (negative
radicand cells masked to NaN, masked fraction reported; Euler side
only, the FlightStream ledger is reversible by design), and the
near-minus-far spurious diagnostic in counts.

G0 runs as tier 1 on synthetic exact fields: uniform flow closes
every ledger; an edge-aligned actuator-disk pressure jump recovers
the analytic thrust to 1e-12 (the ring partition makes it exact);
solid-body swirl recovers the analytic torque to quadrature accuracy
and fills only the swirl channel; pure 1P cosine loading puts the
moment entirely in the harmonic term with the quadrature and harmonic
code paths agreeing to 1e-10; plus the Parseval two-path transverse
flux check, the recorded symmetry floor (the G3 detectability
threshold), the radicand guard, and the nonuniform-azimuth refusal.

## 5. State at close

Suite at 220 tests green at close (including the open M6 session's
in-progress files); ruff clean on this session's files; mkdocs strict
build green with the four new entries rendered in the reference and
matrix. Commits: 6e14036 (database fold), 1caca63 (probes; see
Sec. 6), 2a24bf4 (farfield plus xarray), 0346512 (invariant 5 scrub),
plus this session-close commit. Next on the line (M7): the
probe-export parser blocked on a real 26.120 export fixture
(PLN-016), then G1 to G5 as case-level checks on the
isolated-propeller campaign; pending probes for the fold in PLN-015.

## 6. Concurrency record

Three sessions shared this working tree today. The legacy-case
session committed its own hunks mid-session (ac78bae, 554b79e,
87079b7), which reduced my planned selective staging of
`surface_sections.yaml` to a plain add. Its session-close artifacts
(HND-019 handoff, logbook row, STATUS focus paragraph, plan.csv
PLN-014) were staged concurrently with my probes commit and landed
inside 1caca63; the history is not rewritten (the tree stayed
consistent and the other sessions kept working on top), recorded here
instead. The committed HND-019 handoff carried one occurrence of the
forbidden predecessor-toolchain name; the invariant 5 guard caught it
and 0346512 scrubs it to a generic reference. The M6/FSI session's
uncommitted work (fsi/, conftest.py, test_fsi_config.py, RPT-002)
stays untouched and uncommitted; its one-line M6 milestone row rides
along in this close's STATUS.md commit as a factual started marker.

## 7. Decisions

* Per-version argument grammar entered the schema as a
  `versions.<v>.args` override rather than duplicate entries; the
  recorded-deviation precedent of M1/M4 applies (Claude).
* The CREARE/CREATE question stays open as a probe item; the
  database emits the header spelling for both versions and the note
  carries the discrepancy (Claude).
* Probe specs for the four folded commands were not added to
  qa/specs.py: the catalog test builds every spec against 26.120,
  and one command is 26.100-only; the pending probes live in
  PLN-015 with reasons instead (Claude).
* xarray runtime dependency: decided by the author's instruction
  that the ledgers live on xarray (PLN-006 closed).
* The rothalpy channel implements the guarded
  rothalpy-and-entropy velocity-deficit construction generically
  (ideal relative speed from the guarded radicand); the
  paper-faithful coefficient chain arrives with the Euler-side
  campaign, where its inputs exist (Claude).
