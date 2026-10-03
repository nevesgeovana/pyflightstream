"""Tier 1 offline: the storage and sync module of 0.30.0 (GOAL-035).

Covers ``pyflightstream.workspace.storage``: ``space-in-use``, ``free-space``
(its three recipe tables), ``delete-sims`` and ``sync``, plus the CLI surface
that ``pyfs-matrix`` exposes for them (``_STORAGE_COMMANDS`` and the owner's
flag form). Every workspace is a real ``tmp_path`` tree built with real
``CampaignWorkspace.init`` and real ``RunRecord`` rows; nothing here reads or
writes through the live repository tree.

SEVEN MUTANTS are proved here, each a single-line change to the SOURCE TEXT of
``storage.py`` loaded into a standalone module (never written back to
``src/``, per the session's instruction that this worktree's ``src/`` is
edited elsewhere): the protection a named output gets from a recipe, the
preview-changes-nothing guarantee, the refusal to compact a ``SUBMITTED``
simulation, the hash check a restore refuses on, the refusal to re-add a run
id a ``delete-sims`` note already retired, the refusal to apply
``delete-sims`` against a shared product with no ``--matrix-products``
choice, and the relink of a compacted sim's ``inputs/`` back into the
geometry library on restore. Each ``test_mutant_*`` function shows the same
check passes against the real module and fails (returns the opposite of what
the real behaviour proves) against the mutant.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.run import cli as matrix_cli
from pyflightstream.workspace import (
    CampaignWorkspace,
    RunRecord,
    RunStatus,
    _make_dir_link,
)
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.naming import ARCHIVE_DIR

STORAGE_SRC = Path(storage_module.__file__)


# --------------------------------------------------------------------------- fixtures


def _ws(tmp_path: Path, name: str = "camp") -> CampaignWorkspace:
    root = tmp_path / name
    workspace = CampaignWorkspace(root)
    workspace.init(root)
    return workspace


def _record(
    sim_id: str,
    run_id: str,
    *,
    status: RunStatus = RunStatus.CONVERGED,
    matrix_stem: str = "matriz",
    outputs: list[str] | None = None,
    script_path: str | None = None,
    inputs_sha256: dict[str, str] | None = None,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id=sim_id,
        matrix_stem=matrix_stem,
        fs_version_requested="26.123",
        package_version="0.30.0",
        script_sha256="c" * 64,
        raw_flag=False,
        status=status,
        outputs=outputs or [],
        script_path=script_path,
        inputs_sha256=inputs_sha256 or {},
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_recipe(workspace: CampaignWorkspace, recipe_id: str, toml_text: str) -> Path:
    path = workspace.root / storage_module.MANAGEMENT_DIR / f"{recipe_id}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(toml_text, encoding="utf-8")
    return path


def _shared_product_workspace(tmp_path: Path, name: str) -> CampaignWorkspace:
    """Two sims under one matrix, a product only sim A owns and one they share."""
    workspace = _ws(tmp_path, name)
    sim_a = workspace.sim_dir("3001")
    sim_b = workspace.sim_dir("3002")
    _write(sim_a / "datapoints" / "DP-1" / "x.txt", "a")
    _write(sim_b / "datapoints" / "DP-1" / "x.txt", "b")
    workspace.append_record(_record("3001", "camp/sim_3001/AL+000"))
    workspace.append_record(_record("3002", "camp/sim_3002/AL+000"))
    products_dir = workspace.root / "post" / "matriz"
    products_dir.mkdir(parents=True, exist_ok=True)
    _write(products_dir / "polar.csv", "shared-product-data")
    _write(products_dir / "sim_3001_diag.csv", "own-product-data")
    document = {
        "products": {
            "polar.csv": {"sim_id": None, "runs": ["camp/sim_3001/AL+000", "camp/sim_3002/AL+000"]},
            "sim_3001_diag.csv": {"sim_id": "3001", "runs": ["camp/sim_3001/AL+000"]},
        },
        "provenance": {"camp/sim_3001/AL+000": "point_log.txt"},
    }
    (products_dir / "products.json").write_text(json.dumps(document), encoding="utf-8")
    return workspace


def _sync_config(main_root: Path, others: dict[str, Path]) -> None:
    lines = [
        'main = "main"',
        "",
        "[workspaces.main]",
        f"path = '{main_root.resolve().as_posix()}'",
        "",
    ]
    for other_name, path in others.items():
        lines += [f"[workspaces.{other_name}]", f"path = '{path.resolve().as_posix()}'", ""]
    config = main_root / storage_module.SYNC_CONFIG
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("\n".join(lines), encoding="utf-8")


def _sync_pair(tmp_path: Path, tag: str) -> tuple[CampaignWorkspace, CampaignWorkspace]:
    main = _ws(tmp_path, f"{tag}_main")
    other = _ws(tmp_path, f"{tag}_other")
    _sync_config(main.root, {"other": other.root})
    return main, other


# --------------------------------------------------------------------------- space-in-use


@pytest.mark.requirement("FR-173")
def test_space_in_use_groups_by_folder_sim_and_extension_and_records_a_call(tmp_path):
    workspace = _ws(tmp_path)
    _write(workspace.sim_dir("1001") / "datapoints" / "DP-1" / "loads.vtk", "a" * 100)
    _write(workspace.sim_dir("1001") / "datapoints" / "DP-1" / "loads.txt", "b" * 50)
    _write(workspace.sim_dir("2002") / "datapoints" / "DP-1" / "loads.vtk", "c" * 10)
    report = storage_module.space_in_use(workspace.root)
    assert report.by_sim == {"sim_1001": 150, "sim_2002": 10}
    assert report.by_extension[".vtk"] == 110
    assert report.by_extension[".txt"] == 50
    assert any(name.startswith("sims/") for name in report.by_folder)
    calls = storage_module.read_storage_calls(workspace.root)
    assert calls[-1]["action"] == "space-in-use"
    assert calls[-1]["applied"] is False
    assert calls[-1]["sims"] == 2


# --------------------------------------------------------------------------- the record


def test_record_storage_call_continues_an_existing_fts_sync_style_file(tmp_path):
    workspace = _ws(tmp_path)
    path = workspace.root / storage_module.STORAGE_FILE
    path.write_text(
        json.dumps(
            {
                "schema": storage_module.STORAGE_SCHEMA,
                "calls": [
                    {"at": "2026-01-01T00:00:00+00:00", "tool": "fts_sync.py", "action": "sync"}
                ],
            }
        ),
        encoding="utf-8",
    )
    index = storage_module.record_storage_call(workspace.root, {"action": "space-in-use"})
    assert index == 1
    calls = storage_module.read_storage_calls(workspace.root)
    assert len(calls) == 2
    assert calls[0]["tool"] == "fts_sync.py"
    assert calls[1]["tool"] == storage_module.TOOL


def test_record_storage_call_refuses_a_foreign_schema(tmp_path):
    workspace = _ws(tmp_path)
    (workspace.root / storage_module.STORAGE_FILE).write_text(
        json.dumps({"schema": "some/other-schema/1", "calls": []}), encoding="utf-8"
    )
    with pytest.raises(storage_module.StorageError):
        storage_module.record_storage_call(workspace.root, {"action": "space-in-use"})


# ------------------------------------------------------------------- free-space: compact/restore


def test_free_space_apply_compacts_then_ensure_sim_expanded_restores_byte_identical(tmp_path):
    workspace = _ws(tmp_path)
    sim = workspace.sim_dir("1201")
    target = sim / "datapoints" / "DP-1" / "loads.vtk"
    content = b"payload-bytes-0123456789"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    workspace.append_record(_record("1201", "camp/sim_1201/AL+000"))
    _write_recipe(workspace, "m001", '[[compact_sims]]\nsims = "all"\n')
    entry = storage_module.free_space(workspace.root, "m001", apply=True)
    assert entry["applied"] is True
    archive = sim.with_name(sim.name + storage_module.COMPACTED_SUFFIX)
    assert archive.is_file()
    assert not sim.exists()
    restored = storage_module.ensure_sim_expanded(workspace, "1201", reason="test")
    assert restored is True
    assert sim.is_dir()
    assert (sim / "datapoints" / "DP-1" / "loads.vtk").read_bytes() == content
    assert not archive.exists()
    calls = storage_module.read_storage_calls(workspace.root)
    assert calls[-1]["action"] == "restore"
    assert calls[-1]["sim_id"] == "1201"
    assert calls[-1]["reason"] == "test"


def test_ensure_sim_expanded_on_an_expanded_or_absent_sim_does_nothing(tmp_path):
    workspace = _ws(tmp_path)
    assert storage_module.ensure_sim_expanded(workspace, "9999", reason="test") is False
    sim = workspace.sim_dir("1210")
    _write(sim / "x.txt", "already here")
    assert storage_module.ensure_sim_expanded(workspace, "1210", reason="test") is False


# ------------------------------------------------------------------- free-space: delete_extensions


def test_delete_extensions_deletes_unprotected_keeps_named_output_and_fsm(tmp_path):
    workspace = _ws(tmp_path)
    sim = workspace.sim_dir("1301")
    unprotected = sim / "datapoints" / "DP-1" / "junk.vtk"
    named = sim / "datapoints" / "DP-1" / "loads.vtk"
    fsm = sim / "datapoints" / "DP-1" / "case.fsm"
    _write(unprotected, "junk")
    _write(named, "keep-me")
    _write(fsm, "saved-sim")
    workspace.append_record(
        _record("1301", "camp/sim_1301/AL+000", outputs=["datapoints/DP-1/loads.vtk"])
    )
    _write_recipe(workspace, "m001", '[[delete_extensions]]\nextensions = [".vtk"]\n')
    entry = storage_module.free_space(workspace.root, "m001", apply=True)
    assert not unprotected.exists()
    assert named.exists()
    assert fsm.exists()
    step = entry["steps"][0]
    assert step["mode"] == "delete_extensions"
    assert any(item["path"].endswith("junk.vtk") for item in step["files"])
    assert any(path.endswith("loads.vtk") for path in step["kept"])


def test_delete_extensions_preview_changes_nothing(tmp_path):
    workspace = _ws(tmp_path)
    sim = workspace.sim_dir("1310")
    target = sim / "datapoints" / "DP-1" / "loads.vtk"
    _write(target, "data")
    workspace.append_record(_record("1310", "camp/sim_1310/AL+000"))
    _write_recipe(workspace, "m001", '[[delete_extensions]]\nextensions = [".vtk"]\n')
    entry = storage_module.free_space(workspace.root, "m001", apply=False)
    assert entry["applied"] is False
    assert target.exists()


def test_recipe_naming_fsm_extension_is_refused(tmp_path):
    workspace = _ws(tmp_path)
    workspace.sim_dir("1401").mkdir(parents=True, exist_ok=True)
    _write_recipe(workspace, "m001", '[[delete_extensions]]\nextensions = [".fsm"]\n')
    with pytest.raises(storage_module.StorageError):
        storage_module.free_space(workspace.root, "m001", apply=False)


# ------------------------------------------------------------------- free-space: post_archives


def test_post_archives_delete_with_keep_latest(tmp_path):
    workspace = _ws(tmp_path)
    archive_root = workspace.root / "post" / "matriz" / ARCHIVE_DIR
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        _write(archive_root / stamp / "old_product.csv", "data" * 10)
    _write_recipe(workspace, "m001", '[[post_archives]]\naction = "delete"\nkeep_latest = 1\n')
    entry = storage_module.free_space(workspace.root, "m001", apply=True)
    remaining = sorted(p.name for p in archive_root.iterdir())
    assert remaining == ["20260103-000000"]
    assert entry["steps"][0]["mode"] == "post_archives"


def test_post_archives_compact_zips_and_removes_the_folder(tmp_path):
    workspace = _ws(tmp_path)
    archive_root = workspace.root / "post" / "matriz" / ARCHIVE_DIR
    stamp_dir = archive_root / "20260101-000000"
    _write(stamp_dir / "old_product.csv", "data")
    _write_recipe(workspace, "m001", '[[post_archives]]\naction = "compact"\nkeep_latest = 0\n')
    storage_module.free_space(workspace.root, "m001", apply=True)
    assert not stamp_dir.exists()
    assert (archive_root / "20260101-000000.zip").is_file()


def test_post_archives_skips_an_archive_nested_inside_another_archive(tmp_path):
    workspace = _ws(tmp_path)
    archive_root = workspace.root / "post" / "matriz" / ARCHIVE_DIR
    outer_stamp = archive_root / "20260101-000000"
    _write(outer_stamp / "product.csv", "data")
    _write(outer_stamp / ARCHIVE_DIR / "20260102-000000" / "inner.csv", "nested")
    _write_recipe(workspace, "m001", '[[post_archives]]\naction = "delete"\nkeep_latest = 0\n')
    entry = storage_module.free_space(workspace.root, "m001", apply=True)
    paths = [item["path"] for item in entry["steps"][0]["archives"]]
    assert any(path.endswith("20260101-000000") for path in paths)
    assert not any(f"{ARCHIVE_DIR}/20260102-000000" in path for path in paths)
    assert not outer_stamp.exists()


# --------------------------------------------------------------------------- delete-sims


def test_delete_sims_preview_changes_nothing(tmp_path):
    workspace = _ws(tmp_path)
    sim = workspace.sim_dir("2001")
    _write(sim / "datapoints" / "DP-1" / "loads.vtk", "data")
    workspace.append_record(_record("2001", "camp/sim_2001/AL+000"))
    entry = storage_module.delete_sims(workspace.root, ["2001"], apply=False)
    assert entry["applied"] is False
    assert sim.is_dir()
    raw = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert len(raw) == 1 and raw[0]["run_id"] == "camp/sim_2001/AL+000"


def test_delete_sims_apply_refused_when_shared_product_exists_and_no_choice(tmp_path):
    workspace = _shared_product_workspace(tmp_path, "refuse")
    with pytest.raises(storage_module.StorageError):
        storage_module.delete_sims(workspace.root, ["3001"], apply=True)


def test_delete_sims_points_only_apply_removes_folder_products_and_leaves_note_row(tmp_path):
    workspace = _shared_product_workspace(tmp_path, "pts")
    entry = storage_module.delete_sims(
        workspace.root, ["3001"], matrix_products="points-only", apply=True
    )
    assert entry["applied"] is True

    # the sim folder is gone
    assert not workspace.sim_dir("3001").exists()

    # its own product file is gone; the shared one's FILE is left, marked stale
    own_file = workspace.root / "post" / "matriz" / "sim_3001_diag.csv"
    shared_file = workspace.root / "post" / "matriz" / "polar.csv"
    assert not own_file.exists()
    assert shared_file.exists()

    # products.json was rewritten: the own entry is gone, the shared one stays,
    # the deleted run's provenance entry is gone, and a deleted_by_storage note lands
    document = json.loads(
        (workspace.root / "post" / "matriz" / "products.json").read_text(encoding="utf-8")
    )
    assert "sim_3001_diag.csv" not in document["products"]
    assert "polar.csv" in document["products"]
    assert "camp/sim_3001/AL+000" not in document.get("provenance", {})
    assert document["deleted_by_storage"][-1]["sims"] == ["3001"]
    assert document["deleted_by_storage"][-1]["stale"] == ["polar.csv"]

    # runs.json keeps a note row, not a run record, for the deleted sim
    raw = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    note_rows = [row for row in raw if row.get("deleted_sim") == "3001"]
    assert len(note_rows) == 1
    assert not any(row.get("run_id") == "camp/sim_3001/AL+000" for row in raw)

    # read_manifest (the typed view) skips the note row entirely
    assert all(record.sim_id != "3001" for record in workspace.read_manifest())

    # the id can be reused
    workspace.append_record(_record("3001", "camp/sim_3001/AL+001"))
    assert any(record.sim_id == "3001" for record in workspace.read_manifest())


# --------------------------------------------------------------------------- sync


def test_sync_adds_a_run_present_only_in_the_other_workspace(tmp_path):
    main, other = _sync_pair(tmp_path, "add")
    other.append_record(_record("7001", "campo/sim_7001/AL+000"))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert entry["runs"]["added"] == ["campo/sim_7001/AL+000"]
    raw = json.loads(main.manifest_path.read_text(encoding="utf-8"))
    assert any(row["run_id"] == "campo/sim_7001/AL+000" for row in raw)


def test_sync_a_submitted_main_record_is_replaced_by_the_others(tmp_path):
    main, other = _sync_pair(tmp_path, "subreplace")
    main.append_record(_record("7002", "campo/sim_7002/AL+000", status=RunStatus.SUBMITTED))
    other.append_record(_record("7002", "campo/sim_7002/AL+000", status=RunStatus.CONVERGED))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert entry["runs"]["replaced"][0]["to"] == "CONVERGED"
    raw = json.loads(main.manifest_path.read_text(encoding="utf-8"))
    status = next(row["status"] for row in raw if row["run_id"] == "campo/sim_7002/AL+000")
    assert status == "CONVERGED"


def test_sync_a_conflict_keeps_main_unless_prefer_other(tmp_path):
    main, other = _sync_pair(tmp_path, "conflict")
    main.append_record(_record("7003", "campo/sim_7003/AL+000", status=RunStatus.CONVERGED))
    other.append_record(_record("7003", "campo/sim_7003/AL+000", status=RunStatus.FAILED_EXECUTION))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert entry["runs"]["conflicts"]
    raw = json.loads(main.manifest_path.read_text(encoding="utf-8"))
    status = next(row["status"] for row in raw if row["run_id"] == "campo/sim_7003/AL+000")
    assert status == "CONVERGED"


def test_sync_prefer_other_takes_the_other_workspaces_record(tmp_path):
    main, other = _sync_pair(tmp_path, "preferother")
    main.append_record(_record("7004", "campo/sim_7004/AL+000", status=RunStatus.CONVERGED))
    other.append_record(_record("7004", "campo/sim_7004/AL+000", status=RunStatus.FAILED_EXECUTION))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True, prefer_other=True)
    assert not entry["runs"]["conflicts"]
    raw = json.loads(main.manifest_path.read_text(encoding="utf-8"))
    status = next(row["status"] for row in raw if row["run_id"] == "campo/sim_7004/AL+000")
    assert status == "FAILED_EXECUTION"


def test_sync_a_submitted_sim_in_the_other_workspace_is_record_only(tmp_path):
    main, other = _sync_pair(tmp_path, "subother")
    sim = other.sim_dir("7005")
    _write(sim / "scripts" / "point.fs", "script")
    other.append_record(_record("7005", "campo/sim_7005/AL+000", status=RunStatus.SUBMITTED))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert "7005" in entry["runs"]["submitted_sims_record_only"]
    assert entry["files"]["to_copy"] == 0
    assert not (main.sim_dir("7005") / "scripts" / "point.fs").exists()
    raw = json.loads(main.manifest_path.read_text(encoding="utf-8"))
    assert any(row["run_id"] == "campo/sim_7005/AL+000" for row in raw)


def test_sync_overwrite_archives_mains_copy_before_taking_the_others(tmp_path):
    main, other = _sync_pair(tmp_path, "overwrite")
    sim_main = main.sim_dir("7006")
    sim_other = other.sim_dir("7006")
    _write(sim_main / "scripts" / "point.fs", "main-version")
    _write(sim_other / "scripts" / "point.fs", "other-version")
    entry = storage_module.sync_workspaces(main.root, "runs", apply=True)[0]
    assert "sims/sim_7006/scripts/point.fs" in entry["files"]["conflicts"]
    assert (sim_main / "scripts" / "point.fs").read_text(encoding="utf-8") == "main-version"
    storage_module.sync_workspaces(main.root, "runs", apply=True, overwrite=True)
    assert (sim_main / "scripts" / "point.fs").read_text(encoding="utf-8") == "other-version"
    archived = list((main.root / ARCHIVE_DIR).glob("sync-*/sims/sim_7006/scripts/point.fs"))
    assert len(archived) == 1
    assert archived[0].read_text(encoding="utf-8") == "main-version"


def test_sync_refuses_when_a_runs_json_lock_is_present(tmp_path):
    main, other = _sync_pair(tmp_path, "lock")
    (main.root / "runs.json.lock").write_text("", encoding="utf-8")
    with pytest.raises(storage_module.StorageError):
        storage_module.sync_workspaces(main.root, "runs", apply=True)


def _copied_paths(tmp_path: Path, other_root: Path, level: str, tag: str) -> set[str]:
    main = _ws(tmp_path, f"levels_{tag}")
    _sync_config(main.root, {"other": other_root})
    (entry,) = storage_module.sync_workspaces(main.root, level, apply=True)
    return {item["path"] for item in entry["files"]["copied"]}


@pytest.mark.requirement("FR-175")
def test_sync_level_is_cumulative_and_never_follows_the_inputs_junction(tmp_path):
    other_root = tmp_path / "levels_other"
    other = CampaignWorkspace(other_root)
    other.init(other_root)
    sim = other.sim_dir("7007")
    _write(sim / "scripts" / "point.fs", "s")
    _write(sim / "datapoints" / "DP-1" / "run_log.txt", "l")
    _write(sim / "datapoints" / "DP-1" / "case.fsm", "f")
    _write(sim / "notes.txt", "extra")
    _write(other.root / "post" / "matriz" / "polar.csv", "p")
    other.append_record(_record("7007", "campo/sim_7007/AL+000"))
    junction_target = tmp_path / "levels_junction_target"
    _write(junction_target / "secret.txt", "hidden")
    _make_dir_link(junction_target, sim / "inputs")

    script = "sims/sim_7007/scripts/point.fs"
    log = "sims/sim_7007/datapoints/DP-1/run_log.txt"
    fsm = "sims/sim_7007/datapoints/DP-1/case.fsm"
    post = "post/matriz/polar.csv"
    extra = "sims/sim_7007/notes.txt"

    runs_paths = _copied_paths(tmp_path, other_root, "runs", "a")
    assert {script, log} <= runs_paths
    assert post not in runs_paths and fsm not in runs_paths and extra not in runs_paths

    post_paths = _copied_paths(tmp_path, other_root, "post", "b")
    assert {script, log, post} <= post_paths
    assert fsm not in post_paths and extra not in post_paths

    fsm_paths = _copied_paths(tmp_path, other_root, "fsm", "c")
    assert {script, log, post, fsm} <= fsm_paths
    assert extra not in fsm_paths

    all_paths = _copied_paths(tmp_path, other_root, "all", "d")
    assert {script, log, post, fsm, extra} <= all_paths
    assert not any("inputs" in path.split("/") for path in all_paths), (
        "the inputs junction inside the sim folder must never be synced"
    )


def test_sync_does_not_re_add_a_run_deleted_by_delete_sims(tmp_path):
    main, other = _sync_pair(tmp_path, "delsim")
    main.append_record(_record("7008", "campo/sim_7008/AL+000"))
    storage_module.delete_sims(main.root, ["7008"], apply=True)
    other.append_record(_record("7008", "campo/sim_7008/AL+000"))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert entry["runs"]["conflicts"]
    assert entry["runs"]["conflicts"][0]["reason"].startswith("deleted")
    raw = json.loads(main.manifest_path.read_text(encoding="utf-8"))
    assert not any(
        row.get("run_id") == "campo/sim_7008/AL+000" and "deleted_sim" not in row for row in raw
    )


# ------------------------------------------------------- the mesh is linked, never copied or lost
#
# The owner's two rules of 2026-09-28: "o sync precisa refazer o link logico da
# pasta sim_<>/inputs/ pra nao precisar criar copias da malha" and "o delete de
# sim precisa desfazer o junction ou link logico antes de apagar a sim para nao
# apagar a malha em inputs".


def _linked_sim(workspace: CampaignWorkspace, sim_id: str) -> Path:
    """A simulation whose inputs/ links into one geometry folder of the library."""
    library = workspace.inputs_dir / "geometries" / "wing"
    _write(library / "wing.obj", "o wing\nv 0 0 0\n")
    folder = workspace.sim_dir(sim_id)
    _write(folder / "scripts" / "point.fs", "script")
    _make_dir_link(library.resolve(), folder / "inputs")
    return library / "wing.obj"


def test_delete_sims_undoes_the_inputs_link_and_keeps_the_mesh(tmp_path):
    workspace = _ws(tmp_path, "keepmesh")
    mesh = _linked_sim(workspace, "8001")
    workspace.append_record(_record("8001", "camp/sim_8001/AL+000"))
    entry = storage_module.delete_sims(workspace.root, ["8001"], apply=True)
    assert not workspace.sim_dir("8001").exists()
    assert mesh.is_file() and mesh.read_text(encoding="utf-8").startswith("o wing")
    assert entry["links_undone"] == {"8001": ["inputs"]}


def test_a_sim_folder_is_never_removed_while_a_link_survives_inside(tmp_path, monkeypatch):
    workspace = _ws(tmp_path, "linkguard")
    mesh = _linked_sim(workspace, "8002")
    monkeypatch.setattr(storage_module, "_remove_link", lambda path: None)
    with pytest.raises(storage_module.StorageError, match="link is still inside"):
        storage_module._remove_sim_folder(workspace.sim_dir("8002"))
    assert mesh.is_file()


def test_removing_a_sim_folder_unlinks_a_file_symlink_and_keeps_its_target(tmp_path):
    """The reparse-point branch of ``_remove_sim_folder`` when it is a FILE, not a directory.

    ``inputs/`` is always a directory link; this covers the other shape the
    walk in ``_remove_sim_folder`` treats the same way, a symlink to a FILE
    outside the sim folder. Skipped where this OS account cannot create a
    file symlink (Windows without Developer Mode or the privilege), which is
    an environment limit, not a defect to report.
    """
    workspace = _ws(tmp_path, "filelinkguard")
    sim = workspace.sim_dir("8007")
    sim.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "outside_target.txt"
    target.write_text("keep me", encoding="utf-8")
    link = sim / "external_link.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("this OS account cannot create a file symlink")
    workspace.append_record(_record("8007", "camp/sim_8007/AL+000"))
    storage_module.delete_sims(workspace.root, ["8007"], apply=True)
    assert not sim.exists()
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "keep me"


def test_sync_relinks_inputs_into_mains_own_library_and_copies_no_mesh(tmp_path):
    main, other = _sync_pair(tmp_path, "relink")
    _linked_sim(other, "8003")
    _write(main.inputs_dir / "geometries" / "wing" / "wing.obj", "o wing\nv 0 0 0\n")
    other.append_record(_record("8003", "camp/sim_8003/AL+000", script_path="scripts/point.fs"))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    inputs = main.sim_dir("8003") / "inputs"
    assert storage_module._is_link(inputs)
    assert (
        Path(storage_module.os.path.realpath(inputs))
        == (main.inputs_dir / "geometries" / "wing").resolve()
    )
    assert entry["inputs_links"] == {"sim_8003": "linked to inputs/geometries/wing"}
    copied = {item["path"] for item in entry["files"]["copied"]}
    assert not any(path.endswith(".obj") for path in copied)


def test_sync_does_not_link_a_geometry_main_does_not_have(tmp_path):
    main, other = _sync_pair(tmp_path, "nolink")
    _linked_sim(other, "8004")
    other.append_record(_record("8004", "camp/sim_8004/AL+000"))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert not (main.sim_dir("8004") / "inputs").exists()
    assert "not in main's inputs/geometries" in entry["inputs_links"]["sim_8004"]


def test_free_space_compacting_a_linked_sim_keeps_the_mesh_and_restore_relinks_it(tmp_path):
    """compact_sims on a linked sim never touches the library, and restore relinks it.

    The owner's rule that opens this section: compacting a simulation whose
    ``inputs/`` is a link into the geometry library must not walk into the
    link (the mesh is not this sim's to zip), and restoring the compacted
    sim must leave ``inputs/`` a link again, not a copy.
    """
    workspace = _ws(tmp_path, "linkedcompact")
    mesh = _linked_sim(workspace, "8005")
    mesh_bytes = mesh.read_bytes()
    workspace.append_record(_record("8005", "camp/sim_8005/AL+000"))
    _write_recipe(workspace, "m001", '[[compact_sims]]\nsims = "all"\n')
    entry = storage_module.free_space(workspace.root, "m001", apply=True)
    assert entry["applied"] is True

    sim = workspace.sim_dir("8005")
    archive = sim.with_name(sim.name + storage_module.COMPACTED_SUFFIX)
    assert archive.is_file()
    assert not sim.exists()

    # the mesh in the geometry library is untouched: same bytes, still there
    assert mesh.is_file()
    assert mesh.read_bytes() == mesh_bytes

    # the archive holds no member under inputs/: the link was never walked into
    with zipfile.ZipFile(archive) as zf:
        assert not any(name.startswith("inputs/") for name in zf.namelist())

    restored = storage_module.ensure_sim_expanded(workspace, "8005", reason="test")
    assert restored is True
    inputs = sim / "inputs"
    assert storage_module._is_link(inputs)
    assert (
        Path(storage_module.os.path.realpath(inputs))
        == (workspace.inputs_dir / "geometries" / "wing").resolve()
    )
    assert mesh.read_bytes() == mesh_bytes


# --------------------------------------------------------------------------- sync of matrices
#
# The owner's rule of 2026-09-28: a matrix is declared by the ONE workspace it
# belongs to; every difference is a merge conflict, and the owner wins.


def _owned_pair(tmp_path: Path, tag: str, main_owns: list[str], other_owns: list[str]):
    main = _ws(tmp_path, f"{tag}_main")
    other = _ws(tmp_path, f"{tag}_other")
    config = main.root / storage_module.SYNC_CONFIG
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "\n".join(
            [
                'main = "main"',
                "[workspaces.main]",
                f"path = '{main.root.resolve().as_posix()}'",
                f"matrices = {json.dumps(main_owns)}",
                "[workspaces.hpc]",
                f"path = '{other.root.resolve().as_posix()}'",
                f"matrices = {json.dumps(other_owns)}",
            ]
        ),
        encoding="utf-8",
    )
    return main, other


def test_sync_refuses_a_matrix_no_workspace_declares(tmp_path):
    main, other = _owned_pair(tmp_path, "undecl", [], [])
    _write(other.root / "matriz.fs", "row")
    with pytest.raises(storage_module.StorageError, match="undeclared: matriz.fs"):
        storage_module.sync_workspaces(main.root, "runs")


def test_a_matrix_declared_by_two_workspaces_is_refused(tmp_path):
    main, _other = _owned_pair(tmp_path, "twice", ["matriz"], ["matriz"])
    with pytest.raises(storage_module.StorageError, match="one workspace only"):
        storage_module.sync_workspaces(main.root, "runs")


def test_a_conflict_on_a_matrix_the_other_owns_is_reported_and_the_owner_wins(tmp_path):
    main, other = _owned_pair(tmp_path, "theirs", [], ["matriz"])
    _write(main.root / "matriz.fs", "main edit")
    _write(other.root / "matriz.fs", "owner edit")
    (preview,) = storage_module.sync_workspaces(main.root, "runs")
    assert preview["matrices"]["conflicts"][0]["kept"] == "hpc"
    assert (main.root / "matriz.fs").read_text(encoding="utf-8") == "main edit"
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert entry["matrices"]["conflicts"][0]["matrix"] == "matriz"
    assert (main.root / "matriz.fs").read_text(encoding="utf-8") == "owner edit"
    archived = list((main.root / ARCHIVE_DIR).glob("sync-*/matriz.fs"))
    assert archived and archived[0].read_text(encoding="utf-8") == "main edit"


def test_a_conflict_on_a_matrix_main_owns_is_reported_and_main_is_kept(tmp_path):
    main, other = _owned_pair(tmp_path, "mine", ["matriz"], [])
    _write(main.root / "matriz.fs", "owner edit")
    _write(other.root / "matriz.fs", "stale copy")
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert entry["matrices"]["conflicts"][0]["kept"] == "main"
    assert (main.root / "matriz.fs").read_text(encoding="utf-8") == "owner edit"


def test_a_matrix_only_the_owner_has_is_copied_and_one_it_does_not_own_is_not(tmp_path):
    main, other = _owned_pair(tmp_path, "new", ["m_main"], ["m_hpc"])
    _write(other.root / "inputs" / "matrices" / "m_hpc.fs", "hpc row")
    _write(other.root / "m_main.fs", "copy of main's")
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert (main.root / "inputs" / "matrices" / "m_hpc.fs").read_text(encoding="utf-8") == "hpc row"
    assert not (main.root / "m_main.fs").exists()
    assert entry["matrices"]["not_copied"][0]["matrix"] == "m_main"


# --------------------------------------------------------------------------- disk_estimate


def test_disk_estimate_says_not_fitting_when_free_space_is_monkeypatched_small(
    tmp_path, monkeypatch
):
    workspace = _ws(tmp_path)
    _write(workspace.sim_dir("8001") / "datapoints" / "DP-1" / "x.bin", "a" * 1000)
    monkeypatch.setattr(storage_module.shutil, "disk_usage", lambda path: SimpleNamespace(free=10))
    line, fits = storage_module.disk_estimate(workspace, 5)
    assert fits is False
    assert "5 point" in line


def test_disk_estimate_fits_when_free_space_is_ample(tmp_path, monkeypatch):
    workspace = _ws(tmp_path)
    _write(workspace.sim_dir("8002") / "datapoints" / "DP-1" / "x.bin", "a" * 10)
    monkeypatch.setattr(
        storage_module.shutil, "disk_usage", lambda path: SimpleNamespace(free=10**12)
    )
    _line, fits = storage_module.disk_estimate(workspace, 5)
    assert fits is True


# --------------------------------------------------------------------------- CLI


def test_cli_space_in_use_subcommand_and_the_owners_flag_form(tmp_path):
    workspace = _ws(tmp_path)
    assert matrix_cli.main(["space-in-use", "--workspace", str(workspace.root)]) == 0
    assert matrix_cli.main(["--workspace", str(workspace.root), "--space-in-use"]) == 0


def test_cli_free_space_flag_form_routes_the_recipe_value(tmp_path):
    workspace = _ws(tmp_path)
    _write_recipe(workspace, "m001", '[[delete_extensions]]\nextensions = [".vtk"]\n')
    assert matrix_cli.main(["--workspace", str(workspace.root), "--free-space", "m001"]) == 0
    calls = storage_module.read_storage_calls(workspace.root)
    assert calls[-1]["action"] == "free-space"
    assert calls[-1]["recipe"].endswith("m001.toml")


def test_cli_delete_sims_accepts_the_owners_bracketed_id_list(tmp_path):
    workspace = _ws(tmp_path)
    workspace.sim_dir("2101").mkdir(parents=True, exist_ok=True)
    workspace.append_record(_record("2101", "camp/sim_2101/AL+000"))
    workspace.sim_dir("2102").mkdir(parents=True, exist_ok=True)
    workspace.append_record(_record("2102", "camp/sim_2102/AL+000"))
    assert matrix_cli.main(["delete-sims", "[2101,2102]", "--workspace", str(workspace.root)]) == 0
    entry = storage_module.read_storage_calls(workspace.root)[-1]
    assert entry["action"] == "delete-sims"
    assert entry["applied"] is False
    assert {item["sim_id"] for item in entry["sims"]} == {"2101", "2102"}


# --------------------------------------------------------------------------- mutants
#
# Each mutant is a single-line change applied to a COPY of storage.py's
# source text, imported as a standalone module. src/ itself is never
# touched: the coordinator is editing it in a parallel session.


def _mutant_module(tmp_path: Path, old: str, new: str, tag: str):
    text = STORAGE_SRC.read_text(encoding="utf-8")
    count = text.count(old)
    assert count == 1, f"mutant anchor for {tag!r} matched {count} times, not exactly 1"
    mutated = text.replace(old, new, 1)
    assert mutated != text
    path = tmp_path / f"_storage_mutant_{tag}.py"
    path.write_text(mutated, encoding="utf-8")
    module_name = f"_storage_mutant_{tag}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ---- 1: a named output is protected from delete_extensions


def _protection_holds(module, tmp_path: Path) -> bool:
    workspace = _ws(tmp_path, "protset")
    sim = workspace.sim_dir("3101")
    named = sim / "datapoints" / "DP-1" / "loads.vtk"
    unnamed = sim / "datapoints" / "DP-1" / "junk.vtk"
    _write(named, "keep-me")
    _write(unnamed, "delete-me")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3101/AL+000",
            sim_id="3101",
            fs_version_requested="26.123",
            package_version="0.30.0",
            script_sha256="c" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
            outputs=["datapoints/DP-1/loads.vtk"],
        )
    )
    recipe = workspace.root / storage_module.MANAGEMENT_DIR / "m001.toml"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text('[[delete_extensions]]\nextensions = [".vtk"]\n', encoding="utf-8")
    module.free_space(workspace.root, "m001", apply=True)
    return named.exists() and not unnamed.exists()


_PROTECTION_OLD = (
    "        for name in names:\n"
    "            candidate = (folder / name).resolve()\n"
    "            keep.add(candidate)\n"
)
_PROTECTION_NEW = (
    "        for name in names:\n"
    "            candidate = (folder / name).resolve()\n"
    "            pass  # MUTANT: a named output is no longer protected\n"
)


def test_a_named_output_is_protected_from_delete_extensions(tmp_path):
    assert _protection_holds(storage_module, tmp_path)


def test_mutant_disabling_named_output_protection_is_caught(tmp_path):
    mutant = _mutant_module(tmp_path, _PROTECTION_OLD, _PROTECTION_NEW, "protection")
    assert not _protection_holds(mutant, tmp_path / "mut")


# ---- 2: preview changes nothing (delete_extensions)


def _preview_changes_nothing(module, tmp_path: Path) -> bool:
    workspace = _ws(tmp_path, "prev")
    target = workspace.sim_dir("4101") / "datapoints" / "DP-1" / "loads.vtk"
    _write(target, "data")
    workspace.append_record(_record("4101", "camp/sim_4101/AL+000"))
    recipe = workspace.root / storage_module.MANAGEMENT_DIR / "m001.toml"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text('[[delete_extensions]]\nextensions = [".vtk"]\n', encoding="utf-8")
    module.free_space(workspace.root, "m001", apply=False)
    return target.exists()


_PREVIEW_OLD = (
    "                if apply:\n"
    "                    file.unlink()\n"
    "                    freed += size\n"
)
_PREVIEW_NEW = (
    "                if True:  # MUTANT: preview also deletes\n"
    "                    file.unlink()\n"
    "                    freed += size\n"
)


def test_free_space_preview_changes_nothing(tmp_path):
    assert _preview_changes_nothing(storage_module, tmp_path)


def test_mutant_preview_deleting_files_is_caught(tmp_path):
    mutant = _mutant_module(tmp_path, _PREVIEW_OLD, _PREVIEW_NEW, "preview")
    assert not _preview_changes_nothing(mutant, tmp_path / "mut")


# ---- 3: a SUBMITTED sim is never compacted


def _submitted_not_compacted(module, tmp_path: Path) -> bool:
    workspace = _ws(tmp_path, "sub")
    sim = workspace.sim_dir("5101")
    _write(sim / "datapoints" / "DP-1" / "x.txt", "data")
    workspace.append_record(_record("5101", "camp/sim_5101/AL+000", status=RunStatus.SUBMITTED))
    recipe = workspace.root / storage_module.MANAGEMENT_DIR / "m001.toml"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text('[[compact_sims]]\nsims = "all"\n', encoding="utf-8")
    module.free_space(workspace.root, "m001", apply=True)
    archive = sim.with_name(sim.name + storage_module.COMPACTED_SUFFIX)
    return sim.is_dir() and not archive.exists()


_SUBMITTED_OLD = (
    '            if any(row.get("status") == RunStatus.SUBMITTED.value for row in rows):\n'
    '                step["refused"][sim] = "a run is still SUBMITTED"\n'
    "                continue\n"
)
_SUBMITTED_NEW = (
    "            if False:  # MUTANT: SUBMITTED sims are compacted too\n"
    '                step["refused"][sim] = "a run is still SUBMITTED"\n'
    "                continue\n"
)


def test_a_submitted_sim_is_never_compacted(tmp_path):
    assert _submitted_not_compacted(storage_module, tmp_path)


def test_mutant_compacting_a_submitted_sim_is_caught(tmp_path):
    mutant = _mutant_module(tmp_path, _SUBMITTED_OLD, _SUBMITTED_NEW, "submitted")
    assert not _submitted_not_compacted(mutant, tmp_path / "mut")


# ---- 4: a restore refuses a tampered archive (the hash check)


def _tamper_zip_member(archive: Path, member: str, new_content: bytes) -> None:
    scratch = archive.with_suffix(".tamper.zip")
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(scratch, "w") as dest:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == member:
                data = new_content
            dest.writestr(info, data)
    scratch.replace(archive)


def _restore_checks_the_hash(module, tmp_path: Path) -> bool:
    workspace = _ws(tmp_path, "restore")
    sim = workspace.sim_dir("6101")
    target = sim / "datapoints" / "DP-1" / "x.txt"
    _write(target, "original-bytes")
    workspace.append_record(_record("6101", "camp/sim_6101/AL+000"))
    recipe = workspace.root / storage_module.MANAGEMENT_DIR / "m001.toml"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text('[[compact_sims]]\nsims = "all"\n', encoding="utf-8")
    module.free_space(workspace.root, "m001", apply=True)
    archive = sim.with_name(sim.name + module.COMPACTED_SUFFIX)
    _tamper_zip_member(archive, "datapoints/DP-1/x.txt", b"corrupted-bytes")
    try:
        module.ensure_sim_expanded(workspace, "6101", reason="test")
    except module.StorageError:
        return True  # refused the tampered archive, as it must
    return False  # restored despite the tamper: the hash check is broken


_RESTORE_OLD = (
    '    for name, digest in dict(meta.get("members", {})).items():\n'
    "        if _sha256(temporary / name) != digest:\n"
)
_RESTORE_NEW = (
    '    for name, digest in dict(meta.get("members", {})).items():\n'
    "        if False:  # MUTANT: the restored hash is never checked\n"
)


def test_a_restore_refuses_a_tampered_archive(tmp_path):
    assert _restore_checks_the_hash(storage_module, tmp_path)


def test_mutant_disabling_the_restore_hash_check_is_caught(tmp_path):
    mutant = _mutant_module(tmp_path, _RESTORE_OLD, _RESTORE_NEW, "restorehash")
    assert not _restore_checks_the_hash(mutant, tmp_path / "mut")


# ---- 5: a run id a delete-sims note retired is not re-added by sync


def _deleted_run_stays_out(module) -> bool:
    main_rows = [
        {
            "run_id": "deleted/sim_9001/20260101-000000",
            "deleted_sim": "9001",
            "deleted_run_ids": ["camp/sim_9001/AL+000"],
        }
    ]
    other_rows = [{"run_id": "camp/sim_9001/AL+000", "sim_id": "9001", "status": "CONVERGED"}]
    merged, added, _replaced, _conflicts = module._merge_runs(main_rows, other_rows, False)
    return "camp/sim_9001/AL+000" not in added and len(merged) == 1


_DELETED_OLD = (
    "        if str(run_id) in deleted:\n"
    '            conflicts.append({"run_id": run_id, "reason": "deleted in main by delete-sims"})\n'
    "            continue\n"
)
_DELETED_NEW = (
    "        if False:  # MUTANT: a deleted run id is re-added\n"
    '            conflicts.append({"run_id": run_id, "reason": "deleted in main by delete-sims"})\n'
    "            continue\n"
)


def test_a_deleted_run_id_is_not_re_added_by_merge_runs(tmp_path):
    assert _deleted_run_stays_out(storage_module)


def test_mutant_re_adding_a_deleted_run_id_is_caught(tmp_path):
    mutant = _mutant_module(tmp_path, _DELETED_OLD, _DELETED_NEW, "deletedrun")
    assert not _deleted_run_stays_out(mutant)


# ---- 6: apply is refused without --matrix-products when a product is shared


def _apply_refused_without_choice(module, tmp_path: Path) -> bool:
    workspace = _ws(tmp_path, "refusecheck")
    sim_a = workspace.sim_dir("3201")
    sim_b = workspace.sim_dir("3202")
    _write(sim_a / "datapoints" / "DP-1" / "x.txt", "a")
    _write(sim_b / "datapoints" / "DP-1" / "x.txt", "b")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3201/AL+000",
            sim_id="3201",
            matrix_stem="matriz",
            fs_version_requested="26.123",
            package_version="0.30.0",
            script_sha256="c" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
        )
    )
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3202/AL+000",
            sim_id="3202",
            matrix_stem="matriz",
            fs_version_requested="26.123",
            package_version="0.30.0",
            script_sha256="c" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
        )
    )
    products_dir = workspace.root / "post" / "matriz"
    products_dir.mkdir(parents=True, exist_ok=True)
    _write(products_dir / "polar.csv", "shared")
    document = {
        "products": {
            "polar.csv": {"sim_id": None, "runs": ["camp/sim_3201/AL+000", "camp/sim_3202/AL+000"]}
        }
    }
    (products_dir / "products.json").write_text(json.dumps(document), encoding="utf-8")
    try:
        module.delete_sims(workspace.root, ["3201"], apply=True)
    except module.StorageError:
        return True  # refused, as it must
    return False  # applied without a choice: the refusal is broken


_REFUSE_OLD = "    if apply and shared and matrix_products is None:\n        raise StorageError(\n"
_REFUSE_NEW = (
    "    if False:  # MUTANT: apply never refuses a shared product\n        raise StorageError(\n"
)


def test_delete_sims_apply_is_refused_without_matrix_products(tmp_path):
    assert _apply_refused_without_choice(storage_module, tmp_path)


def test_mutant_removing_the_apply_refusal_is_caught(tmp_path):
    mutant = _mutant_module(tmp_path, _REFUSE_OLD, _REFUSE_NEW, "refuse")
    assert not _apply_refused_without_choice(mutant, tmp_path / "mut")


# ---- 7: restoring a compacted, linked sim relinks inputs/ rather than leaving it copied or missing


def _restore_relinks_inputs(module, tmp_path: Path) -> bool:
    workspace = _ws(tmp_path, "relinkcheck")
    mesh = _linked_sim(workspace, "8006")
    mesh_bytes = mesh.read_bytes()
    workspace.append_record(_record("8006", "camp/sim_8006/AL+000"))
    recipe = workspace.root / storage_module.MANAGEMENT_DIR / "m001.toml"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text('[[compact_sims]]\nsims = "all"\n', encoding="utf-8")
    module.free_space(workspace.root, "m001", apply=True)
    module.ensure_sim_expanded(workspace, "8006", reason="test")
    inputs = workspace.sim_dir("8006") / "inputs"
    return module._is_link(inputs) and mesh.read_bytes() == mesh_bytes


_RELINK_OLD = (
    '    link = meta.get("inputs_link")\n    if link and not (folder / "inputs").exists():\n'
)
_RELINK_NEW = (
    '    link = meta.get("inputs_link")\n'
    "    if False:  # MUTANT: restore never relinks inputs into the library\n"
)


def test_restore_of_a_compacted_linked_sim_relinks_inputs(tmp_path):
    assert _restore_relinks_inputs(storage_module, tmp_path)


def test_mutant_dropping_the_restore_relink_is_caught(tmp_path):
    mutant = _mutant_module(tmp_path, _RELINK_OLD, _RELINK_NEW, "relink")
    assert not _restore_relinks_inputs(mutant, tmp_path / "mut")
