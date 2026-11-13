"""Build the native geometry of a run's rows with the solver, at the run (PFS-2220, G13).

Pipeline role: a matrix row that states a ``.geom.toml`` (or an IGES) with ``MESH_ROUTE`` ``native``
is generated when the matrix binds, and its ``.fsm`` is the solver's own import of the IGES.
Binding spends no seat (a plan must not), so the build happens here, at the start of
``pyfs-matrix run``: :func:`build_native_rows` runs the existing geometry build of every such row
whose ``.fsm`` is not there yet. A build that fails its audit, or a solver that fails, is not an
error of the run: the row is then left out as ``GEOMETRY_FAILED`` by the binding that follows,
with the reason warned here, and the other rows run.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream.cases.matrix import read_matrix
from pyflightstream.workspace._geometry_build import GeometryBuildError
from pyflightstream.workspace._geometry_row import (
    GEOMETRY_VARIABLE,
    plan_row_geometry,
    prepare_row_geometry,
)

__all__ = ["build_native_rows", "has_native_rows"]


def has_native_rows(rows: Sequence[Any], workspace: Any) -> bool:
    """Whether any of ``rows`` generates its geometry on the ``native`` route.

    Reads the rows' cells only: nothing is generated and the solver is not asked. A row whose
    geometry cells cannot be read is not counted; the binding reports it.
    """
    for row in rows:
        if not str(row.variables.get(GEOMETRY_VARIABLE, "")).strip():
            continue
        try:
            request = plan_row_geometry(
                row.variables, row.pol, workspace.resolve_geometry, fs_build=row.fs_build or None
            )
        except (PyflightstreamError, OSError, ValueError):
            continue
        if request is not None and request.route == "native":
            return True
    return False


def build_native_rows(
    matrix: str | Path,
    workspace: Any,
    *,
    default_build: str | None,
    fs_exe: str | Path | None = None,
    rows: Sequence[Any] | None = None,
    build: Callable[[Path, str | None, str | Path | None], tuple[Any, ...]],
    generate: Callable[..., dict[str, Any]] | None = None,
) -> list[str]:
    """Build, with the solver, the geometry of every native row whose ``.fsm`` is missing.

    Parameters
    ----------
    matrix : str or Path
        The matrix file; its active rows are read when ``rows`` is not given.
    workspace : CampaignWorkspace
        Whose ``inputs/geometries`` library holds the generated folders.
    default_build : str or None
        The build a row without ``FS_BUILD`` uses.
    fs_exe : str or Path, optional
        An executable that replaces the registered one of the build.
    rows : sequence of MatrixRow, optional
        The rows to consider, instead of the matrix's active rows.
    build : callable
        ``build(folder, build_id, fs_exe)`` runs the solver's geometry build of a folder and
        returns its results (the run layer supplies it).
    generate : callable, optional
        The generation runner, with the signature of ``run_geometry``; that function by default.

    Returns
    -------
    list of str
        The names of the geometries built by this call; a geometry already built, a row with no
        generated geometry and a build that failed are not listed (a failure warns).
    """
    built: list[str] = []
    for row in read_matrix(matrix) if rows is None else rows:
        if not str(row.variables.get(GEOMETRY_VARIABLE, "")).strip():
            continue
        try:
            name = _build_one(
                row,
                workspace,
                row.fs_build.strip() or default_build,
                fs_exe,
                solver=build,
                generate=generate,
            )
        except (PyflightstreamError, OSError, ValueError) as error:
            warnings.warn(
                f"matrix row POL {row.pol}: the native geometry was not built: {error}",
                PyflightstreamWarning,
                stacklevel=2,
            )
            continue
        if name:
            built.append(name)
    return built


def _build_one(
    row: Any,
    workspace: Any,
    build: str | None,
    fs_exe: str | Path | None,
    *,
    solver: Callable[[Path, str | None, str | Path | None], tuple[Any, ...]],
    generate: Callable[..., dict[str, Any]] | None,
) -> str:
    """Build one row's geometry; return its name, or "" when there is nothing to build."""
    request = plan_row_geometry(row.variables, row.pol, workspace.resolve_geometry, fs_build=build)
    if request is None or request.route != "native":
        return ""
    prepared = prepare_row_geometry(request, workspace.inputs_dir / "geometries", generate=generate)
    if prepared.geometry.is_file():
        return ""
    failed = [item for item in solver(prepared.folder, build, fs_exe) if not item.passed]
    if failed:
        gates = ", ".join(gate for item in failed for gate in item.failed_gates)
        raise GeometryBuildError(
            f"the solver's import of {prepared.name} failed its audit ({gates}); nothing was "
            "promoted, and the built files are kept beside it for inspection"
        )
    return str(prepared.name)
