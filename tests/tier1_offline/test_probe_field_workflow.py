# GEOVERSE_HEADER
# file_version: 1.1.5
# last_modified_at: 2026-09-27T20:59:34.961Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.cases.workflows]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind existing behavioral checks to explicit release obligations.
# revision_source: git
"""Probe field declarations retain the emitted sample identities."""

import pytest

from pyflightstream.cases import PprocSpec, ProbesSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, steady_case, unsteady_case


@pytest.mark.parametrize("steady", [False, True])
def test_field_request_samples_components_and_records_layout(tmp_path, steady):
    assert "field_formats" in ProbesSpec.model_fields, "field request schema is missing"
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "probes": [
                {
                    "frame": "REFERENCE",
                    "field_formats": ["vtk", "tecplot"],
                    "reusable_inflow": True,
                    "rectangles": [
                        {
                            "origin": [0, -1, -2],
                            "along_u": [0, 1, -2],
                            "along_v": [0, -1, 2],
                            "points_u": 2,
                            "points_v": 2,
                        }
                    ],
                }
            ],
        }
    )
    case = _with_pproc(
        steady_case() if steady else unsteady_case(), _wb_geometry(tmp_path), pproc=spec
    )
    script = Script("26.124")
    build_script(case, script)
    assert len(script.probe_points) == 4
    layout = script.probe_field_layout
    assert len(layout) == 1 and layout[0]["probe_ids"] == [1, 2, 3, 4]
    assert layout[0]["frame"] == "REFERENCE"
    assert layout[0]["native_to_m"] == 1
    assert layout[0]["formats"] == ["vtk", "tecplot"]
    if not steady:
        assert "UNSTEADY_SOLVER_DELETE_ALL_PLOTS" in script.render()
        for component in ("VX", "VY", "VZ"):
            assert f"NAME {component}4\n" in script.render()


def test_field_request_resolves_the_existing_default_frame():
    spec = ProbesSpec(field_formats=["vtk"])
    assert {"VX", "VY", "VZ"} <= set(spec.parameters)


@pytest.mark.parametrize("steady", [False, True])
def test_volume_section_uses_sampled_field_without_native_index(tmp_path, steady):
    # GOAL033:post:checks:probe_volume_sections
    # GOAL033:capability_ids:items:G39
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "volume_section": {
                "shape": "rectangle",
                "frame": "REFERENCE",
                "plane": "YZ",
                "offset_m": 2,
                "corners_m": [-1, -2, 1, 2],
                "points": [2, 3],
                "format": "vtk",
            },
        }
    )
    case = _with_pproc(
        steady_case() if steady else unsteady_case(), _wb_geometry(tmp_path), pproc=spec
    )
    script = Script("26.124")
    build_script(case, script)
    assert len(script.probe_points) == 6, "volume section must sample its declared grid"
    assert script.probe_field_layout[0]["kind"] == "volume-section"
    assert not any(
        word in script.render()
        for word in (
            "CREATE_NEW_RECTANGLE_VOLUME_SECTION",
            "EXPORT_VOLUME_SECTION",
            "DELETE_VOLUME_SECTION",
        )
    )
    assert {point[1] for point in script.probe_points} == {2.0}


def test_fields_with_general_plots_disabled(tmp_path, monkeypatch):
    import json

    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.run import _write_probe_points
    from pyflightstream.script import Script, helpers
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_f01_probe_source import _post_workspace
    from tests.tier1_offline.test_post_products import PLOTS_HEADER

    w = _post_workspace(tmp_path, monkeypatch)
    (w.inputs_dir / "pproc/p001.toml").write_text(
        '[groups]\n"1"="all"\n[products]\nplots=false\n'
        '[[probes]]\nframe="REFERENCE"\nfield_formats=["vtk","tecplot"]\n'
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
        "Time-step," + ",".join(f"{v}{i}" for i in range(1, 5) for v in ("VX", "VY", "VZ")) + "\n"
    )
    for step in (1, 2):
        history += (
            ",".join(
                map(str, [step] + [v for i in range(1, 5) for v in (10 + step + i, 3 + i, 5 - i)])
            )
            + "\n"
        )
    source = w.sim_dir("7001") / "outputs/AL-020_plots.txt"
    source.write_text(
        PLOTS_HEADER + history + "-" * 60 + "\n     Force Units: Coefficients\n", encoding="utf-8"
    )
    original = source.read_bytes()
    record = w.read_manifest()[0].model_copy(
        update={
            "probe_points_file": relative,
            "solver_setup": helpers.solver_settings(Script("26.124"), velocity=30).model_dump(
                mode="json"
            ),
            "probe_field_layout": [
                {
                    "entry": 1,
                    "kind": "probe-field",
                    "probe_ids": [1, 2, 3, 4],
                    "frame": "REFERENCE",
                    "native_to_m": 1,
                    "formats": ["vtk", "tecplot"],
                    "reusable_inflow": True,
                }
            ],
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    write_campaign_products(w)
    fields = w.root / "post/products/fields"
    assert len(list(fields.glob("*.vtk"))) == 2, "field outputs were suppressed"
    assert len(list(fields.glob("*.dat"))) == 2
    assert len(list(fields.glob("*.inflow.txt"))) == 2
    meta = json.loads(next(fields.glob("*.vtk.provenance.json")).read_text())
    assert meta["sampling"]["frame"] == "REFERENCE"
    assert source.read_bytes() == original


@pytest.mark.parametrize("kind", ["probe", "volume"])
def test_unsteady_named_frame_keeps_local_samples_and_resolved_index(tmp_path, kind):
    payload = {"groups": {"1": "all"}}
    if kind == "probe":
        payload["probes"] = [
            {
                "frame": "MRP",
                "field_formats": ["vtk"],
                "rectangles": [
                    {
                        "origin": [0, -1, -2],
                        "along_u": [0, 1, -2],
                        "along_v": [0, -1, 2],
                        "points_u": 2,
                        "points_v": 2,
                    }
                ],
            }
        ]
    else:
        payload["volume_section"] = {
            "shape": "rectangle",
            "frame": "MRP",
            "plane": "YZ",
            "offset_m": 0,
            "corners_m": [-1, -2, 1, 2],
            "points": [2, 2],
            "format": "vtk",
        }
    case = _with_pproc(
        unsteady_case(), _wb_geometry(tmp_path), pproc=PprocSpec.model_validate(payload)
    )
    script = Script("26.124")
    build_script(case, script)
    layout = script.probe_field_layout[0]
    assert layout["frame"] == "MRP"
    assert layout["frame_index"] == 2
    assert layout["coordinate_source"] == "emitted-local"
    assert layout["export_kind"] == "unsteady-fluid-plot"
    assert layout["points_native"] == [list(point[1:4]) for point in script.probe_points]
    assert all(point[4] == "MRP" for point in script.probe_points)
    assert "FRAME 2" in script.render()


def test_steady_volume_layout_round_trips_through_field_writer(tmp_path):
    from types import SimpleNamespace

    from pyflightstream.post.probe_fields import write_recorded_probe_fields
    from pyflightstream.script import helpers

    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "volume_section": {
                "shape": "rectangle",
                "frame": "REFERENCE",
                "plane": "YZ",
                "offset_m": 2,
                "corners_m": [-1, -2, 1, 2],
                "points": [2, 2],
                "format": "vtk",
            },
        }
    )
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path), pproc=spec)
    script = Script("26.124")
    build_script(case, script)
    # This minimal mesh fixture omits GLOBAL units; state them explicitly.
    script.record_opened_length_unit("METER")
    table = tmp_path / "native.csv"
    table.write_text(
        "PROBE,X,Y,Z,VX,VY,VZ,FRAME\n"
        + "".join(
            f"{i},{x},{y},{z},11,3,5,REFERENCE\n" for i, x, y, z, _frame in script.probe_points
        )
    )
    record = SimpleNamespace(
        run_id="round-trip",
        campaign=None,
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(),
        probe_field_layout=script.probe_field_layout,
        frame_motions=script.frame_motions,
        fs_exe_sha256="68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65",
        fs_build="8172026",
    )
    written = write_recorded_probe_fields(table, record, tmp_path / "fields", "volume")
    assert any(path.suffix == ".vtk" for path in written)


def test_millimeter_volume_fluid_plot_vertex_is_si_but_record_is_native():
    from pyflightstream.cases.workflows import _pproc_sampled_volume

    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "volume_section": {
                "shape": "rectangle",
                "frame": "REFERENCE",
                "plane": "YZ",
                "offset_m": 2,
                "corners_m": [-1, -2, 1, 2],
                "points": [2, 2],
                "format": "vtk",
            },
        }
    )
    case = unsteady_case().model_copy(update={"pproc": spec})
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    _pproc_sampled_volume(case, script, {"REFERENCE": 1}, 0, unsteady=True)
    vertices = [
        list(map(float, line.split()[1:]))
        for line in script.render().splitlines()
        if line.startswith("VERTEX ")
    ]
    assert vertices[0] == [2.0, -1.0, -2.0]
    assert list(script.probe_points[0][1:4]) == [2000.0, -1000.0, -2000.0]
    layout = script.probe_field_layout[0]
    assert layout["points_native"][0] == [2000.0, -1000.0, -2000.0]
    assert layout["native_to_m"] == 0.001
    assert layout["command_coordinate_units"] == "m"
