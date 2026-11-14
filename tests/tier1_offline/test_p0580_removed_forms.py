"""P0580-REMOVED-FORMS (PFS-2237): every form that was deprecated is refused by name.

Each old form of the former deprecation ledger no longer works. A person who still writes it
is told what it became, so the migration is one edit and not a search. One test per form: it
runs the real entry point with the old spelling and requires the refusal to name the new one.
"""

import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.workspace import sector_to_wheel
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0540_wheel_obj import build_sector
from tests.tier1_offline.test_p0560_morph import build, control, invoke


def test_p0580_hub_rings_width_key_is_refused_naming_band_width(tmp_path, capsys):
    source = build(tmp_path)
    cfg = control(tmp_path, "[hub_rings]\nrings = 4\nwidth = 0.04\n")
    out = tmp_path / "rings.obj"
    assert invoke("hub-rings", source, cfg, out) == 2
    said = capsys.readouterr().err
    assert "width" in said and "band_width" in said and "no longer accepted" in said, said
    assert not out.exists()


def test_p0580_sector_to_wheel_hub_argument_is_refused_naming_center(tmp_path):
    sector = build_sector(tmp_path)
    with pytest.raises(InputValueError, match=r"center \(CLI: --center\)") as refused:
        sector_to_wheel(sector.obj, copies=6, blades=["Blade1"], hub=[0, 0, 0])
    assert "no longer accepted" in str(refused.value)
    # Stating the replacement beside it does not make the old form pass.
    with pytest.raises(InputValueError, match="no longer accepted"):
        sector_to_wheel(sector.obj, copies=6, blades=["Blade1"], center=[0, 0, 0], hub=[0, 0, 0])


def test_p0580_sector_to_wheel_hub_flag_is_refused_naming_center(tmp_path, capsys):
    sector = build_sector(tmp_path)
    out = tmp_path / "wheel.obj"
    code = main(
        [
            "geometry",
            "sector-to-wheel",
            str(sector.obj),
            "--copies",
            "6",
            "--blades",
            "Blade1",
            "--out",
            str(out),
            "--hub",
            "0",
            "0",
            "0",
        ]
    )
    said = capsys.readouterr().err
    assert code == 2 and "--center" in said and "no longer accepted" in said, said
    assert not out.exists()
