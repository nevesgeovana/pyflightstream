"""Package B2 of 0.32.0: the sync of every simulation folder, and the two matrix homes.

- P0320-SYNC-ALL-FOLDERS: ``sync`` compares every ``sims/sim_*`` folder on both
  sides, recorded or not, and names the folders no record carries.
- P0320-SYNC-RESTORE-OPTIN: ``restore`` (CLI ``--restore``) is off by default;
  asked, the applying sync rebuilds the records of those folders through
  ``run.records.rebuild`` once it has released the lease.
- P0320-SYNC-ATOMIC: a file is copied to a temporary name and renamed in place,
  so an interrupted copy never leaves a partial target.
- P0320-SYNC-SKIP-ARCHIVES: every folder named ``archive`` is skipped unless
  ``include_archives``; the entry counts the files and bytes skipped.
- P0320-MATRICES-HOME and P0320-RST-1: ``inputs/matrices/`` is a home equal to
  the root for the sync, the plan's POL census and the post; one stem in both
  homes is read once when the bytes are identical, refused naming both paths
  when they differ.
- P0320-RST-6: the sync holds the ``runs.json`` lease for the whole of its
  merge and copy, so a restore, or a second sync, refuses while it writes.
- P0320-RUNS-NAME: ``sync``, ``free-space`` and ``delete-sims`` read the
  manifest ``run.records.resolve_manifest`` names.

Every workspace here is synthetic.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-220, FR-221, FR-222, FR-225, FR-226, FR-227.

from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run import records as run_records

# The rebuild and what it reads are private modules of run since 0.33.0 (AD-11).
from pyflightstream.run._rebuild_evidence import _matrices
from pyflightstream.workspace import WorkspaceError, find_matrix, matrix_by_stem
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.naming import ARCHIVE_DIR
from tests.tier1_offline.test_goal021_matrix_ids import _matrix, row
from tests.tier1_offline.test_goal021_matrix_ids import _workspace as _library
from tests.tier1_offline.test_goal035_storage import (
    _record,
    _sync_pair,
    _write,
    _write_recipe,
)
from tests.tier1_offline.test_goal036_pol_census import _plan_recording

# --------------------------------------------------------------------------- helpers


def _orphan_pair(tmp_path: Path, tag: str):
    """Other: sim 2001 recorded, sim 2002 copied by hand; main: sim 3000 by hand."""
    main, other = _sync_pair(tmp_path, tag)
    _write(other.sim_dir("2001") / "scripts" / "point.fs", "recorded")
    other.append_record(_record("2001", "campo/sim_2001/AL+000"))
    _write(other.sim_dir("2002") / "scripts" / "point.fs", "by hand")
    _write(other.sim_dir("2002") / "datapoints" / "DP-1" / "point_log.txt", "log")
    _write(main.sim_dir("3000") / "scripts" / "point.fs", "main by hand")
    return main, other


class _Rebuilds:
    """A stand-in for ``run.records.rebuild`` that records each call and the lease."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, root, **kwargs):
        lease = Path(root) / "runs.json.lock"
        self.calls.append({"root": Path(root), "lease_held": lease.exists(), **kwargs})
        return {
            "applied": kwargs.get("apply", False),
            "rebuilt": [{"sim": sim} for sim in kwargs.get("sims") or []],
            "refused": {},
            "records": ["bulky"],
        }


# --------------------------------------------------------------------------- all folders


def test_p0320_sync_all_folders_names_every_sim_folder_of_both_sides(tmp_path):
    # P0320-SYNC-ALL-FOLDERS
    main, other = _orphan_pair(tmp_path, "allfolders")
    (preview,) = storage_module.sync_workspaces(main.root, "runs")
    sims = preview["sims"]
    assert sims["main"] == ["3000"]
    assert sims["other"] == ["2001", "2002"]
    assert sims["only_main"] == ["3000"]
    assert sims["only_other"] == ["2001", "2002"]
    assert sims["both"] == []
    assert sims["without_record"] == ["2002", "3000"]
    (applied,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert applied["sims"]["without_record"] == ["2002", "3000"]
    # The folder no record names is brought like a recorded one.
    assert (main.sim_dir("2002") / "scripts" / "point.fs").read_text("utf-8") == "by hand"
    again = storage_module.sync_workspaces(main.root, "runs")[0]["sims"]
    assert again["both"] == ["2001", "2002"]
    assert again["only_main"] == ["3000"]


def test_p0320_sync_all_folders_counts_a_compacted_sim_and_the_cli_prints_them(tmp_path, capsys):
    # P0320-SYNC-ALL-FOLDERS
    main, other = _orphan_pair(tmp_path, "allcli")
    (other.root / "sims" / "sim_2003.zip").write_bytes(b"PK")
    # The level "all" brings a compacted simulation, so main will hold 2003.
    (entry,) = storage_module.sync_workspaces(main.root, "all")
    assert "2003" in entry["sims"]["other"]
    assert matrix_cli.main(["sync", "all", "--workspace", str(main.root)]) == 0
    out = capsys.readouterr().out
    assert "sims/: 1 in main, 3 in other, 0 in both" in out
    assert "without a record: 2002, 2003, 3000" in out
    assert "--restore" in out


def test_p0320_sync_all_folders_without_record_names_only_what_main_will_hold(
    tmp_path, monkeypatch
):
    # P0320-SYNC-ALL-FOLDERS and P0320-SYNC-RESTORE-OPTIN: "without a record"
    # is what main holds, or holds once applied, so the restore, which rebuilds
    # in main, is never handed a simulation the level does not bring: a
    # compacted one below "all", or a folder holding nothing the level copies.
    rebuilds = _Rebuilds()
    monkeypatch.setattr(run_records, "rebuild", rebuilds)
    main, other = _orphan_pair(tmp_path, "heldonly")
    (other.root / "sims" / "sim_2003.zip").write_bytes(b"PK")
    _write(other.sim_dir("2004") / "datapoints" / "DP-1" / "surface.vtk", "not at runs")
    (preview,) = storage_module.sync_workspaces(main.root, "runs", restore=True)
    assert preview["sims"]["other"] == ["2001", "2002", "2003", "2004"]
    assert preview["sims"]["without_record"] == ["2002", "3000"]
    assert preview["restore"]["sims"] == ["2002", "3000"]
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True, restore=True)
    (call,) = rebuilds.calls
    assert call["sims"] == ["2002", "3000"]
    assert not (main.root / "sims" / "sim_2003.zip").exists()
    assert not main.sim_dir("2004").exists()
    (whole,) = storage_module.sync_workspaces(main.root, "all")
    assert whole["sims"]["without_record"] == ["2002", "2003", "2004", "3000"]


def test_p0320_sync_all_folders_leaves_out_a_folder_a_delete_sims_note_names(tmp_path):
    # P0320-SYNC-ALL-FOLDERS: a simulation deleted in main and still on disk in
    # the other workspace is accounted for by its note, never offered to restore.
    main, other = _orphan_pair(tmp_path, "noted")
    _write(main.sim_dir("3100") / "datapoints" / "DP-1" / "x.txt", "a")
    main.append_record(_record("3100", "campo/sim_3100/AL+000"))
    storage_module.delete_sims(main.root, ["3100"], apply=True)
    _write(other.sim_dir("3100") / "scripts" / "point.fs", "still in the other workspace")
    (entry,) = storage_module.sync_workspaces(main.root, "runs")
    assert "3100" in entry["sims"]["other"]
    assert entry["sims"]["without_record"] == ["2002", "3000"]


def test_p0320_sync_the_cli_passes_restore_and_include_archives(tmp_path, monkeypatch, capsys):
    # P0320-SYNC-RESTORE-OPTIN and P0320-SYNC-SKIP-ARCHIVES: the two switches
    # of the command line reach the sync, not only the library's keywords.
    rebuilds = _Rebuilds()
    monkeypatch.setattr(run_records, "rebuild", rebuilds)
    main, _ = _archived_other(tmp_path, "cliflags")
    _write(main.sim_dir("5900") / "scripts" / "point.fs", "by hand")
    base = ["sync", "all", "--workspace", str(main.root), "--apply"]
    assert matrix_cli.main([*base, "--include-archives", "--restore"]) == 0
    assert (main.sim_dir("5001") / "archive" / "old.txt").read_text("utf-8") == "1234567"
    (call,) = rebuilds.calls
    assert call["sims"] == ["5001", "5900"]
    assert "restore: 2 record(s) rebuilt, 0 sim(s) refused" in capsys.readouterr().out


# --------------------------------------------------------------------------- restore opt-in


def test_p0320_sync_restore_is_off_by_default(tmp_path, monkeypatch):
    # P0320-SYNC-RESTORE-OPTIN
    rebuilds = _Rebuilds()
    monkeypatch.setattr(run_records, "rebuild", rebuilds)
    main, _ = _orphan_pair(tmp_path, "restoreoff")
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert rebuilds.calls == []
    assert entry["restore"] == {"asked": False, "sims": [], "result": None, "error": None}
    parser = matrix_cli._build_parser()
    args = parser.parse_args(["sync", "runs"])
    assert args.restore is False


def test_p0320_sync_restore_rebuilds_the_orphans_after_the_lease_is_released(tmp_path, monkeypatch):
    # P0320-SYNC-RESTORE-OPTIN and P0320-RST-6: the rebuild takes the lease itself.
    rebuilds = _Rebuilds()
    monkeypatch.setattr(run_records, "rebuild", rebuilds)
    main, _ = _orphan_pair(tmp_path, "restoreon")
    (preview,) = storage_module.sync_workspaces(main.root, "runs", restore=True)
    assert rebuilds.calls == []
    assert preview["restore"]["asked"] is True
    assert preview["restore"]["sims"] == ["2002", "3000"]
    assert preview["restore"]["result"] is None
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True, restore=True)
    (call,) = rebuilds.calls
    assert call["root"] == main.root
    assert call["sims"] == ["2002", "3000"]
    assert call["apply"] is True
    assert call["lease_held"] is False
    assert entry["restore"]["result"]["rebuilt"] == [{"sim": "2002"}, {"sim": "3000"}]
    assert "records" not in entry["restore"]["result"]


def test_p0320_sync_restore_reports_a_refused_rebuild_and_keeps_the_sync(tmp_path, monkeypatch):
    # P0320-SYNC-RESTORE-OPTIN: a refused rebuild is said in the entry, the copy stands.
    def refuse(root, **kwargs):
        raise run_records.RunsManifestError("refused: the stand-in rebuild says no")

    monkeypatch.setattr(run_records, "rebuild", refuse)
    main, _ = _orphan_pair(tmp_path, "restorerefused")
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True, restore=True)
    assert "refused" in entry["restore"]["error"]
    assert (main.sim_dir("2002") / "scripts" / "point.fs").is_file()
    calls = storage_module.read_storage_calls(main.root)
    assert calls[-1]["restore"]["error"] == entry["restore"]["error"]


def test_p0320_sync_restore_with_another_manifest_is_refused(tmp_path):
    # P0320-SYNC-RESTORE-OPTIN: the rebuild appends to runs.json only (B1 contract).
    main, _ = _orphan_pair(tmp_path, "restorename")
    with pytest.raises(storage_module.StorageError, match="runs.json"):
        storage_module.sync_workspaces(main.root, "runs", restore=True, runs="runs-alt.json")


# --------------------------------------------------------------------------- atomic copy


def _interrupt_copies_of(monkeypatch, name: str) -> None:
    """Make every copy of a file called ``name`` write half its bytes and then fail."""
    real = shutil.copy2

    def interrupted(source, target, *args, **kwargs):
        if Path(source).name == name:
            data = Path(source).read_bytes()
            Path(target).write_bytes(data[: len(data) // 2])
            raise OSError("the network share went away mid-copy")
        return real(source, target, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", interrupted)


def test_p0320_sync_atomic_an_interrupted_copy_leaves_no_partial_target(tmp_path, monkeypatch):
    # P0320-SYNC-ATOMIC
    main, other = _sync_pair(tmp_path, "atomic")
    _write(other.sim_dir("4001") / "scripts" / "point.fs", "x" * 4000)
    _interrupt_copies_of(monkeypatch, "point.fs")
    with pytest.raises(OSError, match="mid-copy"):
        storage_module.sync_workspaces(main.root, "runs", apply=True)
    folder = main.sim_dir("4001") / "scripts"
    assert not (folder / "point.fs").exists()
    assert not folder.is_dir() or list(folder.iterdir()) == []


def test_p0320_sync_atomic_an_interrupted_overwrite_keeps_mains_copy_in_place(
    tmp_path, monkeypatch
):
    # P0320-SYNC-ATOMIC
    main, other = _sync_pair(tmp_path, "atomicover")
    _write(main.sim_dir("4002") / "scripts" / "point.fs", "main-version")
    _write(other.sim_dir("4002") / "scripts" / "point.fs", "other-version" * 100)
    _interrupt_copies_of(monkeypatch, "point.fs")
    with pytest.raises(OSError):
        storage_module.sync_workspaces(main.root, "runs", apply=True, overwrite=True)
    folder = main.sim_dir("4002") / "scripts"
    assert (folder / "point.fs").read_text("utf-8") == "main-version"
    assert [path.name for path in folder.iterdir()] == ["point.fs"]


def test_p0320_sync_atomic_a_finished_copy_leaves_no_temporary_file(tmp_path):
    # P0320-SYNC-ATOMIC
    main, other = _sync_pair(tmp_path, "atomicdone")
    _write(other.sim_dir("4003") / "scripts" / "point.fs", "whole")
    storage_module.sync_workspaces(main.root, "runs", apply=True)
    folder = main.sim_dir("4003") / "scripts"
    assert [path.name for path in folder.iterdir()] == ["point.fs"]
    assert (folder / "point.fs").read_text("utf-8") == "whole"


def test_p0320_sync_atomic_a_temporary_file_a_killed_sync_left_is_never_brought(tmp_path):
    # P0320-SYNC-ATOMIC: the half-written name of an interrupted sync stays behind.
    main, other = _sync_pair(tmp_path, "atomicleft")
    folder = other.sim_dir("4004") / "scripts"
    _write(folder / "point.fs", "whole")
    _write(folder / ".point.fs.999.pyfs-sync.tmp", "half")
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True)
    copied = {item["path"] for item in entry["files"]["copied"]}
    assert "sims/sim_4004/scripts/point.fs" in copied
    assert not any(path.endswith(".pyfs-sync.tmp") for path in copied)
    assert [path.name for path in (main.sim_dir("4004") / "scripts").iterdir()] == ["point.fs"]


# --------------------------------------------------------------------------- archives


def _archived_other(tmp_path: Path, tag: str):
    main, other = _sync_pair(tmp_path, tag)
    post = other.root / "post" / "matriz" / "sections"
    _write(post / "b.csv", "live")
    _write(post / "archive" / "20260101-000000" / "a.csv", "12345")
    _write(other.root / "post" / "matriz" / "archive" / "20260102-000000" / "p.csv", "123")
    _write(other.sim_dir("5001") / "scripts" / "point.fs", "s")
    _write(other.sim_dir("5001") / "archive" / "old.txt", "1234567")
    return main, other


def test_p0320_sync_skip_archives_by_default_and_counts_what_was_skipped(tmp_path):
    # P0320-SYNC-SKIP-ARCHIVES
    main, _ = _archived_other(tmp_path, "archskip")
    (preview,) = storage_module.sync_workspaces(main.root, "all")
    assert preview["files"]["archives_skipped"] == {"files": 3, "bytes": 15}
    assert preview["files"]["to_copy"] == 2
    (entry,) = storage_module.sync_workspaces(main.root, "all", apply=True)
    copied = {item["path"] for item in entry["files"]["copied"]}
    assert copied == {"post/matriz/sections/b.csv", "sims/sim_5001/scripts/point.fs"}
    assert not (main.root / "post" / "matriz" / "archive").exists()
    assert not (main.sim_dir("5001") / "archive").exists()


def test_p0320_sync_skip_archives_include_archives_brings_them(tmp_path, capsys):
    # P0320-SYNC-SKIP-ARCHIVES
    main, _ = _archived_other(tmp_path, "archinc")
    assert matrix_cli.main(["sync", "all", "--workspace", str(main.root)]) == 0
    assert "archive: 3 file(s), 15 B skipped" in capsys.readouterr().out
    (entry,) = storage_module.sync_workspaces(main.root, "all", apply=True, include_archives=True)
    assert entry["files"]["archives_skipped"] == {"files": 0, "bytes": 0}
    assert len(entry["files"]["copied"]) == 5
    assert (main.sim_dir("5001") / "archive" / "old.txt").read_text("utf-8") == "1234567"
    args = matrix_cli._build_parser().parse_args(["sync", "all"])
    assert args.include_archives is False


# --------------------------------------------------------------------------- matrix homes


def test_p0320_matrices_home_one_stem_in_both_homes_is_read_once_or_refused(tmp_path):
    # P0320-MATRICES-HOME and P0320-RST-1
    root = tmp_path / "ws"
    _write(root / "m.fs", "same")
    _write(root / "inputs" / "matrices" / "m.fs", "same")
    _write(root / "inputs" / "matrices" / "n.fs", "only here")
    assert matrix_by_stem(root) == {"m": root / "m.fs", "n": root / "inputs/matrices/n.fs"}
    assert find_matrix(root, "n") == root / "inputs" / "matrices" / "n.fs"
    assert find_matrix(root, "absent") is None
    _write(root / "inputs" / "matrices" / "m.fs", "different")
    for call in (lambda: matrix_by_stem(root), lambda: find_matrix(root, "m")):
        with pytest.raises(WorkspaceError) as refused:
            call()
        assert str(root / "m.fs") in str(refused.value)
        assert str(root / "inputs" / "matrices" / "m.fs") in str(refused.value)
    # A differing stem refuses only a lookup of that stem.
    assert find_matrix(root, "n") == root / "inputs" / "matrices" / "n.fs"


def _owned(tmp_path: Path, tag: str):
    main, other = _sync_pair(tmp_path, tag)
    config = main.root / storage_module.SYNC_CONFIG
    config.write_text(
        config.read_text("utf-8").replace(
            "[workspaces.main]\n", '[workspaces.main]\nmatrices = ["matriz"]\n'
        ),
        encoding="utf-8",
    )
    return main, other


def test_p0320_matrices_home_sync_reads_an_identical_pair_once_and_refuses_a_differing_one(
    tmp_path,
):
    # P0320-MATRICES-HOME and P0320-RST-1
    main, _ = _owned(tmp_path, "homesync")
    _write(main.root / "matriz.fs", "rows")
    _write(main.root / "inputs" / "matrices" / "matriz.fs", "rows")
    (entry,) = storage_module.sync_workspaces(main.root, "runs")
    assert entry["matrices"]["conflicts"] == []
    _write(main.root / "inputs" / "matrices" / "matriz.fs", "other rows")
    with pytest.raises(WorkspaceError) as refused:
        storage_module.sync_workspaces(main.root, "runs")
    assert str(main.root / "matriz.fs") in str(refused.value)
    assert str(main.root / "inputs" / "matrices" / "matriz.fs") in str(refused.value)


def test_p0320_matrices_home_sync_replaces_every_copy_main_keeps(tmp_path):
    # P0320-MATRICES-HOME: the owner's copy replaces both of main's, so they stay one.
    main, other = _sync_pair(tmp_path, "homereplace")
    config = main.root / storage_module.SYNC_CONFIG
    config.write_text(
        config.read_text("utf-8").replace(
            "[workspaces.other]\n", '[workspaces.other]\nmatrices = ["matriz"]\n'
        ),
        encoding="utf-8",
    )
    _write(main.root / "matriz.fs", "old")
    _write(main.root / "inputs" / "matrices" / "matriz.fs", "old")
    _write(other.root / "matriz.fs", "new")
    storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert (main.root / "matriz.fs").read_text("utf-8") == "new"
    assert (main.root / "inputs" / "matrices" / "matriz.fs").read_text("utf-8") == "new"
    assert find_matrix(main.root, "matriz") == main.root / "matriz.fs"


def test_p0320_matrices_home_the_census_reads_an_identical_copy_once(tmp_path):
    # P0320-MATRICES-HOME and P0320-RST-1: the plan's POL census.
    workspace = _library(tmp_path)
    planned = _matrix(workspace.root, "a.fs", [row(8101)])
    _matrix(workspace.inputs_dir / "matrices", "a.fs", [row(8101)])
    _plan_recording(workspace, planned)


def test_p0320_matrices_home_the_census_refuses_a_differing_copy_naming_both(tmp_path):
    # P0320-MATRICES-HOME and P0320-RST-1
    workspace = _library(tmp_path)
    planned = _matrix(workspace.root, "a.fs", [row(8102)])
    other = _matrix(workspace.inputs_dir / "matrices", "a.fs", [row(8102), row(8103)])
    with pytest.raises(MatrixError) as refused:
        _plan_recording(workspace, planned)
    assert str(planned) in str(refused.value)
    assert str(other) in str(refused.value)


def test_p0320_matrices_home_the_census_refuses_in_the_words_of_the_one_rule(tmp_path):
    # P0320-MATRICES-HOME and P0320-RST-1: one fact, one home. The census
    # refuses a differing pair through `matrix_by_stem`, not a second copy of it.
    workspace = _library(tmp_path)
    planned = _matrix(workspace.root, "a.fs", [row(8104)])
    _matrix(workspace.inputs_dir / "matrices", "a.fs", [row(8104), row(8105)])
    with pytest.raises(WorkspaceError) as rule:
        matrix_by_stem(workspace.root)
    with pytest.raises(MatrixError) as refused:
        _plan_recording(workspace, planned)
    assert str(rule.value) in str(refused.value)


def _post_warnings(workspace) -> list[str]:
    from tests.tier1_offline.test_post_superfile import _post

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _post(workspace)
    return [str(w.message) for w in caught if "matriz.fs" in str(w.message)]


def test_p0320_matrices_home_the_post_finds_the_matrix_in_inputs_matrices(tmp_path):
    # P0320-MATRICES-HOME: the post reads the matrix from either home.
    from pyflightstream.post.superfile import matrix_rows
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
    home = workspace.inputs_dir / "matrices"
    home.mkdir(parents=True, exist_ok=True)
    (workspace.root / "matriz.fs").replace(home / "matriz.fs")
    assert matrix_rows(workspace.root, "matriz")
    assert _post_warnings(workspace) == []


def test_p0320_matrices_home_the_post_refuses_a_differing_pair_naming_both(tmp_path):
    # P0320-MATRICES-HOME and P0320-RST-1: refused, said, never guessed (and never blocking).
    from pyflightstream.post.superfile import matrix_rows
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
    home = workspace.inputs_dir / "matrices"
    home.mkdir(parents=True, exist_ok=True)
    text = (workspace.root / "matriz.fs").read_text("utf-8")
    (home / "matriz.fs").write_text(text + "\n", encoding="utf-8")
    assert matrix_rows(workspace.root, "matriz") == {}
    (said,) = _post_warnings(workspace)
    assert str(workspace.root / "matriz.fs") in said
    assert str(home / "matriz.fs") in said
    assert "run records" in said


# --------------------------------------------------------------------------- RST-6


def test_p0320_rst6_the_sync_holds_the_runs_lease_so_a_second_writer_is_refused(
    tmp_path, monkeypatch
):
    # P0320-RST-6: the lease is held for the whole copy, so a restore (which
    # refuses on runs.json.lock, run.records) or a second sync refuses meanwhile.
    main, other = _sync_pair(tmp_path, "rst6")
    _write(other.sim_dir("6001") / "scripts" / "point.fs", "s")
    other.append_record(_record("6001", "campo/sim_6001/AL+000"))
    seen: list[bool] = []
    real = shutil.copy2

    def watching(source, target, *args, **kwargs):
        if Path(source).name == "point.fs":
            seen.append((main.root / "runs.json.lock").exists())
            with pytest.raises(storage_module.StorageError, match="runs.json.lock"):
                storage_module.sync_workspaces(main.root, "runs", apply=True)
        return real(source, target, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", watching)
    storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert seen == [True]
    assert not (main.root / "runs.json.lock").exists()


# --------------------------------------------------------------------------- --runs NAME


def test_p0320_runs_name_sync_merges_into_the_named_manifest_only(tmp_path):
    # P0320-RUNS-NAME
    main, other = _sync_pair(tmp_path, "runsname")
    main.append_record(_record("7100", "campo/sim_7100/AL+000"))
    before = main.manifest_path.read_bytes()
    (main.root / "runs-alt.json").write_text("[]\n", encoding="utf-8")
    other.append_record(_record("7101", "campo/sim_7101/AL+000"))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=True, runs="runs-alt.json")
    assert entry["runs"]["manifest"] == "runs-alt.json"
    assert entry["runs"]["added"] == ["campo/sim_7101/AL+000"]
    assert main.manifest_path.read_bytes() == before
    alt = json.loads((main.root / "runs-alt.json").read_text("utf-8"))
    assert [item["run_id"] for item in alt] == ["campo/sim_7101/AL+000"]
    assert list((main.root / ARCHIVE_DIR).glob("runs-alt-*.json"))


def test_p0320_runs_name_a_bad_name_is_refused_before_any_work(tmp_path):
    # P0320-RUNS-NAME
    main, _ = _sync_pair(tmp_path, "runsbad")
    with pytest.raises(run_records.RunsManifestError, match="not a file name"):
        storage_module.sync_workspaces(main.root, "runs", runs="sub/runs.json")
    with pytest.raises(run_records.RunsManifestError):
        storage_module.delete_sims(main.root, ["1"], runs="runs.txt")
    with pytest.raises(run_records.RunsManifestError):
        storage_module.free_space(main.root, "m001", runs="../runs.json")
    assert storage_module.read_storage_calls(main.root) == []


def test_p0320_runs_name_delete_sims_edits_the_named_manifest_only(tmp_path):
    # P0320-RUNS-NAME
    main, _ = _sync_pair(tmp_path, "runsdelete")
    _write(main.sim_dir("7200") / "datapoints" / "DP-1" / "x.txt", "a")
    main.append_record(_record("7200", "campo/sim_7200/AL+000"))
    before = main.manifest_path.read_bytes()
    alt = main.root / "runs-alt.json"
    alt.write_text(main.manifest_path.read_text("utf-8"), encoding="utf-8")
    entry = storage_module.delete_sims(main.root, ["7200"], apply=True, runs="runs-alt.json")
    assert main.manifest_path.read_bytes() == before
    rows = json.loads(alt.read_text("utf-8"))
    assert [row.get("deleted_sim") for row in rows] == ["7200"]
    assert entry["runs_archived_as"].startswith(f"{ARCHIVE_DIR}/runs-alt-")
    assert (main.root / entry["runs_archived_as"]).is_file()
    assert not main.sim_dir("7200").exists()


def test_p0320_runs_name_delete_sims_regenerate_with_another_manifest_is_refused(tmp_path):
    # P0320-RUNS-NAME: the post of another manifest is `post --runs`, not this command.
    main, _ = _sync_pair(tmp_path, "runsregen")
    with pytest.raises(storage_module.StorageError, match="regenerate"):
        storage_module.delete_sims(
            main.root, ["1"], matrix_products="regenerate", apply=True, runs="runs-alt.json"
        )


def test_p0320_runs_name_free_space_protects_what_the_named_manifest_names(tmp_path):
    # P0320-RUNS-NAME: the named manifest adds protection; runs.json keeps its own.
    main, _ = _sync_pair(tmp_path, "runsfree")
    folder = main.sim_dir("7300") / "datapoints" / "DP-1"
    _write(folder / "rebuilt.vtk", "named by the rebuilt manifest")
    _write(folder / "recorded.vtk", "named by runs.json")
    _write(folder / "junk.vtk", "named by nobody")
    main.append_record(
        _record("7300", "campo/sim_7300/AL+000", outputs=["datapoints/DP-1/recorded.vtk"])
    )
    alt = [
        {
            "run_id": "campo/sim_7300/AL+000",
            "sim_id": "7300",
            "outputs": ["datapoints/DP-1/rebuilt.vtk"],
        }
    ]
    (main.root / "runs-alt.json").write_text(json.dumps(alt), encoding="utf-8")
    _write_recipe(main, "m001", '[[delete_extensions]]\nextensions = [".vtk"]\n')
    storage_module.free_space(main.root, "m001", apply=True, runs="runs-alt.json")
    assert (folder / "rebuilt.vtk").exists()
    assert (folder / "recorded.vtk").exists()
    assert not (folder / "junk.vtk").exists()


def test_p0320_runs_name_the_cli_passes_the_name_to_sync_and_storage(tmp_path, monkeypatch):
    # P0320-RUNS-NAME: sync, free-space and delete-sims no longer refuse another name.
    seen: dict[str, object] = {}

    def spy(name):
        def call(*args, **kwargs):
            seen[name] = kwargs.get("runs")
            if name == "sync_workspaces":
                return []
            return {
                "applied": False,
                "recipe": "m001",
                "steps": [],
                "sims": [],
                "post": {},
                "stale": [],
            }

        return call

    for name in ("sync_workspaces", "free_space", "delete_sims"):
        monkeypatch.setattr(storage_module, name, spy(name))
    base = ["--workspace", str(tmp_path), "--runs", "runs-alt.json"]
    assert matrix_cli.main(["sync", "runs", *base]) == 0
    assert matrix_cli.main(["free-space", "m001", *base]) == 0
    assert matrix_cli.main(["delete-sims", "1", *base]) == 0
    assert seen == {
        "sync_workspaces": "runs-alt.json",
        "free_space": "runs-alt.json",
        "delete_sims": "runs-alt.json",
    }


# --------------------------------------------------------------------------- progress


def test_p0320_sync_reports_its_three_stages_to_the_progress(tmp_path, monkeypatch):
    # The hook of package A: sync's hash, merge and copy stages, in that order.
    import contextlib

    stages: list[tuple[str, int | None]] = []

    @contextlib.contextmanager
    def recording(name, *, total_files=None, total_bytes=None):
        stages.append((name, total_files))

        class _Stage:
            def advance(self, files=0, bytes=0, current=None):
                return None

        yield _Stage()

    monkeypatch.setattr(storage_module, "stage_progress", recording)
    main, other = _orphan_pair(tmp_path, "progress")
    storage_module.sync_workspaces(main.root, "runs", apply=True)
    assert [name for name, _ in stages] == ["sync hash", "sync merge", "sync copy"]
    assert stages[0][1] == 3


# --------------------------------------------------------------------------- B1 and B2 together
def test_p0320_merge_b1_b2_restore_reaches_the_real_rebuild_and_keeps_its_refusal(tmp_path):
    # P0320-SYNC-RESTORE-OPTIN against B1's real run.records.rebuild, not the
    # stand-in: the call shape B2 makes is one the rebuild accepts, and the
    # rebuild's refusal is caught and written in the entry, not raised.
    root = tmp_path / "ws"
    (root / "sims" / "sim_1").mkdir(parents=True)
    outcome = storage_module._restore_orphans(root, ["1"])
    assert outcome["asked"] is True
    assert outcome["sims"] == ["1"]
    assert outcome["result"] is None
    assert "rebuild" in outcome["error"]
    # 0.33.0 (AD-09): the rebuild is reached through the registry, whose own
    # "nothing is registered" error also names a rebuild; the refusal read
    # here must be the real rebuild's.
    assert not outcome["error"].startswith("no records rebuild is registered")


def test_p0320_merge_b1_b2_rebuild_and_the_two_homes_agree_on_the_path(tmp_path):
    # P0320-MATRICES-HOME and B1's rebuild: an identical pair is read once,
    # from the root, by both; a differing pair names both paths in both. FR-310
    # changed this expectation: the rebuild uses the workspace's one lookup and
    # REFUSES the differing pair, naming both, where until 0.32.0 it left that
    # stem out with a note. FR-224 lists sync, the census and the post as the
    # commands that refuse; FR-310 joins the rebuild to them.
    requirement = "FR-310"
    root = tmp_path / "ws"
    _write(root / "m.fs", "same")
    _write(root / "inputs" / "matrices" / "m.fs", "same")
    _write(root / "inputs" / "matrices" / "n.fs", "only here")
    chosen = _matrices(root, None)
    assert chosen == [path.resolve() for path in matrix_by_stem(root).values()]
    _write(root / "inputs" / "matrices" / "m.fs", "different")
    with pytest.raises(WorkspaceError):
        matrix_by_stem(root)
    with pytest.raises(WorkspaceError) as refused:
        _matrices(root, None)
    assert "m.fs" in str(refused.value) and "matrices" in str(refused.value), requirement
