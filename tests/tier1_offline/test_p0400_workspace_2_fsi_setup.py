"""P0400-FSIROW: a row's FSI input is refused by name, and unity calibration changes nothing."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pyflightstream.fsi.materials import SHEAR_MODULUS_DERIVED
from pyflightstream.workspace import fsi_setup
from pyflightstream.workspace.fsi_setup import FsiSetupError, resolve_fsi_setup, resolve_row_fsi
from tests.tier1_offline.test_workspace_fsi_setup import CALCULATED, SUPPLIED


def test_p0400_fsirow_a_missing_input_lists_the_inputs_there(tmp_path: Path) -> None:
    """P0400-FSIROW (PFS-2095.031): FSI: f002 with only f001 present is an FsiSetupError naming
    the missing file and the inputs that exist, never a bare FileNotFoundError."""
    (tmp_path / "fsi").mkdir()
    (tmp_path / "fsi" / "f001.toml").write_text(SUPPLIED, encoding="utf-8")
    with pytest.raises(FsiSetupError, match=r"f002\.toml.*f001"):
        resolve_row_fsi(tmp_path, {"FSI": "f002"})


def test_p0400_fsirow_an_unknown_material_is_wrapped_naming_the_file(tmp_path: Path) -> None:
    """P0400-FSIROW (PFS-2095.031): the FSI package's refusal of an unknown material arrives as
    an FsiSetupError naming the source file."""
    path = tmp_path / "f002.toml"
    path.write_text(CALCULATED.replace("ti-6al-4v-grade5-annealed", "no-such-alloy"))
    with pytest.raises(FsiSetupError, match="f002.toml"):
        resolve_fsi_setup(path)


def test_p0400_fsirow_placeholder_factor_cells_beside_no_fsi_are_blank(tmp_path: Path) -> None:
    """P0400-FSIROW (PFS-2100.021): FSI: - with FSI_* factor cells of '-' states no FSI, as the
    factor loop already reads '-', and is not refused with the add-an-input remedy."""
    row = {"FSI": "-", "FSI_BENDING_STIFFNESS_N_M2_FACTOR": "-"}
    assert resolve_row_fsi(tmp_path, row) is None


def test_p0400_fsirow_a_derived_shear_modulus_stands_at_unity(tmp_path, monkeypatch) -> None:
    """P0400-FSIROW (PFS-2104.048): a derived-basis material whose stated G is rounded keeps it
    when no factor moves E or nu, so the effective beam is the base one with every origin unity;
    calibrating E re-derives G and says so in the origins."""
    titanium = fsi_setup.material("ti-6al-4v-grade5-annealed")
    rounded = replace(
        titanium,
        shear_modulus_basis=SHEAR_MODULUS_DERIVED,
        shear_modulus_pa=round(titanium.youngs_modulus_pa / (2 * (1 + titanium.poisson_ratio)), -9),
    )
    monkeypatch.setattr(fsi_setup, "material", lambda key: rounded)
    path = tmp_path / "f002.toml"
    path.write_text(CALCULATED)
    result = resolve_fsi_setup(path)
    assert set(result.origins.values()) == {"unity"}
    assert result.material_effective == result.material_base
    assert result.effective.blade == result.base.blade
    scaled = resolve_fsi_setup(path, matrix_calibration={"youngs_modulus_pa": 2.0})
    assert scaled.origins["shear_modulus_pa"].startswith("derived")
