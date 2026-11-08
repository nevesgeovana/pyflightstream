"""The surface export and trailing-edge detection probes of 0.56.0 (FR-3741, FR-3742).

Pipeline role: register two controlled probes on synthetic meshes, so the geometry build's
evidence gate (FR-1110) and the marking pass can rest on a measured effect rather than a log line.

EXPORT_SURFACE_MESH (PFS-2187.04). The blunt box of the 0.46.0 marking probes, two boundaries
(Body and Rim) of eight vertices and twelve triangles, imported in metres; the target exports
every boundary (``-1``) to an OBJ in the probe folder. The effect is the file the build reads
back: it is True when the OBJ holds the twelve faces over exactly the eight source vertices,
False when the file is missing or holds another mesh (a command that runs and writes nothing,
or writes something else, is broken), never guessed.

AUTO_DETECT_TRAILING_EDGES (PFS-2187.05). The sharp wing stub joined to a body of the 0.46.0
marking probes. The simulation is saved before and after the target (``save_state``) and both
saves are read with the measured mesh-block reader of those probes, which returns the mid-point
of every flagged edge. The effect is True when the wing's sharp trailing edge, the edge from
(2, 1, 0) to (2, 3, 0) with mid-point (2, 2, 0), is marked after the command and no edge was
marked before; False when the saved state before shows no edge and after shows no wing trailing
edge; None when either save is missing or in a layout the reader does not know, which is the
case on builds whose save layout the reader was never measured against. Stored coordinates
must be metres and the target edge unambiguous in comparable finite meshes. The coordinate
allowance is absolute (relative tolerance zero), local to this fixed synthetic probe. Extra
marked edges do not invalidate the presence-only result.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pyflightstream._fsm import (
    MeshReadError,
    _mesh_block,
    saved_mesh_coordinate_unit,
    trailing_edge_midpoints,
)
from pyflightstream.qa._spec_0460_marking import _POINTS, _geometry, _state
from pyflightstream.qa._spec_kit import _spec
from pyflightstream.qa.probes import ProbeArtifacts
from pyflightstream.script import Script

__all__: list[str] = []

_EXPORT = "EXPORT_SURFACE_MESH"
_DETECT = "AUTO_DETECT_TRAILING_EDGES"
_EXPORTED = "export.obj"
#: Faces of the blunt box: ten on Body and two on Rim (``_spec_0460_marking._FACES``).
_BOX_FACES = 12
#: Mid-point of the wing stub's sharp trailing edge, from (2, 1, 0) to (2, 3, 0).
_WING_TE = (2.0, 2.0, 0.0)
# A coordinate-identity allowance, not a solver or aerodynamic accuracy.
_COORDINATE_TOLERANCE_M = 1e-6


def _comparable_saves(workdir: Path, tolerance: float) -> bool:
    """Require metre coordinates, finite comparable meshes and an unambiguous target edge."""
    paths = [workdir / f"state_{stage}.fsm" for stage in ("before", "after")]
    try:
        if any(saved_mesh_coordinate_unit(path) != "METER" for path in paths):
            return False
        meshes = [_mesh_block(path) for path in paths]
    except (OSError, ValueError, MeshReadError):
        return False
    vertices, faces = meshes[0][:2]
    after_vertices, after_faces = meshes[1][:2]
    if faces != after_faces or len(vertices) != len(after_vertices):
        return False
    if any(not math.isfinite(c) for mesh in meshes for p in mesh[0] for c in p):
        return False
    edges = {
        tuple(sorted((a, b)))
        for face in faces
        for a, b in zip(face, face[1:] + face[:1], strict=True)
    }
    midpoints = {
        edge: tuple((vertices[edge[0]][i] + vertices[edge[1]][i]) / 2 for i in range(3))
        for edge in edges
    }
    targets = [
        e
        for e, p in midpoints.items()
        if max(abs(p[i] - _WING_TE[i]) for i in range(3)) <= tolerance
    ]
    if len(targets) != 1:
        return False
    target = targets[0]
    separation = min(
        (math.dist(midpoints[target], p) for e, p in midpoints.items() if e != target), default=0.0
    )
    # A geometry change large enough to exchange edge identities is not a comparable save.
    if any(
        math.dist(a, b) >= separation / 2 for a, b in zip(vertices, after_vertices, strict=True)
    ):
        return False
    # Distinct edges must be separated by more than twice the Euclidean allowance.
    for points in (vertices, after_vertices):
        midpoint = tuple((points[target[0]][i] + points[target[1]][i]) / 2 for i in range(3))
        for edge in edges - {target}:
            other = tuple((points[edge[0]][i] + points[edge[1]][i]) / 2 for i in range(3))
            if math.dist(midpoint, other) <= 2 * math.sqrt(3) * tolerance:
                return False
    return True


def _obj_reading(path: Path) -> dict[str, object] | None:
    """Faces, distinct vertices and group names of an OBJ; None when the file is absent."""
    if not path.is_file():
        return None
    vertices: list[tuple[float, float, float]] = []
    faces = 0
    groups: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = raw.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append(tuple(round(float(value), 9) for value in parts[1:4]))  # type: ignore[arg-type]
        elif parts[0] == "f":
            faces += 1
        elif parts[0] in ("g", "o") and len(parts) > 1:
            groups.append(" ".join(parts[1:]))
    return {"faces": faces, "vertices": sorted(set(vertices)), "groups": groups}


def _export_target(script: Script, workdir: Path) -> None:
    script.emit(_EXPORT, "OBJ", -1, workdir / _EXPORTED)


def _export_effect(artifacts: ProbeArtifacts) -> bool:
    reading = _obj_reading(artifacts.workdir / _EXPORTED)
    if reading is None:
        return False
    source = sorted({tuple(round(value, 9) for value in point) for point in _POINTS})
    return reading["faces"] == _BOX_FACES and reading["vertices"] == source


def _export_observe(artifacts: ProbeArtifacts) -> str:
    reading = _obj_reading(artifacts.workdir / _EXPORTED)
    if reading is None:
        return json.dumps({"file": None})
    vertices = reading["vertices"]
    assert isinstance(vertices, list)
    return json.dumps(
        {"faces": reading["faces"], "vertices": len(vertices), "groups": reading["groups"]}
    )


_spec(
    command=_EXPORT,
    build_target=_export_target,
    prelude=lambda script, workdir: _geometry(script, workdir),
    assert_effect=_export_effect,
    observe=_export_observe,
    effect_note=(
        "the OBJ the export writes holds the twelve faces of the imported two-boundary box "
        "over exactly its eight vertices"
    ),
)


def _detect_target(script: Script, workdir: Path) -> None:
    script.emit(_DETECT)


def _detect_reading(workdir: Path) -> dict[str, object]:
    before = _state(workdir / "state_before.fsm")
    after = _state(workdir / "state_after.fsm")
    if before is not None and after is not None and before.names != after.names:
        return {"before": None, "after": None}

    def edges(state: object) -> list[list[float]] | None:
        if state is None:
            return None
        return sorted([list(point) for point, _ in state.edges])  # type: ignore[attr-defined]

    return {"before": edges(before), "after": edges(after)}


def _detect_effect(
    artifacts: ProbeArtifacts, *, coordinate_tolerance_m: float = _COORDINATE_TOLERANCE_M
) -> bool | None:
    """Judge target presence with an overridable absolute coordinate allowance in metres."""
    if not math.isfinite(coordinate_tolerance_m) or coordinate_tolerance_m < 0:
        raise ValueError("coordinate_tolerance_m must be finite and nonnegative")
    if not _comparable_saves(artifacts.workdir, coordinate_tolerance_m):
        return None
    reading = _detect_reading(artifacts.workdir)
    before, after = reading["before"], reading["after"]
    if before is None or after is None or before:
        return None
    # The observation retains its legacy rounding; the verdict uses saved precision.
    try:
        midpoints = trailing_edge_midpoints(artifacts.workdir / "state_after.fsm")
    except (OSError, ValueError, MeshReadError):
        return None
    if any(not all(math.isfinite(c) for c in p) for p in midpoints):
        return None
    return any(
        max(abs(p[i] - _WING_TE[i]) for i in range(3)) <= coordinate_tolerance_m for p in midpoints
    )


_detect_effect.needs_saved_state = True  # type: ignore[attr-defined]


def _detect_observe(artifacts: ProbeArtifacts) -> str:
    return json.dumps(_detect_reading(artifacts.workdir))


_spec(
    command=_DETECT,
    build_target=_detect_target,
    prelude=lambda script, workdir: _geometry(script, workdir, wing_body=True),
    save_state=True,
    assert_effect=_detect_effect,
    observe=_detect_observe,
    effect_note=(
        "the saved simulation marks the sharp wing trailing edge, mid-point (2, 2, 0), after the "
        "command and no edge before it, read from both saves with the measured mesh-block reader"
    ),
)
