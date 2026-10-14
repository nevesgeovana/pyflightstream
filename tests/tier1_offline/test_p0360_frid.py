"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import ast
import copy
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


TIER1 = REPO / "tests" / "tier1_offline"


def _helper_shape(node: ast.FunctionDef) -> str:
    node = copy.deepcopy(node)
    node.name = "helper"
    node.returns = None
    if ast.get_docstring(node) is not None:
        node.body = node.body[1:]
    for child in ast.walk(node):
        if isinstance(child, ast.arg):
            child.annotation = None
    return ast.dump(node, include_attributes=False)


def _helper_duplicates(source: str, support: str) -> list[str]:
    helpers = {
        node.name: _helper_shape(node)
        for node in ast.parse(support).body
        if isinstance(node, ast.FunctionDef)
    }
    return [
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef)
        and (node.name in helpers or _helper_shape(node) in helpers.values())
    ]


def test_shared_helpers_have_one_definition():
    """P0360-RV-A1 (NFR-39): renamed or identically named local copies are refused."""
    support = (REPO / "tests/support_helpers.py").read_text(encoding="utf-8")
    duplicates = {
        path.name: found
        for path in TIER1.rglob("*.py")
        if (found := _helper_duplicates(path.read_text(encoding="utf-8"), support))
    }
    assert not duplicates
    control = "def file_sha256(path):\n    return 'wrong'\n"
    assert _helper_duplicates(control, support) == ["file_sha256"]
    copied = next(n for n in ast.parse(support).body if isinstance(n, ast.FunctionDef))
    copied.name = "_planted_copy"
    assert _helper_duplicates(ast.unparse(copied), support) == ["_planted_copy"]
