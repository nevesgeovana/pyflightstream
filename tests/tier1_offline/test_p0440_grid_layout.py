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
from tests.p0380_mesh_fixtures import Composite, face_coordinates, read_mesh, write_source

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
