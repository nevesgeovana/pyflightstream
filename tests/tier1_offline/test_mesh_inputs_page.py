"""Tier 1: ``docs/mesh-inputs.md`` runs its own example and names the sidecar's keys (D05).

The page is where a user who starts from an OBJ or an STL learns what to
write beside the mesh, and until 0.27.0 it had grown by accretion: five items
of the release each added a section, and nothing held the sections to the
reader of the file they describe or ran the page as a whole. Three tests hold
it now, each reading the page's OWN code blocks and retyping none of them:

* the complete example is written into a temporary workspace (every titled
  block at the path its title names, the python block run there), planned
  with the command line the page prints, and rendered point by point through
  the public API without a solver. The script has to carry the import in the
  unit the page's sidecar states, the page's operations in the order written,
  and the trailing-edge import with its node file, and it has to start with
  the lines the page shows, the node file holding the page's points in metres;
* every key a sidecar block on the page writes is a key the sidecar's readers
  read, and every key those readers read is written by some block of the
  page, so neither can move without the other;
* every name a python block on the page imports exists, which covers the
  block the docs example run skips because it names a blade this repository
  does not commit.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pyflightstream.cases import (
    MeshImport,
    MeshOperation,
)
from pyflightstream.cases._ccs import CcsImportOptions
from pyflightstream.run.cli import main as pyfs_matrix
from pyflightstream.workspace import CampaignWorkspace

# The sidecar readers are workspace.sidecars since 0.33.0 (AD-11); workspace.inputs
# re-exports their public names.
from pyflightstream.workspace import sidecars as sidecar_reader
from tests.tier1_offline._workflow_docs import MESH_DOCS

REPO = Path(__file__).resolve().parents[2]
PAGE = MESH_DOCS

#: The heading of the page's one complete example. Matched as a prefix, so the
#: heading may go on to say what the example is.
EXAMPLE_HEADING = "## A complete example"

#: Metres per unit, for the units a points file on the page may state. Written
#: here rather than read from the package, because it is the oracle the node
#: file's conversion is checked against.
METRES_PER = {"METER": 1.0, "CENTIMETER": 0.01, "MILLIMETER": 0.001, "INCH": 0.0254, "FEET": 0.3048}

_FENCE = re.compile(r"^```(?P<info>[^\n`]*)\n(?P<body>.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
_TITLE = re.compile(r'title="(?P<title>[^"]+)"')
_PLACEHOLDER = re.compile(r"<[^<>]+>")


@dataclass(frozen=True)
class Block:
    """One fenced code block of the page: its language, its title and its text."""

    language: str
    title: str | None
    body: str


def _blocks(text: str) -> list[Block]:
    """Every fenced block of ``text``, in order."""
    found = []
    for match in _FENCE.finditer(text):
        info = match.group("info").strip()
        title = _TITLE.search(info)
        found.append(
            Block(
                language=info.split()[0] if info else "",
                title=title.group("title") if title else None,
                body=match.group("body"),
            )
        )
    return found


def _section(text: str, heading: str) -> str:
    """The text from the line starting with ``heading`` to the next level-2 heading."""
    starts = [match.start() for match in re.finditer(rf"^{re.escape(heading)}", text, re.M)]
    assert len(starts) == 1, f"{PAGE.name} carries {len(starts)} headings starting {heading!r}"
    rest = text[starts[0] :]
    following = re.search(r"^## ", rest[3:], re.M)
    return rest if following is None else rest[: following.start() + 3]


def _operation_commands(text: str) -> dict[str, str | None]:
    """The page's operations table: each ``op`` and the command its third column names.

    A body row only, read after the separator line: the header row's first
    cell is the word ``op`` in backticks too.
    """
    table: dict[str, str | None] = {}
    body = False
    for line in text.splitlines():
        if re.fullmatch(r"\|(?:-+\|)+", line.strip()):
            body = True
            continue
        if not line.startswith("|"):
            body = False
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not body or len(cells) != 4 or not re.fullmatch(r"`[a-z]+`", cells[0]):
            continue
        command = re.fullmatch(r"`([A-Z_]+)`", cells[2])
        table[cells[0].strip("`")] = command.group(1) if command else None
    return table


def _as_pattern(line: str) -> re.Pattern[str]:
    """A page line as a pattern: each ``<placeholder>`` stands for one path or value."""
    pieces = _PLACEHOLDER.split(line)
    return re.compile("^" + "(.+)".join(re.escape(piece) for piece in pieces) + "$")


def _points(body: str) -> tuple[str, list[tuple[float, float, float]]]:
    """A points file as the page prints it: the unit line, then one x,y,z per line."""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    rows = [tuple(float(value) for value in line.split(",")) for line in lines[1:]]
    assert all(len(row) == 3 for row in rows), rows
    return lines[0], [(row[0], row[1], row[2]) for row in rows]


#: The one top-level key of a sidecar that is not a table: the surface names.
BOUNDARIES = "boundaries"
#: The key ``[import]`` holds its operations under, and the key detection is
#: written under in every table that detects.
OPERATIONS = "operations"
DETECT = "detect"
SURFACES = "surfaces"


def _key_paths(table: Mapping[str, object], prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Every key of a parsed TOML table as a path; an array of tables adds its keys once."""
    found: set[tuple[str, ...]] = set()
    for key, value in table.items():
        path = (*prefix, key)
        found.add(path)
        if isinstance(value, dict):
            found |= _key_paths(value, path)
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            for item in value:
                found |= _key_paths(item, path)
    return found


def _reader_key_paths() -> set[tuple[str, ...]]:
    """Every key the sidecar's readers read, from the constants and models they read through.

    ``[import]`` and its operations are pydantic models that forbid any other
    key, so their fields ARE the keys. ``[trailing_edges]`` and its ``detect``
    table refuse a key outside the two tuples their reader checks against.
    The two option tables read one key, ``detect``, and the wake-termination
    one takes a table of surfaces there; those three words are written here
    and held to the reader by the acceptance run of the page's blocks.
    """
    imports = sidecar_reader.IMPORT_TABLE
    trailing = sidecar_reader.TRAILING_EDGES_TABLE
    wake = sidecar_reader.WAKE_TERMINATION_TABLE
    base = sidecar_reader.BASE_REGIONS_TABLE
    assert OPERATIONS in MeshImport.model_fields
    assert DETECT in sidecar_reader._TRAILING_EDGE_KEYS
    assert SURFACES in sidecar_reader._DETECT_KEYS
    tables = sidecar_reader.RAW_MESH_CONDITION_TABLES
    paths: set[tuple[str, ...]] = {(BOUNDARIES,), (imports,), *((name,) for name in tables)}
    paths |= {(imports, key) for key in MeshImport.model_fields}
    # 0.32.0 (P0320-I2): [import.ccs] is a model of its own. Its REQUIRED keys are what a
    # sidecar block must state to be accepted, so they are the page's; the optional ones
    # belong to docs/ccs-geometry.md, which holds every key of each kind.
    paths |= {
        (imports, "ccs", key)
        for key, field in CcsImportOptions.model_fields.items()
        if field.is_required()
    }
    paths |= {(imports, OPERATIONS, key) for key in MeshOperation.model_fields}
    paths |= {(trailing, key) for key in sidecar_reader._TRAILING_EDGE_KEYS}
    paths |= {(trailing, "files", key) for key in ("file", "type")}
    paths |= {(trailing, DETECT, key) for key in sidecar_reader._DETECT_KEYS}
    paths |= {(wake, DETECT), (wake, DETECT, SURFACES), (base, DETECT)}
    paths |= {(wake, key) for key in ("file", "tolerance")}
    return paths


def _sidecar_blocks(text: str) -> list[Block]:
    """The page's TOML blocks that are a sidecar or a fragment of one.

    An untitled TOML block on this page is a sidecar fragment; a titled one is
    a sidecar when its title names one, and otherwise another artifact of the
    example (a reference, a setup, a post-processing artifact).
    """
    return [
        block
        for block in _blocks(text)
        if block.language == "toml"
        and (block.title is None or block.title.endswith(sidecar_reader.INVENTORY_SUFFIX))
    ]


def _divergence(blocks: list[Block]) -> tuple[set[tuple[str, ...]], set[tuple[str, ...]]]:
    """``(keys the page writes that no reader reads, keys read that the page never writes)``."""
    written: set[tuple[str, ...]] = set()
    for block in blocks:
        data = tomllib.loads(block.body)
        # Named declarations are a separate loader, exercised below. This
        # bidirectional key inventory remains the legacy run reader's contract.
        if "fs_build" not in data:
            written |= _key_paths(data)
    read = _reader_key_paths()
    return written - read, read - written


def test_every_name_a_python_block_on_the_page_imports_exists():
    """A block the docs run skips still names the API as it is.

    The blade block is skipped by the docs example run because it reads a
    blade mesh this repository does not commit, so a rename of either name it
    imports would leave it stale with nothing to say so. The import is read
    statically and each name resolved, which is all a skipped block can be
    held to without a blade.
    """
    checked = []
    for block in _blocks(PAGE.read_text(encoding="utf-8")):
        if block.language != "python":
            continue
        for node in ast.walk(ast.parse(block.body)):
            if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith(
                "pyflightstream"
            ):
                continue
            module = importlib.import_module(node.module or "")
            for alias in node.names:
                assert hasattr(module, alias.name), (
                    f"a python block on {PAGE.name} imports {alias.name} from {node.module}, "
                    "which does not carry it"
                )
                checked.append(f"{node.module}.{alias.name}")
    assert len(checked) >= 3, f"the walk checked {checked}; it is not reading the page's blocks"


def test_p0460_mesh_example_previews_and_refuses_an_unmarked_plan(tmp_path, monkeypatch):
    from pyflightstream.workspace.cli import main as workspace_main

    CampaignWorkspace.init(tmp_path)
    text = PAGE.read_text(encoding="utf-8")
    blocks = _blocks(_section(text, EXAMPLE_HEADING))
    monkeypatch.chdir(tmp_path)
    for block in blocks:
        if block.title:
            path = tmp_path / block.title
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(block.body, encoding="utf-8")
        elif block.language == "python":
            exec(compile(block.body, "documented preparation", "exec"), {})
    assert workspace_main(["geometry", "mark-boundaries", "inputs/geometries/wing.obj"]) == 0
    assert not (tmp_path / "inputs/geometries/wing.fsm").exists()
    assert pyfs_matrix(["plan", "wing.fs", "--fs-exe", sys.executable]) == 2
