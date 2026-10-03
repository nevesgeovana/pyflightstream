"""P0360-MATURITY (FR-409): one maturity row per affirmed public module."""

from __future__ import annotations

import ast
import importlib.util
import runpy
from pathlib import Path

import pytest

from tests.tier1_offline.test_public_api import PUBLIC_MODULES

REPO = Path(__file__).resolve().parents[2]
TABLE = REPO / "src" / "pyflightstream" / "_maturity.py"
LEVELS = {"stable", "provisional", "experimental", "internal"}


def _checked_table(source: str, public: list[str]) -> dict[str, str]:
    assignments = [
        node.value
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "MATURITY" for target in node.targets)
    ]
    assert len(assignments) == 1, "MATURITY must have one literal table"
    table = assignments[0]
    assert isinstance(table, ast.Dict), "MATURITY must be a literal dict"
    keys = [ast.literal_eval(key) for key in table.keys]
    assert len(keys) == len(set(keys)), "duplicate maturity row"
    rows = ast.literal_eval(table)
    assert not (set(public) - rows.keys()), "public modules missing maturity rows"
    assert not (rows.keys() - set(public)), "maturity rows for non-public modules"
    assert set(rows.values()) <= LEVELS, "unknown maturity level"
    assert "internal" not in rows.values(), "internal modules are not public"
    return rows


def _reference_pages() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location(
        "maturity_reference", REPO / "scripts" / "gen_api_reference.py"
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    return generator.api_reference_pages()


def _assert_rendered(pages: dict[str, str], rows: dict[str, str]) -> None:
    for module, level in rows.items():
        slug = module.removeprefix("pyflightstream.").replace(".", "/")
        assert pages[f"{slug}.md"].splitlines()[0] == f"# `{module}` ({level})", module
        assert f"| [`{module}`]({slug}.md) | {level} |" in pages["index.md"], module


def test_public_modules_have_exactly_one_maturity():
    """P0360-MATURITY (FR-409): uniqueness, enum and both set differences."""
    assert TABLE.is_file(), "the committed maturity table is missing"
    rows = _checked_table(TABLE.read_text(encoding="utf-8"), PUBLIC_MODULES)
    assert rows, "the coverage check must read public modules"


def test_maturity_controls_reject_missing_extra_duplicate_and_unknown_rows():
    """P0360-MATURITY (FR-409): each planted defect fails the real table check."""
    source = TABLE.read_text(encoding="utf-8")
    rows = _checked_table(source, PUBLIC_MODULES)
    with pytest.raises(AssertionError, match="public modules missing"):
        _checked_table(source, [*PUBLIC_MODULES, "pyflightstream.planted_public"])
    extra = {**rows, "pyflightstream._planted_private": "stable"}
    with pytest.raises(AssertionError, match="non-public"):
        _checked_table(f"MATURITY = {extra!r}", PUBLIC_MODULES)
    module = PUBLIC_MODULES[0]
    unknown = {**rows, module: "unknown"}
    with pytest.raises(AssertionError, match="unknown maturity level"):
        _checked_table(f"MATURITY = {unknown!r}", PUBLIC_MODULES)
    duplicate = repr(rows)[:-1] + f", {module!r}: {rows[module]!r}" + "}"
    with pytest.raises(AssertionError, match="duplicate maturity row"):
        _checked_table(f"MATURITY = {duplicate}", PUBLIC_MODULES)


def test_generated_reference_shows_each_modules_maturity():
    """P0360-MATURITY (FR-409): the reference renders the table beside each heading."""
    rows = _checked_table(TABLE.read_text(encoding="utf-8"), PUBLIC_MODULES)
    pages = _reference_pages()
    _assert_rendered(pages, rows)
    module = PUBLIC_MODULES[0]
    slug = module.removeprefix("pyflightstream.").replace(".", "/")
    cut = {**pages, f"{slug}.md": pages[f"{slug}.md"].replace(f" ({rows[module]})", "", 1)}
    with pytest.raises(AssertionError, match=module):
        _assert_rendered(cut, rows)
    wrong = {
        **pages,
        "index.md": pages["index.md"].replace(
            f"| [`{module}`]({slug}.md) | {rows[module]} |",
            f"| [`{module}`]({slug}.md) | unknown |",
            1,
        ),
    }
    with pytest.raises(AssertionError, match=module):
        _assert_rendered(wrong, rows)


@pytest.mark.parametrize(
    ("defect", "message"),
    [("missing", "missing rows"), ("extra", "non-public rows"), ("unknown", "unknown maturity")],
)
def test_reference_validation_refuses_planted_table_defects(defect, message):
    """P0360-MATURITY (FR-409): the generator's validation also refuses the controls."""
    # Each control owns a fresh table; no installed module or patch target changes.
    namespace = runpy.run_path(str(TABLE))
    table = namespace["MATURITY"]
    validate = namespace["validate_maturity"]
    validate(PUBLIC_MODULES)
    public = list(PUBLIC_MODULES)
    if defect == "missing":
        public.append("pyflightstream.planted_public")
    elif defect == "extra":
        table["pyflightstream._planted_private"] = "stable"
    else:
        table[public[0]] = "unknown"
    with pytest.raises(ValueError, match=message):
        validate(public)
