"""P0570-GSCALE: scale an OBJ mesh uniformly into a new output folder (PFS-2222).

Usage: pyfs-workspace geometry scale 0.5 --mesh part.obj --out scaled_folder
"""

import hashlib
import json
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, InputValueError
from pyflightstream.workspace.cli import main

OBJ = (
    b"# mesh with comments, v 9 9 9\n"
    b"mtllib part.mtl\n"
    b"g wing\n"
    b"v 1.0 2.0 3.0\n"
    b"v -1 0 4\n"
    b"v 3 -2 0\n"
    b"vn 0 0 1\n"
    b"vt 0.5 0.5\n"
    b"f 1//1 2//1 3//1\n"
    b"g tail\n"
    b"v 2 2 2 \n"
    b"f 4 3 2\n"
    b"s off\n"
)


@pytest.fixture
def mesh(tmp_path):
    path = tmp_path / "part.obj"
    path.write_bytes(OBJ)
    return path


def vertices(data):
    rows = [ln.split() for ln in data.decode().splitlines() if ln.startswith("v ")]
    return [[float(c) for c in r[1:4]] for r in rows]


def non_vertex(data):
    return [ln for ln in data.split(b"\n") if not ln.startswith(b"v ")]


def test_factor_one_half_halves_every_coordinate_and_the_box(mesh, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    out = tmp_path / "half"
    record = scale_mesh(mesh, 0.5, out=out)
    before, after = vertices(OBJ), vertices((out / "part.obj").read_bytes())
    assert after == [[c * 0.5 for c in v] for v in before]
    assert record["bounding_box_before"] == {"min": [-1.0, -2.0, 0.0], "max": [3.0, 2.0, 4.0]}
    assert record["bounding_box_after"] == {"min": [-0.5, -1.0, 0.0], "max": [1.5, 1.0, 2.0]}


def test_everything_but_the_vertex_lines_is_byte_identical(mesh, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    out = tmp_path / "o"
    scale_mesh(mesh, 2, out=out)
    data = (out / "part.obj").read_bytes()
    assert non_vertex(data) == non_vertex(OBJ)
    assert data.count(b"\n") == OBJ.count(b"\n")
    assert b"# mesh with comments, v 9 9 9\n" in data
    assert b"v 4.0 4.0 4.0 \n" in data


def test_crlf_line_ends_survive(tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    src = tmp_path / "w.obj"
    src.write_bytes(b"g a\r\nv 1 1 1\r\nf 1 1 1\r\n")
    scale_mesh(src, 3, out=tmp_path / "o")
    assert (tmp_path / "o" / "w.obj").read_bytes() == b"g a\r\nv 3.0 3.0 3.0\r\nf 1 1 1\r\n"


def test_about_scales_about_that_point(mesh, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    record = scale_mesh(mesh, 0.5, out=tmp_path / "o", about="1,2,3")
    got = vertices((tmp_path / "o" / "part.obj").read_bytes())
    assert got[0] == [1.0, 2.0, 3.0]
    assert got[1] == [0.0, 1.0, 3.5]
    assert record["about"] == [1.0, 2.0, 3.0]


def test_the_input_is_never_modified(mesh, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    scale_mesh(mesh, 0.5, out=tmp_path / "o")
    assert mesh.read_bytes() == OBJ


@pytest.mark.parametrize("bad", [0, 0.0, "0", -1, "-0.5", "abc", "", "nan", "inf", None])
def test_a_bad_factor_is_refused_by_name(mesh, tmp_path, bad):
    from pyflightstream.workspace.scale import scale_mesh

    with pytest.raises(InputValueError, match=r"scale: the factor"):
        scale_mesh(mesh, bad, out=tmp_path / "o")
    assert not (tmp_path / "o").exists()


def test_a_missing_file_is_refused_by_name(tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    with pytest.raises(InputArtifactError, match=r"scale: the mesh file .* does not exist"):
        scale_mesh(tmp_path / "nope.obj", 0.5, out=tmp_path / "o")
    assert not (tmp_path / "o").exists()


def test_an_existing_output_is_refused_unless_forced(mesh, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    out = tmp_path / "o"
    scale_mesh(mesh, 0.5, out=out)
    first = (out / "part.obj").read_bytes()
    with pytest.raises(InputValueError, match=r"already exists in the output folder.*force"):
        scale_mesh(mesh, 0.25, out=out)
    assert (out / "part.obj").read_bytes() == first
    scale_mesh(mesh, 0.25, out=out, force=True)
    assert (out / "part.obj").read_bytes() != first


def test_the_input_folder_as_output_never_overwrites_the_input(mesh):
    from pyflightstream.workspace.scale import scale_mesh

    for force in (False, True):
        with pytest.raises(InputValueError, match="never overwritten"):
            scale_mesh(mesh, 0.5, out=mesh.parent, force=force)
    assert mesh.read_bytes() == OBJ


def test_the_record_holds_hash_factor_counts_and_boxes(mesh, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    out = tmp_path / "o"
    scale_mesh(mesh, "0.5", out=out)
    record = json.loads((out / "part.obj.scale.json").read_text())
    assert record["input_sha256"] == hashlib.sha256(OBJ).hexdigest()
    assert record["factor"] == 0.5
    assert record["about"] == [0.0, 0.0, 0.0]
    assert (record["vertices"], record["faces"]) == (4, 2)
    assert set(record["bounding_box_before"]) == {"min", "max"}


def test_the_default_output_folder_is_beside_the_input(mesh):
    from pyflightstream.workspace.scale import scale_mesh

    record = scale_mesh(mesh, 0.5)
    folder = mesh.parent / "part_scaled0.5"
    assert (folder / "part.obj").is_file() and (folder / "part.obj.scale.json").is_file()
    assert Path(record["output"]) == folder / "part.obj"


def test_the_output_folder_is_created_with_its_parents(mesh, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    scale_mesh(mesh, 0.5, out=tmp_path / "a" / "b" / "c")
    assert (tmp_path / "a" / "b" / "c" / "part.obj").is_file()


def test_the_cli_writes_the_folder_and_prints_the_boxes(mesh, tmp_path, capsys):
    out = tmp_path / "cli_out"
    code = main(["geometry", "scale", "0.5", "--mesh", str(mesh), "--out", str(out)])
    assert code == 0
    shown = capsys.readouterr().out
    assert "bounding_box_before" in shown and "bounding_box_after" in shown
    assert (out / "part.obj").is_file()


def test_the_cli_refuses_by_name_with_exit_two(mesh, tmp_path, capsys):
    code = main(["geometry", "scale", "-0", "--mesh", str(mesh), "--out", str(tmp_path / "o")])
    assert code == 2
    assert "scale: the factor" in capsys.readouterr().err
    code = main(["geometry", "scale", "0.5", "--mesh", str(tmp_path / "x.obj")])
    assert code == 2


# ---- round 2: FlightStream .fsm meshes (PFS-2222) ----------------------------------------------

FSM_BEFORE = b"26,1\r\n7012026\r\n$CAD_START$\r\n  1.0E+00  2.0E+00  3.0E+00\r\n$CAD_END$\r\n"
FSM_MESH_HEAD = (
    b"$MESH_START$\r\n2\r\n1\r\n1\r\n1, T, F, F\r\nWing\r\n.494,.573,.576\r\n"
    b"2\r\n1,2,\r\n3,3,\r\n1,2,\r\n2,3,\r\n3,4,\r\n0,0,\r\n0,0,\r\n"
    b"T,T,\r\nF,F,\r\nF,F,\r\nF,F,\r\nT,T,\r\n0\r\n4\r\n"
)


def _row(*values):
    return b",".join(b"% .17E" % v for v in values) + b",\r\n"


FSM_X = _row(1, -4, 0, 2)
FSM_Y = _row(2, 0, -2, 4)
FSM_Z = _row(3, 4, 0, 2)
FSM_AFTER = b"$MESH_END$\r\n$PHYSICS_START$\r\n1.225\r\n 9.0E+00, 9.0E+00, 9.0E+00, 9.0E+00,\r\n"
FSM = FSM_BEFORE + FSM_MESH_HEAD + FSM_X + FSM_Y + FSM_Z + FSM_AFTER


@pytest.fixture
def fsm(tmp_path):
    path = tmp_path / "part.fsm"
    path.write_bytes(FSM)
    return path


def fsm_rows(data):
    lines = data.split(b"\r\n")
    start = lines.index(b"4") + 1
    return [[float(t) for t in ln.split(b",") if t.strip()] for ln in lines[start : start + 3]]


def test_fsm_half_halves_every_coordinate_and_the_box(fsm, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    out = tmp_path / "half"
    record = scale_mesh(fsm, 0.5, out=out)
    before, after = fsm_rows(FSM), fsm_rows((out / "part.fsm").read_bytes())
    assert after == [[c * 0.5 for c in row] for row in before]
    assert record["bounding_box_before"] == {"min": [-4.0, -2.0, 0.0], "max": [2.0, 4.0, 4.0]}
    assert record["bounding_box_after"] == {"min": [-2.0, -1.0, 0.0], "max": [1.0, 2.0, 2.0]}
    assert (record["vertices"], record["faces"]) == (4, 2)


def test_fsm_only_the_three_coordinate_rows_change(fsm, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    out = tmp_path / "o"
    scale_mesh(fsm, 2, out=out)
    data = (out / "part.fsm").read_bytes()
    assert data.startswith(FSM_BEFORE + FSM_MESH_HEAD)
    assert data.endswith(FSM_AFTER)
    assert data.count(b"\r\n") == FSM.count(b"\r\n")
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert data != FSM
    assert len(data) == len(FSM)
    scale_mesh(fsm, 1, out=tmp_path / "one")
    assert (tmp_path / "one" / "part.fsm").read_bytes() == FSM


def test_fsm_about_scales_about_that_point(fsm, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    record = scale_mesh(fsm, 0.5, out=tmp_path / "o", about="1,2,3")
    rows = fsm_rows((tmp_path / "o" / "part.fsm").read_bytes())
    assert [row[0] for row in rows] == [1.0, 2.0, 3.0]
    assert [row[1] for row in rows] == [-1.5, 1.0, 3.5]
    assert record["about"] == [1.0, 2.0, 3.0]


def test_fsm_the_input_is_never_modified_and_the_record_matches(fsm, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    out = tmp_path / "o"
    scale_mesh(fsm, "0.5", out=out)
    assert fsm.read_bytes() == FSM
    record = json.loads((out / "part.fsm.scale.json").read_text())
    assert record["input_sha256"] == hashlib.sha256(FSM).hexdigest()
    assert record["factor"] == 0.5 and record["about"] == [0.0, 0.0, 0.0]
    assert set(record["bounding_box_before"]) == {"min", "max"}


def test_fsm_default_folder_force_and_refusals(fsm, tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    record = scale_mesh(fsm, 0.5)
    folder = fsm.parent / "part_scaled0.5"
    assert Path(record["output"]) == folder / "part.fsm"
    with pytest.raises(InputValueError, match=r"already exists in the output folder.*force"):
        scale_mesh(fsm, 0.5)
    scale_mesh(fsm, 0.5, force=True)
    with pytest.raises(InputValueError, match="never overwritten"):
        scale_mesh(fsm, 0.5, out=fsm.parent, force=True)
    with pytest.raises(InputValueError, match=r"scale: the factor"):
        scale_mesh(fsm, 0, out=tmp_path / "z")
    assert not (tmp_path / "z").exists()
    assert fsm.read_bytes() == FSM


def test_fsm_without_a_node_block_is_refused_by_name(tmp_path):
    from pyflightstream.workspace.scale import scale_mesh

    bare = tmp_path / "bare.fsm"
    bare.write_bytes(b"26,1\r\n$CAD_START$\r\n$CAD_END$\r\n")
    with pytest.raises(InputValueError, match=r"scale: .*no mesh block"):
        scale_mesh(bare, 0.5, out=tmp_path / "o")
    cut = tmp_path / "cut.fsm"
    cut.write_bytes(FSM_BEFORE + FSM_MESH_HEAD + FSM_X + b"$MESH_END$\r\n")
    with pytest.raises(InputValueError, match=r"scale: .*node"):
        scale_mesh(cut, 0.5, out=tmp_path / "o2")
    assert not (tmp_path / "o").exists() and not (tmp_path / "o2").exists()


def test_fsm_through_the_cli_and_a_sidecar_is_left_alone(fsm, tmp_path, capsys):
    side = fsm.parent / "part.boundaries.toml"
    side.write_bytes(b'file = "part.fsm"\n')
    out = tmp_path / "cli_out"
    code = main(["geometry", "scale", "0.5", "--mesh", str(fsm), "--out", str(out)])
    assert code == 0
    assert "bounding_box_after" in capsys.readouterr().out
    assert (out / "part.fsm").is_file()
    assert side.read_bytes() == b'file = "part.fsm"\n'
