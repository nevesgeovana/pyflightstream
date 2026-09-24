# %% [markdown]
# # A wing OBJ with its trailing edge marked by a points file
#
# A raw mesh reaches a workflow row with one file beside it, its sidecar
# `<stem>.boundaries.toml`: the names of the mesh's surfaces, the unit it is
# written in, the operations that make it the body, and how its trailing edge
# is marked (the route is described on the "Mesh inputs" page). This example
# takes that route end to end without a solver:
#
# 1. write a small wing OBJ in millimetres, from the package's own geometry;
# 2. write its sidecar and its trailing-edge points file;
# 3. write the reference, setup and post-processing artifacts and one row;
# 4. plan the row, which is what `pyfs-matrix plan` runs, and render each
#    point's script with the node file the run would write beside the mesh.
#
# Nothing here needs FlightStream. The trailing-edge file route runs on
# FlightStream 26.124, the one build it was measured on (RPT-061), so the
# row names that build.

# %%
"""A wing OBJ with its trailing edge by a points file: plan and render, no solver."""

import tempfile
from pathlib import Path

import numpy as np

from pyflightstream.cases import case_at_point
from pyflightstream.cases.workflows import build_script, workflow_registry
from pyflightstream.qa.geometry import WingSpec, wing_triangles
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.matrix import resolve_matrix
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
# `wing_skin`, as a CAD tool might name it. Generated rather than committed,
# so no geometry file enters the repository.

# %%
spec = WingSpec(naca="0012", chord_m=1.0, span_m=4.0, n_chord=12, n_span=8)
corners = wing_triangles(spec).reshape(-1, 3) * 1000.0  # metres to millimetres
vertices, index = np.unique(corners.round(6), axis=0, return_inverse=True)
faces = index.reshape(-1, 3)
mesh = geometries / "wing.obj"
with mesh.open("w", encoding="utf-8") as obj:
    obj.write("o wing_skin\n")
    obj.writelines(f"v {x:.4f} {y:.4f} {z:.4f}\n" for x, y, z in vertices)
    obj.writelines(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in faces)
print(f"{mesh.name}: {len(vertices)} vertices, {len(faces)} triangles, in millimetres")

# %% [markdown]
# ## 2. The sidecar and the points file
#
# The sidecar says, in order: the surface names as the file holds them, the
# unit the file is written in, a rename to the name the study cites, and the
# trailing edge by a points file, the default route. The rename is the one
# operation the file route accepts, because the points name edges of the mesh
# as the FILE holds it and a scale or a move would carry the body away from
# them.
#
# The points file names each trailing-edge mesh edge by its MID-POINT, which
# is what the solver's import matches, under a first line naming their unit.
# Here they are read off the mesh itself: the trailing edge is the aftmost
# line of vertices, and each edge joins two neighbours along the span.

# %%
(geometries / "wing.boundaries.toml").write_text(
    'boundaries = ["wing_skin"]\n'
    "\n"
    "[import]\n"
    'units = "MILLIMETER"\n'
    "\n"
    "[[import.operations]]\n"
    'op = "rename"\n'
    'surface = "wing_skin"\n'
    'to = "Wing"\n'
    "\n"
    "[trailing_edges]\n"
    'file = "wing.te.txt"\n',
    encoding="utf-8",
)
aftmost = vertices[np.isclose(vertices[:, 0], vertices[:, 0].max())]
aftmost = aftmost[np.argsort(aftmost[:, 1])]
midpoints = (aftmost[:-1] + aftmost[1:]) / 2.0 + 0.0  # the + 0.0 writes -0.0 as 0.0
write_trailing_edge_points(geometries / "wing.te.txt", midpoints, unit="MILLIMETER")
print((geometries / "wing.te.txt").read_text(encoding="utf-8"))

# %% [markdown]
# ## 3. The artifacts and the row
#
# The row cites a reference, a setup and a post-processing artifact as every
# row does; these are the smallest that serve this wing. Every length they
# state is in metres, the simulation's unit, whatever unit the mesh is in.
# The post-processing group cites the surface by the name the rename gave it.
#
# `inputs/executables.toml` maps the build to its installation. The path is
# machine configuration, so a placeholder stands here: the plan binds the
# build without launching it, and a run on a licensed machine needs the real
# path in its place.

# %%
inputs = workspace.inputs_dir
(inputs / "references" / "r001.toml").write_text(
    "area_m2 = 4.0\nchord_m = 1.0\nspan_m = 4.0\n\n"
    "[moment_point]\nx_m = 0.25\ny_m = 0.0\nz_m = 0.0\n",
    encoding="utf-8",
)
(inputs / "setups" / "s001.toml").write_text("NITER = 300\n", encoding="utf-8")
(inputs / "pproc" / "p001.toml").write_text('[groups]\n"1" = "Wing"\n', encoding="utf-8")
(inputs / "executables.toml").write_text(f'"{BUILD}" = "FlightStream.exe"\n', encoding="utf-8")

HEADER = (
    "POL | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION "
    "| SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS "
    "| WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES"
)
ROW = (
    "1001 | 0 | 1 | Wing | - | OBJ_wing_trailing_edge_by_file "
    "| MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0,4.0 | wing.obj | r001 | s001 | p001 "
    f"| NONE | - | - | - | {BUILD} | steady |"
)
matrix = workspace.root / "wing.fs"
matrix.write_text("\n".join([HEADER, "-" * len(HEADER), ROW]) + "\n", encoding="utf-8")

# %% [markdown]
# ## 4. Plan, then the script of each point
#
# The plan spends no seat. It binds the row, reads the points file and checks
# every point against the mesh (a point farther than the tolerance from every
# mesh-edge mid-point is refused by its line), and builds each point's script
# in dry run. The render below is the same build, printed: the import in the
# sidecar's unit, the rename, the simulation's metres, and the trailing-edge
# import naming the node file the run writes beside the staged mesh, which
# holds the points converted to metres.

# %%
plan = plan_matrix(
    matrix, workspace, name="wing_study", recipes={}, recipe_registry=workflow_registry()
)
print(plan.summary())
if plan.blocked:
    raise AssertionError(f"the plan blocked a point: {[point.error for point in plan.blocked]}")

resolved = resolve_matrix(matrix, workspace, name="wing_study", fs_version=BUILD, recipes={})
(case,) = resolved.campaign.sims
for alpha in case.sweep.values:
    script = Script(BUILD)
    build_script(case_at_point(case, {case.sweep.type: alpha}), script)
    lines = script.render().splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("IMPORT_WAKE_EDGES_FROM_FILE"))
    print(f"--- alpha {alpha:+.1f} deg: the script up to the trailing-edge import ---")
    print("\n".join(lines[: at + 2]))
    node_file = script.pending_input_files[lines[at + 1]]
    # An example whose claim is a line of the script goes quiet the day the
    # line changes, so it says so instead.
    if "UNITS MILLIMETER" not in lines or "SURFACE_RENAME 1 Wing" not in lines:
        raise AssertionError("the import lost the sidecar's unit or its rename")
    if int(node_file.splitlines()[0]) != len(midpoints):
        raise AssertionError(f"the node file holds {node_file.splitlines()[0]} points")
print("--- the node file, in metres: the count, a line the solver consumes, the points ---")
print(node_file)

# %% [markdown]
# ## 5. Running it (licensed)
#
# On a licensed machine with the build registered, `pyfs-matrix plan wing.fs`
# and then `pyfs-matrix run wing.fs`, from the workspace root. The run stages
# the mesh, writes the node file beside it, and after the solve compares the
# number of edges the solver logs as imported with the points it wrote: a
# point that matches no edge is dropped in silence, so a difference records
# the point `FAILED_SCRIPT`.
#
# The mesh is in millimetres, and whether the solver's import converts a body
# into the simulation's metres is not measured on any build. If it does not,
# none of the points lies on the body and that count check says so. A mesh
# written in metres, with its points file, does not depend on the answer.
