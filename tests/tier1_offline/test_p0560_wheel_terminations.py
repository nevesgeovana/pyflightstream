"""P0560-WHEEL: wake terminations carried by sector-to-wheel and marked across a merge.

Pipeline role: tier-1 oracle of PFS-2195 (FR-3720, FR-3721) and PFS-2187.08 (FR-3722, FR-3723).
The sector is the synthetic one of ``test_p0540_wheel``, with its blade base and nacelle base
merged into their parents and one explicit wake-termination node at the tip end of a rim. The
node expected in the wheel is that tip point turned by each copy's angle, computed here, not
read from the code under test.
"""

from __future__ import annotations

import json
import tomllib
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, NotApplicableWarning
from pyflightstream.workspace import plan_mark_boundaries
from pyflightstream.workspace._wheel import sector_to_wheel
from tests.tier1_offline.test_p0540_wheel import (
    Built,
    _write_points,
    build_sector,
    read_wheel,
    turn,
)
from tests.tier1_offline.test_p0540_wheel_fsm import build_saved_sector

COPIES = 6
RIM = '[trailing_edges.TE_a]\nfile = "sector.TE_a.te.txt"\ntype = "STANDARD"\n'
OTHER_RIM = '[trailing_edges.TE_b]\nfile = "sector.TE_b.te.txt"\ntype = "STANDARD"\n'


def terminated_sector(
    folder: Path, build: str = "26.125", *, auto: bool = False
) -> tuple[Built, np.ndarray]:
    """Write the merged sector with one explicit termination node; return it and that node.

    With ``auto`` the other rim declares autodetected terminations as well.
    """
    built = build_sector(folder, copies=COPIES, separate_base=True)
    _, tip = built.rims["TE_a"][-1]
    point = built.verts[tip]
    _write_points(folder / "sector.TE_a.wake.te.txt", [point])
    sidecar = folder / "sector.obj.boundaries.toml"
    text = sidecar.read_text(encoding="utf-8")
    assert text.count(RIM) == 1 and text.count('fs_build = "26.124"') == 1
    text = text.replace(RIM, RIM + 'wake_termination_nodes = "sector.TE_a.wake.te.txt"\n')
    if auto:
        assert text.count(OTHER_RIM) == 1
        text = text.replace(OTHER_RIM, OTHER_RIM + 'wake_termination_nodes = "auto"\n')
    sidecar.write_text(text.replace('"26.124"', f'"{build}"'), encoding="utf-8")
    return built, point


def _terminations(folder: Path) -> dict[str, str]:
    """Return the wheel's ``wake_termination_nodes`` by trailing-edge label."""
    text = (folder / "wheel.obj.boundaries.toml").read_text(encoding="utf-8")
    entries = tomllib.loads(text).get("trailing_edges", {})
    return {
        label: entry["wake_termination_nodes"]
        for label, entry in entries.items()
        if isinstance(entry, dict) and "wake_termination_nodes" in entry
    }


def _record(folder: Path, stem: str = "wheel") -> dict:
    return json.loads((folder / f"{stem}.wheel.json").read_text(encoding="utf-8"))


def wheel_of(built: Built, out: Path, **options):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sector_to_wheel(
            built.obj, copies=COPIES, blades=["Blade1"], axis="x", out=out, **options
        )


@pytest.mark.requirement("FR-3720")
@pytest.mark.parametrize("build", ["26.124", "26.125"])
def test_p0560_a_wheel_with_explicit_terminations_across_a_merge_passes_the_preview(
    tmp_path: Path, build: str
) -> None:
    built, point = terminated_sector(tmp_path, build)
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    side = (tmp_path / "wheel.obj.boundaries.toml").read_text(encoding="utf-8")
    assert side.count("wake_termination_nodes") == COPIES and side.count("merge_into") == 7

    plan = plan_mark_boundaries(wheel)

    verts, _ = read_wheel(wheel)
    labels = [f"TE_a_{k + 1}" for k in range(COPIES)]
    assert sorted(plan.nodes) == labels
    for k, label in enumerate(labels):
        expected = turn(point[None, :], np.array([1.0, 0.0, 0.0]), np.zeros(3), 60.0 * k)[0]
        (node,) = plan.nodes[label]
        assert np.allclose(verts[node - 1], expected, atol=1e-9), label
    lines = plan.script.splitlines()
    marks = [i for i, line in enumerate(lines) if line == "MARK_WAKE_TERMINATION_NODES"]
    combines = [i for i, line in enumerate(lines) if line.startswith("SURFACE_COMBINE")]
    assert len(marks) == COPIES and len(combines) == 7
    assert max(marks) < min(combines)


@pytest.mark.requirement("FR-3721")
@pytest.mark.parametrize("build", ["26.126", "26.127"])
def test_p0560_explicit_terminations_across_a_merge_on_an_unmeasured_build_name_the_evidence(
    tmp_path: Path, build: str
) -> None:
    built, _ = terminated_sector(tmp_path, build)
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    with pytest.raises(InputArtifactError) as caught:
        plan_mark_boundaries(wheel)
    words = str(caught.value)
    assert build in words and "26.124" in words and "26.125" in words
    assert "CMP-26125_2026-10-26_marking" in words


@pytest.mark.requirement("FR-3722")
def test_p0560_the_obj_route_carries_the_sector_s_terminations_by_default_and_records_it(
    tmp_path: Path,
) -> None:
    built, point = terminated_sector(tmp_path, auto=True)
    wheel_of(built, tmp_path / "wheel.obj")

    carried = _terminations(tmp_path)
    explicit = {f"TE_a_{k + 1}": k for k in range(COPIES)}
    autos = {f"TE_b_{k + 1}" for k in range(COPIES)}
    assert set(carried) == set(explicit) | autos
    assert all(carried[label] == "auto" for label in autos)
    for label, k in explicit.items():
        rows = (tmp_path / carried[label]).read_text(encoding="utf-8").split()
        assert rows[0] == "METER" and len(rows) == 2, label
        got = np.array([float(c) for c in rows[1].split(",")])
        expected = turn(point[None, :], np.array([1.0, 0.0, 0.0]), np.zeros(3), 60.0 * k)[0]
        assert np.allclose(got, expected, atol=1e-9), label
    assert _record(tmp_path)["wake_terminations"] == "carried"


@pytest.mark.requirement("FR-3723")
def test_p0560_wake_terminations_false_drops_every_termination_and_the_record_says_so(
    tmp_path: Path,
) -> None:
    built, _ = terminated_sector(tmp_path, auto=True)
    wheel_of(built, tmp_path / "wheel.obj", wake_terminations=False)

    assert _terminations(tmp_path) == {}
    assert not list(tmp_path.glob("wheel.*.wake.te.txt"))
    record = _record(tmp_path)
    assert record["wake_terminations"] == "dropped"
    assert not [name for name in record["points_files"] if ".wake." in name]
    side = (tmp_path / "wheel.obj.boundaries.toml").read_text(encoding="utf-8")
    assert side.count("[trailing_edges.TE_a_") == COPIES and side.count("merge_into") == 7


@pytest.mark.requirement("FR-3723")
def test_p0560_the_command_line_drops_them_with_no_wake_terminations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pyflightstream.workspace.cli import main as workspace_main

    built, _ = terminated_sector(tmp_path)
    argv = ["geometry", "sector-to-wheel", str(built.obj), "--copies", str(COPIES)]
    argv += ["--axis", "x", "--blades", "Blade1", "--out", str(tmp_path / "wheel.obj")]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert workspace_main([*argv, "--no-wake-terminations"]) == 0
    capsys.readouterr()
    assert _terminations(tmp_path) == {}
    assert _record(tmp_path)["wake_terminations"] == "dropped"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert workspace_main([*argv, "--overwrite"]) == 0
    assert len(_terminations(tmp_path)) == COPIES
    assert _record(tmp_path)["wake_terminations"] == "carried"


@pytest.mark.requirement("FR-3723")
def test_p0560_the_saved_route_warns_that_the_switch_does_not_apply_and_carries_them(
    tmp_path: Path,
) -> None:
    sector = build_saved_sector(tmp_path, build_sector(tmp_path, copies=COPIES))
    with pytest.warns(NotApplicableWarning, match="wake_terminations") as caught:
        result = sector_to_wheel(
            sector,
            copies=COPIES,
            blades=["Blade1"],
            axis="x",
            out=tmp_path / "saved.fsm",
            wake_terminations=False,
        )
    assert result.written
    assert any("--no-wake-terminations" in str(item.message) for item in caught)
    assert _record(tmp_path, "saved")["wake_terminations"] == "carried"
