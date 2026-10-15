"""The streamline products of a point (FR-1083, 0.40.0).

A point whose pproc states ``[streamlines]`` leaves the solver's own export
files, collected and hashed in its run record: ``<point>_slo.txt`` for the
off-body lines and ``<point>_sls.txt`` for the surface friction lines. The post
writes, from the off-body file, ``streamlines/<point>_off_body.vtk``: a legacy
VTK polydata file holding one polyline per streamline, in integration order,
with the export's per-point variables as point data (``Mach``, ``Cp_ref``,
``vtot``, ``Cp`` as scalars and ``velocity`` as the vector ``vx, vy, vz``).

THE POSITIONS ARE THE EXPORT'S, in the simulation length unit and in the
analysis frame the export names, the same convention as the solver's surface
VTK the reader opens beside it; velocities are in m/s, the coefficients
dimensionless (:data:`pyflightstream.results.OFF_BODY_STREAMLINE_COLUMNS`).

THE SURFACE FRICTION LINES GET NO VTK YET: their export has never been read by
a probe, so its grammar is unknown, and a reader written against a guess would
turn a misread file into a plausible picture. The post records that as a skip
in ``post.log``, naming the solver file that stays in the record.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream._errors import PyflightstreamError
from pyflightstream.results import OffBodyStreamlinesReport, parse_off_body_streamlines

__all__ = [
    "STREAMLINES_DIR",
    "render_streamlines_vtk",
    "write_point_streamlines",
    "write_streamline_products",
]

#: The products folder of the streamline products, beside ``sections/`` and ``probes/``.
STREAMLINES_DIR = "streamlines"

_SCALARS = ("Mach", "Cp_ref", "vtot", "Cp")


def _number(value: float) -> str:
    return repr(float(value))


def render_streamlines_vtk(report: OffBodyStreamlinesReport, *, title: str) -> str:
    """Render an off-body streamline export as legacy VTK polydata, one polyline per line.

    Parameters
    ----------
    report : OffBodyStreamlinesReport
        The parsed export.
    title : str
        The file's title line (one line).

    Returns
    -------
    str
        The VTK text, LF line ends.
    """
    columns = list(report.columns)
    rows = [row for line in report.streamlines for row in line.values]
    total = len(rows)
    lines = [
        "# vtk DataFile Version 3.0",
        " ".join(title.split())[:255],
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {total} double",
    ]
    x, y, z = (columns.index(name) for name in ("X", "Y", "Z"))
    lines += [f"{_number(row[x])} {_number(row[y])} {_number(row[z])}" for row in rows]
    sizes = [line.points for line in report.streamlines]
    lines.append(f"LINES {len(sizes)} {sum(sizes) + len(sizes)}")
    start = 0
    for size in sizes:
        lines.append(" ".join([str(size), *(str(start + k) for k in range(size))]))
        start += size
    lines.append(f"POINT_DATA {total}")
    for name in _SCALARS:
        index = columns.index(name)
        lines += [f"SCALARS {name} double 1", "LOOKUP_TABLE default"]
        lines += [_number(row[index]) for row in rows]
    vx, vy, vz = (columns.index(name) for name in ("vx", "vy", "vz"))
    lines.append("VECTORS velocity double")
    lines += [f"{_number(row[vx])} {_number(row[vy])} {_number(row[vz])}" for row in rows]
    return "\n".join(lines) + "\n"


def write_point_streamlines(ctx: Any, point: str) -> None:
    """Write one point's streamline products into a simulation's post context.

    The post step of FR-1083: the context (the post's ``SimContext``) holds
    the point's streamline exports by kind (``ctx.streamlines``), its pproc,
    its products root and its sinks; a product written is added to the
    manifest as an instant of the point's runs, and one not written is a skip
    that ``post.log`` states.

    Parameters
    ----------
    ctx : SimContext
        The simulation's post context.
    point : str
        The point's name.
    """
    exported = ctx.streamlines.get(point, {})
    spec = ctx.pproc.streamlines
    if not exported or spec is None:
        return
    for relative, outcome in write_streamline_products(
        exported, ctx.out, point, vtk=spec.vtk, target=ctx.target
    ).items():
        if isinstance(outcome, Path):
            ctx.add(outcome, {"runs": ctx.sources[point], "kind": "instant"})
        else:
            ctx.skipped[f"{STREAMLINES_DIR}/{relative}"] = outcome


def write_streamline_products(
    exported: Mapping[str, Path],
    out: Path,
    point: str,
    *,
    vtk: bool = True,
    target: Callable[[Path], Path] | None = None,
) -> dict[str, Path | str]:
    """Write one point's streamline products; say why each one not written is not.

    Parameters
    ----------
    exported : mapping of str to Path
        The point's streamline exports by kind (``streamlines_off_body``,
        ``streamlines_surface``), as collected.
    out : Path
        The products root.
    point : str
        The point's name.
    vtk : bool, optional
        The ``[streamlines] vtk`` choice; False writes nothing.
    target : callable, optional
        Archives or refuses what stands at a product's path and returns the path to
        write (the post's own rule); the path itself where None.

    Returns
    -------
    dict of str to Path or str
        Per product name relative to ``streamlines/``: the path written, or the
        reason it was not, one line.
    """
    outcomes: dict[str, Path | str] = {}
    if not vtk:
        return outcomes
    off_body = exported.get("streamlines_off_body")
    name = f"{point}_off_body.vtk"
    if off_body is not None:
        if not off_body.is_file():
            outcomes[name] = f"no off-body streamline export: {off_body.name} was not collected"
        else:
            try:
                report = parse_off_body_streamlines(
                    off_body.read_text(encoding="utf-8", errors="replace")
                )
            except (PyflightstreamError, ValueError) as error:
                outcomes[name] = f"the off-body streamline export {off_body.name}: {error}"
            else:
                path = out / STREAMLINES_DIR / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path = target(path) if target is not None else path
                _textio.write_text(
                    path,
                    render_streamlines_vtk(report, title=f"{point} off-body streamlines"),
                )
                outcomes[name] = path
    surface = exported.get("streamlines_surface")
    if surface is not None:
        outcomes[f"{point}_surface.vtk"] = (
            f"surface streamlines kept as the solver's file {surface.name}: its export "
            "grammar is not yet measured by a probe, so no VTK is written from it"
        )
    return outcomes
