"""P0380-DUMMY (FR-425 R1 to R5): a grid's shared nodes become its neighbours', and components.

Every source is synthetic (tests/p0380_mesh_fixtures.py): the cambered sheet
grid ``G``; ``T``, a strip of triangles (no grid) sharing G's tip station
node for node; ``U``, a strip of triangles sharing T's last row only, so it
touches T and never G; and for R1 ``G2``, a second grid of quadrilaterals
sharing G's tip station. Each behaviour is also run with the step it rests on
taken away or on a planted input, so a check that accepts everything cannot
pass.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run import cli
from pyflightstream.workspace import refine_mesh
from tests.p0380_mesh_fixtures import (
    face_coordinates,
    open_loop_count,
    open_loops,
    read_mesh,
    sheet_with_strips,
    write_source,
)

#: The row spacings of T beyond G's tip station, growing so a moved node shows.
STRIP = (0.03, 0.04, 0.05, 0.065, 0.08)
GTU = (("T", "tri", STRIP), ("U", "tri", (0.1, 0.1)))
GG = (("G2", "quad", (0.05, 0.05, 0.05)),)
#: The y of G's tip station, the curve G shares with T (and with G2).
TIP = 2.0


def _source(tmp_path: Path, strips=GTU, *, refine_toml=None, first=None) -> Path:
    """Write ``<tmp>/src/wing.obj``; ``first`` names a family written before the others."""
    mesh = sheet_with_strips(strips)
    if first is not None:
        mesh.families = {first: mesh.families[first]} | {
            n: f for n, f in mesh.families.items() if n != first
        }
    return write_source(tmp_path / "src", "wing", mesh, refine_toml=refine_toml)


def _left(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.name != "src")


def _nodes(faces) -> set[int]:
    return {v for f in faces for v in f}


def _all(families) -> list[list[int]]:
    return [f for fs in families.values() for f in fs]


def _refused(tmp_path: Path, src: Path, capsys, *args, **kwargs) -> str:
    """Return the text of a refusal, the same from the command, with nothing written."""
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, *args, **kwargs)
    text = str(caught.value)
    assert text.endswith("Nothing was written.") and _left(tmp_path) == []
    capsys.readouterr()
    argv = [str(a) for a in args]
    if kwargs.get("families"):
        argv += ["--families", ",".join(kwargs["families"])]
    assert cli.main(["refine", str(src), *argv]) == 2
    assert text in capsys.readouterr().err and _left(tmp_path) == []
    return text


# --------------------------------------------------------- R1 grids first


def test_r1_a_second_grid_sharing_nodes_is_remeshed_under_auto(tmp_path):
    """P0380-DUMMY (FR-425 R1): G is refined as a grid first, G2 sharing its nodes is remeshed.

    Controls: G2 alone is refined as a grid (it is one), and with G2 written
    first in the source it is G that is remeshed, naming G2.
    """
    src = _source(tmp_path, GG)
    report = refine_mesh(src, 2.0).report
    assert report["G"]["method"] == "grid"
    assert (report["G2"]["method"], report["G2"]["reason"]) == (
        "remesh",
        "shares nodes with the grid G",
    )
    alone = refine_mesh(src, 2.0, families=["G2"]).report
    assert alone["G2"]["method"] == "grid" and alone["G"]["method"] == "unchanged"
    swapped = refine_mesh(_source(tmp_path / "swapped", GG, first="G2"), 2.0).report
    assert swapped["G2"]["method"] == "grid"
    assert swapped["G"]["reason"] == "shares nodes with the grid G2"


def test_r1_method_grid_on_the_second_grid_is_refused_naming_both(tmp_path, capsys):
    """P0380-DUMMY (FR-425 R1; FR-424 R11): ``grid`` on G2 is refused naming G2 and G.

    Control: ``grid`` on G2 with G not refined is accepted.
    """
    toml = '[families.G]\nfactor = 2\n\n[families.G2]\nfactor = 2\nmethod = "grid"\n'
    src = _source(tmp_path, GG, refine_toml=toml)
    text = _refused(tmp_path, src, capsys)
    assert text == (
        f"{src} family G2: method is grid and it shares nodes with G, refined as a grid first. "
        "Nothing was written."
    )
    src.with_name("wing.refine.toml").write_bytes(b'[families.G2]\nfactor = 2\nmethod = "grid"\n')
    assert refine_mesh(src).report["G2"]["method"] == "grid"


# ------------------------------------------- R2 the remeshed neighbour conforms


def _tip_nodes(verts: np.ndarray, faces) -> set[int]:
    """Return the nodes of the faces that lie on G's tip station."""
    return {v for v in _nodes(faces) if abs(verts[v, 1] - TIP) < 1e-12}


def test_r2_the_remeshed_neighbour_holds_exactly_the_grids_new_nodes(tmp_path):
    """P0380-DUMMY (FR-425 R2, R5): T, remeshed, shares every new node of G's tip and no other.

    The level welds G and T on the 37 nodes of G's refined tip station, and
    its open loops are the source's. Control: the source's G and T share
    19 nodes, so 18 of the 37 the level's share are G's new ones; the mutant
    of the commit message that drops the hand-over in the code leaves T on
    the 19 and the level with 20 open loops, and fails this test.
    """
    src = _source(tmp_path)
    sv, sf = read_mesh(src)
    level = refine_mesh(src, 2.0, families=["G", "T"])
    lv, lf = read_mesh(level.obj)
    tip = _tip_nodes(lv, lf["G"])
    assert len(tip) == 2 * 18 + 1
    assert _nodes(lf["G"]) & _nodes(lf["T"]) == tip == _tip_nodes(lv, lf["T"])
    assert level.report["G"]["interfaces"] == {"T": "19 -> 37 nodes"}
    assert open_loop_count(_all(lf)) == open_loop_count(_all(sf)) == 1
    shared = {tuple(sv[v]) for v in _nodes(sf["G"]) & _nodes(sf["T"])}
    assert len(shared) == 19 and len({tuple(lv[v]) for v in tip} - shared) == 18


# ---------------------------------------- R3 the band of an unchanged neighbour


def _band(faces, seed: set[int], layers: int) -> set[int]:
    """Return the faces within ``layers`` face layers of the seed nodes (FR-425 R3).

    Layer one is the faces with a node on the curve; each next layer the
    faces sharing a node with the layers before.
    """
    nodes, chosen = set(seed), set()
    for _ in range(layers):
        new = {i for i, f in enumerate(faces) if i not in chosen and nodes & set(f)}
        chosen |= new
        nodes |= {v for i in new for v in faces[i]}
    return chosen


def _outside(src: Path, layers: int) -> tuple[list[tuple], int]:
    """Return T's source faces outside the band, in order, and the band's face count."""
    sv, sf = read_mesh(src)
    band = _band(sf["T"], _nodes(sf["G"]) & _nodes(sf["T"]), layers)
    coords = face_coordinates(sv, sf["T"])
    return [c for i, c in enumerate(coords) if i not in band], len(band)


def _kept_in_order(level_faces: list[tuple], outside: list[tuple]) -> bool:
    """Return whether every face outside the band is in the level, unchanged and in order."""
    wanted = set(outside)
    return [f for f in level_faces if f in wanted] == outside


def test_r3_an_unchanged_neighbour_changes_only_in_its_two_layer_band(tmp_path):
    """P0380-DUMMY (FR-425 R3): T, not asked to change, is remeshed only in a band of two layers.

    Outside the band T's faces equal the source's in coordinates, first
    vertex and order; U, beyond T, is untouched; refine.json names the band's
    face count. Controls: one face outside the band rotated by a vertex fails
    the check, and so does the same check against a band of one layer (the
    second layer was remeshed); the mutant of the commit message that cuts
    three layers in the code fails it too.
    """
    src = _source(tmp_path)
    outside, count = _outside(src, 2)
    assert count == 2 * 2 * 18 and len(outside) == 180 - count
    level = refine_mesh(src, 2.0, families=["G"])
    lv, lf = read_mesh(level.obj)
    got = face_coordinates(lv, lf["T"])
    assert _kept_in_order(got, outside)
    assert level.report["T"] == {"method": "unchanged", "band": count, "faces": 180}
    sv, sf = read_mesh(src)
    assert face_coordinates(lv, lf["U"]) == face_coordinates(sv, sf["U"])
    assert len(lf["T"]) > len(sf["T"])
    where = got.index(outside[len(outside) // 2])
    planted = [*got[:where], got[where][1:] + got[where][:1], *got[where + 1 :]]
    assert not _kept_in_order(planted, outside)
    assert not _kept_in_order(got, _outside(src, 1)[0])


@pytest.mark.parametrize(
    "kwargs",
    [{"factor": 1.0}, {"chordwise": 1.0, "spanwise": 2.0}],
    ids=["factor-1", "spanwise-only"],
)
def test_r3_when_the_grids_curve_nodes_do_not_change_nothing_of_the_neighbour_changes(
    tmp_path, kwargs
):
    """P0380-DUMMY (FR-425 R3): G's tip nodes unchanged leaves T and U as the source.

    At factor 1, and when only the spanwise direction is refined (the tip
    station is a knot and keeps its nodes), T and U are written face for face.
    The control is the band test above: chordwise 2 changes T.
    """
    src = _source(tmp_path)
    level = refine_mesh(src, families=["G"], **kwargs)
    sv, sf = read_mesh(src)
    lv, lf = read_mesh(level.obj)
    for name in ("T", "U"):
        assert face_coordinates(lv, lf[name]) == face_coordinates(sv, sf[name])
        assert level.report[name] == {"method": "copied"}
    assert "interfaces" not in level.report["G"]
    assert len(lf["G"]) == len(sf["G"]) * (2 if "spanwise" in kwargs else 1)


# ------------------------------------------------------------- R4 components


def test_r4_a_component_writes_its_members_as_one_family_in_the_sources_order(tmp_path):
    """P0380-DUMMY (FR-425 R4): ``Wing = ["T", "G"]`` writes Wing = G's faces then T's.

    The members are listed in reverse; the faces follow the source's family
    order. The boundaries file names Wing in place of G and T. Control: the
    listing's order (T then G) is not what is written. Refined, the
    component holds the level's G and T faces.
    """
    toml = '[components]\nWing = ["T", "G"]\n'
    src = _source(tmp_path, refine_toml=toml)
    level = refine_mesh(src, 1.0, families=["G"])
    sv, sf = read_mesh(src)
    lv, lf = read_mesh(level.obj)
    assert list(lf) == ["Wing", "U"]
    wing = face_coordinates(lv, lf["Wing"])
    assert wing == face_coordinates(sv, sf["G"] + sf["T"])
    assert wing != face_coordinates(sv, sf["T"] + sf["G"])
    side = (level.folder / f"{level.folder.name}.boundaries.toml").read_text(encoding="utf-8")
    assert 'boundaries = ["Wing", "U"]' in side
    refined = refine_mesh(src, 2.0, families=["G", "T"])
    counts = {n: len(f) for n, f in read_mesh(refined.obj)[1].items()}
    t_after = refined.report["T"]["faces_after"]
    assert counts == {"Wing": 576 + t_after, "U": 72}


@pytest.mark.parametrize(
    ("toml", "said"),
    [
        (
            '[components]\nWing = ["G", "Fin"]\n',
            "[components] Wing: the mesh holds no family 'Fin'; it holds G, T, U",
        ),
        (
            '[components]\nWing = ["G"]\nBody = ["G", "T"]\n',
            "[components] Body: family 'G' is also in component 'Wing'",
        ),
        (
            '[components]\nT = ["G", "U"]\n',
            "[components] T: a family of the mesh already has this name and is not a member",
        ),
    ],
    ids=["missing-member", "member-in-two", "name-clash"],
)
def test_r4_a_bad_component_is_refused_naming_the_component_and_the_family(
    tmp_path, capsys, toml, said
):
    """P0380-DUMMY (FR-425 R4; FR-424 R11): each refusal by both routes, nothing written.

    Control: a component named after one of its own members is accepted.
    """
    src = _source(tmp_path, refine_toml=toml)
    text = _refused(tmp_path, src, capsys, 1.0, families=["G"])
    assert text.startswith(str(src.with_name("wing.refine.toml"))) and said in text
    src.with_name("wing.refine.toml").write_bytes(b'[components]\nT = ["T", "U"]\n')
    level = refine_mesh(src, 1.0, families=["G"])
    assert list(read_mesh(level.obj)[1]) == ["G", "T"]


# ------------------------------------------------------------ R5 open loops


def _box(verts: np.ndarray, loop: set[int]) -> np.ndarray:
    return np.concatenate([verts[sorted(loop)].min(axis=0), verts[sorted(loop)].max(axis=0)])


@pytest.mark.parametrize("factor", [2.0, 0.5])
def test_r5_the_levels_open_loops_are_the_sources(tmp_path, factor):
    """P0380-DUMMY (FR-425 R5): refined or coarsened, the level has the source's open loops.

    Every family changes (G as a grid, T and U remeshed together and onto
    G's new nodes); the level has as many loops as the source, its loop
    spanning the source loop's box within 1e-3 of the size (a coarsened
    station drops the source's highest node). Control: one interior face
    taken out of the level opens a loop the same count sees.
    """
    src = _source(tmp_path)
    sv, sf = read_mesh(src)
    level = refine_mesh(src, factor)
    lv, lf = read_mesh(level.obj)
    source, got = open_loops(_all(sf)), open_loops(_all(lf))
    assert open_loop_count(_all(lf)) == open_loop_count(_all(sf)) == len(source) == 1
    size = float(np.linalg.norm(sv.max(axis=0) - sv.min(axis=0)))
    assert np.allclose(_box(lv, got[0]), _box(sv, source[0]), rtol=0.0, atol=1e-3 * size)
    faces = _all(lf)
    boundary = set().union(*got)
    inner = next(i for i, f in enumerate(faces) if not boundary & set(f))
    assert open_loop_count(faces[:inner] + faces[inner + 1 :]) == len(source) + 1
