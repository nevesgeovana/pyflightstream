"""P0440-LAYOUT (FR-932, FR-921, PFS-2151): touching grid families are resampled as one layout.

The source is synthetic, a tail in miniature built on one structured surface
of 13 chordwise by 18 spanwise cells, its numbering shuffled: ``W``, a sheet
(the stabilizer) over spanwise cells 10 to 18; ``C``, a sheet (the centre
strip) over 3 to 7; ``J``, two junction strips over 0 to 3 and 7 to 10, one
family and so a multiblock grid of two patches; and ``T``, a strip of
triangles beyond W's tip that no factor selects. The trailing edge is the
chordwise index 0 line of every family. W and J share a station, C and J
two. Before 0.44.0 only the first of them in the source's order stayed a grid.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import refine_mesh
from tests.p0380_mesh_fixtures import (
    Composite,
    face_coordinates,
    l_sheet,
    read_mesh,
    write_source,
)

NX = 13  # chordwise cells
BANDS = {"W": [(10, 18)], "C": [(3, 7)], "J": [(0, 3), (7, 10)]}
NY = 18
FACTOR = 0.76923


def _point(i, j):
    """Return the surface at the (fractional) indices: chordwise i from the trailing edge."""
    u, v = np.asarray(i, float) / NX, np.asarray(j, float) / NY
    x = 1.0 - u - 0.05 * u**3 + 0.1 * v
    y = 2.0 * v + 0.05 * v**2
    z = 0.06 * np.sin(np.pi * u) * (1.0 - 0.3 * v)
    return np.stack(np.broadcast_arrays(x, y, z), axis=-1)


def tail(*, strip: bool = True, seed: int = 7) -> Composite:
    """Return the tail: W, C, J (and T beyond W), numbering shuffled, faces row by row."""
    rows = NY + (5 if strip else 0)
    used = [(i, j) for j in range(rows + 1) for i in range(NX + 1)]
    perm = np.random.default_rng(seed).permutation(len(used))
    number = {ij: int(perm[n]) for n, ij in enumerate(used)}
    verts = np.empty((len(used), 3))
    for (i, j), n in number.items():
        verts[n] = _point(i, j)
    families: dict[str, list[list[int]]] = {}
    for name, bands in BANDS.items():
        families[name] = [
            [number[(i, j)], number[(i + 1, j)], number[(i + 1, j + 1)], number[(i, j + 1)]]
            for lo, hi in bands
            for j in range(lo, hi)
            for i in range(NX)
        ]
    if strip:
        tri = []
        for j in range(NY, rows):
            for i in range(NX):
                a, b = number[(i, j)], number[(i + 1, j)]
                c, d = number[(i + 1, j + 1)], number[(i, j + 1)]
                tri += [[a, b, c], [a, c, d]] if (i + j) % 2 else [[a, b, d], [b, c, d]]
        families["T"] = tri
    te = 0.5 * (_point(0, np.arange(NY)) + _point(0, np.arange(1, NY + 1)))
    return Composite(verts, families, te, {})


def _source(tmp_path: Path, refine_toml: str | None = None, **kwargs) -> Path:
    return write_source(tmp_path / "src", "tail", tail(**kwargs), refine_toml=refine_toml)


def _nodes(faces) -> set[int]:
    return {v for f in faces for v in f}


def _centroids(verts, faces) -> np.ndarray:
    return np.array([verts[f].mean(axis=0) for f in faces])


def _in_source_order(level_verts, level_faces, source_verts, source_faces) -> bool:
    """Return whether the level's faces follow their nearest source faces in order (FR-921)."""
    old = _centroids(source_verts, source_faces)
    new = _centroids(level_verts, level_faces)
    nearest = np.argmin(np.linalg.norm(new[:, None, :] - old[None, :, :], axis=2), axis=1)
    return bool(np.all(np.diff(nearest) >= 0))


def _gates(level) -> dict[str, str]:
    return {f"{g.name} {g.family}": g.verdict for g in level.audit.gates}


GROUP = ["W", "C", "J"]


def test_three_touching_grids_stay_grids_in_their_own_families_and_conform(tmp_path):
    """P0440-LAYOUT (FR-932, FR-921, FR-936): W, C and J at 0.76923 are all grids, conforming.

    Each is a grid of its own family that names the other two under
    ``grouped_with``; every curve two of them share holds round(13 f) + 1 = 11
    nodes from both sides; the audit's gates G1 to G5 pass, G5 judged on each
    pair of families that shared nodes in the source; each family's faces follow its own
    source faces in order; T, unchanged, is remeshed only in its band beside W.
    Controls: the order check fails on a family's faces reversed; before
    PFS-2151 C and J were remeshed.
    """
    src = _source(tmp_path)
    level = refine_mesh(src, FACTOR, families=GROUP)
    report = level.report
    for name in GROUP:
        assert report[name]["method"] == "grid", report[name]
        assert report[name]["grouped_with"] == [n for n in GROUP if n != name]
    assert report["J"]["layout"] == "multiblock" and report["W"]["layout"] == "sheet"
    assert report["T"]["method"] == "unchanged" and report["T"]["band"] > 0
    gates = _gates(level)
    assert all(g.passed for g in level.audit.gates), gates
    assert {"G5 W and J", "G5 C and J", "G5 W and T"} <= set(gates), gates
    sv, sf = read_mesh(src)
    lv, lf = read_mesh(level.obj)
    for a, b, curves in (("W", "J", 1), ("C", "J", 2)):
        assert len(_nodes(lf[a]) & _nodes(lf[b])) == curves * (round(NX * FACTOR) + 1)
        assert len(_nodes(sf[a]) & _nodes(sf[b])) == curves * (NX + 1)
    assert not _nodes(lf["W"]) & _nodes(lf["C"])
    for name in GROUP:
        assert len(lf[name]) < len(sf[name])
        assert _in_source_order(lv, lf[name], sv, sf[name]), name
    assert not _in_source_order(lv, lf["C"][::-1], sv, sf["C"])


def test_at_factor_one_each_grouped_family_is_its_source_face_for_face(tmp_path):
    """P0440-LAYOUT (FR-921, FR-938): at factor 1 every family is the source, G6 passing.

    Control: the level's faces of J rotated by one vertex differ from the source's.
    """
    src = _source(tmp_path, strip=False)
    level = refine_mesh(src, 1.0)
    sv, sf = read_mesh(src)
    lv, lf = read_mesh(level.obj)
    for name in GROUP:
        assert face_coordinates(lv, lf[name]) == face_coordinates(sv, sf[name]), name
    rotated = [f[1:] + f[:1] for f in lf["J"]]
    assert face_coordinates(lv, rotated) != face_coordinates(sv, sf["J"])
    gates = _gates(level)
    assert all(g.passed for g in level.audit.gates) and "G6 W" in gates, gates


def test_two_grids_giving_a_shared_curve_different_counts_are_refused_naming_both(tmp_path):
    """P0440-LAYOUT (FR-932, FR-925): J at 0.5 beside W and C at 0.76923 is refused.

    A station of 13 intervals would hold round(13 x 0.76923) = 10 intervals on
    one side and round(13 x 0.5) = 6 on the other; the refusal names both
    families, the curve and both counts, and nothing is written. Control: J at
    0.76923 is accepted (the test above).
    """
    toml = (
        f"[families.W]\nfactor = {FACTOR}\n\n[families.C]\nfactor = {FACTOR}\n\n"
        "[families.J]\nfactor = 0.5\n"
    )
    src = _source(tmp_path, toml, strip=False)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src)
    text = str(caught.value)
    assert text.startswith(f"{src} families ") and " and J: the curve they share from node " in text
    assert "of 13 source intervals, would hold 10 intervals as " in text
    assert "and 6 as J is" in text and text.endswith("Nothing was written.")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["src"]


# ------------------------------------------- PFS-2150 chordwise and spanwise on a multiblock


def _pairs(entry) -> list[list[tuple[int, int]]]:
    """Return each patch's (before, after) interval pairs, its two directions sorted."""
    return sorted(sorted([tuple(b["rows"]), tuple(b["columns"])]) for b in entry["blocks"])


def test_the_junction_coarsened_chordwise_only_keeps_its_spanwise_counts(tmp_path):
    """P0440-LAYOUT (FR-915, FR-932, PFS-2150): J at chordwise 0.76923, spanwise 1.

    J's arcs are told chordwise or spanwise from its trailing edge: its
    spanwise arcs (3 intervals across each strip, along the trailing edge)
    keep 3, its chordwise arcs (13 intervals) take 10, and so do the curves it
    shares with W and C at 0.76923; the level conforms and its gates pass.
    Control: J at factor 0.76923 in both directions takes 2 across each strip.
    """
    toml = (
        f"[families.W]\nfactor = {FACTOR}\n\n[families.C]\nfactor = {FACTOR}\n\n"
        f"[families.J]\nchordwise = {FACTOR}\nspanwise = 1\n"
    )
    src = _source(tmp_path, toml, strip=False)
    level = refine_mesh(src)
    report = level.report
    assert _pairs(report["J"]) == [[(3, 3), (13, 10)]] * 2, report["J"]
    assert _pairs(report["C"]) == [[(4, 3), (13, 10)]]
    assert _pairs(report["W"]) == [[(8, 6), (13, 10)]]
    assert report["J"]["kept_sides"] == []
    assert all(g.passed for g in level.audit.gates), _gates(level)
    lv, lf = read_mesh(level.obj)
    assert len(_nodes(lf["C"]) & _nodes(lf["J"])) == 2 * (round(NX * FACTOR) + 1)
    both = refine_mesh(src, FACTOR, out_dir=tmp_path / "both").report
    assert _pairs(both["J"]) == [[(3, 2), (13, 10)]] * 2


def _l_with_trailing_edge(shear: float = 0.0) -> Composite:
    """Return the L-shaped multiblock sheet M with its j = 0 row as the trailing edge."""
    sheet = l_sheet()
    verts = sheet.verts.copy()
    verts[:, 0] += shear * verts[:, 1]
    row = sorted((v for v, (i, j) in sheet.place.items() if j == 0), key=lambda v: sheet.place[v])
    te = 0.5 * (verts[row[:-1]] + verts[row[1:]])
    return Composite(verts, {"M": sheet.faces}, te, {})


def test_a_lone_multiblock_takes_chordwise_and_spanwise_from_its_trailing_edge(tmp_path):
    """P0440-LAYOUT (FR-915, PFS-2150): the L-shaped multiblock M at chordwise 0.5, spanwise 1.

    Its trailing edge runs along its rows, so every row arc is spanwise and
    keeps its count, every column arc is chordwise and halves. Control: the
    single factor 0.5 halves both, as before.
    """
    src = write_source(tmp_path / "src", "plate", _l_with_trailing_edge())
    level = refine_mesh(src, chordwise=0.5, spanwise=1.0, out_dir=tmp_path / "a")
    assert _pairs(level.report["M"]) == [
        [(4, 2), (5, 5)],
        [(4, 2), (7, 7)],
        [(6, 3), (7, 7)],
    ], level.report["M"]
    assert all(g.passed for g in level.audit.gates), _gates(level)
    half = refine_mesh(src, 0.5, out_dir=tmp_path / "b").report["M"]
    assert _pairs(half) == [[(4, 2), (5, 2)], [(4, 2), (7, 4)], [(6, 3), (7, 4)]]


def test_a_patch_whose_two_directions_cannot_be_told_apart_is_refused_naming_it(tmp_path):
    """P0440-LAYOUT (FR-915, FR-925, PFS-2150): M sheared until its columns run near the edge.

    Sheared by 1.5, its columns run within 35 degrees of the trailing edge,
    like its rows, so patch 1 has no chordwise direction: chordwise and
    spanwise are refused naming the family and the patch, nothing written.
    Control: the single factor is accepted on the sheared M.
    """
    src = write_source(tmp_path / "src", "plate", _l_with_trailing_edge(shear=1.5))
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, chordwise=0.5, spanwise=1.0, out_dir=tmp_path / "a")
    text = str(caught.value)
    assert text.startswith(f"{src} family M: chordwise and spanwise cannot be told apart on ")
    assert "patch 1 of a multiblock of 3 four-sided patches" in text
    assert "its rows run spanwise and its columns spanwise" in text
    assert text.endswith("Nothing was written.") and not (tmp_path / "a").exists()
    assert refine_mesh(src, 0.5, out_dir=tmp_path / "b").report["M"]["method"] == "grid"
