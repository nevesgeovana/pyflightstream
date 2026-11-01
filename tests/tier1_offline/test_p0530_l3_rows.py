"""P0530-L3-ROWS (PFS-2140.023, PFS-2185.04, PFS-2185.05, PFS-2185.08): each node has its L3 row.

A node closed without a ``tests/requirements_l3.csv`` row naming it has no requirement behind it
(PFS-2140.023 closed that way at 0.50.0). Each row names a code path and a test that exist.
"""

from __future__ import annotations

import ast
import csv
import importlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
NODES = ("PFS-2140.023", "PFS-2185.04", "PFS-2185.05", "PFS-2185.08")


def _rows(node: str) -> list[dict[str, str]]:
    with (REPO / "tests" / "requirements_l3.csv").open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["node"] == node]


def _test_exists(spec: str) -> bool:
    path, *names = spec.split("::")
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    scope: list[ast.AST] = [tree]
    for name in names:
        found = [
            child
            for parent in scope
            for child in ast.iter_child_nodes(parent)
            if isinstance(child, (ast.FunctionDef, ast.ClassDef)) and child.name == name
        ]
        if not found:
            return False
        scope = list(found)
    return True


@pytest.mark.requirement("FR-3411")
@pytest.mark.parametrize("node", NODES)
def test_p0530_a_node_has_an_implemented_l3_row_with_a_code_path_and_a_test(node):
    rows = _rows(node)
    assert rows, f"no requirements_l3.csv row names {node}"
    for row in rows:
        assert row["status"] == "implemented", row["uid"]
        module, _, attribute = row["code"].partition(":")
        assert hasattr(importlib.import_module(module), attribute), row["code"]
        assert _test_exists(row["test"]), row["test"]
