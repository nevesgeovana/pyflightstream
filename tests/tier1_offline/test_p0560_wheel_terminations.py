"""P0560-WHEEL: wake terminations carried by sector-to-wheel and marked across a merge.

Pipeline role: tier-1 oracle of PFS-2195 (FR-3720, FR-3721), PFS-2187.08 (FR-3722, FR-3723)
and PFS-2187.11 (FR-3724, the body of a nacelle marked with ``merge_into``, compared with the
body of the same sector named for its boundaries). The wheel's sector is the synthetic one of
``test_p0540_wheel``, with its blade base and nacelle base merged into their parents and one
explicit wake-termination node at the tip end of a rim. The node expected in the wheel is that
tip point turned by each copy's angle, computed here, not read from the code under test.
"""

from __future__ import annotations

import json
import tomllib
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import (
    InputArtifactError,
    NotApplicableWarning,
    PyflightstreamWarning,
)
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
@pytest.mark.parametrize("build", ["26.124", "26.125", "26.127"])
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
@pytest.mark.parametrize("build", ["26.126"])
def test_p0560_explicit_terminations_across_a_merge_on_an_unmeasured_build_name_the_evidence(
    tmp_path: Path, build: str
) -> None:
    built, _ = terminated_sector(tmp_path, build)
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    with pytest.raises(InputArtifactError) as caught:
        plan_mark_boundaries(wheel)
    words = str(caught.value)
    assert build in words and all(name in words for name in ("26.124", "26.125", "26.127"))
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


def _body(sector: Path, out: Path):
    from pyflightstream.workspace import power_off_body

    return power_off_body(sector, blades=["Blade1"], copies=COPIES, out=out)


@pytest.mark.requirement("FR-3724")
def test_p0560_the_body_of_a_marked_nacelle_is_the_plain_body_under_the_merged_names(
    tmp_path: Path,
) -> None:
    """PFS-2187.11: the mesh and every physics value are the plain sector's; only names move."""
    from tests.tier1_offline.test_p0540_sector_remesh import build_blunt_sector
    from tests.tier1_offline.test_p0550_wheel_mark import _marked

    plain = build_blunt_sector(tmp_path)
    marked = _marked(plain, tmp_path / "marked.fsm")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        expected = _body(plain, tmp_path / "plain_body.fsm")
    with pytest.warns(PyflightstreamWarning) as caught:
        got = _body(marked, tmp_path / "marked_body.fsm")
    assert expected.written and got.written
    lines = got.output.read_text(encoding="latin-1").splitlines()
    want = expected.output.read_text(encoding="latin-1").splitlines()
    assert len(lines) == len(want)
    differing = [(w, g) for w, g in zip(want, lines, strict=True) if w != g]
    assert differing == [("N", "NBase"), ("N", "NBase")]
    words = [str(item.message) for item in caught if "merged" in str(item.message)]
    assert len(words) == 1
    assert "NBase into N" in words[0] and "Base1 into Blade1" in words[0]
    assert "keeps NBase" in words[0] and "removes Base1" in words[0]


@pytest.mark.requirement("FR-3724")
def test_p0560_a_plain_sector_s_body_says_nothing_of_merged_families(tmp_path: Path) -> None:
    from tests.tier1_offline.test_p0540_sector_remesh import build_blunt_sector

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _body(build_blunt_sector(tmp_path), tmp_path / "body.fsm")
    assert result.written
    assert not [item for item in caught if "merged" in str(item.message)]


@pytest.mark.requirement("FR-3724")
def test_p0560_a_nacelle_base_under_another_boundary_s_name_is_not_guessed(tmp_path: Path) -> None:
    """The nacelle's base named for the spinner: no entry is the nacelle's, nothing is written."""
    from tests.tier1_offline.test_p0540_sector_remesh import build_blunt_sector
    from tests.tier1_offline.test_p0550_wheel_mark import _relabelled

    other = _relabelled(
        build_blunt_sector(tmp_path),
        tmp_path / "other.fsm",
        base="2\nBase1\nS\n F, F,",
        te="3\nBase1\nBase1\nNBase\n1,1,1,",
        term="2\nBase1\nBase1\n1,1,\n",
    )
    with pytest.warns(PyflightstreamWarning) as caught:
        result = _body(other, tmp_path / "body.fsm")
    words = " ".join(str(item.message) for item in caught)
    assert not result.written and not (tmp_path / "body.fsm").exists()
    assert "base region of the nacelle 'N'" in words and "0 such names" in words
