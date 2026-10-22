"""Tier 1 offline: ``pyfs-matrix delete-sims --force`` (FR-306).

A simulation with a run still SUBMITTED is refused by ``delete-sims``; with
``--force`` it is deleted whatever the status of its records. Every workspace
is a real ``tmp_path`` tree.
"""
# The evidence line of this requirement cites this module
# (docs/unpublished/requirements/functional-requirements.md):

from __future__ import annotations

import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

from pyflightstream.run import _cli_print
from pyflightstream.run import cli as matrix_cli
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.naming import ARCHIVE_DIR
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from pyflightstream.workspace.storage import StorageError
from tests.tier1_offline.test_goal035_storage import _linked_sim, _sync_pair, _write
from tests.tier1_offline.test_goal035_storage import _record as _storage_record

REFUSAL = "have a run still SUBMITTED; collect it first"


def _record(sim_id: str, run_id: str, status: RunStatus) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id=sim_id,
        matrix_stem="matriz",
        fs_version_requested="26.123",
        package_version="0.33.0",
        script_sha256="c" * 64,
        raw_flag=False,
        status=status,
        outputs=[],
        script_path=None,
        inputs_sha256={},
    )


def _workspace(tmp_path: Path) -> CampaignWorkspace:
    root = tmp_path / "camp"
    workspace = CampaignWorkspace(root)
    workspace.init(root)
    for sim, status in (("6001", RunStatus.SUBMITTED), ("6002", RunStatus.CONVERGED)):
        folder = workspace.sim_dir(sim) / "datapoints" / "DP-1"
        folder.mkdir(parents=True)
        (folder / "x.txt").write_text("data", encoding="utf-8")
        workspace.append_record(_record(sim, f"camp/sim_{sim}/AL+000", status))
    products = workspace.root / "post" / "matriz"
    products.mkdir(parents=True)
    (products / "sim_6001_diag.csv").write_text("own", encoding="utf-8")
    document = {
        "products": {
            "sim_6001_diag.csv": {"sim_id": "6001", "runs": ["camp/sim_6001/AL+000"]},
        },
        "provenance": {},
    }
    (products / "products.json").write_text(json.dumps(document), encoding="utf-8")
    return workspace


def _link(target: Path, link: Path) -> None:
    """Make ``link`` a directory link to ``target``; skip when the host does not permit one.

    On Windows the link is a junction, which needs no privilege, so the test runs on every
    host; a symbolic link elsewhere.
    """
    try:
        if sys.platform == "win32":
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"links are not permitted here: {error}")


def _rows(workspace: CampaignWorkspace) -> list[dict]:
    return _read_record_rows(workspace.manifest_path)


def test_refused_without_force_with_the_same_text(tmp_path):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    with pytest.raises(StorageError) as caught:
        storage_module.delete_sims(workspace.root, ["6001"], apply=True)
    assert str(caught.value) == "sims ['6001'] have a run still SUBMITTED; collect it first"
    assert workspace.sim_dir("6001").exists()
    with pytest.raises(StorageError, match=REFUSAL):
        storage_module.delete_sims(workspace.root, ["6001"], force=False)


def test_force_preview_names_the_submitted_sim_and_changes_nothing(tmp_path, capsys):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    before = workspace.manifest_path.read_bytes()
    entry = storage_module.delete_sims(workspace.root, ["6001", "6002"], force=True)
    assert entry["applied"] is False
    assert entry["forced_submitted"] == ["6001"]
    assert workspace.sim_dir("6001").exists() and workspace.sim_dir("6002").exists()
    assert workspace.manifest_path.read_bytes() == before
    assert (workspace.root / "post" / "matriz" / "sim_6001_diag.csv").exists()
    _cli_print._print_delete_sims(entry)
    assert "sim 6001: still SUBMITTED, deleted because of --force" in capsys.readouterr().out


def test_force_apply_deletes_folder_products_records_and_records_the_call(tmp_path):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    entry = storage_module.delete_sims(workspace.root, ["6001"], force=True, apply=True)
    assert entry["applied"] is True
    assert not workspace.sim_dir("6001").exists()
    assert workspace.sim_dir("6002").exists()
    assert not (workspace.root / "post" / "matriz" / "sim_6001_diag.csv").exists()
    rows = _rows(workspace)
    assert not any(row.get("run_id") == "camp/sim_6001/AL+000" for row in rows)
    assert any(str(row.get("run_id")).startswith("deleted/sim_6001/") for row in rows)
    assert any(row.get("run_id") == "camp/sim_6002/AL+000" for row in rows)
    archived = list((workspace.root / ARCHIVE_DIR).glob("runs-*.json"))
    assert archived
    call = storage_module.read_storage_calls(workspace.root)[-1]
    assert call["force"] is True
    assert call["sims"][0]["statuses"] == [RunStatus.SUBMITTED.value]


def test_without_force_the_call_records_force_false(tmp_path):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    storage_module.delete_sims(workspace.root, ["6002"], apply=True)
    call = storage_module.read_storage_calls(workspace.root)[-1]
    assert call["force"] is False
    assert call["forced_submitted"] == []


def test_cli_force_flag_reaches_the_library(tmp_path):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    args = ["delete-sims", "6001", "--workspace", str(workspace.root)]
    assert matrix_cli.main([*args, "--apply"]) != 0
    assert workspace.sim_dir("6001").exists()
    assert matrix_cli.main([*args, "--force", "--apply"]) == 0
    assert not workspace.sim_dir("6001").exists()


def test_mutant_ignoring_force_turns_the_check_red(tmp_path):
    # Verifies FR-306.
    source = Path(storage_module.__file__).read_text(encoding="utf-8")
    old = "    if submitted and not force:\n"
    assert source.count(old) == 1
    mutant = source.replace(old, "    if submitted:\n")
    assert mutant != source
    spec = importlib.util.spec_from_loader("storage_mutant_force", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "pyflightstream.workspace"
    sys.modules["storage_mutant_force"] = module
    try:
        exec(compile(mutant, "storage_mutant_force.py", "exec"), module.__dict__)
        workspace = _workspace(tmp_path)
        with pytest.raises(Exception, match=REFUSAL):
            module.delete_sims(workspace.root, ["6001"], force=True)
        module_real = storage_module.delete_sims(workspace.root, ["6001"], force=True)
        assert module_real["forced_submitted"] == ["6001"]
    finally:
        sys.modules.pop("storage_mutant_force", None)


def test_f_1488_one_bare_simulation_id_is_one_simulation(tmp_path):
    """F2-0203: F-1488, a string selector was split into characters and named other folders."""
    workspace = _workspace(tmp_path)
    storage_module.delete_sims(workspace.root, "6002", apply=True)
    assert not workspace.sim_dir("6002").exists()
    assert workspace.sim_dir("6001").exists()


def test_f_743_a_product_path_outside_the_post_folder_deletes_nothing(tmp_path):
    """F2-0203: F-743, a traversal key of products.json is refused before anything is removed."""
    workspace = _workspace(tmp_path)
    outside = workspace.root / "escape.txt"
    outside.write_text("not a product", encoding="utf-8")
    manifest = workspace.root / "post" / "matriz" / "products.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["products"]["../../escape.txt"] = {"sim_id": "6002", "runs": []}
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(StorageError, match="not inside"):
        storage_module.delete_sims(workspace.root, ["6002"], apply=True)
    assert outside.read_text(encoding="utf-8") == "not a product"
    assert workspace.sim_dir("6002").exists()


def test_f_742_a_planted_staging_link_is_unlinked_and_never_extracted_through(tmp_path):
    """F2-0203: F-742, the restore's staging folder is a link to an outside folder: the link
    is removed, and the archive is extracted into a real folder."""
    workspace = _workspace(tmp_path)
    folder = workspace.sim_dir("7001")
    archive = folder.with_name(folder.name + ".zip")
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("x.txt", "restored")
    outside = tmp_path / "outside"
    outside.mkdir()
    staging = folder.with_name(folder.name + f".{os.getpid()}.restoring")
    _link(outside, staging)
    assert storage_module.ensure_sim_expanded(workspace, "7001", reason="the test")
    assert (folder / "x.txt").read_text(encoding="utf-8") == "restored"
    assert list(outside.iterdir()) == []


def test_rb4_a_product_reached_through_a_linked_folder_deletes_nothing(tmp_path):
    """RB4-01: F-743, a product key whose folder is a link leaves the post folder too.

    The link is a junction on Windows (no privilege needed), so the test runs on every host.
    """
    workspace = _workspace(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "p.csv").write_text("another workspace's product", encoding="utf-8")
    _link(elsewhere, workspace.root / "post" / "matriz" / "shared")
    manifest = workspace.root / "post" / "matriz" / "products.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["products"]["shared/p.csv"] = {"sim_id": "6002", "runs": []}
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(StorageError, match="not inside"):
        storage_module.delete_sims(workspace.root, ["6002"], apply=True)
    assert (elsewhere / "p.csv").read_text(encoding="utf-8") == "another workspace's product"
    assert workspace.sim_dir("6002").exists()


@pytest.mark.parametrize(
    "document",
    [[], {"schema": "pyfs-storage/1", "calls": [None]}, {"schema": "pyfs-storage/1", "calls": [1]}],
)
def test_f1543_malformed_storage_register_raises_storage_error(tmp_path, document):
    # A register that is no object, or whose calls are no objects, is the documented refusal.
    workspace = _workspace(tmp_path)
    (workspace.root / storage_module.STORAGE_FILE).write_text(
        json.dumps(document), encoding="utf-8"
    )
    with pytest.raises(StorageError, match="is not a"):
        storage_module.read_storage_calls(workspace.root)
    with pytest.raises(StorageError, match="is not a"):
        storage_module.record_storage_call(workspace.root, {"action": "x"})


def test_f1497_unmappable_source_link_is_not_reported_as_linked(tmp_path):
    # A source link outside the other library, named like no folder of main's, must not
    # fall back to linking main's whole geometry library.
    main, other = _sync_pair(tmp_path, "stray")
    stray = tmp_path / "stray_geometry"
    _write(stray / "x.obj", "o x\n")
    (main.inputs_dir / "geometries").mkdir(parents=True, exist_ok=True)
    folder = other.sim_dir("8020")
    _write(folder / "scripts" / "point.fs", "script")
    _link(stray.resolve(), folder / "inputs")
    other.append_record(_storage_record("8020", "camp/sim_8020/AL+000"))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert not (main.sim_dir("8020") / "inputs").exists()
    assert entry["inputs_links"]["sim_8020"].startswith("not linked")


def test_f1271_a_recorded_windows_path_is_split_on_any_platform(tmp_path):
    recorded = "D:\\old\\camp\\inputs\\geometries\\wing"
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(workspace.root)
    _write(workspace.inputs_dir / "geometries" / "wing" / "wing.obj", "o w\n")
    archive = workspace.root / "sims" / "sim_9101.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("a.txt", "a")
        bundle.writestr(
            "_pyfs_compacted.json",
            json.dumps({"sim_id": "9101", "inputs_link": recorded, "members": {}}),
        )
    assert storage_module.ensure_sim_expanded(workspace, "9101", reason="the test")
    call = storage_module.read_storage_calls(workspace.root)[-1]
    wanted = (workspace.inputs_dir / "geometries" / "wing").resolve()
    assert call["inputs_link_restored"] is True
    assert Path(call["inputs_link_target"]) == wanted
    assert (workspace.sim_dir("9101") / "inputs" / "wing.obj").is_file()


def test_f347_disk_estimate_ignores_empty_datapoint_folders(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(workspace.root)
    _write(workspace.sim_dir("7001") / "datapoints" / "DP-1" / "x.bin", "a" * 1000)
    (workspace.sim_dir("7001") / "datapoints" / "DP-2").mkdir(parents=True)
    (workspace.sim_dir("7001") / "datapoints" / "DP-3").mkdir(parents=True)
    line, fits = storage_module.disk_estimate(workspace, 10)
    assert "(1 measured)" in line
    assert fits


def test_f1235_a_submitted_compacted_simulation_is_not_brought(tmp_path):
    main, other = _sync_pair(tmp_path, "zips")
    (other.root / "sims").mkdir(parents=True, exist_ok=True)
    (other.root / "sims" / "sim_6001.zip").write_bytes(b"zip")
    (other.root / "sims" / "sim_6002.zip").write_bytes(b"zip")
    other.append_record(_storage_record("6001", "camp/sim_6001/AL+000", status=RunStatus.SUBMITTED))
    storage_module.sync_workspaces(main.root, "all", apply=True)
    assert not (main.root / "sims" / "sim_6001.zip").exists()
    assert (main.root / "sims" / "sim_6002.zip").is_file()


def test_f1236_sync_does_not_relink_a_submitted_record_only_simulation(tmp_path):
    main, other = _sync_pair(tmp_path, "submitted")
    _linked_sim(other, "8010")
    _write(main.inputs_dir / "geometries" / "wing" / "wing.obj", "o wing\n")
    _write(main.sim_dir("8010") / "scripts" / "point.fs", "script")  # main holds the folder
    other.append_record(_storage_record("8010", "camp/sim_8010/AL+000", status=RunStatus.SUBMITTED))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert entry["runs"]["submitted_sims_record_only"] == ["8010"]
    assert "sim_8010" not in entry["inputs_links"]
    assert not (main.sim_dir("8010") / "inputs").exists()


def test_f746_sync_refuses_to_write_through_a_destination_link(tmp_path):
    main, other = _sync_pair(tmp_path, "dstlink")
    outside = tmp_path / "outside"
    outside.mkdir()
    (main.root / "post").rmdir()
    _link(outside.resolve(), main.root / "post")
    _write(other.root / "post" / "m" / "p.csv", "data")
    with pytest.raises(StorageError, match="is a link"):
        storage_module.sync_workspaces(main.root, "post", apply=True)
    assert list(outside.iterdir()) == []


def test_f747_a_planted_name_at_the_temporary_path_is_not_written_through(tmp_path):
    main, other = _sync_pair(tmp_path, "planted")
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    _write(other.root / "post" / "m" / "t.txt", "new")
    target = main.root / "post" / "m" / "t.txt"
    target.parent.mkdir(parents=True)
    planted = target.with_name(f".{target.name}.{os.getpid()}.pyfs-sync.tmp")
    os.link(victim, planted)  # same inode as the victim, as a link would be
    storage_module.sync_workspaces(main.root, "post", apply=True)
    assert victim.read_text(encoding="utf-8") == "precious"
    assert target.read_text(encoding="utf-8") == "new"


def test_f1234_a_tombstone_names_its_call_by_stamp_when_another_call_intervenes(
    tmp_path, monkeypatch
):
    workspace = _workspace(tmp_path)
    original = CampaignWorkspace._replace_manifest

    def _with_a_concurrent_call(self, *args, **kwargs):
        storage_module.record_storage_call(workspace.root, {"action": "other-command"})
        return original(self, *args, **kwargs)

    monkeypatch.setattr(CampaignWorkspace, "_replace_manifest", _with_a_concurrent_call)
    storage_module.delete_sims(workspace.root, ["6002"], apply=True)
    tombstone = next(row for row in _rows(workspace) if row.get("deleted_sim") == "6002")
    calls = storage_module.read_storage_calls(workspace.root)
    by_stamp = [c for c in calls if c.get("delete_stamp") == tombstone["delete_stamp"]]
    assert by_stamp
    assert by_stamp[-1]["action"] == "delete-sims" and by_stamp[-1]["applied"] is True


def _archive_with_hash_table(tmp_path, members):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(workspace.root)
    archive = workspace.root / "sims" / "sim_9001.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.txt", "a")
        if members is not None:
            zf.writestr("_pyfs_compacted.json", json.dumps({"members": members}))
    return workspace, archive


def test_x_f1369_a_member_missing_from_the_zip_is_a_storage_error_and_leaves_no_folder(tmp_path):
    workspace, archive = _archive_with_hash_table(tmp_path, {"gone.txt": "0" * 64})
    folder = workspace.sim_dir("9001")
    with pytest.raises(StorageError, match="gone.txt"):
        storage_module.ensure_sim_expanded(workspace, "9001", reason="the test")
    assert not list(folder.parent.glob("*.restoring"))
    assert archive.is_file()


def test_x_f1370_an_archive_without_a_hash_table_warns_that_nothing_is_verified(tmp_path):
    workspace, archive = _archive_with_hash_table(tmp_path, None)
    with pytest.warns(Warning, match="without a hash check"):
        storage_module.ensure_sim_expanded(workspace, "9001", reason="the test")


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", "5", "null"])
def test_f2_0809_a_storage_record_that_is_not_a_record_is_a_storage_error(tmp_path, text):
    """PFS-2119.013: invalid JSON and a non-object document both refuse by path."""
    (tmp_path / storage_module.STORAGE_FILE).write_text(text, encoding="utf-8")
    with pytest.raises(StorageError) as caught:
        storage_module.read_storage_calls(tmp_path)
    assert storage_module.STORAGE_FILE in str(caught.value)


def test_f2_0809_a_malformed_toml_of_the_storage_commands_names_the_file(tmp_path):
    """PFS-2119.013: the recipe and sync-configuration readers refuse a broken file by path."""
    (tmp_path / storage_module.MANAGEMENT_DIR).mkdir(parents=True)
    recipe = tmp_path / storage_module.MANAGEMENT_DIR / "m001.toml"
    recipe.write_text("[[prune_step_exports\n", encoding="utf-8")
    with pytest.raises(StorageError, match="m001.toml"):
        storage_module.read_recipe(tmp_path, "m001")
    config = tmp_path / storage_module.SYNC_CONFIG
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("main = \n", encoding="utf-8")
    for reader in (storage_module.read_sync_config, storage_module.read_matrix_owners):
        with pytest.raises(StorageError, match=config.name):
            reader(tmp_path)


def test_f2_0809_delete_sims_archives_the_products_manifest_before_rewriting_it(tmp_path):
    """PFS-2119.058: the previous products.json is in the archive `restore products` reads."""
    workspace = _workspace(tmp_path)
    manifests = sorted((workspace.root / "post").glob("*/products.json"))
    assert manifests, "the fixture holds a products manifest"
    before = {manifest: manifest.read_bytes() for manifest in manifests}
    storage_module.delete_sims(workspace.root, ["6001"], force=True, apply=True)
    for manifest, content in before.items():
        archived = list((manifest.parent / ARCHIVE_DIR).rglob("products.json"))
        assert archived, f"{manifest} was rewritten without archiving the previous copy"
        assert content in {copy.read_bytes() for copy in archived}
