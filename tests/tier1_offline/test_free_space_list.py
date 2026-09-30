"""Tier 1 offline: ``pyfs-matrix free-space --list`` prints every path a step touches.

The data is the entry ``storage.free_space`` returns (one home); the CLI only
prints it. A synthetic workspace carries a recipe of all four tables.
"""
# The evidence line of this requirement cites this module (docs/srs/functional-requirements.md):
# FR-305.

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream.run import cli as matrix_cli
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.naming import ARCHIVE_DIR

RECIPE = """
[[prune_step_exports]]
sims = ["5001"]

[[compact_sims]]
sims = ["5002"]

[[delete_extensions]]
extensions = [".vtk"]

[[post_archives]]
action = "delete"
keep_latest = 1
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _record(sim: str, outputs: list[str] | None = None) -> RunRecord:
    return RunRecord(
        run_id=f"camp/sim_{sim}/AL+000",
        sim_id=sim,
        matrix_stem="matriz",
        fs_version_requested="26.123",
        package_version="0.33.0",
        script_sha256="c" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
        outputs=outputs or [],
        script_path=None,
        inputs_sha256={},
    )


def _workspace(tmp_path: Path, name: str = "camp") -> CampaignWorkspace:
    root = tmp_path / name
    workspace = CampaignWorkspace(root)
    workspace.init(root)
    point = workspace.sim_dir("5001") / "datapoints" / "DP-1"
    for step in (1, 2, 3):
        _write(point / f"loads_iteration={step}.txt", "x" * 100 * step)
    workspace.append_record(_record("5001"))
    _write(workspace.sim_dir("5002") / "datapoints" / "DP-1" / "a.txt", "y" * 2000)
    workspace.append_record(_record("5002"))
    sim = workspace.sim_dir("5003") / "datapoints" / "DP-1"
    _write(sim / "junk.vtk", "j" * 50)
    _write(sim / "loads.vtk", "k" * 60)
    workspace.append_record(_record("5003", outputs=["datapoints/DP-1/loads.vtk"]))
    archive_root = workspace.root / "post" / "matriz" / ARCHIVE_DIR
    for stamp in ("20260101-000000", "20260102-000000"):
        _write(archive_root / stamp / "old.csv", "d" * 40)
    _write(workspace.root / storage_module.MANAGEMENT_DIR / "m001.toml", RECIPE)
    return workspace


def _run(workspace: CampaignWorkspace, capsys, *extra: str) -> str:
    capsys.readouterr()
    code = matrix_cli.main(["free-space", "m001", "--workspace", str(workspace.root), *extra])
    assert code == 0
    return capsys.readouterr().out


def _tree(root: Path) -> dict[str, int]:
    return {
        p.relative_to(root).as_posix(): p.stat().st_size
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.relative_to(root).parts[0] in ("sims", "post", "inputs")
    }


def _checks(out: str) -> list[str]:
    """The expectations of the preview list; each message names the branch it proves."""
    base = "sims/sim_5001/datapoints/DP-1/loads_iteration="
    failures = []
    if f"{base}1.txt  100 B  would delete (step 1)" not in out:
        failures.append("prune: a deleted per-step file")
    if f"{base}3.txt  kept (last step 3)" not in out:
        failures.append("prune: the kept last step")
    if not re.search(r"sims/sim_5002  .+  would be compacted", out):
        failures.append("compact: a sim with its folder size")
    if not re.search(r"junk\.vtk  50 B  would delete", out):
        failures.append("extensions: a deleted file")
    if not re.search(r"loads\.vtk  kept \(a later post needs it\)", out):
        failures.append("extensions: a kept file and why")
    if "post/matriz/archive/20260101-000000  40 B  would delete" not in out:
        failures.append("archives: a folder")
    return failures


def test_list_shows_every_path_of_the_four_tables_in_a_preview_fr_305(tmp_path, capsys):
    # Verifies FR-305.
    workspace = _workspace(tmp_path)
    before = _tree(workspace.root)
    out = _run(workspace, capsys, "--list")
    assert _checks(out) == [], out
    assert "20260102-000000" not in out  # keep_latest keeps the newest stamp
    assert "preview only" in out
    assert _tree(workspace.root) == before


def test_list_after_apply_says_what_was_done_fr_305(tmp_path, capsys):
    # Verifies FR-305.
    workspace = _workspace(tmp_path)
    out = _run(workspace, capsys, "--apply", "--list")
    assert re.search(r"junk\.vtk  50 B  deleted", out), out
    assert re.search(r"sims/sim_5002  .+  compacted into sims/sim_5002\.zip", out), out
    assert re.search(r"20260101-000000  40 B  deleted", out), out
    assert not (workspace.root / "sims/sim_5003/datapoints/DP-1/junk.vtk").exists()


def test_the_output_without_list_is_the_old_output_byte_for_byte_fr_305(tmp_path, capsys):
    # Verifies FR-305.
    workspace = _workspace(tmp_path)
    out = _run(workspace, capsys)
    assert out == (
        "free-space inputs/management/m001.toml (preview)\n"
        "  prune_step_exports: 1 point(s), 2 per-step file(s), 300 B; the last step of each "
        "export kept\n"
        "    sims/sim_5001/datapoints/DP-1: steps 1 to 2 (2 step(s))\n"
        "  compact_sims: 1 sim(s) 5002\n"
        "  delete_extensions .vtk: 1 file(s), 50 B; 1 kept (a later post needs them)\n"
        "  post_archives (delete): 1 folder(s), 40 B\n"
        "preview only: run again with --apply to change files\n"
    )


def test_dropping_one_list_branch_turns_the_check_red_fr_305(tmp_path, capsys, monkeypatch):
    # Verifies FR-305.
    workspace = _workspace(tmp_path)
    real = matrix_cli._print_free_space_paths

    def mutant(step, applied):
        if step["mode"] != "post_archives":
            real(step, applied)

    monkeypatch.setattr(matrix_cli, "_print_free_space_paths", mutant)
    out = _run(workspace, capsys, "--list")
    assert _checks(out) == ["archives: a folder"]
    with pytest.raises(AssertionError):
        assert _checks(out) == []
