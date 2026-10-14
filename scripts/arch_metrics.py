"""Measure live architecture and check its committed structural baselines.

Use summary, tables or check. Source readers take text mappings, so syntax
analysis does not import the product. Historical report generation is maintained
with the internal release tooling. This tool never edits baseline tables.
"""

from __future__ import annotations

import argparse
import ast
import functools
import importlib.util
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING


def _sibling(name: str, file: str):
    """Load a sibling script once, under one name, however this file was loaded."""
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


readers = _sibling("pyflightstream_arch_readers", "_arch_readers.py")
if TYPE_CHECKING:
    from _arch_readers import Coupling, Tree
else:
    Coupling = readers.Coupling
    Tree = readers.Tree
code_lines = readers.code_lines
dotted = readers.dotted
facade_lines = readers.facade_lines
is_exempt = readers.is_exempt
load_sources = readers.load_sources
load_tests = readers.load_tests
read_test_coupling = readers.read_test_coupling
top_level_defs = readers.top_level_defs
walk_functions = readers.walk_functions

REPO = readers.REPO
BASELINES = REPO / "tests" / "tier1_offline" / "architecture_baselines.json"
PKG = readers.PKG

# The lens (GEO-072 lens C1 and C3; GOAL-038 "The lens").
SOFT_LINES, HARD_LINES = 1000, 2000
DEEP_MIN_LINES, DEEP_MIN_DEFS = 60, 2
DEEP_REVIEW_LINES = 150  # AD-08 "Deep modules": listed for the reviewer, not refused
FACADE_CAP = (
    300  # G8: a tabled root above it may hold definitions; G3b: run declares its order under it
)
FUNCTION_FLOOR = 250  # G2: a function above this many code lines is in the length table
FAN_OUT_CAP = 25  # G4
LIMITS = {"complexity": 10, "branches": 12, "statements": 50, "positional": 5}  # G2, ruff/pylint
LENGTH_BANDS = (100, 200, 300)  # G7: functions over these code lines
TOP_SHARES = (1, 5, 13)  # G7
FACADE_ALLOWED_DEFS = frozenset({"__getattr__"})  # G8: "at most a lazy __getattr__ loader"

# The metrics of the record that may only improve (G7), and the direction.
MONOTONE = (
    "top1_share",
    "top5_share",
    "top13_share",
    "modules_over_1000",
    "modules_over_2000",
    "functions_over_100",
    "functions_over_200",
    "functions_over_300",
    "functions_over_limits",
    "cross_package_sccs",
    "largest_fan_out",
    "largest_fan_out_deferred",
    "private_test_names",
    "monkeypatch_targets",
    "workspace_to_run_imports",
    "root_facade_lines",
)

# THE TEST-COUPLING FREEZE RE-PINNED AT 0.40.0, and nothing else of the first
# record: the release decision of 2026-10-12 (capabilities first, rigor in its
# own release) accepted the coupling the 0.40.0 lanes' tests brought, listed
# per module in RPT-168, with the final 2026-10-13 lane recount at 334 and 150,
# attributed to rfixAPI, rfixR5 and rfixR6 in RPT-173,
# and planned the reduction back to the numbers of the
# first record (242 private names, 83 patch targets) as PFS-2081.47 (0.42.0).
# The metrics table is compared with these two numbers in place of the first
# record's; raising either is an edit of this line, visible in review.
COUPLING_REPIN = {"private_test_names": 334, "monkeypatch_targets": 150}


def freeze_floor(freeze: Mapping) -> dict:
    """Return the first record's numbers the metrics table may not be worse than, re-pinned."""
    return {**freeze, **COUPLING_REPIN}


def over_limits(measures: Mapping[str, int]) -> bool:
    """Whether a function exceeds any G2 limit."""
    return any(measures[k] > v for k, v in LIMITS.items())


def package_order_findings(
    tree: Tree, package: str, order: list[str], outside: list[str]
) -> list[str]:
    """G3b: each ordered module imports only modules after it; every other module is declared."""
    prefix = package + "."
    members = {
        n.removeprefix(prefix) if n != package else "__init__"
        for n in tree.path_of
        if n == package or (n.startswith(prefix) and "." not in n.removeprefix(prefix))
    }
    findings = []
    if package not in tree.path_of:
        return [f"{package}: declares an order and is not a package of this tree"]
    missing = sorted(members - set(order) - set(outside))
    findings += [
        f"{package}.{m}: a module of the package missing from its declared order" for m in missing
    ]
    unknown = sorted(set(order) - members)
    findings += [
        f"{package}.{m}: in the declared order but not a module of the package" for m in unknown
    ]
    position = {m: i for i, m in enumerate(order)}

    def short(name: str) -> str | None:
        if name == package:
            return "__init__"
        rest = name.removeprefix(prefix) if name.startswith(prefix) else None
        return rest.split(".")[0] if rest else None

    for imp in tree.imports:
        src, dst = short(imp.src), short(imp.target)
        if src is None or dst is None or src == dst or src not in position or dst not in position:
            continue
        if position[dst] <= position[src]:
            findings.append(
                f"{tree.path_of[imp.src]}:{imp.line}: {imp.kind} import of {imp.target}, "
                f"which is not after {src} in the declared order of {package}"
            )
    return findings


# ------------------------------------------------------------------ the guards
# Each returns the list of its findings; an empty list is green. The tests
# call these on the tree and on planted mutants.


def _at_most(
    measured: Mapping[str, int], table: Mapping[str, int], floor: int, what: str
) -> list[str]:
    """Judge an 'at most' ratchet: unlisted above the floor, an entry grown, a stale entry."""
    out = []
    for key, n in sorted(measured.items()):
        if key in table:
            if n > int(table[key]):
                out.append(f"{key}: {what} {n}, above its baseline entry {table[key]}")
        elif n > floor:
            out.append(f"{key}: {what} {n}, above {floor} and not in the baseline")
    for key in sorted(set(table) - set(measured)):
        out.append(f"{key}: stale baseline entry, the item is gone; delete the entry")
    for key in sorted(k for k in table if k in measured and measured[k] <= floor):
        out.append(
            f"{key}: stale baseline entry, {what} {measured[key]} is within {floor}; "
            "delete the entry"
        )
    return out


def _exact(measured: Mapping[str, int], table: Mapping[str, int], what: str) -> list[str]:
    """Judge an exact ratchet: a rise fails as growth, a fall until the entry is lowered."""
    out = []
    for key in sorted(set(measured) | set(table)):
        n, entry = int(measured.get(key, 0)), int(table.get(key, 0))
        if n > entry:
            out.append(f"{key}: {what} {n}, above its baseline entry {entry}")
        elif n < entry:
            out.append(f"{key}: {what} fell to {n} from {entry}; lower the baseline entry to {n}")
    return out


def _shrinking(
    measured: Mapping[str, int], table: Mapping[str, int], floor: int, what: str
) -> list[str]:
    """Judge a ratchet that clicks: 'at most', and a fall fails until the entry is lowered."""
    out = _at_most(measured, table, floor, what)
    for key in sorted(k for k in table if k in measured and floor < measured[k] < int(table[k])):
        out.append(
            f"{key}: {what} fell to {measured[key]} from {table[key]}; "
            f"lower the baseline entry to {measured[key]}"
        )
    return out


def size_findings(
    tree: Tree, table: Mapping[str, int], modules_at_freeze: Iterable[str]
) -> list[str]:
    """G1 (the lens) and the depth rule for a module created after the freeze."""
    measured = tree.module_code_lines
    out = []
    for path, n in sorted(measured.items()):
        if path in table:
            if n > int(table[path]):
                out.append(f"{path}: {n} code lines, above its baseline entry {table[path]}")
            elif SOFT_LINES < n < int(table[path]):
                out.append(
                    f"{path}: {n} code lines, fell from {table[path]}; "
                    f"lower the baseline entry to {n}"
                )
            continue
        if n > HARD_LINES:
            out.append(
                f"{path}: {n} code lines, above the hard limit {HARD_LINES} and not in the baseline"
            )
        elif n > SOFT_LINES and not is_exempt(tree.sources[path]):
            out.append(
                f"{path}: {n} code lines, above {SOFT_LINES}, and its module docstring has no "
                "'Size exemption: <reason>' line"
            )
    for path in sorted(table):
        if path not in measured:
            out.append(f"{path}: stale size entry, the module is gone; delete the entry")
        elif measured[path] <= SOFT_LINES:
            out.append(f"{path}: stale size entry, {measured[path]} code lines; delete the entry")
    frozen = set(modules_at_freeze)
    for path in sorted(set(measured) - frozen):
        if path.endswith("__init__.py"):
            continue
        defs = top_level_defs(tree.sources[path])
        if defs < DEEP_MIN_DEFS or measured[path] < DEEP_MIN_LINES:
            out.append(
                f"{path}: a module created after the freeze with {defs} top-level definitions and "
                f"{measured[path]} code lines; a new module is deep (>= {DEEP_MIN_DEFS} and "
                f">= {DEEP_MIN_LINES})"
            )
    return out


def function_findings(
    tree: Tree, lines_table: Mapping[str, int], limits_table: Mapping[str, Mapping[str, int]]
) -> list[str]:
    """G2: the function length ratchet and the function limits ratchet."""
    functions = tree.functions
    out = _at_most(
        {k: f["lines"] for k, f in functions.items()}, lines_table, FUNCTION_FLOOR, "code lines"
    )
    for key, f in sorted(functions.items()):
        entry = limits_table.get(key)
        for metric, limit in LIMITS.items():
            allowed = max(limit, int(entry.get(metric, 0))) if entry else limit
            if f[metric] > allowed:
                where = (
                    f"its baseline entry {allowed}"
                    if entry and allowed > limit
                    else f"the limit {limit}"
                )
                out.append(f"{key}: {metric} {f[metric]}, above {where}")
    for key in sorted(limits_table):
        if key not in functions:
            out.append(f"{key}: stale limits entry, the function is gone; delete the entry")
        elif not over_limits(functions[key]):
            out.append(f"{key}: stale limits entry, now within every limit; delete the entry")
        else:
            for metric, n in limits_table[key].items():
                if int(n) > max(LIMITS[metric], functions[key][metric]):
                    out.append(
                        f"{key}: {metric} fell to {functions[key][metric]}; "
                        f"lower the entry from {n}"
                    )
    return out


def scc_findings(tree: Tree, baseline: Iterable[Iterable[str]]) -> list[str]:
    """G3a: the cross-package components equal the baseline, both ways."""
    found = {frozenset(c) for c in tree.cross_package_sccs}
    frozen = {frozenset(c) for c in baseline}
    out = []
    for component in sorted(found - frozen, key=sorted):
        out.append(
            "cross-package import cycle not in the baseline: " + ", ".join(sorted(component))
        )
    for component in sorted(frozen - found, key=sorted):
        out.append(
            "baseline component no longer found as it is; update or delete it: "
            + ", ".join(sorted(component))
        )
    return out


# The packages AD-12 and AD-14 require to declare an order, and when.
def required_orders(tree: Tree) -> list[str]:
    """Return the packages that must declare an order in ``package_order`` today (G3b)."""
    required = []
    if "cases/workflows/__init__.py" in tree.sources:
        required.append(PKG + ".cases.workflows")
    if tree.root_facade_lines.get("run/__init__.py", FACADE_CAP + 1) <= FACADE_CAP:
        required.append(PKG + ".run")
    return required


def order_findings(tree: Tree, package_order: Mapping[str, Mapping[str, list[str]]]) -> list[str]:
    """G3b: each declared package keeps its order; the required packages declare one."""
    out = []
    for package in required_orders(tree):
        if package not in package_order:
            out.append(f"{package}: a package that AD-12/AD-14 order and that declares no order")
    for package, declared in sorted(package_order.items()):
        out += package_order_findings(
            tree, package, list(declared.get("order", [])), list(declared.get("outside", []))
        )
    return out


def cross_import_findings(tree: Tree, same_row: Mapping[str, int]) -> list[str]:
    """G3c: the interim workspace to run ratchet (exact; WP1 takes it to 0)."""
    measured = {"workspace->run": len(tree.cross_imports("workspace", "run"))}
    return _exact(measured, same_row, "same-row cross imports")


def fan_out_findings(
    tree: Tree, table: Mapping[str, int], deferred: Mapping[str, int]
) -> list[str]:
    """G4: module-level and deferred fan-out, each capped, counted separately."""
    return _shrinking(tree.fan_out, table, FAN_OUT_CAP, "module-level fan-out") + _shrinking(
        tree.fan_out_deferred, deferred, FAN_OUT_CAP, "deferred fan-out"
    )


def coupling_findings(
    coupling: Coupling,
    private: Mapping[str, int],
    patch_total: int,
    patch_by_module: Mapping[str, int],
) -> list[str]:
    """G5: private names and patch targets the tests reach, per module, exact."""
    out = _exact(coupling.private_counts(), private, "private names referenced by tests")
    out += _exact(coupling.patch_counts(), patch_by_module, "patch targets")
    total = sum(coupling.patch_counts().values())
    if total != int(patch_total):
        out.append(f"monkeypatch_targets: {total} measured, {patch_total} recorded")
    return out


def one_home_findings(tree: Tree, allowlist: Iterable[Iterable[str]]) -> list[str]:
    """G6: a (NAME, literal) defined in two modules without an import between them."""
    found = {readers.allowlist_key(p): p for p in tree.one_home_pairs}
    allowed = {tuple(a) for a in allowlist}
    out = []
    for key in sorted(set(found) - allowed):
        name, value, a, b = found[key]
        out.append(f"{name} = {value} has two homes: {a} and {b}; import it from one")
    for key in sorted(allowed - set(found)):
        out.append(f"stale one-home allowlist entry, the pair is gone; delete it: {list(key)}")
    return out


@functools.lru_cache(maxsize=128)
def _root_facts(text: str) -> tuple[tuple[str, ...], tuple[int, ...], int]:
    """Parse a root once: its definitions, its star-import lines, its lines beyond the facade."""
    tree = ast.parse(text)
    definitions = tuple(
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and n.name not in FACADE_ALLOWED_DEFS
    )
    stars = tuple(
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
    )
    loader = sum(
        (n.end_lineno or n.lineno) - n.lineno + 1
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in FACADE_ALLOWED_DEFS
    )
    return definitions, stars, facade_lines(text) - loader


def root_definitions(text: str) -> list[str]:
    """Top-level functions and classes of a root other than a lazy loader (G8)."""
    return list(_root_facts(text)[0])


def star_imports(text: str) -> list[int]:
    """Lines of the star imports of a source."""
    return list(_root_facts(text)[1])


def facade_excess(text: str) -> int:
    """Statement lines of a root beyond its docstring, imports, __all__ and a lazy __getattr__."""
    return _root_facts(text)[2]


def facade_findings(
    tree: Tree, table: Mapping[str, int], definitions: Mapping[str, list[str]]
) -> list[str]:
    """G8: a root absent from the table holds nothing beyond the facade; entries only shrink."""
    measured = tree.root_facade_lines
    out = []
    for path in tree.roots:
        text = tree.sources[path]
        n, entry, excess = measured[path], table.get(path), facade_excess(text)
        out += [f"{path}:{line}: a star import in a package root" for line in star_imports(text)]
        if entry is None:
            if excess:
                out.append(
                    f"{path}: {excess} statement lines beyond its docstring, imports, __all__ and "
                    "a lazy __getattr__; a root absent from the baseline holds none"
                )
        elif n > int(entry):
            out.append(
                f"{path}: statement lines beyond the facade {n}, above its baseline entry {entry}"
            )
        elif not excess:
            out.append(f"{path}: stale baseline entry, the root is now a facade; delete the entry")
        elif n < int(entry):
            out.append(
                f"{path}: statement lines beyond the facade fell to {n} from {entry}; "
                f"lower the baseline entry to {n}"
            )
        if int(entry or 0) > FACADE_CAP:
            continue
        extra = sorted(set(root_definitions(text)) - set(definitions.get(path, [])))
        out += [f"{path}: defines {name}; a facade root holds no definitions" for name in extra]
    for path in sorted(set(table) - set(measured)):
        out.append(f"{path}: stale baseline entry, the root is gone; delete the entry")
    for path, names in sorted(definitions.items()):
        if path not in tree.sources:
            out.append(f"{path}: stale definitions entry, the root is gone; delete it")
            continue
        gone = sorted(set(names) - set(root_definitions(tree.sources[path])))
        out += [
            f"{path}: {name} left the root; delete it from the definitions entry" for name in gone
        ]
    return out


def thresholds() -> dict:
    """Every threshold the guards read, as the record states them."""
    return {
        "soft_lines": SOFT_LINES,
        "hard_lines": HARD_LINES,
        "deep_min_lines": DEEP_MIN_LINES,
        "deep_min_defs": DEEP_MIN_DEFS,
        "facade_cap": FACADE_CAP,
        "function_floor": FUNCTION_FLOOR,
        "fan_out_cap": FAN_OUT_CAP,
        "limits": dict(LIMITS),
    }


def record_findings(
    measured: Mapping, newest: Mapping, table: Mapping, freeze: Mapping
) -> list[str]:
    """G7: tree against newest record, record against table, table against the first record."""
    out = []
    if measured["module_count"] != newest.get("module_count"):
        out.append(
            f"module_count: {measured['module_count']} measured, "
            f"{newest.get('module_count')} in the "
            "newest record; write a new record"
        )
    for key in MONOTONE:
        for label, low, high in (
            ("the tree", measured, newest),
            ("the newest record", newest, table),
            ("the metrics table", table, freeze_floor(freeze)),
        ):
            if key not in low or key not in high:
                out.append(f"{key}: missing from {label} or from what it is compared with")
            elif low[key] > high[key]:
                out.append(f"{key}: {label} says {low[key]}, worse than {high[key]}")
    if freeze.get("thresholds") != thresholds():
        out.append(
            f"thresholds: the guards read {thresholds()}, "
            f"the first record states {freeze.get('thresholds')}"
        )
    return out


def check(tree: Tree, coupling: Coupling, baselines: Mapping) -> dict[str, list[str]]:
    """Every guard's findings against a baseline mapping (G7 excepted: it reads the records)."""
    b = baselines
    return {
        "G1": size_findings(tree, b["module_code_lines"], b["modules_at_freeze"]),
        "G2": function_findings(tree, b["function_lines"], b["function_limits"]),
        "G3a": scc_findings(tree, b["baseline_sccs"]),
        "G3b": order_findings(tree, b["package_order"]),
        "G3c": cross_import_findings(tree, b["same_row_cross_imports"]),
        "G4": fan_out_findings(tree, b["fan_out"], b["fan_out_deferred"]),
        "G5": coupling_findings(
            coupling,
            b["private_test_names"],
            b["monkeypatch_targets"],
            b["monkeypatch_targets_by_module"],
        ),
        "G6": one_home_findings(tree, b["one_home_allowlist"]),
        "G8": facade_findings(tree, b["facade_lines"], b["facade_definitions"]),
    }


# ------------------------------------------------------------------ the record


def metrics(tree: Tree, coupling: Coupling) -> dict:
    """Return the numbers of the architecture metrics record (G7)."""
    sizes = sorted(tree.module_code_lines.values(), reverse=True)
    code_total = sum(sizes)
    functions = tree.functions
    fan = max(tree.fan_out.items(), key=lambda kv: (kv[1], kv[0]))
    fan_d = max(tree.fan_out_deferred.items(), key=lambda kv: (kv[1], kv[0]))
    out: dict = {
        "module_count": len(tree.paths),
        "total_lines": tree.total_lines,
        "code_lines": code_total,
    }
    for k in TOP_SHARES:
        out[f"top{k}_share"] = round(100.0 * sum(sizes[:k]) / code_total, 1) if code_total else 0.0
    out["modules_over_1000"] = sum(n > SOFT_LINES for n in sizes)
    out["modules_over_2000"] = sum(n > HARD_LINES for n in sizes)
    for band in LENGTH_BANDS:
        out[f"functions_over_{band}"] = sum(f["lines"] > band for f in functions.values())
    out["functions_over_limits"] = sum(over_limits(f) for f in functions.values())
    out["cross_package_sccs"] = len(tree.cross_package_sccs)
    out["largest_fan_out"] = fan[1]
    out["largest_fan_out_module"] = fan[0]
    out["largest_fan_out_deferred"] = fan_d[1]
    out["largest_fan_out_deferred_module"] = fan_d[0]
    out["private_test_names"] = sum(coupling.private_counts().values())
    out["monkeypatch_targets"] = sum(coupling.patch_counts().values())
    out["workspace_to_run_imports"] = len(tree.cross_imports("workspace", "run"))
    out["root_facade_lines"] = sum(tree.root_facade_lines.values())
    out["thresholds"] = thresholds()
    return out


def package_summary(tree: Tree, coupling: Coupling) -> dict[str, dict[str, int]]:
    """Summarise each top-level package: the unit a per-package review is partitioned by."""
    out: dict[str, dict[str, int]] = {}

    def row(package: str) -> dict[str, int]:
        return out.setdefault(
            package,
            {"modules": 0, "code_lines": 0, "over_1000": 0, "over_limits": 0, "private_names": 0},
        )

    for path in tree.paths:
        r = row(readers.top_package(tree.names[path]))
        r["modules"] += 1
        r["code_lines"] += tree.module_code_lines[path]
        r["over_1000"] += tree.module_code_lines[path] > SOFT_LINES
    for key, f in tree.functions.items():
        row(readers.top_package(dotted(key.split(":", 1)[0])))["over_limits"] += over_limits(f)
    for module, n in coupling.private_counts().items():
        row(readers.top_package(module))["private_names"] += n
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["code_lines"], kv[0])))


def tables(tree: Tree, coupling: Coupling) -> dict:
    """Today's measure of every baseline table (the shape of architecture_baselines.json)."""
    functions = tree.functions
    return {
        "module_code_lines": {
            p: n for p, n in sorted(tree.module_code_lines.items()) if n > SOFT_LINES
        },
        "function_lines": {
            k: f["lines"] for k, f in sorted(functions.items()) if f["lines"] > FUNCTION_FLOOR
        },
        "function_limits": {
            k: {m: f[m] for m in LIMITS} for k, f in sorted(functions.items()) if over_limits(f)
        },
        "baseline_sccs": [sorted(c) for c in tree.cross_package_sccs],
        "fan_out": {p: n for p, n in sorted(tree.fan_out.items()) if n > FAN_OUT_CAP},
        "fan_out_deferred": {
            p: n for p, n in sorted(tree.fan_out_deferred.items()) if n > FAN_OUT_CAP
        },
        "private_test_names": coupling.private_counts(),
        "monkeypatch_targets": sum(coupling.patch_counts().values()),
        "monkeypatch_targets_by_module": coupling.patch_counts(),
        "one_home_allowlist": [list(readers.allowlist_key(p)) for p in tree.one_home_pairs],
        "facade_lines": {
            p: n
            for p, n in sorted(tree.root_facade_lines.items())
            if facade_excess(tree.sources[p])
        },
        "facade_definitions": {
            p: sorted(root_definitions(tree.sources[p]))
            for p in tree.roots
            if tree.root_facade_lines[p] <= FACADE_CAP and root_definitions(tree.sources[p])
        },
        "same_row_cross_imports": {"workspace->run": len(tree.cross_imports("workspace", "run"))},
        "modules_at_freeze": list(tree.paths),
        "package_order": {},
        "metrics": {k: v for k, v in metrics(tree, coupling).items() if k in MONOTONE},
    }


def deep_review_list(tree: Tree, added: Iterable[str]) -> list[str]:
    """Return the modules of ``added`` under DEEP_REVIEW_LINES code lines (AD-08 deep modules)."""
    return [p for p in sorted(added) if tree.module_code_lines.get(p, 0) < DEEP_REVIEW_LINES]


def measure_repo(repo: Path = REPO) -> tuple[Tree, Coupling]:
    """Measure the package and the tests of a checkout."""
    tree = Tree(load_sources(repo / "src" / "pyflightstream"))
    coupling = read_test_coupling(load_tests(repo / "tests"), tree.path_of)
    return tree, coupling


def main(argv: list[str] | None = None) -> int:
    """Run the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary", help="print the numbers of the record")
    sub.add_parser("tables", help="print today's measure of every baseline table")
    sub.add_parser("check", help="run guards G1 to G6 and G8 against the committed baselines")
    args = parser.parse_args(argv)
    tree, coupling = measure_repo()
    if args.command == "summary":
        print(json.dumps(metrics(tree, coupling), indent=2, sort_keys=True))
    elif args.command == "tables":
        print(json.dumps(tables(tree, coupling), indent=1, sort_keys=True))
    elif args.command == "check":
        baselines = json.loads(BASELINES.read_text(encoding="utf-8"))
        findings = check(tree, coupling, baselines)
        for guard, items in findings.items():
            print(f"{guard}: {len(items)} findings")
            for item in items:
                print(f"  {item}")
        return 1 if any(findings.values()) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
