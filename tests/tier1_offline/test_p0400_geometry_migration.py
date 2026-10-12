"""Tier 1, 0.40.0: the in-row routes warn, and the converter writes the instruction (FR-476).

P0400-GEOM-MIGRATE (PFS-2081.41). Option A of the geometry stage: a row naming
a CCS, IGES or STL file, or a sidecar that scales, renames or mirrors, still
plans and runs as in 0.39.0, with a warning naming the exact replacement; the
converter writes the instruction that builds the same body.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.cases.mesh import MeshImport, MeshOperation
from pyflightstream.workspace._geometry_instruction import read_geometry_instruction
from pyflightstream.workspace._geometry_record import judge_the_row_geometry
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0400_geometry_build import wing_obj, workspace
from tests.tier1_offline.test_p0400_geometry_instruction import ccs_text


def _warnings(geometry, mesh_import=None) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        judge_the_row_geometry(geometry, "7001", fs_build="26.124", mesh_import=mesh_import)
    return [
        str(item.message) for item in caught if issubclass(item.category, PyflightstreamWarning)
    ]


@pytest.mark.requirement("FR-476")
@pytest.mark.parametrize(
    ("name", "built"), [("wing.csv", "wing.fsm"), ("rig.igs", "rig.fsm"), ("hull.stl", "hull.obj")]
)
def test_p0400_geom_migrate_an_in_row_source_warns_with_the_replacement(tmp_path, name, built):
    """P0400-GEOM-MIGRATE (PFS-2081.41): R1, the converter, the build and the cell, and 0.41.0."""
    folder = tmp_path / "inputs" / "geometries" / name.split(".")[0]
    folder.mkdir(parents=True)
    geometry = folder / name
    geometry.write_text("x\n", encoding="utf-8")
    (texts,) = _warnings(geometry)
    assert "POL 7001" in texts and "0.41.0 refuses" in texts
    assert f"pyfs-workspace geometry from-sidecar {name} --apply" in texts
    assert f"pyfs-workspace geometry build {folder.name} --apply" in texts
    assert f"name {built} in the GEOMETRY cell" in texts


@pytest.mark.requirement("FR-476")
def test_p0400_geom_migrate_sidecar_operations_warn_and_translate_does_not(tmp_path):
    """P0400-GEOM-MIGRATE (PFS-2081.41): R1, scale, rename and mirror move; translate stays."""
    geometry = tmp_path / "blade.obj"
    geometry.write_text("x\n", encoding="utf-8")
    moving = MeshImport(
        units="METER", operations=(MeshOperation(op="scale", factors=(2.0, 2.0, 2.0)),)
    )
    staying = MeshImport(
        units="METER", operations=(MeshOperation(op="translate", vector=(1.0, 0.0, 0.0)),)
    )
    assert any("operations scale" in text for text in _warnings(geometry, moving))
    assert _warnings(geometry, staying) == []
    assert _warnings(tmp_path / "plain.fsm") == []


@pytest.mark.requirement("FR-476")
def test_p0400_geom_migrate_the_plan_of_a_ccs_row_warns_and_still_binds(tmp_path):
    """P0400-GEOM-MIGRATE (PFS-2081.41): R1, through the plan's binding."""
    from tests.tier1_offline.test_p0320_ccs import THREE, _row_case

    with pytest.warns(PyflightstreamWarning, match="0.41.0 refuses"):
        case = _row_case(tmp_path, "wing", 'kind = "wing"\ncomponent = 1\n', ["W1"], text=THREE)
    assert case.mesh_import is not None and case.mesh_import.ccs is not None


@pytest.mark.requirement("FR-476")
def test_p0400_geom_migrate_the_converter_writes_an_instruction_that_reads(
    tmp_path, monkeypatch, capsys
):
    """P0400-GEOM-MIGRATE (PFS-2081.41): R2, a raw mesh with a rename, a scale and a translate."""
    root = workspace(tmp_path)
    folder = root / "inputs" / "geometries" / "blade"
    folder.mkdir()
    wing_obj(folder / "blade.obj", group="naca")
    (folder / "blade.boundaries.toml").write_text(
        'boundaries = ["naca"]\n[import]\nunits = "METER"\n'
        '[[import.operations]]\nop = "rename"\nsurface = "naca"\nto = "Wing"\n'
        '[[import.operations]]\nop = "scale"\nfactors = [2.0, 2.0, 2.0]\n'
        '[[import.operations]]\nop = "translate"\nvector = [1.0, 0.0, 0.0]\n'
        '[trailing_edges]\ndetect = "auto"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    assert main(["geometry", "from-sidecar", "blade.obj", "--build", "26.125"]) == 0
    assert not (folder / "blade.geometry.toml").exists()
    assert main(["geometry", "from-sidecar", "blade.obj", "--build", "26.125", "--apply"]) == 0
    out = capsys.readouterr().out
    assert "operation 3 (translate) stay in the run" in out
    assert "name blade_ops.obj in the GEOMETRY cell" in out
    instruction = read_geometry_instruction(folder / "blade.geometry.toml")
    assert instruction.boundaries == ("Wing",)
    assert [op.op for op in instruction.operations] == ["rename", "scale"]
    assert instruction.fs_build == "26.125"
    assert main(["geometry", "from-sidecar", "blade.obj", "--apply"]) == 2


@pytest.mark.requirement("FR-476")
def test_p0400_geom_migrate_the_converter_reads_a_ccs_sidecar(tmp_path, monkeypatch):
    """P0400-GEOM-MIGRATE (PFS-2081.41): R2, [import.ccs] becomes [ccs]."""
    root = workspace(tmp_path)
    folder = root / "inputs" / "geometries" / "wing"
    folder.mkdir()
    (folder / "wing.csv").write_text(ccs_text(), encoding="utf-8")
    (folder / "wing.boundaries.toml").write_text(
        'boundaries = ["WING"]\n[import]\nunits = "METER"\n[import.ccs]\nkind = "wing"\n'
        "component = 1\n\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    assert main(["geometry", "from-sidecar", "wing.csv", "--build", "26.125", "--apply"]) == 0
    instruction = read_geometry_instruction(folder / "wing.geometry.toml")
    assert instruction.kind == "ccs" and instruction.ccs is not None
    assert instruction.ccs.options.component == 1


def test_p0400_geom_migrate_the_converter_refuses_a_flat_geometry(tmp_path):
    """P0400-GEOM-MIGRATE (PFS-2081.41): R2, a flat library is migrated first."""
    from pyflightstream.workspace._geometry_convert import instruction_from_sidecar

    root = workspace(tmp_path)
    (root / "inputs" / "geometries" / "flat.stl").write_text("solid x\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="migrate-geometries"):
        instruction_from_sidecar("flat.stl", root=root)
