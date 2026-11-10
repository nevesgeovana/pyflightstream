"""A written face has a parameter-space outer boundary flagged 2D parametric (PFS-2220, G13D).

The licensed record ``data/g13d-reads.json`` (build 26.127) isolates why a file the writer wrote
read as an empty model when imported directly: the curves a 142 names by BPTR carried entity use
flag 00, and a face with no BPTR curve (a natural boundary, N1 = 0, or a plane) is never read. The
structural tests read the written file only; no test runs the solver.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from pyflightstream.workspace._iges_write import read_iges
from tests.tier1_offline._kernel_support import kernel_or_skip

RECORD = Path(__file__).parent / "data" / "g13d-reads.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture
def kernel():
    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    k = open_kernel("test")
    try:
        yield k
    finally:
        k.close()


def _use(entity) -> str:
    """The entity use flag: digits 5 and 6 of the directory entry status number (field 9)."""
    return entity["d1"][8][4:6]


def _outer_boundaries(document):
    """Per 144: its outer 142 (None when N1 = 0) and the curves its BPTR reaches."""
    by_id = {e["id"]: e for e in document["entities"]}
    out = []
    for face in (e for e in document["entities"] if e["type"] == 144):
        values = face["parameters"]
        outer = by_id.get(int(values[4] or 0)) if int(values[2] or 0) else None
        curves = []
        if outer is not None:
            stack = [int(outer["parameters"][3] or 0)]
            while stack:
                member = by_id.get(stack.pop())
                if member is None:
                    continue
                curves.append(member)
                if member["type"] == 102:
                    p = member["parameters"]
                    stack += [int(v) for v in p[2 : 2 + int(p[1])]]
        out.append((outer, curves))
    return out


def _assert_readable(path):
    boundaries = _outer_boundaries(read_iges(path))
    assert boundaries
    for outer, curves in boundaries:
        assert outer is not None, "a 144 with N1 = 0 (no outer 142) is read as no face"
        assert curves, "an outer 142 with no BPTR curve is read as no face"
        assert [_use(c) for c in curves] == ["05"] * len(curves)
        assert _use(outer) == "00"


def test_record_isolates_the_use_flag_of_the_bptr_curves(record):
    """One field moved at a time: only the BPTR members' use flag turns the read on and off."""
    v = record["isolation_p6"]["variants"]
    written = record["isolation_p6"]["written_area"]
    assert v["D"][1]["triangles"] == 0 and v["C_bptrUse00"][1]["triangles"] == 0
    assert v["C"][1]["area"] == pytest.approx(written, rel=1e-3)
    assert v["D_bptrMembersOnly05"][1]["area"] == pytest.approx(written, rel=1e-3)
    for neutral in ("D_142use00", "D_bptr102only05", "D_406use00"):
        assert v[neutral][1]["triangles"] == 0, neutral
    assert v["C_142use05"][1]["area"] == pytest.approx(written, rel=1e-3)


def test_record_a_face_with_no_parameter_space_outer_boundary_is_not_read(record):
    p9 = record["isolation_p9"]
    assert p9["P9a_conv"][1]["triangles"] > 0
    assert p9["C9a_N1zero"][1]["triangles"] == 0
    assert p9["D9b_flagged"][1]["area"] == pytest.approx(2 * math.pi * 0.5 * 2.0, rel=1e-3)


def test_record_every_probe_with_a_parameter_space_preference_reads_after_the_fix(record):
    """P1, P3 to P9 read directly within 0.1 percent; P2 (PREF 2, model space) is not read."""
    items = record["after_fix_direct"]
    for name, item in items.items():
        if item["preference"] == 2:
            assert item["triangles"] == 0, name
        else:
            assert item["ratio"] == pytest.approx(1.0, abs=1e-3), name
    assert {n for n, i in items.items() if i["preference"] != 2} >= {
        "P1", "P3", "P4", "P5", "P6", "P7", "P8", "P9a_rational", "P9b_revolution"
    }  # fmt: skip
    pref = record["pref_p1_after_fix"]
    assert [pref[k]["triangles"] > 0 for k in ("P1_pref0", "P1_pref1", "P2_pref2", "P1_pref3")] == [
        True, True, False, True
    ]  # fmt: skip


def test_trimmed_faces_flag_their_parameter_space_curves_05(kernel, tmp_path):
    net = [[(2.0 * i / 5.0, 3.0 * j, 0.1 * math.sin(i)) for j in range(2)] for i in range(6)]
    base = kernel.add_bspline_surface(
        net, knots_u=[0.0, 1.0], knots_v=[0.0, 1.0], mult_u=[6, 6], mult_v=[2, 2], deg_u=5, deg_v=1
    )  # fmt: skip
    box = [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]
    face = kernel.add_trimmed_face(base, [[[box[k], box[(k + 1) % 4]] for k in range(4)]])
    kernel.remove([base])
    path = tmp_path / "trimmed.igs"
    kernel.export_iges({"WING": [face]}, path)
    _assert_readable(path)


def test_natural_and_planar_faces_are_written_with_a_parameter_space_boundary(kernel, tmp_path):
    net = [[(float(i), float(j), 0.1 * i * j) for j in range(2)] for i in range(4)]
    skin = kernel.add_bspline_surface(
        net, knots_u=[0.0, 1.0], knots_v=[0.0, 1.0], mult_u=[4, 4], mult_v=[2, 2], deg_u=3, deg_v=1
    )  # fmt: skip
    plate = kernel.add_planar_face(
        [(0.0, 0.0, 2.0), (1.0, 0.0, 2.0), (1.0, 1.0, 2.0), (0.0, 1.0, 2.0)]
    )
    before = kernel.faces()
    areas = sorted([kernel.area(skin), kernel.area(plate)])
    path = tmp_path / "natural.igs"
    kernel.export_iges({"SKIN": [skin], "PLATE": [plate]}, path)
    _assert_readable(path)
    assert kernel.faces() == before  # the B-spline copies left the model
    named = kernel.import_iges(path)
    assert sorted(named.names) == ["PLATE", "SKIN"]
    assert sorted(kernel.area(f) for f in named.faces) == pytest.approx(areas, rel=1e-6)


@pytest.mark.parametrize("planted", ["none", "use_00", "pref_2", "bptr_0", "n1_0"])
def test_r21_004_the_gate_warns_on_a_boundary_the_direct_import_reads_as_no_face(
    kernel, tmp_path, planted
):
    """Each condition of the record, planted alone in a written file, is warned as profile.trim."""
    from pyflightstream._textio import write_text
    from pyflightstream.workspace._geom_gate import check_profile
    from pyflightstream.workspace._iges_write import serialize_iges

    net = [[(float(i), float(j), 0.1 * i * j) for j in range(4)] for i in range(4)]
    skin = kernel.add_bspline_surface(
        net, knots_u=[0.0, 1.0], knots_v=[0.0, 1.0], mult_u=[4, 4], mult_v=[4, 4], deg_u=3, deg_v=3
    )  # fmt: skip
    path = tmp_path / "skin.igs"
    kernel.export_iges({"SKIN": [skin]}, path)
    document = read_iges(path)
    ((outer, curves),) = _outer_boundaries(document)
    face = next(e for e in document["entities"] if e["type"] == 144)
    if planted == "use_00":
        curves[0]["d1"][8] = curves[0]["d1"][8][:4] + "00" + curves[0]["d1"][8][6:]
    elif planted == "pref_2":
        outer["parameters"][5] = "2"
    elif planted == "bptr_0":
        outer["parameters"][3] = "0"
    elif planted == "n1_0":
        face["parameters"][2] = "0"
        face["parameters"][4] = "0"
    planted_path = tmp_path / f"{planted}.igs"
    write_text(planted_path, serialize_iges(document), encoding="ascii")
    trims = [f for f in check_profile(planted_path).findings if f.check == "profile.trim"]
    if planted == "none":
        assert trims == []
    else:
        assert [f.severity for f in trims] == ["warn"] and "iges-convert" in trims[0].detail
