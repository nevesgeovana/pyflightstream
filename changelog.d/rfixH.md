- FR-471 R2: Geometry builds set the simulation length unit and mark trailing
  edges before saving the FSM and exporting the OBJ. The OBJ now always uses
  the explicitly stated unit, independent of the solver's initial default.
  `EXPORT_SURFACE_MESH` preserves the current script phase, so it may follow
  unit setup and `SAVEAS` as well as geometry operations.
- REL7-001, FR-471 R2: Generated OBJ sidecars now state the exported metre
  unit instead of the source mesh's import unit. Millimetre-source builds
  retain their physical dimensions on re-import and pass valid trailing-edge
  audits for both OBJ-only and FSM-plus-OBJ outputs.
