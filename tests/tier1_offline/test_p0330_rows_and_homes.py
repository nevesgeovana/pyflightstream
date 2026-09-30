"""Tier 1, 0.33.0 work packages WP1 and WP2: the rows are true and every constant has one home.

WP1 (AD-09): the layer table gains a row, ``run`` alone above ``workspace``
alone, and nothing of ``workspace`` imports ``run`` at any depth: at module
level, inside a function body or under ``TYPE_CHECKING``. The two imports that
pointed up on v0.32.0 are gone: the manifest-name rule moved down into
``workspace.naming``, and the rebuild a restoring sync asks for is registered
by ``run.records`` with ``workspace.storage`` instead of being imported by it.

WP2 (AD-10): the constants v0.32.0 defined twice each have one home, and
``results`` imports nothing of ``fsi``.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pyflightstream
from pyflightstream import exceptions
from pyflightstream.overview import _CORE_LAYERS
from pyflightstream.run import records
from pyflightstream.workspace import naming

_SRC = Path(pyflightstream.__file__).parent


def _imports_at_any_depth(source: str, package: str) -> set[str]:
    """Every dotted module an import statement of ``source`` may name, at any depth.

    ``ast.walk`` reaches module-level statements, function bodies and
    ``if TYPE_CHECKING:`` blocks alike; a relative import is resolved against
    ``package``, and both readings of a ``from`` import are kept.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                base = f"{base}.{node.module}" if node.module else base
            else:
                base = node.module or ""
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def _package_imports(folder: str, target: str) -> list[str]:
    """Each ``module -> imported`` pair of ``pyflightstream.<folder>`` naming ``target``."""
    found = []
    root = _SRC / folder
    for path in sorted(root.rglob("*.py")):
        dotted = "pyflightstream." + path.relative_to(_SRC).with_suffix("").as_posix()
        dotted = dotted.replace("/", ".").removesuffix(".__init__")
        package = dotted if path.name == "__init__.py" else dotted.rsplit(".", 1)[0]
        for name in _imports_at_any_depth(path.read_text(encoding="utf-8"), package):
            if name == target or name.startswith(target + "."):
                found.append(f"{dotted} -> {name}")
    return sorted(found)


# ------------------------------------------------------------------ WP1


def test_run_is_a_row_alone_above_workspace_alone():
    # P0330-WP1 (AD-09, decision 4): seven core rows, run alone directly
    # above workspace alone.
    rows = [names for names, _ in _CORE_LAYERS]
    assert len(rows) == 7, rows
    assert ("run",) in rows and ("workspace",) in rows, rows
    assert rows.index(("run",)) + 1 == rows.index(("workspace",)), rows


def test_no_workspace_module_imports_run_at_any_depth():
    # P0330-WP1 (AD-09): zero workspace -> run imports, deferred and
    # annotation-only included.
    assert _package_imports("workspace", "pyflightstream.run") == []


def test_the_any_depth_reader_sees_a_deferred_and_an_annotation_import():
    # P0330-WP1: non-vacuity of the reader above; a function-body import and
    # a TYPE_CHECKING import of the run layer are both seen.
    planted = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from ..run import records\n"
        "def f():\n"
        "    import pyflightstream.run.collect\n"
    )
    seen = _imports_at_any_depth(planted, "pyflightstream.workspace")
    assert "pyflightstream.run.records" in seen
    assert "pyflightstream.run.collect" in seen


def test_the_manifest_name_rule_has_one_home_in_the_workspace():
    # P0330-WP1 (AD-09): resolve_manifest moved down into workspace.naming;
    # its 0.32.0 path in run.records and the exception catalog name the same
    # objects, so nothing that imported them breaks.
    assert records.resolve_manifest is naming.resolve_manifest
    assert records.RunsManifestError is naming.RunsManifestError
    assert exceptions.RunsManifestError is naming.RunsManifestError
    assert records.DEFAULT_MANIFEST == naming.DEFAULT_MANIFEST == "runs.json"


def test_importing_the_storage_layer_registers_the_records_rebuild():
    # P0330-WP1 (AD-09, FR-221): the storage layer imports nothing of the
    # run, and the package root loads the run records, which register the
    # rebuild a restoring sync calls; a library caller that imports only
    # workspace.storage still gets it.
    probe = (
        "import sys\n"
        "import pyflightstream.workspace.storage as storage\n"
        "print('pyflightstream.run.records' in sys.modules)\n"
        "print(storage.register_records_rebuild.__module__)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(_SRC.parent)}
    done = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        cwd=_SRC.parents[1],
        env=env,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["True", "pyflightstream.workspace.storage"]
