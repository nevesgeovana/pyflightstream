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
```

**The sidecar** names the surface as the file holds it, states the unit,
renames the surface to the name the study cites, and marks the trailing edge
by file. The rename is emitted by position, so after it the surface is `Wing`
whatever name the solver took from the file:

```toml title="inputs/geometries/wing.boundaries.toml"
boundaries = ["wing_skin"]

[import]
units = "MILLIMETER"

[[import.operations]]
op = "rename"
surface = "wing_skin"
to = "Wing"

[trailing_edges]
file = "wing.te.txt"
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
1001 |    0   |  1  | Wing     | -             | OBJ_wing_trailing_edge_by_file | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0,4.0      | wing.obj | r001 | s001 | p001  | NONE     | -              | -     | -        | 26.124   | steady   |
```

With `inputs/executables.toml` naming your 26.124 installation, as for any
row ([workspaces and workflows](../workspace-and-workflows.md)), plan it and run
it from the workspace root:

```text
pyfs-matrix plan wing.fs
pyfs-matrix run wing.fs
```

The plan spends no seat. It binds the row, reads the points file and checks
every point against the mesh, and builds each point's script; a point that
misses the mesh, a missing unit or a missing log among the outputs stops it
here. The script it builds for each point starts:

```text
NEW_SIMULATION
IMPORT
UNITS MILLIMETER
FILE_TYPE OBJ
FILE <the point's staged copy of wing.obj>
CLEAR

SURFACE_RENAME 1 Wing
SET_SIMULATION_LENGTH_UNITS METER
IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER
<the folder the point runs in>/wing.wake_nodes.txt
```

and the node file the run writes in that folder holds the count, the
coordinate line the solver consumes, and the eight points in metres:

```text
8
0,0,0
1.0,-1.75,0.0
1.0,-1.25,0.0
1.0,-0.75,0.0
1.0,-0.25,0.0
1.0,0.25,0.0
1.0,0.75,0.0
1.0,1.25,0.0
1.0,1.75,0.0
```

**Read the unit once more before copying this.** The mesh is in millimetres,
as a CAD export usually is, which puts the example on the one question above
that no build has answered: whether `IMPORT` converts the body into metres. If
it does not, the body the solver holds is not the one the node file describes,
none of this example's points lies on it, and the count check records each
point `FAILED_SCRIPT` rather than letting a solve of the wrong body pass.
Written in metres, the mesh and the points file both, the example does not
depend on the answer.

The suite runs this example as printed: `tests/tier1_offline/test_mesh_inputs_page.py`
writes every titled block above into a temporary workspace, runs the python
block there, plans the matrix with the command above, and renders both points
without a solver. It fails when the scripts the package builds and the two
blocks above differ, and when a key a sidecar block on this page writes is not
one the sidecar's readers read, or the other way round. A runnable script of
the same route is `examples/obj_wing_trailing_edge_file.py`.
