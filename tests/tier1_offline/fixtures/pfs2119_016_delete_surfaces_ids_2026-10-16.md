# PFS-2119.016: boundary IDs after DELETE_SURFACES

Date: 2026-10-16. Licensed observation on FlightStream 26.124 and 26.125, read from
the batch-10 results of the 0.42.0 release evidence (probe PFS-2119.016-B, answered).

Question: does `DELETE_SURFACES` renumber the surviving boundaries, so that the ID a
script cites is the tree position after the deletion plus the import offset?

Observation, eight arms (OBJ and STL imports, first blade renamed or not, builds
26.124 and 26.125):

- Before the deletion the controls number the boundaries: an OBJ import gives Body 2,
  Blade1 3, Blade2 4; an STL import gives Body 1, Blade1 2, Blade2 3.
- After `DELETE_SURFACES 1` the survivors keep their IDs in all eight arms: OBJ Blade1 3
  and Blade2 4, STL Blade1 2 and Blade2 3. Renamed non-first blades (`Rotor_A`, `Zeta`)
  keep theirs likewise.
- Tree position 1 is Blade1 after the deletion, but its ID is not the position plus the
  import offset. The ID is the boundary's position in the inventory the geometry
  opened with, plus the offset.

Limits: the assign and morph step after a deletion was not part of this probe, so
nothing here says what the solver then does with the IDs. One body and two blades per
import type were measured.

Source: GEO-105 release 0.42.0 licensed EVIDENCE-5, batch 10, probe PFS-2119.016-B.
