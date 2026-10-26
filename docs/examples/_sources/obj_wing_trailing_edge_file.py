# %% [markdown]
# # A wing OBJ with its trailing edge marked by a points file
#
# Prepare a raw OBJ through `geometry mark-boundaries` before a matrix run.
# This example writes a synthetic wing in millimetres, a qualified sidecar
# and edge midpoints, then previews marking without launching FlightStream.
# The saved-state evidence for both supported builds is in the marking
# compatibility reports. A licensed apply must admit the saved marks before
# the resulting .fsm can be used by a matrix row.

# %%
"""A wing OBJ with its trailing edge by a points file: plan and render, no solver."""

import hashlib
import tempfile
from pathlib import Path

import numpy as np

from pyflightstream.qa.geometry import WingSpec, wing_triangles
from pyflightstream.workspace import CampaignWorkspace, plan_mark_boundaries
from pyflightstream.workspace.wake_edges import write_trailing_edge_points

BUILD = "26.124"

workdir = Path(tempfile.mkdtemp(prefix="pyfs_obj_wing_"))
workspace = CampaignWorkspace.init(workdir / "wing_study")
geometries = workspace.inputs_dir / "geometries"
print(f"workspace: {workspace.root}")

# %% [markdown]
# ## 1. The mesh
#
# A stand-in for a CAD export: the synthetic NACA 0012 wing of
# `pyflightstream.qa.geometry`, chord 1 m and span 4 m in eight spanwise
# panels, written as an OBJ in MILLIMETRES with its one surface named
# `Wing`, the name the study cites. Generated rather than committed,
# so no geometry file enters the repository.

# %%
spec = WingSpec(naca="0012", chord_m=1.0, span_m=4.0, n_chord=12, n_span=8)
corners = wing_triangles(spec).reshape(-1, 3) * 1000.0  # metres to millimetres
vertices, index = np.unique(corners.round(6), axis=0, return_inverse=True)
faces = index.reshape(-1, 3)
mesh = geometries / "wing.obj"
with mesh.open("w", encoding="utf-8") as obj:
    obj.write("o Wing\n")
    obj.writelines(f"v {x:.4f} {y:.4f} {z:.4f}\n" for x, y, z in vertices)
    obj.writelines(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in faces)
print(f"{mesh.name}: {len(vertices)} vertices, {len(faces)} triangles, in millimetres")

# %% [markdown]
# ## 2. The sidecar and the points file
#
# The sidecar says, in order: the surface names as the file holds them, the
# unit the file is written in, and the
# trailing edge by a points file, the default route. Geometry operations
# belong to the geometry stage before a run; this mesh already carries the
# final surface name. A scale or move would carry the body away from its
# edge points.
#
# The points file names each trailing-edge mesh edge by its MID-POINT, which
# is what the solver's import matches, under a first line naming their unit.
# Here they are read off the mesh itself: the trailing edge is the aftmost
# line of vertices, and each edge joins two neighbours along the span.

# %%
(geometries / "wing.obj.boundaries.toml").write_text(
    'boundaries = ["Wing"]\n'
    f'fs_build = "{BUILD}"\n'
    f"boundary_faces = [{len(faces)}]\nmesh_faces = {len(faces)}\n"
    f'mesh_sha256 = "{hashlib.sha256(mesh.read_bytes()).hexdigest()}"\n'
    "\n"
    "[import]\n"
    'units = "MILLIMETER"\n'
    "\n"
    "[trailing_edges.main]\n"
    'file = "wing.te.txt"\n'
    'type = "STANDARD"\n',
    encoding="utf-8",
)
aftmost = vertices[np.isclose(vertices[:, 0], vertices[:, 0].max())]
aftmost = aftmost[np.argsort(aftmost[:, 1])]
midpoints = (aftmost[:-1] + aftmost[1:]) / 2.0 + 0.0  # the + 0.0 writes -0.0 as 0.0
write_trailing_edge_points(geometries / "wing.te.txt", midpoints, unit="MILLIMETER")
print((geometries / "wing.te.txt").read_text(encoding="utf-8"))

# %% [markdown]
# ## 3. Preview marking
#
# Preview validates each midpoint against the OBJ and writes nothing.
# Apply on a licensed machine with `pyfs-matrix geometry mark-boundaries
# inputs/geometries/wing.obj --apply --fs-exe <installation>`.
# Use the admitted wing.fsm and its generated sidecar in the matrix.

# %%
plan = plan_mark_boundaries(mesh)
print(plan.script)
node_files = [
    data.decode("utf-8")
    for name, data in plan.pending.items()
    if Path(name).name.startswith("edges-")
]
if not node_files:
    raise AssertionError("marking did not prepare the edge node file")
if int(node_files[0].splitlines()[0]) != len(midpoints):
    raise AssertionError("the marking node count differs from the declared midpoints")
if "UNITS MILLIMETER" not in plan.script:
    raise AssertionError("the import lost the sidecar's unit")
print(node_files[0])
