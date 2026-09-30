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
    # The table may reach empty; the walk totals are the non-vacuity.
    assert len(tree.paths) >= max(100, int(0.9 * newest["module_count"]))
    assert sum(tree.module_code_lines.values()) >= 0.9 * newest["code_lines"]


def _size_cases(tree):
    """(tree, table, listed module over the ceiling): the real one while any, and a planted one.

    The planted case keeps the mutants alive once the ratchet has emptied the table.
    """
    table = BASELINES["module_code_lines"]
    over = [p for p in table if tree.module_code_lines.get(p, 0) > am.HARD_LINES]
    cases = [(tree, table, max(over, key=lambda p: table[p]))] if over else []
    planted = "qa/p0330_listed.py"
    big = tree.with_changes({planted: _deep_module(am.HARD_LINES + 500)})
    cases.append((big, {**table, planted: am.HARD_LINES + 500}, planted))
    return cases


def test_module_size_ratchet_refuses_each_planted_mutant(measured):
    # P0330-G1: the mutants of AD-08 G1 and QA-S1-11 are each red.
    tree, _ = measured
    table = BASELINES["module_code_lines"]
    frozen = BASELINES["modules_at_freeze"]

    for base, listed_table, listed in _size_cases(tree):
        assert am.size_findings(base, listed_table, frozen) == [], listed
        grown = base.with_changes({listed: base.sources[listed] + MUTANT})
        assert any(
            f.startswith(f"{listed}: ") and "above its baseline entry" in f
            for f in am.size_findings(grown, listed_table, frozen)
        ), listed
        slack = {**listed_table, listed: listed_table[listed] + 5}
        assert any(
            f.startswith(f"{listed}: ") and "lower the baseline entry" in f
            for f in am.size_findings(base, slack, frozen)
        ), listed
        deleted = {k: v for k, v in listed_table.items() if k != listed}
        assert any(
            f.startswith(f"{listed}: ") and "not in the baseline" in f
            for f in am.size_findings(base, deleted, frozen)
        ), listed

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
    # (ruff and pylint defaults) hold; the tables may reach empty, the
    # function count read is the non-vacuity.
    tree, _ = measured
    assert (
        am.function_findings(tree, BASELINES["function_lines"], BASELINES["function_limits"]) == []
    )
    assert len(tree.functions) >= 2000


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
    cases = [(tree, lengths, max(lengths, key=lambda k: lengths[k]))] if lengths else []
    # A planted listed function keeps the mutant alive once the table is empty.
    long_fn = "def _p0330_long():\n" + "    x = 1\n" * (am.FUNCTION_FLOOR + 9)
    planted = tree.with_changes({"qa/p0330_long.py": long_fn})
    key = "qa/p0330_long.py:_p0330_long"
    cases.append((planted, {**lengths, key: am.FUNCTION_FLOOR + 10}, key))
    for base, table, key in cases:
        path, qualname = key.split(":", 1)
        grown = base.with_changes({path: _grow_function(base.sources[path], qualname)})
        assert not any(
            f.startswith(f"{key}: code lines") for f in am.function_findings(base, table, limits)
        ), key
        assert any(
            f.startswith(f"{key}: code lines") for f in am.function_findings(grown, table, limits)
        ), key

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
    # The baseline may reach empty (WP2 removes the loads cycle); the edges
    # read are the non-vacuity.
    assert sum(len(t) for t in tree.graph(("module", "deferred")).values()) >= 500


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
    # P0330-G4: a baseline entry may not grow, and a fall fails until the
    # entry is lowered; a planted listed module keeps the mutant alive once
    # the table is empty.
    tree, _ = measured
    table, deferred = BASELINES["fan_out"], BASELINES["fan_out_deferred"]
    cases = [(tree, table, max(table, key=lambda p: table[p]))] if table else []
    targets = [n for n in sorted(tree.path_of) if n != am.PKG][: am.FAN_OUT_CAP + 5]
    wide = tree.with_changes({"qa/p0330_wide.py": "".join(f"import {n}\n" for n in targets)})
    cases.append((wide, {**table, "qa/p0330_wide.py": am.FAN_OUT_CAP + 5}, "qa/p0330_wide.py"))
    for base, listed, path in cases:
        assert am.fan_out_findings(base, listed, deferred) == [], path
        graph = base.graph(("module",))
        extra = next(
            n
            for n in sorted(base.path_of)
            if n not in graph[am.dotted(path)] and n not in (am.dotted(path), am.PKG)
        )
        planted = base.with_changes({path: base.sources[path] + f"\nimport {extra}\n"})
        assert any(
            f.startswith(f"{path}: ") and "above its baseline entry" in f
            for f in am.fan_out_findings(planted, listed, deferred)
        ), path
        slack = {**listed, path: listed[path] + 1}
        assert any(
            f.startswith(f"{path}: ") and "lower the baseline entry" in f
            for f in am.fan_out_findings(base, slack, deferred)
        ), path


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
    # The counts may reach zero as tests are retargeted; the test files read
    # are the non-vacuity, beside the planted references below.
    assert len(am.load_tests(REPO / "tests")) >= 100


@pytest.mark.parametrize(
    ("source", "module"),
    [
        ("from pyflightstream.run import _p0330_new_private\n", "pyflightstream.run"),
        (
            "import pyflightstream.cases.workflows as wf\n\nwf._p0330_new_private\n",
            "pyflightstream.cases.workflows",
        ),
        (
            "import pyflightstream.run as r\n\ngetattr(r, '_p0330_new_private')\n",
            "pyflightstream.run",
        ),
        (
            "def test_x(monkeypatch):\n"
            "    monkeypatch.setattr('pyflightstream.run.p0330_target', 1)\n",
            "pyflightstream.run",
        ),
        (
            "from unittest import mock\nimport pyflightstream.run as r\n\n"
            "mock.patch.object(r, 'p0330_target')\n",
            "pyflightstream.run",
        ),
        (
            "from unittest.mock import patch\n\npatch('pyflightstream.workspace.p0330_target')\n",
            "pyflightstream.workspace",
        ),
    ],
)
def test_a_test_reaching_a_new_private_name_or_target_is_red(measured, source, module):
    # P0330-G5: each spelling the reader covers raises the count of the
    # module it names, from a clean start (QA-S1-15).
    tree, coupling = measured
    assert _g5(coupling) == []
    extra = am.read_test_coupling({"test_p0330_planted.py": source}, tree.path_of)
    assert any(
        f.startswith(f"{module}: ") and "above its baseline entry" in f
        for f in _g5(coupling.merged(extra))
    )


def test_a_retargeted_test_asks_for_the_entry_to_be_lowered(measured):
    # P0330-G5: a count that falls fails until its entry is lowered; the
    # coupling carries planted names so the mutant lives when the tree's is zero.
    tree, coupling = measured
    planted = am.read_test_coupling(
        {"test_p0330_planted.py": "from pyflightstream.run import _p0330_a, _p0330_b\n"},
        tree.path_of,
    )
    base = coupling.merged(planted)

    def g5(c) -> list[str]:
        counts = base.patch_counts()
        return am.coupling_findings(c, base.private_counts(), sum(counts.values()), counts)

    assert g5(base) == []
    module = max(base.private, key=lambda m: len(base.private[m]))
    fewer = am.Coupling(
        {**base.private, module: set(sorted(base.private[module])[1:])}, base.patched
    )
    assert any(f.startswith(module) and "lower the baseline entry" in f for f in g5(fewer))


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


# The numbers of the freeze record, pinned here so that renumbering, editing
# or deleting RPT-100 in the same commit as a table change cannot move the
# floor the metrics table is compared with.
_FREEZE_RECORD = "RPT-100_architecture-metrics_2026-09-30.md"
_FREEZE = {
    "module_count": 150,
    "total_lines": 146463,
    "code_lines": 79704,
    "top1_share": 11.3,
    "top5_share": 30.6,
    "top13_share": 48.2,
    "modules_over_1000": 17,
    "modules_over_2000": 6,
    "functions_over_100": 75,
    "functions_over_200": 19,
    "functions_over_300": 8,
    "functions_over_limits": 230,
    "cross_package_sccs": 2,
    "largest_fan_out": 36,
    "largest_fan_out_deferred": 11,
    "private_test_names": 242,
    "monkeypatch_targets": 83,
    "workspace_to_run_imports": 2,
    "root_facade_lines": 23961,
}


def test_the_freeze_record_is_pinned(records):
    # P0330-G7: the first record is RPT-100 and states the freeze numbers,
    # and the committed table is no worse than them.
    first, _, _ = records
    found = am.records(REPO / "reports")
    assert found[0][1].name == _FREEZE_RECORD
    assert {k: first[k] for k in _FREEZE} == _FREEZE
    assert set(am.MONOTONE) <= set(_FREEZE)
    for key in am.MONOTONE:
        assert BASELINES["metrics"][key] <= _FREEZE[key], key


def test_the_record_lists_new_modules_under_the_review_size(measured, monkeypatch):
    # P0330-G7: a module created since v0.32.0 under 150 code lines is listed
    # for the reviewer (AD-08 "Deep modules"); one of 150 or more is not.
    tree, coupling = measured
    short, deep = "qa/p0330_short.py", "qa/p0330_deep.py"
    planted = tree.with_changes(
        {short: _deep_module(am.DEEP_REVIEW_LINES - 1), deep: _deep_module(am.DEEP_REVIEW_LINES)}
    )
    assert am.deep_review_list(planted, [short, deep]) == [short]
    monkeypatch.setattr(am, "_modules_added_since", lambda ref, sources: [deep, short])
    text = am.render_report(planted, coupling, 999, "2026-09-30")
    assert f"- `{short}` {am.DEEP_REVIEW_LINES - 1}" in text
    assert (
        f"`{deep}`"
        not in text.split(f"under {am.DEEP_REVIEW_LINES} code lines", 1)[1].split("##", 1)[0]
    )


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
    # P0330-G8: tabled roots at their entry, every other root holding nothing
    # beyond docstring, imports, __all__ and a lazy __getattr__, no star import.
    tree, _ = measured
    assert (
        am.facade_findings(tree, BASELINES["facade_lines"], BASELINES["facade_definitions"]) == []
    )
    # The table may reach empty; the roots read are the non-vacuity.
    assert len(tree.roots) >= 10


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


def test_a_tabled_root_only_shrinks(measured):
    # P0330-G8: one more statement line in a tabled root is red, a fall fails
    # until the entry is lowered, and an entry for a root that is now a
    # facade, or is gone, is stale.
    tree, _ = measured
    table, defs = BASELINES["facade_lines"], BASELINES["facade_definitions"]
    base = tree.with_changes({_CLEAN_ROOT: '"""A planted root."""\nX = 1\nY = 2\n'})
    listed = {**table, _CLEAN_ROOT: 2}
    assert am.facade_findings(base, listed, defs) == []
    tabled = [_CLEAN_ROOT] + ([max(table, key=lambda p: table[p])] if table else [])
    for path in tabled:
        grown = base.with_changes({path: base.sources[path] + MUTANT})
        assert any(
            f.startswith(path) and "above its baseline entry" in f
            for f in am.facade_findings(grown, listed, defs)
        ), path
        slack = {**listed, path: listed[path] + 1}
        assert any(
            f.startswith(path) and "lower the baseline entry" in f
            for f in am.facade_findings(base, slack, defs)
        ), path
    clean = base.with_changes({"qa/p0330_facade/__init__.py": '"""A facade."""\n'})
    now_facade = {**listed, "qa/p0330_facade/__init__.py": 1}
    assert any(
        f.startswith("qa/p0330_facade/__init__.py: stale")
        for f in am.facade_findings(clean, now_facade, defs)
    )
    gone = {**listed, "gone/__init__.py": 5}
    assert any(
        f.startswith("gone/__init__.py: stale") for f in am.facade_findings(base, gone, defs)
    )
    stale = {**defs, _CLEAN_ROOT: ["_p0330_gone"]}
    assert any("_p0330_gone left the root" in f for f in am.facade_findings(base, listed, stale))


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
