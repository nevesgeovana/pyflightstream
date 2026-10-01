"""The files beside a geometry: its boundary inventory, provenance and raw-mesh sidecar.

A geometry of ``inputs/geometries/`` carries up to two files of its own,
named by its stem: ``<stem>.boundaries.toml``, the boundary inventory
(PFS-2029.06), which states the boundary order and, beside a raw mesh, the
``[import]`` table and the raw mesh conditions (trailing edges, wake
termination, base regions); and ``<stem>.provenance.toml``, the record of
where the geometry came from, which the package never writes. This module
writes and checks the inventory (the boundary names read off an OBJ or a
saved simulation), reads each table of the sidecar with its own reader over
one parse, and moves a flat geometry library into one folder per geometry
(:func:`migrate_geometry_layout`, PFS-2032.04).

It also holds the TOML reader of the input library's artifact files, which
the artifact resolvers and the HPC profile reader share.

Every public name is re-exported, unchanged, by :mod:`pyflightstream.workspace.inputs`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import json
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import ValidationError

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning, warn
from pyflightstream._fsm import MeshReadError, boundary_names
from pyflightstream.cases import (
    EVERY_SURFACE,
    InputKey,
    MeshImport,
    RawMeshConditions,
    TrailingEdgeMarking,
)

__all__ = [
    "BASE_REGIONS_TABLE",
    "DETECT_EVERYWHERE",
    "GEOMETRIES_README",
    "GEOMETRY_SIDECAR_KEYS",
    "IMPORT_TABLE",
    "INVENTORY_SUFFIX",
    "OBJ_SUFFIX",
    "PROVENANCE_SUFFIX",
    "RAW_MESH_CONDITION_KEYS",
    "RAW_MESH_CONDITION_TABLES",
    "SIDECAR_SUFFIXES",
    "TRAILING_EDGES_TABLE",
    "TRAILING_EDGE_DETECT_KEYS",
    "WAKE_TERMINATION_TABLE",
    "GeometryMigration",
    "ensure_inventory",
    "inventory_sidecar",
    "migrate_geometry_layout",
    "obj_boundary_names",
    "read_inventory",
    "read_mesh_import",
    "read_raw_mesh_conditions",
    "write_inventory",
]


def load_toml(path: Path, kind: str) -> dict[str, Any]:
    """Read one TOML artifact file, naming the file on a syntax error."""
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise InputArtifactError(
            f"the {kind} artifact {path} is not valid TOML: {error}. Artifacts are "
            "declarative TOML files, one artifact per file."
        ) from error


def is_sidecar(name: str) -> bool:
    """Whether a file name is a geometry's inventory or provenance record."""
    return name.endswith(SIDECAR_SUFFIXES)


# --- the boundary inventory sidecar (PFS-2029.06) ------------------------------------

#: Suffix of the sidecar that states a geometry's boundary order, appended
#: to the geometry's stem: ``30_WB.fsm`` has ``30_WB.boundaries.toml``.
INVENTORY_SUFFIX = ".boundaries.toml"
#: Suffix of the record that says where a geometry came from, appended to
#: its stem the same way. The package writes none: the tier-3 preparer and
#: a user do, and the library carries it beside the file it describes.
PROVENANCE_SUFFIX = ".provenance.toml"
#: The two files that belong to a geometry and are never geometries
#: themselves: the resolver leaves them out of what a cell could name and
#: the layout migration moves them with their geometry (PFS-2032.05).
SIDECAR_SUFFIXES = (INVENTORY_SUFFIX, PROVENANCE_SUFFIX)
#: The page ``init`` leaves in the geometry library saying where a mesh goes
#: (PFS-2032.07). It lives HERE, beside the suffixes, rather than beside the
#: text it names, because the resolver and the writer are the two ends of one
#: spelling: the resolver must leave this file out of what a GEOMETRY cell
#: could name, and a second spelling of it is how that stops being true.
GEOMETRIES_README = "README.md"


def inventory_sidecar(geometry: str | Path) -> Path:
    """Return the sidecar path beside ``geometry``, whether or not it exists."""
    path = Path(geometry)
    return path.with_name(path.stem + INVENTORY_SUFFIX)


def write_inventory(geometry: str | Path, *, overwrite: bool = False) -> Path:
    """Write ``<stem>.boundaries.toml`` beside a saved simulation.

    THE ORDER IS READ, NEVER STATED (PFS-2029.06.02). Until 0.11.0 a
    setup preset could carry ``mesh_order_list``, an order typed by hand
    for one mesh into a file several meshes shared, and nothing checked
    it against any of them. The sidecar is produced from the mesh block
    of the file it sits beside, and a run whose sidecar disagrees with
    the file is refused before the solver starts (:func:`read_inventory`
    and the workflow builder), so the two cannot drift apart silently.

    AN OBJ IS READ FROM ITS GROUPS (G30). It carries no mesh block, and
    its sidecar is written through :func:`ensure_inventory`, the function
    the matrix binding reaches it through as well, so ``pyfs-matrix
    inventory`` and a plan write the same file. An OBJ's existing sidecar
    is refused with ``overwrite`` too: beside a raw mesh it also carries
    the ``[import]`` table and the trailing edges, which a rewrite of the
    list would lose. An STL, which names no group, is refused as before.

    Parameters
    ----------
    geometry : str or Path
        A saved simulation file carrying a mesh block, or an OBJ.
    overwrite : bool
        Rewrite a saved simulation's sidecar that already exists. Without
        it an existing sidecar is refused, because the file may have been
        edited by the user after it was written.

    Returns
    -------
    Path
        The sidecar written.

    Raises
    ------
    InputArtifactError
        A geometry that cannot be read, that carries no mesh block, or
        whose block does not hold its shape, each naming the file; a
        sidecar that already exists, naming it and ``--overwrite``; an
        OBJ's sidecar that already exists, with ``overwrite`` or without;
        an OBJ whose groups cannot be read (:func:`obj_boundary_names`).
    """
    path = Path(geometry)
    sidecar = inventory_sidecar(path)
    if not path.is_file():
        raise InputArtifactError(
            f"{path} is not a file, so no boundary inventory can be read from it."
        )
    if path.suffix.lower() == OBJ_SUFFIX:
        if sidecar.exists():
            raise InputArtifactError(
                f"{sidecar} already exists, and the sidecar of an OBJ is never rewritten, "
                "overwrite (CLI: --overwrite) or not: beside a raw mesh it also carries the "
                "[import] table and the trailing edges, which a rewrite of the list would "
                f"lose. A plan compares its boundaries with the groups of {path.name} and "
                "warns naming both lists when they differ; correct the list by hand, or "
                "move the file aside, run this again and copy its tables beneath the new "
                "list (docs/mesh-inputs.md)."
            )
        return ensure_inventory(path)
    if sidecar.exists() and not overwrite:
        raise InputArtifactError(
            f"{sidecar} already exists; pass overwrite (CLI: --overwrite) to rewrite it "
            "from the mesh block, after checking that the file is the one the sidecar "
            "should describe."
        )
    try:
        names = boundary_names(path)
    except MeshReadError as error:
        raise InputArtifactError(f"{path.name}: {error}") from error
    if not names:
        raise InputArtifactError(
            f"{path} carries no mesh block, so it states no boundary order to write. "
            "A saved simulation (.fsm) carries one; a raw mesh (.obj, .stl) does not, so "
            f"write its surface names by hand in {sidecar.name}, in the file's order, "
            "beside the [import] table that states its units (docs/mesh-inputs.md)."
        )
    body = [
        f"# Boundary inventory of {path.name}, read from its mesh block by "
        "`pyfs-matrix inventory`.",
        "# The solver's own order: the name at position i is boundary i (1-based).",
        f'file = "{path.name}"',
        "boundaries = [",
        *[f'    "{name}",' for name in names],
        "]",
    ]
    sidecar.write_text("\n".join(body) + "\n", encoding="utf-8")
    return sidecar


# --- an OBJ's surface names, read from its groups (G30, RPT-078) ---------------------

#: The raw-mesh suffix whose surface names are read from the file itself. An
#: OBJ names its groups, and the solver makes one boundary of each group that
#: holds a face, named by the group, in the order of the file (RPT-078). An
#: STL names no group, so its names stay written by hand.
OBJ_SUFFIX = ".obj"

#: The two statements that open a group of an OBJ. RPT-078 measured both,
#: each alone in its file; a file mixing them is refused.
_OBJ_GROUP_STATEMENTS = ("o", "g")


def obj_boundary_names(path: str | Path) -> tuple[str, ...]:
    """Return measured OBJ boundary names in native order, preserving duplicates.

    RPT-078 established face-bearing groups. GOAL-033 controls on 26.124,
    build 8172026 additionally measured an o-to-g transition, repeated g
    groups, a face prefix before the first g, and multiple names in a g
    statement. The latter uses only its first name, with a warning.

    Repeated g groups remain separate boundaries; ambiguous labels must be
    selected by position downstream. Reverse g-to-o transitions, repeated
    o names, unnamed groups and multiword o names remain unmeasured here.
    """
    mesh = Path(path)
    by_hand = (
        "The surface names of such a file are not read from it: write them by hand in "
        f"{inventory_sidecar(mesh).name} beside it, as boundaries = [...] in the order the "
        "solver numbers the surfaces (docs/mesh-inputs.md)."
    )
    names: list[str] = []
    opened: dict[str, tuple[str, int]] = {}
    previous: tuple[str, int] | None = None
    current: str | None = None
    holds_face = False
    prefix_face_line: int | None = None
    try:
        with mesh.open(encoding="utf-8") as lines:
            for number, line in enumerate(lines, start=1):
                if line.startswith("v"):
                    continue
                words = line.split("#", 1)[0].split()
                if not words:
                    continue
                if words[0] == "f":
                    if current is None and prefix_face_line is None:
                        prefix_face_line = number
                    holds_face = True
                    continue
                if words[0] not in _OBJ_GROUP_STATEMENTS:
                    continue
                statement = words[0]
                if len(words) < 2 or (statement == "o" and len(words) != 2):
                    stated = "no group" if len(words) == 1 else "a group of several words"
                    raise InputArtifactError(
                        f"{mesh}: line {number}, {line.strip()!r}, names {stated}, and how "
                        f"the solver names such a group is not measured. {by_hand}"
                    )
                if prefix_face_line is not None and previous is None and statement != "g":
                    raise InputArtifactError(
                        f"{mesh}: line {prefix_face_line} writes a face before the first "
                        f"{statement!r} group; that variant is not measured. {by_hand}"
                    )
                if previous is not None and previous[0] == "g" and statement == "o":
                    raise InputArtifactError(
                        f"{mesh}: line {number} opens a group with `o` after `g` at "
                        f"line {previous[1]}; this transition is not measured. {by_hand}"
                    )
                name = words[1]
                if name in opened and (statement != "g" or opened[name][0] != "g"):
                    raise InputArtifactError(
                        f"{mesh}: line {number} opens the group {name!r} again, first opened "
                        f"at line {opened[name][1]}: a group in two places involving an "
                        f"`o` statement is not measured. {by_hand}"
                    )
                if len(words) > 2:
                    warn(
                        f"{mesh}: line {number} names multiple OBJ groups; the measured "
                        f"native importer uses only the first, {name!r}.",
                        PyflightstreamWarning,
                        stacklevel=2,
                    )
                opened.setdefault(name, (statement, number))
                if holds_face:
                    names.append(current if current is not None else "Boundary-1")
                current, holds_face = name, False
                previous = (statement, number)
    except (OSError, UnicodeDecodeError) as error:
        raise InputArtifactError(
            f"{mesh} cannot be read as the text of an OBJ: {error}. {by_hand}"
        ) from error
    if current is not None and holds_face:
        names.append(current)
    if not names:
        raise InputArtifactError(
            f"{mesh} holds no face under any measured `o` or `g` group, so no "
            f"boundary inventory is established; check the mesh. {by_hand}"
        )
    return tuple(names)


def ensure_inventory(geometry: str | Path) -> Path:
    """Return the boundary sidecar beside a geometry, writing an OBJ's from its groups (G30).

    THE ONE PLACE A SIDECAR IS ASKED FOR. The matrix binding, which
    ``pyfs-matrix plan`` and ``pyfs-matrix run`` both pass through, and
    ``pyfs-matrix inventory`` (:func:`write_inventory`) reach the sidecar
    through this function, so an OBJ is treated alike wherever a user
    meets it:

    * an OBJ with no sidecar gets one, its ``boundaries`` read by
      :func:`obj_boundary_names` under a comment header naming the file's
      sha256 and RPT-078, and a line on stderr says so. It carries the
      list and nothing else: the ``[import]`` units and the trailing
      edges, which only the user can state, go beneath it.
    * an OBJ with a sidecar keeps it, never rewritten, because the file
      may carry tables and names the user wrote. When its ``boundaries``
      differ from the groups, in names or in order, the run cites the
      sidecar's, as before, and a warning names both lists; when the
      groups cannot be read, the sidecar written by hand is that file's
      route and nothing is said.
    * any other geometry is left as it was: a saved simulation's sidecar
      is written by ``pyfs-matrix inventory`` from its mesh block, and an
      STL's by hand.

    Parameters
    ----------
    geometry : str or Path
        The geometry the sidecar sits beside.

    Returns
    -------
    Path
        The sidecar beside ``geometry``, which exists for every OBJ this
        returns for; for another geometry it exists only if written.

    Raises
    ------
    InputArtifactError
        An OBJ with no sidecar whose groups cannot be read
        (:func:`obj_boundary_names`), naming the line and the sidecar to
        write by hand; an OBJ whose sidecar states no ``boundaries`` list,
        naming the list its groups make.

    Warns
    -----
    PyflightstreamWarning
        An OBJ whose sidecar's ``boundaries`` differ from its groups,
        naming both lists.
    """
    path = Path(geometry)
    sidecar = inventory_sidecar(path)
    if path.suffix.lower() != OBJ_SUFFIX or not path.is_file():
        return sidecar
    if sidecar.exists():
        _compare_with_the_groups(path, sidecar)
        return sidecar
    names = obj_boundary_names(path)
    body = [
        f"# Written by pyflightstream from the groups of {path.name}, which had no sidecar;",
        f"# the OBJ's sha256 was {file_sha256(path)}.",
        "# One boundary per `o` or `g` group holding a face, named by the group, in the",
        "# order of the file: how the solver numbers an OBJ's surfaces on import",
        "# (RPT-078). The package never rewrites this file. Add the [import] table with",
        "# the file's units, and the [trailing_edges] table, beneath the list",
        "# (docs/mesh-inputs.md).",
        "boundaries = [",
        *[f"    {_toml_string(name)}," for name in names],
        "]",
    ]
    sidecar.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(
        f"wrote {sidecar}: the boundaries of {path.name}, read from its groups in the "
        f"order of the file (RPT-078): {', '.join(names)}. Add its [import] units and its "
        "[trailing_edges] beneath them.",
        file=sys.stderr,
        flush=True,
    )
    return sidecar


def _compare_with_the_groups(mesh: Path, sidecar: Path) -> None:
    """Warn when an OBJ's own sidecar lists other boundaries than its groups make (G30)."""
    stated = _sidecar_data(sidecar).get("boundaries")
    try:
        groups = obj_boundary_names(mesh)
    except InputArtifactError:
        # The file is one whose names are not read from it, so the list
        # written by hand is its route, and there is nothing to compare.
        return
    listed = ", ".join(groups)
    if not isinstance(stated, list) or not stated or not all(isinstance(n, str) for n in stated):
        written = ", ".join(_toml_string(name) for name in groups)
        raise InputArtifactError(
            f"{sidecar} does not state `boundaries` as a non-empty list of strings. The "
            f"groups of {mesh.name} that hold a face, in the order the solver numbers "
            f"them on import (RPT-078), are {listed}: write boundaries = [{written}] at "
            "the top of the file. It is never rewritten by the package, because it may "
            "carry tables you wrote (docs/mesh-inputs.md)."
        )
    if tuple(stated) != groups:
        warn(
            f"{sidecar.name} lists the boundaries of {mesh.name} as {', '.join(stated)}, and "
            "its groups that hold a face, in the order the solver numbers them on import "
            f"(RPT-078), are {listed}. The run cites the sidecar's list as written, so a "
            "surface it names at a position where the file holds another is cited at the "
            "wrong one. Correct the list, or move the sidecar aside, plan again to have it "
            "written from the groups, and copy its tables beneath the new list.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _toml_string(name: str) -> str:
    """Quote one name as a TOML basic string; JSON's escapes are TOML's."""
    return json.dumps(name, ensure_ascii=False)


#: The table of a geometry's sidecar that states how a raw mesh is imported
#: (G01): ``[import]``, holding ``units``.
IMPORT_TABLE = "import"


def _sidecar_data(sidecar: Path) -> dict[str, Any]:
    """Parse one geometry sidecar, refusing a file that does not read as TOML, by name.

    ONE PARSE, ONE READER PER TABLE. The sidecar holds the boundary order
    (``boundaries``) and, beside a raw mesh, the ``[import]`` table; each
    is read by its own function over this parse, and no reader refuses a
    table it does not read. A table added to the file later is therefore
    one more reader beside these, and the readers already here are left as
    they are.
    """
    try:
        return tomllib.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise InputArtifactError(
            f"{sidecar} cannot be read as a geometry sidecar: {error}"
        ) from error


def read_inventory(sidecar: str | Path) -> tuple[str, ...]:
    """Return the ordered boundary names a sidecar states.

    Raises
    ------
    InputArtifactError
        A sidecar without a ``boundaries`` list of strings, naming it.
    """
    path = Path(sidecar)
    names = _sidecar_data(path).get("boundaries")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise InputArtifactError(
            f"{path} does not state `boundaries` as a non-empty list of strings; "
            "for a saved simulation, rewrite it from the file with `pyfs-matrix "
            "inventory <geometry>`, overwrite (CLI: --overwrite); for a raw mesh (.obj, "
            ".stl), write its surface names in the order the solver numbers them "
            "(docs/mesh-inputs.md)."
        )
    return tuple(names)


def read_mesh_import(sidecar: str | Path) -> MeshImport | None:
    """Return the ``[import]`` table a geometry's sidecar states, or None (G01, G03).

    The table states the length unit a raw mesh is written in, and the
    mesh operations applied right after the import, in the order written::

        boundaries = ["naca"]

        [import]
        units = "MILLIMETER"

        [[import.operations]]
        op = "rename"
        surface = "naca"
        to = "Wing"

    Read at binding, beside :func:`read_inventory`, so a table that does
    not hold its shape is refused with the row before any seat is spent,
    an operation named by its position. Whether the unit is one ``IMPORT``
    takes, whether the geometry is a raw mesh at all, and whether each
    cited surface exists at its step, is the builder's to judge, per build.

    Parameters
    ----------
    sidecar : str or Path
        The ``<stem>.boundaries.toml`` beside the geometry.

    Returns
    -------
    MeshImport or None
        None when the file holds no ``[import]`` table.

    Raises
    ------
    InputArtifactError
        A file that does not read as TOML, an ``import`` key that is not a
        table, a table that states no ``units`` or a key it does not read,
        or an operation that does not hold its shape (its own keys, finite
        numbers, scale factors above zero, a named surface for a rename or
        a mirror), each naming the sidecar and the operation's position.
    """
    path = Path(sidecar)
    table = _sidecar_data(path).get(IMPORT_TABLE)
    if table is None:
        return None
    if not isinstance(table, dict):
        raise InputArtifactError(
            f"{path} states `{IMPORT_TABLE}` as a {type(table).__name__}; write it as the "
            f'table [{IMPORT_TABLE}], with units = "MILLIMETER" (the unit the mesh file is '
            "written in) beneath it."
        )
    try:
        return MeshImport.model_validate(table)
    except ValidationError as error:
        missing = any(
            item["type"] == "missing" and tuple(item["loc"]) == ("units",)
            for item in error.errors()
        )
        if missing:
            raise InputArtifactError(
                f"{path}: the [{IMPORT_TABLE}] table does not state `units`, the length "
                "unit the mesh file is written in; write it beneath the table, as "
                'units = "MILLIMETER". A unit is never assumed (docs/mesh-inputs.md).'
            ) from error
        problems = "; ".join(
            f"{_where_in_the_import_table(item['loc'])}: "
            f"{str(item['msg']).removeprefix('Value error, ')}"
            for item in error.errors()
        )
        raise InputArtifactError(
            f"{path}: the [{IMPORT_TABLE}] table is refused: {problems}. It holds `units`, "
            "the length unit the mesh file is written in, and the mesh operations of the "
            f"import as [[{IMPORT_TABLE}.operations]], numbered in the order written "
            "(docs/mesh-inputs.md)."
        ) from error


#: The tables of a geometry's sidecar that declare a raw mesh's boundary
#: conditions (G02): the trailing edge, which every raw mesh a workflow
#: imports declares, and two options that apply only when written.
TRAILING_EDGES_TABLE = "trailing_edges"
WAKE_TERMINATION_TABLE = "wake_termination"
BASE_REGIONS_TABLE = "base_regions"
RAW_MESH_CONDITION_TABLES = (TRAILING_EDGES_TABLE, WAKE_TERMINATION_TABLE, BASE_REGIONS_TABLE)

#: The word a ``detect`` key takes for detection over every surface.
DETECT_EVERYWHERE = "auto"

#: WHAT A GEOMETRY'S SIDECAR MAY HOLD AT ITS TOP LEVEL, each with what it
#: sets, for the generated input glossary ``INPUTS.md`` (G08 of 0.27.0). The
#: tables' own keys are in the registries below, which are the ones their
#: readers read, so a key a reader gains is a key the glossary states.
GEOMETRY_SIDECAR_KEYS: Mapping[str, InputKey] = {
    "ports": InputKey(
        "Stable port identity to exact surface name; conditions belong to setup and MATRIX.",
        'a table such as [ports] with feed = "Inlet"',
    ),
    "boundaries": InputKey(
        "The mesh's boundary names in the solver's order, the name at position i being "
        "boundary i; read from a saved simulation by pyfs-matrix inventory, read from an "
        "OBJ's groups by the plan when it has no sidecar, written by hand for an STL.",
        "a list of names",
    ),
    "file": InputKey(
        "The file the inventory was read from, as pyfs-matrix inventory writes it; "
        "nothing reads it back.",
        "a file name",
    ),
    IMPORT_TABLE: InputKey(
        "How a raw mesh is imported: the unit it is written in and the operations "
        "applied right after.",
        "a table; see `[import]` below",
        "IMPORT",
    ),
    TRAILING_EDGES_TABLE: InputKey(
        "How a raw mesh's trailing edges are marked, which every raw mesh a workflow "
        "imports declares.",
        "a table; see `[trailing_edges]` below",
        "IMPORT_WAKE_EDGES_FROM_FILE, AUTO_DETECT_TRAILING_EDGES, DETECT_TRAILING_EDGES_BY_SURFACE",
    ),
    WAKE_TERMINATION_TABLE: InputKey(
        "Detects a raw mesh's wake-termination nodes, only when written.",
        "a table; see `[wake_termination]` below",
        "AUTO_DETECT_WAKE_TERMINATION_NODES, DETECT_WAKE_TERMINATION_NODES_BY_SURFACE",
    ),
    BASE_REGIONS_TABLE: InputKey(
        "Detects a raw mesh's base regions over the whole mesh, only when written.",
        "a table; see `[base_regions]` below",
        "AUTO_DETECT_BASE_REGIONS",
    ),
}

#: THE KEYS EACH BOUNDARY-CONDITION TABLE OF A SIDECAR READS, each with what it
#: sets. The readers below read THESE: a key outside its table's entry is
#: refused naming itself, so a key added here is read and stated at once, and
#: one read without a meaning cannot exist.
RAW_MESH_CONDITION_KEYS: Mapping[str, Mapping[str, InputKey]] = {
    TRAILING_EDGES_TABLE: {
        "none": InputKey(
            "Explicitly declares a body without a trailing edge; no wake is generated by it.",
            "true, alone in the table",
            "",
        ),
        "file": InputKey(
            "The points file beside the sidecar holding the mid-point of every "
            "trailing-edge mesh edge, under a line naming their length unit; the "
            "default route.",
            "a file name",
            "IMPORT_WAKE_EDGES_FROM_FILE",
        ),
        "type": InputKey(
            "The edge type every point of the file is given.",
            'text, default `"STANDARD"`',
            "IMPORT_WAKE_EDGES_FROM_FILE",
        ),
        "tolerance": InputKey(
            "The distance within which an edge's mid-point counts as a point of the file.",
            "m, > 0, default `0.0001`",
            "IMPORT_WAKE_EDGES_FROM_FILE",
        ),
        "detect": InputKey(
            "Marks the edges by the solver's detection instead of a file, over every "
            "surface or on the surfaces named.",
            '`"auto"`, or a table; see `detect = { ... }` below',
            "AUTO_DETECT_TRAILING_EDGES, DETECT_TRAILING_EDGES_BY_SURFACE",
        ),
    },
    WAKE_TERMINATION_TABLE: {
        "detect": InputKey(
            "Detects the wake-termination nodes over every surface, or on the surfaces named.",
            '`"auto"`, or `{ surfaces = ["<name>"] }`',
            "AUTO_DETECT_WAKE_TERMINATION_NODES, DETECT_WAKE_TERMINATION_NODES_BY_SURFACE",
        ),
    },
    BASE_REGIONS_TABLE: {
        "detect": InputKey(
            "Detects the base regions over the whole mesh; a named boundary is the "
            "row's BASE_REGIONS key's.",
            '`"auto"`',
            "AUTO_DETECT_BASE_REGIONS",
        ),
    },
}

#: The keys a ``detect = { ... }`` table of ``[trailing_edges]`` reads, with
#: what each sets, read by :func:`_read_trailing_edge_detection`.
TRAILING_EDGE_DETECT_KEYS: Mapping[str, InputKey] = {
    "surfaces": InputKey(
        "The surfaces to detect on, by the sidecar's names.",
        'a list of names, or `"all"` for every surface',
        "DETECT_TRAILING_EDGES_BY_SURFACE",
    ),
    "sweep_angle": InputKey(
        "The sweep angle set before the detection, only when stated.",
        "deg",
        "SET_TRAILING_EDGE_SWEEP_ANGLE",
    ),
}

#: The keys ``[trailing_edges]`` reads: ``file`` with ``type`` and
#: ``tolerance``, the default route, or ``detect`` alone.
_TRAILING_EDGE_KEYS = tuple(RAW_MESH_CONDITION_KEYS[TRAILING_EDGES_TABLE])

#: The keys a ``detect = { ... }`` table of ``[trailing_edges]`` reads.
_DETECT_KEYS = tuple(TRAILING_EDGE_DETECT_KEYS)

_TRAILING_EDGE_ROUTES = (
    'file = "<points file>", the default route: the mid-point of every trailing-edge '
    'mesh edge, under a line naming their length unit; or detect = "auto" or '
    'detect = { surfaces = ["<name>"], sweep_angle = <degrees> }, detection, which '
    "applies only when written (docs/mesh-inputs.md)"
)


def read_raw_mesh_conditions(sidecar: str | Path) -> RawMeshConditions | None:
    """Return the boundary conditions a raw mesh's sidecar declares, or None (G02).

    Three tables, each read only when written::

        [trailing_edges]
        file = "wing.te.txt"      # the default route: a points file
        type = "STANDARD"         # optional, the edge type of every point
        tolerance = 0.0001        # optional, in the simulation's length unit

        # or detection, only when written:
        # detect = "auto"
        # detect = { surfaces = ["Wing"], sweep_angle = 60 }

        [wake_termination]
        detect = "auto"           # or { surfaces = ["Wing"] }

        [base_regions]
        detect = "auto"

    Read at binding, beside :func:`read_mesh_import`, so a table that does
    not hold its shape is refused with the row before any seat is spent.
    ``file`` is resolved against the sidecar's folder here; its points are
    read and checked against the mesh by the binding, which knows the
    mesh's unit, and whether the geometry is a raw mesh at all is the
    builder's to judge.

    Parameters
    ----------
    sidecar : str or Path
        The ``<stem>.boundaries.toml`` beside the geometry.

    Returns
    -------
    RawMeshConditions or None
        None when the file holds none of the three tables. A file route's
        ``points_m`` are empty here and ``points_file`` names the file.

    Raises
    ------
    InputArtifactError
        A table written as anything but a table, a key a table does not
        read, a ``[trailing_edges]`` stating both ``file`` and ``detect`` or
        neither, a ``type`` or ``tolerance`` beside ``detect``, a ``detect``
        of a shape its table does not take, an empty surface list, or a
        tolerance that is not a positive number; each naming the sidecar
        and the table.
    """
    path = Path(sidecar)
    data = _sidecar_data(path)
    if any(name in data for name in ("inlets", "outlets")):
        raise InputArtifactError(
            f"{path}: inlet/outlet conditions belong to setup [[ports]] and MATRIX values; "
            "keep only [ports] identity-to-surface mappings in this geometry sidecar."
        )
    ports = data.get("ports", {})
    if not isinstance(ports, dict) or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, str)
        or not value.strip()
        for key, value in ports.items()
    ):
        raise InputArtifactError(f"{path}: [ports] maps each nonempty identity to a surface name")
    tables: dict[str, dict[str, Any] | None] = {}
    for name in RAW_MESH_CONDITION_TABLES:
        table = data.get(name)
        if table is not None and not isinstance(table, dict):
            raise InputArtifactError(
                f"{path} states `{name}` as a {type(table).__name__}; write it as the table "
                f"[{name}] with its keys beneath it (docs/mesh-inputs.md)."
            )
        tables[name] = table
    if all(table is None for table in tables.values()) and not ports:
        return None
    trailing = tables[TRAILING_EDGES_TABLE]
    wake = tables[WAKE_TERMINATION_TABLE]
    base = tables[BASE_REGIONS_TABLE]
    # The reader returns DETECT_EVERYWHERE or, by surface, the surfaces' names,
    # and refuses anything else; the casts state that to the type checker,
    # which cannot see it through the reader's one return type.
    try:
        return RawMeshConditions(
            trailing_edges=None if trailing is None else _read_trailing_edges(path, trailing),
            wake_termination=(
                None
                if wake is None
                else cast(
                    "Literal['auto'] | tuple[str, ...]",
                    _read_detection(path, WAKE_TERMINATION_TABLE, wake, by_surface=True),
                )
            ),
            base_regions=(
                None
                if base is None
                else cast(
                    "Literal['auto']",
                    _read_detection(path, BASE_REGIONS_TABLE, base, by_surface=False),
                )
            ),
            ports=ports,
        )
    except ValueError as exc:
        raise InputArtifactError(f"{path}: invalid mesh boundary conditions: {exc}") from exc


def _read_trailing_edges(path: Path, table: Mapping[str, Any]) -> TrailingEdgeMarking:
    """Read ``[trailing_edges]``: one route, file or detect, and the keys of that route."""
    where = f"{path}: the [{TRAILING_EDGES_TABLE}] table"
    if "none" in table:
        if table != {"none": True} or table["none"] is not True:
            raise InputArtifactError(f"{where}: none = true must be the only trailing-edge choice")
        return TrailingEdgeMarking(route="none")
    foreign = sorted(set(table) - set(_TRAILING_EDGE_KEYS))
    if foreign:
        raise InputArtifactError(
            f"{where} does not read {', '.join(foreign)}; it reads {_TRAILING_EDGE_ROUTES}, "
            "with type and tolerance beside file."
        )
    if ("file" in table) == ("detect" in table):
        stated = "both file and detect" if "file" in table else "neither file nor detect"
        raise InputArtifactError(
            f"{where} states {stated}, and a trailing edge is marked by one of them: "
            f"{_TRAILING_EDGE_ROUTES}."
        )
    tolerance = table.get("tolerance", 0.0001)
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise InputArtifactError(
            f"{where} states tolerance = {tolerance!r}; write the distance, in the "
            "simulation's length unit, within which an edge's mid-point counts as a point "
            "of the file, as a number such as 0.0001."
        )
    fields: dict[str, Any] = {}
    if "file" in table:
        written = table["file"]
        if not isinstance(written, str) or not written.strip():
            raise InputArtifactError(
                f"{where} states file = {written!r}; write the name of the points file, "
                'beside the sidecar, as file = "wing.te.txt".'
            )
        fields = {
            "route": "file",
            "edge_type": table.get("type", "STANDARD"),
            "tolerance": float(tolerance),
            "points_file": str(path.parent / written.strip()),
        }
    else:
        beside = sorted(key for key in ("type", "tolerance") if key in table)
        if beside:
            raise InputArtifactError(
                f"{where} states {' and '.join(beside)} beside detect, and detection reads "
                "neither: it gives every edge it marks the STANDARD type and matches no "
                "points. Delete them, or mark the edges by a points file (file = ...)."
            )
        fields = {"route": "detect", **_read_trailing_edge_detection(where, table["detect"])}
    try:
        return TrailingEdgeMarking.model_validate(fields)
    except ValidationError as error:
        problems = "; ".join(
            str(item["msg"]).removeprefix("Value error, ") for item in error.errors()
        )
        raise InputArtifactError(f"{where} is refused: {problems}.") from error


def _read_trailing_edge_detection(where: str, detect: object) -> dict[str, Any]:
    """Read ``detect``: ``"auto"``, or a table of surfaces and an optional sweep angle."""
    if detect == DETECT_EVERYWHERE:
        return {}
    if not isinstance(detect, dict):
        raise InputArtifactError(
            f'{where} states detect = {detect!r}; write detect = "{DETECT_EVERYWHERE}" for '
            'detection over every surface, or detect = { surfaces = ["<name>"], '
            "sweep_angle = <degrees> } for detection on the surfaces named."
        )
    foreign = sorted(set(detect) - set(_DETECT_KEYS))
    if foreign:
        raise InputArtifactError(
            f"{where}: detect does not read {', '.join(foreign)}; it reads surfaces and, "
            "optionally, sweep_angle."
        )
    surfaces = detect.get("surfaces")
    fields: dict[str, Any] = {"detect_surfaces": _surface_names(where, surfaces, every=True)}
    if "sweep_angle" in detect:
        angle = detect["sweep_angle"]
        if isinstance(angle, bool) or not isinstance(angle, (int, float)):
            raise InputArtifactError(
                f"{where}: detect states sweep_angle = {angle!r}; write it in degrees, as a number."
            )
        fields["sweep_angle_deg"] = float(angle)
    return fields


def _surface_names(where: str, surfaces: object, *, every: bool) -> tuple[str, ...]:
    """Read a ``surfaces`` list of sidecar names; ``"all"`` is every surface where ``every``."""
    if every and surfaces == EVERY_SURFACE:
        return ()
    if (
        not isinstance(surfaces, list)
        or not surfaces
        or not all(isinstance(name, str) and name.strip() for name in surfaces)
    ):
        written = "is not stated" if surfaces is None else f"= {surfaces!r}"
        also = f', or "{EVERY_SURFACE}" for every surface' if every else ""
        raise InputArtifactError(
            f"{where}: detect's surfaces {written}; write the surfaces to detect on as a "
            f'non-empty list of the sidecar\'s names, surfaces = ["<name>"]{also}.'
        )
    return tuple(name.strip() for name in surfaces)


def _read_detection(
    path: Path, name: str, table: Mapping[str, Any], *, by_surface: bool
) -> str | tuple[str, ...]:
    """Read ``[wake_termination]`` or ``[base_regions]``: one ``detect`` key."""
    where = f"{path}: the [{name}] table"
    shapes = f'detect = "{DETECT_EVERYWHERE}"' + (
        ' or detect = { surfaces = ["<name>"] }' if by_surface else ""
    )
    foreign = sorted(set(table) - set(RAW_MESH_CONDITION_KEYS[name]))
    if foreign or "detect" not in table:
        stated = f"reads no {', '.join(foreign)}" if foreign else "states no detect"
        raise InputArtifactError(f"{where} {stated}; it reads one key, {shapes}.")
    detect = table["detect"]
    if detect == DETECT_EVERYWHERE:
        return DETECT_EVERYWHERE
    if by_surface and isinstance(detect, dict) and set(detect) == {"surfaces"}:
        return _surface_names(where, detect["surfaces"], every=False)
    why = (
        ""
        if by_surface
        else ". A base region is detected on a named boundary by the row's BASE_REGIONS "
        "key, which names the boundary that becomes the base"
    )
    raise InputArtifactError(f"{where} states detect = {detect!r}; it takes {shapes}{why}.")


def _where_in_the_import_table(loc: Sequence[int | str]) -> str:
    """Name a place of the ``[import]`` table as its reader counts it: ``operation 2 (factors)``."""
    if len(loc) >= 2 and loc[0] == "operations" and isinstance(loc[1], int):
        rest = ".".join(str(part) for part in loc[2:])
        return f"operation {loc[1] + 1}" + (f" ({rest})" if rest else "")
    return ".".join(str(part) for part in loc) or "the table"


# --- one subfolder per geometry (PFS-2032.05) ----------------------------------------


@dataclass(frozen=True)
class GeometryMigration:
    """What :func:`migrate_geometry_layout` did to one library.

    Attributes
    ----------
    moved : tuple of (Path, Path)
        Every file moved, as ``(where it was, where it is)``, in the order
        the moves were made: each geometry file, then the sidecars that
        carry its stem.
    kept : tuple of str
        The stems whose folder already existed and was left alone, a flat
        file of that stem included: the folder is the reading's first
        answer, so the migration does not decide which of the two the
        owner meant.
    """

    moved: tuple[tuple[Path, Path], ...]
    kept: tuple[str, ...]


def migrate_geometry_layout(inputs_dir: str | Path) -> GeometryMigration:
    """Move a flat geometry library into one folder per geometry, idempotently.

    Every ``geometries/<stem>.<ext>`` directly under the library moves to
    ``geometries/<stem>/<stem>.<ext>``, and its ``<stem>.boundaries.toml``
    and ``<stem>.provenance.toml`` move with it, so what belongs to one
    geometry sits in one place (PFS-2032.05, design 68 section A3). A
    folder that already exists is left alone with whatever it holds, and a
    second run over the same library moves nothing: nothing here decides
    for the user. The run records of a workspace are untouched and keep
    reading, because a record names its inputs by file name and hashes
    their bytes, and neither moved.

    Nothing migrates by itself: the resolver reads both layouts, and the
    flat one is not deprecated.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory.

    Returns
    -------
    GeometryMigration
        The files moved and the folders left alone.

    Raises
    ------
    InputArtifactError
        A root with no ``inputs/geometries``: there is no library to move,
        and creating one here would hide a wrong path.
    """
    directory = Path(inputs_dir) / "geometries"
    if not directory.is_dir():
        raise InputArtifactError(
            f"{directory} does not exist, so there is no geometry library to migrate: "
            "the root of a campaign workspace carries inputs/geometries (create the "
            "tree with pyfs-workspace init), and the path given holds none.",
            kind="geometry",
            artifact_id=None,
        )
    entries = sorted(directory.iterdir())
    kept = tuple(entry.name for entry in entries if entry.is_dir())
    created: set[Path] = set()
    moved: list[tuple[Path, Path]] = []
    for entry in entries:
        # THE LIBRARY'S OWN README IS NOT A GEOMETRY and is left where it is.
        # `init` writes one here (PFS-2032.07), and without this line the
        # migration filed the instruction page under `geometries/README/`,
        # which both hides the page from the person it was written for and
        # creates a folder the resolver then reads as a geometry's home.
        if not entry.is_file() or is_sidecar(entry.name) or entry.name == GEOMETRIES_README:
            continue
        folder = directory / entry.stem
        if folder.exists() and folder not in created:
            continue
        if folder not in created:
            folder.mkdir()
            created.add(folder)
        sidecars = [directory / (entry.stem + suffix) for suffix in SIDECAR_SUFFIXES]
        for source in (entry, *[sidecar for sidecar in sidecars if sidecar.is_file()]):
            target = folder / source.name
            source.rename(target)
            moved.append((source, target))
    return GeometryMigration(moved=tuple(moved), kept=kept)
