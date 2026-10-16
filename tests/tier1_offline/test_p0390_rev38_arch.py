"""P0390-REV38 (NFR-45, PUSH-W12-ARCH-2): no private name crosses the workspace package boundary.

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

#: No crossing is allowed: every helper read from outside the package has a public name.
KNOWN_CROSSINGS: set[tuple[str, str]] = set()


def _imported_module(rel: str, node: ast.ImportFrom) -> str:
    """The absolute module an ``from ... import`` names, a relative one resolved from ``rel``."""
    if node.level == 0:
        return node.module or ""
    package = ["pyflightstream", *rel.removesuffix(".py").split("/")[:-1]]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, node.module] if node.module else base)


def crossings(sources: dict[str, str]) -> set[tuple[str, str]]:
    """Return (module path, private name) read from ``pyflightstream.workspace`` from outside it.

    A relative import is resolved against the importing module's package first, so
    ``from ..workspace import _x`` in ``run/a.py`` is read as the absolute form is.
    """
    found = set()
    for rel, text in sources.items():
        if rel.startswith("workspace/"):
            continue
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = _imported_module(rel, node)
            if module != "pyflightstream.workspace" and not module.startswith(
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


def script_crossings(sources: dict[str, str]) -> set[tuple[str, str]]:
    """Find private attribute use on imported, constructed or annotated Script values."""
    found = set()
    for rel, text in sources.items():
        if rel.startswith("script/"):
            continue
        tree = ast.parse(text)
        types = {"Script"}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and _imported_module(rel, node) == "pyflightstream.script"
            ):
                types.update(
                    alias.asname or alias.name for alias in node.names if alias.name == "Script"
                )
        instances = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.arg)
                and isinstance(node.annotation, ast.Name)
                and node.annotation.id in types
            ):
                instances.add(node.arg)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value.func
                if isinstance(call, ast.Name) and call.id in types:
                    instances.update(t.id for t in node.targets if isinstance(t, ast.Name))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr.startswith("_")
                and isinstance(node.value, ast.Name)
                and node.value.id in instances
            ):
                found.add((rel, node.attr))
    return found


def test_p0420_cases_use_the_public_script_boundary():
    assert script_crossings(_tree()) == set()


def test_p0420_script_attribute_guard_sees_renamed_instances_and_reads():
    planted = {
        "cases/planted.py": "from pyflightstream.script import Script as Builder\n"
        "def build(target: Builder):\n    target._through_the_door = True\n"
        "other = Builder('26.124')\nfiles = other._pending_input_files\n",
    }
    assert script_crossings(planted) == {
        ("cases/planted.py", "_through_the_door"),
        ("cases/planted.py", "_pending_input_files"),
    }
    assert script_crossings({"script/planted.py": planted["cases/planted.py"]}) == set()


def test_the_reparse_helper_has_a_public_name_in_its_home_module():
    """P0390-REV38 (NFR-45, PUSH-W12-ARCH-2): ``_links.is_reparse`` is public."""
    assert callable(_links.is_reparse)
    assert not hasattr(_links, "_is_reparse")
    assert not hasattr(workspace, "_is_reparse")
    assert _links.is_reparse(SRC) is False


def test_no_module_outside_workspace_reads_a_new_private_name_from_it():
    """P0390-REV38 (NFR-45, PUSH-W12-ARCH-2): no crossing exists at all."""
    assert crossings(_tree()) == set()


def test_the_guard_sees_a_planted_private_import():
    """P0390-REV38 (NFR-45, PUSH-W12-ARCH-2): control, a planted private import is found."""
    planted = _tree()
    planted["run/planted.py"] = "from pyflightstream.workspace import _is_reparse\n"
    assert crossings(planted) - KNOWN_CROSSINGS == {("run/planted.py", "_is_reparse")}
    planted["run/planted.py"] = "from pyflightstream.workspace._links import _remove_link as r\n"
    assert crossings(planted) - KNOWN_CROSSINGS == {("run/planted.py", "_remove_link")}


def test_the_guard_resolves_a_planted_relative_import():
    """P0390-REV38 (NFR-45, PUSH-W12-ARCH-2): control, a relative private import is found.

    ``from ..workspace import _x`` and ``from ..workspace._links import _x`` in ``run/``
    are the absolute imports written relatively and are found; a relative import of
    another package, and one inside ``workspace`` itself, stay allowed.
    """
    planted = _tree()
    planted["run/planted.py"] = "from ..workspace import _is_reparse\n"
    assert crossings(planted) - KNOWN_CROSSINGS == {("run/planted.py", "_is_reparse")}
    planted["run/planted.py"] = "from ..workspace._links import _remove_link\n"
    assert crossings(planted) - KNOWN_CROSSINGS == {("run/planted.py", "_remove_link")}
    planted["run/planted.py"] = "from .. import workspace\nfrom . import _alias\n"
    assert crossings(planted) - KNOWN_CROSSINGS == set()
    del planted["run/planted.py"]
    planted["workspace/planted.py"] = "from ._links import _remove_link\n"
    assert crossings(planted) - KNOWN_CROSSINGS == set()
