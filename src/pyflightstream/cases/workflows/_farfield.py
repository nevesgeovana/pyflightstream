"""What the plan adds to a row's script for the far field (FR-455, FR-459 R4).

The emission half of the far-field family: where a row's pproc artifact carries
``[farfield]``, the builders call these functions to declare the outputs the far
field reads, to add a section distribution over the families no declared one
covers, to switch the wake on in the VTK export, and to lay the far-field
plane or survey lattice as probe points. What is reused, added, not applicable
or refused is the resolver's (:mod:`pyflightstream.cases.farfield_inputs`);
the geometry is laid out by :mod:`pyflightstream.probes.layouts`. A row whose
artifact has no ``[farfield]`` reaches none of this, so its script keeps its
bytes.

The plane and the lattice are chosen once (:func:`farfield_shapes`): a
declared ``[[probes]]`` shape is reused when it is the far field's geometry
after layout, or, where ``[farfield]`` states no geometry, when it is the one
declaration that qualifies; what is not declared is appended after every
declared probe. Every chosen shape is recorded on the script for the run
record, and post matches the exported positions to it (PFS-2081.56, .58).
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import CampaignConfigError, SimCase, classify_outputs, select_families
from pyflightstream.cases._farfield_spec import FarfieldSpec, LatticeShape
from pyflightstream.cases.farfield_inputs import (
    ROTOR_RUN_TYPES,
    FarfieldResolution,
    applies,
    few_stations_warning,
    resolve_farfield,
    traced_family,
)
from pyflightstream.commands import CommandRegistry
from pyflightstream.probes.layouts import (
    FarfieldPlane,
    emit_probe_import,
    emit_probe_points,
    farfield_plane,
    lattice_points,
    rectangle_points,
    write_points_csv,
    write_probe_csv,
)
from pyflightstream.script import Script

from ._names import _inventory
from ._rows import (
    _angle,
    _from_metres,
    _states_a_rotor_speed,
    _the_names_a_rotor_answers_to,
    _variable,
)

__all__ = [
    "FARFIELD_PLOT_PARAMETERS",
    "FarfieldShape",
    "declared_lattice_points",
    "declared_lattices",
    "farfield_lattice",
    "farfield_outputs",
    "farfield_plane_of",
    "farfield_probes",
    "farfield_resolution",
    "farfield_sections",
    "farfield_shapes",
    "needs_fresh_probes",
    "plan_record",
    "warn_declared_inside",
    "wants_wake",
]

#: The fluid-plot parameters an unsteady row samples at every far-field point:
#: the velocity and the pressure coefficient on the reference velocity, which a
#: rotor at rest still has (FR-455 R9).
FARFIELD_PLOT_PARAMETERS: tuple[str, ...] = ("VX", "VY", "VZ", "CP_REF")
#: The reference frame of the far-field fluid plots (frame 1, the global frame).
_PLOT_FRAME = 1
_SECTION_COMMAND = "NEW_SURFACE_SECTION_DISTRIBUTION"
_MESH_SUFFIXES = (".obj", ".stl")
#: Two laid-out probe sets are one declaration when every coordinate agrees at
#: the fifth decimal of the simulation's unit, the precision the script writes
#: a probe position in (FR-455 R2, PFS-2081.56).
_SAME_POSITION = 1.01e-5


def _spec(case: SimCase) -> FarfieldSpec | None:
    return getattr(case.pproc, "farfield", None) if case.pproc is not None else None


def _run_type(case: SimCase) -> str:
    return str(case.recipe or "steady")


def _rotor(case: SimCase) -> bool:
    return _run_type(case) in ROTOR_RUN_TYPES or (
        _run_type(case) == "steady" and _states_a_rotor_speed(case)
    )


def _analyses(spec: FarfieldSpec, case: SimCase) -> list[str]:
    selected = []
    if spec.trefftz is not None:
        selected += [f"trefftz:{variant}" for variant in spec.trefftz.variant]
    if spec.ledgers is not None:
        selected.append("ledgers")
    run_type, rotor = _run_type(case), _rotor(case)
    return [analysis for analysis in selected if not applies(analysis, run_type, rotor=rotor)]


def wants_wake(case: SimCase) -> bool:
    """Whether the row's far field reads the wake export (Trefftz B applies)."""
    spec = _spec(case)
    return spec is not None and "trefftz:wake" in _analyses(spec, case)


def _needs_plane(case: SimCase) -> bool:
    spec = _spec(case)
    return spec is not None and "trefftz:plane" in _analyses(spec, case) and not _rotor(case)


def _needs_lattice(case: SimCase) -> bool:
    spec = _spec(case)
    if spec is None:
        return False
    analyses = _analyses(spec, case)
    return "ledgers" in analyses or ("trefftz:plane" in analyses and _rotor(case))


def needs_fresh_probes(case: SimCase) -> bool:
    """Whether the row's far field lays probes, so a steady point starts from none."""
    return _needs_plane(case) or _needs_lattice(case)


def _normal(case: SimCase) -> bool:
    """Whether the row's ``[[probes]]`` entries are all of kind normal (FR-417)."""
    if case.pproc is None:
        return False
    try:
        return bool(case.pproc.samples_normal_probes())
    except CampaignConfigError:
        return False


def farfield_outputs(case: SimCase, workflow: str, names: Sequence[str]) -> list[str]:
    """Return ``names`` with the exports the far field reads added (FR-455 R3).

    An ``[exports]`` entry set to false that the far field needs is turned on
    for this row, with a WARNING naming the entry and the analysis.
    """
    spec = _spec(case)
    if spec is None:
        return list(names)
    analyses = _analyses(spec, case)
    wanted: list[tuple[str, str, str]] = []
    if "trefftz:sections" in analyses:
        wanted.append(("sectional_loads", "{name}_sloads.txt", "trefftz:sections"))
    if "trefftz:wake" in analyses:
        wanted.append(("vtk", "{name}.vtk", "trefftz:wake"))
    if needs_fresh_probes(case):
        # FR-455 R9: an unsteady row whose [[probes]] entries are of kind normal
        # samples the far field with them, as probe points exported once.
        kind = "plots" if workflow.startswith("unsteady") and not _normal(case) else "probes"
        wanted.append((kind, f"{{name}}_{kind}.txt", "trefftz:plane or ledgers"))
    out = list(names)
    present = classify_outputs(out)
    exports = dict(case.pproc.exports) if case.pproc is not None else {}
    for kind, template, analysis in wanted:
        if kind in present:
            continue
        if exports.get(kind) is False:
            warn(
                f"case {case.sim_id!r}: [exports] {kind} = false in the pproc artifact "
                f"{case.pproc_id!r}, and the far field's {analysis} needs it; it is turned on "
                "for this row (FR-455 R3).",
                PyflightstreamWarning,
                stacklevel=2,
            )
        out.append(template)
    return out


def _selected(case: SimCase, spec: FarfieldSpec, inventory: Sequence[str]) -> list[str]:
    is_blade = case.pproc.is_blade if case.pproc is not None else (lambda name: False)
    groups = select_families(
        spec.families, inventory, is_blade, aliases=_the_names_a_rotor_answers_to(case)
    )
    chosen: list[str] = []
    for group in groups:
        for name in group or list(inventory):
            if name not in chosen:
                chosen.append(name)
    return chosen


def _covered(case: SimCase, inventory: Sequence[str]) -> set[str]:
    """Return the families a declared distribution cuts alone in XZ of the reference axes.

    A block of several families is an aggregate Trefftz A cannot trace, so it
    covers none of them and the plan adds their own (:func:`traced_family`,
    the rule post reads by, PFS-2081.100).
    """
    covered: set[str] = set()
    if case.pproc is None:
        return covered
    aliases = _the_names_a_rotor_answers_to(case)
    for entry in case.pproc.sections.distributions:
        if "XZ" not in entry.planes or entry.frame.strip().upper() not in ("MRP", "REFERENCE"):
            continue
        for group in select_families(entry.families, inventory, case.pproc.is_blade, aliases):
            name = traced_family(group, inventory)
            if name is not None:
                covered.add(name)
    return covered


def _warn_few_stations(
    case: SimCase, inventory: Sequence[str], reused: Sequence[str], mirror: bool
) -> None:
    """Warn per reused family whose declared distribution has too few stations (FR-451 R10).

    The stations per side of a family are those of the densest declared
    distribution that covers it: its count on a mirrored half model, half its
    count on a full one, as the plan lays its own (``stations`` per side).
    """
    spec = _spec(case)
    if case.pproc is None or spec is None or spec.trefftz is None or not reused:
        return
    sections = case.pproc.sections
    aliases = _the_names_a_rotor_answers_to(case)
    per_side: dict[str, int] = {}
    for entry in sections.distributions:
        if "XZ" not in entry.planes or entry.frame.strip().upper() not in ("MRP", "REFERENCE"):
            continue
        count = int(entry.count or sections.count)
        side = count if mirror else count // 2
        for group in select_families(entry.families, inventory, case.pproc.is_blade, aliases):
            name = traced_family(group, inventory)
            if name is not None:
                per_side[name] = max(per_side.get(name, 0), side)
    for name in reused:
        few = few_stations_warning(name, per_side.get(name, 0), spec.trefftz.stations)
        if few:
            warn(f"case {case.sim_id!r}: {few}.", PyflightstreamWarning, stacklevel=3)


@dataclass(frozen=True)
class FarfieldShape:
    """One far-field probe set as the plan chose it: the plane or the lattice (FR-455 R2).

    The ONE selection planning, emission and post use (PFS-2081.56, .58): the
    plan lays an ``added`` shape and reuses a ``declared`` one, the run record
    carries :meth:`record`, and post rebuilds the points from it and matches
    every exported position to them before it integrates.

    Attributes
    ----------
    kind : {"plane", "lattice"}
        The Trefftz C plane of a wing, or the survey lattice.
    source : {"added", "declared"}
        Laid by the plan, or the ``[[probes]]`` declaration reused.
    entry : int or None
        The number of the ``[[probes]]`` entry reused, from 1; None when added.
    points_m : numpy.ndarray
        ``(n, 3)`` positions in metres, in the reference frame, in the order
        the probes are laid.
    geometry : dict
        What rebuilds ``points_m``: for a plane its center, the free-stream
        direction, its half extents and its spacing (m); for a lattice the
        :class:`~pyflightstream.probes.lattice.ProbeLattice` in metres, the
        shaft axis letter, the origin (m) and the frame its recorded probe
        positions are stated in.
    lattice : ProbeLattice or None
        The lattice ``points_m`` is laid from, in metres; None for a plane.
        It is not part of the record, whose ``geometry`` carries it as data.
    """

    kind: str
    source: str
    entry: int | None
    points_m: np.ndarray
    geometry: dict[str, Any]
    lattice: Any = field(default=None, compare=False, repr=False)

    def record(self) -> dict[str, Any]:
        """Return the shape as the run record and ``plan.json`` carry it (FR-455 R4)."""
        return {
            "kind": self.kind,
            "source": self.source,
            "entry": self.entry,
            "count": len(self.points_m),
            **self.geometry,
        }


def _same_points(first: np.ndarray, second: np.ndarray, native_per_m: float) -> bool:
    """Whether two laid-out point sets are one, in order, at the precision a probe is written.

    The script writes a probe position rounded to five decimals of the
    simulation's unit, so two declarations whose every coordinate agrees there
    are the same probes (FR-455 R2: same frame, same points after layout).
    """
    if first.shape != second.shape:
        return False
    a = np.round(np.asarray(first, dtype=float) * native_per_m, 5)
    b = np.round(np.asarray(second, dtype=float) * native_per_m, 5)
    return bool(np.all(np.abs(a - b) <= _SAME_POSITION))


def _emitted(entry: Any) -> bool:
    """Whether a ``[[probes]]`` entry lays its shapes as points (not a cited points file)."""
    return bool(entry.parameters) and not entry.points_file


def _plane_shape(
    source: str, entry: int | None, center: np.ndarray, direction: np.ndarray, grid: tuple
) -> FarfieldShape:
    half_width, half_height, spacing = (float(value) for value in grid)
    laid = farfield_plane(
        tuple(center),
        direction=tuple(direction),
        distance=0.0,
        half_width=half_width,
        half_height=half_height,
        spacing=spacing,
    )
    geometry = {
        "center_m": [float(v) for v in center],
        "direction": [float(v) for v in direction],
        "half_width_m": half_width,
        "half_height_m": half_height,
        "spacing_m": spacing,
    }
    return FarfieldShape("plane", source, entry, laid.points, geometry)


def _qualifying_plane(rectangle: Any, axes: np.ndarray, reach: float) -> tuple | None:
    """Return a declared rectangle as a far-field plane (center, grid), or None (FR-455 R2).

    It qualifies when it IS a Trefftz C plane of this point: a uniform grid of
    one spacing both ways with an odd count each way (so its center is a
    point, as the plan lays one), its u edge along the plane's y and its v
    edge along its z (normal to this point's free stream), downstream of the
    body.
    """
    origin = np.asarray(rectangle.origin, dtype=float)
    edge_u = np.asarray(rectangle.along_u, dtype=float) - origin
    edge_v = np.asarray(rectangle.along_v, dtype=float) - origin
    if rectangle.points_u % 2 == 0 or rectangle.points_v % 2 == 0:
        return None
    width, height = float(np.linalg.norm(edge_u)), float(np.linalg.norm(edge_v))
    spacing = width / (rectangle.points_u - 1)
    if not math.isclose(spacing, height / (rectangle.points_v - 1), rel_tol=1e-9):
        return None
    aligned = float(edge_u @ axes[1]) / width, float(edge_v @ axes[2]) / height
    if min(aligned) < 1.0 - 1e-9:
        return None
    center = origin + edge_u / 2.0 + edge_v / 2.0
    if float(center @ axes[0]) <= reach:
        return None
    return center, (width / 2.0, height / 2.0, spacing)


def _plane_choice(case: SimCase, native_per_m: float) -> FarfieldShape:
    """Choose the wing's Trefftz C plane: a declared one, or the one the plan lays (FR-455 R2)."""
    spec = _spec(case)
    trefftz = spec.trefftz if spec is not None else None
    if trefftz is None:
        raise CampaignConfigError(f"case {case.sim_id!r}: the far-field plane needs a trefftz")
    direction = _free_stream(case)
    extent = _extent_m(case, direction, native_per_m)
    laid = farfield_plane_of(case, extent_m=extent)
    middle = (len(laid.y) // 2) * len(laid.z) + len(laid.z) // 2
    bref = float(getattr(case.reference, "span_m", None) or 0.0)
    grid = tuple(value * bref for value in trefftz.plane_bref())
    own = _plane_shape("added", None, laid.points[middle], direction, grid)
    mrp = np.asarray(getattr(case.reference, "moment_point_m", None) or (0.0, 0.0, 0.0))
    reach = float(mrp @ laid.axes[0]) if extent is None else extent
    qualifying: list[FarfieldShape] = []
    identical: list[FarfieldShape] = []
    entries: Sequence[Any] = case.pproc.probes if case.pproc is not None else []
    for number, entry in enumerate(entries, start=1):
        if not _emitted(entry) or entry.frame.strip().upper() != "REFERENCE" or entry.scale != "m":
            continue
        for rectangle in entry.rectangles:
            # Laid as `[[probes]]` lays it, in the simulation's unit, then in metres.
            native = rectangle_points(rectangle, scale=native_per_m)
            points = np.array(native, dtype=float) / native_per_m
            if _same_points(points, own.points_m, native_per_m):
                identical.append(replace(own, source="declared", entry=number))
            chosen = _qualifying_plane(rectangle, laid.axes, reach)
            if chosen is not None:
                qualifying.append(_plane_shape("declared", number, chosen[0], direction, chosen[1]))
    if not trefftz.states_plane and len(qualifying) == 1:
        return qualifying[0]
    return identical[0] if identical else own


def _lattice_placement(
    case: SimCase, script: Script, frames: Any, shape: LatticeShape, native_per_m: float
) -> tuple[Any, str, np.ndarray]:
    """Return a lattice, its shaft axis letter and its origin in metres (reference frame)."""
    if shape.rotor is not None:
        return _rotor_placement(case, shape)
    origin = _frame_origin(case, script, frames, str(shape.frame), native_per_m)
    return shape.build(float(shape.tip_radius_m or 0.0)), "X", origin


def _rotor_placement(case: SimCase, shape: LatticeShape) -> tuple[Any, str, np.ndarray]:
    """Return a rotor's lattice, its shaft axis letter and its hub in metres (FR-459 R2)."""
    rotor = case.rotors.get(str(shape.rotor))
    if rotor is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: a lattice names the rotor {shape.rotor!r}, which the "
            f"reference does not declare ({', '.join(sorted(case.rotors)) or 'none'})"
        )
    axis = rotor.axis if isinstance(rotor.axis, str) else ""
    if axis.strip().upper() not in ("X", "Y", "Z"):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the rotor {shape.rotor!r} states its axis as "
            f"{rotor.axis!r}; a lattice is laid along an axis letter X, Y or Z"
        )
    origin = np.array([rotor.x_m, rotor.y_m, rotor.z_m])
    return shape.build(rotor.diameter_m / 2.0), axis, origin


def _lattice_shape(
    case: SimCase,
    script: Script,
    frames: Any,
    shape: LatticeShape,
    native_per_m: float,
    *,
    source: str,
    entry: int | None,
) -> FarfieldShape:
    lattice, axis, origin = _lattice_placement(case, script, frames, shape, native_per_m)
    points = lattice_points(lattice, axis=axis) + origin
    # A declared frame lattice's positions are recorded in its own frame on an
    # unsteady row (its fluid plots name that frame); every other in the reference.
    recorded_in = "REFERENCE" if source == "added" or shape.rotor is not None else shape.frame
    geometry = {
        "lattice": lattice.model_dump(mode="json"),
        "axis": axis,
        "origin_m": [float(v) for v in origin],
        "positions_frame": str(recorded_in),
    }
    return FarfieldShape("lattice", source, entry, points, geometry, lattice)


def _placed_alike(wanted: LatticeShape, shape: LatticeShape, entry_frame: str) -> bool:
    """Whether a declared lattice stands where the far field's would: same rotor, or same frame."""
    if wanted.rotor is not None:
        return shape.rotor == wanted.rotor and entry_frame == "REFERENCE"
    frame = str(wanted.frame).strip().upper()
    return (
        shape.rotor is None
        and str(shape.frame).strip().upper() == frame
        and entry_frame == frame
        and shape.tip_radius_m == wanted.tip_radius_m
    )


def _lattice_choice(
    case: SimCase, script: Script, frames: Any, native_per_m: float
) -> FarfieldShape:
    """Choose the survey lattice: a declared one, or the one the plan lays (FR-455 R2).

    A ``[farfield.ledgers]`` that states no lattice key reuses the one declared
    lattice placed on its rotor or frame, when exactly one is and its azimuths
    carry the table's ``m_max``; otherwise a declaration whose laid-out points
    are the far field's own is reused, and none is added.
    """
    spec = _spec(case)
    wanted = spec.ledgers if spec is not None else None
    if wanted is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: Trefftz C on a rotor row reads a station of the survey "
            "lattice; state [farfield.ledgers] with the rotor"
        )
    own = _lattice_shape(case, script, frames, wanted, native_per_m, source="added", entry=None)
    qualifying: list[FarfieldShape] = []
    identical: list[FarfieldShape] = []
    entries = case.pproc.probes if case.pproc is not None else []
    for number, entry in enumerate(entries, start=1):
        if not _emitted(entry):
            continue
        for shape in entry.lattices:
            if not _placed_alike(wanted, shape, entry.frame.strip().upper()):
                continue
            declared = _lattice_shape(
                case, script, frames, shape, native_per_m, source="declared", entry=number
            )
            if _same_points(declared.points_m, own.points_m, native_per_m):
                identical.append(declared)
            if 2 * wanted.m_max < shape.build(1.0).n_psi:
                qualifying.append(declared)
    if not wanted.states_geometry and len(qualifying) == 1:
        return qualifying[0]
    return identical[0] if identical else own


def farfield_shapes(
    case: SimCase, script: Script, frames: Any, native_per_m: float
) -> list[FarfieldShape]:
    """Return the plane and the lattice the row's far field reads, each declared or added.

    The one selection of PFS-2081.56: geometry is resolved once, by frame and
    by the exact laid-out points, and :func:`farfield_probes` lays the added
    ones and records all of them on the script for the run record and post.

    Parameters
    ----------
    case : SimCase
        The row at one point.
    script : Script
        The script being built, whose frame placements place a frame's lattice.
    frames : Any
        The builder's frames by name.
    native_per_m : float
        Simulation length units per metre.

    Returns
    -------
    list of FarfieldShape
        The plane (a wing's Trefftz C) and the lattice (the balances, or a
        rotor's Trefftz C), each where the row needs it.
    """
    shapes: list[FarfieldShape] = []
    if _needs_plane(case):
        shapes.append(_plane_choice(case, native_per_m))
    if _needs_lattice(case):
        shapes.append(_lattice_choice(case, script, frames, native_per_m))
    return shapes


def _command_test(view: Any) -> Callable[[str], bool]:
    def has(command: str) -> bool:
        try:
            view[command]
        except PyflightstreamError:
            return False
        return True

    return has


def _resolve(
    case: SimCase,
    inventory: Sequence[str],
    view: Any,
    shapes: Sequence[Mapping[str, Any]] = (),
) -> FarfieldResolution | None:
    """Resolve the row's inputs; ``shapes`` is the probe selection the script recorded."""
    spec = _spec(case)
    if spec is None:
        return None

    def declares(kind: str) -> bool:
        return any(s.get("kind") == kind and s.get("source") == "declared" for s in shapes)

    return resolve_farfield(
        spec,
        run_type=_run_type(case),
        covered_families=_covered(case, inventory),
        selected_families=_selected(case, spec, inventory),
        exports=dict(case.pproc.exports) if case.pproc is not None else {},
        declares_lattice=declares("lattice"),
        declares_plane=declares("plane"),
        coupled=case.fsi is not None,
        admits_probes=not (case.fsi is not None and _run_type(case) == "steady"),
        has_command=_command_test(view),
        rotor=_rotor(case),
    )


def farfield_resolution(case: SimCase, script: Script) -> FarfieldResolution | None:
    """Resolve the row's far-field inputs against its geometry and build (FR-455)."""
    inventory = _inventory(script) or list(case.inventory or ())
    return _resolve(
        case,
        inventory,
        script.registry.for_version(script.version),
        _recorded_shapes(case, script),
    )


def _recorded_shapes(case: SimCase, script: Script | None) -> list[Mapping[str, Any]]:
    """Return the probe shapes the script recorded for this case's point, or none."""
    if script is None:
        return []
    for laid in reversed(script.farfield_layout):
        if laid.get("point") == dict(case.point):
            return list(laid.get("shapes") or [])
    return []


def plan_record(case: SimCase, version: str, script: Script | None = None) -> dict[str, object]:
    """Return the row's ``farfield`` object of ``plan.json``, empty without one (FR-455 R4).

    With the dry-run ``script`` of the point, the record states the probe
    shapes that script selected (``probes``: kind, declared or added, the
    entry reused and the geometry), so ``plan.json`` serialises the selection
    the run will carry rather than recomputing it (PFS-2081.56).
    """
    if _spec(case) is None:
        return {}
    try:
        view = CommandRegistry.load().for_version(version)
    except PyflightstreamError:
        return {}
    shapes = _recorded_shapes(case, script)
    resolution = _resolve(case, list(case.inventory or ()), view, shapes)
    if resolution is None:
        return {}
    record = resolution.as_record()
    if shapes:
        record["probes"] = [dict(shape) for shape in shapes]
    return record


def _refuse(case: SimCase, resolution: FarfieldResolution) -> None:
    refused = resolution.refused
    if refused:
        lines = "; ".join(f"{item.analysis} {item.input}: {item.reason}" for item in refused)
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the far field of the pproc artifact {case.pproc_id!r} "
            f"cannot be produced on this row: {lines}. Nothing of the plan is written."
        )


def farfield_sections(case: SimCase, script: Script, frames: Any) -> None:
    """Add the section distribution Trefftz A needs over the uncovered families (FR-455 R3)."""
    spec = _spec(case)
    if spec is None or "trefftz:sections" not in _analyses(spec, case):
        return
    resolution = farfield_resolution(case, script)
    if resolution is None:
        return
    _refuse(case, resolution)
    inventory = _inventory(script)
    covered = _covered(case, inventory)
    selected = _selected(case, spec, inventory)
    missing = [name for name in selected if name not in covered]
    stations = spec.trefftz.stations if spec.trefftz is not None else 80
    mirror = str(_variable(case, "SYMMETRY") or "").strip().upper() == "MIRROR"
    _warn_few_stations(case, inventory, [name for name in selected if name in covered], mirror)
    if not missing:
        return
    from ._frames import _pproc_frame

    count = stations if mirror else 2 * stations
    frame = _pproc_frame(case, frames, "MRP", "the far-field section distribution", missing)
    args = {arg.name for arg in script.registry.for_version(script.version)[_SECTION_COMMAND].args}
    sections = spec_sections(case)
    for offset, name in enumerate(missing, start=1):
        index = script.resolve_boundary(name, context="far-field section")
        script.section_blocks.append(
            {
                "distribution": len(sections.distributions) + offset,
                "distribution_families": [name],
                "families": [name],
                "plane": "XZ",
                "frame": "MRP",
                "count": count,
            }
        )
        script.emit(
            _SECTION_COMMAND,
            frame=frame,
            plane="XZ",
            num_sections=count,
            plot_direction=str(sections.plot_direction),
            **({"include_symmetry": "DISABLE"} if "include_symmetry" in args else {}),
            surfaces=1,
            surface_indices=[index],
        )


def spec_sections(case: SimCase) -> Any:
    """Return the row's ``[sections]`` table; a row with ``[farfield]`` has a pproc."""
    if case.pproc is None:
        raise CampaignConfigError(f"case {case.sim_id!r}: the far field needs a pproc artifact")
    return case.pproc.sections


def _free_stream(case: SimCase) -> np.ndarray:
    alpha = math.radians(_angle(case, "alpha"))
    beta = math.radians(_angle(case, "beta"))
    return np.array(
        [math.cos(alpha) * math.cos(beta), -math.cos(alpha) * math.sin(beta), math.sin(alpha)]
    )


def farfield_plane_of(case: SimCase, *, extent_m: float | None) -> FarfieldPlane:
    """Lay the Trefftz C plane of the row's point, in metres (FR-453 R4).

    Normal to the point's free stream, centered on the free-stream line through
    the moment reference point, ``distance_bref BREF`` behind ``extent_m``, the
    most downstream point of the geometry along the free stream (the moment
    reference point itself where the geometry cannot be read).
    """
    spec = _spec(case)
    if spec is None or spec.trefftz is None:
        raise CampaignConfigError(f"case {case.sim_id!r}: the far-field plane needs a trefftz")
    reference = case.reference
    bref = float(getattr(reference, "span_m", None) or 0.0)
    if bref <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the far-field plane is sized in BREF and the reference "
            "states no span"
        )
    direction = _free_stream(case)
    mrp = np.asarray(getattr(reference, "moment_point_m", None) or (0.0, 0.0, 0.0), dtype=float)
    along = float(mrp @ direction)
    reach = along if extent_m is None else extent_m
    half_width, half_height, spacing = spec.trefftz.plane_bref()
    return farfield_plane(
        tuple(mrp + (reach - along) * direction),
        direction=tuple(direction),
        distance=spec.trefftz.distance_bref * bref,
        half_width=half_width * bref,
        half_height=half_height * bref,
        spacing=spacing * bref,
    )


def _rotor_lattice(case: SimCase, shape: LatticeShape) -> np.ndarray:
    lattice, axis, origin = _rotor_placement(case, shape)
    return lattice_points(lattice, axis=axis) + origin


def farfield_lattice(case: SimCase, shape: LatticeShape) -> np.ndarray:
    """Lay a rotor's survey lattice in the reference frame, in metres (FR-459 R2).

    The lattice lies on the rotor's hub along its axis letter, scaled by its
    tip radius.
    """
    if shape.rotor is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the far field lays its lattice on a rotor; a lattice of "
            "a frame is declared in a [[probes]] entry's lattices"
        )
    return _rotor_lattice(case, shape)


def declared_lattice_points(case: SimCase, shape: LatticeShape, frame: str) -> np.ndarray:
    """Lay a ``[[probes]]`` lattice in its entry's frame, in metres (FR-459 R2).

    A lattice naming a rotor lies on the rotor's hub in the reference frame, so
    its entry's frame is ``REFERENCE``; a lattice naming a frame lies along that
    frame's x axis, which is its entry's frame.
    """
    if shape.rotor is not None:
        if frame.strip().upper() != "REFERENCE":
            raise CampaignConfigError(
                f"case {case.sim_id!r}: a lattice on the rotor {shape.rotor!r} is placed in "
                f"the reference frame, and its [[probes]] entry states frame {frame!r}"
            )
        return _rotor_lattice(case, shape)
    if str(shape.frame).strip().upper() != frame.strip().upper():
        raise CampaignConfigError(
            f"case {case.sim_id!r}: a lattice of the frame {shape.frame!r} sits in a [[probes]] "
            f"entry of frame {frame!r}; state it in an entry of its own frame"
        )
    return lattice_points(shape.build(float(shape.tip_radius_m or 0.0)), axis="X")


def declared_lattices(
    case: SimCase, probes: Any, native_per_m: float, *, unsteady: bool
) -> list[list[float]]:
    """Return the native points of a ``[[probes]]`` entry's lattices (FR-459 R2, R5).

    Rounded to five decimals as every drawn probe is; an unsteady entry warns
    the fluid-plot count its lattices cost.
    """
    out: list[list[float]] = []
    for shape in probes.lattices:
        laid = declared_lattice_points(case, shape, probes.frame) * native_per_m
        out += [[round(float(value), 5) for value in point] for point in laid]
        if unsteady:
            warn(
                f"case {case.sim_id!r}: a [[probes]] lattice samples {len(laid)} points at every "
                f"time step, {len(laid) * len(probes.parameters)} fluid plots (FR-459 R5).",
                PyflightstreamWarning,
                stacklevel=3,
            )
    return out


def emit_declared_lattices(case: SimCase, script: Script, probes: Any, native_per_m: float) -> int:
    """Emit a steady reference-frame entry's lattices through the probes home (FR-459 R2).

    Each lattice is placed as :func:`declared_lattice_points` places it (on its
    rotor's hub along the rotor's axis, or along the reference x axis), scaled
    to the simulation's unit and rounded to five decimals, as
    :func:`declared_lattices` records the same points; one ``NEW_PROBE_POINT``
    per point, in the recorded order. Returns the count emitted.
    """
    count = 0
    for shape in probes.lattices:
        if shape.rotor is not None:
            lattice, axis, origin = _rotor_placement(case, shape)
            placed: Any = origin
        else:
            lattice, axis, placed = shape.build(float(shape.tip_radius_m or 0.0)), "X", None
        count += emit_probe_points(
            script, lattice, axis=axis, origin=placed, scale=native_per_m, decimals=5
        )
    return count


def _mesh(case: SimCase) -> str | None:
    geometry = getattr(case, "geometry", None)
    if geometry and Path(str(geometry)).suffix.lower() in _MESH_SUFFIXES:
        return str(geometry)
    if geometry and Path(str(geometry)).suffix.lower() == ".fsm":
        exported = Path(str(geometry)).with_suffix(".surface.stl")
        if exported.is_file():
            return str(exported)
    return None


def _extent_m(case: SimCase, direction: np.ndarray, native_per_m: float) -> float | None:
    mesh = _mesh(case)
    if mesh is None:
        return None
    try:
        from pyflightstream._mesh import read_mesh

        vertices = np.asarray(read_mesh(mesh).vertices, dtype=float) / native_per_m
    except (OSError, ValueError, PyflightstreamError):
        return None
    return float((vertices @ direction).max())


def _inside(case: SimCase, native: np.ndarray) -> tuple[int, str]:
    """Return the count of ``native`` points inside the body and the first ones.

    The count is -1 where the check cannot run, with the reason in place of
    the points.
    """
    mesh = _mesh(case)
    if mesh is None:
        return -1, "the row's geometry is not a mesh file the check reads"
    from pyflightstream.probes.geometry import points_inside

    report = points_inside(native, mesh_path=mesh)
    if not report.checked:
        return -1, str(report.reason)
    first = ", ".join(str(tuple(round(float(v), 5) for v in p)) for p in report.first(native))
    return report.count, first


def warn_declared_inside(case: SimCase, entries: Sequence[tuple[int, str, np.ndarray]]) -> None:
    """Warn per declared ``[[probes]]`` entry with points inside the body (FR-459 R4).

    ``entries`` holds the entry number, its frame and its native points. The
    points are kept. An entry in a frame other than the reference one, or a row
    whose mesh the check cannot read, gets one WARNING saying the points were
    not checked and why; the check never refuses a declared point.
    """
    unchecked: list[str] = []
    for number, frame, native in entries:
        if not len(native):
            continue
        if frame.strip().upper() != "REFERENCE":
            unchecked.append(f"entry {number} lies in the moving frame {frame!r}")
            continue
        count, detail = _inside(case, native)
        if count < 0:
            unchecked.append(detail)
        elif count:
            warn(
                f"case {case.sim_id!r}: {count} point(s) of [[probes]] entry {number} lie "
                f"inside the body, the first at {detail} (native units); they are kept "
                "(FR-459 R4).",
                PyflightstreamWarning,
                stacklevel=3,
            )
    if unchecked:
        warn(
            f"case {case.sim_id!r}: probe points were not checked against the body: "
            f"{'; '.join(dict.fromkeys(unchecked))} (FR-459 R4).",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _check_added(case: SimCase, native: np.ndarray, what: str) -> None:
    """Refuse a package-added point inside the body (FR-455 R7); warn when unchecked."""
    count, detail = _inside(case, native)
    if count < 0:
        warn(
            f"case {case.sim_id!r}: the far-field {what} was not checked against the body: "
            f"{detail} (FR-459 R4).",
            PyflightstreamWarning,
            stacklevel=3,
        )
    elif count:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {count} point(s) of the far-field {what} the plan adds lie "
            f"inside the body, the first at {detail} (native units); state the geometry in "
            "[farfield] (the plane's extent and distance, or the lattice's r_inner and "
            "stations) so it clears the body (FR-455 R7)."
        )


def _frame_origin(
    case: SimCase, script: Script, frames: Any, name: str, native_per_m: float
) -> np.ndarray:
    """Return where a frame's survey lattice starts, in metres, reference frame (FR-454 R1).

    The lattice lies along the frame's x axis from the frame's origin, as the
    script placed the frame; a frame whose axes turn from the reference axes
    is refused by name, because post reads the lattice's velocities on the
    reference axes and could not turn them without the frame's placement.
    """
    from ._frames import _pproc_frame

    index = _pproc_frame(case, frames, name, "the far-field lattice")
    placement = script.frame_placements.get(index) if index != 1 else None
    origin = np.zeros(3)
    if index != 1:
        if placement is None or placement.origin is None or placement.axes is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the far-field lattice lies in the frame {name!r}, and "
                "this script does not follow where that frame stands"
            )
        if not np.allclose(np.asarray(placement.axes, dtype=float), np.eye(3), atol=1e-9):
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the far-field lattice lies in the frame {name!r}, whose "
                "axes turn from the reference axes; state the lattice on a rotor, or in a frame "
                "with the reference axes"
            )
        origin = np.asarray(placement.origin, dtype=float) / native_per_m
    return origin


def _complete_declared_plots(
    case: SimCase,
    script: Script,
    frames: Any,
    shape: FarfieldShape,
    recorded: dict[str, Any],
    native_per_m: float,
) -> None:
    """Add the fluid plots a reused declared set lacks, on its own vertices (PFS-2081.99).

    The far field reads ``VX``, ``VY``, ``VZ`` and ``CP_REF`` at every time
    step; a declared entry states its own ``parameters``, so reusing its points
    reuses its histories and adds only the missing ones, at the same vertices,
    in the frame the entry laid them in (a reused frame keeps the reference
    axes, :func:`_frame_origin`). The added plots are recorded on the shape as
    ``plots_added`` and their count is warned (FR-455 R9).
    """
    entries = case.pproc.probes if case.pproc is not None else []
    entry = entries[int(shape.entry or 0) - 1]
    stated = {str(parameter).strip().upper() for parameter in entry.parameters}
    missing = [name for name in FARFIELD_PLOT_PARAMETERS if name not in stated]
    if not missing:
        return
    label = str(recorded.get("positions_frame", "REFERENCE")).strip().upper()
    expected = shape.points_m
    if label != "REFERENCE":
        expected = expected - np.asarray(recorded["origin_m"], dtype=float)
    laid = [point for point in script.probe_points if str(point[4]).strip().upper() == label]
    native = np.asarray([point[1:4] for point in laid], dtype=float).reshape(-1, 3)
    count = len(expected)
    starts = [
        start
        for start in range(len(laid) - count + 1)
        if _same_points(native[start : start + count] / native_per_m, expected, native_per_m)
    ]
    if len(starts) != 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the far field reuses the {shape.kind} of [[probes]] entry "
            f"{shape.entry}, and its points are laid {len(starts)} times in {label!r}, so the "
            f"histories it lacks ({', '.join(missing)}) cannot be added to them"
        )
    from ._frames import _pproc_frame

    frame = 1 if label == "REFERENCE" else _pproc_frame(case, frames, entry.frame, "the probes")
    vertices = laid[starts[0] : starts[0] + count]
    warn(
        f"case {case.sim_id!r}: the far field reuses the {shape.kind} of [[probes]] entry "
        f"{shape.entry} and adds its missing histories {', '.join(missing)}: "
        f"{count * len(missing)} fluid plots at every time step (FR-455 R9).",
        PyflightstreamWarning,
        stacklevel=3,
    )
    for point in vertices:
        for parameter in missing:
            script.emit(
                "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                frame=frame,
                parameter=parameter,
                name=f"{parameter}{point[0]}",
                vertex=" ".join(str(float(value) / native_per_m) for value in point[1:4]),
            )
    recorded["plots_added"] = missing


def farfield_probes(
    case: SimCase, script: Script, vertex: int, *, unsteady: bool, frames: Any = None
) -> int:
    """Lay the far-field plane and lattice as probe points after the declared ones (FR-455).

    Every shape the far field reads, reused or added, is recorded on the script
    (:attr:`~pyflightstream.script.Script.farfield_layout`, one entry per
    point) for the run record, so post integrates exactly the probes laid here
    (PFS-2081.58); only the added ones are emitted.
    """
    if not needs_fresh_probes(case):
        return vertex
    resolution = farfield_resolution(case, script)
    if resolution is not None:
        _refuse(case, resolution)
    native_per_m = _from_metres(case, script, "far-field probe coordinates")
    shapes = farfield_shapes(case, script, frames, native_per_m)
    records = [shape.record() for shape in shapes]
    script.farfield_layout.append({"point": dict(case.point), "shapes": records})
    imported: list[tuple[float, float, float]] = []
    for shape, recorded in zip(shapes, records, strict=True):
        if shape.source != "added":
            if unsteady:
                _complete_declared_plots(case, script, frames, shape, recorded, native_per_m)
            continue
        what, points = shape.kind, shape.points_m
        native = np.round(points * native_per_m, 5)
        _check_added(case, native, what)
        if unsteady:
            warn(
                f"case {case.sim_id!r}: the far-field {what} samples {len(points)} points at "
                f"every time step, {len(points) * len(FARFIELD_PLOT_PARAMETERS)} fluid plots "
                "(FR-455 R9).",
                PyflightstreamWarning,
                stacklevel=2,
            )
        for x, y, z in native.tolist():
            vertex += 1
            script.probe_points.append((vertex, float(x), float(y), float(z), "REFERENCE"))
            if not unsteady:
                imported.append((x, y, z))
                continue
            for parameter in FARFIELD_PLOT_PARAMETERS:
                script.emit(
                    "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                    frame=_PLOT_FRAME,
                    parameter=parameter,
                    name=f"{parameter}{vertex}",
                    vertex=" ".join(str(value / native_per_m) for value in (x, y, z)),
                )
    if imported:
        _stage_import(script, shapes, imported, native_per_m)
    return vertex


def _stage_import(
    script: Script,
    shapes: Sequence[FarfieldShape],
    imported: Sequence[tuple[float, float, float]],
    native_per_m: float,
) -> None:
    """Park the csv of a steady row's added far-field points and import it (FR-455).

    THE PROBES HOME WRITES THE CSV (PFS-2140.001): the public writer of the
    PROBE_POINTS_IMPORT format is what the plan runs, into the text it parks. A
    lattice added alone is written from the lattice, placed and rounded as
    :func:`farfield_probes` recorded it; a plane, alone or before the lattice,
    from the recorded points.
    """
    staged = io.StringIO()
    added = [shape for shape in shapes if shape.source == "added"]
    if len(added) == 1 and added[0].kind == "lattice":
        write_probe_csv(
            added[0].lattice,
            staged,
            axis=added[0].geometry["axis"],
            origin=added[0].geometry["origin_m"],
            scale=native_per_m,
            decimals=5,
        )
    else:
        write_points_csv(np.asarray(imported, dtype=float), staged)
    payload = staged.getvalue()
    path = f"farfield_probes_{sha256(payload.encode()).hexdigest()}.csv"
    script.park_input_file(path, payload)
    emit_probe_import(script, path, units=script.simulation_length_unit or "METER")
