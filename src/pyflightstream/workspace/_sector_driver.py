"""The verbs that remesh a saved sector and build its power-off body (PFS-2186.06).

Pipeline role: ``pyfs-workspace geometry sector-remesh`` and ``power-off-body`` call
:func:`sector_remesh` and :func:`power_off_body`. The geometry is in
:mod:`pyflightstream.workspace._sector_remesh` (blade) and
:mod:`pyflightstream.workspace._sector_body` (spinner, nacelle), the reading in
:mod:`pyflightstream.workspace._sector_read`, the saved layout in
:mod:`pyflightstream.workspace._sector_save`. This module takes the options, converts lengths
from metres to the mesh's unit, builds, checks, writes the saved simulation through a ``.part``
file that must read back, and writes the record ``<out stem>.remesh.json`` or ``.body.json``.

Defaults that are lengths are fractions of the tip radius (``root_margin_r``, ``nose_radius_r``),
so no constant of one rotor is in the code. The tip radius is the blade's largest radius about
the axis unless it is stated, and the default used is warned. A sector whose topology is not the
one of :mod:`pyflightstream.workspace._sector_read`, or whose spinner grid folds, is warned,
nothing is written and the result says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy
from numpy.typing import NDArray

from pyflightstream._digest import file_sha256
from pyflightstream._errors import (
    InputArtifactError,
    InputValueError,
    NotApplicableWarning,
    PyflightstreamWarning,
    warn,
)
from pyflightstream._fsm import MeshReadError, saved_mesh_coordinate_unit
from pyflightstream.workspace._sector_body import (
    Builder,
    FoldedGridError,
    NacelleSpec,
    SpinnerSpec,
    nacelle,
    seam_meridian,
    spinner_closed,
    spinner_with_root,
)
from pyflightstream.workspace._sector_read import (
    Sector,
    TopologyNotFoundError,
    radius_of,
    read_sector,
)
from pyflightstream.workspace._sector_remesh import (
    Grid,
    Plan,
    blade_grid,
    read_blade,
)
from pyflightstream.workspace._sector_save import (
    QuadSink,
    RemeshResult,
    compose_sector,
    face_rows,
    mesh_checks,
    node_rows,
    read_back,
    wheel_checks,
)
from pyflightstream.workspace._wheel import (
    _NOTHING,
    Faces,
    check_wheel,
    merge_nodes,
    refuse_existing,
    refuse_the_source,
    unit_of,
    write_json,
)

__all__ = ["RemeshResult", "power_off_body", "sector_remesh"]

Array = NDArray[numpy.float64]
_AXES = ("x", "y", "z")
_UNIT_VECTOR = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


@dataclass
class Ask:
    """Every option of both verbs (the body ignores the blade-only ones)."""

    blades: list[str]
    axis: str = "x"
    chord_cells: int = 0
    le: float = 0.0
    span_cell: float = 0.0
    tip_ratio: float = 0.6
    tip_length: float = 0.2
    tip_radius: float | None = None
    spinner_theta: int = 12
    spinner_layers: int = 4
    spinner_rings: int = 7
    nacelle_theta: int = 6
    nacelle_cells: int = 28
    root_margin_r: float = 0.038
    nose_radius_r: float = 0.038
    copies: int = 0


@dataclass
class Built:
    """A built sector: the quads, the nodes in the sector's frame, and the notes of the build."""

    sink: QuadSink
    nodes: Array
    notes: dict[str, Any] = field(default_factory=dict)


def _validate(ask: Ask) -> None:
    """Refuse an option no mesh can follow, before anything is read."""
    if ask.axis not in _AXES:
        raise InputValueError(f"axis (CLI: --axis) {ask.axis!r} must be x, y or z. {_NOTHING}")
    for name in ("spinner_theta", "nacelle_theta"):
        value = getattr(ask, name)
        if value < 2 or value % 2:
            raise InputValueError(
                f"{name} (CLI: --{name.replace('_', '-')}) is {value}; the kite at the pole "
                f"needs an even number of cells, 2 or more. {_NOTHING}"
            )
    for name in ("spinner_layers", "spinner_rings", "nacelle_cells"):
        if getattr(ask, name) < 1:
            raise InputValueError(
                f"{name} (CLI: --{name.replace('_', '-')}) must be 1 or more. {_NOTHING}"
            )


def _paths(
    sector: str | Path, out: str | Path | None, tag: str, record: str, over: bool
) -> tuple[Path, Path, Path]:
    """Return the sector, the output and the record paths, refusing a missing sector or a clash."""
    path = Path(sector)
    if path.suffix.lower() != ".fsm" or not path.is_file():
        raise InputArtifactError(
            f"{path}: a sector to remesh is an existing saved simulation (.fsm). {_NOTHING}"
        )
    target = Path(out) if out is not None else path.with_name(f"{path.stem}_{tag}.fsm")
    if target.suffix.lower() != ".fsm":
        warn(
            f"out (CLI: --out) {target.name} is not the sector's kind (.fsm); the output takes "
            "the sector's kind, as the output of a route does.",
            NotApplicableWarning,
            stacklevel=3,
        )
        target = target.with_suffix(".fsm")
    rec = target.with_name(f"{target.stem}.{record}.json")
    refuse_the_source(target, path)
    refuse_existing([target, rec], over)
    return path, target, rec


def _unit_m(path: Path) -> float:
    """Return the metres per mesh unit of a saved file, warning when it states none."""
    try:
        unit = saved_mesh_coordinate_unit(path)
    except MeshReadError as error:
        raise TopologyNotFoundError(
            f"a stored coordinate unit that is measured ({error})"
        ) from error
    return unit_of(unit, path.name)


def _tip_radius(sector: Sector, ask: Ask, metres: float) -> float:
    """Return the tip radius in the mesh's unit; the blade's largest radius is warned as used."""
    if ask.tip_radius is not None:
        return ask.tip_radius / metres
    tip = float(radius_of(sector.q[sector.nodes_of(sector.blade)]).max())
    warn(
        f"tip-radius (CLI: --tip-radius) is not stated; the blade's largest radius about the axis, "
        f"{tip * metres:.6g} m, is used for the span rows and for the lengths given as fractions "
        "of it.",
        PyflightstreamWarning,
        stacklevel=4,
    )
    return tip


def _span_check(sector: Sector, expected: int | None) -> None:
    """Warn when the sector's angle is not 360/N about the axis (N the copies it is read as)."""
    n = expected or sector.copies
    angle = math.degrees(sector.span)
    if n < 2 or abs(angle - 360.0 / n) > 0.05:
        warn(
            f"the sector spans {angle:.4f} deg about the axis, which is not 360/N for a whole "
            f"number N{f' (N = {expected} was asked)' if expected else ''}; the copies will not "
            "close, and the rotation check below says so.",
            PyflightstreamWarning,
            stacklevel=4,
        )


def _not_written(path: Path, error: Exception) -> RemeshResult:
    """Warn what was not found or what folded, and return the result of a run that wrote nothing."""
    if isinstance(error, FoldedGridError):
        message = str(error)
    else:
        message = f"it lacks {error}"
    warn(
        f"{path.name} cannot be remeshed: {message}. The topology this release covers is a blunt "
        "trailing edge, rim lines from the root loop, one blade per sector and a nacelle with a "
        f"flat base (docs/geometry.md). {_NOTHING}",
        PyflightstreamWarning,
        stacklevel=4,
    )
    return RemeshResult(False)


# --- the sector-remesh verb ------------------------------------------------------------------


def _blade_faces(
    sink: QuadSink, rows: Any, grid: Grid, owner: int, groups: tuple[int, int, int]
) -> None:
    """Add the blade's quads: surface, rim edges, base row, then the tip cap, turned outward."""
    g = grid.nodes
    n_rows, n_col = rows.shape
    last, n_a = n_col - 1, len(grid.f_a) - 1
    m = n_rows // 2
    p0, p1, p2 = g[m, n_a], g[m + 1, n_a], g[m + 1, n_a + 1]
    sign = float(numpy.dot(numpy.cross(p1 - p0, p2 - p0), p0 - g[m].mean(0)))
    swap = lambda a, b, c, d, flip: (a, d, c, b) if flip else (a, b, c, d)  # noqa: E731
    for m in range(n_rows - 1):
        for j in range(last):
            a, b, c, d = rows[m, j], rows[m + 1, j], rows[m + 1, j + 1], rows[m, j + 1]
            kind, group, rim = 0, 0, None
            if j == 0:
                kind, group, rim = 1, groups[0], (rows[m, 0], rows[m + 1, 0])
            if j == last - 1:
                kind, group, rim = 1, groups[1], (rows[m, last], rows[m + 1, last])
            sink.quad(swap(a, b, c, d, sign < 0), owner, kind=kind, group=group, rim=rim)
        a, b, c, d = rows[m, last], rows[m + 1, last], rows[m + 1, 0], rows[m, 0]
        sink.quad(swap(a, b, c, d, sign < 0), owner, kind=3, group=groups[2])
    tip, n_b = rows[-1], len(grid.f_b) - 1
    for i in range(n_b - 1):
        sink.quad(swap(tip[i], tip[i + 1], tip[last - i - 1], tip[last - i], sign > 0), owner)
    sink.quad(swap(tip[n_b - 1], tip[n_b], tip[n_b + 1], tip[n_b + 2], sign > 0), owner)


def _group_of(sector: Sector, boundary: int, kind: int) -> int:
    """Return the physics group of a boundary's faces of one kind (rim 1, base 3)."""
    values = set(sector.group[(sector.owner == boundary) & (sector.kind == kind)].tolist())
    if len(values) != 1:
        raise TopologyNotFoundError(
            f"one group on the faces of kind {kind} of {sector.names[boundary - 1]!r}"
        )
    return values.pop()


def _build_bodies(
    sector: Sector, ask: Ask, sink: QuadSink, rows: Any, *, given: Array, tip: float
) -> Builder:
    bodies = numpy.unique(
        sector.tri[(sector.owner == sector.spinner) | (sector.owner == sector.nacelle)]
    )
    reach = 2.0 * float(radius_of(sector.q[bodies]).max())
    builder = Builder(given, sink, (sector.centre, 0.5 * sector.span), reach, {sector.spinner})
    spec = SpinnerSpec(
        ask.spinner_theta,
        ask.spinner_rings,
        ask.spinner_layers,
        ask.root_margin_r * tip,
        ask.nose_radius_r * tip,
    )
    mer = seam_meridian(sector, sector.nodes_of(sector.spinner), pole=True)
    spinner_with_root(builder, sector.spinner, mer, [int(n) for n in rows[0]], spec)
    return builder


def _nacelle(
    sector: Sector, ask: Ask, builder: Builder, owner: int, groups: tuple[int, int] | None = None
) -> None:
    """Add the nacelle of a sector with the (rim, base) groups it carries in the source.

    ``groups`` replaces the source's: the body has one rim group and one base region.
    """
    mer = seam_meridian(sector, sector.nodes_of(sector.nacelle, base=False), pole=False)
    rim, base = groups or (
        _group_of(sector, sector.nacelle, 1),
        _group_of(sector, sector.nacelle, 3),
    )
    spec = NacelleSpec(ask.nacelle_theta, ask.nacelle_cells, rim, base)
    nacelle(builder, owner, mer, spec)


def _termination(sector: Sector, source: Any, rows: Any, sink: QuadSink) -> list[list[int]]:
    """Return the wake termination rows: the root end of each rim line, as face and slot."""
    groups = list(sector.parsed.mesh["term"][2]) if sector.parsed.mesh["term"] else []
    tris = sink.array()
    faces: list[int] = []
    slots: list[int] = []
    for group in groups:
        if group not in source.groups:
            raise TopologyNotFoundError(
                f"a wake termination only on the blade's rim groups, not {group}"
            )
        target = int(rows[0, 0 if group == source.groups[0] else rows.shape[1] - 1])
        hit = int(numpy.flatnonzero((tris == target).any(axis=1))[0])
        faces.append(hit + 1)
        slots.append(int(numpy.flatnonzero(tris[hit] == target)[0]) + 1)
    return [faces, slots, groups] if groups else []


def _build_remesh(sector: Sector, ask: Ask, plan: Plan) -> tuple[Built, Grid, Any, Any]:
    """Build the remeshed sector: blade first, then the spinner and the nacelle."""
    source, all_rings = read_blade(sector)
    grid = blade_grid(sector.q, all_rings, plan)
    n_rows, n_col = int(grid.nodes.shape[0]), int(grid.nodes.shape[1])
    rows = numpy.arange(n_rows * n_col).reshape(n_rows, n_col)
    sink = QuadSink()
    groups = (source.groups[0], source.groups[1], source.base_group)
    _blade_faces(sink, rows, grid, sector.blade, groups)
    n_blade = len(sink)
    builder = _build_bodies(
        sector, ask, sink, rows, given=grid.nodes.reshape(-1, 3), tip=plan.tip_radius
    )
    n_spinner = len(sink)
    _nacelle(sector, ask, builder, sector.nacelle)
    notes = {
        "rows": n_rows,
        "columns": n_col,
        "blade_faces": n_blade,
        "spinner_faces": n_spinner - n_blade,
        "skipped": source.skipped,
    }
    return Built(sink, builder.all_nodes(), notes), grid, rows, source


def _widths(grid: Grid) -> dict[str, Any]:
    """Measure the chord law on every row: the growth ratio and the spread of the fixed part."""
    na = len(grid.f_a) - 1
    sides = ((grid.nodes[:, : na + 1][:, ::-1], grid.f_a), (grid.nodes[:, na:], grid.f_b))
    worst, spread, fixed_lo, fixed_hi = 0.0, 0.0, math.inf, 0.0
    for pts, frac in sides:
        n_fix = int(numpy.sum(numpy.diff(frac) > numpy.diff(frac).max() - 1e-9))
        w = numpy.linalg.norm(numpy.diff(pts, axis=1), axis=2)
        grow, fixed = w[:, :-n_fix], w[:, -n_fix:]
        worst = max(worst, float((grow[:, :-1] / grow[:, 1:]).max()))
        spread = max(spread, float(((fixed.max(1) - fixed.min(1)) / fixed.min(1)).max()))
        fixed_lo, fixed_hi = min(fixed_lo, float(fixed.min())), max(fixed_hi, float(fixed.max()))
    return {
        "growth_worst_ratio": worst,
        "monotonic": worst <= 1.0,
        "fixed_spread": spread,
        "fixed_width_min": fixed_lo,
        "fixed_width_max": fixed_hi,
    }


def _spreads(grid: Grid) -> dict[str, float]:
    """Return the radius spread within a row: root, mid blade, tip and worst from mid out."""
    rr = radius_of(grid.nodes.reshape(-1, 3)).reshape(grid.nodes.shape[:2])
    span = numpy.ptp(rr, axis=1)
    return {
        "root": float(span[0]),
        "mid": float(span[grid.mid_row]),
        "tip": float(span[-1]),
        "outboard_worst": float(span[grid.mid_row :].max()),
    }


def _area(nodes: Array, tris: Any) -> float:
    pts = nodes[tris]
    return float(
        numpy.linalg.norm(numpy.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1).sum()
        / 2
    )


def _rim_counts(sector: Sector, sink: QuadSink, copies: int) -> dict[str, int]:
    """Count the trailing-edge edges and groups of the sector and of its wheel."""
    flagged = [i for i, s in enumerate(sink.slot) if s is not None]
    groups = {(sink.owner[i], sink.group[i]) for i in flagged}
    return {
        "sector_edges": len(flagged),
        "sector_groups": len(groups),
        "wheel_edges": len(flagged) * copies,
        "wheel_groups": len({g for o, g in groups if o == sector.blade}) * copies
        + len({g for o, g in groups if o != sector.blade}),
    }


def _checks(sector: Sector, built: Built, grid: Grid, rows: Any, ask: Ask) -> dict[str, Any]:
    """Measure the acceptance checks of the method on the built sector."""
    sink, nodes = built.sink, built.nodes
    tris = sink.array()
    world = sector.frame.world(nodes)
    scale = float(numpy.ptp(world, axis=0).max())
    blade_mask = numpy.array(sink.owner) == sector.blade
    spinner_nodes = set(tris[numpy.array(sink.owner) == sector.spinner].ravel().tolist())
    src_tris = sector.tri[sector.owner == sector.blade]
    copies = sector.copies
    return {
        "radius_spread": _spreads(grid),
        "chord": _widths(grid),
        "root_loop_shared": len(spinner_nodes & set(rows[0].tolist())),
        "root_loop_nodes": int(rows.shape[1]),
        "edges": mesh_checks(tris, nodes),
        "blade_area": {"new": _area(nodes, tris[blade_mask]), "source": _area(sector.q, src_tris)},
        "trailing_edges": _rim_counts(sector, sink, copies),
        "rotation": wheel_checks(
            world, tris, numpy.array(_UNIT_VECTOR[ask.axis]), copies, 1e-9 * scale
        ),
        "mesh_size": scale,
    }


def _summary(report: dict[str, Any]) -> list[str]:
    """Return the printed checks of a remesh report, in the order of the method's table."""
    c, f = report["checks"], report["faces"]
    spread, chord, edges = c["radius_spread"], c["chord"], c["edges"]
    rot, area, te = c["rotation"]["invariance"], c["blade_area"], c["trailing_edges"]
    return [
        f"triangles in a pair-less face (blade, spinner, nacelle): {report['triangles']}",
        f"quads: blade {f['blade']}, spinner {f['spinner']}, nacelle {f['nacelle']}",
        f"radius spread within a row: root {spread['root']:.3g}, mid blade {spread['mid']:.3g}, "
        f"tip {spread['tip']:.3g}, worst from mid blade out {spread['outboard_worst']:.3g}",
        f"chord widths: growth worst ratio {chord['growth_worst_ratio']:.3f} (monotonic "
        f"{chord['monotonic']}), fixed width {chord['fixed_width_min']:.6g} to "
        f"{chord['fixed_width_max']:.6g}, fixed spread {chord['fixed_spread']:.3f}",
        f"root loop nodes shared with the spinner: {c['root_loop_shared']} of "
        f"{c['root_loop_nodes']}",
        f"rotation {rot['angle_deg']:g} deg of the wheel: nodes mapped {rot['nodes_mapped']} of "
        f"{rot['nodes']}, faces mapped {rot['faces_mapped']} of {rot['faces']}; control turn "
        f"maps {c['rotation']['control']['faces_mapped']} of {c['rotation']['control']['faces']}",
        f"trailing edges in the wheel: {te['wheel_edges']}, with {te['wheel_groups']} groups",
        f"blade area {area['new']:.5f} against source {area['source']:.5f}",
        f"spinner O-grid folded cells: 0; non-manifold edges {edges['non_manifold_edges']}, "
        f"degenerate faces {edges['degenerate_faces']}, open edges {edges['open_edges']}",
    ]


def _write(
    path: Path, sector: Sector, built: Built, term: list[list[int]], target: Path
) -> dict[str, int]:
    """Write the sector through a .part file that must read back; return triangles per boundary."""
    world = sector.frame.world(built.nodes)
    text = compose_sector(sector.parsed, built.sink, world, term)
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(text.encode("latin-1"))
    try:
        back = read_back(part, tuple(sector.names))
    except ValueError:
        part.unlink(missing_ok=True)
        raise
    part.replace(target)
    return back.triangles


def _plan(sector: Sector, ask: Ask, metres: float) -> Plan:
    tip = _tip_radius(sector, ask, metres)
    return Plan(
        ask.chord_cells, ask.le, ask.span_cell / metres, ask.tip_ratio, ask.tip_length / metres, tip
    )


def sector_remesh(
    sector: str | Path,
    *,
    blades: list[str],
    chord_cells: int,
    le: float,
    span_cell: float,
    axis: str = "x",
    tip_ratio: float = 0.6,
    tip_length: float = 0.2,
    tip_radius: float | None = None,
    spinner_theta: int = 12,
    spinner_layers: int = 4,
    spinner_rings: int = 7,
    nacelle_theta: int = 6,
    nacelle_cells: int = 28,
    root_margin_r: float = 0.038,
    nose_radius_r: float = 0.038,
    out: str | Path | None = None,
    overwrite: bool = False,
) -> RemeshResult:
    """Rebuild a saved sector's blade, spinner and nacelle as full-quad surfaces (PFS-2186.06).

    Parameters
    ----------
    sector : str or Path
        A saved simulation of one sector: one blade, a spinner and a nacelle with a flat base,
        the blade's quads ending in two trailing-edge rim lines (a blunt trailing edge).
    blades : list of str
        The one boundary that is the blade; the spinner and the nacelle are found from it
        (the spinner is the boundary the blade's root loop lies on, the nacelle the one with a
        flat base).
    chord_cells : int
        Chord cells on the side with fewer; the other side has one more.
    le : float
        The first chord cell, as a fraction of the side's arc.
    span_cell : float
        The constant span cell, in metres.
    axis : str
        ``x``, ``y`` or ``z``, the axis the sector is a sector about.
    tip_ratio, tip_length : float
        The last span cell over the constant one, and the length in metres of the finer region.
    tip_radius : float, optional
        The tip radius in metres; default the blade's largest radius about the axis, warned.
    spinner_theta, spinner_layers, spinner_rings, nacelle_theta, nacelle_cells : int
        Cells of the spinner around the sector, O-grid layers around the root, rings forward to
        the nose, and the nacelle's cells around the sector and along its meridian. The two
        around-the-sector counts are even.
    root_margin_r, nose_radius_r : float
        The spinner's margin ahead of the root loop and the radius of its nose kite, as
        fractions of the tip radius (0.038 is 0.07 m on a 1.8288 m tip).
    out : str or Path, optional
        The remeshed sector; default ``<sector stem>_remesh.fsm`` beside it.
    overwrite : bool
        Replace existing outputs.

    Returns
    -------
    RemeshResult
        ``written`` False, with a warning that names what was not found, when the topology is
        not the one of this release or the spinner grid folds (raise ``spinner_layers``).

    Raises
    ------
    InputArtifactError
        A sector that is no existing saved simulation, or an output that exists.
    InputValueError
        An option no mesh can follow (an odd cell count, a chord law that cannot be reached).
    """
    ask = Ask(
        blades, axis, chord_cells, le, span_cell, tip_ratio, tip_length, tip_radius,
        spinner_theta, spinner_layers, spinner_rings, nacelle_theta, nacelle_cells,
        root_margin_r, nose_radius_r,
    )  # fmt: skip
    _validate(ask)
    path, target, record = _paths(sector, out, "remesh", "remesh", overwrite)
    try:
        sec = read_sector(path, blades, axis)
        metres = _unit_m(path)
        _span_check(sec, None)
        plan = _plan(sec, ask, metres)
        built, grid, rows, source = _build_remesh(sec, ask, plan)
        term = _termination(sec, source, rows, built.sink)
        checks = _checks(sec, built, grid, rows, ask)
        triangles = _write(path, sec, built, term, target)
    except (TopologyNotFoundError, FoldedGridError) as error:
        return _not_written(path, error)
    done = Done(built, checks, triangles, target, record, metres)
    return _remesh_result(path, sec, ask, plan, done)


@dataclass
class Done:
    """What a remesh run produced: the build, its checks, the file and the record paths."""

    built: Built
    checks: dict[str, Any]
    triangles: dict[str, int]
    target: Path
    record: Path
    metres: float


def _remesh_result(path: Path, sec: Sector, ask: Ask, plan: Plan, done: Done) -> RemeshResult:
    """Assemble, write and return the record of a remesh run."""
    built, checks, triangles = done.built, done.checks, done.triangles
    target, record, metres = done.target, done.record, done.metres
    owners = numpy.array(built.sink.owner)
    quads = {
        k: int((owners == b).sum()) // 2
        for k, b in (("blade", sec.blade), ("spinner", sec.spinner), ("nacelle", sec.nacelle))
    }
    report = {
        "source": path.name,
        "source_sha256": file_sha256(path),
        "families": {
            "blade": sec.names[sec.blade - 1],
            "spinner": sec.names[sec.spinner - 1],
            "nacelle": sec.names[sec.nacelle - 1],
        },
        "axis": ask.axis,
        "sector": {
            "copies": sec.copies,
            "angle_deg": math.degrees(sec.span),
            "centre_deg": math.degrees(sec.centre),
        },
        "tip_radius_m": plan.tip_radius * metres,
        "options": {k: v for k, v in vars(ask).items() if k != "blades"},
        "faces": {**quads, "triangles_total": len(built.sink), "nodes": len(built.nodes)},
        "triangles": triangles,
        "checks": checks,
        "build": built.notes,
        "out": target.name,
    }
    files = [target, write_json(record, report)]
    return RemeshResult(True, target, files, report, _summary(report))


# --- the power-off-body verb -----------------------------------------------------------------


def _turned(nodes: Array, degrees: float) -> Array:
    """Return the nodes turned about the axis (the first coordinate) by an angle."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    out = nodes.copy()
    out[:, 1], out[:, 2] = c * nodes[:, 1] - s * nodes[:, 2], s * nodes[:, 1] + c * nodes[:, 2]
    return out


def _copies_of(sink: QuadSink, nodes: Array, copies: int, tol: float) -> tuple[QuadSink, Array]:
    """Return the sink and nodes of the copies about the axis, merged across the seams."""
    stack = numpy.vstack([_turned(nodes, 360.0 * k / copies) for k in range(copies)])
    root = merge_nodes(stack, tol)
    used = numpy.unique(root)
    index = numpy.full(len(stack), -1, dtype=numpy.int64)
    index[used] = numpy.arange(len(used))
    node = index[root]
    full = QuadSink()
    for k in range(copies):
        for nodes4, owner, kind, group, rim in sink.quads():
            mapped = tuple(int(node[x + k * len(nodes)]) for x in nodes4)
            rim_new = (
                None
                if rim is None
                else (int(node[rim[0] + k * len(nodes)]), int(node[rim[1] + k * len(nodes)]))
            )
            full.quad(mapped, owner, kind=kind, group=group, rim=rim_new)  # type: ignore[arg-type]
    return full, stack[used]


def _body_physics(sector: Sector) -> list[str]:
    """Return the physics block of the body: the nacelle's base region and rim group."""
    phys, lines = sector.parsed.phys, sector.parsed.lines
    name = sector.names[sector.nacelle - 1]
    if name not in phys["base_names"] or name not in phys["te_names"]:
        raise TopologyNotFoundError(f"a base region and a trailing-edge group named {name!r}")
    ib, it = phys["base_names"].index(name), phys["te_names"].index(name)
    out = lines[phys["p0"] : phys["p0"] + 4] + ["1", name, f" {phys['base_rows'][0][ib]},"]
    out += [f"{row[ib]}," for row in phys["base_rows"][1:]]
    out += ["1", name, f"{phys['te_values'][it]},", "0"]
    return out + lines[phys["after"] : phys["p_end"] - 1] + [f"{phys['base_codes'][ib]},"]


def _body_text(sector: Sector, sink: QuadSink, nodes: Array) -> str:
    """Return the saved body: two boundaries, the physics of the nacelle, the rest as the source."""
    parsed = sector.parsed
    lines, mesh = parsed.lines, parsed.mesh
    first = mesh["heads"][0][0]
    heads = [mesh["heads"][sector.spinner - 1], mesh["heads"][sector.nacelle - 1]]
    records: list[str] = []
    for k, h in enumerate(heads):
        records += [f"{first + k}, {h[1]}, {h[2]}, {h[3]}", h[4], h[5]]
    total = str(len(sink))
    text = lines[: mesh["start"] + 1] + [total, str(first + 1), "2", *records, total]
    text += [*face_rows(sink, mesh["rows"]), lines[mesh["tail"]], *node_rows(nodes), "0"]
    text += lines[mesh["end"] : parsed.phys["p0"]] + _body_physics(sector)
    return parsed.newline.join(text + lines[parsed.phys["p_end"] :])


def _body_report(
    sector: Sector, ask: Ask, sink: QuadSink, nodes: Array, world: Array
) -> dict[str, Any]:
    """Measure the body: faces, edges, and the rotation of one sector's turn."""
    tris = sink.array()
    owners = numpy.array(sink.owner)
    faces = Faces(tris.ravel(), numpy.full(len(tris), 3))
    scale = float(numpy.ptp(world, axis=0).max())
    turn = check_wheel(
        world,
        faces,
        numpy.array(_UNIT_VECTOR[ask.axis]),
        numpy.zeros(3),
        copies=ask.copies,
        tol=1e-9 * scale,
    )
    return {
        "faces": {
            "triangles": len(tris),
            "quads": len(tris) // 2,
            "spinner": int((owners == 1).sum()) // 2,
            "nacelle": int((owners == 2).sum()) // 2,
            "nodes": len(nodes),
        },
        "blade_faces": 0,
        "edges": mesh_checks(tris, nodes),
        "rotation": turn,
        "mesh_size": scale,
    }


def _body_summary(report: dict[str, Any]) -> list[str]:
    f, e, r = report["faces"], report["edges"], report["rotation"]["invariance"]
    return [
        f"body: {f['quads']} quads ({f['triangles']} faces), {f['nodes']} nodes; spinner "
        f"{f['spinner']}, nacelle {f['nacelle']}, no blade surface",
        f"rotation {r['angle_deg']:g} deg: nodes mapped {r['nodes_mapped']} of {r['nodes']}, "
        f"faces mapped {r['faces_mapped']} of {r['faces']}",
        f"open edges {e['open_edges']}, non-manifold edges {e['non_manifold_edges']}, "
        f"degenerate faces {e['degenerate_faces']}",
    ]


def _build_body(sector: Sector, ask: Ask, tip: float) -> Built:
    """Build one sector of the power-off body: a closed spinner and the nacelle of the remesh."""
    bodies = numpy.unique(
        sector.tri[(sector.owner == sector.spinner) | (sector.owner == sector.nacelle)]
    )
    reach = 2.0 * float(radius_of(sector.q[bodies]).max())
    sink = QuadSink()
    builder = Builder(numpy.zeros((0, 3)), sink, (sector.centre, 0.5 * sector.span), reach, {1})
    spec = SpinnerSpec(ask.spinner_theta, ask.spinner_rings, 0, 0.0, ask.nose_radius_r * tip)
    spinner_closed(
        builder, 1, seam_meridian(sector, sector.nodes_of(sector.spinner), pole=True), spec
    )
    _nacelle(sector, ask, builder, 2, (1, 1))
    return Built(sink, builder.all_nodes())


def power_off_body(
    sector: str | Path,
    *,
    blades: list[str],
    copies: int,
    axis: str = "x",
    spinner_theta: int = 6,
    spinner_rings: int = 12,
    nacelle_theta: int = 6,
    nacelle_cells: int = 28,
    nose_radius_r: float = 0.038,
    tip_radius: float | None = None,
    out: str | Path | None = None,
    overwrite: bool = False,
) -> RemeshResult:
    """Write the power-off body of a saved sector: a closed spinner and the remesh's nacelle.

    The body is the whole turn (``copies`` sectors merged across the seams), full quad, with
    no blade surface. Its nacelle is built by the function ``sector-remesh`` uses, with the same
    arguments, so the nacelle of the remeshed wheel and of this body have the same nodes.

    Parameters
    ----------
    sector : str or Path
        The saved sector the body is made from (the source, as ``sector-remesh`` reads it).
    blades : list of str
        The boundary that is the blade; it gives the spinner, the nacelle and the tip radius.
    axis : str
        ``x``, ``y`` or ``z``, the axis the sector is a sector about.
    copies : int
        Sectors in a turn; the sector's angle is warned when it is not 360/copies.
    spinner_theta, spinner_rings, nacelle_theta, nacelle_cells : int
        Cells of the closed spinner around the sector and along its meridian, and of the nacelle.
    nose_radius_r : float
        The nose kite's radius, a fraction of the tip radius.
    tip_radius : float, optional
        The tip radius in metres; default the blade's largest radius, warned.
    out : str or Path, optional
        The body; default ``<sector stem>_body.fsm``.
    overwrite : bool
        Replace existing outputs.

    Returns
    -------
    RemeshResult
        ``written`` False, with a warning naming what was not found, for another topology.

    Raises
    ------
    InputArtifactError
        A sector that is no existing saved simulation, or an output that exists.
    InputValueError
        An odd cell count, or fewer than two copies.
    """
    ask = Ask(
        blades,
        axis,
        spinner_theta=spinner_theta,
        spinner_rings=spinner_rings,
        nacelle_theta=nacelle_theta,
        nacelle_cells=nacelle_cells,
        nose_radius_r=nose_radius_r,
        tip_radius=tip_radius,
        copies=copies,
    )
    if copies < 2:
        raise InputValueError(
            f"copies (CLI: --copies) is {copies}; a body needs 2 or more. {_NOTHING}"
        )
    _validate(ask)
    path, target, record = _paths(sector, out, "body", "body", overwrite)
    try:
        sec = read_sector(path, blades, axis)
        metres = _unit_m(path)
        _span_check(sec, copies)
        built = _build_body(sec, ask, _tip_radius(sec, ask, metres))
        full, nodes = _copies_of(built.sink, built.nodes, copies, 1e-6 / metres)
        world = sec.frame.world(nodes)
        report = _body_report(sec, ask, full, nodes, world)
        _write_body(sec, full, nodes, target)
    except (TopologyNotFoundError, FoldedGridError) as error:
        return _not_written(path, error)
    if report["faces"]["quads"] >= 2000:
        warn(
            f"the power-off body has {report['faces']['quads']} quads; the method's bound is "
            "under 2000.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    report.update(source=path.name, source_sha256=file_sha256(path), out=target.name, copies=copies)
    return RemeshResult(
        True, target, [target, write_json(record, report)], report, _body_summary(report)
    )


def _write_body(sector: Sector, sink: QuadSink, nodes: Array, target: Path) -> None:
    """Write the body through a .part file that must read back as two boundaries."""
    world = sector.frame.world(nodes)
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(_body_text(sector, sink, world).encode("latin-1"))
    names = (sector.names[sector.spinner - 1], sector.names[sector.nacelle - 1])
    try:
        read_back(part, names)
    except ValueError:
        part.unlink(missing_ok=True)
        raise
    part.replace(target)
