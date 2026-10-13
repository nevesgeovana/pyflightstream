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

The plane and the lattice are appended after every declared probe, so the
probe export of a point ends with them, the plane first; post finds the
lattice by its positions and the plane as the points before it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
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
)
from pyflightstream.commands import CommandRegistry
from pyflightstream.probes.layouts import (
    FarfieldPlane,
    emit_probe_import,
    farfield_plane,
    lattice_points,
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
    "declared_lattice_points",
    "declared_lattices",
    "farfield_lattice",
    "farfield_outputs",
    "farfield_plane_of",
    "farfield_probes",
    "farfield_resolution",
    "farfield_sections",
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
    """Return the families a declared distribution cuts in XZ of the reference axes."""
    covered: set[str] = set()
    if case.pproc is None:
        return covered
    aliases = _the_names_a_rotor_answers_to(case)
    for entry in case.pproc.sections.distributions:
        if "XZ" not in entry.planes or entry.frame.strip().upper() not in ("MRP", "REFERENCE"):
            continue
        for group in select_families(entry.families, inventory, case.pproc.is_blade, aliases):
            covered.update(group or inventory)
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
            for name in group or inventory:
                per_side[name] = max(per_side.get(name, 0), side)
    for name in reused:
        few = few_stations_warning(name, per_side.get(name, 0), spec.trefftz.stations)
        if few:
            warn(f"case {case.sim_id!r}: {few}.", PyflightstreamWarning, stacklevel=3)


def _lattice_key(shape: LatticeShape) -> dict[str, Any]:
    return {name: getattr(shape, name) for name in LatticeShape.model_fields}


def _declares_lattice(case: SimCase, spec: FarfieldSpec) -> bool:
    """Whether a ``[[probes]]`` entry declares the far field's lattice, by identity (R2).

    A rotor's lattice is declared in an entry of the reference frame and a
    frame's lattice in an entry of its own frame (FR-459 R2), which is where
    :func:`declared_lattice_points` lays it.
    """
    if spec.ledgers is None or case.pproc is None:
        return False
    wanted = _lattice_key(spec.ledgers)
    home = "REFERENCE" if spec.ledgers.rotor is not None else str(spec.ledgers.frame).upper()
    return any(
        _lattice_key(shape) == wanted
        for entry in case.pproc.probes
        if entry.frame.strip().upper() == home
        for shape in entry.lattices
    )


def _command_test(view: Any) -> Callable[[str], bool]:
    def has(command: str) -> bool:
        try:
            view[command]
        except PyflightstreamError:
            return False
        return True

    return has


def _resolve(case: SimCase, inventory: Sequence[str], view: Any) -> FarfieldResolution | None:
    spec = _spec(case)
    if spec is None:
        return None
    return resolve_farfield(
        spec,
        run_type=_run_type(case),
        covered_families=_covered(case, inventory),
        selected_families=_selected(case, spec, inventory),
        exports=dict(case.pproc.exports) if case.pproc is not None else {},
        declares_lattice=_declares_lattice(case, spec),
        declares_plane=False,
        coupled=case.fsi is not None,
        admits_probes=not (case.fsi is not None and _run_type(case) == "steady"),
        has_command=_command_test(view),
        rotor=_rotor(case),
    )


def farfield_resolution(case: SimCase, script: Script) -> FarfieldResolution | None:
    """Resolve the row's far-field inputs against its geometry and build (FR-455)."""
    inventory = _inventory(script) or list(case.inventory or ())
    return _resolve(case, inventory, script.registry.for_version(script.version))


def plan_record(case: SimCase, version: str) -> dict[str, object]:
    """Return the row's ``farfield`` object of ``plan.json``, empty without one (FR-455 R4)."""
    if _spec(case) is None:
        return {}
    try:
        view = CommandRegistry.load().for_version(version)
    except PyflightstreamError:
        return {}
    resolution = _resolve(case, list(case.inventory or ()), view)
    return {} if resolution is None else resolution.as_record()


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
        tuple(direction),
        distance=spec.trefftz.distance_bref * bref,
        half_width=half_width * bref,
        half_height=half_height * bref,
        spacing=spacing * bref,
    )


def _rotor_lattice(case: SimCase, shape: LatticeShape) -> np.ndarray:
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
    points = lattice_points(shape.build(rotor.diameter_m / 2.0), axis=axis)
    return points + np.array([rotor.x_m, rotor.y_m, rotor.z_m])


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


def _mesh(case: SimCase) -> str | None:
    geometry = getattr(case, "geometry", None)
    if geometry and Path(str(geometry)).suffix.lower() in _MESH_SUFFIXES:
        return str(geometry)
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


def _frame_lattice(
    case: SimCase, script: Script, frames: Any, shape: LatticeShape, native_per_m: float
) -> np.ndarray:
    """Lay a frame's survey lattice in the reference frame, in metres (FR-454 R1).

    The lattice lies along the frame's x axis from the frame's origin, as the
    script placed the frame; a frame whose axes turn from the reference axes
    is refused by name, because post reads the lattice's velocities on the
    reference axes and could not turn them without the frame's placement.
    """
    from ._frames import _pproc_frame

    name = str(shape.frame)
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
    lattice = shape.build(float(shape.tip_radius_m or 0.0))
    return lattice_points(lattice, axis="X") + origin


def _added_shapes(
    case: SimCase, native_per_m: float, script: Script, frames: Any
) -> list[tuple[str, np.ndarray]]:
    spec = _spec(case)
    shapes: list[tuple[str, np.ndarray]] = []
    if spec is None:
        return shapes
    if _needs_plane(case):
        direction = _free_stream(case)
        laid = farfield_plane_of(case, extent_m=_extent_m(case, direction, native_per_m))
        shapes.append(("plane", laid.points))
    if _needs_lattice(case) and not _declares_lattice(case, spec):
        if spec.ledgers is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: Trefftz C on a rotor row reads a station of the survey "
                "lattice; state [farfield.ledgers] with the rotor"
            )
        if spec.ledgers.frame is not None:
            points = _frame_lattice(case, script, frames, spec.ledgers, native_per_m)
        else:
            points = farfield_lattice(case, spec.ledgers)
        shapes.append(("lattice", points))
    return shapes


def farfield_probes(
    case: SimCase, script: Script, vertex: int, *, unsteady: bool, frames: Any = None
) -> int:
    """Lay the far-field plane and lattice as probe points after the declared ones (FR-455)."""
    if not needs_fresh_probes(case):
        return vertex
    resolution = farfield_resolution(case, script)
    if resolution is not None:
        _refuse(case, resolution)
    native_per_m = _from_metres(case, script, "far-field probe coordinates")
    imported: list[tuple[float, float, float]] = []
    for what, points in _added_shapes(case, native_per_m, script, frames):
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
        payload = str(len(imported)) + "\n"
        payload += "".join(f"{x},{y},{z},1\n" for x, y, z in imported)
        path = f"farfield_probes_{sha256(payload.encode()).hexdigest()}.csv"
        script.park_input_file(path, payload)
        emit_probe_import(script, path, units=script.simulation_length_unit or "METER")
    return vertex
