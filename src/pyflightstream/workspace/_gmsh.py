"""The one guarded import of gmsh, and the named import of IGES files both IGES commands share.

gmsh ships with the optional ``gmsh`` extra; the base install never imports it. A command that
needs it calls :func:`gmsh_module`, which raises the package's one missing-extra refusal with the
install command when gmsh is absent. :func:`import_named` reads each IGES file into one
OpenCASCADE model and keeps the component of every face from the file's own names
(:mod:`pyflightstream.workspace._iges_names`), with every file scaled to the first file's unit.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.extras import missing_extra
from pyflightstream.workspace._iges_names import (
    DEFAULT_NAME_ENCODING,
    IgesNames,
    read_iges_names,
)

__all__ = [
    "NamedModel",
    "gmsh_module",
    "import_iges",
    "import_named",
    "keep_components",
    "session",
]

#: The unit an OpenCASCADE IGES import returns its coordinates in, whatever the file states.
IMPORT_UNIT = "MILLIMETER"
#: The same unit as gmsh's target unit option names it.
_OCC_IMPORT_UNIT = "MM"


def gmsh_module(purpose: str) -> ModuleType:
    """Return the gmsh module, or raise the missing-extra refusal naming ``purpose``."""
    try:
        import gmsh
    except ImportError as error:
        raise missing_extra("gmsh", package="gmsh", purpose=purpose) from error
    return gmsh


@contextlib.contextmanager
def _quiet_stdout() -> Iterator[None]:
    """Send the process's standard output to the null device for the block.

    The OpenCASCADE IGES reader prints a line of its own to the C standard output on every
    import, which gmsh's terminal option does not reach; a command that prints its record as
    JSON would otherwise print that line before it.
    """
    try:
        fd = sys.stdout.fileno()
    except (AttributeError, OSError, ValueError):
        yield
        return
    sys.stdout.flush()
    saved = os.dup(fd)
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, fd)
        yield
    finally:
        os.dup2(saved, fd)
        os.close(saved)
        os.close(null)


def import_iges(gmsh: Any, path: str | Path) -> list[int]:
    """Import one IGES file into the open model and return its faces, in import order.

    OpenCASCADE keeps the target unit of its last import in a process-wide static that an empty
    gmsh option leaves alone and ``gmsh.finalize`` does not reset, so a session that once asked
    for metres would change every later read in the process. The unit is named on every read and
    the option the caller's session held is put back.
    """
    held = gmsh.option.getString("Geometry.OCCTargetUnit")
    gmsh.option.setString("Geometry.OCCTargetUnit", _OCC_IMPORT_UNIT)
    try:
        with _quiet_stdout():
            out = gmsh.model.occ.importShapes(str(path), highestDimOnly=True)
    finally:
        gmsh.option.setString("Geometry.OCCTargetUnit", held)
    return [tag for dim, tag in out if dim == 2]


@contextlib.contextmanager
def session(purpose: str) -> Iterator[Any]:
    """Yield an initialized gmsh with its terminal output off; finalize it on the way out."""
    gmsh = gmsh_module(purpose)
    gmsh.initialize(readConfigFiles=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        yield gmsh
    finally:
        gmsh.finalize()


@dataclass
class NamedModel:
    """The faces of the imported files, each with its component, in import order."""

    unit: str
    faces: list[int]
    names: list[str]
    sources: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def components(self) -> dict[str, list[int]]:
        """Return the face tags of each component, in the order its first face was imported."""
        out: dict[str, list[int]] = {}
        for tag, name in zip(self.faces, self.names, strict=True):
            out.setdefault(name, []).append(tag)
        return out


def _unit_of(names: IgesNames) -> str:
    if names.unit is None:
        raise InputArtifactError(
            f"{names.path}: its global section names a length unit this package has no scale "
            f"for; give the file one of {', '.join(METRES_PER_UNIT)} and run again. Nothing "
            "was written.",
            kind="geometry",
        )
    return names.unit


def import_named(
    gmsh: Any, paths: Sequence[str | Path], *, name_encoding: str = DEFAULT_NAME_ENCODING
) -> NamedModel:
    """Import every IGES file into the open gmsh model and name each face from its file.

    The i-th face the import returns is the i-th face :func:`read_iges_names` lists; the counts
    are compared and a file where they differ is refused with both. Coordinates are scaled from
    the import's unit to the first file's unit, so every file of the model is in that unit.
    ``name_encoding`` is the text encoding of the NAME bytes (:func:`read_iges_names`).
    """
    if not paths:
        raise InputArtifactError(
            "name at least one IGES file. Nothing was written.", kind="geometry"
        )
    listed: list[IgesNames] = [read_iges_names(p, name_encoding=name_encoding) for p in paths]
    unit = _unit_of(listed[0])
    model = NamedModel(unit=unit, faces=[], names=[])
    for names in listed:
        _unit_of(names)
        faces = import_iges(gmsh, names.path)
        if len(faces) != len(names.faces):
            raise InputArtifactError(
                f"{names.path}: the import returned {len(faces)} faces and the file's directory "
                f"lists {len(names.faces)} surfaces, so no face can be named from it. Write the "
                "file again from its CAD system and run again. Nothing was written.",
                kind="geometry",
            )
        model.faces += faces
        model.names += list(names.faces)
        model.sources.append(
            {
                "file": names.path.name,
                "sha256": file_sha256(names.path),
                "unit": names.unit,
                "faces": len(faces),
                "components": names.components,
            }
        )
        if names.unit != unit:
            model.notes.append(f"{names.path.name} is in {names.unit} and was scaled to {unit}")
    gmsh.model.occ.synchronize()
    factor = float(METRES_PER_UNIT[IMPORT_UNIT] / METRES_PER_UNIT[unit])
    if factor != 1.0:
        gmsh.model.occ.dilate([(2, t) for t in model.faces], 0.0, 0.0, 0.0, factor, factor, factor)
        gmsh.model.occ.synchronize()
    return model


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
