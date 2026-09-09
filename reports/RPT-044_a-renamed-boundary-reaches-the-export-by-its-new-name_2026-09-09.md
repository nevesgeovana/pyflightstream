# RPT-044: a boundary renamed in the solver before the save reaches every export by its new name (2026-09-09)

The measurement PFS-2007.01 asked for: whether a boundary renamed in the
solver's interface on a saved file overrides the mesh solid name on
export. One geometry prepared by script and one row of the tier-3
geometry study, run through `pyfs-matrix run` on 26.120.

Verdict: the renamed name overrides the mesh solid name, everywhere
Build: 26.120 (build #7012026)
Row: `tests/tier3_licensed/matriz_geometry.fs` 4004, CONVERGED, 65 iterations

## The question

A geometry arrives as a mesh whose solids carry names; the solver's
interface lets a user rename a boundary, and a saved simulation can be
cited by a matrix row through `MOVING_BOUNDARIES` or a pproc group. The
node asked which name the export carries afterwards, the renamed one or
the mesh solid's, because the inventory sidecar of PFS-2028.00 can only
hold one and a row citing the other would resolve to nothing.

## How it was measured

`tests/tier3_licensed/prepare.py` grew the shape `wing_renamed`: the same
STL part as the tour's wing, called `Wing` in the STL, imported by script,
renamed with `SURFACE_RENAME 1 MainWing` (a geometry-phase command, so it
precedes the units line; the script layer refused the first placement),
and saved as `14_WING_RENAMED.fsm`. The package's own inventory reader
then wrote the sidecar off the saved file's mesh block:

    14_WING_RENAMED.boundaries.toml: boundaries = ["MainWing"]

That is the first fact: the saved file carries the renamed name in its
mesh block, and the mesh solid's name is gone from it.

Row 4004 is the tour's wing row (4001) with the renamed geometry and a
pproc artifact `p004` whose one group is `["MainWing"]`, and nothing else
cites the boundary. The steady run type does not name boundaries in the
script (`SURFACES -1`), so the script is the same as 4001's but for the
file it opens; the group is resolved by the products stage against the
loads export.

    pyfs-matrix run tests/tier3_licensed/matriz_geometry.fs --workspace tests/tier3_licensed --resume
    -> tier3_licensed/sim_4004/a+04.0 CONVERGED on 26.120, 65 iterations

## What the run left

| Where | Name carried |
|---|---|
| loads spreadsheet, per-boundary table | `MainWing` (the mesh name appears nowhere) |
| solver log, the boundary list | `MainWing` |
| saved simulation of the run (`.fsm`) | `MainWing`, three occurrences |
| Tecplot export, cp, probes, sectional loads | no boundary name at all |
| `post/matriz_geometry/4004_M10_g01.csv` | written; the stage resolved group 1 by `MainWing` |

The lift of the renamed row equals the plain wing's to every printed
decimal (CL 0.3312577 on both, 65 iterations on both), as it must: the
mesh is the same and a name changes nothing physical.

## What the measurement also showed, and where it goes

A pproc group citing the mesh solid name, `Wing`, against the renamed
file plans READY (measured with a one-row copy of the matrix on the
tier-3 inputs): a steady row's groups are resolved at products time, not
at plan time, so a name the file's inventory does not carry is not
refused before the seat is spent. That is PFS-2028.00's ground ("an
unknown name is refused naming the file and its inventory"), and this
report is its red measurement; it is not fixed here.

## What the sidecar may hold

The inventory sidecar holds the names the saved file carries, which are
the renamed ones when a rename was made before the save. A row cites
those and the export answers to them. A row citing a mesh solid name
that was renamed away will resolve to nothing, and PFS-2028.00 makes that
a refusal at plan time.
