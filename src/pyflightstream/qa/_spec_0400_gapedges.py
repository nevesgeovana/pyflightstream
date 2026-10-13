"""The mesh-edge instruments of the 0.40.0 command-gap probes.

Pipeline role: readers of the edges a saved mesh marks, the judges of what a probe
did to them and the builds that mark them. ``pyflightstream.qa._spec_0400_gapkit``
imports every name here back.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._fsm import MESH_MARKER as _MESH_MARKER
from pyflightstream._fsm import (
    trailing_edge_midpoints,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _WING,
    Build,
    Judge,
    Reading,
    _names,
    _state,
    _states_read,
)
from pyflightstream.qa._spec_ccs_noise import (
    _ccs_assign,
    _ccs_import,
    _ccs_initialize,
    _ccs_select,
)
from pyflightstream.qa._spec_kit import _emit, _seq
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.geometry import wing_triangles
from pyflightstream.qa.probes import ProbeArtifacts
from pyflightstream.script import Script
from pyflightstream.script.helpers import (
    render_wake_edge_node_file,
    wake_edge_import_token,
)


def mesh_edges(path: Path) -> dict[str, object]:
    """Read a saved mesh block's face shapes and the edges its slot rows mark, quads included.

    The package's reader (``pyflightstream._fsm``) reads triangles only, measured
    on the solver's saves (RPT-065): three vertex-index rows, then per-face rows
    up to five T/F rows, the second to fourth of which flag the edges (1,2),
    (2,3) and (3,1). A loft may save quadrilaterals, whose layout no run has
    measured, and a reader that refuses them would leave a loft's edges
    unprobed for a reason that is not the loft's. So this probe reader carries
    the stated hypothesis for a block whose faces have up to K corners: K
    vertex-index rows, then the T/F rows, of which rows 2 to K+1 flag the edges
    (i, i+1) of each face, wrapping on the face's own corner count. Whatever it
    finds is reported with the face shapes and the T/F row count, so the
    reading shows when the hypothesis did not hold; the format becomes the
    package reader's once a run has measured it.
    """
    result: dict[str, object] = {"edges": None}
    if not path.is_file():
        result["error"] = f"{path.name} absent"
        return result
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = next(i for i, line in enumerate(lines) if line.strip() == _MESH_MARKER) + 1
        rows = _BlockRows(lines[start:])
        rows.skip(2)
        rows.skip(3 * int(rows.next_line()))
        faces = int(rows.next_line())
        rows.tokens()
        corners = [int(t) for t in rows.tokens()]
        result["face_shapes"] = {str(k): corners.count(k) for k in sorted(set(corners))}
        slots = [
            [int(t) - 1 if t.lstrip("-").isdigit() else -1 for t in rows.tokens()]
            for _ in range(max(corners))
        ]
        flags, after = rows.flag_rows(faces)
        result["flag_rows"] = len(flags)
        if after != ["0"]:
            result["error"] = f"the line after the T/F rows reads {after[:3]}"
            return result
        rows.next_line()
        axes = [[float(t) for t in rows.tokens()] for _ in range(3)]
        vertices = list(zip(*axes, strict=True))
        result["edges"] = len(_marked_midpoints(vertices, corners, slots, flags))
    except (StopIteration, ValueError, IndexError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    return result


class _BlockRows:
    """Step through the rows of a mesh block, comma-separated tokens per row."""

    def __init__(self, lines: list[str]) -> None:
        self._rows = iter(lines)

    def next_line(self) -> str:
        return next(self._rows).strip()

    def skip(self, count: int) -> None:
        for _ in range(count):
            next(self._rows)

    def tokens(self) -> list[str]:
        return [t.strip() for t in next(self._rows).split(",") if t.strip()]

    def flag_rows(self, faces: int) -> tuple[list[list[bool]], list[str]]:
        """Skip the per-face number rows, read the T/F rows, and return the row after them."""
        flags: list[list[bool]] = []
        while True:
            row = self.tokens()
            if row and set(row) <= {"T", "F"} and len(row) == faces:
                flags.append([t == "T" for t in row])
            elif flags:
                return flags, row


def _marked_midpoints(
    vertices: list[tuple[float, ...]],
    corners: list[int],
    slots: list[list[int]],
    flags: list[list[bool]],
) -> set[tuple[float, ...]]:
    """Return the mid-points of the edges T/F rows 2 to K+1 flag, edge (i, i+1) per face."""
    found: set[tuple[float, ...]] = set()
    for edge_row in range(1, min(len(slots) + 1, len(flags))):
        slot = edge_row - 1
        for face, flagged in enumerate(flags[edge_row]):
            n = corners[face]
            if flagged and slot < n:
                a = vertices[slots[slot][face]]
                b = vertices[slots[(slot + 1) % n][face]]
                found.add(tuple(round((p + q) / 2, 9) for p, q in zip(a, b, strict=True)))
    return found


def edge_count(path: Path) -> int | None:
    """Count the trailing edges a saved simulation marks, or None when it cannot be read."""
    if not path.is_file():
        return None
    try:
        return len(trailing_edge_midpoints(path))
    except (OSError, ValueError, QaEvidenceError):
        found = mesh_edges(path).get("edges")
        return found if isinstance(found, int) else None


def edges_kept(name: str) -> Judge:
    """Judge a loft asked to mark its trailing edges: marked True, none False, unreadable None.

    Strict on a read file, triangles or quadrilaterals alike (:func:`mesh_edges`):
    a loft told to mark its trailing edges that saves none did not do what it was
    asked. Only a block neither reader can read records unprobed.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        found = edge_count(artifacts.workdir / name)
        if found is None:
            return None
        return found > 0

    return check


def _edges_read(name: str, *extra: str) -> Reading:
    states = _states_read(name, *extra)

    def read(artifacts: ProbeArtifacts) -> str:
        path = artifacts.workdir / name
        found = edge_count(path)
        shape = mesh_edges(path)
        shown = {k: v for k, v in shape.items() if k != "edges"}
        return f"{name} marks {found} trailing edges, block {shown}; " + states(artifacts)

    return read


def _boundaries_at_least(name: str, count: int) -> Judge:
    def check(artifacts: ProbeArtifacts) -> bool | None:
        names = _names(artifacts.workdir / name)
        return True if names and len(names) >= count else None

    return check


def _file_written(name: str) -> Judge:
    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / name
        return True if path.is_file() and path.stat().st_size > 0 else None

    return check


def _deflected(angle: float) -> Build:
    """Emit the reopen probes' control surface in the ten-argument PARAMETRIC form."""
    return _emit(
        "NEW_CCS_WING_CONTROL_SURFACE",
        "PYFS_AIL",
        0.5,
        0.9,
        0.25,
        0.25,
        0.5,
        angle,
        1.0,
        "PARAMETRIC",
        "Y",
    )


_DEFLECTED = _deflected(20.0)


_CCS_WING_CURVES = _seq(_ccs_initialize, _ccs_import(1), _ccs_select, _ccs_assign(1))


def _opened_file(script: Script) -> Path | None:
    """Return the simulation file the script's tier prelude opened, read off its OPEN line."""
    lines = script.render().splitlines()
    for index, line in enumerate(lines):
        words = line.split(maxsplit=1)
        if words[:1] == ["OPEN"]:
            if len(words) == 2:
                return Path(words[1].strip())
            if index + 1 < len(lines) and lines[index + 1].strip():
                return Path(lines[index + 1].strip())
    return None


_MARKS_FILE = "source_marks.txt"


_MARKS_COUNT = "source_marks_count.txt"


def _reimport_with_marks(obj_name: str, edge_type: str) -> Build:
    """Open nothing new but the source's OBJ, and write the points file of the source's marks.

    The tier prelude opened the source probe's ``saved.fsm``; its marked edges
    (read here, at build time, from that file) become the points file, and the
    OBJ the source exported beside it is imported into a new simulation in
    metres. The count is kept in the probe folder for the judge.
    """

    def build(script: Script, workdir: Path) -> None:
        source = _opened_file(script)
        midpoints: tuple[tuple[float, float, float], ...] = ()
        if source is not None and source.is_file():
            try:
                midpoints = trailing_edge_midpoints(source)
            except (OSError, ValueError):
                midpoints = ()
        _textio.write_text(workdir / _MARKS_FILE, render_wake_edge_node_file(midpoints))
        _textio.write_text(workdir / _MARKS_COUNT, f"{len(midpoints)}\n")
        obj = (source.parent if source is not None else workdir) / obj_name
        script.emit("NEW_SIMULATION")
        script.emit("IMPORT", "METER", "OBJ", obj, clear=True)
        script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")

    return build


def _import_marks(edge_type: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        token = wake_edge_import_token(script, "METER")
        script.emit("IMPORT_WAKE_EDGES_FROM_FILE", edge_type, 0.0001, token, workdir / _MARKS_FILE)

    return build


def _marks_reproduced(artifacts: ProbeArtifacts) -> bool | None:
    """Judge the points-file route: the saved marks number what the source marked."""
    count_file = artifacts.workdir / _MARKS_COUNT
    if not count_file.is_file():
        return None
    expected = int(count_file.read_text(encoding="utf-8").strip() or 0)
    found = edge_count(artifacts.workdir / "saved.fsm")
    if not expected or found is None:
        return None
    return True if found == expected else None


def _marks_read(artifacts: ProbeArtifacts) -> str:
    count_file = artifacts.workdir / _MARKS_COUNT
    expected = count_file.read_text(encoding="utf-8").strip() if count_file.is_file() else "?"
    return f"source marked {expected}; " + _edges_read("saved.fsm")(artifacts)


def _write_obj(triangles: np.ndarray, path: Path, scale: float = 1.0) -> Path:
    """Write triangles as an OBJ, vertices shared, faces in the given order."""
    index: dict[tuple[float, ...], int] = {}
    faces = []
    for triangle in triangles:
        face = []
        for corner in triangle:
            key = tuple(round(float(c) * scale, 9) for c in corner)
            face.append(index.setdefault(key, len(index) + 1))
        faces.append(face)
    body = ["# pyflightstream synthetic probe body"]
    body += [f"v {x:.9g} {y:.9g} {z:.9g}" for (x, y, z) in index]
    body += ["f " + " ".join(str(i) for i in face) for face in faces]
    _textio.write_text(path, "\n".join(body) + "\n")
    return path


def _obj_source(name: str, *, scale: float = 1.0, reverse: bool = False) -> Build:
    def build(script: Script, workdir: Path) -> None:
        triangles = wing_triangles(_WING)
        if reverse:
            triangles = triangles[::-1]
        units = "MILLIMETER" if scale != 1.0 else "METER"
        path = _write_obj(triangles, workdir / name, scale)
        script.emit("NEW_SIMULATION")
        script.emit("IMPORT", units, "OBJ", path, clear=True)

    return build


def _face_order_read(source: str, exported: str) -> Reading:
    """Compare the face sequence of an exported OBJ with its source, as corner sets."""

    def faces(path: Path) -> list[frozenset[tuple[float, ...]]] | None:
        if not path.is_file():
            return None
        vertices: list[tuple[float, ...]] = []
        out: list[frozenset[tuple[float, ...]]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            words = line.split()
            if words[:1] == ["v"]:
                vertices.append(tuple(round(float(w), 5) for w in words[1:4]))
            elif words[:1] == ["f"]:
                out.append(frozenset(vertices[int(w.split("/")[0]) - 1] for w in words[1:]))
        return out

    def read(artifacts: ProbeArtifacts) -> str:
        a, b = faces(artifacts.workdir / source), faces(artifacts.workdir / exported)
        if a is None or b is None:
            return f"{source} or {exported} absent"
        same = sum(1 for x, y in zip(a, b, strict=False) if x == y)
        first = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), None)
        return (
            f"source {len(a)} faces, export {len(b)} faces, {same} at the same position, "
            f"first difference at face {first}, same set {set(a) == set(b)}"
        )

    return read


def _groups_read(name: str) -> Reading:
    def read(artifacts: ProbeArtifacts) -> str:
        path = artifacts.workdir / name
        if not path.is_file():
            return f"{name} absent; " + _state(artifacts.workdir / "saved.fsm")
        groups = [
            line.strip()
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line[:2] in ("o ", "g ")
        ]
        return f"{name} groups {groups[:12]}; " + _state(artifacts.workdir / "saved.fsm")

    return read


def _emit_export_all(name: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, workdir / name)

    return build


def _export_format(fmt: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("EXPORT_SURFACE_MESH", fmt, 1, workdir / f"wing.{fmt.lower()}")

    return build
