"""Selecting named components of an imported IGES model (``iges-grid --component``).

Pipeline role: the selection step of iges-grid. A name given on the command line is resolved
against the component names the IGES files carry (the NAME of each level, the 406 index): an
exact name wins; otherwise a name that differs only in case or in surrounding blanks selects
the one component it matches. A name no component carries, or one that matches two components
that differ only in case, is refused with the names found, so a mistyped name never grids
nothing or the wrong part. The faces of the components that are not selected leave the
geometry model before it is healed and joined, so they take no part in the junctions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pyflightstream._errors import InputValueError
from pyflightstream.workspace._gmsh import NamedModel

__all__ = ["keep_components", "resolve_components"]


def resolve_components(found: Sequence[str], requested: Sequence[str]) -> list[str]:
    """Return the components ``requested`` names, in the order of ``found``, or refuse.

    Raises
    ------
    InputValueError
        ``requested`` is empty, a name matches no component, or a name matches more than one
        component that differs from it only in case or surrounding blanks.
    """
    if not requested:
        raise InputValueError(
            "component: at least one component name required. Nothing was written."
        )
    listing = ", ".join(repr(name) for name in found)
    chosen: set[str] = set()
    for name in requested:
        if name in found:
            chosen.add(name)
            continue
        loose = [f for f in found if f.strip().casefold() == name.strip().casefold()]
        if not loose:
            raise InputValueError(
                f"component {name!r}: no component of the IGES files has this name; found: "
                f"{listing}. Nothing was written."
            )
        if len(loose) > 1:
            raise InputValueError(
                f"component {name!r}: ambiguous, it matches "
                f"{', '.join(repr(m) for m in loose)}; give the exact name. Nothing was written."
            )
        chosen.add(loose[0])
    return [name for name in found if name in chosen]


def keep_components(gmsh: Any, model: NamedModel, names: Sequence[str]) -> NamedModel:
    """Remove the faces of every component not in ``names`` from the gmsh model; return the rest."""
    keep = set(names)
    dropped = [t for t, n in zip(model.faces, model.names, strict=True) if n not in keep]
    if dropped:
        gmsh.model.occ.remove([(2, t) for t in dropped], recursive=True)
        gmsh.model.occ.synchronize()
    pairs = [(t, n) for t, n in zip(model.faces, model.names, strict=True) if n in keep]
    return NamedModel(
        unit=model.unit,
        faces=[t for t, _ in pairs],
        names=[n for _, n in pairs],
        sources=model.sources,
        notes=[*model.notes, f"selected components: {', '.join(names)}"],
    )
