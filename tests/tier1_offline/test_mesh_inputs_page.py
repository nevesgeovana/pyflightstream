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
import shlex
import sys
import tomllib
import typing
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyflightstream.cases import MeshImport, MeshOperation, TrailingEdgeMarking, case_at_point
from pyflightstream.cases.matrix import read_matrix
from pyflightstream.cases.workflows import SIMULATION_LENGTH_UNIT, build_script
from pyflightstream.run.cli import main as pyfs_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace import inputs as sidecar_reader
from pyflightstream.workspace.matrix import resolve_matrix

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "docs" / "mesh-inputs.md"

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


def test_the_complete_example_plans_and_renders_the_script_the_page_shows(tmp_path, monkeypatch):
    """The page's example, from its own blocks, through the plan and the render.

    Nothing of the example is written here. Every titled block goes to the
    path its title names under the root of a fresh workspace, the python
    block runs in that root (the docs example run skips it, because it writes
    into its working directory), the plan is the command line the page
    prints, and each point's script is rendered by the public API the run
    uses, with no solver. What is asserted is read off the page as well: the
    unit, the operations and the points from the sidecar and points blocks,
    the operation commands from the page's own table, and the script head and
    node file from the two blocks that show them.
    """
    text = PAGE.read_text(encoding="utf-8")
    blocks = _blocks(_section(text, EXAMPLE_HEADING))
    titled = {block.title: block for block in blocks if block.title}
    programs = [block for block in blocks if block.language == "python"]
    shown = [block for block in blocks if block.language == "text" and not block.title]
    commands = [block for block in shown if block.body.startswith("pyfs-matrix ")]
    heads = [block for block in shown if block.body.startswith("NEW_SIMULATION")]
    nodes = [block for block in shown if block not in commands and block not in heads]
    assert len(programs) == 1, (
        f"the example holds {len(programs)} python blocks, and writes its mesh with one"
    )
    assert (len(commands), len(heads), len(nodes)) == (1, 1, 1), (
        "the example shows the command that plans it, the head of the script and the node "
        f"file, one block each; found {len(commands)}, {len(heads)} and {len(nodes)}"
    )
    sidecars = [title for title in titled if title.endswith(sidecar_reader.INVENTORY_SUFFIX)]
    matrices = [title for title in titled if title.endswith(".fs")]
    assert len(sidecars) == 1 and len(matrices) == 1, sorted(titled)

    workspace = CampaignWorkspace.init(tmp_path / "wing_study")
    monkeypatch.chdir(workspace.root)
    for title, block in titled.items():
        target = workspace.root / title
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(block.body, encoding="utf-8")
    exec(compile(programs[0].body, f"{PAGE.name}, the example's mesh", "exec"), {})

    matrix = workspace.root / matrices[0]
    (row,) = read_matrix(matrix)
    # WHERE THE BUILD IS INSTALLED is machine configuration, which a public
    # page never names: the page says to register it, and this registers one.
    registry = workspace.inputs_dir / "executables.toml"
    registry.write_text(f'"{row.fs_build}" = "{Path(sys.executable).as_posix()}"\n', "utf-8")

    command = shlex.split(commands[0].body.splitlines()[0])
    assert command[:2] == ["pyfs-matrix", "plan"], command
    assert pyfs_matrix(command[1:]) == 0, "the page's plan command did not plan every point READY"

    sidecar = tomllib.loads(titled[sidecars[0]].body)
    folder = sidecars[0].rsplit("/", 1)[0]
    unit, points = _points(titled[f"{folder}/{sidecar['trailing_edges']['file']}"].body)
    operations = sidecar["import"].get("operations", [])
    table = _operation_commands(text)
    assert operations, "the example states no operation, so the order of none is checked"
    expected = [table[operation["op"]] for operation in operations]
    assert all(expected), f"the page's table names no command for {operations}"
    head = [line.rstrip() for line in heads[0].body.splitlines()]
    node_lines = [line.strip() for line in nodes[0].body.splitlines() if line.strip()]

    resolved = resolve_matrix(
        matrix, workspace, name="example", fs_version=row.fs_build, recipes={}
    )
    (case,) = resolved.campaign.sims
    geometry = Path(case.geometry)
    assert case.sweep.values, "the example's row sweeps nothing"
    for value in case.sweep.values:
        script = Script(row.fs_build)
        build_script(case_at_point(case, {case.sweep.type: value}), script)
        lines = [line.replace("\\", "/") for line in script.render().splitlines()]

        # The import, in the unit the page's sidecar states.
        assert lines[:4] == [
            "NEW_SIMULATION",
            "IMPORT",
            f"UNITS {sidecar['import']['units']}",
            f"FILE_TYPE {geometry.suffix[1:].upper()}",
        ], lines[:6]
        assert Path(lines[4].removeprefix("FILE ")).name == geometry.name, lines[4]

        # The operations, in the order written, each emitting the command the
        # page's table names for it.
        at = next(index for index, line in enumerate(lines) if line.startswith("IMPORT_WAKE_"))
        places = []
        cursor = lines.index("CLEAR")
        for operation, emitted in zip(operations, expected, strict=True):
            cursor = next(
                index for index in range(cursor + 1, at) if lines[index].startswith(f"{emitted} ")
            )
            if operation["op"] == "rename":
                assert lines[cursor].split()[-1] == operation["to"], lines[cursor]
            places.append(cursor)
        assert places == sorted(places) and len(set(places)) == len(places), places
        between = [line for line in lines[places[-1] + 1 : at] if line]
        assert between == [f"SET_SIMULATION_LENGTH_UNITS {SIMULATION_LENGTH_UNIT}"], between

        # The trailing-edge import, right after them, with its node file.
        marking = sidecar["trailing_edges"]
        defaults = TrailingEdgeMarking.model_fields
        words = lines[at].split()
        assert words[0] == "IMPORT_WAKE_EDGES_FROM_FILE", words
        assert words[1] == marking.get("type", defaults["edge_type"].default), words
        assert float(words[2]) == marking.get("tolerance", defaults["tolerance"].default), words
        assert words[3] == SIMULATION_LENGTH_UNIT, words
        node_path = script.render().splitlines()[at + 1]
        assert Path(node_path).name == f"{geometry.stem}.wake_nodes.txt", node_path
        written = script.pending_input_files[node_path].splitlines()
        assert written == node_lines, (
            f"the node file the page shows and the one the package writes differ:\n"
            f"page    {node_lines}\npackage {written}"
        )
        assert int(written[0]) == len(points) == script.wake_edge_points, written[:2]
        converted = [tuple(float(v) for v in line.split(",")) for line in written[2:]]
        assert converted == pytest.approx(
            [tuple(METRES_PER[unit] * v for v in point) for point in points]
        ), "the node file does not hold the page's points in metres"

        # And the head of the script is the block the page shows.
        for number, (page_line, rendered) in enumerate(zip(head, lines, strict=False), 1):
            assert _as_pattern(page_line).match(rendered), (
                f"line {number} of the script head the page shows is {page_line!r} and the "
                f"package renders {rendered!r}"
            )
        assert len(lines) > len(head)


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
    paths = {(BOUNDARIES,), (imports,), *((name,) for name in tables)}
    paths |= {(imports, key) for key in MeshImport.model_fields}
    paths |= {(imports, OPERATIONS, key) for key in MeshOperation.model_fields}
    paths |= {(trailing, key) for key in sidecar_reader._TRAILING_EDGE_KEYS}
    paths |= {(trailing, DETECT, key) for key in sidecar_reader._DETECT_KEYS}
    paths |= {(wake, DETECT), (wake, DETECT, SURFACES), (base, DETECT)}
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
        written |= _key_paths(tomllib.loads(block.body))
    read = _reader_key_paths()
    return written - read, read - written


def test_every_sidecar_key_the_page_writes_is_one_the_readers_read_and_back(tmp_path):
    """The page and the sidecar's readers name the same keys, and the page's blocks read.

    Both directions, because each has its own failure: a key on the page that
    no reader reads is a key a user copies and the run then refuses (or, for
    a table the reader skips, ignores in silence), and a key a reader reads
    that the page never writes is a capability nobody can find. The kinds of
    operation are held the same way, against the model's own list. And every
    block is read by the readers themselves, so a value the page shows that
    the reader refuses fails here too.
    """
    text = PAGE.read_text(encoding="utf-8")
    blocks = _sidecar_blocks(text)
    assert len(blocks) >= 5, f"{PAGE.name} holds {len(blocks)} sidecar blocks; the walk is broken"
    unread, unwritten = _divergence(blocks)
    assert not unread, (
        f"{PAGE.name} writes {sorted(unread)} in a sidecar block, and no reader of the sidecar "
        "reads it; correct the page, or teach the reader and this test together"
    )
    assert not unwritten, (
        f"the sidecar's readers read {sorted(unwritten)}, and no sidecar block on {PAGE.name} "
        "writes it; a key a reader takes is a key the page shows"
    )

    kinds = set(typing.get_args(MeshOperation.model_fields["op"].annotation))
    written_kinds = {
        operation["op"]
        for block in blocks
        for operation in tomllib.loads(block.body).get("import", {}).get(OPERATIONS, [])
    }
    assert written_kinds == kinds, (written_kinds, kinds)
    assert set(_operation_commands(text)) == kinds, _operation_commands(text)

    for number, block in enumerate(blocks, 1):
        sidecar = tmp_path / f"block{number}{sidecar_reader.INVENTORY_SUFFIX}"
        sidecar.write_text(block.body, encoding="utf-8")
        data = tomllib.loads(block.body)
        if BOUNDARIES in data:
            sidecar_reader.read_inventory(sidecar)
        sidecar_reader.read_mesh_import(sidecar)
        sidecar_reader.read_raw_mesh_conditions(sidecar)


def test_the_key_comparison_sees_a_divergence_in_either_direction():
    """The companion of the test above, which passes on a page that agrees.

    A comparison that had stopped seeing anything would look the same, so
    both directions are driven: a key no reader reads is reported, and a
    reader key no block writes is reported. The control is the page itself.
    """
    blocks = _sidecar_blocks(PAGE.read_text(encoding="utf-8"))
    assert _divergence(blocks) == (set(), set())
    stray = Block("toml", None, "[trailing_edges]\nangle = 30\n")
    unread, _ = _divergence([*blocks, stray])
    assert unread == {("trailing_edges", "angle")}, unread
    without_tolerance = [
        Block(block.language, block.title, re.sub(r"(?m)^tolerance = .*$", "", block.body))
        for block in blocks
    ]
    _, unwritten = _divergence(without_tolerance)
    assert unwritten == {("trailing_edges", "tolerance")}, unwritten


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
