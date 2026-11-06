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
from pyflightstream._fsm import trailing_edge_midpoints
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


# R1-MARK-001: a sector saved by FlightStream 26.127 holds the three edge-slot rows of the mesh
# block as integers, 0 for no trailing edge and the trailing-edge group's number for one
# (FR-3764). The saved route read only T/F rows there, so it warned the layout as not
# recognized and wrote no wheel.
EDGE_ROWS = (21, 22, 23)


def _first_row(lines: list[str]) -> int:
    start = lines.index("$MESH_START$")
    return start + 4 + 3 * int(lines[start + 3]) + 1


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.split(",") if cell.strip()]


def _as_26127(sector: Path, out: Path, *, value: int | None = None) -> Path:
    """Rewrite the edge-slot rows as 26.127 saves them: T as the face's group (row 5), F as 0."""
    lines = sector.read_text().split("\n")
    first = _first_row(lines)
    group = [int(v) for v in _cells(lines[first + 5])]
    for k in EDGE_ROWS:
        flags = _cells(lines[first + k])
        lines[first + k] = "".join(
            f"{(group[i] if value is None else value) if f == 'T' else 0},"
            for i, f in enumerate(flags)
        )
    out.write_text("\n".join(lines))
    return out


def _mesh_rows(path: Path) -> dict[int, list[str]]:
    lines = path.read_text().split("\n")
    first = _first_row(lines)
    return {k: _cells(lines[first + k]) for k in range(25)}


@pytest.mark.requirement("FR-3764")
def test_p0560_r1_mark_001_the_saved_route_repeats_a_26127_sector_with_each_copy_s_groups(
    tmp_path: Path,
) -> None:
    sector = build_saved_sector(tmp_path, build_sector(tmp_path, copies=COPIES))
    saved = _as_26127(sector, tmp_path / "sector_26127.fsm")
    out = tmp_path / "wheel.fsm"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = sector_to_wheel(saved, copies=COPIES, blades=["Blade1"], axis="x", out=out)
    assert not [w for w in caught if "not recognized" in str(w.message)]
    assert result.written
    plain = tmp_path / "plain_wheel.fsm"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sector_to_wheel(sector, copies=COPIES, blades=["Blade1"], axis="x", out=plain)
    # the trailing edges of the wheel of the same sector saved with T/F rows
    assert trailing_edge_midpoints(out) == trailing_edge_midpoints(plain)
    rows, flags = _mesh_rows(out), _mesh_rows(plain)
    group = np.array([int(v) for v in rows[5]])
    named: set[int] = set()
    for k in EDGE_ROWS:
        written = np.array([int(v) for v in rows[k]])
        marked = np.array([f == "T" for f in flags[k]])
        # the integer form is kept, and each flagged edge names its own copy's group
        assert (written[marked] == group[marked]).all()
        assert (written[~marked] == 0).all()
        named |= set(written[marked].tolist())
    # every copy's rim groups, not the sector's repeated: two blade rims per copy and the nacelle
    assert len(named) == 2 * COPIES + 1
    assert set(rows[20]) <= {"T", "F"} and set(rows[24]) <= {"T", "F"}


@pytest.mark.requirement("FR-3764")
def test_p0560_r1_mark_001_an_integer_edge_flag_that_is_not_its_face_s_group_is_not_guessed(
    tmp_path: Path,
) -> None:
    """An integer that is not the rim face's group has no measured meaning: warned, no wheel."""
    sector = build_saved_sector(tmp_path, build_sector(tmp_path, copies=COPIES))
    odd = _as_26127(sector, tmp_path / "odd.fsm", value=7)
    out = tmp_path / "odd_wheel.fsm"
    with pytest.warns(PyflightstreamWarning, match="not recognized"):
        result = sector_to_wheel(odd, copies=COPIES, blades=["Blade1"], axis="x", out=out)
    assert not result.written and not out.exists()


@pytest.mark.requirement("FR-3764")
def test_p0560_r1_mark_001_the_body_of_a_26127_sector_names_the_form_it_does_not_read(
    tmp_path: Path,
) -> None:
    """power-off-body reads the edge rows as flags, so it names the 26.127 form, writes nothing."""
    from tests.tier1_offline.test_p0540_sector_remesh import build_blunt_sector

    saved = _as_26127(build_blunt_sector(tmp_path), tmp_path / "blunt_26127.fsm")
    with pytest.warns(PyflightstreamWarning) as caught:
        result = _body(saved, tmp_path / "body.fsm")
    assert not result.written and not (tmp_path / "body.fsm").exists()
    assert "26.127" in " ".join(str(item.message) for item in caught)
