from pathlib import Path

import pytest

from pyflightstream._fsm import MeshReadError, saved_length_unit, saved_mesh_coordinate_unit


@pytest.mark.parametrize("head,display", [("1\n5", "METER"), (".001\n2", "MILLIMETER")])
def test_measured_build_stores_meter_coordinates_for_both_display_units(
    tmp_path: Path, head: str, display: str
) -> None:
    # Synthetic structural excerpt; native paired rotation evidence measured
    # equal stored vertices despite 1000x different command-frame coordinates.
    path = tmp_path / "geometry.fsm"
    path.write_text(f"26,1\n8172026\n$GLOBAL_START$\n{head}\n$GLOBAL_END$\n")
    assert saved_length_unit(path) == display
    assert saved_mesh_coordinate_unit(path) == "METER"


def test_display_head_does_not_transfer_storage_proof_to_another_build(tmp_path: Path) -> None:
    path = tmp_path / "geometry.fsm"
    path.write_text("26,1\n9999999\n$GLOBAL_START$\n.001\n2\n$GLOBAL_END$\n")
    assert saved_length_unit(path) == "MILLIMETER"
    with pytest.raises(MeshReadError, match="stored mesh coordinate units are not measured"):
        saved_mesh_coordinate_unit(path)


def test_placeholder_does_not_invent_a_coordinate_unit(tmp_path: Path) -> None:
    path = tmp_path / "geometry.fsm"
    path.write_text("placeholder")
    assert saved_mesh_coordinate_unit(path) is None
