"""Probe samples retain coordinates, components and explicit point topology."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

import pyflightstream.post as post
from pyflightstream._errors import ProductError, collecting_warnings
from pyflightstream.cases.workflows._freestream import _read_custom_freestream
from pyflightstream.post.field_frames import native_velocity_proof
from pyflightstream.post.probe_fields import point_field_products
from pyflightstream.script import Script, helpers


@pytest.mark.parametrize(
    ("column", "cell"),
    [(column, cell) for column in ("PROBE", "X", "VX") for cell in ("NA", "invalid", "inf")]
    + [("STEP", cell) for cell in ("invalid", "inf")],
)
def test_p0430_w012_invalid_sample_names_source_and_column(tmp_path, column, cell):
    from pyflightstream.post.probe_fields import write_recorded_probe_fields

    cells = dict(PROBE="1", STEP="2", X="0", Y="1", Z="2", VX="3", VY="4", VZ="5")
    cells[column] = cell
    source = tmp_path / "samples.csv"
    source.write_text(",".join(cells) + "\n" + ",".join(cells.values()) + "\n", encoding="utf-8")
    record = SimpleNamespace(
        run_id="control",
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
    with pytest.raises(ValueError) as caught:
        write_recorded_probe_fields(source, record, tmp_path / "fields", "point")
    assert isinstance(caught.value, ProductError)
    assert source.name in str(caught.value) and column in str(caught.value)
    assert "row 2" in str(caught.value)
    assert not (tmp_path / "fields").exists()


@pytest.mark.parametrize("values", [[["bad", 0, 0]], [[object(), 0, 0]], [[0], [0, 1]]])
def test_p0430_w012_nonnumeric_field_is_product_error(tmp_path, values):
    provenance = post.OutputProvenance(
        run_id="test/point", setup=helpers.solver_settings(Script("26.124"), velocity=30)
    )
    with pytest.raises((ValueError, TypeError)) as caught:
        post.write_probe_field(
            tmp_path / "field",
            values,
            [[0, 0, 0]],
            source=tmp_path / "source",
            provenance=provenance,
        )
    assert isinstance(caught.value, ProductError)
    assert not list(tmp_path.glob("field*"))


def test_p0430_historical_dash_step_is_an_unstamped_field(tmp_path):
    from pyflightstream.post.probe_fields import write_recorded_probe_fields

    source = tmp_path / "source.csv"
    source.write_text("PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ\n1,-,0,1,2,REFERENCE,11,3,5\n")
    record = SimpleNamespace(
        run_id="control",
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
    paths = write_recorded_probe_fields(source, record, tmp_path / "fields", "point")
    assert any(path.suffix == ".vtk" for path in paths)


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


def test_recorded_moving_field_uses_final_motion_ledger(tmp_path, monkeypatch):
    # GOAL033:post:checks:velocity_fields
    # GOAL033:capability_ids:items:G61
    from types import SimpleNamespace

    import pyflightstream.post.probe_fields as fields

    # One case covers both recorded steps, so the obligation is proved by a
    # case that is not named after one step.
    for step in (1, 2):
        root = tmp_path / f"step-{step}"
        root.mkdir()
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
        monkeypatch.setattr(
            fields, "native_velocity_proof", lambda *a, _p=proof, **k: _p, raising=False
        )
        source = root / "source.csv"
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
            solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(
                mode="json"
            ),
        )
        paths = fields.write_recorded_probe_fields(source, record, root / "fields", "point")
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


def test_recorded_millimetre_rotor_field_keeps_units_frames_and_vertex_topology(tmp_path):
    # GOAL033:post:checks:units_frames_topology
    # Units: a MILLIMETER run's local samples are written in metres, with the
    # velocity convention the package's recorded native receipt establishes
    # for that unit (not a synthetic proof). Frames: rotor-local samples are
    # carried into REFERENCE through the recorded rotation. Topology: both
    # writers keep one vertex per sample, in sample order.
    from types import SimpleNamespace

    import pyflightstream.post.probe_fields as fields

    identity = {
        "fs_exe_sha256": "9" * 64,
        "fs_build": "8172026",
    }
    motion = {
        "frame_index": 4,
        "state": "known",
        "reason": None,
        "solver_version": "26.124",
        "length_unit": "MILLIMETER",
        "origin_native": [4500.0, 0, 0],
        "x_axis": [1, 0, 0],
        "y_axis": [0, 1, 0],
        "z_axis": [0, 0, 1],
        "trajectory": {
            "kind": "constant_rotation",
            "center_native": [4500.0, 0, 0],
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
    source = tmp_path / "source.csv"
    source.write_text(
        "PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ\n"
        "1,1,5000,1000,0,ROTOR,11,3,5\n"
        "2,1,6000,0,2000,ROTOR,12,-4,6\n"
    )
    layout = {
        "entry": 1,
        "probe_ids": [1, 2],
        "frame": "ROTOR",
        "frame_index": 4,
        "native_to_m": 0.001,
        "formats": ["vtk", "tecplot"],
        "reusable_inflow": False,
        "export_kind": "unsteady-fluid-plot",
        "coordinate_source": "emitted-local",
    }
    record = SimpleNamespace(
        run_id="moving-mm",
        campaign=None,
        probe_field_layout=[layout],
        frame_motions={4: motion},
        **identity,
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    paths = fields.write_recorded_probe_fields(source, record, tmp_path / "fields", "point")
    # Rotation of -pi/2 about +x after one step: (y, z) -> (z, -y), about the
    # rotor centre at x = 4.5 m; local millimetres become reference metres.
    expected_points = np.array([[9.5, 0.0, -1.0], [10.5, 2.0, 0.0]])
    # The recorded MILLIMETER fluid-plot receipt measured velocity already in
    # m/s with REFERENCE components, so the vectors pass through unchanged.
    expected_velocity = np.array([[11.0, 3.0, 5.0], [12.0, -4.0, 6.0]])

    vtk = next(p for p in paths if p.suffix == ".vtk")
    lines = vtk.read_text().splitlines()
    start = lines.index("POINTS 2 float") + 1
    points = np.array([[float(x) for x in row.split()] for row in lines[start : start + 2]])
    assert np.allclose(points, expected_points, rtol=0, atol=1e-9), points
    assert "VERTICES 2 4" in lines, "each sample must be its own vertex"
    start = lines.index("VECTORS Velocity float") + 1
    vectors = np.array([[float(x) for x in row.split()] for row in lines[start : start + 2]])
    assert np.allclose(vectors, expected_velocity, rtol=0, atol=1e-9), vectors

    tecplot = next(p for p in paths if p.suffix == ".dat")
    rows = tecplot.read_text().splitlines()
    zones = [row for row in rows if row.startswith("ZONE")]
    assert len(zones) == 2 and all("I=1, J=1, K=1" in zone for zone in zones)
    data = np.array(
        [
            [float(x) for x in row.split()]
            for row in rows[2:]
            if row.strip() and not row.startswith("ZONE")
        ]
    )
    assert np.allclose(data, np.column_stack((expected_points, expected_velocity)), atol=1e-9)

    for path in (vtk, tecplot):
        sampling = json.loads(path.with_name(path.name + ".provenance.json").read_text())[
            "sampling"
        ]
        assert sampling["coordinate_units"] == "m"
        assert sampling["velocity_units"] == "m/s"
        assert sampling["topology"] == "vertex-cloud"
        assert sampling["frame"] == "REFERENCE" and sampling["declared_frame"] == "ROTOR"
        convention = sampling["velocity_convention"]
        assert convention["length_unit"] == "MILLIMETER"
        assert convention["coordinate_to_m"] == 0.001
        assert convention["velocity_to_m_s"] == 1.0
        assert convention["evidence"]["receipt"] == (
            "GOAL-033/g61-moving-millimeter-fluid-si-comparison"
        )


def test_documented_synthetic_field_example_executes(tmp_path):
    # GOAL033:post:checks:reusable_inflow
    import runpy
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "docs/examples/_sources/sampled_field_export.py"
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


def test_steady_field_uses_measured_reference_export_and_si_velocity(tmp_path):
    # GOAL033:post:checks:variable_correspondence
    from types import SimpleNamespace

    from pyflightstream.post.probe_fields import write_recorded_probe_fields

    # One case covers metres and millimetres, so the obligation is proved
    # by a case that is not named after one length unit.
    for unit, scale in (("METER", 1.0), ("MILLIMETER", 1000.0)):
        root = tmp_path / unit
        root.mkdir()
        script = Script("26.124")
        script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
        source = root / "probes.csv"
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
            fs_exe_sha256="9" * 64,
            fs_build="8172026",
            solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(
                mode="json"
            ),
        )
        paths = write_recorded_probe_fields(source, record, root / "out", "P")
        vtk = next(p for p in paths if p.suffix == ".vtk")
        lines = vtk.read_text().splitlines()
        pi = next(i for i, row in enumerate(lines) if row.startswith("POINTS ")) + 1
        vi = next(i for i, row in enumerate(lines) if row.startswith("VECTORS ")) + 1
        np.testing.assert_allclose([float(x) for x in lines[pi].split()], [1, 2, 3])
        np.testing.assert_allclose([float(x) for x in lines[vi].split()], [11, 3, 5])
        metadata = json.loads(vtk.with_suffix(".vtk.provenance.json").read_text())["sampling"]
        assert metadata["frame"] == "REFERENCE" and metadata["declared_frame"] == "MRP"
        assert metadata["velocity_convention"]["velocity_to_m_s"] == 1 / scale


_FR153_FIELD_BUILD_WARNING__MEASURED = "8172026"


#: A build nobody registered (8242026 is the Linux build of 8172026, RPT-083).
_FR153_FIELD_BUILD_WARNING__OTHER = "8999999"


_FR153_FIELD_BUILD_WARNING__DIGEST = "a" * 64


#: The proof each measured export kind and unit returned before FR-153's
#: warning rule, written out: the control that the measured build is unchanged.
_FR153_FIELD_BUILD_WARNING__BEFORE = {
    ("unsteady-fluid-plot", "METER"): (
        1.0,
        1.0,
        {
            "receipt": "GOAL-033/g61-velocity-comparison",
            "receipt_sha256": "af4cc684043546188b4de86320c00b8a45041d7da40b6b2cd62b0172cf55130b",
            "native_plot_sha256": (
                "2f34cf5dd7053a462f19fd618757c274bd4e076d01059e7c38d43d3bcf139a29"
            ),
            "comparison": "nineteen coincident fixed/moving samples at six actual STEPs",
        },
    ),
    ("unsteady-fluid-plot", "MILLIMETER"): (
        0.001,
        1.0,
        {
            "receipt": "GOAL-033/g61-moving-millimeter-fluid-si-comparison",
            "receipt_sha256": "4193840726b01d12b9cfd81c854636ed5b9328a431d315020f5cde8b505c62b6",
            "native_plot_sha256": (
                "effbbb615dc64144fe0e7f685f8f6c2f8b966532db16ffe3f3b1029b8fed7f33"
            ),
            "comparison": "all76 columns at six STEPs exactly match the METER control",
        },
    ),
    ("steady-probe", "METER"): (1.0, 1.0, None),
    ("steady-probe", "MILLIMETER"): (0.001, 0.001, None),
}


_FR153_FIELD_BUILD_WARNING__STEADY = {
    "receipt": "GOAL-033/g61-probe-basis-comparison",
    "receipt_sha256": "58b314eaf3aa7ce2cb7823255b8b8031e99bc6b67664cae000b17c321316e9cb",
    "comparison": "same four samples under reference, fixed and rotating analysis frames",
}


def _fr153_field_build_warning___motion(version="26.124", unit="METER"):
    """A fixed REFERENCE sampling frame, recorded as the script records one."""
    return {
        "frame_index": 1,
        "state": "known",
        "reason": None,
        "solver_version": version,
        "length_unit": unit,
        "origin_native": [0.0, 0.0, 0.0],
        "x_axis": [1, 0, 0],
        "y_axis": [0, 1, 0],
        "z_axis": [0, 0, 1],
        "trajectory": {"kind": "fixed"},
        "proof": {"geometry": {"source": "synthetic"}},
    }


def _fr153_field_build_warning___layout(ids):
    return {
        "entry": 1,
        "kind": "probe-field",
        "probe_ids": ids,
        "frame": "REFERENCE",
        "frame_index": 1,
        "native_to_m": 1,
        "formats": ["vtk"],
        "reusable_inflow": True,
        "export_kind": "unsteady-fluid-plot",
        "coordinate_source": "emitted-local",
    }


def _fr153_field_build_warning___rotating(version="26.124"):
    """A frame turning at -800 rev/min about X, recorded before any build was bound."""
    from tests.tier1_offline.test_motion_ledger import placed_script

    script, hub, moving = placed_script()
    helpers.rotary_motion(
        script, frame=hub, axis="X", rpm=-800, boundaries=[1], moving_frames=[moving]
    )
    helpers.unsteady_solver(script, time_iterations=6, delta_time=0.00625)
    motion = {**script.frame_motions[moving], "solver_version": version}
    assert motion["state"] == "unknown" and motion["trajectory"]["kind"] == "constant_rotation"
    return moving, motion


def _fr153_field_build_warning___point(
    tmp_path,
    *,
    build=_FR153_FIELD_BUILD_WARNING__MEASURED,
    version="26.124",
    unit="METER",
    rotating=False,
    native_to_m=1,
):
    """Write one point's fields over two STEPs; return (entries, warning texts)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    table = tmp_path / "probes.csv"
    rows = [(i, y, z) for i, (y, z) in enumerate([(-1, -2), (-1, 2), (1, -2), (1, 2)], 1)]
    index, motion = (
        _fr153_field_build_warning___rotating(version)
        if rotating
        else (1, _fr153_field_build_warning___motion(version, unit))
    )
    frame = motion.get("frame_name") or "REFERENCE"
    table.write_text(
        "PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ\n"
        + "".join(
            f"{i},{step},0,{y},{z},{frame},{10 + step + i},{3 + i},{5 - i}\n"
            for step in (1, 2)
            for i, y, z in rows
        ),
        encoding="utf-8",
    )
    record = SimpleNamespace(
        run_id="r1",
        campaign=None,
        probe_field_layout=[
            {
                **_fr153_field_build_warning___layout([1, 2, 3, 4]),
                "frame": frame,
                "frame_index": index,
                "native_to_m": native_to_m,
            }
        ],
        frame_motions={index: motion},
        fs_exe_sha256=_FR153_FIELD_BUILD_WARNING__DIGEST,
        fs_build=build,
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    with collecting_warnings() as caught:
        entries = point_field_products(table, record, tmp_path / "out", "P1")
    return entries, [str(warning.message) for warning in caught]


class TestFr153FieldBuildWarning:
    """FR-153: a field of a measured solver version and unit on another build is written, warned.

    The native velocity convention of 26.124 was measured on build 8172026. A run of
    26.124 in a measured unit on another build gets that convention, its field is
    written, one warning per point names both builds and the field's products.json
    entry records ``proven`` False. Another solver version or unit keeps the refusal,
    and the measured build is unchanged: its proof is the dictionary the package
    returned before this rule, key for key.
    """

    @staticmethod
    @pytest.mark.parametrize(("kind", "unit"), sorted(_FR153_FIELD_BUILD_WARNING__BEFORE))
    def test_fr153_the_measured_build_returns_the_proof_it_returned_before(kind, unit):
        to_m, velocity, evidence = _FR153_FIELD_BUILD_WARNING__BEFORE[(kind, unit)]
        proof = native_velocity_proof(
            {"solver_version": "26.124", "length_unit": unit},
            solver_identity={
                "fs_exe_sha256": _FR153_FIELD_BUILD_WARNING__DIGEST,
                "fs_build": _FR153_FIELD_BUILD_WARNING__MEASURED,
            },
            export_kind=kind,
        )
        assert json.dumps(proof) == json.dumps(
            {
                "state": "known",
                "fs_exe_sha256": _FR153_FIELD_BUILD_WARNING__DIGEST,
                "fs_build": _FR153_FIELD_BUILD_WARNING__MEASURED,
                "length_unit": unit,
                "export_kind": kind,
                "coordinate_to_m": to_m,
                "velocity_to_m_s": velocity,
                "components": "REFERENCE",
                "velocity_kind": "absolute",
                "origin_rule": "none",
                "evidence": evidence or _FR153_FIELD_BUILD_WARNING__STEADY,
            }
        )

    @staticmethod
    def test_fr153_the_measured_build_writes_the_field_and_warns_nothing(tmp_path):
        entries, warned = _fr153_field_build_warning___point(tmp_path)
        assert warned == []
        names = sorted(path.name for path in entries)
        assert any(name.endswith("_step_1.inflow.dat") for name in names), names
        assert any(name.endswith("_step_2.inflow.dat") for name in names), names
        assert all(entry == {"kind": "probe-field"} for entry in entries.values())

    @staticmethod
    def test_fr153_another_build_writes_the_field_warns_once_and_records_proven_false(tmp_path):
        measured, _ = _fr153_field_build_warning___point(tmp_path / "measured")
        entries, warned = _fr153_field_build_warning___point(
            tmp_path / "other", build=_FR153_FIELD_BUILD_WARNING__OTHER
        )
        assert len(warned) == 1, warned
        assert warned[0].startswith("point=P1 product=fields/P1: ")
        assert (
            f"build {_FR153_FIELD_BUILD_WARNING__MEASURED}" in warned[0]
            and f"build {_FR153_FIELD_BUILD_WARNING__OTHER}" in warned[0]
        )
        assert "FR-153" in warned[0]
        assert sorted(p.name for p in entries) == sorted(p.name for p in measured)
        for entry in entries.values():
            assert entry == {
                "kind": "probe-field",
                "velocity_convention": {
                    "measured_on_build": _FR153_FIELD_BUILD_WARNING__MEASURED,
                    "run_build": _FR153_FIELD_BUILD_WARNING__OTHER,
                    "proven": False,
                },
            }
        # The same convention: the SI inflow files are the measured build's, byte for byte.
        inflows = sorted(p for p in entries if p.name.endswith(".inflow.dat"))
        assert inflows
        for path in inflows:
            twin = next(p for p in measured if p.name == path.name)
            assert path.read_bytes() == twin.read_bytes()
        provenance = json.loads(
            next(p for p in entries if p.name.endswith(".vtk.provenance.json")).read_text()
        )
        convention = provenance["sampling"]["velocity_convention"]
        assert (
            convention["proven"] is False
            and convention["measured_on_build"] == _FR153_FIELD_BUILD_WARNING__MEASURED
        )
        assert convention["fs_build"] == _FR153_FIELD_BUILD_WARNING__OTHER

    @staticmethod
    @pytest.mark.parametrize(
        ("version", "unit"), [("26.122", "METER"), ("26.124", "INCH")], ids=["version", "unit"]
    )
    def test_fr153_another_solver_version_or_unit_is_refused_as_before(tmp_path, version, unit):
        with pytest.raises(ProductError, match="has no evidence for this export/build/unit"):
            _fr153_field_build_warning___point(
                tmp_path, build=_FR153_FIELD_BUILD_WARNING__OTHER, version=version, unit=unit
            )
        with pytest.raises(ProductError, match="has no evidence for this export/build/unit"):
            _fr153_field_build_warning___point(
                tmp_path / "measured-build", version=version, unit=unit
            )
        assert not list((tmp_path / "out").rglob("*.inflow.dat"))

    @staticmethod
    def test_fr153_the_post_writes_one_warning_line_and_the_manifest_entry(tmp_path, monkeypatch):
        from pyflightstream.post.products import write_campaign_products
        from pyflightstream.run._pending import _write_probe_points
        from pyflightstream.workspace import CampaignWorkspace
        from tests.tier1_offline.test_f01_probe_source import _post_workspace
        from tests.tier1_offline.test_post_products import PLOTS_HEADER

        w = _post_workspace(tmp_path, monkeypatch)
        (w.inputs_dir / "pproc/p001.toml").write_text(
            '[groups]\n"1"="all"\n[products]\nplots=false\n'
            '[[probes]]\nframe="REFERENCE"\nfield_formats=["vtk"]\n'
            "reusable_inflow=true\nrectangles=[{origin=[0,-1,-2],"
            "along_u=[0,1,-2],along_v=[0,-1,2],points_u=2,points_v=2}]\n",
            encoding="utf-8",
        )
        positions = [
            (i, 0, y, z, "REFERENCE")
            for i, (y, z) in enumerate([(-1, -2), (-1, 2), (1, -2), (1, 2)], 1)
        ]
        relative = _write_probe_points(w.sim_dir("7001"), "7001", positions)
        history = (
            "Time-step,"
            + ",".join(f"{v}{i}" for i in range(1, 5) for v in ("VX", "VY", "VZ"))
            + "\n"
        )
        for step in (1, 2):
            values = [step] + [v for i in range(1, 5) for v in (10 + step + i, 3 + i, 5 - i)]
            history += ",".join(map(str, values)) + ",\n"
        (w.sim_dir("7001") / "outputs/AL-020_plots.txt").write_text(
            PLOTS_HEADER
            + history
            + "-" * 60
            + "\n     Force Units: Coefficients\n"
            + "Software : Flightstream version 26.1, build #7012026\n",
            encoding="utf-8",
        )
        record = w.read_manifest()[0].model_copy(
            update={
                "probe_points_file": relative,
                "solver_setup": helpers.solver_settings(Script("26.124"), velocity=30).model_dump(
                    mode="json"
                ),
                "probe_field_layout": [_fr153_field_build_warning___layout([1, 2, 3, 4])],
                "frame_motions": {1: _fr153_field_build_warning___motion()},
                "fs_exe_sha256": _FR153_FIELD_BUILD_WARNING__DIGEST,
                "fs_build": _FR153_FIELD_BUILD_WARNING__OTHER,
            }
        )
        monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
        write_campaign_products(w)
        out = w.root / "post/products"
        manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
        fields = {name: entry for name, entry in manifest["products"].items() if "fields/" in name}
        assert any(name.endswith(".inflow.dat") for name in fields), manifest.get("skipped")
        for entry in fields.values():
            assert entry["velocity_convention"] == {
                "measured_on_build": _FR153_FIELD_BUILD_WARNING__MEASURED,
                "run_build": _FR153_FIELD_BUILD_WARNING__OTHER,
                "proven": False,
            }
        lines = [
            line
            for line in (out / "post.log").read_text(encoding="utf-8").splitlines()
            if "velocity convention" in line
        ]
        assert len(lines) == 1, lines
        assert lines[0].startswith("WARNING point=")
        assert (
            f"build {_FR153_FIELD_BUILD_WARNING__MEASURED}" in lines[0]
            and f"build {_FR153_FIELD_BUILD_WARNING__OTHER}" in lines[0]
        )

    @staticmethod
    def test_fr153_a_rotating_frame_of_the_measured_build_is_unchanged(tmp_path):
        from pyflightstream.script.motion import _ROTARY_PROOFS, resolve_frame_motion

        entries, warned = _fr153_field_build_warning___point(tmp_path, rotating=True)
        assert warned == []
        assert any(p.name.endswith("_step_2.vtk") for p in entries)
        assert all(entry == {"kind": "probe-field"} for entry in entries.values())
        _, motion = _fr153_field_build_warning___rotating()
        timing = resolve_frame_motion(
            motion,
            solver_identity={
                "fs_exe_sha256": _FR153_FIELD_BUILD_WARNING__DIGEST,
                "fs_build": _FR153_FIELD_BUILD_WARNING__MEASURED,
            },
        )["proof"]["timing"]
        # The control: the measured row with the run's digest and unit, nothing added.
        assert timing == {
            **_ROTARY_PROOFS[("26.124", "METER", _FR153_FIELD_BUILD_WARNING__MEASURED)],
            "fs_exe_sha256": _FR153_FIELD_BUILD_WARNING__DIGEST,
            "length_unit": "METER",
        }

    @staticmethod
    def test_fr153_a_rotating_frame_of_another_build_is_written_with_one_warning(tmp_path):
        measured, _ = _fr153_field_build_warning___point(tmp_path / "measured", rotating=True)
        entries, warned = _fr153_field_build_warning___point(
            tmp_path / "other", build=_FR153_FIELD_BUILD_WARNING__OTHER, rotating=True
        )
        assert len(warned) == 1, warned
        assert (
            f"build {_FR153_FIELD_BUILD_WARNING__MEASURED}" in warned[0]
            and f"build {_FR153_FIELD_BUILD_WARNING__OTHER}" in warned[0]
        )
        assert "rotating-frame timing" in warned[0]
        unproven = {
            "measured_on_build": _FR153_FIELD_BUILD_WARNING__MEASURED,
            "run_build": _FR153_FIELD_BUILD_WARNING__OTHER,
            "proven": False,
        }
        assert sorted(p.name for p in entries) == sorted(p.name for p in measured)
        for entry in entries.values():
            assert entry == {
                "kind": "probe-field",
                "velocity_convention": unproven,
                "rotation_timing": unproven,
            }
        inflows = [p for p in entries if p.name.endswith(".inflow.dat")]
        assert inflows
        for path in inflows:
            twin = next(p for p in measured if p.name == path.name)
            assert path.read_bytes() == twin.read_bytes()

    @staticmethod
    def test_fr153_a_rotating_frame_of_another_solver_version_is_refused(tmp_path):
        from pyflightstream.script.motion import resolve_frame_motion

        with pytest.raises(ProductError, match="has no evidence for this export/build/unit"):
            _fr153_field_build_warning___point(
                tmp_path, build=_FR153_FIELD_BUILD_WARNING__OTHER, version="26.122", rotating=True
            )
        _, motion = _fr153_field_build_warning___rotating("26.122")
        for build in (_FR153_FIELD_BUILD_WARNING__MEASURED, _FR153_FIELD_BUILD_WARNING__OTHER):
            resolved = resolve_frame_motion(
                motion,
                solver_identity={
                    "fs_exe_sha256": _FR153_FIELD_BUILD_WARNING__DIGEST,
                    "fs_build": build,
                },
            )
            assert resolved["state"] == "unknown"


@pytest.mark.parametrize("rotating", [False, True], ids=["fixed-frame", "rotating-frame"])
def test_p0410_pc_field_warning_names_only_unproven_conventions(tmp_path, rotating: bool) -> None:
    """PFS-2116.048: velocity evidence and rotation evidence are distinct claims."""
    entries, warned = _fr153_field_build_warning___point(
        tmp_path, build=_FR153_FIELD_BUILD_WARNING__OTHER, rotating=rotating
    )

    assert entries
    assert len(warned) == 1
    diagnostic = warned[0].lower()
    assert "velocity" in diagnostic, diagnostic
    if rotating:
        assert "rotating-frame timing" in diagnostic, diagnostic
    else:
        assert "rotating-frame timing" not in diagnostic, diagnostic
    for entry in entries.values():
        assert entry["velocity_convention"]["proven"] is False
        if rotating:
            assert entry["rotation_timing"]["proven"] is False


def test_p0410_pc_timing_only_warning_does_not_discredit_proven_velocity(
    tmp_path, monkeypatch
) -> None:
    """PFS-2116.048: unproven rotation timing cannot invalidate velocity evidence."""
    from pyflightstream.post.field_frames import VELOCITY_EVIDENCE

    # Supply velocity evidence for this synthetic build while leaving its
    # rotation timing unproven. Both consumers read the public evidence table.
    for key, evidence in list(VELOCITY_EVIDENCE.items()):
        if key[1] == _FR153_FIELD_BUILD_WARNING__MEASURED:
            monkeypatch.setitem(
                VELOCITY_EVIDENCE,
                (key[0], _FR153_FIELD_BUILD_WARNING__OTHER, *key[2:]),
                evidence,
            )
    entries, warned = _fr153_field_build_warning___point(
        tmp_path, build=_FR153_FIELD_BUILD_WARNING__OTHER, rotating=True
    )

    assert entries
    for entry in entries.values():
        assert entry["rotation_timing"]["proven"] is False
        assert entry.get("velocity_convention", {}).get("proven", True) is True
    assert len(warned) == 1
    diagnostic = warned[0].lower()
    assert "rotating-frame timing" in diagnostic, diagnostic
    assert "native velocity convention" not in diagnostic, diagnostic


def _f4_0304_point(*, v_inf, v_ref, cl):
    loads = SimpleNamespace(
        freestream_velocity_m_s=v_inf,
        reference_velocity_m_s=v_ref,
        total={"CL": cl},
        angle_of_attack_deg=0.0,
        sideslip_deg=0.0,
    )
    return SimpleNamespace(
        name="p", loads=loads, state=SimpleNamespace(density_kg_m3=1.0), vorticity_selection=False
    )


def test_f4_0304_free_stream_lift_is_compared_with_the_solver_cl_on_one_basis(tmp_path):
    """F-143, F-146, X-F-0321: VINF-based traced lift meets the VREF-based CL on one q."""
    import tests.tier1_offline.test_regression_farfield_products as wing
    from tests.tier1_offline.test_post_products import at_twice_the_free_stream

    # The reference velocity is twice the free stream's and the native CL a quarter of the
    # traced one: on one basis they are the same lift, so Trefftz A states no shortfall.
    workspace = wing._farfield_products___workspace(tmp_path, farfield=True)
    at_twice_the_free_stream(workspace)
    said = wing._farfield_products___post(workspace)
    traced = [message for message in said if "Trefftz A traces" in message]
    assert not traced, traced


def test_f4_0304_a_missing_selected_family_is_a_named_skip(tmp_path, monkeypatch):
    """F-476: a selected family without an XZ distribution is named, not dropped silently."""
    import tests.tier1_offline.test_regression_farfield_products as wing
    from pyflightstream.workspace import RunRecord

    def record(**fields):
        return RunRecord(**{**fields, "inventory": ["W", "H"]})

    monkeypatch.setattr(wing, "_FarfieldProductsRunRecord", record)
    workspace = wing._farfield_products___workspace(tmp_path, farfield=True)
    wing._farfield_products___post(workspace)
    products = wing._farfield_products___one(tmp_path, "products.json")
    skipped = json.loads(products.read_text(encoding="utf-8")).get("skipped", {})
    named = [why for key, why in skipped.items() if key.endswith("#family=H")]
    assert named and "H" in named[0]


def test_f4_0304_the_manifest_names_the_exports_a_far_field_file_consumed(tmp_path):
    """F-502: inputs lists the consumed export files, not the run ids again."""
    import tests.tier1_offline.test_regression_farfield_products as wing

    workspace = wing._farfield_products___workspace(tmp_path, farfield=True)
    wing._farfield_products___post(workspace)
    manifest = json.loads(
        wing._farfield_products___one(tmp_path, "products.json").read_text(encoding="utf-8")
    )
    (entry,) = [
        value
        for key, value in wing._farfield_products___items(manifest.get("products", manifest))
        if key.endswith("_trefftz.csv")
    ]
    (consumed,) = entry["inputs"].values()
    assert any(name.endswith("_sloads.txt") for name in consumed), consumed
    assert any(name.endswith("_wakes.vtk") for name in consumed), consumed
    assert entry["runs"] not in consumed


def test_f4_0304_a_reduced_far_field_file_records_its_window_and_sample_count(tmp_path):
    """F-504: the average of a far-field table states the window and the samples it holds."""
    from pathlib import Path

    import tests.tier1_offline.test_regression_farfield_products as wing

    stem = wing._FFPROOF_POST___STEM
    workspace = wing._ffproof_post___campaign(
        tmp_path,
        pproc=wing._FFPROOF_POST___LEDGERS,
        files={
            f"{stem}_plots.txt": wing._ffproof_post___plots_export(
                len(wing._FFPROOF_POST___POINTS_M), 8
            )
        },
        recipe="unsteady",
        reductions=wing._FFPROOF_POST___WINDOW,
        positions=True,
    )
    wing._ffproof_post___post(workspace)
    manifest = wing._ffproof_post___manifest(Path(workspace.root))
    average = wing._ffproof_post___entry(manifest, "_ledgers_average.csv")
    assert average["reduced_from"] == {stem: {"window": [5.0, 8.0], "samples": 4}}
    assert average["inputs"] == {stem: [f"outputs/{stem}_plots.txt"]}
    assert "reduced_from" not in wing._ffproof_post___entry(manifest, "_ledgers_instant.csv")


def test_f4_0304_one_absent_point_set_keeps_the_other_analysis(tmp_path):
    """F-1246: a missing lattice leaves the C plane written, and the absence is named."""
    from pathlib import Path

    import tests.tier1_offline.test_regression_farfield_products as wing

    workspace = wing._farfield_products___workspace(tmp_path, farfield=True)
    pproc = Path(workspace.inputs_dir) / "pproc" / "p001.toml"
    ledgers = (
        '[farfield.ledgers]\nframe = "MRP"\ntip_radius_m = 1.0\n'
        "stations = [-1.0, 1.0]\nn_r = 2\nn_psi = 16\nm_max = 2\n"
    )
    pproc.write_text(pproc.read_text(encoding="utf-8") + ledgers, encoding="utf-8")
    wing._farfield_products___post(workspace)
    root = Path(workspace.root)
    skipped = json.loads(wing._farfield_products___one(root, "products.json").read_text("utf-8"))[
        "skipped"
    ]
    assert any(key.endswith("#absent=lattice") for key in skipped), skipped
    rows = wing._farfield_products___table(
        wing._farfield_products___one(root, "farfield/*_trefftz.csv")
    )
    assert [row["VARIANT"] for row in rows if row["VARIANT"] == "C"] == ["C"]
    assert not list(root.rglob("farfield/*_ledgers*.csv"))


def test_pfs_2124_031_each_file_carries_the_conventions_its_own_layout_borrowed(tmp_path):
    """The writer states each file's unproven conventions; no second lookup rebuilds them."""
    unproven = {
        "measured_on_build": _FR153_FIELD_BUILD_WARNING__MEASURED,
        "run_build": _FR153_FIELD_BUILD_WARNING__OTHER,
        "proven": False,
    }

    def named(case, **keywords):
        entries, _warned = _fr153_field_build_warning___point(tmp_path / case, **keywords)
        assert entries
        return {key for entry in entries.values() for key in entry if key != "kind"}, [
            entry for entry in entries.values()
        ]

    # nothing borrowed: a measured build states no convention
    assert named("measured", rotating=True)[0] == set()
    # the velocity convention alone: a fixed frame of another build
    keys, entries = named("fixed", build=_FR153_FIELD_BUILD_WARNING__OTHER)
    assert keys == {"velocity_convention"}
    assert all(entry["velocity_convention"] == unproven for entry in entries)
    # both: a rotating frame of another build borrows the velocity convention and the timing
    keys, entries = named("rotating", build=_FR153_FIELD_BUILD_WARNING__OTHER, rotating=True)
    assert keys == {"velocity_convention", "rotation_timing"}
    assert all(entry["rotation_timing"] == unproven for entry in entries)
