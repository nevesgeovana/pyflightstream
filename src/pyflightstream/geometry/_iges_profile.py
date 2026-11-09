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

__all__ = ["OBSERVED", "SOLID_ENTITIES", "ReaderProfile"]

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
