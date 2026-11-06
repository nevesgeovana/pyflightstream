"""Rewrite one or more named IGES files as one IGES of B-spline faces, names kept (PFS-2199).

Each file is imported into one OpenCASCADE model (optional ``gmsh`` extra), every face is
converted to a NURBS surface, and one IGES is written holding only B-spline surfaces and curves,
the form the solver's CAD import reads. Each component keeps its name: its faces sit on one level
and one 406 form 15 NAME names that level, so the solver and
:func:`pyflightstream.workspace._iges_names.read_iges_names` read the same components back. The
first file's length unit is kept and every other file is scaled to it. A record
``<out>.json`` beside the output lists the faces of each component, the digest of every source,
the surface types before and after, and the read-back.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.workspace._gmsh import IMPORT_UNIT, import_iges, import_named, session
from pyflightstream.workspace._iges_names import (
    flag_curves_on_surfaces,
    name_faces,
    read_iges_names,
)

__all__ = ["convert_iges"]

_PURPOSE = "Converting an IGES file to B-spline faces"


def _types(gmsh: Any, faces: Sequence[int]) -> dict[str, int]:
    return dict(Counter(gmsh.model.getType(2, t) for t in faces))


def _centres(gmsh: Any, faces: Sequence[int]) -> list[tuple[float, ...]]:
    return [tuple(gmsh.model.occ.getCenterOfMass(2, t)) for t in faces]


def convert_iges(sources: Sequence[str | Path], out: str | Path) -> dict[str, Any]:
    """Write the faces of ``sources`` as one IGES of NURBS faces with their component names.

    Parameters
    ----------
    sources : sequence of str or Path
        IGES files, read only; their faces are named by the NAME of their level.
    out : str or Path
        The IGES to write; ``<out>.json`` is written beside it.

    Returns
    -------
    dict
        The record written to ``<out>.json``.

    Raises
    ------
    MissingExtraError
        gmsh is not installed (``pip install "pyflightstream[gmsh]"``).
    InputArtifactError
        A source cannot be named face by face, or the written file does not read back with the
        same components; nothing was written.
    """
    target = Path(out)
    if target.suffix.lower() not in (".igs", ".iges"):
        raise InputArtifactError(
            f"{target}: the output of iges-convert is an IGES file (.igs or .iges). Nothing was "
            "written.",
            kind="geometry",
        )
    with session(_PURPOSE) as gmsh:
        model = import_named(gmsh, sources)
        before = _types(gmsh, model.faces)
        gmsh.model.occ.convertToNURBS([(2, t) for t in model.faces])
        gmsh.model.occ.synchronize()
        after = _types(gmsh, model.faces)
        centres = _centres(gmsh, model.faces)
        size = _diagonal(gmsh)
        # The import is in millimetres; the model now holds the first file's unit, which the
        # writer labels as millimetres, so the unit flag is set back on the named copy below.
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "faces.igs"
            gmsh.write(str(raw))
            gmsh.clear()
            back = _read_back(gmsh, raw, len(model.faces))
            distance = max(
                (
                    max(abs(a - b) for a, b in zip(x, y, strict=True))
                    for x, y in zip(centres, back, strict=True)
                ),
                default=0.0,
            )
            # The writer rounds coordinates; a face read back out of order moves by a face.
            tolerance = 1e-4 * max(size, 1.0)
            if len(back) != len(model.faces) or distance > tolerance:
                raise InputArtifactError(
                    f"{target}: the written faces do not read back in the order they were "
                    f"written (largest centre distance {distance:g} {model.unit}), so no face "
                    "can carry its name. Nothing was written.",
                    kind="geometry",
                )
            named = Path(folder) / "named.igs"
            name_faces(raw, named, model.names, unit=model.unit)
            # The solver's CAD import reads the parameter-space flags the writer leaves wrong.
            staged = flag_curves_on_surfaces(named, Path(folder) / "flagged.igs")
            again = read_iges_names(staged)
            if list(again.faces) != model.names:
                raise InputArtifactError(
                    f"{target}: the named file reads back other components than were written. "
                    "Nothing was written.",
                    kind="geometry",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            _textio.write_bytes(target, staged.read_bytes())
    readback = read_iges_names(target)
    record = {
        "output": target.name,
        "sha256": file_sha256(target),
        "unit": model.unit,
        "sources": model.sources,
        "notes": model.notes,
        "faces": len(model.faces),
        "components": readback.components,
        "surface_types_before": before,
        "surface_types_after": after,
        "readback": {
            "components": readback.components,
            "unit": readback.unit,
            "same_components": list(readback.faces) == model.names,
            "largest_centre_distance": distance,
        },
        "import_unit": IMPORT_UNIT,
        "metres_per_unit": float(METRES_PER_UNIT[model.unit]),
    }
    _textio.write_text(Path(str(target) + ".json"), json.dumps(record, indent=2) + "\n")
    return record


def _diagonal(gmsh: Any) -> float:
    box = gmsh.model.getBoundingBox(-1, -1)
    return float(sum((box[i + 3] - box[i]) ** 2 for i in range(3)) ** 0.5)


def _read_back(gmsh: Any, path: Path, expected: int) -> list[tuple[float, ...]]:
    """Import a written IGES into an empty model and return the centre of each face."""
    faces = import_iges(gmsh, path)
    gmsh.model.occ.synchronize()
    centres = _centres(gmsh, faces) if len(faces) == expected else []
    gmsh.clear()
    return centres
