"""Tier 1, 0.33.0 WP4 (AD-12): ``cases/workflows`` is a package with a guarded order.

The module ``cases/workflows.py`` became the package ``cases/workflows/``:
a facade root over private modules cut along the measured clusters. Its
modules import one another only downward, in the order declared in the
``package_order`` entry of ``architecture_baselines.json`` (G3(b) of AD-08),
module-level and deferred imports alike, with the vocabulary as the leaf.
Each test here carries the requirement id P0330-WORKFLOWS-ORDER; the
measuring code is ``scripts/arch_metrics.py``, loaded by path, so a verdict
here and a guard verdict are one reader's.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "arch_metrics_workflows_order", REPO / "scripts" / "arch_metrics.py"
)
am = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = am
_SPEC.loader.exec_module(am)

BASELINES = json.loads(
    (REPO / "tests" / "tier1_offline" / "architecture_baselines.json").read_text(encoding="utf-8")
)
PACKAGE = "pyflightstream.cases.workflows"
DECLARED = BASELINES["package_order"][PACKAGE]["order"]


@pytest.fixture(scope="module")
def tree():
    """The tree of this checkout, measured once."""
    return am.measure_repo(REPO)[0]


def _members(tree) -> set[str]:
    prefix = "cases/workflows/"
    return {
        p.removeprefix(prefix).removesuffix(".py")
        for p in tree.paths
        if p.startswith(prefix) and "/" not in p.removeprefix(prefix)
    }


def test_the_package_declares_every_module_root_first_and_vocabulary_last(tree):
    # P0330-WORKFLOWS-ORDER: the declared order names every module of the
    # package exactly once, the facade root first and the leaf vocabulary
    # last, and the tree keeps it (no module imports one before it).
    assert "cases/workflows.py" not in tree.paths, "the module is back beside the package"
    members = _members(tree)
    assert len(members) >= 8, members
    assert sorted(DECLARED) == sorted(members), set(DECLARED) ^ members
    assert len(DECLARED) == len(set(DECLARED))
    assert DECLARED[0] == "__init__" and DECLARED[-1] == "_vocabulary", DECLARED
    assert am.package_order_findings(tree, PACKAGE, DECLARED, []) == []


@pytest.mark.parametrize(
    ("importer", "line"),
    [
        # The leaf reaching for the table at module level.
        ("_vocabulary", "from pyflightstream.cases.workflows._registry import build_script\n"),
        # A row reader reaching for a builder inside a function body.
        ("_rows", "def _p0330():\n    from pyflightstream.cases.workflows import _steady\n"),
        # A relative import of the facade from a private module.
        ("_conventions", "from . import build_script\n"),
    ],
)
def test_an_upward_import_inside_the_package_is_red(tree, importer, line):
    # P0330-WORKFLOWS-ORDER: a module importing one before it in the declared
    # order fails the guard, at module level and deferred alike, while the
    # unmutated tree (the control) is green.
    assert am.package_order_findings(tree, PACKAGE, DECLARED, []) == []
    path = f"cases/workflows/{importer}.py"
    planted = tree.with_changes({path: tree.sources[path] + "\n" + line})
    findings = am.package_order_findings(planted, PACKAGE, DECLARED, [])
    assert any(path in f and "declared order" in f for f in findings), findings


def test_a_new_module_of_the_package_must_join_the_order(tree):
    # P0330-WORKFLOWS-ORDER: a module added to the package and not declared is
    # red, so the order cannot be bypassed by a new file; the guard of the
    # whole tree (G3(b)) refuses the same.
    planted = tree.with_changes({"cases/workflows/_p0330_new.py": "def f():\n    return 1\n"})
    findings = am.package_order_findings(planted, PACKAGE, DECLARED, [])
    assert any("_p0330_new: a module of the package missing" in f for f in findings), findings
    assert am.order_findings(tree, BASELINES["package_order"]) == []
    assert any("declares no order" in f for f in am.order_findings(tree, {}))


def test_the_root_is_a_facade_and_the_table_is_one_object(tree):
    # P0330-WORKFLOWS-ORDER: the root holds nothing beyond its docstring,
    # imports and __all__ (G8), and the run-type table the root exports is the
    # object the readers below the builders consult, in the table's order.
    root = tree.sources["cases/workflows/__init__.py"]
    assert am.facade_excess(root) == 0
    assert am.root_definitions(root) == []
    from pyflightstream.cases import workflows
    from pyflightstream.cases.workflows import _conventions, _registry

    assert workflows.WORKFLOWS is _conventions.WORKFLOWS is _registry.WORKFLOWS
    # The order of the entries as the registry's literal states them.
    # A key is a string or a vocabulary constant (QSTEADY_ROTOR).
    stated = [
        key.value if isinstance(key, ast.Constant) else getattr(workflows, key.id)
        for node in ast.walk(ast.parse(tree.sources["cases/workflows/_registry.py"]))
        if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Dict)
        for key in node.value.keys
        if isinstance(key, (ast.Constant, ast.Name))
    ]
    assert list(workflows.WORKFLOWS) == stated
    assert len(stated) >= 2


def test_every_module_of_the_package_is_within_the_lens_and_deep(tree):
    # P0330-WORKFLOWS-ORDER: each module of the package is at most 1000 code
    # lines (so none enters the size table) and each private module is deep.
    for member in sorted(_members(tree)):
        path = f"cases/workflows/{member}.py"
        lines = tree.module_code_lines[path]
        assert lines <= am.SOFT_LINES, (path, lines)
        assert path not in BASELINES["module_code_lines"], path
        if member != "__init__":
            assert lines >= am.DEEP_MIN_LINES, (path, lines)
            assert am.top_level_defs(tree.sources[path]) >= am.DEEP_MIN_DEFS, path
