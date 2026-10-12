"""Tier 1, 0.40.0: a deflection sweep builds one sibling geometry per angle (FR-472).

P0400-GEOM-SWEEP (PFS-2081.41). Run from ``inputs/geometries/``, one
instruction with a ``[sweep]`` renders one script per angle, each lofting the
wing with its control surface at that angle, into ``<name>_<SURFACE><sign><ttt>``.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._geometry_build import plan_geometry_build
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0400_geometry_build import geometry, workspace
from tests.tier1_offline.test_p0400_geometry_instruction import CCS_WING, ccs_text

SWEEP = CCS_WING + '[sweep]\ncontrol_surface = "AIL"\nangle_deg = [-10.0, 0.0, 10.0]\n'


def _wing(tmp_path, text=SWEEP):
    root = workspace(tmp_path)
    folder = geometry(root, "wing", text, source=None)
    (folder / "wing_sections.csv").write_text(ccs_text(), encoding="utf-8")
    return root, folder


def _surface_angle(script_text: str) -> float:
    line = next(
        line for line in script_text.splitlines() if line.startswith("NEW_CCS_WING_CONTROL_SURFACE")
    )
    return float(line.split()[7])


@pytest.mark.requirement("FR-472")
def test_p0400_geom_sweep_one_script_per_angle_into_sibling_folders(tmp_path):
    """P0400-GEOM-SWEEP (PFS-2081.41): the tags, the folders and each script's angle."""
    root, folder = _wing(tmp_path)
    plan = plan_geometry_build("wing", cwd=folder.parent)
    assert [v.tag for v in plan.variants] == ["AIL-100", "AIL+000", "AIL+100"]
    assert [v.folder.name for v in plan.variants] == [
        "wing_AIL-100",
        "wing_AIL+000",
        "wing_AIL+100",
    ]
    assert all(v.folder.parent == folder.parent for v in plan.variants)
    assert [_surface_angle(v.script.text) for v in plan.variants] == [-10.0, 0.0, 10.0]
    assert all(v.instruction.sweep is None for v in plan.variants)


@pytest.mark.requirement("FR-472")
def test_p0400_geom_sweep_only_builds_the_named_variants(tmp_path):
    """P0400-GEOM-SWEEP (PFS-2081.41): R2, --only, and an unknown tag is refused."""
    _, folder = _wing(tmp_path)
    plan = plan_geometry_build("wing", cwd=folder.parent, only=("AIL+100",))
    assert [v.tag for v in plan.variants] == ["AIL+100"]
    with pytest.raises(InputArtifactError, match="AIL\\+200"):
        plan_geometry_build("wing", cwd=folder.parent, only=("AIL+200",))


@pytest.mark.requirement("FR-472")
def test_p0400_geom_sweep_from_inside_its_folder_is_refused(tmp_path):
    """P0400-GEOM-SWEEP (PFS-2081.41): R4, the variants never live inside the base folder."""
    _, folder = _wing(tmp_path)
    with pytest.raises(InputArtifactError, match="level above"):
        plan_geometry_build(None, cwd=folder)


@pytest.mark.requirement("FR-472")
@pytest.mark.parametrize(
    "angles",
    ["[]", "[1.0, 1.0]", "[1.0, 1.04]"],
    ids=["empty", "repeated", "one-tag"],
)
def test_p0400_geom_sweep_values_that_cannot_name_their_folders_are_refused(tmp_path, angles):
    """P0400-GEOM-SWEEP (PFS-2081.41): R4, an empty list or two values with one tag."""
    text = CCS_WING + f'[sweep]\ncontrol_surface = "AIL"\nangle_deg = {angles}\n'
    _, folder = _wing(tmp_path, text)
    with pytest.raises(InputArtifactError, match="angle_deg|tag"):
        plan_geometry_build("wing", cwd=folder.parent)


@pytest.mark.requirement("FR-472")
def test_p0400_geom_sweep_refuses_a_foreign_folder_of_a_variant_name(tmp_path, monkeypatch):
    """P0400-GEOM-SWEEP (PFS-2081.41): R4, a foreign folder."""
    import pyflightstream.cases._geometry_emit as geometry_emit

    monkeypatch.setattr(geometry_emit, "_awaiting_evidence", lambda script, commands: ())
    root, folder = _wing(tmp_path)
    (folder.parent / "wing_AIL+100").mkdir()
    monkeypatch.chdir(folder.parent)
    assert main(["geometry", "build", "wing", "--apply", "--overwrite"]) == 2


@pytest.mark.requirement("FR-472")
def test_p0400_geom_sweep_prints_the_matrix_cells_of_each_variant(tmp_path, monkeypatch, capsys):
    """P0400-GEOM-SWEEP (PFS-2081.41): R3, the CONFIGURATION and GEOMETRY cells."""
    _, folder = _wing(tmp_path)
    monkeypatch.chdir(folder.parent)
    assert main(["geometry", "build", "wing"]) == 0
    out = capsys.readouterr().out
    assert "CONFIGURATION AIL-100 | GEOMETRY wing_AIL-100.fsm" in out
