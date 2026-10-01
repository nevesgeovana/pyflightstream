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
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pyflightstream
from pyflightstream import exceptions
from pyflightstream.overview import _CORE_LAYERS
from pyflightstream.run import _record_files as record_files
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


def test_importing_the_storage_layer_registers_the_records_rebuild(tmp_path):
    # P0330-WP1 (AD-09, FR-221): the storage layer imports nothing of the
    # run, and the package root loads the run records, which register the
    # rebuild a restoring sync calls; a library caller that imports only
    # workspace.storage, in a fresh interpreter, still gets it. Read by what
    # the restore answers: the real rebuild's refusal of a workspace with no
    # matrix, never the "nothing is registered" error.
    root = tmp_path / "ws"
    (root / "sims" / "sim_1").mkdir(parents=True)
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "import pyflightstream.workspace.storage as storage\n"
        "print('pyflightstream.run.records' in sys.modules)\n"
        "print(storage.register_records_rebuild.__module__)\n"
        "outcome = storage._restore_orphans(Path(sys.argv[1]), ['1'])\n"
        "print(outcome['error'].startswith('no records rebuild is registered'))\n"
        "print(outcome['asked'], outcome['sims'] == ['1'], outcome['result'] is None)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(_SRC.parent)}
    done = subprocess.run(
        [sys.executable, "-c", probe, str(root)],
        capture_output=True,
        text=True,
        check=False,
        cwd=_SRC.parents[1],
        env=env,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == [
        "True",
        "pyflightstream.workspace.storage",
        "False",
        "True",
        "True",
        "True",
    ]


def _storage_loaded_by_path():
    """A copy of ``workspace/storage.py`` loaded by its path, apart from the package.

    Its registry is its own and empty, the case of a caller that loads the
    file by path; the package's registry is untouched.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "p0330_storage_by_path", _SRC / "workspace" / "storage.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses look their module up while it executes.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


def test_a_restore_with_nothing_registered_names_it_and_a_registered_one_is_called(tmp_path):
    # P0330-WP1 (AD-09, FR-221): with nothing registered the restore block
    # names the missing registration in its error and does not raise; once a
    # rebuild is registered it is called with (root, sims) and its block is
    # the answer; the registry holds exactly one: a rebuild of the same module
    # replaces it (a reload), one of another module is not taken.
    storage = _storage_loaded_by_path()
    root = tmp_path / "ws"
    empty = storage._restore_orphans(root, ["2002", "3000"])
    assert empty["asked"] is True
    assert empty["sims"] == ["2002", "3000"]
    assert empty["result"] is None
    assert empty["error"].startswith("no records rebuild is registered")

    calls: list[tuple[Path, list[str]]] = []

    def first(at: Path, sims: list[str]) -> dict:
        calls.append((at, sims))
        return {"asked": True, "sims": sims, "result": {"by": "first"}, "error": None}

    def second(at: Path, sims: list[str]) -> dict:
        calls.append((at, sims))
        return {"asked": True, "sims": sims, "result": {"by": "second"}, "error": None}

    assert storage.register_records_rebuild(first) is first
    assert storage._restore_orphans(root, ["2002"])["result"] == {"by": "first"}
    assert storage.register_records_rebuild(second) is second
    assert storage._restore_orphans(root, ["3000"])["result"] == {"by": "second"}

    def foreign(at: Path, sims: list[str]) -> dict:
        calls.append((at, sims))
        return {"asked": True, "sims": sims, "result": {"by": "foreign"}, "error": None}

    # A copy of the records executed under another module name is not taken,
    # and the return names the rebuild still held.
    foreign.__module__ = "records_mutant_copy"
    assert storage.register_records_rebuild(foreign) is second
    assert storage._restore_orphans(root, ["2002"])["result"] == {"by": "second"}
    assert calls == [(root, ["2002"]), (root, ["3000"]), (root, ["2002"])]


# ------------------------------------------------------------------ WP2

_BASELINES = json.loads(
    (Path(__file__).parent / "architecture_baselines.json").read_text(encoding="utf-8")
)


def test_the_one_home_allowlist_is_empty():
    # P0330-WP2 (AD-10): every constant v0.32.0 defined twice has one home,
    # so guard G6 runs with nothing allowed.
    assert _BASELINES["one_home_allowlist"] == []


def test_the_archive_stamp_pattern_matches_its_spelling():
    # P0330-WP2 (AD-10): the run records read archive stamps with the pattern
    # that lives beside the spelling, and the two agree.
    stamp = datetime.datetime(2026, 9, 30, 7, 5, 9).strftime(naming.ARCHIVE_STAMP)
    assert re.fullmatch(naming.ARCHIVE_STAMP_PATTERN, stamp)
    # Negative controls: a pattern that took anything would pass the line above.
    for wrong in ("2026-09-30", "20260930_070509", "20260930-0705", "2026093-0070509", ""):
        assert not re.fullmatch(naming.ARCHIVE_STAMP_PATTERN, wrong), wrong
    # Since 0.33.0 (AD-11) the stamp is written by run._record_files, under records.
    assert record_files.ARCHIVE_STAMP == naming.ARCHIVE_STAMP
    assert records.ARCHIVE_DIR == naming.ARCHIVE_DIR == "archive"


def test_results_imports_nothing_of_fsi_at_any_depth():
    # P0330-WP2 (AD-10, decision 15): the fsi.loads <-> results.tables cycle
    # is gone because results names nothing of fsi.
    assert _package_imports("results", "pyflightstream.fsi") == []
    for component in _BASELINES["baseline_sccs"]:
        assert "pyflightstream.fsi.loads" not in component, component


def test_the_sectional_loads_parser_has_one_home_in_results():
    # P0330-WP2 (AD-10): parse_sectional_loads and its report are defined in
    # results.sectional_loads; fsi.loads re-exports every name it had, and
    # the coupling's refusal is the floor's.
    from pyflightstream import _errors
    from pyflightstream.fsi import errors as fsi_errors
    from pyflightstream.fsi import loads
    from pyflightstream.results import sectional_loads

    for name in (
        "parse_sectional_loads",
        "SectionalLoadsReport",
        "SectionBlock",
        "UnitsError",
        "EXPECTED_COLUMNS",
    ):
        assert getattr(loads, name) is getattr(sectional_loads, name), name
    assert sectional_loads.parse_sectional_loads.__module__ == sectional_loads.__name__
    assert fsi_errors.FsiInputError is _errors.FsiInputError
    assert exceptions.UnitsError is sectional_loads.UnitsError
    assert issubclass(fsi_errors.FsiInputError, ValueError)


def test_the_csv_reader_has_one_home_in_post_tables():
    # P0330-WP2 (AD-10): read_csv_table and the plots-table readers live in
    # post._tables; post.products re-exports them in its unchanged __all__,
    # and post.corrections reads tables without importing post.products.
    from pyflightstream.post import _tables, products

    for name in ("read_csv_table", "plots_table_series"):
        assert getattr(products, name) is getattr(_tables, name), name
        assert name in products.__all__, name
    corrections = _SRC / "post" / "corrections.py"
    reached = _imports_at_any_depth(corrections.read_text(encoding="utf-8"), "pyflightstream.post")
    assert not any(name.startswith("pyflightstream.post.products") for name in reached)


def test_both_post_modules_refuse_a_removed_name_through_one_hook():
    # P0330-WP2 (AD-10): the duplicated module __getattr__ of post and
    # post.products became one helper; each still names the replacement and
    # still says a plain AttributeError for any other name.
    import pytest

    import pyflightstream.post as post
    from pyflightstream.post import products

    for module in (post, products):
        with pytest.raises(AttributeError, match="CustomPolarTable"):
            module.HerPolarTable  # noqa: B018
        with pytest.raises(AttributeError, match="has no attribute 'no_such_name'"):
            module.no_such_name  # noqa: B018


def test_the_dead_private_helpers_are_gone():
    # P0330-WP2 (AD-10, GEO-072 4.4): three private helpers are deleted. A
    # tombstone only: it holds the deletion, not the absence of a caller,
    # which rests on the git grep of the tracked files named in the WP2
    # review-fix commit message (no caller of any of the three).
    # cases/workflows.py is the package cases/workflows/ since 0.33.0 (AD-12):
    # the tombstone reads every module of it.
    workflows = sorted((_SRC / "cases" / "workflows").glob("*.py"))
    assert workflows
    for path, definition in (
        *((path, "def _passages(") for path in workflows),
        *((path, "def _output(") for path in workflows),
        (_SRC / "cases" / "matrix.py", "def _cell_value("),
    ):
        assert definition not in path.read_text(encoding="utf-8"), path
