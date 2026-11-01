"""The mesh reader this package reads surface geometry through.

Pipeline role: below every layer, imported by the ones that need a mesh
and importing nothing from this package. It exists for the same reason
:mod:`pyflightstream._digest` does: two layers need one thing, and
neither may import the other to get it. The probe planner's geometry
gate (a side branch) and the workspace layer's trailing-edge extraction
both read a surface mesh through this shared accessor.

WHY THE IMPORT IS DEFERRED AND NOT AT MODULE LEVEL. ``trimesh`` is a
RUNTIME dependency of this package (design note DD-27), so its absence is a
broken installation rather than
a missing extra. It is still imported at call time, and the reason is
cost rather than availability: ``import pyflightstream`` reaches the
workspace layer eagerly, and a reader that costs 3.89 MiB and pulls its
own numpy machinery has no business being paid for by a user who only
wanted to build a script.

WHAT HAPPENS WHEN IT IS ABSENT. Trimesh is a declared runtime dependency
exactly as numpy and pydantic are, and none of those is guarded anywhere in
this package: an environment missing one is an incomplete install, and the
interpreter's own ``ModuleNotFoundError``, naming the module and nothing
else, is the same answer every other runtime dependency gives. The same
holds for the SPATIAL INDEX (``scipy`` and ``rtree``) that trimesh's
containment and distance-to-surface queries go through: both are runtime
dependencies too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["mesh_reader", "obj_group_surface", "read_mesh"]


def mesh_reader() -> Any:
    """Return the ``trimesh`` module, imported at call time.

    The ONE accessor. Every site in this package that needs the reader
    calls this rather than writing its own deferred import, so there is
    a single place where the import cost is paid and a single place a
    later decision about the reader has to be made.

    Returns
    -------
    module
        The imported ``trimesh`` module.

    Raises
    ------
    ModuleNotFoundError
        If trimesh is not installed. Deliberately not translated into a
        refusal of this package's own: see this module's docstring, it
        is a declared runtime dependency and its absence is an
        incomplete installation rather than a missing extra.

    Examples
    --------
    >>> from pyflightstream._mesh import mesh_reader
    >>> mesh_reader().__name__
    'trimesh'
    """
    import trimesh

    return trimesh


def read_mesh(path: str | Path) -> Any:
    """Load one surface mesh file through :func:`mesh_reader`.

    Parameters
    ----------
    path : str or pathlib.Path
        Mesh file (``.obj`` or ``.stl``), in the simulation's own length
        units and reference frame.

    Returns
    -------
    trimesh.Trimesh
        The loaded mesh. Nothing here inspects it; the caller states
        what it needs of it (watertightness, a spanwise extent) and
        refuses in its own vocabulary.

    Notes
    -----
    ``load_mesh`` is the typed loader; the ``load(force="mesh")`` form is
    the deprecated content-dependent compatibility wrapper.
    """
    return mesh_reader().load_mesh(str(path))


def obj_group_surface(path: Path, name: str) -> tuple[np.ndarray, np.ndarray]:
    """Read the faces of one object or group of an OBJ, as vertices and 0-based triangles.

    Polygons are split into a fan of triangles. The vertices are those the group's
    faces use. A coupled blade is its group of the imported OBJ (FR-3416, FR-3417).

    Parameters
    ----------
    path : pathlib.Path
        The OBJ file.
    name : str
        The ``o`` or ``g`` name of the group, a boundary name of the mesh.

    Returns
    -------
    tuple of numpy.ndarray
        The vertices ``(v, 3)`` and the 0-based triangles ``(f, 3)``.

    Raises
    ------
    ValueError
        If the file holds no face of ``name``.
    """
    vertices: list[list[float]] = []
    triangles: list[list[int]] = []
    current = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if words[0] in ("o", "g") and len(words) > 1:
            current = words[1]
        elif words[0] == "v" and len(words) >= 4:
            vertices.append([float(word) for word in words[1:4]])
        elif words[0] == "f" and current == name:
            index = [int(word.split("/", 1)[0]) for word in words[1:]]
            index = [i - 1 if i > 0 else len(vertices) + i for i in index]
            triangles.extend([index[0], index[k], index[k + 1]] for k in range(1, len(index) - 1))
    if not triangles:
        raise ValueError(f"{path.name} holds no face of {name!r}; the blade cannot be placed")
    faces = np.asarray(triangles, dtype=np.int64)
    used, inverse = np.unique(faces, return_inverse=True)
    return np.asarray(vertices, dtype=float)[used], inverse.reshape(-1, 3)
