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
from pyflightstream.geometry._iges_profile import OBSERVED, SOLID_ENTITIES, ReaderProfile
from pyflightstream.workspace._iges_write import read_iges

__all__ = ["GateFinding", "GateReport", "check_profile"]


@dataclass(frozen=True)
class GateFinding:
    """One defect: the check that found it, ``fail`` or ``warn``, the entity and the detail."""

    check: str
    severity: str
    entity: int | None
    detail: str


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


def _number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


def _surface_findings(entity: dict[str, Any], profile: ReaderProfile) -> list[GateFinding]:
    values = entity["parameters"]
    ident = entity["id"]
    k1, k2, m1, m2 = (int(values[i]) for i in range(1, 5))
    start = 10
    t1 = [_number(v) for v in values[start : start + k1 + m1 + 2]]
    start += k1 + m1 + 2
    t2 = [_number(v) for v in values[start : start + k2 + m2 + 2]]
    start += k2 + m2 + 2
    weights = [_number(v) for v in values[start : start + (k1 + 1) * (k2 + 1)]]
    found: list[GateFinding] = []
    if not profile.rational and max(weights) - min(weights) > 1e-12:
        found.append(GateFinding("profile.rational", "fail", ident, "weights are not all one"))
    if profile.clamped:
        for label, knots, degree in (("u", t1, m1), ("v", t2, m2)):
            ends = knots[: degree + 1] + knots[-(degree + 1) :]
            if len(set(knots[: degree + 1])) != 1 or len(set(knots[-(degree + 1) :])) != 1:
                found.append(
                    GateFinding(
                        "profile.unclamped", "fail", ident, f"{label} knots are not clamped: {ends}"
                    )
                )
    for degree in (m1, m2):
        if profile.max_degree is not None and degree > profile.max_degree:
            found.append(
                GateFinding("profile.degree", "fail", ident, f"degree {degree} above the limit")
            )
        elif degree not in profile.degrees:
            found.append(
                GateFinding(
                    "profile.degree",
                    "warn",
                    ident,
                    f"degree {degree} was not observed read and no limit is stated for it",
                )
            )
    return found


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


def _face_findings(
    entity: dict[str, Any], by_id: dict[int, dict[str, Any]], profile: ReaderProfile
) -> list[GateFinding]:
    values = entity["parameters"]
    ident = entity["id"]
    found: list[GateFinding] = []
    inner = int(values[3])
    named = False
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

    Raises :class:`InputArtifactError` for a solid entity (surfaces only). Every other defect is a
    finding of the returned report.
    """
    document = read_iges(path)
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
    for entity in entities:
        if entity["type"] == 128:
            findings += _surface_findings(entity, profile)
    for entity in faces:
        findings += _face_findings(entity, by_id, profile)
    return GateReport(path=Path(path), surfaces=len(faces), findings=tuple(findings))
