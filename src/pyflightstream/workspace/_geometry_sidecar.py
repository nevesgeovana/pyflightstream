"""The sidecar a build writes beside a built mesh, and what it carries over (FR-1105, FR-1111).

Pipeline role: the workspace row. A built OBJ carries a kind-qualified inventory
with its export unit, build and a named trailing-edge entry for the saved edge
points. It reaches the matrix through boundary marking and the resulting FSM.
Carried translate and rotate operations apply during that marking pass. Named
base regions and the generated entry's termination choice survive a rebuild.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream.workspace.sidecars import (
    boundaries_for_marking,
    face_count_lines,
    inventory_sidecar,
    read_boundary_declarations,
)

__all__ = [
    "CARRIED_OPERATIONS",
    "UnreadableSidecarError",
    "carried_tables",
    "sidecar_candidates",
    "sidecar_text",
    "toml_table",
    "toml_value",
    "write_mesh_sidecar",
]

#: The sidecar operations a build never applies: they stay in boundary marking.
CARRIED_OPERATIONS = ("translate", "rotate")

#: Named declarations whose retained settings belong to the next marking pass.
_CARRIED_TABLES = ("base_regions", "trailing_edges")


class UnreadableSidecarError(ValueError):
    """A sidecar that exists and cannot be read: a build must not carry nothing over it."""


def toml_value(value: Any) -> str:
    """Return one TOML value: a boolean, a number, a string, an inline table or an array."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # A basic string that reads back as exactly ``value`` (RB4-02): JSON's escapes are
        # TOML's, and DEL, which TOML also refuses raw, is escaped too.
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
    if isinstance(value, Mapping):
        return "{ " + ", ".join(f"{key} = {toml_value(item)}" for key, item in value.items()) + " }"
    return "[" + ", ".join(toml_value(item) for item in value) + "]"


def toml_table(name: str, table: Mapping[str, Any]) -> list[str]:
    """Return the lines of one TOML table, a list of tables written as ``[[name.key]]``."""
    rows = [f"[{name}]"]
    nested: list[str] = []
    for key, value in table.items():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            for item in value:
                nested += [
                    "",
                    f"[[{name}.{key}]]",
                    *(f"{k} = {toml_value(v)}" for k, v in item.items()),
                ]
        else:
            rows.append(f"{toml_value(key)} = {toml_value(value)}")
    return rows + nested


def carried_tables(candidates: Sequence[Path]) -> dict[str, Any]:
    """Return what the first existing sidecar of ``candidates`` carries over, or nothing.

    The result holds ``operations`` (the translate and rotate operations, in the
    order written) and the named ``trailing_edges`` and ``base_regions`` tables.
    The shared declaration loader refuses retired or malformed tables. An
    unreadable sidecar raises UnreadableSidecarError; later candidates are not
    tried, so its settings cannot silently disappear.
    """
    for path in candidates:
        if not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as error:
            # Skipping it would drop its translate, rotate, wake and base-region settings.
            raise UnreadableSidecarError(
                f"the sidecar {path} cannot be read ({error}); repair or remove it, "
                "because a rebuild would drop what it carries"
            ) from error
        read_boundary_declarations(path)
        carried: dict[str, Any] = {}
        operations = [
            dict(op)
            for op in data.get("import", {}).get("operations", [])
            if isinstance(op, dict) and op.get("op") in CARRIED_OPERATIONS
        ]
        if operations:
            carried["operations"] = operations
        for table in _CARRIED_TABLES:
            if isinstance(data.get(table), dict):
                carried[table] = dict(data[table])
        return carried
    return {}


def sidecar_text(
    names: Sequence[str],
    units: str | None,
    te_file: str | None,
    carried: Mapping[str, Any] | None = None,
    *,
    fs_build: str | None = None,
    mesh: Path | None = None,
) -> tuple[str, list[str]]:
    """Return a built geometry's sidecar and the notes the build prints about it.

    Parameters
    ----------
    names : sequence of str
        The boundaries, in order.
    units : str or None
        The ``[import]`` unit of a built mesh; None beside a saved simulation.
    te_file : str or None
        The trailing-edge points file, when the build marked edges.
    carried : mapping, optional
        What :func:`carried_tables` returned.
    fs_build : str, optional
        Build that exported this mesh, required by its marking declarations.
    mesh : Path, optional
        Exported mesh whose inventory supplies face counts, digest and entry label.
    """
    carried = carried or {}
    notes: list[str] = []
    rows = [
        "# Written by pyfs-workspace geometry build.",
        "boundaries = " + toml_value(list(names)),
    ]
    if mesh is not None:
        rows += face_count_lines(mesh, len(names), obj=mesh.suffix.lower() == ".obj")
    if fs_build is not None:
        rows.append(f"fs_build = {toml_value(fs_build)}")
    if units is not None:
        rows += ["", "[import]", f"units = {toml_value(units)}"]
        for operation in carried.get("operations", []):
            rows += [
                "",
                "[[import.operations]]",
                *(f"{k} = {toml_value(v)}" for k, v in operation.items()),
            ]
        if carried.get("operations"):
            notes.append(
                "carried over the sidecar operations "
                + ", ".join(str(op.get("op")) for op in carried["operations"])
                + ", which apply during boundary marking"
            )
    if te_file is not None:
        rows += _edge_rows(mesh.stem if mesh is not None else "mesh", te_file, carried)
    elif units is not None:
        rows += ["", "[trailing_edges]", "none = true"]
    for table in ("base_regions",):
        if table in carried:
            rows += ["", *toml_table(table, carried[table])]
            notes.append(f"carried over [{table}]")
    return "\n".join(rows) + "\n", notes


def _edge_rows(label: str, te_file: str, carried: Mapping[str, Any]) -> list[str]:
    """Serialize the generated entry and its retained termination choice."""
    rows = [
        "",
        f"[trailing_edges.{toml_value(label)}]",
        f"file = {toml_value(te_file)}",
        'type = "STANDARD"',
    ]
    named = carried.get("trailing_edges", {}).get(label, {})
    termination = named.get("wake_termination_nodes")
    if termination is not None:
        rows.append("wake_termination_nodes = " + toml_value(termination))
    return rows


def write_mesh_sidecar(instruction, mesh, unit, midpoints, carried) -> list[str]:
    """Write the exported OBJ's inventory and edge points in the saved simulation's unit."""
    import numpy

    from pyflightstream.workspace._refine._obj import write_te

    te_file = None
    if midpoints:
        te_file = f"{mesh.stem}.te.txt"
        write_te(mesh.parent / te_file, unit, numpy.asarray(midpoints, dtype=float))
    text, notes = sidecar_text(
        instruction.boundaries, unit, te_file, carried, fs_build=instruction.fs_build, mesh=mesh
    )
    _textio.write_text(inventory_sidecar(mesh, "obj"), text)
    return notes


def sidecar_candidates(variant, mesh_name: str) -> list[Path]:
    """Return the sidecars a build reads, with the rebuilt mesh's inventory first."""
    instruction, folder = variant.instruction, variant.folder
    built = folder / f"{mesh_name}.obj"
    if instruction.outputs != ("obj",):
        built = folder.with_name(mesh_name) / f"{mesh_name}.obj"
    candidates = [boundaries_for_marking(built)]
    if instruction.mesh is not None:
        candidates.append(boundaries_for_marking(folder / instruction.mesh.file))
    return candidates
