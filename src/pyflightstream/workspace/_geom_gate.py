"""The reader profile gate: measure a written IGES file against what the solver reader accepts.

Pure text work on the file, with no kernel: :func:`check_profile` reads the entities back and
reports one finding per defect. A solid entity is refused with an error, because the package
builds surfaces only. Every other defect is a ``fail`` finding that names its check and entity,
so a loop of parameter sets keeps its report. A degree beyond the observed ones, which no source
limits yet, is a ``warn``. The profile itself is
:mod:`pyflightstream.geometry._iges_profile`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyflightstream._errors import InputArtifactError
from pyflightstream.geometry._iges_profile import (
    OBSERVED,
    SOLID_ENTITIES,
    GateFinding,
    ReaderProfile,
    surface_findings,
)
from pyflightstream.workspace._iges_write import read_iges

__all__ = ["GateFinding", "GateReport", "check_profile"]


@dataclass(frozen=True)
class GateReport:
    """The findings of one file and how many surfaces it holds."""

    path: Path
    surfaces: int
    findings: tuple[GateFinding, ...]

    @property
    def failed(self) -> tuple[GateFinding, ...]:
        """Return the findings that fail the gate."""
        return tuple(f for f in self.findings if f.severity == "fail")

    @property
    def passed(self) -> bool:
        """Return whether no finding fails the gate; warnings do not."""
        return not self.failed


def _outer_sides(entity: dict[str, Any], by_id: dict[int, dict[str, Any]]) -> int | None:
    values = entity["parameters"]
    outer = by_id.get(int(values[4])) if len(values) > 4 and int(values[4]) else None
    if outer is None or outer["type"] != 142:
        return None
    for pointer in (outer["parameters"][4], outer["parameters"][3]):
        curve = by_id.get(int(pointer)) if int(pointer) else None
        if curve is not None and curve["type"] == 102:
            return int(curve["parameters"][1])
    return None


def face_findings(
    entity: dict[str, Any], by_id: dict[int, dict[str, Any]], profile: ReaderProfile
) -> list[GateFinding]:
    values = entity["parameters"]
    ident = entity["id"]
    found: list[GateFinding] = []
    inner = int(values[3])
    named = False
    surface = by_id.get(int(values[1]))
    if surface is not None and surface["type"] != 128:
        found.append(
            GateFinding(
                "profile.entity",
                "warn",
                ident,
                f"the surface is entity {surface['type']}; only 128 was observed read and no "
                "source states the rest",
            )
        )
    if len(values) >= 8 + inner:
        prop = by_id.get(int(values[7 + inner]))
        named = prop is not None and prop["type"] == 406 and int(prop["d2"][4]) == 15
    if not named:
        found.append(GateFinding("profile.name", "fail", ident, "no 406 form 15 NAME on the face"))
    sides = _outer_sides(entity, by_id)
    if sides in profile.bad_side_counts:
        found.append(
            GateFinding("profile.sides", "fail", ident, f"outer boundary has {sides} curves")
        )
    return found


def check_profile(path: str | Path, profile: ReaderProfile = OBSERVED) -> GateReport:
    """Measure the IGES file at ``path`` against ``profile``.

    Raises :class:`InputArtifactError` for a solid entity (surfaces only) and for a file that
    cannot be read as IGES. Every other defect is a finding of the returned report, and a file with
    no trimmed surface fails: it holds nothing the gate could have measured.
    """
    try:
        document = read_iges(path)
    except (UnicodeDecodeError, ValueError, IndexError) as error:
        raise InputArtifactError(
            f"{path}: this cannot be read as an IGES file ({error}). Write the file again and "
            "run again. Nothing was written.",
            kind="geometry",
        ) from error
    entities = document["entities"]
    solids = sorted({e["type"] for e in entities if e["type"] in SOLID_ENTITIES})
    if solids:
        raise InputArtifactError(
            f"{path}: the file holds solid entities {solids}; this package builds surfaces only. "
            "Export surfaces from the CAD system and run again. Nothing was written.",
            kind="geometry",
        )
    by_id = {e["id"]: e for e in entities}
    findings: list[GateFinding] = []
    faces = [e for e in entities if e["type"] == 144]
    if not faces:
        findings.append(GateFinding("profile.surfaces", "fail", None, "no trimmed surface (144)"))
    trimmed = {int(e["parameters"][1]) for e in faces}
    for entity in entities:
        if entity["type"] == 128:
            findings += surface_findings(entity, profile)
            if entity["id"] not in trimmed:
                findings.append(
                    GateFinding("profile.name", "fail", entity["id"], "a surface no face names")
                )
    for entity in faces:
        findings += face_findings(entity, by_id, profile)
    return GateReport(path=Path(path), surfaces=len(faces), findings=tuple(findings))
