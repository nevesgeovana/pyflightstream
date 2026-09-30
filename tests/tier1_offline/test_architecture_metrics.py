"""Tier 1, 0.33.0 WP0 (AD-08): the architecture guards G1 to G8 and the metrics record.

Each guard is a ratchet over a baseline measured on 2026-09-30 and committed in
``architecture_baselines.json``; each is green on the tree and each is shown
to fire on a planted in-memory mutant, so a guard that reads nothing cannot
pass (QA-S1-11 to QA-S1-19 of the SRS review). The measuring code is
``scripts/arch_metrics.py``, loaded by path; the record under ``reports/`` is
written by the same code and read back here, never regenerated.

Units: module and function size in code lines without docstrings (the
review lens, C1), computed as the goal checker computes it. The function
limits are ruff's C901, PLR0912, PLR0915 and pylint's positional-argument
limit at their defaults.
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
    "arch_metrics_under_test", REPO / "scripts" / "arch_metrics.py"
)
am = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = am
_SPEC.loader.exec_module(am)

BASELINES = json.loads(
    (REPO / "tests" / "tier1_offline" / "architecture_baselines.json").read_text(encoding="utf-8")
)
MUTANT = "\n_P0330_PLANTED_MUTANT = 1\n"


@pytest.fixture(scope="module")
def measured():
    """The tree and the test coupling of this checkout, measured once."""
    return am.measure_repo(REPO)


@pytest.fixture(scope="module")
def records():
    """(first, newest) numbers of the architecture metrics records, and the newest path."""
    found = am.records(REPO / "reports")
    assert found, "no reports/RPT-*_architecture-metrics_*.md record"
    first = am.record_numbers(found[0][1].read_text(encoding="utf-8"))
    newest = am.record_numbers(found[-1][1].read_text(encoding="utf-8"))
    return first, newest, found[-1][1]


def _mini(sources: dict[str, str]):
    """A synthetic package: paths relative to src/pyflightstream."""
    return am.Tree({"__init__.py": '"""Root."""\n', **sources})


def _grow_function(text: str, qualname: str, line: str = "_p0330 = 1") -> str:
    """Insert one statement after the last statement of a function's body."""
    for name, node, _ in am.walk_functions(ast.parse(text)):
        if name == qualname:
            last = node.body[-1]
            lines = text.splitlines(keepends=True)
            indent = " " * last.col_offset
            lines.insert(last.end_lineno, f"{indent}{line}\n")
            return "".join(lines)
    raise AssertionError(f"{qualname} not found")


def _deep_module(code_lines: int, docstring: str = "A planted module.") -> str:
    """A module of exactly ``code_lines`` code lines with two functions."""
    body = [f'"""{docstring}"""', "def first():", "    return 1", "def second():", "    return 2"]
    body += [f"X{i} = {i}" for i in range(code_lines - 4)]
    return "\n".join(body) + "\n"


# ---------------------------------------------------------------- G1 module size


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


def test_module_size_ratchet_holds_on_the_tree(measured, records):
    # P0330-G1: every module over 1000 code lines is in the table or exempt,
    # no entry grew, no entry is stale.
    tree, _ = measured
    _, newest, _ = records
    assert (
        am.size_findings(tree, BASELINES["module_code_lines"], BASELINES["modules_at_freeze"]) == []
    )
    # Non-vacuity: the walk read the tree the record describes.
    assert len(tree.paths) >= max(100, int(0.9 * newest["module_count"]))
    assert sum(tree.module_code_lines.values()) >= 0.9 * newest["code_lines"]
    assert BASELINES["module_code_lines"], "the size table is empty"


def test_module_size_ratchet_refuses_each_planted_mutant(measured):
    # P0330-G1: the mutants of AD-08 G1 and QA-S1-11 are each red.
    tree, _ = measured
    table = BASELINES["module_code_lines"]
    frozen = BASELINES["modules_at_freeze"]
    listed = max(table, key=lambda p: table[p])

    grown = tree.with_changes({listed: tree.sources[listed] + MUTANT})
    assert any(
        f.startswith(f"{listed}: ") and "above its baseline entry" in f
        for f in am.size_findings(grown, table, frozen)
    )

    plain = tree.with_changes({"qa/p0330_big.py": _deep_module(1001)})
    assert any(
        "qa/p0330_big.py" in f and "Size exemption" in f
        for f in am.size_findings(plain, table, frozen)
    )
    exempt = _deep_module(1001, "A planted module.\n\nSize exemption: a catalogue of one shape.\n")
    control = tree.with_changes({"qa/p0330_big.py": exempt})
    assert am.size_findings(control, table, frozen) == []
    too_big = tree.with_changes(
        {"qa/p0330_big.py": exempt + "".join(f"Y{i} = 1\n" for i in range(1000))}
    )
    assert any(
        "qa/p0330_big.py" in f and "hard limit" in f
        for f in am.size_findings(too_big, table, frozen)
    )

    deleted = {k: v for k, v in table.items() if k != listed}
    assert any(
        f.startswith(f"{listed}: ") and "not in the baseline" in f
        for f in am.size_findings(tree, deleted, frozen)
    )
    small = min((p for p in tree.paths if p not in table), key=lambda p: tree.module_code_lines[p])
    stale = {**table, small: 1500, "gone/p0330.py": 1500}
    findings = am.size_findings(tree, stale, frozen)
    assert any(f.startswith(f"{small}: stale") for f in findings)
    assert any(f.startswith("gone/p0330.py: stale") for f in findings)


def test_a_module_created_after_the_freeze_is_deep(measured):
    # P0330-G1: a new module is deep (>= 2 definitions and >= 60 code lines);
    # a package __init__ is not held to it.
    tree, _ = measured
    table, frozen = BASELINES["module_code_lines"], BASELINES["modules_at_freeze"]
    shallow = tree.with_changes({"qa/p0330_one.py": "def only():\n    return 1\n"})
    assert any(
        "qa/p0330_one.py" in f and "deep" in f for f in am.size_findings(shallow, table, frozen)
    )
    deep = tree.with_changes({"qa/p0330_deep.py": _deep_module(60), "qa/p0330_pkg/__init__.py": ""})
    assert am.size_findings(deep, table, frozen) == []


# ---------------------------------------------------------------- G2 function limits


def test_function_ratchets_hold_on_the_tree(measured):
    # P0330-G2: the length table (code lines over 250) and the limits table
    # (ruff and pylint defaults) hold, and neither is empty.
    tree, _ = measured
    assert (
        am.function_findings(tree, BASELINES["function_lines"], BASELINES["function_limits"]) == []
    )
    assert len(tree.functions) >= 2000
    assert BASELINES["function_lines"] and BASELINES["function_limits"]


@pytest.mark.parametrize(
    ("metric", "at_limit", "over_limit"),
    [
        (
            "complexity",
            "def f(x):\n" + "    if x == 0:\n        pass\n" * 9,
            "def f(x):\n" + "    if x == 0:\n        pass\n" * 10,
        ),
        (
            "branches",
            "def f(x):\n" + "    if x:\n        pass\n    else:\n        pass\n" * 6,
            "def f(x):\n"
            + "    if x:\n        pass\n    else:\n        pass\n" * 6
            + "    if x:\n        pass\n",
        ),
        ("statements", "def f():\n" + "    x = 1\n" * 50, "def f():\n" + "    x = 1\n" * 51),
        ("positional", "def f(a, b, c, d, e):\n    pass\n", "def f(a, b, c, d, e, g):\n    pass\n"),
        (
            "positional",
            "class C:\n    def f(self, a, b, c, d, e):\n        pass\n",
            "class C:\n    def f(self, a, b, c, d, e, g):\n        pass\n",
        ),
    ],
)
def test_a_function_at_a_limit_passes_and_one_over_it_is_red(metric, at_limit, over_limit):
    # P0330-G2: the boundary of each limit (QA-S1-12).
    def red(source: str) -> list[str]:
        findings = am.function_findings(_mini({"m.py": source}), {}, {})
        return [f for f in findings if f": {metric} " in f]

    assert red(at_limit) == []
    assert red(over_limit)


def test_the_function_length_floor_is_inclusive():
    # P0330-G2: a function of exactly 250 code lines passes, 251 is red.
    def length_findings(n: int) -> list[str]:
        source = "def f():\n" + "    x = 1\n" * (n - 1)
        return [
            f for f in am.function_findings(_mini({"m.py": source}), {}, {}) if "code lines" in f
        ]

    assert length_findings(am.FUNCTION_FLOOR) == []
    assert length_findings(am.FUNCTION_FLOOR + 1)


def test_function_ratchets_refuse_growth_and_stale_entries(measured):
    # P0330-G2: a listed function one line longer, a new function over a
    # limit in a real module, and a stale entry are each red.
    tree, _ = measured
    lengths, limits = BASELINES["function_lines"], BASELINES["function_limits"]
    key = max(lengths, key=lambda k: lengths[k])
    path, qualname = key.split(":", 1)
    grown = tree.with_changes({path: _grow_function(tree.sources[path], qualname)})
    assert any(
        f.startswith(f"{key}: code lines") for f in am.function_findings(grown, lengths, limits)
    )

    complex_fn = "\n\ndef _p0330_complex(x):\n" + "    if x == 0:\n        pass\n" * 11
    planted = tree.with_changes({"versions.py": tree.sources["versions.py"] + complex_fn})
    assert any(
        "versions.py:_p0330_complex: complexity" in f
        for f in am.function_findings(planted, lengths, limits)
    )

    stale = {**limits, "versions.py:_p0330_gone": {"complexity": 30}}
    assert any("_p0330_gone: stale" in f for f in am.function_findings(tree, lengths, stale))


# ---------------------------------------------------------------- G3 import graph


def test_cross_package_components_equal_the_baseline(measured):
    # P0330-G3: (a) found == baseline, both ways, so an empty graph cannot pass.
    tree, _ = measured
    assert am.scc_findings(tree, BASELINES["baseline_sccs"]) == []
    assert len(BASELINES["baseline_sccs"]) >= 1
    assert sum(len(t) for t in tree.graph(("module", "deferred")).values()) >= 500


def test_a_component_that_gains_a_member_is_red(measured):
    # P0330-G3: (a) an import from a module outside a baseline component into
    # it, and a new two-package cycle, are each red (QA-S1-13).
    tree, _ = measured
    baseline = BASELINES["baseline_sccs"]
    graph = tree.graph(("module", "deferred"))
    component = set(baseline[0])
    member, outside = next(
        (m, t) for m in sorted(component) for t in sorted(graph[m]) if t not in component
    )
    path = tree.path_of[outside]
    planted = tree.with_changes(
        {path: tree.sources[path] + f"\n\ndef _p0330_mutant():\n    import {member}\n"}
    )
    findings = am.scc_findings(planted, baseline)
    assert any("not in the baseline" in f and outside in f for f in findings)
    assert any("no longer found" in f for f in findings)

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


def test_the_workspace_to_run_count_is_an_exact_ratchet(measured):
    # P0330-G3: (c) the interim same-row ratchet; one more import is red, one
    # fewer asks for the entry to be lowered.
    tree, _ = measured
    same_row = BASELINES["same_row_cross_imports"]
    assert am.cross_import_findings(tree, same_row) == []
    planted = tree.with_changes(
        {
            "workspace/naming.py": tree.sources["workspace/naming.py"]
            + "\n\ndef _p0330():\n    import pyflightstream.run\n"
        }
    )
    assert any("above its baseline entry" in f for f in am.cross_import_findings(planted, same_row))
    higher = {"workspace->run": same_row["workspace->run"] + 1}
    assert any("lower the baseline entry" in f for f in am.cross_import_findings(tree, higher))


# ---------------------------------------------------------------- G4 fan-out


def test_fan_out_ratchet_holds_on_the_tree(measured):
    # P0330-G4: module-level and deferred fan-out within 25 or their entry.
    tree, _ = measured
    assert am.fan_out_findings(tree, BASELINES["fan_out"], BASELINES["fan_out_deferred"]) == []
    assert max(tree.fan_out.values()) > 0 and max(tree.fan_out_deferred.values()) > 0


@pytest.mark.parametrize("deferred", [False, True])
def test_a_module_of_26_imports_is_red(deferred):
    # P0330-G4: 25 distinct package modules pass, 26 are red, counted
    # separately at module level and in function bodies (QA-S1-14).
    def wide(n: int) -> dict[str, str]:
        lines = [f"import pyflightstream.m{i}" for i in range(n)]
        body = (
            "def f():\n" + "".join(f"    {line}\n" for line in lines)
            if deferred
            else "\n".join(lines) + "\n"
        )
        return {**{f"m{i}.py": "X = 1\n" for i in range(26)}, "wide.py": body}

    assert am.fan_out_findings(_mini(wide(25)), {}, {}) == []
    kind = "deferred fan-out" if deferred else "module-level fan-out"
    assert any(
        f.startswith("wide.py: ") and kind in f
        for f in am.fan_out_findings(_mini(wide(26)), {}, {})
    )


def test_a_listed_module_that_imports_one_more_is_red(measured):
    # P0330-G4: a baseline entry may not grow.
    tree, _ = measured
    table = BASELINES["fan_out"]
    path = max(table, key=lambda p: table[p])
    graph = tree.graph(("module",))
    extra = next(
        n for n in sorted(tree.path_of) if n not in graph[am.dotted(path)] and n != am.dotted(path)
    )
    planted = tree.with_changes({path: tree.sources[path] + f"\nimport {extra}\n"})
    assert any(
        f.startswith(f"{path}: ") and "above its baseline entry" in f
        for f in am.fan_out_findings(planted, table, BASELINES["fan_out_deferred"])
    )


# ---------------------------------------------------------------- G5 test coupling


def _g5(coupling) -> list[str]:
    return am.coupling_findings(
        coupling,
        BASELINES["private_test_names"],
        BASELINES["monkeypatch_targets"],
        BASELINES["monkeypatch_targets_by_module"],
    )


def test_private_name_coupling_is_pinned(measured):
    # P0330-G5: the counts per source module equal the baseline exactly, and
    # the reader found what the tests reach.
    tree, coupling = measured
    assert _g5(coupling) == []
    assert sum(coupling.private_counts().values()) > 0
    assert sum(coupling.patch_counts().values()) > 0


@pytest.mark.parametrize(
    "source",
    [
        "from pyflightstream.run import _p0330_new_private\n",
        "import pyflightstream.cases.workflows as wf\n\nwf._p0330_new_private\n",
        "import pyflightstream.run as r\n\ngetattr(r, '_p0330_new_private')\n",
        "def test_x(monkeypatch):\n    monkeypatch.setattr('pyflightstream.run.p0330_target', 1)\n",
        "from unittest import mock\nimport pyflightstream.run as r\n\n"
        "mock.patch.object(r, 'p0330_target')\n",
        "from unittest.mock import patch\n\npatch('pyflightstream.workspace.p0330_target')\n",
    ],
)
def test_a_test_reaching_a_new_private_name_or_target_is_red(measured, source):
    # P0330-G5: each spelling the reader covers raises a count (QA-S1-15).
    tree, coupling = measured
    extra = am.read_test_coupling({"test_p0330_planted.py": source}, tree.path_of)
    assert any(
        "above its baseline entry" in f or "measured" in f for f in _g5(coupling.merged(extra))
    )


def test_a_retargeted_test_asks_for_the_entry_to_be_lowered(measured):
    # P0330-G5: a count that falls fails until its entry is lowered.
    _, coupling = measured
    module = max(coupling.private, key=lambda m: len(coupling.private[m]))
    fewer = am.Coupling(
        {**coupling.private, module: set(sorted(coupling.private[module])[1:])}, coupling.patched
    )
    assert any(f.startswith(module) and "lower the baseline entry" in f for f in _g5(fewer))


# ---------------------------------------------------------------- G6 one home


# The nine two-home pairs measured on v0.32.0 (GEO-072 2.6), kept as
# synthetic sources so the detector is shown to fire after WP2 empties the
# allowlist (QA-S1-16).
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


# ---------------------------------------------------------------- G7 the record


def test_the_record_agrees_with_the_tree(measured, records):
    # P0330-ARCH-METRICS and P0330-G7: the tree re-measured agrees with the
    # newest record, the record is no worse than the committed metrics table,
    # and the table is no worse than the first record (the freeze).
    tree, coupling = measured
    first, newest, path = records
    numbers = am.metrics(tree, coupling)
    assert am.record_findings(numbers, newest, BASELINES["metrics"], first) == []
    date = am.RECORD_RE.match(path.name).group(2)
    assert am.headline(newest, date) in path.read_text(encoding="utf-8")
    for key in ("module_count", "total_lines", "code_lines"):
        assert newest[key] > 0, key


def test_a_regenerated_record_cannot_hide_growth(measured, records, monkeypatch):
    # P0330-G7: 500 lines added to the top module and the record regenerated
    # from the mutant is still red against the table (QA-S1-17); a module
    # count the record does not state is red; a threshold changed without
    # the first record is red.
    tree, coupling = measured
    first, newest, _ = records
    top = max(tree.module_code_lines, key=lambda p: tree.module_code_lines[p])
    grown = tree.with_changes(
        {top: tree.sources[top] + "".join(f"_P{i} = {i}\n" for i in range(500))}
    )
    regenerated = am.metrics(grown, coupling)
    findings = am.record_findings(regenerated, regenerated, BASELINES["metrics"], first)
    assert any(f.startswith("top1_share: the newest record") for f in findings)

    added = tree.with_changes({"qa/p0330_new.py": _deep_module(80)})
    assert any(
        f.startswith("module_count")
        for f in am.record_findings(
            am.metrics(added, coupling), newest, BASELINES["metrics"], first
        )
    )

    monkeypatch.setattr(am, "SOFT_LINES", 1500)
    assert any(
        f.startswith("thresholds")
        for f in am.record_findings(newest, newest, BASELINES["metrics"], first)
    )


# ---------------------------------------------------------------- G8 facades


def test_roots_are_facades_on_the_tree(measured):
    # P0330-G8: tabled roots within their entry, every other root within the
    # cap and holding no definitions beyond its recorded ones, no star import.
    tree, _ = measured
    assert (
        am.facade_findings(tree, BASELINES["facade_lines"], BASELINES["facade_definitions"]) == []
    )
    assert len(tree.roots) >= 10 and BASELINES["facade_lines"]


def test_a_definition_in_a_facade_root_is_red(measured):
    # P0330-G8: a function or class defined in a facade root, a star import,
    # and one more statement line in a tabled root are each red; a lazy
    # __getattr__ is the one definition a facade may hold (QA-S1-18).
    tree, _ = measured
    table, defs = BASELINES["facade_lines"], BASELINES["facade_definitions"]

    def red(path: str, addition: str) -> list[str]:
        planted = tree.with_changes({path: tree.sources[path] + addition})
        return [f for f in am.facade_findings(planted, table, defs) if f.startswith(path)]

    facade = min(tree.roots, key=lambda p: tree.root_facade_lines[p])
    assert red(facade, "\n\ndef _p0330_helper():\n    return 1\n")
    assert red(facade, "\n\nclass P0330:\n    pass\n")
    assert red(facade, "\nfrom pyflightstream._errors import *\n")
    assert red(facade, "\n\ndef __getattr__(name):\n    raise AttributeError(name)\n") == []
    tabled = max(table, key=lambda p: table[p])
    assert any("above its baseline entry" in f for f in red(tabled, MUTANT))
    stale = {**defs, facade: ["_p0330_gone"]}
    assert any("_p0330_gone left the root" in f for f in am.facade_findings(tree, table, stale))


def test_the_baselines_carry_every_key_the_goal_reads():
    # P0330-G1: the keys of architecture_baselines.json the goal checker and
    # the guards read.
    for key in (
        "module_code_lines",
        "function_lines",
        "baseline_sccs",
        "fan_out",
        "private_test_names",
        "monkeypatch_targets",
        "one_home_allowlist",
        "facade_lines",
        "same_row_cross_imports",
        "function_limits",
        "fan_out_deferred",
        "monkeypatch_targets_by_module",
        "facade_definitions",
        "modules_at_freeze",
        "package_order",
        "metrics",
    ):
        assert key in BASELINES, key
