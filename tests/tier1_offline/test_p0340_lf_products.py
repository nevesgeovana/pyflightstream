"""Tier 1, 0.34.0: every text file the package writes has LF line ends, through one route (NFR-32).

Pipeline role: quality gate on the one write route ``pyflightstream._textio``, on the
writers under ``src/`` that must go through it, and on the products and emitted
scripts a campaign leaves.

Marker P0340-LF-PRODUCTS, requirement NFR-32. A file written in text mode gets CRLF
on Windows and LF on Linux, so the same campaign posted on two platforms gave two
byte sequences. The package now writes every text file with LF (R1), through
``pyflightstream._textio`` (R2); a campaign posted with text mode forced to write
CRLF, as Windows does, holds no CR byte in any product or emitted script (R3); the
parity script compares 0.33.0 with the CR before LF removed and counts the CR in
the release (R4); the writers that produced CRLF are listed in RPT-140 (R7).

The guard (:func:`text_write_bypasses`) reads the SYNTAX of every module under
``src/`` and refuses a text write that does not go through the route: a
``write_text``, an ``open`` in a text writing mode (the builtin's, ``io``'s,
``builtins``' or ``codecs``'), a ``csv`` writer, a pandas ``to_csv`` that states
no LF line terminator, a ``write_bytes`` or an ``os.write`` of text encoded on the
spot, a ``TextIOWrapper``, a text ``os.fdopen`` or temporary file. Its control
plants twenty-three bypasses and requires each to be caught
(:func:`guard_control`, ``caught 23 of 23``), and the clean forms to pass. What it
does not read: the forms of :data:`UNCOVERED`, each with its reason; a binary write
of bytes it cannot see are text (a byte-exact copy, a workbook); and the source of the
programs the solver runs, which are checked as text by :func:`program_bypasses` on
their rendered form.

What this does NOT prove: that the solver reads an LF script. The licensed probes
of RPT-070 found that line ends change nothing in the disc profile file, and the
licensed runs of 0.34.0 are the confirmation (NFR-32 R6).
"""
# The evidence line of this requirement cites this module (docs/srs/nonfunctional-requirements.md):
# NFR-32.

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest

from pyflightstream import _textio

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "pyflightstream"
ROUTE = "_textio.py"
_TEXT_FLAGS = set("wax+")

#: The files of a campaign folder the PACKAGE writes (the others are the builders' recorded inputs).
PACKAGE_WRITTEN = (
    "post/**/*",
    "sims/*/scripts/**/*",
    "runs.json",
    "logs/*",
    "reports/*",
    "archive/*",
    "*.json",
)


def package_written(root: Path) -> list[Path]:
    """The files under a campaign ``root`` that the package writes, sorted, each once."""
    found = {p for pattern in PACKAGE_WRITTEN for p in root.glob(pattern) if p.is_file()}
    return sorted(found)


# --------------------------------------------------------------------------------- the guard


def _aliases(tree: ast.AST) -> dict[str, str]:
    """The names a module binds by import and the dotted name each stands for.

    ``from io import TextIOWrapper as W`` binds ``W`` to ``io.TextIOWrapper``.
    """
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bound[alias.asname] = alias.name
                else:
                    root = alias.name.split(".")[0]
                    bound[root] = root
        elif isinstance(node, ast.ImportFrom):
            origin = "." * node.level + (node.module or "")
            for alias in node.names:
                bound[alias.asname or alias.name] = f"{origin}.{alias.name}"
    return bound


def _dotted(node: ast.expr, aliases: Mapping[str, str]) -> str | None:
    """The dotted name of ``a.b.c`` with its first name resolved through ``aliases``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(aliases.get(node.id, node.id))
    return ".".join(reversed(parts))


def _callee(
    func: ast.expr, aliases: Mapping[str, str] | None = None
) -> tuple[str | None, str | None]:
    """The called name and, for ``a.b(...)``, the name ``a`` when it is a plain name.

    With ``aliases`` an import alias is resolved to what it stands for: ``W(...)`` after
    ``from io import TextIOWrapper as W`` is ``("TextIOWrapper", "io")`` and ``c.open(...)``
    after ``import codecs as c`` is ``("open", "codecs")``.
    """
    aliases = aliases or {}
    if isinstance(func, ast.Name):
        target = aliases.get(func.id)
        if target and "." in target and not target.startswith("."):
            module, _, name = target.rpartition(".")
            return name, module
        return func.id, None
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return func.attr, aliases.get(func.value.id, func.value.id)
        return func.attr, None
    return None, None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _mode_node(call: ast.Call, index: int) -> ast.expr | None:
    if len(call.args) > index:
        return call.args[index]
    return _keyword(call, "mode")


def _text_write_mode(node: ast.expr | None, *, strict: bool) -> bool:
    """True when ``node`` is a text mode that writes; one not readable is ``strict``'s verdict."""
    if node is None:
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "b" not in node.value and bool(_TEXT_FLAGS & set(node.value))
    return strict


def _states_lf(call: ast.Call) -> bool:
    node = _keyword(call, "newline")
    return isinstance(node, ast.Constant) and node.value == "\n"


def _encodes_text(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "encode"
        for n in ast.walk(node)
    )


_ROUTE_MODULE = "pyflightstream._textio"


def _states_lf_terminator(call: ast.Call, aliases: Mapping[str, str] | None = None) -> bool:
    """True when a ``to_csv`` call states LF: ``"\\n"`` or ``LINE_END`` of the route.

    ``LINE_END`` counts only when it provably comes from the route: the attribute of a
    module imported from ``pyflightstream._textio``, or the bare name imported by
    ``from pyflightstream._textio import LINE_END``. A local or foreign one is refused.
    """
    aliases = aliases or {}
    node = _keyword(call, "lineterminator")
    if isinstance(node, ast.Constant):
        return node.value == "\n"
    if node is None:
        return False
    return _dotted(node, aliases) == f"{_ROUTE_MODULE}.LINE_END"


#: The modules whose ``open`` is the builtin text open, mode second (G2 of the deep QA pass).
_BUILTIN_OPEN_BASES = ("io", "builtins")


def _bypass(call: ast.Call, program: bool, aliases: Mapping[str, str] | None = None) -> str | None:
    name, base = _callee(call.func, aliases)
    if name == "write_text" and not (base or "").endswith("_textio"):
        return None if program and _states_lf(call) else "write_text outside the route"
    is_open = (name == "open" and base is None and isinstance(call.func, ast.Name)) or (
        name == "open" and base in _BUILTIN_OPEN_BASES
    )
    if is_open and _text_write_mode(_mode_node(call, 1), strict=True):
        return None if program and _states_lf(call) else "open in a text writing mode"
    if name == "open" and base == "codecs" and _text_write_mode(_mode_node(call, 1), strict=True):
        return "codecs.open in a text writing mode"
    if name == "TextIOWrapper" and base in (None, "io"):
        return None if program and _states_lf(call) else "a TextIOWrapper outside the route"
    if (
        name == "open"
        and isinstance(call.func, ast.Attribute)
        and base not in (*_BUILTIN_OPEN_BASES, "codecs")
    ):
        if _text_write_mode(_mode_node(call, 0), strict=False):
            return None if program and _states_lf(call) else "Path.open in a text writing mode"
    if program:
        return None
    if name == "to_csv" and isinstance(call.func, ast.Attribute):
        if not _states_lf_terminator(call, aliases):
            return "a pandas to_csv that states no LF line terminator"
    if name in ("writer", "DictWriter") and base == "csv":
        return "a csv writer outside the route"
    if name == "write_bytes" and call.args and _encodes_text(call.args[0]):
        return "text encoded and written as bytes"
    data = call.args[1] if len(call.args) > 1 else _keyword(call, "data")
    if name == "write" and base == "os" and data is not None and _encodes_text(data):
        return "text encoded and written by os.write"
    if name == "fdopen" and base == "os" and _text_write_mode(_mode_node(call, 1), strict=False):
        return "os.fdopen in a text writing mode"
    if name in ("NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"):
        if _text_write_mode(_mode_node(call, 0), strict=False):
            return "a temporary file in a text writing mode"
    return None


def text_write_bypasses(
    sources: Mapping[str, str], *, program: bool = False
) -> list[tuple[str, int, str]]:
    """Every text write of ``sources`` (name to text) that does not go through the route.

    ``program`` reads the text of a program the solver runs, which cannot import the
    route: there a ``write_text`` or an ``open`` is allowed when it states ``newline="\\n"``.
    The route module itself is not read, because it is where the writes are.
    """
    found: list[tuple[str, int, str]] = []
    for name, text in sorted(sources.items()):
        if Path(name).name == ROUTE:
            continue
        tree = ast.parse(text)
        aliases = _aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (what := _bypass(node, program, aliases)):
                found.append((name, node.lineno, what))
    return found


def program_bypasses(text: str) -> list[tuple[str, int, str]]:
    """The writes of one rendered solver program that state no LF line end."""
    return text_write_bypasses({"program.py": text}, program=True)


PLANTED = {
    "write_text": 'from pathlib import Path\nPath("x").write_text("a", encoding="utf-8")\n',
    "open w": 'with open("x", "w", encoding="utf-8") as h:\n    h.write("a")\n',
    "Path.open a": 'from pathlib import Path\nwith Path("x").open("a") as h:\n    h.write("a")\n',
    "csv.writer": "import csv\nw = csv.writer(h)\n",
    "csv.DictWriter": 'import csv\nw = csv.DictWriter(h, ["a"])\n',
    "write_bytes of text": 'from pathlib import Path\nPath("x").write_bytes("a".encode("utf-8"))\n',
    "open with a mode it cannot read": "with open(p, mode) as h:\n    h.write(t)\n",
    "os.fdopen w": 'import os\nh = os.fdopen(fd, "w")\n',
    "NamedTemporaryFile w": 'import tempfile\nh = tempfile.NamedTemporaryFile("w")\n',
    "io.open w": 'import io\nh = io.open("x", "w")\n',
    # The five forms the deep QA mutation pass of 0.34.0 wave 2 found the walk blind to.
    "pandas to_csv": "frame.to_csv(p, index=False)\n",
    "codecs.open w": 'import codecs\nh = codecs.open(p, "w", encoding="utf-8")\n',
    "builtins.open w": 'import builtins\nh = builtins.open(p, "w")\n',
    "os.write of text": 'import os\nos.write(fd, t.encode("utf-8"))\n',
    "io.TextIOWrapper": 'import io\nh = io.TextIOWrapper(open(p, "wb"), encoding="utf-8")\n',
    # The forms the LF guard review of 0.34.0 found: where LINE_END comes from, and import aliases.
    "to_csv with a local LINE_END": (
        'LINE_END = "\\r\\n"\nframe.to_csv(p, lineterminator=LINE_END)\n'
    ),
    "to_csv with a foreign LINE_END": (
        "from other import LINE_END\nframe.to_csv(p, lineterminator=LINE_END)\n"
    ),
    "to_csv with the LINE_END of a foreign _textio": (
        "from other import _textio\nframe.to_csv(p, lineterminator=_textio.LINE_END)\n"
    ),
    "aliased TextIOWrapper": (
        'from io import TextIOWrapper as W\nh = W(open(p, "wb"), encoding="utf-8")\n'
    ),
    "aliased codecs.open w": 'import codecs as c\nh = c.open(p, "w", encoding="utf-8")\n',
    "aliased builtins open w": 'from builtins import open as op\nh = op(p, "w")\n',
    "aliased os.write of text": 'import os as o\no.write(fd, t.encode("utf-8"))\n',
    "os.write of text by keyword": 'import os\nos.write(fd, data=t.encode("utf-8"))\n',
}
CLEAN = {
    "the route": 'from pyflightstream import _textio\n_textio.write_text(p, "a")\n',
    "the route handle": (
        'from pyflightstream import _textio\nwith _textio.open_text(p, "a") as h:\n    pass\n'
    ),
    "a read": 'from pathlib import Path\nPath("x").read_text(encoding="utf-8")\nopen("x")\n',
    "a binary write": 'from pathlib import Path\nPath("x").write_bytes(blob)\nopen("x", "wb")\n',
    "a workspace open": "CampaignWorkspace.open(root, naming)\n",
    "a to_csv stating the route's LF": (
        "from pyflightstream import _textio\n"
        "frame.to_csv(p, index=False, lineterminator=_textio.LINE_END)\n"
        'frame.to_csv(p, lineterminator="\\n")\n'
    ),
    "a codecs and a builtins read": (
        'import builtins, codecs\ncodecs.open(p, "r", encoding="utf-8")\nbuiltins.open(p)\n'
    ),
    "an os.write of bytes": "import os\nos.write(fd, blob)\n",
    "a to_csv stating LINE_END imported from the route": (
        "from pyflightstream._textio import LINE_END\nframe.to_csv(p, lineterminator=LINE_END)\n"
    ),
    "a to_csv stating LINE_END of an aliased route module": (
        "import pyflightstream._textio as t\nframe.to_csv(p, lineterminator=t.LINE_END)\n"
    ),
    "an aliased codecs read": 'import codecs as c\nc.open(p, "r", encoding="utf-8")\n',
}

#: Forms the guard deliberately does NOT read, each with the reason. A named list, so that
#: what is left uncovered is written down and not silent; the test below keeps it true.
UNCOVERED = {
    "print to a handle": (
        'print("a", file=h)\n',
        "the handle comes from a write the guard already refuses or from the route, so the "
        "text mode is decided where the handle is opened, not at the print",
    ),
    "numpy.savetxt": (
        "import numpy\nnumpy.savetxt(p, a)\n",
        "its default newline is the one character LF on every platform, so it writes LF "
        "whatever the mode of the file it is given",
    ),
}


def guard_control() -> tuple[int, int]:
    """Plant every bypass and clean form; return (caught, planted), the clean ones must pass."""
    caught = sum(bool(text_write_bypasses({name: text})) for name, text in PLANTED.items())
    clean = [name for name, text in CLEAN.items() if text_write_bypasses({name: text})]
    assert not clean, f"the guard refused clean forms: {clean}"
    return caught, len(PLANTED)


def _sources() -> dict[str, str]:
    return {
        p.relative_to(SRC).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(SRC.rglob("*.py"))
    }


# ------------------------------------------------------------------------------------ tests


def test_every_text_write_under_src_goes_through_the_one_lf_route() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R2: a walk of src/ finds no text write outside _textio."""
    sources = _sources()
    assert len(sources) > 150, "the walk found too few modules to be the package"
    assert ROUTE in sources
    uses = sum("_textio" in text for name, text in sources.items() if name != ROUTE)
    assert uses > 40, "the route has too few users to be the route of the package"
    bypasses = text_write_bypasses(sources)
    assert not bypasses, "text writes outside pyflightstream._textio:\n" + "\n".join(
        f"  {name}:{line}: {what}" for name, line, what in bypasses
    )


def test_a_planted_bypass_of_every_kind_is_caught_and_the_clean_forms_pass() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R2: the control of the guard, caught 23 of 23."""
    caught, planted = guard_control()
    assert planted == 23
    assert caught == planted, f"caught {caught} of {planted}"


def test_the_forms_the_guard_leaves_uncovered_are_named_with_their_reason_and_really_pass() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R2: what the guard does not read is a named list, kept true."""
    assert UNCOVERED, "the list of uncovered forms is empty"
    for name, (text, reason) in UNCOVERED.items():
        assert len(reason) > 40, f"{name}: no reason written down"
        assert text_write_bypasses({name: text}) == [], f"{name} is read by the guard; unlist it"


def test_a_line_end_name_passes_only_when_it_comes_from_the_route() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R2: the same call passes or fails by where LINE_END comes from."""
    call = "frame.to_csv(p, lineterminator={})\n"
    imported = "from pyflightstream._textio import LINE_END\n"
    assert text_write_bypasses({"a": imported + call.format("LINE_END")}) == []
    assert text_write_bypasses({"b": call.format("LINE_END")}), "an unbound LINE_END passed"
    local = 'LINE_END = "\\r\\n"\n' + call.format("LINE_END")
    assert text_write_bypasses({"c": local}), "a local LINE_END passed"
    via_module = "from pyflightstream import _textio\n" + call.format("_textio.LINE_END")
    assert text_write_bypasses({"d": via_module}) == []
    assert text_write_bypasses({"e": "from x import _textio\n" + call.format("_textio.LINE_END")})


def test_the_route_is_a_floor_module_that_imports_nothing_of_the_package() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R2: ``_textio`` imports the standard library only: a floor."""
    tree = ast.parse((SRC / ROUTE).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import points into the package"
            roots.add((node.module or "").split(".")[0])
    assert "pyflightstream" not in roots, roots
    assert roots <= set(sys.stdlib_module_names), roots
    from tests.tier1_offline.test_conventions import _UNDRAWN_FLOOR_MODULES

    assert "_textio" in _UNDRAWN_FLOOR_MODULES
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert len(functions) >= 2


def test_the_route_writes_lf_with_text_mode_forced_to_crlf(tmp_path: Path) -> None:
    """P0340-LF-PRODUCTS, NFR-32 R1: each route function writes no CR where text mode does."""
    from tests.tier1_offline.test_products_snapshot import crlf_text_mode

    with crlf_text_mode():
        plain = tmp_path / "plain.txt"
        plain.write_text("a\nb\n", encoding="utf-8")
        assert b"\r\n" in plain.read_bytes(), "the forcing does not write CRLF: no control"
        _textio.write_text(tmp_path / "text.txt", "a\nb\n")
        _textio.append_text(tmp_path / "text.txt", "c\n")
        with _textio.open_text(tmp_path / "open.txt", "w") as handle:
            handle.write("a\nb\n")
        with _textio.open_text(tmp_path / "table.csv", "w") as handle:
            writer = _textio.csv_writer(handle)
            writer.writerow(["x", "y"])
            writer.writerow([1, 2])
        with _textio.open_text(tmp_path / "dict.csv", "w") as handle:
            dict_writer = _textio.csv_dict_writer(handle, ["x", "y"])
            dict_writer.writeheader()
            dict_writer.writerow({"x": 1, "y": 2})
        _textio.write_csv(tmp_path / "rows.csv", [[1, 2], [3, 4]], header=["x", "y"])
        _textio.write_json(tmp_path / "doc.json", {"a": [1, 2]})
        _textio.write_lines(tmp_path / "lines.txt", ["a", "b"])
        _textio.append_lines(tmp_path / "lines.txt", ["c"])
        with _textio.open_text(tmp_path / "x.txt", "x") as handle:
            handle.write("a\n")
    written = [p for p in tmp_path.iterdir() if p.name != "plain.txt"]
    assert len(written) == 8
    for path in written:
        assert _textio.file_cr_count(path) == 0, path.name
    assert (tmp_path / "text.txt").read_bytes() == b"a\nb\nc\n"
    assert (tmp_path / "table.csv").read_bytes() == b"x,y\n1,2\n"
    assert (tmp_path / "dict.csv").read_bytes() == b"x,y\n1,2\n"
    assert (tmp_path / "doc.json").read_bytes().endswith(b"]\n}\n")
    # append_lines APPENDS: the file holds the two lines written first and the one after.
    assert (tmp_path / "lines.txt").read_bytes() == b"a\nb\nc\n"
    # The instrument can say NO: a CR is counted, in bytes and in the forced CRLF file.
    assert _textio.count_cr(b"a\r\nb\r") == 2
    assert _textio.file_cr_count(plain) == 2
    assert _textio.lf("a\r\nb\rc\n") == "a\nb\nc\n"
    for refused in ("r", "wb", "rb", "r+"):
        with pytest.raises(ValueError):
            _textio.open_text(tmp_path / "never.txt", refused)
    assert not (tmp_path / "never.txt").exists()


def test_the_campaign_sweep_table_a_run_writes_holds_no_cr_with_crlf_forced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0340-LF-PRODUCTS, NFR-32 R1: the sweep table the RUN writes is LF where Windows is CRLF.

    ``campaign_sweep.csv`` is written by the run stage (``write_table``, after the points
    ran), so the campaigns posted above never read it. pandas ends a row with
    ``os.linesep`` unless told otherwise, which is set to CRLF here as Windows has it,
    beside text mode forced to CRLF. The control: under the same forcing a ``to_csv``
    that states no line terminator writes a CR, so the check can fail.
    """
    import pandas as pd

    from pyflightstream.run import SWEEP_TABLE_NAME
    from tests.tier1_offline.test_goal028_hpc_sweep_csv import _run
    from tests.tier1_offline.test_products_snapshot import crlf_text_mode

    monkeypatch.setattr(os, "linesep", "\r\n")
    with crlf_text_mode():
        workspace = _run(tmp_path)
        control = tmp_path / "control.csv"
        pd.DataFrame({"a": [1]}).to_csv(control, index=False)
    data = (workspace.sweep_dir("warm") / SWEEP_TABLE_NAME).read_bytes()
    assert data.count(b"\n") >= 2, data[:200]
    assert _textio.count_cr(data) == 0, data[:200]
    assert _textio.file_cr_count(control) == 2, "the forcing does not reach pandas: no control"


@contextmanager
def bypassed_route() -> Iterator[None]:
    """Plant the defect in the route: a write that states no line end, as 0.33.1 wrote."""

    def plain(path, text, *, encoding="utf-8", errors=None):
        return Path(path).write_text(text, encoding=encoding, errors=errors)

    kept = _textio.write_text
    _textio.write_text = plain
    try:
        yield
    finally:
        _textio.write_text = kept


@pytest.mark.parametrize("name", ["unsteady_rotor", "steady_provenance", "per_revolution_rotor"])
def test_a_campaign_posted_with_text_mode_forced_to_crlf_holds_no_cr_in_any_product(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0340-LF-PRODUCTS, NFR-32 R3: no CR byte in any file the post writes; a bypass plants one."""
    from tests.tier1_offline.test_products_snapshot import (
        CAMPAIGNS,
        FORCE_CRLF_IN_POST,
        pin_environment,
    )

    assert FORCE_CRLF_IN_POST, "the post is not run with text mode forced to CRLF"
    pin_environment(monkeypatch)
    root = CAMPAIGNS[name](tmp_path / "w", monkeypatch)
    products = package_written(root)
    assert len(products) >= 5, f"{name}: the post wrote {len(products)} files"
    crs = [p.relative_to(root).as_posix() for p in products if b"\r" in p.read_bytes()]
    assert crs == [], f"{name}: products hold a CR byte: {crs[:5]}"
    # The control: the same campaign with the route bypassed holds CR, so the test can fail.
    with bypassed_route():
        root2 = CAMPAIGNS[name](tmp_path / "w2", monkeypatch)
        held = [p for p in package_written(root2) if b"\r" in p.read_bytes()]
    assert held, f"{name}: a bypassed route left no CR, so the check above proves nothing"


def test_the_scripts_a_campaign_emits_hold_no_cr_with_text_mode_forced_to_crlf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0340-LF-PRODUCTS, NFR-32 R1, R3: the emitted solver scripts and records hold no CR."""
    from tests.tier1_offline.test_additional_post import (
        POST_ADDITIONAL_TOML,
        a_recorded_campaign,
        a_stub,
        extract,
    )
    from tests.tier1_offline.test_products_snapshot import crlf_text_mode, pin_environment

    pin_environment(monkeypatch)

    def built(folder: Path) -> list[Path]:
        workspace, matrix = a_recorded_campaign(folder, additional=POST_ADDITIONAL_TOML)
        with crlf_text_mode():
            extract(workspace, matrix, a_stub(folder))
        return package_written(Path(workspace.root))

    first = tmp_path / "a"
    first.mkdir()
    written = built(first)
    scripts = [p for p in written if "scripts" in p.parts and p.suffix == ".txt"]
    assert len(scripts) >= 2, [p.name for p in written]
    assert any(p.name == "runs.json" for p in written)
    assert [p.name for p in written if b"\r" in p.read_bytes()] == []
    with bypassed_route():
        second = tmp_path / "b"
        second.mkdir()
        held = [p for p in built(second) if b"\r" in p.read_bytes()]
    assert held, "a bypassed route left no CR in a script or a record: the check proves nothing"


def test_the_programs_the_solver_runs_state_lf_for_every_file_they_write(tmp_path: Path) -> None:
    """P0340-LF-PRODUCTS, NFR-32 R1: the counter and clock programs write with ``newline="\\n"``."""
    from pyflightstream.cases.workflows import UnsteadyExportThreshold
    from pyflightstream.cases.workflows._clock import WALLTIME_CLOCK_TEMPLATE
    from pyflightstream.run._actions_counter import render_count_program, render_program

    threshold = UnsteadyExportThreshold(
        stated_form="iterations",
        stated_value=4.0,
        first_step=4,
        time_iterations=8,
        delta_time_s=0.01,
        step_deg=None,
        rpm=None,
        exports="EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nloads.txt\n",
    )
    programs = {
        "counter": render_program(threshold, interpreter="python"),
        "count only": render_count_program(4, interpreter="python"),
        "clock": WALLTIME_CLOCK_TEMPLATE.format(
            sim="s", state_name="clock.json", stop_name="stop.txt", deadline=10.0, stop_text="X\n"
        ),
    }
    for name, text in programs.items():
        assert "write_text(" in text, f"{name}: the program writes nothing, so the guard reads none"
        assert program_bypasses(text) == [], name
        unstated = text.replace(', newline="\\n"', "")
        assert program_bypasses(unstated), f"{name}: a program with no stated line end passed"
    # The counter, run as the solver runs it: its files hold no CR in any platform's text mode.
    program = tmp_path / "pfs_unsteady_actions.py"
    _textio.write_text(program, programs["counter"])
    for _ in range(2):
        subprocess.run(
            [sys.executable, str(program)],
            cwd=tmp_path,
            check=True,
            timeout=60,
            env=dict(os.environ),
        )
    made = [p for p in tmp_path.iterdir() if p != program and p.is_file()]
    assert len(made) >= 2, [p.name for p in made]
    assert [p.name for p in made if _textio.file_cr_count(p)] == []


def _parity():
    spec = importlib.util.spec_from_file_location(
        "check_parity_lf_under_test", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_parity_script_removes_cr_before_lf_on_the_033_side_and_counts_the_release_cr() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R4: a CRLF-only difference is named NFR-32, any other differs."""
    parity = _parity()
    assert parity.LF_REQUIREMENT == "NFR-32"
    defined = {"NFR-32"}
    base = {"post.log": "a\r\nb\r\n", "kept.csv": "x\n", "changed.csv": "x\r\ny\r\n"}
    release = {"post.log": "a\nb\n", "kept.csv": "x\n", "changed.csv": "x\nz\n"}
    result = parity.compare_texts("post", "file", base, release, defined)
    assert [d["file"] for d in result["differing"]] == ["changed.csv"], result
    assert "requirement" not in result["differing"][0], "a content change must stay unnamed"
    assert result["cr_removed"] == [
        {"file": "changed.csv", "requirement": "NFR-32"},
        {"file": "post.log", "requirement": "NFR-32"},
    ]
    # The release side is NOT normalised: a CR in a release file is a difference and is counted.
    held = parity.compare_texts("post", "file", {"a.csv": "x\n"}, {"a.csv": "x\r\n"}, defined)
    assert [d["file"] for d in held["differing"]] == ["a.csv"]
    raw = {"a.csv": b"x\r\n", "b.csv": b"x\n", "c.png": b"\x89\r\n", "d.log": b"a\rb"}
    assert parity.count_cr_files(raw) == 2
    assert parity.count_cr_files({"b.csv": b"x\n"}) == 0
    assert parity.lf(b"a\r\nb\rc") == b"a\nb\rc"
    assert parity.CONTROLS == 7


def test_the_parity_byte_control_is_caught_alone_over_a_crlf_base() -> None:
    """NFR-32 R4: the planted byte is caught alone though the 0.33 base holds CRLF files.

    The parity run of 2026-10-02 on Windows caught 6 of 7 controls: the post control
    mutated the raw base, so every CRLF product differed beside the victim.
    """
    parity = _parity()
    defined = {"NFR-32"}
    base = {"a/post.log": "a\r\nb\r\n", "b.csv": "x\r\ny\r\n", "c.csv": "z\n"}
    assert parity.text_control("post", "file", base, "\x00", defined) == "a/post.log"
    assert parity.text_control("scripts", "name", base, "PARITY CONTROL\n", defined) == "a/post.log"
    # The control still fails when the comparator is blind: a comparator that names
    # every difference leaves nothing unnamed, so nothing is caught.
    blind = parity.compare_texts
    try:
        parity.compare_texts = lambda *a, **k: {
            "differing": [{"file": "a/post.log", "requirement": "X"}]
        }
        assert parity.text_control("post", "file", base, "\x00", defined) is None
    finally:
        parity.compare_texts = blind


def test_the_snapshot_receipt_judges_line_ends_and_names_its_platform() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R3: this platform's receipt judges line ends and counts 0 CR."""
    from tests.tier1_offline.test_products_snapshot import _platform, snapshot_receipt

    receipt = snapshot_receipt()
    assert receipt["platforms"] == [_platform()]
    assert _platform() in ("linux", "win32")
    assert receipt["line_ends_judged"] is True
    assert receipt["cr_files"] == 0
    assert receipt["differing"] == []
    control = str(receipt["control"]).split()
    assert control[1] == control[3] and int(control[1]) > 0


def test_the_lf_receipt_script_posts_a_campaign_and_writes_the_lines_the_goal_reads(
    tmp_path: Path,
) -> None:
    """P0340-LF-PRODUCTS, NFR-32 R3: lf_products_check.py writes SHA, platform, counts, verdict."""
    out = tmp_path / "lf_products.txt"
    command = [
        sys.executable,
        str(REPO / "scripts" / "lf_products_check.py"),
        "--out",
        str(out),
        "--campaign",
        "unsteady_rotor",
        "--campaign",
        "additional",
        "--allow-dirty",
    ]
    done = subprocess.run(
        command, cwd=REPO, capture_output=True, text=True, timeout=600, env=dict(os.environ)
    )
    data = out.read_bytes()
    assert b"\r" not in data, "the receipt is not LF"
    lines = data.decode("utf-8").splitlines()
    fields = dict(line.split(": ", 1) for line in lines if ": " in line)
    assert lines[0].startswith("SHA: ") and len(lines[0]) == len("SHA: ") + 40
    assert fields["PLATFORM"] in ("linux", "win32")
    assert int(fields["FILES_CHECKED"]) > 0 and int(fields["SCRIPTS_CHECKED"]) > 0
    assert fields["CR_FILES"] == "0"
    assert fields["GUARD_CONTROL"] == "caught 23 of 23"
    assert fields["GUARD_BYPASSES_IN_SRC"] == "0"
    # PASS names a SHA the tree must be at: a tree with changes (a rehearsal) ends in FAIL.
    verdict = "PASS" if fields["TREE_CLEAN"] == "yes" else "FAIL"
    assert lines[-1] == f"LF PRODUCTS: {verdict}"
    assert done.returncode == (0 if verdict == "PASS" else 1), done.stderr[-500:]


def test_the_change_log_fragment_names_the_lf_change_first_in_its_migration() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R5: the migration paragraph names the LF change, citing NFR-32.

    Before the integration the entries are the fragment ``changelog.d/0-34-lf.md``;
    ``scripts/assemble_changelog.py`` then folds its bullets into the change log
    and deletes it, and the release's migration page carries the migration
    paragraph. Whichever form the tree holds is read, and held to the same rule.
    """
    fragment_path = REPO / "changelog.d" / "0-34-lf.md"
    if fragment_path.is_file():
        fragment = fragment_path.read_text(encoding="utf-8")
        section = fragment.split("## Migration", 1)[1]
        first = next(line for line in section.splitlines() if line.startswith("- "))
        assert "LF" in first and "NFR-32" in first
        for line in fragment.splitlines():
            if line.startswith("- "):
                assert "NFR-32" in line, f"a bullet cites no requirement: {line[:60]}"
        assert "no switch" in section.lower()
        return
    # Folded: the first section of the 0.34.0 migration page is the LF change.
    page = (REPO / "docs" / "migrating-to-0.34.0.md").read_text(encoding="utf-8")
    first_heading, first_body = page.split("\n## ", 2)[1].split("\n", 1)
    assert "LF" in first_heading and "NFR-32" in first_body
    assert "no switch" in first_body.lower()
    # Folded: every bullet the fragment carried is in the 0.34.0 section and cites NFR-32.
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    released = changelog.split("\n## [0.34.0]", 1)[1].split("\n## [", 1)[0]
    bullets = [line for line in released.splitlines() if line.startswith("- ")]
    for marker in (
        "`pyflightstream._textio`, the one floor module",
        "`scripts/lf_products_check.py` posts the recorded offline campaigns",
        "RPT-140, the census of the text writers",
        "Every text file the package writes has LF line ends on every platform",
        "The products snapshot judges line ends",
        "`scripts/check_parity.py` compares the post of 0.33.1 with CR before LF removed",
        # The Fixed bullet of the wave-2 fragment 0-34-killw2.md, folded at its merge.
        "The campaign sweep table `campaign_sweep.csv`, which a run writes",
    ):
        carrying = [line for line in bullets if marker in line]
        assert len(carrying) == 1, f"the 0.34.0 section has {len(carrying)} bullets of {marker!r}"
        assert "NFR-32" in carrying[0], f"a bullet cites no requirement: {carrying[0][:60]}"
    # The guard's control the folded bullet names is the one guard_control plants.
    textio = next(line for line in bullets if "`pyflightstream._textio`, the one floor" in line)
    assert "with twenty-three planted bypasses" in textio and len(PLANTED) == 23


def test_the_census_note_lists_the_writers_that_gave_crlf_on_windows() -> None:
    """P0340-LF-PRODUCTS, NFR-32 R7: the census report names its platform and the writers."""
    notes = sorted((REPO / "reports").glob("RPT-140_*.md"))
    assert len(notes) == 1
    text = notes[0].read_text(encoding="utf-8")
    assert "win32" in text and "NFR-32" in text
    listed = [line for line in text.splitlines() if line.startswith("| `")]
    assert len(listed) >= 20, "the census lists too few writers"
    for source in ("post/products.py", "run/_pending.py", "workspace/storage.py"):
        assert source in text, f"the census does not name {source}"
