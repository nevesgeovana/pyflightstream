# RPT-170 - Geometry build: does the command order matter? (2026-10-13)

## Scope and verdicts

Planning node PFS-2081.75 (lens finding QA-008 on FR-471). FR-471 R2 lists the build as: units, trailing edges,
`SAVEAS`, then `EXPORT_SURFACE_MESH OBJ`. `cases/_geometry_emit.py` (line 195 on) emits the OBJ export FIRST, then the
units, the trailing edges and `SAVEAS`. Order A below is the code's, order B the requirement's.

| Build | Order A (code) vs B (requirement) | Right order |
|---|---|---|
| 26.124 | equivalent: identical OBJ bytes, identical marked edges, identical `.fsm` apart from 16 bytes of denormal noise | B is the one that cannot depend on a default; A is safe only while the solver's default length unit is METER (it was, here) |
| 26.125 | equivalent: identical OBJ bytes, identical marked edges, byte-identical `.fsm` | same |

The OBJ is written in the simulation length unit in force AT THE EXPORT (control C below), so an export before
`SET_SIMULATION_LENGTH_UNITS` is correct only because the unit a fresh `NEW_SIMULATION` starts in is METER on both builds,
whatever unit the source was imported in. The trailing-edge marks do not travel in the OBJ in either order; they live in the
`.fsm` only.

## What was set

Script `tests/tier3_licensed/geometry_order_probe.py`, output `gapprobes-run/out-rpt170/<build>/<case>/`. Source: the wing
stl of P4-04m (RPT-169), 288 faces, 1 m chord, 4 m span, scaled by 1000 and imported with `UNITS MILLIMETER` (coordinates
0 to 1000, so a unit slip is a factor of 1000). No solve. Hidden solver, one process at a time, free memory above 2 GB at
each launch. Per build five cases:

| Case | Order | Marking | Unit stated |
|---|---|---|---|
| A-detect | `EXPORT_SURFACE_MESH`, units, mark, `SAVEAS` | `AUTO_DETECT_TRAILING_EDGES` | METER |
| B-detect | units, mark, `SAVEAS`, `EXPORT_SURFACE_MESH` | `AUTO_DETECT_TRAILING_EDGES` | METER |
| A-file | as A | `IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER` with the 8 mid-points of the trailing line, in metres | METER |
| B-file | as B | as A-file | METER |
| C-detect | order B | `AUTO_DETECT_TRAILING_EDGES` | MILLIMETER (control: does the OBJ follow the unit?) |

## What was read

The OBJ (vertex count, extent), the `.fsm` read with `pyflightstream._fsm` (`saved_length_unit`,
`trailing_edge_midpoints`), the solver log lines on edges, and byte comparisons of the OBJ and `.fsm` of A against B.

| Quantity | 26.124 A and B (all four cases) | 26.125 A and B (all four cases) |
|---|---|---|
| OBJ vertices | 146 | 146 |
| OBJ x extent, y extent, z extent | 0 to 1, -2 to 2, -0.06 to 0.06 (metres) | same |
| OBJ A vs B | byte-identical (detect and file) | byte-identical |
| `.fsm` unit head | METER | METER |
| Marked trailing edges in the `.fsm` | 8, x = 1.0, y from -1.75 to 1.75 | same |
| Log, detect | "8 trailing edges marked on surface Wing" | same |
| Log, file | "16 trailing edges imported for boundary Wing" (two faces per edge), 8 edges in the `.fsm` | same |
| `.fsm` A vs B | file route identical; detect route differs in 16 bytes of one line: `2.78779319098761984-309` against `1.39629445073815897-309`, a denormal never-initialised value, not a setting | byte-identical |
| Control C (unit MILLIMETER, export last) | OBJ extent 0 to 1000, -2000 to 2000, +-59.99 (millimetres); `.fsm` unit head MILLIMETER; 8 edges | same |

Reading: the source in millimetres is stored in metres internally; the OBJ comes out in the unit stated by
`SET_SIMULATION_LENGTH_UNITS` (control C), and in the unit a fresh simulation starts in when none was stated yet (A),
which is METER. The marks are identical in both orders, and neither order puts them in the OBJ. A reload of the saved
`.fsm` was not run in the solver; the marks are read from the saved file itself, which is where the package reads them
(FR-471 R3).

## Conclusion per build

- **26.124**: the two orders are equivalent for the OBJ coordinates, the saved unit and the marked edges. The requirement's
  order (B) is the safer to state, since it does not rest on the default unit; the code's order (A) gives the same bytes.
- **26.125**: same, byte for byte on the `.fsm` as well.
- Not measured: whether the default unit of a fresh simulation can differ with the solver's saved preferences on another
  seat (this one is METER on both builds). Should it ever not be, order A would export in that unit while `SAVEAS` and
  the sidecar claim METER. Moving the OBJ export after the units, as FR-471 R2 states, removes that dependency at no cost.
- Side finding: `EXPORT_SURFACE_MESH` and `SAVEAS` take their path on the next line, the line after must be blank, and a
  one-line form (`SAVEAS <path>`) is refused (`Command syntax is invalid`) and leaves a hung solver until killed.

## Evidence envelope

OBJ hashes (SHA-256): 26.124 A and B, detect and file: `075d6c4cf619434c2024d41b5a625ac8eb1f81cb72c6e89a3a80a5a2d99214f7`;
26.125 A and B: `8e4dab111c57802df5832dc0c7ff1882ea5d6bc55b1804a8a77482885daa574a`; control C on 26.124:
`af5d4380450728dd152f3256b59a083133cdd18dc1d4df5f830c62829c2dd50b`, on 26.125:
`5f2d67e9e02173204f62f1579ae9ac6ac18ceeb0e4ea3ea8c2fbc5dc2c20f61b`. Files under
`gapprobes-run/out-rpt170/` (scripts, logs, OBJ, `.fsm`, `summary_main.json`). No commit was made; `src/` unchanged.
