"""Planning a body with a legacy build record must give an actionable refusal."""
# ruff: noqa: N999 - the assigned lane name is rfixG.

import json
import sys
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._geometry_record import judge_the_row_geometry
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix

pytestmark = pytest.mark.requirement("P0400-RFIXG-RECORD")


def legacy_record() -> dict:
    """The legacy record's field shape, with neutral paths and synthetic values."""
    return {
        "source": "source/body.fsm",
        "source_sha256": "a" * 64,
        "obj": "geometries/body.obj",
        "obj_sha256": "b" * 64,
        "te_file_sha256": "c" * 64,
        "f001_sha256": "d" * 64,
        "blades": 2,
        "stations": 2,
        "panels_per_side": 2,
        "faces_per_blade": 4,
        "vertices_per_blade": 4,
        "faces_total": 8,
        "te_edges_per_blade": 1,
        "blade_volume_m3": 0.001,
        "radii_m": [0.1, 0.2],
        "chord_m": [0.02, 0.01],
        "beta_deg": [20.0, 10.0],
        "struct_radii_m": [0.1, 0.2],
        "struct_chord_m": [0.02, 0.01],
        "struct_beta_deg": [20.0, 10.0],
        "pitch_axis_from_quarter_chord_in_section_m": [[0.0, 0.0], [0.0, 0.0]],
        "omega_rad_per_s": 10.0,
        "time_increment_s": 0.01,
        "rpm": 100.0,
    }


@pytest.mark.requirement("FR-473")
def test_p0400_rfixg_legacy_record_is_refused_by_matrix_plan(tmp_path: Path) -> None:
    workspace = make_library(
        tmp_path / "ws", register_build=("26.125", Path(sys.executable).as_posix())
    )
    folder = workspace.inputs_dir / "geometries" / "body"
    folder.mkdir()
    (folder / "body.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    (folder / "body.boundaries.toml").write_text('boundaries = ["Body"]\n', encoding="utf-8")
    record = folder / "body.build.json"
    record.write_text(json.dumps(legacy_record()), encoding="utf-8")
    row = (
        "9401 | TestGeom | GEOM | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
        "| 003 | 26.125 | 0 | 1 | OUTPUTS: loads_{point}.txt / VELOCITY: 30.0 / GEOMETRY: body.obj"
    )
    matrix = write_matrix(tmp_path / "matrix.fs", [row])
    with pytest.raises(InputArtifactError) as caught:
        resolve_matrix(matrix, workspace, name="matrix", fs_version="26.125", recipes=RECIPES)
    message = str(caught.value)
    assert str(record) in message
    assert "instruction.file" in message and "missing" in message


@pytest.mark.requirement("FR-473")
@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"instruction": {"sha256": "a" * 64}}, "instruction.file"),
        ({"instruction": {"file": "body.toml"}}, "instruction.sha256"),
        (
            {"instruction": {"file": "body.toml", "sha256": "a" * 64}, "inputs": [{}]},
            "inputs[0].file",
        ),
    ],
)
def test_p0400_rfixg_incomplete_input_record_names_missing_key(
    tmp_path: Path, data, key: str
) -> None:
    body = tmp_path / "body.fsm"
    body.write_text("saved", encoding="utf-8")
    record = tmp_path / "body.build.json"
    record.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        judge_the_row_geometry(body, "9401", fs_build="26.125", mesh_import=None)
    assert str(record) in str(caught.value) and key in str(caught.value)


@pytest.mark.requirement("FR-473")
@pytest.mark.parametrize(
    ("data", "diagnosis"),
    [
        ([], "expected an object"),
        ({"inputs": None}, "inputs must be a list"),
        ({"instruction": {"file": "", "sha256": "a" * 64}}, "instruction.file"),
        ({"instruction": {"file": "body.toml", "sha256": 10}}, "instruction.sha256"),
    ],
)
def test_p0400_rfixg_uninterpretable_record_is_refused(
    tmp_path: Path, data, diagnosis: str
) -> None:
    body = tmp_path / "body.fsm"
    body.write_text("saved", encoding="utf-8")
    record = tmp_path / "body.build.json"
    record.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        judge_the_row_geometry(body, "9401", fs_build="26.125", mesh_import=None)
    assert str(record) in str(caught.value) and diagnosis in str(caught.value)
