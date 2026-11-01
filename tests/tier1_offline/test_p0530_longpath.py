"""Tier 1 offline: workspace file operations past the 260 characters of Windows (0.53.0).

A datapoint whose earlier attempt was moved into ``archive/<stamp>/`` holds files whose paths
pass 260 characters. ``free-space`` and ``sync`` handed such a path to the operating system as
it was and stopped the whole command at the first one (``WinError 3``). They now hand every file
operation the extended-length spelling, so the file is reached, and a file that still fails is
warned and skipped while the rest of the command completes.

The trees are real ``tmp_path`` trees: on Windows the paths really pass the limit, so these tests
fail there without the spelling; elsewhere the limit does not exist and they hold the same
behaviour. The spelling itself is read for Windows through the helper's ``windows`` argument.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream._textio import extended_length, long_path
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.storage import PRUNE_MODE, free_space, sync_workspaces

LIMIT = 260
POINT = "DP-" + "M144RE438MU17890A3403T2882PS101325AL+000BE+000RPM00447" * 2
STAMP = "20261031-144049"


def _ws(tmp_path: Path, name: str) -> CampaignWorkspace:
    root = tmp_path / name
    workspace = CampaignWorkspace(root)
    workspace.init(root)
    return workspace


def _long_folder(workspace: CampaignWorkspace, sim: str = "9753") -> Path:
    return workspace.sim_dir(sim) / "datapoints" / POINT / "archive" / STAMP


def _put(path: Path, text: str = "x") -> None:
    long_path(path.parent).mkdir(parents=True, exist_ok=True)
    long_path(path).write_text(text, encoding="utf-8")


def _steps(workspace: CampaignWorkspace, steps=(1, 2, 3)) -> list[Path]:
    folder = _long_folder(workspace)
    paths = [folder / f"P9753-{POINT}_iteration={n}.txt" for n in steps]
    for path in paths:
        _put(path, "payload")
    assert max(len(str(p)) for p in paths) > LIMIT, "the fixture must pass the limit"
    return paths


def _recipe(workspace: CampaignWorkspace, text: str) -> str:
    path = workspace.root / storage_module.MANAGEMENT_DIR / "m1.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "m1"


def _present(path: Path) -> bool:
    return long_path(path).is_file()


@pytest.mark.requirement("FR-3418")
def test_p0530_the_extended_spelling_is_read_for_windows_and_left_alone_elsewhere():
    assert extended_length("C:/work/a", windows=True) == "\\\\?\\C:\\work\\a"
    assert extended_length("\\\\host\\share\\a", windows=True) == "\\\\?\\UNC\\host\\share\\a"
    assert extended_length("\\\\?\\C:\\work\\a", windows=True) == "\\\\?\\C:\\work\\a"
    assert extended_length("C:/work/a", windows=False) == "C:/work/a"


@pytest.mark.requirement("FR-3418")
def test_p0530_prune_step_exports_reaches_a_file_past_the_windows_limit(tmp_path):
    workspace = _ws(tmp_path, "camp")
    paths = _steps(workspace)
    entry = free_space(
        workspace.root, _recipe(workspace, f'[[{PRUNE_MODE}]]\nsims = "all"\n'), apply=True
    )
    assert [_present(p) for p in paths] == [False, False, True]
    (point,) = entry["steps"][0]["points"]
    assert point["deleted_steps"] == [1, 2] and "skipped" not in point
    assert entry["bytes_freed"] == 2 * len("payload")


@pytest.mark.requirement("FR-3418")
def test_p0530_delete_extensions_reaches_a_file_past_the_windows_limit(tmp_path):
    workspace = _ws(tmp_path, "camp")
    paths = _steps(workspace, steps=(1,))
    recipe = _recipe(workspace, '[[delete_extensions]]\nsims = "all"\nextensions = [".txt"]\n')
    entry = free_space(workspace.root, recipe, apply=True)
    assert not _present(paths[0])
    assert entry["bytes_freed"] == len("payload")


@pytest.mark.requirement("FR-3418")
def test_p0530_one_file_that_cannot_be_deleted_is_warned_and_skipped(tmp_path, monkeypatch):
    workspace = _ws(tmp_path, "camp")
    paths = _steps(workspace, steps=(1, 2, 3, 4))
    real_unlink = Path.unlink

    def refuse_step_two(self, *args, **kwargs):
        if "_iteration=2." in self.name:
            raise PermissionError(13, "in use", self.name)
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse_step_two)
    with pytest.warns(PyflightstreamWarning, match=r"_iteration=2\.txt.*not deleted, skipped"):
        entry = free_space(
            workspace.root, _recipe(workspace, f'[[{PRUNE_MODE}]]\nsims = "all"\n'), apply=True
        )
    assert [_present(p) for p in paths] == [False, True, False, True]
    (point,) = entry["steps"][0]["points"]
    assert point["deleted_steps"] == [1, 3]
    assert len(point["skipped"]) == 1 and "_iteration=2." in point["skipped"][0]
    assert entry["bytes_freed"] == 2 * len("payload")
    assert "interrupted" not in storage_module.read_storage_calls(workspace.root)[-1]


def _sync_pair(tmp_path: Path) -> tuple[CampaignWorkspace, CampaignWorkspace]:
    main = _ws(tmp_path, "main")
    other = _ws(tmp_path, "other")
    config = main.root / storage_module.SYNC_CONFIG
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        'main = "main"\n\n[workspaces.main]\n'
        f"path = '{main.root.resolve().as_posix()}'\n\n[workspaces.other]\n"
        f"path = '{other.root.resolve().as_posix()}'\n",
        encoding="utf-8",
    )
    return main, other


@pytest.mark.requirement("FR-3418")
def test_p0530_sync_copies_to_a_destination_past_the_windows_limit(tmp_path):
    main, other = _sync_pair(tmp_path)
    paths = _steps(other, steps=(1, 2))
    (entry,) = sync_workspaces(main.root, "all", apply=True, include_archives=True)
    for path in paths:
        copied = main.root / path.relative_to(other.root)
        assert len(str(copied)) > LIMIT and _present(copied)
        assert long_path(copied).read_text(encoding="utf-8") == "payload"
    assert len(entry["files"]["copied"]) >= 2 and "skipped" not in entry["files"]


@pytest.mark.requirement("FR-3418")
def test_p0530_a_file_the_sync_cannot_copy_is_warned_and_the_rest_completes(tmp_path, monkeypatch):
    main, other = _sync_pair(tmp_path)
    paths = _steps(other, steps=(1, 2, 3))
    real_replace = storage_module.os.replace

    def refuse_step_two(source, target, *args, **kwargs):
        if "_iteration=2." in str(target):
            raise PermissionError(13, "in use", str(target))
        return real_replace(source, target, *args, **kwargs)

    monkeypatch.setattr(storage_module.os, "replace", refuse_step_two)
    with pytest.warns(PyflightstreamWarning, match=r"_iteration=2\.txt.*not copied, skipped"):
        (entry,) = sync_workspaces(main.root, "all", apply=True, include_archives=True)
    landed = [_present(main.root / p.relative_to(other.root)) for p in paths]
    assert landed == [True, False, True]
    assert len(entry["files"]["skipped"]) == 1 and "_iteration=2." in entry["files"]["skipped"][0]
    assert "interrupted" not in entry
