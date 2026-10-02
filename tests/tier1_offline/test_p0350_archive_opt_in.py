"""Tier 1: the post writes no archive folder unless asked (P0350-ARCHIVE-OPT-IN, FR-397).

Since 0.35.0 a rebuild overwrites the products in place; ``--archive`` on
``pyfs-matrix post`` and ``archive=True`` on ``write_campaign_products`` move
what a rebuild replaces into ``archive/<stamp>/`` as 0.34.0 did.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pyflightstream.post.products import PRODUCT_ARCHIVE_DIR, write_campaign_products
from pyflightstream.run.cli import main
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_post_products import LOADS


def _workspace(tmp_path: Path) -> CampaignWorkspace:
    """One converged steady record whose loads export is on disk."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    raw = workspace.sim_dir("7001") / "outputs"
    raw.mkdir(parents=True)
    (raw / "AL-020.txt").write_text(LOADS, encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_7001/AL-020",
            point_name="AL-020",
            sweep_name="AL-020",
            sim_id="7001",
            point={"alpha": -2.0},
            fs_version_requested="26.123",
            package_version="0.35.0.dev0",
            script_sha256="",
            raw_flag=False,
            status=RunStatus.CONVERGED,
            outputs=["outputs/AL-020.txt"],
            mach=0.2,
            reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0},
        )
    )
    return workspace


def _archive_folders(root: Path) -> list[Path]:
    return sorted(p for p in (root / "post").rglob(PRODUCT_ARCHIVE_DIR) if p.is_dir())


def _digests(root: Path) -> dict[str, str]:
    """Every product's bytes by relative name, the logs and the stamp-bearing files left out."""
    skip = {"post.log", "post.log.json", "products.json"}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and PRODUCT_ARCHIVE_DIR not in path.parts and path.name not in skip
    }


def test_a_rebuild_with_no_option_writes_no_archive_folder(tmp_path):
    """P0350-ARCHIVE-OPT-IN (FR-397): the default rebuild overwrites in place."""
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace)
    first = _digests(workspace.root / "post")
    assert first, "the first post wrote no product, so the test proves nothing"

    write_campaign_products(workspace, overwrite=True)

    assert _archive_folders(workspace.root) == []
    assert _digests(workspace.root / "post") == first


def test_a_rebuild_with_archive_true_archives_as_0340_did(tmp_path):
    """P0350-ARCHIVE-OPT-IN (FR-397), the control: archive=True moves the files aside."""
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace)
    first = _digests(workspace.root / "post")

    write_campaign_products(workspace, overwrite=True, archive=True)

    folders = _archive_folders(workspace.root)
    assert folders, "archive=True wrote no archive folder"
    kept = {p.name for folder in folders for p in folder.rglob("*") if p.is_file()}
    assert {"post.log", "products.json"} <= kept
    assert _digests(workspace.root / "post") == first, "the products differ with the archive"


def test_the_post_command_archives_only_with_the_archive_option(tmp_path, capsys):
    """P0350-ARCHIVE-OPT-IN (FR-397): `pyfs-matrix post` and `post --archive`."""
    workspace = _workspace(tmp_path)
    root = str(workspace.root)
    assert main(["post", "--workspace", root]) == 0
    assert main(["post", "--workspace", root]) == 0
    assert _archive_folders(workspace.root) == []

    assert main(["post", "--workspace", root, "--archive"]) == 0
    assert _archive_folders(workspace.root)
    capsys.readouterr()


def test_archive_and_force_overwrite_together_are_refused(tmp_path, capsys):
    """P0350-ARCHIVE-OPT-IN (FR-397): one keeps a copy and the other keeps none."""
    workspace = _workspace(tmp_path)

    with pytest.raises(SystemExit) as stopped:
        main(["post", "--workspace", str(workspace.root), "--archive", "--force-overwrite"])

    assert stopped.value.code == 2
    assert "--archive" in capsys.readouterr().err
