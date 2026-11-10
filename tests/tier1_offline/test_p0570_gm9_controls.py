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


def _plain_config():
    return {
        "components": {
            "panel": {
                "type": "lifting_surface",
                "planform": {"sref_m2": 4.0, "aspect_ratio": 4.0, "taper": 1.0},
                "stations": [
                    {"eta": 0.0, "section": {"kind": "naca", "code": "0012"}},
                    {"eta": 1.0, "section": {"kind": "naca", "code": "0012"}},
                ],
                "cap": {"type": "flat"},
                "root": "flat",
                "control": [
                    {
                        "name": "flap",
                        "kind": "plain",
                        "eta": [0.2, 0.7],
                        "chord_ratio": 0.25,
                        "gap_span": 0.01,
                        "gap_chord": 0.002,
                        "deflection_deg": [0, 15],
                    }
                ],
            }
        }
    }


def test_p0570_gm9_plain_applied_geometry_preserves_skin_and_closes(kernel, tmp_path):
    from pyflightstream.geometry import resolve_config

    component = stages.unpack(resolve_config(_plain_config()))["components"]["panel"]
    build = getattr(stages.controls, "build", None)
    assert callable(build), "TOML control entries have no applied geometry"
    model = build(component)
    assert set(model.pieces) == {"main", "flap-d0", "flap-d15"}
    for name, trims in model.pieces.items():
        native = {}
        for key in {t.base for t in trims}:
            patch = model.bases[key]
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
        result = _fcheck(kernel, "F1" if name == "main" else "F2", {"path": str(path)})
        assert _passed(result), result
    # NO: a gap wider than the interval must refuse before constructing faces.
    component["control_surfaces"][0]["gap_span"] = 0.3
    with pytest.raises(InputValueError, match="gap_span"):
        build(component)


def test_p0570_gm9_toml_controls_reach_default_runner(tmp_path):
    import json

    from pyflightstream.workspace.geometry_pipeline import run_geometry

    report = run_geometry(_plain_config(), out=tmp_path, until="S10.F4")
    records = {r["stage"]: r for r in report["stages"]}
    assert "S10.F0" in records, report
    record = json.loads((tmp_path / records["S10.F0"]["record"]).read_text(encoding="utf-8"))
    assert records["S10.F0"]["status"] == "passed", json.dumps(record)
    assert records["S10.F1"]["status"] == records["S10.F2"]["status"] == "passed"
    assert "applied_controls" in record["outputs"]
    assert "flap-d15" in (tmp_path / "geom-run.log").read_text(encoding="utf-8")


def test_p0570_gm9_public_edit_applies_control_and_preserves_other_faces(kernel, tmp_path, capsys):
    from pyflightstream.geometry import resolve_config
    from pyflightstream.workspace.geometry_pipeline import add_control_surfaces

    raw = _plain_config()
    model = stages.controls.build(stages.unpack(resolve_config(raw))["components"]["panel"])
    native = []
    for key in ("skin", "root", "tip", "trailing_edge"):
        p = model.bases[key]
        native.append(
            kernel.add_bspline_surface(
                p.controls,
                knots_u=p.knots_u,
                knots_v=p.knots_v,
                mult_u=p.multiplicities_u,
                mult_v=p.multiplicities_v,
                deg_u=p.degree_u,
                deg_v=p.degree_v,
            )
        )
    source, target = tmp_path / "source.igs", tmp_path / "edited.igs"
    kernel.export_iges({"panel": native, "body": _closed_box(kernel, 4)}, source)
    entry = {**raw["components"]["panel"]["control"][0], "deflection_deg": [15]}
    result = add_control_surfaces(source, "panel", [entry], target)
    assert result["status"] == "passed", result
    imported = kernel.import_iges(target)
    assert "panel/flap-d15" in imported.names
    assert imported.names.count("body") == 6
    topology = kernel.inspect_file(target, 1e-5)
    assert all(len(owners) == 2 for _, owners in topology.edges)
    with pytest.raises(InputValueError, match="eta"):
        add_control_surfaces(source, "panel", [{**entry, "eta": [0.8, 0.2]}], tmp_path / "bad.igs")
    assert not (tmp_path / "bad.igs").exists()
    from pyflightstream.run.geom_cli import main

    table = tmp_path / "control.toml"
    table.write_text(
        "[[control]]\nname='flap'\nkind='plain'\neta=[0.2,0.7]\nchord_ratio=0.25\ngap_span=0.01\ngap_chord=0.002\ndeflection_deg=[15]\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "add-control-surface",
                str(source),
                "panel",
                str(table),
                "--out",
                str(tmp_path / "cli.igs"),
            ]
        )
        == 0
    )
    assert (tmp_path / "cli.igs").is_file()


def test_p0570_gm9_default_runner_measures_control_host_clearance(tmp_path):
    import json

    from pyflightstream.workspace.geometry_pipeline import run_geometry

    raw = _plain_config()
    raw["components"]["host"] = {
        "type": "body",
        "length_mm": 1000.0,
        "placement": {"translation": [0, 4, 0]},
    }
    report = run_geometry(raw, out=tmp_path, until="S10.F3")
    assert (tmp_path / "S10.F3.json").is_file(), json.dumps(report)
    record = json.loads((tmp_path / "S10.F3.json").read_text(encoding="utf-8"))
    assert record["status"] == "passed", (report, record)
    assert min(record["outputs"]["distances_m"].values()) > 0


def test_p0570_gm9_combined_variants_include_every_control(kernel, tmp_path):
    from pyflightstream.geometry import resolve_config
    from pyflightstream.workspace._geom_control_build import prepare

    raw = _plain_config()
    entries = raw["components"]["panel"]["control"]
    entries[0]["eta"] = [0.2, 0.4]
    entries.append({**entries[0], "name": "aileron", "kind": "aileron", "eta": [0.6, 0.8]})
    components = stages.unpack(resolve_config(raw))["components"]
    inputs = prepare(kernel, components, ["panel"], tmp_path)
    assert len(inputs["F4"]["batch"]) == 4
    for row in inputs["F4"]["batch"].values():
        names = set(kernel.import_iges(row["path"]).names)
        assert len(names) == 3, names
        assert any("flap-d" in n for n in names) and any("aileron-d" in n for n in names)
    result = _fcheck(kernel, "F4", inputs["F4"])
    assert _passed(result), result
