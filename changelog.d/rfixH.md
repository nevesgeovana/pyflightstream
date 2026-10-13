- FR-471 R2: Geometry builds set the simulation length unit and mark trailing
  edges before saving the FSM and exporting the OBJ. The OBJ now always uses
  the explicitly stated unit, independent of the solver's initial default.
  `EXPORT_SURFACE_MESH` preserves the current script phase, so it may follow
  unit setup and `SAVEAS` as well as geometry operations.
