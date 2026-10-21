"""The sidecar a build writes beside a built mesh, and what it carries over (FR-1105, FR-1111).

Pipeline role: the workspace row. A built OBJ is opened by the run through its
``<name>.boundaries.toml``: the inventory, the unit of the export and the
trailing-edge route the build wrote, and what the run reads of a mesh and the
build does not make: the ``translate`` and ``rotate`` operations of
``[[import.operations]]`` (these stay in the run), ``[wake_termination]``
and ``[base_regions]``. :func:`carried_tables` takes those from the sidecar the
rebuilt mesh had, else from the sidecar of the ``[mesh]`` source, so a rebuild
or a first build after ``from-sidecar`` keeps them.

A carried operation that moves the body cannot sit beside a trailing-edge
points file: the run refuses that pair, because the points name edges of the
file as it is. The sidecar then marks the edges by detection, and says so.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "CARRIED_OPERATIONS",
    "UnreadableSidecarError",
    "carried_tables",
    "sidecar_text",
    "toml_table",
    "toml_value",
]

#: The sidecar operations a build never applies: they stay in the run.
CARRIED_OPERATIONS = ("translate", "rotate")

#: The sidecar tables of a mesh the run reads and the build does not make.
_CARRIED_TABLES = ("wake_termination", "base_regions")


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
            rows.append(f"{key} = {toml_value(value)}")
    return rows + nested


def carried_tables(candidates: Sequence[Path]) -> dict[str, Any]:
    """Return what the first readable sidecar of ``candidates`` carries over, or nothing.

    The result holds ``operations`` (the translate and rotate operations, in the
    order written) and the ``wake_termination`` and ``base_regions`` tables, each
    only when stated.
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
    """
    carried = carried or {}
    notes: list[str] = []
    rows = [
        "# Written by pyfs-workspace geometry build.",
        "boundaries = [" + ", ".join(f'"{n}"' for n in names) + "]",
    ]
    if units is not None:
        rows += ["", "[import]", f'units = "{units}"']
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
                + ", which stay in the run"
            )
    if te_file is not None and carried.get("operations"):
        rows += ["", "[trailing_edges]", 'detect = "auto"']
        notes.append(
            "the trailing edges are marked by detection in the sidecar, because a carried "
            f"operation moves the body and the run refuses a points file beside it ({te_file} "
            "is kept beside the mesh)"
        )
    elif te_file is not None:
        rows += ["", "[trailing_edges]", f'file = "{te_file}"']
    for table in _CARRIED_TABLES:
        if table in carried:
            rows += ["", *toml_table(table, carried[table])]
            notes.append(f"carried over [{table}]")
    return "\n".join(rows) + "\n", notes
