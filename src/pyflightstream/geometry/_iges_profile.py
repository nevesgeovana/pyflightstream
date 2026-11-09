"""The IGES profile the FlightStream reader is known to accept, and what is not known.

A plain description with no kernel and no file access: :mod:`pyflightstream.workspace._geom_gate`
measures a file against it. Every value here is either observed (a file of that shape was read by
the solver) or ``None``, which means no source states a limit and a file beyond the observed shape
is warned about, never refused. Only a solid entity is refused, because the package builds
surfaces only.

Observed: non-rational, clamped, bicubic parametric surfaces (entity 128), trimmed by an outer
boundary (entities 142 and 102), each face named by a 406 form 15 property.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "OBSERVED",
    "SOLID_ENTITIES",
    "GateFinding",
    "ReaderProfile",
    "surface_findings",
]

#: Entity types that describe a solid or a boundary representation of one: CSG primitives (150 to
#: 168), the Boolean tree (180), the manifold solid B-rep object (186), the solid instance (430)
#: and the B-rep topology entities (502 to 514). The package writes surfaces only.
SOLID_ENTITIES: tuple[int, ...] = (
    150,
    152,
    154,
    156,
    158,
    160,
    162,
    164,
    168,
    180,
    184,
    186,
    430,
    502,
    504,
    508,
    510,
    514,
)


@dataclass(frozen=True)
class ReaderProfile:
    """What the reader is known to accept.

    ``degrees`` are the degrees a file was read with. ``max_degree`` is a stated limit, ``None``
    while no source gives one: a degree outside ``degrees`` is then warned about; once a source
    sets it, a degree above it fails. ``bad_side_counts`` are the numbers of curves of an outer
    boundary that fail: a three-sided face collapses a side and is not among the observed shapes.
    """

    rational: bool = False
    clamped: bool = True
    degrees: tuple[int, ...] = (3,)
    max_degree: int | None = None
    bad_side_counts: tuple[int, ...] = (3,)


#: The profile every file is measured against.
OBSERVED = ReaderProfile()


@dataclass(frozen=True)
class GateFinding:
    """One defect: the check that found it, ``fail`` or ``warn``, the entity and the detail."""

    check: str
    severity: str
    entity: int | None
    detail: str


def _number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


def surface_findings(entity: dict[str, Any], profile: ReaderProfile) -> list[GateFinding]:
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
