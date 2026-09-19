"""Tier-1 siblings use their package name without modifying the import path."""

import ast
from pathlib import Path


def test_sibling_imports_are_package_qualified_without_path_prepends():
    directory = Path(__file__).parent
    siblings = {path.stem for path in directory.glob("*.py")}
    found = []
    for path in sorted(directory.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in siblings:
                found.append(f"{path.name}:{node.lineno}: unqualified sibling import")
            elif isinstance(node, ast.Import):
                if any(alias.name in siblings for alias in node.names):
                    found.append(f"{path.name}:{node.lineno}: unqualified sibling import")
            elif isinstance(node, ast.Call) and ast.unparse(node.func) == "sys.path.insert":
                argument = ast.unparse(node)
                if "__file__" in argument or "tier1_offline" in argument:
                    found.append(f"{path.name}:{node.lineno}: sibling sys.path prepend")
    assert not found, "Use tests.tier1_offline sibling imports:\n" + "\n".join(found)
