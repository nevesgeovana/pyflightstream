"""P0540-WHEEL-FSM: the saved route of sector-to-wheel, from a saved sector built here.

Pipeline role: tier-1 oracle of PFS-2186.04 (FR-3467, FR-3468). The saved sector is written
in the form the saved files of the solver take (a mesh block of 25 per-face rows, a wake
termination tail and a physics block), from the geometry ``test_p0540_wheel.build_sector``
makes: a blade with a blunt trailing edge (two rims and a base), a spinner and a nacelle with
a base and a rim. The wheel is read back with the package's own saved-file readers and with a
parser of the rows written here, and compared with the sector's rows turned about the axis.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._fsm import (
    boundary_names,
    saved_base_regions,
    saved_termination_count,
    saved_trailing_edge_groups,
    surface_mesh,
    trailing_edge_midpoints,
)
from pyflightstream.workspace._wheel import sector_to_wheel
from tests.tier1_offline.test_p0540_wheel import Built, build_sector, turn

COPIES = 6
NAMES = ["Blade1", "S", "N"]


def _row(values) -> str:
    return "".join(f"{int(v)}," for v in values)


def _flags(values) -> str:
    return "".join(f" {'T' if v else 'F'}," for v in values)


def _reals(values) -> str:
    return "".join(f"{v: .17E}," for v in values)


def build_saved_sector(folder: Path, built: Built, name: str = "sector.fsm") -> Path:
    """Write the saved form of a built sector: triangles, rim faces, bases, terminations."""
    verts = built.verts
    sets = {
        1: {frozenset(e) for e in built.rims["TE_a"]},
        2: {frozenset(e) for e in built.rims["TE_b"]},
        3: {frozenset(e) for e in built.rims["N"]},
    }
    rows: dict[str, list] = {k: [] for k in ("tri", "group", "slot", "partner", "owner", "kind")}
    flags = [[], [], []]
    terms: list[tuple[int, int]] = []
    for boundary, family in enumerate(NAMES, 1):
        polys = built.families[family]
        base = {"Blade1": built.base_faces, "S": 0, "N": built.notes["disc"]}[family]
        for index, poly in enumerate(polys):
            is_base = index >= len(polys) - base
            parts = [poly] if len(poly) == 3 else [poly[:3], [poly[0], poly[2], poly[3]]]
            for part, tri in enumerate(parts):
                number = len(rows["tri"]) + 1
                rows["tri"].append(tri)
                rows["owner"].append(boundary)
                if len(parts) == 2:
                    rows["slot"].append(3 if part == 0 else 1)
                    rows["partner"].append(number + 1 if part == 0 else number - 1)
                else:
                    rows["slot"].append(0)
                    rows["partner"].append(0)
                slot_flags = [False, False, False]
                group, kind = 0, 0
                if is_base:
                    group, kind = (1 if family == "Blade1" else 2), 3
                else:
                    for s, (a, b) in enumerate(((0, 1), (1, 2), (2, 0))):
                        edge = frozenset((tri[a], tri[b]))
                        hit = [g for g, edges in sets.items() if edge in edges]
                        if hit:
                            slot_flags[s], group, kind = True, hit[0], 1
                            if len(terms) < 2 and hit[0] in (1, 2) and (hit[0], 0) not in terms:
                                terms.append((number, hit[0]))
                rows["group"].append(group)
                rows["kind"].append(kind)
                for s in range(3):
                    flags[s].append(slot_flags[s])
    nf = len(rows["tri"])
    tri = np.array(rows["tri"]) + 1
    nodes = len(verts)
    zeros = [0] * nf
    per_face = [
        _row(range(1, nf + 1)),
        _row([3] * nf),
        _row(tri[:, 0]),
        _row(tri[:, 1]),
        _row(tri[:, 2]),
        _row(rows["group"]),
        *[_row(zeros)] * 3,
        _row(rows["slot"]),
        _row(rows["partner"]),
        _row(rows["owner"]),
        _row(rows["kind"]),
        *[_row(zeros)] * 7,
        _flags([False] * nf),
        *[_flags(f) for f in flags],
        _flags([False] * nf),
    ]
    mesh = ["$MESH_START$", str(nf), "4", "3"]
    for boundary, family in enumerate(NAMES, 2):
        mesh += [f"{boundary}, T, F, F", family, ".494,.573,.576"]
    mesh += [str(nf), *per_face, "0", str(nodes)]
    mesh += [_reals(verts[:, k]) for k in range(3)]
    mesh += [
        "2",
        _row([face for face, _ in terms]),
        _row([1, 1]),
        _row([group for _, group in terms]),
        "$MESH_END$",
    ]
    physics = [
        "$PHYSICS_START$",
        " 0.14000E+03",
        " 0.45000E+02",
        " 0.15000E+02",
        "2",
        "Blade1",
        "N",
        " F, F,",
        "-0.2,-0.2,",
        "0,0,",
        "0,0,",
        "0,0,",
        "3",
        "Blade1",
        "Blade1",
        "N",
        "1,1,1,",
        "2",
        "Blade1",
        "Blade1",
        "1,1,",
        "1,1,1,0",
        " 0.00000000000000000E+00",
        "0",
        "0",
        "0",
        "Air",
        *[f" {v:.17E}" for v in (1.225, 1.78e-5, 340.3, 288.16, 101324.0, 1.4, 0.0)],
        "1,1,",
        "$PHYSICS_END$",
    ]
    head = ["26,1", "7012026", "$GLOBAL_START$", "1.0", "5", "$GLOBAL_END$"]
    path = folder / name
    path.write_text("\n".join([*head, *mesh, *physics, "$MOTION_START$", "$MOTION_END$"]) + "\n")
    return path


def _saved(tmp_path, copies: int = COPIES, **kwargs):
    built = build_sector(tmp_path, copies=copies, **kwargs)
    return built, build_saved_sector(tmp_path, built)


def _rows_of(path: Path) -> dict[int, list[int]]:
    """The mesh block's per-face integer rows, read by line position after the records."""
    lines = path.read_text().split("\n")
    start = lines.index("$MESH_START$")
    nb = int(lines[start + 3])
    first = start + 4 + 3 * nb + 1
    return {k: [int(x) for x in lines[first + k].split(",") if x.strip()] for k in range(20)}


@pytest.mark.requirement("FR-3467")
@pytest.mark.parametrize("copies", [6, 4])
def test_p0540_a_saved_sector_gives_a_saved_wheel_with_n_times_the_entries(tmp_path, copies):
    built, sector = _saved(tmp_path, copies)
    out = tmp_path / "wheel.fsm"
    result = sector_to_wheel(sector, copies=copies, blades=["Blade1"], axis="x", out=out)
    assert result.written and result.output == out
    # read back by the package's own readers
    others = [f"Blade{k}" for k in range(2, copies + 1)]
    assert boundary_names(out) == ("Blade1", "S", "N", *others)
    assert saved_trailing_edge_groups(out) == (
        *[f"Blade{k}" for k in range(1, copies + 1) for _ in range(2)],
        "N",
    )
    assert [n for n, _, _ in saved_base_regions(out)] == [
        *[f"Blade{k}" for k in range(1, copies + 1)],
        "N",
    ]
    assert saved_termination_count(out) == 2 * copies
    assert len(trailing_edge_midpoints(out)) == copies * len(trailing_edge_midpoints(sector))
    # the base regions and trailing-edge groups of each copy, from the rows written
    own, kind, group = _rows_of(out)[11], _rows_of(out)[12], _rows_of(out)[5]
    nf = len(_rows_of(sector)[0])
    for c in range(copies):
        window = slice(c * nf, (c + 1) * nf)
        o, k, g = np.array(own[window]), np.array(kind[window]), np.array(group[window])
        blade = o == (1 if c == 0 else 3 + c)
        assert set(g[blade & (k == 3)]) == {c + 1}
        assert set(g[blade & (k == 1)]) == {2 * c + 1, 2 * c + 2}
        assert set(g[(o == 3) & (k == 3)]) == {copies + 1}
        assert set(g[(o == 3) & (k == 1)]) == {2 * copies + 1}
    # the sector's face order inside each copy: face j of copy c is face j turned by c steps
    sv, st = surface_mesh(sector)
    wv, wt = surface_mesh(out)
    assert len(wt) == copies * len(st)
    sv, wv = np.array(sv), np.array(wv)
    for c in (0, 1, copies - 1):
        turned = turn(sv, np.array([1.0, 0, 0]), np.zeros(3), 360.0 * c / copies)
        for j in range(0, len(st), 7):
            got = wv[list(wt[c * len(st) + j])]
            assert np.allclose(got, turned[list(st[j])], atol=1e-9)
    assert result.report["area_ratio"] == pytest.approx(1.0, rel=1e-12)
    assert result.report["invariance"]["faces_mapped"] == len(wt)
    assert result.report["control"]["faces_mapped"] < len(wt)
    assert result.report["degenerate_faces"] == 0
    # the termination tail: copy c repeats the sector's faces shifted by c sector faces
    terms, first = _termination(out), _termination(sector)
    assert terms[0] == [f + c * nf for c in range(copies) for f in first[0]]
    assert terms[1] == first[1] * copies
    assert terms[2] == [g + 2 * c for c in range(copies) for g in first[2]]


def _termination(path: Path) -> list[list[int]]:
    lines = path.read_text().split("\n")
    end = lines.index("$MESH_END$")
    return [[int(x) for x in lines[end - 3 + k].split(",") if x.strip()] for k in range(3)]


@pytest.mark.requirement("FR-3467")
def test_p0540_a_second_header_value_above_the_last_boundary_id_is_a_known_layout(tmp_path):
    """A saved sector may count past its last boundary id, as one that lost a boundary does."""
    built, sector = _saved(tmp_path)
    lines = sector.read_text().split("\n")
    start = lines.index("$MESH_START$")
    assert lines[start + 2] == "4"
    lines[start + 2] = "5"
    above = tmp_path / "above.fsm"
    above.write_text("\n".join(lines))
    result = sector_to_wheel(
        above, copies=COPIES, blades=["Blade1"], out=tmp_path / "above_wheel.fsm"
    )
    assert result.written


@pytest.mark.requirement("FR-3468")
def test_p0540_a_layout_the_reader_does_not_recognize_is_warned_and_nothing_is_written(tmp_path):
    from pyflightstream.workspace.cli import main as workspace_main

    built, sector = _saved(tmp_path)
    text = sector.read_text()
    # a trailing-edge group named for no boundary of the mesh
    bad = tmp_path / "bad_name.fsm"
    bad.write_text(text.replace("3\nBlade1\nBlade1\nN\n", "3\nBlade1\nWing\nN\n"))
    # a per-face row of the wrong length
    short = tmp_path / "short_row.fsm"
    lines = text.split("\n")
    start = lines.index("$MESH_START$") + 4 + 9 + 1
    lines[start + 5] = lines[start + 5].rsplit(",", 2)[0] + ","
    short.write_text("\n".join(lines))
    for source in (bad, short):
        out = tmp_path / f"{source.stem}_wheel.fsm"
        with pytest.warns(Warning, match="not recognized"):
            result = sector_to_wheel(source, copies=COPIES, blades=["Blade1"], out=out)
        assert not result.written
        assert not out.exists() and not list(tmp_path.glob("*.part"))
        assert not out.with_name(f"{out.stem}.wheel.json").exists()
        argv = ["geometry", "sector-to-wheel", str(source), "--copies", "6", "--blades", "Blade1"]
        assert workspace_main([*argv, "--out", str(out)]) == 2
        assert not out.exists()


@pytest.mark.requirement("FR-3467")
def test_p0540_the_saved_route_needs_a_blade_that_is_a_boundary_and_no_solver(tmp_path, capsys):
    from pyflightstream.workspace.cli import main as workspace_main

    built, sector = _saved(tmp_path)
    argv = ["geometry", "sector-to-wheel", str(sector), "--copies", "6"]
    out = tmp_path / "cli.fsm"
    assert workspace_main([*argv, "--blades", "Wing", "--out", str(out)]) == 2
    assert "not a boundary of the sector" in capsys.readouterr().err and not out.exists()
    assert workspace_main([*argv, "--blades", "Blade1", "--out", str(out)]) == 0
    assert "area ratio" in capsys.readouterr().out and out.is_file()
    assert workspace_main([*argv, "--blades", "Blade1", "--out", str(out)]) == 2
    assert workspace_main([*argv, "--blades", "Blade1", "--out", str(out), "--overwrite"]) == 0
    assert math.isclose(1.0, 1.0)
