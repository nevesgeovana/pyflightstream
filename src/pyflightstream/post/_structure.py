"""Structural products decoded from a coupled point's recorded working folder."""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import (
    InputValueError,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream._tokens import CONTEXT_COLUMNS, POLAR_ID_COLUMN
from pyflightstream.fsi.config import (
    DIRECT_NODE_TYPES,
    FsiConfig,
    config_sha256,
    load_config,
)
from pyflightstream.fsi.kinematics import decode_station_translations
from pyflightstream.fsi.nodes import (
    NodeOrderingMap,
    generate_node_layout,
    read_fsidisp,
    unflatten_translations,
)
from pyflightstream.fsi.state import load_state
from pyflightstream.post._tables import context_row

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext


def _decoded_structure(record: Any):
    """Return the folder, source, station rows and tips of a coupled record, or raise."""
    if not record.cwd:
        raise InputValueError(
            "the coupled record has no working folder; point the record at its working folder"
        )
    folder = Path(record.cwd)
    config_path = folder / "config.json"
    if file_sha256(config_path) != record.inputs_sha256.get("config.json"):
        raise InputValueError(
            "config.json differs from the coupled run's recorded input; "
            "restore the recorded config.json or start a new coupled run"
        )
    config = load_config(config_path)
    layout = generate_node_layout(config)
    source, flat = _recorded_displacements(folder, config, layout)
    rows = []
    tips = []
    for blade, translations in enumerate(unflatten_translations(layout, flat), start=1):
        deflection, twist = decode_station_translations(
            translations, np.asarray(layout.le_offset_m), np.asarray(layout.te_offset_m)
        )
        for station, radius in enumerate(config.blade.station_radii_m):
            rows.append((blade, radius, deflection[station], math.degrees(twist[station])))
        tips.append((float(deflection[-1]), math.degrees(float(twist[-1]))))
    return folder, source, rows, tips


def structure_products(ctx: SimContext) -> None:
    """Write deflection and twist, retaining recorded history without re-solving."""
    for point in ctx.points:
        record = ctx.record_of[point.name]
        if "fsi-provenance.json" not in record.inputs_sha256:
            continue
        relative = f"structure/{point.name}_deflection.csv"
        try:
            folder, source, rows, tips = _decoded_structure(record)
        except (OSError, ValueError) as error:
            ctx.skipped[relative] = f"structure: {error}"
            continue
        target = ctx.target(ctx.out / relative)
        for run_id in ctx.sources[point.name]:
            ctx.structure_tips[run_id] = tips
        target.parent.mkdir(parents=True, exist_ok=True)
        # POL AND THE CONDITION LEAD EVERY TABLE THE POST WRITES (definitions page): a
        # station row says which polar and which flight condition it deflects under.
        context = context_row(ctx.condition(point), ctx.reference.as_lengths())
        with _textio.open_text(target, "w") as handle:
            writer = _textio.csv_writer(handle)
            writer.writerow(
                (
                    POLAR_ID_COLUMN,
                    *CONTEXT_COLUMNS,
                    "blade",
                    "station_radius_m",
                    "deflection_m",
                    "twist_deg",
                )
            )
            writer.writerows((ctx.sim_id, *context, *row) for row in rows)
        ctx.add(
            target,
            {
                "runs": ctx.sources[point.name],
                "kind": "structure",
                "source_sha256": file_sha256(source),
            },
        )
        history = folder / "fsi_convergence_log.csv"
        history_relative = f"structure/{point.name}_history.csv"
        if not history.is_file():
            ctx.skipped[history_relative] = (
                f"structure: the coupled run's working folder holds no {history.name}"
            )
            continue
        try:
            history_text = history.read_text(encoding="utf-8")
        except (OSError, ValueError) as error:
            # ValueError is UnicodeDecodeError: the history costs only itself.
            ctx.skipped[history_relative] = f"structure: {history.name} cannot be read: {error}"
            continue
        target = ctx.target(ctx.out / history_relative)
        _textio.write_text(target, history_text)
        ctx.add(
            target,
            {
                "runs": ctx.sources[point.name],
                "kind": "structure_history",
                "source_sha256": file_sha256(history),
            },
        )


def append_tip_columns(ctx: SimContext, path: Path, runs: Sequence[str]) -> None:
    """Append each row's own recorded tip quantities, retaining all existing cells."""
    count = max((len(ctx.structure_tips.get(run, [])) for run in runs), default=0)
    if not count:
        return
    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
    prefix = []
    if len(rows) > 1 and len(rows[0]) == 1 and len(rows[1]) > 1:
        prefix = rows[:1]
        rows = rows[1:]
    if not rows or len(rows) - 1 != len(runs):
        ctx.skipped[f"{path.relative_to(ctx.out).as_posix()}#structure"] = (
            "tip quantities require one recorded run per table row; row attribution is ambiguous"
        )
        return
    columns = [
        f"{quantity}_blade_{blade}"
        for blade in range(1, count + 1)
        for quantity in ("tip_deflection_m", "tip_twist_deg")
    ]
    if collisions := set(columns).intersection(rows[0]):
        ctx.skipped[f"{path.relative_to(ctx.out).as_posix()}#structure"] = (
            f"tip quantities would replace existing columns {sorted(collisions)}; "
            "rename those columns in the pproc names or equations before adding structural tips"
        )
        return
    rows[0].extend(columns)
    for row, run in zip(rows[1:], runs, strict=True):
        tips = ctx.structure_tips.get(run, [])
        row.extend(
            str(value)
            for blade in range(count)
            for value in (tips[blade] if blade < len(tips) else ("NA", "NA"))
        )
    with _textio.open_text(path, "w") as handle:
        _textio.csv_writer(handle).writerows([*prefix, *rows])


def _recorded_displacements(folder: Path, config: FsiConfig, layout: NodeOrderingMap):
    """Read the applied displacement source and validate its recorded configuration."""
    if config.morphing in DIRECT_NODE_TYPES:
        source = folder / "state.json"
        state = load_state(source)
        if state.config_sha256 != config_sha256(config):
            raise InputValueError(
                "direct station state does not match the recorded configuration; "
                "rerun the coupling with the same configuration"
            )
        if state.station_displacements_m is None:
            raise InputValueError(
                "direct state has no recorded applied station displacements; "
                "rerun the coupling so the displacements are recorded"
            )
        flat = np.asarray(state.station_displacements_m, dtype=float)
    else:
        source = folder / "FSIDisp.txt"
        flat = read_fsidisp(source, expected_rows=layout.total_nodes)
    if not np.isfinite(flat).all():
        raise InputValueError(
            "structural displacements contain non-finite values; "
            "check the structural solve that wrote them"
        )
    return source, flat


# ------------------------------------------------- the placement check (FR-3416) --

#: The post product that checks where the solver placed a coupled blade, step by step (FR-3416).
PLACEMENT_CHECK_PRODUCT = "placement_check"
#: A step is misplaced when the median distance of its cut points to the blade at its
#: prescribed azimuth exceeds this tolerance and their median distance to the blade at its
#: import azimuth is smaller [m] (FR-3416). Basis: above the beam's deflection, which moves the
#: cuts millimetres off the undeformed blade, and well below the arc a blade misplaced by one
#: step travels at the stations checked (its radius times the step's turn), so a blade one step
#: or more from its prescribed azimuth is named.
PLACEMENT_TOLERANCE_M = 0.02
#: The columns of ``structure/<point>_placement_check.csv`` after ``POL`` and the condition.
PLACEMENT_CHECK_COLUMNS = (
    "blade",
    "step",
    "prescribed_azimuth_deg",
    "cut_points",
    "prescribed_median_m",
    "prescribed_p95_m",
    "import_median_m",
    "import_p95_m",
    "misplaced",
    "not_judged",
)
#: The provenance record the run stages for the check (``fsi-provenance.json``): the mesh
#: file's metres per unit, the hub, whether the row moves the mesh, and each blade's group.
BLADE_MESH_RECORD = "blade_mesh"


def _turned(points: np.ndarray, angle_rad: float) -> np.ndarray:
    """Turn ``points`` by ``angle_rad`` about +X (+Z toward -Y), the rotor axis of a coupled row."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.asarray(points, dtype=float) @ np.array([[1.0, 0.0, 0.0], [0.0, c, s], [0.0, -s, c]])


def placement_check(
    cuts: Mapping[int, np.ndarray],
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    step_azimuth_rad: float,
    tolerance_m: float = PLACEMENT_TOLERANCE_M,
) -> list[dict[str, object]]:
    """Measure where the solver placed a turning blade at each step, from its exported cuts.

    The definition of record is the placement check of
    ``definitions/what-every-product-states.md``. At step ``k`` the blade's
    prescribed azimuth is ``k step_azimuth_rad`` about +X; its import azimuth is
    zero, the geometry as imported. Every exported cut point is measured to the
    undeformed blade surface placed at each: ``prescribed`` is the distance of the
    point turned back by the prescribed azimuth to the blade, ``import`` its
    distance to the blade as imported. A step is misplaced when the median
    prescribed distance exceeds ``tolerance_m`` and the median import distance is
    smaller. A step with no cut point states ``NA`` distances and is not misplaced.

    Parameters
    ----------
    cuts : mapping of int to numpy.ndarray
        The cut points of each step, shape ``(n, 3)``, in the frame the blade was imported in [m].
    vertices, faces : numpy.ndarray
        The blade's surface as imported: vertices ``(v, 3)`` [m] and 0-based triangles ``(f, 3)``.
    step_azimuth_rad : float
        The blade's turn per time step about +X [rad], signed with the rotor's hand.
    tolerance_m : float, optional
        The misplacement tolerance [m], :data:`PLACEMENT_TOLERANCE_M` by default.

    Returns
    -------
    list of dict
        One row per step in step order, keyed by :data:`PLACEMENT_CHECK_COLUMNS` except ``blade``.

    Examples
    --------
    >>> import numpy as np
    >>> from pyflightstream.post._structure import placement_check
    >>> plate = np.array([[0.0, -0.1, 0.5], [0.0, 0.1, 0.5], [0.0, 0.1, 1.5], [0.0, -0.1, 1.5]])
    >>> faces = np.array([[0, 1, 2], [0, 2, 3]])
    >>> rows = placement_check({1: plate[:2]}, plate, faces, step_azimuth_rad=np.pi / 2)
    >>> rows[0]["misplaced"]
    True
    """
    from pyflightstream._mesh import mesh_reader

    surface = mesh_reader().Trimesh(
        vertices=np.asarray(vertices, dtype=float), faces=np.asarray(faces), process=False
    )
    rows: list[dict[str, object]] = []
    for step in sorted(cuts):
        points = np.asarray(cuts[step], dtype=float).reshape(-1, 3)
        azimuth = step * step_azimuth_rad
        row: dict[str, object] = {
            "step": step,
            "prescribed_azimuth_deg": round(math.degrees(azimuth) % 360.0, 9),
            "cut_points": len(points),
        }
        if not len(points):
            rows.append(
                {
                    **row,
                    **dict.fromkeys(PLACEMENT_CHECK_COLUMNS[4:8], "NA"),
                    "misplaced": False,
                    "not_judged": "",
                }
            )
            continue
        prescribed = surface.nearest.on_surface(_turned(points, -azimuth))[1]
        imported = surface.nearest.on_surface(points)[1]
        stats = {
            "prescribed_median_m": float(np.median(prescribed)),
            "prescribed_p95_m": float(np.percentile(prescribed, 95.0)),
            "import_median_m": float(np.median(imported)),
            "import_p95_m": float(np.percentile(imported, 95.0)),
        }
        misplaced = (
            stats["prescribed_median_m"] > tolerance_m
            and stats["import_median_m"] < stats["prescribed_median_m"]
        )
        rows.append({**row, **stats, "misplaced": misplaced, "not_judged": ""})
    return rows


def _not_judged_reason(blade_mesh: Mapping[str, Any] | None) -> str | None:
    """Return why the recorded mesh cannot be placed where the solver has the blade, or None."""
    if not isinstance(blade_mesh, Mapping):
        return (
            f"the run's fsi-provenance.json records no {BLADE_MESH_RECORD} (a run staged before "
            "the package recorded it), so the mesh file's length unit and the hub are not known"
        )
    if blade_mesh.get("moves_mesh") is not False:
        return (
            "the row moves the mesh before the solve, so the mesh file does not hold the blade "
            "where the solver has it"
        )
    factor = blade_mesh.get("metres_per_unit")
    if not isinstance(factor, int | float) or not math.isfinite(factor) or factor <= 0:
        return "the mesh's import unit names no length"
    return None


def placement_check_of_mesh(
    blades: Sequence[tuple[str, Mapping[int, np.ndarray]]],
    geometry: Path,
    blade_mesh: Mapping[str, Any] | None,
    *,
    step_azimuth_rad: float,
    tolerance_m: float = PLACEMENT_TOLERANCE_M,
) -> tuple[list[tuple[object, ...]], str | None]:
    """Return the placement check rows of a coupled point's blades, read off its mesh file.

    The mesh file is read as the run staged it in ``blade_mesh`` (FR-3416): scaled
    to metres by its ``metres_per_unit``, each blade from its ``groups`` name, and
    both the blade and the exported cuts measured about the hub ``hub_m``, on
    which the blades turn about +X (:func:`placement_check`). Where the record is
    missing (a run staged before the package recorded it), the row moved the mesh, or the unit
    names no length, every step is stated not judged, with the reason in the
    ``not_judged`` column, ``NA`` distances and ``NA`` for ``misplaced``.

    Parameters
    ----------
    blades : sequence of (str, mapping of int to numpy.ndarray)
        Each coupled blade, numbered from 1 in this order, and its cut points per step [m].
    geometry : pathlib.Path
        The OBJ the run imported.
    blade_mesh : mapping or None
        The ``blade_mesh`` record of the run's ``fsi-provenance.json``.
    step_azimuth_rad : float
        The blades' turn per time step about +X [rad], signed with the rotor's hand.
    tolerance_m : float, optional
        The misplacement tolerance [m].

    Returns
    -------
    tuple
        The rows, each ``(blade, *the other columns of PLACEMENT_CHECK_COLUMNS)``, and the
        reason the steps were not judged, or None.
    """
    from pyflightstream._mesh import obj_group_surface

    reason = _not_judged_reason(blade_mesh)
    rows: list[tuple[object, ...]] = []
    for number, (name, cuts) in enumerate(blades, start=1):
        if reason is not None:
            for step in sorted(cuts):
                azimuth = step * step_azimuth_rad
                rows.append(
                    (
                        number,
                        step,
                        round(math.degrees(azimuth) % 360.0, 9),
                        len(np.asarray(cuts[step]).reshape(-1, 3)),
                        *("NA",) * 5,
                        reason,
                    )
                )
            continue
        assert blade_mesh is not None  # a missing record is a reason
        groups = blade_mesh.get("groups")
        group = groups.get(name, name) if isinstance(groups, Mapping) else name
        hub = np.asarray(blade_mesh.get("hub_m") or (0.0, 0.0, 0.0), dtype=float)
        raw, faces = obj_group_surface(geometry, str(group))
        vertices = raw * float(blade_mesh["metres_per_unit"]) - hub
        about_hub = {
            step: np.asarray(points, dtype=float).reshape(-1, 3) - hub
            for step, points in cuts.items()
        }
        for row in placement_check(
            about_hub, vertices, faces, step_azimuth_rad=step_azimuth_rad, tolerance_m=tolerance_m
        ):
            rows.append((number, *(row[column] for column in PLACEMENT_CHECK_COLUMNS[1:])))
    return rows, reason


def section_cut_points(path: Path, sections: Sequence[int]) -> np.ndarray:
    """Return the X, Y, Z of the cut points of the 1-based ``sections`` of one export."""
    from pyflightstream.results.exports import parse_surface_sections

    report = parse_surface_sections(path.read_text(encoding="utf-8", errors="replace"))
    xyz = [report.columns.index(axis) for axis in ("X", "Y", "Z")]
    chosen = [s.values[:, xyz] for s in report.sections if s.index in sections and s.count]
    return np.vstack(chosen) if chosen else np.zeros((0, 3))


def _blade_sections(record: Any, blade: str) -> list[int]:
    """Return the 1-based section numbers of the record's layout that cut ``blade``."""
    numbers: list[int] = []
    start = 0
    for block in record.sections_layout or ():
        count = int(block.get("count", 0))
        if list(block.get("families") or ()) == [blade]:
            numbers.extend(range(start + 1, start + count + 1))
        start += count
    return numbers


def _blade_geometry(ctx: SimContext, record: Any) -> Path:
    """Return the OBJ the coupled run imported, its digest the recorded one."""
    for name, digest in record.inputs_sha256.items():
        if Path(name).name != name or not name.lower().endswith(".obj"):
            continue
        path = ctx.workspace.sim_dir(record.sim_id) / "inputs" / name
        if path.is_file() and file_sha256(path) == digest:
            return path
    raise InputValueError(
        "the run imported no OBJ whose recorded copy is in the simulation's inputs; the check "
        "reads the blade as imported from it"
    )


def _rotor_hand(record: Any) -> float:
    """Return -1 for a rotor the record turned at negative speed, else +1."""
    reductions = record.reductions if isinstance(record.reductions, Mapping) else {}
    rotors = reductions.get("rotors")
    speeds = [
        float(block["rpm"])
        for block in (rotors.values() if isinstance(rotors, Mapping) else ())
        if isinstance(block, Mapping) and isinstance(block.get("rpm"), int | float)
    ]
    flat = reductions.get("rpm")
    if isinstance(flat, int | float):
        speeds.append(float(flat))
    return -1.0 if speeds and speeds[0] < 0 else 1.0


def _placement_rows(
    ctx: SimContext, record: Any
) -> tuple[list[tuple[object, ...]], str | None] | None:
    """Return one coupled point's placement rows and any not-judged reason, None with no cut."""
    import json

    from pyflightstream.fsi.loads import SectionFamilyMap
    from pyflightstream.post._condition import classify_record_outputs
    from pyflightstream.post.series import stamped_exports

    kinds = classify_record_outputs(record)
    named = kinds.get("loads") or kinds.get("sectional_loads") or kinds.get("sections")
    if named is None or not record.cwd:
        return None
    stem = named[: -len(".txt")] if "loads" in kinds else named.rsplit("_", 1)[0]
    folder = Path(record.cwd)
    exports = stamped_exports(ctx.workspace.sim_dir(record.sim_id), stem, folder).get(
        ("_cp", "txt"), {}
    )
    if not exports:
        return None
    config = load_config(folder / "config.json")
    if config.time_increment_s is None:
        raise InputValueError("config.json states no time increment, so no step has an azimuth")
    turn = _rotor_hand(record) * config.omega_rad_per_s * config.time_increment_s
    families = SectionFamilyMap.model_validate_json(
        (folder / "fsi_family_map.json").read_text(encoding="utf-8-sig")
    )
    geometry = _blade_geometry(ctx, record)
    provenance = json.loads((folder / "fsi-provenance.json").read_text(encoding="utf-8-sig"))
    blade_mesh = provenance.get(BLADE_MESH_RECORD) if isinstance(provenance, dict) else None
    blades = []
    for family in (f for f in families.families if f.is_blade):
        sections = _blade_sections(record, family.name)
        cuts = {step: section_cut_points(path, sections) for step, path in exports.items()}
        blades.append((family.name, cuts))
    return placement_check_of_mesh(blades, geometry, blade_mesh, step_azimuth_rad=turn)


def placement_check_products(ctx: SimContext) -> None:
    """Write ``structure/<point>_placement_check.csv`` for each coupled unsteady rotor point.

    Per blade and per step, the distances of the solver's exported cuts to the
    blade at its prescribed and at its import azimuth (:func:`placement_check`).
    A point with a misplaced step is warned, naming the steps. A point whose
    steps cannot be judged (:func:`placement_check_of_mesh`) writes them as not
    judged, with the reason, and is warned once. A point that exported no cut
    writes nothing; one whose inputs cannot be read is skipped with its reason.
    """
    for point in ctx.points:
        record = ctx.record_of[point.name]
        if "fsi-provenance.json" not in record.inputs_sha256 or record.recipe != "unsteady_rotor":
            continue
        relative = f"structure/{point.name}_{PLACEMENT_CHECK_PRODUCT}.csv"
        try:
            placed = _placement_rows(ctx, record)
        except (OSError, ValueError, PyflightstreamError) as error:
            ctx.skipped[relative] = f"{PLACEMENT_CHECK_PRODUCT}: {error}"
            continue
        if placed is None:
            continue
        rows, reason = placed
        if reason is not None:
            warn(
                f"{point.name}: {PLACEMENT_CHECK_PRODUCT} states its steps not judged: {reason} "
                f"({relative}).",
                PyflightstreamWarning,
                stacklevel=2,
            )
        target = ctx.target(ctx.out / relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        context = context_row(ctx.condition(point), ctx.reference.as_lengths())
        with _textio.open_text(target, "w") as handle:
            writer = _textio.csv_writer(handle)
            writer.writerow((POLAR_ID_COLUMN, *CONTEXT_COLUMNS, *PLACEMENT_CHECK_COLUMNS))
            writer.writerows((ctx.sim_id, *context, *row) for row in rows)
        ctx.add(target, {"runs": ctx.sources[point.name], "kind": PLACEMENT_CHECK_PRODUCT})
        flag = PLACEMENT_CHECK_COLUMNS.index("misplaced")
        misplaced = sorted({int(str(row[1])) for row in rows if row[flag] is True})
        if misplaced:
            warn(
                f"{point.name}: {PLACEMENT_CHECK_PRODUCT} finds the coupled blade's cuts off its "
                f"prescribed azimuth and nearer its import azimuth in steps "
                f"{', '.join(map(str, misplaced))} ({relative}).",
                PyflightstreamWarning,
                stacklevel=2,
            )
