"""PFS-2215: control cuts preserve imported trims and clearance uses trimmed faces."""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.exceptions import InputValueError
from pyflightstream.geometry import stages
from tests.tier1_offline._kernel_support import kernel_or_skip


@pytest.fixture
def kernel():
    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    instance = open_kernel("control surface checks")
    try:
        yield instance
    finally:
        instance.close()


def _surface(kernel):
    return kernel.add_bspline_surface(
        [[(float(i), float(j), 0.0) for j in range(4)] for i in range(4)],
        knots_u=[0.0, 1.0],
        knots_v=[0.0, 1.0],
        mult_u=[4, 4],
        mult_v=[4, 4],
        deg_u=3,
        deg_v=3,
    )


def _loop(a, b, c, d):
    corners = [(a, c), (b, c), (b, d), (a, d)]
    return [[corners[i], corners[(i + 1) % 4]] for i in range(4)]


@pytest.mark.parametrize("direction", ["u", "v"], ids=["P0570-G9-ISO-U", "P0570-G9-ISO-V"])
def test_p0570_gm9_imported_split_preserves_hole(kernel, tmp_path, direction):
    base = _surface(kernel)
    trimmed = kernel.add_trimmed_face(base, [_loop(0, 1, 0, 1), _loop(0.2, 0.4, 0.2, 0.4)])
    path = tmp_path / "perforated.igs"
    kernel.export_iges({"PANEL": [trimmed]}, path)
    face = kernel.import_iges(path).faces[0]
    split = getattr(kernel, "split_imported_face_uv", kernel.split_face_uv)
    try:
        pieces = split(face, direction, 0.6)
    except InputValueError as error:
        pytest.fail(f"an imported B-spline must support exact iso splitting: {error}")
    assert len(pieces) == 2
    assert [kernel.area(f) for f in pieces] == pytest.approx([5.04, 3.6], abs=1e-8)
    assert not any(kernel.is_inside(f, (0.3, 0.3)) for f in pieces)
    # NO: invalid parameters must not remove or alter any face.
    before = [(f, kernel.area(f)) for f in kernel.faces()]
    with pytest.raises(InputValueError, match="direction"):
        split(pieces[0], "w", 0.3)
    with pytest.raises(InputValueError, match="finite"):
        split(pieces[0], direction, float("nan"))
    assert [(f, kernel.area(f)) for f in kernel.faces()] == before


@pytest.mark.parametrize("offset", [0.25, 0.0], ids=["P0570-G9-DIST-YES", "P0570-G9-DIST-NO"])
def test_p0570_gm9_minimum_distance_contact_and_separation(kernel, offset):
    a = kernel.add_planar_face([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    b = kernel.add_planar_face([(0, 0, offset), (1, 0, offset), (1, 1, offset), (0, 1, offset)])
    distance = getattr(kernel, "minimum_distance", None)
    assert callable(distance), "F3 requires a native face-set minimum distance"
    assert distance([a], [b]) == pytest.approx(offset, abs=1e-12)
    assert (distance([a], [b]) > 0) is (offset > 0)
    with pytest.raises(InputValueError, match="empty"):
        distance([], [b])


def test_p0570_gm9_minimum_distance_respects_holes_and_crossings(kernel):
    base = _surface(kernel)
    ring = kernel.add_trimmed_face(base, [_loop(0, 1, 0, 1), _loop(0.2, 0.8, 0.2, 0.8)])
    inside_hole = kernel.add_planar_face([(1, 1, 0), (2, 1, 0), (2, 2, 0), (1, 2, 0)])
    crossing = kernel.add_planar_face([(0.3, 0, -1), (0.3, 3, -1), (0.3, 3, 1), (0.3, 0, 1)])
    distance = getattr(kernel, "minimum_distance", None)
    assert callable(distance), "F3 requires a native face-set minimum distance"
    assert distance([ring], [inside_hole]) == pytest.approx(0.4, abs=1e-9)
    assert distance([ring], [inside_hole, crossing]) == pytest.approx(0, abs=1e-12)


def _control_partition():
    namespace = getattr(stages, "controls", None)
    assert namespace is not None, "controls need a public stage facade"
    return namespace


def _box_skin():
    # A closed rectangular section, chord 1 m, half span 2 m. The hinge at
    # x = 0.5 is exactly u = 0.2 (lower) and 0.8 (upper), already pinned.
    section = [(1, -0.1), (0.5, -0.1), (0, -0.1), (0, 0.1), (0.5, 0.1), (1, 0.1)]
    return stages.Patch(
        family="skin",
        controls=np.array([[(x, y, z) for y in (0, 1, 2)] for x, z in section]),
        knots_u=(0, 0.2, 0.4, 0.6, 0.8, 1),
        knots_v=(0, 0.5, 1),
        multiplicities_u=(2, 1, 1, 1, 1, 2),
        multiplicities_v=(2, 1, 2),
        degree_u=1,
        degree_v=1,
    )


def test_p0570_gm9_plain_partition_preserves_base_and_closes_ends(kernel, tmp_path):
    controls = _control_partition()
    skin = _box_skin()
    result = controls.partition(skin, lower=0.2, upper=0.8, span=(0.25, 0.75))
    assert result.bases["skin"] is skin
    assert set(result.pieces) == {"main", "control"}
    for name, trims in result.pieces.items():
        native = {}
        for key, patch in result.bases.items():
            native[key] = kernel.add_bspline_surface(
                patch.controls,
                knots_u=patch.knots_u,
                knots_v=patch.knots_v,
                mult_u=patch.multiplicities_u,
                mult_v=patch.multiplicities_v,
                deg_u=patch.degree_u,
                deg_v=patch.degree_v,
            )
        faces = [kernel.add_trimmed_face(native[t.base], [t.loop]) for t in trims]
        path = tmp_path / f"{name}.igs"
        kernel.export_iges({name: faces}, path)
        topology = kernel.inspect_file(path, 1e-5)
        assert len(topology.areas) == len(faces)
        assert sum(len(owners) == 1 for _, owners in topology.edges) == 0
        assert sum(len(owners) > 2 for _, owners in topology.edges) == 0
        # NO: an omitted end face must expose a real opening after sewing.
        end = next(i for i, trim in enumerate(trims) if trim.role == "end")
        kernel.export_iges({name: faces[:end] + faces[end + 1 :]}, path)
        opened = kernel.inspect_file(path, 1e-5)
        assert sum(len(owners) == 1 for _, owners in opened.edges) > 0


@pytest.mark.parametrize("span", [(0.75, 0.25), (-0.1, 0.5), (0.2, float("nan"))])
def test_p0570_gm9_partition_refuses_invalid_span(span):
    with pytest.raises(InputValueError, match="span"):
        _control_partition().partition(_box_skin(), lower=0.2, upper=0.8, span=span)


def _closed_box(kernel, offset=0.0):
    points = [
        (x, y + offset, z)
        for x, y, z in [
            (0, 0, 0),
            (1, 0, 0),
            (1, 1, 0),
            (0, 1, 0),
            (0, 0, 1),
            (1, 0, 1),
            (1, 1, 1),
            (0, 1, 1),
        ]
    ]
    return [
        kernel.add_planar_face([points[i] for i in indices])
        for indices in [
            (0, 1, 2, 3),
            (4, 7, 6, 5),
            (0, 4, 5, 1),
            (1, 5, 6, 2),
            (2, 6, 7, 3),
            (3, 7, 4, 0),
        ]
    ]


def _fcheck(kernel, stage, inputs):
    import importlib
    import importlib.util

    module = "pyflightstream.workspace._geom_control"
    assert importlib.util.find_spec(module), "the F sub-steps have no implementation"
    return importlib.import_module(module).check_stage(kernel, stage, inputs)


def _passed(result):
    return all(c["status"] == "passed" for c in result["checks"])


@pytest.mark.parametrize("missing", [False, True], ids=["P0570-F0-YES", "P0570-F0-NO"])
def test_p0570_gm9_f0_counts_faces_read_against_written(kernel, tmp_path, missing):
    faces = _closed_box(kernel)
    path = tmp_path / "piece.igs"
    kernel.export_iges({"main": faces[:-1] if missing else faces}, path)
    result = _fcheck(kernel, "F0", {"pieces": {"main": {"path": str(path), "written": 6}}})
    assert _passed(result) is not missing
    assert result["checks"][0]["measured"] == int(missing)


@pytest.mark.parametrize("stage", ["F1", "F2", "F7"], ids=["P0570-F1", "P0570-F2", "P0570-F7"])
@pytest.mark.parametrize("missing", [False, True], ids=["YES", "NO"])
def test_p0570_gm9_sewn_closure_rejects_missing_end(kernel, tmp_path, stage, missing):
    faces = _closed_box(kernel)
    path = tmp_path / "closed.igs"
    kernel.export_iges({"piece": faces[:-1] if missing else faces}, path)
    result = _fcheck(kernel, stage, {"path": str(path)})
    assert _passed(result) is not missing
    checks = {c["id"]: c for c in result["checks"]}
    assert checks["control.free_edges"]["measured"] == (4 if missing else 0)
    assert checks["control.free_edges"]["limit"] == 0
    assert result["outputs"]["sew_tolerance_m"] == 1e-5


@pytest.mark.parametrize("offset", [2.0, 1.0], ids=["P0570-F3-YES", "P0570-F3-NO"])
def test_p0570_gm9_f3_exact_clearance(kernel, offset):
    flap, host = _closed_box(kernel), _closed_box(kernel, offset)
    result = _fcheck(kernel, "F3", {"controls": {"flap": flap}, "hosts": {"body": host}})
    assert _passed(result) is (offset > 1)
    assert result["outputs"]["distances_m"]["flap/body"] == pytest.approx(offset - 1)


@pytest.mark.parametrize("named", [True, False], ids=["P0570-F4-YES", "P0570-F4-NO"])
def test_p0570_gm9_f4_requires_names_for_slot_openings(kernel, tmp_path, named):
    faces = _closed_box(kernel)
    path = tmp_path / "slot.igs"
    kernel.export_iges({"main": faces[1:]}, path)
    # The four bottom boundary edges are the deliberately open slot rim.
    rim = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    slots = {"slot": [[rim[i], rim[(i + 1) % 4]] for i in range(4)]} if named else {}
    result = _fcheck(kernel, "F4", {"path": str(path), "slots": slots, "previous_free": 4})
    assert _passed(result) is named


@pytest.mark.parametrize("stage", ["F5", "F6"], ids=["P0570-F5", "P0570-F6"])
@pytest.mark.parametrize("missing", [False, True], ids=["YES", "NO"])
@pytest.mark.xfail(reason="waits for the trimmed assembly of G8", strict=True)
def test_p0570_gm9_trimmed_assembly_boundary(kernel, tmp_path, stage, missing):
    from pyflightstream.workspace import _geom_run

    faces = _closed_box(kernel)
    path = tmp_path / "after_cut.igs"
    kernel.export_iges({"main": faces[:-1] if missing else faces}, path)
    inputs = {
        "path": str(path),
        "previous_free": 0,
        "junction_lengths_m": {"main/body": 4.0},
        "clean_junction_lengths_m": {"main/body": 4.0},
    }
    result = _fcheck(kernel, stage, inputs)
    assert _passed(result) is not missing
    # The session supplies the trimmed assembly boundary at merge. This assertion
    # keeps the integration expectation pending even once the checker works.
    assert hasattr(_geom_run, "trimmed_control_assembly")


@pytest.mark.parametrize("missing", [False, True], ids=["P0570-F-LOG-YES", "P0570-F-LOG-NO"])
def test_p0570_gm9_stage_table_runner_records_and_log(kernel, tmp_path, missing):
    from pyflightstream.workspace import _geom_run

    rows = {row.stage: row for row in stages.STAGE_ROWS}
    assert all(f"S10.F{i}" in rows for i in range(8)), "F sub-steps absent from the table"
    assert all(f"S10.F{i}" in _geom_run.STAGE_FUNCTIONS for i in range(8))
    faces = _closed_box(kernel)
    path = tmp_path / "main.igs"
    kernel.export_iges({"main": faces[:-1] if missing else faces}, path)

    def seed(context):
        context.state["control_inputs"] = {
            "F0": {"pieces": {"main": {"path": str(path), "written": 6}}},
            "F1": {"path": str(path)},
        }
        return _geom_run.StageOutcome(checks=[stages.check_entry("input.valid", "passed", 0, 0)])

    selected = [_geom_run.Stage(rows["S0"], seed)]
    selected += [
        _geom_run.Stage(rows[f"S10.F{i}"], _geom_run.STAGE_FUNCTIONS[f"S10.F{i}"]) for i in (0, 1)
    ]
    report = _geom_run.run_geometry(
        {"type": "body"}, out=tmp_path / "run", until="S10.F1", stages=selected
    )
    assert report["status"] == ("failed" if missing else "accepted")
    log = (tmp_path / "run" / "geom-run.log").read_text(encoding="utf-8")
    assert "sub-step S10.F0" in log and "control.faces_read" in log
    assert "threshold" in log and "sha256" in log and "wall" in log
    if missing:
        assert report["stage"] == "S10.F0"
        assert "sub-step S10.F1 " not in log
    else:
        assert "sub-step S10.F1" in log and "control.free_edges" in log
