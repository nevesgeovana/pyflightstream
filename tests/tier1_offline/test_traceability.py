"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


TESTS = REPO / "tests"


INDEX = REPO / "reports" / "requirements-index.json"


def _marked() -> dict[str, list[str]]:
    """Read decorators and module/class pytestmark assignments, including lists."""
    from scripts._requirements_paths import migrated_uids

    aliases = migrated_uids(REPO)
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                candidates = node.decorator_list
                location = node.name
            elif isinstance(node, ast.Assign | ast.AnnAssign):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
                    continue
                candidates = list(ast.walk(node.value)) if node.value is not None else []
                location = f"pytestmark:{node.lineno}"
            else:
                continue
            for decorator in candidates:
                if not isinstance(decorator, ast.Call):
                    continue
                target = decorator.func
                parts = []
                while isinstance(target, ast.Attribute):
                    parts.append(target.attr)
                    target = target.value
                if parts[:1] != ["requirement"] or "mark" not in parts:
                    continue
                for argument in decorator.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        found.setdefault(aliases.get(argument.value, argument.value), []).append(
                            f"{path.relative_to(REPO).as_posix()}::{location}"
                        )
    return found


def _live_identifiers() -> set[str]:
    from scripts._requirements_paths import read_l3, roadmap_uids
    from scripts.gen_requirements_index import SRS, collect

    # Since the 0.43.0 trim, L3 detail rows live beside the tests and keep their identities,
    # and parked candidates keep theirs on the roadmap page: a test may still exercise the
    # partial behaviour of a parked candidate. Neither kind is counted by the index.
    live = {entry["id"] for entry in collect(SRS)}
    return live | {row["uid"] for row in read_l3(REPO)} | roadmap_uids(REPO)


def test_p0440_marker_scan_includes_module_and_class_assignments(tmp_path, monkeypatch):
    import sys

    (tmp_path / "test_control.py").write_text(
        'pytestmark = [pytest.mark.requirement("MODULE"), pytest.mark.slow]\n'
        "class TestControl:\n"
        '    pytestmark: object = pytest.mark.requirement("CLASS")\n'
        '    @pytest.mark.requirement("METHOD")\n'
        "    def test_control(self): pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "TESTS", tmp_path)
    assert set(_marked()) == {"MODULE", "CLASS", "METHOD"}


def test_every_marker_resolves_to_a_live_requirement():
    """A marker naming a withdrawn or misspelled identifier traces nothing.

    This is the half of NFR-13 that is closed rather than ratcheted: it
    holds completely today and cannot silently stop holding.
    """
    live = _live_identifiers()
    marked = _marked()
    assert marked, "no requirement markers found at all; the AST scan is broken"
    dangling = sorted(set(marked) - live)
    assert not dangling, (
        f"these markers name identifiers the SRS does not publish: {dangling}. A "
        "marker that resolves to nothing is worse than no marker, because the "
        "index counts it"
    )


def test_the_marker_is_registered_so_a_typo_is_not_silent():
    """An unregistered pytest mark is a warning, not an error, by default.

    The marker is declared in pyproject, and this asserts the
    declaration, because a renamed marker would otherwise make every
    marked test lose its trace while the suite stayed green.
    """
    config = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'"requirement\(identifier\):', config), (
        "the requirement marker is not registered in pyproject's markers list"
    )
