"""P0400-FFPROOF: the migration table of the far-field signatures (FR-457 R5, FR-458 R1).

``docs/upgrading.md`` must give, under 0.40.0, the old-to-new table of every
far-field signature that changed. The old side is the 0.39.0 surface captured
from the release tag (``data/p0400_farfield_signatures_0390.json``: every
public function of ``farfield`` and the retired ``post.dataset_to_points``,
written by ``ast.unparse`` of its arguments and return annotation); the new
side is read here, the same way, from the sources of this tree. The table
must hold exactly the signatures that changed, each beside the one that
replaces it as the code defines it today.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

import pyflightstream.farfield as ff
from pyflightstream._retired_names import RETIRED_ATTRIBUTES

REPO = Path(__file__).resolve().parents[2]
FARFIELD = REPO / "src" / "pyflightstream" / "farfield"
SNAPSHOT = json.loads(
    (Path(__file__).parent / "data" / "p0400_farfield_signatures_0390.json").read_text("utf-8")
)
_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*$")
_PIPE = "\x00"


def _text(node: ast.FunctionDef, owner: str | None = None) -> str:
    """A signature as the snapshot writes it: name, unparsed arguments, return annotation."""
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    head = f"{owner}.{node.name}" if owner else node.name
    return f"{head}({ast.unparse(node.args)}){returns}"


def _current() -> dict[str, str]:
    """Every public function of ``farfield`` and every public method of its classes, today."""
    out: dict[str, str] = {}
    for path in sorted(FARFIELD.glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and node.name in ff.__all__:
                out[node.name] = _text(node)
            elif isinstance(node, ast.ClassDef) and node.name in ff.__all__:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        out[f"{node.name}.{item.name}"] = _text(item, node.name)
    return out


def _table() -> dict[str, str]:
    """The rows of the far-field signature table of the 0.40.0 section, old to new."""
    page = (REPO / "docs" / "upgrading.md").read_text(encoding="utf-8")
    section = page.split("\n## 0.40.0\n", 1)[1].split("\n## ", 1)[0]
    assert "### Far-field signatures" in section, "the 0.40.0 section has no signature table"
    block = section.split("### Far-field signatures", 1)[1].split("\n### ", 1)[0]
    rows: dict[str, str] = {}
    for line in block.splitlines():
        # A pipe inside a signature is escaped so the table keeps two cells.
        match = _ROW.match(line.replace("\\|", _PIPE))
        if match:
            old, new = (match.group(n).replace(_PIPE, "|").strip() for n in (1, 2))
            assert old not in rows, f"two rows for {old}"
            rows[old] = new
    return rows


def _changed() -> dict[str, str]:
    """The 0.39.0 signatures whose function is gone or now reads differently, by name."""
    now = _current()
    out = {}
    for dotted, old in SNAPSHOT["signatures"].items():
        name = dotted.rsplit(".", 1)[1]
        if dotted.startswith("pyflightstream.post.") or now.get(name) != old:
            out[dotted] = old
    return out


@pytest.mark.requirement("FR-457")
def test_p0400_ffproof_the_table_lists_every_changed_signature_and_no_other():
    """P0400-FFPROOF (FR-457 R5): one row per changed 0.39.0 signature, the old text exact."""
    changed = _changed()
    assert len(changed) >= 18, "the snapshot no longer sees the numpy change"
    rows = _table()
    assert set(rows) == set(changed.values()), (
        sorted(set(changed.values()) - set(rows)),
        sorted(set(rows) - set(changed.values())),
    )
    unchanged = set(SNAPSHOT["signatures"].values()) - set(changed.values())
    assert not unchanged & set(rows), "an unchanged signature has a row"


@pytest.mark.requirement("FR-457")
def test_p0400_ffproof_each_new_side_is_the_signature_the_code_defines():
    """P0400-FFPROOF (FR-457 R5): the new cell is today's signature of the replacement.

    A name kept is written with its own new signature; a retired name with the
    signature of the replacement its refusal names; a removed name says so,
    naming where it went.
    """
    now = _current()
    by_old = {old: dotted for dotted, old in _changed().items()}
    for old, cell in _table().items():
        dotted = by_old[old]
        module, _, name = dotted.rpartition(".")
        if dotted in RETIRED_ATTRIBUTES:
            message = RETIRED_ATTRIBUTES[dotted].new
            if "ITACA" in message:
                assert cell.startswith("removed") and "ITACA" in cell, (old, cell)
                continue
            new = cell.strip("`")
            target = new.split("(", 1)[0]
            assert target in message, (old, cell, message)
            assert now.get(target) == new, (target, new, now.get(target))
            continue
        assert module == "pyflightstream.farfield", dotted
        assert cell == f"`{now[name]}`", (old, cell, now[name])


@pytest.mark.requirement("FR-458")
def test_p0400_ffproof_the_migration_page_names_both_removed_functions_and_why():
    """P0400-FFPROOF (FR-458 R1): ``docs/upgrading.md`` itself, the release and the reason."""
    page = (REPO / "docs" / "upgrading.md").read_text(encoding="utf-8")
    section = page.split("\n## 0.40.0\n", 1)[1].split("\n## ", 1)[0]
    assert "farfield.rothalpy" in section and "farfield.irreversible_deficit" in section
    assert "ITACA" in section and "total enthalpy" in section and "entropy" in section
    assert "removed in 0.40.0" in section
