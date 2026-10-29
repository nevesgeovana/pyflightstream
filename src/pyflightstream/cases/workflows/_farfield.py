"""What the plan adds to a row's script for the far field (FR-455, FR-1074).

The emission half of the far-field family: where a row's pproc artifact carries
``[[farfields]]``, the builders call these functions to resolve what the far
field reads, to switch the wake on in the VTK export, and to lay the far-field
plane or survey lattice as probe points; the outputs it declares and the
section distributions it adds are emitted beside the other post-processing
sections (:mod:`._pproc`), and the body the points must clear is read by
:mod:`._geometry`. What is reused, added, not applicable
or refused is the resolver's (:mod:`pyflightstream.cases.farfield_inputs`);
the geometry is laid out by :mod:`pyflightstream.probes.layouts`. A row whose
artifact has no ``[[farfields]]`` reaches none of this, so its script keeps its
bytes.

The plane and the lattice are chosen once (:func:`farfield_shapes`): a
declared ``[[probes]]`` shape is reused when it is the far field's geometry
after layout, or, where ``[[farfields]]`` states no geometry, when it is the one
declaration that qualifies; what is not declared is appended after every
declared probe. Every chosen shape is recorded on the script for the run
record, and post matches the exported positions to it (PFS-2081.56, .58).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
    select_families,
)
from pyflightstream.cases._farfield_spec import FarfieldSpec, LatticeShape
from pyflightstream.cases.farfield_inputs import (
    ROTOR_RUN_TYPES,
    FarfieldInput,
    FarfieldResolution,
    applies,
    resolve_farfield,
    traced_family,
)
from pyflightstream.cases.windows import averaging_steps
from pyflightstream.commands import CommandRegistry
from pyflightstream.probes.layouts import (
    FarfieldPlane,
    emit_probe_points,
    farfield_plane,
    lattice_points,
    rectangle_points,
)
from pyflightstream.script import Script

from ._conventions import declared_run_type
from ._freestream import rotor_row_stepping
from ._geometry import _extent_m, _inside
from ._motion import _origin
from ._names import _inventory
from ._probe_imports import _phased_farfield, _shape_key, _stage_import
from ._rows import (
    _angle,
    _from_metres,
    _states_a_rotor_speed,
    _the_names_a_rotor_answers_to,
    _the_rotor_a_flat_row_turns,
    _variable,
    continuation_of,
)
from ._timing import unsteady_time_stepping
from ._vocabulary import ROTOR_ORIGIN_VARIABLE

__all__ = [
    "FARFIELD_PLOT_PARAMETERS",
    "FarfieldShape",
    "declared_lattice_points",
    "declared_lattices",
    "farfield_lattice",
    "farfield_plane_of",
    "farfield_probes",
    "farfield_resolution",
    "farfield_shapes",
    "needs_fresh_probes",
    "plan_record",
    "wants_wake",
]

#: The fluid-plot parameters an unsteady row samples at every far-field point:
#: the velocity components and ``CP_REF``, a parameter the command database lists
#: for ``UNSTEADY_SOLVER_NEW_FLUID_PLOT``; its normalization is not recorded there
#: and none is claimed here (FR-1052 names the plots).
FARFIELD_PLOT_PARAMETERS: tuple[str, ...] = ("VX", "VY", "VZ", "CP_REF")
#: The reference frame of the far-field fluid plots (frame 1, the global frame).
_PLOT_FRAME = 1
#: The stations of the blade distribution the far field adds for a rotor's disk
#: loading (P0470-FFR option 1a), as the rotor pproc of the PFS-2165 study cut them.
_BLADE_STATIONS = 50
#: Two laid-out probe sets are one declaration when every coordinate agrees at
#: the fifth decimal of the simulation's unit, the precision the script writes
#: a probe position in (FR-1045, PFS-2081.56): after rounding to five decimals
#: the values are equal, so the tolerance is float noise and never one step of
#: 1e-5 (F-064).
_SAME_POSITION = 1e-9


def _spec(case: SimCase) -> FarfieldSpec | None:
    return getattr(case.pproc, "farfield", None) if case.pproc is not None else None


def _entry_cases(case: SimCase) -> list[SimCase]:
    if case.pproc is None or len(case.pproc.farfields) < 2:
        return []
    return [
        case.model_copy(update={"pproc": case.pproc.model_copy(update={"farfields": [entry]})})
        for entry in case.pproc.farfields
    ]


def _run_type(case: SimCase) -> str:
    return str(declared_run_type(case) or "steady")


def _rotor(case: SimCase) -> bool:
    return _run_type(case) in ROTOR_RUN_TYPES or (
        _run_type(case) == "steady" and _states_a_rotor_speed(case)
    )


def _declared_analyses(spec: FarfieldSpec) -> list[str]:
    """Return the analyses an entry declares, before the row decides which apply."""
    selected = []
    if spec.trefftz is not None:
        selected += [f"trefftz:{variant}" for variant in spec.trefftz.variant]
    if spec.balances:
        selected.append("ledgers")
    return selected


def _analyses(spec: FarfieldSpec, case: SimCase) -> list[str]:
    if _entry_window(spec, case):
        return []
    run_type, rotor = _run_type(case), _rotor(case)
    # An analysis that does not apply to the row is skipped here and stated
    # `not_applicable` by the plan, never refused.
    return [
        analysis
        for analysis in _declared_analyses(spec)
        if not applies(analysis, run_type, rotor=rotor)
    ]


def _entry_window(spec: FarfieldSpec, case: SimCase) -> str:
    """Return why this row cannot take the entry's averaging window, or ``""``.

    A WINDOW THE ROW CANNOT SAMPLE OR CLOCK SKIPS THE ENTRY ON THAT ROW (P0471):
    a steady row has no march to average, and a row
    with no rotor clock counts no revolutions; the unsteady (rotor) rows of the
    same pproc take the entry. A window stated without ``export_type =
    "avg_window"`` is a writing error no row can take, and is refused.
    """
    key = "last_revs" if spec.last_revs is not None else "last_steps"
    value = getattr(spec, key)
    if value is None:
        return ""
    per_revolution = None
    if _run_type(case) not in ("unsteady", "unsteady_rotor"):
        return f"its {key} window needs an unsteady row, and this row is {_run_type(case)}"
    if spec.export_type != "avg_window":
        raise CampaignConfigError(
            f'case {case.sim_id!r}: {key} requires export_type = "avg_window"'
        )
    if key == "last_revs":
        if _rotor(case):
            per_revolution = rotor_row_stepping(case).steps_per_revolution
        if per_revolution is None:
            return (
                "its last_revs window counts rotor revolutions and this row has no rotor "
                "clock; the rotor rows take it, and last_steps serves every unsteady row"
            )
    averaging_steps(
        {"LAST_REVS_AVG" if key == "last_revs" else "LAST_ITERS_AVG": value},
        per_revolution=per_revolution,
    )
    return ""


def wants_wake(case: SimCase) -> bool:
    """Whether the row's far field reads the wake export (Trefftz B applies)."""
    entries = _entry_cases(case)
    if entries:
        return any(wants_wake(entry) for entry in entries)
    spec = _spec(case)
    return spec is not None and "trefftz:wake" in _analyses(spec, case)


def _needs_plane(case: SimCase) -> bool:
    spec = _spec(case)
    return spec is not None and "trefftz:plane" in _analyses(spec, case)


def _needs_lattice(case: SimCase) -> bool:
    spec = _spec(case)
    if spec is None:
        return False
    analyses = _analyses(spec, case)
    return "ledgers" in analyses or "trefftz:power" in analyses


def needs_fresh_probes(case: SimCase) -> bool:
    """Whether the row's far field lays probes, so a steady point starts from none."""
    entries = _entry_cases(case)
    return (
        any(needs_fresh_probes(entry) for entry in entries)
        if entries
        else (_needs_plane(case) or _needs_lattice(case))
    )


def _normal(case: SimCase) -> bool:
    """Whether any declared entry needs the final probe-points export."""
    if case.pproc is None:
        return False
    try:
        return bool(case.pproc.samples_normal_probes())
    except CampaignConfigError:
        return False


def _selected(case: SimCase, spec: FarfieldSpec, inventory: Sequence[str]) -> list[str]:
    is_blade = case.pproc.is_blade if case.pproc is not None else (lambda name: False)
    groups = select_families(
        spec.families or "all", inventory, is_blade, aliases=_the_names_a_rotor_answers_to(case)
    )
    chosen: list[str] = []
    for group in groups:
        for name in group or list(inventory):
            if name not in chosen:
                chosen.append(name)
    if spec.variant == "sections":
        for alias, rotor in case.rotors.items():
            overlap = set(chosen).intersection(rotor.families_blades + rotor.families_general)
            if overlap:
                raise CampaignConfigError(
                    f"case {case.sim_id!r}: Trefftz A selects rotor {alias} families "
                    f"{', '.join(sorted(overlap))}; select the reference's lifting-surface aliases"
                )
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


@dataclass(frozen=True)
class FarfieldShape:
    """One far-field probe set as the plan chose it: the plane or the lattice (FR-1045).

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
    component: tuple[str, int] | None = None

    def record(self) -> dict[str, Any]:
        """Return the shape as the run record and ``plan.json`` carry it (FR-1047)."""
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
    are the same probes (FR-1045: same frame, same points after layout).
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
    """Return a declared rectangle as a far-field plane (center, grid), or None (FR-1045).

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


def _plane_choice(
    case: SimCase, native_per_m: float, script: Script | None = None
) -> FarfieldShape:
    """Choose the wing's Trefftz C plane: a declared one, or the one the plan lays (FR-1045)."""
    spec = _spec(case)
    trefftz = spec.trefftz if spec is not None else None
    if trefftz is None:
        raise CampaignConfigError(f"case {case.sim_id!r}: the far-field plane needs a trefftz")
    direction = _free_stream(case)
    extent = _extent_m(case, direction, native_per_m, script)
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
        for index, rectangle in enumerate(entry.rectangles):
            # Laid as `[[probes]]` lays it, in the simulation's unit, then in metres.
            native = rectangle_points(rectangle, scale=native_per_m)
            points = np.array(native, dtype=float) / native_per_m
            if _same_points(points, own.points_m, native_per_m):
                identical.append(
                    replace(own, source="declared", entry=number, component=("rectangle", index))
                )
            chosen = _qualifying_plane(rectangle, laid.axes, reach)
            if chosen is not None:
                qualifying.append(
                    replace(
                        _plane_shape("declared", number, chosen[0], direction, chosen[1]),
                        component=("rectangle", index),
                    )
                )
    if not trefftz.states_plane and len(qualifying) == 1:
        return qualifying[0]
    return identical[0] if identical else own


def _lattice_placement(
    case: SimCase, script: Script, frames: Any, shape: LatticeShape, native_per_m: float
) -> tuple[Any, str | tuple[float, float, float], np.ndarray]:
    """Return a lattice, its shaft axis letter and its origin in metres (reference frame)."""
    if shape.rotor is not None:
        return _rotor_placement(case, shape, native_per_m)
    origin = _frame_origin(case, script, frames, str(shape.frame), native_per_m)
    return shape.build(float(shape.tip_radius_m or 0.0)), "X", origin


def _rotor_placement(
    case: SimCase, shape: LatticeShape, native_per_m: float = 1.0
) -> tuple[Any, str | tuple[float, float, float], np.ndarray]:
    """Return a rotor's lattice, its shaft axis letter and its hub in metres (FR-1072).

    The hub is the one the run places: a row stating ROTOR_ORIGIN moves the hub of
    the rotor it turns, in the simulation's unit (``native_per_m`` of them to the
    metre; a caller with no script states the metre).
    """
    rotor = case.rotors.get(str(shape.rotor))
    if rotor is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: a lattice names the rotor {shape.rotor!r}, which the "
            f"reference does not declare ({', '.join(sorted(case.rotors)) or 'none'})"
        )
    axis = rotor.axis if isinstance(rotor.axis, str) else rotor.axis_vector
    origin = np.array([rotor.x_m, rotor.y_m, rotor.z_m])
    if _variable(case, ROTOR_ORIGIN_VARIABLE) is not None and (
        _the_rotor_a_flat_row_turns(case) is rotor
    ):
        origin = np.asarray(_origin(case), dtype=float) / native_per_m
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


def _unplaced_frame_of(case: SimCase, frames: Any, frame: object) -> bool:
    """Whether ``frame`` is a declared rotor's frame this row does not place (P0471)."""
    from ._frames import _an_unplaced_rotor_frame

    name = str(frame or "").strip()
    return frames is not None and bool(name) and _an_unplaced_rotor_frame(case, frames, name)


def _the_lattice_this_row_leaves_out(case: SimCase, frames: Any) -> dict[str, Any] | None:
    """Return the skip record of an entry whose survey lattice lies in an unplaced rotor frame.

    WARNED AND SKIPPED, NEVER REFUSED (P0471). A lattice laid
    in a declared rotor's frame that this row does not place (``PUSHER_RMRP`` on
    a steady row) cannot be laid here, and can on the row that turns the rotor,
    so the entry's lattice analyses are left out of this row: nothing is laid,
    the record carries this skip for the plan and post, and the plan says it once.
    """
    spec = _spec(case)
    if spec is None:
        return None
    wanted = spec.ledgers
    record = {
        "kind": "skipped",
        "source": "skipped",
        "entry": None,
        "count": 0,
        "farfield_entry": spec.name or "",
        "frame": "",
    }
    if wanted is None:
        # A WING ENTRY ON A ROTOR ROW: Trefftz C there reads a lattice station, which
        # only a power entry with the rotor states; the wing rows read its plane.
        return dict(
            record,
            reason=(
                "Trefftz C on a rotor row reads a station of the survey lattice, which only "
                "a [[farfields]] power entry with the rotor states; the wing rows read this "
                "entry's plane"
            ),
        )
    if wanted.rotor is not None or not _unplaced_frame_of(case, frames, wanted.frame):
        return None
    return dict(
        record,
        frame=str(wanted.frame),
        reason=(
            f"the survey lattice lies in {wanted.frame!r}, a rotor frame this row does not "
            "place; the entry is ignored on this row"
        ),
    )


def _say_the_lattice_left_out(case: SimCase, frames: Any, left_out: dict[str, Any] | None) -> None:
    """Note, once per campaign, an entry whose lattice this row leaves out (P0471)."""
    from pyflightstream.cases._skipped_families import leave_out_what_the_row_cannot_take

    from ._frames import _a_rotor_frame_the_row_leaves_out
    from ._names import _artifact_of

    if left_out is None:
        return
    entry = f"[[farfields]] entry {left_out['farfield_entry']!r}"
    if left_out["frame"]:
        _a_rotor_frame_the_row_leaves_out(case, frames, left_out["frame"], entry)
    else:
        leave_out_what_the_row_cannot_take(
            case.sim_id, _artifact_of(case), entry, f"is skipped on this row: {left_out['reason']}"
        )


def _lattice_choice(
    case: SimCase, script: Script, frames: Any, native_per_m: float
) -> FarfieldShape | None:
    """Choose the survey lattice: a declared one, or the one the plan lays (FR-1045).

    A ``[[farfields]]`` power entry that states no lattice key reuses the one declared
    lattice placed on its rotor or frame, when exactly one is and its azimuths
    carry the table's ``m_max``; otherwise a declaration whose laid-out points
    are the far field's own is reused, and none is added. None when the lattice
    lies in a rotor frame this row does not place (it is left out, said once);
    a declared ``[[probes]]`` entry laid in such a frame is not reused.
    """
    spec = _spec(case)
    left_out = _the_lattice_this_row_leaves_out(case, frames)
    if spec is None or spec.ledgers is None or left_out is not None:
        _say_the_lattice_left_out(case, frames, left_out)
        return None
    wanted = spec.ledgers
    own = _lattice_shape(case, script, frames, wanted, native_per_m, source="added", entry=None)
    qualifying: list[FarfieldShape] = []
    identical: list[FarfieldShape] = []
    entries = case.pproc.probes if case.pproc is not None else []
    for number, entry in enumerate(entries, start=1):
        # A [[probes]] entry the row leaves out laid nothing, so nothing of it is reused.
        if not _emitted(entry) or _unplaced_frame_of(case, frames, entry.frame):
            continue
        for index, shape in enumerate(entry.lattices):
            if not _placed_alike(wanted, shape, entry.frame.strip().upper()):
                continue
            declared = _lattice_shape(
                case, script, frames, shape, native_per_m, source="declared", entry=number
            )
            declared = replace(declared, component=("lattice", index))
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
    entries = _entry_cases(case)
    if entries:
        return [
            shape
            for entry in entries
            for shape in farfield_shapes(entry, script, frames, native_per_m)
        ]
    shapes: list[FarfieldShape] = []
    if _needs_plane(case):
        shapes.append(_plane_choice(case, native_per_m, script))
    if _needs_lattice(case):
        lattice = _lattice_choice(case, script, frames, native_per_m)
        if lattice is not None:
            shapes.append(lattice)
    spec = _spec(case)
    for shape in shapes:
        shape.geometry["farfield_entry"] = spec.name if spec is not None else ""
        shape.geometry["export_type"] = spec.export_type if spec is not None else "default"
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
    entries = _entry_cases(case)
    if entries:
        resolved = [_resolve(entry, inventory, view, shapes) for entry in entries]
        return FarfieldResolution(
            tuple(item for result in resolved if result for item in result.inputs)
        )
    spec = _spec(case)
    if spec is None:
        return None
    window = _entry_window(spec, case)
    if window:
        # P0471: an entry whose window this row cannot take is not applicable here.
        return FarfieldResolution(
            tuple(
                FarfieldInput(
                    analysis,
                    "window",
                    "not_applicable",
                    reason=window,
                    entry=spec.name,
                    variant=spec.variant,
                )
                for analysis in _declared_analyses(spec)
            )
        )

    def declares(kind: str) -> bool:
        return any(
            s.get("kind") == kind
            and s.get("source") == "declared"
            and s.get("farfield_entry", spec.name) == spec.name
            for s in shapes
        )

    resolution = resolve_farfield(
        spec,
        run_type=_run_type(case),
        covered_families=_covered(case, inventory),
        # An entry the row does not apply to selects nothing: its families may be
        # absent from this row's geometry (a wing on a quasi-steady rotor's pproc).
        selected_families=_selected(case, spec, inventory) if _analyses(spec, case) else [],
        exports=dict(case.pproc.exports) if case.pproc is not None else {},
        declares_lattice=declares("lattice"),
        declares_plane=declares("plane"),
        coupled=case.fsi is not None,
        admits_probes=not (case.fsi is not None and _run_type(case) == "steady"),
        has_command=_command_test(view),
        rotor=_rotor(case),
        blade_loads=blade_loads_state(case, spec),
    )
    # A LATTICE THE SCRIPT LEFT OUT (an unplaced rotor frame) is not applicable on
    # this row, with the recorded reason: never refused, never claimed as added.
    left_out = next(
        (
            s.get("reason")
            for s in shapes
            if s.get("kind") == "skipped" and s.get("farfield_entry", "") == (spec.name or "")
        ),
        None,
    )
    return FarfieldResolution(
        tuple(
            replace(
                item,
                entry=spec.name,
                variant=spec.variant,
                **(
                    {"state": "not_applicable", "reason": str(left_out)}
                    if left_out and item.analysis in ("ledgers", "trefftz:power")
                    else {}
                ),
            )
            for item in resolution.inputs
        )
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
    """Return the row's ``farfield`` object of ``plan.json``, empty without one (FR-1047).

    With the dry-run ``script`` of the point, the record states the probe
    shapes that script selected (``probes``: kind, declared or added, the
    entry reused and the geometry), so ``plan.json`` serialises the selection
    the run will carry rather than recomputing it (PFS-2081.56).
    """
    if _spec(case) is None:
        return {}
    try:
        view = CommandRegistry.load().for_version(version)
    except PyflightstreamError as error:
        # F-1317: not an empty record, which reads as "no far field".
        return {"unresolved": f"the command database for {version} could not be read: {error}"}
    shapes = _recorded_shapes(case, script)
    # THE INVENTORY THE SCRIPT EMITS FROM, as `farfield_resolution` reads it (F-765).
    inventory = (_inventory(script) if script is not None else None) or list(case.inventory or ())
    resolution = _resolve(case, inventory, view, shapes)
    if resolution is None:
        return {}
    if script is not None and _run_type(case) == "qsteady_rotor":
        _warn_not_applicable(case, resolution)
    elif script is not None:
        # An entry whose lattice the build left out was said there, with its frame.
        said = {s.get("farfield_entry") for s in shapes if s.get("kind") == "skipped"}
        _say_what_the_row_skips(case, resolution, said)
    record = resolution.as_record()
    if shapes:
        record["probes"] = [dict(shape) for shape in shapes]
    return record


def _say_what_the_row_skips(case: SimCase, resolution: FarfieldResolution, said: set[Any]) -> None:
    """Say once per campaign each far-field analysis this row skips (P0471).

    An entry a row cannot take (a steady
    coupled row reads no probes, a coupled row's one distribution does not
    cover the entry, a window or a lattice the row cannot have) is skipped
    and never refused. The plan notes the row; one warning names the rows.
    A blade-loads input stated not applicable is an optional input, not a skip.
    """
    from pyflightstream.cases._skipped_families import leave_out_what_the_row_cannot_take

    from ._names import _artifact_of

    # ONE NOTE PER ENTRY AND REASON, naming every analysis it skips.
    skipped: dict[tuple[str, str], list[str]] = {}
    for item in resolution.inputs:
        if (
            item.state == "not_applicable"
            and item.input != "blade_sectional_loads"
            and item.entry not in said
        ):
            analyses = skipped.setdefault((item.entry, item.reason), [])
            if item.analysis not in analyses:
                analyses.append(item.analysis)
    for (entry, reason), analyses in skipped.items():
        leave_out_what_the_row_cannot_take(
            case.sim_id,
            _artifact_of(case),
            f"[[farfields]] entry {entry!r} ({', '.join(analyses)})",
            f"is not applicable on this row ({reason})",
        )


def _warn_not_applicable(case: SimCase, resolution: FarfieldResolution) -> None:
    """Warn of each entry a quasi-steady row skips.

    A quasi-steady row holds an isolated rotor, so A and B have no family to
    trace on it; the entries are skipped and the plan stays ready, so the same
    pproc serves the unsteady row that carries the lifting surfaces.
    """
    for item in resolution.inputs:
        if item.analysis == "trefftz:wake" and item.state in ("added", "reused"):
            warn(
                f"case {case.sim_id!r}: [[farfields]] entry {item.entry!r}: "
                "Trefftz B on qsteady_rotor has no wake of a lifting surface outside the "
                "rotor: B is traced on a steady row that carries the lifting surfaces. "
                "B is skipped; the rotor wake loads W are written.",
                PyflightstreamWarning,
                stacklevel=3,
            )
        if item.state == "not_applicable":
            warn(
                f"case {case.sim_id!r}: [[farfields]] entry {item.entry!r} is not applicable "
                f"on this row and is skipped: {item.reason}",
                PyflightstreamWarning,
                stacklevel=3,
            )


def _refuse(case: SimCase, resolution: FarfieldResolution) -> None:
    refused = resolution.refused
    if refused:
        lines = "; ".join(f"{item.analysis} {item.input}: {item.reason}" for item in refused)
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the far field of the pproc artifact {case.pproc_id!r} "
            f"cannot be produced on this row: {lines}. Nothing of the plan is written."
        )


def _blade_rotor(case: SimCase, spec: FarfieldSpec) -> tuple[str, Any] | None:
    """Return the alias and block of the rotor a power entry's disk loading reads, or None."""
    if spec.ledgers is None or not _rotor(case):
        return None
    alias = spec.ledgers.rotor
    rotors = dict(case.rotors)
    if alias is None:
        if len(rotors) != 1:
            return None
        alias = next(iter(rotors))
    block = rotors.get(alias)
    return None if block is None else (str(alias), block)


def _declares_blade_loads(case: SimCase) -> bool:
    """Whether a declared distribution cuts the blades in a blade or rotor frame."""
    if case.pproc is None:
        return False
    for entry in case.pproc.sections.distributions:
        frame = entry.frame.strip().upper()
        if frame in ("LOCAL_AXIS", "RMRP", "BLADE_AXIS") or frame.rsplit("_", 1)[-1].startswith(
            "RMRP"
        ):
            return True
    return False


def blade_loads_state(case: SimCase, spec: FarfieldSpec) -> tuple[str, str]:
    """Return how a rotor row gets the blade loads its disk correction reads (P0470-FFR).

    ``("", "")`` for an entry that reads no rotor lattice; else the state
    (``reused``, ``added`` or ``not_applicable``) and its source or reason.
    """
    found = _blade_rotor(case, spec)
    if found is None:
        return "", ""
    alias, block = found
    if _declares_blade_loads(case):
        return "reused", "[sections] distributions in the blade frames"
    if _run_type(case) == "unsteady_rotor" and block.families_blades:
        return (
            "added",
            f"a distribution over each blade of {alias} in its own frame, "
            f"{_BLADE_STATIONS} stations",
        )
    return (
        "not_applicable",
        f"a {_run_type(case)} row places no blade frames unless a distribution is declared; "
        f'declare a [[sections.distributions]] entry with frame = "LOCAL_AXIS" over the '
        f"blades, or G4 of the rotor stays NA (WARNING)",
    )


def _free_stream(case: SimCase) -> np.ndarray:
    alpha = math.radians(_angle(case, "alpha"))
    beta = math.radians(_angle(case, "beta"))
    return np.array(
        [math.cos(alpha) * math.cos(beta), -math.cos(alpha) * math.sin(beta), math.sin(alpha)]
    )


def farfield_plane_of(case: SimCase, *, extent_m: float | None) -> FarfieldPlane:
    """Lay the Trefftz C plane of the row's point, in metres (FR-1033).

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
    """Lay a rotor's survey lattice in the reference frame, in metres (FR-1072).

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
    """Lay a ``[[probes]]`` lattice in its entry's frame, in metres (FR-1072).

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
    """Return the native points of a ``[[probes]]`` entry's lattices (FR-1072, FR-1075).

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
                f"time step, {len(laid) * len(probes.parameters)} fluid plots (FR-1075).",
                PyflightstreamWarning,
                stacklevel=3,
            )
    return out


def emit_declared_lattices(case: SimCase, script: Script, probes: Any, native_per_m: float) -> int:
    """Emit a steady reference-frame entry's lattices through the probes home (FR-1072).

    Each lattice is placed as :func:`declared_lattice_points` places it (on its
    rotor's hub along the rotor's axis, or along the reference x axis), scaled
    to the simulation's unit and rounded to five decimals, as
    :func:`declared_lattices` records the same points; one ``NEW_PROBE_POINT``
    per point, in the recorded order. Returns the count emitted.
    """
    count = 0
    for shape in probes.lattices:
        if shape.rotor is not None:
            lattice, axis, origin = _rotor_placement(case, shape, native_per_m)
            placed: Any = origin
        else:
            lattice, axis, placed = shape.build(float(shape.tip_radius_m or 0.0)), "X", None
        count += emit_probe_points(
            script, lattice, axis=axis, origin=placed, scale=native_per_m, decimals=5
        )
    return count


def _check_added(case: SimCase, native: np.ndarray, what: str) -> None:
    """Refuse a package-added point inside the body (FR-1050); warn when unchecked."""
    count, detail = _inside(case, native)
    if count < 0:
        warn(
            f"case {case.sim_id!r}: the far-field {what} was not checked against the body: "
            f"{detail} (FR-1074).",
            PyflightstreamWarning,
            stacklevel=3,
        )
    elif count:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {count} point(s) of the far-field {what} the plan adds lie "
            f"inside the body, the first at {detail} (native units); state the geometry in "
            "the [[farfields]] entry (the plane's extent and distance, or the lattice's "
            "r_inner and stations) so it clears the body (FR-1050)."
        )


def _frame_origin(
    case: SimCase, script: Script, frames: Any, name: str, native_per_m: float
) -> np.ndarray:
    """Return where a frame's survey lattice starts, in metres, reference frame (FR-1039).

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
    ``plots_added`` and their count is warned (FR-1052).
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
        f"{count * len(missing)} fluid plots at every time step (FR-1052).",
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
    case: SimCase,
    script: Script,
    vertex: int,
    *,
    unsteady: bool,
    frames: Any = None,
    analysis_points: list | None = None,
    declared_spans: dict[int, tuple[int, dict[tuple[str, int], int]]] | None = None,
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
    for shape in shapes:
        if shape.source == "added":
            _check_added(case, np.round(shape.points_m * native_per_m, 5), shape.kind)
    if _run_type(case) in ("unsteady", "unsteady_rotor"):
        laid = _phased_farfield(
            case,
            script,
            shapes,
            records=records,
            vertex=vertex,
            native_per_m=native_per_m,
            analysis_points=analysis_points,
            windows=farfield_export_windows(case),
        )
        records.extend(_lattices_left_out(case, frames))
        return laid
    script.farfield_layout.append({"point": dict(case.point), "shapes": records})
    imported: list[tuple[float, float, float]] = []
    placements: dict[tuple, dict[str, Any]] = {}
    for shape, recorded in _unique_shapes(shapes, records):
        points = shape.points_m
        native = np.round(points * native_per_m, 5)
        placements[_shape_key(shape)] = _steady_probe_span(
            shape, declared_spans, len(imported), vertex, len(placements)
        )
        if shape.source != "added":
            continue
        recorded["positions_frame"] = "REFERENCE"
        for x, y, z in native.tolist():
            vertex += 1
            script.probe_points.append((vertex, float(x), float(y), float(z), "REFERENCE"))
            imported.append((x, y, z))
    _record_shape_spans(shapes, records, placements)
    records.extend(_lattices_left_out(case, frames))
    if imported:
        _stage_import(script, shapes, imported, native_per_m)
    return vertex


def _lattices_left_out(case: SimCase, frames: Any) -> list[dict[str, Any]]:
    """Return the skip records of every entry whose lattice this row leaves out (P0471)."""
    cases = _entry_cases(case) or [case]
    found = (
        _the_lattice_this_row_leaves_out(entry, frames) if _needs_lattice(entry) else None
        for entry in cases
    )
    return [record for record in found if record is not None]


def _record_shape_spans(shapes, records, placements):
    """Give each reader of a shared shape the span assigned to its one import."""
    for shape, recorded in zip(shapes, records, strict=True):
        recorded.update(placements.get(_shape_key(shape), {}))


def _steady_probe_span(shape, declared_spans, offset, vertex, number):
    """Record a steady shape at the declared or appended position already known."""
    if shape.source == "added":
        return dict(
            id=f"farfield:{shape.kind}:{number}",
            offset=offset,
            final_offset=vertex,
            import_phase="after-march",
            exports=["final"],
        )
    if declared_spans is None or shape.entry not in declared_spans:
        return {}
    first, parts = declared_spans[shape.entry]
    return dict(
        id=f"probes[{shape.entry}]",
        offset=first,
        final_offset=first,
        sample_offset=parts.get(shape.component, 0),
        import_phase="after-march",
        exports=["final"],
    )


def _unique_shapes(shapes: Sequence[FarfieldShape], records: list[dict[str, Any]]):
    """Emit identical sample positions once while retaining each entry's layout record."""
    seen = set()
    for shape, recorded in zip(shapes, records, strict=True):
        key = _shape_key(shape)
        if key not in seen:
            seen.add(key)
            yield shape, recorded


def farfield_export_windows(case: SimCase) -> tuple[tuple[int, int, str], ...]:
    """Resolve independent far-field export windows on the row's solver clock."""
    from pyflightstream.cases.windows import averaging_span

    if case.pproc is None or _run_type(case) not in ("unsteady", "unsteady_rotor"):
        return ()
    entries = [entry for entry in case.pproc.farfields if entry.export_type == "avg_window"]
    if not entries:
        return ()
    clock = (
        rotor_row_stepping(case)
        if _run_type(case) == "unsteady_rotor"
        else unsteady_time_stepping(case)
    )
    resumed = continuation_of(case)
    # The action counter restarts at one; prior snapshots remain on the global
    # solver clock. Export the intersection with this continued march only.
    last_step = resumed[1] if resumed is not None else clock.time_iterations
    windows: dict[str, tuple[int, int]] = {}
    for entry in entries:
        if entry.variant == "wake" and not _rotor(case):
            continue
        variables = (
            {"LAST_REVS_AVG": entry.last_revs}
            if entry.last_revs is not None
            else {"LAST_ITERS_AVG": entry.last_steps}
            if entry.last_steps is not None
            else case.variables
        )
        span = averaging_span(
            variables, last_step=last_step, per_revolution=clock.steps_per_revolution
        )
        if span is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: export_type avg_window needs an averaging window"
            )
        # P0470-FFR: a rotor row's wake entry exports the surface VTK, its wake on, per step.
        kinds = [
            {"sections": "sectional_loads", "wake": "vtk"}.get(entry.variant, "farfield_probes")
        ]
        if entry.variant == "power":
            entry_case = case.model_copy(
                update={"pproc": case.pproc.model_copy(update={"farfields": [entry]})}
            )
            if blade_loads_state(entry_case, entry)[0] in ("reused", "added"):
                # P0470-FFR: the disk correction averages the blade loads over the window.
                kinds.append("sectional_loads")
        for kind in kinds:
            previous = windows.get(kind, span)
            windows[kind] = (min(previous[0], span[0]), span[1])
    return tuple((first, last, kind) for kind, (first, last) in windows.items())
