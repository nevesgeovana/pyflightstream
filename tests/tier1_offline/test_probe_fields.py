# GEOVERSE_HEADER
# file_version: 1.2.8
# last_modified_at: 2026-09-27T23:40:40.346Z
# last_modified_by: OpenAI / Codex / unknown / api-designer-pyflightstream
# dependencies: [pyflightstream.post]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Keep reusable inflow filenames consistent with UNSTRUCTURED workspace input.
# revision_source: git
"""Probe samples retain coordinates, components and explicit point topology."""

import json

import numpy as np
import pytest

import pyflightstream.post as post
from pyflightstream.cases.workflows import _read_custom_freestream
from pyflightstream.script import Script, helpers


@pytest.mark.parametrize("format_name", ["vtk", "tecplot"])
def test_probe_field_round_trip_and_provenance(tmp_path, format_name):
    # GOAL033:post:checks:vtk
    # GOAL033:post:checks:tecplot
    writer = getattr(post, "write_probe_field", None)
    assert callable(writer), "the public probe-field writer is missing"
    points = np.array([[0, -1, -2], [0, -1, 2], [0, 1, -2], [0, 1, 2]], dtype=float)
    velocity = np.array([[11, 1, 2], [12, 3, 4], [13, 5, 6], [14, 7, 8]], dtype=float)
    source = tmp_path / "sample.csv"
    source.write_text("recorded probe samples\n", encoding="utf-8")
    before = source.read_bytes()
    provenance = post.OutputProvenance(
        run_id="test/point",
        setup=helpers.solver_settings(Script("26.124"), velocity=30.0),
    )
    paths = writer(
        tmp_path / "field",
        points,
        velocity,
        source=source,
        provenance=provenance,
        formats=(format_name,),
        reusable_inflow=True,
    )
    inflow = tmp_path / "field.inflow.dat"
    np.testing.assert_array_equal(np.loadtxt(inflow), np.column_stack((points, velocity)))
    assert _read_custom_freestream(str(inflow), "UNSTRUCTURED") == (-1, 1, -2, 2)
    extension = "vtk" if format_name == "vtk" else "dat"
    lines = (tmp_path / f"field.{extension}").read_text().splitlines()
    if format_name == "vtk":
        assert "VERTICES 4 8" in lines and "VECTORS Velocity float" in lines
        start = lines.index("POINTS 4 float") + 1
        np.testing.assert_array_equal(np.loadtxt(lines[start : start + 4]), points)
        start = lines.index("VECTORS Velocity float") + 1
        np.testing.assert_array_equal(np.loadtxt(lines[start : start + 4]), velocity)
    else:
        zones = [line for line in lines if line.startswith("ZONE")]
        assert len(zones) == 4 and all("I=1, J=1, K=1" in zone for zone in zones)
        data = np.loadtxt([line for line in lines[2:] if not line.startswith("ZONE")])
        np.testing.assert_array_equal(data, np.column_stack((points, velocity)))
    meta = json.loads((tmp_path / f"field.{extension}.provenance.json").read_text())
    assert meta["sampling"]["coordinate_units"] == "m"
    assert meta["sampling"]["velocity_units"] == "m/s"
    assert meta["sampling"]["frame"] == "REFERENCE"
    assert meta["sampling"]["topology"] == "vertex-cloud"
    assert meta["sampling"]["source_sha256"]
    assert all(path.is_file() for path in paths)
    assert source.read_bytes() == before


@pytest.mark.parametrize("bad", ["frame", "plane", "nan"])
def test_invalid_reusable_field_writes_nothing(tmp_path, bad):
    writer = getattr(post, "write_probe_field", None)
    assert callable(writer), "the public probe-field writer is missing"
    points = np.array([[0, -1, -1], [0, 1, 1]], dtype=float)
    velocity = np.ones((2, 3))
    frame = "MRP" if bad == "frame" else "REFERENCE"
    if bad == "plane":
        points[1, 0] = 1
    if bad == "nan":
        velocity[0, 0] = np.nan
    source = tmp_path / "source.csv"
    source.write_text("source", encoding="utf-8")
    provenance = post.OutputProvenance(
        run_id="test/point", setup=helpers.solver_settings(Script("26.124"), velocity=30.0)
    )
    with pytest.raises(ValueError):
        writer(
            tmp_path / "field",
            points,
            velocity,
            source=source,
            provenance=provenance,
            reusable_inflow=True,
            frame=frame,
        )
    assert not list(tmp_path.glob("field*"))


def test_recorded_field_converts_units_and_keeps_steps_separate(tmp_path):
    from types import SimpleNamespace

    import pyflightstream.post.probe_fields as fields

    writer = getattr(fields, "write_recorded_probe_fields", None)
    assert callable(writer), "recorded field integration is missing"
    source = tmp_path / "probes.csv"
    source.write_text(
        "PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ\n"
        "1,10,0,-1000,-2000,REFERENCE,11,2,3\n"
        "2,10,0,-1000,2000,REFERENCE,12,4,5\n"
        "3,10,0,1000,-2000,REFERENCE,13,6,7\n"
        "4,10,0,1000,2000,REFERENCE,14,8,9\n"
        "1,20,0,-1000,-2000,REFERENCE,21,2,3\n"
        "2,20,0,-1000,2000,REFERENCE,22,4,5\n"
        "3,20,0,1000,-2000,REFERENCE,23,6,7\n"
        "4,20,0,1000,2000,REFERENCE,24,8,9\n",
        encoding="utf-8",
    )
    record = SimpleNamespace(
        run_id="run",
        campaign="campaign",
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
        probe_field_layout=[
            {
                "entry": 1,
                "kind": "probe-field",
                "probe_ids": [1, 2, 3, 4],
                "frame": "REFERENCE",
                "native_to_m": 0.001,
                "formats": ["vtk"],
                "reusable_inflow": True,
            }
        ],
    )
    paths = writer(source, record, tmp_path / "fields", "point")
    inflows = sorted(p for p in paths if p.name.endswith(".inflow.dat"))
    assert len(inflows) == 2
    first, second = [np.loadtxt(p) for p in inflows]
    np.testing.assert_array_equal(first[:, 1:3], [[-1, -2], [-1, 2], [1, -2], [1, 2]])
    assert first[0, 3] == 11 and second[0, 3] == 21
    assert source.read_text().startswith("PROBE,STEP")


@pytest.mark.parametrize("bad", ["late_nan", "step_alias", "frame", "formats"])
def test_recorded_fields_preflight_writes_nothing(tmp_path, bad):
    from types import SimpleNamespace

    from pyflightstream.post.probe_fields import write_recorded_probe_fields

    rows = ["1,1,0,1,2,REFERENCE,11,3,5", "1,2,0,1,2,REFERENCE,12,4,6"]
    if bad == "late_nan":
        rows[1] = "1,2,0,1,2,REFERENCE,nan,4,6"
    if bad == "step_alias":
        rows[1] = "1,1.0,0,1,2,REFERENCE,12,4,6"
    if bad == "frame":
        rows[1] = "1,2,0,1,2,MRP,12,4,6"
    source = tmp_path / "source.csv"
    source.write_text("PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ\n" + "\n".join(rows) + "\n")
    layout = dict(
        entry=1,
        probe_ids=[1],
        frame="REFERENCE",
        native_to_m=1,
        formats=["vtk"],
        reusable_inflow=False,
    )
    layouts = [layout]
    if bad == "formats":
        layouts.append({**layout, "entry": 2, "formats": ["unknown"]})
    record = SimpleNamespace(
        run_id="control",
        campaign=None,
        probe_field_layout=layouts,
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    output = tmp_path / "fields"
    with pytest.raises(ValueError):
        write_recorded_probe_fields(source, record, output, "point")
    assert not output.exists() or not list(output.iterdir())


@pytest.mark.parametrize("step", [1, 2])
def test_recorded_moving_field_uses_final_motion_ledger(tmp_path, monkeypatch, step):
    # GOAL033:post:checks:velocity_fields
    # GOAL033:capability_ids:items:G61
    from types import SimpleNamespace

    import pyflightstream.post.probe_fields as fields

    identity = {"fs_exe_sha256": "a" * 64, "fs_build": "8172026"}
    motion = {
        "frame_index": 4,
        "state": "known",
        "reason": None,
        "solver_version": "26.124",
        "length_unit": "METER",
        "origin_native": [4.5, 0, 0],
        "x_axis": [1, 0, 0],
        "y_axis": [0, 1, 0],
        "z_axis": [0, 0, 1],
        "trajectory": {
            "kind": "constant_rotation",
            "center_native": [4.5, 0, 0],
            "axis_reference": [1, 0, 0],
            "omega_rad_s": -np.pi / 2,
            "dt_s": 1,
            "step_time_origin": 0,
            "start_time_s": 0,
        },
        "proof": {
            "geometry": {"source": "synthetic"},
            "timing": {**identity, "evidence": {"receipt_sha256": "b" * 64}},
        },
    }
    proof = {
        **identity,
        "state": "known",
        "length_unit": "METER",
        "export_kind": "unsteady-fluid-plot",
        "components": "REFERENCE",
        "velocity_kind": "absolute",
        "origin_rule": "none",
        "evidence": {"receipt_sha256": "c" * 64},
    }
    monkeypatch.setattr(fields, "native_velocity_proof", lambda *a, **k: proof, raising=False)
    source = tmp_path / "source.csv"
    source.write_text(f"PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ\n1,{step},5,1,0,ROTOR,11,3,5\n")
    layout = {
        "entry": 1,
        "probe_ids": [1],
        "frame": "ROTOR",
        "frame_index": 4,
        "native_to_m": 1,
        "formats": ["vtk"],
        "reusable_inflow": False,
        "export_kind": "unsteady-fluid-plot",
        "coordinate_source": "emitted-local",
    }
    record = SimpleNamespace(
        run_id="moving",
        campaign=None,
        probe_field_layout=[layout],
        frame_motions={4: motion},
        **identity,
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    paths = fields.write_recorded_probe_fields(source, record, tmp_path / "fields", "point")
    vtk = next(p for p in paths if p.suffix == ".vtk")
    lines = vtk.read_text().splitlines()
    point_line = next(i for i, line in enumerate(lines) if line.startswith("POINTS ")) + 1
    actual = [float(x) for x in lines[point_line].split()]
    angle = -step * np.pi / 2
    np.testing.assert_allclose(actual, [9.5, np.cos(angle), np.sin(angle)], atol=1e-12)
    metadata = json.loads(vtk.with_suffix(".vtk.provenance.json").read_text())["sampling"]
    assert metadata["frame"] == "REFERENCE"
    assert metadata["declared_frame"] == "ROTOR"
    assert metadata["velocity_convention"]["evidence"] == proof["evidence"]
    assert motion["origin_native"] == [4.5, 0, 0]


def test_documented_synthetic_field_example_executes(tmp_path):
    # GOAL033:post:checks:reusable_inflow
    import runpy
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "examples/sampled_field_export.py"
    main = runpy.run_path(str(example))["main"]
    assert main(["--output", str(tmp_path / "example")]) == 0
    output = tmp_path / "example"
    source = np.loadtxt(output / "synthetic-source.csv", delimiter=",", skiprows=1)
    inflow = np.loadtxt(output / "synthetic-field.inflow.dat")
    np.testing.assert_array_equal(source, inflow)
    meta = json.loads((output / "synthetic-field.vtk.provenance.json").read_text())
    assert meta["sampling"]["data_origin"] == "synthetic example; no native solver execution"


def test_recorded_field_refuses_invented_step_ordinal(tmp_path):
    from types import SimpleNamespace

    from pyflightstream.post.probe_fields import write_recorded_probe_fields

    table = tmp_path / "probes.csv"
    table.write_text("PROBE,STEP,X,Y,Z,VX,VY,VZ\n1,1,0,0,0,11,3,5\n")
    plots = tmp_path / "plots.csv"
    plots.write_text("VX1,VY1,VZ1\n11,3,5\n")
    record = SimpleNamespace(
        run_id="test",
        campaign=None,
        probe_field_layout=[
            dict(
                entry=1,
                probe_ids=[1],
                frame="REFERENCE",
                native_to_m=1,
                formats=["vtk"],
                reusable_inflow=False,
            )
        ],
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    with pytest.raises(ValueError, match="STEP|Time-step"):
        write_recorded_probe_fields(table, record, tmp_path / "out", "P", step_source=plots)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("unit,scale", [("METER", 1.0), ("MILLIMETER", 1000.0)])
def test_steady_field_uses_measured_reference_export_and_si_velocity(tmp_path, unit, scale):
    # GOAL033:post:checks:variable_correspondence
    from types import SimpleNamespace

    from pyflightstream.post.probe_fields import write_recorded_probe_fields

    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
    source = tmp_path / "probes.csv"
    source.write_text(
        "PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ\n"
        f"1,NA,{scale},{2 * scale},{3 * scale},MRP,{11 * scale},{3 * scale},{5 * scale}\n"
    )
    layout = dict(
        entry=1,
        probe_ids=[1],
        frame="MRP",
        frame_index=2,
        coordinate_frame_index=1,
        coordinate_source="native-export-reference",
        export_kind="steady-probe",
        native_to_m=1 / scale,
        formats=["vtk"],
        reusable_inflow=False,
        points_native=[[0, 0, 0]],
    )
    record = SimpleNamespace(
        run_id="steady",
        campaign=None,
        probe_field_layout=[layout],
        frame_motions=script.frame_motions,
        fs_exe_sha256="68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65",
        fs_build="8172026",
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    paths = write_recorded_probe_fields(source, record, tmp_path / "out", "P")
    vtk = next(p for p in paths if p.suffix == ".vtk")
    lines = vtk.read_text().splitlines()
    pi = next(i for i, row in enumerate(lines) if row.startswith("POINTS ")) + 1
    vi = next(i for i, row in enumerate(lines) if row.startswith("VECTORS ")) + 1
    np.testing.assert_allclose([float(x) for x in lines[pi].split()], [1, 2, 3])
    np.testing.assert_allclose([float(x) for x in lines[vi].split()], [11, 3, 5])
    metadata = json.loads(vtk.with_suffix(".vtk.provenance.json").read_text())["sampling"]
    assert metadata["frame"] == "REFERENCE" and metadata["declared_frame"] == "MRP"
    assert metadata["velocity_convention"]["velocity_to_m_s"] == 1 / scale
