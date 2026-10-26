# Mesh input example

## A complete example: a wing OBJ with its trailing edge by file

A rectangular NACA 0012 wing of chord 1 m and span 4 m, exported in
millimetres with its one surface named `wing_skin`, as a CAD tool might write
it, run at two angles of attack on FlightStream 26.124 with its trailing edge
marked by a points file. Every path below is relative to the root of a
workspace made by `pyfs-workspace init`.

**The mesh.** Your own export goes to `inputs/geometries/wing.obj`. To follow
along without one, this writes a stand-in with the package's synthetic wing,
eight panels across the span; run it from the workspace root:

<!-- skip: next -->
```python
import numpy as np

from pyflightstream.qa.geometry import WingSpec, wing_triangles

spec = WingSpec(naca="0012", chord_m=1.0, span_m=4.0, n_chord=12, n_span=8)
corners = wing_triangles(spec).reshape(-1, 3) * 1000.0  # metres to millimetres
vertices, faces = np.unique(corners.round(6), axis=0, return_inverse=True)
with open("inputs/geometries/wing.obj", "w", encoding="utf-8") as obj:
    obj.write("o wing_skin\n")
    obj.writelines(f"v {x:.4f} {y:.4f} {z:.4f}\n" for x, y, z in vertices)
    obj.writelines(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in faces.reshape(-1, 3))

from pyflightstream.workspace.inputs import write_inventory

sidecar = write_inventory("inputs/geometries/wing.obj")
with sidecar.open("a", encoding="utf-8") as stream:
    stream.write('\nfs_build = "26.124"\n[import]\nunits = "MILLIMETER"\n'
                 '[[import.operations]]\nop = "rename"\nsurface = "wing_skin"\nto = "Wing"\n'
                 '[trailing_edges.wing]\nfile = "wing.te.txt"\ntype = "STANDARD"\n')

```

The preparation above writes the measured inventory, face counts and OBJ digest,
then appends these declarations to `wing.obj.boundaries.toml`.

**The sidecar** names the surface as the file holds it, states the unit,
renames the surface to the name the study cites, and marks the trailing edge
by file. The rename is emitted by position, so after it the surface is `Wing`
whatever name the solver took from the file:

```toml
fs_build = "26.124"

[import]
units = "MILLIMETER"

[[import.operations]]
op = "rename"
surface = "wing_skin"
to = "Wing"

[trailing_edges.wing]
file = "wing.te.txt"
type = "STANDARD"
```

**The points file.** The trailing edge is the line x = 1000 mm, z = 0, and
its eight mesh edges have their mid-points every 500 mm of span:

```text title="inputs/geometries/wing.te.txt"
MILLIMETER
1000,-1750,0
1000,-1250,0
1000,-750,0
1000,-250,0
1000,250,0
1000,750,0
1000,1250,0
1000,1750,0
```

**The reference, the setup and the post-processing artifact** the row cites,
the smallest that serve this wing:

```toml title="inputs/references/r001.toml"
area_m2 = 4.0      # SREF, chord x span
chord_m = 1.0      # CREF
span_m = 4.0       # BREF

[moment_point]
x_m = 0.25         # the quarter chord, in metres like every length here
y_m = 0.0
z_m = 0.0
```

```toml title="inputs/setups/s001.toml"
NITER = 300        # SOLVER_SET_ITERATIONS
```

```toml title="inputs/pproc/p001.toml"
[groups]
"1" = "Wing"       # the name the rename gave the surface
```

**The row** names the mesh, sweeps two angles and runs on 26.124, the build
the file route was run on:

```text title="wing.fs"
POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION                    | FLIGHT_CONDITION                | SWEEP_VALUES | GEOMETRY | REF  | SET  | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
1001 |    0   |  1  | Wing     | -             | OBJ_wing_trailing_edge_by_file | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0,4.0      | wing.fsm | r001 | s001 | p001  | NONE     | -              | -     | -        | 26.124   | steady   |
```

Preview the marking pass without a solver. Then apply it with a licensed
26.124 installation and inspect the saved geometry before planning:

```text
pyfs-workspace geometry mark-boundaries inputs/geometries/wing.obj
pyfs-workspace geometry mark-boundaries inputs/geometries/wing.obj --apply --fs-exe PATH
pyfs-matrix plan wing.fs
pyfs-matrix run wing.fs
```

The preview writes nothing. Until marking has produced `wing.fsm`, planning
refuses the missing saved file and names mark-boundaries. A run opens the
saved FSM, preserving its marks; it imports no mesh or points file. The
offline example test exercises preparation, preview and that refusal.
