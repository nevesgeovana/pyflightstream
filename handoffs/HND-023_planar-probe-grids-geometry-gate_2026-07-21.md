# HND-023: planar probe grids, geometry gate, flow-vis writers (2026-07-21)

## 1. Context

Geovana's instruction, planned interactively and approved before
implementation: probes as the controlled equivalent of FlightStream
volume sections, which never expose where their points fall. Planar
Cartesian grids with prescribed element size, prescription on any
custom plane, an option that discards probes falling inside the body
(from an existing `.obj`, or by exporting one from the input `.fsm`
in a pre-processing run), an optional finer band within a distance
`d` of the surface (boundary layer), plus a probe-data converter to
VTK and Tecplot for later flow visualization. Decisions confirmed in
planning: trimesh in a new `[geom]` extra (public-library policy),
frames explicit in the Python object with reference-frame emission
(culling always consistent), two-level refinement.

## 2. Delivered

* `probes/planar.py`: `FrameDefinition` (orthonormalized origin plus
  axes, the EDIT_COORDINATE_SYSTEM mirror, exact transform pair),
  `AxisSpec` (element-size uniform path, cosine and geometric
  distributions with cluster control), `PlanarProbeGrid`
  (serializable, row-major ordering contract), `RefinementBand`,
  `GeometryGateReport`, `PlannedProbes` (grid + final points + report
  serialized together: the loading contract of the future export
  parser).
* `probes/geometry.py`: guarded trimesh import naming the `[geom]`
  extra, watertight check with the physical cause (inside/outside is
  undefined on an open mesh), containment culling, two-level band
  refinement (flagged by cell-center distance, base nodes never
  duplicated, shared fine nodes emitted once, refined candidates
  culled the same way).
* `run.export_surface_mesh`: pre-processing OPEN plus
  EXPORT_SURFACE_MESH OBJ -1 run through the Executor (SRC-003
  pp.282, 307-308), didactic failure with the hidden-mode log
  excerpt.
* `post/writers.py` (the post/ layer's first code): deterministic VTK
  legacy ASCII polydata and Tecplot ASCII POINT-zone writers,
  byte-exact goldens, and `dataset_to_points` flattening the DLV-006
  far-field dataset into the same writers.
* `helpers.coordinate_frame`: optional solver-side frame creation
  returning the new index; `write_points_csv` shared between lattice
  and grids.
* Packaging: `[geom] = trimesh, rtree, scipy` (RPT-003 license
  evidence: MIT, MIT, BSD-3); CI installs `.[dev,fsi,geom]`.

## 3. Evidence and verification

Command database untouched: every emitted command already existed
with citations (EXPORT_SURFACE_MESH formats confirmed by direct
manual read, SRC-003 pp.307-308: STL, TRI, OBJ; -1 exports all
surfaces; path on the next line). 36 new tier 1 tests; suite at 265
green with docs strict. Smoke on the committed QA wing STL
(4100-triangle watertight mesh): chordwise plane at mid-span, 1275
base nodes, 35 culled inside the wing (2.7 percent), 388 band nodes
added at a third of the base spacing, 52 band candidates culled;
csv, vtk, and dat written.

## 4. Open questions

* Does the solver preserve row order and count of imported probes in
  its export? This is the single risk to the PlannedProbes ordering
  contract; the licensed round-trip probe (PLN-018) answers it and
  seeds the PLN-016 parser fixture in the same run.
* Half models: the gate refuses open meshes by design; mirroring a
  half mesh into a closed one before culling is a candidate helper if
  the need appears in practice.

## 5. Decisions

* VTK/Tecplot writers in-house rather than a meshio dependency: two
  small deterministic writers, the write_stl precedent, and Tecplot
  ASCII is not covered by the candidate library anyway (Claude).
* Emission always in the reference frame (FRAME 1); the solver-side
  FRAME parameter of PROBE_POINTS_IMPORT stays unused by the planner
  so the culling geometry and the solver geometry cannot diverge
  (Geovana's confirmed choice).
* Refinement subdivides linearly inside each cell, also on nonuniform
  axes: the band factor applies to the local cell, which is what a
  boundary-layer band needs (Claude).

## 6. Single highest-value next action

Run PLN-018 on the licensed machine: real fsm-to-obj export, culled
planar csv import, solve, probe export; verify the row-order
contract and seed the PLN-016 parser fixture from the same run.
