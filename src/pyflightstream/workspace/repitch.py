"""Small rigid blade pitch changes with source-ring hub rebuilding (PFS-2187.22).

The saved route replaces only coordinate rows: connectivity, quad pairing, face order,
trailing-edge flags, base regions and wake terminations retain their original identities.
"""

from __future__ import annotations

import json
import math
import tomllib
from pathlib import Path
from typing import Any

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import (
    InputValueError,
    NotApplicableWarning,
    PyflightstreamWarning,
    warn,
)
from pyflightstream._fsm import saved_mesh_coordinate_unit
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.cases.reference_blocks import frame_basis_for_shaft
from pyflightstream.workspace._pitch_axis import pitch_axes
from pyflightstream.workspace._refine._obj import ObjMesh, mesh_unit, obj_text, read_obj
from pyflightstream.workspace._repitch import HubSurface, surface_checks
from pyflightstream.workspace._repitch_grid import incidence, quality, rebuild, rings, root_loop
from pyflightstream.workspace._repitch_io import attachments, morphing_table, read_rotor
from pyflightstream.workspace._wheel import Faces, parse_axis, rotate, wheel_symmetry
from pyflightstream.workspace._wheel_fsm import _parse, _real_row

__all__ = ["repitch_mesh"]


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise InputValueError(f"repitch: {message}. No file was written.")


def _read(path: Path) -> tuple[ObjMesh, Any]:
    if path.suffix.lower() == ".obj":
        return read_obj(path), None
    _need(path.suffix.lower() == ".fsm", f"mesh {path} must be .obj or .fsm")
    parsed = _parse(path.read_bytes().decode("latin-1"))
    m = parsed.mesh
    ints = m["ints"]
    tri = np.stack([ints[2], ints[3], ints[4]], axis=1) - 1
    families: dict[str, list[list[int]]] = {h[4]: [] for h in m["heads"]}
    names = list(families)
    for i, t in enumerate(tri):
        partner = int(ints[10][i]) - 1
        if partner >= 0 and partner < i:
            continue
        face = t.tolist()
        if partner >= 0:
            _need(int(ints[10][partner]) == i + 1, "quad partners are not reciprocal")
            _need(ints[11][partner] == ints[11][i], "quad partners belong to different families")
            both = [
                *zip(face, face[1:] + face[:1], strict=True),
                *zip(tri[partner].tolist(), np.roll(tri[partner], -1).tolist(), strict=True),
            ]
            outer = [(a, b) for a, b in both if (b, a) not in both]
            _need(len(outer) == 4, "quad partner does not share an oppositely directed edge")
            face = [outer[0][0]]
            for _ in range(3):
                face.append(next(b for a, b in outer if a == face[-1]))
            # Fan triangulation must retain the saved pair's actual diagonal.
            shared = set(t.tolist()) & set(tri[partner].tolist())
            start = next(j for j, vertex in enumerate(face) if vertex in shared)
            face = face[start:] + face[:start]
        families[names[int(ints[11][i]) - 1]].append(face)
    return ObjMesh(m["xyz"].copy(), families), parsed


def _config(path: Path) -> dict[str, Any]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = morphing_table(data, "repitch", ("blades", "hub"))
    _need(isinstance(cfg, dict), f"{path} needs a [repitch] table")
    for key in set(cfg) - {
        "angle_deg",
        "max_angle_deg",
        "blades",
        "hub",
        "keep",
        "axis",
        "axes",
        "reference",
        "rotor",
        "rotor_axis",
        "reference_point",
    }:
        warn(f"repitch.{key} does not apply and is skipped", NotApplicableWarning)
    angle = float(cfg.get("angle_deg", math.nan))
    limit = float(cfg.get("max_angle_deg", 5.0))
    _need(
        math.isfinite(limit) and 0 < limit <= 5,
        f"max_angle_deg {limit!r} must be positive and at most 5 degrees",
    )
    _need(
        math.isfinite(angle) and abs(angle) <= limit,
        f"angle_deg {angle!r} exceeds max_angle_deg {limit:g}; use a smaller pitch change",
    )
    cfg["angle_deg"] = angle
    return cfg


def _own_axis(name: str, cfg: dict[str, Any]) -> Any:
    """Return the axis the table states for one blade (``axes`` before ``axis``), or None."""
    return cfg.get("axes", {}).get(name, cfg.get("axis"))


def _axis(name: str, cfg: dict[str, Any], rotor: Any, derived: dict[str, Any]) -> tuple[Any, Any]:
    spec = _own_axis(name, cfg)
    if spec is None and name in derived:
        return derived[name]
    spec = "auto" if spec is None else spec
    if isinstance(spec, dict):
        origin = np.asarray(spec.get("origin", []), dtype=float)
        _need(
            origin.shape == (3,) and bool(np.isfinite(origin).all()),
            f"blade {name!r}: repitch.axes.{name}.origin needs three finite coordinates",
        )
        return origin, parse_axis(spec.get("direction", []))
    _need(spec == "auto", f"blade {name!r}: axis must be auto or origin/direction")
    _need(
        rotor is not None and name in rotor.get("families_blades", []),
        f"blade {name!r} has no reference axis; add repitch.rotor_axis and "
        f"repitch.reference_point, repitch.axes.{name}.origin and direction, or "
        "repitch.reference",
    )
    main_axis = parse_axis(rotor["axis"])
    datum = rotor.get("blade1", {})
    _need(
        "zero" in datum and "azimuth_deg" in datum,
        f"blade {name!r}: reference rotor needs blade1.zero and blade1.azimuth_deg",
    )
    zero = parse_axis(datum["zero"])
    zero = np.asarray(frame_basis_for_shaft(tuple(main_axis), tuple(zero))[0])
    names = rotor["families_blades"]
    angle = float(datum["azimuth_deg"]) + names.index(name) * 360 / len(names)
    direction = rotate(zero[None, :], main_axis, np.zeros(3), angle)[0]
    sense = rotor.get("rpm_sign", 1)
    _need(sense in (-1, 1), "reference rpm_sign must be +1 or -1")
    direction *= -sense
    origin = np.array([float(rotor.get(k + "_m", 0)) for k in ("x", "y", "z")])
    return origin, direction


def _selection(cfg: dict[str, Any], mesh: ObjMesh, rotor: Any) -> tuple[list[str], list[str]]:
    blades = cfg.get("blades", [])
    if blades == "all" or blades == ["all"]:
        _need(rotor is not None, "blades=all needs repitch.reference")
        blades = rotor["families_blades"]
    hubs = cfg.get("hub", [])
    for key, names in (("blades", blades), ("hub", hubs)):
        _need(
            isinstance(names, list) and bool(names) and all(isinstance(n, str) for n in names),
            f"repitch.{key} must explicitly name nonempty families",
        )
        _need(len(set(names)) == len(names), f"repitch.{key} repeats a family")
        _need(
            not set(names) - mesh.families.keys(),
            f"repitch.{key} names absent families {sorted(set(names) - mesh.families.keys())}",
        )
    _need(not set(blades) & set(hubs), "blades and hub must be disjoint")
    keep = cfg.get("keep", [])
    _need(not set(keep) & set(blades + hubs), "keep overlaps blades or hub")
    for name in set(keep) - mesh.families.keys():
        warn(f"repitch.keep {name!r} is absent and skipped", NotApplicableWarning)
    return blades, hubs


def _blade_check(old: Any, new: Any, ids: Any, origin: Any, axis: Any, *, angle: float) -> dict:
    a, b = old[ids] - origin, new[ids] - origin
    axial = a @ axis
    u, v = a - np.outer(axial, axis), b - np.outer(b @ axis, axis)
    radius = np.linalg.norm(u, axis=1)
    usable = radius > max(float(radius.max()) * 1e-10, 1e-14)
    measured = np.degrees(
        np.arctan2(np.cross(u[usable], v[usable]) @ axis, np.sum(u[usable] * v[usable], axis=1))
    )
    error = float(np.max(np.abs(radius - np.linalg.norm(v, axis=1))))
    rigid_error = float(
        np.max(np.linalg.norm(rotate(new[ids], axis, origin, -angle) - old[ids], axis=1))
    )
    _need(
        rigid_error < 1e-11 * max(float(np.linalg.norm(a, axis=1).max()), 1),
        "blade shape is not a rigid rotation",
    )
    _need(
        bool(len(measured)) and bool(np.allclose(measured, angle, atol=1e-8, rtol=0)),
        "measured blade pitch change differs from angle_deg",
    )
    _need(error < 1e-11 * max(float(radius.max()), 1), "blade distance from pitch axis changed")
    selected = np.argsort(axial[usable])
    samples = selected[np.linspace(0, len(selected) - 1, 5).astype(int)]
    return {
        "connectivity_unchanged": True,
        "face_order_unchanged": True,
        "axis_distance_max_error": error,
        "rigid_max_error": rigid_error,
        "pitch_samples_deg": measured[samples].tolist(),
        "span_samples_mesh_unit": axial[usable][samples].tolist(),
        "pitch_min_deg": float(measured.min()),
        "pitch_max_deg": float(measured.max()),
    }


def repitch_mesh(mesh: str | Path, morphing: str | Path, out: str | Path) -> dict[str, Any]:
    """Repitch named blades, rebuild hub rings and write after every check.

    Parameters
    ----------
    mesh : str or Path
        Source OBJ or saved simulation, read only.
    morphing : str or Path
        TOML control file; axes use the mesh coordinates and angle uses degrees.
    out : str or Path
        New mesh of the source kind. Existing outputs are refused.

    Returns
    -------
    dict
        The checks also written beside the output as ``<out>.repitch.json``;
        ``checks["passed"]`` is false with ``checks["warnings"]`` when quality was warned.
    """
    path, control, target = Path(mesh), Path(morphing), Path(out)
    record = Path(str(target) + ".repitch.json")
    _need(target.resolve() != path.resolve(), "--out must differ from the source")
    _need(target.suffix.lower() == path.suffix.lower(), "--out must keep the source suffix")
    _need(not target.exists() and not record.exists(), "output or report exists; choose new --out")
    cfg = _config(control)
    source, parsed = _read(path)
    rotor = read_rotor(cfg, control, path)
    blades, hubs = _selection(cfg, source, rotor)
    unit = mesh_unit(path) if parsed is None else saved_mesh_coordinate_unit(path)
    if unit is None:
        warn(
            "repitch: mesh unit is unstated; surface distances assume metres", NotApplicableWarning
        )
        unit = "METER"
    _need(unit in METRES_PER_UNIT, f"mesh unit {unit!r} has no metre scale; state a known unit")
    new, report = _deform(source, cfg, rotor, blades, hubs, scale=float(METRES_PER_UNIT[unit]))
    report["distance_unit"] = "m"
    report["source_sha256"] = file_sha256(path)
    _write_output(path, target, source, parsed, new)
    _textio.write_text(record, json.dumps(report, indent=2) + "\n")
    return report


def _pitch_frame(
    source: ObjMesh, cfg: dict, rotor: Any, blades: list, hubs: list
) -> tuple[dict, Any, Any]:
    """Return the derived pitch axes, the hub chart's rotor frame and how they were found.

    A blade with an axis of its own (``axes`` or ``axis``) keeps it; the others take the rule of
    ``rotor_axis`` and ``reference_point`` when the table states either, else the reference's.
    """
    derived: dict[str, Any] = {}
    found = None
    needs = [n for n in blades if _own_axis(n, cfg) is None]
    if needs and ("rotor_axis" in cfg or "reference_point" in cfg):
        derived, found = pitch_axes(source.verts, source.families, needs, hubs, cfg)
    frame = None
    if rotor is not None:
        frame = (
            np.array([rotor.get(k + "_m", 0.0) for k in ("x", "y", "z")]),
            parse_axis(rotor["axis"]),
        )
    elif derived:
        frame = (next(iter(derived.values()))[0], parse_axis(cfg["rotor_axis"]))
    return derived, frame, found


def _turn_blades(
    source: ObjMesh, new: Any, cfg: dict, axes: tuple[Any, dict], names: tuple[list, list]
) -> tuple[list, list, set[int], dict]:
    """Turn each blade rigidly about its pitch axis; return its rings, motions and checks."""
    old, (rotor, derived), (blades, hubs) = source.verts, axes, names
    hub_faces = [f for n in hubs for f in source.families[n]]
    held = {
        v for n in source.families if n not in blades + hubs for f in source.families[n] for v in f
    }
    patches: list = []
    motions: list = []
    used: set[int] = set()
    report: dict = {}
    for name in blades:
        ids = source.family_vertices(name)
        _need(not set(ids) & (held | used), f"blade {name!r} shares nodes with a kept/other blade")
        used.update(ids.tolist())
        origin, axis = _axis(name, cfg, rotor, derived)
        if cfg["angle_deg"]:
            new[ids] = rotate(old[ids], axis, origin, cfg["angle_deg"])
        loop = root_loop(source.families[name], hub_faces, name)
        patches.append(rings(loop, hub_faces))
        motions.append((origin, axis, cfg["angle_deg"]))
        report[name] = {
            "faces": len(source.families[name]),
            "axis_origin": origin.tolist(),
            "axis_direction": axis.tolist(),
            **_blade_check(old, new, ids, origin, axis, angle=cfg["angle_deg"]),
        }
    return patches, motions, used | held, report


def _deform(
    source: ObjMesh, cfg: dict, rotor: Any, blades: list, hubs: list, *, scale: float = 1.0
) -> tuple[Any, dict]:
    """Compute the new coordinates and checks without touching output files."""
    old, new = source.verts, source.verts.copy()
    hub_faces = [f for n in hubs for f in source.families[n]]
    kept = [n for n in source.families if n not in blades + hubs]
    held = {v for n in kept for f in source.families[n] for v in f}
    report: dict[str, Any] = {"angle_deg": cfg["angle_deg"], "kept": kept, "blades": {}, "hub": {}}
    derived, frame, found = _pitch_frame(source, cfg, rotor, blades, hubs)
    if found is not None:
        report["pitch_axes"] = found
    patches, motions, taken, report["blades"] = _turn_blades(
        source, new, cfg, (rotor, derived), (blades, hubs)
    )
    interiors: set[int] = set()
    outer_nodes = {int(v) for patch in patches for v in patch[-1]}
    surface = HubSurface(old, hub_faces)
    for patch, motion in zip(patches, motions, strict=True):
        inner = set(patch[1:-1].ravel().tolist())
        _need(
            not inner & (taken | interiors | outer_nodes),
            "hub rings overlap a blade or another patch boundary",
        )
        interiors.update(inner)
        rebuild(old, new, patch, motion, surface, frame=frame)
    _need(bool(np.isfinite(new).all()), "hub smoothing produced nonfinite coordinates")
    all_faces = [f for fs in source.families.values() for f in fs]
    edge_map = incidence(all_faces)
    _need(not any(len(owners) > 2 for owners in edge_map.values()), "non-manifold edge in mesh")
    distances = surface_checks(surface, old, new, {int(v) for p in patches for v in p[0]}, scale)
    report["hub"] = _hub_checks(source, new, hubs)
    boundary = {v for e, owners in incidence(hub_faces).items() if len(owners) == 1 for v in e}
    fixed = sorted((boundary - (taken - held)) | held)
    _need(np.array_equal(old[fixed], new[fixed]), "non-root hub boundary moved")
    found = distances.pop("warnings") + [w for h in report["hub"].values() for w in h["warnings"]]
    report["checks"] = {
        "passed": not found,
        "warnings": found,
        "non_manifold_edges": 0,
        "root_gap": 0.0,
        "hub_boundary_unmoved": True,
        "triangles_added": 0,
        "ring_counts": [len(p) - 1 for p in patches],
        **distances,
    }
    _periodicity(source, new, _periodic_set(cfg, rotor, blades, hubs, frame), report["checks"])
    return new, report


def _hub_checks(source: ObjMesh, new: Any, hubs: list) -> dict:
    """Measure the hub's quality against the source; warn of folded and reversed cells.

    A folded cell (a corner's scaled Jacobian at or below zero) and a reversed cell (its normal
    against the source cell's) are quality: each is warned with its count, the least scaled
    Jacobian beside the source's, and listed under the hub's ``warnings``.
    """
    old = source.verts
    report = {}
    for name in hubs:
        faces = source.families[name]
        before, after = quality(old, faces), quality(new, faces)
        reversed_cells = 0
        for face in faces:
            a, b = old[face], new[face]
            na = np.cross(a, np.roll(a, -1, axis=0)).sum(axis=0)
            nb = np.cross(b, np.roll(b, -1, axis=0)).sum(axis=0)
            reversed_cells += float(na @ nb) <= 0
        found = []
        if after["folded_cells"]:
            found.append(
                f"hub {name!r} has {after['folded_cells']} folded cell(s); the least scaled "
                f"Jacobian is {after['min_scaled_jacobian']:.6g} (source "
                f"{before['min_scaled_jacobian']:.6g})"
            )
        if reversed_cells:
            found.append(f"hub {name!r} has {reversed_cells} reversed cell(s) against the source")
        for sentence in found:
            warn(f"repitch: {sentence}; the mesh is written", PyflightstreamWarning)
        report[name] = {
            "source_cells": len(faces),
            "output_cells": len(faces),
            "source_quality": before,
            "output_quality": after,
            "reversed_cells": reversed_cells,
            "warnings": found,
        }
    return report


def _periodic_set(cfg: dict, rotor: Any, blades: list, hubs: list, frame: Any) -> Any:
    """Return the wheel the periodicity check reads (blades, hubs, axis, origin, copies), or None.

    A reference that declares several blades turns it on, about its own axis, over every blade
    it declares; without one, several named blades turn it on, about ``rotor_axis`` through the
    hub centre. Only the blades and the hub are read, so another body in the file (a wing, a
    fuselage) does not take part.
    """
    if rotor is not None and len(rotor["families_blades"]) > 1:
        origin = np.array([rotor.get(k + "_m", 0.0) for k in ("x", "y", "z")])
        names = list(rotor["families_blades"])
        return names, hubs, parse_axis(rotor["axis"]), origin, len(names)
    if rotor is None and frame is not None and len(blades) > 1:
        return blades, hubs, frame[1], frame[0], len(blades)
    return None


def _symmetry(verts: Any, faces: list, axis: Any, origin: Any, copies: int) -> dict:
    """Return the N-fold invariance of some faces, read on their own nodes."""
    ids = np.unique([v for f in faces for v in f])
    local = np.full(len(verts), -1, dtype=np.int64)
    local[ids] = np.arange(len(ids))
    picked = Faces.of([[int(local[v]) for v in f] for f in faces])
    return wheel_symmetry(verts[ids], picked, axis, origin, copies=copies, tol=1e-7)["invariance"]


def _whole(inv: dict) -> bool:
    return bool(inv["nodes_mapped"] == inv["nodes"] and inv["faces_mapped"] == inv["faces"])


def _periodicity(source: ObjMesh, new: Any, wheel: Any, checks: dict) -> None:
    """Check the blades and hub of a wheel; refuse only what the repitch made unperiodic."""
    if wheel is None:
        warn(
            "repitch: full-wheel periodicity does not apply without a wheel reference or "
            "several named blades about rotor_axis; skipped",
            NotApplicableWarning,
        )
        return
    names, hubs, axis, origin, copies = wheel
    faces = [f for n in [*names, *hubs] if n in source.families for f in source.families[n]]
    inv = _symmetry(new, faces, axis, origin, copies)
    checks["periodicity"] = inv
    if _whole(inv):
        return
    _need(
        not _whole(_symmetry(source.verts, faces, axis, origin, copies)),
        "wheel periodicity failed; repitch every blade by the same angle",
    )
    warn(
        "repitch: the blades and hub of the source are not periodic either, so the wheel "
        "periodicity is reported and does not refuse",
        NotApplicableWarning,
    )


def _write_output(path: Path, target: Path, source: ObjMesh, parsed: Any, new: Any) -> None:
    """Prepare every payload and validate readback before writing any output."""
    if parsed is None:
        payload = obj_text(ObjMesh(new, source.families, source.header)).encode("utf-8")
        extra = attachments(path, target, source, new, payload)
    else:
        for k in range(3):
            parsed.lines[parsed.mesh["tail"] + 2 + k] = _real_row(new[:, k])
        payload = "\n".join(parsed.lines).encode("latin-1")
        checked = _parse(payload.decode("latin-1"))
        _need(np.array_equal(checked.mesh["xyz"], new), "saved coordinate readback differs")
        extra = {}
    for file in extra:
        _need(not file.exists(), f"attachment {file} exists; choose new --out")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    for file, content in extra.items():
        file.write_bytes(content)
