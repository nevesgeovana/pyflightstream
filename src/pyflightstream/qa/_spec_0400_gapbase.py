"""The base of the 0.40.0 command-gap instruments: readers of saved states and exports.

Pipeline role: the lowest layer under ``pyflightstream.qa._spec_0400_gapkit``, which
imports every name here back. The callable aliases, the probe wing and the readers of
saved simulations, OBJ exports, numeric exports and CCS files live here so the
instruments above can share them without a cycle.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from pathlib import Path

import numpy as np

from pyflightstream._fsm import (
    boundary_names,
    mesh_face_counts,
    saved_length_unit,
)
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.geometry import WingSpec
from pyflightstream.qa.probes import ProbeArtifacts
from pyflightstream.script import Script

Build = Callable[[Script, Path], None]


Judge = Callable[[ProbeArtifacts], "bool | None"]


Reading = Callable[[ProbeArtifacts], str]


#: The saved states the harness brackets a target with (``ProbeSpec.save_state``).
_BEFORE, _AFTER = "state_before.fsm", "state_after.fsm"


#: Solved probes march or iterate; a cold licence checkout plus a short solve
#: fits in three minutes on the licensed machine.
_SOLVE_TIMEOUT_S = 180.0


def _faces(path: Path) -> tuple[int, tuple[int, ...] | None] | None:
    if not path.is_file():
        return None
    try:
        return mesh_face_counts(path)
    except (OSError, ValueError, QaEvidenceError):
        return None


def _names(path: Path) -> tuple[str, ...] | None:
    if not path.is_file():
        return None
    try:
        return boundary_names(path)
    except (OSError, ValueError, QaEvidenceError):
        return None


def _state(path: Path) -> str:
    """Read a saved simulation as names with their face counts, or say it is absent."""
    if not path.is_file():
        return f"{path.name} absent"
    names = _names(path)
    faces = _faces(path)
    per = faces[1] if faces else None
    if names and per and len(per) == len(names):
        listed = ", ".join(f"{n}:{c}" for n, c in zip(names, per, strict=True))
    else:
        listed = ", ".join(names or ())
    total = faces[0] if faces else "?"
    return f"{path.name} {len(names or ())} boundaries [{listed}] {total} faces"


def _obj(path: Path) -> tuple[list[tuple[float, float, float]], int] | None:
    """Read an exported OBJ as its vertices and its face count, or None."""
    if not path.is_file():
        return None
    vertices: list[tuple[float, float, float]] = []
    faces = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            words = line.partition("#")[0].split()
            if words[:1] == ["v"] and len(words) >= 4:
                vertices.append((float(words[1]), float(words[2]), float(words[3])))
            elif words[:1] == ["f"]:
                faces += 1
    except ValueError:
        return None
    return vertices, faces


def obj_summary(path: Path) -> str:
    """Name an OBJ export's size, bounding box and centroid azimuth about X."""
    read = _obj(path)
    if read is None or not read[0]:
        return f"{path.name} absent"
    vertices, faces = read
    array = np.asarray(vertices)
    low, high = array.min(axis=0), array.max(axis=0)
    centre = array.mean(axis=0)
    azimuth = math.degrees(math.atan2(float(centre[2]), float(centre[1])))
    box = ",".join(f"{a:.3f}..{b:.3f}" for a, b in zip(low, high, strict=True))
    return (
        f"{path.name} {len(vertices)} vertices {faces} faces box[{box}] "
        f"centroid({centre[0]:.3f},{centre[1]:.3f},{centre[2]:.3f}) azimuth_x {azimuth:.1f} deg"
    )


_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")


def _rows(path: Path) -> list[list[float]]:
    """Return the all-numeric rows of a text export, split on spaces, commas or semicolons."""
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        tokens = [t for t in re.split(r"[\s,;]+", line.strip()) if t]
        if tokens and all(_NUMBER.match(t) for t in tokens):
            rows.append([float(t) for t in tokens])
    return rows


def _text_head(path: Path, lines: int = 3) -> str:
    if not path.is_file():
        return f"{path.name} absent"
    head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:lines]
    return " | ".join(line.strip()[:80] for line in head)


def _export_summary(path: Path) -> str:
    """Summarise a numeric export: bytes, numeric rows, widths, column ranges, header."""
    if not path.is_file():
        return f"{path.name} absent"
    rows = _rows(path)
    widths = sorted({len(r) for r in rows})
    ranges = ""
    if rows:
        width = min(len(r) for r in rows)
        cols = np.asarray([r[:width] for r in rows])
        ranges = " ranges " + ",".join(
            f"{a:.3g}..{b:.3g}" for a, b in zip(cols.min(axis=0), cols.max(axis=0), strict=True)
        )
    return (
        f"{path.name} {path.stat().st_size} bytes, {len(rows)} numeric rows, widths {widths}"
        f"{ranges}; head: {_text_head(path)}"
    )


def _ccs_sections(path: Path) -> list[list[tuple[float, ...]]]:
    """Return the cross sections of a CCS text file as point lists."""
    if not path.is_file():
        return []
    sections = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().lower().startswith("crosssection"):
            values = [float(t) for t in line.split(";")[1:] if _NUMBER.match(t.strip())]
            sections.append([tuple(values[i : i + 3]) for i in range(0, len(values) - 2, 3)])
    return sections


def _ccs_summary(path: Path) -> str:
    sections = _ccs_sections(path)
    if not path.is_file():
        return f"{path.name} absent"
    parts = []
    for points in sections:
        array = np.asarray(points)
        if array.size:
            low, high = array.min(axis=0), array.max(axis=0)
            parts.append(
                f"{len(points)}pts x {low[0]:.3f}..{high[0]:.3f} y {low[1]:.3f}..{high[1]:.3f} "
                f"z {low[2]:.3f}..{high[2]:.3f} first ({array[0][0]:.3f},{array[0][2]:.3f})"
            )
    return f"{path.name} {len(sections)} sections [{'; '.join(parts)}]; head: {_text_head(path, 2)}"


#: The probe wing: chord 1 m, span 4 m centred on y = 0, coarse.
_WING = WingSpec(naca="0012", chord_m=1.0, span_m=4.0, n_chord=8, n_span=8)


def _states_read(*extra: str) -> Reading:
    """Read the bracketing states, then each named extra file of the workdir."""

    def read(artifacts: ProbeArtifacts) -> str:
        unit = None
        if (artifacts.workdir / _AFTER).is_file():
            unit = saved_length_unit(artifacts.workdir / _AFTER)
        parts = [_state(artifacts.workdir / _BEFORE), _state(artifacts.workdir / _AFTER)]
        parts.append(f"length unit {unit}")
        for name in extra:
            path = artifacts.workdir / name
            if name.endswith(".obj"):
                parts.append(obj_summary(path))
            elif name.endswith(".fsm"):
                parts.append(_state(path))
            elif name.endswith(".ccs"):
                parts.append(_ccs_summary(path))
            else:
                parts.append(_export_summary(path))
        return "; ".join(parts)

    return read
