"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


_SPEC = importlib.util.spec_from_file_location(
    "arch_metrics_under_test", REPO / "scripts" / "arch_metrics.py"
)

assert _SPEC is not None and _SPEC.loader is not None


am = importlib.util.module_from_spec(_SPEC)


sys.modules[_SPEC.name] = am


_SPEC.loader.exec_module(am)


BASELINES = json.loads(
    (REPO / "tests" / "tier1_offline" / "architecture_baselines.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def measured():
    """The tree and the test coupling of this checkout, measured once."""
    return am.measure_repo(REPO)


def _mini(sources: dict[str, str]):
    """A synthetic package: paths relative to src/pyflightstream."""
    return am.Tree({"__init__.py": '"""Root."""\n', **sources})


def test_the_code_line_unit_is_the_lens():
    # P0330-G1: docstrings, comments and blank lines are not code lines.
    text = (
        '"""Module docstring,\n\nthree lines."""\n'
        "# a comment\n"
        "\n"
        "X = (\n"
        "    1,  # trailing\n"
        ")\n"
        "def f():\n"
        '    """Function docstring."""\n'
        "    return X\n"
    )
    assert am.code_lines(text) == 5
    assert am.is_exempt('"""Doc.\n\nSize exemption: a catalogue of one shape.\n"""\n')
    assert not am.is_exempt('"""Doc.\n\nSize exemption:\n"""\n')


def test_cross_package_components_equal_the_baseline(measured):
    # P0330-G3: (a) found == baseline, both ways, so an empty graph cannot pass.
    tree, _ = measured
    assert am.scc_findings(tree, BASELINES["baseline_sccs"]) == []


def test_a_component_that_gains_a_member_is_red(measured):
    # P0330-G3: (a) an import from a module outside a baseline component into
    # it, and a new two-package cycle, are each red (QA-S1-13).
    tree, _ = measured
    baseline = BASELINES["baseline_sccs"]
    cases = [(tree, baseline, baseline[0])] if baseline else []
    # A planted two-package cycle keeps the mutant alive once the baseline is empty.
    cycle = tree.with_changes(
        {
            "qa/p0330_c.py": (
                "import pyflightstream.utils.p0330_d\nimport pyflightstream.versions\n"
            ),
            "utils/p0330_d.py": "def f():\n    import pyflightstream.qa.p0330_c\n",
        }
    )
    planted_component = ["pyflightstream.qa.p0330_c", "pyflightstream.utils.p0330_d"]
    cases.append((cycle, [*baseline, planted_component], planted_component))
    for base, frozen, members in cases:
        assert am.scc_findings(base, frozen) == [], members
        graph = base.graph(("module", "deferred"))
        component = set(members)
        member, outside = next(
            (m, t) for m in sorted(component) for t in sorted(graph[m]) if t not in component
        )
        path = base.path_of[outside]
        planted = base.with_changes(
            {path: base.sources[path] + f"\n\ndef _p0330_mutant():\n    import {member}\n"}
        )
        findings = am.scc_findings(planted, frozen)
        assert any("not in the baseline" in f and outside in f for f in findings), members
        assert any("no longer found" in f for f in findings), members

    pair = tree.with_changes(
        {
            "qa/p0330_a.py": "import pyflightstream.utils.p0330_b\n",
            "utils/p0330_b.py": "def f():\n    import pyflightstream.qa.p0330_a\n",
        }
    )
    assert any("pyflightstream.qa.p0330_a" in f for f in am.scc_findings(pair, baseline))


def test_a_declared_package_order_is_enforced(measured):
    # P0330-G3: (b) inside a package that declares an order a module imports
    # only later modules, at module level and deferred alike, and a module
    # missing from the order fails; the real tree holds its declarations.
    tree, _ = measured
    assert am.order_findings(tree, BASELINES["package_order"]) == []

    package = {
        "cases/__init__.py": "",
        "cases/workflows/__init__.py": "from pyflightstream.cases.workflows import _a, _b\n",
        "cases/workflows/_a.py": "from pyflightstream.cases.workflows._b import X\n",
        "cases/workflows/_b.py": "X = 1\n",
    }
    order = {"pyflightstream.cases.workflows": {"order": ["__init__", "_a", "_b"]}}
    assert am.order_findings(_mini(package), order) == []
    upward = {**package, "cases/workflows/_b.py": "X = 1\ndef f():\n    from . import _a\n"}
    assert any(
        "_b.py" in f and "declared order" in f for f in am.order_findings(_mini(upward), order)
    )
    missing = {**package, "cases/workflows/_c.py": "Y = 2\n"}
    assert any(
        "_c: a module of the package missing" in f for f in am.order_findings(_mini(missing), order)
    )
    assert any("declares no order" in f for f in am.order_findings(_mini(package), {}))
    facade_run = {
        "run/__init__.py": '"""Run."""\nfrom pyflightstream.run._x import f\n',
        "run/_x.py": "def f():\n    pass\n",
    }
    assert any(
        "pyflightstream.run" in f and "declares no order" in f
        for f in am.order_findings(_mini(facade_run), {})
    )


_NINE = {
    "run/records.py": 'ARCHIVE_DIR = "archive"\nARCHIVE_STAMP = "%Y%m%d-%H%M%S"\n',
    "workspace/naming.py": 'ARCHIVE_DIR = "archive"\nARCHIVE_STAMP = "%Y%m%d-%H%M%S"\n',
    "cases/__init__.py": 'FLAG_PHASES = ("control", "geometry", "setup")\n',
    "cases/workflows.py": (
        'FLAG_PHASES = ("control", "geometry", "setup")\n'
        '_UNIT_THAT_NAMES_NO_LENGTH = "OTHER"\n'
        '_SECTION_COMMAND = "NEW_SURFACE_SECTION_DISTRIBUTION"\n'
    ),
    "cases/ccs_wing.py": '_UNIT_THAT_NAMES_NO_LENGTH = "OTHER"\n',
    "post/superfile.py": '_SECTION_COMMAND = "NEW_SURFACE_SECTION_DISTRIBUTION"\n',
    "cases/setup_surfaces.py": '_STABILIZATION = "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION"\n',
    "script/helpers.py": (
        '_STABILIZATION = "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION"\n'
        '_LENGTH_UNIT_COMMAND = "SET_SIMULATION_LENGTH_UNITS"\n'
    ),
    "script/__init__.py": '_LENGTH_UNIT_COMMAND = "SET_SIMULATION_LENGTH_UNITS"\n',
    "cases/matrix.py": 'VELOCITY_KEYS = ("MACH", "TASmps")\n',
    "workspace/flight_condition.py": 'VELOCITY_KEYS = ("MACH", "TASmps")\n',
    "cases/acoustics.py": 'ACOUSTICS_DIR = "acoustics"\n',
    "post/acoustics.py": 'ACOUSTICS_DIR = "acoustics"\n',
    "run/__init__.py": "",
    "workspace/__init__.py": "",
    "post/__init__.py": "",
}


_NINE_NAMES = (
    "ARCHIVE_DIR",
    "ARCHIVE_STAMP",
    "FLAG_PHASES",
    "_UNIT_THAT_NAMES_NO_LENGTH",
    "_SECTION_COMMAND",
    "_STABILIZATION",
    "_LENGTH_UNIT_COMMAND",
    "VELOCITY_KEYS",
    "ACOUSTICS_DIR",
)


def test_one_home_per_literal_holds_on_the_tree(measured):
    # P0330-G6: the pairs found equal the allowlist, both ways (WP2 empties it).
    tree, _ = measured
    assert am.one_home_findings(tree, BASELINES["one_home_allowlist"]) == []


def test_the_nine_pairs_of_v0320_are_always_red():
    # P0330-G6: each of the nine pairs is found, naming both files and lines.
    findings = am.one_home_findings(_mini(_NINE), [])
    assert len(findings) == 9
    for name in _NINE_NAMES:
        assert any(f.startswith(f"{name} = ") and ".py:" in f for f in findings), name


def test_one_home_leaves_an_import_and_another_name_alone():
    # P0330-G6: the clean control; the same value under another name is out
    # of the guard's scope (AD-08 G6).
    imported = {
        "run/__init__.py": "",
        "run/records.py": "from pyflightstream.workspace.naming import ARCHIVE_DIR\n",
        "workspace/__init__.py": "",
        "workspace/naming.py": 'ARCHIVE_DIR = "archive"\n',
        "cases/__init__.py": 'FLAG_PHASES = ("control",)\n',
        "cases/matrix.py": 'PHASES = ("control",)\n',
    }
    assert am.one_home_findings(_mini(imported), []) == []


def test_roots_are_facades_on_the_tree(measured):
    # P0330-G8: tabled roots at their entry, every other root holding nothing
    # beyond docstring, imports, __all__ and a lazy __getattr__, no star import.
    tree, _ = measured
    assert (
        am.facade_findings(tree, BASELINES["facade_lines"], BASELINES["facade_definitions"]) == []
    )


_CLEAN_ROOT = "qa/p0330_pkg/__init__.py"


def test_a_definition_in_a_facade_root_is_red(measured):
    # P0330-G8: in a root absent from the table, a function, a class, a lazy
    # __dir__, a star import and fifty lines of logic that define nothing are
    # each red; a lazy __getattr__ is the one definition a facade may hold
    # (QA-S1-18). The planted clean root keeps the mutants alive whatever the
    # tree's roots become.
    tree, _ = measured
    table, defs = BASELINES["facade_lines"], BASELINES["facade_definitions"]
    base = tree.with_changes({_CLEAN_ROOT: '"""A planted facade."""\nimport os\n\n__all__ = []\n'})
    facades = sorted(p for p in base.roots if p not in table)
    assert _CLEAN_ROOT in facades
    assert am.facade_findings(base, table, defs) == []

    def red(path: str, addition: str) -> list[str]:
        planted = base.with_changes({path: base.sources[path] + addition})
        return [f for f in am.facade_findings(planted, table, defs) if f.startswith(path)]

    logic = "".join(f"_P{i} = {i}\n" for i in range(40))
    logic += "if _P0:\n    _Q = 1\nelse:\n    _Q = 2\n"
    logic += "try:\n    _R = 1\nexcept ValueError:\n    _R = 2\n"
    getattr_only = "\n\ndef __getattr__(name):\n    raise AttributeError(name)\n"
    for facade in facades:
        assert red(facade, "\n\ndef _p0330_helper():\n    return 1\n"), facade
        assert red(facade, "\n\nclass P0330:\n    pass\n"), facade
        assert red(facade, "\n\ndef __dir__():\n    return []\n"), facade
        assert red(facade, "\nfrom pyflightstream._errors import *\n"), facade
        assert any("holds none" in f for f in red(facade, "\n" + logic)), facade
        assert red(facade, getattr_only) == [], facade
