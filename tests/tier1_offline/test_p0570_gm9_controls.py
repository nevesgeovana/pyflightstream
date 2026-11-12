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
    result = importlib.import_module(module).check_stage(kernel, stage, inputs)
    row = next(row for row in stages.STAGE_ROWS if row.stage == f"S10.{stage}")
    assert {c["id"] for c in result["checks"]} == {cid for cid, _ in row.checks}
    return result


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
    assert checks[f"control.{stage.lower()}.free_edges"]["measured"] == (4 if missing else 0)
    assert checks[f"control.{stage.lower()}.free_edges"]["limit"] == 0
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
@pytest.mark.parametrize(
    ("delta", "accepted"),
    [(5.3e-14, True), (4e-9, False)],
    ids=["roundoff-YES", "real-delta-NO"],
)
def test_p0570_gm9_junction_length_tolerance_is_relative_to_size(
    kernel, tmp_path, stage, delta, accepted
):
    faces = _closed_box(kernel)
    path = tmp_path / "after_cut.igs"
    kernel.export_iges({"main": faces}, path)
    inputs = {
        "path": str(path),
        "previous_free": 0,
        "junction_lengths_m": {"main/body": 4.0 + delta},
        "clean_junction_lengths_m": {"main/body": 4.0},
    }
    assert _passed(_fcheck(kernel, stage, inputs)) is accepted


@pytest.mark.parametrize("stage", ["F5", "F6"], ids=["P0570-F5", "P0570-F6"])
@pytest.mark.parametrize("missing", [False, True], ids=["YES", "NO"])
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
        assert "sub-step S10.F1" in log and "control.f1.free_edges" in log


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


@pytest.mark.parametrize(
    "builder", ["build", "imported"], ids=["P0570-R26-build", "P0570-R26-imported"]
)
def test_p0570_r26_distinct_angles_keep_distinct_control_pieces(builder):
    """Two deflections differing after six significant digits must both survive."""
    from pyflightstream.geometry import resolve_config

    raw = _plain_config()
    entry = raw["components"]["panel"]["control"][0]
    entry["deflection_deg"] = [15.000001, 15.000002]
    component = stages.unpack(resolve_config(raw))["components"]["panel"]
    if builder == "build":
        result = stages.controls.build(component)
        labels = set(result.pieces) - {"main"}
    else:
        result = stages.controls.imported(stages.lifting_model(component).skin, entry)
        labels = set(result["motions"])
    assert labels == {"flap-d15.000001", "flap-d15.000002"}


def test_p0570_r26_control_guide_has_an_executed_example():
    """The guide must expose the control workflow and its assembly limits."""
    from pathlib import Path

    page = Path(__file__).resolve().parents[2] / "docs" / "geometry-parametrization.md"
    text = page.read_text(encoding="utf-8")
    assert "add-control-surface" in text and "add_control_surfaces" in text
    assert "F5" in text and "F6" in text
    examples = [part.split("```", 1)[0] for part in text.split("```python\n")[1:]]
    example = next((part for part in examples if "controls.build" in part), "")
    assert example, "control guide needs a runnable worked example"
    exec(compile(example, str(page), "exec"), {})


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


def test_p0570_gm9_exposed_span_and_split_bounds():
    from pyflightstream.geometry import resolve_config

    component = stages.unpack(resolve_config(_plain_config()))["components"]["panel"]
    control = component["control_surfaces"][0]
    control.update(span_basis="exposed", exposed_root_m=1.0, gap_span=0.0)
    model = stages.controls.build(component)
    trim = next(t for t in model.pieces["flap-d0"] if t.base.endswith("/skin"))
    assert sorted({p[1] for edge in trim.loop for p in edge}) == pytest.approx([0.6, 0.85])
    control.update(span_basis="semi_span", split_around=["pod"], gap_span=0.005)
    component["sections"]["nacelle_bounds"] = [{"component": "pod", "eta_in": 0.4, "eta_out": 0.5}]
    model = stages.controls.build(component)
    assert set(model.pieces) == {
        "main",
        "flap-inboard-d0",
        "flap-inboard-d15",
        "flap-outboard-d0",
        "flap-outboard-d15",
    }
    # NO: an exposed root outside the planform cannot silently move the control.
    control.update(span_basis="exposed", exposed_root_m=3.0)
    with pytest.raises(InputValueError, match="exposed_root"):
        stages.controls.build(component)


def _fowler_config():
    raw = _plain_config()
    entry = raw["components"]["panel"]["control"][0]
    entry.update(
        kind="fowler",
        gap_chord=0.0,
        cove={"wall_x": 0.72, "lip_x": 0.94, "p3": {"eta": 0.45, "z_over_c": 0.035}},
        nose={"kind": "elliptic", "radius": 0.01},
        nested_dz_pct=-0.2,
        clearance_pct=0.1,
        kinematics=[
            {
                "deflection_deg": 15,
                "pivot_x": 0.75,
                "pivot_z": -0.1,
                "gap_pct": 2.0,
                "overlap_pct": 1.0,
            }
        ],
    )
    return raw


def _fowler_model(raw):
    from pyflightstream.geometry import resolve_config

    component = stages.unpack(resolve_config(raw))["components"]["panel"]
    try:
        return stages.controls.build(component)
    except InputValueError as error:
        pytest.fail(f"a stated Fowler cove must build applied surfaces: {error}")


def test_p0570_gm9_fowler_cove_nested_and_deployed_are_closed(kernel, tmp_path):
    model = _fowler_model(_fowler_config())
    assert set(model.pieces) == {"main", "flap-d0", "flap-d15"}
    roles = {t.role for t in model.pieces["main"]}
    assert {"cove_wall", "cove_roof", "lip_base"} <= roles
    for name, trims in model.pieces.items():
        path = tmp_path / f"{name}.igs"
        native = {}
        for key in {t.base for t in trims}:
            p = model.bases[key]
            native[key] = kernel.add_bspline_surface(
                p.controls,
                knots_u=p.knots_u,
                knots_v=p.knots_v,
                mult_u=p.multiplicities_u,
                mult_v=p.multiplicities_v,
                deg_u=p.degree_u,
                deg_v=p.degree_v,
            )
        faces = [kernel.add_trimmed_face(native[t.base], [t.loop]) for t in trims]
        kernel.export_iges({name: faces}, path)
        assert _passed(_fcheck(kernel, "F1" if name == "main" else "F2", {"path": str(path)}))
        # NO: removing a cove wall or flap nose must expose an actual sewn opening.
        role = "cove_wall" if name == "main" else "nose"
        missing = next(i for i, trim in enumerate(trims) if trim.role == role)
        kernel.export_iges({name: faces[:missing] + faces[missing + 1 :]}, path)
        assert not _passed(_fcheck(kernel, "F1", {"path": str(path)}))


def test_p0570_gm9_fowler_laws_have_measured_yes_and_no():
    model = _fowler_model(_fowler_config())
    checks = getattr(model, "checks", ())
    assert checks, "Fowler acceptance must carry measured checks"
    by_id = {c["id"]: c for c in checks}
    for name in ("fowler.gap_error_pct", "fowler.overlap_error_pct"):
        assert by_id[name]["limit"] == 0.01
        assert by_id[name]["measured"] < 0.01
    assert by_id["fowler.inside_main"]["measured"] == 0
    assert by_id["fowler.nested_clearance_pct"]["measured"] >= 0.1
    assert by_id["closure.retracted_identity"]["measured"] <= 1e-12
    bad = _fowler_config()
    bad["components"]["panel"]["control"][0]["clearance_pct"] = 20
    with pytest.raises(InputValueError, match="clearance"):
        from pyflightstream.geometry import resolve_config

        stages.controls.build(stages.unpack(resolve_config(bad))["components"]["panel"])


def test_p0570_gm9_fowler_substeps_reach_records_and_log(tmp_path):
    import json

    from pyflightstream.workspace.geometry_pipeline import run_geometry

    rows = {row.stage for row in stages.STAGE_ROWS}
    assert {f"S10.FW{i}" for i in range(1, 5)} <= rows, "Fowler sub-steps are absent"
    report = run_geometry(_fowler_config(), out=tmp_path, until="S10.F4")
    for step in ("FW1", "FW2", "FW3", "FW4"):
        record = json.loads((tmp_path / f"S10.{step}.json").read_text(encoding="utf-8"))
        assert record["status"] == "passed", (report, record)
        assert record["outputs"]["inputs"]
        assert all(c["measured"] is not None and c["limit"] is not None for c in record["checks"])
    log = (tmp_path / "geom-run.log").read_text(encoding="utf-8")
    assert all(f"sub-step S10.FW{i}" in log for i in range(1, 5))
    assert "fowler.gap_error_pct" in log and "0.01" in log and "49" in log


def test_p0570_gm9_fowler_public_edit_checks_the_actual_cove(kernel, tmp_path):
    from pyflightstream.workspace.geometry_pipeline import add_control_surfaces

    raw = _fowler_config()
    model = _fowler_model(raw)
    faces = []
    for key in ("skin", "root", "tip", "trailing_edge"):
        p = model.bases[key]
        faces.append(
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
    source, target = tmp_path / "clean.igs", tmp_path / "fowler.igs"
    kernel.export_iges({"panel": faces}, source)
    result = add_control_surfaces(source, "panel", raw["components"]["panel"]["control"], target)
    assert result["status"] == "passed", result
    assert any(c["id"] == "fowler.gap_error_pct" for c in result["checks"]), result
    assert all(len(owners) == 2 for _, owners in kernel.inspect_file(target, 1e-5).edges)


@pytest.mark.parametrize(
    "variant", ["clean", "cs", "csf"], ids=["P0570-F7-CLEAN", "P0570-F7-CS", "P0570-F7-CSF"]
)
def test_p0570_gm9_f7_automatically_selects_variant_controls(kernel, tmp_path, variant):
    import copy
    import json

    from pyflightstream.workspace import _geom_run

    raw = _plain_config()
    tail = copy.deepcopy(raw["components"]["panel"])
    tail["placement"] = {"translation": [3, 0, 1]}
    tail["control"][0].update(name="elevator", kind="elevator")
    raw["components"]["tail"] = tail
    raw["variants"] = {"cs": ["tail.elevator"], "csf": ["tail.elevator", "panel.flap"]}
    selected = [
        _geom_run.Stage(row, _geom_run.STAGE_FUNCTIONS[row.stage])
        for row in stages.STAGE_ROWS
        if row.stage in ("S0", "S10.F7")
    ]
    report = _geom_run.run_geometry(
        raw, out=tmp_path, variant=variant, until="S10.F7", stages=selected
    )
    record = json.loads((tmp_path / "S10.F7.json").read_text(encoding="utf-8"))
    assert record["status"] == "passed", (report, record)
    paths = record["outputs"]["variants"]
    assert len(paths) == {"clean": 1, "cs": 2, "csf": 4}[variant]
    for item in paths.values():
        names = set(kernel.import_iges(item["path"]).names)
        assert any("elevator-d" in n for n in names) is (variant != "clean")
        assert any("flap-d" in n for n in names) is (variant == "csf")
    assert "S10.F7" in (tmp_path / "geom-run.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("missing", [False, True], ids=["P0570-F7-CAP-YES", "P0570-F7-CAP-NO"])
def test_p0570_gm9_f7_caps_fin_root_and_rejects_open_tip(tmp_path, missing):
    import json

    from pyflightstream.workspace import _geom_run

    raw = _plain_config()
    fin = raw["components"]["panel"]
    fin.pop("root")
    fin["surface"] = {"span_axis": "z"}
    fin["cap"]["type"] = "none" if missing else "flat"
    raw["variants"] = {"cs": ["panel.flap"]}
    selected = [
        _geom_run.Stage(row, _geom_run.STAGE_FUNCTIONS[row.stage])
        for row in stages.STAGE_ROWS
        if row.stage in ("S0", "S10.F7")
    ]
    report = _geom_run.run_geometry(
        raw, out=tmp_path, variant="cs", until="S10.F7", stages=selected
    )
    record = json.loads((tmp_path / "S10.F7.json").read_text(encoding="utf-8"))
    assert record["status"] == ("failed" if missing else "passed"), (report, record)
    assert record["outputs"]["root_caps_m2"]["panel"] > 0
    assert (
        any(c["id"] == "control.f7.free_edges" and c["measured"] > 0 for c in record["checks"])
        is missing
    )


def test_p0570_gm9_fowler_checks_measure_mutated_applied_geometry():
    import copy
    from dataclasses import replace

    verify = getattr(stages.controls, "check_fowler", None)
    assert callable(verify), (
        "Fowler checks must measure the applied bases, not only construction inputs"
    )
    raw = _fowler_config()
    entry = raw["components"]["panel"]["control"][0]
    model = _fowler_model(raw)
    assert all(c["status"] == "passed" for c in verify(model, entry, span=(0.2, 0.7, 0.01)))
    for angle, delta, check in [
        (15, (0.01, 0, 0), "fowler.overlap_error_pct"),
        (15, (0, 0, -0.01), "fowler.gap_error_pct"),
        (0, (-0.3, 0, 0), "fowler.inside_main"),
    ]:
        changed = copy.deepcopy(model)
        prefix = f"flap-d{angle}/"
        for key, p in list(changed.bases.items()):
            if key.startswith(prefix):
                changed.bases[key] = replace(p, controls=p.controls + delta)
        measured = verify(changed, entry, span=(0.2, 0.7, 0.01))
        assert any(c["id"] == check and c["status"] == "failed" for c in measured), measured
    changed = copy.deepcopy(model)
    p = changed.bases["flap-d0/skin"]
    changed.bases["flap-d0/skin"] = replace(p, controls=p.controls + (0, 0, -0.01))
    assert any(
        c["id"] == "closure.retracted_identity" and c["status"] == "failed"
        for c in verify(changed, entry, span=(0.2, 0.7, 0.01))
    )
    changed = copy.deepcopy(model)
    p = changed.bases["flap-d0/upper_nested"]
    changed.bases["flap-d0/upper_nested"] = replace(p, controls=p.controls + (0, 0, 0.0019))
    assert any(
        c["id"] == "fowler.nested_clearance_pct" and c["status"] == "failed"
        for c in verify(changed, entry, span=(0.2, 0.7, 0.01))
    )


def test_p0570_gm9_fowler_kink_bays_have_a_no_fixture():
    from dataclasses import replace

    skin = _box_skin()
    poles = skin.controls.copy()
    poles[:, 1, 0] += 0.3
    poles[:, 2, 0] += 0.1
    skin = replace(skin, controls=poles)
    entry = _fowler_config()["components"]["panel"]["control"][0]
    entry = {**entry, "deflection_deg": [0]}
    model = stages.controls.imported(skin, entry)["main"]
    verify = getattr(stages.controls, "check_fowler", None)
    assert callable(verify), "kink splitting needs a measured YES and NO"
    roofs = [t for t in model.pieces["main"] if t.role == "cove_roof"]
    bounds = sorted(sorted({p[1] for edge in t.loop for p in edge}) for t in roofs)
    assert bounds == [[0.2, 0.5], [0.5, 0.7]]
    assert all(c["status"] == "passed" for c in verify(model, entry, span=(0.2, 0.7, 0.01)))
    model.pieces["main"] = tuple(t for t in model.pieces["main"] if t != roofs[0])
    assert any(
        c["id"] == "fowler.cove_bay_mismatch" and c["status"] == "failed"
        for c in verify(model, entry, span=(0.2, 0.7, 0.01))
    )


def test_p0570_gm9_f7_applies_the_tail_host_junction(tmp_path):
    import json

    from pyflightstream.workspace import _geom_run

    raw = _plain_config()
    fin = raw["components"]["panel"]
    fin.pop("root")
    fin["surface"] = {"span_axis": "z"}
    fin["placement"] = {"translation": [0.5, 0, 0]}
    raw["components"]["host"] = {"type": "body", "length_mm": 2000, "symmetry": "full"}
    raw["dominance"] = [{"dominant": ["host"], "dominated": ["panel"], "operation": "cut"}]
    raw["variants"] = {"cs": ["panel.flap"]}
    selected = [
        _geom_run.Stage(row, _geom_run.STAGE_FUNCTIONS[row.stage])
        for row in stages.STAGE_ROWS
        if row.stage in ("S0", "S10.F7")
    ]
    report = _geom_run.run_geometry(
        raw, out=tmp_path, variant="cs", until="S10.F7", stages=selected
    )
    record = json.loads((tmp_path / "S10.F7.json").read_text(encoding="utf-8"))
    assert record["status"] == "passed", (report, record)
    lengths = record["outputs"].get("junction_lengths_m", {})
    assert lengths and all(values["host/panel"] > 0 for values in lengths.values()), record


def test_p0570_gm9_fowler_bad_nesting_stops_at_its_own_substep(tmp_path):
    import json

    from pyflightstream.workspace.geometry_pipeline import run_geometry

    raw = _fowler_config()
    raw["components"]["panel"]["control"][0]["clearance_pct"] = 20
    report = run_geometry(raw, out=tmp_path, until="S10.F4")
    assert report["status"] == "failed" and report["stage"] == "S10.FW2", report
    record = json.loads((tmp_path / "S10.FW2.json").read_text(encoding="utf-8"))
    assert record["checks"][0]["id"] == "fowler.nested_clearance_pct"
    assert record["checks"][0]["limit"] == 20
    assert not (tmp_path / "S10.FW3.json").exists()
    log = (tmp_path / "geom-run.log").read_text(encoding="utf-8")
    assert "fowler.nested_clearance_pct" in log and "S10.FW2" in log


def test_p0570_gm9_kinked_cove_uses_sewing_to_reject_an_unsplit_roof(kernel, tmp_path):
    from dataclasses import replace

    skin = _box_skin()
    poles = skin.controls.copy()
    poles[:, 1, 0] += 0.3
    poles[:, 2, 0] += 0.1
    skin = replace(skin, controls=poles)
    original = stages.controls.partition(skin, lower=0.2, upper=0.8, span=(0.2, 0.7))
    entry = {**_fowler_config()["components"]["panel"]["control"][0], "deflection_deg": [0]}
    model = stages.controls.imported(skin, entry)["main"]
    model.bases.update({k: original.bases[k] for k in ("root", "tip")})
    extra = [
        t
        for t in original.pieces["main"]
        if t.base in ("root", "tip")
        or (
            t.base in ("skin", "trailing_edge")
            and min(p[1] for edge in t.loop for p in edge) >= 0.7
        )
    ]
    main = [*model.pieces["main"], *extra]
    for broken in (False, True):
        if broken:
            p = model.bases["flap_cove_roof"]
            changed = p.controls.copy()
            changed[:, 1] = (changed[:, 0] + changed[:, -1]) / 2
            model.bases["flap_cove_roof"] = replace(p, controls=changed)
        native = {}
        for key in {t.base for t in main}:
            p = model.bases[key]
            native[key] = kernel.add_bspline_surface(
                p.controls,
                knots_u=p.knots_u,
                knots_v=p.knots_v,
                mult_u=p.multiplicities_u,
                mult_v=p.multiplicities_v,
                deg_u=p.degree_u,
                deg_v=p.degree_v,
            )
        faces = [kernel.add_trimmed_face(native[t.base], [t.loop]) for t in main]
        path = tmp_path / f"kink-{broken}.igs"
        kernel.export_iges({"main": faces}, path)
        measured = _fcheck(kernel, "F1", {"path": str(path)})
        assert _passed(measured) is not broken, measured


def test_p0570_gm9_fowler_public_edit_bad_inputs_are_visible(kernel, tmp_path):
    import copy

    from pyflightstream.exceptions import InputArtifactError
    from pyflightstream.workspace.geometry_pipeline import add_control_surfaces

    raw = _fowler_config()
    model = _fowler_model(raw)
    faces = []
    for key in ("skin", "root", "tip", "trailing_edge"):
        p = model.bases[key]
        faces.append(
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
    source = tmp_path / "source.igs"
    kernel.export_iges({"panel": faces}, source)
    entry = copy.deepcopy(raw["components"]["panel"]["control"][0])
    entry["gap_sapn"] = 0.01
    entry["cove"]["lip_xx"] = 0.94
    entry["cove"]["p3"]["z_over_cc"] = 0.035
    entry["nose"]["raduis"] = 0.01
    entry["kinematics"][0]["gap_pc"] = 2.0
    result = add_control_surfaces(source, "panel", [entry], tmp_path / "warned.igs")
    assert result["status"] == "passed", result
    for key in ("gap_sapn", "lip_xx", "z_over_cc", "raduis", "gap_pc"):
        assert any(key in warning for warning in result["warnings"]), result
    target = tmp_path / "refused.igs"
    bad = {**entry, "gap_span": "5mm"}
    with pytest.raises(InputValueError, match="gap_span"):
        add_control_surfaces(source, "panel", [bad], target)
    with pytest.raises(InputValueError, match="component"):
        add_control_surfaces(source, "relabeled", [entry], target)
    empty, swapped = tmp_path / "empty.igs", tmp_path / "entry.toml"
    empty.write_text("", encoding="utf-8")
    swapped.write_text("name='flap'", encoding="utf-8")
    for wrong in (empty, swapped):
        with pytest.raises((InputValueError, InputArtifactError)):
            add_control_surfaces(wrong, "panel", [entry], target)
    with pytest.raises((InputValueError, InputArtifactError)):
        add_control_surfaces(source, "panel", [empty], target)
    assert not target.exists()


def test_p0570_gm9_imported_control_validation_keeps_caller_tables():
    import copy

    raw = _fowler_config()
    model = _fowler_model(raw)
    entry = copy.deepcopy(raw["components"]["panel"]["control"][0])
    entry["cove"]["lip_xx"] = 0.94
    before = copy.deepcopy(entry)
    stages.controls.imported(model.bases["skin"], entry)
    assert entry == before, "warning about an unknown key must not delete it from caller data"
