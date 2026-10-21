"""Reading a geometry instruction file and the files it names (FR-470).

Pipeline role: the workspace row. :func:`read_geometry_instruction` reads one
``<name>.geometry.toml`` into the model of
:mod:`pyflightstream.cases._geometry_instruction`, refusing before any solver
starts and naming the file and the key; :func:`checked_trailing_edge_points`
reads the points file of a ``[trailing_edges]`` file route and checks it
against the source mesh, the rule a sidecar's file route meets at binding;
:func:`refuse_moved_nodes` holds the node operations to the mesh they were
written for.
"""

from __future__ import annotations

from pathlib import Path, PurePath
from typing import Any

from pydantic import ValidationError

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError
from pyflightstream.cases._ccs import CCS_FORMATS
from pyflightstream.cases._geometry_instruction import (
    GEOMETRY_PAGE,
    INSTRUCTION_SUFFIX,
    GeometryInstruction,
    source_names,
)
from pyflightstream.workspace.sidecars import load_toml, obj_boundary_names, read_trailing_edges
from pyflightstream.workspace.wake_edges import (
    matched_trailing_edge_points,
    read_trailing_edge_points,
)

__all__ = [
    "SOURCE_TABLES",
    "checked_trailing_edge_points",
    "instruction_stem",
    "read_geometry_instruction",
    "refuse_foreign_source_names",
    "refuse_moved_nodes",
]

#: The four source tables; an instruction states exactly one.
SOURCE_TABLES = ("ccs", "cad", "create", "mesh")

#: Every top-level key the file reads.
_TOP_KEYS = frozenset(
    {
        "name",
        "fs_build",
        "outputs",
        "boundaries",
        "operations",
        "trailing_edges",
        "sweep",
        *SOURCE_TABLES,
    }
)

_DEFAULT_OUTPUTS = {"ccs": ("fsm",), "cad": ("fsm",), "create": ("fsm",), "mesh": ("obj",)}
_SOURCE_SUFFIXES = {
    "ccs": tuple(sorted(CCS_FORMATS)),
    "cad": (".igs", ".iges"),
    "mesh": (".obj", ".stl"),
}
_STEP = (".step", ".stp")

#: The page every refusal of the file points at.
_PAGE = GEOMETRY_PAGE


def instruction_stem(path: Path) -> str:
    """Return ``wing`` for ``wing.geometry.toml``."""
    return path.name[: -len(INSTRUCTION_SUFFIX)]


def _refuse(path: Path, text: str) -> InputArtifactError:
    return InputArtifactError(f"{path}: {text} ({_PAGE}).", kind="geometry")


def _source_table(path: Path, data: dict[str, Any]) -> str:
    stated = [table for table in SOURCE_TABLES if table in data]
    if len(stated) != 1:
        found = ", ".join(f"[{table}]" for table in stated) or "none"
        raise _refuse(
            path,
            f"an instruction states exactly one source table, [ccs], [cad], [create] or "
            f"[mesh]; it states {found}",
        )
    return stated[0]


def _a_file_in_the_folder(path: Path, kind: str, written: object, key: str = "file") -> str:
    """Refuse a source file written as a path, absent from the folder, or of another kind."""
    if not isinstance(written, str) or not written.strip():
        raise _refuse(
            path, f'[{kind}] {key} = {written!r}; write the file name, such as {key} = "wing.csv"'
        )
    name = written.strip()
    if PurePath(name).name != name or "/" in name or "\\" in name:
        raise _refuse(
            path,
            f"[{kind}] {key} = {name!r} is a path; a source lies in the instruction's folder "
            "and is named by its file name alone",
        )
    suffix = PurePath(name).suffix.lower()
    if suffix in _STEP:
        raise _refuse(
            path,
            f"[{kind}] names the STEP file {name}, and STEP is refused: native STEP controls "
            "produced empty geometry. Use the IGES route ([cad] with an .igs file)",
        )
    allowed = _SOURCE_SUFFIXES.get(kind)
    if allowed is not None and suffix not in allowed:
        raise _refuse(
            path, f"[{kind}] {key} = {name!r}; a [{kind}] source is a {' or '.join(allowed)} file"
        )
    if not (path.parent / name).is_file():
        raise _refuse(
            path, f"[{kind}] {key} = {name!r}, and the folder {path.parent} holds no such file"
        )
    return name


def _source_fields(path: Path, kind: str, table: object) -> dict[str, Any]:
    """Split one source table into the fields of the instruction model."""
    if not isinstance(table, dict):
        raise _refuse(path, f"[{kind}] is written as a {type(table).__name__}; write it as a table")
    table = dict(table)
    if kind == "ccs":
        file = _a_file_in_the_folder(path, kind, table.pop("file", None))
        units = table.pop("units", None)
        shedding = table.pop("shedding", None)
        return {"ccs": {"file": file, "units": units, "shedding": shedding, "options": table}}
    if kind == "cad":
        file = _a_file_in_the_folder(path, kind, table.pop("file", None))
        units = table.pop("units", "FILE")
        operations = table.pop("operations", [])
        return {"cad": {"file": file, "units": units, "operations": operations, "options": table}}
    if kind == "mesh":
        table["file"] = _a_file_in_the_folder(path, kind, table.get("file"))
        return {"mesh": table}
    sections = table.get("sections", []) or []
    if not isinstance(sections, list):
        raise _refuse(
            path,
            f"[create] sections is written as a {type(sections).__name__}; "
            "write it as an array of tables, [[create.sections]]",
        )
    for section in sections:
        if isinstance(section, dict):
            section["file"] = _a_file_in_the_folder(path, "create.sections", section.get("file"))
    return {"create": table}


def _where(loc: tuple[int | str, ...]) -> str:
    parts = [str(part) for part in loc if part not in ("options",)]
    return ".".join(parts) or "the file"


def read_geometry_instruction(path: str | Path) -> GeometryInstruction:
    """Read and check one ``<name>.geometry.toml`` (FR-470).

    Parameters
    ----------
    path : str or Path
        The instruction file, in a geometry folder.

    Returns
    -------
    GeometryInstruction
        The instruction, every rule of the file held.

    Raises
    ------
    InputArtifactError
        Every refusal of FR-1101, naming the file, the key and what to write.
    """
    path = Path(path)
    if not path.name.endswith(INSTRUCTION_SUFFIX):
        raise _refuse(path, f"an instruction file is named <name>{INSTRUCTION_SUFFIX}")
    data = load_toml(path, "geometry instruction")
    foreign = sorted(set(data) - _TOP_KEYS)
    if foreign:
        raise _refuse(
            path,
            f"the file does not read {', '.join(foreign)}; it reads {', '.join(sorted(_TOP_KEYS))}",
        )
    kind = _source_table(path, data)
    for key in ("outputs", "boundaries", "operations"):
        if key in data and not isinstance(data[key], list):
            raise _refuse(
                path,
                f"{key} = {data[key]!r} is written as a {type(data[key]).__name__}; "
                f"write {key} as a list"
                + (", one [[operations]] table per operation" if key == "operations" else ""),
            )
    fields: dict[str, Any] = {
        "name": data.get("name", instruction_stem(path)),
        "fs_build": data.get("fs_build"),
        "outputs": tuple(data.get("outputs", _DEFAULT_OUTPUTS[kind])),
        "boundaries": tuple(data.get("boundaries", ())),
        "kind": kind,
        "operations": tuple(data.get("operations", ())),
        "sweep": data.get("sweep"),
        **_source_fields(path, kind, data[kind]),
    }
    if "trailing_edges" in data:
        table = data["trailing_edges"]
        if not isinstance(table, dict):
            raise _refuse(path, "[trailing_edges] is not a table")
        fields["trailing_edges"] = read_trailing_edges(path, table)
    try:
        return GeometryInstruction.model_validate(fields)
    except ValidationError as error:
        problems = "; ".join(
            f"{_where(tuple(item['loc']))}: {str(item['msg']).removeprefix('Value error, ')}"
            for item in error.errors()
        )
        raise _refuse(path, f"the instruction is refused: {problems}") from error


def checked_trailing_edge_points(
    instruction: GeometryInstruction, path: Path
) -> tuple[tuple[float, float, float], ...]:
    """Return the points of a ``[trailing_edges]`` file route, in metres, checked.

    Empty when the instruction marks its edges another way. The points name
    edges of the source mesh as the file holds it, so an operation that moves
    or adds faces before the marking is refused, as a sidecar's file route is.
    """
    marking = instruction.trailing_edges
    if marking is None or marking.route != "file":
        return ()
    if instruction.mesh is None:
        raise _refuse(
            path,
            "[trailing_edges] file = ... reads points on the edges of a raw mesh; beside a "
            '[cad] or [create] source write detect = "auto"',
        )
    moving = [
        f"operation {position} ({operation.op})"
        for position, operation in enumerate(instruction.operations, start=1)
        if operation.op not in ("rename", "fill_holes")
    ]
    if moving:
        raise _refuse(
            path,
            f"[trailing_edges] marks edges by a points file, and {', '.join(moving)} moves, "
            "copies or changes faces of the mesh before the marking, so the points would mark "
            'nothing; write detect = "auto", or apply the operation to the mesh file itself',
        )
    assert marking.points_file is not None  # the file route's reader always sets it
    points_file = Path(marking.points_file)
    read = read_trailing_edge_points(points_file)
    points = matched_trailing_edge_points(
        read.points,
        points_unit=read.unit,
        mesh=path.parent / instruction.mesh.file,
        mesh_unit=instruction.mesh.units,
        simulation_unit="METER",
        tolerance=marking.tolerance,
        source=f"the [trailing_edges] file {points_file.name} of {path.name}",
        lines=read.lines,
    )
    return tuple((float(x), float(y), float(z)) for x, y, z in points.tolist())


def refuse_moved_nodes(instruction: GeometryInstruction, path: Path) -> None:
    """Refuse node operations whose mesh no longer hashes as pinned (FR-1129)."""
    for position, operation in enumerate(instruction.operations, start=1):
        if operation.op != "transform_nodes":
            continue
        assert instruction.mesh is not None  # the model refuses node operations elsewhere
        mesh = path.parent / instruction.mesh.file
        digest = file_sha256(mesh)
        if digest != operation.mesh_sha256:
            raise _refuse(
                path,
                f"operation {position} (transform_nodes) is pinned to the mesh sha256 "
                f"{operation.mesh_sha256}, and {mesh.name} now hashes {digest}: a node number is "
                "a fact about one file. Check the node numbers against the new mesh, then write "
                "its sha256",
            )


def refuse_foreign_source_names(instruction: GeometryInstruction, path: Path) -> None:
    """Refuse an OBJ source whose groups are not the names the operations start from."""
    if instruction.mesh is None or not instruction.mesh.file.lower().endswith(".obj"):
        return
    mesh = path.parent / instruction.mesh.file
    found = obj_boundary_names(mesh)
    wanted = tuple(source_names(instruction))
    if found != wanted:
        raise _refuse(
            path,
            f"{mesh.name} carries the surfaces {', '.join(found) or 'none'}, and boundaries with "
            f"the operations undone start from {', '.join(wanted)}; state the names the "
            "operations leave, starting from the file's own",
        )
