# RPT-010: OBJ surface-mesh export group names (PLN-023 boundary inspector)

Date: 2026-07-23. Licensed machine, FlightStream 26.120
(`Flightstream_2612.exe`, solver build #7012026). Synthetic geometry
only (two generated NACA 0012 wings); no research geometry involved.

## Question

Does `EXPORT_SURFACE_MESH OBJ` write one named group per boundary, so
a fsm-to-obj export can inventory boundary name to index for the
entity-label registry (usage-feedback item T3.3, PLN-023)? And where
does the name come from?

## Method

A two-boundary model was built through the library's own script
builder: `NEW_SIMULATION`, `IMPORT` of a first STL (clear), `IMPORT`
of a second STL (no clear), `EXPORT_SURFACE_MESH OBJ -1 <file>`. Two
runs: first with both STLs carrying the same internal solid name
(`naca0012_full`), then with the second STL's solid name changed to
`tail_surface`.

## Finding

* The OBJ export writes one `o <name>` object block per boundary
  (Wavefront object lines), preceded by the header
  `# Wavefront Object File written by FlightStream`. Two imported
  boundaries produce exactly two `o` lines.
* The object name is the source mesh solid name carried through the
  import. Both boundaries with solid name `naca0012_full` exported as
  `o naca0012_full` / `o naca0012_full` (indistinguishable); after
  renaming the second STL's solid to `tail_surface`, the export read
  `o naca0012_full` / `o tail_surface`.

## Implications

* The boundary inspector is feasible: reading the `o` lines in
  creation order yields the boundary name to index map the entity
  registry needs, without touching the geometry gate (which loads the
  mesh with `force="mesh"` and collapses groups; the inspector reads
  the OBJ text separately).
* Names are only distinct when the source meshes carry distinct solid
  names. STL import propagates the solid name verbatim; a workflow
  that wants meaningful boundary names must set them on the source
  meshes (or, untested here, rely on an in-GUI boundary rename
  propagating to the export, a follow-up probe).

## Follow-up

* Whether an in-FlightStream boundary rename (geometry-tree name)
  overrides the source solid name in the OBJ export is not tested by
  this probe; it needs a GUI-renamed fsm as input.
* Implementing `inspect_boundaries()` on `run.export_surface_mesh`
  (read the `o` lines, cache by fsm sha256) is unblocked by this
  finding and is a lane A code item.
