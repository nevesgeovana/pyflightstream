"""0.58.0 PFS-2226 and PFS-2227 (review R32 of 0.57.0): a wing-body cut on the kernel where the
body seam lies in the plane of the wing's blunt trailing-edge base.

Written from the two acceptance sentences. A body box carries a seam on its side at the x of the
wing's trailing-edge base, so the base plane holds that seam, the configuration of CI run
43484118433. Every test runs the real kernel through the ``kernel`` fixture: it skips only where
gmsh cannot load, and fails instead where ``PYFS_REQUIRE_KERNEL=1`` (the Linux legs of CI set it).
Each test checks the faces the cut leaves (the base kept in two pieces split at the body side, a
footprint face cut out of the body side) and the junction (four curves, top, bottom, leading face
and base, closed), not only the value the cut was asked for.
"""

from __future__ import annotations

import math

import pytest

from tests.tier1_offline._kernel_support import kernel_or_skip
from tests.tier1_offline.test_p0570_g7r_assembly import box, quad

CUT = {"dominant": ["BODY"], "dominated": ["WING"], "operation": "cut"}
KINDS = {"BODY": "body", "WING": "lifting_surface"}
#: The default blunt base of the generator at unit chord, the base of the CI case.
DEFAULT_BASE_M = 2.52e-3


@pytest.fixture
def kernel():
    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    k = open_kernel("P0580 blunt base cut test")
    yield k
    k.close()


def body(seam_x):
    """A 4 x 2 x 2 body whose side y = 1 is two faces meeting at the seam x = ``seam_x``."""
    return box((0.0, -1.0, -1.0), (4.0, 1.0, 1.0), split_x=seam_x)


def blunt_wing(base, x=(1.5, 2.5), t=0.1, root=0.5, tip=3.0):
    """A wing of planar faces whose section closes from 2 ``t`` at the leading face to a blunt
    base of height ``base`` at the trailing x; the root at ``root`` is open, buried in the body."""
    x0, x1 = x
    lo, hi = -base / 2, base / 2
    corners = {
        "upper": ((x0, root, t), (x1, root, hi), (x1, tip, hi), (x0, tip, t)),
        "lower": ((x0, root, -t), (x0, tip, -t), (x1, tip, lo), (x1, root, lo)),
        "lead": ((x0, root, -t), (x0, root, t), (x0, tip, t), (x0, tip, -t)),
        "te_base": ((x1, root, lo), (x1, tip, lo), (x1, tip, hi), (x1, root, hi)),
        "tip": ((x0, tip, -t), (x0, tip, t), (x1, tip, hi), (x1, tip, lo)),
    }
    return [quad(*c, family) for family, c in corners.items()]


def cut(kernel, tmp_path, pieces):
    from pyflightstream.workspace._geom_assembly import Assembly

    asm = Assembly(kernel, pieces, [CUT], out=tmp_path, kinds=KINDS)
    for stage in ("S10.D1", "S10.D3"):
        record = asm.step(stage)
        assert not [c for c in record["checks"] if c["status"] == "failed"], record
    return asm, asm.step("S10.D4")


def assert_cut_keeps_the_base(asm, record, *, base, chord, t, inside, outside):
    """The cut passes every junction check, keeps the base in two faces of the expected areas
    and cuts a footprint face of the expected area out of the body side."""
    failed = [(c["id"], c["measured"]) for c in record["checks"] if c["status"] == "failed"]
    assert not failed, failed
    k = asm.k
    wing_areas = [k.area(f) for f in asm.faces["WING"]]
    for span in (inside, outside):
        expected = base * span
        assert any(a == pytest.approx(expected, rel=1e-3) for a in wing_areas), (
            f"no base face of {expected:.3e} m2 among {sorted(wing_areas)[:6]}"
        )
    # top, bottom, leading face and base: five faces cut in two at the body side, the tip whole
    assert len(wing_areas) == 9, sorted(wing_areas)
    footprint = chord * (2 * t + base) / 2
    body_areas = [k.area(f) for f in asm.faces["BODY"]]
    assert any(a == pytest.approx(footprint, rel=1e-6) for a in body_areas), sorted(body_areas)
    edges = asm._junction("BODY", "WING")
    assert len(edges) == 4, edges
    slope = math.hypot(chord, t - base / 2)
    length = sum(asm._length(e) for e in edges)
    assert length == pytest.approx(2 * slope + 2 * t + base, rel=1e-6)
    assert min(asm._length(e) for e in edges) == pytest.approx(base, rel=1e-3)


# ---- PFS-2227: the body seam in the plane of a blunt base ----------------------------------


def test_p0580_body_seam_in_the_plane_of_a_blunt_base_splits_and_closes(kernel, tmp_path):
    """P0580-SEAM-IN-BASE-PLANE: the CI case, a 2.52 mm base whose plane holds the body seam."""
    pieces = {"BODY": body(2.5), "WING": blunt_wing(DEFAULT_BASE_M)}
    asm, record = cut(kernel, tmp_path, pieces)
    assert_cut_keeps_the_base(
        asm, record, base=DEFAULT_BASE_M, chord=1.0, t=0.1, inside=0.5, outside=2.0
    )


def test_p0580_unequal_extents_a_small_wing_keeps_its_base_on_a_large_body(kernel, tmp_path):
    """P0580-SEAM-IN-BASE-PLANE-UNEQUAL-SCALE: the CI case at a hundredth of its size on the
    full-size body, so the two pieces' extents differ by 160. The base, 25.2 micrometres, lies
    below the fuzzy value the larger piece would set (2e-5 of 4 m, capped at 50 micrometres), so
    a cut taken relative to the larger piece merges the base and loses the junction across it."""
    base = DEFAULT_BASE_M / 100
    wing = blunt_wing(base, x=(2.49, 2.5), t=0.001, root=0.99, tip=1.015)
    asm, record = cut(kernel, tmp_path, {"BODY": body(2.5), "WING": wing})
    assert asm.extents["BODY"] / asm.extents["WING"] == pytest.approx(160, rel=1e-9)
    assert_cut_keeps_the_base(
        asm, record, base=base, chord=0.01, t=0.001, inside=0.01, outside=0.015
    )
