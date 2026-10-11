"""P0390-REV38 (NFR-45 R3, PUSH-W12-ARCH-2): no private name crosses the workspace package boundary.

The 0.38.0 package re-exported ``_is_reparse`` from ``pyflightstream.workspace`` for
the helpers that had moved out of ``storage.py``. The helper now has a public name
in its home module (``workspace/_links.py``) and the package root re-exports no
private name of it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pyflightstream
from pyflightstream import workspace
from pyflightstream.workspace import _links

SRC = Path(pyflightstream.__file__).parent

#: No crossing is allowed: the three script-comparison helpers have public names.
KNOWN_CROSSINGS: set[tuple[str, str]] = set()


def crossings(sources: dict[str, str]) -> set[tuple[str, str]]:
    """Return (module path, private name) read from ``pyflightstream.workspace`` from outside it."""
    found = set()
    for rel, text in sources.items():
        if rel.startswith("workspace/"):
            continue
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.ImportFrom) or node.level != 0 or node.module is None:
                continue
            if node.module != "pyflightstream.workspace" and not node.module.startswith(
                "pyflightstream.workspace."
            ):
                continue
            found |= {
                (rel, alias.name)
                for alias in node.names
                if alias.name.startswith("_") and not alias.name.startswith("__")
            }
    return found


def _tree() -> dict[str, str]:
    return {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in SRC.rglob("*.py")
    }


def test_the_reparse_helper_has_a_public_name_in_its_home_module():
    """P0390-REV38 (NFR-45 R3, PUSH-W12-ARCH-2): ``_links.is_reparse`` is public."""
    assert callable(_links.is_reparse)
    assert not hasattr(_links, "_is_reparse")
    assert not hasattr(workspace, "_is_reparse")
    assert _links.is_reparse(SRC) is False


def test_no_module_outside_workspace_reads_a_new_private_name_from_it():
    """P0390-REV38 (NFR-45 R3, PUSH-W12-ARCH-2): no crossing exists at all."""
    assert crossings(_tree()) == set()


def test_the_guard_sees_a_planted_private_import():
    """P0390-REV38 (NFR-45 R3, PUSH-W12-ARCH-2): control, a planted private import is found."""
    planted = _tree()
    planted["run/planted.py"] = "from pyflightstream.workspace import _is_reparse\n"
    assert crossings(planted) - KNOWN_CROSSINGS == {("run/planted.py", "_is_reparse")}
    planted["run/planted.py"] = "from pyflightstream.workspace._links import _remove_link as r\n"
    assert crossings(planted) - KNOWN_CROSSINGS == {("run/planted.py", "_remove_link")}
