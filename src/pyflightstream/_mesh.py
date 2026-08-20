"""The mesh reader this package reads surface geometry through.

Pipeline role: below every layer, imported by the ones that need a mesh
and importing nothing from this package. It exists for the same reason
:mod:`pyflightstream._digest` does: two layers need one thing, and
neither may import the other to get it. The probe planner's geometry
gate (a side branch) and the workspace layer's trailing-edge extraction
both read a surface mesh, and before this module there were two
hand-rolled accessors in one file and a third about to be written in
another.

WHY THE IMPORT IS DEFERRED AND NOT AT MODULE LEVEL. ``trimesh`` is a
RUNTIME dependency of this package since the promotion of 2026-08-19
(design note DD-27), so its absence is a broken installation rather than
a missing extra. It is still imported at call time, and the reason is
cost rather than availability: ``import pyflightstream`` reaches the
workspace layer eagerly, and a reader that costs 3.89 MiB and pulls its
own numpy machinery has no business being paid for by a user who only
wanted to build a script.

WHAT HAPPENS WHEN IT IS ABSENT, stated because the previous accessor
raised a didactic refusal here and this one does not. Before the
promotion trimesh arrived with the ``[geom]`` extra, so its absence was
an ordinary and recoverable state with a remedy to print. It is now a
declared runtime dependency exactly as numpy, pandas, pydantic and
xarray are, and none of those is guarded anywhere in this package: an
environment missing one is an incomplete install, and the interpreter's
own ``ModuleNotFoundError``, naming the module and nothing else, is the
same answer every other runtime dependency gives. Printing
``pip install pyflightstream[geom]`` here would now send a reader to an
extra that no longer carries the reader at all, which is the failure
mode :mod:`pyflightstream.extras` was built to make impossible.

WHAT IS STILL AN EXTRA, so the two are not confused: the SPATIAL INDEX
(``scipy`` and ``rtree``), which trimesh's containment and
distance-to-surface queries go through. That is what ``[geom]`` installs
now, and what
:class:`~pyflightstream.probes.geometry.GeometryEngineMissingError`
refuses on. Reading vertices and faces needs none of it, which is why
the trailing-edge extraction runs on a base install.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["mesh_reader", "read_mesh"]


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
