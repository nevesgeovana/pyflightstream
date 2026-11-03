"""P0540-REMESH: sector-remesh and power-off-body on a blunt-trailing-edge sector built here.

Pipeline role: tier-1 oracle of PFS-2186.06 (FR-3490 to FR-3499). The sector is written in the
saved layout from geometry made in numpy: a tapered, twisted, swept blade with a blunt trailing
edge (two rim lines and a base strip) on a spinner of revolution, and a nacelle of revolution with
a flat base. The checks do not use the code under test: triangles, radii, chord widths, nodes and
the turn of the wheel are measured here on the written files, read with the layout parser.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.spatial import cKDTree

from tests.tier1_offline.test_p0540_wheel import Built
from tests.tier1_offline.test_p0540_wheel_fsm import build_saved_sector

HUB, TIP, SPANS, SIDE = 0.4, 1.2, 12, 8
PERMUTATION = {"x": (0, 1, 2), "y": (1, 2, 0), "z": (2, 0, 1)}


def _blade(verts: list[list[float]]) -> tuple[Any, list[list[int]]]:
    """Return the node ids (station by ring node) of a tapered, twisted, swept blunt blade."""
    f = 1.0 - np.cos(0.5 * np.pi * np.arange(SIDE + 1) / SIDE)
    ids = np.zeros((SPANS + 1, 2 * SIDE + 1), dtype=int)
    for j in range(SPANS + 1):
        s = j / SPANS
        rho0 = HUB + (TIP - HUB) * s
        chord, beta = 0.3 - 0.15 * s, math.radians(25.0 - 20.0 * s)
        for k in range(2 * SIDE + 1):
            fk = f[abs(k - SIDE)]
            h = (
                0.1
                * chord
                * math.sqrt(fk)
                * (1 - 0.7 * fk)
                * (0 if k == SIDE else 1 if k < SIDE else -1)
            )
            u, v = (fk - 0.25) * chord, h
            x = 0.65 + 0.1 * (rho0 - HUB) + u * math.cos(beta) - v * math.sin(beta)
            rho = rho0 * (1 + 0.03 * s * (fk - 0.5))
            alpha = (u * math.sin(beta) + v * math.cos(beta)) / rho
            verts.append([x, rho * math.cos(alpha), rho * math.sin(alpha)])
            ids[j, k] = len(verts) - 1
    polys = [
        [ids[j, k], ids[j + 1, k], ids[j + 1, k + 1], ids[j, k + 1]]
        for j in range(SPANS)
        for k in range(2 * SIDE)
    ]
    polys += [[ids[j, 0], ids[j + 1, 0], ids[j + 1, -1], ids[j, -1]] for j in range(SPANS)]
    return ids, [[int(n) for n in p] for p in polys]


def _revolved(
    verts: list[list[float]], profile: list[tuple[float, float]], half: float, cells: int
) -> list[list[int]]:
    """Return the ring node ids of a surface of revolution over the sector, one ring per station."""
    rings = []
    for x, r in profile:
        row = []
        for t in np.linspace(-half, half, cells + 1):
            verts.append([x, r * math.cos(t), r * math.sin(t)])
            row.append(len(verts) - 1)
        rings.append(row)
    return rings


def build_blunt_sector(
    folder: Path,
    *,
    copies: int = 6,
    axis: str = "x",
    reverse: bool = False,
    name: str = "sector.fsm",
) -> Path:
    """Write a saved sector: a blunt-trailing-edge blade, a spinner and a nacelle with a base."""
    half, cells = math.pi / copies, 4
    verts: list[list[float]] = []
    ids, blade = _blade(verts)
    nose = [(x, HUB * math.sqrt(1 - (1 - x / 0.4) ** 2)) for x in (0.02, 0.07, 0.14, 0.24, 0.4)]
    spin = [*nose, *[(0.4 + 0.1 * i, HUB) for i in range(1, 7)]]
    pole = len(verts)
    verts.append([0.0, 0.0, 0.0])
    rings = _revolved(verts, spin, half, cells)
    s_faces = [[pole, rings[0][j + 1], rings[0][j]] for j in range(cells)]
    s_faces += [
        [rings[i][j], rings[i + 1][j], rings[i + 1][j + 1], rings[i][j + 1]]
        for i in range(len(rings) - 1)
        for j in range(cells)
    ]
    loop = [int(n) for n in ids[0]]
    s_faces += [[pole, loop[k], loop[k + 1]] for k in range(len(loop) - 1)]
    stations = [(1.001 + 0.06 * i, 0.4 + 0.1 * (1 - (1 - i / 6) ** 2)) for i in range(7)]
    stations += [(1.001 + 0.06 * 6 + 0.1 * i, 0.5) for i in range(1, 10)]
    nac = _revolved(verts, stations, half, cells)
    n_faces = [
        [nac[i][j], nac[i + 1][j], nac[i + 1][j + 1], nac[i][j + 1]]
        for i in range(len(nac) - 1)
        for j in range(cells)
    ]
    centre = len(verts)
    verts.append([stations[-1][0], 0.0, 0.0])
    disc = [[centre, nac[-1][j + 1], nac[-1][j]] for j in range(cells)]
    local = np.array(verts)
    if reverse:
        local[:, 0], local[:, 2] = -local[:, 0], -local[:, 2]
    world = np.empty_like(local)
    world[:, PERMUTATION[axis]] = local
    rims = {
        "TE_a": [(int(ids[j, 0]), int(ids[j + 1, 0])) for j in range(SPANS)],
        "TE_b": [(int(ids[j, -1]), int(ids[j + 1, -1])) for j in range(SPANS)],
        "N": [(nac[-1][j], nac[-1][j + 1]) for j in range(cells)],
    }
    built = Built(
        folder / "unused.obj", copies, axis, (0.0, 0.0, 0.0), world,
        {"Blade1": blade, "S": s_faces, "N": n_faces + disc}, set(), SPANS, {"disc": cells}, rims,
    )  # fmt: skip
    return build_saved_sector(folder, built, name)


COPIES = 6
CHORD = 12
ARGS = {"chord_cells": CHORD, "le": 0.03, "span_cell": 0.1, "spinner_theta": 4}


def _cells(line: str) -> list[str]:
    return [x.strip() for x in line.split(",") if x.strip()]


def _read(path: Path) -> dict[str, Any]:
    """The written file's rows, read here by position with no code under test.

    The mesh block is: a head, the count, the last id, the number of boundaries and three lines
    each, the count again, 25 rows of one value per face, ``0``, the node count, three rows of
    coordinates and the wake termination (a count and three rows).
    """
    lines = path.read_bytes().decode("latin-1").split("\n")
    lines = [x.rstrip("\r") for x in lines]
    start = lines.index("$MESH_START$")
    nb = int(lines[start + 3])
    first = start + 4 + 3 * nb + 1
    rows = [_cells(lines[first + k]) for k in range(25)]
    ints = {k: np.array([int(x) for x in rows[k]]) for k in range(20)}
    at = first + 25
    xyz = np.array([[float(x) for x in _cells(lines[at + 2 + k])] for k in range(3)]).T
    n_term = int(lines[at + 5])
    term = [[int(x) for x in _cells(lines[at + 6 + k])] for k in range(3 if n_term else 0)]
    return {
        "xyz": xyz,
        "tri": np.stack([ints[2], ints[3], ints[4]], axis=1) - 1,
        "owner": ints[11],
        "kind": ints[12],
        "group": ints[5],
        "partner": ints[10] - 1,
        "names": [lines[start + 5 + 3 * k].strip() for k in range(nb)],
        "flags": [np.array(rows[r]) == "T" for r in (21, 22, 23)],
        "term": term,
    }


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    """A blunt sector, its remesh and its body, made once by the two verbs."""
    from pyflightstream.workspace import power_off_body, sector_remesh

    folder = tmp_path_factory.mktemp("remesh")
    source = build_blunt_sector(folder)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        remesh = sector_remesh(source, blades=["Blade1"], out=folder / "new.fsm", **ARGS)
        body = power_off_body(
            source, blades=["Blade1"], copies=COPIES, out=folder / "body.fsm", spinner_rings=4
        )
    assert remesh.written and body.written
    return {"folder": folder, "source": source, "remesh": remesh, "body": body}


def _grid(made) -> tuple[np.ndarray, int, int]:
    """The remeshed blade nodes as a (rows, columns, 3) array, from the record's grid size."""
    data = _read(made["remesh"].output)
    n_rows, n_col = (
        made["remesh"].report["build"]["rows"],
        made["remesh"].report["build"]["columns"],
    )
    return data["xyz"][: n_rows * n_col].reshape(n_rows, n_col, 3), n_rows, n_col


def _widths(row: np.ndarray, n_col: int) -> np.ndarray:
    """Chord widths of side b, from the leading edge (the middle column is the leading edge)."""
    side = row[CHORD + 1 :]
    return np.linalg.norm(np.diff(side, axis=0), axis=1)


def _monotone_then_fixed(w: np.ndarray, tol: float = 0.08) -> bool:
    """Widths never fall in the growing part, and are one width from the middle of the arc out."""
    arc = np.r_[0.0, np.cumsum(w)] / w.sum()
    fixed = w[arc[:-1] >= 0.5 - 1e-9]
    grow = w[: len(w) - len(fixed)]
    return bool(
        np.all(grow[:-1] <= grow[1:] * (1 + 1e-9)) and fixed.max() <= fixed.min() * (1 + tol)
    )


@pytest.mark.requirement("FR-3490")
def test_p0540_the_remesh_holds_no_triangle_and_every_face_is_a_pair(made):
    data = _read(made["remesh"].output)
    partner, tri = data["partner"], data["tri"]
    assert (partner >= 0).all() and (partner[partner] == np.arange(len(partner))).all()
    assert (data["owner"][partner] == data["owner"]).all()
    shared = [len(set(tri[i]) & set(tri[j])) for i, j in enumerate(partner)]
    assert set(shared) == {2}
    for k in (1, 2, 3):
        assert (data["owner"] == k).sum() > 0 and (data["owner"] == k).sum() % 2 == 0
    assert made["remesh"].report["triangles"] == {"Blade1": 0, "S": 0, "N": 0}
    # control: the source holds triangles (the spinner's pole fan and the nacelle's disc)
    src = _read(made["source"])
    assert (src["partner"] < 0).any()


@pytest.mark.requirement("FR-3491")
def test_p0540_from_mid_blade_out_every_row_is_at_one_radius(made):
    grid, n_rows, _ = _grid(made)
    radius = np.hypot(grid[:, :, 1], grid[:, :, 2])
    spread = np.ptp(radius, axis=1)
    mean = radius.mean(axis=1)
    mid = 0.5 * (mean[0] + mean[-1])
    outboard = mean >= mid
    assert outboard.sum() > 3
    assert spread[outboard].max() < 1e-3 * mean[-1]
    assert spread[-1] < 1e-6
    # control: the source rows are not at one radius (the sections are swept)
    src = _read(made["source"])
    ring = src["xyz"][: 17 * 13].reshape(13, 17, 3)
    assert np.ptp(np.hypot(ring[-1, :, 1], ring[-1, :, 2])) > 100 * spread[-1] + 1e-3
    assert made["remesh"].report["checks"]["radius_spread"]["outboard_worst"] == pytest.approx(
        spread[outboard].max(), rel=1e-6
    )


@pytest.mark.requirement("FR-3492")
def test_p0540_chord_widths_grow_to_one_fixed_width_in_every_row_root_included(made):
    grid, n_rows, n_col = _grid(made)
    assert all(_monotone_then_fixed(_widths(grid[m], n_col)) for m in range(n_rows))
    # the leading edge is clustered: the first width is a small fraction of the fixed one
    first, fixed = _widths(grid[0], n_col)[0], _widths(grid[0], n_col)[-1]
    assert first < 0.3 * fixed
    # control: the same widths, reversed or shuffled, fail the check
    w = _widths(grid[0], n_col)
    assert not _monotone_then_fixed(w[::-1])
    assert not _monotone_then_fixed(np.roll(w, 3))
    assert made["remesh"].report["checks"]["chord"]["monotonic"]


@pytest.mark.requirement("FR-3493")
def test_p0540_the_spinner_adapts_to_the_root_row_which_is_never_moved(made):
    grid, _, n_col = _grid(made)
    data = _read(made["remesh"].output)
    blade_nodes = set(data["tri"][data["owner"] == 1].ravel().tolist())
    spinner_nodes = set(data["tri"][data["owner"] == 2].ravel().tolist())
    root = set(range(n_col))
    assert blade_nodes & spinner_nodes == root
    # the root row is the chord law: the same fractions as every other row
    assert _monotone_then_fixed(_widths(grid[0], n_col))
    # the spinner's root loop quads sit on the spinner surface: radius equal to the hub
    assert np.allclose(np.hypot(grid[0, :, 1], grid[0, :, 2]), HUB, rtol=2e-3)


@pytest.mark.requirement("FR-3493")
def test_p0540_a_folded_spinner_grid_warns_naming_the_layers_and_writes_nothing(tmp_path):
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.workspace import sector_remesh

    source = build_blunt_sector(tmp_path)
    out = tmp_path / "folded.fsm"
    args = {**ARGS, "spinner_layers": 1, "root_margin_r": 0.6}
    with pytest.warns(PyflightstreamWarning, match="--spinner-layers"):
        result = sector_remesh(source, blades=["Blade1"], out=out, **args)
    assert not result.written
    assert not out.exists() and not list(tmp_path.glob("*.part"))
    assert not out.with_name("folded.remesh.json").exists()
    # control: the same sector with the default layers is not folded
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert sector_remesh(source, blades=["Blade1"], out=out, **ARGS).written


@pytest.mark.requirement("FR-3494")
def test_p0540_the_nacelle_of_the_remesh_and_of_the_body_are_the_same_nodes(made):
    sector, body = _read(made["remesh"].output), _read(made["body"].output)
    n_sector = np.unique(sector["tri"][sector["owner"] == 3])
    n_body = np.unique(body["tri"][body["owner"] == 2])
    points = body["xyz"][n_body]
    psi = np.arctan2(points[:, 2], points[:, 1])
    inside = points[np.abs(psi) <= np.pi / COPIES + 1e-9]
    mine = sector["xyz"][n_sector]
    tree = cKDTree(mine)
    assert tree.query(inside)[0].max() == 0.0 or tree.query(inside)[0].max() < 1e-12
    assert cKDTree(inside).query(mine)[0].max() < 1e-12
    assert len(mine) == len(inside)
    # control: nodes of the spinner are not nacelle nodes
    spinner = sector["xyz"][np.unique(sector["tri"][sector["owner"] == 2])]
    assert tree.query(spinner)[0].min() > 1e-6


@pytest.mark.requirement("FR-3495")
def test_p0540_two_trailing_edges_per_blade_and_the_base_read_back_through_fsm(made):
    from pyflightstream._fsm import (
        boundary_names,
        saved_base_regions,
        saved_termination_count,
        saved_trailing_edge_groups,
        surface_mesh,
    )

    path = made["remesh"].output
    data = _read(path)
    _, n_rows, n_col = _grid(made)
    assert boundary_names(path) == ("Blade1", "S", "N")
    assert saved_trailing_edge_groups(path) == ("Blade1", "Blade1", "N")
    assert [b[0] for b in saved_base_regions(path)] == ["Blade1", "N"]
    assert saved_termination_count(path) == 2
    assert len(surface_mesh(path)[1]) == len(data["tri"])
    blade = data["owner"] == 1
    flagged = np.zeros(len(blade), dtype=int)
    for slot in data["flags"]:
        flagged += slot
    for group in (1, 2):
        faces = blade & (data["kind"] == 1) & (data["group"] == group)
        assert faces.sum() == n_rows - 1 and flagged[faces].sum() == n_rows - 1
    base = blade & (data["kind"] == 3)
    assert base.sum() == 2 * (n_rows - 1) and set(data["group"][base]) == {1}
    # the wake terminates at the root end of each rim line
    faces, slots, groups = data["term"]
    ends = {1: 0, 2: n_col - 1}
    for face, slot, group in zip(faces, slots, groups, strict=True):
        assert data["tri"][face - 1][slot - 1] == ends[group]


@pytest.mark.requirement("FR-3496")
def test_p0540_remesh_then_sector_to_wheel_is_invariant_to_a_sixth_of_a_turn(made):
    from pyflightstream.workspace import sector_to_wheel

    out = made["folder"] / "wheel.fsm"
    result = sector_to_wheel(
        made["remesh"].output, copies=COPIES, blades=["Blade1"], out=out, overwrite=True
    )
    assert result.written
    turn, control = result.report["invariance"], result.report["control"]
    assert turn["nodes_mapped"] == turn["nodes"] and turn["faces_mapped"] == turn["faces"]
    assert control["faces_mapped"] == 0
    wheel = _read(out)
    c, s = np.cos(np.pi / 3), np.sin(np.pi / 3)
    p = wheel["xyz"]
    turned = np.c_[p[:, 0], c * p[:, 1] - s * p[:, 2], s * p[:, 1] + c * p[:, 2]]
    size = np.ptp(p, axis=0).max()
    assert cKDTree(p).query(turned)[0].max() <= 1e-9 * size
    # control: a turn of 61 degrees is not mapped
    c, s = np.cos(np.radians(61)), np.sin(np.radians(61))
    off = np.c_[p[:, 0], c * p[:, 1] - s * p[:, 2], s * p[:, 1] + c * p[:, 2]]
    assert cKDTree(p).query(off)[0].max() > 1e-3 * size
    # the record of the remesh says the same
    rotation = made["remesh"].report["checks"]["rotation"]
    assert rotation["invariance"]["faces_mapped"] == rotation["invariance"]["faces"]
    assert rotation["control"]["faces_mapped"] == 0


@pytest.mark.requirement("FR-3497")
def test_p0540_the_body_has_a_closed_spinner_the_same_nacelle_and_no_blade(made):
    from pyflightstream._fsm import boundary_names

    path = made["body"].output
    data = _read(path)
    assert boundary_names(path) == ("S", "N")
    assert (data["partner"] >= 0).all()
    report = made["body"].report
    assert report["faces"]["triangles"] == len(data["tri"])
    assert report["faces"]["quads"] == len(data["tri"]) // 2 < 2000
    nodes = data["xyz"]
    on_axis = np.hypot(nodes[:, 1], nodes[:, 2]) < 1e-12
    assert on_axis.sum() == 2  # the spinner's pole and the centre of the nacelle's base
    spinner = np.unique(data["tri"][data["owner"] == 1])
    assert on_axis[spinner].sum() == 1
    rot = report["rotation"]["invariance"]
    assert rot["nodes_mapped"] == rot["nodes"] and rot["faces_mapped"] == rot["faces"]
    assert report["rotation"]["control"]["faces_mapped"] == 0
    # the physics block keeps the nacelle's base region and rim group only
    from pyflightstream._fsm import saved_base_regions, saved_trailing_edge_groups

    assert [b[0] for b in saved_base_regions(path)] == ["N"]
    assert saved_trailing_edge_groups(path) == ("N",)
    # control: the remeshed wheel has the blade surface the body does not
    assert (_read(made["remesh"].output)["owner"] == 1).sum() > 0


@pytest.mark.requirement("FR-3498")
@pytest.mark.parametrize(("axis", "reverse"), [("y", False), ("z", True)])
def test_p0540_the_axis_and_the_flow_direction_are_read_not_fixed(tmp_path, axis, reverse):
    from pyflightstream.workspace import sector_remesh

    source = build_blunt_sector(tmp_path, axis=axis, reverse=reverse)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = sector_remesh(source, blades=["Blade1"], axis=axis, out=tmp_path / "o.fsm", **ARGS)
    assert result.written
    rotation = result.report["checks"]["rotation"]["invariance"]
    assert rotation["faces_mapped"] == rotation["faces"] == rotation["faces"]
    assert result.report["triangles"] == {"Blade1": 0, "S": 0, "N": 0}
    assert result.report["sector"]["copies"] == COPIES


@pytest.mark.requirement("FR-3498")
def test_p0540_the_tip_radius_is_read_and_warned_unless_stated_and_the_angle_is_checked(tmp_path):
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.workspace import power_off_body, sector_remesh

    source = build_blunt_sector(tmp_path)
    with pytest.warns(PyflightstreamWarning, match="largest radius about the axis, 1.218"):
        sector_remesh(source, blades=["Blade1"], out=tmp_path / "a.fsm", **ARGS)
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        warnings.filterwarnings("ignore", message=".*states no.*")
        result = sector_remesh(
            source, blades=["Blade1"], tip_radius=1.218, out=tmp_path / "b.fsm", **ARGS
        )
    assert result.report["tip_radius_m"] == pytest.approx(1.218)
    with pytest.warns(PyflightstreamWarning, match=r"not 360/N.*N = 5 was asked"):
        power_off_body(source, blades=["Blade1"], copies=5, out=tmp_path / "c.fsm")


@pytest.mark.requirement("FR-3498")
def test_p0540_a_topology_not_found_is_warned_by_name_and_nothing_is_written(tmp_path):
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.workspace import power_off_body, sector_remesh
    from pyflightstream.workspace.cli import main as workspace_main

    source = build_blunt_sector(tmp_path)
    flat = tmp_path / "no_base.fsm"
    flat.write_bytes(source.read_bytes())
    lines = flat.read_text().split("\n")
    start = lines.index("$MESH_START$") + 4 + 9 + 1
    kind = lines[start + 12].split(",")
    kind = ["0" if k == "3" and i >= len(kind) - 20 else k for i, k in enumerate(kind)]
    lines[start + 12] = ",".join(kind)
    flat.write_text("\n".join(lines))
    cases = [
        (source, ["Wing"], "the blade 'Wing' among the boundaries"),
        (source, ["Blade1", "S"], "one blade per sector"),
        (flat, ["Blade1"], "a nacelle with a flat base"),
    ]
    for path, blades, what in cases:
        out = tmp_path / f"{path.stem}_{blades[0]}.fsm"
        for verb in (sector_remesh, power_off_body):
            extra = ARGS if verb is sector_remesh else {"copies": COPIES}
            with pytest.warns(PyflightstreamWarning, match=what):
                result = verb(path, blades=blades, out=out, **extra)
            assert not result.written and not out.exists()
    argv = ["geometry", "sector-remesh", str(flat), "--blades", "Blade1", "--chord-cells", "12"]
    out = tmp_path / "cli_flat.fsm"
    code = workspace_main([*argv, "--le", "0.03", "--span-cell", "0.1", "--out", str(out)])
    assert code == 2 and not out.exists()


@pytest.mark.requirement("FR-3499")
def test_p0540_both_verbs_run_end_to_end_and_an_existing_output_needs_overwrite(tmp_path, capsys):
    from pyflightstream.workspace.cli import main as workspace_main

    source = build_blunt_sector(tmp_path)
    sector_argv = [
        "geometry", "sector-remesh", str(source), "--blades", "Blade1", "--chord-cells", "12",
        "--le", "0.03", "--span-cell", "0.1", "--spinner-theta", "4",
    ]  # fmt: skip
    body_argv = ["geometry", "power-off-body", str(source), "--blades", "Blade1", "--copies", "6"]
    for argv, name in ((sector_argv, "s.fsm"), (body_argv, "b.fsm")):
        out = tmp_path / name
        assert workspace_main([*argv, "--out", str(out)]) == 0
        assert out.is_file() and "rotation" in capsys.readouterr().out
        assert workspace_main([*argv, "--out", str(out)]) == 2
        assert "already exist" in capsys.readouterr().err
        assert workspace_main([*argv, "--out", str(out), "--overwrite"]) == 0
    record = json.loads((tmp_path / "s.remesh.json").read_text())
    assert record["source_sha256"] and record["families"]["spinner"] == "S"
    assert record["checks"]["trailing_edges"]["wheel_groups"] == 2 * COPIES + 1
    body = json.loads((tmp_path / "b.body.json").read_text())
    assert body["faces"]["quads"] * 2 == body["faces"]["triangles"]


@pytest.mark.requirement("FR-3499")
def test_p0540_options_no_mesh_can_follow_are_refused_before_anything_is_written(tmp_path):
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace import sector_remesh

    source = build_blunt_sector(tmp_path)
    for change, text in (
        ({"spinner_theta": 5}, "even number of cells"),
        ({"chord_cells": 4}, "no growth that reaches a fixed width"),
        ({"span_cell": 5.0}, "no constant cells"),
    ):
        with pytest.raises(InputValueError, match=text):
            sector_remesh(source, blades=["Blade1"], out=tmp_path / "x.fsm", **{**ARGS, **change})
    assert not (tmp_path / "x.fsm").exists()


@pytest.mark.requirement("FR-3499")
def test_p0540_a_second_header_value_above_the_last_id_is_a_layout_the_reader_knows(tmp_path):
    from pyflightstream.workspace import sector_to_wheel

    source = build_blunt_sector(tmp_path)
    lines = source.read_text().split("\n")
    at = lines.index("$MESH_START$") + 2
    assert lines[at] == "4"
    lines[at] = "5"
    odd = tmp_path / "odd_header.fsm"
    odd.write_text("\n".join(lines))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert sector_to_wheel(
            odd, copies=COPIES, blades=["Blade1"], out=tmp_path / "w.fsm"
        ).written
    lines[at] = "3"
    odd.write_text("\n".join(lines))
    with pytest.warns(Warning, match="not recognized"):
        assert not sector_to_wheel(
            odd, copies=COPIES, blades=["Blade1"], out=tmp_path / "v.fsm"
        ).written


@pytest.mark.requirement("FR-3499")
@pytest.mark.parametrize(
    "change",
    [
        {"nose_radius_r": 10.0},
        {"nose_radius_r": 0.0},
        {"tip_radius": 0.0},
        {"tip_radius": -1.0},
    ],
)
def test_p0540_a_nose_kite_off_the_spinner_is_refused_on_the_body(tmp_path, change):
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace import power_off_body

    source = build_blunt_sector(tmp_path)
    out = tmp_path / "b.fsm"
    with pytest.raises(InputValueError, match="nose-radius-r"):
        power_off_body(source, blades=["Blade1"], copies=COPIES, out=out, **change)
    assert not out.exists()


@pytest.mark.requirement("FR-3499")
@pytest.mark.parametrize(
    "change",
    [
        {"nose_radius_r": 10.0},
        {"nose_radius_r": 0.0},
        {"root_margin_r": 0.3, "nose_radius_r": 0.32},
    ],
)
def test_p0540_rings_that_would_run_past_the_nose_kite_are_refused_on_the_sector(tmp_path, change):
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace import sector_remesh

    source = build_blunt_sector(tmp_path)
    out = tmp_path / "s.fsm"
    with pytest.raises(InputValueError, match="nose-radius-r"):
        sector_remesh(source, blades=["Blade1"], tip_radius=1.218, out=out, **ARGS, **change)
    assert not out.exists()


@pytest.mark.requirement("FR-3499")
def test_p0540_an_output_that_is_the_sector_itself_is_refused_by_every_verb(tmp_path):
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace import power_off_body, sector_remesh, sector_to_wheel
    from tests.tier1_offline.test_p0540_wheel import build_sector

    source = build_blunt_sector(tmp_path)
    before = source.read_bytes()
    calls = [
        lambda: sector_to_wheel(
            source, copies=COPIES, blades=["Blade1"], out=source, overwrite=True
        ),
        lambda: sector_remesh(source, blades=["Blade1"], out=source, overwrite=True, **ARGS),
        lambda: power_off_body(
            source, blades=["Blade1"], copies=COPIES, out=source, overwrite=True
        ),
    ]
    for call in calls:
        with pytest.raises(InputArtifactError, match="the sector itself"):
            call()
        assert source.read_bytes() == before
    sector = build_sector(tmp_path)
    obj_before = sector.obj.read_bytes()
    with pytest.raises(InputArtifactError, match="the sector itself"):
        sector_to_wheel(sector.obj, copies=6, blades=["Blade1"], out=sector.obj, overwrite=True)
    assert sector.obj.read_bytes() == obj_before


@pytest.mark.requirement("FR-3498")
def test_p0540_the_angle_of_a_two_blade_sector_survives_the_rounding_of_its_seams():
    from pyflightstream.workspace._sector_read import _seams

    rng = np.random.default_rng(1)
    wrong = []
    for _ in range(400):
        centre = rng.uniform(-math.pi, math.pi)
        theta = centre + np.linspace(-math.pi / 2, math.pi / 2, 9)
        radius = 0.3 + 0.2 * rng.random()
        q = np.c_[np.zeros(9), radius * np.cos(theta), radius * np.sin(theta)]
        found_centre, span = _seams(q, np.arange(9))
        gap = abs(math.remainder(found_centre - centre, 2.0 * math.pi))
        if abs(span - math.pi) > 1e-6 or gap > 1e-6:
            wrong.append((centre, span))
    assert not wrong


def _axis_off_the_origin(source: Path, shift: float) -> None:
    """Move the sector's nodes off the x axis, as a sector about another line sits."""
    lines = source.read_bytes().decode("latin-1").replace("\r\n", "\n").split("\n")
    at = lines.index("$MESH_START$") + 4 + 9 + 1 + 25
    values = [float(v) + shift for v in lines[at + 3].split(",") if v.strip()]
    lines[at + 3] = "".join(f"{v: .17E}," for v in values)
    source.write_bytes("\n".join(lines).encode("latin-1"))


@pytest.mark.requirement("FR-3498")
@pytest.mark.parametrize("verb", ["sector-remesh", "power-off-body"])
@pytest.mark.parametrize("shift", [0.1, 3.0])
def test_p0540_a_sector_off_the_origin_is_warned_by_name_at_the_command_line(
    tmp_path, capsys, verb, shift
):
    from pyflightstream.workspace.cli import main as workspace_main

    source = build_blunt_sector(tmp_path)
    _axis_off_the_origin(source, shift)
    extra = (
        ["--chord-cells", "12", "--le", "0.03", "--span-cell", "0.1", "--spinner-theta", "4"]
        if verb == "sector-remesh"
        else ["--copies", "6"]
    )
    out = tmp_path / "o.fsm"
    argv = ["geometry", verb, str(source), "--blades", "Blade1", *extra, "--out", str(out)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert workspace_main(argv) == 2
    assert not out.exists() and not list(tmp_path.glob("*.part"))


@pytest.mark.requirement("FR-3498")
def test_p0540_a_sector_off_the_origin_names_the_origin_in_its_warning(tmp_path):
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.workspace import power_off_body

    source = build_blunt_sector(tmp_path)
    _axis_off_the_origin(source, 0.1)
    with pytest.warns(PyflightstreamWarning, match="through the origin"):
        result = power_off_body(source, blades=["Blade1"], copies=6, out=tmp_path / "o.fsm")
    assert not result.written


@pytest.mark.requirement("FR-3499")
@pytest.mark.parametrize(("row", "value"), [(10, "999999"), (2, "999999"), (2, "0")])
def test_p0540_a_row_that_names_a_face_or_node_outside_the_block_is_not_read(tmp_path, row, value):
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.workspace import sector_remesh, sector_to_wheel

    source = build_blunt_sector(tmp_path)
    lines = source.read_bytes().decode("latin-1").replace("\r\n", "\n").split("\n")
    at = lines.index("$MESH_START$") + 4 + 9 + 1 + row
    cells = [c for c in lines[at].split(",") if c.strip()]
    cells[0] = value
    lines[at] = "".join(f"{c}," for c in cells)
    source.write_bytes("\n".join(lines).encode("latin-1"))
    out = tmp_path / "o.fsm"
    with pytest.warns(PyflightstreamWarning, match="outside"):
        assert not sector_remesh(source, blades=["Blade1"], out=out, **ARGS).written
    with pytest.warns(PyflightstreamWarning, match="outside"):
        assert not sector_to_wheel(source, copies=COPIES, blades=["Blade1"], out=out).written
    assert not out.exists()


@pytest.mark.requirement("FR-3499")
@pytest.mark.parametrize(
    ("change", "text"),
    [
        ({"span_cell": 0.0}, "--span-cell"),
        ({"span_cell": math.nan}, "--span-cell"),
        ({"tip_length": math.inf}, "--tip-length"),
        ({"tip_radius": math.nan}, "--tip-radius"),
        ({"tip_ratio": 0.0}, "--tip-ratio"),
        ({"tip_ratio": 1.0}, "--tip-ratio"),
        ({"le": 0.0}, "larger le"),
        ({"le": -0.1}, "larger le"),
        ({"le": math.nan}, "larger le"),
        ({"spinner_theta": 14}, "--spinner-theta"),
    ],
)
def test_p0540_an_option_no_mesh_can_follow_is_refused_in_words_on_the_sector(
    tmp_path, change, text
):
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace import sector_remesh

    source = build_blunt_sector(tmp_path)
    out = tmp_path / "s.fsm"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(InputValueError, match=text):
            sector_remesh(source, blades=["Blade1"], out=out, **{**ARGS, **change})
    assert not out.exists()


@pytest.mark.requirement("FR-3499")
@pytest.mark.parametrize(
    "change",
    [
        {"spinner_rings": 0},
        {"spinner_rings": -1},
        {"nacelle_cells": 0},
        {"nacelle_cells": -1},
    ],
)
def test_p0540_the_body_checks_the_counts_it_is_given(tmp_path, change):
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace import power_off_body

    source = build_blunt_sector(tmp_path)
    out = tmp_path / "b.fsm"
    with pytest.raises(InputValueError, match="must be 1 or more"):
        power_off_body(source, blades=["Blade1"], copies=COPIES, out=out, **change)
    assert not out.exists()
