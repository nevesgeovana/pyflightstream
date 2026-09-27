# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.2
# artifact_id: fsi-calibration-contract-tests
# last_modified_at: 2026-09-27T20:13:54.844Z
# last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
# dependencies: [pyflightstream.workspace.fsi_setup, test_workspace_fsi_setup]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Wrap long assertions after successful property and CLI acceptance.
# revision_source: git
# GEOVERSE_HEADER_END
"""Physical input invariants; these tests do not substitute for a coupled solve."""

import hashlib
import json

import pytest

from pyflightstream.workspace.fsi_setup import resolve_fsi_setup, resolve_row_fsi, stage_fsi_setup
from tests.tier1_offline.test_workspace_fsi_setup import CALCULATED, SUPPLIED


@pytest.mark.parametrize(
    ("property_name", "field"),
    [
        ("geometric_pitch", "geometric_pitch_deg"),
        ("mass_per_length", "mass_per_length_kg_per_m"),
        ("inertia_major", "inertia_major_kg_m"),
        ("inertia_minor", "inertia_minor_kg_m"),
        ("bending_stiffness", "bending_stiffness_n_m2"),
        ("torsional_stiffness", "torsion_stiffness_n_m2"),
        ("elastic_axis_offset_chordwise", "elastic_axis_offset_chordwise_m"),
        ("elastic_axis_offset_normal", "elastic_axis_offset_normal_m"),
        ("cg_offset_chordwise", "cg_offset_chordwise_m"),
        ("cg_offset_normal", "cg_offset_normal_m"),
    ],
    ids=lambda item: item,
)
def test_supplied_property_factor_preserves_base_and_other_properties(
    tmp_path, property_name, field
):
    """Only the named distribution changes, with file and matrix precedence.

    GOAL033:fsi:property_checks:geometric_pitch
    GOAL033:fsi:property_checks:mass_per_length
    GOAL033:fsi:property_checks:inertia_major
    GOAL033:fsi:property_checks:inertia_minor
    GOAL033:fsi:property_checks:bending_stiffness
    GOAL033:fsi:property_checks:torsional_stiffness
    GOAL033:fsi:property_checks:elastic_axis_offset_chordwise
    GOAL033:fsi:property_checks:elastic_axis_offset_normal
    GOAL033:fsi:property_checks:cg_offset_chordwise
    GOAL033:fsi:property_checks:cg_offset_normal
    """
    folder = tmp_path / "fsi"
    folder.mkdir()
    source = SUPPLIED.replace("bending_stiffness_n_m2 = 2.0", f"{field} = 2.0")
    source = source.replace("= [0.0, 0.0]", "= [-0.001, 0.002]")
    source = source.replace(
        "geometric_pitch_deg = [-0.001, 0.002]", "geometric_pitch_deg = [-10.0, 20.0]"
    )
    path = folder / "f001.toml"
    path.write_text(source, encoding="utf-8")
    source_bytes = path.read_bytes()
    file_result = resolve_fsi_setup(path)
    row_result = resolve_row_fsi(tmp_path, {"FSI": "f001", f"FSI_{field.upper()}_FACTOR": "1.5"})
    assert row_result is not None
    base = row_result.base.blade.model_dump()
    assert file_result.base.blade.model_dump() == base
    assert getattr(file_result.effective.blade, field) == pytest.approx(
        [2.0 * item for item in base[field]]
    )
    assert getattr(row_result.effective.blade, field) == pytest.approx(
        [1.5 * item for item in base[field]]
    )
    remaining = row_result.effective.blade.model_dump()
    remaining.pop(field)
    base.pop(field)
    assert remaining == base
    assert row_result.origins[field] == "matrix"
    assert file_result.origins[field] == "file"
    assert path.read_bytes() == source_bytes
    config, provenance = stage_fsi_setup(row_result, tmp_path / property_name)
    saved = json.loads(config.read_text())
    recorded = json.loads(provenance.read_text())
    assert saved["blade"][field] == getattr(row_result.effective.blade, field)
    assert recorded["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert recorded["base"]["blade"][field] == getattr(row_result.base.blade, field)
    assert recorded["effective"]["blade"][field] == saved["blade"][field]


@pytest.mark.parametrize(
    ("property_name", "field", "affected"),
    [
        (
            "density",
            "density_kg_per_m3",
            ("mass_per_length_kg_per_m", "inertia_major_kg_m", "inertia_minor_kg_m"),
        ),
        ("young_modulus", "youngs_modulus_pa", ("bending_stiffness_n_m2",)),
        ("shear_modulus", "shear_modulus_pa", ("torsion_stiffness_n_m2",)),
        ("poisson_ratio", "poisson_ratio", ()),
    ],
    ids=("density", "young_modulus", "shear_modulus", "poisson_ratio"),
)
def test_material_factor_changes_only_its_physical_dependents(
    tmp_path, property_name, field, affected
):
    """Keep sourced G independent of E and nu; scale derived sections once.

    GOAL033:fsi:property_checks:density
    GOAL033:fsi:property_checks:young_modulus
    GOAL033:fsi:property_checks:shear_modulus
    GOAL033:fsi:property_checks:poisson_ratio
    """
    folder = tmp_path / "fsi"
    folder.mkdir()
    source = CALCULATED.replace("[config]", f"[calibration]\n{field} = 1.05\n[config]")
    path = folder / "f001.toml"
    path.write_text(source, encoding="utf-8")
    file_result = resolve_fsi_setup(path)
    result = resolve_row_fsi(tmp_path, {"FSI": "f001", f"FSI_{field.upper()}_FACTOR": "1.1"})
    assert result is not None
    assert result.material_base is not None and result.material_effective is not None
    assert file_result.material_effective[field] == pytest.approx(
        result.material_base[field] * 1.05
    )
    assert result.material_effective[field] == pytest.approx(result.material_base[field] * 1.1)
    for key, original in result.material_base.items():
        if key != field:
            assert result.material_effective[key] == original
    base, effective = result.base.blade.model_dump(), result.effective.blade.model_dump()
    assert base.pop("provenance")["material"][field] == result.material_base[field]
    assert effective.pop("provenance")["material"][field] == result.material_effective[field]
    for key, original in base.items():
        assert effective[key] == pytest.approx(
            [value * 1.1 for value in original] if key in affected else original
        )
    assert result.origins[field] == "matrix"
    assert path.read_text(encoding="utf-8") == source
    config, provenance = stage_fsi_setup(result, tmp_path / property_name)
    assert json.loads(config.read_text()) == result.effective.model_dump(mode="json")
    assert json.loads(provenance.read_text())["material_base"] == result.material_base


def test_supplied_stiffness_and_mass_need_no_material_inference(tmp_path):
    """GOAL033:fsi:checks:supplied_stiffness_mass."""
    path = tmp_path / "f001.toml"
    path.write_text(SUPPLIED, encoding="utf-8")
    result = resolve_fsi_setup(path)
    assert result.material_base is None and result.material_effective is None
    assert result.effective.blade.bending_stiffness_n_m2 == [20.0, 40.0]
    assert result.effective.blade.mass_per_length_kg_per_m == [1.0, 2.0]
    assert result.effective.blade.torsion_stiffness_n_m2 == [5.0, 10.0]


@pytest.mark.parametrize("template", [SUPPLIED, CALCULATED], ids=["supplied", "calculated"])
def test_absent_calibration_keeps_every_property_and_factor_at_unity(tmp_path, template):
    """GOAL033:fsi:checks:unity_default."""
    path = tmp_path / "f001.toml"
    path.write_text(template.replace("bending_stiffness_n_m2 = 2.0", ""), encoding="utf-8")
    result = resolve_fsi_setup(path)
    assert result.effective.model_dump() == result.base.model_dump()
    assert len(result.factors) == 14
    assert set(result.factors.values()) == {1.0}
    assert set(result.origins.values()) == {"unity"}


def test_explicit_matrix_unity_overrides_file_calibration(tmp_path):
    """GOAL033:fsi:checks:matrix_override."""
    path = tmp_path / "f001.toml"
    path.write_text(SUPPLIED, encoding="utf-8")
    file_result = resolve_fsi_setup(path)
    selected = resolve_fsi_setup(path, matrix_calibration={"bending_stiffness_n_m2": 1.0})
    assert file_result.effective.blade.bending_stiffness_n_m2 == [20.0, 40.0]
    assert selected.effective.blade.bending_stiffness_n_m2 == [10.0, 20.0]
    assert selected.effective.model_dump() == selected.base.model_dump()
    assert selected.origins["bending_stiffness_n_m2"] == "matrix"
