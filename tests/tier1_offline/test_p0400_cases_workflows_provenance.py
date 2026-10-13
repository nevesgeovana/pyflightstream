"""Reference coordinates keep the field's originally declared frame in provenance."""

import json
from types import SimpleNamespace

from pyflightstream.post.probe_fields import write_recorded_probe_fields
from pyflightstream.script import Script, helpers


def test_p0400_cw_provenance_a_reference_field_keeps_its_declared_frame(tmp_path):
    """P0400-CW-PROBES (PFS-2105.027): writing metadata preserves the separate declaration."""
    requirement = "P0400-CW-PROBES"
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    source = tmp_path / "probes.csv"
    source.write_text(
        "PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ" + chr(10) + "1,NA,1,2,3,REFERENCE,11,3,5" + chr(10),
        encoding="utf-8",
    )
    layout = dict(
        entry=1,
        probe_ids=[1],
        frame="REFERENCE",
        declared_frame="PROBE_F",
        frame_index=1,
        coordinate_frame_index=1,
        coordinate_source="native-export-reference",
        export_kind="steady-probe",
        native_to_m=1.0,
        formats=["vtk"],
        reusable_inflow=False,
        points_native=[[1, 2, 3]],
    )
    record = SimpleNamespace(
        run_id="steady",
        campaign=None,
        probe_field_layout=[layout],
        frame_motions=script.frame_motions,
        fs_exe_sha256="9" * 64,
        fs_build="8172026",
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    paths = write_recorded_probe_fields(source, record, tmp_path / "out", "P")
    vtk = next(path for path in paths if path.suffix == ".vtk")
    metadata = json.loads(vtk.with_suffix(".vtk.provenance.json").read_text())["sampling"]
    assert metadata["declared_frame"] == "PROBE_F", requirement
    assert metadata["frame"] == "REFERENCE"
