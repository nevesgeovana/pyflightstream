"""PFS-2083.002: every root module has a layer, the guards check all of them, and a planted
upward import through a root module is refused.

The rows live in `test_conventions._ROOT_UNIT_ROWS`. These tests plant a package
tree in `tmp_path` (never the real one) and run the real guards on it: the
unranked-unit guard, the module-level scanner and the function-body scanner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tests.tier1_offline.test_conventions as conv
from tests.tier1_offline.test_goal028_module_level_layering import _upward_module_level_imports


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "pyflightstream"
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def _findings(root: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Everything the real guards say about the planted tree: unranked units and upward imports."""
    monkeypatch.setattr(conv, "_SRC", root)
    out = [f"unranked {name}" for name in conv._unranked_root_units(root)]
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        dotted = ("pyflightstream." + rel).removesuffix(".__init__")
        source = path.read_text(encoding="utf-8")
        out += [
            f"{rel} module-level {t}"
            for t in _upward_module_level_imports(
                dotted, source, is_package=path.name == "__init__.py"
            )
        ]
        out += [f"{rel} deferred {o}" for o in conv._upward_function_body_imports(path)]
    return out


_CLEAN = {
    "__init__.py": "",
    "post/__init__.py": "",
    "run/__init__.py": "",
    "commands/__init__.py": "",
    "_errors.py": "",
    "_cli.py": "from pyflightstream import _errors\n",
    "utils/__init__.py": "from pyflightstream import commands\nfrom pyflightstream import _cli\n",
    "exceptions.py": "from pyflightstream import post, run\n",
}


def test_the_planted_clean_tree_is_the_control(tmp_path, monkeypatch):
    """Downward edges and an exceptions catalog nobody imports: nothing is reported."""
    assert _findings(_tree(tmp_path, _CLEAN), monkeypatch) == []


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        ("_cli.py", "from pyflightstream.post import x\n", "_cli module-level pyflightstream.post"),
        (
            "_cli.py",
            "def f():\n    from pyflightstream.run import x\n",
            "_cli deferred",
        ),
        (
            "extras.py",
            "from pyflightstream.exceptions import SomeError\n",
            "extras module-level pyflightstream.exceptions",
        ),
        (
            "utils/tool.py",
            "from pyflightstream.fsi import beam\n",
            "utils.tool module-level pyflightstream.fsi",
        ),
        (
            "options.py",
            "import pyflightstream.utils\n",
            "options module-level pyflightstream.utils",
        ),
    ],
)
def test_a_planted_upward_import_through_a_root_module_is_refused(
    tmp_path, monkeypatch, name, text, expected
):
    files = {**_CLEAN, "fsi/__init__.py": "", "fsi/beam.py": "", "extras.py": "", "options.py": ""}
    files[name] = text
    found = _findings(_tree(tmp_path, files), monkeypatch)
    assert any(f.startswith(expected) for f in found), found


def test_a_planted_unranked_root_module_is_refused(tmp_path, monkeypatch):
    files = {**_CLEAN, "_brand_new.py": "", "newpkg/__init__.py": ""}
    found = _findings(_tree(tmp_path, files), monkeypatch)
    assert "unranked _brand_new" in found and "unranked newpkg" in found


def test_a_root_module_with_a_row_is_not_reported_unranked(tmp_path, monkeypatch):
    """Control for the test above: a ranked unit and the named exception are not refused."""
    assert _findings(_tree(tmp_path, _CLEAN), monkeypatch) == []
    assert conv._unranked_root_units(_tree(tmp_path / "again", _CLEAN), {"post": 0}) != []


def test_the_real_tree_has_no_unranked_unit_and_the_named_list_has_one_entry():
    assert conv._unranked_root_units(conv._SRC) == []
    assert list(conv._NAMED_UNRANKED_ROOT_UNITS) == ["__init__"]


def test_the_exceptions_catalog_is_imported_by_no_module_of_the_package():
    """It ranks at the top and imports every layer; that is safe only while nobody imports it."""
    importers = []
    for path in sorted(conv._SRC.rglob("*.py")):
        if path.name == "exceptions.py" and path.parent == conv._SRC:
            continue
        rel = path.relative_to(conv._SRC).with_suffix("")
        package = ".".join(["pyflightstream", *rel.parts[:-1]])
        if "pyflightstream.exceptions" in conv._imported_module_names(
            path.read_text(encoding="utf-8"), package
        ):
            importers.append(rel.as_posix())
    assert importers == []
