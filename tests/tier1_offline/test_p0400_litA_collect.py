"""Reproduce collect_outputs of a surface VTK with its solver-created wake sidecar."""

# ruff: noqa: N999 - the release lane requires this filename.

from pathlib import Path

import pytest

from pyflightstream.workspace import CampaignWorkspace, WorkspaceError
from pyflightstream.workspace.naming import PointName

WAKE_BYTES = (Path(__file__).parent / "fixtures/p0400_lita_solver_wake.vtk").read_bytes()


@pytest.mark.requirement("FR-92")
@pytest.mark.parametrize("ran_in_datapoint", [False, True])
def test_p0400_lita_collect_files_the_optional_wake_and_records_it(tmp_path, ran_in_datapoint):
    workspace = CampaignWorkspace(tmp_path / "campaign")
    sim = workspace.create_sim("9001")
    source = sim / "datapoints/DP-AL+040" if ran_in_datapoint else sim
    source.mkdir(parents=True, exist_ok=True)
    surface = source / "surface.vtk"
    surface.write_bytes(b"surface export")
    wake = source / "surface_wakes.vtk"
    wake.write_bytes(WAKE_BYTES)
    collected = workspace.collect_outputs(
        "9001", [surface], datapoint=PointName("AL+040"), ran_in_datapoint=ran_in_datapoint
    )
    assert collected == [
        "datapoints/DP-AL+040/surface.vtk",
        "datapoints/DP-AL+040/surface_wakes.vtk",
    ]
    assert (sim / collected[1]).read_bytes() == WAKE_BYTES
    assert not (sim / "surface_wakes.vtk").exists()


@pytest.mark.requirement("FR-92")
def test_p0400_lita_a_held_wake_refuses_before_the_surface_is_moved(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "campaign")
    sim = workspace.create_sim("9001")
    surface = sim / "surface.vtk"
    wake = sim / "surface_wakes.vtk"
    surface.write_bytes(b"surface export")
    wake.write_bytes(WAKE_BYTES)
    folder = sim / "datapoints/DP-AL+040"
    folder.mkdir(parents=True)
    (folder / wake.name).write_bytes(b"earlier wake export")
    with pytest.raises(WorkspaceError, match="already"):
        workspace.collect_outputs("9001", [surface], datapoint=PointName("AL+040"))
    assert surface.is_file() and wake.is_file()


@pytest.mark.requirement("NFR-14")
def test_p0400_lita_only_the_authorized_recorded_wake_bytes_are_admitted():
    from tests.tier1_offline.test_house_style import RECORDED_WAKE_PATH, _geometry_offenses

    assert _geometry_offenses([RECORDED_WAKE_PATH], read=lambda path: WAKE_BYTES) == []
    assert _geometry_offenses([RECORDED_WAKE_PATH], read=lambda path: b"changed") == [
        RECORDED_WAKE_PATH
    ]
    other = "tests/tier1_offline/fixtures/another_wake.vtk"
    assert _geometry_offenses([other], read=lambda path: WAKE_BYTES) == [other]
