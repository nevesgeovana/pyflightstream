"""The converter from an in-row geometry to its instruction file (FR-1135).

Pipeline role: the workspace row. :func:`instruction_from_sidecar` reads the
sidecar of a geometry a matrix names today (a CCS file, an IGES file, a raw
mesh with scale, rename or mirror operations) and writes the
``<name>.geometry.toml`` that builds the same body: ``[ccs]`` from
``[import.ccs]``, ``[cad]`` from ``[import.cad]``, ``[mesh]`` for a raw mesh,
``[[operations]]`` from every scale, rename and mirror, ``boundaries`` as the
renames leave them, ``[trailing_edges]`` carried over, ``fs_build`` from the
command or the rows that name the geometry. It never edits the sidecar or a
matrix; translate and rotate stay in the sidecar of the built mesh and are
named.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning, warn
from pyflightstream.cases._ccs import CCS_FORMATS, CCS_SHEDDING_VARIABLE
from pyflightstream.cases._geometry_instruction import GEOMETRY_PAGE, INSTRUCTION_SUFFIX
from pyflightstream.cases.matrix import read_matrix
from pyflightstream.workspace._geometry_sidecar import toml_table as _table
from pyflightstream.workspace._geometry_sidecar import toml_value as _value
from pyflightstream.workspace._layout import matrix_files
from pyflightstream.workspace.sidecars import inventory_sidecar, load_toml

__all__ = ["GeometryConversion", "instruction_from_sidecar", "rows_for_built_geometries"]

_PAGE = GEOMETRY_PAGE
_MOVED = ("scale", "rename", "mirror")
_CAD = (".igs", ".iges")
_RAW = (".obj", ".stl")


@dataclass(frozen=True)
class GeometryConversion:
    """The instruction a converter writes, and what it tells the user."""

    path: Path
    text: str
    name: str
    built: str
    staying: tuple[str, ...]
    notes: tuple[str, ...]


def _rows_naming(root: Path, name: str) -> list[Any]:
    found = []
    for matrix in matrix_files(root):
        try:
            rows = read_matrix(matrix)
        except (OSError, ValueError, InputArtifactError) as error:
            warn(
                f"{matrix} could not be read ({error}); its rows are left out of the "
                "rows this conversion reads.",
                PyflightstreamWarning,
                stacklevel=2,
            )
            continue
        found += [row for row in rows if row.variables.get("GEOMETRY", "") == name]
    return found


def _source_table(
    geometry: Path, sidecar: Mapping[str, Any], shedding: str | None
) -> tuple[str, dict[str, Any]]:
    suffix = geometry.suffix.lower()
    imported = dict(sidecar.get("import", {}))
    if suffix in CCS_FORMATS:
        ccs = dict(imported.get("ccs", {}))
        table = {"file": geometry.name, "units": imported.get("units", "METER"), **ccs}
        if shedding is not None:
            table["shedding"] = shedding
        return "ccs", table
    if suffix in _CAD:
        return "cad", {"file": geometry.name, "units": "FILE", **dict(imported.get("cad", {}))}
    if suffix in _RAW:
        if "units" not in imported:
            raise InputArtifactError(
                f"{geometry.name}: its sidecar states no [import] units ({_PAGE})."
            )
        return "mesh", {"file": geometry.name, "units": imported["units"]}
    raise InputArtifactError(
        f"{geometry.name} is neither a CCS, an IGES nor a raw mesh; a saved simulation needs "
        f"no instruction ({_PAGE})."
    )


def _locate(geometry: str | Path, root: Path) -> Path:
    """Return the geometry file a cell names, refusing one outside a folder of its own."""
    geometries = root / "inputs" / "geometries"
    path = Path(geometry)
    if not path.is_absolute() and len(path.parts) > 1:
        # A path with folders names that file under inputs/geometries, never another
        # geometry that merely shares its basename.
        path = geometries / path
    elif not path.is_absolute():
        candidates = [geometries / path.stem / path.name, geometries / path.name]
        found = [c for c in candidates if c.is_file()]
        others = [c for c in sorted(geometries.glob(f"*/{path.name}")) if c not in found]
        if not found and len(others) > 1:
            folders = ", ".join(c.parent.name for c in others)
            raise InputArtifactError(
                f"{path.name} is in several geometry folders ({folders}); "
                f"write the folder too, as <folder>/{path.name} ({_PAGE})."
            )
        path = next(iter(found + others), candidates[0])
    elif not path.resolve().is_relative_to(geometries.resolve()):
        raise InputArtifactError(
            f"{geometry} lies outside {geometries}; an instruction is written only beside a "
            f"geometry of the workspace, in inputs/geometries/<name>/ ({_PAGE})."
        )
    if not path.is_file():
        raise InputArtifactError(f"{geometry} is not a file of {geometries} ({_PAGE}).")
    if path.parent == geometries:
        raise InputArtifactError(
            f"{path.name} lies flat in {geometries}, and an instruction lives in a geometry "
            f"folder of its own at inputs/geometries/{path.stem}/; place the geometry "
            "and its sidecars there, then run this "
            f"command again ({_PAGE})."
        )
    return path


def _what_the_rows_say(
    root: Path, name: str, build: str | None
) -> tuple[str | None, str | None, list[str]]:
    """Return the build id, the shedding direction and the notes the matrix rows give."""
    rows = _rows_naming(root, name)
    builds = sorted({row.fs_build.strip() for row in rows if row.fs_build.strip()})
    sheds = sorted(
        {
            str(row.variables[CCS_SHEDDING_VARIABLE])
            for row in rows
            if row.variables.get(CCS_SHEDDING_VARIABLE)
        }
    )
    notes: list[str] = []
    if not build and len(builds) > 1:
        notes.append(f"the rows naming {name} run on {', '.join(builds)}; fs_build is the newest")
    if len(sheds) > 1:
        notes.append(
            f"the rows shed in {', '.join(sheds)}; this instruction uses {sheds[0]}, and each "
            "other direction is an instruction of its own in a folder of its own"
        )
    return build or (builds[-1] if builds else None), sheds[0] if sheds else None, notes


def _operations(sidecar: Mapping[str, Any]) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Split the sidecar's operations: the ones that move to the instruction, the ones that stay."""
    written = sidecar.get("import", {}).get("operations", [])
    moved = [dict(op) for op in written if op.get("op") in _MOVED]
    staying = tuple(
        f"operation {position} ({op.get('op')})"
        for position, op in enumerate(written, start=1)
        if op.get("op") not in _MOVED
    )
    return moved, staying


def _quoted(text: str) -> str:
    """Return ``text`` as a TOML basic string that reads back as exactly ``text``."""
    return json.dumps(text, ensure_ascii=False)


def _instruction_text(
    sidecar_name: str,
    name: str,
    fs_build: str | None,
    source: tuple[str, dict[str, Any]],
    sidecar: Mapping[str, Any],
) -> str:
    kind, table = source
    operations, _ = _operations(sidecar)
    names = list(sidecar.get("boundaries", []))
    for op in operations:
        if op.get("op") == "rename" and op.get("surface") in names:
            names[names.index(op["surface"])] = op["to"]
    rows = [
        f"# Written by pyfs-workspace geometry from-sidecar from {sidecar_name}; check it, "
        "then build it.",
        f"name = {_quoted(name)}",
    ]
    if fs_build:
        rows.append(f"fs_build = {_quoted(fs_build)}")
    rows += [f"boundaries = {_value(names)}", "", *_table(kind, table)]
    for op in operations:
        rows += ["", "[[operations]]", *(f"{key} = {_value(value)}" for key, value in op.items())]
    if "trailing_edges" in sidecar and kind != "ccs":
        rows += ["", *_table("trailing_edges", sidecar["trailing_edges"])]
    return "\n".join(rows) + "\n"


def _write_once(target: Path, text: str) -> None:
    if target.exists():
        raise InputArtifactError(
            f"{target} exists; the converter never replaces an instruction ({_PAGE})."
        )
    others = sorted(target.parent.glob(f"*{INSTRUCTION_SUFFIX}"))
    if others:
        raise InputArtifactError(
            f"{target.parent} already holds {others[0].name}; a folder holds one "
            f"instruction ({_PAGE})."
        )
    _textio.write_text(target, text)


def instruction_from_sidecar(
    geometry: str | Path, *, root: Path, build: str | None = None, apply: bool = False
) -> GeometryConversion:
    """Write, or with ``apply`` False only render, the instruction of an in-row geometry.

    Parameters
    ----------
    geometry : str or Path
        The geometry a matrix names: a file of ``inputs/geometries/<folder>/``.
    root : Path
        The workspace root.
    build : str, optional
        The build id; else the newest the rows naming the geometry use.
    apply : bool
        Write ``<stem>.geometry.toml``; it refuses an existing one.

    Raises
    ------
    InputArtifactError
        A geometry not in its own ``inputs/geometries/<stem>/`` folder,
        a sidecar missing, or an existing instruction.
    """
    path = _locate(geometry, root)
    sidecar_path = inventory_sidecar(path)
    if not sidecar_path.is_file() and path.suffix.lower() in (*CCS_FORMATS, *_CAD):
        raise InputArtifactError(
            f"{path.name}: its sidecar {sidecar_path.name} is missing; a CCS or CAD geometry "
            f"states its import there, and defaults are never assumed ({_PAGE})."
        )
    sidecar = load_toml(sidecar_path, "geometry sidecar") if sidecar_path.is_file() else {}
    fs_build, shedding, notes = _what_the_rows_say(root, path.name, build)
    source = _source_table(path, sidecar, shedding)
    name = path.stem if source[0] != "mesh" else f"{path.stem}_ops"
    text = _instruction_text(sidecar_path.name, name, fs_build, source, sidecar)
    target = path.parent / f"{path.stem}{INSTRUCTION_SUFFIX}"
    if apply:
        _write_once(target, text)
    built = f"{name}.obj" if source[0] == "mesh" else f"{name}.fsm"
    return GeometryConversion(target, text, name, built, _operations(sidecar)[1], tuple(notes))


def conversion_lines(conversion: GeometryConversion, rows: Sequence[str] = ()) -> list[str]:
    """Return what the command prints after the instruction: the build, the cell, what stays."""
    lines = [
        f"build it with: pyfs-workspace geometry build {conversion.path.parent.name} --apply",
        f"then name {conversion.built} in the GEOMETRY cell of the rows"
        + (" " + ", ".join(rows) if rows else ""),
    ]
    if conversion.staying:
        lines.append(
            f"{', '.join(conversion.staying)} stay in the run: copy them into the sidecar "
            "of the built mesh"
        )
    return lines + [f"note: {note}" for note in conversion.notes]


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.split("|")]


def _header_and_rows(matrix: Path) -> tuple[list[str], list[list[str]]]:
    try:
        lines = matrix.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise InputArtifactError(f"{matrix} cannot be read: {error} ({GEOMETRY_PAGE}).") from error
    header_at = next(
        (i for i, line in enumerate(lines) if "|" in line and _cells(line)[0] == "POL"), None
    )
    if header_at is None:
        raise InputArtifactError(f"{matrix} holds no header line beginning POL ({GEOMETRY_PAGE}).")
    header = _cells(lines[header_at])
    candidates = [_cells(line) for line in lines[header_at + 1 :] if "|" in line]
    rows = [row for row in candidates if len(row) == len(header)]
    if len(rows) != len(candidates):
        warn(
            f"{matrix}: {len(candidates) - len(rows)} line(s) with a '|' do not have the "
            f"{len(header)} cells of the header and are left out of the rows read.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return header, rows


def rows_for_built_geometries(
    matrix: str | Path, pol: str, cells: Sequence[tuple[str | None, str]]
) -> list[str]:
    """Return one matrix row per built geometry, copied from the row ``pol``.

    Parameters
    ----------
    matrix : str or Path
        The run matrix holding the template row.
    pol : str
        The template row's ``POL``.
    cells : sequence of (configuration or None, geometry file)
        Per built geometry, the ``CONFIGURATION`` cell (None keeps the
        template's) and the ``GEOMETRY`` cell.

    Raises
    ------
    InputArtifactError
        A matrix that cannot be read, has no ``CONFIGURATION`` or ``GEOMETRY``
        column, or holds no row ``pol``.
    """
    path = Path(matrix)
    header, rows = _header_and_rows(path)
    missing = [column for column in ("CONFIGURATION", "GEOMETRY") if column not in header]
    if missing:
        raise InputArtifactError(
            f"{path} has no {' or '.join(missing)} column; "
            "rows (CLI: --rows) copies a row of a matrix "
            "at the current layout; see docs/upgrading.md for older formats and "
            f"`pyfs-workspace migrate` ({GEOMETRY_PAGE})."
        )
    template = next((row for row in rows if row[0] == str(pol).strip()), None)
    if template is None:
        raise InputArtifactError(f"{path} holds no row POL {pol} to copy ({GEOMETRY_PAGE}).")
    numbers = [int(row[0]) for row in rows if row[0].isascii() and row[0].isdigit()]
    next_pol = max(numbers, default=0) + 1
    out = []
    for offset, (configuration, geometry) in enumerate(cells):
        row = list(template)
        row[0] = str(next_pol + offset)
        if configuration is not None:
            row[header.index("CONFIGURATION")] = configuration
        row[header.index("GEOMETRY")] = geometry
        out.append(" | ".join(row))
    return out
