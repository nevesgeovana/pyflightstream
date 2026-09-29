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
    ids=(
        "geometric_pitch",
        "mass_per_length",
        "inertia_major",
        "inertia_minor",
        "bending_stiffness",
        "torsional_stiffness",
        "elastic_axis_offset_chordwise",
        "elastic_axis_offset_normal",
        "cg_offset_chordwise",
        "cg_offset_normal",
    ),
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
    # The sections are geometry: no material factor reaches them.
    assert effective.pop("section_contours_m") == base.pop("section_contours_m")
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


CALIBRATABLE_FIELDS = {
    "geometric_pitch_deg",
    "mass_per_length_kg_per_m",
    "inertia_major_kg_m",
    "inertia_minor_kg_m",
    "bending_stiffness_n_m2",
    "torsion_stiffness_n_m2",
    "elastic_axis_offset_chordwise_m",
    "elastic_axis_offset_normal_m",
    "cg_offset_chordwise_m",
    "cg_offset_normal_m",
    "density_kg_per_m3",
    "youngs_modulus_pa",
    "shear_modulus_pa",
    "poisson_ratio",
}


def test_absent_calibration_keeps_every_property_and_factor_at_unity(tmp_path):
    """Both property modes, with no factor named, resolve every factor to unity.

    Coordinates (station radii, chord) and provenance metadata carry no
    factor at all: the factor set is exactly the fourteen physical fields.

    GOAL033:fsi:checks:unity_default
    """
    for name, template in (("supplied", SUPPLIED), ("calculated", CALCULATED)):
        path = tmp_path / name / "f001.toml"
        path.parent.mkdir()
        path.write_text(template.replace("bending_stiffness_n_m2 = 2.0", ""), encoding="utf-8")
        result = resolve_fsi_setup(path)
        assert result.effective.model_dump() == result.base.model_dump(), name
        assert len(result.factors) == 14, name
        assert set(result.factors) == CALIBRATABLE_FIELDS, name
        assert set(result.factors.values()) == {1.0}, name
        assert set(result.origins.values()) == {"unity"}, name
        if result.material_base is not None:
            assert result.material_effective == result.material_base, name


def test_calibration_preserves_the_base_inputs_it_scales(tmp_path):
    """Every factor a mode admits, from file and matrix at once, leaves the base intact.

    The source file bytes, the resolved base and the staged base record stay
    those of the uncalibrated input, while every scaled effective value moves.

    GOAL033:fsi:checks:base_preserved
    """
    supplied = SUPPLIED.replace("bending_stiffness_n_m2 = 2.0\n", "")
    supplied = supplied.replace("= [0.0, 0.0]", "= [-0.001, 0.002]")
    supplied = supplied.replace(
        "geometric_pitch_deg = [-0.001, 0.002]", "geometric_pitch_deg = [-10.0, 20.0]"
    )
    calculated = CALCULATED.replace(
        "geometric_pitch_deg = [0.0, 0.0]", "geometric_pitch_deg = [-10.0, 20.0]"
    )
    cases = (
        (
            "supplied",
            supplied,
            {
                "bending_stiffness_n_m2": 2.0,
                "mass_per_length_kg_per_m": 1.2,
                "geometric_pitch_deg": 1.5,
                "elastic_axis_offset_chordwise_m": 1.1,
                "cg_offset_chordwise_m": 1.3,
            },
            {
                "torsion_stiffness_n_m2": 1.5,
                "inertia_major_kg_m": 1.25,
                "inertia_minor_kg_m": 1.25,
                "elastic_axis_offset_normal_m": 0.9,
                "cg_offset_normal_m": 0.8,
            },
        ),
        (
            "calculated",
            calculated,
            {"density_kg_per_m3": 1.05, "youngs_modulus_pa": 1.1},
            {"shear_modulus_pa": 1.2, "poisson_ratio": 1.02, "geometric_pitch_deg": 1.5},
        ),
    )
    for name, template, from_file, from_matrix in cases:
        reference_path = tmp_path / name / "reference.toml"
        reference_path.parent.mkdir()
        reference_path.write_text(template, encoding="utf-8")
        reference = resolve_fsi_setup(reference_path)
        assert set(reference.origins.values()) == {"unity"}, name
        block = "".join(f"{key} = {value}\n" for key, value in from_file.items())
        if "[calibration]\n" in template:
            source = template.replace("[calibration]\n", "[calibration]\n" + block)
        else:
            source = template.replace("[config]\n", "[calibration]\n" + block + "[config]\n")
        folder = tmp_path / name / "fsi"
        folder.mkdir()
        path = folder / "f001.toml"
        path.write_text(source, encoding="utf-8")
        source_bytes = path.read_bytes()
        row = {"FSI": "f001"}
        row.update({f"FSI_{key.upper()}_FACTOR": str(value) for key, value in from_matrix.items()})
        result = resolve_row_fsi(tmp_path / name, row)
        assert result is not None, name
        assert path.read_bytes() == source_bytes, name
        assert result.base.model_dump() == reference.base.model_dump(), name
        assert result.base.blade.geometric_pitch_deg == [-10.0, 20.0], name
        assert result.material_base == reference.material_base, name
        for key, factor in {**from_file, **from_matrix}.items():
            assert result.factors[key] == factor, (name, key)
            assert result.origins[key] == ("file" if key in from_file else "matrix"), (name, key)
            if key in CALIBRATABLE_FIELDS - set(result.material_base or {}):
                base_values = getattr(result.base.blade, key)
                assert getattr(result.effective.blade, key) == pytest.approx(
                    [factor * value for value in base_values]
                ), (name, key)
                assert getattr(result.effective.blade, key) != base_values, (name, key)
            else:
                assert result.material_effective[key] == pytest.approx(
                    factor * result.material_base[key]
                ), (name, key)
        if name == "supplied":
            assert result.base.blade.bending_stiffness_n_m2 == [10.0, 20.0]
            assert result.effective.blade.bending_stiffness_n_m2 == [20.0, 40.0]
        else:
            assert result.effective.blade.mass_per_length_kg_per_m != pytest.approx(
                result.base.blade.mass_per_length_kg_per_m
            )
        config, provenance = stage_fsi_setup(result, tmp_path / name / "run")
        recorded = json.loads(provenance.read_text())
        assert recorded["base"] == reference.base.model_dump(mode="json"), name
        assert recorded["source_sha256"] == hashlib.sha256(source_bytes).hexdigest(), name
        assert json.loads(config.read_text()) == result.effective.model_dump(mode="json"), name
        assert path.read_bytes() == source_bytes, name


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
