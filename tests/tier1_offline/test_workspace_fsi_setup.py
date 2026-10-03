# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
import json
from pathlib import Path

import pytest

from pyflightstream.workspace.fsi_setup import (
    FsiSetupError,
    load_fsi_setup,
    resolve_fsi_setup,
    resolve_row_fsi,
    stage_fsi_setup,
)

SUPPLIED = """mode = "supplied"
[calibration]
bending_stiffness_n_m2 = 2.0
[config]
blade_count = 2
omega_rad_per_s = 0.0
[config.blade]
station_radii_m = [0.1, 0.5]
chord_m = [0.04, 0.04]
mass_per_length_kg_per_m = [1.0, 2.0]
inertia_major_kg_m = [0.001, 0.002]
inertia_minor_kg_m = [0.0001, 0.0002]
bending_stiffness_n_m2 = [10.0, 20.0]
torsion_stiffness_n_m2 = [5.0, 10.0]
elastic_axis_offset_chordwise_m = [0.0, 0.0]
elastic_axis_offset_normal_m = [0.0, 0.0]
cg_offset_chordwise_m = [0.0, 0.0]
cg_offset_normal_m = [0.0, 0.0]
geometric_pitch_deg = [0.0, 0.0]
"""


@pytest.mark.requirement("FR-155")
def test_matrix_factor_replaces_file_factor_once(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:matrix_calibration
    path = tmp_path / "f001.toml"
    path.write_text(SUPPLIED, encoding="utf-8")
    resolved = load_fsi_setup(path, matrix_calibration={"bending_stiffness_n_m2": 3.0})
    assert resolved.blade.bending_stiffness_n_m2 == [30.0, 60.0]


def test_base_provenance_and_staged_effective_config(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:file_calibration
    path = tmp_path / "f001.toml"
    path.write_text(SUPPLIED, encoding="utf-8")
    result = resolve_fsi_setup(path)
    assert result.base.blade.bending_stiffness_n_m2 == [10, 20]
    assert result.effective.blade.bending_stiffness_n_m2 == [20, 40]
    assert result.origins["bending_stiffness_n_m2"] == "file"
    assert result.origins["torsion_stiffness_n_m2"] == "unity"
    config, receipt = stage_fsi_setup(result, tmp_path / "run")
    assert json.loads(config.read_text())["blade"]["bending_stiffness_n_m2"] == [20, 40]
    assert json.loads(receipt.read_text())["base"]["blade"]["bending_stiffness_n_m2"] == [10, 20]


@pytest.mark.parametrize("factor", [0, -1, float("inf"), float("nan"), True])
def test_invalid_factor_is_rejected(tmp_path: Path, factor: float) -> None:
    path = tmp_path / "f001.toml"
    path.write_text(SUPPLIED, encoding="utf-8")
    with pytest.raises(FsiSetupError, match="finite positive"):
        resolve_fsi_setup(path, matrix_calibration={"mass_per_length_kg_per_m": factor})


def test_second_solve_time_scale_is_rejected(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:apply_once
    path = tmp_path / "f001.toml"
    path.write_text(
        SUPPLIED.replace("blade_count = 2", "blade_count = 2\nstiffness_scale_factor = 2")
    )
    with pytest.raises(FsiSetupError, match="second solve-time"):
        resolve_fsi_setup(path)


def test_row_resolves_f_code_and_rejects_orphan_or_unknown_factor(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:f_toml
    (tmp_path / "fsi").mkdir()
    (tmp_path / "fsi" / "f001.toml").write_text(SUPPLIED)
    resolved = resolve_row_fsi(tmp_path, {"FSI": "f001", "FSI_BENDING_STIFFNESS_N_M2_FACTOR": "1"})
    assert resolved is not None
    assert resolved.effective.blade.bending_stiffness_n_m2 == [10, 20]
    assert resolved.origins["bending_stiffness_n_m2"] == "matrix"
    with pytest.raises(FsiSetupError, match="states no FSI"):
        resolve_row_fsi(tmp_path, {"FSI_BENDING_STIFFNESS_N_M2_FACTOR": "2"})
    with pytest.raises(FsiSetupError, match="unknown FSI"):
        resolve_row_fsi(tmp_path, {"FSI": "f001", "FSI_EI": "2"})
    with pytest.raises(FsiSetupError, match="f-prefixed"):
        resolve_row_fsi(tmp_path, {"FSI": "../f001"})


CALCULATED = """mode = "calculated"
material = "ti-6al-4v-grade5-annealed"
[config]
blade_count = 2
omega_rad_per_s = 0.0
[sections]
station_radii_m = [0.1, 0.5]
chord_m = [0.04, 0.04]
geometric_pitch_deg = [0.0, 0.0]
geometry_source = "synthetic rectangular test, SI"
torsion_grid_cells = 16
sections_m = [
  [[-0.02, -0.002], [0.02, -0.002], [0.02, 0.002], [-0.02, 0.002]],
  [[-0.02, -0.002], [0.02, -0.002], [0.02, 0.002], [-0.02, 0.002]]
]
"""


def test_calculated_grade5_density_changes_mass_once(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:calculated_section_mass
    path = tmp_path / "f002.toml"
    path.write_text(CALCULATED)
    result = resolve_fsi_setup(path, matrix_calibration={"density_kg_per_m3": 2})
    assert result.base.blade.mass_per_length_kg_per_m == pytest.approx([0.7088, 0.7088])
    assert result.effective.blade.mass_per_length_kg_per_m == pytest.approx([1.4176, 1.4176])
    assert result.material_base["shear_modulus_pa"] == 44e9
    assert result.material_effective["density_kg_per_m3"] == 8860
    assert result.effective.blade.bending_stiffness_n_m2 == result.base.blade.bending_stiffness_n_m2


def test_source_and_derived_double_calibration_rejected(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:derived_source_conflicts
    path = tmp_path / "f002.toml"
    path.write_text(CALCULATED)
    with pytest.raises(FsiSetupError, match="twice"):
        resolve_fsi_setup(
            path, matrix_calibration={"youngs_modulus_pa": 2, "bending_stiffness_n_m2": 2}
        )


def test_invalid_effective_principal_inertia_rejected(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:physical_admissibility
    path = tmp_path / "f001.toml"
    path.write_text(SUPPLIED)
    with pytest.raises(FsiSetupError, match="major is smaller"):
        resolve_fsi_setup(path, matrix_calibration={"inertia_minor_kg_m": 20})


def test_existing_run_writer_stages_and_hashes_fsi_per_point(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:resolved_provenance
    from pyflightstream._digest import file_sha256
    from pyflightstream.cases import SimCase, SweepAxis
    from pyflightstream.run._pending import _write_pending_files
    from pyflightstream.script import Script

    source = tmp_path / "f001.toml"
    source.write_text(SUPPLIED)
    resolved = resolve_fsi_setup(source)
    case = SimCase(
        sim_id="001",
        aircraft="Synthetic",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0]),
        fsi=resolved.effective,
        fsi_provenance=resolved.provenance(),
    )
    run_dir = tmp_path / "point"
    script = Script("26.120")
    digests = _write_pending_files(script, run_dir, case=case, recorded={})
    assert digests["config.json"] == file_sha256(run_dir / "config.json")
    assert digests["fsi-provenance.json"] == file_sha256(run_dir / "fsi-provenance.json")
    assert digests["f001.toml"] == file_sha256(source)
    assert json.loads((run_dir / "config.json").read_text())["blade"]["bending_stiffness_n_m2"] == [
        20,
        40,
    ]
    assert not (tmp_path / "inputs" / "config.json").exists()


def test_matrix_binding_reaches_effective_case_and_registered_vocabulary(tmp_path: Path) -> None:
    # GOAL033:fsi:checks:workspace_integration
    import sys

    from pyflightstream.cases.matrix import _COLUMNS
    from pyflightstream.cases.workflows import ROW_KEY_MEANINGS, workflow_registry
    from pyflightstream.script import Script
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.matrix import resolve_matrix

    workspace = CampaignWorkspace.init(tmp_path / "workspace")
    inputs = workspace.inputs_dir
    (inputs / "fsi").mkdir(exist_ok=True)
    (inputs / "fsi" / "f001.toml").write_text(SUPPLIED)
    (inputs / "references" / "r001.toml").write_text("area_m2=1.0\nchord_m=1.0\nspan_m=2.0\n")
    (inputs / "setups" / "s001.toml").write_text("iterations=10\n")
    (inputs / "pproc" / "p001.toml").write_text('[groups]\n"1"="all"\n')
    values = dict.fromkeys(_COLUMNS, "-")
    values.update(
        POL="001",
        RUN="1",
        HIDDEN="0",
        AIRCRAFT="Synthetic",
        DESCRIPTION="FSI",
        FLIGHT_CONDITION="MACH: 0.1, ALPHA: sweep",
        SWEEP_VALUES="0",
        REF="r001",
        SET="s001",
        PPROC="p001",
        WORKFLOW="steady",
        VAR_NAMES_VALUES="FSI: f001 / FSI_BENDING_STIFFNESS_N_M2_FACTOR: 3",
    )
    matrix_path = tmp_path / "case.fs"
    matrix_path.write_text(
        " | ".join(_COLUMNS) + "\n" + " | ".join(values[name] for name in _COLUMNS) + "\n"
    )
    result = resolve_matrix(
        matrix_path, workspace, name="fsi", fs_version="26.120", recipes={}, fs_exe=sys.executable
    )
    assert result.campaign.sims[0].fsi.blade.bending_stiffness_n_m2 == [30, 60]
    assert result.fsis["001"].origins["bending_stiffness_n_m2"] == "matrix"
    assert "FSI" in ROW_KEY_MEANINGS
    script = Script("26.120")
    # Selection is now active coupling; a steady row must not silently ignore it.
    # Until the fixed-wing route (FSI-G) wires it, the refusal says so.
    with pytest.raises(ValueError, match="FSI-G"):
        workflow_registry()["steady"](result.campaign.sims[0], script)
    assert "START_SOLVER" not in script.render()


@pytest.mark.parametrize(
    "factors", [{}, {"density_kg_per_m3": 2.0}, {"youngs_modulus_pa": 2.0}, {"poisson_ratio": 1.1}]
)
def test_tabulated_shear_modulus_is_not_silently_rederived(tmp_path: Path, factors) -> None:
    path = tmp_path / "f002.toml"
    path.write_text(CALCULATED)
    result = resolve_fsi_setup(path, matrix_calibration=factors)
    assert result.material_effective["shear_modulus_pa"] == 44e9
    assert result.effective.blade.torsion_stiffness_n_m2 == result.base.blade.torsion_stiffness_n_m2


def test_tabulated_youngs_and_torsion_factors_remain_independent(tmp_path: Path) -> None:
    path = tmp_path / "f002.toml"
    path.write_text(CALCULATED)
    result = resolve_fsi_setup(
        path, matrix_calibration={"youngs_modulus_pa": 2.0, "torsion_stiffness_n_m2": 3.0}
    )
    assert result.effective.blade.bending_stiffness_n_m2 == pytest.approx(
        [2.0 * value for value in result.base.blade.bending_stiffness_n_m2]
    )
    assert result.effective.blade.torsion_stiffness_n_m2 == pytest.approx(
        [3.0 * value for value in result.base.blade.torsion_stiffness_n_m2]
    )


def test_derived_shear_still_tracks_modulus_and_refuses_double_scaling(tmp_path, monkeypatch):
    from dataclasses import replace

    from pyflightstream.fsi.materials import SHEAR_MODULUS_DERIVED, material
    from pyflightstream.workspace import fsi_setup

    titanium = material("ti-6al-4v-grade5-annealed")
    derived = replace(
        titanium,
        shear_modulus_basis=SHEAR_MODULUS_DERIVED,
        shear_modulus_pa=titanium.youngs_modulus_pa / (2 * (1 + titanium.poisson_ratio)),
    )
    monkeypatch.setattr(fsi_setup, "material", lambda key: derived)
    path = tmp_path / "f002.toml"
    path.write_text(CALCULATED)
    result = resolve_fsi_setup(path, matrix_calibration={"youngs_modulus_pa": 2.0})
    assert result.material_effective["shear_modulus_pa"] == pytest.approx(
        2.0 * derived.shear_modulus_pa
    )
    assert result.effective.blade.torsion_stiffness_n_m2 == pytest.approx(
        [2.0 * value for value in result.base.blade.torsion_stiffness_n_m2]
    )
    with pytest.raises(FsiSetupError, match="torsion twice"):
        resolve_fsi_setup(
            path, matrix_calibration={"youngs_modulus_pa": 2.0, "torsion_stiffness_n_m2": 3.0}
        )


@pytest.mark.parametrize("template", [SUPPLIED, CALCULATED], ids=["supplied", "calculated"])
@pytest.mark.parametrize("angles", [[-60.0, 20.0], [0.0, 60.0]])
def test_geometric_pitch_calibration_reaches_structural_nodes_once(tmp_path, template, angles):
    import math

    from pyflightstream.fsi.nodes import generate_node_layout, node_positions

    source = template.replace("bending_stiffness_n_m2 = 2.0", "bending_stiffness_n_m2 = 1.0")
    source = source.replace("omega_rad_per_s = 0.0", "omega_rad_per_s = 100.0")
    source = source.replace("geometric_pitch_deg = [0.0, 0.0]", f"geometric_pitch_deg = {angles}")
    if "[calibration]" in source:
        source = source.replace("[calibration]", "[calibration]\ngeometric_pitch_deg = 2.0")
    else:
        source = source.replace("[config]", "[calibration]\ngeometric_pitch_deg = 2.0\n[config]")
    folder = tmp_path / "fsi"
    folder.mkdir()
    path = folder / "f001.toml"
    path.write_text(source, encoding="utf-8")
    file_result = resolve_fsi_setup(path)
    assert file_result.effective.blade.geometric_pitch_deg == pytest.approx([2 * a for a in angles])
    result = resolve_row_fsi(tmp_path, {"FSI": "f001", "FSI_GEOMETRIC_PITCH_DEG_FACTOR": "1.5"})
    assert result is not None
    effective_angles = [1.5 * a for a in angles]
    assert result.base.blade.geometric_pitch_deg == angles
    assert result.effective.blade.geometric_pitch_deg == pytest.approx(effective_angles)
    assert result.origins["geometric_pitch_deg"] == "matrix"
    assert path.read_text(encoding="utf-8") == source
    base_properties = result.base.blade.model_dump()
    effective_properties = result.effective.blade.model_dump()
    base_properties.pop("geometric_pitch_deg")
    effective_properties.pop("geometric_pitch_deg")
    assert effective_properties == base_properties
    base_map = generate_node_layout(result.base)
    effective_map = generate_node_layout(result.effective)
    assert effective_map.blade_angle_deg == pytest.approx(effective_angles)
    base_layout, effective_layout = base_map.model_dump(), effective_map.model_dump()
    base_layout.pop("blade_angle_deg")
    effective_layout.pop("blade_angle_deg")
    assert effective_layout == base_layout
    positions = node_positions(effective_map)
    # The supplied blade states offsets: the leading-edge node sits 0.25 chord
    # ahead of the elastic axis. The calculated blade carries its 40 mm section,
    # so the nodes sit on its camber line (FSI-1): the elastic axis at the
    # centroid, half chord, and the leading-edge node at 10 % chord, 0.4 chord
    # ahead of it.
    lead = 0.01 if template is SUPPLIED else 0.016
    for station, angle in enumerate(effective_angles):
        radians = math.radians(angle)
        radius = result.base.blade.station_radii_m[station]
        assert positions[3 * station] == pytest.approx([0.0, 0.0, radius], abs=1e-14)
        assert positions[3 * station + 1] == pytest.approx(
            [-lead * math.sin(radians), -lead * math.cos(radians), radius], abs=1e-14
        )
