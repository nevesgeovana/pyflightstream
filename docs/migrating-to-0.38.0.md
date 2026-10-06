# Migrating to 0.38.0

> Frozen record: not edited after its release.

A workspace using 0.37.0 needs no changes. The refinement file gains one new
optional key, `elements` (`"triangles"`, the default, or `"quad-dominant"`), in a
family table and in `[refine]`; nothing has to be changed to keep the output of a
file that does not state it. Nothing is removed, no key, command
or product of 0.37.0 changes, and a matrix, setup or pproc renders the same
scripts and writes the same records as in 0.37.0. The release adds two
`pyfs-matrix` verbs that work on a panel mesh outside any matrix, `refine`
(FR-424 to FR-428) and `audit-mesh` (FR-426), and seven public names of
`pyflightstream.workspace`: the two functions and two result classes of those
verbs, and the thin blade of `pyfs-matrix degenerate` (FR-429).

## New commands

### `pyfs-matrix refine` (FR-424 to FR-428)

```text
pyfs-matrix refine MESH [FACTOR] [--families A,B] [--chordwise F] [--spanwise F]
                   [--config FILE] [--out-dir DIR] [--overwrite]
```

The command writes a finer or a coarser level of an OBJ into a new geometry
folder, `<out-dir>/<stem>_<tag>/`, which by default sits beside the folder
holding the source. The source and its folder are never modified. The level is
a geometry like any other: a row names its OBJ in the `GEOMETRY` column, and the
level's `<stem>_<tag>.boundaries.toml` is the sidecar the run reads. A refused
request writes nothing. Remeshing a family that is not a structured grid needs
the geometry extra, `pip install pyflightstream[geom]`; a mesh whose families
are all grids refines without it.

The factors come from the command, or from a refinement file
(`--config FILE`, or `<stem>.refine.toml` beside the mesh) when the command
gives none. A workspace that holds a file named `<stem>.refine.toml` beside a
mesh is unaffected until `refine` is run on that mesh.

### `pyfs-matrix audit-mesh` (FR-426)

```text
pyfs-matrix audit-mesh OBJ [--against SOURCE] [--csv FILE]
```

The command audits any OBJ, alone or against the mesh it was made from, and
writes `<stem>.audit.json` beside it. It exits 0 when every gate and check
passes, 1 when one fails (the audit is still written) and 2 when its input is
refused. Every `refine` runs the same audit on its level against the source;
there a failure is a warning and the level is still written.

Both commands are described in
[Refining or coarsening a mesh](mesh/how-to.md#refining-or-coarsening-a-mesh)
and [The refinement file and the audit](mesh/reference.md#the-refinement-file-and-the-audit).

## New public names

| name | what it is | requirement |
|---|---|---|
| `refine_mesh(mesh, factor=None, *, families=None, chordwise=None, spanwise=None, config=None, out_dir=None, overwrite=False)` | the function `pyfs-matrix refine` calls; same files, same refusals | FR-424 |
| `RefinedMesh` | what `refine_mesh` returns: `folder`, `obj`, `files`, `report` and `audit` | FR-424 |
| `audit_mesh(mesh, *, against=None, unchanged_grids=())` | the function `pyfs-matrix audit-mesh` calls | FR-426 |
| `MeshAudit` | what `audit_mesh` returns: `gates`, `checks`, `figures`, `passed`, `path` | FR-426 |
| `derive_thin_blade`, `ThinBlade`, `thin_blade_path` | the thin blade of `pyfs-matrix degenerate`, with their earlier signatures | FR-429 |

Each is imported from `pyflightstream.workspace`:

```python
from pyflightstream.workspace import audit_mesh, derive_thin_blade, refine_mesh
```

### The thin blade from Python (FR-429)

`derive_thin_blade`, `ThinBlade` and `thin_blade_path` were reached only by
`pyfs-matrix degenerate`, through the private module
`pyflightstream.workspace._degenerate`. They are now public names of
`pyflightstream.workspace`, and `pyfs-matrix degenerate` calls the public
function: for the same arguments the command and the function write the same
bytes and refuse with the same message. The private module stays importable
and holds the same objects, so a script that imported from it keeps working;
import from `pyflightstream.workspace` instead.

## New keys

The keys below belong to the refinement file, a file of its own read only by
`refine`; no matrix, setup or pproc key is added.

| key | where | what it does | requirement |
|---|---|---|---|
| `factor`, `chordwise`, `spanwise` | `[families.<name>]` | the factor of the family, or of one index direction of a grid | FR-424 |
| `method = "auto"`, `"grid"` or `"remesh"` | `[families.<name>]` | whether the family is resampled as a grid or remeshed | FR-424 |
| `axial`, `circumferential`, `axis`, `origin` | `[families.<name>]` of a body | the factors along and around an axis | FR-428 |
| `tag` | `[refine]` | the level's name in place of the factors | FR-424 |
| `NAME = ["A", "B", ...]` | `[components]` | several families written as one family of the output | FR-425 |
| `axis`, `origin`, `copies` | `[periodic]` | the two cut faces of a sector matched node for node | FR-427 |
