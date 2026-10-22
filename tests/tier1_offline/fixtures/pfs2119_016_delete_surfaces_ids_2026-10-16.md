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

Source: GEO-105 release records 0.42.0, `licensed/EVIDENCE-5.md`, Batch 10 (namespace
3891a52dfe79a1f18685c33f342f386ec3ddbe72-a993925ac8bc46d5bc5f3af868dc8526, source
3891a52d), probe PFS-2119.016-B, answered on 2026-10-16. The numbers above are read
from the saved simulations that entry cites: `125Oa/before.fsm` lines 21, 24 and 27
and `125Sa` (before the deletion), `125Ob/after.fsm` lines 21 and 24 and
`125Sb/after.fsm` (after it), and the `*c` arms for the renamed blades.
