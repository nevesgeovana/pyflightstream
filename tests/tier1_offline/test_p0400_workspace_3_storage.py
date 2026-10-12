"""P0400-WS3-STORAGE: storage commands keep every copy, lease and record they owe."""

from __future__ import annotations

import datetime as dt
import json
import os
import socket
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run.records import restore
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.naming import ARCHIVE_DIR
from tests.tier1_offline.test_goal035_storage import (
    _linked_sim,
    _record,
    _shared_product_workspace,
    _sync_pair,
    _write,
    _write_recipe,
    _ws,
)

StorageError = storage_module.StorageError
DELETED = storage_module.DELETED_SIM_KEY


def _recorded_sim(workspace, sim_id: str, files: dict[str, str], **record) -> None:
    for name, text in files.items():
        _write(workspace.sim_dir(sim_id) / name, text)
    workspace.append_record(_record(sim_id, f"camp/sim_{sim_id}/AL+000", **record))


def _zip(workspace, sim_id: str) -> Path:
    """The archive a compacted simulation is stored as, ``sims/sim_<id>.zip``."""
    folder = workspace.sim_dir(sim_id)
    return folder.with_name(folder.name + storage_module.COMPACTED_SUFFIX)


def _compacted(workspace, sim_id: str, files: dict[str, str]) -> Path:
    """Write, record and compact one simulation; return its archive."""
    _recorded_sim(workspace, sim_id, files)
    _write_recipe(workspace, "m901", f'[[compact_sims]]\nsims = ["{sim_id}"]\n')
    storage_module.free_space(workspace.root, "m901", apply=True)
    archive = _zip(workspace, sim_id)
    assert archive.is_file()
    return archive


def _members(archive: Path) -> set[str]:
    with zipfile.ZipFile(archive) as zf:
        return set(zf.namelist())


def _rows(workspace) -> list[dict]:
    return json.loads(workspace.manifest_path.read_text(encoding="utf-8"))


FULL = {"scripts/point.fs": "s", "datapoints/DP-1/loads.txt": "full"}


# --------------------------------------------------------------------------- PFS-2096.014


def test_p0400_compacting_a_folder_beside_an_archive_is_refused_and_the_archive_kept(tmp_path):
    """P0400-COMPACT-OVER-ZIP (PFS-2096.014): a second compaction never replaces the zip."""
    workspace = _ws(tmp_path, "overzip")
    archive = _compacted(workspace, "4101", FULL)
    members = _members(archive)
    _write(workspace.sim_dir("4101") / "scripts" / "point.fs", "partial")
    entry = storage_module.free_space(workspace.root, "m901", apply=True)
    assert "4101" in entry["steps"][0]["refused"], entry["steps"]
    assert _members(archive) == members


def test_p0400_a_restore_refuses_a_folder_beside_the_archive_naming_both(tmp_path):
    """P0400-RESTORE-BOTH (PFS-2096.014): the folder and the zip together are refused."""
    workspace = _ws(tmp_path, "both")
    archive = _compacted(workspace, "4102", FULL)
    _write(workspace.sim_dir("4102") / "scripts" / "point.fs", "partial")
    with pytest.raises(StorageError) as raised:
        storage_module.ensure_sim_expanded(workspace, "4102", reason="test")
    message = str(raised.value)
    assert str(archive) in message and str(workspace.sim_dir("4102")) in message


def test_p0400_sync_restores_a_compacted_simulation_before_copying_into_it(tmp_path):
    """P0400-SYNC-INTO-ZIP (PFS-2096.014): sync expands main's archive, then copies."""
    main, other = _sync_pair(tmp_path, "zipsync")
    archive = _compacted(main, "4103", FULL)
    _write(other.sim_dir("4103") / "scripts" / "point.fs", "s")
    _write(other.sim_dir("4103") / "datapoints" / "DP-1" / "run_log.txt", "log")
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert entry["expanded"] == ["4103"]
    assert not archive.exists()
    folder = main.sim_dir("4103") / "datapoints" / "DP-1"
    assert (folder / "loads.txt").read_text(encoding="utf-8") == "full"
    assert (folder / "run_log.txt").is_file()


# --------------------------------------------------------------------------- PFS-2096.015, .011


def _synced_linked_archive(tmp_path: Path, tag: str, *, main_has_wing: bool):
    main, other = _sync_pair(tmp_path, tag)
    _linked_sim(other, "4201")
    other.append_record(_record("4201", "camp/sim_4201/AL+000"))
    _write_recipe(other, "m901", '[[compact_sims]]\nsims = ["4201"]\n')
    storage_module.free_space(other.root, "m901", apply=True)
    if main_has_wing:
        _write(main.inputs_dir / "geometries" / "wing" / "wing.obj", "o wing\n")
    storage_module.sync_workspaces(main.root, "all", apply=True)
    assert _zip(main, "4201").is_file()
    return main, other


def test_p0400_a_synced_archive_restores_its_inputs_link_into_mains_library(tmp_path):
    """P0400-RESTORE-RELINK (PFS-2096.015): the link goes to main's library, not the other's."""
    main, _ = _synced_linked_archive(tmp_path, "relinkzip", main_has_wing=True)
    assert storage_module.ensure_sim_expanded(main, "4201", reason="test")
    inputs = main.sim_dir("4201") / "inputs"
    assert (inputs / "wing.obj").is_file(), "inputs/ is not the link into main's library"
    assert Path(os.path.realpath(inputs)) == (main.inputs_dir / "geometries" / "wing").resolve()


def test_p0400_a_restore_that_cannot_link_inputs_records_it_and_warns(tmp_path):
    """P0400-RESTORE-NOLINK (PFS-2085.011): an empty inputs folder is recorded and warned."""
    main, other = _synced_linked_archive(tmp_path, "nolink", main_has_wing=False)
    with pytest.warns(PyflightstreamWarning, match="empty folder"):
        assert storage_module.ensure_sim_expanded(main, "4201", reason="test")
    entry = storage_module.read_storage_calls(main.root)[-1]
    assert entry["action"] == "restore"
    assert entry["inputs_link_restored"] is False
    recorded = Path(entry["inputs_link_target"])
    assert recorded == (other.inputs_dir / "geometries" / "wing").resolve()


# --------------------------------------------------------------------------- PFS-2096.016


def test_p0400_two_readers_of_one_compacted_simulation_restore_it_once(tmp_path, monkeypatch):
    """P0400-RESTORE-RACE (PFS-2096.016): the second reader waits and finds it restored."""
    workspace = _ws(tmp_path, "tworeaders")
    archive = _compacted(
        workspace, "4301", {**FULL, "datapoints/DP-1/a.txt": "a", "datapoints/DP-1/b.txt": "b"}
    )
    results: dict[str, bool] = {}
    errors: list[BaseException] = []

    def reader(name: str) -> None:
        try:
            results[name] = storage_module.ensure_sim_expanded(workspace, "4301", reason=name)
        except BaseException as error:  # noqa: BLE001 - every failure is asserted on
            errors.append(error)

    second = threading.Thread(target=reader, args=("second",))
    real_extract = zipfile.ZipFile.extract

    def extract(self, member, path=None, pwd=None):
        if threading.current_thread() is threading.main_thread() and second.ident is None:
            second.start()
            second.join(timeout=3)
        return real_extract(self, member, path, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "extract", extract)
    reader("first")
    second.join(timeout=120)
    assert not errors, errors
    assert sorted(results.values()) == [False, True], results
    assert not list((workspace.root / "sims").glob("*.restoring"))
    assert not archive.exists()
    assert (workspace.sim_dir("4301") / "datapoints" / "DP-1" / "b.txt").is_file()


# --------------------------------------------------------------------------- PFS-2096.026


class _Clock(dt.datetime):
    """Local 09:00, and UTC three hours later, as on a machine at UTC-3."""

    @classmethod
    def now(cls, tz=None):
        local = dt.datetime(2026, 10, 12, 9, 0, 0)
        return local if tz is None else (local + dt.timedelta(hours=3)).replace(tzinfo=tz)


def test_p0400_storage_archives_runs_on_the_package_clock_and_never_over_a_copy(
    tmp_path, monkeypatch
):
    """P0400-ARCHIVE-CLOCK (PFS-2096.026): restore takes the newest copy, and none is lost."""
    monkeypatch.setattr(dt, "datetime", _Clock)
    workspace = _ws(tmp_path, "clock")
    for sim in ("4401", "4402", "4403"):
        _recorded_sim(workspace, sim, {"scripts/point.fs": "s"})
    storage_module.delete_sims(workspace.root, ["4401"], apply=True)
    storage_module.delete_sims(workspace.root, ["4402"], apply=True)
    workspace.supersede_records(["camp/sim_4403/AL+000"], stamp=dt.datetime(2026, 10, 12, 9))
    archives = sorted((workspace.root / ARCHIVE_DIR).glob("runs-*.json"))
    assert len(archives) == 3, [path.name for path in archives]
    chosen = restore(workspace.root, "runs")
    newest = json.loads((workspace.root / chosen["source"]).read_text(encoding="utf-8"))
    assert any(row.get(DELETED) == "4402" for row in newest), chosen["source"]
    assert any(row.get("sim_id") == "4403" for row in newest), chosen["source"]


# --------------------------------------------------------------------------- delete-sims


def test_p0400_a_repeated_id_writes_one_tombstone(tmp_path):
    """P0400-DELETE-DEDUP (PFS-2103.041): one note row per simulation, run ids unique."""
    workspace = _ws(tmp_path, "dedup")
    _recorded_sim(workspace, "4501", {"scripts/point.fs": "s"})
    entry = storage_module.delete_sims(workspace.root, ["4501", "4501"], apply=True)
    rows = _rows(workspace)
    assert len([row for row in rows if row.get(DELETED) == "4501"]) == 1
    run_ids = [row["run_id"] for row in rows]
    assert len(run_ids) == len(set(run_ids))
    assert [item["sim_id"] for item in entry["sims"]] == ["4501"]


def test_p0400_an_interrupted_delete_is_recorded_and_a_rerun_finishes_it(tmp_path, monkeypatch):
    """P0400-DELETE-INTENT (PFS-2086.005): the stop is recorded; the same delete finishes it."""
    workspace = _shared_product_workspace(tmp_path, "interrupted")
    real = Path.replace

    def killed(self, target):
        if Path(target).name == "products.json":
            raise RuntimeError("killed while rewriting products.json")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", killed)
    with pytest.raises(RuntimeError):
        storage_module.delete_sims(
            workspace.root, ["3001"], matrix_products="points-only", apply=True
        )
    assert not workspace.sim_dir("3001").exists()
    assert any(row.get("sim_id") == "3001" for row in _rows(workspace))
    calls = [
        call
        for call in storage_module.read_storage_calls(workspace.root)
        if call["action"] == "delete-sims"
    ]
    assert any("intent" in call for call in calls), calls
    assert "killed while rewriting" in calls[-1]["interrupted"]
    monkeypatch.setattr(Path, "replace", real)
    storage_module.delete_sims(workspace.root, ["3001"], matrix_products="points-only", apply=True)
    rows = _rows(workspace)
    assert not any(row.get("sim_id") == "3001" and DELETED not in row for row in rows)
    assert [row for row in rows if row.get(DELETED) == "3001"]


def test_p0400_delete_refuses_when_a_products_manifest_cannot_be_read(tmp_path):
    """P0400-DELETE-PRODUCTS (PFS-2086.006): a truncated products.json refuses, deleting nothing."""
    workspace = _shared_product_workspace(tmp_path, "truncated")
    manifest = workspace.root / "post" / "matriz" / "products.json"
    manifest.write_text('{"products": {"polar.csv": {', encoding="utf-8")
    with pytest.raises(StorageError) as raised:
        storage_module.delete_sims(workspace.root, ["3001"], apply=True)
    assert str(manifest) in str(raised.value)
    assert workspace.sim_dir("3001").is_dir()


# --------------------------------------------------------------------------- free-space


def test_p0400_delete_extensions_records_a_submitted_simulation_it_skips(tmp_path):
    """P0400-EXT-SUBMITTED (PFS-2093.006): the skipped simulation is recorded as refused."""
    workspace = _ws(tmp_path, "extsubmitted")
    _recorded_sim(workspace, "4601", {"datapoints/DP-1/a.vtk": "v"}, status=RunStatus.SUBMITTED)
    _write_recipe(workspace, "m902", '[[delete_extensions]]\nextensions = [".vtk"]\n')
    entry = storage_module.free_space(workspace.root, "m902")
    assert "SUBMITTED" in entry["steps"][0]["refused"]["4601"]


@pytest.mark.parametrize("value", ["-1", '"two"', "1.5", "true"])
def test_p0400_post_archives_keep_latest_is_a_whole_number(tmp_path, value):
    """P0400-KEEP-LATEST (PFS-2096.017): keep_latest is refused unless an integer 0 or more."""
    workspace = _ws(tmp_path, "keeplatest")
    stamp = workspace.root / "post" / "matriz" / ARCHIVE_DIR / "20260101-000000"
    _write(stamp / "polar.csv", "old")
    _write_recipe(workspace, "m904", f"[[post_archives]]\nkeep_latest = {value}\n")
    with pytest.raises(StorageError, match="keep_latest"):
        storage_module.free_space(workspace.root, "m904", apply=True)
    assert (stamp / "polar.csv").is_file()


def test_p0400_a_later_step_naming_a_compacted_sim_is_refused_before_any_step(tmp_path):
    """P0400-RECIPE-CHECKED (PFS-2096.027): the preview refuses what the apply would."""
    workspace = _ws(tmp_path, "checked")
    _recorded_sim(workspace, "4901", {**FULL, "datapoints/DP-1/a.vtk": "v"})
    _write_recipe(
        workspace,
        "m905",
        '[[compact_sims]]\nsims = ["4901"]\n\n'
        '[[delete_extensions]]\nsims = ["4901"]\nextensions = [".vtk"]\n',
    )
    with pytest.raises(StorageError, match="4901"):
        storage_module.free_space(workspace.root, "m905")
    with pytest.raises(StorageError, match="4901"):
        storage_module.free_space(workspace.root, "m905", apply=True)
    assert workspace.sim_dir("4901").is_dir()
    assert not _zip(workspace, "4901").exists()


def test_p0400_an_applied_recipe_that_stops_part_way_is_recorded(tmp_path, monkeypatch):
    """P0400-RECIPE-PARTIAL (PFS-2096.027): the steps done and the error are recorded."""
    workspace = _ws(tmp_path, "partial")
    _recorded_sim(workspace, "4911", FULL)
    _recorded_sim(workspace, "4912", FULL)
    real = zipfile.ZipFile.write

    def second_fails(self, filename, *args, **kwargs):
        if "sim_4912" in str(filename):
            raise OSError("held open by another process")
        return real(self, filename, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "write", second_fails)
    _write_recipe(workspace, "m906", '[[compact_sims]]\nsims = "all"\n')
    with pytest.raises(OSError, match="held open"):
        storage_module.free_space(workspace.root, "m906", apply=True)
    last = storage_module.read_storage_calls(workspace.root)[-1]
    assert last["action"] == "free-space" and last["applied"] is True
    assert "held open" in last["interrupted"]
    assert [item["sim_id"] for item in last["steps"][0]["sims"]] == ["4911"]


def test_p0400_a_compaction_that_fails_while_zipping_leaves_no_partial_zip(tmp_path, monkeypatch):
    """P0400-COMPACT-TMP (PFS-2096.029): the temporary zip is removed on a failed write."""
    workspace = _ws(tmp_path, "ziptmp")
    _recorded_sim(workspace, "4921", FULL)

    def held_open(self, filename, arcname=None, *args, **kwargs):
        raise PermissionError(f"{filename} is held open")

    monkeypatch.setattr(zipfile.ZipFile, "write", held_open)
    _write_recipe(workspace, "m907", '[[compact_sims]]\nsims = "all"\n')
    with pytest.raises(PermissionError):
        storage_module.free_space(workspace.root, "m907", apply=True)
    assert not list((workspace.root / "sims").glob("*.tmp"))
    assert workspace.sim_dir("4921").is_dir()


def test_p0400_compaction_verifies_each_member_by_streaming_it(tmp_path, monkeypatch):
    """P0400-COMPACT-STREAM (PFS-2101.001): no member is read whole into memory."""
    workspace = _ws(tmp_path, "stream")
    _recorded_sim(workspace, "4931", FULL)

    def whole(self, name, pwd=None):
        raise AssertionError(f"{name} was read whole into memory")

    monkeypatch.setattr(zipfile.ZipFile, "read", whole)
    _write_recipe(workspace, "m908", '[[compact_sims]]\nsims = "all"\n')
    entry = storage_module.free_space(workspace.root, "m908", apply=True)
    assert [item["sim_id"] for item in entry["steps"][0]["sims"]] == ["4931"]


# --------------------------------------------------------------------------- PFS-2094.047


def _exited_pid() -> int:
    done = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(done.stdout)


def test_p0400_a_lock_left_by_a_dead_process_does_not_stop_free_space_which_holds_the_lease(
    tmp_path, monkeypatch
):
    """P0400-LEASE-DEAD (PFS-2094.047): the lease's rules recover it; free-space holds the lease."""
    workspace = _ws(tmp_path, "deadlock")
    _recorded_sim(workspace, "4701", FULL)
    lock = workspace.root / "runs.json.lock"
    owner = {"pid": _exited_pid(), "host": socket.gethostname(), "token": "gone"}
    lock.write_text(json.dumps(owner) + "\n", encoding="utf-8")
    held: list[bool] = []
    real = zipfile.ZipFile.write

    def watching(self, filename, *args, **kwargs):
        held.append(lock.exists())
        return real(self, filename, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "write", watching)
    _write_recipe(workspace, "m903", '[[compact_sims]]\nsims = "all"\n')
    entry = storage_module.free_space(workspace.root, "m903", apply=True)
    assert [item["sim_id"] for item in entry["steps"][0]["sims"]] == ["4701"]
    assert held and all(held), held
    assert not lock.exists()


def test_p0400_sync_reads_another_workspace_whose_lock_no_heartbeat_touched(tmp_path):
    """P0400-LEASE-STALE (PFS-2094.047): a stale lock there is not a run in progress."""
    main, other = _sync_pair(tmp_path, "stalelock")
    _recorded_sim(other, "4702", {"scripts/point.fs": "s"})
    lock = other.root / "runs.json.lock"
    lock.write_text("{}\n", encoding="utf-8")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert "skipped" not in entry, entry.get("skipped")
    assert entry["runs"]["added"]


# --------------------------------------------------------------------------- PFS-2094.049


def test_p0400_a_relative_sync_path_is_the_workspace_roots(tmp_path, monkeypatch):
    """P0400-SYNC-RELATIVE (PFS-2094.049): path = "." names main from any working directory."""
    main, other = _sync_pair(tmp_path, "relpath")
    config = main.root / storage_module.SYNC_CONFIG
    config.write_text(
        'main = "main"\n\n[workspaces.main]\npath = "."\n\n'
        '[workspaces.other]\npath = "../relpath_other"\n',
        encoding="utf-8",
    )
    _recorded_sim(other, "4801", {"scripts/point.fs": "s"})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert Path(entry["source"]) == other.root.resolve()
    assert entry["runs"]["added"]
