"""Morph a sector or a full wheel from one control file, on the OBJ (PFS-2193).

``morph`` applies the tables the morphing file holds, in one fixed order: ``[hub_rings]``,
``[repitch]``, ``[collapse_te]``, ``[wheel]``. The order is not a key: the ring route of repitch
needs the rings, and the collapse leaves a closure triangle on the first ring, so no other order
works; the wheel copies the finished sector. ``[hub_rings]`` is optional: without it,
``[repitch] hub_method`` (and ``band_width``) decide how the hub follows each blade, and a
quad-dominant hub is remeshed around each turned root (PFS-2196). Each step is the verb of the
same name with its own checks, reading its own table and the top-level ``blades`` and ``hub``.
The steps pass their mesh, boundaries file and points files to the next through a private
temporary folder; one output is written
with its boundaries file, the points files it names and ``<out>.morph.json``, and nothing is
written beside the output when any step refuses.
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputValueError, NotApplicableWarning, warn
from pyflightstream.workspace._pitch_axis import plane_basis
from pyflightstream.workspace._refine._obj import read_obj
from pyflightstream.workspace._repitch_grid import incidence
from pyflightstream.workspace._repitch_io import morphing_table
from pyflightstream.workspace._sector_read import _ON_AXIS, _snapped
from pyflightstream.workspace._wheel import (
    azimuth_range,
    nearest,
    parse_axis,
    rotate,
    sector_to_wheel,
)

__all__ = ["MORPH_ORDER", "morph_mesh"]

#: The tables ``morph`` applies, in the order it applies them.
MORPH_ORDER = ("hub_rings", "repitch", "collapse_te", "wheel")

#: The keys a morphing file states at its top level, for every table.
_TOP = ("blades", "hub")

#: The records each verb writes beside its own output, which ``morph`` gathers into one.
_RECORDS = (".hub_rings.json", ".repitch.json", ".collapse.json", ".wheel.json")


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise InputValueError(f"morph: {message}. No file was written.")


def _wheel_table(data: dict[str, Any]) -> dict[str, Any]:
    """Return ``[wheel]`` with the axis it reads: its own, else ``[repitch] rotor_axis``."""
    cfg = morphing_table(data, "wheel", ("blades", "hub"))
    _need(isinstance(cfg, dict), "[wheel] must be a table")
    for key in sorted(set(cfg) - {"blades", "hub", "copies", "center", "axis"}):
        warn(f"wheel.{key} does not apply and is skipped", NotApplicableWarning)
    repitch: dict[str, Any] = data["repitch"] if isinstance(data.get("repitch"), dict) else {}
    axis = cfg.get("axis", repitch.get("rotor_axis"))
    _need(
        axis is not None,
        "[wheel] needs the rotor axis: [repitch] rotor_axis, or [wheel] axis when the file has "
        "no [repitch]",
    )
    centre = np.asarray(cfg.get("center", [0.0, 0.0, 0.0]), dtype=float)
    _need(
        centre.shape == (3,) and bool(np.isfinite(centre).all()),
        "wheel.center must be a point [x, y, z] in the mesh's unit",
    )
    names = cfg.get("blades")
    _need(
        isinstance(names, list) and bool(names) and all(isinstance(n, str) for n in names),
        "[wheel] needs the blades: blades at the top of the file or in [wheel]",
    )
    hubs = cfg.get("hub")
    _need(
        isinstance(hubs, list) and bool(hubs) and all(isinstance(n, str) for n in hubs),
        "[wheel] reads the sector's angle from the hub: hub at the top of the file or in [wheel]",
    )
    return {**cfg, "axis": parse_axis(axis), "center": centre}


def sector_copies(points: Any, axis: Any, centre: Any) -> tuple[int | None, float]:
    """Return the copies a sector's angle about the axis makes (None when it is no 360/N)."""
    first, second = plane_basis(axis)
    q = points - centre
    radius = np.hypot(q @ first, q @ second)
    keep = radius > _ON_AXIS * float(radius.max())
    _, span = azimuth_range(np.arctan2(q[keep] @ second, q[keep] @ first))
    snapped = _snapped(span)
    copies = round(2.0 * math.pi / snapped)
    exact = copies >= 2 and snapped == 2.0 * math.pi / copies
    return (copies if exact else None), math.degrees(span)


def _seams(path: Path, axis: Any, centre: Any, copies: int) -> tuple[int, int]:
    """Return the open edges of a sector and those of them that are a seam.

    A seam edge is an open edge whose two ends, turned one copy either way about the axis, each
    land on an open node. A seam split into other edges on its far side stays a seam edge,
    so the wheel's open edges exceed the count and the wheel is refused. The landing is judged
    within half the shortest open edge, where two ends cannot be taken for one another, and
    not within the merge tolerance: judged there, a seam that the wheel leaves open (a center
    off the axis, copies that do not tile the turn) would count as no seam, and the count of
    the wheel's open edges would agree with it whatever the wheel holds.
    """
    mesh = read_obj(path)
    owners = incidence([f for fs in mesh.families.values() for f in fs])
    open_edges = [e for e, own in owners.items() if len(own) == 1]
    if not open_edges:
        return 0, 0
    ends = np.array(open_edges, dtype=np.int64)
    sides = mesh.verts[ends[:, 0]] - mesh.verts[ends[:, 1]]
    reach = 0.5 * float(np.linalg.norm(sides, axis=1).min())
    nodes = np.unique(ends.reshape(-1))
    points = mesh.verts[nodes]
    seam: set[tuple[int, int]] = set()
    for sign in (1.0, -1.0):
        hit = nearest(rotate(points, axis, centre, sign * 360.0 / copies), points, reach)
        lands = {int(v) for v, h in zip(nodes, hit, strict=True) if h >= 0}
        seam |= {(a, b) for a, b in open_edges if a in lands and b in lands}
    return len(open_edges), len(seam)


def _wheel_step(source: Path, data: dict[str, Any], target: Path) -> dict[str, Any]:
    """Copy the sector about the rotor axis into a full wheel, refusing seams left open."""
    cfg = _wheel_table(data)
    mesh = read_obj(source)
    absent = sorted(set(cfg["blades"] + cfg["hub"]) - mesh.families.keys())
    _need(not absent, f"[wheel] names families the mesh lacks: {absent}")
    hub_nodes = np.unique([v for n in cfg["hub"] for f in mesh.families[n] for v in f])
    copies, angle = sector_copies(mesh.verts[hub_nodes], cfg["axis"], cfg["center"])
    if "copies" in cfg:
        copies = cfg["copies"]
    _need(
        isinstance(copies, int) and not isinstance(copies, bool) and copies >= 2,
        f"the sector's hub spans {angle:.6g} deg about the rotor axis, which is no 360/N; "
        "state [wheel] copies, or check [wheel] center and the rotor axis",
    )
    assert isinstance(copies, int)
    result = sector_to_wheel(
        source,
        copies=copies,
        blades=cfg["blades"],
        axis=cfg["axis"].tolist(),
        hub=cfg["center"].tolist(),
        out=target,
    )
    report = dict(result.report)
    total, seams = _seams(source, cfg["axis"], cfg["center"], copies)
    _need(
        not total or bool(seams),
        f"no open edge of the sector meets another when turned by 360/{copies} deg about the "
        "rotor axis, so no seam of the wheel can close; check [wheel] copies, center and the "
        "rotor axis",
    )
    expected = copies * (total - seams)
    merged = report["open_edges"]["merged"]
    _need(
        merged == expected,
        f"the wheel's seams did not close: it holds {merged} open edges, not the {expected} its "
        "sector leaves open away from its seams; check [wheel] copies, center and the rotor axis",
    )
    report["sector_angle_deg"] = angle
    return report


def _verb(table: str) -> Callable[[Path, Path, Path], dict[str, Any]]:
    """Return the verb that applies one table: (source, control, out) to its report."""
    if table == "hub_rings":
        from pyflightstream.workspace.hub_rings import hub_rings_mesh

        return hub_rings_mesh
    if table == "repitch":
        from pyflightstream.workspace.repitch import repitch_mesh

        return repitch_mesh
    from pyflightstream.workspace.collapse_te import collapse_trailing_edge

    return collapse_trailing_edge


def _tables(data: dict[str, Any]) -> list[str]:
    """Return the tables to apply, in the fixed order, warning of what does not apply."""
    for key in sorted(set(data) - set(MORPH_ORDER) - set(_TOP)):
        warn(f"morph: {key} does not apply and is skipped", NotApplicableWarning)
    tables = [t for t in MORPH_ORDER if t in data]
    _need(
        bool(tables),
        "the morphing file holds none of [hub_rings], [repitch], [collapse_te] or [wheel]",
    )
    return tables


def _outputs(folder: Path, target: Path) -> list[Path]:
    """Return the files of the last step that belong to the output: all but its record."""
    return sorted(p for p in folder.iterdir() if not p.name.endswith(_RECORDS))


def morph_mesh(mesh: str | Path, morphing: str | Path, out: str | Path) -> dict[str, Any]:
    """Apply the tables of a morphing control file to an OBJ, in their fixed order.

    Parameters
    ----------
    mesh : str or Path
        Source OBJ, a sector or a full wheel, read only. A saved simulation (.fsm) is refused.
    morphing : str or Path
        TOML control file: ``blades`` and ``hub`` at the top, and any of ``[hub_rings]``,
        ``[repitch]``, ``[collapse_te]`` and ``[wheel]`` (a sector only).
    out : str or Path
        New OBJ. Existing outputs are refused.

    Returns
    -------
    dict
        The order applied, each step's checks and the files written, also written as
        ``<out>.morph.json``.
    """
    path, control, target = Path(mesh), Path(morphing), Path(out)
    record = Path(str(target) + ".morph.json")
    _need(
        path.suffix.lower() == ".obj",
        f"mesh {path} must be an .obj: the operation works on the OBJ, not on a saved .fsm",
    )
    _need(target.suffix.lower() == ".obj", "--out must be an .obj")
    _need(target.resolve() != path.resolve(), "--out must differ from the source")
    _need(not target.exists() and not record.exists(), "output or report exists; choose new --out")
    data = tomllib.loads(control.read_text(encoding="utf-8"))
    tables = _tables(data)
    steps: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as folder:
        current = path
        for k, table in enumerate(tables):
            stage = Path(folder) / f"{k + 1}_{table}"
            stage.mkdir()
            made = stage / target.name
            if table == "wheel":
                steps[table] = _wheel_step(current, data, made)
            else:
                steps[table] = _verb(table)(current, control, made)
            current = made
        files = _outputs(current.parent, target)
        placed = [target.with_name(p.name) for p in files]
        clash = [p.name for p in placed if p.exists()]
        _need(not clash, f"files of the output exist: {clash}; choose new --out")
        target.parent.mkdir(parents=True, exist_ok=True)
        for src, dst in zip(files, placed, strict=True):
            shutil.copyfile(src, dst)
    report = {
        "order": tables,
        "steps": steps,
        "source_sha256": file_sha256(path),
        "output_sha256": file_sha256(target),
        "files": [p.name for p in placed],
    }
    _textio.write_text(record, json.dumps(report, indent=2, default=str) + "\n")
    return report
