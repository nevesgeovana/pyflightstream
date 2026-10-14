"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest

import pyflightstream

_SRC = Path(pyflightstream.__file__).parent


_FROZEN: tuple[tuple[str, str], ...] = (
    ("cases.windows", "script._surface_averaging"),
    ("cases.workflows._exports", "script._surface_averaging"),
    ("cases.workflows._skeleton", "script._settings"),
    ("post.farfield_fields", "cases._farfield_spec"),
    ("post.farfield_products", "cases._farfield_spec"),
    ("qa.matrix", "workspace._matrix_homes"),
    ("run._assemble", "workspace._batch_life"),
    ("run._batch_collect", "cases.workflows._batch_script"),
    ("run._batch_collect", "workspace._batch_relocate"),
    ("run._batch_collect", "workspace._batches"),
    ("run._batch_collect", "workspace._missing_log"),
    ("run._batch_exec", "workspace._batches"),
    ("run._batch_plan", "cases._unsteady_actions"),
    ("run._batch_plan", "cases.workflows._batch_actions"),
    ("run._batch_plan", "cases.workflows._batch_script"),
    ("run._batch_plan", "cases.workflows._rows"),
    ("run._batch_plan", "workspace._batches"),
    ("run._batch_plan", "workspace._geometry_clean"),
    ("run._batch_run", "cases._unsteady_actions"),
    ("run._batch_run", "cases.workflows._batch_actions"),
    ("run._batch_run", "cases.workflows._batch_script"),
    ("run._batch_run", "workspace._batches"),
    ("run._campaign", "workspace._settings_file"),
    ("run._cli_geometry", "workspace._geometry_build"),
    ("run._cli_geometry", "workspace._geometry_convert"),
    ("run._cli_mesh", "cases.workflows._vocabulary"),
    ("run._cli_mesh", "workspace._geometry_clean"),
    ("run._collect_logs", "workspace._batches"),
    ("run._grouped", "workspace._batches"),
    ("run._identity", "workspace._settings_file"),
    ("run._mark_converged", "workspace._verdicts"),
    ("run._plan", "cases._skipped_families"),
    ("run._plan", "cases.workflows._farfield"),
    ("run._plan", "cases.workflows._freestream"),
    ("run._plan", "workspace._batches"),
    ("run._plan", "workspace._settings_file"),
    ("run._points", "cases._skipped_families"),
    ("run._rebuild", "workspace._matrix_homes"),
    ("run._rebuild_evidence", "workspace._batches"),
    ("run._rebuild_evidence", "workspace._matrix_homes"),
    ("run._rebuild_evidence", "workspace._script_comparison"),
    ("run._rebuild_grouped", "workspace._batches"),
    ("run._sweep", "cases._skipped_families"),
    ("run._wake_edge_verdict", "workspace._missing_log"),
    ("run.cli", "workspace._matrix_homes"),
    ("run.collect", "workspace._batches"),
    ("run.collect", "workspace._missing_log"),
    ("run.matrix", "workspace._geometry_clean"),
    ("run.matrix", "workspace._matrix_homes"),
    ("workspace", "script._surface_averaging"),
    ("workspace._geometry_build", "cases._geometry_emit"),
    ("workspace._geometry_build", "cases._geometry_instruction"),
    ("workspace._geometry_convert", "cases._ccs"),
    ("workspace._geometry_convert", "cases._geometry_instruction"),
    ("workspace._geometry_instruction", "cases._ccs"),
    ("workspace._geometry_instruction", "cases._geometry_instruction"),
    ("workspace._geometry_record", "cases._ccs"),
    ("workspace._geometry_record", "cases._geometry_instruction"),
    ("workspace._row_setup", "cases.workflows._freestream"),
    ("workspace.manifest", "script._surface_averaging"),
    ("workspace.sidecars", "cases._ccs"),
    ("workspace.sidecars", "cases._geometry_instruction"),
    ("workspace.sidecars", "cases.workflows._vocabulary"),
)


def _module_exists(root: Path, dotted: str) -> bool:
    parts = dotted.split(".")
    if parts[0] != "pyflightstream" or len(parts) < 2:
        return False
    target = root.joinpath(*parts[1:])
    return target.with_suffix(".py").is_file() or (target / "__init__.py").is_file()


def measure_private_cross_package_imports(root: Path) -> set[tuple[str, str]]:
    """Every (importer, imported) private cross-package module pair under ``root``."""
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).with_suffix("")
        parts = list(rel.parts)
        if len(parts) < 2 and parts[-1] == "__init__":
            continue
        unit = parts[0]
        if not (root / unit).is_dir():
            continue  # a root-level module is not inside a package
        importer = ".".join(["pyflightstream", *[p for p in parts if p != "__init__"]])
        package = ["pyflightstream", *parts[:-1]]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base_parts = package[: len(package) - node.level + 1]
                    base = ".".join([*base_parts, *([node.module] if node.module else [])])
                else:
                    base = node.module or ""
                if base:
                    candidates = [base, *[f"{base}.{alias.name}" for alias in node.names]]
            for name in candidates:
                pieces = name.split(".")
                if len(pieces) < 3 or pieces[0] != "pyflightstream":
                    continue
                if pieces[1] == unit or not (root / pieces[1]).is_dir():
                    continue
                if not any(p.startswith("_") for p in pieces[2:]):
                    continue
                if _module_exists(root, name):
                    found.add(
                        (
                            importer.removeprefix("pyflightstream."),
                            name.removeprefix("pyflightstream."),
                        )
                    )
    return found


def ratchet_verdict(
    measured: set[tuple[str, str]], frozen: set[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(new, gone): pairs measured but not frozen, and pairs frozen but no longer measured."""
    return sorted(measured - frozen), sorted(frozen - measured)


@pytest.mark.requirement("NFR-23")
def test_private_cross_package_imports_are_frozen_and_shrink_only():
    """P0400-PRIVATEIMPORT: a new pair fails; a removed pair asks for the list to shrink."""
    measured = measure_private_cross_package_imports(_SRC)
    # Non-vacuity: the three families the decision names are read.
    assert measured, "the import walk found no pairs"
    frozen = set(_FROZEN)
    assert len(frozen) == len(_FROZEN), "a pair is listed twice"
    new, gone = ratchet_verdict(measured, frozen)
    assert not new, (
        "NEW private cross-package imports (a package importing another package's private "
        "module); move the shared code to a public home or a module below both, do not add "
        f"to the list: {new}"
    )
    if gone:
        warnings.warn(
            f"P0400-PRIVATEIMPORT: these listed imports no longer exist, remove them from "
            f"_FROZEN so the freeze shrinks: {gone}",
            stacklevel=1,
        )


def _plant(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "pyflightstream"
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


_BASE_TREE = {
    "__init__.py": "",
    "run/__init__.py": "",
    "run/a.py": "",
    "workspace/__init__.py": "",
    "workspace/_priv.py": "VALUE = 1\n",
    "workspace/public.py": "",
}


def test_a_planted_new_private_import_is_refused_and_a_removed_one_asks_to_shrink(tmp_path):
    frozen: set[tuple[str, str]] = set()
    root = _plant(
        tmp_path, {**_BASE_TREE, "run/a.py": "from pyflightstream.workspace import _priv\n"}
    )
    measured = measure_private_cross_package_imports(root)
    assert measured == {("run.a", "workspace._priv")}
    new, gone = ratchet_verdict(measured, frozen)
    assert new == [("run.a", "workspace._priv")] and not gone

    # Other spellings of the same import are read: absolute module, relative, deferred.
    for text in (
        "import pyflightstream.workspace._priv\n",
        "from pyflightstream.workspace._priv import VALUE\n",
        "from ..workspace import _priv\n",
        "def f():\n    from pyflightstream.workspace._priv import VALUE\n",
    ):
        root = _plant(tmp_path, {**_BASE_TREE, "run/a.py": text})
        assert measure_private_cross_package_imports(root) == {("run.a", "workspace._priv")}, text

    # Not private cross-package imports: a public module, the own package, a private NAME.
    for text in (
        "from pyflightstream.workspace import public\n",
        "from pyflightstream.workspace.public import VALUE\n",
        "from pyflightstream.workspace import _not_a_module\n",
    ):
        root = _plant(tmp_path, {**_BASE_TREE, "run/a.py": text})
        assert measure_private_cross_package_imports(root) == set(), text
    root = _plant(
        tmp_path,
        {**_BASE_TREE, "run/_own.py": "", "run/a.py": "from pyflightstream.run import _own\n"},
    )
    assert measure_private_cross_package_imports(root) == set()

    # Frozen, then removed: passes the ratchet and names the pair to delete.
    root = _plant(tmp_path, _BASE_TREE)
    new, gone = ratchet_verdict(
        measure_private_cross_package_imports(root), {("run.a", "workspace._priv")}
    )
    assert not new and gone == [("run.a", "workspace._priv")]
