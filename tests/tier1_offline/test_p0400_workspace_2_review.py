"""P0400-REVIEW: acceptance gaps exercised through their consumers."""

import numpy
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import CampaignWorkspace, costs, hpc, refine_mesh
from pyflightstream.workspace._refine._obj import read_te
from tests.p0380_mesh_fixtures import Composite, sheet_with_strips, write_source
from tests.tier1_offline.test_p0400_workspace_2_refine_wing import wing


@pytest.mark.parametrize("selector", ["hpc", "cost"])
def test_p0400_review_cli_selection_is_restored(tmp_path, monkeypatch, selector):
    from pyflightstream.run import cli

    hpc.select_hpc_profile(None)
    costs.select_cost_file(None)
    observed = []
    monkeypatch.setattr(cli, "resolve_matrix_arguments", lambda args: None)
    monkeypatch.setattr(
        cli,
        "_cmd_plan",
        lambda *args: (
            observed.append((hpc._SELECTED_HPC.get(), costs._SELECTED_COST_FILE.get())) or 0
        ),
    )
    flag, name = ("--hpc", "h002") if selector == "hpc" else ("--cost-file", "c002")
    try:
        args = ["plan", "batch.fs", "--workspace", str(tmp_path)]
        assert cli.main([*args, flag, name]) == 0
        assert cli.main(args) == 0
        assert observed[0] == ((name, None) if selector == "hpc" else (None, name))
        assert observed[1] == (None, None)
    finally:
        hpc.select_hpc_profile(None)
        costs.select_cost_file(None)


@pytest.mark.parametrize("reader", ["artifact", "reference_points"])
def test_p0400_review_toml_encoding_refusal_names_file(tmp_path, reader):
    from pyflightstream.workspace.sidecars import load_toml

    path = tmp_path / "inputs" / "reference_points.toml"
    path.parent.mkdir()
    path.write_bytes(b"# " + bytes([233]))
    with pytest.raises(InputArtifactError, match="UTF-8") as caught:
        if reader == "artifact":
            load_toml(path, "reference")
        else:
            CampaignWorkspace(tmp_path).reference_points()
    assert str(path) in str(caught.value)


def test_p0400_review_detected_points_require_mesh_units(tmp_path):
    mesh = wing()
    mesh = Composite(mesh.verts, mesh.families, numpy.zeros((0, 3)), {})
    src = write_source(tmp_path / "src", "wing", mesh)
    src.with_suffix(".boundaries.toml").write_text(
        '[trailing_edges]\ndetect = { surfaces = ["U"] }\n', encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match=r"\[import\].*units"):
        refine_mesh(src, spanwise=2, families=["U"], keep_first_row=["U"])


def test_p0400_review_remesh_does_not_invent_trailing_edges(tmp_path):
    points = numpy.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
    te = numpy.array([[0.5, 0, 0], [0.5, 1, 0]])
    mesh = Composite(points, {"A": [[0, 1, 2, 3]]}, te, {})
    src = write_source(
        tmp_path / "src",
        "plate",
        mesh,
        refine_toml='[families.A]\nfactor = 1\nmethod = "remesh"\n',
    )
    level = refine_mesh(src)
    _, actual = read_te(level.obj.with_suffix(".te.txt"))
    assert len(actual) == 2
    assert sorted(actual.tolist()) == sorted(te.tolist())


def test_p0400_review_grid_does_not_fill_a_wake_gap(tmp_path):
    mesh = wing(root=False)
    mesh = Composite(mesh.verts, mesh.families, mesh.te[[0, 2, 3]], {})
    src = write_source(tmp_path / "src", "wing", mesh)
    level = refine_mesh(src, 1, families=["U"])
    _, actual = read_te(level.obj.with_suffix(".te.txt"))
    assert len(actual) == len(mesh.te)
    assert sorted(actual.tolist()) == sorted(mesh.te.tolist())


@pytest.mark.parametrize("unit", ["MILLIMETER", None])
def test_p0400_review_shared_target_has_honest_units(tmp_path, unit):
    mesh = sheet_with_strips((("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)),))
    src = write_source(tmp_path / "src", "wing", mesh)
    side = src.with_suffix(".boundaries.toml")
    text = side.read_text("utf-8")
    if unit is not None:
        text += f'\n[import]\nunits = "{unit}"\n'
    side.write_text(text, "utf-8")
    # Keep the points in the mesh's units as well.
    te = src.with_suffix(".te.txt")
    te.write_text(te.read_text("utf-8").replace("METER", unit or "METER"), "utf-8")
    level = refine_mesh(src, 2, families=["G"])
    entry = level.report["T"]
    if unit is None:
        assert "shared_edge_target_m" not in entry
        assert entry["shared_edge_target_mesh_units"]["max"] > 0
    else:
        assert entry["shared_edge_target_m"]["max"] < 0.001


@pytest.mark.parametrize("angle", [0, 90, 180])
@pytest.mark.parametrize("hand", [-1, 1])
def test_p0400_review_trailing_edge_follows_family_orientation(tmp_path, angle, hand):
    from tests.tier1_offline.test_p0390_firstrow import _tube_source

    mesh = _tube_source(sharp_le=True)
    theta, tilt = numpy.radians([angle, 37])
    azimuth = numpy.array(
        [
            [numpy.cos(theta), -numpy.sin(theta), 0],
            [numpy.sin(theta), numpy.cos(theta), 0],
            [0, 0, 1],
        ]
    )
    inclined = numpy.array(
        [
            [numpy.cos(tilt), 0, numpy.sin(tilt)],
            [0, hand, 0],
            [-numpy.sin(tilt), 0, numpy.cos(tilt)],
        ]
    )
    rotation = azimuth @ inclined
    direction = rotation @ numpy.array([1.0, 0.0, 0.0])
    transformed = Composite(mesh.verts @ rotation.T, mesh.families, numpy.zeros((0, 3)), {})
    config = (
        "[families.Wing]\nspanwise = 2\nkeep_first_row = true\n"
        f"trailing_edge_direction = {direction.tolist()}\n"
    )
    src = write_source(tmp_path / "src", "wing", transformed, refine_toml=config)
    side = src.with_suffix(".boundaries.toml")
    side.write_text(
        side.read_text("utf-8") + '\n[import]\nunits = "METER"\n'
        '[trailing_edges]\ndetect = { surfaces = ["Wing"] }\n',
        "utf-8",
    )
    level = refine_mesh(src)
    _, actual = read_te(level.obj.with_suffix(".te.txt"))
    assert actual @ direction == pytest.approx(numpy.ones(len(actual)), abs=1e-8)


def test_p0400_review_inspection_uses_shared_row_resolution():
    from pyflightstream.cases import SimCase, SweepAxis
    from pyflightstream.cases.workflows import row_solver_setting
    from pyflightstream.workspace.setup_inspection import inspect_case_setup

    case = SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"NCPUS": "4", "SYMMETRY_LOADS": " "},
        solver={"max_threads": 8, "symmetry_loads": True},
    )
    assert row_solver_setting(case, "max_threads") == (4, True)
    assert row_solver_setting(case, "symmetry_loads") == (True, False)
    settings = inspect_case_setup(case, "26.124")["settings"]
    assert settings["max_threads"]["value"] == 4
    assert settings["symmetry_loads"]["provenance"] == "setup"


def test_p0400_review_ambiguous_sharp_edges_are_refused(tmp_path):
    from tests.tier1_offline.test_p0390_firstrow import _tube_source

    src = write_source(
        tmp_path / "src",
        "wing",
        _tube_source(sharp_le=True),
        refine_toml="[families.Wing]\nspanwise = 2\nkeep_first_row = true\n",
    )
    side = src.with_suffix(".boundaries.toml")
    side.write_text(
        side.read_text("utf-8") + '\n[import]\nunits = "METER"\n'
        '[trailing_edges]\ndetect = { surfaces = ["Wing"] }\n',
        "utf-8",
    )
    with pytest.raises(InputArtifactError, match="trailing_edge_direction"):
        refine_mesh(src)
