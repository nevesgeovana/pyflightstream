"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pyflightstream

PACKAGE = Path(pyflightstream.__file__).parent


PRIVATE_SUPPORT = re.compile(r"^- ``(_\w+)``:", re.MULTILINE)


def _package_imports(module: str) -> set[str]:
    """Every pyflightstream module a module imports, at any depth."""
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("pyflightstream."):
                found.add(node.module.removeprefix("pyflightstream."))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("pyflightstream."):
                    found.add(alias.name.removeprefix("pyflightstream."))
    return found


def test_declared_support_modules_import_only_support_modules():
    """Shared support modules cannot depend on higher package layers."""
    listed = set(PRIVATE_SUPPORT.findall(pyflightstream.__doc__ or ""))
    assert listed, "no declared support modules found"
    floors = {path.stem for path in PACKAGE.glob("_*.py") if path.stem != "__init__"}
    for module in sorted(listed):
        reached = _package_imports(module)
        assert reached <= floors, f"{module} imports {sorted(reached - floors)}, above the floor"
