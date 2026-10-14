"""Adversarial regression cases for the workspace storage and migration lane."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import storage
from pyflightstream.workspace.sidecars import migrate_geometry_layout
from tests.tier1_offline.test_goal035_storage import (
    _shared_product_workspace,
    _sync_pair,
    _write,
    _ws,
)
from tests.tier1_offline.test_p0400_workspace_3_storage import (
    FULL,
    _compacted,
    _recorded_sim,
    _rows,
)


def test_p0400_restore_reader_waits_after_folder_is_published(tmp_path, monkeypatch):
    workspace = _ws(tmp_path, "publish")
    _compacted(workspace, "5101", FULL)
    results = []
    errors = []
    started = threading.Event()

    def reader():
        started.set()
        try:
            results.append(storage.ensure_sim_expanded(workspace, "5101", reason="second"))
        except BaseException as error:
            errors.append(error)

    second = threading.Thread(target=reader)
    real = Path.replace

    def publish(path, target):
        result = real(path, target)
        if Path(target) == workspace.sim_dir("5101"):
            second.start()
            assert started.wait(2)
            second.join(timeout=0.2)
        return result

    monkeypatch.setattr(Path, "replace", publish)
    assert storage.ensure_sim_expanded(workspace, "5101", reason="first")
    second.join(timeout=5)
    assert not second.is_alive()
    assert not errors
    assert results == [False]


def test_p0400_delete_records_regeneration_failure(tmp_path):
    workspace = _shared_product_workspace(tmp_path, "regeneration")
    # A fresh interpreter isolates a public stage registration from the suite.
    code = """
import sys
from pyflightstream.workspace import register_post_stage
from pyflightstream.workspace.storage import delete_sims
@register_post_stage
def fails(*args, **kwargs):
    raise RuntimeError("post failed")
delete_sims(sys.argv[1], ["3001"], matrix_products="regenerate", apply=True)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(workspace.root)],
        env={**os.environ, "PYTHONPATH": str(Path(storage.__file__).resolve().parents[2])},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1 and "post failed" in result.stderr, result.stderr
    calls = storage.read_storage_calls(workspace.root)
    assert calls[-1]["applied"] is True
    assert "interrupted" in calls[-1]
    assert "post failed" in calls[-1]["interrupted"]
    tombstone = next(row for row in _rows(workspace) if row.get("deleted_sim") == "3001")
    assert calls[tombstone["storage_entry"]] == calls[-1]


def test_p0400_sync_expands_under_runs_lease(tmp_path, monkeypatch):
    main, other = _sync_pair(tmp_path, "expandlease")
    _compacted(main, "5102", FULL)
    _write(other.sim_dir("5102") / "scripts" / "point.fs", "s")
    held = []
    real = zipfile.ZipFile.extract

    def watching(*args, **kwargs):
        held.append((main.root / "runs.json.lock").is_file())
        return real(*args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "extract", watching)
    storage.sync_workspaces(main.root, "runs", apply=True)
    assert held and all(held)


def test_p0400_sync_copy_failure_records_committed_runs(tmp_path, monkeypatch):
    main, other = _sync_pair(tmp_path, "copyfailure")
    _recorded_sim(other, "5103", FULL)

    real = shutil.copy2

    def fails(source, *args, **kwargs):
        if other.sim_dir("5103") in Path(source).parents:
            raise OSError("copy failed")
        return real(source, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", fails)
    with pytest.raises(OSError, match="copy failed"):
        storage.sync_workspaces(main.root, "runs", apply=True)
    entry = storage.read_storage_calls(main.root)[-1]
    assert "copy failed" in entry["interrupted"]
    assert "runs" in entry
    assert entry["runs"]["added"] == ["camp/sim_5103/AL+000"]
    assert entry["runs"]["records_after"] == len(_rows(main))


def test_p0400_sync_preview_reads_conflicts_inside_compacted_sim(tmp_path):
    main, other = _sync_pair(tmp_path, "previewzip")
    archive = _compacted(main, "5105", FULL)
    _write(other.sim_dir("5105") / "scripts" / "point.fs", "changed")
    preview = storage.sync_workspaces(main.root, "runs")[0]
    assert archive.is_file()
    applied = storage.sync_workspaces(main.root, "runs", apply=True)[0]
    assert preview["files"]["conflicts"] == applied["files"]["conflicts"]
    assert preview["files"]["to_copy"] == applied["files"]["to_copy"]


@pytest.mark.parametrize("incoming_archive", [False, True])
@pytest.mark.parametrize("apply", [False, True])
def test_p0400_sync_refuses_folder_archive_collision(tmp_path, incoming_archive, apply):
    main, other = _sync_pair(tmp_path, "collision")
    if incoming_archive:
        _compacted(other, "5104", FULL)
        _write(main.sim_dir("5104") / "keep.txt", "keep")
    else:
        _compacted(main, "5104", FULL)
        _write(main.sim_dir("5104") / "keep.txt", "keep")
        _write(other.sim_dir("5104") / "scripts" / "point.fs", "incoming")
    before = (main.sim_dir("5104") / "keep.txt").read_bytes()
    with pytest.raises(storage.StorageError, match="5104"):
        storage.sync_workspaces(main.root, "all", apply=apply)
    assert (main.sim_dir("5104") / "keep.txt").read_bytes() == before


@pytest.mark.parametrize("reference", ["te.txt", "./te.txt"])
def test_p0400_migration_refuses_shared_points_before_moving(tmp_path, reference):
    directory = tmp_path / "inputs" / "geometries"
    for stem in ("left", "right"):
        _write(directory / f"{stem}.stl", "mesh")
        _write(
            directory / f"{stem}.boundaries.toml",
            f'[trailing_edges]\nfile = "{reference}"\n',
        )
    _write(directory / "te.txt", "0 0 0")
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    with pytest.raises(InputArtifactError, match="te.txt"):
        migrate_geometry_layout(directory.parent)
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


def test_p0400_lane_regressions_carry_release_in_test_names():
    missing = []
    # The tests tree itself, not a path through the package: the release workflow runs
    # these tests against the installed wheel, where the package has no tests beside it.
    directory = Path(__file__).resolve().parent
    paths = list(directory.glob("test_p0400_workspace_3_*.py"))
    assert len(paths) >= 3
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                if not node.name.startswith("test_p0400_"):
                    missing.append(f"{path.name}:{node.name}")
    assert not missing, missing
