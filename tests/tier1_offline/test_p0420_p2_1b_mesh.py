"""Tier 1, 0.42.0 P2-1b: the trailing-edge points file, the none route and the mesh audit's inputs.

Pipeline role: guards on :mod:`pyflightstream.workspace._refine` (FR-424, FR-426, FR-937).
Every mesh is a strip of two quadrilaterals whose trailing edge is the edge
at x = 2; each defect is shown refused beside a control that is accepted.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.workspace import MeshAudit, audit_mesh, refine_mesh
from pyflightstream.workspace._refine._obj import read_obj, read_te, te_file, te_route

OBJ = "v 0 0 0\nv 1 0 0\nv 2 0 0\nv 0 1 0\nv 1 1 0\nv 2 1 0\ng W\nf 1 2 5 4\nf 2 3 6 5\n"


def _mesh(folder: Path, te_rows: list[str] | None = None, boundaries: str = "") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    obj = folder / "w.obj"
    obj.write_text(OBJ, encoding="utf-8")
    if te_rows is not None:
        (folder / "w.te.txt").write_text("\n".join(te_rows) + "\n", encoding="utf-8")
    if boundaries:
        (folder / "w.boundaries.toml").write_text(boundaries, encoding="utf-8")
    return obj


def _g4(obj: Path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        audit = audit_mesh(obj)
    return next(g for g in audit.gates if g.name == "G4"), audit


# ---------------------------------------------------------------- PFS-2130.065


def test_p0420_a_points_file_without_its_unit_line_is_refused_before_a_point_is_read(tmp_path):
    """PFS-2130.065: a first row that is not a unit is refused, not read as a lost point."""
    lost = tmp_path / "lost.te.txt"
    lost.write_text("2,0.5,0\n2,0.6,0\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match=r"lost\.te\.txt.*not a length unit.*METER"):
        read_te(lost)
    ok = tmp_path / "ok.te.txt"
    ok.write_text(" millimeter \n2,0.5,0\n2,0.6,0\n", encoding="utf-8")
    unit, points = read_te(ok)
    assert unit == "millimeter" and len(points) == 2


# ---------------------------------------------------------------- PFS-2130.067


def test_p0420_read_obj_refuses_a_missing_mesh_as_the_audit_does(tmp_path):
    """PFS-2130.067: read_obj, refine_mesh and audit_mesh refuse a missing path alike."""
    for path in (tmp_path / "nope.obj", tmp_path):
        with pytest.raises(InputArtifactError, match="no such OBJ file"):
            read_obj(path)
        with pytest.raises(InputArtifactError, match="no such OBJ file"):
            refine_mesh(path, 2)
        with pytest.raises(InputArtifactError, match="no such OBJ file"):
            audit_mesh(path)
    assert read_obj(_mesh(tmp_path / "ok")).families["W"]


# ---------------------------------------------------------------- PFS-2119.063


def test_p0420_none_true_stops_a_te_txt_beside_the_mesh_being_read(tmp_path):
    """PFS-2119.063: ``none = true`` carries in the route and te_file returns None for it."""
    rows = ["METER", "2,0.5,0"]
    stale = _mesh(tmp_path / "stale", rows, 'boundaries = ["W"]\n\n[trailing_edges]\nnone = true\n')
    assert te_route(stale).none and te_file(stale) is None
    g4, _ = _g4(stale)
    assert g4.values["points"] == 0
    control = _mesh(tmp_path / "control", rows, 'boundaries = ["W"]\n')
    assert not te_route(control).none and te_file(control) == control.with_suffix(".te.txt")
    assert _g4(control)[0].values["points"] == 1
    assert ("its trailing-edge points file", stale.with_suffix(".te.txt")) not in (
        MeshAudit.files_read(stale)
    )


# ---------------------------------------------------------------- PFS-2130.068


def test_p0420_g4_fails_two_points_on_one_mesh_edge(tmp_path):
    """PFS-2130.068: a duplicated row is two points on one edge and fails the gate."""
    once = _mesh(tmp_path / "once", ["METER", "2,0.5,0"])
    g4, _ = _g4(once)
    assert g4.values["points_sharing_an_edge"] == 0 and g4.verdict == "pass"
    twice = _mesh(tmp_path / "twice", ["METER", "2,0.5,0", "2,0.5,0"])
    g4, audit = _g4(twice)
    assert g4.values["points"] == 2 and g4.values["points_on_edges"] == 2
    assert g4.values["points_sharing_an_edge"] == 1
    assert g4.verdict == "fail" and not audit.passed


# ---------------------------------------------------------------- PFS-2123.004


def test_p0420_files_read_is_the_list_the_audit_refuses_by_and_write_csv_guards_it(tmp_path):
    """PFS-2123.004: one list; write_csv refuses a file the audit reads or wrote."""
    obj = _mesh(tmp_path / "m", ["METER", "2,0.5,0"], 'boundaries = ["W"]\n')
    record = obj.with_name("w.refine.json")
    record.write_text("{}", encoding="utf-8")
    read = MeshAudit.files_read(obj)
    assert ("its refinement record", record) in read
    _, audit = _g4(obj)
    for _, path in [*read, ("the audit JSON", audit.path)]:
        if path.exists():
            before = path.read_bytes()
            with pytest.raises(InputArtifactError, match="Nothing was written"):
                audit.write_csv(path)
            assert path.read_bytes() == before
    out = tmp_path / "figures.csv"
    assert audit.write_csv(out) == out and out.is_file()


# ---------------------------------------------------------------- PFS-2119.062


def test_p0420_a_sheet_with_no_trailing_edge_is_refused_for_that_reason():
    """PFS-2119.062: a sheet needs a trailing edge; the refusal says so, not 'not a grid line'."""
    from pyflightstream.workspace._refine._grid import recover_grid
    from tests.p0380_mesh_fixtures import sheet_quads

    sheet = sheet_quads()
    said = recover_grid(sheet.verts, sheet.faces, set())
    assert isinstance(said, str) and said.startswith("a sheet needs a trailing edge")
    assert "only a smooth tube is recovered without one" in said
    # the control: with its trailing edge the same sheet is a grid
    assert not isinstance(recover_grid(sheet.verts, sheet.faces, sheet.te), str)


# ---------------------------------------------------------------- F-1517


def test_p0430_f1517_an_obj_that_is_not_utf8_is_refused_not_merged_by_replacement(tmp_path):
    """F-1517: family labels differing only in a non-UTF-8 byte are not merged into one."""
    bad = tmp_path / "bad.obj"
    bad.write_bytes(b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\ng W\xe9a\nf 1 2 3\ng W\xe9b\nf 1 3 4\n")
    with pytest.raises(InputArtifactError, match=r"bad\.obj.*not UTF-8"):
        read_obj(bad)
    good = tmp_path / "good.obj"
    good.write_bytes(bad.read_bytes().replace(b"\xe9", "é".encode()))
    assert sorted(read_obj(good).families) == ["Wéa", "Wéb"]
