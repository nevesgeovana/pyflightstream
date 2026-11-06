"""The surface export probe of 0.56.0 (FR-3741).

Pipeline role: register a controlled probe on a synthetic mesh, so the geometry build's
evidence gate (FR-1110) can rest on a measured effect rather than a log line.

EXPORT_SURFACE_MESH (PFS-2187.04). The blunt box of the 0.46.0 marking probes, two boundaries
(Body and Rim) of eight vertices and twelve triangles, imported in metres; the target exports
every boundary (``-1``) to an OBJ in the probe folder. The effect is the file the build reads
back: it is True when the OBJ holds the twelve faces over exactly the eight source vertices,
False when the file is missing or holds another mesh (a command that runs and writes nothing,
or writes something else, is broken), never guessed.
"""

from __future__ import annotations

import json
from pathlib import Path

from pyflightstream.qa._spec_0460_marking import _POINTS, _geometry
from pyflightstream.qa._spec_kit import _spec
from pyflightstream.qa.probes import ProbeArtifacts
from pyflightstream.script import Script

__all__: list[str] = []

_EXPORT = "EXPORT_SURFACE_MESH"
_EXPORTED = "export.obj"
#: Faces of the blunt box: ten on Body and two on Rim (``_spec_0460_marking._FACES``).
_BOX_FACES = 12


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
