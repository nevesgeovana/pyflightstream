"""Flow-visualization writers: probe data to VTK and Tecplot files.

Pipeline role: turns probe positions plus sampled fields into files
ParaView (VTK legacy ASCII polydata) and Tecplot (ASCII POINT zone)
open directly, so any probe survey (planar grid, cylindrical
lattice, or parsed solver export) becomes inspectable flow-vis data.
The writers are deterministic (fixed ``%.9e`` formatting, fixed field
order) so outputs are diffable and goldens are exact, the same policy
as the STL writer of the QA geometry.

Scalars are ``(n,)`` arrays; a ``(n, 3)`` array is written as a
vector field. Field units are whatever the caller sampled; the
writers never rescale.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import xarray as xr

__all__ = ["write_vtk_points", "write_tecplot_points", "dataset_to_points"]


def _fmt(value: float) -> str:
    return f"{value:.9e}"


def _checked(points: np.ndarray, fields: Mapping[str, np.ndarray] | None):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"points must have shape (n, 3), got {points.shape}")
    checked: dict[str, np.ndarray] = {}
    for name, values in (fields or {}).items():
        array = np.asarray(values, dtype=float)
        if array.shape not in ((len(points),), (len(points), 3)):
            raise ValueError(
                f"field {name!r} has shape {array.shape}; it must hold one scalar "
                f"or one 3-vector per probe ({len(points)} probes)"
            )
        checked[name] = array
    return points, checked


def write_vtk_points(
    path: str | Path,
    points: np.ndarray,
    fields: Mapping[str, np.ndarray] | None = None,
    *,
    title: str = "pyflightstream probe data",
) -> Path:
    """Write probe data as a VTK legacy ASCII polydata file.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination ``.vtk`` file.
    points : numpy.ndarray
        Probe positions, shape ``(n, 3)``, reference frame.
    fields : mapping of str to numpy.ndarray, optional
        Per-probe data: ``(n,)`` scalars or ``(n, 3)`` vectors,
        written in the mapping's order.
    title : str
        VTK header title line.

    Returns
    -------
    pathlib.Path
        The written file.
    """
    points, checked = _checked(points, fields)
    n = len(points)
    lines = [
        "# vtk DataFile Version 3.0",
        title,
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {n} float",
    ]
    lines += [" ".join(_fmt(c) for c in row) for row in points]
    lines.append(f"VERTICES {n} {2 * n}")
    lines += [f"1 {i}" for i in range(n)]
    if checked:
        lines.append(f"POINT_DATA {n}")
        for name, array in checked.items():
            if array.ndim == 1:
                lines.append(f"SCALARS {name} float 1")
                lines.append("LOOKUP_TABLE default")
                lines += [_fmt(value) for value in array]
            else:
                lines.append(f"VECTORS {name} float")
                lines += [" ".join(_fmt(c) for c in row) for row in array]
    destination = Path(path)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def write_tecplot_points(
    path: str | Path,
    points: np.ndarray,
    fields: Mapping[str, np.ndarray] | None = None,
    *,
    title: str = "pyflightstream probe data",
    zone: str = "probes",
) -> Path:
    """Write probe data as a Tecplot ASCII ordered POINT zone.

    Vector fields expand into three variables with ``_x``/``_y``/``_z``
    suffixes, following the Cartesian axis naming of the writers'
    coordinate columns.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination ``.dat`` file.
    points : numpy.ndarray
        Probe positions, shape ``(n, 3)``, reference frame.
    fields : mapping of str to numpy.ndarray, optional
        Per-probe data: ``(n,)`` scalars or ``(n, 3)`` vectors.
    title : str
        TITLE record.
    zone : str
        Zone name.

    Returns
    -------
    pathlib.Path
        The written file.
    """
    points, checked = _checked(points, fields)
    columns: list[tuple[str, np.ndarray]] = [
        ("X", points[:, 0]),
        ("Y", points[:, 1]),
        ("Z", points[:, 2]),
    ]
    for name, array in checked.items():
        if array.ndim == 1:
            columns.append((name, array))
        else:
            for axis, component in zip("xyz", array.T, strict=True):
                columns.append((f"{name}_{axis}", component))
    lines = [
        f'TITLE = "{title}"',
        "VARIABLES = " + " ".join(f'"{name}"' for name, _ in columns),
        f'ZONE T="{zone}" I={len(points)} ZONETYPE=ORDERED DATAPACKING=POINT',
    ]
    table = np.column_stack([values for _, values in columns])
    lines += [" ".join(_fmt(value) for value in row) for row in table]
    destination = Path(path)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def dataset_to_points(ds: xr.Dataset) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Flatten a far-field ledger dataset into writer inputs.

    Rebuilds Cartesian positions from the survey coordinates
    (``x = station R``, ``y = r sin(psi) R``, ``z = r cos(psi) R``,
    the convention of :mod:`pyflightstream.probes`) and flattens every
    ``(station, r, psi)`` data variable in the dataset's order, so a
    ledger dataset drops straight into :func:`write_vtk_points` or
    :func:`write_tecplot_points`.

    Parameters
    ----------
    ds : xarray.Dataset
        Ledger dataset with dims ``(station, r, psi)`` and the
        ``tip_radius`` attribute, as built by
        :func:`pyflightstream.farfield.lattice_dataset`.

    Returns
    -------
    tuple
        ``(points, fields)``: positions ``(n, 3)`` in simulation
        length units and the flattened scalar fields.
    """
    tip = float(ds.attrs["tip_radius"])
    station = np.asarray(ds.coords["station"])
    r = np.asarray(ds.coords["r"])
    psi = np.asarray(ds.coords["psi"])
    x, rr, pp = np.meshgrid(station, r, psi, indexing="ij")
    points = np.column_stack(
        [
            (x * tip).ravel(),
            (rr * np.sin(pp) * tip).ravel(),
            (rr * np.cos(pp) * tip).ravel(),
        ]
    )
    fields = {}
    for name, variable in ds.data_vars.items():
        if variable.dims == ("station", "r", "psi"):
            fields[name] = np.asarray(variable).ravel()
    return points, fields
