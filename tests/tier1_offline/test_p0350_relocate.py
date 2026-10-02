"""FR-367: a batch's points copied and moved home without crossing the inputs link (0.35.0).

The ``inputs`` entry of a simulation is a directory link (a junction on
Windows, a symlink elsewhere) to the workspace's staged inputs. A copy through
it would duplicate every geometry and a removal through it would delete them,
so the test puts a sentinel behind it and checks it is still there, alone.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pyflightstream.workspace._batch_relocate import copy_point, move_sim, relink_inputs


def _make_link(target: Path, link: Path) -> None:
    """A directory link the way the workspace makes one: a junction on Windows."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _is_link(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _listing(root: Path) -> dict[str, tuple[int, int]]:
    """Every file and link under ``root`` with its size and mtime, never through a link."""
    seen: dict[str, tuple[int, int]] = {}
    for path in sorted(root.iterdir()):
        info = os.lstat(path)
        name = path.relative_to(root).as_posix()
        if _is_link(path) or not path.is_dir():
            seen[name] = (info.st_size, info.st_mtime_ns)
        else:
            seen.update({f"{name}/{k}": v for k, v in _listing(path).items()})
    return seen


def _batch(tmp_path: Path) -> tuple[Path, Path, Path]:
    staged = tmp_path / "staged_inputs"
    staged.mkdir()
    (staged / "SENTINEL.fsm").write_bytes(b"geometry")
    batch_sim = tmp_path / "sims" / "batch" / "mtx_b1" / "sim_2006"
    for point in ("DP-AL+000", "DP-AL+020"):
        folder = batch_sim / "datapoints" / point
        folder.mkdir(parents=True)
        (folder / "loads.txt").write_bytes(f"loads {point}".encode())
    (batch_sim / "scripts").mkdir()
    (batch_sim / "scripts" / "P2006-AL+000.txt").write_bytes(b"script")
    (batch_sim / "profiles").mkdir()
    (batch_sim / "profiles" / "probes.txt").write_bytes(b"probes")
    _make_link(staged, batch_sim / "inputs")
    return staged, batch_sim, tmp_path / "sims" / "sim_2006"


def test_p0350_relocate_never_crosses_a_link(tmp_path):
    """P0350-COLLECT-COPY-MOVE (FR-367): copy, relink and move leave the link's target alone."""
    requirement = "FR-367"
    staged, batch_sim, sim = _batch(tmp_path)
    before_batch = _listing(batch_sim)
    before_staged = _listing(staged)

    copied = copy_point(batch_sim, sim, "DP-AL+000")
    relink_inputs(batch_sim, sim)
    assert _listing(batch_sim) == before_batch, "a copy wrote under the batch folder"
    assert copied.copied == (
        "datapoints/DP-AL+000/loads.txt",
        "profiles/probes.txt",
        "scripts/P2006-AL+000.txt",
    ), requirement
    assert not (sim / "datapoints" / "DP-AL+020").exists(), "only the settled point is copied"
    assert _is_link(sim / "inputs"), requirement
    assert (sim / "inputs").resolve() == staged.resolve(), requirement
    assert "inputs" in _listing(sim) and "inputs/SENTINEL.fsm" not in _listing(sim)
    # Twice is the same: nothing is copied again, nothing replaced.
    again = copy_point(batch_sim, sim, "DP-AL+000")
    relink_inputs(batch_sim, sim)
    assert again.copied == () and again.replaced == () and len(again.kept) == 3

    # The solver rewrites a file after its copy, and the collect slices a log
    # into the copy only; then the job ends and everything is moved home.
    (batch_sim / "datapoints" / "DP-AL+000" / "loads.txt").write_bytes(b"loads final")
    (sim / "datapoints" / "DP-AL+000" / "P2006_log.txt").write_bytes(b"sliced")
    moved = move_sim(batch_sim, sim)
    assert moved.replaced == ("datapoints/DP-AL+000/loads.txt",), requirement
    assert moved.copied == ("datapoints/DP-AL+020/loads.txt",), requirement
    assert set(moved.kept) == {"profiles/probes.txt", "scripts/P2006-AL+000.txt"}
    assert not batch_sim.exists(), "the batch's sim folder is removed once empty"
    assert batch_sim.parent.is_dir(), "the job's own folder stays"
    assert (sim / "datapoints" / "DP-AL+000" / "loads.txt").read_bytes() == b"loads final"
    assert (sim / "datapoints" / "DP-AL+000" / "P2006_log.txt").read_bytes() == b"sliced"
    assert _is_link(sim / "inputs") and (sim / "inputs").resolve() == staged.resolve()
    assert _listing(staged) == before_staged, "the link's target was touched"
    assert (staged / "SENTINEL.fsm").read_bytes() == b"geometry", requirement


def test_p0350_relocate_the_control_a_copy_through_the_link_is_seen(tmp_path):
    """The control: the listing does see a file written behind the copy's back."""
    staged, batch_sim, sim = _batch(tmp_path)
    before = _listing(batch_sim)
    copy_point(batch_sim, sim, "DP-AL+000")
    (batch_sim / "scripts" / "planted.txt").write_bytes(b"x")
    assert _listing(batch_sim) != before
    assert _listing(staged) == {"SENTINEL.fsm": _listing(staged)["SENTINEL.fsm"]}


def test_p0350_relocate_replaces_the_plans_empty_inputs_folder(tmp_path):
    """P0350-COLLECT-COPY-MOVE (FR-367): the empty ``inputs`` the plan allocates becomes the link.

    The plan creates ``sims/sim_<id>/inputs`` empty before any run, so a batched
    sim brought home always meets one; a folder holding a file stays refused.
    """
    import pytest

    from pyflightstream.workspace import WorkspaceError

    staged, batch_sim, sim = _batch(tmp_path)
    (sim / "inputs").mkdir(parents=True)
    relink_inputs(batch_sim, sim)
    assert _is_link(sim / "inputs") and (sim / "inputs").resolve() == staged.resolve()
    assert (staged / "SENTINEL.fsm").read_bytes() == b"geometry"

    other = tmp_path / "other"
    other.mkdir()
    staged2, batch_sim2, sim2 = _batch(other)
    (sim2 / "inputs").mkdir(parents=True)
    (sim2 / "inputs" / "kept.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        relink_inputs(batch_sim2, sim2)
    assert (sim2 / "inputs" / "kept.txt").read_text(encoding="utf-8") == "mine"
